# Adding a Russian relay server

The default inventory uses two RU relays (`ru-msk-1`, `ru-msk-2`) and two foreign exits. This procedure adds another **RU** host without changing the two-tier design: balancing and observatory stay on RU relays; foreign exits stay as defined in `foreign_servers`.

---

## 1. How the pieces connect

| Artifact | Purpose |
|----------|---------|
| `inventories/production/hosts.yml` | New host under `ru_relays.hosts` with `ansible_host`, `server_tag`, `server_location` |
| `configs/production/secrets/vault.yml` | IP, Reality **private/public** keys for this host; **`vault_client_uuid` unchanged** (shared across RU inbounds) |
| `configs/production/vars/servers.yml` | New row under `ru_servers` with same `tag` as inventory |
| `scripts/generate-keys.sh` | Extend `for server in …` loops if you use the script for bulk key generation |

Vault naming: tag `ru-ekb-1` → variables like `vault_ru_ekb_1_ip`, `vault_ru_ekb_1_reality_private_key`, etc. (hyphens → underscores).

---

## 2. Steps

1. **Provision** a VM and note its public IP.

2. **Choose a tag**, e.g. `ru-ekb-1` (letters, numbers, hyphens — used in Vault and filenames).

3. **Generate a Reality key pair** for this host only:

   ```bash
   make gen-keys
   # or: docker run --rm ghcr.io/xtls/xray-core:latest x25519
   ```

4. **Vault** — add:

   - `vault_ru_ekb_1_ip` (example)
   - `vault_ru_ekb_1_reality_private_key` / `vault_ru_ekb_1_reality_public_key`  
   Do **not** change **`vault_client_uuid`** — all RU relays share the same user UUID for subscriptions.

5. **`inventories/production/hosts.yml`** — under `ru_relays.hosts`, add:

   - `ansible_host: "{{ vault_ru_ekb_1_ip }}"` (matching your tag)
   - `server_tag`, `server_location`

6. **`configs/production/vars/servers.yml`** — under `ru_servers`, add `tag`, `address: "{{ vault_…_ip }}"`, `port`, `location`.

7. **`scripts/generate-keys.sh`** — update if you rely on it for this tag.

8. **Deploy** the host:

   ```bash
   ansible-playbook playbooks/setup-common.yml --limit ru-ekb-1
   ansible-playbook playbooks/deploy-ru-relay.yml --limit ru-ekb-1
   ```

   Or for the whole RU group: `make setup` / `make deploy-ru` with appropriate `--limit`.

9. **Refresh subscription data** so clients get the new node in `vless://` links:

   ```bash
   make deploy-telegram
   ```

   Deploy the **external subscription stack** on the new relay (Caddy + proxy) if it is not yet covered:

   ```bash
   make deploy-subscription-external
   ```

   (Use `deploy-full` only if you intend to replay the entire stack.)

10. **Monitoring** — after adding a node, run `make deploy-vpn` and `make deploy-monitoring` so Prometheus targets and exporters include the new server (see [05-monitoring.md](05-monitoring.md)).

---

## 3. What does *not* change

- **`foreign_servers`** — no change if exits are unchanged.
- **Per-foreign link UUIDs** — only relevant when adding foreign exits ([08-add-foreign-exit.md](08-add-foreign-exit.md)).

---

## 4. Checks

```bash
ansible-inventory --list
make check
```

---

## 5. Renaming hosts

Vault keys derive from the tag. If you rename a host, merge or re-key `vault.yml` and redeploy every affected machine.
