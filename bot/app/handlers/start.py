from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import repositories as repo
from app.keyboards.menus import main_menu_keyboard, menu_title

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, command: CommandObject) -> None:
    from_user = message.from_user  # type: ignore[union-attr]
    telegram_id = from_user.id
    first_name = from_user.first_name or "User"
    last_name = from_user.last_name
    username = from_user.username

    existing = await repo.get_user(session, telegram_id)
    if existing and existing.active:
        instructions = await repo.list_instructions(session)
        has_instructions = len(instructions) > 0
        await message.answer(
            f"{menu_title('Главное меню')}\n\nВы уже зарегистрированы.",
            reply_markup=main_menu_keyboard(existing.role, has_instructions=has_instructions),
        )
        return

    # Auto-create admin on first /start from the configured admin Telegram ID
    if telegram_id == settings.ADMIN_TELEGRAM_ID:
        user = await repo.create_user(
            session, telegram_id, first_name, "admin",
            last_name=last_name, username=username,
        )
        instructions = await repo.list_instructions(session)
        has_instructions = len(instructions) > 0
        await message.answer(
            f"{menu_title('Главное меню')}\n\n"
            f"Добро пожаловать, {user.full_name}! Вы зарегистрированы как администратор.",
            reply_markup=main_menu_keyboard(user.role, has_instructions=has_instructions),
        )
        return

    code = command.args
    if not code:
        await message.answer(
            "Пожалуйста, используйте ссылку с кодом приглашения для регистрации.",
        )
        return

    invitation = await repo.get_invitation(session, code)
    if not invitation or invitation.used:
        await message.answer("Код приглашения недействителен.")
        return

    # Fallback for users without proper Telegram profile
    if not first_name or first_name == str(telegram_id):
        first_name = f"User {telegram_id}"

    if existing and not existing.active:
        # Re-invitation: reactivate revoked user
        await repo.reactivate_user(session, telegram_id)
        await repo.update_user_profile(
            session,
            telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            full_name=first_name + (f" {last_name}" if last_name else ""),
        )
        await repo.mark_invitation_used(session, code, telegram_id)

        user = await repo.get_user(session, telegram_id)
        instructions = await repo.list_instructions(session)
        has_instructions = len(instructions) > 0
        await message.answer(
            f"{menu_title('Главное меню')}\n\n"
            f"Добро пожаловать снова, {user.full_name}! Доступ восстановлен.",
            reply_markup=main_menu_keyboard(user.role, has_instructions=has_instructions),
        )
        return

    user = await repo.create_user(
        session,
        telegram_id,
        first_name,
        invitation.target_role,
        last_name=last_name,
        username=username,
        invited_by=invitation.created_by,
    )
    await repo.mark_invitation_used(session, code, telegram_id)

    instructions = await repo.list_instructions(session)
    has_instructions = len(instructions) > 0
    await message.answer(
        f"{menu_title('Главное меню')}\n\n"
        f"Добро пожаловать, {user.full_name}! Вы зарегистрированы.",
        reply_markup=main_menu_keyboard(user.role, has_instructions=has_instructions),
    )
