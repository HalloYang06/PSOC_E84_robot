import { redirect } from "next/navigation";
import Link from "next/link";
import {
  getCurrentAuthState,
  getCollaborationMessagesState,
  getProjectComputerNodesState,
  getProjectMembersState,
  getProjectState,
  getProjectWorkstationsState,
} from "../../../../lib/server-data";
import { isNpcSeatRecord, platformProviderIdFromSeat } from "../../../../lib/platform-provider";
import { WorkbenchClient } from "../workbench/workbench-client";

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
  if (raw.includes("claude")) return "Claude Code";
  if (raw.includes("codex")) return "Codex";
  return providerId || "thread";
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
  if (value.includes("/skill-forge")) return "← 返回 Skill 工坊";
  if (value.includes("/workbench")) return "← 返回工作台";
  if (value.includes("/company")) return "← 返回公司层";
  return "← 返回来源";
}

export default async function CompanyPage({ params, searchParams }: { params: { id: string }; searchParams?: { embed?: string; return_to?: string; from?: string } }) {
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    const query = new URLSearchParams();
    if (searchParams?.return_to) query.set("return_to", searchParams.return_to);
    if (searchParams?.from) query.set("from", searchParams.from);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${params.id}/company${suffix}`)}`);
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

  const [computerNodesState, projectWorkstationsState, projectMembersState, collaborationMessagesState] = await Promise.all([
    getProjectComputerNodesState(params.id),
    getProjectWorkstationsState(params.id),
    getProjectMembersState(params.id),
    getCollaborationMessagesState({ projectId: params.id }),
  ]);
  const liveNodes = asArray<AnyRecord>(computerNodesState.data);
  const projectWorkstations = asArray<AnyRecord>(projectWorkstationsState.data);
  const projectMembers = asArray<AnyRecord>(projectMembersState.data);

  const config = (project.collaboration_config ?? {}) as AnyRecord;
  const rawWorkstations = asArray<AnyRecord>(
    config.thread_workstations ?? config.threadWorkstations ?? config.workstations,
  );
  const seatRecords = rawWorkstations.filter((item) => isNpcSeatRecord(item));
  const configNodes = asArray<AnyRecord>(config.computer_nodes ?? config.nodes);
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
  for (const ws of projectWorkstations) {
    const wsId = text(ws?.id, "");
    if (!wsId) continue;
    workstationNameById.set(wsId, text(ws?.name, wsId));
    const lead = text(ws?.lead_seat_id ?? ws?.leadSeatId, "");
    if (lead) leadByWorkstation.set(wsId, lead);
  }

  const leadByNode = new Map<string, string>();
  const inheritedSkillsByNode = new Map<string, string[]>();
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
      const kp = text(p.knowledge_path ?? p.knowledgePath, "");
      if (kp) knowledgePathByNode.set(String(nodeId), kp);
    }
  }

  const allSeats = seatRecords.map((seat, index) => {
    const id = text(seat.id ?? seat.config_id ?? seat.row_id, `seat-${index}`);
    const name = text(seat.name ?? seat.title, `NPC ${index + 1}`);
    const workstationId = text(seat.workstation_id ?? seat.workstationId, "");
    const computerNodeId = text(seat.computer_node_id ?? seat.computerNodeId, "");
    const providerId = platformProviderIdFromSeat(seat) || text(seat.provider_id ?? seat.providerId, "");
    const providerLabel = text(seat.provider_label ?? seat.providerLabel ?? providerId, providerId);
    const responsibility = text(seat.responsibility ?? seat.body, "待分配职责");
    const skillLoadout = asArray<string>(seat.skill_loadout ?? seat.skillLoadout).map((s) => String(s)).filter(Boolean);
    const inheritedSkills = computerNodeId ? (inheritedSkillsByNode.get(computerNodeId) ?? []) : [];
    const workstationKnowledgePath = computerNodeId
      ? (knowledgePathByNode.get(computerNodeId) ?? `docs/workstations/${computerNodeId}.md`)
      : "";
    const knowledgeSummary = text(seat.knowledge_summary ?? seat.knowledgeSummary, "");
    const model = text(seat.model, "");
    const permissionLevel = text(seat.permission_level ?? seat.permissionLevel, "");
    const meta = record(seat.metadata);
    const extra = record(seat.extra_data ?? seat.extraData);
    const automationEnabled = Boolean(
      seat.automation_enabled
      ?? seat.automationEnabled
      ?? meta.automation_enabled
      ?? meta.automationEnabled
      ?? extra.automation_enabled
      ?? extra.automationEnabled
      ?? false,
    );
    const adapter = record(meta.adapter ?? extra.adapter);
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
    const threadKind = firstText(seat.thread_kind, seat.threadKind, meta.thread_kind, meta.threadKind, adapter.kind, deriveThreadKind(providerId, threadId));
    const threadHealth = firstText(
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
    const gitUserName = text(meta.git_user_name ?? meta.gitUserName, name);
    const gitUserEmail = text(
      meta.git_user_email ?? meta.gitUserEmail,
      `bot+${id}@noreply.invalid`,
    );
    const reviewPolicy = text(meta.review_policy ?? meta.reviewPolicy, "inherit");
    const leadSeatId = workstationId
      ? (leadByWorkstation.get(workstationId) ?? "")
      : (computerNodeId ? (leadByNode.get(computerNodeId) ?? "") : "");
    const isLead = !!leadSeatId && leadSeatId === id;
    return {
      id,
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

  const leadSeats = allSeats.filter((s) => s.isLead);

  const me = auth.data?.user as AnyRecord | null;
  const currentUserId = text(me?.id, "");
  const currentUserName = text(me?.name ?? me?.email ?? me?.id, currentUserId || "我");
  const returnToPath = safeProjectReturnPath(params.id, searchParams?.return_to);

  return (
    <WorkbenchClient
      projectId={String(project.id ?? params.id)}
      projectName={text(project.name, `项目 ${params.id.slice(0, 8)}`)}
      projectDescription={text(project.description, "")}
      projectGithubUrl={text(project.github_url, "")}
      projectLocalPath={text(project.local_git_url, "")}
      apiBaseUrl={(process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8010").trim().replace(/\/$/, "")}
      seats={leadSeats}
      messages={asArray<AnyRecord>(collaborationMessagesState.data).map((message, index) => ({
        id: text(message.id, `message-${index + 1}`),
        title: text(message.title, ""),
        body: text(message.body, ""),
        status: text(message.status, ""),
        message_type: text(message.message_type ?? message.messageType, ""),
        created_at: text(message.created_at ?? message.createdAt, ""),
        sender_type: text(message.sender_type ?? message.senderType, ""),
        sender_id: text(message.sender_id ?? message.senderId, ""),
        recipient_id: text(message.recipient_id ?? message.recipientId, ""),
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
      pageMode="company"
      returnTo={returnToPath}
      returnToLabel={returnToPath ? labelProjectReturnPath(returnToPath) : ""}
      embedded={searchParams?.embed === "drawer"}
    />
  );
}
