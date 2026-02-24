"""Add device tokens table

Revision ID: add_device_tokens_table
Revises: add_personal_agents_profiles
Create Date: 2025-01-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_device_tokens_table'
down_revision = 'add_personal_agents_profiles'
branch_labels = None
depends_on = None


def upgrade():
    # Create device_tokens table
    op.create_table(
        'device_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=512), nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=False),
        sa.Column('device_id', sa.String(length=255), nullable=True),
        sa.Column('device_name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('token', name='uq_device_tokens_token')
    )
    
    # Create indexes for better performance
    op.create_index(
        'ix_device_tokens_user_id',
        'device_tokens',
        ['user_id']
    )
    
    op.create_index(
        'ix_device_tokens_platform',
        'device_tokens',
        ['platform']
    )
    
    op.create_index(
        'ix_device_tokens_is_active',
        'device_tokens',
        ['is_active']
    )


def downgrade():
    # Drop indexes
    op.drop_index('ix_device_tokens_is_active', table_name='device_tokens')
    op.drop_index('ix_device_tokens_platform', table_name='device_tokens')
    op.drop_index('ix_device_tokens_user_id', table_name='device_tokens')
    
    # Drop table
    op.drop_table('device_tokens')
