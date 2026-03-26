from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repositories as repo
from app.keyboards.menus import (
    friends_list_empty_keyboard,
    friends_revoke_confirm_keyboard,
    friends_revoke_list_keyboard,
    friends_submenu_keyboard,
    invite_role_keyboard,
    main_menu_keyboard,
    menu_title,
)
from app.xray.subscription_email import remove_subscription_from_xray

logger = logging.getLogger(__name__)
router = Router()


async def _get_user_or_deny(
    session: AsyncSession,
    telegram_id: int,
    answer_func,  # noqa: ANN001
) -> repo.User | None:
    user = await repo.get_user(session, telegram_id)
    if not user or user.role == "l2":
        await answer_func("У вас нет прав для этой команды.")
        return None
    return user


def _format_invite_message(created_at, link: str) -> str:
    """Format invite as: 1. Приглашение. DD/MM/YYYY + plain link."""
    date_str = created_at.strftime("%d/%m/%Y") if created_at else "—"
    return f"Приглашение. {date_str}\n{link}"


async def _generate_and_send(
    session: AsyncSession,
    created_by: int,
    target_role: str,
    answer_func,  # noqa: ANN001
    bot: Bot,
    *,
    with_friends_menu: bool = False,
) -> None:
    code = repo.generate_code()
    invitation = await repo.create_invitation(session, code, created_by, target_role)
    await session.refresh(invitation)  # load created_at from DB

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"

    # 1. Send main menu first (same as key generation)
    if with_friends_menu:
        inviter = await repo.get_user(session, created_by)
        if inviter:
            instructions = await repo.list_instructions(session)
            has_instructions = len(instructions) > 0
            await answer_func(
                menu_title("Главное меню"),
                reply_markup=main_menu_keyboard(
                    inviter.role, has_instructions=has_instructions,
                ),
            )

    # 2. Send invite in separate message
    invite_text = _format_invite_message(invitation.created_at, link)
    await answer_func(invite_text)


