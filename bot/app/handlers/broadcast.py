from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InputMediaPhoto, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repositories as repo
from app.db.engine import AsyncSessionLocal
from app.keyboards.menus import (
    broadcast_prompt_keyboard,
    broadcast_sending_keyboard,
    main_menu_keyboard,
    menu_title,
)

logger = logging.getLogger(__name__)

router = Router()

ALBUM_DEBOUNCE_SEC = 0.75
BROADCAST_SEND_DELAY_SEC = 0.05

_broadcast_album_buffers: dict[str, dict[str, Any]] = {}
_broadcast_cancel_events: dict[int, asyncio.Event] = {}


class BroadcastStates(StatesGroup):
    waiting_content = State()


def clear_broadcast_album_pending_for_chat(chat_id: int) -> None:
    keys = [k for k in _broadcast_album_buffers if k.startswith(f"{chat_id}:")]
    for k in keys:
        bucket = _broadcast_album_buffers.pop(k, None)
        if bucket and (t := bucket.get("task")) and not t.done():
            t.cancel()


async def _require_admin(
    session: AsyncSession,
    telegram_id: int,
    answer,
):
    user = await repo.get_user(session, telegram_id)
    if not user or user.role != "admin":
        await answer("У вас нет прав для этой команды.")
        return None
    return user


async def _start_broadcast_flow(answer) -> None:
    await answer(
        "Отправьте текст рассылки, одно фото, фото с подписью или альбом до "
        f"{repo.MAX_INSTRUCTION_PHOTOS} фото. Фото можно без текста, текст — без фото.",
        reply_markup=broadcast_prompt_keyboard(),
    )


