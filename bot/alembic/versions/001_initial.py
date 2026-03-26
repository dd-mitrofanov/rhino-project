"""Initial schema.

Revision ID: 001
Revises:
Create Date: 2025-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("invited_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint("role IN ('admin', 'l1', 'l2')", name="ck_users_role"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("telegram_id"),
    )
    op.create_table(
        "invitations",
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("target_role", sa.String(length=10), nullable=False),
        sa.Column("used", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("used_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint("target_role IN ('l1', 'l2')", name="ck_invitations_target_role"),
        sa.ForeignKeyConstraint(["created_by"], ["users.telegram_id"]),
        sa.ForeignKeyConstraint(["used_by"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("vless_uuid", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_telegram_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_user_active", "subscriptions", ["user_telegram_id", "active"], unique=False)
    op.create_index("ix_subscriptions_vless_uuid", "subscriptions", ["vless_uuid"], unique=True)
    op.create_index("ix_subscriptions_token", "subscriptions", ["token"], unique=True)
    op.create_table(
        "instructions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_instructions_sort_order", "instructions", ["sort_order"], unique=True)
    op.create_table(
        "instruction_photos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instruction_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["instruction_id"], ["instructions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_instruction_photos_instruction_position",
        "instruction_photos",
        ["instruction_id", "position"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_instruction_photos_instruction_position", table_name="instruction_photos")
    op.drop_table("instruction_photos")
    op.drop_index("ix_instructions_sort_order", table_name="instructions")
    op.drop_table("instructions")
    op.drop_index("ix_subscriptions_token", table_name="subscriptions")
    op.drop_index("ix_subscriptions_vless_uuid", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_active", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_table("invitations")
    op.drop_table("users")
