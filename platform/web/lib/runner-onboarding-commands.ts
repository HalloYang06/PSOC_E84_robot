// Onboarding command builders for runner / workstation 接入。
// 抽自 project-playable-shell.tsx 1653-1862,供主壳与 2d-upgrade 共享。

type AnyRecord = Record<string, any>;

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

export const DEFAULT_AUTOMATION_HEARTBEAT_SECONDS = 60;

export function normalizeAutomationHeartbeatSeconds(
  value: unknown,
  fallback = DEFAULT_AUTOMATION_HEARTBEAT_SECONDS,
) {
  const parsed = Number(value);
  const candidate = Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed) : fallback;
  return Math.min(3600, Math.max(15, candidate));
}

function adapterShellArg(value: unknown) {
  const raw = text(value, "");
  if (!raw) return "\"\"";
  if (/^[A-Za-z0-9_.:/-]+$/.test(raw)) return raw;
  return `"${raw.replace(/"/g, "\\\"")}"`;
}

function bashSingleQuoted(value: unknown) {
  return `'${text(value, "").replace(/'/g, `'\\''`)}'`;
}

function powerShellQuoted(value: unknown) {
  return `'${text(value, "").replace(/'/g, "''")}'`;
}

function powerShellHereString(value: unknown) {
  return `@'\n${text(value, "").replace(/'@/g, "' + '@' + '")}\n'@`;
}

function powerShellEncodedCommand(value: unknown) {
  const raw = text(value, "");
  if (typeof Buffer !== "undefined") {
    return Buffer.from(raw, "utf16le").toString("base64");
  }
  let binary = "";
  for (let index = 0; index < raw.length; index += 1) {
    const code = raw.charCodeAt(index);
    binary += String.fromCharCode(code & 0xff, code >> 8);
  }
  return btoa(binary);
}

function bashDoubleQuoted(value: unknown) {
  return `"${text(value, "").replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\$/g, "\\$").replace(/`/g, "\\`")}"`;
}

function bashSingleLine(value: unknown) {
  return text(value, "").replace(/\r?\n/g, " ").replace(/\s+/g, " ").trim();
}

export function buildRunnerScriptUrl(webBaseUrl: string, scriptName: string) {
  const base = text(webBaseUrl, "http://127.0.0.1:3000")
    .replace(/\/+$/, "")
    .replace(/:8010$/, ":3000")
    .replace(/:8011$/, ":3001")
    .replace(/:8000$/, ":3000");
  return `${base}/downloads/runner/${encodeURIComponent(scriptName)}`;
}

export function buildRunnerApiBaseUrl(serverUrl: string) {
  return text(serverUrl, "http://127.0.0.1:8010")
    .replace(/\/+$/, "")
    .replace(/:3000$/, ":8010")
    .replace(/:3001$/, ":8011")
    .replace(/:8000$/, ":8010");
}

function buildRunnerScriptBootstrapCommand(webBaseUrl: string, scriptName: string) {
  const scriptUrl = buildRunnerScriptUrl(webBaseUrl, scriptName);
  return [
    `New-Item -ItemType Directory -Force -Path .\\ai-collab-runner | Out-Null`,
    `Invoke-WebRequest -UseBasicParsing -Uri ${powerShellQuoted(scriptUrl)} -OutFile ${powerShellQuoted(`.\\ai-collab-runner\\${scriptName}`)}`,
  ].join("; ");
}

function buildPowerShellRunnerScriptCommand(
  webBaseUrl: string,
  scriptName: string,
  args: Array<[string, unknown]>,
) {
  const argText = args
    .map(([name, value]) => {
      if (value === true) return name;
      if (value === false || value === null || value === undefined) return "";
      return `${name} ${powerShellQuoted(value)}`;
    })
    .filter(Boolean)
    .join(" ");
  const scriptPath = `.\\ai-collab-runner\\${scriptName}`;
  const commandBody = `& { ${buildRunnerScriptBootstrapCommand(webBaseUrl, scriptName)}; & ${powerShellQuoted(scriptPath)} ${argText} }`;
  return [
    "powershell",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    adapterShellArg(commandBody),
  ].join(" ");
}

