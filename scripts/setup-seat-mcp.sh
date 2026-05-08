#!/usr/bin/env bash
# Seat MCP — 一键配置脚本（macOS / Linux 工位电脑）
#
# 用法：
#   bash scripts/setup-seat-mcp.sh --api-base http://192.168.1.10:8010
#
# 参数：
#   --api-base <url>      必填。平台 API 根
#   --install-dir <path>  可选。本地存放 server.py 的目录（默认 $HOME/seat-mcp-server）
#   --source-url <url>    可选。下载源（默认 <api-base>/static/seat-mcp-server.py）
#   --source-path <file>  可选。本地已经有副本时直接用
#   --cli <claude|codex|both>  可选。要注册到哪些 CLI（默认 both）
#   --skip-env            可选。不写 ~/.profile

set -euo pipefail

API_BASE=""
INSTALL_DIR="$HOME/seat-mcp-server"
SOURCE_URL=""
SOURCE_PATH=""
CLI_TARGETS="both"
SKIP_ENV=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --api-base) API_BASE="$2"; shift 2 ;;
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        --source-url) SOURCE_URL="$2"; shift 2 ;;
        --source-path) SOURCE_PATH="$2"; shift 2 ;;
        --cli) CLI_TARGETS="$2"; shift 2 ;;
        --skip-env) SKIP_ENV=1; shift ;;
        -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

if [[ -z "$API_BASE" ]]; then
    echo "[X] 必须 --api-base <url>"; exit 1
fi

ok()   { echo "  [OK] $*"; }
warn() { echo "  [!]  $*"; }
err()  { echo "  [X]  $*"; }
step() { echo "==> $*"; }

step "Step 1/5 检测 Python"
if ! command -v python3 >/dev/null 2>&1; then
    err "未检测到 python3。装 Python 3.10+ 后重试。"
    exit 1
fi
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYMAJ=${PYVER%.*}; PYMIN=${PYVER#*.}
if (( PYMAJ < 3 || ( PYMAJ == 3 && PYMIN < 10 ) )); then
    err "Python 版本 $PYVER 太低，需要 >= 3.10"; exit 1
fi
ok "Python $PYVER 满足要求"

step "Step 2/5 同步 server.py 到 $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
DEST="$INSTALL_DIR/server.py"
if [[ -n "$SOURCE_PATH" ]]; then
    if [[ ! -f "$SOURCE_PATH" ]]; then err "找不到 SOURCE_PATH=$SOURCE_PATH"; exit 1; fi
    cp "$SOURCE_PATH" "$DEST"
    ok "从 $SOURCE_PATH 复制到 $DEST"
else
    [[ -z "$SOURCE_URL" ]] && SOURCE_URL="${API_BASE%/}/static/seat-mcp-server.py"
    if command -v curl >/dev/null 2>&1; then
        if curl -fsSL -o "$DEST" "$SOURCE_URL"; then
            ok "从 $SOURCE_URL 下载到 $DEST"
        else
            err "下载失败。请手动从源电脑拷 scripts/seat-mcp-server/server.py 到 $DEST，然后重跑加 --source-path <本地路径>"; exit 1
        fi
    else
        err "未检测到 curl，无法下载"; exit 1
    fi
fi

step "Step 3/5 注册到 CLI"
REGISTERED=()

register_claude() {
    if ! command -v claude >/dev/null 2>&1; then
        warn "未检测到 claude CLI，跳过 Claude 注册"; return
    fi
    claude mcp remove seat-mcp >/dev/null 2>&1 || true
    if claude mcp add seat-mcp -- python3 "$DEST"; then
        ok "已通过 'claude mcp add' 注册"
        REGISTERED+=("claude")
    else
        warn "claude mcp add 返回非 0，请手动检查"
    fi
}

register_codex() {
    if ! command -v codex >/dev/null 2>&1; then
        warn "未检测到 codex CLI，跳过 Codex 注册"; return
    fi
    CFG_DIR="$HOME/.codex"
    mkdir -p "$CFG_DIR"
    CFG="$CFG_DIR/config.toml"
    if [[ -f "$CFG" ]] && grep -q '^\[mcp_servers\.seat-mcp\]' "$CFG"; then
        warn "$CFG 已包含 [mcp_servers.seat-mcp]，跳过"
        return
    fi
    cat >> "$CFG" <<EOF

[mcp_servers.seat-mcp]
command = "python3"
args = ["$DEST"]
EOF
    ok "写入 $CFG"
    REGISTERED+=("codex")
}

case "$CLI_TARGETS" in
    claude) register_claude ;;
    codex)  register_codex ;;
    both)   register_claude; register_codex ;;
    *) err "--cli 必须是 claude / codex / both"; exit 1 ;;
esac

if [[ ${#REGISTERED[@]} -eq 0 ]]; then
    warn "没有任何 CLI 被注册（可能都没装或都已注册过）"
else
    ok "已注册：${REGISTERED[*]}"
fi

step "Step 4/5 写入 PLATFORM_API_BASE"
if [[ $SKIP_ENV -eq 1 ]]; then
    warn "--skip-env：跳过；请确保 watcher 启动时能拿到 PLATFORM_API_BASE"
else
    PROFILE="$HOME/.profile"
    LINE="export PLATFORM_API_BASE=\"$API_BASE\""
    if [[ -f "$PROFILE" ]] && grep -q '^export PLATFORM_API_BASE=' "$PROFILE"; then
        sed -i.bak "s|^export PLATFORM_API_BASE=.*|$LINE|" "$PROFILE"
        ok "更新 $PROFILE 里现有的 PLATFORM_API_BASE"
    else
        echo "$LINE" >> "$PROFILE"
        ok "追加到 $PROFILE：$LINE"
    fi
    export PLATFORM_API_BASE="$API_BASE"
    ok "本进程也已设置（新 shell 才会自动继承；或 source ~/.profile）"
fi

step "Step 5/5 自检：ping 平台 API"
if curl -fsS -m 5 "${API_BASE%/}/health" >/dev/null 2>&1; then
    ok "平台 ${API_BASE%/}/health 可达"
else
    warn "无法访问 ${API_BASE%/}/health"
    warn "排查：① 平台主机 8010 入站防火墙；② 工位能 ping 到主机；③ 平台 API 服务在跑"
fi

echo
step "完成"
echo "下一步："
echo "  1. 启动 watcher："
echo "       bash scripts/start-thread-watcher.sh --project-id <pid> --workstation-id <wsid> --api-base $API_BASE"
echo "  2. NPC 在 CLI 里调用 seat-mcp 的 list_peers / request_help / dispatch_to_peer 即可。"
echo "  3. 故障排查见源仓库 scripts/seat-mcp-server/README.md。"
