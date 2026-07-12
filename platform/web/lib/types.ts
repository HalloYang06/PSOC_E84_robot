export type Id = string;

export type ContextHealth = "green" | "yellow" | "orange" | "red";

export type ApprovalRiskLevel = "H0" | "H1" | "H2" | "H3" | "H4";

export type GitSyncStatus = "synced" | "pending" | "failed";

export type TaskStatus =
  | "draft"
  | "ready"
  | "planning"
  | "waiting_approval"
  | "running"
  | "waiting_response"
  | "testing"
  | "reviewing"
  | "blocked"
  | "failed"
  | "merged"
  | "rolled_back"
  | "cancelled";

export type AgentStatus =
  | "working"
  | "blocked"
  | "waiting_agent"
  | "waiting_human"
  | "offline"
  | "handoff_needed";

export type RunnerStatus = "online" | "offline";

export type Project = {
  id: Id;
  name: string;
  description?: string;
  defaultBranch: string;
  developBranch: string;
  gitRemote?: string;
  collaboration_config?: {
    computer_nodes?: unknown[];
    ai_providers?: unknown[];
    thread_workstations?: unknown[];
    [key: string]: unknown;
  };
};

export type Agent = {
  id: Id;
  name: string;
  role: string;
  runnerName: string;
  model: string;
  status: AgentStatus;
  modules: string[];
  contextHealth: ContextHealth;
  contextUsageRatio: number;
  tokenCostToday: number;
  successRate: number;
  currentTaskId?: Id;
};

export type Runner = {
  id: Id;
  name: string;
  host: string;
  os: string;
  status: RunnerStatus;
  capabilities: string[];
  lastHeartbeatAt: string;
};

export type Task = {
  id: Id;
  title: string;
  module: string;
  priority: "P0" | "P1" | "P2" | "P3";
  status: TaskStatus;
  assigneeAgentId?: Id;
  branch?: string;
  blockedReason?: string;
  requiresHumanApproval: boolean;
  acceptanceCriteriaCount: number;
  updatedAt: string;
  readinessSummary?: {
    status?: string;
    label?: string;
    detail?: string;
    score?: number;
    blockers?: string[];
    warnings?: string[];
    matchCount?: number;
  };
  recommendedWorkstations?: Array<{
    workstationId?: Id;
    workstationName?: string;
    nodeId?: Id;
    nodeLabel?: string;
    providerId?: Id;
    providerLabel?: string;
    matchScore?: number;
    matchReason?: string;
    readiness?: string;
  }>;
  workstationMatches?: Array<{
    workstationId?: Id;
    workstationName?: string;
    matchScore?: number;
    matchReason?: string;
    readiness?: string;
  }>;
};

export type BaseOverview = {
  projectName: string;
  branch: string;
  onlineAgents: number;
  totalAgents: number;
  onlineRunners: number;
  totalRunners: number;
  tokenCostToday: number;
  budgetUsageRatio: number;
  highRiskCount: number;
  pendingHumanApprovals: number;
  gitSyncStatus: GitSyncStatus;
};

export type HardwareLabCard = {
  id: Id;
  deviceName: string;
  deviceType: string;
  runnerName: string;
  connectionStatus: "online" | "offline" | "unknown";
  currentTaskId?: Id;
  riskLevel: ApprovalRiskLevel;
  aiSuggestion: string;
  humanChecklist: string[];
  uploadedLogs: number;
  uploadedImages: number;
  approvalStatus: "not_required" | "pending" | "approved" | "rejected";
};

export type UsageSummaryRow = {
  agentId: Id;
  agentName: string;
  model: string;
  tasks: number;
  inputTokens: number;
  outputTokens: number;
  cost: number;
  successRate: number;
};
