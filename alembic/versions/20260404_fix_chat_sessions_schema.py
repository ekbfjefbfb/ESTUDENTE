"""fix_chat_sessions_schema

Revision ID: 20260404_fix01
Revises: 0d0ab1312ebf
Create Date: 2026-04-04 18:40:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260404_fix01'
down_revision = '0d0ab1312ebf'
branch_labels = None
depends_on = None

def upgrade():
    # Detectar si las columnas existen antes de añadir (Safety Senior)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('chat_sessions')]
    
    if 'title' not in columns:
        op.add_column('chat_sessions', sa.Column('title', sa.String(length=200), server_default='Nueva Conversación', nullable=False))
    if 'is_active' not in columns:
        op.add_column('chat_sessions', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    if 'is_archived' not in columns:
        op.add_column('chat_sessions', sa.Column('is_archived', sa.Boolean(), server_default='false', nullable=False))
    if 'topic' not in columns:
        op.add_column('chat_sessions', sa.Column('topic', sa.String(length=100), nullable=True))
    if 'summary' not in columns:
        op.add_column('chat_sessions', sa.Column('summary', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('chat_sessions', 'summary')
    op.drop_column('chat_sessions', 'topic')
    op.drop_column('chat_sessions', 'is_archived')
    op.drop_column('chat_sessions', 'is_active')
    op.drop_column('chat_sessions', 'title')
