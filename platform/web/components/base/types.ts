export type HealthLevel = "green" | "yellow" | "orange" | "red";

export type AgentStatus =
  | "working"
  | "blocked"
  | "waiting_agent"
  | "waiting_human"
  | "offline"
  | "handoff_needed";

export type GitSyncStatus = "synced" | "pending" | "failed";

export type HardwareRiskLevel = "H0" | "H1" | "H2" | "H3" | "H4";

export type ApprovalStatus = "not_required" | "pending" | "approved" | "rejected";

export type BaseOverview = {
  projectName: string;
  branch: string;
  onlineAgents: number;
  totalAgents: number;
  onlineRunners: number;
  totalRunners: number;
  tokenCostToday: number;
  budgetUsageRatio: number; // 0..1
  highRiskCount: number;
  pendingHumanApprovals: number;
  gitSyncStatus: GitSyncStatus;
};

export type AgentWorkstation = {
  id: string;
  name: string;
  role: string;
  runnerName: string;
  model: string;
  currentTaskId?: string;
  modules: string[];
  contextHealth: HealthLevel;
  contextUsageRatio: number; // 0..1
  tokenCostToday: number;
  successRate: number; // 0..1
  status: AgentStatus;
};

export type CodeBranchSummary = {
  name: string;
  taskId?: string;
  ownerAgentName?: string;
  latestCommit?: string;
  changedFilesCount?: number;
  testStatus?: "not_started" | "running" | "passed" | "failed" | "skipped" | "waiting_human";
  reviewStatus?: "not_started" | "waiting" | "approved" | "changes_requested";
  mergeable?: boolean;
};

export type HardwareLabCard = {
  id: string;
  deviceName: string;
  deviceType: string;
  runnerName: string;
  connectionStatus: "online" | "offline" | "unknown";
  currentTaskId?: string;
  riskLevel: HardwareRiskLevel;
  aiSuggestion: string;
  humanChecklist: string[];
  uploadedLogs: number;
  uploadedImages: number;
  approvalStatus: ApprovalStatus;
};

export type FinanceSummary = {
  tokenCostToday: number;
  tokenCostWeek: number;
  budgetUsageRatio: number; // 0..1
  topAgents: Array<{
    agentName: string;
    model: string;
    tokenCostToday: number;
    successRate: number; // 0..1
  }>;
  alerts: string[];
};

export type RescueItem = {
  id: string;
  type:
    | "task_failed"
    | "context_overload"
    | "token_budget"
    | "runner_offline"
    | "git_conflict"
    | "human_approval";
  severity: "info" | "warning" | "danger";
  title: string;
  taskId?: string;
  agentName?: string;
  summary: string;
  suggestedActions: string[];
  needsHuman: boolean;
};

