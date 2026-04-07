"""Subscription plaintext assembly: four-group order, shuffle, deterministic names."""
from __future__ import annotations

import hashlib
import random

from app.hysteria_uri import build_hysteria2_link
from app.vless import build_vless_link


def _is_whitelist(server: dict) -> bool:
    """Treat missing, null, or false as non-whitelist; only explicit true counts."""
    return server.get("is_whitelist") is True


def _subscription_display_number(
    subscription_token: str,
    tag: str,
    protocol_kind: str,
    is_whitelist: bool,
) -> str:
    """Stable 1–9999 label per (token, tag, protocol, whitelist bucket)."""
    wf = "1" if is_whitelist else "0"
    material = f"{subscription_token}|{tag}|{protocol_kind}|{wf}".encode("utf-8")
    n = int(hashlib.sha256(material).hexdigest()[:16], 16) % 9999 + 1
    return str(n)


def _subscription_server_name(
    subscription_token: str,
    tag: str,
    protocol_kind: str,
    is_whitelist: bool,
) -> str:
    n = _subscription_display_number(
        subscription_token, tag, protocol_kind, is_whitelist
    )
    if protocol_kind == "xhttp":
        return f"{n} XHTTP WL" if is_whitelist else f"{n} XHTTP"
    if protocol_kind == "hysteria2":
        return f"{n} Hysteria2 WL" if is_whitelist else f"{n} Hysteria2"
    raise ValueError(f"unknown protocol_kind: {protocol_kind!r}")


def build_subscription_link_lines(
    *,
    subscription_token: str,
    vless_uuid: str,
    hysteria_password: str,
    servers: list[dict],
) -> list[str]:
    """Four-group global order; shuffle a copy of each group; emit vless then hysteria2 per spec."""
    non_wl = [s for s in servers if not _is_whitelist(s)]
    wl = [s for s in servers if _is_whitelist(s)]
    groups: list[tuple[str, bool, list[dict]]] = [
        ("xhttp", False, non_wl),
        ("xhttp", True, wl),
        ("hysteria2", False, non_wl),
        ("hysteria2", True, wl),
    ]
    links: list[str] = []
    for protocol_kind, wl_flag, group_servers in groups:
        shuffled = list(group_servers)
        random.shuffle(shuffled)
        for server in shuffled:
            name = _subscription_server_name(
                subscription_token, server["tag"], protocol_kind, wl_flag
            )
            if protocol_kind == "xhttp":
                links.append(
                    build_vless_link(
                        vless_uuid=vless_uuid,
                        server_address=server["address"],
                        server_port=server["port"],
                        reality_public_key=server["reality_public_key"],
                        sni_domain=server["sni_domain"],
                        short_id=server.get("short_id", ""),
                        server_name=name,
                    )
                )
            else:
                links.append(
                    build_hysteria2_link(
                        username=subscription_token,
                        password=hysteria_password,
                        server_address=server["address"],
                        server_port=int(server["hysteria_port"]),
                        sni=str(server["hysteria_sni"]),
                        server_name=name,
                    )
                )
    return links
