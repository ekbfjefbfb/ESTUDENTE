"""Merge multiple heads into single timeline

Revision ID: 466239181fed
Revises: 20260302_agenda_chunk_relevance, 7f84d78abd7a, oauth_profile_001, add_study_groups_v2_chat_sessions, fix_model_inconsistencies
Create Date: 2026-03-02 21:52:14.999411

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '466239181fed'
down_revision: Union[str, Sequence[str], None] = ('20260302_agenda_chunk_relevance', '7f84d78abd7a', 'oauth_profile_001', 'add_study_groups_v2_chat_sessions', 'fix_model_inconsistencies')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
