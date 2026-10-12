"""Alembic environment. Migrations run as a superuser connection (extensions and roles need it);
each SQL file switches to daydor_schema_owner itself so objects are owned by a non-superuser."""
from alembic import context
from sqlalchemy import create_engine, pool

from daydor.config import database_url

config = context.config


def run_migrations_online() -> None:
    url = config.attributes.get("database_url") or database_url()
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
