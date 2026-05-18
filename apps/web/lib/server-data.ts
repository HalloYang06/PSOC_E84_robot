import { getApiBaseUrl } from "./config";
import { cookies } from "next/headers";

const ACCESS_TOKEN_COOKIE = "farm_access_token";
const LEGACY_ACCESS_TOKEN_COOKIE = "搴勫洯璁块棶浠ょ墝";

export class ApiRequestError extends Error {
  status: number;

  constructor(status: number, message?: string) {
    super(message ?? `HTTP ${status}`);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

export type ApiLoadState<T> = {
  data: T;
  status: number;
  error: ApiRequestError | null;
};

function okState<T>(data: T): ApiLoadState<T> {
  return { data, status: 200, error: null };
}

function errorState<T>(error: unknown, fallback: T, message: string): ApiLoadState<T> {
  if (error instanceof ApiRequestError) {
    return { data: fallback, status: error.status, error };
  }
  return { data: fallback, status: 500, error: new ApiRequestError(500, message) };
}

function unwrapData<T>(json: unknown): T {
  if (json && typeof json === "object" && "data" in json) {
    return (json as { data: T }).data;
  }
  return json as T;
}

function asArray<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object" && "items" in value && Array.isArray((value as { items?: unknown[] }).items)) {
    return ((value as { items: T[] }).items) ?? [];
  }
  return [];
}

function normalizePathList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

function normalizeObject(value: unknown): Record<string, any> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, any>;
  }
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, any>;
      }
    } catch {}
  }
  return {};
}

function pickNormalizedObject(...values: unknown[]): Record<string, any> {
  for (const value of values) {
    const normalized = normalizeObject(value);
    if (Object.keys(normalized).length > 0) return normalized;
  }
  return {};
}

const LEGACY_POLLUTED_PHRASE_MAP: Array<[RegExp, string]> = [
  [/鍦ㄧ嚎/g, "在线"],
  [/绂荤嚎/g, "离线"],
  [/鐮斿彂鍩哄湴/g, "研发基地"],
  [/寮€鍙戜富绾/g, "开发主线"],
  [/寮�鍙戜富绾/g, "开发主线"],
  [/鏈懡鍚嶄换鍔/g, "未命名任务"],
  [/浠诲姟/g, "任务"],
];

const LATIN1_MOJIBAKE_MARKER_REGEX = /(?:Ã.|Â.|â.|ðŸ|ï¿|¢|¤|¦|œ|ž|€|™)/;
const COMMON_MOJIBAKE_MARKER_REGEX = /(?:[\uFFFD�]|鍦ㄧ嚎|绂荤嚎|鐮斿彂鍩哄湴|寮€鍙戜富绾|寮�鍙戜富绾|鏈懡鍚嶄换鍔|浠诲姟|搴勫洯璁块棶浠ょ墝)/g;
const ALL_QUESTION_MARKS_REGEX = /^\?+$/;

function mojibakeScore(value: string): number {
  if (!value) return 0;
  const latinMarkers = value.match(/(?:Ã.|Â.|â.|ðŸ|ï¿|¢|¤|¦|œ|ž|€|™)/g);
  const commonMarkers = value.match(COMMON_MOJIBAKE_MARKER_REGEX);
  return (latinMarkers?.length ?? 0) * 2 + (commonMarkers?.length ?? 0) * 3;
}

function decodeLikelyLatin1Mojibake(value: string): string {
  if (!LATIN1_MOJIBAKE_MARKER_REGEX.test(value)) return value;
  const bytes: number[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const charCode = value.charCodeAt(index);
    if (charCode > 0xff) return value;
    bytes.push(charCode);
  }
  try {
    // Only keep decoded text when it actually reduces mojibake markers.
    const decoded = new TextDecoder("utf-8", { fatal: false }).decode(Uint8Array.from(bytes));
    if (!decoded) return value;
    return mojibakeScore(decoded) < mojibakeScore(value) ? decoded : value;
  } catch {
    return value;
  }
}

function isQuestionMarkPolluted(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  if (ALL_QUESTION_MARKS_REGEX.test(trimmed)) return true;
  const questionMarks = trimmed.match(/\?/g)?.length ?? 0;
  return questionMarks >= 4 && questionMarks >= Math.ceil(trimmed.length / 2);
}

function normalizeDisplayText(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) return fallback;
  let normalized = String(value).replace(/\r\n?/g, "\n");
  if (!normalized.trim()) return fallback;

  normalized = decodeLikelyLatin1Mojibake(normalized);
  for (const [pattern, replacement] of LEGACY_POLLUTED_PHRASE_MAP) {
    normalized = normalized.replace(pattern, replacement);
  }
  normalized = normalized.replace(/[\uFFFD�]+/g, "").trim();
  if (isQuestionMarkPolluted(normalized)) return fallback;
  return normalized || fallback;
}

function normalizeOptionalDisplayText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  return normalizeDisplayText(value, "") || null;
}

function isCodexSessionId(value: unknown): boolean {
  return String(value ?? "").trim().toLowerCase().startsWith("codex-session-");
}

function normalizeRequirementStatusLabel(value: unknown): string {
  switch (String(value ?? "").trim().toLowerCase()) {
    case "done":
    case "closed":
    case "completed":
    case "resolved":
      return "done";
    case "in_progress":
    case "processing":
    case "active":
    case "running":
    case "accepted":
      return "active";
    case "queued":
    case "open":
    case "routed":
    case "waiting_response":
      return "queued";
    case "blocked":
    case "failed":
    case "error":
      return "blocked";
    default:
      return "queued";
  }
}

function normalizeMessageProofStage(value: unknown): "dispatch" | "progress" | "final_reply" | "comment" {
  switch (String(value ?? "").trim().toLowerCase()) {
    case "requirement_dispatch":
      return "dispatch";
    case "requirement_final_reply":
      return "final_reply";
    case "requirement_progress_ack":
    case "agent_report":
    case "runner_ack":
    case "runner_result":
      return "progress";
    default:
      return "comment";
  }
}

