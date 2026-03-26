# First-time deployment

End-to-end steps to deploy production from a clean checkout. Adjust hostnames, domains, and IPs to your environment.

---

## 1. Prerequisites (operator machine)

- **Ansible** ≥ 2.15 (`pip install ansible`)
- **Python** ≥ 3.10
- **SSH** key-based access to all target servers as the Ansible user (default: `deploy` — see `inventories/production/group_vars/all/common.yml`)
- **ansible-vault** (included with Ansible) for encrypting `configs/production/secrets/vault.yml`
- Optional: **ansible-lint** for `make lint`

Install collections:

```bash
ansible-galaxy collection install -r requirements.yml
```

---

## 2. Clone and vault password

```bash
git clone <repository-url> && cd rhino-project
echo 'your-ansible-vault-password' > .vault_pass
chmod 600 .vault_pass
```

Never commit `.vault_pass`.

---

## 3. Secrets and keys

1. Copy the vault example and fill in placeholders:

   ```bash
   cp configs/production/secrets/vault.yml.example configs/production/secrets/vault.yml
   ```

2. Generate Xray-related keys and UUIDs:

   ```bash
   make gen-keys
   ```

3. Merge generated values into `vault.yml` (IPs, Reality key pairs per host, `vault_client_uuid`, per-foreign `vault_<tag>_uuid`, `vault_subscription_api_token`, Telegram and subscription API fields, Grafana vars if you use monitoring).

4. Encrypt the vault when satisfied:

   ```bash
   ansible-vault encrypt configs/production/secrets/vault.yml
   ```

   Later edits: `make edit-secrets`.

---

## 4. SSH and inventory

- **`inventories/production/group_vars/all/common.yml`**: `ansible_user`, `ansible_ssh_private_key_file` (default `$HOME/.ssh/id_rhino`). Ensure that user exists on servers and your public key is in `authorized_keys`.
- **`inventories/production/hosts.yml`**: hosts reference Vault variables for IPs (e.g. `{{ vault_ru_msk_1_ip }}`). Keep Vault and inventory tags consistent (`ru-msk-1` → `vault_ru_msk_1_ip`).

You can override the key for one run: `export ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/other_key`.

---

## 5. Non-secret configuration

- **`configs/production/vars/xray.yml`**: SNI allowlist, shortIds, `balancer_strategy`, observatory URLs, optional `ru_relay_vk_max_*` rules.
- **`configs/production/vars/servers.yml`**: ordered lists `ru_servers` and `foreign_servers` (tags must match inventory and Vault). **First** `foreign_servers` entry is the balancer **fallback**.
- **`configs/production/vars/monitoring.yml`**: required for `make deploy-monitoring` (images, ports, paths). A baseline ships in-repo; adjust as needed.

---

## 6. DNS (before subscription + monitoring)

| Purpose | Record |
|---------|--------|
| **Subscription API** | `subscription_api_domain` (from Vault): **A** records pointing to **each RU relay** IP (multi-A for failover). Short TTL (e.g. 300–600 s) recommended. |
| **Grafana** (if using monitoring) | `vault_grafana_domain` → **A** to `de-fra-1` (or whichever host runs the monitoring playbook). Needed before Let’s Encrypt via Caddy. |

HTTP-01 for subscription TLS requires **port 80** reachable on RU relays for the ACME challenge (see subscription role).

---

## 7. Deploy

**Vault link** (Makefile does this automatically for production targets):

```bash
make ensure-vault-link   # optional; ln -sf ... group_vars/all/vault.yml
```

Choose one:

| Goal | Command |
|------|---------|
| **VPN only** (Xray on all relays and exits, common hardening) | `make deploy-vpn` |
| **Full stack** (VPN + external subscription on all RU relays + Telegram bot on `nl-ams-1`) | `make deploy-full` |

Dry run:

```bash
make check
```

---

## 8. Monitoring (optional, after VPN)

1. Set Grafana admin user, domain, and password in Vault (`vault_grafana_*`).
2. Ensure DNS for `vault_grafana_domain` points to the monitoring host (`de-fra-1` in the default inventory).
3. Run:

   ```bash
   make deploy-vpn    # enables Stats API + exporter if not already applied
   make deploy-monitoring
   ```

Grafana is exposed on **`grafana_https_port`** (default **8443**) because Xray typically uses 443 on that host. Open `https://<vault_grafana_domain>:8443`.

Details: [05-monitoring.md](05-monitoring.md).

---

## 9. Verification checklist

- `make check` passes (or targeted playbooks run without errors).
- On a RU relay: `docker ps` shows Xray (and subscription stack if deployed).
- On `nl-ams-1`: bot and DB containers up if you ran `deploy-full` / `deploy-telegram`.
- Client: import subscription URL; confirm handshake to RU relay and browsing.

---

## 10. Optional: isolated test server

For transport smoke tests without touching production inventory, use the test playbook and `configs/test/`:

```bash
make deploy-test-server
```

Uses `ANSIBLE_CONFIG=ansible-test.cfg`. Does **not** import production `site.yml`.

---

## See also

- Makefile targets: summarized in [06-bot-and-subs.md](06-bot-and-subs.md) and [05-monitoring.md](05-monitoring.md).
- Adding hosts after the base four: [07-add-ru-relay.md](07-add-ru-relay.md), [08-add-foreign-exit.md](08-add-foreign-exit.md).
