"""Add media_type column to generated_images.

Revision ID: 010
Revises: 009
Create Date: 2026-02-20
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generated_images",
        sa.Column("media_type", sa.String(20), nullable=False, server_default="image"),
    )
    op.create_index(
        "ix_generated_images_media_type",
        "generated_images",
        ["media_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_generated_images_media_type", table_name="generated_images")
    op.drop_column("generated_images", "media_type")
