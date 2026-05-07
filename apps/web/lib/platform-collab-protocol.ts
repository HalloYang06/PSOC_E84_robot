import {
  type PlatformRepoContext,
  resolvePlatformRepoContext,
} from "./platform-repo-context";

type AnyRecord = Record<string, unknown>;

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function normalizeList(value: unknown) {
  const values = Array.isArray(value) ? value : typeof value === "string" ? value.split(/[\n,]/) : [];
  return values.map((item) => text(item)).filter(Boolean);
}

function normalizeNumber(value: unknown, fallback: number, min: number, max: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.round(parsed)));
}

function normalizeBoolean(value: unknown, fallback = false) {
  if (typeof value === "boolean") return value;
  const normalized = text(value, "").toLowerCase();
  if (!normalized) return fallback;
  if (["1", "true", "yes", "on", "y"].includes(normalized)) return true;
  if (["0", "false", "no", "off", "n"].includes(normalized)) return false;
  return fallback;
}

export type PlatformApprovalPolicy = "auto_continue" | "human_review_required";
export type PlatformWorkKind = "implementation" | "review" | "research" | "ops";
export type PlatformProjectProfile = "software" | "robotics" | "embedded" | "education" | "mixed";
export type PlatformTokenPolicyMode = "bounded" | "manual_review" | "trusted_longform";

export type PlatformTokenPolicy = {
  mode: PlatformTokenPolicyMode;
  per_message_limit: number;
  per_round_limit: number;
  daily_budget: number;
  context_window_policy: "summarize_before_long_context" | "full_context_allowed";
};

export type PlatformRunawayPolicy = {
  max_auto_rounds: number;
  human_review_after_rounds: number;
  stop_conditions: string[];
  approval_boundaries: string[];
};

export type PlatformEfficiencyPolicy = {
  parallelism_limit: number;
  prefer_readonly_probe: boolean;
  batch_similar_tasks: boolean;
  require_plan_before_execute: boolean;
};

export type PlatformDebugPolicy = {
  debug_enabled: boolean;
  simulation_first: boolean;
  hardware_write_requires_review: boolean;
};

export type PlatformCollabProtocol = {
  version: "v1";
  provider_id: string | null;
  work_kind: PlatformWorkKind;
  approval_policy: PlatformApprovalPolicy;
  project_profile: PlatformProjectProfile;
  required_capabilities: string[];
  reference_paths: string[];
  repo_context: PlatformRepoContext | null;
  require_minimal_ack: boolean;
  require_final_reply: boolean;
  token_policy: PlatformTokenPolicy;
  runaway_policy: PlatformRunawayPolicy;
  efficiency_policy: PlatformEfficiencyPolicy;
  debug_policy: PlatformDebugPolicy;
};

export const PLATFORM_APPROVAL_POLICY_OPTIONS: Array<{
  id: PlatformApprovalPolicy;
  label: string;
  note: string;
}> = [
  {
    id: "auto_continue",
    label: "自动续推",
    note: "适合纯软件、只读研究和低风险 UI 验收。NPC 先给最小回执，再按预算推进到最终回复。",
  },
  {
    id: "human_review_required",
    label: "人工审核",
    note: "适合机器人、嵌入式、烧录、真实设备、跨电脑环境差异大的任务。AI 先仿真和回执，再等人确认。",
  },
];

export const PLATFORM_WORK_KIND_OPTIONS: Array<{
  id: PlatformWorkKind;
  label: string;
  note: string;
}> = [
  { id: "implementation", label: "实现", note: "改代码、补功能、跑验证，但遵守人审和 token 边界。" },
  { id: "review", label: "评审", note: "偏审查、风险检查、验收和截图证明。" },
  { id: "research", label: "研究", note: "资料整理、方案比较、只读探索和环境摸底。" },
  { id: "ops", label: "运维", note: "桥接、派单、接入、心跳和多电脑环境维护。" },
];

function containsHardwareRisk(raw: string, capabilities: string[]) {
  const caps = capabilities.map((item) => item.toLowerCase());
  return (
    caps.includes("embedded-toolchain") ||
    caps.includes("robotics") ||
    /(robot|机器人|机械臂|电机|舵机|nanopi|开发板|嵌入式|firmware|烧录|串口|jtag|i2c|spi|gpio|stm32|arduino|硬件|上电|传感器|usb)/i.test(raw)
  );
}

function inferWorkKind(options: {
  roleText?: string;
  threadText?: string;
  providerId?: string;
}): PlatformWorkKind {
  const raw = `${text(options.roleText)} ${text(options.threadText)} ${text(options.providerId)}`.toLowerCase();
  if (/(review|审核|评审|风控|proof|验收)/i.test(raw)) return "review";
  if (/(research|研究|方案|参考|调研|资料|只读)/i.test(raw)) return "research";
  if (/(ops|运维|桥接|派单|接入|环境|runner|adapter|heartbeat|心跳)/i.test(raw)) return "ops";
  return "implementation";
}

