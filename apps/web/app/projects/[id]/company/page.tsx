import { redirect } from "next/navigation";
import Link from "next/link";
import {
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectState,
} from "../../../../lib/server-data";
import { isNpcSeatRecord, platformProviderIdFromSeat } from "../../../../lib/platform-provider";
import { WorkbenchClient } from "../workbench/workbench-client";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type AnyRecord = Record<string, any>;

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

export default async function CompanyPage({ params }: { params: { id: string } }) {
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?next=/projects/${params.id}/company`);
  }

  const projectState = await getProjectState(params.id);
  const project = projectState.data;
  if (!project) {
    return (
      <main style={{ padding: 32, color: "#eaffff" }}>
        <p>项目不存在或无权限。</p>
        <Link href="/projects" style={{ color: "#93fbff" }}>← 返回项目列表</Link>
      </main>
    );
  }

  const computerNodesState = await getProjectComputerNodesState(params.id);
  const liveNodes = asArray<AnyRecord>(computerNodesState.data);

  const config = (project.collaboration_config ?? {}) as AnyRecord;
  const rawWorkstations = asArray<AnyRecord>(
    config.thread_workstations ?? config.threadWorkstations ?? config.workstations,
  );
  const seatRecords = rawWorkstations.filter((item) => isNpcSeatRecord(item));
  const configNodes = asArray<AnyRecord>(config.computer_nodes ?? config.nodes);
  const workstationProfiles = (config.workstation_profiles && typeof config.workstation_profiles === "object")
    ? (config.workstation_profiles as AnyRecord)
    : {};

  const nodeMap = new Map<string, string>();
  for (const node of [...configNodes, ...liveNodes]) {
    const id = text(node?.id ?? node?.node_id, "");
    if (!id) continue;
    const name = text(node?.name ?? node?.label ?? node?.hostname ?? id, id);
    nodeMap.set(id, name);
  }

  const leadByNode = new Map<string, string>();
  for (const [nodeId, profile] of Object.entries(workstationProfiles)) {
    if (profile && typeof profile === "object") {
      const lead = text((profile as AnyRecord).lead_seat_id ?? (profile as AnyRecord).leadSeatId, "");
      if (lead) leadByNode.set(String(nodeId), lead);
    }
  }

  const allSeats = seatRecords.map((seat, index) => {
    const id = text(seat.id ?? seat.config_id ?? seat.row_id, `seat-${index}`);
    const name = text(seat.name ?? seat.title, `NPC ${index + 1}`);
    const computerNodeId = text(seat.computer_node_id ?? seat.computerNodeId, "");
    const providerId = platformProviderIdFromSeat(seat) || text(seat.provider_id ?? seat.providerId, "");
    const providerLabel = text(seat.provider_label ?? seat.providerLabel ?? providerId, providerId);
    const responsibility = text(seat.responsibility ?? seat.body, "待分配职责");
    const skillLoadout = asArray<string>(seat.skill_loadout ?? seat.skillLoadout).map((s) => String(s)).filter(Boolean);
    const knowledgeSummary = text(seat.knowledge_summary ?? seat.knowledgeSummary, "");
    const automationEnabled = Boolean(seat.automation_enabled ?? seat.automationEnabled ?? false);
    const model = text(seat.model, "");
    const permissionLevel = text(seat.permission_level ?? seat.permissionLevel, "");
    const meta = (seat.metadata && typeof seat.metadata === "object") ? (seat.metadata as AnyRecord) : {};
    const gitUserName = text(meta.git_user_name ?? meta.gitUserName, name);
    const gitUserEmail = text(
      meta.git_user_email ?? meta.gitUserEmail,
      `bot+${id}@noreply.invalid`,
    );
    const reviewPolicy = text(meta.review_policy ?? meta.reviewPolicy, "inherit");
    const leadSeatId = computerNodeId ? (leadByNode.get(computerNodeId) ?? "") : "";
    const isLead = !!leadSeatId && leadSeatId === id;
    return {
      id,
      name,
      computerNodeId,
      computerNodeName: computerNodeId ? nodeMap.get(computerNodeId) ?? computerNodeId : "",
      providerId,
      providerLabel,
      responsibility,
      skillLoadout,
      knowledgeSummary,
      automationEnabled,
      model,
      permissionLevel,
      gitUserName,
      gitUserEmail,
      reviewPolicy,
      leadSeatId,
      isLead,
    };
  });

  const leadSeats = allSeats.filter((s) => s.isLead);

  const me = auth.data?.user as AnyRecord | null;
  const currentUserId = text(me?.id, "");
  const currentUserName = text(me?.name ?? me?.email ?? me?.id, currentUserId || "我");

  return (
    <WorkbenchClient
      projectId={String(project.id ?? params.id)}
      projectName={text(project.name, `项目 ${params.id.slice(0, 8)}`)}
      apiBaseUrl={(process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8010").trim().replace(/\/$/, "")}
      seats={leadSeats}
      currentUserId={currentUserId}
      currentUserName={currentUserName}
      pageMode="company"
    />
  );
}
