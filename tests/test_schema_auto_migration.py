"""
Covers app.core.db's "add missing columns" auto-migration -- the thing
that stops every future "I added a column to an existing model" from
crash-looping anyone's already-running Postgres with UndefinedColumnError
(exactly what happened in production: gpu_model/gpu_count/gpu_memory_gb
got added to HardwareAsset, and any database whose hardware_assets table
already existed never got those columns, since SQLAlchemy's
Base.metadata.create_all() only creates missing TABLES, never ALTERs
existing ones).

This isn't a real migration system (no Alembic, no history, no down-
migrations) -- see app/core/db.py's _add_missing_columns docstring for
what it deliberately does and doesn't handle. These tests simulate
exactly the failure mode that actually happened: hand-build an
old-schema table missing the newer columns, seed it with a row (real
production data doesn't disappear when a server restarts), then run the
real init_db() and confirm both that the columns appear AND that the
pre-existing row's data survives with a sane backfilled value rather
than either crashing or silently losing data.
"""
import asyncio
import os
import sys
import tempfile

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


OLD_HARDWARE_ASSETS_SCHEMA = """
    CREATE TABLE hardware_assets (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        serial_number VARCHAR(255),
        vendor VARCHAR(255),
        model VARCHAR(255),
        status VARCHAR(32) NOT NULL DEFAULT 'DISCOVERED',
        cpu_model VARCHAR(255),
        cpu_sockets INTEGER NOT NULL DEFAULT 2,
        cpu_cores_per_socket INTEGER NOT NULL DEFAULT 32,
        cpu_threads_per_core INTEGER NOT NULL DEFAULT 2,
        memory_gb INTEGER NOT NULL DEFAULT 0,
        nics JSON NOT NULL DEFAULT '[]',
        disks JSON NOT NULL DEFAULT '[]',
        bmc_address VARCHAR(500),
        boot_mac_address VARCHAR(32),
        bmc_username VARCHAR(255),
        encrypted_bmc_password VARCHAR(512),
        node_pool_name VARCHAR(128),
        cluster_id VARCHAR(36),
        created_at DATETIME,
        updated_at DATETIME
    )
"""


async def _seed_old_schema_db(db_path: str) -> None:
    """Builds a hardware_assets table matching this project's schema
    from BEFORE the GPU columns existed, with one real row in it --
    simulating an already-running deployment's database exactly as it
    would look at the moment someone deploys the GPU-support update."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.execute(sa.text(OLD_HARDWARE_ASSETS_SCHEMA))
        await conn.execute(
            sa.text(
                """
                INSERT INTO hardware_assets
                    (id, name, status, cpu_sockets, cpu_cores_per_socket, cpu_threads_per_core, memory_gb, nics, disks)
                VALUES
                    ('11111111-1111-1111-1111-111111111111', 'old-existing-server', 'AVAILABLE', 2, 32, 2, 256, '[]', '[]')
                """
            )
        )
    await engine.dispose()


@pytest.fixture
def old_schema_db_path(tmp_path):
    db_path = str(tmp_path / "old_schema_test.db")
    asyncio.run(_seed_old_schema_db(db_path))
    return db_path


def test_missing_columns_get_added_and_existing_row_survives(old_schema_db_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{old_schema_db_path}")

    # app.core.config/db cache settings and the engine at import time --
    # force a clean re-import so this test's DATABASE_URL actually takes
    # effect rather than reusing whatever a previously-imported test
    # already set up.
    for mod in list(sys.modules):
        if mod.startswith("app.core.config") or mod.startswith("app.core.db"):
            del sys.modules[mod]
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.db import init_db, AsyncSessionLocal
    from app.models.hardware_asset import HardwareAsset
    from sqlalchemy import select

    async def _run():
        await init_db()
        async with AsyncSessionLocal() as session:
            result = await session.scalars(select(HardwareAsset).order_by(HardwareAsset.name))
            return result.all()

    assets = asyncio.run(_run())

    assert len(assets) == 1, "the pre-existing row must survive the migration, not disappear"
    asset = assets[0]
    assert asset.name == "old-existing-server"
    assert asset.status.value == "available"
    # the actual bug: these three columns didn't exist at all before
    assert asset.gpu_model is None
    assert asset.gpu_count == 0, "NOT NULL column with no explicit value must get its model default backfilled, not crash"
    assert asset.gpu_memory_gb is None
    assert asset.has_gpu is False


def test_running_init_db_twice_is_a_no_op_the_second_time(old_schema_db_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{old_schema_db_path}")
    for mod in list(sys.modules):
        if mod.startswith("app.core.config") or mod.startswith("app.core.db"):
            del sys.modules[mod]
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.db import init_db

    async def _run_twice():
        await init_db()
        await init_db()  # must not raise "column already exists" or similar

    asyncio.run(_run_twice())  # the assertion here is simply that this doesn't raise


def test_enum_value_migration_is_a_safe_noop_on_sqlite(old_schema_db_path, monkeypatch):
    """SQLite has no native enum type -- _add_missing_enum_values must
    detect that (via the DATABASE_URL's backend name) and do nothing,
    not attempt Postgres-only catalog queries against a database that
    doesn't have pg_enum/pg_type at all."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{old_schema_db_path}")
    for mod in list(sys.modules):
        if mod.startswith("app.core.config") or mod.startswith("app.core.db"):
            del sys.modules[mod]
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.db import _add_missing_enum_values, engine

    assert engine.url.get_backend_name() == "sqlite"
    asyncio.run(_add_missing_enum_values())  # must not raise
