import type {
  Agent,
  BaseOverview,
  HardwareLabCard,
  Project,
  Runner,
  Task,
  UsageSummaryRow
} from "../types";

type AnyInit = RequestInit & { json?: unknown };

const nowIso = () => new Date().toISOString();

const mockProjects: Project[] = [
  {
    id: "proj_001",
    name: "AI 合作平台 (MVP)",
    description: "第一版 AI 协作开发平台",
    defaultBranch: "main",
    developBranch: "develop",
    gitRemote: "https://github.com/wenjunyong666/ai-",
    collaboration_config: {
      computer_nodes: [
        {
          id: "pc-1",
          label: "PC1",
          status: "online",
          runner_id: "runner_001",
          connection_kind: "local",
          workspace_root: "D:/workspaces/pc-1",
          git_root: "D:/workspaces/pc-1/repo",
          read_paths: ["D:/workspaces/pc-1/repo", "D:/shared/specs"],
          write_paths: ["D:/workspaces/pc-1/repo", "D:/workspaces/pc-1/artifacts"],
        },
      ],
      ai_providers: [
        {
          id: "codex",
          label: "Codex",
          kind: "thread",
          enabled: true,
          endpoint: "local",
          model: "gpt-5",
        },
      ],
      thread_workstations: [
        {
          id: "pc-1/frontend",
          name: "PC1 / frontend",
          agent_id: "agent_002",
          computer_node: "PC1",
          computer_node_id: "pc-1",
          ai_provider: "Codex",
          ai_provider_id: "codex",
          status: "active",
          responsibility: "front-end and product experience",
          model: "gpt-5",
          permission_level: "L2",
          read_paths: ["D:/workspaces/pc-1/repo", "D:/shared/specs"],
          write_paths: ["D:/workspaces/pc-1/repo/src", "D:/workspaces/pc-1/repo/app"],
          description: "Front-end workbench",
          notes: "UI and product work",
        },
      ],
    }
  }
];

const mockRunners: Runner[] = [
  {
    id: "runner_001",
    name: "Local Runner",
    host: "PC1",
    os: "windows",
    status: "online",
    capabilities: ["git", "node", "python"],
    lastHeartbeatAt: nowIso()
  }
];

const mockTasks: Task[] = [
  {
    id: "TASK-001",
    title: "初始化前端工程骨架",
    module: "frontend",
    priority: "P1",
    status: "running",
    assigneeAgentId: "agent_002",
    branch: "ai/fe-lead/TASK-001-web-skeleton",
    requiresHumanApproval: false,
    acceptanceCriteriaCount: 6,
    updatedAt: nowIso()
  },
  {
    id: "TASK-002",
    title: "实现 /api/health",
    module: "backend",
    priority: "P1",
    status: "merged",
    assigneeAgentId: "agent_003",
    branch: "ai/be-lead/TASK-002-health",
    requiresHumanApproval: false,
    acceptanceCriteriaCount: 3,
    updatedAt: nowIso()
  },
  {
    id: "TASK-003",
    title: "硬件实验室确认卡 (H3)",
    module: "hardware",
    priority: "P0",
    status: "waiting_approval",
    requiresHumanApproval: true,
    acceptanceCriteriaCount: 5,
    updatedAt: nowIso()
  }
];

const mockAgents: Agent[] = [
  {
    id: "agent_001",
    name: "AI-Boss",
    role: "AI 团队主管",
    runnerName: "PC1",
    model: "Codex Thread",
    status: "working",
    modules: ["planning", "risk"],
    contextHealth: "green",
    contextUsageRatio: 0.32,
    tokenCostToday: 2.4,
    successRate: 0.92
  },
  {
    id: "agent_002",
    name: "AI-FE-LEAD",
    role: "前端负责人",
    runnerName: "PC1",
    model: "Codex Thread",
    status: "working",
    modules: ["frontend", "ui"],
    contextHealth: "yellow",
    contextUsageRatio: 0.63,
    tokenCostToday: 12.8,
    successRate: 0.84,
    currentTaskId: "TASK-001"
  },
  {
    id: "agent_003",
    name: "AI-BE-LEAD",
    role: "后端负责人",
    runnerName: "PC1",
    model: "Codex Thread",
    status: "waiting_human",
    modules: ["backend", "db"],
    contextHealth: "green",
    contextUsageRatio: 0.41,
    tokenCostToday: 8.1,
    successRate: 0.88
  }
];

const mockHardware: HardwareLabCard[] = [
  {
    id: "dev_001",
    deviceName: "M33 Board",
    deviceType: "devboard",
    runnerName: "PC1",
    connectionStatus: "unknown",
    currentTaskId: "TASK-003",
    riskLevel: "H3",
    aiSuggestion:
      "请确认固件分支与电源稳定后，由人类执行烧录。AI 不会自动烧录。",
    humanChecklist: [
      "固件分支正确",
      "电源稳定",
      "串口连接正常",
      "已准备急停/断电"
    ],
    uploadedLogs: 0,
    uploadedImages: 0,
    approvalStatus: "pending"
  }
];

