"""Fix model inconsistencies

Revision ID: fix_inconsistencies_001
Revises: 7f84d78abd7a
Create Date: 2024-10-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'fix_inconsistencies_001'
down_revision = '7f84d78abd7a'
branch_labels = None
depends_on = None

def upgrade():
    # Fix grok_model -> gpt_model inconsistency
    op.alter_column('plans', 'grok_model', new_column_name='gpt_model')
    
    # Add missing columns to plans table
    op.add_column('plans', sa.Column('max_live_search', sa.Integer(), nullable=True, default=3))
    op.add_column('plans', sa.Column('max_voice_minutes', sa.Integer(), nullable=True, default=10))
    op.add_column('plans', sa.Column('max_document_size_mb', sa.Integer(), nullable=True, default=10))
    
    # Add demo tracking columns to users table
    op.add_column('users', sa.Column('demo_count', sa.Integer(), nullable=True, default=0))
    op.add_column('users', sa.Column('last_demo_date', sa.DateTime(), nullable=True))
    
    # Create indexes for better performance
    op.create_index('idx_users_demo_until', 'users', ['demo_until'])
    op.create_index('idx_users_plan_id', 'users', ['plan_id'])
    op.create_index('idx_plans_name', 'plans', ['name'])
    
    # Update existing demo plan
    op.execute("""
        UPDATE plans 
        SET 
            max_live_search = 1,
            max_voice_minutes = 2,
            max_document_size_mb = 5
        WHERE name = 'demo'
    """)
    
    # Update existing normal plan
    op.execute("""
        UPDATE plans 
        SET 
            max_live_search = 5,
            max_voice_minutes = 30,
            max_document_size_mb = 25
        WHERE name = 'normal'
    """)
    
    # Update existing pro plan
    op.execute("""
        UPDATE plans 
        SET 
            max_live_search = 20,
            max_voice_minutes = 120,
            max_document_size_mb = 100
        WHERE name = 'pro'
    """)

def downgrade():
    # Remove added columns
    op.drop_column('users', 'last_demo_date')
    op.drop_column('users', 'demo_count')
    op.drop_column('plans', 'max_document_size_mb')
    op.drop_column('plans', 'max_voice_minutes')
    op.drop_column('plans', 'max_live_search')
    
    # Drop indexes
    op.drop_index('idx_plans_name')
    op.drop_index('idx_users_plan_id')
    op.drop_index('idx_users_demo_until')
    
    # Revert column name
    op.alter_column('plans', 'gpt_model', new_column_name='grok_model')