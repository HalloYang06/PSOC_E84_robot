import { execFile, spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync, statSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { loadLocalClaudeWorkstations } from "./local-claude-sessions";

type AnyRecord = Record<string, unknown>;
const execFileAsync = promisify(execFile);

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

// 把席位名清洗成文件系统安全的slug
// 处理：中文/特殊字符 (`/` `\` ` ` `(` `)` 等)
export function slugSeatName(seatName: string): string {
  const trimmed = String(seatName ?? "").trim();
  if (!trimmed) return "claude-seat";
  // 替换所有路径分隔符和文件系统不友好字符
  const slug = trimmed
    .replace(/[\\/:*?"<>|]/g, "_") // Windows禁止字符
    .replace(/\s+/g, "_") // 空格
    .replace(/[()[\]{}]/g, "_") // 括号
    .replace(/_+/g, "_") // 连续下划线合并
    .replace(/^_+|_+$/g, ""); // 首尾下划线
  return slug || "claude-seat";
}

function workspaceRoot() {
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
}

function registryPath() {
  return path.join(workspaceRoot(), "artifacts", "claude-seat-registry.json");
}

function startClaudeSeatScriptPath() {
  return path.join(workspaceRoot(), "scripts", "start-claude-seat.ps1");
}

function claudeCliPath() {
  const appData = text(process.env.APPDATA, "");
  if (appData) {
    return path.join(appData, "npm", "claude.cmd");
  }
  return "claude.cmd";
}

function deriveClaudeSessionId(sourceWorkstationId: unknown) {
  const raw = text(sourceWorkstationId, "");
  if (!raw) return null;
  if (raw.toLowerCase().startsWith("claude-session-")) {
    const stripped = raw.slice("claude-session-".length).trim();
    return stripped || null;
  }
  return raw || null;
}

function parseIso(value: unknown) {
  const raw = text(value, "");
  if (!raw) return Number.NaN;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function ageMinutesFromIso(value: unknown) {
  const parsed = parseIso(value);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, Math.floor((Date.now() - parsed) / 60000));
}

async function readRegistry() {
  try {
    const raw = await fs.readFile(registryPath(), "utf8");
    const parsed = JSON.parse(raw.replace(/^\uFEFF/, "")) as AnyRecord;
    const seats = Array.isArray(parsed?.seats) ? parsed.seats : [];
    return seats.filter((item): item is AnyRecord => Boolean(item && typeof item === "object"));
  } catch {
    return [] as AnyRecord[];
  }
}

async function writeRegistry(entries: AnyRecord[], targetPath = registryPath()) {
  await fs.mkdir(path.dirname(targetPath), { recursive: true });
  await fs.writeFile(
    targetPath,
    JSON.stringify(
      {
        updated_at: new Date().toISOString(),
        seats: entries,
      },
      null,
      2,
    ),
    "utf8",
  );
}

function matchRegistryEntry(entries: AnyRecord[], seatName: string, sessionId: string) {
  return (
    entries.find((item) => text(item.seat_name, "") === seatName || text(item.session_id, "") === sessionId) ?? null
  );
}

function classifyClaudeLaunchFailure(error: unknown) {
  const fallback = {
    code: "CLAUDE_LAUNCH_FAILED",
    summary: "Claude 会话启动失败",
    blockedByEnvironment: false,
  };
  const details = [
    error instanceof Error ? error.message : "",
    text((error as AnyRecord | null)?.stderr, ""),
    text((error as AnyRecord | null)?.stdout, ""),
    text((error as AnyRecord | null)?.code, ""),
  ]
    .filter(Boolean)
    .join("\n");
  if (!details) return fallback;
  if (details.includes("uv_spawn 'C:\\WINDOWS\\System32\\reg.exe'") && details.includes("EPERM")) {
    return {
      code: "CLAUDE_AUTO_WAKE_BLOCKED",
      summary: "当前环境阻止 Claude 自启（reg.exe 权限受限）",
      blockedByEnvironment: true,
    };
  }
  if (/timed out|ETIMEDOUT/i.test(details)) {
    return {
      code: "CLAUDE_LAUNCH_TIMEOUT",
      summary: "Claude 会话启动超时",
      blockedByEnvironment: false,
    };
  }
  if (/not recognized|ENOENT/i.test(details)) {
    return {
      code: "CLAUDE_CLI_MISSING",
      summary: "本机没有找到 Claude CLI",
      blockedByEnvironment: true,
    };
  }
  return {
    code: text((error as AnyRecord | null)?.code, fallback.code) || fallback.code,
    summary: fallback.summary,
    blockedByEnvironment: false,
  };
}

async function probeClaudeSessionWake(options: { threadId: string; model?: string | null }) {
  const args = [
    "--bare",
    "--no-chrome",
    "-p",
    "--output-format",
    "json",
    "--session-id",
    options.threadId,
    "--model",
    text(options.model, "sonnet") || "sonnet",
    "Reply with exactly OK.",
  ];
  try {
    await execFileAsync(claudeCliPath(), args, {
      cwd: workspaceRoot(),
      windowsHide: true,
      timeout: 30000,
      maxBuffer: 1024 * 1024,
    });
    return {
      status: "ok",
      blockedByEnvironment: false,
      errorCode: null,
      errorSummary: null,
    };
  } catch (error) {
    const classified = classifyClaudeLaunchFailure(error);
    return {
      status: classified.blockedByEnvironment ? "blocked" : "failed",
      blockedByEnvironment: classified.blockedByEnvironment,
      errorCode: classified.code,
      errorSummary: classified.summary,
    };
  }
}

export type ClaudeSeatAutonomyStatus = {
  seatId: string;
  seatName: string;
  sourceWorkstationId: string | null;
  threadId: string | null;
  consumerScriptPath: string | null;
  consumerScriptExists: boolean;
  consumerStatePath: string | null;
  consumerStateExists: boolean;
  consumerStateUpdatedAt: string | null;
  consumerStateAgeMinutes: number | null;
  consumerStateStale: boolean;
  automationId: string | null;
  automationName: string | null;
  automationStatus: string | null;
  automationUpdatedAt: string | null;
  heartbeatMissing: boolean;
  autonomyReady: boolean;
  bridgeHealthLabel: string;
  autonomyLabel: string;
  registryPath: string;
  sessionSeen: boolean;
  sessionRegistered: boolean;
  sessionStatus: string | null;
  lastLaunchProbeAt: string | null;
  lastLaunchProbeStatus: string | null;
  lastLaunchErrorCode: string | null;
  lastLaunchErrorSummary: string | null;
  sessionLaunchBlocked: boolean;
};

export async function readClaudeSeatAutonomyStatus(options: {
  seatId: string;
  seatName: string;
  sourceWorkstationId?: string | null;
}) {
  const sourceWorkstationId = text(options.sourceWorkstationId, "") || null;
  const threadId = deriveClaudeSessionId(sourceWorkstationId);
  const registryFile = registryPath();
  if (!sourceWorkstationId || !threadId) {
    return {
      seatId: options.seatId,
      seatName: options.seatName,
      sourceWorkstationId,
      threadId,
      consumerScriptPath: null,
      consumerScriptExists: false,
      consumerStatePath: null,
      consumerStateExists: false,
      consumerStateUpdatedAt: null,
      consumerStateAgeMinutes: null,
      consumerStateStale: false,
      automationId: null,
      automationName: null,
      automationStatus: null,
      automationUpdatedAt: null,
      heartbeatMissing: false,
      autonomyReady: false,
      bridgeHealthLabel: "bind Claude session",
      autonomyLabel: "bind Claude session",
      registryPath: registryFile,
      sessionSeen: false,
      sessionRegistered: false,
      sessionStatus: null,
      lastLaunchProbeAt: null,
      lastLaunchProbeStatus: null,
      lastLaunchErrorCode: null,
      lastLaunchErrorSummary: null,
      sessionLaunchBlocked: false,
    } satisfies ClaudeSeatAutonomyStatus;
  }

  const [sessions, registrySeats] = await Promise.all([
    loadLocalClaudeWorkstations({ cwdFilter: workspaceRoot(), limit: 50 }),
    readRegistry(),
  ]);
  const workstationId = `claude-session-${threadId}`;
  const session = sessions.find((item) => text(item.workstation_id, "") === workstationId) ?? null;
  const registryEntry =
    registrySeats.find((item) => text(item.session_id, "") === threadId && text(item.seat_name, "") === options.seatName) ?? null;
  const sessionUpdatedAt = text(session?.updated_at, "") || null;
  const sessionAgeMinutes = ageMinutesFromIso(sessionUpdatedAt);
  const sessionStatus = text(session?.status, "") || null;
  const sessionSeen = Boolean(session);
  const sessionRegistered = Boolean(registryEntry);
  const sessionIdle = sessionStatus === "idle";
  const sessionStale = sessionStatus === "stale";
  const launchProbeStatus = text(registryEntry?.launch_probe_status, "") || null;
  const launchErrorCode = text(registryEntry?.launch_error_code, "") || null;
  const launchErrorSummary = text(registryEntry?.launch_error_summary, "") || null;
  const launchProbeAt = text(registryEntry?.launch_probe_at, "") || null;
  const sessionLaunchBlocked = launchProbeStatus === "blocked";
  const sessionNeedsWake = sessionIdle || sessionStale;
  const bridgeHealthLabel = !sessionSeen
    ? "missing Claude session"
    : !sessionRegistered
      ? "missing Claude registration"
      : sessionNeedsWake && sessionLaunchBlocked
        ? "Claude auto-wake blocked"
        : sessionStale
        ? "Claude session stale"
        : sessionIdle
          ? "Claude session idle"
          : "Claude session ready";
  const autonomyReady =
    sessionSeen && sessionRegistered && (!sessionNeedsWake || launchProbeStatus === "ok");

  return {
    seatId: options.seatId,
    seatName: options.seatName,
    sourceWorkstationId,
    threadId,
    consumerScriptPath: null,
    consumerScriptExists: false,
    consumerStatePath: null,
    consumerStateExists: false,
    consumerStateUpdatedAt: sessionUpdatedAt,
    consumerStateAgeMinutes: sessionAgeMinutes,
    consumerStateStale: sessionStale,
    automationId: null,
    automationName: null,
    automationStatus: null,
    automationUpdatedAt: null,
    heartbeatMissing: false,
    autonomyReady,
    bridgeHealthLabel,
    autonomyLabel: bridgeHealthLabel,
    registryPath: registryFile,
    sessionSeen,
    sessionRegistered,
    sessionStatus,
    lastLaunchProbeAt: launchProbeAt,
    lastLaunchProbeStatus: launchProbeStatus,
    lastLaunchErrorCode: launchErrorCode,
    lastLaunchErrorSummary: launchErrorSummary,
    sessionLaunchBlocked,
  } satisfies ClaudeSeatAutonomyStatus;
}

export async function loadClaudeSeatAutonomyStatuses(
  seats: Array<{ seatId: string; seatName: string; sourceWorkstationId?: string | null }>,
) {
  const records = await Promise.all(
    seats.map((seat) =>
      readClaudeSeatAutonomyStatus({
        seatId: seat.seatId,
        seatName: seat.seatName,
        sourceWorkstationId: seat.sourceWorkstationId,
      }),
    ),
  );
  return Object.fromEntries(records.map((record) => [record.seatId, record] as const));
}

export async function ensureClaudeSeatSessionRegistration(options: {
  seatName: string;
  sourceWorkstationId?: string | null;
  model?: string | null;
}) {
  const threadId = deriveClaudeSessionId(options.sourceWorkstationId);
  if (!threadId) return null;
  const registryFile = registryPath();
  const entries = await readRegistry();
  const now = new Date().toISOString();
  const existing = matchRegistryEntry(entries, options.seatName, threadId);
  const nextEntry = {
    ...(existing ?? {}),
    seat_name: options.seatName,
    seat_slug: options.seatName.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "claude-seat",
    provider: "claude",
    session_id: threadId,
    display_name: `Claude NPC / ${options.seatName}`,
    project_root: workspaceRoot(),
    model: text(options.model, "") || null,
    launched_at: now,
    updated_at: now,
  } satisfies AnyRecord;
  const deduped = entries.filter((item) => item !== existing);
  await writeRegistry([...deduped, nextEntry], registryFile);
  return {
    sessionId: threadId,
    registryPath: registryFile,
  };
}

export async function launchClaudeSeatSession(options: {
  seatName: string;
  sourceWorkstationId?: string | null;
  model?: string | null;
  registerOnly?: boolean;
}) {
  const threadId = deriveClaudeSessionId(options.sourceWorkstationId);
  if (!threadId) return null;

  const args = [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    startClaudeSeatScriptPath(),
    "-SeatName",
    options.seatName,
    "-ProjectRoot",
    workspaceRoot(),
    "-SessionId",
    threadId,
  ];
  const model = text(options.model, "");
  if (model) {
    args.push("-Model", model);
  }
  if (options.registerOnly) {
    args.push("-RegisterOnly");
  }

  let launched = false;
  let registerOnly = Boolean(options.registerOnly);
  let resolvedRegistryPath = registryPath();
  let launcherErrorSummary: string | null = null;
  try {
    const { stdout } = await execFileAsync("powershell.exe", args, {
      cwd: workspaceRoot(),
      windowsHide: true,
      maxBuffer: 1024 * 1024,
    });
    const lines = text(stdout, "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const payloadLine = lines.at(-1);
    let parsed: AnyRecord = {};
    if (payloadLine) {
      try {
        parsed = JSON.parse(payloadLine) as AnyRecord;
      } catch {
        parsed = {};
      }
    }
    launched = Boolean(parsed.launched);
    registerOnly = Boolean(parsed.register_only);
    resolvedRegistryPath = text(parsed.registry_path, registryPath()) || registryPath();
  } catch (error) {
    launcherErrorSummary = classifyClaudeLaunchFailure(error).summary;
  }

  const probe = await probeClaudeSessionWake({
    threadId,
    model: options.model,
  });
  const entries = await readRegistry();
  const now = new Date().toISOString();
  const existing = matchRegistryEntry(entries, options.seatName, threadId);
  const nextEntry = {
    ...(existing ?? {}),
    seat_name: options.seatName,
    seat_slug: text(existing?.seat_slug, "") || options.seatName.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "claude-seat",
    provider: "claude",
    session_id: threadId,
    display_name: text(existing?.display_name, `Claude NPC / ${options.seatName}`) || `Claude NPC / ${options.seatName}`,
    project_root: workspaceRoot(),
    model: text(options.model, "") || text(existing?.model, "") || null,
    launched_at: text(existing?.launched_at, "") || now,
    updated_at: now,
    launch_probe_at: now,
    launch_probe_status: probe.status,
    launch_error_code: probe.errorCode ?? null,
    launch_error_summary: probe.errorSummary ?? launcherErrorSummary,
  } satisfies AnyRecord;
  const deduped = entries.filter((item) => item !== existing);
  await writeRegistry([...deduped, nextEntry], resolvedRegistryPath);

  let launchSummary: string | null = null;
  if (probe.status === "ok") {
    launchSummary = `Claude 会话已可直接使用 ${threadId}`;
  } else if (probe.errorSummary) {
    launchSummary = probe.errorSummary;
  } else if (launcherErrorSummary) {
    launchSummary = launcherErrorSummary;
  } else if (launched) {
    launchSummary = `已尝试唤醒 Claude 会话 ${threadId}`;
  }

  return {
    sessionId: threadId,
    launched,
    registerOnly,
    registryPath: resolvedRegistryPath,
    directReady: probe.status === "ok",
    launchBlocked: probe.blockedByEnvironment,
    launchSummary,
  };
}

export async function cleanupClaudeSeatSessionRegistration(options: {
  seatName: string;
  sourceWorkstationId?: string | null;
}) {
  const threadId = deriveClaudeSessionId(options.sourceWorkstationId);
  const registryFile = registryPath();
  const entries = await readRegistry();
  if (!entries.length) {
    return {
      removed: false,
      registryPath: registryFile,
    };
  }
  const nextEntries = entries.filter((item) => {
    const sameSeat = text(item.seat_name, "") === options.seatName;
    const sameThread = threadId ? text(item.session_id, "") === threadId : false;
    return !sameSeat && !sameThread;
  });
  if (nextEntries.length === entries.length) {
    return {
      removed: false,
      registryPath: registryFile,
    };
  }
  const payload = {
    updated_at: new Date().toISOString(),
    seats: nextEntries,
  };
  await fs.mkdir(path.dirname(registryFile), { recursive: true });
  await fs.writeFile(registryFile, JSON.stringify(payload, null, 2), "utf8");
  return {
    removed: true,
    registryPath: registryFile,
  };
}

export async function writeClaudeSeatMessage(options: {
  seatName: string;
  messageId: string;
  title: string;
  body: string;
  metadata?: Record<string, unknown>;
}) {
  const inboxDir = path.join(
    workspaceRoot(),
    "artifacts",
    "claude-messages",
    options.seatName,
    "inbox"
  );
  await fs.mkdir(inboxDir, { recursive: true });

  const messageFile = path.join(inboxDir, `${options.messageId}.json`);
  const payload = {
    message_id: options.messageId,
    seat_name: options.seatName,
    title: options.title,
    body: options.body,
    created_at: new Date().toISOString(),
    metadata: options.metadata ?? {},
  };

  await fs.writeFile(messageFile, JSON.stringify(payload, null, 2), "utf8");

  return {
    messageFile,
    inboxDir,
  };
}

export async function readClaudeSeatReplies(options: {
  seatName: string;
  since?: Date;
}) {
  const outboxDir = path.join(
    workspaceRoot(),
    "artifacts",
    "claude-messages",
    options.seatName,
    "outbox"
  );

  try {
    const files = await fs.readdir(outboxDir);
    const replies: Array<{
      messageId: string;
      content: string;
      replyAt: string;
      success: boolean;
      file: string;
    }> = [];

    for (const file of files) {
      if (!file.endsWith("-reply.json")) continue;

      const filePath = path.join(outboxDir, file);
      const stat = await fs.stat(filePath);

      if (options.since && stat.mtime < options.since) {
        continue;
      }

      const content = await fs.readFile(filePath, "utf8");
      const reply = JSON.parse(content);

      replies.push({
        messageId: reply.message_id,
        content: reply.content,
        replyAt: reply.reply_at,
        success: reply.success ?? true,
        file: filePath,
      });
    }

    return replies;
  } catch {
    return [];
  }
}

export async function cleanupClaudeSeatMessageFiles(options: {
  seatName: string;
  olderThanDays?: number;
}) {
  const baseDir = path.join(workspaceRoot(), "artifacts", "claude-messages", options.seatName);
  const olderThanMs = (options.olderThanDays ?? 7) * 24 * 60 * 60 * 1000;
  const cutoffTime = Date.now() - olderThanMs;

  let removedCount = 0;

  for (const subdir of ["processed", "outbox"]) {
    const dirPath = path.join(baseDir, subdir);
    try {
      const files = await fs.readdir(dirPath);
      for (const file of files) {
        const filePath = path.join(dirPath, file);
        const stat = await fs.stat(filePath);
        if (stat.mtime.getTime() < cutoffTime) {
          await fs.unlink(filePath);
          removedCount++;
        }
      }
    } catch {
      // 目录不存在或无法访问，跳过
    }
  }

  return { removedCount };
}

export function launchClaudeSeatMessageBridge(options: {
  seatName: string;
  sessionId: string;
  model?: string;
}) {
  const bridgeScriptPath = path.join(workspaceRoot(), "scripts", "claude-seat-message-bridge.ps1");
  const logStamp = new Date().toISOString().replace(/[:.]/g, "-");
  const logDir = path.join(workspaceRoot(), "artifacts", "claude-messages", options.seatName, "logs");

  try {
    // 确保日志目录存在
    if (!require("fs").existsSync(logDir)) {
      require("fs").mkdirSync(logDir, { recursive: true });
    }

    const stdoutPath = path.join(logDir, `bridge-${logStamp}.out.log`);
    const stderrPath = path.join(logDir, `bridge-${logStamp}.err.log`);

    const args = [
      "-NoExit",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      bridgeScriptPath,
      "-SeatName",
      options.seatName,
      "-SessionId",
      options.sessionId,
    ];

    if (options.model) {
      args.push("-Model", options.model);
    }

    const { spawn } = require("child_process");
    const child = spawn("powershell.exe", args, {
      cwd: workspaceRoot(),
      detached: true,
      stdio: "ignore",
      windowsHide: false, // 显示窗口
    });

    child.unref();

    return {
      launched: true,
      stdoutPath,
      stderrPath,
      bridgeScript: bridgeScriptPath,
    };
  } catch (error) {
    console.error("启动Claude消息桥接器失败:", error);
    return {
      launched: false,
      error: error instanceof Error ? error.message : String(error),
      stdoutPath: null,
      stderrPath: null,
    };
  }
}

