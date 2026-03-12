"""fix: add full_name and bio to users, change priority to string in agenda_items

Revision ID: a49a4d68a042
Revises: 466239181fed
Create Date: 2026-03-11 18:09:44.728564

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a49a4d68a042'
down_revision: Union[str, Sequence[str], None] = '466239181fed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Añadir columnas a la tabla users si no existen
    # Nota: full_name podría ya existir en el modelo pero no en la DB real según los logs
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(100)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT")
    
    # Cambiar tipo de columna priority en agenda_items de Integer a String
    # Primero convertimos a texto para no perder datos si los hubiera
    op.execute("ALTER TABLE agenda_items ALTER COLUMN priority TYPE VARCHAR(20) USING priority::VARCHAR")


def downgrade() -> None:
    """Downgrade schema."""
    # Revertir cambios (bio y full_name se quedan por seguridad o se eliminan)
    # op.drop_column('users', 'bio')
    
    # Intentar revertir priority a Integer (solo si son números válidos)
    op.execute("ALTER TABLE agenda_items ALTER COLUMN priority TYPE INTEGER USING (CASE WHEN priority ~ '^[0-9]+$' THEN priority::INTEGER ELSE NULL END)")
