# [04] Telegram user ID mapping metrics (PostgreSQL → Prometheus)

## Goal

Enable Grafana/Prometheus to correlate **xray-exporter user traffic** (`dimension="user"`, label **`target`** = VLESS email) with **`telegram_id`** from the bot database, without exposing PostgreSQL to the internet or to all relays.

## Scope

**In scope**

- A **small HTTP `/metrics` exporter** running on the **`telegram_bot` inventory host** (default **`nl-ams-1`**), with read-only SQL access to the same PostgreSQL as the bot.
- For each relevant row in **`subscriptions`** (and join **`users`** if needed for labels such as `active`), emit at least one Prometheus series that maps **Xray client email string** → **`telegram_id`**.
- Support **both** email formats used in production code (`bot/app/xray/subscription_email.py`):
  - Current: `sub_<telegram_id>_<8_hex_of_subscription_id>@rhino`
  - Legacy: `sub-<full_subscription_uuid_hex>@rhino`
- Expose metrics under a **stable metric name** with low cardinality (one series per known email string per active subscription; inactive subscriptions policy: see below).
- **UFW:** allow scrape port from **`vault_de_fra_1_ip`** only (and localhost if exporter binds only inside Docker — follow docker-compose port publishing pattern).
- **Prometheus:** new scrape job in `prometheus.yml.j2` targeting the bot host public IP (or VPN-internal if introduced later — default inventory uses public IPs like other jobs).

**Out of scope**

- Writing to the database from the exporter.
- Replacing xray-exporter or querying Xray API from this component (optional future optimization only if specified later).
- Storing historical traffic in PostgreSQL.

**Inactive subscriptions:** Emit mapping only for **`subscriptions.active = true`** unless product requires seeing inactive users’ last traffic; document choice in implementation. Default recommendation: **active only** to limit cardinality.

## Dependencies

- **Blocking:** none for design; implementation needs Docker/network access to Postgres on bot host.
- **Informs:** [05_grafana_dashboards_host_and_traffic.md](05_grafana_dashboards_host_and_traffic.md).

## Implementation notes (files / roles to touch)

- **New code or container image:** minimal service (Python with `prometheus_client`, or Go) that:
  - On scrape (or every N seconds with cache), runs SQL like: load `telegram_id`, `id` (subscription UUID) from `subscriptions` where `active` per policy.
  - For each row, compute **both** `xray_subscription_email` and `legacy_xray_subscription_email` logic — **must match bot** (consider shared module or duplicating the exact string rules with tests).
  - Expose e.g. `rhino_vless_user_mapping{target="<email>",telegram_id="<id>"} 1` (gauge). Use **string** `telegram_id` label to avoid float precision issues with large Telegram IDs.
- **`configs/production/templates/docker-compose.telegram-bot.yml.j2`**: add service `user-mapping-exporter` (name TBD) on a **dedicated port** (e.g. 9101 — avoid clash with node_exporter 9100 on the same host).
- **`roles/telegram-bot/tasks/main.yml`**: template env vars for `DATABASE_URL` (read-only user optional future hardening) or reuse same DB credentials as bot if acceptable; document security tradeoff.
- **`roles/telegram-bot` UFW**: allow new port from `vault_de_fra_1_ip`.
- **`configs/production/templates/prometheus.yml.j2`**: job e.g. `telegram_user_mapping` with one static target `vault_nl_ams_1_ip:new_port` and label `role=telegram-bot` or similar.
- **`configs/production/vars/monitoring.yml`**: image/tag/port vars for the exporter service.

**PromQL join pattern (for implementers of 05):**

```promql
sum by (telegram_id, server) (
  irate(xray_traffic_downlink_bytes_total{dimension="user",role="ru-relay"}[5m])
  * on(target) group_left(telegram_id) rhino_vless_user_mapping
)
```

Adjust metric name and labels to match the implemented exposition. **Requirement:** the **`target` label** on the mapping metric must **exactly equal** the `target` label on xray traffic series for the join to work.

**Security:** bind exporter to docker internal network if Prometheus can reach it — today Prometheus uses **public IPs**, so published port + UFW is the primary control; prefer no public exposure beyond scrape IP.

## Acceptance criteria

- Scraping `http://<nl-ams-1-ip>:<port>/metrics` from `de-fra-1` shows `rhino_vless_user_mapping` (or chosen name) with **correct** `telegram_id` for a test subscription.
- For a subscription known to use **legacy** email in Xray, a matching **`target`** label is present so traffic still joins.
- Prometheus target for this job is **up** after `make deploy-monitoring` + bot stack deploy.
- UFW denies the mapping port from arbitrary IPs; allows from Prometheus host.
- Exporter failure does not break the bot stack (healthcheck / restart policy; compose `depends_on` only where safe).
