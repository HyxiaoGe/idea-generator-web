"""
History-related Pydantic schemas for image history management.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from .generate import GenerationMode


class HistorySettings(BaseModel):
    """Settings used for generation."""

    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = None


class HistoryItem(BaseModel):
    """A single history record."""

    id: str = Field(..., description="Unique identifier (filename or key)")
    filename: str = Field(..., description="Image filename")
    prompt: str = Field(..., description="Generation prompt")
    mode: str = Field(..., description="Generation mode")
    settings: HistorySettings = Field(default_factory=HistorySettings)
    duration: Optional[float] = Field(None, description="Generation time in seconds")
    created_at: datetime
    url: Optional[str] = Field(None, description="Public URL if available")
    r2_key: Optional[str] = Field(None, description="R2 storage key")
    text_response: Optional[str] = Field(None, description="Model text response")
    thinking: Optional[str] = Field(None, description="Model thinking process")
    session_id: Optional[str] = Field(None, description="Chat session ID if from chat")


class HistoryListRequest(BaseModel):
    """Request parameters for listing history."""

    limit: int = Field(default=20, ge=1, le=100, description="Max items to return")
    offset: int = Field(default=0, ge=0, description="Items to skip")
    mode: Optional[str] = Field(None, description="Filter by generation mode")
    search: Optional[str] = Field(None, description="Search in prompts")
    sort: str = Field(default="newest", description="Sort order: newest or oldest")
    date_from: Optional[datetime] = Field(None, description="Filter from date")
    date_to: Optional[datetime] = Field(None, description="Filter to date")


class HistoryListResponse(BaseModel):
    """Response containing history items."""

    items: List[HistoryItem] = Field(default_factory=list)
    total: int = Field(default=0)
    limit: int
    offset: int
    has_more: bool = Field(default=False)


class HistoryDetailResponse(BaseModel):
    """Detailed history item response."""

    item: HistoryItem
    image_url: Optional[str] = Field(None, description="Direct image URL")
    image_base64: Optional[str] = Field(None, description="Base64 encoded image data")


class HistoryDeleteResponse(BaseModel):
    """Response for history deletion."""

    success: bool = Field(default=True)
    deleted_count: int = Field(default=0)
    message: str = Field(default="Items deleted successfully")


class HistoryStatsResponse(BaseModel):
    """Statistics about user's generation history."""

    total_images: int = Field(default=0)
    images_by_mode: Dict[str, int] = Field(default_factory=dict)
    total_duration: float = Field(default=0.0, description="Total generation time")
    average_duration: float = Field(default=0.0)
    earliest_date: Optional[datetime] = None
    latest_date: Optional[datetime] = None
