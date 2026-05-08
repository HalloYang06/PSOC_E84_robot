import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { buildEconomyBalance } from "../../../lib/game/economy-balance";
import { loadCodexSeatAutonomyStatuses } from "../../../lib/codex-seat-bridge";
import { loadLocalClaudeWorkstations } from "../../../lib/local-claude-sessions";
import { readProjectCodexCommands, syncProjectCodexDispatchInboxFromRecords } from "../../../lib/local-agent-bridge";
import { loadNpcKnowledgeSnapshots } from "../../../lib/npc-knowledge-docs";
import { resolveNpcKnowledgeProfile } from "../../../lib/npc-knowledge";
import { loadClaudeSeatAutonomyStatuses } from "../../../lib/claude-seat-bridge";
import {
  isNpcSeatRecord,
  platformProviderIdFromSeat,
} from "../../../lib/platform-provider";
import { DEFAULT_PLATFORM_SKILL_LIBRARY } from "../../../lib/platform-skills";
import {
  getApprovalsData,
  getCollaborationMessagesState,
  getCurrentAuthState,
  getGitProjectActivityState,
  getGitProjectExecutionState,
  getHandoffsData,
  getProjectComputerNodesState,
  getProjectMembersState,
  getProjectState,
  getProjectThreadWorkstationsState,
  markProjectPresenceState,
  getRequirementsState,
  getTasksDataScopedState,
  getUsageData,
} from "../../../lib/server-data";
import { ProjectPlayableShell } from "./project-playable-shell";
import { GameShell } from "./_components/game-shell";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type AnyRecord = Record<string, any>;

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function uniqueStrings(values: unknown[]) {
  return Array.from(
    new Set(
      values
        .map((value) => String(value ?? "").trim())
        .filter(Boolean),
    ),
  );
}

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function decodePreviewSearchParam(value: unknown) {
  const raw = text(value, "");
  if (!raw) return null;
  try {
    const json = Buffer.from(raw, "base64url").toString("utf8");
    const parsed = JSON.parse(json);
    return parsed && typeof parsed === "object" ? (parsed as AnyRecord) : null;
  } catch {
    return null;
  }
}

async function resolveComputerConnectServerUrl() {
  const envOrigin = text(
    process.env.NEXT_PUBLIC_API_BASE_URL ??
      process.env.INTERNAL_API_BASE_URL ??
      process.env.PUBLIC_API_BASE_URL ??
      process.env.NEXT_PUBLIC_APP_ORIGIN ??
      process.env.PUBLIC_APP_DOMAIN,
    "",
  );
  if (envOrigin) {
    return envOrigin;
  }

  const statusCandidates = [
    join(process.cwd(), "artifacts", "local-server-mode-status.json"),
    join(process.cwd(), "..", "artifacts", "local-server-mode-status.json"),
  ];
  for (const candidate of statusCandidates) {
    try {
      if (!existsSync(candidate)) continue;
      const raw = readFileSync(candidate, "utf8");
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      const apiUrl = text(parsed.api_url, "");
      if (apiUrl) {
        return apiUrl;
      }
      const webUrl = text(parsed.web_url, "");
      if (webUrl) {
        return webUrl.replace(":3000", ":8010");
      }
    } catch {
      continue;
    }
  }

  try {
    const headerStore = await headers();
    const host = text(headerStore.get("x-forwarded-host") ?? headerStore.get("host"), "");
    if (host) {
      const forwardedProto = text(headerStore.get("x-forwarded-proto"), "");
      const proto =
        forwardedProto ||
        (/^(localhost|127\.0\.0\.1|192\.168\.|10\.|172\.(1[6-9]|2\d|3[0-1])\.)/i.test(host) ? "http" : "https");
      return `${proto}://${host}`.replace(":3000", ":8010");
    }
  } catch {
    // fall through to localhost
  }

  return "http://127.0.0.1:8010";
}

const STALE_NPC_MOJIBAKE_REGEX = /(?:[\uFFFD�]|鍦ㄧ嚎|绂荤嚎|鐮斿彂鍩哄湴|寮€|寮�|鏈懡|搴勫洯|浠诲姟|鍗忎綔|闃熼暱|涓荤▼|鏈烘埧|鐢佃剳|绾跨▼|銆)/;

function isQuestionMarkHeavy(value: unknown) {
  const raw = String(value ?? "").trim();
  if (!raw) return true;
  const questionMarkCount = raw.match(/\?/g)?.length ?? 0;
  return /^\?+$/.test(raw) || questionMarkCount >= Math.ceil(raw.length / 2);
}

