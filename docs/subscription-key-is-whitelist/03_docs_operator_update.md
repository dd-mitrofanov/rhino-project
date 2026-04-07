# [03] Operator documentation: subscription vs server `is_whitelist`

## Description

Update `docs/06-bot-and-subs.md` to document:

1. **Server-level** `is_whitelist` in `RU_SERVERS_JSON` (already described) — controls which **segment** a relay belongs to when building the **full** list.
2. **Subscription-level** `is_whitelist` in PostgreSQL (`subscriptions.is_whitelist`) — controls whether the user receives the **full** four-segment list (`true`) or **only non-whitelist servers** (`false`), using the same `_is_whitelist` semantics for each server dict.

Clarify that for **restricted** keys, the WL segments are **empty** but the global order rule is unchanged (non-WL XHTTP, then WL XHTTP, then non-WL H2, then WL H2).

Add a short note on **defaults**: existing and new keys default to `true` until operators change rows (e.g. via SQL or a future bot command).

Run a quick repository grep for `is_whitelist` / `subscriptions` in `docs/` and update any other file that would otherwise contradict the new behavior.

## Goal

Operators and implementers can reason about two different flags without conflating them.

## Technical details

- **Files:** primary `docs/06-bot-and-subs.md`; adjust section “Subscription link order and `is_whitelist`” or add a subsection “Per-subscription access (`subscriptions.is_whitelist`)”.
- **No code** in this task — documentation only.

## Dependencies

**02** — Docs should match shipped behavior (filtering in `build_subscription_link_lines` and HTTP).

## Usage examples (user story)

- **As an operator**, I read `docs/06-bot-and-subs.md` and understand how to grant full vs restricted access using the DB column vs `servers.yml`.

## Acceptance criteria

- The doc explicitly names the DB column and its `true`/`false` meaning relative to the subscription URL output.
- The doc states that new and migrated subscriptions default to full access (`true`).
- No remaining doc implies that every key always sees all servers regardless of DB state.