@router.callback_query(F.data == "broadcast:back")
async def broadcast_prompt_back(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Назад из ввода рассылки: сброс FSM и буфера альбома."""
    if await state.get_state() != BroadcastStates.waiting_content.state:
        await callback.answer()
        return
    clear_broadcast_album_pending_for_chat(callback.message.chat.id)  # type: ignore[union-attr]
    await state.clear()
    await callback.message.delete()  # type: ignore[union-attr]
    user = await repo.get_user(session, callback.from_user.id)  # type: ignore[union-attr]
    if not user:
        await callback.message.answer("Вы не зарегистрированы")  # type: ignore[union-attr]
    else:
        from app.handlers.menu import _send_main_menu

        await _send_main_menu(session, callback.message.answer, user)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "m:broadcast")
async def menu_broadcast(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer("У вас нет прав для этой команды.", show_alert=True)
        return
    await state.set_state(BroadcastStates.waiting_content)
    await callback.message.delete()  # type: ignore[union-attr]
    await _start_broadcast_flow(callback.message.answer)  # type: ignore[union-attr]
    await callback.answer()


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        return
    await state.set_state(BroadcastStates.waiting_content)
    await _start_broadcast_flow(message.answer)


@router.callback_query(lambda cb: cb.data == "broadcast:cancel")
async def broadcast_cancel_click(callback: CallbackQuery) -> None:
    ev = _broadcast_cancel_events.get(callback.from_user.id)  # type: ignore[union-attr]
    if ev:
        ev.set()
        await callback.answer("Останавливаем рассылку…")
    else:
        await callback.answer("Рассылка уже завершена.", show_alert=True)


async def _send_broadcast(
    bot,
    *,
    file_ids: list[str],
    text: str | None,
    recipient_ids: list[int],
    cancel_event: asyncio.Event | None = None,
) -> tuple[int, int, int]:
    """Returns (delivered_ok, failed, not_sent_because_cancelled)."""
    ok = 0
    failed = 0
    cap = (text or "").strip() or None

    for i, uid in enumerate(recipient_ids):
        if cancel_event and cancel_event.is_set():
            return ok, failed, len(recipient_ids) - i
        try:
            if not file_ids:
                if not cap:
                    failed += 1
                    continue
                await bot.send_message(chat_id=uid, text=cap)
            elif len(file_ids) == 1:
                await bot.send_photo(chat_id=uid, photo=file_ids[0], caption=cap)
            else:
                media: list[InputMediaPhoto] = []
                for j, fid in enumerate(file_ids):
                    if j == 0:
                        media.append(InputMediaPhoto(media=fid, caption=cap))
                    else:
                        media.append(InputMediaPhoto(media=fid))
                await bot.send_media_group(chat_id=uid, media=media)
            ok += 1
        except Exception:
            logger.exception("Broadcast: failed to send to %s", uid)
            failed += 1
        await asyncio.sleep(BROADCAST_SEND_DELAY_SEC)

    return ok, failed, 0


async def _finish_broadcast_ui(
    message: Message,
    session: AsyncSession,
    *,
    admin,
    status_msg,
    ok: int,
    failed: int,
    cancelled_left: int,
) -> None:
    try:
        await status_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.debug("Could not remove broadcast cancel keyboard", exc_info=True)

    if cancelled_left > 0:
        summary = (
            f"Отправка остановлена. Доставлено: {ok}, ошибок: {failed}, "
            f"не отправлено: {cancelled_left}."
        )
    else:
        summary = f"Готово. Доставлено: {ok}, ошибок: {failed}."

    instructions = await repo.list_instructions(session)
    has_instructions = len(instructions) > 0
    await message.answer(summary)
    await message.answer(
        menu_title("Главное меню"),
        reply_markup=main_menu_keyboard(admin.role, has_instructions=has_instructions),
    )


async def _run_broadcast(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    *,
    file_ids: list[str],
    text: str | None,
) -> None:
    admin_id = message.from_user.id  # type: ignore[union-attr]
    event = asyncio.Event()
    _broadcast_cancel_events[admin_id] = event
    try:
        async with AsyncSessionLocal() as s2:
            users = await repo.list_active_users(s2)
        recipient_ids = [u.telegram_id for u in users if u.telegram_id != admin_id]

        cap = (text or "").strip() or None
        if not file_ids and not cap:
            await message.answer("Нужен непустой текст или хотя бы одно фото.")
            return

        if cap and len(cap) > repo.MAX_INSTRUCTION_BODY_CHARS:
            await message.answer(f"Текст не длиннее {repo.MAX_INSTRUCTION_BODY_CHARS} символов.")
            return

        await state.clear()
        status_msg = await message.answer(
            f"Отправляю сообщение {len(recipient_ids)} активным пользователям…",
            reply_markup=broadcast_sending_keyboard(),
        )

        ok, failed, cancelled_left = await _send_broadcast(
            message.bot,
            file_ids=file_ids,
            text=cap,
            recipient_ids=recipient_ids,
            cancel_event=event,
        )

        admin = await repo.get_user(session, admin_id)
        if not admin:
            await message.answer("Сессия сброшена.")
            return
        await _finish_broadcast_ui(
            message,
            session,
            admin=admin,
            status_msg=status_msg,
            ok=ok,
            failed=failed,
            cancelled_left=cancelled_left,
        )
    finally:
        _broadcast_cancel_events.pop(admin_id, None)


@router.message(BroadcastStates.waiting_content, F.photo)
async def broadcast_receive_photo(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        await state.clear()
        return

    if message.media_group_id is None:
        fid = message.photo[-1].file_id  # type: ignore[union-attr]
        caption = message.caption
        cap = (caption or "").strip() or None
        if cap and len(cap) > repo.MAX_INSTRUCTION_BODY_CHARS:
            await message.answer(f"Текст не длиннее {repo.MAX_INSTRUCTION_BODY_CHARS} символов.")
            return

        await _run_broadcast(message, session, state, file_ids=[fid], text=cap)
        return

    key = f"{message.chat.id}:{message.media_group_id}"
    if key not in _broadcast_album_buffers:
        _broadcast_album_buffers[key] = {"file_ids": [], "caption": None, "task": None}
    bucket = _broadcast_album_buffers[key]
    bucket["file_ids"].append(message.photo[-1].file_id)  # type: ignore[union-attr]
    if message.caption:
        bucket["caption"] = message.caption

    prev = bucket.get("task")
    if prev and not prev.done():
        prev.cancel()

    async def _finish() -> None:
        await asyncio.sleep(ALBUM_DEBOUNCE_SEC)
        b = _broadcast_album_buffers.pop(key, None)
        if not b:
            return
        file_ids = b["file_ids"]
        caption = b["caption"]
        cap = (caption or "").strip() or None
        st = await state.get_state()
        if st != BroadcastStates.waiting_content.state:
            return
        if cap and len(cap) > repo.MAX_INSTRUCTION_BODY_CHARS:
            await message.bot.send_message(
                message.chat.id,
                f"Текст не длиннее {repo.MAX_INSTRUCTION_BODY_CHARS} символов.",
            )
            return
        if not file_ids or len(file_ids) > repo.MAX_INSTRUCTION_PHOTOS:
            await message.bot.send_message(
                message.chat.id,
                f"Нужно от 1 до {repo.MAX_INSTRUCTION_PHOTOS} фото.",
            )
            return

        admin_id = message.from_user.id  # type: ignore[union-attr]
        event = asyncio.Event()
        _broadcast_cancel_events[admin_id] = event
        try:
            async with AsyncSessionLocal() as s2:
                users = await repo.list_active_users(s2)
            recipient_ids = [u.telegram_id for u in users if u.telegram_id != admin_id]

            if not file_ids and not cap:
                await message.bot.send_message(message.chat.id, "Нужен непустой текст или хотя бы одно фото.")
                return

            await state.clear()
            status_msg = await message.bot.send_message(
                message.chat.id,
                f"Отправляю сообщение {len(recipient_ids)} активным пользователям…",
                reply_markup=broadcast_sending_keyboard(),
            )

            ok, failed, cancelled_left = await _send_broadcast(
                message.bot,
                file_ids=file_ids,
                text=cap,
                recipient_ids=recipient_ids,
                cancel_event=event,
            )

            async with AsyncSessionLocal() as s3:
                admin_u = await repo.get_user(s3, message.from_user.id)  # type: ignore[union-attr]
            if not admin_u:
                await message.bot.send_message(message.chat.id, "Сессия сброшена.")
                return
            try:
                await status_msg.edit_reply_markup(reply_markup=None)
            except Exception:
                logger.debug("Could not remove broadcast cancel keyboard", exc_info=True)

            if cancelled_left > 0:
                summary = (
                    f"Отправка остановлена. Доставлено: {ok}, ошибок: {failed}, "
                    f"не отправлено: {cancelled_left}."
                )
            else:
                summary = f"Готово. Доставлено: {ok}, ошибок: {failed}."

            async with AsyncSessionLocal() as s4:
                instructions = await repo.list_instructions(s4)
            has_instructions = len(instructions) > 0
            await message.bot.send_message(message.chat.id, summary)
            await message.bot.send_message(
                message.chat.id,
                menu_title("Главное меню"),
                reply_markup=main_menu_keyboard(admin_u.role, has_instructions=has_instructions),
            )
        finally:
            _broadcast_cancel_events.pop(admin_id, None)

    bucket["task"] = asyncio.create_task(_finish())


@router.message(BroadcastStates.waiting_content, F.text)
async def broadcast_receive_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        await state.clear()
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Текст не может быть пустым.")
        return
    if raw.startswith("/"):
        await message.answer("Для рассылки отправьте обычный текст без / в начале или нажмите «Назад».")
        return

    await _run_broadcast(message, session, state, file_ids=[], text=raw)


@router.message(BroadcastStates.waiting_content)
async def broadcast_wrong_type(message: Message) -> None:
    await message.answer(
        "Отправьте текст, фото или альбом (до 10 фото), либо нажмите «Назад».",
    )
