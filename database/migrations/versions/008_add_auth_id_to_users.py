"""Add auth_id column to users and make github_id nullable.

Revision ID: 008
Revises: 007
Create Date: 2026-02-18
"""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add auth_id column
    op.add_column("users", sa.Column("auth_id", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_users_auth_id", "users", ["auth_id"])
    op.create_index("idx_users_auth_id", "users", ["auth_id"])

    # Make github_id nullable for new auth-service users
    op.alter_column("users", "github_id", existing_type=sa.BigInteger(), nullable=True)


def downgrade() -> None:
    # Make github_id non-nullable again (set 0 for any NULL rows first)
    op.execute("UPDATE users SET github_id = 0 WHERE github_id IS NULL")
    op.alter_column("users", "github_id", existing_type=sa.BigInteger(), nullable=False)

    # Drop auth_id column
    op.drop_index("idx_users_auth_id", table_name="users")
    op.drop_constraint("uq_users_auth_id", "users", type_="unique")
    op.drop_column("users", "auth_id")