function inferCapabilities(options: {
  roleText?: string;
  threadText?: string;
  providerId?: string;
}) {
  const raw = `${text(options.roleText)} ${text(options.threadText)} ${text(options.providerId)}`.toLowerCase();
  const capabilities = new Set<string>();
  if (/(unity|3d)/i.test(raw)) capabilities.add("unity");
  if (containsHardwareRisk(raw, [])) capabilities.add("embedded-toolchain");
  if (/(robot|机器人|机械臂|电机|舵机)/i.test(raw)) capabilities.add("robotics");
  if (/(github|repo|git|clone|拉代码)/i.test(raw)) capabilities.add("repo-bootstrap");
  if (/(phaser|farm|map|npc|ui|frontend|界面|前端)/i.test(raw)) capabilities.add("web-game-ui");
  if (/(runner|thread|bridge|automation|heartbeat|codex|claude|qwen|glm|openclaw|线程|自动化)/i.test(raw)) {
    capabilities.add("thread-adapter");
  }
  return Array.from(capabilities);
}

function normalizeProjectProfile(value: unknown, fallback: PlatformProjectProfile): PlatformProjectProfile {
  const normalized = text(value, "").toLowerCase();
  if (["software", "robotics", "embedded", "education", "mixed"].includes(normalized)) {
    return normalized as PlatformProjectProfile;
  }
  return fallback;
}

function inferProjectProfile(options: {
  roleText?: string;
  threadText?: string;
  providerId?: string;
  requiredCapabilities?: string[];
}): PlatformProjectProfile {
  const raw = `${text(options.roleText)} ${text(options.threadText)} ${text(options.providerId)}`.toLowerCase();
  const capabilities = options.requiredCapabilities ?? [];
  if (/(robot|机器人|机械臂|电机|舵机)/i.test(raw) || capabilities.includes("robotics")) return "robotics";
  if (containsHardwareRisk(raw, capabilities)) return "embedded";
  if (/(教育|教程|课程|lesson|course|student|新手)/i.test(raw)) return "education";
  if (capabilities.some((item) => ["unity", "embedded-toolchain", "web-game-ui"].includes(item))) return "mixed";
  return "software";
}

function inferApprovalPolicy(options: {
  roleText?: string;
  threadText?: string;
  providerId?: string;
  requiredCapabilities?: string[];
  projectProfile?: PlatformProjectProfile;
}): PlatformApprovalPolicy {
  const raw = `${text(options.roleText)} ${text(options.threadText)} ${text(options.providerId)}`.toLowerCase();
  const capabilities = options.requiredCapabilities ?? [];
  if (options.projectProfile === "robotics" || options.projectProfile === "embedded") return "human_review_required";
  if (containsHardwareRisk(raw, capabilities)) return "human_review_required";
  if (capabilities.includes("unity")) return "human_review_required";
  return "auto_continue";
}

function defaultTokenPolicy(profile: PlatformProjectProfile, approvalPolicy: PlatformApprovalPolicy): PlatformTokenPolicy {
  if (approvalPolicy === "human_review_required" || profile === "robotics" || profile === "embedded") {
    return {
      mode: "manual_review",
      per_message_limit: 1800,
      per_round_limit: 5000,
      daily_budget: 20000,
      context_window_policy: "summarize_before_long_context",
    };
  }
  if (profile === "education") {
    return {
      mode: "bounded",
      per_message_limit: 2200,
      per_round_limit: 6500,
      daily_budget: 24000,
      context_window_policy: "summarize_before_long_context",
    };
  }
  return {
    mode: "bounded",
    per_message_limit: 2500,
    per_round_limit: 8000,
    daily_budget: 30000,
    context_window_policy: "summarize_before_long_context",
  };
}

function normalizeTokenPolicy(
  value: unknown,
  profile: PlatformProjectProfile,
  approvalPolicy: PlatformApprovalPolicy,
): PlatformTokenPolicy {
  const defaults = defaultTokenPolicy(profile, approvalPolicy);
  const raw = value && typeof value === "object" ? (value as AnyRecord) : {};
  const mode = text(raw.mode, defaults.mode) as PlatformTokenPolicyMode;
  return {
    mode: ["bounded", "manual_review", "trusted_longform"].includes(mode) ? mode : defaults.mode,
    per_message_limit: normalizeNumber(raw.per_message_limit, defaults.per_message_limit, 500, 20000),
    per_round_limit: normalizeNumber(raw.per_round_limit, defaults.per_round_limit, 1000, 50000),
    daily_budget: normalizeNumber(raw.daily_budget, defaults.daily_budget, 1000, 200000),
    context_window_policy:
      text(raw.context_window_policy, defaults.context_window_policy) === "full_context_allowed"
        ? "full_context_allowed"
        : "summarize_before_long_context",
  };
}

