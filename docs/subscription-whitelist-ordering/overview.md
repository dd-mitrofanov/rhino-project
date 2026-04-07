# Task: Subscription ordering by whitelist and deterministic display names

## Context and motivation

Some Russian relay servers operate under ISP **whitelist** conditions; others do not. Clients should see subscription links in a **predictable global order** (non-whitelist XHTTP first, then whitelist XHTTP, then the same split for Hysteria2) so behavior is consistent, while **within** each segment order should vary per request to spread load. Display names in URIs must be **stable per user and server** (no flicker on refresh) but must **not** retain the legacy `{prefix}-{tag}-xhttp` / `hysteria-2` pattern.

This aligns with the architecture in [docs/01-arch-overview.md](../01-arch-overview.md): subscription HTTP builds lines from PostgreSQL and **`RU_SERVERS_JSON`** injected at deploy from Ansible.

## Global goal

- Each RU server is optionally marked **`is_whitelist`** in Git/Ansible and in **`RU_SERVERS_JSON`**.
- **`GET /{token}`** uses the four-group order below for whatever server set applies to that key (full inventory vs restricted — see **`subscriptions.is_whitelist`** in [docs/06-bot-and-subs.md](../06-bot-and-subs.md)), with random **within-group** shuffling each request.
- Fragment display names follow only the four documented patterns, with **`{n}`** from a **deterministic** hash (same spirit as `_two_digit_prefix`).
- Legacy naming patterns are removed from subscription output.
- Configuration and user-facing docs reflect the new field and behavior.

## Architectural brief

| Area | Change |
|------|--------|
| **Ansible / data** | Add optional boolean `is_whitelist` per `ru_servers` row in `configs/production/vars/servers.yml`; default **`false`** when omitted. Extend `ru_servers_json` in `playbooks/deploy-telegram-bot.yml` (same inline JSON pattern as existing fields). |
| **Bot runtime** | `RU_SERVERS_JSON` parsed in `bot/app/config.py` → `settings.ru_servers`; each dict may include `"is_whitelist": true/false`. |
| **Subscription HTTP** | `bot/app/subscription_http.py`: partition servers into four lists by `(protocol: xhttp vs hysteria, is_whitelist)`; emit **XHTTP groups before Hysteria2 groups**; shuffle a **copy** of each list per request; build `server_name` / fragment via a small helper using **SHA-256** (or same family as `_two_digit_prefix`) over `subscription_token + server_tag + protocol_kind + whitelist_flag`. |

**Global link order (fixed):**

1. XHTTP, `is_whitelist == false`
2. XHTTP, `is_whitelist == true`
3. Hysteria2, `is_whitelist == false`
4. Hysteria2, `is_whitelist == true`

**Display name patterns (fragment after `#` in URI):**

| Segment | Pattern |
|---------|---------|
| XHTTP, not whitelist | `"{n} XHTTP"` |
| XHTTP, whitelist | `"{n} XHTTP WL"` |
| Hysteria2, not whitelist | `"{n} Hysteria2"` |
| Hysteria2, whitelist | `"{n} Hysteria2 WL"` |

**`{n}`:** deterministic integer in **1–9999** (inclusive) from hash — see [02_subscription_http_ordering_and_names.md](02_subscription_http_ordering_and_names.md).

## Sub-tasks (table of contents)

| # | Document | Summary |
|---|----------|---------|
| 01 | [01_ansible_is_whitelist_and_ru_servers_json.md](01_ansible_is_whitelist_and_ru_servers_json.md) | Ansible vars + `RU_SERVERS_JSON` injection; default `false` |
| 02 | [02_subscription_http_ordering_and_names.md](02_subscription_http_ordering_and_names.md) | Grouping, shuffle, naming helper, remove legacy names; `config.py` docstring |
| 03 | [03_docs_and_test_inventory_notes.md](03_docs_and_test_inventory_notes.md) | `docs/06-bot-and-subs.md`; test inventory / fixtures notes |

**Dependency graph:** `01` → `02` (bot logic assumes JSON shape). `03` can proceed after `02` is specified; doc updates can be merged in the same PR as implementation or immediately after.

## Definition of done (whole project)

- Production `servers.yml` and deploy playbook produce valid JSON with optional `is_whitelist`; omitting the key behaves as `false`.
- Subscription endpoint matches the four-group order; within-group order is random per request but groups are stable.
- Display names match only the four patterns; no `{prefix}-{tag}-xhttp` or `-hysteria-2` style strings.
- `ru_servers` property docstring in `config.py` documents `is_whitelist`.
- Short operator note in `docs/06-bot-and-subs.md` (ordering + flag).
- No unnecessary drive-by refactors outside listed files; tests added or updated if the repo has subscription tests (see subtask 03).
