#!/usr/bin/env bash
set -euo pipefail

VAULT_FILE="${1:-configs/production/secrets/vault.yml}"

if ! head -1 "$VAULT_FILE" | grep -q '^\$ANSIBLE_VAULT;'; then
    echo "File is not encrypted (or already decrypted): $VAULT_FILE"
    exit 0
fi

ansible-vault decrypt "$VAULT_FILE"
echo "Decrypted: $VAULT_FILE"
echo "WARNING: Remember to re-encrypt before committing!"
