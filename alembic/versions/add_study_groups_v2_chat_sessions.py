"""Add chat_sessions and private_ai_messages tables; add member profile columns

Revision ID: add_study_groups_v2_chat_sessions
Revises: add_study_groups_001
Create Date: 2025-10-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_study_groups_v2_chat_sessions'
down_revision = 'add_study_groups_001'
branch_labels = None
depends_on = None


def upgrade():
    # Add columns to group_members
    op.add_column('group_members', sa.Column('avatar_url', sa.String(length=500), nullable=True))
    op.add_column('group_members', sa.Column('display_name', sa.String(length=100), nullable=True))
    op.add_column('group_members', sa.Column('status_message', sa.String(length=200), nullable=True))

    # Create chat_sessions table
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.String(50), nullable=False),
        sa.Column('user_id', sa.String(50), nullable=False),
        sa.Column('group_id', sa.String(50), nullable=False),
        sa.Column('session_type', sa.Enum('group', 'personal', name='sessiontype'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_message_at', sa.DateTime(), nullable=True),
        sa.Column('messages_count', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['study_groups.id'], ondelete='CASCADE')
    )

    op.create_index('ix_chat_sessions_user_id', 'chat_sessions', ['user_id'])
    op.create_index('ix_chat_sessions_group_id', 'chat_sessions', ['group_id'])
    op.create_index('ix_chat_sessions_is_active', 'chat_sessions', ['is_active'])

    # Create private_ai_messages table
    op.create_table(
        'private_ai_messages',
        sa.Column('id', sa.String(50), nullable=False),
        sa.Column('user_id', sa.String(50), nullable=False),
        sa.Column('session_id', sa.String(50), nullable=False),
        sa.Column('group_id', sa.String(50), nullable=False),
        sa.Column('user_message', sa.Text(), nullable=False),
        sa.Column('ai_response', sa.Text(), nullable=False),
        sa.Column('context_docs', postgresql.JSON(), nullable=True),
        sa.Column('context_messages', postgresql.JSON(), nullable=True),
        sa.Column('attachments', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('tokens_used', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['study_groups.id'], ondelete='CASCADE')
    )

    op.create_index('ix_private_ai_messages_user_id', 'private_ai_messages', ['user_id'])
    op.create_index('ix_private_ai_messages_session_id', 'private_ai_messages', ['session_id'])
    op.create_index('ix_private_ai_messages_group_id', 'private_ai_messages', ['group_id'])


def downgrade():
    # Drop private_ai_messages
    op.drop_index('ix_private_ai_messages_group_id', table_name='private_ai_messages')
    op.drop_index('ix_private_ai_messages_session_id', table_name='private_ai_messages')
    op.drop_index('ix_private_ai_messages_user_id', table_name='private_ai_messages')
    op.drop_table('private_ai_messages')

    # Drop chat_sessions
    op.drop_index('ix_chat_sessions_is_active', table_name='chat_sessions')
    op.drop_index('ix_chat_sessions_group_id', table_name='chat_sessions')
    op.drop_index('ix_chat_sessions_user_id', table_name='chat_sessions')
    op.drop_table('chat_sessions')

    # Drop columns from group_members
    op.drop_column('group_members', 'status_message')
    op.drop_column('group_members', 'display_name')
    op.drop_column('group_members', 'avatar_url')

    # Drop enum
    op.execute("DROP TYPE IF EXISTS sessiontype")
