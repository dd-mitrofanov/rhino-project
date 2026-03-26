from __future__ import annotations

from urllib.parse import quote

import httpx
from fastapi import HTTPException
from fastapi.responses import PlainTextResponse

from app.config import settings

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(verify=False, timeout=10.0)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _internal_subscription_url(token: str) -> str:
    base = settings.INTERNAL_API_URL.rstrip("/")
    return f"{base}/{quote(token, safe='')}"


async def proxy_subscription(token: str) -> PlainTextResponse:
    url = _internal_subscription_url(token)
    headers = {"Authorization": f"Bearer {settings.INTERNAL_API_TOKEN}"}

    try:
        resp = await _get_client().get(url, headers=headers)
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Upstream unreachable")

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Not found")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream returned HTTP {resp.status_code}",
        )

    return PlainTextResponse(resp.text)
