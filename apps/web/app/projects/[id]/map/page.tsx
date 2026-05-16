import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getApiHealthState,
  getProjectComputerNodesState,
  getProjectKnowledgeDocumentsState,
  getProjectSkillsState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
} from "../../../../lib/server-data";
import styles from "./map.module.css";

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
  if (value.includes("/2d-upgrade")) return "返回项目入口";
  if (value.includes("/workbench")) return "返回 NPC 工作台";
  if (value.includes("/datasets")) return "返回数据工场";
  if (value.includes("/ai-lab")) return "返回 AI 实验室";
  if (value.includes("/robotics")) return "返回机器人现场";
  if (value.includes("/observability")) return "返回观测台";
  if (value.includes("/skill-forge")) return "返回能力工坊";
  if (value.includes("/company")) return "返回公司层";
  return "返回来源";
}

const surfaceGroups = [
  {
    title: "资源治理",
    note: "电脑、执行线程、NPC、工位、能力包、GitHub 知识库都回主页面维护。",
    items: [
      ["项目主页面", "资源源头和治理面", "2d-upgrade"],
      ["驾驶舱", "项目合格性、KPI、广播", "cockpit"],
      ["公司层", "工位长会议室和跨工位入口", "company"],
    ],
  },
  {
    title: "协作执行",
    note: "完整过程在桌面线程，平台显示最小回执、异常和下一步。",
    items: [
      ["NPC 工作台", "多 NPC 对话瓷砖、审核、派单、回执", "workbench"],
      ["观测台", "派单、回执、待审、执行电脑和风险观测", "observability"],
    ],
  },
  {
    title: "专业工作台",
    note: "面向数据、调试、机器人和长期能力沉淀的同级页面。",
    items: [
      ["数据工场", "训练数据采集、标注、质检和导出", "datasets"],
      ["AI 实验室", "AI 调试、仿真和审批边界", "ai-lab"],
      ["机器人现场", "App、Linux、ROS、硬件和 VLA 现场", "robotics"],
      ["能力工坊", "能力包起草、审查、绑定和复用", "skill-forge"],
    ],
  },
];

export default async function ProjectMapPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { return_to?: string; from?: string };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/map`)}`);
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

  const [computersState, seatsState, workstationsState, skillsState, docsState, healthState] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
    getProjectSkillsState(projectId),
    getProjectKnowledgeDocumentsState(projectId),
    getApiHealthState(),
  ]);
  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(seatsState.data);
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const skills = asArray<AnyRecord>(skillsState.data);
  const docs = asArray<AnyRecord>(docsState.data);
  const health = (healthState.data ?? {}) as AnyRecord;
  const localServices = asArray<AnyRecord>(health.local_services ?? health.localServices);
  const listeningPorts = localServices.filter((item) => Boolean(item.listening)).map((item) => text(item.port, ""));
  const hasMultipleFrontendPorts = listeningPorts.includes("3000") && listeningPorts.includes("3001");
  const onlineComputers = computers.filter((node) => /online|ready|active/.test(statusText(node.runner_effective_status ?? node.runner_status ?? node.status))).length;
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/map`;
  const readiness = [
    {
      title: "资源底座",
      value: onlineComputers && seats.length && workstations.length ? "可执行" : "待补齐",
      detail: `电脑 ${onlineComputers}/${computers.length} · NPC ${seats.length} · 工位 ${workstations.length}`,
      href: `/projects/${projectId}/2d-upgrade?return_to=${encodeURIComponent(selfPath)}&from=map`,
    },
    {
      title: "知识与能力包",
      value: skills.length && docs.length ? "可复用" : "待沉淀",
      detail: `能力包 ${skills.length} · 知识库 ${docs.length}`,
      href: `/projects/${projectId}/skill-forge?return_to=${encodeURIComponent(selfPath)}&from=map`,
    },
    {
      title: "服务实例",
      value: text(health.base_url ?? health.baseUrl, healthState.error ? "不可用" : "待确认"),
      detail: hasMultipleFrontendPorts ? "多个前端实例同时在线，先到观测台确认当前页面。" : `服务端口 ${listeningPorts.join(" / ") || "未探测"}`,
      href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=map`,
    },
  ];
  const nextActions = [
    onlineComputers ? null : ["接入电脑 / 执行线程", `/projects/${projectId}/2d-upgrade?panel=computers&return_to=${encodeURIComponent(selfPath)}&from=map`],
    seats.length ? null : ["绑定 NPC 线程", `/projects/${projectId}/2d-upgrade?panel=npcs&return_to=${encodeURIComponent(selfPath)}&from=map`],
    skills.length ? null : ["准备项目能力包", `/projects/${projectId}/skill-forge?return_to=${encodeURIComponent(selfPath)}&from=map`],
    docs.length ? null : ["索引 GitHub 知识库", `/projects/${projectId}/2d-upgrade?panel=knowledge&return_to=${encodeURIComponent(selfPath)}&from=map`],
    hasMultipleFrontendPorts ? ["确认当前服务实例", `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=map`] : null,
  ].filter(Boolean) as string[][];

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <nav>
          <Link href="/projects">项目列表</Link>
          <Link href={`/projects/${projectId}`}>项目入口</Link>
          {returnTo ? <Link href={returnTo}>{labelProjectReturnPath(returnTo)}</Link> : null}
        </nav>
        <div>
          <span>电脑 {onlineComputers}/{computers.length}</span>
          <span>NPC {seats.length}</span>
          <span>工位 {workstations.length}</span>
          <span>能力包 {skills.length}</span>
          <span>知识库 {docs.length}</span>
        </div>
      </header>

      <section className={styles.hero}>
        <span>项目导航</span>
        <h1>{text(project.name, "项目")} 工作台地图</h1>
        <p>页面越来越多时，地图负责告诉你每个入口的职责：主页面管资源，工作台管执行，专业页面管数据、仿真、机器人、观测和能力包。</p>
      </section>

      <section className={styles.commandCenter} aria-label="项目就绪度">
        <div className={styles.readinessGrid}>
          {readiness.map((item) => (
            <Link key={item.title} href={item.href} className={styles.readinessCard}>
              <span>{item.title}</span>
              <strong>{item.value}</strong>
              <p>{item.detail}</p>
            </Link>
          ))}
        </div>
        <aside className={styles.nextPanel}>
          <span>建议下一步</span>
          <div>
            {nextActions.map(([label, href]) => (
              <Link key={label} href={href}>{label}</Link>
            ))}
            {!nextActions.length ? <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=map`}>进入 NPC 工作台派单</Link> : null}
          </div>
        </aside>
      </section>

      <section className={styles.groups}>
        {surfaceGroups.map((group) => (
          <article key={group.title} className={styles.group}>
            <div className={styles.groupHead}>
              <span>{group.title}</span>
              <p>{group.note}</p>
            </div>
            <div className={styles.surfaceGrid}>
              {group.items.map(([label, detail, path]) => (
                <Link
                  key={path}
                  href={`/projects/${projectId}/${path}?return_to=${encodeURIComponent(selfPath)}&from=map`}
                  className={styles.surface}
                >
                  <strong>{label}</strong>
                  <p>{detail}</p>
                </Link>
              ))}
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
