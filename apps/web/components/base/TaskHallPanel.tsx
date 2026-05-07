import styles from "./base.module.css";
import { Card, Badge } from "../common";

export type TaskItem = {
  id: string;
  title: string;
  module: string;
  priority: "P0" | "P1" | "P2" | "P3";
  owner?: string;
  status: string;
  blockedReason?: string;
  needsHumanApproval?: boolean;
};

function priorityTone(priority: TaskItem["priority"]) {
  if (priority === "P0") return "red";
  if (priority === "P1") return "orange";
  if (priority === "P2") return "yellow";
  return "gray";
}

export function TaskHallPanel(props: {
  blocked: TaskItem[];
  unassigned: TaskItem[];
  active: TaskItem[];
}) {
  const blockedTone = props.blocked.length > 0 ? "orange" : "green";

  return (
    <Card title="任务大厅" right={<Badge tone={blockedTone} text={`阻塞 ${props.blocked.length}`} />}>
      <div className={styles.panelBody}>
        <div className={styles.kvRow}>
          <div className={styles.kvKey}>待分配</div>
          <div className={styles.kvVal}>{props.unassigned.length}</div>
        </div>
        <div className={styles.kvRow}>
          <div className={styles.kvKey}>执行中</div>
          <div className={styles.kvVal}>{props.active.length}</div>
        </div>

        <div className={styles.sectionTitle}>阻塞任务</div>
        {props.blocked.length === 0 ? (
          <div className={styles.muted}>当前没有阻塞任务。</div>
        ) : (
          <div>
            {props.blocked.slice(0, 4).map((task) => (
              <div key={task.id} className={styles.taskRow}>
                <div>
                  <div className={styles.taskTitle}>
                    {task.id} {task.title}
                  </div>
                  <div className={styles.taskMeta}>
                    <Badge tone={priorityTone(task.priority)} text={task.priority} />
                    <Badge tone="gray" text={task.module} />
                    <span className={styles.muted}>{task.status}</span>
                    {task.owner ? <span className={styles.muted}>负责人 {task.owner}</span> : null}
                  </div>
                  {task.blockedReason ? (
                    <div className={styles.muted} title={task.blockedReason}>
                      阻塞原因：{task.blockedReason}
                    </div>
                  ) : null}
                </div>
                <div className={styles.rightCol}>
                  {task.needsHumanApproval ? <Badge tone="orange" text="待确认" /> : null}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className={styles.sectionTitle}>待分配</div>
        {props.unassigned.length === 0 ? (
          <div className={styles.muted}>当前没有待分配任务。</div>
        ) : (
          <div>
            {props.unassigned.slice(0, 3).map((task) => (
              <div key={task.id} className={styles.taskRow}>
                <div>
                  <div className={styles.taskTitle}>
                    {task.id} {task.title}
                  </div>
                  <div className={styles.taskMeta}>
                    <Badge tone={priorityTone(task.priority)} text={task.priority} />
                    <Badge tone="gray" text={task.module} />
                    <span className={styles.muted}>{task.status}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
