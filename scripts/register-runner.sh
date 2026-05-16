#!/usr/bin/env bash
set -euo pipefail

SERVER=""
PAIRING_TOKEN=""
COMPUTER_NODE_ID=""
RUNNER_NAME=""
RUNNER_ID=""
CAPABILITIES="codex,threads,filesystem"
HARDWARE_ACCESS="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) SERVER="${2:-}"; shift 2 ;;
    --pairing-token) PAIRING_TOKEN="${2:-}"; shift 2 ;;
    --computer-node-id) COMPUTER_NODE_ID="${2:-}"; shift 2 ;;
    --runner-name) RUNNER_NAME="${2:-}"; shift 2 ;;
    --runner-id) RUNNER_ID="${2:-}"; shift 2 ;;
    --capabilities) CAPABILITIES="${2:-}"; shift 2 ;;
    --hardware-access) HARDWARE_ACCESS="true"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$SERVER" || -z "$PAIRING_TOKEN" || -z "$COMPUTER_NODE_ID" || -z "$RUNNER_NAME" ]]; then
  echo "Required: --server --pairing-token --computer-node-id --runner-name" >&2
  exit 2
fi

if [[ -z "$RUNNER_ID" ]]; then
  RUNNER_ID="runner-$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex[:8])
PY
)"
fi

export RUNNER_ID RUNNER_NAME CAPABILITIES HARDWARE_ACCESS COMPUTER_NODE_ID
BODY="$(python3 - <<'PY'
import json
import os

capabilities = [item.strip() for item in os.environ["CAPABILITIES"].split(",") if item.strip()]
print(json.dumps({
    "runner_id": os.environ["RUNNER_ID"],
    "runner_name": os.environ["RUNNER_NAME"],
    "capabilities": capabilities,
    "hardware_access": os.environ["HARDWARE_ACCESS"].lower() == "true",
    "computer_node_id": os.environ["COMPUTER_NODE_ID"],
}, ensure_ascii=False))
PY
)"

API_BASE="${SERVER%/}"
API_BASE="${API_BASE/:3000/:8011}"
API_BASE="${API_BASE/:3001/:8011}"
URL="${API_BASE%/}/api/runners/register"
echo "Registering runner to $URL ..."
curl -fsSL \
  -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "x-runner-registration-token: $PAIRING_TOKEN" \
  --data-binary "$BODY"
echo
echo "Runner registered."
