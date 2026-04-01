"""Prometheus exporter: Xray user email (target) → Telegram ID from bot DB."""
from __future__ import annotations

import logging
import os
import uuid
from threading import Event

import psycopg2
from prometheus_client import CollectorRegistry, generate_latest, start_http_server
from prometheus_client.core import GaugeMetricFamily

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_EMAIL_SUFFIX = "@rhino"
_UNIQUE_SUFFIX_LEN = 8


def _current_email(telegram_id: int, subscription_id: uuid.UUID) -> str:
    u = subscription_id.hex[:_UNIQUE_SUFFIX_LEN]
    return f"sub_{telegram_id}_{u}{_EMAIL_SUFFIX}"


def _legacy_email(subscription_id: uuid.UUID) -> str:
    return f"sub-{subscription_id.hex}{_EMAIL_SUFFIX}"


class MappingCollector:
    """One gauge per (target email, telegram_id), value 1 — join key for xray user traffic."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def collect(self):
        metric = GaugeMetricFamily(
            "rhino_vless_user_mapping",
            "Maps Xray stats user email (target) to Telegram user id",
            labels=["target", "telegram_id"],
        )
        try:
            conn = psycopg2.connect(self._dsn)
        except Exception:
            logger.exception("database connection failed")
            yield metric
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_telegram_id
                    FROM subscriptions
                    WHERE active = true
                    """
                )
                seen: set[tuple[str, str]] = set()
                for row in cur.fetchall():
                    sid_raw, tg_id = row
                    if isinstance(sid_raw, uuid.UUID):
                        sid = sid_raw
                    else:
                        sid = uuid.UUID(str(sid_raw))
                    tg_str = str(int(tg_id))
                    for em in (
                        _current_email(int(tg_id), sid),
                        _legacy_email(sid),
                    ):
                        key = (em, tg_str)
                        if key in seen:
                            continue
                        seen.add(key)
                        metric.add_metric([em, tg_str], 1.0)
        finally:
            conn.close()
        yield metric


def main() -> None:
    dsn = os.environ.get("MAPPING_EXPORTER_DATABASE_URL")
    if not dsn:
        raise SystemExit("MAPPING_EXPORTER_DATABASE_URL is required")
    port = int(os.environ.get("MAPPING_EXPORTER_PORT", "9101"))
    registry = CollectorRegistry()
    registry.register(MappingCollector(dsn))
    start_http_server(port, registry=registry)
    logger.info("listening on :%s /metrics", port)
    try:
        Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
