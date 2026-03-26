"""Xray gRPC client for managing VLESS clients on RU relay servers.

Communicates with Xray-core's HandlerService and StatsService APIs
using manual protobuf serialization — no generated stubs or
grpcio-tools dependency required.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import grpc
import grpc.aio

logger = logging.getLogger(__name__)


class XrayClientError(Exception):
    """Raised when an Xray gRPC operation fails on one or more servers."""

    def __init__(self, message: str, failures: dict[str, str]) -> None:
        super().__init__(message)
        self.failures = failures


# ---------------------------------------------------------------------------
# Protobuf manual serialization helpers
#
# Xray uses standard protobuf wire format.  We encode the handful of
# messages we need by hand so the project doesn't depend on cloning
# xray-core and running protoc.
# ---------------------------------------------------------------------------

def _encode_varint(value: int) -> bytes:
    """Encode an unsigned varint."""
    parts: list[int] = []
    while value > 0x7F:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    parts.append(value & 0x7F)
    return bytes(parts)


def _encode_field(field_number: int, wire_type: int, data: bytes) -> bytes:
    """Encode a protobuf field tag + data."""
    tag = (field_number << 3) | wire_type
    return _encode_varint(tag) + data


def _encode_string(field_number: int, value: str) -> bytes:
    """Encode a string field (wire type 2 — length-delimited)."""
    encoded = value.encode("utf-8")
    return _encode_field(field_number, 2, _encode_varint(len(encoded)) + encoded)


def _encode_bytes_field(field_number: int, value: bytes) -> bytes:
    """Encode a bytes/embedded-message field (wire type 2)."""
    return _encode_field(field_number, 2, _encode_varint(len(value)) + value)


# ---------------------------------------------------------------------------
# Xray protobuf message builders
# ---------------------------------------------------------------------------

def _build_typed_message(type_url: str, value: bytes) -> bytes:
    """Build xray TypedMessage: { 1: type (string), 2: value (bytes) }."""
    return _encode_string(1, type_url) + _encode_bytes_field(2, value)


def _build_vless_account(vless_uuid: str) -> bytes:
    """Build xray.proxy.vless.Account: { 1: id (string) }."""
    return _encode_string(1, vless_uuid)


def _build_add_user_operation(vless_uuid: str, email: str) -> bytes:
    """Build AddUserOperation wrapping a protocol.User with a VLESS account.

    Wire layout:
        AddUserOperation  { 1: user (protocol.User) }
        protocol.User     { 2: email, 3: account (TypedMessage) }
        TypedMessage      { 1: "xray.proxy.vless.Account", 2: Account bytes }
    """
    account_bytes = _build_vless_account(vless_uuid)
    typed_account = _build_typed_message(
        "xray.proxy.vless.Account", account_bytes,
    )
    user_bytes = _encode_string(2, email) + _encode_bytes_field(3, typed_account)
    return _encode_bytes_field(1, user_bytes)


def _build_remove_user_operation(email: str) -> bytes:
    """Build RemoveUserOperation: { 1: email (string) }."""
    return _encode_string(1, email)


def _build_alter_inbound_request(
    tag: str,
    operation_type: str,
    operation_bytes: bytes,
) -> bytes:
    """Build AlterInboundRequest: { 1: tag, 2: operation (TypedMessage) }."""
    typed_op = _build_typed_message(operation_type, operation_bytes)
    return _encode_string(1, tag) + _encode_bytes_field(2, typed_op)


# ---------------------------------------------------------------------------
# gRPC transport
# ---------------------------------------------------------------------------

_ALTER_INBOUND_METHOD = "/xray.app.proxyman.command.HandlerService/AlterInbound"
_QUERY_STATS_METHOD = "/xray.app.stats.command.StatsService/QueryStats"

_DEFAULT_TIMEOUT: float = 5.0


async def _call_grpc(
    endpoint: str,
    method: str,
    request_bytes: bytes,
    timeout: float = _DEFAULT_TIMEOUT,
) -> bytes:
    """Send a unary gRPC call and return the raw response bytes."""
    async with grpc.aio.insecure_channel(endpoint) as channel:
        call = channel.unary_unary(
            method,
            request_serializer=lambda x: x,
            response_deserializer=lambda x: x,
        )
        return await call(request_bytes, timeout=timeout)


async def _call_alter_inbound(
    endpoint: str,
    request_bytes: bytes,
    timeout: float = _DEFAULT_TIMEOUT,
) -> None:
    """Send a single AlterInbound RPC to *endpoint*."""
    await _call_grpc(endpoint, _ALTER_INBOUND_METHOD, request_bytes, timeout)


async def _fan_out(
    endpoints: list[str],
    request_bytes: bytes,
    operation_desc: str,
) -> dict[str, bool]:
    """Call AlterInbound on every endpoint concurrently.

    Returns a mapping of ``{endpoint: success}``.
    Raises :class:`XrayClientError` only when **all** endpoints fail.
    """
    if not endpoints:
        logger.warning("No Xray gRPC endpoints configured")
        return {}

    async def _call_one(ep: str) -> tuple[str, bool, str]:
        try:
            await _call_alter_inbound(ep, request_bytes)
            return (ep, True, "")
        except Exception as exc:
            return (ep, False, str(exc))

    results_list = await asyncio.gather(*[_call_one(ep) for ep in endpoints])

    results: dict[str, bool] = {}
    failures: dict[str, str] = {}
    for ep, ok, err in results_list:
        results[ep] = ok
        if not ok:
            failures[ep] = err
            logger.warning("Xray %s failed on %s: %s", operation_desc, ep, err)

    if failures and not any(results.values()):
        raise XrayClientError(
            f"Xray {operation_desc} failed on ALL endpoints",
            failures,
        )

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def add_vless_client(
    endpoints: list[str],
    inbound_tag: str,
    vless_uuid: uuid.UUID,
    email: str,
) -> dict[str, bool]:
    """Add a VLESS client to *inbound_tag* on all Xray endpoints.

    Args:
        endpoints: ``"host:port"`` gRPC addresses (one per RU relay).
        inbound_tag: Xray inbound tag to modify (e.g. ``"vless-in"``).
        vless_uuid: The VLESS client UUID.
        email: Unique identifier for this client in Xray (used for stats
            and for :func:`remove_vless_client`).

    Returns:
        ``{endpoint: success}`` mapping.  Logs warnings for individual
        failures; raises :class:`XrayClientError` only when *all* fail.
    """
    op_bytes = _build_add_user_operation(str(vless_uuid), email)
    request = _build_alter_inbound_request(
        inbound_tag,
        "xray.app.proxyman.command.AddUserOperation",
        op_bytes,
    )
    return await _fan_out(endpoints, request, f"AddUser({email})")


async def remove_vless_client(
    endpoints: list[str],
    inbound_tag: str,
    email: str,
) -> dict[str, bool]:
    """Remove a VLESS client from *inbound_tag* on all Xray endpoints.

    Args:
        endpoints: ``"host:port"`` gRPC addresses.
        inbound_tag: Xray inbound tag.
        email: The client's email (must match the one used in
            :func:`add_vless_client`).

    Returns:
        ``{endpoint: success}`` mapping.
    """
    op_bytes = _build_remove_user_operation(email)
    request = _build_alter_inbound_request(
        inbound_tag,
        "xray.app.proxyman.command.RemoveUserOperation",
        op_bytes,
    )
    return await _fan_out(endpoints, request, f"RemoveUser({email})")


async def sync_vless_clients(
    endpoints: list[str],
    inbound_tag: str,
    clients: list[tuple[uuid.UUID, str]],
) -> None:
    """Ensure all *clients* exist on every endpoint (bulk idempotent sync).

    Xray silently accepts ``AddUser`` for already-existing UUIDs, so this
    is safe to call repeatedly.

    Args:
        clients: Sequence of ``(vless_uuid, email)`` tuples.
    """
    if not clients:
        return

    for vless_uuid, email in clients:
        try:
            await add_vless_client(endpoints, inbound_tag, vless_uuid, email)
        except XrayClientError:
            logger.warning(
                "Failed to sync client %s, will retry next cycle", email,
            )


# ---------------------------------------------------------------------------
# Protobuf decoding helpers (for parsing Xray Stats API responses)
# ---------------------------------------------------------------------------

def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode an unsigned varint at *pos*, return ``(value, new_pos)``."""
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            return result, pos
        shift += 7
    raise ValueError("truncated varint")


