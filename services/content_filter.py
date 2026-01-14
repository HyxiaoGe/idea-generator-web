"""
Content filter service for prompt safety checking.
Prevents generation of NSFW/violent/illegal content.

Keywords are stored remotely in Cloudflare R2 to prevent user discovery.
"""
import os
import re
import json
from typing import List, Tuple, Optional
from datetime import datetime, timedelta


# Minimal fallback keywords (only used if R2 is unavailable)
# Full keyword list is stored remotely in R2 to prevent user discovery
# This is just a basic safety net - production MUST use R2 storage
DEFAULT_BANNED_KEYWORDS = [
    "nsfw", "porn", "xxx", "色情",
]


def get_config_value(key: str, default: str = "") -> str:
    """Get configuration value from environment variables."""
    return os.getenv(key, default)


class ContentFilter:
    """
    Two-layer content safety filter.
    Layer 1: Fast keyword matching (instant blocking) - loaded from remote R2
    Layer 2: AI-powered deep analysis (context-aware)
    """

    # R2 path for remote keyword storage
    REMOTE_KEYWORDS_KEY = "config/banned_keywords.json"
    CACHE_TTL = timedelta(hours=1)  # Cache keywords for 1 hour

    def __init__(self, api_key: str = None):
        """Initialize content filter with banned keywords and AI moderator."""
        self._keywords_cache = None
        self._keywords_cache_time = None

        # Load keywords (remote + local fallback)
        self.banned_keywords = self._load_keywords()

        # Check if filter is enabled
        self.enabled = get_config_value("CONTENT_FILTER_ENABLED", "true").lower() in ["true", "1", "yes"]

        # Initialize AI moderator (Layer 2)
        self.ai_moderator = None
        try:
            from .ai_content_moderator import get_ai_moderator
            self.ai_moderator = get_ai_moderator(api_key)
        except Exception as e:
            print(f"AI moderator not available: {e}")

    def _load_keywords(self) -> List[str]:
        """
        Load banned keywords from remote R2 storage.
        Falls back to default list if remote unavailable.
        """
        # Check cache first
        if self._keywords_cache and self._keywords_cache_time:
            if datetime.now() - self._keywords_cache_time < self.CACHE_TTL:
                return self._keywords_cache

        # Try to load from R2
        remote_keywords = self._load_from_r2()
        if remote_keywords:
            self._keywords_cache = remote_keywords
            self._keywords_cache_time = datetime.now()
            print(f"[ContentFilter] Loaded {len(remote_keywords)} keywords from R2")
            return remote_keywords

        # Fallback to minimal default keywords
        print("⚠️ [ContentFilter] WARNING: R2 unavailable, using minimal fallback keywords")
        print("⚠️ [ContentFilter] Production deployment MUST have R2 configured for full protection")
        custom_keywords = get_config_value("BANNED_KEYWORDS", "")
        custom_list = [k.strip().lower() for k in custom_keywords.split(",") if k.strip()] if custom_keywords else []
        return list(set(DEFAULT_BANNED_KEYWORDS + custom_list))

    def _load_from_r2(self) -> Optional[List[str]]:
        """Load keyword list from R2 storage."""
        try:
            from .r2_storage import get_r2_storage

            r2 = get_r2_storage()
            if not r2.is_available:
                return None

            # Download keywords JSON from R2
            response = r2._client.get_object(
                Bucket=r2.bucket_name,
                Key=self.REMOTE_KEYWORDS_KEY
            )
            content = response["Body"].read().decode("utf-8")
            data = json.loads(content)

            # Return the keywords list
            return data.get("keywords", [])

        except Exception as e:
            print(f"[ContentFilter] Failed to load from R2: {e}")
            return None

    def refresh_keywords(self):
        """Force refresh keywords from R2 (bypasses cache)."""
        self._keywords_cache = None
        self._keywords_cache_time = None
        self.banned_keywords = self._load_keywords()

    def is_safe(self, prompt: str, context: Optional[dict] = None) -> Tuple[bool, str]:
        """
        Two-layer safety check:
        1. Fast keyword blacklist (Layer 1)
        2. AI-powered analysis (Layer 2)

        Args:
            prompt: The user's prompt text
            context: Optional context dict (generation_mode, user_id, session_id, etc.)

        Returns:
            Tuple of (is_safe, reason)
            - is_safe: True if safe, False if blocked
            - reason: Empty string if safe, keyword/category if blocked
        """
        import time

        if not self.enabled:
            return True, ""

        # Track timing for audit
        start_time = time.time()
        layer1_time_ms = 0
        layer2_time_ms = 0

        # === LAYER 1: Keyword Blacklist (Fast) ===
        layer1_start = time.time()
        keyword_safe, keyword_reason = self._check_keywords(prompt)
        layer1_time_ms = (time.time() - layer1_start) * 1000

        layer1_result = {
            "checked": True,
            "passed": keyword_safe,
            "matched_keywords": [] if keyword_safe else [keyword_reason],
            "execution_time_ms": round(layer1_time_ms, 2),
            "total_keywords_count": len(self.banned_keywords)
        }

        # === LAYER 2: AI Deep Analysis (Slower but Smart) ===
        layer2_result = None
        ai_safe = True
        ai_reason = ""

        if self.ai_moderator and self.ai_moderator.enabled and keyword_safe:
            layer2_start = time.time()
            ai_safe, ai_reason = self.ai_moderator.check_safety(prompt)
            layer2_time_ms = (time.time() - layer2_start) * 1000

            # Check if result was cached
            cache_key = self.ai_moderator._get_cache_key(prompt)
            was_cached = cache_key in self.ai_moderator._cache

            layer2_result = {
                "checked": True,
                "passed": ai_safe,
                "classification": "safe" if ai_safe else "unsafe",
                "reason": ai_reason,
                "ai_raw_response": None,  # We don't store the full response
                "execution_time_ms": round(layer2_time_ms, 2),
                "model": "gemini-2.0-flash-exp",
                "cache_hit": was_cached
            }

        # === Final Decision ===
        total_time_ms = (time.time() - start_time) * 1000

        if not keyword_safe:
            final_decision = {
                "allowed": False,
                "blocked_by": "keyword",
                "blocked_reason": f"keyword:{keyword_reason}",
                "total_time_ms": round(total_time_ms, 2)
            }
            result = (False, f"keyword:{keyword_reason}")
        elif not ai_safe:
            final_decision = {
                "allowed": False,
                "blocked_by": "ai",
                "blocked_reason": f"ai:{ai_reason}",
                "total_time_ms": round(total_time_ms, 2)
            }
            result = (False, f"ai:{ai_reason}")
        else:
            final_decision = {
                "allowed": True,
                "blocked_by": None,
                "blocked_reason": None,
                "total_time_ms": round(total_time_ms, 2)
            }
            result = (True, "")

        # === Audit Logging ===
        try:
            from .audit_logger import get_audit_logger
            audit_logger = get_audit_logger()
            audit_logger.log_moderation_check(
                prompt=prompt,
                layer1_result=layer1_result,
                layer2_result=layer2_result,
                final_decision=final_decision,
                context=context
            )
        except Exception as e:
            # Don't fail on logging errors
            print(f"[ContentFilter] Audit logging failed: {e}")

        return result

    def _check_keywords(self, prompt: str) -> Tuple[bool, str]:
        """Layer 1: Fast keyword blacklist checking with word boundary detection."""
        # Normalize prompt for checking
        normalized = prompt.lower()

        # Remove spaces and special chars for evasion detection
        # e.g., "n s f w" or "n-s-f-w" should still match "nsfw"
        compact = re.sub(r'[\s\-_]+', '', normalized)

        # Check each banned keyword
        for keyword in self.banned_keywords:
            keyword_lower = keyword.lower()

            # For multi-word phrases, use substring match
            if ' ' in keyword_lower:
                if keyword_lower in normalized:
                    return False, keyword

            # For single words, use word boundary match (avoid "bra" in "embracing")
            else:
                # Word boundary pattern: \b{keyword}\b
                pattern = r'\b' + re.escape(keyword_lower) + r'\b'
                if re.search(pattern, normalized):
                    return False, keyword

            # Evasion detection for compact form (spaces removed)
            keyword_compact = re.sub(r'[\s\-_]+', '', keyword_lower)
            if keyword_compact in compact and len(keyword_compact) > 3:  # Avoid short false positives
                return False, keyword

        return True, ""

    def get_blocked_message(self, language: str = "en", reason: str = "") -> str:
        """Get localized blocked message based on reason."""
        # If it's an AI-detected issue, use AI moderator's messages
        if reason.startswith("ai:") and self.ai_moderator:
            ai_reason = reason.split(":", 1)[1]
            return self.ai_moderator.get_blocked_message(ai_reason, language)

        # Otherwise use generic messages
        messages = {
            "en": "⚠️ Your prompt contains inappropriate content and cannot be processed.",
            "zh": "⚠️ 您的提示词包含不当内容，无法处理。"
        }
        return messages.get(language, messages["en"])


# Global singleton instance
_content_filter = None


def get_content_filter() -> ContentFilter:
    """Get or create the global content filter instance."""
    global _content_filter
    if _content_filter is None:
        _content_filter = ContentFilter()
    return _content_filter
