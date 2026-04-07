from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import AsyncSessionLocal
from app.db.repositories import get_subscription_by_token
from app.subscription_format import build_subscription_link_lines

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
    """Re-push all active subscriptions to RU Xray (gRPC) and Hysteria (HTTP) (same Bearer)."""
    from app.xray.sync import sync_all_subscriptions

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

    links = build_subscription_link_lines(
        subscription_token=subscription.token,
        vless_uuid=str(subscription.vless_uuid),
        hysteria_password=subscription.hysteria_password,
        servers=list(settings.ru_servers),
        subscription_is_whitelist=subscription.is_whitelist,
    )
    return PlainTextResponse("\n".join(links) + "\n")
