"""Drop prompt and user_favorite_prompts tables.

Prompt functionality is being moved to the external PromptHub platform.

Revision ID: 004
Revises: 003
Create Date: 2026-02-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop user_favorite_prompts first (has FK to prompts)
    op.drop_index("idx_favorites_user", table_name="user_favorite_prompts")
    op.drop_table("user_favorite_prompts")

    # Drop prompts table
    op.drop_index("idx_prompts_use_count", table_name="prompts")
    op.drop_index("idx_prompts_tags", table_name="prompts")
    op.drop_index("idx_prompts_category", table_name="prompts")
    op.drop_table("prompts")


def downgrade() -> None:
    # Recreate prompts table
    op.create_table(
        "prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("subcategory", sa.String(100), nullable=True),
        sa.Column("text_en", sa.Text(), nullable=False),
        sa.Column("text_zh", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(100)), nullable=True),
        sa.Column("difficulty", sa.String(20), nullable=True),
        sa.Column("use_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("favorite_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_prompts_category", "prompts", ["category"])
    op.create_index("idx_prompts_tags", "prompts", ["tags"], postgresql_using="gin")
    op.create_index("idx_prompts_use_count", "prompts", [sa.text("use_count DESC")])

    # Recreate user_favorite_prompts table
    op.create_table(
        "user_favorite_prompts",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "prompt_id"),
    )
    op.create_index("idx_favorites_user", "user_favorite_prompts", ["user_id"])
