from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand, CallbackQuery, InputMediaPhoto, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repositories as repo
from app.db.engine import AsyncSessionLocal
from app.db.models import User
from app.keyboards.menus import (
    instruction_delete_confirm_keyboard,
    instruction_delete_pick_keyboard,
    instruction_edit_pick_keyboard,
    instruction_edit_submenu_keyboard,
    instructions_list_keyboard,
    instructions_manage_submenu_keyboard,
    instructions_submenu_keyboard,
    main_menu_keyboard,
    menu_title,
)

logger = logging.getLogger(__name__)

router = Router()

ALBUM_DEBOUNCE_SEC = 0.75

# Buffers Telegram album parts: key = "{chat_id}:{media_group_id}"
_album_buffers: dict[str, dict[str, Any]] = {}


class InstructionAddStates(StatesGroup):
    waiting_title = State()
    waiting_media = State()


class InstructionEditStates(StatesGroup):
    waiting_new_title = State()
    waiting_media = State()


def _clear_album_pending_for_chat(chat_id: int) -> None:
    keys = [k for k in _album_buffers if k.startswith(f"{chat_id}:")]
    for k in keys:
        bucket = _album_buffers.pop(k, None)
        if bucket and (t := bucket.get("task")) and not t.done():
            t.cancel()


async def _get_registered_user(
    session: AsyncSession,
    telegram_id: int,
    answer,
) -> User | None:
    user = await repo.get_user(session, telegram_id)
    if not user:
        await answer("Вы не зарегистрированы. Используйте /start для начала.")
        return None
    return user


async def _require_admin(
    session: AsyncSession,
    telegram_id: int,
    answer,
) -> User | None:
    user = await repo.get_user(session, telegram_id)
    if not user or user.role != "admin":
        await answer("У вас нет прав для этой команды.")
        return None
    return user


async def _send_instructions_submenu(
    session: AsyncSession,
    answer_func,  # noqa: ANN001
    user: User,
    *,
    success_message: str | None = None,
) -> None:
    """Show admin instructions management submenu after an action."""
    if success_message:
        await answer_func(success_message)
    await answer_func(
        menu_title("Управление инструкциями"),
        reply_markup=instructions_manage_submenu_keyboard(),
    )


async def send_instructions_menu(session: AsyncSession, answer) -> None:
    instructions = await repo.list_instructions(session)
    if not instructions:
        text = "Пока нет инструкций."
        kb = None
    else:
        text = "Выберите инструкцию:"
        kb = instructions_list_keyboard(instructions)

    await answer(text, reply_markup=kb)


def _is_instruction_fsm_state(state_name: str | None) -> bool:
    if not state_name:
        return False
    head = state_name.split(":", 1)[0] if ":" in state_name else state_name
    return head in ("InstructionAddStates", "InstructionEditStates")


def _is_broadcast_fsm_state(state_name: str | None) -> bool:
    if not state_name:
        return False
    head = state_name.split(":", 1)[0] if ":" in state_name else state_name
    return head == "BroadcastStates"


# Registered before FSM text handlers so /cancel is not handled as title or as «wrong media».
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    cur = await state.get_state()
    if not _is_instruction_fsm_state(cur) and not _is_broadcast_fsm_state(cur):
        return
    _clear_album_pending_for_chat(message.chat.id)
    from app.handlers.broadcast import clear_broadcast_album_pending_for_chat

    clear_broadcast_album_pending_for_chat(message.chat.id)
    await state.clear()
    await message.answer("Действие отменено.")


# ── User: list + open ───────────────────────────────────────────────


