"""create recording_sessions

Revision ID: 5861508b24e0
Revises: 24f221074abc
Create Date: 2026-03-18 17:44:47.327999

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5861508b24e0'
down_revision: Union[str, Sequence[str], None] = '24f221074abc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "recording_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("session_type", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="recording"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("teacher_name", sa.String(length=200), nullable=True),
        sa.Column("scheduled_id", sa.String(length=36), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=10), nullable=True, server_default="es"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("extracted_state", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_recording_sessions_user_id", "recording_sessions", ["user_id"], unique=False)
    op.create_index("idx_recording_sessions_status", "recording_sessions", ["status"], unique=False)

    # scheduled_recordings puede no existir en bases viejas.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_name = 'scheduled_recordings'
            ) THEN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_recording_sessions_scheduled_id' AND table_name = 'recording_sessions'
                ) THEN
                    ALTER TABLE recording_sessions
                    ADD CONSTRAINT fk_recording_sessions_scheduled_id
                    FOREIGN KEY (scheduled_id) REFERENCES scheduled_recordings (id) ON DELETE SET NULL;
                END IF;
            END IF;
        END $$;
        """
    )

    # Si session_items ya existe, agregarle el FK hacia recording_sessions.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_name = 'session_items'
            ) THEN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_session_items_session_id' AND table_name = 'session_items'
                ) THEN
                    ALTER TABLE session_items
                    ADD CONSTRAINT fk_session_items_session_id
                    FOREIGN KEY (session_id) REFERENCES recording_sessions (id) ON DELETE CASCADE;
                END IF;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_session_items_session_id' AND table_name = 'session_items'
            ) THEN
                ALTER TABLE session_items DROP CONSTRAINT fk_session_items_session_id;
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_recording_sessions_scheduled_id' AND table_name = 'recording_sessions'
            ) THEN
                ALTER TABLE recording_sessions DROP CONSTRAINT fk_recording_sessions_scheduled_id;
            END IF;
        END $$;
        """
    )

    op.drop_index("idx_recording_sessions_status", table_name="recording_sessions")
    op.drop_index("idx_recording_sessions_user_id", table_name="recording_sessions")
    op.drop_table("recording_sessions")
