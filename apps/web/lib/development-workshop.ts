export type DevelopmentWorkshopRiskLevel = "低" | "中" | "高";

export type DevelopmentWorkshopKnowledgeBase = {
  summary: string;
  handoffPath: string;
  tags: string[];
};

export type DevelopmentWorkshopStation = {
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
  riskLevel: DevelopmentWorkshopRiskLevel;
  assignedNpcIds: string[];
  knowledgeBase: DevelopmentWorkshopKnowledgeBase;
};

const DEFAULT_APPROVAL_POLICY = "默认按项目规则执行；涉及真实设备、花钱、删除、发布动作时转人工确认。";
const DEFAULT_DETAIL = "这是一个由项目自己定义的开发工位，用来承接特定职责、NPC 和交付边界。";
const DEFAULT_STATION = "开发工坊 / 待定位";
const DEFAULT_MAP_SCENE = "map-farm";
const DEFAULT_MAP_LOCATION = "开发工坊内";
const DEFAULT_BACKEND_ANCHOR = "待补后端锚点";

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function slugify(value: unknown, fallbackPrefix = "station") {
  const next = String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return next || `${fallbackPrefix}-${Math.random().toString(16).slice(2, 8)}`;
}

function normalizeStringList(value: unknown, fallback: string[] = []) {
  const raw = Array.isArray(value)
    ? value
    : typeof value === "string"
      ? value.split(/[\n,]+/)
      : [];
  const items = raw.map((item) => text(item)).filter(Boolean);
  return items.length ? Array.from(new Set(items)) : fallback;
}

function normalizeRiskLevel(value: unknown, fallback: DevelopmentWorkshopRiskLevel = "中"): DevelopmentWorkshopRiskLevel {
  const raw = text(value, fallback);
  if (raw === "低" || raw === "中" || raw === "高") return raw;
  return fallback;
}

function normalizeKnowledgeBase(value: unknown, label: string, id: string): DevelopmentWorkshopKnowledgeBase {
  const record = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  return {
    summary: text(record.summary, `${label} 的共用岗位知识库，用来沉淀职责、约束、常用流程和交接方法。`),
    handoffPath: text(record.handoffPath ?? record.handoff_path, `docs/ai-handoffs/stations/${id}.md`),
    tags: normalizeStringList(record.tags, [label, id, "development-workshop-station"]),
  };
}

