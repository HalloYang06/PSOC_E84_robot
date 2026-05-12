import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCollaborationMessagesState,
  getApiHealthState,
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectScorecardState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
  getTasksDataScopedState,
  getUsageData,
} from "../../../../lib/server-data";
import styles from "./observability.module.css";

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
  if (value.includes("/2d-upgrade")) return "返回主页面";
  if (value.includes("/workbench")) return "返回 NPC 工作台";
  if (value.includes("/datasets")) return "返回数据工场";
  if (value.includes("/ai-lab")) return "返回 AI 实验室";
  if (value.includes("/robotics")) return "返回机器人现场";
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/observability")) return "返回观测台";
  if (value.includes("/skill-forge")) return "返回 Skill 工坊";
  return "返回来源";
}

function messageTitle(item: AnyRecord) {
  return text(item.title ?? item.body ?? item.message_type ?? item.id, "未命名消息");
}

function statusLabel(value: unknown) {
  const normalized = statusText(value);
  if (["done", "completed", "resolved"].includes(normalized)) return "完成";
  if (["blocked", "failed", "error", "rejected"].includes(normalized)) return "阻塞";
  if (["pending_review", "waiting_review", "review"].includes(normalized)) return "待审";
  if (["queued", "active", "running", "in_progress", "accepted"].includes(normalized)) return "进行中";
  if (["online", "ready"].includes(normalized)) return "在线";
  return text(value, "待处理");
}

const referenceSignals = [
  ["Trace", "Langfuse / Phoenix", "把一次派单、工具调用、回执、最终结果串成可查 trace。"],
  ["Metrics", "OpenTelemetry", "统计延迟、失败率、队列积压、Runner 在线和成本风险。"],
  ["Evaluation", "MLflow / Ragas", "把最终答案、验收、数据集、模型版本和评测结果关联。"],
  ["Incident", "Sentry", "阻塞、超时、重复派单、桌面不可见要进入事件线。"],
];

