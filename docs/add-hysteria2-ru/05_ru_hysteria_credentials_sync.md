# [05] RU relay: sync per-user Hysteria credentials from bot (not gRPC)

## Description

Hysteria2 has **no** Xray-style **gRPC `HandlerService`** for adding users. The bot must push **per-subscription** secrets to each RU so the Hysteria server config/auth file stays consistent with PostgreSQL.

**Recommended pattern (aligns with repo conventions):**

1. **Small HTTP API** on each RU relay, listening on **a dedicated TCP port** (e.g. `hysteria_sync_port`), bound to **`0.0.0.0`** but **firewall-restricted** to the **Telegram bot host IP** (`vault_nl_ams_1_ip`), same security model as `roles/xray/tasks/firewall.yml` for `xray_grpc_port`.
2. **POST** body: JSON list of `{ "user": "<stable-id>", "password": "<secret>" }` for **all active subscriptions** (full sync) or incremental protocol — **full sync** is simpler and matches `sync_all_subscriptions` in `bot/app/xray/sync.py`.
3. Handler writes **`auth` file** atomically (write temp + rename) in the path consumed by Hysteria container, then **reloads** Hysteria (`docker kill -s HUP` or restart).

**Alternative (weaker):** periodic Ansible-only deploy — **rejected** for dynamic users.

**Alternative:** SSH from bot to RU — avoid; adds SSH key sprawl.

## Goal

Every time subscriptions change or on a **timer**, all RU relays receive the same credential set as the database, without manual SSH.

## Technical details

### RU-side component

Options (pick one in implementation):

- **nginx + lua** — heavier.
- **Python FastAPI/Flask** onefile behind systemd — simple.
- **Go micro-binary** — minimal deps.

Requirements:

- **TLS optional** on loopback; if plain HTTP, **must** rely on **firewall source IP + Bearer token** (defense in depth).
- Validate `Authorization: Bearer <vault_hysteria_sync_token>` (or dedicated vault key).
- Idempotent writes.

### Bot-side

- New module parallel to `bot/app/xray/sync.py`, e.g. `bot/app/hysteria/sync.py`:
  - Load all active subscriptions (reuse `repo.list_all_active_subscriptions`).
  - For each endpoint in **`HYSTERIA_SYNC_ENDPOINTS`** env (comma-separated `host:port` per RU), POST credentials.
- Call from:
  - Same periodic loop as Xray sync (`_periodic_sync` in `bot/app/__main__.py`), **or** shared scheduler.
  - After subscription create/delete in handlers (same as `add_vless_client` fan-out today).

### Environment

- `configs/production/templates/telegram-bot.env.j2` — add:
  - `HYSTERIA_SYNC_ENDPOINTS=ru1:port,ru2:port`
  - `HYSTERIA_SYNC_TOKEN={{ vault_... }}`

### Webhook (optional)

- Mirror `roles/xray/files/xray-sync-webhook.sh`: on Hysteria container **start**, POST to bot to trigger **full sync** (reuse existing webhook URL with new path **or** extend payload — document choice). Ensures RU catches up after reboot before clients fail.

### Files to touch (illustrative)

- New: RU systemd unit + script or small app under `roles/hysteria/files/` or `roles/ru-hysteria-sync/`
- `roles/xray/tasks/firewall.yml` **or** new firewall task — allow TCP `hysteria_sync_port` from bot IP
- `bot/app/config.py` — new settings
- `playbooks/deploy-telegram-bot.yml` — pass endpoints list (from `ru_servers` + port var)

## Dependencies

- **01** — DB field exists
- **04** — Hysteria reads auth file from known path

## Usage example (user story)

- As the bot, after I create a subscription, I push updated user list to every RU; Hysteria reloads; the new `hysteria2://` line works within one sync interval.

## Acceptance criteria

- It must be true that **unauthenticated** requests from arbitrary IPs cannot update credentials (UFW + Bearer).
- It must be true that sync **fan-out** covers **all** RU relays in inventory.
- Failed RU update is **logged** and retried on the next interval (same resilience as Xray gRPC sync warnings).
- It must be documented whether sync is **full replace** or incremental (prefer full replace for simplicity).
