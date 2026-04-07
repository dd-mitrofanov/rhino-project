# [01] Ansible: `is_whitelist` on RU servers and `RU_SERVERS_JSON`

## Description

Introduce an optional boolean **`is_whitelist`** on each entry under **`ru_servers`** in `configs/production/vars/servers.yml`. When **`true`**, the relay is treated as operating under Russian ISP whitelist conditions for subscription ordering and labeling (consumed by the Telegram bot). When the key is **absent**, it must behave as **`false`** (implementations must default in JSON generation and/or Python).

Extend the **`ru_servers_json`** fact in **`playbooks/deploy-telegram-bot.yml`** so each JSON object includes **`"is_whitelist":`** `true` or `false` (boolean, not string). Follow the same Jinja pattern as `tag`, `address`, `port`, etc.

## Goal

Ensure the bot’s **`RU_SERVERS_JSON`** environment (via `configs/production/templates/telegram-bot.env.j2`) carries per-server whitelist metadata without manual `.env` editing.

## Technical details

- **Files to touch**
  - `configs/production/vars/servers.yml` — add `is_whitelist: true` or `false` per RU row as needed; omit on rows that should default to non-whitelist (document in PR that omission = false once playbook emits explicit `false` **or** document that playbook adds default — prefer **explicit boolean in JSON** for every object for clarity).
  - `playbooks/deploy-telegram-bot.yml` — extend the `set_fact` `ru_servers_json` loop to include `is_whitelist` (e.g. `{% if s.is_whitelist is defined %}...{% else %}false{% endif %}` or `{{ s.is_whitelist | default(false) | lower }}` mapped to JSON boolean — verify Ansible/Jinja produces valid JSON `true`/`false`).

- **JSON shape (example)**

```json
{"tag":"ru-msk-1","address":"…","port":443,"location":"moscow","is_whitelist":false,"reality_public_key":"…","sni_domain":"…","short_id":"…","hysteria_port":443,"hysteria_sni":"…"}
```

- **No change** to Vault or `foreign_servers` for this task unless a separate requirement appears.

## Dependencies

- None (first task).

## Usage example (operator story)

As an operator, I set `is_whitelist: true` on the RU relay that sits behind a whitelist ISP and deploy the Telegram bot. The generated `RU_SERVERS_JSON` in the container environment includes `"is_whitelist": true` for that server.

## Acceptance criteria

- It must be true that **`ansible-playbook playbooks/deploy-telegram-bot.yml`** (or project-standard deploy) renders **`ru_servers_json`** as **valid JSON** and each RU object includes **`is_whitelist`** as a JSON boolean.
- It must be true that servers **without** `is_whitelist` in **`servers.yml`** still deploy successfully and result in **`false`** (or equivalent) in JSON.
- It must be true that **`configs/production/templates/telegram-bot.env.j2`** requires **no** structural change if it already passes `{{ ru_servers_json }}` unchanged (only the playbook fact changes).
- It works if production **`servers.yml`** rows are updated to set the flag where operationally needed; test inventory may omit full `ru_servers` (see subtask 03).
