import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectBossPlansState,
  getProjectComputerNodesState,
  getProjectKnowledgeDocumentsState,
  getProjectSkillsState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
} from "../../../../lib/server-data";
import styles from "./robotics.module.css";

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
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/robotics")) return "返回机器人现场";
  if (value.includes("/observability")) return "返回观测台";
  return "返回来源";
}

function withReturnTo(projectId: string, panel: string, returnTo: string, action?: string) {
  const params = new URLSearchParams({ panel, return_to: returnTo, from: "robotics" });
  if (action) params.set("action", action);
  return `/projects/${projectId}/2d-upgrade?${params.toString()}`;
}

const openSourceRadar = [
  {
    name: "LeRobot Dataset",
    source: "Hugging Face LeRobot",
    detail: "同步视频和状态/动作数据，适合机器人 episode、VLA 数据和训练包版本化。",
    href: "https://github.com/huggingface/lerobot",
  },
  {
    name: "ROS 遥测和回放",
    source: "Foxglove Studio",
    detail: "机器人调试需要 topic、bag、TF、相机和传感器面板，而不是只看日志。",
    href: "https://github.com/foxglove/studio",
  },
  {
    name: "AI 运行观测",
    source: "Phoenix / Langfuse",
    detail: "把 prompt、工具调用、回执、评测、artifact 和失败样本纳入 trace。",
    href: "https://github.com/Arize-ai/phoenix",
  },
  {
    name: "实验和提示词版本",
    source: "Langfuse",
    detail: "实验、prompt 版本、dataset 和评测需要能被项目成员复盘。",
    href: "https://github.com/langfuse/langfuse",
  },
];

const lanes = [
  ["App / 前端", "小程序、移动端、遥操作 UI、采集入口", "连到数据工场"],
  ["Linux / ROS", "节点、topic、bag、launch、日志、远端主机", "连到 Runner"],
  ["硬件 / 控制", "串口、烧录、上电、运动控制、急停", "强制人审"],
  ["VLA / 训练", "episode、指令、模型、评测、artifact", "连到实验追踪"],
];

const safetyGates = [
  ["只读观察", "日志、topic、数据集预览、仿真结果可以直接查看。"],
  ["人审执行", "跨电脑指令、持续自动化、回退、部署、数据删除需要确认。"],
  ["硬件锁", "真实运动、上电、烧录、串口写入默认锁住，必须有人确认。"],
];

export default async function ProjectRoboticsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { return_to?: string; from?: string };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/robotics`)}`);
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
    skillsState,
    documentsState,
    bossPlansState,
  ] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
    getProjectSkillsState(projectId),
    getProjectKnowledgeDocumentsState(projectId),
    getProjectBossPlansState(projectId, 5),
  ]);

  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(seatsState.data);
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const skills = asArray<AnyRecord>(skillsState.data);
  const documents = asArray<AnyRecord>(documentsState.data);
  const bossPlans = asArray<AnyRecord>(bossPlansState.data);
  const onlineComputers = computers.filter((node) => /online|ready|active/.test(statusText(node.runner_effective_status ?? node.runner_status ?? node.status))).length;
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/robotics`;

  const telemetryReadiness = Math.min(100, Math.round(((onlineComputers ? 35 : 0) + (documents.length ? 20 : 0) + (skills.length ? 20 : 0) + (workstations.length ? 15 : 0) + (seats.length ? 10 : 0))));

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <nav>
          <Link href={`/projects/${projectId}/cockpit`}>驾驶舱</Link>
          <Link href={`/projects/${projectId}/2d-upgrade?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>主页面</Link>
          <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>NPC 工作台</Link>
          <Link href={`/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>数据工场</Link>
          <Link href={`/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>AI 实验室</Link>
          <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>观测台</Link>
          <Link href={`/projects/${projectId}/company?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>公司层</Link>
          {returnTo ? <Link href={returnTo}>{labelProjectReturnPath(returnTo)}</Link> : null}
        </nav>
        <div>
          <span>电脑 {onlineComputers}/{computers.length}</span>
          <span>工位 {workstations.length}</span>
          <span>NPC {seats.length}</span>
        </div>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroText}>
          <span>一级工作台</span>
          <h1>{text(project.name, "项目")} 机器人现场</h1>
          <p>把 App、Linux、ROS、硬件、VLA 训练和多电脑 Runner 放到同一个现场视图里，看资源、看风险、看实验闭环。</p>
          <div className={styles.heroActions}>
            <Link href={withReturnTo(projectId, "computers", selfPath)}>接入电脑</Link>
            <Link href={`/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>进入仿真</Link>
            <Link href={`/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>查看数据</Link>
          </div>
        </div>
        <div className={styles.radar}>
          <div className={styles.radarDial} style={{ ["--ready" as string]: `${telemetryReadiness}%` }}>
            <strong>{telemetryReadiness}</strong>
            <span>现场就绪度</span>
          </div>
          <dl>
            <div><dt>Runner</dt><dd>{onlineComputers}/{computers.length}</dd></div>
            <div><dt>知识库</dt><dd>{documents.length}</dd></div>
            <div><dt>Skill</dt><dd>{skills.length}</dd></div>
            <div><dt>计划</dt><dd>{bossPlans.length}</dd></div>
          </dl>
        </div>
      </section>

      <section className={styles.lanes} aria-label="机器人开发分区">
        {lanes.map(([label, detail, link]) => (
          <article key={label}>
            <span>{link}</span>
            <strong>{label}</strong>
            <p>{detail}</p>
          </article>
        ))}
      </section>

      <section className={styles.board}>
        <aside className={styles.timeline}>
          <strong>现场链路</strong>
          <ol>
            <li>电脑 Runner 上报能力和线程。</li>
            <li>AI 实验室先仿真和定义审批边界。</li>
            <li>数据工场沉淀 episode、bag、manifest 和版本。</li>
            <li>NPC 工作台只展示最小回执和最终结果。</li>
          </ol>
        </aside>

        <div className={styles.mainGrid}>
          <section className={styles.telemetryPanel}>
            <div className={styles.sectionHead}>
              <span>遥测观察</span>
              <h2>多电脑、多 topic、多日志需要一个统一入口。</h2>
            </div>
            <div className={styles.computerList}>
              {computers.length ? computers.slice(0, 6).map((node) => (
                <article key={text(node.id, text(node.name, "computer"))}>
                  <strong>{text(node.name ?? node.runner_id ?? node.id, "未命名电脑")}</strong>
                  <p>{text(node.runner_effective_status ?? node.runner_status ?? node.status, "未知状态")}</p>
                </article>
              )) : <p className={styles.emptyHint}>还没有电脑接入。先回主页面生成 Runner 配对令牌。</p>}
            </div>
          </section>

          <section className={styles.safetyPanel}>
            <div className={styles.sectionHead}>
              <span>硬件安全</span>
              <h2>越接近真实设备，平台越保守。</h2>
            </div>
            <div className={styles.gateGrid}>
              {safetyGates.map(([label, detail]) => (
                <article key={label}>
                  <strong>{label}</strong>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.referencePanel}>
            <div className={styles.sectionHead}>
              <span>开源参考雷达</span>
              <h2>把成熟项目能力接进平台结构，而不是复制一个孤立工具。</h2>
            </div>
            <div className={styles.referenceGrid}>
              {openSourceRadar.map((item) => (
                <a key={item.name} href={item.href} target="_blank" rel="noreferrer">
                  <span>{item.source}</span>
                  <strong>{item.name}</strong>
                  <p>{item.detail}</p>
                </a>
              ))}
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
