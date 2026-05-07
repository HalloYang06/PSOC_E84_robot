import styles from "./base.module.css";
import { Card, Badge } from "../common";

export function BossOfficePanel(props: {
  project: string;
  stage: string;
  weeklyGoal: string;
  doneToday: number;
  inProgress: number;
  blocked: number;
  pendingApprovals: number;
  topRisk: string;
  recommendations: string[];
}) {
  const approvalTone = props.pendingApprovals > 0 ? "orange" : "green";
  const blockedTone = props.blocked > 0 ? "orange" : "green";

  return (
    <Card
      title="老板办公室"
      right={<Badge tone={approvalTone} text={`待确认 ${props.pendingApprovals}`} />}
    >
      <div className={styles.panelBody}>
        <div className={styles.kvRow}>
          <div className={styles.kvKey}>项目</div>
          <div className={styles.kvVal}>{props.project}</div>
        </div>
        <div className={styles.kvRow}>
          <div className={styles.kvKey}>阶段</div>
          <div className={styles.kvVal}>{props.stage}</div>
        </div>
        <div className={styles.kvRow}>
          <div className={styles.kvKey}>本周目标</div>
          <div className={styles.kvVal}>{props.weeklyGoal}</div>
        </div>

        <div className={styles.kvRow}>
          <div className={styles.kvKey}>今日完成</div>
          <div className={styles.kvVal}>{props.doneToday}</div>
        </div>
        <div className={styles.kvRow}>
          <div className={styles.kvKey}>进行中</div>
          <div className={styles.kvVal}>{props.inProgress}</div>
        </div>
        <div className={styles.kvRow}>
          <div className={styles.kvKey}>阻塞</div>
          <div className={styles.kvVal}>
            <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
              <span>{props.blocked}</span>
              <Badge tone={blockedTone} text={props.blocked > 0 ? "需处理" : "正常"} />
            </span>
          </div>
        </div>

        <div className={styles.kvRow}>
          <div className={styles.kvKey}>最高风险</div>
          <div className={styles.kvVal} title={props.topRisk}>
            {props.topRisk}
          </div>
        </div>

        <div>
          <div className={styles.sectionTitle}>建议</div>
          <ol className={styles.list}>
            {props.recommendations.slice(0, 4).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </div>
      </div>
    </Card>
  );
}
