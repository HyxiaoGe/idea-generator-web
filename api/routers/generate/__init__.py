"""
Image generation router package.

Endpoints:
- POST /api/generate - Generate a single image
- POST /api/generate/batch - Queue batch generation
- GET /api/generate/task/{task_id} - Get task progress
- POST /api/generate/search - Search-grounded generation
- POST /api/generate/blend - Blend multiple images
- POST /api/generate/inpaint - Inpaint an image
- POST /api/generate/outpaint - Outpaint an image
- POST /api/generate/describe - Describe an image
- GET /api/generate/providers - List providers
- GET /api/generate/providers/{name}/health - Provider health check
"""

from fastapi import APIRouter

from ._blend import router as blend_router
from ._core import router as core_router
from ._describe import router as describe_router
from ._inpaint import router as inpaint_router
from ._outpaint import router as outpaint_router
from ._providers import router as providers_router
from ._search import router as search_router

router = APIRouter(tags=["generation"])
router.include_router(core_router, prefix="/generate")
router.include_router(search_router, prefix="/generate")
router.include_router(blend_router, prefix="/generate")
router.include_router(inpaint_router, prefix="/generate")
router.include_router(outpaint_router, prefix="/generate")
router.include_router(describe_router, prefix="/generate")
router.include_router(providers_router, prefix="/generate")

# Re-exports for test compatibility — tests patch "api.routers.generate.<name>"
# so these names must exist in this namespace and be the same objects used by submodules.
from api.dependencies import check_quota_and_consume as check_quota_and_consume  # noqa: F401, E402
from core.redis import get_redis as get_redis  # noqa: F401, E402
from services import get_provider_router as get_provider_router  # noqa: F401, E402
from services.storage import get_storage_manager as get_storage_manager  # noqa: F401, E402

from ._helpers import build_provider_request as build_provider_request  # noqa: F401, E402
from ._helpers import create_generator as create_generator  # noqa: F401, E402
