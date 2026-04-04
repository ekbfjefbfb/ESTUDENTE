"""root_chat_infrastructure_v34_4

Revision ID: 63127a94ad16
Revises: 06942e72ce3b
Create Date: 2026-04-04 19:16:43.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '63127a94ad16'
down_revision = '06942e72ce3b'
branch_labels = None
depends_on = None

def upgrade():
    # 1. Asegurar que chat_sessions tenga updated_at
    # Usamos una verificación segura para no romper si ya existe
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('chat_sessions')]
    
    if 'updated_at' not in columns:
        op.add_column('chat_sessions', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
        # Actualizar los existentes para que no tengan null
        op.execute("UPDATE chat_sessions SET updated_at = created_at WHERE updated_at IS NULL")
    
    # 2. Crear físicamente la tabla chat_messages si no existe
    if 'chat_messages' not in inspector.get_table_names():
        op.create_table(
            'chat_messages',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('session_id', sa.String(length=36), nullable=False),
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column('role', sa.String(length=20), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('media_metadata', postgresql.JSON(astext_type=sa.Text()), server_default='{}', nullable=True),
            sa.Column('request_id', sa.String(length=36), nullable=True),
            sa.Column('tokens_used', sa.Integer(), server_default='0', nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
        )
        op.create_index(op.f('ix_chat_messages_id'), 'chat_messages', ['id'], unique=False)
        op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)
        op.create_index(op.f('ix_chat_messages_user_id'), 'chat_messages', ['user_id'], unique=False)

def downgrade():
    op.drop_table('chat_messages')
    op.drop_column('chat_sessions', 'updated_at')
