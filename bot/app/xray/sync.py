"""Periodic synchronization of active subscriptions to Xray servers."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.db import repositories as repo
from app.xray.grpc_client import XrayClientError, add_vless_client, remove_vless_client
from app.xray.subscription_email import legacy_xray_subscription_email, xray_subscription_email

logger = logging.getLogger(__name__)


async def sync_all_subscriptions(session_factory: async_sessionmaker) -> None:
    """Read all active subscriptions from DB and sync to all RU Xray servers."""
    endpoints = settings.xray_grpc_endpoint_list
    if not endpoints:
        logger.debug("No Xray gRPC endpoints configured, skipping sync")
        return

    async with session_factory() as session:
        subscriptions = await repo.list_all_active_subscriptions(session)

    if not subscriptions:
        logger.debug("No active subscriptions to sync")
        return

    logger.info(
        "Syncing %d active subscriptions to %d Xray endpoints",
        len(subscriptions), len(endpoints),
    )

    inbound_tag = settings.XRAY_INBOUND_TAG
    for sub in subscriptions:
        email = xray_subscription_email(sub)
        legacy = legacy_xray_subscription_email(sub.id)
        if legacy != email:
            try:
                await remove_vless_client(endpoints, inbound_tag, legacy)
            except XrayClientError:
                pass
        try:
            await add_vless_client(endpoints, inbound_tag, sub.vless_uuid, email)
        except XrayClientError:
            logger.warning(
                "Failed to sync client %s, will retry next cycle", email,
            )

    logger.info("Sync complete")
