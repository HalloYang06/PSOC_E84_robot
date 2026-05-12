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
import { ModelImportInspector } from "./model-import-inspector";
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
  if (value.includes("/skill-forge")) return "返回 Skill 工坊";
  return "返回来源";
}

function withReturnTo(projectId: string, panel: string, returnTo: string, action?: string) {
  const params = new URLSearchParams({ panel, return_to: returnTo, from: "robotics" });
  if (action) params.set("action", action);
  return `/projects/${projectId}/2d-upgrade?${params.toString()}`;
}

const topicRows = [
  ["/joint_states", "sensor_msgs/JointState", "32 Hz", "只读"],
  ["/tf", "tf2_msgs/TFMessage", "60 Hz", "只读"],
  ["/camera/front", "sensor_msgs/Image", "12 Hz", "存档"],
  ["/imu/data", "sensor_msgs/Imu", "100 Hz", "波形"],
];

const externalTools = [
  ["Foxglove", "3D / TF / rosbag", "layout"],
  ["PlotJuggler", "高频波形", "timeseries"],
  ["Gazebo / Webots", "仿真状态", "sim"],
  ["rosbridge", "WebSocket 只读桥", "bridge"],
];

const operationQueue = [
  ["导入模型", "URDF / GLTF / GLB", "本地解析"],
  ["连接仿真", "Gazebo / Webots / Isaac", "等 Runner"],
  ["采集数据", "audio / imu / joint / camera", "可送数据工场"],
  ["安全动作", "上电 / 运动 / 写串口", "人审"],
];

const safetyGates = [
  ["只读观察", "topic / bag / 日志 / 数据预览"],
  ["仿真优先", "先在 Gazebo / Webots / Isaac 验证"],
  ["人审写入", "部署 / 回退 / 硬件动作需要审核"],
];

