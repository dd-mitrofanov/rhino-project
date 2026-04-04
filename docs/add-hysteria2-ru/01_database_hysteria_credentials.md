# [01] Database: per-subscription Hysteria2 credentials

## Description

Add a **per-subscription** secret used as the Hysteria2 authentication password (or equivalent `auth` user secret in server config). This mirrors how `vless_uuid` is unique per row but is **independent** — VLESS UUIDs remain for `vless://` and gRPC; Hysteria uses its own field.

## Goal

Enable the bot and RU relays to enforce **one credential per subscription** without sharing the VLESS UUID with the Hysteria protocol stack.

## Technical details

### Schema

- **Table:** `subscriptions`
- **New column (example name):** `hysteria_password` — `String(128)` or `Text`, **non-null** for new rows; migration must **backfill** existing active subscriptions (generate cryptographically random strings, e.g. `secrets.token_urlsafe(32)` in a data migration step or one-off script).
- **Uniqueness:** Not required globally if the protocol only needs uniqueness per server user list; if Hysteria `userpass` uses `name` = subscription email/key, password can collide across names — **per-row unique secret** is still recommended for hygiene.

### Files to touch

- `bot/app/db/models.py` — `Mapped[str]` on `Subscription`
- `bot/alembic/versions/00X_add_hysteria_password.py` — new revision after latest head
- `bot/app/handlers/subscription.py` (or wherever subscriptions are created) — set `hysteria_password` on create (if not set by DB default)
- Optional: admin/bot command to **rotate** `hysteria_password` (triggers re-sync to RU — covered in task 05/06)

### Rotation policy (recommended)

- **On demand** via admin or user “reset link” flow (optional product decision).
- After rotation, **05/06** must push new secret to all RU relays before old password stops working.

## Dependencies

- None (first data-layer task).

## Usage example (user story)

- As an operator, after deploy, **all** existing subscriptions receive a generated `hysteria_password` so no row is NULL.
- As a user, my subscription page shows **VLESS** and **Hysteria2** entries; both work for the same subscription id.

## Acceptance criteria

- It must be possible to run `alembic upgrade head` from a clean DB and from the current production schema without error.
- It must be true that **every** `subscriptions` row has a **non-empty** `hysteria_password` after migration completes.
- New subscriptions created via the bot must **persist** a new random `hysteria_password` without reusing `vless_uuid`.
- It must be documented in the migration whether **downgrade** drops the column (acceptable) or is omitted.
