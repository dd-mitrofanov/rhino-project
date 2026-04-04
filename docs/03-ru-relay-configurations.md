# Russian relay servers (RU)

This document describes how RU relays are configured in this project: inbound path, routing, balancer, observatory, and integration with the bot.

Templates and variables: `configs/production/templates/ru-relay.json.j2`, `configs/production/vars/xray.yml`, `configs/production/vars/hysteria.yml`, `configs/production/vars/servers.yml`, secrets in `configs/production/secrets/vault.yml`.

---

## 1. Role in the architecture

RU relays are the **only** place where users connect. They:

- Terminate **VLESS + Reality** with **XHTTP** in **packet-up** mode (mobile-friendly, DPI-resistant).
- Optionally terminate **Hysteria2** (QUIC/UDP) on a **separate port** (`hysteria_listen_port` in `hysteria.yml`); traffic is forwarded to a **loopback-only SOCKS5** inbound on Xray (`socks-hysteria-in` on `127.0.0.1:xray_socks_listen_port`) so routing matches VLESS users. Hysteria uses a **self-signed TLS** cert on the relay (`hysteria_tls_cn`), not the public subscription domain.
- **Sniff** HTTP/TLS/QUIC so domain-based rules work even when clients connect by IP.
- Route Russian / private traffic **direct**; send other traffic to **foreign exits** via a **balancer** backed by **observatory**.
- Expose the **Xray gRPC API** on the public host so the Telegram bot can add/remove VLESS users dynamically.

---

## 2. Inbound (user-facing)

| Setting | Source | Notes |
|---------|--------|--------|
| Protocol | `xray_inbound_protocol` | `vless` |
| Transport | `xray_transport` | `xhttp` |
| Mode | `xray_xhttp_mode` | `packet-up` |
| Security | `xray_security` | `reality` |
| Port | `xray_inbound_port` (role default typically **443**) | Host networking in Docker |
| Reality `dest` / SNI | `sni_domain_default`, `sni_domains` | Masquerade target |
| shortIds | `xray_reality_short_ids` | Must match clients; subscription uses `xray_subscription_short_id` |
| Clients | Empty in static JSON | Filled at runtime via gRPC (`clients: []` in template) |

Sniffing: `xray_sniffing_route_only` controls whether overrides apply only to routing (see `xray.yml` comments).

---

## 3. API inbound (control plane)

A **dokodemo-door** inbound (`api-in`) listens on **`0.0.0.0:xray_grpc_port`** (default **10085**) and forwards to the API service. The Telegram bot uses this to sync user UUIDs to each RU relay.

### Hysteria credential sync (HTTP)

There is **no** gRPC API for Hysteria users. A small **Python** service on each RU (`hysteria-sync.service`) listens on **`hysteria_sync_port`** (TCP). The bot **POST**s a full user list (`Bearer` `vault_hysteria_sync_token`); the handler rewrites `auth.userpass` in `server.yaml` and restarts the **hysteria** container. UFW allows this port **only** from the Telegram bot host (`vault_nl_ams_1_ip`).

---

## 4. Outbound to foreign servers

For each entry in `foreign_servers` (`servers.yml`), the template adds a **VLESS** outbound:

- **Network**: `raw` (TCP)
- **Security**: `reality` with the foreign server’s **public key** and shared **link UUID** (`vault_<tag>_uuid`)
- **Flow**: `xtls-rprx-vision`

This must match **foreign exit inbounds** (same UUID, keys, SNI/shortId policy).

---

## 5. Routing rule order (important)

Rules in `ru-relay.json.j2` are evaluated in order. Summary:

1. **API** traffic (`api-in`) → API outbound.
2. **BitTorrent** → `blocked` (blackhole).
3. **VK / Mail.ru / OK / MAX / selected IP-check domains** → outbound tag `ru_relay_vk_max_exit_tag` (default **`de-fra-1`**), list in `ru_relay_vk_max_domain_matchers` in `xray.yml`.  
   This keeps certain services on a **single** exit IP (see comments in `xray.yml`).
4. **`geosite:category-ru`** → **direct** (exit from RU relay).
5. **`geosite:private`** → **direct**.
6. **`geoip:ru`** → **direct**.
7. **TCP/UDP** → **balancer** `balancer_tag` (default `eu-balancer`).

So “Russian sites” use direct, except the explicit domain list that is forced through the configured foreign exit.

---

## 6. Balancer and observatory

**Balancer** (`routing.balancers`):

- **selector**: all tags from `foreign_servers` (same order as in `servers.yml`).
- **strategy**: `balancer_strategy` in `xray.yml` — repository default is **`roundRobin`**. Alternatives: `leastPing`, `random` (see Xray docs).
- **fallbackTag**: **first** foreign server in `foreign_servers` — used when no healthy node is available.

**Observatory**:

- **subjectSelector**: same foreign outbound tags.
- **probeUrl** / **probeInterval** / **enableConcurrency**: from `observatory_*` in `xray.yml` (default probe `https://www.google.com/generate_204`).

Observatory marks nodes down; the balancer only considers live nodes for strategies that respect it.

---

## 7. DNS on the relay

`ru-relay.json.j2` configures split DNS: queries for `geosite:category-ru` can go through `localhost` (for on-box resolution behavior), plus public resolvers — see the `dns` block in the template and `dns_servers` in `xray.yml`.

---

## 8. Geodata

Routing uses `geosite.dat` / `geoip.dat` under the Xray geodata path (Ansible deploys paths consistently). Refresh on relays:

```bash
make geodata
```

---

## 9. Stats and policy

When monitoring is enabled (`deploy-vpn` with monitoring-related template changes), policy enables per-user and inbound/outbound stats (`statsUserUplink`, `statsUserOnline`, etc.) for limits and Prometheus (see [05-monitoring.md](05-monitoring.md)).

---

## 10. Related

- Foreign side of the tunnel: [04-foreign-exit-configurations.md](04-foreign-exit-configurations.md)
- Adding another RU host: [07-add-ru-relay.md](07-add-ru-relay.md)