@router.message(Command("invite"))
async def cmd_invite(message: Message, session: AsyncSession, bot: Bot) -> None:
    user = await _get_user_or_deny(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not user:
        return

    if user.role == "admin":
        await message.answer("Выберите роль для приглашения.")
        await message.answer(
            menu_title("Мои друзья"),
            reply_markup=invite_role_keyboard(),
        )
    else:
        await _generate_and_send(
            session, user.telegram_id, "l2", message.answer, bot,
            with_friends_menu=True,
        )


@router.callback_query(lambda cb: cb.data == "m:friends:invite")
async def menu_friends_invite(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    user = await _get_user_or_deny(session, callback.from_user.id, callback.message.answer)  # type: ignore[union-attr]
    if not user:
        await callback.answer()
        return

    await callback.message.delete()  # type: ignore[union-attr]
    if user.role == "admin":
        await callback.message.answer("Выберите роль для приглашения.")  # type: ignore[union-attr]
        await callback.message.answer(  # type: ignore[union-attr]
            menu_title("Мои друзья"),
            reply_markup=invite_role_keyboard(),
        )
    else:
        await _generate_and_send(
            session,
            user.telegram_id,
            "l2",
            callback.message.answer,  # type: ignore[union-attr]
            bot,
            with_friends_menu=True,
        )

    await callback.answer()


@router.callback_query(lambda cb: cb.data == "m:friends:list")
async def menu_friends_list(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user_or_deny(session, callback.from_user.id, callback.message.answer)  # type: ignore[union-attr]
    if not user:
        await callback.answer()
        return

    friends = await repo.list_users_invited_by(session, user.telegram_id)
    await callback.message.delete()  # type: ignore[union-attr]
    if not friends:
        await callback.message.answer("Вы никого не пригласили.")  # type: ignore[union-attr]
        await callback.message.answer(  # type: ignore[union-attr]
            menu_title("Мои друзья"),
            reply_markup=friends_list_empty_keyboard(),
        )
    else:
        lines = ["Ваши приглашённые:\n"]
        for f in friends:
            status = "активен" if f.active else "отозван"
            lines.append(f"• {f.full_name} ({f.telegram_id}) — {status}")
        await callback.message.answer("\n".join(lines))  # type: ignore[union-attr]
        await callback.message.answer(  # type: ignore[union-attr]
            menu_title("Мои друзья"),
            reply_markup=friends_submenu_keyboard(),
        )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "m:friends:revoke")
async def menu_friends_revoke(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user_or_deny(session, callback.from_user.id, callback.message.answer)  # type: ignore[union-attr]
    if not user:
        await callback.answer()
        return

    friends = await repo.list_users_invited_by(session, user.telegram_id)
    active_friends = [f for f in friends if f.active]
    await callback.message.delete()  # type: ignore[union-attr]
    if not active_friends:
        await callback.message.answer(  # type: ignore[union-attr]
            "Нет активных приглашённых для отзыва.",
        )
        await callback.message.answer(  # type: ignore[union-attr]
            menu_title("Мои друзья"),
            reply_markup=friends_submenu_keyboard(),
        )
    else:
        await callback.message.answer(  # type: ignore[union-attr]
            "Выберите пользователя для отзыва доступа:",
        )
        await callback.message.answer(  # type: ignore[union-attr]
            menu_title("Мои друзья"),
            reply_markup=friends_revoke_list_keyboard(active_friends),
        )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("friends_revoke_pick:"))
async def friends_revoke_pick(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user_or_deny(session, callback.from_user.id, callback.message.answer)  # type: ignore[union-attr]
    if not user:
        await callback.answer()
        return

    target_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    friends = await repo.list_users_invited_by(session, user.telegram_id)
    target = next((f for f in friends if f.telegram_id == target_id), None)
    if not target or not target.active:
        await callback.answer("Пользователь не найден или доступ уже отозван.")
        return

    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        f"Отозвать доступ у {target.full_name}?\nВсе ключи будут деактивированы.",
    )
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Мои друзья"),
        reply_markup=friends_revoke_confirm_keyboard(target_id),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("friends_revoke_confirm:"))
async def friends_revoke_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user_or_deny(session, callback.from_user.id, callback.message.answer)  # type: ignore[union-attr]
    if not user:
        await callback.answer()
        return

    target_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    friends = await repo.list_users_invited_by(session, user.telegram_id)
    target = next((f for f in friends if f.telegram_id == target_id), None)
    if not target or not target.active:
        await callback.message.answer("Пользователь не найден или доступ уже отозван.")  # type: ignore[union-attr]
        await callback.answer()
        return

    deactivated_subs = await repo.deactivate_user_subscriptions(session, target_id)
    await repo.deactivate_user(session, target_id)
    await session.commit()

    for sub in deactivated_subs:
        try:
            await remove_subscription_from_xray(sub)
        except Exception:
            logger.warning(
                "Failed to remove Xray client for subscription %s",
                sub.id,
                exc_info=True,
            )

    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        f"Доступ пользователя {target.full_name} отозван.",
    )
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Мои друзья"),
        reply_markup=friends_submenu_keyboard(),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "friends_revoke_cancel")
async def friends_revoke_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user_or_deny(session, callback.from_user.id, callback.message.answer)  # type: ignore[union-attr]
    if not user:
        await callback.answer()
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Мои друзья"),
        reply_markup=friends_submenu_keyboard(),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("invite_role:"))
async def invite_role_callback(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    user = await _get_user_or_deny(session, callback.from_user.id, callback.message.answer)  # type: ignore[union-attr]
    if not user:
        await callback.answer()
        return

    target_role = callback.data.split(":")[1]  # type: ignore[union-attr]
    if target_role not in ("l1", "l2"):
        await callback.answer("Недопустимая роль.")
        return

    # L1 users may only invite L2
    if user.role == "l1" and target_role != "l2":
        await callback.answer("Вы можете приглашать только L2.")
        return

    await _generate_and_send(
        session,
        user.telegram_id,
        target_role,
        callback.message.answer,  # type: ignore[union-attr]
        bot,
        with_friends_menu=True,
    )
    await callback.answer()
