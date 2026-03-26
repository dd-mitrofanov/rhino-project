from __future__ import annotations

import uuid
from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Instruction, Subscription, User


def menu_title(name: str) -> str:
    """Format menu title with fixed-width separator for consistent menu width."""
    return f"{name}:\n\n Выберите действие из списка ниже:"


# Preset device code → label stored in Subscription.label (and shown in UI).
# Order matches `label_keyboard()` preset rows.
LABEL_PRESET_LABELS: dict[str, str] = {
    "pc": "ПК/Ноутбук",
    "phone": "Телефон",
    "tablet": "Планшет",
    "tv": "ТВ",
}


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Single button: ◀ Назад (m:back)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀ Назад", callback_data="m:back")],
        ],
    )


def broadcast_sending_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены во время рассылки (callback broadcast:cancel)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отменить", callback_data="broadcast:cancel")],
        ],
    )


def broadcast_prompt_keyboard() -> InlineKeyboardMarkup:
    """Назад в главное меню из шага ввода рассылки (broadcast:back)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="broadcast:back")],
        ],
    )


def main_menu_button_keyboard() -> InlineKeyboardMarkup:
    """Под сообщением с ключом: открыть главное меню (тот же callback, что у «Назад»)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Главное меню", callback_data="m:back")],
        ],
    )


def main_menu_keyboard(role: str, *, has_instructions: bool = True) -> InlineKeyboardMarkup:
    """Top-level menu: Ключи, Мои друзья (admin/L1), Инструкции (if any), admin-only."""
    buttons: list[list[InlineKeyboardButton]] = []
    buttons.append([InlineKeyboardButton(text="Ключи", callback_data="m:keys")])
    if role in ("admin", "l1"):
        buttons.append([InlineKeyboardButton(text="Мои друзья", callback_data="m:friends")])
    if has_instructions:
        buttons.append([InlineKeyboardButton(text="Инструкции", callback_data="m:instr")])
    if role == "admin":
        buttons.append([InlineKeyboardButton(text="Управление инструкциями", callback_data="m:instr:manage")])
        buttons.append([InlineKeyboardButton(text="Пользователи", callback_data="m:users")])
        buttons.append([InlineKeyboardButton(text="Рассылка", callback_data="m:broadcast")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def keys_submenu_keyboard(role: str) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Создать ключ", callback_data="m:keys:add")],
        [InlineKeyboardButton(text="Удалить ключ", callback_data="m:keys:del")],
        [InlineKeyboardButton(text="Мои ключи", callback_data="m:keys:list")],
    ]
    if role == "admin":
        buttons.append([InlineKeyboardButton(text="Ключи пользователей", callback_data="m:keys:admin")])
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="m:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def friends_revoke_list_keyboard(users: Sequence[User]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"{u.full_name} ({u.telegram_id})",
            callback_data=f"friends_revoke_pick:{u.telegram_id}",
        )]
        for u in users
        if u.active
    ]
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="m:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def friends_list_empty_keyboard() -> InlineKeyboardMarkup:
    """Back button when friends list is empty."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="m:friends")]],
    )


def friends_revoke_confirm_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, отозвать",
                    callback_data=f"friends_revoke_confirm:{telegram_id}",
                ),
                InlineKeyboardButton(text="Отмена", callback_data="friends_revoke_cancel"),
            ],
        ],
    )


def friends_submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пригласить", callback_data="m:friends:invite")],
            [InlineKeyboardButton(text="Отозвать доступ", callback_data="m:friends:revoke")],
            [InlineKeyboardButton(text="Список друзей", callback_data="m:friends:list")],
            [InlineKeyboardButton(text="◀ Назад", callback_data="m:back")],
        ],
    )


def instructions_submenu_keyboard(
    instructions: Sequence[Instruction],
) -> InlineKeyboardMarkup:
    """Instructions list for all users (admin management is in m:instr:manage)."""
    buttons: list[list[InlineKeyboardButton]] = []
    for i in instructions:
        buttons.append([
            InlineKeyboardButton(
                text=_truncate_inline_button(i.title),
                callback_data=f"m:instr:open:{i.id.hex}",
            ),
        ])
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="m:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def instructions_manage_submenu_keyboard() -> InlineKeyboardMarkup:
    """Admin-only: Create, Edit, Delete instructions."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Создать инструкцию", callback_data="m:instr:add")],
            [InlineKeyboardButton(text="Изменить инструкцию", callback_data="m:instr:edit")],
            [InlineKeyboardButton(text="Удалить инструкцию", callback_data="m:instr:del")],
            [InlineKeyboardButton(text="◀ Назад", callback_data="m:back")],
        ],
    )


