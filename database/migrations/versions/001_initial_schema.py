"""Initial schema with all tables.

Revision ID: 001
Revises:
Create Date: 2026-02-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ========================================
    # P0: Core Tables
    # ========================================

    # 1. Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("tier", sa.String(50), server_default="free", nullable=False),
        sa.Column(
            "custom_quota_multiplier", sa.Numeric(3, 2), server_default="1.0", nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_id"),
    )
    op.create_index("idx_users_github_id", "users", ["github_id"])
    op.create_index("idx_users_username", "users", ["username"])

    # ========================================
    # P1: Chat Tables (before images due to FK)
    # ========================================

    # 3. Chat sessions table
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("initial_prompt", sa.Text(), nullable=True),
        sa.Column("aspect_ratio", sa.String(20), server_default="1:1", nullable=False),
        sa.Column("resolution", sa.String(10), server_default="1K", nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latest_image_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index("idx_chat_sessions_status", "chat_sessions", ["status"])
    op.create_index("idx_chat_sessions_updated", "chat_sessions", [sa.text("updated_at DESC")])

    # 2. Generated images table
    op.create_table(
        "generated_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("storage_backend", sa.String(50), server_default="local", nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("public_url", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(50), server_default="basic", nullable=False),
        sa.Column("aspect_ratio", sa.String(20), nullable=True),
        sa.Column("resolution", sa.String(10), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(50), server_default="image/png", nullable=False),
        sa.Column("generation_duration_ms", sa.Integer(), nullable=True),
        sa.Column("text_response", sa.Text(), nullable=True),
        sa.Column("thinking", sa.Text(), nullable=True),
        sa.Column("chat_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_images_user_id", "generated_images", ["user_id"])
    op.create_index("idx_images_created_at", "generated_images", [sa.text("created_at DESC")])
    op.create_index("idx_images_mode", "generated_images", ["mode"])
    op.create_index("idx_images_provider", "generated_images", ["provider"])
    op.create_index("idx_images_chat_session", "generated_images", ["chat_session_id"])

    # 4. Chat messages table
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["image_id"], ["generated_images.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_messages_session", "chat_messages", ["session_id"])
    op.create_index(
        "idx_chat_messages_sequence", "chat_messages", ["session_id", "sequence_number"]
    )

    # ========================================
    # P2: Quota and Prompts
    # ========================================

    # 5. Quota usage table
    op.create_table(
        "quota_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mode", sa.String(50), nullable=False),
        sa.Column("points_used", sa.Integer(), nullable=False),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["image_id"], ["generated_images.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_quota_usage_user_id", "quota_usage", ["user_id"])
    op.create_index("idx_quota_usage_created", "quota_usage", ["created_at"])
    op.create_index("idx_quota_usage_mode", "quota_usage", ["mode"])

    # 6. Prompts table
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
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_prompts_category", "prompts", ["category"])
    op.create_index("idx_prompts_tags", "prompts", ["tags"], postgresql_using="gin")
    op.create_index("idx_prompts_use_count", "prompts", [sa.text("use_count DESC")])

    # 7. User favorite prompts table
    op.create_table(
        "user_favorite_prompts",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "prompt_id"),
    )
    op.create_index("idx_favorites_user", "user_favorite_prompts", ["user_id"])

    # ========================================
    # P3: Audit and Monitoring
    # ========================================

    # 8. Audit logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=True),
        sa.Column("method", sa.String(10), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("filter_result", sa.String(20), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_user", "audit_logs", ["user_id"])
    op.create_index("idx_audit_action", "audit_logs", ["action"])
    op.create_index("idx_audit_filter", "audit_logs", ["filter_result"])
    op.create_index("idx_audit_created", "audit_logs", [sa.text("created_at DESC")])

    # 9. Provider health logs table
    op.create_table(
        "provider_health_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_health_provider", "provider_health_logs", ["provider"])
    op.create_index("idx_health_created", "provider_health_logs", [sa.text("created_at DESC")])
    op.create_index("idx_health_success", "provider_health_logs", ["success"])

    # ========================================
    # Views (optional, for analytics)
    # ========================================

    # Daily quota stats view
    op.execute("""
        CREATE VIEW daily_quota_stats AS
        SELECT
            user_id,
            DATE(created_at) as date,
            mode,
            SUM(points_used) as total_points,
            COUNT(*) as request_count
        FROM quota_usage
        GROUP BY user_id, DATE(created_at), mode;
    """)

    # Provider health stats view
    op.execute("""
        CREATE VIEW provider_health_stats AS
        SELECT
            provider,
            COUNT(*) as total_requests,
            SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
            ROUND(AVG(CASE WHEN success THEN latency_ms END)) as avg_latency_ms,
            ROUND(100.0 * SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
        FROM provider_health_logs
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY provider;
    """)


def downgrade() -> None:
    # Drop views first
    op.execute("DROP VIEW IF EXISTS provider_health_stats")
    op.execute("DROP VIEW IF EXISTS daily_quota_stats")

    # Drop tables in reverse order of creation (respecting FKs)
    op.drop_table("provider_health_logs")
    op.drop_table("audit_logs")
    op.drop_table("user_favorite_prompts")
    op.drop_table("prompts")
    op.drop_table("quota_usage")
    op.drop_table("chat_messages")
    op.drop_table("generated_images")
    op.drop_table("chat_sessions")
    op.drop_table("users")
