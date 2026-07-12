import type { AgentWorkstation } from "./types";
import { AgentWorkstationCard } from "./AgentWorkstationCard";
import { Empty, Panel } from "./ui";

export function AgentWorkstationGrid({
  agents,
  onOpenAgent,
  onHandoffAgent
}: {
  agents: AgentWorkstation[];
  onOpenAgent?: (agentId: string) => void;
  onHandoffAgent?: (agentId: string) => void;
}) {
  return (
    <Panel title="AI 工位区" subtitle="状态、任务、上下文健康与预算">
      {agents.length ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 10
          }}
        >
          {agents.map((a) => (
            <AgentWorkstationCard key={a.id} agent={a} onOpen={onOpenAgent} onHandoff={onHandoffAgent} />
          ))}
        </div>
      ) : (
        <Empty title="暂无 AI 工位" body="先在 AI 成员页面添加 AI，并在任务大厅指派任务。" />
      )}
    </Panel>
  );
}