export const DEFAULT_DEVELOPMENT_WORKSHOP_STATIONS: DevelopmentWorkshopStation[] = [
  {
    id: "project-generator",
    label: "项目生成器",
    icon: "案",
    station: "项目办公室 / 需求信箱",
    mapScene: "map-farm",
    mapLocation: "农舍门口与需求信箱之间",
    detail: "用户先说目标，平台拆成项目计划、模块、验收标准、任务链和可交给 AI 的工作单。",
    modes: ["2D 开发者", "2D 教育版", "3D 开发者", "3D 教育版"],
    backendAnchor: "/api/development/projects/{project_id}/framework#project-generator",
    runnerCapabilities: ["repo-clone", "template-expand", "task-split"],
    aiResponsibilities: ["澄清需求", "生成计划", "拆分任务", "写验收标准"],
    npcRoleTemplates: ["需求澄清员", "项目拆解员", "验收标准编写员"],
    assignmentKeywords: ["项目生成", "需求", "拆分", "验收", "project-generator"],
    nextActions: ["接需求信箱", "生成 requirement 草案", "把计划播种到任务田"],
    approvalPolicy: "普通软件/文档可自动推进；涉及采购、真实设备动作时转人工确认。",
    riskLevel: "低",
    assignedNpcIds: [],
    knowledgeBase: {
      summary: "项目生成器的共用知识库，用来沉淀需求澄清、任务拆解和验收标准模板。",
      handoffPath: "docs/ai-handoffs/stations/project-generator.md",
      tags: ["项目生成器", "project-generator", "development-workshop-station"],
    },
  },
  {
    id: "environment-builder",
    label: "环境搭建器",
    icon: "环",
    station: "电脑车间 / Runner 机房",
    mapScene: "map-farm",
    mapLocation: "牛棚入口与机房中控",
    detail: "根据项目类型选择本机路径、GitHub 仓库、工具链、依赖安装和验证命令；每台电脑自己确定本地路径。",
    modes: ["开发者模式", "多人多电脑协作"],
    backendAnchor: "/api/runners + /api/collaboration/projects/{project_id}/computer-nodes",
    runnerCapabilities: ["github-clone", "dependency-install", "build-test", "workspace-report"],
    aiResponsibilities: ["判断电脑能力", "生成安装步骤", "安排验证命令", "回写环境状态"],
    npcRoleTemplates: ["环境搭建员", "Runner 能力巡检员", "依赖安装员"],
    assignmentKeywords: ["环境", "Runner", "依赖", "电脑", "environment-builder"],
    nextActions: ["接电脑管理器", "给 Runner 增加能力标签", "把环境状态写进项目配置"],
    approvalPolicy: "安装命令先给用户可见确认；不默认改系统级配置。",
    riskLevel: "中",
    assignedNpcIds: [],
    knowledgeBase: {
      summary: "环境搭建器的共用知识库，用来沉淀多电脑路径、拉代码、依赖安装和验证命令。",
      handoffPath: "docs/ai-handoffs/stations/environment-builder.md",
      tags: ["环境搭建器", "environment-builder", "development-workshop-station"],
    },
  },
  {
    id: "wiring-bom",
    label: "连线选型台",
    icon: "线",
    station: "硬件实验区 / 工具棚外场",
    mapScene: "map-farm",
    mapLocation: "工具棚和审批门岗之间",
    detail: "把器件清单、BOM、引脚连线、供电风险和采购建议结构化；同样也支持纯软件项目的依赖清单。",
    modes: ["嵌入式", "机器人", "课程实验", "软件依赖清单"],
    backendAnchor: "/api/development/projects/{project_id}/framework#wiring-bom",
    runnerCapabilities: ["bom-validate", "pinout-lookup", "document-generate"],
    aiResponsibilities: ["补齐器件清单", "标注线序", "识别供电/电平风险", "生成采购说明"],
    npcRoleTemplates: ["BOM 整理员", "连线检查员", "供电风险审查员"],
    assignmentKeywords: ["BOM", "连线", "器件", "供电", "wiring-bom"],
    nextActions: ["沉淀器件知识库", "接实验记录", "接审批门岗"],
    approvalPolicy: "任何真实接线、上电、烧录前都必须有人确认。",
    riskLevel: "高",
    assignedNpcIds: [],
    knowledgeBase: {
      summary: "连线选型台的共用知识库，用来沉淀 BOM、接线图、供电边界和采购审查经验。",
      handoffPath: "docs/ai-handoffs/stations/wiring-bom.md",
      tags: ["连线选型台", "wiring-bom", "development-workshop-station"],
    },
  },
  {
    id: "debug-console",
    label: "可视化调试台",
    icon: "波",
    station: "串口电视 / 调试控制台",
    mapScene: "map-home",
    mapLocation: "主房电视机，也可从电脑车间进入",
    detail: "统一串口收发、USB 扫描、日志采集和数字波形显示；协议先走 AICSV/1，后续兼容更多仪器。",
    modes: ["串口", "USB", "日志", "波形"],
    backendAnchor: "/api/collaboration/projects/{project_id}/runner-commands",
    runnerCapabilities: ["serial-scan", "serial-open", "serial-write", "waveform-parse"],
    aiResponsibilities: ["解释日志", "生成收发命令", "判断波形异常", "沉淀实验记录"],
    npcRoleTemplates: ["串口调试员", "波形分析员", "日志解释员"],
    assignmentKeywords: ["串口", "波形", "USB", "日志", "debug-console"],
    nextActions: ["复用串口电视", "接 Runner 串口白名单", "把波形帧写入实验记录"],
    approvalPolicy: "串口写入、参数改写默认属于高风险动作，需要审批或现场确认。",
    riskLevel: "高",
    assignedNpcIds: [],
    knowledgeBase: {
      summary: "可视化调试台的共用知识库，用来沉淀串口协议、波形解析格式和设备调试经验。",
      handoffPath: "docs/ai-handoffs/stations/debug-console.md",
      tags: ["可视化调试台", "debug-console", "development-workshop-station"],
    },
  },
  {
    id: "ai-coach",
    label: "AI 教练站",
    icon: "师",
    station: "NPC 管理 / 聊天小院",
    mapScene: "map-farm",
    mapLocation: "鸡舍聊天区与 NPC 精灵区",
    detail: "教育模式里一步一步教；开发模式里把 Codex、Claude、Qwen 等 NPC 分成资料、实现、测试、验收角色。",
    modes: ["教育模式", "开发模式", "多 NPC 协作"],
    backendAnchor: "/api/collaboration/projects/{project_id}/thread-workstations",
    runnerCapabilities: ["provider-adapter", "thread-inbox", "final-reply-sync"],
    aiResponsibilities: ["提出下一步", "派单协作", "最小回执", "最终回复", "交接总结"],
    npcRoleTemplates: ["学习教练", "协作调度员", "最终回复收口员"],
    assignmentKeywords: ["教练", "协作", "派单", "最终回复", "ai-coach"],
    nextActions: ["继续打通 Claude/Qwen 适配器", "把 NPC 知识库做成固定资产", "让最终回复池成为收口真值"],
    approvalPolicy: "软件任务可自动续推；硬件、花钱、发布、删库等动作转人工审核。",
    riskLevel: "中",
    assignedNpcIds: [],
    knowledgeBase: {
      summary: "AI 教练站的共用知识库，用来沉淀多模型协作话术、派单格式和最终回复收口规范。",
      handoffPath: "docs/ai-handoffs/stations/ai-coach.md",
      tags: ["AI 教练站", "ai-coach", "development-workshop-station"],
    },
  },
  {
    id: "simulation-lab",
    label: "仿真数字孪生",
    icon: "仿",
    station: "实验洞口 / 仿真台",
    mapScene: "map-toolshed",
    mapLocation: "工具棚内部实验洞口",
    detail: "先在仿真里完成接线、示例运行、数据回放和 AI 判定，再进入真机实验。",
    modes: ["教育版优先", "硬件前置验证", "机器人/ROS"],
    backendAnchor: "/api/lab/short-chain + future /api/simulations",
    runnerCapabilities: ["simulation-run", "log-replay", "artifact-capture"],
    aiResponsibilities: ["生成仿真步骤", "检查结果", "输出风险", "决定是否进入真机准备"],
    npcRoleTemplates: ["仿真测试员", "实验记录员", "真机前置审查员"],
    assignmentKeywords: ["仿真", "实验", "数字孪生", "真机", "simulation-lab"],
    nextActions: ["定义仿真任务模型", "把截图/录像沉淀为实验记录", "联动审批门岗"],
    approvalPolicy: "仿真可自动跑；真机准备、烧录、执行器动作必须过审批门岗。",
    riskLevel: "高",
    assignedNpcIds: [],
    knowledgeBase: {
      summary: "仿真数字孪生的共用知识库，用来沉淀仿真步骤、回放标准和真机前检查单。",
      handoffPath: "docs/ai-handoffs/stations/simulation-lab.md",
      tags: ["仿真数字孪生", "simulation-lab", "development-workshop-station"],
    },
  },
];

