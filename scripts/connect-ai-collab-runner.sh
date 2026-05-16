#!/usr/bin/env bash
set -euo pipefail

SERVER=""
PAIRING_TOKEN=""
COMPUTER_NODE_ID=""
RUNNER_NAME=""
RUNNER_ID=""
PROJECT_ID=""
WORKSPACE_ROOT=""
WEB_BASE_URL=""
TAKE="12"
CODEX_MAX_AGE_DAYS="14"
CLAUDE_MAX_AGE_HOURS="24"
WATCH="false"
WATCH_POLL_SECONDS="15"
WATCH_MAX_LOOPS="0"
WATCH_EXECUTE_PROVIDER_CLI="false"
SKIP_CODEX="false"
SKIP_CLAUDE="false"
HARDWARE_ACCESS="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) SERVER="${2:-}"; shift 2 ;;
    --pairing-token) PAIRING_TOKEN="${2:-}"; shift 2 ;;
    --computer-node-id) COMPUTER_NODE_ID="${2:-}"; shift 2 ;;
    --runner-name) RUNNER_NAME="${2:-}"; shift 2 ;;
    --runner-id) RUNNER_ID="${2:-}"; shift 2 ;;
    --project-id) PROJECT_ID="${2:-}"; shift 2 ;;
    --workspace-root) WORKSPACE_ROOT="${2:-}"; shift 2 ;;
    --web-base-url) WEB_BASE_URL="${2:-}"; shift 2 ;;
    --take) TAKE="${2:-}"; shift 2 ;;
    --codex-max-age-days) CODEX_MAX_AGE_DAYS="${2:-}"; shift 2 ;;
    --claude-max-age-hours) CLAUDE_MAX_AGE_HOURS="${2:-}"; shift 2 ;;
    --watch) WATCH="true"; shift ;;
    --watch-poll-seconds) WATCH_POLL_SECONDS="${2:-}"; shift 2 ;;
    --watch-max-loops) WATCH_MAX_LOOPS="${2:-}"; shift 2 ;;
    --watch-execute-provider-cli) WATCH_EXECUTE_PROVIDER_CLI="true"; shift ;;
    --skip-codex) SKIP_CODEX="true"; shift ;;
    --skip-claude) SKIP_CLAUDE="true"; shift ;;
    --hardware-access) HARDWARE_ACCESS="true"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$SERVER" || -z "$PAIRING_TOKEN" || -z "$COMPUTER_NODE_ID" ]]; then
  echo "Required: --server --pairing-token --computer-node-id" >&2
  exit 2
fi

normalize_slug() {
  python3 - "$1" <<'PY'
import re
import sys
raw = (sys.argv[1] if len(sys.argv) > 1 else "computer").lower()
slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
print(slug or "computer")
PY
}

resolve_api_base() {
  local base="${1%/}"
  base="${base/:3000/:8011}"
  base="${base/:3001/:8011}"
  echo "$base"
}

resolve_web_base() {
  if [[ -n "$WEB_BASE_URL" ]]; then
    echo "${WEB_BASE_URL%/}"
    return
  fi
  local base="${1%/}"
  base="${base/:8010/:3000}"
  base="${base/:8011/:3001}"
  base="${base/:8000/:3000}"
  echo "$base"
}

if [[ -z "$RUNNER_ID" ]]; then
  RUNNER_ID="runner-$(normalize_slug "$COMPUTER_NODE_ID")"
fi
if [[ -z "$RUNNER_NAME" ]]; then
  RUNNER_NAME="$COMPUTER_NODE_ID Runner"
fi

API_BASE="$(resolve_api_base "$SERVER")"
WEB_BASE="$(resolve_web_base "$SERVER")"
RUNNER_DIR="./ai-collab-runner"
mkdir -p "$RUNNER_DIR"

download_runner_script() {
  local script="$1"
  local target="$RUNNER_DIR/$script"
  local url="${WEB_BASE%/}/downloads/runner/$script"
  echo "Downloading $script from $url ..."
  curl -fsSL "$url" -o "$target"
  chmod +x "$target" || true
}

json_body() {
  export RUNNER_ID RUNNER_NAME COMPUTER_NODE_ID HARDWARE_ACCESS
  python3 - <<'PY'
import json
import os

print(json.dumps({
    "runner_id": os.environ["RUNNER_ID"],
    "runner_name": os.environ["RUNNER_NAME"],
    "capabilities": ["codex", "threads", "filesystem"],
    "hardware_access": os.environ["HARDWARE_ACCESS"].lower() == "true",
    "computer_node_id": os.environ["COMPUTER_NODE_ID"],
}, ensure_ascii=False))
PY
}

