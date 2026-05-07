import type { RescueItem } from "./types";
import { Empty, Panel, Pill } from "./ui";

function sevTone(s: RescueItem["severity"]) {
  if (s === "danger") return "danger" as const;
  if (s === "warning") return "warn" as const;
  return "info" as const;
}

export function RescueStationPanel({
  items,
  onOpenTask,
  onCreateHandoff
}: {
  items: RescueItem[];
  onOpenTask?: (taskId: string) => void;
  onCreateHandoff?: (taskId: string) => void;
}) {
  return (
    <Panel title="急救站/维修站" subtitle="失败任务、交接、预算与风险处理入口">
      {items.length ? (
        <div style={{ display: "grid", gap: 8 }}>
          {items.slice(0, 6).map((it) => (
            <div
              key={it.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 8,
                background: "var(--panel-alt)",
                padding: 10,
                display: "grid",
                gridTemplateColumns: "1fr auto",
                gap: 10,
                alignItems: "center"
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <div style={{ fontSize: 13, fontWeight: 800 }}>{it.title}</div>
                  <Pill label={it.type} tone="neutral" />
                  <Pill label={it.severity} tone={sevTone(it.severity)} />
                  {it.needsHuman ? <Pill label="需人确认" tone="warn" /> : null}
                </div>
                <div style={{ marginTop: 6, fontSize: 12, color: "var(--muted)" }}>
                  {it.taskId ? `${it.taskId} · ` : ""}
                  {it.agentName ? `${it.agentName} · ` : ""}
                  {it.summary}
                </div>
                {it.suggestedActions.length ? (
                  <div style={{ marginTop: 6, fontSize: 12, color: "var(--text)" }}>
                    {it.suggestedActions.slice(0, 2).map((a, idx) => (
                      <div key={idx}>{a}</div>
                    ))}
                  </div>
                ) : null}
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
                {it.taskId ? (
                  <button
                    type="button"
                    onClick={() => onOpenTask?.(it.taskId!)}
                    style={{
                      borderRadius: 8,
                      border: "1px solid var(--border)",
                      background: "transparent",
                      color: "var(--text)",
                      padding: "6px 10px",
                      cursor: "pointer"
                    }}
                  >
                    任务
                  </button>
                ) : null}
                {it.taskId ? (
                  <button
                    type="button"
                    onClick={() => onCreateHandoff?.(it.taskId!)}
                    style={{
                      borderRadius: 8,
                      border: "1px solid var(--border)",
                      background: "rgba(210,153,34,0.18)",
                      color: "var(--warn)",
                      padding: "6px 10px",
                      cursor: "pointer"
                    }}
                  >
                    交接
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Empty title="暂无需要急救的事项" body="第一版建议把失败任务、上下文红区、Runner 离线都归集到这里。" />
      )}
    </Panel>
  );
}

