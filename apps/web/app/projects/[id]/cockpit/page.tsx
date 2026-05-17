import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCollaborationMessagesState,
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectScorecardState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getRequirementsState,
  getTasksDataScopedState,
} from "../../../../lib/server-data";
import { runnerCanDispatch, runnerStateLabel } from "../../../../lib/runner-status";
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

function statusText(value: unknown) {
  return text(value, "").toLowerCase();
}

function safeProjectReturnPath(projectId: string, value: unknown) {
  const raw = text(value, "");
  if (!raw.startsWith(`/projects/${projectId}/`)) return "";
  if (/^\/\//.test(raw) || raw.includes("\\") || raw.includes("://")) return "";
  return raw;
}

function labelProjectReturnPath(value: string) {
  if (value.includes("/workbench")) return "返回 NPC 工作台";
  if (value.includes("/datasets")) return "返回数据工场";
  if (value.includes("/ai-lab")) return "返回 AI 实验室";
  if (value.includes("/robotics")) return "返回机器人现场";
  if (value.includes("/observability")) return "返回观测台";
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/skill-forge")) return "返回能力工坊";
  return "返回来源";
}

function humanStatus(value: unknown, fallback = "待处理") {
  const raw = statusText(value);
  if (/completed|done|success|resolved|passed/.test(raw)) return "已完成";
  if (/review|approval/.test(raw)) return "待审核";
  if (/blocked|failed|error|rejected|timeout/.test(raw)) return "阻塞";
  if (/pending_closeout|closeout/.test(raw)) return "待收口";
  if (/running|active|in_progress|queued|accepted|pending/.test(raw)) return "处理中";
  if (/offline|stale|disconnect/.test(raw)) return "等待电脑恢复";
  if (/online|ready|connected/.test(raw)) return "在线";
  return text(value, fallback);
}

function eventTypeLabel(value: unknown) {
  const raw = statusText(value);
  const commandKinds = ["runner", "command", "dispatch"];
  const resultKinds = ["final", "reply", "receipt", "agent", "result"];
  const progressKinds = ["progress", "ack", "agent", "command"];
  if (commandKinds.some((part) => raw.includes(part))) return "派单事件";
  if (resultKinds.some((part) => raw.includes(part))) return "回执";
  if (progressKinds.some((part) => raw.includes(part))) return "过程记录";
  if (/desktop|question/.test(raw)) return "桌面消息";
  if (/review|approval/.test(raw)) return "审核";
  if (/requirement|need/.test(raw)) return "协作需求";
  return text(value, "协作事件");
}

function itemTitle(item: AnyRecord | null | undefined, fallback = "未命名事项") {
  if (!item) return fallback;
  return text(item.title ?? item.name ?? item.body ?? item.description, fallback)
    .replace(new RegExp(`^${["Task", "dispatch"].join(" ")}:\\s*`, "i"), "任务派发：")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "当前记录");
}

function computerState(value: unknown) {
  const raw = statusText(value);
  if (/watching|online|ready|active|connected/.test(raw)) return "在线";
  if (/recent|stale|timeout|delay/.test(raw)) return "可能延迟";
  if (/offline|lost|disconnect|error/.test(raw)) return "离线，需重连";
  return "状态未知";
}

function computerDispatchState(node: AnyRecord | undefined) {
  return runnerStateLabel(node);
}

function seatCanDispatch(seat: AnyRecord, computerById: Map<string, AnyRecord>) {
  const nodeId = text(seat.computer_node_id ?? seat.computerNodeId ?? seat.computer_node ?? seat.computerNode, "");
  if (!nodeId) return false;
  return runnerCanDispatch(computerById.get(nodeId));
}