function defaultRunawayPolicy(profile: PlatformProjectProfile): PlatformRunawayPolicy {
  const hardwareLike = profile === "robotics" || profile === "embedded";
  return {
    max_auto_rounds: hardwareLike ? 1 : 3,
    human_review_after_rounds: hardwareLike ? 1 : 3,
    stop_conditions: [
      "需求不清或目标冲突",
      "连续两轮没有新的可验证进展",
      "超过 token 预算",
      "需要访问未授权账号、私钥或敏感数据",
    ],
    approval_boundaries: hardwareLike
      ? [
          "真实硬件上电、烧录、写串口、写 GPIO、移动机器人或机械结构",
          "删除文件、回滚历史、推送分支、安装系统级依赖",
          "跨账号或跨项目数据读取",
        ]
      : [
          "删除文件、回滚历史、推送分支、生产环境发布",
          "跨账号或跨项目数据读取",
          "大批量自动派单或超过预算继续执行",
        ],
  };
}

function normalizeRunawayPolicy(value: unknown, profile: PlatformProjectProfile): PlatformRunawayPolicy {
  const defaults = defaultRunawayPolicy(profile);
  const raw = value && typeof value === "object" ? (value as AnyRecord) : {};
  return {
    max_auto_rounds: normalizeNumber(raw.max_auto_rounds, defaults.max_auto_rounds, 0, 20),
    human_review_after_rounds: normalizeNumber(raw.human_review_after_rounds, defaults.human_review_after_rounds, 1, 20),
    stop_conditions: normalizeList(raw.stop_conditions).length ? normalizeList(raw.stop_conditions) : defaults.stop_conditions,
    approval_boundaries: normalizeList(raw.approval_boundaries).length
      ? normalizeList(raw.approval_boundaries)
      : defaults.approval_boundaries,
  };
}

function defaultEfficiencyPolicy(profile: PlatformProjectProfile): PlatformEfficiencyPolicy {
  const hardwareLike = profile === "robotics" || profile === "embedded";
  return {
    parallelism_limit: hardwareLike ? 1 : 2,
    prefer_readonly_probe: true,
    batch_similar_tasks: true,
    require_plan_before_execute: hardwareLike,
  };
}

function normalizeEfficiencyPolicy(value: unknown, profile: PlatformProjectProfile): PlatformEfficiencyPolicy {
  const defaults = defaultEfficiencyPolicy(profile);
  const raw = value && typeof value === "object" ? (value as AnyRecord) : {};
  return {
    parallelism_limit: normalizeNumber(raw.parallelism_limit, defaults.parallelism_limit, 1, 12),
    prefer_readonly_probe: normalizeBoolean(raw.prefer_readonly_probe, defaults.prefer_readonly_probe),
    batch_similar_tasks: normalizeBoolean(raw.batch_similar_tasks, defaults.batch_similar_tasks),
    require_plan_before_execute: normalizeBoolean(raw.require_plan_before_execute, defaults.require_plan_before_execute),
  };
}

function defaultDebugPolicy(profile: PlatformProjectProfile): PlatformDebugPolicy {
  const hardwareLike = profile === "robotics" || profile === "embedded";
  return {
    debug_enabled: true,
    simulation_first: hardwareLike,
    hardware_write_requires_review: hardwareLike,
  };
}

function normalizeDebugPolicy(value: unknown, profile: PlatformProjectProfile): PlatformDebugPolicy {
  const defaults = defaultDebugPolicy(profile);
  const raw = value && typeof value === "object" ? (value as AnyRecord) : {};
  return {
    debug_enabled: normalizeBoolean(raw.debug_enabled, defaults.debug_enabled),
    simulation_first: normalizeBoolean(raw.simulation_first, defaults.simulation_first),
    hardware_write_requires_review: normalizeBoolean(
      raw.hardware_write_requires_review,
      defaults.hardware_write_requires_review,
    ),
  };
}

