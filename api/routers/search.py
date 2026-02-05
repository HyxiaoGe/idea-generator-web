"""
Search router for global search functionality.

Endpoints:
- GET /api/search - Global search
- GET /api/search/images - Search images
- GET /api/search/prompts - Search prompts
- GET /api/search/suggestions - Search suggestions
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from api.dependencies import (
    get_image_repository,
    get_prompt_repository,
    get_template_repository,
    get_user_repository,
)
from api.routers.auth import get_current_user
from api.schemas.search import (
    GlobalSearchResponse,
    ImageSearchResponse,
    ImageSearchResult,
    PromptSearchResponse,
    SearchResult,
    SearchResultType,
    SearchSuggestion,
    SuggestionsResponse,
)
from database.repositories import (
    ImageRepository,
    PromptRepository,
    TemplateRepository,
    UserRepository,
)
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# ============ Helpers ============


async def get_db_user_id(
    user: GitHubUser | None,
    user_repo: UserRepository | None,
) -> UUID | None:
    """Get database user ID from GitHub user."""
    if not user or not user_repo:
        return None

    db_user = await user_repo.get_by_github_id(int(user.id))
    return db_user.id if db_user else None


def highlight_match(text: str, query: str, context_chars: int = 50) -> str:
    """Create a highlighted snippet showing where the query matches."""
    query_lower = query.lower()
    text_lower = text.lower()

    pos = text_lower.find(query_lower)
    if pos == -1:
        return text[: context_chars * 2] + "..." if len(text) > context_chars * 2 else text

    start = max(0, pos - context_chars)
    end = min(len(text), pos + len(query) + context_chars)

    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet


# ============ Endpoints ============


@router.get("", response_model=GlobalSearchResponse)
async def global_search(
    q: str = Query(..., min_length=1, description="Search query"),
    types: str | None = Query(default=None, description="Comma-separated types to search"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: GitHubUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Global search across all content types.

    Searches images, prompts, templates, and projects.
    """
    results: list[SearchResult] = []
    facets: dict[str, int] = {}

    user_id = await get_db_user_id(user, user_repo)

    # Parse types filter
    search_types = None
    if types:
        search_types = [t.strip() for t in types.split(",")]

    # Search images
    if (not search_types or "image" in search_types) and image_repo:
        images = await image_repo.list_by_user(
            user_id=user_id,
            search=q,
            limit=limit,
        )
        facets["image"] = len(images)

        for img in images:
            results.append(
                SearchResult(
                    id=str(img.id),
                    type=SearchResultType.IMAGE,
                    title=img.filename,
                    description=img.prompt[:200] if img.prompt else None,
                    url=img.public_url,
                    thumbnail_url=None,
                    score=1.0,
                    created_at=img.created_at,
                    highlight=highlight_match(img.prompt, q) if img.prompt else None,
                )
            )

    # Search templates
    if (not search_types or "template" in search_types) and template_repo:
        templates = await template_repo.list_accessible(
            user_id=user_id,
            search=q,
            limit=limit,
        )
        facets["template"] = len(templates)

        for tmpl in templates:
            results.append(
                SearchResult(
                    id=str(tmpl.id),
                    type=SearchResultType.TEMPLATE,
                    title=tmpl.name,
                    description=tmpl.description,
                    url=None,
                    thumbnail_url=tmpl.preview_url,
                    score=0.9,
                    created_at=tmpl.created_at,
                    highlight=highlight_match(tmpl.prompt_template, q),
                )
            )

    # Sort by score and recency
    results.sort(key=lambda r: (r.score, r.created_at), reverse=True)

    # Apply pagination
    total = len(results)
    results = results[offset : offset + limit]
    has_more = offset + len(results) < total

    return GlobalSearchResponse(
        query=q,
        results=results,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
        facets=facets,
    )


@router.get("/images", response_model=ImageSearchResponse)
async def search_images(
    q: str = Query(..., min_length=1, description="Search query"),
    mode: str | None = Query(default=None, description="Filter by mode"),
    provider: str | None = Query(default=None, description="Filter by provider"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: GitHubUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Search images by prompt text."""
    if not image_repo:
        return ImageSearchResponse(
            query=q,
            results=[],
            total=0,
            limit=limit,
            offset=offset,
            has_more=False,
        )

    user_id = await get_db_user_id(user, user_repo)

    images = await image_repo.list_by_user(
        user_id=user_id,
        mode=mode,
        search=q,
        limit=limit + 1,
        offset=offset,
    )

    has_more = len(images) > limit
    images = images[:limit]

    results = []
    for img in images:
        results.append(
            ImageSearchResult(
                id=str(img.id),
                prompt=img.prompt,
                url=img.public_url,
                thumbnail_url=None,
                mode=img.mode,
                provider=img.provider,
                created_at=img.created_at,
                highlight=highlight_match(img.prompt, q) if img.prompt else None,
            )
        )

    total = await image_repo.count_by_user(user_id, mode=mode, search=q)

    return ImageSearchResponse(
        query=q,
        results=results,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get("/prompts", response_model=PromptSearchResponse)
async def search_prompts(
    q: str = Query(..., min_length=1, description="Search query"),
    category: str | None = Query(default=None, description="Filter by category"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: GitHubUser | None = Depends(get_current_user),
    prompt_repo: PromptRepository | None = Depends(get_prompt_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Search prompts in the prompt library."""
    if not prompt_repo:
        return PromptSearchResponse(
            query=q,
            results=[],
            total=0,
            limit=limit,
            offset=offset,
            has_more=False,
        )

    # TODO: Add search method to PromptRepository
    # For now, return empty results
    return PromptSearchResponse(
        query=q,
        results=[],
        total=0,
        limit=limit,
        offset=offset,
        has_more=False,
    )


@router.get("/suggestions", response_model=SuggestionsResponse)
async def get_suggestions(
    q: str = Query(..., min_length=1, description="Input query"),
    limit: int = Query(default=5, ge=1, le=10),
    user: GitHubUser | None = Depends(get_current_user),
):
    """
    Get search suggestions based on partial input.

    Returns autocomplete suggestions.
    """
    # TODO: Implement proper autocomplete
    # For now, return basic suggestions
    suggestions = [
        SearchSuggestion(
            text=q,
            type=SearchResultType.IMAGE,
            count=None,
        ),
    ]

    return SuggestionsResponse(
        query=q,
        suggestions=suggestions,
    )
