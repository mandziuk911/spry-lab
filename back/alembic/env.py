from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import settings
from app.db import DB_CONNECT_ARGS, Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Arbitrary constant: serialises migrations when several containers start at once.
MIGRATION_LOCK_ID = 727_001


def run_migrations_offline() -> None:
    url = settings.sqlalchemy_url.render_as_string(hide_password=False)
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def migrate_connection(connection) -> None:
    # Session-level lock: survives commits; released even after a failed migration.
    connection.execute(text("SELECT pg_advisory_lock(:id)"), {"id": MIGRATION_LOCK_ID})
    connection.commit()
    try:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.rollback()
        connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": MIGRATION_LOCK_ID})
        connection.commit()


def run_migrations_online() -> None:
    # Tests supply a connection restricted to their disposable schema.
    connection = config.attributes.get("connection")
    if connection is not None:
        migrate_connection(connection)
        return
    connectable = create_engine(
        settings.sqlalchemy_url, poolclass=pool.NullPool, connect_args=DB_CONNECT_ARGS
    )
    try:
        with connectable.connect() as connection:
            migrate_connection(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
