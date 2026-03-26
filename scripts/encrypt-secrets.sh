#!/usr/bin/env bash
set -euo pipefail

VAULT_FILE="${1:-configs/production/secrets/vault.yml}"

if head -1 "$VAULT_FILE" | grep -q '^\$ANSIBLE_VAULT;'; then
    echo "File is already encrypted: $VAULT_FILE"
    exit 0
fi

ansible-vault encrypt "$VAULT_FILE"
echo "Encrypted: $VAULT_FILE"
