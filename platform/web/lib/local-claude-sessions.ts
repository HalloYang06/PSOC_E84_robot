import { execFileSync } from "node:child_process";
import type { Dirent } from "node:fs";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

type AnyRecord = Record<string, unknown>;

type LocalClaudeSessionSummary = {
  id: string;
  workstation_id: string;
  name: string;
  status: string;
  computer_node: string;
  computer_node_id: string | null;
  ai_provider: string;
  ai_provider_id: string;
  model: string | null;
  updated_at: string;
  description: string | null;
  notes: string | null;
  metadata: Record<string, unknown>;
};

type ClaudeSessionCandidate = {
  sessionId: string;
  cwd: string;
  gitBranch: string;
  updatedAt: string;
  startedAt: string;
  pid: number | null;
  latestUserMessage: string;
  latestAssistantMessage: string;
  projectSlug: string;
  sourceFile: string;
  sourceKind: "project_jsonl" | "live_session_file";
  liveProcessSeen: boolean;
  sessionKind: string | null;
};

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function skipLocalProviderScans() {
  return text(process.env.AI_COLLAB_SKIP_LOCAL_PROVIDER_SCANS, "") === "1";
}

function shortText(value: string, limit = 96) {
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (cleaned.length <= limit) return cleaned;
  return `${cleaned.slice(0, Math.max(0, limit - 3))}...`;
}

function normalizeComparablePath(value: string) {
  return value.replace(/[\\/]+/g, "/").toLowerCase();
}

function workspaceRoot() {
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
}

