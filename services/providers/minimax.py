"""
MiniMax Image Provider.

This provider integrates with MiniMax's API for image generation.

API Documentation:
https://platform.minimaxi.com/document/image-generation
"""

import contextlib
import logging
import os

import httpx

from .base import (
    AuthType,
    ExecutionMode,
    GenerationRequest,
    MediaType,
    ProviderCapability,
    ProviderConfig,
    ProviderModel,
    ProviderRegion,
    RetryConfig,
    TaskInfo,
)
from .china_base import ChinaImageProvider

logger = logging.getLogger(__name__)


# ============ Model Definitions ============

MINIMAX_MODELS = [
    ProviderModel(
        id="image-01",
        name="MiniMax Image-01",
        provider="minimax",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.02,  # Competitive pricing
        quality_score=0.87,
        latency_estimate=12.0,
        is_default=True,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.BEARER_TOKEN,
    ),
    ProviderModel(
        id="image-01-hd",
        name="MiniMax Image-01 HD",
        provider="minimax",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
            ProviderCapability.UPSCALING,
        ],
        max_resolution="4K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.035,
        quality_score=0.90,
        latency_estimate=18.0,
        is_default=False,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.BEARER_TOKEN,
    ),
]

# Size mappings for MiniMax API
SIZE_MAP = {
    "1:1": "1024x1024",
    "16:9": "1280x720",
    "9:16": "720x1280",
    "4:3": "1024x768",
    "3:4": "768x1024",
    "3:2": "1200x800",
    "2:3": "800x1200",
}


