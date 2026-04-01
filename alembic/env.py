import os
import logging
import sqlalchemy as sa
import socket
from urllib.parse import urlparse

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import text

from alembic import context
from sqlalchemy.schema import DropTable, DropConstraint, DropIndex
from sqlalchemy.ext.compiler import compiles

@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs):
    return "DROP TABLE IF EXISTS " + compiler.preparer.format_table(element.element) + " CASCADE"

@compiles(DropConstraint, "postgresql")
def _compile_drop_constraint(element, compiler, **kwargs):
    return "ALTER TABLE " + compiler.preparer.format_table(element.element.table) + (" DROP CONSTRAINT IF EXISTS " if hasattr(element.element, "name") and element.element.name else " DROP CONSTRAINT ") + compiler.preparer.format_constraint(element.element) + " CASCADE"

@compiles(DropIndex, "postgresql")
def _compile_drop_index(element, compiler, **kwargs):
    return "DROP INDEX IF EXISTS " + compiler.preparer.quote(element.element.name) + " CASCADE"

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

db_url = (os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL") or "").strip()
if not db_url:
    raise ValueError("DATABASE_URL or SQLALCHEMY_DATABASE_URL environment variable is not set")

# Asegurar que el host sea resoluble y el esquema sea correcto para Alembic (psycopg2)
if db_url.startswith("postgresql+asyncpg://"):
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

db_url = db_url.replace("%", "%%")
config.set_main_option("sqlalchemy.url", db_url)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
from models.models import Base  # importa tu Base donde están todos tus modelos

# Importar modelos para que Alembic los detecte en autogenerate
from models import study_groups_models  # 🎓 Study Groups models

target_metadata = Base.metadata


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    # context.configure(
    #     url=url,
    #     target_metadata=target_metadata,
    #     literal_binds=True,
    #     dialect_opts={"paramstyle": "named"},
    # )
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_kwargs={"version_num_type": sa.VARCHAR(255)}
    )

    with context.begin_transaction():
        context.run_migrations()


def _validate_db_dns() -> bool:
    """Valida si el host de DATABASE_URL es resoluble"""
    db_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL")
    if not db_url:
        return True
    try:
        if "sqlite" in db_url:
            return True
        parsed = urlparse(db_url)
        host = parsed.hostname
        if host:
            socket.gethostbyname(host)
            return True
    except Exception as e:
        logger.warning(f"⚠️ DNS validation failed for host: {e}")
    return False

def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    if not _validate_db_dns():
        db_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL")
        logger.error(f"❌ DATABASE HOST NOT RESOLVABLE: {db_url}")
        # En modo online, si no hay DNS, no podemos proceder
        raise RuntimeError(f"Could not resolve database host. Check your DATABASE_URL.")

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # 1. Ensanchar la columna de versión ANTES de iniciar Alembic
    # Usamos una conexión independiente para asegurar que el COMMIT sea inmediato
    with connectable.connect() as connection:
        try:
            # Forzar el ensanchamiento si la tabla existe
            connection.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version') THEN
                        ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255);
                    END IF;
                END $$;
            """))
            connection.commit()
            logger.info("✅ alembic_version.version_num widened to 255")
        except Exception as e:
            logger.warning(f"⚠️ Could not widen alembic_version: {e}")
            pass

    # with connectable.connect() as connection:
    #     context.configure(
    #         connection=connection, target_metadata=target_metadata
    #     )
    #
    #     with context.begin_transaction():
    #         context.run_migrations()
    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            version_table_kwargs={"version_num_type": sa.VARCHAR(255)}
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
