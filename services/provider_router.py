"""
Provider Router for intelligent provider selection and failover.

This module provides smart routing capabilities to select the best
AI provider based on various strategies (cost, quality, speed, priority).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.config import get_settings

from .providers.base import (
    CircuitBreakerManager,
    CostTracker,
    GenerationRequest,
    GenerationResult,
    MediaType,
    ProviderConfig,
    ProviderRegion,
    is_retryable_error,
)
from .providers.registry import ProviderRegistry, get_provider_registry

logger = logging.getLogger(__name__)


class RoutingStrategy(StrEnum):
    """Strategy for selecting providers."""

    PRIORITY = "priority"  # Use configured priority order
    COST = "cost"  # Minimize cost
    QUALITY = "quality"  # Maximize quality
    SPEED = "speed"  # Minimize latency
    ROUND_ROBIN = "round_robin"  # Rotate between providers
    ADAPTIVE = "adaptive"  # ML-inspired routing based on historical performance
    REGION = "region"  # Prefer providers in specified region


@dataclass
class RoutingDecision:
    """Result of routing decision."""

    provider_name: str
    model_id: str
    estimated_cost: float = 0.0
    estimated_latency: float = 0.0
    fallback_providers: list[str] = field(default_factory=list)
    strategy_used: str = "priority"
    region: ProviderRegion | None = None


@dataclass
class ProviderHealth:
    """Health status of a provider."""

    name: str
    is_healthy: bool
    last_check: float = 0.0
    latency_ms: int = 0
    error_count: int = 0
    success_count: int = 0


class AdaptiveRoutingStrategy:
    """
    ML-inspired routing based on historical performance.

    Tracks success rates, latencies, and costs to score providers
    and select the best one dynamically.
    """

    def __init__(self):
        self.success_rates: dict[str, float] = {}
        self.latencies: dict[str, list[float]] = {}
        self.costs: dict[str, float] = {}
        self._alpha = 0.1  # Exponential moving average factor

    def update(
        self,
        provider: str,
        success: bool,
        latency: float,
        cost: float,
    ) -> None:
        """Update metrics for a provider after a request."""
        # Update success rate (exponential moving average)
        old_rate = self.success_rates.get(provider, 1.0)
        self.success_rates[provider] = (
            self._alpha * (1.0 if success else 0.0) + (1 - self._alpha) * old_rate
        )

        # Update latency history
        if provider not in self.latencies:
            self.latencies[provider] = []
        self.latencies[provider].append(latency)
        # Keep only last 100 latencies
        if len(self.latencies[provider]) > 100:
            self.latencies[provider] = self.latencies[provider][-100:]

        # Update cost
        self.costs[provider] = cost

    def score(
        self,
        provider: str,
        weights: dict[str, float] | None = None,
    ) -> float:
        """
        Calculate provider score (higher = better).

        Args:
            provider: Provider name
            weights: Optional weight overrides

        Returns:
            Score between 0 and 1
        """
        weights = weights or {"success": 0.5, "speed": 0.3, "cost": 0.2}

        # Success score (0-1)
        success_score = self.success_rates.get(provider, 0.8)

        # Speed score (0-1, normalized)
        latencies = self.latencies.get(provider, [10.0])
        avg_latency = sum(latencies) / len(latencies)
        speed_score = 1.0 / (1.0 + avg_latency / 10.0)  # Normalize around 10s

        # Cost score (0-1, normalized)
        cost = self.costs.get(provider, 0.05)
        cost_score = 1.0 / (1.0 + cost * 10)  # Normalize around $0.10

        return (
            weights["success"] * success_score
            + weights["speed"] * speed_score
            + weights["cost"] * cost_score
        )

    def get_best_provider(
        self,
        providers: list[str],
        weights: dict[str, float] | None = None,
    ) -> str | None:
        """Get the best scoring provider from a list."""
        if not providers:
            return None

        scores = [(p, self.score(p, weights)) for p in providers]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[0][0]

    def get_stats(self) -> dict[str, Any]:
        """Get current routing statistics."""
        return {
            "success_rates": dict(self.success_rates),
            "avg_latencies": {p: sum(l) / len(l) if l else 0 for p, l in self.latencies.items()},
            "last_costs": dict(self.costs),
        }


class ProviderRouter:
    """
    Intelligent router for selecting AI providers.

    Features:
    - Multiple routing strategies (priority, cost, quality, speed, adaptive, region)
    - Automatic failover on provider failure
    - Circuit breaker integration for fault tolerance
    - Health checking with caching
    - Cost tracking
    - Adaptive routing based on historical performance
    """

    # Health cache TTL in seconds
    HEALTH_CACHE_TTL = 60

    def __init__(self, registry: ProviderRegistry | None = None):
        """
        Initialize the router.

        Args:
            registry: Optional ProviderRegistry instance
        """
        self._settings = get_settings()
        self._registry = registry or get_provider_registry()
        self._health_cache: dict[str, ProviderHealth] = {}
        self._round_robin_index = 0
        self._initialized = False
        # New components
        self._adaptive = AdaptiveRoutingStrategy()
        self._cost_tracker = CostTracker()

    def initialize(self) -> None:
        """Initialize the router and register providers."""
        if self._initialized:
            return

        self._register_providers()
        self._initialized = True
        logger.info("ProviderRouter initialized")

    def _register_providers(self) -> None:
        """Register all enabled providers from config."""
        settings = self._settings

        # Register Google provider if enabled
        if settings.provider_google_enabled and settings.get_google_api_key():
            from .providers.google import GoogleProvider

            self._registry.register_image_provider(
                name="google",
                display_name="Google Gemini",
                provider_class=GoogleProvider,
                priority=settings.provider_google_priority,
                enabled=True,
                config=ProviderConfig(
                    enabled=True,
                    api_key=settings.get_google_api_key(),
                    priority=settings.provider_google_priority,
                ),
            )
            logger.info("Registered Google provider")

        # Register OpenAI provider if enabled (supports third-party proxies like OpenRouter)
        if settings.provider_openai_enabled and settings.provider_openai_api_key:
            from .providers.openai import OpenAIProvider

            # Build extra headers for third-party proxies
            extra_headers = {}
            if settings.provider_openai_referer:
                extra_headers["HTTP-Referer"] = settings.provider_openai_referer
                extra_headers["X-Title"] = settings.app_name  # OpenRouter recommends this

            self._registry.register_image_provider(
                name="openai",
                display_name="OpenAI",
                provider_class=OpenAIProvider,
                priority=settings.provider_openai_priority,
                enabled=True,
                config=ProviderConfig(
                    enabled=True,
                    api_key=settings.provider_openai_api_key,
                    api_base_url=settings.provider_openai_base_url,
                    priority=settings.provider_openai_priority,
                    extra={"headers": extra_headers} if extra_headers else {},
                ),
            )
            logger.info(
                f"Registered OpenAI provider (base_url: {settings.provider_openai_base_url or 'official'})"
            )

        # Register FLUX provider (Black Forest Labs) if enabled
        if settings.provider_bfl_enabled and settings.provider_bfl_api_key:
            from .providers.flux import FluxProvider

            self._registry.register_image_provider(
                name="bfl",
                display_name="FLUX (Black Forest Labs)",
                provider_class=FluxProvider,
                priority=settings.provider_bfl_priority,
                enabled=True,
                config=ProviderConfig(
                    enabled=True,
                    api_key=settings.provider_bfl_api_key,
                    priority=settings.provider_bfl_priority,
                ),
            )
            logger.info("Registered FLUX (BFL) provider")

        # ============ Chinese Image Providers ============

        # Register Alibaba (通义万相) provider if enabled
        if settings.provider_alibaba_enabled and settings.provider_alibaba_api_key:
            from .providers.alibaba import AlibabaProvider

            self._registry.register_image_provider(
                name="alibaba",
                display_name="通义万相 (Alibaba)",
                provider_class=AlibabaProvider,
                priority=settings.provider_alibaba_priority,
                enabled=True,
                config=ProviderConfig(
                    enabled=True,
                    api_key=settings.provider_alibaba_api_key,
                    priority=settings.provider_alibaba_priority,
                ),
            )
            logger.info("Registered Alibaba (通义万相) provider")

        # Register Zhipu AI (智谱) provider if enabled
        if settings.provider_zhipu_enabled and settings.provider_zhipu_api_key:
            from .providers.zhipu import ZhipuProvider

            self._registry.register_image_provider(
                name="zhipu",
                display_name="智谱 AI (CogView)",
                provider_class=ZhipuProvider,
                priority=settings.provider_zhipu_priority,
                enabled=True,
                config=ProviderConfig(
                    enabled=True,
                    api_key=settings.provider_zhipu_api_key,
                    priority=settings.provider_zhipu_priority,
                ),
            )
            logger.info("Registered Zhipu AI (智谱) provider")

        # Register ByteDance (即梦) provider if enabled
        if settings.provider_bytedance_enabled and settings.provider_bytedance_access_key:
            from .providers.bytedance import ByteDanceProvider

            self._registry.register_image_provider(
                name="bytedance",
                display_name="即梦 (ByteDance)",
                provider_class=ByteDanceProvider,
                priority=settings.provider_bytedance_priority,
                enabled=True,
                config=ProviderConfig(
                    enabled=True,
                    api_key=settings.provider_bytedance_access_key,
                    priority=settings.provider_bytedance_priority,
                    extra={"secret_key": settings.provider_bytedance_secret_key},
                ),
            )
            logger.info("Registered ByteDance (即梦) provider")

        # Register MiniMax provider if enabled
        if settings.provider_minimax_enabled and settings.provider_minimax_api_key:
            from .providers.minimax import MiniMaxProvider

            self._registry.register_image_provider(
                name="minimax",
                display_name="MiniMax",
                provider_class=MiniMaxProvider,
                priority=settings.provider_minimax_priority,
                enabled=True,
                config=ProviderConfig(
                    enabled=True,
                    api_key=settings.provider_minimax_api_key,
                    priority=settings.provider_minimax_priority,
                    extra={"group_id": settings.provider_minimax_group_id}
                    if settings.provider_minimax_group_id
                    else {},
                ),
            )
            logger.info("Registered MiniMax provider")

    async def route(
        self,
        request: GenerationRequest,
        strategy: str | None = None,
        media_type: MediaType = MediaType.IMAGE,
    ) -> RoutingDecision:
        """
        Select the best provider for a request.

        Args:
            request: The generation request
            strategy: Routing strategy to use (defaults to config)
            media_type: Type of media to generate

        Returns:
            RoutingDecision with selected provider and model
        """
        self.initialize()

        strategy = strategy or self._settings.default_routing_strategy
        strategy_enum = RoutingStrategy(strategy) if strategy else RoutingStrategy.PRIORITY

        # If user specified a provider, use it
        if request.preferred_provider:
            provider = self._get_provider(request.preferred_provider, media_type)
            if provider and provider.is_available:
                model = (
                    provider.get_model_by_id(request.preferred_model)
                    if request.preferred_model and hasattr(provider, "get_model_by_id")
                    else provider.get_default_model()
                )
                return RoutingDecision(
                    provider_name=provider.name,
                    model_id=model.id if model else "",
                    estimated_cost=model.pricing_per_unit if model else 0,
                    estimated_latency=model.latency_estimate if model else 10,
                    fallback_providers=self._get_fallback_list(provider.name, media_type),
                    strategy_used="user_specified",
                )

        # Get available providers
        if media_type == MediaType.IMAGE:
            providers = self._registry.get_available_image_providers()
        else:
            providers = self._registry.get_available_video_providers()

        if not providers:
            raise ValueError(f"No available providers for {media_type.value} generation")

        # Filter by circuit breaker state
        available_providers = [
            p for p in providers if CircuitBreakerManager.get(p.name).can_execute()
        ]

        if not available_providers:
            # All circuit breakers are open - try to use original list anyway
            logger.warning("All provider circuit breakers are open, using original list")
            available_providers = providers

        # Filter by region if specified
        prefer_region = request.preferred_region
        if prefer_region:
            region_providers = [
                p for p in available_providers if hasattr(p, "region") and p.region == prefer_region
            ]
            if region_providers:
                available_providers = region_providers
            # If no providers in preferred region, continue with all

        # Select based on strategy
        if strategy_enum == RoutingStrategy.COST:
            selected = self._select_by_cost(available_providers, request)
        elif strategy_enum == RoutingStrategy.QUALITY:
            selected = self._select_by_quality(available_providers, request)
        elif strategy_enum == RoutingStrategy.SPEED:
            selected = self._select_by_speed(available_providers, request)
        elif strategy_enum == RoutingStrategy.ROUND_ROBIN:
            selected = self._select_round_robin(available_providers)
        elif strategy_enum == RoutingStrategy.ADAPTIVE:
            selected = self._select_adaptive(available_providers, request)
        elif strategy_enum == RoutingStrategy.REGION:
            selected = self._select_by_region(available_providers, request, prefer_region)
        else:  # PRIORITY
            selected = self._select_by_priority(available_providers)

        if not selected:
            raise ValueError("Failed to select a provider")

        provider, model = selected

        # Determine provider region
        provider_region = None
        if hasattr(provider, "region"):
            provider_region = provider.region

        return RoutingDecision(
            provider_name=provider.name,
            model_id=model.id,
            estimated_cost=model.pricing_per_unit,
            estimated_latency=model.latency_estimate,
            fallback_providers=self._get_fallback_list(provider.name, media_type),
            strategy_used=strategy_enum.value,
            region=provider_region,
        )

    async def execute(
        self,
        request: GenerationRequest,
        decision: RoutingDecision | None = None,
        media_type: MediaType = MediaType.IMAGE,
    ) -> GenerationResult:
        """
        Execute a generation request using the routed provider.

        Args:
            request: The generation request
            decision: Optional pre-computed routing decision
            media_type: Type of media to generate

        Returns:
            GenerationResult from the provider
        """
        self.initialize()

        # Get routing decision if not provided
        if decision is None:
            decision = await self.route(request, media_type=media_type)

        # Get provider
        provider = self._get_provider(decision.provider_name, media_type)
        if not provider:
            return GenerationResult(
                success=False,
                error=f"Provider not found: {decision.provider_name}",
            )

        # Execute generation
        try:
            result = await provider.generate(request, model_id=decision.model_id)
            self._record_result(decision.provider_name, result)
            return result
        except Exception as e:
            logger.error(f"Generation failed with {decision.provider_name}: {e}")
            return GenerationResult(
                success=False,
                error=str(e),
                provider=decision.provider_name,
                model=decision.model_id,
            )

    async def execute_with_fallback(
        self,
        request: GenerationRequest,
        decision: RoutingDecision | None = None,
        media_type: MediaType = MediaType.IMAGE,
        max_fallbacks: int = 2,
    ) -> GenerationResult:
        """
        Execute request with automatic fallback on failure.

        Integrates circuit breakers and adaptive routing metrics.

        Args:
            request: The generation request
            decision: Optional pre-computed routing decision
            media_type: Type of media to generate
            max_fallbacks: Maximum number of fallback attempts

        Returns:
            GenerationResult from successful provider or last error
        """
        self.initialize()

        if decision is None:
            decision = await self.route(request, media_type=media_type)

        # Build provider list: primary + fallbacks
        provider_names = [decision.provider_name] + (decision.fallback_providers or [])
        provider_names = provider_names[: max_fallbacks + 1]

        result = None

        for i, provider_name in enumerate(provider_names):
            # Check circuit breaker
            breaker = CircuitBreakerManager.get(provider_name)
            if not breaker.can_execute():
                logger.info(f"Circuit breaker open for {provider_name}, skipping")
                continue

            provider = self._get_provider(provider_name, media_type)
            if not provider or not provider.is_available:
                continue

            # Use the model from decision for primary, default for fallbacks
            model_id = decision.model_id if i == 0 else None
            if model_id is None:
                model = provider.get_default_model()
                model_id = model.id if model else None

            if not model_id:
                continue

            start_time = time.time()
            timeout = self._settings.provider_timeout

            try:
                result = await asyncio.wait_for(
                    provider.generate(request, model_id=model_id),
                    timeout=timeout,
                )
                latency = time.time() - start_time

                if result.success:
                    # Record success
                    breaker.record_success()
                    self._adaptive.update(
                        provider_name,
                        success=True,
                        latency=latency,
                        cost=result.cost or 0,
                    )
                    self._record_result(provider_name, result)

                    # Track cost
                    if result.cost:
                        asyncio.create_task(
                            self._cost_tracker.record(
                                provider=provider_name,
                                model=result.model,
                                cost=result.cost,
                                media_type=media_type,
                                resolution=request.resolution,
                            )
                        )

                    if i > 0:
                        logger.info(f"Fallback to {provider_name} succeeded")
                    return result

                else:
                    # Record failure
                    breaker.record_failure()
                    self._adaptive.update(
                        provider_name,
                        success=False,
                        latency=latency,
                        cost=0,
                    )
                    self._record_result(provider_name, result)

                    # Don't fallback for non-retryable errors
                    if not result.retryable:
                        return result

            except TimeoutError:
                latency = time.time() - start_time
                breaker.record_failure()
                self._adaptive.update(
                    provider_name,
                    success=False,
                    latency=latency,
                    cost=0,
                )
                logger.warning(
                    f"Provider {provider_name} timed out after {timeout}s, "
                    f"moving to next fallback"
                )

                result = GenerationResult(
                    success=False,
                    error=f"Provider {provider_name} timed out after {timeout}s",
                    provider=provider_name,
                    model=model_id or "",
                    retryable=True,
                )

            except Exception as e:
                latency = time.time() - start_time
                breaker.record_failure()
                self._adaptive.update(
                    provider_name,
                    success=False,
                    latency=latency,
                    cost=0,
                )
                logger.warning(f"Provider {provider_name} failed with exception: {e}")

                result = GenerationResult(
                    success=False,
                    error=str(e),
                    provider=provider_name,
                    model=model_id or "",
                    retryable=is_retryable_error(str(e)),
                )

            # Check if fallback is disabled
            if not self._settings.enable_fallback:
                break

        # Return last result or create error result
        if result is None:
            result = GenerationResult(
                success=False,
                error="No available providers",
                provider="none",
            )

        return result

    def _get_provider(self, name: str, media_type: MediaType):
        """Get provider instance by name and type."""
        if media_type == MediaType.IMAGE:
            return self._registry.get_image_provider(name)
        else:
            return self._registry.get_video_provider(name)

    def _select_by_priority(self, providers: list) -> tuple:
        """Select provider with highest priority (lowest number)."""
        if not providers:
            return None
        provider = providers[0]  # Already sorted by priority
        model = provider.get_default_model()
        return (provider, model)

    def _select_by_cost(self, providers: list, request: GenerationRequest) -> tuple:
        """Select cheapest provider for the request."""
        best = None
        best_cost = float("inf")

        for provider in providers:
            for model in provider.models:
                if model.hidden:
                    continue
                if model.supports_resolution(request.resolution):
                    cost = model.pricing_per_unit
                    if request.resolution == "4K":
                        cost *= 2
                    elif request.resolution == "2K":
                        cost *= 1.5

                    if cost < best_cost:
                        best_cost = cost
                        best = (provider, model)

        return best or self._select_by_priority(providers)

    def _select_by_quality(self, providers: list, request: GenerationRequest) -> tuple:
        """Select highest quality provider."""
        best = None
        best_quality = 0.0

        for provider in providers:
            for model in provider.models:
                if model.hidden:
                    continue
                if model.supports_resolution(request.resolution):
                    if model.quality_score > best_quality:
                        best_quality = model.quality_score
                        best = (provider, model)

        return best or self._select_by_priority(providers)

    def _select_by_speed(self, providers: list, request: GenerationRequest) -> tuple:
        """Select fastest provider."""
        best = None
        best_latency = float("inf")

        for provider in providers:
            for model in provider.models:
                if model.hidden:
                    continue
                if model.supports_resolution(request.resolution):
                    if model.latency_estimate < best_latency:
                        best_latency = model.latency_estimate
                        best = (provider, model)

        return best or self._select_by_priority(providers)

    def _select_round_robin(self, providers: list) -> tuple:
        """Select provider in round-robin fashion."""
        if not providers:
            return None

        provider = providers[self._round_robin_index % len(providers)]
        self._round_robin_index += 1
        model = provider.get_default_model()
        return (provider, model)

    def _select_adaptive(self, providers: list, request: GenerationRequest) -> tuple:
        """
        Select provider using adaptive routing based on historical performance.

        Uses success rates, latencies, and costs to score providers.
        """
        if not providers:
            return None

        # Get provider names
        provider_names = [p.name for p in providers]

        # Get best provider from adaptive strategy
        best_name = self._adaptive.get_best_provider(provider_names)

        if best_name:
            for provider in providers:
                if provider.name == best_name:
                    # Find best model for this resolution
                    best_model = None
                    for model in provider.models:
                        if model.supports_resolution(request.resolution):
                            if best_model is None or model.quality_score > best_model.quality_score:
                                best_model = model
                    if best_model:
                        return (provider, best_model)
                    return (provider, provider.get_default_model())

        # Fallback to priority if adaptive has no data
        return self._select_by_priority(providers)

    def _select_by_region(
        self,
        providers: list,
        request: GenerationRequest,
        prefer_region: ProviderRegion | None = None,
    ) -> tuple:
        """
        Select provider preferring a specific region.

        Useful for latency optimization (e.g., China users prefer China providers).
        """
        if not providers:
            return None

        region = prefer_region or request.preferred_region

        if region:
            # Filter to providers in the preferred region
            region_providers = [p for p in providers if hasattr(p, "region") and p.region == region]

            if region_providers:
                # Within region, select by quality
                return self._select_by_quality(region_providers, request)

        # No region preference or no providers in region - select by quality
        return self._select_by_quality(providers, request)

    def _get_fallback_list(self, exclude: str, media_type: MediaType) -> list[str]:
        """Get fallback provider list excluding the primary."""
        if media_type == MediaType.IMAGE:
            fallbacks = self._settings.fallback_image_providers
        else:
            fallbacks = self._settings.fallback_video_providers

        return [p for p in fallbacks if p != exclude]

    def _record_result(self, provider_name: str, result: GenerationResult) -> None:
        """Record result for health tracking."""
        if provider_name not in self._health_cache:
            self._health_cache[provider_name] = ProviderHealth(
                name=provider_name,
                is_healthy=True,
                last_check=time.time(),
            )

        health = self._health_cache[provider_name]
        if result.success:
            health.success_count += 1
            health.is_healthy = True
        else:
            health.error_count += 1
            # Mark unhealthy after 3 consecutive failures
            if health.error_count >= 3:
                health.is_healthy = False

        health.last_check = time.time()

    async def check_provider_health(self, provider_name: str) -> ProviderHealth:
        """Check health of a specific provider."""
        # Check cache first
        if provider_name in self._health_cache:
            cached = self._health_cache[provider_name]
            if time.time() - cached.last_check < self.HEALTH_CACHE_TTL:
                return cached

        # Perform health check
        provider = self._registry.get_image_provider(
            provider_name
        ) or self._registry.get_video_provider(provider_name)

        if not provider:
            return ProviderHealth(
                name=provider_name,
                is_healthy=False,
                last_check=time.time(),
            )

        try:
            result = await provider.health_check()
            health = ProviderHealth(
                name=provider_name,
                is_healthy=result.get("status") == "healthy",
                last_check=time.time(),
                latency_ms=result.get("latency_ms", 0),
            )
        except Exception:
            health = ProviderHealth(
                name=provider_name,
                is_healthy=False,
                last_check=time.time(),
            )

        self._health_cache[provider_name] = health
        return health

    def get_all_provider_health(self) -> dict[str, ProviderHealth]:
        """Get health status of all registered providers."""
        return self._health_cache.copy()

    def list_available_providers(self, media_type: MediaType = MediaType.IMAGE) -> list[dict]:
        """List all available providers with their info."""
        self.initialize()

        if media_type == MediaType.IMAGE:
            providers = self._registry.get_available_image_providers()
        else:
            providers = self._registry.get_available_video_providers()

        result = []
        for p in providers:
            info = {
                "name": p.name,
                "display_name": p.display_name,
                "models": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "max_resolution": m.max_resolution,
                        "pricing": m.pricing_per_unit,
                        "quality_score": m.quality_score,
                    }
                    for m in p.models
                    if not m.hidden
                ],
            }
            # Add region if available
            if hasattr(p, "region"):
                info["region"] = p.region.value if p.region else None
            result.append(info)
        return result

    def get_adaptive_stats(self) -> dict[str, Any]:
        """Get adaptive routing statistics."""
        return self._adaptive.get_stats()

    def get_circuit_breaker_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all circuit breakers."""
        return CircuitBreakerManager.get_all_status()

    def reset_circuit_breaker(self, provider_name: str) -> bool:
        """Reset a specific provider's circuit breaker."""
        return CircuitBreakerManager.reset(provider_name)

    def reset_all_circuit_breakers(self) -> None:
        """Reset all circuit breakers."""
        CircuitBreakerManager.reset_all()

    def get_cost_summary(self, since: float = 0) -> dict[str, Any]:
        """Get cost tracking summary."""
        return self._cost_tracker.get_summary(since)


# Global singleton
_router: ProviderRouter | None = None


def get_provider_router() -> ProviderRouter:
    """Get the global provider router singleton."""
    global _router
    if _router is None:
        _router = ProviderRouter()
    return _router


def reset_provider_router() -> None:
    """Reset the global router (mainly for testing)."""
    global _router
    _router = None
