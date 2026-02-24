from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Integer, Float, Boolean, DateTime, JSON, Text, ForeignKey, func

# ------------------
# Revision identifiers
# ------------------
revision = '20251007_full_models'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # ------------------
    # Tabla: plans
    # ------------------
    op.create_table(
        'plans',
        sa.Column('id', Integer, primary_key=True),
        sa.Column('name', String, nullable=False, unique=True),
        sa.Column('max_messages', Integer, default=1000),
        sa.Column('max_files', Integer, default=50),
        sa.Column('max_images', Integer, default=50),
        sa.Column('demo_requests_per_day', Integer, default=5),
        sa.Column('demo_files', Integer, default=2),
        sa.Column('demo_images', Integer, default=1),
        sa.Column('demo_storage', String, default='100MB'),
        sa.Column('grok_model', String, default='grok-4-fast'),
        sa.Column('image_engine', String, default='stable-diffusion'),
        sa.Column('price', Float, default=0)
    )

    # Insertar planes iniciales
    plans_table = table(
        'plans',
        column('name', String),
        column('max_messages', Integer),
        column('max_files', Integer),
        column('max_images', Integer),
        column('demo_requests_per_day', Integer),
        column('demo_files', Integer),
        column('demo_images', Integer),
        column('demo_storage', String),
        column('grok_model', String),
        column('image_engine', String),
        column('price', Float)
    )
    op.bulk_insert(plans_table, [
        {'name': 'Demo', 'max_messages': 50, 'max_files': 6, 'max_images': 6,
         'demo_requests_per_day': 5, 'demo_files': 3, 'demo_images': 1,
         'demo_storage': '100MB', 'grok_model': 'grok-4-reasoning',
         'image_engine': 'stable-diffusion', 'price': 0},
        {'name': 'Pro', 'max_messages': 1000, 'max_files': 50, 'max_images': 50,
         'demo_requests_per_day': None, 'demo_files': None, 'demo_images': None,
         'demo_storage': None, 'grok_model': 'grok-4-reasoning',
         'image_engine': 'stable-diffusion', 'price': 15},
        {'name': 'Plus', 'max_messages': 5000, 'max_files': 500, 'max_images': 500,
         'demo_requests_per_day': None, 'demo_files': None, 'demo_images': None,
         'demo_storage': None, 'grok_model': 'grok-4-reasoning',
         'image_engine': 'stable-diffusion', 'price': 60},
    ])

    # ------------------
    # Tabla: users
    # ------------------
    op.create_table(
        'users',
        sa.Column('id', Integer, primary_key=True),
        sa.Column('username', String(50), nullable=False, unique=True, index=True),
        sa.Column('email', String(100), nullable=False, unique=True, index=True),
        sa.Column('password', String, nullable=True),
        sa.Column('provider', String, default='local'),
        sa.Column('plan_id', Integer, sa.ForeignKey('plans.id', ondelete='SET NULL'), nullable=True),
        sa.Column('plan_started_at', DateTime(timezone=True), nullable=True),
        sa.Column('plan_ends_at', DateTime(timezone=True), nullable=True),
        sa.Column('is_active', Boolean, default=True),
        sa.Column('created_at', DateTime(timezone=True), server_default=func.now()),
        sa.Column('demo_until', DateTime(timezone=True), nullable=True),
        sa.Column('demo_requests_today', Integer, default=0),
        sa.Column('demo_last_reset', DateTime(timezone=True), nullable=True),
    )

    # ------------------
    # Tabla: subscriptions
    # ------------------
    op.create_table(
        'subscriptions',
        sa.Column('id', Integer, primary_key=True),
        sa.Column('user_id', Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan_id', Integer, sa.ForeignKey('plans.id', ondelete='SET NULL'), nullable=False),
        sa.Column('start_date', DateTime, default=func.now()),
        sa.Column('end_date', DateTime, nullable=True),
        sa.Column('active', Boolean, default=True),
    )

    # ------------------
    # Tabla: payments
    # ------------------
    op.create_table(
        'payments',
        sa.Column('id', Integer, primary_key=True),
        sa.Column('user_id', Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan_id', Integer, sa.ForeignKey('plans.id', ondelete='SET NULL'), nullable=True),
        sa.Column('gateway', String, nullable=False),
        sa.Column('payment_id', String, nullable=False, unique=True),
        sa.Column('amount', Float, nullable=False),
        sa.Column('currency', String(3), nullable=False),
        sa.Column('status', String, default='pending'),
        sa.Column('payment_metadata', JSON, nullable=True),
        sa.Column('created_at', DateTime(timezone=True), server_default=func.now()),
    )

    # ------------------
    # Tabla: conversations
    # ------------------
    op.create_table(
        'conversations',
        sa.Column('id', Integer, primary_key=True),
        sa.Column('user_id', Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message', Text, nullable=False),
        sa.Column('role', String, default='user'),
        sa.Column('created_at', DateTime(timezone=True), server_default=func.now()),
        sa.Column('metadata_extra', JSON, nullable=True),
    )

    # ------------------
    # Tabla: uploaded_files
    # ------------------
    op.create_table(
        'uploaded_files',
        sa.Column('id', Integer, primary_key=True),
        sa.Column('user_id', Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', String, nullable=False),
        sa.Column('file_type', String, nullable=True),
        sa.Column('url', String, nullable=True),
        sa.Column('created_at', DateTime(timezone=True), server_default=func.now()),
    )

    # ------------------
    # Tabla: usage_logs
    # ------------------
    op.create_table(
        'usage_logs',
        sa.Column('id', Integer, primary_key=True),
        sa.Column('user_id', Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', String, nullable=False),
        sa.Column('detail', JSON, nullable=True),
        sa.Column('created_at', DateTime(timezone=True), server_default=func.now()),
        sa.Index('idx_usage_user_created', 'user_id', 'created_at'),
    )

    # ------------------
    # Tabla: media
    # ------------------
    op.create_table(
        'media',
        sa.Column('id', Integer, primary_key=True),
        sa.Column('user_id', Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', String, nullable=False),
        sa.Column('url', String, nullable=False),
        sa.Column('created_at', DateTime(timezone=True), server_default=func.now()),
    )

    # ------------------
    # Tabla: history
    # ------------------
    op.create_table(
        'history',
        sa.Column('id', Integer, primary_key=True),
        sa.Column('user_id', Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', Integer, sa.ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('type', String, nullable=False),
        sa.Column('content', Text, nullable=True),
        sa.Column('response', Text, nullable=True),
        sa.Column('created_at', DateTime(timezone=True), server_default=func.now()),
        sa.Index('idx_history_conv_user', 'conversation_id', 'user_id'),
    )

    # ------------------
    # Tabla: live_search_logs (para live search)
    # ------------------
    op.create_table(
        'live_search_logs',
        sa.Column('id', Integer, primary_key=True),
        sa.Column('user_id', Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('query', Text, nullable=False),
        sa.Column('created_at', DateTime(timezone=True), server_default=func.now()),
    )


def downgrade():
    op.drop_table('live_search_logs')
    op.drop_table('history')
    op.drop_table('media')
    op.drop_table('usage_logs')
    op.drop_table('uploaded_files')
    op.drop_table('conversations')
    op.drop_table('payments')
    op.drop_table('subscriptions')
    op.drop_table('users')
    op.execute("DELETE FROM plans WHERE name IN ('Demo','Pro','Plus')")
    op.drop_table('plans')