export function resolvePlatformCollabProtocol(
  value: unknown,
  options: {
    providerId?: string | null;
    roleText?: string;
    threadText?: string;
    repoContext?: unknown;
  } = {},
): PlatformCollabProtocol {
  const base = value && typeof value === "object" ? (value as AnyRecord) : {};
  const providerId = text(base.provider_id ?? options.providerId, "") || null;
  const requiredCapabilities = normalizeList(base.required_capabilities);
  const inferredCapabilities = requiredCapabilities.length
    ? requiredCapabilities
    : inferCapabilities({
        roleText: options.roleText,
        threadText: options.threadText,
        providerId: providerId ?? undefined,
      });
  const projectProfile = normalizeProjectProfile(
    base.project_profile,
    inferProjectProfile({
      roleText: options.roleText,
      threadText: options.threadText,
      providerId: providerId ?? undefined,
      requiredCapabilities: inferredCapabilities,
    }),
  );
  const workKind = text(base.work_kind, "") as PlatformWorkKind;
  const resolvedWorkKind: PlatformWorkKind =
    ["implementation", "review", "research", "ops"].includes(workKind)
      ? workKind
      : inferWorkKind({
          roleText: options.roleText,
          threadText: options.threadText,
          providerId: providerId ?? undefined,
        });
  const approvalPolicy = text(base.approval_policy, "") as PlatformApprovalPolicy;
  const resolvedApprovalPolicy: PlatformApprovalPolicy =
    approvalPolicy === "human_review_required" || approvalPolicy === "auto_continue"
      ? approvalPolicy
      : inferApprovalPolicy({
          roleText: options.roleText,
          threadText: options.threadText,
          providerId: providerId ?? undefined,
          requiredCapabilities: inferredCapabilities,
          projectProfile,
        });
  const repoContext = resolvePlatformRepoContext(base.repo_context ?? options.repoContext);
  return {
    version: "v1",
    provider_id: providerId,
    work_kind: resolvedWorkKind,
    approval_policy: resolvedApprovalPolicy,
    project_profile: projectProfile,
    required_capabilities: inferredCapabilities,
    reference_paths: normalizeList(base.reference_paths),
    repo_context: repoContext,
    require_minimal_ack: base.require_minimal_ack !== false,
    require_final_reply: base.require_final_reply !== false,
    token_policy: normalizeTokenPolicy(base.token_policy, projectProfile, resolvedApprovalPolicy),
    runaway_policy: normalizeRunawayPolicy(base.runaway_policy, projectProfile),
    efficiency_policy: normalizeEfficiencyPolicy(base.efficiency_policy, projectProfile),
    debug_policy: normalizeDebugPolicy(base.debug_policy, projectProfile),
  };
}

export function collabProtocolApprovalLabel(policy: unknown) {
  return policy === "human_review_required" ? "人工审核" : "自动续推";
}

export function collabProtocolWorkKindLabel(kind: unknown) {
  if (kind === "review") return "评审";
  if (kind === "research") return "研究";
  if (kind === "ops") return "运维";
  return "实现";
}

export function collabProjectProfileLabel(profile: unknown) {
  if (profile === "robotics") return "机器人 / 真实设备";
  if (profile === "embedded") return "嵌入式 / 硬件";
  if (profile === "education") return "教育教程";
  if (profile === "mixed") return "混合项目";
  return "纯软件";
}

export function collabTokenPolicySummary(protocol: unknown) {
  const resolved = resolvePlatformCollabProtocol(protocol);
  const token = resolved.token_policy;
  const modeLabel =
    token.mode === "manual_review"
      ? "预算内执行，超预算人审"
      : token.mode === "trusted_longform"
        ? "可信长上下文"
        : "有界预算";
  return `${modeLabel} / 单条 ${token.per_message_limit} / 单轮 ${token.per_round_limit} / 日预算 ${token.daily_budget}`;
}

export function collabRunawayPolicySummary(protocol: unknown) {
  const resolved = resolvePlatformCollabProtocol(protocol);
  const runaway = resolved.runaway_policy;
  return `最多自动 ${runaway.max_auto_rounds} 轮 / 第 ${runaway.human_review_after_rounds} 轮后人审 / ${runaway.stop_conditions.length} 个停止条件`;
}

export function collabEfficiencyPolicySummary(protocol: unknown) {
  const resolved = resolvePlatformCollabProtocol(protocol);
  const efficiency = resolved.efficiency_policy;
  return `并发上限 ${efficiency.parallelism_limit} / ${efficiency.prefer_readonly_probe ? "先只读探针" : "允许直接执行"} / ${efficiency.batch_similar_tasks ? "相似任务合批" : "逐条执行"}`;
}

export function collabDebugPolicySummary(protocol: unknown) {
  const resolved = resolvePlatformCollabProtocol(protocol);
  const debug = resolved.debug_policy;
  return `${debug.debug_enabled ? "允许 AI 调试" : "关闭 AI 调试"} / ${debug.simulation_first ? "仿真优先" : "可直接软件验证"} / ${debug.hardware_write_requires_review ? "硬件写入需人审" : "无硬件写入限制"}`;
}
