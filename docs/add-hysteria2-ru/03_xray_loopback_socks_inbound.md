# [03] Xray RU template: new loopback SOCKS inbound (do not touch `vless-in`)

## Description

Append a **new** inbound to `configs/production/templates/ru-relay.json.j2` that listens on **`127.0.0.1`** only, **TCP**, protocol **socks** (or **socks** with appropriate auth — prefer **no auth** on loopback if threat model accepts local-only binding). Enable **sniffing** consistent with `vless-in` (`http`, `tls`, `quic`) and `routeOnly` aligned with `xray_sniffing_route_only` so routing matches existing behavior.

**Explicit constraint:** Do **not** modify the existing `vless-in` inbound object (lines containing `"tag": "vless-in"` and its `streamSettings`). Add a separate JSON object in the `inbounds` array.

## Goal

Give Hysteria2 a local upstream that feeds **the same** `routing` / `balancers` / `observatory` section already defined in the template without duplicating rules.

## Technical details

### Template variables

- Use `{{ xray_socks_listen_port }}` (or name from task 02) for `port`.
- `"listen": "127.0.0.1"` — **not** `0.0.0.0`.

### Inbound tag

- Example: `socks-hysteria-in` — document tag for bot/Xray sync (no gRPC user add for SOCKS if not needed).

### Routing

- **No new routing rules required** if default behavior sends SOCKS-originated traffic through the same rule set; confirm in Xray docs that inbound from SOCKS uses `routing` with `domainStrategy` as configured.
- If BitTorrent blocking uses `protocol` sniffing, ensure SOCKS inbound has sniffing enabled.

### Files to touch

- `configs/production/templates/ru-relay.json.j2` — add inbound only
- `inventories/production/group_vars/ru_relays.yml` or `configs/production/vars/xray.yml` — default `xray_socks_listen_port`

### Post-deploy verification

- `playbooks/deploy-ru-relay.yml` may add a `wait_for` on `127.0.0.1:xray_socks_listen_port` **from the host** (optional).

## Dependencies

- **02** — port variable defined.

## Usage example (user story)

- As Hysteria, I connect outbound to `127.0.0.1:10808` and Xray accepts the SOCKS session; traffic to foreign domains uses the balancer like VLESS users.

## Acceptance criteria

- It must be true that the **`vless-in`** block in `ru-relay.json.j2` is **unchanged** from the pre-task version (aside from any unavoidable global variable renames — ideally none).
- Rendered config shows new inbound **only** on loopback.
- It works if `ss`/`nc` from the RU host can open TCP to `127.0.0.1:<socks_port>` while the same port is **not** reachable from outside (verify with external scan or UFW).
