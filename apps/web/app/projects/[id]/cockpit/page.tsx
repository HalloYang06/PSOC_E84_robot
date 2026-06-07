import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectBossPlansState,
  getProjectComputerNodesState,
  getProjectMembersState,
  getProjectState,
  getProjectThreadWorkstationsState,
} from "../../../../lib/server-data";
import { isNpcSeatRecord } from "../../../../lib/platform-provider";
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

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? (value as AnyRecord) : {};
}

function statusText(value: unknown) {
  return text(value, "").toLowerCase();
}

function countHumanReviewTasks(bossPlans: AnyRecord[]) {
  return bossPlans.reduce((total, plan) => {
    const tasks = asArray<AnyRecord>(plan.tasks);
    return total + tasks.filter((task) => {
      const status = statusText(task.status ?? task.state);
      return status.includes("review") || status.includes("confirm") || status.includes("待确认") || status.includes("待审");
    }).length;
  }, 0);
}

function activeComputerCount(nodes: AnyRecord[]) {
  return nodes.filter((node) => {
    const status = statusText(node.status ?? node.state ?? node.runner_status ?? node.runnerStatus);
    return /online|ready|idle|running|active|ok|可排队|在线|就绪/.test(status);
  }).length;
}

export default async function CockpitPage({ params }: { params: { id: string } }) {
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${params.id}/cockpit`)}`);
  }

  const [projectState, membersState, seatsState, computersState, bossPlansState] = await Promise.all([
    getProjectState(params.id),
    getProjectMembersState(params.id),
    getProjectThreadWorkstationsState(params.id),
    getProjectComputerNodesState(params.id),
    getProjectBossPlansState(params.id, 5),
  ]);

  const project = projectState.data;
  if (!project) {
    return (
      <main className={styles.shell}>
        <nav className={styles.topNav} aria-label="项目导航">
          <Link href="/projects">← 项目列表</Link>
        </nav>
        <section className={styles.header}>
          <div>
            <span>项目不可用</span>
            <h1>找不到这个项目</h1>
            <p>当前账号没有这个项目的访问权限，或项目已经不存在。</p>
          </div>
        </section>
      </main>
    );
  }

  const projectId = text(project.id, params.id);
  const projectName = text(project.name, `项目 ${projectId.slice(0, 8)}`);
  const members = asArray<AnyRecord>(membersState.data);
  const seats = asArray<AnyRecord>(seatsState.data).filter((seat) => isNpcSeatRecord(seat));
  const computers = asArray<AnyRecord>(computersState.data);
  const bossPlans = asArray<AnyRecord>(bossPlansState.data);
  const config = record(project.collaboration_config);
  const repoUrl = text(
    config.repo_url ?? config.repository_url ?? project.github_url ?? project.local_git_url,
    "未配置仓库",
  );
  const activeComputers = activeComputerCount(computers);
  const reviewCount = countHumanReviewTasks(bossPlans);

  return (
    <main className={styles.shell}>
      <nav className={styles.topNav} aria-label="项目导航">
        <Link href="/projects">← 项目列表</Link>
        <Link href={`/projects/${projectId}/2d-upgrade`}>🎮 游戏</Link>
        <Link href={`/projects/${projectId}/workbench`} title="打开工作台">打开工作台 →</Link>
        <Link href={`/projects/${projectId}/company`}>公司层 →</Link>
        <Link href={`/projects/${projectId}/robotics`}>设备数据工作台 →</Link>
        <Link href={`/projects/${projectId}/skill-forge`}>能力工坊 →</Link>
      </nav>

      <section className={styles.header}>
        <div>
          <span>项目驾驶舱</span>
          <h1>{projectName}</h1>
          <p>把今天要处理的项目、NPC、电脑和人工确认放在同一屏。这里保留稳定深链，旧书签和验收脚本不会被打到公司层。</p>
        </div>
        <div>
          <span>仓库</span>
          <h1>{repoUrl}</h1>
          <p>需要代码开发、回滚或 Git 预检时，先进入 NPC 工作台或能力工坊分派给具体工位。</p>
        </div>
      </section>

      <section className={styles.statusStrip} aria-label="平台状态">
        <article>
          <span>成员</span>
          <strong>{members.length}</strong>
          <small>项目成员</small>
        </article>
        <article>
          <span>NPC</span>
          <strong>{seats.length}</strong>
          <small>可协作线程</small>
        </article>
        <article>
          <span>电脑</span>
          <strong>{activeComputers}/{computers.length}</strong>
          <small>可用 / 总数</small>
        </article>
        <article>
          <span>人工确认</span>
          <strong>{reviewCount}</strong>
          <small>待处理项</small>
        </article>
      </section>

      <section className={styles.layout}>
        <aside className={styles.leftRail}>
          <div className={styles.railHead}>
            <span>今日入口</span>
            <strong>先选工作面</strong>
          </div>
          <Link className={styles.focusCard} href={`/projects/${projectId}/workbench`} title="打开工作台">
            <span>协同</span>
            <strong>打开工作台</strong>
            <p>给 Boss 或具体 NPC 发指令，查看需求、任务、回执和派工证据。</p>
          </Link>
          <Link className={styles.focusCard} href={`/projects/${projectId}/company`}>
            <span>治理</span>
            <strong>公司层</strong>
            <p>看工位链路、待确认事项、工位归属和跨工位协作状态。</p>
          </Link>
          <Link className={styles.focusCard} href={`/projects/${projectId}/robotics`}>
            <span>设备</span>
            <strong>设备数据工作台</strong>
            <p>扫描接口、创建调试窗口、采集片段、标注数据并做图表实验。</p>
          </Link>
        </aside>

        <section className={styles.centerPane}>
          <div className={styles.toolbar}>
            <div>
              <span>驾驶舱</span>
              <strong>当前需要处理的事项</strong>
            </div>
            <div className={styles.toolbarActions}>
              <Link href={`/projects/${projectId}/workbench`}>打开工作台 →</Link>
              <Link href={`/projects/${projectId}/2d-upgrade`}>返回游戏 →</Link>
            </div>
          </div>
          <div className={styles.decisionList}>
            <article className={styles.decisionItem} data-tone={reviewCount ? "review" : "warning"}>
              <strong>{reviewCount}</strong>
              <div>
                <span>人工确认</span>
                <p>{reviewCount ? "先进入公司层或 NPC 工作台处理待确认项。" : "当前没有显式待确认项，可以从工作台继续拆任务。"}</p>
              </div>
            </article>
            <article className={styles.decisionItem} data-tone={activeComputers ? "review" : "danger"}>
              <strong>{activeComputers}</strong>
              <div>
                <span>可用电脑</span>
                <p>{activeComputers ? "已有电脑可排队或执行，适合继续派工。" : "暂无可用执行电脑，先检查 Runner 或电脑接入。"}</p>
              </div>
            </article>
            <article className={styles.decisionItem} data-tone={seats.length ? "review" : "warning"}>
              <strong>{seats.length}</strong>
              <div>
                <span>NPC 线程</span>
                <p>{seats.length ? "可以从工作台打开 NPC 瓷砖并发指令。" : "还没有可用 NPC，先在工作台或主页面创建协作线程。"}</p>
              </div>
            </article>
          </div>
        </section>

        <aside className={styles.rightRail}>
          <details open>
            <summary>
              <span>下一步</span>
              <strong>主线动作</strong>
            </summary>
            <div className={styles.drawerBody}>
              <Link href={`/projects/${projectId}/workbench`}>
                <span>1</span>
                <strong>进入 NPC 工作台</strong>
                <p>选择 Boss 或具体 NPC，开始发指令和收回执。</p>
              </Link>
              <Link href={`/projects/${projectId}/company`}>
                <span>2</span>
                <strong>处理公司层确认</strong>
                <p>先确认工位归属、执行链路和待审项。</p>
              </Link>
              <Link href={`/projects/${projectId}/skill-forge`}>
                <span>3</span>
                <strong>补能力包</strong>
                <p>把重复流程沉淀成 Skill、知识库和 Git 规范。</p>
              </Link>
            </div>
          </details>
        </aside>
      </section>

      <section className={styles.bottomDock} aria-label="快捷入口">
        <div className={styles.logHeader}>
          <span>快捷入口</span>
          <strong>稳定深链</strong>
        </div>
        <div className={styles.nextRows}>
          <Link href={`/projects/${projectId}/workbench`}>
            <span>协作</span>
            <strong>NPC 工作台</strong>
            <p>对话、需求、任务。</p>
          </Link>
          <Link href={`/projects/${projectId}/robotics`}>
            <span>设备</span>
            <strong>调试窗口</strong>
            <p>终端、采集、图表。</p>
          </Link>
          <Link href={`/projects/${projectId}/company`}>
            <span>公司</span>
            <strong>运行态势</strong>
            <p>工位和确认。</p>
          </Link>
          <Link href={`/projects/${projectId}/2d-upgrade`}>
            <span>主界面</span>
            <strong>返回游戏</strong>
            <p>可视化入口。</p>
          </Link>
        </div>
      </section>
    </main>
  );
}
