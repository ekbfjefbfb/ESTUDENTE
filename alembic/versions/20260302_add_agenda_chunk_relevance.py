"""Add relevance fields to agenda_chunks

Revision ID: 20260302_agenda_chunk_relevance
Revises: 20260301_add_agenda
Create Date: 2026-03-02

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260302_agenda_chunk_relevance"
down_revision = "20260301_add_agenda"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agenda_chunks", sa.Column("relevance_label", sa.String(length=16), nullable=True))
    op.add_column("agenda_chunks", sa.Column("relevance_reason", sa.Text(), nullable=True))
    op.add_column("agenda_chunks", sa.Column("relevance_signals", sa.JSON(), nullable=True))
    op.add_column("agenda_chunks", sa.Column("relevance_score", sa.Float(), nullable=True))

    op.create_index("idx_agenda_chunks_relevance_label", "agenda_chunks", ["relevance_label"], unique=False)


def downgrade():
    op.drop_index("idx_agenda_chunks_relevance_label", table_name="agenda_chunks")

    op.drop_column("agenda_chunks", "relevance_score")
    op.drop_column("agenda_chunks", "relevance_signals")
    op.drop_column("agenda_chunks", "relevance_reason")
    op.drop_column("agenda_chunks", "relevance_label")
