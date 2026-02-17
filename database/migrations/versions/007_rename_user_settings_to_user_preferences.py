"""Rename user_settings table to user_preferences.

Revision ID: 007
Revises: 006
Create Date: 2026-02-17
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("user_settings", "user_preferences")


def downgrade() -> None:
    op.rename_table("user_preferences", "user_settings")
