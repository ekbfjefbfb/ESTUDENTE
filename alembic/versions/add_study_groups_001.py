"""Add study groups system tables

Revision ID: add_study_groups_001
Revises: add_device_tokens_table
Create Date: 2025-01-15 12:00:00.000000

Sistema completo de Study Groups con:
- study_groups: Grupos de estudio
- group_members: Miembros con roles (ADMIN/MODERATOR/MEMBER)
- shared_documents: Biblioteca compartida del grupo
- group_messages: Chat del grupo con IA
- group_invitations: Sistema viral de invitaciones
- group_activities: Log de actividades
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_study_groups_001'
down_revision = 'add_device_tokens_table'
branch_labels = None
depends_on = None


def upgrade():
    # =============================================
    # 1. STUDY GROUPS (tabla principal)
    # =============================================
    op.create_table(
        'study_groups',
        sa.Column('id', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('subject', sa.String(100), nullable=True),
        sa.Column('university', sa.String(200), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('max_members', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('members_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('creator_id', sa.String(50), nullable=False),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Índices para study_groups
    op.create_index('ix_study_groups_creator_id', 'study_groups', ['creator_id'])
    op.create_index('ix_study_groups_subject', 'study_groups', ['subject'])
    op.create_index('ix_study_groups_university', 'study_groups', ['university'])
    op.create_index('ix_study_groups_is_public', 'study_groups', ['is_public'])
    op.create_index('ix_study_groups_created_at', 'study_groups', ['created_at'])
    
    # =============================================
    # 2. GROUP MEMBERS (membresía con roles)
    # =============================================
    op.create_table(
        'group_members',
        sa.Column('id', sa.String(50), nullable=False),
        sa.Column('group_id', sa.String(50), nullable=False),
        sa.Column('user_id', sa.String(50), nullable=False),
        sa.Column('role', sa.Enum('ADMIN', 'MODERATOR', 'MEMBER', name='grouprole'), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_active_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['group_id'], ['study_groups.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('group_id', 'user_id', name='uq_group_members')
    )
    
    # Índices para group_members
    op.create_index('ix_group_members_group_id', 'group_members', ['group_id'])
    op.create_index('ix_group_members_user_id', 'group_members', ['user_id'])
    op.create_index('ix_group_members_role', 'group_members', ['role'])
    
    # =============================================
    # 3. SHARED DOCUMENTS (biblioteca compartida)
    # =============================================
    op.create_table(
        'shared_documents',
        sa.Column('id', sa.String(50), nullable=False),
        sa.Column('group_id', sa.String(50), nullable=False),
        sa.Column('document_id', sa.String(50), nullable=False),
        sa.Column('shared_by', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('document_type', sa.String(50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('download_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('shared_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['group_id'], ['study_groups.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('group_id', 'document_id', name='uq_shared_documents')
    )
    
    # Índices para shared_documents
    op.create_index('ix_shared_documents_group_id', 'shared_documents', ['group_id'])
    op.create_index('ix_shared_documents_document_id', 'shared_documents', ['document_id'])
    op.create_index('ix_shared_documents_shared_by', 'shared_documents', ['shared_by'])
    op.create_index('ix_shared_documents_shared_at', 'shared_documents', ['shared_at'])
    
    # =============================================
    # 4. GROUP MESSAGES (chat con IA)
    # =============================================
    op.create_table(
        'group_messages',
        sa.Column('id', sa.String(50), nullable=False),
        sa.Column('group_id', sa.String(50), nullable=False),
        sa.Column('user_id', sa.String(50), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('message_type', sa.Enum('USER', 'AI', 'SYSTEM', name='messagetype'), nullable=False),
        sa.Column('attachments', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('ai_context_docs', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['group_id'], ['study_groups.id'], ondelete='CASCADE')
    )
    
    # Índices para group_messages
    op.create_index('ix_group_messages_group_id', 'group_messages', ['group_id'])
    op.create_index('ix_group_messages_user_id', 'group_messages', ['user_id'])
    op.create_index('ix_group_messages_message_type', 'group_messages', ['message_type'])
    op.create_index('ix_group_messages_created_at', 'group_messages', ['created_at'])
    
    # =============================================
    # 5. GROUP INVITATIONS (sistema viral)
    # =============================================
    op.create_table(
        'group_invitations',
        sa.Column('id', sa.String(50), nullable=False),
        sa.Column('group_id', sa.String(50), nullable=False),
        sa.Column('invited_by', sa.String(50), nullable=False),
        sa.Column('invited_email', sa.String(255), nullable=False),
        sa.Column('invitation_token', sa.String(100), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'ACCEPTED', 'EXPIRED', name='invitationstatus'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('accepted_by_user_id', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['group_id'], ['study_groups.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('invitation_token', name='uq_invitation_token')
    )
    
    # Índices para group_invitations
    op.create_index('ix_group_invitations_group_id', 'group_invitations', ['group_id'])
    op.create_index('ix_group_invitations_invited_by', 'group_invitations', ['invited_by'])
    op.create_index('ix_group_invitations_invited_email', 'group_invitations', ['invited_email'])
    op.create_index('ix_group_invitations_invitation_token', 'group_invitations', ['invitation_token'])
    op.create_index('ix_group_invitations_status', 'group_invitations', ['status'])
    op.create_index('ix_group_invitations_expires_at', 'group_invitations', ['expires_at'])
    
    # =============================================
    # 6. GROUP ACTIVITIES (log de actividades)
    # =============================================
    op.create_table(
        'group_activities',
        sa.Column('id', sa.String(50), nullable=False),
        sa.Column('group_id', sa.String(50), nullable=False),
        sa.Column('user_id', sa.String(50), nullable=True),
        sa.Column('activity_type', sa.Enum('MEMBER_JOINED', 'MEMBER_LEFT', 'DOCUMENT_SHARED', 
                                           'MESSAGE_SENT', 'GROUP_CREATED', 'SETTINGS_CHANGED', 
                                           name='activitytype'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('activity_metadata', postgresql.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['group_id'], ['study_groups.id'], ondelete='CASCADE')
    )
    
    # Índices para group_activities
    op.create_index('ix_group_activities_group_id', 'group_activities', ['group_id'])
    op.create_index('ix_group_activities_activity_type', 'group_activities', ['activity_type'])
    op.create_index('ix_group_activities_created_at', 'group_activities', ['created_at'])


def downgrade():
    # Drop tables in reverse order (respecting FK constraints)
    op.drop_index('ix_group_activities_created_at', table_name='group_activities')
    op.drop_index('ix_group_activities_activity_type', table_name='group_activities')
    op.drop_index('ix_group_activities_group_id', table_name='group_activities')
    op.drop_table('group_activities')
    
    op.drop_index('ix_group_invitations_expires_at', table_name='group_invitations')
    op.drop_index('ix_group_invitations_status', table_name='group_invitations')
    op.drop_index('ix_group_invitations_invitation_token', table_name='group_invitations')
    op.drop_index('ix_group_invitations_invited_email', table_name='group_invitations')
    op.drop_index('ix_group_invitations_invited_by', table_name='group_invitations')
    op.drop_index('ix_group_invitations_group_id', table_name='group_invitations')
    op.drop_table('group_invitations')
    
    op.drop_index('ix_group_messages_created_at', table_name='group_messages')
    op.drop_index('ix_group_messages_message_type', table_name='group_messages')
    op.drop_index('ix_group_messages_user_id', table_name='group_messages')
    op.drop_index('ix_group_messages_group_id', table_name='group_messages')
    op.drop_table('group_messages')
    
    op.drop_index('ix_shared_documents_shared_at', table_name='shared_documents')
    op.drop_index('ix_shared_documents_shared_by', table_name='shared_documents')
    op.drop_index('ix_shared_documents_document_id', table_name='shared_documents')
    op.drop_index('ix_shared_documents_group_id', table_name='shared_documents')
    op.drop_table('shared_documents')
    
    op.drop_index('ix_group_members_role', table_name='group_members')
    op.drop_index('ix_group_members_user_id', table_name='group_members')
    op.drop_index('ix_group_members_group_id', table_name='group_members')
    op.drop_table('group_members')
    
    op.drop_index('ix_study_groups_created_at', table_name='study_groups')
    op.drop_index('ix_study_groups_is_public', table_name='study_groups')
    op.drop_index('ix_study_groups_university', table_name='study_groups')
    op.drop_index('ix_study_groups_subject', table_name='study_groups')
    op.drop_index('ix_study_groups_creator_id', table_name='study_groups')
    op.drop_table('study_groups')
    
    # Drop ENUMs
    op.execute('DROP TYPE IF EXISTS activitytype')
    op.execute('DROP TYPE IF EXISTS invitationstatus')
    op.execute('DROP TYPE IF EXISTS messagetype')
    op.execute('DROP TYPE IF EXISTS grouprole')
