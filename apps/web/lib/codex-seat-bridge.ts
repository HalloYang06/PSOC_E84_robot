import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

type AnyRecord = Record<string, unknown>;

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function skipLocalProviderScans() {
  return text(process.env.AI_COLLAB_SKIP_LOCAL_PROVIDER_SCANS, "") === "1";
}

function normalizeSlug(value: string, fallback = "codex-seat") {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || fallback;
}

function escapeTomlString(value: string) {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function parseTomlValue(raw: string) {
  const value = raw.trim();
  if (value.startsWith('"') && value.endsWith('"')) {
    return value
      .slice(1, -1)
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, "\\");
  }
  if (/^-?\d+$/.test(value)) return Number(value);
  return value;
}

function parseAutomationToml(contents: string): AnyRecord {
  const parsed: AnyRecord = {};
  for (const line of contents.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const match = trimmed.match(/^([a-zA-Z0-9_]+)\s*=\s*(.+)$/);
    if (!match) continue;
    parsed[match[1]] = parseTomlValue(match[2]);
  }
  return parsed;
}

async function exists(filePath: string) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function statSafe(filePath: string) {
  try {
    return await fs.stat(filePath);
  } catch {
    return null;
  }
}

async function readJsonSafe(filePath: string) {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8")) as AnyRecord;
  } catch {
    return null;
  }
}

function ageMinutesFromDate(value: Date | null) {
  if (!value) return null;
  const diff = Date.now() - value.getTime();
  if (!Number.isFinite(diff) || diff < 0) return 0;
  return Math.floor(diff / 60000);
}

export function workspaceRoot() {
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
}

export function codexHomeRoot() {
  const envHome = text(process.env.CODEX_HOME, "");
  return envHome || path.join(os.homedir(), ".codex");
}

export function isCodexSessionWorkstationId(value: unknown) {
  return text(value, "").toLowerCase().startsWith("codex-session-");
}

export function deriveCodexThreadId(sourceWorkstationId: unknown) {
  const raw = text(sourceWorkstationId, "");
  if (!raw) return null;
  if (raw.toLowerCase().startsWith("codex-session-")) {
    const stripped = raw.slice("codex-session-".length).trim();
    return stripped || null;
  }
  return raw || null;
}

export function buildCodexSeatConsumerScriptName(seatName: string) {
  const normalized = normalizeSlug(seatName, "codex-seat");
  if (/^npc\d+$/.test(normalized)) return `${normalized}-thread-consumer.py`;
  return `codex-seat-${normalized}-thread-consumer.py`;
}

export function buildCodexSeatConsumerScriptRelativePath(seatName: string) {
  return `scripts/${buildCodexSeatConsumerScriptName(seatName)}`;
}

export function buildCodexSeatConsumerStateRelativePath(seatName: string) {
  return `scripts/.${buildCodexSeatConsumerScriptName(seatName).replace(/\.py$/i, "")}-state.json`;
}

export function buildCodexSeatHeartbeatAutomationId(seatName: string) {
  return `${normalizeSlug(seatName, "codex-seat")}-coop-loop`;
}

export function buildCodexSeatHeartbeatPrompt(options: {
  seatName: string;
  sourceWorkstationId: string;
  responsibility?: string | null;
  heartbeatIntervalSeconds?: number | null;
}) {
  const seatName = text(options.seatName, "Codex NPC");
  const responsibility = text(options.responsibility, "");
  const heartbeatIntervalSeconds = normalizeHeartbeatIntervalSeconds(options.heartbeatIntervalSeconds);
  return [
    `Check for queued platform work targeting workstation ${options.sourceWorkstationId}.`,
    `Keep pushing the freshest ${seatName} task in the local workspace.`,
    "Before work, read docs/ai-requirements/ai-required-requirements-ledger.md when it exists and obey proposer/target/review/reply-to rules.",
    `This automation heartbeat is configured for about ${heartbeatIntervalSeconds} seconds; do not start extra loops unless the platform asks for them.`,
    responsibility ? `Focus on ${responsibility} first when multiple tasks compete.` : "",
    "Update the NPC handoff notes with real progress and keep the farm base intact.",
    "If direct platform write-back is unavailable in this thread, continue local work and let the host bridge mirror the minimal acknowledgement and final reply.",
  ]
    .filter(Boolean)
    .join(" ");
}

type CodexAutomationRecord = {
  id: string;
  name: string;
  status: string;
  prompt: string;
  kind: string;
  rrule: string;
  targetThreadId: string;
  createdAt: number | null;
  updatedAt: number | null;
  filePath: string;
};

const CONSUMER_STATE_STALE_MINUTES = 30;
const DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 60;
const MIN_HEARTBEAT_INTERVAL_SECONDS = 15;
const MAX_HEARTBEAT_INTERVAL_SECONDS = 3600;