const waveformBars = [34, 58, 42, 82, 46, 70, 38, 92, 54, 76, 44, 66, 52, 86, 48, 62, 36, 72];

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
  const readiness = Math.min(
    100,
    Math.round((onlineComputers ? 32 : 0) + (documents.length ? 18 : 0) + (skills.length ? 18 : 0) + (workstations.length ? 18 : 0) + (seats.length ? 14 : 0)),
  );

  const navItems = [
    ["模型", "#model"],
    ["遥测", "#telemetry"],
    ["工具", "#tools"],
    ["安全", "#safety"],
  ];
  const metrics = [
    ["就绪", `${readiness}%`],
    ["Runner", `${onlineComputers}/${computers.length}`],
    ["NPC", `${seats.length}`],
    ["工位", `${workstations.length}`],
    ["Skill", `${skills.length}`],
  ];
  const leftLinks = [
    ["主页面", `/projects/${projectId}/2d-upgrade?return_to=${encodeURIComponent(selfPath)}&from=robotics`],
    ["NPC 工作台", `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`],
    ["数据工场", `/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics`],
    ["AI 实验室", `/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=robotics`],
  ];
  const rightLinks = [
    ["接入电脑", withReturnTo(projectId, "computers", selfPath)],
    ["绑定 NPC", withReturnTo(projectId, "threads", selfPath)],
    ["关联知识库", withReturnTo(projectId, "knowledge", selfPath)],
    ["安装 Skill", withReturnTo(projectId, "skills", selfPath)],
    ["派给 NPC", `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`],
  ];

  return (
    <main className={styles.shell}>
      <aside className={styles.leftRail}>
        <Link className={styles.brand} href={`/projects/${projectId}/map?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>
          <span>Robot</span>
          <strong>现场</strong>
        </Link>
        <nav>
          {navItems.map(([label, href]) => <a key={label} href={href}>{label}</a>)}
        </nav>
        <div className={styles.leftLinks}>
          {leftLinks.map(([label, href]) => <Link key={label} href={href}>{label}</Link>)}
          {returnTo ? <Link href={returnTo}>{labelProjectReturnPath(returnTo)}</Link> : null}
        </div>
      </aside>

      <section className={styles.workspace}>
        <header className={styles.workspaceHead}>
          <div>
            <span>{text(project.name, "项目")}</span>
            <h1>机器人开发现场</h1>
          </div>
          <Link href={withReturnTo(projectId, "computers", selfPath)}>接入 Runner</Link>
        </header>

        <section className={styles.metrics} aria-label="现场状态">
          {metrics.map(([label, value]) => (
            <article key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </article>
          ))}
        </section>

        <section className={styles.commandDeck} id="model" aria-label="机器人现场总控">
          <section className={styles.viewportPanel}>
            <div className={styles.panelHead}>
              <span>模型 / 仿真状态</span>
              <div className={styles.segmented}>
                <button type="button">模型</button>
                <button type="button">TF</button>
                <button type="button">仿真</button>
              </div>
            </div>
            <div className={styles.scene}>
              <div className={styles.sceneReadout}>
                <strong>等待真实模型或 ROS 同步</strong>
                <span>导入 URDF / GLTF 后识别关节；Runner 可同步 robot_description、TF、joint_states。</span>
              </div>
              <div className={styles.floorGrid} />
              <div className={styles.viewerFrame}>
                <div className={styles.viewerCore}>
                  <i />
                  <i />
                  <i />
                  <i />
                </div>
              </div>
              <div className={styles.layerDock}>
                <span>URDF</span>
                <span>TF</span>
                <span>Joint</span>
                <span>Map</span>
              </div>
            </div>
          </section>

          <section className={styles.modelColumn}>
            <ModelImportInspector />
            <div className={styles.operationQueue}>
              <div className={styles.panelHead}>
                <span>下一步</span>
                <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>派单</Link>
              </div>
              {operationQueue.map(([label, detail, state]) => (
                <article key={label}>
                  <strong>{label}</strong>
                  <p>{detail}</p>
                  <span>{state}</span>
                </article>
              ))}
            </div>
          </section>
        </section>

        <section className={styles.telemetryGrid} id="telemetry">
          <section className={styles.topicPanel}>
            <div className={styles.panelHead}>
              <span>Topic / 数据流</span>
              <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>查看日志</Link>
            </div>
            <div className={styles.topicTable}>
              {topicRows.map(([topic, type, rate, mode]) => (
                <article key={topic}>
                  <strong>{topic}</strong>
                  <span>{type}</span>
                  <small>{rate}</small>
                  <em>{mode}</em>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.wavePanel}>
            <div className={styles.panelHead}>
              <span>波形 / 事件对齐</span>
              <Link href={`/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>入库</Link>
            </div>
            <div className={styles.waveform}>
              {waveformBars.map((height, index) => <i key={`${height}-${index}`} style={{ ["--h" as string]: `${height}%` }} />)}
            </div>
            <div className={styles.signalRows}>
              <span>audio.in</span>
              <span>imu.acc</span>
              <span>joint.pos</span>
            </div>
          </section>
        </section>

        <section className={styles.bottomGrid}>
          <section className={styles.devicePanel}>
            <div className={styles.panelHead}>
              <span>电脑 / Runner</span>
              <Link href={withReturnTo(projectId, "computers", selfPath)}>管理</Link>
            </div>
            <div className={styles.deviceList}>
              {computers.length ? computers.slice(0, 6).map((node) => (
                <article key={text(node.id, text(node.name, "computer"))}>
                  <strong>{text(node.name ?? node.runner_id ?? node.id, "未命名电脑")}</strong>
                  <span>{text(node.runner_effective_status ?? node.runner_status ?? node.status, "未知状态")}</span>
                </article>
              )) : <p className={styles.emptyHint}>还没有电脑接入。</p>}
            </div>
          </section>

          <section className={styles.safetyPanel} id="safety">
            <div className={styles.panelHead}>
              <span>安全闸门</span>
              <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>审计</Link>
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
        </section>
      </section>

      <aside className={styles.rightRail} id="tools">
        <section>
          <span>平台动作</span>
          <div className={styles.toolList}>
            {rightLinks.map(([label, href]) => <Link key={label} href={href}>{label}</Link>)}
          </div>
        </section>
        <section>
          <span>外部工具</span>
          <div className={styles.externalList}>
            {externalTools.map(([label, detail, state]) => (
              <article key={label}>
                <strong>{label}</strong>
                <small>{detail}</small>
                <em>{state}</em>
              </article>
            ))}
          </div>
        </section>
        <section>
          <span>项目资源</span>
          <div className={styles.resourceList}>
            <div><strong>{documents.length}</strong><small>知识库</small></div>
            <div><strong>{skills.length}</strong><small>Skill</small></div>
            <div><strong>{bossPlans.length}</strong><small>计划</small></div>
          </div>
        </section>
      </aside>
    </main>
  );
}
