import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectBossPlansState,
  getProjectComputerNodesState,
  getProjectKnowledgeDocumentsState,
  getProjectMembersState,
  getProjectSkillsState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
} from "../../../../lib/server-data";
import styles from "./ai-lab.module.css";

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
  if (value.includes("/robotics")) return "返回机器人现场";
  if (value.includes("/observability")) return "返回观测台";
  if (value.includes("/skill-forge")) return "返回 Skill 工坊";
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/ai-lab")) return "返回 AI 实验室";
  return "返回来源";
}

function withReturnTo(projectId: string, panel: string, returnTo: string, action?: string) {
  const params = new URLSearchParams({ panel, return_to: returnTo, from: "ai-lab" });
  if (action) params.set("action", action);
  return `/projects/${projectId}/2d-upgrade?${params.toString()}`;
}

function itemTitle(item: AnyRecord) {
  return text(item.title ?? item.name ?? item.display_name ?? item.type ?? item.id, "未命名");
}

const simulationTracks = [
  {
    id: "software-sim",
    label: "软件任务仿真",
    summary: "让 NPC 先模拟拆解、风险、验收点和最小回执，不改文件。",
    tone: "mint",
  },
  {
    id: "robot-sim",
    label: "机器人仿真",
    summary: "把 ROS、串口、烧录、机械臂动作放进只读沙盘，硬件动作必须人审。",
    tone: "amber",
  },
  {
    id: "approval-boundary",
    label: "审批边界仿真",
    summary: "定义哪些任务能自动推进，哪些必须问人，哪些触发暂停。",
    tone: "rose",
  },
];

const guardRails = [
  ["跑飞保护", "重复原地踏步、无截图、无最终回执、越权执行时提示暂停。"],
  ["预算和心跳", "持续自动化必须显式开启；普通派单只是一句话进入绑定线程。"],
  ["硬件强审", "机器人、机械臂、串口、烧录、真实设备动作覆盖免审。"],
  ["回执最小化", "平台只显示指令、审核、最小回执和最终结果，长过程留在桌面线程。"],
];

const openSourceSignals = [
  ["实验追踪", "MLflow / ClearML", "记录 prompt、模型、参数、artifact、最终回执和验收结果。", "https://github.com/mlflow/mlflow"],
  ["ROS 可视化", "Foxglove / Webviz / ROSboard", "回放 topic、TF、相机、传感器和机器人状态，定位跨电脑问题。", "https://github.com/foxglove/studio"],
  ["仿真平台", "Gazebo / Webots", "先在仿真里跑软件和机器人动作，再决定是否接真实设备。", "https://github.com/cyberbotics/webots"],
  ["数据版本", "DVC", "让实验输入数据、模型输出和回退版本能对应到同一条审计线。", "https://github.com/iterative/dvc"],
];

const robotWorkspaces = [
  ["任务编排", "Boss 拆分软件、硬件、Linux、ROS、VLA、App 多端任务，并路由到对应工位。"],
  ["遥测观察", "Runner 上报机器状态、topic、日志、GPU/CPU、传感器延迟和最近错误。"],
  ["仿真回放", "接 Gazebo/Webots/Isaac/自研仿真结果，保留只读预演和人工确认。"],
  ["硬件闸门", "串口写入、烧录、运动控制、上电检查必须进入人审和风险记录。"],
  ["实验记录", "每次训练/测试记录数据集版本、模型版本、参数、结果和可复现命令。"],
  ["现场交接", "把长日志留在桌面线程，平台收最小回执、阻塞、截图和最终结果。"],
];

