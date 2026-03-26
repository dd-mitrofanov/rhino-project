# Rhino — Fault-Tolerant Two-Level VPN Bypass Channel

Automated infrastructure for a censorship-resistant VPN setup using **Xray-core** (VLESS + Reality, XHTTP packet-up mode), deployed via **Ansible + Docker**.

The system comprises **2 RU relay servers** (Yandex.Cloud / VK Cloud) and **2 foreign exit servers** (Netherlands / Germany). Russian traffic is split on each RU relay: inbound **sniffing** feeds domain rules (`geosite:category-ru`), **geoip:ru** covers IP-only destinations; everything else exits through EU nodes via the **balancer** (default strategy **`roundRobin`**, configurable) with **observatory** probes and automatic failover.

**Documentation:** operator guides live in [docs/](docs/01-arch-overview.md) (numbered topics: architecture, first deploy, RU/foreign configs, monitoring, bot/subscriptions, adding servers).

## Architecture

```
Client
    │
    ├─► connects to one of 2 RU Relay Servers
    │   (VLESS + Reality, XHTTP packet-up, SNI = whitelisted domain)
    ▼
┌──────────────────────────────────────┐
│  RU Relay Server (×2)                │  Yandex.Cloud / VK Cloud
│  sniff + geosite:ru / geoip:ru→dir   │
│  balancer + observatory              │
│  observatory: 1min probe             │
└───────────┬──────────────────────────┘
            │  VLESS + Reality outbound
            ▼
┌──────────────────────────────────────┐
│  Foreign Exit Server (×2)            │  Netherlands / Germany
│  outbound: freedom                   │
└───────────┬──────────────────────────┘
            ▼
        Internet
```

**Key decisions:**


| Aspect     | Choice                                                                                                |
| ---------- | ----------------------------------------------------------------------------------------------------- |
| Transport  | VLESS + Reality, XHTTP in packet-up mode                                                              |
| Balancing  | Xray observatory + configurable balancer strategy (default `roundRobin` in `configs/production/vars/xray.yml`) |
| Routing    | Sniffing (TLS/HTTP/QUIC) + `geosite:category-ru` / `geoip:ru` → direct; everything else → eu-balancer |
| Deployment | Ansible + Docker Compose                                                                              |
| Secrets    | Ansible Vault                                                                                         |


## Prerequisites

