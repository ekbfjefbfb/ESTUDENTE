"""Add hashed_password to users

Revision ID: 20260320_add_hashed_password
Revises: 20260313_merge_heads
Create Date: 2026-03-20

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260320_add_hashed_password"
down_revision = "20260313_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_password VARCHAR(255)")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS hashed_password")