export default async function ProjectCockpitPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { return_to?: string; from?: string; embed?: string };
}) {
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${params.id}/cockpit`)}`);
  }

  const projectState = await getProjectState(params.id);
  const project = projectState.data;
  if (!project) {
    return (
      <main className={styles.shell}>
        <p>项目不存在或无权限。</p>
        <Link href="/projects">返回项目列表</Link>
      </main>
    );
  }

  const projectId = String(project.id ?? params.id);
  const selfPath = `/projects/${projectId}/cockpit`;
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const [tasksState, requirementsState, messagesState, computersState, seatsState, scorecardState] = await Promise.all([
    getTasksDataScopedState({ projectIds: [projectId] }),
    getRequirementsState({ projectIds: [projectId] }),
    getCollaborationMessagesState({ projectId }),
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectScorecardState(projectId),
  ]);

  const tasks = asArray<AnyRecord>(tasksState.data);
  const requirements = asArray<AnyRecord>(requirementsState.data);
  const messages = asArray<AnyRecord>(messagesState.data);
  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(seatsState.data);
  const scorecard = scorecardState.data && typeof scorecardState.data === "object" ? (scorecardState.data as AnyRecord) : {};
  const computerById = new Map<string, AnyRecord>();
  for (const computer of computers) {
    const id = text(computer.id ?? computer.config_id ?? computer.node_id, "");
    if (id) computerById.set(id, computer);
  }

  const pendingReviews = messages.filter((item) => /review|approval|pending_review|waiting_review/.test(statusText(item.status) + " " + statusText(item.message_type)));
  const blockedTasks = tasks.filter((item) => /blocked|failed|error|rejected|timeout/.test(statusText(item.status)));
  const closeoutItems = messages.filter((item) => /closeout|pending_closeout|waiting_closeout/.test(statusText(item.status) + " " + statusText(item.message_type)));
  const activeTasks = tasks.filter((item) => /queued|running|active|in_progress|accepted|pending/.test(statusText(item.status)));
  const finalReceipts = messages
    .filter((item) => {
      const messageType = statusText(item.message_type);
      return ["final", "reply", "receipt"].some((part) => messageType.includes(part)) || (messageType.includes("agent") && messageType.includes("result")) || item.is_final_reply;
    })
    .slice(0, 4);
  const riskyNeeds = requirements.filter((item) => /high|critical/.test(statusText(item.risk_level ?? item.riskLevel ?? item.priority)));
  const onlineComputers = computers.filter((node) => runnerCanDispatch(node));
  const staleComputers = computers.filter((node) => !runnerCanDispatch(node));
  const readySeats = seats.filter((seat) => seatCanDispatch(seat, computerById));
  const grade = text(scorecard.grade ?? scorecard.overall_grade ?? scorecard.status, "待评估");

  const focusCards = [
    {
      label: "待我处理",
      value: pendingReviews.length + closeoutItems.length,
      detail: pendingReviews.length ? "先处理待审核，再看待收口。" : closeoutItems.length ? "有桌面回执需要收口。" : "当前没有必须立刻处理的审核。",
      href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=cockpit`,
    },
    {
      label: "阻塞",
      value: blockedTasks.length + riskyNeeds.length,
      detail: blockedTasks.length ? "有任务处于阻塞或失败状态。" : riskyNeeds.length ? "有高风险需求需要负责人判断。" : "暂无高风险阻塞。",
      href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=cockpit`,
    },
    {
      label: "电脑状态",
      value: `${onlineComputers.length}/${computers.length || 0}`,
      detail: staleComputers.length ? "有执行电脑需要重连或确认状态。" : "执行电脑状态未发现明显阻塞。",
      href: `/projects/${projectId}`,
    },
    {
      label: "可验收回执",
      value: finalReceipts.length,
      detail: finalReceipts.length ? "最近 final 回执可进入观测台核对。" : "等待 NPC 或执行电脑回执。",
      href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=cockpit`,
    },
  ];

  const decisionItems = [
    ...pendingReviews.slice(0, 3).map((item) => ({
      tone: "review",
      title: itemTitle(item, "待审核事项"),
      detail: `${humanStatus(item.status)} · ${eventTypeLabel(item.message_type)}`,
      href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=cockpit`,
    })),
    ...blockedTasks.slice(0, 3).map((item) => ({
      tone: "danger",
      title: itemTitle(item, "阻塞任务"),
      detail: `${humanStatus(item.status)} · 打开证据链后再决定重试、打回或收口。`,
      href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=cockpit`,
    })),
    ...closeoutItems.slice(0, 3).map((item) => ({
      tone: "warning",
      title: itemTitle(item, "待收口事项"),
      detail: "桌面过程可能已继续，先补拉最终回执或延长等待。",
      href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=cockpit`,
    })),
  ].slice(0, 6);

  const nextActions = [
    ["处理待审", pendingReviews.length ? "先通过、打回或改派待审核事项。" : "当前没有待审，保持观察。", `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=cockpit`],
    ["检查电脑", staleComputers.length ? "有电脑离线或状态未知，先回主页面检查接入。" : "电脑状态暂不阻塞派单。", `/projects/${projectId}`],
    ["看 NPC 工作", activeTasks.length ? "打开 NPC 工作台看进行中任务和最小回执。" : "没有明显活跃任务，准备下一轮派单。", `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=cockpit`],
    ["看完整证据", "完整历史链路留在观测台，不塞进驾驶舱。", `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=cockpit`],
  ];

  return (
    <main className={styles.shell} data-embed={searchParams?.embed === "drawer" ? "drawer" : undefined}>
      <nav className={styles.topNav} aria-label="驾驶舱导航">
        <Link href={`/projects/${projectId}`}>主页面</Link>
        <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=cockpit`}>NPC 工作台</Link>
        <Link href={`/projects/${projectId}/company?return_to=${encodeURIComponent(selfPath)}&from=cockpit`}>公司层</Link>
        <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=cockpit`}>观测台</Link>
        {returnTo ? <Link href={returnTo}>{labelProjectReturnPath(returnTo)}</Link> : null}
      </nav>

      <header className={styles.header}>
        <div>
          <span>驾驶舱 / 今日决策</span>
          <h1>{text(project.name, "AI 合作平台")} 今日状态</h1>
          <p>这里只放今天需要负责人处理、确认或跳转的事项。完整链路、历史和技术细节进观测台。</p>
        </div>
        <section className={styles.statusStrip}>
          <article><span>评分</span><strong>{grade}</strong><small>部署/协作状态</small></article>
          <article><span>NPC</span><strong>{readySeats.length}/{seats.length || 0}</strong><small>可投递线程</small></article>
          <article><span>任务</span><strong>{activeTasks.length}</strong><small>进行中</small></article>
          <article><span>电脑</span><strong>{onlineComputers.length}/{computers.length || 0}</strong><small>在线</small></article>
        </section>
      </header>

      <section className={styles.layout}>
        <aside className={styles.leftRail}>
          <div className={styles.railHead}><span>今日重点</span><strong>{focusCards.length} 项</strong></div>
          {focusCards.map((card) => (
            <Link key={card.label} href={card.href} className={styles.focusCard}>
              <span>{card.label}</span>
              <strong>{card.value}</strong>
              <p>{card.detail}</p>
            </Link>
          ))}
        </aside>

        <section className={styles.centerPane}>
          <div className={styles.toolbar}>
            <div>
              <span>等我处理</span>
              <strong>{decisionItems.length ? `${decisionItems.length} 个事项` : "当前清爽"}</strong>
            </div>
            <div className={styles.toolbarActions}>
              <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=cockpit`}>看证据</Link>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=cockpit`}>打开 NPC</Link>
            </div>
          </div>
          <div className={styles.decisionList}>
            {decisionItems.length ? decisionItems.map((item, index) => (
              <Link key={`${item.title}-${index}`} href={item.href} className={styles.decisionItem} data-tone={item.tone}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
              </Link>
            )) : (
              <article className={styles.emptyState}>
                <strong>当前没有必须立刻处理的阻塞</strong>
                <p>可以继续从 NPC 工作台派单，或从观测台回看最近证据链。</p>
              </article>
            )}
          </div>
        </section>

        <aside className={styles.rightRail}>
          <details open>
            <summary><span>电脑 / Runner</span><strong>{onlineComputers.length}/{computers.length || 0}</strong></summary>
            <div className={styles.drawerBody}>
              {(computers.length ? computers.slice(0, 5) : [{ name: "还没有电脑接入", status: "unknown" }]).map((node, index) => (
                <article key={text(node.id, `computer-${index}`)}>
                  <span>{computerDispatchState(node)}</span>
                  <strong>{text(node.name ?? node.label ?? node.hostname, `执行电脑 ${index + 1}`)}</strong>
                  <p>{runnerCanDispatch(node) ? "可用于派发和回执同步。" : "先检查接入、重连或改派。"}</p>
                </article>
              ))}
            </div>
          </details>
          <details open>
            <summary><span>最近 final 回执</span><strong>{finalReceipts.length}</strong></summary>
            <div className={styles.drawerBody}>
              {finalReceipts.length ? finalReceipts.map((item, index) => (
                <Link key={text(item.id, `receipt-${index}`)} href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=cockpit`}>
                  <span>{humanStatus(item.status)}</span>
                  <strong>{itemTitle(item, "最终回执")}</strong>
                  <p>{eventTypeLabel(item.message_type)} · 由负责人确认是否验收。</p>
                </Link>
              )) : <p className={styles.emptyText}>等待最终回执。</p>}
            </div>
          </details>
        </aside>
      </section>

      <section className={styles.bottomDock}>
        <div className={styles.logHeader}><span>下一步建议</span><strong>{nextActions.length} 条</strong></div>
        <div className={styles.nextRows}>
          {nextActions.map(([label, detail, href]) => (
            <Link key={label} href={href}>
              <span>{label}</span>
              <p>{detail}</p>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
