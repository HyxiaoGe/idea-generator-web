"""
AI-powered content moderation service using Gemini Flash.
Provides intelligent safety classification beyond keyword matching.
"""
import os
import hashlib
from typing import Tuple, Optional, Dict
from datetime import datetime, timedelta

# Try to import streamlit for secrets
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

# Try to import Google GenAI
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


def get_config_value(key: str, default: str = "") -> str:
    """Get configuration value from multiple sources."""
    if HAS_STREAMLIT:
        try:
            if hasattr(st, 'secrets') and key in st.secrets:
                return str(st.secrets[key])
        except Exception:
            pass
    return os.getenv(key, default)


class AIContentModerator:
    """
    AI-powered content moderator using Gemini Flash.
    Detects NSFW, violence, and other inappropriate content with context understanding.
    """

    # Safety categories to check (aligned with Google's Imagen/Gemini policy)
    SAFETY_PROMPT = """You are a content safety classifier for an AI image generation service.
Follow Google's content policy standards.

Analyze the following prompt and classify it as SAFE or UNSAFE.

UNSAFE - MUST BLOCK:
1. Explicit sexual acts or sexual intercourse (e.g., "having sex", "sexual penetration", "oral sex")
2. Sexual body parts shown explicitly (e.g., "naked showing genitals", "erect penis", "vagina closeup")
3. Pornographic or erotic content (e.g., "porn star", "XXX scene", "erotic photography")
4. Sexual violence or non-consensual acts (e.g., "rape", "sexual assault", "forced")
5. Minors in ANY sexual or suggestive context
6. Graphic violence or gore (e.g., "decapitation", "dismembered body", "blood everywhere")
7. Illegal drugs production/use (e.g., "snorting cocaine", "injecting heroin")
8. Terrorism or bomb-making instructions

SAFE - ALLOW (even if intimate):
✓ Romantic affection: kissing, hugging, embracing, cuddling, holding hands
✓ Emotional intimacy: couples in love, passionate embrace, tender moment
✓ Fashion/swimwear: bikini, lingerie in fashion/commercial context
✓ Artistic nudity: classical sculptures, renaissance paintings, fine art photography
✓ Medical/educational: anatomy diagrams, medical procedures
✓ Everyday romance: wedding scenes, proposal, date night, anniversary

Context matters - Examples:
- "Couple embracing passionately" → SAFE (romantic embrace, fully clothed)
- "Couple kissing tenderly" → SAFE (romantic kiss, appropriate)
- "Couple making love" → UNSAFE ("making love" is euphemism for sex)
- "Couple in bed making love" → UNSAFE (explicit sexual activity)
- "Intimate bedroom scene" → UNSAFE (sexual context implied)
- "Erotic photography" → UNSAFE (erotic content)
- "Woman in bikini at beach" → SAFE (swimwear, beach context)
- "Woman naked showing body" → UNSAFE (explicit nudity)
- "Nude David sculpture" → SAFE (classical art)
- "Nude woman posing" → UNSAFE (erotic photography)

Key phrases that indicate UNSAFE:
- "making love", "intimate bedroom", "erotic", "provocative pose"
- "bedroom scene", "passionate bedroom", "sensual photography"

Respond with ONLY ONE WORD:
- "SAFE" if the prompt is acceptable
- "UNSAFE" if the prompt violates content policy

Prompt to analyze: "{prompt}"

Classification:"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize AI content moderator."""
        self.api_key = api_key or get_config_value("GOOGLE_API_KEY", "")
        self.enabled = get_config_value("AI_MODERATION_ENABLED", "true").lower() in ["true", "1", "yes"]
        self.model = None
        self._cache: Dict[str, Tuple[bool, str, datetime]] = {}
        self._cache_ttl = timedelta(hours=24)  # Cache results for 24 hours

        if self.enabled and HAS_GENAI and self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                # Use Flash for speed and cost efficiency
                self.model = genai.GenerativeModel("gemini-2.0-flash-exp")
            except Exception as e:
                print(f"Failed to initialize AI moderator: {e}")
                self.enabled = False

    def _get_cache_key(self, prompt: str) -> str:
        """Generate cache key from prompt."""
        return hashlib.md5(prompt.lower().encode()).hexdigest()

    def _get_cached_result(self, prompt: str) -> Optional[Tuple[bool, str]]:
        """Get cached moderation result if available and not expired."""
        cache_key = self._get_cache_key(prompt)
        if cache_key in self._cache:
            is_safe, reason, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < self._cache_ttl:
                return is_safe, reason
            else:
                # Expired, remove from cache
                del self._cache[cache_key]
        return None

    def _cache_result(self, prompt: str, is_safe: bool, reason: str):
        """Cache moderation result."""
        cache_key = self._get_cache_key(prompt)
        self._cache[cache_key] = (is_safe, reason, datetime.now())

        # Limit cache size to prevent memory issues
        if len(self._cache) > 1000:
            # Remove oldest entries
            sorted_cache = sorted(self._cache.items(), key=lambda x: x[1][2])
            for key, _ in sorted_cache[:200]:  # Remove oldest 200
                del self._cache[key]

    def check_safety(self, prompt: str) -> Tuple[bool, str]:
        """
        Check if a prompt is safe using AI classification.

        Args:
            prompt: The user's prompt text

        Returns:
            Tuple of (is_safe, reason)
            - is_safe: True if safe, False if unsafe
            - reason: "safe" or specific category like "nsfw", "violence", etc.
        """
        if not self.enabled or not self.model:
            # AI moderation disabled, default to safe
            return True, "ai_moderation_disabled"

        # Check cache first
        cached = self._get_cached_result(prompt)
        if cached is not None:
            return cached

        try:
            # Generate safety classification prompt
            analysis_prompt = self.SAFETY_PROMPT.format(prompt=prompt)

            # Call Gemini Flash with strict safety settings
            response = self.model.generate_content(
                analysis_prompt,
                generation_config={
                    "temperature": 0,  # Deterministic results
                    "max_output_tokens": 10,  # Just need "SAFE" or "UNSAFE"
                },
                safety_settings={
                    "HARASSMENT": "BLOCK_NONE",  # We're analyzing safety, not generating content
                    "HATE_SPEECH": "BLOCK_NONE",
                    "SEXUALLY_EXPLICIT": "BLOCK_NONE",
                    "DANGEROUS_CONTENT": "BLOCK_NONE",
                }
            )

            # Parse response
            result = response.text.strip().upper()

            if "UNSAFE" in result:
                # Determine category from prompt content for better error messages
                reason = self._categorize_unsafe_content(prompt)
                self._cache_result(prompt, False, reason)
                return False, reason
            else:
                # Safe
                self._cache_result(prompt, True, "safe")
                return True, "safe"

        except Exception as e:
            # On error, fail open (allow) to not block legitimate users
            # but log the error for monitoring
            print(f"AI moderation error: {e}")
            return True, f"ai_error: {str(e)[:50]}"

    def _categorize_unsafe_content(self, prompt: str) -> str:
        """Categorize unsafe content for better error messages."""
        prompt_lower = prompt.lower()

        # Simple heuristics for category
        nsfw_indicators = ["sex", "nude", "naked", "breast", "vagina", "penis", "erotic"]
        violence_indicators = ["kill", "murder", "blood", "gore", "weapon", "shoot"]
        minor_indicators = ["child", "kid", "teen", "young", "minor", "loli", "shota"]
        drug_indicators = ["drug", "cocaine", "heroin", "meth", "marijuana"]

        if any(word in prompt_lower for word in nsfw_indicators):
            return "nsfw_content"
        elif any(word in prompt_lower for word in violence_indicators):
            return "violent_content"
        elif any(word in prompt_lower for word in minor_indicators):
            return "minor_safety"
        elif any(word in prompt_lower for word in drug_indicators):
            return "illegal_content"
        else:
            return "policy_violation"

    def get_blocked_message(self, reason: str, language: str = "en") -> str:
        """Get localized blocked message based on reason."""
        messages = {
            "en": {
                "nsfw_content": "🔞 NSFW content detected. Please use appropriate prompts.",
                "violent_content": "⚠️ Violent content detected. Please avoid graphic descriptions.",
                "minor_safety": "🚫 Content involving minors is not allowed.",
                "illegal_content": "⚠️ Illegal content detected. Request blocked.",
                "policy_violation": "⚠️ Content violates usage policy. Please revise your prompt.",
                "default": "⚠️ Your prompt was flagged by our AI safety system.",
            },
            "zh": {
                "nsfw_content": "🔞 检测到NSFW内容，请使用合适的提示词。",
                "violent_content": "⚠️ 检测到暴力内容，请避免过度描述。",
                "minor_safety": "🚫 不允许涉及未成年人的内容。",
                "illegal_content": "⚠️ 检测到违法内容，请求已被拦截。",
                "policy_violation": "⚠️ 内容违反使用政策，请修改提示词。",
                "default": "⚠️ 您的提示词被AI安全系统标记。",
            }
        }

        lang_messages = messages.get(language, messages["en"])
        return lang_messages.get(reason, lang_messages["default"])


# Global singleton instance
_ai_moderator = None


def get_ai_moderator(api_key: Optional[str] = None) -> AIContentModerator:
    """Get or create the global AI content moderator instance."""
    global _ai_moderator
    if _ai_moderator is None:
        _ai_moderator = AIContentModerator(api_key=api_key)
    return _ai_moderator
