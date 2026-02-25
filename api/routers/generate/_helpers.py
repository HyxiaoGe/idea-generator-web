"""Shared helpers for the generate router package."""

from core.config import get_settings
from core.exceptions import ValidationError
from services import (
    ImageGenerator,
)
from services.request_builder import build_provider_request  # noqa: F401


def create_generator(api_key: str | None = None) -> ImageGenerator:
    """Create image generator with appropriate API key (legacy, for backward compatibility)."""
    settings = get_settings()
    key = api_key or settings.get_google_api_key()

    if not key:
        raise ValidationError(message="No API key configured")

    return ImageGenerator(api_key=key)
