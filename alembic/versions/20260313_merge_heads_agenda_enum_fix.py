"""Merge multiple heads after agenda enum conversion

Revision ID: 20260313_merge_heads
Revises: 20260313_agenda_item_enum_to_varchar, a49a4d68a042
Create Date: 2026-03-13

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260313_merge_heads"
down_revision = ("20260313_agenda_item_enum_to_varchar", "a49a4d68a042")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
