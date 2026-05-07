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
  fetchNpcHandoffContext,
  fetchProjectClaudeContext,
  fetchProjectScorecard,
  importGithubProjectSkill,
  issueComputerNodePairingToken,
  previewCollaborationMessage,
  previewProjectGitRollback,
  requestComputerThreadScan,
  recordNpcHandoff,
  requestProjectGitRollback,
  sendWorkspaceInvitation,
  submitCollaborationMessage,
  updateProjectGitSettings,
  updateDevelopmentWorkshopStation,
  updateNpcWorkstationSeat,
  保存串口电视配置,
  保存项目日程安排,
  请求串口USB扫描,
  下发串口调试指令,
} from "../../../actions";
import { useTeamNoticeToast } from "../../../../lib/use-team-notice-toast";
import { TeamNoticeToast } from "../../../../components/team-notice-toast";
import { buildComputerOneClickConnectCommand, suggestedComputerRunnerId } from "../../../../lib/runner-onboarding-commands";
import styles from "./project-2d-upgrade-game.module.css";

type GameProject = {
  id: string;
  name: string;
  description: string;
  type: string;
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
  title?: string;
  name?: string;
  type?: string;
  body?: string;
  status: string;
  at?: string;
  providerId?: string;
  providerLabel?: string;
  computerNodeId?: string;
  sourceWorkstationId?: string;
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
  knowledgeSummary?: string;
  knowledgeHandoffPath?: string;
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
  workshopStations: WorkshopStationItem[];
  skills: FeedItem[];
  teamNotice?: string;
  teamError?: string;
};

const PANEL_TABS = [
  "development-workshop",
  "human-party",
  "npc-create",
  "computers",
  "skills",
  "schedule",
  "serial-tv",
  "ai-debug",
  "ai-simulation",
  "exchange",
  "machine-room",
  "git",
] as const;

