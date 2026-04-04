# Task: Add Hysteria2 as client→RU transport (RU relay)

## Context and motivation

Some clients benefit from **QUIC/UDP-based** entry (Hysteria2) while the project’s **policy routing** (geosite/geoip, balancer, observatory, VK/Mail dedicated exit) must remain on **Xray** at the RU relay. The established pattern is a **standalone Hysteria2 server** on each RU that forwards decrypted user traffic to a **local SOCKS5** served by **Xray**, so all sniffing and routing stay in the existing `ru-relay.json.j2` pipeline.

The current **VLESS + Reality + XHTTP** user inbound (`vless-in` in `configs/production/templates/ru-relay.json.j2`) must stay **bit-for-bit in intent**: do not edit that inbound block; only **add** new configuration (e.g. loopback SOCKS inbound + separate Hysteria stack).

## Global goal

- Users receive subscription text containing both **`vless://`** lines (unchanged semantics) and **`hysteria2://`** lines (one per RU relay).
- Each subscription has a **per-user Hysteria2 secret** stored in the bot DB and **propagated to every RU relay** so servers can authenticate clients.
- On each RU: **UDP** listens on a **dedicated port** (not TCP 443); **TLS** for Hysteria uses a **self-signed / internal** certificate generated and held **only on that RU** (not the public subscription domain cert).
- Hysteria server **chains** to **127.0.0.1** SOCKS inbound on Xray; **no change** to the existing XHTTP `vless-in` block.

## Architectural brief

| Layer | Choice |
|-------|--------|
| Hysteria2 server | Official container image **`ghcr.io/apernet/hysteria`** (or Docker Hub `tobyxdd/hysteria` — pin digest/tag in Ansible vars). Server mode with **TLS** (self-signed cert on RU), **UDP** listen port from vars. |
| Chain to Xray | Hysteria **TCP redirect / SOCKS5 outbound** (per upstream Hysteria v2 config) to **`127.0.0.1:<xray_socks_port>`** where Xray exposes a **new** SOCKS inbound (sniffing enabled for routing). |
| Xray | **New** inbound only (e.g. tag `socks-hysteria-in`), `listen`: `127.0.0.1`. **Do not** modify the `vless-in` JSON object. |
| Per-user auth | **Not** via Xray gRPC — Hysteria has no `HandlerService`. Store **per-subscription secret** in PostgreSQL; sync to RU via a **dedicated control-plane path** (recommended: **HTTPS or HTTP + Bearer** from bot host to RU, firewall **source = bot host**, same idea as `roles/xray/tasks/firewall.yml` for gRPC). |
| Subscription URI | **`hysteria2://`** share links per [Hysteria URI scheme](https://v2.hysteria.network/docs/advanced/Full-Client-Config/) — include `insecure=1` (or pin SPKI later) for self-signed RU cert; **server address** = RU public IP/DNS from `ru_servers`; **port** = Hysteria UDP port variable. |

## Sub-tasks (order and dependencies)

| # | Document | Summary | Depends on |
|---|----------|---------|------------|
| 01 | [01_database_hysteria_credentials.md](01_database_hysteria_credentials.md) | Alembic migration + `Subscription` field for Hysteria secret; generation on create; rotation rules | — |
| 02 | [02_ansible_vars_tls_firewall_subscription_json.md](02_ansible_vars_tls_firewall_subscription_json.md) | New vars (`hysteria_*`, `xray_socks_port`), vault keys if needed, self-signed TLS tasks, **UFW UDP** for Hysteria port, extend `ru_servers_json` in `deploy-telegram-bot.yml` | 01 (for documenting backfill of existing rows) |
| 03 | [03_xray_loopback_socks_inbound.md](03_xray_loopback_socks_inbound.md) | Add SOCKS inbound on `127.0.0.1` only + sniffing; **do not** touch `vless-in` | 02 (port variable) |
| 04 | [04_hysteria_docker_and_upstream.md](04_hysteria_docker_and_upstream.md) | New Ansible role or `tasks` include: Hysteria config template, Docker run/compose, upstream to local SOCKS, volume for cert + auth file | 02, 03 |
| 05 | [05_ru_hysteria_credentials_sync.md](05_ru_hysteria_credentials_sync.md) | Mechanism to push per-user credentials from bot to each RU (file + reload/restart); firewall for sync listener; optional webhook after Hysteria restart | 01, 04 |
| 06 | [06_bot_subscription_and_sync_integration.md](06_bot_subscription_and_sync_integration.md) | `build_hysteria2_link`, extend `subscription_http.py`, wire sync into existing periodic sync / subscription lifecycle | 01, 02, 05 |
| 07 | [07_testing_and_rollout.md](07_testing_and_rollout.md) | Manual tests, deploy order, rollback, observability | 01–06 |

**Parallelization:** After 02 is drafted, **03** and **04** can proceed in parallel (Xray template vs Hysteria container). **05** blocks on **04** (target files/services exist). **06** blocks on **01**, **02**, **05**.

## Definition of done (project-wide)

- Existing **VLESS** subscription lines and Xray **gRPC** user sync behave as before; **`vless-in`** template block is unchanged.
- New **Hysteria2** lines appear in `GET /{token}` output; each active user has a **consistent** secret across all RU relays.
- RU exposes **UDP** Hysteria port; **TLS** for Hysteria is **self-signed on RU**; TCP **443** remains Xray-only.
- Traffic entering via Hysteria is subject to **the same** RU routing (balancer, direct RU, etc.) as VLESS users.
- Ansible playbooks are idempotent; secrets not committed; firewall least-privilege (sync from bot IP only).
- **Documentation:** Update `docs/06-bot-and-subs.md` and `docs/03-ru-relay-configurations.md` when implementing (outside this planning folder unless the team prefers linking here).