function normalizeHeartbeatIntervalSeconds(value: unknown, fallback = DEFAULT_HEARTBEAT_INTERVAL_SECONDS) {
  const parsed = Number(value);
  const candidate = Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed) : fallback;
  return Math.min(MAX_HEARTBEAT_INTERVAL_SECONDS, Math.max(MIN_HEARTBEAT_INTERVAL_SECONDS, candidate));
}

function heartbeatRruleForSeconds(seconds: number) {
  const intervalMinutes = Math.max(1, Math.ceil(normalizeHeartbeatIntervalSeconds(seconds) / 60));
  return `FREQ=MINUTELY;INTERVAL=${intervalMinutes}`;
}

function heartbeatSecondsFromRrule(value: unknown) {
  const raw = text(value, "");
  const minuteMatch = raw.match(/FREQ=MINUTELY;INTERVAL=(\d+)/i);
  if (minuteMatch) return normalizeHeartbeatIntervalSeconds(Number(minuteMatch[1]) * 60);
  return null;
}

export type CodexSeatAutonomyStatus = {
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
  heartbeatIntervalSeconds: number | null;
  heartbeatMissing: boolean;
  lastSelectedRequirementId: string | null;
  lastSelectedAt: string | null;
  lastPlatformFetchRequirementId: string | null;
  lastPlatformFetchAt: string | null;
  autonomyReady: boolean;
  bridgeHealthLabel: string;
  autonomyLabel: string;
};

async function readCodexAutomationCatalog(): Promise<CodexAutomationRecord[]> {
  if (skipLocalProviderScans()) return [];
  const automationsRoot = path.join(codexHomeRoot(), "automations");
  let entries: { name: string; fullPath: string }[] = [];
  try {
    const items = await fs.readdir(automationsRoot, { withFileTypes: true });
    entries = items
      .filter((entry) => entry.isDirectory())
      .map((entry) => ({
        name: entry.name,
        fullPath: path.join(automationsRoot, entry.name, "automation.toml"),
      }));
  } catch {
    return [];
  }

  const records = await Promise.all(
    entries.map(async (entry) => {
      try {
        const parsed = parseAutomationToml(await fs.readFile(entry.fullPath, "utf8"));
        const id = text(parsed.id, entry.name);
        if (!id) return null;
        return {
          id,
          name: text(parsed.name, id),
          status: text(parsed.status, "UNKNOWN"),
          prompt: text(parsed.prompt, ""),
          kind: text(parsed.kind, ""),
          rrule: text(parsed.rrule, ""),
          targetThreadId: text(parsed.target_thread_id, ""),
          createdAt: Number.isFinite(Number(parsed.created_at)) ? Number(parsed.created_at) : null,
          updatedAt: Number.isFinite(Number(parsed.updated_at)) ? Number(parsed.updated_at) : null,
          filePath: entry.fullPath,
        } satisfies CodexAutomationRecord;
      } catch {
        return null;
      }
    }),
  );

  return records.filter((item): item is CodexAutomationRecord => Boolean(item));
}

function pickMatchingAutomation(
  automations: CodexAutomationRecord[],
  options: { seatName: string; sourceWorkstationId: string; threadId: string },
) {
  const expectedId = buildCodexSeatHeartbeatAutomationId(options.seatName);
  const ranked = automations
    .map((item) => {
      const exactIdMatch = item.id === expectedId;
      const promptSeatMatch = item.prompt.includes(options.seatName);
      const nameSeatMatch = item.name.includes(options.seatName);
      if (!exactIdMatch && !promptSeatMatch && !nameSeatMatch) return null;
      let score = 0;
      if (exactIdMatch) score += 8;
      if (promptSeatMatch) score += 4;
      if (nameSeatMatch) score += 2;
      if (item.prompt.includes(options.sourceWorkstationId)) score += 1;
      if (item.targetThreadId === options.threadId) score += 1;
      return { item, score };
    })
    .filter((item): item is { item: CodexAutomationRecord; score: number } => Boolean(item));

  return ranked
    .sort((left, right) => {
      const scoreDelta = right.score - left.score;
      if (scoreDelta !== 0) return scoreDelta;
      return (right.item.updatedAt ?? right.item.createdAt ?? 0) - (left.item.updatedAt ?? left.item.createdAt ?? 0);
    })[0]?.item ?? null;
}

