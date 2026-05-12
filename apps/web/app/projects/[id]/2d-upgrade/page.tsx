import { redirect } from "next/navigation";

import {
  getCollaborationMessagesState,
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectMembersState,
  getProjectKnowledgeDocumentsState,
  getProjectSkillsState,
  getSeatSkillAssignmentsState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
  getRequirementsState,
  getTasksDataScopedState,
  getUsageData,
} from "../../../../lib/server-data";
import { normalizeDevelopmentWorkshopStations } from "../../../../lib/development-workshop";
import { Project2dUpgradeGame } from "./project-2d-upgrade-game";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type AnyRecord = Record<string, any>;

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function isDoneStatus(status: unknown) {
  return ["done", "completed", "archived"].includes(String(status ?? "").toLowerCase());
}

function isBlockedStatus(status: unknown) {
  return ["blocked", "failed", "error"].includes(String(status ?? "").toLowerCase());
}

function isOnlineStatus(status: unknown) {
  return ["online", "ready", "active"].includes(String(status ?? "").toLowerCase());
}

function sumUsageCost(entries: AnyRecord[]) {
  return entries.reduce((sum, item) => sum + Number(item.costCny ?? item.cost ?? ((item.cost_cents ?? 0) / 100)), 0);
}

function searchText(value: unknown) {
  if (Array.isArray(value)) return text(value[0], "");
  return text(value, "");
}

function searchParamsQuery(searchParams?: Record<string, string | string[] | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams ?? {})) {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined) params.append(key, item);
      });
    } else if (value !== undefined) {
      params.set(key, value);
    }
  }
  return params.toString();
}

function metadataOf(value: AnyRecord) {
  const metadata = value.metadata;
  return metadata && typeof metadata === "object" && !Array.isArray(metadata) ? (metadata as AnyRecord) : {};
}

function booleanValue(value: unknown, fallback = false) {
  if (typeof value === "boolean") return value;
  const normalized = String(value ?? "").trim().toLowerCase();
  if (["true", "1", "yes", "on", "enabled"].includes(normalized)) return true;
  if (["false", "0", "no", "off", "disabled"].includes(normalized)) return false;
  return fallback;
}