@router.message(Command("instructions"))
async def cmd_instructions(message: Message, session: AsyncSession) -> None:
    user = await _get_registered_user(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not user:
        return
    await send_instructions_menu(session, message.answer)


@router.callback_query(
    lambda cb: cb.data
    and (cb.data.startswith("instr:open:") or cb.data.startswith("m:instr:open:")),
)
async def instr_open(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_registered_user(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not user:
        await callback.answer()
        return

    data = callback.data or ""
    parts = data.split(":")
    if len(parts) < 2:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    hex_part = parts[-1]
    try:
        iid = uuid.UUID(hex=hex_part)
    except ValueError:
        await callback.answer("Инструкция не найдена.", show_alert=True)
        return

    inst, photos = await repo.get_instruction_with_photos(session, iid)
    if not inst:
        await callback.answer("Инструкция не найдена или удалена.", show_alert=True)
        return

    file_ids = [p.file_id for p in photos]
    caption = inst.caption
    chat_id = callback.message.chat.id  # type: ignore[union-attr]
    bot = callback.bot

    try:
        if not file_ids:
            body = (caption or "").strip()
            if not body:
                await callback.answer("Инструкция пуста.", show_alert=True)
                return
            await bot.send_message(chat_id=chat_id, text=body)
            await callback.answer()
            return

        if len(file_ids) == 1:
            await bot.send_photo(
                chat_id=chat_id,
                photo=file_ids[0],
                caption=caption or None,
            )
        else:
            media: list[InputMediaPhoto] = []
            for i, fid in enumerate(file_ids):
                if i == 0:
                    media.append(
                        InputMediaPhoto(media=fid, caption=caption or None),
                    )
                else:
                    media.append(InputMediaPhoto(media=fid))
            await bot.send_media_group(chat_id=chat_id, media=media)
    except Exception:
        logger.exception("Failed to send instruction media")
        await callback.answer("Не удалось отправить инструкцию.", show_alert=True)
        return

    await callback.answer()


# ── Admin: add ──────────────────────────────────────────────────────


@router.callback_query(lambda cb: cb.data == "m:instr:add")
async def menu_instr_add(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer()
        return
    await state.set_state(InstructionAddStates.waiting_title)
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer("Введите короткое название инструкции:")  # type: ignore[union-attr]
    await callback.message.answer(menu_title("Инструкции"))  # type: ignore[union-attr]
    await callback.answer()


@router.message(Command("instruction_add"))
async def cmd_instruction_add(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        return
    await state.set_state(InstructionAddStates.waiting_title)
    await message.answer("Введите короткое название инструкции:")
    await message.answer(menu_title("Инструкции"))


@router.message(InstructionAddStates.waiting_title)
async def add_instruction_title(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        await state.clear()
        return

    if message.text is None or not message.text.strip():
        await message.answer("Нужен текст названия (1–200 символов).")
        return

    title = message.text.strip()
    if len(title) > 200:
        await message.answer("Название слишком длинное (максимум 200 символов).")
        return

    await state.update_data(title=title)
    await state.set_state(InstructionAddStates.waiting_media)
    await message.answer(
        "Отправьте текст инструкции, одно фото или альбом (до 10 фото). "
        "Подпись к первому фото будет показана пользователям вместе с фото.",
    )


@router.message(InstructionAddStates.waiting_media, F.photo)
async def add_instruction_media(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        await state.clear()
        return

    if message.media_group_id is None:
        fid = message.photo[-1].file_id  # type: ignore[union-attr]
        caption = message.caption
        data = await state.get_data()
        title = data.get("title")
        if not title or not isinstance(title, str):
            await state.clear()
            await message.answer("Сессия сброшена. Начните снова с /instruction_add.")
            return
        try:
            await repo.create_instruction(session, title, caption, [fid])
        except ValueError as e:
            await message.answer(str(e))
            return
        await state.clear()
        admin = await repo.get_user(session, message.from_user.id)  # type: ignore[union-attr]
        if admin:
            await _send_instructions_submenu(
                session, message.answer, admin, success_message="Инструкция сохранена.",
            )
        else:
            await message.answer("Инструкция сохранена.")
        return

    key = f"{message.chat.id}:{message.media_group_id}"
    if key not in _album_buffers:
        _album_buffers[key] = {"file_ids": [], "caption": None, "task": None}
    bucket = _album_buffers[key]
    bucket["file_ids"].append(message.photo[-1].file_id)  # type: ignore[union-attr]
    if message.caption:
        bucket["caption"] = message.caption

    prev = bucket.get("task")
    if prev and not prev.done():
        prev.cancel()

    async def _finish() -> None:
        await asyncio.sleep(ALBUM_DEBOUNCE_SEC)
        b = _album_buffers.pop(key, None)
        if not b:
            return
        file_ids = b["file_ids"]
        caption = b["caption"]
        st = await state.get_state()
        if st != InstructionAddStates.waiting_media.state:
            return
        data = await state.get_data()
        title = data.get("title")
        if not title or not isinstance(title, str):
            await message.bot.send_message(
                message.chat.id,
                "Сессия сброшена. Начните снова с /instruction_add.",
            )
            await state.clear()
            return
        try:
            if not file_ids or len(file_ids) > repo.MAX_INSTRUCTION_PHOTOS:
                await message.bot.send_message(
                    message.chat.id,
                    f"Нужно от 1 до {repo.MAX_INSTRUCTION_PHOTOS} фото.",
                )
                return
            async with AsyncSessionLocal() as s2:
                await repo.create_instruction(s2, title, caption, file_ids)
                await s2.commit()
        except ValueError as e:
            await message.bot.send_message(message.chat.id, str(e))
            return
        except Exception:
            logger.exception("create_instruction (album) failed")
            await message.bot.send_message(
                message.chat.id,
                "Не удалось сохранить инструкцию.",
            )
            return
        await state.clear()
        async with AsyncSessionLocal() as s3:
            admin = await repo.get_user(s3, message.from_user.id)  # type: ignore[union-attr]
            if admin:
                insts = await repo.list_instructions(s3)
                await message.bot.send_message(message.chat.id, "Инструкция сохранена.")
                await message.bot.send_message(
                    message.chat.id,
                    menu_title("Инструкции"),
                    reply_markup=instructions_submenu_keyboard(insts),
                )
            else:
                await message.bot.send_message(message.chat.id, "Инструкция сохранена.")

    bucket["task"] = asyncio.create_task(_finish())


@router.message(InstructionAddStates.waiting_media, F.text)
async def add_instruction_text_only(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Текст не может быть пустым.")
        return
    if raw.startswith("/"):
        await message.answer(
            "Для текстовой инструкции отправьте обычный текст без / в начале "
            "(или отправьте фото). Отмена: /cancel.",
        )
        return

    data = await state.get_data()
    title = data.get("title")
    if not title or not isinstance(title, str):
        await state.clear()
        await message.answer("Сессия сброшена. Начните снова с /instruction_add.")
        return

    try:
        await repo.create_instruction(session, title, raw, [])
    except ValueError as e:
        await message.answer(str(e))
        return
    await state.clear()
    await _send_instructions_submenu(
        session, message.answer, admin, success_message="Инструкция сохранена.",
    )


@router.message(InstructionAddStates.waiting_media)
async def add_instruction_media_wrong_type(message: Message) -> None:
    await message.answer(
        "Отправьте текст, фото или альбом (до 10 изображений), либо /cancel для отмены.",
    )


# ── Admin: edit ───────────────────────────────────────────────────────


@router.callback_query(lambda cb: cb.data == "m:instr:edit")
async def menu_instr_edit(callback: CallbackQuery, session: AsyncSession) -> None:
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer()
        return
    instructions = await repo.list_instructions(session)
    if not instructions:
        await callback.message.answer("Список инструкций пуст.")  # type: ignore[union-attr]
        await callback.answer()
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer("Выберите инструкцию:")  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Инструкции"),
        reply_markup=instruction_edit_pick_keyboard(instructions),
    )
    await callback.answer()


@router.message(Command("instruction_edit"))
async def cmd_instruction_edit(message: Message, session: AsyncSession) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        return
    instructions = await repo.list_instructions(session)
    if not instructions:
        await message.answer("Список инструкций пуст.")
        return
    await message.answer("Выберите инструкцию:")
    await message.answer(
        menu_title("Инструкции"),
        reply_markup=instruction_edit_pick_keyboard(instructions),
    )


@router.callback_query(lambda cb: cb.data and cb.data.startswith("instr:edit_pick:"))
async def instr_edit_pick(callback: CallbackQuery, session: AsyncSession) -> None:
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer()
        return
    parts = (callback.data or "").split(":", 2)
    if len(parts) < 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        iid = uuid.UUID(hex=parts[2])
    except ValueError:
        await callback.answer("Инструкция не найдена.", show_alert=True)
        return
    inst = await repo.get_instruction(session, iid)
    if not inst:
        await callback.answer("Инструкция уже удалена.", show_alert=True)
        return
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=instruction_edit_submenu_keyboard(iid),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "instr:edit_cancel")
async def instr_edit_cancel(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Cancel always leads to main menu (legacy callback for old messages)."""
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer()
        return
    _clear_album_pending_for_chat(callback.message.chat.id)  # type: ignore[union-attr]
    await state.clear()
    await callback.message.delete()  # type: ignore[union-attr]
    instructions = await repo.list_instructions(session)
    has_instructions = len(instructions) > 0
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Главное меню"),
        reply_markup=main_menu_keyboard(admin.role, has_instructions=has_instructions),
    )
    await callback.answer("Отменено.")


@router.callback_query(lambda cb: cb.data and cb.data.startswith("instr:edit_title:"))
async def instr_edit_title_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer()
        return
    parts = (callback.data or "").split(":", 2)
    if len(parts) < 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        iid = uuid.UUID(hex=parts[2])
    except ValueError:
        await callback.answer("Инструкция не найдена.", show_alert=True)
        return
    inst = await repo.get_instruction(session, iid)
    if not inst:
        await callback.answer("Инструкция уже удалена.", show_alert=True)
        return
    await state.set_state(InstructionEditStates.waiting_new_title)
    await state.update_data(edit_instruction_id=str(iid))
    await callback.message.answer(  # type: ignore[union-attr]
        "Введите новое название инструкции:",
    )
    await callback.answer()


@router.message(InstructionEditStates.waiting_new_title)
async def instr_edit_title_commit(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        await state.clear()
        return
    data = await state.get_data()
    raw = data.get("edit_instruction_id")
    if not raw:
        await state.clear()
        await message.answer("Сессия сброшена.")
        return
    try:
        iid = uuid.UUID(raw)
    except ValueError:
        await state.clear()
        await message.answer("Сессия сброшена.")
        return

    if message.text is None or not message.text.strip():
        await message.answer("Нужен текст названия (1–200 символов).")
        return
    title = message.text.strip()
    if len(title) > 200:
        await message.answer("Название слишком длинное (максимум 200 символов).")
        return

    try:
        ok = await repo.update_instruction_title(session, iid, title)
    except ValueError as e:
        await message.answer(str(e))
        return
    await state.clear()
    if not ok:
        await message.answer("Инструкция не найдена (возможно, удалена).")
        return
    await _send_instructions_submenu(
        session, message.answer, admin, success_message="Название обновлено.",
    )


@router.callback_query(lambda cb: cb.data and cb.data.startswith("instr:edit_media:"))
async def instr_edit_media_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer()
        return
    parts = (callback.data or "").split(":", 2)
    if len(parts) < 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        iid = uuid.UUID(hex=parts[2])
    except ValueError:
        await callback.answer("Инструкция не найдена.", show_alert=True)
        return
    inst = await repo.get_instruction(session, iid)
    if not inst:
        await callback.answer("Инструкция уже удалена.", show_alert=True)
        return
    await state.set_state(InstructionEditStates.waiting_media)
    await state.update_data(edit_instruction_id=str(iid))
    await callback.message.answer(  # type: ignore[union-attr]
        "Отправьте новый текст инструкции, одно фото или альбом (до 10 фото). "
        "Подпись к первому фото сохранится вместе с фото.",
    )
    await callback.answer()


@router.message(InstructionEditStates.waiting_media, F.text)
async def edit_instruction_text_only(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Текст не может быть пустым.")
        return
    if raw.startswith("/"):
        await message.answer(
            "Для текстовой инструкции отправьте обычный текст без / в начале "
            "(или отправьте фото). Отмена: /cancel.",
        )
        return

    data = await state.get_data()
    raw_id = data.get("edit_instruction_id")
    if not raw_id:
        await state.clear()
        await message.answer("Сессия сброшена.")
        return
    try:
        iid = uuid.UUID(raw_id)
    except ValueError:
        await state.clear()
        await message.answer("Сессия сброшена.")
        return

    try:
        ok = await repo.replace_instruction_photos(session, iid, [], raw)
    except ValueError as e:
        await message.answer(str(e))
        return
    await state.clear()
    if not ok:
        await message.answer("Инструкция не найдена (возможно, удалена).")
        return
    await _send_instructions_submenu(
        session, message.answer, admin, success_message="Инструкция обновлена.",
    )


@router.message(InstructionEditStates.waiting_media, F.photo)
async def edit_instruction_media(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        await state.clear()
        return
    data = await state.get_data()
    raw = data.get("edit_instruction_id")
    if not raw:
        await state.clear()
        await message.answer("Сессия сброшена.")
        return
    try:
        iid = uuid.UUID(raw)
    except ValueError:
        await state.clear()
        await message.answer("Сессия сброшена.")
        return

    if message.media_group_id is None:
        fid = message.photo[-1].file_id  # type: ignore[union-attr]
        caption = message.caption
        try:
            ok = await repo.replace_instruction_photos(session, iid, [fid], caption)
        except ValueError as e:
            await message.answer(str(e))
            return
        await state.clear()
        if not ok:
            await message.answer("Инструкция не найдена (возможно, удалена).")
            return
        await message.answer("Инструкция обновлена.")
        return

    key = f"{message.chat.id}:{message.media_group_id}"
    if key not in _album_buffers:
        _album_buffers[key] = {"file_ids": [], "caption": None, "task": None}
    bucket = _album_buffers[key]
    bucket["file_ids"].append(message.photo[-1].file_id)  # type: ignore[union-attr]
    if message.caption:
        bucket["caption"] = message.caption

    prev = bucket.get("task")
    if prev and not prev.done():
        prev.cancel()

    async def _finish() -> None:
        await asyncio.sleep(ALBUM_DEBOUNCE_SEC)
        b = _album_buffers.pop(key, None)
        if not b:
            return
        file_ids = b["file_ids"]
        caption = b["caption"]
        st = await state.get_state()
        if st != InstructionEditStates.waiting_media.state:
            return
        d2 = await state.get_data()
        rid = d2.get("edit_instruction_id")
        if not rid:
            await message.bot.send_message(message.chat.id, "Сессия сброшена.")
            await state.clear()
            return
        try:
            iid2 = uuid.UUID(rid)
        except ValueError:
            await state.clear()
            await message.bot.send_message(message.chat.id, "Сессия сброшена.")
            return
        try:
            if not file_ids or len(file_ids) > repo.MAX_INSTRUCTION_PHOTOS:
                await message.bot.send_message(
                    message.chat.id,
                    f"Нужно от 1 до {repo.MAX_INSTRUCTION_PHOTOS} фото.",
                )
                return
            async with AsyncSessionLocal() as s2:
                ok = await repo.replace_instruction_photos(s2, iid2, file_ids, caption)
                await s2.commit()
        except ValueError as e:
            await message.bot.send_message(message.chat.id, str(e))
            return
        except Exception:
            logger.exception("replace_instruction_photos (album) failed")
            await message.bot.send_message(
                message.chat.id,
                "Не удалось обновить фото.",
            )
            return
        await state.clear()
        if not ok:
            await message.bot.send_message(
                message.chat.id,
                "Инструкция не найдена (возможно, удалена).",
            )
            return
        async with AsyncSessionLocal() as s3:
            adm = await repo.get_user(s3, message.from_user.id)  # type: ignore[union-attr]
            if adm:
                insts = await repo.list_instructions(s3)
                await message.bot.send_message(message.chat.id, "Инструкция обновлена.")
                await message.bot.send_message(
                    message.chat.id,
                    menu_title("Инструкции"),
                    reply_markup=instructions_submenu_keyboard(insts),
                )
            else:
                await message.bot.send_message(message.chat.id, "Инструкция обновлена.")

    bucket["task"] = asyncio.create_task(_finish())


@router.message(InstructionEditStates.waiting_media)
async def edit_instruction_media_wrong_type(message: Message) -> None:
    await message.answer(
        "Отправьте текст, фото или альбом, либо /cancel для отмены.",
    )


# ── Admin: delete ─────────────────────────────────────────────────────


@router.callback_query(lambda cb: cb.data == "m:instr:del")
async def menu_instr_del(callback: CallbackQuery, session: AsyncSession) -> None:
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer()
        return
    instructions = await repo.list_instructions(session)
    if not instructions:
        await callback.message.answer("Список инструкций пуст.")  # type: ignore[union-attr]
        await callback.answer()
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer("Выберите инструкцию для удаления:")  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Инструкции"),
        reply_markup=instruction_delete_pick_keyboard(instructions),
    )
    await callback.answer()


@router.message(Command("instruction_delete"))
async def cmd_instruction_delete(message: Message, session: AsyncSession) -> None:
    admin = await _require_admin(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not admin:
        return
    instructions = await repo.list_instructions(session)
    if not instructions:
        await message.answer("Список инструкций пуст.")
        return
    await message.answer("Выберите инструкцию для удаления:")
    await message.answer(
        menu_title("Инструкции"),
        reply_markup=instruction_delete_pick_keyboard(instructions),
    )


@router.callback_query(lambda cb: cb.data and cb.data.startswith("instr:del_pick:"))
async def instr_del_pick(callback: CallbackQuery, session: AsyncSession) -> None:
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer()
        return
    parts = (callback.data or "").split(":", 2)
    if len(parts) < 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        iid = uuid.UUID(hex=parts[2])
    except ValueError:
        await callback.answer("Инструкция не найдена.", show_alert=True)
        return
    inst = await repo.get_instruction(session, iid)
    if not inst:
        await callback.answer("Инструкция уже удалена.", show_alert=True)
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        f"Удалить инструкцию «{inst.title}»?",
    )
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Инструкции"),
        reply_markup=instruction_delete_confirm_keyboard(iid),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("instr:del_confirm:"))
async def instr_del_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer()
        return
    parts = (callback.data or "").split(":", 2)
    if len(parts) < 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        iid = uuid.UUID(hex=parts[2])
    except ValueError:
        await callback.answer("Инструкция не найдена.", show_alert=True)
        return
    ok = await repo.delete_instruction(session, iid)
    await callback.message.delete()  # type: ignore[union-attr]
    if ok:
        await _send_instructions_submenu(
            session,
            callback.message.answer,  # type: ignore[union-attr]
            admin,
            success_message="Удалено.",
        )
    else:
        await _send_instructions_submenu(
            session,
            callback.message.answer,  # type: ignore[union-attr]
            admin,
            success_message="Инструкция уже была удалена.",
        )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "instr:del_cancel")
async def instr_del_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
    """Cancel always leads to main menu (legacy callback for old messages)."""
    admin = await _require_admin(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not admin:
        await callback.answer()
        return
    await callback.message.delete()  # type: ignore[union-attr]
    instructions = await repo.list_instructions(session)
    has_instructions = len(instructions) > 0
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Главное меню"),
        reply_markup=main_menu_keyboard(admin.role, has_instructions=has_instructions),
    )
    await callback.answer("Отменено.")


def bot_instruction_commands() -> list[BotCommand]:
    return [
        BotCommand(command="instructions", description="Список инструкций"),
        BotCommand(command="instruction_add", description="Добавить инструкцию (админ)"),
        BotCommand(command="instruction_edit", description="Изменить инструкцию (админ)"),
        BotCommand(command="instruction_delete", description="Удалить инструкцию (админ)"),
    ]
