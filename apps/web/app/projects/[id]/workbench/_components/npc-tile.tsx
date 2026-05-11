"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./npc-tile.module.css";
import { apiClientUrl } from "../../../../../lib/api-client-url";
import { launchNpcOneShotThreadProcessing, launchNpcRealThreadProcessing, prepareCodexThreadLaunchPack } from "../../../../actions";

export type WorkbenchSeat = {
  id: string;
  rowId?: string;
  configId?: string;
  name: string;
  workstationId: string;
  workstationName: string;
  computerNodeId: string;
  computerNodeName: string;
  providerId: string;
  providerLabel: string;
  threadId: string;
  threadKind: string;
  threadHealth: string;
  deliveryMode?: string;
  deliveryLabel?: string;
  deliveryWarning?: string;
  desktopVisible?: boolean;
  desktopProcessDetected?: boolean;
  desktopBridgeConnected?: boolean;
  desktopBridgeLabel?: string;
  desktopBridgeNote?: string;
  desktopThreadUrl?: string;
  executorCwd?: string;
  codexLaunchPrompt: string;
  metadata?: Record<string, unknown>;
  responsibility: string;
  skillLoadout: string[];
  inheritedSkills?: string[];
  workstationKnowledgePath?: string;
  knowledgeSummary: string;
  automationEnabled: boolean;
  model: string;
  permissionLevel: string;
  gitUserName: string;
  gitUserEmail: string;
  reviewPolicy: string;
  leadSeatId: string;
  isLead: boolean;
};

function seatIdentityList(seat: Pick<WorkbenchSeat, "id" | "rowId" | "configId" | "threadId" | "name">): string[] {
  return [seat.id, seat.rowId, seat.configId, seat.threadId, seat.name].filter((value): value is string => !!value);
}

type NpcTileProps = {
  projectId: string;
  apiBaseUrl: string;
  seat: WorkbenchSeat;
  teammates: WorkbenchSeat[];
  crossLeads?: WorkbenchSeat[];
  currentUserId: string;
  currentUserName: string;
  launchPackAutoOpen?: boolean;
  onOpenTeammate: (id: string) => void;
  sourcePath?: string;
  onClose: () => void;
};

type CollabMessage = {
  id: string;
  message_type: string;
  title: string | null;
  body: string;
  sender_type: string;
  sender_id: string | null;
  recipient_type: string | null;
  recipient_id: string | null;
  status: string;
  created_at?: string | null;
  dispatch_id?: string | null;
};

const NOISE_PREFIXES = [
  "watcher 启动",
  "watcher started",
  "mcp 启动",
  "mcp loaded",
  "mcp server",
  "heartbeat",
  "心跳",
  "[mcp]",
  "adapter started",
  "adapter ready",
  "adapter ack",
  "executor",
  "platform routing chatter",
];

const NOISE_INFIX = [
  "watcher 心跳",
  "polling inbox",
  "no new messages",
];

