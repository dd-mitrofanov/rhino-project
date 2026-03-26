from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base

async_engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    async_engine, expire_on_commit=False,
)


async def init_db() -> None:
    """Run Alembic migrations to create/update database schema."""
    bot_root = Path(__file__).resolve().parent.parent.parent
    alembic_cfg = Config(str(bot_root / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
