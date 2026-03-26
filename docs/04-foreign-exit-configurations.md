# Foreign exit servers

Foreign exits terminate the **inner** tunnel from RU relays and forward traffic to the public internet. They do **not** run the user-facing XHTTP inbound or the RU→foreign balancer.

Template: `configs/production/templates/foreign-exit.json.j2`.

---

## 1. Role

| Function | Detail |
|----------|--------|
| **Inbound from RU** | VLESS + Reality on **TCP raw** (not XHTTP) — matches RU **outbounds** |
| **Outbound** | `freedom` to the internet |
| **Per-link identity** | Each RU→foreign path uses a **dedicated UUID** in Vault (`vault_<foreign_tag>_uuid`) |
| **Balancing** | None — all selection is on RU relays |

---

## 2. Inbound configuration

- **Tag**: `vless-in` (aligned with RU outbound targeting).
- **Listen**: `0.0.0.0` on `xray_inbound_port` (typically **443**).
- **Clients**: static list in generated config — the foreign server’s **link UUID** for traffic from RU relays (`vault_<tag>_uuid`), with `flow: xtls-rprx-vision`.
- **Reality**: private key from Vault for this host; `serverNames` / `shortIds` consistent with RU outbound `realitySettings`.

RU relays use the foreign **public** Reality key in their outbound; the foreign server holds the **private** key.

---

## 3. API inbound

Foreign exits expose a dokodemo-door for the Xray API on **`127.0.0.1:xray_grpc_port`** (not public). This is **not** used for the Telegram bot user sync (the bot talks to **RU relays**). Stats/monitoring may still scrape the node via the exporter sidecar.

---

## 4. Relationship to other services

| Service | Typical host | Note |
|---------|--------------|------|
| **Telegram bot + PostgreSQL** | Often `nl-ams-1` (same machine as one exit) | Separate Docker stack; not part of Xray foreign template |
| **Subscription HTTP (internal)** | Bot on `nl-ams-1` | RU relays proxy public subscription requests here |
| **Grafana / Prometheus** | Often `de-fra-1` in default inventory | Monitoring stack; Xray still uses 443 on that host; Grafana on another port |

---

## 5. Firewall expectations

- **From RU relays**: TCP to foreign **443** (or your `xray_inbound_port`) must be allowed so inner VLESS + Reality works.
- **From the internet**: only what you intend (often **no** open gRPC from WAN on foreign exits).

---

## 6. Deploying changes

After editing foreign templates, Vault keys, or `foreign_servers` in `servers.yml`:

```bash
make deploy-foreign    # foreign exits only
make deploy-ru           # required if foreign topology or UUIDs changed — RU must get new outbounds + observatory
```

---

## See also

- [03-ru-relay-configurations.md](03-ru-relay-configurations.md) — matching outbounds and balancer.
- [08-add-foreign-exit.md](08-add-foreign-exit.md) — add a new exit.
