"""
Alibaba (通义万相 / Wanxiang) Image Provider.

This provider integrates with Alibaba Cloud's DashScope API
for image generation using the Wanxiang models.

API Documentation:
https://help.aliyun.com/zh/dashscope/developer-reference/tongyi-wanxiang
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

ALIBABA_MODELS = [
    ProviderModel(
        id="qwen-image",
        name="通义万相 (Qwen Image)",
        provider="alibaba",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.02,
        quality_score=0.88,
        latency_estimate=15.0,
        is_default=True,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.BEARER_TOKEN,
        tier="balanced",
        arena_rank=9,
        arena_score=1165,
        aliases=["wanx-v1"],
        strengths=["chinese-style", "cost-effective"],
    ),
    ProviderModel(
        id="wan2.6-t2i",
        name="Wan 2.6 Text-to-Image",
        provider="alibaba",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.025,
        quality_score=0.91,
        latency_estimate=12.0,
        is_default=False,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.BEARER_TOKEN,
        tier="balanced",
        arena_rank=7,
        arena_score=1175,
        strengths=["photorealism", "detail"],
    ),
    ProviderModel(
        id="wanx-sketch-to-image-v1",
        name="通义万相 草图生图",
        provider="alibaba",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.IMAGE_TO_IMAGE,
        ],
        max_resolution="1K",
        supports_aspect_ratios=["1:1", "16:9", "9:16"],
        pricing_per_unit=0.02,
        quality_score=0.85,
        latency_estimate=12.0,
        is_default=False,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.BEARER_TOKEN,
        tier="balanced",
        hidden=True,
    ),
    ProviderModel(
        id="wanx-style-repaint-v1",
        name="通义万相 风格重绘",
        provider="alibaba",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.STYLE_TRANSFER,
            ProviderCapability.IMAGE_TO_IMAGE,
        ],
        max_resolution="1K",
        supports_aspect_ratios=["1:1", "16:9", "9:16"],
        pricing_per_unit=0.02,
        quality_score=0.86,
        latency_estimate=15.0,
        is_default=False,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.BEARER_TOKEN,
        tier="balanced",
        hidden=True,
    ),
]

# DashScope API model name mapping (canonical ID → API model name)
DASHSCOPE_MODEL_MAP = {
    "qwen-image": "wanx-v1",
    "wan2.6-t2i": "wan2.6-t2i",
}

# Size mappings for Alibaba API
SIZE_MAP = {
    "1:1": "1024*1024",
    "16:9": "1280*720",
    "9:16": "720*1280",
    "4:3": "1024*768",
    "3:4": "768*1024",
    "3:2": "1024*682",
    "2:3": "682*1024",
}


class AlibabaProvider(ChinaImageProvider):
    """
    通义万相 (Alibaba Wanxiang) image generation provider.

    Uses DashScope API for text-to-image and image-to-image generation.
    Features:
    - High-quality Chinese-style image generation
    - Multiple artistic styles
    - Async task-based generation
    """

    RETRY_CONFIG = RetryConfig()

    def __init__(self, config: ProviderConfig | None = None):
        """
        Initialize the Alibaba provider.

        Args:
            config: Optional provider configuration with API key
        """
        self._config = config or ProviderConfig()
        self._api_key = (
            self._config.api_key
            or os.getenv("PROVIDER_ALIBABA_API_KEY")
            or os.getenv("ALIBABA_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
        )
        self._base_url = self._config.api_base_url or "https://dashscope.aliyuncs.com/api/v1"
        self._models = ALIBABA_MODELS.copy()
        self._client: httpx.AsyncClient | None = None
        self._stats: list[dict] = []

    @property
    def name(self) -> str:
        return "alibaba"

    @property
    def display_name(self) -> str:
        return "通义万相 (Alibaba)"

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
        """Get default headers for DashScope API."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",  # Enable async mode
        }

    def _get_size(self, aspect_ratio: str) -> str:
        """Convert aspect ratio to size string for API."""
        return SIZE_MAP.get(aspect_ratio, "1024*1024")

    async def submit_task(
        self,
        request: GenerationRequest,
        model: ProviderModel,
    ) -> str:
        """
        Submit generation task to DashScope API.

        Args:
            request: The generation request
            model: The model to use

        Returns:
            Task ID string
        """
        client = await self._get_client()

        # Build payload based on model type
        if model.id in ("qwen-image", "wan2.6-t2i"):
            # Text to image
            payload = {
                "model": DASHSCOPE_MODEL_MAP.get(model.id, model.id),
                "input": {
                    "prompt": request.prompt,
                },
                "parameters": {
                    "size": self._get_size(request.aspect_ratio),
                    "n": 1,  # Number of images
                    "seed": request.seed if request.seed else None,
                },
            }

            # Add negative prompt if provided
            if request.negative_prompt:
                payload["input"]["negative_prompt"] = request.negative_prompt

            # Remove None values
            payload["parameters"] = {
                k: v for k, v in payload["parameters"].items() if v is not None
            }

            response = await client.post(
                "/services/aigc/text2image/image-synthesis",
                json=payload,
            )

        elif model.id == "wanx-sketch-to-image-v1":
            # Sketch to image (requires reference image)
            if not request.reference_images:
                raise ValueError("Sketch-to-image requires a reference image")

            # Note: In production, you'd upload the image first and get a URL
            # For now, we'll raise an error since this requires additional setup
            raise NotImplementedError("Sketch-to-image requires image upload, not yet implemented")

        else:
            # Default text to image
            payload = {
                "model": model.id,
                "input": {
                    "prompt": request.prompt,
                },
                "parameters": {
                    "size": self._get_size(request.aspect_ratio),
                    "n": 1,
                },
            }
            response = await client.post(
                "/services/aigc/text2image/image-synthesis",
                json=payload,
            )

        # Check response
        if response.status_code not in [200, 201]:
            error_data = {}
            with contextlib.suppress(Exception):
                error_data = response.json()
            error_msg = (
                error_data.get("message")
                or error_data.get("error", {}).get("message")
                or f"HTTP {response.status_code}"
            )
            raise Exception(f"Failed to submit task: {error_msg}")

        data = response.json()

        # Extract task ID from response
        # DashScope returns: {"output": {"task_id": "xxx", "task_status": "PENDING"}, "request_id": "xxx"}
        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            raise Exception(f"No task_id in response: {data}")

        return task_id

    async def poll_task_status(self, task_id: str) -> TaskInfo:
        """
        Poll task status from DashScope API.

        Args:
            task_id: The task ID to check

        Returns:
            TaskInfo with current status
        """
        client = await self._get_client()

        response = await client.get(
            f"/tasks/{task_id}",
            headers={
                "Authorization": f"Bearer {self._api_key}",
            },
        )

        if response.status_code != 200:
            return TaskInfo(
                task_id=task_id,
                status="failed",
                error=f"HTTP {response.status_code}",
            )

        data = response.json()
        output = data.get("output", {})

        # Map DashScope status to our standard status
        status_map = {
            "PENDING": "queued",
            "RUNNING": "processing",
            "SUCCEEDED": "completed",
            "FAILED": "failed",
            "CANCELED": "cancelled",
            "UNKNOWN": "unknown",
        }

        task_status = output.get("task_status", "UNKNOWN")
        mapped_status = status_map.get(task_status, "unknown")

        # Extract result URL if completed
        result_url = None
        result_urls = None
        if mapped_status == "completed":
            results = output.get("results", [])
            if results:
                result_urls = [r.get("url") for r in results if r.get("url")]
                if result_urls:
                    result_url = result_urls[0]

        # Extract error if failed
        error = None
        error_code = None
        if mapped_status == "failed":
            error = output.get("message") or data.get("message")
            error_code = output.get("code") or data.get("code")

        return TaskInfo(
            task_id=task_id,
            status=mapped_status,
            progress=None,  # DashScope doesn't provide progress
            result_url=result_url,
            result_urls=result_urls,
            error=error,
            error_code=error_code,
            metadata={
                "task_status": task_status,
                "request_id": data.get("request_id"),
            },
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

            # DashScope doesn't have a dedicated health endpoint,
            # but we can check with a minimal request
            response = await client.get(
                "/tasks/test-nonexistent",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10.0,
            )
            latency = time.time() - start

            # 404 means API is reachable, auth works
            # 401/403 means auth issue but API is up
            if response.status_code in [404, 401, 403]:
                status = "healthy" if response.status_code == 404 else "degraded"
                return {
                    "status": status,
                    "latency_ms": int(latency * 1000),
                    "models_available": len(self._models),
                }
            else:
                return {
                    "status": "unhealthy",
                    "message": f"Unexpected response: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "unhealthy",
                "message": str(e)[:100],
            }
