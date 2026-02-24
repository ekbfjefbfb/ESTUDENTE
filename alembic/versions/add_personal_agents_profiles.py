"""Add personal agents and user profiles

Revision ID: add_personal_agents_profiles
Revises: fix_model_inconsistencies
Create Date: 2025-01-09 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_personal_agents_profiles'
down_revision = 'fix_model_inconsistencies'
branch_labels = None
depends_on = None


def upgrade():
    # Create new enum types
    agent_type_enum = postgresql.ENUM('tutor', 'mentor', 'assistant', 'coach', 'researcher', 'creative', name='agenttype')
    agent_type_enum.create(op.get_bind())
    
    specialization_enum = postgresql.ENUM('technology', 'business', 'academic', 'creative', 'personal_development', 'language', 'science', name='specialization')
    specialization_enum.create(op.get_bind())
    
    integration_status_enum = postgresql.ENUM('disconnected', 'connecting', 'connected', 'error', 'expired', name='integrationstatus')
    integration_status_enum.create(op.get_bind())
    
    service_type_enum = postgresql.ENUM('google_calendar', 'google_gmail', 'google_drive', 'microsoft_outlook', 'microsoft_onedrive', 'linkedin', name='servicetype')
    service_type_enum.create(op.get_bind())

    # Create user_profiles table
    op.create_table('user_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('basic_info', sa.JSON(), nullable=True),
        sa.Column('topic_interests', sa.JSON(), nullable=True),
        sa.Column('skill_levels', sa.JSON(), nullable=True),
        sa.Column('communication_preferences', sa.JSON(), nullable=True),
        sa.Column('preferred_explanation_style', sa.String(length=50), nullable=True),
        sa.Column('activity_patterns', sa.JSON(), nullable=True),
        sa.Column('learning_progress', sa.JSON(), nullable=True),
        sa.Column('learning_velocity', sa.Float(), nullable=True),
        sa.Column('profile_completeness', sa.Float(), nullable=True),
        sa.Column('total_interactions', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_profiles_id'), 'user_profiles', ['id'], unique=False)
    op.create_index(op.f('ix_user_profiles_user_id'), 'user_profiles', ['user_id'], unique=True)

    # Create learning_patterns table
    op.create_table('learning_patterns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_profile_id', sa.Integer(), nullable=False),
        sa.Column('pattern_type', sa.String(length=100), nullable=False),
        sa.Column('pattern_data', sa.JSON(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('frequency', sa.Integer(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_profile_id'], ['user_profiles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_learning_patterns_id'), 'learning_patterns', ['id'], unique=False)

    # Create personal_agents table
    op.create_table('personal_agents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.String(length=100), nullable=False),
        sa.Column('user_profile_id', sa.Integer(), nullable=False),
        sa.Column('agent_type', agent_type_enum, nullable=False),
        sa.Column('specialization', specialization_enum, nullable=False),
        sa.Column('personality_config', sa.JSON(), nullable=True),
        sa.Column('response_templates', sa.JSON(), nullable=True),
        sa.Column('specialized_prompts', sa.JSON(), nullable=True),
        sa.Column('learned_preferences', sa.JSON(), nullable=True),
        sa.Column('user_context', sa.Text(), nullable=True),
        sa.Column('conversation_memory', sa.JSON(), nullable=True),
        sa.Column('interaction_count', sa.Integer(), nullable=True),
        sa.Column('effectiveness_score', sa.Float(), nullable=True),
        sa.Column('adaptation_level', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_interaction', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_profile_id'], ['user_profiles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_personal_agents_agent_id'), 'personal_agents', ['agent_id'], unique=True)
    op.create_index(op.f('ix_personal_agents_id'), 'personal_agents', ['id'], unique=False)

    # Create agent_interactions table
    op.create_table('agent_interactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.String(length=100), nullable=False),
        sa.Column('interaction_id', sa.String(length=100), nullable=False),
        sa.Column('user_message', sa.Text(), nullable=False),
        sa.Column('agent_response', sa.Text(), nullable=False),
        sa.Column('context_used', sa.JSON(), nullable=True),
        sa.Column('personalization_applied', sa.JSON(), nullable=True),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('user_satisfaction', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['personal_agents.agent_id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_interactions_id'), 'agent_interactions', ['id'], unique=False)
    op.create_index(op.f('ix_agent_interactions_interaction_id'), 'agent_interactions', ['interaction_id'], unique=True)

    # Create onboarding_sessions table
    op.create_table('onboarding_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=100), nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('current_step', sa.String(length=50), nullable=False),
        sa.Column('estimated_completion', sa.Float(), nullable=True),
        sa.Column('personalization_score', sa.Float(), nullable=True),
        sa.Column('collected_data', sa.JSON(), nullable=True),
        sa.Column('detected_preferences', sa.JSON(), nullable=True),
        sa.Column('conversation_history', sa.JSON(), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=True),
        sa.Column('completion_duration_seconds', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_onboarding_sessions_id'), 'onboarding_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_onboarding_sessions_session_id'), 'onboarding_sessions', ['session_id'], unique=True)

    # Create external_integrations table
    op.create_table('external_integrations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('service_type', service_type_enum, nullable=False),
        sa.Column('status', integration_status_enum, nullable=True),
        sa.Column('access_token_hash', sa.String(length=255), nullable=True),
        sa.Column('refresh_token_hash', sa.String(length=255), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('permissions', sa.JSON(), nullable=True),
        sa.Column('integration_metadata', sa.JSON(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sync_frequency_minutes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_external_integrations_id'), 'external_integrations', ['id'], unique=False)

    # Create synced_external_data table
    op.create_table('synced_external_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('integration_id', sa.Integer(), nullable=False),
        sa.Column('data_type', sa.String(length=100), nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=True),
        sa.Column('data_content', sa.JSON(), nullable=False),
        sa.Column('sync_version', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('external_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['integration_id'], ['external_integrations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_synced_external_data_id'), 'synced_external_data', ['id'], unique=False)

    # Set default values for existing columns
    op.alter_column('user_profiles', 'basic_info', server_default=sa.text("'{}'"))
    op.alter_column('user_profiles', 'topic_interests', server_default=sa.text("'{}'"))
    op.alter_column('user_profiles', 'skill_levels', server_default=sa.text("'{}'"))
    op.alter_column('user_profiles', 'communication_preferences', server_default=sa.text("'{}'"))
    op.alter_column('user_profiles', 'preferred_explanation_style', server_default=sa.text("'balanced'"))
    op.alter_column('user_profiles', 'activity_patterns', server_default=sa.text("'{}'"))
    op.alter_column('user_profiles', 'learning_progress', server_default=sa.text("'{}'"))
    op.alter_column('user_profiles', 'learning_velocity', server_default=sa.text("0.5"))
    op.alter_column('user_profiles', 'profile_completeness', server_default=sa.text("0.0"))
    op.alter_column('user_profiles', 'total_interactions', server_default=sa.text("0"))

    op.alter_column('learning_patterns', 'confidence', server_default=sa.text("0.0"))
    op.alter_column('learning_patterns', 'frequency', server_default=sa.text("1"))

    op.alter_column('personal_agents', 'personality_config', server_default=sa.text("'{}'"))
    op.alter_column('personal_agents', 'response_templates', server_default=sa.text("'{}'"))
    op.alter_column('personal_agents', 'specialized_prompts', server_default=sa.text("'{}'"))
    op.alter_column('personal_agents', 'learned_preferences', server_default=sa.text("'{}'"))
    op.alter_column('personal_agents', 'conversation_memory', server_default=sa.text("'[]'"))
    op.alter_column('personal_agents', 'interaction_count', server_default=sa.text("0"))
    op.alter_column('personal_agents', 'effectiveness_score', server_default=sa.text("0.5"))
    op.alter_column('personal_agents', 'adaptation_level', server_default=sa.text("0"))

    op.alter_column('agent_interactions', 'context_used', server_default=sa.text("'{}'"))
    op.alter_column('agent_interactions', 'personalization_applied', server_default=sa.text("'{}'"))

    op.alter_column('onboarding_sessions', 'estimated_completion', server_default=sa.text("0.0"))
    op.alter_column('onboarding_sessions', 'personalization_score', server_default=sa.text("0.0"))
    op.alter_column('onboarding_sessions', 'collected_data', server_default=sa.text("'{}'"))
    op.alter_column('onboarding_sessions', 'detected_preferences', server_default=sa.text("'{}'"))
    op.alter_column('onboarding_sessions', 'conversation_history', server_default=sa.text("'[]'"))
    op.alter_column('onboarding_sessions', 'is_completed', server_default=sa.text("false"))

    op.alter_column('external_integrations', 'status', server_default=sa.text("'disconnected'"))
    op.alter_column('external_integrations', 'permissions', server_default=sa.text("'[]'"))
    op.alter_column('external_integrations', 'integration_metadata', server_default=sa.text("'{}'"))
    op.alter_column('external_integrations', 'sync_frequency_minutes', server_default=sa.text("60"))

    op.alter_column('synced_external_data', 'sync_version', server_default=sa.text("1"))
    op.alter_column('synced_external_data', 'is_active', server_default=sa.text("true"))


def downgrade():
    # Drop tables in reverse order
    op.drop_table('synced_external_data')
    op.drop_table('external_integrations')
    op.drop_table('onboarding_sessions')
    op.drop_table('agent_interactions')
    op.drop_table('personal_agents')
    op.drop_table('learning_patterns')
    op.drop_table('user_profiles')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS servicetype')
    op.execute('DROP TYPE IF EXISTS integrationstatus')
    op.execute('DROP TYPE IF EXISTS specialization')
    op.execute('DROP TYPE IF EXISTS agenttype')