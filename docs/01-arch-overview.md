# Architecture overview

This document describes the high-level design of the Rhino project: a fault-tolerant, two-level VPN path from clients (e.g. iOS) to the open internet, with split routing for Russian destinations on Russian relays.

For deployment and operations, see [02-first-deploy.md](02-first-deploy.md) and the numbered guides in this directory.

---

## 1. Problem and goals

- **Censorship resistance**: traffic to foreign sites is tunneled through domestic-looking transports (VLESS + Reality, XHTTP in packet-up mode).
- **Split routing**: Russian sites and IPs can exit **directly** from a Russian relay (lower latency, domestic CDN paths).
- **Fault tolerance**: multiple RU relays for client entry; multiple foreign exits with health probing and a configurable balancer on each RU relay.
- **Operations**: configuration in Git, rendered with Ansible/Jinja2; secrets in Ansible Vault.

---

## 2. Topology (two relay levels)

```
Client (subscription lists all RU relays)
    │
    ▼
┌─────────────────────┐
│  RU relay servers   │  VLESS + Reality, XHTTP (packet-up); sniffing + geo rules
│  (observatory +     │
│   balancer)         │
└─────────┬───────────┘
          │ VLESS + Reality to selected foreign exit
          ▼
┌─────────────────────┐
│  Foreign exits      │  VLESS + Reality inbound; outbound to internet
│  (no balancer)      │
└─────────┬───────────┘
          ▼
      Internet
```

**Important:** All exit selection, observatory probes, and balancer logic run **on the RU relays**. Foreign servers only terminate the inner tunnel and forward to the open internet.

---

## 3. Components

### 3.1 Russian relay servers

| Aspect | Implementation |
|--------|----------------|
| **Role** | Entry point for users; routing, sniffing, balancer, observatory |
| **Inbound** | VLESS + Reality, **XHTTP** transport, `packet-up` mode, SNI from a configurable allowlist (`sni_domains` / `sni_domain_default` in `configs/production/vars/xray.yml`) |
| **API** | gRPC/Xray API on `0.0.0.0` (port `xray_grpc_port`, default 10085) for the Telegram bot to add/remove users |
| **Outbound to foreign** | One outbound per foreign server: VLESS + Reality, **TCP `raw`** (not XHTTP) — must match foreign inbounds |
| **Routing** | Sniffing (HTTP/TLS/QUIC); rules for BitTorrent (blocked), selected domains (VK/Mail/OK/MAX and IP-check hosts → dedicated foreign exit), `geosite:category-ru` and `geoip:ru` → direct, private → direct, remainder → balancer |
| **Balancer** | Tag `eu-balancer` (configurable); strategy from `balancer_strategy` in `xray.yml` (repository default: **`roundRobin`**; `leastPing` and `random` are also supported) |
| **Observatory** | Probes foreign outbounds (default `https://www.google.com/generate_204`, interval 1m) so dead nodes are excluded from selection |

### 3.2 Foreign exit servers

| Aspect | Implementation |
|--------|----------------|
| **Role** | Decrypt inner VLESS + Reality from RU; outbound `freedom` to the internet |
| **Inbound** | VLESS + Reality on **TCP `raw`** (aligned with RU outbounds); one link UUID per RU→foreign pair in Vault |
| **API** | Xray API typically bound to **localhost** only on foreign exits (no public gRPC from the internet) |
| **Balancing** | None — handled entirely on RU relays |

### 3.3 Control plane (typical deployment)

- **Telegram bot + PostgreSQL** run on a foreign host (inventory: `telegram_bot`, default `nl-ams-1` in Docker).
- **Subscription HTTP** on the bot serves `GET /{token}` with Bearer auth; builds `vless://` lines from the database and **`RU_SERVERS_JSON`** (injected at deploy time from Ansible).
- **External subscription proxies** on **each RU relay**: Caddy terminates TLS for `subscription_api_domain`; forwards to the bot host. Clients use DNS with **multiple A records** (one per RU) for resilience.

---

## 4. Fault tolerance

| Layer | Mechanism |
|-------|-----------|
| **RU relays** | Subscription lists all RU nodes; clients pick by latency or failover |
| **Foreign exits** | Observatory drops failed nodes; balancer uses live set; **fallback** outbound is the **first** entry in `foreign_servers` in `configs/production/vars/servers.yml` |
| **Subscription URL** | Same hostname resolves to several RU IPs; clients retry another IP if one relay is down |

---

## 5. Data flow (simplified)

1. Client connects to one RU relay (VLESS + Reality, XHTTP packet-up).
2. Xray sniffs the destination; routing rules decide: direct (RU/geo/private), dedicated outbound (specific domain sets), or balancer → foreign.
3. For foreign-bound traffic, the balancer chooses among **live** foreign outbounds (per `balancer_strategy`); observatory maintains liveness.
4. Foreign exit receives the inner connection and sends traffic to the final destination.

---

## 6. Configuration layout (repository)

| Area | Location |
|------|----------|
| Inventory | `inventories/production/hosts.yml` (groups `ru_relays`, `foreign_exits`, `telegram_bot`, `subscription`) |
| Non-secret vars | `configs/production/vars/` (`xray.yml`, `servers.yml`, `monitoring.yml`, …) |
| Secrets | `configs/production/secrets/vault.yml` (encrypted; see `vault.yml.example`) |
| Templates | `configs/production/templates/` (e.g. `ru-relay.json.j2`, `foreign-exit.json.j2`) |
| Playbooks | `playbooks/` (`site.yml`, `deploy-full.yml`, …) |
| Ansible roles | `roles/` |

Vault symlink: `make` targets ensure `inventories/production/group_vars/all/vault.yml` → `configs/production/secrets/vault.yml` so secrets load with the inventory.

---

## 7. Design guarantees (intent)

| Property | How it is addressed |
|----------|---------------------|
| **Availability** | Multiple RU and foreign nodes; observatory + fallback tag; multi-A DNS for subscriptions |
| **Stealth** | Reality + plausible SNI; domestic-looking XHTTP entry on RU |
| **Operability** | Ansible idempotency; dynamic users via gRPC + DB instead of per-user static files |

---

## 8. Related documents

| Topic | Doc |
|-------|-----|
| First deployment | [02-first-deploy.md](02-first-deploy.md) |
| RU relay behavior | [03-ru-relay-configurations.md](03-ru-relay-configurations.md) |
| Foreign exits | [04-foreign-exit-configurations.md](04-foreign-exit-configurations.md) |
| Monitoring | [05-monitoring.md](05-monitoring.md) |
| Bot & subscriptions | [06-bot-and-subs.md](06-bot-and-subs.md) |
| Add RU relay | [07-add-ru-relay.md](07-add-ru-relay.md) |
| Add foreign exit | [08-add-foreign-exit.md](08-add-foreign-exit.md) |
