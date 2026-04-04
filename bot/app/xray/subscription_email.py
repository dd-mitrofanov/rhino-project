"""VLESS client email for Xray (stats / Grafana user labels)."""
from __future__ import annotations

import logging
import uuid

from app.config import settings
from app.db.engine import AsyncSessionLocal
from app.db.models import Subscription
from app.hysteria.sync import sync_hysteria_credentials
from app.xray.grpc_client import XrayClientError, remove_vless_client

logger = logging.getLogger(__name__)

_EMAIL_SUFFIX = "@rhino"
_UNIQUE_SUFFIX_LEN = 8


def xray_subscription_email_from_ids(
    user_telegram_id: int,
    subscription_id: uuid.UUID,
) -> str:
    """Same rule as :func:`xray_subscription_email` without loading the ORM row."""
    u = subscription_id.hex[:_UNIQUE_SUFFIX_LEN]
    return f"sub_{user_telegram_id}_{u}{_EMAIL_SUFFIX}"


def xray_subscription_email(subscription: Subscription) -> str:
    """Stable label ``sub_<telegram_id>_<8 hex of subscription id>@rhino``."""
    return xray_subscription_email_from_ids(
        subscription.user_telegram_id,
        subscription.id,
    )


def legacy_xray_subscription_email(subscription_id: uuid.UUID) -> str:
    """Previous format (full subscription UUID hex); may still exist in Xray."""
    return f"sub-{subscription_id.hex}{_EMAIL_SUFFIX}"


async def remove_subscription_from_xray(subscription: Subscription) -> None:
    """Remove client by current and legacy email (best-effort)."""
    endpoints = settings.xray_grpc_endpoint_list
    if not endpoints:
        return
    tag = settings.XRAY_INBOUND_TAG
    current = xray_subscription_email(subscription)
    legacy = legacy_xray_subscription_email(subscription.id)
    for email in (legacy, current):
        try:
            await remove_vless_client(endpoints, tag, email)
        except XrayClientError:
            logger.debug(
                "remove_vless_client(%s) failed on all endpoints (likely absent)",
                email,
            )

    try:
        await sync_hysteria_credentials(AsyncSessionLocal)
    except Exception:
        logger.exception("Hysteria credential sync after remove failed")
