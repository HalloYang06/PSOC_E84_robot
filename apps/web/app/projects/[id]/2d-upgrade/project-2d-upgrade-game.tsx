"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useFormStatus } from "react-dom";

import {
  bindProjectGithubAccount,
  createCollaborationNode,
  createDevelopmentWorkshopStation,
  createNpcWorkstationSeat,
  createProjectSkill,
  启用Npc自造Skill,
  fetchNpcHandoffContext,
  fetchProjectClaudeContext,
  fetchProjectScorecard,
  issueComputerNodePairingToken,
  previewProjectGitRollback,
  requestComputerThreadScan,
  recordNpcHandoff,
  requestProjectGitRollback,
  sendWorkspaceInvitation,
  submitCollaborationMessage,
  updateProjectGitSettings,
  updateDevelopmentWorkshopStation,
  updateNpcWorkstationSeat,
} from "../../../actions";
import { useTeamNoticeToast } from "../../../../lib/use-team-notice-toast";
import { TeamNoticeToast } from "../../../../components/team-notice-toast";
import {
  buildComputerOneClickConnectBashCommand,
  buildComputerOneClickConnectCommand,
  buildComputerRunnerWatchBashCommand,
  buildComputerRunnerWatchCommand,
  buildComputerRunnerWatchServiceBashCommand,
  buildComputerRunnerWatchServiceCommand,
  suggestedComputerRunnerId,
} from "../../../../lib/runner-onboarding-commands";
import styles from "./project-2d-upgrade-game.module.css";
import { ClaudeCommandPalette } from "../_components/claude-command-palette";
import { apiClientUrl } from "../../../../lib/api-client-url";
import { BroadcastModal } from "../_components/broadcast-modal";
import { WorkstationProfileEditor } from "../_components/workstation-profile-editor";
import { CrossWorkstationHandoffs } from "../_components/cross-workstation-handoffs";
import { RequirementDispatcher } from "../_components/requirement-dispatcher";

type GameProject = {
  id: string;
  name: string;
  description: string;
  type: string;
  collaboration_config?: Record<string, unknown>;
  github_url?: string;
  local_git_url?: string;
  default_branch?: string;
  develop_branch?: string;
};

type GameStats = {
  requirementCount: number;
  taskCount: number;
  activeTaskCount: number;
  blockedTaskCount: number;
  onlineComputerCount: number;
  computerCount: number;
  messageCount: number;
  tokenSpend: string;
};

type FeedItem = {
  id: string;
  skillId?: string;
  rowId?: string;
  title?: string;
  name?: string;
  type?: string;
  body?: string;
  status: string;
  repoRelativePath?: string;
  source?: string;
  category?: string;
  draftStatus?: string;
  authorSeatId?: string;
  assignedSeatIds?: string[];
  at?: string;
  providerId?: string;
  providerLabel?: string;
  computerNodeId?: string;
  sourceWorkstationId?: string;
  workstationId?: string;
  workstationName?: string;
  responsibility?: string;
  model?: string;
  permissionLevel?: string;
  automationEnabled?: boolean;
  automationHeartbeatSeconds?: number;
  scene?: string;
  avatarKey?: string;
  mapX?: number | null;
  mapY?: number | null;
  skillLoadout?: string[];
  inheritedSkills?: string[];
  knowledgeSummary?: string;
  knowledgeHandoffPath?: string;
  threadScanCount?: number;
  desktopProcessDetected?: boolean;
  desktopBridgeConnected?: boolean;
  desktopDeliveryMode?: string;
  desktopBridgeLabel?: string;
  desktopBridgeNote?: string;
  runnerId?: string;
  runnerWatchState?: string;
  runnerEffectiveStatus?: string;
};

type WorkshopStationItem = {
  id: string;
  label: string;
  icon: string;
  station: string;
  mapScene: string;
  mapLocation: string;
  detail: string;
  modes: string[];
  backendAnchor: string;
  runnerCapabilities: string[];
  aiResponsibilities: string[];
  npcRoleTemplates: string[];
  assignmentKeywords: string[];
  nextActions: string[];
  approvalPolicy: string;
  riskLevel: string;
  assignedNpcIds: string[];
  knowledgeSummary: string;
  knowledgeHandoffPath: string;
  knowledgeTags: string[];
};

type ProjectWorkstation = {
  id: string;
  configId: string;
  name: string;
  description: string | null;
  leadSeatId: string | null;
  reviewPolicy: string | null;
  sortOrder: number;
  seatCount: number;
};

type KnowledgeDocumentItem = {
  id: string;
  title: string;
  repoRelativePath: string;
  scope: string;
  ownerType: string;
  ownerId: string;
  existsInRepo: boolean | null;
  versionRef: string;
  lastSyncedAt: string;
  summary: string;
  tags: string[];
};

type Project2dUpgradeGameProps = {
  project: GameProject;
  apiBaseUrl: string;
  currentUser: {
    name: string;
    email: string;
  };
  stats: GameStats;
  tasks: FeedItem[];
  requirements: FeedItem[];
  messages: FeedItem[];
  computers: FeedItem[];
  projectMembers: FeedItem[];
  workstations: FeedItem[];
  npcSeats: FeedItem[];
  projectWorkstations: ProjectWorkstation[];
  workshopStations: WorkshopStationItem[];
  skills: FeedItem[];
  knowledgeDocuments: KnowledgeDocumentItem[];
  teamNotice?: string;
  teamError?: string;
};

type ServiceHealthState = {
  status: "checking" | "ok" | "error";
  webUrl: string;
  apiBaseUrl: string;
  apiPid?: string;
  apiVersion?: string;
  apiSeenUrl?: string;
  localServices?: Array<{ host: string; port: number; listening: boolean }>;
  message?: string;
};

type RecommendedProjectSkill = {
  id: string;
  label: string;
  note: string;
  recommendedFor: string[];
};

function safeProjectReturnPath(projectId: string, value: string | null | undefined): string {
  const raw = String(value ?? "").trim();
  if (!raw.startsWith(`/projects/${projectId}/`)) return "";
  if (raw.includes("://") || raw.startsWith("//") || raw.includes("\\") || raw.includes("\n") || raw.includes("\r")) return "";
  return raw;
}

function labelProjectReturnPath(value: string): string {
  if (value.includes("/workbench")) return "返回 NPC 工作台";
  if (value.includes("/datasets")) return "返回设备数据工作台";
  if (value.includes("/ai-lab")) return "返回设备数据工作台";
  if (value.includes("/robotics")) return "返回设备数据工作台";
  if (value.includes("/rehab-arm-control")) return "返回专项设备总控台";
  if (value.includes("/observability")) return "返回公司层";
  if (value.includes("/skill-forge")) return "返回能力工坊";
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/cockpit")) return "返回公司层";
  if (value.includes("/unity-client")) return "返回 Unity 工作台";
  return "返回来源页面";
}

const PLATFORM_RECOMMENDED_SKILLS: RecommendedProjectSkill[] = [
  {
    id: "platform-boss-planning",
    label: "平台 Boss 分工规划",
    note: "把用户的一句话需求拆成可执行方案、工位分工、NPC 职责、GitHub 知识库路径和验收口径；Boss 只做规划、派单、收口，不直接替执行 NPC 写实现。",
    recommendedFor: ["Boss NPC", "产品与分工工位", "项目负责人"],
  },
  {
    id: "platform-backend-api",
    label: "平台后端接口与数据",
    note: "负责阅读项目仓库文档，梳理接口、数据模型、数据流、导出格式和迁移风险；输出要能被前端和 QA NPC 复用。",
    recommendedFor: ["后端数据 NPC", "标注与导出工位"],
  },
  {
    id: "platform-frontend-workbench",
    label: "平台前端工作台体验",
    note: "负责从真实用户路径检查页面密度、主操作、工作台布局和状态反馈；提交前必须说明点击步骤和页面状态。",
    recommendedFor: ["前端体验 NPC", "工作台体验工位"],
  },
  {
    id: "platform-dataset-export",
    label: "平台数据集导出",
    note: "关注音频、文本、评分、标注结果的导入导出闭环；每次改动要说明字段来源、兼容旧数据方式和可回滚点。",
    recommendedFor: ["后端数据 NPC", "数据治理 NPC"],
  },
  {
    id: "platform-browser-acceptance",
    label: "平台浏览器验收",
    note: "用用户视角验证页面能不能用、密度是否舒服、核心按钮是否找得到；每次给出截图或明确的路由、操作、结果。",
    recommendedFor: ["QA 验收 NPC", "验收风险工位"],
  },
  {
    id: "platform-cross-station-routing",
    label: "跨工位协作路由",
    note: "同一工位 NPC 互相认识并按职责找人；不同工位只能通过目标工位长 NPC 沟通，回执必须回到发起 NPC 和 Boss 收口。",
    recommendedFor: ["Boss NPC", "工位长 NPC", "协作平台 NPC"],
  },
];

function normalizeSkillLibraryItem(skill: RecommendedProjectSkill) {
  return {
    id: skill.id,
    label: skill.label,
    note: skill.note,
    source: "custom",
    scope: "role",
    recommended_for: skill.recommendedFor,
  };
}

const PANEL_TABS = [
  "development-workshop",
  "human-party",
  "npc-create",
  "computers",
  "skills",
  "exchange",
  "machine-room",
  "git",
] as const;

type ModuleTab = (typeof PANEL_TABS)[number];

const SCORECARD_FIX_TAB: Record<string, ModuleTab> = {
  thread_call_health: "machine-room",
  npc_handover_health: "npc-create",
  human_review_responsiveness: "exchange",
  collaboration_density: "exchange",
  token_spend_7d_yuan: "exchange",
};

function buildWatcherCommand(projectId: string, workstationId: string): string {
  const quote = (value: string) =>
    /^[A-Za-z0-9_\-]+$/.test(value) ? value : `'${value.replace(/'/g, "''")}'`;
  return [
    "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ",
    `"& { $repo = git rev-parse --show-toplevel; if (-not $repo) { throw '请先在项目仓库终端里运行'; }`,
    `; Set-Location $repo; .\\scripts\\start-thread-watcher.ps1 -ProjectId ${quote(projectId)} -WorkstationId ${quote(workstationId)} }"`,
  ].join("");
}

type ModuleLink = {
  label: string;
  short: string;
  hint: string;
  tab: ModuleTab;
  tone: "core" | "agent" | "computer" | "workshop" | "skill" | "review" | "tool";
  primary: string;
  description: string;
  farmSource: string;
};

type PanelAction = {
  id: string;
  label: string;
  summary: string;
  detail: string;
  primaryLabel: string;
  safety: string;
};

type ActionConnectivity = {
  label: string;
  tone: "ready" | "readonly" | "preview" | "review" | "pending";
  detail: string;
};

const UNITY_PUBLIC_PATH = "/unity/education2d";
const UNITY_SCENE_NAME = "Education2D_Ref_InteriorLab";

function SubmitButton({
  label,
  disabled = false,
  pendingLabel = "处理中...",
}: {
  label: string;
  disabled?: boolean;
  pendingLabel?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={disabled || pending} aria-busy={pending}>
      {pending ? pendingLabel : label}
    </button>
  );
}

const PANEL_ACTIONS: Record<ModuleTab, PanelAction[]> = {
  "development-workshop": [
    {
      id: "create-station",
      label: "添加工位",
      summary: "创建 Nanopi / App / Unity / 测试等项目工位。",
      detail: "三级抽屉里只放工位名称、职责、总知识库和负责 NPC 列表，不把所有字段塞到二级页。",
      primaryLabel: "打开工位创建抽屉",
      safety: "只创建项目结构，不自动派单。",
    },
    {
      id: "station-knowledge",
      label: "工位知识库",
      summary: "维护工位共享知识，不替代 NPC 私有知识库。",
      detail: "后续接入文档、GitHub 路径、硬件约束和人工确认边界。",
      primaryLabel: "打开知识库抽屉",
      safety: "知识库修改需要保存确认。",
    },
    {
      id: "assign-npc",
      label: "挂载负责 NPC",
      summary: "给工位添加一个或多个负责 NPC。",
      detail: "用户先选工位，再选 NPC，平台只记录职责关系，不直接触发自动化。",
      primaryLabel: "打开 NPC 挂载抽屉",
      safety: "不会向线程发任务。",
    },
  ],
  "human-party": [
    {
      id: "invite-member",
      label: "邀请协作者",
      summary: "把另一个账号加入当前项目。",
      detail: "三级抽屉放邮箱、角色、权限和邀请链接；人工确认后才加入项目。",
      primaryLabel: "打开邀请抽屉",
      safety: "跨账号隔离不放松。",
    },
    {
      id: "role-permission",
      label: "设置权限",
      summary: "配置项目 owner、member、viewer 等角色。",
      detail: "用户可以看到每个主角名下电脑和线程，但不能越权操作其他项目。",
      primaryLabel: "打开权限抽屉",
      safety: "权限变更需要项目负责人确认。",
    },
    {
      id: "presence",
      label: "查看协作现场",
      summary: "查看谁在线、谁进入项目、谁正在执行。",
      detail: "这里后续接项目 presence，不再用右侧常驻大栏挡视野。",
      primaryLabel: "打开现场抽屉",
      safety: "只读查看。",
    },
  ],
  "npc-create": [
    {
      id: "create-npc",
      label: "添加 NPC",
      summary: "填写名字、职责、头像、自动化开关和初始知识库。",
      detail: "创建后地图后续会出现同风格 NPC，但当前阶段先只做管理入口和抽屉。",
      primaryLabel: "打开 NPC 创建抽屉",
      safety: "默认不开自动化，避免无意消耗 token。",
    },
    {
      id: "bind-thread",
      label: "绑定线程",
      summary: "把 NPC 绑定到某台电脑的 Codex / Claude / Qwen 线程。",
      detail: "三级抽屉显示电脑、执行程序、线程、模型和工作路径提醒。",
      primaryLabel: "打开线程绑定抽屉",
      safety: "只绑定，不发任务。",
    },
    {
      id: "npc-knowledge",
      label: "知识库",
      summary: "维护这个 NPC 自己继承的长期知识。",
      detail: "NPC 固定存在，线程和模型可以换，但知识库要跟着 NPC 走。",
      primaryLabel: "打开知识库抽屉",
      safety: "只保存知识，不自动执行。",
    },
    {
      id: "npc-skills",
      label: "能力配置",
      summary: "查看这个 NPC 当前能力摘要，完整配置进入能力工坊。",
      detail: "主页面不再直接装配 Skill，避免和上岗包快照冲突。",
      primaryLabel: "去能力工坊配置",
      safety: "配置变更会按上岗包规则生成新快照。",
    },
    {
      id: "npc-dialogue",
      label: "进入 NPC 工作台",
      summary: "和 NPC 对话、查看我的需求和我的任务。",
      detail: "对话、协作请求、人工确认和回执都回到 NPC 工作台瓷砖完成。",
      primaryLabel: "打开 NPC 工作台",
      safety: "发送前显示目标 NPC 和是否自动化。",
    },
  ],
  computers: [
    {
      id: "pairing-token",
      label: "生成配对令牌",
      summary: "给新电脑生成执行接入令牌。",
      detail: "三级抽屉展示一键命令、局域网地址和失败排查，不再让按钮一直转圈。",
      primaryLabel: "打开配对抽屉",
      safety: "令牌过期后不能复用。",
    },
    {
      id: "scan-threads",
      label: "扫描线程",
      summary: "扫描本机 Codex / Claude / Qwen 真实线程。",
      detail: "后续把无标题线程、找不到 session index、Claude 未启动等情况变成清晰提示。",
      primaryLabel: "打开扫描抽屉",
      safety: "扫描只读，不改代码。",
    },
    {
      id: "runner-health",
      label: "执行电脑健康",
      summary: "确认电脑在线、心跳、队列和最近错误。",
      detail: "如果电脑没进入项目或执行程序离线，首页需要持续提醒。",
      primaryLabel: "打开健康抽屉",
      safety: "只读状态检查。",
    },
  ],
  skills: [
    {
      id: "github-import",
      label: "从 GitHub 导入",
      summary: "选择性导入 GitHub skill，不再只能全量导入。",
      detail: "三级抽屉展示 repo、分类、中文介绍、适用职业和导入预览。",
      primaryLabel: "打开 GitHub 导入抽屉",
      safety: "先预览再入库。",
    },
    {
      id: "skill-category",
      label: "分类管理",
      summary: "按固定必备、职业、硬件、UI、验证等分类。",
      detail: "能力仓库是来源库，NPC 装配只索引这里的条目。",
      primaryLabel: "打开分类抽屉",
      safety: "分类修改不影响已装配 NPC，除非用户确认同步。",
    },
    {
      id: "skill-detail",
      label: "编辑中文说明",
      summary: "把 skill 说明写得具体、小白能懂。",
      detail: "包含用途、适用边界、输入输出、截图验证要求和 token 风险。",
      primaryLabel: "打开说明抽屉",
      safety: "编辑后保留版本记录。",
    },
  ],
  exchange: [
    {
      id: "dispatch-command",
      label: "协作审计",
      summary: "查看协作请求、人工确认、回执链路，不在主页面直接派发。",
      detail: "真实 NPC 对话和启动处理只在 workbench 瓷砖里进行；这里负责索引和治理。",
      primaryLabel: "打开审计抽屉",
      safety: "只读查看，不触发执行。",
    },
    {
      id: "final-pool",
      label: "最终回复池",
      summary: "只看最终结果，不把过程噪声堆首页。",
      detail: "过程留在本机 Codex/Claude/Qwen，平台首页突出最终回复和下一步推荐。",
      primaryLabel: "打开最终回复抽屉",
      safety: "只读查看。",
    },
    {
      id: "required-ledger",
      label: "必读需求表",
      summary: "人和 AI 提需求都写入统一需求表。",
      detail: "每个 AI 做任务前必须读：提需求者、被提需求者、需求内容、边界、验收。",
      primaryLabel: "打开需求表抽屉",
      safety: "未读需求表不派单。",
    },
  ],
  "machine-room": [
    {
      id: "thread-list",
      label: "线程列表",
      summary: "查看每台电脑真实线程与绑定 NPC。",
      detail: "解决 12 条只显示 6 条、无标题线程、Claude 识别不到等用户问题。",
      primaryLabel: "打开线程抽屉",
      safety: "只读查看。",
    },
    {
      id: "execution-logs",
      label: "执行日志",
      summary: "查看 Codex/Claude/Qwen 执行程序的接单和回写状态。",
      detail: "用于判断任务是否送到正确电脑、是否有回执、是否需要重新连接。",
      primaryLabel: "打开执行日志",
      safety: "默认不暴露长日志给小白。",
    },
    {
      id: "online-check",
      label: "在线判断",
      summary: "判断电脑是否在线、是否登录、是否进入项目。",
      detail: "离线电脑、未进入项目、持续接单断开要有明确状态。",
      primaryLabel: "打开在线抽屉",
      safety: "只读心跳。",
    },
  ],
  git: [
    {
      id: "checkpoint",
      label: "创建检查点",
      summary: "在危险修改前创建可视化版本点。",
      detail: "每次大改 UI/后端/Unity 前都应形成回退点和截图证据。",
      primaryLabel: "打开检查点抽屉",
      safety: "不自动 reset。",
    },
    {
      id: "diff-preview",
      label: "差异预览",
      summary: "看清楚哪些文件将被影响。",
      detail: "用户先看 diff，再决定是否回退或合并。",
      primaryLabel: "打开差异抽屉",
      safety: "只读 diff。",
    },
    {
      id: "rollback-request",
      label: "申请回退",
      summary: "把回退变成人工确认流程。",
      detail: "任何删除、覆盖、reset 都必须人工确认和记录。",
      primaryLabel: "打开回退抽屉",
      safety: "不会直接执行 destructive 命令。",
    },
  ],
};

function cleanFeedCopy(value: unknown, fallback = "暂无可展示条目") {
  const raw = String(value ?? "").trim();
  if (!raw) return fallback;
  return raw
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "平台记录")
    .replace(/\bRequirement\b/gi, "需求")
    .replace(/\bTaskDispatch\b/gi, "派发记录")
    .replace(/\brunner\s+ack\b/gi, "接单回执")
    .replace(/\badapter\b/gi, "接入程序")
    .replace(/\bbridge\b/gi, "同步通道");
}

function isRawUuid(value: unknown) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(value ?? "").trim());
}

function itemTitle(item?: FeedItem) {
  if (!item) return "暂无可展示条目";
  return cleanFeedCopy(item.title || item.name || item.type || item.body || "", "平台记录");
}