register_runner() {
  local body
  body="$(json_body)"
  local url="${API_BASE%/}/api/runners/register"
  echo "Registering runner to $url ..."
  if curl -fsSL \
    -X POST "$url" \
    -H "Content-Type: application/json" \
    -H "x-runner-registration-token: $PAIRING_TOKEN" \
    --data-binary "$body"; then
    echo
    echo "Runner registered as $RUNNER_ID"
    return 0
  fi
  if [[ "$PAIRING_TOKEN" != "already-bound-runner-reuse" ]]; then
    if heartbeat_runner 2>/dev/null; then
      local workspace_json
      workspace_json="$(runner_workspace_json 2>/dev/null || true)"
      if [[ -n "$workspace_json" ]] && WORKSPACE_JSON="$workspace_json" PROJECT_ID="$PROJECT_ID" COMPUTER_NODE_ID="$COMPUTER_NODE_ID" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ.get("WORKSPACE_JSON") or "{}")
data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
project_id = os.environ.get("PROJECT_ID", "")
computer_node_id = os.environ.get("COMPUTER_NODE_ID", "")
for binding in data.get("bindings") or []:
    if str(binding.get("project_id") or "") == project_id and str(binding.get("computer_node_id") or "") == computer_node_id:
        raise SystemExit(0)
raise SystemExit(1)
PY
      then
        echo "Pairing token was rejected, but runner $RUNNER_ID is already bound to $COMPUTER_NODE_ID. Continuing with existing runner."
        return 0
      fi
    fi
  fi
  if [[ "$PAIRING_TOKEN" == "already-bound-runner-reuse" ]]; then
    echo "Pairing token is reuse marker; continuing with existing runner $RUNNER_ID."
    return 0
  fi
  echo "Runner registration failed. Generate a fresh pairing token and rerun the command." >&2
  return 1
}

heartbeat_runner() {
  local body
  body="$(python3 - <<PY
import json
print(json.dumps({"runner_id": "$RUNNER_ID"}))
PY
)"
  curl -fsSL \
    -X POST "${API_BASE%/}/api/runners/heartbeat" \
    -H "Content-Type: application/json" \
    -H "X-Runner-Id: $RUNNER_ID" \
    --data-binary "$body" >/dev/null
}

runner_workspace_json() {
  curl -fsSL \
    -H "X-Runner-Id: $RUNNER_ID" \
    "${API_BASE%/}/api/runners/$RUNNER_ID/workspace"
}

poll_runner_inbox_once() {
  local payload
  payload="$(curl -fsSL \
    -H "X-Runner-Id: $RUNNER_ID" \
    "${API_BASE%/}/api/runners/$RUNNER_ID/inbox?limit=20")"
  RUNNER_INBOX_JSON="$payload" RUNNER_ID="$RUNNER_ID" python3 - <<'PY' | while IFS=$'\t' read -r message_id title; do
import json
import os

raw = os.environ.get("RUNNER_INBOX_JSON") or "{}"
payload = json.loads(raw)
items = payload.get("data") if isinstance(payload, dict) else []
for item in items or []:
    if str(item.get("status") or "").strip().lower() not in {"pending", "queued"}:
        continue
    message_id = str(item.get("id") or "").strip()
    if not message_id:
        continue
    title = str(item.get("title") or "Platform dispatch").replace("\t", " ").replace("\n", " ").strip()
    print(f"{message_id}\t{title}")
PY
    local note="Runner ${RUNNER_NAME} received platform dispatch: ${title}. The computer connection is reachable; enable NPC automation or bind a desktop thread before real execution."
    curl -fsSL \
      -X POST "${API_BASE%/}/api/runners/$RUNNER_ID/messages/$message_id/ack" \
      -H "Content-Type: application/json" \
      -H "X-Runner-Id: $RUNNER_ID" \
      --data-binary "$(NOTE="$note" python3 - <<'PY'
import json
import os
print(json.dumps({"note": os.environ["NOTE"]}, ensure_ascii=False))
PY
)" >/dev/null || echo "runner ack failed for $message_id" >&2
    curl -fsSL \
      -X POST "${API_BASE%/}/api/runners/$RUNNER_ID/messages/$message_id/complete" \
      -H "Content-Type: application/json" \
      -H "X-Runner-Id: $RUNNER_ID" \
      --data-binary "$(NOTE="$note" python3 - <<'PY'
import json
import os
print(json.dumps({"result_status": "completed", "note": os.environ["NOTE"]}, ensure_ascii=False))
PY
)" >/dev/null || echo "runner complete failed for $message_id" >&2
    echo "Runner command completed: $message_id $title"
  done
}

