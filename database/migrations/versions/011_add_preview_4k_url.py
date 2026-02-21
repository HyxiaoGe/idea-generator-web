"""Add preview_4k_url column to prompt_templates.

Revision ID: 011
Revises: 010
Create Date: 2026-02-21
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompt_templates",
        sa.Column("preview_4k_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prompt_templates", "preview_4k_url")
