"""Merge system and session fix heads

Revision ID: 06942e72ce3b
Revises: 20260403_scope_voice_note_client_record_per_user, 20260404_fix01
Create Date: 2026-04-04 12:47:24.471313

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06942e72ce3b'
down_revision: Union[str, Sequence[str], None] = ('20260403_scope_voice_note_client_record_per_user', '20260404_fix01')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
