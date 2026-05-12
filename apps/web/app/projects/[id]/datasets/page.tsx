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
  if (value.includes("/ai-lab")) return "返回 AI 实验室";
  if (value.includes("/robotics")) return "返回机器人现场";
  if (value.includes("/observability")) return "返回观测台";
  if (value.includes("/skill-forge")) return "返回 Skill 工坊";
  if (value.includes("/datasets")) return "返回数据工场";
  return "返回来源";
}

function withReturnTo(projectId: string, panel: string, returnTo: string) {
  const params = new URLSearchParams({ panel, return_to: returnTo, from: "datasets" });
  return `/projects/${projectId}/2d-upgrade?${params.toString()}`;
}

const datasetTypes = [
  ["语音", "audio / transcript / score", "待标注 18"],
  ["视觉", "image / video / frame", "待复核 7"],
  ["传感器", "imu / force / current", "异常 3"],
  ["ROS bag", "topic / tf / camera_info", "缺 topic 2"],
  ["Episode", "action / state / instruction", "可训练 42"],
];

const sampleRows = [
  ["YS-voice-014", "语音", "待标注", "audio + transcript", "Frontend Miniapp"],
  ["arm-episode-022", "Episode", "待复核", "joint + camera", "Robot QA"],
  ["imu-telemetry-118", "传感器", "异常", "imu.acc gap", "Backend Data"],
  ["rosbag-2026-05-12", "ROS bag", "可训练", "tf + camera", "Boss"],
];

const qualityRows = [
  ["schema", "通过", "字段完整"],
  ["privacy", "通过", "无手机号/邮箱"],
  ["files", "待查", "2 个音频未确认"],
  ["timestamp", "警告", "IMU 有 80ms 断点"],
];

const versionRows = [
  ["dataset_v0.3.1", "JSONL + manifest", "可送实验室"],
  ["speech_seed_v2", "audio manifest", "待隐私检查"],
  ["episode_arm_v1", "episode manifest", "需复核"],
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

  const metrics = [
    ["样本", "70"],
    ["待标注", "18"],
    ["待复核", "7"],
    ["可训练", "42"],
    ["异常", "3"],
  ];
  const leftLinks = [
    ["主页面", `/projects/${projectId}/2d-upgrade?return_to=${encodeURIComponent(selfPath)}&from=datasets`],
    ["NPC 工作台", `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`],
    ["AI 实验室", `/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=datasets`],
    ["机器人现场", `/projects/${projectId}/robotics?return_to=${encodeURIComponent(selfPath)}&from=datasets`],
  ];
  const resourceCards = [
    ["Runner", `${onlineComputers}/${computers.length}`, withReturnTo(projectId, "computers", selfPath)],
    ["NPC", `${seats.length}`, withReturnTo(projectId, "npc-create", selfPath)],
    ["工位", `${workstations.length}`, withReturnTo(projectId, "development-workshop", selfPath)],
    ["Skill", `${skills.length}`, withReturnTo(projectId, "skills", selfPath)],
    ["知识库", `${documents.length}`, withReturnTo(projectId, "knowledge", selfPath)],
    ["Git", repoReady ? "已设置" : "待设置", withReturnTo(projectId, "git", selfPath)],
  ];
  const actions = [
    ["导入数据", withReturnTo(projectId, "computers", selfPath)],
    ["创建标注任务", `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`],
    ["送去实验室", `/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=datasets`],
    ["维护 Skill", withReturnTo(projectId, "skills", selfPath)],
  ];

  return (
    <main className={styles.shell}>
      <aside className={styles.leftRail}>
        <Link className={styles.brand} href={`/projects/${projectId}/map?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>
          <span>Dataset</span>
          <strong>工场</strong>
        </Link>
        <nav>
          {datasetTypes.map(([label, detail]) => (
            <a key={label} href={`#${label}`}>
              <span>{label}</span>
              <small>{detail}</small>
            </a>
          ))}
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
            <h1>数据工场</h1>
          </div>
          <Link href={`/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>送去实验室</Link>
        </header>

        <section className={styles.metrics} aria-label="数据状态">
          {metrics.map(([label, value]) => (
            <article key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </article>
          ))}
        </section>

        <section className={styles.mainGrid}>
          <section className={styles.queuePanel}>
            <div className={styles.panelHead}>
              <span>样本队列</span>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>派给 NPC</Link>
            </div>
            <div className={styles.sampleTable}>
              {sampleRows.map(([id, type, state, signal, owner]) => (
                <article key={id}>
                  <strong>{id}</strong>
                  <span>{type}</span>
                  <em>{state}</em>
                  <small>{signal}</small>
                  <small>{owner}</small>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.typePanel}>
            <div className={styles.panelHead}>
              <span>数据类型</span>
              <Link href={withReturnTo(projectId, "knowledge", selfPath)}>Schema</Link>
            </div>
            <div className={styles.typeGrid}>
              {datasetTypes.map(([label, detail, state]) => (
                <article key={label} id={label}>
                  <strong>{label}</strong>
                  <p>{detail}</p>
                  <span>{state}</span>
                </article>
              ))}
            </div>
          </section>
        </section>

        <section className={styles.opsGrid}>
          <section className={styles.qualityPanel}>
            <div className={styles.panelHead}>
              <span>质检</span>
              <Link href={withReturnTo(projectId, "skills", selfPath)}>规则</Link>
            </div>
            <div className={styles.qualityRows}>
              {qualityRows.map(([name, state, detail]) => (
                <article key={name}>
                  <strong>{name}</strong>
                  <span>{state}</span>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.versionPanel}>
            <div className={styles.panelHead}>
              <span>数据版本</span>
              <Link href={`/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>实验</Link>
            </div>
            <div className={styles.versionRows}>
              {versionRows.map(([name, bundle, state]) => (
                <article key={name}>
                  <strong>{name}</strong>
                  <small>{bundle}</small>
                  <span>{state}</span>
                </article>
              ))}
            </div>
          </section>
        </section>

        <section className={styles.resourcePanel}>
          <div className={styles.panelHead}>
            <span>主页面资源索引</span>
            <Link href={`/projects/${projectId}/2d-upgrade?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>治理</Link>
          </div>
          <div className={styles.resourceGrid}>
            {resourceCards.map(([label, value, href]) => (
              <Link key={label} href={href}>
                <span>{label}</span>
                <strong>{value}</strong>
              </Link>
            ))}
          </div>
        </section>
      </section>

      <aside className={styles.rightRail}>
        <section>
          <span>动作</span>
          <div className={styles.actionList}>
            {actions.map(([label, href]) => <Link key={label} href={href}>{label}</Link>)}
          </div>
        </section>
        <section>
          <span>项目资源</span>
          <div className={styles.resourceSummary}>
            <div><strong>{members.length}</strong><small>成员</small></div>
            <div><strong>{assignments.length}</strong><small>Skill 绑定</small></div>
            <div><strong>{documents.length}</strong><small>知识库</small></div>
          </div>
        </section>
      </aside>
    </main>
  );
}
