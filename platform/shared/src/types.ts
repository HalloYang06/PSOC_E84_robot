// Shared DTOs and enums for v0.1.
// Keep these types stable; they are used across web/api/runner.

export type ID = string;

export type ISO8601 = string;

export type Money = number;

export type AgentProvider =
  | "manual_codex_thread"
  | "codex_cli"
  | "codex_sdk"
  | "openai_responses_api"
  | "openhands"
  | "openclaw"
  | "ollama"
  | "custom_http_agent";

export type ExecutionMode = "manual" | "semi_auto" | "auto";

export type PermissionLevel = "L0" | "L1" | "L2" | "L3" | "L4" | "L5";

export type ApprovalLevel = "H0" | "H1" | "H2" | "H3" | "H4";

export type ContextHealthLevel = "green" | "yellow" | "orange" | "red";

export type RunnerStatus = "online" | "offline" | "unknown";

export type AgentStatus =
  | "active"
  | "paused"
  | "offline"
  | "working"
  | "blocked"
  | "waiting_agent"
  | "waiting_human"
  | "handoff_needed";

export type TaskPriority = "P0" | "P1" | "P2" | "P3";

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

export type GitSyncStatus = "synced" | "pending" | "failed";

export interface ProjectDTO {
  id: ID;
  name: string;
  description?: string;
  type?: string;
  githubUrl?: string;
  localGitUrl?: string;
  defaultBranch?: string;
  developBranch?: string;
  createdAt: ISO8601;
  updatedAt: ISO8601;
}

export interface AgentDTO {
  id: ID;
  name: string;
  role: string;
  provider: AgentProvider;
  executionMode: ExecutionMode;
  model?: string;
  runnerId?: ID;
  host?: string;
  responsibility?: string;
  modules?: string[];
  readPaths?: string[];
  writePaths?: string[];
  permissionLevel: PermissionLevel;
  status: AgentStatus;
  maxTokensPerTask?: number;
  maxCostPerDay?: Money;
  createdAt: ISO8601;
  updatedAt: ISO8601;
}

export interface RunnerCapabilityDTO {
  name: string;
}

export interface RunnerDTO {
  id: ID;
  name: string;
  host?: string;
  os?: string;
  status: RunnerStatus;
  capabilities: RunnerCapabilityDTO[];
  hardwareAccess: boolean;
  lastHeartbeatAt?: ISO8601;
  createdAt: ISO8601;
  updatedAt: ISO8601;
}

export interface TaskDTO {
  id: ID;
  title: string;
  description?: string;
  projectId: ID;
  module?: string;
  priority: TaskPriority;
  status: TaskStatus;
  assigneeAgentId?: ID;
  reviewerAgentId?: ID;
  branch?: string;
  relatedIssue?: string;
  acceptanceCriteria?: string[];
  createdAt: ISO8601;
  updatedAt: ISO8601;
}

export type TaskEventType =
  | "created"
  | "status_changed"
  | "comment"
  | "log"
  | "artifact"
  | "approval_requested"
  | "approval_recorded"
  | "handoff_created"
  | "runner_assigned";

export interface TaskEventDTO {
  id: ID;
  taskId: ID;
  type: TaskEventType;
  message: string;
  meta?: Record<string, unknown>;
  createdAt: ISO8601;
}

export interface ContextHealthDTO {
  taskId: ID;
  agentId?: ID;
  modelContextLimit?: number;
  contextTokensCurrent?: number;
  contextUsageRatio?: number; // 0..1
  conversationTurns?: number;
  filesLoadedCount?: number;
  failedRetryCount?: number;
  repeatedQuestionCount?: number;
  lastSummaryAt?: ISO8601;
  level: ContextHealthLevel;
  handoffRecommended: boolean;
  createdAt: ISO8601;
}

export type ApprovalStatus = "not_required" | "pending" | "approved" | "rejected";

export interface ApprovalDTO {
  id: ID;
  projectId: ID;
  taskId?: ID;
  title: string;
  level: ApprovalLevel;
  status: ApprovalStatus;
  requestedBy?: string;
  approvedBy?: string;
  requestedAt: ISO8601;
  decidedAt?: ISO8601;
  notes?: string;
}

export interface HandoffPackageDTO {
  id: ID;
  taskId: ID;
  fromAgentId?: ID;
  toAgentId?: ID;
  goal: string;
  currentStatus: string;
  completedSteps: string[];
  remainingSteps: string[];
  importantContext: string[];
  changedFiles: string[];
  currentBranch?: string;
  lastErrorSummary?: string;
  doNotRepeat: string[];
  createdAt: ISO8601;
}

export interface UsageLogDTO {
  id: ID;
  projectId: ID;
  taskId?: ID;
  agentId?: ID;
  model?: string;
  inputTokens?: number;
  outputTokens?: number;
  cachedTokens?: number;
  cost?: Money;
  startedAt: ISO8601;
  finishedAt?: ISO8601;
  status?: "success" | "failed" | "cancelled";
}

export interface BaseOverviewDTO {
  projectName: string;
  branch: string;
  onlineAgents: number;
  totalAgents: number;
  onlineRunners: number;
  totalRunners: number;
  tokenCostToday: Money;
  budgetUsageRatio: number; // 0..1
  highRiskCount: number;
  pendingHumanApprovals: number;
  gitSyncStatus: GitSyncStatus;
}

