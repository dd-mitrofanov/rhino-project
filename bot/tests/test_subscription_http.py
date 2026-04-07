"""Tests for subscription grouping, naming, and link assembly."""
from __future__ import annotations

from unittest.mock import patch
from urllib.parse import unquote

import pytest

from app.subscription_format import (
    _is_whitelist,
    _subscription_display_number,
    _subscription_server_name,
    build_subscription_link_lines,
)


def test_is_whitelist_defaults() -> None:
    assert _is_whitelist({}) is False
    assert _is_whitelist({"is_whitelist": None}) is False
    assert _is_whitelist({"is_whitelist": False}) is False
    assert _is_whitelist({"is_whitelist": True}) is True


def test_subscription_display_number_range_and_stable() -> None:
    n = _subscription_display_number("tok", "ru-1", "xhttp", False)
    assert 1 <= int(n) <= 9999
    assert n == _subscription_display_number("tok", "ru-1", "xhttp", False)
    assert n != _subscription_display_number("tok", "ru-1", "xhttp", True)
    assert n != _subscription_display_number("tok", "ru-1", "hysteria2", False)


@pytest.mark.parametrize(
    ("protocol_kind", "wl", "suffix"),
    [
        ("xhttp", False, " XHTTP"),
        ("xhttp", True, " XHTTP WL"),
        ("hysteria2", False, " Hysteria2"),
        ("hysteria2", True, " Hysteria2 WL"),
    ],
)
def test_subscription_server_name_patterns(
    protocol_kind: str, wl: bool, suffix: str
) -> None:
    name = _subscription_server_name("t", "tag", protocol_kind, wl)
    assert name.endswith(suffix)
    num = name[: -len(suffix)]
    assert num.isdigit()
    assert 1 <= int(num) <= 9999


def _server(tag: str, *, wl: bool | None) -> dict:
    d = {
        "tag": tag,
        "address": "192.0.2.1",
        "port": 443,
        "reality_public_key": "abc",
        "sni_domain": "example.com",
        "short_id": "",
        "hysteria_port": 8443,
        "hysteria_sni": "example.com",
    }
    if wl is not None:
        d["is_whitelist"] = wl
    return d


@patch("app.subscription_format.random.shuffle", lambda x: None)
def test_build_subscription_lines_segment_order_and_no_legacy_names() -> None:
    servers = [
        _server("b", wl=False),
        _server("a", wl=True),
        _server("z", wl=None),
    ]
    lines = build_subscription_link_lines(
        subscription_token="subtok",
        vless_uuid="550e8400-e29b-41d4-a716-446655440000",
        hysteria_password="pw",
        servers=servers,
    )
    assert len(lines) == 6

    def frag(line: str) -> str:
        return unquote(line.split("#", 1)[1])

    assert frag(lines[0]).endswith(" XHTTP")
    assert frag(lines[1]).endswith(" XHTTP")
    assert frag(lines[2]).endswith(" XHTTP WL")
    assert frag(lines[3]).endswith(" Hysteria2")
    assert frag(lines[4]).endswith(" Hysteria2")
    assert frag(lines[5]).endswith(" Hysteria2 WL")

    joined = "\n".join(lines)
    assert "-xhttp" not in joined
    assert "-hysteria-2" not in joined


def test_shuffle_receives_copy_not_original_partition() -> None:
    """random.shuffle must run on a copy so partition lists are not mutated."""
    servers = [_server("only", wl=False)]
    seen: list[int] = []

    def capture_shuffle(seq: list) -> None:
        seen.append(id(seq))

    with patch("app.subscription_format.random.shuffle", capture_shuffle):
        build_subscription_link_lines(
            subscription_token="t",
            vless_uuid="550e8400-e29b-41d4-a716-446655440000",
            hysteria_password="p",
            servers=servers,
        )

    assert len(seen) == 4
    assert id(servers) not in seen
