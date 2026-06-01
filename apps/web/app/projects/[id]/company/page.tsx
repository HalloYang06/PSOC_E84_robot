import { redirect } from "next/navigation";
import Link from "next/link";
import {
  getCurrentAuthState,
  getCollaborationMessagesState,
  getProjectComputerNodesState,
  getProjectState,
  getProjectWorkstationsState,
  getRequirementsState,
  getTasksDataScopedState,
  getUsageData,
} from "../../../../lib/server-data";
import { isNpcSeatRecord, platformProviderIdFromSeat } from "../../../../lib/platform-provider";
import { runnerStateLabel, summarizeRunnerDispatchState } from "../../../../lib/runner-status";
import styles from "./company.module.css";

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

function numberValue(value: unknown) {
  const next = Number(value ?? 0);
  return Number.isFinite(next) ? next : 0;
}

function formatTokenCount(value: number) {
  return new Intl.NumberFormat("zh-CN").format(Math.max(0, Math.round(value)));
}

function sameLocalDay(value: unknown, now = new Date()) {
  const date = value ? new Date(String(value)) : null;
  if (!date || Number.isNaN(date.getTime())) return false;
  return date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate();
}

function deriveThreadKind(providerId: string, threadId: string) {
  const raw = `${providerId} ${threadId}`.toLowerCase();
  if (raw.includes("claude")) return "Claude Code";
  if (raw.includes("codex")) return "Codex";
  return providerId || "thread";
}

function publicThreadState(value: unknown, automationEnabled = false) {
  const raw = text(value, "").toLowerCase();
  if (/online|ready|ok|watcher ready|connected|active/.test(raw)) return "线程已绑定";
  if (/stale|timeout|delay/.test(raw)) return "可能延迟";
  if (/offline|lost|failed|error/.test(raw)) return "需重连";
  return automationEnabled ? "已绑定，待电脑可投递" : "待接入";
}

function publicComputerDispatchState(node: AnyRecord | undefined) {
  return runnerStateLabel(node);
}

function looksInternalIdentifier(value: string) {
  const raw = text(value, "");
  return /^platform-npc-\d+$/i.test(raw)
    || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)
    || /^agent-[0-9a-f-]+$/i.test(raw);
}

