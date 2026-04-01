# [05] Grafana dashboards: hosts + Telegram-linked traffic

## Goal

Deliver **operator-ready Grafana dashboards** that combine **node_exporter host views**, **RU `vless-in` aggregates** (from [03](03_ru_vless_in_aggregates.md)), and **per-user traffic by Telegram ID** using the mapping metric from [04](04_telegram_id_mapping_exporter.md), each with **volume-over-range** and **throughput** visualizations.

## Scope

**In scope**

- **Host dashboard** (new JSON under `configs/production/files/grafana-dashboards/`):
  - Variables: `job`, `instance` or `server` matching Prometheus labels from node scrape ([02](02_prometheus_scrape_ufw_node.md)).
  - Panels: CPU, memory, disk space, filesystem usage, network throughput, load — reuse proven node_exporter panel patterns (Grafana dashboard ID community examples as reference only; commit JSON in-repo).
- **Traffic dashboard extensions** (new file or extend `xray-exporter.json` cautiously):
  - **RU `vless-in`:** panels from [03](03_ru_vless_in_aggregates.md).
  - **Per Telegram ID:** tables or time series with `legendFormat` / column showing `telegram_id` (and optional `username` if later joined — out of scope unless exporter extended).
  - For **user** traffic, restrict to **`role="ru-relay"`** for “bytes hitting user-facing inbound” interpretation, consistent with requirement (2) focusing on RU; if product also wants foreign user stats, use separate row with clear title.
- **Dual visualization** for each traffic family:
  - **Volume:** `increase(...[$__range])` or `sum_over_time` patterns appropriate to counters; unit bytes / IEC.
  - **Throughput:** `rate` or `irate` with 5m window aligned with existing dashboard.
- **`roles/monitoring/tasks/main.yml`:** `ansible.builtin.copy` any new dashboard JSON into `{{ monitoring_dir }}/dashboards/` alongside `xray-exporter.json`.

**Out of scope**

- Alertmanager rules (optional follow-up epic).
- Grafana SSO beyond existing Caddy setup.

## Dependencies

- **Blocking:** [01](01_node_exporter_deployment.md), [02](02_prometheus_scrape_ufw_node.md) for host panels.
- **Blocking:** [04](04_telegram_id_mapping_exporter.md) for Telegram ID joins.
- **Strong coordination:** [03](03_ru_vless_in_aggregates.md) for RU inbound panels (queries may be copied verbatim into JSON).

## Implementation notes (files / roles to touch)

- **`configs/production/files/grafana-dashboards/node-overview.json`** (example name) — new.
- **`configs/production/files/grafana-dashboards/rhino-traffic-telegram.json`** or split files per concern; keep dashboard UID/folder consistent with `grafana-dashboard-provider.yml.j2`.
- **`roles/monitoring/tasks/main.yml`:** duplicate the copy pattern used for `xray-exporter.json` for each new file.
- **Join queries:** use `* on(target) group_left(telegram_id) rhino_vless_user_mapping` (final metric name per [04](04_telegram_id_mapping_exporter.md)).
- **High-cardinality warning:** “top N” tables or recording rules may be needed if user count is large; for first version, **table with Grafana transform** “sort by total” capped or **increase over range** sorted is acceptable if documented.
- **Datasource:** existing Prometheus provisioning template `grafana-datasource-prometheus.yml.j2` unchanged.

## Acceptance criteria

- After `make deploy-monitoring`, new dashboards appear in Grafana without manual import.
- Host dashboard shows **all** servers when variable set to “All” (or equivalent).
- **RU vless-in** panels match acceptance in [03](03_ru_vless_in_aggregates.md).
- At least one panel proves **Telegram ID** appears in legend/table for user traffic joined from mapping metric; **raw email-only** panel can remain for debugging but must not be the only view.
- For the same time range, **throughput** panels react to short spikes and **volume** panels reflect cumulative increase over the selected Grafana range.
- No broken references to datasource UID (use default Prometheus name as in existing xray-exporter.json).
