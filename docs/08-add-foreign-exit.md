# Adding a foreign exit server

Foreign exits receive traffic from **RU outbounds** (VLESS + Reality, TCP raw). Adding a new exit requires new **Reality keys**, a new **link UUID** for RU→that-exit, inventory and `servers.yml` updates, and a **full RU relay redeploy** so outbounds and observatory selectors match.

---

## 1. How the pieces connect

| Artifact | Purpose |
|----------|---------|
| `inventories/production/hosts.yml` | Host under `foreign_exits.hosts` |
| `configs/production/secrets/vault.yml` | IP; Reality private/public keys; **`vault_<tag>_uuid`** — unique per foreign exit (RU outbounds use this UUID) |
| `configs/production/vars/servers.yml` | `foreign_servers` list: `tag`, `address`, `port`, `location` |
| `scripts/generate-keys.sh` | Extend if you generate keys in bulk |

**Balancer fallback:** In `ru-relay.json.j2`, `fallbackTag` is **`foreign_servers[0].tag`**. Put your preferred default exit **first** in the list.

---

## 2. Steps

1. **Provision** a VM (EU or any suitable region) and note its public IP.

2. **Choose a tag**, e.g. `nl-ams-2`.

3. **Generate**:

   - A **Reality key pair** for this host.
   - A **new UUID** for the RU→foreign link (`docker run --rm ghcr.io/xtls/xray-core:latest uuid` or via `make gen-keys` workflow).

4. **Vault** — add:

   - `vault_nl_ams_2_ip` (example)
   - `vault_nl_ams_2_reality_private_key` / `vault_nl_ams_2_reality_public_key`
   - `vault_nl_ams_2_uuid` — **must** match the outbound UUID configured on **all** RU relays for this exit.

5. **`inventories/production/hosts.yml`** — add the host under `foreign_exits`.

6. **`configs/production/vars/servers.yml`** — append to `foreign_servers` with correct **order** (first entry = balancer fallback).

7. **`scripts/generate-keys.sh`** — update if needed.

8. **Deploy the new exit**:

   ```bash
   ansible-playbook playbooks/setup-common.yml --limit nl-ams-2
   ansible-playbook playbooks/deploy-foreign-exit.yml --limit nl-ams-2
   ```

9. **Redeploy all RU relays** — required so they receive the new outbound and observatory entry:

   ```bash
   make deploy-ru
   ```

   Without this step, RU relays will not use the new node.

10. **Monitoring** — `make deploy-vpn` and `make deploy-monitoring` so Prometheus scrapes the new node (see [05-monitoring.md](05-monitoring.md)).

---

## 3. Observatory behavior

After deployment, observatory probes (default ~1 minute) will start marking the new exit as live. Until then, the balancer may exclude it if probes fail — verify connectivity from RU to the foreign **443** (or your inbound port) and firewall rules.

---

## 4. Checks

```bash
ansible-inventory --list
make check
```

---

## 5. Renaming or removing an exit

- **Rename**: re-key Vault variables to match the new tag; update inventory and `servers.yml`; redeploy foreign and **all** RU relays.
- **Remove**: remove from `servers.yml` and inventory; redeploy **all** RU relays so outbounds and observatory no longer reference the old tag; decommission the VM.

---

## See also

- RU side of outbounds: [03-ru-relay-configurations.md](03-ru-relay-configurations.md)
- Foreign template behavior: [04-foreign-exit-configurations.md](04-foreign-exit-configurations.md)
