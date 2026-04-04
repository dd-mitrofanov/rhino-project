"""Add subscriptions.hysteria_password for Hysteria2 per-user auth.

Revision ID: 003
Revises: 002
Create Date: 2026-04-04

"""
from typing import Sequence, Union

import secrets

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("hysteria_password", sa.String(length=128), nullable=True),
    )
    bind = op.get_bind()
    result = bind.execute(text("SELECT id FROM subscriptions WHERE hysteria_password IS NULL"))
    rows = result.fetchall()
    for row in rows:
        sub_id = row[0]
        pw = secrets.token_urlsafe(32)
        bind.execute(
            text("UPDATE subscriptions SET hysteria_password = :pw WHERE id = :id"),
            {"pw": pw, "id": sub_id},
        )
    op.alter_column(
        "subscriptions",
        "hysteria_password",
        existing_type=sa.String(length=128),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "hysteria_password")
