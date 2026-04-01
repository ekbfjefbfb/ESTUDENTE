"""Create plans table for Nhost PostgreSQL

Revision ID: 20260331_create_plans_table
Revises: 20260331_add_users_missing_columns
Create Date: 2026-03-31

Crea la tabla de planes de suscripción necesaria para la relación
plan_id en la tabla users. Incluye planes por defecto.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260331_create_plans_table'
down_revision = '20260331_add_users_missing_columns'
branch_labels = None
depends_on = None


def upgrade():
    # =============================================
    # CREAR TABLA PLANS
    # =============================================
    
    op.create_table(
        'plans',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(50), nullable=False, unique=True),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('requests_per_month', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('max_file_size_mb', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('features', postgresql.JSONB(), nullable=True, server_default='[]'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('is_demo', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('sort_order', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Índices para plans
    op.create_index('ix_plans_name', 'plans', ['name'], unique=True)
    op.create_index('ix_plans_is_active', 'plans', ['is_active'])
    
    # =============================================
    # AGREGAR FOREIGN KEY A USERS
    # =============================================
    
    # Agregar constraint de foreign key para plan_id
    op.create_foreign_key(
        'fk_users_plan_id',
        'users', 'plans',
        ['plan_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # =============================================
    # INSERTAR PLANES POR DEFECTO
    # =============================================
    
    op.execute("""
        INSERT INTO plans (name, display_name, description, price, requests_per_month, max_file_size_mb, features, is_demo, sort_order) 
        VALUES 
        ('demo', 'Demo', 'Plan de prueba gratuito', 0, 50, 1, '["basic_chat"]', TRUE, 1),
        ('normal', 'Normal', 'Plan básico para usuarios individuales', 9.99, 1000, 10, '["basic_chat", "file_upload", "vision"]', FALSE, 2),
        ('pro', 'Pro', 'Plan profesional con funciones avanzadas', 29.99, 5000, 50, '["basic_chat", "file_upload", "vision", "advanced_agents", "priority_support"]', FALSE, 3),
        ('enterprise', 'Enterprise', 'Plan empresarial con soporte dedicado', 99.99, 50000, 100, '["all_features", "dedicated_support", "custom_agents", "analytics"]', FALSE, 4)
        ON CONFLICT (name) DO NOTHING;
    """)


def downgrade():
    # Eliminar foreign key primero
    op.drop_constraint('fk_users_plan_id', 'users', type_='foreignkey')
    
    # Eliminar índices
    op.drop_index('ix_plans_is_active', table_name='plans')
    op.drop_index('ix_plans_name', table_name='plans')
    
    # Eliminar tabla
    op.drop_table('plans')
