"""
The migrations must actually produce the schema the models describe.

This is the test I most wanted after Alembic's autogenerate SILENTLY MISSED the
new 'SUBTASK' enum value — it emits no warning, the migration looks clean, and
the failure only surfaces at runtime when an insert blows up.

Every other test in this suite builds its schema with create_all() from the
models, so none of them would ever notice that the migrations disagree.
"""
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from app.config import settings
from app.database import Base
from app import models  # noqa: F401 — registers every table on Base.metadata

MIGRATION_DB = "qtech_resolver_migrations"
MIGRATION_URL = settings.DATABASE_URL.rsplit("/", 1)[0] + f"/{MIGRATION_DB}"


@pytest.fixture(scope="module")
def migrated_engine():
    """A scratch database built ONLY by running the migrations — never create_all."""
    admin_url = settings.DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATION_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{MIGRATION_DB}"'))
    admin.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", MIGRATION_URL.replace("%", "%%"))
    command.upgrade(cfg, "head")

    engine = create_engine(MIGRATION_URL)
    yield engine
    engine.dispose()

    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATION_DB}"'))
    admin.dispose()


def test_migrations_run_from_scratch(migrated_engine):
    """`alembic upgrade head` on an empty database must not blow up.

    This alone would have caught the sla_policies migration re-declaring the
    'ticketpriority' enum that already existed ("type already exists").
    """
    with migrated_engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }

    expected = set(Base.metadata.tables) | {"alembic_version"}
    missing = expected - tables
    assert not missing, f"migrations did not create: {sorted(missing)}"


def test_migrations_match_the_models(migrated_engine):
    """No drift: the migrated schema and the models must describe the same thing.

    If this fails, someone changed a model without generating a migration — or
    generated one that autogenerate got wrong.
    """
    with migrated_engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)

    assert not diff, (
        "The migrated schema does not match the models. Run:\n"
        "    python -m alembic revision --autogenerate -m '<what changed>'\n"
        f"Differences: {diff}"
    )


def test_enum_values_are_present_in_the_database(migrated_engine):
    """Autogenerate does NOT diff enum values. A new one has to be added by hand
    inside an autocommit_block, and nothing warns you when you forget."""
    with migrated_engine.connect() as conn:
        def values(enum_name):
            return {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum "
                        "WHERE enumtypid = CAST(:n AS regtype)"
                    ),
                    {"n": enum_name},
                )
            }

        # Compare what the DB has against what the Python enum declares.
        for enum_cls, pg_name in [
            (models.TicketType, "tickettype"),
            (models.TicketStatus, "ticketstatus"),
            (models.TicketPriority, "ticketpriority"),
            (models.UserRole, "userrole"),
            (models.SprintState, "sprintstate"),
        ]:
            in_db = values(pg_name)
            in_code = {member.name for member in enum_cls}
            missing = in_code - in_db
            assert not missing, (
                f"{pg_name}: the model declares {sorted(missing)} but the database "
                "doesn't have them. Add them in a migration with:\n"
                "    with op.get_context().autocommit_block():\n"
                f"        op.execute(\"ALTER TYPE {pg_name} ADD VALUE IF NOT EXISTS '...'\")"
            )
