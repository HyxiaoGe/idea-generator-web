"""Add thinking column to chat_messages.

Stores the AI reasoning/thinking content for assistant messages,
previously only stored in Redis JSON blobs.

Revision ID: 005
Revises: 004
Create Date: 2026-02-17
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("thinking", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "thinking")
