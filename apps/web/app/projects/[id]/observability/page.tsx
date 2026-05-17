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

function seatCanTakeTask(seat: AnyRecord, config: AnyRecord) {
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
  const health = `${text(seat.thread_health ?? seat.threadHealth, "")} ${text(config.health, "")} ${text(config.status, "")} ${text(config.delivery_label ?? config.deliveryLabel, "")} ${text(config.delivery_mode ?? config.deliveryMode, "")}`.toLowerCase();
  const desktopVisible = Boolean(config.desktop_visible ?? config.desktopVisible ?? seat.desktop_visible ?? seat.desktopVisible);
  const automationEnabled = Boolean(seat.automation_enabled ?? seat.automationEnabled ?? messageMetadata(seat).automation_enabled ?? messageMetadata(seat).automationEnabled);
  return Boolean(automationEnabled || desktopVisible || /可接单|ready|已登记|online|ok|watcher|就绪|线程可见|桌面线程可见/i.test(health));
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
  const onlineComputers = computers.filter((node) => /online|ready|active/.test(statusText(node.runner_effective_status ?? node.runner_status ?? node.status))).length;
  const computerCapabilityRows = computers.map((node, index) => {
    const capabilities = Array.from(new Set([
      ...asTextList(node.capabilities),
      ...asTextList(node.runner_capabilities ?? node.runnerCapabilities),
      ...asTextList(node.capability_labels ?? node.capabilityLabels),
    ])).slice(0, 5);
    const status = node.runner_effective_status ?? node.runner_status ?? node.status;
    const isOnline = /online|ready|active/.test(statusText(status));
    const osLabel = text(node.os ?? node.platform ?? node.computer_node_os ?? node.computerNodeOs, "系统待识别");
    const hostLabel = text(node.host ?? node.hostname ?? node.computer_node_host ?? node.computerNodeHost, "");
    return {
      key: text(node.id ?? node.runner_id ?? node.name, `computer-${index}`),
      name: text(node.label ?? node.name ?? node.runner_label ?? node.runner_id, `执行电脑 ${index + 1}`),
      status: computerStatusLabel(status),
      state: isOnline ? "ready" : /busy|running|in_progress/.test(statusText(status)) ? "watch" : "blocked",
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
    return seatCanTakeTask(seat, config);
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
                ? "派工、最小回执和可接单通道已经接上；历史积压已收进抽屉，不再压住当前判断。"
                : "派工、最小回执和可接单通道已经接上，负责人现在主要判断下一步去哪一层继续看证据。",
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
          title: `${desktopNotLiveSeats.length} 个 NPC 线程走后台同步或需恢复桌面可见性`,
          detail: "这不等于不能派活；平台会保留原派单，负责人可回 NPC 工作台查看通道和回执。",
          href: focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" }),
        }
      : {
          state: "connected",
          label: "已重新连接",
          title: `可接单 ${deliverableSeats.length}/${evidenceSeats.length || 0}，桌面可见 ${desktopReadySeats.length}/${evidenceSeats.length || 0}`,
          detail: "可接单表示平台能派活；桌面可见只是诊断信息，不等于派工能力。",
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
      label: "NPC 可接单",
      state: deliverableSeats.length === evidenceSeats.length && evidenceSeats.length > 0 ? "ready" : "watch",
      value: `${deliverableSeats.length}/${evidenceSeats.length || 0}`,
      detail: `桌面可见 ${desktopReadySeats.length}/${evidenceSeats.length || 0}；后台同步线程也可接单。`,
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

      <section className={styles.hero}>
        <div>
          <span>项目负责人 / QA 工作面 / 异常入口</span>
          <h1>{text(project.name, "项目")} 观测台</h1>
          <p>这里先帮人把当前卡点、最近证据、派工验真和下一步整理清楚。AI 负责辅助归拢证据链，是否继续、待审还是打回，仍由负责人确认。</p>
        </div>
        <div className={styles.evidenceConsole} data-ready={dispatchEvidenceReady ? "1" : "0"}>
          <div>
            <span>{currentBlocker.label}</span>
            <strong>{currentBlocker.title}</strong>
            <p>{currentBlocker.detail}</p>
          </div>
          <div className={styles.evidenceMetrics}>
            <span data-ok={hasCurrentSubject ? "1" : "0"}>当前主体 {currentSubjectName}</span>
            <span data-ok={hasFocusedSubject ? "1" : "0"}>{hasFocusedSubject ? `正式 NPC ${currentSubjectName}` : "正式 NPC 待选择"}</span>
            <span data-ok={deliverableSeats.length === evidenceSeats.length ? "1" : "0"}>可接单 {deliverableSeats.length}/{evidenceSeats.length}</span>
            <span data-ok={desktopReadySeats.length > 0 ? "1" : "0"}>桌面可见 {desktopReadySeats.length}/{evidenceSeats.length}</span>
            <span data-ok={completedHumanDispatches.length > 0 ? "1" : "0"}>用户派工 {completedHumanDispatches.length}</span>
            <span data-ok={completedPeerDispatches.length > 0 ? "1" : "0"}>NPC互派 {completedPeerDispatches.length}</span>
            <span data-ok={completedReceipts.length > 0 ? "1" : "0"}>回执 {completedReceipts.length}</span>
            <span data-warn={currentHardwarePending.length > 0 ? "1" : "0"}>当前强审 {currentHardwarePending.length}</span>
            <span data-warn={currentPendingReview.length > 0 ? "1" : "0"}>当前待审 {currentPendingReview.length}</span>
            <span data-warn={(chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length) > 0 ? "1" : "0"}>当前待收口 {chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length}</span>
            <span data-warn={historicalBacklogCount > 0 ? "1" : "0"}>历史积压 {historicalBacklogCount}</span>
          </div>
          <span className={styles.consoleStatus}>{currentBlocker.cta}</span>
        </div>
      </section>

      {chainFocused ? (
        <section className={styles.focusSection} aria-label="当前证据链">
          <div className={styles.sectionHead}>
            <span>当前证据链</span>
            <h2>{focusTitle}</h2>
          </div>
          <div className={styles.focusHead}>
            <div>
              <strong>{focusSeat}</strong>
              <p>只展示当前任务、派单、回执和证据状态，不把历史噪音抬成主角，也不把 AI 写成替负责人自动验收。</p>
            </div>
            <div className={styles.focusActions}>
              {chainCards.slice(0, 3).map((card) => (
                <span key={card.label}>{card.label}：{card.value}</span>
              ))}
            </div>
          </div>
          <div className={styles.chainGrid}>
            {chainCards.map((card) => (
              <article key={card.label}>
                <span>{card.label}</span>
                <strong>{card.value}</strong>
                <p>{card.detail}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className={styles.firstLookGrid} aria-label="异常入口">
        <article className={styles.actionPanel}>
          <div className={styles.sectionHead}>
            <span>下一步动作</span>
            <h2>第一屏只保留 3 个主动作。</h2>
          </div>
          <div className={styles.primaryActionList}>
            {primaryActions.map((action) => (
              <Link key={action.label} href={action.href}>
                <span>{action.label}</span>
                <strong>{action.title}</strong>
                <p>{action.detail}</p>
              </Link>
            ))}
          </div>
        </article>

        <article className={styles.recentEvidencePanel} id="recent-evidence" aria-label="最近协作证据">
          <div className={styles.sectionHead}>
            <span>最近协作证据</span>
            <h2>只留对负责人判断有帮助的最近三条。</h2>
          </div>
          <ol className={styles.recentEvidenceList}>
            {recentEvidence.slice(0, 3).map((item) => (
              <li key={`${item.label}-${item.title}`}>
                <span>{item.label}</span>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
              </li>
            ))}
          </ol>
        </article>
      </section>

      <section className={styles.closeoutPanel} aria-label="桌面过程与待收口入口">
        <div className={styles.sectionHead}>
          <span>桌面过程 / 待收口</span>
          <h2>AI 负责把动作入口排好，人决定是否继续催办、延长等待或打回。</h2>
        </div>
        <div className={styles.closeoutGrid}>
          {closeoutActions.map(([label, href, detail]) => (
            <Link key={label} href={href}>
              <span>{label}</span>
              <strong>{detail}</strong>
            </Link>
          ))}
        </div>
      </section>

      <section className={styles.routePanel} aria-label="全链路入口">
        <div className={styles.sectionHead}>
          <span>全链路入口</span>
          <h2>从目标走到专业工作面，再回 NPC 工作台，不需要翻说明书。</h2>
        </div>
        <div className={styles.routeGrid}>
          {routeCards.map((card) => (
            <Link key={card.label} href={card.href}>
              <span>{card.label}</span>
              <strong>{card.title}</strong>
              <p>{card.detail}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className={styles.flowStrip} aria-label="派工证据流">
        <div className={styles.flowLabel}>
          <strong>派工证据流</strong>
          <span>用户目标 → Boss → NPC → 回执 → 风险门</span>
        </div>
        {[
          ["目标", completedHumanDispatches.length > 0 ? "ok" : "idle", "用户目标"],
          ["Boss", completedPeerDispatches.length > 0 ? "ok" : "idle", "统筹拆分"],
          ["NPC", progressMessages.length > 0 || completedPeerDispatches.length > 0 ? "ok" : "idle", "过程可见"],
          ["回执", completedReceipts.length > 0 ? "ok" : "idle", "最小回执"],
          ["风险门", currentHardwarePending.length > 0 ? "warn" : "ok", currentHardwarePending.length > 0 ? "当前强审" : "当前风险正常"],
        ].map(([label, state, detail]) => (
          <article key={label} data-state={state}>
            <strong>{label}</strong>
            <span>{detail}</span>
          </article>
        ))}
      </section>

      <section className={styles.exceptionBand} aria-label="异常入口">
        <div>
          <span>异常入口</span>
          <strong>这里给负责人聚合入口，不替负责人做最终结论。</strong>
        </div>
        <Link href={focusHref(projectId, "workbench", selfPath, sharedFocus)}>
          当前待审 {currentPendingReview.length}
        </Link>
        <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" })}>
          当前待收口 {chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length}
        </Link>
        <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "resync" })}>
          重新同步
        </Link>
        <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "nudge" })}>
          催办
        </Link>
        <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "extend_wait" })}>
          延长等待
        </Link>
        <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" })}>
          真异常 {failedAutonomousMessages.length}
        </Link>
        <Link href={`/projects/${projectId}/observability?focus=peer-dispatch`}>
          免审链路 {peerDispatchRows.length}
        </Link>
      </section>

      <section className={styles.kpiGrid} aria-label="观测指标">
        {kpis.map(([label, value, detail]) => (
          <article key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <p>{detail}</p>
          </article>
        ))}
      </section>

      <section className={styles.operatorDeck} aria-label="观测台工作抽屉">
        <aside className={styles.lineageRail} aria-label="当前目标与链路对象">
          <div className={styles.actorStack}>
            <article className={styles.actorCard} data-kind="hero">
              <span>主角</span>
              <strong>项目负责人</strong>
              <p>最终验收、强审放行、异常打回都由人决定。</p>
            </article>
            <article className={styles.actorCard} data-kind="npc">
              <span>负责 NPC</span>
              <strong>{currentSubjectName}</strong>
              <p>{hasFocusedSubject ? "负责整理观测证据、待收口和下一步建议。" : "从 NPC 工作台打开一条任务证据链后显示负责 NPC。"}</p>
            </article>
            <div className={styles.npcIndexBox}>
              <span>NPC 索引</span>
              <Link href={`/projects/${projectId}?tab=npc-create&return_to=${encodeURIComponent(selfPath)}`}>添加 / 管理 NPC</Link>
              <Link href={focusHref(projectId, "workbench", selfPath, sharedFocus)}>回 NPC 工作台</Link>
            </div>
          </div>

          <div className={styles.sectionHead}>
            <span>当前目标 / 链路</span>
            <h2>先确认当前目标链是不是同一条目标。</h2>
          </div>
          <div className={styles.lineageStack}>
            {chainWorkbenchObjects.map((item) => (
              <article key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
        </aside>

        <div className={styles.deckWorkspace}>
          <div className={styles.debugToolbar} aria-label="观测参数">
            <span>观测参数</span>
            <small>过滤 {text(searchParams?.focus, "当前链路")}</small>
            <small>任务 {currentTaskId ? compactEvidenceId(currentTaskId) : "待选择"}</small>
            <small>待审 {currentPendingReview.length}</small>
            <small>待收口 {chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length}</small>
            <small>权限 只读 / 人审结论</small>
          </div>
          <div className={styles.sectionHead}>
            <span>工作内容 / 全链路入口</span>
            <h2>负责人先看当前链路，细节放进抽屉。</h2>
          </div>
          <div className={styles.operatorBoard}>
            <article>
              <span>当前阻塞</span>
              <strong>{currentBlocker.title}</strong>
              <p>{currentBlocker.detail}</p>
              <Link href={currentBlocker.href}>{currentBlocker.cta}</Link>
            </article>
            <article>
              <span>NPC 协作</span>
              <strong>{currentSubjectName}</strong>
              <p>{hasFocusedSubject ? `${completedPeerDispatches.length}/${visiblePeerRows.length || 0} 条协作链路。当前正式 NPC 先在这里露出，细节再进右侧抽屉。` : "从 NPC 工作台选择一条任务证据链后，再显示负责 NPC 和协作链路。"}</p>
              <Link href={focusHref(projectId, "workbench", selfPath, sharedFocus)}>看对话过程</Link>
            </article>
            <article>
              <span>执行电脑调度</span>
              <strong>{onlineComputers}/{computers.length} 在线</strong>
              <p>{computerCapabilityRows.length ? "先确认哪台电脑在线、有什么能力，再决定是否派发采集、构建或执行任务。" : "还没有执行电脑登记，部署前先接入一台执行电脑。"}</p>
              <Link href={`${selfPath}?focus=services#execution-computers`}>看执行能力</Link>
            </article>
            <article>
          <span>人工边界</span>
              <strong>{currentHardwarePending.length ? "当前有强审" : "当前只读正常"}</strong>
              <p>AI 只整理证据和下一步，硬件、发布、最终验收仍由负责人决定。</p>
              <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "review" })}>处理待审</Link>
            </article>
          </div>
        </div>

        <aside className={styles.drawerRail} aria-label="观测抽屉">
          <section className={styles.toolLauncher} aria-label="观测功能">
            <span>功能</span>
            {observabilityTools.map((tool) => (
              <Link key={tool.label} href={tool.href} data-active={tool.active ? "1" : undefined}>
                <strong>{tool.label}</strong>
                <small>{tool.detail}</small>
              </Link>
            ))}
          </section>

          <details open id="current-chain">
            <summary>
              <span>当前目标链</span>
              <strong>{currentLineageCards.length} 项</strong>
            </summary>
            <div className={styles.lineageCardGrid}>
              {currentLineageCards.map((card) => (
                <article key={card.label}>
                  <span>{card.label}</span>
                  <strong>{card.value}</strong>
                  <p>{card.detail}</p>
                </article>
              ))}
            </div>
          </details>

          <details open>
            <summary>
              <span>当前链路成员</span>
              <strong>{chainSeatCoverage.filter((item) => item.attached).length}/{chainSeatCoverage.length} 已挂回</strong>
            </summary>
            <div className={styles.chainSeatGrid}>
              {chainSeatCoverage.map((item) => (
                <article key={item.seat} data-ok={item.attached ? "1" : "0"}>
                  <span>链路成员</span>
                  <strong>{item.seat}</strong>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          </details>

          <details open id="receipt-chain">
            <summary>
              <span>证据抽屉</span>
              <strong>{rightRailEvidence.length} 条</strong>
            </summary>
            <div className={styles.referenceGrid}>
              {rightRailEvidence.map((card) => (
                <article key={card.label}>
                  <span>{card.label}</span>
                  <strong>{card.title}</strong>
                  <p>{card.detail}</p>
                </article>
              ))}
            </div>
          </details>

          <details open>
            <summary>
              <span>NPC 协作抽屉</span>
              <strong>{visiblePeerRows.length} 条</strong>
            </summary>
            <div className={styles.peerMatrix}>
              {visiblePeerRows.slice(0, 6).map((row) => (
                <article key={row.id} className={styles.peerMatrixRow} data-state={row.state}>
                  <div>
                    <span>目标 NPC</span>
                    <strong>{row.targetName}</strong>
                    <p>{row.title}</p>
                  </div>
                  <div>
                    <span>状态 / 当前链路</span>
                    <strong>{row.state === "pending_closeout" ? "待收口" : row.state}</strong>
                    <p>{row.state === "pending_closeout" ? (row.platformDefect ? "平台缺陷 · 桌面最终同步滞后" : "桌面待收口，可催办或重新同步") : row.sourceName}</p>
                    <p>起点记录 {lineageRecordLabel(row.sourceMessageId, "等待起点")} · 汇总记录 {lineageRecordLabel(row.rootMessageId, "等待汇总")} · 当前负责 {row.delegatedViaSeat || "等待"}</p>
                  </div>
                  <div>
                    <span>回执 / final</span>
                    <strong>{row.ack ? "已回执" : "等回执"} · {row.state === "pending_closeout" ? "待收口" : row.final ? "已 final" : "等 final"}</strong>
                    <p>{row.blockedReason || row.nextAction || "无阻塞"}</p>
                    {row.state === "pending_closeout" ? (
                      <div className={styles.closeoutActionLinks}>
                        <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "resync" })}>
                          重新同步
                        </Link>
                        <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "nudge" })}>
                          催办
                        </Link>
                        <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed", action: "extend_wait" })}>
                          延长等待
                        </Link>
                      </div>
                    ) : null}
                  </div>
                </article>
              ))}
              {!visiblePeerRows.length ? <p className={styles.peerMatrixEmpty}>当前还没有可展示的免审协作记录。</p> : null}
            </div>
          </details>

          <details>
            <summary>
              <span>异常与服务</span>
              <strong>{currentPendingReview.length + currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber} 项当前</strong>
            </summary>
            <div className={styles.recoveryGrid}>
              {recoveryCards.map((card) => (
                <Link key={`${card.label}-${card.title}`} href={card.href} data-state={card.state}>
                  <span>{card.label}</span>
                  <strong>{card.title}</strong>
                  <p>{card.detail}</p>
                </Link>
              ))}
            </div>
            <div className={styles.alertList}>
              <Link href={focusHref(projectId, "workbench", selfPath, sharedFocus)}>
                当前待审 {currentPendingReview.length}
              </Link>
              <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "failed" })}>
                当前待收口 {chainFocused ? currentCloseoutWaitingMessages.length + currentPendingCloseoutNumber : closeoutWaitingMessages.length}
              </Link>
              <Link href={`/projects/${projectId}/observability?focus=services&return_to=${encodeURIComponent(selfPath)}&from=observability`}>
                执行电脑在线 {onlineComputers}/{computers.length}
              </Link>
              <Link href={focusHref(projectId, "workbench", selfPath, { ...sharedFocus, filter: "git" })}>
                Git 回退 / 版本索引
              </Link>
            </div>
            <details className={styles.historyDrawer}>
              <summary>
                <span>历史积压</span>
                <strong>{historicalBacklogCount} 项</strong>
              </summary>
              <div className={styles.historyGrid}>
                <article>
                  <span>历史待审</span>
                  <strong>{historicalPendingReviewCount}</strong>
                  <p>保留给负责人复盘，不压住当前链路。</p>
                </article>
                <article>
                  <span>历史待收口</span>
                  <strong>{historicalCloseoutCount}</strong>
                  <p>需要时回 NPC 工作台逐条重新同步或手动收口。</p>
                </article>
                <article>
                  <span>历史强审</span>
                  <strong>{historicalHardwarePendingCount}</strong>
                  <p>涉及硬件、部署、运动或写入动作时仍必须人工确认。</p>
                </article>
              </div>
            </details>
            <div className={styles.serviceGrid}>
              <CurrentBrowserInstance />
              <article>
                <span>API 状态</span>
                <strong>{text(health.status, healthState.error ? "不可用" : "未知")}</strong>
                <p>{healthState.error ? `${healthState.error.status} · ${healthState.error.message}` : "当前页面服务端读取 /api/health 的结果。"}</p>
              </article>
              <article>
                <span>API 实例</span>
                <strong>{text(health.base_url ?? health.baseUrl, "未确认")}</strong>
                <p>PID {text(health.pid, "未知")} · version {text(health.version, "未知")}</p>
              </article>
            </div>
            <div className={styles.portList}>
              {localServices.map((item) => (
                <span key={`${text(item.host, "127.0.0.1")}:${text(item.port, "")}`} data-live={item.listening ? "1" : "0"}>
                  {text(item.host, "127.0.0.1")}:{text(item.port, "?")} {item.listening ? "监听中" : "未监听"}
                </span>
              ))}
              {!localServices.length ? <span data-live="0">API 未返回本机端口探测</span> : null}
            </div>
          </details>

          <details open>
            <summary>
              <span>部署 / 稳定性检查</span>
              <strong>{deploymentReadinessRows.filter((item) => item.state === "ready").length}/{deploymentReadinessRows.length} 通过</strong>
            </summary>
            <div className={styles.deploymentGrid}>
              {deploymentReadinessRows.map((item) => (
                <article key={item.label} data-state={item.state}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          </details>

          <details open id="execution-computers">
            <summary>
              <span>执行电脑能力</span>
              <strong>{onlineComputers}/{computers.length} 在线</strong>
            </summary>
            <div className={styles.executionGrid}>
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
            <div className={styles.coverageGrid}>
              {capabilityCoverageRows.map((item) => (
                <article key={item.label} data-state={item.state}>
                  <span>{item.label}</span>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          </details>

          <details id="acceptance-paths">
            <summary>
              <span>验收路径</span>
              <strong>{acceptanceCards.length} 条</strong>
            </summary>
            <div className={styles.referenceGrid}>
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
