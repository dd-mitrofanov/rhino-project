#!/usr/bin/env python3
"""HTTP POST /sync — replace auth.userpass in server.yaml and restart Hysteria."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

TOKEN = os.environ["HYSTERIA_SYNC_TOKEN"]
CONFIG_PATH = Path(os.environ["HYSTERIA_SERVER_CONFIG_PATH"])
COMPOSE_DIR = Path(os.environ["HYSTERIA_COMPOSE_DIR"])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _unauthorized(self) -> None:
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"detail":"Unauthorized"}')

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/sync":
            self.send_error(404)
            return
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {TOKEN}":
            self._unauthorized()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400)
            return
        users_in = data.get("users")
        if not isinstance(users_in, list):
            self.send_error(400)
            return
        userpass: dict[str, str] = {}
        for item in users_in:
            if not isinstance(item, dict):
                continue
            user = item.get("user")
            password = item.get("password")
            if isinstance(user, str) and isinstance(password, str) and user:
                userpass[user] = password
        if not CONFIG_PATH.is_file():
            self.send_error(500)
            return
        with CONFIG_PATH.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if not isinstance(cfg, dict):
            self.send_error(500)
            return
        cfg.setdefault("auth", {})
        cfg["auth"]["type"] = "userpass"
        cfg["auth"]["userpass"] = userpass
        tmp = CONFIG_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
        tmp.replace(CONFIG_PATH)
        os.chmod(CONFIG_PATH, 0o644)
        try:
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(COMPOSE_DIR / "docker-compose.yml"),
                    "restart",
                    "hysteria",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            sys.stderr.write("docker compose restart failed: %s\n" % (e.stderr or e,))
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')


def main() -> None:
    host = os.environ.get("HYSTERIA_SYNC_BIND", "0.0.0.0")
    port = int(os.environ["HYSTERIA_SYNC_PORT"])
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
