"""Ensure app settings can load before tests import application modules."""
from __future__ import annotations

import os

os.environ.setdefault("BOT_TOKEN", "0000000000:TEST_TOKEN_FOR_PYTEST")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "1")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
