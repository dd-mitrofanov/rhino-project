"""
Alembic environment for async SQLAlchemy + asyncpg.
Run from bot/ directory so that app.config and app.db.models import correctly.
"""
import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Ensure bot/ is on sys.path for app imports when running alembic from bot/
_bot_root = Path(__file__).resolve().parent.parent
if str(_bot_root) not in sys.path:
    sys.path.insert(0, str(_bot_root))

from app.config import settings
from app.db.models import Base

config = context.config

if config.config_file_name is not None:
    from logging.config import fileConfig
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_async_url() -> str:
    """Get DATABASE_URL and ensure postgresql+asyncpg:// driver."""
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generate SQL script only)."""
    url = _get_async_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create async engine and run migrations with connection.run_sync."""
    connectable = create_async_engine(
        _get_async_url(),
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g. alembic upgrade from CLI) — safe to use asyncio.run()
        asyncio.run(run_async_migrations())
    else:
        # Already inside an event loop (e.g. init_db from main) — run in a thread
        # since asyncio.run() cannot be called from a running loop
        with ThreadPoolExecutor() as executor:
            executor.submit(asyncio.run, run_async_migrations()).result()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
