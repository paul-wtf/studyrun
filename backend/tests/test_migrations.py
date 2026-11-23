import io
import os
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from studyrun.models.db import Base

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def _config(buffer: io.StringIO | None = None) -> Config:
    config = Config(output_buffer=buffer)
    config.set_main_option("script_location", str(MIGRATIONS))
    return config


def _chain() -> list[tuple[str, str]]:
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1, "the migrations have more than one head"
    steps = []
    for rev in reversed(list(script.walk_revisions("base", "heads"))):
        down = rev.down_revision
        assert down is None or isinstance(down, str), f"{rev.revision} is a merge"
        steps.append((down or "base", rev.revision))
    return steps


def _sql(direction: str, revisions: str) -> str:
    # Offline mode prints the DDL so it can run inside a scratch schema; online
    # mode has no way to pick a schema.
    buffer = io.StringIO()
    getattr(command, direction)(_config(buffer), revisions, sql=True)
    return buffer.getvalue()


@pytest.fixture
async def scratch(test_database):
    url = make_url(test_database)
    schema = f"migration_test_{os.getpid()}"
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database=url.database,
    )
    await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    await conn.execute(f'CREATE SCHEMA "{schema}"')
    await conn.execute(f'SET search_path TO "{schema}"')
    try:
        yield conn, schema
    finally:
        await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await conn.close()


async def _schema(conn, schema: str) -> dict[str, list]:
    columns = await conn.fetch(
        "SELECT table_name, column_name, data_type, character_maximum_length, is_nullable, "
        "column_default FROM information_schema.columns "
        "WHERE table_schema = $1 AND table_name <> 'alembic_version' ORDER BY 1, 2",
        schema,
    )
    indexes = await conn.fetch(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = $1 AND tablename <> 'alembic_version' ORDER BY 1",
        schema,
    )
    constraints = await conn.fetch(
        "SELECT c.conrelid::regclass::text, c.conname, pg_get_constraintdef(c.oid) "
        "FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
        "WHERE n.nspname = $1 AND c.conrelid::regclass::text <> 'alembic_version' ORDER BY 1, 2",
        schema,
    )
    return {
        "columns": [tuple(r) for r in columns],
        "indexes": [tuple(r) for r in indexes],
        "constraints": [tuple(r) for r in constraints],
    }


async def test_every_migration_downgrades_and_upgrades_again(scratch):
    conn, schema = scratch
    for down, rev in _chain():
        before = await _schema(conn, schema)
        upgrade = _sql("upgrade", f"{down}:{rev}" if down != "base" else rev)
        await conn.execute(upgrade)
        after = await _schema(conn, schema)

        await conn.execute(_sql("downgrade", f"{rev}:{down}"))
        assert await _schema(conn, schema) == before, f"downgrade of {rev}"
        if down == "base":
            # A downgrade to base empties alembic_version but keeps the table.
            await conn.execute("DROP TABLE alembic_version")

        await conn.execute(upgrade)
        assert await _schema(conn, schema) == after, f"second upgrade to {rev}"
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == rev


async def test_upgrade_matches_metadata(scratch, test_database):
    conn, schema = scratch
    await conn.execute(_sql("upgrade", "head"))

    engine = create_async_engine(
        test_database, connect_args={"server_settings": {"search_path": schema}}
    )

    def diff(sync_conn):
        context = MigrationContext.configure(
            sync_conn,
            opts={
                "compare_type": True,
                "compare_server_default": True,
                "include_object": lambda obj, name, type_, reflected, compare_to: (
                    name != "alembic_version"
                ),
            },
        )
        return compare_metadata(context, Base.metadata)

    try:
        async with engine.connect() as sync_side:
            assert await sync_side.run_sync(diff) == []
    finally:
        await engine.dispose()
