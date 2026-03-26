from __future__ import annotations

from urllib.parse import quote


def build_vless_link(
    vless_uuid: str,
    server_address: str,
    server_port: int,
    reality_public_key: str,
    sni_domain: str,
    short_id: str,
    server_name: str,
) -> str:
    # Use path=/ (not %2F) — some clients mishandle percent-encoded slash in the path param.
    params = (
        f"encryption=none"
        f"&security=reality"
        f"&pbk={quote(reality_public_key)}"
        f"&fp=chrome"
        f"&type=xhttp"
        f"&path={quote('/', safe='/')}"
        f"&mode=packet-up"
        f"&host={quote(sni_domain)}"
        f"&sni={quote(sni_domain)}"
    )
    if short_id:
        params += f"&sid={quote(short_id)}"
    return f"vless://{vless_uuid}@{server_address}:{server_port}?{params}#{quote(server_name)}"
