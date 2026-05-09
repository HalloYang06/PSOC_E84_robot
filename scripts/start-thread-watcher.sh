#!/usr/bin/env bash
# Cross-platform watcher launcher (macOS / Linux / git-bash on Windows).
# Mirror of start-thread-watcher.ps1 — keep flags in sync if you edit one.
#
# Usage:
#   bash scripts/start-thread-watcher.sh \
#       --project-id proj_ai_collab \
#       --workstation-id <thread-config-id> \
#       [--api-base http://127.0.0.1:8010] \
#       [--provider claude|codex|qwen] \
#       [--executor-cwd <path>] \
#       [--poll-seconds 3] \
#       [--spawn-window] [--persistent-window]
#
# Watcher runs in FOREGROUND on purpose — you must see the collaboration
# happen in this terminal (banners + claude stdout + 已回写). Do NOT wrap
# this with nohup/& — that defeats the visibility requirement.
#
# Auth token: export PLATFORM_AUTH_TOKEN beforehand (a human session bearer
# minted via apps/api app.common.access.issue_access_token), otherwise inbox
# fetch returns 401 and the watcher will idle.

set -euo pipefail

PROJECT_ID=""
WORKSTATION_ID=""
API_BASE="http://127.0.0.1:8010"
PROVIDER=""
EXECUTOR_CWD=""
POLL_SECONDS="3"
SPAWN_WINDOW="0"
PERSISTENT_WINDOW="0"

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-2}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --project-id) PROJECT_ID="$2"; shift 2 ;;
    --workstation-id) WORKSTATION_ID="$2"; shift 2 ;;
    --api-base) API_BASE="$2"; shift 2 ;;
    --provider) PROVIDER="$2"; shift 2 ;;
    --executor-cwd) EXECUTOR_CWD="$2"; shift 2 ;;
    --poll-seconds) POLL_SECONDS="$2"; shift 2 ;;
    --spawn-window) SPAWN_WINDOW="1"; shift ;;
    --persistent-window) PERSISTENT_WINDOW="1"; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown arg: $1" >&2; usage 2 ;;
  esac
done

if [ -z "$PROJECT_ID" ] || [ -z "$WORKSTATION_ID" ]; then
  echo "missing --project-id or --workstation-id" >&2
  usage 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ADAPTER_REL="scripts/platform-workstation-adapter.py"

# On Windows git-bash / MSYS / Cygwin, the python interpreter is the native
# Windows build and cannot read POSIX-style paths like /d/foo. Convert to
# Windows form so --executor-cwd is usable. On macOS / Linux cygpath is absent,
# leave paths untouched. The adapter itself is invoked via a cwd-relative path
# (after `cd $REPO_ROOT`) to avoid passing absolute non-ASCII paths through
# the bash→cmd argv encoding boundary.
_to_native_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf '%s' "$1"
  fi
}

REPO_ROOT_NATIVE="$(_to_native_path "$REPO_ROOT")"

if [ ! -f "$REPO_ROOT/$ADAPTER_REL" ]; then
  echo "adapter not found at $REPO_ROOT/$ADAPTER_REL" >&2
  exit 2
fi

if [ -z "$EXECUTOR_CWD" ]; then
  EXECUTOR_CWD="$REPO_ROOT_NATIVE"
else
  EXECUTOR_CWD="$(_to_native_path "$EXECUTOR_CWD")"
fi

# Pick a python: prefer python3, fallback to python.
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "python not found in PATH" >&2
  exit 127
fi

echo "========================================"
echo "项目线程 watcher 启动准备"
echo "项目: $PROJECT_ID"
echo "线程: $WORKSTATION_ID"
echo "API:  $API_BASE"
echo "执行目录: $EXECUTOR_CWD"
[ -n "$PROVIDER" ] && echo "Provider 覆盖: $PROVIDER"
echo "轮询: 每 ${POLL_SECONDS}s"
if [ -z "${PLATFORM_AUTH_TOKEN:-}" ]; then
  echo "⚠ PLATFORM_AUTH_TOKEN 未设置，watcher 拉 inbox 会 401。"
  echo "  先 mint 一个 human session token 再 export，或者用 PLATFORM_ADAPTER_TOKEN。"
fi
echo "========================================"

ARGS=(
  "$ADAPTER_REL"
  --api-base "$API_BASE"
  --project-id "$PROJECT_ID"
  --workstation-id "$WORKSTATION_ID"
  --auto-ack
  --execute-provider-cli
  --executor-cwd "$EXECUTOR_CWD"
  --watch
  --poll-seconds "$POLL_SECONDS"
)
[ -n "$PROVIDER" ] && ARGS+=(--provider "$PROVIDER")
[ "$SPAWN_WINDOW" = "1" ] && ARGS+=(--spawn-window)
[ "$PERSISTENT_WINDOW" = "1" ] && ARGS+=(--persistent-window)

cd "$REPO_ROOT"
exec "$PY" "${ARGS[@]}"