function numberValue(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function numberOrNull(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function stringArray(value: unknown) {
  const source = Array.isArray(value)
    ? value
    : typeof value === "string"
      ? value.split(/[\n,]+/)
      : [];
  return source.map((item) => text(item, "")).filter(Boolean);
}

function isNpcSeat(workstation: AnyRecord) {
  const metadata = metadataOf(workstation);
  const seatType = text(workstation.seat_type ?? metadata.seat_type, "").toLowerCase();
  return seatType === "npc" || seatType === "codex";
}

async function safeLoad<T>(loader: Promise<T>, fallback: T): Promise<T> {
  try {
    return await loader;
  } catch {
    return fallback;
  }
}

export default async function Project2dUpgradePage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const projectState = await getProjectState(params.id);
  const query = searchParamsQuery(searchParams);
  const returnTo = encodeURIComponent(`/projects/${params.id}/2d-upgrade${query ? `?${query}` : ""}`);
  const apiBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8010").trim().replace(/\/$/, "");

  if (projectState.status === 401) {
    redirect(`/login?returnTo=${returnTo}`);
  }
  if (projectState.status === 403) {
    redirect(`/projects?tab=projects&team_error=${encodeURIComponent("当前账号没有这个项目的访问权限，请从项目列表重新进入。")}`);
  }
  if (projectState.status === 404) {
    redirect(`/projects?tab=projects&team_error=${encodeURIComponent("这个项目不存在，或者你没有被授权访问。")}`);
  }

  const [authState, taskState, requirementState, messageState, nodeState, workstationState, projectWorkstationsState, memberState, knowledgeDocumentState, formalSkillState, seatSkillAssignmentState, usage] = await Promise.all([
    safeLoad(getCurrentAuthState(), { data: null, status: 500, error: null }),
    safeLoad(getTasksDataScopedState({ projectIds: [params.id] }), { data: [], status: 500, error: null }),
    safeLoad(getRequirementsState({ projectIds: [params.id] }), { data: [], status: 500, error: null }),
    safeLoad(getCollaborationMessagesState({ projectId: params.id }), { data: [], status: 500, error: null }),
    safeLoad(getProjectComputerNodesState(params.id), { data: [], status: 500, error: null }),
    safeLoad(getProjectThreadWorkstationsState(params.id), { data: [], status: 500, error: null }),
    safeLoad(getProjectWorkstationsState(params.id), { data: [], status: 500, error: null }),
    safeLoad(getProjectMembersState(params.id), { data: [], status: 500, error: null }),
    safeLoad(getProjectKnowledgeDocumentsState(params.id), { data: [], status: 500, error: null }),
    safeLoad(getProjectSkillsState(params.id), { data: [], status: 500, error: null }),
    safeLoad(getSeatSkillAssignmentsState(params.id), { data: [], status: 500, error: null }),
    safeLoad(getUsageData(), []),
  ]);

  const project = (projectState.data ?? {}) as AnyRecord;
  const collaborationConfig =
    project.collaboration_config && typeof project.collaboration_config === "object" && !Array.isArray(project.collaboration_config)
      ? (project.collaboration_config as AnyRecord)
      : {};
  const legacyProjectSkills = Array.isArray(collaborationConfig.skill_library) ? (collaborationConfig.skill_library as AnyRecord[]) : [];
  const formalProjectSkills = Array.isArray(formalSkillState.data) ? formalSkillState.data : [];
  const projectSkills = [
    ...formalProjectSkills.map((skill) => ({
      ...skill,
      id: skill.skill_id ?? skill.id,
      label: skill.label ?? skill.name,
      note: skill.description ?? skill.note,
      source: skill.source ?? "formal",
      metadata: {
        ...(skill.metadata && typeof skill.metadata === "object" ? skill.metadata : {}),
        ...(skill.extra_data && typeof skill.extra_data === "object" ? skill.extra_data : {}),
        repo_relative_path: skill.repo_relative_path ?? null,
        exists_in_repo: skill.exists_in_repo ?? null,
        last_synced_at: skill.last_synced_at ?? null,
        formal_resource_id: skill.id,
      },
    })),
    ...legacyProjectSkills.filter((legacy) => {
      const legacyId = text(legacy.id ?? legacy.skill_id, "").toLowerCase();
      return legacyId && !formalProjectSkills.some((formal) => text(formal.skill_id ?? formal.id, "").toLowerCase() === legacyId);
    }),
  ];
  const inheritedSkillsByNode = new Map<string, string[]>();
  const inheritedSkillsByWorkstation = new Map<string, string[]>();
  const workstationProfiles =
    collaborationConfig.workstation_profiles && typeof collaborationConfig.workstation_profiles === "object"
      ? (collaborationConfig.workstation_profiles as AnyRecord)
      : {};
  for (const [nodeId, profile] of Object.entries(workstationProfiles)) {
    if (profile && typeof profile === "object") {
      const inh = stringArray((profile as AnyRecord).skill_inheritance ?? (profile as AnyRecord).skillInheritance);
      if (inh.length) inheritedSkillsByNode.set(String(nodeId), inh);
      if (inh.length) inheritedSkillsByWorkstation.set(String(nodeId), inh);
    }
  }
  const tasks = Array.isArray(taskState.data) ? taskState.data : [];
  const requirements = Array.isArray(requirementState.data) ? requirementState.data : [];
  const messages = Array.isArray(messageState.data) ? messageState.data : [];
  const nodes = Array.isArray(nodeState.data) ? nodeState.data : [];
  const workstations = Array.isArray(workstationState.data) ? workstationState.data : [];
  const projectWorkstations = Array.isArray(projectWorkstationsState.data) ? projectWorkstationsState.data : [];
  const projectWorkstationNameById = new Map<string, string>();
  for (const ws of projectWorkstations) {
    const id = String(ws.id ?? "");
    if (id) projectWorkstationNameById.set(id, String(ws.name ?? id));
  }
  const members = Array.isArray(memberState.data) ? memberState.data : [];
  const knowledgeDocuments = Array.isArray(knowledgeDocumentState.data) ? knowledgeDocumentState.data : [];
  const seatSkillAssignments = Array.isArray(seatSkillAssignmentState.data) ? seatSkillAssignmentState.data : [];
  const skillAssignedSeatIds = new Map<string, string[]>();
  const skillDraftSeatIds = new Map<string, string[]>();
  for (const assignment of seatSkillAssignments) {
    const skillId = text(assignment.skill_id, "");
    const seatId = text(assignment.seat_id, "");
    const status = text(assignment.status, "active").toLowerCase();
    if (!skillId || !seatId) continue;
    const targetMap = status === "draft" ? skillDraftSeatIds : skillAssignedSeatIds;
    const list = targetMap.get(skillId) ?? [];
    list.push(seatId);
    targetMap.set(skillId, list);
  }
  const knowledgeByOwner = new Map<string, AnyRecord[]>();
  for (const doc of knowledgeDocuments) {
    const ownerKey = `${text(doc.owner_type, "")}:${text(doc.owner_id, "")}`;
    if (!knowledgeByOwner.has(ownerKey)) knowledgeByOwner.set(ownerKey, []);
    knowledgeByOwner.get(ownerKey)!.push(doc);
  }
  const skillsBySeat = new Map<string, string[]>();
  for (const assignment of seatSkillAssignments) {
    const seatId = text(assignment.seat_id, "");
    const skillId = text(assignment.skill_id, "");
    if (!seatId || !skillId || text(assignment.status, "active") !== "active") continue;
    const list = skillsBySeat.get(seatId) ?? [];
    list.push(skillId);
    skillsBySeat.set(seatId, list);
  }
  const workshopStationRows = normalizeDevelopmentWorkshopStations(collaborationConfig.development_workshop_stations);
  const activeTasks = tasks.filter((task) => !isDoneStatus(task.status));
  const blockedTasks = tasks.filter((task) => isBlockedStatus(task.status));
  const onlineNodes = nodes.filter((node) => isOnlineStatus(node.runner_effective_status ?? node.runner_status ?? node.status));
  const npcSeatRows = workstations.filter(isNpcSeat);
  const sourceWorkstations = workstations.filter((workstation) => !isNpcSeat(workstation));
  const selectableWorkstations = sourceWorkstations.length ? sourceWorkstations : workstations;
  const sortedMessages = messages
    .slice()
    .sort((a, b) => {
      const bt = new Date(String(b.created_at ?? b.updated_at ?? 0)).getTime();
      const at = new Date(String(a.created_at ?? a.updated_at ?? 0)).getTime();
      return bt - at;
    });
  const recentAndGitMessages = [
    ...sortedMessages.slice(0, 8),
    ...sortedMessages.filter((message) => /git|回退|rollback|对齐/i.test(`${message.message_type ?? message.type ?? ""} ${message.title ?? ""} ${message.body ?? message.content ?? message.summary ?? ""}`)),
  ].filter((message, index, list) => {
    const id = text(message.id ?? message.message_id, "");
    return !id || list.findIndex((candidate) => text(candidate.id ?? candidate.message_id, "") === id) === index;
  });
  const recentMessages = recentAndGitMessages
    .slice(0, 40)
    .map((message, index) => ({
      id: text(message.id ?? message.message_id, `message-${index + 1}`),
      title: text(message.title ?? message.subject, ""),
      type: text(message.message_type ?? message.type, "协作消息"),
      body: text(message.content ?? message.body ?? message.summary, "平台收到一条协作动态，等待线程回执。"),
      status: text(message.status, "new"),
      at: text(message.created_at ?? message.updated_at, ""),
      providerId: text(message.sender_id ?? message.senderId, ""),
      sourceWorkstationId: text(message.recipient_id ?? message.recipientId, ""),
      knowledgeSummary: JSON.stringify(message.extra_data ?? message.metadata ?? {}),
    }));

  return (
    <Project2dUpgradeGame
      project={{
        id: text(project.id, params.id),
        name: text(project.name ?? project.project_name, `项目 ${params.id.slice(0, 8)}`),
        description: text(project.description, "小A工作室 2D 开发者模式升级入口，聚合项目、NPC、电脑、线程与协作回执。"),
        type: text(project.project_type, "software"),
        collaboration_config: collaborationConfig,
        github_url: text(project.github_url, ""),
        local_git_url: text(project.local_git_url, ""),
        default_branch: text(project.default_branch, "main"),
        develop_branch: text(project.develop_branch, "develop"),
      }}
      apiBaseUrl={apiBaseUrl}
      currentUser={{
        name: text((authState.data as AnyRecord | null)?.user?.name, "小A操作者"),
        email: text((authState.data as AnyRecord | null)?.user?.email, ""),
      }}
      stats={{
        requirementCount: requirements.length,
        taskCount: tasks.length,
        activeTaskCount: activeTasks.length,
        blockedTaskCount: blockedTasks.length,
        onlineComputerCount: onlineNodes.length,
        computerCount: nodes.length,
        messageCount: messages.length,
        tokenSpend: sumUsageCost(Array.isArray(usage) ? usage : []).toFixed(2),
      }}
      tasks={tasks.slice(0, 8).map((task, index) => ({
        id: text(task.id ?? task.task_id, `task-${index + 1}`),
        title: text(task.title ?? task.name, `开发任务 ${index + 1}`),
        status: text(task.status, "todo"),
        body: text(task.description ?? task.summary, ""),
        providerId: text(task.branch ?? task.git_branch, ""),
      }))}
      requirements={requirements.slice(0, 8).map((requirement, index) => ({
        id: text(requirement.id ?? requirement.requirement_id, `requirement-${index + 1}`),
        title: text(requirement.title ?? requirement.name, `需求 ${index + 1}`),
        status: text(requirement.status, "open"),
      }))}
      messages={recentMessages}
      computers={nodes.slice(0, 8).map((node, index) => ({
        id: text(node.id ?? node.node_id, `computer-${index + 1}`),
        name: text(node.name ?? node.label, `电脑 ${index + 1}`),
        type: text(node.connection_kind ?? node.connectionKind, "runner"),
        status: text(node.runner_effective_status ?? node.runner_status ?? node.status, "offline"),
        body: [
          text(node.runner_name, ""),
          node.runner_heartbeat_age_seconds !== null && node.runner_heartbeat_age_seconds !== undefined
            ? `心跳 ${node.runner_heartbeat_age_seconds}s 前`
            : "",
          text(node.runner_watch_detail, ""),
          text(node.desktop_bridge_label, ""),
          text(node.host, ""),
          text(node.os, ""),
          text(node.workspace_root ?? node.git_root, ""),
        ].filter(Boolean).join(" / "),
        at: text(node.runner_last_heartbeat_at, ""),
        providerId: text(node.runner_id, ""),
        runnerId: text(node.runner_id, ""),
        runnerWatchState: text(node.runner_watch_state, ""),
        runnerEffectiveStatus: text(node.runner_effective_status ?? node.runner_status ?? node.status, "offline"),
        threadScanCount: numberValue(node.thread_scan_count ?? node.threadScanCount, 0),
        desktopProcessDetected: booleanValue(node.desktop_process_detected ?? node.desktopProcessDetected, false),
        desktopBridgeConnected: booleanValue(node.desktop_bridge_connected ?? node.desktopBridgeConnected, false),
        desktopDeliveryMode: text(node.desktop_delivery_mode ?? node.desktopDeliveryMode, ""),
        desktopBridgeLabel: text(node.desktop_bridge_label ?? node.desktopBridgeLabel, ""),
        desktopBridgeNote: text(node.desktop_bridge_note ?? node.desktopBridgeNote, ""),
      }))}
      projectWorkstations={projectWorkstations.map((ws) => ({
        id: String(ws.id ?? ""),
        configId: String(ws.config_id ?? ws.id ?? ""),
        name: String(ws.name ?? ""),
        description: ws.description ? String(ws.description) : null,
        leadSeatId: ws.lead_seat_id ? String(ws.lead_seat_id) : null,
        reviewPolicy: ws.review_policy ? String(ws.review_policy) : null,
        sortOrder: Number(ws.sort_order ?? 0) || 0,
        seatCount: Number(ws.seat_count ?? 0) || 0,
      }))}
      projectMembers={members.slice(0, 24).map((member, index) => {
        const user = member.user && typeof member.user === "object" ? (member.user as AnyRecord) : {};
        const role = text(member.role, member.is_owner ? "owner" : "member");
        return {
          id: text(member.id ?? member.user_id ?? user.id, `member-${index + 1}`),
          name: text(member.display_name ?? member.name ?? user.display_name ?? user.name ?? user.email ?? member.email, `项目成员 ${index + 1}`),
          type: role,
          status: text(member.status, member.is_owner ? "owner" : "active"),
          body: text(member.email ?? user.email, ""),
          permissionLevel: member.is_owner ? "owner" : role,
        };
      })}
      workstations={selectableWorkstations.slice(0, 48).map((workstation, index) => ({
        id: text(workstation.id ?? workstation.workstation_id ?? workstation.thread_id, `workstation-${index + 1}`),
        name: text(workstation.name ?? workstation.workstation_name ?? workstation.thread_name, `线程 ${index + 1}`),
        type: text(workstation.ai_provider_id ?? workstation.ai_provider ?? workstation.provider, "thread"),
        status: text(workstation.status, "idle"),
        body: text(workstation.description ?? workstation.responsibility ?? workstation.notes, ""),
        computerNodeId: text(workstation.computer_node_id ?? metadataOf(workstation).computer_node_id, ""),
        model: text(workstation.model ?? metadataOf(workstation).model, ""),
      }))}
      npcSeats={npcSeatRows.slice(0, 12).map((workstation, index) => {
        const metadata = metadataOf(workstation);
        const npcKnowledge = metadata.npc_knowledge && typeof metadata.npc_knowledge === "object" ? (metadata.npc_knowledge as AnyRecord) : {};
        const providerId = text(workstation.ai_provider_id ?? metadata.ai_provider_id ?? metadata.provider_id, "npc");
        const workstationId = text(workstation.workstation_id ?? metadata.workstation_id, "");
        const workstationName = workstationId ? projectWorkstationNameById.get(workstationId) ?? "" : "";
        const seatId = text(workstation.id ?? workstation.row_id ?? workstation.config_id, "");
        const formalSkillLoadout = [
          ...(skillsBySeat.get(seatId) ?? []),
          ...(skillsBySeat.get(text(workstation.config_id, "")) ?? []),
        ].filter(Boolean);
        const formalKnowledgeDocs = [
          ...(knowledgeByOwner.get(`seat:${seatId}`) ?? []),
          ...(knowledgeByOwner.get(`seat:${text(workstation.config_id, "")}`) ?? []),
        ];
        const formalKnowledgeSummary = formalKnowledgeDocs.length
          ? `GitHub 知识文档：${formalKnowledgeDocs.map((doc) => text(doc.repo_relative_path, "")).filter(Boolean).slice(0, 3).join(" / ")}${formalKnowledgeDocs.length > 3 ? ` 等 ${formalKnowledgeDocs.length} 份` : ""}`
          : "";
        return {
          id: text(workstation.id ?? workstation.workstation_id ?? workstation.thread_id, `npc-${index + 1}`),
          rowId: text(workstation.row_id ?? workstation.rowId, ""),
          name: text(workstation.name ?? workstation.workstation_name ?? workstation.thread_name, `NPC ${index + 1}`),
          type: text(workstation.seat_type ?? metadata.seat_type ?? providerId, "npc"),
          status: text(workstation.status, "idle"),
          body: text(workstation.description ?? workstation.responsibility ?? metadata.responsibility ?? workstation.notes, ""),
          providerId,
          providerLabel: text(workstation.ai_provider ?? metadata.ai_provider ?? metadata.provider_label, providerId),
          workstationId,
          workstationName,
          computerNodeId: text(workstation.computer_node_id ?? metadata.computer_node_id, ""),
          sourceWorkstationId: text(workstation.source_workstation_id ?? metadata.source_workstation_id, ""),
          responsibility: text(workstation.responsibility ?? metadata.responsibility ?? workstation.description, ""),
          model: text(workstation.model ?? metadata.model, "gpt-5.4"),
          permissionLevel: text(workstation.permission_level ?? metadata.permission_level, "L2"),
          automationEnabled: booleanValue(metadata.automation_enabled, false),
          automationHeartbeatSeconds: numberValue(metadata.automation_heartbeat_seconds, 900),
          scene: text(workstation.scene_key ?? metadata.scene ?? metadata.scene_key, "unity-2d-upgrade"),
          avatarKey: text(workstation.sprite_key ?? metadata.avatar_key ?? metadata.sprite_key, "a-agent-lab-npc"),
          mapX: numberOrNull(workstation.x ?? metadata.map_x ?? metadata.x),
          mapY: numberOrNull(workstation.y ?? metadata.map_y ?? metadata.y),
          skillLoadout: Array.from(new Set([...stringArray(workstation.skill_loadout ?? metadata.skill_loadout), ...formalSkillLoadout])),
          inheritedSkills: (() => {
            const node = text(workstation.computer_node_id ?? metadata.computer_node_id, "");
            const logicalWorkstation = text(workstation.workstation_id ?? metadata.workstation_id, "");
            return logicalWorkstation
              ? (inheritedSkillsByWorkstation.get(logicalWorkstation) ?? [])
              : node
                ? (inheritedSkillsByNode.get(node) ?? [])
                : [];
          })(),
          knowledgeSummary: text(npcKnowledge.summary ?? metadata.knowledge_summary, formalKnowledgeSummary),
          knowledgeHandoffPath: text(npcKnowledge.handoff_path ?? metadata.knowledge_handoff_path, ""),
        };
      })}
      workshopStations={workshopStationRows.slice(0, 24).map((station) => ({
        id: station.id,
        label: station.label,
        icon: station.icon,
        station: station.station,
        mapScene: station.mapScene,
        mapLocation: station.mapLocation,
        detail: station.detail,
        modes: station.modes,
        backendAnchor: station.backendAnchor,
        runnerCapabilities: station.runnerCapabilities,
        aiResponsibilities: station.aiResponsibilities,
        npcRoleTemplates: station.npcRoleTemplates,
        assignmentKeywords: station.assignmentKeywords,
        nextActions: station.nextActions,
        approvalPolicy: station.approvalPolicy,
        riskLevel: station.riskLevel,
        assignedNpcIds: station.assignedNpcIds,
        knowledgeSummary: station.knowledgeBase.summary,
        knowledgeHandoffPath: station.knowledgeBase.handoffPath,
        knowledgeTags: station.knowledgeBase.tags,
      }))}
      skills={projectSkills.map((skill, index) => {
        const metadata = metadataOf(skill);
        const skillId = text(skill.skill_id ?? skill.id ?? skill.slug, `skill-${index + 1}`);
        const repoPath = text(metadata.repo_relative_path ?? skill.repo_relative_path, "");
        const repoNote = repoPath ? `GitHub 路径：${repoPath}${metadata.exists_in_repo === true || skill.exists_in_repo === true ? " / 已确认存在" : ""}` : "";
        const draftStatus = text(metadata.draft_status, "");
        const assignedSeatIds = [
          ...(skillAssignedSeatIds.get(skillId) ?? []),
          ...(skillDraftSeatIds.get(skillId) ?? []),
        ];
        return {
          id: skillId,
          skillId,
          rowId: text(skill.row_id ?? skill.formal_resource_id ?? metadata.formal_resource_id, ""),
          name: text(skill.name ?? skill.title ?? skill.label, `Skill ${index + 1}`),
          type: text(skill.category ?? skill.source ?? skill.type, "项目 Skill"),
          source: text(skill.source ?? skill.type, ""),
          category: text(skill.category ?? metadata.category, ""),
          status: draftStatus || text(skill.status, "available"),
          body: [text(skill.note ?? skill.description ?? skill.summary ?? skill.instructions, ""), repoNote].filter(Boolean).join(" ｜ "),
          repoRelativePath: repoPath,
          draftStatus,
          authorSeatId: text(metadata.author_seat_id, ""),
          assignedSeatIds,
        };
      })}
      knowledgeDocuments={knowledgeDocuments.map((doc, index) => ({
        id: text(doc.id, `knowledge-${index + 1}`),
        title: text(doc.title, `知识文档 ${index + 1}`),
        repoRelativePath: text(doc.repo_relative_path, ""),
        scope: text(doc.scope, "project"),
        ownerType: text(doc.owner_type, ""),
        ownerId: text(doc.owner_id, ""),
        existsInRepo: doc.exists_in_repo === true ? true : doc.exists_in_repo === false ? false : null,
        versionRef: text(doc.version_ref, ""),
        lastSyncedAt: text(doc.last_synced_at, ""),
        summary: text(doc.summary, ""),
        tags: stringArray(doc.tags),
      }))}
      teamNotice={searchText(searchParams?.team_notice)}
      teamError={searchText(searchParams?.team_error)}
    />
  );
}