class MiniMaxProvider(ChinaImageProvider):
    """
    MiniMax image generation provider.

    Uses MiniMax API for text-to-image generation.
    Features:
    - High-quality image generation
    - Good Chinese prompt understanding
    - Competitive pricing
    """

    RETRY_CONFIG = RetryConfig()

    def __init__(self, config: ProviderConfig | None = None):
        """
        Initialize the MiniMax provider.

        Args:
            config: Optional provider configuration with API key and group_id
        """
        self._config = config or ProviderConfig()
        self._api_key = (
            self._config.api_key
            or os.getenv("PROVIDER_MINIMAX_API_KEY")
            or os.getenv("MINIMAX_API_KEY")
        )
        self._group_id = (
            (self._config.extra.get("group_id") if self._config.extra else None)
            or os.getenv("PROVIDER_MINIMAX_GROUP_ID")
            or os.getenv("MINIMAX_GROUP_ID")
        )
        # 注意: 图像生成 API 使用 minimaxi.com 而不是 minimax.chat
        self._base_url = self._config.api_base_url or "https://api.minimaxi.com/v1"
        self._models = MINIMAX_MODELS.copy()
        self._client: httpx.AsyncClient | None = None
        self._stats: list[dict] = []

    @property
    def name(self) -> str:
        return "minimax"

    @property
    def display_name(self) -> str:
        return "MiniMax"

    @property
    def models(self) -> list[ProviderModel]:
        return self._models

    @property
    def is_available(self) -> bool:
        return self._api_key is not None and len(self._api_key) > 0

    def validate_api_key(self) -> tuple[bool, str]:
        """Validate the configured API key."""
        if not self._api_key:
            return False, "API key not configured"
        if len(self._api_key) < 10:
            return False, "API key appears to be too short"
        return True, "API key format is valid"

    def _get_default_headers(self) -> dict:
        """Get default headers for MiniMax API."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _get_size(self, aspect_ratio: str) -> str:
        """Convert aspect ratio to size string for API."""
        return SIZE_MAP.get(aspect_ratio, "1024x1024")

    async def submit_task(
        self,
        request: GenerationRequest,
        model: ProviderModel,
    ) -> str:
        """
        Submit generation task to MiniMax API.

        Args:
            request: The generation request
            model: The model to use

        Returns:
            Task ID string
        """
        client = await self._get_client()

        # Build payload according to official docs
        # https://platform.minimaxi.com/docs
        payload = {
            "model": model.id,
            "prompt": request.prompt,
            "aspect_ratio": request.aspect_ratio.replace(":", ":"),  # e.g., "16:9"
            "response_format": "base64",  # Return base64 encoded image
        }

        # Add optional parameters
        if request.seed is not None:
            payload["seed"] = request.seed

        # Use the correct endpoint: /image_generation
        response = await client.post("/image_generation", json=payload)

        # Check response
        if response.status_code not in [200, 201]:
            error_data = {}
            with contextlib.suppress(Exception):
                error_data = response.json()
            error_msg = (
                error_data.get("base_resp", {}).get("status_msg")
                or error_data.get("error", {}).get("message")
                or error_data.get("message")
                or f"HTTP {response.status_code}"
            )
            raise Exception(f"Failed to submit task: {error_msg}")

        data = response.json()

        # Check for base_resp status if present
        base_resp = data.get("base_resp", {})
        if base_resp and base_resp.get("status_code") not in [None, 0]:
            raise Exception(f"API error: {base_resp.get('status_msg', 'Unknown error')}")

        # MiniMax image API returns sync response with base64 data
        # Response format: {"data": {"image_base64": ["base64_string", ...]}}
        image_base64_list = data.get("data", {}).get("image_base64", [])

        if image_base64_list:
            # Cache sync result with generated task_id
            task_id = f"sync_{id(data)}"
            self._sync_results = getattr(self, "_sync_results", {})
            self._sync_results[task_id] = data
            return task_id

        # Fallback: check for task_id (async mode, if supported)
        task_id = data.get("task_id")
        if task_id:
            return task_id

        raise Exception(f"No image_base64 or task_id in response: {data}")

    async def poll_task_status(self, task_id: str) -> TaskInfo:
        """
        Poll task status from MiniMax API.

        Args:
            task_id: The task ID to check

        Returns:
            TaskInfo with current status
        """
        # Check for cached sync result (base64 response)
        if hasattr(self, "_sync_results") and task_id in self._sync_results:
            data = self._sync_results.pop(task_id)

            # MiniMax returns: {"data": {"image_base64": ["base64_string", ...]}}
            image_base64_list = data.get("data", {}).get("image_base64", [])

            if image_base64_list:
                # Return data URLs for base64 images
                result_urls = [f"data:image/jpeg;base64,{b64}" for b64 in image_base64_list if b64]
                return TaskInfo(
                    task_id=task_id,
                    status="completed",
                    result_url=result_urls[0] if result_urls else None,
                    result_urls=result_urls,
                )
            else:
                return TaskInfo(
                    task_id=task_id,
                    status="failed",
                    error="No image_base64 in sync response",
                )

        # For async tasks (if MiniMax supports them in the future)
        client = await self._get_client()

        url = f"/image_generation/query/{task_id}"
        response = await client.get(url)

        if response.status_code != 200:
            return TaskInfo(
                task_id=task_id,
                status="failed",
                error=f"HTTP {response.status_code}",
            )

        data = response.json()

        # Check base_resp
        base_resp = data.get("base_resp", {})
        if base_resp and base_resp.get("status_code") not in [None, 0]:
            return TaskInfo(
                task_id=task_id,
                status="failed",
                error=base_resp.get("status_msg", "Unknown error"),
                error_code=str(base_resp.get("status_code")),
            )

        # Map status
        status_map = {
            "pending": "queued",
            "processing": "processing",
            "running": "processing",
            "completed": "completed",
            "success": "completed",
            "failed": "failed",
            "error": "failed",
        }

        task_status = data.get("status", "processing")
        mapped_status = status_map.get(task_status.lower(), "processing")

        # Extract result if completed
        result_url = None
        result_urls = None
        if mapped_status == "completed":
            image_base64_list = data.get("data", {}).get("image_base64", [])
            if image_base64_list:
                result_urls = [f"data:image/jpeg;base64,{b64}" for b64 in image_base64_list if b64]
                if result_urls:
                    result_url = result_urls[0]

        # Extract error if failed
        error = None
        if mapped_status == "failed":
            error = data.get("error_message") or data.get("message")

        return TaskInfo(
            task_id=task_id,
            status=mapped_status,
            progress=None,
            result_url=result_url,
            result_urls=result_urls,
            error=error,
            metadata={"task_status": task_status},
        )

    async def health_check(self) -> dict:
        """Perform a health check on this provider."""
        if not self._api_key:
            return {
                "status": "unhealthy",
                "message": "API key not configured",
            }

        try:
            import time

            client = await self._get_client()
            start = time.time()

            # Try to access API - even an error response means it's reachable
            url = "/models"
            if self._group_id:
                url = f"{url}?GroupId={self._group_id}"

            response = await client.get(url, timeout=10.0)
            latency = time.time() - start

            if response.status_code in [200, 401, 403]:
                status = "healthy" if response.status_code == 200 else "degraded"
                return {
                    "status": status,
                    "latency_ms": int(latency * 1000),
                    "models_available": len(self._models),
                }
            else:
                return {
                    "status": "unhealthy",
                    "message": f"HTTP {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "unhealthy",
                "message": str(e)[:100],
            }