export default async function ProjectObservabilityPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { return_to?: string; from?: string };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/observability`)}`);
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

  const [
    computersState,
    seatsState,
    workstationsState,
    tasksState,
    messagesState,
    pendingReviewState,
    scorecardState,
    healthState,
    usageData,
  ] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
    getTasksDataScopedState({ projectIds: [projectId] }),
    getCollaborationMessagesState({ projectId }),
    getCollaborationMessagesState({ projectId, status: "pending_review" }),
    getProjectScorecardState(projectId),
    getApiHealthState(),
    getUsageData(),
  ]);

  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(seatsState.data);
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const tasks = asArray<AnyRecord>(tasksState.data);
  const messages = asArray<AnyRecord>(messagesState.data);
  const pendingReview = asArray<AnyRecord>(pendingReviewState.data);
  const usage = asArray<AnyRecord>(usageData).filter((item) => !text(item.project_id ?? item.projectId, "") || text(item.project_id ?? item.projectId, "") === projectId);
  const onlineComputers = computers.filter((node) => /online|ready|active/.test(statusText(node.runner_effective_status ?? node.runner_status ?? node.status))).length;
  const dispatchMessages = messages.filter((item) => statusText(item.proof_stage) === "dispatch" || statusText(item.message_type).includes("dispatch"));
  const finalMessages = messages.filter((item) => Boolean(item.is_final_reply) || statusText(item.proof_stage) === "final_reply" || statusText(item.message_type).includes("final"));
  const progressMessages = messages.filter((item) => Boolean(item.is_progress_signal));
  const blockedTasks = tasks.filter((item) => /blocked|failed|error/.test(statusText(item.status))).length;
  const activeTasks = tasks.filter((item) => /active|running|in_progress|queued/.test(statusText(item.status))).length;
  const sc = scorecardState.data as AnyRecord | null;
  const health = (healthState.data ?? {}) as AnyRecord;
  const localServices = asArray<AnyRecord>(health.local_services ?? health.localServices);
  const listeningPorts = localServices.filter((item) => Boolean(item.listening)).map((item) => text(item.port, ""));
  const overall = (sc?.overall ?? {}) as AnyRecord;
  const grade = text(overall.grade, "-");
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/observability`;

  const kpis = [
    ["Runner 在线", `${onlineComputers}/${computers.length}`, "多电脑能力是否可用"],
    ["NPC 线程", `${seats.length}`, "可接收平台派单的工作线程"],
    ["活跃任务", `${activeTasks}`, `阻塞 ${blockedTasks}`],
    ["待审消息", `${pendingReview.length}`, "NPC-to-NPC / 硬件风险"],
    ["最终回执", `${finalMessages.length}`, `派单 ${dispatchMessages.length}`],
    ["合格性", grade, text(overall.summary, "暂无评估")],
  ];

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <nav>
          <Link href={`/projects/${projectId}/cockpit`}>驾驶舱</Link>
          <Link href={`/projects/${projectId}/map?return_to=${encodeURIComponent(selfPath)}&from=observability`}>地图</Link>
          <Link href={`/projects/${projectId}/2d-upgrade?return_to=${encodeURIComponent(selfPath)}&from=observability`}>主页面</Link>
          <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=observability`}>NPC 工作台</Link>
          <Link href={`/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=observability`}>数据工场</Link>
          <Link href={`/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=observability`}>AI 实验室</Link>
          <Link href={`/projects/${projectId}/robotics?return_to=${encodeURIComponent(selfPath)}&from=observability`}>机器人现场</Link>
          <Link href={`/projects/${projectId}/skill-forge?return_to=${encodeURIComponent(selfPath)}&from=observability`}>Skill 工坊</Link>
          {returnTo ? <Link href={returnTo}>{labelProjectReturnPath(returnTo)}</Link> : null}
        </nav>
        <div>
          <span>消息 {messages.length}</span>
          <span>用量 {usage.length}</span>
          <span>工位 {workstations.length}</span>
        </div>
      </header>

      <section className={styles.hero}>
        <div>
          <span>一级工作台</span>
          <h1>{text(project.name, "项目")} 观测台</h1>
          <p>把派单、回执、待审、Runner、任务状态和风险集中到一个看板里，避免平台功能多了以后用户不知道哪里断了。</p>
        </div>
        <div className={styles.traceBox}>
          <span>dispatch</span>
          <i />
          <span>ack</span>
          <i />
          <span>final</span>
        </div>
      </section>

      <section className={styles.kpiGrid} aria-label="观测指标">
        {kpis.map(([label, value, detail]) => (
          <article key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <p>{detail}</p>
          </article>
        ))}
      </section>

      <section className={styles.contentGrid}>
        <section className={styles.timeline}>
          <div className={styles.sectionHead}>
            <span>最近协作信号</span>
            <h2>只看可定位问题的最小事件。</h2>
          </div>
          <ol>
            {messages.slice(0, 10).map((item) => (
              <li key={text(item.id, messageTitle(item))}>
                <strong>{messageTitle(item)}</strong>
                <p>{statusLabel(item.status)} · {text(item.message_type, "message")} · {text(item.at ?? item.created_at ?? item.updated_at, "")}</p>
              </li>
            ))}
            {!messages.length ? <li><strong>暂无协作消息</strong><p>去 NPC 工作台发起第一条派单后，这里会出现事件线。</p></li> : null}
          </ol>
        </section>

        <aside className={styles.sidePanel}>
          <div className={styles.sectionHead}>
            <span>异常入口</span>
            <h2>先处理会卡住真实开发的东西。</h2>
          </div>
          <div className={styles.alertList}>
            <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=observability`}>
              待审消息 {pendingReview.length}
            </Link>
            <Link href={`/projects/${projectId}/2d-upgrade?panel=computers&return_to=${encodeURIComponent(selfPath)}&from=observability`}>
              Runner 在线 {onlineComputers}/{computers.length}
            </Link>
            <Link href={`/projects/${projectId}/2d-upgrade?panel=git&return_to=${encodeURIComponent(selfPath)}&from=observability`}>
              Git 回退 / 版本索引
            </Link>
          </div>
        </aside>
      </section>

      <section className={styles.servicePanel} aria-label="服务实例健康">
        <div className={styles.sectionHead}>
          <span>服务实例健康</span>
          <h2>先确认你看的页面连的是哪个 API。</h2>
        </div>
        <div className={styles.serviceGrid}>
          <article>
            <span>API 状态</span>
            <strong>{text(health.status, healthState.error ? "不可用" : "未知")}</strong>
            <p>{healthState.error ? `${healthState.error.status} · ${healthState.error.message}` : "当前页面服务端读取 /api/health 的结果。"}</p>
          </article>
          <article>
            <span>API 实例</span>
            <strong>{text(health.base_url ?? health.baseUrl, "未确认")}</strong>
            <p>PID {text(health.pid, "未知")} · version {text(health.version, "未知")}</p>
          </article>
          <article>
            <span>本机端口</span>
            <strong>{listeningPorts.length ? listeningPorts.join(" / ") : "未探测"}</strong>
            <p>用于识别 3000/3001、8010/8011 是否同时存在旧实例。</p>
          </article>
        </div>
        <div className={styles.portList}>
          {localServices.map((item) => (
            <span key={`${text(item.host, "127.0.0.1")}:${text(item.port, "")}`} data-live={item.listening ? "1" : "0"}>
              {text(item.host, "127.0.0.1")}:{text(item.port, "?")} {item.listening ? "监听中" : "未监听"}
            </span>
          ))}
          {!localServices.length ? <span data-live="0">API 未返回本机端口探测</span> : null}
        </div>
      </section>

      <section className={styles.referencePanel}>
        <div className={styles.sectionHead}>
          <span>开源观测参考</span>
          <h2>平台不做全量日志仓库，只把真实协作链路看清。</h2>
        </div>
        <div className={styles.referenceGrid}>
          {referenceSignals.map(([name, source, detail]) => (
            <article key={name}>
              <span>{source}</span>
              <strong>{name}</strong>
              <p>{detail}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
