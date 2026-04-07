from __future__ import annotations

import html
import logging
import random
import uuid

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import repositories as repo
from app.db.engine import AsyncSessionLocal
from app.db.repositories import SubscriptionLimitError
from app.keyboards.menus import (
    LABEL_PRESET_LABELS,
    admin_subscription_list_back_keyboard,
    admin_subs_user_list_keyboard,
    confirm_revoke_keyboard,
    keys_submenu_keyboard,
    label_keyboard,
    main_menu_button_keyboard,
    main_menu_keyboard,
    menu_title,
    subscription_list_back_keyboard,
    subscription_single_delete_keyboard,
    subscription_single_revoke_keyboard,
    whitelist_choice_keyboard,
)
from app.hysteria.sync import sync_hysteria_credentials
from app.xray.grpc_client import XrayClientError, add_vless_client
from app.xray.subscription_email import (
    remove_subscription_from_xray,
    xray_subscription_email,
)

logger = logging.getLogger(__name__)

# Masculine singular adjective + noun pairs (independent choice; words are broadly combinable).
SKIP_LABEL_ADJECTIVES: tuple[str, ...] = (
    "тихий",
    "ясный",
    "светлый",
    "тёмный",
    "быстрый",
    "спокойный",
    "свежий",
    "ровный",
    "чёткий",
    "чистый",
    "мягкий",
    "крепкий",
    "широкий",
    "узкий",
    "глубокий",
    "высокий",
    "низкий",
    "дальний",
    "близкий",
    "яркий",
    "тёплый",
)

SKIP_LABEL_NOUNS: tuple[str, ...] = (
    "океан",
    "ветер",
    "лес",
    "поток",
    "холм",
    "мост",
    "сад",
    "путь",
    "берег",
    "ручей",
    "камень",
    "свет",
    "луч",
    "горизонт",
    "снег",
    "дождь",
    "звук",
    "дом",
    "утёс",
    "остров",
    "овраг",
)

_SUB_LABEL_UNKNOWN_CHOICE_RU = "Не удалось распознать выбор. Используйте кнопки меню."
_SUB_WL_STALE_RU = "Сессия устарела. Начните создание ключа заново через меню."

WHITELIST_PROMPT_RU = (
    "Выпустить ключ с поддержкой обхода блокировок по белым спискам? Выберите Да, только если вы планируете использовать данный ключ на телефоне и в вашем регионе блокируют мобильный интернет. Можно выпустить только 1 ключ для обхода белых списков"
)


def _keys_form_after_number(n: int) -> str:
    """Грамматическая форма «ключ» после числительного (1 ключ, 2 ключа, 5 ключей)."""
    if n % 10 == 1 and n % 100 != 11:
        return "ключ"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "ключа"
    return "ключей"


router = Router()


class SubAddStates(StatesGroup):
    waiting_for_label = State()
    waiting_for_whitelist_choice = State()


def _sub_url(subscription: repo.Subscription) -> str:
    return f"{settings.SUBSCRIPTION_BASE_URL}/{subscription.token}"


async def _get_registered_user(
    session: AsyncSession,
    telegram_id: int,
    answer_func,  # noqa: ANN001
) -> repo.User | None:
    user = await repo.get_user(session, telegram_id)
    if not user:
        await answer_func("Вы не зарегистрированы. Используйте /start для начала.")
        return None
    return user


def _format_key_message(
    name: str,
    created_at,
    url: str,
) -> str:
    """Format key/invite as: 1. <Name>. DD/MM/YYYY + HTML code block."""
    date_str = created_at.strftime("%d/%m/%Y") if created_at else "—"
    escaped = html.escape(url)
    return f"{name}. {date_str}\n<pre><code>{escaped}</code></pre>"


async def _resolve_whitelist_or_prompt(
    session: AsyncSession,
    user: repo.User,
    label: str,
    answer_func,  # noqa: ANN001
    state: FSMContext,
) -> bool:
    """Return True if creation ran (or limit error). False if whitelist prompt was shown."""
    if user.role == "admin":
        await state.clear()
        await _create_and_send_subscription(
            session,
            user.telegram_id,
            label,
            answer_func,
            role=user.role,
            is_whitelist=True,
        )
        return True

    if await repo.user_has_active_whitelist_subscription(session, user.telegram_id):
        await state.clear()
        await _create_and_send_subscription(
            session,
            user.telegram_id,
            label,
            answer_func,
            role=user.role,
            is_whitelist=False,
        )
        return True

    await state.set_state(SubAddStates.waiting_for_whitelist_choice)
    await state.update_data(pending_label=label)
    await answer_func(
        WHITELIST_PROMPT_RU,
        reply_markup=whitelist_choice_keyboard(),
    )
    return False


