"""Add media_type column to prompt_templates.

Revision ID: 009
Revises: 008
Create Date: 2026-02-19
"""

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompt_templates",
        sa.Column("media_type", sa.String(20), nullable=False, server_default="image"),
    )
    op.create_index(
        "ix_prompt_templates_media_type",
        "prompt_templates",
        ["media_type"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_templates_media_type", table_name="prompt_templates")
    op.drop_column("prompt_templates", "media_type")
