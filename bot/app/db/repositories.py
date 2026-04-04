from __future__ import annotations

import random
import secrets
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Instruction, InstructionPhoto, Invitation, Subscription, User


class SubscriptionLimitError(Exception):
    """Raised when a user already has the maximum number of active subscriptions."""


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.get(User, telegram_id)


async def create_user(
    session: AsyncSession,
    telegram_id: int,
    first_name: str,
    role: str,
    *,
    last_name: str | None = None,
    username: str | None = None,
    invited_by: int | None = None,
) -> User:
    full_name = first_name + (f" {last_name}" if last_name else "")
    user = User(
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        full_name=full_name,
        role=role,
        invited_by=invited_by,
    )
    session.add(user)
    await session.flush()
    return user


async def deactivate_user(session: AsyncSession, telegram_id: int) -> bool:
    """Set User.active=False. Returns True if user existed and was active."""
    result = await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id, User.active.is_(True))
        .values(active=False),
    )
    return result.rowcount > 0


async def reactivate_user(session: AsyncSession, telegram_id: int) -> bool:
    """Set User.active=True. Returns True if user existed and was inactive."""
    result = await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id, User.active.is_(False))
        .values(active=True),
    )
    return result.rowcount > 0


async def update_user_profile(
    session: AsyncSession,
    telegram_id: int,
    *,
    username: str | None,
    first_name: str,
    last_name: str | None,
    full_name: str,
) -> None:
    """Update user profile fields from Telegram. No-op if user does not exist."""
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(
            username=username,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
        ),
    )


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User).order_by(User.created_at),
    )
    return list(result.scalars().all())


async def list_active_users(session: AsyncSession) -> list[User]:
    """Users with active=True, ordered by created_at."""
    result = await session.execute(
        select(User)
        .where(User.active.is_(True))
        .order_by(User.created_at),
    )
    return list(result.scalars().all())


async def list_users_invited_by(
    session: AsyncSession,
    inviter_telegram_id: int,
) -> list[User]:
    """Return users where invited_by == inviter_telegram_id, ordered by created_at."""
    result = await session.execute(
        select(User)
        .where(User.invited_by == inviter_telegram_id)
        .order_by(User.created_at),
    )
    return list(result.scalars().all())


async def delete_user_tree(
    session: AsyncSession, telegram_id: int,
) -> tuple[int, list[Subscription]]:
    """Recursively delete a user and all descendants invited by them.

    Uses a recursive CTE to collect the full subtree, then deactivates
    subscriptions, batch-deletes invitations and users in one transaction.

    Returns ``(deleted_user_count, deactivated_subscriptions)`` so the
    caller can propagate Xray RemoveUser for each deactivated subscription.
    """
    tree = (
        select(User.telegram_id)
        .where(User.telegram_id == telegram_id)
        .cte(name="tree", recursive=True)
    )
    tree = tree.union_all(
        select(User.telegram_id).where(User.invited_by == tree.c.telegram_id),
    )

    result = await session.execute(select(tree.c.telegram_id))
    ids = [row[0] for row in result.all()]

    if not ids:
        return 0, []

    # 0. Deactivate subscriptions for all users in the tree.
    deactivated: list[Subscription] = []
    for uid in ids:
        deactivated.extend(await deactivate_user_subscriptions(session, uid))

    # 1. Remove invitations created by tree users.
    await session.execute(
        delete(Invitation).where(Invitation.created_by.in_(ids)),
    )

    # 2. Detach used_by references for invitations created by *other* users.
    await session.execute(
        update(Invitation)
        .where(Invitation.used_by.in_(ids))
        .values(used_by=None),
    )

    # 3. Break self-referencing FK (invited_by) so the batch DELETE succeeds
    #    regardless of row-evaluation order.
    await session.execute(
        update(User)
        .where(User.telegram_id.in_(ids))
        .values(invited_by=None),
    )

    # 4. Delete subscriptions (they reference users via user_telegram_id).
    await session.execute(
        delete(Subscription).where(Subscription.user_telegram_id.in_(ids)),
    )

    # 5. Delete the users.
    await session.execute(
        delete(User).where(User.telegram_id.in_(ids)),
    )

    return len(ids), deactivated


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