function parseIso(value: string | null | undefined) {
  const raw = text(value, "");
  if (!raw) return Number.NaN;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function parseEpochMillis(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : Number.NaN;
}

function epochMillisToIso(value: unknown) {
  const parsed = parseEpochMillis(value);
  if (!Number.isFinite(parsed)) return "";
  try {
    return new Date(parsed).toISOString();
  } catch {
    return "";
  }
}

function extractMessageText(message: unknown) {
  if (typeof message === "string") return shortText(message);
  if (!message || typeof message !== "object") return "";
  const content = (message as AnyRecord).content;
  if (typeof content === "string") return shortText(content);
  if (!Array.isArray(content)) return "";
  const parts: string[] = [];
  content.forEach((item) => {
    if (typeof item === "string") {
      parts.push(item);
      return;
    }
    if (!item || typeof item !== "object") return;
    const record = item as AnyRecord;
    if (text(record.type, "").toLowerCase() === "text") {
      parts.push(text(record.text, ""));
    }
  });
  return shortText(parts.filter(Boolean).join(" "));
}

async function listFiles(root: string, suffix: string): Promise<string[]> {
  const results: string[] = [];
  async function walk(current: string): Promise<void> {
    let entries: Dirent[] = [];
    try {
      entries = await fs.readdir(current, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const nextPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        await walk(nextPath);
        continue;
      }
      if (entry.isFile() && nextPath.toLowerCase().endsWith(suffix)) {
        results.push(nextPath);
      }
    }
  }
  await walk(root);
  return results;
}

async function readRegistryMap(registryPath: string) {
  try {
    const raw = await fs.readFile(registryPath, "utf8");
    const parsed = JSON.parse(raw.replace(/^\uFEFF/, "")) as AnyRecord;
    const seats = Array.isArray(parsed?.seats) ? parsed.seats : [];
    const registry = new Map<string, AnyRecord>();
    seats.forEach((item) => {
      if (!item || typeof item !== "object") return;
      const record = item as AnyRecord;
      const sessionId = text(record.session_id, "");
      if (!sessionId) return;
      registry.set(sessionId, record);
    });
    return registry;
  } catch {
    return new Map<string, AnyRecord>();
  }
}

function processExists(pid: unknown) {
  const parsed = Number(pid);
  if (!Number.isFinite(parsed) || parsed <= 0) return false;
  try {
    const output = execFileSync("tasklist", ["/FI", `PID eq ${parsed}`, "/FO", "CSV", "/NH"], {
      encoding: "utf8",
      windowsHide: true,
    });
    const normalized = String(output || "").toLowerCase();
    return Boolean(normalized) && !normalized.includes("no tasks are running") && normalized.includes(`\"${parsed}\"`);
  } catch {
    return false;
  }
}

function cwdMatchesFilter(cwd: string, cwdFilter: string) {
  if (!cwdFilter) return true;
  return normalizeComparablePath(cwd).includes(normalizeComparablePath(cwdFilter));
}

function sessionStatus(lastActivityAt: string) {
  const lastActivityMs = parseIso(lastActivityAt);
  if (!Number.isFinite(lastActivityMs)) return "idle";
  const diffMinutes = Math.max(0, Math.floor((Date.now() - lastActivityMs) / 60000));
  if (diffMinutes <= 15) return "active";
  if (diffMinutes <= 180) return "open";
  if (diffMinutes <= 1440) return "idle";
  return "stale";
}

function resolveClaudeSessionStatus(candidate: ClaudeSessionCandidate, lastActivityAt: string, cwdMatchesWorkspace: boolean) {
  if (candidate.sourceKind === "live_session_file") {
    if (candidate.liveProcessSeen) {
      return cwdMatchesWorkspace ? "active" : "external";
    }
    if (recentlyStarted(lastActivityAt)) return "recent_exit";
    return "stale";
  }
  return sessionStatus(lastActivityAt);
}

function recentlyStarted(lastActivityAt: string, withinMinutes = 30) {
  const lastActivityMs = parseIso(lastActivityAt);
  if (!Number.isFinite(lastActivityMs)) return false;
  return Date.now() - lastActivityMs <= withinMinutes * 60_000;
}

function mergeCandidate(existing: ClaudeSessionCandidate | undefined, next: ClaudeSessionCandidate) {
  if (!existing) return next;
  const existingUpdatedMs = parseIso(existing.updatedAt);
  const nextUpdatedMs = parseIso(next.updatedAt);
  const preferNext = !Number.isFinite(existingUpdatedMs) || (Number.isFinite(nextUpdatedMs) && nextUpdatedMs > existingUpdatedMs);
  return {
    sessionId: existing.sessionId || next.sessionId,
    cwd: preferNext ? next.cwd || existing.cwd : existing.cwd || next.cwd,
    gitBranch: existing.gitBranch || next.gitBranch,
    updatedAt: preferNext ? next.updatedAt || existing.updatedAt : existing.updatedAt || next.updatedAt,
    latestUserMessage: existing.latestUserMessage || next.latestUserMessage,
    latestAssistantMessage: existing.latestAssistantMessage || next.latestAssistantMessage,
    startedAt: preferNext ? next.startedAt || existing.startedAt : existing.startedAt || next.startedAt,
    pid:
      preferNext
        ? (Number.isFinite(next.pid ?? Number.NaN) ? next.pid : existing.pid)
        : (Number.isFinite(existing.pid ?? Number.NaN) ? existing.pid : next.pid),
    projectSlug: existing.projectSlug || next.projectSlug,
    sourceFile: preferNext ? next.sourceFile || existing.sourceFile : existing.sourceFile || next.sourceFile,
    sourceKind: preferNext ? next.sourceKind : existing.sourceKind,
    liveProcessSeen: existing.liveProcessSeen || next.liveProcessSeen,
    sessionKind: existing.sessionKind || next.sessionKind,
  } satisfies ClaudeSessionCandidate;
}

async function loadProjectSessionCandidates(projectsRoot: string) {
  const files = await listFiles(projectsRoot, ".jsonl");
  const sessions = new Map<string, ClaudeSessionCandidate>();

  for (const filePath of files) {
    let contents = "";
    try {
      contents = await fs.readFile(filePath, "utf8");
    } catch {
      continue;
    }
    const lines = contents.split(/\r?\n/).filter(Boolean);
    let sessionId = "";
    let cwd = "";
    let gitBranch = "";
    let latestAt = "";
    let latestUserMessage = "";
    let latestAssistantMessage = "";

    for (const line of lines) {
      let parsed: AnyRecord | null = null;
      try {
        parsed = JSON.parse(line) as AnyRecord;
      } catch {
        parsed = null;
      }
      if (!parsed) continue;
      sessionId = text(parsed.sessionId, sessionId);
      cwd = text(parsed.cwd, cwd);
      gitBranch = text(parsed.gitBranch, gitBranch);
      const timestamp = text(parsed.timestamp, "");
      if (timestamp) {
        const currentMs = parseIso(latestAt);
        const nextMs = parseIso(timestamp);
        if (!Number.isFinite(currentMs) || (Number.isFinite(nextMs) && nextMs > currentMs)) {
          latestAt = timestamp;
        }
      }
      const itemType = text(parsed.type, "").toLowerCase();
      if (itemType === "user") latestUserMessage = extractMessageText(parsed.message) || latestUserMessage;
      if (itemType === "assistant") latestAssistantMessage = extractMessageText(parsed.message) || latestAssistantMessage;
    }

    if (!sessionId || !cwd) continue;
    const candidate: ClaudeSessionCandidate = {
      sessionId,
      cwd,
      gitBranch,
      updatedAt: latestAt,
      latestUserMessage,
      latestAssistantMessage,
      startedAt: latestAt,
      pid: null,
      projectSlug: path.basename(path.dirname(filePath)),
      sourceFile: filePath,
      sourceKind: "project_jsonl",
      liveProcessSeen: false,
      sessionKind: "interactive",
    };
    sessions.set(sessionId, mergeCandidate(sessions.get(sessionId), candidate));
  }

  return sessions;
}

async function loadLiveSessionCandidates(claudeHome: string) {
  const sessionsRoot = path.join(claudeHome, "sessions");
  const files = await listFiles(sessionsRoot, ".json");
  const sessions = new Map<string, ClaudeSessionCandidate>();

  for (const filePath of files) {
    let parsed: AnyRecord | null = null;
    try {
      parsed = JSON.parse(await fs.readFile(filePath, "utf8")) as AnyRecord;
    } catch {
      parsed = null;
    }
    if (!parsed) continue;
    const sessionId = text(parsed.sessionId, "");
    const cwd = text(parsed.cwd, "");
    if (!sessionId || !cwd) continue;
    const updatedAt = epochMillisToIso(parsed.startedAt);
    const liveProcessSeen = processExists(parsed.pid);
    const recentlyExited = !liveProcessSeen && recentlyStarted(updatedAt);
    if (!liveProcessSeen && !recentlyExited) continue;
    const candidate: ClaudeSessionCandidate = {
      sessionId,
      cwd,
      gitBranch: "",
      updatedAt,
      startedAt: updatedAt,
      pid: Number.isFinite(Number(parsed.pid)) ? Number(parsed.pid) : null,
      latestUserMessage: "",
      latestAssistantMessage: "",
      projectSlug: "(live-session)",
      sourceFile: filePath,
      sourceKind: "live_session_file",
      liveProcessSeen,
      sessionKind: text(parsed.kind, "") || null,
    };
    sessions.set(sessionId, mergeCandidate(sessions.get(sessionId), candidate));
  }

  return sessions;
}

export async function loadLocalClaudeWorkstations(options?: {
  cwdFilter?: string | null;
  claudeHome?: string | null;
  registryPath?: string | null;
  limit?: number;
}) {
  if (skipLocalProviderScans()) return [];
  const claudeHome = text(options?.claudeHome, "") || path.join(os.homedir(), ".claude");
  const cwdFilter = text(options?.cwdFilter, "");
  const registryPath =
    text(options?.registryPath, "") || path.join(workspaceRoot(), "artifacts", "claude-seat-registry.json");
  const registry = await readRegistryMap(registryPath);
  const [projectCandidates, liveCandidates] = await Promise.all([
    loadProjectSessionCandidates(path.join(claudeHome, "projects")),
    loadLiveSessionCandidates(claudeHome),
  ]);

  const candidateMap = new Map<string, ClaudeSessionCandidate>();
  for (const [sessionId, candidate] of projectCandidates.entries()) {
    candidateMap.set(sessionId, mergeCandidate(candidateMap.get(sessionId), candidate));
  }
  for (const [sessionId, candidate] of liveCandidates.entries()) {
    candidateMap.set(sessionId, mergeCandidate(candidateMap.get(sessionId), candidate));
  }

  const sessions: LocalClaudeSessionSummary[] = [];
  for (const candidate of candidateMap.values()) {
    const sessionId = candidate.sessionId;
    const cwd = candidate.cwd;
    if (!sessionId || !cwd) continue;
    const registryEntry = registry.get(sessionId) ?? {};
    const lastActivityAt = candidate.updatedAt || "";
    const cwdInWorkspace = cwdMatchesFilter(cwd, cwdFilter);
    const status = resolveClaudeSessionStatus(candidate, lastActivityAt, cwdInWorkspace);
    const includeSession =
      candidate.liveProcessSeen ||
      Boolean(registryEntry && Object.keys(registryEntry).length > 0) ||
      (candidate.sourceKind === "live_session_file" && (cwdInWorkspace || recentlyStarted(lastActivityAt))) ||
      (candidate.sourceKind === "project_jsonl" && cwdInWorkspace && ["active", "open"].includes(status));
    if (!includeSession) continue;

    const seatName = text(registryEntry.seat_name, "");
    const description =
      candidate.latestAssistantMessage || candidate.latestUserMessage
        ? shortText(candidate.latestAssistantMessage || candidate.latestUserMessage, 140)
        : candidate.sourceKind === "live_session_file"
          ? candidate.liveProcessSeen
            ? cwdInWorkspace
              ? "手动打开的 Claude 终端已在线，等待第一条会话消息。"
              : "Claude 终端已打开，但当前目录还不在项目仓库。"
            : "Claude 终端刚刚退出，还没进入持续协作。"
          : null;
    const notes = seatName
      ? `已登记席位：${seatName}`
      : candidate.sourceKind === "live_session_file" && !candidate.liveProcessSeen
        ? "Claude 终端刚刚退出，请重新打开后再绑定。"
        : candidate.liveProcessSeen && !cwdInWorkspace
          ? "Claude 终端已打开，但要先切到项目目录再绑定。"
          : "未登记到平台席位";

    sessions.push({
      id: `claude-session-${sessionId}`,
      workstation_id: `claude-session-${sessionId}`,
      name: seatName ? `Claude / ${seatName}` : `Claude 会话 ${sessionId.slice(0, 8)}`,
      status,
      computer_node: "本机 Claude",
      computer_node_id: null,
      ai_provider: "Claude",
      ai_provider_id: "claude",
      model: null,
      updated_at: lastActivityAt,
      description,
      notes,
      metadata: {
        source: "local_claude_session",
        provider: "claude",
        claude_session_id: sessionId,
        pid: candidate.pid,
        started_at: candidate.startedAt || null,
        seat_name: seatName || null,
        git_branch: candidate.gitBranch || null,
        cwd,
        cwd_matches_filter: cwdInWorkspace,
        cwd_display: cwd,
        live_process_seen: candidate.liveProcessSeen,
        session_kind: candidate.sessionKind,
        latest_user_message: candidate.latestUserMessage || null,
        latest_assistant_message: candidate.latestAssistantMessage || null,
        source_file: candidate.sourceFile,
        source_kind: candidate.sourceKind,
        registry_path: registryPath,
      },
    });
  }

  return sessions
    .sort((left, right) => parseIso(right.updated_at) - parseIso(left.updated_at))
    .slice(0, Math.max(1, options?.limit ?? 12));
}