def _iter_proto_fields(
    data: bytes,
) -> list[tuple[int, int, bytes | int]]:
    """Parse raw protobuf bytes into ``(field_number, wire_type, value)`` tuples.

    wire_type 0 → value is ``int`` (varint)
    wire_type 2 → value is ``bytes`` (length-delimited)
    """
    fields: list[tuple[int, int, bytes | int]] = []
    pos = 0
    while pos < len(data):
        tag, pos = _decode_varint(data, pos)
        fn = tag >> 3
        wt = tag & 0x07
        if wt == 0:
            val, pos = _decode_varint(data, pos)
            fields.append((fn, wt, val))
        elif wt == 2:
            length, pos = _decode_varint(data, pos)
            fields.append((fn, wt, data[pos : pos + length]))
            pos += length
        elif wt == 1:  # 64-bit
            pos += 8
        elif wt == 5:  # 32-bit
            pos += 4
        else:
            break
    return fields


def _parse_query_stats_response(data: bytes) -> dict[str, int]:
    """Decode ``QueryStatsResponse`` → ``{stat_name: value}``.

    Message layout::

        QueryStatsResponse { repeated Stat stat = 1; }
        Stat { string name = 1; int64 value = 2; }
    """
    result: dict[str, int] = {}
    for fn, wt, val in _iter_proto_fields(data):
        if fn == 1 and wt == 2 and isinstance(val, bytes):
            name = ""
            stat_value = 0
            for sfn, swt, sval in _iter_proto_fields(val):
                if sfn == 1 and swt == 2 and isinstance(sval, bytes):
                    name = sval.decode("utf-8")
                elif sfn == 2 and swt == 0 and isinstance(sval, int):
                    stat_value = sval
            if name:
                result[name] = stat_value
    return result


# ---------------------------------------------------------------------------
# Stats API
# ---------------------------------------------------------------------------

async def query_online_stats(
    endpoint: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, int]:
    """Query online IP counts from a single Xray endpoint.

    Requires ``statsUserOnline: true`` in the Xray policy config.

    Returns ``{stat_name: ip_count}`` for stats matching ``online``,
    e.g. ``{"user>>>sub_12345_a1b2c3d4@rhino>>>online": 2}``.
    """
    request = _encode_string(1, "online")  # QueryStatsRequest.pattern
    response = await _call_grpc(
        endpoint, _QUERY_STATS_METHOD, request, timeout,
    )
    return _parse_query_stats_response(response)