async def create_invitation(
    session: AsyncSession,
    code: str,
    created_by: int,
    target_role: str,
) -> Invitation:
    invitation = Invitation(
        code=code,
        created_by=created_by,
        target_role=target_role,
    )
    session.add(invitation)
    await session.flush()
    return invitation


async def get_invitation(session: AsyncSession, code: str) -> Invitation | None:
    return await session.get(Invitation, code)


async def mark_invitation_used(
    session: AsyncSession, code: str, used_by: int,
) -> None:
    await session.execute(
        update(Invitation)
        .where(Invitation.code == code)
        .values(used=True, used_by=used_by),
    )


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

MAX_ACTIVE_SUBSCRIPTIONS = 4


async def create_subscription(
    session: AsyncSession,
    user_telegram_id: int,
    label: str,
    *,
    role: str = "l1",
) -> Subscription:
    if role != "admin":
        count = await count_active_subscriptions(session, user_telegram_id)
        if count >= MAX_ACTIVE_SUBSCRIPTIONS:
            raise SubscriptionLimitError(
                f"User {user_telegram_id} already has {count} active subscriptions",
            )

    subscription = Subscription(
        user_telegram_id=user_telegram_id,
        label=label,
        token=uuid.uuid4().hex,
        hysteria_password=secrets.token_urlsafe(32),
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def get_subscription(
    session: AsyncSession,
    subscription_id: uuid.UUID,
) -> Subscription | None:
    return await session.get(Subscription, subscription_id)


async def get_subscription_by_token(
    session: AsyncSession,
    token: str,
) -> Subscription | None:
    result = await session.execute(
        select(Subscription).where(
            Subscription.token == token,
            Subscription.active.is_(True),
        ),
    )
    return result.scalar_one_or_none()


async def list_user_subscriptions(
    session: AsyncSession,
    user_telegram_id: int,
    active_only: bool = True,
) -> list[Subscription]:
    stmt = select(Subscription).where(
        Subscription.user_telegram_id == user_telegram_id,
    )
    if active_only:
        stmt = stmt.where(Subscription.active.is_(True))
    stmt = stmt.order_by(Subscription.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_all_active_subscriptions(
    session: AsyncSession,
) -> list[Subscription]:
    result = await session.execute(
        select(Subscription)
        .where(Subscription.active.is_(True))
        .order_by(Subscription.created_at),
    )
    return list(result.scalars().all())


async def deactivate_subscription(
    session: AsyncSession,
    subscription_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        update(Subscription)
        .where(
            Subscription.id == subscription_id,
            Subscription.active.is_(True),
        )
        .values(active=False),
    )
    return result.rowcount > 0


async def deactivate_user_subscriptions(
    session: AsyncSession,
    user_telegram_id: int,
) -> list[Subscription]:
    active_subs = await list_user_subscriptions(
        session, user_telegram_id, active_only=True,
    )
    if active_subs:
        sub_ids = [s.id for s in active_subs]
        await session.execute(
            update(Subscription)
            .where(Subscription.id.in_(sub_ids))
            .values(active=False),
        )
        for s in active_subs:
            s.active = False
    return active_subs


async def count_active_subscriptions(
    session: AsyncSession,
    user_telegram_id: int,
) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Subscription)
        .where(
            Subscription.user_telegram_id == user_telegram_id,
            Subscription.active.is_(True),
        ),
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def generate_code() -> str:
    """Return a random zero-padded 6-digit numeric string."""
    return f"{random.randint(0, 999999):06d}"


# ---------------------------------------------------------------------------
# Instructions: text-only and/or up to 10 photos (Telegram media group limit)
# ---------------------------------------------------------------------------

MAX_INSTRUCTION_PHOTOS = 10
# Telegram message text limit for send_message
MAX_INSTRUCTION_BODY_CHARS = 4096


async def list_instructions(session: AsyncSession) -> list[Instruction]:
    result = await session.execute(
        select(Instruction).order_by(Instruction.sort_order, Instruction.created_at),
    )
    return list(result.scalars().all())


async def get_instruction(
    session: AsyncSession,
    instruction_id: uuid.UUID,
) -> Instruction | None:
    return await session.get(Instruction, instruction_id)


async def get_instruction_with_photos(
    session: AsyncSession,
    instruction_id: uuid.UUID,
) -> tuple[Instruction | None, list[InstructionPhoto]]:
    result = await session.execute(
        select(Instruction)
        .where(Instruction.id == instruction_id)
        .options(selectinload(Instruction.photos)),
    )
    inst = result.scalar_one_or_none()
    if not inst:
        return None, []
    photos = sorted(inst.photos, key=lambda p: p.position)
    return inst, photos


async def _next_sort_order(session: AsyncSession) -> int:
    result = await session.execute(select(func.coalesce(func.max(Instruction.sort_order), 0)))
    max_so = result.scalar_one()
    return int(max_so) + 1


async def create_instruction(
    session: AsyncSession,
    title: str,
    caption: str | None,
    file_ids: list[str],
) -> Instruction:
    if not title or len(title) > 200:
        raise ValueError("title must be 1–200 characters")

    cap = caption.strip() if caption else None
    if not file_ids:
        if not cap:
            raise ValueError("Нужен текст инструкции или хотя бы одно фото.")
        if len(cap) > MAX_INSTRUCTION_BODY_CHARS:
            raise ValueError(f"Текст не длиннее {MAX_INSTRUCTION_BODY_CHARS} символов.")
    else:
        if len(file_ids) > MAX_INSTRUCTION_PHOTOS:
            raise ValueError(f"Не больше {MAX_INSTRUCTION_PHOTOS} фото в одной инструкции.")
        if any(not fid.strip() for fid in file_ids):
            raise ValueError("empty file_id")
        if cap and len(cap) > MAX_INSTRUCTION_BODY_CHARS:
            raise ValueError(f"Подпись не длиннее {MAX_INSTRUCTION_BODY_CHARS} символов.")

    sort_order = await _next_sort_order(session)
    inst = Instruction(
        title=title.strip(),
        caption=cap,
        sort_order=sort_order,
    )
    session.add(inst)
    await session.flush()
    for pos, fid in enumerate(file_ids):
        session.add(
            InstructionPhoto(
                instruction_id=inst.id,
                position=pos,
                file_id=fid,
            ),
        )
    await session.flush()
    return inst


async def update_instruction_title(
    session: AsyncSession,
    instruction_id: uuid.UUID,
    title: str,
) -> bool:
    if not title or len(title) > 200:
        raise ValueError("title must be 1–200 characters")
    result = await session.execute(
        update(Instruction)
        .where(Instruction.id == instruction_id)
        .values(title=title.strip()),
    )
    return result.rowcount > 0


async def replace_instruction_photos(
    session: AsyncSession,
    instruction_id: uuid.UUID,
    file_ids: list[str],
    caption: str | None,
) -> bool:
    cap = caption.strip() if caption else None
    if not file_ids:
        if not cap:
            raise ValueError("Нужен текст инструкции или хотя бы одно фото.")
        if len(cap) > MAX_INSTRUCTION_BODY_CHARS:
            raise ValueError(f"Текст не длиннее {MAX_INSTRUCTION_BODY_CHARS} символов.")
    else:
        if len(file_ids) > MAX_INSTRUCTION_PHOTOS:
            raise ValueError(f"Не больше {MAX_INSTRUCTION_PHOTOS} фото в одной инструкции.")
        if any(not fid.strip() for fid in file_ids):
            raise ValueError("empty file_id")
        if cap and len(cap) > MAX_INSTRUCTION_BODY_CHARS:
            raise ValueError(f"Подпись не длиннее {MAX_INSTRUCTION_BODY_CHARS} символов.")

    inst = await session.get(Instruction, instruction_id)
    if not inst:
        return False

    await session.execute(
        delete(InstructionPhoto).where(InstructionPhoto.instruction_id == instruction_id),
    )
    inst.caption = cap
    for pos, fid in enumerate(file_ids):
        session.add(
            InstructionPhoto(
                instruction_id=instruction_id,
                position=pos,
                file_id=fid,
            ),
        )
    await session.flush()
    return True


async def delete_instruction(session: AsyncSession, instruction_id: uuid.UUID) -> bool:
    result = await session.execute(
        delete(Instruction).where(Instruction.id == instruction_id),
    )
    return result.rowcount > 0
