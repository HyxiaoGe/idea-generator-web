"""
Pydantic schemas for search API.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SearchResultType(StrEnum):
    """Types of search results."""

    IMAGE = "image"
    PROMPT = "prompt"
    TEMPLATE = "template"
    PROJECT = "project"
    CHAT = "chat"


class SearchResult(BaseModel):
    """A single search result."""

    id: str = Field(..., description="Item ID")
    type: SearchResultType = Field(..., description="Result type")
    title: str = Field(..., description="Display title")
    description: str | None = Field(None, description="Description/preview")
    url: str | None = Field(None, description="URL for images")
    thumbnail_url: str | None = Field(None, description="Thumbnail URL")
    score: float = Field(default=1.0, description="Relevance score")
    created_at: datetime = Field(..., description="Creation timestamp")
    highlight: str | None = Field(
        None,
        description="Highlighted matching text",
    )


class ImageSearchResult(BaseModel):
    """Image-specific search result."""

    id: str = Field(..., description="Image ID")
    prompt: str = Field(..., description="Generation prompt")
    url: str | None = Field(None, description="Image URL")
    thumbnail_url: str | None = Field(None, description="Thumbnail URL")
    mode: str = Field(..., description="Generation mode")
    provider: str | None = Field(None, description="Provider used")
    created_at: datetime = Field(..., description="Creation timestamp")
    highlight: str | None = Field(
        None,
        description="Highlighted matching text in prompt",
    )


class SearchSuggestion(BaseModel):
    """Search suggestion/autocomplete item."""

    text: str = Field(..., description="Suggested search text")
    type: SearchResultType | None = Field(
        None,
        description="Type of result this would match",
    )
    count: int | None = Field(
        None,
        description="Number of results this would return",
    )


# ============ Request/Response Schemas ============


class GlobalSearchResponse(BaseModel):
    """Response for GET /api/search."""

    query: str = Field(..., description="Search query")
    results: list[SearchResult] = Field(
        default_factory=list,
        description="Search results",
    )
    total: int = Field(..., description="Total matching results")
    limit: int = Field(..., description="Items returned")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more results exist")
    facets: dict[str, int] = Field(
        default_factory=dict,
        description="Result counts by type",
    )


class ImageSearchResponse(BaseModel):
    """Response for GET /api/search/images."""

    query: str = Field(..., description="Search query")
    results: list[ImageSearchResult] = Field(
        default_factory=list,
        description="Image search results",
    )
    total: int = Field(..., description="Total matching results")
    limit: int = Field(..., description="Items returned")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more results exist")


class SuggestionsResponse(BaseModel):
    """Response for GET /api/search/suggestions."""

    query: str = Field(..., description="Input query")
    suggestions: list[SearchSuggestion] = Field(
        default_factory=list,
        description="Search suggestions",
    )