def users_submenu_keyboard() -> InlineKeyboardMarkup:
    """Admin-only: List users, Delete user."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Список пользователей", callback_data="m:users:list")],
            [InlineKeyboardButton(text="Удалить пользователя", callback_data="m:users:delete")],
            [InlineKeyboardButton(text="◀ Назад", callback_data="m:back")],
        ],
    )


def invite_role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Пригласить L1", callback_data="invite_role:l1"),
                InlineKeyboardButton(text="Пригласить L2", callback_data="invite_role:l2"),
            ],
            [InlineKeyboardButton(text="◀ Назад", callback_data="m:friends")],
        ],
    )


def user_list_keyboard(users: Sequence[User]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{u.full_name} ({u.telegram_id})",
                callback_data=f"delete_select:{u.telegram_id}",
            ),
            InlineKeyboardButton(
                text="📋 Ключи",
                callback_data=f"admin_sub_list:{u.telegram_id}",
            ),
        ]
        for u in users
        if u.role != "admin"
    ]
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="m:users")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_delete_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data=f"delete_confirm:{telegram_id}"),
                InlineKeyboardButton(text="Отмена", callback_data="m:back"),
            ],
        ],
    )


def admin_subs_user_list_keyboard(users: Sequence[User]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{u.full_name} ({u.telegram_id})",
                callback_data=f"admin_sub_list:{u.telegram_id}",
            ),
        ]
        for u in users
    ]
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="m:keys")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subscription_single_revoke_keyboard(subscription: Subscription) -> InlineKeyboardMarkup:
    """Single-key keyboard for admin: revoke button (only if active)."""
    buttons: list[list[InlineKeyboardButton]] = []
    if subscription.active:
        buttons.append([
            InlineKeyboardButton(
                text=f"🚫 Отозвать: {subscription.label}",
                callback_data=f"admin_sub_revoke:{subscription.id}",
            ),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_subscription_list_back_keyboard(
    user_telegram_id: int,
    *,
    has_active: bool = False,
) -> InlineKeyboardMarkup:
    """Back to keys admin; optionally include 'Revoke ALL' button."""
    rows: list[list[InlineKeyboardButton]] = []
    if has_active:
        rows.append([
            InlineKeyboardButton(
                text="🚫 Отозвать ВСЕ",
                callback_data=f"admin_sub_revoke_all:{user_telegram_id}",
            ),
        ])
    rows.append([InlineKeyboardButton(text="◀ Назад", callback_data="m:keys:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_revoke_keyboard(subscription_id: uuid.UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, отозвать",
                    callback_data=f"admin_sub_revoke_confirm:{subscription_id}",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="m:back",
                ),
            ],
        ],
    )


def label_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=display_label,
                callback_data=f"sub_label:preset:{code}",
            ),
        ]
        for code, display_label in LABEL_PRESET_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text="Задать своё", callback_data="sub_label:custom")])
    rows.append([InlineKeyboardButton(text="Пропустить", callback_data="sub_label:skip")])
    rows.append([InlineKeyboardButton(text="◀ Назад", callback_data="m:keys")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscription_single_delete_keyboard(subscription: Subscription) -> InlineKeyboardMarkup:
    """Single-key keyboard: delete button for one subscription."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🗑 Удалить: {subscription.label}",
                callback_data=f"sub_delete:{subscription.id}",
            )],
        ],
    )


def subscription_list_back_keyboard() -> InlineKeyboardMarkup:
    """Back button for keys list (used on empty state or hint message)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="m:keys")]],
    )


def _truncate_inline_button(text: str, max_len: int = 64) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def instructions_list_keyboard(instructions: Sequence[Instruction]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_truncate_inline_button(i.title),
                callback_data=f"instr:open:{i.id.hex}",
            ),
        ]
        for i in instructions
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def instruction_edit_pick_keyboard(instructions: Sequence[Instruction]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_truncate_inline_button(i.title),
                callback_data=f"instr:edit_pick:{i.id.hex}",
            ),
        ]
        for i in instructions
    ]
    rows.append([InlineKeyboardButton(text="◀ Назад", callback_data="m:instr:manage")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def instruction_delete_pick_keyboard(instructions: Sequence[Instruction]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_truncate_inline_button(i.title),
                callback_data=f"instr:del_pick:{i.id.hex}",
            ),
        ]
        for i in instructions
    ]
    rows.append([InlineKeyboardButton(text="◀ Назад", callback_data="m:instr:manage")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def instruction_edit_submenu_keyboard(instruction_id: uuid.UUID) -> InlineKeyboardMarkup:
    hid = instruction_id.hex
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Изменить название",
                    callback_data=f"instr:edit_title:{hid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Заменить текст или фото",
                    callback_data=f"instr:edit_media:{hid}",
                ),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="m:back")],
        ],
    )


def instruction_delete_confirm_keyboard(instruction_id: uuid.UUID) -> InlineKeyboardMarkup:
    hid = instruction_id.hex
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить",
                    callback_data=f"instr:del_confirm:{hid}",
                ),
                InlineKeyboardButton(text="Отмена", callback_data="m:back"),
            ],
        ],
    )
