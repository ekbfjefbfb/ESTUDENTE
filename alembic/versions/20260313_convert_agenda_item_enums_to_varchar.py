"""Convert agenda_items enum columns to varchar

Revision ID: 20260313_agenda_item_enum_to_varchar
Revises: 20260302_agenda_chunk_relevance
Create Date: 2026-03-13

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260313_agenda_item_enum_to_varchar"
down_revision = "20260302_agenda_chunk_relevance"
branch_labels = None
depends_on = None


def upgrade():
    # Convert ENUM columns to VARCHAR to avoid enum/varchar operator mismatch
    op.execute(
        "ALTER TABLE agenda_items ALTER COLUMN item_type TYPE VARCHAR(32) USING item_type::text"
    )
    op.execute(
        "ALTER TABLE agenda_items ALTER COLUMN status TYPE VARCHAR(32) USING status::text"
    )

    # Ensure defaults remain consistent after type conversion
    op.alter_column(
        "agenda_items",
        "status",
        existing_type=sa.String(length=32),
        server_default="suggested",
        existing_nullable=False,
    )


def downgrade():
    # Best-effort downgrade back to enums.
    # Requires the enum types to exist.
    op.execute(
        "ALTER TABLE agenda_items ALTER COLUMN item_type TYPE agendaitemtype USING item_type::agendaitemtype"
    )
    op.execute(
        "ALTER TABLE agenda_items ALTER COLUMN status TYPE agendaitemstatus USING status::agendaitemstatus"
    )

    op.alter_column(
        "agenda_items",
        "status",
        existing_type=sa.Enum(name="agendaitemstatus"),
        server_default="suggested",
        existing_nullable=False,
    )
