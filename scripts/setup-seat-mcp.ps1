# Seat MCP — 一键配置脚本（Windows 工位电脑）
#
# 用途：在另一台 Windows 工位电脑上一行命令完成：
#   1. 检测 Python（>=3.10）
#   2. 同步 server.py 到本机（默认 %USERPROFILE%\seat-mcp-server\server.py）
#   3. 注册到 Claude / Codex CLI
#   4. 写入 PLATFORM_API_BASE 环境变量（用户级，永久生效）
#   5. 自检：能不能 ping 到平台 API
#
# 用法（在工位电脑 PowerShell 跑）：
#   irm http://<平台主机>:8010/static/setup-seat-mcp.ps1 | iex
# 或本地复制后：
#   pwsh -ExecutionPolicy Bypass -File scripts/setup-seat-mcp.ps1 -ApiBase http://192.168.1.10:8010
#
# 参数：
#   -ApiBase     必填。平台 API 根，例如 http://192.168.1.10:8010
#   -InstallDir  可选。本地存放 server.py 的目录（默认 $HOME\seat-mcp-server）
#   -SourceUrl   可选。从哪里拉 server.py（默认 $ApiBase/static/seat-mcp-server.py）
#   -SourcePath  可选。如果你已经有本地副本，直接用文件路径而不是网络下载
#   -CliTargets  可选。要注册到哪些 CLI：claude / codex / both（默认 both，自动跳过没装的）
#   -SkipEnv     可选。不写 PLATFORM_API_BASE 到用户环境变量
#
# 它不做什么：
#   - 不装 Python（如果没装会提示你装）
#   - 不动 PLATFORM_SEAT_ID（这个是 watcher 每条消息动态注入的）
#   - 不动其他 MCP server 的配置（只 add 一项 seat-mcp）

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ApiBase,
    [string]$InstallDir = (Join-Path $env:USERPROFILE "seat-mcp-server"),
    [string]$SourceUrl = "",
    [string]$SourcePath = "",
    [ValidateSet("claude","codex","both")][string]$CliTargets = "both",
    [switch]$SkipEnv
)

$ErrorActionPreference = "Stop"

function Write-Step { param([string]$msg) Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn2{ param([string]$msg) Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Write-Err2 { param([string]$msg) Write-Host "  [X] $msg" -ForegroundColor Red }

Write-Step "Step 1/5 检测 Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Err2 "未检测到 python。请装 Python 3.10+ 后重试：https://www.python.org/downloads/"
    exit 1
}
$verRaw = & python --version 2>&1
$ver = ($verRaw -replace '[^\d\.]','').Split('.') | Select-Object -First 3
$major = [int]$ver[0]; $minor = [int]$ver[1]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    Write-Err2 "Python 版本太低 ($verRaw)，需要 >= 3.10"
    exit 1
}
Write-Ok "Python $verRaw 满足要求"

Write-Step "Step 2/5 同步 server.py 到 $InstallDir"
if (-not (Test-Path $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null }
$dest = Join-Path $InstallDir "server.py"
if ($SourcePath) {
    if (-not (Test-Path $SourcePath)) { Write-Err2 "找不到 SourcePath: $SourcePath"; exit 1 }
    Copy-Item $SourcePath $dest -Force
    Write-Ok "从 $SourcePath 复制到 $dest"
} else {
    if (-not $SourceUrl) { $SourceUrl = "$($ApiBase.TrimEnd('/'))/static/seat-mcp-server.py" }
    try {
        Invoke-WebRequest -Uri $SourceUrl -OutFile $dest -UseBasicParsing
        Write-Ok "从 $SourceUrl 下载到 $dest"
    } catch {
        Write-Err2 "下载失败：$($_.Exception.Message)"
        Write-Warn2 "兜底方案：在源电脑上手动 scp/共享盘把 scripts/seat-mcp-server/server.py 拷到 $dest，然后重跑本脚本时加 -SourcePath <本地路径>"
        exit 1
    }
}

Write-Step "Step 3/5 注册到 CLI"
$registered = @()

function Register-Claude {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $cmd) { Write-Warn2 "未检测到 claude CLI，跳过 Claude 注册"; return }
    & claude mcp remove seat-mcp 2>&1 | Out-Null
    $serverArg = $dest.Replace('\','/')
    & claude mcp add seat-mcp -- python $serverArg
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "已通过 'claude mcp add' 注册"
        $script:registered += "claude"
    } else {
        Write-Warn2 "claude mcp add 返回非 0，请手动检查"
    }
}

