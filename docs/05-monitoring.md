# Monitoring (Prometheus + Grafana)

Metrics from all Xray nodes are scraped by **Prometheus** on **`de-fra-1`** (default inventory), with **Grafana** behind **Caddy** (HTTPS). **xray-exporter** runs next to Xray on each node; **UFW** allows scrapes only from the Prometheus host.

---

## 1. Topology (default four-server layout)

```
ru-msk-1, ru-msk-2, nl-ams-1, de-fra-1
    │  Xray (Stats API, gRPC :10085)
    │  xray-exporter → :9550/metrics
    │  UFW: 9550 allowed only from de-fra-1
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

## 2. Configuration files

| File | Purpose |
|------|---------|
| `configs/production/vars/monitoring.yml` | Exporter/Prometheus/Grafana images, ports, host paths (required by `deploy-monitoring.yml`) |
| `configs/production/secrets/vault.yml` | `vault_grafana_domain`, `vault_grafana_admin_user`, `vault_grafana_admin_password` |
| `configs/production/templates/prometheus.yml.j2` | Scrape targets (built from inventory / server lists) |
| `configs/production/templates/docker-compose.monitoring.yml.j2` | Stack definition |
| `configs/production/templates/Caddyfile.monitoring.j2` | TLS + reverse proxy to Grafana |
| `configs/production/files/grafana-dashboards/xray-exporter.json` | Bundled dashboard |
| `roles/monitoring/` | Install paths, UFW, compose, provisioning |
| `playbooks/deploy-monitoring.yml` | Runs on `de-fra-1` |

---

## 3. Before deploy

1. **Vault**: set Grafana domain and credentials (`vault_grafana_*` — see `configs/production/secrets/vault.yml.example`).
2. **DNS**: **A** record for `vault_grafana_domain` → **`de-fra-1` public IP** (or whichever host runs `deploy-monitoring.yml`).
3. **Vars**: ensure `configs/production/vars/monitoring.yml` exists and matches your image/tag policy (a baseline is committed in this repo).

Caddy obtains Let’s Encrypt certificates using HTTP-01; **port 80** must be reachable on the monitoring host for issuance/renewal (unless you change the role).

---

## 4. Deploy sequence

1. **Enable Stats API + exporter on all VPN nodes** (usually already applied with modern `deploy-vpn`):

   ```bash
   make deploy-vpn
   ```

   This adds stats/policy to Xray, runs **xray-exporter** on port **9550**, and restricts **9550** in UFW to the Prometheus host.

2. **Deploy the monitoring stack**:

   ```bash
   make deploy-monitoring
   ```

3. **Open Grafana**: `https://<vault_grafana_domain>:8443` (replace port if you changed `grafana_https_port`).

---

## 5. Useful commands

```bash
# Scrape targets (on de-fra-1)
curl -s http://127.0.0.1:9090/api/v1/targets | python3 -m json.tool

# Exporter locally on any node
curl -s http://127.0.0.1:9550/metrics | head

# Xray Stats API (example)
docker exec xray xray api statsquery --server=127.0.0.1:10085

# Re-apply monitoring only
make deploy-monitoring

# Re-apply VPN + exporters after Xray template changes
make deploy-vpn
```

---

## 6. When you add or remove servers

Update `configs/production/vars/servers.yml` (and inventory/Vault) first, then:

- `make deploy-vpn` — exporters and UFW on new nodes; Prometheus config refresh on monitoring deploy.
- `make deploy-monitoring` — Prometheus scrape list and stack.

---

## 7. What metrics cover

- **Runtime**: memory, GC, goroutines (via exporter/Xray stats).
- **Traffic**: uplink/downlink bytes per inbound/outbound/user (where user stats are available).
- **Health**: `xray_up` style indicators per target (as provided by the exporter/dashboard).

---

## See also

- Architecture context: [01-arch-overview.md](01-arch-overview.md)
- First deploy: [02-first-deploy.md](02-first-deploy.md)