const mockUsage: UsageSummaryRow[] = [
  {
    agentId: "agent_001",
    agentName: "AI-Boss",
    model: "Codex Thread",
    tasks: 3,
    inputTokens: 12000,
    outputTokens: 4100,
    cost: 2.4,
    successRate: 0.92
  },
  {
    agentId: "agent_002",
    agentName: "AI-FE-LEAD",
    model: "Codex Thread",
    tasks: 5,
    inputTokens: 34000,
    outputTokens: 9800,
    cost: 12.8,
    successRate: 0.84
  }
];

const mockOverview: BaseOverview = {
  projectName: mockProjects[0].name,
  branch: "develop",
  onlineAgents: 2,
  totalAgents: 3,
  onlineRunners: 1,
  totalRunners: 1,
  tokenCostToday: 36.8,
  budgetUsageRatio: 0.42,
  highRiskCount: 2,
  pendingHumanApprovals: 1,
  gitSyncStatus: "pending"
};

export function getMockOverview(): BaseOverview {
  return mockOverview;
}

export function listMockProjects(): Project[] {
  return mockProjects;
}

export function getMockProject(id: string): Project | undefined {
  return mockProjects.find((p) => p.id === id);
}

export function listMockAgents(): Agent[] {
  return mockAgents;
}

export function getMockAgent(id: string): Agent | undefined {
  return mockAgents.find((a) => a.id === id);
}

export function listMockRunners(): Runner[] {
  return mockRunners;
}

export function getMockRunner(id: string): Runner | undefined {
  return mockRunners.find((r) => r.id === id);
}

function augmentMockTask(task: Task): Task {
  if (task.id === "TASK-001") {
    return {
      ...task,
      readinessSummary: {
        status: "ready",
        label: "ready for PC1 Codex",
        detail: "matches front-end workspace and write scope",
        score: 0.92,
        blockers: [],
        warnings: [],
        matchCount: 1,
      },
      recommendedWorkstations: [
        {
          workstationId: "pc-1/frontend",
          workstationName: "PC1 / frontend",
          nodeId: "pc-1",
          nodeLabel: "PC1",
          providerId: "codex",
          providerLabel: "Codex",
          matchScore: 0.92,
          matchReason: "permission and path scope align",
          readiness: "ready",
        },
      ],
    };
  }
  if (task.id === "TASK-002") {
    return {
      ...task,
      readinessSummary: {
        status: "paired",
        label: "paired with backend workstation",
        detail: "best fit is Claude on PC2 for backend updates",
        score: 0.85,
        blockers: [],
        warnings: ["needs repo access confirmation"],
        matchCount: 1,
      },
      workstationMatches: [
        {
          workstationId: "pc-2/backend",
          workstationName: "PC2 / backend",
          matchScore: 0.85,
          matchReason: "backend module and read scope fit",
          readiness: "paired",
        },
      ],
    };
  }
  if (task.id === "TASK-003") {
    return {
      ...task,
      readinessSummary: {
        status: "blocked",
        label: "blocked by human approval",
        detail: "hardware tasks require approval before dispatch",
        score: 0.1,
        blockers: ["H3 approval required"],
        warnings: ["safety gate not cleared"],
        matchCount: 0,
      },
    };
  }
  return task;
}

export function listMockTasks(): Task[] {
  return mockTasks.map(augmentMockTask);
}

export function getMockTask(id: string): Task | undefined {
  return mockTasks.map(augmentMockTask).find((t) => t.id === id);
}

export function listMockHardware(): HardwareLabCard[] {
  return mockHardware;
}

export function listMockUsage(): UsageSummaryRow[] {
  return mockUsage;
}

export async function handleMockRequest<T>(
  path: string,
  init?: AnyInit
): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();

  // Minimal mock router to keep UI unblocked.
  if (method === "GET" && path === "/api/health") {
    return { status: "ok", version: "0.1.0" } as T;
  }
  if (method === "GET" && path === "/api/mock/overview") {
    return getMockOverview() as T;
  }
  if (method === "GET" && path === "/api/projects") {
    return listMockProjects() as T;
  }
  if (method === "GET" && path.startsWith("/api/projects/")) {
    const id = path.split("/").pop() || "";
    const p = getMockProject(id);
    if (!p) throw new Error("NOT_FOUND");
    return p as T;
  }
  if (method === "GET" && path === "/api/agents") {
    return listMockAgents() as T;
  }
  if (method === "GET" && path.startsWith("/api/agents/")) {
    const id = path.split("/").pop() || "";
    const a = getMockAgent(id);
    if (!a) throw new Error("NOT_FOUND");
    return a as T;
  }
  if (method === "GET" && path === "/api/runners") {
    return listMockRunners() as T;
  }
  if (method === "GET" && path.startsWith("/api/runners/")) {
    const id = path.split("/").pop() || "";
    const r = getMockRunner(id);
    if (!r) throw new Error("NOT_FOUND");
    return r as T;
  }
  if (method === "GET" && path === "/api/tasks") {
    return listMockTasks() as T;
  }
  if (method === "GET" && path.startsWith("/api/tasks/")) {
    const id = path.split("/").pop() || "";
    const t = getMockTask(id);
    if (!t) throw new Error("NOT_FOUND");
    return t as T;
  }
  if (method === "GET" && path === "/api/hardware") {
    return listMockHardware() as T;
  }
  if (method === "GET" && path === "/api/usage/summary") {
    return listMockUsage() as T;
  }

  // For non-essential endpoints, return empty.
  return null as T;
}
