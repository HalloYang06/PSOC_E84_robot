import { redirect } from "next/navigation";
import Link from "next/link";
import {
  getCurrentAuthState,
  getCollaborationMessagesState,
  getProjectComputerNodesState,
  getProjectState,
  getProjectWorkstationsState,
} from "../../../../lib/server-data";
import { isNpcSeatRecord, platformProviderIdFromSeat } from "../../../../lib/platform-provider";
import styles from "./company.module.css";

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

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? (value as AnyRecord) : {};
}

function firstText(...values: unknown[]) {
  for (const value of values) {
    const next = text(value, "");
    if (next) return next;
  }
  return "";
}

function deriveThreadKind(providerId: string, threadId: string) {
  const raw = `${providerId} ${threadId}`.toLowerCase();
  if (raw.includes("claude")) return "Claude Code";
  if (raw.includes("codex")) return "Codex";
  return providerId || "thread";
}

function publicThreadState(value: unknown, automationEnabled = false) {
  const raw = text(value, "").toLowerCase();
  if (/online|ready|ok|watcher ready|connected|active/.test(raw)) return "可接单";
  if (/stale|timeout|delay/.test(raw)) return "可能延迟";
  if (/offline|lost|failed|error/.test(raw)) return "需重连";
  return automationEnabled ? "已绑定，待电脑接单" : "待接入";
}

function publicComputerDispatchState(node: AnyRecord | undefined) {
  if (!node) return "状态未知";
  const watchState = text(node.runner_watch_state ?? node.runnerWatchState, "").toLowerCase();
  const effectiveStatus = text(
    node.runner_effective_status ?? node.runnerEffectiveStatus ?? node.runner_status ?? node.runnerStatus ?? node.status,
    "",
  ).toLowerCase();
  if (watchState === "watching" || /watching|online|ready|active|connected/.test(effectiveStatus)) return "可接单";
  if (/stale|timeout|delay|recent/.test(watchState) || /stale|timeout|delay|recent/.test(effectiveStatus)) return "可能延迟";
  if (/offline|lost|failed|error|runner_offline|missing/.test(watchState) || /offline|lost|failed|error/.test(effectiveStatus)) return "需重连";
  return "状态未知";
}

function publicStatusLabel(value: unknown) {
  const raw = text(value, "").toLowerCase();
  if (/completed|done|success|resolved/.test(raw)) return "已完成";
  if (/delivered|acked|accepted|queued/.test(raw)) return "已送达";
  if (/running|progress|active|pending/.test(raw)) return "处理中";
  if (/failed|error|blocked|rejected/.test(raw)) return "待处理";
  return text(value, "已记录");
}

function reviewPolicyLabel(value: unknown) {
  const raw = text(value, "inherit").toLowerCase();
  if (/strict|always|manual|required/.test(raw)) return "强审";
  if (/trusted|auto|bypass|allow/.test(raw)) return "免审边界";
  return "继承工位策略";
}

function orgEventTypeLabel(value: unknown) {
  const raw = text(value, "").toLowerCase();
  if (/agent_result|final|reply|receipt/.test(raw)) return "回执";
  if (/agent_command|runner_command|dispatch/.test(raw)) return "派单事件";
  if (/runner_command|dispatch/.test(raw)) return "派单事件";
  if (/review|approval/.test(raw)) return "审核事件";
  if (/desktop|question/.test(raw)) return "桌面消息";
  if (/requirement|need/.test(raw)) return "协作需求";
  if (/progress|ack|running/.test(raw)) return "进度";
  return text(value, "组织事件");
}

function knowledgeLabel(seat: { knowledgeSummary: string; workstationKnowledgePath: string }) {
  if (seat.knowledgeSummary) return seat.knowledgeSummary;
  if (seat.workstationKnowledgePath) return "工位知识库已配置";
  return "待绑定知识库";
}

