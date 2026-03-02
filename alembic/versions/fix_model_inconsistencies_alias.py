"""Alias revision for legacy down_revision reference.

Some historical migrations referenced a non-existent revision id 'fix_model_inconsistencies'.
This file provides a no-op alias that points to the actual revision 'fix_inconsistencies_001'
so that Alembic can build a consistent revision graph.

Revision ID: fix_model_inconsistencies
Revises: fix_inconsistencies_001
Create Date: 2026-03-02

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "fix_model_inconsistencies"
down_revision = "fix_inconsistencies_001"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
