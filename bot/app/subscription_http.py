from __future__ import annotations

import hashlib
import random

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import AsyncSessionLocal
from app.db.repositories import get_subscription_by_token
from app.vless import build_vless_link
from app.xray.sync import sync_all_subscriptions


def _two_digit_prefix(subscription_token: str, server_tag: str) -> str:
    """Per-subscription 00–99 from token+tag; stable on refresh, differs between users."""
    material = f"{subscription_token}:{server_tag}".encode()
    n = int(hashlib.sha256(material).hexdigest()[:8], 16) % 100
    return f"{n:02d}"


_scheme = HTTPBearer(auto_error=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_scheme),
) -> None:
    if (
        not settings.SUBSCRIPTION_API_TOKEN
        or credentials is None
        or credentials.credentials != settings.SUBSCRIPTION_API_TOKEN
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


app = FastAPI(docs_url=None, redoc_url=None)


@app.post("/internal/xray-sync")
async def trigger_xray_sync(
    _: None = Depends(verify_bearer_token),
) -> dict[str, str]:
    """Re-push all active VLESS clients to RU Xray nodes (same Bearer as subscription API)."""
    await sync_all_subscriptions(AsyncSessionLocal)
    return {"status": "ok"}


@app.get("/{token}")
async def get_subscription(
    token: str,
    _: None = Depends(verify_bearer_token),
    session: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    subscription = await get_subscription_by_token(session, token)
    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    servers = list(settings.ru_servers)
    random.shuffle(servers)
    links = []
    for server in servers:
        links.append(
            build_vless_link(
                vless_uuid=str(subscription.vless_uuid),
                server_address=server["address"],
                server_port=server["port"],
                reality_public_key=server["reality_public_key"],
                sni_domain=server["sni_domain"],
                short_id=server.get("short_id", ""),
                server_name=f"{_two_digit_prefix(subscription.token, server['tag'])}-{server['tag']}",
            )
        )
    return PlainTextResponse("\n".join(links) + "\n")
