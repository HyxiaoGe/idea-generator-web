"""Add analytics columns to quota_usage.

Adds provider, model, resolution, and media_type columns
for usage analytics tracking.

Revision ID: 003
Revises: 002
Create Date: 2026-02-07
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quota_usage", sa.Column("provider", sa.String(50), nullable=True))
    op.add_column("quota_usage", sa.Column("model", sa.String(100), nullable=True))
    op.add_column("quota_usage", sa.Column("resolution", sa.String(10), nullable=True))
    op.add_column(
        "quota_usage",
        sa.Column("media_type", sa.String(20), nullable=False, server_default="image"),
    )

    op.create_index("idx_quota_usage_provider", "quota_usage", ["provider"])
    op.create_index("idx_quota_usage_media_type", "quota_usage", ["media_type"])
    op.create_index("idx_quota_usage_user_date", "quota_usage", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_quota_usage_user_date", table_name="quota_usage")
    op.drop_index("idx_quota_usage_media_type", table_name="quota_usage")
    op.drop_index("idx_quota_usage_provider", table_name="quota_usage")

    op.drop_column("quota_usage", "media_type")
    op.drop_column("quota_usage", "resolution")
    op.drop_column("quota_usage", "model")
    op.drop_column("quota_usage", "provider")
