"""
ByteDance (即梦/Jimeng) Image Provider.

This provider integrates with ByteDance's Volcano Engine API
for image generation using the Jimeng (即梦) models.

API Documentation:
https://www.volcengine.com/docs/6791/1360967
"""

import contextlib
import json
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
    VolcanoEngineAuth,
)
from .china_base import ChinaImageProvider

logger = logging.getLogger(__name__)


# ============ Model Definitions ============

BYTEDANCE_MODELS = [
    ProviderModel(
        id="seedream-4.5",
        name="Seedream 4.5",
        provider="bytedance",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
            ProviderCapability.IMAGE_TO_IMAGE,
            ProviderCapability.UPSCALING,
        ],
        max_resolution="4K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        pricing_per_unit=0.04,
        quality_score=0.95,
        latency_estimate=15.0,
        is_default=True,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.VOLCANO_ENGINE,
        tier="premium",
        arena_rank=1,
        arena_score=1258,
        aliases=["jimeng-xl-pro", "jimeng-2.1-pro"],
        strengths=["photorealism", "chinese-style", "detail"],
    ),
    ProviderModel(
        id="seedream-4.0",
        name="Seedream 4.0",
        provider="bytedance",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.02,
        quality_score=0.90,
        latency_estimate=12.0,
        is_default=False,
        region=ProviderRegion.CHINA,
        execution_mode=ExecutionMode.ASYNC_TASK,
        auth_type=AuthType.VOLCANO_ENGINE,
        tier="balanced",
        arena_rank=6,
        arena_score=1183,
        aliases=["jimeng-2.0"],
        strengths=["speed", "chinese-style"],
    ),
]

# Request key mappings for different models
REQ_KEY_MAP = {
    "seedream-4.5": "jimeng_high_aes_general_v21_L",
    "seedream-4.0": "jimeng_high_aes_general_v20",
    # Legacy (safety net)
    "jimeng-2.1-pro": "jimeng_high_aes_general_v21_L",
    "jimeng-2.0": "jimeng_high_aes_general_v20",
    "jimeng-xl-pro": "jimeng_xl_pro",
}

# Size mappings for Jimeng API
SIZE_MAP = {
    "1:1": (1024, 1024),
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "4:3": (1024, 768),
    "3:4": (768, 1024),
    "3:2": (1200, 800),
    "2:3": (800, 1200),
    "21:9": (1680, 720),
}


