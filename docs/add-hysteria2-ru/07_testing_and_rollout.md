# [07] Testing, rollout order, rollback

## Description

Define how to validate Hysteria2 end-to-end and a safe deployment sequence across **DB → RU (Xray + Hysteria + sync API) → bot**.

## Goal

Minimize user downtime; allow quick rollback of Hysteria layer without touching working VLESS.

## Technical details

### Suggested rollout order

1. **Database migration** (task **01**) — deploy bot image that includes Alembic revision; run once; verify column populated.
2. **Ansible vars + TLS + firewall** (task **02**) — deploy to one **staging** RU if available, else single RU canary.
3. **Xray SOCKS inbound** (task **03**) — deploy `ru-relay`; verify `127.0.0.1` SOCKS responds locally (`curl` via a small socks test or `xray` api if available).
4. **Hysteria container** (task **04**) — verify UDP port open, TLS handshake with self-signed from client perspective.
5. **RU sync API** (task **05**) — `curl` from bot host with Bearer token; confirm file on disk updates and Hysteria reloads.
6. **Bot** (task **06**) — deploy bot; verify subscription output; trigger full sync.

### Manual test checklist

- **VLESS** client still connects to RU **443** XHTTP/Reality (smoke test).
- **Hysteria2** official client connects using copied `hysteria2://` line; traffic reaches internet; **RU-only** domains go **direct** (spot-check a RU geo rule).
- **Balancer**: foreign traffic rotates or follows `balancer_strategy` (optional deep check).
- **Revoke subscription**: user removed from Hysteria auth after sync interval (or immediate if handler triggers sync).
- **Firewall**: external host cannot POST to sync port; bot host can.

### Monitoring

- Existing Prometheus/Xray exporters unchanged; optional: add Hysteria **metrics** port if upstream supports it (out of scope unless needed).

### Rollback

- Remove Hysteria lines from subscription (feature flag env `ENABLE_HYSTERIA_SUBSCRIPTION=false`) — optional implementer choice.
- Stop hysteria container; remove UDP rule; leave DB column (harmless).
- Revert template **03** only if no dependency — prefer feature flag over template revert.

### Documentation updates (implementation phase)

- `docs/06-bot-and-subs.md` — document new env vars and link format.
- `docs/03-ru-relay-configurations.md` — Hysteria UDP port, SOCKS chain, self-signed TLS note.

## Dependencies

- **01–06** complete or staged per environment.

## Usage example (user story)

- As a release engineer, I follow the ordered checklist and can prove VLESS still works before announcing Hysteria2 to users.

## Acceptance criteria

- It must be possible to **prove** routing parity (at least one RU-direct and one foreign case) for Hysteria-entered traffic.
- Rollback path must **not** require editing Vault Reality keys or foreign UUIDs.
- A written **test record** (even a short checklist in the PR) exists for the first production deploy.
