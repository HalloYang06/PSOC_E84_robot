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

function powerShellQuoted(value: unknown) {
  return `'${text(value, "").replace(/'/g, "''")}'`;
}

export function buildRunnerScriptUrl(webBaseUrl: string, scriptName: string) {
  const base = text(webBaseUrl, "http://127.0.0.1:3000")
    .replace(/\/+$/, "")
    .replace(/:8010$/, ":3000")
    .replace(/:8000$/, ":3000");
  return `${base}/downloads/runner/${encodeURIComponent(scriptName)}`;
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
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const runnerName = `${text(node.label ?? node.name, nodeId)} Runner`;
  return buildPowerShellRunnerScriptCommand(serverUrl, "register-runner.ps1", [
    ["-Server", serverUrl],
    ["-PairingToken", pairingToken],
    ["-ComputerNodeId", nodeId],
    ["-RunnerName", runnerName],
    ["-RunnerId", runnerId],
  ]);
}

export function buildComputerOneClickConnectCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  pairingToken: string,
  runnerId: string,
) {
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const runnerName = `${text(node.label ?? node.name, nodeId)} Runner`;
  const workspaceRoot = text(node.git_root ?? node.workspace_root, "");
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
  return buildPowerShellRunnerScriptCommand(serverUrl, "connect-ai-collab-runner.ps1", args);
}

export function buildComputerRunnerWatchCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
  options: { executeProviderCli?: boolean; pollSeconds?: number | null } = {},
) {
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const runnerName = `${text(node.label ?? node.name, nodeId)} Runner`;
  const workspaceRoot = text(node.git_root ?? node.workspace_root, "");
  const args: Array<[string, unknown]> = [
    ["-Server", serverUrl],
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
  return buildPowerShellRunnerScriptCommand(serverUrl, "connect-ai-collab-runner.ps1", args);
}

export function buildComputerCodexThreadSyncCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
) {
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  return buildPowerShellRunnerScriptCommand(serverUrl, "sync-codex-session-threads.ps1", [
    ["-Server", serverUrl],
    ["-RunnerId", runnerId],
    ["-ProjectId", projectId],
    ["-ComputerNodeId", nodeId],
  ]);
}

export function buildComputerClaudeThreadSyncCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
) {
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const workspaceRoot = text(node.git_root ?? node.workspace_root, "");
  const args: Array<[string, unknown]> = [
    ["-Server", serverUrl],
    ["-RunnerId", runnerId],
    ["-ProjectId", projectId],
    ["-ComputerNodeId", nodeId],
  ];
  if (workspaceRoot) {
    args.push(["-WorkspaceRoot", workspaceRoot]);
  }
  return buildPowerShellRunnerScriptCommand(serverUrl, "sync-claude-session-threads.ps1", args);
}

export function buildComputerManualThreadSyncCommand(
  serverUrl: string,
  projectId: string,
  node: AnyRecord,
  runnerId: string,
) {
  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "computer");
  const nodeLabel = text(node.label ?? node.name, nodeId);
  const manualThreadId = `codex-${normalizeComputerRunnerSlug(nodeId)}-mainline`;
  const manualThreadName = `${nodeLabel} / Codex 主线程`;
  const cwd = text(node.git_root ?? node.workspace_root, "");
  const args: Array<[string, unknown]> = [
    ["-Server", serverUrl],
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
