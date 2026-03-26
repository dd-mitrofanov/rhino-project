from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repositories as repo
from app.db.models import User
from app.keyboards.menus import back_to_main_keyboard, menu_title

router = Router()

# Telegram message limit is 4096; reserve space for <pre></pre> and html.escape.
_TELEGRAM_MAX = 4096
_PRE_HTML_OVERHEAD = len("<pre></pre>") + 32


def _tree_html_block(tree_segment: str) -> str:
    return f"<pre>{escape(tree_segment)}</pre>"


def _build_tree_text(users: list[User]) -> str:
    by_parent: dict[int | None, list[User]] = {}
    for u in users:
        by_parent.setdefault(u.invited_by, []).append(u)
    for group in by_parent.values():
        group.sort(key=lambda u: u.created_at)

    lines: list[str] = []

    def _walk(user: User, prefix: str, is_last: bool) -> None:
        children = by_parent.get(user.telegram_id, [])
        has_children = len(children) > 0
        display = user.full_name
        id_part = f"[{user.telegram_id}]"

        if not prefix:
            lines.append(f"{display} {id_part}")
        else:
            branch = "└─" if is_last else "├─"
            mid = " "
            lines.append(f"{prefix}{branch}{mid}{display} {id_part}")

        child_prefix = prefix + ("   " if is_last else "│  ") if prefix else "  "
        for i, child in enumerate(children):
            _walk(child, child_prefix, i == len(children) - 1)

    roots = by_parent.get(None, [])
    for i, root in enumerate(roots):
        _walk(root, "", i == len(roots) - 1)

    return "\n".join(lines) if lines else "Пользователей пока нет."


def _chunk_text(
    text: str,
    max_len: int,
    *,
    first_max: int | None = None,
) -> list[str]:
    """Split text into chunks at line boundaries; first chunk may use a smaller limit."""
    if not text:
        return []
    limit0 = first_max if first_max is not None else max_len
    lines = text.split("\n")
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    cap = limit0

    for line in lines:
        extra = 1 if buf else 0
        if len(line) > cap:
            if buf:
                chunks.append("\n".join(buf))
                buf = []
                size = 0
            for j in range(0, len(line), cap):
                chunks.append(line[j : j + cap])
            cap = max_len
            continue
        if size + len(line) + extra > cap:
            chunks.append("\n".join(buf))
            buf = [line]
            size = len(line)
            cap = max_len
        else:
            buf.append(line)
            size += len(line) + extra
    if buf:
        chunks.append("\n".join(buf))
    return chunks


async def _send_user_tree(
    session: AsyncSession,
    answer_func,  # noqa: ANN001
    *,
    with_menu_format: bool = False,
) -> None:
    users = await repo.list_users(session)
    tree = _build_tree_text(users)

    inner_limit = _TELEGRAM_MAX - _PRE_HTML_OVERHEAD

    if with_menu_format:
        header = f"{menu_title('Пользователи')}\n\n"
        first_inner = max(1, _TELEGRAM_MAX - len(header) - _PRE_HTML_OVERHEAD)
        parts = _chunk_text(tree, inner_limit, first_max=first_inner)
        if not parts:
            await answer_func(
                header.strip(),
                reply_markup=back_to_main_keyboard(),
                parse_mode="HTML",
            )
            return
        await answer_func(
            header + _tree_html_block(parts[0]),
            reply_markup=back_to_main_keyboard(),
            parse_mode="HTML",
        )
        for segment in parts[1:]:
            await answer_func(_tree_html_block(segment), parse_mode="HTML")
    else:
        for segment in _chunk_text(tree, inner_limit):
            await answer_func(_tree_html_block(segment), parse_mode="HTML")


@router.message(Command("users"))
async def cmd_users(message: Message, session: AsyncSession) -> None:
    user = await repo.get_user(session, message.from_user.id)  # type: ignore[union-attr]
    if not user or user.role != "admin":
        await message.answer("У вас нет прав для этой команды.")
        return

    await _send_user_tree(session, message.answer)


@router.callback_query(lambda cb: cb.data == "m:users:list")
async def menu_users_list(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await repo.get_user(session, callback.from_user.id)
    if not user or user.role != "admin":
        await callback.answer("У вас нет прав для этой команды.", show_alert=True)
        return

    await callback.message.delete()  # type: ignore[union-attr]
    await _send_user_tree(
        session,
        callback.message.answer,  # type: ignore[union-attr]
        with_menu_format=True,
    )
    await callback.answer()
