from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommandScopeDefault

from app.config import settings
from app.db.engine import AsyncSessionLocal, init_db
from app.handlers import broadcast, delete, invite, instructions, menu, start, subscription, users
from app.handlers.menu import bot_commands
from app.middlewares.db_session import DbSessionMiddleware
from app.middlewares.update_user import UpdateUserMiddleware
from app.subscription_http import app as subscription_app
from app.xray.connection_limiter import enforce_connection_limits
from app.xray.sync import sync_all_subscriptions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _periodic_sync(session_factory) -> None:
    """Run Xray client sync on a fixed interval."""
    while True:
        try:
            await sync_all_subscriptions(session_factory)
        except Exception:
            logger.exception("Xray sync failed, will retry next cycle")
        await asyncio.sleep(settings.XRAY_SYNC_INTERVAL_SECONDS)


async def _periodic_connection_limit(session_factory) -> None:
    """Enforce per-key connection limits on a fixed interval."""
    while True:
        await asyncio.sleep(settings.XRAY_CONNECTION_LIMIT_INTERVAL_SECONDS)
        try:
            await enforce_connection_limits(session_factory)
        except Exception:
            logger.exception("Connection limit enforcement failed, will retry next cycle")


async def main() -> None:
    logger.info("Initialising database …")
    await init_db()

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    await bot.set_my_commands(bot_commands(), scope=BotCommandScopeDefault())

    dp.update.outer_middleware(DbSessionMiddleware(AsyncSessionLocal))
    dp.update.outer_middleware(UpdateUserMiddleware())

    dp.include_routers(
        start.router,
        invite.router,
        users.router,
        delete.router,
        subscription.router,
        instructions.router,
        broadcast.router,
        menu.router,
    )

    try:
        await sync_all_subscriptions(AsyncSessionLocal)
    except Exception:
        logger.exception("Initial Xray sync failed, will retry periodically")

    asyncio.create_task(_periodic_sync(AsyncSessionLocal))
    asyncio.create_task(_periodic_connection_limit(AsyncSessionLocal))

    config = uvicorn.Config(
        subscription_app,
        host="0.0.0.0",
        port=settings.SUBSCRIPTION_HTTP_PORT,
    )
    server = uvicorn.Server(config)
    logger.info("Starting subscription HTTP on port %s and polling …", settings.SUBSCRIPTION_HTTP_PORT)
    await asyncio.gather(server.serve(), dp.start_polling(bot))


if __name__ == "__main__":
    asyncio.run(main())
