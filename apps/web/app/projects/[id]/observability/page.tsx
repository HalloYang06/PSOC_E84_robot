import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCollaborationMessagesState,
  getApiHealthState,
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectScorecardState,
  getProjectState,
  getProjectThreadWorkstationAdapterConfigState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
  getTaskProfessionalViewState,
  getTasksDataScopedState,
  getUsageData,
} from "../../../../lib/server-data";
import { runnerStateLabel } from "../../../../lib/runner-status";
import { CurrentBrowserInstance } from "./current-browser-instance";
import styles from "./observability.module.css";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type AnyRecord = Record<string, any>;
const CURRENT_CHAIN_SEATS = [
  "1号 前端实现",
  "2号 后端数据流",
  "3号 前端验收",
  "5号 Runner 与桌面同步",
] as const;

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function asTextList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => text(item, "")).filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .split(/[,;\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? (value as AnyRecord) : {};
}

function computerStatusLabel(value: unknown) {
  const normalized = statusText(value);
  if (/online|ready|active/.test(normalized)) return "在线";
  if (/busy|running|in_progress/.test(normalized)) return "忙碌";
  if (/offline|lost|stale|error/.test(normalized)) return "离线";
  return text(value, "待确认");
}

function userFacingText(value: unknown, fallback = "") {
  const next = String(value ?? "")
    .replace(/source_message_id/gi, "起点记录")
    .replace(/root_message_id/gi, "汇总记录")
    .replace(/delegation_context/gi, "当前链路")
    .replace(/source_message/gi, "起点记录")
    .replace(/root_message/gi, "汇总记录")
    .replace(/alias_display_non_authoritative/gi, "历史标识展示规则")
    .replace(/historical[_\s-]*alias(?:[_\s-]*non[_\s-]*authoritative)?/gi, "历史标识")
    .replace(/历史\s*alias/gi, "历史标识")
    .replace(/current\s+alias/gi, "当前标识")
    .replace(/source_thread/gi, "来源桌面线程")
    .replace(/canonical_workstation_id/gi, "正式工位")
    .replace(/requested_workstation_id/gi, "请求工位")
    .replace(/authoritative_([a-z]+_)?seat_id/gi, "正式 NPC")
    .replace(/authoritative_target_seat_id/gi, "目标 NPC")
    .replace(/sender_id/gi, "发送方")
    .replace(/codex-session-[0-9a-z-]+/gi, "绑定桌面线程")
    .replace(/codex-session/gi, "桌面线程")
    .replace(/线程\s*codex/gi, "桌面线程")
    .replace(/session JSONL/gi, "桌面记录")
    .replace(/Provider CLI/gi, "执行通道")
    .replace(/Local prompt file/gi, "本地任务说明")
    .replace(/adapter/gi, "同步")
    .replace(/bridge/gi, "同步")
    .replace(/执行失败[:：]?/g, "待收口")
    .replace(/hard failed/gi, "待收口")
    .replace(/\b([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "记录 $1")
    .trim();
  return next || fallback;
}

function collaborationEventTypeLabel(value: unknown) {
  const normalized = statusText(value);
  if (/runner_command|task_dispatch|dispatch/.test(normalized)) return "派单事件";
  if (/requirement_final_reply|final_reply|final/.test(normalized)) return "最终回执";
  if (/requirement_progress_ack|progress_ack|agent_progress|ack/.test(normalized)) return "过程回执";
  if (/desktop_user_question|desktop.*question/.test(normalized)) return "桌面提问";
  if (/requirement|need/.test(normalized)) return "协作需求";
  if (/review|approval/.test(normalized)) return "人工审核";
  if (/artifact|evidence/.test(normalized)) return "证据";
  if (/message|chat/.test(normalized)) return "协作消息";
  return userFacingText(value, "协作消息");
}

function compactEvidenceId(value: unknown, fallback = "等待") {
  const raw = text(value, "");
  if (!raw) return fallback;
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)) {
    return `记录 ${raw.slice(0, 8)}`;
  }
  if (raw.length > 28 && /^[0-9a-z_-]+$/i.test(raw)) {
    return `记录 ${raw.slice(0, 8)}`;
  }
  return userFacingText(raw, fallback);
}

function lineageRecordLabel(value: unknown, fallback: string) {
  const compact = compactEvidenceId(value, fallback);
  if (compact === fallback) return fallback;
  return compact.startsWith("记录 ") ? compact : `记录 ${compact}`;
}

function isHistoricalAliasValue(value: string) {
  return /codex-session|claude-session|session-|thread-|legacy|alias/i.test(value);
}

function seatDisplayName(value: unknown, seatsById: Map<string, string>, fallback = "协作者") {
  const raw = text(value, "");
  if (!raw) return fallback;
  const mapped = seatsById.get(raw);
  if (mapped) return mapped;
  return isHistoricalAliasValue(raw) ? "历史标识" : userFacingText(raw, fallback);
}

function authoritativeSeatName(item: AnyRecord, seatsById: Map<string, string>, role: "source" | "target", fallback: string) {
  const meta = messageMetadata(item);
  const raw = role === "source"
    ? meta.authoritative_sender_seat_id ?? meta.authoritative_seat_id ?? meta.delegated_via_seat_id ?? item.sender_id
    : meta.authoritative_target_seat_id
      ?? meta.intended_target_seat_id
      ?? meta.routed_recipient_seat_id
      ?? meta.downstream_seat_id
      ?? meta.intended_target_name
      ?? meta.routed_recipient_name
      ?? item.recipient_id;
  return seatDisplayName(raw, seatsById, fallback);
}

function statusText(value: unknown) {
  return text(value, "").toLowerCase();
}

function safeProjectReturnPath(projectId: string, value: unknown) {
  const raw = text(value, "");
  if (!raw.startsWith(`/projects/${projectId}/`)) return "";
  if (/^\/\//.test(raw) || raw.includes("\\") || raw.includes("://")) return "";
  return raw;
}

function labelProjectReturnPath(value: string) {
  if (value.includes("/workbench")) return "返回 NPC 工作台";
  if (value.includes("/datasets")) return "返回数据工场";
  if (value.includes("/ai-lab")) return "返回 AI 实验室";
  if (value.includes("/robotics")) return "返回机器人现场";
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/observability")) return "返回观测台";
  if (value.includes("/skill-forge")) return "返回能力工坊";
  return "返回来源";
}

function messageTitle(item: AnyRecord) {
  return userFacingText(item.title ?? item.body ?? item.message_type ?? item.id, "未命名消息");
}

function statusLabel(value: unknown) {
  const normalized = statusText(value);
  if (["done", "completed", "resolved"].includes(normalized)) return "完成";
  if (["blocked", "failed", "error", "rejected"].includes(normalized)) return "待处理";
  if (["pending_review", "waiting_review", "review"].includes(normalized)) return "待审";
  if (["queued", "active", "running", "in_progress", "accepted"].includes(normalized)) return "进行中";
  if (["online", "ready"].includes(normalized)) return "在线";
  return text(value, "待处理");
}

function messageMetadata(item: AnyRecord | null | undefined) {
  if (!item) return {};
  const meta = item.metadata && typeof item.metadata === "object" ? item.metadata as AnyRecord : {};
  const extra = item.extra_data && typeof item.extra_data === "object" ? item.extra_data as AnyRecord : {};
  return { ...extra, ...meta };
}

function isPlatformValidationRecord(item: AnyRecord | null | undefined) {
  if (!item) return false;
  const metadata = messageMetadata(item);
  const validationKind = text(
    metadata.validation_kind
      ?? metadata.validationKind
      ?? metadata.validation
      ?? item.validation_kind
      ?? item.validationKind,
    "",
  );
  if (/^(cloud_runner_|runner_|platform_validation|workbench_validation)/i.test(validationKind)) return true;
  const title = `${text(item.title, "")} ${text(item.name, "")} ${text(item.label, "")}`;
  return /云端多电脑隔离验收|隔离验收电脑|隔离验收 NPC|平台验收脚本/i.test(title);
}

function getBlockedTaxonomy(item: AnyRecord | null | undefined) {
  const metadata = item ? messageMetadata(item) : {};
  return metadata.blocked_taxonomy && typeof metadata.blocked_taxonomy === "object"
    ? metadata.blocked_taxonomy as AnyRecord
    : {};
}

function isDesktopCloseoutWaiting(item: AnyRecord | null | undefined) {
  if (!item) return false;
  const metadata = messageMetadata(item);
  const taxonomy = getBlockedTaxonomy(item);
  const code = statusText(taxonomy.blocked_reason_code ?? taxonomy.exception_kind ?? metadata.progress_state);
  return Boolean(metadata.desktop_closeout_waiting || taxonomy.desktop_closeout_waiting)
    || code === "desktop_final_sync_lag"
    || code === "desktop_delivery_unconfirmed";
}

function computerDispatchState(node: AnyRecord | undefined) {
  return runnerStateLabel(node);
}

function seatComputerNodeId(seat: AnyRecord, config: AnyRecord = {}) {
  const metadata = messageMetadata(seat);
  const extra = record(seat.extra_data ?? seat.extraData);
  return text(
    seat.computer_node_id
      ?? seat.computerNodeId
      ?? seat.computer_node
      ?? seat.computerNode
      ?? metadata.computer_node_id
      ?? metadata.computerNodeId
      ?? extra.computer_node_id
      ?? extra.computerNodeId
      ?? config.computer_node_id
      ?? config.computerNodeId,
    "",
  );
}

function seatCanTakeTask(seat: AnyRecord, config: AnyRecord, computerById: Map<string, AnyRecord>) {
  const threadId = text(
    seat.thread_id
      ?? seat.threadId
      ?? seat.target_thread_id
      ?? seat.targetThreadId
      ?? seat.source_workstation_id
      ?? seat.sourceWorkstationId,
    "",
  );
  if (!threadId) return false;
  const nodeId = seatComputerNodeId(seat, config);
  if (!nodeId) return false;
  return computerDispatchState(computerById.get(nodeId)) === "可投递";
}

function collaborationStatusLabel(item: AnyRecord) {
  if (isDesktopCloseoutWaiting(item)) return "待收口";
  return statusLabel(item.status);
}

type PeerDispatchRow = {
  id: string;
  title: string;
  sourceName: string;
  targetName: string;
  sourceMessageId: string;
  rootMessageId: string;
  delegatedViaSeat: string;
  state: "queued" | "delivered" | "acked" | "blocked" | "finaled" | "next_ready" | "pending_closeout";
  ack: boolean;
  final: boolean;
  blockedReason: string;
  nextAction: string;
  platformDefect: boolean;
  blockedReasonCode: string;
};

function relatedSourceMessageId(item: AnyRecord) {
  const meta = (item.metadata ?? item.extra_data ?? {}) as AnyRecord;
  return text(meta.source_message_id ?? meta.sourceMessageId, "");
}

function normalizeDispatchState(
  status: string,
  hasAck: boolean,
  hasFinal: boolean,
  blockedReason: string,
  blockedReasonCode: string,
  platformDefect: boolean,
): PeerDispatchRow["state"] {
  const normalized = status.toLowerCase();
  if (blockedReasonCode === "desktop_final_sync_lag" || blockedReasonCode === "desktop_delivery_unconfirmed" || platformDefect) return "pending_closeout";
  if (blockedReason || ["failed", "rejected", "blocked"].includes(normalized)) return "blocked";
  if (hasFinal || ["completed", "done", "delivered"].includes(normalized)) return "finaled";
  if (hasAck || normalized === "acked") return "acked";
  if (["in_progress", "running", "active"].includes(normalized)) return "delivered";
  return "queued";
}

function firstText(values: unknown[], fallback = "") {
  for (const value of values) {
    const next = text(value, "");
    if (next) return next;
  }
  return fallback;
}

function focusHref(
  projectId: string,
  surface: "workbench" | "datasets" | "ai-lab" | "robotics" | "observability",
  selfPath: string,
  options: {
    taskId?: string;
    messageId?: string;
    dispatchId?: string;
    sourceSeat?: string;
    sourceLabel?: string;
    sourceTitle?: string;
    from?: string;
    filter?: string;
    action?: string;
  } = {},
) {
  const params = new URLSearchParams();
  params.set("return_to", selfPath);
  params.set("from", options.from ?? "observability");
  if (options.taskId) params.set("task_id", options.taskId);
  if (options.messageId) params.set("message_id", options.messageId);
  if (options.dispatchId) params.set("dispatch_id", options.dispatchId);
  if (options.sourceSeat) params.set("source_seat", options.sourceSeat);
  if (options.sourceLabel) params.set("source_label", options.sourceLabel);
  if (options.sourceTitle) params.set("source_title", options.sourceTitle);
  if (options.filter) params.set("filter", options.filter);
  if (options.action) params.set("action", options.action);
  return `/projects/${projectId}/${surface}?${params.toString()}`;
}

export default async function ProjectObservabilityPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: {
    return_to?: string;
    from?: string;
    task_id?: string;
    message_id?: string;
    dispatch_id?: string;
    source_seat?: string;
    source_label?: string;
    source_title?: string;
    focus?: string;
  };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/observability`)}`);
  }

  const projectState = await getProjectState(projectId);
  const project = projectState.data;
  if (!project) {
    return (
      <main className={styles.emptyPage}>
        <p>项目不存在或无权限。</p>
        <Link href="/projects">返回项目列表</Link>
      </main>
    );
  }

  const [
    computersState,
    seatsState,
    workstationsState,
    tasksState,
    messagesState,
    pendingReviewState,
    scorecardState,
    healthState,
    usageData,
    taskProfessionalState,
  ] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
    getTasksDataScopedState({ projectIds: [projectId] }),
    getCollaborationMessagesState({ projectId }),
    getCollaborationMessagesState({ projectId, status: "pending_review" }),
    getProjectScorecardState(projectId),
    getApiHealthState(),
    getUsageData(),
    searchParams?.task_id ? getTaskProfessionalViewState(searchParams.task_id) : Promise.resolve({ data: null, status: 200, error: null }),
  ]);

  const rawComputers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(seatsState.data);
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const tasks = asArray<AnyRecord>(tasksState.data);
  const rawMessages = asArray<AnyRecord>(messagesState.data);
  const rawPendingReview = asArray<AnyRecord>(pendingReviewState.data);
  const computers = rawComputers.filter((item) => !isPlatformValidationRecord(item));
  const messages = rawMessages.filter((item) => !isPlatformValidationRecord(item));
  const pendingReview = rawPendingReview.filter((item) => !isPlatformValidationRecord(item));
  const computerById = new Map<string, AnyRecord>();
  for (const node of computers) {
    const id = text(node.id ?? node.config_id ?? node.node_id ?? node.nodeId, "");
    if (id) computerById.set(id, node);
  }
  const adapterConfigs = await Promise.all(
    seats.map(async (seat) => {
      const id = text(seat.id ?? seat.name, "");
      if (!id) return { id, data: {} as AnyRecord };
      const state = await getProjectThreadWorkstationAdapterConfigState(projectId, id);
      return { id, data: (state.data ?? {}) as AnyRecord };
    }),
  );
  const adapterBySeat = new Map(adapterConfigs.map((item) => [item.id, item.data]));
  const platformNumberedSeats = seats.filter((seat) => /^platform-npc-[1-6]$/i.test(text(seat.id ?? seat.name, "")));
  const evidenceSeats = platformNumberedSeats.length >= 6 ? platformNumberedSeats : seats;
  const usage = asArray<AnyRecord>(usageData).filter((item) => !text(item.project_id ?? item.projectId, "") || text(item.project_id ?? item.projectId, "") === projectId);
  const onlineComputers = computers.filter((node) => computerDispatchState(node) === "可投递").length;
  const computerCapabilityRows = computers.map((node, index) => {
    const capabilities = Array.from(new Set([
      ...asTextList(node.capabilities),
      ...asTextList(node.runner_capabilities ?? node.runnerCapabilities),
      ...asTextList(node.capability_labels ?? node.capabilityLabels),
    ])).slice(0, 5);
    const status = node.runner_effective_status ?? node.runner_status ?? node.status;
    const dispatchState = computerDispatchState(node);
    const isOnline = dispatchState === "可投递";
    const osLabel = text(node.os ?? node.platform ?? node.computer_node_os ?? node.computerNodeOs, "系统待识别");
    const hostLabel = text(node.host ?? node.hostname ?? node.computer_node_host ?? node.computerNodeHost, "");
    return {
      key: text(node.id ?? node.runner_id ?? node.name, `computer-${index}`),
      name: text(node.label ?? node.name ?? node.runner_label ?? node.runner_id, `执行电脑 ${index + 1}`),
      status: dispatchState,
      state: isOnline ? "ready" : dispatchState === "最近在线，可能延迟" || dispatchState === "等待电脑恢复" || /busy|running|in_progress/.test(statusText(status)) ? "watch" : "blocked",
      osLabel,
      hostLabel,
      capabilities,
      detail: capabilities.length
        ? capabilities.join(" / ")
        : "等待能力登记，先确认这台电脑能跑哪些采集、构建或执行任务。",
    };
  });
  const capabilityPool = new Set(computerCapabilityRows.flatMap((row) => row.capabilities.map((item) => item.toLowerCase())));
  const dispatchMessages = messages.filter((item) => statusText(item.proof_stage) === "dispatch" || statusText(item.message_type).includes("dispatch"));
  const finalMessages = messages.filter((item) => Boolean(item.is_final_reply) || statusText(item.proof_stage) === "final_reply" || statusText(item.message_type).includes("final"));
  const progressMessages = messages.filter((item) => Boolean(item.is_progress_signal));
  const completedReceipts = messages.filter((item) => {
    const status = statusText(item.status);
    const type = statusText(item.message_type ?? item.messageType);
    return ["completed", "done", "delivered"].includes(status) && (type === "agent_result" || type.includes("receipt") || type.includes("final"));
  });
  const completedSourceIds = new Set(
    completedReceipts
      .map((item) => relatedSourceMessageId(item))
      .filter(Boolean),
  );
  const completedHumanDispatches = messages.filter((item) => {
    const status = statusText(item.status);
    return ["completed", "done", "delivered"].includes(status) && statusText(item.sender_type ?? item.senderType) === "human";
  });
  const completedPeerDispatches = messages.filter((item) => {
    const status = statusText(item.status);
    const sender = statusText(item.sender_type ?? item.senderType);
    const recipient = statusText(item.recipient_type ?? item.recipientType);
    return ["completed", "done", "delivered"].includes(status) && sender.includes("agent") && recipient.includes("agent");
  });
  const hardwarePending = pendingReview.filter((item) => {
    const haystack = `${messageTitle(item)} ${text(item.body, "")} ${JSON.stringify(item.metadata ?? {})}`.toLowerCase();
    return /(hardware|ros|motion|firmware|deploy|restart|硬件|实机|运动)/i.test(haystack);
  });
  const closeoutWaitingMessages = messages.filter((item) => {
    if (!isDesktopCloseoutWaiting(item)) return false;
    const sourceId = relatedSourceMessageId(item);
    return !sourceId || !completedSourceIds.has(sourceId);
  });
  const failedAutonomousMessages = messages.filter((item) => {
    if (isDesktopCloseoutWaiting(item)) return false;
    const meta = messageMetadata(item);
    const haystack = `${messageTitle(item)} ${text(item.body, "")} ${JSON.stringify(meta)}`.toLowerCase();
    return ["failed", "blocked", "rejected"].includes(statusText(item.status)) && /(peer|dispatch|npc|自主|免审|超时|timeout)/i.test(haystack);
  });
  const desktopReadySeats = evidenceSeats.filter((seat) => {
    const id = text(seat.id ?? seat.name, "");
    const config = adapterBySeat.get(id) ?? {};
    return Boolean(config.desktop_visible ?? config.desktopVisible) && text(config.desktop_delivery_mode ?? config.desktopDeliveryMode, "") === "codex_desktop_ui";
  });
  const desktopNotLiveSeats = evidenceSeats.filter((seat) => {
    const id = text(seat.id ?? seat.name, "");
    const config = adapterBySeat.get(id) ?? {};
    const warning = `${text(config.delivery_warning ?? config.deliveryWarning, "")} ${text(config.delivery_label ?? config.deliveryLabel, "")}`;
    return /not Desktop live|app-server|adapter/i.test(warning);
  });
  const deliverableSeats = evidenceSeats.filter((seat) => {
    const id = text(seat.id ?? seat.name, "");
    const config = adapterBySeat.get(id) ?? {};
    return seatCanTakeTask(seat, config, computerById);
  });
  const dispatchEvidenceReady =
    evidenceSeats.length > 0 &&
    deliverableSeats.length === evidenceSeats.length &&
    completedHumanDispatches.length > 0 &&
    completedReceipts.length > 0;
  const blockedTasks = tasks.filter((item) => /blocked|failed|error/.test(statusText(item.status))).length;
  const activeTasks = tasks.filter((item) => /active|running|in_progress|queued/.test(statusText(item.status))).length;
  const sc = scorecardState.data as AnyRecord | null;
  const health = (healthState.data ?? {}) as AnyRecord;
  const taskView = taskProfessionalState.data as AnyRecord | null;
  const localServices = asArray<AnyRecord>(health.local_services ?? health.localServices);
  const listeningPorts = localServices.filter((item) => Boolean(item.listening)).map((item) => text(item.port, ""));
  const overall = (sc?.overall ?? {}) as AnyRecord;
  const grade = text(overall.grade, "-");
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/observability`;
  const latestTaskMessage = Array.isArray(taskView?.messages) ? (taskView.messages as AnyRecord[])[0] : null;
  const latestTaskReceipt = Array.isArray(taskView?.receipts) ? (taskView.receipts as AnyRecord[])[0] : null;
  const latestTaskDispatch = Array.isArray(taskView?.dispatches) ? (taskView.dispatches as AnyRecord[])[0] : null;
  const taskExceptionSummary = taskView?.summary?.exception_summary && typeof taskView.summary.exception_summary === "object"
    ? taskView.summary.exception_summary as AnyRecord
    : {};
  const focusTitle = text(searchParams?.source_title, text(taskView?.task?.title, "当前证据链"));
  const focusSeat = text(searchParams?.source_label ?? searchParams?.source_seat, "待选择目标");
  const currentTaskId = text(taskView?.task?.id ?? taskView?.summary?.task_id ?? searchParams?.task_id, "");
  const currentDispatchId = firstText([
    searchParams?.dispatch_id,
    latestTaskMessage?.dispatch_id,
    latestTaskReceipt?.dispatch_id,
    latestTaskDispatch?.id,
  ], "");
  const currentSourceMessageId = firstText([
    searchParams?.message_id,
    latestTaskReceipt?.source_message_id,
    latestTaskMessage?.id,
  ], "");
  const currentRootMessageId = firstText([
    latestTaskReceipt?.root_message_id,
    messageMetadata(latestTaskReceipt).root_message_id,
    messageMetadata(latestTaskMessage).root_message_id,
    messageMetadata(latestTaskDispatch).root_message_id,
    messageMetadata(latestTaskReceipt).source_message_id,
    messageMetadata(latestTaskMessage).source_message_id,
  ], "");
  const currentReceiptId = firstText([
    latestTaskReceipt?.message_id,
    taskView?.summary?.latest_result_message_id,
  ], "");
  const currentArtifactCount = String(Number(taskView?.summary?.artifact_count ?? 0) || 0);
  const currentAuditCount = String(Number(taskView?.summary?.audit_count ?? 0) || 0);
  const currentReceiptCount = String(Number(taskView?.summary?.receipt_count ?? 0) || 0);
  const currentPendingCloseoutNumber = Number(taskView?.summary?.pending_closeout_count ?? 0) || 0;
  const currentExceptionNumber = Number(taskExceptionSummary.failed ?? 0) || 0;
  const currentPendingCloseout = String(currentPendingCloseoutNumber);
  const currentExceptionCount = String(currentExceptionNumber);
  const chainFocused = Boolean(currentTaskId || currentDispatchId || currentSourceMessageId || searchParams?.source_seat);
  const sharedFocus = {
    taskId: currentTaskId,
    messageId: currentSourceMessageId,
    dispatchId: currentDispatchId,
    sourceSeat: searchParams?.source_seat,
    sourceLabel: searchParams?.source_label,
    sourceTitle: focusTitle,
  };
  const matchesCurrentChain = (item: AnyRecord) => {
    if (!chainFocused) return false;
    const meta = messageMetadata(item);
    const ids = [
      item.id,
      item.task_id,
      item.dispatch_id,
      meta.source_message_id,
      meta.root_message_id,
      meta.dispatch_id,
      meta.task_id,
    ].map((value) => text(value, ""));
    return Boolean(
      (currentTaskId && ids.includes(currentTaskId))
      || (currentDispatchId && ids.includes(currentDispatchId))
      || (currentSourceMessageId && ids.includes(currentSourceMessageId))
      || (currentRootMessageId && ids.includes(currentRootMessageId)),
    );
  };
  const currentPendingReview = pendingReview.filter(matchesCurrentChain);
  const currentHardwarePending = hardwarePending.filter(matchesCurrentChain);
  const currentCloseoutWaitingMessages = closeoutWaitingMessages.filter(matchesCurrentChain);
  const capabilityCoverageRows = [
    {
      label: "网页 / API",
      state: healthState.error ? "blocked" : "ready",
      detail: healthState.error ? "服务健康状态不可读，部署前先恢复。" : "页面和 API 已能通过观测台读取。",
    },
    {
      label: "任务执行",
      state: onlineComputers > 0 ? "ready" : "watch",
      detail: onlineComputers > 0 ? "已有在线执行电脑，可继续验证派发和回执。" : "至少接入一台执行电脑后再做部署验收。",
    },
    {
      label: "数据采集",
      state: Array.from(capabilityPool).some((item) => /serial|can|usb|ros|data|collect|采集/.test(item)) ? "ready" : "watch",
      detail: "用于承接串口、CAN、USB、ROS 或项目自定义采集能力。",
    },
    {
      label: "强审边界",
      state: currentHardwarePending.length > 0 ? "blocked" : "ready",
      detail: currentHardwarePending.length > 0 ? "当前链路存在高风险动作，必须人工确认。" : "当前链路没有高风险动作挡住稳定性验收。",
    },
  ];
  const historicalPendingReviewCount = Math.max(0, pendingReview.length - currentPendingReview.length);
  const historicalCloseoutCount = Math.max(0, closeoutWaitingMessages.length - currentCloseoutWaitingMessages.length);
  const historicalHardwarePendingCount = Math.max(0, hardwarePending.length - currentHardwarePending.length);
  const historicalBacklogCount = historicalPendingReviewCount + historicalCloseoutCount + historicalHardwarePendingCount;
  const seatNamesById = new Map<string, string>();
  for (const seat of seats) {
    const name = text(seat.name ?? seat.config_name ?? seat.id, "NPC");
    for (const key of [seat.id, seat.row_id, seat.rowId, seat.config_id, seat.configId, seat.name]) {
      const id = text(key, "");
      if (id) seatNamesById.set(id, name);
    }
  }
  const peerDispatchRows: PeerDispatchRow[] = messages
    .filter((item) => {
      const meta = messageMetadata(item);
      const isPeerOrigin = text(meta.origin, "") === "platform_peer_dispatches";
      const type = statusText(item.message_type);
      return statusText(item.sender_type).includes("agent") && (type === "requirement_dispatch" || isPeerOrigin);
    })
    .map((item) => {
      const meta = messageMetadata(item);
      const linked = messages.filter((candidate) => relatedSourceMessageId(candidate) === text(item.id, ""));
      const latestAck = linked.find((candidate) => statusText(candidate.status) === "acked" || statusText(candidate.message_type).includes("ack"));
      const latestFinal = linked.find((candidate) => {
        const s = statusText(candidate.status);
        const t = statusText(candidate.message_type);
        return ["completed", "done", "delivered"].includes(s) || t.includes("final") || t.includes("result");
      });
      const latestBlocked = linked.find((candidate) => ["failed", "rejected", "blocked"].includes(statusText(candidate.status)));
      const latestWaiting = linked.find((candidate) => isDesktopCloseoutWaiting(candidate));
      const blockedSource = latestWaiting ?? latestBlocked;
      const blockedTaxonomy = getBlockedTaxonomy(blockedSource);
      const blockedReasonCode = text(
        blockedTaxonomy.blocked_reason_code ?? blockedTaxonomy.exception_kind,
        "",
      );
      const blockedReason = blockedSource
        ? userFacingText(blockedTaxonomy.blocked_reason_label ?? blockedTaxonomy.exception_kind, messageTitle(blockedSource))
        : "";
      const platformDefect = Boolean(blockedTaxonomy.platform_defect);
      const state = normalizeDispatchState(
        statusText(item.status),
        Boolean(latestAck),
        Boolean(latestFinal),
        blockedReason,
        blockedReasonCode,
        platformDefect,
      );
      return {
        id: text(item.id, ""),
        title: messageTitle(item),
        sourceName: authoritativeSeatName(item, seatNamesById, "source", "Boss/NPC"),
        targetName: authoritativeSeatName(item, seatNamesById, "target", "目标 NPC"),
        sourceMessageId: text(meta.source_message_id, ""),
        rootMessageId: text(meta.root_message_id, ""),
        delegatedViaSeat: seatDisplayName(meta.delegated_via_seat_id, seatNamesById, text(meta.delegated_via_seat_id, "未登记")),
        state,
        ack: Boolean(latestAck),
        final: Boolean(latestFinal),
        blockedReason,
        nextAction: state === "pending_closeout"
          ? "催办 / 延长等待 / 重新同步 / 手动收口"
          : state === "blocked"
            ? "看阻塞"
            : state === "finaled"
              ? "看 final"
              : state === "acked"
                ? "继续下一步"
                : "看状态",
        platformDefect,
        blockedReasonCode,
      };
    })
    .slice(0, 8);
  const currentChainPeerRows = peerDispatchRows.filter((row) => {
    const ids = [row.id, row.sourceMessageId, row.rootMessageId].filter(Boolean);
    return Boolean(
      (currentDispatchId && ids.includes(currentDispatchId))
      || (currentSourceMessageId && ids.includes(currentSourceMessageId))
      || (currentRootMessageId && ids.includes(currentRootMessageId)),
    );
  });
  const visiblePeerRows = currentChainPeerRows.length ? currentChainPeerRows : peerDispatchRows;
  const currentChainMessages = messages.filter(matchesCurrentChain);
  const chainSeats = Array.from(new Set(
    currentChainMessages.flatMap((item) => {
      const meta = messageMetadata(item);
      return [
        seatDisplayName(meta.authoritative_sender_seat_id ?? item.sender_id, seatNamesById, ""),
        seatDisplayName(meta.authoritative_target_seat_id ?? item.recipient_id, seatNamesById, ""),
      ].filter(Boolean);
    }),
  )).filter((name) => /^([1-6]号 )/.test(name));
  const currentLineageMeta = messageMetadata(latestTaskReceipt ?? latestTaskMessage ?? latestTaskDispatch ?? {});
  const currentDelegation = currentLineageMeta.delegation_context && typeof currentLineageMeta.delegation_context === "object"
    ? currentLineageMeta.delegation_context as AnyRecord
    : {};
  const currentDelegationSource = firstText([
    currentDelegation.source_message_id,
    currentLineageMeta.source_message_id,
    currentSourceMessageId,
  ], "等待来源");
  const currentDelegationRoot = firstText([
    currentLineageMeta.root_message_id,
    currentDelegation.source_message_id,
    currentRootMessageId,
  ], "等待根链路");
  const currentDelegatedVia = seatDisplayName(
    currentDelegation.delegated_via_seat_id ?? currentLineageMeta.authoritative_sender_seat_id,
    seatNamesById,
    "等待委派",
  );
  const focusSeatName = text(
    searchParams?.source_label,
    seatDisplayName(searchParams?.source_seat, seatNamesById, focusSeat),
  );
  const hasFocusedSubject = chainFocused && focusSeatName !== "待选择目标";
  const currentSubjectName = chainFocused
    ? focusSeatName
    : peerDispatchRows[0]?.targetName ?? peerDispatchRows[0]?.sourceName ?? "待选择目标";
  const hasCurrentSubject = currentSubjectName !== "待选择目标";
  const currentTargetSeat = seatDisplayName(
    currentLineageMeta.authoritative_target_seat_id ?? currentDelegation.target_seat_id ?? searchParams?.source_seat,
    seatNamesById,
    currentSubjectName,
  );
  const chainWorkbenchObjects = [
    { label: "当前目标", value: focusTitle, detail: currentTaskId ? `任务 ${compactEvidenceId(currentTaskId)}` : "等待任务焦点" },
    { label: "起点记录", value: lineageRecordLabel(currentDelegationSource, "等待起点"), detail: "用来确认这条任务是从哪次派工进入的" },
    { label: "汇总记录", value: lineageRecordLabel(currentDelegationRoot, "等待汇总"), detail: "用来把同一目标下的分支结果收回一处" },
    { label: "当前负责", value: hasFocusedSubject ? currentDelegatedVia : "待选择目标", detail: hasFocusedSubject ? `当前指向 ${currentTargetSeat}` : "从 NPC 工作台打开一条任务证据链后显示负责 NPC" },
    { label: "聚合 NPC", value: chainSeats.length ? chainSeats.join(" / ") : currentSubjectName, detail: hasCurrentSubject ? `${visiblePeerRows.length} 条当前链路协作` : "等待选择链路后聚合参与 NPC" },
  ];
  const chainSeatCoverage = CURRENT_CHAIN_SEATS.map((seat) => {
    const attached = chainSeats.includes(seat)
      || visiblePeerRows.some((row) => row.targetName === seat || row.sourceName === seat || row.delegatedViaSeat === seat);
    return {
      seat,
      attached,
      detail: attached ? "已挂回当前目标链" : "当前还没在这条目标链里看到结果",
    };
  });
  const currentLineageCards = [
    { label: "起点记录", value: lineageRecordLabel(currentDelegationSource, "等待起点"), detail: "当前任务从哪次派工进入执行链" },
    { label: "汇总记录", value: lineageRecordLabel(currentDelegationRoot, "等待汇总"), detail: "让负责人和当前协作 NPC 看见同一目标链" },
    { label: "当前负责", value: currentDelegatedVia, detail: `当前目标 ${currentTargetSeat}` },
  ];
  const rightRailEvidence = [
    latestTaskDispatch
      ? { label: "当前派单", title: messageTitle(latestTaskDispatch), detail: compactEvidenceId(currentDispatchId, "等待派工记录") }
      : null,
    latestTaskReceipt
      ? { label: "当前回执", title: messageTitle(latestTaskReceipt), detail: compactEvidenceId(currentReceiptId, "等待回执记录") }
      : null,
    latestTaskMessage
      ? { label: "当前消息", title: messageTitle(latestTaskMessage), detail: collaborationEventTypeLabel(latestTaskMessage.message_type) }
      : null,
  ].filter(Boolean) as Array<{ label: string; title: string; detail: string }>;
  const observabilityTools = [
    { label: "当前链路", href: "#current-chain", detail: "目标 / 起点 / 汇总 / 负责 NPC", active: true },
    { label: "回执链", href: "#receipt-chain", detail: "派单 / 最小回执 / final" },
    { label: "异常入口", href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" }), detail: "待收口 / 失败 / 阻塞" },
    { label: "人工审核", href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "review" }), detail: "强审 / 放行 / 打回" },
    { label: "执行电脑", href: "#execution-computers", detail: "在线 / 能力 / 最近心跳" },
    { label: "验收脚本", href: "#acceptance-paths", detail: "点击链 / 泄漏 / 对齐" },
  ];

  const currentBlocker = chainFocused && currentHardwarePending.length > 0
    ? {
        label: "人工确认",
        title: `当前链路有 ${currentHardwarePending.length} 条强审动作`,
        detail: "涉及硬件、部署、运动或写入动作时，只能由人确认是否继续。",
        href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" }),
        cta: "去看待审与阻塞",
      }
    : chainFocused && (currentCloseoutWaitingMessages.length > 0 || currentPendingCloseoutNumber > 0)
      ? {
          label: "待收口",
          title: `当前链路有 ${currentCloseoutWaitingMessages.length || currentPendingCloseoutNumber} 条待收口`,
          detail: "NPC 和桌面过程可能已经推进，但最终回执还没挂回平台，需要负责人决定是催办、重同步还是继续等。",
          href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" }),
          cta: "去看待收口",
        }
      : chainFocused && currentExceptionNumber > 0
        ? {
            label: "异常",
            title: `当前链路有 ${currentExceptionNumber} 条异常需要判断`,
            detail: "先看证据和上下文，再决定是驳回、补证据还是继续让 NPC 修复。",
            href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" }),
            cta: "去看异常链路",
          }
        : dispatchEvidenceReady
          ? {
              label: "当前状态",
              title: "当前链路可继续推进",
              detail: historicalBacklogCount > 0
                ? "派工、最小回执和可投递通道已经接上；历史积压已收进抽屉，不再压住当前判断。"
                : "派工、最小回执和可投递通道已经接上，负责人现在主要判断下一步去哪一层继续看证据。",
              href: focusHref(projectId, "workbench", selfPath, sharedFocus),
              cta: "回 NPC 工作台",
            }
          : {
              label: "当前状态",
              title: "先补齐派工和回执链路",
              detail: "观测台已经能看见问题，但还需要把工作台、桌面和最小回执重新挂回同一条任务证据链。",
              href: focusHref(projectId, "workbench", selfPath, sharedFocus),
              cta: "打开 NPC 工作台",
            };

  const primaryActions = [
    {
      label: "主动作 1",
      title: "回 NPC 工作台看完整上下文",
      detail: "负责人的判断仍在对话流里完成，这里只负责把当前链路找准。",
      href: focusHref(projectId, "workbench", selfPath, sharedFocus),
    },
    {
      label: "主动作 2",
      title: (chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length) > 0 ? "处理当前待收口 / 重同步" : "看当前证据链",
      detail: (chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length) > 0
        ? "先确认当前链路的最终回执为什么没挂回，再决定催办、延长等待还是重同步。"
        : "沿当前任务链继续去数据工场、AI 实验室或机器人现场看证据。",
      href: (chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length) > 0
        ? focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "resync" })
        : focusHref(projectId, "datasets", selfPath, sharedFocus),
    },
    {
      label: "主动作 3",
      title: (chainFocused ? currentPendingReview.length : pendingReview.length) > 0 ? "看当前待审与风险边界" : "看最近协作证据",
      detail: (chainFocused ? currentPendingReview.length : pendingReview.length) > 0
        ? "AI 只能整理证据和异常，是否放行或打回仍由人决定。"
        : "快速确认最近谁派工、谁回执、哪一步还没闭环。",
      href: (chainFocused ? currentPendingReview.length : pendingReview.length) > 0
        ? focusHref(projectId, "workbench", selfPath, sharedFocus)
        : `${selfPath}?focus=recent-evidence`,
    },
  ];

  const recentEvidence = [
    latestTaskReceipt
      ? {
          label: "最新回执",
          title: messageTitle(latestTaskReceipt),
          detail: `${collaborationStatusLabel(latestTaskReceipt)} · ${text(latestTaskReceipt.at ?? latestTaskReceipt.created_at ?? latestTaskReceipt.updated_at, "") || "刚刚同步"}`,
        }
      : null,
    latestTaskMessage
      ? {
          label: "当前消息",
          title: messageTitle(latestTaskMessage),
          detail: `${collaborationStatusLabel(latestTaskMessage)} · ${collaborationEventTypeLabel(latestTaskMessage.message_type)}`,
        }
      : null,
    (chainFocused ? currentPendingReview[0] : pendingReview[0])
      ? {
          label: chainFocused ? "当前待审" : "待审消息",
          title: messageTitle(chainFocused ? currentPendingReview[0] : pendingReview[0]),
          detail: "需要负责人判断是否继续，不会由 AI 自动放行。",
        }
      : null,
    (chainFocused ? currentCloseoutWaitingMessages[0] : closeoutWaitingMessages[0])
      ? {
          label: chainFocused ? "当前待收口" : "待收口",
          title: messageTitle(chainFocused ? currentCloseoutWaitingMessages[0] : closeoutWaitingMessages[0]),
          detail: "桌面过程可能已继续，但平台还在等最终回执挂回当前任务。",
        }
      : null,
    messages[0]
      ? {
          label: "最近协作",
          title: messageTitle(messages[0]),
          detail: `${collaborationStatusLabel(messages[0])} · ${collaborationEventTypeLabel(messages[0].message_type)}`,
        }
      : null,
  ].filter(Boolean) as Array<{ label: string; title: string; detail: string }>;

  const kpis = [
    ["执行电脑在线", `${onlineComputers}/${computers.length}`, "多电脑能力是否可用"],
    ["NPC 线程", `${seats.length}`, "可接收平台派单的工作线程"],
    ["活跃任务", `${activeTasks}`, `阻塞 ${blockedTasks}`],
    ["当前待审", `${currentPendingReview.length}`, `历史 ${historicalPendingReviewCount}`],
    ["最小回执", `${completedReceipts.length}`, `用户派工 ${completedHumanDispatches.length}`],
    ["历史积压", `${historicalBacklogCount}`, text(overall.summary, `合格性 ${grade}`)],
  ];
  const closeoutActions = [
    ["桌面过程入口", focusHref(projectId, "workbench", selfPath, sharedFocus), "打开 NPC 工作台，查看完整桌面处理过程。"],
    ["最小回执", focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "receipt" }), "先确认平台是否已收到最小回执。"],
    ["待收口", focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" }), "桌面还在跑或最终同步滞后时，从这里继续处理。"],
    ["催办", focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "nudge" }), "提醒对应桌面线程补交最终回执，原任务链保持不变。"],
    ["延长等待", focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "extend_wait" }), "桌面仍在处理时保留等待窗口，避免把进行中误判成失败。"],
    ["自动重试 / 重新同步", focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "resync" }), "不改原命令状态，优先补拉最终结果；若桌面还在执行，保持处理中。"],
  ];
  const routeCards = [
    {
      label: "目标",
      title: currentTaskId || "等待任务焦点",
      detail: chainFocused ? "当前任务链已经进入观测台。" : "先从 NPC 工作台打开一条任务证据链。",
      href: focusHref(projectId, "workbench", selfPath, sharedFocus),
    },
    {
      label: "数据工场",
      title: "样本 / manifest / QA",
      detail: "检查证据是否已变成可训练、可导出的数据对象。",
      href: focusHref(projectId, "datasets", selfPath, sharedFocus),
    },
    {
      label: "AI 实验室",
      title: "实验 / 仿真 / 回放",
      detail: "沿同一条任务链继续看实验、回放和结果。",
      href: focusHref(projectId, "ai-lab", selfPath, sharedFocus),
    },
    {
      label: "机器人现场",
      title: "只读现场 / topic / 波形",
      detail: "只看当前任务链的现场证据，不扩散成说明页面。",
      href: focusHref(projectId, "robotics", selfPath, sharedFocus),
    },
    {
      label: "回 NPC 工作台",
      title: "继续协作 / 审核 / 收口",
      detail: "从观测台回去继续派工、催办、待收口。",
      href: focusHref(projectId, "workbench", selfPath, sharedFocus),
    },
  ];
  const acceptanceCards = [
    {
      label: "路径 1",
      title: "目标 -> NPC 派工 -> 观测台 -> 回工作台",
      detail: "从工作台带当前任务进入，发起后确认观测台出现当前证据链，再点回原 NPC。",
    },
    {
      label: "路径 2",
      title: "NPC 派工 -> 数据工场 -> 观测台",
      detail: "确认样本、版本、异常入口都保持同一任务关系，没有跳到旧页面。",
    },
    {
      label: "路径 3",
      title: "NPC 派工 -> AI 实验室 -> 观测台",
      detail: "确认实验、回放、审批边界都能回到当前证据链，不出现历史噪音。",
    },
    {
      label: "路径 4",
      title: "NPC 派工 -> 机器人现场 -> 观测台",
      detail: "确认只读现场证据、异常入口和回工作台链路可点，不暴露内部词。",
    },
  ];
  const chainCards = [
    { label: "任务", value: compactEvidenceId(currentTaskId, "等待焦点"), detail: chainFocused ? "当前任务对象" : "先从工作台带当前任务进入" },
    { label: "派单", value: compactEvidenceId(currentDispatchId, "等待派工"), detail: "当前执行链路" },
    { label: "消息", value: compactEvidenceId(currentSourceMessageId, "等待回流"), detail: "当前消息证据入口" },
    { label: "回执", value: compactEvidenceId(currentReceiptId, "等待回执"), detail: `${currentReceiptCount} 条回执` },
    { label: "证据", value: currentArtifactCount, detail: "当前证据索引数" },
    { label: "审计", value: currentAuditCount, detail: `${currentPendingCloseout} 条待收口 · ${currentExceptionCount} 条异常` },
  ];
  const recoveryCards = [
    closeoutWaitingMessages.length
      ? {
          state: "resync",
          label: "重新同步中",
          title: `${closeoutWaitingMessages.length} 条桌面最终结果待挂回`,
          detail: "优先补拉最终回执；如果桌面还在执行，平台保持处理中，不把它误判成失败。",
          href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "resync" }),
        }
      : {
          state: "connected",
          label: "已重新连接",
          title: "当前没有桌面最终同步滞后",
          detail: "桌面回执链路目前没有待收口项；继续从当前任务链看证据和下一步。",
          href: focusHref(projectId, "workbench", selfPath, sharedFocus),
        },
    desktopNotLiveSeats.length
      ? {
          state: "waiting",
          label: "等待恢复",
          title: `${desktopNotLiveSeats.length} 个 NPC 线程需核对桌面可见性`,
          detail: "这不等于不能派活；平台会保留原派单，负责人可回 NPC 工作台查看通道和回执。",
          href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" }),
        }
      : {
          state: "connected",
          label: "已重新连接",
          title: `可投递 ${deliverableSeats.length}/${evidenceSeats.length || 0}，桌面可见 ${desktopReadySeats.length}/${evidenceSeats.length || 0}`,
          detail: "可投递只看目标电脑是否持续心跳并绑定线程；桌面可见只是诊断信息，不等于派工能力。",
          href: focusHref(projectId, "workbench", selfPath, sharedFocus),
        },
    failedAutonomousMessages.length
      ? {
          state: "manual",
          label: "需要人工处理",
          title: `${failedAutonomousMessages.length} 条真实异常`,
          detail: "先看证据和上下文，再决定让 NPC 修复、打回或转人工。",
          href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" }),
        }
      : {
          state: "retry",
          label: "自动重试中",
          title: "没有新的真实异常",
          detail: "遇到焦点丢失或桌面短暂不可见时，平台会先重试并保留过程记录。",
          href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "receipt" }),
        },
    {
      state: "extended",
      label: "已延长等待",
      title: closeoutWaitingMessages.length ? "等待窗口已保留，继续观察桌面回流" : "当前没有需要延长等待的任务",
      detail: closeoutWaitingMessages.length
        ? "负责人可以继续等桌面线程完成，也可以回 NPC 工作台改为催办、重新同步或人工收口。"
        : "如果后续出现长时间待收口，平台会把延长等待作为可审计动作保留在对话里。",
      href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "extend_wait" }),
    },
  ];
  const deploymentReadinessRows = [
    {
      label: "API / 页面一致性",
      state: healthState.error ? "blocked" : "ready",
      value: healthState.error ? "需检查" : "已连接",
      detail: healthState.error ? "页面暂时不能读取服务健康状态，部署前先恢复 API。" : `API ${text(health.status, "可读")} · PID ${text(health.pid, "未知")}`,
    },
    {
      label: "执行电脑",
      state: onlineComputers > 0 ? "ready" : "watch",
      value: `${onlineComputers}/${computers.length}`,
      detail: onlineComputers > 0 ? "已有执行电脑在线，可继续验证任务派发与回执。" : "部署前建议至少准备一台执行电脑或 runner 节点。",
    },
    {
      label: "电脑可投递",
      state: deliverableSeats.length === evidenceSeats.length && evidenceSeats.length > 0 ? "ready" : "watch",
      value: `${deliverableSeats.length}/${evidenceSeats.length || 0}`,
      detail: `桌面可见 ${desktopReadySeats.length}/${evidenceSeats.length || 0}；只有目标电脑持续心跳并绑定线程才计入可投递。`,
    },
    {
      label: "当前待审",
      state: currentPendingReview.length > 0 || currentHardwarePending.length > 0 ? "blocked" : "ready",
      value: `${currentPendingReview.length}`,
      detail: currentHardwarePending.length > 0 ? "存在硬件、部署、运动或写入类强审，必须人工确认。" : "当前链路没有强审卡挡住部署检查。",
    },
    {
      label: "当前待收口",
      state: (chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length) > 0 ? "watch" : "ready",
      value: `${chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length}`,
      detail: "待收口不等于失败，先催办、延长等待或重新同步，再决定是否人工收口。",
    },
    {
      label: "历史积压",
      state: historicalBacklogCount > 0 ? "watch" : "ready",
      value: `${historicalBacklogCount}`,
      detail: historicalBacklogCount > 0 ? "历史积压已收进抽屉，不压住当前链路；部署前可分批清理。" : "当前没有历史积压需要先处理。",
    },
  ];

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <nav>
          <Link href={`/projects/${projectId}/cockpit`}>驾驶舱</Link>
          <Link href={`/projects/${projectId}/map?return_to=${encodeURIComponent(selfPath)}&from=observability`}>地图</Link>
          <Link href={focusHref(projectId, "workbench", selfPath, sharedFocus)}>NPC 工作台</Link>
          <Link href={focusHref(projectId, "datasets", selfPath, sharedFocus)}>数据工场</Link>
          <Link href={focusHref(projectId, "ai-lab", selfPath, sharedFocus)}>AI 实验室</Link>
          <Link href={focusHref(projectId, "robotics", selfPath, sharedFocus)}>机器人现场</Link>
          <Link href={`/projects/${projectId}/skill-forge?return_to=${encodeURIComponent(selfPath)}&from=observability`}>能力工坊</Link>
          {returnTo ? <Link href={returnTo}>{labelProjectReturnPath(returnTo)}</Link> : null}
        </nav>
        <div>
          <span>消息 {messages.length}</span>
          <span>用量 {usage.length}</span>
          <span>工位 {workstations.length}</span>
        </div>
      </header>

      <section className={styles.workbenchLayout} aria-label="观测台工作台">
        <aside className={styles.leftRail} aria-label="对象索引">
          <article className={styles.actorCard} data-kind="lead">
            <span>主角</span>
            <strong>项目负责人</strong>
            <p>最终验收、强审放行、异常打回都由人决定。</p>
          </article>
          <article className={styles.actorCard}>
            <span>负责 NPC</span>
            <strong>{currentSubjectName}</strong>
            <p>{hasFocusedSubject ? "负责整理观测证据、待收口和下一步建议。" : "从 NPC 工作台打开任务链后显示负责 NPC。"}</p>
          </article>
          <section className={styles.indexPanel}>
            <span>当前对象</span>
            {chainWorkbenchObjects.map((item) => (
              <article key={item.label}>
                <small>{item.label}</small>
                <strong>{item.value}</strong>
                <p>{item.detail}</p>
              </article>
            ))}
          </section>
          <section className={styles.indexPanel}>
            <span>链路成员</span>
            {chainSeatCoverage.slice(0, 6).map((item) => (
              <article key={item.seat} data-state={item.attached ? "ready" : "watch"}>
                <small>{item.attached ? "已挂回" : "待确认"}</small>
                <strong>{item.seat}</strong>
                <p>{item.detail}</p>
              </article>
            ))}
          </section>
        </aside>

        <section className={styles.centerPane} aria-label="观测工作区">
          <div className={styles.debugToolbar} aria-label="观测参数">
            <span>观测台</span>
            <small>过滤 {text(searchParams?.focus, "当前链路")}</small>
            <small>任务 {currentTaskId ? compactEvidenceId(currentTaskId) : "待选择"}</small>
            <small>待审 {currentPendingReview.length}</small>
            <small>待收口 {chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length}</small>
            <small>权限 只读 / 人审结论</small>
          </div>

          <section className={styles.mainSurface} aria-label="当前证据链">
            <div className={styles.surfaceHead}>
              <span>{currentBlocker.label}</span>
              <strong>派工验真 / 全链路入口</strong>
              <p>{currentBlocker.title}：{currentBlocker.detail}</p>
            </div>
            <div className={styles.actionGrid}>
              {primaryActions.map((action) => (
                <Link key={action.label} href={action.href}>
                  <span>{action.label}</span>
                  <strong>{action.title}</strong>
                  <p>{action.detail}</p>
                </Link>
              ))}
              <Link href={currentBlocker.href}>
                <span>当前动作</span>
                <strong>{currentBlocker.cta}</strong>
                <p>只跳到对应上下文，不在观测台替用户做最终结论。</p>
              </Link>
            </div>
            <div className={styles.chainGrid}>
              {(chainFocused ? chainCards : currentLineageCards).map((card) => (
                <article key={card.label}>
                  <span>{card.label}</span>
                  <strong>{card.value}</strong>
                  <p>{card.detail}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.evidenceSurface} id="recent-evidence" aria-label="最近证据">
            <div className={styles.surfaceHead}>
              <span>最近证据</span>
              <strong>{focusTitle}</strong>
              <p>{chainFocused ? `当前负责：${focusSeat}` : "未聚焦任务时，只显示最近协作信号和部署就绪判断。"}</p>
            </div>
            <div className={styles.evidenceGrid}>
              {recentEvidence.slice(0, 4).map((item) => (
                <article key={`${item.label}-${item.title}`}>
                  <span>{item.label}</span>
                  <strong>{item.title}</strong>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          </section>
        </section>

        <aside className={styles.rightRail} aria-label="操作抽屉">
          <section className={styles.toolLauncher} aria-label="观测功能">
            <span>功能</span>
            {observabilityTools.map((tool) => (
              <Link key={tool.label} href={tool.href} data-active={tool.active ? "1" : undefined}>
                <strong>{tool.label}</strong>
                <small>{tool.detail}</small>
              </Link>
            ))}
          </section>

          <details className={styles.drawerPanel} open>
            <summary><span>部署 / 稳定性</span><strong>{deploymentReadinessRows.filter((item) => item.state === "ready").length}/{deploymentReadinessRows.length}</strong></summary>
            <div className={styles.drawerGrid}>
              {deploymentReadinessRows.map((item) => (
                <article key={item.label} data-state={item.state}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          </details>

          <details className={styles.drawerPanel} open id="execution-computers">
            <summary><span>执行电脑能力 / 执行电脑调度</span><strong>{onlineComputers}/{computers.length}</strong></summary>
            <div className={styles.drawerGrid}>
              {computerCapabilityRows.map((node) => (
                <article key={node.key} data-state={node.state}>
                  <span>{node.status} · {node.osLabel}</span>
                  <strong>{node.name}</strong>
                  <p>{node.hostLabel ? `${node.hostLabel} · ${node.detail}` : node.detail}</p>
                </article>
              ))}
              {!computerCapabilityRows.length ? (
                <article data-state="watch">
                  <span>待登记</span>
                  <strong>还没有执行电脑</strong>
                  <p>先在项目入口接入执行电脑，再回来做派发、采集和回执验收。</p>
                </article>
              ) : null}
            </div>
          </details>

          <details className={styles.drawerPanel} open>
            <summary><span>异常与服务</span><strong>{currentPendingReview.length + currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber}</strong></summary>
            <div className={styles.actionList}>
              {closeoutActions.map(([label, href, detail]) => (
                <Link key={label} href={href}>
                  <span>{label}</span>
                  <strong>{detail}</strong>
                </Link>
              ))}
              <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" })}>
                <span>真异常</span>
                <strong>{failedAutonomousMessages.length}</strong>
              </Link>
            </div>
          </details>

          <details className={styles.drawerPanel}>
            <summary><span>NPC 协作</span><strong>{visiblePeerRows.length}</strong></summary>
            <div className={styles.drawerGrid}>
              {visiblePeerRows.slice(0, 6).map((row) => (
                <article key={row.id} data-state={row.state}>
                  <span>{row.sourceName}</span>
                  <strong>{row.targetName}</strong>
                  <p>{row.title} · {row.ack ? "已回执" : "等回执"} · {row.final ? "已 final" : "等 final"}</p>
                </article>
              ))}
              {!visiblePeerRows.length ? <article><span>空</span><strong>暂无免审协作</strong><p>NPC 创建结构化需求后才进入协作链路。</p></article> : null}
            </div>
          </details>

          <details className={styles.drawerPanel}>
            <summary><span>验收路径</span><strong>{acceptanceCards.length}</strong></summary>
            <div className={styles.drawerGrid}>
              {acceptanceCards.map((card) => (
                <article key={card.label}>
                  <span>{card.label}</span>
                  <strong>{card.title}</strong>
                  <p>{card.detail}</p>
                </article>
              ))}
            </div>
          </details>
        </aside>
      </section>

      <section className={styles.bottomLog} aria-label="底部事件日志">
        <details open>
          <summary>
            <span>最近协作信号</span>
            <strong>事件线</strong>
          </summary>
          <ol>
            {messages.slice(0, 8).map((item) => (
              <li key={text(item.id, messageTitle(item))}>
                <strong>{messageTitle(item)}</strong>
                <p>{collaborationStatusLabel(item)} · {collaborationEventTypeLabel(item.message_type)} · {text(item.at ?? item.created_at ?? item.updated_at, "")}</p>
              </li>
            ))}
            {!messages.length ? <li><strong>暂无协作消息</strong><p>去 NPC 工作台发起第一条派单后，这里会出现事件线。</p></li> : null}
          </ol>
        </details>
      </section>
    </main>
  );
}
