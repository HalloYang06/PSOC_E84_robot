#!/usr/bin/env bash
set -euo pipefail

ROOT="${AI_COLLAB_ROOT:-$HOME/apps/ai-collab}"
WEB_PORT="${WEB_PORT:-3001}"
API_PORT="${API_PORT:-8011}"
RESTART="${RESTART:-0}"

cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export AI_COLLAB_BUILD_SHA="${AI_COLLAB_BUILD_SHA:-$(git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)}"
export AI_COLLAB_BUILD_REF="${AI_COLLAB_BUILD_REF:-$(git branch --show-current 2>/dev/null || echo unknown)}"
export AI_COLLAB_BUILD_TIME="${AI_COLLAB_BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

mkdir -p "$ROOT"

health_ok() {
  local url="$1"
  curl -fsS "$url" >/dev/null 2>&1
}

if [[ "$RESTART" == "1" ]]; then
  pkill -f "uvicorn app.main:app.*--port ${API_PORT}" >/dev/null 2>&1 || true
  pkill -f "next start apps/web" >/dev/null 2>&1 || true
  pkill -f "next-server" >/dev/null 2>&1 || true
  sleep 1
fi

if health_ok "http://127.0.0.1:${API_PORT}/api/health"; then
  echo "API already running on ${API_PORT}"
else
  (
    cd "$ROOT/apps/api"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    nohup python -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" \
      > "$ROOT/logs-api.txt" 2> "$ROOT/logs-api.err.txt" < /dev/null &
  )
  echo "API started on ${API_PORT}"
fi

if health_ok "http://127.0.0.1:${WEB_PORT}/api/proxy/health"; then
  echo "Web already running on ${WEB_PORT}"
else
  # Run Next directly instead of through npm --workspace. On some SSH sessions the npm wrapper exits after Ready.
  nohup env PORT="$WEB_PORT" node node_modules/next/dist/bin/next start apps/web --hostname 0.0.0.0 \
    > "$ROOT/logs-web.txt" 2> "$ROOT/logs-web.err.txt" < /dev/null &
  echo "Web started on ${WEB_PORT}"
fi

failed=0
for url in "http://127.0.0.1:${API_PORT}/api/health" "http://127.0.0.1:${WEB_PORT}/api/proxy/health"; do
  ok=0
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if health_ok "$url"; then
      echo "OK $url"
      ok=1
      break
    fi
    sleep 1
  done
  if [[ "$ok" != "1" ]]; then
    echo "FAILED $url" >&2
    failed=1
  fi
done

ss -lntp | grep -E "(:${WEB_PORT}|:${API_PORT})" || true
exit "$failed"
