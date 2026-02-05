"""
Base classes for Chinese AI providers.

This module provides base classes optimized for Chinese AI providers,
which typically use an async task polling pattern (submit -> poll -> download).
"""

import logging
import time
from abc import abstractmethod
from io import BytesIO
from typing import Any

from PIL import Image

from .base import (
    BaseImageProvider,
    BaseVideoProvider,
    GenerationRequest,
    GenerationResult,
    HTTPProviderMixin,
    MediaType,
    ProviderModel,
    ProviderRegion,
    TaskInfo,
    TaskPollingMixin,
    classify_error,
)

logger = logging.getLogger(__name__)


class ChinaImageProvider(TaskPollingMixin, HTTPProviderMixin, BaseImageProvider):
    """
    Base class for Chinese image generation providers.

    Chinese providers typically use an async task pattern:
    1. Submit task (returns task_id)
    2. Poll for completion
    3. Download result from URL

    Subclasses must implement:
    - submit_task(request, model) -> task_id
    - poll_task_status(task_id) -> TaskInfo
    """

    # Common settings for Chinese providers (longer timeouts due to network latency)
    DEFAULT_TIMEOUT = 300.0
    DEFAULT_POLL_INTERVAL = 3.0
    MAX_POLL_INTERVAL = 15.0

    @property
    def region(self) -> ProviderRegion:
        """Chinese providers are in China region."""
        return ProviderRegion.CHINA

    def _get_size_from_aspect_ratio(
        self,
        aspect_ratio: str,
        resolution: str = "1K",
    ) -> tuple[int, int]:
        """
        Convert aspect ratio and resolution to width/height.

        Args:
            aspect_ratio: Aspect ratio string (e.g., "16:9", "1:1")
            resolution: Resolution string ("1K", "2K", "4K")

        Returns:
            Tuple of (width, height)
        """
        # Base sizes for 1K resolution
        base_sizes = {
            "1:1": (1024, 1024),
            "16:9": (1024, 576),
            "9:16": (576, 1024),
            "4:3": (1024, 768),
            "3:4": (768, 1024),
            "3:2": (1024, 682),
            "2:3": (682, 1024),
            "21:9": (1024, 439),
        }

        # Resolution multipliers
        multipliers = {
            "1K": 1.0,
            "2K": 2.0,
            "4K": 4.0,
        }

        base = base_sizes.get(aspect_ratio, (1024, 1024))
        mult = multipliers.get(resolution, 1.0)

        return (int(base[0] * mult), int(base[1] * mult))

    async def generate(
        self,
        request: GenerationRequest,
        model_id: str | None = None,
    ) -> GenerationResult:
        """
        Standard generate flow for async task providers.

        1. Submit task
        2. Wait for completion
        3. Download image

        Args:
            request: The generation request
            model_id: Optional specific model to use

        Returns:
            GenerationResult with the generated image or error
        """
        start_time = time.time()
        result = self._create_result(MediaType.IMAGE)

        # Select model
        model = self.get_model_by_id(model_id) if model_id else self.get_default_model()
        if not model:
            result.error = f"Model not found: {model_id}" if model_id else "No models available"
            result.error_type = "invalid_model"
            return result

        result.model = model.id

        try:
            # Submit task
            task_id = await self.submit_task(request, model)
            logger.info(f"[{self.name}] Task submitted: {task_id}")

            # Wait for completion
            task_info = await self.wait_for_completion(task_id)

            if task_info.status == "completed":
                # Get result URL
                result_url = task_info.result_url
                if task_info.result_urls and len(task_info.result_urls) > 0:
                    result_url = task_info.result_urls[0]

                if result_url:
                    # Download image
                    image_data = await self.download_result(result_url)
                    result.image = Image.open(BytesIO(image_data))
                    result.success = True
                    result.cost = self._estimate_cost(model, request.resolution)
                    logger.info(f"[{self.name}] Generation completed successfully")
                else:
                    result.error = "No result URL in completed task"
                    result.error_type = "no_result"
            elif task_info.status == "timeout":
                result.error = task_info.error or "Task timed out"
                result.error_type = "timeout"
                result.retryable = True
            else:
                result.error = task_info.error or f"Task {task_info.status}"
                result.error_type = classify_error(result.error)
                result.retryable = task_info.status not in ("failed", "cancelled")

        except Exception as e:
            logger.error(f"[{self.name}] Generation failed: {e}")
            result.error = str(e)
            result.error_type = classify_error(str(e))

        result.duration = time.time() - start_time
        self._record_stats(result.duration)
        return result

    @abstractmethod
    async def submit_task(
        self,
        request: GenerationRequest,
        model: ProviderModel,
    ) -> str:
        """
        Submit generation task to the provider.

        Args:
            request: The generation request
            model: The model to use

        Returns:
            Task ID string
        """
        ...

    @abstractmethod
    async def poll_task_status(self, task_id: str) -> TaskInfo:
        """
        Poll task status from the provider.

        Args:
            task_id: The task ID to check

        Returns:
            TaskInfo with current status
        """
        ...

    async def health_check(self) -> dict:
        """Perform a health check on this provider."""
        if not self.is_available:
            return {
                "status": "unhealthy",
                "message": "API key not configured",
            }

        try:
            client = await self._get_client()
            start = time.time()

            # Most Chinese providers don't have a health endpoint,
            # so we just verify connectivity to the base URL
            await client.get("/", timeout=10.0)
            latency = time.time() - start

            # Any response (even 404) means the API is reachable
            return {
                "status": "healthy",
                "latency_ms": int(latency * 1000),
                "models_available": len(self._models),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": str(e)[:100],
            }


