"""
Provider Registry for managing and discovering AI providers.

This module provides a central registry for all AI providers,
enabling dynamic provider discovery, selection, and management.
"""

import logging
from dataclasses import dataclass, field

from .base import (
    ImageProvider,
    MediaType,
    ProviderCapability,
    ProviderConfig,
    ProviderModel,
    VideoProvider,
)

logger = logging.getLogger(__name__)


@dataclass
class ProviderEntry:
    """Registry entry for a provider."""

    name: str
    display_name: str
    provider_class: type[ImageProvider | VideoProvider]
    media_type: MediaType
    priority: int = 100  # Lower = higher priority
    is_enabled: bool = True
    config: ProviderConfig = field(default_factory=ProviderConfig)
    _instance: ImageProvider | VideoProvider | None = field(default=None, repr=False)


class ProviderRegistry:
    """
    Central registry for all AI providers.

    Supports:
    - Dynamic provider registration
    - Provider discovery by capability
    - Singleton instance management
    - Priority-based provider selection
    """

    def __init__(self):
        self._image_providers: dict[str, ProviderEntry] = {}
        self._video_providers: dict[str, ProviderEntry] = {}
        self._initialized = False

    def register_image_provider(
        self,
        name: str,
        display_name: str,
        provider_class: type[ImageProvider],
        priority: int = 100,
        enabled: bool = True,
        config: ProviderConfig | None = None,
    ) -> None:
        """
        Register an image generation provider.

        Args:
            name: Unique identifier (e.g., 'google', 'openai')
            display_name: Human-readable name
            provider_class: The provider class to instantiate
            priority: Lower = higher priority for selection
            enabled: Whether the provider is enabled
            config: Optional provider configuration
        """
        entry = ProviderEntry(
            name=name,
            display_name=display_name,
            provider_class=provider_class,
            media_type=MediaType.IMAGE,
            priority=priority,
            is_enabled=enabled,
            config=config or ProviderConfig(),
        )
        self._image_providers[name] = entry
        logger.info(f"Registered image provider: {name} (priority={priority})")

    def register_video_provider(
        self,
        name: str,
        display_name: str,
        provider_class: type[VideoProvider],
        priority: int = 100,
        enabled: bool = True,
        config: ProviderConfig | None = None,
    ) -> None:
        """Register a video generation provider."""
        entry = ProviderEntry(
            name=name,
            display_name=display_name,
            provider_class=provider_class,
            media_type=MediaType.VIDEO,
            priority=priority,
            is_enabled=enabled,
            config=config or ProviderConfig(),
        )
        self._video_providers[name] = entry
        logger.info(f"Registered video provider: {name} (priority={priority})")

    def get_image_provider(self, name: str) -> ImageProvider | None:
        """
        Get an image provider instance by name.

        Returns a cached instance if available, otherwise creates one.
        """
        entry = self._image_providers.get(name)
        if not entry:
            logger.warning(f"Image provider not found: {name}")
            return None

        if not entry.is_enabled:
            logger.warning(f"Image provider is disabled: {name}")
            return None

        # Lazy instantiation with caching
        if entry._instance is None:
            try:
                entry._instance = entry.provider_class(config=entry.config)
                logger.debug(f"Instantiated image provider: {name}")
            except Exception as e:
                logger.error(f"Failed to instantiate image provider {name}: {e}")
                return None

        return entry._instance

    def get_video_provider(self, name: str) -> VideoProvider | None:
        """Get a video provider instance by name."""
        entry = self._video_providers.get(name)
        if not entry:
            logger.warning(f"Video provider not found: {name}")
            return None

        if not entry.is_enabled:
            logger.warning(f"Video provider is disabled: {name}")
            return None

        if entry._instance is None:
            try:
                entry._instance = entry.provider_class(config=entry.config)
                logger.debug(f"Instantiated video provider: {name}")
            except Exception as e:
                logger.error(f"Failed to instantiate video provider {name}: {e}")
                return None

        return entry._instance

    def get_available_image_providers(self) -> list[ImageProvider]:
        """Get all available (enabled and instantiable) image providers."""
        providers = []
        for name, entry in sorted(self._image_providers.items(), key=lambda x: x[1].priority):
            if entry.is_enabled:
                provider = self.get_image_provider(name)
                if provider and provider.is_available:
                    providers.append(provider)
        return providers

    def get_available_video_providers(self) -> list[VideoProvider]:
        """Get all available video providers."""
        providers = []
        for name, entry in sorted(self._video_providers.items(), key=lambda x: x[1].priority):
            if entry.is_enabled:
                provider = self.get_video_provider(name)
                if provider and provider.is_available:
                    providers.append(provider)
        return providers

    def get_providers_by_capability(
        self,
        capability: ProviderCapability,
        media_type: MediaType | None = None,
    ) -> list[ImageProvider | VideoProvider]:
        """
        Get all providers that support a specific capability.

        Args:
            capability: The capability to filter by
            media_type: Optional filter by media type

        Returns:
            List of providers sorted by priority
        """
        result = []

        # Check image providers
        if media_type is None or media_type == MediaType.IMAGE:
            for provider in self.get_available_image_providers():
                for model in provider.models:
                    if model.supports_capability(capability):
                        result.append(provider)
                        break

        # Check video providers
        if media_type is None or media_type == MediaType.VIDEO:
            for provider in self.get_available_video_providers():
                for model in provider.models:
                    if model.supports_capability(capability):
                        result.append(provider)
                        break

        return result

    def get_models_by_capability(
        self,
        capability: ProviderCapability,
    ) -> list[ProviderModel]:
        """Get all models across all providers that support a capability."""
        models = []

        for provider in self.get_available_image_providers():
            for model in provider.models:
                if model.supports_capability(capability):
                    models.append(model)

        for provider in self.get_available_video_providers():
            for model in provider.models:
                if model.supports_capability(capability):
                    models.append(model)

        # Sort by quality score (highest first)
        return sorted(models, key=lambda m: m.quality_score, reverse=True)

    def get_all_image_provider_names(self) -> list[str]:
        """Get names of all registered image providers."""
        return list(self._image_providers.keys())

    def get_all_video_provider_names(self) -> list[str]:
        """Get names of all registered video providers."""
        return list(self._video_providers.keys())

    def is_provider_registered(self, name: str) -> bool:
        """Check if a provider is registered (image or video)."""
        return name in self._image_providers or name in self._video_providers

    def enable_provider(self, name: str) -> bool:
        """Enable a provider by name."""
        if name in self._image_providers:
            self._image_providers[name].is_enabled = True
            return True
        if name in self._video_providers:
            self._video_providers[name].is_enabled = True
            return True
        return False

    def disable_provider(self, name: str) -> bool:
        """Disable a provider by name."""
        if name in self._image_providers:
            self._image_providers[name].is_enabled = False
            return True
        if name in self._video_providers:
            self._video_providers[name].is_enabled = False
            return True
        return False

    def update_provider_config(
        self,
        name: str,
        config: ProviderConfig,
    ) -> bool:
        """
        Update configuration for a provider.

        This will invalidate the cached instance, forcing re-instantiation.
        """
        entry = self._image_providers.get(name) or self._video_providers.get(name)
        if entry:
            entry.config = config
            entry._instance = None  # Force re-instantiation
            return True
        return False

    def get_provider_info(self, name: str) -> dict | None:
        """Get information about a registered provider."""
        entry = self._image_providers.get(name) or self._video_providers.get(name)
        if not entry:
            return None

        provider = None
        if name in self._image_providers:
            provider = self.get_image_provider(name)
        else:
            provider = self.get_video_provider(name)

        return {
            "name": entry.name,
            "display_name": entry.display_name,
            "media_type": entry.media_type.value,
            "priority": entry.priority,
            "is_enabled": entry.is_enabled,
            "is_available": provider.is_available if provider else False,
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "capabilities": [c.value for c in m.capabilities],
                    "max_resolution": m.max_resolution,
                    "pricing_per_unit": m.pricing_per_unit,
                    "quality_score": m.quality_score,
                }
                for m in (provider.models if provider else [])
            ],
        }

    def list_all_providers(self) -> dict:
        """Get a summary of all registered providers."""
        return {
            "image_providers": [self.get_provider_info(name) for name in self._image_providers],
            "video_providers": [self.get_provider_info(name) for name in self._video_providers],
        }

    def clear(self) -> None:
        """Clear all registered providers (mainly for testing)."""
        self._image_providers.clear()
        self._video_providers.clear()
        self._initialized = False


# Global singleton instance
_registry: ProviderRegistry | None = None


def get_provider_registry() -> ProviderRegistry:
    """
    Get the global provider registry singleton.

    This ensures a single registry instance across the application.
    """
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def reset_provider_registry() -> None:
    """Reset the global registry (mainly for testing)."""
    global _registry
    if _registry:
        _registry.clear()
    _registry = None
