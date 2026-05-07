import type { CodeBranchSummary } from "./types";
import { Empty, Panel, Pill } from "./ui";

function testTone(s?: CodeBranchSummary["testStatus"]) {
  if (s === "passed") return "ok" as const;
  if (s === "failed") return "danger" as const;
  if (s === "running") return "info" as const;
  if (s === "waiting_human") return "warn" as const;
  return "neutral" as const;
}

export function CodeWorkshopPanel({
  branch,
  syncStatus,
  branches,
  onOpenBranch
}: {
  branch: string;
  syncStatus: "synced" | "pending" | "failed";
  branches: CodeBranchSummary[];
  onOpenBranch?: (branchName: string) => void;
}) {
  return (
    <Panel
      title="代码车间"
      subtitle="分支、commit、测试流水线与合并状态"
      actions={
        <>
          <Pill label={branch} tone="info" title="当前分支" />
          <Pill label={syncStatus === "synced" ? "已同步" : syncStatus === "pending" ? "待同步" : "同步失败"} tone={syncStatus === "failed" ? "danger" : syncStatus === "pending" ? "warn" : "ok"} />
        </>
      }
    >
      {branches.length ? (
        <div style={{ display: "grid", gap: 8 }}>
          {branches.slice(0, 6).map((b) => (
            <div
              key={b.name}
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
                  {b.name}
                </div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>
                  {b.taskId ? `${b.taskId}` : "未绑定任务"}
                  {b.ownerAgentName ? ` · ${b.ownerAgentName}` : ""}
                  {b.changedFilesCount != null ? ` · ${b.changedFilesCount} files` : ""}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
                <Pill label={b.testStatus ? `测试:${b.testStatus}` : "测试:未知"} tone={testTone(b.testStatus)} />
                <Pill label={b.mergeable ? "可合并" : "待处理"} tone={b.mergeable ? "ok" : "warn"} />
                <button
                  type="button"
                  onClick={() => onOpenBranch?.(b.name)}
                  style={{
                    borderRadius: 8,
                    border: "1px solid var(--border)",
                    background: "transparent",
                    color: "var(--text)",
                    padding: "6px 10px",
                    cursor: "pointer"
                  }}
                >
                  查看
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Empty title="暂无分支数据" body="第一版可先用 mock 数据；后续接入 Git 服务后将自动展示任务分支与测试状态。" />
      )}
    </Panel>
  );
}

