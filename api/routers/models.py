"""
Models endpoint for frontend model/preset discovery.

Endpoints:
- GET /api/models - List all available models and quality presets
"""

from fastapi import APIRouter

from services.model_router import PRESET_INFO, QualityPreset, get_all_models

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_models():
    """
    List all available image models and quality presets.

    Returns:
    - presets: Available quality presets with display info
    - models: All visible models across providers, sorted by arena_score
    - default_preset: The default quality preset
    """
    presets = [
        {
            "id": preset.value,
            **info,
        }
        for preset, info in PRESET_INFO.items()
    ]

    return {
        "presets": presets,
        "models": get_all_models(include_hidden=False),
        "default_preset": QualityPreset.BALANCED.value,
    }
