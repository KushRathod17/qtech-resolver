from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Pull the URL and the models from the app itself, so the database is configured
# in exactly one place (backend/.env) and the schema is defined in exactly one
# place (app/models.py). alembic.ini deliberately carries no URL — a second copy
# of the connection string is a second thing to get out of sync.
from app.config import settings
from app.database import Base
from app import models  # noqa: F401 — imported for the side effect of registering every table

config = context.config

# Default to the app's own DATABASE_URL, but let a caller override it — the
# migration tests point this at a throwaway database, and a deploy points it at
# staging. Unconditionally overwriting here made it impossible to target any
# database except the one in .env.
#
# '%' is the config parser's interpolation character, so any %-escape in a
# URL-encoded password has to be doubled before it goes into the ini layer.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # catch column type changes, not just add/drop
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
