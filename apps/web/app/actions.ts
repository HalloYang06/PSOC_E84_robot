"use server";

import { createHash } from "node:crypto";
import { closeSync, existsSync, mkdirSync, openSync, type Dirent } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { execFileSync, spawn } from "node:child_process";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { isRedirectError } from "next/dist/client/components/redirect";

import {
  buildCodexSeatConsumerScriptName,
  cleanupCodexSeatAutonomyArtifacts,
  ensureCodexSeatHeartbeatAutomation,
  isCodexSessionWorkstationId,
  readCodexSeatAutonomyStatus,
} from "../lib/codex-seat-bridge";
import {
  cleanupClaudeSeatSessionRegistration,
  ensureClaudeSeatSessionRegistration,
  launchClaudeSeatMessageBridge,
  launchClaudeSeatSession,
  readClaudeSeatAutonomyStatus,
} from "../lib/claude-seat-bridge";
import { getApiBaseUrl } from "../lib/config";
import { appendProjectCodexCommand, syncProjectCodexDispatchInboxFromRecords } from "../lib/local-agent-bridge";
import { buildNpcKnowledgeProfile } from "../lib/npc-knowledge";
import { summarizeNpcProvisioning } from "../lib/npc-provisioning";
import {
  collabDebugPolicySummary,
  collabEfficiencyPolicySummary,
  collabProjectProfileLabel,
  collabProtocolApprovalLabel,
  collabProtocolWorkKindLabel,
  collabRunawayPolicySummary,
  collabTokenPolicySummary,
  type PlatformProjectProfile,
  resolvePlatformCollabProtocol,
} from "../lib/platform-collab-protocol";
import {
  buildPlatformRepoReferencePaths,
  platformRepoContextSummary,
  resolvePlatformRepoContext,
} from "../lib/platform-repo-context";
import {
  derivePlatformProviderIdFromThreadId,
  normalizePlatformProviderId,
  platformProviderEndpoint,
  platformProviderIdFromSeat,
  platformProviderLabel,
  isNpcSeatRecord,
  seatTypeForProvider,
  supportsLocalCodexAutonomyBridge,
} from "../lib/platform-provider";
import { summarizeRunnerDispatchState } from "../lib/runner-status";
import {
  DEFAULT_PLATFORM_SKILL_LIBRARY,
  RESERVED_PLATFORM_SKILL_IDS,
  mergePlatformSkillLoadout,
  splitPlatformSkillLoadout,
} from "../lib/platform-skills";
import {
  normalizeDevelopmentWorkshopStation,
  normalizeDevelopmentWorkshopStations,
} from "../lib/development-workshop";

const ACCESS_TOKEN_COOKIE = "farm_access_token";
const USER_COOKIE = "farm_user";

function rethrowRedirectError(error: unknown) {
  if (isRedirectError(error)) {
    throw error;
  }
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function getAuthHeaders() {
  const cookieStore = cookies();
  const accessToken = cookieStore.get(ACCESS_TOKEN_COOKIE)?.value;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  return headers;
}

async function postJson(path: string, body: Record<string, unknown>) {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    let errorCode = `HTTP_${res.status}`;
    let errorMessage = `HTTP ${res.status}`;
    let errorDetails: unknown;
    try {
      const payload = await res.json();
      errorCode = payload?.error?.code ?? errorCode;
      errorMessage = payload?.error?.message ?? errorMessage;
      errorDetails = payload?.error?.details;
    } catch {}
    const error = new Error(errorMessage) as Error & {
      status?: number;
      code?: string;
      details?: unknown;
    };
    error.status = res.status;
    error.code = errorCode;
    error.details = errorDetails;
    throw error;
  }
  return res.json();
}

async function getJson(path: string) {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    let errorCode = `HTTP_${res.status}`;
    let errorMessage = `HTTP ${res.status}`;
    let errorDetails: unknown;
    try {
      const payload = await res.json();
      errorCode = payload?.error?.code ?? errorCode;
      errorMessage = payload?.error?.message ?? errorMessage;
      errorDetails = payload?.error?.details;
    } catch {}
    const error = new Error(errorMessage) as Error & {
      status?: number;
      code?: string;
      details?: unknown;
    };
    error.status = res.status;
    error.code = errorCode;
    error.details = errorDetails;
    throw error;
  }
  return res.json();
}

function isProjectCollaborator(currentUser: any, project: any, members: any[]) {
  if (!currentUser) return false;
  if (project?.is_owner) return true;
  const currentId = String(currentUser.id ?? "").trim();
  const currentEmail = String(currentUser.email ?? "").trim().toLowerCase();
  const role = String(project?.role ?? "").trim().toLowerCase();
  if (role && role !== "guest") return true;
  return members.some((member) => {
    const memberId = String(
      member.user_id ?? member.userId ?? member.id ?? member.user?.id ?? member.member_id ?? "",
    ).trim();
    const memberEmail = String(member.email ?? member.user?.email ?? "").trim().toLowerCase();
    return (currentId && memberId === currentId) || (currentEmail && memberEmail === currentEmail);
  });
}

async function ensureProjectCollaborationAccess(projectId: string) {
  const meResult = await getJson("/api/auth/me");
  const currentUser = meResult?.data?.user ?? meResult?.user ?? null;
  if (!currentUser?.id && !currentUser?.email) {
    const error = new Error("需要先登录") as Error & { code?: string };
    error.code = "AUTH_REQUIRED";
    throw error;
  }

  const projectResult = await getJson(`/api/projects/${projectId}`);
  const project = projectResult?.data ?? projectResult ?? {};
  const membersResult = await getJson(`/api/auth/projects/${projectId}/members`);
  const members = Array.isArray(membersResult?.data)
    ? membersResult.data
    : Array.isArray(membersResult)
      ? membersResult
      : [];

  if (!isProjectCollaborator(currentUser, project, members)) {
    const error = new Error("请先通过项目邀请加入协作，再操作这台电脑或线程。") as Error & {
      code?: string;
    };
    error.code = "PROJECT_MEMBERSHIP_REQUIRED";
    throw error;
  }

  return { currentUser, project, members };
}

async function resolveProjectHumanActorId(projectId: string) {
  const { currentUser } = await ensureProjectCollaborationAccess(projectId);
  return text(currentUser?.id ?? currentUser?.email, "human-chief");
}

async function patchJson(path: string, body: Record<string, unknown>) {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "PATCH",
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    let errorCode = `HTTP_${res.status}`;
    let errorMessage = `HTTP ${res.status}`;
    try {
      const payload = await res.json();
      errorCode = payload?.error?.code ?? errorCode;
      errorMessage = payload?.error?.message ?? errorMessage;
    } catch {}
    const error = new Error(errorMessage) as Error & { status?: number; code?: string };
    error.status = res.status;
    error.code = errorCode;
    throw error;
  }
  return res.json();
}

async function deleteJson(path: string) {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    let errorCode = `HTTP_${res.status}`;
    let errorMessage = `HTTP ${res.status}`;
    try {
      const payload = await res.json();
      errorCode = payload?.error?.code ?? errorCode;
      errorMessage = payload?.error?.message ?? errorMessage;
    } catch {}
    const error = new Error(errorMessage) as Error & { status?: number; code?: string };
    error.status = res.status;
    error.code = errorCode;
    throw error;
  }
  return res.json();
}

function encodeRepoPathForRoute(value: string) {
  return value.split("/").map((part) => encodeURIComponent(part)).join("/");
}

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function slugifyAscii(value: unknown, fallback = "item") {
  const normalized = text(value, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || fallback;
}

function booleanFromUnknown(value: unknown, fallback = false) {
  if (typeof value === "boolean") return value;
  const normalized = text(value, "").toLowerCase();
  if (!normalized) return fallback;
  return !["false", "0", "off", "no"].includes(normalized);
}

function readBooleanFormField(formData: FormData, name: string, fallback = false) {
  const values = formData.getAll(name);
  if (!values.length) return fallback;
  for (const entry of values) {
    const normalized = text(entry, "").toLowerCase();
    if (!normalized) continue;
    return !["false", "0", "off", "no"].includes(normalized);
  }
  return fallback;
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function normalizeProjectReturnPath(projectId: string, value: unknown, fallbackTab = "skills") {
  const raw = text(value, "");
  if (raw.startsWith(`/projects/${projectId}`) && isSafeLocalReturnPath(raw)) return raw;
  return `/projects/${projectId}?panel=team&tab=${fallbackTab}`;
}

function normalizeWorkspaceReturnPath(value: unknown, fallback = "/projects") {
  const raw = text(value, "");
  if ((raw.startsWith("/projects") || raw.startsWith("/members")) && isSafeLocalReturnPath(raw)) return raw;
  return fallback;
}

function normalizeAuthReturnPath(value: unknown, fallback = "/projects") {
  const raw = text(value, "");
  if (
    isSafeLocalReturnPath(raw)
    && (
      raw === "/projects"
      || raw.startsWith("/projects/")
      || raw.startsWith("/projects?")
      || raw === "/members"
      || raw.startsWith("/members?")
    )
  ) {
    return raw;
  }
  return fallback;
}

function isSafeLocalReturnPath(value: string) {
  if (!value || !value.startsWith("/")) return false;
  if (value.startsWith("//")) return false;
  if (/[\\\u0000-\u001f\u007f]/.test(value)) return false;
  return !/^[a-z][a-z0-9+.-]*:/i.test(value);
}

function readSeatAutomationEnabled(
  metadata: Record<string, unknown> | null | undefined,
  fallback = true,
) {
  if (!metadata || typeof metadata !== "object") return fallback;
  return booleanFromUnknown(metadata.automation_enabled, fallback);
}

const DEFAULT_AUTOMATION_HEARTBEAT_SECONDS = 60;
const MIN_AUTOMATION_HEARTBEAT_SECONDS = 15;
const MAX_AUTOMATION_HEARTBEAT_SECONDS = 3600;

function normalizeAutomationHeartbeatSeconds(value: unknown, fallback = DEFAULT_AUTOMATION_HEARTBEAT_SECONDS) {
  const parsed = Number(value);
  const candidate = Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed) : fallback;
  return Math.min(MAX_AUTOMATION_HEARTBEAT_SECONDS, Math.max(MIN_AUTOMATION_HEARTBEAT_SECONDS, candidate));
}

function readSeatAutomationHeartbeatSeconds(
  metadata: Record<string, unknown> | null | undefined,
  fallback = DEFAULT_AUTOMATION_HEARTBEAT_SECONDS,
) {
  if (!metadata || typeof metadata !== "object") return normalizeAutomationHeartbeatSeconds(fallback);
  return normalizeAutomationHeartbeatSeconds(metadata.automation_heartbeat_seconds, fallback);
}

function withQueryValue(path: string, key: string, value: string) {
  const [pathPart, hashPart = ""] = path.split("#", 2);
  const [pathname, queryPart = ""] = pathPart.split("?", 2);
  const params = new URLSearchParams(queryPart);
  params.set(key, value);
  const query = params.toString();
  return `${pathname}${query ? `?${query}` : ""}${hashPart ? `#${hashPart}` : ""}`;
}

function withoutQueryKeys(path: string, keys: string[]) {
  const [pathPart, hashPart = ""] = path.split("#", 2);
  const [pathname, queryPart = ""] = pathPart.split("?", 2);
  const params = new URLSearchParams(queryPart);
  keys.forEach((key) => params.delete(key));
  const query = params.toString();
  return `${pathname}${query ? `?${query}` : ""}${hashPart ? `#${hashPart}` : ""}`;
}

function encodePreviewState(value: unknown) {
  return Buffer.from(JSON.stringify(value), "utf8").toString("base64url");
}

type CollaborationMessagePayload = {
  project_id: string | null;
  task_id: string | null;
  approval_id: string | null;
  handoff_id: string | null;
  requirement_id: string | null;
  agent_id: string | null;
  message_type: string;
  title: string | null;
  body: string;
  sender_type: string;
  sender_id: string | null;
  recipient_type: string | null;
  recipient_id: string | null;
  status: string;
};

const AI_REQUIRED_REQUIREMENT_LEDGER_PATH = "docs/ai-requirements/ai-required-requirements-ledger.md";
const AI_REQUIRED_REQUIREMENT_LEDGER_SENTINEL = "AI_REQUIRED_REQUIREMENT_LEDGER_V1";
const AI_REQUIRED_REQUIREMENT_LEDGER_END = "AI_REQUIRED_REQUIREMENT_LEDGER_END";

function normalizeMessageFormValue(value: FormDataEntryValue | null | undefined) {
  const next = String(value ?? "").trim();
  return next || null;
}

function readCollaborationMessagePayload(formData: FormData): CollaborationMessagePayload {
  return {
    project_id: normalizeMessageFormValue(formData.get("project_id")),
    task_id: normalizeMessageFormValue(formData.get("task_id")),
    approval_id: normalizeMessageFormValue(formData.get("approval_id")),
    handoff_id: normalizeMessageFormValue(formData.get("handoff_id")),
    requirement_id: normalizeMessageFormValue(formData.get("requirement_id")),
    agent_id: normalizeMessageFormValue(formData.get("agent_id")),
    message_type: normalizeMessageFormValue(formData.get("message_type")) ?? "comment_message",
    title: normalizeMessageFormValue(formData.get("title")),
    body: String(formData.get("body") ?? "").trim(),
    sender_type: normalizeMessageFormValue(formData.get("sender_type")) ?? "human",
    sender_id: normalizeMessageFormValue(formData.get("sender_id")),
    recipient_type: normalizeMessageFormValue(formData.get("recipient_type")),
    recipient_id: normalizeMessageFormValue(formData.get("recipient_id")),
    status: normalizeMessageFormValue(formData.get("status")) ?? "open",
  };
}

function buildCollaborationMessagePreviewSignature(payload: CollaborationMessagePayload, senderId: string | null) {
  const normalized = {
    project_id: payload.project_id,
    task_id: payload.task_id,
    approval_id: payload.approval_id,
    handoff_id: payload.handoff_id,
    requirement_id: payload.requirement_id,
    agent_id: payload.agent_id,
    message_type: payload.message_type,
    title: payload.title,
    body: payload.body,
    sender_type: "human",
    sender_id: senderId,
    recipient_type: payload.recipient_type,
    recipient_id: payload.recipient_id,
    status: payload.status,
  };
  return createHash("sha256").update(JSON.stringify(normalized)).digest("hex").slice(0, 24);
}

function collaborationMessageShouldCarryRequiredLedger(payload: { message_type?: unknown }) {
  const messageType = text(payload.message_type, "");
  return messageType === "agent_command" || messageType === "requirement_dispatch";
}

function buildAiRequiredRequirementLedgerBlock(
  payload: {
    project_id?: unknown;
    requirement_id?: unknown;
    title?: unknown;
    sender_type?: unknown;
    sender_id?: unknown;
    recipient_type?: unknown;
    recipient_id?: unknown;
  },
  options: {
    requesterLabel?: string | null;
    assigneeLabel?: string | null;
    automationMode?: string | null;
    heartbeatInterval?: string | null;
    reviewPolicy?: string | null;
    executionMode?: string | null;
    estimatedTokens?: number | null;
    gitRepositoryLine?: string | null;
    gitIdentityLine?: string | null;
    gitCredentialLine?: string | null;
    gitLocalPathPolicyLine?: string | null;
    gitReviewBoundaryLine?: string | null;
  } = {},
) {
  const requester =
    text(options.requesterLabel, "") ||
    [text(payload.sender_type, "human"), text(payload.sender_id, "")].filter(Boolean).join(":") ||
    "human";
  const assignee =
    text(options.assigneeLabel, "") ||
    [text(payload.recipient_type, "target"), text(payload.recipient_id, "")].filter(Boolean).join(":") ||
    "target";
  const automationMode = text(options.automationMode, "off");
  const heartbeatInterval = text(options.heartbeatInterval, automationMode === "heartbeat" ? "未设置" : "不开启");
  const reviewPolicy = text(options.reviewPolicy, "高风险、硬件、删除/发布/回滚、跨账号/跨项目、持续自动化、需求不清时必须人审");
  const executionMode = text(options.executionMode, "先最小回执，再做当前一轮；不确定就停下等人确认");
  const estimatedTokens = typeof options.estimatedTokens === "number" ? String(options.estimatedTokens) : "未估算";
  const gitRepositoryLine = text(options.gitRepositoryLine, "GitHub 仓库未绑定；跨电脑协作只能先做只读规划并请求人补仓库地址");
  const gitIdentityLine = text(options.gitIdentityLine, "未绑定 GitHub 账号；需要写仓库前先请求人补账号/凭据来源");
  const gitCredentialLine = text(options.gitCredentialLine, "不允许在消息正文粘贴明文 token；使用 Runner 环境变量、SSH Agent、GitHub App 或 OAuth");
  const gitLocalPathPolicyLine = text(options.gitLocalPathPolicyLine, "每台电脑自行决定本地 clone 路径；AI 不要把自己电脑的绝对路径硬发给其他电脑");
  const gitReviewBoundaryLine = text(options.gitReviewBoundaryLine, "clone/status/diff/read-only 可按权限执行；push/pull/reset/revert/delete/release/跨账号访问必须先人审");
  return [
    AI_REQUIRED_REQUIREMENT_LEDGER_SENTINEL,
    "固定 Skill: AI 必读需求表",
    `必读路径: ${AI_REQUIRED_REQUIREMENT_LEDGER_PATH}`,
    `项目: ${text(payload.project_id, "未绑定项目")}`,
    `需求 ID: ${text(payload.requirement_id, "") || text(payload.title, "临时协作指令")}`,
    `提需求者: ${requester}`,
    `被提需求者: ${assignee}`,
    `代码协作: ${gitRepositoryLine}`,
    `GitHub 身份: ${gitIdentityLine}`,
    `GitHub 凭据: ${gitCredentialLine}`,
    `本地路径规则: ${gitLocalPathPolicyLine}`,
    `Git 人审边界: ${gitReviewBoundaryLine}`,
    `自动化许可: ${automationMode}`,
    `心跳间隔: ${heartbeatInterval}`,
    `人审规则: ${reviewPolicy}`,
    `执行边界: ${executionMode}`,
    "显示边界: 真实处理过程留在绑定的 Codex / Claude Code / Runner 线程中；平台只回写最小回执、最终结果、阻塞原因和可追踪索引。",
    `预计 token: ${estimatedTokens}`,
    "开工前动作:",
    `1. 先阅读 ${AI_REQUIRED_REQUIREMENT_LEDGER_PATH}，确认自己是不是被提需求者。`,
    "2. 先回最小回执：我接到什么、边界是什么、是否需要人审、下一步只做哪一轮。",
    "3. 涉及跨电脑代码协作时，优先使用上面的 GitHub 仓库；本地路径由当前电脑自己决定，不要照抄其他电脑路径。",
    "4. 未开启自动化时，只执行本条指令；开启自动化也不能越过人审边界。",
    "5. 完成后写最终回复；若要交给下游 AI，必须新增下一条需求，不要私下连续喊话。",
    AI_REQUIRED_REQUIREMENT_LEDGER_END,
  ].join("\n");
}

function withAiRequiredRequirementLedger<T extends { body?: string; message_type?: unknown }>(
  payload: T,
  options: Parameters<typeof buildAiRequiredRequirementLedgerBlock>[1] = {},
): T {
  if (!collaborationMessageShouldCarryRequiredLedger(payload)) return payload;
  const body = text(payload.body, "");
  if (body.includes(AI_REQUIRED_REQUIREMENT_LEDGER_SENTINEL)) return payload;
  return {
    ...payload,
    body: `${buildAiRequiredRequirementLedgerBlock(payload as Record<string, unknown>, options)}\n\n${body}`,
  };
}

function workstationLookupKeys(item: Record<string, unknown>) {
  const metadata =
    item.metadata && typeof item.metadata === "object" ? (item.metadata as Record<string, unknown>) : {};
  const extraData =
    item.extra_data && typeof item.extra_data === "object" ? (item.extra_data as Record<string, unknown>) : {};
  return [
    item.id,
    item.workstation_id,
    item.config_id,
    item.row_id,
    item.source_workstation_id,
    metadata.source_workstation_id,
    extraData.source_workstation_id,
  ]
    .map((candidate) => text(candidate, ""))
    .filter(Boolean);
}

function resolveCodexWorkstationContext(
  workstations: Record<string, unknown>[],
  workstationId: string,
  project?: Record<string, unknown> | null,
) {
  const matched =
    workstations.find((item) => workstationLookupKeys(item).some((candidate) => candidate === workstationId)) ?? null;
  const metadata =
    matched?.metadata && typeof matched.metadata === "object" ? (matched.metadata as Record<string, unknown>) : {};
  const baseCollabProtocol = resolvePlatformCollabProtocol(metadata.collab_protocol, {
    providerId:
      text(matched?.ai_provider_id ?? matched?.provider_id ?? metadata.provider_id, "") ||
      (isCodexSessionWorkstationId(workstationId) ? "codex" : ""),
    roleText: text(matched?.responsibility ?? metadata.responsibility, ""),
    threadText: text(matched?.name ?? matched?.workstation_name, ""),
  });
  const collabProtocol =
    project && typeof project === "object"
      ? enrichNpcCollabProtocolWithRepoContext(project, baseCollabProtocol, {
          gitBoundary: asArray(matched?.git_boundary ?? metadata.git_boundary).map((item) => text(item)).filter(Boolean),
          handoffPath:
            text(
              metadata.npc_knowledge && typeof metadata.npc_knowledge === "object"
                ? (metadata.npc_knowledge as Record<string, unknown>).handoff_path
                : "",
              "",
            ) || null,
        })
      : baseCollabProtocol;
  const referencePaths = buildPlatformRepoReferencePaths({
    referencePaths: collabProtocol.reference_paths,
    repositoryUrl: collabProtocol.repo_context?.repository_url ?? null,
    branch: collabProtocol.repo_context?.branch ?? null,
    gitBoundary: asArray(matched?.git_boundary ?? metadata.git_boundary).map((item) => text(item)).filter(Boolean),
    handoffPath: text(metadata.npc_knowledge && typeof metadata.npc_knowledge === "object" ? (metadata.npc_knowledge as Record<string, unknown>).handoff_path : "", "") || null,
    workspaceRoots: [workspaceRoot(), text(matched?.local_git_url ?? metadata.local_git_url, "")].filter(Boolean),
  });
  return {
    workstationName: text(matched?.name ?? matched?.workstation_name, workstationId) || "Codex 主工位",
    provider:
      text(matched?.ai_provider ?? matched?.ai_provider_label ?? metadata.ai_provider, "") ||
      (isCodexSessionWorkstationId(workstationId) ? "codex" : ""),
    computerNodeId:
      text(matched?.computer_node_id ?? matched?.computerNodeId ?? metadata.computer_node_id, "") || null,
    computerNodeLabel:
      text(
        matched?.computer_node ??
          matched?.computerNode ??
          matched?.computer_node_label ??
          matched?.computerNodeLabel ??
          metadata.computer_node,
        "",
      ) || null,
    skillLoadout: mergePlatformSkillLoadout(
      matched?.skill_loadout,
      matched?.skillLoadout,
      metadata.additional_skill_ids,
      metadata.skill_loadout,
    ),
    repoSummary: collabProtocol.repo_context ? platformRepoContextSummary(collabProtocol.repo_context) : null,
    referencePaths,
  };
}

async function syncPlatformCodexDispatchInbox(projectId: string) {
  const [messagesResult, workstationsResult, projectResult] = await Promise.all([
    getJson(
      `/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&message_type=requirement_dispatch`,
    ),
    getJson(`/api/collaboration/projects/${encodeURIComponent(projectId)}/thread-workstations`),
    getJson(`/api/projects/${encodeURIComponent(projectId)}`),
  ]);

  return syncProjectCodexDispatchInboxFromRecords({
    projectId,
    dispatchMessages: asArray<Record<string, unknown>>(messagesResult?.data ?? messagesResult),
    workstations: asArray<Record<string, unknown>>(workstationsResult?.data ?? workstationsResult),
    project:
      projectResult && typeof projectResult === "object"
        ? ((projectResult.data ?? projectResult) as Record<string, unknown>)
        : null,
    issuer: "平台自治推进",
  });
}

async function postAgentSeatJson(projectId: string, workstationId: string, body: Record<string, unknown>) {
  const res = await fetch(
    `${getApiBaseUrl()}/api/collaboration/projects/${projectId}/thread-workstations/${workstationId}/messages`,
    {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(body),
      cache: "no-store",
    },
  );
  if (!res.ok) {
    let errorCode = `HTTP_${res.status}`;
    let errorMessage = `HTTP ${res.status}`;
    try {
      const payload = await res.json();
      errorCode = payload?.error?.code ?? errorCode;
      errorMessage = payload?.error?.message ?? errorMessage;
    } catch {}
    const error = new Error(errorMessage) as Error & { status?: number; code?: string };
    error.status = res.status;
    error.code = errorCode;
    throw error;
  }
  return res.json();
}

function parseOptionalJson(text: string): unknown {
  if (!text.trim()) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function parseStringList(value: FormDataEntryValue | null): string[] | null {
  const items = String(value ?? "")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length ? items : null;
}

function parseStringListAll(formData: FormData, field: string): string[] | null {
  const direct = formData
    .getAll(field)
    .map((item) => String(item ?? "").trim())
    .filter(Boolean);
  if (direct.length) return direct;
  return parseStringList(formData.get(field));
}

function normalizeUnknownStringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => text(item)).filter(Boolean);
  if (typeof value === "string") return parseStringList(value) ?? [];
  return [];
}

function normalizeStringList(value: unknown) {
  return (Array.isArray(value) ? value : typeof value === "string" ? value.split(/[\n,]/) : [])
    .map((item) => text(item))
    .filter(Boolean);
}

function repoRelativePath(value: unknown) {
  return text(value, "").replace(/\\/g, "/").replace(/^\/+/, "");
}

function readRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function recordId(item: Record<string, unknown>) {
  return text(item.id ?? item.config_id ?? item.row_id, "");
}

function displaySlug(value: unknown, fallback = "item") {
  return slugifyAscii(text(value, ""), fallback).replace(/^-+|-+$/g, "") || fallback;
}

function recordIdentitySet(item: Record<string, unknown>) {
  const metadata = readRecord(item.metadata);
  const extraData = readRecord(item.extra_data ?? item.extraData);
  return new Set(
    [
      item.id,
      item.config_id,
      item.row_id,
      item.rowId,
      item.name,
      item.workstation_name,
      item.agent_id,
      item.agentId,
      item.source_workstation_id,
      metadata.source_workstation_id,
      metadata.bound_thread_id,
      extraData.source_workstation_id,
    ]
      .map((value) => text(value, ""))
      .filter(Boolean),
  );
}

function readProjectCollaborationConfig(project: Record<string, unknown> | null | undefined) {
  return project?.collaboration_config && typeof project.collaboration_config === "object"
    ? ({ ...(project.collaboration_config as Record<string, unknown>) } as Record<string, unknown>)
    : {};
}

function normalizeGithubCredentialSource(value: unknown) {
  const normalized = text(value, "runner_env");
  return ["github_app", "oauth", "runner_env", "ssh_agent", "manual_review"].includes(normalized)
    ? normalized
    : "runner_env";
}

function githubCredentialSourceLabel(value: unknown) {
  const source = normalizeGithubCredentialSource(value);
  return (
    {
      github_app: "GitHub App",
      oauth: "OAuth 授权",
      runner_env: "Runner 环境变量",
      ssh_agent: "SSH Agent",
      manual_review: "人工审批后手动执行",
    } as Record<string, string>
  )[source];
}

function looksLikeRawGithubCredential(value: unknown) {
  const raw = text(value, "");
  if (!raw) return false;
  if (/^(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}$/i.test(raw)) return true;
  if (/^github_pat_[A-Za-z0-9_]{40,}$/i.test(raw)) return true;
  if (/-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(raw)) return true;
  return false;
}

function safeGithubCredentialRef(value: unknown) {
  const raw = text(value, "");
  if (!raw) return "";
  return looksLikeRawGithubCredential(raw) ? "疑似明文密钥（已隐藏，请改用环境变量名）" : raw;
}

function readProjectGithubAccountBinding(project: Record<string, unknown> | null | undefined) {
  const collaborationConfig = readProjectCollaborationConfig(project);
  const raw =
    collaborationConfig.github_account_binding && typeof collaborationConfig.github_account_binding === "object"
      ? (collaborationConfig.github_account_binding as Record<string, unknown>)
      : {};
  const accountLogin = text(raw.account_login ?? raw.login, "");
  const credentialSource = normalizeGithubCredentialSource(raw.credential_source);
  const credentialRef = safeGithubCredentialRef(raw.credential_ref);
  const defaultCloneProtocol = ["https", "ssh"].includes(text(raw.default_clone_protocol, "https"))
    ? text(raw.default_clone_protocol, "https")
    : "https";
  if (!accountLogin && !credentialRef && !text(raw.profile_url, "")) return null;
  return {
    accountLogin,
    accountType: text(raw.account_type, "user"),
    profileUrl: text(raw.profile_url, accountLogin ? `https://github.com/${accountLogin}` : ""),
    credentialSource,
    credentialSourceLabel: githubCredentialSourceLabel(credentialSource),
    credentialRef,
    defaultCloneProtocol,
    permissionScopes: normalizeStringList(raw.permission_scopes),
    secretStorage: text(raw.secret_storage, "not_stored_in_project_config"),
  };
}

function buildProjectGitCollaborationContext(project: Record<string, unknown> | null | undefined) {
  const repositoryUrl = text(project?.github_url ?? project?.githubUrl, "");
  const branch = text(project?.develop_branch ?? project?.developBranch ?? project?.default_branch ?? project?.defaultBranch, "");
  const localMirror = text(project?.local_git_url ?? project?.localGitUrl, "");
  const binding = readProjectGithubAccountBinding(project);
  const repoLabel = repositoryUrl
    ? `优先使用 GitHub 仓库 ${repositoryUrl}${branch ? ` / 分支 ${branch}` : ""}`
    : branch
      ? `仓库地址未绑定，仅记录目标分支 ${branch}；需要跨电脑执行前先补 GitHub 仓库地址`
      : "GitHub 仓库未绑定；跨电脑协作只能先做只读规划并请求人补仓库地址";
  const localPathPolicy = localMirror
    ? `本机镜像可参考 ${localMirror}；其他电脑必须自行决定本地 clone 路径，不要复用这台电脑的绝对路径`
    : "每台电脑自行决定本地 clone 路径；AI 不要把自己电脑的绝对路径硬发给其他电脑";
  const identity = binding?.accountLogin
    ? `${binding.accountLogin} / ${binding.accountType} / 默认 ${binding.defaultCloneProtocol.toUpperCase()}`
    : "未绑定 GitHub 账号；需要写仓库前先请求人补账号/凭据来源";
  const credential = binding
    ? `${binding.credentialSourceLabel}${binding.credentialRef ? ` / ${binding.credentialRef}` : ""} / ${binding.secretStorage}`
    : "不允许在消息正文粘贴明文 token；使用 Runner 环境变量、SSH Agent、GitHub App 或 OAuth";
  return {
    repositoryLine: repoLabel,
    identityLine: identity,
    credentialLine: credential,
    localPathPolicyLine: localPathPolicy,
    reviewBoundaryLine: "clone/status/diff/read-only 可按权限执行；push/pull/reset/revert/delete/release/跨账号访问必须先人审",
  };
}

function appendGitCollaborationContextToNotes(
  project: Record<string, unknown> | null | undefined,
  notes: string,
  fallback: string,
) {
  const gitContext = buildProjectGitCollaborationContext(project);
  return [
    notes || fallback,
    "",
    "GitHub 协作上下文:",
    `- 代码协作: ${gitContext.repositoryLine}`,
    `- GitHub 身份: ${gitContext.identityLine}`,
    `- GitHub 凭据: ${gitContext.credentialLine}`,
    `- 本地路径规则: ${gitContext.localPathPolicyLine}`,
    `- Git 人审边界: ${gitContext.reviewBoundaryLine}`,
  ].join("\n");
}

function buildProjectGitPreflightCommandBody(
  project: Record<string, unknown> | null | undefined,
  options: {
    action: "sync" | "rollback";
    provider?: string;
    targetRef?: string;
    notes?: string;
    requestedBy?: string;
  },
) {
  const gitContext = buildProjectGitCollaborationContext(project);
  const binding = readProjectGithubAccountBinding(project);
  const provider = text(options.provider, "github");
  const githubUrl = text(project?.github_url ?? project?.githubUrl, "");
  const localGitUrl = text(project?.local_git_url ?? project?.localGitUrl, "");
  const repositoryUrl = provider === "local" ? localGitUrl || githubUrl : githubUrl || localGitUrl;
  const branch = text(project?.develop_branch ?? project?.developBranch ?? project?.default_branch ?? project?.defaultBranch, "");
  return {
    kind: "git.preflight",
    version: "git-preflight.v1",
    action: options.action,
    provider,
    dry_run: true,
    repository_url: repositoryUrl,
    branch,
    target_ref: text(options.targetRef, ""),
    credential_source: binding?.credentialSource ?? "manual_review",
    credential_ref: binding?.credentialRef ?? "",
    credential_identity: binding?.accountLogin ?? "",
    local_path_policy: gitContext.localPathPolicyLine,
    human_review_boundary: gitContext.reviewBoundaryLine,
    requested_at: new Date().toISOString(),
    requested_by: text(options.requestedBy, "human-chief"),
    notes: text(options.notes, ""),
    expected_reply: {
      message_type: "runner_result",
      data_key: "git_preflight",
      must_not_execute: ["clone", "pull", "push", "reset", "revert", "delete", "release"],
    },
  };
}

async function dispatchProjectGitPreflightToRunners(
  projectId: string,
  project: Record<string, unknown> | null | undefined,
  options: {
    action: "sync" | "rollback";
    provider?: string;
    targetRef?: string;
    notes?: string;
    requestedBy?: string;
  },
) {
  const result = await getJson(`/api/collaboration/projects/${projectId}/computer-nodes`);
  const nodes = asArray<Record<string, unknown>>(result?.data ?? result);
  const onlineNodes = nodes.filter((node) => {
    const extraData = readRecord(node.extra_data ?? node.extraData);
    const status = text(node.status, "").toLowerCase();
    const runnerStatus = text(extraData.runner_effective_status ?? extraData.runner_status, "").toLowerCase();
    const watchState = text(extraData.runner_watch_state, "").toLowerCase();
    return (
      status === "online" ||
      runnerStatus === "online" ||
      watchState === "watching"
    );
  });
  const runnableNodes = nodes.filter((node) => {
    const nodeId = text(node.id ?? node.node_id ?? node.config_id ?? node.label, "");
    const runnerId = text(node.runner_id ?? node.runnerId, "");
    const extraData = readRecord(node.extra_data ?? node.extraData);
    const status = text(node.status, "").toLowerCase();
    const runnerStatus = text(extraData.runner_effective_status ?? extraData.runner_status, "").toLowerCase();
    const watchState = text(extraData.runner_watch_state, "").toLowerCase();
    const isOnline =
      status === "online" ||
      runnerStatus === "online" ||
      watchState === "watching";
    return Boolean(nodeId && runnerId && isOnline);
  });
  const body = buildProjectGitPreflightCommandBody(project, options);
  let queued = 0;
  let failed = 0;
  for (const node of runnableNodes) {
    const nodeId = text(node.id ?? node.node_id ?? node.config_id ?? node.label, "");
    try {
      await postJson(`/api/collaboration/projects/${projectId}/runner-commands`, {
        computer_node_id: nodeId,
        title: options.action === "rollback" ? `Git 回退只读预检 / ${text(options.targetRef, "未填写目标")}` : "Git 同步只读预检",
        body: JSON.stringify(body, null, 2),
      });
      queued += 1;
    } catch {
      failed += 1;
    }
  }
  return {
    queued,
    failed,
    availableNodeCount: nodes.length,
    onlineNodeCount: onlineNodes.length,
    runnableNodeCount: runnableNodes.length,
  };
}

function readProjectThreadWorkstations(project: Record<string, unknown> | null | undefined) {
  const collaborationConfig = readProjectCollaborationConfig(project);
  return asArray<Record<string, unknown>>(
    collaborationConfig.thread_workstations ??
      collaborationConfig.threadWorkstations ??
      collaborationConfig.workstations,
  );
}

function readDevelopmentWorkshopStations(project: Record<string, unknown> | null | undefined) {
  const collaborationConfig = readProjectCollaborationConfig(project);
  return normalizeDevelopmentWorkshopStations(collaborationConfig.development_workshop_stations);
}

function readProjectCollaborationActors(project: Record<string, unknown> | null | undefined) {
  const collaborationConfig = readProjectCollaborationConfig(project);
  return [
    ...readProjectThreadWorkstations(project),
    ...asArray<Record<string, unknown>>(collaborationConfig.codexSeats),
    ...asArray<Record<string, unknown>>(collaborationConfig.codex_seats),
    ...asArray<Record<string, unknown>>(collaborationConfig.npcSeats),
    ...asArray<Record<string, unknown>>(collaborationConfig.npc_seats),
  ];
}

function estimateMessageTokens(payload: CollaborationMessagePayload) {
  const raw = `${payload.title ?? ""}\n${payload.body ?? ""}`;
  const ascii = (raw.match(/[\x00-\x7F]/g) ?? []).length;
  const nonAscii = Math.max(0, raw.length - ascii);
  return Math.max(64, Math.ceil(ascii / 4 + nonAscii * 1.2));
}

function classifyCollaborationIntent(payload: CollaborationMessagePayload) {
  const raw = `${payload.title ?? ""}\n${payload.body ?? ""}`.toLowerCase();
  const hardwareRisk =
    /(机器人|机械臂|电机|舵机|上电|烧录|固件|串口|jtag|gpio|i2c|spi|usb|传感器|开发板|nanopi|stm32|arduino|robot|motor|servo|firmware|flash|serial)/i.test(raw);
  const destructiveRisk =
    /(删除|清空|回滚|重置|覆盖|发布|推送|生产|密钥|账号|跨项目|跨账号|rm -rf|reset --hard|force push|deploy|secret|token)/i.test(raw);
  const readOnlyHint = /(只读|阅读|调研|查资料|总结|审查|review|research|read-only|readonly)/i.test(raw);
  const simulationHint = /(仿真|模拟|沙盘|波形|日志回放|simulation|simulator|mock|dry run)/i.test(raw);
  const softwareHint = /(软件|前端|后端|ui|api|测试|构建|纯软件|web|react|next|python|typescript)/i.test(raw);
  return { hardwareRisk, destructiveRisk, readOnlyHint, simulationHint, softwareHint };
}

function resolveActorProtocolForPreview(
  project: Record<string, unknown> | null | undefined,
  payload: CollaborationMessagePayload,
) {
  const actors = readProjectCollaborationActors(project);
  const targetKeys = [
    payload.recipient_id,
    payload.agent_id,
    payload.handoff_id,
    payload.task_id,
  ]
    .map((item) => text(item, ""))
    .filter(Boolean);
  const matched =
    actors.find((actor) => {
      const keys = workstationLookupKeys(actor);
      return targetKeys.some((target) => keys.includes(target));
    }) ?? null;
  const metadata =
    matched?.metadata && typeof matched.metadata === "object" ? (matched.metadata as Record<string, unknown>) : {};
  const providerId =
    normalizePlatformProviderId(
      matched?.ai_provider_id ??
        matched?.ai_provider ??
        matched?.provider_id ??
        metadata.provider_id ??
        metadata.provider,
    ) ||
    derivePlatformProviderIdFromThreadId(
      matched?.source_workstation_id ??
        metadata.source_workstation_id ??
        matched?.id ??
        matched?.workstation_id ??
        payload.recipient_id,
    ) ||
    "codex";
  const actorLabel = text(
    matched?.name ??
      matched?.workstation_name ??
      matched?.label ??
      metadata.display_name ??
      payload.recipient_id ??
      payload.agent_id,
    "未选择 AI",
  );
  const roleText = text(matched?.responsibility ?? metadata.responsibility ?? payload.title, "");
  const protocol = resolvePlatformCollabProtocol(metadata.collab_protocol, {
    providerId,
    roleText,
    threadText: actorLabel,
  });
  return { actor: matched, actorLabel, providerId, protocol };
}

function buildCollaborationGovernancePreview(
  project: Record<string, unknown> | null | undefined,
  payload: CollaborationMessagePayload,
) {
  const { actorLabel, providerId, protocol } = resolveActorProtocolForPreview(project, payload);
  const intent = classifyCollaborationIntent(payload);
  const estimatedTokens = estimateMessageTokens(payload);
  const tokenPolicy = protocol.token_policy;
  const inferredProfile: PlatformProjectProfile = intent.hardwareRisk
    ? protocol.project_profile === "robotics"
      ? "robotics"
      : "embedded"
    : protocol.project_profile;
  const tokenOverMessageLimit = estimatedTokens > tokenPolicy.per_message_limit;
  const tokenOverRoundLimit = estimatedTokens > tokenPolicy.per_round_limit;
  const requiresHumanReview =
    protocol.approval_policy === "human_review_required" ||
    intent.hardwareRisk ||
    intent.destructiveRisk ||
    tokenOverMessageLimit ||
    protocol.debug_policy.hardware_write_requires_review;
  const shouldSimulateFirst =
    protocol.debug_policy.simulation_first || intent.hardwareRisk || intent.simulationHint;
  const readonlyFirst = protocol.efficiency_policy.prefer_readonly_probe || intent.readOnlyHint || intent.hardwareRisk;
  const riskLevel = tokenOverRoundLimit || (intent.hardwareRisk && intent.destructiveRisk)
    ? "high"
    : requiresHumanReview
      ? "medium"
      : "low";
  const modeLabel = requiresHumanReview
    ? shouldSimulateFirst
      ? "先仿真/只读，等人工确认"
      : "先最小回执，等人工审核"
    : "可单次执行；开自动化才续推";
  const warnings = [
    tokenOverMessageLimit
      ? `预计 ${estimatedTokens} token，超过该 NPC 单条预算 ${tokenPolicy.per_message_limit}，建议先摘要或拆分。`
      : "",
    tokenOverRoundLimit
      ? `预计 ${estimatedTokens} token，已经超过单轮预算 ${tokenPolicy.per_round_limit}，不建议自动执行。`
      : "",
    intent.hardwareRisk
      ? "检测到机器人/嵌入式/真实设备语义：必须先仿真或只读探针，真实硬件写入要人工确认。"
      : "",
    intent.destructiveRisk
      ? "检测到删除、回滚、发布、密钥、跨账号/跨项目等高风险语义：必须人工审核。"
      : "",
  ].filter(Boolean);
  const notes = [
    `${collabProjectProfileLabel(inferredProfile)} / ${collabProtocolWorkKindLabel(protocol.work_kind)} / ${collabProtocolApprovalLabel(protocol.approval_policy)}`,
    `目标 ${actorLabel} / ${platformProviderLabel(providerId)}`,
    `预计 token ${estimatedTokens}`,
    readonlyFirst ? "建议先只读探针" : "可直接进入软件验证",
    shouldSimulateFirst ? "仿真优先" : "无需强制仿真",
  ];
  return {
    risk_level: riskLevel,
    requires_human_review: requiresHumanReview,
    should_simulate_first: shouldSimulateFirst,
    readonly_first: readonlyFirst,
    execution_mode_label: modeLabel,
    actor_label: actorLabel,
    provider_id: providerId,
    provider_label: platformProviderLabel(providerId),
    project_profile: inferredProfile,
    project_profile_label: collabProjectProfileLabel(inferredProfile),
    approval_policy: protocol.approval_policy,
    approval_label: collabProtocolApprovalLabel(protocol.approval_policy),
    work_kind: protocol.work_kind,
    work_kind_label: collabProtocolWorkKindLabel(protocol.work_kind),
    estimated_tokens: estimatedTokens,
    token_policy: tokenPolicy,
    token_summary: collabTokenPolicySummary(protocol),
    runaway_summary: collabRunawayPolicySummary(protocol),
    efficiency_summary: collabEfficiencyPolicySummary(protocol),
    debug_summary: collabDebugPolicySummary(protocol),
    max_auto_rounds: protocol.runaway_policy.max_auto_rounds,
    parallelism_limit: protocol.efficiency_policy.parallelism_limit,
    warnings,
    notes,
  };
}

function resolveAiRequiredLedgerOptions(
  project: Record<string, unknown> | null | undefined,
  payload: CollaborationMessagePayload,
  currentUserId: string | null,
  governancePreview?: ReturnType<typeof buildCollaborationGovernancePreview> | null,
): Parameters<typeof withAiRequiredRequirementLedger>[1] {
  if (!project) {
    return {
      requesterLabel: currentUserId || "human",
      assigneeLabel: payload.recipient_id,
      automationMode: "off",
      executionMode: governancePreview?.execution_mode_label,
      estimatedTokens: governancePreview?.estimated_tokens ?? estimateMessageTokens(payload),
    };
  }
  const { actor, actorLabel, protocol } = resolveActorProtocolForPreview(project, payload);
  const metadata = actor?.metadata && typeof actor.metadata === "object" ? (actor.metadata as Record<string, unknown>) : {};
  const automationEnabled = readSeatAutomationEnabled(metadata, false);
  const heartbeatSeconds = readSeatAutomationHeartbeatSeconds(metadata);
  const gitContext = buildProjectGitCollaborationContext(project);
  return {
    requesterLabel: currentUserId || "human",
    assigneeLabel: actorLabel,
    automationMode: automationEnabled ? "heartbeat" : "off",
    heartbeatInterval: automationEnabled ? `${heartbeatSeconds}s` : "不开启",
    reviewPolicy: collabProtocolApprovalLabel(protocol.approval_policy),
    executionMode: governancePreview?.execution_mode_label ?? collabProtocolWorkKindLabel(protocol.work_kind),
    estimatedTokens: governancePreview?.estimated_tokens ?? estimateMessageTokens(payload),
    gitRepositoryLine: gitContext.repositoryLine,
    gitIdentityLine: gitContext.identityLine,
    gitCredentialLine: gitContext.credentialLine,
    gitLocalPathPolicyLine: gitContext.localPathPolicyLine,
    gitReviewBoundaryLine: gitContext.reviewBoundaryLine,
  };
}

function buildHumanReviewRequestPayload(
  payload: CollaborationMessagePayload,
  governancePreview: ReturnType<typeof buildCollaborationGovernancePreview>,
  senderId: string | null,
) {
  const title = text(payload.title, "未命名协作指令");
  const target = text(payload.recipient_id, "未选择目标");
  const targetType = text(payload.recipient_type, "未指定");
  const warnings = asArray<string>(governancePreview.warnings)
    .map((item) => text(item))
    .filter(Boolean);
  const reviewMeta = {
    schema: "ai_collab_human_review_v1",
    original_title: title,
    original_target: target,
    target_type: targetType,
    target_ai: text(governancePreview.actor_label, target),
    provider: text(governancePreview.provider_label, ""),
    risk_level: text(governancePreview.risk_level, ""),
    estimated_tokens: Number(governancePreview.estimated_tokens ?? 0),
    execution_boundary: text(governancePreview.execution_mode_label, ""),
    readonly_first: Boolean(governancePreview.readonly_first),
    simulation_first: Boolean(governancePreview.should_simulate_first),
    original_instruction: text(payload.body, ""),
  };
  const reviewBody = [
    "这条 AI 协作指令没有直接派给目标线程，因为治理预演判断它需要人工审核。",
    "AI_REVIEW_META_JSON:",
    JSON.stringify(reviewMeta),
    "AI_REVIEW_META_JSON_END",
    "",
    `原始标题: ${title}`,
    `原始目标: ${target}`,
    `目标类型: ${targetType}`,
    `目标 AI: ${text(governancePreview.actor_label, target)}`,
    `Provider: ${text(governancePreview.provider_label, "")}`,
    `项目视角: ${text(governancePreview.project_profile_label, "")}`,
    `风险等级: ${text(governancePreview.risk_level, "")}`,
    `预计 token: ${String(governancePreview.estimated_tokens ?? 0)}`,
    `执行边界: ${text(governancePreview.execution_mode_label, "")}`,
    `只读探针: ${governancePreview.readonly_first ? "是" : "否"}`,
    `仿真优先: ${governancePreview.should_simulate_first ? "是" : "否"}`,
    "",
    "治理提醒:",
    ...(warnings.length ? warnings.map((item, index) => `${index + 1}. ${item}`) : ["1. 需要人工确认后再继续。"]),
    "",
    "原始指令:",
    payload.body,
    "",
    "人工审核动作建议:",
    "1. 如果只是只读/调研，确认范围后重新发送一条更小的只读指令。",
    "2. 如果涉及真实硬件、烧录、串口、删除、发布或跨项目数据，先补仿真/回滚/权限边界。",
    "3. 审核通过前，不要让目标 NPC 自动续推。",
  ].join("\n");

  return {
    project_id: payload.project_id,
    task_id: payload.task_id,
    approval_id: payload.approval_id,
    handoff_id: payload.handoff_id,
    requirement_id: payload.requirement_id,
    agent_id: payload.agent_id,
    message_type: "human_review_request",
    title: `人工审核：${title}`,
    body: reviewBody,
    sender_type: "human",
    sender_id: senderId,
    recipient_type: "project",
    recipient_id: payload.project_id,
    status: "pending_human_review",
  };
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function readReviewLine(body: unknown, label: string) {
  const source = String(body ?? "");
  const match = source.match(new RegExp(`^${escapeRegExp(label)}:\\s*(.*)$`, "m"));
  return text(match?.[1], "");
}

function readReviewMeta(body: unknown): Record<string, unknown> {
  const source = String(body ?? "");
  const match = source.match(/AI_REVIEW_META_JSON:\s*([\s\S]*?)\s*AI_REVIEW_META_JSON_END/);
  if (!match?.[1]) return {};
  try {
    const parsed = JSON.parse(match[1]);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function readReviewInstruction(body: unknown) {
  const source = String(body ?? "");
  const marker = "原始指令:";
  const start = source.indexOf(marker);
  if (start < 0) return "";
  const tail = source.slice(start + marker.length).trim();
  const endWithBlank = tail.indexOf("\n\n人工审核动作建议:");
  const endWithoutBlank = tail.indexOf("\n人工审核动作建议:");
  const end = endWithBlank >= 0 ? endWithBlank : endWithoutBlank;
  return text(end >= 0 ? tail.slice(0, end) : tail, "");
}

function humanReviewDecisionConfig(decision: string) {
  const normalized = text(decision, "readonly_probe");
  if (normalized === "simulation") {
    return {
      status: "approved_simulation",
      titlePrefix: "仿真验证：",
      notice: "已通过人工审核，并改为先仿真验证。",
      bodyPrefix: [
        "人工审核结论：先仿真验证，不允许直接触碰真实硬件或生产数据。",
        "执行边界：只能做模拟、沙盘、日志回放、方案推演；如果发现必须动真实设备，先回最小回执并再次请求人审。",
      ],
    };
  }
  if (normalized === "formal_execute") {
    return {
      status: "approved_formal",
      titlePrefix: "人工通过：",
      notice: "已通过人工审核，并派发正式执行指令。",
      bodyPrefix: [
        "人工审核结论：允许正式执行本次指令。",
        "执行边界：先回最小回执；删除、烧录、发布、真实设备写入、跨账号/跨项目读取前仍要再次停下来确认。",
      ],
    };
  }
  return {
    status: "approved_readonly",
    titlePrefix: "只读探针：",
    notice: "已通过人工审核，并改为只读探针。",
    bodyPrefix: [
      "人工审核结论：只允许只读探针。",
      "执行边界：只能阅读、梳理、列计划、返回最小回执；禁止修改文件、运行危险命令、访问真实硬件或发布结果。",
    ],
  };
}

function buildApprovedHumanReviewCommand(
  reviewMessage: Record<string, unknown>,
  decision: string,
  reviewerNote: string,
  senderId: string | null,
  project?: Record<string, unknown> | null,
) {
  const config = humanReviewDecisionConfig(decision);
  const reviewMeta = readReviewMeta(reviewMessage.body);
  const originalTitle =
    text(reviewMeta.original_title, "") || readReviewLine(reviewMessage.body, "原始标题") || text(reviewMessage.title, "未命名协作指令");
  const originalTarget = text(reviewMeta.original_target, "") || readReviewLine(reviewMessage.body, "原始目标");
  const originalTargetType = text(reviewMeta.target_type, "") || readReviewLine(reviewMessage.body, "目标类型") || "workstation";
  const originalInstruction =
    text(reviewMeta.original_instruction, "") || readReviewInstruction(reviewMessage.body) || text(reviewMessage.body, "");
  const body = [
    ...config.bodyPrefix,
    reviewerNote ? `审核备注：${reviewerNote}` : "",
    "",
    "原始指令:",
    originalInstruction,
    "",
    "回执要求:",
    "1. 先回一条最小回执，说明你理解的边界和下一步。",
    "2. 如果边界不清楚，直接停下并回到协作消息池请求人确认。",
    "3. 完成后必须给最终回复，说明产出、验证方式、剩余风险和下一步需求。",
  ].filter(Boolean).join("\n");

  const commandPayload = {
    project_id: text(reviewMessage.project_id, "") || null,
    task_id: text(reviewMessage.task_id, "") || null,
    approval_id: text(reviewMessage.approval_id, "") || null,
    handoff_id: text(reviewMessage.handoff_id, "") || null,
    requirement_id: text(reviewMessage.requirement_id, "") || null,
    agent_id: text(reviewMessage.agent_id, "") || null,
    message_type: "agent_command",
    title: `${config.titlePrefix}${originalTitle.replace(/^人工审核：/, "")}`,
    body,
    sender_type: "human",
    sender_id: senderId,
    recipient_type: originalTargetType,
    recipient_id: originalTarget,
    status: "queued",
  };
  const gitContext = buildProjectGitCollaborationContext(project);
  return withAiRequiredRequirementLedger(commandPayload, {
    requesterLabel: senderId || "human",
    assigneeLabel: text(reviewMeta.target_ai, "") || originalTarget,
    automationMode: "off",
    heartbeatInterval: "不开启",
    reviewPolicy: text(reviewMeta.risk_level, "") ? `人工已审核；原风险等级 ${text(reviewMeta.risk_level, "")}` : "人工已审核",
    executionMode: config.bodyPrefix.join(" / "),
    estimatedTokens: Number(reviewMeta.estimated_tokens ?? 0) || null,
    gitRepositoryLine: gitContext.repositoryLine,
    gitIdentityLine: gitContext.identityLine,
    gitCredentialLine: gitContext.credentialLine,
    gitLocalPathPolicyLine: gitContext.localPathPolicyLine,
    gitReviewBoundaryLine: gitContext.reviewBoundaryLine,
  });
}

function buildDevelopmentWorkshopStationFromFormData(formData: FormData, fallbackId?: string | null) {
  return normalizeDevelopmentWorkshopStation(
    {
      id: text(formData.get("station_id"), "") || fallbackId || undefined,
      label: text(formData.get("label"), ""),
      icon: text(formData.get("icon"), "工"),
      station: text(formData.get("station"), ""),
      mapScene: text(formData.get("map_scene"), ""),
      mapLocation: text(formData.get("map_location"), ""),
      detail: text(formData.get("detail"), ""),
      modes: parseStringList(formData.get("modes")) ?? [],
      backendAnchor: text(formData.get("backend_anchor"), ""),
      runnerCapabilities: parseStringList(formData.get("runner_capabilities")) ?? [],
      aiResponsibilities: parseStringList(formData.get("ai_responsibilities")) ?? [],
      npcRoleTemplates: parseStringList(formData.get("npc_role_templates")) ?? [],
      assignmentKeywords: parseStringList(formData.get("assignment_keywords")) ?? [],
      nextActions: parseStringList(formData.get("next_actions")) ?? [],
      approvalPolicy: text(formData.get("approval_policy"), ""),
      riskLevel: text(formData.get("risk_level"), "中"),
      assignedNpcIds: parseStringListAll(formData, "assigned_npc_ids") ?? [],
      knowledgeBase: {
        summary: text(formData.get("knowledge_summary"), ""),
        handoffPath: text(formData.get("knowledge_handoff_path"), ""),
        tags: parseStringList(formData.get("knowledge_tags")) ?? [],
      },
    },
    null,
  );
}

function mergeSeatMetadata(seed: unknown, patch: Record<string, unknown>) {
  const base = seed && typeof seed === "object" ? (seed as Record<string, unknown>) : {};
  return {
    ...base,
    ...patch,
  };
}

function cloneRecord(value: unknown) {
  return value && typeof value === "object" ? ({ ...(value as Record<string, unknown>) } satisfies Record<string, unknown>) : {};
}

function parseOptionalPositiveInteger(value: FormDataEntryValue | null | undefined) {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed) : null;
}

function mergeExecutionMetadata(
  seed: unknown,
  options: {
    executorCommand?: string | null;
    executorCwd?: string | null;
    executorTimeoutSeconds?: number | null;
    clearExecutorTemplate?: boolean;
  },
) {
  const base = cloneRecord(seed);
  const adapter = cloneRecord(base.adapter);
  if (options.clearExecutorTemplate) {
    delete adapter.executor_command;
    delete adapter.executor_cwd;
    delete adapter.executor_timeout_seconds;
    delete base.executor_command;
    delete base.executor_cwd;
    delete base.executor_timeout_seconds;
  } else {
    if (options.executorCommand) adapter.executor_command = options.executorCommand;
    else delete adapter.executor_command;
    if (options.executorCwd) adapter.executor_cwd = options.executorCwd;
    else delete adapter.executor_cwd;
    if (options.executorTimeoutSeconds !== undefined) {
      if (options.executorTimeoutSeconds === null) delete base.executor_timeout_seconds;
      else base.executor_timeout_seconds = options.executorTimeoutSeconds;
      delete adapter.executor_timeout_seconds;
    }
  }
  if (Object.keys(adapter).length) base.adapter = adapter;
  else delete base.adapter;
  return Object.keys(base).length ? base : null;
}

let cachedWorkspaceRoot: string | null = null;

function workspaceRoot() {
  if (cachedWorkspaceRoot) return cachedWorkspaceRoot;
  const envRoot = String(process.env.AI_COLLAB_REPO_ROOT ?? process.env.WORKSPACE_ROOT ?? "").trim();
  if (envRoot) {
    cachedWorkspaceRoot = path.resolve(envRoot);
    return cachedWorkspaceRoot;
  }
  try {
    const gitRoot = execFileSync("git", ["rev-parse", "--show-toplevel"], {
      cwd: process.cwd(),
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    if (gitRoot) {
      cachedWorkspaceRoot = path.resolve(gitRoot);
      return cachedWorkspaceRoot;
    }
  } catch {
    // Fall through to the filesystem walk below.
  }
  let cursor = process.cwd();
  for (let index = 0; index < 8; index += 1) {
    if (
      existsSync(path.join(cursor, "apps"))
      && existsSync(path.join(cursor, "scripts"))
      && existsSync(path.join(cursor, "docs", "platform-agent-operating-architecture.md"))
    ) {
      cachedWorkspaceRoot = cursor;
      return cachedWorkspaceRoot;
    }
    const parent = path.dirname(cursor);
    if (parent === cursor) break;
    cursor = parent;
  }
  cachedWorkspaceRoot = path.resolve(process.cwd(), "..", "..");
  return cachedWorkspaceRoot;
}

function uniqueStrings(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.map((item) => text(item, "")).filter(Boolean)));
}

type ExternalSkillPackPayload = {
  source_repo?: string;
  skill_count?: number;
  categories?: Record<string, number>;
  curated_seed_skill_ids?: string[];
  skill_library?: Record<string, unknown>[];
};

type GithubSkillImportTarget = {
  owner: string;
  repo: string;
  ref: string;
  path: string;
  mode: "file" | "tree";
  sourceUrl: string;
};

type GithubSkillSourceFile = {
  owner: string;
  repo: string;
  ref: string;
  path: string;
  sourceUrl: string;
  rawUrl: string;
  content: string;
  importMode?: "standard" | "agent_markdown";
};

const GITHUB_SKILL_IMPORT_MAX_FILES = 40;
const GITHUB_SKILL_IMPORT_MAX_SKILLS = 120;
const GITHUB_SKILL_IMPORT_MAX_TEXT_BYTES = 600_000;
const GITHUB_SKILL_STORED_INSTRUCTION_LIMIT = 18_000;

function skillCategoryLabel(skill: Record<string, unknown>) {
  const metadata = cloneRecord(skill.metadata);
  if (text(metadata.category, "")) return text(metadata.category, "");
  if (text(skill.source, "") === "agency-agents") return "external";
  if (text(skill.source, "") === "github") return "github";
  return "custom";
}

function skillSortRank(skill: Record<string, unknown>) {
  const source = text(skill.source, "custom");
  if (source === "custom") return 0;
  if (source === "agency-agents") return 1;
  return 2;
}

function sortProjectSkillLibrary(skills: Record<string, unknown>[]) {
  return skills.slice().sort((left, right) => {
    const sourceRank = skillSortRank(left) - skillSortRank(right);
    if (sourceRank !== 0) return sourceRank;
    const categoryRank = skillCategoryLabel(left).localeCompare(skillCategoryLabel(right), "zh-CN");
    if (categoryRank !== 0) return categoryRank;
    return text(left.label ?? left.id, "").localeCompare(text(right.label ?? right.id, ""), "zh-CN");
  });
}

const RECOMMENDED_PROJECT_SKILLS: Record<string, { label: string; note: string; recommendedFor: string[] }> = {
  "platform-boss-planning": {
    label: "Boss 分工规划",
    note: "把用户的一句话需求拆成可执行方案、工位分工、NPC 职责、GitHub 知识库路径和验收口径；Boss 只做规划、派单、收口，不直接替执行 NPC 写实现。",
    recommendedFor: ["Boss NPC", "产品与分工工位", "项目负责人"],
  },
  "platform-backend-api": {
    label: "后端接口与数据",
    note: "负责阅读项目仓库文档，梳理接口、数据模型、标注流程、导出格式和迁移风险；输出要能被前端和 QA NPC 复用。",
    recommendedFor: ["后端数据 NPC", "标注与导出工位"],
  },
  "platform-frontend-experience": {
    label: "前端体验验收",
    note: "负责核心页面、表单、工作台和跨端体验；提交前必须从真实用户路径说明点击步骤和页面状态。",
    recommendedFor: ["前端体验 NPC", "用户体验工位"],
  },
  "platform-dataset-export": {
    label: "数据集导入导出",
    note: "关注项目数据、标注结果、采样片段和训练清单的导入导出闭环；每次改动要说明字段来源、兼容旧数据方式和可回滚点。",
    recommendedFor: ["后端数据 NPC", "数据治理 NPC"],
  },
  "platform-browser-acceptance": {
    label: "浏览器用户验收",
    note: "用用户视角验证页面能不能用、密度是否舒服、核心按钮是否找得到；每次给出截图或明确的路由、操作、结果。",
    recommendedFor: ["QA 验收 NPC", "验收风险工位"],
  },
  "platform-cross-station-routing": {
    label: "跨工位协作路由",
    note: "同一工位 NPC 互相认识并按职责找人；不同工位只能通过目标工位长 NPC 沟通，回执必须回到发起 NPC 和 Boss 收口。",
    recommendedFor: ["Boss NPC", "工位长 NPC", "协作平台 NPC"],
  },
};

async function readAgencyAgentsSkillPack(): Promise<ExternalSkillPackPayload> {
  const candidates = [
    path.join(process.cwd(), "lib", "skill-packs", "agency-agents-skill-pack.json"),
    path.join(workspaceRoot(), "apps", "web", "lib", "skill-packs", "agency-agents-skill-pack.json"),
  ];
  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      const raw = await fs.readFile(candidate, "utf8");
      const parsed = JSON.parse(raw) as ExternalSkillPackPayload;
      if (Array.isArray(parsed.skill_library)) return parsed;
    } catch {}
  }
  throw new Error("还没找到 Agency Agents skill 包，请先生成或同步 skill-packs/agency-agents-skill-pack.json");
}

function slugifyProjectSkillId(value: unknown, fallback = "skill") {
  const normalized = text(value, fallback)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9-_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return normalized || fallback;
}

function trimToLength(value: unknown, maxLength: number) {
  const raw = text(value, "");
  if (raw.length <= maxLength) return raw;
  return `${raw.slice(0, maxLength).trimEnd()}\n\n[内容已截断，完整内容请查看 GitHub 源文件]`;
}

function parseGithubUrl(rawUrl: string, pathOverride = "", branchOverride = ""): GithubSkillImportTarget {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new Error("请填写有效的 GitHub 地址，例如 https://github.com/owner/repo/tree/main/skills");
  }
  const host = parsed.hostname.toLowerCase();
  const parts = parsed.pathname.split("/").map((item) => decodeURIComponent(item)).filter(Boolean);
  const cleanPathOverride = pathOverride.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  const cleanBranchOverride = branchOverride.replace(/^\/+|\/+$/g, "");

  if (host === "raw.githubusercontent.com") {
    const [owner, repo, rawRef, ...pathParts] = parts;
    if (!owner || !repo || !rawRef) {
      throw new Error("Raw GitHub 地址不完整，至少需要 owner/repo/branch/path");
    }
    const filePath = cleanPathOverride || pathParts.join("/");
    if (!filePath) throw new Error("Raw GitHub 地址缺少文件路径");
    return {
      owner,
      repo,
      ref: cleanBranchOverride || rawRef || "main",
      path: filePath,
      mode: "file",
      sourceUrl: rawUrl,
    };
  }

  if (host !== "github.com" && host !== "www.github.com") {
    throw new Error("当前只允许从 github.com 或 raw.githubusercontent.com 导入 Skill，避免误抓内网或不可信地址。");
  }

  const [owner, repo, modeSegment, rawRef, ...pathParts] = parts;
  if (!owner || !repo) {
    throw new Error("GitHub 地址缺少 owner/repo，例如 https://github.com/owner/repo");
  }
  const repoName = repo.replace(/\.git$/i, "");
  const isBlob = modeSegment === "blob";
  const isTree = modeSegment === "tree";
  const inferredPath = cleanPathOverride || (isBlob || isTree ? pathParts.join("/") : "");
  const inferredRef = cleanBranchOverride || (isBlob || isTree ? rawRef : "") || "";
  const mode: "file" | "tree" = isBlob || /\.[a-z0-9]+$/i.test(inferredPath) ? "file" : "tree";
  return {
    owner,
    repo: repoName,
    ref: inferredRef,
    path: inferredPath,
    mode,
    sourceUrl: rawUrl,
  };
}

function githubApiUrl(target: GithubSkillImportTarget, apiPath: string) {
  return `https://api.github.com/repos/${encodeURIComponent(target.owner)}/${encodeURIComponent(target.repo)}${apiPath}`;
}

async function fetchGithubJson(url: string) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20_000);
  try {
    const response = await fetch(url, {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": "ai-collab-platform-skill-import",
      },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`GitHub API 返回 HTTP ${response.status}`);
    }
    return (await response.json()) as Record<string, unknown>;
  } finally {
    clearTimeout(timer);
  }
}

async function fetchGithubText(url: string) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20_000);
  try {
    const response = await fetch(url, {
      headers: {
        Accept: "text/plain, application/json;q=0.9, text/markdown;q=0.9, */*;q=0.5",
        "User-Agent": "ai-collab-platform-skill-import",
      },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`GitHub 文件读取失败：HTTP ${response.status}`);
    }
    const contentLength = Number(response.headers.get("content-length") ?? 0);
    if (contentLength > GITHUB_SKILL_IMPORT_MAX_TEXT_BYTES) {
      throw new Error("这个 GitHub 文件太大，请指定具体 Skill 文件或目录。");
    }
    const content = await response.text();
    if (content.length > GITHUB_SKILL_IMPORT_MAX_TEXT_BYTES) {
      throw new Error("这个 GitHub 文件太大，请指定更小的 Skill 文件。");
    }
    return content;
  } finally {
    clearTimeout(timer);
  }
}

async function resolveGithubImportRef(target: GithubSkillImportTarget) {
  if (target.ref) return target.ref;
  try {
    const repoPayload = await fetchGithubJson(githubApiUrl(target, ""));
    return text(repoPayload.default_branch, "main");
  } catch {
    return "main";
  }
}

function githubRawUrl(owner: string, repo: string, ref: string, filePath: string) {
  return `https://raw.githubusercontent.com/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/${encodeURIComponent(ref)}/${filePath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/")}`;
}

function looksLikeGithubSkillFile(filePath: string, exactFileMode = false) {
  const normalized = filePath.replace(/\\/g, "/");
  const baseName = path.posix.basename(normalized).toLowerCase();
  if (exactFileMode) return /\.(md|mdx|json)$/i.test(baseName);
  if (/^(skill|skills|skill-pack|skill_pack)\.(md|mdx|json)$/i.test(baseName)) return true;
  if (/^skill[-_.].+\.(md|mdx|json)$/i.test(baseName)) return true;
  if (/(^|\/)(skills|skill|\.codex\/skills)\/.+\.(md|mdx|json)$/i.test(normalized)) return true;
  if (/\.skill\.(md|mdx|json)$/i.test(baseName)) return true;
  return false;
}

function looksLikeGithubAgentMarkdownFile(filePath: string) {
  const normalized = filePath.replace(/\\/g, "/").replace(/^\/+/, "");
  const lower = normalized.toLowerCase();
  const baseName = path.posix.basename(lower);
  if (!/\.(md|mdx)$/i.test(baseName)) return false;
  if (/^(readme|contributing|security|license|code_of_conduct|pull_request_template)\.mdx?$/i.test(baseName)) return false;
  if (lower.startsWith(".github/") || lower.startsWith("scripts/") || lower.startsWith("examples/")) return false;
  if (lower.split("/").some((part) => part.startsWith("."))) return false;
  return normalized.split("/").length >= 2;
}

async function readGithubSkillSourceFiles(target: GithubSkillImportTarget): Promise<GithubSkillSourceFile[]> {
  const resolvedRef = await resolveGithubImportRef(target);
  const activeTarget = { ...target, ref: resolvedRef };
  if (activeTarget.mode === "file") {
    const rawUrl =
      activeTarget.sourceUrl.includes("raw.githubusercontent.com")
        ? activeTarget.sourceUrl
        : githubRawUrl(activeTarget.owner, activeTarget.repo, activeTarget.ref, activeTarget.path);
    return [
      {
        owner: activeTarget.owner,
        repo: activeTarget.repo,
        ref: activeTarget.ref,
        path: activeTarget.path,
        sourceUrl: activeTarget.sourceUrl,
        rawUrl,
        content: await fetchGithubText(rawUrl),
        importMode: "standard",
      },
    ];
  }

  const treeUrl = githubApiUrl(activeTarget, `/git/trees/${encodeURIComponent(activeTarget.ref)}?recursive=1`);
  const treePayload = await fetchGithubJson(treeUrl);
  const tree = Array.isArray(treePayload.tree) ? (treePayload.tree as Record<string, unknown>[]) : [];
  const basePath = activeTarget.path.replace(/^\/+|\/+$/g, "");
  const prefix = basePath ? `${basePath}/` : "";
  let importMode: GithubSkillSourceFile["importMode"] = "standard";
  let candidatePaths = tree
    .filter((entry) => text(entry.type, "") === "blob")
    .map((entry) => text(entry.path, ""))
    .filter(Boolean)
    .filter((filePath) => (prefix ? filePath === basePath || filePath.startsWith(prefix) : true))
    .filter((filePath) => looksLikeGithubSkillFile(filePath))
    .slice(0, GITHUB_SKILL_IMPORT_MAX_FILES);

  if (!candidatePaths.length) {
    candidatePaths = tree
      .filter((entry) => text(entry.type, "") === "blob")
      .map((entry) => text(entry.path, ""))
      .filter(Boolean)
      .filter((filePath) => (prefix ? filePath === basePath || filePath.startsWith(prefix) : true))
      .filter((filePath) => looksLikeGithubAgentMarkdownFile(filePath))
      .slice(0, GITHUB_SKILL_IMPORT_MAX_FILES);
    importMode = "agent_markdown";
  }

  if (!candidatePaths.length) {
    throw new Error(
      "这个 GitHub 目录里没有找到明显的 Skill 文件，也没有可转换的 Markdown agent profile。请指定 SKILL.md、skill.json、skills.json、skills/ 目录，或一个按目录分类存放角色 Markdown 的仓库。",
    );
  }

  const files: GithubSkillSourceFile[] = [];
  for (const filePath of candidatePaths) {
    const rawUrl = githubRawUrl(activeTarget.owner, activeTarget.repo, activeTarget.ref, filePath);
    files.push({
      owner: activeTarget.owner,
      repo: activeTarget.repo,
      ref: activeTarget.ref,
      path: filePath,
      sourceUrl: activeTarget.sourceUrl,
      rawUrl,
      content: await fetchGithubText(rawUrl),
      importMode,
    });
  }
  return files;
}

function stripMarkdownFrontmatter(markdown: string) {
  if (!markdown.startsWith("---")) return markdown;
  const closeIndex = markdown.indexOf("\n---", 3);
  if (closeIndex < 0) return markdown;
  const afterClose = markdown.indexOf("\n", closeIndex + 4);
  return markdown.slice(afterClose >= 0 ? afterClose + 1 : closeIndex + 4);
}

function parseSimpleFrontmatter(markdown: string) {
  if (!markdown.startsWith("---")) return {};
  const closeIndex = markdown.indexOf("\n---", 3);
  if (closeIndex < 0) return {};
  const block = markdown.slice(3, closeIndex).trim();
  const result: Record<string, unknown> = {};
  for (const line of block.split(/\r?\n/)) {
    const match = /^([A-Za-z0-9_.-]+):\s*(.*)$/.exec(line.trim());
    if (!match) continue;
    const key = match[1];
    let value: unknown = match[2].trim();
    if (typeof value === "string" && value.startsWith("[") && value.endsWith("]")) {
      value = value
        .slice(1, -1)
        .split(",")
        .map((item) => item.trim().replace(/^["']|["']$/g, ""))
        .filter(Boolean);
    } else if (typeof value === "string") {
      value = value.replace(/^["']|["']$/g, "");
    }
    result[key] = value;
  }
  return result;
}

function extractMarkdownHeading(markdown: string) {
  const body = stripMarkdownFrontmatter(markdown);
  const heading = /^#\s+(.+)$/m.exec(body);
  return text(heading?.[1], "");
}

function extractMarkdownSummary(markdown: string) {
  const body = stripMarkdownFrontmatter(markdown)
    .replace(/```[\s\S]*?```/g, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/!\[[^\]]*]\([^)]+\)/g, " ")
    .replace(/\[[^\]]+]\([^)]+\)/g, (match) => match.replace(/^\[|\]\([^)]+\)$/g, ""))
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && !line.startsWith("---") && !line.startsWith("|"));
  return trimToLength(body.slice(0, 3).join(" ").replace(/\s+/g, " "), 360);
}

function buildGithubProjectSkillId(sourceFile: GithubSkillSourceFile, rawId: unknown, index = 0) {
  const repoSlug = slugifyProjectSkillId(`${sourceFile.owner}-${sourceFile.repo}`, "github");
  const rawSlug = slugifyProjectSkillId(rawId, path.posix.basename(sourceFile.path).replace(/\.[^.]+$/, "") || `skill-${index + 1}`);
  const hash = createHash("sha1")
    .update(`${sourceFile.owner}/${sourceFile.repo}/${sourceFile.path}#${rawSlug}#${index}`)
    .digest("hex")
    .slice(0, 8);
  return `github-${repoSlug}-${rawSlug}`.slice(0, 86).replace(/-+$/g, "") + `-${hash}`;
}

function normalizeGithubRecommendedFor(...values: unknown[]) {
  return uniqueStrings(
    values
      .flatMap((value) => normalizeStringList(value))
      .map((item) => item.toLowerCase()),
  );
}

function normalizeGithubSkillRecord(
  skill: Record<string, unknown>,
  sourceFile: GithubSkillSourceFile,
  index: number,
  options: { category?: string; recommendedFor?: string[] },
): Record<string, unknown> {
  const metadata = cloneRecord(skill.metadata);
  const rawLabel = text(skill.label ?? metadata.label ?? metadata.name ?? skill.name ?? skill.title, "");
  const label = rawLabel || text(skill.id, "") || path.posix.basename(sourceFile.path).replace(/\.[^.]+$/, "");
  const description = text(skill.note ?? metadata.description ?? skill.description ?? metadata.summary, "");
  const category = text(options.category, "") || text(metadata.category ?? skill.category, "github");
  const recommendedFor = normalizeGithubRecommendedFor(
    options.recommendedFor,
    skill.recommended_for,
    metadata.recommended_for,
    metadata.tags,
    skill.tags,
    category,
    sourceFile.repo,
  );
  return {
    id: buildGithubProjectSkillId(sourceFile, skill.id ?? metadata.id ?? label, index),
    label,
    note: description ? `从 GitHub 导入：${description}` : "从 GitHub 导入的外部 Skill，请在详情中补充项目化说明。",
    source: "github",
    scope: "role",
    recommended_for: recommendedFor,
    metadata: {
      ...metadata,
      category,
      original_source: text(skill.source, ""),
      source_url: sourceFile.sourceUrl,
      raw_url: sourceFile.rawUrl,
      external_repo: `${sourceFile.owner}/${sourceFile.repo}`,
      external_ref: sourceFile.ref,
      external_path: sourceFile.path,
      imported_from: "github",
      imported_format: "json",
      description: description || text(metadata.description, ""),
    },
  };
}

function parseGithubMarkdownSkill(
  sourceFile: GithubSkillSourceFile,
  index: number,
  options: { category?: string; recommendedFor?: string[] },
): Record<string, unknown> {
  const frontmatter = parseSimpleFrontmatter(sourceFile.content);
  const heading = extractMarkdownHeading(sourceFile.content);
  const fallbackLabel = path.posix.basename(sourceFile.path).replace(/\.[^.]+$/, "");
  const label = text(frontmatter.label ?? frontmatter.display_name ?? frontmatter.name ?? heading, fallbackLabel);
  const description = text(frontmatter.description ?? frontmatter.summary, "") || extractMarkdownSummary(sourceFile.content);
  const category = text(options.category, "") || text(frontmatter.category, "github");
  const recommendedFor = normalizeGithubRecommendedFor(
    options.recommendedFor,
    frontmatter.recommended_for,
    frontmatter.tags,
    frontmatter.keywords,
    category,
    sourceFile.repo,
  );
  const rawId = frontmatter.id ?? frontmatter.name ?? label;
  return {
    id: buildGithubProjectSkillId(sourceFile, rawId, index),
    label,
    note:
      sourceFile.importMode === "agent_markdown"
        ? description
          ? `从 GitHub Agent Markdown 转换：${description}`
          : "从 GitHub 普通 Agent Markdown 转换的 Skill 草稿。"
        : description
          ? `从 GitHub 导入：${description}`
          : "从 GitHub 导入的 Markdown Skill。",
    source: "github",
    scope: "role",
    recommended_for: recommendedFor,
    metadata: {
      ...frontmatter,
      category,
      description: description || `GitHub Markdown Skill：${label}`,
      source_url: sourceFile.sourceUrl,
      raw_url: sourceFile.rawUrl,
      external_repo: `${sourceFile.owner}/${sourceFile.repo}`,
      external_ref: sourceFile.ref,
      external_path: sourceFile.path,
      imported_from: "github",
      imported_format: sourceFile.importMode === "agent_markdown" ? "agent_markdown" : "markdown",
      instructions: trimToLength(sourceFile.content, GITHUB_SKILL_STORED_INSTRUCTION_LIMIT),
    },
  };
}

function parseGithubSkillFile(
  sourceFile: GithubSkillSourceFile,
  options: { category?: string; recommendedFor?: string[] },
): Record<string, unknown>[] {
  const extension = path.posix.extname(sourceFile.path).toLowerCase();
  if (extension === ".json") {
    let parsed: unknown;
    try {
      parsed = JSON.parse(sourceFile.content);
    } catch {
      throw new Error(`GitHub JSON Skill 解析失败：${sourceFile.path}`);
    }
    const payload = parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
    const rawItems = Array.isArray(payload.skill_library)
      ? payload.skill_library
      : Array.isArray(payload.skills)
        ? payload.skills
        : Array.isArray(parsed)
          ? parsed
          : [payload];
    return rawItems
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .map((item, index) => normalizeGithubSkillRecord(item, sourceFile, index, options));
  }
  return [parseGithubMarkdownSkill(sourceFile, 0, options)];
}

function normalizeImportedProjectSkill(skill: Record<string, unknown>) {
  const metadata = cloneRecord(skill.metadata);
  return {
    id: text(skill.id, ""),
    label: text(skill.label ?? metadata.name, ""),
    note: text(skill.note ?? metadata.description, "外部导入 Skill"),
    source: text(skill.source, "agency-agents"),
    scope: text(skill.scope, "role") === "baseline" ? "baseline" : "role",
    recommended_for: normalizeStringList(skill.recommended_for),
    metadata,
  };
}

function readWorkspaceGitDefaults() {
  try {
    const repoRoot = execFileSync("git", ["rev-parse", "--show-toplevel"], {
      cwd: workspaceRoot(),
      encoding: "utf8",
    }).trim();
    const remoteUrl = execFileSync("git", ["remote", "get-url", "origin"], {
      cwd: workspaceRoot(),
      encoding: "utf8",
    }).trim();
    const currentBranch = execFileSync("git", ["branch", "--show-current"], {
      cwd: workspaceRoot(),
      encoding: "utf8",
    }).trim();
    return {
      githubUrl: remoteUrl || null,
      localGitUrl: repoRoot || null,
      branch: currentBranch || null,
    };
  } catch {
    return {
      githubUrl: null,
      localGitUrl: null,
      branch: null,
    };
  }
}

function enrichNpcCollabProtocolWithRepoContext(
  project: Record<string, unknown>,
  collabProtocol: Record<string, unknown>,
  options: {
    gitBoundary?: string[];
    handoffPath?: string | null;
  } = {},
) {
  const workspaceGit = readWorkspaceGitDefaults();
  const rawRepoContext =
    collabProtocol.repo_context && typeof collabProtocol.repo_context === "object"
      ? (collabProtocol.repo_context as Record<string, unknown>)
      : {};
  const repoContext = resolvePlatformRepoContext({
    repository_url:
      text(project.github_url ?? project.githubUrl, "") ||
      text(rawRepoContext.repository_url ?? rawRepoContext.repositoryUrl, "") ||
      text(workspaceGit.githubUrl, "") ||
      null,
    branch:
      text(project.develop_branch ?? project.developBranch, "") ||
      text(project.default_branch ?? project.defaultBranch, "") ||
      text(rawRepoContext.branch, "") ||
      text(workspaceGit.branch, "") ||
      null,
    relative_root: text(rawRepoContext.relative_root ?? rawRepoContext.relativeRoot, ".") || ".",
  });
  const referencePaths = buildPlatformRepoReferencePaths({
    referencePaths: collabProtocol.reference_paths,
    gitBoundary: options.gitBoundary,
    handoffPath: options.handoffPath,
    repositoryUrl: repoContext?.repository_url ?? null,
    branch: repoContext?.branch ?? null,
    workspaceRoots: uniqueStrings([
      workspaceRoot(),
      text(project.local_git_url ?? project.localGitUrl, "") || null,
      text(workspaceGit.localGitUrl, "") || null,
    ]),
  });
  return resolvePlatformCollabProtocol({
    ...collabProtocol,
    repo_context: repoContext,
    reference_paths: referencePaths,
  });
}

async function ensureNpcKnowledgeDoc(options: {
  handoffPath: string;
  seatName: string;
  responsibility: string;
  projectId: string;
  additionalSkillIds: string[];
  knowledgeDepositPath?: string | null;
  skillDepositPath?: string | null;
  needDepositPath?: string | null;
  taskDepositPath?: string | null;
  providerLabel?: string | null;
  sourceWorkstationId?: string | null;
  computerNodeId?: string | null;
  model?: string | null;
  collabProtocol?: Record<string, unknown> | null;
}) {
  const relativePath = options.handoffPath.replace(/\\/g, "/").replace(/^\/+/, "");
  if (!relativePath.startsWith("docs/ai-handoffs/")) return;
  const root = workspaceRoot();
  const filePath = path.resolve(root, relativePath);
  const normalizedRoot = root.replace(/\\/g, "/").toLowerCase();
  const normalizedFile = filePath.replace(/\\/g, "/").toLowerCase();
  if (!normalizedFile.startsWith(normalizedRoot)) return;
  try {
    await fs.access(filePath);
    return;
  } catch {}

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const role = options.responsibility || "待分配职责";
  const skillLine = options.additionalSkillIds.length ? options.additionalSkillIds.join(", ") : "No add-on skills yet";
  const knowledgeDepositPath = repoRelativePath(options.knowledgeDepositPath) || `docs/npc-knowledge/${displaySlug(options.seatName, "npc")}/`;
  const skillDepositPath = repoRelativePath(options.skillDepositPath) || `skills/npc-authored/${displaySlug(options.seatName, "npc")}/`;
  const needDepositPath = repoRelativePath(options.needDepositPath) || `docs/npc-requests/${displaySlug(options.seatName, "npc")}/needs/`;
  const taskDepositPath = repoRelativePath(options.taskDepositPath) || `docs/npc-requests/${displaySlug(options.seatName, "npc")}/tasks/`;
  const collabProtocol = resolvePlatformCollabProtocol(options.collabProtocol, {
    roleText: role,
    threadText: options.seatName,
    repoContext: options.collabProtocol?.repo_context,
  });
  const approvalPolicy = text(collabProtocol.approval_policy, "auto_continue");
  const workKind = text(collabProtocol.work_kind, "implementation");
  const capabilityLine = normalizeStringList(collabProtocol.required_capabilities).join(", ") || "general-software";
  const referenceLine = normalizeStringList(collabProtocol.reference_paths).join(", ") || "none";
  const repoContext = resolvePlatformRepoContext(collabProtocol.repo_context);
  const repoLine = platformRepoContextSummary(repoContext);
  const contents = `# NPC Knowledge Base: ${options.seatName}

Project id: ${options.projectId}
NPC role: ${role}

## Identity contract

- This NPC keeps a persistent knowledge base even if the execution thread changes.
- Changing computer, model, or source thread only changes the current execution shell.
- New operators should continue from this file and append fresh handoff evidence instead of resetting context.

## Current execution shell

- Provider: ${options.providerLabel || "unbound"}
- Source thread: ${options.sourceWorkstationId || "unbound"}
- Computer node: ${options.computerNodeId || "unbound"}
- Model: ${options.model || "gpt-5.4"}

## Collaboration protocol

- Work kind: ${workKind}
- Approval policy: ${approvalPolicy}
- Project profile: ${collabProtocol.project_profile} / ${collabProjectProfileLabel(collabProtocol.project_profile)}
- Token policy: ${collabTokenPolicySummary(collabProtocol)}
- Runaway guard: ${collabRunawayPolicySummary(collabProtocol)}
- Efficiency policy: ${collabEfficiencyPolicySummary(collabProtocol)}
- Debug and simulation: ${collabDebugPolicySummary(collabProtocol)}
- Repo route: ${repoLine}
- Required capabilities: ${capabilityLine}
- References: ${referenceLine}

## Safety boundaries

- Stop and ask for human review when the task crosses an approval boundary.
- For robot, embedded, serial, GPIO, firmware, or real-device work, simulate or do a read-only probe first.
- Do not keep spending tokens after the auto-round budget is reached; write a final reply or request review.

## Add-on skills

- ${skillLine}

## Default deposit paths

- Reusable knowledge deposit: ${knowledgeDepositPath}
- NPC-authored skill deposit: ${skillDepositPath}
- Need deposit: ${needDepositPath}
- Task receipt deposit: ${taskDepositPath}
- Write reusable discoveries and operating notes under the knowledge deposit path before asking the platform to index them.
- Write reusable skills as \`SKILL.md\` folders under the skill deposit path before asking the platform to index them.
- Write new needs under the need deposit path with required capability, expected output, risk, and preferred target if known.
- Write task receipts under the task deposit path with changed files, validation, evidence, and next step.
- Use GitHub repo-relative paths only; do not record another computer's absolute local path as shared truth.

## Continuation notes

- Keep predecessor decisions, validated screenshots, and requirement closeout notes here.
- Re-run build, pytest, and fresh screenshots before claiming a stable change.
`;
  await fs.writeFile(filePath, contents, "utf8");
}

async function ensureDevelopmentWorkshopStationKnowledgeDoc(options: {
  stationId: string;
  label: string;
  detail: string;
  knowledgeBase: {
    summary: string;
    handoffPath: string;
    tags: string[];
  };
  runnerCapabilities: string[];
  aiResponsibilities: string[];
  nextActions: string[];
  approvalPolicy: string;
}) {
  const relativePath = options.knowledgeBase.handoffPath.replace(/\\/g, "/").replace(/^\/+/, "");
  if (!relativePath.startsWith("docs/ai-handoffs/")) return;
  const root = workspaceRoot();
  const filePath = path.resolve(root, relativePath);
  const normalizedRoot = root.replace(/\\/g, "/").toLowerCase();
  const normalizedFile = filePath.replace(/\\/g, "/").toLowerCase();
  if (!normalizedFile.startsWith(normalizedRoot)) return;
  try {
    await fs.access(filePath);
    return;
  } catch {}

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const contents = `# Station Knowledge Base: ${options.label}

Station id: ${options.stationId}

## Shared purpose

${options.knowledgeBase.summary}

## Scope

${options.detail}

## Runner capabilities

${options.runnerCapabilities.length ? options.runnerCapabilities.map((item) => `- ${item}`).join("\n") : "- Pending capabilities"}

## AI responsibilities

${options.aiResponsibilities.length ? options.aiResponsibilities.map((item) => `- ${item}`).join("\n") : "- Pending responsibilities"}

## Default next actions

${options.nextActions.length ? options.nextActions.map((item) => `- ${item}`).join("\n") : "- Pending actions"}

## Approval boundary

- ${options.approvalPolicy}

## Knowledge tags

${options.knowledgeBase.tags.length ? options.knowledgeBase.tags.map((item) => `- ${item}`).join("\n") : "- development-workshop-station"}

## Continuation notes

- This is the shared station knowledge base. It belongs to the workstation itself, not to any single NPC.
- NPC knowledge bases should reference this file and then append their personal execution continuity separately.
`;
  await fs.writeFile(filePath, contents, "utf8");
}

async function ensureCodexSeatConsumerScript(options: {
  seatName: string;
  sourceWorkstationId?: string | null;
}) {
  const sourceWorkstationId = String(options.sourceWorkstationId ?? "").trim();
  if (!isCodexSessionWorkstationId(sourceWorkstationId)) return null;

  const root = workspaceRoot();
  const scriptName = buildCodexSeatConsumerScriptName(options.seatName);
  const stateName = `.${scriptName.replace(/\.py$/i, "")}-state.json`;
  const scriptPath = path.join(root, "scripts", scriptName);
  const contents = `#!/usr/bin/env python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


DEFAULT_WORKSTATION_ID = "${sourceWorkstationId}"
DEFAULT_WORKSTATION_NAME = "${String(options.seatName || "Codex Seat").replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"


def main() -> int:
  script_path = Path(__file__).with_name("npc1-thread-consumer.py")
  state_path = Path(__file__).with_name("${stateName}")
  command = [
    sys.executable,
    str(script_path),
    "--workstation-id",
    DEFAULT_WORKSTATION_ID,
    "--workstation-name",
    DEFAULT_WORKSTATION_NAME,
    "--state-path",
    str(state_path),
    *sys.argv[1:],
  ]
  completed = subprocess.run(command, check=False)
  return completed.returncode


if __name__ == "__main__":
  raise SystemExit(main())
`;
  await fs.writeFile(scriptPath, contents, "utf8");
  return path.relative(root, scriptPath).replace(/\\/g, "/");
}

async function ensureCodexSeatAutonomyBridge(options: {
  projectId: string;
  seatName: string;
  responsibility?: string | null;
  sourceWorkstationId?: string | null;
  handoffPath: string;
  knowledgeDepositPath?: string | null;
  skillDepositPath?: string | null;
  needDepositPath?: string | null;
  taskDepositPath?: string | null;
  computerNodeId?: string | null;
  model?: string | null;
  additionalSkillIds: string[];
  collabProtocol?: Record<string, unknown> | null;
  heartbeatIntervalSeconds?: number | null;
}) {
  await ensureNpcKnowledgeDoc({
    handoffPath: options.handoffPath,
    knowledgeDepositPath: options.knowledgeDepositPath,
    skillDepositPath: options.skillDepositPath,
    needDepositPath: options.needDepositPath,
    taskDepositPath: options.taskDepositPath,
    seatName: options.seatName,
    responsibility: text(options.responsibility, ""),
    projectId: options.projectId,
    additionalSkillIds: options.additionalSkillIds,
    providerLabel: "Codex",
    sourceWorkstationId: options.sourceWorkstationId,
    computerNodeId: options.computerNodeId,
    model: options.model,
    collabProtocol: options.collabProtocol,
  });
  const consumerScript = await ensureCodexSeatConsumerScript({
    seatName: options.seatName,
    sourceWorkstationId: options.sourceWorkstationId,
  });
  const heartbeat = await ensureCodexSeatHeartbeatAutomation({
    seatName: options.seatName,
    sourceWorkstationId: options.sourceWorkstationId,
    responsibility: options.responsibility,
    heartbeatIntervalSeconds: options.heartbeatIntervalSeconds,
  });
  return { consumerScript, heartbeat };
}

function buildCodexThreadLaunchPrompt(options: {
  projectId: string;
  projectName: string;
  repositoryUrl?: string | null;
  localGitUrl?: string | null;
  branch?: string | null;
  seatName: string;
  responsibility?: string | null;
  sourceWorkstationId: string;
  handoffPath: string;
  knowledgeDepositPath?: string | null;
  skillDepositPath?: string | null;
  needDepositPath?: string | null;
  taskDepositPath?: string | null;
  workstationName?: string | null;
  workstationKnowledgePath?: string | null;
  npcKnowledgeSummary?: string | null;
  sameWorkstationDirectory?: string[];
  crossWorkstationLeads?: string[];
  skills: string[];
  readPaths: string[];
  writePaths: string[];
}) {
  const skills = options.skills.length ? options.skills.join(", ") : "general-codex-collaboration";
  const readPaths = options.readPaths.length ? options.readPaths.join(", ") : "README.md, docs/";
  const writePaths = options.writePaths.length ? options.writePaths.join(", ") : "only files assigned by Boss NPC";
  const workstationKnowledgePath = repoRelativePath(options.workstationKnowledgePath) || "docs/workstations/<logical-workstation>.md";
  const npcHandoffPath = repoRelativePath(options.handoffPath);
  const knowledgeDepositPath = repoRelativePath(options.knowledgeDepositPath) || `docs/npc-knowledge/${displaySlug(options.seatName, "npc")}/`;
  const skillDepositPath = repoRelativePath(options.skillDepositPath) || `skills/npc-authored/${displaySlug(options.seatName, "npc")}/`;
  const needDepositPath = repoRelativePath(options.needDepositPath) || `docs/npc-requests/${displaySlug(options.seatName, "npc")}/needs/`;
  const taskDepositPath = repoRelativePath(options.taskDepositPath) || `docs/npc-requests/${displaySlug(options.seatName, "npc")}/tasks/`;
  const sameWorkstationDirectory = options.sameWorkstationDirectory?.length
    ? options.sameWorkstationDirectory.join("；")
    : "暂无同工位伙伴；有缺口先回 Boss NPC 或工位长";
  const crossWorkstationLeads = options.crossWorkstationLeads?.length
    ? options.crossWorkstationLeads.join("；")
    : "暂无其他工位长；跨工位需求先回 Boss NPC";
  return [
    `你是 ${options.seatName}，这是平台为用户已创建 Codex 线程生成的上岗提示词。`,
    "",
    "身份:",
    `- Project: ${options.projectName} (${options.projectId})`,
    `- NPC: ${options.seatName}`,
    `- Logical workstation: ${text(options.workstationName, "未归属工位")}`,
    `- Bound thread id: ${options.sourceWorkstationId}`,
    `- Responsibility: ${text(options.responsibility, "按 Boss NPC 派单推进")}`,
    `- Required skills: ${skills}`,
    "",
    "仓库和路径:",
    `- GitHub: ${text(options.repositoryUrl, "未绑定")}`,
    `- Local workspace: ${text(options.localGitUrl, "仅作当前电脑参考；所有交接和知识库必须写 GitHub 仓库相对路径")}`,
    `- Branch: ${text(options.branch, "按项目默认分支")}`,
    `- Read paths: ${readPaths}`,
    `- Write paths: ${writePaths}`,
    "",
    "必须先读（全部是 GitHub 仓库相对路径，不要依赖任何电脑绝对路径）:",
    "- docs/ai-handoffs/project-operating-contract.md",
    `- 工位知识库: ${workstationKnowledgePath}`,
    `- NPC 知识库: ${npcHandoffPath}`,
    options.npcKnowledgeSummary ? `- NPC 长期记忆摘要: ${options.npcKnowledgeSummary}` : "- NPC 长期记忆摘要: 先阅读 NPC 知识库后补齐",
    "",
    "默认沉淀路径（平台会从这些 GitHub 相对路径索引到能力工坊）:",
    `- 可复用知识写到: ${knowledgeDepositPath}`,
    `- 自造 Skill 写到: ${skillDepositPath}`,
    `- 我提出的需求写到: ${needDepositPath}`,
    `- 我承接任务的回执写到: ${taskDepositPath}`,
    "- 知识条目优先写成 Markdown；Skill 优先写成独立目录里的 SKILL.md。",
    "- Need 文件必须写清 required capability、expected output、risk、建议承接 NPC；Task 回执必须写清 changed files、validated、evidence、next。",
    "- 写完后在最终回执里列出 repo-relative path，平台会把知识/Skill 归入能力工坊，把 Need/Task 归入 NPC 工作台供用户分配、归档或删除索引。",
    "- 不要把 D:\\、/home/、runner 缓存路径写成共享知识或 Skill 来源。",
    "",
    "协作规则:",
    "- 只使用 Codex，本项目禁止切到 Claude 线程。",
    "- 平台只展示精简消息；复杂推理、代码修改和验证过程留在本 Codex 线程。",
    `- 同工位通讯录: ${sameWorkstationDirectory}`,
    `- 跨工位入口: ${crossWorkstationLeads}`,
    "- 同工位 NPC 互相认识；有需求先按职责找同工位最匹配 NPC，不确定就问本工位工位长。",
    "- 跨工位禁止直连普通 NPC，只能找目标工位工位长转交；工位长负责分派给本工位具体 NPC。",
    "- 收到派单后先给最小 ack，完成后用 Understood / Changed / Validated / Blocked / Next 回执。",
    "- 并行开发前声明写入范围，避免覆盖其他 NPC 工作。",
  ].join("\n");
}

function readSourceThreadCatalog(formData: FormData) {
  const parsed = parseOptionalJson(String(formData.get("source_thread_catalog") ?? ""));
  return asArray<Record<string, unknown>>(parsed);
}

function findSourceThreadCandidate(candidates: Record<string, unknown>[], sourceWorkstationId: string) {
  const normalized = text(sourceWorkstationId, "").toLowerCase();
  if (!normalized) return null;
  return (
    candidates.find((item) =>
      workstationLookupKeys(item).some((candidate) => candidate.toLowerCase() === normalized),
    ) ?? null
  );
}

function resolveNpcSourceThreadContext(project: any, formData: FormData) {
  const sourceWorkstationId = String(formData.get("source_workstation_id") ?? "").trim() || null;
  const collaborationConfig =
    project?.collaboration_config && typeof project.collaboration_config === "object"
      ? (project.collaboration_config as Record<string, unknown>)
      : {};
  const projectThreads = asArray<Record<string, unknown>>(
    collaborationConfig.thread_workstations ?? collaborationConfig.threadWorkstations ?? collaborationConfig.workstations,
  );
  const catalogThreads = readSourceThreadCatalog(formData);
  const matched =
    (sourceWorkstationId ? findSourceThreadCandidate(catalogThreads, sourceWorkstationId) : null) ??
    (sourceWorkstationId ? findSourceThreadCandidate(projectThreads, sourceWorkstationId) : null);
  const metadata =
    matched?.metadata && typeof matched.metadata === "object" ? (matched.metadata as Record<string, unknown>) : {};
  const providerId =
    normalizePlatformProviderId(
      formData.get("ai_provider_id") ??
        matched?.ai_provider_id ??
        matched?.ai_provider ??
        matched?.provider ??
        metadata.provider_id ??
        metadata.provider ??
        metadata.provider_label,
    ) || derivePlatformProviderIdFromThreadId(sourceWorkstationId);
  const providerLabel =
    text(
      formData.get("ai_provider") ??
        matched?.ai_provider ??
        matched?.ai_provider_label ??
        matched?.provider_label ??
        metadata.provider_label,
      "",
    ) || (providerId ? platformProviderLabel(providerId) : "");
  const computerNodeId =
    text(
      matched?.computer_node_id ??
        matched?.computerNodeId ??
        metadata.computer_node_id ??
        metadata.computerNodeId,
      "",
    ) || null;
  const computerNodeLabel =
    text(
      matched?.computer_node ??
        matched?.computerNode ??
        matched?.computer_node_label ??
        matched?.computerNodeLabel ??
        metadata.computer_node ??
        metadata.computer_node_label,
      "",
    ) || null;
  const model = text(matched?.model ?? metadata.model, "") || null;
  return {
    sourceWorkstationId,
    providerId,
    providerLabel,
    computerNodeId,
    computerNodeLabel,
    model,
    threadName: text(matched?.name ?? matched?.workstation_name, "") || null,
  };
}

async function createSkillForgeHumanReviewRequest(options: {
  projectId: string;
  senderId: string | null;
  title: string;
  targetLabel: string;
  actionSummary: string;
  reason: string;
  metadata?: Record<string, unknown>;
}) {
  const body = [
    "能力工坊配置更新需要人工确认，平台没有直接改动 NPC 上岗包。",
    "",
    `配置对象: ${options.targetLabel}`,
    `请求动作: ${options.actionSummary}`,
    `需要确认: ${options.reason}`,
    "",
    "人工审核动作建议:",
    "1. 确认这个 NPC 是否应该获得该能力或知识库。",
    "2. 如果会影响正在执行的任务，先等任务结束或明确刷新下一轮上岗包。",
    "3. 通过后再由能力工坊重新执行绑定动作。",
  ].join("\n");
  await postJson("/api/collaboration/messages", {
    project_id: options.projectId,
    message_type: "human_review_request",
    title: `人工确认：${options.title}`,
    body,
    sender_type: "human",
    sender_id: options.senderId,
    recipient_type: "project",
    recipient_id: options.projectId,
    status: "pending_human_review",
    extra_data: {
      schema: "skill_forge_review_v1",
      ...options.metadata,
    },
  });
}

function isHumanApprovalError(error: unknown) {
  const err = error as (Error & { status?: number; code?: string }) | null;
  const code = text(err?.code, "");
  const message = text(err?.message, "");
  return code === "HUMAN_APPROVAL_REQUIRED" || err?.status === 403 || /人工确认|项目负责人|审批|审核/.test(message);
}

function resolveNpcCollabProtocol(formData: FormData, options: {
  providerId?: string | null;
  responsibility?: string | null;
  threadText?: string | null;
  existing?: Record<string, unknown> | null;
}) {
  const parsed = options.existing && typeof options.existing === "object" ? options.existing : {};
  const parsedTokenPolicy =
    parsed.token_policy && typeof parsed.token_policy === "object" ? (parsed.token_policy as Record<string, unknown>) : {};
  const parsedRunawayPolicy =
    parsed.runaway_policy && typeof parsed.runaway_policy === "object"
      ? (parsed.runaway_policy as Record<string, unknown>)
      : {};
  const parsedEfficiencyPolicy =
    parsed.efficiency_policy && typeof parsed.efficiency_policy === "object"
      ? (parsed.efficiency_policy as Record<string, unknown>)
      : {};
  const parsedDebugPolicy =
    parsed.debug_policy && typeof parsed.debug_policy === "object" ? (parsed.debug_policy as Record<string, unknown>) : {};
  const formText = (field: string) => text(formData.get(field), "");
  const formNumber = (field: string, fallback: unknown) => parseOptionalPositiveInteger(formData.get(field)) ?? fallback;
  const formBoolean = (field: string, fallback: unknown) =>
    formText(field) === "" ? fallback : !["0", "false", "off", "no"].includes(formText(field).toLowerCase());
  return resolvePlatformCollabProtocol(
    {
      ...(parsed ?? {}),
      provider_id: text(formData.get("ai_provider_id"), "") || options.providerId || parsed.provider_id,
      work_kind: text(formData.get("work_kind"), "") || parsed.work_kind,
      approval_policy: text(formData.get("approval_policy"), "") || parsed.approval_policy,
      project_profile: formText("project_profile") || parsed.project_profile,
      required_capabilities:
        parseStringList(formData.get("required_capabilities")) ??
        (Array.isArray(parsed.required_capabilities) ? parsed.required_capabilities : []),
      reference_paths:
        parseStringList(formData.get("reference_paths")) ??
        (Array.isArray(parsed.reference_paths) ? parsed.reference_paths : []),
      require_minimal_ack:
        text(formData.get("require_minimal_ack"), "") === ""
          ? parsed.require_minimal_ack
          : text(formData.get("require_minimal_ack"), "true") !== "false",
      require_final_reply:
        text(formData.get("require_final_reply"), "") === ""
          ? parsed.require_final_reply
          : text(formData.get("require_final_reply"), "true") !== "false",
      token_policy: {
        ...parsedTokenPolicy,
        mode: formText("token_policy_mode") || parsedTokenPolicy.mode,
        per_message_limit: formNumber("token_per_message_limit", parsedTokenPolicy.per_message_limit),
        per_round_limit: formNumber("token_per_round_limit", parsedTokenPolicy.per_round_limit),
        daily_budget: formNumber("token_daily_budget", parsedTokenPolicy.daily_budget),
      },
      runaway_policy: {
        ...parsedRunawayPolicy,
        max_auto_rounds: formNumber("max_auto_rounds", parsedRunawayPolicy.max_auto_rounds),
        human_review_after_rounds: formNumber(
          "human_review_after_rounds",
          parsedRunawayPolicy.human_review_after_rounds,
        ),
      },
      efficiency_policy: {
        ...parsedEfficiencyPolicy,
        parallelism_limit: formNumber("parallelism_limit", parsedEfficiencyPolicy.parallelism_limit),
        prefer_readonly_probe: formBoolean("prefer_readonly_probe", parsedEfficiencyPolicy.prefer_readonly_probe),
        batch_similar_tasks: formBoolean("batch_similar_tasks", parsedEfficiencyPolicy.batch_similar_tasks),
        require_plan_before_execute: formBoolean(
          "require_plan_before_execute",
          parsedEfficiencyPolicy.require_plan_before_execute,
        ),
      },
      debug_policy: {
        ...parsedDebugPolicy,
        debug_enabled: formBoolean("debug_enabled", parsedDebugPolicy.debug_enabled),
        simulation_first: formBoolean("simulation_first", parsedDebugPolicy.simulation_first),
        hardware_write_requires_review: formBoolean(
          "hardware_write_requires_review",
          parsedDebugPolicy.hardware_write_requires_review,
        ),
      },
    },
    {
      providerId: options.providerId ?? undefined,
      roleText: options.responsibility ?? undefined,
      threadText: options.threadText ?? undefined,
    },
  );
}

function providerSortOrder(providerId: string) {
  if (providerId === "codex") return 10;
  if (providerId === "claude") return 20;
  if (providerId === "qwen") return 30;
  if (providerId === "glm") return 40;
  if (providerId === "openclaw") return 50;
  return 90;
}

async function ensureProjectAiProvider(
  projectId: string,
  project: any,
  options: { providerId: string; providerLabel?: string | null; model?: string | null },
) {
  const providerId = normalizePlatformProviderId(options.providerId);
  if (!providerId) return;
  const collaborationConfig =
    project?.collaboration_config && typeof project.collaboration_config === "object"
      ? { ...(project.collaboration_config as Record<string, unknown>) }
      : {};
  const providers = Array.isArray(collaborationConfig.ai_providers)
    ? [...(collaborationConfig.ai_providers as Record<string, unknown>[])]
    : [];
  const hasProvider = providers.some((item) => {
    const id = normalizePlatformProviderId(item.id ?? item.label ?? item.name);
    return id === providerId;
  });
  if (hasProvider) return;

  providers.push({
    id: providerId,
    label: text(options.providerLabel, "") || platformProviderLabel(providerId),
    kind: "thread",
    enabled: true,
    endpoint: platformProviderEndpoint(providerId),
    model: text(options.model, "") || null,
    sort_order: providerSortOrder(providerId),
    metadata: {
      role: `${providerId}_operator`,
    },
  });

  await patchJson(`/api/projects/${projectId}`, {
    collaboration_config: {
      ...collaborationConfig,
      ai_providers: providers,
    },
  });
}

async function ensureNpcSeatContinuity(options: {
  projectId: string;
  seatName: string;
  responsibility?: string | null;
  sourceWorkstationId?: string | null;
  handoffPath: string;
  knowledgeDepositPath?: string | null;
  skillDepositPath?: string | null;
  needDepositPath?: string | null;
  taskDepositPath?: string | null;
  computerNodeId?: string | null;
  model?: string | null;
  additionalSkillIds: string[];
  providerId?: string | null;
  providerLabel?: string | null;
  collabProtocol?: Record<string, unknown> | null;
  heartbeatIntervalSeconds?: number | null;
}) {
  if (supportsLocalCodexAutonomyBridge(options.providerId)) {
    const result = await ensureCodexSeatAutonomyBridge({
      projectId: options.projectId,
      seatName: options.seatName,
      responsibility: options.responsibility,
      sourceWorkstationId: options.sourceWorkstationId,
      handoffPath: options.handoffPath,
      knowledgeDepositPath: options.knowledgeDepositPath,
      skillDepositPath: options.skillDepositPath,
      needDepositPath: options.needDepositPath,
      taskDepositPath: options.taskDepositPath,
      computerNodeId: options.computerNodeId,
      model: options.model,
      additionalSkillIds: options.additionalSkillIds,
      heartbeatIntervalSeconds: options.heartbeatIntervalSeconds,
    });
    return {
      ...result,
      providerRegistration: null as string | null,
      providerActivation: null as string | null,
    };
  }

  if (normalizePlatformProviderId(options.providerId) === "claude") {
    const beforeStatus = await readClaudeSeatAutonomyStatus({
      seatId: options.sourceWorkstationId || options.seatName,
      seatName: options.seatName,
      sourceWorkstationId: options.sourceWorkstationId,
    });
    await ensureNpcKnowledgeDoc({
      handoffPath: options.handoffPath,
      knowledgeDepositPath: options.knowledgeDepositPath,
      skillDepositPath: options.skillDepositPath,
      needDepositPath: options.needDepositPath,
      taskDepositPath: options.taskDepositPath,
      seatName: options.seatName,
      responsibility: text(options.responsibility, ""),
      projectId: options.projectId,
      additionalSkillIds: options.additionalSkillIds,
      providerLabel: text(options.providerLabel, "") || "Claude",
      sourceWorkstationId: options.sourceWorkstationId,
      computerNodeId: options.computerNodeId,
      model: options.model,
      collabProtocol: options.collabProtocol,
    });
    const registration = await ensureClaudeSeatSessionRegistration({
      seatName: options.seatName,
      sourceWorkstationId: options.sourceWorkstationId,
      model: options.model,
    });
    const shouldLaunchSession =
      !beforeStatus.sessionSeen ||
      text(beforeStatus.sessionStatus, "") === "idle" ||
      text(beforeStatus.sessionStatus, "") === "stale";
    const activation = shouldLaunchSession
      ? await launchClaudeSeatSession({
          seatName: options.seatName,
          sourceWorkstationId: options.sourceWorkstationId,
          model: options.model,
        })
      : null;
    return {
      consumerScript: null,
      heartbeat: null,
      providerRegistration: registration ? `Claude session ${registration.sessionId}` : null,
      providerActivation: activation?.launchSummary ?? null,
    };
  }

  await ensureNpcKnowledgeDoc({
    handoffPath: options.handoffPath,
    knowledgeDepositPath: options.knowledgeDepositPath,
    skillDepositPath: options.skillDepositPath,
    needDepositPath: options.needDepositPath,
    taskDepositPath: options.taskDepositPath,
    seatName: options.seatName,
    responsibility: text(options.responsibility, ""),
    projectId: options.projectId,
    additionalSkillIds: options.additionalSkillIds,
    providerLabel: text(options.providerLabel, "") || platformProviderLabel(options.providerId),
    sourceWorkstationId: options.sourceWorkstationId,
    computerNodeId: options.computerNodeId,
    model: options.model,
    collabProtocol: options.collabProtocol,
  });
  return {
    consumerScript: null,
    heartbeat: null,
    providerRegistration: null as string | null,
    providerActivation: null as string | null,
  };
}

async function disableNpcSeatContinuity(options: {
  seatName: string;
  previousSeatName?: string | null;
  providerId?: string | null;
  sourceWorkstationId?: string | null;
  previousSourceWorkstationId?: string | null;
}) {
  const providerId = normalizePlatformProviderId(options.providerId) || "codex";
  const seatNames = Array.from(
    new Set([text(options.seatName, ""), text(options.previousSeatName, "")].filter(Boolean)),
  );
  const sourceWorkstationIds = Array.from(
    new Set(
      [text(options.sourceWorkstationId, ""), text(options.previousSourceWorkstationId, "")]
        .filter(Boolean),
    ),
  );
  const cleanupNotes: string[] = [];

  if (providerId === "codex") {
    let cleaned = false;
    for (const seatName of seatNames) {
      const cleanup = await cleanupCodexSeatAutonomyArtifacts({ seatName });
      cleaned = cleaned || Boolean(cleanup.removedScript || cleanup.removedState || cleanup.removedAutomation);
    }
    if (cleaned) cleanupNotes.push("已关闭持续自治桥");
    return cleanupNotes;
  }

  if (providerId === "claude") {
    let cleaned = false;
    for (const seatName of seatNames) {
      for (const sourceWorkstationId of sourceWorkstationIds.length ? sourceWorkstationIds : [null]) {
        const cleanup = await cleanupClaudeSeatSessionRegistration({
          seatName,
          sourceWorkstationId,
        });
        cleaned = cleaned || cleanup.removed;
      }
    }
    if (cleaned) cleanupNotes.push("已关闭 Claude 持续自治");
    return cleanupNotes;
  }

  return cleanupNotes;
}

function launchDetachedWorkstationOneShot(options: {
  projectId: string;
  workstationId: string;
  messageId?: string | null;
  providerId?: string | null;
  seatName?: string | null;
  ignoreAutomationSwitch?: boolean;
}) {
  const providerId = normalizePlatformProviderId(options.providerId);

  // 如果是Claude席位，尝试启动可见的消息桥接器窗口
  if (providerId === "claude" && options.seatName) {
    try {
      const sessionId = options.workstationId.replace(/^claude-session-/, "");
      if (sessionId && sessionId !== options.workstationId) {
        const bridgeResult = launchClaudeSeatMessageBridge({
          seatName: options.seatName,
          sessionId,
        });
        if (bridgeResult.launched) {
          return {
            launched: true,
            launcher: "claude-seat-message-bridge.ps1",
            stdoutPath: bridgeResult.stdoutPath || "",
            stderrPath: bridgeResult.stderrPath || "",
            bridgeWindow: true,
          };
        }
      }
    } catch (error) {
      console.error("启动Claude消息桥接器失败，回退到后台模式:", error);
    }
  }

  // 原有的后台Python adapter逻辑
  const scriptPath = path.join(workspaceRoot(), "scripts", "platform-workstation-adapter.py");
  const safeWorkstationId =
    text(options.workstationId, "workstation").replace(/[^a-zA-Z0-9._-]+/g, "-").slice(0, 96) || "workstation";
  const logStamp = new Date().toISOString().replace(/[:.]/g, "-");
  const logDir = path.join(workspaceRoot(), "artifacts", "workstation-inbox", "oneshot", "logs");
  mkdirSync(logDir, { recursive: true });
  const stdoutPath = path.join(logDir, `${safeWorkstationId}-${logStamp}.out.log`);
  const stderrPath = path.join(logDir, `${safeWorkstationId}-${logStamp}.err.log`);
  const accessToken = cookies().get(ACCESS_TOKEN_COOKIE)?.value ?? "";
  const pythonCandidates =
    process.platform === "win32"
      ? [
          ["python"],
          ["py", "-3"],
        ]
      : [["python3"], ["python"]];
  const baseArgs = [
    scriptPath,
    "--api-base",
    getApiBaseUrl(),
    "--project-id",
    options.projectId,
    "--workstation-id",
    options.workstationId,
    "--auto-ack",
    "--execute-provider-cli",
    "--limit",
    "1",
    "--output-dir",
    path.join("artifacts", "workstation-inbox", "oneshot"),
  ];
  if (text(options.messageId, "")) {
    baseArgs.push("--message-id", text(options.messageId, ""));
  }
  if (providerId === "codex") {
    baseArgs.push("--executor-timeout-seconds", "600");
  }
  if (accessToken) {
    baseArgs.push("--auth-token", accessToken);
  }
  if (text(options.providerId, "")) {
    baseArgs.push("--provider", text(options.providerId, ""));
  }
  if (options.ignoreAutomationSwitch) {
    baseArgs.push("--ignore-automation-switch");
  }

  let lastError: unknown = null;
  for (const commandParts of pythonCandidates) {
    let stdoutFd: number | null = null;
    let stderrFd: number | null = null;
    try {
      stdoutFd = openSync(stdoutPath, "a");
      stderrFd = openSync(stderrPath, "a");
      const child = spawn(commandParts[0], [...commandParts.slice(1), ...baseArgs], {
        cwd: workspaceRoot(),
        detached: true,
        stdio: ["ignore", stdoutFd, stderrFd],
        windowsHide: true,
        env: {
          ...process.env,
          PYTHONIOENCODING: "utf-8",
          PLATFORM_AUTH_TOKEN: accessToken,
        },
      });
      child.unref();
      if (stdoutFd !== null) closeSync(stdoutFd);
      if (stderrFd !== null) closeSync(stderrFd);
      return {
        launched: true,
        launcher: [...commandParts, "platform-workstation-adapter.py"].join(" "),
        stdoutPath,
        stderrPath,
      };
    } catch (error) {
      lastError = error;
      if (stdoutFd !== null) {
        try {
          closeSync(stdoutFd);
        } catch {}
      }
      if (stderrFd !== null) {
        try {
          closeSync(stderrFd);
        } catch {}
      }
    }
  }

  return {
    launched: false,
    launcher: null,
    stdoutPath,
    stderrPath,
    error:
      lastError instanceof Error
        ? lastError.message
        : "无法拉起本机的一次性工位执行器",
  };
}

function launchDetachedNpcRelay(options: {
  projectId: string;
  relayId?: string | null;
  firstWorkstationId: string;
  firstProviderId?: string | null;
  secondWorkstationId: string;
  secondProviderId?: string | null;
  title: string;
  objective: string;
}) {
  const scriptPath = path.join(workspaceRoot(), "scripts", "platform-composite-relay-orchestrator.py");
  const safeTitle =
    text(options.title, "relay").replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "relay";
  const logStamp = new Date().toISOString().replace(/[:.]/g, "-");
  const logDir = path.join(workspaceRoot(), "artifacts", "workstation-inbox", "relay", "logs");
  mkdirSync(logDir, { recursive: true });
  const stdoutPath = path.join(logDir, `${safeTitle}-${logStamp}.out.log`);
  const stderrPath = path.join(logDir, `${safeTitle}-${logStamp}.err.log`);
  const accessToken = cookies().get(ACCESS_TOKEN_COOKIE)?.value ?? "";
  const pythonCandidates =
    process.platform === "win32"
      ? [
          ["python"],
          ["py", "-3"],
        ]
      : [["python3"], ["python"]];
  const baseArgs = [
    scriptPath,
    "--api-base",
    getApiBaseUrl(),
    "--project-id",
    options.projectId,
    "--relay-id",
    options.relayId || "",
    "--first-workstation-id",
    options.firstWorkstationId,
    "--first-provider",
    normalizePlatformProviderId(options.firstProviderId) || "codex",
    "--second-workstation-id",
    options.secondWorkstationId,
    "--second-provider",
    normalizePlatformProviderId(options.secondProviderId) || "claude",
    "--title",
    options.title,
    "--objective",
    options.objective,
  ];

  let lastError: unknown = null;
  for (const commandParts of pythonCandidates) {
    let stdoutFd: number | null = null;
    let stderrFd: number | null = null;
    try {
      stdoutFd = openSync(stdoutPath, "a");
      stderrFd = openSync(stderrPath, "a");
      const child = spawn(commandParts[0], [...commandParts.slice(1), ...baseArgs], {
        cwd: workspaceRoot(),
        detached: true,
        stdio: ["ignore", stdoutFd, stderrFd],
        windowsHide: true,
        env: {
          ...process.env,
          PYTHONIOENCODING: "utf-8",
          PLATFORM_AUTH_TOKEN: accessToken,
        },
      });
      child.unref();
      if (stdoutFd !== null) closeSync(stdoutFd);
      if (stderrFd !== null) closeSync(stderrFd);
      return {
        launched: true,
        launcher: [...commandParts, "platform-composite-relay-orchestrator.py"].join(" "),
        stdoutPath,
        stderrPath,
      };
    } catch (error) {
      lastError = error;
      if (stdoutFd !== null) {
        try {
          closeSync(stdoutFd);
        } catch {}
      }
      if (stderrFd !== null) {
        try {
          closeSync(stderrFd);
        } catch {}
      }
    }
  }

  return {
    launched: false,
    launcher: null,
    stdoutPath,
    stderrPath,
    error:
      lastError instanceof Error
        ? lastError.message
        : "无法拉起平台多 NPC 接力编排器",
  };
}

function buildNpcRelayStatusBody(options: {
  relayId: string;
  title: string;
  objective: string;
  firstWorkstationId: string;
  firstProviderId: string;
  secondWorkstationId: string;
  secondProviderId: string;
  stdoutPath?: string | null;
  stderrPath?: string | null;
  launchError?: string | null;
}) {
  const firstLabel = platformProviderLabel(options.firstProviderId);
  const secondLabel = platformProviderLabel(options.secondProviderId);
  return [
    `relay_id: ${options.relayId}`,
    `目标: ${options.objective}`,
    `第一棒: ${firstLabel} / ${options.firstWorkstationId}`,
    `第二棒: ${secondLabel} / ${options.secondWorkstationId}`,
    "人工审核点: 第二棒最终回复完成后，用户需要确认是否可作为正式交付；涉及硬件、费用、删除、发布等高风险动作必须另走审批。",
    "失败重试: 如果状态变为 failed，回到“多 NPC 接力”动作台，保留同一目标重新选择可用线程后再提交。",
    options.stdoutPath ? `stdout: ${options.stdoutPath}` : "",
    options.stderrPath ? `stderr: ${options.stderrPath}` : "",
    options.launchError ? `启动错误: ${options.launchError}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

async function postNpcRelayStatus(options: {
  projectId: string;
  relayId: string;
  title: string;
  objective: string;
  firstWorkstationId: string;
  firstProviderId: string;
  secondWorkstationId: string;
  secondProviderId: string;
  status: "pending" | "running" | "failed" | "completed";
  stdoutPath?: string | null;
  stderrPath?: string | null;
  launchError?: string | null;
}) {
  return postJson("/api/collaboration/messages", {
    project_id: options.projectId,
    agent_id: "platform-relay",
    message_type: "relay_status",
    title: `${options.title} / 接力状态`,
    body: buildNpcRelayStatusBody(options),
    sender_type: "human",
    sender_id: "platform-relay",
    recipient_type: "project",
    recipient_id: options.projectId,
    status: options.status,
  });
}

function resolveProjectWorkstationProviderId(
  project: Record<string, unknown> | null | undefined,
  workstationId: string | null | undefined,
  fallbackProviderId: string,
) {
  const normalizedWorkstationId = text(workstationId, "");
  if (!normalizedWorkstationId) return normalizePlatformProviderId(fallbackProviderId) || fallbackProviderId;
  const workstations = readProjectThreadWorkstations(project);
  const workstation =
    workstations.find((item) =>
      workstationLookupKeys(item).some((candidate) => candidate === normalizedWorkstationId),
    ) ?? null;
  if (!workstation) {
    return normalizePlatformProviderId(fallbackProviderId) || fallbackProviderId;
  }
  const metadata =
    workstation.metadata && typeof workstation.metadata === "object"
      ? (workstation.metadata as Record<string, unknown>)
      : {};
  return (
    normalizePlatformProviderId(
      workstation.ai_provider_id ??
        workstation.ai_provider ??
        metadata.provider_id ??
        metadata.provider ??
        metadata.provider_label,
    ) ||
    derivePlatformProviderIdFromThreadId(
      workstation.source_workstation_id ??
        metadata.source_workstation_id ??
        workstation.id ??
        workstation.workstation_id ??
        normalizedWorkstationId,
    ) ||
    normalizePlatformProviderId(fallbackProviderId) ||
    fallbackProviderId
  );
}

async function resolveNpcSeatDispatchMode(options: {
  project: Record<string, unknown>;
  formData: FormData;
  payload: CollaborationMessagePayload;
  messageId?: string | null;
}) {
  const npcSeatId = normalizeMessageFormValue(options.formData.get("npc_seat_id"));
  if (
    !npcSeatId ||
    !options.payload.project_id ||
    options.payload.message_type !== "agent_command" ||
    options.payload.recipient_type !== "workstation" ||
    !options.payload.recipient_id
  ) {
    return null;
  }

  const workstations = readProjectThreadWorkstations(options.project);
  const seat =
    workstations.find((item) =>
      workstationLookupKeys(item).some((candidate) => candidate === npcSeatId),
    ) ?? null;
  if (!seat) return null;

  const metadata =
    seat.metadata && typeof seat.metadata === "object" ? (seat.metadata as Record<string, unknown>) : {};
  const providerId =
    normalizePlatformProviderId(
      seat.ai_provider_id ?? seat.ai_provider ?? metadata.provider_id ?? metadata.provider_label,
    ) || "codex";
  const automationEnabled = readSeatAutomationEnabled(metadata, false);
  if (automationEnabled) {
    return {
      mode: "automation" as const,
      launched: false,
      providerId,
      seatName: text(seat.name ?? seat.workstation_name, npcSeatId),
    };
  }

  const seatName = text(seat.name ?? seat.workstation_name, npcSeatId);
  const launchResult = launchDetachedWorkstationOneShot({
    projectId: options.payload.project_id,
    workstationId: options.payload.recipient_id,
    messageId: options.messageId,
    providerId,
    seatName,
  });
  return {
    mode: "one-shot" as const,
    ...launchResult,
    providerId,
    seatName,
  };
}

async function readNpcProvisioningSummary(options: {
  seatId: string;
  seatName: string;
  providerId: string;
  providerLabel?: string | null;
  sourceWorkstationId?: string | null;
}) {
  const providerId = normalizePlatformProviderId(options.providerId);
  const sourceWorkstationId = text(options.sourceWorkstationId, "") || null;
  if (providerId === "codex") {
    const status = await readCodexSeatAutonomyStatus({
      seatId: options.seatId,
      seatName: options.seatName,
      sourceWorkstationId,
    });
    return summarizeNpcProvisioning({
      providerId,
      providerLabel: options.providerLabel,
      sourceThreadId: sourceWorkstationId,
      hasActiveRequirement: false,
      autonomyReady: status.autonomyReady,
      supportsLocalAutonomyBridge: true,
      consumerScriptExists: status.consumerScriptExists,
      consumerStateExists: status.consumerStateExists,
      consumerStateStale: status.consumerStateStale,
      heartbeatMissing: status.heartbeatMissing,
      heartbeatStatus: status.automationStatus,
    });
  }
  if (providerId === "claude") {
    const status = await readClaudeSeatAutonomyStatus({
      seatId: options.seatId,
      seatName: options.seatName,
      sourceWorkstationId,
    });
    return summarizeNpcProvisioning({
      providerId,
      providerLabel: options.providerLabel,
      sourceThreadId: sourceWorkstationId,
      hasActiveRequirement: false,
      autonomyReady: status.autonomyReady,
      supportsLocalAutonomyBridge: false,
      sessionSeen: status.sessionSeen,
      sessionRegistered: status.sessionRegistered,
      sessionStatus: status.sessionStatus,
      sessionLaunchBlocked: status.sessionLaunchBlocked,
      sessionLaunchBlockReason: status.lastLaunchErrorSummary,
    });
  }
  return summarizeNpcProvisioning({
    providerId,
    providerLabel: options.providerLabel,
    sourceThreadId: sourceWorkstationId,
    hasActiveRequirement: false,
    supportsLocalAutonomyBridge: false,
  });
}

function revalidateProjectSurfaces(projectId: string) {
  revalidatePath(`/projects/${projectId}`);
  revalidatePath(`/projects/${projectId}/2d-upgrade`);
  revalidatePath(`/projects/${projectId}/workbench`);
  revalidatePath(`/projects/${projectId}/skill-forge`);
  revalidatePath(`/projects/${projectId}/company`);
  revalidatePath(`/projects/${projectId}/robotics`);
  revalidatePath("/projects");
  revalidatePath("/projects/mode-choice");
  revalidatePath("/projects/mode-choice/2d-edu");
  revalidatePath("/projects/mode-choice/3d-dev");
  revalidatePath("/projects/mode-choice/3d-edu");
  revalidatePath("/login");
}

function seatIdentityValues(item: Record<string, unknown>) {
  const metadata = readRecord(item.metadata);
  const extraData = readRecord(item.extra_data ?? item.extraData);
  return [
    item.id,
    item.config_id,
    item.row_id,
    item.rowId,
    item.name,
    item.workstation_name,
    item.agent_id,
    item.agentId,
    item.source_workstation_id,
    metadata.source_workstation_id,
    metadata.bound_thread_id,
    extraData.source_workstation_id,
  ]
    .map((value) => text(value, ""))
    .filter(Boolean);
}

function canonicalSeatRecipientId(seat: Record<string, unknown>) {
  return text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, "");
}

function resolveGitRollbackAlignmentTargets(project: Record<string, unknown>) {
  const config = readProjectCollaborationConfig(project);
  const seats = readProjectThreadWorkstations(project);
  const workstationProfiles = readRecord(config.workstation_profiles);
  const targets = new Map<string, { id: string; label: string; reason: string }>();
  const rememberSeat = (seat: Record<string, unknown>, reason: string) => {
    const id = canonicalSeatRecipientId(seat);
    if (!id || targets.has(id)) return;
    targets.set(id, {
      id,
      label: text(seat.name ?? seat.workstation_name, id),
      reason,
    });
  };

  for (const seat of seats) {
    const haystack = `${text(seat.name ?? seat.workstation_name, "")} ${text(seat.responsibility, "")}`.toLowerCase();
    if (/(boss|负责人|分工|总控|项目经理|pm|产品)/i.test(haystack)) {
      rememberSeat(seat, "Boss / 项目收口");
    }
  }

  for (const [workstationId, rawProfile] of Object.entries(workstationProfiles)) {
    const profile = readRecord(rawProfile);
    const leadId = text(profile.lead_seat_id ?? profile.leadSeatId, "");
    if (!leadId) continue;
    const leadSeat = seats.find((seat) => seatIdentityValues(seat).includes(leadId));
    if (leadSeat) {
      rememberSeat(leadSeat, `工位长 / ${text(profile.name, workstationId) || workstationId}`);
    }
  }

  const projectName = text(project.name ?? project.project_name, "").toLowerCase();
  if (targets.size === 0 && /yuespeak|yue/i.test(projectName)) {
    const boss = seats.find((seat) => /boss/i.test(`${text(seat.name ?? seat.workstation_name, "")} ${text(seat.responsibility, "")}`));
    if (boss) rememberSeat(boss, "Boss / 项目收口");
  }
  if (targets.size === 0 && seats[0]) {
    rememberSeat(seats[0], "默认项目 NPC");
  }
  return Array.from(targets.values()).slice(0, 12);
}

async function notifyGitRollbackAlignmentTargets(
  projectId: string,
  project: Record<string, unknown>,
  options: {
    targetRef: string;
    notes: string;
    requestedBy: string;
    preflightQueued: number;
    preflightRunnableNodeCount: number;
    preflightOnlineNodeCount?: number;
  },
) {
  const targets = resolveGitRollbackAlignmentTargets(project);
  let queued = 0;
  const repository = text(project.github_url ?? project.githubUrl ?? project.local_git_url ?? project.localGitUrl, "未绑定仓库");
  for (const target of targets) {
    const body = [
      `类型：Git 回退对齐请求`,
      `目标版本：${options.targetRef}`,
      `仓库：${repository}`,
      `发起人：${options.requestedBy}`,
      `原因：${options.notes || "未填写"}`,
      `Runner 只读预检：${
        options.preflightQueued
          ? `已下发 ${options.preflightQueued} 台`
          : options.preflightRunnableNodeCount
            ? "存在在线 Runner 但下发失败，请检查 Runner 收件箱"
            : options.preflightOnlineNodeCount
              ? "电脑登记在线但缺少 Runner 绑定，请先回电脑接入面板修复"
              : "暂无在线 Runner，预检待电脑上线后重试"
      }`,
      "",
      "请在绑定线程中只做对齐检查，不要执行 destructive git reset。",
      "回执格式：已对齐 / 阻塞 / 需人工；同时说明当前分支、未提交改动、需要保留的文件和下一步建议。",
    ].join("\n");
    try {
      await postJson("/api/collaboration/messages", {
        project_id: projectId,
        agent_id: target.id,
        message_type: "agent_command",
        title: `Git 回退对齐 / ${options.targetRef}`,
        body,
        sender_type: "human",
        sender_id: options.requestedBy,
        recipient_type: "thread_workstation",
        recipient_id: target.id,
        status: "queued",
        metadata: {
          source: "git_rollback_alignment",
          target_ref: options.targetRef,
          target_reason: target.reason,
        },
      });
      queued += 1;
    } catch {
      // 单个 NPC 通知失败不阻断 Git 回退登记，避免前端把已登记请求误判为失败。
    }
  }
  return { queued, targetCount: targets.length };
}

export async function 创建项目工作区(formData: FormData) {
  const result = await postJson("/api/projects", {
    name: String(formData.get("name") ?? "").trim(),
    description: String(formData.get("description") ?? "").trim() || null,
    project_type: String(formData.get("project_type") ?? "").trim() || "software",
    github_url: String(formData.get("github_url") ?? "").trim() || null,
    local_git_url: String(formData.get("local_git_url") ?? "").trim() || null,
    default_branch: String(formData.get("default_branch") ?? "").trim() || "main",
    develop_branch: String(formData.get("develop_branch") ?? "").trim() || "develop",
  });
  const project = result.data ?? result;
  revalidatePath("/projects");
  revalidatePath("/");
  const projectId = String(project.id ?? "").trim();
  redirect(projectId ? `/projects/${encodeURIComponent(projectId)}/2d-upgrade` : "/projects");
}

export async function 创建项目任务(formData: FormData) {
  const projectId = String(formData.get("project_id") ?? "").trim();
  if (!projectId) return;
  const rawDueAt = String(formData.get("due_at") ?? "").trim();
  const dueAtDate = rawDueAt ? new Date(rawDueAt) : null;
  const dueAt = dueAtDate && !Number.isNaN(dueAtDate.getTime()) ? dueAtDate.toISOString() : null;
  const rawReturnTo = String(formData.get("return_to") ?? "").trim();

  await postJson("/api/tasks", {
    project_id: projectId,
    title: String(formData.get("title") ?? "").trim() || "未命名任务",
    description: String(formData.get("description") ?? "").trim() || null,
    module: String(formData.get("module") ?? "").trim() || null,
    priority: String(formData.get("priority") ?? "P2").trim() || "P2",
    status: String(formData.get("status") ?? "draft").trim() || "draft",
    branch: String(formData.get("branch") ?? "").trim() || null,
    related_issue: String(formData.get("related_issue") ?? "").trim() || null,
    assignee_agent_id: String(formData.get("assignee_agent_id") ?? "").trim() || null,
    due_at: dueAt,
    reviewers: parseStringList(formData.get("reviewers")) ?? [],
    acceptance_criteria: parseStringList(formData.get("acceptance_criteria")) ?? [],
  });

  revalidateProjectSurfaces(projectId);
  revalidatePath("/tasks");
  if (rawReturnTo) {
    redirect(normalizeProjectReturnPath(projectId, rawReturnTo, "schedule"));
  }
}

export async function 创建项目需求(formData: FormData) {
  const projectId = String(formData.get("project_id") ?? "").trim();
  if (!projectId) return;

  await postJson("/api/requirements", {
    project_id: projectId,
    task_id: String(formData.get("task_id") ?? "").trim() || null,
    title: String(formData.get("title") ?? "").trim() || "未命名需求",
    requirement_type: String(formData.get("requirement_type") ?? "thread_request").trim() || "thread_request",
    module: String(formData.get("module") ?? "").trim() || null,
    priority: String(formData.get("priority") ?? "high").trim() || "high",
    status: String(formData.get("status") ?? "waiting_response").trim() || "waiting_response",
    from_agent: String(formData.get("from_agent") ?? "").trim() || null,
    to_agent: String(formData.get("to_agent") ?? "").trim() || null,
    context_summary: String(formData.get("context_summary") ?? "").trim() || null,
    expected_output: String(formData.get("expected_output") ?? "").trim() || null,
    related_files: parseStringList(formData.get("related_files")) ?? [],
    max_response_tokens: Number(formData.get("max_response_tokens") ?? 3000) || 3000,
    opening_message: String(formData.get("opening_message") ?? "").trim() || null,
  });

  revalidateProjectSurfaces(projectId);
  revalidatePath("/requirements");
}

export async function submitApprovalAction(
  approvalId: string,
  action: "approve" | "reject" | "request-changes",
  formData: FormData,
) {
  const result = await postJson(`/api/approvals/${approvalId}/${action}`, {
    notes: String(formData.get("notes") ?? "").trim() || action,
  });
  const approval = result.data ?? result;
  revalidatePath("/approvals");
  revalidatePath("/lab");
  if (approval?.task_id) {
    revalidatePath(`/tasks/${approval.task_id}`);
    revalidatePath(`/tasks/${approval.task_id}/context`);
  }
}

export async function submitApprovalRequest(formData: FormData) {
  const result = await postJson("/api/approvals", {
    project_id: String(formData.get("project_id") ?? "") || null,
    task_id: String(formData.get("task_id") ?? ""),
    level: String(formData.get("level") ?? "H3"),
    action: String(formData.get("action") ?? "firmware flash"),
    status: String(formData.get("status") ?? "pending"),
    notes: String(formData.get("notes") ?? "") || null,
  });
  const approval = result.data ?? result;
  revalidatePath("/lab");
  revalidatePath("/approvals");
  if (approval?.task_id) {
    revalidatePath(`/tasks/${approval.task_id}`);
    revalidatePath(`/tasks/${approval.task_id}/context`);
  }
}

export async function 提交审批动作(
  approvalId: string,
  action: "approve" | "reject" | "request-changes",
  formData: FormData,
) {
  const result = await postJson(`/api/approvals/${approvalId}/${action}`, {
    notes: String(formData.get("notes") ?? "").trim() || (action === "approve" ? "??" : action === "reject" ? "??" : "????"),
  });
  const approval = result.data ?? result;
  revalidatePath("/approvals");
  revalidatePath("/lab");
  if (approval?.task_id) {
    revalidatePath(`/tasks/${approval.task_id}`);
    revalidatePath(`/tasks/${approval.task_id}/context`);
  }
}

export async function 创建审批记录(formData: FormData) {
  const result = await postJson("/api/approvals", {
    project_id: String(formData.get("project_id") ?? "") || null,
    task_id: String(formData.get("task_id") ?? ""),
    level: String(formData.get("level") ?? "H3"),
    action: String(formData.get("action") ?? "????"),
    status: String(formData.get("status") ?? "pending"),
    approver_user_id: String(formData.get("approver_user_id") ?? "") || null,
    notes: String(formData.get("notes") ?? "") || null,
  });
  const approval = result.data ?? result;
  revalidatePath("/lab");
  revalidatePath("/approvals");
  if (approval?.task_id) {
    revalidatePath(`/tasks/${approval.task_id}`);
    revalidatePath(`/tasks/${approval.task_id}/context`);
  }
}

export async function 提交需求动作(
  requirementId: string,
  action: "accept" | "escalate" | "close" | "promote-to-knowledge",
) {
  await postJson(`/api/requirements/${requirementId}/${action}`, {
    actor_type: "human",
    actor_id: "human-chief",
    target_type: "knowledge",
    note:
      action === "accept"
        ? "由前端需求库直接采纳"
        : action === "escalate"
          ? "由前端需求库升级处理"
          : action === "promote-to-knowledge"
            ? "由前端需求库沉淀到知识库"
            : "由前端需求库关闭",
  });
  revalidatePath("/requirements");
  revalidatePath("/knowledge");
  revalidatePath("/handoffs");
  revalidatePath("/context-health");
}

export async function 登记需求最小回执(
  requirementId: string,
  ackKind: "claimed" | "done",
  formData: FormData,
) {
  const projectId = String(formData.get("project_id") ?? "").trim();
  const requirementTitle = String(formData.get("requirement_title") ?? "").trim() || "未命名需求";
  const target = String(formData.get("target") ?? "").trim();
  const senderSeatId = String(formData.get("sender_seat_id") ?? "").trim();
  const route = String(formData.get("route") ?? "").trim();

  if (!projectId || !requirementId) return;

  const senderType = route.includes("人工") || target.startsWith("human:") ? "human" : "agent";
  const title = ackKind === "claimed" ? `${requirementTitle} 已接单` : `${requirementTitle} 已完成`;
  const body =
    ackKind === "claimed"
      ? String(formData.get("claimed_body") ?? "").trim() || "已接单，开始处理，稍后补最小报告。"
      : String(formData.get("done_body") ?? "").trim() || "已完成，已回最小报告，可继续看下一条。";

  const senderId =
    senderType === "agent"
      ? senderSeatId || target || String(formData.get("sender_id") ?? "codex-mainline").trim()
      : target || String(formData.get("sender_id") ?? "human-chief").trim();

  if (ackKind === "claimed") {
    const targetType =
      senderType === "human"
        ? "human"
        : target.startsWith("ai:")
          ? "agent"
          : "workstation";
    await postJson(`/api/requirements/${encodeURIComponent(requirementId)}/dispatch`, {
      target_type: targetType,
      target_id: senderId,
      note: body,
      status: "in_progress",
      title,
      body,
    });
  } else {
    await postJson(`/api/requirements/${encodeURIComponent(requirementId)}/final-reply`, {
      sender_type: senderType,
      sender_id: senderId,
      recipient_type: "project",
      recipient_id: projectId,
      message: body,
      status: "done",
      title,
    });
  }

  revalidateProjectSurfaces(projectId);
  redirect(
    `/projects/${projectId}?panel=team&tab=exchange&team_notice=${encodeURIComponent(
      ackKind === "claimed" ? "已登记最小接单回执" : "已登记完成回执",
    )}`,
  );
}

export async function 运行平台自治推进(projectId: string, formData: FormData) {
  if (!projectId) return;
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "git");
  try {
    const result = await postJson(`/api/requirements/projects/${encodeURIComponent(projectId)}/autonomy-sweep`, {});
    const payload = result?.data ?? result ?? {};
    const dispatched = Number(payload.dispatched ?? 0) || 0;
    const finalized = Number(payload.finalized ?? 0) || 0;
    const syncedCodexCommands = await syncPlatformCodexDispatchInbox(projectId);
    revalidateProjectSurfaces(projectId);
    redirect(
      withQueryValue(
        returnTo,
        "team_notice",
        `自治推进完成：派单 ${dispatched} 条，补最终回复 ${finalized} 条，同步 Codex 指令 ${syncedCodexCommands} 条`,
      ),
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "自治推进失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 沉淀需求到知识库(requirementId: string) {
  await postJson(`/api/requirements/${requirementId}/promote-to-knowledge`, {
    actor_type: "human",
    actor_id: "human-chief",
    target_type: "knowledge",
    note: "由需求页直接沉淀为知识库样板",
  });
  revalidatePath("/requirements");
  revalidatePath("/knowledge");
  revalidatePath("/handoffs");
  revalidatePath("/context-health");
}

export async function 通过自主合作待审消息(messageId: string, projectId: string) {
  await postJson(`/api/collaboration/messages/${encodeURIComponent(messageId)}/review/approve`, {});
  revalidatePath(`/projects/${projectId}/cockpit`);
  revalidatePath(`/projects/${projectId}/workbench`);
}

export async function 打回自主合作待审消息(messageId: string, projectId: string) {
  await postJson(`/api/collaboration/messages/${encodeURIComponent(messageId)}/review/reject`, {});
  revalidatePath(`/projects/${projectId}/cockpit`);
  revalidatePath(`/projects/${projectId}/workbench`);
}

export async function 切换智能体状态(agentId: string, enabled: boolean) {
  await postJson(`/api/agents/${agentId}/${enabled ? "enable" : "disable"}`, {
    actor_type: "human",
    actor_id: "human-chief",
    note: enabled ? "由前端工位启用" : "由前端工位停用",
  });
  revalidatePath(`/agents/${agentId}`);
  revalidatePath("/agents");
}

export async function 接受交接(taskId: string, handoffId: string, agentId: string | null | undefined) {
  await postJson(`/api/tasks/${taskId}/handoffs/${handoffId}/accept`, {
    actor_type: "agent",
    actor_id: agentId ?? "agent_boss",
    note: "由前端交接站确认接手",
  });
  revalidatePath("/handoffs");
  revalidatePath(`/tasks/${taskId}`);
  revalidatePath(`/tasks/${taskId}/context`);
  revalidatePath("/requirements");
  revalidatePath("/knowledge");
  revalidatePath("/context-health");
}

export async function 更新项目配置(projectId: string, formData: FormData) {
  const requirementPolicyText = String(formData.get("requirement_policy") ?? "").trim();
  const collaborationConfigText = String(formData.get("collaboration_config") ?? "").trim();
  const computerNodesText = String(formData.get("computer_nodes") ?? "").trim();
  const aiProvidersText = String(formData.get("ai_providers") ?? "").trim();
  const threadWorkstationsText = String(formData.get("thread_workstations") ?? "").trim();
  let requirementPolicy: unknown = {};
  let collaborationConfig: unknown = {};
  if (requirementPolicyText) {
    try {
      requirementPolicy = JSON.parse(requirementPolicyText);
    } catch {
      requirementPolicy = {};
    }
  }
  if (collaborationConfigText) {
    try {
      collaborationConfig = JSON.parse(collaborationConfigText);
    } catch {
      collaborationConfig = {};
    }
  }
  const configBase = collaborationConfig && typeof collaborationConfig === "object" ? (collaborationConfig as Record<string, unknown>) : {};
  if (computerNodesText || aiProvidersText || threadWorkstationsText) {
    const mergeArray = (text: string, key: "computer_nodes" | "ai_providers" | "thread_workstations") => {
      if (!text) return Array.isArray(configBase[key]) ? configBase[key] : [];
      try {
        const parsed = JSON.parse(text);
        return Array.isArray(parsed) ? parsed : [];
      } catch {
        return [];
      }
    };
    collaborationConfig = {
      ...configBase,
      computer_nodes: mergeArray(computerNodesText, "computer_nodes"),
      ai_providers: mergeArray(aiProvidersText, "ai_providers"),
      thread_workstations: mergeArray(threadWorkstationsText, "thread_workstations"),
    };
  }
  await patchJson(`/api/projects/${projectId}`, {
    name: String(formData.get("name") ?? ""),
    description: String(formData.get("description") ?? ""),
    project_type: String(formData.get("project_type") ?? ""),
    github_url: String(formData.get("github_url") ?? ""),
    local_git_url: String(formData.get("local_git_url") ?? ""),
    default_branch: String(formData.get("default_branch") ?? "main"),
    develop_branch: String(formData.get("develop_branch") ?? "develop"),
    requirement_policy: requirementPolicy,
    collaboration_config: collaborationConfig,
  });
  revalidateProjectSurfaces(projectId);
}

export async function 创建开发工坊工位(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "development-workshop");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig = readProjectCollaborationConfig(project);
    const currentStations = readDevelopmentWorkshopStations(project);
    const nextStation = buildDevelopmentWorkshopStationFromFormData(formData);
    const nextStations = [...currentStations, nextStation];
    collaborationConfig.development_workshop_stations = nextStations;
    await ensureDevelopmentWorkshopStationKnowledgeDoc({
      stationId: nextStation.id,
      label: nextStation.label,
      detail: nextStation.detail,
      knowledgeBase: nextStation.knowledgeBase,
      runnerCapabilities: nextStation.runnerCapabilities,
      aiResponsibilities: nextStation.aiResponsibilities,
      nextActions: nextStation.nextActions,
      approvalPolicy: nextStation.approvalPolicy,
    });

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: collaborationConfig,
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", `已添加工位：${nextStation.label}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "添加开发工坊工位失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 更新开发工坊工位(projectId: string, stationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "development-workshop");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig = readProjectCollaborationConfig(project);
    const currentStations = readDevelopmentWorkshopStations(project);
    const nextStation = buildDevelopmentWorkshopStationFromFormData(formData, stationId);
    const targetIndex = currentStations.findIndex((item) => item.id === stationId);
    if (targetIndex < 0) {
      throw new Error("没有找到这个工位");
    }
    const nextStations = [...currentStations];
    nextStations[targetIndex] = nextStation;
    collaborationConfig.development_workshop_stations = nextStations;
    await ensureDevelopmentWorkshopStationKnowledgeDoc({
      stationId: nextStation.id,
      label: nextStation.label,
      detail: nextStation.detail,
      knowledgeBase: nextStation.knowledgeBase,
      runnerCapabilities: nextStation.runnerCapabilities,
      aiResponsibilities: nextStation.aiResponsibilities,
      nextActions: nextStation.nextActions,
      approvalPolicy: nextStation.approvalPolicy,
    });

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: collaborationConfig,
    });
    revalidateProjectSurfaces(projectId);
    let nextPath = withQueryValue(returnTo, "team_notice", `已更新工位：${nextStation.label}`);
    nextPath = withQueryValue(nextPath, "station", nextStation.id);
    redirect(nextPath);
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "更新开发工坊工位失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 删除开发工坊工位(projectId: string, stationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "development-workshop");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig = readProjectCollaborationConfig(project);
    const currentStations = readDevelopmentWorkshopStations(project);
    const removed = currentStations.find((item) => item.id === stationId) ?? null;
    if (!removed) {
      throw new Error("没有找到这个工位");
    }
    if (currentStations.length <= 1) {
      throw new Error("开发工坊至少要保留 1 个工位");
    }
    collaborationConfig.development_workshop_stations = currentStations.filter((item) => item.id !== stationId);

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: collaborationConfig,
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", `已删除工位：${removed.label}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "删除开发工坊工位失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 更新任务DDL(projectId: string, taskId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "schedule");
  const rawDueAt = String(formData.get("due_at") ?? "").trim();
  const note = String(formData.get("note") ?? "").trim();

  try {
    const actorId = await resolveProjectHumanActorId(projectId);
    const dueAtDate = rawDueAt ? new Date(rawDueAt) : null;
    if (dueAtDate && Number.isNaN(dueAtDate.getTime())) {
      throw new Error("DDL 时间格式无效");
    }
    const dueAt = dueAtDate ? dueAtDate.toISOString() : null;
    await patchJson(`/api/tasks/${encodeURIComponent(taskId)}`, {
      due_at: dueAt,
    });
    if (note) {
      await postJson(`/api/tasks/${encodeURIComponent(taskId)}/messages`, {
        project_id: projectId,
        message_type: "task_message",
        sender_type: "human",
        sender_id: actorId,
        body: `日程日历备注：${note}`,
        data: {
          kind: "schedule_deadline_note",
          due_at: dueAt,
        },
      });
    }
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/tasks/${taskId}`);
    redirect(withQueryValue(returnTo, "team_notice", dueAt ? "任务 DDL 已更新" : "任务 DDL 已清空"));
  } catch (error) {
    const message = error instanceof Error ? error.message : "更新任务 DDL 失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 保存项目日程安排(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "schedule");
  const scheduleDate = String(formData.get("schedule_date") ?? "").trim() || new Date().toISOString().slice(0, 10);
  const dailyPlan = String(formData.get("daily_plan") ?? "").trim();
  const ddlNote = String(formData.get("ddl_note") ?? "").trim();

  try {
    const { currentUser, project } = await ensureProjectCollaborationAccess(projectId);
    const actorId = text(currentUser?.id ?? currentUser?.email, "human-chief");
    const collaborationConfig =
      project?.collaboration_config && typeof project.collaboration_config === "object"
        ? { ...(project.collaboration_config as Record<string, unknown>) }
        : {};
    const dailySchedule =
      collaborationConfig.daily_schedule && typeof collaborationConfig.daily_schedule === "object"
        ? { ...(collaborationConfig.daily_schedule as Record<string, unknown>) }
        : {};

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        daily_schedule: {
          ...dailySchedule,
          [scheduleDate]: {
            date: scheduleDate,
            daily_plan: dailyPlan,
            ddl_note: ddlNote,
            updated_at: new Date().toISOString(),
            updated_by: actorId,
          },
        },
      },
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", "每日安排已保存"));
  } catch (error) {
    const message = error instanceof Error ? error.message : "保存每日安排失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 保存串口电视配置(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "device-debug");
  const baudRate = Number(formData.get("baud_rate") ?? 115200) || 115200;
  const protocol = String(formData.get("protocol") ?? "aicollab-csv-v1").trim() || "aicollab-csv-v1";
  const frameFormat =
    String(formData.get("frame_format") ?? "@xy,<x>,<y>\\n 或 @sample,<t>,<ch1>,<ch2>...\\n").trim() ||
    "@xy,<x>,<y>\\n";
  const channelNames =
    parseStringList(formData.get("channel_names")) ?? ["x", "y"];
  const notes = String(formData.get("notes") ?? "").trim();

  try {
    const { currentUser, project } = await ensureProjectCollaborationAccess(projectId);
    const actorId = text(currentUser?.id ?? currentUser?.email, "human-chief");
    const collaborationConfig =
      project?.collaboration_config && typeof project.collaboration_config === "object"
        ? { ...(project.collaboration_config as Record<string, unknown>) }
        : {};

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        serial_debug_assistant: {
          ...((collaborationConfig.serial_debug_assistant &&
          typeof collaborationConfig.serial_debug_assistant === "object"
            ? collaborationConfig.serial_debug_assistant
            : {}) as Record<string, unknown>),
          protocol,
          baud_rate: baudRate,
          frame_format: frameFormat,
          channel_names: channelNames,
          notes,
          updated_at: new Date().toISOString(),
          updated_by: actorId,
        },
      },
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", "设备调试协议已保存"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "保存设备调试协议失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 请求串口USB扫描(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "device-debug");
  const targetNodeId = String(formData.get("computer_node_id") ?? "all").trim() || "all";
  try {
    await ensureProjectCollaborationAccess(projectId);
    const result = await getJson(`/api/collaboration/projects/${projectId}/computer-nodes`);
    const nodes = asArray<Record<string, unknown>>(result?.data ?? result);
    const targetNodes =
      targetNodeId === "all"
        ? nodes
        : nodes.filter((node) => text(node.id ?? node.node_id ?? node.name ?? node.label, "") === targetNodeId);
    if (!targetNodes.length) {
      throw new Error("没有可扫描的电脑，请先在电脑接入管理里添加电脑。");
    }

    const requestedAt = new Date().toISOString();

    for (const node of targetNodes) {
      const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "");
      if (!nodeId) continue;
      await postJson(`/api/collaboration/projects/${projectId}/runner-commands`, {
        computer_node_id: nodeId,
        title: "设备调试台 / 扫描 USB 与串口设备",
        body: JSON.stringify(
          {
            kind: "serial.usb.scan",
            version: "serial-tv.v1",
            requested_at: requestedAt,
            scan: ["serial_ports", "usb_devices"],
            expected_reply: {
              message_type: "runner_result",
              data_key: "serial_devices",
              item_shape: {
                port: "COM3 or /dev/ttyUSB0",
                label: "USB Serial / CH340 / CP210x / STM32 VCP",
                vendor_id: "optional",
                product_id: "optional",
                serial_number: "optional",
              },
            },
          },
          null,
          2,
        ),
      });
    }

    revalidateProjectSurfaces(projectId);
    revalidatePath("/runners");
    redirect(withQueryValue(returnTo, "team_notice", `已向 ${targetNodes.length} 台电脑下发 USB/串口扫描`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "下发串口扫描失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

function normalizeRoboticsDebugWindows(value: unknown) {
  return asArray<Record<string, unknown>>(value)
    .map((item) => ({
      resourceId: text(item.resourceId ?? item.resource_id ?? item.interface_id, ""),
      name: text(item.name ?? item.label, ""),
      type: text(item.type ?? item.kind, "serial"),
      baudRate: text(item.baudRate ?? item.baud_rate, "115200"),
      sampleHz: text(item.sampleHz ?? item.sample_hz, "100"),
      channels: text(item.channels, "time,signal.value,status.code,event.count"),
      boundNpc: text(item.boundNpc ?? item.bound_npc ?? item.bound_npc_id, ""),
      createdAt: text(item.createdAt ?? item.created_at, ""),
      updatedAt: text(item.updatedAt ?? item.updated_at, ""),
      updatedBy: text(item.updatedBy ?? item.updated_by, ""),
    }))
    .filter((item) => item.resourceId);
}

export async function 创建机器人调试窗口(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "robotics");
  const resourceId = text(formData.get("resource_id"), "");
  const windowName = text(formData.get("window_name"), "");
  const windowType = text(formData.get("window_type"), "serial");
  const baudRate = text(formData.get("baud_rate"), "115200");
  const sampleHz = text(formData.get("sample_hz"), "100");
  const channels = text(formData.get("channels"), "time,signal.value,status.code,event.count");
  const boundNpc = text(formData.get("bound_npc"), "");

  if (!resourceId) {
    redirect(withQueryValue(returnTo, "team_error", "请先从真实扫描设备里选择要绑定的接口"));
  }

  try {
    const { currentUser, project } = await ensureProjectCollaborationAccess(projectId);
    const actorId = text(currentUser?.id ?? currentUser?.email, "human-chief");
    const collaborationConfig = readProjectCollaborationConfig(project);
    const currentWindows = normalizeRoboticsDebugWindows(collaborationConfig.robotics_debug_windows);
    const timestamp = new Date().toISOString();
    const nextWindow = {
      resourceId,
      name: windowName || `调试窗口 ${currentWindows.length + 1}`,
      type: windowType,
      baudRate,
      sampleHz,
      channels,
      boundNpc,
      createdAt: currentWindows.find((item) => item.resourceId === resourceId)?.createdAt || timestamp,
      updatedAt: timestamp,
      updatedBy: actorId,
    };
    const nextWindows = [
      ...currentWindows.filter((item) => item.resourceId !== resourceId),
      nextWindow,
    ];

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        robotics_debug_windows: nextWindows,
      },
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/robotics`);
    redirect(withQueryValue(returnTo, "windows", resourceId));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "创建调试窗口失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 更新机器人调试窗口(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "robotics");
  const resourceId = text(formData.get("resource_id"), "");
  if (!resourceId) {
    redirect(withQueryValue(returnTo, "team_error", "请选择要更新的调试窗口"));
  }

  try {
    const { currentUser, project } = await ensureProjectCollaborationAccess(projectId);
    const actorId = text(currentUser?.id ?? currentUser?.email, "human-chief");
    const collaborationConfig = readProjectCollaborationConfig(project);
    const currentWindows = normalizeRoboticsDebugWindows(collaborationConfig.robotics_debug_windows);
    const current = currentWindows.find((item) => item.resourceId === resourceId);
    if (!current) {
      redirect(withQueryValue(returnTo, "team_error", "这个调试窗口还没有保存，请先创建窗口"));
    }
    const nextWindow = {
      ...current,
      name: text(formData.get("window_name"), current.name),
      type: text(formData.get("window_type"), current.type),
      baudRate: text(formData.get("baud_rate"), current.baudRate || "115200"),
      sampleHz: text(formData.get("sample_hz"), current.sampleHz || "100"),
      channels: text(formData.get("channels"), current.channels || "time,signal.value,status.code,event.count"),
      boundNpc: text(formData.get("bound_npc"), ""),
      updatedAt: new Date().toISOString(),
      updatedBy: actorId,
    };
    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        robotics_debug_windows: currentWindows.map((item) => item.resourceId === resourceId ? nextWindow : item),
      },
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/robotics`);
    redirect(returnTo);
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "保存调试窗口设置失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 删除机器人调试窗口(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "robotics");
  const resourceId = text(formData.get("resource_id"), "");
  if (!resourceId) {
    redirect(withQueryValue(returnTo, "team_error", "请选择要删除的调试窗口"));
  }
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig = readProjectCollaborationConfig(project);
    const currentWindows = normalizeRoboticsDebugWindows(collaborationConfig.robotics_debug_windows);
    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        robotics_debug_windows: currentWindows.filter((item) => item.resourceId !== resourceId),
      },
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/robotics`);
    redirect(withoutQueryKeys(returnTo, ["windows", "team_notice", "team_error"]));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "删除调试窗口失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 下发串口调试指令(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "device-debug");
  const nodeId = String(formData.get("computer_node_id") ?? "").trim();
  const port = String(formData.get("port") ?? "").trim();
  const baudRate = Number(formData.get("baud_rate") ?? 115200) || 115200;
  const payloadText = String(formData.get("payload") ?? "").trim();
  const payloadFormat = String(formData.get("payload_format") ?? "text-lf").trim() || "text-lf";
  try {
    if (!nodeId) throw new Error("请先选择目标电脑");
    if (!port) throw new Error("请先填写串口号，例如 COM3 或 /dev/ttyUSB0");
    if (!payloadText) throw new Error("请先填写要发送的数据");
    await ensureProjectCollaborationAccess(projectId);
    await postJson(`/api/collaboration/projects/${projectId}/runner-commands`, {
      computer_node_id: nodeId,
      title: `设备调试台 / 写入 ${port}`,
      body: JSON.stringify(
        {
          kind: "serial.write",
          version: "serial-tv.v1",
          port,
          baud_rate: baudRate,
          payload_format: payloadFormat,
          payload: payloadText,
          expected_reply: {
            message_type: "runner_result",
            data_key: "serial_write_result",
          },
        },
        null,
        2,
      ),
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath("/runners");
    redirect(withQueryValue(returnTo, "team_notice", "串口写入命令已下发"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "下发串口写入失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 更新项目版本库配置(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "git");
  try {
    await ensureProjectCollaborationAccess(projectId);
    await patchJson(`/api/projects/${projectId}`, {
      github_url: String(formData.get("github_url") ?? "").trim() || null,
      local_git_url: String(formData.get("local_git_url") ?? "").trim() || null,
      default_branch: String(formData.get("default_branch") ?? "main").trim() || "main",
      develop_branch: String(formData.get("develop_branch") ?? "develop").trim() || "develop",
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", "Git 配置已更新"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "更新 Git 配置失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 保存项目Github账号绑定(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "git");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig = readProjectCollaborationConfig(project);
    const action = text(formData.get("binding_action"), "save").toLowerCase();
    if (action === "clear") {
      delete collaborationConfig.github_account_binding;
      await patchJson(`/api/projects/${projectId}`, {
        collaboration_config: collaborationConfig,
      });
      revalidateProjectSurfaces(projectId);
      redirect(withQueryValue(returnTo, "team_notice", "GitHub 账号绑定已清除"));
    }

    const accountLogin = text(formData.get("account_login"), "");
    const accountType = text(formData.get("account_type"), "user");
    const profileUrl = text(formData.get("profile_url"), "");
    const credentialSource = text(formData.get("credential_source"), "runner_env");
    const credentialRef = text(formData.get("credential_ref"), "");
    const defaultCloneProtocol = text(formData.get("default_clone_protocol"), "https");
    const permissionScopes = parseStringList(formData.get("permission_scopes")) ?? [];
    const notes = text(formData.get("notes"), "");

    if (!accountLogin) {
      throw new Error("请先填写 GitHub 账号或组织名。");
    }
    if (looksLikeRawGithubCredential(credentialRef)) {
      throw new Error("凭据标识不能填写明文 GitHub token。请改填环境变量名，例如 GITHUB_TOKEN，或选择 SSH Agent / GitHub App / OAuth。");
    }
    if (profileUrl) {
      let parsed: URL;
      try {
        parsed = new URL(profileUrl);
      } catch {
        throw new Error("GitHub 主页地址格式不正确。");
      }
      if (!["github.com", "www.github.com"].includes(parsed.hostname.toLowerCase())) {
        throw new Error("GitHub 主页必须是 github.com 地址。");
      }
    }

    collaborationConfig.github_account_binding = {
      account_login: accountLogin,
      account_type: ["user", "org", "bot"].includes(accountType) ? accountType : "user",
      profile_url: profileUrl || `https://github.com/${accountLogin}`,
      credential_source: ["github_app", "oauth", "runner_env", "ssh_agent", "manual_review"].includes(credentialSource)
        ? credentialSource
        : "runner_env",
      credential_ref: credentialRef,
      default_clone_protocol: ["https", "ssh"].includes(defaultCloneProtocol) ? defaultCloneProtocol : "https",
      permission_scopes: permissionScopes,
      notes,
      secret_storage: "not_stored_in_project_config",
      updated_at: new Date().toISOString(),
    };

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: collaborationConfig,
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", `GitHub 账号已绑定：${accountLogin}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "保存 GitHub 账号绑定失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 登记项目Git同步(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "git");
  try {
    const { currentUser, project } = await ensureProjectCollaborationAccess(projectId);
    const provider = String(formData.get("provider") ?? "").trim() || "github";
    const notes = String(formData.get("notes") ?? "").trim();

    await postJson(`/api/git/projects/${projectId}/sync-github`, {
      actor_type: "human",
      actor_id: String(currentUser?.id ?? "").trim() || null,
      provider,
      notes: appendGitCollaborationContextToNotes(project, notes, "从项目页 Git 面板登记同步请求"),
    });
    const preflight = await dispatchProjectGitPreflightToRunners(projectId, project, {
      action: "sync",
      provider,
      notes,
      requestedBy: text(currentUser?.id ?? currentUser?.email, "human-chief"),
    });
    revalidateProjectSurfaces(projectId);
    const preflightNotice = preflight.queued
      ? `；已向 ${preflight.queued} 台已接入电脑下发只读预检`
      : preflight.runnableNodeCount
        ? "；只读预检未能下发，请检查 Runner 收件箱"
        : preflight.onlineNodeCount
          ? "；电脑登记在线但缺少 Runner 绑定，请回电脑接入面板修复"
          : "；暂无在线 Runner，只登记项目活动";
    redirect(withQueryValue(returnTo, "team_notice", `Git 同步请求已登记：${provider}${preflightNotice}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "登记 Git 同步失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 预演项目Git同步(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "git");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const provider = String(formData.get("provider") ?? "").trim() || "github";
    const notes = String(formData.get("notes") ?? "").trim();

    const previewResult = await postJson(`/api/git/projects/${projectId}/sync-preview`, {
      provider,
      notes: notes || null,
    });
    const previewPayload =
      previewResult && typeof previewResult === "object" && previewResult.data
        ? previewResult.data
        : previewResult;
    const withPreview = withQueryValue(returnTo, "git_sync_preview", encodePreviewState(previewPayload));
    redirect(withQueryValue(withPreview, "team_notice", `已生成 Git 同步预演：${provider}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "Git 同步预演失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 登记项目Git回退(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "git");
  try {
    const { currentUser, project } = await ensureProjectCollaborationAccess(projectId);
    const targetRef = String(formData.get("target_ref") ?? "").trim();
    const notes = String(formData.get("notes") ?? "").trim();
    if (!targetRef) {
      throw new Error("请先填写要回退到的 Git 目标，例如 develop 或 HEAD~1");
    }

    await postJson(`/api/git/projects/${projectId}/rollback`, {
      actor_type: "human",
      actor_id: String(currentUser?.id ?? "").trim() || null,
      target_ref: targetRef,
      notes: appendGitCollaborationContextToNotes(project, notes, "从项目页 Git 面板登记回退请求"),
    });
    const preflight = await dispatchProjectGitPreflightToRunners(projectId, project, {
      action: "rollback",
      provider: "github",
      targetRef,
      notes,
      requestedBy: text(currentUser?.id ?? currentUser?.email, "human-chief"),
    });
    const alignment = await notifyGitRollbackAlignmentTargets(projectId, project, {
      targetRef,
      notes,
      requestedBy: text(currentUser?.id ?? currentUser?.email, "human-chief"),
      preflightQueued: preflight.queued,
      preflightRunnableNodeCount: preflight.runnableNodeCount,
      preflightOnlineNodeCount: preflight.onlineNodeCount,
    });
    revalidateProjectSurfaces(projectId);
    const preflightNotice = preflight.queued
      ? `；已向 ${preflight.queued} 台已接入电脑下发只读预检`
      : preflight.runnableNodeCount
        ? "；在线 Runner 下发失败，请检查 Runner 收件箱"
        : preflight.onlineNodeCount
          ? "；电脑登记在线但缺少 Runner 绑定，请回电脑接入面板修复"
          : "；暂无在线 Runner，预检待电脑上线后重试";
    const alignmentNotice = alignment.queued
      ? `；已通知 ${alignment.queued} 个 Boss/工位长 NPC 对齐`
      : alignment.targetCount
        ? "；NPC 对齐消息未能写入，请到工作台手动同步"
        : "；暂无可通知的 Boss/工位长 NPC";
    redirect(withQueryValue(returnTo, "team_notice", `Git 回退请求已登记：${targetRef}${preflightNotice}${alignmentNotice}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "登记 Git 回退失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 预演项目Git回退(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "git");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const targetRef = String(formData.get("target_ref") ?? "").trim();
    const notes = String(formData.get("notes") ?? "").trim();
    if (!targetRef) {
      throw new Error("请先填写要回退到的 Git 目标，例如 develop 或 HEAD~1");
    }

    const previewResult = await postJson(`/api/git/projects/${projectId}/rollback-preview`, {
      target_ref: targetRef,
      notes: notes || null,
    });
    const previewPayload =
      previewResult && typeof previewResult === "object" && previewResult.data
        ? previewResult.data
        : previewResult;
    const withPreview = withQueryValue(returnTo, "git_preview", encodePreviewState(previewPayload));
    redirect(withQueryValue(withPreview, "team_notice", `已生成 Git 回退预演：${targetRef}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "Git 回退预演失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 创建项目Skill(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "skills");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig =
      project?.collaboration_config && typeof project.collaboration_config === "object"
        ? { ...(project.collaboration_config as Record<string, unknown>) }
        : {};
    const skillLibrary = Array.isArray(collaborationConfig.skill_library)
      ? [...(collaborationConfig.skill_library as Record<string, unknown>[])]
      : [];
    const rawId = String(formData.get("skill_id") ?? "").trim().toLowerCase();
    const skillId = rawId.replace(/[^a-z0-9-_]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
    const recommendedFor = parseStringList(formData.get("recommended_for")) ?? [];
    const recommendedPreset = RECOMMENDED_PROJECT_SKILLS[skillId];
    if (!skillId) {
      throw new Error("请先填写 skill 标识");
    }
    if (RESERVED_PLATFORM_SKILL_IDS.includes(skillId)) {
      throw new Error("这是平台默认 skill，不需要重复新增。");
    }
    if (skillLibrary.some((item) => String(item.id ?? "").trim().toLowerCase() === skillId)) {
      throw new Error("这个 skill 标识已经存在");
    }
    const source = text(formData.get("source"), "custom") || "custom";
    const category = text(formData.get("category"), source === "npc-authored" ? "npc-authored" : "custom");
    const repoRelativePath = text(formData.get("repo_relative_path"), "");
    const authorSeatId = text(formData.get("author_seat_id"), "");
    const assignmentSeatId = text(formData.get("assignment_seat_id"), "");
    const createdFromMessageId = text(formData.get("created_from_message_id"), "");
    const closureSource = text(formData.get("closure_source"), "");
    const closureNeedId = text(formData.get("closure_need_id"), "");
    const closureTaskId = text(formData.get("closure_task_id"), "");
    const closureDispatchId = text(formData.get("closure_dispatch_id"), "");
    const draftStatus = text(formData.get("draft_status"), source === "npc-authored" ? "draft" : "");
    const shouldAssignToAuthor = readBooleanFormField(formData, "assign_to_author", false);
    const shouldAssignToSeat = Boolean(assignmentSeatId) || shouldAssignToAuthor;
    const targetSeatId = assignmentSeatId || authorSeatId;

    const nextSkill = {
      id: skillId,
      label: String(formData.get("label") ?? "").trim() || recommendedPreset?.label || skillId,
      note: String(formData.get("note") ?? "").trim() || recommendedPreset?.note || "项目自定义 skill",
      source,
      scope: "role",
      recommended_for: recommendedFor.length ? recommendedFor : (recommendedPreset?.recommendedFor ?? []),
      repo_relative_path: repoRelativePath || (source === "npc-authored" ? `skills/${skillId}/SKILL.md` : undefined),
      metadata: {
        ...(source === "npc-authored"
          ? {
              author_seat_id: authorSeatId || null,
              created_from_message_id: createdFromMessageId || null,
              draft_status: draftStatus || "draft",
              skill_creator_version: "openai-skill-creator",
              template: "SKILL.md + optional agents/openai.yaml + references/scripts/assets",
            }
          : {}),
        ...(closureSource
          ? {
              closure_source: closureSource,
              closure_need_id: closureNeedId || null,
              closure_task_id: closureTaskId || null,
              closure_dispatch_id: closureDispatchId || null,
            }
          : {}),
      },
    };

    await postJson(`/api/knowledge/projects/${projectId}/skills`, {
      skill_id: nextSkill.id,
      label: nextSkill.label,
      source: nextSkill.source,
      category,
      repo_relative_path: nextSkill.repo_relative_path ?? null,
      description: nextSkill.note,
      recommended_for: nextSkill.recommended_for,
      exists_in_repo: source === "npc-authored" ? false : false,
      extra_data: nextSkill.metadata,
    });

    if (shouldAssignToSeat && targetSeatId) {
      await postJson(`/api/knowledge/projects/${projectId}/seat-skill-assignments`, {
        seat_id: targetSeatId,
        skill_id: nextSkill.id,
        assignment_type: source === "npc-authored" ? "npc-authored-draft" : "direct",
        status: source === "npc-authored" ? "draft" : "active",
        notes: source === "npc-authored" ? "NPC 在项目开发中沉淀的可复用 Skill 草稿，确认后可设为 active。" : null,
        extra_data: {
          author_seat_id: authorSeatId || null,
          draft_status: draftStatus || null,
          closure_source: closureSource || null,
          closure_need_id: closureNeedId || null,
          closure_task_id: closureTaskId || null,
          closure_dispatch_id: closureDispatchId || null,
        },
      });
    }

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        skill_library: sortProjectSkillLibrary([...skillLibrary, nextSkill]),
      },
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", closureSource ? `已生成 Skill 草稿：${nextSkill.label}，可继续索引 NPC 沉淀。` : `已新增 Skill：${nextSkill.label}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "新增项目 Skill 失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 删除项目Skill(projectId: string, skillId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "skills");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig =
      project?.collaboration_config && typeof project.collaboration_config === "object"
        ? { ...(project.collaboration_config as Record<string, unknown>) }
        : {};
    const skillLibrary = Array.isArray(collaborationConfig.skill_library)
      ? [...(collaborationConfig.skill_library as Record<string, unknown>[])]
      : [];
    const normalizedId = String(skillId ?? "").trim().toLowerCase();
    const nextSkills = skillLibrary.filter(
      (item) => String(item.id ?? "").trim().toLowerCase() !== normalizedId,
    );
    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        skill_library: sortProjectSkillLibrary(nextSkills),
      },
    });
    if (normalizedId) {
      try {
        await deleteJson(`/api/knowledge/projects/${projectId}/skills/${encodeURIComponent(normalizedId)}`);
      } catch (error) {
        const err = error as (Error & { status?: number; code?: string }) | null;
        if (err?.status !== 404 && err?.code !== "SKILL_NOT_FOUND") throw error;
      }
    }
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", "项目 Skill 已删除"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "删除项目 Skill 失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 保存能力工坊知识库(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "skill-forge");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const title = text(formData.get("title"), "");
    const repoRelativePathValue = repoRelativePath(formData.get("repo_relative_path"));
    const scope = text(formData.get("scope"), "project") || "project";
    const ownerType = text(formData.get("owner_type"), "");
    const ownerId = text(formData.get("owner_id"), "");
    const summary = text(formData.get("summary"), "");
    const tags = parseStringList(formData.get("tags")) ?? [];
    const authorSeatId = text(formData.get("author_seat_id"), "");
    const sourceMessageId = text(formData.get("created_from_message_id"), "");
    const closureSource = text(formData.get("closure_source"), "");
    const closureNeedId = text(formData.get("closure_need_id"), "");
    const closureTaskId = text(formData.get("closure_task_id"), "");
    const closureDispatchId = text(formData.get("closure_dispatch_id"), "");
    const savedAt = new Date().toISOString();
    if (!title) throw new Error("请填写知识库标题");
    if (!repoRelativePathValue) throw new Error("请填写仓库相对路径");

    await postJson(`/api/knowledge/projects/${projectId}/documents`, {
      title,
      repo_relative_path: repoRelativePathValue,
      scope,
      owner_type: ownerType || null,
      owner_id: ownerId || null,
      exists_in_repo: readBooleanFormField(formData, "exists_in_repo", false),
      summary,
      tags,
      extra_data: {
        author_seat_id: authorSeatId || null,
        created_from_message_id: sourceMessageId || null,
        source: authorSeatId ? "npc-authored" : "human-authored",
        updated_from: "skill-forge",
        updated_at: savedAt,
        closure_source: closureSource || null,
        closure_need_id: closureNeedId || null,
        closure_task_id: closureTaskId || null,
        closure_dispatch_id: closureDispatchId || null,
      },
    });

    if (ownerType === "seat" && ownerId) {
      const seatsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
      const seats = asArray<Record<string, unknown>>(seatsResult?.data ?? seatsResult);
      const seat =
        seats.find((item) =>
          isNpcSeatRecord(item) &&
          (
            workstationLookupKeys(item).some((candidate) => candidate === ownerId) ||
            seatIdentityValues(item).some((candidate) => candidate === ownerId)
          ),
        ) ?? null;
      if (seat) {
        const seatRecordId = text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, ownerId);
        const seatName = text(seat.name ?? seat.workstation_name, "该 NPC");
        const metadata = readRecord(seat.metadata ?? seat.extra_data ?? seat.extraData);
        const existingPaths = uniqueStrings([
          ...normalizeUnknownStringList(seat.knowledge_paths),
          ...normalizeUnknownStringList(metadata.knowledge_paths),
          repoRelativePathValue,
        ]);
        const storedKnowledge = readRecord(metadata.npc_knowledge);
        await patchJson(
          `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(seatRecordId)}`,
          {
            metadata: mergeSeatMetadata(metadata, {
              knowledge_paths: existingPaths,
              npc_knowledge: {
                ...storedKnowledge,
                summary: summary || text(storedKnowledge.summary, `已保存知识库：${title}`),
                handoff_path: text(storedKnowledge.handoff_path, repoRelativePathValue),
                tags: uniqueStrings([
                  ...normalizeUnknownStringList(storedKnowledge.tags),
                  ...tags,
                  "skill-forge",
                ]),
              },
              knowledge_forge_snapshot: {
                source: "能力工坊",
                generated_at: savedAt,
                changed_path: repoRelativePathValue,
                changed_title: title,
                affected_seat_name: seatName,
                effect: "下一轮派单 / 刷新后的上岗包会读取",
                summary: "能力工坊已更新该 NPC 的知识库配置源；后续新派单和刷新后的上岗包会读取这份知识。",
              },
            }),
          },
        );
      }
    }
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", closureSource ? `已保存协作知识：${title}，下一步可索引 NPC 沉淀。` : `已保存知识库：${title}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "保存知识库失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 删除能力工坊知识库(projectId: string, documentId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "skill-forge");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const normalizedId = text(documentId || formData.get("document_id"), "");
    if (!normalizedId) throw new Error("请先选择知识库");
    const docsResult = await getJson(`/api/knowledge/projects/${projectId}/documents`);
    const documents = asArray<Record<string, unknown>>(docsResult?.data ?? docsResult);
    const targetDoc =
      documents.find((item) =>
        [
          item.id,
          item.repo_relative_path,
          item.repoRelativePath,
          item.path,
          item.title,
        ].some((candidate) => text(candidate, "") === normalizedId),
      ) ?? null;
    const targetPath = repoRelativePath(targetDoc?.repo_relative_path ?? targetDoc?.repoRelativePath ?? targetDoc?.path);
    const targetTitle = text(targetDoc?.title ?? targetDoc?.name, "");
    const ownerType = text(targetDoc?.owner_type ?? targetDoc?.ownerType ?? formData.get("owner_type"), "");
    const ownerId = text(targetDoc?.owner_id ?? targetDoc?.ownerId ?? formData.get("owner_id"), "");
    await deleteJson(`/api/knowledge/projects/${projectId}/documents/${encodeRepoPathForRoute(normalizedId)}`);
    if (ownerType === "seat" && ownerId && targetPath) {
      const seatsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
      const seats = asArray<Record<string, unknown>>(seatsResult?.data ?? seatsResult);
      const seat =
        seats.find((item) =>
          isNpcSeatRecord(item) &&
          (
            workstationLookupKeys(item).some((candidate) => candidate === ownerId) ||
            seatIdentityValues(item).some((candidate) => candidate === ownerId)
          ),
        ) ?? null;
      if (seat) {
        const seatRecordId = text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, ownerId);
        const metadata = readRecord(seat.metadata ?? seat.extra_data ?? seat.extraData);
        const nextPaths = uniqueStrings([
          ...normalizeUnknownStringList(seat.knowledge_paths),
          ...normalizeUnknownStringList(metadata.knowledge_paths),
        ]).filter((item) => item !== targetPath);
        const snapshot = readRecord(metadata.knowledge_forge_snapshot);
        const snapshotMatches =
          text(snapshot.changed_path, "") === targetPath ||
          (targetTitle && text(snapshot.changed_title, "") === targetTitle);
        const storedKnowledge = readRecord(metadata.npc_knowledge);
        const nextKnowledge =
          text(storedKnowledge.handoff_path, "") === targetPath
            ? {
                ...storedKnowledge,
                summary: "",
                handoff_path: "",
                tags: normalizeUnknownStringList(storedKnowledge.tags).filter((item) => item !== "skill-forge"),
              }
            : storedKnowledge;
        await patchJson(
          `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(seatRecordId)}`,
          {
            metadata: mergeSeatMetadata(metadata, {
              knowledge_paths: nextPaths,
              npc_knowledge: nextKnowledge,
              ...(snapshotMatches ? { knowledge_forge_snapshot: null } : {}),
            }),
          },
        );
      }
    }
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", "知识库条目已删除"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "删除知识库失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

async function safeRepoFileCandidates(relativeDir: string, options: { maxFiles?: number; fileNames?: string[]; extensions?: string[] } = {}) {
  const relative = repoRelativePath(relativeDir).replace(/\/+$/, "");
  if (!relative || relative.includes("..") || /^[a-zA-Z]:\//.test(relative)) return [];
  const root = workspaceRoot();
  const dirPath = path.resolve(root, relative);
  const normalizedRoot = root.replace(/\\/g, "/").toLowerCase();
  const normalizedDir = dirPath.replace(/\\/g, "/").toLowerCase();
  if (!normalizedDir.startsWith(normalizedRoot)) return [];
  const maxFiles = Math.max(1, Math.min(options.maxFiles ?? 12, 30));
  const fileNames = new Set((options.fileNames ?? []).map((item) => item.toLowerCase()));
  const extensions = new Set((options.extensions ?? [".md", ".mdx"]).map((item) => item.toLowerCase()));
  const found: Array<{ relativePath: string; name: string; content: string }> = [];

  async function walk(current: string) {
    if (found.length >= maxFiles) return;
    let entries: Dirent[];
    try {
      entries = await fs.readdir(current, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (found.length >= maxFiles) break;
      if (entry.name.startsWith(".")) continue;
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
        continue;
      }
      if (!entry.isFile()) continue;
      const lower = entry.name.toLowerCase();
      if (fileNames.size ? !fileNames.has(lower) : !extensions.has(path.extname(lower))) continue;
      const relativePath = path.relative(root, fullPath).replace(/\\/g, "/");
      let content = "";
      try {
        content = await fs.readFile(fullPath, "utf8");
      } catch {}
      found.push({ relativePath, name: entry.name, content });
    }
  }

  await walk(dirPath);
  return found;
}

function markdownTitle(content: string, fallback: string) {
  const heading = content.split(/\r?\n/).find((line) => /^#\s+/.test(line.trim()));
  return text(heading?.replace(/^#\s+/, ""), fallback);
}

function markdownSummary(content: string, fallback: string) {
  const line = content
    .split(/\r?\n/)
    .map((item) => item.trim())
    .find((item) => item && !item.startsWith("#") && !item.startsWith("---"));
  return text(line, fallback).slice(0, 260);
}

function markdownBullets(content: string, fallback: string[] = []) {
  const bullets = content
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter((item) => /^[-*]\s+/.test(item))
    .map((item) => item.replace(/^[-*]\s+/, "").trim())
    .filter(Boolean)
    .slice(0, 8);
  return bullets.length ? bullets : fallback;
}

function markdownField(content: string, names: string[], fallback = "") {
  const normalizedNames = names.map((item) => item.toLowerCase());
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    const match = line.match(/^[-*]?\s*([^:：]+)\s*[:：]\s*(.+)$/);
    if (!match) continue;
    const key = match[1].trim().toLowerCase();
    if (normalizedNames.some((name) => key === name || key.includes(name))) {
      return text(match[2], fallback);
    }
  }
  return fallback;
}

function fileAlreadyIndexed(items: Record<string, unknown>[], repoPath: string) {
  const normalized = repoRelativePath(repoPath).toLowerCase();
  return items.some((item) => {
    const extra = readRecord(item.extra_data ?? item.extraData ?? item.metadata);
    return [
      item.repo_relative_path,
      item.repoRelativePath,
      item.path,
      item.related_issue,
      item.relatedIssue,
      extra.repo_relative_path,
      extra.repoRelativePath,
      extra.source_file,
      extra.sourceFile,
      ...normalizeUnknownStringList(item.related_files),
      ...normalizeUnknownStringList(item.relatedFiles),
      ...normalizeUnknownStringList(extra.related_files),
      ...normalizeUnknownStringList(extra.relatedFiles),
    ].some((candidate) => repoRelativePath(candidate).toLowerCase() === normalized);
  });
}

function depositAuditItem(kind: string, scanned: number, added: number, destination = "") {
  return {
    kind,
    scanned,
    added,
    skipped: Math.max(0, scanned - added),
    destination,
  };
}

export async function 索引Npc沉淀(projectId: string, seatId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "skill-forge");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const normalizedSeatId = text(seatId || formData.get("seat_id"), "");
    if (!normalizedSeatId) throw new Error("请先选择 NPC");

    const seatsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const seats = asArray<Record<string, unknown>>(seatsResult?.data ?? seatsResult);
    const seat = seats.find((item) =>
      isNpcSeatRecord(item) &&
      (
        workstationLookupKeys(item).some((candidate) => candidate === normalizedSeatId) ||
        seatIdentityValues(item).some((candidate) => candidate === normalizedSeatId)
      ),
    ) ?? null;
    if (!seat) throw new Error("没有找到这个 NPC，不能把线程或电脑当作 NPC 索引");

    const metadata = readRecord(seat.metadata ?? seat.extra_data ?? seat.extraData);
    const storedNpcKnowledge = readRecord(metadata.npc_knowledge);
    const seatNameForPaths = text(seat.name ?? seat.workstation_name, "NPC");
    const depositSlug = text(storedNpcKnowledge.slug ?? metadata.npc_identity_key, "").replace(/^npc:/, "") || slugifyAscii(seatNameForPaths, "npc");
    const npcKnowledge = buildNpcKnowledgeProfile({
      seatId: text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, normalizedSeatId),
      name: seatNameForPaths,
      responsibility: text(seat.responsibility ?? metadata.responsibility, ""),
      knowledgeSlug: depositSlug,
      knowledgeSummary: text(storedNpcKnowledge.summary, "") || null,
      knowledgeHandoffPath: text(storedNpcKnowledge.handoff_path, "") || null,
      knowledgeDepositPath: text(storedNpcKnowledge.knowledge_deposit_path, "") || null,
      skillDepositPath: text(storedNpcKnowledge.skill_deposit_path, "") || null,
      needDepositPath: text(storedNpcKnowledge.need_deposit_path, "") || null,
      taskDepositPath: text(storedNpcKnowledge.task_deposit_path, "") || null,
      knowledgeTags: normalizeUnknownStringList(storedNpcKnowledge.tags),
    });
    const seatRecordId = text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, normalizedSeatId);
    const seatName = text(seat.name ?? seat.workstation_name, "该 NPC");
    const closureSource = text(formData.get("closure_source"), "");
    const closureNeedId = text(formData.get("closure_need_id"), "");
    const closureTaskId = text(formData.get("closure_task_id"), "");
    const closureDispatchId = text(formData.get("closure_dispatch_id"), "");
    const closureExtraData = closureSource === "company_collaboration" && (closureNeedId || closureTaskId || closureDispatchId)
      ? {
          closure_source: closureSource,
          closure_need_id: closureNeedId || null,
          closure_task_id: closureTaskId || null,
          closure_dispatch_id: closureDispatchId || null,
        }
      : {};

    const knowledgeFiles = await safeRepoFileCandidates(npcKnowledge.knowledge_deposit_path, { maxFiles: 12, extensions: [".md", ".mdx"] });
    const skillFiles = await safeRepoFileCandidates(npcKnowledge.skill_deposit_path, { maxFiles: 12, fileNames: ["skill.md"] });
    const needFiles = await safeRepoFileCandidates(npcKnowledge.need_deposit_path, { maxFiles: 12, extensions: [".md", ".mdx", ".json"] });
    const taskFiles = await safeRepoFileCandidates(npcKnowledge.task_deposit_path, { maxFiles: 12, extensions: [".md", ".mdx", ".json"] });
    const [documentsResult, skillsResult, requirementsResult, tasksResult] = await Promise.all([
      getJson(`/api/knowledge/projects/${projectId}/documents`),
      getJson(`/api/knowledge/projects/${projectId}/skills`),
      getJson(`/api/requirements?project_id=${encodeURIComponent(projectId)}`),
      getJson(`/api/tasks?project_id=${encodeURIComponent(projectId)}&page_size=100`),
    ]);
    const existingDocuments = asArray<Record<string, unknown>>(documentsResult?.data ?? documentsResult);
    const existingSkills = asArray<Record<string, unknown>>(skillsResult?.data ?? skillsResult);
    const existingRequirements = asArray<Record<string, unknown>>(requirementsResult?.data ?? requirementsResult);
    const existingTasks = asArray<Record<string, unknown>>(tasksResult?.data ?? tasksResult);
    let knowledgeCount = 0;
    let skillCount = 0;
    let needCount = 0;
    let taskCount = 0;

    for (const file of knowledgeFiles) {
      if (fileAlreadyIndexed(existingDocuments, file.relativePath)) continue;
      await postJson(`/api/knowledge/projects/${projectId}/documents`, {
        title: markdownTitle(file.content, `${seatName} 沉淀知识`),
        repo_relative_path: file.relativePath,
        scope: "npc",
        owner_type: "seat",
        owner_id: seatRecordId,
        exists_in_repo: true,
        summary: markdownSummary(file.content, "NPC 从工作中沉淀的知识条目。"),
        tags: uniqueStrings(["npc-authored", npcKnowledge.slug, ...npcKnowledge.tags]),
        extra_data: {
          author_seat_id: seatRecordId,
          source: "npc-authored",
          indexed_from: "npc-deposit-path",
          indexed_at: new Date().toISOString(),
          ...closureExtraData,
        },
      });
      knowledgeCount += 1;
    }

    for (const file of skillFiles) {
      const skillId = slugifyAscii(`${npcKnowledge.slug}-${path.basename(path.dirname(file.relativePath))}`, `skill-${skillCount + 1}`);
      if (
        fileAlreadyIndexed(existingSkills, file.relativePath) ||
        existingSkills.some((skill) => text(skill.skill_id ?? skill.skillId ?? skill.id, "").toLowerCase() === skillId)
      ) {
        continue;
      }
      await postJson(`/api/knowledge/projects/${projectId}/skills`, {
        skill_id: skillId,
        label: markdownTitle(file.content, `${seatName} 自造 Skill`),
        source: "npc-authored",
        category: "npc-authored",
        repo_relative_path: file.relativePath,
        description: markdownSummary(file.content, "NPC 从工作中沉淀的可复用 Skill。"),
        recommended_for: [seatName],
        exists_in_repo: true,
        extra_data: {
          author_seat_id: seatRecordId,
          draft_status: "draft",
          source: "npc-authored",
          indexed_from: "npc-deposit-path",
          indexed_at: new Date().toISOString(),
          ...closureExtraData,
        },
      });
      await postJson(`/api/knowledge/projects/${projectId}/seat-skill-assignments`, {
        seat_id: seatRecordId,
        skill_id: skillId,
        assignment_type: "npc-authored-draft",
        status: "draft",
        notes: "从该 NPC 默认 Skill 写入目录索引，确认后可设为 active。",
        extra_data: {
          author_seat_id: seatRecordId,
          indexed_from: "npc-deposit-path",
          ...closureExtraData,
        },
      });
      skillCount += 1;
    }

    for (const file of needFiles) {
      if (fileAlreadyIndexed(existingRequirements, file.relativePath)) continue;
      const title = markdownTitle(file.content, `${seatName} 提出的需求`);
      const requiredCapability = markdownField(file.content, ["required capability", "required_capability", "需要能力", "能力"], "待平台路由判断");
      const expectedOutput = markdownField(file.content, ["expected output", "expected_output", "期望产出", "输出"], markdownSummary(file.content, "等待补齐期望产出。"));
      const riskLevel = markdownField(file.content, ["risk", "risk_level", "风险"], "low").toLowerCase();
      const priority = markdownField(file.content, ["priority", "优先级"], "P2").toUpperCase();
      const contextSummary = [
        markdownField(file.content, ["why", "why_needed", "为什么"], markdownSummary(file.content, "NPC 从默认需求目录提交的需求。")),
        "",
        `需要能力：${requiredCapability}`,
        `风险级别：${["low", "medium", "high", "critical"].includes(riskLevel) ? riskLevel : "low"}`,
        `期望产出：${expectedOutput}`,
        `证据路径：${file.relativePath}`,
        "验收标准：",
        ...markdownBullets(file.content, [expectedOutput]).map((item) => `- ${item}`),
      ].join("\n").trim();
      await postJson(`/api/requirements`, {
        project_id: projectId,
        title,
        requirement_type: "npc_structured_need",
        module: markdownField(file.content, ["module", "模块"], "") || null,
        priority: /^P[0-3]$/.test(priority) ? priority : "P2",
        status: ["high", "critical"].includes(riskLevel) ? "needs_human_review" : "ready_to_route",
        from_agent: seatRecordId,
        to_agent: markdownField(file.content, ["suggested assignee", "suggested_assignee", "建议承接"], "") || null,
        context_summary: contextSummary,
        expected_output: expectedOutput,
        related_files: [file.relativePath],
        opening_message: contextSummary,
        target_seat_id: markdownField(file.content, ["suggested assignee", "suggested_assignee", "建议承接"], "") || null,
        trigger_kind: "manual",
      });
      needCount += 1;
    }

    for (const file of taskFiles) {
      if (fileAlreadyIndexed(existingTasks, file.relativePath)) continue;
      const title = markdownTitle(file.content, `${seatName} 任务回执`);
      const status = markdownField(file.content, ["status", "状态"], "done").toLowerCase();
      await postJson(`/api/tasks`, {
        project_id: projectId,
        title,
        description: [
          markdownSummary(file.content, "NPC 从默认任务回执目录提交的回执。"),
          "",
          `证据路径：${file.relativePath}`,
        ].join("\n").trim(),
        module: markdownField(file.content, ["module", "模块"], "") || "npc-receipt",
        priority: markdownField(file.content, ["priority", "优先级"], "P2").toUpperCase(),
        status: ["draft", "ready", "running", "reviewing", "blocked", "done", "failed", "cancelled"].includes(status) ? status : "done",
        related_issue: file.relativePath,
        assignee_agent_id: text(seat.agent_id, seatRecordId),
        acceptance_criteria: markdownBullets(file.content, ["回执必须引用证据路径和验证结果。"]),
      });
      taskCount += 1;
    }

    const indexedAt = new Date().toISOString();
    const auditItems = [
      depositAuditItem("知识", knowledgeFiles.length, knowledgeCount, "已进入该 NPC 知识库配置"),
      depositAuditItem("Skill 草稿", skillFiles.length, skillCount, "已进入能力草稿区，确认后才会影响上岗包"),
      depositAuditItem("需求", needFiles.length, needCount, "已进入当前需求队列，等待路由或人工处理"),
      depositAuditItem("任务回执", taskFiles.length, taskCount, "已进入任务回执队列，可用于验收和归档"),
    ];
    const scannedTotal = auditItems.reduce((sum, item) => sum + item.scanned, 0);
    const addedTotal = auditItems.reduce((sum, item) => sum + item.added, 0);
    const skippedTotal = auditItems.reduce((sum, item) => sum + item.skipped, 0);
    await patchJson(
      `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(seatRecordId)}`,
      {
        metadata: mergeSeatMetadata(metadata, {
          npc_deposit_index_snapshot: {
            generated_at: indexedAt,
            scanned_total: scannedTotal,
            added_total: addedTotal,
            skipped_total: skippedTotal,
            items: auditItems,
            summary: scannedTotal
              ? `扫描 ${scannedTotal} 个文件，新增 ${addedTotal} 条，跳过 ${skippedTotal} 条已入库记录。`
              : "默认写入路径暂未发现可索引文件。",
          },
        }),
      },
    );

    revalidateProjectSurfaces(projectId);
    let nextPath = withQueryValue(
      returnTo,
      "team_notice",
      scannedTotal
        ? `已扫描 ${scannedTotal} 个沉淀文件：新增 ${addedTotal} 条，跳过 ${skippedTotal} 条已入库记录`
        : "默认写入路径暂未发现可索引文件",
    );
    nextPath = withQueryValue(nextPath, "seat", seatRecordId);
    redirect(nextPath);
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "索引 NPC 沉淀失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 启用Npc自造Skill(projectId: string, skillId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "skills");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig =
      project?.collaboration_config && typeof project.collaboration_config === "object"
        ? { ...(project.collaboration_config as Record<string, unknown>) }
        : {};
    const skillLibrary = Array.isArray(collaborationConfig.skill_library)
      ? [...(collaborationConfig.skill_library as Record<string, unknown>[])]
      : [];
    const normalizedId = text(skillId, "").toLowerCase();
    if (!normalizedId) {
      throw new Error("缺少 Skill 标识");
    }
    const existing = skillLibrary.find((item) => text(item.id ?? item.skill_id, "").toLowerCase() === normalizedId);
    if (!existing) {
      throw new Error("没有在项目 Skill 仓库里找到这个草稿");
    }
    const extra = readRecord(existing.metadata ?? existing.extra_data ?? existing.extraData);
    const activatedAt = new Date().toISOString();
    const skillLabel = text(existing.label ?? existing.name, normalizedId);
    const nextSkill = {
      ...existing,
      status: "active",
      metadata: {
        ...extra,
        draft_status: "ready",
        activated_at: activatedAt,
      },
    };

    await postJson(`/api/knowledge/projects/${projectId}/skills`, {
      skill_id: text(existing.id ?? existing.skill_id, normalizedId),
      label: skillLabel,
      source: text(existing.source, "npc-authored"),
      category: text(existing.category, "npc-authored"),
      repo_relative_path: text(existing.repo_relative_path ?? extra.repo_relative_path, "") || `skills/${normalizedId}/SKILL.md`,
      description: text(existing.note ?? existing.description, ""),
      recommended_for: normalizeUnknownStringList(existing.recommended_for),
      exists_in_repo: existing.exists_in_repo === true,
      extra_data: nextSkill.metadata,
    });

    const authorSeatId = text(extra.author_seat_id, "");
    let activatedSeatId = "";
    if (authorSeatId) {
      await postJson(`/api/knowledge/projects/${projectId}/seat-skill-assignments`, {
        seat_id: authorSeatId,
        skill_id: normalizedId,
        assignment_type: "direct",
        status: "active",
        notes: "NPC 自造 Skill 已确认可用，后续派单可作为长期角色能力复用。",
        extra_data: {
          author_seat_id: authorSeatId,
          draft_status: "ready",
          activated_at: nextSkill.metadata.activated_at,
        },
      });

      const seatsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
      const seats = asArray<Record<string, unknown>>(seatsResult?.data ?? seatsResult);
      const seat =
        seats.find((item) =>
          isNpcSeatRecord(item) &&
          (
            workstationLookupKeys(item).some((candidate) => candidate === authorSeatId) ||
            seatIdentityValues(item).some((candidate) => candidate === authorSeatId)
          ),
        ) ?? null;
      if (seat) {
        const seatRecordId = text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, authorSeatId);
        const seatName = text(seat.name ?? seat.workstation_name, "该 NPC");
        const metadata = readRecord(seat.metadata ?? seat.extra_data ?? seat.extraData);
        const existingLoadout = mergePlatformSkillLoadout(
          seat.skill_loadout,
          seat.skillLoadout,
          metadata.additional_skill_ids,
          metadata.skill_loadout,
          normalizedId,
        );
        const { roleSkillIds } = splitPlatformSkillLoadout(existingLoadout, skillLibrary);
        await patchJson(
          `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(seatRecordId)}`,
          {
            metadata: mergeSeatMetadata(metadata, {
              additional_skill_ids: roleSkillIds,
              skill_loadout: existingLoadout,
              skill_forge_snapshot: {
                source: "能力工坊",
                generated_at: activatedAt,
                changed_skill_id: normalizedId,
                changed_skill_label: skillLabel,
                affected_seat_name: seatName,
                effect: "下一轮派单 / 刷新后的上岗包会读取",
                summary: "NPC 自造 Skill 已启用并进入该 NPC 的长期能力配置；后续新派单和刷新后的上岗包会读取这份配置。",
              },
            }),
          },
        );
        activatedSeatId = seatRecordId;
      }
    }

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        skill_library: sortProjectSkillLibrary(
          skillLibrary.map((item) => (text(item.id ?? item.skill_id, "").toLowerCase() === normalizedId ? nextSkill : item)),
        ),
      },
    });
    revalidateProjectSurfaces(projectId);
    let nextPath = withQueryValue(returnTo, "team_notice", `已启用 NPC 自造 Skill：${skillLabel}`);
    if (activatedSeatId) nextPath = withQueryValue(nextPath, "seat", activatedSeatId);
    redirect(nextPath);
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "启用 NPC 自造 Skill 失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 添加Skill到Npc(projectId: string, seatId: string, skillId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "skill-forge");
  let reviewContext: {
    senderId: string | null;
    seatName: string;
    skillLabel: string;
    seatRecordId: string;
    normalizedSkillId: string;
  } | null = null;
  try {
    const { project, currentUser } = await ensureProjectCollaborationAccess(projectId);
    const senderId = normalizeMessageFormValue(currentUser?.id) ?? normalizeMessageFormValue(currentUser?.email);
    const normalizedSeatId = text(seatId || formData.get("seat_id"), "");
    const normalizedSkillId = text(skillId || formData.get("skill_id"), "").toLowerCase();
    if (!normalizedSeatId) {
      throw new Error("请先选择 NPC");
    }
    if (!normalizedSkillId) {
      throw new Error("请先选择 Skill");
    }

    const skillsResult = await getJson(`/api/knowledge/projects/${projectId}/skills`);
    const projectSkills = asArray<Record<string, unknown>>(skillsResult?.data ?? skillsResult);
    const collaborationConfig = readProjectCollaborationConfig(project);
    const skillLibrary = asArray<Record<string, unknown>>(collaborationConfig.skill_library);
    const targetSkill =
      projectSkills.find((item) => text(item.skill_id ?? item.id, "").toLowerCase() === normalizedSkillId) ??
      skillLibrary.find((item) => text(item.id ?? item.skill_id, "").toLowerCase() === normalizedSkillId) ??
      DEFAULT_PLATFORM_SKILL_LIBRARY.find((item) => text(item.id, "").toLowerCase() === normalizedSkillId) ??
      null;
    if (!targetSkill) {
      throw new Error("项目 Skill 仓库里没有找到这个 Skill");
    }
    const targetSkillRecord = targetSkill as Record<string, unknown>;
    const skillLabel = text(targetSkillRecord.label ?? targetSkillRecord.name ?? targetSkillRecord.skill_id, normalizedSkillId);

    const seatsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const seats = asArray<Record<string, unknown>>(seatsResult?.data ?? seatsResult);
    const seat =
      seats.find((item) =>
        isNpcSeatRecord(item) &&
        (
          workstationLookupKeys(item).some((candidate) => candidate === normalizedSeatId) ||
          seatIdentityValues(item).some((candidate) => candidate === normalizedSeatId)
        ),
      ) ?? null;
    if (!seat) {
      throw new Error("没有找到这个 NPC，不能把能力绑定到线程或电脑记录");
    }

    const seatRecordId = text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, normalizedSeatId);
    const seatName = text(seat.name ?? seat.workstation_name, "该 NPC");
    reviewContext = {
      senderId,
      seatName,
      skillLabel,
      seatRecordId,
      normalizedSkillId,
    };

    if (!projectSkills.some((item) => text(item.skill_id ?? item.id, "").toLowerCase() === normalizedSkillId)) {
      await postJson(`/api/knowledge/projects/${projectId}/skills`, {
        skill_id: normalizedSkillId,
        label: text(targetSkillRecord.label ?? targetSkillRecord.name ?? targetSkillRecord.title, normalizedSkillId),
        source: text(targetSkillRecord.source, "project-library"),
        category: text(targetSkillRecord.category, "custom"),
        repo_relative_path: text(targetSkillRecord.repo_relative_path ?? targetSkillRecord.doc_path, "") || null,
        description: text(targetSkillRecord.description ?? targetSkillRecord.note ?? targetSkillRecord.summary, ""),
        recommended_for: normalizeUnknownStringList(targetSkillRecord.recommended_for),
        exists_in_repo: targetSkillRecord.exists_in_repo === true,
        extra_data: readRecord(targetSkillRecord.metadata ?? targetSkillRecord.extra_data ?? targetSkillRecord.extraData),
      });
    }

    await postJson(`/api/knowledge/projects/${projectId}/seat-skill-assignments`, {
      seat_id: normalizedSeatId,
      skill_id: normalizedSkillId,
      assignment_type: "direct",
      status: "active",
      notes: "由能力工坊添加到该 NPC 的长期能力配置。",
      extra_data: {
        configured_from: "skill-forge",
        configured_at: new Date().toISOString(),
      },
    });

    const metadata = readRecord(seat.metadata ?? seat.extra_data ?? seat.extraData);
    const existingLoadout = mergePlatformSkillLoadout(
      seat.skill_loadout,
      seat.skillLoadout,
      metadata.additional_skill_ids,
      metadata.skill_loadout,
      normalizedSkillId,
    );
    const { roleSkillIds } = splitPlatformSkillLoadout(existingLoadout, skillLibrary);
    const snapshot = {
      source: "能力工坊",
      generated_at: new Date().toISOString(),
      changed_skill_id: normalizedSkillId,
      changed_skill_label: text(targetSkillRecord.label ?? targetSkillRecord.name ?? targetSkillRecord.skill_id, normalizedSkillId),
      summary: "能力工坊已更新该 NPC 的 Skill 配置源；后续新派单和刷新后的上岗包会读取这份配置。",
    };

    await patchJson(
      `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(seatRecordId)}`,
      {
        metadata: mergeSeatMetadata(metadata, {
          additional_skill_ids: roleSkillIds,
          skill_loadout: existingLoadout,
          skill_forge_snapshot: snapshot,
        }),
      },
    );

    revalidateProjectSurfaces(projectId);
    let nextPath = withQueryValue(
      returnTo,
      "team_notice",
      `已把 ${skillLabel} 添加到 ${seatName} 的配置源`,
    );
    nextPath = withQueryValue(nextPath, "seat", seatRecordId);
    redirect(nextPath);
  } catch (error) {
    rethrowRedirectError(error);
    if (reviewContext && isHumanApprovalError(error)) {
      try {
        await createSkillForgeHumanReviewRequest({
          projectId,
          senderId: reviewContext.senderId,
          title: `给 ${reviewContext.seatName} 添加能力`,
          targetLabel: reviewContext.seatName,
          actionSummary: `添加能力：${reviewContext.skillLabel}`,
          reason: "该能力配置会影响 NPC 上岗包，需要项目负责人或人工确认。",
          metadata: {
            action: "assign_skill_to_seat",
            seat_id: reviewContext.seatRecordId,
            skill_id: reviewContext.normalizedSkillId,
            skill_label: reviewContext.skillLabel,
          },
        });
        revalidateProjectSurfaces(projectId);
        let nextPath = withQueryValue(returnTo, "team_notice", "已生成能力配置待确认请求，请到公司层决策带处理。");
        nextPath = withQueryValue(nextPath, "seat", reviewContext.seatRecordId);
        redirect(nextPath);
      } catch (reviewError) {
        rethrowRedirectError(reviewError);
      }
    }
    const message = error instanceof Error ? error.message : "添加 Skill 到 NPC 失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 绑定知识库到Npc(projectId: string, seatId: string, documentId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "skill-forge");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const normalizedSeatId = text(seatId || formData.get("seat_id"), "");
    const normalizedDocumentId = text(documentId || formData.get("document_id"), "");
    if (!normalizedSeatId) {
      throw new Error("请先选择 NPC");
    }
    if (!normalizedDocumentId) {
      throw new Error("请先选择知识库");
    }

    const [docsResult, seatsResult] = await Promise.all([
      getJson(`/api/knowledge/projects/${projectId}/documents`),
      getJson(`/api/collaboration/projects/${projectId}/thread-workstations`),
    ]);
    const documents = asArray<Record<string, unknown>>(docsResult?.data ?? docsResult);
    const targetDoc =
      documents.find((item) =>
        [
          item.id,
          item.repo_relative_path,
          item.repoRelativePath,
          item.path,
          item.title,
        ].some((candidate) => text(candidate, "") === normalizedDocumentId),
      ) ?? null;
    if (!targetDoc) {
      throw new Error("没有找到这份知识库");
    }
    const repoPath = repoRelativePath(targetDoc.repo_relative_path ?? targetDoc.repoRelativePath ?? targetDoc.path);
    if (!repoPath) {
      throw new Error("这份知识库缺少 GitHub 相对路径");
    }

    const seats = asArray<Record<string, unknown>>(seatsResult?.data ?? seatsResult);
    const seat =
      seats.find((item) =>
        isNpcSeatRecord(item) &&
        (
          workstationLookupKeys(item).some((candidate) => candidate === normalizedSeatId) ||
          seatIdentityValues(item).some((candidate) => candidate === normalizedSeatId)
        ),
      ) ?? null;
    if (!seat) {
      throw new Error("没有找到这个 NPC，不能把知识库绑定到线程或电脑记录");
    }

    const seatRecordId = text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, normalizedSeatId);
    const seatName = text(seat.name ?? seat.workstation_name, "该 NPC");
    const metadata = readRecord(seat.metadata ?? seat.extra_data ?? seat.extraData);
    const existingPaths = uniqueStrings([
      ...normalizeUnknownStringList(seat.knowledge_paths),
      ...normalizeUnknownStringList(metadata.knowledge_paths),
      repoPath,
    ]);
    const storedKnowledge = readRecord(metadata.npc_knowledge);
    const npcKnowledge = {
      ...storedKnowledge,
      summary: text(targetDoc.summary ?? targetDoc.description ?? storedKnowledge.summary, `已绑定知识库：${text(targetDoc.title, repoPath)}`),
      handoff_path: text(storedKnowledge.handoff_path, repoPath),
      tags: uniqueStrings([
        ...normalizeUnknownStringList(storedKnowledge.tags),
        ...normalizeUnknownStringList(targetDoc.tags),
        "skill-forge",
      ]),
    };

    await patchJson(
      `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(seatRecordId)}`,
      {
        metadata: mergeSeatMetadata(metadata, {
          knowledge_paths: existingPaths,
          npc_knowledge: npcKnowledge,
          knowledge_forge_snapshot: {
            source: "能力工坊",
            generated_at: new Date().toISOString(),
            changed_path: repoPath,
            changed_title: text(targetDoc.title ?? targetDoc.name, repoPath),
            affected_seat_name: seatName,
            effect: "下一轮派单 / 刷新后的上岗包会读取",
            summary: "能力工坊已更新该 NPC 的知识库配置源；后续新派单和刷新后的上岗包会读取这份知识。",
          },
        }),
      },
    );

    revalidateProjectSurfaces(projectId);
    let nextPath = withQueryValue(
      returnTo,
      "team_notice",
      `已把 ${text(targetDoc.title ?? targetDoc.name, repoPath)} 绑定到 ${seatName} 的知识库配置源`,
    );
    nextPath = withQueryValue(nextPath, "seat", seatRecordId);
    redirect(nextPath);
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "绑定知识库到 NPC 失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

async function applySkillForgeSeatSkillAssignment(projectId: string, seatId: string, skillId: string) {
  const { project } = await ensureProjectCollaborationAccess(projectId);
  const normalizedSeatId = text(seatId, "");
  const normalizedSkillId = text(skillId, "").toLowerCase();
  if (!normalizedSeatId || !normalizedSkillId) {
    throw new Error("缺少 NPC 或 Skill，不能执行能力配置。");
  }

  const [skillsResult, seatsResult] = await Promise.all([
    getJson(`/api/knowledge/projects/${projectId}/skills`),
    getJson(`/api/collaboration/projects/${projectId}/thread-workstations`),
  ]);
  const projectSkills = asArray<Record<string, unknown>>(skillsResult?.data ?? skillsResult);
  const collaborationConfig = readProjectCollaborationConfig(project);
  const skillLibrary = asArray<Record<string, unknown>>(collaborationConfig.skill_library);
  const targetSkill =
    projectSkills.find((item) => text(item.skill_id ?? item.id, "").toLowerCase() === normalizedSkillId) ??
    skillLibrary.find((item) => text(item.id ?? item.skill_id, "").toLowerCase() === normalizedSkillId) ??
    DEFAULT_PLATFORM_SKILL_LIBRARY.find((item) => text(item.id, "").toLowerCase() === normalizedSkillId) ??
    null;
  if (!targetSkill) {
    throw new Error("项目 Skill 仓库里没有找到这个 Skill。");
  }
  const targetSkillRecord = targetSkill as Record<string, unknown>;
  const skillLabel = text(targetSkillRecord.label ?? targetSkillRecord.name ?? targetSkillRecord.skill_id, normalizedSkillId);
  const seats = asArray<Record<string, unknown>>(seatsResult?.data ?? seatsResult);
  const seat =
    seats.find((item) =>
      isNpcSeatRecord(item) &&
      (
        workstationLookupKeys(item).some((candidate) => candidate === normalizedSeatId) ||
        seatIdentityValues(item).some((candidate) => candidate === normalizedSeatId)
      ),
    ) ?? null;
  if (!seat) {
    throw new Error("没有找到这个 NPC，不能把能力绑定到线程或电脑记录。");
  }
  const seatRecordId = text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, normalizedSeatId);
  const seatName = text(seat.name ?? seat.workstation_name, "该 NPC");

  if (!projectSkills.some((item) => text(item.skill_id ?? item.id, "").toLowerCase() === normalizedSkillId)) {
    await postJson(`/api/knowledge/projects/${projectId}/skills`, {
      skill_id: normalizedSkillId,
      label: skillLabel,
      source: text(targetSkillRecord.source, "project-library"),
      category: text(targetSkillRecord.category, "custom"),
      repo_relative_path: text(targetSkillRecord.repo_relative_path ?? targetSkillRecord.doc_path, "") || null,
      description: text(targetSkillRecord.description ?? targetSkillRecord.note ?? targetSkillRecord.summary, ""),
      recommended_for: normalizeUnknownStringList(targetSkillRecord.recommended_for),
      exists_in_repo: targetSkillRecord.exists_in_repo === true,
      extra_data: readRecord(targetSkillRecord.metadata ?? targetSkillRecord.extra_data ?? targetSkillRecord.extraData),
    });
  }

  await postJson(`/api/knowledge/projects/${projectId}/seat-skill-assignments`, {
    seat_id: seatRecordId,
    skill_id: normalizedSkillId,
    assignment_type: "direct",
    status: "active",
    notes: "由能力工坊人工确认后添加到该 NPC 的长期能力配置。",
    extra_data: {
      configured_from: "skill-forge",
      configured_at: new Date().toISOString(),
    },
  });

  const metadata = readRecord(seat.metadata ?? seat.extra_data ?? seat.extraData);
  const existingLoadout = mergePlatformSkillLoadout(
    seat.skill_loadout,
    seat.skillLoadout,
    metadata.additional_skill_ids,
    metadata.skill_loadout,
    normalizedSkillId,
  );
  const { roleSkillIds } = splitPlatformSkillLoadout(existingLoadout, skillLibrary);
  await patchJson(
    `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(seatRecordId)}`,
    {
      metadata: mergeSeatMetadata(metadata, {
        additional_skill_ids: roleSkillIds,
        skill_loadout: existingLoadout,
        skill_forge_snapshot: {
          source: "能力工坊",
          generated_at: new Date().toISOString(),
          changed_skill_id: normalizedSkillId,
          changed_skill_label: skillLabel,
          summary: "能力工坊已通过人工确认更新该 NPC 的 Skill 配置源；后续新派单和刷新后的上岗包会读取这份配置。",
        },
      }),
    },
  );
  return { seatRecordId, seatName, skillLabel };
}

export async function 处理能力工坊待确认(projectId: string, messageId: string, decision: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "company");
  try {
    const { currentUser } = await ensureProjectCollaborationAccess(projectId);
    const currentUserId = normalizeMessageFormValue(currentUser?.id) ?? normalizeMessageFormValue(currentUser?.email);
    const messagesResult = await getJson(
      `/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&message_type=human_review_request&limit=200`,
    );
    const messages = asArray<Record<string, unknown>>(messagesResult?.data ?? messagesResult);
    const reviewMessage = messages.find((item) => text(item.id, "") === messageId);
    if (!reviewMessage) {
      throw new Error("没有找到这条待确认请求。");
    }
    const metadata = readRecord(reviewMessage.extra_data ?? reviewMessage.extraData ?? reviewMessage.metadata);
    if (text(metadata.schema, "") !== "skill_forge_review_v1") {
      throw new Error("这不是能力工坊待确认请求。");
    }
    const currentStatus = text(reviewMessage.status, "").toLowerCase();
    if (!["pending_human_review", "pending", "open"].includes(currentStatus)) {
      throw new Error("这条待确认请求已经处理过。");
    }

    const normalizedDecision = text(decision || formData.get("decision"), "approve");
    if (normalizedDecision === "reject") {
      await patchJson(`/api/collaboration/messages/${encodeURIComponent(messageId)}`, { status: "rejected" });
      await postJson("/api/collaboration/messages", {
        project_id: projectId,
        message_type: "human_review_decision",
        title: `已打回：${text(reviewMessage.title, "能力工坊待确认")}`,
        body: "人工确认结论：打回。本次没有改动 NPC 能力配置源。",
        sender_type: "human",
        sender_id: currentUserId,
        recipient_type: "project",
        recipient_id: projectId,
        status: "closed",
      });
      revalidateProjectSurfaces(projectId);
      redirect(withQueryValue(returnTo, "team_notice", "已打回能力工坊待确认请求。"));
    }

    const result = await applySkillForgeSeatSkillAssignment(
      projectId,
      text(metadata.seat_id, ""),
      text(metadata.skill_id, ""),
    );
    await patchJson(`/api/collaboration/messages/${encodeURIComponent(messageId)}`, { status: "approved" });
    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      message_type: "human_review_decision",
      title: `已通过：${result.seatName} 添加 ${result.skillLabel}`,
      body: "人工确认结论：通过。能力工坊已刷新该 NPC 的配置源和上岗包摘要，正在执行的任务仍保持旧快照。",
      sender_type: "human",
      sender_id: currentUserId,
      recipient_type: "project",
      recipient_id: projectId,
      status: "closed",
      extra_data: {
        schema: "skill_forge_review_decision_v1",
        review_message_id: messageId,
        seat_id: result.seatRecordId,
        skill_id: text(metadata.skill_id, ""),
      },
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", `已通过并执行：${result.seatName} 添加 ${result.skillLabel}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "处理能力工坊待确认失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 导入AgencyAgents项目Skill包(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "skills");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig = readProjectCollaborationConfig(project);
    const currentSkillLibrary = Array.isArray(collaborationConfig.skill_library)
      ? [...(collaborationConfig.skill_library as Record<string, unknown>[])]
      : [];
    const currentSkillMap = new Map(
      currentSkillLibrary.map((item, index) => [text(item.id, "").toLowerCase(), { item, index }] as const).filter(([id]) => Boolean(id)),
    );
    const pack = await readAgencyAgentsSkillPack();
    const requestedIds = uniqueStrings(formData.getAll("skill_id").map((item) => text(item)));
    const importAll = text(formData.get("import_mode"), "") === "all" || !requestedIds.length;
    const requestedIdSet = new Set(requestedIds.map((item) => item.toLowerCase()));
    const importedSkills = (pack.skill_library ?? [])
      .map((item) => normalizeImportedProjectSkill(item))
      .filter((item) => (importAll ? true : requestedIdSet.has(text(item.id, "").toLowerCase())))
      .filter((item) => item.id && !RESERVED_PLATFORM_SKILL_IDS.includes(item.id));
    if (!importedSkills.length) {
      throw new Error(importAll ? "Agency Agents skill 包里没有可导入的 skill" : "当前没有命中可导入的所选 Skill");
    }

    let addedCount = 0;
    let updatedCount = 0;
    const nextSkills = [...currentSkillLibrary];
    importedSkills.forEach((skill) => {
      const key = text(skill.id, "").toLowerCase();
      const existing = currentSkillMap.get(key);
      if (!existing) {
        addedCount += 1;
        nextSkills.push(skill);
        currentSkillMap.set(key, { item: skill, index: nextSkills.length - 1 });
        return;
      }
      const previousJson = JSON.stringify(existing.item);
      const nextJson = JSON.stringify(skill);
      if (previousJson !== nextJson) {
        updatedCount += 1;
        nextSkills[existing.index] = skill;
        currentSkillMap.set(key, { item: skill, index: existing.index });
      }
    });

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        skill_library: sortProjectSkillLibrary(nextSkills),
      },
    });
    revalidateProjectSurfaces(projectId);
    const totalCount = importedSkills.length;
    const categoryCount = new Set(importedSkills.map((item) => skillCategoryLabel(item))).size;
    const summary =
      addedCount || updatedCount
        ? importAll
          ? `已同步 Agency Agents Skill：新增 ${addedCount} 条，更新 ${updatedCount} 条，覆盖 ${categoryCount} 类`
          : `已同步所选 Agency Agents Skill：选中 ${requestedIds.length} 条，新增 ${addedCount} 条，更新 ${updatedCount} 条，覆盖 ${categoryCount} 类`
        : importAll
          ? `Agency Agents Skill 已是最新，共 ${totalCount} 条 / ${categoryCount} 类`
          : `所选 Agency Agents Skill 已是最新：选中 ${requestedIds.length} 条 / ${categoryCount} 类`;
    redirect(withQueryValue(returnTo, "team_notice", summary));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "导入 Agency Agents Skill 包失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 导入Github项目Skill(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "skills");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig = readProjectCollaborationConfig(project);
    const currentSkillLibrary = Array.isArray(collaborationConfig.skill_library)
      ? [...(collaborationConfig.skill_library as Record<string, unknown>[])]
      : [];
    const githubUrl = text(formData.get("github_url"), "");
    const githubPath = text(formData.get("github_path"), "");
    const githubBranch = text(formData.get("github_branch"), "");
    const category = text(formData.get("category"), "github");
    const recommendedFor = parseStringList(formData.get("recommended_for")) ?? [];
    const assignmentSeatId = text(formData.get("assignment_seat_id"), "");
    if (!githubUrl) {
      throw new Error("请先粘贴 GitHub repo、目录、blob 或 raw 文件地址。");
    }

    const target = parseGithubUrl(githubUrl, githubPath, githubBranch);
    const sourceFiles = await readGithubSkillSourceFiles(target);
    const importedSkills = sourceFiles
      .flatMap((sourceFile) => parseGithubSkillFile(sourceFile, { category, recommendedFor }))
      .filter((item) => text(item.id, "") && text(item.label, ""))
      .filter((item) => !RESERVED_PLATFORM_SKILL_IDS.includes(text(item.id, "").toLowerCase()))
      .slice(0, GITHUB_SKILL_IMPORT_MAX_SKILLS);
    if (!importedSkills.length) {
      throw new Error("GitHub 内容里没有解析出可导入的 Skill，请确认文件是 Markdown 或 JSON Skill。");
    }

    let addedCount = 0;
    let updatedCount = 0;
    const nextSkills = [...currentSkillLibrary];
    const currentSkillMap = new Map(
      currentSkillLibrary
        .map((item, index) => [text(item.id, "").toLowerCase(), { item, index }] as const)
        .filter(([id]) => Boolean(id)),
    );

    importedSkills.forEach((skill) => {
      const key = text(skill.id, "").toLowerCase();
      const existing = currentSkillMap.get(key);
      if (!existing) {
        addedCount += 1;
        nextSkills.push(skill);
        currentSkillMap.set(key, { item: skill, index: nextSkills.length - 1 });
        return;
      }
      const previousJson = JSON.stringify(existing.item);
      const nextJson = JSON.stringify(skill);
      if (previousJson !== nextJson) {
        updatedCount += 1;
        nextSkills[existing.index] = skill;
        currentSkillMap.set(key, { item: skill, index: existing.index });
      }
    });

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        skill_library: sortProjectSkillLibrary(nextSkills),
      },
    });
    if (assignmentSeatId) {
      for (const skill of importedSkills) {
        const skillId = text(skill.id, "");
        if (!skillId) continue;
        await postJson(`/api/knowledge/projects/${projectId}/seat-skill-assignments`, {
          seat_id: assignmentSeatId,
          skill_id: skillId,
          assignment_type: "github-import",
          status: "active",
          notes: "从 GitHub 导入后添加到该 NPC 的长期能力配置。",
          extra_data: {
            imported_from: "github",
            source_url: text((skill.metadata as Record<string, unknown> | undefined)?.source_url, ""),
          },
        });
      }
    }
    revalidateProjectSurfaces(projectId);
    const repoLabel = `${target.owner}/${target.repo}`;
    const summary =
      addedCount || updatedCount
        ? `已从 GitHub 导入 Skill：${repoLabel} / 文件 ${sourceFiles.length} 个 / 新增 ${addedCount} 条 / 更新 ${updatedCount} 条${assignmentSeatId ? " / 已添加到当前 NPC" : ""}`
        : `GitHub Skill 已是最新：${repoLabel} / ${importedSkills.length} 条${assignmentSeatId ? " / 已添加到当前 NPC" : ""}`;
    redirect(withQueryValue(returnTo, "team_notice", summary));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "导入 GitHub Skill 失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 应用机器人协作模板(projectId: string) {
  await patchJson(`/api/projects/${projectId}`, {
    collaboration_config: {
      computer_nodes: [
        {
          id: "pc-1",
          label: "电脑1",
          status: "online",
          runner_id: "runner-codex",
          host: "192.168.1.21",
          os: "Windows 11",
        },
        {
          id: "pc-2",
          label: "电脑2",
          status: "online",
          runner_id: "runner-claude",
          host: "192.168.1.22",
          os: "macOS",
        },
      ],
      ai_providers: [
        {
          id: "codex",
          label: "Codex",
          kind: "thread",
          enabled: true,
          endpoint: "openai",
          model: "gpt-5.1-codex",
        },
        {
          id: "claude",
          label: "Claude",
          kind: "thread",
          enabled: true,
          endpoint: "anthropic",
          model: "claude-opus-4.1",
        },
      ],
      thread_workstations: [
        {
          name: "前端工位",
          agent_id: "ai-fe-lead",
          computer_node: "电脑1",
          computer_node_id: "pc-1",
          ai_provider: "Codex",
          ai_provider_id: "codex",
          status: "active",
          description: "电脑1 上的 Codex 线程，负责前端与产品体验。",
          notes: "适合 UI、页面、交互和前端联调。",
        },
        {
          name: "机器人工位",
          agent_id: "ai-robot-lead",
          computer_node: "电脑2",
          computer_node_id: "pc-2",
          ai_provider: "Claude",
          ai_provider_id: "claude",
          status: "active",
          description: "电脑2 上的 Claude 线程，负责机器人控制与分析。",
          notes: "适合硬件约束、系统分析和机器人协作任务。",
        },
      ],
    },
  });
  revalidateProjectSurfaces(projectId);
}

export async function 创建协作电脑节点(projectId: string, formData: FormData) {
  const rawReturnTo = String(formData.get("return_to") ?? "").trim();
  const returnTo = normalizeProjectReturnPath(projectId, rawReturnTo, "computers");
  const nodeId = String(formData.get("id") ?? "").trim() || null;
  const nodeLabel = String(formData.get("label") ?? "").trim() || "未命名电脑";
  try {
    await postJson(`/api/collaboration/projects/${projectId}/computer-nodes`, {
      id: nodeId,
      label: nodeLabel,
      status: String(formData.get("status") ?? "offline").trim() || "offline",
      runner_id: String(formData.get("runner_id") ?? "").trim() || null,
      host: String(formData.get("host") ?? "").trim() || null,
      os: String(formData.get("os") ?? "").trim() || null,
      connection_kind: String(formData.get("connection_kind") ?? "").trim() || null,
      workspace_root: String(formData.get("workspace_root") ?? "").trim() || null,
      git_root: String(formData.get("git_root") ?? "").trim() || null,
      read_paths: parseStringList(formData.get("read_paths")),
      write_paths: parseStringList(formData.get("write_paths")),
      sort_order: Number(formData.get("sort_order") ?? 0) || 0,
      metadata: parseOptionalJson(String(formData.get("metadata") ?? "")),
    });
    revalidateProjectSurfaces(projectId);
    if (rawReturnTo) {
      let nextPath = withQueryValue(returnTo, "team_notice", `已登记电脑：${nodeLabel}${nodeId ? `（${nodeId}）` : ""}`);
      if (nodeId) {
        nextPath = withQueryValue(nextPath, "computer", nodeId);
      }
      redirect(nextPath);
    }
  } catch (error) {
    rethrowRedirectError(error);
    revalidateProjectSurfaces(projectId);
    if (rawReturnTo) {
      const message = error instanceof Error ? error.message : "登记电脑失败";
      redirect(withQueryValue(returnTo, "team_error", message));
    }
    throw error;
  }
}

export async function 删除协作电脑节点(projectId: string, nodeId: string) {
  await deleteJson(`/api/collaboration/projects/${projectId}/computer-nodes/${encodeURIComponent(nodeId)}`);
  revalidateProjectSurfaces(projectId);
}

export async function 生成电脑配对令牌(projectId: string, nodeId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "computers");
  const result = await postJson(
    `/api/collaboration/projects/${projectId}/computer-nodes/${encodeURIComponent(nodeId)}/pairing-token`,
    {},
  );
  const token = String(result?.data?.token ?? "").trim();
  revalidateProjectSurfaces(projectId);
  let nextPath = withQueryValue(returnTo, "pairing_node", nodeId);
  nextPath = withQueryValue(nextPath, "pairing_token", token);
  nextPath = withQueryValue(nextPath, "team_notice", `已生成 ${nodeId} 的配对令牌，请在目标电脑执行接入命令`);
  redirect(nextPath);
}

export async function 吊销电脑配对令牌(projectId: string, nodeId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "computers");
  await deleteJson(`/api/collaboration/projects/${projectId}/computer-nodes/${encodeURIComponent(nodeId)}/pairing-token`);
  revalidateProjectSurfaces(projectId);
  redirect(withQueryValue(returnTo, "team_notice", `已吊销 ${nodeId} 的配对令牌`));
}

export async function 生成工位接入令牌(projectId: string, workstationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "machine-room");
  const sanitizedReturnTo = withoutQueryKeys(returnTo, ["adapter_workstation", "adapter_token"]);
  const result = await postJson(
    `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(workstationId)}/adapter-token`,
    {},
  );
  const token = String(result?.data?.token ?? "").trim();
  revalidateProjectSurfaces(projectId);
  let nextPath = withQueryValue(sanitizedReturnTo, "adapter_workstation", workstationId);
  nextPath = withQueryValue(nextPath, "adapter_token", token);
  nextPath = withQueryValue(nextPath, "team_notice", `已生成 ${workstationId} 的工位接入令牌`);
  redirect(nextPath);
}

export async function 吊销工位接入令牌(projectId: string, workstationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "machine-room");
  const sanitizedReturnTo = withoutQueryKeys(returnTo, ["adapter_workstation", "adapter_token"]);
  await deleteJson(
    `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(workstationId)}/adapter-token`,
  );
  revalidateProjectSurfaces(projectId);
  redirect(withQueryValue(sanitizedReturnTo, "team_notice", `已吊销 ${workstationId} 的工位接入令牌`));
}

export async function 创建协作AI提供方(projectId: string, formData: FormData) {
  await postJson(`/api/collaboration/projects/${projectId}/ai-providers`, {
    id: String(formData.get("id") ?? "").trim() || null,
    label: String(formData.get("label") ?? "").trim() || "未命名 AI",
    kind: String(formData.get("kind") ?? "").trim() || null,
    enabled: String(formData.get("enabled") ?? "true").trim() !== "false",
    endpoint: String(formData.get("endpoint") ?? "").trim() || null,
    model: String(formData.get("model") ?? "").trim() || null,
    sort_order: Number(formData.get("sort_order") ?? 0) || 0,
    metadata: parseOptionalJson(String(formData.get("metadata") ?? "")),
  });
  revalidateProjectSurfaces(projectId);
}

export async function 删除协作AI提供方(projectId: string, providerId: string) {
  await deleteJson(`/api/collaboration/projects/${projectId}/ai-providers/${encodeURIComponent(providerId)}`);
  revalidateProjectSurfaces(projectId);
}

export async function 更新协作AI提供方执行配置(projectId: string, providerId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "machine-room");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const normalizedProviderId =
      normalizePlatformProviderId(providerId) ||
      normalizePlatformProviderId(formData.get("provider_id")) ||
      "codex";
    const submittedLabel = text(formData.get("provider_label"), "");
    const submittedModel = text(formData.get("model"), "");
    await ensureProjectAiProvider(projectId, project, {
      providerId: normalizedProviderId,
      providerLabel: submittedLabel || platformProviderLabel(normalizedProviderId),
      model: submittedModel || null,
    });
    const providerResult = await getJson(
      `/api/collaboration/projects/${projectId}/ai-providers/${encodeURIComponent(normalizedProviderId)}`,
    );
    const provider =
      providerResult?.data && typeof providerResult.data === "object"
        ? (providerResult.data as Record<string, unknown>)
        : providerResult && typeof providerResult === "object"
          ? (providerResult as Record<string, unknown>)
          : {};
    const clearExecutorTemplate = text(formData.get("clear_executor_template"), "") === "true";
    const providerLabel =
      submittedLabel ||
      text(provider.label ?? provider.name, "") ||
      platformProviderLabel(normalizedProviderId);
    const nextMetadata = mergeExecutionMetadata(provider.metadata, {
      executorCommand: clearExecutorTemplate ? null : text(formData.get("executor_command"), "") || null,
      executorCwd: clearExecutorTemplate ? null : text(formData.get("executor_cwd"), "") || null,
      executorTimeoutSeconds: clearExecutorTemplate
        ? null
        : parseOptionalPositiveInteger(formData.get("executor_timeout_seconds")),
      clearExecutorTemplate,
    });
    await patchJson(
      `/api/collaboration/projects/${projectId}/ai-providers/${encodeURIComponent(normalizedProviderId)}`,
      {
        label: providerLabel,
        model: submittedModel || text(provider.model, "") || null,
        metadata: nextMetadata,
      },
    );
    revalidateProjectSurfaces(projectId);
    redirect(
      withQueryValue(
        returnTo,
        "team_notice",
        clearExecutorTemplate ? `已清空 ${providerLabel} 的默认执行模板` : `已保存 ${providerLabel} 的默认执行模板`,
      ),
    );
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "保存 AI 提供方执行模板失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 创建协作线程工位(projectId: string, formData: FormData) {
  const rawReturnTo = String(formData.get("return_to") ?? "").trim();
  const workstationName = String(formData.get("name") ?? "").trim() || "未命名工位";
  const responsibility = String(formData.get("responsibility") ?? "").trim() || null;
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim() || null;
  const sourceMetadata = parseOptionalJson(String(formData.get("metadata") ?? ""));
  const metadata =
    sourceMetadata && typeof sourceMetadata === "object"
      ? ({ ...(sourceMetadata as Record<string, unknown>) } satisfies Record<string, unknown>)
      : null;
  const seatType = text(metadata?.seat_type, "").toLowerCase();
  const model = String(formData.get("model") ?? "").trim() || null;
  const aiProviderId = normalizePlatformProviderId(formData.get("ai_provider_id"));
  const aiProviderLabel = text(formData.get("ai_provider"), "") || (aiProviderId ? platformProviderLabel(aiProviderId) : "");
  const storedNpcKnowledge =
    metadata?.npc_knowledge && typeof metadata.npc_knowledge === "object"
      ? (metadata.npc_knowledge as Record<string, unknown>)
      : {};
  const npcKnowledge =
    seatType === "codex"
      ? buildNpcKnowledgeProfile({
          name: workstationName,
          responsibility,
          seatId: text(metadata?.id ?? metadata?.source_workstation_id, "") || null,
          knowledgeSlug: text(storedNpcKnowledge.slug ?? metadata?.npc_identity_key, "").replace(/^npc:/, "") || null,
          knowledgeSummary: text(storedNpcKnowledge.summary, "") || null,
          knowledgeHandoffPath: text(storedNpcKnowledge.handoff_path, "") || null,
          knowledgeTags: asArray<string>(storedNpcKnowledge.tags),
        })
      : null;
  const normalizedMetadata =
    seatType === "codex"
      ? mergeSeatMetadata(metadata, {
          seat_type: "codex",
          npc_identity_key: npcKnowledge?.key ?? null,
          npc_knowledge: npcKnowledge ?? null,
        })
      : metadata;
  if (aiProviderId) {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    await ensureProjectAiProvider(projectId, project, {
      providerId: aiProviderId,
      providerLabel: aiProviderLabel,
      model,
    });
  }
  const created = await postJson(`/api/collaboration/projects/${projectId}/thread-workstations`, {
    id: String(formData.get("id") ?? "").trim() || null,
    name: workstationName,
    agent_id: String(formData.get("agent_id") ?? "").trim() || null,
    computer_node: String(formData.get("computer_node") ?? "").trim() || null,
    computer_node_id: computerNodeId,
    ai_provider: aiProviderLabel || null,
    ai_provider_id: aiProviderId || null,
    status: String(formData.get("status") ?? "idle").trim() || "idle",
    responsibility,
    model,
    permission_level: String(formData.get("permission_level") ?? "").trim() || null,
    read_paths: parseStringList(formData.get("read_paths")),
    write_paths: parseStringList(formData.get("write_paths")),
    description: String(formData.get("description") ?? "").trim() || null,
    notes: String(formData.get("notes") ?? "").trim() || null,
    sort_order: Number(formData.get("sort_order") ?? 0) || 0,
    metadata: normalizedMetadata,
  });
  if (npcKnowledge) {
    await ensureNpcKnowledgeDoc({
      handoffPath: npcKnowledge.handoff_path,
      seatName: workstationName,
      responsibility: responsibility || "",
      projectId,
      additionalSkillIds: asArray<string>(normalizedMetadata?.additional_skill_ids),
      sourceWorkstationId: text(normalizedMetadata?.source_workstation_id, "") || null,
      computerNodeId,
      model,
    });
  }
  revalidateProjectSurfaces(projectId);
  if (rawReturnTo) {
    redirect(normalizeProjectReturnPath(projectId, rawReturnTo, "machine-room"));
  }
}

export async function 删除协作线程工位(projectId: string, workstationId: string) {
  await deleteJson(
    `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(workstationId)}`,
  );
  revalidateProjectSurfaces(projectId);
}

export async function 更新协作线程工位执行配置(projectId: string, workstationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "machine-room");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const workstationResult = await getJson(
      `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(workstationId)}`,
    );
    const workstation =
      workstationResult?.data && typeof workstationResult.data === "object"
        ? (workstationResult.data as Record<string, unknown>)
        : workstationResult && typeof workstationResult === "object"
          ? (workstationResult as Record<string, unknown>)
          : {};
    const workstationLabel =
      text(workstation.name ?? workstation.workstation_name, "") || workstationId;
    const clearExecutorOverride = text(formData.get("clear_executor_override"), "") === "true";
    const submittedModel = text(formData.get("model"), "");
    const nextMetadata = mergeExecutionMetadata(workstation.metadata, {
      executorCommand: clearExecutorOverride ? null : text(formData.get("executor_command"), "") || null,
      executorCwd: clearExecutorOverride ? null : text(formData.get("executor_cwd"), "") || null,
      executorTimeoutSeconds: clearExecutorOverride
        ? null
        : parseOptionalPositiveInteger(formData.get("executor_timeout_seconds")),
      clearExecutorTemplate: clearExecutorOverride,
    });
    await patchJson(
      `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(workstationId)}`,
      {
        model: submittedModel || text(workstation.model, "") || null,
        metadata: nextMetadata,
      },
    );
    revalidateProjectSurfaces(projectId);
    redirect(
      withQueryValue(
        returnTo,
        "team_notice",
        clearExecutorOverride ? `已清空 ${workstationLabel} 的工位执行覆盖` : `已保存 ${workstationLabel} 的工位执行配置`,
      ),
    );
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "保存工位执行配置失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

function revalidateRunnerSurfaces(runnerId: string, projectId: string) {
  revalidatePath(`/runners/${runnerId}`);
  revalidatePath("/runners");
  revalidateProjectSurfaces(projectId);
}

export async function 绑定Runner到项目电脑节点(formData: FormData) {
  const runnerId = String(formData.get("runner_id") ?? "").trim();
  const projectId = String(formData.get("project_id") ?? "").trim();
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  if (!runnerId || !projectId || !computerNodeId) {
    return;
  }
  await postJson(`/api/runners/${encodeURIComponent(runnerId)}/bindings`, {
    project_id: projectId,
    computer_node_id: computerNodeId,
  });
  revalidateRunnerSurfaces(runnerId, projectId);
}

export async function 解绑Runner从项目电脑节点(formData: FormData) {
  const runnerId = String(formData.get("runner_id") ?? "").trim();
  const projectId = String(formData.get("project_id") ?? "").trim();
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  if (!runnerId || !projectId || !computerNodeId) {
    return;
  }
  await deleteJson(
    `/api/runners/${encodeURIComponent(runnerId)}/bindings/${encodeURIComponent(projectId)}/${encodeURIComponent(
      computerNodeId,
    )}`,
  );
  revalidateRunnerSurfaces(runnerId, projectId);
}

export async function 绑定Runner到电脑节点(projectId: string, formData: FormData) {
  const runnerId = String(formData.get("runner_id") ?? "").trim();
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  if (!runnerId || !computerNodeId) {
    return;
  }
  await postJson(`/api/runners/${encodeURIComponent(runnerId)}/bindings`, {
    project_id: projectId,
    computer_node_id: computerNodeId,
  });
  revalidateProjectSurfaces(projectId);
}

export async function 解绑Runner从电脑节点(projectId: string, formData: FormData) {
  const runnerId = String(formData.get("runner_id") ?? "").trim();
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  if (!runnerId || !computerNodeId) {
    return;
  }
  await deleteJson(
    `/api/runners/${encodeURIComponent(runnerId)}/bindings/${encodeURIComponent(projectId)}/${encodeURIComponent(
      computerNodeId,
    )}`,
  );
  revalidateProjectSurfaces(projectId);
}

export async function 更新工位配置(agentId: string, formData: FormData) {
  const modules = String(formData.get("modules") ?? "")
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
  await patchJson(`/api/agents/${agentId}`, {
    name: String(formData.get("name") ?? ""),
    role: String(formData.get("role") ?? ""),
    responsibility: String(formData.get("responsibility") ?? ""),
    permission_level: String(formData.get("permission_level") ?? "L2"),
    notes: String(formData.get("notes") ?? ""),
    modules,
  });
  revalidatePath(`/agents/${agentId}`);
  revalidatePath("/agents");
  revalidatePath("/base");
}

export async function 注册用户(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const returnTo = normalizeAuthReturnPath(formData.get("return_to"));
  let result: any;
  try {
    await postJson("/api/auth/register", {
      email,
      name: String(formData.get("name") ?? ""),
      password,
      global_role: "member",
    });
    result = await postJson("/api/auth/session", {
      email,
      password,
    });
  } catch (error) {
    const code = (error as { code?: string }).code ?? "REGISTER_FAILED";
    const nextLogin = returnTo
      ? `/login?mode=signup&error=${encodeURIComponent(code)}&returnTo=${encodeURIComponent(returnTo)}`
      : `/login?mode=signup&error=${encodeURIComponent(code)}`;
    redirect(nextLogin);
  }
  const session = result.data ?? result;
  const user = session.user ?? {};
  const cookieStore = cookies();
  cookieStore.set(ACCESS_TOKEN_COOKIE, session.access_token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });
  cookieStore.set(USER_COOKIE, JSON.stringify({ id: user.id, name: user.name, email: user.email }), {
    httpOnly: false,
    sameSite: "lax",
    path: "/",
  });
  revalidatePath("/login");
  revalidatePath("/members");
  revalidatePath("/projects");
  redirect(returnTo || "/projects");
}

export async function 登录用户(formData: FormData) {
  let result: any;
  const returnTo = normalizeAuthReturnPath(formData.get("return_to"));
  try {
    result = await postJson("/api/auth/session", {
      email: String(formData.get("email") ?? ""),
      password: String(formData.get("password") ?? ""),
    });
  } catch (error) {
    const code = (error as { code?: string }).code ?? "LOGIN_FAILED";
    const nextLogin = returnTo
      ? `/login?error=${encodeURIComponent(code)}&returnTo=${encodeURIComponent(returnTo)}`
      : `/login?error=${encodeURIComponent(code)}`;
    redirect(nextLogin);
  }
  const session = result.data ?? result;
  const user = session.user ?? {};
  const cookieStore = cookies();
  cookieStore.set(ACCESS_TOKEN_COOKIE, session.access_token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });
  cookieStore.set(USER_COOKIE, JSON.stringify({ id: user.id, name: user.name, email: user.email }), {
    httpOnly: false,
    sameSite: "lax",
    path: "/",
  });
  revalidatePath("/login");
  revalidatePath("/members");
  revalidatePath("/base");
  redirect(returnTo || "/projects");
}

export async function 退出登录(formData?: FormData) {
  const returnTo = normalizeAuthReturnPath(formData?.get("return_to"), "/login");
  const cookieStore = cookies();
  cookieStore.delete(ACCESS_TOKEN_COOKIE);
  cookieStore.delete(USER_COOKIE);
  revalidatePath("/");
  revalidatePath("/login");
  revalidatePath("/projects");
  redirect(returnTo || "/login");
}

export async function 发出邀请(formData: FormData) {
  const email = text(formData.get("email"), "").toLowerCase();
  const projectId = text(formData.get("project_id"), "");
  const role = text(formData.get("role"), "collaborator");
  const note = text(formData.get("note"), "");
  const fallbackReturnTo = projectId
    ? `/projects?tab=invite&project_id=${encodeURIComponent(projectId)}`
    : "/projects?tab=invite";
  const returnTo = normalizeWorkspaceReturnPath(formData.get("return_to"), fallbackReturnTo);

  try {
    if (!projectId) {
      throw new Error("请先选择一个项目，再发送邀请。");
    }
    if (!email) {
      throw new Error("请先填写合作者邮箱。");
    }
    await postJson("/api/auth/invitations", {
      email,
      project_id: projectId,
      role,
      invited_by_user_id: text(formData.get("invited_by_user_id"), "") || null,
      note,
    });
    revalidatePath("/projects");
    revalidatePath("/members");
    redirect(withQueryValue(returnTo, "team_notice", `已发送邀请给 ${email}，对方登录后会在“接受邀请”里看到。`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "发送邀请失败，请稍后重试。";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 接受邀请(invitationId: string, formData: FormData) {
  await postJson(`/api/auth/invitations/${invitationId}/accept`, {
    name: String(formData.get("name") ?? "").trim() || null,
    password: String(formData.get("password") ?? "").trim() || null,
    accepted_by_user_id: String(formData.get("accepted_by_user_id") ?? "").trim() || null,
  });
  revalidatePath("/projects");
  revalidatePath("/members");
  revalidatePath("/login");
}

export async function 接受工作台邀请(invitationId: string) {
  await postJson(`/api/auth/invitations/${invitationId}/accept`, {});
  revalidatePath("/projects");
  revalidatePath("/members");
}

export async function 摘要上下文(taskId: string, formData: FormData) {
  await postJson(`/api/tasks/${taskId}/summarize-context`, {
    project_id: String(formData.get("project_id") ?? "") || null,
    agent_id: String(formData.get("agent_id") ?? "") || null,
    usage_ratio: Number(formData.get("usage_ratio") ?? 0),
    health: String(formData.get("health") ?? "yellow"),
    conversation_turns: Number(formData.get("conversation_turns") ?? 0),
    files_loaded_count: Number(formData.get("files_loaded_count") ?? 0),
    failed_retry_count: Number(formData.get("failed_retry_count") ?? 0),
    summary: String(formData.get("summary") ?? "已从前端发起一次上下文摘要。"),
    recommended_action: String(formData.get("recommended_action") ?? "建议继续交接或压缩上下文。"),
  });
  revalidatePath("/context-health");
  revalidatePath(`/tasks/${taskId}`);
  revalidatePath(`/tasks/${taskId}/context`);
  revalidatePath("/handoffs");
}

export async function 预演协作消息(formData: FormData) {
  const payload = readCollaborationMessagePayload(formData);
  const projectId = payload.project_id;
  const returnTo = projectId
    ? normalizeProjectReturnPath(projectId, formData.get("return_to"), "exchange")
    : null;
  const previewKey = String(formData.get("preview_key") ?? "").trim() || "collaboration-message";
  try {
    if (!projectId) {
      throw new Error("协作消息必须带项目上下文，才能生成预演。");
    }
    if (!returnTo) {
      throw new Error("没有找到协作预演的返回路径。");
    }
    const access = await ensureProjectCollaborationAccess(projectId);
    const previewResult = await postJson("/api/collaboration/messages/preview", payload);
    const previewPayload =
      previewResult && typeof previewResult === "object" && previewResult.data ? previewResult.data : previewResult;
    const governancePreview = buildCollaborationGovernancePreview(
      access.project as Record<string, unknown>,
      payload,
    );
    const mergedPreviewPayload =
      previewPayload && typeof previewPayload === "object"
        ? {
            ...(previewPayload as Record<string, unknown>),
            governance_preview: governancePreview,
            warnings: [
              ...asArray((previewPayload as Record<string, unknown>).warnings).map((item) => text(item)).filter(Boolean),
              ...governancePreview.warnings,
            ],
            preview_notes: [
              ...asArray((previewPayload as Record<string, unknown>).preview_notes)
                .map((item) => text(item))
                .filter(Boolean),
              ...governancePreview.notes,
            ],
          }
        : {
            governance_preview: governancePreview,
            warnings: governancePreview.warnings,
            preview_notes: governancePreview.notes,
          };
    const withPreview = withQueryValue(
      returnTo,
      "collab_preview",
      encodePreviewState({ ...mergedPreviewPayload, preview_key: previewKey }),
    );
    const noticeTarget = payload.title ?? payload.recipient_id ?? "当前协作指令";
    redirect(withQueryValue(withPreview, "team_notice", `已生成协作预演：${noticeTarget}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "协作消息预演失败";
    if (returnTo) {
      redirect(withQueryValue(returnTo, "team_error", message));
    }
    throw error;
  }
}

export async function 提交协作消息(formData: FormData) {
  const payload = readCollaborationMessagePayload(formData);
  const projectId = payload.project_id;
  const taskId = payload.task_id;
  const requirementId = payload.requirement_id;
  const agentId = payload.agent_id;
  const returnTo = projectId
    ? normalizeProjectReturnPath(projectId, formData.get("return_to"), "exchange")
    : null;
  try {
    let currentUserId: string | null = null;
    let project: Record<string, unknown> | null = null;
    let governancePreview: ReturnType<typeof buildCollaborationGovernancePreview> | null = null;
    if (projectId) {
      const access = await ensureProjectCollaborationAccess(projectId);
      const { currentUser } = access;
      currentUserId = normalizeMessageFormValue(currentUser?.id) ?? normalizeMessageFormValue(currentUser?.email);
      project = access.project as Record<string, unknown>;
    }
    const enforcePreview = String(formData.get("enforce_preview") ?? "").trim() === "1";
    const requiredPreviewSignature = String(formData.get("required_preview_signature") ?? "").trim();
    const requiredPreviewReady = String(formData.get("required_preview_ready") ?? "").trim() === "1";
    if (enforcePreview) {
      if (!requiredPreviewSignature || !requiredPreviewReady) {
        throw new Error("请先预演当前协作指令，再正式发送到平台消息池。");
      }
      const actualSignature = buildCollaborationMessagePreviewSignature(payload, currentUserId);
      if (actualSignature !== requiredPreviewSignature) {
        throw new Error("协作指令已经改动，请先重新预演，再正式发送。");
      }
    }

    if (project && payload.message_type === "agent_command") {
      governancePreview = buildCollaborationGovernancePreview(project, payload);
      const humanReviewConfirmed = String(formData.get("human_review_confirmed") ?? "").trim() === "1";
      if (governancePreview.requires_human_review && !humanReviewConfirmed) {
        await postJson(
          "/api/collaboration/messages",
          buildHumanReviewRequestPayload(payload, governancePreview, currentUserId),
        );
        revalidatePath("/base");
        revalidatePath("/collaborators");
        revalidatePath("/requirements");
        revalidatePath("/handoffs");
        revalidatePath("/context-health");
        if (projectId) revalidatePath(`/projects/${projectId}`);
        if (taskId) revalidatePath(`/tasks/${taskId}`);
        if (agentId) revalidatePath(`/agents/${agentId}`);
        if (returnTo) {
          redirect(
            withQueryValue(
              returnTo,
              "team_notice",
              "这条协作指令已转入人工审核，没有派给目标线程。审核通过后再拆成只读/仿真/正式执行。",
            ),
          );
        }
        return;
      }
    }

    const outgoingPayload = withAiRequiredRequirementLedger(
      payload,
      resolveAiRequiredLedgerOptions(project, payload, currentUserId, governancePreview),
    );
    const messageResult = await postJson("/api/collaboration/messages", outgoingPayload);
    const messageRecord =
      messageResult && typeof messageResult === "object" ? (messageResult as Record<string, unknown>) : {};
    const messageData = messageRecord.data && typeof messageRecord.data === "object"
      ? (messageRecord.data as Record<string, unknown>)
      : {};
    const messageId =
      text(messageData.id) || text(messageRecord.id) || `msg-${Date.now()}`;

    const npcDispatchMode =
      project && projectId
        ? await resolveNpcSeatDispatchMode({
            project,
            formData,
            payload: outgoingPayload,
            messageId,
          })
        : null;

    // 如果是Claude席位，同时写入消息文件到inbox供桥接器读取
    if (npcDispatchMode?.providerId === "claude" && projectId) {
      try {
        const { writeClaudeSeatMessage } = await import("../lib/claude-seat-bridge");
        const workstations = readProjectThreadWorkstations(project);
        const recipientId = text(payload.recipient_id, "");
        const seat = workstations.find((item) =>
          workstationLookupKeys(item).some((candidate) => candidate === recipientId),
        );
        const seatName = text(seat?.name ?? seat?.workstation_name, "");
        if (seatName) {
          await writeClaudeSeatMessage({
            seatName,
            messageId,
            title: text(payload.title, "协作指令"),
            body: text(payload.body, ""),
            metadata: {
              project_id: projectId,
              recipient_id: recipientId,
              message_type: payload.message_type,
            },
          });
        }
      } catch (error) {
        console.error("写入Claude消息文件失败:", error);
      }
    }

    revalidatePath("/base");
    revalidatePath("/collaborators");
    revalidatePath("/requirements");
    if (requirementId) revalidatePath("/knowledge");
    revalidatePath("/handoffs");
    revalidatePath("/context-health");
    if (projectId) revalidatePath(`/projects/${projectId}`);
    if (taskId) revalidatePath(`/tasks/${taskId}`);
    if (agentId) revalidatePath(`/agents/${agentId}`);
    if (returnTo) {
      let notice = `已登记协作消息：${payload.title ?? payload.message_type}`;
      if (npcDispatchMode?.mode === "one-shot") {
        notice += npcDispatchMode.launched
          ? ` / 平台已把 ${platformProviderLabel(npcDispatchMode.providerId)} 单次处理交给目标电脑后台接收`
          : ` / 桌面线程启动失败：${npcDispatchMode.error ?? "请检查绑定线程和桌面同步状态"}`;
      }
      redirect(withQueryValue(returnTo, "team_notice", notice));
    }
  } catch (error) {
    rethrowRedirectError(error);
    if (returnTo) {
      const message = error instanceof Error ? error.message : "发送协作消息失败";
      redirect(withQueryValue(returnTo, "team_error", message));
    }
    throw error;
  }
}

export async function 处理协作人工审核(formData: FormData) {
  const projectId = normalizeMessageFormValue(formData.get("project_id"));
  const reviewMessageId = normalizeMessageFormValue(formData.get("review_message_id"));
  const decision = text(formData.get("decision"), "readonly_probe");
  const reviewerNote = text(formData.get("reviewer_note"), "");
  const returnTo = projectId
    ? normalizeProjectReturnPath(projectId, formData.get("return_to"), "exchange")
    : null;
  try {
    if (!projectId || !reviewMessageId) {
      throw new Error("处理人工审核需要项目和审核消息 ID。");
    }
    const { currentUser, project } = await ensureProjectCollaborationAccess(projectId);
    const currentUserId = normalizeMessageFormValue(currentUser?.id) ?? normalizeMessageFormValue(currentUser?.email);
    const messagesResult = await getJson(
      `/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&message_type=human_review_request&limit=200`,
    );
    const messages = asArray<Record<string, unknown>>(messagesResult?.data ?? messagesResult);
    const reviewMessage = messages.find((item) => text(item.id, "") === reviewMessageId);
    if (!reviewMessage) {
      throw new Error("没有找到这条人工审核请求，可能已经被处理或没有权限。");
    }
    const currentStatus = text(reviewMessage.status, "").toLowerCase();
    if (!["pending_human_review", "pending", "open"].includes(currentStatus)) {
      throw new Error(`这条人工审核请求已经是 ${currentStatus || "未知状态"}，不能重复处理。`);
    }

    if (decision === "reject") {
      await patchJson(`/api/collaboration/messages/${encodeURIComponent(reviewMessageId)}`, {
        status: "rejected",
      });
      await postJson("/api/collaboration/messages", {
        project_id: projectId,
        message_type: "human_review_decision",
        title: `已驳回：${text(reviewMessage.title, "人工审核请求")}`,
        body: [
          "人工审核结论：驳回，不派给目标线程。",
          reviewerNote ? `审核备注：${reviewerNote}` : "",
          "如果还要继续，请把需求拆小或补清只读/仿真/硬件边界后重新发起。",
        ].filter(Boolean).join("\n"),
        sender_type: "human",
        sender_id: currentUserId,
        recipient_type: "project",
        recipient_id: projectId,
        status: "closed",
      });
      revalidateProjectSurfaces(projectId);
      redirect(withQueryValue(returnTo ?? `/projects/${projectId}?panel=team&tab=exchange`, "team_notice", "已驳回这条人工审核请求，没有消耗目标线程 token。"));
    }

    const commandPayload = buildApprovedHumanReviewCommand(reviewMessage, decision, reviewerNote, currentUserId, project);
    if (!commandPayload.recipient_id || !commandPayload.recipient_type) {
      throw new Error("这条人工审核请求缺少原始目标，不能安全派发。");
    }
    await postJson("/api/collaboration/messages", commandPayload);
    const config = humanReviewDecisionConfig(decision);
    await patchJson(`/api/collaboration/messages/${encodeURIComponent(reviewMessageId)}`, {
      status: config.status,
    });
    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      message_type: "human_review_decision",
      title: `${config.notice}${text(reviewMessage.title, "") ? `：${text(reviewMessage.title, "")}` : ""}`,
      body: [
        config.notice,
        `审核请求: ${reviewMessageId}`,
        reviewerNote ? `审核备注：${reviewerNote}` : "",
        "平台已按人工选择生成新的 agent_command，目标线程只会看到收窄后的执行边界。",
      ].filter(Boolean).join("\n"),
      sender_type: "human",
      sender_id: currentUserId,
      recipient_type: "project",
      recipient_id: projectId,
      status: "closed",
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo ?? `/projects/${projectId}?panel=team&tab=exchange`, "team_notice", config.notice));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "处理人工审核失败";
    if (returnTo) {
      redirect(withQueryValue(returnTo, "team_error", message));
    }
    throw error;
  }
}

export async function 处理旧队列指令(formData: FormData) {
  const projectId = normalizeMessageFormValue(formData.get("project_id"));
  const messageId = normalizeMessageFormValue(formData.get("message_id"));
  const decision = text(formData.get("decision"), "keep");
  const reviewerNote = text(formData.get("reviewer_note"), "");
  const targetRecipientType = text(formData.get("target_recipient_type"), "workstation") || "workstation";
  const targetRecipientId = normalizeMessageFormValue(formData.get("target_recipient_id"));
  const returnTo = projectId
    ? normalizeProjectReturnPath(projectId, formData.get("return_to"), "exchange")
    : null;
  try {
    if (!projectId || !messageId) {
      throw new Error("处理旧队列需要项目和消息 ID。");
    }
    const { currentUser, project } = await ensureProjectCollaborationAccess(projectId);
    const currentUserId = normalizeMessageFormValue(currentUser?.id) ?? normalizeMessageFormValue(currentUser?.email);
    const messagesResult = await getJson(
      `/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&limit=200`,
    );
    const messages = asArray<Record<string, unknown>>(messagesResult?.data ?? messagesResult);
    const sourceMessage = messages.find((item) => text(item.id, "") === messageId);
    if (!sourceMessage) {
      throw new Error("没有找到这条旧队列指令，可能已被处理或当前账号没有权限。");
    }
    const messageType = text(sourceMessage.message_type, "").toLowerCase();
    const currentStatus = text(sourceMessage.status, "").toLowerCase();
    if (!["queued", "pending", "open", "routed"].includes(currentStatus)) {
      throw new Error(`这条队列已经是 ${currentStatus || "未知状态"}，不能重复按旧队列处理。`);
    }

    const sourceTitle = text(sourceMessage.title, "旧队列指令");
    const sourceTargetType = text(sourceMessage.recipient_type, "") || "workstation";
    const sourceTargetId = text(sourceMessage.recipient_id, "");
    const decisionLines = [
      `队列消息: ${messageId}`,
      `原状态: ${currentStatus || "unknown"}`,
      `原类型: ${messageType || "unknown"}`,
      `原目标: ${sourceTargetType}:${sourceTargetId || "未指定"}`,
      reviewerNote ? `处理备注: ${reviewerNote}` : "",
    ].filter(Boolean);

    if (decision === "expire") {
      await patchJson(`/api/collaboration/messages/${encodeURIComponent(messageId)}`, {
        status: "expired",
      });
      await postJson("/api/collaboration/messages", {
        project_id: projectId,
        message_type: "queue_review_decision",
        title: `已标记过期：${sourceTitle}`.slice(0, 300),
        body: ["人工处理旧队列：标记过期，不重派，不删除。", ...decisionLines].join("\n"),
        sender_type: "human",
        sender_id: currentUserId,
        recipient_type: "project",
        recipient_id: projectId,
        status: "closed",
      });
      revalidateProjectSurfaces(projectId);
      redirect(withQueryValue(returnTo ?? `/projects/${projectId}?panel=team&tab=exchange`, "team_notice", "已把这条旧队列标记为过期，没有删除，也没有重派。"));
    }

    if (decision === "requeue") {
      if (!targetRecipientId) {
        throw new Error("重派旧队列必须选择新的目标线程或 NPC。");
      }
      if (!["agent_command", "requirement_dispatch"].includes(messageType)) {
        throw new Error("当前只允许重派 AI 指令或需求派单；线程扫描类旧队列请先标记过期后重新扫描。");
      }
      const requeuePayload = withAiRequiredRequirementLedger(
        {
          project_id: projectId,
          task_id: text(sourceMessage.task_id, "") || null,
          approval_id: text(sourceMessage.approval_id, "") || null,
          handoff_id: text(sourceMessage.handoff_id, "") || null,
          requirement_id: text(sourceMessage.requirement_id, "") || null,
          agent_id: text(sourceMessage.agent_id, "") || null,
          message_type: messageType,
          title: `重派：${sourceTitle}`.slice(0, 300),
          body: [
            "这是人工确认后的旧队列重派，不是平台自动重复派发。",
            `旧队列消息: ${messageId}`,
            `原目标: ${sourceTargetType}:${sourceTargetId || "未指定"}`,
            reviewerNote ? `重派备注: ${reviewerNote}` : "",
            "",
            "原始指令:",
            text(sourceMessage.body, ""),
          ].filter(Boolean).join("\n"),
          sender_type: "human",
          sender_id: currentUserId,
          recipient_type: targetRecipientType,
          recipient_id: targetRecipientId,
          status: "queued",
        },
        resolveAiRequiredLedgerOptions(
          project as Record<string, unknown>,
          {
            project_id: projectId,
            task_id: text(sourceMessage.task_id, "") || null,
            approval_id: text(sourceMessage.approval_id, "") || null,
            handoff_id: text(sourceMessage.handoff_id, "") || null,
            requirement_id: text(sourceMessage.requirement_id, "") || null,
            agent_id: text(sourceMessage.agent_id, "") || null,
            message_type: messageType,
            title: `重派：${sourceTitle}`.slice(0, 300),
            body: text(sourceMessage.body, ""),
            sender_type: "human",
            sender_id: currentUserId,
            recipient_type: targetRecipientType,
            recipient_id: targetRecipientId,
            status: "queued",
          },
          currentUserId,
          null,
        ),
      );
      await postJson("/api/collaboration/messages", requeuePayload);
      await patchJson(`/api/collaboration/messages/${encodeURIComponent(messageId)}`, {
        status: "superseded",
      });
      await postJson("/api/collaboration/messages", {
        project_id: projectId,
        message_type: "queue_review_decision",
        title: `已重派旧队列：${sourceTitle}`.slice(0, 300),
        body: [
          "人工处理旧队列：已生成一条新的 queued 指令，旧指令标记为 superseded。",
          ...decisionLines,
          `新目标: ${targetRecipientType}:${targetRecipientId}`,
        ].join("\n"),
        sender_type: "human",
        sender_id: currentUserId,
        recipient_type: "project",
        recipient_id: projectId,
        status: "closed",
      });
      revalidateProjectSurfaces(projectId);
      redirect(withQueryValue(returnTo ?? `/projects/${projectId}?panel=team&tab=exchange`, "team_notice", "已人工重派旧队列，并把旧指令标记为已替代。"));
    }

    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      message_type: "queue_review_decision",
      title: `继续保留旧队列：${sourceTitle}`.slice(0, 300),
      body: ["人工处理旧队列：继续保留等待，不改状态，不重派。", ...decisionLines].join("\n"),
      sender_type: "human",
      sender_id: currentUserId,
      recipient_type: "project",
      recipient_id: projectId,
      status: "closed",
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo ?? `/projects/${projectId}?panel=team&tab=exchange`, "team_notice", "已记录：这条旧队列继续保留等待。"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "处理旧队列失败";
    if (returnTo) {
      redirect(withQueryValue(returnTo, "team_error", message));
    }
    throw error;
  }
}

export async function 启动Npc接力协作(formData: FormData) {
  const projectId = normalizeMessageFormValue(formData.get("project_id"));
  const returnTo = projectId
    ? normalizeProjectReturnPath(projectId, formData.get("return_to"), "exchange")
    : null;
  try {
    if (!projectId) {
      throw new Error("平台接力协作必须带项目上下文。");
    }
    const access = await ensureProjectCollaborationAccess(projectId);
    const project = access.project as Record<string, unknown>;
    const firstWorkstationId = normalizeMessageFormValue(formData.get("first_recipient_id"));
    const secondWorkstationId = normalizeMessageFormValue(formData.get("second_recipient_id"));
    const firstProviderId = resolveProjectWorkstationProviderId(
      project,
      firstWorkstationId,
      normalizePlatformProviderId(formData.get("first_provider_id")) || "codex",
    );
    const secondProviderId = resolveProjectWorkstationProviderId(
      project,
      secondWorkstationId,
      normalizePlatformProviderId(formData.get("second_provider_id")) || "claude",
    );
    const title = normalizeMessageFormValue(formData.get("title")) ?? "平台多 NPC 接力协作";
    const objective = String(formData.get("objective") ?? "").trim();
    if (!firstWorkstationId || !secondWorkstationId) {
      throw new Error("请先选择第一棒和第二棒 NPC / 线程。");
    }
    if (!objective) {
      throw new Error("请写清楚这次接力协作要完成的目标。");
    }
    const relayId = `relay-${Date.now().toString(36)}`;
    await postNpcRelayStatus({
      projectId,
      relayId,
      title,
      objective,
      firstWorkstationId,
      firstProviderId,
      secondWorkstationId,
      secondProviderId,
      status: "pending",
    });
    const launchResult = launchDetachedNpcRelay({
      projectId,
      relayId,
      firstWorkstationId,
      firstProviderId,
      secondWorkstationId,
      secondProviderId,
      title,
      objective,
    });
    await postNpcRelayStatus({
      projectId,
      relayId,
      title,
      objective,
      firstWorkstationId,
      firstProviderId,
      secondWorkstationId,
      secondProviderId,
      status: launchResult.launched ? "running" : "failed",
      stdoutPath: launchResult.stdoutPath,
      stderrPath: launchResult.stderrPath,
      launchError: launchResult.error ?? null,
    });
    revalidatePath("/base");
    revalidatePath("/collaborators");
    revalidatePath(`/projects/${projectId}`);
    if (returnTo) {
      const firstLabel = platformProviderLabel(firstProviderId);
      const secondLabel = platformProviderLabel(secondProviderId);
      const notice = launchResult.launched
        ? `已启动平台多 NPC 接力：${firstLabel} -> ${secondLabel}，回执会陆续进入结果区。`
        : `多 NPC 接力未能拉起：${launchResult.error ?? "请检查本机 Python 和脚本路径"}`;
      redirect(withQueryValue(returnTo, launchResult.launched ? "team_notice" : "team_error", notice));
    }
  } catch (error) {
    rethrowRedirectError(error);
    if (returnTo) {
      const message = error instanceof Error ? error.message : "启动平台多 NPC 接力失败";
      redirect(withQueryValue(returnTo, "team_error", message));
    }
    throw error;
  }
}

type GameCollabSeat = {
  id: string;
  name: string;
  metadata: Record<string, unknown>;
};

function resolveGameCollabSeatId(seat: Record<string, unknown>) {
  return (
    text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, "") ||
    text(seat.source_workstation_id ?? readRecord(seat.metadata).source_workstation_id, "")
  );
}

function findFrontCGameSeat(seats: Record<string, unknown>[], slot: "7" | "8"): GameCollabSeat | null {
  const threadHint =
    slot === "7"
      ? "019e8121-ee19-77d2-b391-200ffbc6dad5"
      : "019e8122-6868-7222-9a71-c2eab2483dd7";
  const matched = seats.find((seat) => {
    const metadata = readRecord(seat.metadata);
    const name = text(seat.name ?? seat.workstation_name, "");
    const haystack = [
      name,
      seat.id,
      seat.row_id,
      seat.config_id,
      seat.source_workstation_id,
      metadata.source_workstation_id,
      metadata.automation_thread_id,
      metadata.codex_thread_id,
    ].map((value) => text(value, "")).join(" ");
    return haystack.includes(threadHint) || name.replace(/\s+/g, "").includes(`前端C${slot}号`);
  });
  if (!matched) return null;
  const id = resolveGameCollabSeatId(matched);
  if (!id) return null;
  return {
    id,
    name: text(matched.name ?? matched.workstation_name, `前端 C ${slot}号`),
    metadata: readRecord(matched.metadata),
  };
}

function gameCollabAutonomyCopy(mode: string) {
  if (mode === "full") {
    return {
      label: "完全自主",
      automationEnabled: true,
      review: "允许连续规划、实现、联调和自检；删除、reset、发布、部署、跨账号凭据、长期费用扩大必须停下等人确认。",
      cadence: "完成一个小闭环后继续下一轮，直到用户暂停或明确验收完成。",
    };
  }
  if (mode === "checkpoint") {
    return {
      label: "检查点模式",
      automationEnabled: true,
      review: "可以连续做只读分析、局部实现和测试；每个可玩版本、风险 Git 操作、部署动作前请回平台请求确认。",
      cadence: "先做 MVP，再按检查点给用户看可玩变化和下一步建议。",
    };
  }
  return {
    label: "监督模式",
    automationEnabled: false,
    review: "每一阶段只推进一轮，方案、实现、测试、方向调整都要回平台等用户确认。",
    cadence: "先给计划和最小改动建议，不要私下连续推进。",
  };
}

async function updateGameCollabAutonomy(projectId: string, seat: GameCollabSeat, mode: string) {
  const autonomy = gameCollabAutonomyCopy(mode);
  await patchJson(`/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(seat.id)}`, {
    metadata: {
      ...seat.metadata,
      automation_enabled: autonomy.automationEnabled,
      game_collab_autonomy_mode: mode,
      game_collab_autonomy_label: autonomy.label,
      game_collab_updated_at: new Date().toISOString(),
    },
  });
}

function buildGameCollabPrompt(options: {
  runId: string;
  brief: string;
  autonomyMode: string;
  targetRole: "gameplay" | "qa";
  partnerName: string;
  isInjection?: boolean;
}) {
  const autonomy = gameCollabAutonomyCopy(options.autonomyMode);
  const roleLine =
    options.targetRole === "gameplay"
      ? "你是 7 号，主负责小游戏玩法、前端交互、可玩原型和用户体验。"
      : "你是 8 号，主负责集成、测试、验收标准、风险发现和给 7 号提结构化修改需求。";
  return [
    `协作项目：小游戏双 NPC 开发 / ${options.runId}`,
    `用户最新目标：${options.brief}`,
    `自主级别：${autonomy.label}`,
    `协作伙伴：${options.partnerName}`,
    "",
    roleLine,
    `自治边界：${autonomy.review}`,
    `推进节奏：${autonomy.cadence}`,
    "",
    options.isInjection
      ? "这是用户中途插入的新需求。请先判断对当前设计/代码/测试的影响，再给出你负责的调整和需要伙伴配合的 Need。"
      : "请先给最小可玩方案，再进入实现/测试分工。每轮回复要说明：你做了什么、需要伙伴做什么、用户现在能控制什么。",
    "NPC 间协作要求：如果需要伙伴处理，不要私下隐藏沟通；请在平台沉淀结构化 Need/Task 线索，回执里写明交付物、风险和下一步。",
    "用户可控要求：保留暂停、改方向、收窄范围、提高/降低自主级别的空间。遇到破坏性 Git、部署、删除、长期消耗扩大，必须停下请求确认。",
  ].join("\n");
}

async function postGameCollabCommand(options: {
  projectId: string;
  seat: GameCollabSeat;
  title: string;
  body: string;
  actorId: string;
  runId: string;
  autonomyMode: string;
  kind: "start" | "injection";
}) {
  const messageResult = await postJson("/api/collaboration/messages", {
    project_id: options.projectId,
    agent_id: options.seat.id,
    message_type: "agent_command",
    title: options.title,
    body: options.body,
    sender_type: "human",
    sender_id: options.actorId,
    recipient_type: "thread_workstation",
    recipient_id: options.seat.id,
    status: "queued",
    metadata: {
      source: "front_c_game_collab",
      game_collab_run_id: options.runId,
      game_collab_kind: options.kind,
      autonomy_mode: options.autonomyMode,
    },
  });
  const messageRecord = objectRecord(messageResult);
  const messageData = objectRecord(messageRecord.data);
  const messageId = text(messageData.id ?? messageRecord.id, "");
  if (!messageId) {
    throw new Error(`已登记 ${options.seat.name} 平台消息，但消息接口没有返回 ID，不能继续送到桌面线程。`);
  }
  await postJson(`/api/collaboration/projects/${options.projectId}/runner-commands`, {
    title: `NPC 派工：${options.title}`,
    body: JSON.stringify(
      {
        kind: "codex.desktop.dispatch",
        project_id: options.projectId,
        workstation_id: options.seat.id,
        message_id: messageId,
        provider_id: "codex",
        title: options.title,
      },
      null,
      2,
    ),
    workstation_id: options.seat.id,
    metadata: {
      source: "front_c_game_collab",
      source_message_id: messageId,
      target_workstation_id: options.seat.id,
      delivery_mode: "codex_desktop_ui",
      desktop_delivery_policy: "automation",
      desktop_delivery_method: "codex_desktop_automation",
      game_collab_run_id: options.runId,
      game_collab_kind: options.kind,
    },
  });
  await postJson("/api/collaboration/messages", {
    project_id: options.projectId,
    agent_id: options.seat.id,
    message_type: "agent_ack",
    title: `等待桌面后台接收 / ${options.seat.name}`,
    body: [
      `平台已把 ${options.seat.name} 的小游戏协作指令送入执行电脑队列。`,
      `派单消息：${messageId}`,
      "投递方式：Codex 桌面后台自动化，不抢焦点、不点窗口、不用剪贴板。",
      "下一步状态应该进入等待桌面接收或等待桌面回复；不能把平台 ack 当成桌面已收到。",
    ].join("\n"),
    sender_type: "agent",
    sender_id: options.seat.id,
    recipient_type: "thread_workstation",
    recipient_id: options.seat.id,
    status: "in_progress",
    metadata: {
      source: "front_c_game_collab",
      source_message_id: messageId,
      delivery_mode: "codex_desktop_ui",
      desktop_delivery_policy: "automation",
      progress_state: "awaiting_desktop_pickup",
      game_collab_run_id: options.runId,
      game_collab_kind: options.kind,
    },
  });
}

async function createGameCollabNeed(options: {
  projectId: string;
  from: GameCollabSeat;
  to: GameCollabSeat;
  title: string;
  context: string;
  expected: string;
  runId: string;
}) {
  await postJson("/api/requirements", {
    project_id: options.projectId,
    title: options.title,
    requirement_type: "npc_collaboration",
    module: "game-collab",
    priority: "high",
    status: "waiting_response",
    from_agent: options.from.id,
    to_agent: options.to.id,
    context_summary: options.context,
    expected_output: options.expected,
    related_files: [],
    max_response_tokens: 3000,
    opening_message: `小游戏协作线：${options.runId}`,
  });
}

export async function 发起前端C小游戏协作(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "company");
  try {
    const { currentUser } = await ensureProjectCollaborationAccess(projectId);
    const workstationsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const seats = asArray<Record<string, unknown>>(workstationsResult?.data ?? workstationsResult);
    const seat7 = findFrontCGameSeat(seats, "7");
    const seat8 = findFrontCGameSeat(seats, "8");
    if (!seat7 || !seat8) throw new Error("没有找到前端 C 7号 / 8号，请先确认两个 NPC 已绑定。");

    const brief =
      text(formData.get("brief"), "") ||
      "做一个可玩 2D 小游戏：玩家移动、收集星星、避开障碍，先做 MVP，再根据用户插入需求调整方向。";
    const autonomyMode = text(formData.get("autonomy_mode"), "checkpoint");
    const runId = `game-collab-${Date.now().toString(36)}`;
    const actorId = text(currentUser?.id ?? currentUser?.email, "human-chief");

    await updateGameCollabAutonomy(projectId, seat7, autonomyMode);
    await updateGameCollabAutonomy(projectId, seat8, autonomyMode);
    await postGameCollabCommand({
      projectId,
      seat: seat7,
      title: "小游戏协作启动 / 7号负责玩法原型",
      body: buildGameCollabPrompt({ runId, brief, autonomyMode, targetRole: "gameplay", partnerName: seat8.name }),
      actorId,
      runId,
      autonomyMode,
      kind: "start",
    });
    await postGameCollabCommand({
      projectId,
      seat: seat8,
      title: "小游戏协作启动 / 8号负责联调验收",
      body: buildGameCollabPrompt({ runId, brief, autonomyMode, targetRole: "qa", partnerName: seat7.name }),
      actorId,
      runId,
      autonomyMode,
      kind: "start",
    });
    await createGameCollabNeed({
      projectId,
      from: seat7,
      to: seat8,
      title: "小游戏 MVP 联调与验收",
      context: "7号先做玩法/UI 原型，8号同步建立验收标准、测试反馈和风险清单。",
      expected: "输出可玩性反馈、阻塞风险、验收结果，以及需要 7号 修改的具体点。",
      runId,
    });
    await createGameCollabNeed({
      projectId,
      from: seat8,
      to: seat7,
      title: "小游戏体验修改回路",
      context: "8号发现问题后，把测试/验收反馈转成 7号 可执行的玩法或 UI 修改。",
      expected: "7号根据反馈完成调整，并回写用户能体验到的变化。",
      runId,
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", `已启动 7号/8号 小游戏协作：${gameCollabAutonomyCopy(autonomyMode).label}`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "启动小游戏协作失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 插入前端C小游戏需求(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "company");
  try {
    const { currentUser } = await ensureProjectCollaborationAccess(projectId);
    const workstationsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const seats = asArray<Record<string, unknown>>(workstationsResult?.data ?? workstationsResult);
    const seat7 = findFrontCGameSeat(seats, "7");
    const seat8 = findFrontCGameSeat(seats, "8");
    if (!seat7 || !seat8) throw new Error("没有找到前端 C 7号 / 8号，无法插入需求。");
    const brief = text(formData.get("brief"), "");
    if (!brief) throw new Error("请先写一句要插入的新需求。");
    const autonomyMode = text(formData.get("autonomy_mode"), "checkpoint");
    const runId = text(formData.get("game_collab_run_id"), "") || `game-collab-${Date.now().toString(36)}`;
    const actorId = text(currentUser?.id ?? currentUser?.email, "human-chief");
    await updateGameCollabAutonomy(projectId, seat7, autonomyMode);
    await updateGameCollabAutonomy(projectId, seat8, autonomyMode);
    await postGameCollabCommand({
      projectId,
      seat: seat7,
      title: "用户插入需求 / 小游戏方向调整",
      body: buildGameCollabPrompt({ runId, brief, autonomyMode, targetRole: "gameplay", partnerName: seat8.name, isInjection: true }),
      actorId,
      runId,
      autonomyMode,
      kind: "injection",
    });
    await postGameCollabCommand({
      projectId,
      seat: seat8,
      title: "用户插入需求 / 联调验收调整",
      body: buildGameCollabPrompt({ runId, brief, autonomyMode, targetRole: "qa", partnerName: seat7.name, isInjection: true }),
      actorId,
      runId,
      autonomyMode,
      kind: "injection",
    });
    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", "已把新需求插入 7号/8号 的协作队列"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "插入小游戏需求失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 下发Runner命令(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "git");
  const targetMode = String(formData.get("target_mode") ?? "computer_node_id").trim() || "computer_node_id";
  const body = String(formData.get("body") ?? "").trim();
  const payload: Record<string, unknown> = {
    title: String(formData.get("title") ?? "").trim() || null,
    body,
    task_id: String(formData.get("task_id") ?? "").trim() || null,
  };
  const targetValue = String(formData.get(targetMode) ?? "").trim();
  if (!body) {
    redirect(withQueryValue(returnTo, "team_error", "请先填写要下发给电脑的命令内容"));
  }
  if (!targetValue) {
    redirect(withQueryValue(returnTo, "team_error", "当前没有可接单电脑。请先在目标电脑运行持续接单命令，等状态变成常驻接单后再派任务。"));
  }
  payload[targetMode] = targetValue;
  try {
    await postJson(`/api/collaboration/projects/${projectId}/runner-commands`, payload);
    revalidateProjectSurfaces(projectId);
    revalidatePath("/runners");
    redirect(withQueryValue(returnTo, "team_notice", "Runner 命令已下发"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "下发 Runner 命令失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 下发机器人调试命令(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "robotics");
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  const interfaceId = String(formData.get("interface_id") ?? "").trim();
  const interfaceName = String(formData.get("interface_name") ?? "").trim();
  const interfaceKind = String(formData.get("interface_kind") ?? "").trim();
  const boundNpc = String(formData.get("bound_npc") ?? "").trim();
  const boundNpcLabel = String(formData.get("bound_npc_label") ?? "").trim();
  const command = String(formData.get("command") ?? "").trim();
  if (!computerNodeId) {
    redirect(withQueryValue(returnTo, "team_error", "先选择这条调试终端所在的执行电脑"));
  }
  if (!interfaceId) {
    redirect(withQueryValue(returnTo, "team_error", "先选择一个本项目扫描到的真实调试接口"));
  }
  if (!command) {
    redirect(withQueryValue(returnTo, "team_error", "先在终端输入要执行的调试请求"));
  }
  const title = `机器人现场用户终端：${interfaceName || interfaceKind || "接口"}`;
  const body = [
    "用户本人在调试终端提交请求，请在目标电脑上执行并回写最小回执。",
    `接口类型：${interfaceKind || "待确认"}`,
    `接口名称：${interfaceName || interfaceId}`,
    boundNpc ? `协助 NPC：${boundNpcLabel || boundNpc}` : "协助 NPC：未绑定",
    `用户终端输入：${command}`,
    "权限边界：用户本人操作不走审核；NPC/AI 代操作调试终端必须先提交待审核请求，审核通过后才可下发。",
  ].join("\n");
  try {
    if (boundNpc) {
      await postJson("/api/collaboration/messages", {
        project_id: projectId,
        agent_id: boundNpc,
        title: `负责调试窗口：${interfaceName || interfaceKind || "接口"}`,
        body: [
          "用户把这个调试窗口交给你辅助观察和建议。",
          `接口类型：${interfaceKind || "待确认"}`,
          `接口名称：${interfaceName || interfaceId}`,
          `用户终端输入：${command}`,
          "你可以给调试建议、解释回执、提出下一步操作请求；涉及写入、发送、运动、固件或 ROS 写操作时，必须创建待审核请求，不能直接执行。",
        ].join("\n"),
        message_type: "robotics_terminal_context",
        sender_type: "human",
        sender_id: "robotics-terminal",
        recipient_type: "thread_workstation",
        recipient_id: boundNpc,
        status: "open",
        metadata: {
          terminal_interface_id: interfaceId,
          terminal_interface_name: interfaceName,
          terminal_interface_kind: interfaceKind,
          terminal_bound_npc_id: boundNpc,
          terminal_bound_npc: boundNpcLabel || boundNpc,
          terminal_command: command,
          terminal_mode: "npc_assist",
          terminal_surface: "robotics",
          computer_node_id: computerNodeId,
        },
      });
    }
    await postJson(`/api/collaboration/projects/${projectId}/runner-commands`, {
      title,
      body,
      computer_node_id: computerNodeId,
      metadata: {
        terminal_interface_id: interfaceId,
        terminal_interface_name: interfaceName,
        terminal_interface_kind: interfaceKind,
        terminal_bound_npc_id: boundNpc || null,
        terminal_bound_npc: boundNpcLabel || boundNpc || null,
        terminal_command: command,
        terminal_mode: "user_terminal",
        terminal_surface: "robotics",
      },
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/robotics`);
    redirect(withQueryValue(returnTo, "team_notice", "用户终端请求已排队到所选执行电脑；保持 runner 接单窗口打开，回执会回到平台"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "调试命令排队失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

function safeArtifactSlug(value: unknown, fallback = "item") {
  const raw = String(value ?? "").trim().toLowerCase();
  const slug = raw.replace(/[^a-z0-9_.-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
  return slug || fallback;
}

function roboticsCaptureManifestPath(projectId: string, interfaceId: string, captureId: string) {
  return path.join(
    workspaceRoot(),
    "artifacts",
    "robotics-captures",
    safeArtifactSlug(projectId, "project"),
    safeArtifactSlug(interfaceId, "interface"),
    `${safeArtifactSlug(captureId, "capture")}.json`,
  );
}

function roboticsDerivedArtifactPath(projectId: string, interfaceId: string, kind: string, artifactId: string, extension = "json") {
  return path.join(
    workspaceRoot(),
    "artifacts",
    "robotics-derived",
    safeArtifactSlug(projectId, "project"),
    safeArtifactSlug(interfaceId, "interface"),
    safeArtifactSlug(kind, "artifact"),
    `${safeArtifactSlug(artifactId, "artifact")}.${safeArtifactSlug(extension, "json")}`,
  );
}

function splitFormList(value: FormDataEntryValue | FormDataEntryValue[] | null | undefined) {
  const values = Array.isArray(value) ? value : value == null ? [] : [value];
  return values
    .flatMap((item) => String(item ?? "").split(/[\n,，]+/))
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseRoboticsManualLabels(value: unknown) {
  return String(value ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 200)
    .map((line, index) => {
      const parts = line.split(/[,，|]/).map((part) => part.trim());
      const [captureId, variable, start, end, label, ...noteParts] = parts;
      return {
        row: index + 1,
        capture_id: captureId || "",
        variable: variable || "",
        start: start || "",
        end: end || "",
        label: label || line,
        note: noteParts.join(" / "),
        raw: line,
      };
    });
}

function roboticsNumericSummaryRows(
  runnerSummaries: Record<string, unknown>,
  captureIds: string[],
  variables: string[],
  labelSchema: string,
  labelNotes: string,
) {
  const selected = new Set(variables.map((item) => String(item ?? "").trim()).filter(Boolean));
  return captureIds.flatMap((captureId) => {
    const summary = runnerSummaries[captureId];
    const previewSummary = summary && typeof summary === "object"
      ? (summary as Record<string, unknown>).preview_summary
      : null;
    const numericFields = previewSummary && typeof previewSummary === "object"
      ? (previewSummary as Record<string, unknown>).numeric_fields
      : null;
    if (!numericFields || typeof numericFields !== "object") return [];
    return Object.entries(numericFields as Record<string, unknown>)
      .filter(([variable]) => !selected.size || selected.has(variable))
      .flatMap(([variable, rawStats]) => {
        const stats = rawStats && typeof rawStats === "object" ? rawStats as Record<string, unknown> : {};
        return ["count", "min", "max", "mean", "first", "last"].map((statistic) => ({
          capture_id: captureId,
          variable,
          statistic,
          value: String(stats[statistic] ?? ""),
          label_schema: labelSchema,
          label: labelSchema,
          start: "",
          end: "",
          note: labelNotes,
          source: "runner_numeric_summary",
        })).filter((row) => row.value !== "");
      });
  });
}

async function writeRoboticsDerivedArtifact(options: {
  projectId: string;
  interfaceId: string;
  kind: string;
  artifactId: string;
  extension?: string;
  payload: Record<string, unknown>;
  csvRows?: string[][];
}) {
  const filePath = roboticsDerivedArtifactPath(options.projectId, options.interfaceId, options.kind, options.artifactId, options.extension ?? "json");
  const relativePath = path.relative(workspaceRoot(), filePath).replace(/\\/g, "/");
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  if (options.extension === "csv" && options.csvRows?.length) {
    const csv = options.csvRows
      .map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(","))
      .join("\n");
    await fs.writeFile(filePath, `${csv}\n`, "utf8");
  } else if (options.extension === "jsonl" && options.csvRows?.length) {
    const [header, ...rows] = options.csvRows;
    const jsonl = rows
      .map((row) => Object.fromEntries(header.map((key, index) => [key, row[index] ?? ""])))
      .map((record) => JSON.stringify(record))
      .join("\n");
    await fs.writeFile(filePath, `${jsonl}\n`, "utf8");
  } else {
    await fs.writeFile(filePath, `${JSON.stringify({ ...options.payload, artifact_path: relativePath }, null, 2)}\n`, "utf8");
  }
  return relativePath;
}

async function writeRoboticsCaptureManifest(options: {
  projectId: string;
  captureId: string;
  interfaceId: string;
  interfaceName: string;
  interfaceKind: string;
  computerNodeId: string;
  boundNpc: string;
  boundNpcLabel: string;
  sampleHz: string;
  channels: string[];
  startedAt: string;
  stoppedAt: string;
}) {
  const filePath = roboticsCaptureManifestPath(options.projectId, options.interfaceId, options.captureId);
  const relativePath = path.relative(workspaceRoot(), filePath).replace(/\\/g, "/");
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const manifest = {
    schema: "robotics_capture_manifest_v1",
    project_id: options.projectId,
    capture_id: options.captureId,
    interface_id: options.interfaceId,
    interface_name: options.interfaceName,
    interface_kind: options.interfaceKind,
    computer_node_id: options.computerNodeId,
    bound_npc_id: options.boundNpc || null,
    bound_npc: options.boundNpcLabel || options.boundNpc || null,
    sample_hz: options.sampleHz,
    channels: options.channels,
    started_at: options.startedAt,
    stopped_at: options.stoppedAt,
    artifact_path: relativePath,
    notes: [
      "This manifest is the platform capture segment index for the device data workbench.",
      "Raw device files can be attached later by runner receipts under the same capture_id.",
      "Use GitHub/repo-relative artifact evidence, not a private local path, as shared truth.",
    ],
  };
  await fs.writeFile(filePath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return relativePath;
}

async function findLatestRoboticsCaptureStart(projectId: string, interfaceId: string) {
  try {
    const result = await getJson(`/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&limit=160`);
    const rows = Array.isArray(result?.data) ? result.data : Array.isArray(result) ? result : [];
    const completedCaptureIds = new Set<string>();
    for (const row of rows) {
      const extra = row && typeof row === "object" ? (row.extra_data ?? row.metadata ?? {}) : {};
      if (!extra || typeof extra !== "object") continue;
      if (String(extra.terminal_interface_id ?? "").trim() !== interfaceId) continue;
      if (String(row.message_type ?? row.messageType ?? "").trim() !== "robotics_capture_segment") continue;
      const captureId = String(extra.capture_id ?? "").trim();
      if (captureId) completedCaptureIds.add(captureId);
    }
    for (const row of rows) {
      const extra = row && typeof row === "object" ? (row.extra_data ?? row.metadata ?? {}) : {};
      if (!extra || typeof extra !== "object") continue;
      if (String(row.message_type ?? row.messageType ?? "").trim() !== "robotics_capture_start") continue;
      if (String(extra.terminal_interface_id ?? "").trim() !== interfaceId) continue;
      const captureId = String(extra.capture_id ?? "").trim();
      if (!captureId || completedCaptureIds.has(captureId)) continue;
      return {
        captureId,
        startedAt: String(extra.started_at ?? row.created_at ?? row.createdAt ?? "").trim(),
        sampleHz: String(extra.capture_sample_hz ?? "").trim(),
        channels: Array.isArray(extra.capture_channels) ? (extra.capture_channels as unknown[]).map((item) => String(item ?? "").trim()).filter(Boolean) : [],
      };
    }
  } catch {
    return null;
  }
  return null;
}

async function collectRoboticsCaptureRunnerSummaries(projectId: string, interfaceId: string, captureIds: string[]) {
  const wanted = new Set(captureIds.map((item) => String(item ?? "").trim()).filter(Boolean));
  if (!wanted.size) return {};
  const summaries: Record<string, unknown> = {};
  try {
    const result = await getJson(`/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&limit=240`);
    const rows = Array.isArray(result?.data) ? result.data : Array.isArray(result) ? result : [];
    for (const row of rows) {
      if (String(row?.message_type ?? row?.messageType ?? "").trim() !== "runner_result") continue;
      const extra = row && typeof row === "object" ? (row.extra_data ?? row.metadata ?? {}) : {};
      if (!extra || typeof extra !== "object") continue;
      if (String((extra as Record<string, unknown>).terminal_interface_id ?? "").trim() !== interfaceId) continue;
      const runnerResult = (extra as Record<string, unknown>).runner_result;
      if (!runnerResult || typeof runnerResult !== "object") continue;
      const captureId = String((runnerResult as Record<string, unknown>).capture_id ?? (extra as Record<string, unknown>).capture_id ?? "").trim();
      if (!captureId || !wanted.has(captureId)) continue;
      summaries[captureId] = {
        sample_count: (runnerResult as Record<string, unknown>).sample_count ?? null,
        byte_count: (runnerResult as Record<string, unknown>).byte_count ?? null,
        preview_summary: (runnerResult as Record<string, unknown>).preview_summary ?? null,
        preview_points: (runnerResult as Record<string, unknown>).preview_points ?? null,
        repo_sync: (runnerResult as Record<string, unknown>).repo_sync ?? null,
        local_cache: (runnerResult as Record<string, unknown>).local_cache ?? null,
      };
    }
  } catch {
    return summaries;
  }
  return summaries;
}

export async function 记录机器人采集片段(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "robotics");
  const mode = String(formData.get("capture_mode") ?? "").trim();
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  const interfaceId = String(formData.get("interface_id") ?? "").trim();
  const runnerInterfaceId = String(formData.get("runner_interface_id") ?? "").trim() || interfaceId;
  const interfaceName = String(formData.get("interface_name") ?? "").trim();
  const interfaceKind = String(formData.get("interface_kind") ?? "").trim();
  const boundNpc = String(formData.get("bound_npc") ?? "").trim();
  const boundNpcLabel = String(formData.get("bound_npc_label") ?? "").trim();
  const sampleHz = String(formData.get("sample_hz") ?? "100").trim() || "100";
  const baudRate = String(formData.get("baud_rate") ?? "115200").trim() || "115200";
  const channels = String(formData.get("channels") ?? "")
    .split(/[\n,，]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (!computerNodeId || !interfaceId) {
    redirect(withQueryValue(returnTo, "team_error", "采集需要先选择真实执行电脑和调试接口"));
  }
  if (!["start", "stop"].includes(mode)) {
    redirect(withQueryValue(returnTo, "team_error", "请选择开始采集或停止采集"));
  }

  const now = new Date();
  const timestamp = now.toISOString();
  const latestStart = mode === "stop" ? await findLatestRoboticsCaptureStart(projectId, interfaceId) : null;
  const captureSeed = `${projectId}:${interfaceId}:${timestamp}:${sampleHz}:${channels.join(",")}`;
  const captureId = latestStart?.captureId || `capture-${createHash("sha1").update(captureSeed).digest("hex").slice(0, 12)}`;
  const channelList = channels.length ? channels : ["time", "motor.current", "motor.velocity", "sensor.temperature", "bus.frame"];
  const effectiveChannels = latestStart?.channels?.length ? latestStart.channels : channelList;
  const effectiveSampleHz = latestStart?.sampleHz || sampleHz;
  try {
    if (mode === "start") {
      const commandBody = JSON.stringify({
        kind: "robotics.capture.start",
        project_id: projectId,
        capture_id: captureId,
        interface_id: runnerInterfaceId,
        interface_name: interfaceName,
        interface_kind: interfaceKind,
        computer_node_id: computerNodeId,
        sample_hz: sampleHz,
        baud_rate: baudRate,
        channels: channelList,
        readonly: true,
      });
      await postJson("/api/collaboration/messages", {
        project_id: projectId,
        agent_id: boundNpc || null,
        title: `开始采集：${interfaceName || interfaceKind || "调试接口"}`,
        body: [
          "用户在设备数据工作台启动采集。",
          `接口类型：${interfaceKind || "待确认"}`,
          `接口名称：${interfaceName || interfaceId}`,
          `采样频率：${sampleHz} Hz`,
          `串口波特率：${baudRate}`,
          `采集通道：${channelList.join("、")}`,
          "停止采集后会在同一调试瓷砖的数据标注和图表实验里生成采集片段索引。",
        ].join("\n"),
        message_type: "robotics_capture_start",
        sender_type: "human",
        sender_id: "robotics-terminal",
        recipient_type: boundNpc ? "thread_workstation" : "project",
        recipient_id: boundNpc || projectId,
        status: "running",
        metadata: {
          terminal_interface_id: interfaceId,
          terminal_interface_name: interfaceName,
          terminal_interface_kind: interfaceKind,
          terminal_bound_npc_id: boundNpc || null,
          terminal_bound_npc: boundNpcLabel || boundNpc || null,
          terminal_surface: "robotics",
          capture_id: captureId,
          capture_mode: "start",
          capture_sample_hz: sampleHz,
          capture_baud_rate: baudRate,
          capture_channels: channelList,
          computer_node_id: computerNodeId,
          started_at: timestamp,
        },
      });
      await postJson(`/api/collaboration/projects/${projectId}/runner-commands`, {
        title: `开始采集：${interfaceName || interfaceKind || "调试接口"}`,
        body: commandBody,
        computer_node_id: computerNodeId,
        metadata: {
          terminal_interface_id: interfaceId,
          terminal_interface_name: interfaceName,
          terminal_interface_kind: interfaceKind,
          terminal_bound_npc_id: boundNpc || null,
          terminal_bound_npc: boundNpcLabel || boundNpc || null,
          terminal_surface: "robotics",
          terminal_mode: "capture_start",
          capture_id: captureId,
          capture_sample_hz: sampleHz,
          capture_baud_rate: baudRate,
          capture_channels: channelList,
          computer_node_id: computerNodeId,
          started_at: timestamp,
        },
      });
      revalidateProjectSurfaces(projectId);
      revalidatePath(`/projects/${projectId}/robotics`);
      redirect(withQueryValue(returnTo, "team_notice", "采集请求已排队到目标电脑；停止后会生成采集片段索引"));
    }

    const artifactPath = await writeRoboticsCaptureManifest({
      projectId,
      captureId,
      interfaceId,
      interfaceName,
      interfaceKind,
      computerNodeId,
      boundNpc,
      boundNpcLabel,
      sampleHz: effectiveSampleHz,
      channels: effectiveChannels,
      startedAt: latestStart?.startedAt || timestamp,
      stoppedAt: timestamp,
    });
    const commandBody = JSON.stringify({
      kind: "robotics.capture.stop",
      project_id: projectId,
      capture_id: captureId,
      interface_id: runnerInterfaceId,
      interface_name: interfaceName,
      interface_kind: interfaceKind,
      computer_node_id: computerNodeId,
      sample_hz: effectiveSampleHz,
      baud_rate: baudRate,
      channels: effectiveChannels,
      platform_artifact_path: artifactPath,
      readonly: true,
    });
    await postJson(`/api/collaboration/projects/${projectId}/runner-commands`, {
      title: `停止采集：${interfaceName || interfaceKind || "调试接口"}`,
      body: commandBody,
      computer_node_id: computerNodeId,
      metadata: {
        terminal_interface_id: interfaceId,
        terminal_interface_name: interfaceName,
        terminal_interface_kind: interfaceKind,
        terminal_bound_npc_id: boundNpc || null,
        terminal_bound_npc: boundNpcLabel || boundNpc || null,
        terminal_surface: "robotics",
        terminal_mode: "capture_stop",
        capture_id: captureId,
        capture_sample_hz: effectiveSampleHz,
        capture_baud_rate: baudRate,
        capture_channels: effectiveChannels,
        computer_node_id: computerNodeId,
        stopped_at: timestamp,
        artifact_path: artifactPath,
        artifact_refs: [{ label: "采集片段 manifest", path: artifactPath }],
        evidence_artifacts: [{ label: "采集片段 manifest", path: artifactPath }],
      },
    });
    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      agent_id: boundNpc || null,
      title: `采集片段：${interfaceName || interfaceKind || "调试接口"}`,
      body: [
        "设备数据工作台生成了一个采集片段索引。",
        `接口类型：${interfaceKind || "待确认"}`,
        `接口名称：${interfaceName || interfaceId}`,
        `采样频率：${effectiveSampleHz} Hz`,
        `串口波特率：${baudRate}`,
        `采集通道：${effectiveChannels.join("、")}`,
        `证据文件：${artifactPath}`,
        "这个片段会出现在同一瓷砖的数据标注和图表实验 tab，可继续预标注、导出数据集或画图分析。",
      ].join("\n"),
      message_type: "robotics_capture_segment",
      sender_type: "human",
      sender_id: "robotics-terminal",
      recipient_type: boundNpc ? "thread_workstation" : "project",
      recipient_id: boundNpc || projectId,
      status: "captured",
      metadata: {
        terminal_interface_id: interfaceId,
        terminal_interface_name: interfaceName,
        terminal_interface_kind: interfaceKind,
        terminal_bound_npc_id: boundNpc || null,
        terminal_bound_npc: boundNpcLabel || boundNpc || null,
        terminal_surface: "robotics",
        capture_id: captureId,
        capture_mode: "segment",
        capture_sample_hz: effectiveSampleHz,
        capture_baud_rate: baudRate,
        capture_channels: effectiveChannels,
        computer_node_id: computerNodeId,
        started_at: latestStart?.startedAt || timestamp,
        stopped_at: timestamp,
        artifact_path: artifactPath,
        artifact_refs: [{ label: "采集片段 manifest", path: artifactPath }],
        evidence_artifacts: [{ label: "采集片段 manifest", path: artifactPath }],
      },
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/robotics`);
    redirect(withQueryValue(returnTo, "team_notice", "已生成采集片段；数据标注和图表实验可直接选择它"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "记录采集片段失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 创建机器人数据预标注请求(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "robotics");
  const interfaceId = String(formData.get("interface_id") ?? "").trim();
  const interfaceName = String(formData.get("interface_name") ?? "").trim();
  const interfaceKind = String(formData.get("interface_kind") ?? "").trim();
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  const boundNpc = String(formData.get("bound_npc") ?? "").trim();
  const boundNpcLabel = String(formData.get("bound_npc_label") ?? "").trim();
  const captureIds = splitFormList(formData.getAll("capture_ids"));
  const captureTitles = splitFormList(formData.get("capture_titles"));
  const variables = splitFormList(formData.getAll("variables"));
  const labelSchema = String(formData.get("label_schema") ?? "").trim();
  const labelGoal = String(formData.get("label_goal") ?? "").trim();
  if (!interfaceId || !computerNodeId) {
    redirect(withQueryValue(returnTo, "team_error", "请先在真实接口瓷砖里发起数据预标注"));
  }
  if (!captureIds.length) {
    redirect(withQueryValue(returnTo, "team_error", "请先选择至少一个采集片段"));
  }
  if (!variables.length) {
    redirect(withQueryValue(returnTo, "team_error", "请先选择至少一个变量或通道"));
  }
  if (!boundNpc) {
    redirect(withQueryValue(returnTo, "team_error", "NPC 预标注需要先选择负责这个调试窗口的 NPC"));
  }
  if (!labelSchema) {
    redirect(withQueryValue(returnTo, "team_error", "请先填写本次数据的自定义标注规则，再让 NPC 预标注"));
  }
  const timestamp = new Date().toISOString();
  const annotationId = `annotation-${createHash("sha1").update(`${projectId}:${interfaceId}:${captureIds.join(",")}:${variables.join(",")}:${timestamp}`).digest("hex").slice(0, 12)}`;
  try {
    const artifactPath = await writeRoboticsDerivedArtifact({
      projectId,
      interfaceId,
      kind: "annotations",
      artifactId: annotationId,
      payload: {
        schema: "robotics_annotation_request_v1",
        project_id: projectId,
        annotation_id: annotationId,
        interface_id: interfaceId,
        interface_name: interfaceName,
        interface_kind: interfaceKind,
        computer_node_id: computerNodeId,
        capture_ids: captureIds,
        capture_titles: captureTitles,
        variables,
        label_schema: labelSchema,
        label_goal: labelGoal,
        requested_npc_id: boundNpc,
        requested_npc: boundNpcLabel || boundNpc,
        created_at: timestamp,
        human_confirmation_required: true,
      },
    });
    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      agent_id: boundNpc,
      title: `数据预标注：${interfaceName || interfaceKind || "调试接口"}`,
      body: [
        `${boundNpcLabel || "NPC"} 请基于用户选择的采集片段做预标注建议。`,
        `采集片段：${captureIds.join("、")}`,
        `变量/通道：${variables.join("、")}`,
        `标注规则：${labelSchema}`,
        labelGoal ? `标注目标：${labelGoal}` : "标注目标：按用户选择的变量和片段给出可复核的预标注建议。",
        `证据文件：${artifactPath}`,
        "边界：这是预标注建议，最终标签必须由用户确认后才能导出为训练数据集。",
      ].join("\n"),
      message_type: "robotics_annotation_request",
      sender_type: "human",
      sender_id: "robotics-dataset",
      recipient_type: "thread_workstation",
      recipient_id: boundNpc,
      status: "needs_npc",
      metadata: {
        terminal_interface_id: interfaceId,
        terminal_interface_name: interfaceName,
        terminal_interface_kind: interfaceKind,
        terminal_bound_npc_id: boundNpc,
        terminal_bound_npc: boundNpcLabel || boundNpc,
        terminal_surface: "robotics",
        computer_node_id: computerNodeId,
        annotation_id: annotationId,
        capture_ids: captureIds,
        capture_titles: captureTitles,
        selected_variables: variables,
        label_schema: labelSchema,
        label_goal: labelGoal,
        artifact_path: artifactPath,
        artifact_refs: [{ label: "预标注请求", path: artifactPath }],
        evidence_artifacts: [{ label: "预标注请求", path: artifactPath }],
      },
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/robotics`);
    redirect(withQueryValue(returnTo, "team_notice", "NPC 预标注请求已创建；结果会回到这个调试窗口的事件流"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "创建 NPC 预标注请求失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 导出机器人标注数据(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "robotics");
  const interfaceId = String(formData.get("interface_id") ?? "").trim();
  const interfaceName = String(formData.get("interface_name") ?? "").trim();
  const interfaceKind = String(formData.get("interface_kind") ?? "").trim();
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  const captureIds = splitFormList(formData.getAll("capture_ids"));
  const variables = splitFormList(formData.getAll("variables"));
  const labelSchema = String(formData.get("label_schema") ?? "").trim() || "用户确认标签";
  const exportFormat = safeArtifactSlug(formData.get("export_format") ?? "jsonl", "jsonl");
  const labelNotes = String(formData.get("label_notes") ?? "").trim();
  const manualLabels = parseRoboticsManualLabels(formData.get("manual_labels"));
  if (!interfaceId || !computerNodeId) {
    redirect(withQueryValue(returnTo, "team_error", "请先在真实接口瓷砖里导出标注数据"));
  }
  if (!captureIds.length || !variables.length) {
    redirect(withQueryValue(returnTo, "team_error", "导出前需要选择采集片段和变量"));
  }
  const timestamp = new Date().toISOString();
  const exportId = `dataset-${createHash("sha1").update(`${projectId}:${interfaceId}:${captureIds.join(",")}:${variables.join(",")}:${exportFormat}:${timestamp}`).digest("hex").slice(0, 12)}`;
  const normalizedFormat = ["csv", "jsonl", "parquet", "npz", "manifest"].includes(exportFormat) ? exportFormat : "manifest";
  try {
    const runnerSummaries = await collectRoboticsCaptureRunnerSummaries(projectId, interfaceId, captureIds);
    const numericSummaryRows = roboticsNumericSummaryRows(runnerSummaries, captureIds, variables, labelSchema, labelNotes);
    const payload = {
      schema: "robotics_dataset_export_v1",
      project_id: projectId,
      dataset_id: exportId,
      interface_id: interfaceId,
      interface_name: interfaceName,
      interface_kind: interfaceKind,
      computer_node_id: computerNodeId,
      capture_ids: captureIds,
      selected_variables: variables,
      label_schema: labelSchema,
      label_notes: labelNotes,
      manual_labels: manualLabels,
      export_format: normalizedFormat,
      runner_capture_summaries: runnerSummaries,
      training_rows: numericSummaryRows,
      created_at: timestamp,
      storage_note: "Raw high-frequency data should live in the project GitHub data path; this artifact is the platform export index or lightweight export.",
    };
    const rows = [
      ["dataset_id", "capture_id", "variable", "statistic", "value", "label_schema", "label", "start", "end", "note", "source"],
      ...captureIds.flatMap((captureId) => variables.map((variable) => [exportId, captureId, variable, "selected", "", labelSchema, labelSchema, "", "", labelNotes, "human_selection"])),
      ...numericSummaryRows.map((row) => [
        exportId,
        row.capture_id,
        row.variable,
        row.statistic,
        row.value,
        row.label_schema,
        row.label,
        row.start,
        row.end,
        row.note,
        row.source,
      ]),
      ...manualLabels.map((label) => [
        exportId,
        label.capture_id || captureIds[0] || "",
        label.variable || variables[0] || "",
        "manual_range",
        "",
        labelSchema,
        label.label,
        label.start,
        label.end,
        label.note || labelNotes,
        "human_label",
      ]),
    ];
    const artifactPath = await writeRoboticsDerivedArtifact({
      projectId,
      interfaceId,
      kind: "datasets",
      artifactId: exportId,
      extension: normalizedFormat === "csv" || normalizedFormat === "jsonl" ? normalizedFormat : "json",
      payload,
      csvRows: rows,
    });
    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      title: `标注数据导出：${interfaceName || interfaceKind || "调试接口"}`,
      body: [
        "设备数据工作台导出了一个可训练数据集索引。",
        `采集片段：${captureIds.join("、")}`,
        `变量/通道：${variables.join("、")}`,
        `导出格式：${normalizedFormat.toUpperCase()}`,
        `证据文件：${artifactPath}`,
        normalizedFormat === "parquet" || normalizedFormat === "npz" ? "当前先生成格式化导出清单；重型二进制文件由 runner/GitHub 数据通道补齐。" : "当前导出文件已生成，可作为轻量训练数据或证据索引。",
      ].join("\n"),
      message_type: "robotics_dataset_export",
      sender_type: "human",
      sender_id: "robotics-dataset",
      recipient_type: "project",
      recipient_id: projectId,
      status: "exported",
      metadata: {
        terminal_interface_id: interfaceId,
        terminal_interface_name: interfaceName,
        terminal_interface_kind: interfaceKind,
        terminal_surface: "robotics",
        computer_node_id: computerNodeId,
        dataset_id: exportId,
        capture_ids: captureIds,
        selected_variables: variables,
        label_schema: labelSchema,
        manual_labels: manualLabels,
        export_format: normalizedFormat,
        runner_capture_summaries: runnerSummaries,
        artifact_path: artifactPath,
        artifact_refs: [{ label: "标注数据导出", path: artifactPath }],
        evidence_artifacts: [{ label: "标注数据导出", path: artifactPath }],
      },
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/robotics`);
    redirect(withQueryValue(returnTo, "team_notice", "标注数据导出已生成，并已登记为同一调试窗口证据"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "导出标注数据失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 创建机器人图表实验(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "robotics");
  const interfaceId = String(formData.get("interface_id") ?? "").trim();
  const interfaceName = String(formData.get("interface_name") ?? "").trim();
  const interfaceKind = String(formData.get("interface_kind") ?? "").trim();
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  const captureIds = splitFormList(formData.getAll("capture_ids"));
  const xAxis = String(formData.get("x_axis") ?? "time").trim() || "time";
  const yAxes = splitFormList(formData.getAll("y_axes"));
  const targetValue = String(formData.get("target_value") ?? "").trim();
  const chartMode = String(formData.get("chart_mode") ?? "pid").trim() || "pid";
  if (!interfaceId || !computerNodeId) {
    redirect(withQueryValue(returnTo, "team_error", "请先在真实接口瓷砖里创建图表实验"));
  }
  if (!captureIds.length || !yAxes.length) {
    redirect(withQueryValue(returnTo, "team_error", "图表实验需要选择采集片段和纵轴变量"));
  }
  const timestamp = new Date().toISOString();
  const chartId = `chart-${createHash("sha1").update(`${projectId}:${interfaceId}:${captureIds.join(",")}:${xAxis}:${yAxes.join(",")}:${timestamp}`).digest("hex").slice(0, 12)}`;
  try {
    const runnerSummaries = await collectRoboticsCaptureRunnerSummaries(projectId, interfaceId, captureIds);
    const artifactPath = await writeRoboticsDerivedArtifact({
      projectId,
      interfaceId,
      kind: "charts",
      artifactId: chartId,
      payload: {
        schema: "robotics_chart_experiment_v1",
        project_id: projectId,
        chart_id: chartId,
        interface_id: interfaceId,
        interface_name: interfaceName,
        interface_kind: interfaceKind,
        computer_node_id: computerNodeId,
        capture_ids: captureIds,
        x_axis: xAxis,
        y_axes: yAxes,
        target_value: targetValue,
        chart_mode: chartMode,
        runner_capture_summaries: runnerSummaries,
        created_at: timestamp,
      },
    });
    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      title: `图表快照：${interfaceName || interfaceKind || "调试接口"}`,
      body: [
        "设备数据工作台保存了一个图表实验配置。",
        `采集片段：${captureIds.join("、")}`,
        `横轴：${xAxis}`,
        `纵轴：${yAxes.join("、")}`,
        targetValue ? `目标值：${targetValue}` : "目标值：未设置",
        `实验类型：${chartMode.toUpperCase()}`,
        `证据文件：${artifactPath}`,
      ].join("\n"),
      message_type: "robotics_chart_snapshot",
      sender_type: "human",
      sender_id: "robotics-chart",
      recipient_type: "project",
      recipient_id: projectId,
      status: "captured",
      metadata: {
        terminal_interface_id: interfaceId,
        terminal_interface_name: interfaceName,
        terminal_interface_kind: interfaceKind,
        terminal_surface: "robotics",
        computer_node_id: computerNodeId,
        chart_id: chartId,
        capture_ids: captureIds,
        x_axis: xAxis,
        y_axes: yAxes,
        target_value: targetValue,
        chart_mode: chartMode,
        runner_capture_summaries: runnerSummaries,
        artifact_path: artifactPath,
        artifact_refs: [{ label: "图表实验配置", path: artifactPath }],
        evidence_artifacts: [{ label: "图表实验配置", path: artifactPath }],
      },
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/robotics`);
    redirect(withQueryValue(returnTo, "team_notice", "图表实验快照已保存；可继续请求 NPC 分析建议"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "保存图表实验失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 创建机器人调参建议请求(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "robotics");
  const interfaceId = String(formData.get("interface_id") ?? "").trim();
  const interfaceName = String(formData.get("interface_name") ?? "").trim();
  const interfaceKind = String(formData.get("interface_kind") ?? "").trim();
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  const boundNpc = String(formData.get("bound_npc") ?? "").trim();
  const boundNpcLabel = String(formData.get("bound_npc_label") ?? "").trim();
  const captureIds = splitFormList(formData.getAll("capture_ids"));
  const xAxis = String(formData.get("x_axis") ?? "time").trim() || "time";
  const yAxes = splitFormList(formData.getAll("y_axes"));
  const targetValue = String(formData.get("target_value") ?? "").trim();
  const chartMode = String(formData.get("chart_mode") ?? "pid").trim() || "pid";
  const symptoms = String(formData.get("symptoms") ?? "").trim();
  if (!interfaceId || !computerNodeId) {
    redirect(withQueryValue(returnTo, "team_error", "请先在真实接口瓷砖里请求分析建议"));
  }
  if (!boundNpc) {
    redirect(withQueryValue(returnTo, "team_error", "分析建议需要先选择负责这个调试窗口的 NPC"));
  }
  if (!captureIds.length || !yAxes.length) {
    redirect(withQueryValue(returnTo, "team_error", "分析建议需要选择采集片段和纵轴变量"));
  }
  const timestamp = new Date().toISOString();
  const tuningId = `tuning-${createHash("sha1").update(`${projectId}:${interfaceId}:${captureIds.join(",")}:${xAxis}:${yAxes.join(",")}:${targetValue}:${timestamp}`).digest("hex").slice(0, 12)}`;
  try {
    const runnerSummaries = await collectRoboticsCaptureRunnerSummaries(projectId, interfaceId, captureIds);
    const artifactPath = await writeRoboticsDerivedArtifact({
      projectId,
      interfaceId,
      kind: "tuning",
      artifactId: tuningId,
      payload: {
        schema: "robotics_tuning_request_v1",
        project_id: projectId,
        tuning_id: tuningId,
        interface_id: interfaceId,
        interface_name: interfaceName,
        interface_kind: interfaceKind,
        computer_node_id: computerNodeId,
        capture_ids: captureIds,
        x_axis: xAxis,
        y_axes: yAxes,
        target_value: targetValue,
        chart_mode: chartMode,
        symptoms,
        runner_capture_summaries: runnerSummaries,
        requested_npc_id: boundNpc,
        requested_npc: boundNpcLabel || boundNpc,
        created_at: timestamp,
        hardware_write_requires_review: true,
      },
    });
    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      agent_id: boundNpc,
      title: `数据分析建议：${interfaceName || interfaceKind || "调试接口"}`,
      body: [
        `${boundNpcLabel || "NPC"} 请基于图表实验给出 ${chartMode.toUpperCase()} 分析建议。`,
        `采集片段：${captureIds.join("、")}`,
        `横轴：${xAxis}`,
        `纵轴：${yAxes.join("、")}`,
        targetValue ? `目标值：${targetValue}` : "目标值：未设置",
        Object.keys(runnerSummaries).length ? `采集摘要：${Object.keys(runnerSummaries).length} 个片段已有样本摘要` : "采集摘要：暂无 runner 数值摘要，请结合片段证据谨慎判断。",
        symptoms ? `现象：${symptoms}` : "现象：请判断趋势、异常区间、阈值附近波动、状态切换和延迟。",
        `证据文件：${artifactPath}`,
        "边界：只能给建议或生成待审核操作；不能直接写入真实硬件参数。",
      ].join("\n"),
      message_type: "robotics_tuning_request",
      sender_type: "human",
      sender_id: "robotics-chart",
      recipient_type: "thread_workstation",
      recipient_id: boundNpc,
      status: "needs_npc",
      metadata: {
        terminal_interface_id: interfaceId,
        terminal_interface_name: interfaceName,
        terminal_interface_kind: interfaceKind,
        terminal_bound_npc_id: boundNpc,
        terminal_bound_npc: boundNpcLabel || boundNpc,
        terminal_surface: "robotics",
        computer_node_id: computerNodeId,
        tuning_id: tuningId,
        capture_ids: captureIds,
        x_axis: xAxis,
        y_axes: yAxes,
        target_value: targetValue,
        chart_mode: chartMode,
        symptoms,
        runner_capture_summaries: runnerSummaries,
        artifact_path: artifactPath,
        artifact_refs: [{ label: "分析建议请求", path: artifactPath }],
        evidence_artifacts: [{ label: "分析建议请求", path: artifactPath }],
      },
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/robotics`);
    redirect(withQueryValue(returnTo, "team_notice", "NPC 分析建议请求已创建；涉及真实设备写入仍会回到终端待审"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "创建分析建议请求失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 创建机器人调试Npc操作审核(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "robotics");
  const computerNodeId = String(formData.get("computer_node_id") ?? "").trim();
  const interfaceId = String(formData.get("interface_id") ?? "").trim();
  const interfaceName = String(formData.get("interface_name") ?? "").trim();
  const interfaceKind = String(formData.get("interface_kind") ?? "").trim();
  const boundNpc = String(formData.get("bound_npc") ?? "").trim();
  const boundNpcLabel = String(formData.get("bound_npc_label") ?? "").trim();
  const command = String(formData.get("command") ?? "").trim();
  if (!computerNodeId || !interfaceId) {
    redirect(withQueryValue(returnTo, "team_error", "NPC 代操作需要先绑定真实执行电脑和调试接口"));
  }
  if (!boundNpc) {
    redirect(withQueryValue(returnTo, "team_error", "NPC 代操作需要先选择负责这个调试窗口的 NPC"));
  }
  if (!command) {
    redirect(withQueryValue(returnTo, "team_error", "请先填写 NPC 想代你执行的终端操作"));
  }
  try {
    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      agent_id: boundNpc,
      title: `NPC 代操作待审：${interfaceName || interfaceKind || "调试终端"}`,
      body: [
        `${boundNpcLabel || "NPC"} 请求代用户操作这个调试终端。`,
        `接口类型：${interfaceKind || "待确认"}`,
        `接口名称：${interfaceName || interfaceId}`,
        `拟执行命令：${command}`,
        "",
        "审核规则：用户自己在终端输入不需要审核；这条是 NPC/AI 代操作，所以必须先由用户通过或打回。通过后才允许转成 runner 终端命令。",
      ].join("\n"),
      message_type: "robotics_terminal_npc_request",
      sender_type: "agent",
      sender_id: boundNpc,
      recipient_type: "human",
      recipient_id: "project-owner",
      status: "pending_review",
      metadata: {
        terminal_interface_id: interfaceId,
        terminal_interface_name: interfaceName,
        terminal_interface_kind: interfaceKind,
        terminal_bound_npc_id: boundNpc,
        terminal_bound_npc: boundNpcLabel || boundNpc,
        terminal_command: command,
        terminal_mode: "npc_terminal_request",
        terminal_surface: "robotics",
        computer_node_id: computerNodeId,
        review_required_reason: "npc_operates_terminal",
      },
    });
    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/robotics`);
    redirect(withQueryValue(returnTo, "team_notice", "NPC 代操作已进入待审核；通过前不会下发到执行电脑"));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "创建 NPC 操作审核失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 创建审批单(formData: FormData) {
  await postJson("/api/approvals", {
    project_id: String(formData.get("project_id") ?? "") || null,
    task_id: String(formData.get("task_id") ?? "") || null,
    level: String(formData.get("level") ?? "H3"),
    action: String(formData.get("action") ?? "高风险动作"),
    status: String(formData.get("status") ?? "pending"),
    notes: String(formData.get("notes") ?? ""),
  });
  revalidatePath("/approvals");
  revalidatePath("/lab");
}

export async function 安装农场维护员(projectId: string, _formData?: FormData) {
  if (!projectId) return;
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig =
      project?.collaboration_config && typeof project.collaboration_config === "object"
        ? { ...(project.collaboration_config as Record<string, unknown>) }
        : {};

    const providers = Array.isArray(collaborationConfig.ai_providers)
      ? [...(collaborationConfig.ai_providers as Record<string, unknown>[])]
      : [];
    const workstations = Array.isArray(collaborationConfig.thread_workstations)
      ? [...(collaborationConfig.thread_workstations as Record<string, unknown>[])]
      : [];
    const nodes = Array.isArray(collaborationConfig.computer_nodes)
      ? [...(collaborationConfig.computer_nodes as Record<string, unknown>[])]
      : [];

    const maintainerProviderId = "farm-maintainer";
    const maintainerSeatId = "farm-maintainer-seat";
    const existingProvider = providers.find((item) => {
      const id = String(item.id ?? item.label ?? item.name ?? "").trim().toLowerCase();
      return id === maintainerProviderId || id === "farm maintainer";
    });
    const existingSeat = workstations.find((item) => {
      const id = String(item.id ?? item.name ?? item.agent_id ?? "").trim().toLowerCase();
      const role = String(item.agent_id ?? item.role ?? item.responsibility ?? "").trim().toLowerCase();
      return id === maintainerSeatId || id === "farm maintainer" || role.includes("farm-maintainer") || role.includes("maintainer");
    });
    const onlineNode =
      nodes.find((item) => ["online", "ready", "active"].includes(String(item.status ?? "").trim().toLowerCase())) ??
      nodes[0] ??
      null;

    if (!existingProvider) {
      providers.push({
        id: maintainerProviderId,
        label: "Farm Maintainer",
        kind: "thread",
        enabled: true,
        endpoint: "openai",
        model: "gpt-5.4-mini",
        sort_order: 999,
        metadata: {
          role: "farm_maintainer",
          manages: ["hq", "handoffs", "approvals", "runner-relays"],
        },
      });
    }

    if (!existingSeat) {
      workstations.push({
        id: maintainerSeatId,
        name: "Farm Maintainer",
        agent_id: "farm-maintainer",
        computer_node: onlineNode ? String(onlineNode.label ?? onlineNode.name ?? onlineNode.id ?? "") : null,
        computer_node_id: onlineNode ? String(onlineNode.id ?? "") : null,
        ai_provider: "Farm Maintainer",
        ai_provider_id: maintainerProviderId,
        status: onlineNode ? "active" : "idle",
        responsibility: "Watch boss orders, stale handoffs, approval gates, and runner relays inside the farm.",
        model: "gpt-5.4-mini",
        permission_level: "L2",
        read_paths: [
          "docs/ai-handoffs",
          "apps/web/app/projects/[id]",
          "apps/web/lib/game",
        ],
        write_paths: ["docs/ai-handoffs"],
        description: "Default on-map maintainer seat for the AI collaboration farm.",
        notes: "Use this seat to keep the collaboration loop healthy before the base expands.",
        sort_order: 999,
        metadata: {
          role: "farm_maintainer",
          autopilot: true,
        },
      });
    }

    await patchJson(`/api/projects/${projectId}`, {
      collaboration_config: {
        ...collaborationConfig,
        ai_providers: providers,
        thread_workstations: workstations,
      },
    });

    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      agent_id: "farm-maintainer",
      message_type: "status_update",
      title: "Farm maintainer connected",
      body: onlineNode
        ? `Farm Maintainer is now linked to ${String(onlineNode.label ?? onlineNode.name ?? onlineNode.id ?? "the base node")} and watching handoffs, approvals, and runner relays.`
        : "Farm Maintainer is now installed and waiting for a node before taking active watch duty.",
      sender_type: "system",
      sender_id: "farm-maintainer",
      recipient_type: "project",
      recipient_id: projectId,
      status: "open",
    });

    revalidateProjectSurfaces(projectId);
    revalidatePath("/collaborators");
    revalidatePath("/handoffs");
    revalidatePath("/approvals");
    redirect(`/projects/${projectId}?panel=team&team_notice=${encodeURIComponent("Codex 驻场席位已写入平台")}`);
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "安装失败，请检查是否已登录、是否拥有项目权限，以及 8000 后端是否已启动。";
    redirect(`/projects/${projectId}?panel=team&team_error=${encodeURIComponent(message)}`);
  }
}

export async function 持久化经营状态(projectId: string, economyState: string) {
  if (!projectId || !economyState.trim()) return;

  const payload = JSON.parse(economyState);
  const projectResult = await getJson(`/api/projects/${projectId}`);
  const project = projectResult?.data ?? projectResult ?? {};
  const collaborationConfig =
    project?.collaboration_config && typeof project.collaboration_config === "object"
      ? { ...(project.collaboration_config as Record<string, unknown>) }
      : {};

  await patchJson(`/api/projects/${projectId}`, {
    collaboration_config: {
      ...collaborationConfig,
      economy_state: payload,
    },
  });

  revalidateProjectSurfaces(projectId);
}

export async function 发送Codex桥接指令(projectId: string, formData: FormData) {
  const title = String(formData.get("title") ?? "").trim() || "基地新指令";
  const body = String(formData.get("body") ?? "").trim();
  const issuer = String(formData.get("issuer") ?? "").trim() || "基地指挥官";
  const workstationId = String(formData.get("workstation_id") ?? "").trim() || "codex-mainline";
  if (!projectId || !body) return;
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig =
      project?.collaboration_config && typeof project.collaboration_config === "object"
        ? (project.collaboration_config as Record<string, unknown>)
        : {};
    const workstations = Array.isArray(collaborationConfig.thread_workstations)
      ? (collaborationConfig.thread_workstations as Record<string, unknown>[])
      : [];
    const workstationContext = resolveCodexWorkstationContext(
      workstations,
      workstationId,
      project && typeof project === "object" ? (project as Record<string, unknown>) : null,
    );
    const workstationName = workstationContext.workstationName;

    await appendProjectCodexCommand({
      projectId,
      title,
      body,
      issuer,
      workstationId,
      workstationName,
      provider: workstationContext.provider || undefined,
      computerNodeId: workstationContext.computerNodeId || undefined,
      computerNodeLabel: workstationContext.computerNodeLabel || undefined,
      skillLoadout: workstationContext.skillLoadout,
      repoSummary: workstationContext.repoSummary || undefined,
      referencePaths: workstationContext.referencePaths,
    });

    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      agent_id: "codex",
      message_type: "agent_command",
      title,
      body,
      sender_type: "human",
      sender_id: issuer,
      recipient_type: "workstation",
      recipient_id: workstationId,
      status: "queued",
    });

    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}`);
    redirect(
      `/projects/${projectId}?panel=team&team_notice=${encodeURIComponent(`指令已发送到 ${workstationName}`)}`,
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "指令写入失败";
    redirect(`/projects/${projectId}?panel=team&team_error=${encodeURIComponent(message)}`);
  }
}

export async function 请求扫描电脑线程(projectId: string, formData: FormData) {
  const nodeId = String(formData.get("computer_node_id") ?? "").trim();
  if (!projectId || !nodeId) return;
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "machine-room");

  try {
    const actorId = await resolveProjectHumanActorId(projectId);
    const nodeResult = await getJson(
      `/api/collaboration/projects/${projectId}/computer-nodes/${encodeURIComponent(nodeId)}`,
    );
    const node = nodeResult?.data ?? nodeResult ?? {};
    const nodeLabel = String(node.label ?? node.name ?? node.id ?? nodeId).trim() || nodeId;
    const runnerId = String(node.runner_id ?? "").trim();
    const metadata =
      node?.metadata && typeof node.metadata === "object" ? { ...(node.metadata as Record<string, unknown>) } : {};
    const requestedAt = new Date().toISOString();

    if (!runnerId) {
      await patchJson(`/api/collaboration/projects/${projectId}/computer-nodes/${encodeURIComponent(nodeId)}`, {
        metadata: {
          ...metadata,
          thread_scan: {
            status: "awaiting_runner",
            requested_at: requestedAt,
            requested_by: "human",
            hint: "先在对应电脑运行 runner 接入命令，再回来扫描线程。",
          },
        },
      });
      revalidateProjectSurfaces(projectId);
      redirect(
        withQueryValue(
          returnTo,
          "team_notice",
          `这台电脑还没接入 runner。先在 ${nodeLabel} 的仓库里运行接入命令，再回来扫描线程。`,
        ),
      );
    }

    await patchJson(`/api/collaboration/projects/${projectId}/computer-nodes/${encodeURIComponent(nodeId)}`, {
      metadata: {
        ...metadata,
        thread_scan: {
          status: "requested",
          requested_at: requestedAt,
          requested_by: "human",
        },
      },
    });

    const scanMessageResult = await postJson("/api/collaboration/messages", {
      project_id: projectId,
      agent_id: "codex",
      message_type: "thread_scan_request",
      title: `扫描 ${nodeLabel} 上的 Codex 线程`,
      body: "请回传这台电脑当前可用的 Codex 线程列表，包含线程 id、线程名、工作目录和状态。",
      sender_type: "human",
      sender_id: actorId,
      recipient_type: "computer_node",
      recipient_id: nodeId,
      status: "queued",
    });
    const scanMessageId = String(
      scanMessageResult?.data?.id ?? scanMessageResult?.id ?? "",
    ).trim();

    if (runnerId) {
      const workspaceResult = await getJson(`/api/runners/${encodeURIComponent(runnerId)}/workspace`);
      const workspace = workspaceResult?.data ?? workspaceResult ?? {};
      const discoveredThreads = Array.isArray(workspace?.workstations)
        ? workspace.workstations
            .filter(
              (item: Record<string, unknown>) =>
                String(item.computer_node_id ?? "").trim() === nodeId &&
                String(item.source ?? "").trim() === "runner_thread_scan",
            )
            .map((item: Record<string, unknown>) => ({
              workstation_id: String(item.workstation_id ?? "").trim(),
              workstation_name: String(item.workstation_name ?? item.name ?? "").trim() || "未命名线程",
              workstation_status: String(item.workstation_status ?? item.status ?? "").trim() || "idle",
              agent_id: String(item.agent_id ?? "").trim() || null,
              ai_provider_id: String(item.ai_provider_id ?? "").trim() || null,
              ai_provider_label: String(item.ai_provider_label ?? "").trim() || null,
            }))
        : [];
      const effectiveThreads = discoveredThreads;

      await patchJson(`/api/collaboration/projects/${projectId}/computer-nodes/${encodeURIComponent(nodeId)}`, {
        metadata: {
          ...metadata,
          thread_scan: {
            status: "completed",
            requested_at: requestedAt,
            completed_at: new Date().toISOString(),
            requested_by: "human",
            runner_id: runnerId,
            thread_count: effectiveThreads.length,
            threads: effectiveThreads,
          },
        },
      });
      if (scanMessageId) {
        await patchJson(`/api/collaboration/messages/${encodeURIComponent(scanMessageId)}`, {
          status: "completed",
        });
      }

      revalidateProjectSurfaces(projectId);
      redirect(
        withQueryValue(
          returnTo,
          "team_notice",
          `已扫描 ${nodeLabel}，发现 ${effectiveThreads.length} 个线程`,
        ),
      );
    }

    revalidateProjectSurfaces(projectId);
    redirect(withQueryValue(returnTo, "team_notice", `已向 ${nodeLabel} 发出线程扫描请求`));
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "线程扫描请求失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

async function ensureCodexProvider(projectId: string, project: any) {
  await ensureProjectAiProvider(projectId, project, {
    providerId: "codex",
    providerLabel: "Codex",
    model: "gpt-5.4",
  });
}

export async function 创建Npc驻场席位(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "npc-create");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const workstationName = String(formData.get("name") ?? "").trim() || "NPC 新席位";
    const responsibility = String(formData.get("responsibility") ?? "").trim() || "待分配职位";
    const automationEnabled = readBooleanFormField(formData, "automation_enabled", false);
    const automationHeartbeatSeconds = normalizeAutomationHeartbeatSeconds(
      formData.get("automation_heartbeat_seconds"),
    );
    const threadContext = resolveNpcSourceThreadContext(project, formData);
    const providerId = threadContext.providerId || "codex";
    const providerLabel = threadContext.providerLabel || platformProviderLabel(providerId);
    await ensureProjectAiProvider(projectId, project, {
      providerId,
      providerLabel,
      model: text(formData.get("model"), "") || threadContext.model || "gpt-5.4",
    });

    const computerNodeId = String(formData.get("computer_node_id") ?? "").trim() || threadContext.computerNodeId || null;
    const sourceWorkstationId = threadContext.sourceWorkstationId;
    const additionalSkillIds = parseStringListAll(formData, "skill_loadout") ?? [];
    const skillLoadout = mergePlatformSkillLoadout(additionalSkillIds);
    const gitBoundary = parseStringList(formData.get("git_boundary")) ?? [];
    const scene = String(formData.get("scene") ?? "").trim() || "map-farm";
    const avatarKey = String(formData.get("avatar_key") ?? "").trim() || "jack-standing";
    const mapX = Number(formData.get("map_x") ?? 0) || 0;
    const mapY = Number(formData.get("map_y") ?? 0) || 0;
    const developmentStationId = String(formData.get("development_station_id") ?? "").trim() || null;
    const developmentStationLabel = String(formData.get("development_station_label") ?? "").trim() || null;
    const model = String(formData.get("model") ?? "").trim() || threadContext.model || "gpt-5.4";
    const npcKnowledge = buildNpcKnowledgeProfile({
      name: workstationName,
      responsibility,
      knowledgeSlug: String(formData.get("knowledge_slug") ?? "").trim() || null,
      knowledgeSummary: String(formData.get("knowledge_summary") ?? "").trim() || null,
      knowledgeHandoffPath: String(formData.get("knowledge_handoff_path") ?? "").trim() || null,
      knowledgeDepositPath: String(formData.get("knowledge_deposit_path") ?? "").trim() || null,
      skillDepositPath: String(formData.get("skill_deposit_path") ?? "").trim() || null,
      needDepositPath: String(formData.get("need_deposit_path") ?? "").trim() || null,
      taskDepositPath: String(formData.get("task_deposit_path") ?? "").trim() || null,
      knowledgeTags: parseStringList(formData.get("knowledge_tags")) ?? [],
    });
    const collabProtocol = enrichNpcCollabProtocolWithRepoContext(
      project,
      resolveNpcCollabProtocol(formData, {
        providerId,
        responsibility,
        threadText: threadContext.threadName,
      }),
      {
        gitBoundary,
        handoffPath: npcKnowledge.handoff_path,
      },
    );
    const onlineNode =
      (Array.isArray(project?.collaboration_config?.computer_nodes)
        ? project.collaboration_config.computer_nodes
        : []
      ).find((item: any) => String(item.id ?? "").trim() === computerNodeId) ?? null;

    const created = await postJson(`/api/collaboration/projects/${projectId}/thread-workstations`, {
      name: workstationName,
      agent_id: `${providerId}-${Date.now()}`,
      computer_node:
        onlineNode
          ? String(onlineNode.label ?? onlineNode.name ?? onlineNode.id ?? "")
          : threadContext.computerNodeLabel,
      computer_node_id: computerNodeId,
      ai_provider: providerLabel,
      ai_provider_id: providerId,
      status: String(formData.get("status") ?? "idle").trim() || "idle",
      responsibility,
      model,
      permission_level: String(formData.get("permission_level") ?? "").trim() || "L2",
      description: String(formData.get("description") ?? "").trim() || null,
      notes: String(formData.get("notes") ?? "").trim() || null,
      metadata: {
        seat_type: seatTypeForProvider(providerId),
        provider_id: providerId,
        provider_label: providerLabel,
        source_workstation_id: sourceWorkstationId,
        additional_skill_ids: additionalSkillIds,
        skill_loadout: skillLoadout,
        collab_protocol: collabProtocol,
        npc_identity_key: npcKnowledge.key,
        npc_knowledge: npcKnowledge,
        git_boundary: gitBoundary,
        scene,
        avatar_key: avatarKey,
        map_x: mapX,
        map_y: mapY,
        development_station_id: developmentStationId,
        development_station_label: developmentStationLabel,
        automation_enabled: automationEnabled,
        automation_heartbeat_seconds: automationHeartbeatSeconds,
      },
    });
    const continuity =
      automationEnabled
        ? await ensureNpcSeatContinuity({
            projectId,
            seatName: workstationName,
            responsibility,
            sourceWorkstationId,
            handoffPath: npcKnowledge.handoff_path,
            knowledgeDepositPath: npcKnowledge.knowledge_deposit_path,
            skillDepositPath: npcKnowledge.skill_deposit_path,
            needDepositPath: npcKnowledge.need_deposit_path,
            taskDepositPath: npcKnowledge.task_deposit_path,
            computerNodeId,
            model,
            additionalSkillIds,
            providerId,
            providerLabel,
            collabProtocol,
            heartbeatIntervalSeconds: automationHeartbeatSeconds,
          })
        : {
            consumerScript: null,
            heartbeat: null,
            providerRegistration: null,
            providerActivation: null,
          };
    const { consumerScript, heartbeat, providerRegistration, providerActivation } = continuity;
    const createdSeatId = String(
      (created as Record<string, any>)?.data?.id ??
      (created as Record<string, any>)?.id ??
      workstationName,
    ).trim();
    const provisioning = await readNpcProvisioningSummary({
      seatId: createdSeatId,
      seatName: workstationName,
      providerId,
      providerLabel,
      sourceWorkstationId,
    });
    const repoSummary = platformRepoContextSummary(collabProtocol.repo_context);

    revalidateProjectSurfaces(projectId);
    const search = new URLSearchParams({
      team_notice:
        consumerScript || heartbeat || providerRegistration || providerActivation
          ? `已新增 ${providerLabel} NPC：${workstationName}${consumerScript ? `，已生成线程 consumer：${consumerScript}` : ""}${heartbeat ? `，自治心跳已接通：${heartbeat.id}` : ""}${providerRegistration ? `，已登记 ${providerRegistration}` : ""}${providerActivation ? `，${providerActivation}` : ""} / 开箱状态：${provisioning.label}${provisioning.missing.length ? `（${provisioning.missing.join("、")}）` : ""} / 仓库协作：${repoSummary}`
          : `已新增 ${providerLabel} NPC：${workstationName}${sourceWorkstationId ? "，已绑定来源线程并落固定知识库" : ""}${automationEnabled ? "" : " / 当前为单次执行模式，只有发指令时才会跑这一次"} / 开箱状态：${provisioning.label}${provisioning.missing.length ? `（${provisioning.missing.join("、")}）` : ""} / 仓库协作：${repoSummary}`,
    });
    if (createdSeatId) search.set("seat", createdSeatId);
    let nextPath = withQueryValue(returnTo, "team_notice", search.get("team_notice") || "已新增 NPC 席位");
    if (createdSeatId) {
      nextPath = withQueryValue(nextPath, "seat", createdSeatId);
    }
    redirect(nextPath);
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "新增 NPC 席位失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 更新Npc驻场席位(projectId: string, workstationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "npc-create");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig =
      project?.collaboration_config && typeof project.collaboration_config === "object"
        ? (project.collaboration_config as Record<string, unknown>)
        : {};
    const threadContext = resolveNpcSourceThreadContext(project, formData);
    const providerId = threadContext.providerId || "codex";
    const providerLabel = threadContext.providerLabel || platformProviderLabel(providerId);
    await ensureProjectAiProvider(projectId, project, {
      providerId,
      providerLabel,
      model: text(formData.get("model"), "") || threadContext.model || "gpt-5.4",
    });
    const nodeId = String(formData.get("computer_node_id") ?? "").trim() || threadContext.computerNodeId || null;
    const sourceWorkstationId = threadContext.sourceWorkstationId;
    const additionalSkillIds = parseStringListAll(formData, "skill_loadout") ?? [];
    const skillLoadout = mergePlatformSkillLoadout(additionalSkillIds);
    const gitBoundary = parseStringList(formData.get("git_boundary")) ?? [];
    const scene = String(formData.get("scene") ?? "").trim() || "map-farm";
    const avatarKey = String(formData.get("avatar_key") ?? "").trim() || "jack-standing";
    const mapX = Number(formData.get("map_x") ?? 0) || 0;
    const mapY = Number(formData.get("map_y") ?? 0) || 0;
    const seatName = String(formData.get("name") ?? "").trim() || "NPC 席位";
    const responsibility = String(formData.get("responsibility") ?? "").trim() || null;
    const model = String(formData.get("model") ?? "").trim() || "gpt-5.4";
    const existingSeatResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const existingSeats = asArray<any>(existingSeatResult?.data ?? existingSeatResult);
    const existingSeat =
      existingSeats.find((item) =>
        workstationLookupKeys(item as Record<string, unknown>).some((candidate) => candidate === workstationId),
      ) ?? null;
    const existingMetadata =
      existingSeat?.metadata && typeof existingSeat.metadata === "object"
        ? (existingSeat.metadata as Record<string, unknown>)
        : {};
    const automationEnabled = readBooleanFormField(
      formData,
      "automation_enabled",
      readSeatAutomationEnabled(existingMetadata, false),
    );
    const automationHeartbeatSeconds = normalizeAutomationHeartbeatSeconds(
      formData.get("automation_heartbeat_seconds"),
      readSeatAutomationHeartbeatSeconds(existingMetadata),
    );
    const npcKnowledge = buildNpcKnowledgeProfile({
      seatId: workstationId,
      name: seatName,
      responsibility,
      knowledgeSlug: String(formData.get("knowledge_slug") ?? "").trim() || null,
      knowledgeSummary: String(formData.get("knowledge_summary") ?? "").trim() || null,
      knowledgeHandoffPath: String(formData.get("knowledge_handoff_path") ?? "").trim() || null,
      knowledgeDepositPath: String(formData.get("knowledge_deposit_path") ?? "").trim() || null,
      skillDepositPath: String(formData.get("skill_deposit_path") ?? "").trim() || null,
      needDepositPath: String(formData.get("need_deposit_path") ?? "").trim() || null,
      taskDepositPath: String(formData.get("task_deposit_path") ?? "").trim() || null,
      knowledgeTags: parseStringList(formData.get("knowledge_tags")) ?? [],
    });
    const collabProtocol = enrichNpcCollabProtocolWithRepoContext(
      project,
      resolveNpcCollabProtocol(formData, {
        providerId,
        responsibility,
        threadText: threadContext.threadName,
        existing:
          existingMetadata.collab_protocol && typeof existingMetadata.collab_protocol === "object"
            ? (existingMetadata.collab_protocol as Record<string, unknown>)
            : null,
      }),
      {
        gitBoundary,
        handoffPath: npcKnowledge.handoff_path,
      },
    );
    const onlineNode =
      (Array.isArray(collaborationConfig.computer_nodes) ? collaborationConfig.computer_nodes : []).find(
        (item: any) => String(item.id ?? "").trim() === nodeId,
      ) ?? null;

    await patchJson(
      `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(workstationId)}`,
      {
        name: seatName,
        computer_node:
          onlineNode
            ? String(onlineNode.label ?? onlineNode.name ?? onlineNode.id ?? "")
            : threadContext.computerNodeLabel,
        computer_node_id: nodeId,
        ai_provider: providerLabel,
        ai_provider_id: providerId,
        status: String(formData.get("status") ?? "idle").trim() || "idle",
        responsibility,
        model,
        permission_level: String(formData.get("permission_level") ?? "").trim() || "L2",
        description: String(formData.get("description") ?? "").trim() || null,
        notes: String(formData.get("notes") ?? "").trim() || null,
        metadata: {
          seat_type: seatTypeForProvider(providerId),
          provider_id: providerId,
          provider_label: providerLabel,
          source_workstation_id: sourceWorkstationId,
          additional_skill_ids: additionalSkillIds,
          skill_loadout: skillLoadout,
          collab_protocol: collabProtocol,
          npc_identity_key: npcKnowledge.key,
          npc_knowledge: npcKnowledge,
          git_boundary: gitBoundary,
          scene,
          avatar_key: avatarKey,
          map_x: mapX,
          map_y: mapY,
          automation_enabled: automationEnabled,
          automation_heartbeat_seconds: automationHeartbeatSeconds,
        },
      },
    );
    const continuity =
      automationEnabled
        ? await ensureNpcSeatContinuity({
            projectId,
            seatName,
            responsibility,
            sourceWorkstationId,
            handoffPath: npcKnowledge.handoff_path,
            knowledgeDepositPath: npcKnowledge.knowledge_deposit_path,
            skillDepositPath: npcKnowledge.skill_deposit_path,
            needDepositPath: npcKnowledge.need_deposit_path,
            taskDepositPath: npcKnowledge.task_deposit_path,
            computerNodeId: nodeId,
            model,
            additionalSkillIds,
            providerId,
            providerLabel,
            collabProtocol,
            heartbeatIntervalSeconds: automationHeartbeatSeconds,
          })
        : {
            consumerScript: null,
            heartbeat: null,
            providerRegistration: null,
            providerActivation: null,
          };
    const cleanupNotes = automationEnabled
      ? []
      : await disableNpcSeatContinuity({
          seatName,
          previousSeatName: text(existingSeat?.name ?? existingSeat?.workstation_name, "") || null,
          providerId,
          sourceWorkstationId,
          previousSourceWorkstationId: text(
            existingSeat?.source_workstation_id ?? existingMetadata.source_workstation_id,
            "",
          ) || null,
        });
    const { consumerScript, heartbeat, providerRegistration, providerActivation } = continuity;
    const provisioning = await readNpcProvisioningSummary({
      seatId: workstationId,
      seatName,
      providerId,
      providerLabel,
      sourceWorkstationId,
    });
    const repoSummary = platformRepoContextSummary(collabProtocol.repo_context);

    revalidateProjectSurfaces(projectId);
    let nextPath = withQueryValue(
      returnTo,
      "team_notice",
      consumerScript || heartbeat || providerRegistration || providerActivation
        ? `${providerLabel} NPC 已更新${consumerScript ? `，线程 consumer 已生成：${consumerScript}` : ""}${heartbeat ? `，自治心跳已接通：${heartbeat.id}` : ""}${providerRegistration ? `，已登记 ${providerRegistration}` : ""}${providerActivation ? `，${providerActivation}` : ""} / 开箱状态：${provisioning.label}${provisioning.missing.length ? `（${provisioning.missing.join("、")}）` : ""} / 仓库协作：${repoSummary}`
        : `${providerLabel} NPC 已更新${automationEnabled ? "" : ` / 当前为单次执行模式${cleanupNotes.length ? `（${cleanupNotes.join("、")}）` : ""}` } / 开箱状态：${provisioning.label}${provisioning.missing.length ? `（${provisioning.missing.join("、")}）` : ""} / 仓库协作：${repoSummary}`,
    );
    nextPath = withQueryValue(nextPath, "seat", workstationId);
    redirect(nextPath);
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "更新 NPC 席位失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 校准Codex席位自治桥(projectId: string, workstationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "npc-create");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const workstationsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const workstations = asArray<any>(workstationsResult?.data ?? workstationsResult);
    const seat =
      workstations.find((item) =>
        workstationLookupKeys(item as Record<string, unknown>).some((candidate) => candidate === workstationId),
      ) ?? null;
    if (!seat) {
      throw new Error("没有找到这个 Codex 席位");
    }

    const metadata = seat?.metadata && typeof seat.metadata === "object" ? (seat.metadata as Record<string, unknown>) : {};
    const seatName = text(seat?.name ?? seat?.workstation_name, workstationId) || "Codex 席位";
    const sourceWorkstationId = text(seat?.source_workstation_id ?? metadata.source_workstation_id, "") || null;
    if (!isCodexSessionWorkstationId(sourceWorkstationId)) {
      throw new Error("这个 NPC 还没有绑定本机 Codex 线程，暂时不能自动接通自治桥。");
    }
    const responsibility = text(seat?.responsibility ?? metadata.responsibility, "") || null;
    const model = text(seat?.model ?? metadata.model, "gpt-5.4") || "gpt-5.4";
    const computerNodeId = text(seat?.computer_node_id ?? seat?.computerNodeId ?? metadata.computer_node_id, "") || null;
    const skillLoadout = mergePlatformSkillLoadout(
      seat?.skill_loadout,
      seat?.skillLoadout,
      metadata.additional_skill_ids,
      metadata.skill_loadout,
    );
    const storedKnowledge =
      metadata.npc_knowledge && typeof metadata.npc_knowledge === "object"
        ? (metadata.npc_knowledge as Record<string, unknown>)
        : {};
    const npcKnowledge = buildNpcKnowledgeProfile({
      seatId: workstationId,
      name: seatName,
      responsibility,
      knowledgeSlug: text(storedKnowledge.slug ?? metadata.npc_identity_key, "").replace(/^npc:/, "") || null,
      knowledgeSummary: text(storedKnowledge.summary, "") || null,
      knowledgeHandoffPath: text(storedKnowledge.handoff_path, "") || null,
      knowledgeTags: asArray<string>(storedKnowledge.tags).map((item) => text(item)).filter(Boolean),
    });
    const collabProtocol = resolvePlatformCollabProtocol(metadata.collab_protocol, {
      providerId: "codex",
      roleText: responsibility ?? undefined,
      threadText: seatName,
    });
    const { consumerScript, heartbeat } = await ensureCodexSeatAutonomyBridge({
      projectId,
      seatName,
      responsibility,
      sourceWorkstationId,
      handoffPath: npcKnowledge.handoff_path,
      knowledgeDepositPath: npcKnowledge.knowledge_deposit_path,
      skillDepositPath: npcKnowledge.skill_deposit_path,
      needDepositPath: npcKnowledge.need_deposit_path,
      taskDepositPath: npcKnowledge.task_deposit_path,
      computerNodeId,
      model,
      additionalSkillIds: skillLoadout,
      collabProtocol,
      heartbeatIntervalSeconds: readSeatAutomationHeartbeatSeconds(metadata),
    });

    revalidateProjectSurfaces(projectId);
    let nextPath = withQueryValue(
      returnTo,
      "team_notice",
      `已校准 ${seatName} 自治桥${consumerScript ? `，consumer：${consumerScript}` : ""}${heartbeat ? `，心跳：${heartbeat.id}` : ""}`,
    );
    nextPath = withQueryValue(nextPath, "seat", workstationId);
    redirect(nextPath);
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "校准 Codex 席位自治桥失败";
    let nextPath = withQueryValue(returnTo, "team_error", message);
    nextPath = withQueryValue(nextPath, "seat", workstationId);
    redirect(nextPath);
  }
}

export async function 启动Npc真实线程处理(projectId: string, workstationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "workbench");
  const messageId = text(formData.get("message_id"), "");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const workstationsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const workstations = asArray<Record<string, unknown>>(workstationsResult?.data ?? workstationsResult);
    const seat =
      workstations.find((item) =>
        workstationLookupKeys(item).some((candidate) => candidate === workstationId),
      ) ?? null;
    if (!seat) {
      throw new Error("没有找到这个 NPC，无法启动真实线程处理。");
    }

    const metadata = seat.metadata && typeof seat.metadata === "object" ? (seat.metadata as Record<string, unknown>) : {};
    const seatName = text(seat.name ?? seat.workstation_name, workstationId) || "NPC";
    const providerId =
      normalizePlatformProviderId(
        seat.ai_provider_id ?? seat.ai_provider ?? metadata.provider_id ?? metadata.provider_label,
      ) || "codex";
    const automationEnabled = readSeatAutomationEnabled(metadata, false);
    const recipientId =
      text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, "") || workstationId;

    if (providerId === "codex" && automationEnabled) {
      const sourceWorkstationId =
        text(seat.source_workstation_id ?? metadata.source_workstation_id, "") ||
        text(metadata.target_thread_id ?? metadata.bound_thread_id ?? metadata.thread_id, "");
      if (isCodexSessionWorkstationId(sourceWorkstationId)) {
        const storedKnowledge =
          metadata.npc_knowledge && typeof metadata.npc_knowledge === "object"
            ? (metadata.npc_knowledge as Record<string, unknown>)
            : {};
        const npcKnowledge = buildNpcKnowledgeProfile({
          seatId: recipientId,
          name: seatName,
          responsibility: text(seat.responsibility ?? metadata.responsibility, "") || null,
          knowledgeSlug: text(storedKnowledge.slug ?? metadata.npc_identity_key, "").replace(/^npc:/, "") || null,
          knowledgeSummary: text(storedKnowledge.summary, "") || null,
          knowledgeHandoffPath: text(storedKnowledge.handoff_path, "") || null,
          knowledgeDepositPath: text(storedKnowledge.knowledge_deposit_path, "") || null,
          skillDepositPath: text(storedKnowledge.skill_deposit_path, "") || null,
          needDepositPath: text(storedKnowledge.need_deposit_path, "") || null,
          taskDepositPath: text(storedKnowledge.task_deposit_path, "") || null,
          knowledgeTags: asArray<string>(storedKnowledge.tags).map((item) => text(item)).filter(Boolean),
        });
        await ensureCodexSeatAutonomyBridge({
          projectId,
          seatName,
          responsibility: text(seat.responsibility ?? metadata.responsibility, "") || null,
          sourceWorkstationId,
          handoffPath: npcKnowledge.handoff_path,
          knowledgeDepositPath: npcKnowledge.knowledge_deposit_path,
          skillDepositPath: npcKnowledge.skill_deposit_path,
          needDepositPath: npcKnowledge.need_deposit_path,
          taskDepositPath: npcKnowledge.task_deposit_path,
          computerNodeId: text(seat.computer_node_id ?? seat.computerNodeId ?? metadata.computer_node_id, "") || null,
          model: text(seat.model ?? metadata.model, "gpt-5.4") || "gpt-5.4",
          additionalSkillIds: mergePlatformSkillLoadout(
            seat.skill_loadout,
            seat.skillLoadout,
            metadata.additional_skill_ids,
            metadata.skill_loadout,
          ),
          collabProtocol: resolvePlatformCollabProtocol(metadata.collab_protocol, {
            providerId: "codex",
            roleText: text(seat.responsibility ?? metadata.responsibility, "") || undefined,
            threadText: seatName,
          }),
          heartbeatIntervalSeconds: readSeatAutomationHeartbeatSeconds(metadata),
        });
      }
    }

  const launchResult = launchDetachedWorkstationOneShot({
    projectId,
    workstationId: recipientId,
    messageId,
    providerId,
    seatName,
    ignoreAutomationSwitch: !automationEnabled,
  });

    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      agent_id: recipientId,
      message_type: "agent_ack",
      title: `真实线程处理已启动 / ${seatName}`,
      body: [
        automationEnabled
          ? `平台已按 ${seatName} 的 NPC 自动化设置拉起真实 ${platformProviderLabel(providerId)} 处理器。`
          : `平台已把这一句话派给 ${seatName} 的绑定 ${platformProviderLabel(providerId)} 线程做单次处理，用户不需要手动启动本机桥。`,
        messageId ? `派单消息：${messageId}` : "",
        launchResult.launched ? "目标电脑后台接收：已启动" : `启动失败：${launchResult.error || "未知错误"}`,
        launchResult.stdoutPath ? `stdout：${launchResult.stdoutPath}` : "",
        launchResult.stderrPath ? `stderr：${launchResult.stderrPath}` : "",
        "平台会同步桌面提问、最小回执和最终结果；完整处理过程留在绑定桌面线程中可追踪。",
      ].filter(Boolean).join("\n"),
      sender_type: "agent",
      sender_id: recipientId,
      recipient_type: "thread_workstation",
      recipient_id: recipientId,
      status: launchResult.launched ? "in_progress" : "failed",
    });

    revalidateProjectSurfaces(projectId);
    redirect(
      withQueryValue(
        returnTo,
        launchResult.launched ? "team_notice" : "team_error",
        launchResult.launched
          ? automationEnabled
            ? `${seatName} 的真实 ${platformProviderLabel(providerId)} 自动处理器已启动，等待线程回写结果`
          : `${seatName} 的单次 ${platformProviderLabel(providerId)} 派单已启动；平台会同步桌面过程和回执`
          : `${seatName} 的真实处理器启动失败：${launchResult.error ?? "请检查本机 Python / Codex CLI / 绑定线程"}`,
      ),
    );
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "启动真实线程处理失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 启动Npc单次线程处理(projectId: string, workstationId: string, messageId: string) {
  try {
    await ensureProjectCollaborationAccess(projectId);
    const workstationsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const workstations = asArray<Record<string, unknown>>(workstationsResult?.data ?? workstationsResult);
    const seat =
      workstations.find((item) =>
        workstationLookupKeys(item).some((candidate) => candidate === workstationId),
      ) ?? null;
    if (!seat) {
      throw new Error("没有找到这个 NPC，无法启动单次线程处理。");
    }

    const metadata = seat.metadata && typeof seat.metadata === "object" ? (seat.metadata as Record<string, unknown>) : {};
    const seatName = text(seat.name ?? seat.workstation_name, workstationId) || "NPC";
    const providerId =
      normalizePlatformProviderId(
        seat.ai_provider_id ?? seat.ai_provider ?? metadata.provider_id ?? metadata.provider_label,
      ) || "codex";
    const recipientId = text(seat.row_id ?? seat.rowId ?? seat.id ?? seat.config_id, "") || workstationId;
    const messageResult = await getJson(
      `/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&limit=200`,
    );
    const sourceMessage =
      asArray<Record<string, unknown>>(messageResult?.data ?? messageResult).find((item) => text(item.id, "") === messageId) ??
      null;
    const sourceTitle = text(sourceMessage?.title, "NPC 单次处理");
    const sourceBody = text(sourceMessage?.body, "");
    let adapterConfig: Record<string, unknown> = {};
    try {
      const configResult = await getJson(
        `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(recipientId)}/adapter-config`,
      );
      adapterConfig = (configResult?.data && typeof configResult.data === "object" ? configResult.data : {}) as Record<string, unknown>;
    } catch {
      adapterConfig = {};
    }
    const deliveryLabel = text(adapterConfig.delivery_label, "");
    const deliveryWarning = text(adapterConfig.delivery_warning, "");
    const deliveryMode = text(adapterConfig.delivery_mode, "");
    const desktopVisible = Boolean(adapterConfig.desktop_visible);
    const computerNodeId = text(
      seat.computer_node_id ?? seat.computerNodeId ?? metadata.computer_node_id ?? metadata.computerNodeId,
      "",
    );
    const shouldUseDesktopRunnerDelivery =
      providerId === "codex" && (deliveryMode === "codex_desktop_ui" || (desktopVisible && deliveryLabel.includes("桌面")));
    let runnerSummary = summarizeRunnerDispatchState(null);
    if (computerNodeId) {
      try {
        const computerNodesResult = await getJson(`/api/projects/${projectId}/computer-nodes`);
        const computerNodes = asArray<Record<string, unknown>>(computerNodesResult?.data ?? computerNodesResult);
        const computerNode =
          computerNodes.find((item) => text(item.id ?? item.node_id, "") === computerNodeId)
          ?? null;
        runnerSummary = summarizeRunnerDispatchState(computerNode);
      } catch {
        runnerSummary = summarizeRunnerDispatchState(null);
      }
    }
    const queuesForRecovery = runnerSummary.canQueue && !runnerSummary.canDispatch;
    const runnerDeliveryLabel = queuesForRecovery ? "恢复队列" : "执行电脑队列";
    const runnerDeliveryTitle = queuesForRecovery
      ? `已记录到恢复队列 / ${seatName}`
      : `已投递到执行电脑 / ${seatName}`;
    try {
      const runnerBody = shouldUseDesktopRunnerDelivery
        ? JSON.stringify(
            {
              kind: "codex.desktop.dispatch",
              project_id: projectId,
              workstation_id: recipientId,
              message_id: messageId,
              provider_id: providerId,
              title: sourceTitle || `NPC 派工：${seatName}`,
            },
            null,
            2,
          )
        : [
            `目标 NPC：${seatName}`,
            `目标工位：${recipientId}`,
            messageId ? `平台消息：${messageId}` : "",
            sourceBody || "请处理这条平台派工，并回写最小回执和最终结果。",
          ].filter(Boolean).join("\n\n");
      const runnerCommand = await postJson(`/api/collaboration/projects/${projectId}/runner-commands`, {
        title: sourceTitle ? `NPC 派工：${sourceTitle}` : `NPC 派工：${seatName}`,
        body: runnerBody,
        workstation_id: recipientId,
        metadata: {
          source_message_id: messageId,
          target_workstation_id: recipientId,
          delivery_mode: shouldUseDesktopRunnerDelivery ? "codex_desktop_ui" : deliveryMode || null,
          desktop_visible_capability: desktopVisible,
        },
      });
      const runnerData =
        runnerCommand && typeof runnerCommand === "object" && "data" in runnerCommand
          ? ((runnerCommand as Record<string, unknown>).data as Record<string, unknown>)
          : (runnerCommand as Record<string, unknown>);
      const runnerDeliveryBody = queuesForRecovery
        ? [
            `平台已记录这条派工，等待 ${seatName} 所在电脑恢复后继续处理。`,
            text(runnerData?.recipient_id, "") ? `执行电脑 Runner：${text(runnerData?.recipient_id, "")}` : "",
            text(runnerData?.id, "") ? `队列消息：${text(runnerData?.id, "")}` : "",
            messageId ? `派单消息：${messageId}` : "",
            runnerSummary.detail || "目标电脑最近在线但尚未恢复持续接单，平台不会把这条派工误报成已执行。",
          ].filter(Boolean).join("\n")
        : [
            `平台已把这条派工送到 ${seatName} 所在电脑的 Runner 队列。`,
            text(runnerData?.recipient_id, "") ? `执行电脑 Runner：${text(runnerData?.recipient_id, "")}` : "",
            text(runnerData?.id, "") ? `队列消息：${text(runnerData?.id, "")}` : "",
            messageId ? `派单消息：${messageId}` : "",
            shouldUseDesktopRunnerDelivery
              ? "目标电脑已接入；平台正在等待执行电脑把派单送进绑定桌面线程并确认可见。"
              : desktopVisible
                ? "目标电脑已接入；执行电脑接单后会继续同步过程回执。"
                : deliveryWarning || "目标电脑接单后会回写最小回执；如桌面线程未连接，平台会显示待收口状态。",
          ].filter(Boolean).join("\n");
      await postJson("/api/collaboration/messages", {
        project_id: projectId,
        agent_id: recipientId,
        message_type: "agent_ack",
        title: runnerDeliveryTitle,
        body: runnerDeliveryBody,
        sender_type: "agent",
        sender_id: recipientId,
        recipient_type: "thread_workstation",
        recipient_id: recipientId,
        status: queuesForRecovery ? "queued" : "in_progress",
        metadata: {
          source_message_id: messageId,
          runner_command_id: text(runnerData?.id, "") || null,
          runner_id: text(runnerData?.recipient_id, "") || null,
          delivery_label: shouldUseDesktopRunnerDelivery ? "等待桌面确认" : runnerDeliveryLabel,
          delivery_mode: shouldUseDesktopRunnerDelivery ? "codex_desktop_ui" : deliveryMode || null,
          desktop_visible_capability: desktopVisible,
          runner_dispatch_state: runnerSummary.state,
          runner_dispatch_detail: runnerSummary.detail,
          runner_can_queue: runnerSummary.canQueue,
          runner_can_dispatch: runnerSummary.canDispatch,
        },
      });
      revalidateProjectSurfaces(projectId);
      return {
        launched: true,
        providerId,
        seatName,
        deliveryLabel: shouldUseDesktopRunnerDelivery ? "等待桌面确认" : runnerDeliveryLabel,
        deliveryWarning,
        desktopVisible,
        launcher: shouldUseDesktopRunnerDelivery ? "runner-desktop-dispatch" : "runner-command",
        stdoutPath: null,
        stderrPath: null,
        error: null,
      };
    } catch (runnerError) {
      const runnerErrorMessage = runnerError instanceof Error ? runnerError.message : "目标电脑队列投递失败";
      const runnerErrorDetails =
        runnerError instanceof Error
          ? objectRecord((runnerError as Error & { details?: unknown }).details)
          : {};
      const blockedReasonLabel = text(runnerErrorDetails.blocked_reason, "");
      const blockedReasonCode = text(runnerErrorDetails.blocked_reason_code, "");
      const blockedReasonDetail = blockedReasonLabel
        ? `${blockedReasonLabel}：${runnerErrorMessage}`
        : runnerErrorMessage;
      if (booleanFromUnknown(runnerErrorDetails.can_queue, false)) {
        const queuedLabel = blockedReasonLabel || "等待电脑恢复";
        await postJson("/api/collaboration/messages", {
          project_id: projectId,
          agent_id: recipientId,
          message_type: "agent_ack",
          title: `已记录到恢复队列 / ${seatName}`,
          body: [
            `平台已记录这条派工，等待 ${seatName} 所在电脑恢复后继续处理。`,
            `当前状态：${queuedLabel}`,
            `原因：${blockedReasonDetail}`,
            messageId ? `派单消息：${messageId}` : "",
            "恢复前不会误报成已执行；可在目标电脑恢复后继续，或改派到其他在线电脑。",
          ].filter(Boolean).join("\n"),
          sender_type: "agent",
          sender_id: recipientId,
          recipient_type: "thread_workstation",
          recipient_id: recipientId,
          status: "queued",
          metadata: {
            source_message_id: messageId,
            delivery_label: "恢复队列",
            runner_delivery_failed: false,
            blocked_reason_code: blockedReasonCode || null,
            blocked_reason_label: queuedLabel,
            blocked_taxonomy: {
              blocked_reason_code: blockedReasonCode || "runner_recovery_queue",
              blocked_reason_label: queuedLabel,
              runner_delivery_failed: false,
              can_queue: true,
              can_dispatch: false,
            },
          },
        });
        revalidateProjectSurfaces(projectId);
        return {
          launched: true,
          providerId,
          seatName,
          deliveryLabel: "恢复队列",
          deliveryWarning,
          desktopVisible,
          launcher: "runner-command",
          stdoutPath: null,
          stderrPath: null,
          error: null,
        };
      }
      const blockedRecoveryHint =
        blockedReasonCode === "runner_stale"
          ? "这台电脑最近在线，但持续接单心跳已过期。请回到目标电脑重新运行持续接单命令。"
          : blockedReasonCode === "runner_unbound"
            ? "这个 NPC 还没有接入可用执行程序。先在目标电脑完成持续接单接入，再重新派发。"
            : blockedReasonCode === "runner_offline" || blockedReasonCode === "runner_missing"
              ? "目标电脑当前离线或执行程序不可用。请先重连目标电脑，或改派到其他在线电脑。"
              : blockedReasonCode === "runner_not_started"
                ? "目标电脑还没有开始持续心跳。请先运行持续接单命令，再重新派发。"
                : blockedReasonCode === "computer_node_unbound"
                  ? "这个 NPC 还没有绑定电脑。请先完成电脑接入和线程绑定。"
                  : blockedReasonCode === "provider_disabled" || blockedReasonCode === "provider_missing"
                    ? "目标执行通道当前不可用。请先恢复执行通道配置，再重新派发。"
                    : "请确认这个 NPC 已绑定在线电脑，并且目标电脑的持续接单程序正在运行。";
      console.warn("投递执行电脑队列失败:", runnerError);
      await postJson("/api/collaboration/messages", {
        project_id: projectId,
        agent_id: recipientId,
        message_type: "agent_ack",
        title: `${blockedReasonLabel || "执行电脑未接单"} / ${seatName}`,
        body: [
          `平台没有把这条派工送到 ${seatName} 所在电脑。`,
          `当前状态：${blockedReasonLabel || "状态未知，先检查接入"}`,
          `原因：${blockedReasonDetail}`,
          messageId ? `派单消息：${messageId}` : "",
          blockedRecoveryHint,
        ].filter(Boolean).join("\n"),
        sender_type: "agent",
        sender_id: recipientId,
        recipient_type: "thread_workstation",
        recipient_id: recipientId,
        status: "failed",
        metadata: {
          source_message_id: messageId,
          delivery_label: "执行电脑队列",
          runner_delivery_failed: true,
          blocked_reason_code: blockedReasonCode || null,
          blocked_reason_label: blockedReasonLabel || null,
          blocked_taxonomy: {
            blocked_reason_code: blockedReasonCode || "runner_delivery_failed",
            blocked_reason_label: blockedReasonLabel || "状态未知，先检查接入",
            runner_delivery_failed: true,
            can_queue: runnerErrorDetails.can_queue ?? null,
            can_dispatch: runnerErrorDetails.can_dispatch ?? null,
          },
        },
      });
      revalidateProjectSurfaces(projectId);
      return {
        launched: false,
        providerId,
        seatName,
        deliveryLabel: "执行电脑队列",
        deliveryWarning,
        desktopVisible,
        launcher: "runner-command",
        stdoutPath: null,
        stderrPath: null,
        error: blockedReasonDetail,
      };
    }

  const launchResult = launchDetachedWorkstationOneShot({
    projectId,
    workstationId: recipientId,
    messageId,
    providerId,
    seatName,
    ignoreAutomationSwitch: true,
  });

    await postJson("/api/collaboration/messages", {
      project_id: projectId,
      agent_id: recipientId,
      message_type: "agent_ack",
      title: `单次线程处理已启动 / ${seatName}`,
      body: [
        `平台已把这一句话交给 ${seatName} 的 ${deliveryLabel || platformProviderLabel(providerId)} 做单次处理，用户不需要手动启动本机桥。`,
        desktopVisible
          ? "投递状态：正在确认目标 Codex Desktop 线程是否已收到；确认后会在本对话框显示“等待最终回复”。"
          : "投递状态：平台内部通道处理中；若未连接桌面实时桥，本对话框仍会显示最小回执和最终结果。",
        deliveryWarning,
        messageId ? `派单消息：${messageId}` : "",
        launchResult.launched ? "目标电脑后台接收：已启动" : `启动失败：${launchResult.error || "未知错误"}`,
        launchResult.stdoutPath ? `stdout：${launchResult.stdoutPath}` : "",
        launchResult.stderrPath ? `stderr：${launchResult.stderrPath}` : "",
        "平台会同步桌面提问、最小回执和最终结果；完整处理过程留在绑定桌面线程中可追踪。",
      ].filter(Boolean).join("\n"),
      sender_type: "agent",
      sender_id: recipientId,
      recipient_type: "thread_workstation",
      recipient_id: recipientId,
      status: launchResult.launched ? "in_progress" : "failed",
      metadata: {
        source_message_id: messageId,
        launch_state: launchResult.launched ? "delivery_pending_confirmation" : "launch_failed",
        delivery_label: deliveryLabel || platformProviderLabel(providerId),
        desktop_visible_capability: desktopVisible,
        stdout_path: launchResult.stdoutPath ?? null,
        stderr_path: launchResult.stderrPath ?? null,
      },
    });

    revalidateProjectSurfaces(projectId);
    return {
      launched: Boolean(launchResult.launched),
      providerId,
      seatName,
      deliveryLabel,
      deliveryWarning,
      desktopVisible,
      launcher: launchResult.launcher ?? null,
      stdoutPath: launchResult.stdoutPath ?? null,
      stderrPath: launchResult.stderrPath ?? null,
      error: launchResult.launched ? null : launchResult.error ?? "请检查本机 Python / Codex CLI / 绑定线程",
    };
  } catch (error) {
    return {
      launched: false,
      providerId: null,
      seatName: null,
      deliveryLabel: null,
      deliveryWarning: null,
      desktopVisible: false,
      launcher: null,
      stdoutPath: null,
      stderrPath: null,
      error: error instanceof Error ? error.message : "启动单次线程处理失败",
    };
  }
}

export async function 准备Codex线程上岗包(projectId: string, workstationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "npc-create");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const workstationsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const workstations: Record<string, unknown>[] = asArray<Record<string, unknown>>(workstationsResult?.data ?? workstationsResult);
    const seat: Record<string, unknown> | null =
      workstations.find((item) =>
        workstationLookupKeys(item as Record<string, unknown>).some((candidate) => candidate === workstationId),
      ) ?? null;
    if (!seat) throw new Error("没有找到这个 NPC。");

    const metadata = seat?.metadata && typeof seat.metadata === "object" ? (seat.metadata as Record<string, unknown>) : {};
    const seatName = text(seat?.name ?? seat?.workstation_name, workstationId || "Codex NPC") || "Codex NPC";
    const responsibility = text(seat?.responsibility ?? metadata.responsibility, "") || "按 Boss NPC 派单推进";
    const rawThreadId =
      text(formData.get("codex_thread_id"), "") ||
      text(formData.get("source_workstation_id"), "") ||
      text(seat?.source_workstation_id ?? metadata.source_workstation_id, "") ||
      text(metadata.target_thread_id ?? metadata.bound_thread_id ?? metadata.thread_id, "");
    if (!rawThreadId) {
      throw new Error("请先填入用户已经创建好的 Codex 线程 ID，再生成上岗包。");
    }
    const sourceWorkstationId = rawThreadId.toLowerCase().startsWith("codex-session-")
      ? rawThreadId
      : `codex-session-${slugifyAscii(rawThreadId, slugifyAscii(seatName, "codex-thread"))}`;
    const model = text(seat?.model ?? metadata.model, "gpt-5.4") || "gpt-5.4";
    const computerNodeId = text(seat?.computer_node_id ?? seat?.computerNodeId ?? metadata.computer_node_id, "") || null;
    const logicalWorkstationId =
      text(seat?.workstation_id ?? seat?.workstationId ?? metadata.workstation_id ?? metadata.workstationId, "") ||
      null;
    const logicalWorkstationsResult = await getJson(`/api/projects/${projectId}/workstations`).catch(() => ({ data: [] }));
    const logicalWorkstations = asArray<Record<string, unknown>>(logicalWorkstationsResult?.data ?? logicalWorkstationsResult);
    const logicalWorkstation = logicalWorkstationId
      ? logicalWorkstations.find((item) =>
          [recordId(item), text(item.config_id, ""), text(item.name, "")].includes(logicalWorkstationId),
        ) ?? null
      : null;
    const workstationName =
      text(logicalWorkstation?.name, "") ||
      text(seat?.workstation_name ?? seat?.workstationName ?? metadata.workstation_name ?? metadata.workstationName, "") ||
      (logicalWorkstationId ? logicalWorkstationId : null);
    const workstationExtra = readRecord(logicalWorkstation?.extra_data ?? logicalWorkstation?.extraData);
    const config = readProjectCollaborationConfig(project);
    const workstationProfiles = readRecord(config.workstation_profiles);
    const workstationProfile = readRecord(
      (logicalWorkstationId && workstationProfiles[logicalWorkstationId]) ||
        (workstationName && workstationProfiles[workstationName]) ||
        (computerNodeId && workstationProfiles[computerNodeId]) ||
        {},
    );
    const workstationSlug = displaySlug(workstationName || logicalWorkstationId || computerNodeId, "unassigned");
    const workstationKnowledgePath =
      repoRelativePath(
        logicalWorkstation?.knowledge_path ??
          logicalWorkstation?.knowledgePath ??
          workstationExtra.knowledge_path ??
          workstationExtra.knowledgePath ??
          workstationProfile.knowledge_path ??
          workstationProfile.knowledgePath,
      ) || `docs/workstations/${workstationSlug}.md`;
    const skillLoadout = mergePlatformSkillLoadout(
      seat?.skill_loadout,
      seat?.skillLoadout,
      metadata.additional_skill_ids,
      metadata.skill_loadout,
    );
    const storedKnowledge =
      metadata.npc_knowledge && typeof metadata.npc_knowledge === "object"
        ? (metadata.npc_knowledge as Record<string, unknown>)
        : {};
    const npcKnowledge = buildNpcKnowledgeProfile({
      seatId: workstationId,
      name: seatName,
      responsibility,
      knowledgeSlug: text(storedKnowledge.slug ?? metadata.npc_identity_key, "").replace(/^npc:/, "") || null,
      knowledgeSummary: text(storedKnowledge.summary, "") || null,
      knowledgeHandoffPath: text(storedKnowledge.handoff_path, "") || null,
      knowledgeTags: asArray<string>(storedKnowledge.tags).map((item) => text(item)).filter(Boolean),
    });
    const seatGroupKey = (item: Record<string, unknown>) =>
      text(item.workstation_id ?? item.workstationId, "") ||
      text(item.computer_node_id ?? item.computerNodeId, "");
    const myGroupKey = logicalWorkstationId || computerNodeId || "";
    const sameWorkstationDirectory = workstations
      .filter((item) => recordId(item) !== workstationId && recordId(item) !== recordId(seat) && seatGroupKey(item) === myGroupKey)
      .map((item) => {
        const itemMeta = readRecord(item.metadata);
        return `${text(item.name ?? item.workstation_name, recordId(item))}（${text(item.responsibility ?? itemMeta.responsibility, "待补职责")}）`;
      })
      .filter(Boolean)
      .slice(0, 12);
    const leadByLogicalWorkstation = new Map<string, string>();
    for (const item of logicalWorkstations) {
      const wsId = recordId(item);
      const lead = text(item.lead_seat_id ?? item.leadSeatId, "");
      if (wsId && lead) leadByLogicalWorkstation.set(wsId, lead);
    }
    const crossWorkstationLeads = workstations
      .filter((item) => {
        const id = recordId(item);
        const group = seatGroupKey(item);
        if (!id || !group || group === myGroupKey) return false;
        const identities = recordIdentitySet(item);
        const logicalLead = leadByLogicalWorkstation.get(group);
        if (logicalLead) return identities.has(logicalLead);
        const itemMeta = readRecord(item.metadata);
        const profile = readRecord(workstationProfiles[group]);
        const profileLead = text(profile.lead_seat_id ?? profile.leadSeatId, "");
        return profileLead ? identities.has(profileLead) : Boolean(itemMeta.is_lead ?? itemMeta.isLead);
      })
      .map((item) => {
        const group = seatGroupKey(item);
        const targetWorkstationName =
          text(logicalWorkstations.find((ws) => recordId(ws) === group || text(ws.config_id, "") === group)?.name, "") ||
          text(item.workstation_name ?? item.workstationName ?? item.workstation_id ?? item.workstationId ?? item.computer_node_id, "其他工位");
        return `${text(item.name ?? item.workstation_name, recordId(item))}（${targetWorkstationName} 工位长）`;
      })
      .filter(Boolean)
      .slice(0, 12);
    const readPaths = normalizeStringList(seat?.read_paths ?? metadata.read_paths);
    const writePaths = normalizeStringList(seat?.write_paths ?? metadata.write_paths ?? metadata.git_boundary);
    const collabProtocol = enrichNpcCollabProtocolWithRepoContext(
      project,
      resolvePlatformCollabProtocol(metadata.collab_protocol, {
        providerId: "codex",
        roleText: responsibility,
        threadText: seatName,
      }),
      {
        gitBoundary: writePaths,
        handoffPath: npcKnowledge.handoff_path,
      },
    );
    const repoContext = resolvePlatformRepoContext(collabProtocol.repo_context);
    const launchPrompt = buildCodexThreadLaunchPrompt({
      projectId,
      projectName: text(project?.name, projectId),
      repositoryUrl: (repoContext?.repository_url ?? text(project?.github_url ?? project?.githubUrl, "")) || null,
      localGitUrl: text(project?.local_git_url ?? project?.localGitUrl, "") || null,
      branch: (repoContext?.branch ?? text(project?.develop_branch ?? project?.default_branch, "")) || null,
      seatName,
      responsibility,
      sourceWorkstationId,
      handoffPath: npcKnowledge.handoff_path,
      knowledgeDepositPath: npcKnowledge.knowledge_deposit_path,
      skillDepositPath: npcKnowledge.skill_deposit_path,
      needDepositPath: npcKnowledge.need_deposit_path,
      taskDepositPath: npcKnowledge.task_deposit_path,
      workstationName,
      workstationKnowledgePath,
      npcKnowledgeSummary: npcKnowledge.summary,
      sameWorkstationDirectory,
      crossWorkstationLeads,
      skills: skillLoadout,
      readPaths,
      writePaths,
    });

    await ensureNpcKnowledgeDoc({
      handoffPath: npcKnowledge.handoff_path,
      knowledgeDepositPath: npcKnowledge.knowledge_deposit_path,
      skillDepositPath: npcKnowledge.skill_deposit_path,
      needDepositPath: npcKnowledge.need_deposit_path,
      taskDepositPath: npcKnowledge.task_deposit_path,
      seatName,
      responsibility,
      projectId,
      additionalSkillIds: skillLoadout,
      providerLabel: "Codex",
      sourceWorkstationId,
      computerNodeId,
      model,
      collabProtocol,
    });

    const automationEnabled = readSeatAutomationEnabled(metadata, false);
    const continuity = automationEnabled
      ? await ensureCodexSeatAutonomyBridge({
          projectId,
          seatName,
          responsibility,
          sourceWorkstationId,
          handoffPath: npcKnowledge.handoff_path,
          knowledgeDepositPath: npcKnowledge.knowledge_deposit_path,
          skillDepositPath: npcKnowledge.skill_deposit_path,
          needDepositPath: npcKnowledge.need_deposit_path,
          taskDepositPath: npcKnowledge.task_deposit_path,
          computerNodeId,
          model,
          additionalSkillIds: skillLoadout,
          collabProtocol,
          heartbeatIntervalSeconds: readSeatAutomationHeartbeatSeconds(metadata),
        })
      : { consumerScript: null, heartbeat: null };

    await patchJson(
      `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(workstationId)}`,
      {
        ai_provider: "Codex",
        ai_provider_id: "codex",
        source_workstation_id: sourceWorkstationId,
        target_thread_id: sourceWorkstationId,
        bound_thread_id: sourceWorkstationId,
        model,
        metadata: mergeSeatMetadata(metadata, {
          seat_type: "codex",
          provider_id: "codex",
          provider_label: "Codex",
          source_workstation_id: sourceWorkstationId,
          target_thread_id: sourceWorkstationId,
          source_thread_id: sourceWorkstationId,
          bound_thread_id: sourceWorkstationId,
          thread_kind: "Codex",
          thread_health: "已登记",
          bridge_health_label: automationEnabled ? "watcher ready" : "已登记",
          additional_skill_ids: skillLoadout,
          skill_loadout: skillLoadout,
          npc_knowledge: npcKnowledge,
          npc_identity_key: npcKnowledge.key,
          collab_protocol: collabProtocol,
          codex_launch_prompt: launchPrompt,
          codex_launch_prompt_updated_at: new Date().toISOString(),
        }),
      },
    );

    revalidateProjectSurfaces(projectId);
    revalidatePath(`/projects/${projectId}/workbench`);
    let nextPath = withQueryValue(
      returnTo,
      "team_notice",
      `已为 ${seatName} 绑定用户创建的 Codex 线程并生成上岗包${continuity.consumerScript ? `，consumer：${continuity.consumerScript}` : ""}${continuity.heartbeat ? `，心跳：${continuity.heartbeat.id}` : ""}`,
    );
    nextPath = withQueryValue(nextPath, "seat", workstationId);
    redirect(nextPath);
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "准备 Codex 线程上岗包失败";
    let nextPath = withQueryValue(returnTo, "team_error", message);
    nextPath = withQueryValue(nextPath, "seat", workstationId);
    redirect(nextPath);
  }
}

export async function 校准Claude席位会话(projectId: string, workstationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "npc-create");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const workstationsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const workstations = asArray<any>(workstationsResult?.data ?? workstationsResult);
    const seat =
      workstations.find((item) =>
        workstationLookupKeys(item as Record<string, unknown>).some((candidate) => candidate === workstationId),
      ) ?? null;
    if (!seat) {
      throw new Error("没有找到这个 Claude 席位");
    }

    const metadata = seat?.metadata && typeof seat.metadata === "object" ? (seat.metadata as Record<string, unknown>) : {};
    const providerId =
      normalizePlatformProviderId(
        seat?.ai_provider_id ??
          seat?.ai_provider ??
          metadata.provider_id ??
          metadata.provider_label ??
          platformProviderIdFromSeat(seat),
      ) || "claude";
    if (providerId !== "claude") {
      throw new Error("这个 NPC 当前不是 Claude 席位。");
    }

    const seatName = text(seat?.name ?? seat?.workstation_name, workstationId) || "Claude 席位";
    const sourceWorkstationId = text(seat?.source_workstation_id ?? metadata.source_workstation_id, "") || null;
    if (!text(sourceWorkstationId, "").toLowerCase().startsWith("claude-session-")) {
      throw new Error("这个 NPC 还没有绑定 Claude 会话，暂时不能自动唤醒。");
    }
    const model = text(seat?.model ?? metadata.model, "sonnet") || "sonnet";
    const registration = await ensureClaudeSeatSessionRegistration({
      seatName,
      sourceWorkstationId,
      model,
    });
    const activation = await launchClaudeSeatSession({
      seatName,
      sourceWorkstationId,
      model,
    });
    const providerLabel =
      text(seat?.ai_provider ?? metadata.provider_label ?? metadata.provider_id, "") || platformProviderLabel(providerId);
    const provisioning = await readNpcProvisioningSummary({
      seatId: workstationId,
      seatName,
      providerId,
      providerLabel,
      sourceWorkstationId,
    });

    revalidateProjectSurfaces(projectId);
    let notice = `已校准 ${seatName} 的 Claude 接入`;
    if (registration) {
      notice += `，已登记 Claude session ${registration.sessionId}`;
    }
    if (activation?.launchSummary) {
      notice += `，${activation.launchSummary}`;
    }
    notice += ` / 开箱状态：${provisioning.label}${provisioning.missing.length ? `（${provisioning.missing.join("、")}）` : ""}`;
    let nextPath = withQueryValue(returnTo, "team_notice", notice);
    nextPath = withQueryValue(nextPath, "seat", workstationId);
    redirect(nextPath);
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "校准 Claude 席位会话失败";
    let nextPath = withQueryValue(returnTo, "team_error", message);
    nextPath = withQueryValue(nextPath, "seat", workstationId);
    redirect(nextPath);
  }
}

export async function 补齐项目Npc固定知识库(projectId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "npc-create");
  try {
    const { project } = await ensureProjectCollaborationAccess(projectId);
    const collaborationConfig =
      project?.collaboration_config && typeof project.collaboration_config === "object"
        ? (project.collaboration_config as Record<string, unknown>)
        : {};
    const skillLibrary = asArray<any>(collaborationConfig.skill_library ?? collaborationConfig.skillLibrary);
    const workstations = asArray<any>(
      collaborationConfig.thread_workstations ??
      collaborationConfig.threadWorkstations ??
      collaborationConfig.workstations,
    );
    const npcSeats = workstations.filter((seat) =>
      ["codex", "npc"].includes(text(seat?.metadata?.seat_type ?? seat?.seat_type, "").toLowerCase()),
    );

    let updatedCount = 0;
    let docCount = 0;

    for (const seat of npcSeats) {
      const seatId = text(seat?.id ?? seat?.config_id ?? seat?.row_id, "");
      if (!seatId) continue;

      const metadata =
        seat?.metadata && typeof seat.metadata === "object"
          ? (seat.metadata as Record<string, unknown>)
          : {};
      const automationEnabled = readSeatAutomationEnabled(metadata, false);
      const automationHeartbeatSeconds = readSeatAutomationHeartbeatSeconds(metadata);
      const existingLoadout = asArray<string>(metadata.skill_loadout).map((item) => text(item)).filter(Boolean);
      const additionalSkillIds = (
        asArray<string>(metadata.additional_skill_ids).length
          ? asArray<string>(metadata.additional_skill_ids)
          : splitPlatformSkillLoadout(existingLoadout, skillLibrary).roleSkillIds
      )
        .map((item) => text(item))
        .filter(Boolean);
      const skillLoadout = existingLoadout.length
        ? Array.from(new Set(existingLoadout))
        : mergePlatformSkillLoadout(additionalSkillIds);
      const sourceWorkstationId = text(
        metadata.source_workstation_id ?? seat?.source_workstation_id,
        "",
      ) || null;
      const providerId = platformProviderIdFromSeat(seat) || "codex";
      const providerLabel = text(
        seat?.ai_provider ?? metadata.provider_label ?? metadata.provider_id,
        "",
      ) || platformProviderLabel(providerId);
      const collabProtocol = resolveNpcCollabProtocol(new FormData(), {
        providerId,
        responsibility: text(seat?.responsibility ?? metadata.responsibility, "") || null,
        threadText: text(seat?.name ?? seat?.workstation_name, "") || null,
        existing:
          metadata.collab_protocol && typeof metadata.collab_protocol === "object"
            ? (metadata.collab_protocol as Record<string, unknown>)
            : null,
      });
      const computerNodeId = text(
        seat?.computer_node_id ?? metadata.computer_node_id,
        "",
      ) || null;
      const model = text(seat?.model ?? metadata.model, "gpt-5.4");
      const responsibility = text(seat?.responsibility ?? metadata.responsibility, "") || null;
      const storedKnowledge =
        metadata.npc_knowledge && typeof metadata.npc_knowledge === "object"
          ? (metadata.npc_knowledge as Record<string, unknown>)
          : {};
      const npcKnowledge = buildNpcKnowledgeProfile({
        seatId,
        name: text(seat?.name, "NPC 席位"),
        responsibility,
        knowledgeSlug: text(storedKnowledge.slug ?? metadata.npc_identity_key, "").replace(/^npc:/, "") || null,
        knowledgeSummary: text(storedKnowledge.summary, "") || null,
        knowledgeHandoffPath: text(storedKnowledge.handoff_path, "") || null,
        knowledgeTags: asArray<string>(storedKnowledge.tags),
      });

      await patchJson(
        `/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(seatId)}`,
        {
          name: text(seat?.name, "NPC 席位"),
          computer_node: seat?.computer_node ?? null,
          computer_node_id: computerNodeId,
          ai_provider: providerLabel,
          ai_provider_id: providerId,
          status: text(seat?.status, "idle"),
          responsibility,
          model,
          permission_level: text(seat?.permission_level, "L2"),
          description: text(seat?.description, "") || null,
          notes: text(seat?.notes, "") || null,
          metadata: mergeSeatMetadata(metadata, {
            seat_type: seatTypeForProvider(providerId),
            provider_id: providerId,
            provider_label: providerLabel,
            source_workstation_id: sourceWorkstationId,
            additional_skill_ids: additionalSkillIds,
            skill_loadout: skillLoadout,
            collab_protocol: collabProtocol,
            npc_identity_key: npcKnowledge.key,
            npc_knowledge: npcKnowledge,
            automation_enabled: automationEnabled,
            automation_heartbeat_seconds: automationHeartbeatSeconds,
          }),
        },
      );
      updatedCount += 1;

      if (automationEnabled) {
        await ensureNpcSeatContinuity({
          projectId,
          seatName: text(seat?.name, "NPC 席位"),
          responsibility: responsibility || "",
            sourceWorkstationId,
            handoffPath: npcKnowledge.handoff_path,
            knowledgeDepositPath: npcKnowledge.knowledge_deposit_path,
            skillDepositPath: npcKnowledge.skill_deposit_path,
            needDepositPath: npcKnowledge.need_deposit_path,
            taskDepositPath: npcKnowledge.task_deposit_path,
            computerNodeId,
          model,
          additionalSkillIds,
          providerId,
          providerLabel,
          collabProtocol,
          heartbeatIntervalSeconds: automationHeartbeatSeconds,
        });
      }
      docCount += 1;
    }

    revalidateProjectSurfaces(projectId);
    redirect(
      withQueryValue(
        returnTo,
        "team_notice",
        npcSeats.length
          ? `已校准 ${updatedCount} 个 NPC 的固定知识库，并补齐 ${docCount} 份知识文档`
          : "当前项目还没有可补齐的 NPC 席位",
      ),
    );
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "补齐 NPC 固定知识库失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export async function 删除Codex驻场席位(projectId: string, workstationId: string, formData: FormData) {
  const returnTo = normalizeProjectReturnPath(projectId, formData.get("return_to"), "npc-create");
  try {
    await ensureProjectCollaborationAccess(projectId);
    const workstationsResult = await getJson(`/api/collaboration/projects/${projectId}/thread-workstations`);
    const workstations = asArray<any>(workstationsResult?.data ?? workstationsResult);
    const seat =
      workstations.find((item) =>
        workstationLookupKeys(item as Record<string, unknown>).some((candidate) => candidate === workstationId),
      ) ?? null;
    const metadata = seat?.metadata && typeof seat.metadata === "object" ? (seat.metadata as Record<string, unknown>) : {};
    const seatName = text(seat?.name ?? seat?.workstation_name, workstationId) || workstationId;
    const providerId =
      normalizePlatformProviderId(
        seat?.ai_provider_id ??
          seat?.ai_provider ??
          metadata.provider_id ??
          metadata.provider_label ??
          metadata.provider ??
          platformProviderIdFromSeat(seat),
      ) || "codex";
    const sourceWorkstationId = text(seat?.source_workstation_id ?? metadata.source_workstation_id, "") || null;

    await deleteJson(`/api/collaboration/projects/${projectId}/thread-workstations/${encodeURIComponent(workstationId)}`);
    const cleanupNotes: string[] = [];
    if (providerId === "codex") {
      const cleanup = await cleanupCodexSeatAutonomyArtifacts({ seatName });
      if (cleanup.removedScript || cleanup.removedState || cleanup.removedAutomation) {
        cleanupNotes.push("已清理本地自治桥");
      }
    } else if (providerId === "claude") {
      const cleanup = await cleanupClaudeSeatSessionRegistration({ seatName, sourceWorkstationId });
      if (cleanup.removed) {
        cleanupNotes.push("已清理 Claude 会话登记");
      }
    }
    revalidateProjectSurfaces(projectId);
    redirect(
      withQueryValue(
        returnTo,
        "team_notice",
        cleanupNotes.length ? `NPC 席位已删除，${cleanupNotes.join("，")}` : "NPC 席位已删除",
      ),
    );
  } catch (error) {
    rethrowRedirectError(error);
    const message = error instanceof Error ? error.message : "删除 NPC 席位失败";
    redirect(withQueryValue(returnTo, "team_error", message));
  }
}

export const updateProjectConfig = 更新项目配置;
export const createDevelopmentWorkshopStation = 创建开发工坊工位;
export const updateDevelopmentWorkshopStation = 更新开发工坊工位;
export const deleteDevelopmentWorkshopStation = 删除开发工坊工位;
export const createProjectWorkspace = 创建项目工作区;
export const applyRobotTemplate = 应用机器人协作模板;
export const createCollaborationNode = 创建协作电脑节点;
export const deleteCollaborationNode = 删除协作电脑节点;
export const issueComputerNodePairingToken = 生成电脑配对令牌;
export const revokeComputerNodePairingToken = 吊销电脑配对令牌;
export const issueCollaborationWorkstationAdapterToken = 生成工位接入令牌;
export const revokeCollaborationWorkstationAdapterToken = 吊销工位接入令牌;
export const createCollaborationProvider = 创建协作AI提供方;
export const updateCollaborationProviderExecution = 更新协作AI提供方执行配置;
export const deleteCollaborationProvider = 删除协作AI提供方;
export const createCollaborationWorkstation = 创建协作线程工位;
export const updateCollaborationWorkstationExecution = 更新协作线程工位执行配置;
export const deleteCollaborationWorkstation = 删除协作线程工位;
export const createProjectTask = 创建项目任务;
export const createProjectRequirement = 创建项目需求;
export const recordRequirementAck = 登记需求最小回执;
export const runPlatformAutonomySweep = 运行平台自治推进;
export const bindRunnerToNode = 绑定Runner到电脑节点;
export const unbindRunnerFromNode = 解绑Runner从电脑节点;
export const previewCollaborationMessage = 预演协作消息;
export const submitCollaborationMessage = 提交协作消息;
export const handleCollaborationHumanReview = 处理协作人工审核;
export const handleStaleQueueDecision = 处理旧队列指令;
export const startNpcRelayCollaboration = 启动Npc接力协作;
export const submitRequirementAction = 提交需求动作;
export const promoteRequirementToKnowledge = 沉淀需求到知识库;
export const acceptWorkspaceInvitation = 接受工作台邀请;
export const sendWorkspaceInvitation = 发出邀请;
export const signOutWorkspace = 退出登录;
export const sendRunnerCommand = 下发Runner命令;
export const persistEconomyState = 持久化经营状态;
export const bootstrapFarmMaintainer = 安装农场维护员;
export const dispatchCodexBridgeCommand = 发送Codex桥接指令;
export const requestComputerThreadScan = 请求扫描电脑线程;
export const createNpcWorkstationSeat = 创建Npc驻场席位;
export const updateNpcWorkstationSeat = 更新Npc驻场席位;
export const createCodexWorkstationSeat = 创建Npc驻场席位;
export const updateCodexWorkstationSeat = 更新Npc驻场席位;
export const prepareCodexThreadLaunchPack = 准备Codex线程上岗包;
export const launchNpcRealThreadProcessing = 启动Npc真实线程处理;
export const launchNpcOneShotThreadProcessing = 启动Npc单次线程处理;
export const calibrateClaudeSeatSession = 校准Claude席位会话;
export const backfillProjectNpcKnowledge = 补齐项目Npc固定知识库;
export const deleteNpcWorkstationSeat = 删除Codex驻场席位;
export const deleteCodexWorkstationSeat = 删除Codex驻场席位;
export const updateProjectGitSettings = 更新项目版本库配置;
export const bindProjectGithubAccount = 保存项目Github账号绑定;
export const previewProjectGitSync = 预演项目Git同步;
export const requestProjectGitSync = 登记项目Git同步;
export const previewProjectGitRollback = 预演项目Git回退;
export const requestProjectGitRollback = 登记项目Git回退;
export const createProjectSkill = 创建项目Skill;
export const deleteProjectSkill = 删除项目Skill;
export const importAgencyAgentsSkillPack = 导入AgencyAgents项目Skill包;
export const importGithubProjectSkill = 导入Github项目Skill;

export async function fetchProjectScorecard(projectId: string) {
  try {
    const result = await getJson(`/api/qualification/projects/${encodeURIComponent(projectId)}/scorecard`);
    return result?.data ?? null;
  } catch (error) {
    return null;
  }
}

export async function fetchProjectClaudeContext(projectId: string) {
  try {
    const result = await getJson(`/api/claude-bridge/projects/${encodeURIComponent(projectId)}/context`);
    return result?.data ?? null;
  } catch (error) {
    return null;
  }
}

export async function fetchNpcHandoffContext(projectId: string, npcId: string) {
  try {
    const result = await getJson(`/api/claude-bridge/projects/${encodeURIComponent(projectId)}/npcs/${encodeURIComponent(npcId)}/context`);
    return result?.data ?? null;
  } catch (error) {
    return null;
  }
}

export async function 登记NPC接手交接(
  projectId: string,
  npcId: string,
  body: { task_id: string; summary?: string; next_steps?: string[]; notes?: string },
) {
  const result = await postJson(
    `/api/claude-bridge/projects/${encodeURIComponent(projectId)}/npcs/${encodeURIComponent(npcId)}/handoff`,
    {
      task_id: body.task_id,
      ...(body.summary ? { summary: body.summary } : {}),
      ...(body.next_steps ? { next_steps: body.next_steps } : {}),
      ...(body.notes ? { notes: body.notes } : {}),
    },
  );
  revalidatePath(`/projects/${projectId}`);
  revalidatePath(`/projects/${projectId}/2d-upgrade`);
  revalidatePath("/handoffs");
  return result?.data ?? null;
}

export const recordNpcHandoff = 登记NPC接手交接;




