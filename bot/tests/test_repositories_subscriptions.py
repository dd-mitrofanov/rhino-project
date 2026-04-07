"""Tests for subscription repository helpers and create_subscription flags."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import repositories as repo
from app.db.models import Base, Subscription, User


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


async def _add_user(sess: AsyncSession, telegram_id: int, *, role: str = "l2") -> None:
    u = User(
        telegram_id=telegram_id,
        username=None,
        first_name="T",
        last_name=None,
        full_name="Test",
        role=role,
        invited_by=None,
        active=True,
    )
    sess.add(u)
    await sess.flush()


async def _add_sub(
    sess: AsyncSession,
    user_id: int,
    *,
    is_whitelist: bool | None,
    active: bool = True,
) -> Subscription:
    s = Subscription(
        user_telegram_id=user_id,
        label="L",
        token=uuid.uuid4().hex,
        hysteria_password="x",
        is_whitelist=is_whitelist,
        active=active,
    )
    sess.add(s)
    await sess.flush()
    return s


@pytest.mark.asyncio
async def test_user_has_active_whitelist_no_subscriptions(session: AsyncSession) -> None:
    await _add_user(session, 100)
    assert await repo.user_has_active_whitelist_subscription(session, 100) is False


@pytest.mark.asyncio
async def test_user_has_active_whitelist_only_false(session: AsyncSession) -> None:
    await _add_user(session, 101)
    await _add_sub(session, 101, is_whitelist=False)
    assert await repo.user_has_active_whitelist_subscription(session, 101) is False


@pytest.mark.asyncio
async def test_user_has_active_whitelist_true(session: AsyncSession) -> None:
    await _add_user(session, 102)
    await _add_sub(session, 102, is_whitelist=True)
    assert await repo.user_has_active_whitelist_subscription(session, 102) is True


@pytest.mark.asyncio
async def test_user_has_active_whitelist_null_counts_as_false(session: AsyncSession) -> None:
    await _add_user(session, 105)
    await _add_sub(session, 105, is_whitelist=None)
    assert await repo.user_has_active_whitelist_subscription(session, 105) is False


@pytest.mark.asyncio
async def test_user_has_active_whitelist_inactive_only(session: AsyncSession) -> None:
    await _add_user(session, 103)
    await _add_sub(session, 103, is_whitelist=True, active=False)
    assert await repo.user_has_active_whitelist_subscription(session, 103) is False


@pytest.mark.asyncio
async def test_user_has_active_whitelist_mixed(session: AsyncSession) -> None:
    await _add_user(session, 104)
    await _add_sub(session, 104, is_whitelist=False)
    await _add_sub(session, 104, is_whitelist=True)
    assert await repo.user_has_active_whitelist_subscription(session, 104) is True


@pytest.mark.asyncio
async def test_create_subscription_persists_is_whitelist_false(session: AsyncSession) -> None:
    await _add_user(session, 200)
    sub = await repo.create_subscription(
        session, 200, "k1", role="l2", is_whitelist=False,
    )
    await session.commit()
    row = await session.get(Subscription, sub.id)
    assert row is not None
    assert row.is_whitelist is False


@pytest.mark.asyncio
async def test_create_subscription_persists_is_whitelist_true(session: AsyncSession) -> None:
    await _add_user(session, 201)
    sub = await repo.create_subscription(
        session, 201, "k1", role="l2", is_whitelist=True,
    )
    await session.commit()
    row = await session.get(Subscription, sub.id)
    assert row is not None
    assert row.is_whitelist is True


@pytest.mark.asyncio
async def test_create_subscription_limit_non_admin(session: AsyncSession) -> None:
    await _add_user(session, 300, role="l2")
    for i in range(repo.MAX_ACTIVE_SUBSCRIPTIONS):
        await repo.create_subscription(
            session, 300, f"k{i}", role="l2", is_whitelist=False,
        )
    await session.commit()
    with pytest.raises(repo.SubscriptionLimitError):
        await repo.create_subscription(
            session, 300, "overflow", role="l2", is_whitelist=True,
        )
