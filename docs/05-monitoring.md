# Monitoring (Prometheus + Grafana)

Metrics from all Xray nodes are scraped by **Prometheus** on **`de-fra-1`** (default inventory), with **Grafana** behind **Caddy** (HTTPS). **xray-exporter** runs next to Xray on each node; **node_exporter** exposes host CPU/memory/disk/network on every VPN/monitoring node; on **`nl-ams-1`** the **user-mapping exporter** exposes `email → telegram_id` for joining Xray user stats in Grafana. **UFW** allows scrape ports only from **`vault_de_fra_1_ip`** (Prometheus), except localhost rules on **`de-fra-1`** where Prometheus and exporters share the host.

---

## 1. Topology (default layout)

```
ru-msk-*, nl-ams-1, nl-ams-2, de-fra-1
    │  Xray (Stats API, gRPC :10085)
    │  xray-exporter → :9550/metrics
    │  node_exporter → :9100/metrics
    │  UFW: 9550 / 9100 from de-fra-1 only (127.0.0.1 for self-scrape on de-fra-1)
    └──────────────────────────┐
                               ▼
nl-ams-1 (Telegram bot host)
    │  PostgreSQL (bot DB)
    │  user-mapping-exporter → :9101/metrics  (rhino_vless_user_mapping)
    │  UFW: 9101 from de-fra-1 only
    └──────────────────────────┐
                               ▼
                    de-fra-1  /opt/monitoring/
                    ┌────────────────────────┐
                    │ Prometheus :9090       │  localhost
                    │ Grafana    :3000       │  localhost
                    │ Caddy      (HTTPS)     │  public :8443 → Grafana
                    └────────────────────────┘
```

**Port 443** on `de-fra-1` is used by Xray, so Grafana is published on **`grafana_https_port`** (default **8443**) via Caddy.

---

## 2. Prometheus scrape jobs (names)

| `job` / job_name | Targets | Purpose |
|------------------|---------|---------|
| `xray` | All `ru_servers` and `foreign_servers` addresses, port **`xray_exporter_port`** (9550) | Xray traffic, up, runtime |
| `node` | Same host list, port **`node_exporter_port`** (9100) | Host CPU, RAM, disk, network |
| `telegram_user_mapping` | **`vault_nl_ams_1_ip`:`user_mapping_exporter_port`** (9101) | Join `target` (VLESS email) → `telegram_id` |

Scrape lists are rendered from **`configs/production/vars/servers.yml`** and Vault IPs in **`configs/production/templates/prometheus.yml.j2`**.

---

## 3. Configuration files

| File | Purpose |
|------|---------|
| `configs/production/vars/monitoring.yml` | xray-exporter, node_exporter, mapping exporter port, Prometheus/Grafana images, paths |
| `configs/production/secrets/vault.yml` | Grafana domain/credentials; server IPs used in Prometheus templates |
| `configs/production/templates/prometheus.yml.j2` | Scrape jobs above |
| `configs/production/templates/docker-compose.yml.j2` | Xray stack + xray-exporter + **node_exporter** on VPN nodes |
| `configs/production/templates/docker-compose.telegram-bot.yml.j2` | Bot + DB + **user-mapping-exporter** |
| `configs/production/templates/docker-compose.monitoring.yml.j2` | Prometheus/Grafana/Caddy on `de-fra-1` |
| `configs/production/templates/Caddyfile.monitoring.j2` | TLS + reverse proxy to Grafana |
| `configs/production/files/grafana-dashboards/*.json` | Bundled dashboards (Xray, Node/host, RU traffic & Telegram) |
| `mapping-exporter/` | Small Python exporter (Prometheus + PostgreSQL) |
| `roles/monitoring/` | Install paths, UFW, compose, provisioning |
| `playbooks/deploy-monitoring.yml` | Runs on `de-fra-1` |

Design rationale and task breakdown: [grafana-monitoring-telegram/overview.md](grafana-monitoring-telegram/overview.md).

---

## 4. Before deploy

1. **Vault**: set Grafana domain and credentials (`vault_grafana_*` — see `configs/production/secrets/vault.yml.example`).
2. **DNS**: **A** record for `vault_grafana_domain` → **`de-fra-1` public IP** (or whichever host runs `deploy-monitoring.yml`).
3. **Vars**: ensure `configs/production/vars/monitoring.yml` exists and matches your image/tag policy.

Caddy obtains Let’s Encrypt certificates using HTTP-01; **port 80** must be reachable on the monitoring host for issuance/renewal (unless you change the role).

---

## 5. Deploy sequence

1. **VPN nodes** (Xray + xray-exporter + node_exporter + UFW):

   ```bash
   make deploy-vpn
   ```

2. **Telegram stack** on `nl-ams-1` (bot, PostgreSQL, user-mapping exporter; UFW for mapping port):

   ```bash
   make deploy-telegram
   ```

3. **Monitoring stack** on `de-fra-1` (Prometheus config with all jobs, Grafana dashboards):

   ```bash
   make deploy-monitoring
   ```

4. **Grafana UI**: `https://<vault_grafana_domain>:8443` (replace port if you changed `grafana_https_port`).

Bundled dashboards include **Rhino / Node & host** (`node-overview.json`) and **Rhino / RU traffic & Telegram** (`rhino-traffic-telegram.json`). The latter uses inbound tag **`vless-in`** by default; if you change **`xray_inbound_tag`** in `configs/production/vars/xray.yml`, update the dashboard queries to match.

---

## 6. Useful commands

```bash
# Scrape targets (on de-fra-1)
curl -s http://127.0.0.1:9090/api/v1/targets | python3 -m json.tool

# xray-exporter on any node
curl -s http://127.0.0.1:9550/metrics | head

# node_exporter on any node
curl -s http://127.0.0.1:9100/metrics | head

# User mapping (on nl-ams-1, or from de-fra-1 after UFW)
curl -s http://127.0.0.1:9101/metrics | grep rhino_vless_user_mapping

# Xray Stats API (example)
docker exec xray xray api statsquery --server=127.0.0.1:10085

# Re-apply monitoring only
make deploy-monitoring

# Re-apply VPN + exporters after Xray template changes
make deploy-vpn
```

---

## 7. When you add or remove servers

Update `configs/production/vars/servers.yml` (and inventory/Vault) first, then:

- `make deploy-vpn` — xray-exporter, **node_exporter**, and UFW on new nodes.
- `make deploy-monitoring` — Prometheus **xray** and **node** scrape lists (and stack refresh).

The **telegram_user_mapping** job always points at **`nl-ams-1`**; it does not change when you add RU relays.

---

## 8. What metrics cover

- **Host**: CPU, memory, disk, network via **node_exporter** (job `node`).
- **Xray**: uplink/downlink bytes per inbound/outbound/user, health (`xray_up`), etc. (job `xray`).
- **Identity join**: **`rhino_vless_user_mapping{target="<VLESS email>",telegram_id="..."}`** for active subscriptions only (job `telegram_user_mapping`). Grafana joins this to **`xray_traffic_*{dimension="user"}`** on **`target`**.

If the mapping target is **down** or the exporter cannot reach PostgreSQL, panels that use the join show **no or partial** Telegram ID data; xray user traffic series are still present under raw `target` labels.

---

## See also

- Architecture context: [01-arch-overview.md](01-arch-overview.md)
- First deploy: [02-first-deploy.md](02-first-deploy.md)
