# [04] Hysteria2 server on RU: Docker, config, upstream to Xray SOCKS

## Description

Run the **official Hysteria2** server in Docker on each **RU relay**, with:

- **UDP** listen on `0.0.0.0:hysteria_listen_port` (host mode or published UDP port mapping — prefer **host network** or explicit UDP publish; match what `roles/xray/tasks/docker.yml` does for consistency).
- **TLS** using the self-signed cert from task **02**.
- **Upstream** pointing to **Xray SOCKS** at `127.0.0.1:xray_socks_listen_port` (Hysteria v2 “TCP” / SOCKS outbound — exact stanza per current Hysteria server config schema).
- **Auth** mode supporting **per-user** credentials (e.g. `auth: type: userpass` with `users` list **or** external auth — **userpass + file** is simplest for Ansible/bot to rewrite).

## Goal

Decrypt Hysteria2 client traffic on UDP and forward plain traffic into Xray’s existing policy engine via loopback SOCKS.

## Technical details

### Image

- **Primary recommendation:** `ghcr.io/apernet/hysteria` with pinned tag (verify on [GitHub releases](https://github.com/apernet/hysteria)).
- Alternative documented in many guides: `tobyxdd/hysteria` — pin by digest in production.

### Configuration file

- Render from Jinja2 template in `configs/production/templates/` e.g. `hysteria-server.yaml.j2`.
- Include:
  - `listen` UDP address/port
  - `tls` cert/key paths (mounted read-only)
  - `auth` — user/password list **loaded from a separate file** (e.g. `auth.yaml` or hysteria-supported password file) that task **05** can overwrite atomically
  - **Outbound / proxy** section wiring to local SOCKS — follow upstream Hysteria v2 “forward to socks5” documentation

### Docker

- Either extend `roles/xray/tasks/docker.yml` pattern with a **second** container, or new `roles/hysteria/tasks/docker.yml` included from `deploy-ru-relay.yml`.
- Volumes: TLS dir, auth file dir, optional logs.
- `restart` policy: `unless-stopped`.
- Health: optional `hc` or script checking UDP port process.

### Files to touch

- `playbooks/deploy-ru-relay.yml` — include hysteria role if split
- `roles/hysteria/` (new) or `roles/xray/tasks/hysteria.yml`
- `configs/production/templates/hysteria-server.yaml.j2` (name as chosen)
- `roles/xray/tasks/docker.yml` — **only if** co-locating containers in same role; avoid breaking existing Xray container

### Interaction with task 05

- Hysteria must **reload** or **restart** when the auth file changes; prefer **SIGHUP** if supported, else `docker restart hysteria` — document chosen behavior in **05**.

## Dependencies

- **02** — ports, TLS paths, image vars
- **03** — SOCKS port live on loopback

## Usage example (user story)

- As a client, I connect with Hysteria2 app using `hysteria2://` from subscription; server accepts my password and traffic exits via foreign balancer through Xray.

## Acceptance criteria

- It must be true that **no** Hysteria container listens for **client** traffic on TCP 443 (that remains Xray `vless-in`).
- It must be true that Hysteria **only** forwards to `127.0.0.1` (not to foreign hosts directly).
- After `deploy-ru-relay`, both `xray` and `hysteria` containers are running; UDP port is listening.
- Config templates are **idempotent** on re-run.
