"""Middleware to keep user profile (username, first_name, last_name, full_name) in sync with Telegram."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from app.db import repositories as repo


def _full_name(first_name: str, last_name: str | None) -> str:
    return first_name + (f" {last_name}" if last_name else "")


class UpdateUserMiddleware(BaseMiddleware):
    """Update user profile from Telegram on every Message or CallbackQuery with from_user."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        if session is None:
            return await handler(event, data)

        from_user = None
        if isinstance(event, Update):
            if event.message:
                from_user = event.message.from_user
            elif event.callback_query:
                from_user = event.callback_query.from_user
        elif isinstance(event, (Message, CallbackQuery)):
            from_user = getattr(event, "from_user", None)

        if from_user is not None:
            existing = await repo.get_user(session, from_user.id)
            if existing is not None and not existing.active:
                # Allow /start with invite code — revoked user can be re-invited
                msg = None
                if isinstance(event, Update):
                    msg = event.message
                elif isinstance(event, Message):
                    msg = event
                if msg is not None and isinstance(msg, Message) and msg.text:
                    parts = msg.text.split(maxsplit=1)
                    if len(parts) == 2 and parts[0] in ("/start", "start"):
                        # Has invite code — let handler process re-invitation
                        pass
                    else:
                        msg = None
                if msg is None:
                    answerable = None
                    if isinstance(event, Update):
                        answerable = event.message or event.callback_query
                    elif isinstance(event, (Message, CallbackQuery)):
                        answerable = event
                    if answerable is not None:
                        await answerable.answer("Доступ отозван. Обратитесь к пригласившему.")
                    return
            if existing is not None:
                first_name = from_user.first_name or "User"
                last_name = from_user.last_name
                full_name = _full_name(first_name, last_name).strip() or f"User {from_user.id}"
                await repo.update_user_profile(
                    session,
                    from_user.id,
                    username=from_user.username,
                    first_name=first_name,
                    last_name=last_name,
                    full_name=full_name,
                )

        return await handler(event, data)
