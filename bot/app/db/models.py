import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'l1', 'l2')", name="ck_users_role"),
    )

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(10))
    invited_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint(
            "target_role IN ('l1', 'l2')", name="ck_invitations_target_role",
        ),
    )

    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"),
    )
    target_role: Mapped[str] = mapped_column(String(10))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_user_active", "user_telegram_id", "active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False,
    )
    vless_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4,
    )
    hysteria_password: Mapped[str] = mapped_column(String(128), nullable=False)
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False,
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )


# At most 10 photos per instruction (Telegram send_media_group limit).
class Instruction(Base):
    __tablename__ = "instructions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True,
    )

    photos: Mapped[list["InstructionPhoto"]] = relationship(
        back_populates="instruction",
        order_by="InstructionPhoto.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class InstructionPhoto(Base):
    __tablename__ = "instruction_photos"
    __table_args__ = (
        Index(
            "ix_instruction_photos_instruction_position",
            "instruction_id",
            "position",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    instruction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("instructions.id", ondelete="CASCADE"), nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-based order in album
    file_id: Mapped[str] = mapped_column(String(255))

    instruction: Mapped["Instruction"] = relationship(back_populates="photos")
