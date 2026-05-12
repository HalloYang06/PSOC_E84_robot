import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectKnowledgeDocumentsState,
  getProjectMembersState,
  getProjectSkillsState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
  getSeatSkillAssignmentsState,
} from "../../../../lib/server-data";
import styles from "./datasets.module.css";

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
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/datasets")) return "返回数据工场";
  return "返回来源";
}

function withReturnTo(projectId: string, panel: string, returnTo: string) {
  const params = new URLSearchParams({ panel, return_to: returnTo, from: "datasets" });
  return `/projects/${projectId}/2d-upgrade?${params.toString()}`;
}

const dataSurfaces = [
  {
    id: "speech",
    name: "语音数据集",
    types: "音频 / 转写 / 评分 / 错误标签",
    collection: "App、小程序、网页录音、Runner 监听目录",
    annotation: "转写、发音/流利/内容评分、质检复核",
    export: "JSONL + audio manifest + audit",
  },
  {
    id: "vision",
    name: "视觉数据集",
    types: "图像 / 视频 / 帧序列",
    collection: "相机电脑、标定目录、上传批次",
    annotation: "分类、框选、分割、时间段事件",
    export: "image/video manifest + label map",
  },
  {
    id: "sensor",
    name: "传感器数据集",
    types: "IMU / 力传感器 / 电流 / 时序信号",
    collection: "机器人电脑、串口、Runner 采集任务",
    annotation: "时间窗、异常点、动作阶段、质量标记",
    export: "CSV/Parquet + sensor manifest",
  },
  {
    id: "rosbag",
    name: "ROS bag 数据集",
    types: "ROS topic / bag / TF / camera_info",
    collection: "ROS 主机、多电脑同步、GitHub 相对索引",
    annotation: "topic 完整性、场景标签、失败原因",
    export: "bag index + topic manifest + split",
  },
  {
    id: "robot_episode",
    name: "机器人轨迹数据集",
    types: "遥操作 episode / VLA 指令 / 关键帧",
    collection: "机械臂工位、训练服务器、操作员记录",
    annotation: "成功失败、语言指令、关键帧、奖励标签",
    export: "episode manifest + instruction JSONL",
  },
];

