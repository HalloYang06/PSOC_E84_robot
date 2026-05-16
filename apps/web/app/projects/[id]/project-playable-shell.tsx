"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type Dispatch, type FormEvent, type SetStateAction, useEffect, useMemo, useRef, useState } from "react";

import {
  backfillProjectNpcKnowledge,
  bindProjectGithubAccount,
  校准Claude席位会话,
  校准Codex席位自治桥,
  createDevelopmentWorkshopStation,
  createCollaborationNode,
  createCollaborationWorkstation,
  updateCollaborationProviderExecution,
  updateCollaborationWorkstationExecution,
  createNpcWorkstationSeat,
  createProjectSkill,
  deleteDevelopmentWorkshopStation,
  deleteNpcWorkstationSeat,
  deleteProjectSkill,
  issueComputerNodePairingToken,
  issueCollaborationWorkstationAdapterToken,
  importAgencyAgentsSkillPack,
  importGithubProjectSkill,
  previewCollaborationMessage,
  handleCollaborationHumanReview,
  handleStaleQueueDecision,
  previewProjectGitSync,
  previewProjectGitRollback,
  requestComputerThreadScan,
  updateProjectGitSettings,
  requestProjectGitSync,
  requestProjectGitRollback,
  revokeCollaborationWorkstationAdapterToken,
  revokeComputerNodePairingToken,
  runPlatformAutonomySweep,
  sendRunnerCommand,
  startNpcRelayCollaboration,
  submitCollaborationMessage,
  updateDevelopmentWorkshopStation,
  updateNpcWorkstationSeat,
  创建项目任务,
  保存串口电视配置,
  保存项目日程安排,
  请求串口USB扫描,
  下发串口调试指令,
  更新任务DDL,
  退出登录,
} from "../../actions";
import {
  normalizePlatformProviderId,
  platformProviderLabel,
  platformProviderIdFromSeat,
  platformProviderIdFromThread,
  platformProviderLabelFromSeat,
  platformProviderLabelFromThread,
  supportsLocalCodexAutonomyBridge,
  supportsPlatformNpcCreation,
} from "../../../lib/platform-provider";
import {
  buildProjectFutureModeChoicePaths,
  buildProjectFutureModeShellPaths,
  buildProjectModeDefinitions,
  buildProjectModeChoicePath,
  buildProjectModeEntryPath,
  buildModeShellPath,
  type FutureModePathMap,
  type ProjectModeDefinition,
  normalizeModeEntryId,
  projectEntryLiveModeLayerHint,
  projectEntryShellPath,
} from "../mode-entry-paths";
import {
  PLATFORM_SKILL_STARTER_KITS,
  isBaselineSkill,
  mergePlatformSkillLoadout,
  recommendRoleSkillIds,
  splitPlatformSkillLoadout,
} from "../../../lib/platform-skills";
import { resolveNpcKnowledgeProfile } from "../../../lib/npc-knowledge";
import {
  PLATFORM_APPROVAL_POLICY_OPTIONS,
  PLATFORM_WORK_KIND_OPTIONS,
  collabDebugPolicySummary,
  collabEfficiencyPolicySummary,
  collabProjectProfileLabel,
  collabProtocolApprovalLabel,
  collabProtocolWorkKindLabel,
  collabRunawayPolicySummary,
  collabTokenPolicySummary,
  resolvePlatformCollabProtocol,
} from "../../../lib/platform-collab-protocol";
import {
  buildPlatformRepoReferencePaths,
  platformRepoContextNote,
  platformRepoContextSummary,
} from "../../../lib/platform-repo-context";
import { summarizeNpcProvisioning } from "../../../lib/npc-provisioning";
import { useTeamNoticeToast } from "../../../lib/use-team-notice-toast";
import { TeamNoticeToast } from "../../../components/team-notice-toast";
import {
  DEFAULT_AUTOMATION_HEARTBEAT_SECONDS,
  buildComputerClaudeThreadSyncBashCommand,
  buildComputerClaudeThreadSyncCommand,
  buildComputerCodexThreadSyncBashCommand,
  buildComputerCodexThreadSyncCommand,
  buildComputerManualThreadSyncBashCommand,
  buildComputerManualThreadSyncCommand,
  buildComputerOneClickConnectBashCommand,
  buildComputerOneClickConnectCommand,
  buildComputerRunnerRegisterBashCommand,
  buildComputerRunnerRegisterCommand,
  buildComputerRunnerWatchBashCommand,
  buildComputerRunnerWatchCommand,
  buildRunnerScriptUrl,
  buildWorkstationAdapterBashCommand,
  buildWorkstationAdapterCommand,
  normalizeAutomationHeartbeatSeconds,
  normalizeComputerRunnerSlug,
  suggestedComputerRunnerId,
} from "../../../lib/runner-onboarding-commands";
import {
  normalizeDevelopmentWorkshopStations,
  type DevelopmentWorkshopStation,
} from "../../../lib/development-workshop";
import agencyAgentsSkillPack from "../../../lib/skill-packs/agency-agents-skill-pack.json";
import styles from "./project-playable-shell.module.css";
import { ClaudeCommandPalette } from "./_components/claude-command-palette";

type AnyRecord = Record<string, any>;
type DisplayResolver = (value: unknown, fallback: string) => string;
type RequirementMessageMap = Map<string, AnyRecord[]>;
type PanelView =
  | "exchange"
  | "human-party"
  | "computers"
  | "npc-create"
  | "machine-room"
  | "git"
    | "skills"
    | "schedule"
    | "serial-tv"
    | "ai-debug"
    | "ai-simulation"
    | "development-workshop";
type NpcCreateSubview = "threads" | "seats" | "editor";
type ManagerDrawerKind =
  | "npc-create"
  | "npc-dialog"
  | "npc-profile"
  | "npc-bind"
  | "npc-skills"
  | "exchange-detail"
  | "computer-connect"
  | "computer-threads"
  | "skill-create"
  | "skill-github-import"
  | "skill-import"
  | "skill-detail"
  | "development-module";
type ManagerDrawerState = {
  kind: ManagerDrawerKind;
  id?: string;
};

const EXCHANGE_SECTION_IDS = [
  "overview",
  "member-sync",
  "dispatch",
  "receipts",
  "thread-focus",
  "advanced-proof",
] as const;
type ExchangeSectionId = (typeof EXCHANGE_SECTION_IDS)[number];
type ExchangeReceiptFilter = "all" | "open" | "finals" | "clean";
type ExchangeComposerMode = "sync" | "dispatch" | "relay";

function normalizeExchangeSectionId(value: unknown): ExchangeSectionId {
  const raw = text(value, "overview");
  return (EXCHANGE_SECTION_IDS as readonly string[]).includes(raw) ? (raw as ExchangeSectionId) : "overview";
}

function normalizeExchangeComposerMode(value: unknown): ExchangeComposerMode | null {
  const raw = text(value, "");
  return raw === "sync" || raw === "dispatch" || raw === "relay" ? raw : null;
}

type ProjectPlayableShellProps = {
  project: AnyRecord;
  config: AnyRecord;
  tasks: AnyRecord[];
  requirements: AnyRecord[];
  collaborationMessages: AnyRecord[];
  relayTimeline: AnyRecord[];
  codexInbox?: AnyRecord[];
  gitExecution?: AnyRecord | null;
  gitActivity?: AnyRecord[];
  collaborationPreview?: AnyRecord | null;
  gitSyncPreview?: AnyRecord | null;
  gitRollbackPreview?: AnyRecord | null;
  members?: AnyRecord[];
  currentUser?: AnyRecord | null;
  teamNotice?: string;
  teamError?: string;
  collaborationAuthBlocked?: boolean;
  initialPanelView?: PanelView;
  initialNpcCreateSubview?: NpcCreateSubview;
  initialPanelOpen?: boolean;
  initialExchangeSectionId?: string;
  initialExchangeComposerMode?: ExchangeComposerMode | null;
  initialHumanPartyFocusId?: string;
  initialComputerFocusId?: string;
  initialModeId?: string;
  initialSeatFocusId?: string;
  initialManagerDrawerKind?: ManagerDrawerKind;
  initialManagerDrawerId?: string;
  initialBindThreadId?: string;
  initialBindNodeId?: string;
  initialNpcName?: string;
  initialNpcResponsibility?: string;
  skillReturnTo?: string;
  pairingNodeId?: string;
  pairingToken?: string;
  computerConnectServerUrl?: string;
  workstationTokenId?: string;
  workstationToken?: string;
  [key: string]: unknown;
};

type FeedItem = {
  id: string;
  title: string;
  route: string;
  target: string;
  body: string;
  meta: string;
  ackLabel: string;
  progressLabel: string;
  replyOwnerLabel: string;
  finalReplyAt: number;
};

type RelayFeedItem = {
  id: string;
  title: string;
  body: string;
  meta: string;
  at: number;
};

type GitPreflightFeedItem = {
  id: string;
  title: string;
  runnerId: string;
  runnerLabel: string;
  messageType: string;
  status: string;
  statusLabel: string;
  action: string;
  actionLabel: string;
  repositoryUrl: string;
  branch: string;
  targetRef: string;
  credentialSource: string;
  credentialRef: string;
  gitVersion: string;
  ok: boolean | null;
  blockers: string[];
  warnings: string[];
  summary: string;
  updatedAt: string;
  ageMinutes: number | null;
  attentionLevel: "ok" | "warning" | "critical";
};

type CodexInboxFeedItem = {
  id: string;
  title: string;
  target: string;
  body: string;
  meta: string;
  statusLabel: string;
  sourceStatus: string;
  queueLabel: string;
  queueStartedAtLabel: string | null;
  queueAgeLabel: string | null;
  queueStateLabel: string | null;
  createdAt: number;
  requirementId: string | null;
  workstationId: string | null;
  workstationName: string | null;
  providerLabel: string | null;
  computerNodeLabel: string | null;
  skillLoadout: string[];
  repoSummary: string | null;
  referenceSummary: string | null;
  isQueued: boolean;
};

type CooperationProofItem = {
  id: string;
  title: string;
  target: string;
  routeKeys: string[];
  body: string;
  meta: string;
  requirementId: string;
  dispatchLabel: string;
  progressLabel: string;
  finalLabel: string;
  evidenceLabel: string;
  contextLabel: string | null;
  providerLabel: string | null;
  computerNodeLabel: string | null;
  skillLoadout: string[];
  repoSummary: string | null;
  referenceSummary: string | null;
  protectedDataHidden: boolean;
  latestAt: number;
  hasRouteLock: boolean;
  hasVisibleDispatch: boolean;
  hasDispatchProof: boolean;
  hasProgressSignal: boolean;
  hasFinalReply: boolean;
  usedConfigFallback: boolean;
};

type CooperationProofSummary = {
  foldSummary: string;
  title: string;
  body: string;
  meta: string;
};

type SeatAcceptanceSummary = {
  foldSummary: string;
  title: string;
  body: string;
  meta: string;
  nextStepLabel: string;
  nextStepDetail: string;
};

type MapSeatSkill = {
  id: string;
  label: string;
};

type MapSeatTask = {
  title: string;
  status: string;
  review: string;
};

type MapSeatPayload = {
  id: string;
  name: string;
  role: string;
  status: string;
  providerId: string;
  providerLabel: string;
  automationEnabled: boolean;
  heartbeatIntervalSeconds: number;
  scene: string;
  x: number | null;
  y: number | null;
  avatar: string;
  description: string;
  sourceThreadId: string;
  nodeName: string;
  executionModel: string;
  developmentStationId: string;
  developmentStationLabel: string;
  skillLoadout: string[];
  skillLabels: MapSeatSkill[];
  knowledgeKey: string;
  knowledgeTitle: string;
  knowledgeSummary: string;
  knowledgeHandoffPath: string;
  knowledgeHighlights: string[];
  knowledgeUpdatedAt: string | null;
  knowledgeDocExists: boolean;
  protocolWorkKind: string;
  protocolApprovalPolicy: string;
  protocolProjectProfile: string;
  protocolCapabilities: string[];
  protocolReferences: string[];
  protocolRepoSummary: string;
  protocolTokenSummary: string;
  protocolRunawaySummary: string;
  protocolEfficiencySummary: string;
  protocolDebugSummary: string;
  protocolMaxAutoRounds: number;
  protocolHumanReviewAfterRounds: number;
  protocolParallelismLimit: number;
  protocolSimulationFirst: boolean;
  protocolHardwareWriteRequiresReview: boolean;
  autonomyBridgeLabel: string;
  autonomyReady: boolean;
  supportsLocalAutonomyBridge: boolean;
  consumerScriptPath: string | null;
  consumerScriptExists: boolean;
  consumerStatePath: string | null;
  consumerStateExists: boolean;
  consumerStateUpdatedAt: string | null;
  consumerStateAgeMinutes: number | null;
  consumerStateStale: boolean;
  heartbeatAutomationId: string | null;
  heartbeatStatus: string | null;
  heartbeatUpdatedAt: string | null;
  heartbeatMissing: boolean;
  lastSelectedRequirementId: string | null;
  lastSelectedAt: string | null;
  lastPlatformFetchRequirementId: string | null;
  lastPlatformFetchAt: string | null;
  gitBoundary: string[];
  currentRequirement: string | null;
  currentRequirementId: string | null;
  currentRequirementStatus: string | null;
  recentTasks: MapSeatTask[];
  minimalAck: string | null;
  minimalAckAt: string | null;
  minimalAckType: string | null;
  legacyProgressSignal: boolean;
  finalReply: string | null;
  finalReplyAt: string | null;
  progressLagMinutes: number | null;
  staleAfterAck: boolean;
  staleAfterAckMinutes: number | null;
  progressHealthLabel: string;
  progressWarningLabel: string | null;
  selectionRecovered: boolean;
  autonomyDecision: string;
  reviewState: string;
  approvalState: string;
  lastSignalAt: string | null;
  provisioningState: string;
  provisioningLabel: string;
  provisioningDetail: string;
  provisioningNeeds: string[];
};

type MapCollaboratorWaypoint = {
  x: number;
  y: number;
};

type MapCollaboratorPayload = {
  id: string;
  name: string;
  role: string;
  ownership: string;
  scene: string;
  path: MapCollaboratorWaypoint[];
  isCurrentPlayer: boolean;
  accountPresenceState: string;
  accountPresenceLabel: string;
  accountPresenceAgeSeconds: number | null;
  projectPresenceState: string;
  projectPresenceLabel: string;
  projectPresenceAgeSeconds: number | null;
  lastProjectPath: string;
};

type HumanPartyHudEntry = {
  id: string;
  name: string;
  role: string;
  ownership: string;
  scene: string;
  isCurrentPlayer: boolean;
  identityLabel: string;
  stateLabel: string;
  stateTone: "active" | "review" | "blocked" | "idle";
  stateHint: string;
  detail: string;
  routeKeys: string[];
  computerCount: number;
  onlineComputerCount: number;
  threadCount: number;
  accountPresenceState: string;
  accountPresenceLabel: string;
  accountPresenceAgeLabel: string | null;
  projectPresenceState: string;
  projectPresenceLabel: string;
  projectPresenceAgeLabel: string | null;
  lastProjectPath: string;
};

type ComputerFleetGroup = {
  id: string;
  name: string;
  identityLabel: string;
  isCurrentPlayer: boolean;
  stateLabel: string;
  computerCount: number;
  onlineComputerCount: number;
  threadCount: number;
  routeKeys: string[];
  computers: AnyRecord[];
};

type StarterDrawerStep = {
  id: string;
  title: string;
  detail: string;
  done: boolean;
};

type StarterDrawerModel = {
  title: string;
  summary: string;
  hint: string;
  statusLabel: string;
  ctaLabel: string;
  ctaPanel: PanelView;
  ctaSeatId: string | null;
  ctaHref: string | null;
  secondaryLabel: string;
  secondaryPanel: PanelView;
  secondarySeatId: string | null;
  secondaryHref: string | null;
  steps: StarterDrawerStep[];
};

type PanelDefinition = {
  id: PanelView;
  label: string;
  icon: string;
  layer: "primary" | "setup" | "advanced";
  detail: string;
};

type ModeEntry = {
  id: string;
  label: string;
  state: string;
  detail: string;
  active: boolean;
  readinessLabel: string;
  readinessDetail: string;
  blockerLabel: string;
  blockerDetail: string;
  nextLabel: string;
  nextDetail: string;
  signals: string[];
  routeRuleLabel: string;
  routeRuleDetail: string;
  entrySteps: {
    label: string;
    status: string;
    detail: string;
    href: string | null;
    routeHint: string;
    layerKind: string;
    branchState: string;
  }[];
  layers: {
    label: string;
    status: string;
    detail: string;
  }[];
  actions: {
    label: string;
    href: string | null;
    panel: PanelView | null;
    seatId: string | null;
    emphasis: "primary" | "ghost";
  }[];
};

type ModeEntryStep = ModeEntry["entrySteps"][number];
type ModeEntryAction = ModeEntry["actions"][number];

const PANEL_DEFINITIONS: PanelDefinition[] = [
  { id: "development-workshop", label: "开发工坊", icon: "工", layer: "primary", detail: "把项目生成、环境搭建、连线选型、调试、AI 教练和仿真串成一条开发链。" },
  { id: "human-party", label: "主角管理", icon: "主", layer: "primary", detail: "按项目成员管理主角、名下电脑、线程和协作状态，不再把整列主角卡长期压在地图右边。" },
  { id: "npc-create", label: "NPC 管理", icon: "N", layer: "primary", detail: "NPC 角色栏、对话框、任务、能力包装配、知识库和线程绑定。" },
  { id: "computers", label: "电脑接入", icon: "电", layer: "primary", detail: "接入真实电脑，查看电脑属性和这台电脑上的 Codex、Claude、Qwen 线程。" },
    { id: "skills", label: "能力包仓库", icon: "技", layer: "primary", detail: "维护 Skill 中文名、说明和适用职业；NPC 从这里索引装配。" },
    { id: "schedule", label: "日程 DDL", icon: "历", layer: "primary", detail: "在主房日历编辑任务 DDL、每日安排，并让 AI 给出当日执行顺序。" },
    { id: "serial-tv", label: "设备调试台", icon: "波", layer: "setup", detail: "扫描各电脑 USB/CAN/串口设备，做串口收发和数字波形调试。" },
    { id: "ai-debug", label: "AI 调试", icon: "调", layer: "setup", detail: "调试 AI 协作行为、token 预算、跑飞保护、最小回执和最终回复，不直接动真实硬件。" },
    { id: "ai-simulation", label: "AI 仿真", icon: "仿", layer: "setup", detail: "机器人和纯软件任务先进入仿真/沙盘视角，确认风险边界后再派真实线程执行。" },
    { id: "exchange", label: "协作消息池", icon: "讯", layer: "setup", detail: "查看跨 NPC、跨线程的统一派单、最小回执和最终回复。" },
  { id: "machine-room", label: "线程调试", icon: "线", layer: "setup", detail: "确认 Codex、Claude 等真实线程是否可用。" },
  { id: "git", label: "Git 回退", icon: "Git", layer: "primary", detail: "固定仓库来源、同步约束和可视化回退入口。" },
];

const MAIN_CONTROL_PANEL_IDS: PanelView[] = [
  "development-workshop",
  "human-party",
  "npc-create",
  "computers",
  "machine-room",
  "skills",
  "git",
  "schedule",
];

const PLATFORM_SEAT_KEY = "farm-platform-codex-seats-v1";
const PLATFORM_SEAT_FOCUS_KEY = "farm-platform-seat-focus-v1";
const PLATFORM_FOCUS_RAIL_KEY = "farm-platform-focus-rail-open-v2";
const PLATFORM_COLLABORATOR_KEY = "farm-platform-collaborators-v1";
const PLATFORM_CURRENT_PLAYER_KEY = "farm-platform-current-player-v1";
const FARM_OPEN_NPC_SEAT_EVENT = "farm-open-npc-seat";
const FARM_FOCUS_NPC_SEAT_EVENT = "farm-focus-npc-seat";
const FARM_OPEN_SCHEDULE_EVENT = "farm-open-schedule";
const FARM_OPEN_SERIAL_TV_EVENT = "farm-open-serial-tv";
const FARM_OPEN_DEVELOPMENT_WORKSHOP_EVENT = "farm-open-development-workshop";

const DEVELOPMENT_STATION_CREATE_DRAWER_ID = "__create-development-station__";

const SKILL_CATEGORY_LABELS: Record<string, string> = {
  academic: "学术",
  baseline: "固定必备",
  custom: "项目自定义",
  design: "设计",
  engineering: "工程",
  external: "外部导入",
  finance: "财务",
  "game-development": "游戏开发",
  integrations: "集成",
  marketing: "营销",
  "paid-media": "广告投放",
  product: "产品",
  "project-management": "项目管理",
  sales: "销售",
  specialized: "专项",
  "spatial-computing": "空间计算",
  support: "支持",
  testing: "测试",
};

type SkillIntroProfile = {
  terms: string[];
  title: string;
  focus: string;
  scene: string;
  stations: string[];
  deliverables: string[];
};

const SKILL_INTRO_PROFILES: SkillIntroProfile[] = [
  {
    terms: ["frontend", "react", "vue", "angular", "next.js", "nextjs", "css", "tailwind", "design system", "web ui"],
    title: "前端开发与界面实现位",
    focus: "页面结构、组件拆分、交互实现、样式收口和性能优化",
    scene: "常用于 Web 前台、后台控制台、活动页或工具界面，适合接 UI 落地、可访问性修补和多端适配任务",
    stations: ["前端工位", "App 工位", "项目生成器工位"],
    deliverables: ["页面框架草图", "组件拆分清单", "交互实现结果", "性能优化记录"],
  },
  {
    terms: ["backend", "api", "server", "graphql", "rest", "database", "postgres", "sql", "microservice", "orm"],
    title: "后端与接口实现位",
    focus: "接口定义、数据流转、权限链路、稳定性和性能收口",
    scene: "常用于服务端模块、业务流程编排和数据落库场景，适合接 API 设计、权限控制和瓶颈排查任务",
    stations: ["后端工位", "数据接口工位", "项目生成器工位"],
    deliverables: ["接口清单", "数据模型说明", "权限链路记录", "服务端变更结果"],
  },
  {
    terms: ["embedded", "firmware", "esp32", "stm32", "arduino", "uart", "serial", "rtos", "driver", "i2c", "spi", "bring-up", "pcb"],
    title: "嵌入式固件与板级联调位",
    focus: "板级 bring-up、固件实现、串口联调、驱动排错和外设接线",
    scene: "常用于 MCU、开发板和现场设备调试，适合接底层通信、驱动问题复现和硬件联调任务",
    stations: ["NanoPi 工位", "嵌入式工位", "串口调试工位"],
    deliverables: ["固件版本说明", "外设接线表", "串口调试记录", "驱动问题复盘"],
  },
  {
    terms: ["qa", "quality assurance", "testing", "test engineer", "playwright", "cypress", "regression", "validator", "reviewer"],
    title: "测试与质量保障位",
    focus: "用例补齐、回归验证、缺陷定位、证据整理和验收把关",
    scene: "常用于发版前后和需求收口阶段，适合接自动化补测、问题复现和质量门禁任务",
    stations: ["测试工位", "验收工位", "项目生成器工位"],
    deliverables: ["测试用例清单", "回归结果", "缺陷证据截图", "验收结论"],
  },
  {
    terms: ["game", "unity", "unreal", "godot", "phaser", "multiplayer", "quest", "combat", "npc", "level design"],
    title: "游戏系统与玩法实现位",
    focus: "玩法系统、场景互动、任务循环、多人协作逻辑和体验迭代",
    scene: "常用于关卡、数值、交互系统或工具链开发，适合接原型搭建、玩法收口和玩家体验调优任务",
    stations: ["游戏玩法工位", "关卡工位", "NPC 交互工位"],
    deliverables: ["玩法方案草稿", "系统实现结果", "场景交互说明", "体验迭代清单"],
  },
  {
    terms: ["ui designer", "ux", "figma", "visual designer", "product designer", "interaction design", "wireframe", "prototype"],
    title: "视觉与交互设计位",
    focus: "信息层级、交互路径、组件规范、视觉风格和可用性优化",
    scene: "常用于新功能立项或旧界面重构，适合接页面框架、组件语言和体验统一任务",
    stations: ["设计工位", "前端工位", "项目生成器工位"],
    deliverables: ["界面线框", "交互稿", "视觉规范", "组件风格建议"],
  },
  {
    terms: ["product manager", "product strategist", "roadmap", "prioritization", "requirements", "prd", "backlog"],
    title: "产品拆解与范围收口位",
    focus: "需求梳理、优先级排序、范围边界、验收口和角色对齐",
    scene: "常用于需求起草和复杂协作链路前置整理，适合接 PRD、拆分方案和节奏定义任务",
    stations: ["产品工位", "项目生成器工位", "需求拆解工位"],
    deliverables: ["需求拆解文档", "优先级列表", "验收口清单", "范围说明"],
  },
  {
    terms: ["project manager", "program manager", "scrum", "delivery manager", "producer", "coordinator"],
    title: "项目推进与节奏协调位",
    focus: "排期维护、依赖协调、阻塞跟踪、交付节奏和跨角色同步",
    scene: "常用于多人并行项目推进，适合接任务编排、状态跟进和交接收口任务",
    stations: ["项目管理工位", "协作调度工位", "交付工位"],
    deliverables: ["排期版", "阻塞清单", "交付状态汇总", "交接记录"],
  },
  {
    terms: ["devops", "sre", "platform engineer", "cloud", "deployment", "infra", "infrastructure", "ci/cd", "kubernetes", "docker", "terraform", "observability"],
    title: "环境与发布稳定性位",
    focus: "环境编排、持续集成、部署脚本、监控告警和线上稳定性",
    scene: "常用于发布链路和平台底座建设，适合接自动化部署、故障排查和运行保障任务",
    stations: ["运维工位", "发布工位", "机房工位"],
    deliverables: ["部署脚本", "发布步骤单", "监控告警配置", "故障排查记录"],
  },
  {
    terms: ["marketing", "seo", "geo", "aeo", "citation", "growth", "brand", "paid media", "ads", "content marketing", "social"],
    title: "增长与内容传播位",
    focus: "内容策略、搜索曝光、渠道节奏、投放试验和品牌表达",
    scene: "常用于拉新和转化场景，适合接内容计划、投放优化和传播口径统一任务",
    stations: ["营销工位", "内容工位", "投放工位"],
    deliverables: ["内容计划", "渠道投放建议", "增长观察记录", "品牌口径稿"],
  },
  {
    terms: ["sales", "account executive", "business development", "deal", "pipeline", "discovery", "customer success"],
    title: "销售推进与客户沟通位",
    focus: "线索推进、需求发现、方案表达、异议处理和成交节奏",
    scene: "常用于商机跟进和客户协同，适合接线索分层、方案沟通和转化推进任务",
    stations: ["销售工位", "客户沟通工位", "方案演示工位"],
    deliverables: ["客户需求摘要", "跟进节奏表", "方案讲解稿", "成交推进记录"],
  },
  {
    terms: ["support", "helpdesk", "incident", "triage", "customer support", "service desk"],
    title: "客户支持与问题闭环位",
    focus: "问题分诊、状态同步、反馈整理、经验沉淀和用户沟通",
    scene: "常用于用户问题响应和售后流程，适合接工单跟踪、知识库补充和高频问题收口任务",
    stations: ["支持工位", "客服工位", "问题闭环工位"],
    deliverables: ["问题分诊单", "用户回复稿", "知识库补充", "高频问题归档"],
  },
  {
    terms: ["finance", "accounts payable", "accounting", "bookkeep", "invoice", "payroll", "reconciliation"],
    title: "财务流转与对账位",
    focus: "费用记录、账务核对、付款流程、风险留痕和周期复盘",
    scene: "常用于发票、付款和预算管理流程，适合接对账检查、台账整理和财务异常排查任务",
    stations: ["财务工位", "对账工位", "付款流转工位"],
    deliverables: ["对账清单", "付款记录", "费用台账", "财务风险备注"],
  },
  {
    terms: ["integration", "mcp", "identity", "oauth", "sso", "auth", "connector", "protocol", "interoperability", "trust", "compliance", "security"],
    title: "系统接线与权限边界位",
    focus: "协议适配、身份鉴权、连接器排错、权限边界和跨平台联调",
    scene: "常用于多系统串联和平台接入场景，适合接协议对齐、认证链路和异常排查任务",
    stations: ["系统接线工位", "权限工位", "机房工位"],
    deliverables: ["接入说明", "权限映射表", "接口调试记录", "异常排查结论"],
  },
  {
    terms: ["writer", "writing", "editor", "documentation", "technical writer", "curriculum", "tutorial", "education", "copywriter", "content designer"],
    title: "内容写作与知识表达位",
    focus: "结构化表达、文案打磨、教程串联、知识沉淀和口径统一",
    scene: "常用于教程、文档、脚本和叙事表达，适合接内容改写、资料整理和输出包装任务",
    stations: ["文档工位", "教育工位", "内容工位"],
    deliverables: ["文档草稿", "教程步骤说明", "知识摘要", "对外文案"],
  },
  {
    terms: ["anthropolog", "geograph", "historian", "narratolog", "psycholog", "research", "researcher", "analyst", "academic", "scientist"],
    title: "研究分析与证据整理位",
    focus: "资料检索、概念梳理、证据整理、结构建模和结论解释",
    scene: "常用于陌生领域调研和高信息密度问题拆解，适合接研究综述、比较分析和结构化输出任务",
    stations: ["研究工位", "资料分析工位", "知识库工位"],
    deliverables: ["研究摘要", "证据清单", "比较分析结果", "结构化结论"],
  },
  {
    terms: ["spatial", "3d", "xr", "ar", "vr", "computer vision", "scene", "three.js", "threejs", "vision"],
    title: "3D 与空间交互实现位",
    focus: "场景组织、交互路径、坐标数据处理、设备体验和表现收口",
    scene: "常用于三维展示、空间计算和设备感知场景，适合接 3D 交互、坐标映射和体验验证任务",
    stations: ["3D 工位", "空间交互工位", "视觉调试工位"],
    deliverables: ["场景搭建结果", "坐标映射说明", "交互验证记录", "设备体验反馈"],
  },
];

const SKILL_CATEGORY_INTRO_DEFAULTS: Record<string, Omit<SkillIntroProfile, "terms">> = {
  academic: {
    title: "研究分析位",
    focus: "资料梳理、概念建模、证据整理和结论解释",
    scene: "适合接陌生领域研究、综述整理和高信息密度输出任务",
    stations: ["研究工位", "知识库工位"],
    deliverables: ["研究摘要", "资料清单", "结构化结论"],
  },
  baseline: {
    title: "平台固定基础能力位",
    focus: "通用协作动作、基础流程纪律和稳定性守门",
    scene: "适合做所有 NPC 都应该具备的底座能力，不建议当成单独职业分工",
    stations: ["基础能力工位", "协作底座工位"],
    deliverables: ["基础流程动作", "协作规范记录", "稳定性检查结果"],
  },
  custom: {
    title: "项目自定义协作位",
    focus: "围绕当前项目场景承接明确任务口、流程口和交付口",
    scene: "适合按你的项目需要继续细化职责、工位和具体执行方式",
    stations: ["项目自定义工位", "协作调度工位"],
    deliverables: ["项目定制方案", "协作动作说明", "交付结果摘要"],
  },
  design: {
    title: "设计协作位",
    focus: "信息层级、视觉风格、交互路径和组件统一",
    scene: "适合接页面重构、视觉规范和体验优化任务",
    stations: ["设计工位", "前端工位"],
    deliverables: ["界面草图", "视觉规范", "体验建议"],
  },
  engineering: {
    title: "工程实现位",
    focus: "功能实现、联调排错、性能收口和交付整理",
    scene: "适合接具体模块、接口或工具链开发任务",
    stations: ["开发工位", "项目生成器工位"],
    deliverables: ["实现结果", "联调记录", "交付清单"],
  },
  external: {
    title: "外部引入职业位",
    focus: "承接外部角色能力、补齐专业分工和细化协作链路",
    scene: "适合从外部 skill 包快速引入新职业并挂到工位里实战",
    stations: ["项目生成器工位", "协作调度工位"],
    deliverables: ["角色说明", "交付模板", "协作建议"],
  },
  finance: {
    title: "财务协作位",
    focus: "费用记录、对账校验、付款跟踪和风险留痕",
    scene: "适合接账务流转、预算检查和周期复盘任务",
    stations: ["财务工位", "对账工位"],
    deliverables: ["对账清单", "费用台账", "付款记录"],
  },
  "game-development": {
    title: "游戏开发位",
    focus: "玩法系统、场景互动、任务循环和体验调优",
    scene: "适合接玩法原型、界面互动和系统迭代任务",
    stations: ["游戏玩法工位", "NPC 交互工位"],
    deliverables: ["玩法方案", "交互说明", "迭代清单"],
  },
  integrations: {
    title: "集成接线位",
    focus: "系统互联、协议适配、数据同步和异常排查",
    scene: "适合接平台接入、接口编排和跨系统联调任务",
    stations: ["系统接线工位", "机房工位"],
    deliverables: ["接入说明", "调试记录", "同步结果"],
  },
  marketing: {
    title: "营销传播位",
    focus: "内容方向、渠道节奏、曝光增长和品牌表达",
    scene: "适合接内容策略、传播动作和转化观察任务",
    stations: ["营销工位", "内容工位"],
    deliverables: ["内容计划", "传播建议", "转化观察"],
  },
  "paid-media": {
    title: "广告投放位",
    focus: "投放策略、预算节奏、素材测试和效果归因",
    scene: "适合接广告投放、素材实验和转化优化任务",
    stations: ["投放工位", "营销工位"],
    deliverables: ["投放方案", "素材实验记录", "效果归因结论"],
  },
  product: {
    title: "产品规划位",
    focus: "需求拆解、范围边界、优先级和验收标准",
    scene: "适合接需求定义、方案对齐和里程碑收口任务",
    stations: ["产品工位", "需求拆解工位"],
    deliverables: ["需求说明", "优先级列表", "验收口定义"],
  },
  "project-management": {
    title: "项目管理位",
    focus: "节奏推进、依赖协调、阻塞跟踪和交接同步",
    scene: "适合接多人协作排期、状态维护和项目推进任务",
    stations: ["项目管理工位", "协作调度工位"],
    deliverables: ["排期版", "阻塞清单", "交付状态"],
  },
  sales: {
    title: "销售协作位",
    focus: "线索推进、沟通策略、成交节奏和客户跟进",
    scene: "适合接商机发现、客户沟通和转化推进任务",
    stations: ["销售工位", "客户沟通工位"],
    deliverables: ["需求摘要", "跟进记录", "方案讲解稿"],
  },
  specialized: {
    title: "专项问题处理位",
    focus: "专项域判断、方案设计、风险识别和跨角色协作",
    scene: "适合承接需要专业视角的复杂问题和关键决策任务",
    stations: ["专项工位", "研究工位"],
    deliverables: ["专项判断结果", "方案建议", "风险提示"],
  },
  "spatial-computing": {
    title: "空间计算位",
    focus: "空间交互、坐标处理、三维表现和设备体验",
    scene: "适合接 3D 场景、感知交互和空间映射任务",
    stations: ["3D 工位", "空间交互工位"],
    deliverables: ["场景说明", "坐标结果", "体验反馈"],
  },
  support: {
    title: "支持服务位",
    focus: "问题响应、反馈归档、状态同步和经验沉淀",
    scene: "适合接售后、工单和使用问题闭环任务",
    stations: ["支持工位", "问题闭环工位"],
    deliverables: ["问题分诊单", "回复稿", "知识库补充"],
  },
  testing: {
    title: "测试验收位",
    focus: "回归验证、缺陷复现、证据整理和质量守门",
    scene: "适合接发版前后验收、问题复现和自动化补测任务",
    stations: ["测试工位", "验收工位"],
    deliverables: ["测试结论", "缺陷证据", "回归结果"],
  },
};

function displaySkillCategory(category: string) {
  return SKILL_CATEGORY_LABELS[category] ?? category;
}

function resolveSkillMetadata(skill: AnyRecord | null | undefined) {
  return skill?.metadata && typeof skill.metadata === "object" ? (skill.metadata as AnyRecord) : {};
}

function resolveSkillCategory(skill: AnyRecord | null | undefined) {
  const metadata = resolveSkillMetadata(skill);
  if (text(metadata.category, "")) return text(metadata.category, "");
  if (isBaselineSkill(skill ?? {})) return "baseline";
  if (text(skill?.source, "") === "agency-agents") return "external";
  return "custom";
}

function hasCjkText(value: string) {
  return /[\u3400-\u9fff]/u.test(value);
}

function normalizeSkillKeywordBlob(skill: AnyRecord | null | undefined) {
  const metadata = resolveSkillMetadata(skill);
  const explicitMatchingText = text(metadata.matching_text ?? metadata.keyword_blob, "");
  if (explicitMatchingText) {
    return explicitMatchingText.trim().toLowerCase();
  }
  const parts = [
    text(skill?.id, ""),
    text(skill?.label, ""),
    text(skill?.note, ""),
    text(metadata.name, ""),
    text(metadata.description, ""),
    text(metadata.external_path, ""),
    ...asArray(skill?.recommended_for).slice(0, 18).map((item) => text(item)),
  ];
  return parts
    .join(" ")
    .trim()
    .toLowerCase();
}

function resolveSkillProfile(skill: AnyRecord | null | undefined) {
  if (!skill) return SKILL_CATEGORY_INTRO_DEFAULTS.custom;
  const category = resolveSkillCategory(skill);
  const blob = normalizeSkillKeywordBlob(skill);
  const matchedProfile = SKILL_INTRO_PROFILES.find((profile) =>
    profile.terms.some((term) => blob.includes(term.toLowerCase())),
  );
  return matchedProfile ?? SKILL_CATEGORY_INTRO_DEFAULTS[category] ?? SKILL_CATEGORY_INTRO_DEFAULTS.custom;
}

function resolveGeneratedSkillIntro(skill: AnyRecord | null | undefined) {
  if (!skill) return "";
  const profile = resolveSkillProfile(skill);
  return `适合担任${profile.title}，重点负责${profile.focus}。${profile.scene}。`;
}

function resolveSkillFitStations(skill: AnyRecord | null | undefined) {
  if (!skill) return [];
  const metadata = resolveSkillMetadata(skill);
  const metadataStations = asArray(metadata.preferred_stations ?? metadata.fit_stations ?? metadata.stations)
    .map((item) => text(item))
    .filter((item) => item && hasCjkText(item));
  if (metadataStations.length) return uniqueStrings(metadataStations);
  return uniqueStrings(resolveSkillProfile(skill).stations);
}

function resolveSkillDeliverables(skill: AnyRecord | null | undefined) {
  if (!skill) return [];
  const metadata = resolveSkillMetadata(skill);
  const metadataDeliverables = asArray(metadata.deliverables ?? metadata.common_outputs ?? metadata.technical_deliverables)
    .map((item) => text(item))
    .filter((item) => item && hasCjkText(item));
  if (metadataDeliverables.length) return uniqueStrings(metadataDeliverables);
  return uniqueStrings(resolveSkillProfile(skill).deliverables);
}

function resolveSkillIntro(skill: AnyRecord | null | undefined) {
  const metadata = resolveSkillMetadata(skill);
  const rawIntro = text(metadata.description ?? skill?.note ?? metadata.name, text(skill?.note, ""));
  if (rawIntro && hasCjkText(rawIntro)) return rawIntro;
  const generatedIntro = resolveGeneratedSkillIntro(skill);
  return generatedIntro || rawIntro || "暂无说明";
}

function resolveSkillVibe(skill: AnyRecord | null | undefined) {
  const metadata = resolveSkillMetadata(skill);
  return text(metadata.vibe, "");
}

function resolveSkillSourceLabel(skill: AnyRecord | null | undefined) {
  const source = text(skill?.source, "custom");
  const categoryLabel = displaySkillCategory(resolveSkillCategory(skill));
  if (source === "agency-agents") return `Agency Agents / ${categoryLabel}`;
  if (source === "github") return `GitHub / ${categoryLabel}`;
  if (isBaselineSkill(skill ?? {})) return `平台固定 Skill / ${categoryLabel}`;
  return `项目 Skill / ${categoryLabel}`;
}

function resolveSkillSectionPreview(skill: AnyRecord | null | undefined) {
  const metadata = resolveSkillMetadata(skill);
  const sectionDefs: Array<{ key: string; label: string }> = [
    { key: "core_mission", label: "核心使命" },
    { key: "critical_rules", label: "关键规则" },
    { key: "workflow_process", label: "工作流程" },
    { key: "technical_deliverables", label: "交付物" },
  ];
  return sectionDefs
    .map((section) => ({
      label: section.label,
      items: asArray(metadata[section.key])
        .map((item) => text(item))
        .filter(Boolean)
        .slice(0, 2),
    }))
    .filter((section) => section.items.length);
}

function buildSkillCategorySummary(skills: AnyRecord[]) {
  const categoryMap = new Map<
    string,
    {
      id: string;
      label: string;
      count: number;
      sampleLabels: string[];
    }
  >();
  skills.forEach((skill) => {
    const categoryId = resolveSkillCategory(skill);
    const existing =
      categoryMap.get(categoryId) ?? {
        id: categoryId,
        label: displaySkillCategory(categoryId),
        count: 0,
        sampleLabels: [],
      };
    existing.count += 1;
    if (existing.sampleLabels.length < 3) {
      existing.sampleLabels.push(text(skill.label, text(skill.id)));
    }
    categoryMap.set(categoryId, existing);
  });
  return Array.from(categoryMap.values()).sort(
    (left, right) => right.count - left.count || left.label.localeCompare(right.label, "zh-CN"),
  );
}

function resolveSkillSourceBucket(skill: AnyRecord | null | undefined) {
  const source = text(skill?.source, "custom");
  if (source === "agency-agents") return "agency-agents";
  if (source === "platform-role") return "platform-role";
  if (source === "platform-baseline") return "platform-baseline";
  if (source === "custom") return "custom";
  return source || "custom";
}

function displaySkillSourceBucket(source: string) {
  switch (source) {
    case "agency-agents":
      return "Agency Agents";
    case "platform-role":
      return "平台角色";
    case "platform-baseline":
      return "平台固定";
    case "custom":
      return "项目自定义";
    default:
      return source;
  }
}

function buildSkillSourceSummary(skills: AnyRecord[]) {
  const sourceMap = new Map<
    string,
    {
      id: string;
      label: string;
      count: number;
    }
  >();
  skills.forEach((skill) => {
    const sourceId = resolveSkillSourceBucket(skill);
    const existing =
      sourceMap.get(sourceId) ?? {
        id: sourceId,
        label: displaySkillSourceBucket(sourceId),
        count: 0,
      };
    existing.count += 1;
    sourceMap.set(sourceId, existing);
  });
  return Array.from(sourceMap.values()).sort(
    (left, right) => right.count - left.count || left.label.localeCompare(right.label, "zh-CN"),
  );
}

function matchesSkillLoadoutFilters(
  skill: AnyRecord,
  options: {
    query?: string;
    category?: string;
    source?: string;
  },
) {
  const query = text(options.query, "").trim().toLowerCase();
  const category = text(options.category, "all");
  const source = text(options.source, "all");
  if (category !== "all" && resolveSkillCategory(skill) !== category) return false;
  if (source !== "all" && resolveSkillSourceBucket(skill) !== source) return false;
  if (!query) return true;
  const metadata = resolveSkillMetadata(skill);
  const haystack = [
    text(skill.id),
    text(skill.label),
    text(skill.note),
    text(skill.source),
    text(metadata.description),
    text(metadata.vibe),
    text(metadata.external_path),
    resolveSkillCategory(skill),
    displaySkillCategory(resolveSkillCategory(skill)),
    resolveSkillSourceBucket(skill),
    displaySkillSourceBucket(resolveSkillSourceBucket(skill)),
    asArray(skill.recommended_for).map((item) => text(item)).join(" "),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

type NpcSkillFilterPreset = {
  id: string;
  label: string;
  query?: string;
  category?: string;
  source?: string;
  hint: string;
};

const NPC_SKILL_FILTER_PRESETS: NpcSkillFilterPreset[] = [
  {
    id: "frontend",
    label: "前端",
    query: "frontend",
    category: "engineering",
    source: "agency-agents",
    hint: "筛页面、组件、交互类职业 Skill。",
  },
  {
    id: "embedded",
    label: "嵌入式",
    query: "embedded",
    category: "engineering",
    source: "agency-agents",
    hint: "筛固件、板级联调、驱动类职业 Skill。",
  },
  {
    id: "testing",
    label: "测试",
    category: "testing",
    source: "all",
    hint: "筛 QA、接口验证、回归验收类职业 Skill。",
  },
  {
    id: "game-development",
    label: "游戏开发",
    category: "game-development",
    source: "agency-agents",
    hint: "筛玩法、关卡、游戏界面协作类职业 Skill。",
  },
];

type SkillImportBundlePreset = {
  id: string;
  label: string;
  hint: string;
  skillIds: string[];
};

const SKILL_IMPORT_BUNDLE_PRESETS: SkillImportBundlePreset[] = [
  {
    id: "frontend-starter",
    label: "前端首包",
    hint: "适合先拉一个会做页面、体验和小程序的前端协作组合。",
    skillIds: [
      "agency-frontend-developer",
      "agency-ui-designer",
      "agency-ux-researcher",
      "agency-wechat-mini-program-developer",
    ],
  },
  {
    id: "embedded-starter",
    label: "嵌入式首包",
    hint: "适合板级 bring-up、固件实现和基础验证。",
    skillIds: [
      "agency-embedded-firmware-engineer",
      "agency-api-tester",
      "agency-test-results-analyzer",
      "agency-devops-automator",
    ],
  },
  {
    id: "qa-starter",
    label: "QA 首包",
    hint: "适合回归、接口、结果分析和证据整理。",
    skillIds: [
      "agency-api-tester",
      "agency-test-results-analyzer",
      "agency-model-qa",
      "agency-evidence-collector",
    ],
  },
  {
    id: "game-starter",
    label: "游戏开发首包",
    hint: "适合玩法设计、Unity 联机和工具链协作。",
    skillIds: [
      "agency-game-designer",
      "agency-unity-multiplayer-engineer",
      "agency-unity-editor-tool-developer",
      "agency-ui-designer",
    ],
  },
];

function developmentStationMatchesNpc(station: DevelopmentWorkshopStation, seat: AnyRecord) {
  const metadata = seat?.metadata && typeof seat.metadata === "object" ? (seat.metadata as AnyRecord) : {};
  const stationId = text(
    metadata.development_station_id ??
      metadata.development_station?.id ??
      seat.developmentStationId ??
      seat.development_station_id,
    "",
  );
  if (stationId && stationId === station.id) return true;
  const haystack = [
    seat.name,
    seat.label,
    seat.role,
    seat.responsibility,
    seat.status,
    metadata.development_station_label,
    seat.developmentStationLabel,
    seat.development_station_label,
    metadata.responsibility,
    metadata.npc_knowledge?.summary,
    metadata.collab_protocol?.work_kind,
    metadata.collab_protocol?.required_capabilities,
  ]
    .flat()
    .map((item) => text(item, "").toLowerCase())
    .filter(Boolean)
    .join(" ");
  return station.assignmentKeywords.some((keyword) => haystack.includes(keyword.toLowerCase()));
}

function defaultNpcNameForDevelopmentStation(station: DevelopmentWorkshopStation | undefined) {
  if (!station) return "";
  const role = station.npcRoleTemplates[0] ?? "负责人";
  return `${station.label}${role}`;
}

function defaultNpcResponsibilityForDevelopmentStation(station: DevelopmentWorkshopStation | undefined) {
  if (!station) return "";
  const roles = station.npcRoleTemplates.join(" / ");
  return `${station.label}负责人：${roles}。负责 ${station.nextActions.join("；")}。`;
}

function buildSharedModeFrontDoorSteps(options: {
  reloginPath: string;
  projectPlazaPath: string;
  loginDetail: string;
  projectDetail: string;
}): ModeEntryStep[] {
  const { reloginPath, projectPlazaPath, loginDetail, projectDetail } = options;
  return [
    {
      label: "登录页",
      status: "已存在",
      detail: loginDetail,
      href: reloginPath,
      routeHint: "/login",
      layerKind: "路由层",
      branchState: "不分流",
    },
    {
      label: "项目管理入口页",
      status: "已存在",
      detail: projectDetail,
      href: projectPlazaPath,
      routeHint: "/projects",
      layerKind: "路由层",
      branchState: "当前不分流",
    },
  ];
}

function buildFutureModeTailSteps(options: {
  boardDetail: string;
  boardHref: string;
  shellLabel: string;
  shellDetail: string;
  shellHref: string;
}): ModeEntryStep[] {
  const { boardDetail, boardHref, shellLabel, shellDetail, shellHref } = options;
  return [
    {
      label: "模式选择页",
      status: "已占位",
      detail: boardDetail,
      href: boardHref,
      routeHint: boardHref,
      layerKind: "分流占位层",
      branchState: "当前占位分流点",
    },
    {
      label: shellLabel,
      status: "已占位",
      detail: shellDetail,
      href: shellHref,
      routeHint: shellHref,
      layerKind: "模式占位壳",
      branchState: "future shell",
    },
  ];
}

function buildFutureModeActions(options: {
  primaryLabel: string;
  primaryHref: string;
  boardHref: string;
}): ModeEntryAction[] {
  const { primaryLabel, primaryHref, boardHref } = options;
  return [
    {
      label: primaryLabel,
      href: primaryHref,
      panel: null,
      seatId: null,
      emphasis: "primary",
    },
    {
      label: "回当前项目分流页",
      href: boardHref,
      panel: null,
      seatId: null,
      emphasis: "ghost",
    },
  ];
}

function asArray(value: unknown): AnyRecord[] {
  return Array.isArray(value) ? (value as AnyRecord[]) : [];
}

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

const POSTER_NPC_AVATARS = [
  {
    src: "/assets/a-agent/npc-product.png",
    terms: ["product", "产品", "经理", "需求", "pm", "owner"],
  },
  {
    src: "/assets/a-agent/npc-frontend.png",
    terms: ["frontend", "front-end", "前端", "ui", "web", "react", "界面"],
  },
  {
    src: "/assets/a-agent/npc-backend.png",
    terms: ["backend", "后端", "api", "server", "服务", "工程"],
  },
  {
    src: "/assets/a-agent/npc-embedded.png",
    terms: ["embedded", "嵌入式", "硬件", "firmware", "mcu", "nanopi", "串口", "驱动"],
  },
  {
    src: "/assets/a-agent/npc-tester.png",
    terms: ["test", "qa", "测试", "验收", "verify", "review"],
  },
  {
    src: "/assets/a-agent/npc-designer.png",
    terms: ["design", "设计", "视觉", "交互", "ux"],
  },
  {
    src: "/assets/a-agent/npc-education.png",
    terms: ["education", "教育", "教程", "小白", "学习"],
  },
] as const;

function posterNpcAvatarForSeat(seat: AnyRecord, index = 0) {
  const haystack = [
    seat.name,
    seat.role,
    seat.status,
    seat.responsibility,
    seat.description,
    seat.metadata?.role,
    seat.metadata?.responsibility,
    seat.metadata?.summary,
  ]
    .map((value) => text(value, "").toLowerCase())
    .filter(Boolean)
    .join(" ");
  const matched = POSTER_NPC_AVATARS.find((avatar) => avatar.terms.some((term) => haystack.includes(term.toLowerCase())));
  return matched?.src ?? POSTER_NPC_AVATARS[index % POSTER_NPC_AVATARS.length]?.src ?? "/assets/a-agent/npc-education.png";
}

function booleanFromUnknown(value: unknown, fallback = false) {
  if (typeof value === "boolean") return value;
  const normalized = text(value, "").toLowerCase();
  if (!normalized) return fallback;
  return !["false", "0", "off", "no"].includes(normalized);
}

function parseJsonObjectFromText(value: unknown): AnyRecord | null {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  const fenced = raw.match(/```json\s*([\s\S]*?)```/i);
  const candidate = fenced?.[1]?.trim() || raw;
  try {
    const parsed = JSON.parse(candidate);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as AnyRecord) : null;
  } catch {
    const start = raw.indexOf("{");
    const end = raw.lastIndexOf("}");
    if (start >= 0 && end > start) {
      try {
        const parsed = JSON.parse(raw.slice(start, end + 1));
        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as AnyRecord) : null;
      } catch {
        return null;
      }
    }
  }
  return null;
}

function mergeSerialDeviceLists(...groups: AnyRecord[][]) {
  const seen = new Set<string>();
  const devices: AnyRecord[] = [];
  groups.flat().forEach((device) => {
    if (!device || typeof device !== "object") return;
    const key = text(device.port ?? device.path ?? device.device_id ?? device.hwid ?? device.label, "");
    if (!key || seen.has(key)) return;
    seen.add(key);
    devices.push(device);
  });
  return devices;
}

function collectSerialDevicesFromMessages(messages: AnyRecord[]) {
  const groups: AnyRecord[][] = [];
  messages.forEach((message) => {
    const parsed = parseJsonObjectFromText(message.body);
    if (!parsed) return;
    groups.push(asArray(parsed.serial_devices), asArray(parsed.usb_devices), asArray(parsed.devices));
    const lastScan = parsed.last_scan && typeof parsed.last_scan === "object" ? (parsed.last_scan as AnyRecord) : null;
    if (lastScan) groups.push(asArray(lastScan.serial_devices), asArray(lastScan.usb_devices), asArray(lastScan.devices));
  });
  return mergeSerialDeviceLists(...groups);
}

function stripMachineMetaBlocks(value: unknown) {
  return text(value, "")
    .replace(/AI_REVIEW_META_JSON:\s*[\s\S]*?\s*AI_REVIEW_META_JSON_END/g, "")
    .replace(/AI_REQUIRED_REQUIREMENT_LEDGER_V1\s*[\s\S]*?\s*AI_REQUIRED_REQUIREMENT_LEDGER_END/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function shortText(value: unknown, fallback = "", max = 96) {
  const resolved = stripMachineMetaBlocks(text(value, fallback)) || text(fallback, "");
  return resolved.length <= max ? resolved : `${resolved.slice(0, max)}...`;
}

function relayBodyLine(body: unknown, label: string) {
  const prefix = `${label}:`;
  const cnPrefix = `${label}：`;
  const matched = text(body, "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line.startsWith(prefix) || line.startsWith(cnPrefix));
  return matched ? matched.slice(matched.startsWith(cnPrefix) ? cnPrefix.length : prefix.length).trim() : "";
}

function stripRelayStatusTitle(value: unknown) {
  return text(value, "平台接力状态").replace(/\s*\/\s*接力状态\s*$/, "");
}

function relayStatusLabel(status: string) {
  if (["completed", "done"].includes(status)) return "已完成";
  if (["failed", "cancelled"].includes(status)) return "需重试";
  if (status === "pending") return "等待启动";
  return "运行中";
}

function relayStatusRank(status: unknown) {
  const normalized = text(status, "").toLowerCase();
  if (["completed", "done"].includes(normalized)) return 4;
  if (["failed", "cancelled"].includes(normalized)) return 3;
  if (normalized === "running") return 2;
  if (normalized === "pending") return 1;
  return 0;
}

function relayStepState(status: string, note: string, step: "orchestrator" | "first" | "second") {
  const failed = ["failed", "cancelled"].includes(status);
  const completed = ["completed", "done"].includes(status);
  if (step === "orchestrator") return failed || completed || status === "running" ? "done" : "active";
  if (step === "first") {
    if (completed || note.includes("第一棒已完成") || note.includes("第二棒")) return "done";
    if (failed && note.includes("第一棒")) return "failed";
    return status === "pending" ? "pending" : "active";
  }
  if (completed) return "done";
  if (failed && !note.includes("第一棒")) return "failed";
  if (note.includes("第二棒")) return "active";
  return "pending";
}

function relayNextAction(status: string) {
  if (["completed", "done"].includes(status)) return "下一步：去回执结果确认最终交付";
  if (["failed", "cancelled"].includes(status)) return "下一步：回动作台重试或换线程";
  if (status === "pending") return "下一步：等待编排器启动";
  return "下一步：等待当前棒回写最终回复";
}

function relayStatusView(message: AnyRecord) {
  const status = text(message.status, "pending").toLowerCase();
  const body = text(message.body, "");
  const note = relayBodyLine(body, "当前说明") || "平台编排器正在更新状态。";
  const objective = relayBodyLine(body, "目标") || "等待平台同步接力目标。";
  const first = relayBodyLine(body, "第一棒") || "第一棒待分配";
  const second = relayBodyLine(body, "第二棒") || "第二棒待分配";
  return {
    status,
    statusLabel: relayStatusLabel(status),
    title: stripRelayStatusTitle(message.title),
    relayId: relayBodyLine(body, "relay_id") || text(message.id, ""),
    objective,
    note,
    nextAction: relayNextAction(status),
    steps: [
      {
        label: "编排器",
        state: relayStepState(status, note, "orchestrator"),
        detail: "平台已记录目标并负责中转。",
      },
      {
        label: "第一棒",
        state: relayStepState(status, note, "first"),
        detail: shortText(first, "等待第一位 AI 接单", 72),
      },
      {
        label: "第二棒",
        state: relayStepState(status, note, "second"),
        detail: shortText(second, "等待第二位 AI 接力", 72),
      },
    ],
  };
}

function summarizeEntryLayerKinds(
  steps: {
    layerKind: string;
  }[],
) {
  const counts = new Map<string, number>();
  steps.forEach((step) => {
    counts.set(step.layerKind, (counts.get(step.layerKind) ?? 0) + 1);
  });
  return Array.from(counts.entries())
    .map(([kind, count]) => `${kind} ${count} 层`)
    .join(" + ");
}

function isQuestionMarkHeavy(value: unknown) {
  const raw = String(value ?? "").trim();
  if (!raw) return true;
  const questionMarkCount = raw.match(/\?/g)?.length ?? 0;
  return /^\?+$/.test(raw) || questionMarkCount >= Math.ceil(raw.length / 2);
}

const COMMON_MOJIBAKE_FRAGMENT_REGEX =
  /(?:[\uFFFD�]|鍦ㄧ嚎|绂荤嚎|鐮斿彂鍩哄湴|寮€|寮�|鏈懡|搴勫洯|浠诲姟|鍗忎綔|闃熼暱|涓荤▼|鏈烘埧|鐢佃剳|绾跨▼|銆)/;

function isPollutedDisplayText(value: unknown) {
  const raw = String(value ?? "").trim();
  if (!raw) return true;
  return isQuestionMarkHeavy(raw) || /\?{4,}/.test(raw) || COMMON_MOJIBAKE_FRAGMENT_REGEX.test(raw);
}

function safeDisplayTitle(value: unknown, fallback: string) {
  const raw = text(value, "");
  return !raw || isPollutedDisplayText(raw) ? fallback : raw;
}

function looksLikeUuid(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function isStaleNpcSeat(value: AnyRecord) {
  const seatName = text(value.name, "");
  const sourceThreadId = text(value.source_workstation_id ?? value.metadata?.source_workstation_id, "");
  if (seatName && (isQuestionMarkHeavy(seatName) || /\?{2,}/.test(seatName) || COMMON_MOJIBAKE_FRAGMENT_REGEX.test(seatName))) return true;
  if (sourceThreadId && (/\?{2,}/.test(sourceThreadId) || COMMON_MOJIBAKE_FRAGMENT_REGEX.test(sourceThreadId))) return true;
  if (sourceThreadId && looksLikeUuid(sourceThreadId) && !isCodexSessionId(sourceThreadId)) return true;
  return false;
}

function isNpcSeatWorkstation(value: AnyRecord) {
  const seatType = text(value.seat_type ?? value.metadata?.seat_type ?? value.extra_data?.seat_type, "").toLowerCase();
  return ["npc", "codex"].includes(seatType) || Boolean(text(value.canonical_seat_id, ""));
}

function isCodexSessionId(value: unknown) {
  return text(value, "").toLowerCase().startsWith("codex-session-");
}

function supportsNpcSeatBootstrap(thread: AnyRecord) {
  return !threadBootstrapBlocker(thread);
}

function isManualUserThreadEntry(thread: AnyRecord) {
  const metadata = thread?.metadata && typeof thread.metadata === "object" ? (thread.metadata as AnyRecord) : {};
  return (
    text(metadata.source_kind ?? thread?.source_kind, "").toLowerCase() === "manual_user_entry" ||
    text(metadata.source ?? thread?.source, "").toLowerCase() === "project_workbench"
  );
}

function threadBootstrapBlocker(thread: AnyRecord) {
  const providerId = platformProviderIdFromThread(thread);
  const providerLabel = platformProviderLabelFromThread(thread);
  if (!supportsPlatformNpcCreation(providerId)) {
    return `当前先展示并识别 ${providerLabel} 线程；等它接入统一 adapter 后，这里会直接开放创建。`;
  }
  if (providerId === "claude") {
    if (isManualUserThreadEntry(thread)) return "";
    const note = text(thread.notes, "");
    const status = text(thread.status, "").toLowerCase();
    const liveProcessSeen = String(thread.metadata?.live_process_seen ?? "").toLowerCase() === "true";
    if (!liveProcessSeen || status === "recent_exit" || note.includes("重新打开")) {
      return "先重新打开目标 Claude 终端，并保持它在线，再回来绑定成 NPC。";
    }
  }
  return "";
}

function threadBootstrapReminder(thread: AnyRecord) {
  const providerId = platformProviderIdFromThread(thread);
  if (providerId !== "claude") return "";
  if (isManualUserThreadEntry(thread)) {
    return "提醒：这是用户手动登记的 Claude 线程，平台允许先绑定给 NPC；后续执行时仍要确认终端在线，并让这台电脑自己决定本地仓库路径。";
  }
  const liveProcessSeen = String(thread.metadata?.live_process_seen ?? "").toLowerCase() === "true";
  const cwdMatchesFilter = String(thread.metadata?.cwd_matches_filter ?? "").toLowerCase() === "true";
  if (liveProcessSeen && !cwdMatchesFilter) {
    return "提醒：这个 Claude 终端当前目录不在项目仓库，但仍可绑定给 NPC；后续要自己确认它操作的是目标项目文件。";
  }
  return "";
}

function formatComputerThreadScanStatus(status: unknown) {
  const normalized = text(status, "").toLowerCase();
  if (!normalized) return "未请求";
  if (normalized === "awaiting_runner") return "待接入 runner";
  if (normalized === "requested") return "已请求";
  if (normalized === "completed") return "已完成";
  return text(status, "未请求");
}
function providerExecutorHint(providerId: string) {
  const normalized = providerId.trim().toLowerCase();
  if (normalized === "claude") return "平台里先配 Claude 模板；临时单机覆盖时再追加 --execute-provider-cli 或 --executor-command";
  if (normalized === "qwen") return "平台里先配 Qwen 模板；临时单机覆盖时再追加 --execute-provider-cli 或 --executor-command";
  if (normalized === "codex") return "平台里先配 Codex 模板；临时单机覆盖时再追加 --execute-provider-cli 或 --executor-command";
  return "平台里先配默认模板；临时单机覆盖时再追加 --executor-command";
}

function objectRecord(value: unknown) {
  return value && typeof value === "object" ? (value as AnyRecord) : {};
}

function workstationTokenMetadataValue(thread: AnyRecord, ...keys: string[]) {
  const metadata = objectRecord(thread.metadata);
  const extraData = objectRecord(thread.extra_data);
  for (const key of keys) {
    const value = metadata[key];
    if (value !== undefined && value !== null && text(value, "")) return value;
  }
  for (const key of keys) {
    const value = extraData[key];
    if (value !== undefined && value !== null && text(value, "")) return value;
  }
  return null;
}

function resolveWorkstationAdapterTokenState(thread: AnyRecord) {
  const tokenHash = workstationTokenMetadataValue(thread, "adapter_token_hash", "workstation_token_hash");
  return {
    tokenAvailable: Boolean(text(tokenHash, "")),
    issuedAt: text(
      workstationTokenMetadataValue(thread, "adapter_token_issued_at", "workstation_token_issued_at"),
      "",
    ),
    lastUsedAt: text(
      workstationTokenMetadataValue(thread, "adapter_token_last_used_at", "workstation_token_last_used_at"),
      "",
    ),
  };
}

function adapterTemplate(value: unknown) {
  const metadata = objectRecord(value);
  return metadata.adapter && typeof metadata.adapter === "object" ? (metadata.adapter as AnyRecord) : {};
}

function normalizeExecutionText(value: unknown) {
  const raw = text(value, "");
  return raw || null;
}

function normalizeExecutionTimeout(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed) : null;
}

function providerExecutionSortOrder(providerId: string) {
  if (providerId === "codex") return 10;
  if (providerId === "claude") return 20;
  if (providerId === "qwen") return 30;
  if (providerId === "glm") return 40;
  if (providerId === "openclaw") return 50;
  return 90;
}

function executionSourceLabel(value: string | null | undefined) {
  const normalized = text(value, "");
  if (!normalized) return "未配置";
  if (normalized === "workstation.metadata.adapter.executor_command") return "工位覆盖命令";
  if (normalized === "workstation.metadata.adapter.executor_cwd") return "工位覆盖目录";
  if (normalized === "workstation.metadata.executor_timeout_seconds") return "工位覆盖超时";
  if (normalized === "workstation.metadata.executor_command") return "工位命令";
  if (normalized === "workstation.metadata.executor_cwd") return "工位目录";
  if (normalized === "provider.metadata.adapter.executor_command") return "提供方默认命令";
  if (normalized === "provider.metadata.adapter.executor_cwd") return "提供方默认目录";
  if (normalized === "provider.metadata.adapter.executor_timeout_seconds") return "提供方默认超时";
  if (normalized === "provider.metadata.executor_command") return "提供方命令";
  if (normalized === "provider.metadata.executor_cwd") return "提供方目录";
  if (normalized === "provider.metadata.executor_timeout_seconds") return "提供方超时";
  if (normalized === "computer_node.git_root") return "电脑 Git 根目录";
  if (normalized === "computer_node.workspace_root") return "电脑工作区目录";
  return normalized;
}

function formatExecutionTimeout(seconds: number | null) {
  if (seconds === null) return "未配置";
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds % 60 === 0) return `${Math.round(seconds / 60)} 分钟`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

function displayNodeLabel(node: AnyRecord | null, thread: AnyRecord) {
  return (
    normalizeExecutionText(node?.label) ??
    normalizeExecutionText(node?.name) ??
    normalizeExecutionText(thread.computer_node) ??
    normalizeExecutionText(thread.computer_node_id) ??
    "未绑定电脑"
  );
}

function gitPreflightActionLabel(value: unknown) {
  const normalized = text(value, "status").toLowerCase();
  if (normalized === "sync") return "同步预检";
  if (normalized === "rollback") return "回退预检";
  if (normalized === "clone_prepare") return "克隆准备";
  if (normalized === "read_only") return "只读检查";
  return "状态预检";
}

function gitPreflightStatusLabel(messageType: string, status: string, ok: boolean | null) {
  const normalizedStatus = text(status, "").toLowerCase();
  if (messageType === "runner_command") {
    if (normalizedStatus === "pending") return "已下发，待接单";
    if (normalizedStatus === "acked") return "Runner 已接单";
    if (["completed", "done"].includes(normalizedStatus)) return "Runner 已完成";
    if (["failed", "cancelled"].includes(normalizedStatus)) return "Runner 报错";
    return "已下发";
  }
  if (messageType === "runner_ack") return "最小回执已到";
  if (messageType === "runner_result") {
    if (ok === true) return "预检通过";
    if (ok === false) return "预检有阻塞";
    if (["completed", "done"].includes(normalizedStatus)) return "预检完成";
    if (["failed", "cancelled"].includes(normalizedStatus)) return "预检失败";
    return "预检结果";
  }
  return text(status, "待确认");
}

function gitPreflightRunnerLabel(nodes: AnyRecord[], runnerId: string, resolveDisplay: DisplayResolver) {
  const runnerIdLower = runnerId.toLowerCase();
  const node =
    nodes.find((item) => text(item.runner_id ?? item.runnerId, "").toLowerCase() === runnerIdLower) ?? null;
  return (
    normalizeExecutionText(node?.label) ??
    normalizeExecutionText(node?.name) ??
    normalizeExecutionText(node?.computer_node_label) ??
    resolveDisplay(runnerId, runnerId || "未绑定 Runner")
  );
}

const GIT_PREFLIGHT_PENDING_WARN_MINUTES = 5;
const GIT_PREFLIGHT_PENDING_CRITICAL_MINUTES = 15;

function gitPreflightAgeMinutes(value: unknown) {
  const raw = text(value, "");
  if (!raw) return null;
  const stamp = new Date(raw).getTime();
  if (!Number.isFinite(stamp)) return null;
  return Math.max(0, Math.floor((Date.now() - stamp) / 60000));
}

function parseGitPreflightPayload(message: AnyRecord) {
  return parseJsonObjectFromText(message.body);
}

function isGitPreflightMessage(message: AnyRecord) {
  const messageType = text(message.message_type, "").toLowerCase();
  if (!["runner_command", "runner_ack", "runner_result"].includes(messageType)) return false;
  const parsed = parseGitPreflightPayload(message);
  if (text(parsed?.kind, "").toLowerCase() === "git.preflight") return true;
  const haystack = `${text(message.title, "")}\n${text(message.body, "")}`.toLowerCase();
  return (
    haystack.includes("git.preflight") ||
    haystack.includes("git 同步只读预检") ||
    haystack.includes("git 回退只读预检") ||
    haystack.includes("read-only git capability")
  );
}

function inferGitPreflightAction(message: AnyRecord, payload: AnyRecord | null) {
  const direct = text(payload?.action, "").toLowerCase();
  if (direct) return direct;
  const haystack = `${text(message.title, "")}\n${text(message.body, "")}`.toLowerCase();
  if (haystack.includes("rollback") || haystack.includes("回退")) return "rollback";
  if (haystack.includes("sync") || haystack.includes("同步")) return "sync";
  return "status";
}

function buildGitPreflightFeed(
  collaborationMessages: AnyRecord[],
  nodes: AnyRecord[],
  resolveDisplay: DisplayResolver,
): GitPreflightFeedItem[] {
  return sortedByUpdatedAt(collaborationMessages.filter((message) => isGitPreflightMessage(message))).map((message, index) => {
    const messageType = text(message.message_type, "").toLowerCase();
    const payload = parseGitPreflightPayload(message);
    const runnerId = text(messageType === "runner_command" ? message.recipient_id : message.sender_id, "");
    const action = inferGitPreflightAction(message, payload);
    const ok = typeof payload?.ok === "boolean" ? Boolean(payload.ok) : null;
    const blockers = asArray(payload?.blockers)
      .map((item) => text(item, ""))
      .filter(Boolean);
    const warnings = asArray(payload?.warnings)
      .map((item) => text(item, ""))
      .filter(Boolean);
    const gitVersion =
      text(payload?.git_version?.stdout, "") ||
      text(payload?.git_version?.error, "") ||
      (payload?.git_version ? "已检查 Git" : "");
    const status = text(message.status, messageType === "runner_command" ? "pending" : "");
    const updatedAt = text(message.updated_at ?? message.created_at, "");
    const ageMinutes = gitPreflightAgeMinutes(updatedAt);
    const repositoryUrl = text(payload?.repository_url ?? payload?.repo_url, "");
    const credentialSource = text(payload?.credential_source, "");
    const credentialRef = text(payload?.credential_ref, "");
    const firstProblem = blockers[0] || warnings[0] || "";
    const pendingTooLong =
      messageType === "runner_command" &&
      status === "pending" &&
      ageMinutes !== null &&
      ageMinutes >= GIT_PREFLIGHT_PENDING_WARN_MINUTES;
    const attentionLevel =
      blockers.length || (pendingTooLong && ageMinutes !== null && ageMinutes >= GIT_PREFLIGHT_PENDING_CRITICAL_MINUTES)
        ? "critical"
        : warnings.length || pendingTooLong
          ? "warning"
          : "ok";
    return {
      id: text(message.id, `git-preflight-${index + 1}`),
      title: safeDisplayTitle(message.title, gitPreflightActionLabel(action)),
      runnerId,
      runnerLabel: gitPreflightRunnerLabel(nodes, runnerId, resolveDisplay),
      messageType,
      status,
      statusLabel: gitPreflightStatusLabel(messageType, status, ok),
      action,
      actionLabel: gitPreflightActionLabel(action),
      repositoryUrl,
      branch: text(payload?.branch, ""),
      targetRef: text(payload?.target_ref, ""),
      credentialSource,
      credentialRef,
      gitVersion,
      ok,
      blockers,
      warnings,
      summary: firstProblem || shortText(message.body, "这台电脑已经记录 Git 预检信号。", 120),
      updatedAt,
      ageMinutes,
      attentionLevel,
    } satisfies GitPreflightFeedItem;
  });
}

function summarizeGitPreflightFeed(feed: GitPreflightFeedItem[]) {
  const runnerIds = new Set(feed.map((item) => item.runnerId).filter(Boolean));
  return {
    total: feed.length,
    runnerCount: runnerIds.size,
    resultCount: feed.filter((item) => item.messageType === "runner_result").length,
    passingCount: feed.filter((item) => item.ok === true).length,
    blockedCount: feed.reduce((count, item) => count + item.blockers.length, 0),
    warningCount: feed.reduce((count, item) => count + item.warnings.length, 0),
    pendingCount: feed.filter((item) => item.messageType === "runner_command" && item.status === "pending").length,
    overdueCount: feed.filter((item) => item.messageType === "runner_command" && item.status === "pending" && item.ageMinutes !== null && item.ageMinutes >= GIT_PREFLIGHT_PENDING_WARN_MINUTES).length,
  };
}

function buildGitPreflightAttention(feed: GitPreflightFeedItem[]) {
  const blocker = feed.find((item) => item.blockers.length) ?? null;
  if (blocker) {
    return {
      level: "critical",
      summary: `Git 预检阻塞：${blocker.runnerLabel} / ${blocker.actionLabel} / ${shortText(blocker.blockers[0], blocker.blockers[0], 96)}。先处理这台电脑的 Git/凭据/仓库配置，再继续真实同步或回退。`,
    };
  }
  const overdue =
    feed.find(
      (item) =>
        item.messageType === "runner_command" &&
        item.status === "pending" &&
        item.ageMinutes !== null &&
        item.ageMinutes >= GIT_PREFLIGHT_PENDING_WARN_MINUTES,
    ) ?? null;
  if (overdue) {
    return {
      level: overdue.ageMinutes !== null && overdue.ageMinutes >= GIT_PREFLIGHT_PENDING_CRITICAL_MINUTES ? "critical" : "warning",
      summary: `Git 预检待接单：${overdue.runnerLabel} 已等待 ${formatQueueAge(overdue.ageMinutes) ?? `${overdue.ageMinutes} 分钟`}，请先确认 Runner 是否在线，或重新接入这台电脑。`,
    };
  }
  const warning = feed.find((item) => item.warnings.length) ?? null;
  if (warning) {
    return {
      level: "warning",
      summary: `Git 预检提醒：${warning.runnerLabel} / ${shortText(warning.warnings[0], warning.warnings[0], 96)}。不阻断只读检查，但真实执行前要补齐。`,
    };
  }
  return null;
}

function resolveWorkstationExecutionSettings(workstation: AnyRecord, provider: AnyRecord | null, node: AnyRecord | null) {
  const workstationMetadata = objectRecord(workstation.metadata);
  const providerMetadata = objectRecord(provider?.metadata);
  const workstationAdapter = adapterTemplate(workstationMetadata);
  const providerAdapter = adapterTemplate(providerMetadata);
  const executorCommand =
    normalizeExecutionText(workstationAdapter.executor_command) ??
    normalizeExecutionText(workstationMetadata.executor_command) ??
    normalizeExecutionText(providerAdapter.executor_command) ??
    normalizeExecutionText(providerMetadata.executor_command);
  const executorCommandSource =
    (normalizeExecutionText(workstationAdapter.executor_command) && "workstation.metadata.adapter.executor_command") ||
    (normalizeExecutionText(workstationMetadata.executor_command) && "workstation.metadata.executor_command") ||
    (normalizeExecutionText(providerAdapter.executor_command) && "provider.metadata.adapter.executor_command") ||
    (normalizeExecutionText(providerMetadata.executor_command) && "provider.metadata.executor_command") ||
    null;
  const executorCwd =
    normalizeExecutionText(workstationAdapter.executor_cwd) ??
    normalizeExecutionText(workstationMetadata.executor_cwd) ??
    normalizeExecutionText(providerAdapter.executor_cwd) ??
    normalizeExecutionText(providerMetadata.executor_cwd) ??
    normalizeExecutionText(node?.git_root) ??
    normalizeExecutionText(node?.workspace_root);
  const executorCwdSource =
    (normalizeExecutionText(workstationAdapter.executor_cwd) && "workstation.metadata.adapter.executor_cwd") ||
    (normalizeExecutionText(workstationMetadata.executor_cwd) && "workstation.metadata.executor_cwd") ||
    (normalizeExecutionText(providerAdapter.executor_cwd) && "provider.metadata.adapter.executor_cwd") ||
    (normalizeExecutionText(providerMetadata.executor_cwd) && "provider.metadata.executor_cwd") ||
    (normalizeExecutionText(node?.git_root) && "computer_node.git_root") ||
    (normalizeExecutionText(node?.workspace_root) && "computer_node.workspace_root") ||
    null;
  const executorTimeoutSeconds =
    normalizeExecutionTimeout(workstationAdapter.executor_timeout_seconds) ??
    normalizeExecutionTimeout(workstationMetadata.executor_timeout_seconds) ??
    normalizeExecutionTimeout(providerAdapter.executor_timeout_seconds) ??
    normalizeExecutionTimeout(providerMetadata.executor_timeout_seconds);
  const executorTimeoutSource =
    (normalizeExecutionTimeout(workstationAdapter.executor_timeout_seconds) !== null &&
      "workstation.metadata.adapter.executor_timeout_seconds") ||
    (normalizeExecutionTimeout(workstationMetadata.executor_timeout_seconds) !== null &&
      "workstation.metadata.executor_timeout_seconds") ||
    (normalizeExecutionTimeout(providerAdapter.executor_timeout_seconds) !== null &&
      "provider.metadata.adapter.executor_timeout_seconds") ||
    (normalizeExecutionTimeout(providerMetadata.executor_timeout_seconds) !== null &&
      "provider.metadata.executor_timeout_seconds") ||
    null;
  return {
    executorCommand,
    executorCwd,
    executorTimeoutSeconds,
    executorCommandSource,
    executorCwdSource,
    executorTimeoutSource,
    hasProviderTemplate:
      Boolean(normalizeExecutionText(providerAdapter.executor_command)) ||
      Boolean(normalizeExecutionText(providerAdapter.executor_cwd)) ||
      normalizeExecutionTimeout(providerAdapter.executor_timeout_seconds) !== null ||
      Boolean(normalizeExecutionText(providerMetadata.executor_command)) ||
      Boolean(normalizeExecutionText(providerMetadata.executor_cwd)) ||
      normalizeExecutionTimeout(providerMetadata.executor_timeout_seconds) !== null,
    hasWorkstationOverride:
      Boolean(normalizeExecutionText(workstationAdapter.executor_command)) ||
      Boolean(normalizeExecutionText(workstationAdapter.executor_cwd)) ||
      normalizeExecutionTimeout(workstationAdapter.executor_timeout_seconds) !== null ||
      Boolean(normalizeExecutionText(workstationMetadata.executor_command)) ||
      Boolean(normalizeExecutionText(workstationMetadata.executor_cwd)) ||
      normalizeExecutionTimeout(workstationMetadata.executor_timeout_seconds) !== null,
  };
}

function uniqueStrings(values: unknown[]) {
  return Array.from(
    new Set(
      values
        .map((value) => text(value, ""))
        .filter(Boolean),
    ),
  );
}

function asNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function seatStorageKey(projectId: string) {
  return projectId ? `${PLATFORM_SEAT_KEY}:${projectId}` : PLATFORM_SEAT_KEY;
}

function seatFocusStorageKey(projectId: string) {
  return projectId ? `${PLATFORM_SEAT_FOCUS_KEY}:${projectId}` : PLATFORM_SEAT_FOCUS_KEY;
}

function focusRailStorageKey(projectId: string) {
  return projectId ? `${PLATFORM_FOCUS_RAIL_KEY}:${projectId}` : PLATFORM_FOCUS_RAIL_KEY;
}

function collaboratorStorageKey(projectId: string) {
  return projectId ? `${PLATFORM_COLLABORATOR_KEY}:${projectId}` : PLATFORM_COLLABORATOR_KEY;
}

function currentPlayerStorageKey(projectId: string) {
  return projectId ? `${PLATFORM_CURRENT_PLAYER_KEY}:${projectId}` : PLATFORM_CURRENT_PLAYER_KEY;
}

const MAP_COLLABORATOR_PATH_TEMPLATES: MapCollaboratorWaypoint[][] = [
  [
    { x: 920, y: 620 },
    { x: 1120, y: 620 },
    { x: 1160, y: 790 },
    { x: 960, y: 820 },
  ],
  [
    { x: 760, y: 620 },
    { x: 860, y: 820 },
    { x: 1040, y: 900 },
    { x: 780, y: 900 },
  ],
  [
    { x: 1240, y: 580 },
    { x: 1360, y: 720 },
    { x: 1220, y: 920 },
    { x: 1000, y: 860 },
  ],
  [
    { x: 660, y: 540 },
    { x: 820, y: 560 },
    { x: 960, y: 720 },
    { x: 760, y: 800 },
  ],
];

const MAP_COLLABORATOR_PATH_OFFSETS: MapCollaboratorWaypoint[] = [
  { x: 0, y: 0 },
  { x: -120, y: 30 },
  { x: 120, y: -20 },
  { x: -70, y: 90 },
  { x: 70, y: 80 },
  { x: -150, y: 120 },
  { x: 150, y: 110 },
  { x: 0, y: 140 },
];

function clampMapCoordinate(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function buildCollaboratorPath(index: number): MapCollaboratorWaypoint[] {
  const baseTemplate = MAP_COLLABORATOR_PATH_TEMPLATES[index % MAP_COLLABORATOR_PATH_TEMPLATES.length]!;
  const cycle = Math.floor(index / MAP_COLLABORATOR_PATH_TEMPLATES.length);
  const cycleOffset = MAP_COLLABORATOR_PATH_OFFSETS[cycle % MAP_COLLABORATOR_PATH_OFFSETS.length] ?? { x: 0, y: 0 };
  const band = Math.floor(cycle / MAP_COLLABORATOR_PATH_OFFSETS.length);
  const waveX = (cycle % 2 === 0 ? 1 : -1) * band * 28;
  const waveY = band * 22;
  return baseTemplate.map((point, pointIndex) => ({
    x: clampMapCoordinate(point.x + cycleOffset.x + waveX + (pointIndex % 2 === 0 ? 0 : band * 12), 620, 1410),
    y: clampMapCoordinate(point.y + cycleOffset.y + waveY + (pointIndex >= 2 ? band * 8 : 0), 520, 940),
  }));
}

function objectKeysLower(values: unknown[]) {
  return uniqueStrings(values).map((value) => value.toLowerCase());
}

function nodeOwnerKeys(node: AnyRecord) {
  const metadata = objectRecord(node.metadata);
  return objectKeysLower([
    metadata.owner_user_id,
    metadata.owner_name,
    metadata.owner_email,
    node.owner_user_id,
    node.owner_name,
    node.owner_email,
  ]);
}

function nodeMatchesRouteKeys(node: AnyRecord, routeKeys: string[], allowOwnerlessFallback = false) {
  const ownerKeys = nodeOwnerKeys(node);
  return ownerKeys.some((key) => routeKeys.includes(key)) || (allowOwnerlessFallback && ownerKeys.length === 0);
}

function resolveComputerOwnerLabel(node: AnyRecord, fallbackOwnerLabel = "") {
  const metadata = objectRecord(node.metadata);
  return (
    text(metadata.owner_name, "") ||
    text(metadata.owner_email, "") ||
    text(node.owner_name, "") ||
    text(node.owner_email, "") ||
    fallbackOwnerLabel ||
    "未标记玩家"
  );
}

function isCurrentComputerOwner(
  node: AnyRecord,
  currentUser: AnyRecord | null | undefined,
  allowOwnerlessFallback = false,
) {
  const currentKeys = objectKeysLower([currentUser?.id, currentUser?.email, currentUser?.name]);
  if (!currentKeys.length) return false;
  const ownerKeys = nodeOwnerKeys(node);
  return ownerKeys.some((key) => currentKeys.includes(key)) || (allowOwnerlessFallback && ownerKeys.length === 0);
}

function isOnlineNode(status: unknown) {
  return ["online", "ready", "active"].includes(String(status ?? "").toLowerCase());
}

function computerRegistrationLabel(node: AnyRecord | null | undefined) {
  const status = text(node?.status, "");
  if (!status) return "登记状态未记录";
  if (isOnlineNode(status)) return `登记状态 ${status}，不等于可接单`;
  return `登记状态 ${status}`;
}

function normalizeHumanPresenceState(value: unknown) {
  const normalized = text(value, "").toLowerCase();
  return normalized === "online" || normalized === "stale" || normalized === "never_seen"
    ? normalized
    : "never_seen";
}

function humanPresenceLabel(state: string, fallback: unknown, onlineLabel: string, staleLabel: string, neverLabel: string) {
  return text(
    fallback,
    state === "online" ? onlineLabel : state === "stale" ? staleLabel : neverLabel,
  );
}

function nullableAgeSeconds(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.max(0, Math.floor(numeric)) : null;
}

function collaboratorRoleLabel(value: unknown) {
  const normalized = text(value, "").toLowerCase();
  if (!normalized) return "协作者";
  if (normalized === "owner") return "项目 owner";
  if (normalized === "admin") return "管理员";
  if (normalized === "maintainer") return "维护者";
  if (normalized === "viewer") return "观察者";
  if (normalized === "collaborator") return "协作者";
  return text(value, "协作者");
}

function collaboratorOwnershipLabel(member: AnyRecord, index: number) {
  return text(
    member.summary ??
      member.email ??
      member.user?.email ??
      member.responsibility ??
      member.role ??
      `协作位 ${index + 1}`,
    `协作位 ${index + 1}`,
  );
}

function buildCollaboratorMapPayload(
  members: AnyRecord[],
  currentUser: AnyRecord | null | undefined,
): { collaborators: MapCollaboratorPayload[]; currentPlayerId: string } {
  const currentId = text(currentUser?.id, "");
  const currentEmail = text(currentUser?.email, "").toLowerCase();
  const currentName = text(currentUser?.name, "");
  const seen = new Set<string>();
  const collaborators = members
    .map((member, index) => {
      const id = text(member.id ?? member.user_id ?? member.user?.id, "");
      const email = text(member.email ?? member.user?.email, "").toLowerCase();
      const name = text(member.name ?? member.user?.name ?? member.email ?? member.user?.email, "");
      const stableKey = id || email || name.toLowerCase();
      if (!stableKey || seen.has(stableKey)) return null;
      seen.add(stableKey);
      return {
        id: stableKey,
        name,
        role: collaboratorRoleLabel(member.role),
        ownership: collaboratorOwnershipLabel(member, index),
        scene: "map-home",
        path: buildCollaboratorPath(index),
        isCurrentPlayer:
          (currentId && stableKey === currentId) ||
          (currentEmail && stableKey === currentEmail) ||
          (!!currentName && name === currentName),
        accountPresenceState: normalizeHumanPresenceState(member.online_state ?? member.user?.online_state),
        accountPresenceLabel: humanPresenceLabel(
          normalizeHumanPresenceState(member.online_state ?? member.user?.online_state),
          member.online_label ?? member.user?.online_label,
          "账号在线",
          "账号离线",
          "未见登录",
        ),
        accountPresenceAgeSeconds: nullableAgeSeconds(member.online_age_seconds ?? member.user?.online_age_seconds),
        projectPresenceState: normalizeHumanPresenceState(member.project_presence_state),
        projectPresenceLabel: humanPresenceLabel(
          normalizeHumanPresenceState(member.project_presence_state),
          member.project_presence_label,
          "正在项目里",
          "离开项目",
          "未进入项目",
        ),
        projectPresenceAgeSeconds: nullableAgeSeconds(member.project_presence_age_seconds),
        lastProjectPath: text(member.last_project_path, ""),
      } satisfies MapCollaboratorPayload;
    })
    .filter((item): item is MapCollaboratorPayload => Boolean(item));

  if (!collaborators.length && (currentId || currentEmail || currentName)) {
    collaborators.push({
      id: currentId || currentEmail || currentName.toLowerCase(),
      name: currentName || currentEmail || "当前主角",
      role: "项目 owner",
      ownership: currentEmail || "当前账号",
      scene: "map-home",
      path: buildCollaboratorPath(0),
      isCurrentPlayer: true,
      accountPresenceState: "online",
      accountPresenceLabel: "账号在线",
      accountPresenceAgeSeconds: null,
      projectPresenceState: "online",
      projectPresenceLabel: "正在项目里",
      projectPresenceAgeSeconds: null,
      lastProjectPath: "",
    });
  }

  let currentPlayerId =
    collaborators.find((item) => item.isCurrentPlayer)?.id ??
    currentId ??
    currentEmail;
  if (!collaborators.some((item) => item.isCurrentPlayer) && collaborators[0]) {
    collaborators[0].isCurrentPlayer = true;
    currentPlayerId = collaborators[0].id;
  }

  return {
    collaborators,
    currentPlayerId,
  };
}

function buildHumanPartyHudEntries(
  collaborators: MapCollaboratorPayload[],
  collaborationMessages: AnyRecord[],
  activeTaskCount: number,
  projectId: string,
  nodes: AnyRecord[],
  activeSourceThreads: AnyRecord[],
) {
  const latestHumanProjectSyncBySender = new Map<string, AnyRecord>();
  const allowOwnerlessNodeFallback = collaborators.length === 1;
  sortedByUpdatedAt(
    collaborationMessages.filter((message) => {
      const type = text(message.message_type, "").toLowerCase();
      const recipientType = text(message.recipient_type, "").toLowerCase();
      const recipientId = text(message.recipient_id, "");
      const senderType = text(message.sender_type, "").toLowerCase();
      return (
        senderType === "human" &&
        recipientType === "project" &&
        recipientId === projectId &&
        ["project_sync_note", "status_update"].includes(type)
      );
    }),
  ).forEach((message) => {
    const senderId = text(message.sender_id ?? message.agent_id, "").toLowerCase();
    if (!senderId || latestHumanProjectSyncBySender.has(senderId)) return;
    latestHumanProjectSyncBySender.set(senderId, message);
  });

  return collaborators.map((player) => {
    const sceneLabel = player.scene === "map-home" ? "主房" : player.scene === "map-farm" ? "外场" : player.scene;
    const candidateKeys = uniqueStrings([player.id, player.name, player.ownership]).map((value) => value.toLowerCase());
    const ownedNodes = nodes.filter((node) => nodeMatchesRouteKeys(node, candidateKeys, allowOwnerlessNodeFallback));
    const ownedNodeIds = new Set(ownedNodes.map((node) => text(node.id ?? node.node_id ?? node.name, "")).filter(Boolean));
    const onlineOwnedNodes = ownedNodes.filter((node) => isComputerRunnerOnline(node));
    const threadCount = activeSourceThreads.filter((thread) => {
      const nodeId = text(thread?.computer_node_id ?? thread?.computerNodeId, "");
      return Boolean(nodeId) && ownedNodeIds.has(nodeId);
    }).length;
    const latestSync =
      candidateKeys
        .map((candidate) => latestHumanProjectSyncBySender.get(candidate))
        .find((message): message is AnyRecord => Boolean(message)) ?? null;
    const combinedSyncText = `${text(latestSync?.title, "")} ${text(latestSync?.body, "")}`.toLowerCase();
    let stateLabel = "";
    let stateTone: HumanPartyHudEntry["stateTone"] = "idle";
    if (player.projectPresenceState !== "online") {
      stateLabel = player.projectPresenceLabel;
      stateTone = player.accountPresenceState === "online" ? "idle" : "blocked";
    } else if (/(阻塞|blocked|stuck|卡住|无法继续|需要支援|需要帮助)/.test(combinedSyncText)) {
      stateLabel = "被阻塞";
      stateTone = "blocked";
    } else if (/(审核|review|审批|待确认|待会审|审查)/.test(combinedSyncText)) {
      stateLabel = "待审核";
      stateTone = "review";
    } else if (/(正在|处理中|editing|implement|coding|修复|开发|编写|我先接|跟进|推进)/.test(combinedSyncText)) {
      stateLabel = "处理中";
      stateTone = "active";
    } else if (/(待接手|等待|handoff|接手|协作|排队|待协作|next)/.test(combinedSyncText)) {
      stateLabel = "待协作";
      stateTone = "idle";
    } else if (latestSync) {
      stateLabel = "已同步";
      stateTone = "active";
    } else if (activeTaskCount > 0) {
      stateLabel = player.isCurrentPlayer ? "关注共享任务" : "待协作";
      stateTone = player.isCurrentPlayer ? "active" : "idle";
    } else {
      stateLabel = player.isCurrentPlayer ? "已就位" : "待同步";
      stateTone = "idle";
    }
    const projectPresenceAgeLabel = formatSecondsAsShortAge(player.projectPresenceAgeSeconds);
    const accountPresenceAgeLabel = formatSecondsAsShortAge(player.accountPresenceAgeSeconds);
    const stateHint = player.projectPresenceState !== "online"
      ? `${player.projectPresenceLabel}${projectPresenceAgeLabel ? `：${projectPresenceAgeLabel}` : ""}。如果要让这台电脑继续协作，需要对方重新打开并进入当前项目。`
      : latestSync
      ? shortText(
          text(latestSync.body, "") || text(latestSync.title, "") || "最近同步了一条协作动态。",
          "最近同步了一条协作动态。",
          72,
        )
      : ownedNodes.length
        ? `${onlineOwnedNodes.length}/${ownedNodes.length} 台电脑 Runner 心跳正常 / ${threadCount} 条线程可见。扫描到线程不代表自动接单，常驻 Watch 才能领取平台派工。`
      : activeTaskCount > 0
        ? `当前有 ${activeTaskCount} 条共享任务，适合继续联机分工。`
        : player.isCurrentPlayer
          ? "当前账号主角已经进入项目，可以开始发协作动态或派工。"
          : "等待对方主角同步状态或进入下一步分工。";
    return {
      id: player.id,
      name: player.name,
      role: player.role,
      ownership: player.ownership,
      scene: player.scene,
      isCurrentPlayer: player.isCurrentPlayer,
      identityLabel: player.isCurrentPlayer ? "当前账号主角" : "项目成员主角",
      stateLabel,
      stateTone,
      stateHint,
      detail: `${player.role} / ${player.ownership} / ${sceneLabel} / Runner 心跳 ${onlineOwnedNodes.length}/${ownedNodes.length} 台 / 线程 ${threadCount} 条`,
      routeKeys: candidateKeys,
      computerCount: ownedNodes.length,
      onlineComputerCount: onlineOwnedNodes.length,
      threadCount,
      accountPresenceState: player.accountPresenceState,
      accountPresenceLabel: player.accountPresenceLabel,
      accountPresenceAgeLabel,
      projectPresenceState: player.projectPresenceState,
      projectPresenceLabel: player.projectPresenceLabel,
      projectPresenceAgeLabel,
      lastProjectPath: player.lastProjectPath,
    } satisfies HumanPartyHudEntry;
  });
}

function buildComputerFleetGroups(
  players: HumanPartyHudEntry[],
  nodes: AnyRecord[],
  activeThreads: AnyRecord[],
) {
  const usedNodeIds = new Set<string>();
  const allowOwnerlessNodeFallback = players.length === 1;
  const groups: ComputerFleetGroup[] = players.map((player) => {
    const ownedNodes = sortedByUpdatedAt(
      nodes.filter((node) => nodeMatchesRouteKeys(node, player.routeKeys, allowOwnerlessNodeFallback)),
    );
    ownedNodes.forEach((node) => {
      const nodeId = text(node.id ?? node.node_id ?? node.name, "");
      if (nodeId) usedNodeIds.add(nodeId);
    });
    const nodeIds = new Set(ownedNodes.map((node) => text(node.id ?? node.node_id ?? node.name, "")).filter(Boolean));
    const threadCount = activeThreads.filter((thread) => {
      const nodeId = text(thread.computer_node_id ?? thread.computerNodeId, "");
      return Boolean(nodeId) && nodeIds.has(nodeId);
    }).length;
    return {
      id: player.id,
      name: player.name,
      identityLabel: player.identityLabel,
      isCurrentPlayer: player.isCurrentPlayer,
      stateLabel: player.stateLabel,
      computerCount: ownedNodes.length,
      onlineComputerCount: ownedNodes.filter((node) => isComputerRunnerOnline(node)).length,
      threadCount,
      routeKeys: player.routeKeys,
      computers: ownedNodes,
    } satisfies ComputerFleetGroup;
  });

  const unassignedNodes = sortedByUpdatedAt(
    nodes.filter((node) => {
      const nodeId = text(node.id ?? node.node_id ?? node.name, "");
      return nodeId ? !usedNodeIds.has(nodeId) : false;
    }),
  );
  if (unassignedNodes.length) {
    const nodeIds = new Set(unassignedNodes.map((node) => text(node.id ?? node.node_id ?? node.name, "")).filter(Boolean));
    groups.push({
      id: "unassigned-computers",
      name: "未归组电脑",
      identityLabel: "待归属",
      isCurrentPlayer: false,
      stateLabel: "待整理",
      computerCount: unassignedNodes.length,
      onlineComputerCount: unassignedNodes.filter((node) => isComputerRunnerOnline(node)).length,
      threadCount: activeThreads.filter((thread) => {
        const nodeId = text(thread.computer_node_id ?? thread.computerNodeId, "");
        return Boolean(nodeId) && nodeIds.has(nodeId);
      }).length,
      routeKeys: [],
      computers: unassignedNodes,
    });
  }

  return groups.filter((group) => group.computerCount > 0);
}

function routeAliasesMatch(routeAliases: string[], focusKeys: string[]) {
  if (!focusKeys.length || !routeAliases.length) return false;
  const normalizedFocus = new Set(focusKeys.map((value) => value.toLowerCase()));
  return routeAliases.some((value) => normalizedFocus.has(value.toLowerCase()));
}

function seatMatchesFocus(seat: AnyRecord, seatView: MapSeatPayload | null, focusId: string) {
  const normalizedFocus = text(focusId, "").toLowerCase();
  if (!normalizedFocus) return false;
  return uniqueStrings([
    text(seat.row_id, ""),
    text(seat.id, ""),
    text(seat.config_id, ""),
    text(seat.name, ""),
    text(seat.metadata?.display_name, ""),
    text(seat.source_workstation_id ?? seat.metadata?.source_workstation_id, ""),
    text(seatView?.id, ""),
    text(seatView?.sourceThreadId, ""),
    text(seatView?.name, ""),
  ]).some((candidate) => candidate.toLowerCase() === normalizedFocus);
}

function buildMapHref(
  projectId: string,
  seats: MapSeatPayload[],
  focusSeatId?: string,
  options: { embed?: boolean } = {},
) {
  const params = new URLSearchParams();
  if (projectId) params.set("project", projectId);
  if (options.embed) params.set("embed", "project-shell");
  if (seats.length) {
    params.set(
      "seat_payload",
      JSON.stringify({
        projectId,
        seats,
      }),
    );
  }
  if (focusSeatId) {
    params.set("seat_focus", focusSeatId);
  }
  const query = params.toString();
  return query ? `/harvest-moon-phaser3-game/index.html?${query}` : "/harvest-moon-phaser3-game/index.html";
}

function buildDisplayResolver(config: AnyRecord, members: AnyRecord[] = []): DisplayResolver {
  const labelMap = new Map<string, string>();
  const workstationMap = new Map<string, AnyRecord>();

  function remember(candidate: unknown, label: unknown) {
    const key = text(candidate, "");
    const resolvedLabel = text(label, "");
    if (!key || !resolvedLabel) return;
    labelMap.set(key, resolvedLabel);
    labelMap.set(key.toLowerCase(), resolvedLabel);
  }

  function rememberWorkstation(item: AnyRecord) {
    [item.id, item.config_id, item.row_id, item.workstation_id].forEach((candidate) => {
      const key = text(candidate, "");
      if (!key) return;
      workstationMap.set(key, item);
      workstationMap.set(key.toLowerCase(), item);
    });
  }

  function workstationLabel(item: AnyRecord | null | undefined) {
    if (!item) return "";
    return text(item.name ?? item.metadata?.display_name ?? item.metadata?.name ?? item.extra_data?.display_name ?? item.extra_data?.name, "");
  }

  function effectiveWorkstationLabel(item: AnyRecord) {
    const directLabel = workstationLabel(item);
    const seatType = text(item.metadata?.seat_type ?? item.extra_data?.seat_type ?? item.seat_type, "").toLowerCase();
    const sourceWorkstationId = text(
      item.source_workstation_id ?? item.metadata?.source_workstation_id ?? item.extra_data?.source_workstation_id,
      "",
    );
    if (!["codex", "npc"].includes(seatType) || !sourceWorkstationId) return directLabel;
    const sourceWorkstation =
      workstationMap.get(sourceWorkstationId) ?? workstationMap.get(sourceWorkstationId.toLowerCase()) ?? null;
    if (directLabel && !isQuestionMarkHeavy(directLabel)) return directLabel;
    return workstationLabel(sourceWorkstation) || directLabel;
  }

  function register(item: AnyRecord, label: unknown) {
    remember(item.id, label);
    remember(item.config_id, label);
    remember(item.row_id, label);
    remember(item.workstation_id, label);
    remember(item.agent_id, label);
    if (text(item.agent_id, "")) {
      remember(`ai:${text(item.agent_id, "")}`, label);
    }
    remember(item.runner_id, label);
    remember(item.source_workstation_id, label);
    remember(item.metadata?.source_workstation_id, label);
    remember(item.extra_data?.source_workstation_id, label);
    remember(item.email, label);
    remember(item.name, label);
  }

  const workstations = [
    ...asArray(config.workstations),
    ...asArray(config.sourceThreads),
    ...asArray(config.codexSeats),
  ];

  workstations.forEach((item) => {
    rememberWorkstation(item);
  });

  workstations.forEach((item) => {
    const label = effectiveWorkstationLabel(item);
    if (!label) return;
    register(item, label);
  });

  members.forEach((member) => {
    const label = text(member.name ?? member.display_name ?? member.email, "");
    if (!label) return;
    register(member, label);
    remember(member.user_id, label);
    remember(member.user?.id, label);
    remember(member.user?.email, label);
  });

  return (value, fallback) => {
    const raw = text(value, "");
    if (!raw) return fallback;
    const matched = labelMap.get(raw) ?? labelMap.get(raw.toLowerCase());
    if (matched) return matched;
    return looksLikeUuid(raw) ? fallback : raw;
  };
}

function formatStamp(value: unknown) {
  const raw = text(value, "");
  if (!raw) return "刚刚";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${month}-${day} ${hours}:${minutes}`;
}

function formatDateTimeLocal(value: unknown) {
  const raw = text(value, "");
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 16);
}

function formatEpoch(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "刚刚";
  return formatStamp(new Date(value).toISOString());
}

function queueAgeMinutes(createdAt: number) {
  if (!Number.isFinite(createdAt) || createdAt <= 0) return null;
  return Math.max(0, Math.floor((Date.now() - createdAt) / 60000));
}

function formatQueueAge(minutes: number | null) {
  if (minutes === null) return null;
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (!restMinutes) return `${hours} 小时`;
  return `${hours} 小时 ${restMinutes} 分钟`;
}

function formatSecondsAsShortAge(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds)) return null;
  const normalized = Math.max(0, Math.floor(seconds));
  if (normalized < 60) return `${normalized} 秒前`;
  if (normalized < 3600) return `${Math.floor(normalized / 60)} 分钟前`;
  if (normalized < 86400) return `${Math.floor(normalized / 3600)} 小时前`;
  return `${Math.floor(normalized / 86400)} 天前`;
}

const LATE_PROGRESS_ACK_MINUTES = 60;
const STALE_AFTER_ACK_MINUTES = 4 * 60;
const MACHINE_ROOM_ACTIVITY_WARN_MINUTES = 6 * 60;
const MACHINE_ROOM_ACTIVITY_STALE_MINUTES = 24 * 60;

function queueStateLabel(minutes: number | null) {
  if (minutes === null) return null;
  if (minutes >= 120) return "桥接滞留";
  if (minutes >= 45) return "排队已久";
  return "刚入队列";
}

function workstationActivityFreshnessLabel(minutes: number | null) {
  if (minutes === null) {
    return { label: "还没见到协作信号", stale: false };
  }
  if (minutes < 60) {
    return { label: "刚刚活跃", stale: false };
  }
  if (minutes < MACHINE_ROOM_ACTIVITY_WARN_MINUTES) {
    return { label: "今日活跃", stale: false };
  }
  const ageLabel = formatQueueAge(minutes) ?? `${minutes} 分钟`;
  if (minutes >= MACHINE_ROOM_ACTIVITY_STALE_MINUTES) {
    return { label: `超过 ${ageLabel} 未更新`, stale: true };
  }
  return { label: `已安静 ${ageLabel}`, stale: false };
}

function buildProjectSurfacePath(basePath: string, nextParams: Record<string, string | undefined>) {
  const [pathname, search = ""] = basePath.split("?");
  const params = new URLSearchParams(search);
  Object.entries(nextParams).forEach(([key, value]) => {
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
  });
  const query = params.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function shortRequirementLabel(requirementId: string | null | undefined) {
  const normalized = text(requirementId, "");
  return normalized ? `Requirement ${normalized.slice(0, 8)}` : "";
}

function focusAnchorLabel(target: string | null | undefined, requirementId: string | null | undefined) {
  const targetLabel = text(target, "");
  const requirementLabel = shortRequirementLabel(requirementId);
  if (targetLabel && requirementLabel) return `${targetLabel} · ${requirementLabel}`;
  return targetLabel || requirementLabel || "当前线程";
}

function isNpc2ThreadLabel(value: unknown) {
  return text(value, "").toUpperCase().includes("NPC2");
}

function isPrimaryCoordinatorSeatLabel(value: unknown) {
  const normalized = text(value, "").toUpperCase();
  return ["NPC1", "NPC2", "NPC3"].some((label) => normalized.includes(label));
}

function isPrimaryCoordinatorInboxItem(item: CodexInboxFeedItem) {
  return [
    item.target,
    item.workstationName,
    item.title,
    item.body,
    item.meta,
  ].some((value) => isPrimaryCoordinatorSeatLabel(value));
}

function isPrimaryCoordinatorProofItem(item: CooperationProofItem) {
  return [
    item.target,
    item.title,
    item.body,
    item.meta,
  ].some((value) => isPrimaryCoordinatorSeatLabel(value));
}

function isNpc2InboxItem(item: CodexInboxFeedItem) {
  return [
    item.target,
    item.workstationName,
    item.title,
    item.body,
    item.meta,
  ].some((value) => isNpc2ThreadLabel(value));
}

function pickFeaturedInboxItem(feed: CodexInboxFeedItem[]) {
  return feed.find((item) => isNpc2InboxItem(item)) ?? feed[0] ?? null;
}

function pickFeaturedQueuedInboxItem(feed: CodexInboxFeedItem[]) {
  return feed.find((item) => item.isQueued && isNpc2InboxItem(item))
    ?? feed.find((item) => item.isQueued)
    ?? null;
}

function countQueuedInboxItemsForFocus(feed: CodexInboxFeedItem[], focus: CodexInboxFeedItem | null | undefined) {
  if (!focus) return 0;
  const focusWorkstationId = text(focus.workstationId, "").toLowerCase();
  const focusTarget = text(focus.target, "").toLowerCase();
  return feed.filter((item) => {
    if (!item.isQueued) return false;
    const itemWorkstationId = text(item.workstationId, "").toLowerCase();
    if (focusWorkstationId && itemWorkstationId) {
      return itemWorkstationId === focusWorkstationId;
    }
    return text(item.target, "").toLowerCase() === focusTarget;
  }).length;
}

function routeLabel(requirement: AnyRecord) {
  return text(requirement.requirement_type, "").toLowerCase().includes("human") ? "人工链" : "AI 链";
}

function isFinalReplyMessage(message: AnyRecord) {
  const type = text(message.message_type, "").toLowerCase();
  const status = text(message.status, "").toLowerCase();
  return (type === "requirement_final_reply" && isDoneStatus(status)) || (type === "agent_result" && isDoneStatus(status));
}

function isProgressMessage(message: AnyRecord) {
  const type = text(message.message_type, "").toLowerCase();
  return [
    "requirement_dispatch",
    "requirement_progress_ack",
    "requirement_final_reply",
    "agent_report",
    "agent_ack",
    "agent_result",
    "runner_ack",
    "runner_result",
  ].includes(type);
}

function isAckMessage(message: AnyRecord) {
  const type = text(message.message_type, "").toLowerCase();
  return ["agent_ack", "requirement_progress_ack", "runner_ack"].includes(type);
}

function isCommandMessage(message: AnyRecord) {
  const type = text(message.message_type, "").toLowerCase();
  return ["agent_command", "requirement_dispatch", "runner_command"].includes(type);
}

function commandMessageLabel(message: AnyRecord) {
  const type = text(message.message_type, "").toLowerCase();
  if (type === "requirement_dispatch") return "最近平台派单";
  if (type === "runner_command") return "最近电脑指令";
  return "最近收到命令";
}

function workstationRouteKeys(thread: AnyRecord) {
  return uniqueStrings([
    thread.id,
    thread.workstation_id,
    thread.config_id,
    thread.row_id,
    thread.agent_id,
    thread.source_workstation_id,
    thread.metadata?.source_workstation_id,
  ]).map((item) => item.toLowerCase());
}

function collaborationRouteKeys(message: AnyRecord) {
  return uniqueStrings([
    message.agent_id,
    message.sender_id,
    message.recipient_id,
    message.workstation_id,
    message.source_workstation_id,
    message.metadata?.source_workstation_id,
    message.metadata?.recipient_id,
  ]).map((item) => item.toLowerCase());
}

function messageMatchesWorkstation(message: AnyRecord, thread: AnyRecord) {
  const threadKeys = workstationRouteKeys(thread);
  if (!threadKeys.length) return false;
  const messageKeys = collaborationRouteKeys(message);
  return messageKeys.some((item) => threadKeys.includes(item));
}

function buildWorkstationActivitySummary(thread: AnyRecord, collaborationMessages: AnyRecord[]) {
  const matchingMessages = sortedByUpdatedAt(
    collaborationMessages.filter((message) => messageMatchesWorkstation(message, thread)),
  );
  const latestCommand = matchingMessages.find((message) => isCommandMessage(message)) ?? null;
  const latestAck = matchingMessages.find((message) => isAckMessage(message)) ?? null;
  const latestFinalReply = matchingMessages.find((message) => isFinalReplyMessage(message)) ?? null;
  const latestProgress = matchingMessages.find((message) => isProgressMessage(message)) ?? null;
  const latestSignalAt = text(
    latestFinalReply?.updated_at ??
      latestFinalReply?.created_at ??
      latestAck?.updated_at ??
      latestAck?.created_at ??
      latestProgress?.updated_at ??
      latestProgress?.created_at,
    "",
  );
  const latestSignalEpoch = latestSignalAt ? new Date(latestSignalAt).getTime() : 0;
  const activityAgeMinutes = queueAgeMinutes(latestSignalEpoch);
  const freshness = workstationActivityFreshnessLabel(activityAgeMinutes);

  const activityHealthLabel = latestFinalReply
    ? "已回写最终回复"
    : latestAck
      ? "已回最小回执"
      : latestProgress
        ? "已有过程信号"
        : "还没回过消息";

  return {
    activityHealthLabel,
    latestCommandAt: text(latestCommand?.updated_at ?? latestCommand?.created_at, ""),
    latestCommandLabel: latestCommand ? safeDisplayTitle(latestCommand.title ?? latestCommand.body, commandMessageLabel(latestCommand)) : "",
    latestCommandBody: latestCommand ? shortText(latestCommand.body, "没有额外说明", 60) : "",
    latestCommandTypeLabel: latestCommand ? commandMessageLabel(latestCommand) : "最近收到命令",
    latestAckAt: text(latestAck?.updated_at ?? latestAck?.created_at, ""),
    latestAckLabel: latestAck ? safeDisplayTitle(latestAck.title ?? latestAck.body, "最小回执") : "",
    latestAckBody: latestAck ? shortText(latestAck.body, "没有额外说明", 60) : "",
    latestFinalReplyAt: text(latestFinalReply?.updated_at ?? latestFinalReply?.created_at, ""),
    latestFinalReplyLabel: latestFinalReply ? safeDisplayTitle(latestFinalReply.title ?? latestFinalReply.body, "最终回复") : "",
    latestFinalReplyBody: latestFinalReply ? shortText(latestFinalReply.body, "没有额外说明", 60) : "",
    latestSignalAt,
    activityAgeMinutes,
    activityFreshnessLabel: freshness.label,
    activityFreshnessStale: freshness.stale,
  };
}

function activityMomentValue(value: unknown) {
  const raw = text(value, "");
  if (!raw) return 0;
  const stamp = new Date(raw).getTime();
  return Number.isFinite(stamp) ? stamp : 0;
}

function workstationRecoverySeverityRank(severity: string) {
  if (severity === "critical") return 4;
  if (severity === "warning") return 3;
  if (severity === "info") return 2;
  return 1;
}

function buildWorkstationRecoverySummary(options: {
  providerId: string;
  executionProfile:
    | {
        tokenAvailable?: boolean;
      }
    | null
    | undefined;
  activityProfile: ReturnType<typeof buildWorkstationActivitySummary>;
  boundSeat: AnyRecord | null;
  threadBootstrapIssue: string;
}) {
  const { providerId, executionProfile, activityProfile, boundSeat, threadBootstrapIssue } = options;
  const hasToken = Boolean(executionProfile?.tokenAvailable);
  const hasSignal = Boolean(activityProfile.latestSignalAt);
  const hasAck = Boolean(activityProfile.latestAckAt);
  const hasFinalReply = Boolean(activityProfile.latestFinalReplyAt);
  const hasCommand = Boolean(activityProfile.latestCommandAt);
  const hasBoundSeat = Boolean(boundSeat);
  const commandAfterSignal =
    activityMomentValue(activityProfile.latestCommandAt) > activityMomentValue(activityProfile.latestSignalAt);
  const shouldOfferCalibration = hasBoundSeat && (providerId === "codex" || providerId === "claude");

  if (threadBootstrapIssue) {
    return {
      code: "bootstrap-blocked",
      severity: "warning",
      label: "接入条件待处理",
      summary: threadBootstrapIssue,
      nextStep: providerId === "claude" ? "先重新打开目标 Claude 终端并保持在线，再回来绑定或校准。" : "先补齐这条线程的接入前提，再继续派工。",
      needsAttention: true,
      suggestTokenRotation: false,
      suggestSeatCalibration: shouldOfferCalibration,
    };
  }

  if (hasCommand && !hasSignal) {
    return {
      code: "awaiting-first-signal-after-command",
      severity: "critical",
      label: "派单后还没回信",
      summary: "平台已经把任务发到这条线程，但它还没有回过最小回执或最终回复。",
      nextStep: hasToken ? "先确认目标终端在线，再重跑接入命令；如果仍然没回，轮换工位令牌后重连 adapter。" : "先生成工位令牌并运行接入命令，再让线程先回一条最小回执。",
      needsAttention: true,
      suggestTokenRotation: true,
      suggestSeatCalibration: shouldOfferCalibration,
    };
  }

  if (activityProfile.activityFreshnessStale && commandAfterSignal) {
    return {
      code: "stale-after-command",
      severity: "critical",
      label: "命令后长期未更新",
      summary: `${activityProfile.activityFreshnessLabel}，而且平台最近一次派单时间晚于最后协作信号，说明这条线程更像是派单后掉线了。`,
      nextStep: hasToken ? "优先轮换工位令牌并重连 adapter，再检查目标终端是否卡住或切到别的目录。" : "先补工位令牌，再让目标电脑按接入命令重新上线。",
      needsAttention: true,
      suggestTokenRotation: true,
      suggestSeatCalibration: shouldOfferCalibration,
    };
  }

  if (activityProfile.activityFreshnessStale) {
    return {
      code: "stale-thread",
      severity: "warning",
      label: "线程长时间未更新",
      summary: hasFinalReply
        ? `这条线程上次已经回过最终回复，但现在 ${activityProfile.activityFreshnessLabel}。`
        : hasAck
          ? `这条线程上次只回过最小回执，但现在 ${activityProfile.activityFreshnessLabel}。`
          : `这条线程 ${activityProfile.activityFreshnessLabel}。`,
      nextStep: hasFinalReply ? "如果它后面还要继续接任务，先重连 adapter 保持在线；如果暂时不用，可以保留现状。" : "先确认终端在线，再补一条最小回执，避免平台误判它还在处理中。",
      needsAttention: true,
      suggestTokenRotation: true,
      suggestSeatCalibration: shouldOfferCalibration,
    };
  }

  if (!hasToken) {
    return {
      code: "token-missing",
      severity: "warning",
      label: "还没签发接入令牌",
      summary: "这条线程已经出现在机房里，但还没有稳定的 adapter 令牌，跨电脑接入还不够稳。",
      nextStep: "先生成工位令牌，再到目标电脑运行接入命令，把这条线程纳入平台统一消息格式。",
      needsAttention: hasBoundSeat || hasCommand || hasSignal,
      suggestTokenRotation: true,
      suggestSeatCalibration: false,
    };
  }

  if (!hasSignal) {
    return {
      code: "awaiting-first-signal",
      severity: "warning",
      label: "等待首次回写",
      summary: "线程已经可见，也有接入令牌，但平台还没收到它的第一条协作信号。",
      nextStep: "先下发一条最小协作检查，确认这条线程至少能回一条最小回执。",
      needsAttention: hasBoundSeat || hasCommand,
      suggestTokenRotation: false,
      suggestSeatCalibration: shouldOfferCalibration,
    };
  }

  if (!boundSeat) {
    return {
      code: "unbound-seat",
      severity: "info",
      label: "还没绑定 NPC",
      summary: "这条线程已经可用，但还没有固定的 NPC 身份，后续派工时不够稳定。",
      nextStep: "如果这条线程会长期参与协作，就顺手创建成 NPC，后面回执和知识库才会更稳。",
      needsAttention: false,
      suggestTokenRotation: false,
      suggestSeatCalibration: false,
    };
  }

  return {
    code: "healthy",
    severity: "ok",
    label: "线程状态正常",
    summary: hasFinalReply ? "最近已经回过最终回复，当前更像是稳定在线状态。" : "最近已经有协作信号，可以继续接单。",
    nextStep: "暂时不用额外处理，继续观察它的下一轮回执。",
    needsAttention: false,
    suggestTokenRotation: false,
    suggestSeatCalibration: false,
  };
}

function machineRoomRecoveryPreviewKey(threadId: string) {
  return `machine-room-recovery-${threadId}`;
}

function machineRoomRecoveryCommandTitle(thread: AnyRecord) {
  const label = text(thread.name ?? thread.label ?? thread.id ?? thread.workstation_id, "目标线程");
  return `机房最小检查 / ${label}`;
}

function machineRoomRecoveryCommandBody(thread: AnyRecord, recoveryProfile: ReturnType<typeof buildWorkstationRecoverySummary>) {
  const providerLabel = platformProviderLabelFromThread(thread);
  const threadId = text(thread.id ?? thread.workstation_id, "unknown-thread");
  return [
    `请先对这条 ${providerLabel} 线程做一轮机房恢复检查。`,
    `目标线程：${threadId}`,
    `当前恢复判断：${recoveryProfile.label}`,
    `平台观察：${recoveryProfile.summary}`,
    "请先回一条最小回执，说明终端是否在线、当前目录是否正确、adapter 是否还在工作。",
    "如果线程可以继续接任务，再补一条最终回复，明确说明“当前可继续协作”或“当前阻塞点是什么”。",
  ].join("\n");
}

function isActiveStatus(status: unknown) {
  return [
    "in_progress",
    "processing",
    "active",
    "open",
    "queued",
    "routed",
    "accepted",
    "running",
    "waiting_response",
  ].includes(text(status, "").toLowerCase());
}

function isDoneStatus(status: unknown) {
  return ["done", "closed", "completed", "resolved"].includes(text(status, "").toLowerCase());
}

function isOnlineStatus(status: unknown) {
  return ["online", "ready", "active"].includes(text(status, "").toLowerCase());
}

function isComputerRunnerOnline(node: AnyRecord | null | undefined) {
  const metadata = objectRecord(node?.metadata);
  const effectiveStatus = text(node?.runner_effective_status ?? metadata.runner_effective_status, "").toLowerCase();
  if (effectiveStatus) return effectiveStatus === "online";
  const runnerStatus = text(node?.runner_status ?? metadata.runner_status, "").toLowerCase();
  const heartbeatAgeSeconds = asNumber(node?.runner_heartbeat_age_seconds ?? metadata.runner_heartbeat_age_seconds);
  const freshSeconds = asNumber(node?.runner_watch_fresh_seconds ?? metadata.runner_watch_fresh_seconds) ?? 180;
  return isOnlineStatus(runnerStatus) && heartbeatAgeSeconds !== null && heartbeatAgeSeconds <= freshSeconds;
}

function runnerWatchInfo(node: AnyRecord | null | undefined) {
  const metadata = objectRecord(node?.metadata);
  const runnerId = text(node?.runner_id ?? metadata.runner_id, "");
  const runnerStatus = text(node?.runner_status ?? metadata.runner_status, "").toLowerCase();
  const lastHeartbeat = text(node?.runner_last_heartbeat_at ?? metadata.runner_last_heartbeat_at, "");
  const heartbeatAgeSeconds = asNumber(node?.runner_heartbeat_age_seconds ?? metadata.runner_heartbeat_age_seconds);
  const freshSeconds = asNumber(node?.runner_watch_fresh_seconds ?? metadata.runner_watch_fresh_seconds) ?? 180;
  let state = text(node?.runner_watch_state ?? metadata.runner_watch_state, "").toLowerCase();
  if (!state) {
    if (!runnerId) {
      state = "unbound";
    } else if (heartbeatAgeSeconds !== null && heartbeatAgeSeconds <= freshSeconds && isOnlineStatus(runnerStatus)) {
      state = "watching";
    } else if (lastHeartbeat) {
      state = "stale";
    } else {
      state = "not_started";
    }
  }

  const ageLabel = formatSecondsAsShortAge(heartbeatAgeSeconds);
  if (state === "watching") {
    return {
      state,
      active: true,
      needsAttention: false,
      label: "常驻接单中",
      detail: ageLabel ? `最近心跳 ${ageLabel}` : "runner 正在 watch 平台任务",
    };
  }
  if (state === "stale") {
    return {
      state,
      active: false,
      needsAttention: true,
      label: "心跳超时",
      detail: ageLabel ? `最后心跳 ${ageLabel}，请重启 -Watch` : "请重启自动化心跳 / 持续接单命令",
    };
  }
  if (state === "runner_offline") {
    return {
      state,
      active: false,
      needsAttention: true,
      label: "Runner 离线",
      detail: "runner 不是在线状态，平台指令只会排队",
    };
  }
  if (state === "unbound") {
    return {
      state,
      active: false,
      needsAttention: false,
      label: "未绑定 Runner",
      detail: "先生成配对令牌并运行一键接入命令",
    };
  }
  return {
    state,
    active: false,
    needsAttention: true,
    label: "已登记未监听",
    detail: lastHeartbeat ? `最近心跳 ${formatStamp(lastHeartbeat)}，但没有常驻监听` : "已注册或已扫描，但没有收到 watch 心跳",
  };
}

function defaultActorLabel(senderType: string) {
  if (senderType === "runner") return "Runner";
  if (senderType === "human") return "人工协作者";
  if (["agent", "workstation", "thread"].includes(senderType)) return "AI/NPC";
  return "未知来源";
}

function actorLabel(message: AnyRecord, resolveDisplay: DisplayResolver) {
  const senderType = text(message.sender_type, "").toLowerCase();
  const senderId = text(message.sender_id ?? message.agent_id, "");
  return resolveDisplay(senderId, defaultActorLabel(senderType));
}

function describeAck(messages: AnyRecord[]) {
  const latest = messages.find((item) => isProgressMessage(item));
  if (!latest) return "暂无回执";
  const senderType = text(latest.sender_type, "").toLowerCase();
  if (senderType === "human") return "人工已回";
  if (["agent", "runner", "workstation", "thread"].includes(senderType)) return "AI 已回";
  return "已有回执";
}

function ownerFallback(value: AnyRecord) {
  const type = text(value.requirement_type, "").toLowerCase();
  return type.includes("human") ? "人工协作者" : "AI/NPC";
}

function requirementDisplayTitle(requirement: AnyRecord | null | undefined, resolveDisplay: DisplayResolver) {
  const rawTitle = text(requirement?.title, "");
  if (!isPollutedDisplayText(rawTitle)) return rawTitle;
  const owner = resolveDisplay(requirement?.to_agent, ownerFallback(requirement ?? {}));
  const relatedFiles = asArray(requirement?.related_files)
    .map((item) => text(item).toLowerCase())
    .join(" ");
  const requirementHints = [text(requirement?.expected_output, ""), text(requirement?.context_summary, "")]
    .join(" ")
    .toLowerCase();
  if (
    relatedFiles.includes("harvest-moon-phaser3-game") ||
    requirementHints.includes("enter") ||
    requirementHints.includes("npc")
  ) {
    return `${owner} 地图 NPC 交互任务`;
  }
  if (relatedFiles.includes("server-data") || relatedFiles.includes("project-playable-shell")) {
    return `${owner} 协作展示任务`;
  }
  if (rawTitle.toLowerCase().includes("proof") || requirementHints.includes("proof")) {
    return `${owner} 协作证明任务`;
  }
  return `${owner} 当前任务`;
}

function describeProgress(requirement: AnyRecord, latestFinal: AnyRecord | null, latestMessage: AnyRecord | null) {
  if (isDoneStatus(requirement.status) || latestFinal) return "已完成";
  if (latestMessage && isActiveStatus(latestMessage.status)) return "处理中";
  if (isActiveStatus(requirement.status)) return "处理中";
  return "待接单";
}

function latestMessageAt(message: AnyRecord | null) {
  if (!message) return 0;
  return new Date(text(message.created_at ?? message.updated_at, "1970-01-01")).getTime();
}

function requirementCreatedAt(requirement: AnyRecord) {
  return new Date(text(requirement.created_at, "1970-01-01")).getTime();
}

function requirementActivityAt(requirement: AnyRecord, messageMap: RequirementMessageMap) {
  const requirementId = text(requirement.id ?? requirement.requirement_id, "");
  const latestRequirementMessageAt = (messageMap.get(requirementId) ?? []).reduce(
    (max, item) => Math.max(max, latestMessageAt(item)),
    0,
  );
  const latestResponseAt = new Date(text(requirement.last_response_at, "1970-01-01")).getTime();
  const updatedAt = new Date(text(requirement.updated_at, "1970-01-01")).getTime();
  return Math.max(latestRequirementMessageAt, latestResponseAt, updatedAt, requirementCreatedAt(requirement));
}

function buildRequirementMessageMap(collaborationMessages: AnyRecord[]): RequirementMessageMap {
  const messageMap = new Map<string, AnyRecord[]>();
  collaborationMessages.forEach((message) => {
    const requirementId = text(message.requirement_id, "");
    if (!requirementId) return;
    const bucket = messageMap.get(requirementId) ?? [];
    bucket.push(message);
    messageMap.set(requirementId, bucket);
  });
  return messageMap;
}

function seatSignalAt(seat: MapSeatPayload) {
  const raw = text(seat.lastSignalAt ?? seat.finalReplyAt ?? seat.minimalAckAt, "");
  if (!raw) return 0;
  const value = new Date(raw).getTime();
  return Number.isFinite(value) ? value : 0;
}

function seatBridgePriorityScore(seat: MapSeatPayload) {
  const issue = seatBridgeIssueLabel(seat);
  if (issue === "缺 heartbeat") return 4;
  if (issue?.startsWith("心跳 ")) return 3;
  if (issue === "等待首次回写") return 2;
  if (issue === "本地状态未更新") return 1;
  return 0;
}

function seatProgressWarningPriority(seat: MapSeatPayload) {
  if (seat.staleAfterAck) return 3;
  if (seat.progressWarningLabel === "最小回执偏晚") return 2;
  if (seat.progressWarningLabel === "进度信号待归一") return 1;
  return 0;
}

function isPrimaryCoordinatorSeat(seat: MapSeatPayload) {
  return [
    seat.name,
    seat.role,
    seat.sourceThreadId,
    seat.currentRequirement,
    seat.autonomyBridgeLabel,
  ].some((value) => isPrimaryCoordinatorSeatLabel(value));
}

function pickStarterSeat(seats: MapSeatPayload[]) {
  return (
    seats
      .slice()
      .sort((left, right) => {
        const leftRank =
          seatProgressWarningPriority(left) * 6 +
          seatBridgePriorityScore(left) * 2 +
          Number(Boolean(left.finalReply)) * 4 +
          Number(Boolean(left.minimalAck)) * 3 +
          Number(Boolean(left.currentRequirement)) * 2 +
          Number(left.status === "active");
        const rightRank =
          seatProgressWarningPriority(right) * 6 +
          seatBridgePriorityScore(right) * 2 +
          Number(Boolean(right.finalReply)) * 4 +
          Number(Boolean(right.minimalAck)) * 3 +
          Number(Boolean(right.currentRequirement)) * 2 +
          Number(right.status === "active");
        return rightRank - leftRank || seatSignalAt(right) - seatSignalAt(left);
      })[0] ?? null
  );
}

function buildStarterDrawer(options: {
  hasProtectedDataGap: boolean;
  focusSeat: MapSeatPayload | null;
  finalReplyFeed: FeedItem[];
  recommendedAction: string;
  reloginPath: string;
}): StarterDrawerModel {
  const { hasProtectedDataGap, focusSeat, finalReplyFeed, recommendedAction, reloginPath } = options;
  const seatName = focusSeat?.name || "当前 NPC";
  const stepInspectNpc: StarterDrawerStep = {
    id: "inspect-npc",
    title: `找 ${seatName}`,
    detail: focusSeat
      ? `先看 ${seatName} 的最近任务、最小回执和固定知识库。`
      : "先找一个 NPC，看它当前负责的任务和固定知识库。",
    done: Boolean(focusSeat),
  };
  const stepReadAck: StarterDrawerStep = {
    id: "read-ack",
    title: "盯最小回执",
    detail: focusSeat?.minimalAck
      ? `已经有最小回执：${focusSeat.minimalAck}`
      : "看到“已接单/自动推进中”后，先确认最小回执，不用一上来就追最终答案。",
    done: Boolean(focusSeat?.minimalAck),
  };
  const stepReadFinal: StarterDrawerStep = {
    id: "read-final",
    title: "看最终回复",
    detail: focusSeat?.finalReply
      ? `最近最终回复：${focusSeat.finalReply}`
      : finalReplyFeed.length
        ? `项目里已经有 ${finalReplyFeed.length} 条最终回复，可以去结果池看收口。`
        : "等线程把结果收口后，再去最终回复池确认结果。",
    done: Boolean(focusSeat?.finalReply || finalReplyFeed.length),
  };

  if (hasProtectedDataGap) {
    return {
      title: "先恢复登录态",
      summary: "当前项目页入口壳里的 2D 开发者模式入口还能看，但受保护协作数据没拿到。先登录，再继续玩任务链。",
      hint: "恢复后，第一层只看当前主线；细节继续进 NPC 管理和协作消息池。",
      statusLabel: "待登录",
      ctaLabel: "去登录页",
      ctaPanel: "exchange",
      ctaSeatId: null,
      ctaHref: reloginPath,
      secondaryLabel: "打开 NPC 管理",
      secondaryPanel: "npc-create",
      secondarySeatId: null,
      secondaryHref: null,
      steps: [
        {
          id: "login",
          title: "恢复受保护数据",
          detail: "重新登录后，最小回执、最终回复和 requirement 才会一起回来。",
          done: false,
        },
        stepInspectNpc,
        stepReadFinal,
      ],
    };
  }

  if (!focusSeat) {
    return {
      title: "先招一个 NPC",
      summary: "小白第一步不用研究系统。先去线程列表找一条线程，再把它绑定成地图里的 NPC。",
      hint: "先用两层：电脑管理找线程，NPC 管理负责创建和落位。",
      statusLabel: "待起步",
      ctaLabel: "看线程列表",
      ctaPanel: "machine-room",
      ctaSeatId: null,
      ctaHref: null,
      secondaryLabel: "创建 NPC",
      secondaryPanel: "npc-create",
      secondarySeatId: null,
      secondaryHref: null,
      steps: [
        {
          id: "threads",
          title: "看真实线程",
          detail: "优先选最近在线、职责清楚的线程。",
          done: false,
        },
        {
          id: "bind",
          title: "绑定成 NPC",
          detail: "每创建一个 NPC，地图里都会出现一个同形象、带名字的可交互角色。",
          done: false,
        },
        {
          id: "enter",
          title: "回地图按 Enter",
          detail: "按 Enter 打开 NPC 面板，看最近任务、最小回执和最终回复。",
          done: false,
        },
      ],
    };
  }

  if (focusSeat.finalReply) {
    return {
      title: `先看 ${seatName} 的收口结果`,
      summary: `${seatName} 已经给出了最终回复。先看结果，再决定下一条 requirement。`,
      hint: recommendedAction,
      statusLabel: "已收口",
      ctaLabel: "看最终回复池",
      ctaPanel: "exchange",
      ctaSeatId: null,
      ctaHref: null,
      secondaryLabel: `查看 ${seatName}`,
      secondaryPanel: "npc-create",
      secondarySeatId: focusSeat.id,
      secondaryHref: null,
      steps: [stepInspectNpc, stepReadAck, stepReadFinal],
    };
  }

  if (focusSeat.staleAfterAck) {
    const bridgeIssue = seatBridgeIssueLabel(focusSeat);
    return {
      title: `先处理 ${seatName} 的停滞链路`,
      summary: `${seatName} 已经给过最小回执，但后续 ${formatQueueAge(focusSeat.staleAfterAckMinutes) || "一段时间"} 没再收口${bridgeIssue ? `，当前更像 ${bridgeIssue}` : ""}。现在先别分心补别的入口，先把这条链重新推起来。`,
      hint: recommendedAction,
      statusLabel: bridgeIssue || "停在最小回执",
      ctaLabel: `查看 ${seatName}`,
      ctaPanel: "npc-create",
      ctaSeatId: focusSeat.id,
      ctaHref: null,
      secondaryLabel: "看当前主线",
      secondaryPanel: "exchange",
      secondarySeatId: null,
      secondaryHref: null,
      steps: [stepInspectNpc, stepReadAck, stepReadFinal],
    };
  }

  if (focusSeat.minimalAck) {
    const progressWarning = focusSeat.progressWarningLabel;
    const summary =
      progressWarning === "最小回执偏晚"
        ? `${seatName} 已重新对齐当前任务，但这条最小回执来得偏晚。先继续盯住收口，不要把它误判成已经彻底卡死。`
        : progressWarning === "进度信号待归一"
          ? `${seatName} 已在继续推进，但当前 live API 还把过程信号记成旧的 final reply 语义。先盯住结果收口，再继续清理信号归一。`
          : `${seatName} 已经给了最小回执。现在先别切太多页面，盯住它把结果收口。`;
    return {
      title: `盯住 ${seatName} 的当前任务`,
      summary,
      hint: recommendedAction,
      statusLabel: progressWarning || focusSeat.progressHealthLabel || "自动推进中",
      ctaLabel: `查看 ${seatName}`,
      ctaPanel: "npc-create",
      ctaSeatId: focusSeat.id,
      ctaHref: null,
      secondaryLabel: "看当前主线",
      secondaryPanel: "exchange",
      secondarySeatId: null,
      secondaryHref: null,
      steps: [stepInspectNpc, stepReadAck, stepReadFinal],
    };
  }

  if (focusSeat.currentRequirement) {
    return {
      title: `先去找 ${seatName}`,
      summary: `${seatName} 当前已经挂着任务。第一步先看它负责什么，再等最小回执。`,
      hint: recommendedAction,
      statusLabel: "待回执",
      ctaLabel: `查看 ${seatName}`,
      ctaPanel: "npc-create",
      ctaSeatId: focusSeat.id,
      ctaHref: null,
      secondaryLabel: "看推荐动作",
      secondaryPanel: "exchange",
      secondarySeatId: null,
      secondaryHref: null,
      steps: [stepInspectNpc, stepReadAck, stepReadFinal],
    };
  }

  return {
    title: "先打开 NPC 管理看主线",
    summary: "先不要全看。NPC 管理里先看当前 NPC、对话和最终回复池。",
    hint: recommendedAction,
    statusLabel: "轻引导",
    ctaLabel: "打开 NPC 管理",
    ctaPanel: "npc-create",
    ctaSeatId: null,
    ctaHref: null,
    secondaryLabel: `查看 ${seatName}`,
    secondaryPanel: "npc-create",
    secondarySeatId: focusSeat.id,
    secondaryHref: null,
    steps: [stepInspectNpc, stepReadAck, stepReadFinal],
  };
}

function buildModeEntries(options: {
  hasProtectedDataGap: boolean;
  starterDrawer: StarterDrawerModel;
  starterSeat: MapSeatPayload | null;
  stalledSeatSummary: ReturnType<typeof buildStalledSeatSummary>;
  activeThreadCount: number;
  seatCount: number;
  finalReplyCount: number;
  recommendedAction: string;
  reloginPath: string;
  projectPlazaPath: string;
  modeChoicePath: string;
  modeBoardPaths: FutureModePathMap<string>;
  modeShellPaths: FutureModePathMap<string>;
  modeDefinitionsById: Map<string, ProjectModeDefinition>;
  projectId: string;
  projectPath: string;
}): ModeEntry[] {
  const {
    hasProtectedDataGap,
    starterDrawer,
    starterSeat,
    stalledSeatSummary,
    activeThreadCount,
    seatCount,
    finalReplyCount,
    recommendedAction,
    reloginPath,
    projectPlazaPath,
    modeChoicePath,
    modeBoardPaths,
    modeShellPaths,
    modeDefinitionsById,
    projectId,
    projectPath,
  } = options;
  const liveModeDefinition = modeDefinitionsById.get("2d-dev");
  const twoDEduModeDefinition = modeDefinitionsById.get("2d-edu");
  const threeDDevModeDefinition = modeDefinitionsById.get("3d-dev");
  const threeDEduModeDefinition = modeDefinitionsById.get("3d-edu");
  const liveModeLayerHint = projectId ? `inside ${projectPath}` : projectEntryLiveModeLayerHint;
  const starterSeatName = starterSeat?.name || "当前 NPC";
  const starterSeatIssue = starterSeat ? seatBridgeIssueLabel(starterSeat) : null;
  const starterSeatProgressWarning = starterSeat?.progressWarningLabel ?? null;
  const seatSignal = stalledSeatSummary?.shortLabel
    ? stalledSeatSummary.shortLabel
    : starterSeat?.staleAfterAck
    ? starterSeatIssue
      ? `${starterSeatName} ${starterSeatIssue}`
      : `${starterSeatName} 停在最小回执`
    : starterSeat?.minimalAck && !starterSeat?.finalReply && starterSeatProgressWarning
    ? `${starterSeatName} ${starterSeatProgressWarning}`
    : starterSeat?.minimalAck
    ? `${starterSeatName} 已给最小回执`
    : starterSeat?.currentRequirement
      ? `${starterSeatName} 已挂当前任务`
      : seatCount
        ? "已有 NPC 可继续绑定和分工"
        : "还没有可交互 NPC";

  const currentModeBlockerLabel = hasProtectedDataGap
    ? "受保护协作数据未恢复"
    : starterSeat?.staleAfterAck
      ? "当前有席位停在最小回执"
    : starterSeat?.minimalAck && !starterSeat?.finalReply && starterSeatProgressWarning === "最小回执偏晚"
      ? "当前回执偏晚，需要继续盯住"
    : starterSeat?.minimalAck && !starterSeat?.finalReply && starterSeatProgressWarning === "进度信号待归一"
      ? "当前进度信号待归一"
    : starterSeat?.minimalAck && !starterSeat?.finalReply
      ? "当前没有硬阻塞，主要等线程收口"
      : starterSeat?.currentRequirement && !starterSeat?.minimalAck
        ? "当前还缺最小回执"
        : seatCount
          ? "主路径已成形，继续补协作闭环"
          : "先把真实线程长成 NPC";
  const currentModeBlockerDetail = hasProtectedDataGap
    ? "公开页还能看，但 requirement、最小回执和最终回复还没恢复，需要先登录。"
    : starterSeat?.staleAfterAck
      ? `当前先把 ${starterSeatName} 这条停滞链路重新推起来，比继续堆新入口或新壳层更重要。`
    : starterSeat?.minimalAck && !starterSeat?.finalReply && starterSeatProgressWarning === "最小回执偏晚"
      ? `当前 ${starterSeatName} 已重新对齐 live 任务，但最小回执明显偏晚。先继续盯住这条链的结果收口，再决定是否重新派单。`
    : starterSeat?.minimalAck && !starterSeat?.finalReply && starterSeatProgressWarning === "进度信号待归一"
      ? `当前 ${starterSeatName} 仍在推进，但 live API 还把过程信号记成旧的 final reply 语义。先盯住真实收口，再继续清理信号归一。`
    : starterSeat?.minimalAck && !starterSeat?.finalReply
      ? `先盯住 ${starterSeatName} 继续推进，不要为了补模式入口去打断当前农场主线。`
      : starterSeat?.currentRequirement && !starterSeat?.minimalAck
        ? `地图和管理器都在，先等 ${starterSeatName} 回最小回执，再判断下一层入口。`
        : seatCount
          ? "当前页面已经能承载地图、管理器、线程和 NPC，只需要把入口说明做得更诚实。"
          : "当前地图底座已就位，但还需要真实线程和 NPC 绑定，入口才能对小白形成闭环。";

  return [
    {
      id: "2d-dev",
      label: liveModeDefinition?.label ?? "2D 开发者模式入口",
      state: liveModeDefinition?.state ?? "当前真入口",
      detail: liveModeDefinition?.detail ?? "当前唯一真入口，直接进入农场地图、管理器抽屉和 AI 协作开发。",
      active: true,
      readinessLabel: starterDrawer.statusLabel,
      readinessDetail: starterDrawer.summary,
      blockerLabel: currentModeBlockerLabel,
      blockerDetail: currentModeBlockerDetail,
      nextLabel: starterDrawer.ctaLabel,
      nextDetail: recommendedAction,
      signals: [`活跃线程 ${activeThreadCount} 条`, `NPC ${seatCount} 个`, `最终回复 ${finalReplyCount} 条`, seatSignal],
      routeRuleLabel: "今天的真实落点",
      routeRuleDetail:
        liveModeDefinition?.branchRule ??
        `现在已经先放了真实的 \`${modeChoicePath}\` 当前项目分流板，用来固定 \`/projects\` 之后的未来分支；但今天的 live 2D 路径仍不需要额外绕进去。真实用户路径就是先到 \`/projects\` 选项目，再进入 \`${projectPath}\` 这个当前项目页入口壳；最后落到壳内的 2D 开发者模式 live 层，而不是新路由。`,
      entrySteps: [
        ...buildSharedModeFrontDoorSteps({
          reloginPath,
          projectPlazaPath,
          loginDetail: "这里只负责登录和恢复协作读取，不负责模式分流。",
          projectDetail: "这里是当前唯一项目管理入口页，只负责选项目、接受邀请和创建项目。",
        }),
        {
          label: "当前项目页入口壳",
          status: "已存在",
          detail: "进入项目后，这里直接承接 live 的 2D 开发者模式入口，不再额外插一个 mode choice 步骤。",
          href: projectPath,
          routeHint: projectPath,
          layerKind: "入口壳",
          branchState: "当前落点",
        },
        {
          label: liveModeDefinition?.label ?? "2D 开发者模式入口",
          status: liveModeDefinition?.state ?? "当前真入口",
          detail: "当前真实落点就是农场地图、管理器和 NPC 协作开发面。",
          href: null,
          routeHint: liveModeLayerHint,
          layerKind: "模式层",
          branchState: "live mode",
        },
      ],
      layers: [
        {
          label: "模式选择层",
          status: "当前已落地",
          detail: "项目页顶部现在明确说明四模式，但只把 2D 开发者模式当成真入口。",
        },
        {
          label: "农场地图层",
          status: "当前主底座",
          detail: "真实可玩的农场仍是当前页面基底，不被协作面板替换。",
        },
        {
          label: "新手任务层",
          status: "轻引导已接入",
          detail: "用左侧新手任务抽屉把人引到当前推荐动作，而不是一上来堆满日志。",
        },
        {
          label: "协作管理器层",
          status: "细节入口已接入",
          detail: "管理器负责线程列表、NPC、信息交流、Git 和 Skill 这些深层操作。",
        },
        {
          label: "真实执行层",
          status: seatCount ? "已开始闭环" : "待继续补齐",
          detail: seatCount
            ? "真实线程、NPC 席位和 requirement/ack/final-reply 闭环已经开始接上当前主线。"
            : "下一步继续把真实线程和 NPC 闭环长稳，让入口不是只有地图而是可执行的开发流。",
        },
      ],
      actions: [
        {
          label: starterDrawer.ctaLabel,
          href: starterDrawer.ctaHref,
          panel: starterDrawer.ctaHref ? null : starterDrawer.ctaPanel,
          seatId: starterDrawer.ctaSeatId,
          emphasis: "primary",
        },
        {
          label: starterDrawer.secondaryLabel,
          href: starterDrawer.secondaryHref,
          panel: starterDrawer.secondaryHref ? null : starterDrawer.secondaryPanel,
          seatId: starterDrawer.secondarySeatId,
          emphasis: "ghost",
        },
      ],
    },
    {
      id: "2d-edu",
      label: twoDEduModeDefinition?.label ?? "2D 教育版入口",
      state: twoDEduModeDefinition?.state ?? "排队中",
      detail:
        twoDEduModeDefinition?.detail ??
        "复用当前农场地图和管理器骨架，但要改成 NPC 发任务、小白跟着做的教学闭环。",
      active: false,
      readinessLabel: "只保留计划，不开放独立入口",
      readinessDetail: "不能把教育模式塞进当前开发者管理器里，也不能假装现在已经有教学任务链。",
      blockerLabel: "缺教学任务链和引导 NPC",
      blockerDetail: "还没有把购买器件、接线、环境准备、代码运行和结果验收串成小白可跟的 2D 教学流程。",
      nextLabel: "先复用 2D 开发者底座",
      nextDetail: "先把当前 2D 开发者模式入口说明做实，再抽教育版的新手任务、讲解文案和教学用结果面板。",
      signals: ["依赖当前农场地图", "依赖教学 NPC 任务链", "依赖新手结果闭环"],
      routeRuleLabel: "当前占位分流点",
      routeRuleDetail:
        twoDEduModeDefinition?.branchRule ??
        `2D 教育版不应该从登录后直接硬跳，也不应该塞进当前项目内的开发管理器；它的分流点现在已经先用真实的 \`${modeBoardPaths["2d-edu"]}\` 当前项目分流板钉在 \`/projects\` 之后，但目标模式面仍未开放。`,
      entrySteps: [
        ...buildSharedModeFrontDoorSteps({
          reloginPath,
          projectPlazaPath,
          loginDetail: "登录页仍只负责认证，不提前决定教育或开发分流。",
          projectDetail: "仍然先从当前项目管理入口页选项目，而不是在登录后立即分流模式。",
        }),
        ...buildFutureModeTailSteps({
          boardDetail: `真实的 \`${modeBoardPaths["2d-edu"]}\` 现在先作为占位分流层，未来再从这里把用户分到 2D 教育版，而不是直接掉进当前开发管理器。`,
          boardHref: modeBoardPaths["2d-edu"],
          shellLabel: twoDEduModeDefinition?.label ?? "2D 教育版入口",
          shellDetail: `真实的 \`${modeShellPaths["2d-edu"]}\` 现在先把 2D 教育版的下游壳层钉住，后续再接教学 NPC、任务链和结果闭环。`,
          shellHref: modeShellPaths["2d-edu"],
        }),
      ],
      layers: [
        {
          label: "模式选择层",
          status: "只保留规划",
          detail: "先让用户知道 2D 教育版会独立存在，但现在不生成伪入口。",
        },
        {
          label: "教学地图层",
          status: "未落地",
          detail: "要把当前地图改造成小白按任务逐步学习的节奏，而不是当前开发主线地图。",
        },
        {
          label: "任务 NPC 层",
          status: "未落地",
          detail: "教育版 NPC 需要负责发任务、解释下一步和验收结果。",
        },
        {
          label: "学习结果层",
          status: "未落地",
          detail: "还缺一个更面向教学的结果确认层，而不是直接复用当前开发结果池。",
        },
      ],
      actions: buildFutureModeActions({
        primaryLabel: "打开 2D 教育版占位壳",
        primaryHref: modeShellPaths["2d-edu"],
        boardHref: modeBoardPaths["2d-edu"],
      }),
    },
    {
      id: "3d-dev",
      label: threeDDevModeDefinition?.label ?? "3D 开发者模式入口",
      state: threeDDevModeDefinition?.state ?? "后续接入",
      detail:
        threeDDevModeDefinition?.detail ??
        "未来切到 Unity 或自研 3D 世界时，继续复用当前 requirement / ack / final reply 协作内核。",
      active: false,
      readinessLabel: "先保留方向，不切走当前 2D 主线",
      readinessDetail: "3D 开发者模式的价值在于替换世界载体，不是现在就重写现有平台协作流程。",
      blockerLabel: "缺 3D 世界壳和桥接层",
      blockerDetail: "目前还没有稳定的 3D 世界、地图交互层和与当前协作数据的真实桥接，不能冒充现成入口。",
      nextLabel: "等 2D 开发者模式跑稳后再切",
      nextDetail: "先把当前农场地图入口、管理器主线和 NPC 协作内核跑顺，再决定何时迁移到 3D 世界。",
      signals: ["依赖 3D 世界运行壳", "依赖协作数据桥", "依赖 Unity / WebGL 接入"],
      routeRuleLabel: "当前占位分流点",
      routeRuleDetail:
        threeDDevModeDefinition?.branchRule ??
        `3D 开发者模式的入口应当在 \`/projects\` 之后与 2D 并列分流，而不是在当前项目页内部偷偷替换 2D 农场底座；这个分流点现在已经先用真实的 \`${modeBoardPaths["3d-dev"]}\` 当前项目分流板钉住。`,
      entrySteps: [
        ...buildSharedModeFrontDoorSteps({
          reloginPath,
          projectPlazaPath,
          loginDetail: "登录页未来仍只负责认证，不提前决定 2D 或 3D。",
          projectDetail: "未来仍先在项目管理入口页选项目，而不是在这里直接切换世界维度。",
        }),
        ...buildFutureModeTailSteps({
          boardDetail: `真实的 \`${modeBoardPaths["3d-dev"]}\` 现在先负责把 3D 开发者模式钉成显式分支占位，而不是在当前项目页里偷偷替换 2D 底座。`,
          boardHref: modeBoardPaths["3d-dev"],
          shellLabel: threeDDevModeDefinition?.label ?? "3D 开发者模式入口",
          shellDetail: `真实的 \`${modeShellPaths["3d-dev"]}\` 现在先把 3D 开发者模式的下游壳层钉住，后续再接 3D 世界壳和协作桥接层。`,
          shellHref: modeShellPaths["3d-dev"],
        }),
      ],
      layers: [
        {
          label: "模式选择层",
          status: "方向已定",
          detail: "3D 开发者模式会和 2D 并列存在，但今天不抢当前真入口。",
        },
        {
          label: "3D 世界层",
          status: "未落地",
          detail: "还没有可替换农场地图的稳定 3D 世界壳。",
        },
        {
          label: "协作桥接层",
          status: "未落地",
          detail: "还没把 requirement、NPC、管理器和世界内交互接到同一套 3D 表面。",
        },
        {
          label: "执行席位层",
          status: "可复用当前内核",
          detail: "真实线程和 NPC 协作内核可以复用，但需要新的 3D 呈现外壳承接。",
        },
      ],
      actions: buildFutureModeActions({
        primaryLabel: "打开 3D 开发者占位壳",
        primaryHref: modeShellPaths["3d-dev"],
        boardHref: modeBoardPaths["3d-dev"],
      }),
    },
    {
      id: "3d-edu",
      label: threeDEduModeDefinition?.label ?? "3D 教育版模式入口",
      state: threeDEduModeDefinition?.state ?? "最后补齐",
      detail:
        threeDEduModeDefinition?.detail ??
        "最终要把 3D 世界、教学任务和硬件实验叠成更沉浸的教学入口，但现在只保留产品方位。",
      active: false,
      readinessLabel: "先不要跳级",
      readinessDetail: "3D 教育版是远期组合项，不能先于 2D 教育版和 3D 开发者世界底座落地。",
      blockerLabel: "同时缺 3D 世界和教学内容",
      blockerDetail: "目前既没有 3D 场景运行壳，也没有可复用的教育任务链、实验脚本和引导节奏。",
      nextLabel: "保持规划，不做伪入口",
      nextDetail: "先完成 2D 开发者入口，再做 2D 教育版，再考虑 3D 世界和其教育层。",
      signals: ["依赖 3D 世界", "依赖 3D 教学任务", "依赖硬件实验引导"],
      routeRuleLabel: "当前占位分流点",
      routeRuleDetail:
        threeDEduModeDefinition?.branchRule ??
        `3D 教育版属于最远期分支，入口同样应放在 \`/projects\` 后的 mode choice 层，而不是混入当前 2D 开发路径；这个分流点现在已经先用真实的 \`${modeBoardPaths["3d-edu"]}\` 当前项目分流板固定下来。`,
      entrySteps: [
        ...buildSharedModeFrontDoorSteps({
          reloginPath,
          projectPlazaPath,
          loginDetail: "登录页未来仍只负责认证，不提前决定教育或开发分流。",
          projectDetail: "未来仍先经由项目管理入口页，而不是在登录后直接跳到 3D 教学面。",
        }),
        ...buildFutureModeTailSteps({
          boardDetail: `真实的 \`${modeBoardPaths["3d-edu"]}\` 现在先把 3D 教育版列成独立选择占位，而不是埋在当前开发路径后面。`,
          boardHref: modeBoardPaths["3d-edu"],
          shellLabel: threeDEduModeDefinition?.label ?? "3D 教育版入口",
          shellDetail: `真实的 \`${modeShellPaths["3d-edu"]}\` 现在先把 3D 教育版的下游壳层钉住，后续再接 3D 世界、教学任务和硬件实验层。`,
          shellHref: modeShellPaths["3d-edu"],
        }),
      ],
      layers: [
        {
          label: "模式选择层",
          status: "只保留远期规划",
          detail: "当前只说明它未来存在，不给出会误导用户的立即入口。",
        },
        {
          label: "3D 教学世界层",
          status: "未落地",
          detail: "需要先有 3D 世界，再谈沉浸式教学路线。",
        },
        {
          label: "教学 NPC 层",
          status: "未落地",
          detail: "需要能在 3D 世界里连续发任务、解释、验收的 NPC 引导层。",
        },
        {
          label: "硬件实验层",
          status: "未落地",
          detail: "还没有 3D 教学版专属的实验、硬件接线和结果回流设计。",
        },
      ],
      actions: buildFutureModeActions({
        primaryLabel: "打开 3D 教育版占位壳",
        primaryHref: modeShellPaths["3d-edu"],
        boardHref: modeBoardPaths["3d-edu"],
      }),
    },
  ];
}

function isRealThreadRequirement(requirement: AnyRecord) {
  return text(requirement.to_agent, "").toLowerCase().startsWith("codex-session-");
}

function selectFreshestRequirement(
  requirements: AnyRecord[],
  messageMap: RequirementMessageMap,
  predicate: (requirement: AnyRecord) => boolean,
) {
  return (
    requirements
      .filter((item) => predicate(item))
      .slice()
      .sort((left, right) => {
        const activityDelta = requirementActivityAt(right, messageMap) - requirementActivityAt(left, messageMap);
        if (activityDelta !== 0) return activityDelta;
        const realThreadDelta = Number(isRealThreadRequirement(right)) - Number(isRealThreadRequirement(left));
        if (realThreadDelta !== 0) return realThreadDelta;
        return requirementCreatedAt(right) - requirementCreatedAt(left);
      })[0] ?? null
  );
}

function latestDispatchAt(task: AnyRecord | null) {
  const dispatch = task?.latest_dispatch;
  if (!dispatch) return 0;
  return new Date(text(dispatch.updated_at ?? dispatch.created_at, "1970-01-01")).getTime();
}

function selectLatestDispatchTask(tasks: AnyRecord[]) {
  return (
    tasks
      .filter((task) => task?.latest_dispatch)
      .slice()
      .sort((left, right) => latestDispatchAt(right) - latestDispatchAt(left))[0] ?? null
  );
}

function latestProgressSignalMessage(requirement: AnyRecord, messageMap: RequirementMessageMap) {
  const requirementId = text(requirement.id ?? requirement.requirement_id, "");
  const messages = [...(messageMap.get(requirementId) ?? [])].sort((left, right) => latestMessageAt(right) - latestMessageAt(left));
  return (
    messages.find((message) => {
      const messageType = text(message.message_type, "").toLowerCase();
      const messageStatus = text(message.status, "").toLowerCase();
      if (messageType === "requirement_progress_ack") return messageStatus === "in_progress";
      if (messageType === "requirement_final_reply") return messageStatus === "in_progress";
      return ["agent_report", "runner_ack", "runner_result"].includes(messageType);
    }) ?? null
  );
}

function latestRequirementFinalReplyMessage(requirement: AnyRecord, messageMap: RequirementMessageMap) {
  const requirementId = text(requirement.id ?? requirement.requirement_id, "");
  const messages = [...(messageMap.get(requirementId) ?? [])].sort((left, right) => latestMessageAt(right) - latestMessageAt(left));
  return messages.find((message) => isFinalReplyMessage(message)) ?? null;
}

function requirementProgressLagMinutes(requirement: AnyRecord, messageMap: RequirementMessageMap) {
  const progressSignal = latestProgressSignalMessage(requirement, messageMap);
  const createdAt = requirementCreatedAt(requirement);
  const progressAt = latestMessageAt(progressSignal);
  if (!progressSignal || createdAt <= 0 || progressAt <= 0) return null;
  return Math.max(0, Math.floor((progressAt - createdAt) / 60000));
}

function requirementStaleAfterAck(requirement: AnyRecord, messageMap: RequirementMessageMap) {
  const progressSignal = latestProgressSignalMessage(requirement, messageMap);
  const finalReply = latestRequirementFinalReplyMessage(requirement, messageMap);
  if (!progressSignal || finalReply) return false;
  const ageMinutes = queueAgeMinutes(latestMessageAt(progressSignal));
  return ageMinutes !== null && ageMinutes >= STALE_AFTER_ACK_MINUTES;
}

function buildFinalReplyFeed(
  requirements: AnyRecord[],
  messageMap: RequirementMessageMap,
  resolveDisplay: DisplayResolver,
): FeedItem[] {
  return requirements
    .map((requirement, index) => {
      const requirementId = text(requirement.id ?? requirement.requirement_id, `requirement-${index + 1}`);
      const messages = [...(messageMap.get(requirementId) ?? [])].sort(
        (left, right) => latestMessageAt(right) - latestMessageAt(left),
      );
      const latestFinal = messages.find((item) => isFinalReplyMessage(item)) ?? null;
      const latestMessage = messages[0] ?? null;
      if (!latestFinal) return null;
      return {
        id: requirementId,
        title: requirementDisplayTitle(requirement, resolveDisplay),
        route: routeLabel(requirement),
        target: resolveDisplay(requirement.to_agent, ownerFallback(requirement)),
        body: shortText(latestFinal.body, "没有额外说明", 96),
        meta: `${actorLabel(latestFinal, resolveDisplay)} / ${formatStamp(latestFinal.created_at ?? latestFinal.updated_at)}`,
        ackLabel: describeAck(messages),
        progressLabel: describeProgress(requirement, latestFinal, latestMessage),
        replyOwnerLabel: actorLabel(latestFinal, resolveDisplay),
        finalReplyAt: latestMessageAt(latestFinal),
      } satisfies FeedItem;
    })
    .filter((item): item is FeedItem => Boolean(item))
    .sort((left, right) => right.finalReplyAt - left.finalReplyAt)
    .slice(0, 8);
}

function buildStandaloneFinalReplyFeed(messages: AnyRecord[], resolveDisplay: DisplayResolver): FeedItem[] {
  return sortedByUpdatedAt(
    messages.filter((message) => {
      const type = text(message.message_type, "").toLowerCase();
      return type === "agent_result" && isDoneStatus(message.status) && !text(message.requirement_id, "");
    }),
  )
    .map((message, index) => {
      const messageId = text(message.id, `agent-result-${index + 1}`);
      const senderLabel = actorLabel(message, resolveDisplay);
      return {
        id: `agent-result-${messageId}`,
        title: safeDisplayTitle(message.title ?? message.body, "平台协作最终回复"),
        route: "平台协作",
        target: resolveDisplay(message.sender_id ?? message.agent_id, senderLabel),
        body: shortText(message.body, "没有额外说明", 96),
        meta: `${senderLabel} / ${formatStamp(message.created_at ?? message.updated_at)}`,
        ackLabel: "平台指令已收口",
        progressLabel: "已完成",
        replyOwnerLabel: senderLabel,
        finalReplyAt: latestMessageAt(message),
      } satisfies FeedItem;
    })
    .slice(0, 8);
}

function buildRecommendedAction(
  requirements: AnyRecord[],
  messageMap: RequirementMessageMap,
  relayTimeline: AnyRecord[],
  tasks: AnyRecord[],
  finalReplyFeed: FeedItem[],
  resolveDisplay: DisplayResolver,
  focusedCodexCommand?: CodexInboxFeedItem | null,
  focusedQueuedCount = 0,
) {
  if (focusedCodexCommand?.isQueued) {
    return `${focusAnchorLabel(focusedCodexCommand.target, focusedCodexCommand.requirementId)} 仍在平台队列中${focusedQueuedCount > 1 ? `，同线程共 ${focusedQueuedCount} 条排队` : ""}${focusedCodexCommand.queueStartedAtLabel ? `，排队起点 ${focusedCodexCommand.queueStartedAtLabel}` : ""}${focusedCodexCommand.queueAgeLabel ? `，已等待 ${focusedCodexCommand.queueAgeLabel}` : ""}${focusedCodexCommand.queueStateLabel ? `，当前判断为 ${focusedCodexCommand.queueStateLabel}` : ""}，优先等待线程最小回执和宿主桥接回写。`;
  }

  const latestDispatchTask = selectLatestDispatchTask(tasks);
  const stalledRequirement = selectFreshestRequirement(
    requirements,
    messageMap,
    (item) => isActiveStatus(item.status) && !isDoneStatus(item.status) && requirementStaleAfterAck(item, messageMap),
  );
  if (stalledRequirement) {
    const stalledAge = queueAgeMinutes(latestMessageAt(latestProgressSignalMessage(stalledRequirement, messageMap)));
    return `优先处理 ${requirementDisplayTitle(stalledRequirement, resolveDisplay)}：它已停在最小回执后 ${formatQueueAge(stalledAge) || "一段时间"}，更适合重新派单、补心跳检查或转人工接手。`;
  }

  const activeRequirement = selectFreshestRequirement(
    requirements,
    messageMap,
    (item) => isActiveStatus(item.status) && !isDoneStatus(item.status),
  );
  if (activeRequirement) {
    return `继续盯住 ${requirementDisplayTitle(activeRequirement, resolveDisplay)}，等待最终回复。`;
  }

  const pendingRequirement = selectFreshestRequirement(requirements, messageMap, (item) => !isDoneStatus(item.status));
  if (pendingRequirement) {
    return `优先补齐 ${requirementDisplayTitle(pendingRequirement, resolveDisplay)} 的最小回执。`;
  }

  const pendingRelay = relayTimeline.find((item) => text(item.message_type, "").toLowerCase() === "runner_command");
  if (pendingRelay) {
    return `检查真实线程回执：${safeDisplayTitle(pendingRelay.title ?? pendingRelay.body, "线程回执")}。`;
  }

  if (latestDispatchTask) {
    return `把 ${safeDisplayTitle(latestDispatchTask.title, "派单任务")} 的 dispatch 回执推进到最终回复。`;
  }

  if (finalReplyFeed.length) {
    return "当前闭环已跑通，可以继续推进下一条 requirement。";
  }

  return "运行一轮自治推进，补齐派单、最小回执和最终回复。";
}

function buildCurrentOwner(
  requirements: AnyRecord[],
  messageMap: RequirementMessageMap,
  tasks: AnyRecord[],
  config: AnyRecord,
  resolveDisplay: DisplayResolver,
) {
  const activeRequirement = selectFreshestRequirement(
    requirements,
    messageMap,
    (item) => isActiveStatus(item.status) && !isDoneStatus(item.status),
  );
  if (activeRequirement) {
    return resolveDisplay(activeRequirement.to_agent, ownerFallback(activeRequirement));
  }

  const latestDispatchTask = selectLatestDispatchTask(tasks);
  if (latestDispatchTask?.latest_dispatch) {
    return resolveDisplay(
      latestDispatchTask.latest_dispatch.workstation_id ??
        latestDispatchTask.latest_dispatch.agent_id ??
        latestDispatchTask.latest_dispatch.workstation_name,
      "待分配",
    );
  }

  const firstSeat = asArray(config.codexSeats)[0] ?? null;
  return resolveDisplay(
    firstSeat?.source_workstation_id ??
      firstSeat?.agent_id ??
      firstSeat?.config_id ??
      firstSeat?.id ??
      firstSeat?.name,
    text(firstSeat?.name, "待分配"),
  );
}

function buildRelayFeed(relayTimeline: AnyRecord[], tasks: AnyRecord[], resolveDisplay: DisplayResolver): RelayFeedItem[] {
  const relayItems = relayTimeline
    .slice()
    .sort(
      (left, right) =>
        new Date(text(right.created_at ?? right.updated_at, "1970-01-01")).getTime() -
        new Date(text(left.created_at ?? left.updated_at, "1970-01-01")).getTime(),
    )
    .slice(0, 8)
    .map((item, index) => ({
      id: text(item.id, `relay-${index + 1}`),
      title: safeDisplayTitle(item.title ?? item.message_type, "线程回执"),
      body: shortText(item.body, "没有额外说明", 96),
      meta: `${actorLabel(item, resolveDisplay)} / ${formatStamp(item.created_at ?? item.updated_at)}`,
      at: new Date(text(item.created_at ?? item.updated_at, "1970-01-01")).getTime(),
    }));

  const dispatchItems = tasks
    .filter((task) => task?.latest_dispatch)
    .slice(0, 4)
    .map((task) => ({
      id: `dispatch-${text(task.id, "task")}`,
      title: `Task Dispatch / ${safeDisplayTitle(task.title, "未命名任务")}`,
      body: `${text(task.latest_dispatch.workstation_name ?? task.latest_dispatch.workstation_id, "未绑定工位")} / ${text(task.latest_dispatch.status, "dispatched")}`,
      meta: `${text(task.latest_dispatch.runner_id, "无 runner")} / ${formatStamp(task.latest_dispatch.updated_at ?? task.latest_dispatch.created_at)}`,
      at: new Date(text(task.latest_dispatch.updated_at ?? task.latest_dispatch.created_at, "1970-01-01")).getTime(),
    }));

  return [...relayItems, ...dispatchItems]
    .sort((left, right) => right.at - left.at)
    .slice(0, 10);
}

function bridgeStatusLabel(status: unknown) {
  const normalized = text(status, "").toLowerCase();
  if (["done", "completed", "resolved"].includes(normalized)) return "已收口";
  if (normalized === "seen") return "已查看";
  if (normalized === "accepted") return "已接单";
  if (["queued", "open", "waiting_response"].includes(normalized)) return "队列中";
  if (normalized === "routed") return "已路由";
  return "已桥接";
}

function isQueuedBridgeStatus(status: unknown) {
  return ["queued", "open", "waiting_response", "routed"].includes(text(status, "").toLowerCase());
}

function buildCodexInboxFeed(commands: AnyRecord[], resolveDisplay: DisplayResolver): CodexInboxFeedItem[] {
  return commands
    .map((item, index) => {
      const createdAt = new Date(text(item.createdAt ?? item.created_at, "1970-01-01")).getTime();
      const sourceStatus = text(item.sourceStatus ?? item.source_status ?? item.status, "queued").toLowerCase();
      const queuedAgeMinutes = isQueuedBridgeStatus(sourceStatus) ? queueAgeMinutes(createdAt) : null;
      const workstationId = text(item.workstationId ?? item.workstation_id, "");
      const workstationName = text(item.workstationName ?? item.workstation_name, workstationId || "Codex 线程");
      const providerLabel = text(item.provider ?? item.provider_label, "");
      const computerNodeLabel = text(item.computerNodeLabel ?? item.computer_node_label ?? item.computer_node, "");
      const skillLoadout = asArray(item.skillLoadout ?? item.skill_loadout).map((skill) => text(skill)).filter(Boolean);
      const repoSummary = text(item.repoSummary ?? item.repo_summary, "") || null;
      const referencePaths = asArray(item.referencePaths ?? item.reference_paths).map((value) => text(value)).filter(Boolean);
      const target = resolveDisplay(workstationId || workstationName, workstationName || "Codex 线程");
      const requirementId = text(item.sourceRequirementId ?? item.source_requirement_id, "");
      const bodyLines = text(item.body, "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
      const summaryLine = bodyLines[0] ?? "";
      const inlineBody = (isQuestionMarkHeavy(summaryLine) || /\?{4,}|�{2,}/.test(summaryLine))
        ? requirementId
          ? `Requirement ${requirementId.slice(0, 8)} 已派发，请在线程中查看详情。`
          : "平台已向该线程派发 requirement，请在 Codex 收件箱查看详情。"
        : summaryLine;
      const issuer = isQuestionMarkHeavy(item.issuer) ? "平台自治推进" : text(item.issuer, "平台自治推进");
      const metaParts = [
        issuer,
        formatStamp(item.createdAt ?? item.created_at),
        providerLabel ? `Provider ${providerLabel}` : "",
        computerNodeLabel ? `电脑 ${computerNodeLabel}` : "",
        requirementId ? `Requirement ${requirementId.slice(0, 8)}` : "",
      ].filter(Boolean);
      const rawTitle = text(item.title, "");
      const titleFallback = requirementId ? `Requirement ${requirementId.slice(0, 8)}` : "平台新指令";
      return {
        id: text(item.id ?? item.sourceMessageId, `codex-inbox-${index + 1}`),
        title: safeDisplayTitle(rawTitle, titleFallback),
        target,
        body: shortText(inlineBody, "没有额外说明", 120),
        meta: metaParts.join(" / "),
        statusLabel: bridgeStatusLabel(sourceStatus),
        sourceStatus,
        queueLabel: isQueuedBridgeStatus(sourceStatus) ? "平台队列中" : "平台已镜像",
        queueStartedAtLabel: isQueuedBridgeStatus(sourceStatus) ? formatStamp(item.createdAt ?? item.created_at) : null,
        queueAgeLabel: formatQueueAge(queuedAgeMinutes),
        queueStateLabel: queueStateLabel(queuedAgeMinutes),
        createdAt,
        requirementId: requirementId || null,
        workstationId: workstationId || null,
        workstationName: workstationName || null,
        providerLabel: providerLabel || null,
        computerNodeLabel: computerNodeLabel || null,
        skillLoadout,
        repoSummary,
        referenceSummary: referencePaths.length ? referencePaths.join(" / ") : null,
        isQueued: isQueuedBridgeStatus(sourceStatus),
      } satisfies CodexInboxFeedItem;
    })
    .filter((item): item is CodexInboxFeedItem => Boolean(item))
    .sort((left, right) => {
      if (right.createdAt !== left.createdAt) return right.createdAt - left.createdAt;
      const npc2Delta = Number(isNpc2InboxItem(right)) - Number(isNpc2InboxItem(left));
      if (npc2Delta !== 0) return npc2Delta;
      return left.title.localeCompare(right.title, "zh-CN");
    });
}

function exchangeDispatchRouteKeys(item: {
  target?: string | null;
  workstationId?: string | null;
  workstationName?: string | null;
}) {
  return uniqueStrings([item.workstationId, item.workstationName, item.target]).map((value) => value.toLowerCase());
}

function proofKeyForRequirement(requirementId: string, workstationId: string, title: string) {
  if (requirementId) return `requirement:${requirementId}`;
  return `command:${workstationId || "unknown-thread"}:${title || "untitled"}`;
}

function proofStageSummary(item: CooperationProofItem) {
  if (item.hasFinalReply) return "已收到最终回复";
  if (item.hasProgressSignal) return "线程已给出过程信号";
  if (item.protectedDataHidden) {
    return item.hasVisibleDispatch ? "派单可见，但受保护进度未授权" : "目标已锁定，但受保护进度未授权";
  }
  if (item.hasVisibleDispatch) return "平台派单已可见";
  if (item.hasRouteLock) return "目标线程已锁定";
  return "等待平台派单";
}

function proofEvidenceLabel(inbox: CodexInboxFeedItem | null, dispatchMessage: AnyRecord | null, hasRouteLock: boolean) {
  if (inbox && dispatchMessage) return "证据 桥接+平台";
  if (inbox) return "证据 本地桥接";
  if (dispatchMessage) return "证据 平台回流";
  if (hasRouteLock) return "证据 目标锁定";
  return "证据 待出现";
}

function buildWorkstationContextMap(config: AnyRecord) {
  const contextMap = new Map<string, AnyRecord>();

  function remember(candidate: unknown, value: AnyRecord) {
    const key = text(candidate, "");
    if (!key) return;
    contextMap.set(key, value);
    contextMap.set(key.toLowerCase(), value);
  }

  const workstations = [
    ...asArray(config.workstations),
    ...asArray(config.sourceThreads),
    ...asArray(config.codexSeats),
  ];

  workstations.forEach((item) => {
    remember(item.id, item);
    remember(item.workstation_id, item);
    remember(item.config_id, item);
    remember(item.row_id, item);
    remember(item.source_workstation_id, item);
  });

  return contextMap;
}

function buildCooperationProofFeed(
  requirements: AnyRecord[],
  messageMap: RequirementMessageMap,
  codexInboxFeed: CodexInboxFeedItem[],
  resolveDisplay: DisplayResolver,
  config: AnyRecord,
  hasProtectedDataGap: boolean,
): CooperationProofItem[] {
  const buckets = new Map<string, { requirement: AnyRecord | null; inboxItems: CodexInboxFeedItem[] }>();
  const workstationContextMap = buildWorkstationContextMap(config);

  function ensureBucket(key: string) {
    const existing = buckets.get(key);
    if (existing) return existing;
    const created = { requirement: null as AnyRecord | null, inboxItems: [] as CodexInboxFeedItem[] };
    buckets.set(key, created);
    return created;
  }

  requirements.forEach((requirement, index) => {
    const requirementId = text(requirement.id ?? requirement.requirement_id, "");
    const targetId = text(requirement.to_agent, "");
    const title = requirementDisplayTitle(requirement, resolveDisplay) || `未命名需求 ${index + 1}`;
    if (!Boolean(requirement.is_codex_session_target) && !isCodexSessionId(targetId)) return;
    ensureBucket(proofKeyForRequirement(requirementId, targetId, title)).requirement = requirement;
  });

  codexInboxFeed.forEach((item) => {
    ensureBucket(proofKeyForRequirement(item.requirementId ?? "", item.workstationId ?? "", item.title)).inboxItems.push(item);
  });

  return Array.from(buckets.entries())
    .map(([key, bucket]) => {
      const requirement = bucket.requirement;
      const inbox = bucket.inboxItems.slice().sort((left, right) => right.createdAt - left.createdAt)[0] ?? null;
      const requirementId = text(requirement?.id ?? requirement?.requirement_id ?? inbox?.requirementId, "");
      const messages = requirementId
        ? [...(messageMap.get(requirementId) ?? [])].sort((left, right) => latestMessageAt(right) - latestMessageAt(left))
        : [];
      const dispatchMessage =
        messages.find(
          (item) =>
            Boolean(item.is_dispatch_signal) ||
            text(item.proof_stage, "").toLowerCase() === "dispatch" ||
            text(item.message_type, "").toLowerCase() === "requirement_dispatch",
        ) ?? null;
      const progressMessage =
        messages.find((item) => text(item.proof_stage, "").toLowerCase() === "progress") ?? null;
      const finalMessage =
        messages.find(
          (item) =>
            Boolean(item.is_final_reply) ||
            text(item.proof_stage, "").toLowerCase() === "final_reply" ||
            isFinalReplyMessage(item),
        ) ?? null;
      const targetId = text(requirement?.to_agent ?? inbox?.workstationId ?? inbox?.workstationName, "");
      const targetFallback = text(inbox?.workstationName ?? requirement?.to_agent, "Codex 线程");
      const target = resolveDisplay(targetId || targetFallback, targetFallback || "Codex 线程");
      const workstationContext =
        workstationContextMap.get(targetId) ??
        workstationContextMap.get(targetId.toLowerCase()) ??
        null;
      const routeKeys = uniqueStrings([
        targetId,
        targetFallback,
        inbox?.workstationId,
        inbox?.workstationName,
        requirement?.to_agent,
        workstationContext?.id,
        workstationContext?.workstation_id,
        workstationContext?.source_workstation_id,
        workstationContext?.metadata?.source_workstation_id,
      ]).map((value) => value.toLowerCase());
      const workstationContextSkills = asArray(workstationContext?.skill_loadout ?? workstationContext?.skillLoadout)
        .map((skill) => text(skill))
        .filter(Boolean);
      const workstationHasContext = Boolean(
        text(
          workstationContext?.ai_provider ??
            workstationContext?.aiProvider ??
            workstationContext?.metadata?.ai_provider ??
            workstationContext?.metadata?.provider,
          "",
        ) ||
          text(
            workstationContext?.computer_node ??
              workstationContext?.computerNode ??
              workstationContext?.metadata?.computer_node ??
              workstationContext?.metadata?.computerNode,
            "",
          ) ||
          workstationContextSkills.length,
      );
      const inboxHasContext = Boolean(inbox?.providerLabel || inbox?.computerNodeLabel || inbox?.skillLoadout?.length);
      const providerLabel =
        inbox?.providerLabel ??
        (text(
          workstationContext?.ai_provider ??
            workstationContext?.aiProvider ??
            workstationContext?.metadata?.ai_provider ??
            workstationContext?.metadata?.provider,
          "",
        ) || null);
      const computerNodeLabel =
        inbox?.computerNodeLabel ??
        (text(
          workstationContext?.computer_node ??
            workstationContext?.computerNode ??
            workstationContext?.metadata?.computer_node ??
            workstationContext?.metadata?.computerNode,
          "",
        ) || null);
      const skillLoadout = (inbox?.skillLoadout?.length ? inbox.skillLoadout : workstationContextSkills)
        .map((skill) => text(skill))
        .filter(Boolean);
      const usedConfigFallback = Boolean(
        workstationHasContext &&
          ((!inbox?.providerLabel && providerLabel) ||
            (!inbox?.computerNodeLabel && computerNodeLabel) ||
            (!(inbox?.skillLoadout?.length) && skillLoadout.length)),
      );
      const contextLabel = usedConfigFallback ? (inboxHasContext ? "上下文补全" : "配置回填") : inboxHasContext ? "桥接上下文" : null;
      const latestAt = Math.max(
        requirement ? requirementActivityAt(requirement, messageMap) : 0,
        latestMessageAt(dispatchMessage),
        latestMessageAt(progressMessage),
        latestMessageAt(finalMessage),
        inbox?.createdAt ?? 0,
      );
      const hasRouteLock = Boolean(requirement);
      const hasVisibleDispatch = Boolean(inbox || dispatchMessage);
      const hasDispatchProof = Boolean(inbox || dispatchMessage || requirement);
      const hasProgressSignal = Boolean(progressMessage);
      const hasFinalReply = Boolean(finalMessage);
      const protectedDataHidden = hasProtectedDataGap && (hasVisibleDispatch || hasRouteLock) && !hasProgressSignal && !hasFinalReply;
      const evidenceLabel = proofEvidenceLabel(inbox, dispatchMessage, hasRouteLock);
      const displayTitle =
        requirementDisplayTitle(requirement, resolveDisplay) ||
        safeDisplayTitle(inbox?.title, "平台派往 Codex 的指令");

      return {
        id: key,
        title: displayTitle,
        target,
        routeKeys,
        body: finalMessage
          ? shortText(finalMessage.body, "最终回复已写回平台。", 108)
          : progressMessage
            ? shortText(progressMessage.body, `${actorLabel(progressMessage, resolveDisplay)} 已给出过程信号。`, 108)
            : protectedDataHidden && hasVisibleDispatch
              ? "已看到平台派单，但当前登录态未授权读取过程信号和最终回复。"
            : protectedDataHidden
              ? `${displayTitle} 已锁定真实线程 ${target}，但当前登录态未授权读取后续过程信号。`
            : inbox
              ? shortText(inbox.body, "平台已把这条 requirement 发到真实 Codex 线程。", 108)
              : dispatchMessage
                ? shortText(dispatchMessage.body, "平台派单消息已写入协作流。", 108)
              : `${displayTitle} 已指向真实线程 ${target}。`,
        meta: [
          target ? `目标 ${target}` : "",
          requirementId ? `Requirement ${requirementId.slice(0, 8)}` : "",
          evidenceLabel,
          contextLabel ? `上下文 ${contextLabel}` : "",
          protectedDataHidden ? "受保护数据未授权" : "",
          formatEpoch(latestAt),
        ]
          .filter(Boolean)
          .join(" / "),
        requirementId,
        dispatchLabel: inbox ? "平台派单已桥接" : dispatchMessage ? "派单消息已写入" : "目标线程已锁定",
        progressLabel: progressMessage
          ? `${actorLabel(progressMessage, resolveDisplay)} 已回`
          : hasFinalReply
            ? "已直接收口"
            : protectedDataHidden
              ? "过程信号未授权"
            : hasVisibleDispatch
              ? "等待最小回执"
              : hasRouteLock
                ? "等待派单可见"
              : "尚未开始",
        finalLabel: hasFinalReply
          ? "最终回复已回"
          : isDoneStatus(requirement?.status)
            ? "需求已结束"
            : protectedDataHidden
              ? "最终回复未授权"
            : hasVisibleDispatch
              ? "最终回复待回"
              : hasRouteLock
                ? "等待派单可见"
              : "尚未开始",
        evidenceLabel,
        contextLabel,
        providerLabel,
        computerNodeLabel,
        skillLoadout,
        repoSummary: inbox?.repoSummary ?? null,
        referenceSummary: inbox?.referenceSummary ?? null,
        protectedDataHidden,
        latestAt,
        hasRouteLock,
        hasVisibleDispatch,
        hasDispatchProof,
        hasProgressSignal,
        hasFinalReply,
        usedConfigFallback,
      } satisfies CooperationProofItem;
    })
    .sort((left, right) => {
      const npc2Delta = Number(text(right.target, "").includes("NPC2")) - Number(text(left.target, "").includes("NPC2"));
      if (npc2Delta !== 0) return npc2Delta;
      return right.latestAt - left.latestAt;
    })
    .slice(0, 4);
}

function buildCooperationProofSummary(
  proofFeed: CooperationProofItem[],
  hasProtectedDataGap: boolean,
): CooperationProofSummary {
  const featured = proofFeed[0] ?? null;
  if (!featured) {
    return {
      foldSummary: "协作证明面：暂无真线程闭环",
      title: "还没有真线程协作证明",
      body: hasProtectedDataGap
        ? "当前登录态拿不到全部受保护协作数据，本地 Codex inbox 里也还没出现新的项目派单。"
        : "平台下一次把 requirement 发到真实 Codex 线程后，这里会按派单、过程信号和最终回复三段收口显示。",
      meta: "保持农场底座和三主卡不变，这里只放折叠后的闭环证据。",
    };
  }

  const movedCount = proofFeed.filter((item) => item.hasProgressSignal || item.hasFinalReply).length;
  const finalizedCount = proofFeed.filter((item) => item.hasFinalReply).length;
  const dispatchedCount = proofFeed.filter((item) => item.hasVisibleDispatch).length;
  const routeLockedCount = proofFeed.filter((item) => item.hasRouteLock && !item.hasVisibleDispatch).length;
  const protectedCount = proofFeed.filter((item) => item.protectedDataHidden).length;
  const configFallbackCount = proofFeed.filter((item) => item.usedConfigFallback).length;
  const featuredRequirementLabel = shortRequirementLabel(featured.requirementId);

  return {
    foldSummary: `协作证明面：${featured.target || "Codex 线程"}${featuredRequirementLabel ? ` · ${featuredRequirementLabel}` : ""} ${proofStageSummary(featured)} · ${formatEpoch(featured.latestAt)}`,
    title: featuredRequirementLabel
      ? `${featured.target || "Codex 线程"} 的 ${featuredRequirementLabel} 闭环证据可见`
      : `${featured.target || "Codex 线程"} 的闭环证据可见`,
    body: hasProtectedDataGap
      ? featured.hasVisibleDispatch
        ? `当前登录态拿不到全部受保护协作数据，但本地 Codex inbox 仍能证明平台已经把工作发往 ${featured.target || "Codex 线程"}。`
        : `当前登录态拿不到全部受保护协作数据，目前至少能确认 requirement 已锁定到 ${featured.target || "Codex 线程"}，但派单过程还没有完全露出。`
      : featured.hasVisibleDispatch
        ? `${featured.title} 现在能在一个折叠区里看到派单、过程信号和最终回复的进度，不需要把首屏变成日志墙。`
        : `${featured.title} 目前先证明 requirement 已锁定到真实线程 ${featured.target || "Codex 线程"}，后续派单和线程回执会继续在这里累积。`,
    meta: `${proofFeed.length} 条真线程链路 / 派单可见 ${dispatchedCount} 条 / 仅锁定目标 ${routeLockedCount} 条 / 已动 ${movedCount} 条 / 已收口 ${finalizedCount} 条${protectedCount ? ` / 未授权 ${protectedCount} 条` : ""}${configFallbackCount ? ` / 配置回填 ${configFallbackCount} 条` : ""}`,
  };
}

function seatNeedsHumanReview(seat: MapSeatPayload) {
  return ["等待人工审批", "人工审核中", "审批阻塞", "需要人工确认"].includes(seat.reviewState);
}

function taskNeedsHumanReview(task: AnyRecord) {
  const status = text(task.status, "").toLowerCase();
  if (["waiting_approval", "reviewing", "blocked_by_review", "pending_human_review"].includes(status)) return true;
  return Boolean(task.requires_human_approval ?? task.requiresHumanApproval);
}

function collaborationMessageNeedsHumanReview(message: AnyRecord) {
  const type = text(message.message_type, "").toLowerCase();
  const status = text(message.status, "").toLowerCase();
  if (type === "human_review_request") {
    return ["pending_human_review", "pending", "open"].includes(status);
  }
  return status === "pending_human_review";
}

function seatIsAutonomous(seat: MapSeatPayload) {
  return seat.automationEnabled && seat.approvalState === "自动推进" && !seatNeedsHumanReview(seat);
}

function seatScreenshotState(seat: MapSeatPayload, hasProtectedDataGap: boolean) {
  if (hasProtectedDataGap) return "截图待恢复协作数据";
  if (seatNeedsHumanReview(seat)) return "截图含人审状态";
  if (seat.staleAfterAck) return "截图可证明停在最小回执";
  if (seat.finalReply) return "截图可证明已收口";
  if (seat.minimalAck) return "截图可证明自主推进";
  if (seat.currentRequirement) return "截图可证明已接单";
  return "截图等待新派单";
}

function seatAutonomyChip(seat: MapSeatPayload) {
  if (!seat.automationEnabled) return "单次执行";
  if (seat.staleAfterAck) return "最小回执后停滞";
  if (seat.progressWarningLabel) return seat.progressWarningLabel;
  if (seat.autonomyDecision.includes("重新登录")) return "待恢复协作数据";
  if (seat.autonomyDecision.includes("暂停自动推进")) return "暂停自动推进";
  if (seat.autonomyDecision.includes("等待人工审核")) return "等待人审结论";
  if (seat.autonomyDecision.includes("本轮已收口")) return "本轮已收口";
  if (seat.autonomyDecision.includes("已给最小回执")) return "自动推进中";
  if (seat.autonomyDecision.includes("已接单")) return "等待最小回执";
  if (seat.autonomyDecision.includes("当前空闲")) return "当前空闲";
  return seat.approvalState;
}

function seatBridgeIssueLabel(seat: MapSeatPayload) {
  if (!seat.sourceThreadId) return "待绑定线程";
  if (!seat.automationEnabled) return "自动化已关闭";
  if (!seat.supportsLocalAutonomyBridge) {
    if (seat.providerId === "claude") {
      if (seat.autonomyBridgeLabel.includes("Claude auto-wake blocked")) return "Claude 自启受限";
      if (seat.autonomyBridgeLabel.includes("missing Claude registration")) return "缺 Claude 登记";
      if (seat.autonomyBridgeLabel.includes("missing Claude session")) return "缺 Claude 会话";
      if (seat.autonomyBridgeLabel.includes("Claude session stale")) return "Claude 会话过旧";
      if (seat.autonomyBridgeLabel.includes("Claude session idle")) return "Claude 会话空闲";
    }
    return null;
  }
  if (!seat.consumerScriptExists) return "缺 consumer";
  if (seat.heartbeatMissing || !seat.heartbeatAutomationId) return "缺 heartbeat";
  if (seat.heartbeatStatus && seat.heartbeatStatus !== "ACTIVE") return `心跳 ${seat.heartbeatStatus}`;
  const needsFreshConsumerState = Boolean(seat.currentRequirement || (seat.minimalAck && !seat.finalReply) || seat.staleAfterAck);
  if (!seat.consumerStateExists) return needsFreshConsumerState ? "等待首次回写" : null;
  if (seat.consumerStateStale) return needsFreshConsumerState ? "本地状态未更新" : null;
  return null;
}

function prioritizedStalledSeats(seats: MapSeatPayload[]) {
  return seats
    .filter((seat) => seat.staleAfterAck)
    .slice()
    .sort((left, right) => {
      const bridgeDelta = seatBridgePriorityScore(right) - seatBridgePriorityScore(left);
      if (bridgeDelta !== 0) return bridgeDelta;
      const staleDelta = (right.staleAfterAckMinutes ?? 0) - (left.staleAfterAckMinutes ?? 0);
      if (staleDelta !== 0) return staleDelta;
      return seatSignalAt(right) - seatSignalAt(left);
    });
}

function stalledSeatLabel(seat: MapSeatPayload) {
  return `${seat.name} ${seatBridgeIssueLabel(seat) || "停在最小回执"}`;
}

function buildStalledSeatSummary(seats: MapSeatPayload[], limit = 2) {
  const stalledSeats = prioritizedStalledSeats(seats);
  if (!stalledSeats.length) return null;
  const visible = stalledSeats.slice(0, limit).map((seat) => stalledSeatLabel(seat));
  const suffix = stalledSeats.length > limit ? ` 等 ${stalledSeats.length} 席` : "";
  return {
    count: stalledSeats.length,
    topSeat: stalledSeats[0] ?? null,
    shortLabel: `${visible.join(" / ")}${suffix}`,
    detail: stalledSeats
      .slice(0, limit)
      .map((seat) => {
        const issue = seatBridgeIssueLabel(seat) || "停在最小回执";
        return `${seat.name} ${issue}${seat.staleAfterAckMinutes !== null ? `（已停滞 ${formatQueueAge(seat.staleAfterAckMinutes) || `${seat.staleAfterAckMinutes} 分钟`}）` : ""}`;
      })
      .join("；"),
  };
}

function stalledSeatRecoveryHint(seat: MapSeatPayload) {
  const seatName = seat.name || "当前 NPC";
  const issue = seatBridgeIssueLabel(seat);
  if (issue === "自动化已关闭") {
    return `${seatName} 当前是单次执行模式。只会在你发新指令时跑这一轮，不会持续自动消耗 token。`;
  }
  if (issue === "缺 heartbeat") {
    return `先给 ${seatName} 补 heartbeat 或重新校准自治桥，再让线程继续吃单。`;
  }
  if (issue?.startsWith("心跳 ")) {
    return `先把 ${seatName} 的 heartbeat 恢复为 ACTIVE，再观察这条 requirement 能否继续推进。`;
  }
  if (issue === "缺 consumer") {
    return `先给 ${seatName} 补 consumer wrapper，再恢复自治桥。`;
  }
  if (issue === "等待首次回写") {
    return `先让 ${seatName} 跑一轮本地 consumer，确认首次最小回执能写回平台。`;
  }
  if (issue === "本地状态未更新") {
    return `先唤醒 ${seatName} 所在线程或重跑本地 consumer，让本地 state 追上平台派单。`;
  }
  if (issue === "缺 Claude 登记") {
    return `先把 ${seatName} 当前绑定的 Claude 会话登记到平台 seat registry，再继续派单。`;
  }
  if (issue === "缺 Claude 会话") {
    return `先确认 ${seatName} 绑定的 Claude 会话还存在，再决定重绑线程还是重新开 Claude 窗口。`;
  }
  if (issue === "Claude 自启受限") {
    return `平台已经登记 ${seatName} 的 Claude 会话，但当前环境阻止自动唤醒。先在本机手动打开或唤醒 Claude，再回来重新检测。`;
  }
  if (issue === "Claude 会话过旧" || issue === "Claude 会话空闲") {
    return `先唤醒 ${seatName} 当前的 Claude 会话或重新登记最新会话，再继续推进这条 requirement。`;
  }
  return `先重新派单、补最小回执检查，必要时再转人工接手 ${seatName} 当前 requirement。`;
}

function seatNextStepHint(seat: MapSeatPayload | null | undefined) {
  if (!seat) return null;
  if (seatBridgeIssueLabel(seat) || seat.staleAfterAck) {
    return stalledSeatRecoveryHint(seat);
  }
  if (seat.progressWarningLabel === "最小回执偏晚" && seat.minimalAck && !seat.finalReply) {
    return `继续盯住 ${seat.name || "当前 NPC"} 当前 requirement 的结果收口。线程已经恢复推进，但这条最小回执偏晚，暂时不该误判成彻底卡死。`;
  }
  if (seat.progressWarningLabel === "进度信号待归一" && seat.minimalAck && !seat.finalReply) {
    return `继续盯住 ${seat.name || "当前 NPC"} 当前 requirement 的结果收口，同时把 live API 的旧进度信号归一回真正的 progress_ack。`;
  }
  if (seat.provisioningState !== "ready" && seat.provisioningNeeds.length) {
    return `先把 ${seat.name || "当前 NPC"} 的开箱缺口补齐：${seat.provisioningNeeds.join(" / ")}。`;
  }
  if (seat.finalReply) {
    return `${seat.name || "当前 NPC"} 这轮已经有最终回复，可以继续接下一条 requirement。`;
  }
  return null;
}

function seatBridgeChip(seat: MapSeatPayload) {
  if (!seat.sourceThreadId) return "待绑定线程";
  const issue = seatBridgeIssueLabel(seat);
  if (!seat.automationEnabled) return issue ?? "单次执行";
  if (!seat.supportsLocalAutonomyBridge) return issue ?? seat.autonomyBridgeLabel ?? `${seat.providerLabel} 已绑定`;
  return issue ?? "自治桥健康";
}

function claudeSeatActionLabel(seat: MapSeatPayload) {
  const issue = seatBridgeIssueLabel(seat);
  if (
    issue === "Claude 自启受限" ||
    seat.provisioningNeeds.includes("手动唤醒 Claude 会话") ||
    seat.provisioningNeeds.includes("手动刷新 Claude 会话")
  ) {
    return "重新检测 Claude 接入";
  }
  if (issue === "Claude 会话空闲" || seat.provisioningNeeds.includes("唤醒 Claude 会话")) {
    return "唤醒 Claude 会话";
  }
  if (issue === "Claude 会话过旧" || seat.provisioningNeeds.includes("刷新 Claude 会话")) {
    return "刷新 Claude 会话";
  }
  if (issue === "缺 Claude 登记" || seat.provisioningNeeds.includes("登记 Claude 会话")) {
    return "登记 Claude 会话";
  }
  if (issue === "缺 Claude 会话" || seat.provisioningNeeds.includes("打开 Claude 会话")) {
    return "打开 Claude 会话";
  }
  return seat.autonomyReady ? "重新登记 Claude 会话" : "接通 Claude 会话";
}

function seatAcceptanceBody(seat: MapSeatPayload, hasProtectedDataGap: boolean) {
  if (hasProtectedDataGap) {
    return `${seat.name} 的 requirement、回执和最终回复当前未授权，先恢复协作数据再做截图验收。`;
  }
  if (seat.staleAfterAck) {
    const bridgeIssue = seatBridgeIssueLabel(seat);
    return `${seat.name} 已给最小回执，但后续 ${formatQueueAge(seat.staleAfterAckMinutes) || "一段时间"} 没再收口${bridgeIssue ? `，当前根因更像 ${bridgeIssue}` : ""}，更适合重新派单或人工接手。`;
  }
  if (seat.finalReply) return seat.finalReply;
  if (seat.minimalAck) return seat.minimalAck;
  if (seat.currentRequirement) return `${seat.currentRequirement} / ${text(seat.currentRequirementStatus, "waiting_response")}`;
  return seat.description || "当前空闲，可接受新的平台 requirement。";
}

function buildSeatNextStepDecision(
  seats: MapSeatPayload[],
  hasProtectedDataGap: boolean,
  codexInboxFeed: CodexInboxFeedItem[],
) {
  if (hasProtectedDataGap) {
    return {
      label: "待恢复协作数据",
      detail: "重新登录后再判断是否继续自动推进，还是转入人工审核。",
    };
  }

  const reviewSeat = seats.find((seat) => seatNeedsHumanReview(seat)) ?? null;
  if (reviewSeat) {
    return {
      label: "等待人工审核",
      detail: `${reviewSeat.name} 当前处于 ${reviewSeat.reviewState}，下一步应等待人工结论而不是继续自动推进。`,
    };
  }

  const stalledSeat = seats.find((seat) => seat.staleAfterAck) ?? null;
  if (stalledSeat) {
    const bridgeIssue = seatBridgeIssueLabel(stalledSeat);
    return {
      label: "处理停滞席位",
      detail: `${stalledSeat.name} 已停在最小回执后 ${formatQueueAge(stalledSeat.staleAfterAckMinutes) || "一段时间"}${bridgeIssue ? `，当前更像 ${bridgeIssue}` : ""}，下一步更适合重新派单、补心跳检查或转人工接手。`,
    };
  }

  const autonomousSeat = seats.find((seat) => Boolean(seat.minimalAck) && !seat.finalReply) ?? null;
  if (autonomousSeat) {
    return {
      label: "可自动推进",
      detail: `${autonomousSeat.name} 已给出最小回执${autonomousSeat.progressWarningLabel ? `（${autonomousSeat.progressWarningLabel}）` : ""}，下一步可以继续自动推进直到最终回复。`,
    };
  }

  const activeSeat = seats.find((seat) => Boolean(seat.currentRequirement)) ?? null;
  if (activeSeat) {
    return {
      label: "等待最小回执",
      detail: `${activeSeat.name} 已接单，下一步先等线程回最小回执。`,
    };
  }

  const finalizedSeat = seats.find((seat) => Boolean(seat.finalReply)) ?? null;
  if (finalizedSeat) {
    return {
      label: "等待新派单",
      detail: `${finalizedSeat.name} 的上一轮已经收口，当前更适合等待新的平台派单。`,
    };
  }

  const queuedCommand = pickFeaturedQueuedInboxItem(codexInboxFeed);
  if (queuedCommand) {
    const requirementLabel = queuedCommand.requirementId
      ? `Requirement ${queuedCommand.requirementId.slice(0, 8)}`
      : "一条平台派单";
    return {
      label: "等待桥接回写",
      detail: `${queuedCommand.target || "当前线程"} 的 ${requirementLabel} 仍在平台队列中${queuedCommand.queueStartedAtLabel ? `（排队起点 ${queuedCommand.queueStartedAtLabel}）` : ""}${queuedCommand.queueAgeLabel ? `，已等待 ${queuedCommand.queueAgeLabel}` : ""}${queuedCommand.queueStateLabel ? `，当前判断为 ${queuedCommand.queueStateLabel}` : ""}，下一步更适合等待线程最小回执或宿主桥接镜像回写。`,
    };
  }

  return {
    label: "等待新派单",
    detail: "当前没有新的 NPC2 派单信号，下一步应等待平台把新 requirement 发到真实线程。",
  };
}

function buildSeatAcceptanceSummary(
  seats: MapSeatPayload[],
  hasProtectedDataGap: boolean,
  codexInboxFeed: CodexInboxFeedItem[],
): SeatAcceptanceSummary {
  const activeSeats = seats.filter((seat) => seat.status === "active").length;
  const autonomousSeats = seats.filter((seat) => seatIsAutonomous(seat)).length;
  const reviewSeats = seats.filter((seat) => seatNeedsHumanReview(seat)).length;
  const stalledSeats = seats.filter((seat) => seat.staleAfterAck).length;
  const ackSeats = seats.filter((seat) => Boolean(seat.minimalAck)).length;
  const finalizedSeats = seats.filter((seat) => Boolean(seat.finalReply)).length;
  const screenshotReadySeats = seats.filter(
    (seat) => seatNeedsHumanReview(seat) || Boolean(seat.currentRequirement || seat.minimalAck || seat.finalReply),
  ).length;
  const queuedBridgeCount = codexInboxFeed.filter((item) => item.isQueued).length;
  const featuredQueuedBridge = pickFeaturedQueuedInboxItem(codexInboxFeed);
  const oldestQueuedBridge =
    codexInboxFeed
      .filter((item) => item.isQueued)
      .slice()
      .sort((left, right) => left.createdAt - right.createdAt)[0] ?? null;
  const latestSignalAt = seats.reduce((latest, seat) => {
    const current = new Date(text(seat.lastSignalAt, "1970-01-01")).getTime();
    return current > latest ? current : latest;
  }, 0);
  const nextStep = buildSeatNextStepDecision(seats, hasProtectedDataGap, codexInboxFeed);

  if (!seats.length) {
    return {
      foldSummary: "截图验收链：还没有 NPC 席位",
      title: "还没有可验收的席位链路",
      body: "先绑定真实 NPC 席位和来源线程，截图验收链才会开始证明谁在自主推进、谁在等待人工审核。",
      meta: "继续保持农场底座和三主卡可见，这里只收口席位级状态。",
      nextStepLabel: "等待建席位",
      nextStepDetail: "先创建或绑定 NPC 席位，再继续做截图验收和推进判断。",
    };
  }

  return {
    foldSummary: `截图验收链：下一步 ${nextStep.label} / 自主推进 ${autonomousSeats} 席 / 停滞 ${stalledSeats} 席 / 等待人审 ${reviewSeats} 席${queuedBridgeCount ? ` / 桥接排队 ${queuedBridgeCount} 条` : ""}${featuredQueuedBridge ? ` / 当前聚焦 ${featuredQueuedBridge.target || "当前线程"}${shortRequirementLabel(featuredQueuedBridge.requirementId) ? ` · ${shortRequirementLabel(featuredQueuedBridge.requirementId)}` : ""}` : ""}${latestSignalAt ? ` / 最新 ${formatEpoch(latestSignalAt)}` : ""}`,
    title: "农场席位状态可直接截图验收",
    body: hasProtectedDataGap
      ? "当前登录态未授权读取完整协作数据，但席位级链路仍能说明哪些线程拓扑已就位，恢复登录后即可继续验证自主推进和人审状态。"
      : reviewSeats
        ? "截图时不用展开日志墙，只要保留农场底座、三主卡和这个折叠区，就能证明哪些席位还在自动推进、哪些已经停在人审。"
        : queuedBridgeCount
          ? `当前席位链路可以直接在截图里证明谁已接单、谁给过最小回执、谁已经收口；同时还能看到仍有 ${queuedBridgeCount} 条桥接派单在等线程最小回执或宿主镜像回写${featuredQueuedBridge ? `，当前聚焦 ${featuredQueuedBridge.target || "当前线程"}${shortRequirementLabel(featuredQueuedBridge.requirementId) ? ` 的 ${shortRequirementLabel(featuredQueuedBridge.requirementId)}` : ""}` : ""}，不需要把整页变成过程日志。`
          : "当前席位链路可以直接在截图里证明谁已接单、谁给过最小回执、谁已经收口，不需要把整页变成过程日志。",
    meta: `${seats.length} 个 NPC 席位 / 活跃 ${activeSeats} 席 / 最小回执 ${ackSeats} 席 / 停滞 ${stalledSeats} 席 / 已收口 ${finalizedSeats} 席 / 可截图验收 ${screenshotReadySeats} 席${queuedBridgeCount ? ` / 桥接排队 ${queuedBridgeCount} 条` : ""}${featuredQueuedBridge ? ` / 当前聚焦 ${featuredQueuedBridge.target || "当前线程"}${shortRequirementLabel(featuredQueuedBridge.requirementId) ? ` · ${shortRequirementLabel(featuredQueuedBridge.requirementId)}` : ""}` : ""}${oldestQueuedBridge?.queueAgeLabel ? ` / 最久等待 ${oldestQueuedBridge.queueAgeLabel}` : ""}${oldestQueuedBridge?.queueStateLabel ? ` / 队列判断 ${oldestQueuedBridge.queueStateLabel}` : ""}`,
    nextStepLabel: nextStep.label,
    nextStepDetail: nextStep.detail,
  };
}

function buildProcessVisibility(
  relayFeed: RelayFeedItem[],
  finalReplyFeed: FeedItem[],
  maintenanceBoard: Array<{ status: string }>,
  activeSourceThreadCount: number,
  currentOwner: string,
  codexInboxFeed: CodexInboxFeedItem[],
  seats: MapSeatPayload[],
) {
  const activeMaintenanceCount = maintenanceBoard.filter((item) => isActiveStatus(item.status)).length;
  const ownerLabel = currentOwner || "待分配";
  const stalledSeatSummary = buildStalledSeatSummary(seats);
  if (stalledSeatSummary?.topSeat) {
    const recoveryHint = stalledSeatRecoveryHint(stalledSeatSummary.topSeat);
    return {
      foldSummary: `协作脉搏：${stalledSeatSummary.shortLabel}`,
      title: "当前有席位停在最小回执",
      body: `${stalledSeatSummary.detail}。${recoveryHint} 现在更适合先处理这些真实阻塞，再继续给别的线程加新 requirement。`,
      meta: `当前负责人 ${ownerLabel} / 活跃线程 ${activeSourceThreadCount} 条 / 停滞 ${stalledSeatSummary.count} 席 / 维护链 ${activeMaintenanceCount} 条`,
    };
  }
  const latestCommand = codexInboxFeed[0] ?? null;
  const featuredCommand = pickFeaturedInboxItem(codexInboxFeed);
  if (latestCommand) {
    const queuedCount = codexInboxFeed.filter((item) => item.isQueued).length;
    const oldestQueuedCommand =
      codexInboxFeed
        .filter((item) => item.isQueued)
        .slice()
        .sort((left, right) => left.createdAt - right.createdAt)[0] ?? null;
    const featuredQueuedCommand = pickFeaturedQueuedInboxItem(codexInboxFeed);
    const featuredFocusLabel = featuredQueuedCommand
      ? `${featuredQueuedCommand.target || "当前线程"}${shortRequirementLabel(featuredQueuedCommand.requirementId) ? ` · ${shortRequirementLabel(featuredQueuedCommand.requirementId)}` : ""}`
      : featuredCommand
        ? `${featuredCommand.target || "当前线程"}${shortRequirementLabel(featuredCommand.requirementId) ? ` · ${shortRequirementLabel(featuredCommand.requirementId)}` : ""}`
        : "";
    const uniqueTargets = Array.from(new Set(codexInboxFeed.map((item) => item.target))).filter(Boolean);
    const targetSummary =
      uniqueTargets.length > 1
        ? `${uniqueTargets.slice(0, 2).join("、")} 等 ${uniqueTargets.length} 条线程`
        : uniqueTargets[0] ?? "其他 Codex 线程";
    return {
      foldSummary: `协作脉搏：平台队列 ${queuedCount} 条 / 已桥接 ${codexInboxFeed.length} 条${featuredFocusLabel ? ` / 当前聚焦 ${featuredFocusLabel}` : ""} · 最新 ${formatEpoch(latestCommand.createdAt)}`,
      title: queuedCount ? "平台已有排队中的 Codex 工作" : "平台正在给其他 Codex 线程派单",
      body: queuedCount
        ? `最近 bridged 指令已发给 ${targetSummary}${featuredQueuedCommand && featuredQueuedCommand !== latestCommand ? `，当前截图聚焦 ${featuredQueuedCommand.target || "当前线程"}${shortRequirementLabel(featuredQueuedCommand.requirementId) ? ` 的 ${shortRequirementLabel(featuredQueuedCommand.requirementId)}` : ""}` : ""}${oldestQueuedCommand?.queueAgeLabel ? `，其中最久一条已等待 ${oldestQueuedCommand.queueAgeLabel}` : ""}${oldestQueuedCommand?.queueStateLabel ? `，当前判断为 ${oldestQueuedCommand.queueStateLabel}` : ""}，当前更该等线程最小回执或宿主桥接回写，而不是继续把首屏堆成日志墙。`
        : `最近指令已发给 ${targetSummary}${featuredCommand && featuredCommand !== latestCommand ? `，当前截图聚焦 ${featuredCommand.target || "当前线程"}${shortRequirementLabel(featuredCommand.requirementId) ? ` 的 ${shortRequirementLabel(featuredCommand.requirementId)}` : ""}` : ""}，这些线程不用你手动逐个催，平台会继续等最小回执和最终回复。`,
      meta: `当前负责人 ${ownerLabel} / 活跃线程 ${activeSourceThreadCount} 条 / 平台队列 ${queuedCount} 条${featuredQueuedCommand ? ` / 当前聚焦 ${featuredQueuedCommand.target || "当前线程"}${shortRequirementLabel(featuredQueuedCommand.requirementId) ? ` · ${shortRequirementLabel(featuredQueuedCommand.requirementId)}` : ""}` : featuredCommand ? ` / 当前聚焦 ${featuredCommand.target || "当前线程"}${shortRequirementLabel(featuredCommand.requirementId) ? ` · ${shortRequirementLabel(featuredCommand.requirementId)}` : ""}` : ""}${oldestQueuedCommand?.queueStartedAtLabel ? ` / 最早排队 ${oldestQueuedCommand.queueStartedAtLabel}` : ""}${oldestQueuedCommand?.queueAgeLabel ? ` / 已等 ${oldestQueuedCommand.queueAgeLabel}` : ""}${oldestQueuedCommand?.queueStateLabel ? ` / 队列判断 ${oldestQueuedCommand.queueStateLabel}` : ""} / 最近指令 ${latestCommand.title}`,
    };
  }

  const latestRelay = relayFeed[0] ?? null;
  if (latestRelay) {
    return {
      foldSummary: `协作脉搏：最近回执《${latestRelay.title}》 · ${formatEpoch(latestRelay.at)}`,
      title: "协作正在跑",
      body: `${latestRelay.title}：${latestRelay.body}`,
      meta: `当前负责人 ${ownerLabel} / 活跃线程 ${activeSourceThreadCount} 条 / 维护链 ${activeMaintenanceCount} 条`,
    };
  }

  const latestFinal = finalReplyFeed[0] ?? null;
  if (latestFinal) {
    return {
      foldSummary: `协作脉搏：上一轮已收口 · 最新最终回复 ${formatEpoch(latestFinal.finalReplyAt)}`,
      title: "上一轮已收口",
      body: `${latestFinal.title} 已进入最终回复池，平台现在优先等待下一条最小回执。`,
      meta: `当前负责人 ${ownerLabel} / 活跃线程 ${activeSourceThreadCount} 条 / 维护链 ${activeMaintenanceCount} 条`,
    };
  }

  if (activeSourceThreadCount > 0) {
    return {
      foldSummary: "协作脉搏：线程在线，等待回执",
      title: "线程在线，等待回执",
      body: `当前已有 ${activeSourceThreadCount} 条活跃线程，但还没有新的真实回执进入过程区。`,
      meta: `当前负责人 ${ownerLabel} / 维护链 ${activeMaintenanceCount} 条`,
    };
  }

  return {
    foldSummary: "协作脉搏：暂无真实回执",
    title: "还没有真实回执",
    body: "先让真实电脑、真实线程和真实席位接单，过程区才会真正滚动起来。",
    meta: `当前负责人 ${ownerLabel} / 维护链 ${activeMaintenanceCount} 条`,
  };
}

function buildMaintenanceBoard(requirements: AnyRecord[]) {
  const templates = ["平台主链自检", "复查电脑与线程扫描", "人工确认平台风险点"];

  return templates.map((title) => {
    const match = requirements.find((item) => text(item.title, "") === title);
    return {
      title,
      status: match ? text(match.status, "waiting_response") : "missing",
      target: match ? text(match.to_agent, "待指定") : "待指定",
    };
  });
}

function normalizePanelView(value: unknown): PanelView {
  const raw = text(value, "exchange") as PanelView;
  return PANEL_DEFINITIONS.some((item) => item.id === raw) ? raw : "exchange";
}

function sortedByUpdatedAt(items: AnyRecord[]) {
  return items
    .slice()
    .sort(
      (left, right) =>
        new Date(text(right.updated_at ?? right.created_at, "1970-01-01")).getTime() -
        new Date(text(left.updated_at ?? left.created_at, "1970-01-01")).getTime(),
    );
}

function seatRouteKeys(seat: AnyRecord) {
  return uniqueStrings([
    seat.canonical_seat_id,
    seat.id,
    seat.workstation_id,
    seat.config_id,
    seat.row_id,
    seat.agent_id,
    seat.source_workstation_id,
    seat.metadata?.source_workstation_id,
    seat.metadata?.display_name,
    seat.name,
  ]);
}

function preferredSeatRouteId(seat: AnyRecord, seatView?: MapSeatPayload | null) {
  return text(
    seatView?.id ??
      seat.canonical_seat_id ??
      seat.source_workstation_id ??
      seat.metadata?.source_workstation_id ??
      seat.row_id ??
      seat.id ??
      seat.config_id,
    "",
  );
}

function requirementMatchesSeat(requirement: AnyRecord, seat: AnyRecord) {
  const target = text(requirement.to_agent, "");
  if (!target) return false;
  const targetLower = target.toLowerCase();
  return seatRouteKeys(seat).some((candidate) => candidate.toLowerCase() === targetLower);
}

function taskMatchesSeat(task: AnyRecord, seat: AnyRecord) {
  const seatKeys = seatRouteKeys(seat).map((item) => item.toLowerCase());
  const taskKeys = uniqueStrings([
    task.latest_dispatch?.workstation_id,
    task.latest_dispatch?.workstation_name,
    task.assignee_agent_id,
  ]).map((item) => item.toLowerCase());
  return taskKeys.some((candidate) => seatKeys.includes(candidate));
}

function threadRouteKeys(thread: AnyRecord) {
  return uniqueStrings([
    thread.id,
    thread.workstation_id,
    thread.source_workstation_id,
    thread.metadata?.source_workstation_id,
    thread.name,
  ]);
}

function threadMatchesSeat(thread: AnyRecord, seat: AnyRecord) {
  const threadKeys = threadRouteKeys(thread).map((item) => item.toLowerCase());
  return seatRouteKeys(seat).some((candidate) => threadKeys.includes(candidate.toLowerCase()));
}

function resolveSeatViewForRecord(seat: AnyRecord, seatPayloadMap: Map<string, MapSeatPayload>) {
  for (const key of seatRouteKeys(seat)) {
    const direct = seatPayloadMap.get(key);
    if (direct) return direct;
    const lowered = seatPayloadMap.get(key.toLowerCase());
    if (lowered) return lowered;
  }
  return null;
}

function guessNpcName(thread: AnyRecord, fallbackIndex: number) {
  const explicitName = text(thread.name ?? thread.label, "");
  if (/^npc\d+$/i.test(explicitName)) return explicitName.toUpperCase();
  const sessionName = text(thread.id ?? thread.workstation_id, "");
  const matchedNpc = explicitName.match(/npc[\s_-]*(\d+)/i) ?? sessionName.match(/npc[\s_-]*(\d+)/i);
  if (matchedNpc) return `NPC${matchedNpc[1]}`;
  return `NPC${fallbackIndex + 1}`;
}

function guessNpcResponsibility(thread: AnyRecord) {
  const name = text(thread.name ?? thread.label, "").toLowerCase();
  if (name.includes("ui") || name.includes("front")) return "界面协作 / 结果展示";
  if (name.includes("git")) return "Git 协作 / 结果回流";
  if (name.includes("proof")) return "闭环证明 / 稳定性验证";
  if (name.includes("scan")) return "线程扫描 / 线程接单";
  if (name.includes("review")) return "审核把关 / 风险复查";
  return "线程协作 / 平台推进";
}

function resolveSeatSkillLoadout(seat: AnyRecord, skillLibrary: AnyRecord[]) {
  const additionalSkillIds = asArray(seat.additional_skill_ids ?? seat.metadata?.additional_skill_ids)
    .map((skill) => text(skill))
    .filter(Boolean);
  const storedSkillIds = asArray(seat.skill_loadout ?? seat.metadata?.skill_loadout)
    .map((skill) => text(skill))
    .filter(Boolean);
  const splitLoadout = splitPlatformSkillLoadout([...additionalSkillIds, ...storedSkillIds], skillLibrary);
  const roleSkillIds = uniqueStrings([...additionalSkillIds, ...splitLoadout.roleSkillIds]);
  const allSkillIds = mergePlatformSkillLoadout(roleSkillIds);
  return {
    additionalSkillIds: roleSkillIds,
    allSkillIds,
    baselineSkillIds: splitLoadout.baselineSkillIds,
  };
}

function describeSeatReviewState(tasks: AnyRecord[], hasProtectedDataGap: boolean) {
  if (hasProtectedDataGap) return "协作数据未授权";
  if (tasks.some((task) => text(task.status, "").toLowerCase() === "waiting_approval")) return "等待人工审批";
  if (tasks.some((task) => text(task.status, "").toLowerCase() === "reviewing")) return "人工审核中";
  if (tasks.some((task) => text(task.status, "").toLowerCase() === "blocked")) return "审批阻塞";
  if (tasks.some((task) => Boolean(task.requires_human_approval))) return "需要人工确认";
  return "无需人审";
}

function describeSeatAutonomyDecision(options: {
  hasProtectedDataGap: boolean;
  activeRequirement: AnyRecord | null;
  latestMinimalAck: AnyRecord | null;
  latestFinalReply: AnyRecord | null;
  relatedTasks: AnyRecord[];
  lateProgressAck: boolean;
  staleAfterAck: boolean;
  legacyProgressSignal: boolean;
  selectionRecovered: boolean;
}) {
  const {
    hasProtectedDataGap,
    activeRequirement,
    latestMinimalAck,
    latestFinalReply,
    relatedTasks,
    lateProgressAck,
    staleAfterAck,
    legacyProgressSignal,
    selectionRecovered,
  } = options;
  if (hasProtectedDataGap) return "重新登录后再判断自动推进还是人工审核";
  if (relatedTasks.some((task) => text(task.status, "").toLowerCase() === "waiting_approval")) {
    return "暂停自动推进，等待人工审批";
  }
  if (relatedTasks.some((task) => text(task.status, "").toLowerCase() === "reviewing")) {
    return "等待人工审核结论";
  }
  if (latestFinalReply && !activeRequirement) return "本轮已收口，可继续接下一条 requirement";
  if (staleAfterAck) return "最小回执后停滞，建议重新派单或人工接手";
  if (latestMinimalAck && !latestFinalReply && legacyProgressSignal) return "线程仍在推进，但进度信号还待归一";
  if (latestMinimalAck && !latestFinalReply && lateProgressAck) {
    return selectionRecovered ? "线程已恢复推进，但最小回执偏晚，继续盯住收口" : "已给最小回执，但回执偏晚，建议尽快复核是否卡住";
  }
  if (latestMinimalAck && !latestFinalReply) return "已给最小回执，可继续自动推进";
  if (activeRequirement) return "已接单，等待最小回执";
  return "当前空闲，可接受新任务";
}

function buildSeatMapPayload(options: {
  seats: AnyRecord[];
  tasks: AnyRecord[];
  requirements: AnyRecord[];
  messageMap: RequirementMessageMap;
  skillLibrary: AnyRecord[];
  knowledgeSnapshots: Record<string, AnyRecord>;
  autonomyStatuses: Record<string, AnyRecord>;
  hasProtectedDataGap: boolean;
  resolveDisplay: DisplayResolver;
  projectRepoDefaults?: {
    githubUrl?: string | null;
    branch?: string | null;
  };
}): MapSeatPayload[] {
  const {
    seats,
    tasks,
    requirements,
    messageMap,
    skillLibrary,
    knowledgeSnapshots,
    autonomyStatuses,
    hasProtectedDataGap,
    resolveDisplay,
    projectRepoDefaults,
  } = options;
  const skillLabelMap = new Map<string, string>();

  skillLibrary.forEach((skill) => {
    const skillId = text(skill.id, "");
    if (!skillId) return;
    skillLabelMap.set(skillId, text(skill.label, skillId));
  });

  return seats.map((seat, index) => {
    const relatedRequirements = requirements
      .filter((requirement) => requirementMatchesSeat(requirement, seat))
      .slice()
      .sort((left, right) => requirementActivityAt(right, messageMap) - requirementActivityAt(left, messageMap));
    const relatedTasks = tasks
      .filter((task) => taskMatchesSeat(task, seat))
      .slice()
      .sort((left, right) => latestDispatchAt(right) - latestDispatchAt(left));
    const activeRequirement = relatedRequirements.find((requirement) => !isDoneStatus(requirement.status)) ?? null;
    const allMessages = relatedRequirements
      .flatMap((requirement) => messageMap.get(text(requirement.id ?? requirement.requirement_id, "")) ?? [])
      .slice()
      .sort((left, right) => latestMessageAt(right) - latestMessageAt(left));
    const activeRequirementMessages = activeRequirement
      ? (messageMap.get(text(activeRequirement.id ?? activeRequirement.requirement_id, "")) ?? [])
          .slice()
          .sort((left, right) => latestMessageAt(right) - latestMessageAt(left))
      : allMessages;
    const scopedMessages = activeRequirement ? activeRequirementMessages : allMessages;
    const latestMinimalAck =
      scopedMessages.find((message) => {
        const messageType = text(message.message_type, "").toLowerCase();
        const messageStatus = text(message.status, "").toLowerCase();
        if (messageType === "requirement_progress_ack") return messageStatus === "in_progress";
        if (messageType === "requirement_final_reply") return messageStatus === "in_progress";
        return ["agent_report", "runner_ack", "runner_result"].includes(messageType);
      }) ?? null;
    const latestFinalReply = scopedMessages.find((message) => isFinalReplyMessage(message)) ?? null;
    const latestMinimalAckType = latestMinimalAck ? text(latestMinimalAck.message_type, "").toLowerCase() : null;
    const activeRequirementCreatedAt = activeRequirement ? requirementCreatedAt(activeRequirement) : 0;
    const minimalAckAt = latestMessageAt(latestMinimalAck);
    const progressLagMinutes =
      latestMinimalAck && activeRequirementCreatedAt > 0 && minimalAckAt > 0
        ? Math.max(0, Math.floor((minimalAckAt - activeRequirementCreatedAt) / 60000))
        : null;
    const staleAfterAckMinutes =
      latestMinimalAck && !latestFinalReply
        ? queueAgeMinutes(minimalAckAt)
        : null;
    const sourceThreadId = text(seat.source_workstation_id ?? seat.metadata?.source_workstation_id, "");
    const seatIdentityKeys = uniqueStrings([
      seat.canonical_seat_id,
      seat.id,
      seat.config_id,
      seat.row_id,
      sourceThreadId,
    ]);
    const autonomyStatus =
      seatIdentityKeys
        .map((key) => autonomyStatuses[key])
        .find(Boolean) ?? null;
    const selectionRecovered = Boolean(
      activeRequirement &&
        text(autonomyStatus?.lastSelectedRequirementId, "") &&
        text(autonomyStatus?.lastSelectedRequirementId, "") === text(activeRequirement.id, "") &&
        !Boolean(autonomyStatus?.consumerStateStale) &&
        !Boolean(autonomyStatus?.heartbeatMissing) &&
        (!text(autonomyStatus?.automationStatus, "") || text(autonomyStatus?.automationStatus, "").toUpperCase() === "ACTIVE"),
    );
    const lateProgressAck = progressLagMinutes !== null && progressLagMinutes >= LATE_PROGRESS_ACK_MINUTES;
    const legacyProgressSignal =
      latestMinimalAckType === "requirement_final_reply" &&
      text(latestMinimalAck?.status, "").toLowerCase() === "in_progress";
    const staleAfterAck =
      staleAfterAckMinutes !== null && staleAfterAckMinutes >= STALE_AFTER_ACK_MINUTES && !selectionRecovered;
    const progressWarningLabel = staleAfterAck
      ? "最小回执后停滞"
      : legacyProgressSignal
        ? "进度信号待归一"
      : lateProgressAck
        ? "最小回执偏晚"
        : null;
    const progressHealthLabel = latestFinalReply
      ? "已收口"
      : staleAfterAck
        ? "停在最小回执"
      : latestMinimalAck
          ? legacyProgressSignal
            ? "自动推进中"
            : lateProgressAck
              ? selectionRecovered
                ? "恢复推进中"
                : "回执偏晚"
              : "自动推进中"
          : activeRequirement
            ? "等待最小回执"
            : "当前空闲";
    const reviewState = describeSeatReviewState(relatedTasks, hasProtectedDataGap);
    const approvalState =
      reviewState === "无需人审"
        ? "自动推进"
        : reviewState === "协作数据未授权"
          ? "待恢复协作数据"
          : "等待人审";
    const autonomyDecision = describeSeatAutonomyDecision({
      hasProtectedDataGap,
      activeRequirement,
      latestMinimalAck,
      latestFinalReply,
      relatedTasks,
      lateProgressAck,
      staleAfterAck,
      legacyProgressSignal,
      selectionRecovered,
    });
    const seatSkills = resolveSeatSkillLoadout(seat, skillLibrary);
    const skillLoadout = seatSkills.allSkillIds;
    const knowledgeProfile = resolveNpcKnowledgeProfile(seat, {
      fallbackName: text(seat.name, `NPC ${index + 1}`),
      fallbackResponsibility: text(seat.responsibility ?? seat.metadata?.responsibility, "待分配职责"),
    });
    const knowledgeSnapshot =
      seatIdentityKeys
        .map((key) => knowledgeSnapshots[key])
        .find(Boolean) ??
      knowledgeSnapshots[knowledgeProfile.handoff_path] ??
      null;
    const providerId = platformProviderIdFromSeat(seat);
    const providerLabel = platformProviderLabelFromSeat(seat);
    const supportsBridge = supportsLocalCodexAutonomyBridge(providerId);
    const collabProtocol = resolvePlatformCollabProtocol(seat.metadata?.collab_protocol, {
      providerId,
      roleText: text(seat.responsibility ?? seat.metadata?.responsibility, ""),
      threadText: text(seat.name, ""),
      repoContext: {
        repository_url: text(projectRepoDefaults?.githubUrl, "") || null,
        branch: text(projectRepoDefaults?.branch, "") || null,
        relative_root: ".",
      },
    });
    const seatReferencePaths = buildPlatformRepoReferencePaths({
      referencePaths: collabProtocol.reference_paths,
      repositoryUrl:
        collabProtocol.repo_context?.repository_url ??
        (text(projectRepoDefaults?.githubUrl, "") || null),
      branch:
        collabProtocol.repo_context?.branch ??
        (text(projectRepoDefaults?.branch, "") || null),
      gitBoundary: asArray(seat.git_boundary ?? seat.metadata?.git_boundary).map((item) => text(item)).filter(Boolean),
      handoffPath: knowledgeProfile.handoff_path,
    });
    const rawSeatId = text(seat.id ?? seat.config_id ?? seat.row_id, `seat-${index + 1}`);
    const shouldUseSourceThreadId =
      Boolean(sourceThreadId) && (looksLikeUuid(rawSeatId) || rawSeatId.includes("?") || isQuestionMarkHeavy(rawSeatId));
    const seatId = text(
      seat.canonical_seat_id,
      shouldUseSourceThreadId ? sourceThreadId : rawSeatId,
    );
    const recentTasks = relatedTasks.slice(0, 3).map((task) => ({
      title: safeDisplayTitle(task.title, "未命名任务"),
      status: text(task.status, "draft"),
      review: describeSeatReviewState([task], hasProtectedDataGap),
    }));
    const provisioning = summarizeNpcProvisioning({
      providerId,
      providerLabel,
      sourceThreadId,
      hasActiveRequirement: Boolean(activeRequirement),
      autonomyReady: Boolean(autonomyStatus?.autonomyReady),
      supportsLocalAutonomyBridge: supportsBridge,
      consumerScriptExists: Boolean(autonomyStatus?.consumerScriptExists),
      consumerStateExists: Boolean(autonomyStatus?.consumerStateExists),
      consumerStateStale: Boolean(autonomyStatus?.consumerStateStale),
      heartbeatMissing: Boolean(autonomyStatus?.heartbeatMissing),
      heartbeatStatus: text(autonomyStatus?.automationStatus, "") || null,
      sessionSeen: Boolean(autonomyStatus?.sessionSeen),
      sessionRegistered: Boolean(autonomyStatus?.sessionRegistered),
      sessionStatus: text(autonomyStatus?.sessionStatus, "") || null,
      sessionLaunchBlocked: Boolean(autonomyStatus?.sessionLaunchBlocked),
      sessionLaunchBlockReason: text(autonomyStatus?.lastLaunchErrorSummary, "") || null,
    });

    return {
      id: seatId,
      name: text(seat.name, `NPC ${index + 1}`),
      role: text(seat.responsibility ?? seat.metadata?.responsibility, "待分配职责"),
      status:
        reviewState === "等待人工审批" || reviewState === "人工审核中" || reviewState === "审批阻塞"
          ? "paused"
          : activeRequirement || latestMinimalAck
            ? "active"
            : "idle",
      providerId,
      providerLabel,
      automationEnabled: booleanFromUnknown(seat.metadata?.automation_enabled, false),
      heartbeatIntervalSeconds: normalizeAutomationHeartbeatSeconds(seat.metadata?.automation_heartbeat_seconds),
      scene: text(seat.scene_key ?? seat.metadata?.scene, "map-farm"),
      x: asNumber(seat.x ?? seat.metadata?.map_x ?? seat.metadata?.x),
      y: asNumber(seat.y ?? seat.metadata?.map_y ?? seat.metadata?.y),
      avatar: text(seat.sprite_key ?? seat.metadata?.avatar_key, "jack-standing"),
      description: text(seat.description ?? seat.notes, ""),
      sourceThreadId,
      nodeName: text(seat.computer_node ?? seat.metadata?.computer_node, "未绑定电脑"),
      executionModel: text(seat.model ?? seat.metadata?.model, "gpt-5.4"),
      developmentStationId: text(seat.metadata?.development_station_id ?? seat.development_station_id, ""),
      developmentStationLabel: text(seat.metadata?.development_station_label ?? seat.development_station_label, ""),
      skillLoadout,
      skillLabels: skillLoadout.map((skillId) => ({
        id: skillId,
        label: skillLabelMap.get(skillId) ?? skillId,
      })),
      knowledgeKey: knowledgeProfile.key,
      knowledgeTitle: knowledgeProfile.title,
      knowledgeSummary: knowledgeProfile.summary,
      knowledgeHandoffPath: knowledgeProfile.handoff_path,
      knowledgeHighlights: asArray(knowledgeSnapshot?.highlights).map((item) => text(item)).filter(Boolean).slice(0, 3),
      knowledgeUpdatedAt: text(knowledgeSnapshot?.updatedAt, "") || null,
      knowledgeDocExists: Boolean(knowledgeSnapshot?.exists),
      protocolWorkKind: collabProtocol.work_kind,
      protocolApprovalPolicy: collabProtocol.approval_policy,
      protocolProjectProfile: collabProtocol.project_profile,
      protocolCapabilities: collabProtocol.required_capabilities,
      protocolReferences: seatReferencePaths,
      protocolRepoSummary: platformRepoContextSummary(collabProtocol.repo_context),
      protocolTokenSummary: collabTokenPolicySummary(collabProtocol),
      protocolRunawaySummary: collabRunawayPolicySummary(collabProtocol),
      protocolEfficiencySummary: collabEfficiencyPolicySummary(collabProtocol),
      protocolDebugSummary: collabDebugPolicySummary(collabProtocol),
      protocolMaxAutoRounds: collabProtocol.runaway_policy.max_auto_rounds,
      protocolHumanReviewAfterRounds: collabProtocol.runaway_policy.human_review_after_rounds,
      protocolParallelismLimit: collabProtocol.efficiency_policy.parallelism_limit,
      protocolSimulationFirst: collabProtocol.debug_policy.simulation_first,
      protocolHardwareWriteRequiresReview: collabProtocol.debug_policy.hardware_write_requires_review,
      autonomyBridgeLabel: text(
        autonomyStatus?.bridgeHealthLabel ?? autonomyStatus?.autonomyLabel,
        supportsBridge
          ? sourceThreadId
            ? "缺 consumer"
            : "待绑定 Codex 线程"
          : sourceThreadId
            ? `${providerLabel} 已绑定`
            : `待绑定 ${providerLabel} 线程`,
      ),
      autonomyReady: Boolean(autonomyStatus?.autonomyReady),
      supportsLocalAutonomyBridge: supportsBridge,
      consumerScriptPath: text(autonomyStatus?.consumerScriptPath, "") || null,
      consumerScriptExists: Boolean(autonomyStatus?.consumerScriptExists),
      consumerStatePath: text(autonomyStatus?.consumerStatePath, "") || null,
      consumerStateExists: Boolean(autonomyStatus?.consumerStateExists),
      consumerStateUpdatedAt: text(autonomyStatus?.consumerStateUpdatedAt, "") || null,
      consumerStateAgeMinutes: asNumber(autonomyStatus?.consumerStateAgeMinutes),
      consumerStateStale: Boolean(autonomyStatus?.consumerStateStale),
      heartbeatAutomationId: text(autonomyStatus?.automationId, "") || null,
      heartbeatStatus: text(autonomyStatus?.automationStatus, "") || null,
      heartbeatUpdatedAt: text(autonomyStatus?.automationUpdatedAt, "") || null,
      heartbeatMissing: Boolean(autonomyStatus?.heartbeatMissing),
      lastSelectedRequirementId: text(autonomyStatus?.lastSelectedRequirementId, "") || null,
      lastSelectedAt: text(autonomyStatus?.lastSelectedAt, "") || null,
      lastPlatformFetchRequirementId: text(autonomyStatus?.lastPlatformFetchRequirementId, "") || null,
      lastPlatformFetchAt: text(autonomyStatus?.lastPlatformFetchAt, "") || null,
      gitBoundary: asArray(seat.git_boundary ?? seat.metadata?.git_boundary).map((item) => text(item)).filter(Boolean),
      currentRequirement:
        activeRequirement
          ? requirementDisplayTitle(activeRequirement, resolveDisplay)
          : null,
      currentRequirementId: activeRequirement ? text(activeRequirement.id, "") || null : null,
      currentRequirementStatus: activeRequirement ? text(activeRequirement.status, "waiting_response") : null,
      recentTasks,
      minimalAck: latestMinimalAck ? shortText(latestMinimalAck.body, text(latestMinimalAck.title, "已有最小回执"), 96) : null,
      minimalAckAt: latestMinimalAck ? text(latestMinimalAck.created_at ?? latestMinimalAck.updated_at, "") || null : null,
      minimalAckType: latestMinimalAckType,
      legacyProgressSignal,
      finalReply: latestFinalReply ? shortText(latestFinalReply.body, text(latestFinalReply.title, "已有最终回复"), 96) : null,
      finalReplyAt: latestFinalReply ? text(latestFinalReply.created_at ?? latestFinalReply.updated_at, "") || null : null,
      progressLagMinutes,
      staleAfterAck,
      staleAfterAckMinutes,
      progressHealthLabel,
      progressWarningLabel,
      selectionRecovered,
      autonomyDecision,
      reviewState,
      approvalState,
      lastSignalAt:
        text(
          latestFinalReply?.created_at ??
            latestFinalReply?.updated_at ??
            latestMinimalAck?.created_at ??
            latestMinimalAck?.updated_at ??
            activeRequirement?.last_activity_at,
          "",
        ) || null,
      provisioningState: provisioning.state,
      provisioningLabel: provisioning.label,
      provisioningDetail: provisioning.detail,
      provisioningNeeds: provisioning.missing,
    } satisfies MapSeatPayload;
  });
}

type TokenResultCardProps = {
  title: string;
  subtitle?: string;
  token: string;
  command: string;
  linuxCommand?: string;
  watchCommand?: string;
  linuxWatchCommand?: string;
  testId?: string;
};

function TokenResultCard({
  title,
  subtitle,
  token,
  command,
  linuxCommand,
  watchCommand,
  linuxWatchCommand,
  testId,
}: TokenResultCardProps) {
  const [copyState, setCopyState] = useState<{ kind: "idle" | "ok" | "err"; message?: string }>({
    kind: "idle",
  });

  async function copyText(text: string, okMessage: string) {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else if (typeof document !== "undefined") {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      } else {
        throw new Error("剪贴板不可用");
      }
      setCopyState({ kind: "ok", message: okMessage });
      setTimeout(() => setCopyState({ kind: "idle" }), 3000);
    } catch (error) {
      setCopyState({
        kind: "err",
        message: `复制失败：${error instanceof Error ? error.message : "未知错误"}`,
      });
      setTimeout(() => setCopyState({ kind: "idle" }), 4000);
    }
  }

  return (
    <article
      className={styles.successBanner}
      data-token-result-card={testId || "true"}
      style={{ display: "flex", flexDirection: "column", gap: 8 }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <strong>{title}</strong>
        {subtitle ? <span style={{ fontWeight: 400, opacity: 0.85 }}>{subtitle}</span> : null}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <code style={{ background: "rgba(0,0,0,0.25)", padding: "2px 6px", borderRadius: 6, wordBreak: "break-all" }}>
          {token}
        </code>
        <button
          type="button"
          className={styles.ghostButton}
          onClick={() => copyText(token, "令牌已复制到剪贴板")}
          data-token-copy-token={testId || "true"}
        >
          复制令牌
        </button>
      </div>
      <p style={{ margin: "4px 0", fontWeight: 400, opacity: 0.9 }}>
        把下面命令发到目标电脑运行。命令会自动下载平台最新版接入脚本，无需提前 clone 仓库。
      </p>
      <p style={{ margin: "4px 0", fontWeight: 700, opacity: 0.95 }}>Windows PowerShell</p>
      <textarea
        readOnly
        rows={4}
        value={command}
        aria-label="电脑接入命令"
        data-token-command={testId || "true"}
        style={{
          width: "100%",
          fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
          fontSize: 11,
          background: "rgba(0,0,0,0.32)",
          color: "#f6edd8",
          border: "1px solid rgba(246,237,216,0.12)",
          borderRadius: 10,
          padding: "8px 10px",
          resize: "vertical",
        }}
      />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button
          type="button"
          className={styles.ghostButton}
          onClick={() => copyText(command, "接入命令已复制，可以粘贴到目标电脑 PowerShell 运行")}
          data-token-copy-command={testId || "true"}
        >
          复制完整命令
        </button>
        {copyState.kind !== "idle" && copyState.message ? (
          <small
            style={{
              opacity: 0.95,
              color: copyState.kind === "ok" ? "#b7f0ad" : "#ffb4b4",
            }}
            data-token-copy-status={copyState.kind}
          >
            {copyState.message}
          </small>
        ) : null}
      </div>
      {linuxCommand ? (
        <>
          <p style={{ margin: "4px 0", fontWeight: 700, opacity: 0.95 }}>Linux / macOS bash</p>
          <textarea
            readOnly
            rows={4}
            value={linuxCommand}
            aria-label="Linux 或 macOS 接入命令"
            data-token-linux-command={testId || "true"}
            style={{
              width: "100%",
              fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
              fontSize: 11,
              background: "rgba(0,0,0,0.32)",
              color: "#f6edd8",
              border: "1px solid rgba(246,237,216,0.12)",
              borderRadius: 10,
              padding: "8px 10px",
              resize: "vertical",
            }}
          />
          <button
            type="button"
            className={styles.ghostButton}
            onClick={() => copyText(linuxCommand, "Linux / macOS 接入命令已复制")}
            data-token-copy-linux-command={testId || "true"}
            style={{ alignSelf: "flex-start" }}
          >
            复制 Linux / macOS 命令
          </button>
        </>
      ) : null}
      {watchCommand ? (
        <details style={{ marginTop: 4 }} data-token-watch-card={testId || "true"}>
          <summary style={{ cursor: "pointer", fontWeight: 600 }}>
            ▷ 想让平台下发的指令真的进 CLI？复制下面这条「持续协作」命令运行（替代上面那条）
          </summary>
          <p style={{ margin: "6px 0", fontWeight: 400, opacity: 0.9 }}>
            上面&quot;一键接入&quot;只跑一次就退出。要让平台派单 / 指令实时进入本机 Claude / Codex CLI，
            必须用下面这条带 <code>-Watch -WatchExecuteProviderCli</code> 的命令，并保持窗口运行。
          </p>
          <textarea
            readOnly
            rows={4}
            value={watchCommand}
            aria-label="持续协作命令"
            data-token-watch-command={testId || "true"}
            style={{
              width: "100%",
              fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
              fontSize: 11,
              background: "rgba(0,0,0,0.32)",
              color: "#f6edd8",
              border: "1px solid rgba(246,237,216,0.12)",
              borderRadius: 10,
              padding: "8px 10px",
              resize: "vertical",
            }}
          />
          <button
            type="button"
            className={styles.ghostButton}
            onClick={() => copyText(watchCommand, "持续协作命令已复制，请在目标电脑运行并保持窗口")}
            data-token-copy-watch={testId || "true"}
            style={{ marginTop: 6 }}
          >
            复制持续协作命令
          </button>
          {linuxWatchCommand ? (
            <>
              <p style={{ margin: "8px 0 4px", fontWeight: 700, opacity: 0.95 }}>Linux / macOS bash</p>
              <textarea
                readOnly
                rows={4}
                value={linuxWatchCommand}
                aria-label="Linux 或 macOS 持续协作命令"
                data-token-linux-watch-command={testId || "true"}
                style={{
                  width: "100%",
                  fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                  fontSize: 11,
                  background: "rgba(0,0,0,0.32)",
                  color: "#f6edd8",
                  border: "1px solid rgba(246,237,216,0.12)",
                  borderRadius: 10,
                  padding: "8px 10px",
                  resize: "vertical",
                }}
              />
              <button
                type="button"
                className={styles.ghostButton}
                onClick={() => copyText(linuxWatchCommand, "Linux / macOS 持续协作命令已复制")}
                data-token-copy-linux-watch={testId || "true"}
                style={{ marginTop: 6 }}
              >
                复制 Linux / macOS 持续协作命令
              </button>
            </>
          ) : null}
        </details>
      ) : null}
    </article>
  );
}

export function ProjectPlayableShell(props: ProjectPlayableShellProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const teamNoticeToast = useTeamNoticeToast({ onRefresh: () => router.refresh() });

  // server action redirect 后 URL 上一定带 team_notice，作为"动作完成"的可靠信号；
  // 主动 router.refresh() 强制重新拉 server data，避免用户看到旧 props。
  // useTeamNoticeToast 也会调一次 onRefresh，这里再加一道保险（依赖 searchParams 变化）。
  const teamNoticeKey = searchParams?.get("team_notice") ?? "";
  const pairingTokenKey = searchParams?.get("pairing_token") ?? "";
  const adapterTokenKey = searchParams?.get("adapter_token") ?? "";
  useEffect(() => {
    if (!teamNoticeKey && !pairingTokenKey && !adapterTokenKey) return;
    router.refresh();
  }, [router, teamNoticeKey, pairingTokenKey, adapterTokenKey]);
  const nodes = asArray(props.config?.nodes);
  const onlineNodes = nodes.filter((node) => isComputerRunnerOnline(node));
  const watchReadyNodes = nodes.filter((node) => runnerWatchInfo(node).active);
  const watchBlockedNodes = nodes.filter((node) => runnerWatchInfo(node).needsAttention);
  const sourceThreads = asArray(props.config?.sourceThreads);
  const activeSourceThreads = asArray(props.config?.activeSourceThreads ?? sourceThreads);
  const queuedCollaborationCommands = props.collaborationMessages.filter((message) => {
    const messageType = text(message.message_type, "").toLowerCase();
    const messageStatus = text(message.status ?? message.sourceStatus ?? message.source_status, "").toLowerCase();
    return ["agent_command", "runner_command", "thread_scan_request", "requirement_dispatch"].includes(messageType)
      && isQueuedBridgeStatus(messageStatus);
  });
  const queuedCollaborationCommandCount = queuedCollaborationCommands.length;
  const queuedCollaborationCommandDetails = queuedCollaborationCommands
    .map((message) => {
      const createdAt = new Date(text(message.created_at ?? message.createdAt ?? message.updated_at ?? message.updatedAt, "1970-01-01")).getTime();
      const ageMinutes = queueAgeMinutes(createdAt);
      const messageType = text(message.message_type, "agent_command");
      const target = safeDisplayTitle(
        message.recipient_label ?? message.recipient_name ?? message.recipient_id ?? message.workstation_id ?? message.agent_id,
        "目标线程",
      );
      return {
        message,
        createdAt,
        ageMinutes,
        ageLabel: formatQueueAge(ageMinutes) ?? "未知时长",
        stateLabel: queueStateLabel(ageMinutes) ?? "等待接单",
        title: safeDisplayTitle(message.title, "平台排队指令"),
        target,
        typeLabel: messageType === "thread_scan_request" ? "线程扫描" : messageType === "requirement_dispatch" ? "需求派单" : "AI 指令",
      };
    })
    .sort((left, right) => left.createdAt - right.createdAt);
  const staleQueuedCollaborationCommands = queuedCollaborationCommandDetails.filter(
    (item) => item.ageMinutes !== null && item.ageMinutes >= 120,
  );
  const oldestQueuedCollaborationCommand = queuedCollaborationCommandDetails[0] ?? null;
  const staleQueuedCommandCount = staleQueuedCollaborationCommands.length;
  const providerRecords = useMemo(() => {
    const providerMap = new Map<string, AnyRecord>();
    const rememberProvider = (candidate: AnyRecord | null | undefined, fallback?: { id?: string | null; label?: string | null; model?: string | null }) => {
      const provider = candidate && typeof candidate === "object" ? candidate : {};
      const providerId = normalizePlatformProviderId(
        provider.id ?? provider.ai_provider_id ?? provider.provider_id ?? fallback?.id,
      );
      if (!providerId) return;
      const previous = providerMap.get(providerId) ?? {};
      providerMap.set(providerId, {
        ...previous,
        ...provider,
        id: providerId,
        label:
          text(provider.label ?? provider.name ?? fallback?.label, "") ||
          text(previous.label ?? previous.name, "") ||
          platformProviderLabel(providerId),
        model: text(provider.model ?? provider.default_model ?? fallback?.model, "") || text(previous.model, "") || null,
      });
    };
    asArray(props.config?.providers).forEach((provider) => rememberProvider(provider));
    [...activeSourceThreads, ...sourceThreads].forEach((thread) =>
      rememberProvider(null, {
        id: platformProviderIdFromThread(thread),
        label: platformProviderLabelFromThread(thread),
        model: text(thread.model ?? thread.metadata?.model, "") || null,
      }),
    );
    return Array.from(providerMap.values()).sort((left, right) => {
      const leftId = text(left.id, "");
      const rightId = text(right.id, "");
      const orderDelta = providerExecutionSortOrder(leftId) - providerExecutionSortOrder(rightId);
      if (orderDelta !== 0) return orderDelta;
      return text(left.label, leftId).localeCompare(text(right.label, rightId), "zh-CN");
    });
  }, [props.config?.providers, activeSourceThreads, sourceThreads]);
  const providerById = useMemo(
    () =>
      new Map(
        providerRecords
          .map((provider) => [text(provider.id, "").toLowerCase(), provider] as const)
          .filter(([providerId]) => Boolean(providerId)),
      ),
    [providerRecords],
  );
  const nodeById = useMemo(
    () =>
      new Map(
        nodes
          .map((node) => [text(node.id, "").toLowerCase(), node] as const)
          .filter(([nodeId]) => Boolean(nodeId)),
      ),
    [nodes],
  );
  const machineRoomProviderCards = useMemo<AnyRecord[]>(
    () =>
      providerRecords.map((provider) => {
        const providerId = text(provider.id, "");
        const metadata = objectRecord(provider.metadata);
        const adapter = adapterTemplate(metadata);
        const linkedThreadCount = activeSourceThreads.filter(
          (thread) => platformProviderIdFromThread(thread) === providerId,
        ).length;
        return {
          ...provider,
          linkedThreadCount,
          executorCommand: normalizeExecutionText(adapter.executor_command) ?? normalizeExecutionText(metadata.executor_command),
          executorCwd: normalizeExecutionText(adapter.executor_cwd) ?? normalizeExecutionText(metadata.executor_cwd),
          executorTimeoutSeconds:
            normalizeExecutionTimeout(adapter.executor_timeout_seconds) ??
            normalizeExecutionTimeout(metadata.executor_timeout_seconds),
        } satisfies AnyRecord;
      }),
    [providerRecords, activeSourceThreads],
  );
  const codexSeats = asArray(props.config?.codexSeats).filter((seat) => !isStaleNpcSeat(seat));
  const machineRoomExecutionWorkstations = useMemo<AnyRecord[]>(
    () =>
      sortedByUpdatedAt(activeSourceThreads).map((thread) => {
        const providerId = platformProviderIdFromThread(thread);
        const provider = providerById.get(providerId.toLowerCase()) ?? null;
        const nodeId = text(thread.computer_node_id ?? thread.computer_node, "").toLowerCase();
        const node = nodeId ? nodeById.get(nodeId) ?? null : null;
        const execution = resolveWorkstationExecutionSettings(thread, provider, node);
        const tokenState = resolveWorkstationAdapterTokenState(thread);
        const activity = buildWorkstationActivitySummary(thread, props.collaborationMessages);
        return {
          thread,
          provider,
          node,
          providerId,
          providerLabel: platformProviderLabelFromThread(thread),
          nodeLabel: displayNodeLabel(node, thread),
          ...tokenState,
          ...execution,
          ...activity,
        } satisfies AnyRecord;
      }),
    [activeSourceThreads, providerById, nodeById, props.collaborationMessages],
  );
  const seatBackedMachineRoomWorkstations = useMemo<AnyRecord[]>(
    () => {
      const activeThreadKeys = new Set(
        activeSourceThreads.flatMap((thread) => threadRouteKeys(thread).map((key) => key.toLowerCase())),
      );
      return sortedByUpdatedAt(
        codexSeats.filter((seat) => {
          const seatTargetId = text(seat.id ?? seat.workstation_id ?? seat.config_id, "");
          if (!seatTargetId) return false;
          const seatKeys = seatRouteKeys(seat).map((key) => key.toLowerCase());
          if (seatKeys.some((key) => activeThreadKeys.has(key))) return false;
          const activity = buildWorkstationActivitySummary(seat, props.collaborationMessages);
          const tokenState = resolveWorkstationAdapterTokenState(seat);
          const providerId = platformProviderIdFromThread(seat);
          const provider = providerById.get(providerId.toLowerCase()) ?? null;
          const nodeId = text(seat.computer_node_id ?? seat.computer_node, "").toLowerCase();
          const node = nodeId ? nodeById.get(nodeId) ?? null : null;
          const execution = resolveWorkstationExecutionSettings(seat, provider, node);
          return Boolean(
            activity.latestSignalAt ||
              activity.latestCommandAt ||
              activity.latestAckAt ||
              activity.latestFinalReplyAt ||
              tokenState.tokenAvailable ||
              execution.hasProviderTemplate ||
              execution.hasWorkstationOverride,
          );
        }),
      );
    },
    [activeSourceThreads, codexSeats, providerById, nodeById, props.collaborationMessages],
  );
  const machineRoomVisibleWorkstations = useMemo(
    () =>
      sortedByUpdatedAt(
        uniqueStrings([
          ...activeSourceThreads.map((thread) => text(thread.id ?? thread.workstation_id ?? thread.config_id, "")),
          ...seatBackedMachineRoomWorkstations.map((seat) => text(seat.id ?? seat.workstation_id ?? seat.config_id, "")),
        ])
          .map((key) => {
            const lowerKey = key.toLowerCase();
            return (
              activeSourceThreads.find(
                (thread) => text(thread.id ?? thread.workstation_id ?? thread.config_id, "").toLowerCase() === lowerKey,
              ) ??
              seatBackedMachineRoomWorkstations.find(
                (seat) => text(seat.id ?? seat.workstation_id ?? seat.config_id, "").toLowerCase() === lowerKey,
              ) ??
              null
            );
          })
          .filter((item): item is AnyRecord => Boolean(item)),
      ),
    [activeSourceThreads, seatBackedMachineRoomWorkstations],
  );
  const seatBackedMachineRoomExecutionWorkstations = useMemo<AnyRecord[]>(
    () =>
      machineRoomVisibleWorkstations
        .filter((workstation) => isNpcSeatWorkstation(workstation))
        .map((thread) => {
          const providerId = platformProviderIdFromThread(thread);
          const provider = providerById.get(providerId.toLowerCase()) ?? null;
          const nodeId = text(thread.computer_node_id ?? thread.computer_node, "").toLowerCase();
          const node = nodeId ? nodeById.get(nodeId) ?? null : null;
          const execution = resolveWorkstationExecutionSettings(thread, provider, node);
          const tokenState = resolveWorkstationAdapterTokenState(thread);
          const activity = buildWorkstationActivitySummary(thread, props.collaborationMessages);
          return {
            thread,
            provider,
            node,
            providerId,
            providerLabel: platformProviderLabelFromThread(thread),
            nodeLabel: displayNodeLabel(node, thread),
            ...tokenState,
            ...execution,
            ...activity,
          } satisfies AnyRecord;
        }),
    [machineRoomVisibleWorkstations, providerById, nodeById, props.collaborationMessages],
  );
  const machineRoomExecutionByWorkstationId = useMemo(
    () =>
      new Map(
        [...machineRoomExecutionWorkstations, ...seatBackedMachineRoomExecutionWorkstations]
          .map((item) => [text(item.thread.id ?? item.thread.workstation_id, ""), item] as const)
          .filter(([threadId]) => Boolean(threadId)),
      ),
    [machineRoomExecutionWorkstations, seatBackedMachineRoomExecutionWorkstations],
  );
  const skillLibrary = asArray(props.config?.skillLibrary);
  const collaborationConfig =
    props.project?.collaboration_config && typeof props.project.collaboration_config === "object"
      ? (props.project.collaboration_config as AnyRecord)
      : {};
  const developmentWorkshopStations = useMemo(
    () => normalizeDevelopmentWorkshopStations(collaborationConfig.development_workshop_stations),
    [collaborationConfig.development_workshop_stations],
  );
  const baselineSkills = skillLibrary.filter((item) => isBaselineSkill(item));
  const roleSkills = skillLibrary.filter((item) => !isBaselineSkill(item));
  const projectId = text(props.project?.id, "");
  const adapterTargetIdSet = useMemo(
    () =>
      new Set(
        asArray(props.config?.adapterTargetIds)
          .map((item) => text(item, "").toLowerCase())
          .filter(Boolean),
      ),
    [props.config?.adapterTargetIds],
  );
  function buildCurrentProjectEntryPath(modeId: string) {
    const normalizedModeId = normalizeModeEntryId(modeId);
    if (projectId) return buildProjectModeEntryPath(projectId, normalizedModeId);
    return normalizedModeId === "2d-dev"
      ? projectEntryShellPath
      : `${projectEntryShellPath}?mode=${encodeURIComponent(normalizedModeId)}`;
  }
  function buildCurrentProjectBoardPath(modeId: string) {
    const normalizedModeId = normalizeModeEntryId(modeId);
    return buildProjectModeChoicePath(projectId || undefined, normalizedModeId);
  }
  const projectPath = buildCurrentProjectEntryPath("2d-dev");
  const projectRouteModeId = normalizeModeEntryId(props.initialModeId);
  const projectEntryPath = buildCurrentProjectEntryPath(projectRouteModeId);
  const modeChoicePath = buildCurrentProjectBoardPath("2d-dev");
  const modeBoardPaths = buildProjectFutureModeChoicePaths(projectId || undefined);
  const modeShellPaths = buildProjectFutureModeShellPaths(projectId || undefined);
  const modeDefinitionsById = useMemo(
    () =>
      new Map(
        buildProjectModeDefinitions(projectId || undefined).map((mode) => [mode.id, mode] as const),
      ),
    [projectId],
  );
  const allThreadCandidates = useMemo(() => {
    const threadMap = new Map<string, AnyRecord>();
    [...activeSourceThreads, ...sourceThreads].forEach((thread) => {
      const canonicalKey = text(thread.id ?? thread.workstation_id ?? thread.name, "");
      if (!canonicalKey) return;
      const lowerKey = canonicalKey.toLowerCase();
      if (!threadMap.has(lowerKey)) {
        threadMap.set(lowerKey, thread);
      }
    });
    return sortedByUpdatedAt(Array.from(threadMap.values()));
  }, [activeSourceThreads, sourceThreads]);
  const exchangeTargetWorkstations = useMemo(() => {
    const workstationMap = new Map<string, AnyRecord>();
    [...machineRoomVisibleWorkstations, ...allThreadCandidates, ...asArray(props.config?.workstations), ...codexSeats].forEach((workstation) => {
      const canonicalKey = text(
        workstation.source_workstation_id ??
          workstation.metadata?.source_workstation_id ??
          workstation.id ??
          workstation.workstation_id ??
          workstation.config_id ??
          workstation.row_id,
        "",
      ).toLowerCase();
      if (!canonicalKey || workstationMap.has(canonicalKey)) return;
      workstationMap.set(canonicalKey, workstation);
    });
    return Array.from(workstationMap.values());
  }, [allThreadCandidates, codexSeats, machineRoomVisibleWorkstations, props.config?.workstations]);
  const liveClaudeThreadCandidates = useMemo(
    () => allThreadCandidates.filter((thread) => platformProviderIdFromThread(thread) === "claude"),
    [allThreadCandidates],
  );
  const seatBySourceThreadId = useMemo(() => {
    const seatMap = new Map<string, AnyRecord>();
    codexSeats.forEach((seat) => {
      threadRouteKeys(seat).forEach((key) => {
        if (!key) return;
        seatMap.set(key, seat);
        seatMap.set(key.toLowerCase(), seat);
      });
    });
    return seatMap;
  }, [codexSeats]);
  const initialBindThreadId = text(props.initialBindThreadId, "");
  const initialBindThread =
    (activeSourceThreads.find((thread) =>
      threadRouteKeys(thread).some((candidate) => candidate.toLowerCase() === initialBindThreadId.toLowerCase()),
    ) ??
      sourceThreads.find((thread) =>
        threadRouteKeys(thread).some((candidate) => candidate.toLowerCase() === initialBindThreadId.toLowerCase()),
      ) ??
      null);
  const initialBindNodeId =
    text(props.initialBindNodeId, "") ||
    text(initialBindThread?.computer_node_id ?? initialBindThread?.computer_node, "");
  const initialNpcName = text(props.initialNpcName, "") || (initialBindThread ? guessNpcName(initialBindThread, codexSeats.length) : "");
  const initialNpcResponsibility =
    text(props.initialNpcResponsibility, "") ||
    (initialBindThread ? guessNpcResponsibility(initialBindThread) : "");
  function buildNpcCreateHref(thread: AnyRecord, fallbackIndex: number) {
    return buildProjectSurfacePath(projectEntryPath, {
      panel: "team",
      tab: "npc-create",
      bind_thread: text(thread.id ?? thread.workstation_id, ""),
      bind_node: text(thread.computer_node_id ?? thread.computer_node, ""),
      npc_name: guessNpcName(thread, fallbackIndex),
      npc_role: guessNpcResponsibility(thread),
    });
  }
  const reloginPath = `/login?returnTo=${encodeURIComponent(projectEntryPath)}`;
  const hasProtectedDataGap = Boolean(props.collaborationAuthBlocked);
  const display = buildDisplayResolver(props.config, asArray(props.members));
  const requirementMessageMap = buildRequirementMessageMap(props.collaborationMessages);
  const finalReplyFeed = [
    ...buildFinalReplyFeed(props.requirements, requirementMessageMap, display),
    ...buildStandaloneFinalReplyFeed(props.collaborationMessages, display),
  ]
    .sort((left, right) => right.finalReplyAt - left.finalReplyAt)
    .slice(0, 8);
  const codexInboxFullFeed = buildCodexInboxFeed(asArray(props.codexInbox), display);
  const codexInboxFeed = codexInboxFullFeed.slice(0, 6);
  const cooperationProofFeed = buildCooperationProofFeed(
    props.requirements,
    requirementMessageMap,
    codexInboxFullFeed,
    display,
    props.config,
    hasProtectedDataGap,
  );
  const featuredQueuedCodexCommandForSummary =
    pickFeaturedQueuedInboxItem(codexInboxFullFeed.filter((item) => isPrimaryCoordinatorInboxItem(item))) ??
    pickFeaturedQueuedInboxItem(codexInboxFullFeed);
  const featuredCooperationProof =
    cooperationProofFeed.find((item) => isPrimaryCoordinatorProofItem(item)) ?? cooperationProofFeed[0] ?? null;
  const featuredCooperationProofId = featuredCooperationProof?.id ?? null;
  const cooperationProofSummary = buildCooperationProofSummary(cooperationProofFeed, hasProtectedDataGap);
  const realThreadCount = sourceThreads.length;
  const projectName = text(props.project?.name, `项目 ${projectId}`);
  const projectDescription = text(
    props.project?.description,
    "当前先以可玩的农场地图为主，平台信息保持轻量，不压住游戏视野。",
  );
  const gitExecution =
    props.gitExecution && typeof props.gitExecution === "object" ? (props.gitExecution as AnyRecord) : null;
  const collaborationPreview =
    props.collaborationPreview && typeof props.collaborationPreview === "object"
      ? (props.collaborationPreview as AnyRecord)
      : null;
  const gitExecutionSummary =
    gitExecution?.summary && typeof gitExecution.summary === "object" ? (gitExecution.summary as AnyRecord) : {};
  const gitExecutionRepository =
    gitExecution?.repository && typeof gitExecution.repository === "object" ? (gitExecution.repository as AnyRecord) : {};
  const gitExecutionActions = asArray(gitExecution?.actions);
  const rollbackExecutionAction =
    gitExecutionActions.find((item) => text(item.action, "").toLowerCase() === "rollback") ?? null;
  const syncExecutionAction =
    gitExecutionActions.find((item) => text(item.action, "").toLowerCase() === "sync_github") ?? null;
  const latestGitActivity = sortedByUpdatedAt(asArray(props.gitActivity)).slice(0, 6);
  const gitPreflightFullFeed = buildGitPreflightFeed(props.collaborationMessages, nodes, display);
  const gitPreflightFeed = gitPreflightFullFeed.slice(0, 8);
  const gitPreflightSummary = summarizeGitPreflightFeed(gitPreflightFullFeed);
  const gitPreflightAttention = buildGitPreflightAttention(gitPreflightFullFeed);
  const gitRollbackPresets = useMemo(
    () =>
      uniqueStrings([
        text(props.project?.developBranch, ""),
        text(props.project?.defaultBranch, ""),
        "HEAD~1",
        ...sortedByUpdatedAt(props.tasks)
          .map((task) => text(task.branch, ""))
          .filter(Boolean)
          .slice(0, 4),
      ]),
    [props.project?.developBranch, props.project?.defaultBranch, props.tasks],
  );
  const gitRollbackVersionIndex = useMemo(() => {
    type RollbackVersionOption = {
      ref: string;
      label: string;
      source: string;
      detail: string;
      tone: "default" | "branch" | "task" | "activity";
    };
    const options: RollbackVersionOption[] = [];
    const remember = (option: RollbackVersionOption) => {
      const ref = text(option.ref, "");
      if (!ref || options.some((item) => item.ref === ref)) return;
      options.push({ ...option, ref });
    };
    const developBranch = text(props.project?.developBranch, "");
    const defaultBranch = text(props.project?.defaultBranch, "");
    if (developBranch) {
      remember({
        ref: developBranch,
        label: "开发分支",
        source: "项目配置",
        detail: "适合回到当前协作主线，让所有 NPC 重新对齐。",
        tone: "branch",
      });
    }
    if (defaultBranch && defaultBranch !== developBranch) {
      remember({
        ref: defaultBranch,
        label: "默认分支",
        source: "项目配置",
        detail: "适合回到稳定主线，登记后需要通知 Boss 和工位长。",
        tone: "branch",
      });
    }
    remember({
      ref: "HEAD~1",
      label: "上一个提交",
      source: "安全快捷项",
      detail: "只作为预演目标，不会直接执行 git reset。",
      tone: "default",
    });
    sortedByUpdatedAt(props.tasks)
      .map((task) => ({
        branch: text(task.branch, ""),
        title: text(task.title ?? task.name, "任务分支"),
        status: text(task.status, "unknown"),
        updatedAt: task.updated_at ?? task.updatedAt ?? task.created_at,
      }))
      .filter((item) => item.branch)
      .slice(0, 8)
      .forEach((item) => {
        remember({
          ref: item.branch,
          label: item.title,
          source: "任务分支",
          detail: `${item.status}${item.updatedAt ? ` / ${formatStamp(item.updatedAt)}` : ""}`,
          tone: "task",
        });
      });
    sortedByUpdatedAt(asArray(props.gitActivity))
      .map((item) => ({
        targetRef: text(item.target_ref ?? item.targetRef, ""),
        title: text(item.title ?? item.action, "Git 动态"),
        body: text(item.body ?? item.summary ?? item.description, ""),
      }))
      .filter((item) => item.targetRef)
      .slice(0, 6)
      .forEach((item) => {
        remember({
          ref: item.targetRef,
          label: item.title,
          source: "历史登记",
          detail: shortText(item.body, "最近一次 Git 活动提到的目标引用", 76),
          tone: "activity",
        });
      });
    return options.slice(0, 16);
  }, [props.gitActivity, props.project?.defaultBranch, props.project?.developBranch, props.tasks]);
  const gitSyncProviderOptions = useMemo(() => {
    const options: { id: string; label: string; target: string | null }[] = [];
    const githubUrl = text(gitExecutionRepository.github_url, "");
    const localGitUrl = text(gitExecutionRepository.local_git_url, "");
    if (githubUrl) {
      options.push({ id: "github", label: "GitHub 仓库", target: githubUrl });
    }
    if (localGitUrl) {
      options.push({ id: "local", label: "本地仓库镜像", target: localGitUrl });
    }
    if (!options.length) {
      options.push({ id: "github", label: "GitHub 仓库", target: null });
    }
    return options;
  }, [gitExecutionRepository.github_url, gitExecutionRepository.local_git_url]);
  const pairingNodeId = text(searchParams?.get("pairing_node") ?? props.pairingNodeId, "");
  const pairingToken = text(searchParams?.get("pairing_token") ?? props.pairingToken, "");
  const workstationTokenId = text(
    searchParams?.get("adapter_workstation") ?? props.workstationTokenId,
    "",
  );
  const workstationToken = text(searchParams?.get("adapter_token") ?? props.workstationToken, "");
  const initialView = normalizePanelView(
    props.initialPanelView ?? (workstationToken ? "machine-room" : pairingToken ? "computers" : "exchange"),
  );
  const [panelOpen, setPanelOpen] = useState(props.initialPanelOpen ?? Boolean(pairingToken || workstationToken));
  const [panelView, setPanelView] = useState<PanelView>(initialView);
  const [pendingActionLabel, setPendingActionLabel] = useState<string | null>(null);
  const [gitSyncProvider, setGitSyncProvider] = useState(gitSyncProviderOptions[0]?.id ?? "github");
  const [gitSyncNotes, setGitSyncNotes] = useState("");
  const [gitRollbackTargetRef, setGitRollbackTargetRef] = useState(
    gitRollbackPresets[0] ?? text(props.project?.developBranch ?? props.project?.defaultBranch, "develop"),
  );
  const [gitRollbackNotes, setGitRollbackNotes] = useState("");
  const [seatFocusId, setSeatFocusId] = useState(text(props.initialSeatFocusId, ""));
  const [computerFocusId, setComputerFocusId] = useState(text(props.initialComputerFocusId, "") || pairingNodeId);
  const [machineRoomFocusThreadId, setMachineRoomFocusThreadId] = useState(text(props.initialBindThreadId, ""));
  const [skillFocusId, setSkillFocusId] = useState("");
  const [developmentFocusId, setDevelopmentFocusId] = useState(developmentWorkshopStations[0]?.id ?? "");
  const [managerDrawer, setManagerDrawer] = useState<ManagerDrawerState | null>(
    props.initialManagerDrawerKind
      ? {
          kind: props.initialManagerDrawerKind,
          id: text(props.initialManagerDrawerId ?? props.initialSeatFocusId, "") || undefined,
        }
      : null,
  );
  const [skillQuery, setSkillQuery] = useState("");
  const [skillImportQuery, setSkillImportQuery] = useState("");
  const [skillImportCategoryFilter, setSkillImportCategoryFilter] = useState("all");
  const [skillImportStatusFilter, setSkillImportStatusFilter] = useState("all");
  const [skillImportRecommendedOnly, setSkillImportRecommendedOnly] = useState(false);
  const [skillImportSelection, setSkillImportSelection] = useState<string[]>([]);
  const [npcSkillQuery, setNpcSkillQuery] = useState("");
  const [npcSkillCategoryFilter, setNpcSkillCategoryFilter] = useState("all");
  const [npcSkillSourceFilter, setNpcSkillSourceFilter] = useState("all");
  const [npcCreateSkillLoadout, setNpcCreateSkillLoadout] = useState<string[]>([]);
  const [npcCreateSkillSeedKey, setNpcCreateSkillSeedKey] = useState("");
  const [npcEditSkillLoadout, setNpcEditSkillLoadout] = useState<string[]>([]);
  const [npcEditSkillSeedKey, setNpcEditSkillSeedKey] = useState("");
  const [exchangeFocusLabel, setExchangeFocusLabel] = useState("");
  const [exchangeFocusRouteKeys, setExchangeFocusRouteKeys] = useState<string[]>([]);
  const [exchangeSectionFocusId, setExchangeSectionFocusId] = useState<ExchangeSectionId>(
    normalizeExchangeSectionId(props.initialExchangeSectionId),
  );
  const [exchangeReceiptFilter, setExchangeReceiptFilter] = useState<ExchangeReceiptFilter>("all");
  const [exchangeComposerMode, setExchangeComposerMode] = useState<ExchangeComposerMode | null>(
    normalizeExchangeComposerMode(props.initialExchangeComposerMode),
  );
  const [humanPartyFocusId, setHumanPartyFocusId] = useState(text(props.initialHumanPartyFocusId, ""));
  const [skinPreviewEnabled, setSkinPreviewEnabled] = useState(false);
  const gameFrameRef = useRef<HTMLIFrameElement | null>(null);
  const selectedDevelopmentStation =
    developmentWorkshopStations.find((item) => item.id === developmentFocusId) ?? developmentWorkshopStations[0];

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setSkinPreviewEnabled(params.get("skin") === "a-agent-lab");
  }, []);

  useEffect(() => {
    setPanelOpen(props.initialPanelOpen ?? Boolean(pairingToken || workstationToken));
  }, [props.initialPanelOpen, pairingToken, workstationToken]);

  useEffect(() => {
    setPanelView(initialView);
  }, [initialView]);

  useEffect(() => {
    setExchangeSectionFocusId(normalizeExchangeSectionId(props.initialExchangeSectionId));
  }, [props.initialExchangeSectionId]);

  useEffect(() => {
    setExchangeComposerMode(normalizeExchangeComposerMode(props.initialExchangeComposerMode));
  }, [props.initialExchangeComposerMode]);

  useEffect(() => {
    if (props.initialHumanPartyFocusId === undefined) return;
    setHumanPartyFocusId(text(props.initialHumanPartyFocusId, ""));
  }, [props.initialHumanPartyFocusId]);

  useEffect(() => {
    if (props.initialComputerFocusId === undefined && !pairingNodeId) return;
    setComputerFocusId(text(props.initialComputerFocusId, "") || pairingNodeId);
  }, [props.initialComputerFocusId, pairingNodeId]);

  useEffect(() => {
    const currentUserId = text(props.currentUser?.id ?? props.currentUser?.email, "");
    if (!projectId || !currentUserId || typeof window === "undefined") return;

    let stopped = false;
    const sendPresence = () => {
      if (stopped) return;
      const path = `${window.location.pathname}${window.location.search}`;
      fetch(`/projects/${encodeURIComponent(projectId)}/presence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
        keepalive: true,
      }).catch(() => {
        // Presence is best-effort; never block the game UI on a stale heartbeat.
      });
    };

    const handleVisibility = () => {
      if (!document.hidden) sendPresence();
    };

    sendPresence();
    const timer = window.setInterval(sendPresence, 30_000);
    window.addEventListener("focus", sendPresence);
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      stopped = true;
      window.clearInterval(timer);
      window.removeEventListener("focus", sendPresence);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [projectId, props.currentUser?.email, props.currentUser?.id]);

  useEffect(() => {
    if (!developmentWorkshopStations.length) return;
    if (developmentWorkshopStations.some((item) => item.id === developmentFocusId)) return;
    setDevelopmentFocusId(developmentWorkshopStations[0]?.id ?? "");
  }, [developmentWorkshopStations, developmentFocusId]);

  useEffect(() => {
    if (gitRollbackTargetRef.trim() || !gitRollbackPresets.length) return;
    setGitRollbackTargetRef(gitRollbackPresets[0]);
  }, [gitRollbackPresets, gitRollbackTargetRef]);

  useEffect(() => {
    if (gitSyncProviderOptions.some((item) => item.id === gitSyncProvider)) return;
    setGitSyncProvider(gitSyncProviderOptions[0]?.id ?? "github");
  }, [gitSyncProviderOptions, gitSyncProvider]);

  useEffect(() => {
    if (!panelOpen || panelView !== "exchange" || !exchangeFocusRouteKeys.length || typeof document === "undefined") return;
    const timer = window.requestAnimationFrame(() => {
      const target = document.querySelector('[data-exchange-focus-active="true"]');
      if (target instanceof HTMLElement) {
        target.scrollIntoView({ block: "center", inline: "nearest" });
      }
    });
    return () => window.cancelAnimationFrame(timer);
  }, [panelOpen, panelView, exchangeFocusRouteKeys, props.collaborationMessages]);

  const hasRecentUnsettledExchangeMessage = useMemo(() => {
    const now = Date.now();
    return props.collaborationMessages.some((message) => {
      const messageType = text(message.message_type, "").toLowerCase();
      if (!["agent_command", "requirement_dispatch", "runner_command"].includes(messageType)) return false;
      const status = text(message.status, "").toLowerCase();
      if (["completed", "failed", "done", "cancelled"].includes(status)) return false;
      const rawTimestamp = text(message.updated_at ?? message.created_at, "");
      const timestamp = Date.parse(/[zZ]|[+-]\d{2}:?\d{2}$/.test(rawTimestamp) ? rawTimestamp : `${rawTimestamp}Z`);
      return Number.isFinite(timestamp) && now - timestamp < 10 * 60 * 1000;
    });
  }, [props.collaborationMessages]);

  useEffect(() => {
    if (!panelOpen || panelView !== "exchange" || !hasRecentUnsettledExchangeMessage) return;
    const timer = window.setInterval(() => {
      router.refresh();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [router, panelOpen, panelView, hasRecentUnsettledExchangeMessage]);

  const skillById = useMemo(() => {
    const next = new Map<string, AnyRecord>();
    skillLibrary.forEach((skill) => {
      const skillId = text(skill.id, "");
      if (!skillId) return;
      next.set(skillId.toLowerCase(), skill);
    });
    return next;
  }, [skillLibrary]);
  const mapSeatPayload = useMemo(
    () =>
      buildSeatMapPayload({
        seats: codexSeats,
        tasks: props.tasks,
        requirements: props.requirements,
        messageMap: requirementMessageMap,
        skillLibrary,
        knowledgeSnapshots: (props.config?.npcKnowledgeSnapshots as Record<string, AnyRecord>) ?? {},
        autonomyStatuses: (props.config?.codexAutonomyStatuses as Record<string, AnyRecord>) ?? {},
        hasProtectedDataGap,
        resolveDisplay: display,
        projectRepoDefaults: {
          githubUrl: text(props.project?.githubUrl, "") || null,
          branch: text(props.project?.developBranch ?? props.project?.defaultBranch, "") || null,
        },
      }),
    [
      codexSeats,
      props.tasks,
      props.requirements,
      requirementMessageMap,
      skillLibrary,
      props.config?.npcKnowledgeSnapshots,
      props.config?.codexAutonomyStatuses,
      hasProtectedDataGap,
      display,
      props.project,
    ],
  );
  const primaryCoordinatorSeats = useMemo(
    () => mapSeatPayload.filter((seat) => isPrimaryCoordinatorSeat(seat)),
    [mapSeatPayload],
  );
  const stalledSeatSummary = useMemo(
    () => buildStalledSeatSummary(primaryCoordinatorSeats) ?? buildStalledSeatSummary(mapSeatPayload),
    [primaryCoordinatorSeats, mapSeatPayload],
  );
  const stalledSeatRecoveryAction = stalledSeatSummary?.topSeat ? stalledSeatRecoveryHint(stalledSeatSummary.topSeat) : "";
  const humanReviewSeats = useMemo(
    () => mapSeatPayload.filter((seat) => seatNeedsHumanReview(seat)),
    [mapSeatPayload],
  );
  const pendingHumanReviewTasks = useMemo(
    () => props.tasks.filter((task) => taskNeedsHumanReview(task)),
    [props.tasks],
  );
  const pendingHumanReviewMessages = useMemo(
    () => sortedByUpdatedAt(props.collaborationMessages.filter((message) => collaborationMessageNeedsHumanReview(message))),
    [props.collaborationMessages],
  );
  const humanReviewAlert = useMemo(() => {
    const seat = humanReviewSeats[0] ?? null;
    const task = pendingHumanReviewTasks[0] ?? null;
    const message = pendingHumanReviewMessages[0] ?? null;
    if (!seat && !task && !message) return null;
    const title =
      seat?.currentRequirement ||
      seat?.recentTasks[0]?.title ||
      safeDisplayTitle(task?.title ?? message?.title, "待人工审核事项");
    return {
      title,
      count: humanReviewSeats.length + pendingHumanReviewTasks.length + pendingHumanReviewMessages.length,
      owner:
        seat?.name ||
        display(task?.assignee_id ?? task?.owner_id ?? task?.agent_id, "") ||
        (message ? actorLabel(message, display) : "") ||
        "待确认负责人",
      state: seat?.reviewState || (message ? "协作指令待人工审核" : describeSeatReviewState(task ? [task] : [], hasProtectedDataGap)),
      detail: seat
        ? `${seat.name} 正在等待人工审核：${seat.reviewState}。不要继续自动推进，先给出通过/驳回/补充要求。`
        : task
          ? `${safeDisplayTitle(task.title, "这条任务")} 需要人工审核。先处理审核，再允许 AI 继续推进。`
          : `${safeDisplayTitle(message?.title, "这条协作指令")} 已被治理闸口挡住，没有派给远端 AI。请先确认只读/仿真/真实执行边界。`,
    };
  }, [humanReviewSeats, pendingHumanReviewTasks, pendingHumanReviewMessages, hasProtectedDataGap, display]);
  const starterSeat = useMemo(
    () => pickStarterSeat(primaryCoordinatorSeats) ?? pickStarterSeat(mapSeatPayload),
    [primaryCoordinatorSeats, mapSeatPayload],
  );
  const starterSeatLabel = starterSeat?.name || "当前 NPC";
  const starterSeatProgressWarning = starterSeat?.progressWarningLabel ?? null;
  const runnerQueueBlocker = queuedCollaborationCommandCount > 0 && watchReadyNodes.length === 0;
  const runnerQueueAttention = queuedCollaborationCommandCount > 0 && (runnerQueueBlocker || watchBlockedNodes.length > 0);
  const runnerQueueAttentionTitle = runnerQueueBlocker
    ? `${queuedCollaborationCommandCount} 条平台指令排队，但 0 台电脑在常驻接单`
    : `${queuedCollaborationCommandCount} 条平台指令仍在排队，${watchBlockedNodes.length} 台电脑未稳定接单`;
  const runnerQueueAttentionBody = runnerQueueBlocker
    ? "先去电脑接入管理恢复自动化心跳，再继续派工；否则新指令只会继续堆在队列里。"
    : `已有 ${watchReadyNodes.length} 台电脑可接单，但仍有 ${watchBlockedNodes.length} 台电脑心跳过期。继续派工前，先确认目标线程在哪台电脑上。`;
  const recommendedAction = hasProtectedDataGap
    ? "重新登录，恢复 requirement、回执和最终回复读取，再继续判断平台下一步。"
    : humanReviewAlert
      ? `先处理人工审核：${humanReviewAlert.detail}`
      : runnerQueueBlocker
      ? `先恢复电脑常驻接单：当前 ${queuedCollaborationCommandCount} 条平台指令排队，但 0 台电脑在持续心跳。进入电脑接入管理，复制“自动化心跳 / 持续接单”命令。`
      : runnerQueueAttention
      ? `继续恢复剩余接单电脑：当前 ${queuedCollaborationCommandCount} 条平台指令仍排队，${watchBlockedNodes.length} 台电脑心跳过期。进入电脑接入管理，优先恢复目标线程所在电脑。`
      : gitPreflightAttention?.summary
      ? gitPreflightAttention.summary
      : stalledSeatSummary?.detail
      ? `优先处理 ${stalledSeatSummary.detail}。${stalledSeatRecoveryAction || "先把这些停滞链路重新推起来，再继续发新的 requirement。"}`
      : starterSeat?.minimalAck && !starterSeat?.finalReply && starterSeatProgressWarning === "最小回执偏晚"
        ? `继续盯住 ${starterSeatLabel} 当前 requirement 的结果收口。它已经重新对齐 live 线程，但最小回执偏晚，暂时不该再误判成彻底卡死。`
      : starterSeat?.minimalAck && !starterSeat?.finalReply && starterSeatProgressWarning === "进度信号待归一"
        ? `继续盯住 ${starterSeatLabel} 当前 requirement 的结果收口，同时把 live API 的旧进度信号语义归一回真正的 progress_ack。`
      : buildRecommendedAction(
          props.requirements,
          requirementMessageMap,
          props.relayTimeline,
          props.tasks,
          finalReplyFeed,
          display,
          featuredQueuedCodexCommandForSummary,
          countQueuedInboxItemsForFocus(codexInboxFullFeed, featuredQueuedCodexCommandForSummary),
        );
  const currentOwner = buildCurrentOwner(props.requirements, requirementMessageMap, props.tasks, props.config, display);
  const visibleOwner = hasProtectedDataGap ? "当前登录态未授权" : currentOwner;
  const relayFeed = buildRelayFeed(props.relayTimeline, props.tasks, display);
  const maintenanceBoard = buildMaintenanceBoard(props.requirements);
  const processVisibility = hasProtectedDataGap
    ? {
        foldSummary: "协作脉搏：受保护协作数据未授权",
        title: "受保护协作数据未授权",
        body: "当前项目页入口壳仍承接 live 的 2D 开发者模式入口，但当前登录态没有拿到 requirement、回执和最终回复；先重新登录，再判断平台是否在真实推进。",
        meta: `当前项目页入口壳仍可见 / 活跃线程 ${activeSourceThreads.length} 条 / NPC 席位 ${codexSeats.length} 个`,
      }
    : buildProcessVisibility(
        relayFeed,
        finalReplyFeed,
        maintenanceBoard,
        activeSourceThreads.length,
        visibleOwner,
        codexInboxFullFeed,
        primaryCoordinatorSeats.length ? primaryCoordinatorSeats : mapSeatPayload,
      );
  const embeddedMapBaseHref = buildMapHref(projectId, [], props.initialSeatFocusId, { embed: true });
  const embeddedMapSrc = `${embeddedMapBaseHref}${embeddedMapBaseHref.includes("?") ? "&" : "?"}v=platform-farm-overlay${
    skinPreviewEnabled ? "&stylePack=a-agent-lab" : ""
  }`;
  const mapCollaboratorPayload = useMemo(
    () => buildCollaboratorMapPayload(asArray(props.members), props.currentUser as AnyRecord | null | undefined),
    [props.members, props.currentUser],
  );
  const sharedTaskSnapshot = useMemo(() => {
    const activeTasks = sortedByUpdatedAt(props.tasks).filter(
      (task) => !["done", "completed", "archived", "cancelled", "canceled"].includes(text(task.status, "").toLowerCase()),
    );
    const topTask = activeTasks[0] ?? null;
    return {
      count: activeTasks.length,
      leadTitle: topTask ? safeDisplayTitle(topTask.title, "未命名任务") : "暂无共享任务",
    };
  }, [props.tasks]);
  const humanPartyHud = useMemo(
    () =>
      buildHumanPartyHudEntries(
        mapCollaboratorPayload.collaborators,
        props.collaborationMessages,
        sharedTaskSnapshot.count,
        projectId,
        nodes,
        activeSourceThreads,
      ),
    [mapCollaboratorPayload, props.collaborationMessages, sharedTaskSnapshot.count, projectId, nodes, activeSourceThreads],
  );
  const connectedHumanPartyCount = useMemo(
    () => humanPartyHud.filter((player) => player.computerCount > 0).length,
    [humanPartyHud],
  );
  const threadedHumanPartyCount = useMemo(
    () => humanPartyHud.filter((player) => player.threadCount > 0).length,
    [humanPartyHud],
  );
  const projectPresentHumanPartyCount = useMemo(
    () => humanPartyHud.filter((player) => player.projectPresenceState === "online").length,
    [humanPartyHud],
  );
  const loggedInHumanPartyCount = useMemo(
    () => humanPartyHud.filter((player) => player.accountPresenceState === "online").length,
    [humanPartyHud],
  );
  const currentHumanPartyPlayer = useMemo(
    () => humanPartyHud.find((player) => player.isCurrentPlayer) ?? humanPartyHud[0] ?? null,
    [humanPartyHud],
  );
  const computerFleetGroups = useMemo(
    () => buildComputerFleetGroups(humanPartyHud, nodes, activeSourceThreads),
    [humanPartyHud, nodes, activeSourceThreads],
  );
  const selectedHumanPartyPlayer = useMemo(() => {
    const focus = text(humanPartyFocusId, "").toLowerCase();
    if (!focus) return currentHumanPartyPlayer;
    return humanPartyHud.find((player) => player.id.toLowerCase() === focus) ?? currentHumanPartyPlayer;
  }, [humanPartyFocusId, humanPartyHud, currentHumanPartyPlayer]);
  const selectedHumanPartyFleetGroup = useMemo(
    () =>
      selectedHumanPartyPlayer
        ? computerFleetGroups.find((group) => group.id.toLowerCase() === selectedHumanPartyPlayer.id.toLowerCase()) ?? null
        : null,
    [computerFleetGroups, selectedHumanPartyPlayer],
  );
  useEffect(() => {
    if (!humanPartyHud.length) {
      if (humanPartyFocusId) setHumanPartyFocusId("");
      return;
    }
    if (humanPartyHud.some((player) => player.id.toLowerCase() === text(humanPartyFocusId, "").toLowerCase())) return;
    setHumanPartyFocusId(currentHumanPartyPlayer?.id ?? humanPartyHud[0]?.id ?? "");
  }, [currentHumanPartyPlayer, humanPartyFocusId, humanPartyHud]);
  const mapCollaboratorPayloadRaw = useMemo(
    () =>
      mapCollaboratorPayload.collaborators.length
        ? JSON.stringify({
            projectId,
            currentPlayerId: mapCollaboratorPayload.currentPlayerId,
            collaborators: mapCollaboratorPayload.collaborators,
          })
        : "",
    [projectId, mapCollaboratorPayload],
  );
  const mapSeatPayloadRaw = useMemo(
    () =>
      mapSeatPayload.length
        ? JSON.stringify({
            projectId,
            seats: mapSeatPayload,
          })
        : "",
    [projectId, mapSeatPayload],
  );
  const seatPayloadMap = useMemo(
    () =>
      new Map(
        mapSeatPayload.flatMap((seat) =>
          uniqueStrings([seat.id, seat.sourceThreadId, seat.name]).map((key) => [key, seat] as const),
        ),
      ),
    [mapSeatPayload],
  );
  const focusedSeatEntry = useMemo(() => {
    for (const seat of codexSeats) {
      const seatView = resolveSeatViewForRecord(seat, seatPayloadMap);
      if (seatMatchesFocus(seat, seatView, seatFocusId)) {
        return { seat, seatView };
      }
    }
    return null;
  }, [codexSeats, seatPayloadMap, seatFocusId]);
  const editorSeat = focusedSeatEntry?.seat ?? null;
  const editorSeatView = focusedSeatEntry?.seatView ?? null;
  const editorSeatId = editorSeat ? preferredSeatRouteId(editorSeat, editorSeatView) : "";
  const editorSeatSkills = editorSeat ? resolveSeatSkillLoadout(editorSeat, skillLibrary) : null;
  const editorThreadId =
    text(editorSeat?.source_workstation_id ?? editorSeat?.metadata?.source_workstation_id, "") ||
    text(initialBindThread?.id ?? initialBindThread?.workstation_id, "");
  const editorBoundThread = useMemo(
    () =>
      allThreadCandidates.find((thread) =>
        threadRouteKeys(thread).some((candidate) => candidate.toLowerCase() === editorThreadId.toLowerCase()),
      ) ?? null,
    [allThreadCandidates, editorThreadId],
  );
  const editorBoundThreadProviderId = editorBoundThread ? platformProviderIdFromThread(editorBoundThread) : "";
  const editorBoundThreadProviderLabel = editorBoundThread ? platformProviderLabelFromThread(editorBoundThread) : "";
  const editorThreadBootstrapBlocker = editorBoundThread ? threadBootstrapBlocker(editorBoundThread) : "";
  const editorSupportsNpcCreation = editorBoundThread ? !editorThreadBootstrapBlocker : true;
  const editorSupportsLocalBridge = editorBoundThread ? supportsLocalCodexAutonomyBridge(editorBoundThreadProviderId) : false;
  const editorName = editorSeat ? text(editorSeat.name, "") : initialNpcName;
  const editorResponsibility = editorSeat
    ? text(editorSeat.responsibility ?? editorSeat.metadata?.responsibility, "")
    : initialNpcResponsibility;
  const editorNodeId =
    text(editorSeat?.computer_node_id ?? editorSeat?.metadata?.computer_node_id, "") ||
    text(editorBoundThread?.computer_node_id ?? editorBoundThread?.computer_node, "") ||
    initialBindNodeId;
  const editorModel =
    text(editorSeat?.model ?? editorSeat?.metadata?.model, "") ||
    text(editorBoundThread?.model ?? editorBoundThread?.metadata?.model, "") ||
    "gpt-5.4";
  const editorKnowledgeProfile = useMemo(
    () =>
      resolveNpcKnowledgeProfile(
        editorSeat ?? {
          id: editorSeatId || null,
          name: editorName || "NPC",
          responsibility: editorResponsibility || null,
        },
        {
          fallbackName: editorName || "NPC",
          fallbackResponsibility: editorResponsibility || "待分配职责",
        },
      ),
    [editorSeat, editorSeatId, editorName, editorResponsibility],
  );
  const editorKnowledgeTags = editorKnowledgeProfile.tags.filter((tag) => tag !== "npc" && tag !== "continuity").join(", ");
  const editorProjectGithubUrl = text(props.project?.githubUrl, "");
  const editorProjectBranch = text(props.project?.developBranch ?? props.project?.defaultBranch, "");
  const editorProtocol = useMemo(
    () =>
      resolvePlatformCollabProtocol(editorSeat?.metadata?.collab_protocol, {
        providerId: editorBoundThreadProviderId || editorSeatView?.providerId || undefined,
        roleText: editorResponsibility,
        threadText: text(editorBoundThread?.name ?? editorBoundThread?.label, ""),
        repoContext: {
          repository_url: editorProjectGithubUrl || null,
          branch: editorProjectBranch || null,
          relative_root: ".",
        },
      }),
    [
      editorSeat,
      editorBoundThreadProviderId,
      editorSeatView?.providerId,
      editorResponsibility,
      editorBoundThread,
      editorProjectGithubUrl,
      editorProjectBranch,
    ],
  );
  const editorCapabilityText = editorProtocol.required_capabilities.join(", ");
  const editorReferencePaths = useMemo(
    () =>
      buildPlatformRepoReferencePaths({
        referencePaths: editorProtocol.reference_paths,
        repositoryUrl: (editorProtocol.repo_context?.repository_url ?? editorProjectGithubUrl) || null,
        branch: (editorProtocol.repo_context?.branch ?? editorProjectBranch) || null,
        handoffPath: editorKnowledgeProfile.handoff_path,
      }),
    [editorProtocol, editorProjectGithubUrl, editorProjectBranch, editorKnowledgeProfile.handoff_path],
  );
  const editorReferenceText = editorReferencePaths.join(", ");
  const editorRepoSummary = platformRepoContextSummary(editorProtocol.repo_context);
  const editorRepoNote = platformRepoContextNote(editorProtocol.repo_context);
  const suggestedRoleSkillIds = useMemo(() => {
    const recommended = recommendRoleSkillIds({
      roleText: editorResponsibility,
      threadText: text(editorBoundThread?.name ?? editorBoundThread?.label ?? editorThreadId, ""),
      skillLibrary,
    });
    if (!editorSeatSkills) return recommended;
    return uniqueStrings([...editorSeatSkills.additionalSkillIds, ...recommended]);
  }, [editorResponsibility, editorBoundThread, editorThreadId, editorSeatSkills, skillLibrary]);
  const orderedRoleSkills = useMemo(() => {
    const recommended = new Set(suggestedRoleSkillIds.map((item) => item.toLowerCase()));
    return roleSkills.slice().sort((left, right) => {
      const leftId = text(left.id, "").toLowerCase();
      const rightId = text(right.id, "").toLowerCase();
      const leftRecommended = Number(recommended.has(leftId));
      const rightRecommended = Number(recommended.has(rightId));
      return rightRecommended - leftRecommended || leftId.localeCompare(rightId);
    });
  }, [roleSkills, suggestedRoleSkillIds]);
  const createDrawerDevelopmentStation =
    managerDrawer?.kind === "npc-create"
      ? developmentWorkshopStations.find((item) => item.id === managerDrawer?.id) ??
        (panelView === "development-workshop" ? selectedDevelopmentStation : undefined)
      : panelView === "development-workshop"
        ? selectedDevelopmentStation
        : undefined;
  const createDrawerDefaultThread = allThreadCandidates[0] ?? null;
  const createDrawerSuggestedRoleSkillIds = useMemo(
    () =>
      recommendRoleSkillIds({
        roleText: defaultNpcResponsibilityForDevelopmentStation(createDrawerDevelopmentStation),
        threadText: text(createDrawerDefaultThread?.name ?? createDrawerDefaultThread?.label, ""),
        skillLibrary,
      }),
    [createDrawerDevelopmentStation, createDrawerDefaultThread, skillLibrary],
  );
  const createDrawerOrderedRoleSkills = useMemo(() => {
    const recommended = new Set(createDrawerSuggestedRoleSkillIds.map((item) => item.toLowerCase()));
    return roleSkills.slice().sort((left, right) => {
      const leftId = text(left.id, "").toLowerCase();
      const rightId = text(right.id, "").toLowerCase();
      const leftRecommended = Number(recommended.has(leftId));
      const rightRecommended = Number(recommended.has(rightId));
      return rightRecommended - leftRecommended || leftId.localeCompare(rightId);
    });
  }, [roleSkills, createDrawerSuggestedRoleSkillIds]);
  const editorEffectiveSkillIds = useMemo(
    () => mergePlatformSkillLoadout(suggestedRoleSkillIds),
    [suggestedRoleSkillIds],
  );
  const editorEffectiveSkills = useMemo(
    () =>
      editorEffectiveSkillIds.map((skillId) => ({
        id: skillId,
        label: text(skillById.get(skillId.toLowerCase())?.label, skillId),
        note: text(skillById.get(skillId.toLowerCase())?.note, ""),
      })),
    [editorEffectiveSkillIds, skillById],
  );
  useEffect(() => {
    if (managerDrawer?.kind !== "npc-create") return;
    const nextKey = `${text(managerDrawer?.id, "general")}::${createDrawerSuggestedRoleSkillIds.join("|")}`;
    if (npcCreateSkillSeedKey === nextKey) return;
    setNpcCreateSkillLoadout(createDrawerSuggestedRoleSkillIds);
    setNpcCreateSkillSeedKey(nextKey);
  }, [managerDrawer, createDrawerSuggestedRoleSkillIds, npcCreateSkillSeedKey]);
  useEffect(() => {
    if (managerDrawer?.kind !== "npc-skills") return;
    const nextIds = editorSeatSkills?.additionalSkillIds ?? [];
    const nextKey = `${text(managerDrawer?.id, "")}::${nextIds.join("|")}`;
    if (npcEditSkillSeedKey === nextKey) return;
    setNpcEditSkillLoadout(nextIds);
    setNpcEditSkillSeedKey(nextKey);
  }, [managerDrawer, editorSeatSkills, npcEditSkillSeedKey]);
  useEffect(() => {
    if (managerDrawer?.kind !== "npc-create" && managerDrawer?.kind !== "npc-skills") return;
    setNpcSkillQuery("");
    setNpcSkillCategoryFilter("all");
    setNpcSkillSourceFilter("all");
  }, [managerDrawer?.kind, managerDrawer?.id]);
  useEffect(() => {
    if (managerDrawer?.kind !== "skill-import") return;
    setSkillImportQuery("");
    setSkillImportCategoryFilter("all");
    setSkillImportStatusFilter("all");
    setSkillImportRecommendedOnly(false);
    setSkillImportSelection([]);
  }, [managerDrawer?.kind, managerDrawer?.id]);
  const missingKnowledgeSeatCount = useMemo(
    () =>
      codexSeats.filter((seat) => {
        const metadata =
          seat?.metadata && typeof seat.metadata === "object"
            ? (seat.metadata as AnyRecord)
            : {};
        return !text(metadata.npc_identity_key, "") || !(metadata.npc_knowledge && typeof metadata.npc_knowledge === "object");
      }).length,
    [codexSeats],
  );
  const editorFormKey = editorSeatId || editorThreadId || "npc-create";
  const defaultNpcCreateSubview: NpcCreateSubview =
    props.initialNpcCreateSubview ??
    (editorSeatId || editorThreadId
      ? "editor"
      : allThreadCandidates.length
        ? "threads"
        : codexSeats.length
          ? "seats"
          : "editor");
  const [npcCreateSubview, setNpcCreateSubview] = useState<NpcCreateSubview>(defaultNpcCreateSubview);
  const sourceThreadCatalogJson = useMemo(
    () =>
      JSON.stringify(
        allThreadCandidates.map((thread) => ({
          id: text(thread.id ?? thread.workstation_id, ""),
          workstation_id: text(thread.workstation_id ?? thread.id, ""),
          name: text(thread.name ?? thread.label, ""),
          ai_provider_id: platformProviderIdFromThread(thread),
          ai_provider: platformProviderLabelFromThread(thread),
          computer_node_id: text(thread.computer_node_id ?? thread.computer_node, ""),
          computer_node: text(thread.computer_node ?? thread.computer_node_id, ""),
          model: text(thread.model ?? thread.metadata?.model, ""),
        })),
      ),
    [allThreadCandidates],
  );
  const npcEditorReturnPath = editorSeatId
    ? buildProjectSurfacePath(projectEntryPath, {
        panel: "team",
        tab: "npc-create",
        seat: editorSeatId,
      })
    : editorThreadId
      ? buildProjectSurfacePath(projectEntryPath, {
          panel: "team",
          tab: "npc-create",
          bind_thread: editorThreadId,
          bind_node: editorNodeId,
          npc_name: editorName,
          npc_role: editorResponsibility,
        })
      : buildProjectSurfacePath(projectEntryPath, {
          panel: "team",
          tab: "npc-create",
        });
  const skillLibraryReturnPath = text(
    props.skillReturnTo,
    buildProjectSurfacePath(projectEntryPath, {
      panel: "team",
      tab: "skills",
    }),
  );
  const npcCreateReturnPath = buildProjectSurfacePath(projectEntryPath, {
    panel: "team",
    tab: "npc-create",
  });
  const exchangePanelReturnPath = buildProjectSurfacePath(projectEntryPath, {
    panel: "team",
    tab: "exchange",
  });
  const developmentWorkshopReturnPath = buildProjectSurfacePath(projectEntryPath, {
    panel: "team",
    tab: "development-workshop",
  });
  const scheduleReturnPath = buildProjectSurfacePath(projectEntryPath, {
    panel: "team",
    tab: "schedule",
  });
  const gitPanelReturnPath = buildProjectSurfacePath(projectEntryPath, {
    panel: "team",
    tab: "git",
  });
  const machineRoomReturnPath = buildProjectSurfacePath(projectEntryPath, {
    panel: "team",
    tab: "machine-room",
  });
  const computersPanelReturnPath = buildProjectSurfacePath(projectEntryPath, {
    panel: "team",
    tab: "computers",
  });
  function buildPanelSurfaceHref(nextPanel: PanelView, nextParams?: Record<string, string | undefined>) {
    return buildProjectSurfacePath(projectEntryPath, {
      panel: "team",
      tab: nextPanel,
      ...(nextParams ?? {}),
    });
  }
  function buildNpcSeatSurfaceHref(
    nextSeatId: string,
    nextDrawerKind?: "npc-dialog" | "npc-profile" | "npc-bind" | "npc-skills",
  ) {
    const normalizedSeatId = text(nextSeatId, "");
    return buildPanelSurfaceHref("npc-create", {
      seat: normalizedSeatId || undefined,
      drawer: nextDrawerKind,
      drawer_id: nextDrawerKind ? normalizedSeatId || undefined : undefined,
    });
  }
  function buildExchangeSurfaceHref(
    nextSectionId: string,
    nextComposerMode?: ExchangeComposerMode | null,
    nextParams?: Record<string, string | undefined>,
  ) {
    const normalizedSectionId = normalizeExchangeSectionId(nextSectionId);
    return buildProjectSurfacePath(projectEntryPath, {
      panel: "team",
      tab: "exchange",
      exchange_section: normalizedSectionId === "overview" ? undefined : normalizedSectionId,
      exchange_composer: nextComposerMode ?? undefined,
      ...(nextParams ?? {}),
    });
  }
  const starterDrawer = useMemo(
    () =>
      buildStarterDrawer({
        hasProtectedDataGap,
        focusSeat: starterSeat,
        finalReplyFeed,
        recommendedAction,
        reloginPath,
      }),
    [hasProtectedDataGap, starterSeat, finalReplyFeed, recommendedAction, reloginPath],
  );
  const modeEntries = useMemo(
    () =>
      buildModeEntries({
        hasProtectedDataGap,
        starterDrawer,
        starterSeat,
        stalledSeatSummary,
        activeThreadCount: activeSourceThreads.length,
        seatCount: codexSeats.length,
        finalReplyCount: finalReplyFeed.length,
        recommendedAction,
        reloginPath,
        projectPlazaPath: "/projects",
        modeChoicePath,
        modeBoardPaths,
        modeShellPaths,
        modeDefinitionsById,
        projectId,
        projectPath,
      }),
    [
      hasProtectedDataGap,
      starterDrawer,
      starterSeat,
      stalledSeatSummary,
      activeSourceThreads.length,
      codexSeats.length,
      finalReplyFeed.length,
      recommendedAction,
      reloginPath,
      modeChoicePath,
      modeBoardPaths,
      modeShellPaths,
      modeDefinitionsById,
      projectId,
      projectPath,
    ],
  );
  const defaultSelectedModeId =
    modeEntries.find((mode) => mode.id === text(props.initialModeId, ""))?.id ??
    modeEntries.find((mode) => mode.active)?.id ??
    modeEntries[0]?.id ??
    "2d-dev";
  const [starterDrawerOpen, setStarterDrawerOpen] = useState(false);
  const shouldOpenFocusRailForAttention = Boolean(hasProtectedDataGap || humanReviewAlert || gitPreflightAttention);
  const [focusRailOpen, setFocusRailOpen] = useState(false);
  const [modePlannerOpen, setModePlannerOpen] = useState(defaultSelectedModeId !== "2d-dev");
  const selectedModeId = defaultSelectedModeId;
  const selectedMode = modeEntries.find((mode) => mode.id === selectedModeId) ?? modeEntries[0] ?? null;
  const selectedModeEntryPath = selectedMode ? buildCurrentProjectEntryPath(selectedMode.id) : projectPath;
  const selectedModeBoardPath =
    selectedMode
      ? buildCurrentProjectBoardPath(selectedMode.id)
      : modeChoicePath;
  const selectedModeLayerKinds = selectedMode ? Array.from(new Set(selectedMode.entrySteps.map((step) => step.layerKind))) : [];
  const selectedModeLayerKindSummary = selectedMode ? summarizeEntryLayerKinds(selectedMode.entrySteps) : "";
  const selectedModeSharedFrontDoorSteps = selectedMode
    ? selectedMode.entrySteps.filter((step) => step.layerKind === "路由层")
    : [];
  const selectedModeSharedFrontDoorHints = new Set(selectedModeSharedFrontDoorSteps.map((step) => step.routeHint));
  const selectedModeSharedFrontDoor = selectedModeSharedFrontDoorSteps.map((step) => step.routeHint).join(" -> ");
  const selectedModeSharedFrontDoorLabelPath = selectedModeSharedFrontDoorSteps.map((step) => step.label).join(" -> ");
  const selectedModeSharedFrontDoorLayerKindSummary = summarizeEntryLayerKinds(selectedModeSharedFrontDoorSteps);
  const selectedModeSharedFrontDoorEnd =
    selectedModeSharedFrontDoorSteps.length > 0
      ? selectedModeSharedFrontDoorSteps[selectedModeSharedFrontDoorSteps.length - 1]
      : null;
  const selectedModeBranchStart =
    selectedMode?.entrySteps.find((step) => step.layerKind !== "路由层") ?? null;
  const selectedModeBranchStartIndex = selectedMode
    ? selectedMode.entrySteps.findIndex((step) => step.layerKind !== "路由层")
    : -1;
  const selectedModeDivergenceLayers =
    selectedMode && selectedModeBranchStartIndex >= 0
      ? selectedMode.entrySteps.length - selectedModeBranchStartIndex
      : 0;
  const selectedModeDivergencePath =
    selectedMode && selectedModeBranchStartIndex >= 0
      ? selectedMode.entrySteps
          .slice(selectedModeBranchStartIndex)
          .map((step) => step.routeHint)
          .join(" -> ")
      : "";
  const selectedModeDivergenceLabelPath =
    selectedMode && selectedModeBranchStartIndex >= 0
      ? selectedMode.entrySteps
          .slice(selectedModeBranchStartIndex)
          .map((step) => step.label)
          .join(" -> ")
      : "";
  const selectedModeDivergenceSteps =
    selectedMode && selectedModeBranchStartIndex >= 0 ? selectedMode.entrySteps.slice(selectedModeBranchStartIndex) : [];
  const selectedModeDivergenceLayerKindSummary = summarizeEntryLayerKinds(selectedModeDivergenceSteps);
  const selectedModeStructureSummary =
    selectedModeSharedFrontDoorHints.size || selectedModeDivergenceLayers
      ? `共享前门 ${selectedModeSharedFrontDoorHints.size} 层 + 模式尾段 ${selectedModeDivergenceLayers} 层`
      : "";
  const selectedModeSegmentStructureSummary =
    selectedModeSharedFrontDoorLayerKindSummary || selectedModeDivergenceLayerKindSummary
      ? `共享前门(${selectedModeSharedFrontDoorLayerKindSummary || "无"}) + 模式尾段(${selectedModeDivergenceLayerKindSummary || "无"})`
      : "";
  const selectedModeFinalStep =
    selectedMode && selectedMode.entrySteps.length > 0
      ? selectedMode.entrySteps[selectedMode.entrySteps.length - 1]
      : null;
  const selectedModeCheckpointPath = Array.from(
    new Set(
      [selectedModeSharedFrontDoorEnd?.label, selectedModeBranchStart?.label, selectedModeFinalStep?.label].filter(
        (value): value is string => Boolean(value),
      ),
    ),
  ).join(" -> ");
  const selectedModeDockMeta = [
    selectedModeStructureSummary ? `入口结构：${selectedModeStructureSummary}` : "",
    selectedModeCheckpointPath ? `检查点：${selectedModeCheckpointPath}` : "",
    selectedModeEntryPath ? `直达入口：${selectedModeEntryPath}` : "",
  ]
    .filter(Boolean)
    .join(" / ");
  const selectedModeDockShellHref =
    selectedMode && !selectedMode.active
      ? selectedMode.actions.find((action) => action.emphasis === "primary" && action.href)?.href ?? selectedModeFinalStep?.href ?? null
      : null;
  const featuredVisibleCodexCommand = useMemo(
    () =>
      pickFeaturedInboxItem(codexInboxFeed.filter((item) => isPrimaryCoordinatorInboxItem(item))) ??
      pickFeaturedInboxItem(codexInboxFeed),
    [codexInboxFeed],
  );
  const featuredVisibleCodexCommandId = featuredVisibleCodexCommand?.id ?? null;
  const featuredQueuedCodexCommand = useMemo(
    () =>
      pickFeaturedQueuedInboxItem(codexInboxFullFeed.filter((item) => isPrimaryCoordinatorInboxItem(item))) ??
      pickFeaturedQueuedInboxItem(codexInboxFullFeed),
    [codexInboxFullFeed],
  );
  const featuredProcessFocusCommand = featuredQueuedCodexCommand ?? featuredVisibleCodexCommand ?? null;
  const seatAcceptanceSummary = useMemo(
    () => buildSeatAcceptanceSummary(mapSeatPayload, hasProtectedDataGap, codexInboxFullFeed),
    [mapSeatPayload, hasProtectedDataGap, codexInboxFullFeed],
  );
  const filteredSkills = useMemo(() => {
    const query = skillQuery.trim().toLowerCase();
    if (!query) return skillLibrary;
    return skillLibrary.filter((item) => {
      const haystack = [
        text(item.id),
        text(item.label),
        text(item.note),
        text(item.source),
        text(resolveSkillCategory(item)),
        displaySkillCategory(resolveSkillCategory(item)),
        text(resolveSkillMetadata(item).description),
        text(resolveSkillMetadata(item).vibe),
        text(resolveSkillMetadata(item).external_path),
        asArray(item.recommended_for).map((value) => text(value)).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [skillLibrary, skillQuery]);
  const skillCategorySummary = useMemo(() => {
    return buildSkillCategorySummary(filteredSkills);
  }, [filteredSkills]);
  const agencySkillCount = useMemo(
    () => skillLibrary.filter((skill) => text(skill.source, "") === "agency-agents").length,
    [skillLibrary],
  );
  const githubSkillCount = useMemo(
    () => skillLibrary.filter((skill) => text(skill.source, "") === "github").length,
    [skillLibrary],
  );
  const agencySkillPackLibrary = useMemo(
    () => (Array.isArray((agencyAgentsSkillPack as AnyRecord).skill_library) ? ((agencyAgentsSkillPack as AnyRecord).skill_library as AnyRecord[]) : []),
    [],
  );
  const agencyCuratedSkillIds = useMemo(
    () => uniqueStrings(asArray((agencyAgentsSkillPack as AnyRecord).curated_seed_skill_ids).map((item) => text(item))),
    [],
  );
  const agencyCuratedSkillIdSet = useMemo(
    () => new Set(agencyCuratedSkillIds.map((item) => item.toLowerCase())),
    [agencyCuratedSkillIds],
  );
  const agencySkillPackById = useMemo(() => {
    const next = new Map<string, AnyRecord>();
    agencySkillPackLibrary.forEach((skill) => {
      const skillId = text(skill.id, "");
      if (!skillId) return;
      next.set(skillId.toLowerCase(), skill);
    });
    return next;
  }, [agencySkillPackLibrary]);
  const agencySkillPackCategories = useMemo(() => buildSkillCategorySummary(agencySkillPackLibrary), [agencySkillPackLibrary]);
  const existingSkillIdSet = useMemo(
    () => new Set(skillLibrary.map((skill) => text(skill.id, "").toLowerCase()).filter(Boolean)),
    [skillLibrary],
  );
  const filteredAgencySkillPack = useMemo(() => {
    const query = skillImportQuery.trim().toLowerCase();
    return agencySkillPackLibrary.filter((skill) => {
      const skillId = text(skill.id, "").toLowerCase();
      if (!skillId) return false;
      if (skillImportRecommendedOnly && !agencyCuratedSkillIdSet.has(skillId)) return false;
      const imported = existingSkillIdSet.has(skillId);
      if (skillImportStatusFilter === "missing" && imported) return false;
      if (skillImportStatusFilter === "existing" && !imported) return false;
      if (skillImportCategoryFilter !== "all" && resolveSkillCategory(skill) !== skillImportCategoryFilter) return false;
      if (!query) return true;
      return matchesSkillLoadoutFilters(skill, { query });
    });
  }, [
    agencySkillPackLibrary,
    existingSkillIdSet,
    skillImportCategoryFilter,
    skillImportQuery,
    skillImportRecommendedOnly,
    skillImportStatusFilter,
    agencyCuratedSkillIdSet,
  ]);
  const roleSkillCategorySummary = useMemo(() => buildSkillCategorySummary(roleSkills), [roleSkills]);
  const roleSkillSourceSummary = useMemo(() => buildSkillSourceSummary(roleSkills), [roleSkills]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const scopedSeatKey = seatStorageKey(projectId);
      const scopedFocusKey = seatFocusStorageKey(projectId);
      const scopedCollaboratorKey = collaboratorStorageKey(projectId);
      const scopedCurrentPlayerKey = currentPlayerStorageKey(projectId);
      if (mapSeatPayloadRaw) {
        window.localStorage.setItem(scopedSeatKey, mapSeatPayloadRaw);
      } else {
        window.localStorage.removeItem(scopedSeatKey);
      }
      if (seatFocusId) {
        window.localStorage.setItem(scopedFocusKey, seatFocusId);
      } else {
        window.localStorage.removeItem(scopedFocusKey);
      }
      if (mapCollaboratorPayloadRaw) {
        window.localStorage.setItem(scopedCollaboratorKey, mapCollaboratorPayloadRaw);
      } else {
        window.localStorage.removeItem(scopedCollaboratorKey);
      }
      if (mapCollaboratorPayload.currentPlayerId) {
        window.localStorage.setItem(scopedCurrentPlayerKey, mapCollaboratorPayload.currentPlayerId);
      } else {
        window.localStorage.removeItem(scopedCurrentPlayerKey);
      }
      if (projectId) {
        window.localStorage.removeItem(PLATFORM_SEAT_KEY);
        window.localStorage.removeItem(PLATFORM_SEAT_FOCUS_KEY);
        window.localStorage.removeItem(PLATFORM_COLLABORATOR_KEY);
        window.localStorage.removeItem(PLATFORM_CURRENT_PLAYER_KEY);
      }
    } catch {}
  }, [
    mapSeatPayloadRaw,
    mapCollaboratorPayloadRaw,
    mapCollaboratorPayload.currentPlayerId,
    projectId,
    seatFocusId,
  ]);

  useEffect(() => {
    if (panelView !== "npc-create") return;
    if (editorSeatId || editorThreadId) {
      setNpcCreateSubview("editor");
      return;
    }
    setNpcCreateSubview((current) => {
      if (current === "threads" && allThreadCandidates.length) return current;
      if (current === "seats" && codexSeats.length) return current;
      if (current === "editor") return current;
      if (allThreadCandidates.length) return "threads";
      if (codexSeats.length) return "seats";
      return "editor";
    });
  }, [panelView, editorSeatId, editorThreadId, allThreadCandidates.length, codexSeats.length]);

  useEffect(() => {
    if (selectedModeId === "2d-dev") return;
    setModePlannerOpen(true);
  }, [selectedModeId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (shouldOpenFocusRailForAttention) {
      setFocusRailOpen(true);
      return;
    }
    try {
      const saved = window.localStorage.getItem(focusRailStorageKey(projectId));
      if (saved === "0") setFocusRailOpen(false);
      if (saved === "1") setFocusRailOpen(true);
    } catch {}
  }, [projectId, shouldOpenFocusRailForAttention]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(focusRailStorageKey(projectId), focusRailOpen ? "1" : "0");
      if (projectId) {
        window.localStorage.removeItem(PLATFORM_FOCUS_RAIL_KEY);
      }
    } catch {}
  }, [focusRailOpen, projectId]);

  useEffect(() => {
    if (props.teamNotice || props.teamError) {
      setPendingActionLabel(null);
    }
  }, [props.teamNotice, props.teamError]);

  useEffect(() => {
    if (pairingToken || workstationToken) {
      setPendingActionLabel(null);
    }
  }, [pairingToken, workstationToken]);

  useEffect(() => {
    if (!pendingActionLabel || typeof window === "undefined") return;
    const timer = window.setTimeout(() => {
      setPendingActionLabel(null);
    }, 18000);
    return () => window.clearTimeout(timer);
  }, [pendingActionLabel]);

  useEffect(() => {
    if (!pendingActionLabel) return;
    setPendingActionLabel(null);
  }, [activeSourceThreads.length, nodes.length, props.collaborationMessages.length]);

  useEffect(() => {
    if (panelView === "exchange") return;
    setExchangeComposerMode(null);
  }, [panelView]);

  useEffect(() => {
    if (!panelOpen || typeof window === "undefined") return;
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeBackpackPanel();
      }
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [panelOpen]);

  useEffect(() => {
    setSeatFocusId(text(props.initialSeatFocusId, ""));
  }, [props.initialSeatFocusId]);

  useEffect(() => {
    setMachineRoomFocusThreadId(text(props.initialBindThreadId, ""));
  }, [props.initialBindThreadId]);

  useEffect(() => {
    if (!props.initialNpcCreateSubview) return;
    setNpcCreateSubview(props.initialNpcCreateSubview);
  }, [props.initialNpcCreateSubview]);

  useEffect(() => {
    if (!props.initialManagerDrawerKind) {
      setManagerDrawer(null);
      return;
    }
    setManagerDrawer({
      kind: props.initialManagerDrawerKind,
      id: text(props.initialManagerDrawerId ?? props.initialSeatFocusId, "") || undefined,
    });
  }, [props.initialManagerDrawerId, props.initialManagerDrawerKind, props.initialSeatFocusId]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    function syncSeatPanelState(nextSeatId: string) {
      const normalizedSeatId = text(nextSeatId, "");
      if (!normalizedSeatId) return;
      setSeatFocusId(normalizedSeatId);
      setPanelView("npc-create");
      setNpcCreateSubview("seats");
      setManagerDrawer({ kind: "npc-dialog", id: normalizedSeatId });
      setPanelOpen(true);
      try {
        window.history.replaceState({}, "", buildNpcSeatSurfaceHref(normalizedSeatId, "npc-dialog"));
      } catch {}
    }

    function openSchedulePanelState() {
      setPendingActionLabel(null);
      setManagerDrawer(null);
      setPanelView("schedule");
      setPanelOpen(true);
      try {
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.set("panel", "team");
        nextUrl.searchParams.set("tab", "schedule");
        nextUrl.searchParams.delete("seat");
        window.history.replaceState({}, "", nextUrl.toString());
      } catch {}
    }

    function openSerialTvPanelState() {
      setPendingActionLabel(null);
      setManagerDrawer(null);
      setPanelView("serial-tv");
      setPanelOpen(true);
      try {
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.set("panel", "team");
        nextUrl.searchParams.set("tab", "serial-tv");
        nextUrl.searchParams.delete("seat");
        window.history.replaceState({}, "", nextUrl.toString());
      } catch {}
    }

    function openDevelopmentWorkshopPanelState() {
      setPendingActionLabel(null);
      setManagerDrawer(null);
      setPanelView("development-workshop");
      setPanelOpen(true);
      try {
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.set("panel", "team");
        nextUrl.searchParams.set("tab", "development-workshop");
        nextUrl.searchParams.delete("seat");
        window.history.replaceState({}, "", nextUrl.toString());
      } catch {}
    }

    function handleFrameMessage(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      const payload = event.data as { type?: string; projectId?: string; seatId?: string } | null;
      if (!payload) return;
      if (text(payload.projectId, projectId) !== projectId) return;
      if (payload.type === FARM_OPEN_NPC_SEAT_EVENT) {
        syncSeatPanelState(text(payload.seatId, ""));
        return;
      }
      if (payload.type === FARM_OPEN_SCHEDULE_EVENT) {
        openSchedulePanelState();
        return;
      }
      if (payload.type === FARM_OPEN_SERIAL_TV_EVENT) {
        openSerialTvPanelState();
        return;
      }
      if (payload.type === FARM_OPEN_DEVELOPMENT_WORKSHOP_EVENT) {
        openDevelopmentWorkshopPanelState();
      }
    }

    window.addEventListener("message", handleFrameMessage);
    return () => window.removeEventListener("message", handleFrameMessage);
  }, [projectId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!panelOpen || panelView !== "npc-create" || !seatFocusId) return;

    const timer = window.requestAnimationFrame(() => {
      const card = window.document.querySelector<HTMLElement>(`[data-seat-card="${CSS.escape(seatFocusId)}"]`);
      card?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });

    return () => window.cancelAnimationFrame(timer);
  }, [panelOpen, panelView, seatFocusId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!panelOpen || panelView !== "machine-room" || !machineRoomFocusThreadId) return;

    const timer = window.requestAnimationFrame(() => {
      const escaped = CSS.escape(machineRoomFocusThreadId);
      const card =
        window.document.querySelector<HTMLElement>(`[data-machine-thread-attention-card="${escaped}"]`) ??
        window.document.querySelector<HTMLElement>(`[data-machine-thread-card="${escaped}"]`);
      card?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });

    return () => window.cancelAnimationFrame(timer);
  }, [panelOpen, panelView, machineRoomFocusThreadId, machineRoomVisibleWorkstations.length]);

  function focusSeatOnEmbeddedMap(nextSeatId: string) {
    const normalizedSeatId = text(nextSeatId, "");
    if (!normalizedSeatId) return false;

    setSeatFocusId(normalizedSeatId);
    try {
      const frameWindow = gameFrameRef.current?.contentWindow;
      if (!frameWindow) return false;
      frameWindow.postMessage(
        {
          type: FARM_FOCUS_NPC_SEAT_EVENT,
          projectId,
          seatId: normalizedSeatId,
        },
        window.location.origin,
      );
      return true;
    } catch {
      return false;
    }
  }

  function openStarterPanel(nextPanel: PanelView, nextSeatId?: string | null) {
    if (nextSeatId) {
      focusSeatOnEmbeddedMap(nextSeatId);
      setSeatFocusId(nextSeatId);
    }
    setPendingActionLabel(null);
    setManagerDrawer(null);
    setPanelView(nextPanel);
    setPanelOpen(true);
    if (typeof window !== "undefined") {
      try {
        const nextUrl = buildPanelSurfaceHref(nextPanel, nextSeatId ? { seat: text(nextSeatId, "") } : undefined);
        window.history.replaceState({}, "", nextUrl);
      } catch {}
    }
  }

  function openHumanPartyPanel(nextPlayerId?: string | null) {
    const normalizedPlayerId = text(nextPlayerId, "") || currentHumanPartyPlayer?.id || humanPartyHud[0]?.id || "";
    setPendingActionLabel(null);
    setManagerDrawer(null);
    clearExchangeFocus();
    setExchangeComposerMode(null);
    setExchangeSectionFocusId("overview");
    setHumanPartyFocusId(normalizedPlayerId);
    setPanelView("human-party");
    setPanelOpen(true);
    if (typeof window !== "undefined") {
      try {
        const nextUrl = buildPanelSurfaceHref("human-party", {
          human_party: normalizedPlayerId || undefined,
        });
        window.history.replaceState({}, "", nextUrl);
      } catch {}
    }
  }

  function openExchangePanel(
    nextSectionId: ExchangeSectionId = "overview",
    nextComposerMode: ExchangeComposerMode | null = null,
  ) {
    const normalizedSectionId = normalizeExchangeSectionId(nextSectionId);
    setPendingActionLabel(null);
    setManagerDrawer(null);
    clearExchangeFocus();
    setExchangeComposerMode(nextComposerMode);
    setExchangeSectionFocusId(normalizedSectionId);
    setPanelView("exchange");
    setPanelOpen(true);
    if (typeof window !== "undefined") {
      try {
        const nextUrl = buildExchangeSurfaceHref(normalizedSectionId, nextComposerMode);
        window.history.replaceState({}, "", nextUrl);
      } catch {}
    }
  }

  function openBackpackPanel(nextPanel: PanelView) {
    if (nextPanel === "exchange") {
      openExchangePanel("overview", null);
      return;
    }
    setPendingActionLabel(null);
    setManagerDrawer(null);
    clearExchangeFocus();
    setExchangeComposerMode(null);
    if (nextPanel === "human-party") {
      setHumanPartyFocusId(currentHumanPartyPlayer?.id ?? humanPartyHud[0]?.id ?? "");
    }
    setPanelView(nextPanel);
    setPanelOpen(true);
    if (typeof window !== "undefined") {
      try {
        const nextUrl = buildPanelSurfaceHref(
          nextPanel,
          nextPanel === "human-party"
            ? { human_party: currentHumanPartyPlayer?.id ?? humanPartyHud[0]?.id ?? undefined }
            : undefined,
        );
        window.history.replaceState({}, "", nextUrl);
      } catch {}
    }
  }

  function openExchangeFocusScene(nextLabel: string, nextRouteKeys: string[]) {
    const normalizedLabel = text(nextLabel, "");
    const normalizedRouteKeys = uniqueStrings(nextRouteKeys);
    if (!normalizedLabel || !normalizedRouteKeys.length) return;
    setPendingActionLabel(null);
    setManagerDrawer(null);
    setExchangeFocusLabel(normalizedLabel);
    setExchangeFocusRouteKeys(normalizedRouteKeys);
    setExchangeSectionFocusId("dispatch");
    setPanelView("exchange");
    setPanelOpen(true);
    if (typeof window !== "undefined") {
      try {
        const nextUrl = buildExchangeSurfaceHref("dispatch");
        window.history.replaceState({}, "", nextUrl);
      } catch {}
    }
  }

  function openExchangeForHumanParty(player: HumanPartyHudEntry | null | undefined) {
    if (!player) return;
    openExchangeFocusScene(player.name, player.routeKeys);
  }

  function openComputersForHumanParty(player: HumanPartyHudEntry | null) {
    if (!player) {
      openBackpackPanel("computers");
      return;
    }
    const ownedGroup =
      computerFleetGroups.find((group) => group.id.toLowerCase() === player.id.toLowerCase()) ?? null;
    const preferredComputer = ownedGroup?.computers[0] ?? null;
    const preferredComputerId = text(
      preferredComputer?.id ?? preferredComputer?.node_id ?? preferredComputer?.name ?? preferredComputer?.label,
      "",
    );
    setPendingActionLabel(null);
    setManagerDrawer(null);
    clearExchangeFocus();
    setExchangeComposerMode(null);
    if (preferredComputerId) {
      setComputerFocusId(preferredComputerId);
    }
    setPanelView("computers");
    setPanelOpen(true);
  }

  function openMachineRoomThread(nextThreadId: string, nextComputerNodeId?: string | null) {
    const normalizedThreadId = text(nextThreadId, "");
    if (!normalizedThreadId) return;
    setPendingActionLabel(null);
    setManagerDrawer(null);
    clearExchangeFocus();
    setMachineRoomFocusThreadId(normalizedThreadId);
    const normalizedNodeId = text(nextComputerNodeId, "");
    if (normalizedNodeId) {
      setComputerFocusId(normalizedNodeId);
    }
    setPanelView("machine-room");
    setPanelOpen(true);
  }

  function openNpcProfileFromExchange(nextSeatId: string) {
    const normalizedSeatId = text(nextSeatId, "");
    if (!normalizedSeatId) return;
    setPendingActionLabel(null);
    setPanelView("npc-create");
    setNpcCreateSubview("seats");
    setManagerDrawer({ kind: "npc-profile", id: normalizedSeatId });
    setPanelOpen(true);
    focusSeatOnEmbeddedMap(normalizedSeatId);
  }

  function resolveWorkstationExchangeTarget(workstation: AnyRecord) {
    const threadId = text(workstation.id ?? workstation.workstation_id ?? workstation.config_id, "");
    if (!threadId) return null;
    const sourceThreadId = text(workstation.source_workstation_id ?? workstation.metadata?.source_workstation_id, "");
    const threadLabel = display(workstation.name ?? workstation.label, threadId);
    const computerNodeId = text(workstation.computer_node_id ?? workstation.computer_node, "");
    const isSeatBackedWorkstation = isNpcSeatWorkstation(workstation);
    const workstationCandidateKeys = uniqueStrings([
      threadId,
      sourceThreadId,
      ...workstationRouteKeys(workstation),
      ...threadRouteKeys(workstation),
    ]);
    const boundSeat = isSeatBackedWorkstation
      ? workstation
      : workstationCandidateKeys
          .map((candidate) => seatBySourceThreadId.get(candidate) ?? seatBySourceThreadId.get(candidate.toLowerCase()) ?? null)
          .find((candidate): candidate is AnyRecord => Boolean(candidate)) ?? null;
    const boundSeatView = boundSeat ? resolveSeatViewForRecord(boundSeat, seatPayloadMap) : null;
    const boundSeatId = boundSeat ? preferredSeatRouteId(boundSeat, boundSeatView) : "";
    const machineRoomTargetId = sourceThreadId || threadId || boundSeatId;
    const routeKeys = uniqueStrings([
      machineRoomTargetId,
      threadLabel,
      ...workstationCandidateKeys,
      ...(boundSeat ? seatRouteKeys(boundSeat) : []),
      boundSeatId,
      text(boundSeat?.name, ""),
    ]).map((value) => value.toLowerCase());
    return {
      threadId: machineRoomTargetId,
      threadLabel,
      computerNodeId,
      seatId: boundSeatId || undefined,
      seatLabel: boundSeat ? text(boundSeat.name, "") : undefined,
      routeKeys,
    };
  }

  function resolveExchangeTargetFromCandidate(candidate: string) {
    const normalizedCandidate = text(candidate, "").toLowerCase();
    if (!normalizedCandidate) return null;

    const workstationMap = new Map<string, AnyRecord>();
    exchangeTargetWorkstations.forEach((workstation) => {
      const workstationId = text(workstation.id ?? workstation.workstation_id ?? workstation.config_id, "").toLowerCase();
      if (!workstationId || workstationMap.has(workstationId)) return;
      workstationMap.set(workstationId, workstation);
    });

    for (const workstation of workstationMap.values()) {
      const target = resolveWorkstationExchangeTarget(workstation);
      if (!target || !target.routeKeys.includes(normalizedCandidate)) continue;
      return {
        threadId: target.threadId,
        threadLabel: target.threadLabel,
        computerNodeId: target.computerNodeId,
        seatId: target.seatId,
        seatLabel: target.seatLabel,
      };
    }

    for (const seat of codexSeats) {
      const targetId = text(seat.id ?? seat.workstation_id ?? seat.config_id, "");
      const seatView = resolveSeatViewForRecord(seat, seatPayloadMap);
      const preferredSeatId = preferredSeatRouteId(seat, seatView);
      const sourceThreadId = text(seat.source_workstation_id ?? seat.metadata?.source_workstation_id, "");
      const seatLabel = display(seat.name ?? seat.label, preferredSeatId || targetId || "NPC");
      const computerNodeId = text(seat.computer_node_id ?? seat.computer_node, "");
      const machineRoomTargetId = sourceThreadId || targetId || preferredSeatId;
      const routeKeys = uniqueStrings([
        targetId,
        preferredSeatId,
        sourceThreadId,
        seatLabel,
        ...seatRouteKeys(seat),
      ]).map((value) => value.toLowerCase());
      if (!routeKeys.includes(normalizedCandidate)) continue;
      return {
        threadId: machineRoomTargetId || undefined,
        threadLabel: sourceThreadId ? undefined : seatLabel,
        computerNodeId,
        seatId: preferredSeatId || undefined,
        seatLabel,
      };
    }

    return null;
  }

  function buildExchangeCommandTargets() {
    const targetMap = new Map<string, { id: string; label: string; meta: string; providerLabel: string }>();
    allThreadCandidates.forEach((thread) => {
      const targetId = text(thread.id ?? thread.workstation_id, "");
      if (!targetId || targetMap.has(targetId)) return;
      if (adapterTargetIdSet.size && !adapterTargetIdSet.has(targetId.toLowerCase())) return;
      const computerNodeId = text(thread.computer_node_id ?? thread.computer_node, "");
      targetMap.set(targetId, {
        id: targetId,
        label: display(thread.name ?? thread.label, targetId),
        meta: `线程 / ${display(computerNodeId, "未绑定电脑")}`,
        providerLabel: platformProviderLabelFromThread(thread),
      });
    });
    codexSeats.forEach((seat) => {
      const targetId = text(seat.id ?? seat.workstation_id ?? seat.config_id, "");
      if (!targetId || targetMap.has(targetId)) return;
      if (adapterTargetIdSet.size && !adapterTargetIdSet.has(targetId.toLowerCase())) return;
      const computerNodeId = text(seat.computer_node_id ?? seat.computer_node, "");
      targetMap.set(targetId, {
        id: targetId,
        label: display(seat.name ?? seat.label, targetId),
        meta: `NPC / ${display(computerNodeId, "未绑定电脑")}`,
        providerLabel: platformProviderLabelFromSeat(seat),
      });
    });
    return Array.from(targetMap.values());
  }

  function buildHistoricalExchangeFocus(threadId: string) {
    const normalizedThreadId = text(threadId, "").toLowerCase();
    if (!normalizedThreadId) return null;

    const matchingProof =
      cooperationProofFeed.find((item) =>
        uniqueStrings([item.target, ...item.routeKeys]).some((candidate) => candidate.toLowerCase() === normalizedThreadId),
      ) ?? null;
    const matchingMessage =
      sortedByUpdatedAt(
        props.collaborationMessages.filter((message) =>
          collaborationRouteKeys(message).some((candidate) => candidate.toLowerCase() === normalizedThreadId),
        ),
      )[0] ?? null;

    if (!matchingProof && !matchingMessage) return null;

    const routeKeys = uniqueStrings([
      threadId,
      ...(matchingProof ? [matchingProof.target, ...matchingProof.routeKeys] : []),
      ...(matchingMessage ? collaborationRouteKeys(matchingMessage) : []),
    ]);

    return {
      proof: matchingProof,
      message: matchingMessage,
      focusLabel:
        matchingProof?.title ||
        text(matchingMessage?.title ?? matchingMessage?.body, "") ||
        threadId,
      routeKeys,
      summary:
        matchingProof?.body ||
        shortText(text(matchingMessage?.body, ""), "这条线程当前只剩历史协作证据，没有实时机房卡。", 120),
    };
  }

  function clearExchangeFocus() {
    setExchangeFocusLabel("");
    setExchangeFocusRouteKeys([]);
  }

  function focusExchangeSection(nextSectionId: string) {
    const normalizedSectionId = normalizeExchangeSectionId(nextSectionId);
    setExchangeSectionFocusId(normalizedSectionId);
    setExchangeComposerMode(null);
    if (typeof window !== "undefined") {
      try {
        const nextUrl = buildExchangeSurfaceHref(normalizedSectionId);
        window.history.replaceState({}, "", nextUrl);
      } catch {}
    }
    if (typeof document === "undefined") return;
    const timer = window.requestAnimationFrame(() => {
      const target = document.querySelector(`[data-exchange-section="${normalizedSectionId}"]`);
      if (!(target instanceof HTMLElement)) return;
      const fold = target.querySelector("details");
      if (fold instanceof HTMLDetailsElement) {
        fold.open = true;
      }
      target.scrollIntoView({ block: "start", inline: "nearest", behavior: "smooth" });
    });
    window.setTimeout(() => window.cancelAnimationFrame(timer), 1000);
  }

  function closeBackpackPanel() {
    setPendingActionLabel(null);
    setManagerDrawer(null);
    clearExchangeFocus();
    setExchangeComposerMode(null);
    setPanelOpen(false);
    if (typeof window !== "undefined") {
      try {
        window.history.replaceState({}, "", projectEntryPath);
      } catch {}
    }
  }

  function openManagerDrawer(kind: ManagerDrawerKind, id?: string) {
    setPendingActionLabel(null);
    setManagerDrawer({ kind, id });
  }

  function closeManagerDrawer() {
    setManagerDrawer(null);
    if (typeof window !== "undefined") {
      try {
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.delete("drawer");
        nextUrl.searchParams.delete("drawer_id");
        window.history.replaceState({}, "", nextUrl.toString());
      } catch {}
    }
  }

  function toggleSkinPreview() {
    const nextEnabled = !skinPreviewEnabled;
    setSkinPreviewEnabled(nextEnabled);
    if (typeof window === "undefined") return;
    try {
      const url = new URL(window.location.href);
      if (nextEnabled) {
        url.searchParams.set("skin", "a-agent-lab");
      } else {
        url.searchParams.delete("skin");
      }
      window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    } catch {}
  }

  function handlePanelSubmit(event: FormEvent<HTMLElement>) {
    const nativeEvent = event.nativeEvent as SubmitEvent;
    const submitter = nativeEvent.submitter as HTMLElement | null;
    const label =
      submitter?.getAttribute("data-loading-label") ||
      submitter?.textContent?.trim() ||
      "正在处理";
    setPendingActionLabel(label);
  }

  const featuredProcessFocusLabel = featuredProcessFocusCommand
    ? focusAnchorLabel(featuredProcessFocusCommand.target, featuredProcessFocusCommand.requirementId)
    : "";
  const featuredProcessQueuedCount = countQueuedInboxItemsForFocus(codexInboxFullFeed, featuredProcessFocusCommand);
  const featuredCooperationFocusLabel = featuredCooperationProof
    ? focusAnchorLabel(featuredCooperationProof.target, featuredCooperationProof.requirementId)
    : "";
  const attentionOwnerSeat =
    humanReviewSeats[0] ??
    stalledSeatSummary?.topSeat ??
    (starterSeat?.minimalAck && !starterSeat?.finalReply && starterSeatProgressWarning ? starterSeat : null);
  const currentOwnerFocusLabel = attentionOwnerSeat?.name || featuredCooperationFocusLabel || visibleOwner || "待分配";
  const currentOwnerStatusLabel = attentionOwnerSeat
    ? seatBridgeIssueLabel(attentionOwnerSeat) ??
      attentionOwnerSeat.progressWarningLabel ??
      attentionOwnerSeat.progressHealthLabel
    : featuredCooperationProof?.progressLabel || null;
  const summaryCards = [
    {
      id: "current-action",
      title: "当前推荐动作",
      body: recommendedAction,
      meta: `${humanReviewAlert ? `人工审核 ${humanReviewAlert.count} 条 / ${humanReviewAlert.owner}` : "暂无怼脸人审"} / 接单 ${watchReadyNodes.length}/${nodes.length} 台 / 排队 ${queuedCollaborationCommandCount} 条 / 真实线程 ${realThreadCount} 条 / 已发 Codex 指令 ${codexInboxFullFeed.length} 条${featuredProcessFocusLabel ? ` / 当前聚焦 ${featuredProcessFocusLabel}` : ""}${featuredProcessFocusCommand?.queueStartedAtLabel ? ` / 排队起点 ${featuredProcessFocusCommand.queueStartedAtLabel}` : ""}${featuredProcessFocusCommand?.queueAgeLabel ? ` / 已等 ${featuredProcessFocusCommand.queueAgeLabel}` : ""}${featuredProcessFocusCommand?.queueStateLabel ? ` / ${featuredProcessFocusCommand.queueStateLabel}` : ""}`,
    },
    {
      id: "current-owner",
      title: "当前负责人",
      body: hasProtectedDataGap
        ? visibleOwner || "待分配"
        : `${currentOwnerFocusLabel}${currentOwnerStatusLabel ? ` · ${currentOwnerStatusLabel}` : ""}${featuredProcessQueuedCount > 1 ? ` · 同线程 ${featuredProcessQueuedCount} 条排队` : ""}${featuredProcessFocusCommand?.queueStartedAtLabel ? ` · 起于 ${featuredProcessFocusCommand.queueStartedAtLabel}` : ""}${featuredProcessFocusCommand?.queueAgeLabel ? ` · 已等 ${featuredProcessFocusCommand.queueAgeLabel}` : ""}${featuredProcessFocusCommand?.queueStateLabel ? ` · ${featuredProcessFocusCommand.queueStateLabel}` : ""}`,
      meta: hasProtectedDataGap
        ? "重新登录后再判断真实负责人。"
        : `${humanReviewAlert ? `先处理人工审核：${humanReviewAlert.detail}` : attentionOwnerSeat && stalledSeatSummary?.detail ? `${stalledSeatRecoveryAction || `先处理 ${stalledSeatSummary.detail}。`}` : attentionOwnerSeat?.progressWarningLabel === "最小回执偏晚" ? `先继续盯住 ${attentionOwnerSeat.name} 的结果收口，不要把这条链误判成彻底卡死。` : attentionOwnerSeat?.progressWarningLabel === "进度信号待归一" ? `先继续盯住 ${attentionOwnerSeat.name} 的结果收口，再把旧进度信号归一回真正的 progress_ack。` : "优先让当前线程先回最小回执，再收口成最终回复。"}${currentOwnerFocusLabel ? ` / 当前聚焦 ${currentOwnerFocusLabel}${currentOwnerStatusLabel ? ` / ${currentOwnerStatusLabel}` : ""}` : ""}${featuredProcessFocusCommand?.queueStartedAtLabel ? ` / 排队起点 ${featuredProcessFocusCommand.queueStartedAtLabel}` : ""}${featuredProcessFocusCommand?.queueAgeLabel ? ` / 已等 ${featuredProcessFocusCommand.queueAgeLabel}` : ""}${featuredProcessFocusCommand?.queueStateLabel ? ` / ${featuredProcessFocusCommand.queueStateLabel}` : ""}`,
    },
    {
      id: "final-replies",
      title: "最终回复池",
      body: hasProtectedDataGap
        ? "未授权"
        : featuredProcessFocusCommand?.isQueued
          ? `${finalReplyFeed.length} 条 · ${featuredProcessFocusLabel} 待收口${featuredProcessQueuedCount > 1 ? ` · 同线程 ${featuredProcessQueuedCount} 条排队` : ""}${featuredProcessFocusCommand.queueStartedAtLabel ? ` · 起于 ${featuredProcessFocusCommand.queueStartedAtLabel}` : ""}${featuredProcessFocusCommand.queueAgeLabel ? ` · 已等 ${featuredProcessFocusCommand.queueAgeLabel}` : ""}${featuredProcessFocusCommand.queueStateLabel ? ` · ${featuredProcessFocusCommand.queueStateLabel}` : ""}`
          : `${finalReplyFeed.length} 条`,
      meta: hasProtectedDataGap
        ? "当前登录态没有拿到最终回复池。"
        : `这里只保留最终收口结果，不把过程噪音堆上首屏。${featuredProcessFocusCommand?.isQueued ? ` / 当前聚焦 ${featuredProcessFocusLabel} 仍未进入最终回复池${featuredProcessFocusCommand.queueStartedAtLabel ? ` / 排队起点 ${featuredProcessFocusCommand.queueStartedAtLabel}` : ""}${featuredProcessFocusCommand.queueAgeLabel ? ` / 已等 ${featuredProcessFocusCommand.queueAgeLabel}` : ""}${featuredProcessFocusCommand.queueStateLabel ? ` / ${featuredProcessFocusCommand.queueStateLabel}` : ""}` : ""}`,
    },
  ];
  const activePanelDefinition =
    PANEL_DEFINITIONS.find((item) => item.id === panelView) ?? PANEL_DEFINITIONS[0];
  const mainControlPanels = MAIN_CONTROL_PANEL_IDS
    .map((id) => PANEL_DEFINITIONS.find((item) => item.id === id))
    .filter(Boolean) as PanelDefinition[];
  const currentPlayerViewLabel = !panelOpen
    ? "地图主场景"
    : managerDrawer?.kind === "npc-profile"
      ? "NPC 属性"
      : managerDrawer?.kind === "npc-dialog"
        ? "NPC 对话"
        : managerDrawer?.kind === "exchange-detail"
          ? "协作详情"
        : managerDrawer?.kind === "npc-bind"
          ? "NPC 绑定线程"
          : managerDrawer?.kind === "npc-skills"
            ? "NPC Skill 装配"
        : managerDrawer?.kind === "npc-create"
          ? "添加 NPC"
          : activePanelDefinition.label;
  const exchangeSectionNavItems = [
    { id: "overview", label: "总览与入口", railDetail: "一级总览与动作入口", meta: "1 级", icon: "总" },
    { id: "member-sync", label: "成员动态", railDetail: "只看真人账号共享动态", meta: "2 级", icon: "动" },
    { id: "dispatch", label: "平台派工", railDetail: "只看正式 AI / NPC 派工", meta: "2 级", icon: "派" },
    { id: "receipts", label: "回执结果", railDetail: "只看最小回执和最终回复", meta: "2 级", icon: "回" },
    { id: "thread-focus", label: "线程焦点", railDetail: "把协作现场和机房线程对齐", meta: "2 级", icon: "线" },
    { id: "advanced-proof", label: "高级证明", railDetail: "深层 proof 只保留摘要入口", meta: "2 级", icon: "证" },
  ] as const;
  const currentExchangeSectionMeta =
    exchangeSectionNavItems.find((item) => item.id === exchangeSectionFocusId) ?? exchangeSectionNavItems[0];

  function renderCollaborationPreviewCard(preview: AnyRecord | null, heading: string) {
    if (!preview) return null;
    const blockers = asArray(preview.blockers).map((item) => display(item, ""));
    const warnings = asArray(preview.warnings).map((item) => display(item, ""));
    const notes = asArray(preview.preview_notes).map((item) => display(item, ""));
    const ready = Boolean(preview.ready);
    const governance =
      preview.governance_preview && typeof preview.governance_preview === "object"
        ? (preview.governance_preview as AnyRecord)
        : null;
    const governanceWarnings = asArray(governance?.warnings).map((item) => display(item, "")).filter(Boolean);
    const riskLevel = text(governance?.risk_level, "");
    const riskLabel = riskLevel === "high" ? "高风险" : riskLevel === "medium" ? "需看护" : riskLevel ? "低风险" : "未评估";
    const governanceNeedsHumanReview = Boolean(governance?.requires_human_review);
    return (
      <div className={styles.noticeCard}>
        <div className={styles.listHead}>
          <strong>{heading}</strong>
          <span className={styles.stateBadge}>{ready ? "可正式发送" : "需要先处理"}</span>
        </div>
        <p>
          这一步只是预演，不会写入平台协作消息池。正式发送时会再次校验当前输入是否和这次预演一致，避免用户改过内容却误发旧指令。
        </p>
        <div className={styles.cardGridCompact}>
          <article className={styles.card}>
            <span>目标</span>
            <strong>{display(preview.recipient_label ?? preview.recipient_id, "未选择")}</strong>
            <p>{display(preview.message_type, "comment_message")}</p>
          </article>
          <article className={styles.card}>
            <span>同目标未收口</span>
            <strong>{`${asNumber(preview.pending_target_message_count) ?? 0} 条`}</strong>
            <p>建议先看最小回执和最终回复，再决定是否继续派工。</p>
          </article>
          <article className={styles.card}>
            <span>同类型历史</span>
            <strong>{`${asNumber(preview.recent_same_type_count) ?? 0} 条`}</strong>
            <p>{text(preview.next_step, ready ? "现在可以正式发送。" : "先处理阻塞。")}</p>
          </article>
        </div>
        {governance ? (
          <div className={styles.noticeCard} data-collab-governance-preview={text(preview.preview_key, heading)}>
            <div className={styles.listHead}>
              <strong>AI 协作治理预演</strong>
              <span className={styles.stateBadge}>{riskLabel}</span>
            </div>
            <p>{display(governance.execution_mode_label, "先预演，再决定是否正式发送。")}</p>
            {governanceNeedsHumanReview ? (
              <p className={styles.microCopy}>
                治理闸口会拦住直接派发：如果现在点正式发送，平台只会登记人工审核请求，不会把指令送进目标线程 inbox。
              </p>
            ) : null}
            <div className={styles.cardGridCompact}>
              <article className={styles.card}>
                <span>项目视角</span>
                <strong>{display(governance.project_profile_label, "纯软件")}</strong>
                <p>{`${display(governance.work_kind_label, "实现")} / ${display(governance.approval_label, "自动续推")}`}</p>
              </article>
              <article className={styles.card}>
                <span>预计 token</span>
                <strong>{`${asNumber(governance.estimated_tokens) ?? 0}`}</strong>
                <p>{display(governance.token_summary, "有界预算")}</p>
              </article>
              <article className={styles.card}>
                <span>执行边界</span>
                <strong>{governance.requires_human_review ? "需要人审" : "可执行"}</strong>
                <p>
                  {[
                    governance.readonly_first ? "先只读探针" : "可直接验证",
                    governance.should_simulate_first ? "仿真优先" : "无需强制仿真",
                  ].join(" / ")}
                </p>
              </article>
            </div>
            <div className={styles.chipRow}>
              <span className={styles.miniChip}>{display(governance.runaway_summary, "自动轮次受限")}</span>
              <span className={styles.miniChip}>{display(governance.efficiency_summary, "先探针再执行")}</span>
              <span className={styles.miniChip}>{display(governance.debug_summary, "AI 调试可用")}</span>
            </div>
            {governanceWarnings.length ? (
              <ul className={styles.list}>
                {governanceWarnings.map((item, index) => (
                  <li key={`collab-governance-warning-${heading}-${index + 1}`}>
                    <strong>{`治理提醒 ${index + 1}`}</strong>
                    <p>{item}</p>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {blockers.length ? (
          <>
            <div className={styles.listHead}>
              <strong>预演阻塞</strong>
            </div>
            <ul className={styles.list}>
              {blockers.map((item, index) => (
                <li key={`collab-preview-blocker-${heading}-${index + 1}`}>
                  <strong>{`阻塞 ${index + 1}`}</strong>
                  <p>{item}</p>
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {warnings.length ? (
          <>
            <div className={styles.listHead}>
              <strong>预演提醒</strong>
            </div>
            <ul className={styles.list}>
              {warnings.map((item, index) => (
                <li key={`collab-preview-warning-${heading}-${index + 1}`}>
                  <strong>{`提醒 ${index + 1}`}</strong>
                  <p>{item}</p>
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {notes.length ? (
          <div className={styles.chipRow}>
            {notes.map((item, index) => (
              <span key={`collab-preview-note-${heading}-${index + 1}`} className={styles.miniChip}>{item}</span>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  function collaborationPreviewNeedsHumanReview(preview: AnyRecord | null) {
    const governance =
      preview?.governance_preview && typeof preview.governance_preview === "object"
        ? (preview.governance_preview as AnyRecord)
        : null;
    return Boolean(governance?.requires_human_review);
  }

  const currentHumanSenderId = text(props.currentUser?.id ?? props.currentUser?.email, "");
  const currentHumanSenderLabel = display(props.currentUser?.name ?? props.currentUser?.email, "当前账号主角");
  const currentHumanSenderValue = currentHumanSenderId || currentHumanSenderLabel;

  function renderExchangePanel() {
    const commandTargetMap = new Map<string, { id: string; label: string; meta: string; providerLabel: string }>();
    const exchangeTargetMap = new Map<
      string,
      {
        threadId?: string;
        threadLabel?: string;
        computerNodeId?: string;
        seatId?: string;
        seatLabel?: string;
      }
    >();

    function rememberExchangeTarget(
      candidate: string,
      partial: {
        threadId?: string;
        threadLabel?: string;
        computerNodeId?: string;
        seatId?: string;
        seatLabel?: string;
      },
    ) {
      const key = text(candidate, "");
      if (!key) return;
      const normalizedKey = key.toLowerCase();
      const previous = exchangeTargetMap.get(normalizedKey) ?? {};
      exchangeTargetMap.set(normalizedKey, {
        ...previous,
        ...partial,
      });
    }

    allThreadCandidates.forEach((thread) => {
      const targetId = text(thread.id ?? thread.workstation_id, "");
      if (!targetId) return;
      if (adapterTargetIdSet.size && !adapterTargetIdSet.has(targetId.toLowerCase())) return;
      const providerLabel = platformProviderLabelFromThread(thread);
      const boundSeat = seatBySourceThreadId.get(targetId) ?? seatBySourceThreadId.get(targetId.toLowerCase()) ?? null;
      const boundSeatView = boundSeat ? resolveSeatViewForRecord(boundSeat, seatPayloadMap) : null;
      const boundSeatId = boundSeat ? preferredSeatRouteId(boundSeat, boundSeatView) : "";
      const threadLabel = display(thread.name ?? thread.label, targetId);
      const computerNodeId = text(thread.computer_node_id ?? thread.computer_node, "");
      commandTargetMap.set(targetId, {
        id: targetId,
        label: threadLabel,
        meta: `线程 / ${display(computerNodeId, "未绑定电脑")}`,
        providerLabel,
      });
      threadRouteKeys(thread).forEach((key) =>
        rememberExchangeTarget(key, {
          threadId: targetId,
          threadLabel,
          computerNodeId,
          seatId: boundSeatId || undefined,
          seatLabel: boundSeat ? text(boundSeat.name, "") : undefined,
        }),
      );
    });
    codexSeats.forEach((seat) => {
      const targetId = text(seat.id ?? seat.workstation_id ?? seat.config_id, "");
      if (!targetId || commandTargetMap.has(targetId)) return;
      if (adapterTargetIdSet.size && !adapterTargetIdSet.has(targetId.toLowerCase())) return;
      const providerLabel = platformProviderLabelFromSeat(seat);
      const seatView = resolveSeatViewForRecord(seat, seatPayloadMap);
      const preferredSeatId = preferredSeatRouteId(seat, seatView);
      const sourceThreadId = text(seat.source_workstation_id ?? seat.metadata?.source_workstation_id, "");
      const seatLabel = display(seat.name ?? seat.label, targetId);
      const computerNodeId = text(seat.computer_node_id ?? seat.computer_node, "");
      const machineRoomTargetId = sourceThreadId || targetId || preferredSeatId;
      commandTargetMap.set(targetId, {
        id: targetId,
        label: seatLabel,
        meta: `NPC / ${display(computerNodeId, "未绑定电脑")}`,
        providerLabel,
      });
      seatRouteKeys(seat).forEach((key) =>
        rememberExchangeTarget(key, {
          threadId: machineRoomTargetId || undefined,
          threadLabel: sourceThreadId ? undefined : seatLabel,
          computerNodeId,
          seatId: preferredSeatId || undefined,
          seatLabel,
        }),
      );
    });

    function resolveExchangeTarget(candidate: string) {
      const key = text(candidate, "");
      if (!key) return null;
      return exchangeTargetMap.get(key.toLowerCase()) ?? null;
    }

    codexSeats.forEach((seat) => {
      const seatView = resolveSeatViewForRecord(seat, seatPayloadMap);
      const preferredSeatId = preferredSeatRouteId(seat, seatView);
      const seatLabel = display(seat.name ?? seat.label, preferredSeatId || "NPC");
      rememberExchangeTarget(preferredSeatId, {
        seatId: preferredSeatId || undefined,
        seatLabel,
      });
    });
    const commandTargets = Array.from(commandTargetMap.values());
    const relayFirstDefaultTarget =
      commandTargets.find((target) => {
        const label = `${target.providerLabel} ${target.label} ${target.id}`.toLowerCase();
        return label.includes("codex");
      }) ?? commandTargets[0] ?? null;
    const relaySecondDefaultTarget =
      commandTargets.find((target) => {
        const label = `${target.providerLabel} ${target.label} ${target.id}`.toLowerCase();
        return target.id !== relayFirstDefaultTarget?.id && label.includes("claude");
      }) ??
      commandTargets.find((target) => target.id !== relayFirstDefaultTarget?.id) ??
      relayFirstDefaultTarget;
    const platformCommandMessages = sortedByUpdatedAt(
      props.collaborationMessages.filter((message) => text(message.message_type, "").toLowerCase() === "agent_command"),
    );
    const recentPlatformCommands = platformCommandMessages.slice(0, 6);
    const recentProjectSyncNotes = sortedByUpdatedAt(
      props.collaborationMessages.filter((message) => {
        const type = text(message.message_type, "").toLowerCase();
        const recipientType = text(message.recipient_type, "").toLowerCase();
        const recipientId = text(message.recipient_id, "");
        return (
          ["project_sync_note", "status_update"].includes(type) &&
          recipientType === "project" &&
          recipientId === projectId &&
          text(message.sender_type, "").toLowerCase() === "human"
        );
      }),
    ).slice(0, 6);
    const recentRelayStatusMessages = (() => {
      const latestByRelay = new Map<string, AnyRecord>();
      sortedByUpdatedAt(
        props.collaborationMessages.filter((message) => {
          const type = text(message.message_type, "").toLowerCase();
          const recipientType = text(message.recipient_type, "").toLowerCase();
          const recipientId = text(message.recipient_id, "");
          return type === "relay_status" && recipientType === "project" && recipientId === projectId;
        }),
      ).forEach((message) => {
        const body = text(message.body, "");
        const relayId = body.match(/relay_id:\s*([^\s]+)/i)?.[1] ?? "";
        const relayKey = relayId || text(message.title, text(message.id, ""));
        if (!relayKey) return;
        const existing = latestByRelay.get(relayKey);
        if (existing) {
          const existingAt = latestMessageAt(existing);
          const nextAt = latestMessageAt(message);
          const existingRank = relayStatusRank(existing.status);
          const nextRank = relayStatusRank(message.status);
          if (nextAt < existingAt || (nextAt === existingAt && nextRank <= existingRank)) return;
        }
        latestByRelay.set(relayKey, message);
      });
      return [...latestByRelay.values()].slice(0, 3);
    })();
    const platformReceiptMessages = sortedByUpdatedAt(
      props.collaborationMessages.filter((message) =>
        ["agent_ack", "agent_result", "requirement_progress_ack", "requirement_final_reply"].includes(
          text(message.message_type, "").toLowerCase(),
        ),
      ),
    );
    const normalizedExchangeFocusRouteKeys = exchangeFocusRouteKeys.map((value) => value.toLowerCase());
    const focusedCommandTitles = uniqueStrings(
      recentPlatformCommands.flatMap((message) => {
        const targetId = text(message.recipient_id, "");
        const targetAliases = uniqueStrings([
          targetId,
          commandTargetMap.get(targetId)?.label,
        ]).map((value) => value.toLowerCase());
        const senderAliases = uniqueStrings([
          text(message.sender_id ?? message.agent_id, ""),
          actorLabel(message, display),
        ]).map((value) => value.toLowerCase());
        return routeAliasesMatch(senderAliases, normalizedExchangeFocusRouteKeys) || routeAliasesMatch(targetAliases, normalizedExchangeFocusRouteKeys)
          ? [text(message.title, "")]
          : [];
      }),
    );
    const focusedProjectSyncCount = recentProjectSyncNotes.filter((message) => {
      const senderAliases = uniqueStrings([
        text(message.sender_id ?? message.agent_id, ""),
        actorLabel(message, display),
      ]).map((value) => value.toLowerCase());
      return routeAliasesMatch(senderAliases, normalizedExchangeFocusRouteKeys);
    }).length;
    const focusedCommandCount = focusedCommandTitles.length;
    const focusedReceiptCount = platformReceiptMessages.filter((message) =>
      focusedCommandTitles.includes(text(message.title, "")),
    ).length;
    const receiptRoundMap = new Map<
      string,
      {
        title: string;
        messages: AnyRecord[];
        commandMessage: AnyRecord | null;
        latestAt: number;
      }
    >();
    platformReceiptMessages.forEach((message, index) => {
      const title = safeDisplayTitle(message.title ?? message.body, `未命名回执 ${index + 1}`);
      const key = title.toLowerCase();
      const previous = receiptRoundMap.get(key) ?? {
        title,
        messages: [] as AnyRecord[],
        commandMessage: null as AnyRecord | null,
        latestAt: 0,
      };
      previous.messages.push(message);
      previous.latestAt = Math.max(previous.latestAt, latestMessageAt(message));
      receiptRoundMap.set(key, previous);
    });
    platformCommandMessages.forEach((message) => {
      const title = safeDisplayTitle(message.title ?? message.body, "");
      if (!title) return;
      const key = title.toLowerCase();
      const previous = receiptRoundMap.get(key);
      if (!previous) return;
      if (!previous.commandMessage) {
        previous.commandMessage = message;
      }
      previous.latestAt = Math.max(previous.latestAt, latestMessageAt(message));
    });
    const receiptRoundItems = Array.from(receiptRoundMap.values())
      .map((round, index) => {
        const sortedMessages = sortedByUpdatedAt(round.messages);
        const latestAck =
          sortedMessages.find((message) =>
            ["agent_ack", "requirement_progress_ack", "runner_ack"].includes(text(message.message_type, "").toLowerCase()),
          ) ?? null;
        const latestFinal =
          sortedMessages.find((message) =>
            ["agent_result", "requirement_final_reply", "runner_result"].includes(text(message.message_type, "").toLowerCase()),
          ) ?? null;
        const latestMessage = latestFinal ?? latestAck ?? sortedMessages[0] ?? null;
        const senderLabel = latestMessage ? actorLabel(latestMessage, display) : "未知来源";
        const commandTargetId = text(round.commandMessage?.recipient_id, "");
        const receiptTargetId = text(latestMessage?.sender_id ?? latestMessage?.agent_id, "");
        const targetLink = resolveExchangeTarget(receiptTargetId) ?? resolveExchangeTarget(commandTargetId);
        const validationProbe = [
          round.title,
          round.commandMessage?.body,
          latestAck?.body,
          latestFinal?.body,
        ].join("\n");
        const isValidationNoise = /验收|验证|validation|user-flow|链路验收|测试/i.test(validationProbe);
        const hasFinal = Boolean(latestFinal && isDoneStatus(latestFinal.status));
        const hasAck = Boolean(latestAck);
        return {
          id: `receipt-round-${index + 1}-${round.title}`,
          title: round.title,
          commandMessage: round.commandMessage,
          latestAck,
          latestFinal,
          latestMessage,
          hasAck,
          hasFinal,
          isValidationNoise,
          senderLabel,
          commandTargetId,
          receiptTargetId,
          targetLink,
          statusLabel: hasFinal ? "已收口" : hasAck ? "已最小回执" : "等待回执",
          bodyPreview: shortText(latestFinal?.body ?? latestAck?.body ?? latestMessage?.body, "没有正文", 112),
          latestAt: round.latestAt,
          receiptCount: sortedMessages.length,
          focused: focusedCommandTitles.includes(round.title),
        };
      })
      .filter((item) => item.latestMessage)
      .sort((left, right) => right.latestAt - left.latestAt);
    const visibleReceiptRoundItems = receiptRoundItems
      .filter((item) => {
        if (exchangeReceiptFilter === "open") return !item.hasFinal;
        if (exchangeReceiptFilter === "finals") return item.hasFinal;
        if (exchangeReceiptFilter === "clean") return !item.isValidationNoise;
        return true;
      })
      .slice(0, 8);
    const exchangeReceiptFilterItems: {
      id: ExchangeReceiptFilter;
      label: string;
      detail: string;
      count: number;
    }[] = [
      { id: "all", label: "全部轮次", detail: "按派工标题聚合", count: receiptRoundItems.length },
      { id: "open", label: "待收口", detail: "有回执但还没最终回复", count: receiptRoundItems.filter((item) => !item.hasFinal).length },
      { id: "finals", label: "已收口", detail: "已有最终回复", count: receiptRoundItems.filter((item) => item.hasFinal).length },
      { id: "clean", label: "隐藏验收", detail: "先看真实业务协作", count: receiptRoundItems.filter((item) => !item.isValidationNoise).length },
    ];
    const exchangeFocusActive = Boolean(exchangeFocusLabel && normalizedExchangeFocusRouteKeys.length);
    const workstationExchangeFocusFeed = machineRoomVisibleWorkstations
      .map((thread, index) => {
        const threadId = text(thread.id ?? thread.workstation_id ?? thread.config_id, "");
        if (!threadId) return null;
        const activity = buildWorkstationActivitySummary(thread, props.collaborationMessages);
        const isSeatBackedWorkstation = isNpcSeatWorkstation(thread);
        const boundSeat = isSeatBackedWorkstation
          ? thread
          : seatBySourceThreadId.get(threadId) ?? seatBySourceThreadId.get(threadId.toLowerCase()) ?? null;
        const boundSeatView = boundSeat ? resolveSeatViewForRecord(boundSeat, seatPayloadMap) : null;
        const preferredSeatId = boundSeat ? preferredSeatRouteId(boundSeat, boundSeatView) : "";
        const latestAt = Math.max(
          new Date(text(activity.latestCommandAt, "1970-01-01")).getTime(),
          new Date(text(activity.latestAckAt, "1970-01-01")).getTime(),
          new Date(text(activity.latestFinalReplyAt, "1970-01-01")).getTime(),
          new Date(text(activity.latestSignalAt, "1970-01-01")).getTime(),
        );
        if (!Number.isFinite(latestAt) || latestAt <= 0) return null;
        const targetLabel = isSeatBackedWorkstation
          ? `${display(thread.name, threadId || `执行位 ${index + 1}`)} / NPC 工位`
          : boundSeat?.name
            ? `${display(thread.name, threadId)} / ${boundSeat.name}`
            : display(thread.name, threadId || `线程 ${index + 1}`);
        const primaryLabel = activity.latestFinalReplyLabel || activity.latestAckLabel || activity.latestCommandLabel || "最近协作信号";
        const primaryBody =
          activity.latestFinalReplyBody || activity.latestAckBody || activity.latestCommandBody || "这条线程最近有真实协作信号。";
        const routeKeys = uniqueStrings([
          ...workstationRouteKeys(thread),
          ...seatRouteKeys(thread),
          boundSeat?.name,
          preferredSeatId,
          boundSeat?.source_workstation_id,
          boundSeat?.workstation_id,
        ]).map((value) => value.toLowerCase());
        return {
          id: `workstation-focus-${threadId}`,
          threadId,
          routeKeys,
          targetLabel,
          providerLabel: platformProviderLabelFromThread(thread),
          preferredSeatId,
          computerNodeLabel: display(thread.computer_node_id ?? thread.computer_node, "未绑定电脑"),
          primaryLabel,
          primaryBody,
          latestCommandTypeLabel: activity.latestCommandTypeLabel,
          latestCommandLabel: activity.latestCommandLabel,
          latestAckLabel: activity.latestAckLabel,
          latestFinalReplyLabel: activity.latestFinalReplyLabel,
          freshnessLabel: activity.activityFreshnessLabel,
          stale: activity.activityFreshnessStale,
          latestAt,
          targetKind: isSeatBackedWorkstation ? "seat" : "thread",
        };
      })
      .filter((item): item is NonNullable<typeof item> => Boolean(item))
      .sort((left, right) => right.latestAt - left.latestAt);
    const exchangePreview =
      text(collaborationPreview?.preview_key, "") === "exchange-command" ? collaborationPreview : null;
    const exchangePreviewReady = Boolean(exchangePreview?.ready);
    const exchangePreviewNeedsHumanReview = collaborationPreviewNeedsHumanReview(exchangePreview);
    const exchangeRequestDisabled = !commandTargets.length || !exchangePreviewReady;
    const visibleExchangeComposerMode = exchangeComposerMode ?? (exchangePreview ? "dispatch" : null);
    const exchangeSnapshotCards = summaryCards.map((card) => ({
      ...card,
      body:
        card.id === "recommended-action"
          ? shortText(card.body, "暂无推荐动作", 64)
          : card.id === "current-owner"
            ? shortText(card.body, "暂无当前负责人", 58)
            : card.body,
      meta: shortText(
        card.meta,
        "",
        card.id === "final-replies" ? 88 : 68,
      ),
    }));

    return (
      <div className={styles.panelStack}>
        {exchangeSectionFocusId === "overview" ? (
          <section
            className={`${styles.exchangeLevelSection} ${styles.exchangeOverviewSection}`}
            data-exchange-level="1"
            data-exchange-section="overview"
            data-exchange-section-active="true"
          >
            <div className={styles.exchangeLevelHead}>
              <span className={styles.exchangeLevelTag}>一级</span>
              <div>
                <strong>协作现场总览与入口</strong>
                <p className={styles.microCopy}>一级只保留总览和动作入口。具体动态、派工、回执和 proof 全都下沉到左侧分区栏对应的二级页面。</p>
              </div>
            </div>

            <div className={`${styles.cardGridCompact} ${styles.exchangeSnapshotGrid}`}>
              {exchangeSnapshotCards.map((card) => (
                <article key={card.id} className={styles.card} data-exchange-overview-card={card.id}>
                  <span>{card.title}</span>
                  <strong>{card.body}</strong>
                  <p>{card.meta}</p>
                </article>
              ))}
            </div>
            <p className={styles.microCopy}>
              总览只保留短结论；完整排队诊断请进“线程焦点”，proof 和跨区校验请进“高级证明”。
            </p>

            {runnerQueueAttention ? (
              <div
                className={`${styles.noticeCard} ${styles.featureCardFocused}`}
                data-exchange-runner-queue-alert="true"
                data-exchange-runner-queue-count={String(queuedCollaborationCommandCount)}
                data-exchange-runner-ready-count={String(watchReadyNodes.length)}
                data-exchange-runner-blocked-count={String(watchBlockedNodes.length)}
                data-exchange-runner-hard-blocker={runnerQueueBlocker ? "true" : "false"}
              >
                <div className={styles.exchangeLevelHead}>
                  <span className={styles.exchangeLevelTag}>{runnerQueueBlocker ? "接单阻塞" : "接单提醒"}</span>
                  <div>
                    <strong>{runnerQueueAttentionTitle}</strong>
                    <p className={styles.microCopy}>{runnerQueueAttentionBody}</p>
                  </div>
                </div>
                <div className={styles.inlineActions}>
                  <button type="button" onClick={() => openBackpackPanel("computers")}>
                    {runnerQueueBlocker ? "去恢复电脑接单" : "去查看剩余阻塞电脑"}
                  </button>
                  <button type="button" className={styles.ghostButton} onClick={() => focusExchangeSection("thread-focus")}>
                    查看线程焦点
                  </button>
                </div>
              </div>
            ) : null}

            {staleQueuedCommandCount ? (
              <div
                className={`${styles.noticeCard} ${styles.featureCardFocused}`}
                data-exchange-stale-queue-guidance="true"
                data-exchange-stale-queue-count={String(staleQueuedCommandCount)}
                data-exchange-oldest-queue-age={String(oldestQueuedCollaborationCommand?.ageMinutes ?? "")}
              >
                <div className={styles.exchangeLevelHead}>
                  <span className={styles.exchangeLevelTag}>旧队列</span>
                  <div>
                    <strong>{`${staleQueuedCommandCount} 条旧指令需要人工处理，不自动删除`}</strong>
                    <p className={styles.microCopy}>
                      {oldestQueuedCollaborationCommand
                        ? `最久等待 ${oldestQueuedCollaborationCommand.ageLabel}，代表项：${oldestQueuedCollaborationCommand.target} / ${oldestQueuedCollaborationCommand.title}。先恢复接单电脑，再判断是重派、归档还是保留。`
                        : "先恢复接单电脑，再判断旧队列是重派、归档还是保留。"}
                    </p>
                  </div>
                </div>
                <div className={styles.cardGridCompact}>
                  <article className={styles.card}>
                    <span>队列判断</span>
                    <strong>{oldestQueuedCollaborationCommand?.stateLabel ?? "等待接单"}</strong>
                    <p>{oldestQueuedCollaborationCommand ? `${oldestQueuedCollaborationCommand.typeLabel} / ${formatStamp(oldestQueuedCollaborationCommand.message.created_at ?? oldestQueuedCollaborationCommand.message.updated_at)}` : "暂无最旧项"}</p>
                  </article>
                  <article className={styles.card}>
                    <span>安全边界</span>
                    <strong>先看，不自动重派</strong>
                    <p>旧队列可能是远端电脑断线、线程未绑定、或人审未通过，平台不能静默重复消耗 token。</p>
                  </article>
                </div>
                <div className={styles.inlineActions}>
                  {oldestQueuedCollaborationCommand ? (
                    <button
                      type="button"
                      data-exchange-stale-queue-open-oldest="true"
                      onClick={() => openManagerDrawer("exchange-detail", `queue:${text(oldestQueuedCollaborationCommand.message.id, "")}`)}
                    >
                      处理最旧项
                    </button>
                  ) : null}
                  <button type="button" onClick={() => focusExchangeSection("thread-focus")}>
                    查看线程焦点
                  </button>
                  <button type="button" className={styles.ghostButton} onClick={() => focusExchangeSection("dispatch")}>
                    去派工区核对
                  </button>
                  <button type="button" className={styles.ghostButton} onClick={() => openBackpackPanel("computers")}>
                    恢复接单电脑
                  </button>
                </div>
              </div>
            ) : null}

            {humanReviewAlert ? (
              <div
                className={`${styles.noticeCard} ${styles.featureCardFocused}`}
                data-human-review-alert="true"
              >
                <div className={styles.exchangeLevelHead}>
                  <span className={styles.exchangeLevelTag}>人工审核</span>
                  <div>
                    <strong>{`有 ${humanReviewAlert.count} 条事项需要先人审`}</strong>
                    <p className={styles.microCopy}>{humanReviewAlert.detail}</p>
                  </div>
                </div>
                <div className={styles.cardGridCompact}>
                  <article className={styles.card}>
                    <span>审核对象</span>
                    <strong>{humanReviewAlert.title}</strong>
                    <p>{humanReviewAlert.state}</p>
                  </article>
                  <article className={styles.card}>
                    <span>当前负责人</span>
                    <strong>{humanReviewAlert.owner}</strong>
                    <p>人工给出通过、驳回或补充要求后，再允许 AI 继续推进。</p>
                  </article>
                </div>
                {pendingHumanReviewMessages.length ? (
                  <div className={styles.panelStack} data-human-review-queue="true">
                    {pendingHumanReviewMessages.slice(0, 3).map((message) => (
                      <article key={text(message.id, text(message.title, "human-review"))} className={styles.card} data-human-review-message={text(message.id, "")}>
                        <span>{`待处理 · ${formatStamp(message.created_at ?? message.updated_at)}`}</span>
                        <strong>{safeDisplayTitle(message.title, "人工审核请求")}</strong>
                        <p>{shortText(message.body, "没有审核正文", 180)}</p>
                        <form action={handleCollaborationHumanReview} className={styles.inlineActions}>
                          <input type="hidden" name="project_id" value={projectId} />
                          <input type="hidden" name="review_message_id" value={text(message.id, "")} />
                          <input type="hidden" name="return_to" value={buildExchangeSurfaceHref("overview")} />
                          <button type="submit" name="decision" value="readonly_probe" data-loading-label="正在登记只读探针">
                            通过：只读探针
                          </button>
                          <button type="submit" name="decision" value="simulation" data-loading-label="正在登记仿真验证">
                            通过：先仿真
                          </button>
                          <button type="submit" name="decision" value="formal_execute" data-loading-label="正在登记正式执行">
                            通过：正式执行
                          </button>
                          <button type="submit" name="decision" value="reject" data-loading-label="正在驳回人审请求">
                            驳回
                          </button>
                        </form>
                      </article>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            <details className={styles.exchangeHelpFold} data-exchange-overview-primer="true">
              <summary className={styles.exchangeHelpSummary}>
                <span className={styles.exchangeLevelTag}>怎么用</span>
                <strong>协作现场只按 1 / 2 / 3 级走</strong>
                <small>一级看结论和入口，二级按类型看列表，三级再打开单条详情。</small>
              </summary>
              <div className={`${styles.exchangeStepStrip} ${styles.exchangeHelpBody}`}>
                <article>
                  <span>1</span>
                  <strong>先看回执</strong>
                  <p>确认目标 AI 有没有最小回执和最终回复。</p>
                </article>
                <article>
                  <span>2</span>
                  <strong>再看派工</strong>
                  <p>只在需要追踪谁接了什么活时进入派工区。</p>
                </article>
                <article>
                  <span>3</span>
                  <strong>最后发新指令</strong>
                  <p>只有确定不是重复催办时，才展开动作台发新任务。</p>
                </article>
              </div>
            </details>

            <details className={styles.exchangeHelpFold} data-ai-collab-contract="true">
              <summary className={styles.exchangeHelpSummary}>
                <span className={styles.exchangeLevelTag}>AI 协作契约</span>
                <strong>{`10+ 线程协作按“需求表 -> 派单 -> 回执 -> 审核 -> 最终回复”流转`}</strong>
                <small>所有 NPC 默认带“AI 必读需求表”固定 Skill；高风险事项先停到人审。</small>
              </summary>
              <p className={styles.microCopy}>
                开工前先读 docs/ai-requirements/ai-required-requirements-ledger.md，
                明确提需求者、被提需求者、人工审核边界、一次性/心跳模式和完成后回给谁。
              </p>
              <div className={`${styles.exchangeStepStrip} ${styles.exchangeHelpBody}`}>
                <article>
                  <span>需</span>
                  <strong>需求先登记</strong>
                  <p>AI 给 AI 提需求也要写清楚双方和验收标准。</p>
                </article>
                <article>
                  <span>审</span>
                  <strong>人审先停下</strong>
                  <p>高风险或不明确事项直接怼到首页，等待人给结论。</p>
                </article>
                <article>
                  <span>回</span>
                  <strong>完成回给提出者</strong>
                  <p>完成后先回原提需求者，再进入最终回复池；接力必须生成下一条需求。</p>
                </article>
              </div>
            </details>

            <div className={styles.exchangeSectionNav} data-exchange-overview-section-nav="true">
              <div className={styles.exchangeSectionNavHead}>
                <strong>二级分区入口</strong>
                <p className={styles.microCopy}>点下面任一区域进入对应二级页；总览页不再把全部内容堆在一起。</p>
              </div>
              <div className={styles.exchangeSectionNavRow}>
                {exchangeSectionNavItems
                  .filter((item) => item.id !== "overview")
                  .map((item) => (
                    <Link
                      key={`exchange-overview-nav-${item.id}`}
                      href={buildExchangeSurfaceHref(item.id)}
                      className={styles.exchangeSectionNavButton}
                      data-exchange-overview-nav={item.id}
                    >
                      <span>{`${item.icon} ${item.label}`}</span>
                      <small>{item.railDetail}</small>
                    </Link>
                  ))}
              </div>
            </div>

            {exchangeFocusActive ? (
              <div
                className={`${styles.noticeCard} ${styles.featureCardFocused}`}
                data-exchange-focus-banner="true"
                data-exchange-focus-label={exchangeFocusLabel}
              >
                <strong>{`正在查看 ${exchangeFocusLabel} 的协作现场`}</strong>
                <p>{`已对齐 ${focusedProjectSyncCount} 条共享动态、${focusedCommandCount} 条平台派工和 ${focusedReceiptCount} 条相关回执。`}</p>
                <div className={styles.inlineActions}>
                  <button type="button" className={styles.ghostButton} onClick={clearExchangeFocus}>
                    取消聚焦
                  </button>
                </div>
              </div>
            ) : null}

            {recentRelayStatusMessages.length ? (
              <div className={styles.noticeCard} data-exchange-relay-status-list="true">
                <div className={styles.exchangeLevelHead}>
                  <span className={styles.exchangeLevelTag}>接力状态</span>
                  <div>
                    <strong>最近平台多 NPC 接力</strong>
                    <p className={styles.microCopy}>这里显示平台编排器的正式状态；失败时从动作台重试，完成后去回执区看最终交付。</p>
                  </div>
                </div>
                <div className={`${styles.cardGridCompact} ${styles.exchangeSnapshotGrid}`}>
                  {recentRelayStatusMessages.map((message, index) => {
                    const relay = relayStatusView(message);
                    return (
                      <article
                        key={`relay-status-${text(message.id, String(index))}`}
                        className={`${styles.card} ${styles.relayStatusCard}`}
                        data-exchange-relay-status-card={relay.status}
                      >
                        <div className={styles.relayStatusCardHead}>
                          <span className={styles.stateBadge}>{relay.statusLabel}</span>
                          <small>{relay.relayId}</small>
                        </div>
                        <strong>{safeDisplayTitle(relay.title, "平台接力状态")}</strong>
                        <p>{shortText(relay.objective, "等待平台编排器更新目标", 96)}</p>
                        <div className={styles.relayStatusSteps}>
                          {relay.steps.map((step) => (
                            <div key={`${relay.relayId}-${step.label}`} className={styles.relayStatusStep} data-relay-step-state={step.state}>
                              <span>{step.label}</span>
                              <p>{step.detail}</p>
                            </div>
                          ))}
                        </div>
                        <p className={styles.microCopy}>{relay.note}</p>
                        <div className={styles.chipRow}>
                          <span className={styles.miniChip}>{relay.nextAction}</span>
                        </div>
                      </article>
                    );
                  })}
                </div>
                <div className={styles.inlineActions}>
                  <Link href={buildExchangeSurfaceHref("receipts")} className={styles.ghostButton}>
                    查看回执结果
                  </Link>
                  <Link href={buildExchangeSurfaceHref("overview", "relay")} className={styles.ghostButton}>
                    打开接力动作台
                  </Link>
                </div>
              </div>
            ) : null}

            <div className={styles.exchangeActionDock} data-exchange-action-dock="true">
              <Link
                href={buildExchangeSurfaceHref(
                  "overview",
                  visibleExchangeComposerMode === "sync" ? null : "sync",
                )}
                className={`${styles.exchangeActionCard} ${visibleExchangeComposerMode === "sync" ? styles.exchangeActionCardActive : ""}`}
                data-exchange-composer-toggle="sync"
              >
                <span className={styles.badge}>共享动态</span>
                <strong>广播给项目成员</strong>
                <p>只给当前项目里的真人主角同步状态，不混进 AI 派工。</p>
              </Link>
              <Link
                href={buildExchangeSurfaceHref(
                  "overview",
                  visibleExchangeComposerMode === "dispatch" ? null : "dispatch",
                )}
                className={`${styles.exchangeActionCard} ${visibleExchangeComposerMode === "dispatch" ? styles.exchangeActionCardActive : ""}`}
                data-exchange-composer-toggle="dispatch"
              >
                <span className={styles.badge}>AI 派工</span>
                <strong>下发给线程或 NPC</strong>
                <p>只在你需要派工时展开，避免一级首页先被大表单占满。</p>
              </Link>
              <Link
                href={buildExchangeSurfaceHref(
                  "overview",
                  visibleExchangeComposerMode === "relay" ? null : "relay",
                )}
                className={`${styles.exchangeActionCard} ${visibleExchangeComposerMode === "relay" ? styles.exchangeActionCardActive : ""}`}
                data-exchange-composer-toggle="relay"
              >
                <span className={styles.badge}>多 NPC 接力</span>
                <strong>一个目标拆给两位 AI</strong>
                <p>平台先派第一棒收集/拆解，再把结果转给第二棒完成交付，回执统一进结果区。</p>
              </Link>
            </div>

            {visibleExchangeComposerMode === "sync" ? (
              <form action={submitCollaborationMessage} className={styles.skillManagerForm} data-project-sync-form="1">
                <div className={styles.exchangeComposerHead}>
                  <div>
                    <strong>广播项目成员协作状态</strong>
                    <p className={styles.microCopy}>这条动态只会给同项目真人主角看，用来交接、提醒和多人联机同步。</p>
                  </div>
                  <Link href={buildExchangeSurfaceHref("overview")} className={styles.ghostButton}>
                    收起动作台
                  </Link>
                </div>
                <input type="hidden" name="project_id" value={projectId} />
                <input type="hidden" name="message_type" value="project_sync_note" />
                <input type="hidden" name="sender_type" value="human" />
                <input type="hidden" name="sender_id" value={currentHumanSenderValue} />
                <input type="hidden" name="recipient_type" value="project" />
                <input type="hidden" name="recipient_id" value={projectId} />
                <input type="hidden" name="status" value="open" />
                <input type="hidden" name="return_to" value={exchangePanelReturnPath} />
                <div className={styles.skillManagerGrid}>
                  <label className={styles.fieldLabel}>
                    <span>协作标题</span>
                    <input name="title" placeholder="例如：主房协作更新 / 我先接前端" required />
                  </label>
                  <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                    <span>共享动态</span>
                    <textarea
                      name="body"
                      placeholder="告诉项目里的其他主角：你现在在做什么、下一步是什么、需要谁接手。"
                      required
                    />
                  </label>
                </div>
                <div className={styles.inlineActions}>
                  <button type="submit" data-project-sync-submit-button="1" data-loading-label="正在广播协作状态">
                    广播到项目协作池
                  </button>
                </div>
                <p className={styles.microCopy}>
                  这条动态会对当前项目已接纳的成员主角可见，但不会跨项目扩散，也不会替代 AI 的最小回执和最终回复链。
                </p>
              </form>
            ) : null}

            {visibleExchangeComposerMode === "dispatch" ? (
              <form action={submitCollaborationMessage} className={styles.skillManagerForm} data-exchange-command-form="1">
                <div className={styles.exchangeComposerHead}>
                  <div>
                    <strong>下发协作指令</strong>
                    <p className={styles.microCopy}>从用户视角直接指定某个线程或 NPC 做事；平台记录统一消息，后续由 Codex、Claude、Qwen 等适配器领取执行。</p>
                  </div>
                  <Link href={buildExchangeSurfaceHref("overview")} className={styles.ghostButton}>
                    收起动作台
                  </Link>
                </div>
                {renderCollaborationPreviewCard(exchangePreview, "最近一次总派工预演")}
                <input type="hidden" name="project_id" value={projectId} />
                <input type="hidden" name="message_type" value="agent_command" />
                <input type="hidden" name="sender_type" value="human" />
                <input type="hidden" name="sender_id" value={currentHumanSenderValue} />
                <input type="hidden" name="recipient_type" value="workstation" />
                <input type="hidden" name="status" value="queued" />
                <input type="hidden" name="return_to" value={exchangePanelReturnPath} />
                <input type="hidden" name="preview_key" value="exchange-command" />
                <input type="hidden" name="enforce_preview" value="1" />
                <input type="hidden" name="required_preview_signature" value={text(exchangePreview?.preview_signature, "")} />
                <input type="hidden" name="required_preview_ready" value={exchangePreviewReady ? "1" : ""} />
                <div className={styles.skillManagerGrid}>
                  <label className={styles.fieldLabel}>
                    <span>目标线程 / NPC</span>
                    <select name="recipient_id" className={styles.select} defaultValue={commandTargets[0]?.id ?? ""}>
                      {commandTargets.length ? (
                        commandTargets.map((target) => (
                          <option key={`command-target-${target.id}`} value={target.id}>
                            {`${target.label} · ${target.providerLabel} · ${target.meta}`}
                          </option>
                        ))
                      ) : (
                        <option value="">先登记线程或创建 NPC</option>
                      )}
                    </select>
                  </label>
                  <label className={styles.fieldLabel}>
                    <span>标题</span>
                    <input name="title" placeholder="例如：协作写作：资料收集" required />
                  </label>
                  <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                    <span>指令正文</span>
                    <textarea
                      name="body"
                      placeholder="告诉目标 AI 做什么、参考什么、完成后怎么回执。"
                      required
                    />
                  </label>
                </div>
                <div className={styles.inlineActions}>
                  <button
                    type="submit"
                    formAction={previewCollaborationMessage}
                    disabled={!commandTargets.length}
                    data-loading-label="正在预演协作指令"
                  >
                    先预演协作指令
                  </button>
                  <button type="submit" disabled={exchangeRequestDisabled} data-loading-label="正在登记协作指令">
                    {exchangePreviewNeedsHumanReview ? "登记人工审核" : "正式发送到协作池"}
                  </button>
                </div>
                <p className={styles.microCopy}>
                  先预演后，正式发送按钮才会亮。若治理预演显示需要人审，点击后只会登记审核请求，不会派给远端线程。
                </p>
              </form>
            ) : null}

            {visibleExchangeComposerMode === "relay" ? (
              <form action={startNpcRelayCollaboration} className={styles.skillManagerForm} data-exchange-relay-form="1">
                <div className={styles.exchangeComposerHead}>
                  <div>
                    <strong>平台多 NPC 接力</strong>
                    <p className={styles.microCopy}>
                      从用户视角只填一个目标；平台会先派第一棒，再把第一棒最终回复转给第二棒，最后统一回到回执结果区。
                    </p>
                  </div>
                  <Link href={buildExchangeSurfaceHref("overview")} className={styles.ghostButton}>
                    收起动作台
                  </Link>
                </div>
                <input type="hidden" name="project_id" value={projectId} />
                <input type="hidden" name="return_to" value={buildExchangeSurfaceHref("receipts")} />
                <div className={styles.skillManagerGrid}>
                  <label className={styles.fieldLabel}>
                    <span>第一棒：资料 / 拆解</span>
                    <select
                      name="first_recipient_id"
                      className={styles.select}
                      defaultValue={relayFirstDefaultTarget?.id ?? ""}
                    >
                      {commandTargets.length ? (
                        commandTargets.map((target) => (
                          <option key={`relay-first-${target.id}`} value={target.id}>
                            {`${target.label} · ${target.providerLabel} · ${target.meta}`}
                          </option>
                        ))
                      ) : (
                        <option value="">先登记线程或创建 NPC</option>
                      )}
                    </select>
                  </label>
                  <label className={styles.fieldLabel}>
                    <span>第二棒：成稿 / 校验</span>
                    <select
                      name="second_recipient_id"
                      className={styles.select}
                      defaultValue={relaySecondDefaultTarget?.id ?? ""}
                    >
                      {commandTargets.length ? (
                        commandTargets.map((target) => (
                          <option key={`relay-second-${target.id}`} value={target.id}>
                            {`${target.label} · ${target.providerLabel} · ${target.meta}`}
                          </option>
                        ))
                      ) : (
                        <option value="">先登记线程或创建 NPC</option>
                      )}
                    </select>
                  </label>
                  <label className={styles.fieldLabel}>
                    <span>接力标题</span>
                    <input name="title" placeholder="例如：双 AI 协作写一篇用户说明" required />
                  </label>
                  <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                    <span>最终目标</span>
                    <textarea
                      name="objective"
                      placeholder="写清楚最终要交付什么。比如：一个 AI 找资料和提纲，另一个 AI 写成面向小白用户的文章，并列出需要人工审核的点。"
                      required
                    />
                  </label>
                </div>
                <div className={styles.inlineActions}>
                  <button
                    type="submit"
                    disabled={commandTargets.length < 2}
                    data-loading-label="平台正在启动两段式接力"
                  >
                    启动平台接力
                  </button>
                  <Link href={buildExchangeSurfaceHref("receipts")} className={styles.ghostButton}>
                    去看回执结果区
                  </Link>
                </div>
                <p className={styles.microCopy}>
                  这不是手动连续派两次：提交后后台编排器会等待第一棒最终回复，再自动创建第二棒派工。若某台电脑路径不同，由各自适配器按本机配置执行。
                </p>
              </form>
            ) : null}

            {!visibleExchangeComposerMode ? (
              <div className={styles.noticeCard}>
                <strong>一级只保留入口，不直接堆动作台</strong>
                <p>先从左侧协作分区栏选你要看的板块；只有当你真要广播成员动态或下发 AI 派工时，才点上面的入口展开对应动作台。</p>
              </div>
            ) : null}
          </section>
        ) : null}

        {exchangeSectionFocusId === "member-sync" ? (
        <section
          className={`${styles.exchangeLevelSection} ${styles.exchangeLevelSectionActive}`}
          data-exchange-level="2"
          data-exchange-section="member-sync"
          data-exchange-section-active="true"
        >
          <div className={styles.exchangeLevelHead}>
            <span className={styles.exchangeLevelTag}>二级</span>
            <div>
              <strong>成员动态区</strong>
              <p className={styles.microCopy}>这里只看真人账号之间的共享动态，不夹 AI 派工和结果。</p>
            </div>
            <span className={styles.stateBadge}>{`${recentProjectSyncNotes.length} 条`}</span>
          </div>
          <ul className={styles.list}>
          {recentProjectSyncNotes.length ? (
            recentProjectSyncNotes.map((message, index) => {
              const messageId = text(message.id, `project-sync-${index + 1}`);
              const syncTitle = text(message.title, "未命名共享动态");
              const syncSender = actorLabel(message, display);
              const syncSenderAliases = uniqueStrings([
                text(message.sender_id ?? message.agent_id, ""),
                syncSender,
              ]).map((value) => value.toLowerCase());
              const syncFocused = routeAliasesMatch(syncSenderAliases, normalizedExchangeFocusRouteKeys);
              return (
                <li
                  key={messageId}
                  className={syncFocused ? styles.listItemFocused : undefined}
                  data-project-sync-note-item={messageId}
                  data-project-sync-note-title={syncTitle}
                  data-project-sync-note-sender={syncSender}
                  data-project-sync-note-aliases={syncSenderAliases.join("|")}
                  data-exchange-focus-active={syncFocused ? "true" : undefined}
                >
                  <strong>{syncTitle}</strong>
                  <p>
                    发起：{syncSender}
                    {text(message.status, "") ? ` / 状态：${text(message.status, "")}` : ""}
                  </p>
                  <p>{shortText(message.body, "没有正文", 92)}</p>
                  <div className={styles.inlineActions}>
                    <button
                      type="button"
                      className={styles.ghostButton}
                      data-exchange-open-detail={`sync:${messageId}`}
                      onClick={() => openManagerDrawer("exchange-detail", `sync:${messageId}`)}
                    >
                      查看详情
                    </button>
                  </div>
                  <p className={styles.microCopy}>{formatStamp(message.created_at ?? message.updated_at)}</p>
                </li>
              );
            })
          ) : (
            <li>
              <strong>还没有项目成员共享动态</strong>
              <p>先让一个账号发出协作状态，接受邀请的其他主角就能在同一项目里看到这条共享动态。</p>
            </li>
          )}
        </ul>
        </section>
        ) : null}

        {exchangeSectionFocusId === "dispatch" ? (
        <section
          className={`${styles.exchangeLevelSection} ${styles.exchangeLevelSectionActive}`}
          data-exchange-level="2"
          data-exchange-section="dispatch"
          data-exchange-section-active="true"
        >
          <div className={styles.exchangeLevelHead}>
            <span className={styles.exchangeLevelTag}>二级</span>
            <div>
              <strong>平台派工区</strong>
              <p className={styles.microCopy}>这里只看 AI/NPC 的正式派工，不混进共享动态和结果回执。</p>
            </div>
            <span className={styles.stateBadge}>{`${recentPlatformCommands.length} 条`}</span>
          </div>
          <p className={styles.microCopy}>
            这里显示当前项目共享的 AI 平台派工记录，不是 owner 私有列表。项目成员进入同一项目后，会看到同一批平台派工状态。
          </p>
          {runnerQueueAttention ? (
            <div
              className={`${styles.noticeCard} ${styles.featureCardFocused}`}
              data-exchange-dispatch-runner-queue-alert="true"
              data-exchange-runner-queue-count={String(queuedCollaborationCommandCount)}
              data-exchange-runner-ready-count={String(watchReadyNodes.length)}
              data-exchange-runner-blocked-count={String(watchBlockedNodes.length)}
              data-exchange-runner-hard-blocker={runnerQueueBlocker ? "true" : "false"}
            >
              <div className={styles.exchangeLevelHead}>
                <span className={styles.exchangeLevelTag}>{runnerQueueBlocker ? "先别继续派工" : "先确认目标电脑"}</span>
                <div>
                  <strong>{runnerQueueBlocker ? `当前 ${queuedCollaborationCommandCount} 条平台指令还没有被电脑取走` : runnerQueueAttentionTitle}</strong>
                  <p className={styles.microCopy}>
                    {runnerQueueBlocker
                      ? "这不是 AI 没有任务，而是所有接入电脑都没有处于常驻接单。先恢复任一电脑的 Watch/心跳，再发送新的协作指令。"
                      : "平台已经有电脑能接单，但不是所有目标都能接。派给未接单电脑的任务仍会卡住，先按目标线程恢复对应电脑。"}
                  </p>
                </div>
              </div>
              <div className={styles.inlineActions}>
                <button type="button" onClick={() => openBackpackPanel("computers")}>
                  {runnerQueueBlocker ? "去电脑接入管理" : "查看未接单电脑"}
                </button>
                <button type="button" className={styles.ghostButton} onClick={() => focusExchangeSection("thread-focus")}>
                  只看线程状态
                </button>
              </div>
            </div>
          ) : null}
          <ul className={styles.list}>
          {recentPlatformCommands.length ? (
            recentPlatformCommands.map((message, index) => {
              const messageId = text(message.id, `platform-command-${index + 1}`);
              const targetId = text(message.recipient_id, "");
              const target = commandTargetMap.get(targetId);
              const targetLink = resolveExchangeTarget(targetId);
              const targetNode = targetLink?.computerNodeId
                ? nodeById.get(text(targetLink.computerNodeId, "").toLowerCase()) ?? null
                : null;
              const targetWatch = runnerWatchInfo(targetNode);
              const commandStatus = text(message.status, "").toLowerCase();
              const commandQueued = ["queued", "pending", "open", "routed"].includes(commandStatus);
              const routeAliases = uniqueStrings([targetId, target?.label]).map((value) => value.toLowerCase());
              const senderLabel = actorLabel(message, display);
              const senderAliases = uniqueStrings([
                text(message.sender_id ?? message.agent_id, ""),
                senderLabel,
              ]).map((value) => value.toLowerCase());
              const commandFocused =
                routeAliasesMatch(senderAliases, normalizedExchangeFocusRouteKeys) ||
                routeAliasesMatch(routeAliases, normalizedExchangeFocusRouteKeys);
              const commandTitle = text(message.title, "未命名协作指令");
              return (
                <li
                  key={messageId}
                  className={commandFocused ? styles.listItemFocused : undefined}
                  data-exchange-command-item={messageId}
                  data-exchange-command-title={commandTitle}
                  data-exchange-command-sender={senderLabel}
                  data-exchange-command-sender-aliases={senderAliases.join("|")}
                  data-exchange-dispatch-target={targetId || target?.label || messageId}
                  data-exchange-dispatch-aliases={routeAliases.join("|")}
                  data-exchange-focus-active={commandFocused ? "true" : undefined}
                >
                  <strong>{commandTitle}</strong>
                  <p>
                    目标：{target ? `${target.label} / ${target.providerLabel}` : display(targetId, targetId || "未指定")}
                    {text(message.status, "") ? ` / 状态：${text(message.status, "")}` : ""}
                  </p>
                  {targetNode ? (
                    <p className={styles.microCopy}>
                      接单监听：{targetWatch.label} / {targetWatch.detail}
                    </p>
                  ) : null}
                  {commandQueued && targetNode && !targetWatch.active ? (
                    <div
                      className={styles.chipRow}
                      data-exchange-watch-warning={messageId}
                      data-exchange-watch-target-node={text(targetLink?.computerNodeId, "")}
                    >
                      <span className={`${styles.miniChip} ${styles.miniChipWarning}`}>
                        已排队但目标电脑未常驻接单，请在对应电脑运行 -Watch 命令
                      </span>
                      <button
                        type="button"
                        className={`${styles.inlineActionLink} ${styles.ghostButton}`}
                        data-exchange-open-watch-command={text(targetLink?.computerNodeId, "")}
                        onClick={() => openManagerDrawer("computer-threads", text(targetLink?.computerNodeId, ""))}
                      >
                        去复制 Watch 命令
                      </button>
                    </div>
                  ) : null}
                  <p>发起：{senderLabel}</p>
                  <p>{shortText(message.body, "没有正文", 96)}</p>
                  {commandQueued ? (
                    <div className={styles.inlineActions}>
                      <button
                        type="button"
                        data-exchange-open-queue-detail={`queue:${messageId}`}
                        onClick={() => openManagerDrawer("exchange-detail", `queue:${messageId}`)}
                      >
                        处理队列
                      </button>
                    </div>
                  ) : null}
                  {targetLink?.threadId || targetLink?.seatId ? (
                    <div className={styles.inlineActions}>
                      <button
                        type="button"
                        className={styles.ghostButton}
                        data-exchange-open-detail={`command:${messageId}`}
                        onClick={() => openManagerDrawer("exchange-detail", `command:${messageId}`)}
                      >
                        查看详情
                      </button>
                      {targetLink.threadId ? (
                        <button
                          type="button"
                          className={styles.ghostButton}
                          data-exchange-open-thread={targetLink.threadId}
                          onClick={() => openMachineRoomThread(targetLink.threadId ?? "", targetLink.computerNodeId)}
                        >
                          去机房定位
                        </button>
                      ) : null}
                      {targetLink.seatId ? (
                        <button
                          type="button"
                          className={styles.ghostButton}
                          data-exchange-open-seat-profile={targetLink.seatId}
                          onClick={() => openNpcProfileFromExchange(targetLink.seatId ?? "")}
                        >
                          看 NPC 属性
                        </button>
                      ) : null}
                    </div>
                  ) : (
                    <div className={styles.inlineActions}>
                      <button
                        type="button"
                        className={styles.ghostButton}
                        data-exchange-open-detail={`command:${messageId}`}
                        onClick={() => openManagerDrawer("exchange-detail", `command:${messageId}`)}
                      >
                        查看详情
                      </button>
                    </div>
                  )}
                  <p className={styles.microCopy}>{formatStamp(message.created_at ?? message.updated_at)}</p>
                </li>
              );
            })
          ) : (
            <li>
              <strong>还没有从页面发出的协作指令</strong>
              <p>先登记线程或创建 NPC，再从上面的表单指定目标。这里会保留最近的统一平台消息。</p>
            </li>
          )}
        </ul>
        </section>
        ) : null}

        {exchangeSectionFocusId === "receipts" ? (
        <section
          className={`${styles.exchangeLevelSection} ${styles.exchangeLevelSectionActive}`}
          data-exchange-level="2"
          data-exchange-section="receipts"
          data-exchange-section-active="true"
        >
          <div className={styles.exchangeLevelHead}>
            <span className={styles.exchangeLevelTag}>二级</span>
            <div>
              <strong>回执结果区</strong>
              <p className={styles.microCopy}>按一次派工聚合成一轮：先看有没有最小回执，再看有没有最终回复。原始消息不再直接堆成日志墙。</p>
            </div>
            <span className={styles.stateBadge}>{`${visibleReceiptRoundItems.length}/${receiptRoundItems.length} 轮`}</span>
          </div>
          <div className={styles.receiptFilterBar} data-exchange-receipt-filter-bar="true">
            {exchangeReceiptFilterItems.map((item) => (
              <button
                key={`receipt-filter-${item.id}`}
                type="button"
                className={`${styles.receiptFilterChip} ${exchangeReceiptFilter === item.id ? styles.receiptFilterChipActive : ""}`}
                data-exchange-receipt-filter={item.id}
                data-exchange-receipt-filter-active={exchangeReceiptFilter === item.id ? "true" : undefined}
                onClick={() => setExchangeReceiptFilter(item.id)}
              >
                <strong>{`${item.label} · ${item.count}`}</strong>
                <span>{item.detail}</span>
              </button>
            ))}
          </div>
          <ul className={`${styles.list} ${styles.receiptRoundList}`}>
          {visibleReceiptRoundItems.length ? (
            visibleReceiptRoundItems.map((round) => {
              const ackId = text(round.latestAck?.id, `${round.id}-ack`);
              const finalId = text(round.latestFinal?.id, `${round.id}-final`);
              const commandTargetLabel = commandTargetMap.get(round.commandTargetId)?.label ?? round.commandTargetId;
              const detailMessageId = text(round.latestFinal?.id ?? round.latestAck?.id ?? round.latestMessage?.id, "");
              const receiptAliases = uniqueStrings([
                round.receiptTargetId,
                round.commandTargetId,
                round.senderLabel,
                commandTargetLabel,
              ]).map((value) => value.toLowerCase());
              return (
                <li
                  key={round.id}
                  className={`${styles.receiptRoundCard} ${round.focused ? styles.listItemFocused : ""} ${round.hasFinal ? styles.receiptRoundDone : styles.receiptRoundOpen}`}
                  data-exchange-receipt-round={round.title}
                  data-exchange-receipt-round-status={round.statusLabel}
                  data-exchange-receipt-round-validation={round.isValidationNoise ? "true" : "false"}
                  data-exchange-dispatch-target={round.receiptTargetId || round.commandTargetId}
                  data-exchange-dispatch-aliases={receiptAliases.join("|")}
                  data-exchange-focus-active={round.focused ? "true" : undefined}
                >
                  <div className={styles.receiptRoundHead}>
                    <div>
                      <span className={styles.exchangeLevelTag}>协作轮次</span>
                      <strong>{round.title}</strong>
                      <p>
                        来源：{round.senderLabel}
                        {commandTargetLabel ? ` / 目标：${commandTargetLabel}` : ""}
                        {round.isValidationNoise ? " / 验收消息" : ""}
                      </p>
                    </div>
                    <span className={round.hasFinal ? styles.stateBadge : styles.miniChipWarning}>{round.statusLabel}</span>
                  </div>
                  <div className={styles.receiptRoundTimeline}>
                    <div className={styles.receiptTimelineStep} data-receipt-step-state={round.commandMessage ? "done" : "empty"}>
                      <span>派工</span>
                      <strong>{round.commandMessage ? "已登记" : "未匹配到派工"}</strong>
                      <p>{round.commandMessage ? shortText(round.commandMessage.body, "没有正文", 64) : "可能是旧 requirement 或外部回写结果。"}</p>
                    </div>
                    <div
                      className={styles.receiptTimelineStep}
                      data-receipt-step-state={round.latestAck ? "done" : "empty"}
                      data-exchange-receipt-item={ackId}
                      data-exchange-receipt-kind="最小回执"
                      data-exchange-receipt-title={round.title}
                      data-exchange-receipt-type={text(round.latestAck?.message_type, "agent_ack")}
                      data-exchange-receipt-sender={round.senderLabel}
                    >
                      <span>最小回执</span>
                      <strong>{round.latestAck ? `状态：${text(round.latestAck.status, "delivered")}` : "等待"}</strong>
                      <p>{round.latestAck ? shortText(round.latestAck.body, "没有正文", 64) : "目标 AI 接单后这里会先亮起。"}</p>
                    </div>
                    <div
                      className={styles.receiptTimelineStep}
                      data-receipt-step-state={round.latestFinal ? "done" : "empty"}
                      data-exchange-receipt-item={finalId}
                      data-exchange-receipt-kind="最终回复"
                      data-exchange-receipt-title={round.title}
                      data-exchange-receipt-type={text(round.latestFinal?.message_type, "agent_result")}
                      data-exchange-receipt-sender={round.senderLabel}
                    >
                      <span>最终回复</span>
                      <strong>{round.latestFinal ? `状态：${text(round.latestFinal.status, "completed")}` : "等待"}</strong>
                      <p>{round.latestFinal ? shortText(round.latestFinal.body, "没有正文", 64) : "完成后会进入最终回复池。"}</p>
                    </div>
                  </div>
                  <p>{round.bodyPreview}</p>
                  <p className={styles.microCopy}>
                    {`最近信号：${formatStamp(round.latestAt)} / 原始回执 ${round.receiptCount} 条 / 当前筛选：${exchangeReceiptFilterItems.find((item) => item.id === exchangeReceiptFilter)?.label ?? "全部轮次"}`}
                  </p>
                  {round.targetLink?.threadId || round.targetLink?.seatId || detailMessageId ? (
                    <div className={styles.inlineActions}>
                      {detailMessageId ? (
                        <button
                          type="button"
                          className={styles.ghostButton}
                          data-exchange-open-detail={`receipt:${detailMessageId}`}
                          onClick={() => openManagerDrawer("exchange-detail", `receipt:${detailMessageId}`)}
                        >
                          查看三级详情
                        </button>
                      ) : null}
                      {round.targetLink?.threadId ? (
                        <button
                          type="button"
                          className={styles.ghostButton}
                          data-exchange-open-thread={round.targetLink.threadId}
                          onClick={() => openMachineRoomThread(round.targetLink?.threadId ?? "", round.targetLink?.computerNodeId)}
                        >
                          去机房定位
                        </button>
                      ) : null}
                      {round.targetLink?.seatId ? (
                        <button
                          type="button"
                          className={styles.ghostButton}
                          data-exchange-open-seat-profile={round.targetLink.seatId}
                          onClick={() => openNpcProfileFromExchange(round.targetLink?.seatId ?? "")}
                        >
                          看 NPC 属性
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              );
            })
          ) : (
            <li>
              <strong>当前筛选下没有回执轮次</strong>
              <p>可以切回“全部轮次”，或等 Codex、Claude、Qwen 领取新指令后再看最小回执和最终回复。</p>
            </li>
          )}
        </ul>
        </section>
        ) : null}

        {exchangeSectionFocusId === "thread-focus" ? (
        <section
          className={`${styles.exchangeLevelSection} ${styles.exchangeLevelSectionActive}`}
          data-exchange-level="2"
          data-exchange-section="thread-focus"
          data-exchange-section-active="true"
        >
          <div className={styles.exchangeLevelHead}>
            <span className={styles.exchangeLevelTag}>二级</span>
            <div>
              <strong>线程焦点区</strong>
              <p className={styles.microCopy}>这一层只负责把协作现场和机房线程一一对齐，便于定位。</p>
            </div>
            <span className={styles.stateBadge}>{`${workstationExchangeFocusFeed.length} 条`}</span>
          </div>
        <details className={styles.editorFold}>
          <summary>{`线程协作焦点（${workstationExchangeFocusFeed.length} 条）`}</summary>
          <div className={styles.foldBody}>
            <div className={styles.noticeCard}>
              <strong>机房与消息池对齐</strong>
              <p>这里按真实线程聚合最近命令、最小回执和最终回复，和机房卡使用同一套线程匹配规则，方便从消息池直接定位到你在机房里看到的那条线程。</p>
            </div>
            <ul className={styles.list}>
              {workstationExchangeFocusFeed.length ? (
                workstationExchangeFocusFeed.map((item) => (
                  <li
                    key={item.id}
                    data-exchange-thread-id={item.threadId}
                    data-exchange-thread-focus-item={item.threadId}
                    data-exchange-dispatch-target={item.threadId}
                    data-exchange-dispatch-aliases={item.routeKeys.join("|")}
                  >
                    <strong>{item.primaryLabel}</strong>
                    <p>
                      目标线程：{item.targetLabel}
                      {item.providerLabel ? ` / Provider ${item.providerLabel}` : ""}
                      {item.computerNodeLabel ? ` / 电脑 ${item.computerNodeLabel}` : ""}
                    </p>
                    <div className={styles.chipRow}>
                      {item.latestCommandLabel ? (
                        <span className={styles.miniChip}>{item.latestCommandTypeLabel || "最近命令"}</span>
                      ) : null}
                      {item.latestAckLabel ? <span className={styles.miniChip}>已回最小回执</span> : null}
                      {item.latestFinalReplyLabel ? <span className={styles.miniChip}>已回写最终回复</span> : null}
                      {item.freshnessLabel ? (
                        <span className={item.stale ? styles.miniChipWarning : styles.miniChip}>{item.freshnessLabel}</span>
                      ) : null}
                    </div>
                    <p>{shortText(item.primaryBody, item.primaryBody, 96)}</p>
                    <div className={styles.inlineActions}>
                      <button
                        type="button"
                        className={styles.ghostButton}
                        data-exchange-open-detail={`thread:${item.threadId}`}
                        onClick={() => openManagerDrawer("exchange-detail", `thread:${item.threadId}`)}
                      >
                        查看详情
                      </button>
                      <button
                        type="button"
                        className={styles.ghostButton}
                        data-exchange-open-thread={item.threadId}
                        onClick={() => openMachineRoomThread(item.threadId, item.computerNodeLabel)}
                      >
                        去机房定位
                      </button>
                      {item.preferredSeatId ? (
                        <button
                          type="button"
                          className={styles.ghostButton}
                          data-exchange-open-seat-profile={item.preferredSeatId}
                          onClick={() => openNpcProfileFromExchange(item.preferredSeatId)}
                        >
                          看 NPC 属性
                        </button>
                      ) : null}
                    </div>
                    <p className={styles.microCopy}>{formatStamp(item.latestAt)}</p>
                  </li>
                ))
              ) : (
                <li>
                  <strong>还没有线程协作焦点</strong>
                  <p>等平台发过真实命令，或者线程回过最小回执/最终回复后，这里就会按线程聚合显示。</p>
                </li>
              )}
            </ul>
          </div>
        </details>
        </section>
        ) : null}

        {exchangeSectionFocusId === "advanced-proof" ? (
        <section
          className={`${styles.exchangeLevelSection} ${styles.exchangeLevelSectionActive}`}
          data-exchange-level="2"
          data-exchange-section="advanced-proof"
          data-exchange-section-active="true"
        >
          <div className={styles.exchangeLevelHead}>
            <span className={styles.exchangeLevelTag}>二级</span>
            <div>
              <strong>高级过程证明</strong>
              <p className={styles.microCopy}>这里保留 proof 摘要卡；正文、仓库协作和参考资料统一收进三级抽屉，不让二级区继续涨成日志墙。</p>
            </div>
          </div>

        <details className={styles.editorFold}>
          <summary>{cooperationProofSummary.foldSummary}</summary>
          <div className={styles.foldBody}>
            <div className={styles.noticeCard}>
              <strong>{cooperationProofSummary.title}</strong>
              <p>{cooperationProofSummary.body}</p>
              {featuredCooperationProof ? (
                <div className={styles.chipRow}>
                  {featuredCooperationProof.requirementId ? (
                    <span className={styles.miniChip}>{`当前聚焦 ${featuredCooperationProof.requirementId.slice(0, 8)}`}</span>
                  ) : null}
                  <span className={styles.miniChip}>{featuredCooperationProof.progressLabel}</span>
                </div>
              ) : null}
              <p className={styles.microCopy}>{cooperationProofSummary.meta}</p>
            </div>

            <div className={styles.listHead}>
              <strong>真线程闭环证明</strong>
              <span className={styles.stateBadge}>
                {featuredCooperationProof?.requirementId
                  ? `${cooperationProofFeed.length} 条 / ${featuredCooperationProof.requirementId.slice(0, 8)}`
                  : `${cooperationProofFeed.length} 条`}
              </span>
            </div>
            <ul className={styles.list}>
              {cooperationProofFeed.length ? (
                cooperationProofFeed.map((item) => (
                  (() => {
                    const proofTargetLink =
                      uniqueStrings([item.target, ...item.routeKeys])
                        .map((candidate) => resolveExchangeTargetFromCandidate(candidate))
                        .find((candidate): candidate is NonNullable<typeof candidate> => Boolean(candidate)) ?? null;
                    return (
                      <li
                        key={item.id}
                        data-exchange-proof-item={item.id}
                        data-exchange-proof-title={item.title}
                        data-exchange-dispatch-target={item.routeKeys[0] || item.target}
                        data-exchange-dispatch-aliases={item.routeKeys.join("|")}
                      >
                        <strong>{item.title}</strong>
                        <p>
                          目标线程：{item.target}
                          {item.providerLabel ? ` / Provider ${item.providerLabel}` : ""}
                          {item.computerNodeLabel ? ` / 电脑 ${item.computerNodeLabel}` : ""}
                          {item.requirementId ? ` / Requirement ${item.requirementId.slice(0, 8)}` : ""}
                        </p>
                        <div className={styles.chipRow}>
                          {featuredCooperationProofId === item.id ? (
                            <span className={styles.miniChip}>
                              {item.requirementId ? `当前聚焦 ${item.requirementId.slice(0, 8)}` : "当前聚焦"}
                            </span>
                          ) : null}
                          <span className={styles.miniChip}>{item.dispatchLabel}</span>
                          <span className={styles.miniChip}>{item.progressLabel}</span>
                          <span className={styles.miniChip}>{item.finalLabel}</span>
                          <span className={styles.miniChip}>{item.evidenceLabel}</span>
                          {item.contextLabel ? <span className={styles.miniChip}>{item.contextLabel}</span> : null}
                        </div>
                        <p>{shortText(item.body, item.body, 88)}</p>
                        <div className={styles.inlineActions}>
                          <button
                            type="button"
                            className={styles.ghostButton}
                            data-exchange-open-detail={`proof:${item.id}`}
                            onClick={() => openManagerDrawer("exchange-detail", `proof:${item.id}`)}
                          >
                            查看详情
                          </button>
                          {proofTargetLink?.threadId ? (
                            <button
                              type="button"
                              className={styles.ghostButton}
                              data-exchange-open-thread={proofTargetLink.threadId}
                              onClick={() => openMachineRoomThread(proofTargetLink.threadId ?? "", proofTargetLink.computerNodeId)}
                            >
                              去机房定位
                            </button>
                          ) : null}
                          {proofTargetLink?.seatId ? (
                            <button
                              type="button"
                              className={styles.ghostButton}
                              data-exchange-open-seat-profile={proofTargetLink.seatId}
                              onClick={() => openNpcProfileFromExchange(proofTargetLink.seatId ?? "")}
                            >
                              看 NPC 属性
                            </button>
                          ) : null}
                        </div>
                        <p className={styles.microCopy}>三级抽屉里再看仓库协作、参考资料和链路元信息。</p>
                      </li>
                    );
                  })()
                ))
              ) : (
                <li>
                  <strong>还没有可展示的闭环证明</strong>
                  <p>平台一旦把 requirement 派往真实 Codex 线程，这里就会开始按派单、过程信号和最终回复三段累积证据。</p>
                </li>
              )}
            </ul>
          </div>
        </details>

        <details className={styles.editorFold}>
          <summary>{seatAcceptanceSummary.foldSummary}</summary>
          <div className={styles.foldBody}>
            <div className={styles.noticeCard}>
              <strong>{seatAcceptanceSummary.title}</strong>
              <p>{seatAcceptanceSummary.body}</p>
              <div className={styles.chipRow}>
                <span className={styles.miniChip}>{`下一步 ${seatAcceptanceSummary.nextStepLabel}`}</span>
                {featuredQueuedCodexCommand?.requirementId ? (
                  <span className={styles.miniChip}>{`当前聚焦 ${featuredQueuedCodexCommand.requirementId.slice(0, 8)}`}</span>
                ) : null}
              </div>
              <p>{seatAcceptanceSummary.nextStepDetail}</p>
              <p className={styles.microCopy}>{seatAcceptanceSummary.meta}</p>
            </div>

            <div className={styles.listHead}>
              <strong>农场截图验收链</strong>
              <span className={styles.stateBadge}>
                {featuredQueuedCodexCommand?.requirementId
                  ? `${mapSeatPayload.length} 席 / ${featuredQueuedCodexCommand.requirementId.slice(0, 8)}`
                  : `${mapSeatPayload.length} 席`}
              </span>
            </div>
            <ul className={styles.list}>
              {mapSeatPayload.length ? (
                mapSeatPayload.slice(0, 6).map((seat) => (
                  <li key={seat.id}>
                    <strong>{seat.name}</strong>
                    <p>
                      来源线程：{display(seat.sourceThreadId, seat.sourceThreadId || "未绑定")}
                      {seat.nodeName ? ` / 电脑 ${seat.nodeName}` : ""}
                      {seat.currentRequirement ? ` / 当前 requirement ${seat.currentRequirement}` : ""}
                    </p>
                    <div className={styles.chipRow}>
                      <span className={styles.miniChip}>{seat.approvalState}</span>
                      <span className={styles.miniChip}>{seat.reviewState}</span>
                      <span className={styles.miniChip}>{seat.progressHealthLabel}</span>
                      <span className={styles.miniChip}>{seatAutonomyChip(seat)}</span>
                      <span className={styles.miniChip}>{seatScreenshotState(seat, hasProtectedDataGap)}</span>
                      {seat.skillLabels.slice(0, 2).map((skill) => (
                        <span key={`${seat.id}-${skill.id}`} className={styles.miniChip}>{skill.label}</span>
                      ))}
                    </div>
                    <p>{seatAcceptanceBody(seat, hasProtectedDataGap)}</p>
                    <p className={styles.microCopy}>
                      判定：{seat.autonomyDecision}
                      {" / "}
                      最后信号：{seat.lastSignalAt ? formatStamp(seat.lastSignalAt) : "暂无"}
                      {seat.progressLagMinutes !== null ? ` / 回执滞后 ${formatQueueAge(seat.progressLagMinutes)}` : ""}
                      {seat.staleAfterAckMinutes !== null ? ` / 停滞 ${formatQueueAge(seat.staleAfterAckMinutes)}` : ""}
                      {seat.finalReplyAt ? ` / 最终回复 ${formatStamp(seat.finalReplyAt)}` : ""}
                      {seat.minimalAckAt ? ` / 最小回执 ${formatStamp(seat.minimalAckAt)}` : ""}
                    </p>
                  </li>
                ))
              ) : (
                <li>
                  <strong>还没有可截图验收的 NPC 席位</strong>
                  <p>先把真实线程绑定到 NPC 席位，截图验收链才会开始证明哪些席位在自主推进、哪些在等待人工审核。</p>
                </li>
              )}
            </ul>
          </div>
        </details>

        <details className={styles.editorFold}>
          <summary>{processVisibility.foldSummary}</summary>
          <div className={styles.foldBody}>
            <div className={styles.noticeCard}>
              <strong>{processVisibility.title}</strong>
              <p>{processVisibility.body}</p>
              {featuredProcessFocusCommand ? (
                <div className={styles.chipRow}>
                  {featuredProcessFocusCommand.requirementId ? (
                    <span className={styles.miniChip}>{`当前聚焦 ${featuredProcessFocusCommand.requirementId.slice(0, 8)}`}</span>
                  ) : null}
                  <span className={styles.miniChip}>{featuredProcessFocusCommand.statusLabel}</span>
                  {featuredProcessFocusCommand.queueStateLabel ? (
                    <span className={styles.miniChip}>{featuredProcessFocusCommand.queueStateLabel}</span>
                  ) : null}
                </div>
              ) : null}
              <p className={styles.microCopy}>{processVisibility.meta}</p>
            </div>

            <div className={styles.listHead}>
              <strong>平台已发往 Codex 的指令</strong>
              <span className={styles.stateBadge}>
                {featuredVisibleCodexCommand?.requirementId
                  ? `${codexInboxFullFeed.length} 条 / ${featuredVisibleCodexCommand.requirementId.slice(0, 8)}`
                  : `${codexInboxFullFeed.length} 条`}
              </span>
            </div>
            {featuredVisibleCodexCommand ? (
              <p className={styles.microCopy}>
                {`当前截图聚焦 ${featuredVisibleCodexCommand.target || "当前线程"}${featuredVisibleCodexCommand.requirementId ? ` / Requirement ${featuredVisibleCodexCommand.requirementId.slice(0, 8)}` : ""}；如果多条 bridged 指令共享同一时间戳，会优先把这条证据放在前面，但平台队列统计仍按全部 bridged 指令计算。`}
              </p>
            ) : null}
            <ul className={styles.list}>
              {codexInboxFeed.length ? (
                codexInboxFeed.map((item) => (
                  <li
                    key={item.id}
                    data-exchange-dispatch-target={item.workstationId || item.target}
                    data-exchange-dispatch-aliases={exchangeDispatchRouteKeys(item).join("|")}
                  >
                    <strong>{item.title}</strong>
                    <p>
                      目标线程：{item.target}
                      {item.providerLabel ? ` / Provider ${item.providerLabel}` : ""}
                      {item.computerNodeLabel ? ` / 电脑 ${item.computerNodeLabel}` : ""}
                    </p>
                    <div className={styles.chipRow}>
                      {featuredVisibleCodexCommandId === item.id ? (
                        <span className={styles.miniChip}>
                          {item.requirementId ? `当前聚焦 ${item.requirementId.slice(0, 8)}` : "当前聚焦"}
                        </span>
                      ) : null}
                      <span className={styles.miniChip}>{item.queueLabel}</span>
                      <span className={styles.miniChip}>{item.statusLabel}</span>
                      {item.queueStartedAtLabel ? <span className={styles.miniChip}>{`排队起点 ${item.queueStartedAtLabel}`}</span> : null}
                      {item.queueAgeLabel || item.queueStateLabel ? (
                        <span className={styles.miniChip}>
                          {item.queueAgeLabel && item.queueStateLabel
                            ? `已等 ${item.queueAgeLabel} · ${item.queueStateLabel}`
                            : item.queueAgeLabel
                              ? `已等 ${item.queueAgeLabel}`
                              : item.queueStateLabel}
                        </span>
                      ) : null}
                      {item.skillLoadout.slice(0, 3).map((skill) => (
                        <span key={`${item.id}-${skill}`} className={styles.miniChip}>{skill}</span>
                      ))}
                    </div>
                    <p>{item.body}</p>
                    <p className={styles.microCopy}>{item.meta}</p>
                  </li>
                ))
              ) : (
                <li>
                  <strong>平台还没发往 Codex 指令</strong>
                  <p>下一次自治推进把 requirement 派给 codex-session 线程后，这里会立刻出现你能看到的线程指令。</p>
                </li>
              )}
            </ul>
            {codexInboxFullFeed.length > codexInboxFeed.length ? (
              <p className={styles.microCopy}>
                {`首屏只展示最新 ${codexInboxFeed.length} 条，但证明面统计仍按全部 ${codexInboxFullFeed.length} 条 bridged 指令计算${featuredVisibleCodexCommand ? `；当前聚焦 ${featuredVisibleCodexCommand.target || "当前线程"}${shortRequirementLabel(featuredVisibleCodexCommand.requirementId) ? ` · ${shortRequirementLabel(featuredVisibleCodexCommand.requirementId)}` : ""}` : ""}。`}
              </p>
            ) : null}

            <div className={styles.listHead}>
              <strong>最终回复池</strong>
              <span className={styles.stateBadge}>{hasProtectedDataGap ? "未授权" : `${finalReplyFeed.length} 条`}</span>
            </div>
            <ul className={styles.list}>
              {hasProtectedDataGap ? (
                <li>
                  <strong>受保护协作数据未授权</strong>
                  <p>重新登录后，这里才会恢复 requirement、最小回执和最终回复。</p>
                </li>
              ) : finalReplyFeed.length ? (
                finalReplyFeed.map((item) => (
                  <li key={item.id}>
                    <strong>{item.title}</strong>
                    <p>{item.route} / {item.target}</p>
                    <div className={styles.chipRow}>
                      <span className={styles.miniChip}>{item.ackLabel}</span>
                      <span className={styles.miniChip}>{item.progressLabel}</span>
                      <span className={styles.miniChip}>{item.replyOwnerLabel}</span>
                    </div>
                    <p>{item.body}</p>
                    <p className={styles.microCopy}>{item.meta}</p>
                  </li>
                ))
              ) : (
                <li>
                  <strong>当前还没有最终回复</strong>
                  <p>先接单，再给最小回执，最后把结果收进最终回复池。</p>
                </li>
              )}
            </ul>

            <div className={styles.listHead}>
              <strong>真实线程回执</strong>
              <span className={styles.stateBadge}>{hasProtectedDataGap ? "未授权" : `${relayFeed.length} 条`}</span>
            </div>
            <ul className={styles.list}>
              {hasProtectedDataGap ? (
                <li>
                  <strong>受保护协作数据未授权</strong>
                  <p>当前登录态没有拿到 runner 回执和结果。</p>
                </li>
              ) : relayFeed.length ? (
                relayFeed.map((item) => (
                  <li key={item.id}>
                    <strong>{item.title}</strong>
                    <p>{item.body}</p>
                    <p className={styles.microCopy}>{item.meta}</p>
                  </li>
                ))
              ) : (
                <li>
                  <strong>线程在线，等待第一条回执</strong>
                  <p>一旦 runner command、ack、result 或 task dispatch 进入，这里就会开始滚动。</p>
                </li>
              )}
            </ul>
          </div>
        </details>
        </section>
        ) : null}
      </div>
    );
  }

  function resolveManagedSeat(selectionId?: string | null) {
    const focus = text(selectionId ?? seatFocusId, "");
    let seat: AnyRecord | null = null;
    let seatView: any = null;

    if (focus) {
      for (const candidate of codexSeats) {
        const candidateView = resolveSeatViewForRecord(candidate, seatPayloadMap);
        if (seatMatchesFocus(candidate, candidateView, focus)) {
          seat = candidate;
          seatView = candidateView;
          break;
        }
      }
    }

    if (!seat && editorSeat) {
      seat = editorSeat;
      seatView = editorSeatView;
    }
    if (!seat && codexSeats.length) {
      seat = codexSeats[0];
      seatView = resolveSeatViewForRecord(seat, seatPayloadMap);
    }
    if (!seatView && seat) {
      seatView = resolveSeatViewForRecord(seat, seatPayloadMap);
    }
    if (!seatView && focus) {
      seatView = seatPayloadMap.get(focus) ?? seatPayloadMap.get(focus.toLowerCase()) ?? null;
    }

    const id = text(seatView?.id ?? seat?.id ?? seat?.config_id ?? seat?.row_id, "");
    const sourceThreadId = text(
      seatView?.sourceThreadId ?? seat?.source_workstation_id ?? seat?.metadata?.source_workstation_id,
      "",
    );
    const name = text(seatView?.name ?? seat?.name, id || "还没有 NPC");
    const role = text(seatView?.role ?? seat?.responsibility ?? seat?.metadata?.responsibility, "待分配职责");
    const providerId = text(seatView?.providerId ?? seat?.ai_provider_id ?? seat?.metadata?.provider_id, "codex");
    const providerLabel = text(seatView?.providerLabel ?? seat?.ai_provider ?? seat?.metadata?.provider_label, platformProviderLabelFromSeat(seat ?? {}));
    const automationEnabled = booleanFromUnknown(
      seatView?.automationEnabled ?? seat?.metadata?.automation_enabled,
      false,
    );
    const heartbeatIntervalSeconds = normalizeAutomationHeartbeatSeconds(
      seatView?.heartbeatIntervalSeconds ?? seat?.metadata?.automation_heartbeat_seconds,
    );
    const computerNodeId = text(seatView?.computerNodeId ?? seat?.computer_node_id ?? seat?.metadata?.computer_node_id, "");
    const model = text(seat?.model ?? seat?.metadata?.model, "gpt-5.4");
    const skillState = seat ? resolveSeatSkillLoadout(seat, skillLibrary) : null;
    const additionalSkillIds = skillState?.additionalSkillIds ?? [];
    const loadoutLabels =
      skillState?.allSkillIds.map((skillId) => text(skillById.get(skillId.toLowerCase())?.label, skillId)) ?? [];
    const targetId = sourceThreadId || id || name;
    const knowledge = seat?.metadata?.npc_knowledge && typeof seat.metadata.npc_knowledge === "object"
      ? (seat.metadata.npc_knowledge as AnyRecord)
      : null;
    const collabProtocol = resolvePlatformCollabProtocol(seat?.metadata?.collab_protocol, {
      providerId,
      roleText: role,
      threadText: name,
    });

    return {
      seat,
      seatView,
      id,
      sourceThreadId,
      targetId,
      name,
      role,
      providerId,
      providerLabel,
      automationEnabled,
      heartbeatIntervalSeconds,
      computerNodeId,
      model,
      additionalSkillIds,
      loadoutLabels,
      knowledge,
      collabProtocol,
      protocolProjectProfile: text(seatView?.protocolProjectProfile, collabProtocol.project_profile),
      protocolTokenSummary: text(seatView?.protocolTokenSummary, collabTokenPolicySummary(collabProtocol)),
      protocolRunawaySummary: text(seatView?.protocolRunawaySummary, collabRunawayPolicySummary(collabProtocol)),
      protocolEfficiencySummary: text(seatView?.protocolEfficiencySummary, collabEfficiencyPolicySummary(collabProtocol)),
      protocolDebugSummary: text(seatView?.protocolDebugSummary, collabDebugPolicySummary(collabProtocol)),
    };
  }

  function renderDevelopmentWorkshopPanel() {
    const selectedStation = selectedDevelopmentStation;
    const assignedWorkshopSeats = selectedStation
      ? mapSeatPayload.filter((seat) => developmentStationMatchesNpc(selectedStation, seat))
      : [];
    const workshopTargets = [
      ...mapSeatPayload.map((seat) => ({
        id: text(seat.sourceThreadId || seat.id, ""),
        label: seat.name || text(seat.id, "NPC"),
        meta: `${seat.providerLabel || "AI"} / ${seat.nodeName || "未绑定电脑"}`,
      })),
      ...allThreadCandidates.map((thread) => ({
        id: text(thread.id ?? thread.workstation_id, ""),
        label: display(thread.name ?? thread.label, "线程"),
        meta: `${platformProviderLabelFromThread(thread)} / ${display(thread.computer_node_id ?? thread.computer_node, "未绑定电脑")}`,
      })),
    ].filter((item, index, list) => item.id && list.findIndex((candidate) => candidate.id === item.id) === index);
    const defaultWorkshopTarget = workshopTargets[0]?.id ?? "";
    const stationBrief = selectedStation
      ? [
          `工位：${selectedStation.label}`,
          `地图位置：${selectedStation.mapScene} / ${selectedStation.mapLocation}`,
          `后端锚点：${selectedStation.backendAnchor}`,
          `审批规则：${selectedStation.approvalPolicy}`,
          `工位知识库：${selectedStation.knowledgeBase.handoffPath}`,
          `下一步：${selectedStation.nextActions.join("；")}`,
        ].join("\n")
      : "";

    return (
      <div className={styles.managerStageStack}>
        <section className={styles.managerObjectHero}>
          <span className={styles.managerObjectSprite}>工</span>
          <div>
            <span className={styles.managerEyebrow}>外场建筑：开发工坊</span>
            <h3>从目标到可交付项目的通用开发链</h3>
            <p>
              这里不是某个 NPC 的页面，而是整个项目共用的开发工坊。工位属于工坊，用户可以自己编辑；NPC 只是挂在工位上的执行者。
              工位有自己的共用知识库，NPC 也有各自的连续知识库，两层分开保留。
            </p>
          </div>
        </section>

        <div className={styles.managerStatGrid}>
          <article><span>工位数量</span><strong>{developmentWorkshopStations.length}</strong></article>
          <article><span>接入电脑</span><strong>{nodes.length}</strong></article>
          <article><span>负责 NPC</span><strong>{assignedWorkshopSeats.length}</strong></article>
        </div>

        {selectedStation ? (
          <section className={styles.managerPreviewPanel}>
            <span className={styles.managerEyebrow}>{selectedStation.station}</span>
            <h3>{selectedStation.label}</h3>
            <p>{selectedStation.detail}</p>
            <p className={styles.microCopy}>{`工位知识库：${selectedStation.knowledgeBase.handoffPath}`}</p>
            <div className={styles.managerActionGrid}>
              <button type="button" onClick={() => openManagerDrawer("npc-create", selectedStation.id)}>
                给此工位添加 NPC
              </button>
              <button type="button" onClick={() => openManagerDrawer("development-module", selectedStation.id)}>
                编辑当前工位
              </button>
              <button type="button" onClick={() => openManagerDrawer("development-module", DEVELOPMENT_STATION_CREATE_DRAWER_ID)}>
                添加新工位
              </button>
              <button type="button" onClick={() => openBackpackPanel("serial-tv")}>
                去串口电视
              </button>
              <button type="button" onClick={() => openBackpackPanel("ai-debug")}>
                去 AI 调试
              </button>
              <button type="button" onClick={() => openBackpackPanel("ai-simulation")}>
                去 AI 仿真
              </button>
              <button type="button" onClick={() => openBackpackPanel("computers")}>
                去电脑接入
              </button>
            </div>
          </section>
        ) : null}

        <div className={styles.listHead}>
          <strong>当前工位负责人 NPC</strong>
          <span className={styles.stateBadge}>{`${assignedWorkshopSeats.length} 个`}</span>
        </div>
        <ul className={styles.list}>
          {assignedWorkshopSeats.length ? (
            assignedWorkshopSeats.map((seat) => (
              <li key={`workshop-assigned-seat-${selectedStation?.id}-${seat.id}`}>
                <strong>{seat.name}</strong>
                <p>{`${seat.role || "待补职责"} / ${seat.providerLabel || "AI"} / ${seat.nodeName || "未绑定电脑"}`}</p>
              </li>
            ))
          ) : (
            <li>
              <strong>这个工位还没有专属 NPC</strong>
              <p>点击“给此工位添加 NPC”，创建后这个 NPC 会固定承担该工位职责，线程和电脑以后可以再切换。</p>
            </li>
          )}
        </ul>

        <div className={styles.managerCardGrid}>
          {developmentWorkshopStations.map((item) => (
            <article key={`workshop-station-${item.id}`}>
              <strong>{`${item.icon} ${item.label}`}</strong>
              <p>{item.detail}</p>
              <p className={styles.microCopy}>{`地图：${item.mapLocation} / 风险：${item.riskLevel} / 知识库：${item.knowledgeBase.handoffPath}`}</p>
            </article>
          ))}
        </div>

        {(() => {
          const workshopPreview =
            text(collaborationPreview?.preview_key, "") === "workshop-plan" ? collaborationPreview : null;
          const workshopPreviewReady = Boolean(workshopPreview?.ready);
          const workshopPreviewNeedsHumanReview = collaborationPreviewNeedsHumanReview(workshopPreview);
          return (
        <form action={submitCollaborationMessage} className={styles.skillManagerForm}>
          <strong>把当前工位交给 AI 规划</strong>
          <p className={styles.microCopy}>这条会进入平台协作消息池，用同一格式派给 Codex、Claude、Qwen 或未来其他模型。</p>
          {renderCollaborationPreviewCard(workshopPreview, "最近一次工位规划预演")}
          <input type="hidden" name="project_id" value={projectId} />
          <input type="hidden" name="message_type" value="agent_command" />
          <input type="hidden" name="sender_type" value="human" />
          <input type="hidden" name="sender_id" value={currentHumanSenderValue} />
          <input type="hidden" name="recipient_type" value="workstation" />
          <input type="hidden" name="status" value="queued" />
          <input type="hidden" name="return_to" value={developmentWorkshopReturnPath} />
          <input type="hidden" name="preview_key" value="workshop-plan" />
          <input type="hidden" name="enforce_preview" value="1" />
          <input type="hidden" name="required_preview_signature" value={text(workshopPreview?.preview_signature, "")} />
          <input type="hidden" name="required_preview_ready" value={workshopPreviewReady ? "1" : ""} />
          <div className={styles.skillManagerGrid}>
            <label className={styles.fieldLabel}>
              <span>交给哪个 AI</span>
              <select name="recipient_id" className={styles.select} defaultValue={defaultWorkshopTarget}>
                {workshopTargets.length ? (
                  workshopTargets.map((target) => (
                    <option key={`workshop-target-${target.id}`} value={target.id}>
                      {`${target.label} · ${target.meta}`}
                    </option>
                  ))
                ) : (
                  <option value="">先创建 NPC 或绑定线程</option>
                )}
              </select>
            </label>
            <label className={styles.fieldLabel}>
              <span>标题</span>
              <input name="title" defaultValue={`开发工坊 / ${selectedStation?.label ?? "规划"}`} required />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>指令正文</span>
              <textarea
                name="body"
                defaultValue={`请按开发工坊框架继续细化这个工位，先不要做危险真实设备动作。\n${stationBrief}\n\n输出要求：1. 最小可落地功能；2. 需要的后端字段/API；3. 前端二级/三级界面；4. 需要人工确认的边界。`}
                required
              />
            </label>
          </div>
          <div className={styles.inlineActions}>
            <button
              type="submit"
              formAction={previewCollaborationMessage}
              disabled={!workshopTargets.length}
              data-loading-label="正在预演工位规划"
            >
              先预演工位规划
            </button>
            <button
              type="submit"
              disabled={!workshopTargets.length || !workshopPreviewReady}
              data-loading-label="正在登记工位规划"
             >
               {workshopPreviewNeedsHumanReview ? "登记人工审核" : "正式发送给 AI"}
             </button>
           </div>
           <p className={styles.microCopy}>这条是开发工坊主链入口之一。预演通过后再入池；如果涉及硬件/发布/删除等高风险语义，会先进入人工审核。</p>
        </form>
          );
        })()}
      </div>
    );
  }

  function renderAiDebugPanel() {
    const governedSeats = mapSeatPayload.filter((seat) => seat.protocolTokenSummary || seat.protocolRunawaySummary);
    const reviewSeats = mapSeatPayload.filter(
      (seat) => seat.protocolApprovalPolicy === "human_review_required" || seat.protocolHardwareWriteRequiresReview,
    );
    const autonomousSeats = mapSeatPayload.filter((seat) => seat.automationEnabled);
    const debugTargets = mapSeatPayload.slice(0, 6);

    return (
      <div className={styles.managerStageStack}>
        <section className={styles.managerObjectHero}>
          <span className={styles.managerObjectSprite}>调</span>
          <div>
            <span className={styles.managerEyebrow}>AI 协作调试台</span>
            <h3>先看 AI 会不会乱跑，再决定要不要开自动化</h3>
            <p>
              这里面向开发者和用户一起看：每个 NPC 都要带 token 预算、自动轮次上限、停止条件、只读探针和人审边界。
              关闭自动化时只跑当前指令，开启自动化后才按这些护栏持续推进。
            </p>
          </div>
        </section>

        <div className={styles.managerStatGrid}>
          <article><span>受治理 NPC</span><strong>{governedSeats.length}</strong></article>
          <article><span>持续自动化</span><strong>{autonomousSeats.length}</strong></article>
          <article><span>需人审边界</span><strong>{reviewSeats.length}</strong></article>
        </div>

        <section className={styles.managerPreviewPanel}>
          <span className={styles.managerEyebrow}>默认护栏</span>
          <h3>防 token 爆炸、防跑飞、防误动真实设备</h3>
          <div className={styles.managerCardGrid}>
            <article>
              <strong>Token 预算</strong>
              <p>纯软件默认单条 2500、单轮 8000、日预算 30000；机器人/嵌入式默认更保守，并超预算转人工审核。</p>
            </article>
            <article>
              <strong>跑飞停止</strong>
              <p>连续没有新进展、需求冲突、预算超限、越过账号/项目隔离、碰到敏感操作，必须停止并写回人审提醒。</p>
            </article>
            <article>
              <strong>效能策略</strong>
              <p>默认先做只读探针，相似阅读任务合批，纯软件允许小并发，真实设备相关任务并发上限更低。</p>
            </article>
          </div>
          <div className={styles.managerActionGrid}>
            <button type="button" onClick={() => openBackpackPanel("exchange")}>
              打开协作消息池
            </button>
            <button type="button" onClick={() => openBackpackPanel("machine-room")}>
              打开线程机房
            </button>
            <button type="button" onClick={() => openBackpackPanel("ai-simulation")}>
              去 AI 仿真
            </button>
          </div>
        </section>

        <div className={styles.listHead}>
          <strong>NPC 协作护栏抽样</strong>
          <span className={styles.stateBadge}>{`${debugTargets.length} / ${mapSeatPayload.length} 个`}</span>
        </div>
        <ul className={styles.list}>
          {debugTargets.length ? (
            debugTargets.map((seat) => (
              <li key={`ai-debug-seat-${seat.id}`} data-ai-debug-seat={seat.id}>
                <strong>{seat.name}</strong>
                <p>{`${collabProjectProfileLabel(seat.protocolProjectProfile)} / ${collabProtocolApprovalLabel(seat.protocolApprovalPolicy)} / ${seat.automationEnabled ? "持续自动化" : "单次执行"}`}</p>
                <div className={styles.chipRow}>
                  <span className={styles.miniChip}>{seat.protocolTokenSummary}</span>
                  <span className={styles.miniChip}>{seat.protocolRunawaySummary}</span>
                  <span className={styles.miniChip}>{seat.protocolEfficiencySummary}</span>
                  <span className={styles.miniChip}>{seat.protocolDebugSummary}</span>
                </div>
              </li>
            ))
          ) : (
            <li>
              <strong>还没有 NPC 可调试</strong>
              <p>先去 NPC 管理创建一个 NPC，平台会自动给它装上默认协作护栏。</p>
            </li>
          )}
        </ul>
      </div>
    );
  }

  function renderAiSimulationPanel() {
    const simulationStations = developmentWorkshopStations.filter((station) =>
      /(仿真|调试|串口|硬件|机器人|嵌入式|debug|simulation|serial)/i.test(
        [station.id, station.label, station.detail, station.mapLocation].map((item) => text(item, "")).join(" "),
      ),
    );
    const roboticsSeats = mapSeatPayload.filter(
      (seat) =>
        seat.protocolProjectProfile === "robotics" ||
        seat.protocolProjectProfile === "embedded" ||
        seat.protocolSimulationFirst ||
        seat.protocolHardwareWriteRequiresReview,
    );
    const softwareSeats = mapSeatPayload.filter((seat) => !roboticsSeats.some((candidate) => candidate.id === seat.id));

    return (
      <div className={styles.managerStageStack}>
        <section className={styles.managerObjectHero}>
          <span className={styles.managerObjectSprite}>仿</span>
          <div>
            <span className={styles.managerEyebrow}>AI 仿真沙盘</span>
            <h3>机器人先仿真，纯软件先沙盘验证</h3>
            <p>
              未来这里会接真实仿真器、串口波形、日志回放和 UI 沙盘。现在先把入口和协作边界固定下来：
              AI 可以提出计划、读取资料、跑只读检查，但真实设备动作必须人审。
            </p>
          </div>
        </section>

        <div className={styles.managerStatGrid}>
          <article><span>机器人/硬件 NPC</span><strong>{roboticsSeats.length}</strong></article>
          <article><span>纯软件 NPC</span><strong>{softwareSeats.length}</strong></article>
          <article><span>仿真相关工位</span><strong>{simulationStations.length}</strong></article>
        </div>

        <div className={styles.managerCardGrid}>
          <article>
            <strong>开发机器人视角</strong>
            <p>
              默认流程是需求澄清、只读环境探针、仿真或数字孪生、人工确认、再允许串口/烧录/GPIO/电机等真实动作。
              没有人审前，AI 只能写计划、读日志、生成测试脚本和说明。
            </p>
          </article>
          <article>
            <strong>开发纯软件视角</strong>
            <p>
              默认流程是拉 GitHub、确认分支、分配 NPC、预演派单、构建测试、截图验收、最终回复。
              允许有限自动续推，但删除、回滚、发布、跨账号数据读取仍然要人审。
            </p>
          </article>
          <article>
            <strong>AI 仿真入口占位</strong>
            <p>
              后续补接：机器人运动/传感器仿真、串口数据波形回放、软件功能沙盘、UI 自动验收、任务消耗评估。
              先把入口放稳，避免以后每个 AI 自己造一套。
            </p>
          </article>
        </div>

        <section className={styles.managerPreviewPanel}>
          <span className={styles.managerEyebrow}>下一步要接的功能</span>
          <h3>调试和仿真都走开发工坊，不直接散落到 NPC 页面</h3>
          <div className={styles.managerActionGrid}>
            <button type="button" onClick={() => openBackpackPanel("development-workshop")}>
              打开开发工坊
            </button>
            <button type="button" onClick={() => openBackpackPanel("serial-tv")}>
              打开串口电视
            </button>
            <button type="button" onClick={() => openBackpackPanel("ai-debug")}>
              打开 AI 调试
            </button>
          </div>
        </section>

        <div className={styles.listHead}>
          <strong>已存在的仿真/调试工位</strong>
          <span className={styles.stateBadge}>{`${simulationStations.length} 个`}</span>
        </div>
        <ul className={styles.list}>
          {simulationStations.length ? (
            simulationStations.map((station) => (
              <li key={`ai-simulation-station-${station.id}`}>
                <strong>{`${station.icon} ${station.label}`}</strong>
                <p>{station.detail}</p>
                <p className={styles.microCopy}>{`地图位置：${station.mapLocation} / 知识库：${station.knowledgeBase.handoffPath}`}</p>
              </li>
            ))
          ) : (
            <li>
              <strong>还没有仿真工位</strong>
              <p>去开发工坊添加“仿真数字孪生”或“可视化调试台”，之后会自动被这里收拢。</p>
            </li>
          )}
        </ul>
      </div>
    );
  }

  function renderSchedulePanel() {
    const todayKey = new Date().toISOString().slice(0, 10);
    const collaborationConfig =
      props.project?.collaboration_config && typeof props.project.collaboration_config === "object"
        ? (props.project.collaboration_config as AnyRecord)
        : {};
    const dailySchedule =
      collaborationConfig.daily_schedule && typeof collaborationConfig.daily_schedule === "object"
        ? (collaborationConfig.daily_schedule as Record<string, AnyRecord>)
        : {};
    const todaySchedule = dailySchedule[todayKey] ?? {};
    const scheduleTasks = sortedByUpdatedAt(props.tasks)
      .filter((task) => !["done", "cancelled"].includes(text(task.status, "").toLowerCase()))
      .slice(0, 6);
    const ddlReadyTasks = scheduleTasks.filter((task) => text(task.due_at ?? task.dueAt, ""));
    const scheduleTargetMap = new Map<string, { id: string; label: string; meta: string; providerLabel: string }>();
    mapSeatPayload.forEach((seat) => {
      const targetId = text(seat.sourceThreadId || seat.id, "");
      if (!targetId) return;
      scheduleTargetMap.set(targetId, {
        id: targetId,
        label: seat.name || targetId,
        meta: `NPC / ${seat.nodeName || "未绑定电脑"}`,
        providerLabel: seat.providerLabel || "AI",
      });
    });
    allThreadCandidates.forEach((thread) => {
      const targetId = text(thread.id ?? thread.workstation_id, "");
      if (!targetId || scheduleTargetMap.has(targetId)) return;
      scheduleTargetMap.set(targetId, {
        id: targetId,
        label: display(thread.name ?? thread.label, targetId),
        meta: `线程 / ${display(thread.computer_node_id ?? thread.computer_node, "未绑定电脑")}`,
        providerLabel: platformProviderLabelFromThread(thread),
      });
    });
    const scheduleTargets = Array.from(scheduleTargetMap.values());
    const taskBrief = scheduleTasks.length
      ? scheduleTasks
          .map((task, index) => {
            const dueAt = text(task.due_at ?? task.dueAt, "");
            return `${index + 1}. ${safeDisplayTitle(task.title, "未命名任务")} / 状态 ${text(task.status, "draft")} / DDL ${
              dueAt ? formatStamp(dueAt) : "未设置"
            }`;
          })
          .join("\n")
      : "当前没有待排程任务。";
    const aiPlanPrompt = `请基于今天的任务和 DDL，给出当日安排：\n${taskBrief}\n\n输出要求：先列优先级，再列上午/下午/晚上安排；标出需要人工审核的步骤；如果 DDL 不合理，请给出调整建议。`;
    const recentScheduleMessages = sortedByUpdatedAt(
      props.collaborationMessages.filter((message) => {
        const haystack = `${text(message.title, "")} ${text(message.body, "")}`.toLowerCase();
        return haystack.includes("日程") || haystack.includes("ddl") || haystack.includes("calendar");
      }),
    ).slice(0, 5);
    const schedulePreview =
      text(collaborationPreview?.preview_key, "") === "schedule-plan" ? collaborationPreview : null;
    const schedulePreviewReady = Boolean(schedulePreview?.ready);
    const schedulePreviewNeedsHumanReview = collaborationPreviewNeedsHumanReview(schedulePreview);

    return (
      <div className={styles.managerStageStack}>
        <section className={styles.managerObjectHero}>
          <span className={styles.managerObjectSprite}>历</span>
          <div>
            <span className={styles.managerEyebrow}>主房物件：日程日历</span>
            <h3>任务 DDL、每日安排、AI 当日排程</h3>
            <p>
              这不是 NPC 管理器里的子页面，而是主房墙上日历打开的独立二级管理器。先把 DDL 和今天怎么干写清楚，再让 AI
              生成当日执行顺序。
            </p>
          </div>
        </section>

        <div className={styles.managerStatGrid}>
          <article><span>待排程任务</span><strong>{scheduleTasks.length}</strong></article>
          <article><span>已有 DDL</span><strong>{ddlReadyTasks.length}</strong></article>
          <article><span>可安排 AI</span><strong>{scheduleTargets.length}</strong></article>
        </div>

        <form action={创建项目任务} className={styles.skillManagerForm} data-schedule-create-task-form="1">
          <strong>新增排程任务</strong>
          <p className={styles.microCopy}>不用先跑去任务田块：在日历里直接写任务、设 DDL，再让 AI 按今天来安排。</p>
          <input type="hidden" name="project_id" value={projectId} />
          <input type="hidden" name="status" value="ready" />
          <input type="hidden" name="return_to" value={scheduleReturnPath} />
          <div className={styles.skillManagerGrid}>
            <label className={styles.fieldLabel}>
              <span>任务标题</span>
              <input name="title" placeholder="例如：今晚完成 Claude 协作验收" required />
            </label>
            <label className={styles.fieldLabel}>
              <span>优先级</span>
              <select name="priority" className={styles.select} defaultValue="P1">
                <option value="P0">P0 / 今天必须收口</option>
                <option value="P1">P1 / 优先推进</option>
                <option value="P2">P2 / 正常推进</option>
                <option value="P3">P3 / 有空再做</option>
              </select>
            </label>
            <label className={styles.fieldLabel}>
              <span>DDL</span>
              <input name="due_at" type="datetime-local" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>任务说明</span>
              <textarea
                name="description"
                placeholder="把交付物、验收方式、需要哪个 AI 协作写清楚。比如：一个线程查资料，一个线程写初稿，最后汇总到最终回复池。"
              />
            </label>
          </div>
          <button type="submit" data-loading-label="正在新增任务">新增任务并留在日历</button>
        </form>

        <form action={保存项目日程安排.bind(null, projectId)} className={styles.skillManagerForm}>
          <strong>每日安排</strong>
          <p className={styles.microCopy}>保存后会写入项目协作配置，换电脑、换线程也能看到今天的安排。</p>
          <input type="hidden" name="return_to" value={scheduleReturnPath} />
          <div className={styles.skillManagerGrid}>
            <label className={styles.fieldLabel}>
              <span>日期</span>
              <input name="schedule_date" type="date" defaultValue={todayKey} />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>今天怎么安排</span>
              <textarea
                name="daily_plan"
                defaultValue={text(todaySchedule.daily_plan, "")}
                placeholder="例如：上午修登录和日历入口，下午验证 Codex/Claude 协作，晚上整理截图与交接。"
              />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>DDL 备注</span>
              <textarea
                name="ddl_note"
                defaultValue={text(todaySchedule.ddl_note, "")}
                placeholder="例如：18:00 前要看到最小回执，睡前必须有最终回复和截图。"
              />
            </label>
          </div>
          <button type="submit" data-loading-label="正在保存日程">保存每日安排</button>
        </form>

        <form action={submitCollaborationMessage} className={styles.skillManagerForm}>
          <strong>让 AI 安排今天</strong>
          <p className={styles.microCopy}>这条会走平台统一协作消息池，后续由 Codex、Claude、Qwen 等适配器领取。</p>
          {renderCollaborationPreviewCard(schedulePreview, "最近一次日程排程预演")}
          <input type="hidden" name="project_id" value={projectId} />
          <input type="hidden" name="message_type" value="agent_command" />
          <input type="hidden" name="sender_type" value="human" />
          <input type="hidden" name="sender_id" value={currentHumanSenderValue} />
          <input type="hidden" name="recipient_type" value="workstation" />
          <input type="hidden" name="status" value="queued" />
          <input type="hidden" name="return_to" value={scheduleReturnPath} />
          <input type="hidden" name="preview_key" value="schedule-plan" />
          <input type="hidden" name="enforce_preview" value="1" />
          <input type="hidden" name="required_preview_signature" value={text(schedulePreview?.preview_signature, "")} />
          <input type="hidden" name="required_preview_ready" value={schedulePreviewReady ? "1" : ""} />
          <div className={styles.skillManagerGrid}>
            <label className={styles.fieldLabel}>
              <span>交给哪个 AI</span>
              <select name="recipient_id" className={styles.select} defaultValue={scheduleTargets[0]?.id ?? ""}>
                {scheduleTargets.length ? (
                  scheduleTargets.map((target) => (
                    <option key={`schedule-target-${target.id}`} value={target.id}>
                      {`${target.label} · ${target.providerLabel} · ${target.meta}`}
                    </option>
                  ))
                ) : (
                  <option value="">先创建 NPC 或接入线程</option>
                )}
              </select>
            </label>
            <label className={styles.fieldLabel}>
              <span>标题</span>
              <input name="title" defaultValue="日程日历 / AI 安排今天" required />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>指令正文</span>
              <textarea name="body" defaultValue={aiPlanPrompt} required />
            </label>
          </div>
          <div className={styles.inlineActions}>
            <button
              type="submit"
              formAction={previewCollaborationMessage}
              disabled={!scheduleTargets.length}
              data-loading-label="正在预演 AI 排程"
            >
              先预演 AI 排程
            </button>
            <button
              type="submit"
              disabled={!scheduleTargets.length || !schedulePreviewReady}
              data-loading-label="正在登记 AI 排程"
             >
               {schedulePreviewNeedsHumanReview ? "登记人工审核" : "正式发送给 AI"}
             </button>
           </div>
           <p className={styles.microCopy}>日程也走同一套协作协议。预演通过才允许正式入池；高风险安排会先登记人工审核，不直接消耗远端 AI。</p>
        </form>

        <div className={styles.listHead}>
          <strong>任务 DDL</strong>
          <span className={styles.stateBadge}>{`${scheduleTasks.length} 条`}</span>
        </div>
        <ul className={styles.list}>
          {scheduleTasks.length ? (
            scheduleTasks.map((task) => {
              const taskId = text(task.id ?? task.task_id, "");
              const dueAt = text(task.due_at ?? task.dueAt, "");
              return (
                <li
                  key={`schedule-task-${taskId}`}
                  data-schedule-task-item={taskId || safeDisplayTitle(task.title, "未命名任务")}
                  data-schedule-task-title={safeDisplayTitle(task.title, "未命名任务")}
                >
                  <strong>{safeDisplayTitle(task.title, "未命名任务")}</strong>
                  <p>{`状态：${text(task.status, "draft")} / DDL：${dueAt ? formatStamp(dueAt) : "未设置"}`}</p>
                  <form action={更新任务DDL.bind(null, projectId, taskId)} className={styles.drawerForm}>
                    <input type="hidden" name="return_to" value={scheduleReturnPath} />
                    <label className={styles.fieldLabel}>
                      <span>DDL 时间</span>
                      <input name="due_at" type="datetime-local" defaultValue={formatDateTimeLocal(dueAt)} />
                    </label>
                    <label className={styles.fieldLabel}>
                      <span>备注</span>
                      <input name="note" placeholder="为什么调整这个 DDL？可选" />
                    </label>
                    <button type="submit" disabled={!taskId} data-loading-label="正在更新 DDL">更新 DDL</button>
                  </form>
                </li>
              );
            })
          ) : (
            <li>
              <strong>还没有可排程任务</strong>
              <p>先在任务田块或需求信箱创建任务，再回到主房日历安排 DDL。</p>
            </li>
          )}
        </ul>

        <div className={styles.listHead}>
          <strong>最近日程协作</strong>
          <span className={styles.stateBadge}>{`${recentScheduleMessages.length} 条`}</span>
        </div>
        <ul className={styles.list}>
          {recentScheduleMessages.length ? (
            recentScheduleMessages.map((message, index) => (
              <li key={text(message.id, `schedule-message-${index + 1}`)}>
                <strong>{text(message.title, "日程消息")}</strong>
                <p>{shortText(message.body, "没有正文", 150)}</p>
                <p className={styles.microCopy}>{formatStamp(message.updated_at ?? message.created_at)}</p>
              </li>
            ))
          ) : (
            <li>
              <strong>还没有日程消息</strong>
              <p>保存每日安排或让 AI 安排今天后，这里会出现日程相关的协作记录。</p>
            </li>
          )}
        </ul>
      </div>
    );
  }

  function renderSerialTvPanel() {
    const collaborationConfig =
      props.project?.collaboration_config && typeof props.project.collaboration_config === "object"
        ? (props.project.collaboration_config as AnyRecord)
        : {};
    const serialConfig =
      collaborationConfig.serial_debug_assistant && typeof collaborationConfig.serial_debug_assistant === "object"
        ? (collaborationConfig.serial_debug_assistant as AnyRecord)
        : {};
    const configuredSerialDevices = asArray(
      serialConfig.devices ?? serialConfig.serial_devices ?? serialConfig.usb_devices ?? serialConfig.last_scan?.devices,
    );
    const serialReturnPath = `/projects/${projectId}?panel=team&tab=serial-tv`;
    const defaultNodeId = text(onlineNodes[0]?.id ?? nodes[0]?.id, "");
    const baudRate = Number(serialConfig.baud_rate ?? 115200) || 115200;
    const channelNames = asArray(serialConfig.channel_names).length
      ? asArray(serialConfig.channel_names).map((item) => text(item, "")).filter(Boolean)
      : ["x", "y"];
    const serialMessages = sortedByUpdatedAt(
      props.collaborationMessages.filter((message) => {
        const haystack = `${text(message.title, "")} ${text(message.body, "")}`.toLowerCase();
        return haystack.includes("serial") || haystack.includes("usb") || haystack.includes("串口") || haystack.includes("波形");
      }),
    ).slice(0, 5);
    const serialDevices = mergeSerialDeviceLists(configuredSerialDevices, collectSerialDevicesFromMessages(serialMessages));
    const defaultPort = text(serialConfig.port ?? serialDevices[0]?.port ?? serialDevices[0]?.path, "");
    const sampleRows = Array.from({ length: 36 }, (_, index) => {
      const x = index;
      const y = Math.sin(index / 4) * 34 + Math.cos(index / 2.5) * 10;
      return { x, y };
    });
    const minY = Math.min(...sampleRows.map((row) => row.y));
    const maxY = Math.max(...sampleRows.map((row) => row.y));
    const yRange = Math.max(maxY - minY, 1);
    const wavePoints = sampleRows
      .map((row, index) => {
        const x = 24 + (index / Math.max(sampleRows.length - 1, 1)) * 420;
        const y = 120 - ((row.y - minY) / yRange) * 88;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
    const protocolText = [
      "默认协议 AICSV/1：UTF-8 文本，一行一帧，以 LF 结束。",
      "坐标帧：@xy,<x>,<y>，例如 @xy,12.5,33.1",
      "多通道波形帧：@sample,<t>,<ch1>,<ch2>...，例如 @sample,1024,1.2,3.4",
      "命令帧：@cmd,<name>,key=value;key=value，例如 @cmd,led,state=1",
      "兼容简写：纯数字 CSV 如 12.5,33.1 会按 x,y 解析。",
    ];

    return (
      <div className={styles.managerStageStack}>
        <section className={styles.managerObjectHero}>
          <span className={styles.managerObjectSprite}>波</span>
          <div>
            <span className={styles.managerEyebrow}>主房物件：串口电视</span>
            <h3>USB 扫描、串口收发、数字波形</h3>
            <p>
              电视机变成 VOFA+ 风格的串口调试助手：平台负责统一入口、协议和跨电脑下发；真正打开串口由各电脑 Runner 执行。
            </p>
          </div>
        </section>

        <div className={styles.managerStatGrid}>
          <article><span>可扫描电脑</span><strong>{nodes.length}</strong></article>
          <article><span>已记录设备</span><strong>{serialDevices.length}</strong></article>
          <article><span>默认波特率</span><strong>{baudRate}</strong></article>
        </div>

        <form action={请求串口USB扫描.bind(null, projectId)} className={styles.skillManagerForm}>
          <strong>扫描所有电脑的 USB / 串口设备</strong>
          <p className={styles.microCopy}>会向目标电脑下发 `serial.usb.scan` Runner 命令；Runner 回写后会进入最终回复池，并在这里提取显示 COM、ttyUSB、CH340、CP210x、STM32 VCP 等设备。</p>
          <input type="hidden" name="return_to" value={serialReturnPath} />
          <div className={styles.skillManagerGrid}>
            <label className={styles.fieldLabel}>
              <span>扫描范围</span>
              <select name="computer_node_id" className={styles.select} defaultValue="all">
                <option value="all">所有已接入电脑</option>
                {nodes.map((node, index) => {
                  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "");
                  return (
                    <option key={`serial-scan-node-${nodeId || index}`} value={nodeId}>
                      {display(node.label ?? node.name, nodeId || `电脑 ${index + 1}`)}
                    </option>
                  );
                })}
              </select>
            </label>
          </div>
          <button type="submit" disabled={!nodes.length} data-loading-label="正在下发 USB 扫描">扫描 USB / 串口</button>
        </form>

        <form action={保存串口电视配置.bind(null, projectId)} className={styles.skillManagerForm}>
          <strong>收发格式</strong>
          <p className={styles.microCopy}>先固定平台协议，后面你单片机只要按这里发横纵坐标，平台就能转波形。</p>
          <input type="hidden" name="return_to" value={serialReturnPath} />
          <div className={styles.skillManagerGrid}>
            <label className={styles.fieldLabel}>
              <span>协议</span>
              <select name="protocol" className={styles.select} defaultValue={text(serialConfig.protocol, "aicollab-csv-v1")}>
                <option value="aicollab-csv-v1">AICSV/1 · 文本 CSV 波形</option>
                <option value="vofa-firewater-compatible">FireWater 兼容 · CSV 文本</option>
                <option value="raw-terminal">RawData · 原始串口终端</option>
                <option value="justfloat-like">JustFloat-like · float32 小端数组</option>
              </select>
            </label>
            <label className={styles.fieldLabel}>
              <span>默认波特率</span>
              <input name="baud_rate" type="number" min="1200" step="1" defaultValue={baudRate} />
            </label>
            <label className={styles.fieldLabel}>
              <span>通道名</span>
              <input name="channel_names" defaultValue={channelNames.join(",")} placeholder="x,y,ch1,ch2" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>帧格式</span>
              <textarea
                name="frame_format"
                defaultValue={text(serialConfig.frame_format, "@xy,<x>,<y>\\n 或 @sample,<t>,<ch1>,<ch2>...\\n")}
              />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>备注</span>
              <textarea name="notes" defaultValue={text(serialConfig.notes, "")} placeholder="例如：主控板上报 @xy,x,y；x 是采样序号，y 是 ADC 电压。" />
            </label>
          </div>
          <button type="submit" data-loading-label="正在保存串口协议">保存收发格式</button>
        </form>

        <form action={下发串口调试指令.bind(null, projectId)} className={styles.skillManagerForm}>
          <strong>发送串口数据</strong>
          <p className={styles.microCopy}>这一步只下发给对应电脑 Runner，不在浏览器里直接碰本机串口，方便以后多电脑、多模型统一协作。</p>
          <input type="hidden" name="return_to" value={serialReturnPath} />
          <div className={styles.skillManagerGrid}>
            <label className={styles.fieldLabel}>
              <span>目标电脑</span>
              <select name="computer_node_id" className={styles.select} defaultValue={defaultNodeId}>
                {nodes.map((node, index) => {
                  const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, "");
                  return (
                    <option key={`serial-write-node-${nodeId || index}`} value={nodeId}>
                      {display(node.label ?? node.name, nodeId || `电脑 ${index + 1}`)}
                    </option>
                  );
                })}
              </select>
            </label>
            <label className={styles.fieldLabel}>
              <span>串口号</span>
              <input name="port" defaultValue={defaultPort} placeholder="COM3 或 /dev/ttyUSB0" />
            </label>
            <label className={styles.fieldLabel}>
              <span>波特率</span>
              <input name="baud_rate" type="number" defaultValue={baudRate} />
            </label>
            <label className={styles.fieldLabel}>
              <span>发送格式</span>
              <select name="payload_format" className={styles.select} defaultValue="text-lf">
                <option value="text-lf">文本 + LF</option>
                <option value="hex">HEX 字节</option>
                <option value="raw">原始字符串</option>
              </select>
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>发送内容</span>
              <textarea name="payload" placeholder="@cmd,start,rate=100 或 01 03 00 00 00 02 C4 0B" />
            </label>
          </div>
          <button type="submit" disabled={!nodes.length} data-loading-label="正在下发串口写入">发送到串口</button>
        </form>

        <section className={styles.managerPreviewPanel}>
          <div className={styles.listHead}>
            <strong>波形预览</strong>
            <span className={styles.stateBadge}>AICSV/1</span>
          </div>
          <svg viewBox="0 0 480 150" role="img" aria-label="串口数值波形预览" style={{ width: "100%", maxHeight: 180 }}>
            <rect x="0" y="0" width="480" height="150" rx="18" fill="rgba(8, 14, 8, 0.72)" />
            {[30, 60, 90, 120].map((y) => (
              <line key={`serial-grid-${y}`} x1="20" x2="460" y1={y} y2={y} stroke="rgba(235, 221, 126, 0.18)" />
            ))}
            <polyline points={wavePoints} fill="none" stroke="#e7dc68" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
            <text x="24" y="24" fill="#fff8d2" fontSize="13">示例：@xy,x,y / @sample,t,ch1,ch2...</text>
          </svg>
        </section>

        <div className={styles.listHead}>
          <strong>协议约定</strong>
          <span className={styles.stateBadge}>{channelNames.join(" / ")}</span>
        </div>
        <ul className={styles.list}>
          {protocolText.map((line) => (
            <li key={line}>
              <strong>{line.split("：")[0]}</strong>
              <p>{line.includes("：") ? line.slice(line.indexOf("：") + 1) : line}</p>
            </li>
          ))}
        </ul>

        <div className={styles.listHead}>
          <strong>已记录 USB / 串口设备</strong>
          <span className={styles.stateBadge}>{`${serialDevices.length} 个`}</span>
        </div>
        <ul className={styles.list}>
          {serialDevices.length ? (
            serialDevices.map((device, index) => (
              <li key={`serial-device-${text(device.port ?? device.path, String(index))}`}>
                <strong>{text(device.label ?? device.name, text(device.port ?? device.path, "未知设备"))}</strong>
                <p>{`${text(device.port ?? device.path, "未知端口")} / ${text(device.vendor_id ?? device.vid, "VID ?")} / ${text(device.product_id ?? device.pid, "PID ?")}`}</p>
              </li>
            ))
          ) : (
            <li>
              <strong>还没有设备清单</strong>
              <p>先点上方扫描。Runner 回写 `serial_devices` 后，这里会列出所有电脑的 USB/串口设备。</p>
            </li>
          )}
        </ul>

        <div className={styles.listHead}>
          <strong>最近串口协作</strong>
          <span className={styles.stateBadge}>{`${serialMessages.length} 条`}</span>
        </div>
        <ul className={styles.list}>
          {serialMessages.length ? (
            serialMessages.map((message, index) => (
              <li key={text(message.id, `serial-message-${index + 1}`)}>
                <strong>{text(message.title, "串口消息")}</strong>
                <p>{shortText(message.body, "没有正文", 150)}</p>
                <p className={styles.microCopy}>{formatStamp(message.updated_at ?? message.created_at)}</p>
              </li>
            ))
          ) : (
            <li>
              <strong>等待第一条串口回执</strong>
              <p>扫描、写入或 Runner 解析波形数据后，这里会显示最小回执和结果。</p>
            </li>
          )}
        </ul>
      </div>
    );
  }

  function resolveManagedComputer(selectionId?: string | null) {
    const focus = text(selectionId ?? computerFocusId, "").toLowerCase();
    const orderedNodes = sortedByUpdatedAt(nodes);
    if (!focus) return orderedNodes[0] ?? null;
    return (
      orderedNodes.find((node) =>
        uniqueStrings([node.id, node.node_id, node.name, node.label]).some((key) => key.toLowerCase() === focus),
      ) ?? orderedNodes[0] ?? null
    );
  }

  function resolveManagedComputerThreads(node: AnyRecord | null) {
    const nodeKeys = uniqueStrings([
      node?.id,
      node?.node_id,
      node?.config_id,
      node?.name,
      node?.label,
      node?.metadata?.computer_node_id,
      node?.metadata?.node_id,
    ]).map((item) => item.toLowerCase());
    if (!nodeKeys.length) return [];
    return sortedByUpdatedAt(
      allThreadCandidates.filter((thread) => {
        const threadNodeKeys = uniqueStrings([
          thread.computer_node_id,
          thread.computerNodeId,
          thread.computer_node,
          thread.computerNode,
          thread.metadata?.computer_node_id,
          thread.metadata?.computer_node,
        ]).map((item) => item.toLowerCase());
        return threadNodeKeys.some((key) => nodeKeys.includes(key));
      }),
    );
  }

  function resolveManagedSkill(selectionId?: string | null) {
    const focus = text(selectionId ?? skillFocusId, "").toLowerCase();
    const source = filteredSkills.length ? filteredSkills : skillLibrary;
    if (!focus) return source[0] ?? null;
    return (
      source.find((skill) =>
        uniqueStrings([skill.id, skill.label, skill.name]).some((key) => key.toLowerCase() === focus),
      ) ?? source[0] ?? null
    );
  }

  function npcConversationFor(selected: ReturnType<typeof resolveManagedSeat>) {
    const keys = new Set(
      uniqueStrings([selected.id, selected.sourceThreadId, selected.targetId, selected.name]).map((item) =>
        item.toLowerCase(),
      ),
    );
    if (!keys.size) return [];
    return sortedByUpdatedAt(
      props.collaborationMessages.filter((message) => {
        const messageKeys = uniqueStrings([
          message.agent_id,
          message.sender_id,
          message.recipient_id,
          message.workstation_id,
          message.source_workstation_id,
          message.metadata?.source_workstation_id,
          message.metadata?.recipient_id,
        ]).map((item) => item.toLowerCase());
        return messageKeys.some((key) => keys.has(key));
      }),
    ).slice(0, 8);
  }

  function collaborationBubbleLabel(message: AnyRecord) {
    const type = text(message.message_type, "").toLowerCase();
    if (type.includes("final") || type === "agent_result") return "最终回复";
    if (type.includes("ack")) return "最小回执";
    if (type.includes("command") || type.includes("dispatch")) return "发给 AI";
    return "协作消息";
  }

  function renderHumanPartyPanel() {
    const selectedPlayer = selectedHumanPartyPlayer;
    const selectedFleetGroup = selectedHumanPartyFleetGroup;
    const selectedComputers = selectedFleetGroup?.computers ?? [];
    const selectedPlayerRouteKeys = uniqueStrings(selectedPlayer?.routeKeys ?? []).slice(0, 6);
    const selectedPlayerViewLabel = selectedPlayer?.isCurrentPlayer ? currentPlayerViewLabel : "外部成员主角";
    const allowOwnerlessNodeFallback = humanPartyHud.length === 1;
    const ownerlessNodeFallbackLabel = selectedPlayer?.name ?? currentHumanPartyPlayer?.name ?? "";

    return (
      <div className={styles.managerStageStack}>
        <section className={styles.managerObjectHero}>
          <span className={styles.managerObjectSprite}>主</span>
          <div>
            <span className={styles.managerEyebrow}>二级：主角对象</span>
            <h3>{selectedPlayer?.name ?? "还没有项目主角"}</h3>
            <p>
              {selectedPlayer
                ? `${selectedPlayer.role} / ${selectedPlayer.ownership} / ${selectedPlayer.stateLabel} / Runner 心跳 ${selectedPlayer.onlineComputerCount}/${selectedPlayer.computerCount} 台 / 线程 ${selectedPlayer.threadCount} 条`
                : "这里按项目成员管理主角、名下电脑、线程和协作状态。先邀请协作者，让对方进入项目后再来这里看。"}
            </p>
          </div>
        </section>

        <div
          className={styles.managerStatGrid}
          data-human-presence-summary="true"
          data-human-project-online-count={String(projectPresentHumanPartyCount)}
          data-human-account-online-count={String(loggedInHumanPartyCount)}
        >
          <article><span>项目主角</span><strong>{humanPartyHud.length}</strong></article>
          <article><span>项目内在线</span><strong>{`${projectPresentHumanPartyCount}/${humanPartyHud.length}`}</strong></article>
          <article><span>账号在线</span><strong>{`${loggedInHumanPartyCount}/${humanPartyHud.length}`}</strong></article>
          <article><span>已接入电脑</span><strong>{connectedHumanPartyCount}</strong></article>
          <article><span>可协作玩家</span><strong>{threadedHumanPartyCount}</strong></article>
          <article><span>共享任务</span><strong>{sharedTaskSnapshot.count}</strong></article>
        </div>

        <div className={styles.managerActionGrid}>
          <button type="button" onClick={() => openHumanPartyPanel(selectedPlayer?.id)} disabled={!selectedPlayer}>
            锁定当前主角
          </button>
          <button type="button" onClick={() => openExchangeForHumanParty(selectedPlayer)} disabled={!selectedPlayer}>
            查看协作现场
          </button>
          <button type="button" onClick={() => openComputersForHumanParty(selectedPlayer)}>
            查看名下电脑
          </button>
        </div>

        {selectedPlayer ? (
          <>
            <section className={styles.managerPreviewPanel}>
              <div className={styles.listHead}>
                <strong>当前主角状态</strong>
                <span className={styles.stateBadge}>{selectedPlayer.stateLabel}</span>
              </div>
              <div
                className={styles.partyManagerMetaGrid}
                data-human-presence-selected-state={selectedPlayer.projectPresenceState}
              >
                <article>
                  <span>主角身份</span>
                  <strong>{selectedPlayer.identityLabel}</strong>
                  <p>{selectedPlayer.ownership}</p>
                </article>
                <article>
                  <span>账号登录</span>
                  <strong>{selectedPlayer.accountPresenceLabel}</strong>
                  <p>{selectedPlayer.accountPresenceAgeLabel ? `最近活动：${selectedPlayer.accountPresenceAgeLabel}` : "暂时没有账号活动记录"}</p>
                </article>
                <article>
                  <span>项目在线</span>
                  <strong>{selectedPlayer.projectPresenceLabel}</strong>
                  <p>
                    {selectedPlayer.projectPresenceAgeLabel
                      ? `最近进入：${selectedPlayer.projectPresenceAgeLabel}`
                      : "暂时没有进入当前项目的记录"}
                    {selectedPlayer.lastProjectPath ? ` / ${selectedPlayer.lastProjectPath}` : ""}
                  </p>
                </article>
                <article>
                  <span>当前状态</span>
                  <strong>{selectedPlayer.stateLabel}</strong>
                  <p>{selectedPlayer.stateHint}</p>
                </article>
                <article>
                  <span>当前查看</span>
                  <strong>{selectedPlayerViewLabel}</strong>
                  <p>{selectedPlayer.scene}</p>
                </article>
              </div>
            </section>

            <section className={styles.managerPreviewPanel}>
              <div className={styles.listHead}>
                <strong>名下电脑与线程</strong>
                <span className={styles.stateBadge}>{`Runner 心跳 ${selectedPlayer.onlineComputerCount}/${selectedPlayer.computerCount} 台 / ${selectedPlayer.threadCount} 条线程`}</span>
              </div>
              {selectedComputers.length ? (
                <ul className={styles.list}>
                  {selectedComputers.slice(0, 6).map((node, index) => {
                    const nodeId = text(node.id ?? node.node_id ?? node.name ?? node.label, `computer-${index + 1}`);
                    const nodeLabel = display(node.label ?? node.name, nodeId);
                    const nodeThreads = resolveManagedComputerThreads(node);
                    return (
                      <li key={`human-party-computer-${nodeId}`}>
                        <strong>{nodeLabel}</strong>
                        <p>
                          {`${resolveComputerOwnerLabel(node, ownerlessNodeFallbackLabel)} / ${computerRegistrationLabel(node)} / ${runnerWatchInfo(node).label}${isCurrentComputerOwner(node, props.currentUser as AnyRecord | null | undefined, allowOwnerlessNodeFallback) ? " / 当前账号" : ""}`}
                        </p>
                        <p>{`${nodeThreads.length} 条线程 / Runner ${text(node.runner_id, "未绑定")} / ${shortText(text(node.note ?? node.description, ""), "这台电脑已经归到当前主角名下。", 72)}`}</p>
                        <div className={styles.inlineActions}>
                          <button
                            type="button"
                            className={styles.ghostButton}
                            onClick={() => {
                              setComputerFocusId(nodeId);
                              openBackpackPanel("computers");
                            }}
                          >
                            去电脑接入管理
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className={styles.noticeCard}>
                  <strong>这位主角还没有名下电脑</strong>
                  <p>从这里直接去电脑接入管理，把这位主角要用的电脑和线程接进来，后面多人多电脑协作才会稳定。</p>
                </div>
              )}
            </section>

            <section className={styles.managerPreviewPanel}>
              <div className={styles.listHead}>
                <strong>协作路由别名</strong>
                <span className={styles.stateBadge}>{`${selectedPlayerRouteKeys.length} 条`}</span>
              </div>
              <div className={styles.partyManagerRouteRow}>
                {selectedPlayerRouteKeys.length ? (
                  selectedPlayerRouteKeys.map((routeKey) => (
                    <span key={`human-party-route-${selectedPlayer.id}-${routeKey}`} className={styles.partyHudTagIdle}>
                      {routeKey}
                    </span>
                  ))
                ) : (
                  <p className={styles.microCopy}>这位主角还没有稳定的协作路由别名。</p>
                )}
              </div>
            </section>
          </>
        ) : (
          <div className={styles.noticeCard}>
            <strong>还没有项目主角</strong>
            <p>先邀请协作者并让对方进入项目。项目成员一旦进入地图，这里就会变成稳定的主角对象管理器。</p>
          </div>
        )}
      </div>
    );
  }

  function renderComputerOnboardingGuide(node: AnyRecord | null, options: { alwaysShowScripts?: boolean; reconnectMode?: boolean } = {}) {
    const nodeId = text(node?.id ?? node?.node_id ?? node?.name ?? node?.label, "");
    if (!nodeId) return null;
    const visiblePairingToken = pairingNodeId === nodeId ? text(pairingToken, "") : "";
    const selectedThreads = resolveManagedComputerThreads(node);
    const hasRunner = Boolean(text(node?.runner_id, ""));
    const needsRunner = !hasRunner;
    const needsThreadSync = !selectedThreads.length;
    const alwaysShowScripts = Boolean(options.alwaysShowScripts);
    const reconnectMode = Boolean(options.reconnectMode);
    if (!visiblePairingToken && !needsRunner && !needsThreadSync && !alwaysShowScripts && !reconnectMode) return null;

    const runnerId = text(node?.runner_id, "") || suggestedComputerRunnerId(node ?? {});
    const serverUrl = text(props.computerConnectServerUrl, "http://127.0.0.1:3000");
    const workspaceHint = text(node?.git_root ?? node?.workspace_root, "");
    const nodeAutomationHeartbeatSeconds = normalizeAutomationHeartbeatSeconds(
      selectedThreads
        .map((thread) => asNumber(thread?.metadata?.automation_heartbeat_seconds))
        .filter((value): value is number => value !== null)
        .sort((left, right) => left - right)[0] ?? DEFAULT_AUTOMATION_HEARTBEAT_SECONDS,
    );
    const oneClickConnectCommand = visiblePairingToken
      ? buildComputerOneClickConnectCommand(serverUrl, projectId, node ?? {}, visiblePairingToken, runnerId)
      : "";
    const oneClickConnectBashCommand = visiblePairingToken
      ? buildComputerOneClickConnectBashCommand(serverUrl, projectId, node ?? {}, visiblePairingToken, runnerId)
      : "";
    const runnerWatchCommand = buildComputerRunnerWatchCommand(serverUrl, projectId, node ?? {}, runnerId, {
      pollSeconds: nodeAutomationHeartbeatSeconds,
    });
    const runnerWatchBashCommand = buildComputerRunnerWatchBashCommand(serverUrl, projectId, node ?? {}, runnerId, {
      pollSeconds: nodeAutomationHeartbeatSeconds,
    });
    const runnerWatchExecuteCommand = buildComputerRunnerWatchCommand(serverUrl, projectId, node ?? {}, runnerId, {
      executeProviderCli: true,
      pollSeconds: nodeAutomationHeartbeatSeconds,
    });
    const runnerWatchExecuteBashCommand = buildComputerRunnerWatchBashCommand(serverUrl, projectId, node ?? {}, runnerId, {
      executeProviderCli: true,
      pollSeconds: nodeAutomationHeartbeatSeconds,
    });
    const registerCommand = visiblePairingToken
      ? buildComputerRunnerRegisterCommand(serverUrl, node ?? {}, visiblePairingToken, runnerId)
      : "";
    const registerBashCommand = visiblePairingToken
      ? buildComputerRunnerRegisterBashCommand(serverUrl, node ?? {}, visiblePairingToken, runnerId)
      : "";
    const codexSyncCommand = buildComputerCodexThreadSyncCommand(serverUrl, projectId, node ?? {}, runnerId);
    const codexSyncBashCommand = buildComputerCodexThreadSyncBashCommand(serverUrl, projectId, node ?? {}, runnerId);
    const claudeSyncCommand = buildComputerClaudeThreadSyncCommand(serverUrl, projectId, node ?? {}, runnerId);
    const claudeSyncBashCommand = buildComputerClaudeThreadSyncBashCommand(serverUrl, projectId, node ?? {}, runnerId);
    const manualSyncCommand = buildComputerManualThreadSyncCommand(serverUrl, projectId, node ?? {}, runnerId);
    const manualSyncBashCommand = buildComputerManualThreadSyncBashCommand(serverUrl, projectId, node ?? {}, runnerId);
    const connectScriptUrl = buildRunnerScriptUrl(serverUrl, "connect-ai-collab-runner.ps1");
    const connectBashScriptUrl = buildRunnerScriptUrl(serverUrl, "connect-ai-collab-runner.sh");
    const codexScriptUrl = buildRunnerScriptUrl(serverUrl, "sync-codex-session-threads.ps1");
    const codexBashScriptUrl = buildRunnerScriptUrl(serverUrl, "sync-codex-session-threads.sh");
    const claudeScriptUrl = buildRunnerScriptUrl(serverUrl, "sync-claude-session-threads.ps1");
    const claudeBashScriptUrl = buildRunnerScriptUrl(serverUrl, "sync-claude-session-threads.sh");

    return (
      <details className={styles.adapterCommandCard} open={Boolean(visiblePairingToken || needsRunner || needsThreadSync || alwaysShowScripts || reconnectMode)}>
        <summary>
          {reconnectMode
            ? "重新连接这台电脑"
            : visiblePairingToken || needsRunner
            ? "下一步：把这台电脑真正接进平台"
            : needsThreadSync
              ? "下一步：把这台电脑的线程同步回平台"
              : "新版脚本 / 重新扫描命令"}
        </summary>
        <div data-computer-onboarding-guide={nodeId}>
          <p className={styles.microCopy}>
            在要接入的那台电脑上运行即可；如果已经 clone 仓库，建议在那台电脑自己的仓库根目录运行。
            {workspaceHint
              ? ` 当前登记路径：${workspaceHint}`
              : " 未填写工作区路径时，平台只扫描本机 AI 会话，不会把服务器当前目录当成远端项目路径。"}
          </p>
          <p className={styles.microCopy}>
            {reconnectMode
              ? "如果 Runner 掉线、心跳超时，直接在那台电脑原来的终端重新运行“自动化心跳 / 持续接单”命令；不需要重新建电脑，也不需要重新绑定线程。"
              : visiblePairingToken
              ? "推荐先复制“一键接入”命令：它只下载接入器、注册 runner、自动扫描 Codex / Claude 线程，跑完就退出；不会默认进入持续自动化。"
              : needsRunner
                ? "这台电脑还没接入 runner。先重新生成配对令牌，这里就会立刻出现第 1 条接入命令。"
                : needsThreadSync
                  ? "这台电脑已经接入 runner；如果线程还是 0，直接执行下面的同步命令，再回来点“扫描线程”。"
                  : "这台电脑已经接入过；如果远端脚本旧了、线程数量不对，直接从这里复制最新版同步命令重新扫。"}
          </p>
          <section className={styles.runnerScriptVersionCard} data-runner-script-version="2026-04-28-manual-bind">
            <div>
              <strong>当前平台下发的是新版接入脚本</strong>
              <p>
                这版会自动搜索 Codex / Claude 的常见会话目录；如果远端电脑还没有打开过对应 AI，脚本不会再红字退出，
                而是同步一个“待绑定线程槽”，让你能继续在平台里绑定 NPC 或提示对方打开 AI 后再扫。
              </p>
            </div>
            <ul>
              <li>Codex：先找 <code>.codex/session_index.jsonl</code>，没有索引就继续扫 <code>.codex/sessions</code>，两者都没有才生成 <code>codex-manual-{normalizeComputerRunnerSlug(nodeId)}</code>。</li>
              <li>Claude：找不到 <code>.claude</code> 或 live session 时生成 <code>claude-manual-{normalizeComputerRunnerSlug(nodeId)}</code>。</li>
              <li>不开自动化：平台只发送并执行当前这一条指令，目标线程回一次最终回复后结束。</li>
              <li>开自动化：再运行“自动化心跳 / 持续接单”命令，窗口保持打开；默认只做最小回执和写入本机 inbox prompt 文件。</li>
              <li>如果要让本机 AI CLI 自动产出最终回复，必须使用带 <code>-WatchExecuteProviderCli</code> 的高风险命令，并先确认该电脑适合执行。</li>
              <li>每次复制下面命令都会重新下载平台当前最新版脚本，不依赖旧聊天记录。</li>
            </ul>
            <div className={styles.runnerScriptLinkGrid}>
              <a href={connectScriptUrl} target="_blank" rel="noreferrer">一键接入脚本</a>
              <a href={connectBashScriptUrl} target="_blank" rel="noreferrer">Linux/macOS 接入脚本</a>
              <a href={codexScriptUrl} target="_blank" rel="noreferrer">Codex 扫描脚本</a>
              <a href={codexBashScriptUrl} target="_blank" rel="noreferrer">Linux/macOS Codex 扫描脚本</a>
              <a href={claudeScriptUrl} target="_blank" rel="noreferrer">Claude 扫描脚本</a>
              <a href={claudeBashScriptUrl} target="_blank" rel="noreferrer">Linux/macOS Claude 扫描脚本</a>
            </div>
          </section>
          {visiblePairingToken ? (
            <>
              <p className={styles.microCopy}><strong>第 1 步推荐：</strong>一键接入这台电脑，只注册 runner 并扫描线程，完成后 PowerShell 可以关闭。</p>
              <pre className={styles.commandBlock} data-computer-one-click-connect-command={nodeId}><code>{oneClickConnectCommand}</code></pre>
              <p className={styles.microCopy}><strong>Linux / macOS：</strong>在 bash 里注册 runner，并扫描本机 Codex / Claude 线程。</p>
              <pre className={styles.commandBlock} data-computer-one-click-connect-linux-command={nodeId}><code>{oneClickConnectBashCommand}</code></pre>
              <details className={styles.adapterCommandCard}>
                <summary>高级备用：分步注册 / 单独同步</summary>
                <p className={styles.microCopy}><strong>第 1 步：</strong>只注册 runner</p>
                <pre className={styles.commandBlock} data-computer-register-command={nodeId}><code>{registerCommand}</code></pre>
                <p className={styles.microCopy}><strong>Linux / macOS：</strong>只注册 runner</p>
                <pre className={styles.commandBlock} data-computer-register-linux-command={nodeId}><code>{registerBashCommand}</code></pre>
                <p className={styles.microCopy}><strong>第 2 步：</strong>只同步这台电脑最近的 Codex 线程</p>
                <pre className={styles.commandBlock} data-computer-codex-sync-command={nodeId}><code>{codexSyncCommand}</code></pre>
                <p className={styles.microCopy}><strong>Linux / macOS：</strong>只同步这台电脑最近的 Codex 线程</p>
                <pre className={styles.commandBlock} data-computer-codex-sync-linux-command={nodeId}><code>{codexSyncBashCommand}</code></pre>
                <p className={styles.microCopy}><strong>第 2 步可选：</strong>如果这台电脑开了 Claude 终端，也同步 Claude 线程</p>
                <pre className={styles.commandBlock} data-computer-claude-sync-command={nodeId}><code>{claudeSyncCommand}</code></pre>
                <p className={styles.microCopy}><strong>Linux / macOS：</strong>如果这台电脑开了 Claude 终端，也同步 Claude 线程</p>
                <pre className={styles.commandBlock} data-computer-claude-sync-linux-command={nodeId}><code>{claudeSyncBashCommand}</code></pre>
                <p className={styles.microCopy}><strong>第 2 步备用：</strong>如果现在只想先手动登记 1 条线程，用这条单线程同步命令</p>
                <pre className={styles.commandBlock} data-computer-manual-sync-command={nodeId}><code>{manualSyncCommand}</code></pre>
                <p className={styles.microCopy}><strong>Linux / macOS：</strong>手动登记 1 条线程</p>
                <pre className={styles.commandBlock} data-computer-manual-sync-linux-command={nodeId}><code>{manualSyncBashCommand}</code></pre>
              </details>
            </>
          ) : needsRunner ? (
            <div className={styles.noticeCard}>
              <strong>还差配对令牌</strong>
              <p>先点上面的“生成配对令牌”。平台不会把长期密钥塞进电脑对象里，所以每次真正接入前都要先签发一次令牌。</p>
            </div>
          ) : (
            <>
              <p className={styles.microCopy}><strong>同步 Codex：</strong>自动同步这台电脑最近的 Codex 线程</p>
              <pre className={styles.commandBlock} data-computer-codex-sync-command={nodeId}><code>{codexSyncCommand}</code></pre>
              <p className={styles.microCopy}><strong>Linux / macOS：</strong>自动同步这台电脑最近的 Codex 线程</p>
              <pre className={styles.commandBlock} data-computer-codex-sync-linux-command={nodeId}><code>{codexSyncBashCommand}</code></pre>
              <p className={styles.microCopy}><strong>同步 Claude：</strong>如果这台电脑开了 Claude 终端，也同步 Claude 线程</p>
              <pre className={styles.commandBlock} data-computer-claude-sync-command={nodeId}><code>{claudeSyncCommand}</code></pre>
              <p className={styles.microCopy}><strong>Linux / macOS：</strong>如果这台电脑开了 Claude 终端，也同步 Claude 线程</p>
              <pre className={styles.commandBlock} data-computer-claude-sync-linux-command={nodeId}><code>{claudeSyncBashCommand}</code></pre>
              <p className={styles.microCopy}><strong>备用：</strong>如果现在只想先手动登记 1 条线程，用这条单线程同步命令</p>
              <pre className={styles.commandBlock} data-computer-manual-sync-command={nodeId}><code>{manualSyncCommand}</code></pre>
              <p className={styles.microCopy}><strong>Linux / macOS：</strong>手动登记 1 条线程</p>
              <pre className={styles.commandBlock} data-computer-manual-sync-linux-command={nodeId}><code>{manualSyncBashCommand}</code></pre>
            </>
          )}
          <details className={styles.adapterCommandCard}>
            <summary>自动化心跳 / 持续接单（只在 NPC 已开启自动化时使用）</summary>
            <p className={styles.microCopy}>
              这条命令会复用已绑定 runner，并持续心跳、轮询平台 inbox。不开 NPC 自动化时不要运行它；
              不然每条平台指令都会被当成持续协作来处理，容易浪费 token。
            </p>
          <p className={styles.microCopy}>
            当前建议心跳间隔：{nodeAutomationHeartbeatSeconds} 秒。这个值来自本电脑已绑定 NPC 里最激进的心跳配置；如果没有 NPC 配置，则用默认 60 秒。
          </p>
          {reconnectMode ? (
            <p className={styles.microCopy} data-computer-reconnect-command-help={nodeId}>
              重连检查：命令执行后不要关闭终端；回到平台刷新，看到“常驻接单中”后再下发任务。Windows 复制 PowerShell 命令，Linux / macOS 复制 Bash 命令。
            </p>
          ) : null}
          <pre className={styles.commandBlock} data-computer-watch-command={nodeId}><code>{runnerWatchCommand}</code></pre>
            <p className={styles.microCopy}><strong>Linux / macOS：</strong>持续心跳 / 接单。</p>
            <pre className={styles.commandBlock} data-computer-watch-linux-command={nodeId}><code>{runnerWatchBashCommand}</code></pre>
            <details className={styles.adapterCommandCard}>
              <summary>高风险：允许本机 AI CLI 自动执行并回最终回复</summary>
              <p className={styles.microCopy}>
                只给可信电脑使用。其它电脑做阅读类验证时，先用上面的默认心跳，让它只写 inbox prompt 和最小回执。
              </p>
              <pre className={styles.commandBlock} data-computer-watch-execute-command={nodeId}><code>{runnerWatchExecuteCommand}</code></pre>
              <p className={styles.microCopy}><strong>Linux / macOS：</strong>允许本机 AI CLI 自动执行并回最终回复。</p>
              <pre className={styles.commandBlock} data-computer-watch-execute-linux-command={nodeId}><code>{runnerWatchExecuteBashCommand}</code></pre>
            </details>
          </details>
          <p className={styles.microCopy}>
            <strong>最后一步：</strong>回平台点“扫描线程”只负责刷新列表；是否持续协作由 NPC 自动化开关和上面的心跳命令决定。
          </p>
        </div>
      </details>
    );
  }
  function renderComputersPanel() {
    const selectedNode = resolveManagedComputer();
    const selectedNodeId = text(selectedNode?.id ?? selectedNode?.node_id ?? selectedNode?.name ?? selectedNode?.label, "");
    const selectedThreads = resolveManagedComputerThreads(selectedNode);
    const scan = selectedNode?.metadata?.thread_scan ?? {};
    const scanStatusLabel = formatComputerThreadScanStatus(scan.status);
    const allowOwnerlessNodeFallback = humanPartyHud.length === 1;
    const ownerlessNodeFallbackLabel =
      humanPartyHud.length === 1 ? humanPartyHud[0]?.name || humanPartyHud[0]?.ownership || "当前主角" : "";
    const selectedNodeOwner = selectedNode ? resolveComputerOwnerLabel(selectedNode, ownerlessNodeFallbackLabel) : "";
    const selectedNodeIsCurrentOwner = selectedNode
      ? isCurrentComputerOwner(selectedNode, props.currentUser as AnyRecord | null | undefined, allowOwnerlessNodeFallback)
      : false;
    const selectedWatch = runnerWatchInfo(selectedNode);

    return (
      <div className={styles.managerStageStack}>
        <section className={styles.managerObjectHero}>
          <span className={styles.managerObjectSprite}>电</span>
          <div>
            <span className={styles.managerEyebrow}>二级：电脑对象</span>
            <h3>{selectedNode ? text(selectedNode.label ?? selectedNode.name, selectedNodeId) : "还没有电脑"}</h3>
            <p>
              {selectedNode
                ? `归属 ${selectedNodeOwner}${selectedNodeIsCurrentOwner ? "（当前账号）" : ""} / ${computerRegistrationLabel(selectedNode)} / Runner ${text(selectedNode.runner_id, "未绑定")} / 接单 ${selectedWatch.label} / 线程 ${selectedThreads.length} 条`
                : "先点左侧 + 添加电脑，接入后再扫描 Codex、Claude、Qwen 等线程。"}
            </p>
          </div>
        </section>

        <div className={styles.managerStatGrid}>
          <article><span>全部电脑</span><strong>{nodes.length}</strong></article>
          <article><span>Runner 心跳</span><strong>{onlineNodes.length}</strong></article>
          <article><span>常驻接单</span><strong>{watchReadyNodes.length}</strong></article>
          <article><span>真实线程</span><strong>{realThreadCount}</strong></article>
          <article><span>已接入玩家</span><strong>{connectedHumanPartyCount}</strong></article>
        </div>

        <div
          className={watchReadyNodes.length ? styles.card : styles.noticeCard}
          data-computer-watch-summary="true"
          data-computer-watch-ready-count={String(watchReadyNodes.length)}
          data-computer-watch-blocked-count={String(watchBlockedNodes.length)}
          data-computer-queued-command-count={String(queuedCollaborationCommandCount)}
        >
          <strong>
            {watchReadyNodes.length
              ? `当前有 ${watchReadyNodes.length} 台电脑能常驻接单`
              : queuedCollaborationCommandCount
                ? "有平台指令排队，但当前没有电脑在常驻接单"
                : "当前没有电脑在常驻接单"}
          </strong>
          <p>
            {watchReadyNodes.length
              ? `可自动领取平台派工；仍有 ${queuedCollaborationCommandCount} 条指令处于队列/等待态，必要时进入“协作消息池”查看回执。`
              : `平台已经登记 ${nodes.length} 台电脑、扫描到 ${realThreadCount} 条线程，但自动协作需要远端电脑保持“自动化心跳 / 持续接单”窗口运行。`}
          </p>
        </div>

        {selectedNode && !selectedWatch.active ? (
          <div
            className={selectedWatch.needsAttention ? styles.noticeCard : styles.card}
            data-computer-watch-state={selectedWatch.state}
            data-computer-watch-node={selectedNodeId}
          >
            <strong>{selectedWatch.label}</strong>
            <p>
              {selectedWatch.detail}。扫描到线程不等于正在接单；要让平台派工被自动领取，需要在那台电脑保持“自动化心跳 / 持续接单”窗口运行。
            </p>
            {text(selectedNode.runner_id, "") ? renderComputerOnboardingGuide(selectedNode, { reconnectMode: true }) : null}
          </div>
        ) : null}

        {pairingToken ? (() => {
          const pairingNode = resolveManagedComputer(pairingNodeId) ?? {};
          const pairingServerUrl = text(props.computerConnectServerUrl, "http://127.0.0.1:3000");
          const pairingRunnerId = text(pairingNode.runner_id, "") || suggestedComputerRunnerId(pairingNode);
          const pairingCommand = buildComputerOneClickConnectCommand(
            pairingServerUrl,
            projectId,
            pairingNode,
            pairingToken,
            pairingRunnerId,
          );
          const pairingWatchCommand = buildComputerOneClickConnectCommand(
            pairingServerUrl,
            projectId,
            pairingNode,
            pairingToken,
            pairingRunnerId,
            { watch: true, executeProviderCli: true },
          );
          return (
            <TokenResultCard
              title="电脑配对令牌已生成"
              subtitle={pairingNodeId ? `电脑 ${pairingNodeId}` : undefined}
              token={pairingToken}
              command={pairingCommand}
              watchCommand={pairingWatchCommand}
              testId="computer-pairing"
            />
          );
        })() : null}

        {watchBlockedNodes.length ? (
          <div className={styles.noticeCard} data-computer-watch-blocked-count={String(watchBlockedNodes.length)}>
            <strong>有 {watchBlockedNodes.length} 台电脑已登记但没有稳定接单</strong>
            <p>
              平台可以继续派工，但这些目标只会堆在队列里。优先打开对应电脑的三级抽屉，复制“自动化心跳 / 持续接单”命令并保持窗口运行。
            </p>
            <div className={styles.chipRow} data-computer-watch-recovery-list="true">
              {watchBlockedNodes.map((node, index) => {
                const nodeId = text(node.id ?? node.node_id ?? node.name, `blocked-node-${index + 1}`);
                const nodeWatch = runnerWatchInfo(node);
                return (
                  <button
                    key={`watch-recovery-${nodeId}`}
                    type="button"
                    className={`${styles.inlineActionLink} ${styles.ghostButton}`}
                    data-computer-watch-recovery-node={nodeId}
                    onClick={() => openManagerDrawer("computer-threads", nodeId)}
                  >
                    {`${display(node.name ?? node.label, nodeId)}：${nodeWatch.label}，打开恢复命令`}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        <div className={styles.managerActionGrid}>
          <button type="button" onClick={() => openManagerDrawer("computer-connect")} data-computer-open-create="true">添加电脑</button>
          <button
            type="button"
            onClick={() => openManagerDrawer("computer-threads", selectedNodeId)}
            disabled={!selectedNodeId}
            data-computer-open-threads={selectedNodeId || ""}
          >
            配对 / 扫描线程
          </button>
        </div>


        {renderComputerOnboardingGuide(selectedNode)}
        <section className={styles.managerPreviewPanel} data-computer-fleet-board="true">
          <div className={styles.listHead}>
            <strong>玩家机队</strong>
            <span className={styles.stateBadge}>{`${computerFleetGroups.length} 组`}</span>
          </div>
          {computerFleetGroups.length ? (
            <div className={styles.computerFleetGrid}>
              {computerFleetGroups.map((group) => (
                <article
                  key={`computer-fleet-${group.id}`}
                  className={styles.computerFleetGroup}
                  data-computer-fleet-group={group.id}
                  data-computer-fleet-name={group.name}
                  data-computer-fleet-computers={String(group.computerCount)}
                  data-computer-fleet-threads={String(group.threadCount)}
                >
                  <div className={styles.computerFleetHead}>
                    <div>
                      <span className={group.isCurrentPlayer ? styles.partyHudTagCurrent : styles.partyHudTag}>
                        {group.identityLabel}
                      </span>
                      <strong>{group.name}</strong>
                    </div>
                    <span
                      className={
                        group.stateLabel === "被阻塞"
                          ? styles.partyHudTagReview
                          : group.stateLabel === "处理中"
                            ? styles.partyHudTagActive
                            : styles.partyHudTagIdle
                      }
                    >
                      {group.stateLabel}
                    </span>
                  </div>
                  <p className={styles.computerFleetMeta}>
                    {`Runner 心跳 ${group.onlineComputerCount}/${group.computerCount} 台 / ${group.threadCount} 条线程`}
                  </p>
                  <ul className={styles.computerFleetNodeList}>
                    {group.computers.slice(0, 4).map((node, index) => {
                      const nodeId = text(node.id ?? node.node_id ?? node.name, `fleet-node-${index + 1}`);
                      const nodeWatch = runnerWatchInfo(node);
                      return (
                        <li key={`${group.id}-${nodeId}`} data-computer-fleet-node={nodeId}>
                          <button
                            type="button"
                            className={styles.inlineActionLink}
                            onClick={() => {
                              setPendingActionLabel(null);
                              setManagerDrawer(null);
                              setComputerFocusId(nodeId);
                            }}
                          >
                            {display(node.name ?? node.label, nodeId)}
                          </button>
                          <span>{nodeWatch.active ? nodeWatch.label : `${computerRegistrationLabel(node)} / ${nodeWatch.label}`}</span>
                        </li>
                      );
                    })}
                  </ul>
                </article>
              ))}
            </div>
          ) : (
            <p className={styles.objectRailEmpty}>还没有玩家机队。先接入至少一台电脑，这里就会按玩家归组显示。</p>
          )}
        </section>

        <section className={styles.managerPreviewPanel} data-computer-thread-preview-for={selectedNodeId || ""}>
          <div className={styles.listHead}>
            <strong>这台电脑的线程</strong>
            <span className={styles.stateBadge}>{selectedThreads.length} 条</span>
          </div>
          <ul
            className={`${styles.managerObjectList} ${styles.threadPreviewList}`}
            data-computer-thread-rendered-count={String(selectedThreads.length)}
          >
            {selectedThreads.length ? (
              selectedThreads.map((thread, index) => {
                const threadId = text(thread.id ?? thread.workstation_id, "");
                const boundSeat = seatBySourceThreadId.get(threadId) ?? seatBySourceThreadId.get(threadId.toLowerCase()) ?? null;
                return (
                  <li key={`${selectedNodeId}-${threadId || index}`} data-computer-thread-item={threadId || `thread-${index + 1}`}>
                    <strong>{display(thread.name, threadId || `线程 ${index + 1}`)}</strong>
                    <p>{platformProviderLabelFromThread(thread)} / {boundSeat ? `已绑定 ${text(boundSeat.name, "NPC")}` : "未绑定 NPC"}</p>
                  </li>
                );
              })
            ) : (
              <li>
                <strong>{selectedNode ? "还没有线程结果" : "还没有电脑"}</strong>
                <p>{selectedNode ? (text(scan.status, "").toLowerCase() === "awaiting_runner" ? "这台电脑还没接入 runner。先运行上面的接入命令，再回来扫描线程。" : "打开三级抽屉生成配对令牌或扫描线程。") : "添加电脑后，这里会显示该电脑上的线程。"}</p>
              </li>
            )}
          </ul>
          {selectedThreads.length ? (
            <p className={styles.microCopy} data-computer-thread-count-summary={String(selectedThreads.length)}>
              已加载并渲染全部 {selectedThreads.length} 条线程；屏幕高度不够时可在列表内滚动，或点“配对 / 扫描线程”进入三级抽屉看完整明细。
            </p>
          ) : null}
          {selectedNode ? (
            <p className={styles.microCopy} data-computer-thread-scan-status={selectedNodeId || ""}>
              扫描状态：{scanStatusLabel} / 最近时间：{formatStamp(scan.completed_at ?? scan.requested_at)}
            </p>
          ) : null}
        </section>
      </div>
    );
  }

  function renderNpcPanel() {
    const selected = resolveManagedSeat();
    const conversation = npcConversationFor(selected);
    const selectedPosterAvatar = selected.id ? posterNpcAvatarForSeat(selected, 0) : "";

    return (
      <div className={styles.managerStageStack}>
        <section
          className={styles.managerObjectHero}
          data-npc-manager-selected={selected.id || ""}
          data-npc-manager-selected-name={selected.name || ""}
          data-npc-manager-selected-thread={selected.sourceThreadId || ""}
        >
          {selectedPosterAvatar ? (
            <span
              className={styles.managerObjectSprite}
              data-poster-npc-hero-avatar="true"
              style={{ backgroundImage: `url("${selectedPosterAvatar}")` }}
              aria-hidden="true"
            />
          ) : (
            <span className={styles.managerObjectSprite}>精</span>
          )}
          <div>
            <span className={styles.managerEyebrow}>二级：NPC 精灵对象</span>
            <h3>{selected.id ? selected.name : "还没有 NPC"}</h3>
            <p>
              {selected.id
                ? `${selected.role} / ${selected.providerLabel} / ${selected.sourceThreadId ? `线程 ${selected.sourceThreadId}` : "未绑定线程"} / ${selected.automationEnabled ? "自动化已开" : "单次执行"}`
                : "点击左侧 + 添加 NPC，创建后会在地图随机点出现一个可交互精灵。"}
            </p>
          </div>
        </section>

        <div className={styles.managerStatGrid}>
          <article><span>NPC</span><strong>{codexSeats.length}</strong></article>
          <article><span>固定 Skill</span><strong>{baselineSkills.length}</strong></article>
          <article><span>最近消息</span><strong>{conversation.length}</strong></article>
        </div>

        <div className={styles.managerActionGrid}>
          {selected.id ? (
            <>
              <Link href={buildNpcSeatSurfaceHref(selected.id, "npc-dialog")} data-npc-open-dialog="1">
                打开对话框
              </Link>
              <Link href={buildNpcSeatSurfaceHref(selected.id, "npc-profile")} data-npc-open-profile="1">
                属性 / 知识库
              </Link>
              <Link href={buildNpcSeatSurfaceHref(selected.id, "npc-bind")}>绑定线程</Link>
              <Link href={buildNpcSeatSurfaceHref(selected.id, "npc-skills")}>装配 Skill</Link>
            </>
          ) : (
            <>
              <button type="button" data-npc-open-dialog="1" disabled>打开对话框</button>
              <button type="button" data-npc-open-profile="1" disabled>属性 / 知识库</button>
              <button type="button" disabled>绑定线程</button>
              <button type="button" disabled>装配 Skill</button>
            </>
          )}
        </div>

        <section className={styles.managerPreviewPanel}>
          <div className={styles.listHead}>
            <strong>对话预览</strong>
            <span className={styles.stateBadge}>{conversation.length} 条</span>
          </div>
          <ul className={styles.managerObjectList}>
            {conversation.length ? (
              conversation.slice(0, 4).map((message, index) => (
                <li key={text(message.id, `npc-message-${index}`)}>
                  <strong>{collaborationBubbleLabel(message)}：{text(message.title, "无标题")}</strong>
                  <p>{shortText(message.body, "没有正文", 120)}</p>
                </li>
              ))
            ) : (
              <li>
                <strong>{selected.id ? "还没有对话" : "还没有选中 NPC"}</strong>
                <p>{selected.id ? "点“打开对话框”后，可以直接给这个 AI 发指令。" : "先创建或选择一个 NPC。"}</p>
              </li>
            )}
          </ul>
        </section>
      </div>
    );
  }
  function renderMachineRoomPanel() {
    const sortedThreads = sortedByUpdatedAt(machineRoomVisibleWorkstations);
    const machineRoomThreadModels = sortedThreads.map((thread, index) => {
      const threadId = text(thread.id ?? thread.workstation_id ?? thread.config_id, "");
      const isSeatBackedWorkstation = isNpcSeatWorkstation(thread);
      const boundSeat = isSeatBackedWorkstation
        ? thread
        : seatBySourceThreadId.get(threadId) ?? seatBySourceThreadId.get(threadId.toLowerCase()) ?? null;
      const boundSeatView = boundSeat ? resolveSeatViewForRecord(boundSeat, seatPayloadMap) : null;
      const boundSeatId = boundSeat ? preferredSeatRouteId(boundSeat, boundSeatView) : "";
      const providerId = platformProviderIdFromThread(thread);
      const threadBootstrapIssue = threadBootstrapBlocker(thread);
      const executionProfile = machineRoomExecutionByWorkstationId.get(threadId) ?? null;
      const activityProfile = buildWorkstationActivitySummary(thread, props.collaborationMessages);
      const recoveryProfile = buildWorkstationRecoverySummary({
        providerId,
        executionProfile,
        activityProfile,
        boundSeat,
        threadBootstrapIssue,
      });
      return {
        thread,
        threadId,
        index,
        boundSeat,
        boundSeatView,
        boundSeatId,
        isSeatBackedWorkstation,
        focusLabel: boundSeat?.name ? text(boundSeat.name, display(thread.name, threadId)) : display(thread.name, threadId),
        routeKeys: uniqueStrings([
          ...workstationRouteKeys(thread),
          ...(boundSeat ? seatRouteKeys(boundSeat) : []),
          text(boundSeat?.name, ""),
          boundSeatId,
        ]),
        providerId,
        executionProfile,
        activityProfile,
        recoveryProfile,
      };
    });
    const machineRoomAttentionThreads = machineRoomThreadModels
      .filter((item) => item.recoveryProfile.needsAttention)
      .sort((left, right) => {
        const severityDiff =
          workstationRecoverySeverityRank(right.recoveryProfile.severity) -
          workstationRecoverySeverityRank(left.recoveryProfile.severity);
        if (severityDiff !== 0) return severityDiff;
        const signalDiff = activityMomentValue(left.activityProfile.latestSignalAt) - activityMomentValue(right.activityProfile.latestSignalAt);
        if (signalDiff !== 0) return signalDiff;
        return left.index - right.index;
      });
    const machineRoomCriticalCount = machineRoomAttentionThreads.filter((item) => item.recoveryProfile.severity === "critical").length;
    const machineRoomWarningCount = machineRoomAttentionThreads.filter((item) => item.recoveryProfile.severity === "warning").length;
    const machineRoomWaitingFirstSignalCount = machineRoomAttentionThreads.filter((item) =>
      ["awaiting-first-signal", "awaiting-first-signal-after-command"].includes(item.recoveryProfile.code),
    ).length;
    const machineRoomTokenGapCount = machineRoomAttentionThreads.filter((item) => item.recoveryProfile.code === "token-missing").length;
    const focusedMachineRoomItem =
      machineRoomThreadModels.find((item) => item.threadId === machineRoomFocusThreadId) ?? null;
    const historicalMachineRoomFocus =
      !focusedMachineRoomItem && machineRoomFocusThreadId ? buildHistoricalExchangeFocus(machineRoomFocusThreadId) : null;

    const renderMachineRoomRecoveryDispatchForm = (
      item: (typeof machineRoomThreadModels)[number],
      heading = "一键最小检查",
      description = "不用自己写文案，平台会自动生成一条标准检查指令，先让这条线程回最小回执，再补当前可接单状态。",
    ) => {
      const recoveryPreviewKey = machineRoomRecoveryPreviewKey(item.threadId);
      const recoveryPreview =
        text(collaborationPreview?.preview_key, "") === recoveryPreviewKey ? collaborationPreview : null;
      const recoveryPreviewReady = Boolean(recoveryPreview?.ready);
      const recoveryPreviewNeedsHumanReview = collaborationPreviewNeedsHumanReview(recoveryPreview);
      const recoveryTitle = machineRoomRecoveryCommandTitle(item.thread);
      const recoveryBody = machineRoomRecoveryCommandBody(item.thread, item.recoveryProfile);
      return (
        <form
          action={submitCollaborationMessage}
          className={styles.skillManagerForm}
          data-machine-thread-recovery-preview-form={item.threadId}
        >
          <strong>{heading}</strong>
          <p className={styles.microCopy}>{description}</p>
          <div data-machine-thread-recovery-preview-card={item.threadId}>
            {renderCollaborationPreviewCard(recoveryPreview, "最近一次机房最小检查预演")}
          </div>
          <input type="hidden" name="project_id" value={projectId} />
          <input type="hidden" name="message_type" value="agent_command" />
          <input type="hidden" name="sender_type" value="human" />
          <input type="hidden" name="sender_id" value={currentHumanSenderValue} />
          <input type="hidden" name="recipient_type" value="workstation" />
          <input type="hidden" name="recipient_id" value={item.threadId} />
          <input type="hidden" name="status" value="queued" />
          <input type="hidden" name="return_to" value={machineRoomReturnPath} />
          <input type="hidden" name="preview_key" value={recoveryPreviewKey} />
          <input type="hidden" name="enforce_preview" value="1" />
          <input type="hidden" name="required_preview_signature" value={text(recoveryPreview?.preview_signature, "")} />
          <input type="hidden" name="required_preview_ready" value={recoveryPreviewReady ? "1" : ""} />
          <input type="hidden" name="title" value={recoveryTitle} />
          <input type="hidden" name="body" value={recoveryBody} />
          <div className={styles.inlineActions}>
            <button
              type="submit"
              formAction={previewCollaborationMessage}
              data-loading-label={`正在预演 ${display(item.thread.name, item.threadId)} 的最小检查`}
            >
              先预演最小检查
            </button>
            <button
              type="submit"
              disabled={!recoveryPreviewReady}
              data-loading-label={`正在正式发送 ${display(item.thread.name, item.threadId)} 的最小检查`}
             >
               {recoveryPreviewNeedsHumanReview ? "登记人工审核" : "正式派最小检查"}
             </button>
          </div>
        </form>
      );
    };

    return (
      <div className={styles.panelStack}>
        <div className={styles.noticeCard}>
          <strong>线程列表</strong>
          <p>这里直接看真实线程，并把某个线程顺手变成 NPC。商业可用的路径应该是“看见线程就能绑定”，不是再回忆一遍线程名。</p>
        </div>

        {focusedMachineRoomItem ? (
          <div
            className={`${styles.noticeCard} ${styles.featureCardFocused}`}
            data-machine-room-focus-banner={focusedMachineRoomItem.threadId}
            data-machine-thread-card={focusedMachineRoomItem.threadId}
          >
            <strong>{`当前聚焦：${display(focusedMachineRoomItem.thread.name, focusedMachineRoomItem.threadId)}`}</strong>
            <p>
              {focusedMachineRoomItem.isSeatBackedWorkstation ? "这是一个 seat-backed NPC 工位。" : "这是一个真实线程执行位。"}
              {` 当前状态：${focusedMachineRoomItem.recoveryProfile.label} / ${focusedMachineRoomItem.activityProfile.activityHealthLabel}。`}
            </p>
            <div className={styles.chipRow}>
              <span className={styles.miniChip}>
                {focusedMachineRoomItem.isSeatBackedWorkstation ? "seat-backed 工位" : "真实线程"}
              </span>
              {focusedMachineRoomItem.activityProfile.latestCommandAt ? (
                <span className={styles.miniChip}>
                  {focusedMachineRoomItem.activityProfile.latestCommandTypeLabel} {formatStamp(focusedMachineRoomItem.activityProfile.latestCommandAt)}
                </span>
              ) : null}
              {focusedMachineRoomItem.activityProfile.latestAckAt ? (
                <span className={styles.miniChip}>最近回执 {formatStamp(focusedMachineRoomItem.activityProfile.latestAckAt)}</span>
              ) : null}
              {focusedMachineRoomItem.activityProfile.latestFinalReplyAt ? (
                <span className={styles.miniChip}>最近最终回复 {formatStamp(focusedMachineRoomItem.activityProfile.latestFinalReplyAt)}</span>
              ) : null}
            </div>
            {focusedMachineRoomItem.routeKeys.length ? (
              <div className={styles.inlineActions}>
                <button
                  type="button"
                  className={styles.ghostButton}
                  data-machine-room-open-exchange={focusedMachineRoomItem.threadId}
                  onClick={() => openExchangeFocusScene(focusedMachineRoomItem.focusLabel, focusedMachineRoomItem.routeKeys)}
                >
                  回到协作现场
                </button>
                {focusedMachineRoomItem.boundSeatId ? (
                  <button
                    type="button"
                    className={styles.ghostButton}
                    data-machine-room-open-seat-profile={focusedMachineRoomItem.boundSeatId}
                    onClick={() => openNpcProfileFromExchange(focusedMachineRoomItem.boundSeatId)}
                  >
                    看 NPC 属性
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {!focusedMachineRoomItem && historicalMachineRoomFocus ? (
          <div
            className={`${styles.noticeCard} ${styles.featureCardFocused}`}
            data-machine-room-history-banner={machineRoomFocusThreadId}
            data-machine-thread-card={machineRoomFocusThreadId}
          >
            <strong>{`当前聚焦：历史线程 ${machineRoomFocusThreadId}`}</strong>
            <p>
              这条线程当前不在 live 机房可见列表里，但它仍然被协作证据引用。
              {historicalMachineRoomFocus.proof
                ? " 这说明我们至少还有一条 proof 能把它和项目现场对应起来。"
                : " 这说明它还留有历史协作消息，需要按历史锚点继续排查。"}
            </p>
            <div className={styles.chipRow}>
              <span className={styles.miniChip}>历史线程锚点</span>
              {historicalMachineRoomFocus.proof?.providerLabel ? (
                <span className={styles.miniChip}>{`Provider ${historicalMachineRoomFocus.proof.providerLabel}`}</span>
              ) : null}
              {historicalMachineRoomFocus.proof?.computerNodeLabel ? (
                <span className={styles.miniChip}>{`电脑 ${historicalMachineRoomFocus.proof.computerNodeLabel}`}</span>
              ) : null}
              {historicalMachineRoomFocus.proof?.requirementId ? (
                <span className={styles.miniChip}>{`Requirement ${historicalMachineRoomFocus.proof.requirementId.slice(0, 8)}`}</span>
              ) : null}
              {historicalMachineRoomFocus.message?.updated_at || historicalMachineRoomFocus.message?.created_at ? (
                <span className={styles.miniChip}>
                  {`最近协作 ${formatStamp(
                    text(
                      historicalMachineRoomFocus.message?.updated_at ?? historicalMachineRoomFocus.message?.created_at,
                      "",
                    ),
                  )}`}
                </span>
              ) : null}
            </div>
            <p className={styles.microCopy}>{historicalMachineRoomFocus.summary}</p>
            {historicalMachineRoomFocus.routeKeys.length ? (
              <div className={styles.inlineActions}>
                <button
                  type="button"
                  className={styles.ghostButton}
                  data-machine-room-open-exchange-history={machineRoomFocusThreadId}
                  onClick={() =>
                    openExchangeFocusScene(
                      historicalMachineRoomFocus.focusLabel,
                      historicalMachineRoomFocus.routeKeys,
                    )
                  }
                >
                  回到协作现场
                </button>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className={styles.cardGridCompact}>
          <article className={styles.card}>
            <span>活跃执行位</span>
            <strong>{machineRoomVisibleWorkstations.length}</strong>
            <p>{`${activeSourceThreads.length} 条真实线程 + ${seatBackedMachineRoomWorkstations.length} 个 seat-backed NPC 工位`}</p>
          </article>
          <article className={styles.card}>
            <span>最近目标</span>
            <strong>{visibleOwner || "待分配"}</strong>
            <p>当前最该盯的责任链，优先等它出最小回执。</p>
          </article>
          <article className={styles.card} data-machine-room-attention-summary="attention">
            <span>待处理线程</span>
            <strong>{machineRoomAttentionThreads.length}</strong>
            <p>{machineRoomCriticalCount} 条紧急 / {machineRoomWarningCount} 条需处理</p>
          </article>
          <article className={styles.card} data-machine-room-attention-summary="recovery">
            <span>恢复入口</span>
            <strong>{machineRoomTokenGapCount}</strong>
            <p>{machineRoomWaitingFirstSignalCount} 条还在等首次回写</p>
          </article>
        </div>

        {workstationToken ? (() => {
          const workstationServerUrl = text(props.computerConnectServerUrl, "http://127.0.0.1:8010");
          const workstationCommand = buildWorkstationAdapterCommand(
            projectId,
            workstationTokenId,
            workstationToken,
            workstationServerUrl,
          );
          const workstationBashCommand = buildWorkstationAdapterBashCommand(
            projectId,
            workstationTokenId,
            workstationToken,
            workstationServerUrl,
          );
          return (
            <TokenResultCard
              title="工位接入令牌已签发"
              subtitle={workstationTokenId ? `工位 ${workstationTokenId}` : undefined}
              token={workstationToken}
              command={workstationCommand}
              linuxCommand={workstationBashCommand}
              testId="workstation-adapter"
            />
          );
        })() : null}

        {machineRoomAttentionThreads.length ? (
          <div className={styles.panelStack} data-machine-room-attention="true">
            <div className={styles.noticeCard}>
              <strong>优先处理线程</strong>
              <p>这几条线程已经不是“看起来有点老”，而是平台可以直接给出恢复建议和下一步动作的对象。先把它们处理干净，协作稳定性会立刻上一个台阶。</p>
            </div>
            <ul className={styles.list}>
              {machineRoomAttentionThreads.slice(0, 6).map((item) => {
                const threadId = item.threadId;
                const providerLabel = platformProviderLabelFromThread(item.thread);
                const tokenButtonLabel =
                  item.executionProfile?.tokenAvailable || item.recoveryProfile.suggestTokenRotation ? "轮换工位令牌" : "生成工位令牌";
                const recoveryChipClass =
                  item.recoveryProfile.severity === "critical"
                    ? styles.miniChipCritical
                    : item.recoveryProfile.severity === "warning"
                      ? styles.miniChipWarning
                      : styles.miniChipInfo;
                const suggestedRole = guessNpcResponsibility(item.thread);
                const canCalibrateCodex =
                  item.recoveryProfile.suggestSeatCalibration && item.providerId === "codex" && Boolean(item.boundSeatId);
                const canCalibrateClaude =
                  item.recoveryProfile.suggestSeatCalibration && item.providerId === "claude" && Boolean(item.boundSeatId);
                return (
                  <li key={`attention-${threadId}`} className={styles.featureCard} data-machine-thread-attention-card={threadId}>
                    <strong>{display(item.thread.name, threadId)}</strong>
                    <p>{item.recoveryProfile.summary}</p>
                    <div className={styles.chipRow}>
                      <span
                        className={`${styles.miniChip} ${styles.primaryStateChip} ${recoveryChipClass}`}
                        data-machine-thread-recovery-label={threadId}
                        title="一眼能看出这条线程当前的主要状态；其他细节折叠在下方"
                      >
                        {item.recoveryProfile.label}
                      </span>
                    </div>
                    <details className={styles.threadDetailsToggle}>
                      <summary>展开细节（provider / 绑定 / 最近活动）</summary>
                      <div className={styles.chipRow}>
                        <span className={styles.miniChip}>{providerLabel}</span>
                        <span className={styles.miniChip}>{item.boundSeat ? `已绑 ${text(item.boundSeat.name, "NPC")}` : "未绑定 NPC"}</span>
                        {item.activityProfile.activityFreshnessLabel ? (
                          <span className={styles.miniChip}>{item.activityProfile.activityFreshnessLabel}</span>
                        ) : null}
                        {item.activityProfile.latestCommandAt ? (
                          <span className={styles.miniChip}>{item.activityProfile.latestCommandTypeLabel} {formatStamp(item.activityProfile.latestCommandAt)}</span>
                        ) : null}
                        {item.activityProfile.latestAckAt ? (
                          <span className={styles.miniChip}>最近回执 {formatStamp(item.activityProfile.latestAckAt)}</span>
                        ) : null}
                        {item.activityProfile.latestFinalReplyAt ? (
                          <span className={styles.miniChip}>最近最终回复 {formatStamp(item.activityProfile.latestFinalReplyAt)}</span>
                        ) : null}
                      </div>
                    </details>
                    <p className={styles.microCopy} data-machine-thread-recovery-next={threadId}>
                      建议动作：{item.recoveryProfile.nextStep}
                    </p>
                    {renderMachineRoomRecoveryDispatchForm(item)}
                    <div className={styles.inlineActions}>
                      <form
                        action={issueCollaborationWorkstationAdapterToken.bind(null, projectId, threadId)}
                        data-machine-thread-recovery-token={threadId}
                      >
                        <input type="hidden" name="return_to" value={machineRoomReturnPath} />
                        <button type="submit" data-loading-label={`正在处理 ${display(item.thread.name, threadId)} 工位令牌`}>
                          {tokenButtonLabel}
                        </button>
                      </form>
                      {canCalibrateCodex ? (
                        <form action={校准Codex席位自治桥.bind(null, projectId, item.boundSeatId)} data-machine-thread-recovery-calibrate={threadId}>
                          <input type="hidden" name="return_to" value={machineRoomReturnPath} />
                          <button type="submit" className={styles.ghostButton} data-loading-label={`正在校准 ${display(item.thread.name, threadId)} Codex 自治桥`}>
                            校准 Codex 自治桥
                          </button>
                        </form>
                      ) : null}
                      {canCalibrateClaude ? (
                        <form action={校准Claude席位会话.bind(null, projectId, item.boundSeatId)} data-machine-thread-recovery-calibrate={threadId}>
                          <input type="hidden" name="return_to" value={machineRoomReturnPath} />
                          <button type="submit" className={styles.ghostButton} data-loading-label={`正在校准 ${display(item.thread.name, threadId)} Claude 会话`}>
                            校准 Claude 会话
                          </button>
                        </form>
                      ) : null}
                      {item.boundSeat ? (
                        <Link
                          href={buildProjectSurfacePath(projectEntryPath, {
                            panel: "team",
                            tab: "npc-create",
                            seat: item.boundSeatId,
                          })}
                          className={styles.inlineActionLink}
                        >
                          查看已绑定 NPC
                        </Link>
                      ) : (
                        <Link href={buildNpcCreateHref(item.thread, codexSeats.length + item.index)} className={styles.inlineActionLink}>
                          先创建 NPC
                        </Link>
                      )}
                      <span className={styles.miniChip}>{suggestedRole}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}

        <form action={sendRunnerCommand.bind(null, projectId)} className={styles.skillManagerForm}>
          <ClaudeCommandPalette />
          <strong>给 Runner 心跳正常的电脑发一条最小命令</strong>
          <p className={styles.microCopy}>
            目标电脑要先保持“自动化心跳 / 持续接单”窗口运行才能接到单。没有可选电脑时，这里不会把任务假装派出去；先到“电脑接入”复制持续接单命令，在目标电脑终端运行并等状态变成常驻接单。
            线程级 watcher（每条线程一个终端）见{" "}
            <a
              href="https://github.com/wenjunyong666/ai-/blob/main/docs/user-guides/THREAD_WATCHER_QUICKSTART_2026-05-07.md"
              target="_blank"
              rel="noopener noreferrer"
            >
              线程 watcher 上手
            </a>
            。
          </p>
          <input type="hidden" name="target_mode" value="computer_node_id" />
          <input type="hidden" name="return_to" value={gitPanelReturnPath} />
          <label className={styles.fieldLabel}>
            <span>目标电脑</span>
            <select name="computer_node_id" className={styles.select} defaultValue={text(onlineNodes[0]?.id, "")}>
              {onlineNodes.length ? (
                onlineNodes.map((node) => {
                  const nodeId = text(node.id, "");
                  return <option key={nodeId} value={nodeId}>{text(node.label ?? node.name, nodeId)}</option>;
                })
              ) : (
                <option value="">没有正在接单的电脑</option>
              )}
            </select>
          </label>
          <label className={styles.fieldLabel}>
            <span>命令标题</span>
            <input name="title" placeholder="例如：请回一条最小回执" defaultValue="最小协作检查" />
          </label>
          <label className={styles.fieldLabel}>
            <span>命令正文</span>
            <textarea name="body" placeholder="写给真实 runner 的一句话命令">请检查这台电脑上的最新线程状态，并回一条最小回执。</textarea>
          </label>
          {!onlineNodes.length ? (
            <p className={styles.microCopy} data-runner-command-disabled-reason="no-watch-ready-computer">
              已登记电脑不会自动接单；需要在目标电脑运行“持续心跳 / 接单”命令后，平台才会把任务送进那台电脑的收件箱。
            </p>
          ) : null}
          <button type="submit" disabled={!onlineNodes.length}>下发 Runner 命令</button>
        </form>

        <form action={createCollaborationWorkstation.bind(null, projectId)} className={styles.skillManagerForm}>
          <strong>手动登记一个真实线程</strong>
          <p className={styles.microCopy}>
            当 Codex、Claude、Qwen 等线程还不能自动扫描时，用户可以先登记来源线程；后续再一键创建 NPC 绑定它。
          </p>
          <div className={styles.skillManagerGrid}>
            <label className={styles.fieldLabel}>
              <span>线程 ID</span>
              <input name="id" placeholder="例如：codex-session-main 或 claude-session-xxx" required />
            </label>
            <label className={styles.fieldLabel}>
              <span>线程名称</span>
              <input name="name" placeholder="例如：Codex 资料员 / Claude 写作者" required />
            </label>
            <label className={styles.fieldLabel}>
              <span>所在电脑</span>
              <select name="computer_node_id" className={styles.select} defaultValue={text(onlineNodes[0]?.id, "")}>
                <option value="">暂不绑定电脑</option>
                {nodes.map((node) => {
                  const nodeId = text(node.id, "");
                  return <option key={`manual-thread-node-${nodeId}`} value={nodeId}>{text(node.label ?? node.name, nodeId)}</option>;
                })}
              </select>
            </label>
            <label className={styles.fieldLabel}>
              <span>AI 提供方</span>
              <select name="ai_provider_id" className={styles.select} defaultValue="codex">
                <option value="codex">Codex</option>
                <option value="claude">Claude</option>
                <option value="qwen">Qwen</option>
                <option value="glm">GLM</option>
                <option value="openclaw">OpenClaw</option>
              </select>
            </label>
            <label className={styles.fieldLabel}>
              <span>提供方显示名</span>
              <input name="ai_provider" placeholder="例如：Codex / Claude" defaultValue="Codex" />
            </label>
            <label className={styles.fieldLabel}>
              <span>模型</span>
              <input name="model" placeholder="例如：gpt-5.4 / claude / qwen-code" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>职责</span>
              <input name="responsibility" placeholder="例如：找资料 / 写文章 / 做验收" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>备注</span>
              <input name="notes" placeholder="例如：这条线程由用户在 Codex/Claude 软件里手动打开" />
            </label>
          </div>
          <input type="hidden" name="return_to" value={machineRoomReturnPath} />
          <input type="hidden" name="status" value="active" />
          <input type="hidden" name="metadata" value='{"source_kind":"manual_user_entry","source":"project_workbench"}' />
          <button type="submit">登记线程</button>
        </form>

        <details className={styles.formSection} open data-machine-execution-config="true">
          <summary className={styles.formSectionSummary}>
            <div className={styles.formSectionText}>
              <strong>平台执行配置</strong>
              <small>先给 AI 提供方配置默认模板，再按具体工位做覆盖。workstation adapter 现在会直接从平台读取这些值，不再要求用户在命令里手填 provider。</small>
            </div>
            <span className={styles.formSectionState}>{machineRoomProviderCards.length} 个提供方 / {machineRoomExecutionWorkstations.length} 个工位</span>
          </summary>
          <div className={styles.formSectionBody}>
            <div className={styles.cardGridCompact}>
              <article className={styles.card}>
                <span>默认模板</span>
                <strong>{machineRoomProviderCards.filter((item) => item.executorCommand || item.executorCwd || item.executorTimeoutSeconds !== null).length}</strong>
                <p>按 Claude / Codex / Qwen 这类提供方统一定义执行命令、仓库目录和超时。</p>
              </article>
              <article className={styles.card}>
                <span>工位覆盖</span>
                <strong>{machineRoomExecutionWorkstations.filter((item) => item.hasWorkstationOverride).length}</strong>
                <p>只给需要差异化的线程填覆盖值，其他线程继续继承默认模板和电脑目录。</p>
              </article>
            </div>

            <details className={styles.formSection} open>
              <summary className={styles.formSectionSummary}>
                <div className={styles.formSectionText}>
                  <strong>AI 提供方默认模板</strong>
                  <small>定义这个提供方的统一执行命令、默认仓库目录和超时。</small>
                </div>
                <span className={styles.formSectionState}>{machineRoomProviderCards.length} 个</span>
              </summary>
              <div className={styles.formSectionBody}>
                <ul className={styles.list}>
                  {machineRoomProviderCards.length ? (
                    machineRoomProviderCards.map((provider) => (
                      <li key={`provider-template-${text(provider.id, "")}`} className={styles.featureCard}>
                        <strong>{text(provider.label, text(provider.id, "未命名提供方"))}</strong>
                        <p>{text(provider.kind, "thread")} / 默认模型 {text(provider.model, "未配置")} / 当前覆盖 {provider.linkedThreadCount} 条线程</p>
                        <div className={styles.chipRow}>
                          <span className={styles.miniChip}>ID {text(provider.id, "-")}</span>
                          <span className={styles.miniChip}>{provider.executorCommand ? "已配默认命令" : "未配默认命令"}</span>
                          <span className={styles.miniChip}>{provider.executorCwd ? `目录 ${provider.executorCwd}` : "目录跟随工位/电脑"}</span>
                          <span className={styles.miniChip}>超时 {formatExecutionTimeout(provider.executorTimeoutSeconds)}</span>
                        </div>
                        <form
                          action={updateCollaborationProviderExecution.bind(null, projectId, text(provider.id, ""))}
                          className={styles.skillManagerForm}
                          data-provider-execution-form={text(provider.id, "")}
                        >
                          <input type="hidden" name="return_to" value={machineRoomReturnPath} />
                          <input type="hidden" name="provider_id" value={text(provider.id, "")} />
                          <input type="hidden" name="provider_label" value={text(provider.label, text(provider.id, ""))} />
                          <div className={styles.skillManagerGrid}>
                            <label className={styles.fieldLabel}>
                              <span>默认模型</span>
                              <input name="model" defaultValue={text(provider.model, "")} placeholder="例如：claude-opus-4.1 / gpt-5.4 / qwen-code" />
                            </label>
                            <label className={styles.fieldLabel}>
                              <span>默认仓库目录</span>
                              <input name="executor_cwd" defaultValue={text(provider.executorCwd, "")} placeholder="例如：D:/ai-collab/runtime" />
                            </label>
                            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                              <span>默认执行命令</span>
                              <textarea
                                name="executor_command"
                                defaultValue={text(provider.executorCommand, "")}
                                placeholder="例如：python scripts/platform-provider-executor.py @PROMPT_FILE@ --provider claude --message-id @MESSAGE_ID@ --cwd D:/ai-collab/runtime"
                              />
                            </label>
                            <label className={styles.fieldLabel}>
                              <span>默认超时（秒）</span>
                              <input name="executor_timeout_seconds" type="number" min="1" step="1" defaultValue={provider.executorTimeoutSeconds ?? ""} placeholder="例如：1800" />
                            </label>
                          </div>
                          <div className={styles.inlineActions}>
                            <button type="submit" data-loading-label={`正在保存 ${text(provider.label, text(provider.id, "提供方"))} 模板`}>保存提供方模板</button>
                          </div>
                        </form>
                        <form action={updateCollaborationProviderExecution.bind(null, projectId, text(provider.id, ""))} className={styles.inlineDangerForm}>
                          <input type="hidden" name="return_to" value={machineRoomReturnPath} />
                          <input type="hidden" name="provider_id" value={text(provider.id, "")} />
                          <input type="hidden" name="provider_label" value={text(provider.label, text(provider.id, ""))} />
                          <input type="hidden" name="model" value={text(provider.model, "")} />
                          <input type="hidden" name="clear_executor_template" value="true" />
                          <button type="submit" className={styles.ghostButton} data-loading-label={`正在清空 ${text(provider.label, text(provider.id, "提供方"))} 模板`}>
                            清空默认模板
                          </button>
                        </form>
                      </li>
                    ))
                  ) : (
                    <li className={styles.featureCard}>
                      <strong>还没有提供方模板</strong>
                      <p>先登记真实线程或创建 AI 提供方，平台再按提供方统一管理执行模板。</p>
                    </li>
                  )}
                </ul>
              </div>
            </details>

            <details className={styles.formSection} open>
              <summary className={styles.formSectionSummary}>
                <div className={styles.formSectionText}>
                  <strong>线程工位覆盖</strong>
                  <small>只在某个线程需要不同仓库目录、命令或超时时，才填这里。</small>
                </div>
                <span className={styles.formSectionState}>{machineRoomExecutionWorkstations.length} 个</span>
              </summary>
              <div className={styles.formSectionBody}>
                <ul className={styles.list}>
                  {machineRoomExecutionWorkstations.length ? (
                    machineRoomExecutionWorkstations.map((item) => {
                      const threadId = text(item.thread.id ?? item.thread.workstation_id, "");
                      return (
                        <li key={`workstation-execution-${threadId}`} className={styles.featureCard}>
                          <strong>{display(item.thread.name, threadId || "未命名工位")}</strong>
                          <p>{item.providerLabel} / {item.nodeLabel} / 当前模型 {text(item.thread.model ?? item.provider?.model, "未配置")}</p>
                          <div className={styles.chipRow}>
                            <span className={styles.miniChip}>{item.hasWorkstationOverride ? "已有工位覆盖" : "继承默认模板"}</span>
                            <span className={styles.miniChip}>命令来源 {executionSourceLabel(item.executorCommandSource)}</span>
                            <span className={styles.miniChip}>目录来源 {executionSourceLabel(item.executorCwdSource)}</span>
                            <span className={styles.miniChip}>超时来源 {executionSourceLabel(item.executorTimeoutSource)}</span>
                          </div>
                          <p className={styles.microCopy}>
                            当前生效：{item.executorCommand ? "已配置执行命令" : "未配置执行命令"} / cwd {item.executorCwd ?? "跟随电脑目录"} / timeout {formatExecutionTimeout(item.executorTimeoutSeconds)}
                          </p>
                          <form
                            action={updateCollaborationWorkstationExecution.bind(null, projectId, threadId)}
                            className={styles.skillManagerForm}
                            data-workstation-execution-form={threadId}
                          >
                            <input type="hidden" name="return_to" value={machineRoomReturnPath} />
                            <div className={styles.skillManagerGrid}>
                              <label className={styles.fieldLabel}>
                                <span>工位模型</span>
                                <input name="model" defaultValue={text(item.thread.model ?? item.provider?.model, "")} placeholder="留空就继续用当前模型" />
                              </label>
                              <label className={styles.fieldLabel}>
                                <span>工位仓库目录</span>
                                <input name="executor_cwd" defaultValue={text(item.executorCwdSource?.startsWith("workstation.") ? item.executorCwd : "", "")} placeholder="留空就继承提供方或电脑目录" />
                              </label>
                              <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                                <span>工位执行命令</span>
                                <textarea
                                  name="executor_command"
                                  defaultValue={text(item.executorCommandSource?.startsWith("workstation.") ? item.executorCommand : "", "")}
                                  placeholder="只给这个线程单独覆盖时再填写"
                                />
                              </label>
                              <label className={styles.fieldLabel}>
                                <span>工位超时（秒）</span>
                                <input
                                  name="executor_timeout_seconds"
                                  type="number"
                                  min="1"
                                  step="1"
                                  defaultValue={item.executorTimeoutSource?.startsWith("workstation.") ? item.executorTimeoutSeconds ?? "" : ""}
                                  placeholder="留空就继承提供方"
                                />
                              </label>
                            </div>
                            <div className={styles.inlineActions}>
                              <button type="submit" data-loading-label={`正在保存 ${display(item.thread.name, threadId || "工位")} 配置`}>保存工位覆盖</button>
                            </div>
                          </form>
                          <form action={updateCollaborationWorkstationExecution.bind(null, projectId, threadId)} className={styles.inlineDangerForm}>
                            <input type="hidden" name="return_to" value={machineRoomReturnPath} />
                            <input type="hidden" name="model" value={text(item.thread.model ?? item.provider?.model, "")} />
                            <input type="hidden" name="clear_executor_override" value="true" />
                            <button type="submit" className={styles.ghostButton} data-loading-label={`正在清空 ${display(item.thread.name, threadId || "工位")} 覆盖`}>
                              清空工位覆盖
                            </button>
                          </form>
                        </li>
                      );
                    })
                  ) : (
                    <li className={styles.featureCard}>
                      <strong>还没有可配置工位</strong>
                      <p>先扫描或登记真实线程，这里才会出现可覆盖的工位。</p>
                    </li>
                  )}
                </ul>
              </div>
            </details>
          </div>
        </details>

        <ul className={styles.list}>
          {activeSourceThreads.length ? (
            machineRoomThreadModels.map((item) => {
              const thread = item.thread;
              const index = item.index;
              const threadId = item.threadId;
              const boundSeat = item.boundSeat;
              const suggestedName = guessNpcName(thread, codexSeats.length + index);
              const suggestedRole = guessNpcResponsibility(thread);
              const providerId = item.providerId;
              const providerLabel = platformProviderLabelFromThread(thread);
              const threadBootstrapIssue = threadBootstrapBlocker(thread);
              const threadBootstrapHint = threadBootstrapReminder(thread);
              const canQuickCreate = !threadBootstrapIssue;
              const executionProfile = item.executionProfile;
              const activityProfile = item.activityProfile;
              const issuedAdapterToken = workstationTokenId === threadId ? workstationToken : "";
              const adapterCommand = buildWorkstationAdapterCommand(
                projectId,
                threadId,
                issuedAdapterToken || undefined,
                text(props.computerConnectServerUrl, "http://127.0.0.1:8010"),
              );
              const adapterBashCommand = buildWorkstationAdapterBashCommand(
                projectId,
                threadId,
                issuedAdapterToken || undefined,
                text(props.computerConnectServerUrl, "http://127.0.0.1:8010"),
              );
              const executorHint = providerExecutorHint(providerId);
              const suggestedThreadSkills = recommendRoleSkillIds({
                roleText: suggestedRole,
                threadText: text(thread.name ?? thread.label ?? threadId, ""),
                skillLibrary,
              });
              const boundSeatId = item.boundSeatId;
              const recoveryChipClass =
                item.recoveryProfile.severity === "critical"
                  ? styles.miniChipCritical
                  : item.recoveryProfile.severity === "warning"
                    ? styles.miniChipWarning
                    : item.recoveryProfile.severity === "info"
                      ? styles.miniChipInfo
                      : "";
              return (
                <li key={threadId} className={styles.featureCard} data-machine-thread-card={threadId}>
                  <strong>{display(thread.name, threadId)}</strong>
                  <p>{`${item.isSeatBackedWorkstation ? "执行位" : "线程"} ID：${threadId}`}</p>
                  <p className={styles.microCopy}>
                    提供方：{providerLabel}
                    {` / ${item.isSeatBackedWorkstation ? "执行位类型：NPC 工位" : "执行位类型：真实线程"}`}
                    {` / 电脑：${display(thread.computer_node ?? thread.computer_node_id, "未记录")}`}
                    {` / 模型：${text(thread.model ?? thread.metadata?.model, "未记录")}`}
                  </p>
                  <div className={styles.chipRow}>
                    <span className={styles.miniChip}>{item.isSeatBackedWorkstation ? "seat-backed 工位" : "真实线程"}</span>
                    <span className={styles.miniChip}>{boundSeat ? `已绑定 ${text(boundSeat.name, "NPC")}` : "未绑定 NPC"}</span>
                    <span className={styles.miniChip}>{suggestedName}</span>
                    <span className={styles.miniChip}>{suggestedRole}</span>
                    <span className={styles.miniChip}>固定 Skill 自动附带</span>
                    <span className={styles.miniChip}>
                      {canQuickCreate
                        ? supportsLocalCodexAutonomyBridge(providerId)
                          ? "创建后自动接通自治桥"
                          : `创建后按 ${providerLabel} 协议协作`
                        : providerId === "claude"
                          ? "先切目录再绑定"
                          : `${providerLabel} 识别已通`}
                    </span>
                    {suggestedThreadSkills.slice(0, 2).map((skillId) => (
                      <span key={`${threadId}-machine-${skillId}`} className={styles.miniChip}>
                        推荐 {text(skillById.get(skillId.toLowerCase())?.label, skillId)}
                      </span>
                    ))}
                    {executionProfile ? (
                      <span className={styles.miniChip}>
                        {executionProfile.hasWorkstationOverride ? "工位覆盖已生效" : executionProfile.hasProviderTemplate ? "提供方模板已生效" : "还没配置执行模板"}
                      </span>
                    ) : null}
                    {activityProfile.activityHealthLabel ? (
                      <span className={styles.miniChip}>{activityProfile.activityHealthLabel}</span>
                    ) : null}
                    <span className={`${styles.miniChip} ${recoveryChipClass}`}>{item.recoveryProfile.label}</span>
                    {activityProfile.activityFreshnessLabel ? (
                      <span
                        className={styles.miniChip}
                        data-machine-thread-freshness={threadId}
                        data-stale={activityProfile.activityFreshnessStale ? "true" : "false"}
                      >
                        {activityProfile.activityFreshnessLabel}
                      </span>
                    ) : null}
                    <span className={styles.miniChip}>
                      {executionProfile?.tokenAvailable ? "工位令牌已签发" : "未签发工位令牌"}
                    </span>
                    {executionProfile?.lastUsedAt ? (
                      <span className={styles.miniChip}>最近使用 {formatStamp(executionProfile.lastUsedAt)}</span>
                    ) : null}
                    {activityProfile.latestAckAt ? (
                      <span className={styles.miniChip} data-machine-thread-last-ack={threadId}>最近回执 {formatStamp(activityProfile.latestAckAt)}</span>
                    ) : null}
                    {activityProfile.latestFinalReplyAt ? (
                      <span className={styles.miniChip} data-machine-thread-last-result={threadId}>最近最终回复 {formatStamp(activityProfile.latestFinalReplyAt)}</span>
                    ) : null}
                    {activityProfile.latestCommandAt ? (
                      <span className={styles.miniChip} data-machine-thread-last-command={threadId}>
                        {activityProfile.latestCommandTypeLabel} {formatStamp(activityProfile.latestCommandAt)}
                      </span>
                    ) : null}
                  </div>
                  <p className={styles.microCopy}>恢复建议：{item.recoveryProfile.nextStep}</p>
                  {item.recoveryProfile.needsAttention ? (
                    <details className={styles.adapterCommandCard}>
                      <summary>直接补一轮最小检查</summary>
                      {renderMachineRoomRecoveryDispatchForm(
                        item,
                        "线程最小检查",
                        "如果你已经在完整线程卡里确认了上下文，就可以直接从这里预演并补发一条标准最小检查。",
                      )}
                    </details>
                  ) : null}
                  {threadBootstrapHint ? <p className={styles.microCopy}>{threadBootstrapHint}</p> : null}
                  <details className={styles.adapterCommandCard} open={index === 0}>
                    <summary>本机/其他电脑接入命令</summary>
                    <p className={styles.microCopy}>
                      在对应电脑上运行。若这条线程需要直接改代码，再进入那台电脑自己的 Git 仓库目录；平台只要求 projectId、workstationId 和统一消息格式一致。
                    </p>
                    {issuedAdapterToken ? (
                      <div className={styles.successBanner} data-workstation-token-banner={threadId}>
                        这是一条刚签发的一次性工位令牌，只会在当前页面直接展示一次。复制后就去接入，不要长期贴在共享文档里。
                      </div>
                    ) : null}
                    <pre className={styles.commandBlock} data-adapter-command={threadId}><code>{adapterCommand}</code></pre>
                    <p className={styles.microCopy}>
                      Linux / macOS 电脑使用下面这条 bash 命令接入平台工位消息通道。
                    </p>
                    <pre className={styles.commandBlock} data-adapter-linux-command={threadId}><code>{adapterBashCommand}</code></pre>
                      <p className={styles.microCopy}>
                        这条命令会先下载最新版 adapter，再读取平台里的 provider 模板和工位覆盖；如果只是临时单机调试，再追加：<code>{executorHint}</code>
                      </p>
                    {executionProfile ? (
                      <>
                        <p className={styles.microCopy}>
                          当前平台配置：{executionProfile.executorCommand ? "已配置执行命令" : "未配置执行命令"} / cwd {executionProfile.executorCwd ?? "跟随电脑 git_root/workspace_root"} / timeout {formatExecutionTimeout(executionProfile.executorTimeoutSeconds)}
                        </p>
                        <p className={styles.microCopy}>
                          令牌状态：{executionProfile.tokenAvailable ? "已签发" : "未签发"}
                          {executionProfile.issuedAt ? ` / 签发 ${formatStamp(executionProfile.issuedAt)}` : ""}
                          {executionProfile.lastUsedAt ? ` / 最近使用 ${formatStamp(executionProfile.lastUsedAt)}` : ""}
                        </p>
                        {activityProfile.latestSignalAt ? (
                          <p className={styles.microCopy}>
                            最近协作信号：{formatStamp(activityProfile.latestSignalAt)} / {activityProfile.activityFreshnessLabel}
                          </p>
                        ) : (
                          <p className={styles.microCopy}>最近协作信号：还没见到协作回写</p>
                        )}
                        {activityProfile.latestAckAt ? (
                          <p className={styles.microCopy}>
                            最近回执：{activityProfile.latestAckLabel || "最小回执"} / {formatStamp(activityProfile.latestAckAt)}
                            {activityProfile.latestAckBody ? ` / ${activityProfile.latestAckBody}` : ""}
                          </p>
                        ) : null}
                        {activityProfile.latestFinalReplyAt ? (
                          <p className={styles.microCopy}>
                            最近最终回复：{activityProfile.latestFinalReplyLabel || "最终回复"} / {formatStamp(activityProfile.latestFinalReplyAt)}
                            {activityProfile.latestFinalReplyBody ? ` / ${activityProfile.latestFinalReplyBody}` : ""}
                          </p>
                        ) : null}
                        {activityProfile.latestCommandAt ? (
                          <p className={styles.microCopy}>
                            {activityProfile.latestCommandTypeLabel}：{activityProfile.latestCommandLabel || activityProfile.latestCommandTypeLabel} / {formatStamp(activityProfile.latestCommandAt)}
                            {activityProfile.latestCommandBody ? ` / ${activityProfile.latestCommandBody}` : ""}
                          </p>
                        ) : null}
                      </>
                    ) : null}
                    <p className={styles.microCopy}>
                      如果该工位配置了接入令牌，再追加 <code>--token 工位令牌</code>；Claude 在其他目录也能操作项目文件，但推荐优先在上面的平台执行配置里写好默认仓库目录。
                    </p>
                    <div className={styles.inlineActions}>
                      <form
                        action={issueCollaborationWorkstationAdapterToken.bind(null, projectId, threadId)}
                        data-workstation-token-issue-form={threadId}
                      >
                        <input type="hidden" name="return_to" value={machineRoomReturnPath} />
                        <button type="submit" data-loading-label={`正在生成 ${display(thread.name, threadId)} 工位令牌`}>
                          {executionProfile?.tokenAvailable ? "轮换工位令牌" : "生成工位令牌"}
                        </button>
                      </form>
                      <form
                        action={revokeCollaborationWorkstationAdapterToken.bind(null, projectId, threadId)}
                        data-workstation-token-revoke-form={threadId}
                      >
                        <input type="hidden" name="return_to" value={machineRoomReturnPath} />
                        <button
                          type="submit"
                          className={styles.ghostButton}
                          disabled={!executionProfile?.tokenAvailable}
                          data-loading-label={`正在吊销 ${display(thread.name, threadId)} 工位令牌`}
                        >
                          吊销工位令牌
                        </button>
                      </form>
                    </div>
                  </details>
                  <div className={styles.inlineActions}>
                    {boundSeat ? (
                      <Link
                        href={buildProjectSurfacePath(projectEntryPath, {
                          panel: "team",
                          tab: "npc-create",
                          seat: boundSeatId,
                        })}
                        className={styles.inlineActionLink}
                      >
                        查看已绑定 NPC
                      </Link>
                    ) : (
                      canQuickCreate ? (
                        <>
                          <form action={createNpcWorkstationSeat.bind(null, projectId)}>
                            <input type="hidden" name="return_to" value={npcCreateReturnPath} />
                            <input type="hidden" name="name" value={suggestedName} />
                            <input type="hidden" name="responsibility" value={suggestedRole} />
                            <input type="hidden" name="computer_node_id" value={text(thread.computer_node_id ?? thread.computer_node, "")} />
                          <input type="hidden" name="source_workstation_id" value={threadId} />
                            <input type="hidden" name="ai_provider_id" value={providerId} />
                            <input type="hidden" name="ai_provider" value={providerLabel} />
                            <input type="hidden" name="model" value={text(thread.model ?? thread.metadata?.model, "")} />
                            <input type="hidden" name="source_thread_catalog" value={sourceThreadCatalogJson} />
                            <input type="hidden" name="avatar_key" value="jack-standing" />
                            {suggestedThreadSkills.map((skillId) => (
                              <input key={`machine-skill-${threadId}-${skillId}`} type="hidden" name="skill_loadout" value={skillId} />
                            ))}
                            <button type="submit">{supportsLocalCodexAutonomyBridge(providerId) ? "创建 NPC 并启动自治" : `创建 ${providerLabel} NPC`}</button>
                          </form>
                          <Link href={buildNpcCreateHref(thread, codexSeats.length + index)} className={styles.inlineActionLink}>
                            进入自定义创建
                          </Link>
                        </>
                      ) : (
                        <p className={styles.microCopy}>
                          {threadBootstrapIssue}
                        </p>
                      )
                    )}
                  </div>
                </li>
              );
            })
          ) : (
            <li>
              <strong>还没有活跃线程</strong>
              <p>先扫描目标电脑上的真实线程；后续派工还需要对应 Runner 保持常驻接单。</p>
            </li>
          )}
        </ul>
      </div>
    );
  }

  function renderGitPanel() {
    const normalizeGitReason = (value: unknown) => {
      const raw = text(value, "");
      const normalized = raw.toLowerCase();
      if (!normalized) return "暂无额外说明";
      if (normalized.includes("no task branches yet")) return "当前还没有分支任务";
      if (normalized.includes("no merge-ready branches yet")) return "当前还没有可同步的合并就绪分支";
      if (normalized.includes("no task branches available for rollback context")) return "当前还没有可用于回退判断的分支上下文";
      if (normalized.includes("repository not bound")) return "还没有绑定 Git 仓库";
      if (normalized.includes("local repository is not bound")) return "当前还没有绑定本地仓库镜像";
      if (normalized.includes("blocked branch")) return "还有阻塞分支未处理";
      if (normalized.includes("high-risk approval")) return "还有高风险审批未完成";
      return raw;
    };

    const gitStatusLabel = (value: unknown) => {
      switch (text(value, "").toLowerCase()) {
        case "ready":
          return "可执行";
        case "attention":
          return "需要先处理阻塞";
        case "blocked":
          return "当前阻塞";
        case "syncable":
          return "已绑定仓库";
        case "waiting-for-bind":
          return "待绑定仓库";
        default:
          return display(value, "待确认");
      }
    };

    const rollbackBlockers = asArray(rollbackExecutionAction?.blockers).map((item) => normalizeGitReason(item));
    const syncBlockers = asArray(syncExecutionAction?.blockers).map((item) => normalizeGitReason(item));
    const gitRepositoryBound =
      Boolean(text(gitExecutionRepository.github_url, "")) || Boolean(text(gitExecutionRepository.local_git_url, ""));
    const rollbackReadyCount = asNumber(gitExecutionSummary.merge_ready_count) ?? 0;
    const rollbackBranchCount = asNumber(gitExecutionSummary.branch_count) ?? 0;
    const rollbackBlockedCount = asNumber(gitExecutionSummary.blocked_count) ?? 0;
    const rollbackRecentCount = asNumber(rollbackExecutionAction?.recent_activity_count) ?? 0;
    const rollbackDisabled = !gitRepositoryBound || !gitRollbackTargetRef.trim();
    const syncRecentCount = asNumber(syncExecutionAction?.recent_activity_count) ?? 0;
    const gitSyncPreview =
      props.gitSyncPreview && typeof props.gitSyncPreview === "object" ? (props.gitSyncPreview as AnyRecord) : null;
    const gitRollbackPreview =
      props.gitRollbackPreview && typeof props.gitRollbackPreview === "object"
        ? (props.gitRollbackPreview as AnyRecord)
        : null;
    const syncProviderTarget =
      gitSyncProviderOptions.find((item) => item.id === gitSyncProvider)?.target ??
      (text(gitSyncProvider === "local" ? gitExecutionRepository.local_git_url : gitExecutionRepository.github_url, "") ||
        null);
    const syncPreviewProvider = text(gitSyncPreview?.provider, "");
    const syncPreviewBlockers = asArray(gitSyncPreview?.blockers).map((item) => normalizeGitReason(item));
    const syncPreviewWarnings = asArray(gitSyncPreview?.warnings).map((item) => normalizeGitReason(item));
    const syncPreviewNotes = asArray(gitSyncPreview?.preview_notes).map((item) => display(item, ""));
    const syncPreviewReady = Boolean(gitSyncPreview?.ready);
    const syncPreviewStatus = gitStatusLabel(text(gitSyncPreview?.status, "attention"));
    const syncPreviewStale = Boolean(syncPreviewProvider) && syncPreviewProvider !== gitSyncProvider;
    const rollbackPreviewTarget = text(gitRollbackPreview?.target_ref, "");
    const rollbackPreviewBlockers = asArray(gitRollbackPreview?.blockers).map((item) => normalizeGitReason(item));
    const rollbackPreviewWarnings = asArray(gitRollbackPreview?.warnings).map((item) => normalizeGitReason(item));
    const rollbackPreviewNotes = asArray(gitRollbackPreview?.preview_notes).map((item) => display(item, ""));
    const rollbackPreviewReady = Boolean(gitRollbackPreview?.ready);
    const rollbackPreviewStatus = gitStatusLabel(text(gitRollbackPreview?.status, "attention"));
    const rollbackPreviewStale =
      Boolean(rollbackPreviewTarget) && rollbackPreviewTarget !== gitRollbackTargetRef.trim();
    const syncPreviewDisabled = !gitRepositoryBound || !syncProviderTarget;
    const syncRequestDisabled =
      syncPreviewDisabled || !Boolean(syncPreviewProvider) || syncPreviewStale || !syncPreviewReady;
    const rollbackRequestDisabled =
      rollbackDisabled || !Boolean(rollbackPreviewTarget) || rollbackPreviewStale || !rollbackPreviewReady;
    const boundGithubUrl = text(
      gitExecutionRepository.github_url ?? props.project?.github_url ?? props.project?.githubUrl,
      "",
    );
    const boundLocalGitUrl = text(
      gitExecutionRepository.local_git_url ?? props.project?.local_git_url ?? props.project?.localGitUrl,
      "",
    );
    const boundDefaultBranch = text(props.project?.defaultBranch ?? props.project?.default_branch, "main");
    const boundDevelopBranch = text(props.project?.developBranch ?? props.project?.develop_branch, "develop");
    const githubAccountBinding =
      collaborationConfig.github_account_binding && typeof collaborationConfig.github_account_binding === "object"
        ? (collaborationConfig.github_account_binding as AnyRecord)
        : {};
    const githubAccountLogin = text(githubAccountBinding.account_login ?? githubAccountBinding.login, "");
    const githubAccountType = ["user", "org", "bot"].includes(text(githubAccountBinding.account_type, "user"))
      ? text(githubAccountBinding.account_type, "user")
      : "user";
    const githubAccountBound = Boolean(githubAccountLogin);
    const githubProfileUrl = text(
      githubAccountBinding.profile_url,
      githubAccountLogin ? `https://github.com/${githubAccountLogin}` : "",
    );
    const githubCredentialSource = [
      "github_app",
      "oauth",
      "runner_env",
      "ssh_agent",
      "manual_review",
    ].includes(text(githubAccountBinding.credential_source, "runner_env"))
      ? text(githubAccountBinding.credential_source, "runner_env")
      : "runner_env";
    const githubCredentialSourceLabel =
      {
        github_app: "GitHub App",
        oauth: "OAuth 授权",
        runner_env: "Runner 环境变量",
        ssh_agent: "SSH Agent",
        manual_review: "人工审批后手动执行",
      }[githubCredentialSource] ?? "Runner 环境变量";
    const githubCredentialRef = text(githubAccountBinding.credential_ref, "");
    const githubCloneProtocol = ["https", "ssh"].includes(text(githubAccountBinding.default_clone_protocol, "https"))
      ? text(githubAccountBinding.default_clone_protocol, "https")
      : "https";
    const githubPermissionScopes = asArray(githubAccountBinding.permission_scopes)
      .map((item) => text(item, ""))
      .filter(Boolean);

    return (
      <div className={styles.panelStack}>
        <div className={styles.noticeCard}>
          <strong>Git 合作</strong>
          <p>
            这里给用户看的是“能不能回退、应该回退到哪、谁刚登记过回退”，不是原始 Git 日志。现在这条链分成两步：先做安全预演，再决定要不要正式登记回退请求。
          </p>
        </div>

        <form action={runPlatformAutonomySweep.bind(null, projectId)}>
          <input type="hidden" name="return_to" value={gitPanelReturnPath} />
          <button type="submit" data-loading-label="正在推进 Git 协作面板">自治推进一轮</button>
        </form>

        <div className={styles.cardGridCompact}>
          <article className={styles.card}>
            <span>分支上下文</span>
            <strong>{rollbackBranchCount} 个</strong>
            <p>{rollbackReadyCount} 个可合并 / {rollbackBlockedCount} 个阻塞</p>
          </article>
          <article className={styles.card}>
            <span>同步状态</span>
            <strong>{gitStatusLabel(syncExecutionAction?.status ?? gitExecutionSummary.sync_status)}</strong>
            <p>{syncBlockers[0] ? shortText(syncBlockers[0], syncBlockers[0], 48) : "当前没有额外阻塞说明"}</p>
          </article>
          <article className={styles.card}>
            <span>回退状态</span>
            <strong>{gitStatusLabel(rollbackExecutionAction?.status ?? gitExecutionSummary.rollback_status)}</strong>
            <p>{rollbackBlockers[0] ? shortText(rollbackBlockers[0], rollbackBlockers[0], 48) : "可以直接登记项目级回退请求"}</p>
          </article>
          <article className={styles.card}>
            <span>最近同步登记</span>
            <strong>{syncRecentCount} 次</strong>
            <p>{formatStamp(syncExecutionAction?.latest_activity_at ?? gitExecutionSummary.last_sync_at)}</p>
          </article>
          <article className={styles.card}>
            <span>最近回退登记</span>
            <strong>{rollbackRecentCount} 次</strong>
            <p>{formatStamp(rollbackExecutionAction?.latest_activity_at ?? gitExecutionSummary.last_rollback_at)}</p>
          </article>
        </div>

        <div className={styles.featureCard} data-github-account-binding-card="1">
          <div className={styles.listHead}>
            <strong>GitHub 项目连接</strong>
            <span className={styles.stateBadge}>
              {gitRepositoryBound ? "仓库已绑定" : "仓库待绑定"} / {githubAccountBound ? "账号已绑定" : "账号待绑定"}
            </span>
          </div>
          <p>
            仓库地址解决“代码在哪”，账号绑定解决“谁有权限”。平台只保存账号、凭据来源和权限说明，不保存明文 token，真实密钥放在 Runner 环境变量、SSH Agent、GitHub App 或 OAuth 授权里。
          </p>
          <div className={styles.cardGridCompact}>
            <article className={styles.card}>
              <span>GitHub 仓库</span>
              <strong>{boundGithubUrl ? "已填写" : "待填写"}</strong>
              <p>{boundGithubUrl || "先绑定 GitHub 仓库地址，其他电脑才能统一从 GitHub 接力。"}</p>
            </article>
            <article className={styles.card}>
              <span>GitHub 身份</span>
              <strong>{githubAccountLogin || "待绑定"}</strong>
              <p>{githubProfileUrl || "可以是个人账号、组织账号或机器人账号。"}</p>
            </article>
            <article className={styles.card}>
              <span>凭据来源</span>
              <strong>{githubCredentialSourceLabel}</strong>
              <p>{githubCredentialRef || "例如 GITHUB_TOKEN、runner-local:GITHUB_TOKEN 或 ssh-agent。"}</p>
            </article>
            <article className={styles.card}>
              <span>默认 clone</span>
              <strong>{githubCloneProtocol.toUpperCase()}</strong>
              <p>{githubPermissionScopes.length ? `权限：${githubPermissionScopes.join(" / ")}` : "建议最小权限：repo read/write，危险操作走人工审批。"}</p>
            </article>
          </div>

          <form action={updateProjectGitSettings.bind(null, projectId)} className={styles.drawerForm}>
            <input type="hidden" name="return_to" value={gitPanelReturnPath} />
            <div className={styles.drawerFormGrid}>
              <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                <span>GitHub 仓库地址</span>
                <input
                  name="github_url"
                  data-github-repository-url="1"
                  defaultValue={boundGithubUrl}
                  placeholder="https://github.com/owner/repo.git"
                />
              </label>
              <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                <span>本地仓库镜像路径</span>
                <input
                  name="local_git_url"
                  defaultValue={boundLocalGitUrl}
                  placeholder="可选，例如 D:/projects/my-repo。其他电脑由各自 Runner 自己决定本地路径。"
                />
              </label>
              <label className={styles.fieldLabel}>
                <span>默认分支</span>
                <input name="default_branch" defaultValue={boundDefaultBranch} placeholder="main" />
              </label>
              <label className={styles.fieldLabel}>
                <span>开发分支</span>
                <input name="develop_branch" defaultValue={boundDevelopBranch} placeholder="develop" />
              </label>
            </div>
            <div className={styles.inlineActions}>
              <button type="submit" data-github-repository-bind-submit="1" data-loading-label="正在保存 Git 仓库配置">
                保存仓库配置
              </button>
            </div>
            <p className={styles.microCopy}>
              多电脑协作优先走 GitHub：每台电脑只需要知道远端仓库，自己的本地路径由本机 Runner/AI 自己确定，避免跨电脑路径互串。
            </p>
          </form>

          <form action={bindProjectGithubAccount.bind(null, projectId)} className={styles.drawerForm}>
            <input type="hidden" name="return_to" value={gitPanelReturnPath} />
            <div className={styles.drawerFormGrid}>
              <label className={styles.fieldLabel}>
                <span>账号 / 组织名</span>
                <input
                  name="account_login"
                  data-github-account-login="1"
                  defaultValue={githubAccountLogin}
                  placeholder="例如 wenjunyong666 或 your-org"
                  required
                />
              </label>
              <label className={styles.fieldLabel}>
                <span>账号类型</span>
                <select name="account_type" className={styles.select} defaultValue={githubAccountType}>
                  <option value="user">个人账号</option>
                  <option value="org">组织账号</option>
                  <option value="bot">机器人账号</option>
                </select>
              </label>
              <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                <span>GitHub 主页</span>
                <input
                  name="profile_url"
                  defaultValue={githubProfileUrl}
                  placeholder="https://github.com/xxx"
                />
              </label>
              <label className={styles.fieldLabel}>
                <span>凭据来源</span>
                <select name="credential_source" className={styles.select} defaultValue={githubCredentialSource}>
                  <option value="runner_env">Runner 环境变量</option>
                  <option value="ssh_agent">SSH Agent</option>
                  <option value="github_app">GitHub App</option>
                  <option value="oauth">OAuth 授权</option>
                  <option value="manual_review">人工审批后手动执行</option>
                </select>
              </label>
              <label className={styles.fieldLabel}>
                <span>凭据标识</span>
                <input
                  name="credential_ref"
                  data-github-credential-ref="1"
                  defaultValue={githubCredentialRef}
                  placeholder="例如 GITHUB_TOKEN / runner-local:GITHUB_TOKEN"
                />
              </label>
              <label className={styles.fieldLabel}>
                <span>默认 clone</span>
                <select name="default_clone_protocol" className={styles.select} defaultValue={githubCloneProtocol}>
                  <option value="https">HTTPS</option>
                  <option value="ssh">SSH</option>
                </select>
              </label>
              <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                <span>权限范围</span>
                <input
                  name="permission_scopes"
                  defaultValue={githubPermissionScopes.join(", ")}
                  placeholder="例如 repo, workflow, read:org"
                />
              </label>
              <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                <span>绑定说明</span>
                <textarea
                  name="notes"
                  defaultValue={text(githubAccountBinding.notes, "")}
                  placeholder="例如：仅用于本项目代码同步；明文 token 放在 runner 环境变量，不存项目配置。"
                />
              </label>
            </div>
            <div className={styles.inlineActions}>
              <button type="submit" data-github-account-bind-submit="1" data-loading-label="正在保存 GitHub 账号绑定">
                保存 GitHub 账号绑定
              </button>
            </div>
          </form>
          {githubAccountBound ? (
            <form action={bindProjectGithubAccount.bind(null, projectId)} className={styles.inlineDangerForm}>
              <input type="hidden" name="return_to" value={gitPanelReturnPath} />
              <input type="hidden" name="binding_action" value="clear" />
              <button type="submit" className={styles.ghostButton} data-loading-label="正在清除 GitHub 账号绑定">
                清除 GitHub 账号绑定
              </button>
            </form>
          ) : null}
        </div>

        <div className={styles.featureCard} data-git-preflight-card="1">
          <div className={styles.listHead}>
            <strong>电脑 Git 预检回执</strong>
            <span className={styles.stateBadge}>{gitPreflightSummary.total} 条</span>
          </div>
          <p>
            登记同步或回退后，平台会让每台已接入电脑先做只读预检。这里直接看它有没有接单、缺不缺 Git 或环境变量、是否需要人工审批；这一步不会执行 push、pull、reset。
          </p>
          {gitPreflightAttention ? (
            <div
              className={styles.noticeCard}
              data-git-preflight-attention={gitPreflightAttention.level}
            >
              <div className={styles.listHead}>
                <strong>{gitPreflightAttention.level === "critical" ? "需要马上处理" : "需要留意"}</strong>
                <span className={`${styles.miniChip} ${gitPreflightAttention.level === "critical" ? styles.miniChipCritical : styles.miniChipWarning}`}>
                  Git 预检
                </span>
              </div>
              <p>{gitPreflightAttention.summary}</p>
            </div>
          ) : null}
          <div className={styles.cardGridCompact}>
            <article className={styles.card}>
              <span>覆盖电脑</span>
              <strong>{gitPreflightSummary.runnerCount} 台</strong>
              <p>{gitPreflightSummary.resultCount} 条结果回执 / {gitPreflightSummary.pendingCount} 条待接单 / {gitPreflightSummary.overdueCount} 条超时</p>
            </article>
            <article className={styles.card}>
              <span>通过结果</span>
              <strong>{gitPreflightSummary.passingCount} 条</strong>
              <p>只读检查通过后，仍然按项目规则走人工确认。</p>
            </article>
            <article className={styles.card}>
              <span>阻塞</span>
              <strong>{gitPreflightSummary.blockedCount} 条</strong>
              <p>常见是缺仓库地址、缺 Git、误填明文 token 或请求非只读操作。</p>
            </article>
            <article className={styles.card}>
              <span>提醒</span>
              <strong>{gitPreflightSummary.warningCount} 条</strong>
              <p>比如 Runner 没有 GITHUB_TOKEN，或凭据需要人工审批。</p>
            </article>
          </div>
          <ul className={styles.list} data-git-preflight-list="1">
            {gitPreflightFeed.length ? (
              gitPreflightFeed.map((item) => (
                <li key={item.id} data-git-preflight-item={item.id}>
                  <strong>{item.runnerLabel} / {item.actionLabel}</strong>
                  <p>
                    {item.statusLabel}
                    {item.repositoryUrl ? ` / ${item.repositoryUrl}` : ""}
                    {item.targetRef ? ` / 目标 ${item.targetRef}` : item.branch ? ` / 分支 ${item.branch}` : ""}
                  </p>
                  <div className={styles.chipRow}>
                    <span className={styles.miniChip}>{formatStamp(item.updatedAt)}</span>
                    {item.attentionLevel !== "ok" ? (
                      <span className={`${styles.miniChip} ${item.attentionLevel === "critical" ? styles.miniChipCritical : styles.miniChipWarning}`}>
                        {item.attentionLevel === "critical" ? "需处理" : "需留意"}
                      </span>
                    ) : null}
                    {item.gitVersion ? <span className={styles.miniChip}>{shortText(item.gitVersion, item.gitVersion, 42)}</span> : null}
                    {item.credentialSource ? <span className={styles.miniChip}>凭据：{item.credentialSource}{item.credentialRef ? ` / ${item.credentialRef}` : ""}</span> : null}
                    {item.messageType === "runner_command" ? <span className={styles.miniChip}>平台已派发</span> : null}
                    {item.messageType === "runner_ack" ? <span className={styles.miniChip}>最小回执</span> : null}
                    {item.messageType === "runner_result" ? <span className={styles.miniChip}>最终回执</span> : null}
                  </div>
                  <p className={styles.microCopy}>{shortText(item.summary, "暂无额外说明", 160)}</p>
                </li>
              ))
            ) : (
              <li>
                <strong>还没有 Git 预检回执</strong>
                <p>先绑定仓库并登记一次 Git 同步或回退；如果电脑已经接入 Runner，这里会出现每台电脑的接单和只读检查结果。</p>
              </li>
            )}
          </ul>
        </div>

        <div className={styles.featureCard}>
          <div className={styles.listHead}>
            <strong>可视化 Git 同步</strong>
            <span className={styles.stateBadge}>{gitRepositoryBound ? "已绑定仓库" : "待绑定仓库"}</span>
          </div>
          <p>
            同步也改成先预演、再登记。先看这次同步会不会遇到阻塞分支、审批缺口和仓库绑定问题，再决定是否把同步请求交给真实线程继续执行。
          </p>
          {gitSyncPreview ? (
            <div className={styles.noticeCard}>
              <div className={styles.listHead}>
                <strong>最近一次同步预演</strong>
                <span className={styles.stateBadge}>{syncPreviewStatus}</span>
              </div>
              <p>
                {syncPreviewStale
                  ? `当前输入已经改成 ${gitSyncProvider}，下面仍是上一次对 ${syncPreviewProvider || "未知目标"} 的预演结果。`
                  : `当前同步目标 ${display(syncPreviewProvider, "未选择")} 的预演已经生成，这一步不会写入项目活动流。`}
              </p>
              <div className={styles.cardGridCompact}>
                <article className={styles.card}>
                  <span>同步目标</span>
                  <strong>{display(syncPreviewProvider === "local" ? "本地仓库镜像" : syncPreviewProvider === "github" ? "GitHub 仓库" : syncPreviewProvider, "未选择")}</strong>
                  <p>{text(gitSyncPreview?.repository_target, "还没有绑定可同步的仓库地址")}</p>
                </article>
                <article className={styles.card}>
                  <span>分支上下文</span>
                  <strong>{`${asNumber(gitSyncPreview?.branch_count) ?? 0} 个`}</strong>
                  <p>{`${asNumber(gitSyncPreview?.merge_ready_count) ?? 0} 个可同步 / ${asNumber(gitSyncPreview?.blocked_count) ?? 0} 个阻塞`}</p>
                </article>
                <article className={styles.card}>
                  <span>高风险审批</span>
                  <strong>{`${asNumber(gitSyncPreview?.pending_high_risk_count) ?? 0} 条`}</strong>
                  <p>{syncPreviewReady ? "当前预演允许继续登记" : "建议先按提醒处理后再登记"}</p>
                </article>
              </div>
              {syncPreviewBlockers.length ? (
                <>
                  <div className={styles.listHead}>
                    <strong>预演阻塞</strong>
                  </div>
                  <ul className={styles.list}>
                    {syncPreviewBlockers.map((item, index) => (
                      <li key={`sync-preview-blocker-${index + 1}`}>
                        <strong>{`阻塞 ${index + 1}`}</strong>
                        <p>{item}</p>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {syncPreviewWarnings.length ? (
                <>
                  <div className={styles.listHead}>
                    <strong>预演提醒</strong>
                  </div>
                  <ul className={styles.list}>
                    {syncPreviewWarnings.slice(0, 4).map((item, index) => (
                      <li key={`sync-preview-warning-${index + 1}`}>
                        <strong>{`提醒 ${index + 1}`}</strong>
                        <p>{item}</p>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {syncPreviewNotes.length ? (
                <div className={styles.chipRow}>
                  {syncPreviewNotes.map((item, index) => (
                    <span key={`sync-preview-note-${index + 1}`} className={styles.miniChip}>{item}</span>
                  ))}
                </div>
              ) : null}
              {(asArray(gitSyncPreview?.merge_ready_titles).length || asArray(gitSyncPreview?.blocked_branch_titles).length) ? (
                <p className={styles.microCopy}>
                  {asArray(gitSyncPreview?.merge_ready_titles).length
                    ? `可同步分支：${asArray(gitSyncPreview?.merge_ready_titles).slice(0, 3).map((item) => display(item, "")).join(" / ")}`
                    : "当前没有可同步分支"}
                  {asArray(gitSyncPreview?.blocked_branch_titles).length
                    ? `；阻塞分支：${asArray(gitSyncPreview?.blocked_branch_titles).slice(0, 3).map((item) => display(item, "")).join(" / ")}`
                    : ""}
                </p>
              ) : null}
            </div>
          ) : null}
          <form className={styles.drawerForm}>
            <input type="hidden" name="return_to" value={gitPanelReturnPath} />
            <div className={styles.drawerFormGrid}>
              <label className={styles.fieldLabel}>
                <span>同步目标</span>
                <select
                  name="provider"
                  className={styles.select}
                  value={gitSyncProvider}
                  onChange={(event) => setGitSyncProvider(event.target.value)}
                >
                  {gitSyncProviderOptions.map((option) => (
                    <option key={`git-sync-provider-${option.id}`} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className={styles.fieldLabel}>
                <span>当前仓库</span>
                <input value={syncProviderTarget ?? "还没有绑定对应仓库地址"} readOnly />
              </label>
              <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                <span>同步原因</span>
                <textarea
                  name="notes"
                  placeholder="例如：当前有可合并分支，准备把稳定结果同步到 GitHub，供其他电脑和 Claude 工位继续接力。"
                  value={gitSyncNotes}
                  onChange={(event) => setGitSyncNotes(event.target.value)}
                />
              </label>
            </div>
            <div className={styles.inlineActions}>
              <button
                type="submit"
                formAction={previewProjectGitSync.bind(null, projectId)}
                disabled={syncPreviewDisabled}
                data-loading-label={`正在预演 Git 同步：${gitSyncProvider}`}
              >
                先预演 Git 同步
              </button>
              <button
                type="submit"
                formAction={requestProjectGitSync.bind(null, projectId)}
                disabled={syncRequestDisabled}
                data-loading-label={`正在登记 Git 同步：${gitSyncProvider}`}
              >
                登记 Git 同步请求
              </button>
              <button type="button" className={`${styles.inlineActionLink} ${styles.ghostButton}`} onClick={() => setGitSyncNotes("")}>
                清空原因
              </button>
            </div>
            <p className={styles.microCopy}>
              {gitRepositoryBound
                ? "先预演后，登记按钮才会亮。预演不会写入活动流；正式登记会给已接入电脑下发只读 Git 预检，但不会直接执行 git push 或 git pull。"
                : "先在项目管理里补齐 GitHub 地址或本地仓库路径，这里才会变成可用入口。"}
            </p>
          </form>
        </div>

        <div className={styles.featureCard}>
          <div className={styles.listHead}>
            <strong>可视化 Git 回退</strong>
            <span className={styles.stateBadge}>{gitRepositoryBound ? "已绑定仓库" : "待绑定仓库"}</span>
          </div>
          <p>
            用户先在这里选目标分支或提交引用，填一句原因，先预演，再登记。平台只会把正式登记写进项目活动流，后续再由真实线程或工位按项目约定执行。
          </p>
          <div className={styles.versionIndexGrid} data-git-rollback-version-index="1">
            {gitRollbackVersionIndex.length ? (
              gitRollbackVersionIndex.map((version) => (
                <button
                  key={`git-rollback-version-${version.ref}`}
                  type="button"
                  className={styles.versionIndexCard}
                  data-active={gitRollbackTargetRef === version.ref ? "1" : undefined}
                  data-tone={version.tone}
                  onClick={() => setGitRollbackTargetRef(version.ref)}
                  title={`选择回退预演目标：${version.ref}`}
                >
                  <span>{version.source}</span>
                  <strong>{version.label}</strong>
                  <code>{version.ref}</code>
                  <small>{version.detail}</small>
                </button>
              ))
            ) : (
              <div className={styles.noticeCard}>
                <strong>还没有可索引版本</strong>
                <p>先绑定 GitHub 仓库或让真实线程产生 Git 动态。临时仍可在下方手填分支、tag 或 commit 引用。</p>
              </div>
            )}
          </div>
          {rollbackBlockers.length ? (
            <ul className={styles.list}>
              {rollbackBlockers.slice(0, 3).map((item, index) => (
                <li key={`rollback-blocker-${index + 1}`}>
                  <strong>当前提醒 {index + 1}</strong>
                  <p>{item}</p>
                </li>
              ))}
            </ul>
          ) : null}
          {gitRollbackPreview ? (
            <div className={styles.noticeCard}>
              <div className={styles.listHead}>
                <strong>最近一次回退预演</strong>
                <span className={styles.stateBadge}>{rollbackPreviewStatus}</span>
              </div>
              <p>
                {rollbackPreviewStale
                  ? `当前输入已经改成 ${gitRollbackTargetRef.trim() || "空白"}，下面仍是上一次对 ${rollbackPreviewTarget || "未知目标"} 的预演结果。`
                  : `目标 ${rollbackPreviewTarget || "未填写"} 的预演已经生成，这一步不会写入项目活动流。`}
              </p>
              <div className={styles.cardGridCompact}>
                <article className={styles.card}>
                  <span>目标引用</span>
                  <strong>{rollbackPreviewTarget || "未填写"}</strong>
                  <p>{text(gitRollbackPreview?.next_step, "确认后再决定是否登记。")}</p>
                </article>
                <article className={styles.card}>
                  <span>分支上下文</span>
                  <strong>{`${asNumber(gitRollbackPreview?.branch_count) ?? 0} 个`}</strong>
                  <p>{`${asNumber(gitRollbackPreview?.merge_ready_count) ?? 0} 个可合并 / ${asNumber(gitRollbackPreview?.blocked_count) ?? 0} 个阻塞`}</p>
                </article>
                <article className={styles.card}>
                  <span>高风险审批</span>
                  <strong>{`${asNumber(gitRollbackPreview?.pending_high_risk_count) ?? 0} 条`}</strong>
                  <p>{rollbackPreviewReady ? "当前预演允许继续登记" : "建议先按提醒处理后再登记"}</p>
                </article>
              </div>
              {rollbackPreviewBlockers.length ? (
                <>
                  <div className={styles.listHead}>
                    <strong>预演阻塞</strong>
                  </div>
                  <ul className={styles.list}>
                    {rollbackPreviewBlockers.map((item, index) => (
                      <li key={`rollback-preview-blocker-${index + 1}`}>
                        <strong>{`阻塞 ${index + 1}`}</strong>
                        <p>{item}</p>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {rollbackPreviewWarnings.length ? (
                <>
                  <div className={styles.listHead}>
                    <strong>预演提醒</strong>
                  </div>
                  <ul className={styles.list}>
                    {rollbackPreviewWarnings.slice(0, 4).map((item, index) => (
                      <li key={`rollback-preview-warning-${index + 1}`}>
                        <strong>{`提醒 ${index + 1}`}</strong>
                        <p>{item}</p>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {rollbackPreviewNotes.length ? (
                <div className={styles.chipRow}>
                  {rollbackPreviewNotes.map((item, index) => (
                    <span key={`rollback-preview-note-${index + 1}`} className={styles.miniChip}>{item}</span>
                  ))}
                </div>
              ) : null}
              {(asArray(gitRollbackPreview?.merge_ready_titles).length || asArray(gitRollbackPreview?.blocked_branch_titles).length) ? (
                <p className={styles.microCopy}>
                  {asArray(gitRollbackPreview?.merge_ready_titles).length
                    ? `可合并分支：${asArray(gitRollbackPreview?.merge_ready_titles).slice(0, 3).map((item) => display(item, "")).join(" / ")}`
                    : "当前没有可合并分支"}
                  {asArray(gitRollbackPreview?.blocked_branch_titles).length
                    ? `；阻塞分支：${asArray(gitRollbackPreview?.blocked_branch_titles).slice(0, 3).map((item) => display(item, "")).join(" / ")}`
                    : ""}
                </p>
              ) : null}
            </div>
          ) : null}
          <form className={styles.drawerForm}>
            <input type="hidden" name="return_to" value={gitPanelReturnPath} />
            <div className={styles.drawerFormGrid}>
              <label className={styles.fieldLabel}>
                <span>回退目标</span>
                <input
                  name="target_ref"
                  placeholder="例如 develop / main / HEAD~1 / feature/xxx"
                  value={gitRollbackTargetRef}
                  onChange={(event) => setGitRollbackTargetRef(event.target.value)}
                />
              </label>
              <label className={styles.fieldLabel}>
                <span>仓库绑定</span>
                <input
                  value={
                    gitRepositoryBound
                      ? text(
                          gitExecutionRepository.github_url ?? gitExecutionRepository.local_git_url,
                          "已绑定仓库",
                        )
                      : "还没有绑定 GitHub 或本地仓库路径"
                  }
                  readOnly
                />
              </label>
              <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
                <span>回退原因</span>
                <textarea
                  name="notes"
                  placeholder="例如：回退到 develop，撤掉上一轮不稳定改动，等待 NPC1/NPC2 重新合并。"
                  value={gitRollbackNotes}
                  onChange={(event) => setGitRollbackNotes(event.target.value)}
                />
              </label>
            </div>
            <div className={styles.inlineActions}>
              <button
                type="submit"
                formAction={previewProjectGitRollback.bind(null, projectId)}
                disabled={rollbackDisabled}
                data-loading-label={`正在预演 Git 回退：${gitRollbackTargetRef || "待填写目标"}`}
              >
                先预演 Git 回退
              </button>
              <button
                type="submit"
                formAction={requestProjectGitRollback.bind(null, projectId)}
                disabled={rollbackRequestDisabled}
                data-loading-label={`正在登记 Git 回退：${gitRollbackTargetRef || "待填写目标"}`}
              >
                登记 Git 回退请求
              </button>
              <button type="button" className={`${styles.inlineActionLink} ${styles.ghostButton}`} onClick={() => setGitRollbackNotes("")}>
                清空原因
              </button>
            </div>
            <p className={styles.microCopy}>
              {gitRepositoryBound
                ? "先预演后，登记按钮才会亮。预演不会写入活动流；正式登记会给已接入电脑下发只读 Git 预检，但不会直接执行 git reset。真正执行仍要走后续工位和人审。"
                : "先在项目管理里补齐 GitHub 地址或本地仓库路径，这里才会变成可用入口。"}
            </p>
          </form>
        </div>

        <div className={styles.listHead}>
          <strong>维护任务状态</strong>
        </div>
        <ul className={styles.list}>
          {maintenanceBoard.map((item) => (
            <li key={item.title}>
              <strong>{item.title}</strong>
              <p>{item.status} / {display(item.target, item.target)}</p>
            </li>
          ))}
        </ul>

        <div className={styles.listHead}>
          <strong>最近 Git 动态</strong>
          <span className={styles.stateBadge}>{latestGitActivity.length} 条</span>
        </div>
        <ul className={styles.list}>
          {latestGitActivity.length ? (
            latestGitActivity.map((item, index) => (
              <li key={text(item.id, `git-${index + 1}`)}>
                <strong>{text(item.title ?? item.summary ?? item.action, "Git 更新")}</strong>
                <p>{shortText(item.body ?? item.description ?? item.summary, "没有额外说明", 120)}</p>
                <p className={styles.microCopy}>{formatStamp(item.updated_at ?? item.created_at)}</p>
              </li>
            ))
          ) : (
            <li>
              <strong>还没有 Git 动态</strong>
              <p>等真实线程回完第一波结果后，这里会开始沉淀提交与回流。</p>
            </li>
          )}
        </ul>
      </div>
    );
  }

  function renderSkillsPanel() {
    const selectedSkill = resolveManagedSkill();
    const selectedSkillId = text(selectedSkill?.id, "");
    const selectedSkillIntro = resolveSkillIntro(selectedSkill);
    const selectedSkillSourceLabel = resolveSkillSourceLabel(selectedSkill);

    return (
      <div className={styles.managerStageStack}>
        <section className={styles.managerObjectHero}>
          <span className={styles.managerObjectSprite}>技</span>
          <div>
            <span className={styles.managerEyebrow}>二级：Skill 仓库对象</span>
            <h3>{selectedSkill ? text(selectedSkill.label, selectedSkillId) : "还没有 Skill"}</h3>
            <p className={styles.skillIntroCopy}>
              {selectedSkill
                ? `${isBaselineSkill(selectedSkill) ? "固定必备" : "可装配职业 Skill"} / ${selectedSkillIntro}`
                : "Skill 仓库只负责维护词条，给 NPC 装配要进入 NPC 的三级抽屉。"}
            </p>
            {selectedSkill ? <p className={styles.microCopy}>{selectedSkillSourceLabel}</p> : null}
          </div>
        </section>

        <div className={styles.managerStatGrid}>
          <article><span>固定 Skill</span><strong>{baselineSkills.length}</strong></article>
          <article><span>职业 Skill</span><strong>{roleSkills.length}</strong></article>
          <article><span>仓库总数</span><strong>{skillLibrary.length}</strong></article>
        </div>

        <div className={styles.managerStatGrid}>
          <article data-skill-agency-count={agencySkillCount}><span>Agency Agents</span><strong>{agencySkillCount}</strong></article>
          <article data-skill-github-count={githubSkillCount}><span>GitHub</span><strong>{githubSkillCount}</strong></article>
          <article><span>可见分类</span><strong>{skillCategorySummary.length}</strong></article>
          <article><span>当前筛选</span><strong>{filteredSkills.length}</strong></article>
        </div>

        <input
          className={styles.searchInput}
          data-skill-search-input="1"
          placeholder="搜索 Skill，例如：git / frontend / embedded / engineering / 测试"
          value={skillQuery}
          onChange={(event) => setSkillQuery(event.target.value)}
        />

        <div className={styles.managerActionGrid}>
          <button type="button" data-skill-open-detail="1" onClick={() => openManagerDrawer("skill-detail", selectedSkillId)} disabled={!selectedSkillId}>查看详情</button>
          <button type="button" onClick={() => openManagerDrawer("skill-create")}>添加 Skill</button>
          <button type="button" data-skill-open-github-import="1" onClick={() => openManagerDrawer("skill-github-import")}>
            从 GitHub 导入
          </button>
          <button type="button" data-skill-open-import-drawer="1" onClick={() => openManagerDrawer("skill-import")}>
            选择性导入 Agency Agents
          </button>
          <form action={importAgencyAgentsSkillPack.bind(null, projectId)}>
            <input type="hidden" name="return_to" value={skillLibraryReturnPath} />
            <button type="submit" className={styles.ghostButton} data-skill-import-agency-pack="1" data-loading-label="正在导入 Agency Agents Skill">
              导入 Agency Agents 全量 Skill
            </button>
          </form>
        </div>

        <section className={styles.managerPreviewPanel}>
          <div className={styles.listHead}>
            <strong>Skill 分类</strong>
            <span className={styles.stateBadge}>{skillCategorySummary.length} 类</span>
          </div>
          <div className={styles.managerCardGrid}>
            {skillCategorySummary.length ? (
              skillCategorySummary.slice(0, 8).map((category) => (
                <article key={`skill-category-${category.id}`} data-skill-category-card={category.id}>
                  <strong>{category.label}</strong>
                  <p>{category.count} 条 / {category.sampleLabels.join(" / ")}</p>
                </article>
              ))
            ) : (
              <article>
                <strong>还没有分类结果</strong>
                <p>先导入外部 Skill 包或新增项目 Skill，这里会自动按分类归档。</p>
              </article>
            )}
          </div>
        </section>

        <section className={styles.managerPreviewPanel}>
          <div className={styles.listHead}>
            <strong>Skill 套装与来源</strong>
            <span className={styles.stateBadge}>{PLATFORM_SKILL_STARTER_KITS.length} 套</span>
          </div>
          <div className={styles.managerCardGrid}>
            {PLATFORM_SKILL_STARTER_KITS.slice(0, 4).map((kit) => (
              <article key={kit.id}>
                <strong>{kit.label}</strong>
                <p>{kit.note}</p>
              </article>
            ))}
            <article>
              <strong>Agency Agents 外部来源</strong>
              <p>
                当前项目已可直接导入
                {" "}
                <a href="https://github.com/msitarzewski/agency-agents" target="_blank" rel="noreferrer">msitarzewski/agency-agents</a>
                {" "}
                这套角色型 skill，统一落进项目 Skill 仓库里。
              </p>
            </article>
          </div>
        </section>
      </div>
    );
  }

  function renderExchangeDetailDrawer() {
    const rawDrawerId = text(managerDrawer?.id, "");
    const separatorIndex = rawDrawerId.indexOf(":");
    const detailType = separatorIndex >= 0 ? rawDrawerId.slice(0, separatorIndex) : "";
    const detailId = separatorIndex >= 0 ? rawDrawerId.slice(separatorIndex + 1) : rawDrawerId;

    const message = props.collaborationMessages.find((item) => text(item.id, "") === detailId) ?? null;
    const proofItem = cooperationProofFeed.find((item) => item.id === detailId) ?? null;

    if (detailType === "proof") {
      if (!proofItem) {
        return (
          <div className={styles.drawerStack}>
            <div className={styles.noticeCard}>
              <strong>没有找到这条证明</strong>
              <p>这条线程闭环证明可能已经被清理，或者当前过滤条件下暂时不可见。</p>
            </div>
          </div>
        );
      }
      const proofRouteKeys = uniqueStrings([proofItem.target, ...proofItem.routeKeys]);
      const targetLink =
        proofRouteKeys
          .map((candidate) => resolveExchangeTargetFromCandidate(candidate))
          .find((candidate): candidate is NonNullable<typeof candidate> => Boolean(candidate)) ?? null;
      const fallbackThreadTarget = targetLink?.threadId || proofRouteKeys[0] || "";
      const proofSeatJumpId = targetLink?.seatId || "";
      return (
        <div className={styles.drawerStack}>
          <div className={styles.drawerSubject}>
            <strong>{proofItem.title}</strong>
            <p>{`真线程闭环证明 / ${proofItem.dispatchLabel} / ${proofItem.progressLabel} / ${proofItem.finalLabel}`}</p>
          </div>
          <div className={styles.noticeCard}>
            <strong>收口概览</strong>
            <p>{proofItem.body}</p>
            <div className={styles.chipRow}>
              <span className={styles.miniChip}>{proofItem.evidenceLabel}</span>
              <span className={styles.miniChip}>{proofItem.dispatchLabel}</span>
              <span className={styles.miniChip}>{proofItem.progressLabel}</span>
              <span className={styles.miniChip}>{proofItem.finalLabel}</span>
              {proofItem.contextLabel ? <span className={styles.miniChip}>{proofItem.contextLabel}</span> : null}
              {proofItem.skillLoadout.slice(0, 4).map((skill) => (
                <span key={`${proofItem.id}-drawer-skill-${skill}`} className={styles.miniChip}>{skill}</span>
              ))}
            </div>
          </div>
          <div className={styles.noticeCard}>
            <strong>链路元信息</strong>
            <p>{`目标线程：${proofItem.target}`}</p>
            {proofItem.requirementId ? <p>{`Requirement：${proofItem.requirementId.slice(0, 8)}`}</p> : null}
            {proofItem.providerLabel ? <p>{`Provider：${proofItem.providerLabel}`}</p> : null}
            {proofItem.computerNodeLabel ? <p>{`电脑：${proofItem.computerNodeLabel}`}</p> : null}
            <p className={styles.microCopy}>{proofItem.meta}</p>
          </div>
          {proofItem.repoSummary || proofItem.referenceSummary ? (
            <div className={styles.noticeCard}>
              <strong>仓库与参考</strong>
              {proofItem.repoSummary ? <p>{`仓库协作：${proofItem.repoSummary}`}</p> : null}
              {proofItem.referenceSummary ? <p>{`参考资料：${proofItem.referenceSummary}`}</p> : null}
            </div>
          ) : null}
          {fallbackThreadTarget || targetLink?.seatId ? (
            <div className={styles.inlineActions}>
              {fallbackThreadTarget ? (
                <button
                  type="button"
                  className={styles.ghostButton}
                  data-exchange-proof-jump-thread={fallbackThreadTarget}
                  onClick={() => openMachineRoomThread(fallbackThreadTarget, targetLink?.computerNodeId)}
                >
                  {targetLink?.threadId ? "去机房定位" : "去机房查看历史线程"}
                </button>
              ) : null}
              {proofSeatJumpId ? (
                <button
                  type="button"
                  className={styles.ghostButton}
                  data-exchange-proof-jump-seat={proofSeatJumpId}
                  onClick={() => openNpcProfileFromExchange(proofSeatJumpId)}
                >
                  看 NPC 属性
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      );
    }

    if (detailType === "thread") {
      const thread = machineRoomVisibleWorkstations.find((item) => text(item.id ?? item.workstation_id ?? item.config_id, "") === detailId) ?? null;
      if (!thread) {
        return (
          <div className={styles.drawerStack}>
            <div className={styles.noticeCard}>
              <strong>没有找到这条线程</strong>
              <p>这条线程详情可能已经被删除，或者当前过滤条件下暂时不可见。</p>
            </div>
          </div>
        );
      }
      const activity = buildWorkstationActivitySummary(thread, props.collaborationMessages);
      const threadId = text(thread.id ?? thread.workstation_id ?? thread.config_id, "");
      const targetLink = resolveExchangeTargetFromCandidate(threadId);
      return (
        <div className={styles.drawerStack}>
          <div className={styles.drawerSubject}>
            <strong>{display(thread.name ?? thread.label, threadId || "线程")}</strong>
            <p>{`线程焦点 / ${activity.activityHealthLabel} / ${activity.activityFreshnessLabel}`}</p>
          </div>
          <div className={styles.noticeCard}>
            <strong>最近命令</strong>
            <p>{activity.latestCommandLabel || "暂时还没有平台派工记录。"}</p>
            <p className={styles.microCopy}>
              {activity.latestCommandAt ? `时间：${formatStamp(activity.latestCommandAt)}` : "时间：暂无"}
              {activity.latestCommandBody ? ` / ${activity.latestCommandBody}` : ""}
            </p>
          </div>
          <div className={styles.noticeCard}>
            <strong>最近回执</strong>
            <p>{activity.latestAckLabel || "暂时还没有最小回执。"}</p>
            <p className={styles.microCopy}>
              {activity.latestAckAt ? `时间：${formatStamp(activity.latestAckAt)}` : "时间：暂无"}
              {activity.latestAckBody ? ` / ${activity.latestAckBody}` : ""}
            </p>
          </div>
          <div className={styles.noticeCard}>
            <strong>最近最终回复</strong>
            <p>{activity.latestFinalReplyLabel || "暂时还没有最终回复。"}</p>
            <p className={styles.microCopy}>
              {activity.latestFinalReplyAt ? `时间：${formatStamp(activity.latestFinalReplyAt)}` : "时间：暂无"}
              {activity.latestFinalReplyBody ? ` / ${activity.latestFinalReplyBody}` : ""}
            </p>
          </div>
          {targetLink?.threadId || targetLink?.seatId ? (
            <div className={styles.inlineActions}>
              {targetLink?.threadId ? (
                <button
                  type="button"
                  className={styles.ghostButton}
                  onClick={() => openMachineRoomThread(targetLink.threadId ?? "", targetLink.computerNodeId)}
                >
                  去机房定位
                </button>
              ) : null}
              {targetLink?.seatId ? (
                <button
                  type="button"
                  className={styles.ghostButton}
                  onClick={() => openNpcProfileFromExchange(targetLink.seatId ?? "")}
                >
                  看 NPC 属性
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      );
    }

    if (!message) {
      return (
        <div className={styles.drawerStack}>
          <div className={styles.noticeCard}>
            <strong>没有找到这条协作记录</strong>
            <p>这条详情可能已经被清理，或者当前账号没有读取它的权限。</p>
          </div>
        </div>
      );
    }

    const senderLabel = actorLabel(message, display);
    const targetCandidate =
      detailType === "command"
        || detailType === "queue"
        ? text(message.recipient_id, "")
        : detailType === "receipt"
          ? text(message.sender_id ?? message.agent_id, "")
          : "";
    const targetLink = targetCandidate ? resolveExchangeTargetFromCandidate(targetCandidate) : null;
    const messageStatus = text(message.status, "").toLowerCase();
    const messageType = text(message.message_type, "").toLowerCase();
    const messageCreatedAt = latestMessageAt(message);
    const messageAgeMinutes = queueAgeMinutes(messageCreatedAt);
    const messageAgeLabel = formatQueueAge(messageAgeMinutes);
    const messageIsQueued = isQueuedBridgeStatus(messageStatus);
    const showStaleQueueControls =
      detailType === "queue" || (detailType === "command" && messageIsQueued && (messageAgeMinutes ?? 0) >= 120);
    const queueRequeueTargets = buildExchangeCommandTargets();
    const canRequeueMessage = ["agent_command", "requirement_dispatch"].includes(messageType);
    const detailTitle =
      detailType === "sync"
        ? text(message.title, "未命名共享动态")
        : detailType === "command" || detailType === "queue"
          ? text(message.title, "未命名协作指令")
          : text(message.title, "未命名协作结果");
    const detailKindLabel =
      detailType === "sync"
        ? "成员共享动态"
        : detailType === "queue"
          ? "旧队列处理"
          : detailType === "command"
            ? "平台派工"
          : text(message.message_type, "").toLowerCase() === "agent_result" || text(message.message_type, "").toLowerCase() === "requirement_final_reply"
            ? "最终回复"
            : "最小回执";

    return (
      <div className={styles.drawerStack}>
        <div className={styles.drawerSubject}>
          <strong>{detailTitle}</strong>
          <p>{`${detailKindLabel} / ${senderLabel}${text(message.status, "") ? ` / ${text(message.status, "")}` : ""}`}</p>
        </div>
        <div className={styles.noticeCard}>
          <strong>完整内容</strong>
          <p>{text(message.body, "没有正文。")}</p>
        </div>
        <div className={styles.noticeCard}>
          <strong>协作元信息</strong>
          <p>{`发起：${senderLabel}`}</p>
          <p>{`记录时间：${formatStamp(message.updated_at ?? message.created_at)}`}</p>
          {detailType === "command" || detailType === "queue" ? (
            <p>{`目标：${display(message.recipient_id, text(message.recipient_id, "未指定"))}`}</p>
          ) : detailType === "receipt" ? (
            <p>{`来源执行位：${display(message.sender_id ?? message.agent_id, text(message.sender_id ?? message.agent_id, "未指定"))}`}</p>
          ) : null}
        </div>
        {showStaleQueueControls ? (
          <div
            className={`${styles.noticeCard} ${styles.featureCardFocused}`}
            data-exchange-stale-queue-actions={text(message.id, "")}
          >
            <div className={styles.listHead}>
              <strong>旧队列人工处理</strong>
              <span className={styles.stateBadge}>{messageAgeLabel ? `已等 ${messageAgeLabel}` : "等待中"}</span>
            </div>
            <p>
              这里不会自动执行远端 AI，只登记人的决定。多线程协作时先人工判断这条指令是继续等、作废，还是重派到一个正在接单的线程，避免平台反复消耗 token。
            </p>
            <div className={styles.cardGridCompact}>
              <article className={styles.card}>
                <span>当前状态</span>
                <strong>{messageStatus || "未知"}</strong>
                <p>{messageType || "未知类型"}</p>
              </article>
              <article className={styles.card}>
                <span>原目标</span>
                <strong>{display(message.recipient_id, text(message.recipient_id, "未指定"))}</strong>
                <p>处理旧队列不会删除原始记录。</p>
              </article>
            </div>
            <div className={styles.inlineActions}>
              <form action={handleStaleQueueDecision}>
                <input type="hidden" name="project_id" value={projectId} />
                <input type="hidden" name="message_id" value={text(message.id, "")} />
                <input type="hidden" name="decision" value="keep" />
                <input type="hidden" name="return_to" value={buildExchangeSurfaceHref("overview")} />
                <button type="submit" className={styles.ghostButton} data-exchange-stale-queue-action="keep" data-loading-label="正在保留旧队列">
                  保留等待
                </button>
              </form>
              <form action={handleStaleQueueDecision}>
                <input type="hidden" name="project_id" value={projectId} />
                <input type="hidden" name="message_id" value={text(message.id, "")} />
                <input type="hidden" name="decision" value="expire" />
                <input type="hidden" name="return_to" value={buildExchangeSurfaceHref("overview")} />
                <button type="submit" className={styles.ghostButton} data-exchange-stale-queue-action="expire" data-loading-label="正在标记过期">
                  标记过期
                </button>
              </form>
            </div>
            {canRequeueMessage ? (
              <form action={handleStaleQueueDecision} className={styles.skillManagerForm}>
                <input type="hidden" name="project_id" value={projectId} />
                <input type="hidden" name="message_id" value={text(message.id, "")} />
                <input type="hidden" name="decision" value="requeue" />
                <input type="hidden" name="target_recipient_type" value="workstation" />
                <input type="hidden" name="return_to" value={buildExchangeSurfaceHref("overview")} />
                <label className={styles.fieldLabel}>
                  <span>重派到哪个线程 / NPC</span>
                  <select name="target_recipient_id" className={styles.select} defaultValue={targetCandidate || queueRequeueTargets[0]?.id || ""}>
                    {queueRequeueTargets.length ? (
                      queueRequeueTargets.map((target) => (
                        <option key={`queue-requeue-target-${target.id}`} value={target.id}>
                          {`${target.label} · ${target.providerLabel} · ${target.meta}`}
                        </option>
                      ))
                    ) : (
                      <option value="">没有可重派目标</option>
                    )}
                  </select>
                </label>
                <label className={styles.fieldLabel}>
                  <span>处理备注</span>
                  <textarea
                    name="reviewer_note"
                    placeholder="例如：原电脑离线，改派给当前正在接单的只读线程。"
                  />
                </label>
                <button
                  type="submit"
                  disabled={!queueRequeueTargets.length}
                  data-exchange-stale-queue-action="requeue"
                  data-loading-label="正在重派旧队列"
                >
                  人工重派到选中线程
                </button>
              </form>
            ) : (
              <p className={styles.microCopy}>这条不是 AI 派工类消息，先标记过期后从对应入口重新发起。</p>
            )}
          </div>
        ) : null}
        {targetLink?.threadId || targetLink?.seatId ? (
          <div className={styles.inlineActions}>
            {targetLink.threadId ? (
              <button
                type="button"
                className={styles.ghostButton}
                onClick={() => openMachineRoomThread(targetLink.threadId ?? "", targetLink.computerNodeId)}
              >
                去机房定位
              </button>
            ) : null}
            {targetLink.seatId ? (
              <button
                type="button"
                className={styles.ghostButton}
                onClick={() => openNpcProfileFromExchange(targetLink.seatId ?? "")}
              >
                看 NPC 属性
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  function managerDrawerTitle(drawer: ManagerDrawerState) {
    switch (drawer.kind) {
      case "exchange-detail":
        return text(drawer.id, "").startsWith("queue:") ? "旧队列处理" : "协作详情";
      case "npc-create":
        return "添加 NPC";
      case "npc-dialog":
        return "NPC 对话框";
      case "npc-profile":
        return "NPC 属性与知识库";
      case "npc-bind":
        return "绑定电脑与线程";
      case "npc-skills":
        return "装配 Skill";
      case "computer-connect":
        return "添加电脑";
      case "computer-threads":
        return "配对 / 扫描线程";
      case "skill-create":
        return "添加 Skill";
      case "skill-github-import":
        return "从 GitHub 导入 Skill";
      case "skill-import":
        return "选择性导入 Skill";
      case "skill-detail":
        return "Skill 详情";
      case "development-module":
        return drawer.id === DEVELOPMENT_STATION_CREATE_DRAWER_ID ? "添加工位" : "工位设置";
      default:
        return "三级抽屉";
    }
  }

  function toggleDrawerSkillLoadout(
    skillId: string,
    setter: Dispatch<SetStateAction<string[]>>,
  ) {
    setter((current) => {
      const normalized = skillId.toLowerCase();
      if (current.some((item) => item.toLowerCase() === normalized)) {
        return current.filter((item) => item.toLowerCase() !== normalized);
      }
      return [...current, skillId];
    });
  }

  function toggleSkillImportSelection(skillId: string) {
    setSkillImportSelection((current) => {
      const normalized = skillId.toLowerCase();
      if (current.some((item) => item.toLowerCase() === normalized)) {
        return current.filter((item) => item.toLowerCase() !== normalized);
      }
      return [...current, skillId];
    });
  }

  function applySkillImportBundle(preset: SkillImportBundlePreset) {
    const availableIds = preset.skillIds.filter((skillId) => agencySkillPackById.has(skillId.toLowerCase()));
    setSkillImportSelection(availableIds);
    setSkillImportRecommendedOnly(true);
    setSkillImportQuery("");
    setSkillImportCategoryFilter("all");
    setSkillImportStatusFilter("all");
  }

  function applyNpcSkillFilterPreset(preset: NpcSkillFilterPreset | null) {
    setNpcSkillQuery(text(preset?.query, ""));
    setNpcSkillCategoryFilter(text(preset?.category, "all"));
    setNpcSkillSourceFilter(text(preset?.source, "all"));
  }

  function renderNpcSkillLoadoutPicker(options: {
    selectedSkillIds: string[];
    orderedSkills: AnyRecord[];
    recommendedSkillIds?: string[];
    setSelectedSkillIds: Dispatch<SetStateAction<string[]>>;
    dataPrefix: string;
    helperText: string;
  }) {
    const selectedSkillSet = new Set(options.selectedSkillIds.map((item) => item.toLowerCase()));
    const recommendedSkillSet = new Set((options.recommendedSkillIds ?? []).map((item) => item.toLowerCase()));
    const selectedSkills = options.selectedSkillIds.map((skillId) => {
      const skill = skillById.get(skillId.toLowerCase());
      return {
        id: skillId,
        label: text(skill?.label, skillId),
        sourceLabel: skill ? resolveSkillSourceLabel(skill) : "已选职业 Skill",
        fitStations: skill ? shortText(resolveSkillFitStations(skill).join(" / "), "暂无建议工位", 56) : "暂无建议工位",
        deliverables: skill ? shortText(resolveSkillDeliverables(skill).join(" / "), "暂无交付物", 64) : "暂无交付物",
      };
    });
    const filtered = options.orderedSkills.filter((skill) =>
      matchesSkillLoadoutFilters(skill, {
        query: npcSkillQuery,
        category: npcSkillCategoryFilter,
        source: npcSkillSourceFilter,
      }),
    );
    const capped = filtered.slice(0, npcSkillQuery.trim() || npcSkillCategoryFilter !== "all" || npcSkillSourceFilter !== "all" ? 40 : 24);
    const visibleCount = capped.length;
    const hiddenCount = Math.max(filtered.length - visibleCount, 0);
    const allPresetActive = !npcSkillQuery.trim() && npcSkillCategoryFilter === "all" && npcSkillSourceFilter === "all";

    return (
      <div className={styles.drawerStack}>
        {options.selectedSkillIds.map((skillId) => (
          <input key={`${options.dataPrefix}-skill-hidden-${skillId}`} type="hidden" name="skill_loadout" value={skillId} />
        ))}
        <div className={styles.noticeCard} data-npc-skill-picker={options.dataPrefix}>
          <strong>职业 Skill 装配器</strong>
          <p>{options.helperText}</p>
          <p className={styles.microCopy}>
            当前已选 {options.selectedSkillIds.length} 条 / 当前命中 {filtered.length} 条
            {hiddenCount ? ` / 先显示前 ${visibleCount} 条，剩下 ${hiddenCount} 条请继续筛` : ""}
          </p>
        </div>
        <div className={styles.noticeCard} data-npc-skill-selected-tray={options.dataPrefix}>
          <strong>已选职业 Skill</strong>
          <p className={styles.microCopy}>
            {selectedSkills.length
              ? "这里就是当前装配结果。点下面已选条目就能立刻移除，不用再滚回列表里找。"
              : "还没选职业 Skill。可以先点一个快速预设，再从候选列表里勾选。"}
          </p>
          <div className={styles.selectedSkillTray} data-npc-skill-selected-count={`${options.dataPrefix}:${selectedSkills.length}`}>
            {selectedSkills.length ? (
              selectedSkills.map((skill) => (
                <button
                  key={`${options.dataPrefix}-selected-${skill.id}`}
                  type="button"
                  className={styles.selectedSkillChip}
                  data-npc-skill-selected-chip={`${options.dataPrefix}:${skill.id}`}
                  onClick={() => toggleDrawerSkillLoadout(skill.id, options.setSelectedSkillIds)}
                >
                  <strong>{skill.label}</strong>
                  <small>{skill.sourceLabel} / 点此移除</small>
                  <small>{`适合工位：${skill.fitStations}`}</small>
                  <small>{`常见交付物：${skill.deliverables}`}</small>
                </button>
              ))
            ) : (
              <p className={styles.objectRailEmpty}>当前还没有职业 Skill 装配。</p>
            )}
          </div>
          {selectedSkills.length ? (
            <div className={styles.chipRow}>
              <button
                type="button"
                className={styles.miniChipButton}
                data-npc-skill-selected-clear={options.dataPrefix}
                onClick={() => options.setSelectedSkillIds([])}
              >
                清空已选
              </button>
            </div>
          ) : null}
        </div>
        <input
          className={styles.searchInput}
          data-npc-skill-search={options.dataPrefix}
          placeholder="筛选 Skill，例如：frontend / embedded / 测试 / engineering"
          value={npcSkillQuery}
          onChange={(event) => setNpcSkillQuery(event.target.value)}
        />
        <div className={styles.filterToolbar}>
          <span className={styles.formLabel}>快速预设</span>
          <div className={styles.chipRow}>
            <button
              type="button"
              data-npc-skill-preset={`${options.dataPrefix}-all`}
              className={allPresetActive ? styles.miniChipButtonActive : styles.miniChipButton}
              onClick={() => applyNpcSkillFilterPreset(null)}
            >
              全部候选
            </button>
            {NPC_SKILL_FILTER_PRESETS.map((preset) => {
              const active =
                npcSkillQuery.trim().toLowerCase() === text(preset.query, "").trim().toLowerCase() &&
                npcSkillCategoryFilter === text(preset.category, "all") &&
                npcSkillSourceFilter === text(preset.source, "all");
              return (
                <button
                  key={`${options.dataPrefix}-preset-${preset.id}`}
                  type="button"
                  data-npc-skill-preset={`${options.dataPrefix}-${preset.id}`}
                  className={active ? styles.miniChipButtonActive : styles.miniChipButton}
                  onClick={() => applyNpcSkillFilterPreset(preset)}
                  title={preset.hint}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
          <p className={styles.microCopy}>给小白的快速入口：先按职业预设收窄，再细筛关键词和来源。</p>
        </div>
        <div className={styles.filterToolbar}>
          <span className={styles.formLabel}>来源过滤</span>
          <div className={styles.chipRow}>
            <button
              type="button"
              data-npc-skill-source={`${options.dataPrefix}-all`}
              className={npcSkillSourceFilter === "all" ? styles.miniChipButtonActive : styles.miniChipButton}
              onClick={() => setNpcSkillSourceFilter("all")}
            >
              全部来源
            </button>
            {roleSkillSourceSummary.map((source) => (
              <button
                key={`${options.dataPrefix}-source-${source.id}`}
                type="button"
                data-npc-skill-source={`${options.dataPrefix}-${source.id}`}
                className={npcSkillSourceFilter === source.id ? styles.miniChipButtonActive : styles.miniChipButton}
                onClick={() => setNpcSkillSourceFilter(source.id)}
              >
                {source.label} {source.count}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.filterToolbar}>
          <span className={styles.formLabel}>分类过滤</span>
          <div className={styles.chipRow}>
            <button
              type="button"
              data-npc-skill-category={`${options.dataPrefix}-all`}
              className={npcSkillCategoryFilter === "all" ? styles.miniChipButtonActive : styles.miniChipButton}
              onClick={() => setNpcSkillCategoryFilter("all")}
            >
              全部分类
            </button>
            {roleSkillCategorySummary.slice(0, 10).map((category) => (
              <button
                key={`${options.dataPrefix}-category-${category.id}`}
                type="button"
                data-npc-skill-category={`${options.dataPrefix}-${category.id}`}
                className={npcSkillCategoryFilter === category.id ? styles.miniChipButtonActive : styles.miniChipButton}
                onClick={() => setNpcSkillCategoryFilter(category.id)}
              >
                {category.label} {category.count}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.checkGrid} data-npc-skill-visible-count={`${options.dataPrefix}:${filtered.length}`}>
          {capped.length ? (
            capped.map((skill) => {
              const skillId = text(skill.id, "");
              const checked = selectedSkillSet.has(skillId.toLowerCase());
              const sourceLabel = resolveSkillSourceLabel(skill);
              const fitStations = shortText(resolveSkillFitStations(skill).join(" / "), "暂无建议工位", 52);
              const intro = shortText(resolveSkillIntro(skill), text(skill.note, "暂无说明"), 90);
              const recommended = recommendedSkillSet.has(skillId.toLowerCase());
              return (
                <label
                  key={`${options.dataPrefix}-skill-${skillId}`}
                  className={`${styles.checkItem} ${styles.checkItemRich} ${checked ? styles.checkItemSelected : ""}`}
                  data-npc-skill-option={`${options.dataPrefix}:${skillId}`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleDrawerSkillLoadout(skillId, options.setSelectedSkillIds)}
                  />
                  <span className={styles.checkItemText}>
                    <strong>{text(skill.label, skillId)}</strong>
                    <small>{sourceLabel}{recommended ? " / 推荐" : ""}</small>
                    <small>{`适合工位：${fitStations}`}</small>
                    <small>{intro}</small>
                  </span>
                </label>
              );
            })
          ) : (
            <p className={styles.objectRailEmpty}>当前筛选没有命中。换个关键词，或者先把来源/分类切回“全部”。</p>
          )}
        </div>
      </div>
    );
  }

  function renderNpcCreateDrawer() {
    const developmentStation = createDrawerDevelopmentStation;
    const defaultThread = createDrawerDefaultThread;
    const defaultThreadId = text(defaultThread?.id ?? defaultThread?.workstation_id, "");
    const defaultNodeId = text(defaultThread?.computer_node_id ?? defaultThread?.computer_node ?? onlineNodes[0]?.id, "");
    const defaultProviderLabel = defaultThread ? platformProviderLabelFromThread(defaultThread) : "Codex";
    const mapSlot = codexSeats.length;
    const mapX = 760 + (mapSlot % 3) * 170;
    const mapY = 720 + (Math.floor(mapSlot / 3) % 3) * 180;
    const createReturnPath = developmentStation ? developmentWorkshopReturnPath : npcCreateReturnPath;
    const stationSignal = [
      developmentStation?.id,
      developmentStation?.label,
      developmentStation?.detail,
      developmentStation?.riskLevel,
      developmentStation?.mapLocation,
    ]
      .map((item) => text(item, ""))
      .join(" ");
    const hardwareLikeStation = /(机器人|机械|硬件|嵌入式|串口|烧录|仿真|调试|gpio|jtag|usb|高)/i.test(stationSignal);
    const defaultProjectProfile = hardwareLikeStation
      ? /(机器人|机械)/i.test(stationSignal)
        ? "robotics"
        : "embedded"
      : "software";
    const defaultApprovalPolicy = hardwareLikeStation ? "human_review_required" : "auto_continue";
    const defaultCapabilities = uniqueStrings([
      "thread-adapter",
      hardwareLikeStation ? "embedded-toolchain" : "repo-bootstrap",
      /界面|ui|前端|地图|npc/i.test(stationSignal) ? "web-game-ui" : "",
      /机器人|机械/i.test(stationSignal) ? "robotics" : "",
    ]).join(", ");

    return (
      <form action={createNpcWorkstationSeat.bind(null, projectId)} className={styles.drawerForm} data-npc-create-form="1">
        <p className={styles.microCopy}>三级：这里才填写创建信息。创建后 NPC 会固定拥有自己的知识库，线程和电脑只是当前执行壳。</p>
        <input type="hidden" name="return_to" value={createReturnPath} />
        <input type="hidden" name="source_thread_catalog" value={sourceThreadCatalogJson} />
        <input type="hidden" name="scene" value="map-farm" />
        <input type="hidden" name="avatar_key" value="jack-standing" />
        <input type="hidden" name="map_x" value={String(mapX)} />
        <input type="hidden" name="map_y" value={String(mapY)} />
        <input type="hidden" name="development_station_id" value={developmentStation?.id ?? ""} />
        <input type="hidden" name="development_station_label" value={developmentStation?.label ?? ""} />
        <input type="hidden" name="status" value="active" />
        <input type="hidden" name="require_minimal_ack" value="true" />
        <input type="hidden" name="require_final_reply" value="true" />
        <input type="hidden" name="work_kind" value="implementation" />
        <input type="hidden" name="approval_policy" value={defaultApprovalPolicy} />
        <input type="hidden" name="project_profile" value={defaultProjectProfile} />
        <input type="hidden" name="required_capabilities" value={defaultCapabilities} />
        <input type="hidden" name="token_policy_mode" value={hardwareLikeStation ? "manual_review" : "bounded"} />
        <input type="hidden" name="token_per_message_limit" value={hardwareLikeStation ? "1800" : "2500"} />
        <input type="hidden" name="token_per_round_limit" value={hardwareLikeStation ? "5000" : "8000"} />
        <input type="hidden" name="token_daily_budget" value={hardwareLikeStation ? "20000" : "30000"} />
        <input type="hidden" name="max_auto_rounds" value={hardwareLikeStation ? "1" : "3"} />
        <input type="hidden" name="human_review_after_rounds" value={hardwareLikeStation ? "1" : "3"} />
        <input type="hidden" name="parallelism_limit" value={hardwareLikeStation ? "1" : "2"} />
        <input type="hidden" name="prefer_readonly_probe" value="true" />
        <input type="hidden" name="batch_similar_tasks" value="true" />
        <input type="hidden" name="require_plan_before_execute" value={hardwareLikeStation ? "true" : "false"} />
        <input type="hidden" name="debug_enabled" value="true" />
        <input type="hidden" name="simulation_first" value={hardwareLikeStation ? "true" : "false"} />
        <input type="hidden" name="hardware_write_requires_review" value={hardwareLikeStation ? "true" : "false"} />
        <div className={styles.drawerFormGrid}>
          <label className={styles.fieldLabel}>
              <span>NPC 名字</span>
              <input name="name" defaultValue={defaultNpcNameForDevelopmentStation(developmentStation)} placeholder="例如：资料员小鹿" required />
            </label>
            <label className={styles.fieldLabel}>
              <span>职责</span>
              <input
                name="responsibility"
                defaultValue={defaultNpcResponsibilityForDevelopmentStation(developmentStation)}
                placeholder="例如：找资料 / 写文章 / 前端验收"
                required
              />
            </label>
          <label className={styles.fieldLabel}>
            <span>绑定线程</span>
            <select name="source_workstation_id" className={styles.select} defaultValue={defaultThreadId}>
              <option value="">先不绑定线程</option>
              {allThreadCandidates.map((thread, index) => {
                const threadId = text(thread.id ?? thread.workstation_id, "");
                return (
                  <option key={`create-npc-thread-${threadId || index}`} value={threadId}>
                    {display(thread.name, threadId || `线程 ${index + 1}`)} / {platformProviderLabelFromThread(thread)}
                  </option>
                );
              })}
            </select>
          </label>
          <label className={styles.fieldLabel}>
            <span>所在电脑</span>
            <select name="computer_node_id" className={styles.select} defaultValue={defaultNodeId}>
              <option value="">由线程决定</option>
              {nodes.map((node) => {
                const nodeId = text(node.id, "");
                return <option key={`create-npc-node-${nodeId}`} value={nodeId}>{text(node.label ?? node.name, nodeId)}</option>;
              })}
            </select>
          </label>
          <label className={styles.fieldLabel}>
            <span>模型</span>
            <input name="model" placeholder="例如：gpt-5.4 / claude / qwen-code" defaultValue={text(defaultThread?.model ?? defaultThread?.metadata?.model, "gpt-5.4")} />
          </label>
          <label className={styles.fieldLabel}>
            <span>提供方</span>
            <input name="ai_provider" defaultValue={defaultProviderLabel} placeholder="Codex / Claude / Qwen" />
          </label>
          <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
            <span>知识库摘要</span>
            <textarea name="knowledge_summary" placeholder="这个 NPC 要长期记住什么？例如：负责平台 UI 验收、保留前任交接。" />
          </label>
          <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
            <span>自动化模式</span>
            <label className={`${styles.checkItem} ${styles.checkItemRich}`}>
              <input type="checkbox" name="automation_enabled" value="true" defaultChecked={false} />
              <span className={styles.checkItemText}>
                <strong>开启持续自动化</strong>
                <small>关闭时：只执行你刚发送的这一条指令。</small>
                <small>开启时：会持续保持自治桥或会话，token 消耗也会更高。</small>
              </span>
            </label>
            <input type="hidden" name="automation_enabled" value="false" />
          </label>
          <label className={styles.fieldLabel}>
            <span>心跳间隔（秒）</span>
            <input
              name="automation_heartbeat_seconds"
              type="number"
              min="15"
              max="3600"
              step="15"
              defaultValue={DEFAULT_AUTOMATION_HEARTBEAT_SECONDS}
            />
            <small>只在开启持续自动化时生效；不开自动化就只执行当前指令一次。</small>
          </label>
        </div>
        {renderNpcSkillLoadoutPicker({
          selectedSkillIds: npcCreateSkillLoadout,
          orderedSkills: createDrawerOrderedRoleSkills,
          recommendedSkillIds: createDrawerSuggestedRoleSkillIds,
          setSelectedSkillIds: setNpcCreateSkillLoadout,
          dataPrefix: "npc-create",
          helperText: "固定 Skill 会自动带上。这里再按来源、分类和关键词挑选职业 Skill，创建后 NPC 还能继续补装或卸载。",
        })}
        <button type="submit" data-loading-label="正在创建 NPC">创建 NPC</button>
      </form>
    );
  }

  function renderNpcDialogDrawer() {
    const selected = resolveManagedSeat(managerDrawer?.id);
    const conversation = npcConversationFor(selected);
    const npcDialogPreviewKey = `npc-dialog-${text(selected.id, text(selected.targetId, "unselected"))}`;
    const npcDialogPreview =
      text(collaborationPreview?.preview_key, "") === npcDialogPreviewKey ? collaborationPreview : null;
    const npcDialogPreviewReady = Boolean(npcDialogPreview?.ready);
    const npcDialogPreviewNeedsHumanReview = collaborationPreviewNeedsHumanReview(npcDialogPreview);
    const npcDialogProviderId = text(selected.providerId, "").toLowerCase();
    const npcDialogProviderLabel = text(selected.providerLabel, selected.providerId || "AI");
    const npcDialogExecutionLabel = selected.automationEnabled ? "自动化执行" : "单次执行";
    const npcDialogProviderNote =
      npcDialogProviderId === "claude"
        ? "Claude 当前通过平台统一消息格式派单并回写。换电脑时由那台电脑的适配器自己确定本地仓库路径，不要求用户手填固定路径。"
        : npcDialogProviderId === "codex"
          ? "Codex 线程会按平台派单接收任务；未开启自动化时只处理本次指令，开启后才持续自治。"
          : "这个 NPC 会按平台统一消息格式接单；不同模型和电脑都应通过同一套最小回执、最终回复流程回写。";
    const npcDialogReturnPath = buildProjectSurfacePath(projectEntryPath, {
      panel: "team",
      tab: "npc-create",
      seat: text(selected.id, "") || undefined,
      drawer: "npc-dialog",
      drawer_id: text(selected.id, "") || undefined,
    });

    return (
      <div className={styles.drawerStack}>
        <div className={`${styles.drawerSubject} ${styles.npcDialogSubject}`}>
          <strong>{selected.id ? selected.name : "未选择 NPC"}</strong>
          <p>
            {selected.role} / {npcDialogProviderLabel} / {selected.sourceThreadId ? `线程 ${selected.sourceThreadId}` : "未绑定线程"}
          </p>
          <div className={styles.npcDialogModeGrid}>
            <article>
              <span>执行模式</span>
              <strong>{npcDialogExecutionLabel}</strong>
              <p>{selected.automationEnabled ? "会进入持续自治流程" : "只执行当前发送的这一条"}</p>
            </article>
            <article>
              <span>绑定线程</span>
              <strong>{selected.sourceThreadId ? "已绑定" : "待绑定"}</strong>
              <p>{selected.sourceThreadId || "先在 NPC 资料里绑定电脑线程"}</p>
            </article>
          </div>
          <p className={styles.npcDialogProviderNote}>{npcDialogProviderNote}</p>
        </div>
        <form
          action={submitCollaborationMessage}
          className={`${styles.drawerForm} ${styles.npcDialogComposer}`}
          data-npc-dialog-form={selected.id || "unselected"}
        >
          <div className={styles.npcDialogComposerHead}>
            <span>1. 发送指令</span>
            <strong>把任务直接交给这个 NPC</strong>
            <p>先写标题和指令，再点预演。预演通过后，正式发送按钮才会亮，避免误派单。</p>
          </div>
          <input type="hidden" name="project_id" value={projectId} />
          <input type="hidden" name="agent_id" value={selected.targetId} />
          <input type="hidden" name="message_type" value="agent_command" />
          <input type="hidden" name="sender_type" value="human" />
          <input type="hidden" name="sender_id" value={currentHumanSenderValue} />
          <input type="hidden" name="recipient_type" value="workstation" />
          <input type="hidden" name="recipient_id" value={selected.targetId} />
          <input type="hidden" name="npc_seat_id" value={selected.id} />
          <input type="hidden" name="status" value="queued" />
          <input type="hidden" name="return_to" value={npcDialogReturnPath} />
          <input type="hidden" name="preview_key" value={npcDialogPreviewKey} />
          <input type="hidden" name="enforce_preview" value="1" />
          <input type="hidden" name="required_preview_signature" value={text(npcDialogPreview?.preview_signature, "")} />
          <input type="hidden" name="required_preview_ready" value={npcDialogPreviewReady ? "1" : ""} />
          <label className={styles.fieldLabel}>
            <span>标题</span>
            <input
              name="title"
              placeholder="例如：协作写一篇文章：先找资料"
              defaultValue={text(npcDialogPreview?.title, "")}
              required
            />
          </label>
          <label className={styles.fieldLabel}>
            <span>指令</span>
            <textarea
              name="body"
              placeholder="写给这个 AI 的具体任务、参考资料、验收标准。"
              defaultValue={text(npcDialogPreview?.body, "")}
              required
            />
          </label>
          <div className={styles.inlineActions}>
            <button
              type="submit"
              formAction={previewCollaborationMessage}
              disabled={!selected.targetId}
              data-npc-dialog-preview={selected.id || "unselected"}
              data-loading-label="正在预演 NPC 指令"
            >
              先预演发给这个 NPC
            </button>
            <button
              type="submit"
              disabled={!selected.targetId || !npcDialogPreviewReady}
              data-npc-dialog-submit={selected.id || "unselected"}
              data-loading-label="正在发送 NPC 指令"
             >
               {npcDialogPreviewNeedsHumanReview ? "登记人工审核" : "发送给这个 NPC"}
             </button>
           </div>
           <p className={styles.microCopy}>
             先预演后，正式发送按钮才会亮。需要人审时，平台会先生成审核请求，不会把指令直接送进 NPC 绑定线程。
           </p>
          <p className={styles.microCopy}>
            {selected.automationEnabled
              ? "当前已开启自动化：发送后会继续走这个 NPC 的自动推进模式。"
              : "当前未开启自动化：发送后只执行这一条指令，不会持续自动跑。"}
          </p>
        </form>
        {renderCollaborationPreviewCard(
          npcDialogPreview,
          selected.id ? `最近一次发给 ${selected.name} 的预演` : "最近一次 NPC 对话预演",
        )}
        <div className={styles.npcDialogHistoryTitle}>
          <span>2. 最近对话</span>
          <p>这里按时间串起你发给 NPC 的指令、最小回执和最终回复。</p>
        </div>
        <ul className={styles.drawerConversation}>
          {conversation.length ? (
            conversation.map((message, index) => (
              <li key={text(message.id, `drawer-message-${index}`)}>
                <span>{collaborationBubbleLabel(message)}</span>
                <strong>{text(message.title, "无标题")}</strong>
                <p>{shortText(message.body, "没有正文", 180)}</p>
                <small>{formatStamp(message.updated_at ?? message.created_at)}</small>
              </li>
            ))
          ) : (
            <li>
              <span>空</span>
              <strong>还没有对话</strong>
              <p>给这个 NPC 发第一条指令后，最小回执和最终回复也会从这里串起来。</p>
            </li>
          )}
        </ul>
      </div>
    );
  }

  function renderNpcProfileDrawer() {
    const selected = resolveManagedSeat(managerDrawer?.id);
    if (!selected.id) {
      return <p className={styles.microCopy}>还没有 NPC。先从左侧 + 添加 NPC。</p>;
    }
    const roleSkills = selected.additionalSkillIds
      .map((skillId) => skillById.get(skillId.toLowerCase()))
      .filter((skill): skill is AnyRecord => Boolean(skill));
    const fallbackRoleSkill: AnyRecord = {
      id: `fallback-role-${selected.id}`,
      label: `${selected.name} / 职责推测`,
      note: selected.role,
      metadata: {
        description: selected.role,
        category: "custom",
        matching_text: selected.role,
      },
      source: "custom",
    };

    return (
      <form action={updateNpcWorkstationSeat.bind(null, projectId, selected.id)} className={styles.drawerForm}>
        <input type="hidden" name="return_to" value={npcCreateReturnPath} />
        <input type="hidden" name="source_thread_catalog" value={sourceThreadCatalogJson} />
        <input type="hidden" name="source_workstation_id" value={selected.sourceThreadId} />
        <input type="hidden" name="computer_node_id" value={selected.computerNodeId} />
        <input type="hidden" name="model" value={selected.model} />
        <input type="hidden" name="ai_provider_id" value={selected.providerId} />
        <input type="hidden" name="ai_provider" value={selected.providerLabel} />
        <input type="hidden" name="scene" value="map-farm" />
        <input type="hidden" name="avatar_key" value="jack-standing" />
        <input type="hidden" name="work_kind" value={selected.collabProtocol.work_kind} />
        <input type="hidden" name="approval_policy" value={selected.collabProtocol.approval_policy} />
        <input type="hidden" name="project_profile" value={selected.collabProtocol.project_profile} />
        <input type="hidden" name="required_capabilities" value={selected.collabProtocol.required_capabilities.join(", ")} />
        <input type="hidden" name="reference_paths" value={selected.collabProtocol.reference_paths.join(", ")} />
        <input type="hidden" name="require_minimal_ack" value={selected.collabProtocol.require_minimal_ack ? "true" : "false"} />
        <input type="hidden" name="require_final_reply" value={selected.collabProtocol.require_final_reply ? "true" : "false"} />
        <input type="hidden" name="token_policy_mode" value={selected.collabProtocol.token_policy.mode} />
        <input type="hidden" name="token_per_message_limit" value={String(selected.collabProtocol.token_policy.per_message_limit)} />
        <input type="hidden" name="token_per_round_limit" value={String(selected.collabProtocol.token_policy.per_round_limit)} />
        <input type="hidden" name="token_daily_budget" value={String(selected.collabProtocol.token_policy.daily_budget)} />
        <input type="hidden" name="max_auto_rounds" value={String(selected.collabProtocol.runaway_policy.max_auto_rounds)} />
        <input
          type="hidden"
          name="human_review_after_rounds"
          value={String(selected.collabProtocol.runaway_policy.human_review_after_rounds)}
        />
        <input type="hidden" name="parallelism_limit" value={String(selected.collabProtocol.efficiency_policy.parallelism_limit)} />
        <input
          type="hidden"
          name="prefer_readonly_probe"
          value={selected.collabProtocol.efficiency_policy.prefer_readonly_probe ? "true" : "false"}
        />
        <input
          type="hidden"
          name="batch_similar_tasks"
          value={selected.collabProtocol.efficiency_policy.batch_similar_tasks ? "true" : "false"}
        />
        <input
          type="hidden"
          name="require_plan_before_execute"
          value={selected.collabProtocol.efficiency_policy.require_plan_before_execute ? "true" : "false"}
        />
        <input type="hidden" name="debug_enabled" value={selected.collabProtocol.debug_policy.debug_enabled ? "true" : "false"} />
        <input
          type="hidden"
          name="simulation_first"
          value={selected.collabProtocol.debug_policy.simulation_first ? "true" : "false"}
        />
        <input
          type="hidden"
          name="hardware_write_requires_review"
          value={selected.collabProtocol.debug_policy.hardware_write_requires_review ? "true" : "false"}
        />
        {selected.additionalSkillIds.map((skillId) => (
          <input key={`profile-skill-${skillId}`} type="hidden" name="skill_loadout" value={skillId} />
        ))}
        <div className={styles.drawerFormGrid}>
          <label className={styles.fieldLabel}>
            <span>NPC 名字</span>
            <input name="name" defaultValue={selected.name} required />
          </label>
          <label className={styles.fieldLabel}>
            <span>职责</span>
            <input name="responsibility" defaultValue={selected.role} required />
          </label>
          <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
            <span>知识库摘要</span>
            <textarea name="knowledge_summary" defaultValue={text(selected.knowledge?.summary, "")} placeholder="这个 NPC 的长期记忆和前任交接重点。" />
          </label>
          <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
            <span>知识标签</span>
            <input name="knowledge_tags" defaultValue={asArray(selected.knowledge?.tags).map((item) => text(item)).join(", ")} placeholder="ui, validation, codex" />
          </label>
          <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
            <span>自动化模式</span>
            <label className={`${styles.checkItem} ${styles.checkItemRich}`}>
              <input type="checkbox" name="automation_enabled" value="true" defaultChecked={selected.automationEnabled} />
              <span className={styles.checkItemText}>
                <strong>开启持续自动化</strong>
                <small>关闭时：这个 NPC 只会执行当前发送的这一条指令。</small>
                <small>开启时：平台会继续维护自治桥或会话，适合持续派工。</small>
              </span>
            </label>
            <input type="hidden" name="automation_enabled" value="false" />
          </label>
          <label className={styles.fieldLabel}>
            <span>心跳间隔（秒）</span>
            <input
              name="automation_heartbeat_seconds"
              type="number"
              min="15"
              max="3600"
              step="15"
              defaultValue={selected.heartbeatIntervalSeconds}
            />
            <small>只在开启持续自动化时生效。建议阅读类任务 60-300 秒，紧急接单再调到 15-30 秒。</small>
          </label>
        </div>
        <div className={styles.noticeCard} data-npc-profile-collab-guard={selected.id}>
          <strong>AI 协作护栏</strong>
          <p className={styles.microCopy}>
            {`项目视角：${collabProjectProfileLabel(selected.collabProtocol.project_profile)} / ${collabProtocolWorkKindLabel(selected.collabProtocol.work_kind)} / ${collabProtocolApprovalLabel(selected.collabProtocol.approval_policy)}`}
          </p>
          <div className={styles.chipRow}>
            <span className={styles.miniChip}>{selected.protocolTokenSummary}</span>
            <span className={styles.miniChip}>{selected.protocolRunawaySummary}</span>
            <span className={styles.miniChip}>{selected.protocolEfficiencySummary}</span>
            <span className={styles.miniChip}>{selected.protocolDebugSummary}</span>
          </div>
          <p className={styles.microCopy}>
            关闭自动化时，平台只执行当前指令；开启自动化后才按这里的轮次、预算和人审边界持续推进。
          </p>
        </div>
        <div className={styles.noticeCard} data-npc-profile-skill-summary={selected.id}>
          <strong>当前职业 Skill 摘要</strong>
          <p className={styles.microCopy}>
            固定 Skill 仍然自动装备。这里专门列这个 NPC 当前装着的职业 Skill，方便你从用户视角快速确认它适合挂到哪些工位、通常会交什么结果。
          </p>
          {!roleSkills.length ? (
            <p className={styles.microCopy}>
              这个 NPC 还没装职业 Skill。下面先按当前职责做一张自动推测卡，等你去“装配 Skill”后，这里会切成真实 Skill 摘要。
            </p>
          ) : null}
        </div>
        <div className={styles.managerCardGrid}>
          {(roleSkills.length ? roleSkills : [fallbackRoleSkill]).map((skill) => {
            const skillId = text(skill.id, "");
            const fitStations = resolveSkillFitStations(skill);
            const deliverables = resolveSkillDeliverables(skill);
            const isFallbackRoleCard = skillId.startsWith("fallback-role-");
            return (
              <article key={`npc-profile-skill-${skillId}`} data-npc-profile-skill-card={skillId}>
                <strong>{text(skill.label, skillId)}</strong>
                <p>{shortText(resolveSkillIntro(skill), text(skill.note, "暂无说明"), 120)}</p>
                <p className={styles.microCopy}>{`适合工位：${fitStations.join(" / ") || "暂无建议工位"}`}</p>
                <p className={styles.microCopy}>{`常见交付物：${deliverables.join(" / ") || "暂无交付物"}`}</p>
                {isFallbackRoleCard ? <p className={styles.microCopy}>当前是按职责自动推测的摘要卡，装配真实 Skill 后会被真实卡片替换。</p> : null}
              </article>
            );
          })}
        </div>
        <button type="submit" data-loading-label="正在保存 NPC 属性">保存属性</button>
      </form>
    );
  }

  function renderNpcBindDrawer() {
    const selected = resolveManagedSeat(managerDrawer?.id);
    if (!selected.id) {
      return <p className={styles.microCopy}>先选择一个 NPC，再绑定电脑和线程。</p>;
    }

    return (
      <form action={updateNpcWorkstationSeat.bind(null, projectId, selected.id)} className={styles.drawerForm}>
        <input type="hidden" name="return_to" value={npcCreateReturnPath} />
        <input type="hidden" name="source_thread_catalog" value={sourceThreadCatalogJson} />
        <input type="hidden" name="name" value={selected.name} />
        <input type="hidden" name="responsibility" value={selected.role} />
        <input type="hidden" name="automation_enabled" value={selected.automationEnabled ? "true" : "false"} />
        <input type="hidden" name="automation_heartbeat_seconds" value={String(selected.heartbeatIntervalSeconds)} />
        <input type="hidden" name="scene" value="map-farm" />
        <input type="hidden" name="avatar_key" value="jack-standing" />
        {selected.additionalSkillIds.map((skillId) => (
          <input key={`bind-skill-${skillId}`} type="hidden" name="skill_loadout" value={skillId} />
        ))}
        <div className={styles.drawerFormGrid}>
          <label className={styles.fieldLabel}>
            <span>来源线程</span>
            <select name="source_workstation_id" className={styles.select} defaultValue={selected.sourceThreadId}>
              <option value="">暂不绑定线程</option>
              {allThreadCandidates.map((thread, index) => {
                const threadId = text(thread.id ?? thread.workstation_id, "");
                return (
                  <option key={`bind-thread-${threadId || index}`} value={threadId}>
                    {display(thread.name, threadId || `线程 ${index + 1}`)} / {platformProviderLabelFromThread(thread)}
                  </option>
                );
              })}
            </select>
          </label>
          <label className={styles.fieldLabel}>
            <span>电脑</span>
            <select name="computer_node_id" className={styles.select} defaultValue={selected.computerNodeId}>
              <option value="">由线程决定</option>
              {nodes.map((node) => {
                const nodeId = text(node.id, "");
                return <option key={`bind-node-${nodeId}`} value={nodeId}>{text(node.label ?? node.name, nodeId)}</option>;
              })}
            </select>
          </label>
          <label className={styles.fieldLabel}>
            <span>模型</span>
            <input name="model" defaultValue={selected.model} />
          </label>
        </div>
        <button type="submit" data-loading-label="正在绑定线程">保存绑定</button>
      </form>
    );
  }

  function renderNpcSkillsDrawer() {
    const selected = resolveManagedSeat(managerDrawer?.id);
    if (!selected.id) {
      return <p className={styles.microCopy}>先选择一个 NPC，再装配 Skill。</p>;
    }
    return (
      <form action={updateNpcWorkstationSeat.bind(null, projectId, selected.id)} className={styles.drawerForm}>
        <input type="hidden" name="return_to" value={npcCreateReturnPath} />
        <input type="hidden" name="source_thread_catalog" value={sourceThreadCatalogJson} />
        <input type="hidden" name="name" value={selected.name} />
        <input type="hidden" name="responsibility" value={selected.role} />
        <input type="hidden" name="source_workstation_id" value={selected.sourceThreadId} />
        <input type="hidden" name="computer_node_id" value={selected.computerNodeId} />
        <input type="hidden" name="model" value={selected.model} />
        <input type="hidden" name="automation_enabled" value={selected.automationEnabled ? "true" : "false"} />
        <input type="hidden" name="automation_heartbeat_seconds" value={String(selected.heartbeatIntervalSeconds)} />
        <input type="hidden" name="scene" value="map-farm" />
        <input type="hidden" name="avatar_key" value="jack-standing" />
        <div className={styles.noticeCard}>
          <strong>固定 Skill 自动装备</strong>
          <p>{baselineSkills.length ? baselineSkills.map((skill) => text(skill.label, text(skill.id))).join(" / ") : "GitHub 拉代码 / 持续协作 / 截图验证 / 交接输出"}</p>
        </div>
        {renderNpcSkillLoadoutPicker({
          selectedSkillIds: npcEditSkillLoadout,
          orderedSkills: orderedRoleSkills,
          recommendedSkillIds: suggestedRoleSkillIds,
          setSelectedSkillIds: setNpcEditSkillLoadout,
          dataPrefix: "npc-edit",
          helperText: "这个装配器会保留你已经勾选的 Skill。先筛到合适分类，再勾选，隐藏掉的已选项也不会丢。",
        })}
        <button type="submit" data-loading-label="正在保存 Skill 装配">保存 Skill 装配</button>
      </form>
    );
  }

  function renderComputerConnectDrawer() {
    return (
      <form action={createCollaborationNode.bind(null, projectId)} className={styles.drawerForm} data-computer-connect-form="true">
        <p className={styles.microCopy}>不同电脑自己决定本地路径。平台只保存项目归属、能力和接入状态，后续通过 GitHub 同步代码。</p>
        <input type="hidden" name="return_to" value={computersPanelReturnPath} />
        <input type="hidden" name="metadata" value='{"source":"user_project_workbench"}' />
        <div className={styles.drawerFormGrid}>
          <label className={styles.fieldLabel}>
            <span>电脑 ID</span>
            <input name="id" placeholder="例如：local-windows-01" />
          </label>
          <label className={styles.fieldLabel}>
            <span>显示名称</span>
            <input name="label" placeholder="例如：本机 Windows 工作站" required />
          </label>
          <label className={styles.fieldLabel}>
            <span>状态</span>
            <select name="status" className={styles.select} defaultValue="online">
              <option value="online">在线</option>
              <option value="offline">离线</option>
              <option value="pending">待确认</option>
            </select>
          </label>
          <label className={styles.fieldLabel}>
            <span>接入方式</span>
            <select name="connection_kind" className={styles.select} defaultValue="manual">
              <option value="manual">手动登记</option>
              <option value="local">本机</option>
              <option value="runner">Runner</option>
              <option value="remote">远端电脑</option>
            </select>
          </label>
          <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
            <span>工作区路径</span>
            <input name="workspace_root" placeholder="由这台电脑自己决定，例如 D:/repo 或 /home/user/repo" />
          </label>
          <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
            <span>Git 根目录</span>
            <input name="git_root" placeholder="建议填本机 clone 后的仓库路径" />
          </label>
        </div>
        <button type="submit" data-loading-label="正在登记电脑">登记电脑</button>
      </form>
    );
  }

  function renderComputerThreadsDrawer() {
    const selectedNode = resolveManagedComputer(managerDrawer?.id);
    const selectedNodeId = text(selectedNode?.id ?? selectedNode?.node_id ?? selectedNode?.name ?? selectedNode?.label, "");
    const selectedThreads = resolveManagedComputerThreads(selectedNode);
    const scan = selectedNode?.metadata?.thread_scan ?? {};
    const scanStatusLabel = formatComputerThreadScanStatus(scan.status);

    return (
      <div className={styles.drawerStack} data-computer-threads-drawer={selectedNodeId || ""}>
        <div className={styles.drawerSubject}>
          <strong>{selectedNode ? text(selectedNode.label ?? selectedNode.name, selectedNodeId) : "未选择电脑"}</strong>
          <p>{selectedThreads.length} 条线程 / Runner {text(selectedNode?.runner_id, "未绑定")}</p>
        </div>
        <div className={styles.managerActionGrid}>
          <form action={issueComputerNodePairingToken.bind(null, projectId, selectedNodeId)} data-computer-pairing-form={selectedNodeId || ""}>
            <input type="hidden" name="return_to" value={computersPanelReturnPath} />
            <button type="submit" disabled={!selectedNodeId} data-loading-label="正在生成配对令牌" data-computer-generate-pairing={selectedNodeId || ""}>生成配对令牌</button>
          </form>
          <form action={revokeComputerNodePairingToken.bind(null, projectId, selectedNodeId)}>
            <input type="hidden" name="return_to" value={computersPanelReturnPath} />
            <button type="submit" className={styles.ghostButton} disabled={!selectedNodeId} data-loading-label="正在吊销令牌" data-computer-revoke-pairing={selectedNodeId || ""}>吊销令牌</button>
          </form>
          <form action={requestComputerThreadScan.bind(null, projectId)} data-computer-thread-scan-form={selectedNodeId || ""}>
            <input type="hidden" name="computer_node_id" value={selectedNodeId} />
            <input type="hidden" name="return_to" value={computersPanelReturnPath} />
            <button type="submit" className={styles.ghostButton} disabled={!selectedNodeId} data-loading-label="正在请求扫描线程" data-computer-request-scan={selectedNodeId || ""}>扫描线程</button>
          </form>
        </div>
        {renderComputerOnboardingGuide(selectedNode, { alwaysShowScripts: true })}
        <ul className={styles.drawerConversation}>
          {selectedThreads.length ? (
            selectedThreads.map((thread, index) => {
              const threadId = text(thread.id ?? thread.workstation_id, "");
              const boundSeat = seatBySourceThreadId.get(threadId) ?? seatBySourceThreadId.get(threadId.toLowerCase()) ?? null;
              return (
                <li key={`drawer-thread-${threadId || index}`} data-computer-drawer-thread-item={threadId || `thread-${index + 1}`}>
                  <span>{platformProviderLabelFromThread(thread)}</span>
                  <strong>{display(thread.name, threadId || `线程 ${index + 1}`)}</strong>
                  <p>{boundSeat ? `已绑定 ${text(boundSeat.name, "NPC")}` : "未绑定 NPC，可回 NPC 管理器创建或绑定。"}</p>
                </li>
              );
            })
          ) : (
            <li>
              <span>空</span>
              <strong>还没有线程</strong>
              <p>{text(scan.status, "").toLowerCase() === "awaiting_runner" ? "这台电脑还没接入 runner。先运行上面的接入命令，再回来扫描线程。" : "先生成配对令牌，让对应电脑接入，再扫描线程。"}</p>
            </li>
          )}
        </ul>
        <p className={styles.microCopy}>扫描状态：{scanStatusLabel} / 最近时间：{formatStamp(scan.completed_at ?? scan.requested_at)}</p>
      </div>
    );
  }

  function renderSkillCreateDrawer() {
    return (
      <form action={createProjectSkill.bind(null, projectId)} className={styles.drawerForm}>
        <input type="hidden" name="return_to" value={skillLibraryReturnPath} />
        <div className={styles.drawerFormGrid}>
          <label className={styles.fieldLabel}>
            <span>Skill 标识</span>
            <input name="skill_id" placeholder="例如：result-relay" />
          </label>
          <label className={styles.fieldLabel}>
            <span>中文名字</span>
            <input name="label" placeholder="例如：结果回流" />
          </label>
          <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
            <span>说明</span>
            <textarea name="note" placeholder="这条 Skill 解决什么问题，适合哪些 NPC。" />
          </label>
          <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
            <span>适用关键词</span>
            <input name="recommended_for" placeholder="例如：git, review, ui, npc" />
          </label>
        </div>
        <button type="submit" data-loading-label="正在新增 Skill">新增 Skill</button>
      </form>
    );
  }

  function renderSkillGithubImportDrawer() {
    return (
      <div className={styles.drawerStack} data-skill-github-import-drawer="1">
        <div className={styles.noticeCard}>
          <strong>自由导入 GitHub Skill</strong>
          <p>
            这里不是内置清单。可以粘 GitHub repo、tree、blob 或 raw 地址；平台会扫描 SKILL.md、skill.json、skills.json
            等文件并写入当前项目 Skill 仓库；如果是普通 agent 仓库，会把分类目录下的 Markdown 角色说明转成可编辑 Skill 草稿。
          </p>
          <p className={styles.microCopy}>私有仓库和 GitHub Token 后续再接；当前先支持公开 GitHub 仓库，导入后会保留来源 repo、分支和文件路径。</p>
        </div>
        <form action={importGithubProjectSkill.bind(null, projectId)} className={styles.drawerForm}>
          <input type="hidden" name="return_to" value={skillLibraryReturnPath} />
          <div className={styles.drawerFormGrid}>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>GitHub 地址</span>
              <input
                name="github_url"
                data-skill-github-url="1"
                placeholder="https://github.com/owner/repo/tree/main/skills 或 raw/blob 文件地址"
                required
              />
            </label>
            <label className={styles.fieldLabel}>
              <span>分支 / tag</span>
              <input name="github_branch" placeholder="默认 main，可填 develop / v1.0" />
            </label>
            <label className={styles.fieldLabel}>
              <span>指定路径</span>
              <input name="github_path" placeholder="可选，例如 skills/SKILL.md" />
            </label>
            <label className={styles.fieldLabel}>
              <span>分类</span>
              <input name="category" placeholder="例如：embedded / ui / testing" defaultValue="github" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>适用关键词</span>
              <input name="recommended_for" placeholder="例如：github, robot, embedded, review" />
            </label>
          </div>
          <div className={styles.managerActionGrid}>
            <button type="submit" data-skill-import-github-submit="1" data-loading-label="正在从 GitHub 导入 Skill">
              导入到 Skill 仓库
            </button>
            <button type="button" className={styles.ghostButton} onClick={() => openManagerDrawer("skill-import")}>
              去 Agency Agents 选择导入
            </button>
          </div>
        </form>
        <div className={styles.noticeCard}>
          <strong>推荐粘贴方式</strong>
          <p className={styles.microCopy}>
            最稳：粘具体 SKILL.md / skill.json 文件。想批量：粘 repo 或 skills 目录；普通 agent 仓库会只扫描分类目录里的 Markdown，最多 40 个文件，避免误导入整个代码仓库。
          </p>
        </div>
      </div>
    );
  }

  function renderSkillImportDrawer() {
    const selectedSet = new Set(skillImportSelection.map((item) => item.toLowerCase()));
    const filteredVisible = filteredAgencySkillPack.slice(0, skillImportQuery.trim() || skillImportCategoryFilter !== "all" || skillImportStatusFilter !== "all" ? 48 : 24);
    const hiddenCount = Math.max(filteredAgencySkillPack.length - filteredVisible.length, 0);
    const selectedSkills = skillImportSelection
      .map((skillId) => agencySkillPackLibrary.find((item) => text(item.id, "").toLowerCase() === skillId.toLowerCase()))
      .filter((item): item is AnyRecord => Boolean(item));
    const filteredIds = filteredAgencySkillPack.map((skill) => text(skill.id, "")).filter(Boolean);
    const selectableFilteredIds = uniqueStrings(filteredIds);
    const missingCount = agencySkillPackLibrary.filter((skill) => !existingSkillIdSet.has(text(skill.id, "").toLowerCase())).length;
    const existingCount = agencySkillPackLibrary.length - missingCount;
    const recommendedVisibleCount = filteredAgencySkillPack.filter((skill) =>
      agencyCuratedSkillIdSet.has(text(skill.id, "").toLowerCase()),
    ).length;

    return (
      <div className={styles.drawerStack} data-skill-import-drawer="1">
        <div className={styles.noticeCard}>
          <strong>Agency Agents 选择性导入</strong>
          <p>不用再一键全量导入。先按关键词、分类和仓库状态筛，再勾选真正要进项目仓库的 Skill。</p>
          <p className={styles.microCopy}>
            包内总数 {agencySkillPackLibrary.length} 条 / 当前项目已在仓库 {existingCount} 条 / 还没导入 {missingCount} 条
          </p>
        </div>
        <div className={styles.noticeCard}>
          <strong>已选待导入</strong>
          <p className={styles.microCopy}>
            当前已选 {selectedSkills.length} 条 / 当前筛选命中 {filteredAgencySkillPack.length} 条
            {hiddenCount ? ` / 先显示前 ${filteredVisible.length} 条，剩下 ${hiddenCount} 条请继续筛` : ""}
          </p>
          <div className={styles.selectedSkillTray} data-skill-import-selected-count={String(selectedSkills.length)}>
            {selectedSkills.length ? (
              selectedSkills.map((skill) => (
                <button
                  key={`skill-import-selected-${text(skill.id, "")}`}
                  type="button"
                  className={styles.selectedSkillChip}
                  data-skill-import-selected-chip={text(skill.id, "")}
                  onClick={() => toggleSkillImportSelection(text(skill.id, ""))}
                >
                  <strong>{text(skill.label, text(skill.id, ""))}</strong>
                  <small>{resolveSkillSourceLabel(skill)} / 点此移除</small>
                </button>
              ))
            ) : (
              <p className={styles.objectRailEmpty}>还没选导入项。可以先点“推荐 16 条”或“勾选当前筛选”。</p>
            )}
          </div>
          <div className={styles.chipRow}>
            <button
              type="button"
              className={styles.miniChipButton}
              data-skill-import-select-curated="1"
              onClick={() => {
                setSkillImportSelection(agencyCuratedSkillIds);
                setSkillImportRecommendedOnly(true);
                setSkillImportQuery("");
                setSkillImportCategoryFilter("all");
                setSkillImportStatusFilter("all");
              }}
            >
              推荐 16 条
            </button>
            <button
              type="button"
              className={styles.miniChipButton}
              data-skill-import-select-filtered="1"
              onClick={() => setSkillImportSelection(selectableFilteredIds)}
            >
              勾选当前筛选
            </button>
            <button
              type="button"
              className={styles.miniChipButton}
              data-skill-import-clear-selection="1"
              onClick={() => setSkillImportSelection([])}
            >
              清空已选
            </button>
          </div>
          <div className={styles.chipRow}>
            {SKILL_IMPORT_BUNDLE_PRESETS.map((preset) => (
              <button
                key={`skill-import-bundle-${preset.id}`}
                type="button"
                className={styles.miniChipButton}
                data-skill-import-bundle={preset.id}
                onClick={() => applySkillImportBundle(preset)}
                title={preset.hint}
              >
                {preset.label} {preset.skillIds.length}
              </button>
            ))}
          </div>
        </div>
        <input
          className={styles.searchInput}
          data-skill-import-search="1"
          placeholder="搜索外部 Skill，例如：frontend / embedded / testing / game"
          value={skillImportQuery}
          onChange={(event) => setSkillImportQuery(event.target.value)}
        />
        <div className={styles.filterToolbar}>
          <span className={styles.formLabel}>仓库状态</span>
          <div className={styles.chipRow}>
            {[
              { id: "all", label: "全部" },
              { id: "missing", label: `仅未导入 ${missingCount}` },
              { id: "existing", label: `已在仓库 ${existingCount}` },
            ].map((item) => (
              <button
                key={`skill-import-status-${item.id}`}
                type="button"
                data-skill-import-status={item.id}
                className={skillImportStatusFilter === item.id ? styles.miniChipButtonActive : styles.miniChipButton}
                onClick={() => setSkillImportStatusFilter(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.filterToolbar}>
          <span className={styles.formLabel}>推荐视图</span>
          <div className={styles.chipRow}>
            <button
              type="button"
              data-skill-import-recommended-view="all"
              className={!skillImportRecommendedOnly ? styles.miniChipButtonActive : styles.miniChipButton}
              onClick={() => setSkillImportRecommendedOnly(false)}
            >
              全部 185 条
            </button>
            <button
              type="button"
              data-skill-import-recommended-view="curated"
              className={skillImportRecommendedOnly ? styles.miniChipButtonActive : styles.miniChipButton}
              onClick={() => setSkillImportRecommendedOnly(true)}
            >
              只看推荐 16 条
            </button>
          </div>
          <p className={styles.microCopy}>
            当前视图里推荐 Skill {recommendedVisibleCount} 条 / 当前是否仅看推荐：{skillImportRecommendedOnly ? "是" : "否"}
          </p>
        </div>
        <div className={styles.filterToolbar}>
          <span className={styles.formLabel}>分类过滤</span>
          <div className={styles.chipRow}>
            <button
              type="button"
              data-skill-import-category="all"
              className={skillImportCategoryFilter === "all" ? styles.miniChipButtonActive : styles.miniChipButton}
              onClick={() => setSkillImportCategoryFilter("all")}
            >
              全部分类
            </button>
            {agencySkillPackCategories.slice(0, 12).map((category) => (
              <button
                key={`skill-import-category-${category.id}`}
                type="button"
                data-skill-import-category={category.id}
                className={skillImportCategoryFilter === category.id ? styles.miniChipButtonActive : styles.miniChipButton}
                onClick={() => setSkillImportCategoryFilter(category.id)}
              >
                {category.label} {category.count}
              </button>
            ))}
          </div>
        </div>
        <form action={importAgencyAgentsSkillPack.bind(null, projectId)} className={styles.drawerForm}>
          <input type="hidden" name="return_to" value={skillLibraryReturnPath} />
          {skillImportSelection.map((skillId) => (
            <input key={`skill-import-hidden-${skillId}`} type="hidden" name="skill_id" value={skillId} />
          ))}
          <div className={styles.checkGrid} data-skill-import-visible-count={String(filteredAgencySkillPack.length)}>
            {filteredVisible.length ? (
              filteredVisible.map((skill) => {
                const skillId = text(skill.id, "");
                const imported = existingSkillIdSet.has(skillId.toLowerCase());
                const checked = selectedSet.has(skillId.toLowerCase());
                return (
                  <label
                    key={`skill-import-option-${skillId}`}
                    className={`${styles.checkItem} ${styles.checkItemRich} ${checked ? styles.checkItemSelected : ""}`}
                    data-skill-import-option={skillId}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleSkillImportSelection(skillId)}
                    />
                    <span className={styles.checkItemText}>
                      <strong>{text(skill.label, skillId)}</strong>
                      <small>
                        {displaySkillCategory(resolveSkillCategory(skill))}
                        {" / "}
                        {imported ? "已在仓库" : "未导入"}
                      </small>
                      <small>{shortText(resolveSkillIntro(skill), text(skill.note, "暂无说明"), 96)}</small>
                    </span>
                  </label>
                );
              })
            ) : (
              <p className={styles.objectRailEmpty}>当前筛选没有命中。先切回“全部”或换个关键词。</p>
            )}
          </div>
          <div className={styles.managerActionGrid}>
            <button
              type="submit"
              data-skill-import-selected-submit="1"
              data-loading-label="正在导入所选 Skill"
              disabled={!skillImportSelection.length}
            >
              导入所选 Skill
            </button>
            <button
              type="submit"
              name="import_mode"
              value="all"
              className={styles.ghostButton}
              data-skill-import-full-submit="1"
              data-loading-label="正在导入 Agency Agents 全量 Skill"
            >
              仍要全量导入
            </button>
          </div>
        </form>
      </div>
    );
  }

  function renderSkillDetailDrawer() {
    const selectedSkill = resolveManagedSkill(managerDrawer?.id);
    const skillId = text(selectedSkill?.id, "");
    if (!selectedSkill) return <p className={styles.microCopy}>还没有 Skill。</p>;
    const metadata = resolveSkillMetadata(selectedSkill);
    const sectionPreview = resolveSkillSectionPreview(selectedSkill);
    const fitStations = resolveSkillFitStations(selectedSkill);
    const deliverables = resolveSkillDeliverables(selectedSkill);
    const docPath = text(selectedSkill.doc_path ?? metadata.doc_path, "");

    return (
      <div className={styles.drawerStack}>
        <div className={styles.drawerSubject} data-skill-detail-drawer={skillId}>
          <strong>{text(selectedSkill.label, skillId)}</strong>
          <p>{isBaselineSkill(selectedSkill) ? "固定必备 Skill" : "可装配职业 Skill"} / {resolveSkillSourceLabel(selectedSkill)}</p>
        </div>
        <p className={styles.skillIntroCopy} data-skill-detail-intro={skillId}>{resolveSkillIntro(selectedSkill)}</p>
        {resolveSkillVibe(selectedSkill) ? (
          <div className={styles.noticeCard}>
            <strong>角色气质</strong>
            <p>{resolveSkillVibe(selectedSkill)}</p>
          </div>
        ) : null}
        <div className={styles.managerStatGrid}>
          <article><span>分类</span><strong>{displaySkillCategory(resolveSkillCategory(selectedSkill))}</strong></article>
          <article><span>来源</span><strong>{text(selectedSkill.source, "custom")}</strong></article>
          <article><span>适用关键词</span><strong>{asArray(selectedSkill.recommended_for).length || 0}</strong></article>
        </div>
        <div className={styles.skillSummaryGrid}>
          <article data-skill-fit-stations={skillId}>
            <strong>适合工位</strong>
            <p>{fitStations.join(" / ") || "还没有建议工位"}</p>
          </article>
          <article data-skill-deliverables={skillId}>
            <strong>常见交付物</strong>
            <p>{deliverables.join(" / ") || "还没有默认交付物"}</p>
          </article>
        </div>
        {docPath ? (
          <p className={styles.microCopy}>必读路径：{docPath}</p>
        ) : null}
        {text(metadata.external_path, "") ? (
          <p className={styles.microCopy}>来源文件：{text(metadata.external_path, "")}</p>
        ) : null}
        {asArray(selectedSkill.recommended_for).length ? (
          <p className={styles.microCopy}>适用：{asArray(selectedSkill.recommended_for).map((item) => text(item)).filter(Boolean).join(" / ")}</p>
        ) : null}
        {sectionPreview.length ? (
          <div className={styles.managerCardGrid}>
            {sectionPreview.map((section) => (
              <article key={`${skillId}-${section.label}`}>
                <strong>{section.label}</strong>
                <p>{section.items.join(" / ")}</p>
              </article>
            ))}
          </div>
        ) : null}
        {isBaselineSkill(selectedSkill) ? (
          <p className={styles.microCopy}>固定 Skill 不能从项目内删除，它会自动装到每个 NPC。</p>
        ) : (
          <form action={deleteProjectSkill.bind(null, projectId, skillId)} className={styles.inlineDangerForm}>
            <input type="hidden" name="return_to" value={skillLibraryReturnPath} />
            <button type="submit" className={styles.dangerButton} data-loading-label="正在删除 Skill">删除 Skill</button>
          </form>
        )}
      </div>
    );
  }

  function renderDevelopmentModuleDrawer() {
    const isCreateMode = managerDrawer?.id === DEVELOPMENT_STATION_CREATE_DRAWER_ID;
    const selectedStation = isCreateMode
      ? null
      : developmentWorkshopStations.find((item) => item.id === managerDrawer?.id) ?? selectedDevelopmentStation ?? null;
    const editingStation = selectedStation ?? selectedDevelopmentStation ?? null;
    if (!selectedStation && !isCreateMode && !editingStation) return <p className={styles.microCopy}>还没有开发工位。</p>;
    const formAction = isCreateMode
      ? createDevelopmentWorkshopStation.bind(null, projectId)
      : updateDevelopmentWorkshopStation.bind(null, projectId, editingStation?.id ?? "");

    return (
      <div className={styles.managerStageStack}>
        <section className={styles.drawerSubject}>
          <strong>{isCreateMode ? "新增开发工位" : `${editingStation?.icon ?? "工"} ${editingStation?.label ?? "开发工位"}`}</strong>
          <p>{isCreateMode ? "工位属于开发工坊本身，用户可以按项目需要自由定义。工位有自己的总知识库，NPC 再挂在工位下面持续执行。" : editingStation?.detail}</p>
          {editingStation ? (
            <p className={styles.microCopy}>{`地图位置：${editingStation.mapScene} / ${editingStation.mapLocation} / 知识库：${editingStation.knowledgeBase.handoffPath}`}</p>
          ) : null}
        </section>

        <form action={formAction} className={styles.drawerForm}>
          <input type="hidden" name="return_to" value={developmentWorkshopReturnPath} />
          {!isCreateMode ? <input type="hidden" name="station_id" value={editingStation?.id ?? ""} /> : null}
          <div className={styles.drawerFormGrid}>
            <label className={styles.fieldLabel}>
              <span>工位名字</span>
              <input name="label" defaultValue={editingStation?.label ?? ""} placeholder="例如：NanoPi 工位" required />
            </label>
            <label className={styles.fieldLabel}>
              <span>图标</span>
              <input name="icon" defaultValue={editingStation?.icon ?? "工"} placeholder="例如：板 / App / 工" maxLength={2} />
            </label>
            <label className={styles.fieldLabel}>
              <span>工坊位置</span>
              <input name="station" defaultValue={editingStation?.station ?? ""} placeholder="例如：开发工坊 / NanoPi 区" />
            </label>
            <label className={styles.fieldLabel}>
              <span>地图场景</span>
              <select name="map_scene" className={styles.select} defaultValue={editingStation?.mapScene ?? "map-farm"}>
                <option value="map-farm">map-farm / 外场</option>
                <option value="map-home">map-home / 主房</option>
                <option value="map-toolshed">map-toolshed / 工具棚</option>
              </select>
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>地图位置说明</span>
              <input name="map_location" defaultValue={editingStation?.mapLocation ?? ""} placeholder="例如：开发工坊东侧第二排工位" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>工位说明</span>
              <textarea name="detail" defaultValue={editingStation?.detail ?? ""} placeholder="这个工位负责什么、交付什么、和别的工位怎么协作。" />
            </label>
            <label className={styles.fieldLabel}>
              <span>风险等级</span>
              <select name="risk_level" className={styles.select} defaultValue={editingStation?.riskLevel ?? "中"}>
                <option value="低">低</option>
                <option value="中">中</option>
                <option value="高">高</option>
              </select>
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>适用模式</span>
              <input name="modes" defaultValue={editingStation?.modes.join(", ") ?? ""} placeholder="例如：2D 开发者模式, 教育模式" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>后端锚点</span>
              <input name="backend_anchor" defaultValue={editingStation?.backendAnchor ?? ""} placeholder="例如：/api/collaboration/..." />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>Runner / 电脑能力</span>
              <input name="runner_capabilities" defaultValue={editingStation?.runnerCapabilities.join(", ") ?? ""} placeholder="例如：github-clone, build-test, serial-open" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>AI 职责</span>
              <input name="ai_responsibilities" defaultValue={editingStation?.aiResponsibilities.join(", ") ?? ""} placeholder="例如：拉代码, 编译验证, 写最终回复" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>NPC 默认职责模板</span>
              <input name="npc_role_templates" defaultValue={editingStation?.npcRoleTemplates.join(", ") ?? ""} placeholder="例如：资料员, 实现员, 验收员" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>关键词</span>
              <input name="assignment_keywords" defaultValue={editingStation?.assignmentKeywords.join(", ") ?? ""} placeholder="例如：nanopi, 烧录, 板卡" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>推荐下一步</span>
              <input name="next_actions" defaultValue={editingStation?.nextActions.join(", ") ?? ""} placeholder="例如：补齐环境, 绑定 NPC, 跑 build" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>审批边界</span>
              <textarea name="approval_policy" defaultValue={editingStation?.approvalPolicy ?? ""} placeholder="写清楚哪些动作能自动推进，哪些必须人工确认。" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>工位知识库摘要</span>
              <textarea name="knowledge_summary" defaultValue={editingStation?.knowledgeBase.summary ?? ""} placeholder="这是工位自己的总知识库，不属于某个 NPC。" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>工位知识库路径</span>
              <input name="knowledge_handoff_path" defaultValue={editingStation?.knowledgeBase.handoffPath ?? ""} placeholder="例如：docs/ai-handoffs/stations/nanopi-station.md" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.fieldLabelWide}`}>
              <span>工位知识标签</span>
              <input name="knowledge_tags" defaultValue={editingStation?.knowledgeBase.tags.join(", ") ?? ""} placeholder="例如：nanopi, hardware, station" />
            </label>
          </div>
          <div className={styles.managerActionGrid}>
            <button type="submit" data-loading-label={isCreateMode ? "正在添加工位" : "正在保存工位"}>
              {isCreateMode ? "创建工位" : "保存工位"}
            </button>
          </div>
        </form>
        {!isCreateMode && editingStation ? (
          <form action={deleteDevelopmentWorkshopStation.bind(null, projectId, editingStation.id)} className={styles.inlineDangerForm}>
            <input type="hidden" name="return_to" value={developmentWorkshopReturnPath} />
            <button type="submit" className={styles.dangerButton} data-loading-label="正在删除工位">
              删除工位
            </button>
          </form>
        ) : null}
      </div>
    );
  }

  function renderManagerDrawer() {
    if (!managerDrawer) return null;
    let body = null;
    switch (managerDrawer.kind) {
      case "exchange-detail":
        body = renderExchangeDetailDrawer();
        break;
      case "npc-create":
        body = renderNpcCreateDrawer();
        break;
      case "npc-dialog":
        body = renderNpcDialogDrawer();
        break;
      case "npc-profile":
        body = renderNpcProfileDrawer();
        break;
      case "npc-bind":
        body = renderNpcBindDrawer();
        break;
      case "npc-skills":
        body = renderNpcSkillsDrawer();
        break;
      case "computer-connect":
        body = renderComputerConnectDrawer();
        break;
      case "computer-threads":
        body = renderComputerThreadsDrawer();
        break;
      case "skill-create":
        body = renderSkillCreateDrawer();
        break;
      case "skill-github-import":
        body = renderSkillGithubImportDrawer();
        break;
      case "skill-import":
        body = renderSkillImportDrawer();
        break;
      case "skill-detail":
        body = renderSkillDetailDrawer();
        break;
      case "development-module":
        body = renderDevelopmentModuleDrawer();
        break;
    }

    return (
      <aside
        className={styles.managerDrawer}
        role="dialog"
        aria-label={managerDrawerTitle(managerDrawer)}
        data-manager-drawer-kind={managerDrawer.kind}
      >
        <header className={styles.managerDrawerHead}>
          <div>
            <span>三级抽屉</span>
            <strong>{managerDrawerTitle(managerDrawer)}</strong>
          </div>
          <button type="button" onClick={closeManagerDrawer} aria-label="关闭三级抽屉">×</button>
        </header>
        <div className={styles.managerDrawerBody}>{body}</div>
      </aside>
    );
  }
  function renderPanelBody() {
    switch (panelView) {
      case "human-party":
        return renderHumanPartyPanel();
      case "computers":
        return renderComputersPanel();
      case "npc-create":
        return renderNpcPanel();
      case "machine-room":
        return renderMachineRoomPanel();
      case "git":
        return renderGitPanel();
      case "skills":
        return renderSkillsPanel();
      case "schedule":
        return renderSchedulePanel();
      case "serial-tv":
        return renderSerialTvPanel();
      case "ai-debug":
        return renderAiDebugPanel();
      case "ai-simulation":
        return renderAiSimulationPanel();
      case "development-workshop":
        return renderDevelopmentWorkshopPanel();
      case "exchange":
      default:
        return renderExchangePanel();
    }
  }

  function handleGameFrameLoad(frame: HTMLIFrameElement | null) {
    try {
      const doc = frame?.contentDocument;
      if (!doc) return;
      if (doc.getElementById("project-shell-embed-hide-overlay")) return;
      const style = doc.createElement("style");
      style.id = "project-shell-embed-hide-overlay";
      style.textContent = `
        .overlay .topbar,
        .overlay .nav-actions,
        .overlay .zones,
        .overlay .zone,
        .overlay .zone.visible,
        .overlay .legend,
        .overlay .debug,
        .overlay .hint,
        .overlay .drawer,
        .overlay .focus-summary,
        .overlay [data-legacy-project-surface] {
          display: none !important;
        }

        .overlay .entities {
          display: block !important;
        }

        .overlay .entity:not(.seat-npc),
        .overlay .entity-seat-flags,
        .overlay .entity-seat-signals,
        .overlay .entity-seat-status-strip,
        .overlay .entity-enter-prompt,
        .overlay .entity-seat-badge,
        .overlay .entity-nameplate-badge,
        .overlay .entity-nameplate-step,
        .overlay .entity-avatar-step {
          display: none !important;
        }
      `;
      doc.head.appendChild(style);
    } catch {}
  }

  const shellClassName = [styles.shell, skinPreviewEnabled ? styles.skinAAgentLab : ""].filter(Boolean).join(" ");

  return (
    <>
      <TeamNoticeToast toast={teamNoticeToast} />
      <main className={shellClassName} data-game-style-pack={skinPreviewEnabled ? "a-agent-lab" : "harvest-current"}>
      <header className={styles.topBar}>
        <div className={styles.projectMeta}>
          <span className={styles.badge}>{selectedMode?.active ? "2D 开发者模式" : `${selectedMode?.label ?? "未来模式"}`}</span>
          <strong>{projectName}</strong>
          <small>{recommendedAction}</small>
          {selectedMode ? (
            <div className={styles.modeDock}>
              <div className={styles.modeDockSummary}>
                <div className={styles.modeDockCopy}>
                  <small className={styles.modeDockEyebrow}>当前模式</small>
                  <strong>{selectedMode.label}</strong>
                  <p>{selectedMode.detail}</p>
                  {selectedModeDockMeta ? <small className={styles.modeDockMeta}>{selectedModeDockMeta}</small> : null}
                </div>
                <div className={styles.modeDockActions}>
                  <span className={selectedMode.active ? styles.modePlannerStateActive : styles.modePlannerState}>
                    {selectedMode.state}
                  </span>
                  <Link
                    href={selectedModeEntryPath}
                    className={styles.modeToggleButton}
                    title="打开当前选中模式的直达入口"
                  >
                    打开当前模式直达页
                  </Link>
                  {selectedModeDockShellHref ? (
                    <Link
                      href={selectedModeDockShellHref}
                      className={styles.modeToggleButton}
                      title="打开当前选中模式的下游占位壳"
                    >
                      打开当前模式占位壳
                    </Link>
                  ) : null}
                  <Link
                    href={selectedModeBoardPath}
                    className={styles.modeToggleButton}
                    title="查看当前项目的模式分流板"
                  >
                    查看当前项目分流板
                  </Link>
                  <button
                    type="button"
                    className={styles.modeToggleButton}
                    aria-expanded={modePlannerOpen}
                    onClick={() => setModePlannerOpen((value) => !value)}
                  >
                    {modePlannerOpen ? "收起四模式规划" : "查看四模式规划"}
                  </button>
                </div>
              </div>
              <div className={styles.chipRow}>
                {selectedMode.signals.map((signal) => (
                  <span key={`${selectedMode.id}-${signal}`} className={styles.miniChip}>
                    {signal}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          {selectedMode && modePlannerOpen ? (
            <div className={styles.modePlannerSheet}>
              <div className={styles.modeRail} data-mode-entry={selectedMode.id}>
                {modeEntries.map((mode) => (
                  <Link
                    key={mode.id}
                    href={buildCurrentProjectEntryPath(mode.id)}
                    className={[
                      styles.modeChipButton,
                      mode.active ? styles.modeChipActive : styles.modeChip,
                      selectedMode?.id === mode.id ? styles.modeChipSelected : "",
                    ].join(" ").trim()}
                    data-mode-card={mode.id}
                    aria-current={selectedMode?.id === mode.id ? "page" : undefined}
                    title={`切换到 ${mode.label} 的直达入口`}
                  >
                    <strong>{mode.label}</strong>
                    <span>{mode.state}</span>
                    <small>{mode.detail}</small>
                  </Link>
                ))}
              </div>
              <div className={styles.modePlanner} data-mode-focus={selectedMode.id}>
              <div className={styles.modePlannerHead}>
                <div>
                  <small className={styles.modePlannerEyebrow}>四模式入口规划</small>
                  <strong>{selectedMode.label}</strong>
                </div>
                <span className={selectedMode.active ? styles.modePlannerStateActive : styles.modePlannerState}>
                  {selectedMode.state}
                </span>
              </div>
              <p className={styles.modePlannerSummary}>{selectedMode.detail}</p>
              <div className={styles.chipRow}>
                {selectedMode.signals.map((signal) => (
                  <span key={`${selectedMode.id}-${signal}`} className={styles.miniChip}>
                    {signal}
                  </span>
                ))}
              </div>
              <div className={styles.modePlannerRule}>
                <span>{selectedMode.routeRuleLabel}</span>
                <strong>{selectedMode.routeRuleDetail}</strong>
              </div>
              <div className={styles.modePlannerRoute}>
                <strong className={styles.modePlannerSectionTitle}>前置入口链</strong>
                <div className={styles.modePlannerLegend}>
                  {selectedModeLayerKinds.map((kind) => (
                    <span key={`${selectedMode.id}-${kind}`} className={styles.modePlannerLegendChip}>
                      {kind}
                    </span>
                  ))}
                </div>
                <p className={styles.modePlannerLegendNote}>
                  先看 URL 路由层，再看当前项目页入口壳，最后才是壳里的 live 模式层。未来模式继续沿用同一条前门链，只在
                  {" "}
                  <code>{selectedModeBoardPath}</code>
                  {" "}
                  这张当前项目分流板之后展开；而今天的 live 2D 路径默认仍直接进入当前项目页入口壳。
                </p>
                <div className={styles.modePlannerLegendSummary}>
                  {selectedMode ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      总层数：{selectedMode.entrySteps.length}
                    </span>
                  ) : null}
                  {selectedModeStructureSummary ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      入口结构：{selectedModeStructureSummary}
                    </span>
                  ) : null}
                  {selectedModeSegmentStructureSummary ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      分段结构：{selectedModeSegmentStructureSummary}
                    </span>
                  ) : null}
                  {selectedModeLayerKindSummary ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      层级公式：{selectedModeLayerKindSummary}
                    </span>
                  ) : null}
                  {selectedModeSharedFrontDoor ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      共享前门 {selectedModeSharedFrontDoorHints.size} 层：{selectedModeSharedFrontDoor}
                    </span>
                  ) : null}
                  {selectedModeSharedFrontDoorLabelPath ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      前门层次：{selectedModeSharedFrontDoorLabelPath}
                    </span>
                  ) : null}
                  {selectedModeSharedFrontDoorEnd ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      共享前门止于：第 {selectedModeSharedFrontDoorSteps.length} 层 {selectedModeSharedFrontDoorEnd.label}
                    </span>
                  ) : null}
                  {selectedModeBranchStart ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      分叉起点：第 {selectedModeBranchStartIndex + 1} 层 {selectedModeBranchStart.label}，后续 {selectedModeDivergenceLayers} 层
                    </span>
                  ) : null}
                  {selectedModeDivergencePath ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      模式尾段：{selectedModeDivergencePath}
                    </span>
                  ) : null}
                  {selectedModeDivergenceLabelPath ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      尾段层次：{selectedModeDivergenceLabelPath}
                    </span>
                  ) : null}
                  {selectedModeFinalStep ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      {selectedMode.active ? "当前落点" : "计划落点"}：第 {selectedMode.entrySteps.length} 层 {selectedModeFinalStep.label}
                    </span>
                  ) : null}
                  {selectedModeCheckpointPath ? (
                    <span className={styles.modePlannerLegendSummaryChip}>
                      检查点链：{selectedModeCheckpointPath}
                    </span>
                  ) : null}
                </div>
                <div className={styles.modePlannerEntryGrid}>
                  {selectedMode.entrySteps.map((step, index) => {
                    const isSharedFrontDoorStep = selectedModeSharedFrontDoorHints.has(step.routeHint);
                    const sharedSegmentIndex = isSharedFrontDoorStep ? index + 1 : null;
                    const divergenceSegmentIndex =
                      !isSharedFrontDoorStep && selectedModeBranchStartIndex >= 0
                        ? index - selectedModeBranchStartIndex + 1
                        : null;

                    return (
                      <article key={`${selectedMode.id}-${step.label}`} className={styles.modePlannerEntryStep}>
                        <div className={styles.modePlannerEntryHeader}>
                          <span className={styles.modePlannerEntryLevel}>第 {index + 1} 层</span>
                          <span className={styles.modePlannerLayerStatus}>{step.status}</span>
                        </div>
                        {step.href ? (
                          <Link href={step.href} className={styles.modePlannerEntryLink}>
                            {step.label}
                          </Link>
                        ) : (
                          <strong>{step.label}</strong>
                        )}
                        <span className={styles.modePlannerEntryBranch}>{step.branchState}</span>
                        <span className={styles.modePlannerEntryKind}>{step.layerKind}</span>
                        <div className={styles.modePlannerEntryFlags}>
                          {sharedSegmentIndex ? (
                            <span className={styles.modePlannerEntryFlag}>
                              共享段 {sharedSegmentIndex}/{selectedModeSharedFrontDoorHints.size}
                            </span>
                          ) : null}
                          {selectedModeSharedFrontDoorEnd?.label === step.label &&
                          selectedModeSharedFrontDoorEnd?.routeHint === step.routeHint ? (
                            <span className={styles.modePlannerEntryFlagAccent}>共享前门终点</span>
                          ) : null}
                          {divergenceSegmentIndex ? (
                            <span className={styles.modePlannerEntryFlag}>
                              分叉段 {divergenceSegmentIndex}/{selectedModeDivergenceLayers}
                            </span>
                          ) : null}
                          {index === selectedMode.entrySteps.length - 1 ? (
                            <span className={styles.modePlannerEntryFlagAccent}>
                              {selectedMode.active ? "当前模式落点" : "计划模式落点"}
                            </span>
                          ) : null}
                          {selectedModeBranchStart?.label === step.label && selectedModeBranchStart?.routeHint === step.routeHint ? (
                            <span className={styles.modePlannerEntryFlagAccent}>模式差异起点</span>
                          ) : null}
                        </div>
                        <small className={styles.modePlannerEntryPath}>{step.routeHint}</small>
                        <p>{step.detail}</p>
                        {index < selectedMode.entrySteps.length - 1 ? (
                          <small className={styles.modePlannerEntryArrow}>进入下一层</small>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              </div>
              <div className={styles.modePlannerRoute}>
                <strong className={styles.modePlannerSectionTitle}>
                  {selectedMode.active ? "当前可走路径" : "计划中的模式层次"}
                </strong>
                <div className={styles.modePlannerRouteGrid}>
                  {selectedMode.layers.map((layer) => (
                    <article key={`${selectedMode.id}-${layer.label}`} className={styles.modePlannerLayer}>
                      <span className={styles.modePlannerLayerStatus}>{layer.status}</span>
                      <strong>{layer.label}</strong>
                      <p>{layer.detail}</p>
                    </article>
                  ))}
                </div>
              </div>
              <div className={styles.modePlannerGrid}>
                <article className={styles.modePlannerCard}>
                  <span>当前定位</span>
                  <strong>{selectedMode.readinessLabel}</strong>
                  <p>{selectedMode.readinessDetail}</p>
                </article>
                <article className={styles.modePlannerCard}>
                  <span>当前缺口</span>
                  <strong>{selectedMode.blockerLabel}</strong>
                  <p>{selectedMode.blockerDetail}</p>
                </article>
                <article className={styles.modePlannerCard}>
                  <span>下一步</span>
                  <strong>{selectedMode.nextLabel}</strong>
                  <p>{selectedMode.nextDetail}</p>
                </article>
              </div>
              {selectedMode.actions.length ? (
                <div className={styles.modePlannerActions}>
                  {selectedMode.actions.map((action) =>
                    action.href ? (
                      <Link
                        key={`${selectedMode.id}-${action.label}`}
                        href={action.href}
                        className={action.emphasis === "ghost" ? `${styles.inlineActionLink} ${styles.ghostButton}` : styles.inlineActionLink}
                      >
                        {action.label}
                      </Link>
                    ) : (
                      <button
                        key={`${selectedMode.id}-${action.label}`}
                        type="button"
                        className={action.emphasis === "ghost" ? styles.ghostButton : undefined}
                        onClick={() => {
                          if (!action.panel) return;
                          openStarterPanel(action.panel, action.seatId);
                        }}
                      >
                        {action.label}
                      </button>
                    ),
                  )}
                </div>
              ) : (
                <p className={styles.modePlannerFootnote}>
                  当前只是查看规划，页面底座仍固定在 2D 开发者模式农场，不会切走当前主线。
                  {" "}
                  <Link href={selectedModeBoardPath} className={styles.inlineActionLink}>
                    打开当前项目分流板
                  </Link>
                  ，对照真实的后置分流层。
                </p>
              )}
            </div>
            </div>
          ) : null}
          <span className={styles.inlineMapLink}>已锁定：AI 合作平台项目入口</span>
          {skinPreviewEnabled ? <span className={styles.stylePackNotice}>试验皮肤：A Agent Lab，只预览 UI 壳层</span> : null}
        </div>

        <div className={styles.actions}>
          {selectedMode && !selectedMode.active ? (
            <Link href={selectedModeBoardPath}>回当前项目分流板</Link>
          ) : null}
          {selectedMode && !selectedMode.active ? (
            <Link href={selectedModeEntryPath}>打开当前模式直达页</Link>
          ) : null}
          {selectedModeDockShellHref ? (
            <Link href={selectedModeDockShellHref}>打开当前模式占位壳</Link>
          ) : null}
          <button type="button" className={styles.panelButton} onClick={toggleSkinPreview}>
            {skinPreviewEnabled ? "关闭试验皮肤" : "预览试验皮肤"}
          </button>
          <Link href="/projects">项目列表</Link>
        </div>
      </header>

      <section className={styles.frameWrap}>
        <div className={styles.mapStage}>
          <iframe
            ref={gameFrameRef}
            className={styles.gameFrame}
            src={embeddedMapSrc}
            title={`${projectName} 农场地图`}
            onLoad={(event) => handleGameFrameLoad(event.currentTarget)}
          />

          <button
            type="button"
            className={styles.focusRailToggle}
            aria-expanded={focusRailOpen}
            onClick={() => setFocusRailOpen((value) => !value)}
          >
            {focusRailOpen ? "隐藏协作焦点" : "显示协作焦点"}
          </button>

          {runnerQueueAttention ? (
            <button
              type="button"
              className={styles.runnerQueueAlert}
              data-runner-queue-alert="true"
              data-runner-queue-count={String(queuedCollaborationCommandCount)}
              data-runner-watch-ready-count={String(watchReadyNodes.length)}
              data-runner-watch-blocked-count={String(watchBlockedNodes.length)}
              data-runner-queue-hard-blocker={runnerQueueBlocker ? "true" : "false"}
              onClick={() => openBackpackPanel("computers")}
            >
              {runnerQueueBlocker
                ? `接单阻塞：${queuedCollaborationCommandCount} 条指令排队，0 台电脑常驻接单`
                : `接单提醒：${queuedCollaborationCommandCount} 条指令排队，${watchBlockedNodes.length} 台电脑未接单`}
            </button>
          ) : null}

          {!panelOpen ? (
            <section className={styles.mainControlDeck} aria-label="平台主控入口">
              <div className={styles.mainControlHead}>
                <div>
                  <span>平台主控</span>
                  <strong>接电脑、管 NPC、派任务都从这里进</strong>
                </div>
                <small>{`${watchReadyNodes.length}/${nodes.length} 台接单 · ${realThreadCount} 条线程 · ${queuedCollaborationCommandCount} 条排队`}</small>
              </div>
              <div className={styles.mainControlGrid}>
                {mainControlPanels.map((item) => (
                  <button
                    key={`main-control-${item.id}`}
                    type="button"
                    className={styles.mainControlButton}
                    data-main-control={item.id}
                    onClick={() => {
                      setPendingActionLabel(null);
                      if (item.id === "human-party") {
                        openHumanPartyPanel(currentHumanPartyPlayer?.id ?? humanPartyHud[0]?.id ?? "");
                        return;
                      }
                      openBackpackPanel(item.id);
                    }}
                  >
                    <span className={styles.mainControlIcon}>{item.icon}</span>
                    <strong>{item.label}</strong>
                    <small>{item.detail}</small>
                  </button>
                ))}
              </div>
            </section>
          ) : null}

          {focusRailOpen ? (
            <div className={styles.focusRail} aria-label="当前协作焦点">
              {summaryCards.map((card, index) => (
                <article key={card.id} className={styles.focusCard} data-focus-index={index + 1}>
                  <span>{card.title}</span>
                  <strong>{card.body}</strong>
                  <p>{card.meta}</p>
                </article>
              ))}
            </div>
          ) : null}

          {humanPartyHud.length ? (
            <aside
              className={`${styles.partyHud} ${styles.partyHudLauncher}`}
              data-human-party-hud="true"
              data-human-party-expanded="false"
              data-human-project-online-count={String(projectPresentHumanPartyCount)}
              data-human-account-online-count={String(loggedInHumanPartyCount)}
            >
              <div className={styles.partyHudHead}>
                <div>
                  <span className={styles.badge}>项目主角</span>
                  <strong data-human-party-count={String(humanPartyHud.length)}>
                    {`${projectPresentHumanPartyCount}/${humanPartyHud.length} 项目在线 / ${nodes.length} 电脑 / ${realThreadCount} 线程`}
                  </strong>
                  {currentHumanPartyPlayer ? (
                    <p className={styles.partyHudCompactCopy} data-human-party-current-summary={currentHumanPartyPlayer.id}>
                      {`当前 ${currentHumanPartyPlayer.name} · ${currentHumanPartyPlayer.projectPresenceLabel} · ${currentHumanPartyPlayer.stateLabel}`}
                    </p>
                  ) : null}
                </div>
                <div className={styles.partyHudHeadActions}>
                  <small data-human-party-shared-task-count={String(sharedTaskSnapshot.count)}>
                    {`${connectedHumanPartyCount} 已接入 / ${threadedHumanPartyCount} 可协作 / 账号 ${loggedInHumanPartyCount}/${humanPartyHud.length}`}
                  </small>
                </div>
              </div>
              <div className={styles.partyHudCollapsedBody}>
                <div className={styles.partyHudCompactStats}>
                  <span className={styles.partyHudTagIdle}>{currentPlayerViewLabel}</span>
                  <span className={styles.partyHudTagIdle}>{`${projectPresentHumanPartyCount} 个项目内在线`}</span>
                  <span className={styles.partyHudTagIdle}>{`${sharedTaskSnapshot.count} 条共享任务`}</span>
                </div>
                <div className={styles.partyHudActions}>
                  <Link
                    href={buildPanelSurfaceHref("human-party", {
                      human_party: currentHumanPartyPlayer?.id ?? humanPartyHud[0]?.id ?? undefined,
                    })}
                    className={styles.ghostButton}
                    data-human-party-open-manager="true"
                    onClick={(event) => {
                      event.preventDefault();
                      openHumanPartyPanel(currentHumanPartyPlayer?.id ?? humanPartyHud[0]?.id ?? "");
                    }}
                  >
                    主角管理
                  </Link>
                  {currentHumanPartyPlayer ? (
                    <Link
                      href={buildExchangeSurfaceHref("dispatch")}
                      className={`${styles.inlineActionLink} ${styles.ghostButton}`}
                      data-human-party-open-exchange={currentHumanPartyPlayer.id}
                      onClick={(event) => {
                        event.preventDefault();
                        openExchangePanel("dispatch", null);
                      }}
                    >
                      协作现场
                    </Link>
                  ) : null}
                </div>
              </div>
            </aside>
          ) : null}

          <div className={styles.hudStrip}>
            <div className={styles.statChip}>
              <span>AI</span>
              <strong>{codexSeats.length}</strong>
            </div>
            <div className={styles.statChip}>
              <span>接单</span>
              <strong>{watchReadyNodes.length}/{nodes.length}</strong>
            </div>
            <div className={styles.statChip}>
              <span>主角</span>
              <strong>{humanPartyHud.length}</strong>
            </div>
            <div className={styles.statChip}>
              <span>玩法</span>
              <strong>{starterDrawer.statusLabel}</strong>
            </div>
          </div>

          <div className={styles.mapPrompt}>靠近粉色点后按 Enter</div>

          <div className={styles.mapBottomTip}>
            方向键移动。靠近 NPC 可交互；也可以先打开 NPC 管理查看对话、任务、Skill 和知识库。
          </div>

          {starterDrawerOpen ? (
            <aside className={styles.starterDrawer} data-guide="starter-drawer">
              <div className={styles.starterDrawerHead}>
                <div>
                  <span className={styles.badge}>新手任务</span>
                  <strong>{starterDrawer.title}</strong>
                </div>
                <button
                  type="button"
                  className={styles.starterDismiss}
                  onClick={() => setStarterDrawerOpen(false)}
                  aria-label="收起新手任务抽屉"
                >
                  ×
                </button>
              </div>
              <p className={styles.starterSummary}>{starterDrawer.summary}</p>
              <p className={styles.starterHint}>{starterDrawer.hint}</p>
              <div className={styles.starterActions}>
                {starterDrawer.ctaHref ? (
                  <Link href={starterDrawer.ctaHref} className={styles.inlineActionLink}>
                    {starterDrawer.ctaLabel}
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={() => openStarterPanel(starterDrawer.ctaPanel, starterDrawer.ctaSeatId)}
                  >
                    {starterDrawer.ctaLabel}
                  </button>
                )}
                {starterDrawer.secondaryHref ? (
                  <Link href={starterDrawer.secondaryHref} className={`${styles.inlineActionLink} ${styles.ghostButton}`}>
                    {starterDrawer.secondaryLabel}
                  </Link>
                ) : (
                  <button
                    type="button"
                    className={styles.ghostButton}
                    onClick={() => openStarterPanel(starterDrawer.secondaryPanel, starterDrawer.secondarySeatId)}
                  >
                    {starterDrawer.secondaryLabel}
                  </button>
                )}
              </div>
              <div className={styles.starterStepList}>
                {starterDrawer.steps.map((step, index) => (
                  <div key={step.id} className={styles.starterStep}>
                    <span className={step.done ? styles.starterStepDone : styles.starterStepIndex}>{index + 1}</span>
                    <div>
                      <strong>{step.title}</strong>
                      <p>{step.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </aside>
          ) : (
            <button
              type="button"
              className={styles.starterHandle}
              onClick={() => setStarterDrawerOpen(true)}
            >
              新手任务
            </button>
          )}

          {!panelOpen ? (
            <div className={styles.gameDock} aria-label="一级管理入口">
              {PANEL_DEFINITIONS.filter((item) => item.layer === "primary").map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={styles.inventoryButton}
                  data-panel-launcher={item.id}
                  onClick={() => {
                    setPendingActionLabel(null);
                    if (item.id === "human-party") {
                      openHumanPartyPanel(currentHumanPartyPlayer?.id ?? humanPartyHud[0]?.id ?? "");
                      return;
                    }
                    openBackpackPanel(item.id);
                  }}
                >
                  <span className={styles.inventoryIcon}>{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>

        {panelOpen ? (
          <aside
            className={styles.panel}
            id="project-main-panel"
            data-busy={pendingActionLabel ? "true" : "false"}
            onSubmit={handlePanelSubmit}
          >
            <div className={styles.panelHead}>
              <div>
                <span className={styles.badge}>AI 协作管理器</span>
                <h2>{activePanelDefinition.label}</h2>
                <p>{activePanelDefinition.detail}</p>
              </div>
              <button type="button" className={styles.closeButton} onClick={closeBackpackPanel}>×</button>
            </div>

            <div className={styles.panelActionsRow}>
              <Link href="/projects">项目列表</Link>
              <button type="button" onClick={() => openBackpackPanel("ai-debug")}>AI 调试</button>
              <button type="button" onClick={() => openBackpackPanel("ai-simulation")}>AI 仿真</button>
              {managerDrawer ? <button type="button" onClick={closeManagerDrawer}>关闭三级抽屉</button> : null}
            </div>

            {props.teamNotice ? (
              <div className={styles.successBanner}>{props.teamNotice}</div>
            ) : null}
            {props.teamError ? (
              <div className={styles.errorBanner}>{props.teamError}</div>
            ) : null}

            <div className={styles.backpackLayout}>
              <aside className={styles.backpackLeft} aria-label="二级对象列表">
                <div className={styles.backpackListHead}>
                  <span>二级对象栏</span>
                  <strong>{activePanelDefinition.label}</strong>
                </div>
                <div className={styles.objectRail}>
                  {panelView === "development-workshop" ? (
                    <>
                      <div className={styles.objectRailHead}>
                        <strong>工位栏</strong>
                        <span>{`${developmentWorkshopStations.length} 个`}</span>
                      </div>
                      {developmentWorkshopStations.map((item) => (
                        <button
                          key={`dev-station-rail-${item.id}`}
                          type="button"
                          className={developmentFocusId === item.id ? styles.objectRailActive : styles.objectRailItem}
                          onClick={() => {
                            setPendingActionLabel(null);
                            setManagerDrawer(null);
                            setDevelopmentFocusId(item.id);
                          }}
                        >
                          <span className={styles.objectAvatar}>{item.icon}</span>
                          <strong>{item.label}</strong>
                          <small>{item.station}</small>
                        </button>
                      ))}
                      <button
                        type="button"
                        className={styles.objectRailAdd}
                        onClick={() => {
                          setPendingActionLabel(null);
                          openManagerDrawer("development-module", DEVELOPMENT_STATION_CREATE_DRAWER_ID);
                        }}
                      >
                        <span className={styles.objectAvatar}>+</span>
                        <strong>添加工位</strong>
                      </button>
                    </>
                  ) : panelView === "npc-create" ? (
                    <>
                      <div className={styles.objectRailHead}>
                        <strong>NPC 精灵栏</strong>
                        <span>{`${mapSeatPayload.length} 个`}</span>
                      </div>
                      {mapSeatPayload.length ? (
                        mapSeatPayload.slice(0, 6).map((seat, index) => (
                          <Link
                            key={`npc-rail-${seat.id}`}
                            href={buildNpcSeatSurfaceHref(text(seat.id, ""))}
                            data-npc-rail-seat={seat.id}
                            data-npc-rail-name={seat.name}
                            className={seatMatchesFocus({ id: seat.id }, seat, seatFocusId) ? styles.objectRailActive : styles.objectRailItem}
                            onClick={() => {
                              setPendingActionLabel(null);
                              setManagerDrawer(null);
                              setPanelView("npc-create");
                              setNpcCreateSubview("seats");
                              focusSeatOnEmbeddedMap(seat.id);
                              setSeatFocusId(text(seat.id || seat.name, ""));
                            }}
                          >
                            <span
                              className={styles.objectAvatar}
                              data-poster-npc-avatar="true"
                              style={{ backgroundImage: `url("${posterNpcAvatarForSeat(seat, index)}")` }}
                              aria-hidden="true"
                            />
                            <strong>{seat.name}</strong>
                            <small>{seat.role || seat.status}</small>
                          </Link>
                        ))
                      ) : (
                        <p className={styles.objectRailEmpty}>还没有 NPC。先点下面的 + 创建一个长期席位。</p>
                      )}
                      <button
                        type="button"
                        className={styles.objectRailAdd}
                        data-npc-open-create="1"
                        onClick={() => {
                          setPendingActionLabel(null);
                          setPanelView("npc-create");
                          openManagerDrawer("npc-create");
                        }}
                      >
                        <span>+</span>
                        添加 NPC
                      </button>
                    </>
                  ) : panelView === "human-party" ? (
                    <>
                      <div className={styles.objectRailHead}>
                        <strong>主角栏</strong>
                        <span>{`${humanPartyHud.length} 个`}</span>
                      </div>
                      {humanPartyHud.length ? (
                        humanPartyHud.map((player) => (
                          <button
                            key={`human-party-rail-${player.id}`}
                            type="button"
                            data-human-party-rail-item={player.id}
                            data-human-party-rail-name={player.name}
                            data-human-presence-state={player.projectPresenceState}
                            data-human-account-state={player.accountPresenceState}
                            className={
                              text(selectedHumanPartyPlayer?.id, "").toLowerCase() === player.id.toLowerCase()
                                ? styles.objectRailActive
                                : styles.objectRailItem
                            }
                            onClick={() => {
                              setPendingActionLabel(null);
                              setManagerDrawer(null);
                              setHumanPartyFocusId(player.id);
                            }}
                          >
                            <span className={styles.objectAvatar}>主</span>
                            <strong>{player.name}</strong>
                            <small>
                              {`${player.projectPresenceLabel} / ${player.stateLabel} / Runner 心跳 ${player.onlineComputerCount}/${player.computerCount} 台 / ${player.threadCount} 条线程`}
                            </small>
                          </button>
                        ))
                      ) : (
                        <p className={styles.objectRailEmpty}>当前项目还没有成员主角。先邀请协作者，让对方进入项目。</p>
                      )}
                    </>
                  ) : panelView === "computers" ? (
                    <>
                      <div className={styles.objectRailHead}>
                        <strong>电脑栏</strong>
                        <span>{`${nodes.length} 台`}</span>
                      </div>
                      {nodes.length ? (
                        sortedByUpdatedAt(nodes).slice(0, 8).map((node, index) => {
                          const nodeId = text(node.id ?? node.node_id ?? node.name, `computer-${index + 1}`);
                          return (
                            <button
                              key={`computer-rail-${nodeId}`}
                              type="button"
                              className={text(computerFocusId, "").toLowerCase() === nodeId.toLowerCase() ? styles.objectRailActive : styles.objectRailItem}
                              data-computer-rail-item={nodeId}
                              data-computer-rail-name={display(node.name ?? node.label, nodeId)}
                              data-computer-rail-owner={resolveComputerOwnerLabel(
                                node,
                                humanPartyHud.length === 1
                                  ? currentHumanPartyPlayer?.name || humanPartyHud[0]?.ownership || "当前主角"
                                  : "",
                              )}
                              onClick={() => {
                                setPendingActionLabel(null);
                                setManagerDrawer(null);
                                setComputerFocusId(nodeId);
                              }}
                            >
                              <span className={styles.objectAvatar}>电</span>
                              <strong>{display(node.name ?? node.label, nodeId)}</strong>
                              <small>{`${resolveComputerOwnerLabel(
                                node,
                                humanPartyHud.length === 1
                                  ? currentHumanPartyPlayer?.name || humanPartyHud[0]?.ownership || "当前主角"
                                  : "",
                              )} / ${computerRegistrationLabel(node)} / ${runnerWatchInfo(node).label}${
                                isCurrentComputerOwner(
                                  node,
                                  props.currentUser as AnyRecord | null | undefined,
                                  humanPartyHud.length === 1,
                                )
                                  ? " / 当前账号"
                                  : ""
                              }`}</small>
                            </button>
                          );
                        })
                      ) : (
                        <p className={styles.objectRailEmpty}>还没有电脑。点击下面的 + 添加电脑。</p>
                      )}
                      <button type="button" className={styles.objectRailAdd} onClick={() => openManagerDrawer("computer-connect")} data-computer-rail-add="true">
                        <span>+</span>
                        添加电脑
                      </button>
                    </>
                  ) : panelView === "skills" ? (
                    <>
                      <div className={styles.objectRailHead}>
                        <strong>Skill 栏</strong>
                        <span>{`${filteredSkills.length} / ${skillLibrary.length} 条`}</span>
                      </div>
                      {filteredSkills.slice(0, 12).map((skill) => {
                        const skillId = text(skill.id, "");
                        const label = text(skill.label, skillId);
                        return (
                          <button
                            key={`skill-rail-${skillId}`}
                            type="button"
                            data-skill-rail-item={skillId}
                            className={text(skillFocusId, "").toLowerCase() === skillId.toLowerCase() ? styles.objectRailActive : styles.objectRailItem}
                            onClick={() => {
                              setPendingActionLabel(null);
                              setManagerDrawer(null);
                              setPanelView("skills");
                              setSkillFocusId(skillId);
                            }}
                          >
                            <span className={styles.objectAvatar}>技</span>
                            <strong>{label}</strong>
                            <small>{isBaselineSkill(skill) ? "固定必备" : resolveSkillSourceLabel(skill)}</small>
                          </button>
                        );
                      })}
                      <button type="button" className={styles.objectRailAdd} onClick={() => openManagerDrawer("skill-create")}>
                        <span>+</span>
                        添加 Skill
                      </button>
                    </>
                  ) : panelView === "exchange" ? (
                    <>
                      <div className={styles.objectRailHead}>
                        <strong>协作分区栏</strong>
                        <span>{`${exchangeSectionNavItems.length} 个`}</span>
                      </div>
                      {exchangeSectionNavItems.map((item) => (
                        <Link
                          key={`exchange-rail-${item.id}`}
                          href={buildExchangeSurfaceHref(item.id)}
                          className={exchangeSectionFocusId === item.id ? styles.objectRailActive : styles.objectRailItem}
                          data-exchange-nav-target={item.id}
                          data-exchange-nav-active={exchangeSectionFocusId === item.id ? "true" : undefined}
                        >
                          <span className={styles.objectAvatar}>{item.icon}</span>
                          <strong>{item.label}</strong>
                          <small>{item.railDetail}</small>
                        </Link>
                      ))}
                    </>
                  ) : (
                    <div className={styles.objectRailHint}>
                      <strong>{activePanelDefinition.label}</strong>
                      <p>{activePanelDefinition.detail}</p>
                    </div>
                  )}
                </div>
              </aside>

              <section className={styles.backpackCenter} aria-label="二级管理器">
                <div className={styles.panelBody}>
                  <div className={styles.panelBodyHead}>
                    <span>二级工作台</span>
                    <strong>{panelView === "exchange" ? currentExchangeSectionMeta.label : activePanelDefinition.label}</strong>
                    <p>
                      {panelView === "exchange"
                        ? `${currentExchangeSectionMeta.railDetail}。三级内容只从按钮打开右侧抽屉，不再堆在二级页面。`
                        : `${activePanelDefinition.detail} 三级内容只从按钮打开右侧抽屉，不再堆在二级页面。`}
                    </p>
                  </div>
                  {renderPanelBody()}
                </div>
              </section>
            </div>
            {renderManagerDrawer()}
            {pendingActionLabel ? (
              <div className={styles.pendingOverlay} role="status" aria-live="polite">
                <span className={styles.pendingSpinner} />
                <strong>{pendingActionLabel}</strong>
                <p>正在提交到平台，请稍等，不要重复点击。若动作已经完成但页面没有自动刷新，18 秒内会自动解除，也可以手动关闭提示查看当前结果。</p>
                <button type="button" className={styles.pendingDismissButton} onClick={() => setPendingActionLabel(null)}>
                  关闭提示，查看结果
                </button>
              </div>
            ) : null}
          </aside>
        ) : null}
      </section>
    </main>
    </>
  );
}




