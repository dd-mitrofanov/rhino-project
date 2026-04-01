#!/bin/bash
# Managed by Ansible — POST to bot after Docker starts the xray container
set -euo pipefail
ENV_FILE=/etc/xray-sync-webhook.env
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
: "${XRAY_SYNC_WEBHOOK_URL:?}"
: "${XRAY_SYNC_WEBHOOK_TOKEN:?}"

trigger_sync() {
  local i=0
  while [ "$i" -lt 15 ]; do
    if curl -fsS --connect-timeout 5 --max-time 120 \
      -X POST \
      -H "Authorization: Bearer ${XRAY_SYNC_WEBHOOK_TOKEN}" \
      -H "Content-Type: application/json" \
      "${XRAY_SYNC_WEBHOOK_URL}"; then
      return 0
    fi
    i=$((i + 1))
    sleep 2
  done
  logger -t xray-sync-webhook "failed to POST ${XRAY_SYNC_WEBHOOK_URL} after retries"
  return 1
}

docker events --filter 'container=xray' --filter 'event=start' --format '{{.Time}}' |
  while read -r _; do
    trigger_sync || true
  done
