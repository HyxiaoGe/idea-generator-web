"""Add thought_signature column to chat_messages.

Gemini API requires thought_signature on model-generated images in
multi-turn history. Without persisting it, signatures are lost when
Redis expires and the session is rebuilt from the database.

Revision ID: 013
Revises: 012
Create Date: 2026-02-22
"""

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("thought_signature", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "thought_signature")
