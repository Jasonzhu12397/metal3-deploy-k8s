from collections.abc import AsyncGenerator
import enum
import json
import logging

from sqlalchemy import Enum as sa_Enum, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

# Importing app.models (not just app.models.base) registers every model on
# Base.metadata before create_all() runs below -- see models/__init__.py
# for why this needs to be explicit rather than relying on some router
# happening to import each model first.
import app.models  # noqa: F401
from app.models.base import Base

settings = get_settings()
logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _ddl_literal_for_default(column) -> str | None:
    """Best-effort: turn a column's Python-side `default=` into a literal
    usable in an ALTER TABLE ... DEFAULT clause, so adding a NOT NULL
    column to a table that already has rows doesn't fail (Postgres
    requires either NULL-able or a DEFAULT when the table isn't empty).
    Returns None if there's no default to work with, or it's a kind this
    can't safely turn into a literal (e.g. a UUID/callable-per-row
    default like uuid.uuid4) -- callers should fall back to adding the
    column as nullable in that case rather than guessing.
    """
    if column.default is None or not column.default.is_scalar and not column.default.is_callable:
        return None

    if column.default.is_scalar:
        value = column.default.arg
    else:
        # dict/list-style defaults (`default=dict`, `default=list`) are
        # callables that take no per-row context -- safe to call once
        # here since every existing row gets the same backfilled value.
        try:
            value = column.default.arg(None)
        except TypeError:
            return None

    if isinstance(value, enum.Enum):
        value = value.value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return "'" + json.dumps(value).replace("'", "''") + "'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


async def _add_missing_columns() -> None:
    """create_all() only creates tables that don't exist yet -- it never
    ALTERs an existing table when a model gains a new column (this is
    documented SQLAlchemy behavior, not a bug in create_all). Every
    column added to an existing model since this project's first release
    (encrypted_bmc_password/bmc_username, then gpu_model/gpu_count/
    gpu_memory_gb) hit exactly this gap on any already-running database:
    the code expects the column, Postgres doesn't have it, every query
    500s with UndefinedColumnError.

    This is deliberately NOT a real migration system (no Alembic, no
    migration history, no down-migrations, no support for renames/drops/
    type changes) -- it only handles the one case that's actually
    happened so far and is easy to keep happening: a new nullable-or-
    safely-defaulted column on an existing table. If this project ever
    needs a genuine schema change (rename, drop, NOT NULL without a safe
    default, data backfill logic), that needs real Alembic migrations,
    not an extension of this function.
    """
    async with engine.begin() as conn:
        def _sync_add_missing(sync_conn):
            inspector = inspect(sync_conn)
            existing_tables = set(inspector.get_table_names())

            for table in Base.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue  # create_all() already created this one fully, nothing to backfill

                existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name in existing_columns:
                        continue

                    col_type = column.type.compile(dialect=sync_conn.dialect)
                    default_literal = _ddl_literal_for_default(column)

                    if not column.nullable and default_literal is None:
                        # Can't safely add NOT NULL to a possibly-non-empty
                        # table without a default -- add it nullable
                        # instead of crashing startup. Not fully correct
                        # (the model claims NOT NULL, the DB won't enforce
                        # it for old rows), but a running app beats a
                        # crash-looping one, and this situation shouldn't
                        # arise as long as new required columns keep
                        # getting a real Python-side default like every
                        # one so far has.
                        logger.warning(
                            "Adding %s.%s as NULLABLE despite the model marking it NOT NULL -- "
                            "no default value was available to backfill existing rows safely.",
                            table.name,
                            column.name,
                        )
                        ddl = f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {col_type}'
                    else:
                        not_null_clause = " NOT NULL" if not column.nullable else ""
                        default_clause = f" DEFAULT {default_literal}" if default_literal is not None else ""
                        ddl = f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {col_type}{default_clause}{not_null_clause}'

                    logger.warning("Auto-migrating: %s", ddl)
                    sync_conn.execute(text(ddl))

        await conn.run_sync(_sync_add_missing)


async def _add_missing_enum_values() -> None:
    """The enum-type sibling of _add_missing_columns' problem: SQLAlchemy's
    Enum() column type creates a real, native Postgres ENUM type by
    default (confirmed: native_enum=True unless a column explicitly opts
    out, which none in this project's models do). Adding a new member to
    a Python enum -- e.g. InfrastructureProvider gaining DOCKER for CAPD
    support -- doesn't touch that native type on an already-running
    database. Postgres then rejects any INSERT/UPDATE using the new
    value with "invalid input value for enum ...", the enum-typed
    equivalent of _add_missing_columns' UndefinedColumnError.

    SQLite (used throughout this project's own test suite) has no
    concept of a native enum type -- Enum columns are just a VARCHAR with
    an app-level CHECK, which already accepts any string the Python enum
    validates, so this is a genuine no-op there and this whole function
    is a no-op except when settings.DATABASE_URL is postgres.

    Not verified against a real Postgres instance (none installable in
    the environment this was developed in -- see this project's other
    "verified against SQLite, reasoned through for Postgres" notes for
    the same limitation elsewhere) -- reasoned through against Postgres's
    documented ALTER TYPE ... ADD VALUE behavior instead: safe to run
    inside the same transaction create_all()/_add_missing_columns()
    already use, since the constraint is only that the new value can't
    be *used* within the same transaction it was added in, and nothing
    here does that.
    """
    if not engine.url.get_backend_name().startswith("postgres"):
        return

    async with engine.begin() as conn:
        def _sync_add_missing_enum_values(sync_conn):
            for table in Base.metadata.sorted_tables:
                for column in table.columns:
                    if not isinstance(column.type, sa_Enum) or not column.type.native_enum:
                        continue
                    enum_type_name = column.type.name
                    if not enum_type_name or column.type.enum_class is None:
                        continue

                    existing_values = {
                        row[0]
                        for row in sync_conn.execute(
                            text(
                                "SELECT enumlabel FROM pg_enum "
                                "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                                "WHERE pg_type.typname = :type_name"
                            ),
                            {"type_name": enum_type_name},
                        )
                    }
                    if not existing_values:
                        continue  # type doesn't exist yet -- create_all() will have made it with every current member already

                    for member in column.type.enum_class:
                        if member.name not in existing_values:
                            logger.warning(
                                "Auto-migrating: ALTER TYPE %s ADD VALUE '%s'", enum_type_name, member.name
                            )
                            # ADD VALUE IF NOT EXISTS needs PG >= 12; every
                            # supported Postgres version at this project's
                            # writing is newer than that.
                            sync_conn.execute(
                                text(f"ALTER TYPE {enum_type_name} ADD VALUE IF NOT EXISTS '{member.name}'")
                            )

        await conn.run_sync(_sync_add_missing_enum_values)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _add_missing_columns()
    await _add_missing_enum_values()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