poll_workstations_once() {
  download_runner_script "platform-workstation-adapter.py"
  download_runner_script "platform-provider-executor.py"
  local adapter="$RUNNER_DIR/platform-workstation-adapter.py"
  local workspace_json
  workspace_json="$(runner_workspace_json)"
  WORKSPACE_JSON="$workspace_json" PROJECT_ID="$PROJECT_ID" COMPUTER_NODE_ID="$COMPUTER_NODE_ID" python3 - <<'PY' | while IFS=$'\t' read -r workstation_id provider; do
import json
import os

raw = os.environ.get("WORKSPACE_JSON") or "{}"
payload = json.loads(raw)
data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
project_id = os.environ.get("PROJECT_ID", "")
computer_node_id = os.environ.get("COMPUTER_NODE_ID", "")
for item in data.get("workstations") or []:
    if str(item.get("project_id") or "") != project_id:
        continue
    if str(item.get("computer_node_id") or "") != computer_node_id:
        continue
    workstation_id = str(item.get("workstation_id") or "").strip()
    if not workstation_id:
        continue
    provider = str(item.get("ai_provider_id") or item.get("ai_provider_label") or "generic").strip() or "generic"
    print(f"{workstation_id}\t{provider}")
PY
    local args=(
      "$adapter"
      --api-base "$API_BASE"
      --project-id "$PROJECT_ID"
      --workstation-id "$workstation_id"
      --runner-id "$RUNNER_ID"
      --provider "$provider"
      --auto-ack
      --limit "20"
      --output-dir "./artifacts/workstation-inbox"
    )
    if [[ "$WATCH_EXECUTE_PROVIDER_CLI" == "true" ]]; then
      args+=(--execute-provider-cli)
    fi
    local output
    if ! output="$(python3 "${args[@]}" 2>&1)"; then
      if echo "$output" | grep -Eq "HTTP 40(1|3)|UNAUTHORIZED|PERMISSION_DENIED"; then
        echo "Workstation $workstation_id is visible to this runner, but it is not authorized for automatic thread inbox polling yet. Keep the runner watch window open, then enable/bind the thread from the platform before expecting NPC auto-execution." >&2
      else
        echo "workstation poll failed for $workstation_id" >&2
        echo "$output" >&2
      fi
      continue
    fi
    echo "$output"
  done
}

register_runner

download_runner_script "platform-workstation-adapter.py"
download_runner_script "platform-provider-executor.py"

if [[ "$SKIP_CODEX" != "true" ]]; then
  if download_runner_script "sync-codex-session-threads.sh"; then
    CODEX_ARGS=(
      --server "$API_BASE"
      --runner-id "$RUNNER_ID"
      --project-id "$PROJECT_ID"
      --computer-node-id "$COMPUTER_NODE_ID"
      --take "$TAKE"
      --max-age-days "$CODEX_MAX_AGE_DAYS"
    )
    if [[ -n "$WORKSPACE_ROOT" ]]; then
      CODEX_ARGS+=(--workspace-root "$WORKSPACE_ROOT")
    fi
    "$RUNNER_DIR/sync-codex-session-threads.sh" "${CODEX_ARGS[@]}" || echo "Codex session scan skipped or failed." >&2
  fi
fi

if [[ "$SKIP_CLAUDE" != "true" ]]; then
  if download_runner_script "sync-claude-session-threads.sh"; then
    CLAUDE_ARGS=(
      --server "$API_BASE"
      --runner-id "$RUNNER_ID"
      --project-id "$PROJECT_ID"
      --computer-node-id "$COMPUTER_NODE_ID"
      --take "$TAKE"
      --max-age-hours "$CLAUDE_MAX_AGE_HOURS"
    )
    if [[ -n "$WORKSPACE_ROOT" ]]; then
      CLAUDE_ARGS+=(--workspace-root "$WORKSPACE_ROOT")
    fi
    "$RUNNER_DIR/sync-claude-session-threads.sh" "${CLAUDE_ARGS[@]}" || echo "Claude session scan skipped or failed." >&2
  fi
fi

echo "AI collaboration runner connect finished."
python3 - <<PY
import json
print(json.dumps({
    "runner_id": "$RUNNER_ID",
    "computer_node_id": "$COMPUTER_NODE_ID",
    "project_id": "$PROJECT_ID",
    "api_base": "$API_BASE",
    "web_base": "$WEB_BASE",
    "workspace_root": "$WORKSPACE_ROOT" or None,
    "runner_dir": "$RUNNER_DIR",
    "watch_enabled": "$WATCH" == "true",
    "watch_execute_provider_cli": "$WATCH_EXECUTE_PROVIDER_CLI" == "true",
}, ensure_ascii=False, indent=2))
PY

if [[ "$WATCH" == "true" ]]; then
  if [[ -z "$PROJECT_ID" ]]; then
    echo "--project-id is required for watch mode." >&2
    exit 2
  fi
  if [[ "$WATCH_EXECUTE_PROVIDER_CLI" == "true" ]]; then
    echo "Provider CLI execution is enabled. Use only on trusted computers after human approval."
  else
    echo "Provider CLI execution is OFF. The runner will keep heartbeat and write minimal acknowledgements."
  fi
  loop=0
  while true; do
    loop=$((loop + 1))
    heartbeat_runner || echo "heartbeat failed once" >&2
    poll_runner_inbox_once || echo "runner inbox poll failed once" >&2
    poll_workstations_once || echo "workstation poll failed once" >&2
    if [[ "$WATCH_MAX_LOOPS" != "0" && "$loop" -ge "$WATCH_MAX_LOOPS" ]]; then
      break
    fi
    sleep "$WATCH_POLL_SECONDS"
  done
fi
