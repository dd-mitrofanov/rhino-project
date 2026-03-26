from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repositories as repo
from app.keyboards.menus import (
    back_to_main_keyboard,
    confirm_delete_keyboard,
    main_menu_keyboard,
    menu_title,
    user_list_keyboard,
)
from app.xray.subscription_email import remove_subscription_from_xray

logger = logging.getLogger(__name__)

router = Router()


async def _check_admin(session: AsyncSession, telegram_id: int, answer_func) -> bool:  # noqa: ANN001
    user = await repo.get_user(session, telegram_id)
    if not user or user.role != "admin":
        await answer_func("У вас нет прав для этой команды.")
        return False
    return True


async def _show_delete_user_list(
    session: AsyncSession,
    answer_func,  # noqa: ANN001
    *,
    with_menu_format: bool = False,
) -> None:
    users = await repo.list_users(session)
    non_admin = [u for u in users if u.role != "admin"]
    if not non_admin:
        text = f"{menu_title('Удалить пользователя')}\n\nНет пользователей для удаления."
        await answer_func(text, reply_markup=back_to_main_keyboard())
        return
    if with_menu_format:
        text = f"{menu_title('Удалить пользователя')}\n\nВыберите пользователя для удаления:"
    else:
        text = "Выберите пользователя для удаления:"
    await answer_func(text, reply_markup=user_list_keyboard(users))


@router.message(Command("delete"))
async def cmd_delete(message: Message, session: AsyncSession) -> None:
    if not await _check_admin(session, message.from_user.id, message.answer):  # type: ignore[union-attr]
        return
    await _show_delete_user_list(session, message.answer)


@router.callback_query(lambda cb: cb.data == "m:users:delete")
async def menu_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(session, callback.from_user.id, callback.message.answer):  # type: ignore[union-attr]
        await callback.answer()
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await _show_delete_user_list(
        session,
        callback.message.answer,  # type: ignore[union-attr]
        with_menu_format=True,
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("delete_select:"))
async def delete_select(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(session, callback.from_user.id, callback.message.answer):  # type: ignore[union-attr]
        await callback.answer()
        return

    target_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    target_user = await repo.get_user(session, target_id)
    if not target_user:
        await callback.answer("Пользователь не найден.")
        return

    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        f"{menu_title('Удалить пользователя')}\n\n"
        f"Удалить пользователя {target_user.full_name} и всех приглашённых им? "
        "Это действие необратимо.",
        reply_markup=confirm_delete_keyboard(target_id),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("delete_confirm:"))
async def delete_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(session, callback.from_user.id, callback.message.answer):  # type: ignore[union-attr]
        await callback.answer()
        return

    target_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    count, deactivated_subs = await repo.delete_user_tree(session, target_id)

    for sub in deactivated_subs:
        try:
            await remove_subscription_from_xray(sub)
        except Exception:
            logger.warning(
                "Failed to remove Xray client for subscription %s",
                sub.id,
                exc_info=True,
            )

    user = await repo.get_user(session, callback.from_user.id)  # type: ignore[union-attr]
    instructions = await repo.list_instructions(session)
    has_instructions = len(instructions) > 0
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(f"Удалено пользователей: {count}.")  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Главное меню"),
        reply_markup=main_menu_keyboard(user.role, has_instructions=has_instructions),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "delete_cancel")
async def delete_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
    """Cancel always leads to main menu (legacy callback for old messages)."""
    user = await repo.get_user(session, callback.from_user.id)  # type: ignore[union-attr]
    await callback.message.delete()  # type: ignore[union-attr]
    if user:
        instructions = await repo.list_instructions(session)
        has_instructions = len(instructions) > 0
        await callback.message.answer(  # type: ignore[union-attr]
            menu_title("Главное меню"),
            reply_markup=main_menu_keyboard(user.role, has_instructions=has_instructions),
        )
    await callback.answer()
