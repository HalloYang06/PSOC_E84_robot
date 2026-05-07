import type { HardwareLabCard } from "./types";
import { Empty, Panel, Pill, approvalTone, riskTone } from "./ui";

export function HardwareLabPanel({
  devices,
  onOpenDevice,
  onRequestApproval
}: {
  devices: HardwareLabCard[];
  onOpenDevice?: (deviceId: string) => void;
  onRequestApproval?: (deviceId: string) => void;
}) {
  return (
    <Panel title="硬件实验室" subtitle="人工确认与日志上传入口（不支持自动硬件控制）">
      {devices.length ? (
        <div style={{ display: "grid", gap: 8 }}>
          {devices.slice(0, 6).map((d) => (
            <div
              key={d.id}
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
                  <div style={{ fontWeight: 750, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {d.deviceName}
                  </div>
                  <Pill label={d.deviceType} tone="neutral" />
                  <Pill label={d.runnerName} tone={d.connectionStatus === "offline" ? "neutral" : "info"} title="所属 Runner" />
                  <Pill label={d.riskLevel} tone={riskTone(d.riskLevel)} title="人工确认等级" />
                  <Pill label={d.approvalStatus} tone={approvalTone(d.approvalStatus)} title="确认状态" />
                </div>
                <div style={{ marginTop: 6, fontSize: 12, color: "var(--muted)" }}>
                  {d.currentTaskId ? `${d.currentTaskId} · ` : ""}
                  logs {d.uploadedLogs} · images {d.uploadedImages}
                </div>
                <div style={{ marginTop: 6, fontSize: 12, color: "var(--text)" }}>{d.aiSuggestion}</div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "flex-end", flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={() => onOpenDevice?.(d.id)}
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
                <button
                  type="button"
                  onClick={() => onRequestApproval?.(d.id)}
                  style={{
                    borderRadius: 8,
                    border: "1px solid var(--border)",
                    background: "rgba(210,153,34,0.18)",
                    color: "var(--warn)",
                    padding: "6px 10px",
                    cursor: "pointer"
                  }}
                >
                  请求确认
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Empty title="暂无硬件任务" body="第一版只提供人工确认与日志入口，任何真实硬件操作必须由人类执行。" />
      )}
    </Panel>
  );
}

