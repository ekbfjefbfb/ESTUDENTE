"""relax_chat_session_constraints_v34_5

Revision ID: d2a8f2938511
Revises: 63127a94ad16
Create Date: 2026-04-04 20:15:34.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd2a8f2938511'
down_revision = '63127a94ad16'
branch_labels = None
depends_on = None

def upgrade():
    # Relajar restricciones para permitir chats individuales sin grupo
    op.alter_column('chat_sessions', 'group_id',
               existing_type=sa.VARCHAR(length=50),
               nullable=True)
    
    op.alter_column('chat_sessions', 'session_type',
               existing_type=sa.VARCHAR(length=20),
               nullable=True)

def downgrade():
    op.alter_column('chat_sessions', 'session_type',
               existing_type=sa.VARCHAR(length=20),
               nullable=False)
    
    op.alter_column('chat_sessions', 'group_id',
               existing_type=sa.VARCHAR(length=50),
               nullable=False)
