#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VAULT_EXAMPLE="$REPO_ROOT/configs/production/secrets/vault.yml.example"
VAULT_OUT="$REPO_ROOT/configs/production/secrets/vault.yml"

XRAY_IMAGE="${XRAY_IMAGE:-ghcr.io/xtls/xray-core:latest}"

echo "=== Fault-Tolerant Bypass Channel — Key Generation ==="
echo ""
echo "Using image: $XRAY_IMAGE"
echo "Make sure Docker is running."
echo ""

generate_keypair() {
    docker run --rm "$XRAY_IMAGE" x25519 2>/dev/null
}

generate_uuid() {
    docker run --rm "$XRAY_IMAGE" uuid 2>/dev/null | tr -d '\r'
}

generate_hex_token() {
    openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | xxd -p -c 64 | tr -d '\n'
}

echo "Generating Reality key pairs..."
ru_msk_1_keys=$(generate_keypair)
ru_msk_2_keys=$(generate_keypair)
nl_ams_1_keys=$(generate_keypair)
de_fra_1_keys=$(generate_keypair)

echo "Generating VLESS UUIDs..."
client_uuid=$(generate_uuid)
nl_ams_1_uuid=$(generate_uuid)
de_fra_1_uuid=$(generate_uuid)

echo "Generating subscription API token..."
subscription_api_token=$(generate_hex_token)

echo ""
echo "Creating vault.yml from template..."

if [[ ! -f "$VAULT_EXAMPLE" ]]; then
    echo "ERROR: Template not found: $VAULT_EXAMPLE"
    exit 1
fi

# Parse x25519 output: supports both "Private key:"/"Public key:" and "PrivateKey:"/"Password:" formats
parse_private() { echo "$1" | grep -iE '(Private key|PrivateKey):' | head -1 | sed -E 's/.*:[[:space:]]+//'; }
parse_public() {
  # New format: "Password:" is the public key; old format: "Public key:"
  if echo "$1" | grep -q -iE 'Password:'; then
    echo "$1" | grep -iE 'Password:' | head -1 | sed -E 's/.*:[[:space:]]+//'
  else
    echo "$1" | grep -iE 'Public key:' | head -1 | sed -E 's/.*:[[:space:]]+//'
  fi
}

ru_msk_1_priv=$(parse_private "$ru_msk_1_keys")
ru_msk_1_pub=$(parse_public "$ru_msk_1_keys")
ru_msk_2_priv=$(parse_private "$ru_msk_2_keys")
ru_msk_2_pub=$(parse_public "$ru_msk_2_keys")
nl_ams_1_priv=$(parse_private "$nl_ams_1_keys")
nl_ams_1_pub=$(parse_public "$nl_ams_1_keys")
de_fra_1_priv=$(parse_private "$de_fra_1_keys")
de_fra_1_pub=$(parse_public "$de_fra_1_keys")

# Build output from template with sed replacements
output=$(cat "$VAULT_EXAMPLE")
output="${output//vault_ru_msk_1_reality_private_key: \"PRIVATE_KEY\"/vault_ru_msk_1_reality_private_key: \"$ru_msk_1_priv\"}"
output="${output//vault_ru_msk_1_reality_public_key: \"PUBLIC_KEY\"/vault_ru_msk_1_reality_public_key: \"$ru_msk_1_pub\"}"
output="${output//vault_ru_msk_2_reality_private_key: \"PRIVATE_KEY\"/vault_ru_msk_2_reality_private_key: \"$ru_msk_2_priv\"}"
output="${output//vault_ru_msk_2_reality_public_key: \"PUBLIC_KEY\"/vault_ru_msk_2_reality_public_key: \"$ru_msk_2_pub\"}"
output="${output//vault_nl_ams_1_reality_private_key: \"PRIVATE_KEY\"/vault_nl_ams_1_reality_private_key: \"$nl_ams_1_priv\"}"
output="${output//vault_nl_ams_1_reality_public_key: \"PUBLIC_KEY\"/vault_nl_ams_1_reality_public_key: \"$nl_ams_1_pub\"}"
output="${output//vault_de_fra_1_reality_private_key: \"PRIVATE_KEY\"/vault_de_fra_1_reality_private_key: \"$de_fra_1_priv\"}"
output="${output//vault_de_fra_1_reality_public_key: \"PUBLIC_KEY\"/vault_de_fra_1_reality_public_key: \"$de_fra_1_pub\"}"
output="${output//vault_client_uuid: \"UUID\"/vault_client_uuid: \"$client_uuid\"}"
output="${output//vault_nl_ams_1_uuid: \"UUID\"/vault_nl_ams_1_uuid: \"$nl_ams_1_uuid\"}"
output="${output//vault_de_fra_1_uuid: \"UUID\"/vault_de_fra_1_uuid: \"$de_fra_1_uuid\"}"
output="${output//vault_subscription_api_token: \"REPLACE_WITH_LONG_RANDOM_HEX_OR_UUID\"/vault_subscription_api_token: \"$subscription_api_token\"}"

echo "$output" > "$VAULT_OUT"

echo "Written: $VAULT_OUT"
echo ""
echo "Next steps:"
echo "  1. Edit $VAULT_OUT and set vault_*_ip for each server (ru_msk_1, ru_msk_2, nl_ams_1, de_fra_1)"
echo "  2. Run: make encrypt"
echo ""