type ModuleTab = (typeof PANEL_TABS)[number];

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
      detail: "后续接入文档、GitHub 路径、硬件约束和人工审核边界。",
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
      detail: "三级抽屉显示电脑、runner、线程、模型和工作路径提醒。",
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
      label: "装配 Skill",
      summary: "从 Skill 仓库给 NPC 选择固定技能。",
      detail: "仓库在 Skill 管理里维护；这里仅给具体 NPC 装配或卸载。",
      primaryLabel: "打开装配抽屉",
      safety: "装配变更不会立即派单。",
    },
    {
      id: "npc-dialogue",
      label: "打开对话框",
      summary: "查看用户发给 AI 的指令、AI 回执和最终回复。",
      detail: "对话框会按派单、最小回执、最终回复分层，不把长消息堆满首屏。",
      primaryLabel: "打开 NPC 对话抽屉",
      safety: "发送前显示目标 NPC 和是否自动化。",
    },
  ],
  computers: [
    {
      id: "pairing-token",
      label: "生成配对令牌",
      summary: "给新电脑生成 runner 接入令牌。",
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
      label: "Runner 健康",
      summary: "确认电脑在线、心跳、队列和最近错误。",
      detail: "如果电脑没进入项目或 runner 离线，首页需要持续提醒。",
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
      detail: "Skill 仓库是来源库，NPC 装配只索引这里的条目。",
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
  schedule: [
    {
      id: "create-ddl",
      label: "添加 DDL",
      summary: "给任务设置日期、优先级和负责人。",
      detail: "主房日历功能迁移到这里；后续在 Unity 日历物件上只做视觉，不做入口。",
      primaryLabel: "打开 DDL 抽屉",
      safety: "不会自动派单。",
    },
    {
      id: "daily-plan",
      label: "生成今日安排",
      summary: "根据任务、在线电脑和审核边界安排今日工作。",
      detail: "AI 可给建议，但涉及硬件和危险操作必须先人工审核。",
      primaryLabel: "打开今日安排抽屉",
      safety: "只生成计划，不执行。",
    },
    {
      id: "human-review",
      label: "人工审核提醒",
      summary: "把需要人确认的事项怼到首页。",
      detail: "发布、删除、回滚、硬件烧录、串口写入等必须持续提醒。",
      primaryLabel: "打开审核抽屉",
      safety: "高风险动作默认阻塞。",
    },
  ],
  "serial-tv": [
    {
      id: "usb-scan",
      label: "扫描 USB",
      summary: "扫描所有接入电脑的 USB/串口设备。",
      detail: "后续由 runner 只读上报设备列表，用户选择目标端口。",
      primaryLabel: "打开 USB 扫描抽屉",
      safety: "扫描不写串口。",
    },
    {
      id: "serial-format",
      label: "配置收发格式",
      summary: "配置后续单片机发送的横纵坐标数据格式。",
      detail: "先定义帧头、分隔符、校验和、采样率，再显示波形。",
      primaryLabel: "打开格式抽屉",
      safety: "保存格式不连接硬件。",
    },
    {
      id: "wave-view",
      label: "波形视图",
      summary: "类似 VOFA+ 的数字数据转波形入口。",
      detail: "这里先做入口，后续接实时图表和串口收发。",
      primaryLabel: "打开波形抽屉",
      safety: "只读绘图。",
    },
  ],
  "ai-debug": [
    {
      id: "automation-toggle",
      label: "自动化开关",
      summary: "按 NPC 控制是否进入持续自动化。",
      detail: "关闭时只执行当前指令；开启时才进入心跳自动化模式。",
      primaryLabel: "打开自动化抽屉",
      safety: "默认关闭，节省 token。",
    },
    {
      id: "heartbeat-time",
      label: "心跳时间",
      summary: "配置 5/15/30 分钟等心跳节奏。",
      detail: "不同 NPC 可设置不同自动化频率，避免所有线程一起烧 token。",
      primaryLabel: "打开心跳抽屉",
      safety: "超过预算时自动暂停。",
    },
    {
      id: "runaway-guard",
      label: "跑飞保护",
      summary: "检查 AI 是否重复原地踏步、越权或无验证。",
      detail: "如果没有截图、没有最终回复、没有交接，就提示人审。",
      primaryLabel: "打开保护抽屉",
      safety: "异常时不继续派单。",
    },
  ],
  "ai-simulation": [
    {
      id: "software-sim",
      label: "软件任务仿真",
      summary: "纯软件任务先模拟拆解和验收链。",
      detail: "让 AI 先产出计划、风险和验收点，再决定是否自动推进。",
      primaryLabel: "打开软件仿真抽屉",
      safety: "不改文件。",
    },
    {
      id: "robot-sim",
      label: "机器人仿真",
      summary: "机器人/嵌入式动作先进入仿真。",
      detail: "串口、烧录、运动控制、真实设备动作都先沙盘确认。",
      primaryLabel: "打开机器人仿真抽屉",
      safety: "硬件动作必须人审。",
    },
    {
      id: "approval-boundary",
      label: "审批边界",
      summary: "定义哪些任务可以自动做、哪些必须问人。",
      detail: "商业化必须把安全边界可视化，不让 AI 自己猜。",
      primaryLabel: "打开边界抽屉",
      safety: "边界修改需要负责人确认。",
    },
  ],
  exchange: [
    {
      id: "dispatch-command",
      label: "下发协作指令",
      summary: "指定给某个 NPC/线程发一条任务。",
      detail: "三级抽屉必须显示目标、需求文档、是否自动化、预期最小回执。",
      primaryLabel: "打开派单抽屉",
      safety: "关闭自动化时只做一次最终回复。",
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
      id: "adapter-logs",
      label: "Adapter 日志",
      summary: "查看 Codex/Claude/Qwen adapter 的接单和回写状态。",
      detail: "用于判断到底是平台协作，还是 Codex 自带自动化在跑。",
      primaryLabel: "打开日志抽屉",
      safety: "默认不暴露长日志给小白。",
    },
    {
      id: "online-check",
      label: "在线判断",
      summary: "判断电脑是否在线、是否登录、是否进入项目。",
      detail: "离线电脑、未进入项目、runner 心跳断开要有明确状态。",
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

function itemTitle(item?: FeedItem) {
  if (!item) return "暂无可展示条目";
  return item.title || item.name || item.type || item.body || item.id;
}

function clampPercent(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function itemBody(item?: FeedItem) {
  if (!item) return "等待平台下一步协作状态。";
  return item.body || item.status || "暂无详细说明";
}

function statusLabel(value?: string) {
  const normalized = String(value ?? "").toLowerCase();
  if (["done", "completed", "archived"].includes(normalized)) return "完成";
  if (["blocked", "failed", "error"].includes(normalized)) return "阻塞";
  if (["active", "running", "in_progress", "queued"].includes(normalized)) return "进行中";
  if (["online", "ready"].includes(normalized)) return "在线";
  if (["offline", "idle"].includes(normalized)) return "空闲";
  return value || "待处理";
}

function automationLabel(item?: FeedItem) {
  return item?.automationEnabled ? "持续自动化" : "单次执行";
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

function isAdapterMessage(message: FeedItem) {
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
  if (String(thread.status ?? "").toLowerCase() === "offline") return "离线：确认这台电脑的 runner 是否仍在心跳。";
  if (!thread.body) return "已发现线程：可继续绑定 NPC，或用于只读协作验证。";
  return thread.body;
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
  return workstations.filter((thread) => thread.computerNodeId === computer.id).length;
}

function computerUserHint(computer: FeedItem, workstations: FeedItem[]) {
  const status = String(computer.status ?? "").toLowerCase();
  const threads = computerThreadCount(computer, workstations);
  if (["online", "ready", "active"].includes(status) && threads > 0) return `可接单：已发现 ${threads} 条线程，可继续绑定 NPC 或下发只读任务。`;
  if (["online", "ready", "active"].includes(status)) return "Runner 在线但暂无线程：请打开 Codex/Claude/Qwen 后重新扫描。";
  if (status.includes("stale") || status.includes("expired")) return "心跳过期：让目标电脑重新运行 runner 接入命令或刷新心跳。";
  if (status.includes("offline")) return "离线：确认目标电脑是否开机、是否进入项目、runner 是否仍在运行。";
  return "状态需要确认：先看 runner 心跳和线程扫描结果，再派单。";
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
  "schedule:create-ddl",
  "schedule:daily-plan",
  "serial-tv:usb-scan",
  "serial-tv:serial-format",
  "serial-tv:wave-view",
  "ai-debug:automation-toggle",
  "ai-debug:heartbeat-time",
  "git:checkpoint",
  "git:diff-preview",
  "git:rollback-request",
]);

const PREVIEW_ACTIONS = new Set([
  "exchange:dispatch-command",
  "ai-simulation:software-sim",
  "ai-simulation:robot-sim",
  "ai-simulation:approval-boundary",
]);

const REVIEW_ACTIONS = new Set([
  "human-party:role-permission",
  "schedule:human-review",
  "ai-debug:runaway-guard",
  "git:rollback-request",
]);

const READONLY_ACTIONS = new Set([
  "human-party:presence",
  "computers:runner-health",
  "exchange:final-pool",
  "exchange:required-ledger",
  "machine-room:thread-list",
  "machine-room:adapter-logs",
  "machine-room:online-check",
]);

function actionKey(moduleTab: ModuleTab, action: PanelAction) {
  return `${moduleTab}:${action.id}`;
}

function actionConnectivity(moduleTab: ModuleTab, action: PanelAction): ActionConnectivity {
  const key = actionKey(moduleTab, action);
  if (REVIEW_ACTIONS.has(key)) {
    return {
      label: "人工审核",
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
    workshopStations,
    skills,
    teamNotice,
    teamError,
  } = props;
  const router = useRouter();
  const searchParams = useSearchParams();
  const teamNoticeToast = useTeamNoticeToast({ onRefresh: () => router.refresh() });

  const teamNoticeKey = searchParams?.get("team_notice") ?? "";
  const pairingTokenKey = searchParams?.get("pairing_token") ?? "";
  const adapterTokenKey = searchParams?.get("adapter_token") ?? "";
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
  const [handoffTaskId, setHandoffTaskId] = useState<string>("");
  const [cockpitOpen, setCockpitOpen] = useState(true);
  const [taskBoardOpen, setTaskBoardOpen] = useState(true);
  const setPanelNotice = (_value: string) => {};
  const panelNotice = "";

  async function copyClaudePrompt() {
    if (copyState.kind === "loading") return;
    setCopyState({ kind: "loading" });
    try {
      const data = await fetchProjectClaudeContext(project.id);
      const prompt = String(data?.prompt ?? "").trim();
      if (!prompt) throw new Error("提示词为空");
      await navigator.clipboard.writeText(prompt);
      setCopyState({ kind: "ok", message: "提示词已复制到剪贴板，粘贴到 Claude Code 即可继续。" });
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
      await navigator.clipboard.writeText(String(repoUrl));
      setCopyState({ kind: "ok", message: `仓库地址已复制：${repoUrl}` });
      setTimeout(() => setCopyState({ kind: "idle" }), 3500);
    } catch (error) {
      setCopyState({ kind: "err", message: "复制失败" });
      setTimeout(() => setCopyState({ kind: "idle" }), 3000);
    }
  }

  const [scorecard, setScorecard] = useState<{
    grade: string;
    score: number | null;
    summary: string;
    indicators: Array<{ key: string; label: string; grade?: string; detail: string }>;
  } | null>(null);
  const [scorecardOpen, setScorecardOpen] = useState(false);

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
        description: "承接农场里的开发工坊：NanoPi、App、Unity、测试等工位都从这里管理。",
        farmSource: "农场：开发工坊 / 工位管理",
      },
      {
        label: "主角管理",
        short: "主",
        hint: "成员、账号主角、名下电脑与线程",
        tab: "human-party",
        tone: "core",
        primary: "管理多人多电脑协作身份",
        description: "承接农场右侧主角栏，但默认不常驻遮挡视野，只在点击后打开。",
        farmSource: "农场：项目主角栏",
      },
      {
        label: "NPC 管理",
        short: "精",
        hint: "创建 NPC、绑定线程、装配 Skill",
        tab: "npc-create",
        tone: "agent",
        primary: "创建 AI 协作精灵",
        description: "承接农场 NPC 管理：名字、职责、知识库、Skill、线程绑定、最近任务和对话。",
        farmSource: "农场：NPC 管理器",
      },
      {
        label: "电脑接入",
        short: "电",
        hint: "Runner、配对令牌、线程扫描",
        tab: "computers",
        tone: "computer",
        primary: "接入真实电脑",
        description: "承接农场电脑接入管理：生成配对令牌、注册 runner、扫描 Codex/Claude/Qwen 线程。",
        farmSource: "农场：电脑接入管理",
      },
      {
        label: "Skill 仓库",
        short: "技",
        hint: "GitHub 导入、中文说明、分类管理",
        tab: "skills",
        tone: "skill",
        primary: "管理可复用能力仓库",
        description: "承接农场 Skill 管理仓库：这里是仓库，不是 NPC 装配页；NPC 从这里索引。",
        farmSource: "农场：Skill 管理仓库",
      },
      {
        label: "日程 DDL",
        short: "历",
        hint: "每日安排、DDL、人工审核提醒",
        tab: "schedule",
        tone: "tool",
        primary: "安排今天怎么协作",
        description: "承接农场主房日历：任务 DDL、每日安排、AI 当日执行顺序。",
        farmSource: "农场：主房日历",
      },
      {
        label: "串口电视",
        short: "波",
        hint: "USB 扫描、串口收发、波形调试",
        tab: "serial-tv",
        tone: "tool",
        primary: "打开硬件调试台",
        description: "承接农场主房电视机：后续扩展成 VOFA+ 类串口调试和波形入口。",
        farmSource: "农场：主房电视机",
      },
      {
        label: "AI 调试",
        short: "调",
        hint: "token、跑飞保护、回执质量",
        tab: "ai-debug",
        tone: "review",
        primary: "调试 AI 协作行为",
        description: "承接农场协作稳定性验收：排查 token 消耗、自动化开关、最小回执和最终回复。",
        farmSource: "农场：协作稳定性入口",
      },
      {
        label: "AI 仿真",
        short: "仿",
        hint: "机器人/软件任务先沙盘预演",
        tab: "ai-simulation",
        tone: "tool",
        primary: "先仿真再真实执行",
        description: "承接农场以战养战链路：机器人和嵌入式动作先在仿真层确认边界。",
        farmSource: "农场：开发工坊扩展入口",
      },
      {
        label: "协作消息",
        short: "讯",
        hint: "派单、最小回执、最终回复池",
        tab: "exchange",
        tone: "review",
        primary: "查看协作现场",
        description: "承接农场协作消息池：统一派单、最小回执、最终回复、人工审核提醒。",
        farmSource: "农场：协作消息池",
      },
      {
        label: "线程调试",
        short: "线",
        hint: "真实线程、心跳、队列状态",
        tab: "machine-room",
        tone: "computer",
        primary: "确认线程是否能接单",
        description: "承接农场电脑车间/机房：确认 Codex、Claude、Qwen 等真实线程是否在线。",
        farmSource: "农场：电脑车间 / 线程调试",
      },
      {
        label: "Git 回退",
        short: "Git",
        hint: "版本点、预检、人工确认",
        tab: "git",
        tone: "review",
        primary: "守住版本安全",
        description: "承接农场 Git 回退：可视化版本点、差异预检、回滚确认和审计记录。",
        farmSource: "农场：Git 回退入口",
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
  const firstNpcSeat = npcSeats[0] ?? null;
  const focusedNpcSeat = npcSeats.find((seat) => seat.id === focusedNpcId) ?? firstNpcSeat ?? null;
  const collaborationTargets = npcSeats.length ? [...npcSeats, ...workstations] : workstations;
  const todayText = new Date().toISOString().slice(0, 10);

  function returnPath(tab: ModuleTab, actionId?: string) {
    const params = new URLSearchParams({ panel: tab });
    if (actionId) params.set("action", actionId);
    return `/projects/${project.id}/2d-upgrade?${params.toString()}`;
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
    window.setTimeout(() => {
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
    }, 420);
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

  function renderMetricGrid() {
    return (
      <div className={styles.metricGrid}>
        <span><b>{stats.requirementCount}</b>需求</span>
        <span><b>{stats.activeTaskCount}</b>进行中</span>
        <span><b>{stats.blockedTaskCount}</b>阻塞</span>
        <span><b>{stats.onlineComputerCount}/{stats.computerCount}</b>在线电脑</span>
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
        label: "3. 最小回执",
        count: ackMessages.length,
        detail: "接单后先回最小回执，说明是否已读需求、能否执行、是否需要人审。",
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
          <strong>{humanReviewMessages.length ? `${humanReviewMessages.length} 条需人审` : "当前无强制人审提醒"}</strong>
          <p>这里回答“AI 到底怎么协作”：先读需求，再平台派单，再最小回执，最后只把最终回复收口。</p>
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
          <span><b>{safeCount}</b>只读/人审</span>
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
            <textarea name="detail" required rows={3} placeholder="这个工位负责什么、哪些 NPC 可以挂在这里、哪些动作必须人工审核。" />
          </label>
          <label>
            <span>总知识库摘要</span>
            <textarea name="knowledge_summary" rows={4} placeholder="写给这个工位下所有 NPC 必读的共享背景，例如仓库、硬件、接口、验收标准。" />
          </label>
          <label>
            <span>Runner 能力，逗号分隔</span>
            <input name="runner_capabilities" placeholder="例如：git, read-only, unity, serial" />
          </label>
          <label>
            <span>人工审核策略</span>
            <select name="approval_policy" defaultValue="human_review_for_hardware_and_destructive">
              <option value="human_review_for_hardware_and_destructive">硬件/删除/发布/回退必须人审</option>
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
          <input type="hidden" name="detail" value="从 Unity 2D 工坊知识库抽屉沉淀的共享知识。" />
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
            <input name="email" type="email" required placeholder="例如：partner@example.com" />
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
            <p>{isRolePanel ? "这里先做可视化权限核对，不提供静默改权。邀请新成员走“邀请协作者”，已有成员改权后续必须加 owner 人审。" : "用户先确认谁在项目里、哪台电脑在线、哪些线程可接单，再决定是否下发协作指令。"}</p>
          </article>
          <div className={styles.layeredList}>
            {projectMembers.length ? (
              projectMembers.map((member) => (
                <article key={member.id} className={styles.layeredItem}>
                  <span>{memberRoleLabel(member)}</span>
                  <b>{itemTitle(member)}</b>
                  <small>{statusLabel(member.status)} / {member.body || "暂无邮箱"}</small>
                  <p>{isRolePanel ? "可查看角色和状态；涉及权限提升、踢人、跨项目授权时必须 owner 审核。" : "项目成员可进入同一张协作地图；名下电脑和线程仍按项目隔离显示。"}</p>
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
            <textarea name="responsibility" required rows={3} placeholder="例如：负责 Unity 2D UI 验收、截图、前端接线和最终回复。" />
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
                        {itemTitle(item)} / {item.type || "线程"} / {statusLabel(item.status)}
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
            <b>这里只给 NPC 装配 Skill，Skill 源头仍在 Skill 仓库</b>
            <p>固定 Skill 会随 NPC 保存；每次派单前，NPC 都应该先读自己的固定 Skill 和项目必读需求表。</p>
          </article>
          {npcSeats.length ? (
            npcSeats.map((seat) => (
              <form key={seat.id} action={updateNpcWorkstationSeat.bind(null, project.id, seat.id)} className={styles.inlineActionForm}>
                {renderNpcSeatHiddenFields(seat, "npc-create", { includeSkillLoadout: false, returnActionId: "npc-skills" })}
                <input type="hidden" name="source_workstation_id" value={seat.sourceWorkstationId || ""} />
                <input type="hidden" name="computer_node_id" value={seat.computerNodeId || ""} />
                <input type="hidden" name="automation_enabled" value={seat.automationEnabled ? "true" : "false"} />
                <input type="hidden" name="automation_heartbeat_seconds" value={String(seat.automationHeartbeatSeconds ?? 900)} />
                <div className={styles.skillChecklist}>
                  <b>{itemTitle(seat)} 已装配 Skill</b>
                  {skills.length ? (
                    skills.map((skill) => (
                      <label key={skill.id} className={styles.skillOption}>
                        <input type="checkbox" name="skill_loadout" value={skill.id} defaultChecked={(seat.skillLoadout ?? []).includes(skill.id)} />
                        <span>{itemTitle(skill)}</span>
                        <small>{skill.body || skill.type || "项目 Skill 仓库条目"}</small>
                      </label>
                    ))
                  ) : (
                    <p className={styles.emptyHint}>Skill 仓库暂无条目。先去 Skill 仓库添加或从 GitHub 导入。</p>
                  )}
                </div>
                <SubmitButton label="保存 Skill 装配" disabled={!skills.length} />
              </form>
            ))
          ) : (
            <p className={styles.emptyHint}>还没有 NPC。先创建 NPC，再装配 Skill。</p>
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
                  const data = await fetchNpcHandoffContext(project.id, targetId);
                  const prompt = String(data?.prompt ?? "").trim();
                  if (!prompt) throw new Error("接手 prompt 为空");
                  await navigator.clipboard.writeText(prompt);
                  let recordedId: string | null = null;
                  try {
                    const recorded = await recordNpcHandoff(project.id, targetId, { task_id: handoffTaskId });
                    recordedId = String(recorded?.handoff?.id || "") || null;
                  } catch (err) {
                    setCopyState({
                      kind: "ok",
                      message: `已复制 ${focusedNpcSeat?.name || "NPC"} 的接手 prompt（落库失败：${err instanceof Error ? err.message : "未知错误"}），仍可粘贴到新线程使用。`,
                    });
                    setTimeout(() => setCopyState({ kind: "idle" }), 6000);
                    return;
                  }
                  setCopyState({
                    kind: "ok",
                    message: recordedId
                      ? `已复制并登记接手记录（Handoff ${recordedId.slice(0, 8)}…），粘贴到新线程即可。`
                      : `已复制 ${focusedNpcSeat?.name || "NPC"} 的接手 prompt，粘贴到新线程即可。`,
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
            <input name="title" required placeholder="例如：只读检查 Unity 2D 入口" />
          </label>
          <label>
            <span>指令正文</span>
            <textarea name="body" required rows={6} placeholder="写清楚目标、边界、是否只读、预期最小回执和最终回复格式。" />
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
              apiBaseUrl,
              project.id,
              node,
              pairingResult.token,
              suggestedComputerRunnerId(node),
            );
          })()
        : "";
      return (
        <div className={styles.realActionStack} data-unity-real-form="computer-pairing">
          {pairingResult ? (
            <article className={styles.resultCard}>
              <span>配对令牌已生成</span>
              <b>{pairingResult.nodeId}</b>
              <p>不用刷新页面。把下面命令发到目标电脑运行；如果目标电脑没有仓库文件，也会从平台下载 runner 脚本。</p>
              <code>{pairingResult.token}</code>
              <textarea readOnly rows={5} value={connectCommand} aria-label="电脑接入命令" />
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
            <p className={styles.emptyHint}>还没有电脑。先登记电脑并完成 runner 接入。</p>
          )}
        </div>
      );
    }

    if (moduleTab === "computers" && action.id === "runner-health") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="runner-health">
          <article className={styles.realNote}>
            <b>Runner 健康要看“电脑在线 + 心跳 + 线程数”</b>
            <p>电脑在线但扫不到线程时，不要直接派单；先让用户打开对应 AI 工具，再重新扫描线程。</p>
          </article>
          <div className={styles.layeredList}>
            {computers.length ? (
              computers.map((computer) => (
                <article key={computer.id} className={styles.layeredItem}>
                  <span>{statusLabel(computer.status)}</span>
                  <b>{itemTitle(computer)}</b>
                  <small>{computer.providerId || "runner 未绑定"} / {computerThreadCount(computer, workstations)} 条线程</small>
                  <p>{computer.body || computerUserHint(computer, workstations)}</p>
                  <details className={styles.itemDetails}>
                    <summary>下一步判断</summary>
                    <dl>
                      <div><dt>用户动作</dt><dd>{computerUserHint(computer, workstations)}</dd></div>
                      <div><dt>协作边界</dt><dd>不在线或无线程时只允许只读检查，不应自动派复杂任务。</dd></div>
                      <div><dt>最近心跳</dt><dd>{computer.at || "暂无心跳时间"}</dd></div>
                    </dl>
                  </details>
                </article>
              ))
            ) : (
              <article className={styles.layeredItem}>
                <span>空状态</span>
                <b>暂无电脑状态</b>
                <p>先到“生成配对令牌”登记电脑，再让目标电脑运行 runner 接入命令。</p>
              </article>
            )}
          </div>
        </div>
      );
    }

    if (moduleTab === "exchange" && action.id === "dispatch-command") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="exchange-dispatch">
          <form action={previewCollaborationMessage} className={styles.drawerForm}>
            <input type="hidden" name="project_id" value={project.id} />
            <input type="hidden" name="return_to" value={returnPath("exchange", "dispatch-command")} />
            <input type="hidden" name="message_type" value="agent_command" />
            <input type="hidden" name="recipient_type" value="workstation" />
            <input type="hidden" name="preview_key" value="unity-2d-dispatch" />
            <article className={styles.realNote}>
              <b>执行模式跟随目标 NPC 的自动化开关</b>
              <p>目标 NPC 关闭自动化时，这条指令只执行当前一轮；目标 NPC 开启自动化时，才允许按心跳继续推进。要改模式，请到“AI 调试”。</p>
            </article>
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
              <input name="title" required placeholder="例如：资料收集：A Agent 商业化入口" />
            </label>
            <label>
              <span>指令正文</span>
              <textarea name="body" required rows={5} placeholder="先预演，确认是否需要人工审核，再正式发送。" />
            </label>
            <SubmitButton label="先预演" disabled={!collaborationTargets.length} />
          </form>
          <form action={submitCollaborationMessage} className={styles.drawerForm}>
            <input type="hidden" name="project_id" value={project.id} />
            <input type="hidden" name="return_to" value={returnPath("exchange", "dispatch-command")} />
            <input type="hidden" name="message_type" value="agent_command" />
            <input type="hidden" name="recipient_type" value="workstation" />
            <article className={styles.realNote}>
              <b>正式登记前确认 token 边界</b>
              <p>下拉框会显示“单次执行”或“自动化开启”。关闭自动化的 NPC 不会自循环，平台只尝试拉起一次执行并等待最终回复。</p>
            </article>
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
              <input name="title" required placeholder="例如：只读协作验证" />
            </label>
            <label>
              <span>指令正文</span>
              <textarea name="body" required rows={5} placeholder="默认经过平台治理；涉及硬件/删除/发布会转人工审核。" />
            </label>
            <SubmitButton label="正式登记到协作池" disabled={!collaborationTargets.length} />
          </form>
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
                      <div><dt>来源</dt><dd>{message.sourceWorkstationId || message.providerLabel || `协作消息 #${index + 1}`}</dd></div>
                      <div><dt>下一步</dt><dd>若结果可用，回到“当前推荐动作”；若缺材料，写入“必读需求表”。</dd></div>
                      <div><dt>噪声规则</dt><dd>过程日志不进首页，只保留最终回复、阻塞原因和需要人工审核的动作。</dd></div>
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
                    <div><dt>被提需求者</dt><dd>待在协作消息里指定 NPC / 线程 / 工位</dd></div>
                    <div><dt>验收</dt><dd>完成后必须回到提需求者，并把最终回复写入最终回复池。</dd></div>
                  </dl>
                </details>
              </article>
            ))}
            {messages.slice(0, 5).map((message) => (
              <article key={`message-${message.id}`} className={styles.layeredItem}>
                <span>{message.type || "协作消息"}</span>
                <b>{itemTitle(message)}</b>
                <small>{statusLabel(message.status)} / 完成后回到提需求者</small>
                <p>{itemBody(message)}</p>
                <details className={styles.itemDetails}>
                  <summary>查看协作规则</summary>
                  <dl>
                    <div><dt>读前置需求</dt><dd>AI 接单前先看需求表，不清楚就请求人工确认。</dd></div>
                    <div><dt>token 边界</dt><dd>未开启 NPC 自动化时只执行当前指令，不连续自循环。</dd></div>
                    <div><dt>回写</dt><dd>先给最小回执，最终结果只写最终回复池。</dd></div>
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
        <form action={importGithubProjectSkill.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="skill-github-import">
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
          <SubmitButton label="从 GitHub 导入 Skill" />
        </form>
      );
    }

    if (moduleTab === "skills" && (action.id === "skill-category" || action.id === "skill-detail")) {
      return (
        <form action={createProjectSkill.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="skill-create-custom">
          <input type="hidden" name="return_to" value={returnPath("skills", action.id)} />
          <label>
            <span>Skill 标识</span>
            <input name="skill_id" required placeholder="例如：unity-ui-screenshot-qa" />
          </label>
          <label>
            <span>中文名字</span>
            <input name="label" required placeholder="例如：Unity UI 截图验收" />
          </label>
          <label>
            <span>中文说明</span>
            <textarea name="note" required rows={6} placeholder="具体说明用途、触发条件、输入输出、截图验证要求、人工审核边界和 token 风险。" />
          </label>
          <label>
            <span>推荐给哪些职业，逗号分隔</span>
            <input name="recommended_for" placeholder="例如：Unity UI 工程师, 前端工程师" />
          </label>
          <SubmitButton label="新增项目 Skill" />
        </form>
      );
    }

    if (moduleTab === "schedule" && (action.id === "create-ddl" || action.id === "daily-plan")) {
      return (
        <form action={保存项目日程安排.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="schedule-save-plan">
          <input type="hidden" name="return_to" value={returnPath("schedule", action.id)} />
          <label>
            <span>日期</span>
            <input name="schedule_date" type="date" defaultValue={todayText} />
          </label>
          <label>
            <span>今日安排</span>
            <textarea name="daily_plan" required rows={5} placeholder="写今天要推进的事项、负责 NPC/电脑、哪些要人审、哪些可以自动做。" />
          </label>
          <label>
            <span>DDL / 审核提醒</span>
            <textarea name="ddl_note" rows={4} placeholder="例如：19:00 前完成只读验收；串口写入和 Git 回退必须人工确认。" />
          </label>
          <SubmitButton label="保存日程安排" />
        </form>
      );
    }

    if (moduleTab === "schedule" && action.id === "human-review") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="schedule-human-review">
          <article className={styles.realNote}>
            <b>需要人工审核的边界</b>
            <p>硬件写入、烧录、删除文件、Git 回退、发布上线、跨账号权限变更，都必须在人审卡片里持续提醒，不能让 AI 静默执行。</p>
          </article>
          {renderList(tasks.filter((task) => ["blocked", "failed", "error"].includes(task.status.toLowerCase())), "当前没有阻塞任务。")}
        </div>
      );
    }

    if (moduleTab === "serial-tv" && action.id === "usb-scan") {
      return (
        <form action={请求串口USB扫描.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="serial-usb-scan">
          <input type="hidden" name="return_to" value={returnPath("serial-tv", "usb-scan")} />
          <label>
            <span>目标电脑</span>
            <select name="computer_node_id" defaultValue="all">
              <option value="all">所有已接入电脑</option>
              {computers.map((computer) => (
                <option key={computer.id} value={computer.id}>{itemTitle(computer)} / {statusLabel(computer.status)}</option>
              ))}
            </select>
          </label>
          <SubmitButton label="下发 USB/串口扫描" disabled={!computers.length} />
        </form>
      );
    }

    if (moduleTab === "serial-tv" && action.id === "serial-format") {
      return (
        <form action={保存串口电视配置.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="serial-format">
          <input type="hidden" name="return_to" value={returnPath("serial-tv", "serial-format")} />
          <label>
            <span>波特率</span>
            <input name="baud_rate" type="number" defaultValue={115200} />
          </label>
          <label>
            <span>协议名</span>
            <input name="protocol" defaultValue="aicollab-csv-v1" />
          </label>
          <label>
            <span>帧格式</span>
            <textarea name="frame_format" rows={4} defaultValue={"@xy,<x>,<y>\\n 或 @sample,<t>,<ch1>,<ch2>...\\n"} />
          </label>
          <label>
            <span>通道名，逗号分隔</span>
            <input name="channel_names" defaultValue="x,y" />
          </label>
          <label>
            <span>备注</span>
            <textarea name="notes" rows={3} placeholder="例如：后续单片机按 @xy,12,34 发送，平台转成二维轨迹和波形。" />
          </label>
          <SubmitButton label="保存串口电视格式" />
        </form>
      );
    }

    if (moduleTab === "serial-tv" && action.id === "wave-view") {
      return (
        <form action={下发串口调试指令.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="serial-write-command">
          <input type="hidden" name="return_to" value={returnPath("serial-tv", "wave-view")} />
          <label>
            <span>目标电脑</span>
            <select name="computer_node_id" required>
              <option value="">请选择电脑</option>
              {computers.map((computer) => (
                <option key={computer.id} value={computer.id}>{itemTitle(computer)} / {statusLabel(computer.status)}</option>
              ))}
            </select>
          </label>
          <label>
            <span>端口</span>
            <input name="port" required placeholder="例如：COM3 或 /dev/ttyUSB0" />
          </label>
          <label>
            <span>波特率</span>
            <input name="baud_rate" type="number" defaultValue={115200} />
          </label>
          <label>
            <span>发送格式</span>
            <select name="payload_format" defaultValue="text-lf">
              <option value="text-lf">文本 + 换行</option>
              <option value="text">原始文本</option>
              <option value="hex">HEX</option>
            </select>
          </label>
          <label>
            <span>发送数据</span>
            <textarea name="payload" required rows={4} placeholder="@xy,12,34" />
          </label>
          <SubmitButton label="下发串口调试指令" disabled={!computers.length} />
        </form>
      );
    }

    if (moduleTab === "ai-debug" && (action.id === "automation-toggle" || action.id === "heartbeat-time")) {
      return (
        <div className={styles.realActionStack} data-unity-real-form={`ai-debug-${action.id}`}>
          <article className={styles.realNote}>
            <b>按 NPC 单独控制 token 消耗</b>
            <p>关闭自动化时，平台只执行当前发送的单条指令；开启后才允许心跳自动推进。这个配置会写回真实 NPC 席位。</p>
          </article>
          {npcSeats.length ? (
            npcSeats.map((seat) => (
              <form key={seat.id} action={updateNpcWorkstationSeat.bind(null, project.id, seat.id)} className={styles.inlineActionForm}>
                {renderNpcSeatHiddenFields(seat, "ai-debug", { returnActionId: action.id })}
                <input type="hidden" name="source_workstation_id" value={seat.sourceWorkstationId || ""} />
                <input type="hidden" name="computer_node_id" value={seat.computerNodeId || ""} />
                <label>
                  <span>{itemTitle(seat)} 自动化模式</span>
                  <select name="automation_enabled" defaultValue={seat.automationEnabled ? "true" : "false"}>
                    <option value="false">关闭：只执行当前指令</option>
                    <option value="true">开启：进入心跳自动化</option>
                  </select>
                </label>
                <label>
                  <span>心跳间隔秒数</span>
                  <input name="automation_heartbeat_seconds" type="number" min={300} step={60} defaultValue={seat.automationHeartbeatSeconds ?? 900} />
                </label>
                <SubmitButton label="保存自动化设置" />
              </form>
            ))
          ) : (
            <p className={styles.emptyHint}>还没有 NPC。先到 NPC 管理创建，再回来配置自动化。</p>
          )}
        </div>
      );
    }

    if (moduleTab === "ai-debug" && action.id === "runaway-guard") {
      return (
        <div className={styles.realActionStack} data-unity-real-form="ai-debug-runaway-guard">
          <article className={styles.realNote}>
            <b>跑飞保护先以只读审计呈现</b>
            <p>这里集中看每个 NPC 是否开启自动化、心跳是否过密、是否缺少绑定线程。后续再接入预算阈值和自动暂停。</p>
          </article>
          <ul className={styles.realList}>
            {feedSummary(npcSeats, "暂无 NPC 可审计。").map((seat) => (
              <li key={seat.id}>
                <b>{itemTitle(seat)}</b>
                <small>
                  {automationLabel(seat)} / {seat.automationHeartbeatSeconds ?? 900}s / 线程 {seat.sourceWorkstationId || "未绑定"}
                </small>
              </li>
            ))}
          </ul>
        </div>
      );
    }

    if (moduleTab === "ai-simulation" && action.id) {
      const simulationPreset =
        action.id === "robot-sim"
          ? "机器人/嵌入式仿真：先列出硬件边界、串口/烧录/运动控制风险、需要人审的动作，再给出只读验证计划。"
          : action.id === "approval-boundary"
            ? "审批边界仿真：列出哪些任务可自动推进，哪些必须人工审核，触发暂停的条件是什么。"
            : "软件任务仿真：先模拟需求拆解、责任人、最小回执、最终回复和验收点，不改文件。";
      return (
        <div className={styles.realActionStack} data-unity-real-form={`${moduleTab}-${action.id}`}>
          <article className={styles.realNote}>
            <b>{action.label} 先预演，再决定是否真实执行</b>
            <p>仿真不会直接改文件或操作硬件；它先向指定 NPC/线程发出“只读仿真”要求，拿到边界和验收点后再决定是否派真实任务。</p>
          </article>
          <form action={previewCollaborationMessage} className={styles.drawerForm}>
            <input type="hidden" name="project_id" value={project.id} />
            <input type="hidden" name="return_to" value={returnPath("ai-simulation", action.id)} />
            <input type="hidden" name="message_type" value="agent_command" />
            <input type="hidden" name="recipient_type" value="workstation" />
            <input type="hidden" name="preview_key" value={`unity-2d-${action.id}`} />
            <label>
              <span>仿真目标 NPC / 线程</span>
              <select name="recipient_id" defaultValue={focusedNpcSeat?.id ?? firstWorkstation?.id ?? ""} required>
                <option value="">请选择一个 NPC 或线程</option>
                {collaborationTargets.map((item) => (
                  <option key={item.id} value={item.id}>
                    {itemTitle(item)} / {item.type || "线程"}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>仿真标题</span>
              <input name="title" required defaultValue={`${action.label}：只读预演`} />
            </label>
            <label>
              <span>仿真指令</span>
              <textarea name="body" required rows={6} defaultValue={simulationPreset} />
            </label>
            <SubmitButton label="先预演仿真" disabled={!collaborationTargets.length} />
          </form>
          <form action={submitCollaborationMessage} className={styles.drawerForm}>
            <input type="hidden" name="project_id" value={project.id} />
            <input type="hidden" name="return_to" value={returnPath("ai-simulation", action.id)} />
            <input type="hidden" name="message_type" value="agent_command" />
            <input type="hidden" name="recipient_type" value="workstation" />
            <label>
              <span>正式登记仿真目标</span>
              <select name="recipient_id" defaultValue={focusedNpcSeat?.id ?? firstWorkstation?.id ?? ""} required>
                <option value="">请选择一个 NPC 或线程</option>
                {collaborationTargets.map((item) => (
                  <option key={item.id} value={item.id}>
                    {itemTitle(item)} / {item.type || "线程"}
                  </option>
                ))}
              </select>
            </label>
            <input type="hidden" name="title" value={`${action.label}：只读仿真`} />
            <input type="hidden" name="body" value={simulationPreset} />
            <SubmitButton label="登记到协作池" disabled={!collaborationTargets.length} />
          </form>
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
                <p className={styles.emptyHint}>暂无线程。先接入电脑、注册 runner，再扫描 Codex / Claude / Qwen 线程。</p>
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
              <p>商用时要同时看：电脑是否登记、Runner 是否心跳、账号是否进入项目、线程是否可接单。任何一层断了，都要告诉用户下一步做什么。</p>
            </article>
            <div className={styles.onlineCheckGrid}>
              <span><b>{computers.length}</b>已登记电脑</span>
              <span><b>{stats.onlineComputerCount}</b>Runner 在线</span>
              <span><b>{workstations.length}</b>可见线程</span>
              <span><b>{npcSeats.length}</b>已绑定 NPC</span>
            </div>
            <div className={styles.layeredList}>
              {computers.length ? (
                computers.map((computer) => (
                  <article key={computer.id} className={styles.layeredItem}>
                    <span>{statusLabel(computer.status)}</span>
                    <b>{itemTitle(computer)}</b>
                    <small>{computerThreadCount(computer, workstations)} 条线程 / {computer.type || "runner"}</small>
                    <p>{computerUserHint(computer, workstations)}</p>
                  </article>
                ))
              ) : (
                <article className={styles.layeredItem}>
                  <span>空状态</span>
                  <b>暂无电脑在线状态</b>
                  <p>先在电脑接入里生成配对令牌并运行 runner 接入命令。</p>
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
            <p>这里承接农场电脑房：只读展示真实电脑、runner 和线程状态。扫描与配对动作已放在“电脑接入”。</p>
          </article>
          <div className={styles.layeredList}>
            {messages.filter(isAdapterMessage).slice(0, 8).map((message) => (
              <article key={message.id} className={styles.layeredItem}>
                <span>{message.type || "adapter"}</span>
                <b>{itemTitle(message)}</b>
                <small>{statusLabel(message.status)} / {message.at || "暂无时间"}</small>
                <p>{itemBody(message)}</p>
              </article>
            ))}
            {!messages.filter(isAdapterMessage).length ? (
              <article className={styles.layeredItem}>
                <span>空状态</span>
                <b>暂无 adapter 摘要</b>
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
                  <option value="runner_env">各电脑 Runner 环境变量</option>
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
        <form action={previewProjectGitRollback.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="git-rollback-preview">
          <input type="hidden" name="return_to" value={returnPath("git", "rollback-request")} />
          <label>
            <span>目标版本</span>
            <input name="target_ref" required placeholder="例如：HEAD~1 或 develop" />
          </label>
          <label>
            <span>备注</span>
            <textarea name="notes" rows={4} placeholder="说明为什么要回退，先只做预演和只读预检。" />
          </label>
          <SubmitButton label="生成回退预演" />
        </form>
      );
    }

    if (moduleTab === "git" && action.id === "rollback-request") {
      return (
        <form action={requestProjectGitRollback.bind(null, project.id)} className={styles.drawerForm} data-unity-real-form="git-rollback-request">
          <input type="hidden" name="return_to" value={returnPath("git", "rollback-request")} />
          <label>
            <span>目标版本</span>
            <input name="target_ref" required placeholder="例如：HEAD~1 或 develop" />
          </label>
          <label>
            <span>人工确认备注</span>
            <textarea name="notes" rows={4} placeholder="登记请求后仍会先下发只读预检，不直接执行破坏性 reset。" />
          </label>
          <SubmitButton label="登记回退请求" />
        </form>
      );
    }

    return (
      <article className={styles.realNote}>
        <b>这一项已完成入口搬迁，真实表单下一批接线。</b>
        <p>当前先保证 Unity 2D 不再跳回农场、不靠地图交互；下一轮继续把旧农场对应 server action 搬进这个抽屉。</p>
      </article>
    );
  }

  function renderPanelContent(tab: ModuleTab) {
    if (tab === "development-workshop") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>工坊总览</span>
            <strong>工位是用户可编辑的项目工作区</strong>
            <p>开发工坊是共用系统，NPC 只是挂到工位下面。后续这里接入工位创建、工位知识库、负责 NPC 和风险边界。</p>
            {renderMetricGrid()}
          </article>
          <article className={styles.panelCard}>
            <span>需求队列</span>
            {renderList(requirements, "暂无需求，先从需求箱写入下一步。")}
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
            <p>{currentUser.email || "未拿到邮箱"} / 这里承接农场主角栏，但只点击打开，不再长期挡住地图。</p>
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
            <span>NPC 精灵栏</span>
            <strong>创建、绑定、装配和对话都放这里</strong>
            <p>后续三级抽屉会包含 NPC 基础信息、职责、自动化开关、知识库、Skill 装配、绑定电脑/线程和对话框。</p>
          </article>
          <article className={styles.panelCard}>
            <span>最近任务</span>
            {renderList(tasks, "暂无任务，先从协作消息或工坊派发。")}
          </article>
        </div>
      );
    }

    if (tab === "computers") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>电脑状态</span>
            <strong>{stats.onlineComputerCount}/{stats.computerCount} 台在线</strong>
            <p>这里接入真实电脑、生成配对令牌、注册 runner、扫描 Codex / Claude / Qwen 线程。</p>
            <small>{providerSummary(workstations)}</small>
          </article>
          <article className={styles.panelCard}>
            <span>电脑列表</span>
            {renderList(computers, "暂无电脑，先添加本机或局域网电脑。")}
          </article>
        </div>
      );
    }

    if (tab === "skills") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>Skill 仓库</span>
            <strong>这里是仓库，不是 NPC 装配页</strong>
            <p>支持从 GitHub 导入 skill，写中文说明、分类和适用职业；NPC 装配时从这里索引。</p>
          </article>
          <article className={styles.panelCard}>
            <span>固定必备 Skill</span>
            <ul className={styles.panelList}>
              <li><b>截图验收</b><small>每个 NPC 提交前必须用户视角验证。</small></li>
              <li><b>需求必读表</b><small>AI 做任务前先读提需求者、被提需求者、边界和验收。</small></li>
              <li><b>Git 安全回退</b><small>改代码前先确认版本点和回滚路径。</small></li>
            </ul>
          </article>
        </div>
      );
    }

    if (tab === "schedule") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>日程日历</span>
            <strong>任务 DDL 和每日安排</strong>
            <p>后续这里接入主房日历：编辑 DDL、今天安排、人工审核提醒，并让 AI 给出当日执行顺序。</p>
          </article>
          <article className={styles.panelCard}>
            <span>今日可安排任务</span>
            {renderList(tasks, "暂无今日任务。")}
          </article>
        </div>
      );
    }

    if (tab === "serial-tv") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>串口电视</span>
            <strong>USB 扫描 / 串口收发 / 波形查看</strong>
            <p>先做入口框架，后续接 Runner 扫描 USB 设备、串口收发格式和数字数据波形。</p>
          </article>
          <article className={styles.panelCard}>
            <span>可调试电脑</span>
            {renderList(computers, "暂无在线电脑可调试。")}
          </article>
        </div>
      );
    }

    if (tab === "ai-debug") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>AI 调试</span>
            <strong>防跑飞、控 token、看回执</strong>
            <p>这里后续专门看自动化开关、心跳时间、队列堆积、最小回执质量和最终回复是否收口。</p>
          </article>
          <article className={styles.panelCard}>
            <span>协作信号</span>
            {renderList(messages, "暂无协作消息。")}
          </article>
        </div>
      );
    }

    if (tab === "ai-simulation") {
      return (
        <div className={styles.panelGrid}>
          <article className={styles.panelCard}>
            <span>AI 仿真</span>
            <strong>机器人和软件任务先沙盘预演</strong>
            <p>纯软件可自动推进；嵌入式、硬件、串口、发布、删除和真实设备动作必须先进入人工审核。</p>
          </article>
          <article className={styles.panelCard}>
            <span>待仿真需求</span>
            {renderList(requirements, "暂无待仿真需求。")}
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
              <p>协作池不再当日志墙：先看链路状态，再进三级抽屉看派单、最终回复或必读需求。</p>
            </article>
            <article className={styles.panelCard}>
              <span>最新消息</span>
              {renderList(messages, "暂无协作消息，先向 NPC 或线程派单。")}
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
            <p>这里显示每台电脑的 Codex、Claude、Qwen 线程、心跳、adapter 状态和队列健康。</p>
            <small>{providerSummary(workstations)}</small>
          </article>
          <article className={styles.panelCard}>
            <span>电脑/线程来源</span>
            {renderList(computers, "暂无电脑，先完成 runner 接入。")}
          </article>
        </div>
      );
    }

    return (
      <div className={styles.panelGrid}>
        <article className={styles.panelCard}>
          <span>Git 回退</span>
          <strong>可视化版本安全入口</strong>
          <p>后续在这里做版本点、差异预检、回滚确认和 AI 改动审查。</p>
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

      {cockpitOpen ? (
        <header className={styles.cockpit} aria-label="开发者驾驶舱">
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
                onClick={copyClaudePrompt}
                disabled={copyState.kind === "loading"}
                title="把当前项目上下文复制为 Claude Code 提示词"
              >
                {copyState.kind === "loading" ? "生成中..." : "复制 Claude Code 提示词"}
              </button>
              <button type="button" className={styles.cockpitGhost} onClick={copyRepoUrl} title="复制仓库地址">
                仓库地址
              </button>
              <button
                type="button"
                className={styles.cockpitGhost}
                onClick={() => setSceneVisible((value) => !value)}
                title="显示/隐藏 Unity 场景背景"
              >
                {sceneVisible ? "隐藏场景" : "显示场景"}
              </button>
              <Link href="/projects" className={styles.cockpitGhost}>项目列表</Link>
              {scorecard ? (
                <button
                  type="button"
                  className={`${styles.gradeChip} ${styles[`gradeChip${scorecard.grade === "-" ? "Neutral" : scorecard.grade}`] ?? ""}`}
                  onClick={() => setScorecardOpen((v) => !v)}
                  title={`${scorecard.summary}（点击展开 6 项指标）`}
                >
                  合格性 {scorecard.grade}
                  {scorecard.score !== null ? ` (${scorecard.score})` : ""}
                </button>
              ) : null}
              <button
                type="button"
                className={styles.cockpitGhost}
                onClick={() => setCockpitOpen(false)}
                title="完全隐藏驾驶舱（不挡视野）"
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
          {teamError ? <div className={`${styles.cockpitToast} ${styles.cockpitToastErr}`}>操作失败：{teamError}</div> : null}
          {!teamError && teamNotice ? <div className={`${styles.cockpitToast} ${styles.cockpitToastOk}`}>{teamNotice}</div> : null}
          <div className={styles.cockpitMetrics}>
            <article className={styles.cockpitMetricCard}>
              <span>当前任务</span>
              <strong>{latestTask ? itemTitle(latestTask) : "暂无活跃任务"}</strong>
              <p>{latestTask ? statusLabel(latestTask.status) : "可在下方派单或新建"} · 进行中 {stats.activeTaskCount} · 阻塞 {stats.blockedTaskCount}</p>
            </article>
            <article className={`${styles.cockpitMetricCard} ${humanReviewCount > 0 ? styles.cockpitMetricAlert : ""}`}>
              <span>待人工审核</span>
              <strong>{humanReviewCount} 条</strong>
              <p>{humanReviewCount > 0 ? "需要你点击审批，AI 不会自动放行" : "暂无阻塞，AI 工作流通畅"}</p>
            </article>
            <article className={styles.cockpitMetricCard}>
              <span>AI 线程</span>
              <strong>{npcSeats.length} 个 · 在线电脑 {stats.onlineComputerCount}/{stats.computerCount}</strong>
              <p>本月 token ￥{stats.tokenSpend} · 协作消息 {stats.messageCount}</p>
            </article>
          </div>
          {scorecard && scorecardOpen ? (
            <div className={styles.scorecardPanel}>
              <div className={styles.scorecardHeader}>
                <strong>
                  合格性 {scorecard.grade}
                  {scorecard.score !== null ? ` (${scorecard.score})` : ""}
                </strong>
                <small>{scorecard.summary} · 近 7 天</small>
              </div>
              <div className={styles.scorecardGrid}>
                {scorecard.indicators.map((ind) => {
                  const gradeKey = (ind.grade && ind.grade !== "-" ? ind.grade : "Neutral");
                  return (
                    <div key={ind.key} className={`${styles.scorecardItem} ${styles[`scoreGrade${gradeKey}`] ?? ""}`}>
                      <span className={styles.scoreGradeBadge}>{ind.grade && ind.grade !== "-" ? ind.grade : "—"}</span>
                      <strong>{ind.label}</strong>
                      <small>{ind.detail}</small>
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
          title="显示驾驶舱"
        >
          ▼ 显示驾驶舱
        </button>
      )}

      <aside
        className={`${styles.moduleDock} ${dockHidden ? styles.moduleDockCollapsed : ""} ${activePanel ? styles.moduleDockWithPanel : ""} ${activeAction ? styles.moduleDockBehindDrawer : ""}`}
        aria-label="平台功能入口"
      >
        <button type="button" className={styles.dockToggle} onClick={() => setDockHidden((value) => !value)}>
          {dockHidden ? "显示功能" : "隐藏功能"}
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
              <small>点任务卡 → 复制 Claude prompt / 派给某个 AI 线程 / 进入消息池</small>
              <button
                type="button"
                className={styles.taskBoardToggle}
                onClick={() => setTaskBoardOpen(false)}
                title="完全隐藏任务看板（不挡视野）"
              >
                ✕ 隐藏
              </button>
            </div>
          </header>
          <div className={styles.taskBoardLanes}>
            {[
              { key: "todo", title: "待派", filter: (t: FeedItem) => /todo|ready|new|pending/i.test(t.status), accent: styles.laneTodo },
              { key: "doing", title: "进行中", filter: (t: FeedItem) => /running|in_progress|active|queued/i.test(t.status), accent: styles.laneDoing },
              { key: "review", title: "待审", filter: (t: FeedItem) => /blocked|waiting_approval|reviewing|failed|error|needs_changes/i.test(t.status), accent: styles.laneReview },
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
            <button type="button" className={styles.closePanel} onClick={closePanel}>关闭</button>
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
            <button type="button" className={styles.panelGhost} onClick={closePanel}>返回游戏背景</button>
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
        <span>当前阶段：先搬功能入口和 UI 风格。所有业务操作先从右侧按钮点击打开，暂不启用 Unity 物件交互。</span>
      </footer>
    </main>
    </>
  );
}
