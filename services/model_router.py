"""
Model Router for quality preset routing and alias resolution.

Provides:
- QualityPreset enum (premium/balanced/fast)
- resolve_alias(): Find canonical model ID from old aliases
- select_model_by_preset(): Pick best model for a quality tier
- get_all_models(): List all image models across providers
"""

import logging
from enum import StrEnum

from .providers.base import MediaType, ProviderModel
from .providers.registry import get_provider_registry

logger = logging.getLogger(__name__)


class QualityPreset(StrEnum):
    """Quality presets for automatic model selection."""

    PREMIUM = "premium"
    BALANCED = "balanced"
    FAST = "fast"


# Display info for each preset
PRESET_INFO = {
    QualityPreset.PREMIUM: {
        "name_en": "Premium",
        "name_zh": "高质量",
        "description": "Best quality, slower generation",
        "icon": "crown",
    },
    QualityPreset.BALANCED: {
        "name_en": "Balanced",
        "name_zh": "均衡",
        "description": "Good quality and speed balance",
        "icon": "scale",
    },
    QualityPreset.FAST: {
        "name_en": "Fast",
        "name_zh": "快速",
        "description": "Fastest generation, good quality",
        "icon": "zap",
    },
}


def resolve_alias(model_id: str) -> tuple[str | None, str]:
    """
    Search all providers for a model by ID or alias.

    Args:
        model_id: Model ID or legacy alias

    Returns:
        Tuple of (provider_name, canonical_model_id).
        If not found, returns (None, original_model_id).
    """
    registry = get_provider_registry()

    for entry in registry.get_available_image_providers():
        # Check direct model ID match
        for model in entry.models:
            if model.id == model_id:
                return entry.name, model.id

        # Check aliases
        for model in entry.models:
            if model_id in model.aliases:
                return entry.name, model.id

    return None, model_id


def select_model_by_preset(
    preset: QualityPreset,
    preferred_provider: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Select the best available model for a quality preset.

    Filters models by tier == preset, sorts by arena_score desc,
    returns the first available model.

    Args:
        preset: Quality preset tier
        preferred_provider: Optional provider to prefer

    Returns:
        Tuple of (provider_name, model_id), or (None, None) if no match.
    """
    registry = get_provider_registry()
    providers = registry.get_available_image_providers()

    candidates: list[tuple[str, ProviderModel]] = []

    for entry in providers:
        if preferred_provider and entry.name != preferred_provider:
            continue
        for model in entry.models:
            if model.hidden:
                continue
            if model.media_type != MediaType.IMAGE:
                continue
            if model.tier == preset.value:
                candidates.append((entry.name, model))

    if not candidates:
        # If preferred_provider was set and no match, try all providers
        if preferred_provider:
            return select_model_by_preset(preset, preferred_provider=None)
        # Fallback to balanced if no models match requested tier
        if preset != QualityPreset.BALANCED:
            return select_model_by_preset(QualityPreset.BALANCED)
        return None, None

    # Sort by arena_score desc (None scores last)
    candidates.sort(key=lambda x: x[1].arena_score or 0, reverse=True)

    provider_name, model = candidates[0]
    return provider_name, model.id


def get_all_models(include_hidden: bool = False) -> list[dict]:
    """
    List all image models across providers.

    Args:
        include_hidden: Whether to include hidden models

    Returns:
        List of model info dicts, sorted by arena_score desc.
    """
    registry = get_provider_registry()
    providers = registry.get_available_image_providers()

    models = []
    for entry in providers:
        for model in entry.models:
            if model.media_type != MediaType.IMAGE:
                continue
            if model.hidden and not include_hidden:
                continue
            models.append(
                {
                    "id": model.id,
                    "name": model.name,
                    "provider": entry.name,
                    "provider_display_name": entry.display_name,
                    "tier": model.tier,
                    "arena_rank": model.arena_rank,
                    "arena_score": model.arena_score,
                    "max_resolution": model.max_resolution,
                    "pricing": model.pricing_per_unit,
                    "quality_score": model.quality_score,
                    "latency_estimate": model.latency_estimate,
                    "strengths": model.strengths,
                    "aliases": model.aliases,
                    "is_default": model.is_default,
                }
            )

    # Sort by arena_score desc (None scores last)
    models.sort(key=lambda m: m["arena_score"] or 0, reverse=True)
    return models