function clampPercent(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function itemBody(item?: FeedItem) {
  if (!item) return "等待平台下一步协作状态。";
  return cleanFeedCopy(item.body || item.status || "", "暂无详细说明");
}

function uniqueText(values: unknown[]) {
  return Array.from(
    new Set(
      values
        .map((value) => String(value ?? "").trim())
        .filter(Boolean),
    ),
  );
}

function shortCopy(value: unknown, fallback = "暂无说明", maxLength = 88) {
  const raw = String(value ?? "").trim();
  if (!raw) return fallback;
  return raw.length > maxLength ? `${raw.slice(0, maxLength).trimEnd()}...` : raw;
}

function statusLabel(value?: string) {
  const normalized = String(value ?? "").toLowerCase();
  if (["done", "completed", "archived"].includes(normalized)) return "完成";
  if (["blocked", "failed", "error"].includes(normalized)) return "阻塞";
  if (normalized === "draft") return "草稿";
  if (normalized === "available") return "可用";
  if (["active", "running", "in_progress", "queued"].includes(normalized)) return "进行中";
  if (["online", "ready"].includes(normalized)) return "在线";
  if (["offline", "idle"].includes(normalized)) return "空闲";
  return value || "待处理";
}

function skillLifecycleLabel(skill: FeedItem) {
  const draftStatus = String(skill.draftStatus || skill.status || "").toLowerCase();
  if (draftStatus === "draft") return "草稿待确认";
  if (draftStatus === "ready" || skill.status === "active") return "已启用";
  if (skill.source === "npc-authored") return "NPC 沉淀";
  return statusLabel(skill.status);
}

function automationLabel(item?: FeedItem) {
  return item?.automationEnabled ? "持续自动化" : "单次执行";
}

function WorkstationGroupsSection({
  projectId,
  apiBaseUrl,
  npcSeats,
  computers,
  projectWorkstations,
  returnTo,
  onBroadcast,
}: {
  projectId: string;
  apiBaseUrl: string;
  npcSeats: FeedItem[];
  computers: FeedItem[];
  projectWorkstations: ProjectWorkstation[];
  returnTo?: string;
  onBroadcast: (scope: string, label: string) => void;
}) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | "create" | null>(null);
  const [adminNote, setAdminNote] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [editingWsId, setEditingWsId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editLeadSeatId, setEditLeadSeatId] = useState("");
  const platformBlueprintNames = [
    "Boss 总控 / 产品与分工工位",
    "后端数据 / 接口与数据流工位",
    "前端体验 / 工作台界面工位",
    "QA 验收 / 用户路径工位",
  ];

  async function callApi(method: string, path: string, body?: unknown): Promise<{ ok: boolean; json: any }> {
    const res = await fetch(apiClientUrl(path), {
      method,
      credentials: "include",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const json = await res.json().catch(() => ({}));
    return { ok: res.ok, json };
  }

  async function createLogicalWorkstation(name: string) {
    if (!name.trim()) {
      setAdminNote("请输入工位名");
      return;
    }
    setBusyId("create");
    setAdminNote(null);
    try {
      const r = await callApi("POST", `/api/projects/${encodeURIComponent(projectId)}/workstations`, { name: name.trim() });
      if (!r.ok) throw new Error(r.json?.error?.message ?? `HTTP ${r.json?.error?.code ?? "?"}`);
      setAdminNote(`✓ 已创建：${r.json?.data?.name}`);
      setNewName("");
      router.refresh();
    } catch (e) {
      setAdminNote(`创建失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function renameLogicalWorkstation(wsId: string, name: string) {
    if (!name.trim()) {
      setAdminNote("请输入新名字");
      return;
    }
    setBusyId(wsId);
    setAdminNote(null);
    try {
      const r = await callApi("PATCH", `/api/projects/${encodeURIComponent(projectId)}/workstations/${encodeURIComponent(wsId)}`, { name: name.trim() });
      if (!r.ok) throw new Error(r.json?.error?.message ?? "rename failed");
      setAdminNote("✓ 已改名");
      setEditingWsId(null);
      router.refresh();
    } catch (e) {
      setAdminNote(`改名失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function setLogicalWorkstationLead(wsId: string, seatId: string) {
    setBusyId(wsId);
    setAdminNote(null);
    try {
      const r = await callApi(
        "POST",
        `/api/projects/${encodeURIComponent(projectId)}/workstations/${encodeURIComponent(wsId)}/lead`,
        { seat_id: seatId || null },
      );
      if (!r.ok) throw new Error(r.json?.error?.message ?? "set lead failed");
      setAdminNote(seatId ? "✓ 已设工位长" : "✓ 已清空工位长");
      setEditingWsId(null);
      router.refresh();
    } catch (e) {
      setAdminNote(`设工位长失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function createPlatformBlueprint() {
    setBusyId("create");
    setAdminNote(null);
    try {
      const existingNames = new Set(projectWorkstations.map((ws) => ws.name.trim().toLowerCase()));
      const missing = platformBlueprintNames.filter((name) => !existingNames.has(name.toLowerCase()));
      if (!missing.length) {
        setAdminNote("平台推荐工位已存在。");
        return;
      }
      for (const name of missing) {
        const r = await callApi("POST", `/api/projects/${encodeURIComponent(projectId)}/workstations`, { name });
        if (!r.ok) throw new Error(`${name}: ${r.json?.error?.message ?? "create failed"}`);
      }
      setAdminNote(`✓ 已创建 ${missing.length} 个平台推荐工位`);
      router.refresh();
    } catch (e) {
      setAdminNote(`创建推荐工位失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function assignNpcToLogicalWorkstation(wsId: string, seatId: string, seatName: string) {
    if (!wsId || !seatId) return;
    setBusyId(`assign:${seatId}`);
    setAdminNote(null);
    try {
      const r = await callApi(
        "POST",
        `/api/projects/${encodeURIComponent(projectId)}/workstations/${encodeURIComponent(wsId)}/seats`,
        { seat_ids: [seatId] },
      );
      if (!r.ok) throw new Error(r.json?.error?.message ?? "assign seat failed");
      setAdminNote(`✓ 已把 ${seatName} 分配到逻辑工位`);
      router.refresh();
    } catch (e) {
      setAdminNote(`分配失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function setSingleNpcWorkstationsAsLeads(groupsToScan: Group[]) {
    const candidates = groupsToScan.filter((group) => group.isLogicalWorkstation && group.workstationId && group.seats.length === 1);
    if (!candidates.length) {
      setAdminNote("没有可自动设置的单 NPC 逻辑工位。");
      return;
    }
    setBusyId("lead:auto");
    setAdminNote(null);
    try {
      for (const group of candidates) {
        const wsId = group.workstationId!;
        const seatId = group.seats[0]?.id;
        if (!seatId) continue;
        const r = await callApi(
          "POST",
          `/api/projects/${encodeURIComponent(projectId)}/workstations/${encodeURIComponent(wsId)}/lead`,
          { seat_id: seatId },
        );
        if (!r.ok) throw new Error(`${group.name}: ${r.json?.error?.message ?? "set lead failed"}`);
      }
      setAdminNote(`✓ 已为 ${candidates.length} 个单 NPC 工位设置工位长`);
      router.refresh();
    } catch (e) {
      setAdminNote(`设置工位长失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function autoArrangePlatformWorkstations() {
    const mapping = [
      { npc: "Boss", station: "Boss 总控 / 产品与分工工位" },
      { npc: "后端", station: "后端数据 / 接口与数据流工位" },
      { npc: "前端", station: "前端体验 / 工作台界面工位" },
      { npc: "QA", station: "QA 验收 / 用户路径工位" },
    ];
    setBusyId("platform:auto");
    setAdminNote(null);
    try {
      const arranged: Array<{ wsId: string; seatId: string; station: string }> = [];
      for (const item of mapping) {
        const seat = npcSeats.find((candidate) => itemTitle(candidate).includes(item.npc));
        const workstation = projectWorkstations.find((candidate) => candidate.name === item.station);
        if (!seat || !workstation) continue;
        const r = await callApi(
          "POST",
          `/api/projects/${encodeURIComponent(projectId)}/workstations/${encodeURIComponent(workstation.id)}/seats`,
          { seat_ids: [seat.id] },
        );
        if (!r.ok) throw new Error(`${item.npc}: ${r.json?.error?.message ?? "assign seat failed"}`);
        arranged.push({ wsId: workstation.id, seatId: seat.id, station: item.station });
      }
      for (const item of arranged) {
        const r = await callApi(
          "POST",
          `/api/projects/${encodeURIComponent(projectId)}/workstations/${encodeURIComponent(item.wsId)}/lead`,
          { seat_id: item.seatId },
        );
        if (!r.ok) throw new Error(`${item.station}: ${r.json?.error?.message ?? "set lead failed"}`);
      }
      setAdminNote(`✓ 已按平台蓝图归位 ${arranged.length} 个 NPC，并设为各自工位长`);
      router.refresh();
    } catch (e) {
      setAdminNote(`平台蓝图自动归位失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function deleteLogicalWorkstation(wsId: string, name: string) {
    if (!confirm(`删除工位「${name}」？\n（必须先把里面的 NPC 调走，否则后端会拒绝）`)) return;
    setBusyId(wsId);
    setAdminNote(null);
    try {
      const r = await callApi("DELETE", `/api/projects/${encodeURIComponent(projectId)}/workstations/${encodeURIComponent(wsId)}`);
      if (!r.ok) throw new Error(r.json?.error?.message ?? "delete failed");
      setAdminNote(`✓ 已删除：${name}`);
      router.refresh();
    } catch (e) {
      setAdminNote(`删除失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  const computerNameById = new Map<string, string>();
  for (const c of computers) {
    computerNameById.set(c.id, itemTitle(c));
  }
  const workstationNameById = new Map<string, string>();
  for (const ws of projectWorkstations) {
    if (ws.id) workstationNameById.set(ws.id, ws.name || ws.id);
  }
  type Group = {
    key: string;
    name: string;
    isLogicalWorkstation: boolean;
    workstationId: string | null;
    nodeId: string | null;
    seats: FeedItem[];
  };
  const groupMap = new Map<string, Group>();
  for (const seat of npcSeats) {
    let key = "__unbound__";
    let name = "未归属工位";
    let isLogical = false;
    let workstationId: string | null = null;
    let nodeId: string | null = null;
    if (seat.workstationId) {
      key = `ws:${seat.workstationId}`;
      name = seat.workstationName || workstationNameById.get(seat.workstationId) || seat.workstationId;
      isLogical = true;
      workstationId = seat.workstationId;
    } else if (seat.computerNodeId) {
      key = `node:${seat.computerNodeId}`;
      name = computerNameById.get(seat.computerNodeId) ?? seat.computerNodeId;
      nodeId = seat.computerNodeId;
    } else if (seat.sourceWorkstationId) {
      key = `legacy:${seat.sourceWorkstationId}`;
      name = seat.sourceWorkstationId;
    }
    const bucket = groupMap.get(key) ?? { key, name, isLogicalWorkstation: isLogical, workstationId, nodeId, seats: [] };
    bucket.seats.push(seat);
    groupMap.set(key, bucket);
  }
  const groups = Array.from(groupMap.values()).sort((a, b) => b.seats.length - a.seats.length);
  const unassignedNpcSeats = npcSeats.filter((seat) => !seat.workstationId);
  const missingLeadCount = projectWorkstations.filter((ws) => !ws.leadSeatId).length;
  const leadNameForWorkstation = (ws: ProjectWorkstation) => {
    if (!ws.leadSeatId) return "未设工位长";
    return npcSeats.find((s) => s.id === ws.leadSeatId || s.rowId === ws.leadSeatId || itemTitle(s) === ws.leadSeatId)?.name ?? ws.leadSeatId.slice(0, 8);
  };

  // groups 为空时仍展示工位管理面板（让用户能新建第一个工位）

  return (
    <section className={styles.workstationGroups}>
      <header className={styles.workstationGroupsHead}>
        <strong>按执行归属分组的 NPC（{groups.length} 组 / {npcSeats.length} 个 NPC）</strong>
        <small>逻辑工位优先；未归属时只按电脑/线程临时分组，不能代表部门协作关系。</small>
      </header>
      <section className={styles.workstationHealthStrip} aria-label="逻辑工位健康摘要">
        <div>
          <strong>逻辑工位链路</strong>
          <small>同工位互认，跨工位走目标工位长；这里是所有工作台复用的资源源头。</small>
        </div>
        <div className={styles.workstationHealthSteps}>
          <span data-ok={projectWorkstations.length > 0 ? "1" : "0"}>工位 {projectWorkstations.length}</span>
          <span data-ok={unassignedNpcSeats.length === 0 && npcSeats.length > 0 ? "1" : "0"}>未归属 {unassignedNpcSeats.length}</span>
          <span data-ok={missingLeadCount === 0 && projectWorkstations.length > 0 ? "1" : "0"}>缺工位长 {missingLeadCount}</span>
        </div>
        {projectWorkstations.length ? (
          <div className={styles.workstationLeadChips}>
            {projectWorkstations.map((ws) => (
              <span key={ws.id} data-missing={ws.leadSeatId ? undefined : "1"}>
                {ws.name} · 工位长：{leadNameForWorkstation(ws)}
              </span>
            ))}
          </div>
        ) : null}
      </section>

      <details
        open={projectWorkstations.length === 0 || unassignedNpcSeats.length > 0 || missingLeadCount > 0}
        style={{ margin: "8px 0", padding: "8px 10px", background: "rgba(255,255,255,0.04)", borderRadius: 8 }}
      >
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          🛠 工位管理（{projectWorkstations.length} 个逻辑工位）
        </summary>
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
          <section className={styles.workstationSetupGuide}>
            <div>
              <strong>平台协作先做这三步</strong>
              <p>创建逻辑工位，把 NPC 分配进去，再给每个工位指定工位长。工位知识库用 GitHub 仓库相对路径，本地工程目录只作为当前电脑执行目录。</p>
            </div>
            <div className={styles.workstationSetupSteps}>
              <span data-done={projectWorkstations.length > 0 ? "1" : "0"}>1. 逻辑工位 {projectWorkstations.length}</span>
              <span data-done={unassignedNpcSeats.length === 0 && npcSeats.length > 0 ? "1" : "0"}>2. 未归属 NPC {unassignedNpcSeats.length}</span>
              <span data-done={missingLeadCount === 0 && projectWorkstations.length > 0 ? "1" : "0"}>3. 未设工位长 {missingLeadCount}</span>
            </div>
          </section>
          {projectWorkstations.length === 0 ? (
            <button
              type="button"
              className={styles.workstationBlueprintBtn}
              onClick={createPlatformBlueprint}
              disabled={busyId === "create"}
            >
              {busyId === "create" ? "创建推荐工位中..." : "一键创建平台推荐工位"}
            </button>
          ) : null}
          {projectWorkstations.length > 0 ? (
            <button
              type="button"
              className={styles.workstationBlueprintBtn}
              onClick={autoArrangePlatformWorkstations}
              disabled={busyId === "platform:auto"}
            >
              {busyId === "platform:auto" ? "平台蓝图自动归位中..." : "按 NPC 名称自动归位并设置工位长"}
            </button>
          ) : null}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createLogicalWorkstation(newName);
            }}
            style={{ display: "flex", gap: 6, alignItems: "center" }}
          >
            <input
              type="text"
              placeholder="新建工位（例：软件工位 / 硬件工位 / 嵌入式工位）"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              style={{ flex: 1, padding: "4px 8px", borderRadius: 4, border: "1px solid rgba(255,255,255,0.2)", background: "rgba(0,0,0,0.3)", color: "inherit" }}
            />
            <button type="submit" disabled={busyId === "create"} className={styles.workstationGroupBroadcast}>
              {busyId === "create" ? "创建中…" : "+ 新建"}
            </button>
          </form>
          {projectWorkstations.length === 0 ? (
            <small style={{ opacity: 0.6 }}>还没有逻辑工位。新建一个软件/硬件/嵌入式工位吧。</small>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 6 }}>
              {projectWorkstations.map((ws) => {
                const isEditing = editingWsId === ws.id;
                const seatChoicesForWs = npcSeats.filter((s) => s.workstationId === ws.id);
                return (
                  <li
                    key={ws.id}
                    style={{
                      display: "flex",
                      gap: 8,
                      alignItems: "center",
                      padding: "6px 8px",
                      borderRadius: 6,
                      background: "rgba(255,255,255,0.03)",
                    }}
                  >
                    <span style={{ minWidth: 20 }}>🏷</span>
                    {isEditing ? (
                      <>
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          style={{ flex: 1, padding: "3px 6px", borderRadius: 4, border: "1px solid rgba(255,255,255,0.2)", background: "rgba(0,0,0,0.3)", color: "inherit" }}
                        />
                        <select
                          value={editLeadSeatId}
                          onChange={(e) => setEditLeadSeatId(e.target.value)}
                          style={{ padding: "3px 6px", borderRadius: 4, background: "rgba(0,0,0,0.3)", color: "inherit", border: "1px solid rgba(255,255,255,0.2)" }}
                          title="工位长（跨工位投递时默认转交给本人）"
                        >
                          <option value="">— 不设工位长 —</option>
                          {seatChoicesForWs.map((s) => (
                            <option key={s.id} value={s.id}>{itemTitle(s)}</option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className={styles.workstationGroupBroadcast}
                          disabled={busyId === ws.id}
                          onClick={async () => {
                            if (editName.trim() && editName.trim() !== ws.name) {
                              await renameLogicalWorkstation(ws.id, editName);
                            }
                            if (editLeadSeatId !== (ws.leadSeatId ?? "")) {
                              await setLogicalWorkstationLead(ws.id, editLeadSeatId);
                            }
                            setEditingWsId(null);
                          }}
                        >
                          保存
                        </button>
                        <button type="button" className={styles.workstationGroupBroadcastDisabled} onClick={() => setEditingWsId(null)}>
                          取消
                        </button>
                      </>
                    ) : (
                      <>
                        <strong style={{ flex: 1 }}>
                          {ws.name}
                          <small style={{ marginLeft: 8, opacity: 0.6 }}>
                            {ws.seatCount} 个 NPC
                            {` · 工位长：${leadNameForWorkstation(ws)}`}
                          </small>
                        </strong>
                        <button
                          type="button"
                          className={styles.workstationGroupBroadcast}
                          onClick={() => {
                            setEditingWsId(ws.id);
                            setEditName(ws.name);
                            setEditLeadSeatId(ws.leadSeatId ?? "");
                          }}
                        >
                          ✎ 改名 / 工位长
                        </button>
                        <button
                          type="button"
                          className={styles.workstationGroupBroadcastDisabled}
                          disabled={busyId === ws.id || ws.seatCount > 0}
                          onClick={() => deleteLogicalWorkstation(ws.id, ws.name)}
                          title={ws.seatCount > 0 ? "请先把里面的 NPC 调走" : "删除这个工位"}
                        >
                          🗑 删除
                        </button>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {projectWorkstations.length > 0 && unassignedNpcSeats.length > 0 ? (
            <section className={styles.unassignedNpcAssignBox}>
              <strong>未归属 NPC，需要分配到逻辑工位</strong>
              <p>同工位互相认识、工位知识库、跨工位走工位长，都从这里的归属关系开始。</p>
              <div className={styles.unassignedNpcGrid}>
                {unassignedNpcSeats.map((seat) => (
                  <div key={seat.id} className={styles.unassignedNpcItem}>
                    <div>
                      <b>{itemTitle(seat)}</b>
                      <small>{seat.responsibility || seat.providerLabel || "待补职责"}</small>
                    </div>
                    <select
                      defaultValue=""
                      onChange={(e) => {
                        const nextWs = e.target.value;
                        if (!nextWs) return;
                        assignNpcToLogicalWorkstation(nextWs, seat.id, itemTitle(seat));
                      }}
                      disabled={busyId === `assign:${seat.id}`}
                      title="选择后立即把 NPC 分配到这个逻辑工位"
                    >
                      <option value="">分配到...</option>
                      {projectWorkstations.map((ws) => (
                        <option key={ws.id} value={ws.id}>{ws.name}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
          {projectWorkstations.length > 0 ? (
            <button
              type="button"
              className={styles.workstationBlueprintBtn}
              onClick={() => setSingleNpcWorkstationsAsLeads(groups)}
              disabled={busyId === "lead:auto"}
            >
              {busyId === "lead:auto" ? "设置工位长中..." : "单 NPC 工位一键设为工位长"}
            </button>
          ) : null}
          {adminNote ? <small style={{ opacity: 0.85 }}>{adminNote}</small> : null}
        </div>
      </details>
      <div className={styles.workstationGroupsList}>
        {groups.map((group) => {
          const automationOn = group.seats.filter((s) => s.automationEnabled).length;
          return (
            <details key={group.key} className={styles.workstationGroupCard}>
              <summary className={styles.workstationGroupSummary}>
                <span className={styles.workstationGroupName}>
                  {group.isLogicalWorkstation ? "🏷" : "🖥"} {group.name}
                  {group.isLogicalWorkstation ? <small style={{ marginLeft: 6, opacity: 0.7 }}>逻辑工位</small> : null}
                </span>
                <span className={styles.workstationGroupCount}>
                  {group.seats.length} 个 NPC · 自动化 {automationOn}
                </span>
                {group.key === "__unbound__" ? (
                  <span
                    className={styles.workstationGroupBroadcastDisabled}
                    title="未归属工位的 NPC 暂不支持组内广播，先在工位管理里把它分配到一个工位"
                  >
                    组内广播 (需先归属工位)
                  </span>
                ) : (
                  <span
                    className={styles.workstationGroupBroadcast}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      onBroadcast(`workstation:${group.key}`, group.name);
                    }}
                    title="组内广播：一键发给本组所有 NPC"
                  >
                    组内广播
                  </span>
                )}
              </summary>
              <ul className={styles.workstationGroupSeatList}>
                {group.seats.map((seat) => (
                  <li key={seat.id} className={styles.workstationGroupSeatRow}>
                    <div>
                      <strong>{itemTitle(seat)}</strong>
                      <small>
                        {seat.providerLabel || seat.providerId || "未绑定 provider"}
                        {seat.responsibility ? ` · ${seat.responsibility.slice(0, 28)}${seat.responsibility.length > 28 ? "…" : ""}` : ""}
                        {seat.automationEnabled ? " · 持续自动化" : ""}
                      </small>
                    </div>
                    {projectWorkstations.length > 0 ? (
                      <select
                        className={styles.workstationSeatMoveSelect}
                        aria-label={`调整 ${itemTitle(seat)} 的逻辑工位归属`}
                        data-testid={`workstation-seat-move-${seat.id}`}
                        value={seat.workstationId || ""}
                        onChange={(e) => {
                          const nextWs = e.target.value;
                          if (!nextWs || nextWs === seat.workstationId) return;
                          assignNpcToLogicalWorkstation(nextWs, seat.id, itemTitle(seat));
                        }}
                        disabled={busyId === `assign:${seat.id}`}
                        title="调整这个 NPC 的逻辑工位归属"
                      >
                        <option value="">未归属</option>
                        {projectWorkstations.map((ws) => (
                          <option key={ws.id} value={ws.id}>{ws.name}</option>
                        ))}
                      </select>
                    ) : null}
                  </li>
                ))}
              </ul>
              <div className={styles.workstationGroupActions}>
                <Link
                  href={`/projects/${projectId}/workbench?${new URLSearchParams({
                    return_to: returnTo || `/projects/${projectId}/2d-upgrade?panel=development-workshop`,
                    from: "2d-upgrade",
                  }).toString()}`}
                  className={styles.workstationGroupOpenLink}
                  title="到工作台同时打开本组 NPC 的瓷砖"
                >
                  到 NPC 工作台 →
                </Link>
                {group.nodeId ? (
                  <WorkstationProfileEditor
                    apiBaseUrl={apiBaseUrl}
                    projectId={projectId}
                    nodeId={group.nodeId}
                    seatChoices={group.seats.map((s) => ({ id: s.id, name: itemTitle(s) }))}
                  />
                ) : null}
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );
}

function listToFormValue(items?: string[]) {
  return (items ?? []).filter(Boolean).join("\n");
}

function isModuleTab(value: unknown): value is ModuleTab {
  return PANEL_TABS.includes(String(value) as ModuleTab);
}

function parseModuleTabFromHref(href: string) {
  try {
    const url = new URL(href, window.location.origin);
    const tab = url.searchParams.get("tab") || url.searchParams.get("panel");
    return isModuleTab(tab) ? tab : null;
  } catch {
    return null;
  }
}

function feedSummary(items: FeedItem[], emptyText: string, limit = 5) {
  return items.length ? items.slice(0, limit) : [{ id: "empty", title: emptyText, status: "idle" }];
}

function isFinalReply(message: FeedItem) {
  const source = `${message.type ?? ""} ${message.status ?? ""} ${message.title ?? ""} ${message.body ?? ""}`.toLowerCase();
  return source.includes("final") || source.includes("最终") || source.includes("reply");
}

function isDispatchMessage(message: FeedItem) {
  const source = `${message.type ?? ""} ${message.status ?? ""} ${message.title ?? ""} ${message.body ?? ""}`.toLowerCase();
  return source.includes("dispatch") || source.includes("agent_command") || source.includes("派单") || source.includes("指令") || source.includes("command");
}

function isProgressAck(message: FeedItem) {
  const source = `${message.type ?? ""} ${message.status ?? ""} ${message.title ?? ""} ${message.body ?? ""}`.toLowerCase();
  return source.includes("ack") || source.includes("progress") || source.includes("accepted") || source.includes("回执") || source.includes("接单") || source.includes("最小");
}

function isHumanReviewMessage(message: FeedItem) {
  const source = `${message.type ?? ""} ${message.status ?? ""} ${message.title ?? ""} ${message.body ?? ""}`.toLowerCase();
  return source.includes("human_review") || source.includes("approval") || source.includes("审核") || source.includes("审批") || source.includes("人审") || source.includes("blocked");
}

function isExecutionChannelMessage(message: FeedItem) {
  const source = `${message.type ?? ""} ${message.status ?? ""} ${message.title ?? ""} ${message.body ?? ""}`.toLowerCase();
  return source.includes("adapter") || source.includes("scan") || source.includes("runner") || source.includes("thread") || source.includes("claude") || source.includes("codex") || source.includes("qwen");
}

function safeThreadName(thread: FeedItem, index: number) {
  const raw = itemTitle(thread).trim();
  if (raw && !/^线程\s+\d+$/i.test(raw)) return raw;
  const provider = thread.type || "AI";
  const suffix = thread.id ? thread.id.slice(0, 8) : String(index + 1).padStart(2, "0");
  return `${provider} 线程 ${suffix}`;
}

function threadUserHint(thread: FeedItem) {
  if (!thread.computerNodeId) return "未归属电脑：请重新扫描或在电脑接入里绑定到正确电脑。";
  if (!thread.name && !thread.title) return "无标题线程：建议打开对应 AI 工具后重新扫描，或手动命名。";
  if (String(thread.status ?? "").toLowerCase() === "offline") return "离线：确认这台电脑的持续接单窗口是否还在运行。";
  if (!thread.body) return "已发现线程：可继续绑定 NPC，或用于只读协作验证。";
  return thread.body;
}

function threadProviderId(thread?: FeedItem) {
  return String(thread?.type || thread?.providerId || thread?.providerLabel || "").trim().toLowerCase();
}

function isCodexThread(thread?: FeedItem) {
  return threadProviderId(thread).includes("codex") || String(thread?.id || "").toLowerCase().startsWith("codex-session-");
}

function sourceThreadOptionLabel(thread: FeedItem) {
  const provider = thread.type || "线程";
  const status = statusLabel(thread.status);
  if (isCodexThread(thread)) return `${itemTitle(thread)} / ${provider} / 可绑定执行 / ${status}`;
  return `${itemTitle(thread)} / ${provider} / ${status}`;
}

function memberRoleLabel(member: FeedItem) {
  const role = String(member.permissionLevel || member.type || member.status || "member").toLowerCase();
  if (role.includes("owner")) return "项目负责人";
  if (role.includes("maintainer")) return "维护者";
  if (role.includes("viewer")) return "只读观察者";
  if (role.includes("collaborator")) return "协作者";
  return member.permissionLevel || member.type || "项目成员";
}

function computerThreadCount(computer: FeedItem, workstations: FeedItem[]) {
  return computer.threadScanCount ?? workstations.filter((thread) => thread.computerNodeId === computer.id).length;
}

function computerUserHint(computer: FeedItem, workstations: FeedItem[]) {
  const status = String(computer.status ?? "").toLowerCase();
  const threads = computerThreadCount(computer, workstations);
  if (["online", "ready", "active"].includes(status) && threads > 0) return `可投递：已发现 ${threads} 条线程，可继续绑定 NPC 或下发只读任务。`;
  if (["online", "ready", "active"].includes(status)) return "执行程序在线但暂无线程：请打开 Codex/Claude/Qwen 后重新扫描。";
  if (status.includes("stale") || status.includes("expired")) return "心跳过期：让目标电脑重新运行执行接入命令或刷新心跳。";
  if (status.includes("offline")) return "离线：确认目标电脑是否开机、是否进入项目、持续接单窗口是否仍在运行。";
  return "状态需要确认：先看持续接单和线程扫描结果，再派单。";
}

function computerDesktopCapabilityLabel(computer: FeedItem) {
  if (computer.desktopBridgeConnected && computer.desktopDeliveryMode === "codex_desktop_ui") {
    return "桌面版可投递";
  }
  if (computer.desktopProcessDetected) return "检测到桌面进程，未确认 UI 投递";
  return "未检测到桌面投递桥";
}

function computerDesktopCapabilityHint(computer: FeedItem) {
  if (computer.desktopBridgeConnected && computer.desktopDeliveryMode === "codex_desktop_ui") {
    return "这台电脑可以把平台派单送进已绑定的 Codex 桌面线程；不会改动本机配置。";
  }
  if (computer.desktopProcessDetected) {
    return "执行程序看到本机桌面进程，但没有确认可交互输入；可能只能走服务端或文件投递。";
  }
  return "这台电脑还未确认桌面线程可接收派单；用户要先在目标电脑打开 AI 桌面版并重新同步线程。";
}

function isRunnerOnlineStatus(computer: FeedItem) {
  const normalized = String(computer.runnerEffectiveStatus || computer.runnerWatchState || computer.status || "").toLowerCase();
  return ["online", "watching", "connected", "ready", "active"].some((status) => normalized.includes(status));
}

function runnerDispatchLabel(computer: FeedItem) {
  const normalized = String(computer.runnerEffectiveStatus || computer.runnerWatchState || computer.status || "").toLowerCase();
  if (isRunnerOnlineStatus(computer)) return "常驻接单";
  if (normalized.includes("stale") || normalized.includes("expired")) return "等待电脑恢复";
  if (normalized.includes("offline")) return "离线，需重连";
  return "状态待确认";
}

function runnerReconnectHint(computer: FeedItem, workstations: FeedItem[]) {
  if (isRunnerOnlineStatus(computer)) {
    const threads = computerThreadCount(computer, workstations);
    return threads > 0 ? `已发现 ${threads} 条线程，可继续绑定 NPC 或派发任务。` : "执行程序在线；若要派给桌面线程，请先打开 AI 工具并重新扫描线程。";
  }
  return "复制下面的持续接单命令到这台电脑运行。命令会使用公网 API，不依赖开发者本机路径。";
}

function computerListDetail(computer: FeedItem, workstations: FeedItem[]) {
  const title = computer.providerLabel || computer.runnerId || "";
  const dispatch = runnerDispatchLabel(computer);
  const threads = computerThreadCount(computer, workstations);
  const platform = computer.type || computer.status || "待确认系统";
  const heartbeat = computer.at ? `心跳 ${computer.at}` : "暂无心跳";
  return [title, dispatch, `${threads} 条线程`, heartbeat, platform].filter(Boolean).join(" / ");
}

function providerSummary(workstations: FeedItem[]) {
  const counts = new Map<string, number>();
  for (const item of workstations) {
    const key = String(item.type || "unknown").trim() || "unknown";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([provider, count]) => `${provider} ${count}`)
    .join(" / ") || "暂无线程";
}

function collaborationTargetLabel(item: FeedItem) {
  const base = `${itemTitle(item)} / ${item.type || "线程"}`;
  if (typeof item.automationEnabled === "boolean") {
    const interval = item.automationEnabled ? ` / ${item.automationHeartbeatSeconds ?? 900}s` : "";
    return `${base} / ${item.automationEnabled ? "自动化开启" : "单次执行"}${interval}`;
  }
  return `${base} / 按线程默认策略`;
}

const REAL_WRITE_ACTIONS = new Set([
  "development-workshop:create-station",
  "development-workshop:station-knowledge",
  "development-workshop:assign-npc",
  "human-party:invite-member",
  "npc-create:create-npc",
  "npc-create:bind-thread",
  "npc-create:npc-knowledge",
  "npc-create:npc-skills",
  "npc-create:npc-dialogue",
  "computers:pairing-token",
  "computers:scan-threads",
  "skills:github-import",
  "skills:skill-category",
  "skills:skill-detail",
  "git:checkpoint",
  "git:diff-preview",
  "git:rollback-request",
]);

const PREVIEW_ACTIONS = new Set([
  "exchange:dispatch-command",
]);

const REVIEW_ACTIONS = new Set([
  "human-party:role-permission",
  "git:rollback-request",
]);

const READONLY_ACTIONS = new Set([
  "human-party:presence",
  "computers:runner-health",
  "exchange:final-pool",
  "exchange:required-ledger",
  "machine-room:thread-list",
  "machine-room:execution-logs",
  "machine-room:online-check",
]);

function actionKey(moduleTab: ModuleTab, action: PanelAction) {
  return `${moduleTab}:${action.id}`;
}

function actionConnectivity(moduleTab: ModuleTab, action: PanelAction): ActionConnectivity {
  const key = actionKey(moduleTab, action);
  if (REVIEW_ACTIONS.has(key)) {
    return {
      label: "人工确认",
      tone: "review",
      detail: "会把风险怼到当前界面，涉及权限、硬件、回退或跑飞保护时不静默执行。",
    };
  }
  if (REAL_WRITE_ACTIONS.has(key)) {
    return {
      label: "已接真实表单",
      tone: "ready",
      detail: "提交会走真实 server action，完成后回到当前二级/三级位置并展示操作结果。",
    };
  }
  if (PREVIEW_ACTIONS.has(key)) {
    return {
      label: "预演后登记",
      tone: "preview",
      detail: "先生成只读预演或平台协作记录，再由目标 NPC/线程按自动化开关决定是否继续。",
    };
  }
  if (READONLY_ACTIONS.has(key)) {
    return {
      label: "只读巡检",
      tone: "readonly",
      detail: "只展示真实状态或归档结果，不改项目、不触发线程、不消耗连续自动化 token。",
    };
  }
  return {
    label: "待接线",
    tone: "pending",
    detail: "入口已迁移，下一轮需要补对应后端动作或验收链路。",
  };
}

function connectivityToneClass(tone: ActionConnectivity["tone"]) {
  if (tone === "ready") return styles.connectivityReady;
  if (tone === "readonly") return styles.connectivityReadonly;
  if (tone === "preview") return styles.connectivityPreview;
  if (tone === "review") return styles.connectivityReview;
  return styles.connectivityPending;
}

export function Project2dUpgradeGame(props: Project2dUpgradeGameProps) {
  const {
    project,
    apiBaseUrl,
    currentUser,
    stats,
    messages,
    tasks,
    requirements,
    computers,
    projectMembers,
    workstations,
    npcSeats,
    projectWorkstations,
    workshopStations,
    skills,
    knowledgeDocuments,
    teamNotice,
    teamError,
  } = props;
  const router = useRouter();
  const searchParams = useSearchParams();
  const teamNoticeToast = useTeamNoticeToast({ onRefresh: () => router.refresh() });

  const teamNoticeKey = searchParams?.get("team_notice") ?? "";
  const pairingTokenKey = searchParams?.get("pairing_token") ?? "";
  const adapterTokenKey = searchParams?.get("adapter_token") ?? "";
  const returnToPath = safeProjectReturnPath(project.id, searchParams?.get("return_to"));
  const returnToLabel = returnToPath ? labelProjectReturnPath(returnToPath) : "";
  useEffect(() => {
    if (!teamNoticeKey && !pairingTokenKey && !adapterTokenKey) return;
    router.refresh();
  }, [router, teamNoticeKey, pairingTokenKey, adapterTokenKey]);

  const [hudHidden, setHudHidden] = useState(true);
  const [dockHidden, setDockHidden] = useState(false);
  const [activePanel, setActivePanel] = useState<ModuleTab | null>(null);
  const [activeAction, setActiveAction] = useState<PanelAction | null>(null);
  const [focusedNpcId, setFocusedNpcId] = useState<string | null>(null);
  const [loadingActionId, setLoadingActionId] = useState<string | null>(null);
  // pairingResult 直接从 URL searchParams 派生，避免 useState + 单次 useEffect
  // 错过 server-action redirect 后的 query 变化（用户反馈：生成令牌后还是要 F5）
  const pairingResult = useMemo(() => {
    const node = searchParams?.get("pairing_node") || "";
    const tk = searchParams?.get("pairing_token") || "";
    return node && tk ? { nodeId: node, token: tk } : null;
  }, [searchParams]);
  const [webBaseUrl, setWebBaseUrl] = useState("http://127.0.0.1:3000");
  const [sceneVisible, setSceneVisible] = useState(false);
  const [copyState, setCopyState] = useState<{ kind: "idle" | "loading" | "ok" | "err"; message?: string }>({ kind: "idle" });
  const [manualCopy, setManualCopy] = useState<{ label: string; value: string } | null>(null);
  const [watcherCopyState, setWatcherCopyState] = useState<{ kind: "idle" | "ok" | "err"; message?: string }>({ kind: "idle" });
  const [serviceHealth, setServiceHealth] = useState<ServiceHealthState>({
    status: "checking",
    webUrl: "",
    apiBaseUrl,
  });
  const [handoffPreview, setHandoffPreview] = useState<{ npcName: string; prompt: string; at: string } | null>(null);
  const [handoffTaskId, setHandoffTaskId] = useState<string>("");
  const [cockpitOpen, setCockpitOpen] = useState(true);
  const [taskBoardOpen, setTaskBoardOpen] = useState(true);
  const [recommendedSkillSavingId, setRecommendedSkillSavingId] = useState<string | null>(null);
  const [recommendedSkillNotice, setRecommendedSkillNotice] = useState<string | null>(null);
  const [selectedRecommendedSkillId, setSelectedRecommendedSkillId] = useState("");
  const [githubSkillImporting, setGithubSkillImporting] = useState(false);
  const [workstationRepairing, setWorkstationRepairing] = useState(false);
  const [workstationRepairNotice, setWorkstationRepairNotice] = useState<string | null>(null);
  const setPanelNotice = (_value: string) => {};
  const panelNotice = "";

  useEffect(() => {
    let cancelled = false;
    async function loadServiceHealth() {
      const webUrl = typeof window !== "undefined" ? window.location.origin : "";
      setServiceHealth((prev) => ({ ...prev, status: "checking", webUrl, apiBaseUrl }));
      try {
        const res = await fetch(apiClientUrl("/api/health"), { credentials: "include", cache: "no-store" });
        const json = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(json?.error?.message ?? `HTTP ${res.status}`);
        const data = json?.data ?? json;
        if (cancelled) return;
        setServiceHealth({
          status: String(data?.status || "").toLowerCase() === "ok" ? "ok" : "error",
          webUrl,
          apiBaseUrl,
          apiPid: data?.pid != null ? String(data.pid) : "",
          apiVersion: data?.version != null ? String(data.version) : "",
          apiSeenUrl: data?.base_url != null ? String(data.base_url) : "",
          localServices: Array.isArray(data?.local_services) ? data.local_services : [],
          message: String(data?.status || "unknown"),
        });
      } catch (error) {
        if (cancelled) return;
        setServiceHealth({
          status: "error",
          webUrl,
          apiBaseUrl,
          message: error instanceof Error ? error.message : String(error),
        });
      }
    }
    loadServiceHealth();
    const timer = window.setInterval(loadServiceHealth, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [apiBaseUrl]);

  async function writeClipboardText(value: string) {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
    if (typeof document === "undefined") throw new Error("剪贴板不可用");
    const ta = document.createElement("textarea");
    ta.value = value;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.style.top = "0";
    ta.setAttribute("readonly", "readonly");
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(ta);
    if (!copied) throw new Error("浏览器没有允许复制");
  }

  function showManualCopy(
    label: string,
    value: string,
    setter: (state: { kind: "idle" | "ok" | "err"; message?: string }) => void = setCopyState,
  ) {
    setManualCopy({ label, value });
    setter({ kind: "ok", message: `${label} 已展开，请在文本框里手动复制。` });
    setTimeout(() => setter({ kind: "idle" }), 5000);
  }

  async function copyAiHandoffPrompt() {
    if (copyState.kind === "loading") return;
    setCopyState({ kind: "loading" });
    try {
      const data = await fetchProjectClaudeContext(project.id);
      const prompt = String(data?.prompt ?? "").trim();
      if (!prompt) throw new Error("提示词为空");
      try {
        await writeClipboardText(prompt);
        setManualCopy(null);
        setCopyState({ kind: "ok", message: "提示词已复制到剪贴板，粘贴到当前使用的 AI 开发工具即可继续。" });
      } catch {
        showManualCopy("AI 接入提示词", prompt);
      }
      setTimeout(() => setCopyState({ kind: "idle" }), 4000);
    } catch (error) {
      setCopyState({ kind: "err", message: `复制失败：${error instanceof Error ? error.message : "未知错误"}` });
      setTimeout(() => setCopyState({ kind: "idle" }), 5000);
    }
  }

  async function copyRepoUrl() {
    const repoUrl = (project as Record<string, unknown>).github_url || (project as Record<string, unknown>).local_git_url || "";
    if (!repoUrl) {
      setCopyState({ kind: "err", message: "项目未配置仓库地址。" });
      setTimeout(() => setCopyState({ kind: "idle" }), 3000);
      return;
    }
    try {
      try {
        await writeClipboardText(String(repoUrl));
        setManualCopy(null);
        setCopyState({ kind: "ok", message: `仓库地址已复制：${repoUrl}` });
      } catch {
        showManualCopy("仓库地址", String(repoUrl));
      }
      setTimeout(() => setCopyState({ kind: "idle" }), 3500);
    } catch (error) {
      setCopyState({ kind: "err", message: "复制失败" });
      setTimeout(() => setCopyState({ kind: "idle" }), 3000);
    }
  }

  async function copyTextToClipboard(value: string, okMessage: string) {
    if (!value) return;
    try {
      try {
        await writeClipboardText(value);
        setManualCopy(null);
        setCopyState({ kind: "ok", message: okMessage });
      } catch {
        showManualCopy("待复制内容", value);
      }
      setTimeout(() => setCopyState({ kind: "idle" }), 3000);
    } catch (error) {
      setCopyState({ kind: "err", message: `复制失败：${error instanceof Error ? error.message : "未知错误"}` });
      setTimeout(() => setCopyState({ kind: "idle" }), 4000);
    }
  }

  async function copyWatcherCommand(workstationId: string) {
    const command = buildWatcherCommand(project.id, workstationId);
    const threadLabel = firstWorkstationLabel || "当前线程";
    try {
      try {
        await writeClipboardText(command);
        setManualCopy(null);
        setWatcherCopyState({ kind: "ok", message: `已复制：粘贴到新 PowerShell 终端即可开始持续接单（${threadLabel}）` });
      } catch {
        showManualCopy("持续接单命令", command, setWatcherCopyState);
      }
      setTimeout(() => setWatcherCopyState({ kind: "idle" }), 4000);
    } catch (error) {
      setWatcherCopyState({ kind: "err", message: `复制失败：${error instanceof Error ? error.message : "未知错误"}` });
      setTimeout(() => setWatcherCopyState({ kind: "idle" }), 4000);
    }
  }

  async function createRecommendedSkill(skillId: string) {
    const selected = PLATFORM_RECOMMENDED_SKILLS.find((skill) => skill.id === skillId);
    if (!selected) {
      setRecommendedSkillNotice("请先选择一个推荐能力包。");
      return;
    }
    const existingSkillIds = new Set(skills.map((skill) => String(skill.id ?? "").trim().toLowerCase()).filter(Boolean));
    if (existingSkillIds.has(selected.id)) {
      setRecommendedSkillNotice("这个能力包已经创建过。");
      return;
    }
    setRecommendedSkillSavingId(selected.id);
    setRecommendedSkillNotice(null);
    try {
      const currentConfig =
        project.collaboration_config && typeof project.collaboration_config === "object"
          ? { ...project.collaboration_config }
          : {};
      const currentLibrary = Array.isArray(currentConfig.skill_library)
        ? [...(currentConfig.skill_library as Record<string, unknown>[])]
        : skills.map((skill) => ({
            id: skill.id,
            label: itemTitle(skill),
            note: itemBody(skill),
            source: skill.type || "custom",
            scope: "role",
          }));
      const nextLibrary = [...currentLibrary, normalizeSkillLibraryItem(selected)].sort((left, right) =>
        String(left.label ?? left.id ?? "").localeCompare(String(right.label ?? right.id ?? ""), "zh-CN"),
      );
      const res = await fetch(apiClientUrl(`/api/projects/${encodeURIComponent(project.id)}`), {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          collaboration_config: {
            ...currentConfig,
            skill_library: nextLibrary,
          },
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json?.error?.message ?? `HTTP ${res.status}`);
      setRecommendedSkillNotice(`已创建：${selected.label}`);
      router.refresh();
    } catch (error) {
      setRecommendedSkillNotice(`创建失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRecommendedSkillSavingId(null);
    }
  }

  async function submitGithubSkillImport(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (githubSkillImporting) return;
    const form = event.currentTarget;
    setGithubSkillImporting(true);
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "include",
        redirect: "follow",
      });
      window.location.assign(response.url || returnPath("skills", "github-import"));
    } catch (error) {
      const target = new URL(returnPath("skills", "github-import"), window.location.origin);
      target.searchParams.set("team_error", error instanceof Error ? error.message : "导入 GitHub Skill 失败");
      window.location.assign(target.toString());
    }
  }

  const [scorecard, setScorecard] = useState<{
    grade: string;
    score: number | null;
    summary: string;
    indicators: Array<{ key: string; label: string; grade?: string; detail: string }>;
  } | null>(null);
  const [scorecardOpen, setScorecardOpen] = useState(false);
  const [broadcastTarget, setBroadcastTarget] = useState<{ scope: string; label: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchProjectScorecard(project.id);
        if (!data || cancelled) return;
        const inds = Object.entries(data.indicators || {}).map(([k, v]: [string, any]) => ({
          key: k,
          label: v.label || k,
          grade: v.grade,
          detail: v.detail || "",
        }));
        setScorecard({
          grade: data.overall?.grade || "—",
          score: data.overall?.score ?? null,
          summary: data.overall?.summary || "",
          indicators: inds,
        });
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  // Keyboard shortcuts to escape Unity iframe focus and re-orient on the
  // dashboard. Acceptance feedback flagged that Unity dominated the screen and
  // there was no fast way to hide it; the cockpit's background toggle works but
  // is buried in a toolbar. Esc collapses the cockpit (gives Unity full focus),
  // Alt+U toggles the Unity scene visibility, Alt+T toggles the task board.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const tag = (target?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
      if (event.altKey && (event.key === "u" || event.key === "U")) {
        event.preventDefault();
        setSceneVisible((value) => !value);
        return;
      }
      if (event.altKey && (event.key === "t" || event.key === "T")) {
        event.preventDefault();
        setTaskBoardOpen((value) => !value);
        return;
      }
      if (event.key === "Escape" && !event.altKey && !event.shiftKey && !event.ctrlKey && !event.metaKey) {
        setCockpitOpen((value) => !value);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const unitySrc = useMemo(() => {
    const query = new URLSearchParams({
      projectId: project.id,
      serverBaseUrl: apiBaseUrl,
      entry: "2d-upgrade",
      scene: UNITY_SCENE_NAME,
      interactionMode: "click-only",
    });
    return `${UNITY_PUBLIC_PATH}/index.html?${query.toString()}`;
  }, [apiBaseUrl, project.id]);

  const modules: ModuleLink[] = useMemo(
    () => [
      {
        label: "开发工坊",
        short: "工",
        hint: "工位、项目知识库、AI 调度主入口",
        tab: "development-workshop",
        tone: "workshop",
        primary: "把项目拆成可协作工位",
        description: "承接项目开发工坊：电脑、App、嵌入式、数据、测试等工位都从这里管理。",
        farmSource: "主页面：开发工坊 / 工位管理",
      },
      {
        label: "主角管理",
        short: "主",
        hint: "成员、账号主角、名下电脑与线程",
        tab: "human-party",
        tone: "core",
        primary: "管理多人多电脑协作身份",
        description: "承接项目成员与负责人视角，默认不常驻遮挡工作区，只在点击后打开。",
        farmSource: "主页面：成员与电脑归属",
      },
      {
        label: "NPC 管理",
        short: "精",
        hint: "创建 NPC、绑定线程、装配能力包",
        tab: "npc-create",
        tone: "agent",
        primary: "创建 AI 协作角色",
        description: "承接 NPC 管理：名字、职责、知识库、能力包、线程绑定、最近任务和对话。",
        farmSource: "主页面：NPC 管理器",
      },
      {
        label: "电脑接入",
        short: "电",
        hint: "执行程序、配对令牌、线程扫描",
        tab: "computers",
        tone: "computer",
        primary: "接入真实电脑",
        description: "承接电脑接入管理：生成配对令牌、注册执行电脑、扫描 Codex/Claude/Qwen 线程。",
        farmSource: "主页面：电脑接入管理",
      },
      {
        label: "能力工坊",
        short: "技",
        hint: "能力包、知识库、Git 治理",
        tab: "skills",
        tone: "skill",
        primary: "进入能力治理正门",
        description: "Git 回退、能力包仓库、NPC 知识库和工位知识库统一收进能力工坊。",
        farmSource: "能力工坊",
      },
      {
        label: "NPC 工作台",
        short: "讯",
        hint: "对话、需求、任务",
        tab: "exchange",
        tone: "review",
        primary: "进入 NPC 瓷砖",
        description: "主页面只保留协作摘要；正式对话、协作请求和人工确认回 NPC 工作台。",
        farmSource: "NPC 工作台",
      },
      {
        label: "线程调试",
        short: "线",
        hint: "真实线程、心跳、队列状态",
        tab: "machine-room",
        tone: "computer",
        primary: "确认线程是否能接单",
        description: "承接电脑线程调试：确认 Codex、Claude、Qwen 等真实线程是否在线。",
        farmSource: "主页面：电脑线程调试",
      },
      {
        label: "版本治理",
        short: "Git",
        hint: "版本点、预检、人工确认",
        tab: "git",
        tone: "review",
        primary: "去能力工坊处理 Git",
        description: "Git 仓库配置、预检、回退登记和审计记录统一进入能力工坊。",
        farmSource: "能力工坊",
      },
    ],
    [],
  );

  const activeModule = modules.find((item) => item.tab === activePanel) ?? null;
  const latestTask = tasks.find((task) => !["done", "completed", "archived"].includes(task.status.toLowerCase())) ?? tasks[0];
  const latestMessage = messages[0];
  const dispatchMessages = messages.filter(isDispatchMessage);
  const ackMessages = messages.filter(isProgressAck);
  const finalMessages = messages.filter(isFinalReply);
  const humanReviewMessages = messages.filter(isHumanReviewMessage);
  const finalReplyCount = finalMessages.length;
  const blockedTaskCount = tasks.filter((task) => /blocked|waiting_approval|reviewing|failed|error|needs_changes/i.test(task.status)).length;
  const humanReviewCount = humanReviewMessages.length + blockedTaskCount;
  const firstWorkstation = workstations[0] ?? null;
  const firstWorkstationLabel = firstWorkstation ? safeThreadName(firstWorkstation, 0) : "";
  const firstNpcSeat = npcSeats[0] ?? null;
  const focusedNpcSeat = npcSeats.find((seat) => seat.id === focusedNpcId) ?? firstNpcSeat ?? null;
  const collaborationTargets = npcSeats.length ? [...npcSeats, ...workstations] : workstations;
  const projectGithubUrl = String(project.github_url ?? "").trim();
  const projectLocalGitUrl = String(project.local_git_url ?? "").trim();
  const projectDefaultBranch = String(project.default_branch ?? "").trim() || "main";
  const projectDevelopBranch = String(project.develop_branch ?? "").trim() || "develop";
  const [gitRollbackTargetRef, setGitRollbackTargetRef] = useState(projectDevelopBranch);
  const gitVersionIndex = useMemo(() => {
    const versions: Array<{ ref: string; label: string; source: string; detail: string; tone: "branch" | "task" | "activity" | "default" }> = [];
    const remember = (item: { ref: string; label: string; source: string; detail: string; tone: "branch" | "task" | "activity" | "default" }) => {
      if (!item.ref || versions.some((version) => version.ref === item.ref)) return;
      versions.push(item);
    };
    remember({
      ref: projectDevelopBranch,
      label: "开发分支",
      source: "项目配置",
      detail: "回到当前协作主线，适合让 Boss 和各工位重新对齐。",
      tone: "branch",
    });
    if (projectDefaultBranch !== projectDevelopBranch) {
      remember({
        ref: projectDefaultBranch,
        label: "默认分支",
        source: "项目配置",
        detail: "回到稳定主线，登记后应同步给 Boss 和工位长。",
        tone: "branch",
      });
    }
    remember({
      ref: "HEAD~1",
      label: "上一个提交",
      source: "安全快捷项",
      detail: "只作为预演目标，不直接执行 reset。",
      tone: "default",
    });
    tasks
      .filter((task) => task.providerId)
      .slice(0, 8)
      .forEach((task) => {
        remember({
          ref: String(task.providerId),
          label: itemTitle(task),
          source: "任务分支",
          detail: `${statusLabel(task.status)} / ${shortCopy(task.body, "任务分支可用于预演影响面", 64)}`,
          tone: "task",
        });
      });
    messages
      .filter((message) => /git|回退|rollback|同步|sync/i.test(`${message.type} ${message.title} ${message.body}`))
      .slice(0, 6)
      .forEach((message) => {
        const bodyTargetRefs = [
          ...String(message.body ?? "").matchAll(/(?:目标版本|target_ref|ref)[:：\s]+([A-Za-z0-9._/~\-]+)/gi),
        ].map((value) => value[1]);
        const candidates = uniqueText([
          ...bodyTargetRefs,
          message.providerId,
        ]);
        const targetRef = candidates[0] ?? "";
        if (!targetRef || isRawUuid(targetRef)) return;
        remember({
          ref: targetRef,
          label: itemTitle(message),
          source: "协作动态",
          detail: shortCopy(cleanFeedCopy(message.body, "最近 Git 动态提到的目标引用"), "最近 Git 动态提到的目标引用", 72),
          tone: "activity",
        });
      });
    return versions.slice(0, 16);
  }, [messages, projectDefaultBranch, projectDevelopBranch, tasks]);
  const gitRollbackAlignmentMessages = useMemo(() => {
    const parseMeta = (message: FeedItem) => {
      try {
        const parsed = JSON.parse(String(message.knowledgeSummary || "{}"));
        return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
      } catch {
        return {};
      }
    };
    const receiptsBySource = new Map<string, FeedItem[]>();
    for (const message of messages) {
      const meta = parseMeta(message);
      const sourceId = String(meta.source_message_id || "").trim();
      if (!sourceId) continue;
      const list = receiptsBySource.get(sourceId) ?? [];
      list.push(message);
      receiptsBySource.set(sourceId, list);
    }
    const npcNameByIdentity = new Map<string, string>();
    for (const seat of npcSeats) {
      const label = itemTitle(seat);
      [seat.id, seat.rowId, seat.name, seat.sourceWorkstationId, seat.providerId]
        .filter(Boolean)
        .forEach((value) => npcNameByIdentity.set(String(value), label));
    }
    return messages
      .filter((message) => {
        const meta = parseMeta(message);
        return meta.source === "git_rollback_alignment" || /Git 回退对齐|回退对齐/i.test(`${message.title} ${message.body}`);
      })
      .filter((message) => message.type === "agent_command")
      .slice()
      .sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")))
      .slice(0, 8)
      .map((message) => {
        const meta = parseMeta(message);
        const receipts = (receiptsBySource.get(message.id) ?? []).slice().sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
        const latestReceipt = receipts[0];
        const body = String(message.body ?? "");
        const refMatch = body.match(/目标版本[:：]\s*([^\s\r\n]+)/);
        return {
          id: message.id,
          title: itemTitle(message),
          status: latestReceipt ? statusLabel(latestReceipt.status) : statusLabel(message.status),
          rawStatus: message.status,
          targetRef: isRawUuid(meta.target_ref || refMatch?.[1] || message.providerId)
            ? "平台记录"
            : String(meta.target_ref || refMatch?.[1] || message.providerId || "未识别"),
          targetNpc: npcNameByIdentity.get(message.sourceWorkstationId || "") || cleanFeedCopy(message.sourceWorkstationId, "未识别 NPC"),
          at: latestReceipt?.at || message.at,
          receiptCount: receipts.length,
          receiptTitle: latestReceipt ? itemTitle(latestReceipt) : "",
        };
      });
  }, [messages, npcSeats]);
  const gitRunnerPreflightStatus = useMemo(() => {
    const isRunnerOnline = (value: string | undefined) => {
      const normalized = String(value || "").toLowerCase();
      return ["online", "watching", "connected", "ready", "active"].some((status) => normalized.includes(status));
    };
    const onlineComputers = computers.filter((computer) => isRunnerOnline(computer.runnerEffectiveStatus || computer.status));
    const runnableComputers = onlineComputers.filter((computer) => computer.runnerId || computer.providerId);
    const gitPreflightMessages = messages.filter((message) => /Git 回退只读预检|git\.preflight/i.test(`${message.title} ${message.body}`));
    const openPreflights = gitPreflightMessages.filter((message) =>
      ["queued", "pending", "acked", "in_progress"].includes(String(message.status || "").toLowerCase()),
    );
    if (openPreflights.length) {
      return {
        tone: "pending",
        title: `只读预检待回执 ${openPreflights.length} 条`,
        detail: "已有回退预检命令进入队列，等待对应执行程序回执。若电脑离线，请先回“电脑接入”重新运行持续接单命令。",
      };
    }
    if (!onlineComputers.length) {
      return {
        tone: "blocked",
        title: "暂无常驻接单电脑",
        detail: "登记回退会保留审计和 Boss 对齐，但不会假装已经完成本地 Git 只读预检。",
      };
    }
    if (!runnableComputers.length) {
      return {
        tone: "blocked",
        title: "电脑登记在线但缺少执行程序绑定",
        detail: "先回电脑接入面板生成配对令牌，并让目标电脑完成执行程序注册。",
      };
    }
    return {
      tone: "ready",
      title: `常驻接单 ${runnableComputers.length} 台`,
      detail: "登记回退后会向常驻接单电脑下发只读 Git 预检；仍不会执行 reset / revert / delete。",
    };
  }, [computers, messages]);
  const currentGitRollbackAlignment = useMemo(() => {
    const target = gitRollbackTargetRef.trim();
    if (!target) return gitRollbackAlignmentMessages[0] ?? null;
    return gitRollbackAlignmentMessages.find((message) => message.targetRef === target) ?? gitRollbackAlignmentMessages[0] ?? null;
  }, [gitRollbackAlignmentMessages, gitRollbackTargetRef]);
  const historicalGitRollbackAlignments = useMemo(() => {
    const currentId = currentGitRollbackAlignment?.id;
    return gitRollbackAlignmentMessages.filter((message) => message.id !== currentId).slice(0, 5);
  }, [currentGitRollbackAlignment, gitRollbackAlignmentMessages]);
  useEffect(() => {
    if (gitRollbackTargetRef.trim()) return;
    setGitRollbackTargetRef(gitRollbackAlignmentMessages[0]?.targetRef ?? gitVersionIndex[0]?.ref ?? projectDevelopBranch);
  }, [gitRollbackAlignmentMessages, gitRollbackTargetRef, gitVersionIndex, projectDevelopBranch]);

  function returnPath(tab: ModuleTab, actionId?: string) {
    const params = new URLSearchParams({ panel: tab });
    if (actionId) params.set("action", actionId);
    if (returnToPath) params.set("return_to", returnToPath);
    const source = searchParams?.get("from");
    if (source) params.set("from", source);
    return `/projects/${project.id}/2d-upgrade?${params.toString()}`;
  }

  function surfacePath(surface: "workbench" | "company" | "datasets" | "ai-lab" | "robotics" | "rehab-arm-control" | "observability" | "skill-forge", tab: ModuleTab = activePanel ?? "exchange", actionId = activeAction?.id) {
    const params = new URLSearchParams({
      return_to: returnPath(tab, actionId),
      from: "2d-upgrade",
    });
    return `/projects/${project.id}/${surface}?${params.toString()}`;
  }

  function renderWorkshopStationHiddenFields(
    station: WorkshopStationItem,
    returnTab: ModuleTab = "development-workshop",
    returnActionId?: string,
  ) {
    return (
      <>
        <input type="hidden" name="return_to" value={returnPath(returnTab, returnActionId)} />
        <input type="hidden" name="station_id" value={station.id} />
        <input type="hidden" name="label" value={station.label} />
        <input type="hidden" name="icon" value={station.icon} />
        <input type="hidden" name="station" value={station.station} />
        <input type="hidden" name="map_scene" value={station.mapScene} />
        <input type="hidden" name="map_location" value={station.mapLocation} />
        <input type="hidden" name="detail" value={station.detail} />
        <input type="hidden" name="modes" value={listToFormValue(station.modes)} />
        <input type="hidden" name="backend_anchor" value={station.backendAnchor} />
        <input type="hidden" name="runner_capabilities" value={listToFormValue(station.runnerCapabilities)} />
        <input type="hidden" name="ai_responsibilities" value={listToFormValue(station.aiResponsibilities)} />
        <input type="hidden" name="npc_role_templates" value={listToFormValue(station.npcRoleTemplates)} />
        <input type="hidden" name="assignment_keywords" value={listToFormValue(station.assignmentKeywords)} />
        <input type="hidden" name="next_actions" value={listToFormValue(station.nextActions)} />
        <input type="hidden" name="approval_policy" value={station.approvalPolicy} />
        <input type="hidden" name="risk_level" value={station.riskLevel} />
        <input type="hidden" name="knowledge_summary" value={station.knowledgeSummary} />
        <input type="hidden" name="knowledge_handoff_path" value={station.knowledgeHandoffPath} />
        <input type="hidden" name="knowledge_tags" value={listToFormValue(station.knowledgeTags)} />
      </>
    );
  }

  function openPanel(tab: ModuleTab, source = "右侧入口") {
    setActivePanel(tab);
    setActiveAction(null);
    setLoadingActionId(null);
    setPanelNotice(`${source} 已打开：${modules.find((item) => item.tab === tab)?.label ?? "平台功能"}`);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("panel", tab);
      url.searchParams.delete("tab");
      url.searchParams.delete("action");
      url.searchParams.delete("pairing_node");
      url.searchParams.delete("pairing_token");
      window.history.replaceState(null, "", url.toString());
    }
  }

  function openNpcSeat(seat: FeedItem) {
    const dialogueAction = PANEL_ACTIONS["npc-create"].find((action) => action.id === "npc-dialogue") ?? null;
    setFocusedNpcId(seat.id);
    setActivePanel("npc-create");
    setActiveAction(dialogueAction);
    setLoadingActionId(null);
    setPanelNotice(`已从地图选中 NPC：${itemTitle(seat)}，正在打开它的对话框。`);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("panel", "npc-create");
      url.searchParams.set("action", "npc-dialogue");
      url.searchParams.delete("tab");
      window.history.replaceState(null, "", url.toString());
    }
  }

  function closePanel() {
    setActivePanel(null);
    setActiveAction(null);
    setFocusedNpcId(null);
    setLoadingActionId(null);
    setPanelNotice("已回到 Unity 背景。继续点击右侧功能入口即可打开平台面板。");
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("panel");
      url.searchParams.delete("action");
      url.searchParams.delete("pairing_node");
      url.searchParams.delete("pairing_token");
      window.history.replaceState(null, "", url.toString());
    }
  }

  function renderNpcSeatHiddenFields(
    seat: FeedItem,
    returnTab: ModuleTab = "npc-create",
    options: { includeKnowledge?: boolean; includeSkillLoadout?: boolean; returnActionId?: string } = {},
  ) {
    const includeKnowledge = options.includeKnowledge ?? true;
    const includeSkillLoadout = options.includeSkillLoadout ?? true;
    return (
      <>
        <input type="hidden" name="return_to" value={returnPath(returnTab, options.returnActionId)} />
        <input type="hidden" name="name" value={itemTitle(seat)} />
        <input type="hidden" name="status" value={seat.status || "idle"} />
        <input type="hidden" name="responsibility" value={seat.responsibility || seat.body || "负责当前项目 AI 协作任务。"} />
        <input type="hidden" name="model" value={seat.model || "gpt-5.4"} />
        <input type="hidden" name="permission_level" value={seat.permissionLevel || "L2"} />
        <input type="hidden" name="scene" value={seat.scene || "unity-2d-upgrade"} />
        <input type="hidden" name="avatar_key" value={seat.avatarKey || "a-agent-lab-npc"} />
        <input type="hidden" name="map_x" value={String(seat.mapX ?? 52)} />
        <input type="hidden" name="map_y" value={String(seat.mapY ?? 44)} />
        {includeKnowledge ? (
          <>
            <input type="hidden" name="knowledge_summary" value={seat.knowledgeSummary || ""} />
            <input type="hidden" name="knowledge_handoff_path" value={seat.knowledgeHandoffPath || ""} />
          </>
        ) : null}
        {includeSkillLoadout
          ? (seat.skillLoadout ?? []).map((skill) => (
              <input key={skill} type="hidden" name="skill_loadout" value={skill} />
            ))
          : null}
      </>
    );
  }

  function openAction(action: PanelAction) {
    setLoadingActionId(action.id);
    setPanelNotice(`正在打开三级抽屉：${action.label}`);
    setActiveAction(action);
    setLoadingActionId(null);
    setPanelNotice(`三级抽屉已打开：${action.label}`);
    if (typeof window !== "undefined" && activeModule) {
      const url = new URL(window.location.href);
      url.searchParams.set("panel", activeModule.tab);
      url.searchParams.set("action", action.id);
      if (action.id !== "pairing-token") {
        url.searchParams.delete("pairing_node");
        url.searchParams.delete("pairing_token");
      }
      window.history.replaceState(null, "", url.toString());
    }
  }

  function closeAction() {
    setActiveAction(null);
    setLoadingActionId(null);
    setPanelNotice(activeModule ? `已回到二级面板：${activeModule.label}` : "已回到 Unity 背景。");
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("action");
      window.history.replaceState(null, "", url.toString());
    }
  }

  useEffect(() => {
    function syncFromUrl() {
      const params = new URLSearchParams(window.location.search);
      setWebBaseUrl(window.location.origin);
      const tab = params.get("panel") || params.get("tab");
      const actionId = params.get("action");
      if (isModuleTab(tab)) {
        setActivePanel(tab);
        const action = actionId ? PANEL_ACTIONS[tab].find((item) => item.id === actionId) ?? null : null;
        if (action) {
          setActiveAction(action);
          setPanelNotice(`已打开三级抽屉：${action.label}`);
        }
      }
    }

    function handleMessage(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      const data = event.data as { type?: string; tab?: string; href?: string } | null;
      if (!data || data.type !== "a-agent-open-panel") return;
      const tab = isModuleTab(data.tab) ? data.tab : data.href ? parseModuleTabFromHref(data.href) : null;
      if (tab) openPanel(tab, "Unity 消息");
    }

    function handleCustomPanel(event: Event) {
      const detail = (event as CustomEvent).detail as { tab?: string } | undefined;
      if (isModuleTab(detail?.tab)) openPanel(detail.tab, "Unity 事件");
    }

    syncFromUrl();
    window.addEventListener("message", handleMessage);
    window.addEventListener("popstate", syncFromUrl);
    window.addEventListener("a-agent-open-panel", handleCustomPanel);

    return () => {
      window.removeEventListener("message", handleMessage);
      window.removeEventListener("popstate", syncFromUrl);
      window.removeEventListener("a-agent-open-panel", handleCustomPanel);
    };
  }, []);

  function renderList(items: FeedItem[], emptyText: string) {
    return (
      <ul className={styles.panelList}>
        {feedSummary(items, emptyText).map((item) => (
          <li key={item.id}>
            <b>{itemTitle(item)}</b>
            <small>{itemBody(item) || statusLabel(item.status)}</small>
          </li>
        ))}
      </ul>
    );
  }

  function renderKnowledgeDocumentList(items: KnowledgeDocumentItem[], emptyText: string) {
    const visible = items.slice(0, 8);
    return (
      <ul className={styles.panelList}>
        {visible.length ? visible.map((item) => {
          const syncDetail = [
            item.existsInRepo === true ? "已确认存在" : item.existsInRepo === false ? "未确认存在" : "待同步",
            item.versionRef ? `版本 ${item.versionRef}` : "",
            item.lastSyncedAt ? `同步 ${item.lastSyncedAt.slice(0, 10)}` : "",
          ].filter(Boolean).join(" / ");
          const ownerDetail = [item.scope, item.ownerType && item.ownerId ? `${item.ownerType}:${item.ownerId}` : ""]
            .filter(Boolean)
            .join(" · ");
          return (
            <li key={item.id}>
              <b>{item.title}</b>
              <small>{item.repoRelativePath}</small>
              <small>{[ownerDetail, syncDetail].filter(Boolean).join(" ｜ ")}</small>
            </li>
          );
        }) : (
          <li>
            <b>空状态</b>
            <small>{emptyText}</small>
          </li>
        )}
      </ul>
    );
  }

  function renderSkillLifecycleList(items: FeedItem[], emptyText: string) {
    const visible = items.slice(0, 10);
    return (
      <ul className={styles.skillLifecycleList}>
        {visible.length ? visible.map((skill) => {
          const assignedCount = skill.assignedSeatIds?.length ?? 0;
          return (
            <li key={skill.id} data-source={skill.source || skill.type} data-draft={skill.draftStatus || skill.status}>
              <div>
                <b>{itemTitle(skill)}</b>
                <small>{shortCopy(itemBody(skill), "暂无说明", 96)}</small>
                {skill.repoRelativePath ? <small>路径：{skill.repoRelativePath}</small> : null}
              </div>
              <span>{skillLifecycleLabel(skill)}</span>
              <small>{assignedCount ? `已关联 ${assignedCount} 个 NPC` : "未关联 NPC"}</small>
            </li>
          );
        }) : (
          <li>
            <div>
              <b>{emptyText}</b>
              <small>从 GitHub 导入，或让 NPC 在项目开发中沉淀 Skill 草稿。</small>
            </div>
          </li>
        )}
      </ul>
    );
  }

  function renderMetricGrid() {
    return (
      <div className={styles.metricGrid}>
        <span><b>{stats.requirementCount}</b>需求</span>
        <span><b>{stats.activeTaskCount}</b>进行中</span>
        <span><b>{stats.blockedTaskCount}</b>阻塞</span>
        <span><b>{stats.onlineComputerCount}/{stats.computerCount}</b>台常驻接单</span>
      </div>
    );
  }

  function renderLogicalWorkstationSummary() {
    const unassignedNpcCount = npcSeats.filter((seat) => !seat.workstationId).length;
    const missingLeadCount = projectWorkstations.filter((ws) => !ws.leadSeatId).length;
    const leadOnlyWorkstations = projectWorkstations.filter((ws) => ws.leadSeatId && ws.seatCount === 0);
    const canRepairLeadMembership = leadOnlyWorkstations.length > 0;
    async function repairLeadMembership() {
      if (!canRepairLeadMembership || workstationRepairing) return;
      setWorkstationRepairing(true);
      setWorkstationRepairNotice(null);
      try {
        let repaired = 0;
        for (const ws of leadOnlyWorkstations) {
          const leadSeatId = ws.leadSeatId || "";
          const leadSeat = npcSeats.find((seat) =>
            seat.id === leadSeatId || seat.rowId === leadSeatId || itemTitle(seat) === leadSeatId,
          );
          const seatId = leadSeat?.id || leadSeat?.rowId || leadSeatId;
          if (!seatId) continue;
          const res = await fetch(apiClientUrl(`/api/projects/${encodeURIComponent(project.id)}/workstations/${encodeURIComponent(ws.id)}/seats`), {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ seat_ids: [seatId] }),
          });
          const json = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(json?.error?.message ?? `${ws.name} 归位失败`);
          repaired += 1;
        }
        setWorkstationRepairNotice(`已补齐 ${repaired} 个工位长的 NPC 归属`);
        router.refresh();
      } catch (error) {
        setWorkstationRepairNotice(`补齐失败：${error instanceof Error ? error.message : String(error)}`);
      } finally {
        setWorkstationRepairing(false);
      }
    }
    return (
      <div className={styles.logicalWorkstationSummary}>
        <section className={styles.workstationSetupGuide}>
          <div>
              <strong>平台协作先做这三步</strong>
            <p>逻辑工位、NPC 归属、工位长都在主页面治理；工作台只复用这些资源。</p>
          </div>
          <div className={styles.workstationSetupSteps}>
            <span data-done={projectWorkstations.length > 0 ? "1" : "0"}>1. 逻辑工位 {projectWorkstations.length}</span>
            <span data-done={unassignedNpcCount === 0 && npcSeats.length > 0 ? "1" : "0"}>2. 未归属 NPC {unassignedNpcCount}</span>
            <span data-done={missingLeadCount === 0 && projectWorkstations.length > 0 ? "1" : "0"}>3. 未设工位长 {missingLeadCount}</span>
          </div>
        </section>
        {canRepairLeadMembership ? (
          <section className={styles.workstationSetupGuide}>
            <div>
              <strong>工位长已选，但 NPC 还没归位</strong>
              <p>这会让工作台看不到同工位关系。平台可以直接按已选工位长补齐归属，不需要用户再写提示词。</p>
              {workstationRepairNotice ? <small>{workstationRepairNotice}</small> : null}
            </div>
            <button
              type="button"
              className={styles.workstationBlueprintBtn}
              onClick={repairLeadMembership}
              disabled={workstationRepairing}
            >
              {workstationRepairing ? "补齐中..." : "一键补齐工位长归属"}
            </button>
          </section>
        ) : workstationRepairNotice ? (
          <small>{workstationRepairNotice}</small>
        ) : null}
        <ul className={styles.logicalWorkstationList}>
          {projectWorkstations.length ? (
            projectWorkstations.map((ws) => {
              const leadName = ws.leadSeatId
                ? (npcSeats.find((seat) => seat.id === ws.leadSeatId || seat.rowId === ws.leadSeatId || itemTitle(seat) === ws.leadSeatId)?.name ?? ws.leadSeatId.slice(0, 8))
                : "未设工位长";
              return (
                <li key={ws.id}>
                  <b>{ws.name}</b>
                  <small>{ws.seatCount} 个 NPC · 工位长：{leadName}</small>
                </li>
              );
            })
          ) : (
            <li>
              <b>还没有逻辑工位</b>
              <small>先添加工位，再把 NPC 分配进去。</small>
            </li>
          )}
        </ul>
      </div>
    );
  }

  function renderCollaborationFlowBoard() {
    const steps = [
      {
        label: "1. 必读需求",
        count: requirements.length,
        detail: "人和 AI 提的需求先进入统一需求表，写清提需求者、被提需求者、边界和验收。",
      },
      {
        label: "2. 平台派单",
        count: dispatchMessages.length,
        detail: "派单必须指定 NPC/线程。目标关闭自动化时，只执行当前一轮。",
      },
      {
        label: "3. 已收到提醒",
        count: ackMessages.length,
        detail: "接单后先回已收到提醒，说明是否已读需求、能否执行、是否需要人工确认。",
      },
      {
        label: "4. 最终回复",
        count: finalReplyCount,
        detail: "最终结果进入最终回复池；过程噪声留在本机 AI 线程，不堆首页。",
      },
    ];

    return (
      <article className={styles.collabFlowBoard} aria-label="AI 协作链路">
        <header>
          <span>AI 协作链路</span>
          <strong>{humanReviewMessages.length ? `${humanReviewMessages.length} 条需人工确认` : "当前无强制确认提醒"}</strong>
          <p>这里回答“AI 到底怎么协作”：先读需求，再平台派单，再已收到提醒，最后只把最终回复收口。</p>
        </header>
        <div className={styles.flowSteps}>
          {steps.map((step) => (
            <section key={step.label}>
              <b>{step.count}</b>
              <span>{step.label}</span>
              <small>{step.detail}</small>
            </section>
          ))}
        </div>
        {humanReviewMessages.length ? (
          <div className={styles.reviewStrip}>
            <b>需要人工处理</b>
            <p>{itemTitle(humanReviewMessages[0])}：{itemBody(humanReviewMessages[0])}</p>
          </div>
        ) : (
          <div className={styles.reviewStrip}>
            <b>自动化边界</b>
            <p>未开启 NPC 自动化时，协作指令只做一次；开启后才允许按心跳继续推进。</p>
          </div>
        )}
      </article>
    );
  }

  function renderConnectivityBoard(tab: ModuleTab) {
    const actions = PANEL_ACTIONS[tab];
    const rows = actions.map((action) => ({
      action,
      connectivity: actionConnectivity(tab, action),
    }));
    const readyCount = rows.filter((row) => row.connectivity.tone === "ready").length;
    const safeCount = rows.filter((row) => row.connectivity.tone === "readonly" || row.connectivity.tone === "review").length;
    const previewCount = rows.filter((row) => row.connectivity.tone === "preview").length;
    const pendingCount = rows.filter((row) => row.connectivity.tone === "pending").length;

    return (
      <article className={styles.connectivityBoard} aria-label={`${activeModule?.label ?? "模块"} 连通状态`}>
        <header>
          <span>全功能连通状态</span>
          <strong>{readyCount + previewCount}/{actions.length} 个动作可真实推进</strong>
          <p>每个按钮现在都标清楚会不会落库、会不会派单、会不会消耗自动化 token。小白用户先看这里，再点下面的三级抽屉。</p>
        </header>
        <div className={styles.connectivitySummary}>
          <span><b>{readyCount}</b>真实表单</span>
          <span><b>{previewCount}</b>预演登记</span>
          <span><b>{safeCount}</b>只读/确认</span>
          <span><b>{pendingCount}</b>待接线</span>
        </div>
        <ul className={styles.connectivityList}>
          {rows.map(({ action, connectivity }) => (
            <li key={action.id}>
              <b>{action.label}</b>
              <span className={`${styles.connectivityBadge} ${connectivityToneClass(connectivity.tone)}`}>{connectivity.label}</span>
              <small>{connectivity.detail}</small>
            </li>
          ))}
        </ul>
      </article>
    );
  }

  function renderActionForm(action: PanelAction, moduleTab: ModuleTab) {
    function renderGitRollbackVersionIndex() {
      return (
        <section className={styles.githubImportGuide} data-git-rollback-version-index="1">
          <b>可回退版本索引</b>
          <p>
            先选一个目标做只读预演。知识库和跨电脑协作仍以 GitHub 仓库为准，每台电脑只管理自己的工作目录。
          </p>
          <dl>
            <div>
              <dt>仓库</dt>
              <dd>{projectGithubUrl || projectLocalGitUrl || "尚未绑定仓库地址"}</dd>
            </div>
            <div>
              <dt>规则</dt>
              <dd>登记请求不会直接 reset；必须通过人工确认、执行电脑只读预检和 NPC 对齐回执。</dd>
            </div>
            <div>
              <dt>执行电脑</dt>
              <dd>{gitRunnerPreflightStatus.title}：{gitRunnerPreflightStatus.detail}</dd>
            </div>
          </dl>
          <div className={styles.gitVersionIndexGrid}>
            {gitVersionIndex.map((version) => (
              <button
                key={`git-version-${version.ref}`}
                type="button"
                className={styles.gitVersionCard}
                data-active={gitRollbackTargetRef === version.ref ? "1" : undefined}
                data-tone={version.tone}
                onClick={() => setGitRollbackTargetRef(version.ref)}
                title={`选择 ${version.ref} 作为回退预演目标`}
              >
                <span>{version.source}</span>
                <b>{version.label}</b>
                <code>{version.ref}</code>
                <small>{version.detail}</small>
              </button>
            ))}
          </div>
          <div className={styles.gitAlignmentStatus}>
            <div className={styles.gitAlignmentHead}>
              <strong>当前目标的 NPC 对齐</strong>
              <Link href={surfacePath("workbench", "git")} title="进入工作台查看 NPC 对话和最终回执">
                去工作台
              </Link>
            </div>
            {currentGitRollbackAlignment ? (
              <article className={styles.gitAlignmentCurrent}>
                <span>{currentGitRollbackAlignment.targetRef}</span>
                <strong>{currentGitRollbackAlignment.title}</strong>
                <small>
                  {currentGitRollbackAlignment.targetNpc} · {currentGitRollbackAlignment.status}
                  {currentGitRollbackAlignment.receiptCount ? ` · 回执 ${currentGitRollbackAlignment.receiptCount}` : " · 待回执"}
                  {currentGitRollbackAlignment.receiptTitle ? ` · ${currentGitRollbackAlignment.receiptTitle}` : ""}
                  {currentGitRollbackAlignment.at ? ` · ${currentGitRollbackAlignment.at}` : ""}
                </small>
              </article>
            ) : (
              <p>当前目标还没有 NPC 对齐消息。登记回退请求后，Boss / 工位长会在工作台收到对齐任务并回已收到提醒。</p>
            )}
            {historicalGitRollbackAlignments.length ? (
              <details className={styles.gitAlignmentHistory}>
                <summary>历史对齐记录（{historicalGitRollbackAlignments.length}）</summary>
                <ul>
                  {historicalGitRollbackAlignments.map((message) => (
                    <li key={`git-align-${message.id}`}>
                      <span>{message.targetRef}</span>
                      <strong>{message.title}</strong>
                      <small>
                        {message.targetNpc} · {message.status}
                        {message.receiptCount ? ` · 回执 ${message.receiptCount}` : " · 待回执"}
                        {message.receiptTitle ? ` · ${message.receiptTitle}` : ""}
                        {message.at ? ` · ${message.at}` : ""}
                      </small>
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>
        </section>
      );
    }

    if (moduleTab === "development-workshop" && action.id === "create-station") {
      return (
        <form action={createDevelopmentWorkshopStation.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="workshop-create-station">
          <input type="hidden" name="return_to" value={returnPath("development-workshop", "create-station")} />
          <label>
            <span>工位名称</span>
            <input name="label" required placeholder="例如：NanoPi 工位 / Unity UI 工位 / 测试验收工位" />
          </label>
          <label>
            <span>工位标识</span>
            <input name="station_id" placeholder="例如：nanopi-station" />
          </label>
          <label>
            <span>职责说明</span>
            <textarea name="detail" required rows={3} placeholder="这个工位负责什么、哪些 NPC 可以挂在这里、哪些动作必须人工确认。" />
          </label>
          <label>
            <span>总知识库摘要</span>
            <textarea name="knowledge_summary" rows={4} placeholder="写给这个工位下所有 NPC 必读的共享背景，例如仓库、硬件、接口、验收标准。" />
          </label>
          <label>
            <span>执行电脑能力，逗号分隔</span>
            <input name="runner_capabilities" placeholder="例如：git, read-only, unity, serial" />
          </label>
          <label>
            <span>人工确认策略</span>
            <select name="approval_policy" defaultValue="human_review_for_hardware_and_destructive">
              <option value="human_review_for_hardware_and_destructive">硬件/删除/发布/回退必须人工确认</option>
              <option value="read_only_auto_allowed">只读可自动推进</option>
              <option value="human_review_required">全部先人工确认</option>
            </select>
          </label>
          <SubmitButton label="创建工位" />
        </form>
      );
    }

    if (moduleTab === "development-workshop" && action.id === "station-knowledge") {
      return (
        <form action={createDevelopmentWorkshopStation.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="workshop-knowledge">
          <input type="hidden" name="return_to" value={returnPath("development-workshop", "station-knowledge")} />
          <input type="hidden" name="label" value="临时知识库工位" />
          <input type="hidden" name="detail" value="从项目工坊知识库抽屉沉淀的共享知识。" />
          <label>
            <span>知识库标签</span>
            <input name="knowledge_tags" placeholder="例如：unity-ui, runner, serial, git-safe" />
          </label>
          <label>
            <span>知识库摘要</span>
            <textarea name="knowledge_summary" required rows={6} placeholder="把这个工位下所有 NPC 必须知道的长期知识写在这里。" />
          </label>
          <label>
            <span>交接文档路径</span>
            <input name="knowledge_handoff_path" placeholder="例如：docs/ai-handoffs/codex-platform-autonomy-current.md" />
          </label>
          <SubmitButton label="沉淀为工位知识" />
        </form>
      );
    }

    if (moduleTab === "development-workshop" && action.id === "assign-npc") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="workshop-assign-npc">
          <article className={styles.realNote}>
            <b>工位只保存职责关系，不会自动派单</b>
            <p>用户可以给一个工位挂多个 NPC。工位总知识库仍归工位，NPC 私有知识库仍跟着 NPC 走。</p>
          </article>
          {workshopStations.length && npcSeats.length ? (
            workshopStations.map((station) => (
              <form key={station.id} action={updateDevelopmentWorkshopStation.bind(null, project.id, station.id)} className={styles.inlineActionForm}>
                {renderWorkshopStationHiddenFields(station, "development-workshop", "assign-npc")}
                <label>
                  <span>{station.label} 负责 NPC</span>
                  <div className={styles.skillChecklist}>
                    {npcSeats.map((seat) => (
                      <label key={seat.id} className={styles.skillOption}>
                        <input
                          type="checkbox"
                          name="assigned_npc_ids"
                          value={seat.id}
                          defaultChecked={station.assignedNpcIds.includes(seat.id)}
                        />
                        <span>{itemTitle(seat)} / {seat.responsibility || seat.body || "暂无职责"} / {automationLabel(seat)}</span>
                      </label>
                    ))}
                  </div>
                </label>
                <SubmitButton label="保存工位负责 NPC" />
              </form>
            ))
          ) : (
            <p className={styles.emptyHint}>
              {workshopStations.length ? "暂无可挂载 NPC，先到 NPC 管理创建。" : "暂无工位，先添加一个开发工坊工位。"}
            </p>
          )}
        </div>
      );
    }

    if (moduleTab === "human-party" && action.id === "invite-member") {
      return (
        <form action={sendWorkspaceInvitation} className={styles.drawerForm} data-unity-real-form="human-invite-member">
          <input type="hidden" name="project_id" value={project.id} />
          <input type="hidden" name="return_to" value={returnPath("human-party", "invite-member")} />
          <label>
            <span>协作者邮箱</span>
            <input name="email" type="email" required placeholder="例如：teammate@company.com" />
          </label>
          <label>
            <span>角色</span>
            <select name="role" defaultValue="collaborator">
              <option value="collaborator">协作者</option>
              <option value="viewer">只读观察者</option>
              <option value="maintainer">项目维护者</option>
            </select>
          </label>
          <label>
            <span>邀请备注</span>
            <textarea name="note" rows={4} placeholder="说明这个账号进入项目后主要负责什么，以及能不能接入电脑和线程。" />
          </label>
          <SubmitButton label="发送邀请" />
        </form>
      );
    }

    if (moduleTab === "human-party" && (action.id === "role-permission" || action.id === "presence")) {
      const isRolePanel = action.id === "role-permission";
      return (
        <div className={styles.realActionStack} data-unity-real-form={`human-${action.id}`}>
          <article className={styles.realNote}>
            <b>{isRolePanel ? "权限变更必须项目负责人确认" : "协作现场按成员、电脑、线程三层看"}</b>
            <p>{isRolePanel ? "这里先做可视化权限核对，不提供静默改权。邀请新成员走“邀请协作者”，已有成员改权后续必须由项目负责人确认。" : "用户先确认谁在项目里、哪台电脑在线、哪些线程可投递，再决定是否下发协作指令。"}</p>
          </article>
          <div className={styles.layeredList}>
            {projectMembers.length ? (
              projectMembers.map((member) => (
                <article key={member.id} className={styles.layeredItem}>
                  <span>{memberRoleLabel(member)}</span>
                  <b>{itemTitle(member)}</b>
                  <small>{statusLabel(member.status)} / {member.body || "暂无邮箱"}</small>
                  <p>{isRolePanel ? "可查看角色和状态；涉及权限提升、踢人、跨项目授权时必须项目负责人确认。" : "项目成员可进入同一张协作地图；名下电脑和线程仍按项目隔离显示。"}</p>
                </article>
              ))
            ) : (
              <article className={styles.layeredItem}>
                <span>空状态</span>
                <b>暂无项目成员数据</b>
                <p>如果你已登录但这里为空，请先回项目列表重新进入，或检查项目成员接口是否可读。</p>
              </article>
            )}
          </div>
          {!isRolePanel ? (
            <div className={styles.onlineCheckGrid}>
              <span><b>{projectMembers.length}</b>项目主角</span>
              <span><b>{computers.length}</b>接入电脑</span>
              <span><b>{workstations.length}</b>可见线程</span>
              <span><b>{npcSeats.length}</b>NPC 席位</span>
            </div>
          ) : null}
        </div>
      );
    }

    if (moduleTab === "npc-create" && action.id === "create-npc") {
      return (
        <form action={createNpcWorkstationSeat.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="npc-create">
          <input type="hidden" name="return_to" value={returnPath("npc-create", "create-npc")} />
          <input type="hidden" name="scene" value="unity-2d-upgrade" />
          <input type="hidden" name="avatar_key" value="a-agent-lab-npc" />
          <label>
            <span>NPC 名字</span>
            <input name="name" required placeholder="例如：小A前端工程师" />
          </label>
          <label>
            <span>职责</span>
            <textarea name="responsibility" required rows={3} placeholder="例如：负责工作台 UI 验收、截图、前端接线和最终回复。" />
          </label>
          <label>
            <span>绑定线程，可选</span>
            <select name="source_workstation_id" defaultValue={firstWorkstation?.id ?? ""}>
              <option value="">先不绑定线程</option>
              {workstations.map((item) => (
                <option key={item.id} value={item.id}>
                  {itemTitle(item)} / {item.type || "线程"} / {statusLabel(item.status)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>模型</span>
            <input name="model" defaultValue="gpt-5.4" />
          </label>
          <label className={styles.checkboxLine}>
            <input type="checkbox" name="automation_enabled" value="1" />
            <span>开启自动化心跳。默认不开，避免无意消耗 token。</span>
          </label>
          <label>
            <span>心跳间隔秒数</span>
            <input name="automation_heartbeat_seconds" type="number" min={300} step={60} defaultValue={900} />
          </label>
          <SubmitButton label="创建真实 NPC" />
        </form>
      );
    }

    if (moduleTab === "npc-create" && action.id === "bind-thread") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="npc-bind-thread">
          <article className={styles.realNote}>
            <b>已有 NPC 可在这里重新绑定真实线程</b>
            <p>默认只改绑定关系，不会自动派单；是否持续自动化请到 AI 调试里单独开关。</p>
          </article>
          {npcSeats.length ? (
            npcSeats.map((seat) => (
              <form key={seat.id} action={updateNpcWorkstationSeat.bind(null, project.id, seat.id)} className={styles.inlineActionForm}>
                {renderNpcSeatHiddenFields(seat, "npc-create", { returnActionId: "bind-thread" })}
                <label>
                  <span>{itemTitle(seat)} 绑定线程</span>
                  <select name="source_workstation_id" defaultValue={seat.sourceWorkstationId || ""}>
                    <option value="">不绑定线程</option>
                    {workstations.map((item) => (
                      <option key={item.id} value={item.id}>
                        {sourceThreadOptionLabel(item)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>电脑节点，可选</span>
                  <select name="computer_node_id" defaultValue={seat.computerNodeId || ""}>
                    <option value="">跟随线程</option>
                    {computers.map((item) => (
                      <option key={item.id} value={item.id}>
                        {itemTitle(item)} / {statusLabel(item.status)}
                      </option>
                    ))}
                  </select>
                </label>
                <input type="hidden" name="automation_enabled" value={seat.automationEnabled ? "true" : "false"} />
                <input type="hidden" name="automation_heartbeat_seconds" value={String(seat.automationHeartbeatSeconds ?? 900)} />
                <SubmitButton label="保存绑定" disabled={!workstations.length} />
              </form>
            ))
          ) : (
            <p className={styles.emptyHint}>还没有 NPC。先在“创建 NPC”里创建一个精灵席位。</p>
          )}
        </div>
      );
    }

    if (moduleTab === "npc-create" && action.id === "npc-knowledge") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="npc-knowledge">
          <article className={styles.realNote}>
            <b>知识跟着 NPC 走，不跟着电脑或线程走</b>
            <p>以后换电脑、换模型、换线程时，NPC 仍会继承这里的长期知识和交接路径。</p>
          </article>
          {npcSeats.length ? (
            npcSeats.map((seat) => (
              <form key={seat.id} action={updateNpcWorkstationSeat.bind(null, project.id, seat.id)} className={styles.inlineActionForm}>
                {renderNpcSeatHiddenFields(seat, "npc-create", { includeKnowledge: false, returnActionId: "npc-knowledge" })}
                <input type="hidden" name="source_workstation_id" value={seat.sourceWorkstationId || ""} />
                <input type="hidden" name="computer_node_id" value={seat.computerNodeId || ""} />
                <input type="hidden" name="automation_enabled" value={seat.automationEnabled ? "true" : "false"} />
                <input type="hidden" name="automation_heartbeat_seconds" value={String(seat.automationHeartbeatSeconds ?? 900)} />
                <label>
                  <span>{itemTitle(seat)} 长期知识摘要</span>
                  <textarea name="knowledge_summary" rows={5} defaultValue={seat.knowledgeSummary || ""} placeholder="写清楚这个 NPC 的固定职责、项目约束、必读文档、不能做的事。" />
                </label>
                <label>
                  <span>交接文档路径</span>
                  <input name="knowledge_handoff_path" defaultValue={seat.knowledgeHandoffPath || ""} placeholder="docs/ai-handoffs/xxx.md" />
                </label>
                <SubmitButton label="保存知识库" />
              </form>
            ))
          ) : (
            <p className={styles.emptyHint}>还没有 NPC。先创建 NPC，再维护知识库。</p>
          )}
        </div>
      );
    }

    if (moduleTab === "npc-create" && action.id === "npc-skills") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="npc-skills">
          <article className={styles.realNote}>
            <b>这里只给 NPC 装配能力包，能力包源头仍在能力仓库</b>
            <p>固定能力包会随 NPC 保存；每次派单前，NPC 都应该先读自己的固定能力包和项目必读需求表。⇪ 标记的能力包来自所在工位继承（去工位设置改）。</p>
          </article>
          {npcSeats.length ? (
            npcSeats.map((seat) => {
              const inheritedSet = new Set((seat.inheritedSkills ?? []).filter(Boolean));
              return (
              <form key={seat.id} action={updateNpcWorkstationSeat.bind(null, project.id, seat.id)} className={styles.inlineActionForm}>
                {renderNpcSeatHiddenFields(seat, "npc-create", { includeSkillLoadout: false, returnActionId: "npc-skills" })}
                <input type="hidden" name="source_workstation_id" value={seat.sourceWorkstationId || ""} />
                <input type="hidden" name="computer_node_id" value={seat.computerNodeId || ""} />
                <input type="hidden" name="automation_enabled" value={seat.automationEnabled ? "true" : "false"} />
                <input type="hidden" name="automation_heartbeat_seconds" value={String(seat.automationHeartbeatSeconds ?? 900)} />
                <div className={styles.skillChecklist}>
                  <b>{itemTitle(seat)} 已装配能力包 {inheritedSet.size ? `· 工位继承 ${inheritedSet.size}` : ""}</b>
                  {skills.length ? (
                    skills.map((skill) => {
                      const isInherited = inheritedSet.has(skill.id);
                      const ownChecked = (seat.skillLoadout ?? []).includes(skill.id);
                      return (
                        <label key={skill.id} className={styles.skillOption} style={isInherited ? { opacity: 0.85 } : undefined}>
                          {isInherited ? (
                            <input type="checkbox" checked readOnly disabled title="本能力包由工位继承注入，不会写进 NPC；要改请去工位设置" />
                          ) : (
                            <input type="checkbox" name="skill_loadout" value={skill.id} defaultChecked={ownChecked} />
                          )}
                          <span>{isInherited ? "⇪ " : ""}{itemTitle(skill)}{isInherited ? "（工位继承）" : ""}</span>
                          <small>{skill.body || skill.type || "项目能力仓库条目"}</small>
                        </label>
                      );
                    })
                  ) : (
                    <p className={styles.emptyHint}>能力仓库暂无条目。先去能力仓库添加或从 GitHub 导入。</p>
                  )}
                </div>
                <SubmitButton label="保存能力包装配" disabled={!skills.length} />
              </form>
              );
            })
          ) : (
            <p className={styles.emptyHint}>还没有 NPC。先创建 NPC，再到能力工坊配置能力。</p>
          )}
        </div>
      );
    }

    if (moduleTab === "npc-create" && action.id === "npc-dialogue") {
      return (
        <>
          <div className={styles.npcHandoffBar}>
            <span>切换线程时，把这个 NPC 的知识、Skill、任务进展打包给新 AI：</span>
            <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ opacity: 0.7, fontSize: 12 }}>关联任务</span>
              <select
                value={handoffTaskId}
                onChange={(e) => setHandoffTaskId(e.target.value)}
                style={{ minWidth: 160 }}
              >
                <option value="">请选择当前线程在做的任务</option>
                {tasks.map((t) => (
                  <option key={t.id} value={t.id}>
                    {(t.title || t.name || t.id).slice(0, 40)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className={styles.cockpitPrimary}
              onClick={async () => {
                const targetId = focusedNpcSeat?.id;
                if (!targetId) {
                  setCopyState({ kind: "err", message: "请先选中一个 NPC" });
                  setTimeout(() => setCopyState({ kind: "idle" }), 3000);
                  return;
                }
                if (!handoffTaskId) {
                  setCopyState({ kind: "err", message: "请先选择关联任务（用于落库 Handoff 记录）" });
                  setTimeout(() => setCopyState({ kind: "idle" }), 4000);
                  return;
                }
                setCopyState({ kind: "loading" });
                try {
                  // 先落库 Handoff，再拉 context —— 这样新拉的 prompt 里
                  // recent_handoffs 会包含这次刚写的记录，确保每次结果是最新的。
                  let recordedId: string | null = null;
                  try {
                    const recorded = await recordNpcHandoff(project.id, targetId, { task_id: handoffTaskId });
                    recordedId = String(recorded?.handoff?.id || "") || null;
                  } catch (err) {
                    setCopyState({
                      kind: "err",
                      message: `Handoff 落库失败：${err instanceof Error ? err.message : "未知错误"}`,
                    });
                    setTimeout(() => setCopyState({ kind: "idle" }), 5000);
                    return;
                  }
                  const data = await fetchNpcHandoffContext(project.id, targetId);
                  const prompt = String(data?.prompt ?? "").trim();
                  if (!prompt) throw new Error("接手 prompt 为空");
                  let copiedToClipboard = true;
                  try {
                    await writeClipboardText(prompt);
                    setManualCopy(null);
                  } catch {
                    copiedToClipboard = false;
                    setManualCopy({ label: `${focusedNpcSeat?.name || "NPC"} 接手提示词`, value: prompt });
                  }
                  setHandoffPreview({
                    npcName: focusedNpcSeat?.name || "NPC",
                    prompt,
                    at: new Date().toLocaleTimeString(),
                  });
                  setCopyState({
                    kind: "ok",
                    message: recordedId
                      ? `${copiedToClipboard ? "已复制" : "已展开"}并登记接手记录（Handoff ${recordedId.slice(0, 8)}…），下面预览即接手内容。`
                      : `${copiedToClipboard ? "已复制" : "已展开"} ${focusedNpcSeat?.name || "NPC"} 的接手 prompt，下面预览即接手内容。`,
                  });
                  setTimeout(() => setCopyState({ kind: "idle" }), 5000);
                } catch (e) {
                  setCopyState({ kind: "err", message: `复制失败：${e instanceof Error ? e.message : "未知错误"}` });
                  setTimeout(() => setCopyState({ kind: "idle" }), 4000);
                }
              }}
              disabled={copyState.kind === "loading"}
            >
              {copyState.kind === "loading" ? "生成中..." : `复制 ${focusedNpcSeat?.name || "NPC"} 的接手 prompt`}
            </button>
            {focusedNpcSeat?.skillLoadout?.length ? (
              <small>
                已装备 Skill：{focusedNpcSeat.skillLoadout.slice(0, 4).join("、")}{focusedNpcSeat.skillLoadout.length > 4 ? `…等 ${focusedNpcSeat.skillLoadout.length} 个` : ""}
              </small>
            ) : null}
            {focusedNpcSeat?.knowledgeSummary ? (
              <small>知识库：{focusedNpcSeat.knowledgeSummary.slice(0, 60)}{focusedNpcSeat.knowledgeSummary.length > 60 ? "…" : ""}</small>
            ) : null}
          </div>
          {copyState.message ? (
            <div className={`${styles.cockpitToast} ${copyState.kind === "err" ? styles.cockpitToastErr : styles.cockpitToastOk}`}>
              {copyState.message}
            </div>
          ) : null}
          {handoffPreview ? (
            <details
              style={{
                margin: "6px 0",
                padding: "8px 10px",
                border: "1px solid rgba(94, 240, 255, 0.32)",
                borderRadius: 10,
                background: "rgba(2, 13, 20, 0.66)",
              }}
              data-handoff-preview-npc={handoffPreview.npcName}
            >
              <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                展开查看 {handoffPreview.npcName} 的 prompt 预览（{handoffPreview.at} 拉取，已在剪贴板）
              </summary>
              <textarea
                readOnly
                value={handoffPreview.prompt}
                rows={12}
                style={{
                  width: "100%",
                  marginTop: 6,
                  fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                  fontSize: 11,
                  background: "rgba(0,0,0,0.35)",
                  color: "#f6edd8",
                  border: "1px solid rgba(246,237,216,0.12)",
                  borderRadius: 8,
                  padding: "8px 10px",
                  resize: "vertical",
                }}
              />
            </details>
          ) : null}
          <form action={submitCollaborationMessage} className={styles.drawerForm} data-unity-real-form="npc-dialogue">
          <input type="hidden" name="project_id" value={project.id} />
          <input type="hidden" name="return_to" value={returnPath("npc-create", "npc-dialogue")} />
          <input type="hidden" name="message_type" value="agent_command" />
          <input type="hidden" name="recipient_type" value="workstation" />
          <label>
            <span>目标 NPC / 线程</span>
            <select name="recipient_id" defaultValue={focusedNpcSeat?.id ?? firstWorkstation?.id ?? ""} required>
              <option value="">请选择一个 NPC 或线程</option>
              {collaborationTargets.map((item) => (
                <option key={item.id} value={item.id}>
                  {collaborationTargetLabel(item)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>标题</span>
            <input name="title" required placeholder="例如：只读检查项目工作台入口" />
          </label>
          <label>
            <span>指令正文</span>
            <textarea name="body" required rows={6} placeholder="写清楚目标、边界、是否只读、预期已收到提醒和最终回复格式。" />
          </label>
          <SubmitButton label="发送给目标 NPC/线程" disabled={!collaborationTargets.length} />
        </form>
        </>
      );
    }

    if (moduleTab === "computers" && action.id === "pairing-token") {
      const connectCommand = pairingResult
        ? (() => {
            const node = { id: pairingResult.nodeId, label: pairingResult.nodeId };
            return buildComputerOneClickConnectCommand(
              webBaseUrl,
              project.id,
              node,
              pairingResult.token,
              suggestedComputerRunnerId(node),
              { serverUrl: apiBaseUrl, watch: true, hardwareAccess: true },
            );
          })()
        : "";
      return (
        <div className={styles.realActionStack} data-unity-real-form="computer-pairing">
          {pairingResult ? (
            <article className={styles.resultCard} data-token-result-card="computer-pairing">
              <span>配对令牌已生成</span>
              <b>{pairingResult.nodeId}</b>
              <p>不用刷新页面。把下面命令发到目标电脑运行；如果目标电脑没有仓库文件，也会从平台下载接入脚本。用户自己在目标电脑终端运行不需要确认，后续 NPC 代操作才需要人工确认。</p>
              <code data-token-copy-token="computer-pairing">{pairingResult.token}</code>
              <strong className={styles.commandLabel}>Windows PowerShell 一键接入</strong>
              <textarea readOnly rows={5} value={connectCommand} aria-label="电脑接入命令" data-token-command="computer-pairing" />
              <strong className={styles.commandLabel}>Linux / macOS Bash 一键接入</strong>
              <textarea
                readOnly
                rows={5}
                value={buildComputerOneClickConnectBashCommand(
                  webBaseUrl,
                  project.id,
                  { id: pairingResult.nodeId, label: pairingResult.nodeId },
                  pairingResult.token,
                  suggestedComputerRunnerId({ id: pairingResult.nodeId, label: pairingResult.nodeId }),
                  { serverUrl: apiBaseUrl, watch: true, hardwareAccess: true },
                )}
                aria-label="Linux 电脑接入命令"
                data-token-command="computer-pairing-linux"
              />
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <button
                  type="button"
                  onClick={() => copyTextToClipboard(pairingResult.token, "令牌已复制到剪贴板")}
                  data-token-copy-token-btn="computer-pairing"
                >
                  复制令牌
                </button>
                <button
                  type="button"
                  onClick={() => copyTextToClipboard(connectCommand, "接入命令已复制，可粘贴到目标电脑 PowerShell 运行")}
                  data-token-copy-command-btn="computer-pairing"
                >
                  复制 Windows 命令
                </button>
                <button
                  type="button"
                  onClick={() => copyTextToClipboard(
                    buildComputerOneClickConnectBashCommand(
                      webBaseUrl,
                      project.id,
                      { id: pairingResult.nodeId, label: pairingResult.nodeId },
                      pairingResult.token,
                      suggestedComputerRunnerId({ id: pairingResult.nodeId, label: pairingResult.nodeId }),
                      { serverUrl: apiBaseUrl, watch: true, hardwareAccess: true },
                    ),
                    "Linux 命令已复制，可粘贴到目标电脑 Bash 运行",
                  )}
                  data-token-copy-command-btn="computer-pairing-linux"
                >
                  复制 Linux 命令
                </button>
                {copyState.kind !== "idle" && copyState.message ? (
                  <small data-token-copy-status={copyState.kind}>{copyState.message}</small>
                ) : null}
              </div>
            </article>
          ) : null}
          <form action={createCollaborationNode.bind(null, project.id)} className={styles.drawerForm}>
            <input type="hidden" name="return_to" value={returnPath("computers", "pairing-token")} />
            <label>
              <span>新电脑 ID</span>
              <input name="id" placeholder="例如：office-pc-01" />
            </label>
            <label>
              <span>显示名</span>
              <input name="label" required placeholder="例如：办公室电脑 01" />
            </label>
            <SubmitButton label="先登记电脑" />
          </form>
          <div className={styles.realDivider}>已有电脑配对令牌</div>
          {computers.length ? (
            computers.map((computer) => (
              <form key={computer.id} action={issueComputerNodePairingToken.bind(null, project.id, computer.id)} className={styles.inlineActionForm}>
                <input type="hidden" name="return_to" value={returnPath("computers", "pairing-token")} />
                <span>{itemTitle(computer)} / {statusLabel(computer.status)}</span>
                <SubmitButton label="生成令牌" />
              </form>
            ))
          ) : (
            <p className={styles.emptyHint}>先登记一台电脑，再生成配对令牌。</p>
          )}
        </div>
      );
    }

    if (moduleTab === "computers" && action.id === "scan-threads") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="computer-thread-scan">
          {computers.length ? (
            computers.map((computer) => (
              <form key={computer.id} action={requestComputerThreadScan.bind(null, project.id)} className={styles.inlineActionForm}>
                <input type="hidden" name="return_to" value={returnPath("machine-room", "thread-list")} />
                <input type="hidden" name="computer_node_id" value={computer.id} />
                <span>{itemTitle(computer)} / {statusLabel(computer.status)}</span>
                <SubmitButton label="扫描线程" />
              </form>
            ))
          ) : (
            <p className={styles.emptyHint}>还没有电脑。先登记电脑并完成执行接入。</p>
          )}
        </div>
      );
    }

    if (moduleTab === "computers" && action.id === "runner-health") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="runner-health">
          <article className={styles.realNote}>
            <b>执行电脑健康要看“电脑在线 + 心跳 + 线程数”</b>
            <p>电脑在线但扫不到线程时，不要直接派单；先让用户打开对应 AI 工具，再重新扫描线程。</p>
          </article>
          <article className={styles.reconnectChecklist} aria-label="电脑重连三步">
            <span>掉线重连三步</span>
            <ol>
              <li><b>复制持续接单命令</b><small>选择目标电脑，按系统复制 Windows 或 Linux 命令。</small></li>
              <li><b>保持终端或启用守护</b><small>临时调试用前台持续接单；长期电脑启用后台守护。</small></li>
              <li><b>回平台确认状态</b><small>看到“常驻接单”后再扫描线程、绑定 NPC、派任务。</small></li>
            </ol>
          </article>
          <div className={styles.layeredList}>
            {computers.length ? (
              computers.map((computer) => {
                const runnerId = computer.runnerId || computer.providerId || suggestedComputerRunnerId(computer);
                const watchCommand = buildComputerRunnerWatchCommand(apiBaseUrl, project.id, computer, runnerId, { pollSeconds: 30 });
                const watchBashCommand = buildComputerRunnerWatchBashCommand(apiBaseUrl, project.id, computer, runnerId, { pollSeconds: 30 });
                const serviceCommand = buildComputerRunnerWatchServiceCommand(apiBaseUrl, project.id, computer, runnerId, { pollSeconds: 30 });
                const serviceBashCommand = buildComputerRunnerWatchServiceBashCommand(apiBaseUrl, project.id, computer, runnerId, { pollSeconds: 30 });
                return (
                  <article key={computer.id} className={styles.layeredItem}>
                    <span>{runnerDispatchLabel(computer)}</span>
                    <b>{itemTitle(computer)}</b>
                    <small>{computer.providerId || runnerId} / {computerThreadCount(computer, workstations)} 条线程 / 最近心跳：{computer.at || "暂无"}</small>
                    <p>{runnerReconnectHint(computer, workstations)}</p>
                    <p>{computerDesktopCapabilityLabel(computer)}：{computerDesktopCapabilityHint(computer)}</p>
                    <details className={styles.itemDetails} open={!isRunnerOnlineStatus(computer)}>
                      <summary>持续接单 / 重连命令</summary>
                      <div className={styles.reconnectCommandGrid}>
                        <label>
                          <span>Windows PowerShell 前台持续接单</span>
                          <textarea readOnly rows={4} value={watchCommand} aria-label={`${itemTitle(computer)} Windows 持续接单命令`} />
                          <button type="button" onClick={() => copyTextToClipboard(watchCommand, `${itemTitle(computer)} Windows 持续接单命令已复制`)}>
                            复制 Windows 前台命令
                          </button>
                        </label>
                        <label>
                          <span>Linux / macOS Bash 前台持续接单</span>
                          <textarea readOnly rows={4} value={watchBashCommand} aria-label={`${itemTitle(computer)} Linux 持续接单命令`} />
                          <button type="button" onClick={() => copyTextToClipboard(watchBashCommand, `${itemTitle(computer)} Linux 持续接单命令已复制`)}>
                            复制 Linux 前台命令
                          </button>
                        </label>
                        <label>
                          <span>Windows 后台守护</span>
                          <textarea readOnly rows={4} value={serviceCommand} aria-label={`${itemTitle(computer)} Windows 后台守护命令`} />
                          <button type="button" onClick={() => copyTextToClipboard(serviceCommand, `${itemTitle(computer)} Windows 后台守护命令已复制`)}>
                            复制 Windows 守护命令
                          </button>
                        </label>
                        <label>
                          <span>Linux 后台守护</span>
                          <textarea readOnly rows={4} value={serviceBashCommand} aria-label={`${itemTitle(computer)} Linux 后台守护命令`} />
                          <button type="button" onClick={() => copyTextToClipboard(serviceBashCommand, `${itemTitle(computer)} Linux 后台守护命令已复制`)}>
                            复制 Linux 守护命令
                          </button>
                        </label>
                      </div>
                      {copyState.kind !== "idle" && copyState.message ? (
                        <p className={copyState.kind === "err" ? styles.watcherCopyErr : styles.watcherCopyOk}>{copyState.message}</p>
                      ) : null}
                      <dl>
                        <div><dt>用户动作</dt><dd>{computerUserHint(computer, workstations)}</dd></div>
                        <div><dt>派单判断</dt><dd>{isRunnerOnlineStatus(computer) ? "可接单；仍需确认线程已绑定到目标 NPC。" : "不可假装成功；新任务只允许排队等待恢复或改派。"}</dd></div>
                        <div><dt>协作边界</dt><dd>用户自己在终端输入不需要确认；NPC 代操作终端必须先生成待确认请求。</dd></div>
                      </dl>
                    </details>
                  </article>
                );
              })
            ) : (
              <article className={styles.layeredItem}>
                <span>空状态</span>
                <b>暂无电脑状态</b>
                <p>先到“生成配对令牌”登记电脑，再让目标电脑运行执行接入命令。</p>
              </article>
            )}
          </div>
        </div>
      );
    }

    if (moduleTab === "exchange" && action.id === "dispatch-command") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="exchange-audit">
          <article className={styles.realNote}>
            <b>NPC 协作现在只做审计和索引</b>
            <p>为了不让主页面和 NPC 工作台重复，正式对话、人工确认、启动真实处理都回到 NPC 工作台瓷砖里完成。</p>
          </article>
          <Link
            href={`/projects/${encodeURIComponent(project.id)}/workbench?return_to=${encodeURIComponent(returnPath("exchange", "dispatch-command"))}`}
            className={styles.primaryPanelLink}
          >
            去 NPC 工作台对话
          </Link>
          <div className={styles.layeredList}>
            {dispatchMessages.length ? (
              dispatchMessages.slice(0, 10).map((message) => (
                <article key={message.id} className={styles.layeredItem}>
                  <span>{message.type || "协作请求"}</span>
                  <b>{itemTitle(message)}</b>
                  <small>{statusLabel(message.status)} / {message.at || "暂无时间"}</small>
                  <p>{itemBody(message)}</p>
                </article>
              ))
            ) : (
              <article className={styles.layeredItem}>
                <span>空状态</span>
                <b>暂无协作记录</b>
                <p>去 NPC 工作台给某个 NPC 发消息，平台会把用户指令、NPC 间消息、人工确认和回执沉淀到这里。</p>
              </article>
            )}
          </div>
        </div>
      );
    }

    if (moduleTab === "exchange" && action.id === "final-pool") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="final-reply-pool">
          <article className={styles.realNote}>
            <b>只收口最终结果，不把过程噪声堆首页</b>
            <p>这里按“最终回复 / 状态 / 摘要”显示，并继续展示来源、下一步和噪声规则。</p>
          </article>
          <div className={styles.layeredList}>
            {finalMessages.length ? (
              finalMessages.slice(0, 10).map((message, index) => (
                <article key={message.id} className={styles.layeredItem}>
                  <span>{message.type || "最终回复"}</span>
                  <b>{itemTitle(message)}</b>
                  <small>{statusLabel(message.status)} / {message.at || "暂无时间"}</small>
                  <p>{itemBody(message)}</p>
                  <details className={styles.itemDetails}>
                    <summary>查看收口详情</summary>
                    <dl>
                      <div><dt>来源</dt><dd>{message.sourceWorkstationId || message.providerLabel || `项目事件 #${index + 1}`}</dd></div>
                      <div><dt>下一步</dt><dd>若结果可用，回到“当前推荐动作”；若缺材料，写入“必读需求表”。</dd></div>
                      <div><dt>噪声规则</dt><dd>过程日志不进首页，只保留最终回复、阻塞原因和需要人工确认的动作。</dd></div>
                    </dl>
                  </details>
                </article>
              ))
            ) : (
              <article className={styles.layeredItem}>
                <span>空状态</span>
                <b>暂无最终回复</b>
                <p>先从“下发协作指令”派给某个 NPC/线程，收到最终回复后只把收口结果放这里。</p>
              </article>
            )}
          </div>
        </div>
      );
    }

    if (moduleTab === "exchange" && action.id === "required-ledger") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="required-ledger">
          <article className={styles.realNote}>
            <b>AI 做任务前必须先读这一层</b>
            <p>需求表按提需求者、被提需求者、边界、验收点组织；AI 不清楚时必须先请求人工确认，而不是盲目继续烧 token。</p>
          </article>
          <div className={styles.layeredList}>
            {requirements.slice(0, 8).map((requirement) => (
              <article key={requirement.id} className={styles.layeredItem}>
                <span>项目需求</span>
                <b>{itemTitle(requirement)}</b>
                <small>{statusLabel(requirement.status)} / 提给：待分配 NPC</small>
                <p>{itemBody(requirement)}</p>
                <details className={styles.itemDetails}>
                  <summary>查看 AI 必读边界</summary>
                  <dl>
                    <div><dt>提需求者</dt><dd>当前项目成员或上游 AI</dd></div>
                    <div><dt>被提需求者</dt><dd>待在 NPC 工作台或公司层指定 NPC / 工位</dd></div>
                    <div><dt>验收</dt><dd>完成后必须回到提需求者，并把最终回复写入最终回复池。</dd></div>
                  </dl>
                </details>
              </article>
            ))}
            {messages.slice(0, 5).map((message) => (
              <article key={`message-${message.id}`} className={styles.layeredItem}>
                <span>{message.type || "项目事件"}</span>
                <b>{itemTitle(message)}</b>
                <small>{statusLabel(message.status)} / 完成后回到提需求者</small>
                <p>{itemBody(message)}</p>
                <details className={styles.itemDetails}>
                  <summary>查看协作规则</summary>
                  <dl>
                    <div><dt>读前置需求</dt><dd>AI 接单前先看需求表，不清楚就请求人工确认。</dd></div>
                    <div><dt>token 边界</dt><dd>未开启 NPC 自动化时只执行当前指令，不连续自循环。</dd></div>
                    <div><dt>回写</dt><dd>先给已收到提醒，最终结果只写最终回复池。</dd></div>
                  </dl>
                </details>
              </article>
            ))}
            {!requirements.length && !messages.length ? (
              <article className={styles.layeredItem}>
                <span>空状态</span>
                <b>暂无必读需求</b>
                <p>当人或 AI 发起需求时，平台会把目标、边界和验收写进这里，避免十几个线程各自乱跑。</p>
              </article>
            ) : null}
          </div>
        </div>
      );
    }

    if (moduleTab === "skills" && action.id === "github-import") {
      return (
        <div className={styles.realActionStack}>
          <section className={styles.githubImportGuide} aria-label="GitHub Skill 导入规则">
            <b>可以从 GitHub 导入 Skill</b>
            <p>当前支持公开仓库的 repo、tree、blob 或 raw 地址。平台会识别 SKILL.md、skill.json、skills.json、skills/ 目录，也能把普通角色 Markdown 转成 Skill 草稿。</p>
            <dl>
              <div><dt>推荐结构</dt><dd>skills/project-boss/SKILL.md</dd></div>
              <div><dt>知识库路径</dt><dd>写 GitHub 仓库相对路径，不写本机 D:\ 目录</dd></div>
              <div><dt>私有仓库</dt><dd>暂不读取私有仓库；后续接 GitHub App、OAuth 或执行电脑凭据</dd></div>
            </dl>
          </section>
          <form
            action={`/projects/${encodeURIComponent(project.id)}/github-skill`}
            method="post"
            className={styles.drawerForm}
            data-unity-real-form="skill-github-import"
            onSubmit={submitGithubSkillImport}
          >
            <input type="hidden" name="return_to" value={returnPath("skills", "github-import")} />
            <label>
              <span>GitHub 地址</span>
              <input name="github_url" required placeholder="repo / tree / blob / raw 地址，例如：https://github.com/org/repo/tree/main/skills" />
            </label>
            <label>
              <span>子路径，可选</span>
              <input name="github_path" placeholder="例如：skills/web-research" />
            </label>
            <label>
              <span>分支，可选</span>
              <input name="github_branch" placeholder="例如：main" />
            </label>
            <label>
              <span>分类</span>
              <input name="category" defaultValue="github" />
            </label>
            <label>
              <span>适用职业，逗号分隔</span>
              <input name="recommended_for" placeholder="例如：前端工程师, 嵌入式工程师, 测试工程师" />
            </label>
            <SubmitButton label="从 GitHub 导入 Skill" disabled={githubSkillImporting} pendingLabel="导入中..." />
          </form>
        </div>
      );
    }

    if (moduleTab === "skills" && (action.id === "skill-category" || action.id === "skill-detail")) {
      const existingSkillIds = new Set(skills.map((skill) => String(skill.id ?? "").trim().toLowerCase()).filter(Boolean));
      const allRecommendedCreated = PLATFORM_RECOMMENDED_SKILLS.every((skill) => existingSkillIds.has(skill.id));
      return (
        <div className={styles.realActionStack} data-unity-real-form="skill-create-custom">
          <section className={styles.recommendedSkillStack} aria-label="平台推荐能力包">
            <div className={styles.realNote}>
              <b>平台推荐能力包</b>
              <p>先把 Boss、后端、前端、QA 和跨工位路由的基础能力包建起来，后面 NPC 装配时直接索引仓库。</p>
            </div>
            <article className={styles.panelCard}>
              <span>GitHub 知识库索引</span>
              <strong>{knowledgeDocuments.length} 份正式文档</strong>
              <p>这里显示平台正式登记的仓库相对路径、存在状态、版本和同步时间；不要写本机 D:\ 路径。</p>
              {renderKnowledgeDocumentList(knowledgeDocuments, "暂无正式知识库文档，先登记 GitHub 仓库相对路径。")}
            </article>
            {PLATFORM_RECOMMENDED_SKILLS.map((skill) => {
              const created = existingSkillIds.has(skill.id);
              return (
                <article
                  key={skill.id}
                  className={`${styles.recommendedSkillItem} ${created ? styles.recommendedSkillItemReady : ""}`}
                >
                  <b>{skill.label}</b>
                  <small>{skill.note}</small>
                  <small>推荐：{skill.recommendedFor.join("、")}</small>
                  <span>{created ? "已创建" : "待创建"}</span>
                  <form
                    action={`/projects/${encodeURIComponent(project.id)}/recommended-skill`}
                    method="post"
                    className={styles.recommendedSkillCreateForm}
                  >
                    <input type="hidden" name="return_to" value={returnPath("skills", action.id)} />
                    <input type="hidden" name="skill_id" value={skill.id} />
                    <button type="submit" disabled={created}>{created ? "已创建" : "创建这个能力包"}</button>
                  </form>
                </article>
              );
            })}
            <div
              className={styles.inlineActionForm}
              data-unity-real-form="skill-create-recommended"
            >
              <label>
                <span>选择一个推荐能力包</span>
                <select
                  name="skill_id"
                  required
                  value={selectedRecommendedSkillId}
                  onChange={(event) => setSelectedRecommendedSkillId(event.currentTarget.value)}
                >
                  <option value="" disabled>选择后创建</option>
                  {PLATFORM_RECOMMENDED_SKILLS.map((skill) => {
                    const created = existingSkillIds.has(skill.id);
                    return (
                      <option key={skill.id} value={skill.id} disabled={created}>
                        {created ? "已创建 / " : ""}{skill.label}
                      </option>
                    );
                  })}
                </select>
              </label>
              <p className={styles.emptyHint}>选择后平台会自动带入标识、说明和推荐角色。</p>
              {recommendedSkillNotice ? <p className={styles.emptyHint}>{recommendedSkillNotice}</p> : null}
              <button
                type="button"
                disabled={allRecommendedCreated || Boolean(recommendedSkillSavingId) || !selectedRecommendedSkillId}
                aria-busy={Boolean(recommendedSkillSavingId)}
                onClick={() => void createRecommendedSkill(selectedRecommendedSkillId)}
              >
                {recommendedSkillSavingId ? "创建中..." : allRecommendedCreated ? "推荐能力包已齐" : "创建所选推荐能力包"}
              </button>
            </div>
          </section>

          <form action={createProjectSkill.bind(null, project.id)} className={styles.drawerForm}>
            <input type="hidden" name="return_to" value={returnPath("skills", action.id)} />
            <label>
              <span>能力包标识</span>
              <input name="skill_id" required placeholder="例如：workbench-ui-screenshot-qa" />
            </label>
            <label>
              <span>中文名字</span>
              <input name="label" required placeholder="例如：Unity UI 截图验收" />
            </label>
            <label>
              <span>中文说明</span>
              <textarea name="note" required rows={6} placeholder="具体说明用途、触发条件、输入输出、截图验证要求、人工确认边界和 token 风险。" />
            </label>
            <label>
              <span>推荐给哪些职业，逗号分隔</span>
              <input name="recommended_for" placeholder="例如：Unity UI 工程师, 前端工程师" />
            </label>
            <SubmitButton label="新增项目 Skill" />
          </form>

          <section className={styles.npcAuthoredSkillPanel} aria-label="NPC 自造 Skill">
            <div className={styles.realNote}>
              <b>NPC 自造 Skill</b>
              <p>当某个 NPC 在开发中形成稳定做法，把它沉淀成项目 Skill 草稿。完整处理仍在已绑定的 AI 开发线程里，平台只保存可复用的角色能力索引。</p>
            </div>
            <dl>
              <div><dt>必备文件</dt><dd>skills/&lt;skill-id&gt;/SKILL.md</dd></div>
              <div><dt>推荐附加</dt><dd>agents/openai.yaml、references/、scripts/、assets/</dd></div>
              <div><dt>沉淀边界</dt><dd>只写长期有效的触发条件、流程、验收和禁区，不保存一次性聊天过程。</dd></div>
            </dl>
            <form action={createProjectSkill.bind(null, project.id)} className={styles.drawerForm}>
              <input type="hidden" name="return_to" value={returnPath("skills", action.id)} />
              <input type="hidden" name="source" value="npc-authored" />
              <input type="hidden" name="category" value="npc-authored" />
              <input type="hidden" name="draft_status" value="draft" />
              <label>
                <span>作者 NPC</span>
                <select name="author_seat_id" required>
                  <option value="" disabled>选择沉淀这个 Skill 的 NPC</option>
                  {npcSeats.map((seat) => (
                    <option key={seat.id} value={seat.id}>{itemTitle(seat)}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Skill 标识</span>
                <input name="skill_id" required placeholder="例如：workbench-review-checklist" />
              </label>
              <label>
                <span>Skill 名字</span>
                <input name="label" required placeholder="例如：教师进度页验收" />
              </label>
              <label>
                <span>仓库相对路径</span>
                <input name="repo_relative_path" placeholder="默认：skills/<skill-id>/SKILL.md" />
              </label>
              <label>
                <span>草稿内容</span>
                <textarea
                  name="note"
                  required
                  rows={7}
                  placeholder="写这个 NPC 以后什么时候触发、先读哪些仓库相对路径、执行步骤、需要哪些真实前端验证、哪些动作必须人工确认。"
                />
              </label>
              <label>
                <span>推荐给哪些职业，逗号分隔</span>
                <input name="recommended_for" placeholder="例如：前端小程序 NPC, QA 验收 NPC" />
              </label>
              <label className={styles.inlineCheck}>
                <input type="checkbox" name="assign_to_author" value="true" defaultChecked />
                <span>创建后先挂到作者 NPC，保持草稿状态</span>
              </label>
              <SubmitButton label="沉淀为 Skill 草稿" disabled={!npcSeats.length} />
            </form>
          </section>

          <section className={styles.npcAuthoredSkillPanel} aria-label="NPC 自造 Skill 草稿治理">
            <div className={styles.realNote}>
              <b>草稿治理</b>
              <p>草稿先保留为 NPC 的候选能力；确认稳定后启用，后续派单才把它当作长期角色特性使用。</p>
            </div>
            {skills.filter((skill) => skill.source === "npc-authored").length ? (
              <ul className={styles.skillLifecycleList}>
                {skills.filter((skill) => skill.source === "npc-authored").map((skill) => {
                  const isDraft = String(skill.draftStatus || skill.status).toLowerCase() === "draft";
                  return (
                    <li key={`npc-authored-${skill.id}`} data-source={skill.source} data-draft={skill.draftStatus || skill.status}>
                      <div>
                        <b>{itemTitle(skill)}</b>
                        <small>{skillLifecycleLabel(skill)} / {skill.repoRelativePath || "未登记仓库相对路径"}</small>
                        <small>{shortCopy(itemBody(skill), "暂无说明", 110)}</small>
                      </div>
                      <form action={启用Npc自造Skill.bind(null, project.id, skill.skillId || skill.id)}>
                        <input type="hidden" name="return_to" value={returnPath("skills", action.id)} />
                        <button type="submit" disabled={!isDraft} aria-label={`${isDraft ? "确认可用" : "已启用"}：${itemTitle(skill)}`}>
                          {isDraft ? "确认可用" : "已启用"}
                        </button>
                      </form>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className={styles.emptyHint}>当前还没有 NPC 自造 Skill 草稿。先让 Boss、前端或 QA NPC 在开发中沉淀一条。</p>
            )}
          </section>
        </div>
      );
    }

    if (moduleTab === "machine-room") {
      if (action.id === "thread-list") {
        const unassignedThreads = workstations.filter((thread) => !thread.computerNodeId);
        const groupedComputers = computers.map((computer) => ({
          computer,
          threads: workstations.filter((thread) => thread.computerNodeId === computer.id),
        }));
        const visibleGroups = [
          ...groupedComputers,
          ...(unassignedThreads.length
            ? [{
                computer: { id: "unassigned", name: "未识别电脑", status: "needs_binding" } as FeedItem,
                threads: unassignedThreads,
              }]
            : []),
        ];
        return (
          <div className={styles.realActionStack} data-unity-real-form="machine-room-thread-list">
            <article className={styles.realNote}>
              <b>按电脑分组看真实线程，先解决“扫到很多但只显示一部分”</b>
              <p>当前前端最多展示 48 条线程。线程没有电脑归属时会落到“未识别电脑”，方便用户继续绑定或重新扫描。</p>
            </article>
            <div className={styles.threadGroupList}>
              {visibleGroups.length ? (
                visibleGroups.map((group) => (
                  <article key={group.computer.id} className={styles.threadGroup}>
                    <header>
                      <b>{itemTitle(group.computer)}</b>
                      <span>{statusLabel(group.computer.status)} / {group.threads.length} 条线程</span>
                    </header>
                    {group.threads.length ? (
                      <ul>
                        {group.threads.map((thread, threadIndex) => (
                          <li key={thread.id}>
                            <strong>{safeThreadName(thread, threadIndex)}</strong>
                            <small>
                              {thread.type || "thread"} / {statusLabel(thread.status)}
                              {thread.model ? ` / ${thread.model}` : ""}
                            </small>
                            <p>{threadUserHint(thread)}</p>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className={styles.emptyHint}>这台电脑暂无线程。先打开对应 AI 工具，再回到电脑接入里扫描。</p>
                    )}
                  </article>
                ))
              ) : (
                <p className={styles.emptyHint}>暂无线程。先接入电脑、注册执行程序，再扫描 Codex / Claude / Qwen 线程。</p>
              )}
            </div>
          </div>
        );
      }

      if (action.id === "online-check") {
        return (
          <div className={styles.realActionStack} data-unity-real-form="machine-room-online-check">
            <article className={styles.realNote}>
              <b>在线不是一个状态，而是四层检查</b>
              <p>商用时要同时看：电脑是否登记、执行程序是否持续接单、账号是否进入项目、线程是否可用。任何一层断了，都要告诉用户下一步做什么。</p>
            </article>
            <div className={styles.onlineCheckGrid}>
              <span><b>{computers.length}</b>已登记电脑</span>
              <span><b>{stats.onlineComputerCount}</b>台常驻接单</span>
              <span><b>{workstations.length}</b>可见线程</span>
              <span><b>{npcSeats.length}</b>已绑定 NPC</span>
            </div>
            <div className={styles.layeredList}>
              {computers.length ? (
                computers.map((computer) => (
                  <article key={computer.id} className={styles.layeredItem}>
                    <span>{statusLabel(computer.status)}</span>
                    <b>{itemTitle(computer)}</b>
                    <small>{computerThreadCount(computer, workstations)} 条线程 / {computer.type || "执行程序"}</small>
                    <p>{computerUserHint(computer, workstations)}</p>
                    <p>{computerDesktopCapabilityLabel(computer)}</p>
                  </article>
                ))
              ) : (
                <article className={styles.layeredItem}>
                  <span>空状态</span>
                  <b>暂无电脑在线状态</b>
                  <p>先在电脑接入里生成配对令牌并运行执行接入命令。</p>
                </article>
              )}
            </div>
          </div>
        );
      }

      return (
        <div className={styles.realActionStack} data-unity-real-form={`machine-room-${action.id}`}>
          <article className={styles.realNote}>
            <b>{action.label}</b>
            <p>这里承接电脑线程调试：只读展示真实电脑、执行程序和线程状态。扫描与配对动作已放在“电脑接入”。</p>
          </article>
          <div className={styles.layeredList}>
            {messages.filter(isExecutionChannelMessage).slice(0, 8).map((message) => (
              <article key={message.id} className={styles.layeredItem}>
                <span>{message.type ? statusLabel(message.type) : "执行通道"}</span>
                <b>{itemTitle(message)}</b>
                <small>{statusLabel(message.status)} / {message.at || "暂无时间"}</small>
                <p>{itemBody(message)}</p>
              </article>
            ))}
            {!messages.filter(isExecutionChannelMessage).length ? (
              <article className={styles.layeredItem}>
                <span>空状态</span>
                <b>暂无执行通道摘要</b>
                <p>长日志不再堆到首页；这里只显示接单、扫描、心跳、失败原因和最终回写摘要。若电脑已接入但这里为空，请先在“电脑接入”重新扫描线程。</p>
              </article>
            ) : null}
          </div>
        </div>
      );
    }

    if (moduleTab === "git" && (action.id === "checkpoint" || action.id === "diff-preview")) {
      if (action.id === "checkpoint") {
        return (
          <div className={styles.realActionStack} data-unity-real-form="git-settings-binding">
            <form action={updateProjectGitSettings.bind(null, project.id)} className={styles.drawerForm}>
              <input type="hidden" name="return_to" value={returnPath("git", action.id)} />
              <label>
                <span>GitHub 仓库地址</span>
                <input name="github_url" placeholder="https://github.com/org/repo" />
              </label>
              <label>
                <span>本地 Git 地址，可选</span>
                <input name="local_git_url" placeholder="由每台电脑自己决定本地路径，这里只放远程/说明。" />
              </label>
              <label>
                <span>默认分支</span>
                <input name="default_branch" defaultValue="main" />
              </label>
              <label>
                <span>开发分支</span>
                <input name="develop_branch" defaultValue="develop" />
              </label>
              <SubmitButton label="保存 Git 配置" />
            </form>
            <form action={bindProjectGithubAccount.bind(null, project.id)} className={styles.drawerForm}>
              <input type="hidden" name="return_to" value={returnPath("git", action.id)} />
              <label>
                <span>GitHub 账号 / 组织</span>
                <input name="account_login" placeholder="例如：a-agent-studio" />
              </label>
              <label>
                <span>凭据来源</span>
                <select name="credential_source" defaultValue="runner_env">
                  <option value="runner_env">各电脑执行环境变量</option>
                  <option value="ssh_agent">各电脑 SSH Agent</option>
                  <option value="github_app">GitHub App</option>
                  <option value="manual_review">人工确认</option>
                </select>
              </label>
              <label>
                <span>凭据标识，不填明文 token</span>
                <input name="credential_ref" placeholder="例如：GITHUB_TOKEN" />
              </label>
              <SubmitButton label="绑定 GitHub 账号" />
            </form>
          </div>
        );
      }
      return (
        <div className={styles.realActionStack} data-unity-real-form="git-rollback-preview">
          {renderGitRollbackVersionIndex()}
          <form action={previewProjectGitRollback.bind(null, project.id)} className={styles.drawerForm}>
            <input type="hidden" name="return_to" value={returnPath("git", "rollback-request")} />
            <label>
              <span>目标版本</span>
              <input
                name="target_ref"
                required
                placeholder="例如：HEAD~1 或 develop"
                value={gitRollbackTargetRef}
                onChange={(event) => setGitRollbackTargetRef(event.target.value)}
              />
            </label>
            <label>
              <span>备注</span>
              <textarea name="notes" rows={4} placeholder="说明为什么要回退，先只做预演和只读预检。" />
            </label>
            <SubmitButton label="生成回退预演" />
          </form>
        </div>
      );
    }

    if (moduleTab === "git" && action.id === "rollback-request") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="git-rollback-request">
          {renderGitRollbackVersionIndex()}
          <article className={styles.realNote}>
            <b>登记后仍不直接回退</b>
            <p>平台会记录请求并下发只读预检。下一步必须把对齐请求同步给 Boss NPC、相关工位长和执行 NPC，让它们回执“已对齐 / 阻塞 / 需人工”。</p>
          </article>
          <form action={requestProjectGitRollback.bind(null, project.id)} className={styles.drawerForm}>
            <input type="hidden" name="return_to" value={returnPath("git", "rollback-request")} />
            <label>
              <span>目标版本</span>
              <input
                name="target_ref"
                required
                placeholder="例如：HEAD~1 或 develop"
                value={gitRollbackTargetRef}
                onChange={(event) => setGitRollbackTargetRef(event.target.value)}
              />
            </label>
            <label>
              <span>人工确认备注</span>
              <textarea name="notes" rows={4} placeholder="登记请求后仍会先下发只读预检，不直接执行破坏性 reset。" />
            </label>
            <SubmitButton label="登记回退请求" />
          </form>
        </div>
      );
    }

    return (
      <article className={styles.realNote}>
        <b>这一项已完成入口搬迁，真实表单下一批接线。</b>
        <p>当前先保证工作台入口不再依赖旧场景交互；下一轮继续把旧入口对应的服务动作搬进这个抽屉。</p>
      </article>
    );
  }

  function renderPanelContent(tab: ModuleTab) {
    if (tab === "development-workshop") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>工坊总览</span>
            <strong>主页面治理工位和工位长</strong>
            <p>同工位 NPC 互相认识；跨工位协作只走目标工位长。这里先把资源关系看清，再去工作台执行。</p>
            {renderMetricGrid()}
          </article>
          <article className={styles.panelCard}>
            <span>逻辑工位</span>
            {renderLogicalWorkstationSummary()}
          </article>
        </div>
      );
    }

    if (tab === "human-party") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>当前主角</span>
            <strong>{currentUser.name}</strong>
            <p>{currentUser.email || "未拿到邮箱"} / 这里承接项目负责人视角，只点击打开，不再长期挡住工作区。</p>
            {renderMetricGrid()}
          </article>
          <article className={styles.panelCard}>
            <span>项目成员</span>
            {renderList(projectMembers, "暂无项目成员数据。先确认当前账号是否已加入项目。")}
          </article>
        </div>
      );
    }

    if (tab === "npc-create") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>NPC 管理栏</span>
            <strong>创建、绑定、装配和对话都放这里</strong>
            <p>后续三级抽屉会包含 NPC 基础信息、职责、自动化开关、知识库、Skill 装配、绑定电脑/线程和对话框。</p>
          </article>
          <article className={styles.panelCard}>
            <span>最近任务</span>
            {renderList(tasks, "暂无任务，先从 NPC 工作台或公司层派发。")}
          </article>
        </div>
      );
    }

    if (tab === "computers") {
      const firstComputer = computers[0];
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>电脑状态</span>
            <strong>{stats.onlineComputerCount}/{stats.computerCount} 台电脑常驻接单</strong>
            <p>这里接入真实电脑、生成配对令牌、注册执行程序、扫描 Codex / Claude / Qwen 线程。</p>
            <small>{providerSummary(workstations)}</small>
          </article>
          <article className={styles.panelCard}>
            <span>重连检查</span>
            <strong>复制持续接单命令 → 保持终端或启用守护 → 回平台确认状态</strong>
            <p>{firstComputer ? runnerReconnectHint(firstComputer, workstations) : "还没有登记电脑。先点右侧“生成配对令牌”，在目标电脑运行 Windows 或 Linux 接入命令。"}</p>
            <small>用户自己运行终端命令不需要确认；NPC 代操作终端会先进入待确认。</small>
          </article>
          <article className={styles.panelCard}>
            <span>电脑列表</span>
            <ul className={styles.panelList}>
              {computers.length ? computers.map((computer) => (
                <li key={computer.id}>
                  <b>{itemTitle(computer)}</b>
                  <small>{computerListDetail(computer, workstations)}</small>
                </li>
              )) : (
                <li>
                  <b>暂无电脑，先添加本机或局域网电脑。</b>
                  <small>右侧打开“生成配对令牌”，复制 Windows 或 Linux 命令到目标电脑运行。</small>
                </li>
              )}
            </ul>
          </article>
        </div>
      );
    }

    if (tab === "skills") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>能力工坊</span>
            <strong>能力、知识库和 Git 治理统一入口</strong>
            <p>主页面只保留状态摘要；导入能力包、维护知识库、处理 Git 预检和回退登记都进入能力工坊。</p>
            <Link href={surfacePath("skill-forge", "skills")}>打开能力工坊</Link>
          </article>
          <article className={styles.panelCard}>
            <span>项目能力包条目</span>
            {renderSkillLifecycleList(skills, "暂无项目能力包")}
          </article>
          <article className={styles.panelCard}>
            <span>固定必备能力包</span>
            <ul className={styles.panelList}>
              <li><b>截图验收</b><small>每个 NPC 提交前必须用户视角验证。</small></li>
              <li><b>需求必读表</b><small>AI 做任务前先读提需求者、被提需求者、边界和验收。</small></li>
              <li><b>Git 安全回退</b><small>改代码前先确认版本点和回滚路径。</small></li>
            </ul>
          </article>
        </div>
      );
    }

    if (tab === "exchange") {
      return (
        <>
          <div className={styles.panelGrid}>
            <article className={styles.panelCard}>
              <span>协作汇总</span>
              <strong>{stats.messageCount} 条消息 / 最终回复 {finalReplyCount} 条</strong>
              <p>协作池只做记录，不是执行面；NPC 对话、人工确认和启动处理统一回 NPC 工作台。</p>
            </article>
            <article className={styles.panelCard}>
              <span>最新消息</span>
              {renderList(messages, "暂无项目事件。去 NPC 工作台和 NPC 对话后会在这里沉淀审计记录。")}
            </article>
          </div>
          {renderCollaborationFlowBoard()}
        </>
      );
    }

    if (tab === "machine-room") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>线程调试</span>
            <strong>真实线程是否能接单</strong>
            <p>这里显示每台电脑的 Codex、Claude、Qwen 线程、心跳、执行通道状态和队列健康。</p>
            <small>{providerSummary(workstations)}</small>
          </article>
          <article className={styles.panelCard}>
            <span>电脑/线程来源</span>
            {renderList(computers, "暂无电脑，先完成执行程序接入。")}
          </article>
        </div>
      );
    }

    return (
      <div className={styles.panelGrid}>
        <article className={styles.panelCard}>
          <span>版本治理</span>
          <strong>去能力工坊处理 Git 安全动作</strong>
          <p>这里保留兼容摘要；版本点、差异预检、回退确认和审计记录统一进入能力工坊。</p>
          <Link href={surfacePath("skill-forge", "git", "rollback-request")}>打开能力工坊</Link>
        </article>
        <article className={styles.panelCard}>
          <span>安全动作</span>
          <ul className={styles.panelList}>
            <li><b>预检</b><small>查看即将回退或覆盖的文件。</small></li>
            <li><b>确认</b><small>涉及代码回退和删除时必须人工确认。</small></li>
            <li><b>记录</b><small>每次回退保留交接和截图证据。</small></li>
          </ul>
        </article>
      </div>
    );
  }

  return (
    <>
      <TeamNoticeToast toast={teamNoticeToast} />
      <main className={styles.shell}>
      {sceneVisible ? (
        <iframe
          title="A Agent Education2D Interior Lab"
          className={styles.unityFrame}
          src={unitySrc}
          allow="fullscreen; gamepad; clipboard-read; clipboard-write"
        />
      ) : (
        <div className={styles.unitySceneFallback} aria-hidden="true" />
      )}

      <div className={styles.edgeGlow} aria-hidden="true" />

      {sceneVisible && npcSeats.length ? (
        <section
          className={`${styles.npcWorldLayer} ${activeAction ? styles.npcWorldLayerMuted : ""}`}
          aria-label="地图 AI 线程快捷入口"
        >
          {npcSeats.slice(0, 12).map((seat, index) => {
            const fallbackX = 28 + (index % 4) * 12;
            const fallbackY = 30 + Math.floor(index / 4) * 12;
            const left = clampPercent(Number(seat.mapX ?? fallbackX), 14, 76);
            const top = clampPercent(Number(seat.mapY ?? fallbackY), 18, 68);
            return (
              <button
                key={seat.id}
                type="button"
                data-npc-map-marker="true"
                data-npc-id={seat.id}
                className={`${styles.npcMapMarker} ${focusedNpcId === seat.id ? styles.npcMapMarkerActive : ""}`}
                style={{ left: `${left}%`, top: `${top}%` }}
                onClick={() => openNpcSeat(seat)}
                aria-label={`打开 AI 线程 ${itemTitle(seat)} 的对话框`}
              >
                <span className={styles.npcAvatarChip}>AI</span>
                <strong>{itemTitle(seat)}</strong>
                <small>{seat.responsibility || seat.body || automationLabel(seat)}</small>
              </button>
            );
          })}
        </section>
      ) : null}

      {cockpitOpen && !activePanel ? (
        <header className={styles.cockpit} aria-label="项目控制台">
          <div className={styles.cockpitHeader}>
            <div className={styles.cockpitProject}>
              <span className={styles.cockpitEyebrow}>嵌入式机器人开发台</span>
              <strong>{project.name}</strong>
              <small>{currentUser.name}{currentUser.email ? ` · ${currentUser.email}` : ""}</small>
            </div>
            <div className={styles.cockpitToolbar}>
              <button
                type="button"
                className={styles.cockpitPrimary}
                onClick={copyAiHandoffPrompt}
                disabled={copyState.kind === "loading"}
                title="把当前项目上下文复制为 AI 开发工具接手提示词"
              >
                {copyState.kind === "loading" ? "生成中..." : "复制 AI 接入提示词"}
              </button>
              <button type="button" className={styles.cockpitGhost} onClick={copyRepoUrl} title="复制仓库地址">
                仓库地址
              </button>
              <button
                type="button"
                className={styles.cockpitGhost}
                onClick={() => setSceneVisible((value) => !value)}
                title="显示/隐藏工作区背景 (快捷键 Alt+U)"
              >
                {sceneVisible ? "隐藏背景" : "显示背景"}
              </button>
              <Link href="/projects" className={styles.cockpitGhost}>项目列表</Link>
              {returnToPath ? (
                <Link href={returnToPath} className={styles.cockpitReturn}>
                  {returnToLabel}
                </Link>
              ) : null}
              <Link
                href={surfacePath("workbench")}
                className={styles.cockpitGhost}
                title="多 NPC 同屏工作台：左栏勾选/+号开瓷砖，多开自动平分"
              >
                NPC 工作台 →
              </Link>
              <Link
                href={surfacePath("robotics")}
                className={styles.cockpitGhost}
                title="调试终端、数据标注、图表实验都在同一个设备数据工作台"
              >
                设备数据工作台 →
              </Link>
              <Link
                href={surfacePath("rehab-arm-control")}
                className={styles.cockpitGhost}
                title="专项设备的非实时遥测、关键帧和安全状态总控台"
              >
                专项设备总控台 →
              </Link>
              <Link
                href={surfacePath("skill-forge")}
                className={styles.cockpitGhost}
                title="把 NPC 稳定经验沉淀成可审查、可绑定、可复用的能力包"
              >
                能力工坊 →
              </Link>
              <Link
                href={surfacePath("company")}
                className={styles.cockpitGhost}
                title="公司层：只看每个工位的工位长（👑），跨工位转交都从这里发起"
              >
                🏢 公司层
              </Link>
              <button
                type="button"
                className={styles.cockpitPrimary}
                onClick={() => setBroadcastTarget({ scope: "all", label: "全员" })}
                disabled={npcSeats.length === 0}
                title={npcSeats.length === 0 ? "项目没有 NPC，先去 NPC 入驻" : "一键给项目所有 NPC 发同一条指令（带预演 + 二次确认）"}
              >
                📣 全员广播
              </button>
              {scorecard ? (
                <button
                  type="button"
                  className={`${styles.gradeChip} ${styles[`gradeChip${scorecard.grade === "-" ? "Neutral" : scorecard.grade}`] ?? ""}`}
                  onClick={() => setScorecardOpen((v) => !v)}
                  title={`${scorecard.summary}（点击展开 6 项指标）`}
                >
                  运行评分 {scorecard.grade}
                  {scorecard.score !== null ? ` (${scorecard.score})` : ""}
                </button>
              ) : null}
              <button
                type="button"
                className={styles.cockpitGhost}
                onClick={() => setCockpitOpen(false)}
                title="完全隐藏控制台（不挡视野）"
              >
                ✕ 隐藏
              </button>
            </div>
          </div>
          {copyState.message ? (
            <div className={`${styles.cockpitToast} ${copyState.kind === "err" ? styles.cockpitToastErr : styles.cockpitToastOk}`}>
              {copyState.message}
            </div>
          ) : null}
          {manualCopy ? (
            <section className={styles.manualCopyPanel} aria-label={`${manualCopy.label} 手动复制`}>
              <div>
                <strong>{manualCopy.label}</strong>
                <button type="button" onClick={() => setManualCopy(null)}>收起</button>
              </div>
              <textarea
                readOnly
                value={manualCopy.value}
                rows={5}
                onFocus={(event) => event.currentTarget.select()}
                aria-label={`${manualCopy.label} 内容`}
              />
              <small>如果浏览器禁止自动复制，点进文本框后按 Ctrl+A / Ctrl+C。</small>
            </section>
          ) : null}
          {teamError ? <div className={`${styles.cockpitToast} ${styles.cockpitToastErr}`}>操作失败：{teamError}</div> : null}
          {!teamError && teamNotice ? <div className={`${styles.cockpitToast} ${styles.cockpitToastOk}`}>{teamNotice}</div> : null}
          <section className={styles.serviceHealthBar} aria-label="平台服务实例健康">
            <div>
              <span data-status={serviceHealth.status}>
                {serviceHealth.status === "ok" ? "服务已连接" : serviceHealth.status === "checking" ? "检查中" : "服务异常"}
              </span>
              <strong>平台状态</strong>
              <p>{serviceHealth.status === "ok" ? "当前页面已连上云端协作服务" : "正在确认平台服务是否可用"}</p>
            </div>
            <dl>
              <div>
                <dt>服务实例</dt>
                <dd>{serviceHealth.apiPid ? "已确认" : "未确认"}</dd>
              </div>
              <div>
                <dt>版本</dt>
                <dd>{serviceHealth.apiVersion || "未知"}</dd>
              </div>
              <div>
                <dt>电脑</dt>
                <dd>{stats.onlineComputerCount}/{stats.computerCount} 台常驻接单</dd>
              </div>
              <div>
                <dt>本机接入</dt>
                <dd>
                  {(serviceHealth.localServices || [])
                    .filter((item) => item.listening)
                    .length
                    ? "已检测"
                    : "未检测"}
                </dd>
              </div>
            </dl>
            <small>
              {serviceHealth.status === "ok"
                ? "页面正在读取当前协作服务；如果状态异常，先确认云端和本机接入程序是否在线。"
                : serviceHealth.message || "等待检测"}
            </small>
          </section>
          <section className={styles.workspaceMatrix} aria-label="项目工作台结构">
            <article>
              <span>资源中心</span>
              <strong>主页面统一创建和治理</strong>
              <p>电脑、执行程序、NPC、工位、Skill、仓库和成员都在这里维护，避免每个工作台各做一套。</p>
              <div>
                <button type="button" onClick={() => openPanel("development-workshop", "工作台结构")}>工位</button>
                <button type="button" onClick={() => openPanel("npc-create", "工作台结构")}>NPC</button>
                <button type="button" onClick={() => openPanel("computers", "工作台结构")}>电脑</button>
                <button type="button" onClick={() => openPanel("skills", "工作台结构")}>Skill</button>
              </div>
            </article>
            <article>
              <span>协作工作台</span>
              <strong>多 NPC 同屏协作</strong>
              <p>只消费主页面资源：Boss 分工、线程绑定、协作请求、精简回执和人工确认都在这里看执行现场。</p>
              <div>
                <Link href={surfacePath("workbench", "exchange", "dispatch-command")}>打开 NPC 工作台</Link>
                <Link href={surfacePath("company", "exchange", "dispatch-command")}>公司层</Link>
              </div>
            </article>
            <article>
              <span>专业工作台</span>
              <strong>终端 / 数据标注 / 图表实验</strong>
              <p>机器人现场、数据标注和图表实验合成同一个设备数据工作台；每个调试窗口像 NPC 瓷砖一样切换三项能力。</p>
              <div>
                <Link href={surfacePath("robotics", "machine-room")}>打开设备数据工作台</Link>
                <Link href={surfacePath("rehab-arm-control", "machine-room")}>专项设备总控台</Link>
                <Link href={surfacePath("skill-forge", "skills")}>打开能力工坊</Link>
              </div>
            </article>
          </section>
          <div className={styles.cockpitMetrics}>
            <article className={styles.cockpitMetricCard}>
              <span>当前任务</span>
              <strong>{latestTask ? itemTitle(latestTask) : "暂无活跃任务"}</strong>
              <p>{latestTask ? statusLabel(latestTask.status) : "可在下方派单或新建"} · 进行中 {stats.activeTaskCount} · 阻塞 {stats.blockedTaskCount}</p>
            </article>
            <article className={`${styles.cockpitMetricCard} ${humanReviewCount > 0 ? styles.cockpitMetricAlert : ""}`}>
              <span>待人工确认</span>
              <strong>{humanReviewCount} 条</strong>
              <p>{humanReviewCount > 0 ? "需要你点击确认，AI 不会自动放行" : "暂无阻塞，AI 工作流通畅"}</p>
            </article>
            <article className={styles.cockpitMetricCard}>
              <span>AI 线程</span>
              <strong>{npcSeats.length} 个 · 常驻接单 {stats.onlineComputerCount}/{stats.computerCount}</strong>
              <p>本月 token ￥{stats.tokenSpend} · 协作审计 {stats.messageCount}</p>
              <p>
                本机线程怎么接单？看{" "}
                <a
                  href="https://github.com/wenjunyong666/ai-/blob/main/docs/user-guides/THREAD_WATCHER_QUICKSTART_2026-05-07.md"
                  target="_blank"
                  rel="noopener noreferrer"
                  title="docs/user-guides/THREAD_WATCHER_QUICKSTART_2026-05-07.md"
                >
                  线程持续接单上手
                </a>
                （每条线程要一个 PS 终端常驻）
              </p>
              {firstWorkstation ? (
                <button
                  type="button"
                  className={styles.watcherCopyButton}
                  onClick={() => copyWatcherCommand(firstWorkstation.id)}
                  title={`复制 ${firstWorkstationLabel || "当前线程"} 的持续接单命令`}
                >
                  {`📋 复制持续接单命令（${firstWorkstationLabel || "当前线程"}）`}
                </button>
              ) : null}
              {watcherCopyState.message ? (
                <p className={watcherCopyState.kind === "err" ? styles.watcherCopyErr : styles.watcherCopyOk}>
                  {watcherCopyState.message}
                </p>
              ) : null}
            </article>
          </div>
          <WorkstationGroupsSection
            projectId={project.id}
            apiBaseUrl={apiBaseUrl}
            npcSeats={npcSeats}
            computers={computers}
            projectWorkstations={projectWorkstations}
            returnTo={returnPath("development-workshop")}
            onBroadcast={(scope, label) => setBroadcastTarget({ scope, label })}
          />
          <CrossWorkstationHandoffs
            apiBaseUrl={apiBaseUrl}
            projectId={project.id}
            seats={npcSeats.map((s) => {
              const wsName = s.workstationId
                ? (projectWorkstations.find((w) => w.id === s.workstationId)?.name ?? s.workstationName ?? s.workstationId)
                : s.computerNodeId
                  ? (computers.find((c) => c.id === s.computerNodeId)?.title ??
                     computers.find((c) => c.id === s.computerNodeId)?.name ?? s.computerNodeId)
                  : "未归属工位";
              return {
                id: s.id,
                name: s.name || s.title || s.id,
                workstationId: s.workstationId || s.computerNodeId || "",
                workstationName: wsName,
                computerNodeId: s.computerNodeId || "",
                computerNodeName: s.computerNodeId
                  ? (computers.find((c) => c.id === s.computerNodeId)?.title ??
                     computers.find((c) => c.id === s.computerNodeId)?.name ?? s.computerNodeId)
                  : "未绑定电脑",
              };
            })}
          />
          <RequirementDispatcher
            apiBaseUrl={apiBaseUrl}
            projectId={project.id}
            seats={npcSeats.map((s) => ({
              id: s.id,
              name: s.name || s.title || s.id,
              computerNodeId: s.computerNodeId || "",
              computerNodeName: s.computerNodeId
                ? (computers.find((c) => c.id === s.computerNodeId)?.title ??
                   computers.find((c) => c.id === s.computerNodeId)?.name ?? s.computerNodeId)
                : "未绑定电脑",
            }))}
          />
          {scorecard && scorecardOpen ? (
            <div className={styles.scorecardPanel}>
              <div className={styles.scorecardHeader}>
                <strong>
                  运行评分 {scorecard.grade}
                  {scorecard.score !== null ? ` (${scorecard.score})` : ""}
                </strong>
                <small>{scorecard.summary} · 近 7 天</small>
              </div>
              <div className={styles.scorecardGrid}>
                {scorecard.indicators.map((ind) => {
                  const gradeKey = (ind.grade && ind.grade !== "-" ? ind.grade : "Neutral");
                  const fixTab = SCORECARD_FIX_TAB[ind.key];
                  const showFix = fixTab && (ind.grade === "C" || ind.grade === "D");
                  return (
                    <div key={ind.key} className={`${styles.scorecardItem} ${styles[`scoreGrade${gradeKey}`] ?? ""}`}>
                      <span className={styles.scoreGradeBadge}>{ind.grade && ind.grade !== "-" ? ind.grade : "—"}</span>
                      <strong>{ind.label}</strong>
                      <small>{ind.detail}</small>
                      {showFix ? (
                        <button
                          type="button"
                          className={styles.scorecardFixButton}
                          onClick={() => openPanel(fixTab, "运行评分指标")}
                          title={`跳到 ${modules.find((m) => m.tab === fixTab)?.label ?? fixTab} 模块`}
                        >
                          去修复 →
                        </button>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}
        </header>
      ) : (
        <button
          type="button"
          className={styles.cockpitReopen}
          onClick={() => setCockpitOpen(true)}
          title="显示控制台（快捷键 Esc）"
        >
          ▼ 显示控制台
        </button>
      )}

      <aside
        className={`${styles.moduleDock} ${dockHidden ? styles.moduleDockCollapsed : ""} ${activePanel ? styles.moduleDockWithPanel : ""} ${activeAction ? styles.moduleDockBehindDrawer : ""}`}
        aria-label="平台功能入口"
      >
        <button type="button" className={styles.dockToggle} onClick={() => setDockHidden((value) => !value)}>
          {dockHidden ? "展开功能区" : "收起功能区"}
        </button>
        <div className={styles.moduleButtonList}>
          {modules.map((item) => (
            <button
              key={item.tab}
              type="button"
              data-panel-tab={item.tab}
              onClick={() => openPanel(item.tab)}
              className={`${styles.moduleButton} ${styles[item.tone]} ${activePanel === item.tab ? styles.activeModuleButton : ""}`}
            >
              <span>{item.short}</span>
              <strong>{item.label}</strong>
              <small>{item.hint}</small>
            </button>
          ))}
        </div>
      </aside>

      {!activePanel && taskBoardOpen ? (
        <section className={styles.taskBoard} aria-label="任务流水线">
          <header className={styles.taskBoardHeader}>
            <div>
              <span>任务流水线</span>
              <strong>当前项目的协作主线</strong>
            </div>
            <div className={styles.taskBoardHints}>
              <small>点任务卡 → 复制 AI 接手提示词 / 派给某个 AI 线程 / 进入消息池</small>
              <button
                type="button"
                className={styles.taskBoardToggle}
                onClick={() => setTaskBoardOpen(false)}
                title="完全隐藏任务看板（快捷键 Alt+T）"
              >
                ✕ 隐藏
              </button>
            </div>
          </header>
          <div className={styles.taskBoardLanes}>
            {[
              { key: "todo", title: "待派", filter: (t: FeedItem) => /todo|ready|new|pending/i.test(t.status), accent: styles.laneTodo },
              { key: "doing", title: "进行中", filter: (t: FeedItem) => /running|in_progress|active|queued/i.test(t.status), accent: styles.laneDoing },
              { key: "review", title: "待确认", filter: (t: FeedItem) => /blocked|waiting_approval|reviewing|failed|error|needs_changes/i.test(t.status), accent: styles.laneReview },
              { key: "done", title: "已完成", filter: (t: FeedItem) => /done|completed|archived/i.test(t.status), accent: styles.laneDone },
            ].map((lane) => {
              const laneItems = tasks.filter(lane.filter).slice(0, 4);
              return (
                <div key={lane.key} className={`${styles.taskLane} ${lane.accent}`}>
                  <header><strong>{lane.title}</strong><small>{laneItems.length}</small></header>
                  {laneItems.length ? (
                    laneItems.map((task) => (
                      <article key={task.id} className={styles.taskCard}>
                        <strong>{itemTitle(task)}</strong>
                        <small>{statusLabel(task.status)}</small>
                      </article>
                    ))
                  ) : (
                    <p className={styles.taskLaneEmpty}>—</p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {!activePanel && !taskBoardOpen ? (
        <button
          type="button"
          className={styles.taskBoardReopen}
          onClick={() => setTaskBoardOpen(true)}
          title="显示任务流水线"
        >
          显示任务流水线
        </button>
      ) : null}

      {activeModule ? (
        <section className={styles.embeddedPanel} aria-label={`${activeModule.label} 功能面板`}>
          <header className={styles.panelHeader}>
            <div>
              <span>{activeModule.short}</span>
              <strong>{activeModule.label}</strong>
              <p>{activeModule.primary}：{activeModule.description}</p>
              <small>{activeModule.farmSource}</small>
            </div>
            <div className={styles.panelHeaderActions}>
              {returnToPath ? (
                <Link href={returnToPath} className={styles.panelReturn}>
                  {returnToLabel}
                </Link>
              ) : null}
              <button type="button" className={styles.closePanel} onClick={closePanel}>关闭</button>
            </div>
          </header>
          {renderPanelContent(activeModule.tab)}
          {renderConnectivityBoard(activeModule.tab)}
          <div className={styles.actionShelf} aria-label={`${activeModule.label} 三级动作`}>
            <div className={styles.actionShelfTitle}>
              <span>三级抽屉动作</span>
              <strong>点一个动作，打开右侧细节抽屉</strong>
            </div>
            <div className={styles.actionGrid}>
              {PANEL_ACTIONS[activeModule.tab].map((action) => {
                const isLoading = loadingActionId === action.id;
                const isActive = activeAction?.id === action.id;
                return (
                  <button
                    key={action.id}
                    type="button"
                    data-panel-action={action.id}
                    className={`${styles.actionButton} ${isActive ? styles.activeActionButton : ""} ${isLoading ? styles.loadingActionButton : ""}`}
                    disabled={Boolean(loadingActionId)}
                    onClick={() => openAction(action)}
                  >
                    <span className={`${styles.actionStatus} ${connectivityToneClass(actionConnectivity(activeModule.tab, action).tone)}`}>
                      {actionConnectivity(activeModule.tab, action).label}
                    </span>
                    <b>{isLoading ? "打开中..." : action.label}</b>
                    <small>{action.summary}</small>
                  </button>
                );
              })}
            </div>
          </div>
          <div className={styles.panelActionRow}>
            <button type="button" className={styles.panelGhost} onClick={closePanel}>返回工作面背景</button>
          </div>
        </section>
      ) : null}

      {activeModule && activeAction ? (
        <aside className={styles.tertiaryDrawer} aria-label={`${activeAction.label} 三级抽屉`}>
          <header>
            <span>{activeModule.label}</span>
            <strong>{activeAction.label}</strong>
            <button type="button" onClick={closeAction}>收起</button>
          </header>
          <nav className={styles.drawerActionSwitch} aria-label={`${activeModule.label} 抽屉切换`}>
            {PANEL_ACTIONS[activeModule.tab].map((action) => {
              const isCurrent = activeAction.id === action.id;
              return (
                <button
                  key={action.id}
                  type="button"
                  data-panel-action-switch={action.id}
                  className={isCurrent ? styles.drawerActionSwitchActive : ""}
                  aria-current={isCurrent ? "page" : undefined}
                  onClick={() => openAction(action)}
                >
                  {action.label}
                </button>
              );
            })}
          </nav>
          <article>
            <b>{activeAction.summary}</b>
            <p>{activeAction.detail}</p>
          </article>
          <article className={styles.safetyBox}>
            <span>安全边界</span>
            <p>{activeAction.safety}</p>
          </article>
          {teamError || teamNotice ? (
            <article className={teamError ? styles.drawerError : styles.drawerNotice} aria-live="polite">
              <span>{teamError ? "操作失败" : "操作结果"}</span>
              <p>{teamError || teamNotice}</p>
            </article>
          ) : null}
          {renderActionForm(activeAction, activeModule.tab)}
          <div className={styles.drawerButtons}>
            <button type="button" onClick={closeAction}>回到二级面板</button>
          </div>
        </aside>
      ) : null}

      <footer className={styles.helpBar}>
        <span>当前阶段：先固定功能入口和工作台风格。所有业务操作先从右侧按钮点击打开，暂不启用可视化场景物件交互。</span>
      </footer>
    </main>
    {broadcastTarget ? (
      <BroadcastModal
        apiBaseUrl={apiBaseUrl}
        projectId={project.id}
        scope={broadcastTarget.scope}
        scopeLabel={broadcastTarget.label}
        onClose={() => setBroadcastTarget(null)}
      />
    ) : null}
    </>
  );
}
