"""Merge heads after adding VoiceNotes

Revision ID: 20260324_merge_heads_voice_notes
Revises: 20260323_add_voice_note_models, 5861508b24e0
Create Date: 2026-03-24

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260324_merge_heads_voice_notes"
down_revision = ("20260323_add_voice_note_models", "5861508b24e0")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
