# [01] Deploy node_exporter on all VPN and monitoring nodes

## Goal

Provide standard **host-level metrics** (CPU, memory, filesystem, network, etc.) for every production server that runs Xray or the monitoring stack, using **Prometheus node_exporter**, deployed and managed consistently with the rest of the Ansible-based infrastructure.

## Scope

**In scope**

- Install and run **node_exporter** on:
  - All hosts in `ru_relays`
  - All hosts in `foreign_exits` (includes `de-fra-1`, `nl-ams-1`, `nl-ams-2`, and any future entries aligned with `configs/production/vars/servers.yml`)
- Configurable image/tag and listen port via vars (default port **9100**, conventional for node_exporter).
- Lifecycle tied to existing VPN/common deploy playbooks so `make deploy-vpn` (or equivalent) rolls out the exporter with the rest of the node stack.

**Out of scope**

- Prometheus scrape config and UFW from Prometheus (handled in [02_prometheus_scrape_ufw_node.md](02_prometheus_scrape_ufw_node.md)).
- Grafana panels (handled in [05_grafana_dashboards_host_and_traffic.md](05_grafana_dashboards_host_and_traffic.md)).
- Custom textfile metrics or process exporters.

## Dependencies

- **Blocking:** none.
- **Informs:** [02](02_prometheus_scrape_ufw_node.md), [05](05_grafana_dashboards_host_and_traffic.md).

## Implementation notes (files / roles to touch)

- **`configs/production/vars/monitoring.yml`** (or a dedicated `node_exporter_*` block): image (e.g. `prom/node-exporter`), tag, `node_exporter_port: 9100`, optional collector flags if the team wants to disable sensitive collectors.
- **`roles/xray/`** (or a small new **`roles/node_exporter/`** included from relay/foreign playbooks): tasks to run node_exporter — **prefer the same container runtime model as Xray** (Docker) for consistency; mount host `/proc`, `/sys`, `/` (read-only) as required by upstream image docs.
- **`playbooks/deploy-ru-relay.yml`** / **`playbooks/deploy-foreign-exit.yml`** (or shared role included by both): ensure node_exporter task list runs on every VPN host.
- **`playbooks/setup-common.yml`**: only if the team chooses a single “common monitoring agent” pass for all hosts; otherwise keep agents with Xray playbooks to avoid running Docker on unexpected groups.
- **Inventory**: no new groups required if “all VPN nodes” = `ru_relays` ∪ `foreign_exits` (matches user requirement and `servers.yml`).

**Design choice to document in implementation:** On `de-fra-1`, node_exporter covers the **host** running Docker (Prometheus/Grafana containers are separate); that is sufficient for “monitoring host” capacity planning unless the project later adds cAdvisor.

## Acceptance criteria

- It must be possible to `curl http://127.0.0.1:<node_exporter_port>/metrics` on **each** `ru_relays` and `foreign_exits` host after deploy and see `node_*` metrics.
- It must work without manual per-host steps beyond Ansible inventory/Vault already used for deploy.
- It must be **disabled or not started** on groups outside production VPN/monitoring scope (e.g. test inventory) unless explicitly included.
- Container/service must be **restart-stable** (systemd or Docker restart policy aligned with xray-exporter).
- Vars must allow changing the **port** in one place so [02](02_prometheus_scrape_ufw_node.md) can reference the same variable.