class ChinaVideoProvider(TaskPollingMixin, HTTPProviderMixin, BaseVideoProvider):
    """
    Base class for Chinese video generation providers.

    Videos take longer, so we use extended timeouts and poll intervals.
    """

    # Video generation takes longer
    DEFAULT_TIMEOUT = 600.0
    DEFAULT_POLL_INTERVAL = 5.0
    MAX_POLL_INTERVAL = 30.0

    @property
    def region(self) -> ProviderRegion:
        """Chinese providers are in China region."""
        return ProviderRegion.CHINA

    def _get_video_params(
        self,
        request: GenerationRequest,
        model: ProviderModel,
    ) -> dict[str, Any]:
        """
        Build video generation parameters.

        Args:
            request: The generation request
            model: The model to use

        Returns:
            Dict of parameters for the API
        """
        duration = request.duration or 5
        if model.max_video_duration and duration > model.max_video_duration:
            duration = model.max_video_duration

        return {
            "duration": duration,
            "aspect_ratio": request.aspect_ratio,
            "fps": request.fps or 24,
        }

    async def generate(
        self,
        request: GenerationRequest,
        model_id: str | None = None,
    ) -> GenerationResult:
        """
        Generate video using async task pattern.

        Args:
            request: The generation request
            model_id: Optional specific model to use

        Returns:
            GenerationResult with video_task_id for polling
        """
        start_time = time.time()
        result = self._create_result(MediaType.VIDEO)

        # Select model
        model = self.get_model_by_id(model_id) if model_id else self.get_default_model()
        if not model:
            result.error = f"Model not found: {model_id}" if model_id else "No models available"
            result.error_type = "invalid_model"
            return result

        result.model = model.id

        try:
            # Submit task
            task_id = await self.submit_task(request, model)
            logger.info(f"[{self.name}] Video task submitted: {task_id}")

            # For video, we typically return the task_id and let caller poll
            result.video_task_id = task_id
            result.success = True
            result.cost = self._estimate_cost(model, request.duration or 5)

        except Exception as e:
            logger.error(f"[{self.name}] Video generation failed: {e}")
            result.error = str(e)
            result.error_type = classify_error(str(e))

        result.duration = time.time() - start_time
        return result

    @abstractmethod
    async def submit_task(
        self,
        request: GenerationRequest,
        model: ProviderModel,
    ) -> str:
        """Submit video generation task."""
        ...

    @abstractmethod
    async def poll_task_status(self, task_id: str) -> TaskInfo:
        """Poll video task status."""
        ...

    async def get_task_status(self, task_id: str) -> dict:
        """
        Get task status in dict format (for VideoProvider protocol).

        Args:
            task_id: The task ID to check

        Returns:
            Dict with status, progress, video_url, error
        """
        info = await self.poll_task_status(task_id)

        result = {
            "status": info.status,
            "progress": int((info.progress or 0) * 100),
        }

        if info.result_url:
            result["video_url"] = info.result_url

        if info.error:
            result["error"] = info.error

        return result

    async def health_check(self) -> dict:
        """Perform a health check on this provider."""
        if not self.is_available:
            return {
                "status": "unhealthy",
                "message": "API key not configured",
            }

        try:
            client = await self._get_client()
            start = time.time()

            await client.get("/", timeout=10.0)
            latency = time.time() - start

            return {
                "status": "healthy",
                "latency_ms": int(latency * 1000),
                "models_available": len(self._models),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": str(e)[:100],
            }
