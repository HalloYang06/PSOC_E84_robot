import type { AgentWorkstation } from "./types";
import { Meter, Pill, healthTone } from "./ui";

function statusLabel(status: AgentWorkstation["status"]) {
  switch (status) {
    case "working":
      return { label: "工作中", tone: "ok" as const };
    case "blocked":
      return { label: "阻塞", tone: "danger" as const };
    case "waiting_agent":
      return { label: "等AI回复", tone: "info" as const };
    case "waiting_human":
      return { label: "等人确认", tone: "warn" as const };
    case "handoff_needed":
      return { label: "需交接", tone: "danger" as const };
    case "offline":
      return { label: "离线", tone: "neutral" as const };
  }
}

export function AgentWorkstationCard({
  agent,
  onOpen,
  onHandoff
}: {
  agent: AgentWorkstation;
  onOpen?: (agentId: string) => void;
  onHandoff?: (agentId: string) => void;
}) {
  const st = statusLabel(agent.status);
  const ctxTone = healthTone(agent.contextHealth);

  return (
    <div
      style={{
        background: "var(--panel)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 10,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minWidth: 0
      }}
    >
      <div style={{ display: "flex", gap: 10, justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 800, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {agent.name}
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {agent.role}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <Pill label={st.label} tone={st.tone} />
          <Pill label={agent.runnerName} tone={agent.status === "offline" ? "neutral" : "info"} title="所属 Runner/电脑" />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 8 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Pill label={agent.model} tone="neutral" title="模型" />
          {agent.currentTaskId ? <Pill label={agent.currentTaskId} tone="info" title="当前任务" /> : <Pill label="无任务" tone="neutral" />}
        </div>

        <Meter
          label={`上下文 ${agent.contextHealth}`}
          value={agent.contextUsageRatio}
          tone={ctxTone}
          hint="上下文占用比例，过高会影响质量"
        />
        <Meter label="成功率" value={agent.successRate} tone={agent.successRate >= 0.8 ? "ok" : agent.successRate >= 0.6 ? "warn" : "danger"} />

        <div style={{ display: "flex", gap: 8, justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>今日 token</div>
          <div style={{ fontSize: 12, fontWeight: 700 }}>{agent.tokenCostToday.toFixed(2)}</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ fontSize: 12, color: "var(--muted)", minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {agent.modules.length ? agent.modules.join(", ") : "未配置模块"}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            onClick={() => onOpen?.(agent.id)}
            style={{
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--panel-alt)",
              color: "var(--text)",
              padding: "6px 10px",
              cursor: "pointer"
            }}
          >
            详情
          </button>
          <button
            type="button"
            onClick={() => onHandoff?.(agent.id)}
            disabled={agent.status === "offline"}
            style={{
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: agent.status === "offline" ? "rgba(154,164,175,0.08)" : "rgba(210,153,34,0.18)",
              color: agent.status === "offline" ? "var(--muted)" : "var(--warn)",
              padding: "6px 10px",
              cursor: agent.status === "offline" ? "not-allowed" : "pointer"
            }}
          >
            交接
          </button>
        </div>
      </div>
    </div>
  );
}
