"""Scope voice note client_record_id uniqueness per user

Revision ID: 20260403_scope_voice_note_client_record_per_user
Revises: 20260324_merge_heads_voice_notes
Create Date: 2026-04-03
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260403_scope_voice_note_client_record_per_user"
down_revision = "20260324_merge_heads_voice_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE voice_notes
        DROP CONSTRAINT IF EXISTS voice_notes_client_record_id_key
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_voice_notes_user_client_record
        ON voice_notes (user_id, client_record_id)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS uq_voice_notes_user_client_record
        """
    )
    op.execute(
        """
        ALTER TABLE voice_notes
        ADD CONSTRAINT voice_notes_client_record_id_key UNIQUE (client_record_id)
        """
    )
