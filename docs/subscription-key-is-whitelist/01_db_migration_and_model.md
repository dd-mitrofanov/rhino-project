# [01] DB migration, model, and `create_subscription` default

## Description

Add a **non-nullable boolean** column `is_whitelist` on table `subscriptions`.

- **Semantics:** `true` = full access (subscription response includes all servers, subject to existing four-group logic). `false` = restricted (subscription response must only include servers treated as non-whitelist by `_is_whitelist` — implemented in subtask 02).
- **Backfill:** All **existing** rows must end up with `is_whitelist = true` (same as current “full list” behavior).

Update the SQLAlchemy model in `bot/app/db/models.py` (`Subscription`) and ensure `create_subscription` in `bot/app/db/repositories.py` creates rows with **`is_whitelist=True`** by default (model default and/or explicit constructor argument), matching prior full-access behavior for **new** keys.

Optional (nice-to-have in same task): add a keyword-only parameter `is_whitelist: bool = True` to `create_subscription` for future admin flows — **not required** if the task owner prefers minimal API surface until a toggle exists.

## Goal

Persist the per-key flag and guarantee backward-compatible data and defaults before any formatting or HTTP changes.

## Technical details

### Database

- **Table:** `subscriptions`
- **Column:** `is_whitelist`, `BOOLEAN`, `NOT NULL`
- **Default for existing + new rows at DB level:** use `server_default=sa.text('true')` on `add_column` (same style as `users.active` in `bot/alembic/versions/002_add_user_active.py`) so PostgreSQL backfills existing rows when the column is added.
- **Alembic:** new revision `down_revision = "003"` (after `003_add_hysteria_password.py`), following the project’s revision ID string pattern.

### SQLAlchemy

- `Mapped[bool]` with `mapped_column(Boolean, default=True, nullable=False)` (or equivalent), aligned with migration.
- If the team drops `server_default` after migration (some codebases do), document in implementation; otherwise keeping `server_default` matches `002`.

### Repository

- In `create_subscription`, the new `Subscription(...)` must not leave `is_whitelist` unset in a way that could violate `NOT NULL` without a DB default.

## Dependencies

None (first task).

## Usage examples (user story)

- **As an operator**, after deploying the migration, I query PostgreSQL and see `is_whitelist = true` for every existing subscription row.
- **As the bot**, when I call `create_subscription` without extra flags, the inserted row has `is_whitelist` true.

## Acceptance criteria

- It must be possible to run `alembic upgrade head` on a copy of production-like data and see all `subscriptions.is_whitelist = true`.
- It must be impossible to insert a subscription row without `is_whitelist` being set (DB `NOT NULL` + application defaults).
- New subscriptions created through `create_subscription` have `is_whitelist=True` unless a deliberate optional parameter is added and documented in code.
- Downgrade removes the column without leaving the schema in an inconsistent state for the previous revision chain.
- Subtask **01** alone does not change subscription plaintext; after **02** merges, `GET /{token}` respects **`subscriptions.is_whitelist`** as in **`docs/06-bot-and-subs.md`** (restricted keys do not see server-whitelist relays in the body).
