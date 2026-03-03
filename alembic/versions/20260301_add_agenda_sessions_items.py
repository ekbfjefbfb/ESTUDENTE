"""Add agenda sessions, chunks and items

Revision ID: 20260301_add_agenda
Revises: 20251012_perf_idx
Create Date: 2026-03-01

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260301_add_agenda"
down_revision = "20251012_perf_idx"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agenda_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("class_name", sa.String(length=200), nullable=False),
        sa.Column("teacher_name", sa.String(length=200), nullable=True),
        sa.Column("teacher_email", sa.String(length=200), nullable=True),
        sa.Column("topic_hint", sa.String(length=300), nullable=True),
        sa.Column("session_datetime", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="recording"),
        sa.Column("live_transcript", sa.Text(), nullable=False, server_default=""),
        sa.Column("extracted_state", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_agenda_sessions_user_id", "agenda_sessions", ["user_id"], unique=False)
    op.create_index("idx_agenda_sessions_status", "agenda_sessions", ["status"], unique=False)

    op.create_table(
        "agenda_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("t_start_ms", sa.Integer(), nullable=True),
        sa.Column("t_end_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["agenda_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_agenda_chunks_session_id", "agenda_chunks", ["session_id"], unique=False)
    op.create_index("idx_agenda_chunks_user_id", "agenda_chunks", ["user_id"], unique=False)

    agenda_item_type = postgresql.ENUM(
        "task",
        "event",
        "key_point",
        "summary",
        "reminder",
        name="agendaitemtype",
        create_type=False
    )
    agenda_item_status = postgresql.ENUM(
        "suggested",
        "confirmed",
        "done",
        "canceled",
        name="agendaitemstatus",
        create_type=False
    )

    op.execute("DO $$ BEGIN CREATE TYPE agendaitemtype AS ENUM ('task', 'event', 'key_point', 'summary', 'reminder'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE agendaitemstatus AS ENUM ('suggested', 'confirmed', 'done', 'canceled'); EXCEPTION WHEN duplicate_object THEN null; END $$;")

    op.create_table(
        "agenda_items",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("item_type", agenda_item_type, nullable=False),
        sa.Column("status", agenda_item_status, nullable=False, server_default="suggested"),
        sa.Column("title", sa.String(length=400), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("datetime_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("datetime_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("important", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="ai"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("item_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["agenda_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_agenda_items_session_id", "agenda_items", ["session_id"], unique=False)
    op.create_index("idx_agenda_items_user_id", "agenda_items", ["user_id"], unique=False)
    op.create_index("idx_agenda_items_type", "agenda_items", ["item_type"], unique=False)


def downgrade():
    op.drop_index("idx_agenda_items_type", table_name="agenda_items")
    op.drop_index("idx_agenda_items_user_id", table_name="agenda_items")
    op.drop_index("idx_agenda_items_session_id", table_name="agenda_items")
    op.drop_table("agenda_items")

    op.drop_index("idx_agenda_chunks_user_id", table_name="agenda_chunks")
    op.drop_index("idx_agenda_chunks_session_id", table_name="agenda_chunks")
    op.drop_table("agenda_chunks")

    op.drop_index("idx_agenda_sessions_status", table_name="agenda_sessions")
    op.drop_index("idx_agenda_sessions_user_id", table_name="agenda_sessions")
    op.drop_table("agenda_sessions")

    # Drop enums if unused
    bind = op.get_bind()
    sa.Enum(name="agendaitemtype").drop(bind, checkfirst=True)
    sa.Enum(name="agendaitemstatus").drop(bind, checkfirst=True)