function normalizeDisplayFieldsInObject(value: Record<string, any>, keys: string[]): Record<string, any> {
  const normalized = { ...value };
  for (const key of keys) {
    if (!(key in normalized)) continue;
    if (normalized[key] === null || normalized[key] === undefined) continue;
    if (!["string", "number", "boolean"].includes(typeof normalized[key])) continue;
    normalized[key] = normalizeDisplayText(normalized[key], "");
  }
  return normalized;
}

function normalizeWorkstation(value: unknown, index: number) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  const metadata = normalizeDisplayFieldsInObject(pickNormalizedObject(item.metadata, item.extra_data), [
    "display_name",
    "displayName",
    "name",
    "responsibility",
    "role",
    "description",
    "notes",
    "label",
    "scene",
    "scene_key",
    "avatar_key",
    "sprite_key",
  ]);
  const preferredName = item.name ?? item.label ?? metadata.display_name ?? metadata.name ?? null;
  const readPaths = normalizePathList(item.read_paths ?? item.readPaths ?? item.read_dirs ?? item.readable_paths);
  const writePaths = normalizePathList(item.write_paths ?? item.writePaths ?? item.write_dirs ?? item.writable_paths);
  return {
    ...item,
    id: String(item.id ?? item.name ?? item.label ?? `station_${index + 1}`),
    name: normalizeDisplayText(preferredName ?? "", ""),
    metadata,
    agent_id: item.agent_id ?? item.agentId ?? null,
    runner_id: item.runner_id ?? item.runnerId ?? metadata.runner_id ?? null,
    computer_node: normalizeOptionalDisplayText(item.computer_node ?? item.computerNode ?? item.node ?? null),
    computer_node_id: item.computer_node_id ?? item.computerNodeId ?? item.node_id ?? item.nodeId ?? null,
    ai_provider: normalizeOptionalDisplayText(item.ai_provider ?? item.aiProvider ?? item.provider ?? null),
    ai_provider_id: item.ai_provider_id ?? item.aiProviderId ?? item.provider_id ?? item.providerId ?? null,
    status: String(item.status ?? "idle"),
    responsibility:
      normalizeOptionalDisplayText(
        item.responsibility ??
          item.responsibility_text ??
          item.role ??
          metadata.responsibility ??
          metadata.role ??
          null,
      ) ?? null,
    model: item.model ?? item.default_model ?? item.model_name ?? metadata.model ?? null,
    permission_level:
      item.permission_level ?? item.permissionLevel ?? item.access_level ?? item.permission ?? metadata.permission_level ?? null,
    seat_type: item.seat_type ?? item.seatType ?? metadata.seat_type ?? null,
    source_workstation_id: item.source_workstation_id ?? item.sourceWorkstationId ?? metadata.source_workstation_id ?? null,
    workstation_id: item.workstation_id ?? item.workstationId ?? metadata.workstation_id ?? null,
    skill_loadout: asArray<string>(item.skill_loadout ?? item.skillLoadout ?? metadata.skill_loadout),
    git_boundary: normalizePathList(item.git_boundary ?? item.gitBoundary ?? metadata.git_boundary),
    scene_key: item.scene_key ?? item.sceneKey ?? item.scene ?? metadata.scene_key ?? metadata.scene ?? null,
    sprite_key:
      item.sprite_key ??
      item.spriteKey ??
      item.avatar_key ??
      item.avatarKey ??
      metadata.sprite_key ??
      metadata.avatar_key ??
      null,
    x: item.x ?? item.map_x ?? item.mapX ?? metadata.x ?? metadata.map_x ?? metadata.mapX ?? null,
    y: item.y ?? item.map_y ?? item.mapY ?? metadata.y ?? metadata.map_y ?? metadata.mapY ?? null,
    read_paths: readPaths,
    write_paths: writePaths,
    description: normalizeOptionalDisplayText(item.description ?? item.notes ?? metadata.description ?? null),
    notes: normalizeOptionalDisplayText(item.notes ?? item.description ?? metadata.notes ?? null),
  };
}

function normalizeProvider(value: unknown, index: number) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  return {
    ...item,
    id: String(item.id ?? item.label ?? item.name ?? `provider_${index + 1}`),
    label: normalizeDisplayText(item.label ?? item.name ?? item.id ?? `provider ${index + 1}`, `provider ${index + 1}`),
    kind: item.kind ?? item.type ?? null,
    endpoint: item.endpoint ?? item.url ?? null,
    model: item.model ?? item.default_model ?? item.model_name ?? null,
    enabled: item.enabled ?? true,
  };
}