- **Ansible** >= 2.15 (`pip install ansible`)
- **Python** >= 3.10
- **Docker** and **Docker Compose** installed on all target servers (automated by the `docker` role)
- **ansible-vault** password (stored locally in `.vault_pass`, never committed)
- **ansible-lint** (optional, for `make lint`)
- **SSH access** to all 4 servers with key-based auth (see [SSH from your laptop](#ssh-from-your-laptop))

Install required Ansible collections:

```bash
ansible-galaxy collection install -r requirements.yml
```

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> && cd rhino-project

# 2. Create the vault password file (never committed)
echo 'your-vault-password' > .vault_pass
chmod 600 .vault_pass

# 3. Generate Reality key pairs and UUIDs
make gen-keys

# 4. Fill in the vault with generated keys
make edit-secrets

# 5. Configure inventory and secrets — IPs and keys in the vault;
#    shared vars in inventories/production/group_vars/all/common.yml

# 6. Deploy (pick one)
make deploy-vpn          # Xray only — common + foreign exits + RU relays
# or, for VPN + subscription API + Telegram stack in one go:
make deploy-full
```

## Directory Structure

```
.
├── ansible.cfg              # Ansible configuration
├── Makefile                 # Common operations (see docs/02-first-deploy.md and Makefile)
├── README.md                # This file
├── requirements.yml         # Ansible Galaxy dependencies
├── docs/                    # Architecture and operations (numbered guides)
│
├── inventories/
│   ├── production/          # Production inventory
│   │   ├── hosts.yml       # Server inventory (IPs, groups)
│   │   └── group_vars/     # Per-group variables (all/, ru_relays.yml, foreign_exits.yml)
│   └── test/               # Test inventory (deploy-test-server)
│       ├── hosts.yml
│       └── group_vars/
│
├── configs/
│   ├── production/          # Production configs
│   │   ├── secrets/         # Encrypted vault (Reality keys, UUIDs, API tokens)
│   │   ├── templates/       # Jinja2 templates (Xray, Docker Compose, Caddy)
│   │   └── vars/            # Non-secret variables (SNI, servers, subscription API hostnames)
│   └── test/                # Test configs (deploy-test-server)
│       ├── secrets/
│       ├── templates/
│       └── vars/
│
├── playbooks/
│   ├── site.yml             # VPN only: common + foreign + RU (imported by deploy-full)
│   ├── deploy-full.yml      # site + subscription external + Telegram stack
│   ├── setup-common.yml
│   ├── deploy-ru-relay.yml
│   ├── deploy-foreign-exit.yml
│   ├── deploy-subscription-external.yml   # External subscription API (all RU relays)
│   ├── deploy-telegram-bot.yml
│   ├── deploy-test-server.yml             # Test Xray server (ANSIBLE_CONFIG=ansible-test.cfg)
│   └── update-geodata.yml
│
├── roles/
│   ├── docker/
│   ├── hardening/
│   ├── xray/
│   ├── subscription-api/    # Proxy stack on RU relays (forwards to bot)
│   └── telegram-bot/        # Bot + DB + built-in subscription HTTP on nl-ams-1
│
├── bot/                     # Telegram bot application
├── subscription-api/        # FastAPI proxy (forwards GET /{token} to bot)
└── scripts/
    ├── generate-keys.sh
    ├── encrypt-secrets.sh
    └── decrypt-secrets.sh
```

## SSH from your laptop

Inventory sets `**ansible_user: deploy**` and `**ansible_ssh_private_key_file**` to `$HOME/.ssh/id_rhino` in `inventories/production/group_vars/all/common.yml`. Ansible connects as that user to the address in `ansible_host` (from the vault unless you change it).

**Override the key:** use `IdentityFile` in `~/.ssh/config` (per-host), edit `ansible_ssh_private_key_file` in `common.yml`, or temporarily:

```bash
export ANSIBLE_PRIVATE_KEY_FILE="$HOME/.ssh/other_key"
```

`**~/.ssh/config` aliases:** you can give each server a `Host` name that matches the inventory name (`ru-msk-1`, `nl-ams-1`, …). Then remove the `ansible_host: "{{ vault_…_ip }}"` line for that host (or replace it with the same name explicitly). Ansible will open SSH to `ru-msk-1`, and OpenSSH will apply `HostName`, `User`, and `IdentityFile` from your config. **Vault IPs stay in `configs/production/secrets/vault.yml`** for Xray and `configs/production/vars/servers.yml`; only the Ansible connection target changes.

## Secrets Management

All secrets (Reality private keys, UUIDs, sensitive configuration) are stored in `configs/production/secrets/`, encrypted with **ansible-vault**. The encryption password lives in `.vault_pass` which is excluded from Git.

**First-time setup:** `configs/production/secrets/vault.yml` is gitignored. Copy the example and fill all values (Xray keys, subscription API, Telegram bot, Grafana), then encrypt:
```bash
cp configs/production/secrets/vault.yml.example configs/production/secrets/vault.yml
# Edit: IPs, keys, subscription_api_*, telegram_bot_*, vault_grafana_*, etc.
ansible-vault encrypt configs/production/secrets/vault.yml   # or use make encrypt after first edit
```

### Workflow

```bash
# Edit secrets interactively (decrypts → opens $EDITOR → re-encrypts)
make edit-secrets

# Manually encrypt after editing
make encrypt

# Decrypt for inspection (re-encrypt when done!)
make decrypt
```

### Rules

1. **Never** commit `.vault_pass` — it's in `.gitignore`.
2. `configs/production/secrets/vault.yml` is **gitignored** — keep it only on operator machines; do not commit plaintext secrets.
3. Share the vault password out-of-band (password manager, secure messaging).
4. Rotate keys periodically by running `make gen-keys`, updating the vault, and re-deploying.
5. `**vault_subscription_api_token`** — shared secret used by external subscription proxies to call the bot; set in the vault (see `[configs/production/secrets/vault.yml.example](configs/production/secrets/vault.yml.example)`).

## Subscriptions and clients

Per-user subscription URLs return a **plain-text list** of `vless://` links built from PostgreSQL and `configs/production/vars/servers.yml`. Users can paste **one** URL into clients such as [Happ](https://www.happ.su/). Split routing for Russian sites is enforced on **RU Xray** (`geosite:category-ru` → direct).

**Ports:** Xray uses host networking on **443**. The public subscription endpoint uses **HTTPS on `subscription_api_port`** (set in `configs/production/secrets/vault.yml` alongside other secrets, default **8443**), with **port 80** open on the RU host for Let’s Encrypt. Configure `**subscription_api_domain`**, `**subscription_api_acme_email**`, and DNS before deploying the external API. For fault tolerance, add multiple A records for `subscription_api_domain` (one per RU relay). See [docs/06-bot-and-subs.md](docs/06-bot-and-subs.md).

Treat each user’s subscription URL as a **secret** (path includes their token). After changing RU relay parameters used in generated links, run `make deploy-telegram` so the bot picks up the new server list. See [docs/06-bot-and-subs.md](docs/06-bot-and-subs.md).

### Telegram bot commands

Slash commands must be **Latin** (Telegram Bot API). The bot sets a command menu with Russian descriptions. Users: `/instructions` — список инструкций с фото. Admins: `/instruction_add`, `/instruction_edit`, `/instruction_delete`. Runtime env: `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `DATABASE_URL` (see `bot/app/config.py`).

## Deployment

### VPN only

`site.yml` deploys common setup, foreign exits, and RU relays — **not** the Telegram bot or subscription containers.

```bash
make deploy-vpn
```

### Everything (VPN + apps)

```bash
make deploy-full
```

### Targeted deployment

```bash
make setup                      # Hardening + Docker (as needed)
make deploy-ru                  # RU relays only
make deploy-foreign             # Foreign exits only
make geodata                    # geosite/geoip on relays
make deploy-telegram            # Bot + DB + built-in subscription HTTP (nl-ams-1)
make deploy-subscription-external   # Public subscription API + Caddy (all RU relays)
```

### Dry Run

Preview changes without applying:

```bash
make check
```

### Linting

```bash
make lint
```

## Updating configuration

1. Modify variables in `inventories/production/group_vars/` or `configs/production/vars/`.
2. If changing secrets, run `make edit-secrets`.
3. Re-deploy what changed (see Makefile and [docs/06-bot-and-subs.md](docs/06-bot-and-subs.md)):

```bash
make deploy-ru                  # RU Xray / balancer / routing
make deploy-foreign             # Foreign exits
make deploy-subscription-external   # TLS / Caddy / proxy on all RU relays
make deploy-telegram            # Bot code or full stack refresh
make deploy-vpn                 # All Xray hosts when unsure
```

Ansible is idempotent — re-running a playbook applies only the delta.

### RU relay: split routing (sniffing / geoip) updates

After pulling changes that affect `configs/production/templates/ru-relay.json.j2`, refresh **all** RU relays so they get the new `config.json` and container definition:

```bash
make deploy-ru
```

Optional: refresh `geosite.dat` / `geoip.dat` on relays (same playbooks as deploy use these paths):

```bash
make geodata
```

`make geodata` restarts Xray only when the downloaded files change.

## Troubleshooting

### SSH connection refused / Permission denied (publickey)

- Confirm `inventories/production/group_vars/all/common.yml` is present (with `all/` as a directory, a sibling `group_vars/all.yml` file is ignored by Ansible).
- Ensure the `**deploy` user** exists on the server and your public key is in `deploy`’s `authorized_keys`.
- If you use several keys, set `IdentityFile` in `~/.ssh/config`, `ansible_ssh_private_key_file` in `common.yml`, or `ANSIBLE_PRIVATE_KEY_FILE`. See [SSH from your laptop](#ssh-from-your-laptop).

### Vault password error

- Confirm `.vault_pass` exists and contains the correct password.
- File must have `chmod 600` permissions.

### Docker not starting on target

- Run `make setup` first to install Docker via the `docker` role.
- Check `systemctl status docker` on the target server.

### Xray container not healthy

- SSH into the server and check logs: `docker logs xray`.
- Validate the config: `docker exec xray xray run -test -c /etc/xray/config.json`.
- Ensure Reality keys in the vault match between RU and foreign servers.

### Observatory reports all foreign nodes down

- Verify foreign servers are running and accessible from RU servers.
- Check firewall rules on foreign servers.
- Test connectivity: `curl -x "" https://<foreign-ip>:<port>` from an RU server.

### Geodata update fails

- Run `make geodata` to pull the latest `geosite.dat` / `geoip.dat`.
- Check that the download URLs in the playbook are still valid.

## Adding a New Server

When the base topology (**ru-msk-1**, **ru-msk-2**, **nl-ams-1**, **de-fra-1**) is already working, extending it follows the same pattern: inventory host + vault secrets + `configs/production/vars/servers.yml` (for foreign exits only) + deploy in the right order.

**Step-by-step:** [docs/07-add-ru-relay.md](docs/07-add-ru-relay.md), [docs/08-add-foreign-exit.md](docs/08-add-foreign-exit.md)

### Adding a new RU relay server

1. Pick a tag, e.g. `ru-ekb-1` (hyphens; letters, numbers, hyphens only — they become vault key suffixes).
2. Provision the VM, note its public IP.
3. `**inventories/production/hosts.yml`** — under `ru_relays.hosts`, add a block mirroring existing entries: `ansible_host: "{{ vault_<tag_underscores>_ip }}"`, `server_tag`, `server_location`.
4. `**configs/production/secrets/vault.yml**` — add `vault_<tag_underscores>_ip` and a full Reality key pair (`_reality_private_key` / `_reality_public_key`) for that host. The **client-facing** UUID stays `vault_client_uuid` (same as other RU relays).
5. `**configs/production/vars/servers.yml`** — add the same tag under `ru_servers` with `address: "{{ vault_<tag_underscores>_ip }}"`, `port`, `location` (used for subscriptions / docs, not for Xray balancing).
6. `**scripts/generate-keys.sh**` — append the new tag to the `for server in ...` loops that generate keys (or run `docker run --rm ghcr.io/xtls/xray-core:latest x25519` once for this host).
7. Deploy: `ansible-playbook playbooks/setup-common.yml --limit <tag>` then `make deploy-ru` (or `--limit <tag>`).
8. Refresh generated subscription links: `make deploy-telegram` so the bot picks up the new RU (same `vault_client_uuid` as other RU relays; per-node Reality public key and address).

### Adding a new foreign exit server

1. Pick a tag, e.g. `nl-ams-2` or `de-fra-2`.
2. Provision the VM, note its public IP.
3. Generate a **new** Reality key pair and a **new** link UUID for this host (`docker run --rm ghcr.io/xtls/xray-core:latest x25519` and `docker run --rm ghcr.io/xtls/xray-core:latest uuid`, or extend `generate-keys.sh` temporarily).
4. `**configs/production/secrets/vault.yml`** — add IP, Reality private/public keys, and `vault_<tag_underscores>_uuid` (RU outbounds use this UUID to reach this exit).
5. `**inventories/production/hosts.yml`** — add host under `foreign_exits` with `ansible_host` and `server_tag`.
6. `**configs/production/vars/servers.yml`** — append one `foreign_servers` list entry: `tag`, `address: "{{ vault_..._ip }}"`, `port`, `location`. Order defines balancer membership; **first** entry is also `fallbackTag` in the rendered Xray config — put your preferred default exit first.
7. Deploy the new exit first: `ansible-playbook playbooks/setup-common.yml --limit <tag>` then `ansible-playbook playbooks/deploy-foreign-exit.yml --limit <tag>`.
8. **Re-deploy all RU relays** so they pick up the new outbound + observatory selector: `make deploy-ru`.
9. Within about a minute, observatory will include the new node in `leastPing` selection.

### If you rename servers (migration note)

Vault variable names are derived from the tag: `nl-ams-1` → `vault_nl_ams_1_ip`, etc. After renaming, merge or re-key values in `vault.yml` and redeploy every host whose keys or topology changed.