function Register-Codex {
    $cmd = Get-Command codex -ErrorAction SilentlyContinue
    if (-not $cmd) { Write-Warn2 "未检测到 codex CLI，跳过 Codex 注册"; return }
    $cfgDir = Join-Path $env:USERPROFILE ".codex"
    if (-not (Test-Path $cfgDir)) { New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null }
    $cfgPath = Join-Path $cfgDir "config.toml"
    $serverArg = $dest.Replace('\','/')
    $section = @"

[mcp_servers.seat-mcp]
command = "python"
args = ["$serverArg"]
"@
    if (Test-Path $cfgPath) {
        $existing = Get-Content $cfgPath -Raw
        if ($existing -match "(?m)^\[mcp_servers\.seat-mcp\]") {
            Write-Warn2 "$cfgPath 已包含 [mcp_servers.seat-mcp]，跳过（如要重置，请手动删后重跑）"
        } else {
            Add-Content -Path $cfgPath -Value $section -Encoding UTF8
            Write-Ok "追加到 $cfgPath"
            $script:registered += "codex"
        }
    } else {
        Set-Content -Path $cfgPath -Value $section.TrimStart() -Encoding UTF8
        Write-Ok "创建 $cfgPath"
        $script:registered += "codex"
    }
}

if ($CliTargets -in @("claude","both")) { Register-Claude }
if ($CliTargets -in @("codex","both"))  { Register-Codex }

if ($registered.Count -eq 0) {
    Write-Warn2 "没有任何 CLI 被注册。可能原因：CLI 都没装；或都已经注册过。后面 Step 5 仍会跑通。"
} else {
    Write-Ok "已注册：$($registered -join ', ')"
}

Write-Step "Step 4/5 写入 PLATFORM_API_BASE 用户级环境变量"
if ($SkipEnv) {
    Write-Warn2 "用户加了 -SkipEnv，跳过。但 watcher 需要从 env 拿 API_BASE，请确保以其他方式注入。"
} else {
    [Environment]::SetEnvironmentVariable("PLATFORM_API_BASE", $ApiBase, "User")
    $env:PLATFORM_API_BASE = $ApiBase
    Write-Ok "PLATFORM_API_BASE=$ApiBase（永久；新开 PowerShell 才生效，本进程已设）"
}

Write-Step "Step 5/5 自检：ping 平台 API"
try {
    $r = Invoke-WebRequest -Uri "$($ApiBase.TrimEnd('/'))/health" -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -eq 200) {
        Write-Ok "平台 $ApiBase/health 200 OK"
    } else {
        Write-Warn2 "/health 返回 $($r.StatusCode)，可能是路由不同；继续视为通"
    }
} catch {
    Write-Warn2 "无法访问 $ApiBase/health：$($_.Exception.Message)"
    Write-Warn2 "如果是局域网 IP，请检查：① 平台主机 8010 入站防火墙 ② 工位电脑能 ping 到主机 ③ 主机 API 服务在跑"
}

Write-Host ""
Write-Step "完成"
Write-Host "下一步：" -ForegroundColor White
Write-Host "  1. 在本电脑上启动 watcher（拉取本工位的 NPC 任务）：" -ForegroundColor White
Write-Host "       pwsh scripts/start-thread-watcher.ps1 -ProjectId <pid> -WorkstationId <wsid> -ApiBase $ApiBase" -ForegroundColor Gray
Write-Host "  2. NPC 在 CLI session 里就能调 seat-mcp 工具了；试着让它说一句：" -ForegroundColor White
Write-Host '       "调用 seat-mcp 的 list_peers 看看伙伴。"' -ForegroundColor Gray
Write-Host "  3. 故障排查见 $InstallDir 里随脚本同步过来的 README（如果有）；或源仓库 scripts/seat-mcp-server/README.md。" -ForegroundColor White