function normalizeComputerNode(value: unknown, index: number) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  const metadata = pickNormalizedObject(item.metadata, item.extra_data);
  const threadScan = pickNormalizedObject(metadata.thread_scan, metadata.threadScan);
  const deviceInterfaceScan = pickNormalizedObject(metadata.device_interface_scan, metadata.deviceInterfaceScan);
  return {
    ...item,
    id: String(item.id ?? item.label ?? item.name ?? `node_${index + 1}`),
    label: normalizeDisplayText(item.label ?? item.name ?? item.id ?? `node ${index + 1}`, `node ${index + 1}`),
    status: String(item.status ?? "offline"),
    runner_id: item.runner_id ?? item.runnerId ?? null,
    runner_name: normalizeOptionalDisplayText(item.runner_name ?? item.runnerName ?? null),
    runner_status: item.runner_status ?? item.runnerStatus ?? null,
    runner_last_heartbeat_at: item.runner_last_heartbeat_at ?? item.runnerLastHeartbeatAt ?? null,
    runner_heartbeat_age_seconds: item.runner_heartbeat_age_seconds ?? item.runnerHeartbeatAgeSeconds ?? null,
    runner_watch_state: item.runner_watch_state ?? item.runnerWatchState ?? null,
    runner_effective_status: item.runner_effective_status ?? item.runnerEffectiveStatus ?? null,
    runner_watch_fresh_seconds: item.runner_watch_fresh_seconds ?? item.runnerWatchFreshSeconds ?? null,
    runner_watch_detail: normalizeOptionalDisplayText(item.runner_watch_detail ?? item.runnerWatchDetail ?? null),
    connection_kind: item.connection_kind ?? item.connectionKind ?? item.connection_type ?? item.kind ?? null,
    workspace_root: item.workspace_root ?? item.workspaceRoot ?? item.workspace ?? item.workspace_path ?? null,
    git_root: item.git_root ?? item.gitRoot ?? item.repo_root ?? item.repository_root ?? null,
    read_paths: normalizePathList(item.read_paths ?? item.readPaths ?? item.read_dirs ?? item.readable_paths),
    write_paths: normalizePathList(item.write_paths ?? item.writePaths ?? item.write_dirs ?? item.writable_paths),
    thread_scan: threadScan,
    thread_scan_count: Number(threadScan.thread_count ?? threadScan.threadCount ?? 0) || 0,
    device_interface_scan: deviceInterfaceScan,
    device_interface_count: Number(deviceInterfaceScan.interface_count ?? deviceInterfaceScan.interfaceCount ?? 0) || 0,
    desktop_process_detected: Boolean(threadScan.desktop_process_detected ?? threadScan.desktopProcessDetected),
    desktop_bridge_connected: Boolean(threadScan.desktop_bridge_connected ?? threadScan.desktopBridgeConnected),
    desktop_delivery_mode: threadScan.desktop_delivery_mode ?? threadScan.desktopDeliveryMode ?? null,
    desktop_bridge_label: normalizeOptionalDisplayText(threadScan.desktop_bridge_label ?? threadScan.desktopBridgeLabel ?? null),
    desktop_bridge_note: normalizeOptionalDisplayText(threadScan.desktop_bridge_note ?? threadScan.desktopBridgeNote ?? null),
    host: item.host ?? null,
    os: item.os ?? item.platform ?? null,
    metadata,
  };
}

function normalizeCollaborationConfig(value: unknown) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  return {
    ...item,
    thread_workstations: asArray<any>(item.thread_workstations ?? item.threadWorkstations ?? item.workstations).map(
      (station, index) => normalizeWorkstation(station, index),
    ),
    ai_providers: asArray<any>(item.ai_providers ?? item.aiProviders ?? item.providers).map((provider, index) =>
      normalizeProvider(provider, index),
    ),
    computer_nodes: asArray<any>(item.computer_nodes ?? item.computerNodes ?? item.nodes).map((node, index) =>
      normalizeComputerNode(node, index),
    ),
  };
}

function normalizeProject(value: unknown, index = 0) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  const id = String(item.id ?? item.project_id ?? `project_${index + 1}`);
  const name = normalizeDisplayText(item.name ?? item.project_name ?? id, id);
  return {
    ...item,
    id,
    project_id: id,
    name,
    project_name: name,
    description: normalizeOptionalDisplayText(item.description ?? null),
    project_type: item.project_type ?? item.projectType ?? null,
    default_branch: item.default_branch ?? item.defaultBranch ?? "main",
    develop_branch: item.develop_branch ?? item.developBranch ?? "develop",
    github_url: item.github_url ?? item.githubUrl ?? null,
    local_git_url: item.local_git_url ?? item.localGitUrl ?? null,
    is_owner: Boolean(item.is_owner ?? item.isOwner ?? false),
    role: item.role ?? null,
    joined_at: item.joined_at ?? item.joinedAt ?? null,
    collaboration_config: normalizeCollaborationConfig(item.collaboration_config ?? item.collaborationConfig),
  };
}

function normalizeTaskDispatch(value: unknown) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  return {
    ...item,
    id: item.id ?? null,
    task_id: item.task_id ?? item.taskId ?? null,
    project_id: item.project_id ?? item.projectId ?? null,
    workstation_id: item.workstation_id ?? item.workstationId ?? null,
    workstation_name: normalizeOptionalDisplayText(item.workstation_name ?? item.workstationName ?? null),
    computer_node_id: item.computer_node_id ?? item.computerNodeId ?? null,
    ai_provider_id: item.ai_provider_id ?? item.aiProviderId ?? null,
    runner_id: item.runner_id ?? item.runnerId ?? null,
  };
}

function normalizeTask(value: unknown, index = 0) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  const id = String(item.id ?? item.task_id ?? `task_${index + 1}`);
  return {
    ...item,
    id,
    task_id: id,
    project_id: item.project_id ?? item.projectId ?? null,
    title: normalizeDisplayText(item.title ?? item.name ?? `task ${index + 1}`, `task ${index + 1}`),
    description: normalizeOptionalDisplayText(item.description ?? null),
    module: item.module ?? null,
    priority: item.priority ?? "P2",
    status: item.status ?? "draft",
    due_at: item.due_at ?? item.dueAt ?? item.deadline_at ?? item.deadlineAt ?? null,
    branch: item.branch ?? null,
    assignee_agent_id: item.assignee_agent_id ?? item.assigneeAgentId ?? item.assignee ?? null,
    reviewers: asArray<string>(item.reviewers),
    acceptance_criteria: asArray<string>(item.acceptance_criteria ?? item.acceptanceCriteria),
    latest_dispatch: item.latest_dispatch ? normalizeTaskDispatch(item.latest_dispatch) : null,
    requires_human_approval:
      item.requires_human_approval ?? item.requiresHumanApproval ?? String(item.status ?? "") === "waiting_approval",
    created_at: item.created_at ?? item.createdAt ?? null,
    updated_at: item.updated_at ?? item.updatedAt ?? null,
  };
}

