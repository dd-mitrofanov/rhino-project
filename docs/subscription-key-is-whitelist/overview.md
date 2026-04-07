# Task: Subscription key `is_whitelist` (per-key access vs server list)

## Context and motivation

RU server entries in `RU_SERVERS_JSON` carry a **server-level** `is_whitelist` flag (see `_is_whitelist` in `bot/app/subscription_format.py`): only explicit `true` marks a whitelist-oriented relay; missing / null / `false` are non-whitelist.

PostgreSQL **`subscriptions.is_whitelist`** selects **full** vs **restricted** plaintext: **`true`** (default for new and migrated keys) keeps the full four-segment list; **`false`** yields **only non-WL** relays (WL segments empty; same global segment order). Operator-facing detail: [docs/06-bot-and-subs.md](../06-bot-and-subs.md).

This supports tiered access without changing the global `ru_servers` inventory.

## Global goal

- PostgreSQL `subscriptions` has a boolean **`is_whitelist`**: `true` = full access (all servers in the response), `false` = restricted (only servers where server dict `is_whitelist` is not explicit `true`).
- **Existing rows** are migrated to **`true`** so behavior stays unchanged for current users.
- **New subscriptions** created via `create_subscription` default to **`true`** unless a later spec adds an override parameter.
- `GET /{token}` (and any code path that calls `build_subscription_link_lines`) applies the filtering rule above.
- Automated tests cover restricted vs full behavior; operator docs describe both flags (server vs subscription).

## Architectural brief

| Layer | Responsibility |
|--------|----------------|
| **DB** | Column `subscriptions.is_whitelist NOT NULL`, default / backfill `true`. |
| **Repository** | `create_subscription` sets default consistent with model (full access for new keys). |
| **Formatting** | `build_subscription_link_lines` receives the subscription’s `is_whitelist`; if `false`, pre-filter `servers` to those where `_is_whitelist(server)` is `false`, then run the **same** four-group pipeline (WL segments become empty when restricted). |
| **HTTP** | `subscription_http.get_subscription` passes `subscription.is_whitelist` into the builder. |

**Two independent concepts:**

1. **Server `is_whitelist`** (in JSON): which segment (non-WL vs WL) a relay belongs to in the **full** list.
2. **Subscription `is_whitelist`**: whether the user may see **all** segments or **only** non-whitelist servers.

**Out of scope (unless product follow-up):**

- Telegram/admin UX to toggle `subscriptions.is_whitelist` (only storage + subscription plaintext behavior are required here).
- Changes to Xray gRPC or Hysteria sync (still provision users per current rules; this task is subscription **link content** only).
- Ansible / `RU_SERVERS_JSON` generation shape (already supports per-server `is_whitelist`).

## Sub-tasks (table of contents)

| # | Spec | Summary | Depends on |
|---|------|---------|------------|
| 01 | [01_db_migration_and_model.md](01_db_migration_and_model.md) | Alembic revision, SQLAlchemy `Subscription.is_whitelist`, `create_subscription` default | — |
| 02 | [02_subscription_format_http_tests.md](02_subscription_format_http_tests.md) | Filter in `build_subscription_link_lines`, wire `subscription_http`, tests | 01 |
| 03 | [03_docs_operator_update.md](03_docs_operator_update.md) | Update `docs/06-bot-and-subs.md` (and grep for other mentions) | 02 |

## Definition of done (whole project)

- Migration applies cleanly on empty DB and on DB with existing `subscriptions` rows; downgrade is defined and consistent with project conventions.
- Model and repository align: new rows get `is_whitelist=True` without callers having to pass it.
- Restricted keys never emit links for servers that are server-whitelist (`is_whitelist is True` in dict); full keys behave exactly as today (including shuffle and naming).
- Tests fail if filtering or wiring regresses; CI for `bot/` stays green.
- Operator documentation explains subscription-level vs server-level `is_whitelist` and points to code entry points.
