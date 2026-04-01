#!/usr/bin/env bash
# Одна пара Reality (x25519) и один VLESS UUID — как в generate-keys.sh (xray в Docker),
# только вывод в терминал. Для полного vault см. scripts/generate-keys.sh.

set -euo pipefail

XRAY_IMAGE="${XRAY_IMAGE:-ghcr.io/xtls/xray-core:latest}"

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

echo "Using image: $XRAY_IMAGE (Docker must be running)"
echo ""

keys=$(generate_keypair)
reality_priv=$(parse_private "$keys")
reality_pub=$(parse_public "$keys")
vless_uuid=$(generate_uuid)

echo "reality_private_key: $reality_priv"
echo "reality_public_key:  $reality_pub"
echo "vless_uuid:          $vless_uuid"
