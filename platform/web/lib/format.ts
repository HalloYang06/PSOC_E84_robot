import type {
  AgentStatus,
  ContextHealth,
  TaskStatus,
  ApprovalRiskLevel
} from "./types";

export function formatMoneyCny(amount: number): string {
  if (!Number.isFinite(amount)) return "-";
  return `${amount.toFixed(1)} 元`;
}

export function formatPct(ratio: number): string {
  if (!Number.isFinite(ratio)) return "-";
  return `${Math.round(ratio * 100)}%`;
}

export function formatDateTime(iso: string): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function healthLabel(h: ContextHealth): string {
  switch (h) {
    case "green":
      return "正常";
    case "yellow":
      return "偏多";
    case "orange":
      return "需交接";
    case "red":
      return "过载";
  }
}

export function taskStatusLabel(s: TaskStatus): string {
  const map: Record<TaskStatus, string> = {
    draft: "草稿",
    ready: "待执行",
    planning: "规划中",
    waiting_approval: "等确认",
    running: "执行中",
    waiting_response: "等回复",
    testing: "测试中",
    reviewing: "审查中",
    blocked: "阻塞",
    failed: "失败",
    merged: "已合并",
    rolled_back: "已回滚",
    cancelled: "已取消"
  };
  return map[s] || s;
}

export function agentStatusLabel(s: AgentStatus): string {
  const map: Record<AgentStatus, string> = {
    working: "工作中",
    blocked: "卡住了",
    waiting_agent: "等同事",
    waiting_human: "等确认",
    offline: "离线",
    handoff_needed: "需交接"
  };
  return map[s] || s;
}

export function riskLabel(h: ApprovalRiskLevel): string {
  const map: Record<ApprovalRiskLevel, string> = {
    H0: "H0",
    H1: "H1",
    H2: "H2",
    H3: "H3",
    H4: "H4"
  };
  return map[h] || h;
}

