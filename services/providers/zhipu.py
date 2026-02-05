"""
Zhipu AI (智谱) Image Provider - CogView models.

This provider integrates with Zhipu AI's BigModel API
for image generation using the CogView series models.

API Documentation:
https://open.bigmodel.cn/dev/api/image-model/cogview
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

ZHIPU_MODELS = [
    ProviderModel(
        id="cogview-3-plus",
        name="CogView-3 Plus",
        provider="zhipu",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
        pricing_per_unit=0.025,  # ~0.18 RMB
        quality_score=0.90,
        latency_estimate=12.0,
        is_default=True,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.BEARER_TOKEN,
    ),
    ProviderModel(
        id="cogview-3",
        name="CogView-3",
        provider="zhipu",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="1K",
        supports_aspect_ratios=["1:1", "16:9", "9:16"],
        pricing_per_unit=0.015,  # ~0.1 RMB
        quality_score=0.85,
        latency_estimate=10.0,
        is_default=False,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.BEARER_TOKEN,
    ),
    ProviderModel(
        id="cogview-4",
        name="CogView-4",
        provider="zhipu",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.03,  # Higher quality, higher price
        quality_score=0.92,
        latency_estimate=15.0,
        is_default=False,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.BEARER_TOKEN,
    ),
]

# Size mappings for Zhipu API
SIZE_MAP = {
    "1:1": "1024x1024",
    "16:9": "1440x816",  # Zhipu uses specific sizes
    "9:16": "816x1440",
    "4:3": "1152x864",
    "3:4": "864x1152",
    "3:2": "1296x864",
    "2:3": "864x1296",
}


class ZhipuProvider(ChinaImageProvider):
    """
    智谱 AI CogView image generation provider.

    Uses BigModel API for text-to-image generation with CogView models.
    Features:
    - State-of-the-art image generation
    - Strong understanding of Chinese prompts
    - Multiple model tiers (CogView-3, 3-Plus, 4)
    """

    RETRY_CONFIG = RetryConfig()

    def __init__(self, config: ProviderConfig | None = None):
        """
        Initialize the Zhipu provider.

        Args:
            config: Optional provider configuration with API key
        """
        self._config = config or ProviderConfig()
        self._api_key = (
            self._config.api_key
            or os.getenv("PROVIDER_ZHIPU_API_KEY")
            or os.getenv("ZHIPU_API_KEY")
        )
        self._base_url = self._config.api_base_url or "https://open.bigmodel.cn/api/paas/v4"
        self._models = ZHIPU_MODELS.copy()
        self._client: httpx.AsyncClient | None = None
        self._stats: list[dict] = []

    @property
    def name(self) -> str:
        return "zhipu"

    @property
    def display_name(self) -> str:
        return "智谱 AI (CogView)"

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
        # Zhipu API keys are typically in format "xxx.yyy"
        if "." not in self._api_key and len(self._api_key) < 20:
            return False, "API key format appears invalid"
        return True, "API key format is valid"

    def _get_default_headers(self) -> dict:
        """Get default headers for BigModel API."""
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
        Submit generation task to BigModel API.

        Args:
            request: The generation request
            model: The model to use

        Returns:
            Task ID string
        """
        client = await self._get_client()

        # Build payload
        payload = {
            "model": model.id,
            "prompt": request.prompt,
            "size": self._get_size(request.aspect_ratio),
        }

        # Add optional parameters
        if request.seed is not None:
            payload["seed"] = request.seed

        # For CogView-3-Plus and CogView-4, quality parameter is available
        if model.id in ["cogview-3-plus", "cogview-4"]:
            # Standard or HD quality
            payload["quality"] = "standard"

        response = await client.post(
            "/images/generations",
            json=payload,
        )

        # Check response
        if response.status_code not in [200, 201]:
            error_data = {}
            with contextlib.suppress(Exception):
                error_data = response.json()
            error_msg = (
                error_data.get("error", {}).get("message")
                or error_data.get("message")
                or f"HTTP {response.status_code}"
            )
            raise Exception(f"Failed to submit task: {error_msg}")

        data = response.json()

        # Zhipu returns task_id for async requests
        # Response format: {"id": "xxx", "data": [...], "created": timestamp}
        # or for async: {"id": "xxx", "task_status": "PROCESSING"}
        task_id = data.get("id")
        if not task_id:
            raise Exception(f"No task_id in response: {data}")

        # Check if this is a sync response with immediate data
        if data.get("data") and isinstance(data["data"], list) and len(data["data"]) > 0:
            # Sync response - store data for immediate retrieval
            # We'll handle this in poll_task_status
            self._sync_results = {task_id: data}

        return task_id

    async def poll_task_status(self, task_id: str) -> TaskInfo:
        """
        Poll task status from BigModel API.

        Args:
            task_id: The task ID to check

        Returns:
            TaskInfo with current status
        """
        # Check if we have a sync result cached
        if hasattr(self, "_sync_results") and task_id in self._sync_results:
            data = self._sync_results.pop(task_id)
            result_url = None
            if data.get("data") and len(data["data"]) > 0:
                result_url = data["data"][0].get("url")
            return TaskInfo(
                task_id=task_id,
                status="completed",
                result_url=result_url,
            )

        client = await self._get_client()

        # Zhipu uses async-result endpoint
        response = await client.get(
            f"/async-result/{task_id}",
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

        if response.status_code != 200:
            # Try the alternative endpoint for images
            response = await client.get(
                f"/images/results/{task_id}",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )

        if response.status_code != 200:
            return TaskInfo(
                task_id=task_id,
                status="failed",
                error=f"HTTP {response.status_code}",
            )

        data = response.json()

        # Map Zhipu status to our standard status
        status_map = {
            "PROCESSING": "processing",
            "SUCCESS": "completed",
            "FAIL": "failed",
            "PENDING": "queued",
        }

        task_status = data.get("task_status", "PROCESSING")
        mapped_status = status_map.get(task_status, "processing")

        # Extract result URL if completed
        result_url = None
        result_urls = None
        if mapped_status == "completed":
            results = data.get("data", [])
            if results:
                result_urls = [r.get("url") for r in results if r.get("url")]
                if result_urls:
                    result_url = result_urls[0]

        # Extract error if failed
        error = None
        error_code = None
        if mapped_status == "failed":
            error = data.get("error", {}).get("message") or data.get("message")
            error_code = data.get("error", {}).get("code")

        return TaskInfo(
            task_id=task_id,
            status=mapped_status,
            progress=None,
            result_url=result_url,
            result_urls=result_urls,
            error=error,
            error_code=error_code,
            metadata={
                "task_status": task_status,
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

            # Try to check API health - Zhipu may not have a dedicated endpoint
            # Use a lightweight request to verify connectivity
            response = await client.get(
                "/models",  # List available models
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10.0,
            )
            latency = time.time() - start

            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "latency_ms": int(latency * 1000),
                    "models_available": len(self._models),
                }
            elif response.status_code in [401, 403]:
                return {
                    "status": "degraded",
                    "message": "Authentication issue",
                    "latency_ms": int(latency * 1000),
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
