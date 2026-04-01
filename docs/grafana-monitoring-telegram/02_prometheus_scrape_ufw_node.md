# [02] Prometheus scrape + UFW for node_exporter

## Goal

Allow **Prometheus on `de-fra-1`** to scrape **node_exporter** on all targets safely: **UFW** permits only the monitoring server IP, and **`prometheus.yml.j2`** includes a dedicated scrape job with useful static labels.

## Scope

**In scope**

- **UFW** on every node running node_exporter:
  - Allow TCP **`node_exporter_port`** from **`vault_de_fra_1_ip`** (mirror `roles/xray/tasks/firewall.yml` xray-exporter rule).
  - On **`de-fra-1`**, allow **localhost** scrape for node_exporter if Prometheus runs in Docker with host networking or published ports — follow the same pattern as xray-exporter localhost rule when `inventory_hostname == 'de-fra-1'`.
- Extend **`configs/production/templates/prometheus.yml.j2`** with a second job (e.g. `job_name: node` or `node_exporter`) listing all `ru_servers` and `foreign_servers` the same way as the existing `xray` job (loop over addresses from `configs/production/vars/servers.yml`).
- Reload/restart monitoring stack when config changes (existing handler notify path in `roles/monitoring/tasks/main.yml`).

**Out of scope**

- Grafana datasource changes (unchanged).
- Scraping the Telegram mapping exporter (see [04](04_telegram_id_mapping_exporter.md)).

## Dependencies

- **Blocking:** [01_node_exporter_deployment.md](01_node_exporter_deployment.md) (exporter must exist and listen on the chosen port).

## Implementation notes (files / roles to touch)

- **`roles/xray/tasks/firewall.yml`** (or shared firewall task file included by VPN deploy): add `community.general.ufw` tasks for `node_exporter_port`, analogous to xray-exporter lines 10–24.
- **`configs/production/templates/prometheus.yml.j2`**: new `scrape_configs` entry with `metrics_path: /metrics`, `scrape_interval` aligned with team SLO (30s is consistent with current global config unless tightened).
- **Labels:** for each target, set at minimum `server` (tag), `role` (`ru-relay` vs `foreign-exit`), `location` — **mirror the xray job** so Grafana template variables stay consistent.
- **`configs/production/vars/monitoring.yml`**: ensure `node_exporter_port` is defined if not already from 01.

**Verification:** From `de-fra-1`, after deploy-monitoring + deploy-vpn, `curl` to `http://<target_ip>:9100/metrics` should work only from bastion/Prometheus path, not from arbitrary IPs (UFW).

## Acceptance criteria

- Prometheus **Targets** UI (or `api/v1/targets`) shows all RU and foreign server IPs under the node job with state **up** after full deploy.
- UFW on a sample non-`de-fra-1` node allows **9100** (or configured port) **only** from `vault_de_fra_1_ip`, not from the world.
- `de-fra-1` self-scrape for node_exporter works without opening the port publicly.
- No regression to existing **xray** scrape job (same file, valid YAML).
