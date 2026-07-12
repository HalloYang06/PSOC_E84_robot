import styles from "./base.module.css";
import { Badge } from "../common";
import type { GitSyncStatus } from "./types";

export function BaseTopBar(props: {
  projectName: string;
  branch: string;
  environment?: string;
  onlineAgents: number;
  totalAgents: number;
  onlineRunners: number;
  totalRunners: number;
  tokenCostToday: number;
  budgetUsageRatio: number;
  highRiskCount: number;
  pendingHumanApprovals: number;
  gitSyncStatus: GitSyncStatus;
}) {
  const budgetPct = Math.round(props.budgetUsageRatio * 100);
  const riskTone =
    props.highRiskCount > 0 ? (props.highRiskCount >= 3 ? "red" : "orange") : "green";
  const approvalsTone = props.pendingHumanApprovals > 0 ? "orange" : "green";
  const gitTone =
    props.gitSyncStatus === "synced"
      ? "green"
      : props.gitSyncStatus === "pending"
        ? "yellow"
        : "red";

  const gitLabel =
    props.gitSyncStatus === "synced"
      ? "Git 已同步"
      : props.gitSyncStatus === "pending"
        ? "Git 待同步"
        : "Git 同步失败";

  return (
    <header className={styles.topBar}>
      <div className={styles.topLeft}>
        <div className={styles.projectName} title={props.projectName}>
          {props.projectName}
        </div>
        <div className={styles.meta}>
          {props.environment ? `${props.environment} | ` : ""}
          {props.branch}
        </div>
      </div>

      <div className={styles.topRight}>
        <div className={styles.kpi}>
          <span className={styles.kpiLabel}>AI</span>
          <span className={styles.kpiValue}>
            {props.onlineAgents}/{props.totalAgents}
          </span>
        </div>
        <div className={styles.kpi}>
          <span className={styles.kpiLabel}>Runner</span>
          <span className={styles.kpiValue}>
            {props.onlineRunners}/{props.totalRunners}
          </span>
        </div>
        <div className={styles.kpi}>
          <span className={styles.kpiLabel}>今日 token</span>
          <span className={styles.kpiValue}>{props.tokenCostToday.toFixed(1)} 元</span>
        </div>
        <div className={styles.kpi}>
          <span className={styles.kpiLabel}>预算</span>
          <span className={styles.kpiValue}>{budgetPct}%</span>
        </div>

        <Badge tone={riskTone} text={`高风险 ${props.highRiskCount}`} />
        <Badge tone={approvalsTone} text={`待确认 ${props.pendingHumanApprovals}`} />
        <Badge tone={gitTone} text={gitLabel} />
      </div>
    </header>
  );
}
