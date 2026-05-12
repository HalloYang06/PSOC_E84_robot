import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectScorecardState,
  getProjectState,
  getProjectWorkstationsState,
  getCollaborationMessagesState,
  getHandoffsData,
} from "../../../../lib/server-data";
import { isNpcSeatRecord } from "../../../../lib/platform-provider";
import { 通过自主合作待审消息, 打回自主合作待审消息 } from "../../../actions";
import styles from "./cockpit.module.css";

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

function gradeColor(grade: string): string {
  switch ((grade || "").toUpperCase()) {
    case "A":
      return "#22c55e";
    case "B":
      return "#84cc16";
    case "C":
      return "#f59e0b";
    case "D":
      return "#ef4444";
    default:
      return "#94a3b8";
  }
}

export default async function ProjectCockpitPage({ params, searchParams }: { params: { id: string }; searchParams?: { embed?: string } }) {
  const embedded = searchParams?.embed === "drawer";
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?next=/projects/${params.id}/cockpit`);
  }

  const [projectState, computerNodesState, projectWorkstationsState, scorecardState, handoffsAll, messagesState, pendingReviewState] = await Promise.all([
    getProjectState(params.id),
    getProjectComputerNodesState(params.id),
    getProjectWorkstationsState(params.id),
    getProjectScorecardState(params.id),
    getHandoffsData(),
    getCollaborationMessagesState({ projectId: params.id }),
    getCollaborationMessagesState({ projectId: params.id, status: "pending_review" }),
  ]);

  const project = projectState.data as AnyRecord | null;
  if (!project) {
    return (
      <main className={styles.page}>
        <p className={styles.muted}>项目不存在或无权限。</p>
        <Link href="/projects" className={styles.link}>← 返回项目列表</Link>
      </main>
    );
  }

  const config = (project.collaboration_config ?? {}) as AnyRecord;
  const rawWorkstations = asArray<AnyRecord>(
    config.thread_workstations ?? config.threadWorkstations ?? config.workstations,
  );
  const seatRecords = rawWorkstations.filter((item) => isNpcSeatRecord(item));
  const liveNodes = asArray<AnyRecord>(computerNodesState.data);
  const configNodes = asArray<AnyRecord>(config.computer_nodes ?? config.nodes);
  const nodeMap = new Map<string, string>();
  for (const node of [...configNodes, ...liveNodes]) {
    const id = text(node?.id ?? node?.node_id, "");
    if (!id) continue;
    const name = text(node?.name ?? node?.label ?? node?.hostname ?? id, id);
    nodeMap.set(id, name);
  }
  const projectWorkstations = asArray<AnyRecord>(projectWorkstationsState.data);
  const workstationNameById = new Map<string, string>();
  for (const ws of projectWorkstations) {
    const id = text(ws?.id, "");
    if (id) workstationNameById.set(id, text(ws?.name, id));
  }

  const seatGroups = new Map<string, { label: string; isLogical: boolean; seats: AnyRecord[] }>();
  for (const seat of seatRecords) {
    const wsId = text(seat.workstation_id ?? seat.workstationId, "");
    const nodeId = text(seat.computer_node_id ?? seat.computerNodeId, "");
    let key = "__unbound__";
    let label = "未归属工位";
    let isLogical = false;
    if (wsId) {
      key = `ws:${wsId}`;
      label = workstationNameById.get(wsId) ?? wsId;
      isLogical = true;
    } else if (nodeId) {
      key = `node:${nodeId}`;
      label = nodeMap.get(nodeId) ?? nodeId;
    }
    const bucket = seatGroups.get(key) ?? { label, isLogical, seats: [] };
    bucket.seats.push(seat);
    seatGroups.set(key, bucket);
  }

  const sc = scorecardState.data as AnyRecord | null;
  const indicators = (sc?.indicators ?? {}) as AnyRecord;
  const overall = (sc?.overall ?? {}) as AnyRecord;
  const overallGrade = text(overall.grade, "-");
  const overallSummary = text(overall.summary, "暂无评估");

  const handoffsForProject = asArray<AnyRecord>(handoffsAll).filter((h) => {
    const pid = text(h.project_id ?? h.projectId, "");
    return pid === text(project.id ?? params.id, "");
  });

  const recentMessages = asArray<AnyRecord>(messagesState.data).slice(0, 8);
  const pendingReviewMessages = asArray<AnyRecord>(pendingReviewState.data);

  const githubUrl = text(project.github_url ?? project.githubUrl, "");
  const localGitUrl = text(project.local_git_url ?? project.localGitUrl, "");
  const defaultBranch = text(project.default_branch ?? project.defaultBranch, "");
  const developBranch = text(project.develop_branch ?? project.developBranch, "");

  const indicatorList = [
    { key: "thread_call_health", row: indicators.thread_call_health },
    { key: "npc_handover_health", row: indicators.npc_handover_health },
    { key: "human_review_responsiveness", row: indicators.human_review_responsiveness },
    { key: "hardware_redline_count", row: indicators.hardware_redline_count },
    { key: "collaboration_density", row: indicators.collaboration_density },
    { key: "token_spend_7d_yuan", row: indicators.token_spend_7d_yuan },
  ].filter((entry) => entry.row && typeof entry.row === "object");

  return (
    <main className={styles.page} data-embed={embedded ? "drawer" : undefined}>
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          <Link href="/projects" className={styles.link}>← 项目列表</Link>
          <span className={styles.sep}>/</span>
          <strong className={styles.projectName}>{text(project.name, params.id.slice(0, 8))}</strong>
          <span className={styles.muted} title={text(project.id ?? params.id)}>#{text(project.id ?? params.id).slice(0, 8)}</span>
        </div>
        <div className={styles.topbarRight}>
          <Link href={`/projects/${params.id}/2d-upgrade`} className={styles.primaryBtn}>
            打开项目主页面 →
          </Link>
          <Link href={`/projects/${params.id}/datasets?return_to=${encodeURIComponent(`/projects/${params.id}/cockpit`)}&from=cockpit`} className={styles.ghostBtn} title="训练数据采集、标注、质检和导出">
            🧪 数据工场
          </Link>
          <Link href={`/projects/${params.id}/company`} className={styles.ghostBtn} title="公司层：只看每个工位的工位长（👑），跨工位指派的默认入口">
            🏢 公司层
          </Link>
          <Link href={`/projects/${params.id}`} className={styles.ghostBtn} title="返回项目入口壳（可打开驾驶舱、工作台、数据工场、公司层）">
            ← 项目入口
          </Link>
        </div>
      </header>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2>项目合格性</h2>
          <span className={styles.gradeChip} style={{ backgroundColor: gradeColor(overallGrade) }} title={overallSummary}>
            {overallGrade}
          </span>
        </div>
        <p className={styles.muted}>{overallSummary}</p>
        {indicatorList.length === 0 ? (
          <p className={styles.muted}>暂无指标数据。</p>
        ) : (
          <div className={styles.scoreGrid}>
            {indicatorList.map(({ key, row }) => {
              const grade = text((row as AnyRecord).grade, "-");
              return (
                <div key={key} className={styles.scoreCard}>
                  <div className={styles.scoreHead}>
                    <span className={styles.scoreLabel}>{text((row as AnyRecord).label, key)}</span>
                    <span className={styles.gradeChipSm} style={{ backgroundColor: gradeColor(grade) }}>
                      {grade}
                    </span>
                  </div>
                  <div className={styles.scoreDetail}>{text((row as AnyRecord).detail, "")}</div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2>仓库 / 分支</h2>
        </div>
        <ul className={styles.repoList}>
          <li>
            <span className={styles.repoKey}>GitHub:</span>
            <span className={styles.repoVal}>{githubUrl || <em className={styles.muted}>未设置</em>}</span>
          </li>
          <li>
            <span className={styles.repoKey}>本地镜像:</span>
            <span className={styles.repoVal}>{localGitUrl || <em className={styles.muted}>未设置</em>}</span>
          </li>
          <li>
            <span className={styles.repoKey}>主分支:</span>
            <span className={styles.repoVal}>{defaultBranch || <em className={styles.muted}>未设置</em>}</span>
          </li>
          <li>
            <span className={styles.repoKey}>开发分支:</span>
            <span className={styles.repoVal}>{developBranch || <em className={styles.muted}>未设置</em>}</span>
          </li>
        </ul>
        <p className={styles.muted}>修改入口在工作台顶部&quot;⚙ 项目设置&quot;（v1.1 添加）。</p>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2>工位 · NPC 分组</h2>
          <span className={styles.muted}>共 {seatRecords.length} 个 NPC / {seatGroups.size} 个工位</span>
        </div>
        {seatGroups.size === 0 ? (
          <p className={styles.muted}>还没有 NPC，去工作台 &quot;+&quot; 创建第一个。</p>
        ) : (
          <div className={styles.workstationGrid}>
            {Array.from(seatGroups.entries()).map(([key, group]) => {
              return (
                <div key={key} className={styles.workstationCard}>
                  <div className={styles.workstationHead}>
                    <strong>
                      {group.isLogical ? "🏷 " : "🖥 "}{group.label}
                      {group.isLogical ? <small style={{ marginLeft: 6, opacity: 0.7 }}>逻辑工位</small> : null}
                    </strong>
                    <span className={styles.muted}>{group.seats.length} 个 NPC</span>
                  </div>
                  <ul className={styles.seatList}>
                    {group.seats.map((seat) => {
                      const sid = text(seat.id ?? seat.config_id, "");
                      const sname = text(seat.name, sid.slice(0, 8) || "未命名");
                      const provider = text(seat.provider_label ?? seat.providerLabel ?? seat.provider_id ?? seat.providerId, "");
                      return (
                        <li key={sid} className={styles.seatItem}>
                          <span className={styles.seatName}>{sname}</span>
                          <span className={styles.muted}>{provider}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2>跨工位 Handoff（最近）</h2>
          <span className={styles.muted}>{handoffsForProject.length} 条</span>
        </div>
        {handoffsForProject.length === 0 ? (
          <p className={styles.muted}>暂无 Handoff 记录。</p>
        ) : (
          <ul className={styles.handoffList}>
            {handoffsForProject.slice(0, 8).map((h) => (
              <li key={text(h.id, Math.random().toString())} className={styles.handoffItem}>
                <span className={styles.handoffStatus}>{text(h.status, "open")}</span>
                <span className={styles.handoffTitle}>{text(h.title ?? h.summary, "(无标题)")}</span>
                <span className={styles.muted}>{text(h.created_at ?? h.createdAt, "").slice(0, 19).replace("T", " ")}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2>待审：NPC 自主合作消息</h2>
          <span className={styles.muted}>
            {pendingReviewMessages.length} 条
            {pendingReviewMessages.length > 0 ? "（跨工位默认走人审；可在项目设置改成免审）" : ""}
          </span>
        </div>
        {pendingReviewMessages.length === 0 ? (
          <p className={styles.muted}>当前没有待审消息。同工位 NPC 间默认免审；跨工位的自主合作会落到这里等你通过/打回。</p>
        ) : (
          <ul className={styles.messageList}>
            {pendingReviewMessages.map((m) => {
              const id = text(m.id, "");
              return (
                <li key={id || Math.random().toString()} className={styles.messageItem}>
                  <span className={styles.msgType}>pending_review</span>
                  <span className={styles.msgSender}>
                    {text(m.sender_type, "?")}/{text(m.sender_id, "").slice(0, 8)} → {text(m.recipient_type, "?")}/{text(m.recipient_id, "").slice(0, 12)}
                  </span>
                  <span className={styles.msgBody}>{text(m.title, "") || text(m.body, "").slice(0, 100)}</span>
                  <span style={{ display: "flex", gap: 6 }}>
                    <form action={async () => { "use server"; await 通过自主合作待审消息(id, params.id); }}>
                      <button type="submit" className={styles.primaryBtn} style={{ padding: "2px 8px", fontSize: 12 }}>通过</button>
                    </form>
                    <form action={async () => { "use server"; await 打回自主合作待审消息(id, params.id); }}>
                      <button type="submit" className={styles.ghostBtn} style={{ padding: "2px 8px", fontSize: 12 }}>打回</button>
                    </form>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2>最近协作消息</h2>
          <span className={styles.muted}>{recentMessages.length} 条</span>
        </div>
        {recentMessages.length === 0 ? (
          <p className={styles.muted}>暂无消息。去工作台开个瓷砖派一条试试。</p>
        ) : (
          <ul className={styles.messageList}>
            {recentMessages.map((m) => (
              <li key={text(m.id, Math.random().toString())} className={styles.messageItem}>
                <span className={styles.msgType}>{text(m.message_type ?? m.type, "msg")}</span>
                <span className={styles.msgSender}>{text(m.sender_type, "?")}/{text(m.sender_id, "").slice(0, 8)}</span>
                <span className={styles.msgBody}>{text(m.content ?? m.body, "").slice(0, 120)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className={styles.footer}>
        <span className={styles.muted}>
          这是真驾驶舱页（v1）。旧版农场游戏壳已迁到 <code>?legacy=1</code>。详细 NPC 操作请进工作台。
        </span>
      </footer>
    </main>
  );
}
