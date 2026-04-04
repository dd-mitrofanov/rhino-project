"""Push active subscription Hysteria credentials to each RU relay (HTTP, not gRPC)."""
from __future__ import annotations

import logging

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.db import repositories as repo

logger = logging.getLogger(__name__)


async def sync_hysteria_credentials(session_factory: async_sessionmaker) -> None:
    endpoints = settings.hysteria_sync_endpoint_list
    if not endpoints:
        logger.debug("No HYSTERIA_SYNC_ENDPOINTS configured, skipping Hysteria sync")
        return
    if not settings.HYSTERIA_SYNC_TOKEN:
        logger.warning("HYSTERIA_SYNC_TOKEN empty, skipping Hysteria sync")
        return

    async with session_factory() as session:
        subscriptions = await repo.list_all_active_subscriptions(session)

    payload = {
        "users": [
            {"user": sub.token, "password": sub.hysteria_password}
            for sub in subscriptions
        ],
    }

    logger.info(
        "Syncing Hysteria credentials for %d subscriptions to %d RU endpoints",
        len(subscriptions),
        len(endpoints),
    )

    headers = {"Authorization": f"Bearer {settings.HYSTERIA_SYNC_TOKEN}"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        for ep in endpoints:
            url = f"http://{ep.rstrip('/')}/sync"
            try:
                r = await client.post(url, json=payload, headers=headers)
                r.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("Hysteria sync failed for %s: %s", ep, e)

    logger.info("Hysteria credential sync complete")
