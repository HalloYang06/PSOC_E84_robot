<#
.SYNOPSIS
  绑定一个项目线程（workstation）到本机一个可视终端：watcher 长跑、有指令就打印、调 claude/codex CLI、流式显示输出、回写平台。

.DESCRIPTION
  这是 MEMORY 里 project_npc_workstation_semantics 的"线程是工具"语义在本机的落地：
  一个项目线程 = 本机一个 watcher 终端，watcher 一直 poll 该线程的 inbox，
  收到指令就在当前终端打印「收到平台指令 / 正在调用 CLI / CLI 输出 / 已回写」。

  默认：API 在 http://127.0.0.1:8000；provider 自动从 adapter-config 解析；
  执行目录默认是仓库根目录（D:\ai合作产品）。

.PARAMETER ProjectId
  项目 id（如 proj_ai_collab）。可在 DB 表 projects 里查。

.PARAMETER WorkstationId
  线程 id，对应 project_thread_workstations.config_id（不是表 PK）。
  比如 proj_ai_collab 下的"前端工位"是 'ǰ��工位'（DB 中文 config_id）。

.PARAMETER ApiBase
  平台 API 根路径，默认 http://127.0.0.1:8000。

.PARAMETER Provider
  覆盖 adapter-config 里的 provider 解析，可填 claude/codex/qwen。

.PARAMETER ExecutorCwd
  执行 CLI 的工作目录。默认仓库根。

.PARAMETER PollSeconds
  轮询间隔秒数，默认 3。

.EXAMPLE
  .\start-thread-watcher.ps1 -ProjectId proj_ai_collab -WorkstationId 'frontend-thread'

  在当前终端绑定一个 watcher，看到这个线程的所有平台指令并实时执行。
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,

  [Parameter(Mandatory = $true)]
  [string]$WorkstationId,

  [string]$ApiBase = "http://127.0.0.1:8000",

  [ValidateSet("claude", "codex", "qwen", "")]
  [string]$Provider = "",

  [string]$ExecutorCwd = "",

  [double]$PollSeconds = 3.0,

  [switch]$SpawnWindow,

  [switch]$PersistentWindow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$adapter = Join-Path $repoRoot "scripts\platform-workstation-adapter.py"
if (-not (Test-Path -LiteralPath $adapter)) {
  Write-Host "找不到 $adapter" -ForegroundColor Red
  exit 2
}

if ([string]::IsNullOrWhiteSpace($ExecutorCwd)) {
  $ExecutorCwd = $repoRoot
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "项目线程 watcher 启动准备" -ForegroundColor Green
Write-Host "项目: $ProjectId" -ForegroundColor Yellow
Write-Host "线程: $WorkstationId" -ForegroundColor Yellow
Write-Host "API:  $ApiBase" -ForegroundColor Gray
Write-Host "执行目录: $ExecutorCwd" -ForegroundColor Gray
if ($Provider) { Write-Host "Provider 覆盖: $Provider" -ForegroundColor Gray }
Write-Host "轮询: 每 ${PollSeconds}s" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan

$pyArgs = @(
  $adapter,
  "--api-base", $ApiBase,
  "--project-id", $ProjectId,
  "--workstation-id", $WorkstationId,
  "--auto-ack",
  "--execute-provider-cli",
  "--executor-cwd", $ExecutorCwd,
  "--watch",
  "--poll-seconds", $PollSeconds
)
if ($Provider) {
  $pyArgs += @("--provider", $Provider)
}
if ($SpawnWindow) {
  $pyArgs += @("--spawn-window")
}
if ($PersistentWindow) {
  $pyArgs += @("--persistent-window")
}

# 不要把 stdout PIPE 走，让 adapter 的横幅 + claude 流式输出直接进当前终端
& python $pyArgs
# StrictMode 下，如果 python 直接抛 native 错误（如可执行不存在）$LASTEXITCODE 可能未初始化。
# 先 try 读取，失败时退 1 表示启动失败。
$exitCode = 0
try { $exitCode = [int]$LASTEXITCODE } catch { $exitCode = 1 }
exit $exitCode
