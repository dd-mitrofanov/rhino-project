from __future__ import annotations

import json

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_TELEGRAM_ID: int
    DATABASE_URL: str

    # Comma-separated RU relay gRPC endpoints, e.g. "1.2.3.4:10085,5.6.7.8:10085"
    XRAY_GRPC_ENDPOINTS: str = ""
    # Comma-separated RU Hysteria sync HTTP endpoints, e.g. "1.2.3.4:18081,5.6.7.8:18081"
    HYSTERIA_SYNC_ENDPOINTS: str = ""
    HYSTERIA_SYNC_TOKEN: str = ""
    XRAY_INBOUND_TAG: str = "vless-in"
    SUBSCRIPTION_BASE_URL: str = ""
    XRAY_SYNC_INTERVAL_SECONDS: int = 600

    # Connection-limit enforcer (requires statsUserOnline in Xray policy)
    XRAY_CONNECTION_LIMIT_INTERVAL_SECONDS: int = 30
    XRAY_MAX_IPS_PER_KEY: int = 1

    # HTTP subscription endpoint (for external RU proxies)
    RU_SERVERS_JSON: str = "[]"
    SUBSCRIPTION_API_TOKEN: str = ""
    SUBSCRIPTION_HTTP_PORT: int = 8000

    @property
    def ru_servers(self) -> list[dict]:
        """Parse RU_SERVERS_JSON into a list of server dicts (tag, address, port, etc.).

        Each entry may include optional ``is_whitelist`` (boolean); when absent or false,
        the server is treated as non-whitelist for subscription grouping and labels.
        """
        return json.loads(self.RU_SERVERS_JSON)

    @property
    def xray_grpc_endpoint_list(self) -> list[str]:
        """Parse XRAY_GRPC_ENDPOINTS into a list of 'host:port' strings."""
        if not self.XRAY_GRPC_ENDPOINTS:
            return []
        return [ep.strip() for ep in self.XRAY_GRPC_ENDPOINTS.split(",") if ep.strip()]

    @property
    def hysteria_sync_endpoint_list(self) -> list[str]:
        """Parse HYSTERIA_SYNC_ENDPOINTS into a list of 'host:port' strings."""
        if not self.HYSTERIA_SYNC_ENDPOINTS:
            return []
        return [ep.strip() for ep in self.HYSTERIA_SYNC_ENDPOINTS.split(",") if ep.strip()]


settings = Settings()  # type: ignore[call-arg]