function summarizeStructuredEvent(value: unknown, eventType: string) {
  const raw = text(value, "");
  if (!raw) return "";
  if (/^\s*[{[]/.test(raw) || /"kind"\s*:/.test(raw) || /"expected_reply"\s*:/.test(raw)) {
    if (/serial\.usb\.scan|serial_ports|usb_devices/i.test(raw)) {
      return "执行电脑正在扫描串口和 USB 设备；扫描结果会进入设备数据工作台的真实设备下拉。";
    }
    if (/codex\.desktop\.dispatch|desktop_delivery/i.test(raw)) {
      return "平台已登记桌面后台接收请求；等待目标桌面线程确认可见后同步结果。";
    }
    if (/runner_result|agent_result|final/i.test(raw)) {
      return "执行结果已回到平台记录；可从对应工作台查看证据。";
    }
    return `${eventType}已进入项目记录；详细证据在对应工作台查看。`;
  }
  if (/scanned real device interfaces and synced them back to the platform/i.test(raw)) {
    const node = raw.match(/(?:Runner|执行电脑|Execution computer)\s+([A-Za-z0-9._-]+)/i)?.[1];
    return node
      ? `执行电脑 ${node} 已完成真实设备扫描，并把结果同步到设备数据工作台。`
      : "执行电脑已完成真实设备扫描，并把结果同步到设备数据工作台。";
  }
  return "";
}

function userFacingEventText(value: unknown, fallback = "") {
  const structured = summarizeStructuredEvent(value, "组织事件");
  if (structured) return structured;
  const next = text(value, "")
    .replace(
      /\bRunner\s+([A-Za-z0-9._-]+)\s+received this dispatch on the execution computer, but Codex Desktop has not confirmed that the bound thread visibly received it\.[^\n]*/gi,
      "执行电脑 $1 已收到派单，但桌面后台还没有确认接收；请保持桌面版在线后重新同步。",
    )
    .replace(/平台等待桌面收口/gi, "平台继续等待桌面结果")
    .replace(/待收口/gi, "等结果")
    .replace(/自动重试桌面同步/gi, "自动重试桌面提醒")
    .replace(/已处于 in_progress 超过/gi, "已持续处理中超过")
    .replace(/已处于 acked 超过/gi, "已停留在已接单状态超过")
    .replace(/仍未拿到 final/gi, "仍未收到最终结果")
    .replace(/等待桌面 final 回执/gi, "等待桌面最终结果")
    .replace(/回写最小回执/gi, "同步已收到提醒")
    .replace(/最小回执/gi, "已收到提醒")
    .replace(/Runner 收件箱/gi, "执行记录")
    .replace(/抢占式引导/gi, "桌面提醒")
    .replace(/\bRunner\s+已收到云端派单，正在回写最小回执。/gi, "执行电脑已收到云端派单，正在等待桌面确认。")
    .replace(/\bRunner\s+已完成云端派单闭环验收：/gi, "执行电脑已完成派单验收：")
    .replace(/\bRunner\s+([A-Za-z0-9._-]+)\s+Runner\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/\bRunner\s+([A-Za-z0-9._-]+)\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/执行电脑\s+([A-Za-z0-9._-]+)\s+执行电脑\s+received this dispatch on the execution computer,?\s*but\s+桌面线程\s+has not confirmed that the\s+绑定线程\s+visibly received it\.?/gi, "执行电脑 $1 已收到派单，正在等待桌面线程确认可见。")
    .replace(/received this dispatch on the execution computer,?\s*but\s+桌面线程\s+has not confirmed that the\s+绑定线程\s+visibly received it\.?/gi, "已收到派单，正在等待桌面线程确认可见。")
    .replace(/received platform dispatch:?/gi, "已收到平台派单：")
    .replace(/\bRunner\s+([A-Za-z0-9._-]+)\s+runner\s+scanned real device interfaces and synced them back to the platform\.?/gi, "执行电脑 $1 已完成真实设备扫描，并把结果同步到设备数据工作台。")
    .replace(/执行电脑\s+([A-Za-z0-9._-]+)\s+执行电脑\s+scanned real device interfaces and synced them back to the platform\.?/gi, "执行电脑 $1 已完成真实设备扫描，并把结果同步到设备数据工作台。")
    .replace(/\bExecution computer\s+([A-Za-z0-9._-]+)\s+scanned real device interfaces and synced them back to the platform\.?/gi, "执行电脑 $1 已完成真实设备扫描，并把结果同步到设备数据工作台。")
    .replace(/The computer connection is reachable;?\s*/gi, "电脑连接可用；")
    .replace(/Codex Desktop UI 投递/gi, "桌面后台可接收")
    .replace(/Codex Desktop UI delivery failed:?/gi, "桌面线程暂未确认收到：")
    .replace(/已把这条派单送进绑定桌面线程；完整处理过程在桌面版继续。平台正在等待桌面线程写出最终回复。/gi, "执行电脑已登记桌面后台接收请求；待桌面线程确认可见后继续同步最终结果。")
    .replace(/Codex Desktop/gi, "桌面线程")
    .replace(/bound thread/gi, "绑定线程")
    .replace(/alias_display_non_authoritative/gi, "历史标识展示规则")
    .replace(/historical[_\s-]*alias(?:[_\s-]*non[_\s-]*authoritative)?/gi, "历史标识")
    .replace(/current\s+alias/gi, "当前标识")
    .replace(/source_thread/gi, "协作记录")
    .replace(/canonical_workstation_id/gi, "协作记录")
    .replace(/requested_workstation_id/gi, "协作记录")
    .replace(/authoritative_([a-z]+_)?seat_id/gi, "协作记录")
    .replace(/authoritative_target_seat_id/gi, "协作记录")
    .replace(/session JSONL/gi, "同步记录")
    .replace(/local path/gi, "当前电脑记录")
    .replace(/\badapter\b/gi, "同步")
    .replace(/\bbridge\b/gi, "同步")
    .replace(/\brunner\b/gi, "执行电脑")
    .replace(/\bcodex app-server\b/gi, "后台线程")
    .replace(/\bcodex desktop ui\b/gi, "桌面线程")
    .replace(/执行电脑\s+([A-Za-z0-9._-]+)\s+执行电脑\s+received this dispatch on the execution computer,?\s*but\s+桌面线程\s+has not confirmed that the\s+绑定线程\s+visibly received it\.?\s*Keep this item pending and retry desktop sync\.?/gi, "执行电脑 $1 已收到派单，正在等待桌面线程确认可见。")
    .replace(/received this dispatch on the execution computer,?\s*but\s+桌面线程\s+has not confirmed that the\s+绑定线程\s+visibly received it\.?\s*Keep this item pending and retry desktop sync\.?/gi, "已收到派单，正在等待桌面线程确认可见。")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "关联记录")
    .replace(/[A-Za-z]:[\\/][^\s"'`<>),\]]+/g, "当前电脑工作副本")
    .replace(/\.codex[\\/][^\s"'`<>),\]]+/gi, "线程记录")
    .replace(/\s{2,}/g, " ")
    .trim();
  if (!next || looksInternalIdentifier(next)) return fallback;
  if (/^(关联记录|协作记录|同步记录)$/.test(next)) return fallback;
  return next;
}

function publicStatusLabel(value: unknown) {
  const raw = text(value, "").toLowerCase();
  if (/completed|done|success|resolved/.test(raw)) return "已完成";
  if (/acked|accepted/.test(raw)) return "已接单";
  if (/delivered/.test(raw)) return "已送达";
  if (/queued/.test(raw)) return "已排队";
  if (/waiting_closeout|closeout/.test(raw)) return "等结果";
  if (/running|progress|active|pending/.test(raw)) return "处理中";
  if (/failed|error|blocked|rejected/.test(raw)) return "异常待处理";
  return text(value, "已记录");
}

function publicNeedStatusLabel(value: unknown) {
  const raw = text(value, "").toLowerCase();
  if (/satisfied|completed|done|closed|resolved/.test(raw)) return "已满足";
  if (/routed|queued|ready/.test(raw)) return "已路由";
  if (/in_progress|running|active|processing/.test(raw)) return "处理中";
  if (/review|approval|pending_human/.test(raw)) return "待确认";
  if (/blocked|failed|rejected/.test(raw)) return "受阻";
  if (/draft/.test(raw)) return "草稿";
  return "等待协作";
}

function publicTaskStatusLabel(value: unknown) {
  const raw = text(value, "").toLowerCase();
  if (/done|completed|closed|resolved/.test(raw)) return "已完成";
  if (/running|active|in_progress|processing/.test(raw)) return "处理中";
  if (/reviewing|waiting_user|waiting_npc/.test(raw)) return "等确认";
  if (/queued|ready|acked|accepted/.test(raw)) return "已承接";
  if (/blocked|failed|rejected/.test(raw)) return "受阻";
  if (/cancelled|archived/.test(raw)) return "已收起";
  return "待承接";
}

function publicReceiptLabel(messages: AnyRecord[]) {
  if (messages.some((message) => /completed|done|delivered|final|resolved/i.test(text(message.status, "") + " " + text(message.message_type ?? message.messageType, "")))) {
    return "已有最终回执";
  }
  if (messages.some((message) => /ack|progress|running|queued|delivered|waiting/i.test(text(message.status, "") + " " + text(message.message_type ?? message.messageType, "")))) {
    return "已有过程回执";
  }
  return "等待回执";
}

function latestActivityTime(...values: unknown[]) {
  let latest = 0;
  for (const value of values) {
    const raw = text(value, "");
    if (!raw) continue;
    const time = new Date(raw).getTime();
    if (Number.isFinite(time)) latest = Math.max(latest, time);
  }
  return latest;
}

function shortPublicText(value: unknown, fallback: string, maxLength = 92) {
  const next = userFacingEventText(value, fallback).replace(/\s+/g, " ").trim();
  if (next.length <= maxLength) return next;
  return `${next.slice(0, maxLength - 1)}…`;
}

function reviewPolicyLabel(value: unknown) {
  const raw = text(value, "inherit").toLowerCase();
  if (/strict|always|manual|required/.test(raw)) return "高风险确认";
  if (/trusted|auto|bypass|allow/.test(raw)) return "直接派发边界";
  return "继承工位规则";
}

function orgEventTypeLabel(value: unknown) {
  const raw = text(value, "").toLowerCase();
  if (/agent_result|runner_result|final|reply|receipt|closeout|minimal/.test(raw)) return "回执";
  if (/agent_command|runner_command|dispatch|delivery/.test(raw)) return "派单事件";
  if (/review|approval|human_review/.test(raw)) return "确认事件";
  if (/requirement|need/.test(raw)) return "协作需求";
  if (/progress|ack|running|queued|waiting|retry|desktop/.test(raw)) return "进度";
  if (/blocked|failed|error|exception/.test(raw)) return "异常";
  return "组织事件";
}

function messageMeta(value: AnyRecord) {
  return {
    ...record(value.extra_data ?? value.extraData),
    ...record(value.metadata),
  };
}

function isPendingHumanReview(value: AnyRecord) {
  const type = text(value.message_type ?? value.messageType, "").toLowerCase();
  const status = text(value.status, "").toLowerCase();
  return type === "human_review_request" && ["pending_human_review", "pending", "open"].includes(status);
}

function reviewSourceLabel(value: AnyRecord) {
  const meta = messageMeta(value);
  if (text(meta.schema, "") === "skill_forge_review_v1") return "能力工坊待确认";
  return "待人工确认";
}

function publicEventTitle(event: AnyRecord) {
  const eventType = orgEventTypeLabel(event.message_type ?? event.body);
  if (isPendingHumanReview(event)) {
    return userFacingEventText(event.title, "协作请求待人工确认");
  }
  return userFacingEventText(event.title, `${eventType}已进入项目记录`);
}

function publicEventDescription(event: AnyRecord) {
  if (isPendingHumanReview(event)) return "需要项目负责人或人工确认后再继续。";
  const eventType = orgEventTypeLabel(event.message_type ?? event.body);
  const structured = summarizeStructuredEvent(event.body, eventType);
  if (structured) return structured;
  return userFacingEventText(event.body, `${eventType} · 组织事件已进入项目记录。`);
}

function knowledgeLabel(seat: { knowledgeSummary: string; workstationKnowledgePath: string }) {
  if (seat.knowledgeSummary) return seat.knowledgeSummary;
  if (seat.workstationKnowledgePath) return "工位知识库已配置";
  return "待绑定知识库";
}

function safeProjectReturnPath(projectId: string, value: unknown) {
  const raw = text(value, "");
  if (!raw.startsWith(`/projects/${projectId}/`)) return "";
  if (/^\/\//.test(raw) || raw.includes("\\") || raw.includes("://")) return "";
  return raw;
}

function labelProjectReturnPath(value: string) {
  if (value.includes("/2d-upgrade")) return "← 返回主页面";
  if (value.includes("/datasets")) return "← 返回设备数据工作台";
  if (value.includes("/ai-lab")) return "← 返回设备数据工作台";
  if (value.includes("/robotics")) return "← 返回设备数据工作台";
  if (value.includes("/observability")) return "← 返回公司层";
  if (value.includes("/skill-forge")) return "← 返回能力工坊";
  if (value.includes("/workbench")) return "← 返回 NPC 工作台";
  if (value.includes("/company")) return "← 返回公司层";
  return "← 返回来源";
}

function statusTone(label: string) {
  if (/可投递|在线|已完成|已送达/.test(label)) return "healthy";
  if (/延迟|待审核|待人工确认|高风险确认|待处理|等待|未知/.test(label)) return "review";
  if (/离线|需重连|阻塞|失败/.test(label)) return "blocked";
  return "idle";
}

function chainTone(label: string) {
  if (/已满足|已完成|最终回执/.test(label)) return "healthy";
  if (/受阻|失败|异常|打回/.test(label)) return "blocked";
  if (/待确认|等待|草稿|过程/.test(label)) return "review";
  return "idle";
}

function summarizeSeatDispatchState(input: {
  providerId: string;
  computerNodeId: string;
  threadId: string;
  nodeState: AnyRecord | undefined;
}) {
  if (!input.providerId) {
    return {
      state: "状态未知，先检查接入",
      canQueue: false,
      shortLabel: "待选择执行通道",
      detail: "先给这个 NPC 选择执行通道，再接入持续接单。",
    };
  }
  if (!input.computerNodeId) {
    return {
      state: "状态未知，先检查接入",
      canQueue: false,
      shortLabel: "待绑定电脑",
      detail: "先绑定目标电脑，平台才能把任务落到固定设备。",
    };
  }
  if (!input.threadId) {
    return {
      state: "状态未知，先检查接入",
      canQueue: false,
      shortLabel: "待绑定线程",
      detail: "先扫描并绑定桌面线程，避免任务落空或串到别的终端。",
    };
  }
  return summarizeRunnerDispatchState(input.nodeState);
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

  const [
    computerNodesState,
    projectWorkstationsState,
    collaborationMessagesState,
    requirementsState,
    tasksState,
    usageData,
  ] = await Promise.all([
    getProjectComputerNodesState(params.id),
    getProjectWorkstationsState(params.id),
    getCollaborationMessagesState({ projectId: params.id }),
    getRequirementsState({ projectIds: [params.id] }),
    getTasksDataScopedState({ projectIds: [params.id] }),
    getUsageData(),
  ]);
  const liveNodes = asArray<AnyRecord>(computerNodesState.data);
  const projectWorkstations = asArray<AnyRecord>(projectWorkstationsState.data);

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
  const nodeStateMap = new Map<string, AnyRecord>();
  for (const node of [...configNodes, ...liveNodes]) {
    const id = text(node?.id ?? node?.node_id, "");
    if (!id) continue;
    const name = text(node?.name ?? node?.label ?? node?.hostname ?? id, id);
    nodeMap.set(id, name);
    nodeStateMap.set(id, node);
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
    const nodeState = computerNodeId ? nodeStateMap.get(computerNodeId) : undefined;
    const seatDispatch = summarizeSeatDispatchState({
      providerId,
      computerNodeId,
      threadId,
      nodeState,
    });
    const dispatchState = seatDispatch.state;
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
      threadHealth: publicThreadState(threadHealth, automationEnabled),
      dispatchState,
      dispatchCanQueue: seatDispatch.canQueue,
      dispatchShortLabel: seatDispatch.shortLabel,
      dispatchDetail: seatDispatch.detail,
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

  const seatsByWorkstation = new Map<string, typeof allSeats>();
  for (const seat of allSeats) {
    const key = seat.workstationId || "unassigned";
    seatsByWorkstation.set(key, [...(seatsByWorkstation.get(key) ?? []), seat]);
  }
  const workstationRows = [
    ...projectWorkstations.map((ws, index) => {
      const id = text(ws.id, `workstation-${index + 1}`);
      const seats = seatsByWorkstation.get(id) ?? [];
      const leadId = text(ws.lead_seat_id ?? ws.leadSeatId, "");
      const lead = allSeats.find((seat) => seat.id === leadId);
      return {
        id,
        name: text(ws.name, `工位 ${index + 1}`),
        description: text(ws.description ?? ws.summary, "负责一类长期工作，不绑定具体电脑。"),
        seats,
        leadName: lead?.name ?? "待指定",
      };
    }),
    ...(seatsByWorkstation.get("unassigned")?.length
      ? [{
          id: "unassigned",
          name: "未归属员工",
          description: "这些 NPC 还需要分配到逻辑工位，之后才能稳定继承职责、知识库和确认规则。",
          seats: seatsByWorkstation.get("unassigned") ?? [],
          leadName: "待指定",
        }]
      : []),
  ];
  const threadReadyCount = allSeats.filter((seat) => seat.dispatchState === "可投递").length;
  const queueOnlySeatCount = allSeats.filter(
    (seat) =>
      seat.threadId
      && seat.dispatchCanQueue
      && ["最近在线，可能延迟", "他人操作中"].includes(seat.dispatchState),
  ).length;
  const recoveryDispatchCount = allSeats.filter(
    (seat) => seat.dispatchState === "等待电脑恢复" || seat.dispatchState === "离线，需重连",
  ).length;
  const offlineDispatchCount = allSeats.filter((seat) => seat.dispatchState === "离线，需重连").length;
  const staleDispatchCount = allSeats.filter((seat) => seat.dispatchState === "等待电脑恢复").length;
  const occupiedDispatchCount = allSeats.filter((seat) => seat.dispatchState === "他人操作中").length;
  const missingProviderCount = allSeats.filter((seat) => seat.dispatchShortLabel === "待选择执行通道").length;
  const missingThreadCount = allSeats.filter((seat) => seat.dispatchShortLabel === "待绑定线程").length;
  const missingComputerCount = allSeats.filter((seat) => seat.dispatchShortLabel === "待绑定电脑").length;
  const unknownDispatchCount = allSeats.filter(
    (seat) =>
      seat.dispatchState === "状态未知，先检查接入"
      && !["待选择执行通道", "待绑定线程", "待绑定电脑"].includes(seat.dispatchShortLabel),
  ).length;
  const strictReviewCount = allSeats.filter((seat) => reviewPolicyLabel(seat.reviewPolicy) === "高风险确认").length;
  const skillAssignedCount = allSeats.filter((seat) => seat.skillLoadout.length || seat.inheritedSkills.length).length;
  const knowledgeAssignedCount = allSeats.filter((seat) => seat.knowledgeSummary || seat.workstationKnowledgePath).length;
  const nodeDispatchCounts = [...nodeStateMap.values()].reduce(
    (summary, node) => {
      const dispatch = summarizeRunnerDispatchState(node);
      if (dispatch.canDispatch) {
        summary.ready += 1;
      } else if (dispatch.tone === "stale" || dispatch.tone === "offline") {
        summary.reconnect += 1;
      } else if (dispatch.canQueue) {
        summary.queueable += 1;
      } else {
        summary.unknown += 1;
      }
      return summary;
    },
    { ready: 0, queueable: 0, reconnect: 0, unknown: 0 },
  );
  const readyNodeCount = nodeDispatchCounts.ready;

  const returnToPath = safeProjectReturnPath(params.id, searchParams?.return_to);

  const projectId = String(project.id ?? params.id);
  const allOrgEvents = asArray<AnyRecord>(collaborationMessagesState.data);
  const allNeeds = asArray<AnyRecord>(requirementsState.data);
  const allTasks = asArray<AnyRecord>(tasksState.data);
  const pendingHumanReviews = allOrgEvents.filter(isPendingHumanReview);
  const recentOrgEvents = allOrgEvents.slice(0, 6);
  const seatNameById = new Map<string, string>();
  for (const seat of allSeats) {
    seatNameById.set(seat.id, seat.name);
    if (seat.threadId) seatNameById.set(seat.threadId, seat.name);
    if (seat.computerNodeId) seatNameById.set(seat.computerNodeId, seat.name);
  }
  const messagesByRequirement = new Map<string, AnyRecord[]>();
  const messagesByTask = new Map<string, AnyRecord[]>();
  const messagesByDispatch = new Map<string, AnyRecord[]>();
  for (const message of allOrgEvents) {
    const meta = messageMeta(message);
    const requirementId = text(
      message.requirement_id
        ?? message.requirementId
        ?? meta.requirement_id
        ?? meta.requirementId,
      "",
    );
    const taskId = text(message.task_id ?? message.taskId ?? meta.task_id ?? meta.taskId, "");
    const dispatchId = text(message.dispatch_id ?? message.dispatchId ?? meta.dispatch_id ?? meta.dispatchId, "");
    if (requirementId) messagesByRequirement.set(requirementId, [...(messagesByRequirement.get(requirementId) ?? []), message]);
    if (taskId) messagesByTask.set(taskId, [...(messagesByTask.get(taskId) ?? []), message]);
    if (dispatchId) messagesByDispatch.set(dispatchId, [...(messagesByDispatch.get(dispatchId) ?? []), message]);
  }
  const tasksByNeed = new Map<string, AnyRecord[]>();
  for (const task of allTasks) {
    const sourceNeedId = text(
      task.source_need_id
        ?? task.sourceNeedId
        ?? task.requirement_id
        ?? task.requirementId,
      "",
    );
    if (sourceNeedId) tasksByNeed.set(sourceNeedId, [...(tasksByNeed.get(sourceNeedId) ?? []), task]);
  }
  const collaborationChains = allNeeds.map((need, index) => {
    const needId = text(need.id ?? need.requirement_id ?? need.requirementId, `need-${index}`);
    const linkedTasks = [
      ...asArray<AnyRecord>(tasksByNeed.get(needId)),
      ...allTasks.filter((task) => text(task.id ?? task.task_id, "") === text(need.task_id ?? need.taskId, "")),
    ].filter((task, taskIndex, array) => {
      const taskId = text(task.id ?? task.task_id, `task-${taskIndex}`);
      return array.findIndex((candidate) => text(candidate.id ?? candidate.task_id, "") === taskId) === taskIndex;
    });
    const primaryTask = linkedTasks[0] ?? null;
    const dispatch = primaryTask ? record(primaryTask.latest_dispatch ?? primaryTask.latestDispatch) : {};
    const dispatchId = text(dispatch.id ?? dispatch.dispatch_id ?? dispatch.dispatchId, "");
    const taskId = primaryTask ? text(primaryTask.id ?? primaryTask.task_id, "") : "";
    const receiptMessages = [
      ...asArray<AnyRecord>(messagesByRequirement.get(needId)),
      ...(taskId ? asArray<AnyRecord>(messagesByTask.get(taskId)) : []),
      ...(dispatchId ? asArray<AnyRecord>(messagesByDispatch.get(dispatchId)) : []),
    ].filter((message, messageIndex, array) => array.findIndex((candidate) => text(candidate.id, "") === text(message.id, "")) === messageIndex);
    const requesterId = text(need.from_agent ?? need.fromAgent ?? need.created_by_id ?? need.createdById, "");
    const targetId = text(
      need.target_seat_id
        ?? need.targetSeatId
        ?? need.to_agent
        ?? need.toAgent
        ?? primaryTask?.assignee_seat_id
        ?? primaryTask?.assigneeSeatId
        ?? primaryTask?.assignee_agent_id
        ?? primaryTask?.assigneeAgentId,
      "",
    );
    const requesterName = seatNameById.get(requesterId) ?? (requesterId ? "发起 NPC" : "项目成员");
    const targetName = seatNameById.get(targetId) ?? (targetId ? "承接 NPC" : "待推荐");
    const needStatus = publicNeedStatusLabel(need.status);
    const taskStatus = primaryTask ? publicTaskStatusLabel(primaryTask.status) : "待生成任务";
    const dispatchStatus = dispatchId ? publicStatusLabel(dispatch.status ?? primaryTask?.status) : "待投递";
    const receiptStatus = publicReceiptLabel(receiptMessages);
    return {
      id: needId,
      title: shortPublicText(need.title, `协作需求 ${index + 1}`, 54),
      summary: shortPublicText(
        need.context_summary ?? need.contextSummary ?? need.expected_output ?? need.expectedOutput,
        "这条需求会在路由后进入承接 NPC 的任务队列。",
        108,
      ),
      requesterName,
      targetName,
      requesterId,
      targetId,
      needStatus,
      taskStatus,
      dispatchStatus,
      receiptStatus,
      taskCount: linkedTasks.length,
      receiptCount: receiptMessages.length,
      activityTime: latestActivityTime(
        need.last_activity_at,
        need.lastActivityAt,
        need.updated_at,
        need.updatedAt,
        need.created_at,
        need.createdAt,
        primaryTask?.updated_at,
        primaryTask?.updatedAt,
        primaryTask?.created_at,
        primaryTask?.createdAt,
        ...receiptMessages.map((message) => message.created_at ?? message.createdAt),
      ),
    };
  }).sort((left, right) => right.activityTime - left.activityTime);
  const visibleChains = collaborationChains.slice(0, 4);
  const seatAliases = new Map<string, Set<string>>();
  for (const seat of allSeats) {
    seatAliases.set(
      seat.id,
      new Set(
        [
          seat.id,
          seat.threadId,
          seat.computerNodeId,
          seat.name,
          text(record(seat.metadata).config_id, ""),
          text(record(seat.metadata).seat_id, ""),
          text(record(seat.metadata).source_workstation_id, ""),
        ].filter(Boolean),
      ),
    );
  }
  const seatMatches = (seat: typeof allSeats[number], value: unknown) => {
    const raw = text(value, "");
    if (!raw) return false;
    return seatAliases.get(seat.id)?.has(raw) ?? false;
  };
  const canonicalSeatId = (value: unknown) => {
    const raw = text(value, "");
    if (!raw) return "";
    for (const seat of allSeats) {
      if (seatAliases.get(seat.id)?.has(raw)) return seat.id;
    }
    return "";
  };
  const officeColumnCount = Math.max(2, Math.ceil(Math.sqrt(Math.max(allSeats.length, 1) * 1.25)));
  const officeRowCount = Math.max(1, Math.ceil(Math.max(allSeats.length, 1) / officeColumnCount));
  const officeNodes = allSeats.map((seat, index) => {
    const column = index % officeColumnCount;
    const row = Math.floor(index / officeColumnCount);
    const x = 10 + ((column + 0.5) * 80) / officeColumnCount + (row % 2 ? 3 : -2);
    const y = 12 + ((row + 0.5) * 74) / officeRowCount + (column % 2 ? 4 : -3);
    const outgoingCount = allNeeds.filter((need) => seatMatches(seat, need.from_agent ?? need.fromAgent ?? need.created_by_id ?? need.createdById)).length;
    const incomingCount = allNeeds.filter((need) =>
      seatMatches(
        seat,
        need.target_seat_id
          ?? need.targetSeatId
          ?? need.to_agent
          ?? need.toAgent,
      ),
    ).length;
    const taskCount = allTasks.filter((task) =>
      seatMatches(
        seat,
        task.assignee_seat_id
          ?? task.assigneeSeatId
          ?? task.assignee_agent_id
          ?? task.assigneeAgentId
          ?? task.assignee,
      ),
    ).length;
    return {
      id: seat.id,
      seat,
      x: Math.max(8, Math.min(92, x)),
      y: Math.max(10, Math.min(88, y)),
      outgoingCount,
      incomingCount,
      taskCount,
      tone: statusTone(seat.dispatchState),
    };
  });
  const officeNodeById = new Map(officeNodes.map((node) => [node.id, node]));
  const officeEdgeMap = new Map<string, {
    id: string;
    fromId: string;
    toId: string;
    count: number;
    label: string;
    needStatus: string;
    taskStatus: string;
    receiptStatus: string;
    activityTime: number;
  }>();
  for (const chain of collaborationChains) {
    const fromId = canonicalSeatId(chain.requesterId);
    const toId = canonicalSeatId(chain.targetId);
    if (!fromId || !toId || fromId === toId) continue;
    const key = `${fromId}->${toId}`;
    const existing = officeEdgeMap.get(key);
    if (!existing) {
      officeEdgeMap.set(key, {
        id: key,
        fromId,
        toId,
        count: 1,
        label: chain.title,
        needStatus: chain.needStatus,
        taskStatus: chain.taskStatus,
        receiptStatus: chain.receiptStatus,
        activityTime: chain.activityTime,
      });
    } else {
      existing.count += 1;
      if (chain.activityTime > existing.activityTime) {
        existing.label = chain.title;
        existing.needStatus = chain.needStatus;
        existing.taskStatus = chain.taskStatus;
        existing.receiptStatus = chain.receiptStatus;
        existing.activityTime = chain.activityTime;
      }
    }
  }
  const explicitOfficeEdges = [...officeEdgeMap.values()]
    .filter((edge) => officeNodeById.has(edge.fromId) && officeNodeById.has(edge.toId))
    .sort((left, right) => right.activityTime - left.activityTime);
  const existingOfficeEdgeIds = new Set(explicitOfficeEdges.map((edge) => edge.id));
  const officeRelationshipEdges: typeof explicitOfficeEdges = [];
  const seatsByOfficeWorkstation = new Map<string, typeof allSeats>();
  for (const seat of allSeats) {
    const key = seat.workstationId || "unassigned";
    seatsByOfficeWorkstation.set(key, [...(seatsByOfficeWorkstation.get(key) ?? []), seat]);
  }
  for (const peers of seatsByOfficeWorkstation.values()) {
    for (let index = 0; index < peers.length - 1; index += 1) {
      const from = peers[index];
      const to = peers[index + 1];
      const id = `${from.id}->${to.id}`;
      if (existingOfficeEdgeIds.has(id)) continue;
      officeRelationshipEdges.push({
        id,
        fromId: from.id,
        toId: to.id,
        count: 1,
        label: "同工位",
        needStatus: "等待协作",
        taskStatus: "同工位",
        receiptStatus: "等待回执",
        activityTime: 0,
      });
    }
  }
  for (const seat of allSeats) {
    if (!seat.leadSeatId || seat.leadSeatId === seat.id) continue;
    const id = `${seat.leadSeatId}->${seat.id}`;
    if (existingOfficeEdgeIds.has(id)) continue;
    if (!officeNodeById.has(seat.leadSeatId) || !officeNodeById.has(seat.id)) continue;
    officeRelationshipEdges.push({
      id,
      fromId: seat.leadSeatId,
      toId: seat.id,
      count: 1,
      label: "负责人",
      needStatus: "等待协作",
      taskStatus: "负责人",
      receiptStatus: "等待回执",
      activityTime: 0,
    });
  }
  const officeEdges = [...explicitOfficeEdges, ...officeRelationshipEdges.slice(0, Math.max(0, 14 - explicitOfficeEdges.length))];
  const seatRelationCards = allSeats.map((seat) => {
    const sameDepartmentPeers = allSeats.filter(
      (peer) => peer.id !== seat.id && peer.workstationId && peer.workstationId === seat.workstationId,
    );
    const leadPeer = allSeats.find((peer) => peer.id !== seat.id && peer.id === seat.leadSeatId) ?? null;
    const outgoingNeeds = allNeeds.filter((need) => seatMatches(seat, need.from_agent ?? need.fromAgent ?? need.created_by_id ?? need.createdById));
    const incomingNeeds = allNeeds.filter((need) =>
      seatMatches(
        seat,
        need.target_seat_id
          ?? need.targetSeatId
          ?? need.to_agent
          ?? need.toAgent,
      ),
    );
    const assignedTasks = allTasks.filter((task) =>
      seatMatches(
        seat,
        task.assignee_seat_id
          ?? task.assigneeSeatId
          ?? task.assignee_agent_id
          ?? task.assigneeAgentId
          ?? task.assignee,
      ),
    );
    const relationNames = new Set<string>();
    if (leadPeer) relationNames.add(leadPeer.name);
    for (const peer of sameDepartmentPeers) relationNames.add(peer.name);
    for (const need of [...outgoingNeeds, ...incomingNeeds]) {
      const targetId = text(
        need.target_seat_id
          ?? need.targetSeatId
          ?? need.to_agent
          ?? need.toAgent
          ?? need.from_agent
          ?? need.fromAgent,
        "",
      );
      const name = seatNameById.get(targetId);
      if (name && name !== seat.name) relationNames.add(name);
    }
    const relatedNames = [...relationNames].slice(0, 5);
    const relationScore = relatedNames.length + outgoingNeeds.length + incomingNeeds.length + assignedTasks.length;
    const tone = seat.dispatchState === "可投递"
      ? "healthy"
      : /等待|未知|延迟|排队/.test(seat.dispatchState)
        ? "review"
        : /离线|重连|失败|阻塞/.test(seat.dispatchState)
          ? "blocked"
          : "idle";
    return {
      seat,
      relatedNames,
      outgoingCount: outgoingNeeds.length,
      incomingCount: incomingNeeds.length,
      taskCount: assignedTasks.length,
      relationScore,
      tone,
    };
  }).sort((left, right) => right.relationScore - left.relationScore || left.seat.name.localeCompare(right.seat.name, "zh-CN"));
  const openNeedCount = allNeeds.filter((need) => !/satisfied|completed|done|closed|resolved|archived|cancelled/i.test(text(need.status, ""))).length;
  const activeTaskCount = allTasks.filter((task) => /queued|ready|running|active|in_progress|reviewing|waiting/i.test(text(task.status, ""))).length;
  const waitingReceiptCount = collaborationChains.filter((chain) => chain.receiptStatus === "等待回执").length;
  const projectUsage = asArray<AnyRecord>(usageData).filter((item) => text(item.project_id ?? item.projectId, "") === projectId);
  const todayUsage = projectUsage.filter((item) => sameLocalDay(item.created_at ?? item.createdAt));
  const usageSource = todayUsage.length ? todayUsage : projectUsage;
  const tokenInputToday = usageSource.reduce((sum, item) => sum + numberValue(item.input_tokens ?? item.inputTokens), 0);
  const tokenOutputToday = usageSource.reduce((sum, item) => sum + numberValue(item.output_tokens ?? item.outputTokens), 0);
  const tokenCachedToday = usageSource.reduce((sum, item) => sum + numberValue(item.cached_tokens ?? item.cachedTokens), 0);
  const tokenTotalToday = tokenInputToday + tokenOutputToday;
  const tokenBudget = allSeats.reduce((sum, seat) => {
    const raw = record(seat.metadata).max_tokens_per_task ?? record(seat.metadata).maxTokensPerTask;
    return sum + numberValue(raw);
  }, 0) || 1000000;
  const runningEventCount = allOrgEvents.filter((event) => /running|progress|active|pending|queued|acked|delivered/i.test(text(event.status, ""))).length;
  const completedEventCount = allOrgEvents.filter((event) => /completed|done|success|resolved/i.test(text(event.status, ""))).length;
  const taskDetailItems = (pendingHumanReviews.length ? pendingHumanReviews : recentOrgEvents).slice(0, 5);
  const selfPath = `/projects/${projectId}/company`;
  const decisionItems = Array.from(new Set([
    pendingHumanReviews.length ? `${pendingHumanReviews.length} 条待人工确认` : "",
    queueOnlySeatCount ? `${queueOnlySeatCount} 名 NPC 当前只能先排队` : "",
    staleDispatchCount ? `${staleDispatchCount} 名 NPC 正等待执行电脑恢复` : "",
    offlineDispatchCount ? `${offlineDispatchCount} 名 NPC 需要重连执行电脑` : "",
    occupiedDispatchCount ? `${occupiedDispatchCount} 名 NPC 当前由他人占用，只能先排队` : "",
    missingProviderCount ? `${missingProviderCount} 名 NPC 还没选择执行通道` : "",
    missingThreadCount ? `${missingThreadCount} 名 NPC 还没绑定桌面线程` : "",
    missingComputerCount ? `${missingComputerCount} 名 NPC 还没绑定目标电脑` : "",
    unknownDispatchCount ? `${unknownDispatchCount} 名 NPC 的执行状态仍需检查接入` : "",
    nodeStateMap.size
      ? `真实电脑：可投递 ${nodeDispatchCounts.ready} · 仅排队 ${nodeDispatchCounts.queueable} · 需重连 ${nodeDispatchCounts.reconnect} · 待检查 ${nodeDispatchCounts.unknown}`
      : "",
    strictReviewCount ? `${strictReviewCount} 名 NPC 启用高风险确认` : "",
    openNeedCount ? `${openNeedCount} 条协作需求仍在流转` : "",
    activeTaskCount ? `${activeTaskCount} 条承接任务正在推进` : "",
    waitingReceiptCount ? `${waitingReceiptCount} 条协作链路等待回执` : "",
    skillAssignedCount < allSeats.length ? `${Math.max(allSeats.length - skillAssignedCount, 0)} 名 NPC 待补 Skill` : "",
    knowledgeAssignedCount < allSeats.length ? `${Math.max(allSeats.length - knowledgeAssignedCount, 0)} 名 NPC 待补知识库` : "",
    recentOrgEvents.length ? `${recentOrgEvents.length} 条最近回执需要抽查` : "",
  ].filter(Boolean))).slice(0, 5);

  return (
    <main className={styles.shell} data-embedded={searchParams?.embed === "drawer" ? "1" : undefined}>
      <nav className={styles.topNav} aria-label="公司层导航">
        <span className={styles.navCrumb}>项目公司 / 公司层</span>
        <Link href={`/projects/${projectId}`}>回到主页面</Link>
        <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=company`}>进入 NPC 工作台</Link>
        <Link href={`/projects/${projectId}/skill-forge?return_to=${encodeURIComponent(selfPath)}&from=company`}>管理能力工坊</Link>
        {returnToPath ? <Link href={returnToPath}>{labelProjectReturnPath(returnToPath)}</Link> : null}
      </nav>

      <header className={styles.header}>
        <div>
          <span>公司层 / 运行态势图</span>
          <h1>{text(project.name, "AI 合作平台")} 公司沙盘</h1>
          <p>先看阻塞、再看部门、最后进入对应工作台处理；这里不展开长表格，只保留组织运行的关键线索。</p>
        </div>
        <section className={styles.statusStrip} aria-label="组织状态">
          <article><span>工位</span><strong>{workstationRows.length}</strong><small>逻辑部门</small></article>
          <article><span>NPC</span><strong>{allSeats.length}</strong><small>员工席位</small></article>
          <article><span>可投递</span><strong>{threadReadyCount}/{allSeats.length || 0}</strong><small>电脑 {readyNodeCount}/{nodeStateMap.size || 0}</small></article>
          <article><span>仅排队</span><strong>{queueOnlySeatCount}</strong><small>电脑 {nodeDispatchCounts.queueable}</small></article>
          <article><span>需重连</span><strong>{recoveryDispatchCount}</strong><small>电脑 {nodeDispatchCounts.reconnect}</small></article>
          <article><span>待检查</span><strong>{unknownDispatchCount}</strong><small>电脑 {nodeDispatchCounts.unknown}</small></article>
        </section>
      </header>

      <section className={styles.layout}>
        <section className={styles.centerPane} aria-label="公司运行状态一览图">
          <div className={styles.decisionBand}>
            <div>
              <span>今天先看</span>
              <strong>{decisionItems[0] ?? "公司运行平稳"}</strong>
            </div>
            <div className={styles.decisionChips}>
              {(decisionItems.length > 1 ? decisionItems.slice(1) : ["暂无需重连", "无待处理提醒", "电脑状态正常"]).map((item, index) => (
                <span key={`${item}-${index}`}>{item}</span>
              ))}
            </div>
          </div>

          <section className={styles.officeNetwork} aria-label="NPC 办公网">
            <header>
              <div>
                <span>NPC 办公网</span>
                <strong>一张图看谁在和谁协作</strong>
              </div>
              <div className={styles.networkLegend}>
                <span data-tone="review">需求</span>
                <span data-tone="healthy">承接/完成</span>
                <span data-tone="blocked">阻塞</span>
                <span>点击线看详情</span>
              </div>
            </header>
            <div className={styles.officeMap}>
              <svg className={styles.officeSvg} viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="NPC 协作网络线">
                {officeEdges.map((edge, index) => {
                  const from = officeNodeById.get(edge.fromId);
                  const to = officeNodeById.get(edge.toId);
                  if (!from || !to) return null;
                  const dx = to.x - from.x;
                  const dy = to.y - from.y;
                  const p1x = from.x + dx * 0.16;
                  const p1y = from.y + dy * 0.16;
                  const p2x = from.x + dx * 0.42;
                  const p2y = from.y + dy * 0.42;
                  const p3x = from.x + dx * 0.68;
                  const p3y = from.y + dy * 0.68;
                  const p4x = from.x + dx * 0.86;
                  const p4y = from.y + dy * 0.86;
                  const labelX = from.x + dx * 0.5;
                  const labelY = from.y + dy * 0.5 - (index % 2 ? 2.8 : -2.8);
                  const width = Math.min(4.2, 1.4 + edge.count * 0.45);
                  const href = `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=company`;
                  return (
                    <a key={edge.id} href={href} className={styles.networkEdgeLink} aria-label={`${from.seat.name} 到 ${to.seat.name}: ${edge.label}`}>
                      <line x1={p1x} y1={p1y} x2={p2x} y2={p2y} className={styles.networkEdge} data-tone={chainTone(edge.needStatus)} strokeWidth={width} />
                      <line x1={p2x} y1={p2y} x2={p3x} y2={p3y} className={styles.networkEdge} data-tone={chainTone(edge.taskStatus)} strokeWidth={width} />
                      <line x1={p3x} y1={p3y} x2={p4x} y2={p4y} className={styles.networkEdge} data-tone={chainTone(edge.receiptStatus)} strokeWidth={width} />
                      <text x={labelX} y={labelY} className={styles.networkEdgeLabel}>
                        {edge.count > 1 ? `${edge.count}条 ` : ""}{edge.label}
                      </text>
                    </a>
                  );
                })}
              </svg>
              <div className={styles.officeNodeLayer}>
                {officeNodes.map((node) => (
                  <Link
                    key={node.id}
                    href={`/projects/${projectId}/workbench?seat_id=${encodeURIComponent(node.id)}&return_to=${encodeURIComponent(selfPath)}&from=company`}
                    className={styles.officeNode}
                    data-tone={node.tone}
                    style={{ left: `${node.x}%`, top: `${node.y}%` }}
                  >
                    <b>{node.seat.name.slice(0, 2).toUpperCase()}</b>
                    <strong>{node.seat.name}</strong>
                    <span>{node.outgoingCount}/{node.incomingCount}/{node.taskCount}</span>
                  </Link>
                ))}
              </div>
              {!officeEdges.length ? (
                <div className={styles.emptyOfficeNetwork}>
                  <strong>还没有 NPC 间协作线</strong>
                  <p>NPC 创建 Need 并路由成 Task 后，这里会出现带颜色分段的协作线。</p>
                </div>
              ) : null}
            </div>
          </section>

          <div className={styles.sandbox}>
            <div className={styles.flowLayer} aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            {workstationRows.map((ws, index) => {
              const wsReady = ws.seats.filter((seat) => seat.dispatchState === "可投递").length;
              const wsQueueable = ws.seats.filter(
                (seat) =>
                  seat.threadId
                  && seat.dispatchCanQueue
                  && ["最近在线，可能延迟", "他人操作中"].includes(seat.dispatchState),
              ).length;
              const wsAttention = ws.seats.filter(
                (seat) =>
                  seat.dispatchState === "等待电脑恢复"
                  || seat.dispatchState === "离线，需重连"
                  || seat.dispatchState === "状态未知，先检查接入",
              ).length;
              const tone = wsAttention ? "blocked" : wsReady ? "healthy" : "idle";
              return (
                <article key={ws.id} className={styles.departmentZone} data-tone={tone} data-active={index === 0 ? "1" : undefined}>
                  <header>
                    <div>
                      <span>部门区域</span>
                      <strong>{ws.name}</strong>
                      <small>负责人：{ws.leadName}</small>
                    </div>
                    <dl>
                      <div><dt>可投递</dt><dd>{wsReady}</dd></div>
                      <div><dt>仅排队</dt><dd>{wsQueueable}</dd></div>
                      <div><dt>待处理</dt><dd>{wsAttention}</dd></div>
                    </dl>
                  </header>

                  <div className={styles.seatGrid}>
                    {ws.seats.length ? ws.seats.map((seat) => (
                      <Link
                        key={seat.id}
                        href={`/projects/${projectId}/workbench?seat_id=${encodeURIComponent(seat.id)}&return_to=${encodeURIComponent(selfPath)}&from=company`}
                        className={styles.seatNode}
                        data-tone={statusTone(seat.dispatchState)}
                        title={`打开 ${seat.name} 的 NPC 工作台：${seat.dispatchDetail}`}
                      >
                        <span className={styles.avatar}>{seat.name.slice(0, 2).toUpperCase()}</span>
                        <strong>{seat.name}</strong>
                        <small>{seat.dispatchShortLabel} · {seat.threadHealth}</small>
                        <em>{seat.dispatchState}</em>
                      </Link>
                    )) : (
                      <div className={styles.emptySeat}>
                        <strong>待分配 NPC</strong>
                        <p>先在主页面创建 NPC，再回公司层分配部门和职责。</p>
                      </div>
                    )}
                  </div>

                  <div className={styles.deviceDock}>
                    {(ws.seats.length ? ws.seats : []).filter((seat) => seat.computerNodeName).slice(0, 4).map((seat) => (
                      <span key={`${ws.id}-${seat.id}-node`} data-tone={statusTone(seat.dispatchState)}>
                        {seat.computerNodeName}
                      </span>
                    ))}
                    {!ws.seats.some((seat) => seat.computerNodeName) ? <span data-tone="idle">待绑定电脑</span> : null}
                  </div>
                </article>
              );
            })}
            {!allSeats.length ? (
              <article className={styles.emptyRow}>
                <strong>还没有 NPC 员工</strong>
                <p>先在主页面创建 NPC、扫描线程并绑定，再回公司层分配职责和确认规则。</p>
              </article>
            ) : null}
          </div>
        </section>

        <aside className={styles.sidePane} aria-label="公司经营明细">
          <section className={styles.tokenPanel}>
            <header>
              <strong>今日 Token</strong>
              <small>{todayUsage.length ? "来自真实用量记录" : projectUsage.length ? "最近记录" : "等待用量回写"}</small>
            </header>
            <div className={styles.tokenGrid}>
              <article>
                <span>今日消耗</span>
                <strong>{formatTokenCount(tokenTotalToday)}</strong>
                <small>/ {formatTokenCount(tokenBudget)}</small>
                <i style={{ width: `${Math.min(100, tokenBudget ? (tokenTotalToday / tokenBudget) * 100 : 0)}%` }} />
              </article>
              <article>
                <span>缓存节省</span>
                <strong>{formatTokenCount(tokenCachedToday)}</strong>
                <small>{tokenCachedToday ? "已复用上下文" : "统计中"}</small>
                <i style={{ width: `${Math.min(100, tokenTotalToday ? (tokenCachedToday / Math.max(tokenTotalToday, 1)) * 100 : 0)}%` }} />
              </article>
            </div>
          </section>

          <section className={styles.detailPanel}>
            <header>
              <span>协作明细</span>
              <strong>最近记录</strong>
            </header>
            <div className={styles.miniStats}>
              <article><strong>{runningEventCount}</strong><span>进行中</span></article>
              <article><strong>{completedEventCount}</strong><span>已完成</span></article>
              <article><strong>{allOrgEvents.length}</strong><span>总计</span></article>
            </div>
            <div className={styles.taskList}>
              {taskDetailItems.map((event, index) => (
                <Link
                  key={text(event.id, `company-detail-${index}`)}
                  href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=company`}
                  className={styles.taskItem}
                >
                  <strong>{publicEventTitle(event)}</strong>
                  <span>{publicEventDescription(event)}</span>
                  <small>{publicStatusLabel(event.status)} ›</small>
                </Link>
              ))}
              {!taskDetailItems.length ? <p className={styles.emptyText}>还没有协作明细。</p> : null}
            </div>
          </section>
        </aside>

      </section>

      <section className={styles.bottomDock} aria-label="组织变更日志">
        <div className={styles.logHeader}>
          <span>组织变更 / 协作事件</span>
          <strong>{recentOrgEvents.length ? `${recentOrgEvents.length} 条` : "等待事件"}</strong>
        </div>
        <div className={styles.logRows}>
          {(pendingHumanReviews.length ? pendingHumanReviews.slice(0, 6) : recentOrgEvents).map((event, index) => (
            <article key={text(event.id, `event-${index}`)}>
              <span>{isPendingHumanReview(event) ? reviewSourceLabel(event) : publicStatusLabel(event.status)}</span>
              <strong>{publicEventTitle(event)}</strong>
              <p>{publicEventDescription(event)}</p>
            </article>
          ))}
          {!pendingHumanReviews.length && !recentOrgEvents.length ? (
            <p className={styles.emptyText}>还没有组织变更事件。创建工位、绑定能力或调整确认规则后会在这里显示摘要。</p>
          ) : null}
        </div>
      </section>
    </main>
  );
}
