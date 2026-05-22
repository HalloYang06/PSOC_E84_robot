"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./npc-tile.module.css";
import { apiClientUrl } from "../../../../../lib/api-client-url";
import { launchNpcOneShotThreadProcessing } from "../../../../actions";

type NpcPanelTab = "dialog" | "needs" | "tasks";

export type WorkbenchSeat = {
  id: string;
  rowId?: string;
  configId?: string;
  name: string;
  workstationId: string;
  workstationName: string;
  computerNodeId: string;
  computerNodeName: string;
  runnerWatchState?: string;
  runnerEffectiveStatus?: string;
  runnerDispatchState?: string;
  runnerStateTone?: "ready" | "recent" | "stale" | "offline" | "unknown" | "occupied";
  runnerStateShortLabel?: string;
  runnerStateDetail?: string;
  runnerCanDispatch?: boolean;
  runnerCanQueue?: boolean;
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

function runnerStateToneForCard(
  tone: WorkbenchSeat["runnerStateTone"],
): "ok" | "manual" | "warn" | "danger" {
  if (tone === "ready") return "ok";
  if (tone === "recent" || tone === "occupied") return "manual";
  if (tone === "stale") return "warn";
  return "danger";
}

type DispatchReadiness = {
  mode: "ready" | "queue" | "blocked";
  actionLabel: string;
  stateLabel: string;
  note: string;
};

function dispatchReadinessForSeat(seat: WorkbenchSeat): DispatchReadiness {
  const stateLabel = seat.runnerDispatchState || "状态未知，先检查接入";
  const detail = seat.runnerStateDetail || "";
  if (!seat.providerId) {
    return {
      mode: "blocked",
      actionLabel: "先选通道",
      stateLabel: "待选择执行通道",
      note: "先给这个 NPC 选择执行通道，再继续派单。",
    };
  }
  if (!seat.computerNodeId) {
    return {
      mode: "blocked",
      actionLabel: "先绑电脑",
      stateLabel: "待绑定电脑",
      note: "先绑定目标电脑，平台才能把任务落到固定设备。",
    };
  }
  if (!seat.threadId) {
    return {
      mode: "blocked",
      actionLabel: "先绑线程",
      stateLabel: "待绑定线程",
      note: "先扫描并绑定桌面线程，再启动真实处理。",
    };
  }
  if (seat.runnerCanDispatch) {
    return {
      mode: "ready",
      actionLabel: "派单",
      stateLabel,
      note: detail || "目标电脑正在持续接单，可以直接启动真实处理。",
    };
  }
  if (seat.runnerCanQueue) {
    return {
      mode: "queue",
      actionLabel: "排队",
      stateLabel,
      note: detail || "目标电脑最近在线或等待恢复，任务会排队但不会假装已执行。",
    };
  }
  return {
    mode: "blocked",
    actionLabel: "先接入",
    stateLabel,
    note: detail || "先检查执行通道、目标电脑和桌面线程绑定，再继续派单。",
  };
}

type NpcTileProps = {
  projectId: string;
  apiBaseUrl: string;
  seat: WorkbenchSeat;
  teammates: WorkbenchSeat[];
  crossLeads?: WorkbenchSeat[];
  currentUserId: string;
  currentUserName: string;
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
  task_id?: string | null;
  dispatch_id?: string | null;
  metadata?: Record<string, unknown> | null;
  extra_data?: Record<string, unknown> | null;
};

type StructuredMessageKind =
  | "boundary"
  | "task"
  | "approval"
  | "receipt"
  | "peer-dispatch-status"
  | "tool"
  | "chart"
  | "model"
  | "waveform"
  | "dataset"
  | "device"
  | "git"
  | "risk";

type StructuredMessageCard = {
  kind: StructuredMessageKind;
  title: string;
  summary: string;
  status: string;
  riskLevel: string;
  items: Array<{ label: string; value: string }>;
  metrics: Array<{ label: string; value: string }>;
  actions: Array<{ label: string; status: string }>;
};

type ProfessionalSurface = "data-label" | "chart-lab" | "robotics";

type ProfessionalViewEntry = {
  surface: ProfessionalSurface;
  label: string;
  hint: string;
};

type EvidenceArtifact = {
  label: string;
  path: string;
};

type ArtifactPreviewState = {
  loading?: boolean;
  error?: string;
  path?: string;
  name?: string;
  sizeBytes?: number;
  truncated?: boolean;
  content?: string;
};

const STRUCTURED_MESSAGE_KINDS = new Set<StructuredMessageKind>([
  "boundary",
  "task",
  "approval",
  "receipt",
  "peer-dispatch-status",
  "tool",
  "chart",
  "model",
  "waveform",
  "dataset",
  "device",
  "git",
  "risk",
]);

const STRUCTURED_KIND_LABEL: Record<StructuredMessageKind, string> = {
  boundary: "边界",
  task: "任务",
  approval: "审核",
  receipt: "回执",
  "peer-dispatch-status": "协作",
  tool: "工具",
  chart: "图表",
  model: "模型",
  waveform: "波形",
  dataset: "数据",
  device: "设备",
  git: "Git",
  risk: "风险",
};

const PROFESSIONAL_SURFACE_LABEL: Record<ProfessionalSurface, string> = {
  "data-label": "设备数据工作台",
  "chart-lab": "设备数据工作台",
  robotics: "设备数据工作台",
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
  "codex adapter accepted command",
  "local prompt file",
  "provider cli execution",
  "executor cwd",
  "codex desktop ui delivery failed",
  "platform routing chatter",
];

const NOISE_INFIX = [
  "watcher 心跳",
  "polling inbox",
  "no new messages",
];

function stripPlatformChatter(body: string, desktopVisible = true): string {
  // 隐藏给绑定 Codex/Claude 线程看的平台协议块；用户对话框只保留可读摘要/回执。
  const threadNoun = threadBindingNoun(desktopVisible);
  const deliveryTarget = deliveryNoun(desktopVisible);
  const recordNoun = desktopVisible ? "桌面线程记录" : "执行线程记录";
  const withoutLedger = body.replace(
    /AI_REQUIRED_REQUIREMENT_LEDGER_V1[\s\S]*?AI_REQUIRED_REQUIREMENT_LEDGER_END\s*/g,
    "",
  );
  const normalizedBody = withoutLedger
    .replace(/alias_display_non_authoritative/gi, "历史标识展示规则")
    .replace(/historical[_\s-]*alias(?:[_\s-]*non[_\s-]*authoritative)?/gi, "历史标识")
    .replace(/历史\s*alias/gi, "历史标识")
    .replace(/current\s+alias/gi, "当前标识")
    .replace(/source_thread/gi, `来源${threadNoun}`)
    .replace(/canonical_workstation_id/gi, "正式工位")
    .replace(/requested_workstation_id/gi, "请求工位")
    .replace(/authoritative_([a-z]+_)?seat_id/gi, "正式 NPC")
    .replace(/authoritative_target_seat_id/gi, "目标 NPC")
    .replace(/`?\bmessage_id\s*[:：]\s*[0-9a-f-]{8,}`?/gi, "平台已记录这次回执")
    .replace(/`?\bdispatch_id\s*[:：]\s*[0-9a-f-]{8,}`?/gi, "平台已记录这次派工")
    .replace(/`?\btask_id\s*[:：]\s*[0-9a-f-]{8,}`?/gi, "平台已记录这次任务")
    .replace(/目标\s+NPC\s+已接到平台派单[:：]\s*[0-9a-f-]{8,}/gi, "目标线程已接到平台派单")
    .replace(/(已收到平台派单[:：])\s*[^。\n]*(?:æ|å|ç|è|é|ï|ã)[^。\n]*/gi, "已收到平台派单，正在等待桌面回执")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "关联记录")
    .replace(/sender_id/gi, "发送方")
    .replace(/完整输出可查看本地 artifact[:：]?\s*[^\r\n]+/gi, "完整输出已保存为平台证据，可在工作台点“证据/查看回执”预览。")
    .replace(/artifacts[\\/]workstation-inbox[\\/]?/gi, "平台证据目录")
    .replace(/\.codex[\\/]sessions[\\/]?/gi, recordNoun)
    .replace(/[A-Za-z]:[\\/][^\s"'`<>),\]]*artifacts[\\/][^\s"'`<>),\]]+\.(?:md|txt|log|json|jsonl|yaml|yml)/gi, "平台证据文件")
    .replace(/artifacts[\\/][^\s"'`<>),\]]+\.(?:md|txt|log|json|jsonl|yaml|yml)/gi, "平台证据文件")
    .replace(/Codex Desktop UI 投递/g, desktopVisible ? "桌面后台可接收" : "执行线程可见")
    .replace(/Codex Desktop UI delivery failed:?/gi, `${deliveryTarget}暂未确认收到`)
    .replace(/Codex app-server/gi, "后台线程")
    .replace(/session JSONL/gi, recordNoun)
    .replace(/Local prompt file/gi, "本地任务说明")
    .replace(/Provider CLI/gi, "执行通道")
    .replace(/provider cli execution/gi, "执行通道运行")
    .replace(/\bTask dispatch:/gi, "任务派发：")
    .replace(/\bTask:/gi, "任务：")
    .replace(
      /\bRunner\s+([A-Za-z0-9._-]+)\s+received this dispatch on the execution computer, but Codex Desktop has not confirmed that the bound thread visibly received it\.[^\n]*/gi,
      "执行电脑 $1 已收到派单，但桌面线程还没有确认可见；请保持桌面打开后重新同步。",
    )
    .replace(/执行电脑\s+([^。\n]{1,80}?)\s+执行电脑\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/\bRunner\s+([A-Za-z0-9._-]+)\s+Runner\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/\bRunner\s+([A-Za-z0-9._-]+)\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/The computer connection is reachable;?\s*/gi, "电脑连接可用；")
    .replace(/enable NPC automation/gi, "可开启 NPC 自动推进")
    .replace(/or bind a desktop thread before real execution\.?/gi, desktopVisible ? "或先绑定可见桌面线程再执行。" : "或保持执行电脑在线后再执行。")
    .replace(/执行电脑\s+([A-Za-z0-9._-]+)\s+执行电脑\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/\brunner\b/gi, "执行电脑")
    .replace(/adapter/gi, "同步")
    .replace(/bridge/gi, "同步")
    .replace(/codex-session-[0-9a-z-]+/gi, `绑定${threadNoun}`)
    .replace(/codex-session/gi, threadNoun)
    .replace(/线程\s*codex/gi, threadNoun);
  // 隐藏后端注入的 [路由]/[NPC ...自主发起]/经工位长 X 转交 等元信息行（用户只想看正文）
  const lines = normalizedBody.split(/\r?\n/);
  const filtered = lines.filter((ln) => {
    const t = ln.trim();
    const lower = t.toLowerCase();
    if (!t) return true;
    if (NOISE_PREFIXES.some((prefix) => lower.startsWith(prefix.toLowerCase()))) return false;
    if (t.startsWith("[路由]") || t.startsWith("[Route]")) return false;
    if (t.startsWith("（NPC ") && t.includes("seat-mcp")) return false;
    if (t.startsWith("（本消息由 NPC")) return false;
    if (t.startsWith("[ack]") && t.length < 80) return false;
    if (/^目标\s+NPC\s+已接到平台派单[:：]\s*[0-9a-f-]{8,}/i.test(t)) return false;
    if (/^[A-Z]:\\/.test(t) || /^\/[\w.-]+/.test(t)) return false;
    return true;
  });
  return filtered.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function userFacingCollabText(value: unknown, fallback = "", desktopVisible = true): string {
  const threadNoun = threadBindingNoun(desktopVisible);
  const recordNoun = desktopVisible ? "桌面线程记录" : "执行线程记录";
  const next = stripPlatformChatter(String(value ?? "").trim(), desktopVisible)
    .replace(/alias_display_non_authoritative/gi, "历史标识展示规则")
    .replace(/historical[_\s-]*alias(?:[_\s-]*non[_\s-]*authoritative)?/gi, "历史标识")
    .replace(/历史\s*alias/gi, "历史标识")
    .replace(/current\s+alias/gi, "当前标识")
    .replace(/source_thread/gi, `来源${threadNoun}`)
    .replace(/canonical_workstation_id/gi, "正式工位")
    .replace(/requested_workstation_id/gi, "请求工位")
    .replace(/authoritative_([a-z]+_)?seat_id/gi, "正式 NPC")
    .replace(/authoritative_target_seat_id/gi, "目标 NPC")
    .replace(/`?\bmessage_id\s*[:：]\s*[0-9a-f-]{8,}`?/gi, "平台已记录这次回执")
    .replace(/`?\bdispatch_id\s*[:：]\s*[0-9a-f-]{8,}`?/gi, "平台已记录这次派工")
    .replace(/`?\btask_id\s*[:：]\s*[0-9a-f-]{8,}`?/gi, "平台已记录这次任务")
    .replace(/目标\s+NPC\s+已接到平台派单[:：]\s*[0-9a-f-]{8,}/gi, "目标线程已接到平台派单")
    .replace(/(已收到平台派单[:：])\s*[^。\n]*(?:æ|å|ç|è|é|ï|ã)[^。\n]*/gi, "已收到平台派单，正在等待桌面回执")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "关联记录")
    .replace(/sender_id/gi, "发送方")
    .replace(/完整输出可查看本地 artifact[:：]?\s*[^\r\n]+/gi, "完整输出已保存为平台证据，可在工作台点“证据/查看回执”预览。")
    .replace(/artifacts[\\/]workstation-inbox[\\/]?/gi, "平台证据目录")
    .replace(/\.codex[\\/]sessions[\\/]?/gi, recordNoun)
    .replace(/[A-Za-z]:[\\/][^\s"'`<>),\]]*artifacts[\\/][^\s"'`<>),\]]+\.(?:md|txt|log|json|jsonl|yaml|yml)/gi, "平台证据文件")
    .replace(/artifacts[\\/][^\s"'`<>),\]]+\.(?:md|txt|log|json|jsonl|yaml|yml)/gi, "平台证据文件")
    .replace(/Codex Desktop UI/gi, threadNoun)
    .replace(/Codex app-server/gi, "后台线程")
    .replace(/session JSONL/gi, recordNoun)
    .replace(/Local prompt file/gi, "本地任务说明")
    .replace(/Provider CLI/gi, "执行通道")
    .replace(/provider cli execution/gi, "执行通道运行")
    .replace(/\bTask dispatch:/gi, "任务派发：")
    .replace(/\bTask:/gi, "任务：")
    .replace(
      /\bRunner\s+([A-Za-z0-9._-]+)\s+received this dispatch on the execution computer, but Codex Desktop has not confirmed that the bound thread visibly received it\.[^\n]*/gi,
      "执行电脑 $1 已收到派单，但桌面线程还没有确认可见；请保持桌面打开后重新同步。",
    )
    .replace(/执行电脑\s+([^。\n]{1,80}?)\s+执行电脑\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/\bRunner\s+([A-Za-z0-9._-]+)\s+Runner\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/\bRunner\s+([A-Za-z0-9._-]+)\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/The computer connection is reachable;?\s*/gi, "电脑连接可用；")
    .replace(/enable NPC automation/gi, "可开启 NPC 自动推进")
    .replace(/or bind a desktop thread before real execution\.?/gi, desktopVisible ? "或先绑定可见桌面线程再执行。" : "或保持执行电脑在线后再执行。")
    .replace(/执行电脑\s+([A-Za-z0-9._-]+)\s+执行电脑\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/\brunner\b/gi, "执行电脑")
    .replace(/\badapter\b/gi, "同步")
    .replace(/\bbridge\b/gi, "同步")
    .replace(/执行失败[:：]?/g, "待收口")
    .replace(/hard failed/gi, "待收口")
    .replace(/failed/gi, "待收口")
    .replace(/codex-session-[0-9a-z-]+/gi, `绑定${threadNoun}`)
    .replace(/codex-session/gi, threadNoun)
    .replace(/线程\s*codex/gi, threadNoun)
    .trim();
  return next || fallback;
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

  const title = userFacingCollabText(msg.title || "");
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

type MessageProcessMeta = {
  origin: string;
  target: string;
  process: string;
  signal: string;
};

function desktopSyncLatencyLabel(value: unknown): string {
  const ms = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(ms) || ms < 0) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;
}

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

function finalReceiptPreview(body: string, maxLines = 5): string[] {
  const lines = stripPlatformChatter(body)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^[-*]\s*\[GitHub\]\(/i.test(line));
  const picked: string[] = [];
  const conclusion = lines.filter((line) => {
    const lower = line.toLowerCase();
    return lower.startsWith("understood") || lower.startsWith("blocked") || lower.startsWith("next");
  });
  const changedFiles = lines.filter((line) => {
    const lower = line.toLowerCase();
    return (
      lower.includes("docs/ai-handoffs/")
      || lower.includes("apps/web/")
      || lower.includes("apps/api/")
      || lower.includes("tests/")
      || lower.includes("commit")
      || lower.includes("github.com/")
    );
  });
  const validation = lines.filter((line) => {
    const lower = line.toLowerCase();
    return lower.startsWith("validated") || lower.includes("pytest") || lower.includes("浏览器") || lower.includes("smoke");
  });
  const source = [...conclusion.slice(0, 1), ...changedFiles.slice(0, 3), ...validation.slice(0, 1)];
  const fallback = source.length ? source : lines;
  for (const line of fallback) {
    const compact = line.replace(/\s+/g, " ");
    if (!compact) continue;
    if (picked.includes(compact)) continue;
    picked.push(compact.length > 180 ? `${compact.slice(0, 180)}...` : compact);
    if (picked.length >= maxLines) break;
  }
  return picked;
}

function messageMetadata(msg: CollabMessage): Record<string, unknown> {
  const meta = msg.metadata && typeof msg.metadata === "object" ? msg.metadata : {};
  const extra = msg.extra_data && typeof msg.extra_data === "object" ? msg.extra_data : {};
  return { ...extra, ...meta };
}

function stringValues(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap((item) => stringValues(item));
  if (value && typeof value === "object") return Object.values(value as Record<string, unknown>).flatMap((item) => stringValues(item));
  const next = safeText(value, "");
  return next ? [next] : [];
}

function isGitMessageForSeat(msg: CollabMessage, seatIdentityIds: Set<string>): boolean {
  const meta = messageMetadata(msg);
  const haystack = [
    msg.message_type,
    msg.title,
    meta.source,
    meta.kind,
    meta.git_event,
    meta.git_action,
    meta.git_operation,
    meta.rollback_preview,
    meta.sync_preview,
  ].map((item) => safeText(item, "").toLowerCase()).join(" ");
  if (!/(^|[^a-z])git([^a-z]|$)|github|rollback|回退|提交|分支|pr|pull request|预检|同步/.test(haystack)) {
    return false;
  }
  if (seatIdentityIds.has(msg.sender_id || "") || seatIdentityIds.has(msg.recipient_id || "")) return true;
  const relatedValues = stringValues({
    author_seat_id: meta.author_seat_id,
    seat_id: meta.seat_id,
    npc_id: meta.npc_id,
    target_seat_id: meta.target_seat_id,
    affected_seat_id: meta.affected_seat_id,
    affected_seat_ids: meta.affected_seat_ids,
    reviewer_seat_id: meta.reviewer_seat_id,
    assignee_seat_id: meta.assignee_seat_id,
  });
  return relatedValues.some((value) => seatIdentityIds.has(value));
}

function safeRecord(value: unknown): Record<string, unknown> {
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? parsed as Record<string, unknown>
        : {};
    } catch {
      return {};
    }
  }
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function safeText(value: unknown, fallback = ""): string {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function isHistoricalAliasValue(value: string): boolean {
  return /codex-session|claude-session|session-|thread-|旧|legacy|alias/i.test(value);
}

function seatNameByAuthoritativeRef(
  value: unknown,
  peerByIdentity: Map<string, WorkbenchSeat>,
  fallback = "协作者",
): string {
  const raw = safeText(value, "");
  if (!raw) return fallback;
  const seat = peerByIdentity.get(raw);
  if (seat) return seat.name;
  if (looksInternalIdentifier(raw)) return fallback;
  return isHistoricalAliasValue(raw) ? "历史标识" : userFacingCollabText(raw, fallback);
}

function cleanActorFallback(value: string, fallback: string): string {
  if (looksInternalIdentifier(value)) return fallback;
  const cleaned = userFacingCollabText(value, "").trim();
  if (!cleaned) return fallback;
  if (/^(发起|目标)\s*NPC$/i.test(cleaned)) return fallback;
  if (/^desktop-user$/i.test(cleaned)) return "桌面用户";
  if (looksInternalIdentifier(cleaned)) return fallback;
  return cleaned;
}

function displaySenderName(
  msg: CollabMessage,
  peerByIdentity: Map<string, WorkbenchSeat>,
  fallback = "协作者",
): string {
  const metadata = messageMetadata(msg);
  const authoritative = metadata.authoritative_sender_seat_id
    ?? metadata.authoritative_seat_id
    ?? metadata.delegated_via_seat_id
    ?? msg.sender_id;
  return seatNameByAuthoritativeRef(authoritative, peerByIdentity, fallback);
}

function displayTargetName(
  msg: CollabMessage,
  peerByIdentity: Map<string, WorkbenchSeat>,
  fallback = "当前承接方",
): string {
  const metadata = messageMetadata(msg);
  const authoritative = metadata.authoritative_target_seat_id
    ?? metadata.intended_target_seat_id
    ?? metadata.routed_recipient_seat_id
    ?? metadata.downstream_seat_id
    ?? msg.recipient_id;
  return seatNameByAuthoritativeRef(authoritative, peerByIdentity, fallback);
}

function displayReviewEndpointName(
  value: unknown,
  peerByIdentity: Map<string, WorkbenchSeat>,
  fallback: string,
): string {
  const raw = safeText(value, "");
  if (!raw) return fallback;
  return seatNameByAuthoritativeRef(raw, peerByIdentity, fallback);
}

function displayReceiptEndpointName(
  value: unknown,
  peerByIdentity: Map<string, WorkbenchSeat>,
  currentSeatName: string,
  fallback: string,
): string {
  const raw = safeText(value, "");
  if (!raw) return fallback;
  const seat = peerByIdentity.get(raw) ?? peerByIdentity.get(raw.toLowerCase());
  if (seat?.name) return seat.name;
  if (looksInternalIdentifier(raw) || isHistoricalAliasValue(raw)) return fallback;
  if (raw === currentSeatName) return currentSeatName;
  return userFacingCollabText(raw, fallback);
}

function normalizeStructuredKind(value: unknown): StructuredMessageKind | null {
  const kind = safeText(value, "").toLowerCase().replace(/_/g, "-");
  const normalized = kind === "model3d" || kind === "model-3d"
    ? "model"
    : kind === "data" || kind === "dataset-preview"
      ? "dataset"
      : kind === "wave" || kind === "telemetry-waveform"
        ? "waveform"
      : kind === "approval-risk"
        ? "risk"
        : kind === "boundary-card" || kind === "dispatch-boundary" || kind === "pre-dispatch"
          ? "boundary"
          : kind;
  return STRUCTURED_MESSAGE_KINDS.has(normalized as StructuredMessageKind)
    ? normalized as StructuredMessageKind
    : null;
}

function normalizeStructuredPairs(value: unknown): Array<{ label: string; value: string }> {
  if (Array.isArray(value)) {
    return value
      .map((item, index) => {
        if (item && typeof item === "object") {
          const rec = item as Record<string, unknown>;
          const label = safeText(rec.label ?? rec.name ?? rec.key, `项 ${index + 1}`);
          const val = safeText(rec.value ?? rec.status ?? rec.detail ?? rec.summary, "");
          return val ? { label, value: val } : null;
        }
        const val = safeText(item, "");
        return val ? { label: `项 ${index + 1}`, value: val } : null;
      })
      .filter((item): item is { label: string; value: string } => Boolean(item))
      .slice(0, 6);
  }
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, val]) => ({ label: key, value: safeText(val, "") || JSON.stringify(val) }))
      .filter((item) => item.value && item.value !== undefined)
      .slice(0, 6);
  }
  return [];
}

function collectProfessionalSignals(msg: CollabMessage, card: StructuredMessageCard | null): string {
  const metadata = messageMetadata(msg);
  const payload = safeRecord(metadata.payload_json ?? metadata.payloadJson);
  return [
    msg.title,
    msg.body,
    metadata.object_type,
    metadata.objectType,
    metadata.surface,
    metadata.surface_hint,
    metadata.surfaceHint,
    metadata.category,
    payload.object_type,
    payload.objectType,
    payload.surface,
    payload.surface_hint,
    payload.surfaceHint,
    card?.kind,
    card?.title,
    card?.summary,
    ...card?.items.flatMap((item) => [item.label, item.value]) ?? [],
    ...card?.metrics.flatMap((item) => [item.label, item.value]) ?? [],
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function inferProfessionalViews(msg: CollabMessage, card: StructuredMessageCard | null): ProfessionalViewEntry[] {
  const metadata = messageMetadata(msg);
  const payload = safeRecord(metadata.payload_json ?? metadata.payloadJson);
  const entries = new Map<ProfessionalSurface, ProfessionalViewEntry>();
  const signals = collectProfessionalSignals(msg, card);
  const add = (surface: ProfessionalSurface, hint: string) => {
    if (!entries.has(surface)) {
      entries.set(surface, { surface, label: PROFESSIONAL_SURFACE_LABEL[surface], hint });
    }
  };

  if (card?.kind === "dataset") add("data-label", "打开数据标注");
  if (card?.kind === "chart") add("chart-lab", "打开图表实验");
  if (card?.kind === "waveform") {
    add("data-label", "看时序数据和入库");
    add("robotics", "看现场波形和接口");
  }
  if (card?.kind === "model" || card?.kind === "device") add("robotics", "看模型、设备和现场状态");
  if (card?.kind === "boundary" || card?.kind === "approval" || card?.kind === "risk") {
    add("chart-lab", "看预演、风险和审核条件");
  }

  if (/\b(dataset|sample|manifest|episode|rosbag|bag|audio|image|video|label|schema|imu|telemetry)\b/.test(signals)
    || /数据|样本|质检|标注|入库|版本/.test(signals)) {
    add("data-label", "打开数据标注");
  }
  if (/\b(robot|ros|topic|tf|joint|serial|imu|urdf|gltf|glb|device|sensor)\b/.test(signals)
    || /机器人|现场|模型|传感器|串口|主控板|设备|关节|波形|ros/.test(signals)) {
    add("robotics", "看现场对象和运行态");
  }
  if (/\b(sim|simulation|review|approval|risk|guard|boundary|policy)\b/.test(signals)
    || /仿真|预演|审核|风险|边界|放行|策略/.test(signals)) {
    add("chart-lab", "打开图表实验");
  }

  const preferredSurface = safeText(
    metadata.surface
      ?? metadata.surface_hint
      ?? metadata.surfaceHint
      ?? payload.surface
      ?? payload.surface_hint
      ?? payload.surfaceHint,
    "",
  ).toLowerCase();
  if (preferredSurface.includes("dataset")) add("data-label", "打开数据标注");
  if (preferredSurface.includes("robot")) add("robotics", "看现场对象和运行态");
  if (preferredSurface.includes("lab") || preferredSurface.includes("sim")) add("chart-lab", "打开图表实验");

  return Array.from(entries.values()).slice(0, 3);
}

function normalizeEvidencePath(rawValue: unknown): string | null {
  const value = safeText(rawValue, "").replace(/\\/g, "/").trim();
  if (!value) return null;
  const match = value.match(/(?:^|[A-Za-z]:\/.*?)(artifacts\/[^\s"'`<>),\]]+\.(?:md|txt|log|json|jsonl|yaml|yml))/i)
    || value.match(/(artifacts\/[^\s"'`<>),\]]+\.(?:md|txt|log|json|jsonl|yaml|yml))/i);
  if (!match) return null;
  return match[1].replace(/[,.;:]+$/g, "");
}

function evidenceLabelFromKey(key: string, path: string): string {
  const lowered = `${key} ${path}`.toLowerCase();
  if (lowered.includes("stdout") || lowered.endsWith(".out.log")) return "执行日志";
  if (lowered.includes("stderr") || lowered.endsWith(".err.log")) return "错误日志";
  if (lowered.includes("screenshot")) return "截图记录";
  if (lowered.includes("receipt") || lowered.includes("result")) return "回执文件";
  if (lowered.includes("manifest")) return "清单";
  if (lowered.includes("prompt")) return "提示词";
  return "证据";
}

function userFacingEvidencePath(path: string): string {
  const normalized = safeText(path, "").replace(/\\/g, "/");
  const fileName = normalized.split("/").filter(Boolean).pop() || "证据文件";
  return `平台证据 · ${fileName}`;
}

function extractEvidenceArtifacts(msg: CollabMessage): EvidenceArtifact[] {
  const metadata = messageMetadata(msg);
  const payload = safeRecord(metadata.payload_json ?? metadata.payloadJson);
  const candidates: Array<{ key: string; value: unknown }> = [];
  for (const source of [metadata, payload]) {
    for (const [key, value] of Object.entries(source)) {
      if (/path|artifact|evidence|stdout|stderr|log|manifest|receipt|result/i.test(key)) {
        candidates.push({ key, value });
      }
      if (Array.isArray(value) && /artifacts|evidence|files|logs/i.test(key)) {
        value.forEach((item, index) => candidates.push({ key: `${key}_${index + 1}`, value: item }));
      }
    }
  }
  const textCandidates = [
    msg.body,
    msg.title,
    ...candidates.map((item) => {
      if (typeof item.value === "string") return item.value;
      try {
        return JSON.stringify(item.value);
      } catch {
        return "";
      }
    }),
  ];
  const found: EvidenceArtifact[] = [];
  const seen = new Set<string>();
  for (const item of candidates) {
    const path = normalizeEvidencePath(item.value);
    if (!path || seen.has(path)) continue;
    seen.add(path);
    found.push({ label: evidenceLabelFromKey(item.key, path), path });
  }
  const artifactRegex = /(?:[A-Za-z]:[\\/][^\s"'`<>),\]]*[\\/])?(artifacts[\\/][^\s"'`<>),\]]+\.(?:md|txt|log|json|jsonl|yaml|yml))/gi;
  for (const text of textCandidates) {
    const raw = safeText(text, "");
    let match: RegExpExecArray | null;
    while ((match = artifactRegex.exec(raw)) !== null) {
      const path = normalizeEvidencePath(match[1]);
      if (!path || seen.has(path)) continue;
      seen.add(path);
      found.push({ label: evidenceLabelFromKey("", path), path });
    }
  }
  return found.slice(0, 4);
}

function boundaryCardMetadataFromText(body: string, sourceName: string, targetName: string): Record<string, unknown> | null {
  const cleaned = body.trim();
  if (!/^(边界卡|boundary card|pre-dispatch|派单边界)[:：\s]/i.test(cleaned)) return null;
  const lines = cleaned.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const first = (lines[0] || cleaned).replace(/^(边界卡|boundary card|pre-dispatch|派单边界)[:：\s]*/i, "").trim();
  const itemLines = lines.slice(1).filter((line) => /^[-*•]/.test(line) || /[:：]/.test(line)).slice(0, 5);
  return {
    payload_json: {
      card_kind: "boundary",
      title: first || "派单前边界卡",
      summary: "审批前只允许 NPC 讨论目标、接口、风险和验收；通过后再进入正式执行。",
      risk_level: "需人审",
      items: [
        { label: "发起", value: sourceName },
        { label: "目标", value: targetName },
        ...(itemLines.length
          ? itemLines.map((line, index) => {
              const normalized = line.replace(/^[-*•]\s*/, "");
              const [label, ...rest] = normalized.split(/[:：]/);
              return {
                label: rest.length ? label.trim().slice(0, 18) || `边界 ${index + 1}` : `边界 ${index + 1}`,
                value: (rest.length ? rest.join("：") : normalized).trim().slice(0, 80),
              };
            })
          : [
              { label: "允许", value: "讨论接口、验收、风险、依赖" },
              { label: "禁止", value: "未经审批直接改代码或触碰禁区" },
            ]),
      ],
      actions: [
        { label: "当前", value: "等待人审" },
        { label: "通过后", value: "再创建正式派单" },
      ],
    },
  };
}

function getStructuredMessageCard(msg: CollabMessage): StructuredMessageCard | null {
  const metadata = messageMetadata(msg);
  const payload = safeRecord(metadata.payload_json ?? metadata.payloadJson);
  const kind = normalizeStructuredKind(
    payload.card_kind
      ?? payload.cardKind
      ?? payload.kind
      ?? metadata.card_kind
      ?? metadata.cardKind
      ?? metadata.kind
  );
  if (!kind) return null;
  const status = safeText(msg.status ?? metadata.card_status ?? payload.status, "");
  return {
    kind,
    title: userFacingCollabText(payload.title ?? msg.title, STRUCTURED_KIND_LABEL[kind]),
    summary: userFacingCollabText(payload.summary ?? payload.description ?? metadata.summary ?? "", ""),
    status,
    riskLevel: userFacingCollabText(payload.risk_level ?? payload.riskLevel ?? metadata.risk_level ?? metadata.riskLevel, ""),
    items: normalizeStructuredPairs(payload.items ?? payload.fields ?? payload.links ?? payload.resources).map((item) => ({
      label: userFacingCollabText(item.label),
      value: userFacingCollabText(item.value),
    })),
    metrics: normalizeStructuredPairs(payload.metrics ?? payload.stats).map((item) => ({
      label: userFacingCollabText(item.label),
      value: userFacingCollabText(item.value),
    })),
    actions: normalizeStructuredPairs(payload.actions).map((item) => ({
      label: userFacingCollabText(item.label),
      status: userFacingCollabText(item.value),
    })),
  };
}

function isPreDispatchBoundaryMessage(msg: CollabMessage | null): boolean {
  if (!msg) return false;
  const metadata = messageMetadata(msg);
  if (metadata.pre_dispatch_gate === true) return true;
  const payload = safeRecord(metadata.payload_json ?? metadata.payloadJson);
  return normalizeStructuredKind(
    payload.card_kind
      ?? payload.cardKind
      ?? payload.kind
      ?? metadata.card_kind
      ?? metadata.cardKind
      ?? metadata.kind
  ) === "boundary";
}

function shouldRenderAsReviewMessage(msg: CollabMessage | null): boolean {
  if (!msg || (msg.status || "").toLowerCase() !== "pending_review") return false;
  if (isPreDispatchBoundaryMessage(msg)) return true;
  const senderType = safeText(msg.sender_type, "").toLowerCase();
  const type = safeText(msg.message_type, "").toLowerCase();
  const body = String(msg.body || "");
  const source = body.match(/来源：([a-z_]+)/)?.[1] || safeText(messageMetadata(msg).route_review_source, "").toLowerCase();
  if (source === "hardware_risk") return true;
  return senderType === "agent" && ["requirement_dispatch", "agent_command", "comment_message"].includes(type);
}

function withSeatReturnParam(path: string, seatId: string): string {
  const [base, query = ""] = path.split("?");
  const params = new URLSearchParams(query);
  params.set("seat", seatId);
  return `${base}?${params.toString()}`;
}

function humanizeDispatchCardStatus(status: string): string {
  const normalized = safeText(status, "").toLowerCase();
  if (normalized === "pending_closeout") return "待收口";
  if (normalized === "finaled") return "已收 final";
  if (normalized === "acked") return "已收最小回执";
  if (normalized === "delivered") return "等待目标回执";
  if (normalized === "blocked") return "已阻塞";
  if (normalized === "queued") return "等待发送";
  if (normalized === "next_ready") return "可继续";
  return safeText(status, "处理中");
}

function renderStructuredMessageCard(card: StructuredMessageCard) {
  const primaryPairs = [...card.metrics, ...card.items].slice(0, 6);
  return (
    <div className={styles.structuredCard} data-card-kind={card.kind} data-card-status={card.status}>
      <div className={styles.structuredCardHead}>
        <span>{STRUCTURED_KIND_LABEL[card.kind]}</span>
        {card.status ? <small>{humanizeDispatchCardStatus(card.status)}</small> : null}
        {card.riskLevel ? <small data-risk="1">{card.riskLevel}</small> : null}
      </div>
      <strong>{card.title}</strong>
      {card.summary ? <p>{card.summary}</p> : null}
      {primaryPairs.length ? (
        <dl className={styles.structuredCardGrid}>
          {primaryPairs.map((item, index) => (
            <div key={`${card.kind}-${item.label}-${index}`}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {card.actions.length ? (
        <div className={styles.structuredActionRow}>
          {card.actions.slice(0, 4).map((action, index) => (
            <span key={`${card.kind}-action-${action.label}-${index}`}>
              {action.label}{action.status ? ` · ${action.status}` : ""}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function relatedSourceMessageId(msg: CollabMessage): string {
  const metadata = messageMetadata(msg);
  return safeText(metadata.source_message_id ?? metadata.sourceMessageId, "");
}

function messageCompletesSource(msg: CollabMessage, sourceId: string): boolean {
  if (!sourceId) return false;
  const status = safeText(msg.status, "").toLowerCase();
  if (!["completed", "done", "delivered", "finaled"].includes(status) && !isFinalReceipt(msg)) return false;
  if (relatedSourceMessageId(msg) === sourceId) return true;
  return safeText(msg.dispatch_id, "") === sourceId || safeText(msg.task_id, "") === sourceId;
}

function sourceHasFinalReceipt(messages: CollabMessage[] | null | undefined, sourceId: string): boolean {
  if (!sourceId) return false;
  return (messages || []).some((item) => messageCompletesSource(item, sourceId));
}

function dialogChainKey(msg: CollabMessage): string {
  const metadata = messageMetadata(msg);
  const type = safeText(msg.message_type, "").toLowerCase();
  if (["agent_command", "requirement_dispatch", "comment_message"].includes(type)) {
    return safeText(msg.id, "");
  }
  return safeText(
    metadata.source_message_id
      ?? metadata.sourceMessageId
      ?? msg.dispatch_id
      ?? msg.task_id,
    "",
  );
}

function dialogDedupeKey(msg: CollabMessage): string {
  const created = msg.created_at ? new Date(msg.created_at) : null;
  const minute = created && !Number.isNaN(created.getTime())
    ? Math.floor(created.getTime() / 60000)
    : "";
  const headline = userFacingCollabText(msg.title || "", "");
  const firstLine = firstUsefulLine(stripPlatformChatter(msg.body || ""));
  return [
    safeText(msg.message_type, "").toLowerCase(),
    safeText(msg.status, "").toLowerCase(),
    safeText(msg.sender_type, "").toLowerCase(),
    safeText(msg.sender_id, "").toLowerCase(),
    safeText(msg.recipient_id, "").toLowerCase(),
    headline,
    firstLine.slice(0, 160),
    minute,
  ].join("|");
}

function isIntermediateReceipt(msg: CollabMessage): boolean {
  const type = safeText(msg.message_type, "").toLowerCase();
  const status = safeText(msg.status, "").toLowerCase();
  const metadata = messageMetadata(msg);
  const progressState = safeText(metadata.progress_state, "").toLowerCase();
  if (isFinalReceipt(msg)) return true;
  return status === "acked"
    || status === "in_progress"
    || type.includes("ack")
    || type.includes("progress")
    || progressState === "awaiting_desktop_reply"
    || progressState === "delivery_pending_confirmation";
}

function isFinalReceipt(msg: CollabMessage): boolean {
  const type = safeText(msg.message_type, "").toLowerCase();
  const status = safeText(msg.status, "").toLowerCase();
  return ["completed", "done", "finaled"].includes(status)
    || type.includes("final")
    || type.includes("result");
}

function looksInternalIdentifier(value: string): boolean {
  const raw = value.trim();
  return /^platform-npc-\d+$/i.test(raw)
    || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)
    || /^agent-[0-9a-f-]+$/i.test(raw);
}

function processActorLabel(value: string, peerByIdentity: Map<string, WorkbenchSeat>, fallback: string): string {
  const raw = safeText(value, "");
  if (!raw) return fallback;
  const peer = peerByIdentity.get(raw) ?? peerByIdentity.get(raw.toLowerCase());
  if (peer?.name) return peer.name;
  return cleanActorFallback(raw, fallback);
}

function messageTypeLabel(msg: CollabMessage): string {
  const type = safeText(msg.message_type, "").toLowerCase();
  if (type === "desktop_user_question") return "桌面提问";
  if (type === "desktop_minimal_receipt") return "最小回执";
  if (type === "requirement_dispatch") return "NPC 派工";
  if (type === "agent_command") return "用户派工";
  if (type.includes("progress")) return "过程回执";
  if (type.includes("final") || type.includes("result")) return "最终回执";
  if (type.includes("ack")) return "接单回执";
  if (type.includes("review")) return "人工审核";
  if (type.includes("comment")) return "协作消息";
  return "协作消息";
}

function threadBindingLabel(seat: WorkbenchSeat): string {
  if (seat.desktopVisible) return seat.threadId ? "桌面线程已绑定" : "待绑定桌面线程";
  return seat.threadId ? "执行线程已绑定" : "待绑定执行线程";
}

function threadBindingHint(seat: WorkbenchSeat): string {
  if (seat.desktopVisible) return "桌面线程在主页面 NPC 管理中绑定；这里显示当前协作状态。";
  return "执行线程在主页面 NPC 管理中绑定；Linux/插件/CLI 场景通过执行电脑队列回写回执。";
}

function threadBindingNoun(seatOrDesktopVisible: WorkbenchSeat | boolean): string {
  const desktopVisible = typeof seatOrDesktopVisible === "boolean" ? seatOrDesktopVisible : seatOrDesktopVisible.desktopVisible;
  return desktopVisible ? "桌面线程" : "执行线程";
}

function deliveryNoun(seatOrDesktopVisible: WorkbenchSeat | boolean): string {
  const desktopVisible = typeof seatOrDesktopVisible === "boolean" ? seatOrDesktopVisible : seatOrDesktopVisible.desktopVisible;
  return desktopVisible ? "桌面线程" : "执行电脑队列";
}

function processTraceHint(seatOrDesktopVisible: WorkbenchSeat | boolean): string {
  const desktopVisible = typeof seatOrDesktopVisible === "boolean" ? seatOrDesktopVisible : seatOrDesktopVisible.desktopVisible;
  return desktopVisible ? "不会抢占当前窗口；用户打开绑定桌面线程后可追踪详细过程。" : "执行过程以回执形式回到当前 NPC 瓷砖。";
}

function processSignalLabel(value: string): string {
  const normalized = safeText(value, "").toLowerCase();
  if (!normalized) return "";
  if (normalized === "awaiting_desktop_pickup") return "等待桌面接收";
  if (normalized === "awaiting_desktop_reply") return "等待桌面回执";
  if (normalized === "desktop_delivery_unconfirmed") return "桌面未确认收到";
  if (normalized === "delivery_pending_confirmation") return "等待送达确认";
  if (normalized === "desktop_final_sync_lag") return "最终回执待同步";
  if (normalized === "desktop_retry_action") return "重新同步中";
  if (looksInternalIdentifier(normalized)) return "关联消息";
  return userFacingCollabText(normalized, "协作信号");
}

function reviewSourceLabel(value: string): string {
  const normalized = safeText(value, "").toLowerCase();
  if (!normalized) return "";
  if (normalized === "hardware_risk") return "硬件强审";
  if (normalized === "cross_workstation") return "跨工位审核";
  if (normalized === "boundary_card") return "边界卡";
  if (normalized === "human_review") return "人工审核";
  return userFacingCollabText(normalized.replace(/_/g, " "), "审核策略");
}

function messageProcessMeta(
  msg: CollabMessage,
  role: RoleTrack,
  senderLabel: string,
  peerByIdentity: Map<string, WorkbenchSeat>,
  seatName: string,
  refined: RefinedMessage,
): MessageProcessMeta {
  const metadata = messageMetadata(msg);
  const senderRaw = role === "human"
    ? "用户"
    : role === "self"
      ? seatName
      : senderLabel.replace(/^(同工位|跨工位|本 NPC|同步线程|系统)\s*·?\s*/, "") || senderLabel;
  const sender = processActorLabel(senderRaw, peerByIdentity, role === "watcher" ? "执行线程" : "协作者");
  const targetRaw = safeText(
    metadata.authoritative_target_seat_id
      ?? metadata.intended_target_seat_id
      ?? metadata.routed_recipient_seat_id
      ?? metadata.downstream_seat_id
      ?? msg.recipient_id,
    "",
  );
  const target = targetRaw
    ? processActorLabel(targetRaw, peerByIdentity, seatName || "当前承接方")
    : role === "self"
      ? "用户 / 平台"
      : seatName;
  const typeLabel = messageTypeLabel(msg);
  const status = refined.statusLabel;
  const dispatchId = safeText(msg.dispatch_id, "");
  const taskId = safeText(msg.task_id, "");
  const sourceId = safeText(metadata.source_message_id ?? metadata.sourceMessageId, "");
  const idLabel = dispatchId || taskId || sourceId ? "关联当前派工" : "当前对话";
  const signal = desktopSyncLatencyLabel(metadata.desktop_sync_latency_ms)
    || processSignalLabel(safeText(metadata.progress_state, ""))
    || processSignalLabel(safeText(metadata.launch_state, ""))
    || idLabel;
  return {
    origin: sender,
    target,
    process: `${typeLabel} · ${status}`,
    signal,
  };
}

function textArrayFromMetadata(...values: unknown[]): string[] {
  const out: string[] = [];
  const push = (value: unknown) => {
    if (Array.isArray(value)) {
      for (const item of value) push(item);
      return;
    }
    const text = userFacingCollabText(value, "");
    if (!text) return;
    for (const part of text.split(/[,，、\n]/)) {
      const clean = userFacingCollabText(part, "");
      if (clean && !out.includes(clean)) out.push(clean);
    }
  };
  values.forEach(push);
  return out.slice(0, 6);
}

function buildConversationCollabCard(
  msg: CollabMessage,
  peerByIdentity: Map<string, WorkbenchSeat>,
  seatName: string,
): StructuredMessageCard | null {
  const metadata = messageMetadata(msg);
  const type = safeText(msg.message_type, "").toLowerCase();
  const senderType = safeText(msg.sender_type, "").toLowerCase();
  const isDispatch = type === "requirement_dispatch" || type === "agent_command" || type === "comment_message";
  const isResult = type.includes("result") || type.includes("final") || type.includes("ack") || type.includes("progress");
  const isSelfStatusReceipt = senderType === "agent"
    && (isResult || type === "desktop_minimal_receipt")
    && safeText(msg.sender_id, "") === safeText(msg.recipient_id, "");
  const hasCollabHints = Boolean(
    metadata.recommended_skills
      || metadata.required_skills
      || metadata.skills
      || metadata.knowledge_paths
      || metadata.repo_paths
      || metadata.boss_name
      || metadata.goal
      || metadata.role
      || metadata.source === "boss_npc_project_generator"
      || metadata.source === "codex-user-orchestrator"
      || senderType === "agent",
  );
  if (isSelfStatusReceipt) return null;
  if (!hasCollabHints || (!isDispatch && !isResult)) return null;

  const targetSeatId = safeText(
    metadata.authoritative_target_seat_id
      ?? metadata.intended_target_seat_id
      ?? metadata.downstream_seat_id
      ?? metadata.routed_recipient_seat_id
      ?? msg.recipient_id,
    "",
  );
  const targetName = processActorLabel(
    safeText(metadata.intended_target_name ?? metadata.routed_recipient_name ?? targetSeatId, ""),
    peerByIdentity,
    seatName || "当前承接方",
  );
  const senderName = processActorLabel(
    safeText(metadata.upstream_seat_id ?? metadata.delegated_via_seat_id ?? metadata.claimed_sender_agent_id ?? msg.sender_id, ""),
    peerByIdentity,
    senderType === "human" ? "用户" : seatName || "当前协作方",
  );
  const skills = textArrayFromMetadata(metadata.recommended_skills, metadata.required_skills, metadata.skills);
  const knowledge = textArrayFromMetadata(metadata.knowledge_paths, metadata.repo_paths, metadata.repoPaths);
  const source = userFacingCollabText(metadata.source, "");
  const goal = userFacingCollabText(metadata.goal, "");
  const role = userFacingCollabText(metadata.role, "");
  const routeReason = userFacingCollabText(metadata.route_review_reason, "");
  const roleLabel = cleanActorFallback(role, isResult ? "按回执结果验收" : "按任务说明执行");
  const capabilityLabel = skills.length ? skills.join(" / ") : "使用已绑定能力";
  const knowledgeLabel = knowledge.length ? knowledge.join(" / ") : "项目知识库与当前证据链";
  const status = normalizeDispatchState(safeText(msg.status, ""));
  const title = safeText(msg.title, isResult ? "协作回执" : "协作派单");

  return {
    kind: "peer-dispatch-status",
    title,
    summary: `${senderName} -> ${targetName}${roleLabel ? ` · ${roleLabel}` : ""}`,
    status,
    riskLevel: userFacingCollabText(metadata.risk_level ?? metadata.riskLevel, ""),
    items: [
      { label: "发起方", value: senderName },
      { label: "目标", value: targetName },
      { label: "职责", value: roleLabel },
      { label: "能力", value: capabilityLabel },
      { label: "知识", value: knowledgeLabel },
      { label: "验收", value: goal || routeReason || (isResult ? "看 final 和证据链" : "等待最小回执 / final") },
    ],
    metrics: [
      { label: "来源", value: source || (senderType === "agent" ? "NPC 协作" : "用户派工") },
      { label: "下一步", value: isResult ? "看回执" : "等接单" },
    ],
    actions: [
      { label: "对话", status: "当前卡片" },
      { label: "能力", status: skills.length ? `${skills.length} 个` : "已绑定" },
      { label: "知识", status: knowledge.length ? `${knowledge.length} 条` : "项目默认" },
      { label: "验收", status: isResult ? "final" : "等待" },
    ],
  };
}

function normalizeDispatchState(value: string): "queued" | "delivered" | "acked" | "blocked" | "finaled" | "next_ready" | "pending_closeout" {
  const normalized = value.toLowerCase();
  if (["failed", "rejected", "blocked"].includes(normalized)) return "blocked";
  if (["completed", "done", "delivered"].includes(normalized)) return "finaled";
  if (["acked"].includes(normalized) || normalized.includes("ack")) return "acked";
  if (["in_progress", "running", "active"].includes(normalized)) return "delivered";
  if (["next_ready", "ready_for_next"].includes(normalized)) return "next_ready";
  return "queued";
}

function buildPeerDispatchStatusCard(
  msg: CollabMessage,
  allMessages: CollabMessage[],
  seatName: string,
  peerByIdentity: Map<string, WorkbenchSeat>,
): StructuredMessageCard | null {
  const type = safeText(msg.message_type, "").toLowerCase();
  const senderType = safeText(msg.sender_type, "").toLowerCase();
  if (type !== "requirement_dispatch" || senderType !== "agent") return null;

  const metadata = messageMetadata(msg);
  const sourceId = msg.id;
  const sourceDispatchId = safeText(msg.dispatch_id, "");
  const linked = allMessages.filter((item) => {
    if (item.id === sourceId) return false;
    const itemSourceId = relatedSourceMessageId(item);
    if (itemSourceId && itemSourceId === sourceId) return true;
    if (sourceDispatchId && safeText(item.dispatch_id, "") === sourceDispatchId) return true;
    return false;
  });

  const targetSeatId = safeText(
    metadata.authoritative_target_seat_id
      ?? metadata.intended_target_seat_id
      ?? metadata.downstream_seat_id
      ?? metadata.routed_recipient_seat_id
      ?? msg.recipient_id,
    "",
  );
  const targetSeatName = seatNameByAuthoritativeRef(
    targetSeatId,
    peerByIdentity,
    cleanActorFallback(safeText(metadata.intended_target_name ?? metadata.routed_recipient_name, ""), seatName || "当前承接方"),
  );
  const latestAck = linked
    .filter((item) => {
      const status = safeText(item.status, "").toLowerCase();
      const itemType = safeText(item.message_type, "").toLowerCase();
      return status === "acked" || itemType.includes("ack");
    })
    .sort((a, b) => safeText(b.created_at, "").localeCompare(safeText(a.created_at, "")))[0] || null;
  const latestBlocked = linked
    .filter((item) => {
      const status = safeText(item.status, "").toLowerCase();
      return ["failed", "rejected", "blocked"].includes(status);
    })
    .sort((a, b) => safeText(b.created_at, "").localeCompare(safeText(a.created_at, "")))[0] || null;
  const blockedTaxonomy = safeRecord(messageMetadata(latestBlocked ?? msg).blocked_taxonomy);
  const blockedReasonCode = safeText(
    blockedTaxonomy.blocked_reason_code
      ?? blockedTaxonomy.exception_kind
      ?? messageMetadata(latestBlocked ?? msg).blocked_reason_code,
    "",
  );
  const blockedReasonLabel = safeText(
    blockedTaxonomy.blocked_reason_label
      ?? blockedTaxonomy.exception_kind
      ?? messageMetadata(latestBlocked ?? msg).blocked_reason_label,
    "",
  );
  const platformDefect = Boolean(
    blockedTaxonomy.platform_defect || messageMetadata(latestBlocked ?? msg).platform_defect,
  );
  const nudgeRequired = Boolean(
    blockedTaxonomy.nudge_required || messageMetadata(latestBlocked ?? msg).nudge_required,
  );
  const waitExtensionAvailable = Boolean(
    blockedTaxonomy.wait_extension_available || messageMetadata(latestBlocked ?? msg).wait_extension_available,
  );
  const manualCloseRequired = Boolean(
    blockedTaxonomy.manual_close_required || messageMetadata(latestBlocked ?? msg).manual_close_required,
  );
  const pendingCloseout = blockedReasonCode === "desktop_final_sync_lag"
    || platformDefect
    || nudgeRequired
    || waitExtensionAvailable
    || manualCloseRequired;
  const latestFinal = linked
    .filter((item) => {
      const status = safeText(item.status, "").toLowerCase();
      const itemType = safeText(item.message_type, "").toLowerCase();
      return ["completed", "done", "delivered"].includes(status) || itemType.includes("result") || itemType.includes("final");
    })
    .sort((a, b) => safeText(b.created_at, "").localeCompare(safeText(a.created_at, "")))[0] || null;

  let currentState: StructuredMessageCard["status"] = "queued";
  if (pendingCloseout) currentState = "pending_closeout";
  else if (latestBlocked) currentState = "blocked";
  else if (latestFinal) currentState = "finaled";
  else if (latestAck) currentState = "acked";
  else if (safeText(msg.status, "").toLowerCase() === "in_progress") currentState = "delivered";

  const blockedReason = blockedReasonLabel || (latestBlocked ? firstUsefulLine(stripPlatformChatter(latestBlocked.body || "")) : "");
  const finalPreview = latestFinal ? firstUsefulLine(stripPlatformChatter(latestFinal.body || "")) : "";
  const nextAction =
    currentState === "pending_closeout"
      ? "待收口"
      : currentState === "blocked"
      ? "看阻塞"
      : currentState === "finaled"
        ? "看 final"
        : currentState === "acked"
          ? "继续下一步"
          : "看状态";

  return {
    kind: "peer-dispatch-status",
    title: safeText(msg.title, "免审协作派单"),
    summary: `${displaySenderName(msg, peerByIdentity, seatName)} -> ${targetSeatName}`,
    status: currentState,
    riskLevel: "",
    items: [
      { label: "目标", value: targetSeatName },
      { label: "当前状态", value: humanizeDispatchCardStatus(currentState) },
      { label: "最小回执", value: latestAck ? "已收到" : "等待中" },
      { label: "Final", value: latestFinal ? "已同步" : pendingCloseout ? "待收口" : "未收到" },
      { label: "当前卡点", value: blockedReason || (pendingCloseout ? "等待最终收口" : "无") },
      {
        label: "系统状态",
        value: pendingCloseout
          ? "待收口"
          : platformDefect
            ? "需要处理"
            : "正常推进",
      },
    ],
    metrics: [
      { label: "关联消息", value: String(linked.length) },
      { label: "下一步", value: nextAction },
    ],
    actions: [
      { label: "看状态", status: humanizeDispatchCardStatus(currentState) },
      {
        label: "看阻塞",
        status: pendingCloseout
          ? "待收口"
          : blockedReason
            ? "有"
            : "无",
      },
      { label: "看 final", status: latestFinal ? "已同步" : pendingCloseout ? "待收口" : "等待" },
      {
        label: "继续下一步",
        status: pendingCloseout
          ? [
              nudgeRequired ? "催办" : "",
              waitExtensionAvailable ? "延长等待" : "",
              "重新同步",
              manualCloseRequired ? "手动收口" : "",
            ].filter(Boolean).join(" / ") || "待收口"
          : currentState === "acked" || currentState === "finaled"
            ? "可继续"
            : "稍后",
      },
    ],
  };
}

function summarizeCollabMessage(msg: CollabMessage, desktopVisible = true): RefinedMessage {
  const classified = classifyMessage(msg);
  const structuredCard = getStructuredMessageCard(msg);
  const type = (msg.message_type || "").toLowerCase();
  const status = (msg.status || "").toLowerCase();
  const rawBody = msg.body || "";
  const cleanBody = stripPlatformChatter(rawBody, desktopVisible);
  const rawLower = rawBody.toLowerCase();
  const cleanFirst = firstUsefulLine(cleanBody);
  const title = userFacingCollabText((msg.title || "").trim(), "", desktopVisible);
  const meta = messageMetadata(msg);
  const isDesktopQuestion = type === "desktop_user_question";
  const isDesktopReceipt = type === "desktop_minimal_receipt";
  const isDesktopSync = isDesktopQuestion || isDesktopReceipt || meta.desktop_sync === true;
  const desktopLatency = desktopSyncLatencyLabel(meta.desktop_sync_latency_ms);
  const blockedTaxonomy = safeRecord(meta.blocked_taxonomy);
  const blockedReasonCode = safeText(
    blockedTaxonomy.blocked_reason_code ?? blockedTaxonomy.exception_kind ?? meta.progress_state,
    "",
  ).toLowerCase();
  const desktopCloseoutWaiting = Boolean(
    blockedTaxonomy.desktop_closeout_waiting
      || meta.desktop_closeout_waiting
      || meta.needs_manual_closeout,
  )
    || blockedReasonCode === "desktop_final_sync_lag"
    || blockedReasonCode === "desktop_delivery_unconfirmed";
  const isWatcher = (msg.sender_type || "").toLowerCase() === "runner"
    || (msg.sender_type || "").toLowerCase() === "watcher"
    || type.includes("watcher")
    || rawLower.startsWith("watcher");
  const threadNoun = threadBindingNoun(desktopVisible);
  const deliveryTarget = deliveryNoun(desktopVisible);
  const statusLabel =
    isDesktopQuestion
      ? `${threadNoun}提问`
      : isDesktopReceipt
        ? "最小回执"
        : status === "pending_review"
        ? "需人审"
        : desktopCloseoutWaiting
          ? "待收口"
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
    (isDesktopQuestion ? `${threadNoun}提问` : "")
    || (isDesktopReceipt ? "最小回执" : "")
    || title
    || (statusLabel === "已接单" ? "目标线程已接单" : "")
    || (statusLabel === "已完成" ? "目标线程已回执" : "")
    || userFacingCollabText(cleanFirst, "", desktopVisible).slice(0, 96)
    || "(空消息)";

  let detail = cleanFirst && cleanFirst !== headline ? userFacingCollabText(cleanFirst, "", desktopVisible) : "";
  if (!detail) {
    if (isDesktopQuestion) detail = cleanFirst || `用户在${threadNoun}里补充了问题，已同步到平台对话流。`;
    else if (isDesktopReceipt) detail = cleanFirst || `${threadNoun}已返回最小回执，最终结果仍按任务回执收口。`;
    else if (statusLabel === "派单") detail = `已写入协作消息池，等待平台送达绑定${deliveryTarget}。`;
    else if (statusLabel === "已接单") detail = `目标${threadNoun}已接到指令；${processTraceHint(desktopVisible)}`;
    else if (statusLabel === "处理中") detail = `绑定${threadNoun}正在推进；平台同步提问、最小回执和最终结果。`;
    else if (statusLabel === "待收口") detail = `${threadNoun}可能仍在处理；请催办、延长等待，或确认结果后手动收口。`;
    else if (statusLabel === "需人审") detail = "需要人类成员查看正文后决定是否放行。";
    else if (statusLabel === "已完成") detail = `${threadNoun}已返回最终结果；${processTraceHint(desktopVisible)}`;
    else if (statusLabel === "异常") detail = "线程同步报告异常，展开可查看收口信息。";
    else detail = "协作事件已记录。";
  }
  const progressState = String(meta.progress_state || "");
  const launchState = String(meta.launch_state || "");
  if (progressState === "awaiting_desktop_reply") {
    detail = `已确认进入目标${deliveryTarget}，正在等待最终回执。`;
  } else if (progressState === "awaiting_desktop_pickup") {
    detail = "已创建桌面版后台自动化请求，正在等待绑定桌面线程接收；不会抢占当前窗口。";
  } else if (progressState === "desktop_delivery_unconfirmed") {
    const retryCount = safeText(meta.desktop_delivery_attempts ?? blockedTaxonomy.desktop_delivery_attempts, "");
    detail = retryCount
      ? `${threadNoun}暂未确认收到，平台已自动重试 ${retryCount} 次；可继续重新同步、延长等待或手动收口。`
      : `${threadNoun}暂未确认收到，平台会自动重试；可重新同步、延长等待或手动收口。`;
  } else if (launchState === "delivery_pending_confirmation") {
    detail = `平台已启动送达流程，正在确认目标${deliveryTarget}是否收到这条消息。`;
  }
  detail = userFacingCollabText(detail, "", desktopVisible);
  if (detail.length > 120) detail = `${detail.slice(0, 120)}...`;
  if (isDesktopSync && desktopLatency) {
    detail = detail ? `${detail} · 同步 ${desktopLatency}` : `同步 ${desktopLatency}`;
  }

  const showByDefault = Boolean(structuredCard) || !isWatcher || IMPORTANT_WATCHER_TYPES.has(type) || ["failed", "rejected", "completed", "done"].includes(status);
  return {
    kind: isDesktopReceipt ? "result" : isDesktopQuestion ? "command" : classified.kind,
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

  if (type === "desktop_user_question") return { role: "human", label: "桌面用户" };
  if (type === "desktop_minimal_receipt") return { role: "self", label: "桌面线程" };
  if (senderType === "human") return { role: "human", label: "用户" };
  if (senderType === "runner" || senderType === "watcher" || type.includes("watcher") || type.includes("heartbeat") || body.startsWith("watcher")) {
    return { role: "watcher", label: "线程同步" };
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

export function NpcTile({ projectId, apiBaseUrl, seat, teammates, crossLeads = [], currentUserId, currentUserName, onOpenTeammate, sourcePath, onClose }: NpcTileProps) {
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
  const [artifactPreviews, setArtifactPreviews] = useState<Record<string, ArtifactPreviewState>>({});
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
  const [automationEnabled, setAutomationEnabled] = useState(seat.automationEnabled);
  const [automationBusy, setAutomationBusy] = useState(false);
  const [automationNote, setAutomationNote] = useState<string | null>(null);
  const [activePanelTab, setActivePanelTab] = useState<NpcPanelTab>("dialog");
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
    my_needs?: { items: SeatQueueItem[]; count: number };
    my_tasks?: { items: SeatQueueItem[]; count: number };
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
  const [queueTab, setQueueTab] = useState<"needs" | "tasks" | "dispatch">("dispatch");
  const [receiptDirection, setReceiptDirection] = useState<"incoming" | "outgoing">("incoming");
  const [queueBusyId, setQueueBusyId] = useState<string | null>(null);
  const [archiveBusyId, setArchiveBusyId] = useState<string | null>(null);
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

  async function toggleAutomation(nextEnabled: boolean) {
    setAutomationBusy(true);
    setAutomationNote(null);
    try {
      const nextHealth = nextEnabled
        ? (seat.threadHealth || "automation requested")
        : "automation paused";
      const nextMetadata = {
        ...(seat.metadata ?? {}),
        automation_enabled: nextEnabled,
        automation_mode: nextEnabled ? "thread_watcher" : "manual",
        automation_provider: seat.providerId || seat.providerLabel || seat.threadKind || "thread",
        automation_thread_id: seat.threadId || "",
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

  const governanceReturnTo = sourcePath || `/projects/${projectId}/workbench`;
  const governanceSource = governanceReturnTo.includes("/company") ? "company" : "workbench";
  const canUseDesktopAutomation = Boolean(seat.threadId && (seat.desktopVisible || seat.desktopThreadUrl));
  const governanceHref = useCallback(
    (panel: string, action?: string) => {
      const params = new URLSearchParams({ panel, return_to: governanceReturnTo, from: governanceSource });
      if (action) params.set("action", action);
      if (panel === "skills" || panel === "git") {
        return `/projects/${projectId}/skill-forge?${params.toString()}`;
      }
      return `/projects/${projectId}/2d-upgrade?${params.toString()}`;
    },
    [governanceReturnTo, governanceSource, projectId],
  );
  const professionalViewHref = useCallback(
    (surface: ProfessionalSurface, msg: CollabMessage) => {
      const params = new URLSearchParams({ return_to: governanceReturnTo, from: governanceSource, focus: "message" });
      if (surface === "data-label") params.set("tab", "data");
      if (surface === "chart-lab") params.set("tab", "chart");
      if (surface === "robotics") params.set("tab", "terminal");
      params.set("message_id", msg.id);
      if (msg.task_id) params.set("task_id", msg.task_id);
      if (msg.dispatch_id) params.set("dispatch_id", msg.dispatch_id);
      params.set("source_seat", seatApiId);
      params.set("source_label", seat.name || seatApiId);
      if (msg.title) params.set("source_title", msg.title.slice(0, 120));
      return `/projects/${projectId}/robotics?${params.toString()}`;
    },
    [governanceReturnTo, governanceSource, projectId, seat.name, seatApiId],
  );

  function renderRealThreadLauncher(message: CollabMessage, variant: "compact" | "inline" = "inline", isPrimary = true) {
    const status = (message.status || "").toLowerCase();
    const type = (message.message_type || "").toLowerCase();
    const isExecutableCommand = ["agent_command", "requirement_dispatch", "comment_message"].includes(type);
    if (!isExecutableCommand) return null;
    const runnable = ["queued", "pending", "acked", "in_progress"].includes(status);
    if (!runnable) return null;
    const launchMessage = async () => {
      await launchQueuedMessage(message, "button");
    };
    return (
      <div
        className={variant === "compact" ? styles.realThreadMiniForm : styles.realThreadForm}
      >
        <button
          type="button"
          className={styles.realThreadBtn}
          data-secondary={!isPrimary ? "1" : undefined}
          onClick={launchMessage}
          disabled={launchingMessageId === message.id}
          title={`让平台把这条派单送到绑定${deliveryNoun(seat)}并回写结果`}
        >
          {launchingMessageId === message.id ? "已提交，刷新中" : isPrimary ? "启动真实处理" : "启动"}
        </button>
        {variant === "inline" ? (
          <small className={styles.realThreadHint}>
            平台同步最小回执和最终结果；{processTraceHint(seat)}
          </small>
        ) : null}
      </div>
    );
  }

  async function launchQueuedMessage(message: CollabMessage, source: "button" | "review" | "intent" = "button") {
    if (!message?.id || launchingMessageId === message.id) return;
    setLaunchingMessageId(message.id);
    setSendNote(
      source === "review"
        ? "已通过审核，正在自动启动目标 NPC 的真实处理..."
        : "已提交启动请求，正在等待平台回执刷新...",
    );
    try {
      const result = await launchNpcOneShotThreadProcessing(projectId, seatApiId, message.id);
      setSendNote(
        result.launched
          ? `${result.seatName || seat.name} 的单次处理已启动，等待最小回执 / 最终结果。`
          : `启动失败：${result.error || "请检查绑定线程、执行电脑或项目目录。"}`,
      );
    } catch (error) {
      setSendNote(`启动失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      await load(limit);
      window.setTimeout(() => load(limit), 1500);
      window.setTimeout(() => load(limit), 4000);
      window.setTimeout(() => {
        setLaunchingMessageId((current) => current === message.id ? null : current);
      }, 5500);
    }
  }

  const load = useCallback(
    async (size: number) => {
      setFetching(true);
      setFetchError(null);
      try {
        const safeFetch = async (url: string) => {
          try {
            return await fetch(url, { credentials: "include" });
          } catch {
            return null;
          }
        };
        const identityIds = Array.from(seatIdentityIds);
        const messageLimit = Math.max(120, size);
        const baseWithLimit = apiClientUrl(`/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&limit=${messageLimit}`);
        const incomingUrls = identityIds.map(
          (id) => `${baseWithLimit}&recipient_type=thread_workstation&recipient_id=${encodeURIComponent(id)}`,
        );
        const outgoingUrls = identityIds.map((id) => `${baseWithLimit}&sender_id=${encodeURIComponent(id)}`);
        const agentUrls = identityIds.map((id) => `${baseWithLimit}&agent_id=${encodeURIComponent(id)}`);
        const scopedProject = encodeURIComponent(projectId);
        const queuesUrl = apiClientUrl(`/api/seats/${encodeURIComponent(seatApiId)}/queues?project_id=${scopedProject}&limit=30`);
        const receiptsUrl = apiClientUrl(`/api/receipts/by-seat/${encodeURIComponent(seatApiId)}?project_id=${scopedProject}&direction=${receiptDirection}&limit=30`);
        const [incomingResponses, outgoingResponses, agentResponses, r3, r4] = await Promise.all([
          Promise.all(incomingUrls.map((url) => safeFetch(url))),
          Promise.all(outgoingUrls.map((url) => safeFetch(url))),
          Promise.all(agentUrls.map((url) => safeFetch(url))),
          fetch(queuesUrl, { credentials: "include" }).catch(() => null),
          fetch(receiptsUrl, { credentials: "include" }).catch(() => null),
        ]);
        const liveIncomingResponses = incomingResponses.filter((res): res is Response => Boolean(res));
        const firstIncomingError = liveIncomingResponses.find((res) => !res.ok);
        if (!liveIncomingResponses.length) {
          throw new Error("主对话暂时无法连接，平台会继续重试。");
        }
        if (firstIncomingError && liveIncomingResponses.every((res) => !res.ok)) {
          const json = await firstIncomingError.json().catch(() => ({}));
          const msg = json?.error?.message ?? json?.message ?? `HTTP ${firstIncomingError.status}`;
          throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        }
        const incomingJson = await Promise.all(liveIncomingResponses.map((res) => res.ok ? res.json().catch(() => ({})) : Promise.resolve({})));
        const outgoingJson = await Promise.all(outgoingResponses.map((res) => res?.ok ? res.json().catch(() => ({})) : Promise.resolve({})));
        const agentJson = await Promise.all(agentResponses.map((res) => res?.ok ? res.json().catch(() => ({})) : Promise.resolve({})));
        const incoming = incomingJson.flatMap((json) => (json?.data ?? []) as CollabMessage[]);
        const outgoing = outgoingJson.flatMap((json) => (json?.data ?? []) as CollabMessage[]);
        const agentScoped = agentJson.flatMap((json) => (json?.data ?? []) as CollabMessage[]);
        const seen = new Set<string>();
        const merged: CollabMessage[] = [];
        for (const m of [...incoming, ...outgoing, ...agentScoped]) {
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
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      void load(limit);
    };
    const t = setInterval(refresh, 6000);
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("focus", refresh);
    };
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

  // 我的任务队列：收件给本 NPC、still open；只让最该处理的一条暴露启动/拒绝动作。
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
      if (value === "in_progress") return 0;
      if (value === "queued" || value === "pending") return 1;
      if (value === "acked") return 2;
      return 2;
    };
    return arr.slice().sort((a, b) => {
      const pa = priority(a.status || "");
      const pb = priority(b.status || "");
      if (pa !== pb) return pa - pb;
      return String(b.created_at || "").localeCompare(String(a.created_at || ""));
    });
  }, [messages, seatIdentityIds]);
  const activeQueueMessageId = myQueue[0]?.id || null;
  const activeDispatchCount = myQueue.length;
  const myNeedItems = seatQueues?.my_needs?.items ?? seatQueues?.requirement_inbox.items ?? [];
  const myTaskItems = seatQueues?.my_tasks?.items ?? seatQueues?.task_todo.items ?? [];
  const myNeedCount = seatQueues?.my_needs?.count ?? seatQueues?.requirement_inbox.count ?? 0;
  const myTaskCount = seatQueues?.my_tasks?.count ?? seatQueues?.task_todo.count ?? 0;
  const pendingCloseoutCount = messages?.filter((item) => {
    if (!isDesktopCloseoutMessage(item)) return false;
    return !sourceHasFinalReceipt(messages, closeoutSourceMessageId(item));
  }).length ?? 0;
  const latestActiveDispatch = myQueue[0] || null;
  const automationModeLabel = automationEnabled ? "自动继续中" : canUseDesktopAutomation ? "人工确认中" : "待绑定线程";
  const automationModeHint = automationEnabled
    ? "免审边界内，NPC 可继续找合适的协作方并等待回执。"
    : canUseDesktopAutomation
      ? "派单会进入队列，由你决定何时启动或开启自动推进。"
      : `先绑定${threadBindingNoun(seat)}，平台才能显示回执和处理状态。`;
  const runnerDispatchLabel = seat.runnerDispatchState || "状态未知，先检查接入";
  const runnerStateDetail = seat.runnerStateDetail
    || (runnerDispatchLabel === "可投递"
      ? "目标电脑正在持续接单，可以直接派发并等待最小回执。"
      : runnerDispatchLabel === "最近在线，可能延迟"
        ? "目标电脑最近在线，但心跳不稳定。可以排队，但要提示可能延迟。"
        : runnerDispatchLabel === "等待电脑恢复"
          ? "持续接单心跳已过期，先让目标电脑重新运行持续接单命令。"
          : runnerDispatchLabel === "离线，需重连"
            ? "目标电脑离线或执行程序不可用，请重新接入或改派。"
            : runnerDispatchLabel === "他人操作中"
              ? "当前电脑或线程正被其他操作者占用，可以申请接手或改派。"
              : "平台暂时不能确认这台电脑是否能接单，先检查电脑接入和线程绑定。");
  const runnerDispatchTitle = seat.computerNodeName
    ? `${seat.computerNodeName} · ${runnerDispatchLabel}`
    : `执行电脑 · ${runnerDispatchLabel}`;
  const runnerDispatchNext = runnerDispatchLabel === "可投递"
    ? "可以继续派发"
    : runnerDispatchLabel === "最近在线，可能延迟"
      ? "允许排队，注意延迟"
      : runnerDispatchLabel === "等待电脑恢复"
        ? "先恢复持续接单"
        : runnerDispatchLabel === "离线，需重连"
          ? "先重连或改派"
          : runnerDispatchLabel === "他人操作中"
            ? "申请接手或改派"
            : "先检查接入";
  const automationCurrentLabel = pendingCloseoutCount > 0
    ? `待收口 ${pendingCloseoutCount}`
    : activeDispatchCount > 0
      ? `等待结果 ${activeDispatchCount}`
      : automationEnabled
        ? "空闲待命"
        : "人工确认";
  const automationNextLabel = pendingCloseoutCount > 0
    ? "催办 / 延长等待 / 重新同步 / 手动收口"
    : automationEnabled
      ? "收到回执后可继续下一步"
      : canUseDesktopAutomation
        ? "可开启自动推进"
        : `去绑定${threadBindingNoun(seat)}`;
  const pendingReviews = useMemo(() => {
    return (messages || [])
      .filter((m) => shouldRenderAsReviewMessage(m))
      .slice()
      .sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")));
  }, [messages]);
  const dialogStateCards = useMemo(() => {
    const cards: Array<{
      id: string;
      status: string;
      title: string;
      detail: string;
      tone: "ok" | "manual" | "warn" | "danger";
      action?: "enable_automation" | "disable_automation";
      actionLabel?: string;
    }> = [];
    cards.push({
      id: "runtime-mode",
      status: automationModeLabel,
      title: automationEnabled ? "自动继续已开启" : canUseDesktopAutomation ? "当前由人确认推进" : `需要先绑定${threadBindingNoun(seat)}`,
      detail: automationModeHint,
      tone: automationEnabled ? "ok" : canUseDesktopAutomation ? "manual" : "warn",
      action: automationEnabled ? "disable_automation" : canUseDesktopAutomation ? "enable_automation" : undefined,
      actionLabel: automationEnabled ? "暂停自动继续" : canUseDesktopAutomation ? "开启自动继续" : undefined,
    });
    cards.push({
      id: "runner-state",
      status: runnerDispatchLabel,
      title: runnerDispatchTitle,
      detail: runnerStateDetail,
      tone: runnerStateToneForCard(seat.runnerStateTone),
    });
    if (pendingCloseoutCount > 0) {
      cards.push({
        id: "closeout",
        status: `待收口 ${pendingCloseoutCount}`,
        title: `${threadBindingNoun(seat)}过程等待最终收口`,
        detail: "在对应消息上可直接催办、延长等待、重新同步或手动收口。",
        tone: "danger",
      });
    }
    if (latestActiveDispatch) {
      cards.push({
        id: "active-dispatch",
        status: automationCurrentLabel,
        title: userFacingCollabText(latestActiveDispatch.title || "当前派单"),
        detail: pendingCloseoutCount > 0 ? automationNextLabel : `${automationNextLabel} · ${runnerDispatchNext}`,
        tone: pendingCloseoutCount > 0 ? "danger" : seat.runnerCanDispatch ? "manual" : runnerStateToneForCard(seat.runnerStateTone),
      });
    }
    if (pendingReviews.length === 0) {
      cards.push({
        id: "review-context",
        status: "待审 0",
        title: "当前没有待审消息",
        detail: "只有 NPC 明确提出跨工位或高风险需求时，才会在这里出现通过/打回控件；你自己手动派单不需要自审。",
        tone: "manual",
      });
    }
    return cards;
  }, [
    automationCurrentLabel,
    automationEnabled,
    automationModeHint,
    automationModeLabel,
    automationNextLabel,
    canUseDesktopAutomation,
    latestActiveDispatch,
    pendingCloseoutCount,
    pendingReviews.length,
    runnerDispatchLabel,
    runnerDispatchNext,
    runnerDispatchTitle,
    runnerStateDetail,
    seat,
  ]);

  const visible = useMemo(() => {
    const list = (messages || []).slice().reverse();
    const readable = hideNoisy
      ? list.filter((m) => {
      if (shouldRenderAsReviewMessage(m)) return true;
      const refined = summarizeCollabMessage(m, seat.desktopVisible);
      return refined.showByDefault && !refined.noisy;
    })
      : list;
    const important = readable.filter((m) => {
      const status = (m.status || "").toLowerCase();
      const type = (m.message_type || "").toLowerCase();
      const title = (m.title || "").toLowerCase();
      return (
        m.id === activeQueueMessageId
        || title.includes("git 回退")
        || type === "desktop_user_question"
        || type === "desktop_minimal_receipt"
        || ["failed", "rejected", "completed", "done", "in_progress"].includes(status)
        || type.includes("result")
        || type.includes("ack")
      );
    });
    const recent = readable.slice(-8);
    const seen = new Set<string>();
    const combined = [...important, ...recent].filter((m) => {
      if (!m.id || seen.has(m.id)) return false;
      seen.add(m.id);
      return true;
    });
    if (showFullHistory) return combined;
    const duplicateSeen = new Set<string>();
    const chainBest = new Map<string, CollabMessage>();
    const chainOrder: string[] = [];
    const passthrough: CollabMessage[] = [];
    const directCommandByChain = new Set<string>();
    const hasFinalByChain = new Set<string>();
    for (const msg of combined) {
      const key = dialogChainKey(msg);
      const type = safeText(msg.message_type, "").toLowerCase();
      const status = safeText(msg.status, "").toLowerCase();
      if (key && ["agent_command", "requirement_dispatch", "comment_message"].includes(type) && ["queued", "pending", "completed", "done"].includes(status)) {
        directCommandByChain.add(key);
      }
      if (key && isFinalReceipt(msg)) hasFinalByChain.add(key);
    }
    for (const msg of combined) {
      const duplicateKey = dialogDedupeKey(msg);
      if (duplicateSeen.has(duplicateKey)) continue;
      duplicateSeen.add(duplicateKey);
      const chainKey = dialogChainKey(msg);
      const type = safeText(msg.message_type, "").toLowerCase();
      if (
        chainKey
        && hasFinalByChain.has(chainKey)
        && ["agent_command", "requirement_dispatch", "comment_message"].includes(type)
      ) {
        continue;
      }
      if (shouldRenderAsReviewMessage(msg)) {
        passthrough.push(msg);
        continue;
      }
      if (!chainKey || !isIntermediateReceipt(msg)) {
        passthrough.push(msg);
        continue;
      }
      if (directCommandByChain.has(chainKey) && !isFinalReceipt(msg)) continue;
      if (hasFinalByChain.has(chainKey) && !isFinalReceipt(msg)) continue;
      const current = chainBest.get(chainKey);
      if (!current) {
        chainBest.set(chainKey, msg);
        chainOrder.push(chainKey);
        continue;
      }
      const preferMsg = isFinalReceipt(msg) || (!isFinalReceipt(current) && String(msg.created_at || "").localeCompare(String(current.created_at || "")) > 0);
      if (preferMsg) chainBest.set(chainKey, msg);
    }
    const compacted = [...passthrough, ...chainOrder.map((key) => chainBest.get(key)).filter((m): m is CollabMessage => Boolean(m))];
    compacted.sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")));
    return compacted;
  }, [messages, hideNoisy, showFullHistory, activeQueueMessageId, seat.desktopVisible]);
  const messageReceiptCount = useMemo(() => {
    return (messages || []).filter((message) => {
      const type = safeText(message.message_type, "").toLowerCase();
      if (!["runner_ack", "runner_result", "agent_ack", "agent_result", "requirement_progress_ack", "requirement_final_reply", "desktop_minimal_receipt"].includes(type)) {
        return false;
      }
      const { noisy } = classifyMessage(message);
      return !noisy;
    }).length;
  }, [messages]);
  const totalReceiptCount = (receipts?.length ?? 0) + messageReceiptCount;

  const peerDispatchCards = useMemo(() => {
    const cards = new Map<string, StructuredMessageCard>();
    for (const message of messages || []) {
      const card = buildPeerDispatchStatusCard(message, messages || [], seat.name, peerByIdentity);
      if (card) cards.set(message.id, card);
    }
    return cards;
  }, [messages, peerByIdentity, seat.name]);

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
      if (senderType === "human") continue;
      const isPeer = senderType === "agent" && peerIds.has(m.sender_id || "");
      const isExternal = senderType === "agent" && !!m.sender_id && !peerIds.has(m.sender_id) && !seatIdentityIds.has(m.sender_id);
      const senderName = displaySenderName(m, peerByIdentity, "协作者");
      const from = isPeer
        ? `同工位 ${senderName}`
        : isExternal
          ? `跨工位 ${senderName}`
          : senderType === "human"
            ? "人类成员"
            : senderType || "系统";
      push({
        id: `queue:${m.id}`,
        tone: isPeer ? "peer" : isExternal ? "external" : "human",
        label: "派单",
        title: userFacingCollabText(m.title || stripPlatformChatter(m.body || "").slice(0, 90), "(无标题)"),
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
        title: userFacingCollabText(r.title || r.body.slice(0, 90), "(无标题回执)"),
        meta: `${r.cross_workstation ? "跨工位" : "同工位"}回执 ${receiptDirection === "incoming" ? "-> 本 NPC" : "从本 NPC ->"}`,
        status: r.receipt_kind,
        createdAt: r.created_at,
      });
    }

    for (const m of messages || []) {
      const type = (m.message_type || "").toLowerCase();
      if (isGitMessageForSeat(m, seatIdentityIds)) {
        push({
          id: `git:${m.id}`,
          tone: "review",
          label: "Git",
          title: userFacingCollabText(m.title || stripPlatformChatter(m.body || "").slice(0, 90), "Git 事件"),
          meta: "来自该 NPC 的提交、预检或回退记录",
          status: m.status,
          createdAt: m.created_at,
        });
        continue;
      }
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
        title: userFacingCollabText(m.title || stripPlatformChatter(m.body || "").slice(0, 90), "(线程事件)"),
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
  const [launchingMessageId, setLaunchingMessageId] = useState<string | null>(null);
  const [closeoutBusyId, setCloseoutBusyId] = useState<string | null>(null);

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
    let approvedMessage: CollabMessage | null = null;
    try {
      approvedMessage = action === "approve" ? (messages || []).find((m) => m.id === id) || null : null;
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
      const isBoundaryApproval = action === "approve" && isPreDispatchBoundaryMessage(approvedMessage);
      setReviewNote(
        action === "approve"
          ? isBoundaryApproval
            ? "✓ 边界卡已通过；请基于这个边界再发正式派单"
            : (rememberPolicy ? "✓ 已通过，并记住这对 NPC 下次免审，正在启动处理" : "✓ 已通过，正在启动处理")
          : "✓ 已打回",
      );
      await load(limit);
      window.dispatchEvent(new CustomEvent("workbench:collab-updated", { detail: { projectId, messageId: id, action } }));
      if (action === "approve" && approvedMessage && !isBoundaryApproval) {
        await launchQueuedMessage({ ...approvedMessage, status: "queued" }, "review");
      }
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

  function closeoutSourceMessageId(msg: CollabMessage): string {
    const meta = messageMetadata(msg);
    const sourceId = safeText(meta.source_message_id ?? meta.sourceMessageId, "");
    return sourceId || msg.id;
  }

  function isDesktopCloseoutMessage(msg: CollabMessage): boolean {
    const meta = messageMetadata(msg);
    const taxonomy = safeRecord(meta.blocked_taxonomy);
    const reason = safeText(taxonomy.blocked_reason_code ?? taxonomy.exception_kind ?? meta.blocked_reason_code, "");
    return Boolean(
      reason === "desktop_final_sync_lag"
        || taxonomy.desktop_closeout_waiting
        || meta.desktop_closeout_waiting
        || meta.needs_manual_closeout
        || meta.timeout_repair
        || meta.nudge_required
        || meta.wait_extension_available
        || meta.manual_close_required,
    );
  }

  function isOpenDesktopCloseoutMessage(msg: CollabMessage): boolean {
    if (!isDesktopCloseoutMessage(msg)) return false;
    return !sourceHasFinalReceipt(messages, closeoutSourceMessageId(msg));
  }

  async function runCloseoutAction(msg: CollabMessage, action: "nudge" | "extend_wait" | "retry_desktop_sync" | "manual_close") {
    const sourceId = closeoutSourceMessageId(msg);
    setCloseoutBusyId(`${sourceId}:${action}`);
    setReviewNote(null);
    const actionLabel = action === "nudge" ? "催办" : action === "extend_wait" ? "延长等待" : action === "retry_desktop_sync" ? "重新同步" : "手动收口";
    try {
      const res = await fetch(
        apiClientUrl(
          `/api/collaboration/projects/${encodeURIComponent(projectId)}/thread-workstations/${encodeURIComponent(seatApiId)}/messages/${encodeURIComponent(sourceId)}/closeout-action`,
        ),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ action }),
        },
      );
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msgText = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msgText === "string" ? msgText : JSON.stringify(msgText));
      }
      setReviewNote(`✓ 已${actionLabel}`);
      await load(limit);
      window.dispatchEvent(new CustomEvent("workbench:collab-updated", { detail: { projectId, messageId: sourceId, action } }));
    } catch (error) {
      setReviewNote(`${actionLabel}失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setCloseoutBusyId(null);
      setTimeout(() => setReviewNote(null), 5000);
    }
  }

  function canArchiveQueueItem(item: SeatQueueItem) {
    return ["done", "completed", "closed", "accepted", "answered", "cancelled", "rejected", "failed"].includes(
      safeText(item.status, "").toLowerCase(),
    );
  }

  async function archiveNeedTaskItem(kind: "needs" | "tasks", item: SeatQueueItem) {
    const id = safeText(item.id, "");
    if (!id || !canArchiveQueueItem(item)) return;
    setArchiveBusyId(`${kind}:${id}`);
    setQueueNote(null);
    const path = kind === "needs" ? `/api/requirements/${encodeURIComponent(id)}/archive` : `/api/tasks/${encodeURIComponent(id)}/archive`;
    try {
      const res = await fetch(apiClientUrl(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          actor_type: "human",
          actor_id: currentUserId,
          note: "从当前工作台队列归档；GitHub 证据保留。",
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msgText = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msgText === "string" ? msgText : JSON.stringify(msgText));
      }
      setQueueNote(kind === "needs" ? "已归档完成需求" : "已归档完成任务");
      await load(limit);
      window.dispatchEvent(new CustomEvent("workbench:queue-archived", { detail: { projectId, kind, id } }));
    } catch (error) {
      setQueueNote(`归档失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setArchiveBusyId(null);
      setTimeout(() => setQueueNote(null), 5000);
    }
  }

  async function openArtifactPreview(msg: CollabMessage, artifact: EvidenceArtifact) {
    const previewKey = `${msg.id}:${artifact.path}`;
    const current = artifactPreviews[previewKey];
    if (current?.content && !current.error) {
      setArtifactPreviews((prev) => ({
        ...prev,
        [previewKey]: { ...current, content: undefined },
      }));
      return;
    }
    setArtifactPreviews((prev) => ({
      ...prev,
      [previewKey]: { ...(prev[previewKey] || {}), loading: true, error: undefined, path: artifact.path },
    }));
    try {
      const params = new URLSearchParams({
        project_id: projectId,
        path: artifact.path,
      });
      if (msg.task_id) params.set("task_id", msg.task_id);
      if (msg.dispatch_id) params.set("dispatch_id", msg.dispatch_id);
      params.set("source_message_id", msg.id);
      const res = await fetch(
        apiClientUrl(`/api/collaboration/artifacts/preview?${params.toString()}`),
        { credentials: "include" },
      );
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      const data = json?.data ?? {};
      setArtifactPreviews((prev) => ({
        ...prev,
        [previewKey]: {
          loading: false,
          path: String(data.path || artifact.path),
          name: String(data.name || artifact.label),
          sizeBytes: typeof data.size_bytes === "number" ? data.size_bytes : undefined,
          truncated: Boolean(data.truncated),
          content: String(data.content ?? ""),
        },
      }));
    } catch (error) {
      setArtifactPreviews((prev) => ({
        ...prev,
        [previewKey]: {
          ...(prev[previewKey] || {}),
          loading: false,
          path: artifact.path,
          error: error instanceof Error ? error.message : "证据预览失败",
        },
      }));
    }
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
      `- 显示边界: ${processTraceHint(seat)}平台只回写最小回执、最终结果、阻塞原因和可追踪索引。`,
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
    const targetSeat = [...teammates, ...crossLeads].find((candidate) => seatIdentityList(candidate).includes(peerId));
    const readiness = targetSeat ? dispatchReadinessForSeat(targetSeat) : null;
    if (readiness?.mode === "blocked") {
      setSendNote(`${peerName} 当前${readiness.stateLabel}。${readiness.note}`);
      setTimeout(() => setSendNote(null), 5000);
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

  function peerDispatchLabel(mode: "same" | "cross", busy: boolean): string {
    if (busy) return "派发中...";
    return mode === "cross" ? "派给工位长" : "派单";
  }

  function renderPeerDirectoryCard(peer: WorkbenchSeat, mode: "same" | "cross") {
    const peerId = peer.rowId || peer.id;
    const isCross = mode === "cross";
    const readiness = dispatchReadinessForSeat(peer);
    const dispatchLabel = dispatchingPeerId === peerId
      ? "派发中..."
      : readiness.mode === "queue"
        ? (isCross ? "排队给工位长" : "排队")
        : readiness.mode === "blocked"
          ? readiness.actionLabel
          : peerDispatchLabel(mode, false);
    const emptyHint = isCross
      ? `先在底部 textarea 写内容，再点「派给工位长 ${peer.name}」`
      : `先在底部 textarea 写内容，再点「派单 ${peer.name}」`;
    const title = isCross
      ? `用户手动把任务派给 ${peer.name}（${peer.computerNodeName || peer.workstationName || "目标工位"} 工位长）`
      : `用户手动把任务派给 ${peer.name}`;
    const dispatchTitle = readiness.mode === "ready"
      ? title
      : `${title}。${peer.name} 当前${readiness.stateLabel}；${readiness.note}`;
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
            title={dispatchTitle}
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
        setSendNote("正在启动第一条派单的真实处理...");
        await launchQueuedMessage(myQueue[0], "intent");
        return;
      }
      setSendNote("正在拒绝第一条派单并写回执...");
      await updateDispatchStatus(myQueue[0], action);
      return;
    }
    const targetOpts = opts;
    sendInFlightRef.current = true;
    setSending(true);
    setDispatchingPeerId(targetOpts?.peerId || "__self__");
    setSendNote(null);
    const isPeer = !!targetOpts?.peerId;
    const manualTargetName = targetOpts?.peerName || seat.name;
    const targetSeat = targetOpts?.peerId
      ? [...teammates, ...crossLeads].find((candidate) => seatIdentityList(candidate).includes(targetOpts.peerId!))
      : null;
    const executionSeat = targetSeat ?? seat;
    const dispatchReadiness = dispatchReadinessForSeat(executionSeat);
    const isCrossWorkstation = Boolean(
      targetSeat && seatGroupKeyLocal(targetSeat) && seatGroupKeyLocal(seat) && seatGroupKeyLocal(targetSeat) !== seatGroupKeyLocal(seat),
    );
    const boundaryMetadata = boundaryCardMetadataFromText(
      body,
      seat.name,
      targetOpts?.peerName || seat.name,
    );
    const isBoundaryCard = Boolean(boundaryMetadata);
    try {
      setSendNote(isPeer ? `正在派给 ${manualTargetName}...` : "正在写入协作消息池...");
      const res = await fetch(apiClientUrl("/api/collaboration/messages"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          project_id: projectId,
          message_type: "agent_command",
          title: isPeer
            ? `[用户 → ${manualTargetName}] 手动派单`
            : `[用户 → ${seat.name}] 对话指令`,
          body: buildDispatchBody(body, manualTargetName),
          sender_type: "human",
          sender_id: null,
          recipient_type: "thread_workstation",
          recipient_id: isPeer ? targetOpts!.peerId! : seatApiId,
          status: isBoundaryCard ? "pending_review" : "queued",
          ...(boundaryMetadata ? { metadata: boundaryMetadata } : {}),
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
      if (isBoundaryCard) {
        setSendNote("边界卡已登记，等待人审；审批前不会启动真实处理 ✓");
      } else {
        const targetSeatId = isPeer ? targetOpts!.peerId! : seatApiId;
        if (dispatchReadiness.mode === "blocked") {
          setSendNote(
            isPeer
              ? `已记录给 ${manualTargetName}，但当前不能启动真实处理：${dispatchReadiness.note}`
              : `已记录到 ${seat.name}，但当前不能启动真实处理：${dispatchReadiness.note}`,
          );
        } else {
          setSendNote(
            dispatchReadiness.mode === "queue"
              ? (isPeer
                ? `已派给 ${manualTargetName}，当前按“${dispatchReadiness.stateLabel}”排队等待恢复...`
                : `已记录到 ${seat.name}，当前按“${dispatchReadiness.stateLabel}”排队等待恢复...`)
              : (isPeer ? `已派给 ${manualTargetName}，正在投递到目标电脑...` : "已派发，正在投递到绑定线程..."),
          );
          const launchResult = await launchNpcOneShotThreadProcessing(projectId, targetSeatId, json.data.id);
          setSendNote(
            launchResult.launched
              ? dispatchReadiness.mode === "queue"
                ? `${launchResult.seatName || manualTargetName} 已进入恢复队列；等目标电脑恢复后会继续处理`
                : launchResult.desktopVisible
                  ? `${launchResult.seatName || manualTargetName} 已进入执行电脑，正在等待桌面线程确认可见`
                  : `${launchResult.seatName || manualTargetName} 已进入执行电脑队列；回执会回到对应 NPC 瓷砖`
              : `已派发，但投递失败：${launchResult.error || "请检查绑定线程、执行电脑或同步状态"}`,
          );
          if (launchResult.launched) refreshAfterOneShot();
        }
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

  function renderNeedTaskPanel(kind: "needs" | "tasks") {
    const activeItems = kind === "needs" ? myNeedItems : myTaskItems;
    const count = kind === "needs" ? myNeedCount : myTaskCount;
    const title = kind === "needs" ? "我的需求" : "我的任务";
    const subtitle = kind === "needs"
      ? "这个 NPC 缺什么、等谁满足；需求不是任务。"
      : "分配给这个 NPC 要完成的工作；任务不是消息。";
    return (
      <section className={styles.queueWorkspace} aria-label={title}>
        <div className={styles.queueWorkspaceHead}>
          <div>
            <span>{title}</span>
            <strong>{count} 项</strong>
          </div>
          <small>{subtitle}</small>
        </div>
        {activeItems.length > 0 ? (
          <ul className={styles.queueList}>
            {activeItems.slice(0, 10).map((it, i) => (
              <li key={it.id} className={styles.queueItem} data-from={kind}>
                <span className={styles.queuePos}>#{i + 1}</span>
                <div className={styles.queueMeta}>
                  <span className={styles.queueFrom}>
                    {kind === "needs"
                      ? (it.to_agent || it.target_seat_id ? `等待 ${it.to_agent || it.target_seat_id}` : it.trigger_kind || "待路由")
                      : (it.module ? `模块 ${it.module}` : it.priority || "待排期")}
                  </span>
                  <span className={styles.queueTitle}>{it.title || "(无标题)"}</span>
                </div>
                <span className={styles.queueStatus} data-status={it.status}>{it.status}</span>
                {canArchiveQueueItem(it) ? (
                  <button
                    type="button"
                    className={styles.queueArchiveBtn}
                    onClick={() => archiveNeedTaskItem(kind, it)}
                    disabled={archiveBusyId !== null}
                    title="从当前队列归档；GitHub 证据仍保留"
                  >
                    {archiveBusyId === `${kind}:${it.id}` ? "归档中" : "归档"}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <div className={styles.queueEmpty}>
            <strong>{kind === "needs" ? "暂无待满足需求" : "暂无待办任务"}</strong>
            <p>
              {kind === "needs"
                ? "NPC 只有明确写入结构化需求后，这里才会出现路由、审核和结果状态。"
                : "用户手动派单或其他 NPC 的需求被路由过来后，这里才会出现任务。"}
            </p>
          </div>
        )}
        {activeItems.length > 10 ? <small className={styles.muted}>… 还有 {activeItems.length - 10} 项</small> : null}
        {queueNote ? <small className={styles.queueNote}>{queueNote}</small> : null}
      </section>
    );
  }

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
    const structuredCard = getStructuredMessageCard(m);
    const isBoundaryReview = isPreDispatchBoundaryMessage(m);
    const upstreamLabel = displayReviewEndpointName(upstream || m.sender_id, peerByIdentity, "未知上游");
    const downstreamLabel = displayReviewEndpointName(downstream || m.recipient_id, peerByIdentity, "未知目标");
    const reviewReason = reviewSourceLabel(source) || (isCross ? "跨工位审核" : "人工审核");
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
              {reviewSourceLabel(source)}
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
        <div className={styles.processLine} aria-label="协作过程">
          <span title="来源">{upstreamLabel}</span>
          <b aria-hidden>→</b>
          <span title="目标">{downstreamLabel}</span>
          <em>人工审核 · 待确认</em>
          <small>{reviewReason}</small>
        </div>
        <p className={styles.msgSummary}>
          <strong>{userFacingCollabText(m.title || "NPC 自主合作请求")}</strong>
          <span>
            {reviewReason}，通过后才会继续送达；打回会保留审计记录。
          </span>
        </p>
        {structuredCard ? renderStructuredMessageCard(structuredCard) : null}
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
            onClick={(e) => {
              e.preventDefault();
              if (reviewBusyId !== m.id) reviewMessage(m.id, "approve");
            }}
          >
            {isBoundaryReview ? "通过边界" : "通过"}
          </button>
          {isBoundaryReview ? null : (
            <button
              type="button"
              className={styles.reviewRememberBtn}
              disabled={reviewBusyId === m.id}
              onClick={(e) => {
                e.preventDefault();
                if (reviewBusyId !== m.id) reviewMessage(m.id, "approve", "skip");
              }}
              title="通过这条消息，并让同一对 NPC 下次直接派发"
            >
              通过并免审
            </button>
          )}
          <button
            type="button"
            className={styles.reviewRejectBtn}
            disabled={reviewBusyId === m.id}
            onClick={(e) => {
              e.preventDefault();
              if (reviewBusyId !== m.id) reviewMessage(m.id, "reject");
            }}
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
            <span className={styles.threadChip} title={threadBindingHint(seat)}>
              {threadBindingLabel(seat)}
            </span>
            <span className={`${styles.threadChip} ${styles.occupancyChip}`} title="当前操作占用状态">
              {threadStatusLabel}
            </span>
            <Link
              href={governanceHref("npc-create")}
              className={styles.threadChip}
              title="回到主页面 NPC 管理，从扫描到的执行线程列表里按名称选择"
            >
              去主页面选择线程
            </Link>
            {seat.desktopVisible ? (
              <span
                className={`${styles.threadChip} ${styles.desktopVisibleChip}`}
                title="平台派单会作为普通用户消息进入绑定桌面线程，完整处理过程在桌面版显示"
              >
                桌面可见
              </span>
            ) : seat.desktopProcessDetected ? (
              <span
                className={`${styles.threadChip} ${styles.desktopDetectedChip}`}
                title="检测到桌面版，但当前绑定线程还不能确认实时可见"
              >
                桌面待确认
              </span>
            ) : null}
            {seat.desktopVisible && seat.desktopThreadUrl ? (
              <a
                className={`${styles.threadChip} ${styles.desktopThreadChip}`}
                href={seat.desktopThreadUrl}
                title="在桌面版打开这个 NPC 绑定的线程"
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

      <nav className={styles.panelTabs} aria-label={`${seat.name} 工作区切换`}>
        {[
          ["dialog", "对话", filteredCount],
          ["needs", "我的需求", myNeedCount],
          ["tasks", "我的任务", myTaskCount],
        ].map(([tab, label, count]) => (
          <button
            key={String(tab)}
            type="button"
            className={styles.panelTab}
            data-active={activePanelTab === tab ? "1" : undefined}
            onClick={() => setActivePanelTab(tab as NpcPanelTab)}
            title={tab === "dialog" ? "对话、回执、审核入口" : tab === "needs" ? "这个 NPC 发出的结构化需求" : "这个 NPC 承接的任务"}
          >
            <span>{label}</span>
            <strong>{count}</strong>
          </button>
        ))}
      </nav>

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
                  <small className={styles.sectionLabel}>能力包 / 知识装配</small>
                  <p className={styles.profileTextDim}>
                    暂无 NPC 能力包或工位继承能力包。先到能力工坊维护能力和知识，再在公司层分配给这个 NPC。
                  </p>
                  <div className={styles.inlineActions}>
                    <Link href={governanceHref("skills", "skill-category")} className={styles.linkBtn}>
                      配置能力包
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
                  能力包 / 知识装配 ({total})
                  {inherited.length > 0 ? <span className={styles.peerHint}> · 工位继承 {inherited.length} / 自加 {own.length}</span> : null}
                </small>
                <div className={styles.chipRow}>
                  {inherited.slice(0, 6).map((skill) => (
                    <Link
                      key={`inh-${skill}`}
                      href={governanceHref("skills")}
                      className={styles.chipInherit}
                      title="去能力工坊：查看能力包仓库和工位继承"
                    >
                      ⇪ {skill}
                    </Link>
                  ))}
                  {own.slice(0, 6).map((skill) => (
                    <Link
                      key={`own-${skill}`}
                      href={governanceHref("skills")}
                      className={styles.chip}
                      title="去能力工坊：查看 NPC 能力包装配"
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
                <Link href={governanceHref("git")} className={styles.codeLink} title="去能力工坊：仓库与知识库路径约定">
                  {seat.workstationKnowledgePath}
                </Link>
                <span className={styles.peerHint}> · 本工位所有 NPC 共读，运行目录只用于当前电脑执行定位</span>
              </p>
            </div>
          ) : (
            <div className={styles.profileRow}>
              <small className={styles.sectionLabel}>工位知识库（待配置）</small>
              <p className={styles.profileTextDim}>
                先在公司层给这个 NPC 分配逻辑工位，再到能力工坊设置知识库；否则同工位互认和跨工位工位长路由都会退化。
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
            <div className={styles.identityRow}>
              <span className={styles.identityMeta}>
                {threadBindingLabel(seat)} · {seat.threadHealth || "未知"}
              </span>
              {seat.desktopVisible ? (
                <span className={styles.statusPill} title="平台派单会作为普通用户消息进入绑定桌面线程">
                  桌面可见
                </span>
              ) : null}
              {seat.desktopVisible && seat.desktopThreadUrl ? (
                <a className={styles.iconBtn} href={seat.desktopThreadUrl} title="在桌面版打开这个 NPC 绑定的线程">
                  打开桌面线程
                </a>
              ) : null}
              <Link
                href={`/projects/${projectId}?panel=team&tab=npc-create&focus_seat=${encodeURIComponent(seatApiId)}`}
                className={styles.iconBtn}
                title="回到主页面 NPC 管理，从平台扫描到的线程列表里按线程名选择"
              >
                去主页面选择线程
              </Link>
            </div>
            <small className={styles.profileTextDim}>
              线程绑定在主页面 NPC 管理完成：先让平台扫描电脑上的{threadBindingNoun(seat)}，再按线程名字选择。这里不要求用户填写任何编号。
            </small>
          </div>
          <div className={styles.profileRow}>
            <small className={styles.sectionLabel}>
              NPC 自动化
              <span className={styles.peerHint}>· 平台送达绑定线程，并同步处理回执</span>
            </small>
            <div className={styles.automationRow}>
              <button
                type="button"
                className={`${styles.automationSwitch} ${automationEnabled ? styles.automationSwitchOn : ""}`}
                onClick={() => toggleAutomation(!automationEnabled)}
                disabled={automationBusy}
                aria-pressed={automationEnabled}
                title={automationEnabled ? "暂停此 NPC 的自动接单和回执同步" : "开启此 NPC 的自动接单和回执同步"}
              >
                <span className={styles.automationKnob} />
                <span>{automationEnabled ? "自动推进已开" : "手动模式"}</span>
              </button>
              <span className={styles.identityMeta}>
                {automationEnabled
                  ? `平台会自动继续当前派单；${processTraceHint(seat)}`
                  : "关闭时只处理当前这一条；你可先看回执，再决定是否继续。"}
              </span>
            </div>
            {!automationEnabled ? (
              <small className={styles.identityNote}>
                当前只显示最小回执和最终结果；{processTraceHint(seat)}
              </small>
            ) : null}
            {automationNote ? <small className={styles.identityNote}>{automationNote}</small> : null}
            <small className={styles.identityMeta}>
              绑定线程保持在线后，可继续自动接收、返回最小回执，并在待收口时支持重新同步。
            </small>
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
            需求 {(seatQueues?.my_needs?.count ?? seatQueues?.requirement_inbox.count ?? 0)}
            {" / "}
            任务 {(seatQueues?.my_tasks?.count ?? seatQueues?.task_todo.count ?? 0)}
            {" / "}
            对话指令 {myQueue.length}
            {" / "}
            回执 {totalReceiptCount}
          </small>
        </summary>
        <div className={styles.runtimeBody}>
      {(() => {
        const needItems = myNeedItems;
        const taskItems = myTaskItems;
        const dispatchItems = myQueue;
        const needCount = myNeedCount;
        const taskCount = myTaskCount;
        if (needCount === 0 && taskCount === 0 && dispatchItems.length === 0 && totalReceiptCount === 0) {
          return null;
        }
        const activeItems = queueTab === "needs" ? needItems : queueTab === "tasks" ? taskItems : null;
        return (
          <div className={styles.queueBox}>
            <div className={styles.queueHead}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={() => setQueueTab("dispatch")}
                  className={styles.iconBtn}
                  data-active={queueTab === "dispatch" ? "1" : undefined}
                  title="派单消息：直接发给本 NPC 的 collaboration_message"
                >
                  ✉ 对话指令 {dispatchItems.length}
                </button>
              </div>
              <small className={styles.muted}>
                对话 Tab 只显示直发派单的接单队列；需求和任务请看上方主 Tab。
              </small>
            </div>
            {queueTab === "dispatch" ? (
              <ul className={styles.queueList}>
                {dispatchItems.slice(0, 6).map((m, i) => {
                  const isFromPeer = (m.sender_type || "").toLowerCase() === "agent" && peerIds.has(m.sender_id || "");
                  const isFromExternal = (m.sender_type || "").toLowerCase() === "agent" && !!m.sender_id && m.sender_id !== seat.id && !peerIds.has(m.sender_id);
                  const senderName = displaySenderName(m, peerByIdentity, "协作者");
                  const fromLabel = isFromPeer
                    ? `同工位 · ${senderName}`
                    : isFromExternal
                      ? `跨工位 · ${senderName}`
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
                        {m.id === activeQueueMessageId ? (
                          <div className={styles.queueActions} aria-label="派单处理">
                            {renderRealThreadLauncher(m, "compact", isLatest)}
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
                          </div>
                        ) : (
                          <small className={styles.muted}>排队中</small>
                        )}
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
                        {queueTab === "needs"
                          ? (it.to_agent || it.target_seat_id ? `→ ${it.to_agent || it.target_seat_id}` : it.trigger_kind || "待路由")
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
                {queueTab === "needs" ? "暂无需求" : "暂无任务"}
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
              const receiptCounterparty = receiptDirection === "incoming"
                ? displayReceiptEndpointName(r.sender_seat_id, peerByIdentity, seat.name, "协作者")
                : displayReceiptEndpointName(r.recipient_seat_id, peerByIdentity, seat.name, "目标方");
              return (
                <li key={r.id} className={styles.queueItem} data-from={r.cross_workstation ? "external" : "peer"}>
                  <span className={styles.queuePos}>{kindLabel}</span>
                  <div className={styles.queueMeta}>
                    <span className={styles.queueFrom}>
                      {r.cross_workstation ? "跨工位" : "同工位"}
                      {" · "}
                      {receiptDirection === "incoming"
                        ? (r.sender_seat_id ? `← ${receiptCounterparty}` : "(系统)")
                        : (r.recipient_seat_id ? `→ ${receiptCounterparty}` : "(广播)")}
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

        </div>
      </details>

      {activePanelTab === "needs" ? renderNeedTaskPanel("needs") : null}
      {activePanelTab === "tasks" ? renderNeedTaskPanel("tasks") : null}

      <div className={styles.dialogPane} data-active={activePanelTab === "dialog" ? "1" : "0"}>
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
            <span className={`${styles.legendDot} ${styles.roleBadge_watcher}`}>线程</span>
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
                ? "摘要流暂无可读信号，取消勾选「只看摘要」可查看原始同步消息。"
                : "暂无协作消息。绑定线程会处理完整过程，平台这里只显示必要摘要。"}
          </p>
        ) : (
          <>
          {dialogStateCards.map((card) => (
            <div
              key={card.id}
              className={`${styles.msg} ${styles.msg_note} ${styles.role_system} ${styles.dialogStateMsg}`}
              data-role="system"
              data-tone={card.tone}
              data-message-type="dialog_state"
            >
              <div className={styles.msgHead}>
                <span className={`${styles.roleBadge} ${styles.roleBadge_system}`}>系统状态</span>
                <span className={`${styles.badge} ${styles.badge_note}`}>{card.status}</span>
                <small className={styles.msgStatus}>跟随对话更新</small>
              </div>
              <div className={styles.processLine} aria-label="协作过程">
                <span title="来源">平台</span>
                <b aria-hidden>→</b>
                <span title="目标">{seat.name}</span>
                <em>{card.status}</em>
                <small>{card.id === "runtime-mode" ? "持续状态" : "当前卡点"}</small>
              </div>
              <p className={styles.msgSummary}>
                <strong>{card.title}</strong>
                <span>{card.detail}</span>
              </p>
              {card.action ? (
                <div className={styles.messageInlineActions} aria-label="自动继续操作">
                  <button
                    type="button"
                    className={styles.queueActionBtn}
                    onClick={() => toggleAutomation(card.action === "enable_automation")}
                    disabled={automationBusy}
                    title={card.action === "enable_automation" ? "允许平台在免审边界内自动继续" : "暂停自动继续，改为人工确认"}
                  >
                    {automationBusy ? "处理中" : card.actionLabel}
                  </button>
                  <Link
                    href={governanceHref("npc-create")}
                    className={styles.inlineLinkBtn}
                    title="线程绑定只在主页面 NPC 管理里选择，不在对话框填写线程编号"
                  >
                    管理线程绑定
                  </Link>
                </div>
              ) : null}
            </div>
          ))}
          {collaborationEvents.length > 0 ? (
            <details className={styles.dialogEvents}>
              <summary>
                <span>协作过程摘要</span>
                <small>{collaborationEvents.length} 条关键事件</small>
              </summary>
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
                        {event.status ? ` · ${humanizeDispatchCardStatus(event.status)}` : ""}
                        {event.createdAt ? ` · ${formatTime(event.createdAt)}` : ""}
                      </small>
                    </div>
                  </li>
                ))}
              </ol>
            </details>
          ) : null}
          {visible.map((msg) => {
            if (shouldRenderAsReviewMessage(msg)) {
              return renderReviewMessage(msg);
            }
            const refined = summarizeCollabMessage(msg, seat.desktopVisible);
            const { role, label: roleLabel } = classifyRole(msg, seat.id, peerIds, externalAgentIds);
            const expanded = expandedIds.has(msg.id);
            const body = userFacingCollabText(refined.cleanBody || refined.rawBody || "", "(空消息)", seat.desktopVisible);
            const canExpand = body.length > 0;
            const structuredCard = peerDispatchCards.get(msg.id) || getStructuredMessageCard(msg);
            const skipConversationCollabCard = role === "self"
              && (refined.kind === "result" || ["已接单", "处理中", "已完成", "最小回执"].includes(refined.statusLabel));
            const conversationCollabCard = skipConversationCollabCard ? null : buildConversationCollabCard(msg, peerByIdentity, seat.name);
            const professionalViews = inferProfessionalViews(msg, structuredCard);
            const evidenceArtifacts = extractEvidenceArtifacts(msg);
            const desktopCloseout = isOpenDesktopCloseoutMessage(msg);
            const closeoutSourceId = desktopCloseout ? closeoutSourceMessageId(msg) : "";
            const senderLabel =
              role === "human"
                ? "用户"
                : role === "self"
                  ? `本 NPC · ${seat.name}`
                  : role === "peer"
                      ? `同工位 · ${displaySenderName(msg, peerByIdentity, "协作者")}`
                    : role === "external"
                      ? `跨工位 · ${displaySenderName(msg, peerByIdentity, "协作者")}`
                      : role === "watcher"
                        ? "同步线程"
                        : roleLabel;
            const processMeta = messageProcessMeta(msg, role, senderLabel, peerByIdentity, seat.name, refined);
            return (
              <div
                key={msg.id}
                className={`${styles.msg} ${styles[`msg_${refined.kind}`] || ""} ${styles[`role_${role}`] || ""}`}
                data-role={role}
                data-message-id={msg.id}
                data-message-type={msg.message_type || ""}
              >
                <div className={styles.msgHead}>
                  <span className={`${styles.roleBadge} ${styles[`roleBadge_${role}`] || ""}`} title={senderLabel}>
                    {senderLabel}
                  </span>
                  <span className={`${styles.badge} ${styles[`badge_${refined.kind}`] || ""}`}>
                    {refined.statusLabel}
                  </span>
                  <small className={styles.msgTime}>{formatTime(msg.created_at)}</small>
                  <small className={styles.msgStatus}>{refined.statusLabel}</small>
                </div>
                <div className={styles.processLine} aria-label="协作过程">
                  <span title="来源">{processMeta.origin}</span>
                  <b aria-hidden>→</b>
                  <span title="目标">{processMeta.target}</span>
                  <em>{processMeta.process}</em>
                  <small>{processMeta.signal}</small>
                </div>
                <p className={styles.msgSummary}>
                  <strong>{refined.headline}</strong>
                  {refined.detail ? <span>{refined.detail}</span> : null}
                </p>
                {structuredCard ? renderStructuredMessageCard(structuredCard) : null}
                {conversationCollabCard && (!structuredCard || conversationCollabCard.summary !== structuredCard.summary) ? renderStructuredMessageCard(conversationCollabCard) : null}
                {desktopCloseout ? (
                  <div className={styles.closeoutActions} aria-label="桌面待收口操作">
                    <span>待收口：已收到过程回执，正在等最终收口</span>
                    <button
                      type="button"
                      onClick={() => runCloseoutAction(msg, "nudge")}
                      disabled={closeoutBusyId !== null}
                      title="提醒目标继续处理，当前命令仍保持处理中"
                    >
                      {closeoutBusyId === `${closeoutSourceId}:nudge` ? "催办中" : "催办"}
                    </button>
                    <button
                      type="button"
                      onClick={() => runCloseoutAction(msg, "extend_wait")}
                      disabled={closeoutBusyId !== null}
                      title="继续等待最终收口，当前命令保持处理中"
                    >
                      {closeoutBusyId === `${closeoutSourceId}:extend_wait` ? "延长中" : "延长等待"}
                    </button>
                    <button
                      type="button"
                      onClick={() => runCloseoutAction(msg, "retry_desktop_sync")}
                      disabled={closeoutBusyId !== null}
                      title="重新拉取最终结果，不需要理解平台内部同步细节"
                    >
                      {closeoutBusyId === `${closeoutSourceId}:retry_desktop_sync` ? "同步中" : "重新同步"}
                    </button>
                    <button
                      type="button"
                      onClick={() => runCloseoutAction(msg, "manual_close")}
                      disabled={closeoutBusyId !== null}
                      data-danger="1"
                      title="确认桌面结果后，由人手动完成平台收口"
                    >
                      {closeoutBusyId === `${closeoutSourceId}:manual_close` ? "收口中" : "手动收口"}
                    </button>
                  </div>
                ) : null}
                {professionalViews.length ? (
                  <div className={styles.professionalStrip} aria-label="进入专业视图">
                    <small className={styles.professionalStripLabel}>专业视图</small>
                    <div className={styles.professionalStripLinks}>
                      {professionalViews.map((entry) => (
                        <Link
                          key={`${msg.id}-${entry.surface}`}
                          href={professionalViewHref(entry.surface, msg)}
                          className={styles.professionalStripLink}
                          data-surface={entry.surface}
                          title={`${entry.label}：${entry.hint}`}
                        >
                          <span>{entry.label}</span>
                          <small>{entry.hint}</small>
                        </Link>
                      ))}
                    </div>
                  </div>
                ) : null}
                {evidenceArtifacts.length ? (
                  <div className={styles.evidenceStrip} aria-label="证据文件">
                    <span className={styles.evidenceLabel}>证据</span>
                    {evidenceArtifacts.map((artifact) => {
                      const previewKey = `${msg.id}:${artifact.path}`;
                      const preview = artifactPreviews[previewKey];
                      return (
                        <button
                          key={previewKey}
                          type="button"
                          className={styles.evidenceBtn}
                          onClick={() => openArtifactPreview(msg, artifact)}
                          title={artifact.path}
                          data-open={preview?.content ? "1" : undefined}
                        >
                          {preview?.loading ? "读取中..." : artifact.label}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
                {evidenceArtifacts.map((artifact) => {
                  const previewKey = `${msg.id}:${artifact.path}`;
                  const preview = artifactPreviews[previewKey];
                  if (!preview || (!preview.content && !preview.error && !preview.loading)) return null;
                  return (
                    <div key={`${previewKey}-preview`} className={styles.evidencePreview}>
                      <div className={styles.evidencePreviewHead}>
                        <strong>{preview.name || artifact.label}</strong>
                        <small>
                          {userFacingEvidencePath(preview.path || artifact.path)}
                          {typeof preview.sizeBytes === "number" ? ` · ${Math.ceil(preview.sizeBytes / 1024)} KB` : ""}
                          {preview.truncated ? " · 已截断" : ""}
                        </small>
                      </div>
                      {preview.error ? (
                        <p className={styles.evidenceError}>{preview.error}</p>
                      ) : preview.loading ? (
                        <p className={styles.evidenceError}>正在读取证据预览...</p>
                      ) : (
                        <pre className={styles.evidenceContent}>{preview.content}</pre>
                      )}
                    </div>
                  );
                })}
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
                    title="去能力工坊：Git 版本索引与回退登记"
                  >
                    去能力工坊
                  </Link>
                ) : null}
                {seatIdentityIds.has(msg.recipient_id || "")
                && ["agent_command", "requirement_dispatch", "comment_message"].includes((msg.message_type || "").toLowerCase())
                && ["queued", "pending", "acked", "in_progress"].includes((msg.status || "").toLowerCase()) ? (
                  msg.id === activeQueueMessageId ? (
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
                  ) : (
                    <small className={styles.muted}>已在指令队列中；先处理队列顶部那条，避免误启动旧任务。</small>
                  )
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
              : sendNote || (seat.permissionLevel ? `风险级别 ${seat.permissionLevel} · ${processTraceHint(seat)}` : "发送后写入协作池；NPC 处理，平台同步最小回执和最终结果")}
          </small>
          <div className={styles.composerActions}>
            <Link href={`/projects/${projectId}/company`} className={styles.linkBtn} title="返回公司运行状态">
              公司层
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
      </div>
    </article>
  );
}
