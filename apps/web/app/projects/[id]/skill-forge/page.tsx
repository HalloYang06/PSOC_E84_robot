import Link from "next/link";
import { redirect } from "next/navigation";
import { createProjectSkill } from "../../../actions";
import {
  getCollaborationMessagesState,
  getCurrentAuthState,
  getProjectKnowledgeDocumentsState,
  getProjectSkillsState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
  getSeatSkillAssignmentsState,
} from "../../../../lib/server-data";
import { DEFAULT_PLATFORM_SKILL_LIBRARY } from "../../../../lib/platform-skills";
import { isNpcSeatRecord } from "../../../../lib/platform-provider";
import { SkillForgeClient } from "./skill-forge-client";
import styles from "./skill-forge.module.css";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type AnyRecord = Record<string, any>;
type ForgeTab = "skills" | "knowledge" | "git";

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function safeProjectReturnPath(projectId: string, value: unknown) {
  const raw = text(value, "");
  if (!raw.startsWith(`/projects/${projectId}/`)) return "";
  if (/^\/\//.test(raw) || raw.includes("\\") || raw.includes("://")) return "";
  return raw;
}

function labelProjectReturnPath(value: string) {
  if (value.includes("/2d-upgrade")) return "返回主页面";
  if (value.includes("/workbench")) return "返回 NPC 工作台";
  if (value.includes("/datasets") || value.includes("/ai-lab") || value.includes("/robotics")) return "返回设备数据工作台";
  if (value.includes("/observability")) return "返回公司层";
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/skill-forge")) return "返回能力工坊";
  return "返回来源";
}

function idOf(value: AnyRecord) {
  return text(value.id ?? value.workstation_id ?? value.config_id ?? value.row_id ?? value.slug, "");
}

function seatIdentityValues(value: AnyRecord) {
  return [
    value.row_id,
    value.rowId,
    value.id,
    value.config_id,
    value.configId,
    value.name,
  ].map((item) => text(item, "")).filter(Boolean);
}

function seatMatchesIdentity(value: AnyRecord, identity: string) {
  const normalized = text(identity, "");
  return normalized ? seatIdentityValues(value).includes(normalized) : false;
}

function normalizeResourceParam(value: string, seats: AnyRecord[], workstations: AnyRecord[]) {
  const raw = text(value, "");
  if (!raw) return "";
  const [kind, ...rest] = raw.split(":");
  const identity = rest.join(":");
  if (kind === "seat" && identity) {
    const seat = seats.find((item) => seatMatchesIdentity(item, identity));
    return seat ? `seat:${idOf(seat)}` : raw;
  }
  if (kind === "station" && identity) {
    const station = workstations.find((item) => idOf(item) === identity);
    return station ? `station:${idOf(station)}` : raw;
  }
  return raw;
}

function workstationIdOfSeat(value: AnyRecord) {
  const metadata = value.metadata && typeof value.metadata === "object" ? value.metadata : {};
  const extraData = value.extra_data && typeof value.extra_data === "object" ? value.extra_data : {};
  return text(
    value.workstation_id ??
      value.workstationId ??
      value.development_station_id ??
      value.developmentStationId ??
      metadata.workstation_id ??
      metadata.workstationId ??
      metadata.development_station_id ??
      metadata.developmentStationId ??
      extraData.workstation_id ??
      extraData.development_station_id,
    "",
  );
}

function skillKey(value: AnyRecord) {
  return text(value.skill_id ?? value.skillId ?? value.id ?? value.slug, "").toLowerCase();
}

function forgeTab(value: unknown): ForgeTab {
  const raw = text(value, "").toLowerCase();
  if (raw === "knowledge") return "knowledge";
  if (raw === "git") return "git";
  return "skills";
}

function skillForgeSelfPath(projectId: string, searchParams?: {
  return_to?: string;
  from?: string;
  resources?: string;
  tab?: string;
  focus?: string;
  queue?: string;
}) {
  const query = new URLSearchParams();
  if (searchParams?.resources) query.set("resources", searchParams.resources);
  if (searchParams?.tab) query.set("tab", forgeTab(searchParams.tab));
  if (searchParams?.from) query.set("from", text(searchParams.from, ""));
  if (searchParams?.focus) query.set("focus", text(searchParams.focus, ""));
  if (searchParams?.queue) query.set("queue", text(searchParams.queue, ""));
  if (searchParams?.return_to) query.set("return_to", text(searchParams.return_to, ""));
  const suffix = query.toString();
  return `/projects/${projectId}/skill-forge${suffix ? `?${suffix}` : ""}`;
}

function publicSeedText(value: unknown, maxLength = 180) {
  const next = text(value, "")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "关联记录")
    .replace(/[A-Za-z]:[\\/][^\s"'`<>),\]]+/g, "当前电脑工作副本")
    .replace(/\s+/g, " ")
    .trim();
  return next.length > maxLength ? `${next.slice(0, maxLength - 1)}…` : next;
}

export default async function ProjectSkillForgePage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: {
    return_to?: string;
    from?: string;
    resources?: string;
    seat?: string;
    seat_id?: string;
    workstation?: string;
    workstation_id?: string;
    tab?: string;
    focus?: string;
    queue?: string;
    need_id?: string;
    task_id?: string;
    dispatch_id?: string;
    seed_title?: string;
    seed_summary?: string;
    seed_output?: string;
    seed_receipt?: string;
    team_notice?: string;
    team_error?: string;
  };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(skillForgeSelfPath(projectId, searchParams))}`);
  }

  const projectState = await getProjectState(projectId);
  const project = projectState.data;
  if (!project) {
    return (
      <main className={styles.emptyPage}>
        <p>项目不存在或无权限。</p>
        <Link href="/projects">返回项目列表</Link>
      </main>
    );
  }

  const [skillsState, documentsState, assignmentsState, seatsState, workstationsState, messagesState] = await Promise.all([
    getProjectSkillsState(projectId),
    getProjectKnowledgeDocumentsState(projectId),
    getSeatSkillAssignmentsState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
    getCollaborationMessagesState({ projectId, limit: 160 }),
  ]);

  const config = project.collaboration_config && typeof project.collaboration_config === "object"
    ? (project.collaboration_config as AnyRecord)
    : {};
  const skills = [
    ...DEFAULT_PLATFORM_SKILL_LIBRARY,
    ...asArray<AnyRecord>(config.skill_library ?? config.skillLibrary),
    ...asArray<AnyRecord>(skillsState.data),
  ].filter((skill, index, list) => {
    const id = skillKey(skill);
    return id && list.findIndex((candidate) => skillKey(candidate) === id) === index;
  });
  const documents = asArray<AnyRecord>(documentsState.data);
  const assignments = asArray<AnyRecord>(assignmentsState.data);
  const seats = asArray<AnyRecord>(seatsState.data).filter((item) => isNpcSeatRecord(item));
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const focusSeatId = text(searchParams?.seat ?? searchParams?.seat_id, "");
  const focusWorkstationId = text(searchParams?.workstation ?? searchParams?.workstation_id, "");
  const resourceIds = text(searchParams?.resources, "")
    .split(",")
    .map((item) => {
      try {
        return decodeURIComponent(item.trim());
      } catch {
        return item.trim();
      }
    })
    .filter(Boolean);
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const focusedSeat = focusSeatId ? seats.find((seat) => seatMatchesIdentity(seat, focusSeatId)) ?? null : null;
  const focusedSeatId = focusedSeat ? idOf(focusedSeat) : "";
  const focusedSeatWorkstationId = focusedSeat ? workstationIdOfSeat(focusedSeat) : "";
  const focusedWorkstation = workstations.find((station) => idOf(station) === (focusWorkstationId || focusedSeatWorkstationId)) ?? null;
  const focusedWorkstationId = focusedWorkstation ? idOf(focusedWorkstation) : "";
  const collaborationSeed = {
    source: text(searchParams?.from, "") === "company" ? "company" : "",
    needId: publicSeedText(searchParams?.need_id, 80),
    taskId: publicSeedText(searchParams?.task_id, 80),
    dispatchId: publicSeedText(searchParams?.dispatch_id, 80),
    rawNeedId: text(searchParams?.need_id, ""),
    rawTaskId: text(searchParams?.task_id, ""),
    rawDispatchId: text(searchParams?.dispatch_id, ""),
    title: publicSeedText(searchParams?.seed_title, 96),
    summary: publicSeedText(searchParams?.seed_summary, 180),
    output: publicSeedText(searchParams?.seed_output, 160),
    receipt: publicSeedText(searchParams?.seed_receipt, 160),
  };

  return (
    <SkillForgeClient
      projectId={projectId}
      projectName={text(project.name, "项目")}
      projectRepo={text(project.github_url, "待绑定 GitHub 仓库")}
      returnTo={returnTo}
      returnToLabel={returnTo ? labelProjectReturnPath(returnTo) : ""}
      surfaceNotice={text(searchParams?.team_notice, "")}
      surfaceError={text(searchParams?.team_error, "")}
      skills={skills}
      documents={documents}
      assignments={assignments}
      messages={asArray<AnyRecord>(messagesState.data)}
      seats={seats}
      workstations={workstations}
      initialOpenResourceIds={[
        ...resourceIds.map((item) => normalizeResourceParam(item, seats, workstations)),
        ...(focusedWorkstationId ? [`station:${focusedWorkstationId}`] : []),
        ...(focusedSeatId ? [`seat:${focusedSeatId}`] : []),
      ]}
      initialActiveTab={forgeTab(searchParams?.tab)}
      initialCollaborationSeed={collaborationSeed.source && (collaborationSeed.title || collaborationSeed.summary || collaborationSeed.receipt) ? collaborationSeed : null}
    />
  );
}
