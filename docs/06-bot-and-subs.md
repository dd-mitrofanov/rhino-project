# Telegram bot and subscriptions

The **Telegram bot** and **PostgreSQL** run on the **`telegram_bot`** host (default **`nl-ams-1`**) in Docker. User access is stored in the database; subscription responses are built dynamically. **RU relays** serve the public subscription URL via **Caddy** + a small proxy that forwards to the bot.

---

## 1. Components

| Piece | Where | Role |
|-------|-------|------|
| **Bot + DB** | `nl-ams-1` (Docker) | Invites, admin flows, subscription HTTP handler |
| **Built-in subscription HTTP** | Bot container | Serves `GET /{token}` with **Bearer** auth; builds `vless://` and `hysteria2://` lines from DB + `RU_SERVERS_JSON` |
| **External stack** | Each **RU relay** | Caddy (TLS) + proxy → forwards to bot; clients use `subscription_api_domain` |

The bot’s environment includes **`RU_SERVERS_JSON`**, generated at deploy time from `ru_servers` in `configs/production/vars/servers.yml`, Reality public keys from Vault, and **Hysteria** fields (`hysteria_port`, `hysteria_sni` from `configs/production/vars/hysteria.yml`) — see `playbooks/deploy-telegram-bot.yml`.

Per-subscription fields in PostgreSQL include **`subscriptions.hysteria_password`** and **`subscriptions.is_whitelist`** (see [Subscription link order and is_whitelist](#subscription-link-order-and-is_whitelist)). Env **`HYSTERIA_SYNC_ENDPOINTS`** lists `address:hysteria_sync_port` for each RU; **`HYSTERIA_SYNC_TOKEN`** must match **`vault_hysteria_sync_token`** on relays.

### Subscription link order and `is_whitelist`

The bot uses the word **`is_whitelist`** in two **independent** places. Server-level flags partition relays into segments; subscription-level flags decide whether the user sees the **full** inventory or **only non-whitelist** relays.

#### Server-level (`RU_SERVERS_JSON` / `ru_servers`)

Each `ru_servers` row may set **`is_whitelist: true`** when that RU relay is operated under ISP whitelist conditions; **`false`** or omitting the key means non-whitelist (the generated JSON still carries a boolean for each server).

This controls **which segment** (non-WL vs WL) a relay belongs to when building the list from the **full** `RU_SERVERS_JSON` inventory.

#### Per-subscription access (`subscriptions.is_whitelist` in PostgreSQL)

Column **`subscriptions.is_whitelist`** applies to the **subscription key**, not to Ansible rows:

- **`true`**: **Full access** — the response includes **all** relays from `RU_SERVERS_JSON`, ordered and labeled using server-level `is_whitelist` as in the four segments below (same behavior as before this column existed).
- **`false`**: **Restricted** — the bot first keeps only servers that are **not** server-whitelist under the same rule as in code (`_is_whitelist` in `bot/app/subscription_format.py`: only explicit **`true`** on the server dict counts as WL; missing / null / **`false`** are non-WL). It then runs the **identical** four-segment pipeline on that reduced set. **Whitelist segments are empty** (no lines for WL XHTTP / WL Hysteria2), but the **global order is unchanged**: non-WL XHTTP, then WL XHTTP, then non-WL Hysteria2, then WL Hysteria2.

**Defaults:** **New** subscriptions and **migrated** existing rows use **`subscriptions.is_whitelist = true`** until an operator updates the row (for example via SQL; a bot command may be added later). There is **no** implied guarantee that every key always sees every relay — check the DB column for restricted tiers.

#### Fixed global segment order

For the server list in play (full inventory or post-filter for restricted keys), `GET /{token}` emits links in this **fixed global order**:

1. **XHTTP** (VLESS) for servers with server-level `is_whitelist == false`
2. **XHTTP** (VLESS) for servers with server-level `is_whitelist == true`
3. **Hysteria2** for server-level `is_whitelist == false`
4. **Hysteria2** for server-level `is_whitelist == true`

**Within** each of those four segments, server order is **shuffled on every request**. The **display name** after `#` in each URI (for example `1234 XHTTP` or `5678 Hysteria2 WL`) is **deterministic** for that subscription and server, so it does not change on refresh.

Production shape of `ru_servers` lives in **`configs/production/vars/servers.yml`**. The **`inventories/test`** tree does not need to duplicate full `ru_servers`; local or CI tests that need this behavior can pass minimal `RU_SERVERS_JSON` fixtures including `is_whitelist`.

---

## 2. Ports and auth (typical Vault keys)

- **Public subscription HTTPS** on RU relays: `subscription_api_port` (example **8443**); TLS via Let’s Encrypt using `subscription_api_domain`, `subscription_api_acme_email`.
- **Bot internal HTTP**: `subscription_api_internal_port` (example **9443**) on the bot host; UFW should restrict this to **RU relay IPs**.
- **Shared secret**: `vault_subscription_api_token` — Bearer token used by RU proxies when calling the bot.

See `configs/production/secrets/vault.yml.example` for the full list.

---

## 3. DNS for fault tolerance

Point **`subscription_api_domain`** to **every RU relay** with **multiple A records** (one IP per relay). Clients resolve all addresses; if one relay is offline, retrying another IP often succeeds without an external load balancer. Use a **short TTL** (e.g. 300–600 seconds) when you change relays.

---

## 4. Syncing users to Xray and Hysteria

When subscriptions are created, revoked, or updated, the bot uses **gRPC** against each RU relay (`XRAY_GRPC_ENDPOINTS` — `address:xray_grpc_port` for each `ru_servers` entry) to add/remove **VLESS** users on inbound `vless-in`. In parallel, it **POST**s the active subscription list to each RU’s Hysteria sync HTTP port (`HYSTERIA_SYNC_ENDPOINTS` / `HYSTERIA_SYNC_TOKEN`) so **userpass** on the Hysteria server matches PostgreSQL. Periodic sync runs both paths (see `bot/app/config.py` for intervals).

**After Xray restarts on an RU relay**, in-memory VLESS clients are empty until the bot runs sync again. Each RU host runs a small **`xray-sync-webhook`** systemd service (installed by the `xray` role) that watches `docker events` for the `xray` container **start** and sends **`POST /internal/xray-sync`** to the bot’s internal HTTP port (`subscription_api_internal_hostname` / IP and `subscription_api_internal_port`), with the same **Bearer** token as the subscription API (`vault_subscription_api_token`). That triggers a full `sync_all_subscriptions` from PostgreSQL (including Hysteria) without restarting the bot. UFW on the bot host should already allow that port only from RU relay IPs (see `roles/telegram-bot/tasks/main.yml`).

**Important:** `vault_client_uuid` is shared across RU inbounds for user keys; per-relay **Reality key pairs** still differ and are embedded in `RU_SERVERS_JSON` for generated links.

---

## 5. Makefile targets (relevant)

| Target | Purpose |
|--------|---------|
| `make deploy-full` | `site.yml` + subscription external on all RU + Telegram stack on `nl-ams-1` |
| `make deploy-vpn` | Xray infrastructure only (no bot/subscription containers) |
| `make deploy-telegram` | Rebuild/restart bot + DB stack; refreshes `RU_SERVERS_JSON` / `.env` from Ansible |
| `make deploy-subscription-external` | Caddy + proxy on **all** RU relays |

After changing **`ru_servers`**, Reality keys used in links, or **`xray.yml`** fields that affect subscription strings → run **`make deploy-telegram`**. After changing proxy/Caddy/TLS for the public subscription → **`make deploy-subscription-external`**.

---

## 6. Security notes

- Treat each user’s subscription URL as a **secret** (token in path).
- Rotate `vault_subscription_api_token` if leaked; redeploy the Telegram bot, subscription external stacks on RU relays, and **`deploy-ru-relay`** (or the xray role) so `/etc/xray-sync-webhook.env` on each RU picks up the new secret.

---

## 7. Bot features (operator reference)

Slash commands for Telegram must be Latin; the bot may expose Russian descriptions in the menu. Admin flows for instruction albums etc. live in the `bot/` application — see repository code for current commands.

---

## See also

- First-time full stack: [02-first-deploy.md](02-first-deploy.md)
- Add RU relay (subscription list impact): [07-add-ru-relay.md](07-add-ru-relay.md)
