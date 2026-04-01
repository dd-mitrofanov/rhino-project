# [03] RU relay `vless-in` traffic aggregates (PromQL + dashboard spec)

## Goal

Expose in Grafana the **user-facing inbound** traffic on RU relays only, for the inbound tag configured as **`xray_inbound_tag`** in `configs/production/vars/xray.yml` (default **`vless-in`**), showing **cluster total** and **per ru-relay** breakdown, with both **bytes over selected range** and **current throughput**.

## Scope

**In scope**

- **PromQL** design documented and implemented as **Grafana panel queries** (in [05](05_grafana_dashboards_host_and_traffic.md) or a dedicated dashboard JSON committed under `configs/production/files/grafana-dashboards/`).
- Metrics source: existing **xray-exporter** counters:
  - `xray_traffic_uplink_bytes_total`
  - `xray_traffic_downlink_bytes_total`
  - With `dimension="inbound"` and `target` equal to the configured inbound tag (verify on a live RU node that `target` matches `xray_inbound_tag`; Xray stats name is typically the inbound tag).
- **Filter:** `role="ru-relay"` (Prometheus label from `prometheus.yml.j2`) so foreign exits are excluded.
- **Queries:**
  - **Volume over `$__range`:** `sum(increase(...[$__range]))` aggregated **total** across RU; `sum by (server) (increase(...[$__range]))` **per relay**.
  - **Throughput:** `sum(rate(...[5m]))` or `sum(irate(...[5m]))` (team choice: `irate` for short-step responsiveness per existing xray dashboard style); same aggregations.

**Out of scope**

- Changing Xray stats configuration on RU (already enabled in `configs/production/templates/ru-relay.json.j2`: `statsInboundUplink` / `statsInboundDownlink`).
- Per-user breakdown (handled via Telegram join in [04](04_telegram_id_mapping_exporter.md) + [05](05_grafana_dashboards_host_and_traffic.md)).

## Dependencies

- **Blocking:** none (metrics already scraped).
- **Coordination:** [05](05_grafana_dashboards_host_and_traffic.md) imports these queries into the final dashboard artifact.

## Implementation notes (files / roles to touch)

- **`configs/production/files/grafana-dashboards/`**: new JSON (e.g. `ru-vless-in-traffic.json`) **or** new rows/panels in an existing dashboard — prefer a **focused dashboard** or clearly labeled row to avoid cluttering the generic xray-exporter import.
- **Grafana variable:** optional `inbound_tag` defaulting to `vless-in` sourced from docs; implementation may hardcode matching `xray_inbound_tag` if Grafana cannot read Ansible vars (acceptable if documented: “change panel when changing `xray_inbound_tag`” or use constant variable in JSON).
- **Example total downlink volume (illustrative):**

  `sum(increase(xray_traffic_downlink_bytes_total{role="ru-relay",dimension="inbound",target="vless-in"}[$__range]))`

  Replace `vless-in` with templated value when variable exists.

- **Example per-relay:** add `sum by (server) (...)`.

**Edge case:** If `target` label differs from tag in config (exporter quirk), acceptance includes verifying the actual label value once in Prometheus and aligning queries.

## Acceptance criteria

- Panels show **non-empty** data when RU relays carry traffic (in a test/staging environment or after smoke test).
- **Total** series equals the **sum of per-relay** series for the same metric and time range (within PromQL aggregation semantics).
- Foreign exit series are **absent** from these panels (enforced by `role="ru-relay"`).
- Both **range increase** and **rate/irate** panel types exist for uplink and downlink (or combined with legend split).
- Changing `xray_inbound_tag` in `xray.yml` is documented: operator knows to update Grafana constant/variable to match.
