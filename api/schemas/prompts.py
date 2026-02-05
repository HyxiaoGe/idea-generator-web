"""
Prompts-related Pydantic schemas for prompt library management.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class PromptTemplate(BaseModel):
    """A single prompt template."""

    id: str = Field(..., description="Unique prompt ID")
    text: str = Field(..., description="The prompt text")
    description: str | None = Field(None, description="Description of the prompt")
    category: str = Field(..., description="Category name")
    tags: list[str] = Field(default_factory=list, description="Associated tags")
    style: str | None = Field(None, description="Style preference")
    is_favorite: bool = Field(default=False, description="Whether marked as favorite")
    created_at: datetime | None = None
    language: str = Field(default="en", description="Language code")


class PromptCategory(BaseModel):
    """A prompt category with metadata."""

    name: str = Field(..., description="Category name")
    display_name: str = Field(..., description="Display name")
    description: str | None = Field(None, description="Category description")
    count: int = Field(default=0, description="Number of prompts")
    icon: str | None = Field(None, description="Category icon")


class ListPromptsRequest(BaseModel):
    """Request parameters for listing prompts."""

    category: str | None = Field(None, description="Filter by category")
    search: str | None = Field(None, description="Search in prompt text")
    favorites_only: bool = Field(default=False, description="Show only favorites")
    language: str = Field(default="en", description="Language filter")
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ListPromptsResponse(BaseModel):
    """Response containing prompts list."""

    prompts: list[PromptTemplate] = Field(default_factory=list)
    total: int = Field(default=0)
    categories: list[PromptCategory] = Field(default_factory=list)


class GeneratePromptsRequest(BaseModel):
    """Request to generate new prompts with AI."""

    category: str = Field(..., description="Category to generate for")
    style: str | None = Field(None, description="Style preference")
    count: int = Field(default=10, ge=1, le=30, description="Number of prompts")
    language: str = Field(default="en", description="Language for prompts")


class GeneratePromptsResponse(BaseModel):
    """Response from prompt generation."""

    prompts: list[PromptTemplate] = Field(default_factory=list)
    count: int = Field(default=0)
    category: str
    saved: bool = Field(default=False, description="Whether saved to library")


class ToggleFavoriteRequest(BaseModel):
    """Request to toggle favorite status."""

    prompt_id: str = Field(..., description="Prompt ID to toggle")


class ToggleFavoriteResponse(BaseModel):
    """Response for favorite toggle."""

    prompt_id: str
    is_favorite: bool
    message: str = Field(default="Favorite status updated")


class SavePromptRequest(BaseModel):
    """Request to save a custom prompt."""

    text: str = Field(..., min_length=1, max_length=2000)
    description: str | None = Field(None, max_length=500)
    category: str = Field(default="custom")
    tags: list[str] = Field(default_factory=list)
    language: str = Field(default="en")


class SavePromptResponse(BaseModel):
    """Response for saving a prompt."""

    prompt: PromptTemplate
    message: str = Field(default="Prompt saved successfully")
