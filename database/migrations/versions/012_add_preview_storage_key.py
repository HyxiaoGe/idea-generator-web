"""Add preview_storage_key column to prompt_templates.

Revision ID: 012
Revises: 011
Create Date: 2026-02-21
"""

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompt_templates",
        sa.Column("preview_storage_key", sa.String(500), nullable=True),
    )
    # Backfill: compute key from category + display_name_en for rows that have a preview
    op.execute("""
        UPDATE prompt_templates
        SET preview_storage_key = 'templates/preview/' || category || '/' ||
            TRIM(BOTH '-' FROM REGEXP_REPLACE(LOWER(TRIM(display_name_en)), '[^a-z0-9]+', '-', 'g'))
            || '.png'
        WHERE preview_image_url IS NOT NULL AND preview_storage_key IS NULL
    """)


def downgrade() -> None:
    op.drop_column("prompt_templates", "preview_storage_key")
