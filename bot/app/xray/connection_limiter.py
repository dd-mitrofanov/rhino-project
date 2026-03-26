"""Periodic enforcement of per-key connection limits.

Queries each RU Xray relay for ``statsUserOnline`` counts (unique IPs
per client email within a 20-second window).  When a non-admin user
exceeds ``XRAY_MAX_IPS_PER_KEY``, the client is removed and immediately
re-added — terminating all active sessions and forcing a reconnect.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.db.models import Subscription, User
from app.xray.grpc_client import (
    add_vless_client,
    query_online_stats,
    remove_vless_client,
)
from app.xray.subscription_email import (
    legacy_xray_subscription_email,
    xray_subscription_email_from_ids,
)

logger = logging.getLogger(__name__)


async def _load_active_subscriptions(
    session_factory: async_sessionmaker,
) -> dict[str, tuple[uuid.UUID, bool]]:
    """Return ``{xray_email: (vless_uuid, is_admin)}`` for active subscriptions.

    Maps both current and legacy Xray emails to the same row so limits apply
    before and after subscription-email migration on relays.
    """
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(
                    Subscription.user_telegram_id,
                    Subscription.id,
                    Subscription.vless_uuid,
                    User.role,
                )
                .join(User, Subscription.user_telegram_id == User.telegram_id)
                .where(Subscription.active.is_(True)),
            )
        ).all()
    result: dict[str, tuple[uuid.UUID, bool]] = {}
    for tg_id, sub_id, vless_uuid, role in rows:
        info = (vless_uuid, role == "admin")
        current = xray_subscription_email_from_ids(tg_id, sub_id)
        result[current] = info
        legacy = legacy_xray_subscription_email(sub_id)
        if legacy != current:
            result[legacy] = info
    return result


def _email_from_stat(stat_name: str) -> str | None:
    """Extract email from stat name ``user>>>email>>>online``."""
    parts = stat_name.split(">>>")
    if len(parts) == 3 and parts[0] == "user" and parts[2] == "online":
        return parts[1]
    return None


async def enforce_connection_limits(
    session_factory: async_sessionmaker,
) -> None:
    """Check all Xray endpoints and reset sessions for users exceeding the IP limit."""
    endpoints = settings.xray_grpc_endpoint_list
    if not endpoints:
        return

    max_ips = settings.XRAY_MAX_IPS_PER_KEY
    if max_ips <= 0:
        return

    sub_map = await _load_active_subscriptions(session_factory)
    if not sub_map:
        return

    inbound_tag = settings.XRAY_INBOUND_TAG

    for endpoint in endpoints:
        try:
            online = await query_online_stats(endpoint)
        except Exception:
            logger.warning(
                "Failed to query online stats from %s", endpoint, exc_info=True,
            )
            continue

        for stat_name, ip_count in online.items():
            if ip_count <= max_ips:
                continue

            email = _email_from_stat(stat_name)
            if not email:
                continue

            sub_info = sub_map.get(email)
            if not sub_info:
                continue

            vless_uuid, is_admin = sub_info
            if is_admin:
                continue

            logger.info(
                "User %s has %d IPs on %s (limit %d), resetting sessions",
                email, ip_count, endpoint, max_ips,
            )

            try:
                await remove_vless_client([endpoint], inbound_tag, email)
            except Exception:
                logger.warning(
                    "Failed to remove %s from %s", email, endpoint, exc_info=True,
                )
                continue

            try:
                await add_vless_client(
                    [endpoint], inbound_tag, vless_uuid, email,
                )
            except Exception:
                logger.error(
                    "Removed %s from %s but failed to re-add; "
                    "will be restored on next sync cycle",
                    email, endpoint, exc_info=True,
                )