export default async function ProjectAiLabPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { return_to?: string; from?: string };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/ai-lab`)}`);
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
    threadWorkstationsState,
    workstationsState,
    skillsState,
    documentsState,
    membersState,
    bossPlansState,
  ] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
    getProjectSkillsState(projectId),
    getProjectKnowledgeDocumentsState(projectId),
    getProjectMembersState(projectId),
    getProjectBossPlansState(projectId, 3),
  ]);

  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(threadWorkstationsState.data);
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const skills = asArray<AnyRecord>(skillsState.data);
  const documents = asArray<AnyRecord>(documentsState.data);
  const members = asArray<AnyRecord>(membersState.data);
  const bossPlans = asArray<AnyRecord>(bossPlansState.data);
  const onlineComputers = computers.filter((node) => /online|ready|active/.test(statusText(node.runner_effective_status ?? node.runner_status ?? node.status))).length;
  const automatedSeats = seats.filter((seat) => Boolean(seat.automationEnabled ?? seat.automation_enabled)).length;
  const boundSeats = seats.filter((seat) => text(seat.sourceWorkstationId ?? seat.source_workstation_id ?? seat.bound_thread_id ?? seat.target_thread_id, "")).length;
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/ai-lab`;
  const leadSeat = seats.find((seat) => /boss|lead|负责人|工位长/i.test(`${itemTitle(seat)} ${text(seat.responsibility, "")}`)) ?? seats[0];

  const resourceCards = [
    {
      label: "NPC 线程",
      value: `${boundSeats}/${seats.length}`,
      detail: "仿真和调试都投递到绑定线程，完整过程在桌面端。",
      href: withReturnTo(projectId, "npc-create", selfPath),
    },
    {
      label: "Runner 电脑",
      value: `${onlineComputers}/${computers.length}`,
      detail: "多电脑能力由 Runner 上报，不改本机 Codex/Claude 配置。",
      href: withReturnTo(projectId, "computers", selfPath),
    },
    {
      label: "Skill",
      value: `${skills.length}`,
      detail: "调试规范、机器人边界、验收检查应沉淀为 Skill。",
      href: withReturnTo(projectId, "skills", selfPath),
    },
    {
      label: "知识库",
      value: `${documents.length}`,
      detail: "只使用 GitHub 仓库相对路径索引规范、schema 和仿真说明。",
      href: withReturnTo(projectId, "skills", selfPath),
    },
  ];

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          <Link href={`/projects/${projectId}/cockpit`} className={styles.navLink}>驾驶舱</Link>
          <Link href={`/projects/${projectId}/map?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`} className={styles.navLink}>地图</Link>
          <Link href={`/projects/${projectId}/2d-upgrade?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`} className={styles.navLink}>主页面</Link>
          <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`} className={styles.navLink}>NPC 工作台</Link>
          <Link href={`/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`} className={styles.navLink}>数据工场</Link>
          <Link href={`/projects/${projectId}/robotics?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`} className={styles.navLink}>机器人现场</Link>
          <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`} className={styles.navLink}>观测台</Link>
          <Link href={`/projects/${projectId}/skill-forge?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`} className={styles.navLink}>Skill 工坊</Link>
          {returnTo ? <Link href={returnTo} className={styles.navLink}>{labelProjectReturnPath(returnTo)}</Link> : null}
        </div>
        <div className={styles.topbarRight}>
          <span>成员 {members.length}</span>
          <span>电脑 {onlineComputers}/{computers.length}</span>
          <span>自动化 {automatedSeats}</span>
        </div>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>一级工作台</span>
          <h1>{text(project.name, "项目")} AI 实验室</h1>
          <p>把 AI 调试、任务仿真、机器人安全边界和审批规则从资源主页面抽出来，成为可复用的项目级沙盘。</p>
          <div className={styles.heroActions}>
            <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`}>
              派给 NPC 预演
            </Link>
            <Link href={withReturnTo(projectId, "ai-debug", selfPath, "runaway-guard")}>
              查看跑飞保护
            </Link>
          </div>
        </div>
        <div className={styles.stage} aria-label="AI 实验室运行状态">
          <div className={styles.stageHeader}>
            <span>Debug</span>
            <span>Simulate</span>
            <span>Review</span>
          </div>
          <div className={styles.traceRail}>
            <i />
            <i />
            <i />
          </div>
          <div className={styles.signalGrid}>
            <strong>{boundSeats}</strong>
            <span>绑定线程</span>
            <strong>{bossPlans.length}</strong>
            <span>Boss 计划</span>
            <strong>{guardRails.length}</strong>
            <span>安全边界</span>
          </div>
        </div>
      </section>

      <section className={styles.resourceStrip} aria-label="资源索引">
        {resourceCards.map((card) => (
          <Link key={card.label} href={card.href} className={styles.resourceItem}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <small>{card.detail}</small>
          </Link>
        ))}
      </section>

      <section className={styles.workspace}>
        <aside className={styles.rail} aria-label="AI 实验室索引">
          <a href="#debug">AI 调试</a>
          <a href="#simulation">仿真沙盘</a>
          <a href="#boundary">审批边界</a>
          <a href="#handoff">回执闭环</a>
        </aside>

        <div className={styles.content}>
          <section id="debug" className={styles.debugPanel}>
            <div className={styles.sectionHead}>
              <span>AI 调试</span>
              <h2>先看守护状态，再决定是否放大自动化。</h2>
            </div>
            <div className={styles.guardGrid}>
              {guardRails.map(([label, detail]) => (
                <article key={label}>
                  <strong>{label}</strong>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
          </section>

          <section id="simulation" className={styles.simulationPanel}>
            <div className={styles.sectionHead}>
              <span>仿真沙盘</span>
              <h2>软件、机器人、审批边界分开预演。</h2>
            </div>
            <div className={styles.trackList}>
              {simulationTracks.map((track, index) => (
                <article key={track.id} data-tone={track.tone}>
                  <div>
                    <small>{String(index + 1).padStart(2, "0")}</small>
                    <strong>{track.label}</strong>
                    <p>{track.summary}</p>
                  </div>
                  <Link href={withReturnTo(projectId, "ai-simulation", selfPath, track.id)}>打开预演</Link>
                </article>
              ))}
            </div>
          </section>

          <section id="boundary" className={styles.boundaryPanel}>
            <div className={styles.sectionHead}>
              <span>审批边界</span>
              <h2>平台默认保守，越接近硬件越要人审。</h2>
            </div>
            <div className={styles.boundaryLine}>
              <div>
                <strong>可自动</strong>
                <p>只读分析、文档整理、软件任务预演、fixture 检查。</p>
              </div>
              <div>
                <strong>需确认</strong>
                <p>跨工位转交、预算扩大、持续自动化、回退或删除。</p>
              </div>
              <div>
                <strong>强制人审</strong>
                <p>机器人运动、硬件上电、串口写入、烧录、真实设备操作。</p>
              </div>
            </div>
          </section>

          <section className={styles.robotPanel} aria-label="机器人开发预留工作面">
            <div className={styles.sectionHead}>
              <span>机器人开发预留</span>
              <h2>平台要能覆盖 App、Linux、ROS、VLA、硬件和多电脑现场。</h2>
            </div>
            <div className={styles.robotGrid}>
              {robotWorkspaces.map(([label, detail]) => (
                <article key={label}>
                  <strong>{label}</strong>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.referencePanel} aria-label="开源能力参考">
            <div className={styles.sectionHead}>
              <span>开源能力参考</span>
              <h2>吸收成熟工具的分层能力，平台负责把它们串成协作闭环。</h2>
            </div>
            <div className={styles.referenceGrid}>
              {openSourceSignals.map(([name, source, detail, href]) => (
                <a key={name} href={href} target="_blank" rel="noreferrer">
                  <span>{source}</span>
                  <strong>{name}</strong>
                  <p>{detail}</p>
                </a>
              ))}
            </div>
          </section>

          <section id="handoff" className={styles.handoffPanel}>
            <div>
              <span>回执闭环</span>
              <strong>完整过程在桌面线程，平台只显示最小状态。</strong>
              <p>
                推荐目标：{leadSeat ? itemTitle(leadSeat) : "先绑定 Boss NPC"}。从这里发起预演后，NPC 工作台负责展示用户指令、审核、最小回执和最终结果。
              </p>
            </div>
            <div className={styles.handoffActions}>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`}>
                打开 NPC 工作台
              </Link>
              <Link href={withReturnTo(projectId, "ai-debug", selfPath, "automation-toggle")}>
                管理自动化开关
              </Link>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
