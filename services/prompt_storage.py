"""
Prompt library storage service.
Supports local JSON storage and Cloudflare R2 cloud sync.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .r2_storage import get_r2_storage


class PromptStorage:
    """Service for storing and managing prompt library."""

    def __init__(self, user_id: str | None = None):
        """
        Initialize the prompt storage service.

        Args:
            user_id: Optional user ID for user-specific favorites
        """
        self.user_id = user_id
        self.base_dir = Path("data/prompts")
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # User-specific favorites directory
        if user_id:
            self.favorites_dir = self.base_dir / "favorites" / user_id
            self.favorites_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.favorites_dir = self.base_dir / "favorites" / "shared"
            self.favorites_dir.mkdir(parents=True, exist_ok=True)

        # R2 storage for cloud sync
        self._r2 = get_r2_storage(user_id=user_id)

        # In-memory cache
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._cache_timestamp: dict[str, float] = {}
        self.cache_ttl = 300  # 5 minutes

    @property
    def r2_enabled(self) -> bool:
        """Check if R2 cloud storage is enabled."""
        return self._r2.is_available

    def _get_category_file(self, category: str, language: str = "en") -> Path:
        """Get the file path for a category with language support."""
        return self.base_dir / f"{category}_{language}.json"

    def _get_favorites_file(self) -> Path:
        """Get the favorites file path."""
        return self.favorites_dir / "favorites.json"

    def save_category_prompts(
        self,
        category: str,
        prompts: list[dict[str, Any]],
        sync_to_cloud: bool = True,
        language: str = "en",
    ) -> bool:
        """
        Save prompts for a category.

        Args:
            category: Category name
            prompts: List of prompt dictionaries
            sync_to_cloud: Whether to sync to R2 cloud storage
            language: Language code ("en" or "zh")

        Returns:
            True if saved successfully
        """
        try:
            file_path = self._get_category_file(category, language)

            data = {
                "category": category,
                "language": language,
                "prompts": prompts,
                "count": len(prompts),
                "updated_at": datetime.now().isoformat(),
                "version": 1,
            }

            # Save locally
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Invalidate cache
            if category in self._cache:
                del self._cache[category]

            # Sync to R2 if enabled
            if sync_to_cloud and self.r2_enabled:
                self._sync_to_r2(category, data, language)

            return True

        except Exception as e:
            print(f"Failed to save prompts for {category}: {e}")
            return False

    def load_category_prompts(
        self, category: str, use_cache: bool = True, try_cloud: bool = True, language: str = "en"
    ) -> list[dict[str, Any]]:
        """
        Load prompts for a category.

        Args:
            category: Category name
            use_cache: Whether to use cached data
            try_cloud: Whether to try loading from cloud if local not found
            language: Language code ("en" or "zh")

        Returns:
            List of prompt dictionaries
        """
        cache_key = f"{category}_{language}"

        # Check cache first
        if use_cache and cache_key in self._cache:
            cache_age = datetime.now().timestamp() - self._cache_timestamp.get(cache_key, 0)
            if cache_age < self.cache_ttl:
                return self._cache[cache_key]

        # Try local file
        file_path = self._get_category_file(category, language)
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                    prompts = data.get("prompts", [])
                    # Update cache
                    self._cache[cache_key] = prompts
                    self._cache_timestamp[cache_key] = datetime.now().timestamp()
                    return prompts
            except Exception as e:
                print(f"Failed to load local prompts for {category}_{language}: {e}")

        # Try R2 cloud storage
        if try_cloud and self.r2_enabled:
            prompts = self._load_from_r2(category, language)
            if prompts:
                # Save to local cache
                self.save_category_prompts(
                    category, prompts, sync_to_cloud=False, language=language
                )
                return prompts

        return []

    def get_all_categories(self, language: str = "en") -> list[str]:
        """Get list of all available categories for a language."""
        categories = set()

        # Local categories
        suffix = f"_{language}.json"
        for file_path in self.base_dir.glob(f"*{suffix}"):
            # Extract category name (remove language suffix)
            category = file_path.stem.replace(f"_{language}", "")
            if category not in ["index", "metadata"]:
                categories.add(category)

        # Cloud categories (if available)
        if self.r2_enabled:
            cloud_categories = self._list_r2_categories(language)
            categories.update(cloud_categories)

        return sorted(categories)

    def get_all_prompts(self) -> dict[str, list[dict[str, Any]]]:
        """Get all prompts from all categories."""
        all_prompts = {}
        for category in self.get_all_categories():
            prompts = self.load_category_prompts(category)
            if prompts:
                all_prompts[category] = prompts
        return all_prompts

    def add_prompt_to_category(
        self, category: str, prompt: dict[str, Any], position: str = "end", language: str = "en"
    ) -> bool:
        """
        Add a single prompt to a category.

        Args:
            category: Category name
            prompt: Prompt dictionary
            position: "start" or "end"
            language: Language code

        Returns:
            True if added successfully
        """
        prompts = self.load_category_prompts(category, language=language)

        # Add metadata
        if "created_at" not in prompt:
            prompt["created_at"] = datetime.now().isoformat()
        if "source" not in prompt:
            prompt["source"] = "user"

        # Add to list
        if position == "start":
            prompts.insert(0, prompt)
        else:
            prompts.append(prompt)

        return self.save_category_prompts(category, prompts, language=language)

    def add_to_favorites(self, prompt: dict[str, Any]) -> bool:
        """
        Add a prompt to user's favorites.

        Args:
            prompt: Prompt dictionary

        Returns:
            True if added successfully
        """
        try:
            favorites_file = self._get_favorites_file()

            # Load existing favorites
            if favorites_file.exists():
                with open(favorites_file, encoding="utf-8") as f:
                    favorites = json.load(f)
            else:
                favorites = []

            # Add new favorite
            favorite = prompt.copy()
            favorite["favorited_at"] = datetime.now().isoformat()

            # Check if already favorited (by prompt text)
            if not any(f.get("prompt") == prompt.get("prompt") for f in favorites):
                favorites.insert(0, favorite)

                # Save
                with open(favorites_file, "w", encoding="utf-8") as f:
                    json.dump(favorites, f, ensure_ascii=False, indent=2)

                return True

            return False

        except Exception as e:
            print(f"Failed to add to favorites: {e}")
            return False

    def get_favorites(self) -> list[dict[str, Any]]:
        """Get user's favorite prompts."""
        try:
            favorites_file = self._get_favorites_file()
            if favorites_file.exists():
                with open(favorites_file, encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Failed to load favorites: {e}")
        return []

    def remove_from_favorites(self, prompt_text: str) -> bool:
        """Remove a prompt from favorites by its text."""
        try:
            favorites_file = self._get_favorites_file()
            if not favorites_file.exists():
                return False

            with open(favorites_file, encoding="utf-8") as f:
                favorites = json.load(f)

            # Filter out the prompt
            new_favorites = [f for f in favorites if f.get("prompt") != prompt_text]

            if len(new_favorites) < len(favorites):
                with open(favorites_file, "w", encoding="utf-8") as f:
                    json.dump(new_favorites, f, ensure_ascii=False, indent=2)
                return True

            return False

        except Exception as e:
            print(f"Failed to remove from favorites: {e}")
            return False

    def search_prompts(self, query: str, category: str | None = None) -> list[dict[str, Any]]:
        """
        Search prompts by keyword.

        Args:
            query: Search query
            category: Optional category to search within

        Returns:
            List of matching prompts
        """
        query_lower = query.lower()
        results = []

        categories = [category] if category else self.get_all_categories()

        for cat in categories:
            prompts = self.load_category_prompts(cat)
            for prompt in prompts:
                prompt_text = prompt.get("prompt", "").lower()
                description = prompt.get("description", "").lower()
                tags = " ".join(prompt.get("tags", [])).lower()

                if query_lower in prompt_text or query_lower in description or query_lower in tags:
                    result = prompt.copy()
                    result["category"] = cat
                    results.append(result)

        return results

    # ============ R2 Cloud Sync Methods ============

    def _sync_to_r2(self, category: str, data: dict, language: str = "en") -> bool:
        """Sync category data to R2."""
        if not self.r2_enabled:
            return False

        try:
            key = f"prompts/library/{category}_{language}.json"
            self._r2._client.put_object(
                Bucket=self._r2.bucket_name,
                Key=key,
                Body=json.dumps(data, ensure_ascii=False, indent=2),
                ContentType="application/json",
                CacheControl="public, max-age=3600",  # 1 hour cache
            )
            print(f"[PromptStorage] Synced {category}_{language} to R2")
            return True
        except Exception as e:
            print(f"[PromptStorage] Failed to sync to R2: {e}")
            return False

    def _load_from_r2(self, category: str, language: str = "en") -> list[dict[str, Any]] | None:
        """Load category data from R2."""
        if not self.r2_enabled:
            return None

        try:
            key = f"prompts/library/{category}_{language}.json"
            response = self._r2._client.get_object(Bucket=self._r2.bucket_name, Key=key)
            data = json.loads(response["Body"].read().decode("utf-8"))
            print(f"[PromptStorage] Loaded {category}_{language} from R2")
            return data.get("prompts", [])
        except self._r2._client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            print(f"[PromptStorage] Failed to load from R2: {e}")
            return None

    def _list_r2_categories(self, language: str = "en") -> list[str]:
        """List available categories in R2."""
        if not self.r2_enabled:
            return []

        try:
            response = self._r2._client.list_objects_v2(
                Bucket=self._r2.bucket_name, Prefix="prompts/library/", Delimiter="/"
            )

            categories = set()
            if "Contents" in response:
                for obj in response["Contents"]:
                    key = obj["Key"]
                    if key.endswith(f"_{language}.json"):
                        # Extract category name
                        filename = key.split("/")[-1]
                        category = filename.replace(f"_{language}.json", "")
                        categories.add(category)

            return list(categories)
        except Exception as e:
            print(f"[PromptStorage] Failed to list R2 categories: {e}")
            return []

    def sync_all_to_cloud(self) -> dict[str, bool]:
        """Sync all local categories to cloud."""
        results = {}
        for category in self.get_all_categories():
            prompts = self.load_category_prompts(category, try_cloud=False)
            if prompts:
                data = {
                    "category": category,
                    "prompts": prompts,
                    "count": len(prompts),
                    "updated_at": datetime.now().isoformat(),
                    "version": 1,
                }
                results[category] = self._sync_to_r2(category, data)
        return results

    def clear_cache(self):
        """Clear the in-memory cache."""
        self._cache.clear()
        self._cache_timestamp.clear()


# Cache for user-specific storage instances
_storage_instances: dict[str | None, PromptStorage] = {}


def get_prompt_storage(user_id: str | None = None) -> PromptStorage:
    """
    Get or create a prompt storage instance.

    Args:
        user_id: Optional user ID for user-specific favorites

    Returns:
        PromptStorage instance
    """
    global _storage_instances

    if user_id not in _storage_instances:
        _storage_instances[user_id] = PromptStorage(user_id=user_id)

    return _storage_instances[user_id]


def get_current_user_prompt_storage() -> PromptStorage:
    """Get prompt storage for the currently authenticated user."""
    from .auth import get_user_id

    user_id = get_user_id()
    return get_prompt_storage(user_id=user_id)
