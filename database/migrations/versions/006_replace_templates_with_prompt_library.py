"""Replace templates table with full prompt template library.

Drops the old `templates` table (0 rows) and creates:
- `prompt_templates` with bilingual support, engagement metrics, trending
- `user_template_likes` (composite PK)
- `user_template_favorites` (composite PK)
- `user_template_usages` (UUID PK, analytics)

Revision ID: 006
Revises: 005
Create Date: 2026-02-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

# revision identifiers
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old templates table (0 rows, no data loss)
    op.drop_table("templates")

    # Create prompt_templates
    op.create_table(
        "prompt_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("display_name_en", sa.String(200), nullable=False),
        sa.Column("display_name_zh", sa.String(200), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("description_zh", sa.Text(), nullable=True),
        sa.Column("preview_image_url", sa.String(500), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column(
            "tags",
            ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column(
            "style_keywords",
            ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column(
            "parameters",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="beginner"),
        sa.Column("language", sa.String(10), nullable=False, server_default="bilingual"),
        sa.Column("source", sa.String(20), nullable=False, server_default="curated"),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("like_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("favorite_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("trending_score", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes for prompt_templates
    op.create_index(
        "ix_prompt_templates_category",
        "prompt_templates",
        ["category"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_prompt_templates_trending",
        "prompt_templates",
        ["trending_score"],
        postgresql_where=sa.text("deleted_at IS NULL AND is_active = TRUE"),
    )
    op.create_index(
        "ix_prompt_templates_tags",
        "prompt_templates",
        ["tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_prompt_templates_use_count",
        "prompt_templates",
        ["use_count"],
        postgresql_where=sa.text("deleted_at IS NULL AND is_active = TRUE"),
    )

    # Create user_template_likes
    op.create_table(
        "user_template_likes",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Create user_template_favorites
    op.create_table(
        "user_template_favorites",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Create user_template_usages
    op.create_table(
        "user_template_usages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_user_template_usages_template_id",
        "user_template_usages",
        ["template_id"],
    )
    op.create_index(
        "ix_user_template_usages_user_id",
        "user_template_usages",
        ["user_id"],
    )


def downgrade() -> None:
    # Drop new tables
    op.drop_table("user_template_usages")
    op.drop_table("user_template_favorites")
    op.drop_table("user_template_likes")
    op.drop_table("prompt_templates")

    # Recreate old templates table
    op.create_table(
        "templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("variables", JSONB(), nullable=False, server_default="[]"),
        sa.Column("default_settings", JSONB(), nullable=False, server_default="{}"),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("tags", ARRAY(sa.String(50)), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("preview_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