export async function readCodexSeatAutonomyStatus(options: {
  seatId: string;
  seatName: string;
  sourceWorkstationId?: string | null;
}) {
  if (skipLocalProviderScans()) {
    return {
      seatId: options.seatId,
      seatName: options.seatName,
      sourceWorkstationId: text(options.sourceWorkstationId, "") || null,
      threadId: null,
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
      heartbeatIntervalSeconds: null,
      heartbeatMissing: false,
      lastSelectedRequirementId: null,
      lastSelectedAt: null,
      lastPlatformFetchRequirementId: null,
      lastPlatformFetchAt: null,
      autonomyReady: false,
      bridgeHealthLabel: "build skip",
      autonomyLabel: "build skip",
    } satisfies CodexSeatAutonomyStatus;
  }
  const sourceWorkstationId = text(options.sourceWorkstationId, "") || null;
  const consumerScriptPath = sourceWorkstationId
    ? buildCodexSeatConsumerScriptRelativePath(options.seatName)
    : null;
  const consumerStatePath = sourceWorkstationId
    ? buildCodexSeatConsumerStateRelativePath(options.seatName)
    : null;
  const consumerScriptExists = consumerScriptPath
    ? await exists(path.join(workspaceRoot(), consumerScriptPath.replace(/\//g, path.sep)))
    : false;
  const consumerStateFullPath = consumerStatePath
    ? path.join(workspaceRoot(), consumerStatePath.replace(/\//g, path.sep))
    : null;
  const consumerStateStats = consumerStateFullPath ? await statSafe(consumerStateFullPath) : null;
  const consumerStateExists = Boolean(consumerStateStats);
  const consumerStateUpdatedAt = consumerStateStats?.mtime ? consumerStateStats.mtime.toISOString() : null;
  const consumerStateAgeMinutes = ageMinutesFromDate(consumerStateStats?.mtime ?? null);
  const consumerStatePayload = consumerStateFullPath ? await readJsonSafe(consumerStateFullPath) : null;
  const workstationState =
    consumerStatePayload && sourceWorkstationId
      ? ((consumerStatePayload.workstations as AnyRecord | undefined)?.[sourceWorkstationId] as AnyRecord | undefined) ?? null
      : null;
  const lastSelected =
    workstationState && typeof workstationState.last_selected === "object"
      ? (workstationState.last_selected as AnyRecord)
      : null;
  const lastPlatformFetch =
    workstationState && typeof workstationState.last_platform_fetch === "object"
      ? (workstationState.last_platform_fetch as AnyRecord)
      : null;
  const lastSelectedRequirementId = text(lastSelected?.requirement_id, "") || null;
  const lastSelectedAt = text(lastSelected?.at, "") || null;
  const lastPlatformFetchRequirementId = text(lastPlatformFetch?.requirement_id, "") || null;
  const lastPlatformFetchAt = text(lastPlatformFetch?.at, "") || null;
  const consumerStateStale =
    consumerStateAgeMinutes !== null && consumerStateAgeMinutes >= CONSUMER_STATE_STALE_MINUTES;
  const threadId = deriveCodexThreadId(sourceWorkstationId);
  if (!sourceWorkstationId || !threadId) {
    return {
      seatId: options.seatId,
      seatName: options.seatName,
      sourceWorkstationId,
      threadId,
      consumerScriptPath,
      consumerScriptExists,
      consumerStatePath,
      consumerStateExists,
      consumerStateUpdatedAt,
      consumerStateAgeMinutes,
      consumerStateStale,
      automationId: null,
      automationName: null,
      automationStatus: null,
      automationUpdatedAt: null,
      heartbeatIntervalSeconds: null,
      heartbeatMissing: false,
      lastSelectedRequirementId,
      lastSelectedAt,
      lastPlatformFetchRequirementId,
      lastPlatformFetchAt,
      autonomyReady: false,
      bridgeHealthLabel: "bind Codex thread",
      autonomyLabel: "bind Codex thread",
    } satisfies CodexSeatAutonomyStatus;
  }

  const automation = pickMatchingAutomation(await readCodexAutomationCatalog(), {
    seatName: options.seatName,
    sourceWorkstationId,
    threadId,
  });
  const automationStatus = automation?.status ?? null;
  const automationUpdatedAt = automation?.updatedAt ? new Date(automation.updatedAt).toISOString() : null;
  const heartbeatIntervalSeconds = automation ? heartbeatSecondsFromRrule(automation.rrule) : null;
  const heartbeatMissing = !automation;
  const autonomyReady = consumerScriptExists && automationStatus === "ACTIVE";
  const bridgeHealthLabel = !consumerScriptExists
    ? "missing consumer"
    : heartbeatMissing
      ? "missing heartbeat"
      : automationStatus && automationStatus !== "ACTIVE"
        ? `heartbeat ${automationStatus}`
        : !consumerStateExists
          ? "waiting first sync"
          : consumerStateStale
            ? "local state stale"
            : "consumer + heartbeat ready";
  const autonomyLabel = autonomyReady
    ? bridgeHealthLabel
    : !consumerScriptExists
      ? "missing consumer"
      : automationStatus
        ? `heartbeat ${automationStatus}`
        : "missing heartbeat";
  return {
    seatId: options.seatId,
    seatName: options.seatName,
    sourceWorkstationId,
    threadId,
    consumerScriptPath,
    consumerScriptExists,
    consumerStatePath,
    consumerStateExists,
    consumerStateUpdatedAt,
    consumerStateAgeMinutes,
    consumerStateStale,
    automationId: automation?.id ?? null,
    automationName: automation?.name ?? null,
    automationStatus,
    automationUpdatedAt,
    heartbeatIntervalSeconds,
    heartbeatMissing,
    lastSelectedRequirementId,
    lastSelectedAt,
    lastPlatformFetchRequirementId,
    lastPlatformFetchAt,
    autonomyReady,
    bridgeHealthLabel,
    autonomyLabel,
  } satisfies CodexSeatAutonomyStatus;
}

export async function loadCodexSeatAutonomyStatuses(
  seats: Array<{ seatId: string; seatName: string; sourceWorkstationId?: string | null }>,
) {
  const records = await Promise.all(
    seats.map((seat) =>
      readCodexSeatAutonomyStatus({
        seatId: seat.seatId,
        seatName: seat.seatName,
        sourceWorkstationId: seat.sourceWorkstationId,
      }),
    ),
  );
  return Object.fromEntries(records.map((record) => [record.seatId, record] as const));
}

export async function ensureCodexSeatHeartbeatAutomation(options: {
  seatName: string;
  sourceWorkstationId?: string | null;
  responsibility?: string | null;
  heartbeatIntervalSeconds?: number | null;
}) {
  const sourceWorkstationId = text(options.sourceWorkstationId, "");
  const threadId = deriveCodexThreadId(sourceWorkstationId);
  if (!sourceWorkstationId || !threadId) return null;

  const existing = pickMatchingAutomation(await readCodexAutomationCatalog(), {
    seatName: options.seatName,
    sourceWorkstationId,
    threadId,
  });
  const now = Date.now();
  const automationId = existing?.id ?? buildCodexSeatHeartbeatAutomationId(options.seatName);
  const automationName = existing?.name ?? `${text(options.seatName, "Codex NPC")} Coop Loop`;
  const heartbeatIntervalSeconds = normalizeHeartbeatIntervalSeconds(options.heartbeatIntervalSeconds);
  const automationDir = path.join(codexHomeRoot(), "automations", automationId);
  const filePath = path.join(automationDir, "automation.toml");
  const prompt = buildCodexSeatHeartbeatPrompt({
    seatName: options.seatName,
    sourceWorkstationId,
    responsibility: options.responsibility,
    heartbeatIntervalSeconds,
  });
  const createdAt = existing?.createdAt ?? now;
  const contents = [
    "version = 1",
    `id = \"${escapeTomlString(automationId)}\"`,
    'kind = \"heartbeat\"',
    `name = \"${escapeTomlString(automationName)}\"`,
    `prompt = \"${escapeTomlString(prompt)}\"`,
    'status = \"ACTIVE\"',
    `rrule = \"${escapeTomlString(heartbeatRruleForSeconds(heartbeatIntervalSeconds))}\"`,
    `target_thread_id = \"${escapeTomlString(threadId)}\"`,
    `created_at = ${createdAt}`,
    `updated_at = ${now}`,
    "",
  ].join("\n");
  await fs.mkdir(automationDir, { recursive: true });
  await fs.writeFile(filePath, contents, "utf8");
  return {
    id: automationId,
    name: automationName,
    status: "ACTIVE",
    heartbeatIntervalSeconds,
    targetThreadId: threadId,
    updatedAt: new Date(now).toISOString(),
    filePath,
  };
}

export async function cleanupCodexSeatAutonomyArtifacts(options: { seatName: string }) {
  const scriptRelativePath = buildCodexSeatConsumerScriptRelativePath(options.seatName);
  const stateRelativePath = buildCodexSeatConsumerStateRelativePath(options.seatName);
  const scriptPath = path.join(workspaceRoot(), scriptRelativePath.replace(/\//g, path.sep));
  const statePath = path.join(workspaceRoot(), stateRelativePath.replace(/\//g, path.sep));
  const automationId = buildCodexSeatHeartbeatAutomationId(options.seatName);
  const automationDir = path.join(codexHomeRoot(), "automations", automationId);

  let removedScript = false;
  let removedState = false;
  let removedAutomation = false;

  try {
    await fs.rm(scriptPath, { force: true });
    removedScript = true;
  } catch {}
  try {
    await fs.rm(statePath, { force: true });
    removedState = true;
  } catch {}
  try {
    await fs.rm(automationDir, { recursive: true, force: true });
    removedAutomation = true;
  } catch {}

  return {
    removedScript,
    removedState,
    removedAutomation,
    scriptPath,
    statePath,
    automationDir,
  };
}