function normalizeRequirement(value: unknown, index = 0) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  const id = String(item.id ?? item.requirement_id ?? `requirement_${index + 1}`);
  const fromAgent = item.from_agent ?? item.fromAgent ?? null;
  const toAgent = item.to_agent ?? item.toAgent ?? null;
  const status = item.status ?? "waiting_response";
  return {
    ...item,
    id,
    requirement_id: id,
    project_id: item.project_id ?? item.projectId ?? null,
    task_id: item.task_id ?? item.taskId ?? null,
    title: normalizeDisplayText(item.title ?? item.name ?? `requirement ${index + 1}`, `requirement ${index + 1}`),
    requirement_type: item.requirement_type ?? item.requirementType ?? "thread_request",
    module: item.module ?? null,
    priority: item.priority ?? "P2",
    status,
    status_label: normalizeRequirementStatusLabel(status),
    from_agent: fromAgent,
    fromAgent,
    to_agent: toAgent,
    toAgent,
    is_codex_session_target: isCodexSessionId(toAgent),
    context_summary: normalizeOptionalDisplayText(item.context_summary ?? item.contextSummary ?? null),
    expected_output: normalizeOptionalDisplayText(item.expected_output ?? item.expectedOutput ?? null),
    latest_response_at: item.last_response_at ?? item.lastResponseAt ?? null,
    last_activity_at:
      item.last_response_at ??
      item.lastResponseAt ??
      item.updated_at ??
      item.updatedAt ??
      item.created_at ??
      item.createdAt ??
      null,
    related_files: asArray<string>(item.related_files ?? item.relatedFiles),
    messages: asArray<any>(item.messages).map((message, messageIndex) =>
      normalizeCollaborationMessage({ ...message, requirement_id: id }, messageIndex),
    ),
  };
}

function normalizeCollaborationMessage(value: unknown, index = 0) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  const id = String(item.id ?? `message_${index + 1}`);
  const senderId = item.sender_id ?? item.senderId ?? null;
  const recipientId = item.recipient_id ?? item.recipientId ?? null;
  const messageType = item.message_type ?? item.messageType ?? "comment_message";
  const status = item.status ?? "open";
  const proofStage = normalizeMessageProofStage(messageType);
  return {
    ...item,
    id,
    project_id: item.project_id ?? item.projectId ?? null,
    task_id: item.task_id ?? item.taskId ?? null,
    dispatch_id: item.dispatch_id ?? item.dispatchId ?? null,
    approval_id: item.approval_id ?? item.approvalId ?? null,
    handoff_id: item.handoff_id ?? item.handoffId ?? null,
    requirement_id: item.requirement_id ?? item.requirementId ?? null,
    agent_id: item.agent_id ?? item.agentId ?? null,
    sender_type: item.sender_type ?? item.senderType ?? "human",
    sender_id: senderId,
    senderId,
    recipient_type: item.recipient_type ?? item.recipientType ?? null,
    recipient_id: recipientId,
    recipientId,
    message_type: messageType,
    messageType,
    status,
    proof_stage: proofStage,
    is_dispatch_signal: proofStage === "dispatch",
    is_final_reply: proofStage === "final_reply",
    is_progress_signal: proofStage !== "comment",
    sender_is_codex_session: isCodexSessionId(senderId),
    recipient_is_codex_session: isCodexSessionId(recipientId),
    title: normalizeOptionalDisplayText(item.title ?? null),
    body: normalizeDisplayText(item.body ?? "", ""),
    created_at: item.created_at ?? item.createdAt ?? null,
    updated_at: item.updated_at ?? item.updatedAt ?? null,
    signal_at: item.created_at ?? item.createdAt ?? item.updated_at ?? item.updatedAt ?? null,
  };
}

function normalizeWorkspaceProject(value: unknown, index = 0) {
  const project = normalizeProject(value, index);
  return {
    ...project,
    role: project.role ?? "collaborator",
    is_owner: Boolean(project.is_owner),
    joined_at: project.joined_at ?? null,
  };
}

function normalizeUser(value: unknown) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  const normalizedDisplayName = normalizeOptionalDisplayText(item.display_name ?? item.displayName ?? item.name ?? null);
  const normalizedName = normalizeOptionalDisplayText(item.name ?? item.display_name ?? item.displayName ?? null);
  return {
    ...item,
    id: item.id ?? null,
    email: item.email ?? null,
    name: normalizedName,
    display_name: normalizedDisplayName,
    global_role: item.global_role ?? item.globalRole ?? "member",
    is_active: item.is_active ?? item.isActive ?? true,
    bio: normalizeOptionalDisplayText(item.bio ?? null),
  };
}

function normalizeInvitation(value: unknown, index = 0) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  return {
    ...item,
    id: String(item.id ?? `invitation_${index + 1}`),
    project_id: item.project_id ?? item.projectId ?? item.project?.id ?? null,
    invited_by_user_id: item.invited_by_user_id ?? item.invitedByUserId ?? null,
    accepted_by_user_id: item.accepted_by_user_id ?? item.acceptedByUserId ?? null,
    project: item.project ? normalizeProject(item.project, index) : null,
  };
}

function normalizeWorkspace(value: unknown) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  return {
    ...item,
    user: item.user ? normalizeUser(item.user) : null,
    projects: asArray<any>(item.projects).map((project, index) => normalizeWorkspaceProject(project, index)),
    pending_invitations: asArray<any>(item.pending_invitations ?? item.pendingInvitations).map((invitation, index) =>
      normalizeInvitation(invitation, index),
    ),
  };
}

