import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectKnowledgeDocumentsState,
  getProjectSkillsState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
  getSeatSkillAssignmentsState,
} from "../../../../lib/server-data";
import styles from "./skill-forge.module.css";

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
  if (value.includes("/observability")) return "返回观测台";
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/skill-forge")) return "返回 Skill 工坊";
  return "返回来源";
}

function withReturnTo(projectId: string, panel: string, returnTo: string, action?: string) {
  const params = new URLSearchParams({ panel, return_to: returnTo, from: "skill-forge" });
  if (action) params.set("action", action);
  return `/projects/${projectId}/2d-upgrade?${params.toString()}`;
}

const forgeSteps = [
  ["发现", "NPC 在真实开发里反复使用的流程、检查项、上下文，可以成为 Skill 候选。"],
  ["起草", "只生成 SKILL.md 和必要 references/scripts/assets，不堆 README、安装指南、周报。"],
  ["审查", "检查触发描述、上下文长度、供应链风险、是否会越权操作。"],
  ["绑定", "把 Skill 绑定到 Boss、工位长、QA、机器人、数据工场等角色。"],
  ["复用", "后续派单自动带上 Skill loadout，平台只显示来源、版本和回执。"],
];

const references = [
  ["Acontext", "技能作为 Agent 记忆层", "把稳定过程压缩成可复用 Skill，而不是无限增长聊天记录。"],
  ["OpenAI Agents", "handoff / guardrails", "Skill 要有边界：什么时候触发、什么时候转交、什么时候人审。"],
  ["CrewAI / LangGraph", "tools + memory", "Skill 不只是文档，也可以绑定脚本、检查器、工具使用流程。"],
  ["Supply-chain review", "Skill 市场风险", "导入第三方 Skill 前必须可见来源、版本、权限和禁用开关。"],
];

export default async function ProjectSkillForgePage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { return_to?: string; from?: string };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/skill-forge`)}`);
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

  const [skillsState, documentsState, assignmentsState, seatsState, workstationsState] = await Promise.all([
    getProjectSkillsState(projectId),
    getProjectKnowledgeDocumentsState(projectId),
    getSeatSkillAssignmentsState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
  ]);

  const skills = asArray<AnyRecord>(skillsState.data);
  const documents = asArray<AnyRecord>(documentsState.data);
  const assignments = asArray<AnyRecord>(assignmentsState.data);
  const seats = asArray<AnyRecord>(seatsState.data);
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const draftSkills = skills.filter((item) => /draft|pending|review/i.test(text(item.draft_status ?? item.draftStatus ?? item.status, "")));
  const npcAuthored = skills.filter((item) => /npc|agent/i.test(text(item.source ?? item.created_by_type ?? item.author_type, "")));
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/skill-forge`;

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <nav>
          <Link href={`/projects/${projectId}/cockpit`}>驾驶舱</Link>
          <Link href={`/projects/${projectId}/map?return_to=${encodeURIComponent(selfPath)}&from=skill-forge`}>地图</Link>
          <Link href={`/projects/${projectId}/2d-upgrade?return_to=${encodeURIComponent(selfPath)}&from=skill-forge`}>主页面</Link>
          <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=skill-forge`}>NPC 工作台</Link>
          <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=skill-forge`}>观测台</Link>
          {returnTo ? <Link href={returnTo}>{labelProjectReturnPath(returnTo)}</Link> : null}
        </nav>
        <div>
          <span>Skill {skills.length}</span>
          <span>草稿 {draftSkills.length}</span>
          <span>绑定 {assignments.length}</span>
        </div>
      </header>

      <section className={styles.hero}>
        <div>
          <span>一级工作台</span>
          <h1>{text(project.name, "项目")} Skill 工坊</h1>
          <p>把 NPC 在真实开发里沉淀出的稳定经验，变成可审查、可绑定、可禁用、可复用的 Skill，而不是让仓库堆满散文档。</p>
          <div className={styles.heroActions}>
            <Link href={withReturnTo(projectId, "skills", selfPath, "github-import")}>导入 GitHub Skill</Link>
            <Link href={withReturnTo(projectId, "skills", selfPath)}>管理 Skill 仓库</Link>
            <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=skill-forge`}>派 NPC 起草</Link>
          </div>
        </div>
        <div className={styles.matrix}>
          <strong>{skills.length}</strong>
          <span>项目 Skill</span>
          <strong>{npcAuthored.length}</strong>
          <span>NPC 沉淀</span>
          <strong>{documents.length}</strong>
          <span>知识库路径</span>
        </div>
      </section>

      <section className={styles.pipeline}>
        {forgeSteps.map(([label, detail], index) => (
          <article key={label}>
            <small>{String(index + 1).padStart(2, "0")}</small>
            <strong>{label}</strong>
            <p>{detail}</p>
          </article>
        ))}
      </section>

      <section className={styles.board}>
        <div className={styles.skillList}>
          <div className={styles.sectionHead}>
            <span>当前 Skill</span>
            <h2>先看来源和绑定，再决定是否放进长期上下文。</h2>
          </div>
          <div className={styles.rows}>
            {skills.slice(0, 10).map((skill) => (
              <article key={text(skill.id ?? skill.name, text(skill.title, "skill"))}>
                <strong>{text(skill.name ?? skill.title ?? skill.id, "未命名 Skill")}</strong>
                <p>{text(skill.description ?? skill.note ?? skill.source, "暂无说明")}</p>
              </article>
            ))}
            {!skills.length ? <article><strong>还没有 Skill</strong><p>从 GitHub 导入或让 NPC 在工作台起草一个最小 Skill。</p></article> : null}
          </div>
        </div>

        <aside className={styles.side}>
          <div className={styles.sectionHead}>
            <span>绑定对象</span>
            <h2>Skill 应该跟角色走。</h2>
          </div>
          <dl>
            <div><dt>NPC</dt><dd>{seats.length}</dd></div>
            <div><dt>工位</dt><dd>{workstations.length}</dd></div>
            <div><dt>绑定</dt><dd>{assignments.length}</dd></div>
          </dl>
        </aside>
      </section>

      <section className={styles.referencePanel}>
        <div className={styles.sectionHead}>
          <span>产品参考</span>
          <h2>Skill 是长期能力层，不是文档垃圾桶。</h2>
        </div>
        <div className={styles.referenceGrid}>
          {references.map(([name, source, detail]) => (
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
