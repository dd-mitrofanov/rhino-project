"""Build hysteria2:// subscription links (Hysteria 2 userpass)."""
from __future__ import annotations

from urllib.parse import quote


def build_hysteria2_link(
    username: str,
    password: str,
    server_address: str,
    server_port: int,
    sni: str,
    server_name: str,
) -> str:
    """Userinfo is username:password (percent-encoded per component)."""
    ui = f"{quote(username, safe='')}:{quote(password, safe='')}"
    params = f"insecure=1&sni={quote(sni)}"
    return (
        f"hysteria2://{ui}@{server_address}:{server_port}?{params}"
        f"#{quote(server_name)}"
    )
