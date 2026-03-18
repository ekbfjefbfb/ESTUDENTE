"""create session_items

Revision ID: 24f221074abc
Revises: 20260313_merge_heads
Create Date: 2026-03-18 16:44:17.229476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24f221074abc'
down_revision: Union[str, Sequence[str], None] = '20260313_merge_heads'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "session_items",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="suggested"),
        sa.Column("title", sa.String(length=400), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("datetime_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("datetime_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("important", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="ai"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("item_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["session_id"], ["recording_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_session_items_session_id", "session_items", ["session_id"], unique=False)
    op.create_index("idx_session_items_user_id", "session_items", ["user_id"], unique=False)
    op.create_index("idx_session_items_item_type", "session_items", ["item_type"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_session_items_item_type", table_name="session_items")
    op.drop_index("idx_session_items_user_id", table_name="session_items")
    op.drop_index("idx_session_items_session_id", table_name="session_items")
    op.drop_table("session_items")
