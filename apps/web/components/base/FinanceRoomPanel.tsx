import type { FinanceSummary } from "./types";
import { Empty, Meter, Panel, Pill } from "./ui";

export function FinanceRoomPanel({
  summary,
  onOpenUsage
}: {
  summary?: FinanceSummary;
  onOpenUsage?: () => void;
}) {
  if (!summary) {
    return (
      <Panel title="财务室" subtitle="token/成本与预算告警">
        <Empty title="暂无成本数据" body="第一版可先用 mock 数据；后续由后端 usage 统计驱动。" />
      </Panel>
    );
  }

  return (
    <Panel
      title="财务室"
      subtitle="token/成本与预算告警"
      actions={
        <button
          type="button"
          onClick={onOpenUsage}
          style={{
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "transparent",
            color: "var(--text)",
            padding: "6px 10px",
            cursor: "pointer"
          }}
        >
          详情
        </button>
      }
    >
      <div style={{ display: "grid", gap: 10 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 10, background: "var(--panel-alt)" }}>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>今日</div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>{summary.tokenCostToday.toFixed(2)}</div>
          </div>
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 10, background: "var(--panel-alt)" }}>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>本周</div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>{summary.tokenCostWeek.toFixed(2)}</div>
          </div>
        </div>

        <Meter
          label="预算使用率"
          value={summary.budgetUsageRatio}
          tone={summary.budgetUsageRatio >= 0.85 ? "danger" : summary.budgetUsageRatio >= 0.7 ? "warn" : "ok"}
        />

        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>高消耗 AI</div>
          {summary.topAgents.length ? (
            <div style={{ display: "grid", gap: 6 }}>
              {summary.topAgents.slice(0, 3).map((a) => (
                <div
                  key={a.agentName}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr auto",
                    gap: 10,
                    alignItems: "center",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: 10,
                    background: "var(--panel-alt)"
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 750, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {a.agentName}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>{a.model}</div>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "flex-end", flexWrap: "wrap" }}>
                    <Pill label={`成功率 ${Math.round(a.successRate * 100)}%`} tone={a.successRate >= 0.8 ? "ok" : a.successRate >= 0.6 ? "warn" : "danger"} />
                    <Pill label={a.tokenCostToday.toFixed(2)} tone="info" title="今日 token 消耗" />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="暂无排行" />
          )}
        </div>

        {summary.alerts.length ? (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {summary.alerts.slice(0, 4).map((a) => (
              <Pill key={a} label={a} tone="warn" />
            ))}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