export function normalizeDevelopmentWorkshopStation(
  raw: unknown,
  fallback?: Partial<DevelopmentWorkshopStation> | null,
  index = 0,
): DevelopmentWorkshopStation {
  const record = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const fallbackRecord = fallback ?? {};
  const label = text(record.label ?? fallbackRecord.label, `自定义工位 ${index + 1}`);
  const id = slugify(record.id ?? label ?? fallbackRecord.id, "station");
  const icon = text(record.icon ?? fallbackRecord.icon, "工").slice(0, 2);
  const station = text(record.station ?? fallbackRecord.station, DEFAULT_STATION);
  const mapScene = text(record.mapScene ?? record.map_scene ?? fallbackRecord.mapScene, DEFAULT_MAP_SCENE);
  const mapLocation = text(record.mapLocation ?? record.map_location ?? fallbackRecord.mapLocation, DEFAULT_MAP_LOCATION);
  const detail = text(record.detail ?? fallbackRecord.detail, DEFAULT_DETAIL);
  const npcRoleTemplates = normalizeStringList(record.npcRoleTemplates ?? record.npc_role_templates, [
    `${label}负责人`,
  ]);
  const nextActions = normalizeStringList(record.nextActions ?? record.next_actions, [
    `补齐 ${label} 的职责说明`,
    `给 ${label} 指定负责 NPC`,
  ]);
  const assignmentKeywords = normalizeStringList(record.assignmentKeywords ?? record.assignment_keywords, [id, label]);
  const knowledgeBase = normalizeKnowledgeBase(
    record.knowledgeBase ?? record.knowledge_base ?? record.station_knowledge,
    label,
    id,
  );

  return {
    id,
    label,
    icon,
    station,
    mapScene,
    mapLocation,
    detail,
    modes: normalizeStringList(record.modes, ["开发者模式"]),
    backendAnchor: text(record.backendAnchor ?? record.backend_anchor ?? fallbackRecord.backendAnchor, DEFAULT_BACKEND_ANCHOR),
    runnerCapabilities: normalizeStringList(record.runnerCapabilities ?? record.runner_capabilities),
    aiResponsibilities: normalizeStringList(record.aiResponsibilities ?? record.ai_responsibilities, npcRoleTemplates),
    npcRoleTemplates,
    assignmentKeywords,
    nextActions,
    approvalPolicy: text(record.approvalPolicy ?? record.approval_policy ?? fallbackRecord.approvalPolicy, DEFAULT_APPROVAL_POLICY),
    riskLevel: normalizeRiskLevel(record.riskLevel ?? record.risk_level, fallbackRecord.riskLevel ?? "中"),
    assignedNpcIds: normalizeStringList(
      record.assignedNpcIds ?? record.assigned_npc_ids ?? fallbackRecord.assignedNpcIds,
      [],
    ),
    knowledgeBase,
  };
}

export function normalizeDevelopmentWorkshopStations(raw: unknown): DevelopmentWorkshopStation[] {
  const source = Array.isArray(raw) ? raw : [];
  const normalized = source
    .map((item, index) => normalizeDevelopmentWorkshopStation(item, null, index))
    .filter((item, index, list) => list.findIndex((candidate) => candidate.id === item.id) === index);
  if (normalized.length) return normalized;
  return DEFAULT_DEVELOPMENT_WORKSHOP_STATIONS.map((item, index) => normalizeDevelopmentWorkshopStation(item, item, index));
}
