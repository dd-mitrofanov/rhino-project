from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.proxy import close_client, proxy_subscription


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


app = FastAPI(docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/{token}")
async def get_subscription(token: str):
    return await proxy_subscription(token)
