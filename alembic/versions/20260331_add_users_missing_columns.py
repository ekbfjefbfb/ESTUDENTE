"""Add missing columns to users table for Nhost PostgreSQL

Revision ID: 20260331_add_users_missing_columns
Revises: 20260323_add_voice_note_models
Create Date: 2026-03-31

Agrega todas las columnas faltantes a la tabla users:
- subscription_expires_at (crítico - causaba error de INSERT)
- phone_number, phone_verified, phone_verified_at
- full_name, bio
- plan_id, plan_started_at, plan_ends_at
- requests_used_this_month, last_request_reset, last_activity
- demo columns, oauth columns, preferences, etc.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260331_add_users_missing_columns'
down_revision = '20260323_add_voice_note_models'
branch_labels = None
depends_on = None


def upgrade():
    # =============================================
    # COLUMNAS BÁSICAS DE USUARIO
    # =============================================
    
    # phone_number (si no existe)
    op.add_column('users', sa.Column('phone_number', sa.String(20), nullable=True, unique=True))
    op.create_index('ix_users_phone_number', 'users', ['phone_number'], unique=True, postgresql_where=sa.text("phone_number IS NOT NULL"))
    
    # phone_verified (si no existe)
    op.add_column('users', sa.Column('phone_verified', sa.Boolean(), nullable=True, server_default='false'))
    
    # phone_verified_at (si no existe)
    op.add_column('users', sa.Column('phone_verified_at', sa.DateTime(timezone=True), nullable=True))
    
    # full_name (si no existe)
    op.add_column('users', sa.Column('full_name', sa.String(100), nullable=True))
    
    # bio (si no existe)
    op.add_column('users', sa.Column('bio', sa.Text(), nullable=True))
    
    # =============================================
    # COLUMNAS DE PLAN Y SUSCRIPCIÓN (CRÍTICAS)
    # =============================================
    
    # subscription_expires_at - CRÍTICO, causaba el error
    op.add_column('users', sa.Column('subscription_expires_at', sa.DateTime(timezone=True), nullable=True))
    
    # plan_started_at (si no existe)
    op.add_column('users', sa.Column('plan_started_at', sa.DateTime(timezone=True), nullable=True))
    
    # plan_ends_at (si no existe)
    op.add_column('users', sa.Column('plan_ends_at', sa.DateTime(timezone=True), nullable=True))
    
    # requests_used_this_month (si no existe)
    op.add_column('users', sa.Column('requests_used_this_month', sa.Integer(), nullable=True, server_default='0'))
    
    # last_request_reset (si no existe)
    op.add_column('users', sa.Column('last_request_reset', sa.DateTime(timezone=True), nullable=True))
    
    # last_activity (si no existe)
    op.add_column('users', sa.Column('last_activity', sa.DateTime(timezone=True), nullable=True))
    
    # profile_data (si no existe)
    op.add_column('users', sa.Column('profile_data', postgresql.JSONB(), nullable=True, server_default='{}'))
    
    # preferences (si no existe)
    op.add_column('users', sa.Column('preferences', postgresql.JSONB(), nullable=True, server_default='{}'))
    
    # =============================================
    # COLUMNAS DE DEMO/TRIAL
    # =============================================
    
    # demo_until (si no existe)
    op.add_column('users', sa.Column('demo_until', sa.DateTime(timezone=True), nullable=True))
    
    # demo_requests_today (si no existe)
    op.add_column('users', sa.Column('demo_requests_today', sa.Integer(), nullable=True, server_default='0'))
    
    # demo_last_reset (si no existe)
    op.add_column('users', sa.Column('demo_last_reset', sa.DateTime(timezone=True), nullable=True))
    
    # demo_count (si no existe)
    op.add_column('users', sa.Column('demo_count', sa.Integer(), nullable=True, server_default='0'))
    
    # last_demo_date (si no existe)
    op.add_column('users', sa.Column('last_demo_date', sa.DateTime(), nullable=True))
    
    # =============================================
    # COLUMNAS DE OAUTH/PERFIL
    # =============================================
    
    # oauth_profile (si no existe)
    op.add_column('users', sa.Column('oauth_profile', postgresql.JSONB(), nullable=True, server_default='{}'))
    
    # profile_picture_url (si no existe)
    op.add_column('users', sa.Column('profile_picture_url', sa.String(500), nullable=True))
    
    # timezone (si no existe)
    op.add_column('users', sa.Column('timezone', sa.String(50), nullable=True, server_default='UTC'))
    
    # preferred_language (si no existe)
    op.add_column('users', sa.Column('preferred_language', sa.String(10), nullable=True, server_default='en'))
    
    # interests (si no existe)
    op.add_column('users', sa.Column('interests', postgresql.JSONB(), nullable=True, server_default='[]'))
    
    # oauth_provider (si no existe)
    op.add_column('users', sa.Column('oauth_provider', sa.String(20), nullable=True))
    op.create_index('ix_users_oauth_provider', 'users', ['oauth_provider'], postgresql_where=sa.text("oauth_provider IS NOT NULL"))
    
    # oauth_access_token (si no existe)
    op.add_column('users', sa.Column('oauth_access_token', sa.String(500), nullable=True))
    
    # oauth_refresh_token (si no existe)
    op.add_column('users', sa.Column('oauth_refresh_token', sa.String(500), nullable=True))
    
    # oauth_token_expires_at (si no existe)
    op.add_column('users', sa.Column('oauth_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    
    # =============================================
    # COLUMNAS DE ACTUALIZACIÓN
    # =============================================
    
    # updated_at (si no existe)
    op.add_column('users', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    
    # =============================================
    # ÍNDICES ADICIONALES
    # =============================================
    
    # Índice para búsqueda por email (parcial)
    op.create_index('ix_users_email_partial', 'users', ['email'], postgresql_where=sa.text("email IS NOT NULL"))


def downgrade():
    # Remover índices
    op.drop_index('ix_users_email_partial', table_name='users')
    op.drop_index('ix_users_oauth_provider', table_name='users')
    op.drop_index('ix_users_phone_number', table_name='users')
    
    # Remover columnas en orden inverso
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'oauth_token_expires_at')
    op.drop_column('users', 'oauth_refresh_token')
    op.drop_column('users', 'oauth_access_token')
    op.drop_column('users', 'oauth_provider')
    op.drop_column('users', 'interests')
    op.drop_column('users', 'preferred_language')
    op.drop_column('users', 'timezone')
    op.drop_column('users', 'profile_picture_url')
    op.drop_column('users', 'oauth_profile')
    op.drop_column('users', 'last_demo_date')
    op.drop_column('users', 'demo_count')
    op.drop_column('users', 'demo_last_reset')
    op.drop_column('users', 'demo_requests_today')
    op.drop_column('users', 'demo_until')
    op.drop_column('users', 'preferences')
    op.drop_column('users', 'profile_data')
    op.drop_column('users', 'last_activity')
    op.drop_column('users', 'last_request_reset')
    op.drop_column('users', 'requests_used_this_month')
    op.drop_column('users', 'plan_ends_at')
    op.drop_column('users', 'plan_started_at')
    op.drop_column('users', 'subscription_expires_at')
    op.drop_column('users', 'bio')
    op.drop_column('users', 'full_name')
    op.drop_column('users', 'phone_verified_at')
    op.drop_column('users', 'phone_verified')
    op.drop_column('users', 'phone_number')