function buildBashRunnerScriptCommand(
  webBaseUrl: string,
  scriptName: string,
  args: Array<[string, unknown]>,
) {
  const scriptUrl = buildRunnerScriptUrl(webBaseUrl, scriptName);
  const argText = args
    .map(([name, value]) => {
      if (value === true) return name;
      if (value === false || value === null || value === undefined) return "";
      return `${name} ${bashSingleQuoted(value)}`;
    })
    .filter(Boolean)
    .join(" ");
  const scriptPath = `./ai-collab-runner/${scriptName}`;
  return [
    "mkdir -p ./ai-collab-runner",
    `curl -fsSL ${bashSingleQuoted(scriptUrl)} -o ${bashSingleQuoted(scriptPath)}`,
    `chmod +x ${bashSingleQuoted(scriptPath)}`,
    `${scriptPath} ${argText}`.trim(),
  ].join(" && ");
}

export function buildWorkstationAdapterCommand(
  projectId: string,
  workstationId: string,
  token?: string | null,
  serverUrl = "http://127.0.0.1:8010",
) {
  const adapterScript = "platform-workstation-adapter.py";
  const providerExecutorScript = "platform-provider-executor.py";
  const adapterScriptPath = `.\\ai-collab-runner\\${adapterScript}`;
  const providerExecutorPath = `.\\ai-collab-runner\\${providerExecutorScript}`;
  const command = [
    "python",
    adapterScriptPath,
    "--api-base",
    adapterShellArg(serverUrl),
    "--project-id",
    adapterShellArg(projectId),
    "--workstation-id",
    adapterShellArg(workstationId),
    "--auto-ack",
  ];
  if (text(token, "")) {
    command.push("--token", adapterShellArg(token));
  }
  const commandBody = [
    "New-Item -ItemType Directory -Force -Path .\\ai-collab-runner | Out-Null",
    `Invoke-WebRequest -UseBasicParsing -Uri ${powerShellQuoted(buildRunnerScriptUrl(serverUrl, adapterScript))} -OutFile ${powerShellQuoted(adapterScriptPath)}`,
    `Invoke-WebRequest -UseBasicParsing -Uri ${powerShellQuoted(buildRunnerScriptUrl(serverUrl, providerExecutorScript))} -OutFile ${powerShellQuoted(providerExecutorPath)}`,
    command.join(" "),
  ].join("; ");
  return [
    "powershell",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    adapterShellArg(`& { ${commandBody} }`),
  ].join(" ");
}

export function buildWorkstationAdapterBashCommand(
  projectId: string,
  workstationId: string,
  token?: string | null,
  serverUrl = "http://127.0.0.1:8010",
) {
  const adapterScript = "platform-workstation-adapter.py";
  const providerExecutorScript = "platform-provider-executor.py";
  const adapterScriptPath = "./ai-collab-runner/platform-workstation-adapter.py";
  const providerExecutorPath = "./ai-collab-runner/platform-provider-executor.py";
  const adapterUrl = buildRunnerScriptUrl(serverUrl, adapterScript);
  const providerUrl = buildRunnerScriptUrl(serverUrl, providerExecutorScript);
  const command = [
    "python3",
    bashSingleQuoted(adapterScriptPath),
    "--api-base",
    bashSingleQuoted(serverUrl),
    "--project-id",
    bashSingleQuoted(projectId),
    "--workstation-id",
    bashSingleQuoted(workstationId),
    "--auto-ack",
  ];
  if (text(token, "")) {
    command.push("--token", bashSingleQuoted(token));
  }
  return [
    "mkdir -p ./ai-collab-runner",
    `curl -fsSL ${bashSingleQuoted(adapterUrl)} -o ${bashSingleQuoted(adapterScriptPath)}`,
    `curl -fsSL ${bashSingleQuoted(providerUrl)} -o ${bashSingleQuoted(providerExecutorPath)}`,
    command.join(" "),
  ].join(" && ");
}

export function normalizeComputerRunnerSlug(value: unknown) {
  const raw = text(value, "").toLowerCase();
  const slug = raw.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return slug || "computer";
}