export default async function ProjectDatasetsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { return_to?: string; from?: string };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/datasets`)}`);
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
    assignmentsState,
    membersState,
  ] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
    getProjectSkillsState(projectId),
    getProjectKnowledgeDocumentsState(projectId),
    getSeatSkillAssignmentsState(projectId),
    getProjectMembersState(projectId),
  ]);

  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(threadWorkstationsState.data);
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const skills = asArray<AnyRecord>(skillsState.data);
  const documents = asArray<AnyRecord>(documentsState.data);
  const assignments = asArray<AnyRecord>(assignmentsState.data);
  const members = asArray<AnyRecord>(membersState.data);
  const onlineComputers = computers.filter((node) => /online|ready|active/.test(statusText(node.runner_effective_status ?? node.runner_status ?? node.status))).length;
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/datasets`;
  const repoReady = Boolean(project.github_url || project.local_git_url);

  const resourceCards = [
    {
      label: "Runner / 电脑",
      value: `${onlineComputers}/${computers.length}`,
      hint: "采集任务只能索引主页面接入的电脑。",
      href: withReturnTo(projectId, "computers", selfPath),
      warning: computers.length === 0 || onlineComputers === 0,
    },
    {
      label: "NPC / 线程",
      value: `${seats.length}`,
      hint: "标注、质检、导出建议由 NPC 处理，完整过程仍在桌面线程。",
      href: withReturnTo(projectId, "npc-create", selfPath),
      warning: seats.length === 0,
    },
    {
      label: "工位",
      value: `${workstations.length}`,
      hint: "数据采集、标注、模型训练可以绑定不同工位长。",
      href: withReturnTo(projectId, "development-workshop", selfPath),
      warning: workstations.length === 0,
    },
    {
      label: "Skill",
      value: `${skills.length}`,
      hint: "标注规范、隐私检查、ROS topic 检查都应沉淀成 Skill。",
      href: withReturnTo(projectId, "skills", selfPath),
      warning: skills.length === 0,
    },
    {
      label: "知识库路径",
      value: `${documents.length}`,
      hint: "schema、采集协议和导出说明使用 GitHub 仓库相对路径。",
      href: withReturnTo(projectId, "skills", selfPath),
      warning: documents.length === 0,
    },
    {
      label: "Git 仓库",
      value: repoReady ? "已设置" : "待设置",
      hint: "导出包、manifest、schema 都需要可追踪版本。",
      href: withReturnTo(projectId, "git", selfPath),
      warning: !repoReady,
    },
  ];

  const pipeline = [
    ["采集", "绑定 Runner、电脑、本地目录、ROS topic 或 App 入口。"],
    ["标注", "按数据类型进入不同标注卡片，NPC 可给建议但人可审核。"],
    ["质检", "跑隐私、schema、文件存在、时间戳连续性和安全规则。"],
    ["导出", "生成 dataset_version、manifest、split、audit，并通知相关 NPC。"],
  ];

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          <Link href={`/projects/${projectId}/cockpit`} className={styles.backLink}>驾驶舱</Link>
          <Link href={`/projects/${projectId}/2d-upgrade?return_to=${encodeURIComponent(selfPath)}&from=datasets`} className={styles.backLink}>主页面</Link>
          <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`} className={styles.backLink}>NPC 工作台</Link>
          {returnTo ? <Link href={returnTo} className={styles.backLink}>{labelProjectReturnPath(returnTo)}</Link> : null}
          <div className={styles.title}>
            <strong>{text(project.name, "项目")} · 数据工场</strong>
            <small>训练数据采集、标注、质检、导出和审计的项目级入口。</small>
          </div>
        </div>
        <div className={styles.kpis}>
          <span>成员 {members.length}</span>
          <span>电脑 {onlineComputers}/{computers.length}</span>
          <span>NPC {seats.length}</span>
          <span>Skill {skills.length}</span>
          <span>绑定 {assignments.length}</span>
        </div>
      </header>

      <div className={styles.body}>
        <aside className={styles.sidebar} aria-label="数据工场索引">
          <div className={styles.sidebarHeader}>
            <strong>数据集类型</strong>
            <small>先索引资源，再创建采集和标注任务。</small>
          </div>
          <nav className={styles.datasetList}>
            {dataSurfaces.map((surface) => (
              <a key={surface.id} href={`#${surface.id}`}>
                <span>{surface.name}</span>
                <small>{surface.types}</small>
              </a>
            ))}
          </nav>
          <div className={styles.sidebarFooter}>
            <strong>资源不在这里创建</strong>
            <p>Runner、NPC、Skill、GitHub 知识库和工位仍回主页面治理，数据工场只索引并使用。</p>
          </div>
        </aside>

        <section className={styles.mainPanel}>
          <section className={styles.hero}>
            <div>
              <p>一级工作台</p>
              <h1>数据工场</h1>
              <span>面向语音、视觉、传感器、ROS bag、机器人 episode 和文本数据的通用训练数据生产线。</span>
            </div>
            <div className={styles.heroStats}>
              <strong>{dataSurfaces.length}</strong>
              <span>通用数据类型</span>
            </div>
          </section>

          <section className={styles.resourceGrid} aria-label="主页面资源索引">
            {resourceCards.map((item) => (
              <Link key={item.label} href={item.href} className={styles.resourceCard} data-warning={item.warning ? "1" : undefined}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <small>{item.hint}</small>
              </Link>
            ))}
          </section>

          <section className={styles.pipeline} aria-label="数据生产流程">
            {pipeline.map(([label, detail], index) => (
              <article key={label}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{label}</strong>
                <p>{detail}</p>
              </article>
            ))}
          </section>

          <section className={styles.datasetGrid} aria-label="数据集能力面">
            {dataSurfaces.map((surface) => (
              <article key={surface.id} id={surface.id} className={styles.datasetCard}>
                <div className={styles.datasetCardHead}>
                  <div>
                    <span>{surface.types}</span>
                    <strong>{surface.name}</strong>
                  </div>
                  <Link href={withReturnTo(projectId, "development-workshop", selfPath)}>绑定工位</Link>
                </div>
                <dl>
                  <div>
                    <dt>采集来源</dt>
                    <dd>{surface.collection}</dd>
                  </div>
                  <div>
                    <dt>标注方式</dt>
                    <dd>{surface.annotation}</dd>
                  </div>
                  <div>
                    <dt>导出包</dt>
                    <dd>{surface.export}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </section>

          <section className={styles.auditPanel} aria-label="导出和审核闭环">
            <div>
              <span>导出闭环</span>
              <strong>dataset_version / manifest / audit / NPC 回执</strong>
              <p>导出包生成后要能通知相关 NPC，回执留在协作消息里；数据页面只显示最小状态和索引，完整处理过程仍在 Codex 或 Claude Code 桌面线程。</p>
            </div>
            <div className={styles.auditLinks}>
              <Link href={withReturnTo(projectId, "skills", selfPath)}>维护数据 Skill</Link>
              <Link href={withReturnTo(projectId, "computers", selfPath)}>绑定采集电脑</Link>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>派给 NPC</Link>
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}
