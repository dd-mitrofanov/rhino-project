.PHONY: deploy-vpn deploy-full deploy-ru deploy-foreign deploy-telegram deploy-subscription-external deploy-monitoring deploy-test-server setup geodata encrypt decrypt edit-secrets gen-keys gen-keys-test lint check ensure-vault-link

# Vault must be loaded with inventory; group_vars/all/vault.yml symlink makes it available at parse time.
ensure-vault-link:
	ln -sf ../../../../configs/production/secrets/vault.yml inventories/production/group_vars/all/vault.yml

# Core Xray infrastructure only (RU relays + foreign exits + common setup).
deploy-vpn: ensure-vault-link
	ansible-playbook playbooks/site.yml

# VPN + external subscription API on all RU relays + Telegram stack with built-in subscription HTTP (nl-ams-1).
deploy-full: ensure-vault-link
	ansible-playbook playbooks/deploy-full.yml

deploy-ru: ensure-vault-link
	ansible-playbook playbooks/deploy-ru-relay.yml

deploy-foreign: ensure-vault-link
	ansible-playbook playbooks/deploy-foreign-exit.yml

# Bot + PostgreSQL + built-in subscription HTTP (full Docker Compose on nl-ams-1).
deploy-telegram: ensure-vault-link
	ansible-playbook playbooks/deploy-telegram-bot.yml

# Public subscription API + Caddy on all RU relays (proxy to bot).
deploy-subscription-external: ensure-vault-link
	ansible-playbook playbooks/deploy-subscription-external.yml

# Prometheus + Grafana + Caddy monitoring stack on de-fra-1.
deploy-monitoring: ensure-vault-link
	ansible-playbook playbooks/deploy-monitoring.yml

# Isolated test-server tree (inventories/test/, configs/test/). Never import production playbooks.
# Uses ansible-test.cfg: inventory=inventories/test, vault_password_file=.vault_pass
deploy-test-server:
	ANSIBLE_CONFIG=ansible-test.cfg ansible-playbook playbooks/deploy-test-server.yml

setup: ensure-vault-link
	ansible-playbook playbooks/setup-common.yml

geodata:
	ansible-playbook playbooks/update-geodata.yml

encrypt:
	bash scripts/encrypt-secrets.sh

decrypt:
	bash scripts/decrypt-secrets.sh

edit-secrets:
	ansible-vault edit configs/production/secrets/vault.yml

gen-keys:
	bash scripts/generate-keys.sh

gen-keys-test:
	bash scripts/generate-keys-test.sh

lint:
	ansible-lint playbooks/

check: ensure-vault-link
	ansible-playbook playbooks/site.yml --check --diff
