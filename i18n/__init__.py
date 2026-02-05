"""
Internationalization (i18n) module for Nano Banana Lab.
"""

import json
import os
from typing import Any

# Supported languages
LANGUAGES = {
    "en": "English",
    "zh": "中文",
}

DEFAULT_LANGUAGE = "en"

# Language data cache
_translations: dict[str, dict[str, Any]] = {}


def _load_language_from_file(lang_code: str) -> dict[str, Any]:
    """Load language file from disk."""
    lang_file = os.path.join(os.path.dirname(__file__), f"{lang_code}.json")
    if os.path.exists(lang_file):
        with open(lang_file, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_language(lang_code: str) -> dict[str, Any]:
    """Load language file with caching."""
    if lang_code in _translations:
        return _translations[lang_code]

    data = _load_language_from_file(lang_code)
    if not data and lang_code != DEFAULT_LANGUAGE:
        # Fallback to English
        data = _load_language(DEFAULT_LANGUAGE)

    _translations[lang_code] = data
    return data


def get_text(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """
    Get translated text by key.

    Args:
        key: Dot-separated key path (e.g., "sidebar.title")
        lang: Language code (e.g., "en", "zh")
        **kwargs: Format arguments for the string

    Returns:
        Translated text or the key if not found
    """
    translations = _load_language(lang)

    # Navigate nested keys
    keys = key.split(".")
    value = translations
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return key  # Return key if not found

    if isinstance(value, str):
        try:
            return value.format(**kwargs) if kwargs else value
        except KeyError:
            return value

    return key


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """Shorthand for get_text."""
    return get_text(key, lang, **kwargs)


class Translator:
    """Translator helper class for a specific language."""

    def __init__(self, lang: str = DEFAULT_LANGUAGE):
        self.lang = lang

    def __call__(self, key: str, **kwargs) -> str:
        return get_text(key, self.lang, **kwargs)

    def set_language(self, lang: str):
        self.lang = lang
