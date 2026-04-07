# [02] `subscription_format`, subscription HTTP handler, and tests

## Description

### 1. `build_subscription_link_lines` (`bot/app/subscription_format.py`)

Extend the public API so the builder knows whether the **subscription** is full or restricted.

**Filtering rule (normative):**

- If **subscription** `is_whitelist` is **`True`**: use the full `servers` list — **identical** behavior to today (partition by server `_is_whitelist`, four groups, shuffle per group, naming).
- If **subscription** `is_whitelist` is **`False`**: first reduce `servers` to **`[s for s in servers if not _is_whitelist(s)]`**, then run the **same** four-group pipeline on that reduced list. WL segments will be **empty**; non-WL segments contain all links for the remaining relays.

**Naming:** Reuse existing `_subscription_server_name(..., wl_flag)` semantics — for restricted keys, links in non-WL segments keep non-WL-style names; no WL-only servers appear.

**API shape:** Prefer an explicit keyword-only parameter, e.g. `subscription_is_whitelist: bool = True`, to avoid confusion with per-server keys. Document in a short docstring that this is the **subscription-key** flag, not the server dict field.

### 2. `subscription_http.get_subscription` (`bot/app/subscription_http.py`)

Pass `subscription.is_whitelist` into `build_subscription_link_lines` (after subtask 01 exposes the ORM attribute).

Search the codebase for other call sites of `build_subscription_link_lines` and update them (tests, sync, scripts) so signatures stay consistent.

### 3. Tests (`bot/tests/test_subscription_http.py` and/or new module)

Add coverage for:

- **Full subscription** (`subscription_is_whitelist=True`) with a mixed server list: behavior matches existing `test_build_subscription_lines_segment_order_and_no_legacy_names` (can parametrize or duplicate minimal assertion).
- **Restricted subscription** (`subscription_is_whitelist=False`): with servers including both WL and non-WL, **only** non-WL servers appear; count of lines equals `2 * number_of_non_wl_servers` (XHTTP + Hysteria2 per server); no fragment ends with ` XHTTP WL` or ` Hysteria2 WL`.
- Edge case: restricted subscription with **zero** non-WL servers in the fixture → empty line list (or document if product prefers a different behavior — default spec: **empty list**, still valid plaintext).

Keep patching `random.shuffle` where deterministic ordering is required, consistent with existing tests.

Optional: FastAPI client test for `GET /{token}` with a mocked DB session returning a subscription with `is_whitelist=False` — only if the project already has similar HTTP tests; otherwise unit tests on the builder + a thin wiring check is enough.

## Goal

Enforce per-key visibility in the subscription plaintext and prevent regressions.

## Technical details

### Function signature (illustrative)

```python
def build_subscription_link_lines(
    *,
    subscription_token: str,
    vless_uuid: str,
    hysteria_password: str,
    servers: list[dict],
    subscription_is_whitelist: bool = True,
) -> list[str]:
    ...
```

### Filtering (illustrative)

```python
if not subscription_is_whitelist:
    servers = [s for s in servers if not _is_whitelist(s)]
# then existing non_wl / wl split and groups unchanged
```

### HTTP (illustrative)

```python
links = build_subscription_link_lines(
    subscription_token=subscription.token,
    vless_uuid=str(subscription.vless_uuid),
    hysteria_password=subscription.hysteria_password,
    servers=list(settings.ru_servers),
    subscription_is_whitelist=subscription.is_whitelist,
)
```

## Dependencies

**01** — `Subscription.is_whitelist` must exist on the model and in the database.

## Usage examples (user story)

- **As a restricted user**, when I open my subscription URL, I only see VLESS/Hysteria2 lines for relays that are **not** server-whitelist in `RU_SERVERS_JSON`.
- **As a full-access user**, my link list is unchanged from before this feature.

## Acceptance criteria

- It works if `build_subscription_link_lines(..., subscription_is_whitelist=False)` never emits a link for a server dict with `is_whitelist is True`.
- It works if `subscription_is_whitelist=True` produces the same segment structure and line count as before for the same `servers` input (given the same shuffle mock).
- `get_subscription` passes the DB field through so behavior is end-to-end for real tokens.
- All call sites compile; test suite passes.
- Restricted + all servers WL-only fixture yields no links (or documented alternative).
