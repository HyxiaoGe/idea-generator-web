"""
Pydantic schemas for templates API.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class VariableType(StrEnum):
    """Template variable types."""

    STRING = "string"
    NUMBER = "number"
    ENUM = "enum"
    BOOLEAN = "boolean"


class TemplateVariable(BaseModel):
    """Definition of a template variable."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Variable name (used in {{name}} placeholders)",
    )
    type: VariableType = Field(
        default=VariableType.STRING,
        description="Variable type",
    )
    required: bool = Field(
        default=True,
        description="Whether the variable is required",
    )
    default: str | None = Field(
        default=None,
        description="Default value",
    )
    description: str | None = Field(
        default=None,
        max_length=200,
        description="Variable description for users",
    )
    options: list[str] | None = Field(
        default=None,
        description="Valid options (for enum type)",
    )


class TemplateSettings(BaseModel):
    """Default generation settings for a template."""

    aspect_ratio: str | None = Field(
        default=None,
        description="Default aspect ratio (e.g., '16:9')",
    )
    resolution: str | None = Field(
        default=None,
        description="Default resolution (e.g., '2K')",
    )
    provider: str | None = Field(
        default=None,
        description="Preferred provider",
    )


class TemplateInfo(BaseModel):
    """Template information."""

    id: str = Field(..., description="Template ID")
    name: str = Field(..., description="Template name")
    description: str | None = Field(None, description="Template description")
    prompt_template: str = Field(..., description="Prompt template with {{variables}}")
    variables: list[TemplateVariable] = Field(
        default_factory=list,
        description="Variable definitions",
    )
    default_settings: TemplateSettings = Field(
        default_factory=TemplateSettings,
        description="Default generation settings",
    )
    category: str | None = Field(None, description="Template category")
    tags: list[str] | None = Field(None, description="Template tags")
    is_public: bool = Field(default=False, description="Whether template is public")
    is_owner: bool = Field(default=False, description="Whether current user owns it")
    use_count: int = Field(default=0, description="Usage count")
    preview_url: str | None = Field(None, description="Preview image URL")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class TemplateListItem(BaseModel):
    """Abbreviated template info for list views."""

    id: str = Field(..., description="Template ID")
    name: str = Field(..., description="Template name")
    description: str | None = Field(None, description="Template description")
    category: str | None = Field(None, description="Template category")
    tags: list[str] | None = Field(None, description="Template tags")
    is_public: bool = Field(default=False, description="Whether template is public")
    is_owner: bool = Field(default=False, description="Whether current user owns it")
    use_count: int = Field(default=0, description="Usage count")
    preview_url: str | None = Field(None, description="Preview image URL")


# ============ Request/Response Schemas ============


class CreateTemplateRequest(BaseModel):
    """Request for creating a template."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Template name",
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Template description",
    )
    prompt_template: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Prompt template with {{variable}} placeholders",
    )
    variables: list[TemplateVariable] = Field(
        default_factory=list,
        description="Variable definitions",
    )
    default_settings: TemplateSettings | None = Field(
        default=None,
        description="Default generation settings",
    )
    category: str | None = Field(
        default=None,
        max_length=50,
        description="Template category",
    )
    tags: list[str] | None = Field(
        default=None,
        max_items=10,
        description="Template tags",
    )
    is_public: bool = Field(
        default=False,
        description="Make template publicly visible",
    )


class CreateTemplateResponse(BaseModel):
    """Response for creating a template."""

    success: bool = True
    template: TemplateInfo


class ListTemplatesResponse(BaseModel):
    """Response for listing templates."""

    templates: list[TemplateListItem] = Field(default_factory=list)
    total: int = Field(..., description="Total number of templates")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more items exist")
    categories: list[str] = Field(
        default_factory=list,
        description="Available categories",
    )


class GetTemplateResponse(BaseModel):
    """Response for getting a template."""

    template: TemplateInfo


class UpdateTemplateRequest(BaseModel):
    """Request for updating a template."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Template name",
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Template description",
    )
    prompt_template: str | None = Field(
        default=None,
        min_length=1,
        max_length=10000,
        description="Prompt template",
    )
    variables: list[TemplateVariable] | None = Field(
        default=None,
        description="Variable definitions",
    )
    default_settings: TemplateSettings | None = Field(
        default=None,
        description="Default generation settings",
    )
    category: str | None = Field(
        default=None,
        max_length=50,
        description="Template category",
    )
    tags: list[str] | None = Field(
        default=None,
        max_items=10,
        description="Template tags",
    )
    is_public: bool | None = Field(
        default=None,
        description="Make template publicly visible",
    )


class UpdateTemplateResponse(BaseModel):
    """Response for updating a template."""

    success: bool = True
    template: TemplateInfo


class DeleteTemplateResponse(BaseModel):
    """Response for deleting a template."""

    success: bool = True
    message: str = Field(default="Template deleted successfully")


class UseTemplateRequest(BaseModel):
    """Request for using a template to generate an image."""

    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Variable values to fill in the template",
    )
    settings_override: TemplateSettings | None = Field(
        default=None,
        description="Override default settings",
    )


class UseTemplateResponse(BaseModel):
    """Response for using a template."""

    prompt: str = Field(..., description="Generated prompt with variables filled in")
    settings: TemplateSettings = Field(
        ...,
        description="Settings to use for generation",
    )
