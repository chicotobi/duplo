"""Alembic environment.

Reads the database URL from the same place the Flask app does so that
``alembic upgrade head`` works without duplicating connection configuration.
"""

from __future__ import with_statement

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from duplo import _build_db_uri


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", _build_db_uri())

# We use raw SQL via repositories rather than ORM models, so there is no
# MetaData object to autogenerate against. Migrations are written by hand.
target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # When invoked programmatically (e.g. from tests) the caller may pass an
    # existing connection via ``config.attributes["connection"]`` so that an
    # in-memory SQLite database is shared with the application.
    existing = config.attributes.get("connection", None)
    if existing is not None:
        context.configure(
            connection=existing,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
