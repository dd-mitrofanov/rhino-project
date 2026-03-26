#!/usr/bin/env bash
set -euo pipefail

# Генерация ключей для тестового сервера (configs/test/secrets/vault.yml).
# Аналог generate-keys.sh, но для единственного тестового хоста.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VAULT_EXAMPLE="$REPO_ROOT/configs/test/secrets/vault.yml.example"
VAULT_OUT="$REPO_ROOT/configs/test/secrets/vault.yml"

XRAY_IMAGE="${XRAY_IMAGE:-ghcr.io/xtls/xray-core:latest}"

echo "=== Test Server — Key Generation ==="
echo ""
echo "Using image: $XRAY_IMAGE"
echo ""

generate_keypair() {
    docker run --rm "$XRAY_IMAGE" x25519 2>/dev/null
}

generate_uuid() {
    docker run --rm "$XRAY_IMAGE" uuid 2>/dev/null | tr -d '\r'
}

parse_private() { echo "$1" | grep -iE '(Private key|PrivateKey):' | head -1 | sed -E 's/.*:[[:space:]]+//'; }
parse_public() {
  if echo "$1" | grep -q -iE 'Password:'; then
    echo "$1" | grep -iE 'Password:' | head -1 | sed -E 's/.*:[[:space:]]+//'
  else
    echo "$1" | grep -iE 'Public key:' | head -1 | sed -E 's/.*:[[:space:]]+//'
  fi
}

echo "Generating Reality key pair..."
keys=$(generate_keypair)
reality_priv=$(parse_private "$keys")
reality_pub=$(parse_public "$keys")

echo "Generating VLESS UUID..."
vless_uuid=$(generate_uuid)

echo ""
echo "Creating vault.yml from template..."

if [[ ! -f "$VAULT_EXAMPLE" ]]; then
    echo "ERROR: Template not found: $VAULT_EXAMPLE"
    exit 1
fi

output=$(cat "$VAULT_EXAMPLE")
output="${output//vault_vless_uuid: \"00000000-0000-0000-0000-000000000000\"/vault_vless_uuid: \"$vless_uuid\"}"
output="${output//vault_reality_private_key: \"YOUR_REALITY_PRIVATE_KEY_BASE64\"/vault_reality_private_key: \"$reality_priv\"}"
output="${output//vault_reality_public_key: \"YOUR_REALITY_PUBLIC_KEY_BASE64\"/vault_reality_public_key: \"$reality_pub\"}"

echo "$output" > "$VAULT_OUT"

echo "Written: $VAULT_OUT"
echo ""
echo "Next steps:"
echo "  1. ansible-vault encrypt $VAULT_OUT"
echo "  2. make deploy-test-server"
echo ""
