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
import { runnerStateLabel } from "../../../../lib/runner-status";
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
  if (/online|ready|ok|watcher ready|connected|active/.test(raw)) return "线程已绑定";
  if (/stale|timeout|delay/.test(raw)) return "可能延迟";
  if (/offline|lost|failed|error/.test(raw)) return "需重连";
  return automationEnabled ? "已绑定，待电脑可投递" : "待接入";
}

function publicComputerDispatchState(node: AnyRecord | undefined) {
  return runnerStateLabel(node);
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

function messageMeta(value: AnyRecord) {
  return {
    ...record(value.extra_data ?? value.extraData),
    ...record(value.metadata),
  };
}

function isPendingHumanReview(value: AnyRecord) {
  const type = text(value.message_type ?? value.messageType, "").toLowerCase();
  const status = text(value.status, "").toLowerCase();
  return type === "human_review_request" && ["pending_human_review", "pending", "open"].includes(status);
}

function reviewSourceLabel(value: AnyRecord) {
  const meta = messageMeta(value);
  if (text(meta.schema, "") === "skill_forge_review_v1") return "能力工坊待确认";
  return "待人工确认";
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
  if (value.includes("/datasets")) return "← 返回设备数据工作台";
  if (value.includes("/ai-lab")) return "← 返回设备数据工作台";
  if (value.includes("/robotics")) return "← 返回设备数据工作台";
  if (value.includes("/observability")) return "← 返回公司层";
  if (value.includes("/skill-forge")) return "← 返回能力工坊";
  if (value.includes("/workbench")) return "← 返回 NPC 工作台";
  if (value.includes("/company")) return "← 返回公司层";
  return "← 返回来源";
}

function statusTone(label: string) {
  if (/可投递|在线|已完成|已送达/.test(label)) return "healthy";
  if (/延迟|待审核|强审|待处理|等待|未知/.test(label)) return "review";
  if (/离线|需重连|阻塞|失败/.test(label)) return "blocked";
  return "idle";
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
    const computerState = computerNodeId ? publicComputerDispatchState(nodeStateMap.get(computerNodeId)) : "状态未知，先检查接入";
    const dispatchState = threadId && computerNodeId ? computerState : "状态未知，先检查接入";
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
  const threadReadyCount = allSeats.filter((seat) => seat.dispatchState === "可投递").length;
  const waitingComputerCount = allSeats.filter((seat) => /等待|离线|重连|未知/.test(seat.dispatchState)).length;
  const strictReviewCount = allSeats.filter((seat) => reviewPolicyLabel(seat.reviewPolicy) === "强审").length;
  const skillAssignedCount = allSeats.filter((seat) => seat.skillLoadout.length || seat.inheritedSkills.length).length;
  const knowledgeAssignedCount = allSeats.filter((seat) => seat.knowledgeSummary || seat.workstationKnowledgePath).length;
  const readyNodeCount = [...nodeStateMap.values()].filter((node) => publicComputerDispatchState(node) === "可投递").length;

  const returnToPath = safeProjectReturnPath(params.id, searchParams?.return_to);

  const allOrgEvents = asArray<AnyRecord>(collaborationMessagesState.data);
  const pendingHumanReviews = allOrgEvents.filter(isPendingHumanReview);
  const recentOrgEvents = allOrgEvents.slice(0, 6);
  const projectId = String(project.id ?? params.id);
  const selfPath = `/projects/${projectId}/company`;
  const decisionItems = [
    pendingHumanReviews.length ? `${pendingHumanReviews.length} 条待人工确认` : "",
    waitingComputerCount ? `有 ${waitingComputerCount} 名 NPC 等待电脑恢复` : "",
    strictReviewCount ? `${strictReviewCount} 名 NPC 启用强审策略` : "",
    skillAssignedCount < allSeats.length ? `${Math.max(allSeats.length - skillAssignedCount, 0)} 名 NPC 待补 Skill` : "",
    knowledgeAssignedCount < allSeats.length ? `${Math.max(allSeats.length - knowledgeAssignedCount, 0)} 名 NPC 待补知识库` : "",
    recentOrgEvents.length ? `${recentOrgEvents.length} 条最近回执需要抽查` : "",
  ].filter(Boolean).slice(0, 5);

  return (
    <main className={styles.shell} data-embedded={searchParams?.embed === "drawer" ? "1" : undefined}>
      <nav className={styles.topNav} aria-label="公司层导航">
        <Link href={`/projects/${projectId}`}>主页面</Link>
        <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=company`}>NPC 工作台</Link>
        <Link href={`/projects/${projectId}/skill-forge?return_to=${encodeURIComponent(selfPath)}&from=company`}>能力工坊</Link>
        {returnToPath ? <Link href={returnToPath}>{labelProjectReturnPath(returnToPath)}</Link> : null}
      </nav>

      <header className={styles.header}>
        <div>
          <span>公司层 / 运行态势图</span>
          <h1>{text(project.name, "AI 合作平台")} 公司沙盘</h1>
          <p>一眼看部门、NPC、任务流、审核风险和电脑健康；组织编辑和证据查看都在当前页抽屉里完成。</p>
        </div>
        <section className={styles.statusStrip} aria-label="组织状态">
          <article><span>工位</span><strong>{workstationRows.length}</strong><small>逻辑部门</small></article>
          <article><span>NPC</span><strong>{allSeats.length}</strong><small>员工席位</small></article>
          <article><span>可接单</span><strong>{threadReadyCount}/{allSeats.length || 0}</strong><small>NPC 状态</small></article>
          <article><span>电脑健康</span><strong>{readyNodeCount}/{nodeStateMap.size || 0}</strong><small>真实设备</small></article>
        </section>
      </header>

      <section className={styles.layout}>
        <section className={styles.centerPane} aria-label="公司运行状态一览图">
          <div className={styles.decisionBand}>
            <div>
              <span>今天先看</span>
              <strong>{decisionItems[0] ?? "公司运行平稳"}</strong>
            </div>
            <div className={styles.decisionChips}>
              {(decisionItems.length ? decisionItems : ["暂无阻塞", "无待审提醒", "电脑状态正常"]).map((item, index) => (
                <span key={`${item}-${index}`}>{item}</span>
              ))}
            </div>
          </div>

          <div className={styles.sandbox}>
            <div className={styles.flowLayer} aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            {workstationRows.map((ws, index) => {
              const wsReady = ws.seats.filter((seat) => seat.dispatchState === "可投递").length;
              const wsBlocked = ws.seats.filter((seat) => statusTone(seat.dispatchState) === "blocked").length;
              const tone = wsBlocked ? "blocked" : wsReady ? "healthy" : "idle";
              return (
                <article key={ws.id} className={styles.departmentZone} data-tone={tone} data-active={index === 0 ? "1" : undefined}>
                  <header>
                    <div>
                      <span>部门区域</span>
                      <strong>{ws.name}</strong>
                      <small>负责人：{ws.leadName}</small>
                    </div>
                    <dl>
                      <div><dt>在线</dt><dd>{wsReady}/{ws.seats.length || 0}</dd></div>
                      <div><dt>待审</dt><dd>{ws.seats.filter((seat) => reviewPolicyLabel(seat.reviewPolicy) === "强审").length}</dd></div>
                      <div><dt>阻塞</dt><dd>{wsBlocked}</dd></div>
                    </dl>
                  </header>

                  <div className={styles.seatGrid}>
                    {ws.seats.length ? ws.seats.map((seat) => (
                      <Link
                        key={seat.id}
                        href={`/projects/${projectId}/workbench?seat_id=${encodeURIComponent(seat.id)}&return_to=${encodeURIComponent(selfPath)}&from=company`}
                        className={styles.seatNode}
                        data-tone={statusTone(seat.dispatchState)}
                        title={`打开 ${seat.name} 的 NPC 工作台`}
                      >
                        <span className={styles.avatar}>{seat.name.slice(0, 2).toUpperCase()}</span>
                        <strong>{seat.name}</strong>
                        <small>{seat.isLead ? "工位长" : reviewPolicyLabel(seat.reviewPolicy)}</small>
                        <em>{seat.dispatchState}</em>
                      </Link>
                    )) : (
                      <div className={styles.emptySeat}>
                        <strong>待分配 NPC</strong>
                        <p>先在主页面创建 NPC，再回公司层分配部门和职责。</p>
                      </div>
                    )}
                  </div>

                  <div className={styles.deviceDock}>
                    {(ws.seats.length ? ws.seats : []).filter((seat) => seat.computerNodeName).slice(0, 4).map((seat) => (
                      <span key={`${ws.id}-${seat.id}-node`} data-tone={statusTone(seat.dispatchState)}>
                        {seat.computerNodeName}
                      </span>
                    ))}
                    {!ws.seats.some((seat) => seat.computerNodeName) ? <span data-tone="idle">待绑定电脑</span> : null}
                  </div>
                </article>
              );
            })}
            {!allSeats.length ? (
              <article className={styles.emptyRow}>
                <strong>还没有 NPC 员工</strong>
                <p>先在主页面创建 NPC、扫描线程并绑定，再回公司层分配职责和审核策略。</p>
              </article>
            ) : null}
          </div>
        </section>

      </section>

      <section className={styles.bottomDock} aria-label="组织变更日志">
        <div className={styles.logHeader}>
          <span>组织变更 / 协作事件</span>
          <strong>{recentOrgEvents.length ? `${recentOrgEvents.length} 条` : "等待事件"}</strong>
        </div>
        <div className={styles.logRows}>
          {(pendingHumanReviews.length ? pendingHumanReviews.slice(0, 6) : recentOrgEvents).map((event, index) => (
            <article key={text(event.id, `event-${index}`)}>
              <span>{isPendingHumanReview(event) ? reviewSourceLabel(event) : publicStatusLabel(event.status)}</span>
              <strong>{text(event.title, "协作事件")}</strong>
              <p>{isPendingHumanReview(event) ? "需要项目负责人或人工确认后再继续。" : `${orgEventTypeLabel(event.message_type ?? event.body)} · 组织事件已进入项目记录。`}</p>
            </article>
          ))}
          {!pendingHumanReviews.length && !recentOrgEvents.length ? (
            <p className={styles.emptyText}>还没有组织变更事件。创建工位、绑定能力或调整审核策略后会在这里显示摘要。</p>
          ) : null}
        </div>
      </section>
    </main>
  );
}
