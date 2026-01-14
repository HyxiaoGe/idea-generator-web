"""
Prompts router for prompt library management.

Endpoints:
- GET /api/prompts - List prompts with filtering
- GET /api/prompts/categories - List available categories
- POST /api/prompts/generate - Generate prompts with AI
- POST /api/prompts - Save a custom prompt
- POST /api/prompts/{prompt_id}/favorite - Toggle favorite status
- DELETE /api/prompts/{prompt_id} - Delete a custom prompt
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query, Header

from core.config import get_settings
from services import PromptGenerator, get_prompt_generator, PromptStorage, get_prompt_storage
from api.schemas.prompts import (
    PromptTemplate,
    PromptCategory,
    ListPromptsResponse,
    GeneratePromptsRequest,
    GeneratePromptsResponse,
    ToggleFavoriteRequest,
    ToggleFavoriteResponse,
    SavePromptRequest,
    SavePromptResponse,
)
from api.routers.auth import get_current_user
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


# Available categories with metadata
PROMPT_CATEGORIES = [
    PromptCategory(name="portrait", display_name="Portrait", description="People and character portraits", icon="👤"),
    PromptCategory(name="landscape", display_name="Landscape", description="Nature and scenic views", icon="🏞️"),
    PromptCategory(name="food", display_name="Food", description="Culinary and food photography", icon="🍽️"),
    PromptCategory(name="abstract", display_name="Abstract", description="Abstract and artistic concepts", icon="🎨"),
    PromptCategory(name="architecture", display_name="Architecture", description="Buildings and structures", icon="🏛️"),
    PromptCategory(name="animals", display_name="Animals", description="Wildlife and pets", icon="🐾"),
    PromptCategory(name="fantasy", display_name="Fantasy", description="Magical and fantastical scenes", icon="🧙"),
    PromptCategory(name="scifi", display_name="Sci-Fi", description="Futuristic and sci-fi themes", icon="🚀"),
    PromptCategory(name="fashion", display_name="Fashion", description="Clothing and style", icon="👗"),
    PromptCategory(name="custom", display_name="Custom", description="User-created prompts", icon="✏️"),
]


# ============ Helpers ============

def get_user_id_from_user(user: Optional[GitHubUser]) -> Optional[str]:
    """Get user ID for storage access."""
    if user:
        return user.user_folder_id
    return None


def get_user_prompt_storage(user: Optional[GitHubUser]) -> PromptStorage:
    """Get prompt storage instance for user."""
    user_id = get_user_id_from_user(user)
    return get_prompt_storage(user_id=user_id)


# ============ Endpoints ============

@router.get("", response_model=ListPromptsResponse)
async def list_prompts(
    category: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    favorites_only: bool = Query(default=False),
    language: str = Query(default="en"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: Optional[GitHubUser] = Depends(get_current_user),
):
    """
    List prompts from the library with optional filtering.
    """
    storage = get_user_prompt_storage(user)

    all_prompts = []
    categories_with_counts = []

    # Load prompts from each category
    for cat in PROMPT_CATEGORIES:
        try:
            cat_prompts = storage.get_category_prompts(cat.name, language=language)

            # Get count for category
            cat_copy = cat.model_copy()
            cat_copy.count = len(cat_prompts)
            categories_with_counts.append(cat_copy)

            # Apply category filter
            if category and cat.name != category:
                continue

            for p in cat_prompts:
                prompt = PromptTemplate(
                    id=p.get("id", str(uuid.uuid4())),
                    text=p.get("text", p.get("prompt", "")),
                    description=p.get("description"),
                    category=cat.name,
                    tags=p.get("tags", []),
                    style=p.get("style"),
                    is_favorite=storage.is_favorite(p.get("id", "")),
                    language=language,
                )
                all_prompts.append(prompt)

        except Exception as e:
            logger.warning(f"Failed to load prompts for {cat.name}: {e}")
            cat_copy = cat.model_copy()
            cat_copy.count = 0
            categories_with_counts.append(cat_copy)

    # Apply favorites filter
    if favorites_only:
        all_prompts = [p for p in all_prompts if p.is_favorite]

    # Apply search filter
    if search:
        search_lower = search.lower()
        all_prompts = [
            p for p in all_prompts
            if search_lower in p.text.lower() or
               (p.description and search_lower in p.description.lower())
        ]

    # Apply pagination
    total = len(all_prompts)
    prompts_page = all_prompts[offset:offset + limit]

    return ListPromptsResponse(
        prompts=prompts_page,
        total=total,
        categories=categories_with_counts,
    )


@router.get("/categories", response_model=List[PromptCategory])
async def list_categories(
    language: str = Query(default="en"),
    user: Optional[GitHubUser] = Depends(get_current_user),
):
    """
    List available prompt categories with counts.
    """
    storage = get_user_prompt_storage(user)

    categories_with_counts = []
    for cat in PROMPT_CATEGORIES:
        try:
            prompts = storage.get_category_prompts(cat.name, language=language)
            cat_copy = cat.model_copy()
            cat_copy.count = len(prompts)
            categories_with_counts.append(cat_copy)
        except Exception:
            cat_copy = cat.model_copy()
            cat_copy.count = 0
            categories_with_counts.append(cat_copy)

    return categories_with_counts


@router.post("/generate", response_model=GeneratePromptsResponse)
async def generate_prompts(
    request: GeneratePromptsRequest,
    user: Optional[GitHubUser] = Depends(get_current_user),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """
    Generate new prompts using AI.

    Uses Gemini to create creative prompts for the specified category.
    """
    settings = get_settings()
    api_key = x_api_key or settings.google_api_key

    if not api_key:
        raise HTTPException(status_code=400, detail="No API key configured")

    try:
        generator = PromptGenerator(api_key=api_key)
        generated = generator.generate_category_prompts(
            category=request.category,
            style=request.style,
            count=request.count,
            language=request.language,
        )

        # Convert to response format
        prompts = []
        for p in generated:
            prompt = PromptTemplate(
                id=p.get("id", str(uuid.uuid4())),
                text=p.get("text", p.get("prompt", "")),
                description=p.get("description"),
                category=request.category,
                tags=p.get("tags", []),
                style=request.style,
                language=request.language,
                created_at=datetime.now(),
            )
            prompts.append(prompt)

        # Optionally save to storage
        storage = get_user_prompt_storage(user)
        saved = False
        try:
            storage.save_category_prompts(
                category=request.category,
                prompts=[p.model_dump() for p in prompts],
                language=request.language,
            )
            saved = True
        except Exception as e:
            logger.warning(f"Failed to save generated prompts: {e}")

        return GeneratePromptsResponse(
            prompts=prompts,
            count=len(prompts),
            category=request.category,
            saved=saved,
        )

    except Exception as e:
        logger.error(f"Prompt generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate prompts: {str(e)}")


@router.post("", response_model=SavePromptResponse)
async def save_custom_prompt(
    request: SavePromptRequest,
    user: Optional[GitHubUser] = Depends(get_current_user),
):
    """
    Save a custom prompt to the library.
    """
    storage = get_user_prompt_storage(user)

    prompt_id = str(uuid.uuid4())
    prompt_data = {
        "id": prompt_id,
        "text": request.text,
        "description": request.description,
        "tags": request.tags,
        "created_at": datetime.now().isoformat(),
    }

    try:
        # Get existing custom prompts
        existing = storage.get_category_prompts("custom", language=request.language)
        existing.append(prompt_data)

        # Save back
        storage.save_category_prompts(
            category="custom",
            prompts=existing,
            language=request.language,
        )

        prompt = PromptTemplate(
            id=prompt_id,
            text=request.text,
            description=request.description,
            category="custom",
            tags=request.tags,
            language=request.language,
            created_at=datetime.now(),
        )

        return SavePromptResponse(
            prompt=prompt,
            message="Prompt saved successfully",
        )

    except Exception as e:
        logger.error(f"Failed to save prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to save prompt")


@router.post("/{prompt_id}/favorite", response_model=ToggleFavoriteResponse)
async def toggle_favorite(
    prompt_id: str,
    user: Optional[GitHubUser] = Depends(get_current_user),
):
    """
    Toggle favorite status for a prompt.
    """
    storage = get_user_prompt_storage(user)

    try:
        is_favorite = storage.toggle_favorite(prompt_id)

        return ToggleFavoriteResponse(
            prompt_id=prompt_id,
            is_favorite=is_favorite,
            message="Favorite status updated",
        )

    except Exception as e:
        logger.error(f"Failed to toggle favorite: {e}")
        raise HTTPException(status_code=500, detail="Failed to update favorite status")


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: str,
    category: str = Query(default="custom"),
    language: str = Query(default="en"),
    user: Optional[GitHubUser] = Depends(get_current_user),
):
    """
    Delete a custom prompt from the library.

    Only custom prompts can be deleted.
    """
    if category != "custom":
        raise HTTPException(
            status_code=400,
            detail="Only custom prompts can be deleted"
        )

    storage = get_user_prompt_storage(user)

    try:
        # Get existing custom prompts
        existing = storage.get_category_prompts("custom", language=language)

        # Find and remove the prompt
        original_count = len(existing)
        existing = [p for p in existing if p.get("id") != prompt_id]

        if len(existing) == original_count:
            raise HTTPException(status_code=404, detail="Prompt not found")

        # Save back
        storage.save_category_prompts(
            category="custom",
            prompts=existing,
            language=language,
        )

        return {"success": True, "message": "Prompt deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete prompt")
