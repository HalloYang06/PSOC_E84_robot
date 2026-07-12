const replacements: Array<[string, string]> = [
  ["AI-Boss", "总控主管"],
  ["AI-PM", "项目管家"],
  ["AI-ARCH", "架构工头"],
  ["AI-FE-LEAD", "前端主理人"],
  ["AI-FE-GAME", "界面造景师"],
  ["AI-BE-LEAD", "后端主理人"],
  ["AI-RUNNER-GIT", "执行与版本官"],
  ["AI-DEVOPS", "部署工位"],
  ["Codex Thread", "线程工位"],
  ["Codex", "编码代理"],
  ["manual_codex_thread", "手动线程"],
  ["codex_cli", "命令行代理"],
  ["codex_sdk", "编码执行器"],
  ["openai_responses_api", "模型接口"],
  ["human-chief", "人类总工程师"],
  ["human_lead", "人类总工程师"],
  ["agent_boss", "总控主管"],
  ["agent_fe_game", "界面造景师"],
  ["agent_runner_git", "执行与版本官"],
  ["runner_pc1", "一号执行节点"],
  ["runner_pc2", "二号执行节点"],
  ["runner_nanopi", "边缘执行节点"],
  ["windows", "视窗系统"],
  ["linux", "开源系统"],
  ["git", "版本仓库"],
  ["node", "前端构建"],
  ["python", "脚本执行"],
  ["ros", "机器人中间件"],
  ["frontend", "前端"],
  ["backend", "后端"],
  ["hardware", "硬件"],
  ["planning", "规划"],
  ["risk", "风险"],
  ["ui", "界面"],
  ["db", "数据"],
  ["web", "网页"],
  ["api", "接口"],
  ["thread_request", "线程信件"],
  ["hardware_request", "硬件信件"],
  ["knowledge_note", "知识条目"],
  ["Rehab Arm Platform", "康复机械臂项目"],
  ["AI Collab Platform", "智能体协作平台"],
  ["M33 board", "M33 开发板"],
  ["Rehab Arm", "康复机械臂"],
  ["Flash firmware", "烧录固件"],
  ["Real motion test", "真机动作测试"],
];

function looksBroken(value: string): boolean {
  return value.includes("???") || value.includes("锟") || value.includes("�");
}

function replaceKnownTerms(value: string): string {
  return replacements.reduce((text, [from, to]) => text.replaceAll(from, to), value);
}

export function toCn(text: string | number | null | undefined, fallback = "待补充"): string {
  const value = String(text ?? "").trim();
  if (!value || looksBroken(value)) return fallback;
  return replaceKnownTerms(value);
}

export function formatMoney(value: number | null | undefined): string {
  return `${Number(value ?? 0).toFixed(1)} 元`;
}

export function formatPriority(value: string | null | undefined): string {
  switch (String(value ?? "").toUpperCase()) {
    case "P0":
      return "最高";
    case "P1":
      return "很高";
    case "P2":
      return "常规";
    case "P3":
      return "较低";
    case "HIGH":
      return "高优先";
    case "MEDIUM":
      return "中优先";
    case "LOW":
      return "低优先";
    default:
      return toCn(value, "常规");
  }
}

export function formatTaskStatus(value: string | null | undefined): string {
  switch (String(value ?? "")) {
    case "draft":
      return "草稿";
    case "ready":
      return "待派工";
    case "planning":
      return "筹划中";
    case "running":
      return "进行中";
    case "testing":
      return "联调中";
    case "reviewing":
      return "审查中";
    case "blocked":
      return "阻塞";
    case "failed":
      return "异常";
    case "merged":
      return "已合并";
    case "waiting_approval":
      return "待人工确认";
    case "rolled_back":
      return "已回滚";
    case "done":
      return "已完成";
    default:
      return toCn(value, "待派工");
  }
}

export function formatApprovalStatus(value: string | null | undefined): string {
  switch (String(value ?? "")) {
    case "pending":
      return "待确认";
    case "approved":
      return "已通过";
    case "rejected":
      return "已拒绝";
    case "cancelled":
      return "已取消";
    case "needs_changes":
      return "待修改";
    default:
      return toCn(value, "待确认");
  }
}

export function formatRiskLevel(value: string | null | undefined): string {
  switch (String(value ?? "")) {
    case "H0":
      return "极低";
    case "H1":
      return "较低";
    case "H2":
      return "中等";
    case "H3":
      return "较高";
    case "H4":
      return "极高";
    default:
      return toCn(value, "待评估");
  }
}

export function formatContextHealth(value: string | null | undefined): string {
  switch (String(value ?? "")) {
    case "red":
    case "overloaded":
      return "过载";
    case "orange":
      return "紧张";
    case "yellow":
      return "偏高";
    case "green":
    default:
      return "稳定";
  }
}

export function formatAgentStatus(value: string | null | undefined): string {
  switch (String(value ?? "")) {
    case "working":
      return "工作中";
    case "waiting_human":
      return "待人工确认";
    case "blocked":
      return "阻塞";
    case "offline":
      return "离线";
    default:
      return "待命";
  }
}

export function formatRunnerStatus(value: string | null | undefined): string {
  return String(value ?? "") === "online" ? "在线" : "离线";
}

export function formatBranch(value: string | null | undefined): string {
  const text = toCn(value, "未绑定分支");
  return text
    .replaceAll("ai/fe-lead", "前端主线")
    .replaceAll("ai/fe-game", "造景主线")
    .replaceAll("ai/be-lead", "后端主线")
    .replaceAll("ai/runner", "执行主线")
    .replaceAll("ai/", "工位/");
}

export function formatId(value: string | null | undefined, kind = "记录"): string {
  const text = String(value ?? "").trim();
  if (!text) return `${kind}未登记`;
  if (text.startsWith("TASK-")) return `任务 ${text.replace("TASK-", "")}`;
  if (text.startsWith("REQ-")) return `需求 ${text.replace("REQ-", "")}`;
  if (text.startsWith("APR-")) return `审批 ${text.replace("APR-", "")}`;
  if (text.startsWith("agent_")) return `工位 ${text.replace("agent_", "")}`;
  if (text.startsWith("runner_")) return `节点 ${text.replace("runner_", "")}`;
  if (text.length >= 32 && text.includes("-")) return `${kind} ${text.slice(0, 8)}`;
  return toCn(text, `${kind}未登记`);
}

export function formatAuditAction(value: string | null | undefined): string {
  switch (String(value ?? "")) {
    case "created":
    case "task.create":
      return "创建";
    case "updated":
      return "更新";
    case "approved":
    case "approval.created":
      return "审批";
    case "rejected":
      return "拒绝";
    case "accepted":
      return "接手";
    case "handoff":
      return "交接";
    case "synced":
      return "同步";
    case "rolled_back":
      return "回滚";
    case "runner.claim_task":
      return "领任务";
    default:
      return toCn(value, "动作");
  }
}

export const 中文 = toCn;
export const 金额 = formatMoney;
export const 优先级 = formatPriority;
export const 任务状态 = formatTaskStatus;
export const 审批状态 = formatApprovalStatus;
export const 风险等级 = formatRiskLevel;
export const 上下文健康 = formatContextHealth;
export const 智能体状态 = formatAgentStatus;
export const 节点状态 = formatRunnerStatus;
export const 分支名 = formatBranch;
export const 编号 = formatId;
export const 审计动作 = formatAuditAction;
export const 事件类型 = formatAuditAction;