function safeProjectReturnPath(projectId: string, value: unknown) {
  const raw = text(value, "");
  if (!raw.startsWith(`/projects/${projectId}/`)) return "";
  if (/^\/\//.test(raw) || raw.includes("\\") || raw.includes("://")) return "";
  return raw;
}

function labelProjectReturnPath(value: string) {
  if (value.includes("/2d-upgrade")) return "← 返回主页面";
  if (value.includes("/datasets")) return "← 返回数据工场";
  if (value.includes("/ai-lab")) return "← 返回 AI 实验室";
  if (value.includes("/robotics")) return "← 返回机器人现场";
  if (value.includes("/observability")) return "← 返回观测台";
  if (value.includes("/skill-forge")) return "← 返回 Skill 工坊";
  if (value.includes("/workbench")) return "← 返回工作台";
  if (value.includes("/company")) return "← 返回公司层";
  return "← 返回来源";
}

export default async function CompanyPage({ params, searchParams }: { params: { id: string }; searchParams?: { embed?: string; return_to?: string; from?: string } }) {
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    const query = new URLSearchParams();
    if (searchParams?.return_to) query.set("return_to", searchParams.return_to);
    if (searchParams?.from) query.set("from", searchParams.from);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${params.id}/company${suffix}`)}`);
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

  const [computerNodesState, projectWorkstationsState, collaborationMessagesState] = await Promise.all([
    getProjectComputerNodesState(params.id),
    getProjectWorkstationsState(params.id),
    getCollaborationMessagesState({ projectId: params.id }),
  ]);
  const liveNodes = asArray<AnyRecord>(computerNodesState.data);
  const projectWorkstations = asArray<AnyRecord>(projectWorkstationsState.data);

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
  const nodeStateMap = new Map<string, AnyRecord>();
  for (const node of [...configNodes, ...liveNodes]) {
    const id = text(node?.id ?? node?.node_id, "");
    if (!id) continue;
    const name = text(node?.name ?? node?.label ?? node?.hostname ?? id, id);
    nodeMap.set(id, name);
    nodeStateMap.set(id, node);
  }

  const workstationNameById = new Map<string, string>();
  const leadByWorkstation = new Map<string, string>();
  for (const ws of projectWorkstations) {
    const wsId = text(ws?.id, "");
    if (!wsId) continue;
    workstationNameById.set(wsId, text(ws?.name, wsId));
    const lead = text(ws?.lead_seat_id ?? ws?.leadSeatId, "");
    if (lead) leadByWorkstation.set(wsId, lead);
  }

  const leadByNode = new Map<string, string>();
  const inheritedSkillsByNode = new Map<string, string[]>();
  const knowledgePathByNode = new Map<string, string>();
  for (const [nodeId, profile] of Object.entries(workstationProfiles)) {
    if (profile && typeof profile === "object") {
      const p = profile as AnyRecord;
      const lead = text(p.lead_seat_id ?? p.leadSeatId, "");
      if (lead) leadByNode.set(String(nodeId), lead);
      const inh = asArray<string>(p.skill_inheritance ?? p.skillInheritance)
        .map((s) => String(s).trim())
        .filter(Boolean);
      if (inh.length) inheritedSkillsByNode.set(String(nodeId), inh);
      const kp = text(p.knowledge_path ?? p.knowledgePath, "");
      if (kp) knowledgePathByNode.set(String(nodeId), kp);
    }
  }

  const allSeats = seatRecords.map((seat, index) => {
    const id = text(seat.id ?? seat.config_id ?? seat.row_id, `seat-${index}`);
    const name = text(seat.name ?? seat.title, `NPC ${index + 1}`);
    const workstationId = text(seat.workstation_id ?? seat.workstationId, "");
    const computerNodeId = text(seat.computer_node_id ?? seat.computerNodeId, "");
    const providerId = platformProviderIdFromSeat(seat) || text(seat.provider_id ?? seat.providerId, "");
    const providerLabel = text(seat.provider_label ?? seat.providerLabel ?? providerId, providerId);
    const responsibility = text(seat.responsibility ?? seat.body, "待分配职责");
    const skillLoadout = asArray<string>(seat.skill_loadout ?? seat.skillLoadout).map((s) => String(s)).filter(Boolean);
    const inheritedSkills = computerNodeId ? (inheritedSkillsByNode.get(computerNodeId) ?? []) : [];
    const workstationKnowledgePath = computerNodeId
      ? (knowledgePathByNode.get(computerNodeId) ?? `docs/workstations/${computerNodeId}.md`)
      : "";
    const knowledgeSummary = text(seat.knowledge_summary ?? seat.knowledgeSummary, "");
    const model = text(seat.model, "");
    const permissionLevel = text(seat.permission_level ?? seat.permissionLevel, "");
    const meta = record(seat.metadata);
    const extra = record(seat.extra_data ?? seat.extraData);
    const automationEnabled = Boolean(
      seat.automation_enabled
      ?? seat.automationEnabled
      ?? meta.automation_enabled
      ?? meta.automationEnabled
      ?? extra.automation_enabled
      ?? extra.automationEnabled
      ?? false,
    );
    const adapter = record(meta.adapter ?? extra.adapter);
    const threadId = firstText(
      seat.target_thread_id,
      seat.targetThreadId,
      seat.session_id,
      seat.sessionId,
      seat.thread_id,
      seat.threadId,
      seat.source_workstation_id,
      seat.sourceWorkstationId,
      meta.target_thread_id,
      meta.targetThreadId,
      meta.session_id,
      meta.sessionId,
      meta.claude_session_id,
      meta.codex_thread_id,
      meta.thread_id,
      meta.threadId,
      meta.source_thread_id,
      meta.bound_thread_id,
      meta.source_workstation_id,
      extra.target_thread_id,
      extra.session_id,
      extra.thread_id,
      extra.source_thread_id,
      extra.bound_thread_id,
      extra.source_workstation_id,
    );
    const threadKind = firstText(seat.thread_kind, seat.threadKind, meta.thread_kind, meta.threadKind, adapter.kind, deriveThreadKind(providerId, threadId));
    const threadHealth = firstText(
      seat.bridge_health_label,
      seat.bridgeHealthLabel,
      seat.thread_health,
      seat.threadHealth,
      meta.bridge_health_label,
      meta.bridgeHealthLabel,
      meta.thread_health,
      meta.threadHealth,
      adapter.health,
      adapter.status,
      automationEnabled ? "watcher ready" : "待接入",
    );
    const dispatchState = computerNodeId ? publicComputerDispatchState(nodeStateMap.get(computerNodeId)) : "待接入";
    const gitUserName = text(meta.git_user_name ?? meta.gitUserName, name);
    const gitUserEmail = text(
      meta.git_user_email ?? meta.gitUserEmail,
      `bot+${id}@noreply.invalid`,
    );
    const reviewPolicy = text(meta.review_policy ?? meta.reviewPolicy, "inherit");
    const leadSeatId = workstationId
      ? (leadByWorkstation.get(workstationId) ?? "")
      : (computerNodeId ? (leadByNode.get(computerNodeId) ?? "") : "");
    const isLead = !!leadSeatId && leadSeatId === id;
    return {
      id,
      name,
      workstationId,
      workstationName: workstationId ? (workstationNameById.get(workstationId) ?? workstationId) : "",
      computerNodeId,
      computerNodeName: computerNodeId ? nodeMap.get(computerNodeId) ?? computerNodeId : "",
      providerId,
      providerLabel,
      threadId,
      threadKind,
      threadHealth,
      dispatchState,
      codexLaunchPrompt: text(meta.codex_launch_prompt ?? meta.codexLaunchPrompt, ""),
      metadata: meta,
      responsibility,
      skillLoadout,
      inheritedSkills,
      workstationKnowledgePath,
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

  const seatsByWorkstation = new Map<string, typeof allSeats>();
  for (const seat of allSeats) {
    const key = seat.workstationId || "unassigned";
    seatsByWorkstation.set(key, [...(seatsByWorkstation.get(key) ?? []), seat]);
  }
  const workstationRows = [
    ...projectWorkstations.map((ws, index) => {
      const id = text(ws.id, `workstation-${index + 1}`);
      const seats = seatsByWorkstation.get(id) ?? [];
      const leadId = text(ws.lead_seat_id ?? ws.leadSeatId, "");
      const lead = allSeats.find((seat) => seat.id === leadId);
      return {
        id,
        name: text(ws.name, `工位 ${index + 1}`),
        description: text(ws.description ?? ws.summary, "负责一类长期工作，不绑定具体电脑。"),
        seats,
        leadName: lead?.name ?? "待指定",
      };
    }),
    ...(seatsByWorkstation.get("unassigned")?.length
      ? [{
          id: "unassigned",
          name: "未归属员工",
          description: "这些 NPC 还需要分配到逻辑工位，之后才能稳定继承职责、知识库和审核策略。",
          seats: seatsByWorkstation.get("unassigned") ?? [],
          leadName: "待指定",
        }]
      : []),
  ];
  const selectedWorkstation = workstationRows[0] ?? {
    id: "empty",
    name: "待创建工位",
    description: "先在主页面创建 NPC 和工位，再回到公司层治理组织结构。",
    seats: [] as typeof allSeats,
    leadName: "待指定",
  };
  const selectedSeats = selectedWorkstation.seats;
  const primarySeat = selectedSeats[0] ?? allSeats[0] ?? null;
  const threadReadyCount = allSeats.filter((seat) => seat.dispatchState === "可接单").length;
  const strictReviewCount = allSeats.filter((seat) => reviewPolicyLabel(seat.reviewPolicy) === "强审").length;
  const skillAssignedCount = allSeats.filter((seat) => seat.skillLoadout.length || seat.inheritedSkills.length).length;
  const knowledgeAssignedCount = allSeats.filter((seat) => seat.knowledgeSummary || seat.workstationKnowledgePath).length;

  const returnToPath = safeProjectReturnPath(params.id, searchParams?.return_to);

  const recentOrgEvents = asArray<AnyRecord>(collaborationMessagesState.data).slice(0, 6);
  const projectId = String(project.id ?? params.id);
  const selfPath = `/projects/${projectId}/company`;

  return (
    <main className={styles.shell} data-embedded={searchParams?.embed === "drawer" ? "1" : undefined}>
      <nav className={styles.topNav} aria-label="公司层导航">
        <Link href={`/projects/${projectId}`}>主页面</Link>
        <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=company`}>NPC 工作台</Link>
        <Link href={`/projects/${projectId}/skill-forge?return_to=${encodeURIComponent(selfPath)}&from=company`}>能力工坊</Link>
        <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=company`}>观测台</Link>
        {returnToPath ? <Link href={returnToPath}>{labelProjectReturnPath(returnToPath)}</Link> : null}
      </nav>

      <header className={styles.header}>
        <div>
          <span>公司层 / 员工表</span>
          <h1>{text(project.name, "AI 合作平台")} 组织结构</h1>
          <p>公司层只负责工位、NPC 员工表、职责边界、Skill/知识库和审核策略；线程绑定和电脑接入仍回主页面管理。</p>
        </div>
        <section className={styles.statusStrip} aria-label="组织状态">
          <article><span>工位</span><strong>{workstationRows.length}</strong><small>逻辑部门</small></article>
          <article><span>NPC</span><strong>{allSeats.length}</strong><small>员工表</small></article>
          <article><span>可接单</span><strong>{threadReadyCount}/{allSeats.length || 0}</strong><small>线程状态</small></article>
          <article><span>强审</span><strong>{strictReviewCount}</strong><small>安全策略</small></article>
        </section>
      </header>

      <section className={styles.layout}>
        <aside className={styles.leftRail} aria-label="工位列表">
          <div className={styles.railHead}>
            <span>工位列表</span>
            <Link href={`/projects/${projectId}`}>管理工位</Link>
          </div>
          <div className={styles.workstationList}>
            {workstationRows.map((ws, index) => (
              <article key={ws.id} data-active={index === 0 ? "1" : undefined}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{ws.name}</strong>
                <p>{ws.description}</p>
                <small>工位长：{ws.leadName} · NPC {ws.seats.length}</small>
              </article>
            ))}
          </div>
        </aside>

        <section className={styles.centerPane} aria-label="NPC 员工表">
          <div className={styles.toolbar}>
            <div>
              <span>当前工位</span>
              <strong>{selectedWorkstation.name}</strong>
            </div>
            <div className={styles.toolbarActions}>
              <Link href={`/projects/${projectId}`}>创建 / 绑定 NPC</Link>
              <Link href={`/projects/${projectId}/skill-forge?return_to=${encodeURIComponent(selfPath)}&from=company`}>补 Skill</Link>
              <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=company`}>看证据</Link>
            </div>
          </div>

          <div className={styles.employeeTable} role="table" aria-label="NPC 员工表">
            <div className={styles.tableHead} role="row">
              <span>NPC</span>
              <span>职责</span>
              <span>能力/知识</span>
              <span>审核</span>
              <span>执行状态</span>
            </div>
            {(selectedSeats.length ? selectedSeats : allSeats).map((seat) => (
              <article key={seat.id} className={styles.tableRow} role="row">
                <div>
                  <strong>{seat.name}</strong>
                  <small>{seat.isLead ? "工位长" : seat.workstationName || "待归属"}</small>
                </div>
                <p>{seat.responsibility}</p>
                <div>
                  <strong>{seat.skillLoadout.length + seat.inheritedSkills.length || 0} 项</strong>
                  <small>{knowledgeLabel(seat)}</small>
                </div>
                <div>
                  <strong>{reviewPolicyLabel(seat.reviewPolicy)}</strong>
                  <small>{seat.permissionLevel || "继承权限"}</small>
                </div>
                <div>
                  <strong>{seat.dispatchState}</strong>
                  <small>{seat.dispatchState === "可接单" ? seat.threadKind || "线程待确认" : "先让电脑持续接单"}</small>
                </div>
              </article>
            ))}
            {!allSeats.length ? (
              <article className={styles.emptyRow}>
                <strong>还没有 NPC 员工</strong>
                <p>先在主页面创建 NPC、扫描线程并绑定，再回公司层分配职责和审核策略。</p>
              </article>
            ) : null}
          </div>
        </section>

        <aside className={styles.rightRail} aria-label="员工属性和策略">
          <details open>
            <summary><span>员工属性</span><strong>{primarySeat?.name ?? "待选择"}</strong></summary>
            {primarySeat ? (
              <div className={styles.drawerBody}>
                <article><span>职责边界</span><p>{primarySeat.responsibility}</p></article>
                <article><span>模型 / 通道</span><p>{primarySeat.model || primarySeat.providerLabel || "继承默认配置"}</p></article>
                <article><span>线程状态</span><p>{primarySeat.dispatchState} · 线程选择回主页面处理，派单前以电脑持续接单为准</p></article>
              </div>
            ) : <p className={styles.emptyText}>选择或创建 NPC 后显示员工属性。</p>}
          </details>
          <details open>
            <summary><span>Skill / 知识库</span><strong>{skillAssignedCount}/{allSeats.length || 0}</strong></summary>
            <div className={styles.drawerBody}>
              <article><span>已绑定能力</span><p>{skillAssignedCount} 名 NPC 已有 Skill loadout 或工位继承能力。</p></article>
              <article><span>知识库</span><p>{knowledgeAssignedCount} 名 NPC 有知识库摘要或工位知识路径。</p></article>
              <Link href={`/projects/${projectId}/skill-forge?return_to=${encodeURIComponent(selfPath)}&from=company`}>打开能力工坊</Link>
            </div>
          </details>
          <details>
            <summary><span>审核策略</span><strong>{strictReviewCount ? "有强审" : "继承默认"}</strong></summary>
            <div className={styles.drawerBody}>
              <article><span>原则</span><p>跨工位、高风险、硬件、部署、模型发布和 Git 回退都必须由人确认。</p></article>
              <Link href={`/projects/${projectId}/cockpit?return_to=${encodeURIComponent(selfPath)}&from=company`}>去驾驶舱处理待审</Link>
            </div>
          </details>
        </aside>
      </section>

      <section className={styles.bottomDock} aria-label="组织变更日志">
        <div className={styles.logHeader}>
          <span>组织变更 / 协作事件</span>
          <strong>{recentOrgEvents.length ? `${recentOrgEvents.length} 条` : "等待事件"}</strong>
        </div>
        <div className={styles.logRows}>
          {recentOrgEvents.length ? recentOrgEvents.map((event, index) => (
            <article key={text(event.id, `event-${index}`)}>
              <span>{publicStatusLabel(event.status)}</span>
              <strong>{text(event.title, "协作事件")}</strong>
              <p>{orgEventTypeLabel(event.message_type ?? event.body)} · 组织事件已进入项目记录。</p>
            </article>
          )) : (
            <p className={styles.emptyText}>还没有组织变更事件。创建工位、绑定能力或调整审核策略后会在这里显示摘要。</p>
          )}
        </div>
      </section>
    </main>
  );
}