class ByteDanceProvider(ChinaImageProvider):
    """
    即梦 (Jimeng/ByteDance) image generation provider.

    Uses Volcano Engine API for text-to-image generation.
    Features:
    - State-of-the-art image quality
    - Excellent Chinese prompt understanding
    - Multiple artistic styles
    - High resolution support (up to 4K)
    """

    RETRY_CONFIG = RetryConfig()
    DEFAULT_POLL_INTERVAL = 3.0
    DEFAULT_TIMEOUT = 300.0

    def __init__(self, config: ProviderConfig | None = None):
        """
        Initialize the ByteDance provider.

        Args:
            config: Optional provider configuration with access_key and secret_key
        """
        self._config = config or ProviderConfig()

        # ByteDance uses access_key + secret_key authentication
        self._access_key = (
            self._config.api_key
            or os.getenv("PROVIDER_BYTEDANCE_ACCESS_KEY")
            or os.getenv("BYTEDANCE_ACCESS_KEY")
            or os.getenv("VOLC_ACCESS_KEY")
        )
        self._secret_key = (
            (self._config.extra.get("secret_key") if self._config.extra else None)
            or os.getenv("PROVIDER_BYTEDANCE_SECRET_KEY")
            or os.getenv("BYTEDANCE_SECRET_KEY")
            or os.getenv("VOLC_SECRET_KEY")
        )

        self._base_url = self._config.api_base_url or "https://visual.volcengineapi.com"
        self._api_key = self._access_key  # For HTTPProviderMixin compatibility
        self._models = BYTEDANCE_MODELS.copy()
        self._client: httpx.AsyncClient | None = None
        self._stats: list[dict] = []

        # Initialize Volcano Engine auth
        if self._access_key and self._secret_key:
            self._auth = VolcanoEngineAuth(
                access_key=self._access_key,
                secret_key=self._secret_key,
                region="cn-north-1",
                service="cv",
            )
        else:
            self._auth = None

    @property
    def name(self) -> str:
        return "bytedance"

    @property
    def display_name(self) -> str:
        return "即梦 (ByteDance)"

    @property
    def models(self) -> list[ProviderModel]:
        return self._models

    @property
    def is_available(self) -> bool:
        return (
            self._access_key is not None
            and self._secret_key is not None
            and len(self._access_key) > 0
            and len(self._secret_key) > 0
        )

    def validate_api_key(self) -> tuple[bool, str]:
        """Validate the configured API keys."""
        if not self._access_key:
            return False, "Access key not configured"
        if not self._secret_key:
            return False, "Secret key not configured"
        if len(self._access_key) < 10 or len(self._secret_key) < 10:
            return False, "API keys appear to be too short"
        return True, "API keys format is valid"

    def _get_default_headers(self) -> dict:
        """Get default headers (auth applied per-request)."""
        return {
            "Content-Type": "application/json",
        }

    def _get_size(self, aspect_ratio: str, resolution: str = "1K") -> tuple[int, int]:
        """
        Get size tuple for the API.

        Args:
            aspect_ratio: Aspect ratio string
            resolution: Resolution string ("1K", "2K", "4K")

        Returns:
            Tuple of (width, height)
        """
        base = SIZE_MAP.get(aspect_ratio, (1024, 1024))

        # Scale based on resolution
        if resolution == "2K":
            return (base[0] * 2, base[1] * 2)
        elif resolution == "4K":
            return (base[0] * 4, base[1] * 4)
        return base

    def _get_auth_headers(
        self,
        method: str,
        path: str,
        query: str,
        body: str,
    ) -> dict:
        """
        Get authentication headers for the request.

        Args:
            method: HTTP method
            path: Request path
            query: Query string
            body: Request body as JSON string

        Returns:
            Headers dict with auth
        """
        if not self._auth:
            return {}

        headers = {
            "Content-Type": "application/json",
        }

        host = "visual.volcengineapi.com"
        headers = self._auth.apply(
            headers=headers,
            method=method,
            path=path,
            query=query,
            body=body,
            host=host,
        )

        return headers

    async def submit_task(
        self,
        request: GenerationRequest,
        model: ProviderModel,
    ) -> str:
        """
        Submit generation task to Volcano Engine API.

        Args:
            request: The generation request
            model: The model to use

        Returns:
            Task ID string
        """
        if not self._auth:
            raise Exception("ByteDance authentication not configured")

        client = await self._get_client()

        # Get model-specific request key
        req_key = REQ_KEY_MAP.get(model.id, "jimeng_high_aes_general_v21_L")

        # Get size
        width, height = self._get_size(request.aspect_ratio, request.resolution)

        # Build payload
        payload = {
            "req_key": req_key,
            "prompt": request.prompt,
            "width": width,
            "height": height,
            "return_url": True,
            "logo_info": {
                "add_logo": False,
            },
        }

        # Add optional parameters
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt

        if request.seed is not None:
            payload["seed"] = request.seed

        # Convert payload to JSON
        body = json.dumps(payload)

        # Build query string
        query = "Action=CVProcess&Version=2022-08-31"
        path = "/"

        # Get auth headers
        headers = self._get_auth_headers("POST", path, query, body)

        response = await client.post(
            f"{path}?{query}",
            content=body,
            headers=headers,
        )

        # Check response
        if response.status_code not in [200, 201]:
            error_data = {}
            with contextlib.suppress(Exception):
                error_data = response.json()
            error_msg = (
                error_data.get("ResponseMetadata", {}).get("Error", {}).get("Message")
                or error_data.get("message")
                or f"HTTP {response.status_code}"
            )
            raise Exception(f"Failed to submit task: {error_msg}")

        data = response.json()

        # Extract task ID or handle sync response
        # Volcano Engine may return:
        # 1. Async: {"data": {"task_id": "xxx"}}
        # 2. Sync: {"code": 10000, "data": {"image_urls": [...]}}
        task_id = data.get("data", {}).get("task_id")

        if not task_id:
            # Check for sync response with image_urls
            image_urls = data.get("data", {}).get("image_urls", [])
            binary_data = data.get("data", {}).get("binary_data_base64", [])

            if image_urls or binary_data:
                # This is a sync response - generate a fake task_id and cache result
                task_id = f"sync_{id(data)}"
                self._sync_results = getattr(self, "_sync_results", {})
                self._sync_results[task_id] = data
            else:
                raise Exception(f"No task_id or image_urls in response: {data}")

        return task_id

    async def poll_task_status(self, task_id: str) -> TaskInfo:
        """
        Poll task status from Volcano Engine API.

        Args:
            task_id: The task ID to check

        Returns:
            TaskInfo with current status
        """
        # Check for cached sync result
        if hasattr(self, "_sync_results") and task_id in self._sync_results:
            data = self._sync_results.pop(task_id)
            # Extract base64 image or URL
            binary_data_list = data.get("data", {}).get("binary_data_base64", [])
            image_urls = data.get("data", {}).get("image_urls", [])

            if binary_data_list and len(binary_data_list) > 0 and binary_data_list[0]:
                # Store base64 data for later retrieval
                return TaskInfo(
                    task_id=task_id,
                    status="completed",
                    result_url=f"data:image/png;base64,{binary_data_list[0]}",
                )
            elif image_urls and len(image_urls) > 0:
                return TaskInfo(
                    task_id=task_id,
                    status="completed",
                    result_url=image_urls[0],
                    result_urls=image_urls,
                )
            else:
                return TaskInfo(
                    task_id=task_id,
                    status="failed",
                    error="No image data in sync response",
                )

        if not self._auth:
            return TaskInfo(
                task_id=task_id,
                status="failed",
                error="Authentication not configured",
            )

        client = await self._get_client()

        # Build query payload
        payload = {
            "req_key": "jimeng_high_aes_general_v21_L",  # Generic query
            "task_id": task_id,
        }
        body = json.dumps(payload)

        query = "Action=CVProcess&Version=2022-08-31"
        path = "/"

        headers = self._get_auth_headers("POST", path, query, body)

        response = await client.post(
            f"{path}?{query}",
            content=body,
            headers=headers,
        )

        if response.status_code != 200:
            return TaskInfo(
                task_id=task_id,
                status="failed",
                error=f"HTTP {response.status_code}",
            )

        data = response.json()

        # Check response metadata for errors
        metadata = data.get("ResponseMetadata", {})
        if metadata.get("Error"):
            error = metadata["Error"]
            return TaskInfo(
                task_id=task_id,
                status="failed",
                error=error.get("Message", "Unknown error"),
                error_code=error.get("Code"),
            )

        task_data = data.get("data", {})

        # Map status
        status_map = {
            "not_started": "queued",
            "in_queue": "queued",
            "running": "processing",
            "done": "completed",
            "success": "completed",
            "failed": "failed",
            "timeout": "timeout",
        }

        task_status = task_data.get("status", "running")
        mapped_status = status_map.get(task_status.lower(), "processing")

        # Extract result URL if completed
        result_url = None
        result_urls = None
        if mapped_status == "completed":
            image_urls = task_data.get("image_urls", [])
            if image_urls:
                result_urls = image_urls
                result_url = image_urls[0]
            else:
                # Check for base64 data
                binary_data = task_data.get("binary_data_base64")
                if binary_data:
                    result_url = f"data:image/png;base64,{binary_data}"

        # Extract error if failed
        error = None
        if mapped_status == "failed":
            error = task_data.get("err_msg") or task_data.get("message")

        # Calculate progress
        progress = None
        if mapped_status == "processing":
            progress = 0.5  # Generic progress for processing state

        return TaskInfo(
            task_id=task_id,
            status=mapped_status,
            progress=progress,
            result_url=result_url,
            result_urls=result_urls,
            error=error,
            metadata={
                "task_status": task_status,
            },
        )

    async def download_result(self, result_url: str) -> bytes:
        """
        Download result, handling base64 data URLs.

        Args:
            result_url: URL or data URL to download

        Returns:
            Image bytes
        """
        # Handle base64 data URLs
        if result_url.startswith("data:"):
            import base64

            # Extract base64 data after the comma
            header, data = result_url.split(",", 1)
            return base64.b64decode(data)

        # Regular URL download
        return await super().download_result(result_url)

    async def health_check(self) -> dict:
        """Perform a health check on this provider."""
        if not self._access_key or not self._secret_key:
            return {
                "status": "unhealthy",
                "message": "API keys not configured",
            }

        try:
            import time as time_module

            client = await self._get_client()
            start = time_module.time()

            # Simple connectivity check
            # Volcano Engine doesn't have a dedicated health endpoint
            # We'll check if we can authenticate
            payload = {"req_key": "health_check"}
            body = json.dumps(payload)
            query = "Action=CVProcess&Version=2022-08-31"

            headers = self._get_auth_headers("POST", "/", query, body)

            response = await client.post(
                f"/?{query}",
                content=body,
                headers=headers,
                timeout=10.0,
            )
            latency = time_module.time() - start

            # Even an error response means the API is reachable and auth works
            if response.status_code in [200, 400, 403]:
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
