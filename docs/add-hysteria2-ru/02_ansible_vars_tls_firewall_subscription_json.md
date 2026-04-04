# [02] Ansible: variables, self-signed TLS on RU, firewall UDP, subscription JSON

## Description

Introduce **Ansible variables** for Hysteria2 (image, UDP listen port, TLS paths, optional tuning) and for the **Xray SOCKS** port used only for Hysteria→Xray chaining. Generate **self-signed** TLS material **on each RU relay** (private key + fullchain) stored under e.g. `/etc/hysteria/tls/` or a Docker named volume. Open **UFW** for **UDP** on the Hysteria port on RU relays. Extend **`RU_SERVERS_JSON`** built in `playbooks/deploy-telegram-bot.yml` so the bot can render `hysteria2://` links without hardcoding.

## Goal

Centralize configuration in `configs/production/vars/` + Vault; ensure **public UDP** reaches Hysteria while **management** traffic stays restricted; feed the bot structured per-relay metadata including Hysteria port and TLS **fingerprint or SNI hints** for clients.

## Technical details

### Variables (non-exhaustive — implementer fills exact names)

- `configs/production/vars/xray.yml` (or new `hysteria.yml` included by playbooks):
  - `hysteria_image: "ghcr.io/apernet/hysteria"` (verify upstream tag naming)
  - `hysteria_docker_tag: "<pinned>"`
  - `hysteria_listen_port: <int>` — **UDP**, distinct from `xray_inbound_port` (443 TCP)
  - `xray_socks_listen_port` — TCP on `127.0.0.1` for new SOCKS inbound (e.g. `10808`)
  - Paths: `hysteria_tls_dir`, `hysteria_config_path`

### Vault

- Optional: **no** per-user secrets in Vault for Hysteria if all per-user state lives in **PostgreSQL** and is pushed by the bot.
- If a **shared HMAC/Bearer** for the RU “credential sync” HTTP API is used, store e.g. `vault_hysteria_sync_token` (or reuse a pattern similar to `vault_subscription_api_token` naming in `configs/production/secrets/vault.yml`).

### Self-signed TLS (RU only)

- Ansible task: `openssl` or `community.crypto.x509_certificate` + private key; **CN/SAN** can be a static string like `hysteria.internal` (clients will use `insecure=1` or pin SPKI later).
- **Do not** use `subscription_api_domain` public cert for Hysteria — user requirement.

### Firewall

- `roles/hardening/tasks/firewall.yml` today allows **TCP** `xray_inbound_port` only. Add **UDP** rule for `hysteria_listen_port` on **`ru_relays`** (use `when: server_role == 'ru-relay'` or equivalent inventory group).
- Keep **narrow** allow for **sync** endpoint (task 05): TCP from `vault_nl_ams_1_ip` (bot host), analogous to `roles/xray/tasks/firewall.yml` gRPC allow.

### `RU_SERVERS_JSON` extension

- File: `playbooks/deploy-telegram-bot.yml` — `set_fact` `ru_servers_json` loop over `ru_servers`.
- Add fields per server, for example:
  - `hysteria_port` — same as `hysteria_listen_port` (or per-relay override in `servers.yml` if ever needed)
  - `hysteria_sni` — string for URI `sni` param (match cert CN/SAN or document mismatch + `insecure=1`)
  - `hysteria_tls_fingerprint` — optional SPKI SHA256 for clients that support pinning instead of `insecure=1` (derive via `openssl x509` in a task and pass to bot — **optional** enhancement; minimum is `insecure=1`)

**Note:** TLS fingerprint is **per RU**; if generated per server in Ansible, it must be captured into `ru_servers_json` at deploy time (similar to Reality `reality_public_key` from Vault lookup).

### Files to touch

- `configs/production/vars/xray.yml` and/or new vars file
- `configs/production/vars/servers.yml` — optional per-relay `hysteria_port` override
- `playbooks/deploy-telegram-bot.yml` — extend JSON blob
- `configs/production/templates/telegram-bot.env.j2` — only if new env vars needed beyond JSON
- `roles/hardening/tasks/firewall.yml` — UDP allow
- New tasks file under `roles/xray/` or new `roles/hysteria/` for TLS generation (clear ownership in implementation)

## Dependencies

- **01** — migration should be applied before backfill expectations; vars can be drafted in parallel.

## Usage example (user story)

- As a deployer, running `ansible-playbook playbooks/deploy-telegram-bot.yml` refreshes `RU_SERVERS_JSON` with Hysteria ports and metadata for every RU entry.
- As a deployer, `deploy-ru-relay` creates TLS files and opens UDP without exposing the Xray SOCKS port publicly.

## Acceptance criteria

- It must be true that **`hysteria_listen_port` is not** `xray_inbound_port` and uses **UDP** in firewall rules.
- It must be true that **SOCKS** port variables refer to **loopback-only** Xray inbound (enforced in task 03).
- `RU_SERVERS_JSON` must remain **valid JSON** and backward-compatible: existing keys (`tag`, `address`, `port`, `reality_public_key`, …) unchanged.
- Self-signed cert and key exist on each RU after playbook run; permissions restrict read to root/hysteria user/container.
