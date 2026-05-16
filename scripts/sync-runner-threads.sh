#!/usr/bin/env bash
set -euo pipefail

SERVER=""
RUNNER_ID=""
PROJECT_ID=""
COMPUTER_NODE_ID=""
THREAD_ID="codex-mainline"
THREAD_NAME="Codex Mainline"
STATUS="active"
CWD_VALUE=""
MODEL="gpt-5.4"
DESCRIPTION="Manually registered AI thread on this runner computer"
NOTES="Synced from the computer-side agent"
AI_PROVIDER_ID="codex"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) SERVER="${2:-}"; shift 2 ;;
    --runner-id) RUNNER_ID="${2:-}"; shift 2 ;;
    --project-id) PROJECT_ID="${2:-}"; shift 2 ;;
    --computer-node-id) COMPUTER_NODE_ID="${2:-}"; shift 2 ;;
    --thread-id) THREAD_ID="${2:-}"; shift 2 ;;
    --thread-name) THREAD_NAME="${2:-}"; shift 2 ;;
    --status) STATUS="${2:-}"; shift 2 ;;
    --cwd) CWD_VALUE="${2:-}"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    --description) DESCRIPTION="${2:-}"; shift 2 ;;
    --notes) NOTES="${2:-}"; shift 2 ;;
    --ai-provider-id) AI_PROVIDER_ID="${2:-}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$SERVER" || -z "$RUNNER_ID" || -z "$PROJECT_ID" || -z "$COMPUTER_NODE_ID" ]]; then
  echo "Required: --server --runner-id --project-id --computer-node-id" >&2
  exit 2
fi

BODY_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE"' EXIT

export BODY_FILE PROJECT_ID COMPUTER_NODE_ID THREAD_ID THREAD_NAME STATUS CWD_VALUE MODEL DESCRIPTION NOTES AI_PROVIDER_ID
python3 - <<'PY'
import json
import os

def clean(value: str | None) -> str:
    return " ".join(str(value or "").split())

cwd = clean(os.environ.get("CWD_VALUE")) or None
payload = {
    "project_id": clean(os.environ["PROJECT_ID"]),
    "computer_node_id": clean(os.environ["COMPUTER_NODE_ID"]),
    "workstations": [
        {
            "workstation_id": clean(os.environ["THREAD_ID"]),
            "workstation_name": clean(os.environ["THREAD_NAME"]),
            "workstation_status": clean(os.environ["STATUS"]),
            "cwd": cwd,
            "model": clean(os.environ["MODEL"]),
            "description": clean(os.environ["DESCRIPTION"]),
            "notes": clean(os.environ["NOTES"]),
            "ai_provider_id": clean(os.environ["AI_PROVIDER_ID"]),
        }
    ],
}
with open(os.environ["BODY_FILE"], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
PY

API_BASE="${SERVER%/}"
API_BASE="${API_BASE/:3000/:8010}"
API_BASE="${API_BASE/:3001/:8011}"
URL="${API_BASE%/}/api/runners/$RUNNER_ID/thread-workstations/sync"
echo "Syncing runner thread slot to $URL ..."
curl -fsSL \
  -X POST "$URL" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-runner-id: $RUNNER_ID" \
  --data-binary "@$BODY_FILE"
echo
echo "Runner thread slot synced."