export function suggestedComputerRunnerId(node: AnyRecord) {
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const slug = normalizeComputerRunnerSlug(nodeId);
  return slug.startsWith("runner-") ? slug : `runner-${slug}`;
}

export function buildComputerRunnerRegisterCommand(
  serverUrl: string,
  node: AnyRecord,
  pairingToken: string,
  runnerId: string,
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const runnerName = `${text(node.label ?? node.name, nodeId)} Runner`;
  return buildPowerShellRunnerScriptCommand(serverUrl, "register-runner.ps1", [
    ["-Server", apiBaseUrl],
    ["-PairingToken", pairingToken],
    ["-ComputerNodeId", nodeId],
    ["-RunnerName", runnerName],
    ["-RunnerId", runnerId],
  ]);
}

export function buildComputerRunnerRegisterBashCommand(
  serverUrl: string,
  node: AnyRecord,
  pairingToken: string,
  runnerId: string,
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const runnerName = `${text(node.label ?? node.name, nodeId)} Runner`;
  return buildBashRunnerScriptCommand(serverUrl, "register-runner.sh", [
    ["--server", apiBaseUrl],
    ["--pairing-token", pairingToken],
    ["--computer-node-id", nodeId],
    ["--runner-name", runnerName],
    ["--runner-id", runnerId],
  ]);
}

export function buildComputerOneClickConnectCommand(
  webBaseUrl: string,
  projectId: string,
  node: AnyRecord,
  pairingToken: string,
  runnerId: string,
  options: { watch?: boolean; executeProviderCli?: boolean; serverUrl?: string; hardwareAccess?: boolean; deviceDataRepo?: string } = {},
) {
  const serverUrl = buildRunnerApiBaseUrl(text(options.serverUrl, webBaseUrl));
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const runnerName = `${text(node.label ?? node.name, nodeId)} Runner`;
  const workspaceRoot = text(node.git_root ?? node.workspace_root, "");
  const deviceDataRepo = text(options.deviceDataRepo ?? node.device_data_repo ?? node.device_data_repository ?? "", "");
  const args: Array<[string, unknown]> = [
    ["-Server", serverUrl],
    ["-PairingToken", pairingToken],
    ["-ComputerNodeId", nodeId],
    ["-RunnerName", runnerName],
    ["-RunnerId", runnerId],
    ["-ProjectId", projectId],
  ];
  if (workspaceRoot) {
    args.push(["-WorkspaceRoot", workspaceRoot]);
  }
  if (options.watch) {
    args.push(["-Watch", true]);
  }
  if (options.hardwareAccess) {
    args.push(["-HardwareAccess", true]);
  }
  if (deviceDataRepo) {
    args.push(["-DeviceDataRepo", deviceDataRepo]);
  }
  if (options.executeProviderCli) {
    args.push(["-WatchExecuteProviderCli", true]);
  }
  return buildPowerShellRunnerScriptCommand(webBaseUrl, "connect-ai-collab-runner.ps1", args);
}

export function buildComputerOneClickConnectBashCommand(
  webBaseUrl: string,
  projectId: string,
  node: AnyRecord,
  pairingToken: string,
  runnerId: string,
  options: { watch?: boolean; executeProviderCli?: boolean; serverUrl?: string; hardwareAccess?: boolean; deviceDataRepo?: string } = {},
) {
  const serverUrl = buildRunnerApiBaseUrl(text(options.serverUrl, webBaseUrl));
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const runnerName = `${text(node.label ?? node.name, nodeId)} Runner`;
  const workspaceRoot = text(node.git_root ?? node.workspace_root, "");
  const deviceDataRepo = text(options.deviceDataRepo ?? node.device_data_repo ?? node.device_data_repository ?? "", "");
  const args: Array<[string, unknown]> = [
    ["--server", serverUrl],
    ["--pairing-token", pairingToken],
    ["--computer-node-id", nodeId],
    ["--runner-name", runnerName],
    ["--runner-id", runnerId],
    ["--project-id", projectId],
  ];
  if (workspaceRoot) {
    args.push(["--workspace-root", workspaceRoot]);
  }
  if (options.watch) {
    args.push(["--watch", true]);
  }
  if (options.hardwareAccess) {
    args.push(["--hardware-access", true]);
  }
  if (deviceDataRepo) {
    args.push(["--device-data-repo", deviceDataRepo]);
  }
  if (options.executeProviderCli) {
    args.push(["--watch-execute-provider-cli", true]);
  }
  return buildBashRunnerScriptCommand(webBaseUrl, "connect-ai-collab-runner.sh", args);
}

export function buildComputerRunnerWatchCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
  options: { executeProviderCli?: boolean; pollSeconds?: number | null } = {},
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const runnerName = `${text(node.label ?? node.name, nodeId)} Runner`;
  const workspaceRoot = text(node.git_root ?? node.workspace_root, "");
  const deviceDataRepo = text(node.device_data_repo ?? node.device_data_repository ?? "", "");
  const args: Array<[string, unknown]> = [
    ["-Server", apiBaseUrl],
    ["-PairingToken", "already-bound-runner-reuse"],
    ["-ComputerNodeId", nodeId],
    ["-RunnerName", runnerName],
    ["-RunnerId", runnerId],
    ["-ProjectId", projectId],
    ["-SkipCodex", true],
    ["-SkipClaude", true],
    ["-Watch", true],
    ["-WatchPollSeconds", normalizeAutomationHeartbeatSeconds(options.pollSeconds)],
  ];
  if (options.executeProviderCli) {
    args.push(["-WatchExecuteProviderCli", true]);
  }
  if (workspaceRoot) {
    args.push(["-WorkspaceRoot", workspaceRoot]);
  }
  if (deviceDataRepo) {
    args.push(["-DeviceDataRepo", deviceDataRepo]);
  }
  return buildPowerShellRunnerScriptCommand(serverUrl, "connect-ai-collab-runner.ps1", args);
}

export function buildComputerRunnerWatchBashCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
  options: { executeProviderCli?: boolean; pollSeconds?: number | null } = {},
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const runnerName = `${text(node.label ?? node.name, nodeId)} Runner`;
  const workspaceRoot = text(node.git_root ?? node.workspace_root, "");
  const deviceDataRepo = text(node.device_data_repo ?? node.device_data_repository ?? "", "");
  const args: Array<[string, unknown]> = [
    ["--server", apiBaseUrl],
    ["--pairing-token", "already-bound-runner-reuse"],
    ["--computer-node-id", nodeId],
    ["--runner-name", runnerName],
    ["--runner-id", runnerId],
    ["--project-id", projectId],
    ["--skip-codex", true],
    ["--skip-claude", true],
    ["--watch", true],
    ["--watch-poll-seconds", normalizeAutomationHeartbeatSeconds(options.pollSeconds)],
  ];
  if (options.executeProviderCli) {
    args.push(["--watch-execute-provider-cli", true]);
  }
  if (workspaceRoot) {
    args.push(["--workspace-root", workspaceRoot]);
  }
  if (deviceDataRepo) {
    args.push(["--device-data-repo", deviceDataRepo]);
  }
  return buildBashRunnerScriptCommand(serverUrl, "connect-ai-collab-runner.sh", args);
}

export function buildComputerRunnerWatchServiceCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
  options: { executeProviderCli?: boolean; pollSeconds?: number | null } = {},
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const webBaseUrl = buildRunnerScriptUrl(serverUrl, "connect-ai-collab-runner.ps1").replace(/\/downloads\/runner\/connect-ai-collab-runner\.ps1$/, "");
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const runnerName = `${text(node.label ?? node.name, nodeId)} Runner`;
  const workspaceRoot = text(node.git_root ?? node.workspace_root, "");
  const slug = normalizeComputerRunnerSlug(`${nodeId}-${runnerId}`);
  const taskName = `AI Collab Runner ${slug}`;
  const argLines = [
    `  -Server ${powerShellQuoted(apiBaseUrl)}`,
    `  -WebBaseUrl ${powerShellQuoted(webBaseUrl)}`,
    `  -PairingToken ${powerShellQuoted("already-bound-runner-reuse")}`,
    `  -ComputerNodeId ${powerShellQuoted(nodeId)}`,
    `  -RunnerName ${powerShellQuoted(runnerName)}`,
    `  -RunnerId ${powerShellQuoted(runnerId)}`,
    `  -ProjectId ${powerShellQuoted(projectId)}`,
    "  -SkipCodex",
    "  -SkipClaude",
    "  -Watch",
    `  -WatchPollSeconds ${normalizeAutomationHeartbeatSeconds(options.pollSeconds)}`,
  ];
  if (options.executeProviderCli) {
    argLines.push("  -WatchExecuteProviderCli");
  }
  if (workspaceRoot) {
    argLines.push(`  -WorkspaceRoot ${powerShellQuoted(workspaceRoot)}`);
  }
  const scriptBody = [
    `$ErrorActionPreference = "Stop"`,
    `$RunnerDir = Join-Path $env:USERPROFILE "ai-collab-runner"`,
    `New-Item -ItemType Directory -Force -Path $RunnerDir | Out-Null`,
    `$LogDir = Join-Path $RunnerDir "logs"`,
    `New-Item -ItemType Directory -Force -Path $LogDir | Out-Null`,
    `$Script = Join-Path $RunnerDir "connect-ai-collab-runner.ps1"`,
    `Invoke-WebRequest -UseBasicParsing -Uri ${powerShellQuoted(buildRunnerScriptUrl(serverUrl, "connect-ai-collab-runner.ps1"))} -OutFile $Script`,
    `Set-Location $env:USERPROFILE`,
    `& $Script \``,
    argLines.join(" `\n"),
  ].join("\n");
  const commandBody = [
    `$RunnerDir = Join-Path $env:USERPROFILE "ai-collab-runner"`,
    `New-Item -ItemType Directory -Force -Path $RunnerDir | Out-Null`,
    `$WatchScript = Join-Path $RunnerDir "runner-watch-${slug}.ps1"`,
    `Set-Content -Encoding UTF8 -LiteralPath $WatchScript -Value ${powerShellHereString(scriptBody)}`,
    `$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -File " + $WatchScript)`,
    `$Trigger = New-ScheduledTaskTrigger -AtLogOn`,
    `$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)`,
    `Register-ScheduledTask -TaskName ${powerShellQuoted(taskName)} -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null`,
    `Start-ScheduledTask -TaskName ${powerShellQuoted(taskName)}`,
    `Write-Host "AI 协作平台后台守护已启动。任务名：${taskName}；日志目录：$RunnerDir\\logs"`,
  ].join("; ");
  return [
    "powershell",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-EncodedCommand",
    powerShellEncodedCommand(`& { ${commandBody} }`),
  ].join(" ");
}

export function buildComputerRunnerWatchServiceBashCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
  options: { executeProviderCli?: boolean; pollSeconds?: number | null } = {},
) {
  const watchCommand = bashSingleLine(buildComputerRunnerWatchBashCommand(serverUrl, projectId, node, runnerId, options));
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const slug = normalizeComputerRunnerSlug(`${nodeId}-${runnerId}`);
  const serviceName = `ai-collab-runner-${slug}.service`;
  const serviceBody = [
    "[Unit]",
    `Description=AI Collab Runner ${slug}`,
    "After=network-online.target",
    "",
    "[Service]",
    "Type=simple",
    "WorkingDirectory=%h",
    `ExecStart=/usr/bin/env bash -lc ${bashDoubleQuoted(watchCommand)}`,
    "Restart=always",
    "RestartSec=5",
    "",
    "[Install]",
    "WantedBy=default.target",
  ].join("\n");
  const fallback = `mkdir -p "$HOME/ai-collab-runner/logs" && nohup bash -lc ${bashSingleQuoted(watchCommand)} >> "$HOME/ai-collab-runner/logs/runner-watch-${slug}.log" 2>&1 & echo "AI 协作平台后台守护已用 nohup 启动；日志：$HOME/ai-collab-runner/logs/runner-watch-${slug}.log"`;
  return [
    `mkdir -p "$HOME/.config/systemd/user" "$HOME/ai-collab-runner/logs"`,
    `cat > "$HOME/.config/systemd/user/${serviceName}" <<'AI_COLLAB_RUNNER_SERVICE'\n${serviceBody}\nAI_COLLAB_RUNNER_SERVICE`,
    `if command -v loginctl >/dev/null 2>&1; then loginctl enable-linger "$USER" >/dev/null 2>&1 || true; fi`,
    `if command -v systemctl >/dev/null 2>&1 && systemctl --user daemon-reload >/dev/null 2>&1; then systemctl --user enable --now ${bashSingleQuoted(serviceName)} && echo "AI 协作平台后台守护已启动：${serviceName}"; else ${fallback}; fi`,
  ].join(" && ");
}

export function buildComputerCodexThreadSyncCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  return buildPowerShellRunnerScriptCommand(serverUrl, "sync-codex-session-threads.ps1", [
    ["-Server", apiBaseUrl],
    ["-RunnerId", runnerId],
    ["-ProjectId", projectId],
    ["-ComputerNodeId", nodeId],
  ]);
}

export function buildComputerCodexThreadSyncBashCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  return buildBashRunnerScriptCommand(serverUrl, "sync-codex-session-threads.sh", [
    ["--server", apiBaseUrl],
    ["--runner-id", runnerId],
    ["--project-id", projectId],
    ["--computer-node-id", nodeId],
  ]);
}

export function buildComputerClaudeThreadSyncCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const workspaceRoot = text(node.git_root ?? node.workspace_root, "");
  const args: Array<[string, unknown]> = [
    ["-Server", apiBaseUrl],
    ["-RunnerId", runnerId],
    ["-ProjectId", projectId],
    ["-ComputerNodeId", nodeId],
  ];
  if (workspaceRoot) {
    args.push(["-WorkspaceRoot", workspaceRoot]);
  }
  return buildPowerShellRunnerScriptCommand(serverUrl, "sync-claude-session-threads.ps1", args);
}

export function buildComputerClaudeThreadSyncBashCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const workspaceRoot = text(node.git_root ?? node.workspace_root, "");
  const args: Array<[string, unknown]> = [
    ["--server", apiBaseUrl],
    ["--runner-id", runnerId],
    ["--project-id", projectId],
    ["--computer-node-id", nodeId],
  ];
  if (workspaceRoot) {
    args.push(["--workspace-root", workspaceRoot]);
  }
  return buildBashRunnerScriptCommand(serverUrl, "sync-claude-session-threads.sh", args);
}

export function buildComputerManualThreadSyncCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const nodeLabel = text(node.label ?? node.name, nodeId);
  const manualThreadId = `codex-${normalizeComputerRunnerSlug(nodeId)}-mainline`;
  const manualThreadName = `${nodeLabel} / Codex 主线程`;
  const cwd = text(node.git_root ?? node.workspace_root, "");
  const args: Array<[string, unknown]> = [
    ["-Server", apiBaseUrl],
    ["-RunnerId", runnerId],
    ["-ProjectId", projectId],
    ["-ComputerNodeId", nodeId],
    ["-ThreadId", manualThreadId],
    ["-ThreadName", manualThreadName],
  ];
  if (cwd) {
    args.push(["-Cwd", cwd]);
  }
  return buildPowerShellRunnerScriptCommand(serverUrl, "sync-runner-threads.ps1", args);
}

export function buildComputerManualThreadSyncBashCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
) {
  const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const nodeLabel = text(node.label ?? node.name, nodeId);
  const manualThreadId = `codex-${normalizeComputerRunnerSlug(nodeId)}-mainline`;
  const manualThreadName = `${nodeLabel} / Codex 主线程`;
  const cwd = text(node.git_root ?? node.workspace_root, "");
  const args: Array<[string, unknown]> = [
    ["--server", apiBaseUrl],
    ["--runner-id", runnerId],
    ["--project-id", projectId],
    ["--computer-node-id", nodeId],
    ["--thread-id", manualThreadId],
    ["--thread-name", manualThreadName],
  ];
  if (cwd) {
    args.push(["--cwd", cwd]);
  }
  return buildBashRunnerScriptCommand(serverUrl, "sync-runner-threads.sh", args);
}
