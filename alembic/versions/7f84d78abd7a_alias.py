"""Alias revision for legacy reference.

Some migrations referenced the revision id '7f84d78abd7a' even though the initial schema
migration used a different revision id ('20251007_full_models'). This no-op alias keeps
Alembic's revision graph consistent across environments.

Revision ID: 7f84d78abd7a
Revises: 20251007_full_models
Create Date: 2026-03-02

"""


# revision identifiers, used by Alembic.
revision = "7f84d78abd7a"
down_revision = "20251007_full_models"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