function stripPlatformChatter(body: string): string {
  // 隐藏给绑定 Codex/Claude 线程看的平台协议块；用户对话框只保留可读摘要/回执。
  const withoutLedger = body.replace(
    /AI_REQUIRED_REQUIREMENT_LEDGER_V1[\s\S]*?AI_REQUIRED_REQUIREMENT_LEDGER_END\s*/g,
    "",
  );
  // 隐藏后端注入的 [路由]/[NPC ...自主发起]/经工位长 X 转交 等元信息行（用户只想看正文）
  const lines = withoutLedger.split(/\r?\n/);
  const filtered = lines.filter((ln) => {
    const t = ln.trim();
    if (!t) return true;
    if (t.startsWith("[路由]") || t.startsWith("[Route]")) return false;
    if (t.startsWith("（NPC ") && t.includes("seat-mcp")) return false;
    if (t.startsWith("（本消息由 NPC")) return false;
    if (t.startsWith("[ack]") && t.length < 80) return false;
    return true;
  });
  return filtered.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function classifyMessage(msg: CollabMessage): { kind: "command" | "result" | "error" | "note"; summary: string; noisy: boolean } {
  const body = (msg.body || "").trim();
  const bodyLower = body.toLowerCase();
  const noisy = NOISE_PREFIXES.some((p) => bodyLower.startsWith(p.toLowerCase()))
    || NOISE_INFIX.some((p) => bodyLower.includes(p.toLowerCase()));
  const type = (msg.message_type || "").toLowerCase();
  let kind: "command" | "result" | "error" | "note" = "note";
  if (type.includes("command") || type === "requirement_dispatch" || msg.sender_type === "human") kind = "command";
  else if (type.includes("result") || type === "ai_reply") kind = "result";
  if ((msg.status || "").toLowerCase() === "failed" || bodyLower.includes("error") || bodyLower.includes("失败")) kind = "error";

  const title = (msg.title || "").trim();
  let summary = title;
  if (!summary) {
    const firstLine = stripPlatformChatter(body).split(/\r?\n/).map((s) => s.trim()).find(Boolean) || "";
    summary = firstLine.slice(0, 160);
  }
  if (!summary) summary = "(空消息)";
  return { kind, summary, noisy };
}

type RefinedMessage = {
  kind: "command" | "result" | "error" | "note";
  statusLabel: string;
  headline: string;
  detail: string;
  rawBody: string;
  cleanBody: string;
  noisy: boolean;
  showByDefault: boolean;
};

const IMPORTANT_WATCHER_TYPES = new Set([
  "runner_ack",
  "runner_result",
  "agent_ack",
  "agent_result",
  "requirement_progress_ack",
  "requirement_final_reply",
]);

function firstUsefulLine(body: string): string {
  return body.split(/\r?\n/).map((s) => s.trim()).find(Boolean) || "";
}

function summarizeCollabMessage(msg: CollabMessage): RefinedMessage {
  const classified = classifyMessage(msg);
  const type = (msg.message_type || "").toLowerCase();
  const status = (msg.status || "").toLowerCase();
  const rawBody = msg.body || "";
  const cleanBody = stripPlatformChatter(rawBody);
  const rawLower = rawBody.toLowerCase();
  const cleanFirst = firstUsefulLine(cleanBody);
  const title = (msg.title || "").trim();
  const isWatcher = (msg.sender_type || "").toLowerCase() === "runner"
    || (msg.sender_type || "").toLowerCase() === "watcher"
    || type.includes("watcher")
    || rawLower.startsWith("watcher");
  const statusLabel =
    status === "pending_review"
      ? "需人审"
      : status === "acked" || type.endsWith("_ack")
        ? "已接单"
        : status === "in_progress" || type.includes("progress")
          ? "处理中"
          : status === "completed" || status === "done" || type.includes("final") || type.includes("result")
            ? "已完成"
            : status === "failed" || status === "rejected" || rawLower.includes("失败") || rawLower.includes("error")
              ? "异常"
              : classified.kind === "command"
                ? "派单"
                : classified.kind === "result"
                  ? "回执"
                  : "协作";

  const headline =
    title
    || (statusLabel === "已接单" ? "目标线程已接单" : "")
    || (statusLabel === "已完成" ? "目标线程已回执" : "")
    || cleanFirst.slice(0, 96)
    || "(空消息)";

  let detail = cleanFirst && cleanFirst !== headline ? cleanFirst : "";
  if (!detail) {
    if (statusLabel === "派单") detail = "已写入协作消息池，等待绑定的执行线程处理。";
    else if (statusLabel === "已接单") detail = "已写入绑定线程；完整处理过程在 Codex / Claude Code 中继续。";
    else if (statusLabel === "处理中") detail = "绑定线程正在推进；平台只保留最小回执和最终结果。";
    else if (statusLabel === "需人审") detail = "需要人类成员查看正文后决定是否放行。";
    else if (statusLabel === "已完成") detail = "线程已返回最终结果；详细过程仍在绑定的 Codex / Claude Code 线程里。";
    else if (statusLabel === "异常") detail = "线程或桥接报告异常，展开可查看失败原文。";
    else detail = "协作事件已记录。";
  }
  if (detail.length > 120) detail = `${detail.slice(0, 120)}...`;

  const showByDefault = !isWatcher || IMPORTANT_WATCHER_TYPES.has(type) || ["failed", "rejected", "completed", "done"].includes(status);
  return {
    kind: classified.kind,
    statusLabel,
    headline,
    detail,
    rawBody,
    cleanBody,
    noisy: classified.noisy || (isWatcher && !showByDefault),
    showByDefault,
  };
}

type RoleTrack = "human" | "self" | "peer" | "external" | "watcher" | "system";

function classifyRole(
  msg: CollabMessage,
  selfId: string,
  peerIds: Set<string>,
  externalAgentIds: Set<string>,
): { role: RoleTrack; label: string } {
  const senderType = (msg.sender_type || "").toLowerCase();
  const senderId = msg.sender_id || "";
  const recipientId = msg.recipient_id || "";
  const body = (msg.body || "").toLowerCase();
  const type = (msg.message_type || "").toLowerCase();

  if (senderType === "human") return { role: "human", label: "用户" };
  if (senderType === "runner" || senderType === "watcher" || type.includes("watcher") || type.includes("heartbeat") || body.startsWith("watcher")) {
    return { role: "watcher", label: "线程 Watcher" };
  }
  if (senderType === "agent" && senderId === selfId) return { role: "self", label: "本 NPC" };
  if (senderType === "agent" && peerIds.has(senderId)) return { role: "peer", label: "同工位 NPC" };
  if (senderType === "agent" && externalAgentIds.has(senderId)) return { role: "external", label: "跨工位 NPC" };
  if (senderType === "agent") return { role: "external", label: "其他 Agent" };
  if (recipientId === selfId && senderType === "system") return { role: "system", label: "系统" };
  return { role: "system", label: senderType || "系统" };
}

function formatTime(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function NpcTile({ projectId, apiBaseUrl, seat, teammates, crossLeads = [], currentUserId, currentUserName, launchPackAutoOpen = false, onOpenTeammate, sourcePath, onClose }: NpcTileProps) {
  const seatApiId = seat.rowId || seat.id;
  const seatIdentityKey = [seat.id, seat.rowId, seat.configId, seat.threadId, seat.name].filter(Boolean).join("|");
  const seatIdentityIds = useMemo(
    () => new Set(seatIdentityList(seat)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [seatIdentityKey],
  );
  const [messages, setMessages] = useState<CollabMessage[] | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [hideNoisy, setHideNoisy] = useState(true);
  const [showFullHistory, setShowFullHistory] = useState(false);
  const [limit, setLimit] = useState(50);
  const [fetching, setFetching] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendNote, setSendNote] = useState<string | null>(null);
  const [dispatchingPeerId, setDispatchingPeerId] = useState<string | null>(null);
  const [headerCollapsed, setHeaderCollapsed] = useState(true);
  const [editingIdentity, setEditingIdentity] = useState(false);
  const [gitName, setGitName] = useState(seat.gitUserName);
  const [gitEmail, setGitEmail] = useState(seat.gitUserEmail);
  const [reviewPolicy, setReviewPolicy] = useState(seat.reviewPolicy || "inherit");
  const [pairReviewPolicies, setPairReviewPolicies] = useState<Record<string, string>>({});
  const [savingIdentity, setSavingIdentity] = useState(false);
  const [identityNote, setIdentityNote] = useState<string | null>(null);
  const [editingThread, setEditingThread] = useState(false);
  const [threadIdDraft, setThreadIdDraft] = useState(seat.threadId);
  const [threadKindDraft, setThreadKindDraft] = useState(seat.threadKind || seat.providerLabel || seat.providerId || "thread");
  const [threadHealthDraft, setThreadHealthDraft] = useState(seat.threadHealth || "待接入");
  const [savingThread, setSavingThread] = useState(false);
  const [threadNote, setThreadNote] = useState<string | null>(null);
  const [launchPackOpen, setLaunchPackOpen] = useState(launchPackAutoOpen);
  const [automationEnabled, setAutomationEnabled] = useState(seat.automationEnabled);
  const [automationBusy, setAutomationBusy] = useState(false);
  const [automationNote, setAutomationNote] = useState<string | null>(null);
  const tileRef = useRef<HTMLElement | null>(null);
  const streamRef = useRef<HTMLDivElement | null>(null);
  const draftRef = useRef<HTMLTextAreaElement | null>(null);
  const autoScrollRef = useRef(true);
  const sendInFlightRef = useRef(false);

  type SeatQueueItem = {
    id: string;
    title: string;
    status: string;
    priority?: string;
    module?: string | null;
    from_agent?: string | null;
    to_agent?: string | null;
    target_seat_id?: string | null;
    trigger_kind?: string;
    context_summary?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
    branch?: string | null;
    due_at?: string | null;
  };
  type SeatQueues = {
    requirement_inbox: { items: SeatQueueItem[]; count: number };
    task_todo: { items: SeatQueueItem[]; count: number };
  };
  type Receipt = {
    id: string;
    receipt_kind: "ack" | "progress" | "done" | "reject";
    parent_requirement_id: string;
    sender_seat_id: string | null;
    recipient_seat_id: string | null;
    cross_workstation: boolean;
    title: string | null;
    body: string;
    created_at: string | null;
  };
  const [seatQueues, setSeatQueues] = useState<SeatQueues | null>(null);
  const [receipts, setReceipts] = useState<Receipt[] | null>(null);
  const [queueTab, setQueueTab] = useState<"inbox" | "todo" | "dispatch">("inbox");
  const [receiptDirection, setReceiptDirection] = useState<"incoming" | "outgoing">("incoming");
  const [queueBusyId, setQueueBusyId] = useState<string | null>(null);
  const [queueNote, setQueueNote] = useState<string | null>(null);

  type Occupancy = {
    user_id: string;
    user_name?: string | null;
    acquired_at?: string | null;
    heartbeat_at?: string | null;
    preempted?: boolean;
    preempted_user?: string | null;
  };
  const [occupancy, setOccupancy] = useState<Occupancy | null>(null);
  const [occupancyError, setOccupancyError] = useState<string | null>(null);
  const [occupancyBusy, setOccupancyBusy] = useState(false);
  const occupancyHeldByMe = !!occupancy && occupancy.user_id === currentUserId;
  const occupancyHeldByOther = !!occupancy && !occupancyHeldByMe;

  const occupyUrl = apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/thread-workstations/${encodeURIComponent(seatApiId)}`);

  const refreshOccupancy = useCallback(async () => {
    try {
      const res = await fetch(`${occupyUrl}/occupancy`, { credentials: "include" });
      const json = await res.json().catch(() => ({}));
      if (res.ok) {
        const occ = (json?.data?.occupancy ?? null) as Occupancy | null;
        setOccupancy(occ);
        setOccupancyError(null);
      }
    } catch (e) {
      setOccupancyError(e instanceof Error ? e.message : "查询占用失败");
    }
  }, [occupyUrl]);

  const claimOccupancy = useCallback(
    async (force: boolean) => {
      setOccupancyBusy(true);
      setOccupancyError(null);
      try {
        const res = await fetch(`${occupyUrl}/occupy`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ force, user_name: currentUserName }),
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
          throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        }
        const data = json?.data ?? {};
        if (data.ok === false) {
          setOccupancy((data.occupied_by ?? null) as Occupancy | null);
          setOccupancyError(`已被 ${data.occupied_by?.user_name || "他人"} 占用，可点"申请抢占"`);
        } else {
          setOccupancy((data.occupancy ?? null) as Occupancy | null);
          setOccupancyError(null);
        }
      } catch (e) {
        setOccupancyError(e instanceof Error ? e.message : "占用失败");
      } finally {
        setOccupancyBusy(false);
      }
    },
    [occupyUrl, currentUserName],
  );

  const releaseOccupancy = useCallback(
    async (silent: boolean = false) => {
      if (!silent) setOccupancyBusy(true);
      try {
        const res = await fetch(`${occupyUrl}/release`, {
          method: "POST",
          credentials: "include",
        });
        const json = await res.json().catch(() => ({}));
        if (res.ok && json?.data?.ok !== false) {
          setOccupancy(null);
          setOccupancyError(null);
        }
      } catch {
        // best-effort
      } finally {
        if (!silent) setOccupancyBusy(false);
      }
    },
    [occupyUrl],
  );

  // open-tile auto-occupy + close auto-release + 30s heartbeat
  useEffect(() => {
    let cancelled = false;
    (async () => {
      await refreshOccupancy();
      if (cancelled) return;
      // soft-claim: only if no one holds it
      try {
        const res = await fetch(`${occupyUrl}/occupy`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ force: false, user_name: currentUserName }),
        });
        const json = await res.json().catch(() => ({}));
        if (!cancelled && res.ok) {
          const data = json?.data ?? {};
          if (data.ok === false) {
            setOccupancy((data.occupied_by ?? null) as Occupancy | null);
          } else {
            setOccupancy((data.occupancy ?? null) as Occupancy | null);
          }
        }
      } catch {}
    })();
    const heartbeat = setInterval(() => {
      // re-claim only if I'm already the holder (refreshes heartbeat_at)
      setOccupancy((curr) => {
        if (curr && curr.user_id === currentUserId) {
          fetch(`${occupyUrl}/occupy`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ force: false, user_name: currentUserName }),
          }).catch(() => {});
        }
        return curr;
      });
      refreshOccupancy();
    }, 30000);
    return () => {
      cancelled = true;
      clearInterval(heartbeat);
      // best-effort release on close (only if I held it)
      releaseOccupancy(true);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seatApiId]);

  async function saveIdentity() {
    setSavingIdentity(true);
    setIdentityNote(null);
    try {
      const nextMetadata = {
        ...(seat.metadata ?? {}),
        git_user_name: gitName.trim() || seat.name,
        git_user_email: gitEmail.trim() || `bot+${seatApiId}@noreply.invalid`,
        review_policy: reviewPolicy,
      };
      const res = await fetch(
        apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/thread-workstations/${encodeURIComponent(seatApiId)}`),
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ metadata: nextMetadata }),
        },
      );
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setIdentityNote("已保存 ✓（刷新页面可见同步）");
      setEditingIdentity(false);
    } catch (e) {
      setIdentityNote(`保存失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setSavingIdentity(false);
      setTimeout(() => setIdentityNote(null), 4000);
    }
  }

  async function saveThreadBinding() {
    setSavingThread(true);
    setThreadNote(null);
    const nextThreadId = threadIdDraft.trim();
    const nextKind = threadKindDraft.trim() || seat.providerLabel || seat.providerId || "thread";
    const nextHealth = threadHealthDraft.trim() || "已登记";
    try {
      const nextMetadata = {
        ...(seat.metadata ?? {}),
        git_user_name: gitName.trim() || seat.name,
        git_user_email: gitEmail.trim() || `bot+${seatApiId}@noreply.invalid`,
        review_policy: reviewPolicy,
        target_thread_id: nextThreadId,
        source_thread_id: nextThreadId,
        bound_thread_id: nextThreadId,
        thread_kind: nextKind,
        thread_health: nextHealth,
        bridge_health_label: nextHealth,
        source: "workbench_thread_binding",
      };
      const res = await fetch(
        apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/thread-workstations/${encodeURIComponent(seatApiId)}`),
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ metadata: nextMetadata }),
        },
      );
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setThreadNote("线程绑定已保存 ✓（刷新后同步到瓷砖头部）");
      setEditingThread(false);
    } catch (e) {
      setThreadNote(`保存失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setSavingThread(false);
      setTimeout(() => setThreadNote(null), 5000);
    }
  }

  async function toggleAutomation(nextEnabled: boolean) {
    setAutomationBusy(true);
    setAutomationNote(null);
    try {
      const nextHealth = nextEnabled
        ? (threadHealthDraft.trim() || seat.threadHealth || "automation requested")
        : "automation paused";
      const nextMetadata = {
        ...(seat.metadata ?? {}),
        automation_enabled: nextEnabled,
        automation_mode: nextEnabled ? "thread_watcher" : "manual",
        automation_provider: seat.providerId || seat.providerLabel || threadKindDraft || "thread",
        automation_thread_id: threadIdDraft.trim() || seat.threadId || "",
        thread_health: nextHealth,
        bridge_health_label: nextHealth,
        automation_updated_at: new Date().toISOString(),
        source: "workbench_automation_toggle",
      };
      const res = await fetch(
        apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/thread-workstations/${encodeURIComponent(seatApiId)}`),
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ automation_enabled: nextEnabled, metadata: nextMetadata }),
        },
      );
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setAutomationEnabled(nextEnabled);
      setThreadHealthDraft(nextHealth);
      setAutomationNote(nextEnabled ? "自动化已请求开启 ✓" : "自动化已暂停 ✓");
    } catch (e) {
      setAutomationNote(`切换失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setAutomationBusy(false);
      setTimeout(() => setAutomationNote(null), 5000);
    }
  }

  const watcherCommand = useMemo(() => {
    const provider = (seat.providerId || seat.providerLabel || "").toLowerCase().includes("claude") ? "claude" : "codex";
    return [
      ".\\scripts\\start-thread-watcher.ps1",
      "-ProjectId",
      projectId,
      "-WorkstationId",
      `'${seatApiId}'`,
      "-Provider",
      provider,
      "-PersistentWindow",
    ].join(" ");
  }, [projectId, seatApiId, seat.providerId, seat.providerLabel]);

  const prepareLaunchPackAction = prepareCodexThreadLaunchPack.bind(null, projectId, seatApiId);
  const launchRealThreadAction = launchNpcRealThreadProcessing.bind(null, projectId, seatApiId);
  const governanceReturnTo = sourcePath || `/projects/${projectId}/workbench`;
  const governanceSource = governanceReturnTo.includes("/company") ? "company" : "workbench";
  const governanceHref = useCallback(
    (panel: string, action?: string) => {
      const params = new URLSearchParams({ panel, return_to: governanceReturnTo, from: governanceSource });
      if (action) params.set("action", action);
      return `/projects/${projectId}/2d-upgrade?${params.toString()}`;
    },
    [governanceReturnTo, governanceSource, projectId],
  );

  function renderRealThreadLauncher(message: CollabMessage, variant: "compact" | "inline" = "inline", isPrimary = true) {
    const status = (message.status || "").toLowerCase();
    const type = (message.message_type || "").toLowerCase();
    const isExecutableCommand = ["agent_command", "requirement_dispatch", "comment_message"].includes(type);
    if (!isExecutableCommand) return null;
    const runnable = ["queued", "pending", "acked", "in_progress"].includes(status);
    if (!runnable) return null;
    return (
      <form action={launchRealThreadAction} className={variant === "compact" ? styles.realThreadMiniForm : styles.realThreadForm}>
        <input type="hidden" name="return_to" value={governanceReturnTo} />
        <input type="hidden" name="message_id" value={message.id} />
        <button
          type="submit"
          className={styles.realThreadBtn}
          data-secondary={!isPrimary ? "1" : undefined}
          title="拉起本机 adapter，让绑定的 Codex / Claude Code 线程处理这条派单并回写结果"
        >
          {isPrimary ? "启动真实处理" : "启动"}
        </button>
        {variant === "inline" ? (
          <small className={styles.realThreadHint}>
            平台只等待最小回执和最终结果；过程在绑定线程里看。
          </small>
        ) : null}
      </form>
    );
  }

  const load = useCallback(
    async (size: number) => {
      setFetching(true);
      setFetchError(null);
      try {
        const base = apiClientUrl(`/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&limit=${size}`);
        const identityIds = Array.from(seatIdentityIds);
        const incomingUrls = identityIds.map(
          (id) => `${base}&recipient_type=thread_workstation&recipient_id=${encodeURIComponent(id)}`,
        );
        const outgoingUrls = identityIds.map((id) => `${base}&sender_id=${encodeURIComponent(id)}`);
        const scopedProject = encodeURIComponent(projectId);
        const queuesUrl = apiClientUrl(`/api/seats/${encodeURIComponent(seatApiId)}/queues?project_id=${scopedProject}&limit=30`);
        const receiptsUrl = apiClientUrl(`/api/receipts/by-seat/${encodeURIComponent(seatApiId)}?project_id=${scopedProject}&direction=${receiptDirection}&limit=30`);
        const [incomingResponses, outgoingResponses, r3, r4] = await Promise.all([
          Promise.all(incomingUrls.map((url) => fetch(url, { credentials: "include" }))),
          Promise.all(outgoingUrls.map((url) => fetch(url, { credentials: "include" }))),
          fetch(queuesUrl, { credentials: "include" }).catch(() => null),
          fetch(receiptsUrl, { credentials: "include" }).catch(() => null),
        ]);
        const firstIncomingError = incomingResponses.find((res) => !res.ok);
        if (firstIncomingError) {
          const json = await firstIncomingError.json().catch(() => ({}));
          const msg = json?.error?.message ?? json?.message ?? `HTTP ${firstIncomingError.status}`;
          throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        }
        const incomingJson = await Promise.all(incomingResponses.map((res) => res.json().catch(() => ({}))));
        const outgoingJson = await Promise.all(outgoingResponses.map((res) => res.ok ? res.json().catch(() => ({})) : Promise.resolve({})));
        const incoming = incomingJson.flatMap((json) => (json?.data ?? []) as CollabMessage[]);
        const outgoing = outgoingJson.flatMap((json) => (json?.data ?? []) as CollabMessage[]);
        const seen = new Set<string>();
        const merged: CollabMessage[] = [];
        for (const m of [...incoming, ...outgoing]) {
          if (!m.id || seen.has(m.id)) continue;
          seen.add(m.id);
          merged.push(m);
        }
        merged.sort((a, b) => {
          const ta = a.created_at ? Date.parse(a.created_at) : 0;
          const tb = b.created_at ? Date.parse(b.created_at) : 0;
          return tb - ta;
        });
        setMessages(merged);
        if (r3 && r3.ok) {
          const j3 = await r3.json().catch(() => ({}));
          const data = (j3?.data ?? null) as SeatQueues | null;
          if (data) setSeatQueues(data);
        }
        if (r4 && r4.ok) {
          const j4 = await r4.json().catch(() => ({}));
          const data = (j4?.data ?? []) as Receipt[];
          setReceipts(Array.isArray(data) ? data : []);
        }
      } catch (e) {
        setFetchError(e instanceof Error ? e.message : "加载失败");
      } finally {
        setFetching(false);
      }
    },
    [apiBaseUrl, projectId, seatApiId, seatIdentityIds, receiptDirection],
  );

  const refreshAfterOneShot = useCallback(() => {
    [2500, 9000, 30000, 60000].forEach((delay) => {
      window.setTimeout(() => {
        autoScrollRef.current = true;
        void load(limit);
      }, delay);
    });
  }, [load, limit]);

  useEffect(() => {
    load(limit);
  }, [load, limit]);

  useEffect(() => {
    const t = setInterval(() => load(limit), 15000);
    return () => clearInterval(t);
  }, [load, limit]);

  const peerIds = useMemo(
    () => new Set(teammates.flatMap((t) => seatIdentityList(t))),
    [teammates],
  );
  const peerByIdentity = useMemo(() => {
    const map = new Map<string, WorkbenchSeat>();
    for (const peer of teammates) {
      for (const value of seatIdentityList(peer)) {
        if (value) map.set(value, peer);
      }
    }
    return map;
  }, [teammates]);
  const externalAgentIds = useMemo(() => {
    const ids = new Set<string>();
    for (const m of messages || []) {
      if ((m.sender_type || "").toLowerCase() === "agent" && m.sender_id && !seatIdentityIds.has(m.sender_id) && !peerIds.has(m.sender_id)) {
        ids.add(m.sender_id);
      }
    }
    return ids;
  }, [messages, peerIds, seatIdentityIds]);

  const visible = useMemo(() => {
    const list = (messages || []).slice().reverse();
    const readable = hideNoisy
      ? list.filter((m) => {
      if ((m.status || "").toLowerCase() === "pending_review") return true;
      const refined = summarizeCollabMessage(m);
      return refined.showByDefault && !refined.noisy;
    })
      : list;
    if (showFullHistory) return readable;
    const important = readable.filter((m) => {
      const status = (m.status || "").toLowerCase();
      const type = (m.message_type || "").toLowerCase();
      const title = (m.title || "").toLowerCase();
      return (
        title.includes("git 回退")
        || ["failed", "rejected", "completed", "done", "in_progress"].includes(status)
        || type.includes("result")
        || type.includes("ack")
      );
    });
    const recent = readable.slice(-8);
    const seen = new Set<string>();
    return [...important, ...recent].filter((m) => {
      if (!m.id || seen.has(m.id)) return false;
      seen.add(m.id);
      return true;
    });
  }, [messages, hideNoisy, showFullHistory]);

  const pendingReviews = useMemo(() => {
    return (messages || [])
      .filter((m) => (m.status || "").toLowerCase() === "pending_review")
      .slice()
      .sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")));
  }, [messages]);

  // 我的任务队列：收件给本 NPC、still open、按 created_at 正序（FIFO）
  const myQueue = useMemo(() => {
    const arr = (messages || []).filter((m) => {
      if (!seatIdentityIds.has(m.recipient_id || "")) return false;
      const t = (m.message_type || "").toLowerCase();
      if (!["agent_command", "requirement_dispatch", "comment_message"].includes(t)) return false;
      const s = (m.status || "").toLowerCase();
      return ["queued", "pending", "acked", "in_progress"].includes(s);
    });
    const priority = (status: string) => {
      const value = status.toLowerCase();
      if (value === "in_progress" || value === "acked") return 0;
      if (value === "queued" || value === "pending") return 1;
      return 2;
    };
    return arr.slice().sort((a, b) => {
      const pa = priority(a.status || "");
      const pb = priority(b.status || "");
      if (pa !== pb) return pa - pb;
      return String(b.created_at || "").localeCompare(String(a.created_at || ""));
    });
  }, [messages, seatIdentityIds]);

  type CollaborationEvent = {
    id: string;
    tone: "human" | "peer" | "external" | "thread" | "review" | "receipt";
    label: string;
    title: string;
    meta: string;
    status?: string;
    createdAt?: string | null;
  };

  const collaborationEvents = useMemo(() => {
    const events: CollaborationEvent[] = [];
    const seen = new Set<string>();
    const push = (event: CollaborationEvent) => {
      if (seen.has(event.id)) return;
      seen.add(event.id);
      events.push(event);
    };

    for (const m of myQueue) {
      const senderType = (m.sender_type || "").toLowerCase();
      const isPeer = senderType === "agent" && peerIds.has(m.sender_id || "");
      const isExternal = senderType === "agent" && !!m.sender_id && !peerIds.has(m.sender_id) && !seatIdentityIds.has(m.sender_id);
      const from = isPeer
        ? `同工位 ${peerByIdentity.get(m.sender_id || "")?.name || m.sender_id}`
        : isExternal
          ? `跨工位 ${m.sender_id}`
          : senderType === "human"
            ? "人类成员"
            : senderType || "系统";
      push({
        id: `queue:${m.id}`,
        tone: isPeer ? "peer" : isExternal ? "external" : "human",
        label: "派单",
        title: m.title || stripPlatformChatter(m.body || "").slice(0, 90) || "(无标题)",
        meta: `${from} -> ${seat.name}`,
        status: m.status,
        createdAt: m.created_at,
      });
    }

    for (const r of receipts || []) {
      const kindLabel = ({ ack: "接单", progress: "进度", done: "完成", reject: "拒绝" } as const)[r.receipt_kind];
      push({
        id: `receipt:${r.id}`,
        tone: "receipt",
        label: kindLabel,
        title: r.title || r.body.slice(0, 90) || "(无标题回执)",
        meta: `${r.cross_workstation ? "跨工位" : "同工位"}回执 ${receiptDirection === "incoming" ? "-> 本 NPC" : "从本 NPC ->"}`,
        status: r.receipt_kind,
        createdAt: r.created_at,
      });
    }

    for (const m of messages || []) {
      const type = (m.message_type || "").toLowerCase();
      if (!["runner_ack", "runner_result", "agent_ack", "agent_result", "requirement_progress_ack", "requirement_final_reply"].includes(type)) continue;
      const { noisy } = classifyMessage(m);
      if (noisy) continue;
      const label =
        type.includes("final") || type.includes("result")
          ? "线程结果"
          : type.includes("ack")
            ? "线程接单"
            : "线程事件";
      push({
        id: `thread:${m.id}`,
        tone: "thread",
        label,
        title: m.title || stripPlatformChatter(m.body || "").slice(0, 90) || "(线程事件)",
        meta: `${seat.providerLabel || seat.providerId || "provider"} / ${seat.computerNodeName || seat.computerNodeId || "未绑定电脑"}`,
        status: m.status,
        createdAt: m.created_at,
      });
    }

    return events
      .sort((a, b) => {
        const ta = a.createdAt ? Date.parse(a.createdAt) : 0;
        const tb = b.createdAt ? Date.parse(b.createdAt) : 0;
        return tb - ta;
      })
      .slice(0, 8);
  }, [messages, myQueue, peerByIdentity, peerIds, receiptDirection, receipts, seat.computerNodeId, seat.computerNodeName, seatIdentityIds, seat.name, seat.providerId, seat.providerLabel]);

  const [reviewBusyId, setReviewBusyId] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState<string | null>(null);

  const refreshPairReviewPolicies = useCallback(async () => {
    try {
      const res = await fetch(apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/config`), {
        credentials: "include",
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) return;
      const cfg = json?.data?.collaboration_config || json?.data || {};
      const reviewPolicyCfg = cfg?.review_policy || {};
      const rules = reviewPolicyCfg?.npc_pair_rules || {};
      const next: Record<string, string> = {};
      if (rules && typeof rules === "object") {
        Object.entries(rules).forEach(([key, value]) => {
          const policy = typeof value === "object" && value ? String((value as { policy?: unknown }).policy || "") : "";
          if (policy) next[key] = policy;
        });
      }
      setPairReviewPolicies(next);
    } catch {
      // 关系免审只是辅助状态，读取失败不阻断工作台主流程。
    }
  }, [projectId]);

  useEffect(() => {
    refreshPairReviewPolicies();
  }, [refreshPairReviewPolicies]);

  async function setPairReviewPolicy(upstreamId: string, downstreamId: string, policy: "skip" | "force" | "inherit", note?: string) {
    if (!upstreamId || !downstreamId) {
      throw new Error("这条关系缺少 NPC 身份，无法设置免审");
    }
    const res = await fetch(apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/review-policy/npc-pairs`), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        upstream_seat_id: upstreamId,
        downstream_seat_id: downstreamId,
        policy,
        reason: note,
      }),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    setPairReviewPolicies((curr) => {
      const next = { ...curr };
      const key = `${upstreamId}->${downstreamId}`;
      if (policy === "inherit") delete next[key];
      else next[key] = policy;
      return next;
    });
    return json?.data;
  }

  async function reviewMessage(id: string, action: "approve" | "reject", rememberPolicy?: "skip") {
    setReviewBusyId(id);
    setReviewNote(null);
    try {
      const res = await fetch(apiClientUrl(`/api/collaboration/messages/${encodeURIComponent(id)}/review/${action}`), {
        method: "POST",
        headers: rememberPolicy ? { "Content-Type": "application/json" } : undefined,
        credentials: "include",
        body: rememberPolicy ? JSON.stringify({ remember_pair_policy: rememberPolicy, reason: "用户在工作台选择通过并下次免审" }) : undefined,
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      if (json?.data?.review_pair_policy) {
        const pair = json.data.review_pair_policy;
        setPairReviewPolicies((curr) => ({ ...curr, [`${pair.upstream_seat_id}->${pair.downstream_seat_id}`]: pair.policy || "skip" }));
      }
      setReviewNote(action === "approve" ? (rememberPolicy ? "✓ 已通过，并记住这对 NPC 下次免审" : "✓ 已通过") : "✓ 已打回");
      await load(limit);
      window.dispatchEvent(new CustomEvent("workbench:collab-updated", { detail: { projectId, messageId: id, action } }));
    } catch (e) {
      setReviewNote(`失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setReviewBusyId(null);
      setTimeout(() => setReviewNote(null), 4000);
    }
  }

  useEffect(() => {
    if (!streamRef.current || !autoScrollRef.current) return;
    streamRef.current.scrollTop = streamRef.current.scrollHeight;
  }, [visible.length]);

  function onStreamScroll() {
    const el = streamRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    autoScrollRef.current = atBottom;
  }

  function toggleExpand(id: string) {
    setExpandedIds((curr) => {
      const next = new Set(curr);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function buildDispatchBody(rawBody: string, targetName: string) {
    const sameWorkstationDirectory = teammates.length
      ? teammates.map((peer) => `${peer.isLead ? "工位长 " : ""}${peer.name}（${peer.responsibility || peer.providerLabel || "待补职责"}）`).join("；")
      : "暂无同工位伙伴";
    const crossLeadDirectory = crossLeads.length
      ? crossLeads.map((lead) => `${lead.name}（${lead.workstationName || lead.computerNodeName || "其他工位"} 工位长）`).join("；")
      : "暂无其他工位长";
    return [
      rawBody,
      "",
      "----",
      "平台协作上下文（请按此执行，不要依赖本机绝对路径）:",
      `- 发起 NPC: ${seat.name}`,
      `- 目标 NPC: ${targetName}`,
      `- 当前逻辑工位: ${seat.workstationName || "未归属工位"}`,
      `- 工位知识库（GitHub repo-relative）: ${seat.workstationKnowledgePath || "docs/workstations/<logical-workstation>.md"}`,
      `- NPC 知识库摘要: ${seat.knowledgeSummary || "未填写；先阅读 NPC 固定知识库后补齐"}`,
      `- 同工位通讯录: ${sameWorkstationDirectory}`,
      `- 跨工位入口: ${crossLeadDirectory}`,
      "- 路由规则: 同工位先按职责找最匹配 NPC；跨工位只找目标工位工位长转交。",
      "- 显示边界: 详细处理过程留在绑定的 Codex / Claude Code 线程；平台只回写最小回执、最终结果、阻塞原因和可追踪索引。",
      "- 回执格式: Understood / Changed / Validated / Blocked / Next。",
    ].join("\n");
  }

  function dispatchToPeer(peerId: string, peerName: string, emptyHint: string) {
    const liveDraft = (draftRef.current?.value ?? draft).trim();
    if (!liveDraft) {
      setSendNote(emptyHint);
      setTimeout(() => setSendNote(null), 4000);
      return;
    }
    sendCommand({ peerId, peerName });
  }

  async function togglePairReview(peer: WorkbenchSeat, nextPolicy: "skip" | "inherit") {
    const peerId = peer.rowId || peer.id;
    const pairKey = `${seatApiId}->${peerId}`;
    setReviewBusyId(`pair:${pairKey}`);
    setReviewNote(null);
    try {
      await setPairReviewPolicy(
        seatApiId,
        peerId,
        nextPolicy,
        nextPolicy === "skip" ? `用户信任 ${seat.name} 到 ${peer.name} 的协作` : `用户关闭 ${seat.name} 到 ${peer.name} 的免审`,
      );
      setReviewNote(nextPolicy === "skip" ? `✓ ${seat.name} → ${peer.name} 已开启免审` : `✓ ${seat.name} → ${peer.name} 已关闭免审`);
      await load(limit);
      window.dispatchEvent(new CustomEvent("workbench:collab-updated", { detail: { projectId, action: "pair-review-policy" } }));
    } catch (e) {
      setReviewNote(`免审设置失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setReviewBusyId(null);
      setTimeout(() => setReviewNote(null), 5000);
    }
  }

  function renderPairReviewToggle(peer: WorkbenchSeat) {
    const peerId = peer.rowId || peer.id;
    const pairKey = `${seatApiId}->${peerId}`;
    const policy = pairReviewPolicies[pairKey] || "inherit";
    const busy = reviewBusyId === `pair:${pairKey}`;
    const nextPolicy: "skip" | "inherit" = policy === "skip" ? "inherit" : "skip";
    return (
      <button
        type="button"
        className={styles.peerReviewToggle}
        data-policy={policy}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (!busy) togglePairReview(peer, nextPolicy);
        }}
        disabled={busy}
        title={policy === "skip" ? `关闭 ${seat.name} → ${peer.name} 的下次免审` : `信任 ${seat.name} → ${peer.name}，下次不再审核`}
      >
        {busy ? "..." : policy === "skip" ? "免审中" : "需审"}
      </button>
    );
  }

  function renderPeerDirectoryCard(peer: WorkbenchSeat, mode: "same" | "cross") {
    const peerId = peer.rowId || peer.id;
    const isCross = mode === "cross";
    const dispatchLabel = dispatchingPeerId === peerId ? (isCross ? "转交中..." : "派发中...") : (isCross ? "转交" : "派单");
    const emptyHint = isCross
      ? `先在底部 textarea 写内容，再点「转交 ${peer.name}」`
      : `先在底部 textarea 写内容，再点「派单 ${peer.name}」`;
    const title = isCross
      ? `以 ${seat.name} 身份请 ${peer.name}（${peer.computerNodeName || peer.workstationName || "目标工位"} 工位长）转交`
      : `以 ${seat.name} 身份直接派单给 ${peer.name}`;
    return (
      <div key={peer.id} className={styles.peerChip} data-lead={peer.isLead ? "1" : "0"} data-cross={isCross ? "1" : "0"}>
        <button
          type="button"
          className={styles.peerOpenBtn}
          onClick={() => onOpenTeammate(peer.id)}
          title={`打开 ${peer.name} 的瓷砖${peer.isLead ? "（工位长）" : ""}`}
        >
          <span className={styles.peerName}>
            {peer.isLead ? "工位长 · " : ""}
            {peer.name}
          </span>
          <span className={styles.peerMeta}>{peer.workstationName || peer.computerNodeName || peer.providerLabel || peer.providerId || "未绑定工位"}</span>
          {peer.responsibility ? <span className={styles.peerResponsibility}>{peer.responsibility}</span> : null}
        </button>
        <div className={styles.peerActions}>
          <button
            type="button"
            className={styles.peerDispatchBtn}
            data-cross={isCross ? "1" : undefined}
            data-testid={`${isCross ? "dispatch-cross-lead" : "dispatch-peer"}-${peerId}`}
            data-dispatch-peer-id={peerId}
            data-dispatch-peer-name={peer.name}
            data-dispatch-empty-hint={emptyHint}
            onMouseDown={(e) => {
              e.preventDefault();
              dispatchToPeer(peerId, peer.name, emptyHint);
            }}
            onPointerDown={(e) => {
              e.preventDefault();
              dispatchToPeer(peerId, peer.name, emptyHint);
            }}
            onKeyDown={(e) => {
              if (e.key !== "Enter" && e.key !== " ") return;
              e.preventDefault();
              dispatchToPeer(peerId, peer.name, emptyHint);
            }}
            onClick={(e) => {
              e.preventDefault();
            }}
            disabled={sending || occupancyHeldByOther}
            title={title}
          >
            {dispatchLabel}
          </button>
          {renderPairReviewToggle(peer)}
        </div>
      </div>
    );
  }

  function resolveImplicitDispatchTarget(text: string): { peerId: string; peerName: string; reason: string } | null {
    const normalizeForRoute = (value: string) =>
      value
        .toLowerCase()
        .replace(/yuespeak/g, " ")
        .replace(/[^\p{L}\p{N}]+/gu, " ")
        .replace(/\s+/g, " ")
        .trim();
    const normalized = normalizeForRoute(text);
    const explicitRouteIntent = /(@|转交给|转给|派单给|交给|找.{0,16}(处理|复核|实现|验证|接手))/i.test(text);
    if (!explicitRouteIntent) return null;
    const candidates = [...crossLeads, ...teammates];
    for (const candidate of candidates) {
      const names = [
        candidate.name,
        candidate.workstationName,
        candidate.computerNodeName,
      ]
        .map((value) => String(value || "").trim())
        .filter(Boolean);
      const aliases = names.flatMap((name) => {
        const normalizedName = normalizeForRoute(name);
        const slashHead = normalizeForRoute(name.split("/")[0] || "");
        const words = normalizedName.split(" ").filter((word) => word.length >= 3);
        const pairs = words.length >= 2 ? words.slice(0, -1).map((word, index) => `${word} ${words[index + 1]}`) : [];
        return [normalizedName, slashHead, ...pairs, ...words].filter((alias) => alias.length >= 3);
      });
      if (aliases.some((alias) => normalized.includes(alias))) {
        return {
          peerId: candidate.rowId || candidate.id,
          peerName: candidate.name,
          reason: candidate.workstationId !== seat.workstationId ? "按正文提到的目标工位长自动转交" : "按正文提到的同工位伙伴自动派单",
        };
      }
    }
    return null;
  }

  useEffect(() => {
    const root = tileRef.current;
    if (!root) return;
    const handleNativeDispatch = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest<HTMLElement>("[data-dispatch-peer-id]") : null;
      if (!target || !root.contains(target)) return;
      event.preventDefault();
      event.stopPropagation();
      const peerId = target.dataset.dispatchPeerId || "";
      const peerName = target.dataset.dispatchPeerName || peerId;
      const emptyHint = target.dataset.dispatchEmptyHint || "先在底部 textarea 写内容，再选择派单目标。";
      if (!peerId || sending || occupancyHeldByOther) return;
      dispatchToPeer(peerId, peerName, emptyHint);
    };
    root.addEventListener("click", handleNativeDispatch, true);
    root.addEventListener("mousedown", handleNativeDispatch, true);
    return () => {
      root.removeEventListener("click", handleNativeDispatch, true);
      root.removeEventListener("mousedown", handleNativeDispatch, true);
    };
  }, [draft, sending, occupancyHeldByOther, reviewBusyId]);

  async function sendCommand(opts?: { peerId?: string; peerName?: string }) {
    if (sendInFlightRef.current) return;
    const liveDraft = draftRef.current?.value ?? draft;
    const body = liveDraft.trim();
    if (!body) return;
    const reviewIntent = /^(通过并下次免审|通过免审|批准并免审|同意并免审|通过|批准|同意|放行|打回|拒绝|驳回)(待审|审核|第一条待审|当前待审)?/i.exec(body);
    if (!opts && reviewIntent && pendingReviews.length > 0) {
      const action: "approve" | "reject" = /打回|拒绝|驳回/i.test(reviewIntent[1]) ? "reject" : "approve";
      const rememberPolicy = action === "approve" && /免审/i.test(reviewIntent[1]) ? "skip" : undefined;
      if (draftRef.current) draftRef.current.value = "";
      setDraft("");
      setSendNote(action === "approve" ? (rememberPolicy ? "正在通过第一条待审消息，并记住这对 NPC 下次免审..." : "正在通过第一条待审消息...") : "正在打回第一条待审消息...");
      await reviewMessage(pendingReviews[0].id, action, rememberPolicy);
      return;
    }
    const dispatchIntent = /^(启动真实处理|启动处理|开始处理|处理|拒绝|无法完成|退回)(派单|任务|第一条派单|当前派单)?/i.exec(body);
    if (!opts && dispatchIntent && myQueue.length > 0) {
      const verb = dispatchIntent[1];
      const action: "ack" | "complete" | "reject" | "launch" =
        /拒绝|无法完成|退回/i.test(verb)
          ? "reject"
          : "launch";
      if (draftRef.current) draftRef.current.value = "";
      setDraft("");
      if (action === "launch") {
        setSendNote("请点击该派单旁边的“启动真实处理”，平台会拉起绑定线程；后续会做成回车直接触发。");
        setTimeout(() => setSendNote(null), 5000);
        return;
      }
      setSendNote("正在拒绝第一条派单并写回执...");
      await updateDispatchStatus(myQueue[0], action);
      return;
    }
    const implicitTarget = opts ? null : resolveImplicitDispatchTarget(body);
    const targetOpts = opts || (implicitTarget ? { peerId: implicitTarget.peerId, peerName: implicitTarget.peerName } : undefined);
    sendInFlightRef.current = true;
    setSending(true);
    setDispatchingPeerId(targetOpts?.peerId || "__self__");
    setSendNote(null);
    const isPeer = !!targetOpts?.peerId;
    const targetSeat = targetOpts?.peerId
      ? [...teammates, ...crossLeads].find((candidate) => seatIdentityList(candidate).includes(targetOpts.peerId!))
      : null;
    const isCrossWorkstation = Boolean(
      targetSeat && seatGroupKeyLocal(targetSeat) && seatGroupKeyLocal(seat) && seatGroupKeyLocal(targetSeat) !== seatGroupKeyLocal(seat),
    );
    try {
      setSendNote(isPeer ? `正在${implicitTarget ? "自动" : ""}转交给 ${targetOpts!.peerName || targetOpts!.peerId}...` : "正在写入协作消息池...");
      const res = await fetch(apiClientUrl("/api/collaboration/messages"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          project_id: projectId,
          message_type: isPeer ? "requirement_dispatch" : "agent_command",
          title: isPeer
            ? `[NPC ${seat.name} → ${targetOpts!.peerName || targetOpts!.peerId}] ${isCrossWorkstation ? "跨工位转交" : "同工位派单"}`
            : `[用户 → ${seat.name}] 对话指令`,
          body: buildDispatchBody(
            implicitTarget ? `${body}\n\n[平台自动路由] ${implicitTarget.reason}` : body,
            targetOpts?.peerName || seat.name,
          ),
          // 同工位伙伴派单：sender/recipient 使用稳定 DB rowId，展示仍保留 NPC 名称。
          sender_type: isPeer ? "agent" : "human",
          sender_id: isPeer ? seatApiId : null,
          recipient_type: "thread_workstation",
          recipient_id: isPeer ? targetOpts!.peerId! : seatApiId,
          status: isCrossWorkstation ? "pending_review" : "queued",
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      if (!json?.data?.id) {
        throw new Error("消息接口没有返回已创建消息，请检查登录态或 API 代理");
      }
      if (draftRef.current) draftRef.current.value = "";
      setDraft("");
      if (!isPeer && !automationEnabled) {
        setSendNote("已派发，正在拉起绑定线程做单次处理...");
        const launchResult = await launchNpcOneShotThreadProcessing(projectId, seatApiId, json.data.id);
        setSendNote(
          launchResult.launched
            ? launchResult.desktopVisible
              ? "已进入绑定桌面线程 ✓"
              : `已执行到绑定 session；当前 Desktop 窗口不直播，结果会回到这个对话框`
            : `已派发，但单次处理启动失败：${launchResult.error || "请检查本机执行器"}`,
        );
        if (launchResult.launched) refreshAfterOneShot();
      } else {
        setSendNote(
          isPeer
            ? (isCrossWorkstation ? `已转交给 ${targetOpts!.peerName || targetOpts!.peerId}，等待人审 ✓` : `已派给 ${targetOpts!.peerName || targetOpts!.peerId} ✓`)
            : (automationEnabled ? "已派发，等待 NPC 自动化拉取 ✓" : "已派发 ✓"),
        );
      }
      autoScrollRef.current = true;
      await load(limit);
      window.dispatchEvent(new CustomEvent("workbench:collab-updated", { detail: { projectId, messageId: json.data.id, action: "send" } }));
    } catch (e) {
      setSendNote(`派发失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      sendInFlightRef.current = false;
      setSending(false);
      setDispatchingPeerId(null);
      setTimeout(() => setSendNote(null), 7000);
    }
  }

  function seatGroupKeyLocal(value: WorkbenchSeat): string {
    return value.workstationId || value.computerNodeId || "";
  }

  async function updateDispatchStatus(message: CollabMessage, action: "reject") {
    setQueueBusyId(`${message.id}:${action}`);
    setQueueNote(null);
    try {
      const endpoint = "complete";
      const body = {
        result_status: "failed",
        note: `NPC ${seat.name} 拒绝或无法完成此派单，已回执给上游。`,
      };
      const res = await fetch(
        apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/thread-workstations/${encodeURIComponent(seatApiId)}/messages/${encodeURIComponent(message.id)}/${endpoint}`),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(body),
        },
      );
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setQueueNote("已拒绝，回执已写入事件线");
      await load(limit);
      window.dispatchEvent(new CustomEvent("workbench:collab-updated", { detail: { projectId, messageId: message.id, action } }));
    } catch (e) {
      setQueueNote(`队列操作失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setQueueBusyId(null);
      setTimeout(() => setQueueNote(null), 5000);
    }
  }

  const totalLoaded = messages?.length ?? 0;
  const filteredCount = visible.length;
  const hiddenHistoryCount = Math.max(0, totalLoaded - filteredCount);
  const threadStatusLabel = occupancyHeldByMe ? "我在操作" : occupancyHeldByOther ? "他人操作中" : "可接手";
  const launchPackNode = launchPackOpen ? (
    <div className={styles.launchPackBox}>
      <form action={prepareLaunchPackAction} className={styles.launchPackForm}>
        <input type="hidden" name="return_to" value={governanceReturnTo} />
        <label>
          <span>用户已创建的 Codex 线程 ID</span>
          <input
            name="codex_thread_id"
            defaultValue={threadIdDraft || seat.threadId}
            placeholder="粘贴真实 Codex thread id"
            required
          />
        </label>
        <button type="submit" className={styles.iconBtn}>
          绑定并生成
        </button>
      </form>
      {seat.codexLaunchPrompt ? (
        <details className={styles.launchPromptDrawer}>
          <summary>查看线程提示词</summary>
          <pre>{seat.codexLaunchPrompt}</pre>
        </details>
      ) : (
        <p className={styles.profileTextDim}>用户开好线程后，把线程 ID 填上；平台会生成提示词、skill、知识库和回执约定。</p>
      )}
    </div>
  ) : null;

  const renderReviewMessage = (m: CollabMessage) => {
    const body = String(m.body || "");
    const cleanBody = stripPlatformChatter(body);
    const crossMatch = body.match(/跨工位：([是否])/);
    const sourceMatch = body.match(/来源：([a-z_]+)/);
    const upstreamMatch = body.match(/上游 NPC:\s*([^；\r\n]+)/);
    const downstreamMatch = body.match(/下游 NPC:\s*([^；\r\n]+)/);
    const isCross = crossMatch?.[1] === "是";
    const source = sourceMatch?.[1] || "";
    const upstream = upstreamMatch?.[1]?.trim() || "";
    const downstream = downstreamMatch?.[1]?.trim() || seat.name;
    const pairKey = `${String(m.sender_id || "")}->${String(m.recipient_id || "")}`;
    const pairPolicy = pairReviewPolicies[pairKey] || "inherit";
    const isHardwareRiskReview = source === "hardware_risk";
    const expanded = expandedIds.has(m.id);
    const displayBody = cleanBody || body || "(空消息)";
    const bodyPreview = displayBody.split(/\r?\n/).map((line) => line.trim()).find(Boolean) || "(空消息)";
    return (
      <div
        key={`review-${m.id}`}
        className={`${styles.msg} ${styles.msg_note} ${styles.role_system} ${styles.reviewMessage}`}
        data-role="system"
      >
        <div className={styles.msgHead}>
          <span className={`${styles.roleBadge} ${styles.roleBadge_system}`}>系统 / 审核</span>
          <span className={styles.reviewInlineBadge}>待确认</span>
          {isCross ? <span className={styles.reviewInlineBadge} data-tone="cross">跨工位</span> : null}
          {source ? (
            <span className={styles.reviewInlineBadge} data-tone={isHardwareRiskReview ? "risk" : "policy"}>
              {isHardwareRiskReview ? "硬件强审" : `policy: ${source}`}
            </span>
          ) : null}
          {pairPolicy === "skip" && !isHardwareRiskReview ? (
            <span className={styles.reviewInlineBadge} data-tone="skip">此关系免审中</span>
          ) : null}
          {pairPolicy === "skip" && isHardwareRiskReview ? (
            <span className={styles.reviewInlineBadge} data-tone="override">覆盖免审</span>
          ) : null}
          <small className={styles.msgTime}>{formatTime(m.created_at)}</small>
        </div>
        <p className={styles.msgSummary}>
          <strong>{m.title || "NPC 自主合作请求"}</strong>
          <span>
            {upstream || m.sender_id || "未知上游"} → {downstream || m.recipient_id || "未知目标"}
            {m.status ? ` · ${m.status}` : ""}
          </span>
        </p>
        {expanded ? (
          <div className={styles.msgDrawer}>
            <small className={styles.msgDrawerLabel}>审核正文</small>
            <pre className={styles.msgFull}>{displayBody}</pre>
          </div>
        ) : (
          <button
            type="button"
            className={styles.inlineBtn}
            onClick={() => toggleExpand(m.id)}
            title="查看审核正文"
          >
            查看正文 · {bodyPreview.slice(0, 58)}{bodyPreview.length > 58 ? "..." : ""}
          </button>
        )}
        {expanded ? (
          <button type="button" className={styles.inlineBtn} onClick={() => toggleExpand(m.id)}>
            收起
          </button>
        ) : null}
        <div className={styles.reviewInlineActions}>
          <button
            type="button"
            className={styles.reviewApproveBtn}
            disabled={reviewBusyId === m.id}
            onMouseDown={(e) => {
              e.preventDefault();
              if (reviewBusyId !== m.id) reviewMessage(m.id, "approve");
            }}
            onPointerDown={(e) => {
              e.preventDefault();
              if (reviewBusyId !== m.id) reviewMessage(m.id, "approve");
            }}
            onClick={(e) => e.preventDefault()}
          >
            通过
          </button>
          <button
            type="button"
            className={styles.reviewRememberBtn}
            disabled={reviewBusyId === m.id}
            onMouseDown={(e) => {
              e.preventDefault();
              if (reviewBusyId !== m.id) reviewMessage(m.id, "approve", "skip");
            }}
            onPointerDown={(e) => {
              e.preventDefault();
              if (reviewBusyId !== m.id) reviewMessage(m.id, "approve", "skip");
            }}
            onClick={(e) => e.preventDefault()}
            title="通过这条消息，并让同一对 NPC 下次直接派发"
          >
            通过并免审
          </button>
          <button
            type="button"
            className={styles.reviewRejectBtn}
            disabled={reviewBusyId === m.id}
            onMouseDown={(e) => {
              e.preventDefault();
              if (reviewBusyId !== m.id) reviewMessage(m.id, "reject");
            }}
            onPointerDown={(e) => {
              e.preventDefault();
              if (reviewBusyId !== m.id) reviewMessage(m.id, "reject");
            }}
            onClick={(e) => e.preventDefault()}
          >
            打回
          </button>
        </div>
      </div>
    );
  };

  return (
    <article ref={tileRef} className={styles.tile}>
      <header className={styles.head}>
        <div className={styles.headLeft}>
          <strong className={styles.name} title={seat.name}>
            {seat.name}
            {seat.isLead ? (
              <span className={styles.leadChip} title="本工位的工位长：跨工位消息默认转交给此 NPC">
                👑 工位长
              </span>
            ) : null}
          </strong>
          <small className={styles.subline}>
            <span title="所属工位">{seat.workstationName || "未归属工位"}</span>
            <span title="模型 provider">{seat.providerLabel || seat.providerId || "未绑定线程"}</span>
            {seat.model ? <span>· {seat.model}</span> : null}
            {automationEnabled ? <span className={styles.pillOk}>自动化</span> : null}
          </small>
          <div className={styles.threadBinding} data-busy={occupancyHeldByOther ? "1" : occupancyHeldByMe ? "me" : "0"}>
            <Link
              href={governanceHref("npc-create")}
              className={styles.threadChip}
              title="回到主页面：NPC / 线程绑定"
            >
              线程 {seat.providerLabel || seat.providerId || "未绑定"}
            </Link>
            <Link
              href={governanceHref("npc-create")}
              className={styles.threadChip}
              title="回到主页面：登记或修正真实执行线程 ID"
            >
              ID {seat.threadId || "未登记"}
            </Link>
            <Link
              href={governanceHref("computers")}
              className={styles.threadChip}
              title="回到主页面：电脑 / Runner / 扫描"
            >
              电脑 {seat.computerNodeName || seat.computerNodeId || "未绑定"}
            </Link>
            <Link
              href={governanceHref("computers")}
              className={styles.threadChip}
              title="回到主页面：查看 Runner 和桥接健康"
            >
              {seat.threadKind || "thread"} · {seat.threadHealth || "未知"}
            </Link>
            <span className={`${styles.threadChip} ${styles.occupancyChip}`} title="当前操作占用状态">
              {threadStatusLabel}
            </span>
            <Link
              href={governanceHref("computers")}
              className={styles.threadChip}
              title="回到主页面：Runner 自动化和电脑接入"
            >
              自动化 {automationEnabled ? "已开" : "手动"}
            </Link>
            {seat.desktopVisible ? (
              <span
                className={`${styles.threadChip} ${styles.desktopVisibleChip}`}
                title="平台派单会作为普通用户消息进入绑定的 Codex Desktop 线程，完整处理过程在桌面版显示"
              >
                桌面可见
              </span>
            ) : seat.desktopProcessDetected ? (
              <span
                className={`${styles.threadChip} ${styles.desktopDetectedChip}`}
                title="检测到桌面版，但当前绑定线程未上报实时 UI 桥；平台会诚实显示为非实时可见"
              >
                桌面待桥接
              </span>
            ) : null}
            {seat.deliveryLabel ? (
              <span className={styles.threadChip} title={seat.deliveryWarning || "当前 NPC 的投递方式"}>
                {seat.deliveryLabel}
              </span>
            ) : null}
            {seat.desktopThreadUrl ? (
              <a
                className={`${styles.threadChip} ${styles.desktopThreadChip}`}
                href={seat.desktopThreadUrl}
                title="在 Codex Desktop 打开这个 NPC 绑定的线程"
              >
                打开桌面线程
              </a>
            ) : null}
          </div>
        </div>
        <div className={styles.headActions}>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => setHeaderCollapsed((v) => !v)}
            title={headerCollapsed ? "展开职责/技能/知识库" : "收起职责/技能/知识库（让消息流占更多空间）"}
          >
            {headerCollapsed ? "展开档案" : "收起档案"}
          </button>
          <button type="button" className={styles.closeBtn} onClick={onClose} title="关闭这个瓷砖">✕</button>
        </div>
      </header>

      <div
        className={`${styles.occupancyBar} ${
          occupancyHeldByMe
            ? styles.occupancyMine
            : occupancyHeldByOther
              ? styles.occupancyOther
              : styles.occupancyIdle
        }`}
      >
        <span className={styles.occupancyDot} aria-hidden />
        <span className={styles.occupancyText}>
          {occupancyHeldByMe
            ? `🟢 你正在占用此 NPC`
            : occupancyHeldByOther
              ? `🟡 ${occupancy?.user_name || occupancy?.user_id} 正在占用`
              : `⚪ 空闲，可占用`}
        </span>
        {occupancyHeldByMe ? (
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => releaseOccupancy(false)}
            disabled={occupancyBusy}
            title="释放占用，让其他人可以接手"
          >
            释放
          </button>
        ) : occupancyHeldByOther ? (
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => claimOccupancy(true)}
            disabled={occupancyBusy}
            title="强制抢占（对方会被踢下来）"
          >
            申请抢占
          </button>
        ) : (
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => claimOccupancy(false)}
            disabled={occupancyBusy}
            title="占用此 NPC，避免他人同时操作"
          >
            占用
          </button>
        )}
        {occupancyError ? <small className={styles.occupancyHint}>{occupancyError}</small> : null}
      </div>

      {headerCollapsed && launchPackNode ? (
        <section className={styles.profile} data-compact="launch-pack">
          <div className={styles.profileRow}>
            <small className={styles.sectionLabel}>上岗包 / 线程绑定</small>
            {launchPackNode}
          </div>
        </section>
      ) : null}

      {!headerCollapsed ? (
        <section className={styles.profile}>
          <div className={styles.profileRow}>
            <small className={styles.sectionLabel}>职责</small>
            <p className={styles.profileText}>{seat.responsibility || "未填写"}</p>
          </div>
          {(() => {
            const inherited = (seat.inheritedSkills ?? []).filter(Boolean);
            const inheritedSet = new Set(inherited);
            const own = (seat.skillLoadout ?? []).filter((s) => !inheritedSet.has(s));
            const total = inherited.length + own.length;
            if (total === 0) {
              return (
                <div className={styles.profileRow}>
                  <small className={styles.sectionLabel}>Skill / 知识装配</small>
                  <p className={styles.profileTextDim}>
                    暂无 NPC skill 或工位继承 skill。先到主页面给逻辑工位配置 skill_inheritance，或给这个 NPC 装配项目 Skill。
                  </p>
                  <div className={styles.inlineActions}>
                    <Link href={governanceHref("skills", "skill-category")} className={styles.linkBtn}>
                      配置 Skill
                    </Link>
                    <Link href={governanceHref("development-workshop")} className={styles.linkBtn}>
                      配置工位
                    </Link>
                  </div>
                </div>
              );
            }
            return (
              <div className={styles.profileRow}>
                <small className={styles.sectionLabel}>
                  Skill / 知识装配 ({total})
                  {inherited.length > 0 ? <span className={styles.peerHint}> · 工位继承 {inherited.length} / 自加 {own.length}</span> : null}
                </small>
                <div className={styles.chipRow}>
                  {inherited.slice(0, 6).map((skill) => (
                    <Link
                      key={`inh-${skill}`}
                      href={governanceHref("skills")}
                      className={styles.chipInherit}
                      title="回到主页面：查看 Skill 仓库和工位继承"
                    >
                      ⇪ {skill}
                    </Link>
                  ))}
                  {own.slice(0, 6).map((skill) => (
                    <Link
                      key={`own-${skill}`}
                      href={governanceHref("skills")}
                      className={styles.chip}
                      title="回到主页面：查看 NPC Skill 装配"
                    >
                      {skill}
                    </Link>
                  ))}
                  {total > 12 ? <span className={styles.chipMore}>+{total - 12}</span> : null}
                </div>
              </div>
            );
          })()}
          {seat.workstationKnowledgePath ? (
            <div className={styles.profileRow}>
              <small className={styles.sectionLabel}>工位知识库（GitHub 相对路径）</small>
              <p className={styles.profileText}>
                <Link href={governanceHref("git")} className={styles.codeLink} title="回到主页面：仓库与 GitHub 相对路径约定">
                  {seat.workstationKnowledgePath}
                </Link>
                <span className={styles.peerHint}> · 本工位所有 NPC 共读，本地路径只作执行目录</span>
              </p>
            </div>
          ) : (
            <div className={styles.profileRow}>
              <small className={styles.sectionLabel}>工位知识库（待配置）</small>
              <p className={styles.profileTextDim}>
                先在主页面给这个 NPC 分配逻辑工位，并设置 GitHub 相对路径知识库；否则同工位互认和跨工位工位长路由都会退化。
              </p>
            </div>
          )}
          {seat.knowledgeSummary ? (
            <div className={styles.profileRow}>
              <small className={styles.sectionLabel}>NPC 知识库摘要</small>
              <p className={styles.profileText}>
                {seat.knowledgeSummary.length > 140
                  ? `${seat.knowledgeSummary.slice(0, 140)}…`
                  : seat.knowledgeSummary}
              </p>
            </div>
          ) : null}
          <div className={styles.profileRow}>
            <small className={styles.sectionLabel}>线程绑定</small>
            {editingThread ? (
              <div className={styles.identityForm}>
                <input
                  className={styles.identityInput}
                  value={threadIdDraft}
                  onChange={(e) => setThreadIdDraft(e.target.value)}
                  placeholder="Codex thread id"
                />
                <input
                  className={styles.identityInput}
                  value={threadKindDraft}
                  onChange={(e) => setThreadKindDraft(e.target.value)}
                  placeholder="Codex"
                />
                <input
                  className={styles.identityInput}
                  value={threadHealthDraft}
                  onChange={(e) => setThreadHealthDraft(e.target.value)}
                  placeholder="watcher ready / 待接入 / 需唤醒"
                />
                <div className={styles.identityActions}>
                  <button type="button" className={styles.iconBtn} onClick={saveThreadBinding} disabled={savingThread}>
                    {savingThread ? "保存中…" : "保存绑定"}
                  </button>
                  <button type="button" className={styles.iconBtn} onClick={() => setEditingThread(false)} disabled={savingThread}>
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <div className={styles.identityRow}>
                <span className={styles.identityMeta}>
                  {seat.threadKind || seat.providerLabel || seat.providerId || "thread"} · {seat.threadId || "未登记真实线程 ID"} · {seat.threadHealth || "未知"}
                </span>
                {seat.desktopVisible ? (
                  <span className={styles.statusPill} title="平台派单会作为普通用户消息进入绑定的 Codex Desktop 线程">
                    桌面可见
                  </span>
                ) : null}
                {seat.desktopThreadUrl ? (
                  <a className={styles.iconBtn} href={seat.desktopThreadUrl} title="在 Codex Desktop 打开这个 NPC 绑定的线程">
                    打开桌面线程
                  </a>
                ) : null}
                <button type="button" className={styles.iconBtn} onClick={() => setEditingThread(true)} title="登记或修正这个 NPC 绑定的执行线程">
                  绑定
                </button>
                <button type="button" className={styles.iconBtn} onClick={() => setLaunchPackOpen((value) => !value)} title="为用户已创建的 Codex 线程生成提示词、skill 和知识库">
                  上岗包
                </button>
              </div>
            )}
            {threadNote ? <small className={styles.identityNote}>{threadNote}</small> : null}
            {launchPackNode}
          </div>
          <div className={styles.deliveryBanner} data-visible={seat.desktopVisible ? "1" : "0"}>
            <div>
              <strong>{seat.deliveryLabel || seat.threadKind || seat.providerLabel || "线程投递"}</strong>
              <span>
                {seat.desktopVisible
                  ? "桌面线程可见"
                  : seat.desktopProcessDetected
                    ? "检测到桌面版，实时桥未连接"
                    : "桌面实时显示不可用"}
              </span>
            </div>
            <details className={styles.deliveryDetails}>
              <summary>桌面状态</summary>
              <small>
                {seat.executorCwd ? `执行目录：${seat.executorCwd}` : "执行目录未登记"}
                {seat.desktopBridgeLabel ? ` · 桥接：${seat.desktopBridgeLabel}` : ""}
                {seat.desktopThreadUrl ? ` · 可打开：${seat.desktopThreadUrl}` : ""}
                {seat.desktopBridgeNote ? ` · ${seat.desktopBridgeNote}` : ""}
                {seat.deliveryWarning ? ` · ${seat.deliveryWarning}` : ""}
              </small>
            </details>
          </div>
          <div className={styles.profileRow}>
            <small className={styles.sectionLabel}>
              NPC 自动化
              <span className={styles.peerHint}>· 执行过程在绑定线程中跑，平台只看摘要回执</span>
            </small>
            <div className={styles.automationRow}>
              <button
                type="button"
                className={`${styles.automationSwitch} ${automationEnabled ? styles.automationSwitchOn : ""}`}
                onClick={() => toggleAutomation(!automationEnabled)}
                disabled={automationBusy}
                aria-pressed={automationEnabled}
                title={automationEnabled ? "暂停此 NPC 的自动接单/回执桥接" : "开启此 NPC 的自动接单/回执桥接"}
              >
                <span className={styles.automationKnob} />
                <span>{automationEnabled ? "自动化已开" : "手动模式"}</span>
              </button>
              <span className={styles.identityMeta}>
                {automationEnabled
                  ? `${seat.providerLabel || seat.providerId || "线程"} watcher 会拉取派单；复杂过程在绑定线程里处理。`
                  : "关闭时发送只跑当前这一条；Codex 会写入/执行绑定 session，不创建持续自动化。"}
              </span>
            </div>
            {!automationEnabled ? (
              <small className={styles.identityNote}>
                Desktop 还没有可接入的实时输入桥；平台只显示最小回执和最终结果。
              </small>
            ) : null}
            {automationNote ? <small className={styles.identityNote}>{automationNote}</small> : null}
            <code className={styles.automationCommand} title="在绑定电脑上运行，让这个 NPC 的绑定线程开始自动拉取派单">
              {watcherCommand}
            </code>
          </div>
          <div className={styles.profileRow}>
            <small className={styles.sectionLabel}>
              GitHub 身份
              <span className={styles.peerHint}>· commit author（SSH 推送本机配）</span>
            </small>
            {editingIdentity ? (
              <div className={styles.identityForm}>
                <input
                  className={styles.identityInput}
                  value={gitName}
                  onChange={(e) => setGitName(e.target.value)}
                  placeholder="git user.name"
                />
                <input
                  className={styles.identityInput}
                  value={gitEmail}
                  onChange={(e) => setGitEmail(e.target.value)}
                  placeholder="git user.email"
                />
                <select
                  className={styles.identityInput}
                  value={reviewPolicy}
                  onChange={(e) => setReviewPolicy(e.target.value)}
                  title="人工审核策略：inherit 跟工位/项目，force 强审，skip 免审"
                >
                  <option value="inherit">审核：继承（项目/工位）</option>
                  <option value="force">审核：强审（必经）</option>
                  <option value="skip">审核：免审（直接落地）</option>
                </select>
                <div className={styles.identityActions}>
                  <button type="button" className={styles.iconBtn} onClick={saveIdentity} disabled={savingIdentity}>
                    {savingIdentity ? "保存中…" : "保存"}
                  </button>
                  <button
                    type="button"
                    className={styles.iconBtn}
                    onClick={() => {
                      setEditingIdentity(false);
                      setGitName(seat.gitUserName);
                      setGitEmail(seat.gitUserEmail);
                      setReviewPolicy(seat.reviewPolicy || "inherit");
                    }}
                  >
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <div className={styles.identityRow}>
                <p className={styles.profileText}>
                  <code className={styles.code}>{seat.gitUserName}</code>{" "}
                  <code className={styles.code}>&lt;{seat.gitUserEmail}&gt;</code>
                </p>
                <small className={styles.identityMeta}>
                  审核：
                  <span className={styles.reviewBadge} data-policy={seat.reviewPolicy}>
                    {seat.reviewPolicy === "force" ? "强审" : seat.reviewPolicy === "skip" ? "免审" : "继承"}
                  </span>
                </small>
                <button type="button" className={styles.iconBtn} onClick={() => setEditingIdentity(true)}>
                  改
                </button>
              </div>
            )}
            {identityNote ? <small className={styles.identityNote}>{identityNote}</small> : null}
          </div>
          <div className={styles.profileRow}>
            <small className={styles.sectionLabel}>协作路由协议</small>
            <div className={styles.routeProtocol}>
              <p>同工位：先按职责找最匹配 NPC，必要时找本工位工位长。</p>
              <p>跨工位：只找目标工位工位长转交；普通 NPC 不跨工位直连。</p>
            </div>
          </div>
          <div className={styles.profileRow}>
            <small className={styles.sectionLabel}>
              同工位伙伴 ({teammates.length})
              <span className={styles.peerHint}>· 互相认识，按职责找人</span>
            </small>
            {teammates.length === 0 ? (
              <p className={styles.profileTextDim}>同工位暂无其他 NPC。</p>
            ) : (
              <div className={styles.peerRow}>
                {teammates.map((peer) => renderPeerDirectoryCard(peer, "same"))}
              </div>
            )}
          </div>
          {crossLeads.length > 0 ? (
            <div className={styles.profileRow}>
              <small className={styles.sectionLabel}>
                跨工位通道（经工位长，{crossLeads.length}）
                <span className={styles.peerHint}>· 跨工位禁直派；后端兜底改寄给目标工位的工位长</span>
              </small>
              <div className={styles.peerRow}>
                {crossLeads.map((lead) => renderPeerDirectoryCard(lead, "cross"))}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      <details className={styles.runtimeDetails}>
        <summary>
          <span>运行详情</span>
          <small>
            需求 {(seatQueues?.requirement_inbox.count ?? 0)}
            {" / "}
            任务 {(seatQueues?.task_todo.count ?? 0)}
            {" / "}
            指令 {myQueue.length}
            {" / "}
            回执 {receipts?.length ?? 0}
          </small>
        </summary>
        <div className={styles.runtimeBody}>
      {(() => {
        const inboxItems = seatQueues?.requirement_inbox.items ?? [];
        const todoItems = seatQueues?.task_todo.items ?? [];
        const dispatchItems = myQueue;
        const inboxCount = seatQueues?.requirement_inbox.count ?? 0;
        const todoCount = seatQueues?.task_todo.count ?? 0;
        if (inboxCount === 0 && todoCount === 0 && dispatchItems.length === 0 && (receipts?.length ?? 0) === 0) {
          return null;
        }
        const activeItems = queueTab === "inbox" ? inboxItems : queueTab === "todo" ? todoItems : null;
        return (
          <div className={styles.queueBox}>
            <div className={styles.queueHead}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={() => setQueueTab("inbox")}
                  className={styles.iconBtn}
                  data-active={queueTab === "inbox" ? "1" : undefined}
                  title="需求队列：别人/自己派给我、未关闭的 requirement"
                >
                  📥 需求 {inboxCount}
                </button>
                <button
                  type="button"
                  onClick={() => setQueueTab("todo")}
                  className={styles.iconBtn}
                  data-active={queueTab === "todo" ? "1" : undefined}
                  title="任务队列：以本 NPC 的 agent 为 assignee 的未结 task"
                >
                  📋 任务 {todoCount}
                </button>
                <button
                  type="button"
                  onClick={() => setQueueTab("dispatch")}
                  className={styles.iconBtn}
                  data-active={queueTab === "dispatch" ? "1" : undefined}
                  title="派单消息：直接发给本 NPC 的 collaboration_message"
                >
                  ✉ 指令 {dispatchItems.length}
                </button>
              </div>
              <small className={styles.muted}>
                {queueTab === "inbox" ? "未接 / 在评估" : queueTab === "todo" ? "已接 task" : "优先显示进行中，其次最新待接"}
              </small>
            </div>
            {queueTab === "dispatch" ? (
              <ul className={styles.queueList}>
                {dispatchItems.slice(0, 6).map((m, i) => {
                  const isFromPeer = (m.sender_type || "").toLowerCase() === "agent" && peerIds.has(m.sender_id || "");
                  const isFromExternal = (m.sender_type || "").toLowerCase() === "agent" && !!m.sender_id && m.sender_id !== seat.id && !peerIds.has(m.sender_id);
                  const fromLabel = isFromPeer
                    ? `同工位 · ${peerByIdentity.get(m.sender_id || "")?.name || m.sender_id}`
                    : isFromExternal
                      ? `跨工位 · ${m.sender_id}`
                      : (m.sender_type || "?");
                  const isLatest = i === 0;
                  return (
                    <li key={m.id} className={styles.queueItem} data-from={isFromPeer ? "peer" : isFromExternal ? "external" : (m.sender_type || "")} data-latest={isLatest ? "1" : undefined}>
                      <span className={styles.queuePos}>{isLatest ? "最新" : `#${i + 1}`}</span>
                      <div className={styles.queueMeta}>
                        <span className={styles.queueFrom}>{fromLabel}</span>
                        <span className={styles.queueTitle}>{m.title || (m.body || "").slice(0, 60) || "(无标题)"}</span>
                      </div>
                      <div className={styles.queueRight}>
                        <span className={styles.queueStatus} data-status={m.status}>{m.status}</span>
                        <div className={styles.queueActions} aria-label="派单处理">
                          {renderRealThreadLauncher(m, "compact", isLatest)}
                          {["queued", "pending", "acked", "in_progress"].includes((m.status || "").toLowerCase()) ? (
                            <button
                              type="button"
                              className={styles.queueActionBtn}
                              data-danger="1"
                              onClick={() => updateDispatchStatus(m, "reject")}
                              disabled={queueBusyId !== null}
                              title="让本 NPC 写入失败/拒绝回执并关闭派单"
                            >
                              拒绝
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : activeItems && activeItems.length > 0 ? (
              <ul className={styles.queueList}>
                {activeItems.slice(0, 6).map((it, i) => (
                  <li key={it.id} className={styles.queueItem} data-from={queueTab}>
                    <span className={styles.queuePos}>#{i + 1}</span>
                    <div className={styles.queueMeta}>
                      <span className={styles.queueFrom}>
                        {queueTab === "inbox"
                          ? (it.from_agent ? `← ${it.from_agent}` : it.trigger_kind || "manual")
                          : (it.module ? `module: ${it.module}` : it.priority || "—")}
                      </span>
                      <span className={styles.queueTitle}>{it.title || "(无标题)"}</span>
                    </div>
                    <span className={styles.queueStatus} data-status={it.status}>{it.status}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.muted} style={{ paddingLeft: 8 }}>
                {queueTab === "inbox" ? "暂无需求" : "暂无任务"}
              </p>
            )}
            {queueTab === "dispatch" && dispatchItems.length > 6 ? (
              <small className={styles.muted}>… 还有 {dispatchItems.length - 6} 条</small>
            ) : null}
            {queueTab !== "dispatch" && activeItems && activeItems.length > 6 ? (
              <small className={styles.muted}>… 还有 {activeItems.length - 6} 条</small>
            ) : null}
            {queueTab === "dispatch" ? (
              <small className={styles.queueNote}>
                对话框是绑定线程的简洁投影：用户直发会自动单次派单；这里的“启动”只用于重试或处理队列旧消息。
              </small>
            ) : null}
            {queueNote ? <small className={styles.queueNote}>{queueNote}</small> : null}
          </div>
        );
      })()}

      {receipts && receipts.length > 0 ? (
        <div className={styles.queueBox}>
          <div className={styles.queueHead}>
            <strong>🧾 回执流（{receipts.length}）</strong>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                type="button"
                onClick={() => setReceiptDirection("incoming")}
                className={styles.iconBtn}
                data-active={receiptDirection === "incoming" ? "1" : undefined}
                title="发给我的回执"
              >
                📨 收到
              </button>
              <button
                type="button"
                onClick={() => setReceiptDirection("outgoing")}
                className={styles.iconBtn}
                data-active={receiptDirection === "outgoing" ? "1" : undefined}
                title="我发的回执"
              >
                📤 发出
              </button>
            </div>
          </div>
          <ul className={styles.queueList}>
            {receipts.slice(0, 6).map((r) => {
              const kindLabel = ({ ack: "已接", progress: "进度", done: "完成", reject: "拒绝" } as const)[r.receipt_kind];
              return (
                <li key={r.id} className={styles.queueItem} data-from={r.cross_workstation ? "external" : "peer"}>
                  <span className={styles.queuePos}>{kindLabel}</span>
                  <div className={styles.queueMeta}>
                    <span className={styles.queueFrom}>
                      {r.cross_workstation ? "跨工位" : "同工位"}
                      {" · "}
                      {receiptDirection === "incoming"
                        ? (r.sender_seat_id ? `← ${r.sender_seat_id.slice(0, 8)}` : "(系统)")
                        : (r.recipient_seat_id ? `→ ${r.recipient_seat_id.slice(0, 8)}` : "(广播)")}
                    </span>
                    <span className={styles.queueTitle}>{r.title || r.body.slice(0, 60) || "(无标题)"}</span>
                  </div>
                  <span className={styles.queueStatus} data-status={r.receipt_kind}>{r.receipt_kind}</span>
                </li>
              );
            })}
          </ul>
          {receipts.length > 6 ? <small className={styles.muted}>… 还有 {receipts.length - 6} 条</small> : null}
        </div>
      ) : null}

      <div className={styles.eventBox}>
        <div className={styles.eventHead}>
          <strong>协作事件线</strong>
          <small>人 / NPC / 线程 / 回执</small>
        </div>
        {collaborationEvents.length > 0 ? (
          <ol className={styles.eventList}>
            {collaborationEvents.map((event) => (
              <li key={event.id} className={styles.eventItem} data-tone={event.tone}>
                <span className={styles.eventDot} />
                <div className={styles.eventMain}>
                  <div className={styles.eventTitleRow}>
                    <span className={styles.eventLabel}>{event.label}</span>
                    <strong>{event.title}</strong>
                  </div>
                  <small className={styles.eventMeta}>
                    {event.meta}
                    {event.status ? ` · ${event.status}` : ""}
                    {event.createdAt ? ` · ${formatTime(event.createdAt)}` : ""}
                  </small>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className={styles.eventEmpty}>
            暂无可归并事件。给这个 NPC 派单后，这里会按「派单 / 接单 / 进度 / 完成或拒绝 / 回执」展示协同过程。
          </p>
        )}
      </div>
        </div>
      </details>

      <div className={styles.streamToolbar}>
        <div className={styles.streamToolbarLeft}>
          <strong>与 {seat.name} 的对话</strong>
          <small>
            {showFullHistory ? `${filteredCount}/${totalLoaded} 条` : `当前 ${filteredCount} · 历史 ${hiddenHistoryCount}`}
            {fetching ? " · 刷新中…" : ""}
          </small>
          <small className={styles.legend} title="按发送方/性质着色：人灰｜本NPC青｜同工位绿｜跨工位紫｜回执蓝｜系统红｜自主合作黄">
            <span className={`${styles.legendDot} ${styles.roleBadge_human}`}>人</span>
            <span className={`${styles.legendDot} ${styles.roleBadge_self}`}>我</span>
            <span className={`${styles.legendDot} ${styles.roleBadge_peer}`}>同工位</span>
            <span className={`${styles.legendDot} ${styles.roleBadge_external}`}>跨工位</span>
            <span className={`${styles.legendDot} ${styles.roleBadge_watcher}`}>CLI</span>
            <span className={`${styles.legendDot} ${styles.roleBadge_system}`}>系统</span>
          </small>
        </div>        <div className={styles.streamToolbarRight}>
          <label className={styles.noiseToggle} title="只显示接单、关键进度、需人审、完成、异常等协作信号">
            <input type="checkbox" checked={hideNoisy} onChange={(e) => setHideNoisy(e.target.checked)} />
            只看摘要
          </label>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => setLimit((v) => Math.min(v + 50, 500))}
            disabled={fetching || limit >= 500}
            title="加载更早的消息"
          >
            更多历史（当前 {limit}）
          </button>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => load(limit)}
            disabled={fetching}
            title="手动刷新"
          >
            ⟳
          </button>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => setShowFullHistory((value) => !value)}
            title={showFullHistory ? "收起旧派单和历史消息" : "展开全部历史消息"}
          >
            {showFullHistory ? "收起历史" : "历史"}
          </button>
        </div>
      </div>

      <div
        className={styles.stream}
        ref={streamRef}
        onScroll={onStreamScroll}
      >
        {fetchError ? (
          <p className={styles.emptyError}>⚠ 加载失败：{fetchError}</p>
        ) : visible.length === 0 ? (
          <p className={styles.emptyHint}>
            {messages === null
              ? "加载中…"
              : hideNoisy && totalLoaded > 0
                ? "摘要流暂无可读信号，取消勾选「只看摘要」可查看原始桥接消息。"
                : "暂无协作消息。绑定线程会处理完整过程，平台这里只显示必要摘要。"}
          </p>
        ) : (
          <>
          {visible.map((msg) => {
            if ((msg.status || "").toLowerCase() === "pending_review") {
              return renderReviewMessage(msg);
            }
            const refined = summarizeCollabMessage(msg);
            const { role, label: roleLabel } = classifyRole(msg, seat.id, peerIds, externalAgentIds);
            const expanded = expandedIds.has(msg.id);
            const body = refined.cleanBody || refined.rawBody || "(空消息)";
            const canExpand = body.length > 0;
            const senderLabel =
              role === "human"
                ? "用户"
                : role === "self"
                  ? `本 NPC · ${seat.name}`
                  : role === "peer"
                    ? `同工位 · ${peerByIdentity.get(msg.sender_id || "")?.name || msg.sender_id}`
                    : role === "external"
                      ? `跨工位 · ${msg.sender_id || "?"}`
                      : role === "watcher"
                        ? "线程 Watcher"
                        : roleLabel;
            return (
              <div
                key={msg.id}
                className={`${styles.msg} ${styles[`msg_${refined.kind}`] || ""} ${styles[`role_${role}`] || ""}`}
                data-role={role}
              >
                <div className={styles.msgHead}>
                  <span className={`${styles.roleBadge} ${styles[`roleBadge_${role}`] || ""}`} title={senderLabel}>
                    {senderLabel}
                  </span>
                  <span className={`${styles.badge} ${styles[`badge_${refined.kind}`] || ""}`}>
                    {refined.statusLabel}
                  </span>
                  <small className={styles.msgTime}>{formatTime(msg.created_at)}</small>
                  <small className={styles.msgStatus}>{msg.status}</small>
                </div>
                <p className={styles.msgSummary}>
                  <strong>{refined.headline}</strong>
                  {refined.detail ? <span>{refined.detail}</span> : null}
                </p>
                {expanded ? (
                  <div className={styles.msgDrawer}>
                    <small className={styles.msgDrawerLabel}>平台登记的回执 / 最终结果；完整过程请看绑定线程</small>
                    <pre className={styles.msgFull}>{body}</pre>
                  </div>
                ) : canExpand ? (
                  <button
                    type="button"
                    className={styles.inlineBtn}
                    onClick={() => toggleExpand(msg.id)}
                    title="查看平台保存的回执或最终结果；完整处理过程在绑定线程里"
                  >
                    查看回执 ({body.length} 字)
                  </button>
                ) : null}
                {expanded ? (
                  <button
                    type="button"
                    className={styles.inlineBtn}
                    onClick={() => toggleExpand(msg.id)}
                  >
                    收起
                  </button>
                ) : null}
                {(msg.title || "").includes("Git 回退") ? (
                  <Link
                    href={governanceHref("git", "rollback-request")}
                    className={styles.inlineLinkBtn}
                    title="回到主页面：Git 版本索引与回退登记"
                  >
                    回到 Git 治理
                  </Link>
                ) : null}
                {seatIdentityIds.has(msg.recipient_id || "")
                && ["agent_command", "requirement_dispatch", "comment_message"].includes((msg.message_type || "").toLowerCase())
                && ["queued", "pending", "acked", "in_progress"].includes((msg.status || "").toLowerCase()) ? (
                  <div className={styles.messageInlineActions} aria-label="当前消息处理">
                    {renderRealThreadLauncher(msg, "compact", visible.findIndex((item) => item.id === msg.id) === 0)}
                    <button
                      type="button"
                      className={styles.queueActionBtn}
                      data-danger="1"
                      onClick={() => updateDispatchStatus(msg, "reject")}
                      disabled={queueBusyId !== null}
                      title="写入阻塞/拒绝回执"
                    >
                      {(msg.title || "").includes("Git 回退") ? "阻塞" : "拒绝"}
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })}
          {reviewNote ? <small className={styles.reviewNote}>{reviewNote}</small> : null}
          </>
        )}
      </div>

      <form
        className={styles.composer}
        onSubmit={(e) => {
          e.preventDefault();
          if (!sending) sendCommand();
        }}
      >
        <textarea
          ref={draftRef}
          data-tile-id={seat.id}
          className={styles.composerInput}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`给 ${seat.name} 发指令（Ctrl+Enter 发送）`}
          rows={2}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault();
              if (!sending && draft.trim()) sendCommand();
            }
          }}
        />
        <div className={styles.composerFoot}>
          <small className={styles.composerHint}>
            {occupancyHeldByOther
              ? `⚠ ${occupancy?.user_name || "他人"} 正在占用，先抢占再发送`
              : sendNote || (seat.permissionLevel ? `权限：${seat.permissionLevel} · 详细处理在绑定线程中` : "发送后写入协作池；Codex / Claude Code 线程处理，平台只收最小回执和最终结果")}
          </small>
          <div className={styles.composerActions}>
            <Link href={`/projects/${projectId}/cockpit`} className={styles.linkBtn} title="返回项目驾驶舱">
              驾驶舱
            </Link>
            <button
              type="submit"
              className={styles.sendBtn}
              onMouseDown={(e) => {
                e.preventDefault();
                if (!sending) sendCommand();
              }}
              disabled={sending || !draft.trim() || occupancyHeldByOther}
              title={occupancyHeldByOther ? "他人占用中，请先抢占" : "派发消息"}
            >
              {sending ? "派发中…" : "发送"}
            </button>
          </div>
        </div>
      </form>
    </article>
  );
}
