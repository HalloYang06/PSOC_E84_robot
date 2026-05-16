import { redirect } from "next/navigation";
import Link from "next/link";
import { existsSync } from "node:fs";
import { join } from "node:path";
import {
  getCurrentAuthState,
  getCollaborationMessagesState,
  getProjectComputerNodesState,
  getProjectBossPlansState,
  getProjectMembersState,
  getProjectState,
  getProjectThreadWorkstationAdapterConfigState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
} from "../../../../lib/server-data";
import { normalizeDevelopmentWorkshopStations } from "../../../../lib/development-workshop";
import { DEFAULT_PLATFORM_SKILL_LIBRARY } from "../../../../lib/platform-skills";
import { isNpcSeatRecord, platformProviderIdFromSeat } from "../../../../lib/platform-provider";
import { WorkbenchClient } from "./workbench-client";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type AnyRecord = Record<string, any>;

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? (value as AnyRecord) : {};
}

function firstText(...values: unknown[]) {
  for (const value of values) {
    const next = text(value, "");
    if (next) return next;
  }
  return "";
}

function deriveThreadKind(providerId: string, threadId: string) {
  const raw = `${providerId} ${threadId}`.toLowerCase();
  if (raw.includes("claude")) return "桌面执行线程";
  if (raw.includes("codex")) return "桌面执行线程";
  return providerId ? "执行线程" : "待绑定线程";
}

function publicProviderLabel(value: string) {
  const raw = `${value || ""}`.trim();
  if (!raw) return "";
  const lower = raw.toLowerCase();
  if (lower.includes("codex") || lower.includes("claude")) return "桌面线程";
  return raw;
}

function publicThreadKindLabel(value: string, providerId: string, threadId: string) {
  const raw = `${value || ""}`.trim();
  const lower = `${raw} ${providerId || ""} ${threadId || ""}`.toLowerCase();
  if (!raw) return deriveThreadKind(providerId, threadId);
  if (lower.includes("codex") || lower.includes("claude") || lower.includes("session")) return "桌面执行线程";
  return raw;
}

function publicThreadHealthLabel(value: string, automationEnabled: boolean) {
  const raw = `${value || ""}`.toLowerCase();
  if (automationEnabled || /ready|online|ok|watcher|已登记|就绪/.test(raw)) return "可接单";
  if (/fail|error|offline|不可用|失败/.test(raw)) return "需检查";
  if (/pending|waiting|待|未/.test(raw)) return "待确认";
  return value ? "已登记" : "待确认";
}

function publicDeliveryLabel(value: string, deliveryMode: string, desktopDeliveryMode: string) {
  const raw = `${value || ""} ${deliveryMode || ""} ${desktopDeliveryMode || ""}`.toLowerCase();
  if (raw.includes("desktop") || raw.includes("codex_desktop_ui")) return "桌面线程可见";
  if (raw.includes("app_server") || raw.includes("session")) return "后台线程同步";
  return value || "";
}

function publicDeliveryWarning(value: string, deliveryMode: string) {
  const rawMode = `${deliveryMode || ""}`.toLowerCase();
  if (rawMode.includes("codex_app_server")) return "平台会通过后台通道同步处理过程；用户仍可在工作台看最小回执。";
  return value ? "平台会把派单送到绑定桌面线程，完整过程在桌面版可追踪。" : "";
}

function codexDesktopThreadUrl(providerId: string, threadId: string) {
  const normalizedProvider = `${providerId} ${threadId}`.toLowerCase();
  if (!normalizedProvider.includes("codex")) return "";
  const raw = threadId.trim().replace(/^codex-session-/i, "");
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)) return "";
  return `codex://threads/${raw.toLowerCase()}`;
}