function normalizeMatchSummary(value: unknown) {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, any>;
  return {
    status: item.status ?? item.state ?? null,
    label: normalizeOptionalDisplayText(item.label ?? item.title ?? null),
    detail: normalizeOptionalDisplayText(item.detail ?? item.description ?? null),
    score: typeof item.score === "number" ? item.score : item.match_score ?? null,
    blockers: Array.isArray(item.blockers) ? item.blockers : normalizePathList(item.blockers),
    warnings: Array.isArray(item.warnings) ? item.warnings : normalizePathList(item.warnings),
    matchCount: Number(item.matchCount ?? item.match_count ?? item.count ?? 0) || 0,
  };
}

function normalizeWorkstationMatch(value: unknown, index: number) {
  const item = value && typeof value === "object" ? (value as Record<string, any>) : {};
  return {
    workstationId: item.workstationId ?? item.workstation_id ?? item.id ?? null,
    workstationName: normalizeDisplayText(
      item.workstationName ?? item.workstation_name ?? item.name ?? `workstation ${index + 1}`,
      `workstation ${index + 1}`,
    ),
    nodeId: item.nodeId ?? item.node_id ?? item.computer_node_id ?? null,
    nodeLabel: normalizeOptionalDisplayText(item.nodeLabel ?? item.node_label ?? item.computer_node ?? null),
    providerId: item.providerId ?? item.provider_id ?? item.ai_provider_id ?? null,
    providerLabel: normalizeOptionalDisplayText(item.providerLabel ?? item.provider_label ?? item.ai_provider ?? null),
    matchScore: typeof item.matchScore === "number" ? item.matchScore : item.match_score ?? null,
    matchReason: normalizeOptionalDisplayText(item.matchReason ?? item.match_reason ?? item.reason ?? null),
    readiness: item.readiness ?? item.status ?? null,
  };
}

function normalizeTaskBranch(task: any, projectId: string, index: number) {
  const branch = {
    id: String(task.id),
    title: normalizeDisplayText(task.title ?? "未命名任务", "未命名任务"),
    branch: task.branch ?? null,
    status: String(task.status ?? "draft"),
    assignee_agent_id: task.assignee_agent_id ?? null,
    reviewer_count: Array.isArray(task.reviewers) ? task.reviewers.length : 0,
    requires_human_approval: ["waiting_approval", "reviewing", "blocked"].includes(String(task.status ?? "")),
    diff_path: `/tasks/${task.id}/diff`,
    logs_path: `/tasks/${task.id}/logs`,
    context_path: `/tasks/${task.id}/context`,
    task_path: `/tasks/${task.id}`,
    rollback_path: `/git?project_id=${projectId}#rollback-panel`,
    readiness_summary: normalizeMatchSummary(task.readiness_summary ?? task.readinessSummary ?? task.dispatch_readiness),
    recommended_workstations: asArray<any>(
      task.recommended_workstations ?? task.recommendedWorkstations ?? task.workstation_matches ?? task.workstationMatches,
    ).map((match, matchIndex) => normalizeWorkstationMatch(match, matchIndex)),
    workstation_matches: asArray<any>(task.workstation_matches ?? task.workstationMatches).map((match, matchIndex) =>
      normalizeWorkstationMatch(match, matchIndex),
    ),
  };
  return branch;
}

async function fetchJson<T>(path: string): Promise<T> {
  const cookieStore = cookies();
  const accessToken =
    cookieStore.get(ACCESS_TOKEN_COOKIE)?.value ??
    cookieStore.get(LEGACY_ACCESS_TOKEN_COOKIE)?.value;
  const headers: Record<string, string> = {};
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const res = await fetch(`${getApiBaseUrl()}${path}`, { cache: "no-store", headers });
  if (!res.ok) {
    throw new ApiRequestError(res.status);
  }
  const json = await res.json();
  return unwrapData<T>(json);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const cookieStore = cookies();
  const accessToken =
    cookieStore.get(ACCESS_TOKEN_COOKIE)?.value ??
    cookieStore.get(LEGACY_ACCESS_TOKEN_COOKIE)?.value;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    cache: "no-store",
    headers,
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    throw new ApiRequestError(res.status);
  }
  const json = await res.json();
  return unwrapData<T>(json);
}

export async function getProjectsData() {
  try {
    const data = asArray<any>(await fetchJson<any>("/api/projects"));
    return data.map((item, index) => normalizeProject(item, index));
  } catch {}
  return [];
}

