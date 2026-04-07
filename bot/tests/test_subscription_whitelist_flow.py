"""Tests for whitelist resolution when creating subscription keys."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.handlers.subscription import (
    WHITELIST_PROMPT_RU,
    SubAddStates,
    _resolve_whitelist_or_prompt,
)


def _user(role: str, telegram_id: int = 1) -> MagicMock:
    u = MagicMock()
    u.role = role
    u.telegram_id = telegram_id
    return u


@pytest.mark.asyncio
async def test_resolve_admin_creates_with_whitelist_true() -> None:
    state = AsyncMock()
    state.clear = AsyncMock()
    answer = AsyncMock()
    session = AsyncMock()

    with patch(
        "app.handlers.subscription._create_and_send_subscription",
        new_callable=AsyncMock,
    ) as create_send:
        done = await _resolve_whitelist_or_prompt(
            session,
            _user("admin"),
            "label",
            answer,
            state,
        )

    assert done is True
    state.clear.assert_awaited_once()
    create_send.assert_awaited_once()
    kwargs = create_send.call_args.kwargs
    assert kwargs["is_whitelist"] is True
    answer.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_non_admin_with_whitelist_key_creates_false() -> None:
    state = AsyncMock()
    state.clear = AsyncMock()
    answer = AsyncMock()
    session = AsyncMock()

    with patch(
        "app.handlers.subscription.repo.user_has_active_whitelist_subscription",
        new_callable=AsyncMock,
        return_value=True,
    ), patch(
        "app.handlers.subscription._create_and_send_subscription",
        new_callable=AsyncMock,
    ) as create_send:
        done = await _resolve_whitelist_or_prompt(
            session,
            _user("l2"),
            "label",
            answer,
            state,
        )

    assert done is True
    state.clear.assert_awaited_once()
    kwargs = create_send.call_args.kwargs
    assert kwargs["is_whitelist"] is False
    answer.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_non_admin_prompt_shows_message_and_keyboard() -> None:
    state = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    answer = AsyncMock()
    session = AsyncMock()

    with patch(
        "app.handlers.subscription.repo.user_has_active_whitelist_subscription",
        new_callable=AsyncMock,
        return_value=False,
    ), patch(
        "app.handlers.subscription.whitelist_choice_keyboard",
    ) as kb:
        kb.return_value = object()
        done = await _resolve_whitelist_or_prompt(
            session,
            _user("l2"),
            "мой ключ",
            answer,
            state,
        )

    assert done is False
    state.set_state.assert_awaited_once_with(SubAddStates.waiting_for_whitelist_choice)
    state.update_data.assert_awaited_once_with(pending_label="мой ключ")
    answer.assert_awaited_once()
    assert answer.call_args[0][0] == WHITELIST_PROMPT_RU
    assert "reply_markup" in answer.call_args.kwargs


@pytest.mark.asyncio
async def test_sub_whitelist_stale_state_does_not_create() -> None:
    from app.handlers import subscription as sub_mod

    callback = AsyncMock()
    callback.data = "sub_wl:yes"
    callback.from_user.id = 42
    callback.message.answer = AsyncMock()

    state = AsyncMock()
    state.get_state = AsyncMock(return_value="OtherState:idle")

    session = AsyncMock()
    user = MagicMock()
    user.role = "l2"
    user.telegram_id = 42

    with patch.object(
        sub_mod,
        "_get_registered_user",
        new_callable=AsyncMock,
        return_value=user,
    ), patch.object(
        sub_mod,
        "_create_and_send_subscription",
        new_callable=AsyncMock,
    ) as create_send:
        await sub_mod.sub_whitelist_chosen(callback, session, state)

    create_send.assert_not_called()
    callback.answer.assert_awaited()