function safeProjectReturnPath(projectId: string, value: unknown) {
  const raw = text(value, "");
  if (!raw.startsWith(`/projects/${projectId}/`)) return "";
  if (/^\/\//.test(raw) || raw.includes("\\") || raw.includes("://")) return "";
  return raw;
}

function labelProjectReturnPath(value: string) {
  if (value.includes("/2d-upgrade")) return "← 返回主页面";
  if (value.includes("/datasets")) return "← 返回数据工场";
  if (value.includes("/ai-lab")) return "← 返回 AI 实验室";
  if (value.includes("/robotics")) return "← 返回机器人现场";
  if (value.includes("/observability")) return "← 返回观测台";
  if (value.includes("/skill-forge")) return "← 返回能力工坊";
  if (value.includes("/company")) return "← 返回公司层";
  if (value.includes("/workbench")) return "← 返回工作台";
  return "← 返回来源";
}

function localGitState(localPath: string) {
  const normalized = text(localPath, "");
  if (!normalized) {
    return { checked: false, exists: false, isGit: false, message: "" };
  }
  if (/^https?:\/\//i.test(normalized) || /^git@/i.test(normalized)) {
    return { checked: false, exists: false, isGit: false, message: "本地路径不是当前电脑目录，仅作为远程/说明。" };
  }
  try {
    const exists = existsSync(normalized);
    const isGit = exists && existsSync(join(normalized, ".git"));
    return {
      checked: true,
      exists,
      isGit,
      message: !exists
        ? "当前电脑找不到这个本地路径。"
        : isGit
          ? "当前电脑本地 Git 仓库可用。"
          : "当前电脑这个目录不是 Git 仓库。",
    };
  } catch {
    return { checked: true, exists: false, isGit: false, message: "当前电脑无法读取这个本地路径。" };
  }
}

export default async function WorkbenchPage({ params, searchParams }: { params: { id: string }; searchParams?: { embed?: string; seat?: string; seats?: string; team_notice?: string; team_error?: string; return_to?: string; from?: string } }) {
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    const query = new URLSearchParams();
    if (searchParams?.return_to) query.set("return_to", searchParams.return_to);
    if (searchParams?.from) query.set("from", searchParams.from);
    if (searchParams?.seat) query.set("seat", searchParams.seat);
    if (searchParams?.seats) query.set("seats", searchParams.seats);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${params.id}/workbench${suffix}`)}`);
  }

  const projectState = await getProjectState(params.id);
  const project = projectState.data;
  if (!project) {
    return (
      <main style={{ padding: 32, color: "#eaffff" }}>
        <p>项目不存在或无权限。</p>
        <Link href="/projects" style={{ color: "#93fbff" }}>← 返回项目列表</Link>
      </main>
    );
  }

  const [
    computerNodesState,
    threadWorkstationsState,
    projectWorkstationsState,
    projectMembersState,
    collaborationMessagesState,
    bossPlansState,
  ] = await Promise.all([
    getProjectComputerNodesState(params.id),
    getProjectThreadWorkstationsState(params.id),
    getProjectWorkstationsState(params.id),
    getProjectMembersState(params.id),
    getCollaborationMessagesState({ projectId: params.id }),
    getProjectBossPlansState(params.id, 5),
  ]);
  const liveNodes = asArray<AnyRecord>(computerNodesState.data);
  const liveThreadWorkstations = asArray<AnyRecord>(threadWorkstationsState.data);
  const projectWorkstations = asArray<AnyRecord>(projectWorkstationsState.data);
  const projectMembers = asArray<AnyRecord>(projectMembersState.data);

  const config = (project.collaboration_config ?? {}) as AnyRecord;
  const rawWorkstations = asArray<AnyRecord>(
    config.thread_workstations ?? config.threadWorkstations ?? config.workstations,
  );
  const seatRecords = (liveThreadWorkstations.length ? liveThreadWorkstations : rawWorkstations).filter((item) => isNpcSeatRecord(item));
  const adapterConfigs = await Promise.all(
    seatRecords.map(async (seat, index) => {
      const id = text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, `seat-${index}`);
      if (!id) return null;
      const state = await getProjectThreadWorkstationAdapterConfigState(params.id, id);
      return state.data ? { id, data: state.data } : null;
    }),
  );
  const adapterConfigBySeatId = new Map<string, AnyRecord>();
  for (const item of adapterConfigs) {
    if (item?.id && item.data) adapterConfigBySeatId.set(item.id, item.data);
  }
  const threadRecordById = new Map<string, AnyRecord>();
  for (const seat of liveThreadWorkstations) {
    const keys = [
      seat.id,
      seat.config_id,
      seat.row_id,
      seat.rowId,
      seat.thread_id,
      seat.threadId,
      seat.source_workstation_id,
      seat.sourceWorkstationId,
    ].map((value) => text(value, "")).filter(Boolean);
    for (const key of keys) threadRecordById.set(key, seat);
  }
  const configNodes = asArray<AnyRecord>(config.computer_nodes ?? config.nodes);
  const skillLibrary = [
    ...DEFAULT_PLATFORM_SKILL_LIBRARY,
    ...asArray<AnyRecord>(config.skill_library ?? config.skillLibrary),
  ].filter((item, index, list) => {
    const recordItem = item as AnyRecord;
    const id = text(recordItem.id ?? recordItem.skill_id ?? recordItem.slug, "");
    return id && list.findIndex((candidate) => {
      const candidateRecord = candidate as AnyRecord;
      return text(candidateRecord.id ?? candidateRecord.skill_id ?? candidateRecord.slug, "") === id;
    }) === index;
  });
  const workshopStations = normalizeDevelopmentWorkshopStations(config.development_workshop_stations);
  const workstationProfiles = (config.workstation_profiles && typeof config.workstation_profiles === "object")
    ? (config.workstation_profiles as AnyRecord)
    : {};

  const nodeMap = new Map<string, string>();
  for (const node of [...configNodes, ...liveNodes]) {
    const id = text(node?.id ?? node?.node_id, "");
    if (!id) continue;
    const name = text(node?.name ?? node?.label ?? node?.hostname ?? id, id);
    nodeMap.set(id, name);
  }

  const workstationNameById = new Map<string, string>();
  const leadByWorkstation = new Map<string, string>();
  const workstationByLeadIdentity = new Map<string, string>();
  const knowledgePathByWorkstation = new Map<string, string>();
  for (const ws of projectWorkstations) {
    const wsId = text(ws?.id, "");
    if (!wsId) continue;
    workstationNameById.set(wsId, text(ws?.name, wsId));
    const lead = text(ws?.lead_seat_id ?? ws?.leadSeatId, "");
    if (lead) {
      leadByWorkstation.set(wsId, lead);
      workstationByLeadIdentity.set(lead, wsId);
    }
    const extra = record(ws?.extra_data ?? ws?.extraData);
    const knowledgePath = text(
      ws?.knowledge_path ??
        ws?.knowledgePath ??
        extra.knowledge_path ??
        extra.knowledgePath,
      "",
    );
    if (knowledgePath) {
      knowledgePathByWorkstation.set(wsId, knowledgePath.replace(/\\/g, "/").replace(/^\/+/, ""));
    }
  }

  function identitySet(...values: unknown[]) {
    return new Set(values.map((value) => text(value, "")).filter(Boolean));
  }

  const leadByNode = new Map<string, string>();
  const inheritedSkillsByNode = new Map<string, string[]>();
  const inheritedSkillsByWorkstation = new Map<string, string[]>();
  const knowledgePathByNode = new Map<string, string>();
  for (const [nodeId, profile] of Object.entries(workstationProfiles)) {
    if (profile && typeof profile === "object") {
      const p = profile as AnyRecord;
      const lead = text(p.lead_seat_id ?? p.leadSeatId, "");
      if (lead) leadByNode.set(String(nodeId), lead);
      const inh = asArray<string>(p.skill_inheritance ?? p.skillInheritance)
        .map((s) => String(s).trim())
        .filter(Boolean);
      if (inh.length) inheritedSkillsByNode.set(String(nodeId), inh);
      if (inh.length) inheritedSkillsByWorkstation.set(String(nodeId), inh);
      const kp = text(p.knowledge_path ?? p.knowledgePath, "");
      if (kp) knowledgePathByNode.set(String(nodeId), kp);
      if (kp) knowledgePathByWorkstation.set(String(nodeId), kp.replace(/\\/g, "/").replace(/^\/+/, ""));
    }
  }

  const seats = seatRecords.map((seat, index) => {
    const id = text(seat.id ?? seat.config_id ?? seat.row_id, `seat-${index}`);
    const rowId = text(seat.row_id ?? seat.rowId, "");
    const name = text(seat.name ?? seat.title, `NPC ${index + 1}`);
    const ownIdentities = identitySet(seat.id, seat.row_id, seat.rowId, seat.config_id, seat.name, seat.thread_id, seat.threadId);
    const leadWorkstationId = Array.from(ownIdentities)
      .map((identity) => workstationByLeadIdentity.get(identity))
      .find((value): value is string => !!value);
    const workstationId = text(seat.workstation_id ?? seat.workstationId, "") || leadWorkstationId || "";
    const computerNodeId = text(seat.computer_node_id ?? seat.computerNodeId, "");
    const providerId = platformProviderIdFromSeat(seat) || text(seat.provider_id ?? seat.providerId, "");
    const providerLabel = publicProviderLabel(text(seat.provider_label ?? seat.providerLabel ?? providerId, providerId));
    const responsibility = text(seat.responsibility ?? seat.body, "待分配职责");
    const skillLoadout = asArray<string>(seat.skill_loadout ?? seat.skillLoadout).map((s) => String(s)).filter(Boolean);
    const inheritedSkills = workstationId
      ? (inheritedSkillsByWorkstation.get(workstationId) ?? [])
      : computerNodeId
        ? (inheritedSkillsByNode.get(computerNodeId) ?? [])
        : [];
    const workstationKnowledgePath = workstationId
      ? (knowledgePathByWorkstation.get(workstationId) ?? `docs/workstations/${workstationId}.md`)
      : computerNodeId
        ? (knowledgePathByNode.get(computerNodeId) ?? `docs/workstations/${computerNodeId}.md`)
        : "";
    const knowledgeSummary = text(seat.knowledge_summary ?? seat.knowledgeSummary, "");
    const model = text(seat.model, "");
    const permissionLevel = text(seat.permission_level ?? seat.permissionLevel, "");
    const meta = record(seat.metadata);
    const extra = record(seat.extra_data ?? seat.extraData);
    const adapterConfig = adapterConfigBySeatId.get(rowId || id) ?? adapterConfigBySeatId.get(id) ?? {};
    const automationEnabled = Boolean(
      seat.automation_enabled
      ?? seat.automationEnabled
      ?? meta.automation_enabled
      ?? meta.automationEnabled
      ?? extra.automation_enabled
      ?? extra.automationEnabled
      ?? false,
    );
    const adapter = { ...record(meta.adapter ?? extra.adapter), ...adapterConfig };
    const threadId = firstText(
      seat.target_thread_id,
      seat.targetThreadId,
      seat.session_id,
      seat.sessionId,
      seat.thread_id,
      seat.threadId,
      seat.source_workstation_id,
      seat.sourceWorkstationId,
      meta.target_thread_id,
      meta.targetThreadId,
      meta.session_id,
      meta.sessionId,
      meta.claude_session_id,
      meta.codex_thread_id,
      meta.thread_id,
      meta.threadId,
      meta.source_thread_id,
      meta.bound_thread_id,
      meta.source_workstation_id,
      extra.target_thread_id,
      extra.session_id,
      extra.thread_id,
      extra.source_thread_id,
      extra.bound_thread_id,
      extra.source_workstation_id,
    );
    const boundThreadRecord = threadRecordById.get(threadId) ?? threadRecordById.get(`codex-session-${threadId}`);
    const boundThreadMeta = record(boundThreadRecord?.metadata);
    const boundThreadExtra = record(boundThreadRecord?.extra_data ?? boundThreadRecord?.extraData);
    const boundThreadAdapter = record(boundThreadMeta.adapter ?? boundThreadExtra.adapter);
    const threadKind = publicThreadKindLabel(
      firstText(seat.thread_kind, seat.threadKind, meta.thread_kind, meta.threadKind, adapter.kind, ""),
      providerId,
      threadId,
    );
    const desktopDeliveryMode = firstText(
      adapter.desktop_delivery_mode,
      adapter.desktopDeliveryMode,
      meta.desktop_delivery_mode,
      meta.desktopDeliveryMode,
      boundThreadMeta.desktop_delivery_mode,
      boundThreadMeta.desktopDeliveryMode,
      boundThreadAdapter.desktop_delivery_mode,
      boundThreadAdapter.desktopDeliveryMode,
      "",
    );
    const deliveryMode = firstText(
      adapter.delivery_mode,
      adapter.deliveryMode,
      desktopDeliveryMode,
      meta.delivery_mode,
      meta.deliveryMode,
      boundThreadMeta.delivery_mode,
      boundThreadMeta.deliveryMode,
      boundThreadAdapter.delivery_mode,
      boundThreadAdapter.deliveryMode,
      threadId && providerId.toLowerCase().includes("codex") ? "codex_app_server" : "",
    );
    const deliveryLabel = firstText(
      adapter.delivery_label,
      adapter.deliveryLabel,
      desktopDeliveryMode === "codex_desktop_ui" ? "桌面线程可见" : "",
      meta.delivery_label,
      meta.deliveryLabel,
      boundThreadMeta.delivery_label,
      boundThreadMeta.deliveryLabel,
      boundThreadAdapter.delivery_label,
      boundThreadAdapter.deliveryLabel,
      boundThreadMeta.desktop_bridge_label,
      boundThreadMeta.desktopBridgeLabel,
      deliveryMode === "codex_app_server" ? "后台线程同步" : "",
    );
    const desktopProcessDetected = Boolean(
      meta.desktop_process_detected
      ?? meta.desktopProcessDetected
      ?? meta.codex_desktop_process_detected
      ?? adapter.desktop_process_detected
      ?? adapter.desktopProcessDetected
      ?? boundThreadMeta.desktop_process_detected
      ?? boundThreadMeta.desktopProcessDetected
      ?? boundThreadMeta.codex_desktop_process_detected
      ?? boundThreadAdapter.desktop_process_detected
      ?? boundThreadAdapter.desktopProcessDetected
      ?? false,
    );
    const desktopBridgeConnected = Boolean(
      meta.desktop_bridge_connected
      ?? meta.desktopBridgeConnected
      ?? meta.codex_desktop_bridge_connected
      ?? adapter.desktop_bridge_connected
      ?? adapter.desktopBridgeConnected
      ?? boundThreadMeta.desktop_bridge_connected
      ?? boundThreadMeta.desktopBridgeConnected
      ?? boundThreadMeta.codex_desktop_bridge_connected
      ?? boundThreadAdapter.desktop_bridge_connected
      ?? boundThreadAdapter.desktopBridgeConnected
      ?? false,
    );
    const desktopVisible = Boolean(
      meta.desktop_visible
      ?? meta.desktopVisible
      ?? adapter.desktop_visible
      ?? adapter.desktopVisible
      ?? boundThreadMeta.desktop_visible
      ?? boundThreadMeta.desktopVisible
      ?? boundThreadAdapter.desktop_visible
      ?? boundThreadAdapter.desktopVisible
      ?? (desktopBridgeConnected && desktopDeliveryMode === "codex_desktop_ui")
      ?? false,
    );
    const desktopBridgeLabel = firstText(
      meta.desktop_bridge_label,
      meta.desktopBridgeLabel,
      adapter.desktop_bridge_label,
      adapter.desktopBridgeLabel,
      boundThreadMeta.desktop_bridge_label,
      boundThreadMeta.desktopBridgeLabel,
      boundThreadAdapter.desktop_bridge_label,
      boundThreadAdapter.desktopBridgeLabel,
      "",
    );
    const desktopBridgeNote = firstText(
      meta.desktop_bridge_note,
      meta.desktopBridgeNote,
      meta.codex_desktop_bridge_note,
      adapter.desktop_bridge_note,
      adapter.desktopBridgeNote,
      boundThreadMeta.desktop_bridge_note,
      boundThreadMeta.desktopBridgeNote,
      boundThreadMeta.codex_desktop_bridge_note,
      boundThreadAdapter.desktop_bridge_note,
      boundThreadAdapter.desktopBridgeNote,
      "",
    );
    const desktopThreadUrl = firstText(
      meta.desktop_thread_url,
      meta.desktopThreadUrl,
      adapter.desktop_thread_url,
      adapter.desktopThreadUrl,
      boundThreadMeta.desktop_thread_url,
      boundThreadMeta.desktopThreadUrl,
      boundThreadAdapter.desktop_thread_url,
      boundThreadAdapter.desktopThreadUrl,
      codexDesktopThreadUrl(providerId, threadId),
    );
    const executorCwd = firstText(
      adapter.executor_cwd,
      adapter.executorCwd,
      meta.executor_cwd,
      meta.executorCwd,
      extra.cwd,
      extra.git_root,
      extra.workspace_root,
    );
    const deliveryWarning = firstText(
      adapter.delivery_warning,
      adapter.deliveryWarning,
      desktopDeliveryMode === "codex_desktop_ui"
        ? "平台会打开绑定桌面线程并把派单作为普通用户消息发送；完整处理过程会在桌面版显示。"
        : "",
      meta.delivery_warning,
      meta.deliveryWarning,
      boundThreadMeta.delivery_warning,
      boundThreadMeta.deliveryWarning,
      boundThreadAdapter.delivery_warning,
      boundThreadAdapter.deliveryWarning,
      deliveryMode === "codex_app_server"
        ? "平台会通过后台线程同步处理过程；用户仍可在工作台看最小回执和最终结果。"
        : "",
    );
    const rawThreadHealth = firstText(
      seat.bridge_health_label,
      seat.bridgeHealthLabel,
      seat.thread_health,
      seat.threadHealth,
      meta.bridge_health_label,
      meta.bridgeHealthLabel,
      meta.thread_health,
      meta.threadHealth,
      adapter.health,
      adapter.status,
      automationEnabled ? "watcher ready" : "待接入",
    );
    const threadHealth = publicThreadHealthLabel(rawThreadHealth, automationEnabled);
    const publicDelivery = publicDeliveryLabel(deliveryLabel, deliveryMode, desktopDeliveryMode);
    const publicWarning = publicDeliveryWarning(deliveryWarning, deliveryMode);
    const gitUserName = text(meta.git_user_name ?? meta.gitUserName, name);
    const gitUserEmail = text(
      meta.git_user_email ?? meta.gitUserEmail,
      `bot+${id}@noreply.invalid`,
    );
    const reviewPolicy = text(meta.review_policy ?? meta.reviewPolicy, "inherit");
    const leadSeatId = workstationId
      ? (leadByWorkstation.get(workstationId) ?? "")
      : (computerNodeId ? (leadByNode.get(computerNodeId) ?? "") : "");
    const isLead = !!leadSeatId && identitySet(id, rowId, seat.config_id, seat.name, threadId).has(leadSeatId);
    return {
      id,
      rowId,
      configId: text(seat.config_id ?? seat.configId, ""),
      name,
      workstationId,
      workstationName: workstationId ? (workstationNameById.get(workstationId) ?? workstationId) : "",
      computerNodeId,
      computerNodeName: computerNodeId ? nodeMap.get(computerNodeId) ?? computerNodeId : "",
      providerId,
      providerLabel,
      threadId,
      threadKind,
      threadHealth,
      deliveryMode,
      deliveryLabel: publicDelivery,
      deliveryWarning: publicWarning,
      desktopVisible,
      desktopProcessDetected,
      desktopBridgeConnected,
      desktopBridgeLabel,
      desktopBridgeNote,
      desktopThreadUrl,
      executorCwd,
      codexLaunchPrompt: text(meta.codex_launch_prompt ?? meta.codexLaunchPrompt, ""),
      metadata: meta,
      responsibility,
      skillLoadout,
      inheritedSkills,
      workstationKnowledgePath,
      knowledgeSummary,
      automationEnabled,
      model,
      permissionLevel,
      gitUserName,
      gitUserEmail,
      reviewPolicy,
      leadSeatId,
      isLead,
    };
  });

  const me = auth.data?.user as AnyRecord | null;
  const currentUserId = text(me?.id, "");
  const currentUserName = text(me?.name ?? me?.email ?? me?.id, currentUserId || "我");
  function decodedFocusValue(value: string) {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  }

  const focusSeatParam = text(searchParams?.seat, "");
  const focusSeatParams = [
    focusSeatParam,
    ...text(searchParams?.seats, "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
  ]
    .filter(Boolean)
    .flatMap((value) => {
      const decoded = decodedFocusValue(value);
      return decoded === value ? [value] : [value, decoded];
    });
  const returnToPath = safeProjectReturnPath(params.id, searchParams?.return_to);
  const focusSeatIds = focusSeatParams.length
    ? seats
        .filter((seat) =>
          focusSeatParams.some((focus) =>
            identitySet(seat.id, seat.rowId, seat.configId, seat.threadId, seat.name).has(focus),
          ),
        )
        .map((seat) => seat.id)
    : [];
  const projectGithubUrl = text(project.github_url, "");
  const projectLocalPath = text(project.local_git_url, "");
  const repoLocalState = localGitState(projectLocalPath);

  return (
    <WorkbenchClient
      projectId={String(project.id ?? params.id)}
      projectName={text(project.name, `项目 ${params.id.slice(0, 8)}`)}
      projectDescription={text(project.description, "")}
      projectGithubUrl={projectGithubUrl}
      projectLocalPath={projectLocalPath}
      apiBaseUrl={(process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8011").trim().replace(/\/$/, "")}
      seats={seats}
      resourceIndex={{
        computers: [...configNodes, ...liveNodes].filter((node, index, list) => {
          const id = text(node.id ?? node.node_id, "");
          return id && list.findIndex((candidate) => text(candidate.id ?? candidate.node_id, "") === id) === index;
        }).length,
        onlineComputers: [...configNodes, ...liveNodes].filter((node, index, list) => {
          const id = text(node.id ?? node.node_id, "");
          const unique = id && list.findIndex((candidate) => text(candidate.id ?? candidate.node_id, "") === id) === index;
          return unique && /online|ready|active/i.test(text(node.runner_effective_status ?? node.runner_status ?? node.status, ""));
        }).length,
        logicalWorkstations: projectWorkstations.length,
        workshopStations: workshopStations.length,
        skills: skillLibrary.length,
        projectSkills: skillLibrary.filter((skill) => text(skill.source, "") !== "platform-baseline" && text(skill.scope, "") !== "baseline").length,
        repoReady: Boolean(projectGithubUrl || projectLocalPath),
        repoLocalChecked: repoLocalState.checked,
        repoLocalExists: repoLocalState.exists,
        repoLocalIsGit: repoLocalState.isGit,
        repoLocalMessage: repoLocalState.message,
      }}
      messages={asArray<AnyRecord>(collaborationMessagesState.data).map((message, index) => ({
        id: text(message.id, `message-${index + 1}`),
        title: text(message.title, ""),
        body: text(message.body, ""),
        status: text(message.status, ""),
        message_type: text(message.message_type ?? message.messageType, ""),
        created_at: text(message.created_at ?? message.createdAt, ""),
        sender_type: text(message.sender_type ?? message.senderType, ""),
        sender_id: text(message.sender_id ?? message.senderId, ""),
        recipient_type: text(message.recipient_type ?? message.recipientType, ""),
        recipient_id: text(message.recipient_id ?? message.recipientId, ""),
        dispatch_id: text(message.dispatch_id ?? message.dispatchId, ""),
        metadata: record(message.metadata),
        extra_data: record(message.extra_data ?? message.extraData),
      }))}
      bossPlans={asArray<AnyRecord>(bossPlansState.data).map((plan, index) => ({
        id: text(plan.id, `boss-plan-${index + 1}`),
        title: text(plan.title, ""),
        goal: text(plan.goal, ""),
        status: text(plan.status, ""),
        bossSeatId: text(plan.boss_seat_id ?? plan.bossSeatId, ""),
        contractPath: text(plan.contract_path ?? plan.contractPath, ""),
        createdAt: text(plan.created_at ?? plan.createdAt, ""),
        updatedAt: text(plan.updated_at ?? plan.updatedAt, ""),
        items: asArray<AnyRecord>(plan.items).map((item, itemIndex) => ({
          id: text(item.id, `boss-plan-item-${itemIndex + 1}`),
          role: text(item.role, ""),
          targetSeatId: text(item.target_seat_id ?? item.targetSeatId, ""),
          targetName: text(item.target_name ?? item.targetName, ""),
          title: text(item.title, ""),
          status: text(item.status, ""),
          dispatchMessageId: text(item.dispatch_message_id ?? item.dispatchMessageId, ""),
          receiptMessageId: text(item.receipt_message_id ?? item.receiptMessageId, ""),
          skills: asArray<string>(item.skills).map((skill) => text(skill, "")).filter(Boolean),
          knowledgePaths: asArray<string>(item.knowledge_paths ?? item.knowledgePaths).map((path) => text(path, "")).filter(Boolean),
          acceptance: text(item.acceptance, ""),
        })),
      }))}
      members={projectMembers.map((member, index) => ({
        id: text(member.user_id ?? member.user?.id ?? member.id, `member-${index + 1}`),
        name: text(member.name ?? member.user?.name ?? member.email ?? member.user?.email, `协作者 ${index + 1}`),
        email: text(member.email ?? member.user?.email, ""),
        role: text(member.role, member.is_owner ? "owner" : "member"),
        status: text(member.status, "active"),
        isOwner: Boolean(member.is_owner ?? member.isOwner),
      }))}
      currentUserId={currentUserId}
      currentUserName={currentUserName}
      initialOpenSeatIds={focusSeatIds}
      initialLaunchPackSeatIds={focusSeatIds}
      surfaceNotice={text(searchParams?.team_notice, "")}
      surfaceError={text(searchParams?.team_error, "")}
      returnTo={returnToPath}
      returnToLabel={returnToPath ? labelProjectReturnPath(returnToPath) : ""}
      embedded={searchParams?.embed === "drawer"}
    />
  );
}
