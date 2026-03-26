# Telegram bot and subscriptions

The **Telegram bot** and **PostgreSQL** run on the **`telegram_bot`** host (default **`nl-ams-1`**) in Docker. User access is stored in the database; subscription responses are built dynamically. **RU relays** serve the public subscription URL via **Caddy** + a small proxy that forwards to the bot.

---

## 1. Components

| Piece | Where | Role |
|-------|-------|------|
| **Bot + DB** | `nl-ams-1` (Docker) | Invites, admin flows, subscription HTTP handler |
| **Built-in subscription HTTP** | Bot container | Serves `GET /{token}` with **Bearer** auth; builds `vless://` lines from DB + `RU_SERVERS_JSON` |
| **External stack** | Each **RU relay** | Caddy (TLS) + proxy → forwards to bot; clients use `subscription_api_domain` |

The bot’s environment includes **`RU_SERVERS_JSON`**, generated at deploy time from `ru_servers` in `configs/production/vars/servers.yml` and Reality public keys from Vault (`playbooks/deploy-telegram-bot.yml`).

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

## 4. Syncing users to Xray

When subscriptions are created, revoked, or updated, the bot uses **gRPC** against each RU relay (`XRAY_GRPC_ENDPOINTS` — `address:xray_grpc_port` for each `ru_servers` entry) to add/remove **VLESS** users on inbound `vless-in`. Periodic sync can reconcile state after restarts (see `bot/app/config.py` for intervals).

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
- Rotate `vault_subscription_api_token` if leaked; redeploy bot and subscription external stacks.

---

## 7. Bot features (operator reference)

Slash commands for Telegram must be Latin; the bot may expose Russian descriptions in the menu. Admin flows for instruction albums etc. live in the `bot/` application — see repository code for current commands.

---

## See also

- First-time full stack: [02-first-deploy.md](02-first-deploy.md)
- Add RU relay (subscription list impact): [07-add-ru-relay.md](07-add-ru-relay.md)
