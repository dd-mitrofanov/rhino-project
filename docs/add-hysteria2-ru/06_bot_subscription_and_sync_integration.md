# [06] Bot: hysteria2:// subscription lines + sync integration

## Description

Extend the HTTP subscription handler and supporting code so each RU server produces **two** link types per subscription fetch: existing **`vless://`** (`bot/app/vless.py` / `build_vless_link`) and new **`hysteria2://`** lines built from DB + `RU_SERVERS_JSON` extended fields (task **02**).

Wire **Hysteria credential sync** (task **05**) into application lifecycle: initial sync at startup, periodic interval, and on subscription mutations where VLESS gRPC is already invoked (`bot/app/handlers/subscription.py`, `bot/app/xray/subscription_email.py` patterns).

## Goal

Users importing the subscription URL see both transports; operators need **one** deploy path for bot env vars.

## Technical details

### URI format

- Scheme: **`hysteria2://`** (Hysteria v2 standard).
- Typical shape: `hysteria2://<password>@<address>:<hysteria_port>?<query>#<fragment>`
- Query params (minimum for self-signed RU TLS):
  - `insecure=1` — if using self-signed cert from task 02
  - `sni=<string>` — often the cert CN/SAN; must match server TLS config or be documented as ignored with `insecure=1`
- **Fragment** (`#`): reuse naming pattern from `subscription_http.py` (`server_name` / two-digit prefix + tag) for client display consistency.

Implement **`build_hysteria2_link(...)`** in a new module e.g. `bot/app/hysteria_uri.py` or next to `vless.py`, with **URL encoding** for password (special characters).

Reference: consult current Hysteria client URI parameters for v2 (obfs, bandwidth) — defaults only unless product requires them.

### Subscription endpoint

- File: `bot/app/subscription_http.py`
- After building `links` with VLESS, **append** Hysteria lines **per server** (mirror the loop over `settings.ru_servers`).
- Order convention: **all VLESS lines first, then all Hysteria lines**, or **interleave per server** — pick one and document (interleaving per server may help users mentally pair endpoints).

### Config

- `bot/app/config.py` — parse `HYSTERIA_SYNC_ENDPOINTS`, `HYSTERIA_SYNC_TOKEN`, optional `HYSTERIA_SYNC_INTERVAL_SECONDS` (or reuse `XRAY_SYNC_INTERVAL_SECONDS` if intentionally unified).

### Data used per line

- `subscription.hysteria_password` (task **01**)
- From each `server` dict in `ru_servers`: `address`, `hysteria_port`, `hysteria_sni`, optional `hysteria_tls_fingerprint`

### gRPC

- **No new gRPC** for Hysteria — confirm in code comments to avoid future confusion.

### Files to touch

- `bot/app/subscription_http.py`
- `bot/app/__main__.py` — schedule hysteria sync task
- `bot/app/handlers/subscription.py` — trigger sync after create/revoke if applicable
- `bot/app/xray/sync.py` — optionally orchestrate both in one `sync_all` or keep parallel functions
- `configs/production/templates/telegram-bot.env.j2`
- `playbooks/deploy-telegram-bot.yml` — ensure JSON/env includes new fields

### Tests

- Unit tests for `build_hysteria2_link` (stable encoding)
- Optional: snapshot test for subscription plaintext format

## Dependencies

- **01**, **02**, **05**

## Usage example (user story)

- As a user, `curl` with Bearer token to my subscription URL returns multiple `vless://` lines and multiple `hysteria2://` lines.
- As an operator, I only set Ansible vars once; bot receives extended `RU_SERVERS_JSON` on deploy.

## Acceptance criteria

- It must be true that **existing** `vless://` lines are **unchanged** in format (regression unless a deliberate bump is agreed).
- It must be true that **each** RU in `RU_SERVERS_JSON` yields a **hysteria2** line when servers list is non-empty.
- Subscription endpoint remains protected by **Bearer** auth (`verify_bearer_token`).
- Bot logs distinguish Xray sync failures vs Hysteria sync failures.