async def _create_and_send_subscription(
    session: AsyncSession,
    user_telegram_id: int,
    label: str,
    answer_func,  # noqa: ANN001
    *,
    role: str = "l1",
    is_whitelist: bool,
) -> None:
    try:
        subscription = await repo.create_subscription(
            session,
            user_telegram_id,
            label,
            role=role,
            is_whitelist=is_whitelist,
        )
    except SubscriptionLimitError:
        m = repo.MAX_ACTIVE_SUBSCRIPTIONS
        await answer_func(
            f"У вас уже {m} {_keys_form_after_number(m)}. "
            "Удалите один ключ, чтобы создать новый.",
        )
        return

    email = xray_subscription_email(subscription)
    xray_warning = ""
    try:
        await add_vless_client(
            settings.xray_grpc_endpoint_list,
            settings.XRAY_INBOUND_TAG,
            subscription.vless_uuid,
            email,
        )
    except XrayClientError:
        logger.warning("Total Xray gRPC failure for %s", email)
        xray_warning = (
            "\n\n⚠️ Ключ создан, но активация VPN может занять некоторое время."
        )
    except Exception:
        logger.exception("Unexpected error calling add_vless_client for %s", email)
        xray_warning = (
            "\n\n⚠️ Ключ создан, но активация VPN может занять некоторое время."
        )

    try:
        await sync_hysteria_credentials(AsyncSessionLocal)
    except Exception:
        logger.exception("Hysteria credential sync failed for %s", email)

    url = _sub_url(subscription)

    key_text = _format_key_message(label, subscription.created_at, url)
    if xray_warning:
        key_text += xray_warning
    await answer_func(
        key_text,
        reply_markup=main_menu_button_keyboard(),
        parse_mode="HTML",
    )


# ── Add Subscription ────────────────────────────────────────────────

