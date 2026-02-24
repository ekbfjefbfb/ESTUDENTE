"""Add OAuth profile fields for auto-personalization

Revision ID: oauth_profile_001
Revises: 
Create Date: 2025-10-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'oauth_profile_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Agregar columnas OAuth al modelo User
    op.add_column('users', sa.Column('oauth_profile', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('users', sa.Column('profile_picture_url', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('timezone', sa.String(length=50), nullable=True, server_default='UTC'))
    op.add_column('users', sa.Column('preferred_language', sa.String(length=10), nullable=True, server_default='en'))
    op.add_column('users', sa.Column('interests', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('users', sa.Column('oauth_provider', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('oauth_access_token', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('oauth_refresh_token', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('oauth_token_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Remover columnas OAuth
    op.drop_column('users', 'oauth_token_expires_at')
    op.drop_column('users', 'oauth_refresh_token')
    op.drop_column('users', 'oauth_access_token')
    op.drop_column('users', 'oauth_provider')
    op.drop_column('users', 'interests')
    op.drop_column('users', 'preferred_language')
    op.drop_column('users', 'timezone')
    op.drop_column('users', 'profile_picture_url')
    op.drop_column('users', 'oauth_profile')
