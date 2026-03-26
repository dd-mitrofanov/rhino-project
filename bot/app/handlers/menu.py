from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BotCommand, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repositories as repo
from app.handlers.instructions import bot_instruction_commands
from app.keyboards.menus import (
    friends_submenu_keyboard,
    instructions_manage_submenu_keyboard,
    instructions_submenu_keyboard,
    keys_submenu_keyboard,
    main_menu_keyboard,
    menu_title,
    users_submenu_keyboard,
)


async def _send_main_menu(session, answer_func, user) -> None:  # noqa: ANN001
    """Send main menu; used by m:back and others."""
    instructions = await repo.list_instructions(session)
    has_instructions = len(instructions) > 0
    await answer_func(
        menu_title("Главное меню"),
        reply_markup=main_menu_keyboard(user.role, has_instructions=has_instructions),
    )

router = Router()


@router.callback_query(lambda cb: cb.data == "m:back")
async def callback_back(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.message.delete()  # type: ignore[union-attr]
    user = await repo.get_user(session, callback.from_user.id)  # type: ignore[union-attr]
    if not user:
        await callback.message.answer("Вы не зарегистрированы")  # type: ignore[union-attr]
    else:
        await _send_main_menu(session, callback.message.answer, user)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "m:keys")
async def callback_keys(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await repo.get_user(session, callback.from_user.id)  # type: ignore[union-attr]
    if not user:
        await callback.message.answer("Вы не зарегистрированы.")  # type: ignore[union-attr]
        await callback.answer()
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Ключи"),
        reply_markup=keys_submenu_keyboard(user.role),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "m:friends")
async def callback_friends(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await repo.get_user(session, callback.from_user.id)  # type: ignore[union-attr]
    if not user or user.role not in ("admin", "l1"):
        await callback.answer("У вас нет прав для этой команды.", show_alert=True)
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Мои друзья"),
        reply_markup=friends_submenu_keyboard(),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "m:instr")
async def callback_instructions(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await repo.get_user(session, callback.from_user.id)  # type: ignore[union-attr]
    if not user:
        await callback.message.answer("Вы не зарегистрированы.")  # type: ignore[union-attr]
        await callback.answer()
        return
    instructions = await repo.list_instructions(session)
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Инструкции"),
        reply_markup=instructions_submenu_keyboard(instructions),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "m:instr:manage")
async def callback_instructions_manage(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await repo.get_user(session, callback.from_user.id)  # type: ignore[union-attr]
    if not user or user.role != "admin":
        await callback.answer("У вас нет прав для этой команды.", show_alert=True)
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Управление инструкциями"),
        reply_markup=instructions_manage_submenu_keyboard(),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "m:users")
async def callback_users(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await repo.get_user(session, callback.from_user.id)  # type: ignore[union-attr]
    if not user or user.role != "admin":
        await callback.answer("У вас нет прав для этой команды.", show_alert=True)
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Пользователи"),
        reply_markup=users_submenu_keyboard(),
    )
    await callback.answer()


def bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="instructions", description="Инструкции"),
    ]


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession) -> None:
    user = await repo.get_user(session, message.from_user.id)  # type: ignore[union-attr]
    if not user:
        await message.answer("Вы не зарегистрированы. Используйте /start для начала.")
        return
    await _send_main_menu(session, message.answer, user)