@router.message(Command("sub_add"))
async def cmd_sub_add(
    message: Message, session: AsyncSession, state: FSMContext,
) -> None:
    user = await _get_registered_user(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not user:
        return
    await state.clear()
    await message.answer(
        "Выберите название для ключа:", reply_markup=label_keyboard(),
    )


@router.callback_query(lambda cb: cb.data == "m:keys:add")
async def menu_keys_add(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    user = await _get_registered_user(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not user:
        await callback.answer()
        return
    await state.clear()
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        f"{menu_title('Создать ключ')}\n\nВыберите название для ключа:",
        reply_markup=label_keyboard(),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("sub_label:"))
async def sub_label_chosen(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    user = await _get_registered_user(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not user:
        await callback.answer()
        return

    data = callback.data  # type: ignore[union-attr]
    parts = data.split(":", 2)

    if len(parts) < 2 or parts[0] != "sub_label":
        await callback.answer(_SUB_LABEL_UNKNOWN_CHOICE_RU, show_alert=True)
        return

    kind = parts[1]
    tail = parts[2] if len(parts) > 2 else ""

    if kind == "custom":
        if tail:
            await callback.answer(_SUB_LABEL_UNKNOWN_CHOICE_RU, show_alert=True)
            return
        await state.set_state(SubAddStates.waiting_for_label)
        await callback.message.answer(  # type: ignore[union-attr]
            "Введите название ключа (от 1 до 100 символов):",
        )
        await callback.answer()
        return

    if kind == "skip":
        if tail:
            await callback.answer(_SUB_LABEL_UNKNOWN_CHOICE_RU, show_alert=True)
            return
        label = f"{random.choice(SKIP_LABEL_ADJECTIVES)} {random.choice(SKIP_LABEL_NOUNS)}"
        logger.debug("sub_label skip: generated label=%r", label)
        await _resolve_whitelist_or_prompt(
            session,
            user,
            label,
            callback.message.answer,  # type: ignore[union-attr]
            state,
        )
        await callback.answer()
        return

    if kind == "preset":
        code = tail
        if not code:
            await callback.answer(_SUB_LABEL_UNKNOWN_CHOICE_RU, show_alert=True)
            return
        display = LABEL_PRESET_LABELS.get(code)
        if not display:
            await callback.answer(_SUB_LABEL_UNKNOWN_CHOICE_RU, show_alert=True)
            return
        logger.debug("sub_label preset: code=%r", code)
        await _resolve_whitelist_or_prompt(
            session,
            user,
            display,
            callback.message.answer,  # type: ignore[union-attr]
            state,
        )
        await callback.answer()
        return

    await callback.answer(_SUB_LABEL_UNKNOWN_CHOICE_RU, show_alert=True)


@router.message(SubAddStates.waiting_for_label)
async def sub_label_typed(
    message: Message, session: AsyncSession, state: FSMContext,
) -> None:
    user = await _get_registered_user(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not user:
        await state.clear()
        return

    label = (message.text or "").strip()
    if not label or len(label) > 100:
        await message.answer(
            "Название ключа: от 1 до 100 символов. Попробуйте ещё раз.",
        )
        return

    await _resolve_whitelist_or_prompt(
        session,
        user,
        label,
        message.answer,
        state,
    )


@router.callback_query(lambda cb: cb.data in ("sub_wl:yes", "sub_wl:no"))
async def sub_whitelist_chosen(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    user = await _get_registered_user(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not user:
        await callback.answer()
        return

    if await state.get_state() != SubAddStates.waiting_for_whitelist_choice.state:
        await callback.answer(_SUB_WL_STALE_RU, show_alert=True)
        return

    data = await state.get_data()
    label = data.get("pending_label")
    if not label or not isinstance(label, str):
        await callback.answer(_SUB_WL_STALE_RU, show_alert=True)
        return

    kind = (callback.data or "").split(":", 1)[-1]  # type: ignore[union-attr]
    is_whitelist = kind == "yes"

    await state.clear()
    await _create_and_send_subscription(
        session,
        callback.from_user.id,
        label,
        callback.message.answer,  # type: ignore[union-attr]
        role=user.role,
        is_whitelist=is_whitelist,
    )
    await callback.answer()


# ── List Subscriptions ──────────────────────────────────────────────

@router.message(Command("sub_list"))
async def cmd_sub_list(message: Message, session: AsyncSession) -> None:
    user = await _get_registered_user(session, message.from_user.id, message.answer)  # type: ignore[union-attr]
    if not user:
        return
    await _show_subscriptions(session, message.from_user.id, message.answer)


@router.callback_query(lambda cb: cb.data == "m:keys:list")
async def menu_keys_list(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_registered_user(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not user:
        await callback.answer()
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await _show_subscriptions(
        session,
        callback.from_user.id,  # type: ignore[union-attr]
        callback.message.answer,  # type: ignore[union-attr]
        user_role=user.role,
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "m:keys:del")
async def menu_keys_del(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_registered_user(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not user:
        await callback.answer()
        return
    await callback.message.delete()  # type: ignore[union-attr]
    await _show_subscriptions(
        session,
        callback.from_user.id,  # type: ignore[union-attr]
        callback.message.answer,  # type: ignore[union-attr]
        user_role=user.role,
    )
    await callback.answer()


async def _show_subscriptions(
    session: AsyncSession,
    user_telegram_id: int,
    answer_func,  # noqa: ANN001
    *,
    user_role: str | None = None,
) -> None:
    """Show keys list: each key in separate message, then usage hint."""
    subscriptions = await repo.list_user_subscriptions(
        session, user_telegram_id, active_only=True,
    )
    if not subscriptions:
        await answer_func(
            "У вас нет ключей. Используйте «Создать ключ», чтобы создать.",
        )
        if user_role is not None:
            await answer_func(
                menu_title("Ключи"),
                reply_markup=keys_submenu_keyboard(user_role),
            )
        else:
            await answer_func(menu_title("Ключи"))
        return

    total = len(subscriptions)
    for i, s in enumerate(subscriptions, 1):
        url = _sub_url(s)
        date_str = s.created_at.strftime("%d/%m/%Y") if s.created_at else "—"
        escaped = html.escape(url)
        text = f"{i}. {s.label}. {date_str}\n<pre><code>{escaped}</code></pre>"
        await answer_func(text, reply_markup=subscription_single_delete_keyboard(s), parse_mode="HTML")

    # Usage hint with Back button
    hint = (
        f"{total + 1}. Чтобы использовать ключ нажмите на него 1 раз, "
        'перейдите в приложение HAPP и нажмите "Вставить из буфера обмена"'
    )
    await answer_func(hint, reply_markup=subscription_list_back_keyboard())


# ── Delete Subscription ────────────────────────────────────────────


async def _perform_delete_own_subscription(
    session: AsyncSession,
    subscription: repo.Subscription,
    user: repo.User,
    callback: CallbackQuery,
) -> None:
    label = subscription.label

    await repo.deactivate_subscription(session, subscription.id)

    try:
        await remove_subscription_from_xray(subscription)
    except Exception:
        logger.exception(
            "Unexpected error calling remove_subscription_from_xray for %s",
            subscription.id,
        )

    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(f"Ключ «{label}» удалён.")  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Ключи"),
        reply_markup=keys_submenu_keyboard(user.role),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("sub_delete:"))
async def sub_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_registered_user(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not user:
        await callback.answer()
        return

    sub_id_str = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    try:
        sub_id = uuid.UUID(sub_id_str)
    except ValueError:
        await callback.answer("Неверный идентификатор ключа.")
        return

    subscription = await repo.get_subscription(session, sub_id)
    if not subscription or subscription.user_telegram_id != callback.from_user.id:
        await callback.message.answer("Ключ не найден.")  # type: ignore[union-attr]
        await callback.answer()
        return

    if not subscription.active:
        await callback.message.answer("Этот ключ уже деактивирован.")  # type: ignore[union-attr]
        await callback.answer()
        return

    await _perform_delete_own_subscription(session, subscription, user, callback)


@router.callback_query(lambda cb: cb.data == "sub_delete_cancel")
async def sub_delete_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
    """Cancel always leads to main menu (legacy callback for old messages)."""
    user = await _get_registered_user(
        session, callback.from_user.id, callback.message.answer,  # type: ignore[union-attr]
    )
    if not user:
        await callback.answer()
        return
    await callback.message.delete()  # type: ignore[union-attr]
    instructions = await repo.list_instructions(session)
    has_instructions = len(instructions) > 0
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Главное меню"),
        reply_markup=main_menu_keyboard(user.role, has_instructions=has_instructions),
    )
    await callback.answer()


# ── Admin: Subscription Management ────────────────────────────────

async def _check_admin(
    session: AsyncSession,
    telegram_id: int,
    answer_func,  # noqa: ANN001
) -> bool:
    user = await repo.get_user(session, telegram_id)
    if not user or user.role != "admin":
        await answer_func("У вас нет прав для этой команды.")
        return False
    return True


async def _show_admin_subscriptions(
    session: AsyncSession,
    target_id: int,
    target_name: str,
    answer_func,  # noqa: ANN001
) -> None:
    """Show user's keys: each key in separate message, same format as _show_subscriptions."""
    subscriptions = await repo.list_user_subscriptions(
        session, target_id, active_only=False,
    )
    if not subscriptions:
        await answer_func(f"У пользователя {target_name} нет ключей.")
        await answer_func(
            menu_title("Ключи пользователей"),
            reply_markup=admin_subscription_list_back_keyboard(target_id, has_active=False),
        )
        return

    for i, s in enumerate(subscriptions, 1):
        url = _sub_url(s)
        date_str = s.created_at.strftime("%d/%m/%Y") if s.created_at else "—"
        escaped = html.escape(url)
        text = f"{i}. {s.label}. {date_str}\n<pre><code>{escaped}</code></pre>"
        await answer_func(
            text,
            reply_markup=subscription_single_revoke_keyboard(s),
            parse_mode="HTML",
        )

    has_active = any(s.active for s in subscriptions)
    await answer_func(
        f"{len(subscriptions) + 1}. Ключи пользователя {target_name}.",
        reply_markup=admin_subscription_list_back_keyboard(target_id, has_active=has_active),
    )


async def _show_admin_subs_user_list(
    session: AsyncSession,
    answer_func,  # noqa: ANN001
) -> None:
    users = await repo.list_users(session)
    if not users:
        await answer_func("Нет пользователей.")
        await answer_func(
            menu_title("Ключи пользователей"),
            reply_markup=keys_submenu_keyboard("admin"),
        )
        return
    await answer_func("Выберите пользователя для просмотра ключей:")
    await answer_func(
        menu_title("Ключи пользователей"),
        reply_markup=admin_subs_user_list_keyboard(users),
    )


@router.callback_query(lambda cb: cb.data == "m:keys:admin")
async def menu_keys_admin(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(session, callback.from_user.id, callback.message.answer):  # type: ignore[union-attr]
        await callback.answer()
        return

    await callback.message.delete()  # type: ignore[union-attr]
    await _show_admin_subs_user_list(
        session,
        callback.message.answer,  # type: ignore[union-attr]
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("admin_sub_list:"))
async def admin_sub_list(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(session, callback.from_user.id, callback.message.answer):  # type: ignore[union-attr]
        await callback.answer()
        return

    target_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    target_user = await repo.get_user(session, target_id)
    if not target_user:
        await callback.message.answer("Пользователь не найден.")  # type: ignore[union-attr]
        await callback.answer()
        return

    await callback.message.delete()  # type: ignore[union-attr]
    await _show_admin_subscriptions(
        session,
        target_id,
        target_user.full_name,
        callback.message.answer,  # type: ignore[union-attr]
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("admin_sub_revoke:"))
async def admin_sub_revoke(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(session, callback.from_user.id, callback.message.answer):  # type: ignore[union-attr]
        await callback.answer()
        return

    sub_id_str = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    try:
        sub_id = uuid.UUID(sub_id_str)
    except ValueError:
        await callback.answer("Неверный идентификатор ключа.")
        return

    subscription = await repo.get_subscription(session, sub_id)
    if not subscription:
        await callback.answer("Ключ не найден.")
        return

    if not subscription.active:
        await callback.answer("Ключ уже отозван.")
        return

    target_user = await repo.get_user(session, subscription.user_telegram_id)
    user_name = target_user.full_name if target_user else str(subscription.user_telegram_id)

    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        f"Отозвать ключ «{subscription.label}» пользователя {user_name}?\n"
        "VPN-доступ будет заблокирован немедленно.",
    )
    await callback.message.answer(  # type: ignore[union-attr]
        menu_title("Ключи пользователей"),
        reply_markup=confirm_revoke_keyboard(subscription.id),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data and cb.data.startswith("admin_sub_revoke_confirm:"))
async def admin_sub_revoke_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(session, callback.from_user.id, callback.message.answer):  # type: ignore[union-attr]
        await callback.answer()
        return

    sub_id_str = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    try:
        sub_id = uuid.UUID(sub_id_str)
    except ValueError:
        await callback.answer("Неверный идентификатор ключа.")
        return

    subscription = await repo.get_subscription(session, sub_id)
    if not subscription or not subscription.active:
        await callback.message.answer("Ключ уже отозван или не найден.")  # type: ignore[union-attr]
        await callback.answer()
        return

    label = subscription.label

    await repo.deactivate_subscription(session, subscription.id)
    try:
        await remove_subscription_from_xray(subscription)
    except Exception:
        logger.warning(
            "Failed to remove Xray client for subscription %s",
            subscription.id,
            exc_info=True,
        )

    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        f"Ключ «{label}» отозван. VPN-доступ заблокирован.",
    )
    users = await repo.list_users(session)
    if users:
        await callback.message.answer(  # type: ignore[union-attr]
            menu_title("Ключи пользователей"),
            reply_markup=admin_subs_user_list_keyboard(users),
        )
    else:
        await callback.message.answer(  # type: ignore[union-attr]
            menu_title("Ключи пользователей"),
            reply_markup=keys_submenu_keyboard("admin"),
        )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "admin_sub_revoke_cancel")
async def admin_sub_revoke_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
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


@router.callback_query(lambda cb: cb.data and cb.data.startswith("admin_sub_revoke_all:"))
async def admin_sub_revoke_all(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(session, callback.from_user.id, callback.message.answer):  # type: ignore[union-attr]
        await callback.answer()
        return

    target_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    target_user = await repo.get_user(session, target_id)
    user_name = target_user.full_name if target_user else str(target_id)

    deactivated = await repo.deactivate_user_subscriptions(session, target_id)

    for sub in deactivated:
        try:
            await remove_subscription_from_xray(sub)
        except Exception:
            logger.warning(
                "Failed to remove Xray client for subscription %s",
                sub.id,
                exc_info=True,
            )

    n = len(deactivated)
    if n == 0:
        revoke_msg = f"У пользователя {user_name} не было активных ключей."
    else:
        revoke_msg = f"Отозвано {n} {_keys_form_after_number(n)} у пользователя {user_name}."
    users = await repo.list_users(session)
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.message.answer(revoke_msg)  # type: ignore[union-attr]
    if users:
        await callback.message.answer(  # type: ignore[union-attr]
            menu_title("Ключи пользователей"),
            reply_markup=admin_subs_user_list_keyboard(users),
        )
    else:
        await callback.message.answer(  # type: ignore[union-attr]
            menu_title("Ключи пользователей"),
            reply_markup=keys_submenu_keyboard("admin"),
        )
    await callback.answer()
