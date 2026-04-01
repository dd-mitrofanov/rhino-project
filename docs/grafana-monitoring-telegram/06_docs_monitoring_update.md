# [06] Documentation update — `docs/05-monitoring.md`

## Goal

Keep **operator documentation** accurate after adding node_exporter, the Telegram user-mapping exporter, new scrape jobs, ports, and dashboards so future deploys and troubleshooting do not rely on tribal knowledge.

## Scope

**In scope**

- Update **`docs/05-monitoring.md`** to include:
  - **node_exporter**: port (default 9100), purpose, UFW rule summary, deploy playbook touchpoint (`deploy-vpn` / site playbooks).
  - **User-mapping exporter** on `telegram_bot` host: purpose, port, dependency on PostgreSQL, scrape job name, security (UFW from `de-fra-1` only).
  - **Prometheus jobs** table or list: `xray`, `node`, `telegram_user_mapping` (final names as implemented).
  - **Grafana**: list new dashboard files and what each covers (hosts, RU inbound, Telegram traffic).
  - **Deploy order** refinement: e.g. deploy VPN (exporters + node) → deploy telegram stack (mapping exporter) → deploy monitoring (Prometheus picks up all jobs).
  - **Troubleshooting**: curl examples for node_exporter and mapping `/metrics`; note that Telegram ID panels break if mapping target is down or DB unreachable.

**Out of scope**

- Rewriting `docs/01-arch-overview.md` unless a single cross-link is needed (optional one line under control plane / monitoring pointer).

## Dependencies

- **Blocking:** [05](05_grafana_dashboards_host_and_traffic.md) should be **functionally complete** so documented ports and names match reality (or update this doc in the same PR as implementation).

## Implementation notes (files / roles to touch)

- **`docs/05-monitoring.md`** only (per task scope).
- Optional: add a **“See also”** link to `docs/grafana-monitoring-telegram/overview.md` for design rationale and subtask breakdown.

## Acceptance criteria

- A new engineer can follow **only** `docs/05-monitoring.md` and know **which ports** must be open, **from which IP**, and **which make target** refreshes each layer.
- Topology diagram in section 1 is updated or extended to show **node_exporter** and **mapping exporter** (ASCII or Mermaid — match doc style).
- **“When you add or remove servers”** section mentions that **both** xray and **node** scrape lists are regenerated from `servers.yml`.
- No duplicate or contradictory instructions vs. `configs/production/vars/monitoring.yml` and `prometheus.yml.j2` comments.
