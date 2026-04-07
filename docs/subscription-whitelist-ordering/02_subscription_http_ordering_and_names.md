# [02] Subscription HTTP: four-group order, shuffle, deterministic display names

## Description

Rewrite **`bot/app/subscription_http.py`** subscription assembly for **`GET /{token}`**:

1. **Partition** `settings.ru_servers` into four lists using normalized **`is_whitelist`** (treat missing/`None` as **`false`**):
   - XHTTP non-WL, XHTTP WL, Hysteria2 non-WL, Hysteria2 WL.
2. **Shuffle** each list with **`random.shuffle`** on a **copy** of the list (do not mutate a shared list reused across loops).
3. **Emit links** in **global order**: all XHTTP lines in group order above (two groups), then all Hysteria2 lines (two groups). Each group emits one link per server in that group after shuffle.
4. **Display names** (fragment / `server_name` passed to `build_vless_link` / `build_hysteria2_link`): **only** these patterns:
   - `"{n} XHTTP"` | `"{n} XHTTP WL"` | `"{n} Hysteria2"` | `"{n} Hysteria2 WL"`  
   where **`{n}`** is a decimal string for an integer in **1–9999** inclusive, computed **deterministically** from:

   `subscription_token`, `server["tag"]`, a fixed **`protocol_kind`** string (`"xhttp"` / `"hysteria2"`), and **`whitelist_flag`** (`True`/`False` or `0`/`1` — pick one convention and use it consistently).

   Use the same **spirit** as **`_two_digit_prefix`**: e.g. **SHA-256** of a UTF-8-encoded concatenation, then **`int(..., 16) % 9999 + 1`** (or ` % 10000` with special-case for 0 → 1) so the value is never 0 and stays in 1–9999.

5. **Remove** the legacy **`base = f"{_two_digit_prefix(...)}-{tag}"`** naming and **`f"{base}-xhttp"`** / **`f"{base}-hysteria-2"`** patterns. Replace **`_two_digit_prefix`** usage for subscription display names with the new helper (either rename/refactor or add a dedicated function; avoid dead code).

6. Update **`bot/app/config.py`**: extend the **`ru_servers`** property docstring to mention **`is_whitelist`** (optional boolean, default false when absent in JSON).

## Goal

Match product ordering and labeling rules while keeping names stable across refreshes and randomizing only within-group order per request.

## Technical details

- **Files to touch**
  - `bot/app/subscription_http.py` — main logic.
  - `bot/app/config.py` — docstring on **`ru_servers`**.
  - Optionally **`bot/app/vless.py`** / **`bot/app/hysteria_uri.py`** — **only** if signatures need changes (prefer no change; pass `server_name` as today).

- **Helpers**
  - e.g. `_subscription_display_number(token: str, tag: str, protocol_kind: str, is_whitelist: bool) -> str` returning `"1234"` (no zero-padding required; natural decimal string).
  - e.g. `_subscription_server_name(...)` returning the full fragment string.

- **Ordering pseudocode**

```text
groups = [xhttp_non_wl, xhttp_wl, hy2_non_wl, hy2_wl]
for g in groups:
    copy = list(g)
    random.shuffle(copy)
    for server in copy:
        emit link with correct protocol and server_name
```

## Dependencies

- **01** must be complete (or **`RU_SERVERS_JSON`** manually shaped in dev) so **`is_whitelist`** exists in parsed dicts; Python must still default missing key to non-whitelist.

## Usage example (user story)

As a subscriber, when I refresh my subscription URL, I still see the same numeric label next to each server name for a given line, but the **order** of lines **within** each protocol/whitelist bucket may change. XHTTP lines always appear **before** Hysteria2 lines, and non-whitelist XHTTP before whitelist XHTTP.

## Acceptance criteria

- It must be true that the **relative global order** of the four segments is: XHTTP non-WL → XHTTP WL → Hysteria2 non-WL → Hysteria2 WL.
- It must be true that **within** each segment, two consecutive requests **may** differ in server order (shuffle), and the implementation uses **`random.shuffle`** on a **copy** of the list.
- It must be true that every emitted **`server_name`** / fragment matches **exactly** one of: `"{n} XHTTP"`, `"{n} XHTTP WL"`, `"{n} Hysteria2"`, `"{n} Hysteria2 WL"` with **`{n}`** in 1–9999.
- It must be true that **`{n}`** for a given subscription + server + protocol + whitelist flag is **unchanged** across repeated calls (deterministic hash).
- It must be true that legacy patterns **`-xhttp`**, **`{prefix}-{tag}`**, and **`-hysteria-2`** do **not** appear in subscription output.
- It must be true that **`is_whitelist`** missing from a server dict is treated as **false**.
- If the repository has tests for subscription formatting, they are updated or added to cover ordering constraints and name patterns.