export async function getAgentsData() {
  try {
    const data = asArray<any>(await fetchJson<any>("/api/agents"));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getRunnersData() {
  try {
    const data = asArray<any>(await fetchJson<any>("/api/runners"));
    if (Array.isArray(data)) {
      return data.map((item: any) => ({
        ...item,
        computer_node_bindings: asArray<any>(item.computer_node_bindings ?? item.computerNodeBindings).map((binding) => ({
          ...binding,
          project_id: binding.project_id ?? binding.projectId ?? null,
          computer_node_id: binding.computer_node_id ?? binding.computerNodeId ?? null,
        })),
      }));
    }
  } catch {}
  return [];
}

export async function getTasksData() {
  return getTasksDataScoped();
}

export async function getTasksDataScopedState(options?: { projectIds?: string[] }): Promise<ApiLoadState<any[]>> {
  try {
    const query = new URLSearchParams();
    for (const projectId of options?.projectIds ?? []) {
      if (projectId) query.append("project_id", projectId);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const data = asArray<any>(await fetchJson<any>(`/api/tasks${suffix}`));
    return okState(Array.isArray(data) ? data.map((item, index) => normalizeTask(item, index)) : []);
  } catch (error) {
    return errorState(error, [], "TASKS_UNAVAILABLE");
  }
}

export async function getTasksDataScoped(options?: { projectIds?: string[] }) {
  return (await getTasksDataScopedState(options)).data;
}

export async function getUsageData() {
  try {
    const data = asArray<any>(await fetchJson<any>("/api/usage"));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getGitStatusData() {
  try {
    return await fetchJson<any>("/api/git/status");
  } catch {}
  return {
    provider: "local",
    supported: [
      "status",
      "projects/{id}/workspace",
      "projects/{id}/sync-github",
      "projects/{id}/rollback",
      "projects/{id}/activity",
      "activity",
    ],
    dangerous_operations_blocked: true,
  };
}

async function fetchJsonWithAsciiSession<T>(path: string): Promise<T> {
  const cookieStore = cookies();
  const accessToken = cookieStore.get(ACCESS_TOKEN_COOKIE)?.value;
  const headers: Record<string, string> = {};
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const res = await fetch(`${getApiBaseUrl()}${path}`, { cache: "no-store", headers });
  if (!res.ok) {
    throw new ApiRequestError(res.status);
  }
  const json = await res.json();
  return unwrapData<T>(json);
}

export async function getCurrentAuthState(): Promise<ApiLoadState<any | null>> {
  try {
    const data = await fetchJsonWithAsciiSession<any>("/api/auth/me");
    return okState({
      ...data,
      user: data?.user ? normalizeUser(data.user) : null,
      principal: data?.principal ?? null,
    });
  } catch (error) {
    return errorState(error, null, "AUTH_UNAVAILABLE");
  }
}

export async function getCurrentAuthData() {
  return (await getCurrentAuthState()).data;
}

export async function getApiHealthState(): Promise<ApiLoadState<Record<string, any> | null>> {
  try {
    const data = await fetchJson<any>("/api/health");
    const normalized = normalizeObject(data);
    const health = normalizeObject(normalized.data ?? normalized);
    return okState(Object.keys(health).length ? health : null);
  } catch (error) {
    return errorState(error, null, "API_HEALTH_UNAVAILABLE");
  }
}

export async function getWorkspaceData() {
  try {
    return normalizeWorkspace(await fetchJsonWithAsciiSession<any>("/api/auth/workspace"));
  } catch {}
  return null;
}

export async function getWorkspaceState() {
  try {
    const data = normalizeWorkspace(await fetchJsonWithAsciiSession<any>("/api/auth/workspace"));
    return { data, status: 200, error: null as ApiRequestError | null };
  } catch (error) {
    if (error instanceof ApiRequestError) {
      return { data: null, status: error.status, error };
    }
    return { data: null, status: 500, error: new ApiRequestError(500, "WORKSPACE_UNAVAILABLE") };
  }
}

export async function getContextHealthListData() {
  try {
    const data = asArray<any>(await fetchJson<any>("/api/context-health"));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getKnowledgeData() {
  try {
    const data = asArray<any>(await fetchJson<any>("/api/knowledge"));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getProjectKnowledgeDocumentsState(projectId: string): Promise<ApiLoadState<any[]>> {
  try {
    const data = asArray<any>(await fetchJson<any>(`/api/knowledge/projects/${projectId}/documents`));
    return okState(Array.isArray(data) ? data : []);
  } catch (error) {
    return errorState(error, [], "PROJECT_KNOWLEDGE_DOCUMENTS_UNAVAILABLE");
  }
}

export async function getProjectSkillsState(projectId: string): Promise<ApiLoadState<any[]>> {
  try {
    const data = asArray<any>(await fetchJson<any>(`/api/knowledge/projects/${projectId}/skills`));
    return okState(Array.isArray(data) ? data : []);
  } catch (error) {
    return errorState(error, [], "PROJECT_SKILLS_UNAVAILABLE");
  }
}

export async function getSeatSkillAssignmentsState(projectId: string): Promise<ApiLoadState<any[]>> {
  try {
    const data = asArray<any>(await fetchJson<any>(`/api/knowledge/projects/${projectId}/seat-skill-assignments`));
    return okState(Array.isArray(data) ? data : []);
  } catch (error) {
    return errorState(error, [], "SEAT_SKILL_ASSIGNMENTS_UNAVAILABLE");
  }
}

export async function getProjectBossPlansState(projectId: string, limit = 5): Promise<ApiLoadState<any[]>> {
  try {
    const query = new URLSearchParams({ limit: String(Math.max(1, Math.min(limit, 30))) });
    const data = asArray<any>(await fetchJson<any>(`/api/projects/${projectId}/boss-plans?${query.toString()}`));
    return okState(Array.isArray(data) ? data : []);
  } catch (error) {
    return errorState(error, [], "PROJECT_BOSS_PLANS_UNAVAILABLE");
  }
}

export async function getUsersData() {
  try {
    const data = asArray<any>(await fetchJson<any>("/api/auth/users"));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getInvitationsData() {
  try {
    const data = asArray<any>(await fetchJson<any>("/api/auth/invitations"));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getAuthSummaryData() {
  try {
    return await fetchJson<any>("/api/auth/summary");
  } catch {}
  return {
    users: 0,
    pending_invitations: 0,
    accepted_invitations: 0,
    project_members: 0,
  };
}

export async function getProjectMembersState(projectId: string): Promise<ApiLoadState<any[]>> {
  try {
    const data = asArray<any>(await fetchJson<any>(`/api/auth/projects/${projectId}/members`));
    return okState(Array.isArray(data) ? data : []);
  } catch (error) {
    return errorState(error, [], "PROJECT_MEMBERS_UNAVAILABLE");
  }
}

export async function getProjectMembersData(projectId: string) {
  return (await getProjectMembersState(projectId)).data;
}

export async function markProjectPresenceState(projectId: string, path?: string): Promise<ApiLoadState<any | null>> {
  try {
    const data = await postJson<any>(`/api/projects/${projectId}/presence`, { path: path ?? `/projects/${projectId}` });
    return okState(data);
  } catch (error) {
    return errorState(error, null, "PROJECT_PRESENCE_UNAVAILABLE");
  }
}

export async function getApprovalsData(taskId?: string) {
  try {
    const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
    const data = asArray<any>(await fetchJson<any>(`/api/approvals${query}`));
    if (data.length >= 0) return data;
  } catch {}
  return [];
}

export async function getRequirementsState(options?: { projectIds?: string[] }): Promise<ApiLoadState<any[]>> {
  try {
    const query = new URLSearchParams();
    for (const projectId of options?.projectIds ?? []) {
      if (projectId) query.append("project_id", projectId);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const data = asArray<any>(await fetchJson<any>(`/api/requirements${suffix}`));
    return okState(data.map((item, index) => normalizeRequirement(item, index)));
  } catch (error) {
    return errorState(error, [], "REQUIREMENTS_UNAVAILABLE");
  }
}

export async function getRequirementsData(options?: { projectIds?: string[] }) {
  return (await getRequirementsState(options)).data;
}

export async function getProjectData(projectId: string) {
  try {
    return normalizeProject(await fetchJson<any>(`/api/projects/${projectId}`));
  } catch {}
  return null;
}

export async function getProjectState(projectId: string) {
  try {
    const data = normalizeProject(await fetchJson<any>(`/api/projects/${projectId}`));
    return { data, status: 200, error: null as ApiRequestError | null };
  } catch (error) {
    if (error instanceof ApiRequestError) {
      return { data: null, status: error.status, error };
    }
    return { data: null, status: 500, error: new ApiRequestError(500, "PROJECT_UNAVAILABLE") };
  }
}

export async function getProjectComputerNodesState(projectId: string): Promise<ApiLoadState<any[]>> {
  try {
    const data = asArray<any>(
      await fetchJson<any>(`/api/collaboration/projects/${projectId}/computer-nodes`),
    );
    return okState(Array.isArray(data) ? data.map((item, index) => normalizeComputerNode(item, index)) : []);
  } catch (error) {
    return errorState(error, [], "PROJECT_COMPUTER_NODES_UNAVAILABLE");
  }
}

export async function getProjectComputerNodesData(projectId: string) {
  return (await getProjectComputerNodesState(projectId)).data;
}

export async function getProjectThreadWorkstationsState(projectId: string): Promise<ApiLoadState<any[]>> {
  try {
    const data = asArray<any>(
      await fetchJson<any>(`/api/collaboration/projects/${projectId}/thread-workstations`),
    );
    return okState(Array.isArray(data) ? data.map((item, index) => normalizeWorkstation(item, index)) : []);
  } catch (error) {
    return errorState(error, [], "PROJECT_THREAD_WORKSTATIONS_UNAVAILABLE");
  }
}

export async function getProjectThreadWorkstationsData(projectId: string) {
  return (await getProjectThreadWorkstationsState(projectId)).data;
}

export async function getProjectThreadWorkstationAdapterConfigState(
  projectId: string,
  workstationId: string,
): Promise<ApiLoadState<Record<string, any> | null>> {
  try {
    const data = await fetchJson<any>(
      `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(workstationId)}/adapter-config`,
    );
    return okState(normalizeObject(data));
  } catch (error) {
    return errorState(error, null, "PROJECT_THREAD_WORKSTATION_ADAPTER_CONFIG_UNAVAILABLE");
  }
}

export async function getProjectWorkstationsState(projectId: string): Promise<ApiLoadState<any[]>> {
  try {
    const data = asArray<any>(
      await fetchJson<any>(`/api/projects/${projectId}/workstations`),
    );
    return okState(
      Array.isArray(data)
        ? data.map((item) => ({
            id: String(item.id ?? ""),
            config_id: String(item.config_id ?? item.configId ?? item.id ?? ""),
            name: String(item.name ?? ""),
            description: item.description ?? null,
            lead_seat_id: item.lead_seat_id ?? item.leadSeatId ?? null,
            review_policy: item.review_policy ?? item.reviewPolicy ?? null,
            sort_order: Number(item.sort_order ?? item.sortOrder ?? 0) || 0,
            seat_count: Number(item.seat_count ?? item.seatCount ?? 0) || 0,
            extra_data: item.extra_data ?? item.extraData ?? null,
          }))
        : [],
    );
  } catch (error) {
    return errorState(error, [], "PROJECT_WORKSTATIONS_UNAVAILABLE");
  }
}

export async function getProjectWorkstationsData(projectId: string) {
  return (await getProjectWorkstationsState(projectId)).data;
}

export async function getAgentData(agentId: string) {
  try {
    return await fetchJson<any>(`/api/agents/${agentId}`);
  } catch {}
  return null;
}

export async function getRunnerData(runnerId: string) {
  try {
    return await fetchJson<any>(`/api/runners/${runnerId}`);
  } catch {}
  return null;
}

export async function getRunnerWorkspaceData(runnerId: string) {
  try {
    return await fetchJson<any>(`/api/runners/${runnerId}/workspace`);
  } catch {}
  return null;
}

export async function getTaskData(taskId: string) {
  try {
    return normalizeTask(await fetchJson<any>(`/api/tasks/${taskId}`));
  } catch {}
  return null;
}

export async function getTaskGateData(taskId: string) {
  try {
    return await fetchJson<any>(`/api/tasks/${taskId}/gate`);
  } catch {}
  return {
    task_id: taskId,
    blocked: true,
    pending_high_risk_count: null,
    blocked_next_statuses: [],
    first_blocking_approval: null,
    pending_high_risk_approvals: [],
    unavailable: true,
  };
}

export async function getTaskProfessionalViewState(taskId: string): Promise<ApiLoadState<any | null>> {
  try {
    const data = await fetchJson<any>(`/api/tasks/${encodeURIComponent(taskId)}/professional-view`);
    return okState(data && typeof data === "object" ? data : null);
  } catch (error) {
    return errorState(error, null, "TASK_PROFESSIONAL_VIEW_UNAVAILABLE");
  }
}

export async function getTaskEventsData(taskId: string) {
  try {
    const data = asArray<any>(await fetchJson<any>(`/api/tasks/${taskId}/events`));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getTaskContextHealthData(taskId: string) {
  try {
    return await fetchJson<any>(`/api/tasks/${taskId}/context-health`);
  } catch {}
  return null;
}

export async function getAuditData() {
  try {
    const data = asArray<any>(await fetchJson<any>("/api/audit"));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getTaskContextHistoryData(taskId: string) {
  try {
    const data = asArray<any>(await fetchJson<any>(`/api/tasks/${taskId}/context-health/history`));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getTaskHandoffsData(taskId: string) {
  try {
    const data = asArray<any>(await fetchJson<any>(`/api/tasks/${taskId}/handoffs`));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getTaskAuditData(taskId: string) {
  try {
    const data = asArray<any>(await fetchJson<any>(`/api/tasks/${taskId}/audit`));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getProjectAuditData(projectId: string) {
  try {
    const data = asArray<any>(await fetchJson<any>(`/api/projects/${projectId}/audit`));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getCollaborationMessagesState(options?: {
  projectId?: string;
  taskId?: string;
  approvalId?: string;
  handoffId?: string;
  requirementId?: string;
  agentId?: string;
  messageType?: string;
  status?: string;
}): Promise<ApiLoadState<any[]>> {
  try {
    const query = new URLSearchParams();
    if (options?.projectId) query.set("project_id", options.projectId);
    if (options?.taskId) query.set("task_id", options.taskId);
    if (options?.approvalId) query.set("approval_id", options.approvalId);
    if (options?.handoffId) query.set("handoff_id", options.handoffId);
    if (options?.requirementId) query.set("requirement_id", options.requirementId);
    if (options?.agentId) query.set("agent_id", options.agentId);
    if (options?.messageType) query.set("message_type", options.messageType);
    if (options?.status) query.set("status", options.status);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const data = asArray<any>(await fetchJson<any>(`/api/collaboration/messages${suffix}`));
    return okState(Array.isArray(data) ? data.map((item, index) => normalizeCollaborationMessage(item, index)) : []);
  } catch (error) {
    return errorState(error, [], "COLLABORATION_MESSAGES_UNAVAILABLE");
  }
}

export async function getCollaborationMessagesData(options?: {
  projectId?: string;
  taskId?: string;
  approvalId?: string;
  handoffId?: string;
  requirementId?: string;
  agentId?: string;
  messageType?: string;
}) {
  return (await getCollaborationMessagesState(options)).data;
}

export async function getHandoffsData() {
  try {
    const data = asArray<any>(await fetchJson<any>("/api/handoffs"));
    if (Array.isArray(data)) return data;
  } catch {}
  return [];
}

export async function getProjectScorecardState(projectId: string): Promise<ApiLoadState<any | null>> {
  try {
    const data = await fetchJson<any>(`/api/qualification/projects/${projectId}/scorecard`);
    return okState(data && typeof data === "object" ? data : null);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      return { data: null, status: error.status, error };
    }
    return errorState(error, null, "PROJECT_SCORECARD_UNAVAILABLE");
  }
}

export async function getGitProjectWorkspaceData(projectId: string) {
  try {
    return await fetchJson<any>(`/api/git/projects/${projectId}/workspace`);
  } catch {}
  return null;
}

export async function getGitProjectExecutionState(projectId: string): Promise<ApiLoadState<any | null>> {
  try {
    const data = await fetchJson<any>(`/api/git/projects/${projectId}/execution`);
    return okState(data && typeof data === "object" ? data : null);
  } catch (error) {
    if (error instanceof ApiRequestError && (error.status === 401 || error.status === 403)) {
      return { data: null, status: error.status, error };
    }
    return errorState(error, null, "GIT_PROJECT_EXECUTION_UNAVAILABLE");
  }
}

export async function getGitProjectExecutionData(projectId: string) {
  return (await getGitProjectExecutionState(projectId)).data;
}

export async function getGitProjectActivityState(projectId: string): Promise<ApiLoadState<any[]>> {
  try {
    const data = asArray<any>(await fetchJson<any>(`/api/git/projects/${projectId}/activity`));
    return okState(Array.isArray(data) ? data : []);
  } catch (error) {
    if (error instanceof ApiRequestError && (error.status === 401 || error.status === 403)) {
      return { data: [], status: error.status, error };
    }
    return errorState(error, await getProjectAuditData(projectId), "GIT_PROJECT_ACTIVITY_UNAVAILABLE");
  }
}

export async function getGitProjectActivityData(projectId: string) {
  return (await getGitProjectActivityState(projectId)).data;
}

export async function getOverviewData() {
  const [projects, agents, runners, tasks, usage] = await Promise.all([
    getProjectsData(),
    getAgentsData(),
    getRunnersData(),
    getTasksData(),
    getUsageData(),
  ]);

  const fromApi = {
    projectName: projects[0]?.name ?? "研发基地",
    branch: projects[0]?.develop_branch ?? "开发主线",
    onlineAgents: agents.filter((item) => item.enabled !== false).length,
    totalAgents: agents.length,
    onlineRunners: runners.filter((item) => (item.status ?? "") === "online" || (item.status ?? "") === "鍦ㄧ嚎").length,
    totalRunners: runners.length,
    tokenCostToday: usage.reduce(
      (sum, item) => sum + Number(item.costCny ?? item.cost ?? ((item.cost_cents ?? 0) / 100)),
      0,
    ),
    budgetUsageRatio: 0.42,
    highRiskCount: tasks.filter((item) => ["blocked", "failed", "阻塞", "异常"].includes(item.status)).length,
    pendingHumanApprovals: tasks.filter((item) => item.requires_human_approval || item.status === "waiting_approval").length,
    gitSyncStatus: "pending",
  };

  if (projects.length || agents.length || runners.length || tasks.length || usage.length) {
    return fromApi;
  }
  return null;
}
