# [03] Documentation and test inventory notes

## Description

Add a **short** subsection to **`docs/06-bot-and-subs.md`** covering:

- The **server-level** **`is_whitelist`** flag (source: **`configs/production/vars/servers.yml`** → **`RU_SERVERS_JSON`**).
- **Per-subscription** **`subscriptions.is_whitelist`** in PostgreSQL (full vs restricted plaintext) — see current **`docs/06-bot-and-subs.md`** for the canonical operator description.
- The **global link order** (four groups: XHTTP non-WL, XHTTP WL, Hysteria2 non-WL, Hysteria2 WL).
- That **within** each group, order is **randomized per request**; display names are **deterministic** (stable on refresh).

Keep the tone consistent with existing tables and cross-links (e.g. deploy playbook, `RU_SERVERS_JSON`).

Optionally add a one-line pointer to **`docs/subscription-whitelist-ordering/overview.md`** only if the team wants a deep link to the feature spec (not required if the section is self-contained).

Document **test / non-production** expectations:

- **`inventories/test`** may not mirror full **`ru_servers`**; **`configs/production/vars/servers.yml`** remains the **source of truth** for production shape.
- If local or CI tests load **`RU_SERVERS_JSON`**, document or add fixtures with minimal JSON including **`is_whitelist`** where behavior is tested.

## Goal

Operators and future contributors understand ordering and the new flag without reading Python first.

## Technical details

- **Files to touch**
  - `docs/06-bot-and-subs.md` — additive section (no large rewrites).
  - If tests exist: e.g. `bot/tests/...` or pytest paths — update fixtures only as needed (reference actual layout when implementing).

## Dependencies

- **02** (behavior finalized) so documentation matches shipped logic.

## Usage example (reader story)

As a reader of `06-bot-and-subs`, I see why some servers are labeled **WL** and why my client shows XHTTP before Hysteria2.

## Acceptance criteria

- It must be true that **`docs/06-bot-and-subs.md`** mentions **`is_whitelist`**, four-group ordering, and within-group shuffle in plain language.
- It must be true that test inventory limitations are **noted** (either in `06-bot-and-subs` or in test README/fixture comment — pick one place and keep it brief).
- It must be true that no other markdown files are edited unless the team explicitly expands scope.