function looksLikeUuid(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function isProviderSessionId(value: unknown) {
  const normalized = String(value ?? "").trim().toLowerCase();
  return normalized.startsWith("codex-session-") || normalized.startsWith("claude-session-");
}

function isStaleNpcSeatRecord(workstation: AnyRecord) {
  if (!isNpcSeatRecord(workstation)) return false;
  const metadata =
    workstation?.metadata && typeof workstation.metadata === "object"
      ? (workstation.metadata as AnyRecord)
      : {};
  const seatName = text(workstation?.name, "");
  const seatId = text(workstation?.id ?? workstation?.config_id ?? workstation?.row_id, "");
  const sourceWorkstationId = text(
    workstation?.source_workstation_id ??
      workstation?.sourceWorkstationId ??
      metadata?.source_workstation_id ??
      workstation?.extra_data?.source_workstation_id,
    "",
  );
  const hasLiveProviderSource = isProviderSessionId(sourceWorkstationId);
  const pollutedSeatName =
    Boolean(seatName) &&
    (isQuestionMarkHeavy(seatName) || /\?{2,}/.test(seatName) || STALE_NPC_MOJIBAKE_REGEX.test(seatName));
  const pollutedSeatId =
    Boolean(seatId) &&
    (isQuestionMarkHeavy(seatId) || /\?{2,}/.test(seatId) || STALE_NPC_MOJIBAKE_REGEX.test(seatId));
  const pollutedSource =
    Boolean(sourceWorkstationId) &&
    (isQuestionMarkHeavy(sourceWorkstationId) ||
      /\?{2,}/.test(sourceWorkstationId) ||
      STALE_NPC_MOJIBAKE_REGEX.test(sourceWorkstationId));
  if (sourceWorkstationId && looksLikeUuid(sourceWorkstationId) && !isProviderSessionId(sourceWorkstationId)) return true;
  if (hasLiveProviderSource) {
    const hasPersistentIdentity = Boolean(text(metadata?.npc_identity_key, "")) || Boolean(metadata?.npc_knowledge);
    const hasResponsibility = Boolean(text(workstation?.responsibility ?? metadata?.responsibility, ""));
    if (hasPersistentIdentity || hasResponsibility || !pollutedSeatName) {
      return false;
    }
  }
  if (pollutedSeatName) return true;
  if (pollutedSource) return true;
  return !hasLiveProviderSource && pollutedSeatId;
}

function sanitizeNpcSeatRecord(workstation: AnyRecord) {
  if (!isNpcSeatRecord(workstation)) return workstation;
  const metadata =
    workstation?.metadata && typeof workstation.metadata === "object"
      ? ({ ...(workstation.metadata as AnyRecord) } satisfies AnyRecord)
      : {};
  const sourceWorkstationId = text(
    workstation?.source_workstation_id ??
      workstation?.sourceWorkstationId ??
      metadata?.source_workstation_id ??
      workstation?.extra_data?.source_workstation_id,
    "",
  );
  const rawSeatId = text(workstation?.id ?? workstation?.config_id ?? workstation?.row_id, "");
  const canonicalSeatId =
    sourceWorkstationId &&
    (looksLikeUuid(rawSeatId) ||
      rawSeatId.includes("?") ||
      isQuestionMarkHeavy(rawSeatId) ||
      isQuestionMarkHeavy(text(workstation?.name, "")))
      ? sourceWorkstationId
      : rawSeatId || sourceWorkstationId || text(workstation?.row_id, "");
  const knowledgeProfile = resolveNpcKnowledgeProfile(
    { ...workstation, metadata },
    {
      fallbackName: text(workstation?.name, "NPC"),
      fallbackResponsibility: text(workstation?.responsibility ?? metadata?.responsibility, "待分配职责"),
    },
  );
  return {
    ...workstation,
    canonical_seat_id: canonicalSeatId || null,
    metadata: {
      ...metadata,
      canonical_seat_id: canonicalSeatId || null,
      npc_identity_key: text(metadata.npc_identity_key, knowledgeProfile.key),
      npc_knowledge: knowledgeProfile,
    },
  };
}

function normalizeConfig(project: AnyRecord) {
  const raw = project.collaboration_config ?? {};
  const skillLibrary = mergeById(
    asArray<AnyRecord>(raw.skill_library ?? raw.skillLibrary),
    DEFAULT_PLATFORM_SKILL_LIBRARY,
  );
  const workstations = asArray<AnyRecord>(raw.thread_workstations ?? raw.threadWorkstations ?? raw.workstations);
  const sourceThreads = workstations.filter((item) => !isNpcSeatRecord(item));
  const codexSeats = workstations.filter((item) => isNpcSeatRecord(item));
  return {
    nodes: asArray<AnyRecord>(raw.computer_nodes ?? raw.nodes),
    providers: asArray<AnyRecord>(raw.ai_providers ?? raw.providers),
    workstations,
    sourceThreads,
    codexSeats,
    skillLibrary,
  };
}

function mergeById(primary: AnyRecord[], fallback: AnyRecord[]) {
  const merged = new Map<string, AnyRecord>();
  for (const item of fallback) {
    const id = String(item?.id ?? item?.name ?? "").trim();
    if (id) merged.set(id, item);
  }
  for (const item of primary) {
    const id = String(item?.id ?? item?.name ?? "").trim();
    if (id) {
      const current = merged.get(id) ?? {};
      const currentMetadata =
        current.metadata && typeof current.metadata === "object" ? (current.metadata as AnyRecord) : {};
      const itemMetadata = item.metadata && typeof item.metadata === "object" ? (item.metadata as AnyRecord) : {};
      merged.set(id, {
        ...current,
        ...item,
        metadata: {
          ...currentMetadata,
          ...itemMetadata,
        },
      });
    }
  }
  return Array.from(merged.values());
}

function workstationsFromNodeScans(nodes: AnyRecord[]) {
  const stations: AnyRecord[] = [];
  for (const node of nodes) {
    const nodeId = text(node?.id);
    const nodeLabel = text(node?.label ?? node?.name ?? nodeId);
    const metadata = node?.metadata && typeof node.metadata === "object" ? (node.metadata as AnyRecord) : {};
    const scan = metadata?.thread_scan && typeof metadata.thread_scan === "object" ? (metadata.thread_scan as AnyRecord) : {};
    const threads = Array.isArray(scan.threads) ? scan.threads : [];
    for (const thread of threads) {
      const workstationId = text(thread?.workstation_id ?? thread?.id);
      if (!workstationId) continue;
      const runnerId = text(thread?.runner_id ?? metadata?.runner_id ?? node?.runner_id, "") || null;
      stations.push({
        id: workstationId,
        workstation_id: workstationId,
        name: text(thread?.workstation_name ?? thread?.name ?? workstationId, workstationId),
        computer_node_id: nodeId,
        computer_node: nodeLabel,
        status: text(thread?.workstation_status ?? thread?.status, "idle"),
        agent_id: text(thread?.agent_id, "") || null,
        runner_id: runnerId,
        ai_provider_id: text(thread?.ai_provider_id, "") || null,
        ai_provider: text(thread?.ai_provider_label ?? thread?.ai_provider, "") || null,
        description: text(thread?.description, "") || null,
        notes: text(thread?.notes, "") || null,
        metadata: {
          ...(thread?.metadata && typeof thread.metadata === "object" ? (thread.metadata as AnyRecord) : {}),
          source: "runner_thread_scan",
          runner_id: runnerId,
        },
      });
    }
  }
  return stations;
}

function sumUsageCost(entries: AnyRecord[]) {
  return entries.reduce(
    (sum, item) => sum + Number(item.costCny ?? item.cost ?? ((item.cost_cents ?? 0) / 100)),
    0,
  );
}

function isOnlineNode(status: unknown) {
  return ["online", "ready", "active"].includes(String(status ?? "").toLowerCase());
}

function isActiveThreadStatus(status: unknown) {
  return ["active", "running", "open", "processing", "in_progress", "queued", "routed"].includes(
    String(status ?? "").toLowerCase(),
  );
}

function isRunnerScannedWorkstation(workstation: AnyRecord) {
  return String(workstation?.metadata?.source ?? workstation?.source ?? "").toLowerCase() === "runner_thread_scan";
}

function isLocalClaudeSessionWorkstation(workstation: AnyRecord) {
  return String(workstation?.metadata?.source ?? workstation?.source ?? "").toLowerCase() === "local_claude_session";
}

function isManualUserEntryWorkstation(workstation: AnyRecord) {
  const metadata = workstation?.metadata && typeof workstation.metadata === "object" ? (workstation.metadata as AnyRecord) : {};
  return (
    String(metadata.source_kind ?? workstation?.source_kind ?? "").toLowerCase() === "manual_user_entry" ||
    String(metadata.source ?? workstation?.source ?? "").toLowerCase() === "project_workbench"
  );
}

function workstationActivityKeys(workstation: AnyRecord) {
  const metadata = workstation?.metadata && typeof workstation.metadata === "object" ? (workstation.metadata as AnyRecord) : {};
  return uniqueStrings([
    workstation?.id,
    workstation?.config_id,
    workstation?.row_id,
    workstation?.agent_id,
    workstation?.source_workstation_id,
    metadata?.source_workstation_id,
    metadata?.workstation_id,
  ]).map((item) => item.toLowerCase());
}

function collaborationActivityKeys(message: AnyRecord) {
  const metadata = message?.metadata && typeof message.metadata === "object" ? (message.metadata as AnyRecord) : {};
  return uniqueStrings([
    message?.agent_id,
    message?.sender_id,
    message?.recipient_id,
    message?.workstation_id,
    message?.source_workstation_id,
    metadata?.source_workstation_id,
    metadata?.recipient_id,
  ]).map((item) => item.toLowerCase());
}

function isWorkstationActivityEvidenceMessage(message: AnyRecord) {
  return [
    "requirement_progress_ack",
    "requirement_final_reply",
    "agent_ack",
    "agent_result",
    "runner_ack",
    "runner_result",
  ].includes(text(message?.message_type, "").toLowerCase());
}

function hasWorkstationActivityEvidence(workstation: AnyRecord, collaborationMessages: AnyRecord[]) {
  if (isNpcSeatRecord(workstation)) return false;
  const workstationKeys = workstationActivityKeys(workstation);
  if (!workstationKeys.length) return false;
  return collaborationMessages.some((message) => {
    if (!isWorkstationActivityEvidenceMessage(message)) return false;
    const messageKeys = collaborationActivityKeys(message);
    return messageKeys.some((key) => workstationKeys.includes(key));
  });
}

function buildActiveSourceThreads(workstations: AnyRecord[], nodes: AnyRecord[], collaborationMessages: AnyRecord[]) {
  const onlineNodeIds = new Set(
    nodes
      .filter((node) => isOnlineNode(node?.status))
      .map((node) => text(node?.id))
      .filter(Boolean),
  );
  return workstations.filter((workstation) => {
    const nodeId = text(workstation?.computer_node_id ?? workstation?.computerNodeId);
    return (
      (
        isRunnerScannedWorkstation(workstation) &&
        Boolean(nodeId) &&
        onlineNodeIds.has(nodeId) &&
        isActiveThreadStatus(workstation?.status)
      ) ||
      (isLocalClaudeSessionWorkstation(workstation) && isActiveThreadStatus(workstation?.status))
      ||
      (
        isManualUserEntryWorkstation(workstation) &&
        isActiveThreadStatus(workstation?.status) &&
        (!nodeId || onlineNodeIds.has(nodeId))
      )
      ||
      (
        isActiveThreadStatus(workstation?.status) &&
        hasWorkstationActivityEvidence(workstation, collaborationMessages)
      )
    );
  });
}

function isDoneTask(status: unknown) {
  return ["done", "completed", "archived"].includes(String(status ?? "").toLowerCase());
}

function isBlockedTask(status: unknown) {
  return ["blocked", "failed", "error"].includes(String(status ?? "").toLowerCase());
}

function isTerminalRequirementStatus(status: unknown) {
  return ["done", "completed", "archived", "failed", "cancelled", "canceled", "rejected"].includes(
    String(status ?? "").toLowerCase(),
  );
}

function isPendingApproval(task: AnyRecord) {
  const status = String(task.status ?? "").toLowerCase();
  return Boolean(task.requires_human_approval) || status === "waiting_approval" || status === "pending_approval";
}

function fallbackProject(id: string): AnyRecord {
  return {
    id,
    name: `项目 ${id.slice(0, 8)}`,
    description: "当前先以可玩的农场地图为主，平台信息保持轻量，不压住游戏视野。",
    collaboration_config: {
      thread_workstations: [],
      ai_providers: [],
      computer_nodes: [],
    },
  };
}

function readWorkspaceGitDefaults() {
  try {
    const repoRoot = execFileSync("git", ["rev-parse", "--show-toplevel"], { encoding: "utf8" }).trim();
    const remoteUrl = execFileSync("git", ["remote", "get-url", "origin"], { encoding: "utf8" }).trim();
    const currentBranch = execFileSync("git", ["branch", "--show-current"], { encoding: "utf8" }).trim();
    return {
      githubUrl: remoteUrl || null,
      localGitUrl: repoRoot || null,
      defaultBranch: "main",
      developBranch: currentBranch || "develop",
    };
  } catch {
    return {
      githubUrl: null,
      localGitUrl: null,
      defaultBranch: "main",
      developBranch: "develop",
    };
  }
}

function hasProjectCollaborationAccess(authData: AnyRecord | null, project: AnyRecord, members: AnyRecord[]) {
  const user = authData?.user ?? null;
  if (!user) return false;
  if (project?.is_owner) return true;
  const role = String(project?.role ?? "").trim().toLowerCase();
  if (role && role !== "guest") return true;
  const currentId = String(user.id ?? "").trim();
  const currentEmail = String(user.email ?? "").trim().toLowerCase();
  return members.some((member) => {
    const memberId = String(member.user_id ?? member.user?.id ?? member.id ?? "").trim();
    const memberEmail = String(member.email ?? member.user?.email ?? "").trim().toLowerCase();
    return (currentId && memberId === currentId) || (currentEmail && memberEmail === currentEmail);
  });
}

async function safeCall<T>(loader: Promise<T>, fallback: T): Promise<T> {
  try {
    return await loader;
  } catch {
    return fallback;
  }
}

type LoadResult<T> = {
  data: T;
  status: number;
  error: null;
};

async function loadWithStatus<T>(loader: Promise<T>, fallback: T): Promise<LoadResult<T>> {
  try {
    return { data: await loader, status: 200, error: null };
  } catch {
    return { data: fallback, status: 500, error: null };
  }
}

export default async function ProjectDetailPage({
  params,
  searchParams,
  }: {
    params: { id: string };
    searchParams?: {
      zone?: string;
      mode?: string;
      panel?: string;
      tab?: string;
      exchange_section?: string;
      exchange_composer?: string;
      human_party?: string;
      computer?: string;
      npc_view?: string;
      seat?: string;
      drawer?: string;
      drawer_id?: string;
      bind_thread?: string;
      bind_node?: string;
      npc_name?: string;
      npc_role?: string;
      return_to?: string;
      team_notice?: string;
      team_error?: string;
      collab_preview?: string;
      git_sync_preview?: string;
      git_preview?: string;
      pairing_node?: string;
      pairing_token?: string;
      adapter_workstation?: string;
      adapter_token?: string;
      legacy?: string;
    };
  }) {
  if (!searchParams?.legacy && !searchParams?.mode && !searchParams?.zone) {
    const projectState = await getProjectState(params.id);
    if (projectState.status === 401) {
      const projectReturnPath = encodeURIComponent(`/projects/${params.id}`);
      redirect(`/login?returnTo=${projectReturnPath}`);
    }
    if (projectState.status === 403) {
      redirect(
        `/projects?tab=projects&team_error=${encodeURIComponent("当前账号没有这个项目的访问权限，请从项目列表重新进入。")}`,
      );
    }
    if (projectState.status === 404) {
      redirect(`/projects?tab=projects&team_error=${encodeURIComponent("这个项目不存在，或者你没有被授权访问。")}`);
    }
    const project = projectState?.data ?? fallbackProject(params.id);
    const projectIdStr = String(project.id ?? params.id);
    const projectName = String(project.name ?? `项目 ${params.id.slice(0, 8)}`).trim() || `项目 ${params.id.slice(0, 8)}`;
    return (
      <GameShell
        projectId={projectIdStr}
        projectName={projectName}
      />
    );
  }
  const projectState = await getProjectState(params.id);
  const projectReturnPath = encodeURIComponent(`/projects/${params.id}`);
  if (projectState.status === 401) {
    redirect(`/login?returnTo=${projectReturnPath}`);
  }
  if (projectState.status === 403) {
    redirect(
      `/projects?tab=projects&team_error=${encodeURIComponent("当前账号没有这个项目的访问权限，请从项目列表重新进入。")}`,
    );
  }
  if (projectState.status === 404) {
    redirect(`/projects?tab=projects&team_error=${encodeURIComponent("这个项目不存在，或者你没有被授权访问。")}`);
  }
  const project = projectState?.data ?? fallbackProject(params.id);
  const computerConnectServerUrl = await resolveComputerConnectServerUrl();
  const authResult = await getCurrentAuthState();
  const authData = authResult.data;
  await markProjectPresenceState(params.id, `/projects/${params.id}`);
  const projectMembersResult = await getProjectMembersState(params.id);
  const projectMembers = projectMembersResult.data;
  const workspaceGitDefaults = readWorkspaceGitDefaults();

  const [
    taskResult,
    requirementResult,
    approvalResult,
    handoffResult,
    usageResult,
    collaborationMessageResult,
    relayCommandResult,
    relayAckResult,
    relayResultResult,
    liveNodeResult,
    liveWorkstationResult,
    gitExecutionResult,
    gitActivityResult,
  ] =
    await Promise.all([
      getTasksDataScopedState({ projectIds: [String(project.id)] }),
      getRequirementsState({ projectIds: [String(project.id)] }),
      loadWithStatus(getApprovalsData(), [] as AnyRecord[]),
      loadWithStatus(getHandoffsData(), [] as AnyRecord[]),
      loadWithStatus(getUsageData(), [] as AnyRecord[]),
      getCollaborationMessagesState({ projectId: String(project.id) }),
      getCollaborationMessagesState({ projectId: String(project.id), messageType: "runner_command" }),
      getCollaborationMessagesState({ projectId: String(project.id), messageType: "runner_ack" }),
      getCollaborationMessagesState({ projectId: String(project.id), messageType: "runner_result" }),
      getProjectComputerNodesState(String(project.id)),
      getProjectThreadWorkstationsState(String(project.id)),
      getGitProjectExecutionState(String(project.id)),
      getGitProjectActivityState(String(project.id)),
    ]);
  const tasks = taskResult.data;
  const requirements = requirementResult.data;
  const approvals = approvalResult.data;
  const handoffs = handoffResult.data;
  const usage = usageResult.data;
  const collaborationMessages = collaborationMessageResult.data;
  const relayCommands = relayCommandResult.data;
  const relayAcks = relayAckResult.data;
  const relayResults = relayResultResult.data;
  const liveNodes = liveNodeResult.data;
  const liveWorkstations = liveWorkstationResult.data;
  const gitExecution = gitExecutionResult.data;
  const gitActivity = gitActivityResult.data;

  await safeCall(
    syncProjectCodexDispatchInboxFromRecords({
      projectId: String(project.id ?? params.id),
      dispatchMessages: collaborationMessages.filter(
        (item) => String(item?.message_type ?? item?.messageType ?? "").trim().toLowerCase() === "requirement_dispatch",
      ),
      workstations: liveWorkstations,
      project: project && typeof project === "object" ? (project as AnyRecord) : null,
      issuer: "平台页面补齐",
    }),
    0,
  );
  const codexInboxRaw = await readProjectCodexCommands(String(project.id ?? params.id));
  const requirementStatusById = new Map(
    requirements
      .map((item) => [text(item.id ?? item.requirement_id, ""), text(item.status, "").toLowerCase()] as const)
      .filter(([id]) => Boolean(id)),
  );
  const codexInbox = codexInboxRaw.filter((item) => {
    const requirementId = text(item.sourceRequirementId, "");
    if (!requirementId) return true;
    return !isTerminalRequirementStatus(requirementStatusById.get(requirementId));
  });
  const localClaudeWorkstations = await loadLocalClaudeWorkstations({
    cwdFilter: text(workspaceGitDefaults.localGitUrl, ""),
  });
  const configBase = normalizeConfig(project);
  const scannedWorkstations = workstationsFromNodeScans(liveNodes);
  const baseSeatRecords = configBase.workstations.filter((item: AnyRecord) => isNpcSeatRecord(item));
  const baseSourceThreadRecords = configBase.workstations.filter((item: AnyRecord) => !isNpcSeatRecord(item));
  const liveSourceThreadRecords = mergeById(
    mergeById(
      liveWorkstations.filter((item: AnyRecord) => !isNpcSeatRecord(item)),
      scannedWorkstations.filter((item: AnyRecord) => !isNpcSeatRecord(item)),
    ),
    localClaudeWorkstations.filter((item: AnyRecord) => !isNpcSeatRecord(item)),
  );
  const mergedSourceThreadRecords = mergeById(liveSourceThreadRecords, baseSourceThreadRecords);
  const filteredSeatRecords = baseSeatRecords
    .filter((item: AnyRecord) => !isStaleNpcSeatRecord(item))
    .map((item: AnyRecord) => sanitizeNpcSeatRecord(item));
  const filteredWorkstations = [...mergedSourceThreadRecords, ...filteredSeatRecords];
  const config: AnyRecord = {
    ...configBase,
    nodes: mergeById(liveNodes, configBase.nodes),
    workstations: filteredWorkstations,
    adapterTargetIds: uniqueStrings(
      liveWorkstations.flatMap((item: AnyRecord) => [
        item.id,
        item.config_id,
        item.workstation_id,
      ]),
    ),
    activeSourceThreads: [] as AnyRecord[],
  };
  config.sourceThreads = mergedSourceThreadRecords;
  config.codexSeats = filteredSeatRecords;
  config.activeSourceThreads = buildActiveSourceThreads(config.workstations, config.nodes, collaborationMessages);
  config.npcKnowledgeSnapshots = await loadNpcKnowledgeSnapshots(
    config.codexSeats.map((seat: AnyRecord, index: number) => {
      const profile = resolveNpcKnowledgeProfile(seat, {
        fallbackName: text(seat?.name, `NPC ${index + 1}`),
        fallbackResponsibility: text(seat?.responsibility ?? seat?.metadata?.responsibility, "待分配职责"),
      });
      return {
        seatId: text(seat?.id ?? seat?.config_id ?? seat?.row_id, ""),
        handoffPath: profile.handoff_path,
      };
    }),
  );
  const codexAutonomyStatuses = await loadCodexSeatAutonomyStatuses(
    config.codexSeats
      .filter((seat: AnyRecord) => platformProviderIdFromSeat(seat) === "codex")
      .map((seat: AnyRecord, index: number) => ({
        seatId: text(seat?.id ?? seat?.config_id ?? seat?.row_id, ""),
        seatName: text(seat?.name, `NPC ${index + 1}`),
        sourceWorkstationId: text(seat?.source_workstation_id ?? seat?.metadata?.source_workstation_id, "") || null,
      })),
  );
  const claudeAutonomyStatuses = await loadClaudeSeatAutonomyStatuses(
    config.codexSeats
      .filter((seat: AnyRecord) => platformProviderIdFromSeat(seat) === "claude")
      .map((seat: AnyRecord, index: number) => ({
        seatId: text(seat?.id ?? seat?.config_id ?? seat?.row_id, ""),
        seatName: text(seat?.name, `NPC ${index + 1}`),
        sourceWorkstationId: text(seat?.source_workstation_id ?? seat?.metadata?.source_workstation_id, "") || null,
      })),
  );
  config.codexAutonomyStatuses = {
    ...codexAutonomyStatuses,
    ...claudeAutonomyStatuses,
  };
  const taskIds = new Set(tasks.map((task) => String(task.id ?? task.task_id ?? "")));
  const onlineComputers = config.nodes.filter((node: AnyRecord) => isOnlineNode(node.status)).length;
  const activeTasks = tasks.filter((task) => !isDoneTask(task.status));
  const blockedTasks = tasks.filter((task) => isBlockedTask(task.status));
  const pendingApprovals = tasks.filter((task) => isPendingApproval(task));

  const relayTimeline = [...relayCommands, ...relayAcks, ...relayResults]
    .sort((a, b) => {
      const bt = new Date(String(b.created_at ?? b.updated_at ?? 0)).getTime();
      const at = new Date(String(a.created_at ?? a.updated_at ?? 0)).getTime();
      return bt - at;
    })
    .slice(0, 10);
  const hasTeamAccess = hasProjectCollaborationAccess(authData, project, projectMembers);
  const protectedReadStatuses = [
    authResult.status,
    projectMembersResult.status,
    taskResult.status,
    requirementResult.status,
    collaborationMessageResult.status,
    relayCommandResult.status,
    relayAckResult.status,
    relayResultResult.status,
    liveNodeResult.status,
    liveWorkstationResult.status,
    gitExecutionResult.status,
    gitActivityResult.status,
  ];
  const hasProtectedReadAuthError = protectedReadStatuses.some((status) => status === 401 || status === 403);
  const derivedTeamError =
    typeof searchParams?.team_error === "string"
      ? searchParams.team_error
      : hasProtectedReadAuthError
        ? "当前登录态没有拿到真实协作数据，但当前项目页入口壳里的 2D 开发者模式入口还在。请重新登录后再看 requirement、回执和最终回复。"
        : undefined;
  const derivedTeamNotice =
    typeof searchParams?.team_notice === "string"
      ? searchParams.team_notice
      : hasProtectedReadAuthError
        ? "当前项目页入口壳和其中的 2D 开发者模式入口还在，但受保护的协作数据没有读到。"
        : undefined;
  const collaborationPreview = decodePreviewSearchParam(searchParams?.collab_preview);
  const gitSyncPreview = decodePreviewSearchParam(searchParams?.git_sync_preview);
  const gitRollbackPreview = decodePreviewSearchParam(searchParams?.git_preview);
  const initialManagerDrawerKind:
    | "npc-create"
    | "npc-dialog"
    | "npc-profile"
    | "npc-bind"
    | "npc-skills"
    | "exchange-detail"
    | "computer-connect"
    | "computer-threads"
    | "skill-create"
    | "skill-github-import"
    | "skill-detail"
    | "development-module"
    | undefined =
    typeof searchParams?.drawer === "string" &&
    [
      "npc-create",
      "npc-dialog",
      "npc-profile",
      "npc-bind",
      "npc-skills",
      "exchange-detail",
      "computer-connect",
      "computer-threads",
      "skill-create",
      "skill-github-import",
      "skill-detail",
      "development-module",
    ].includes(searchParams.drawer)
      ? (searchParams.drawer as
          | "npc-create"
          | "npc-dialog"
          | "npc-profile"
          | "npc-bind"
          | "npc-skills"
          | "exchange-detail"
          | "computer-connect"
          | "computer-threads"
          | "skill-create"
          | "skill-github-import"
          | "skill-detail"
          | "development-module")
      : undefined;

  const tokenSpend = sumUsageCost(usage);
  const economy = buildEconomyBalance({
    projectName: String(project.name ?? `项目 ${params.id.slice(0, 8)}`),
    requirementCount: requirements.length,
    tasks,
    config: {
      nodes: asArray<AnyRecord>(config.nodes),
      providers: asArray<AnyRecord>(config.providers),
      workstations: asArray<AnyRecord>(config.workstations),
    },
    runnerCommandCount: relayCommands.length,
    relayTimelineCount: relayTimeline.length,
    tokenSpend,
    activeTaskCount: activeTasks.length,
    blockedTaskCount: blockedTasks.length,
    pendingApprovalCount: pendingApprovals.length,
    completedTaskCount: tasks.length - activeTasks.length,
  });

  return (
    <ProjectPlayableShell
      project={{
        id: String(project.id ?? params.id),
        name: String(project.name ?? `项目 ${params.id.slice(0, 8)}`),
        description: String(project.description ?? "").trim() || "当前先以可玩的农场地图为主，平台信息保持轻量，不压住游戏视野。",
        collaboration_config: project.collaboration_config ?? {},
        githubUrl: project.github_url ?? null,
        localGitUrl: project.local_git_url ?? null,
        defaultBranch: project.default_branch ?? "main",
        developBranch: project.develop_branch ?? "develop",
        projectType: project.project_type ?? null,
      }}
      config={config}
      tasks={tasks}
      requirements={requirements}
      economy={economy}
      requirementCount={requirements.length}
      approvals={approvals.filter((item) => String(item.project_id ?? "") === String(project.id))}
      handoffs={handoffs.filter((item) => {
        const taskId = String(item.task_id ?? "");
        return String(item.project_id ?? item.payload?.project_id ?? "") === String(project.id) || (taskId && taskIds.has(taskId));
      })}
      collaborationMessages={collaborationMessages}
      runnerCommandCount={relayCommands.length}
      relayTimeline={relayTimeline}
      gitExecution={gitExecution}
      gitActivity={gitActivity}
      collaborationPreview={collaborationPreview}
      gitSyncPreview={gitSyncPreview}
      gitRollbackPreview={gitRollbackPreview}
      codexInbox={codexInbox}
      team={[
        {
          id: "codex-captain",
          name: "Codex 队长",
          role: "主程 / 主线整合",
          status: "已接入",
          summary: "负责接收基地指令，把地图主线、平台接入和后续线程协作收回同一条线。",
        },
        {
          id: "dispatch-scout",
          name: "调度副官",
          role: "需求派发 / 节奏整理",
          status: requirements.length > 0 ? "待扩编" : "空闲",
          summary: "后续承担任务播种、需求整理和派发节奏。",
        },
        {
          id: "runner-chief",
          name: "机房工头",
          role: "电脑 / Runner / 构建",
          status: onlineComputers > 0 ? "在线" : "待接入",
          summary: "后续承担固定电脑和 Runner 通讯，把真实机器接进基地。",
        },
      ]}
      members={projectMembers.map((member, index) => ({
        id: String(member.user_id ?? member.user?.id ?? member.id ?? `member-${index + 1}`),
        user_id: String(member.user_id ?? member.user?.id ?? ""),
        email: String(member.email ?? member.user?.email ?? ""),
        name: String(member.name ?? member.user?.name ?? member.email ?? member.user?.email ?? `协作者 ${index + 1}`),
        role: String(member.role ?? "collaborator"),
        status: String(member.status ?? "active"),
        summary: String(member.email ?? member.user?.email ?? ""),
        last_seen_at: member.last_seen_at ?? member.user?.last_seen_at ?? null,
        online_state: member.online_state ?? member.user?.online_state ?? null,
        online_label: member.online_label ?? member.user?.online_label ?? null,
        online_age_seconds: member.online_age_seconds ?? member.user?.online_age_seconds ?? null,
        online_fresh_seconds: member.online_fresh_seconds ?? member.user?.online_fresh_seconds ?? null,
        last_project_seen_at: member.last_project_seen_at ?? null,
        last_project_path: member.last_project_path ?? null,
        project_presence_state: member.project_presence_state ?? null,
        project_presence_label: member.project_presence_label ?? null,
        project_presence_age_seconds: member.project_presence_age_seconds ?? null,
        project_presence_fresh_seconds: member.project_presence_fresh_seconds ?? null,
      }))}
      currentUser={{
        id: authData?.user?.id ?? null,
        email: authData?.user?.email ?? null,
        name: authData?.user?.name ?? null,
      }}
      authState={{
        isAuthenticated: Boolean(authData?.user?.id),
        userName: authData?.user?.name ?? null,
        hasProjectAccess: hasTeamAccess,
      }}
      hud={{
        tokenSpend: tokenSpend.toFixed(2),
        aiCount: config.providers.length,
        onlineComputers,
        activeTasks: activeTasks.length,
        blockedCount: blockedTasks.length,
        pendingApprovals: pendingApprovals.length,
      }}
      initialZone={typeof searchParams?.zone === "string" ? searchParams.zone : undefined}
      initialPanelOpen={searchParams?.panel === "team"}
      initialModeId={typeof searchParams?.mode === "string" ? searchParams.mode : undefined}
      initialPanelView={
        typeof searchParams?.tab === "string" &&
        ["human-party", "computers", "npc-create", "machine-room", "exchange", "git", "skills", "schedule", "serial-tv", "ai-debug", "ai-simulation", "development-workshop"].includes(searchParams.tab)
          ? (searchParams.tab as "human-party" | "computers" | "npc-create" | "machine-room" | "exchange" | "git" | "skills" | "schedule" | "serial-tv" | "ai-debug" | "ai-simulation" | "development-workshop")
          : undefined
      }
      initialExchangeSectionId={typeof searchParams?.exchange_section === "string" ? searchParams.exchange_section : undefined}
      initialExchangeComposerMode={
        typeof searchParams?.exchange_composer === "string" &&
        ["sync", "dispatch", "relay"].includes(searchParams.exchange_composer)
          ? (searchParams.exchange_composer as "sync" | "dispatch" | "relay")
          : undefined
      }
      initialHumanPartyFocusId={typeof searchParams?.human_party === "string" ? searchParams.human_party : undefined}
      initialComputerFocusId={typeof searchParams?.computer === "string" ? searchParams.computer : undefined}
      initialNpcCreateSubview={
        typeof searchParams?.npc_view === "string" && ["threads", "seats", "editor"].includes(searchParams.npc_view)
          ? (searchParams.npc_view as "threads" | "seats" | "editor")
          : undefined
      }
      initialSeatFocusId={typeof searchParams?.seat === "string" ? searchParams.seat : undefined}
      initialManagerDrawerKind={initialManagerDrawerKind}
      initialManagerDrawerId={typeof searchParams?.drawer_id === "string" ? searchParams.drawer_id : undefined}
      initialBindThreadId={typeof searchParams?.bind_thread === "string" ? searchParams.bind_thread : undefined}
      initialBindNodeId={typeof searchParams?.bind_node === "string" ? searchParams.bind_node : undefined}
      initialNpcName={typeof searchParams?.npc_name === "string" ? searchParams.npc_name : undefined}
      initialNpcResponsibility={typeof searchParams?.npc_role === "string" ? searchParams.npc_role : undefined}
      skillReturnTo={typeof searchParams?.return_to === "string" ? searchParams.return_to : undefined}
      teamNotice={derivedTeamNotice}
      teamError={derivedTeamError}
        collaborationAuthBlocked={hasProtectedReadAuthError}
        pairingNodeId={typeof searchParams?.pairing_node === "string" ? searchParams.pairing_node : undefined}
        pairingToken={typeof searchParams?.pairing_token === "string" ? searchParams.pairing_token : undefined}
        computerConnectServerUrl={computerConnectServerUrl}
        workstationTokenId={
          typeof searchParams?.adapter_workstation === "string" ? searchParams.adapter_workstation : undefined
        }
        workstationToken={typeof searchParams?.adapter_token === "string" ? searchParams.adapter_token : undefined}
      />
    );
  }
