import Link from "next/link";
import { redirect } from "next/navigation";
import { createProjectSkill } from "../../../actions";
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

function skillIdOf(value: AnyRecord) {
  return text(value.skill_id ?? value.skillId ?? value.id ?? value.slug, "").toLowerCase();
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

const reactBitsCatalog = [
  {
    id: "react-bits-text-motion",
    kind: "文字动效",
    examples: "BlurText / ShinyText / SplitText",
    usage: "用于页面标题、状态提示、空态，不进入长正文。",
    state: "已接入目录",
    target: "能力工坊、AI 实验室、观测台",
    permission: "L1 样式草案",
    nextStep: "先登记为项目素材 Skill，再挑一个空态做 CSS-only 试点。",
  },
  {
    id: "react-bits-evidence-cards",
    kind: "工作卡片",
    examples: "SpotlightCard / BorderGlow / AnimatedList",
    usage: "用于专业工作台的证据卡、回执卡、训练回流列表。",
    state: "下一步接组件",
    target: "数据工场、AI 实验室、观测台",
    permission: "L1 样式草案",
    nextStep: "把证据卡、训练回执卡、待审卡拆成可复用视觉配方。",
  },
  {
    id: "react-bits-data-surfaces",
    kind: "数据背景",
    examples: "DotGrid / GridScan / Noise",
    usage: "用于数据工场和机器人现场的只读状态背景，保持低对比。",
    state: "待审样式",
    target: "数据工场、机器人现场",
    permission: "L1 样式草案",
    nextStep: "做低对比只读背景，不覆盖波形、对象树和属性抽屉。",
  },
  {
    id: "react-bits-workbench-nav",
    kind: "导航组件",
    examples: "Dock / PillNav / Stepper",
    usage: "用于同级专业工作台快速切换，不替换 NPC 工作台。",
    state: "待设计",
    target: "专业工作台导航",
    permission: "L1 样式草案",
    nextStep: "只服务数据工场、AI Lab、机器人现场、观测台、能力工坊的同级切换。",
  },
  {
    id: "react-bits-media-models",
    kind: "媒体/模型",
    examples: "ModelViewer / Carousel / Masonry",
    usage: "用于机器人模型、截图、样本帧和 artifact 预览。",
    state: "待能力化",
    target: "机器人现场、数据工场、Artifact 预览",
    permission: "L1 样式草案",
    nextStep: "先登记预览能力边界，再决定是否引入运行时依赖。",
  },
];

const reactBitsAdoption = [
  ["来源确认", "GitHub: DavidHDev/react-bits", "已确认 README、组件分类和安装方式。"],
  ["授权边界", "MIT + Commons Clause", "平台内可参考/集成，但不能把组件库本身包装售卖或再分发。"],
  ["接入策略", "先目录，后精选组件", "先做素材索引和使用场景，再按页面逐个接 CSS-only 或轻依赖组件。"],
  ["保护边界", "不碰 NPC 工作台", "素材先用于能力工坊、数据工场、AI 实验室、机器人现场、观测台。"],
];

const materialAcceptance = [
  ["来源", "必须保留 GitHub/文档站链接、授权说明和接入日期。"],
  ["适用面", "每个素材必须声明目标页面，不能默认全站启用。"],
  ["权限", "默认 L1 样式草案；涉及新依赖、外链、运行时代码时升级人审。"],
  ["保护", "不改变 NPC 工作台对话框、输入框、多 NPC 瓷砖和待审结构。"],
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
  const existingSkillIds = new Set(skills.map(skillIdOf).filter(Boolean));
  const registeredMaterialCount = reactBitsCatalog.filter((item) => existingSkillIds.has(item.id)).length;
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

      <section className={styles.workbenchLayout} aria-label="能力工坊工作台">
        <aside className={styles.leftRail}>
          <article className={styles.actorCard} data-kind="lead">
            <span>主角</span>
            <strong>项目负责人</strong>
            <small>{text(project.name, "项目")}</small>
          </article>
          <article className={styles.actorCard}>
            <span>负责 NPC</span>
            <strong>{seats.length ? `${seats.length} 个 NPC 可装配` : "待创建 NPC"}</strong>
            <small>Skill 绑定仍回主页面 / NPC 管理确认。</small>
          </article>
          <section className={styles.indexPanel}>
            <span>对象索引</span>
            <article><small>项目 Skill</small><strong>{skills.length}</strong></article>
            <article><small>NPC 沉淀</small><strong>{npcAuthored.length}</strong></article>
            <article><small>素材入库</small><strong>{registeredMaterialCount}/{reactBitsCatalog.length}</strong></article>
            <article><small>知识库</small><strong>{documents.length}</strong></article>
          </section>
          <section className={styles.indexPanel}>
            <span>流程</span>
            {forgeSteps.slice(0, 5).map(([label, detail]) => (
              <article key={label}>
                <small>{label}</small>
                <strong>{detail}</strong>
              </article>
            ))}
          </section>
        </aside>

        <section className={styles.centerPane}>
          <section className={styles.debugToolbar}>
            <span>能力工坊</span>
            <small>来源治理</small>
            <small>绑定 {assignments.length}</small>
            <small>草稿 {draftSkills.length}</small>
            <small>权限 人审启用</small>
          </section>

          <section className={styles.mainSurface} aria-label="Skill 仓库">
            <div className={styles.surfaceHead}>
              <span>中央工作区</span>
              <strong>Skill 仓库 / 素材治理</strong>
              <p>这里保留能直接操作的 Skill、素材来源、绑定对象和审核边界；旧的长说明区已经收进右侧抽屉。</p>
            </div>
            <div className={styles.skillGrid}>
              {skills.slice(0, 8).map((skill) => (
                <article key={text(skill.id ?? skill.name, text(skill.title, "skill"))}>
                  <span>{text(skill.source ?? skill.category, "项目 Skill")}</span>
                  <strong>{text(skill.name ?? skill.title ?? skill.id, "未命名 Skill")}</strong>
                  <p>{text(skill.description ?? skill.note ?? skill.source, "暂无说明")}</p>
                </article>
              ))}
              {!skills.length ? (
                <article>
                  <span>空仓库</span>
                  <strong>还没有 Skill</strong>
                  <p>从 GitHub 导入，或让 NPC 在工作台起草一个最小 Skill。</p>
                </article>
              ) : null}
            </div>
          </section>

          <section className={styles.materialSurface} aria-label="React Bits 素材治理">
            <div className={styles.surfaceHead}>
              <span>素材治理</span>
              <strong>React Bits 候选素材</strong>
              <p>素材先登记为 Skill，再按页面试点；不直接替换 NPC 工作台。</p>
            </div>
            <div className={styles.materialRows}>
              {reactBitsCatalog.map((item) => {
                const registered = existingSkillIds.has(item.id);
                return (
                  <article key={item.id} data-registered={registered ? "1" : "0"}>
                    <div>
                      <span>{item.state}</span>
                      <strong>{item.kind}</strong>
                      <p>{item.examples} · {item.target}</p>
                    </div>
                    {registered ? (
                      <small>已入库</small>
                    ) : (
                      <form action={createProjectSkill.bind(null, projectId)}>
                        <input type="hidden" name="return_to" value={selfPath} />
                        <input type="hidden" name="skill_id" value={item.id} />
                        <input type="hidden" name="label" value={`${item.kind}素材治理`} />
                        <input type="hidden" name="source" value="github-material" />
                        <input type="hidden" name="category" value="frontend-material" />
                        <input type="hidden" name="repo_relative_path" value="" />
                        <input type="hidden" name="recommended_for" value="frontend, ui, professional-workbench, material-governance" />
                        <input
                          type="hidden"
                          name="note"
                          value={`React Bits 候选素材：${item.examples}。用途：${item.usage} 目标：${item.target}。权限：${item.permission}。下一步：${item.nextStep} 来源 https://github.com/DavidHDev/react-bits 和 https://reactbits.dev/。保护边界：不碰 NPC 工作台结构；引入运行时依赖、外链、复制组件代码前必须做供应链和授权审查。`}
                        />
                        <button type="submit">入库</button>
                      </form>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        </section>

        <aside className={styles.rightRail}>
          <section className={styles.toolPanel}>
            <span>功能</span>
            <Link href={withReturnTo(projectId, "skills", selfPath, "github-import")}>导入 GitHub Skill</Link>
            <Link href={withReturnTo(projectId, "skills", selfPath)}>管理 Skill 仓库</Link>
            <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=skill-forge`}>派 NPC 起草</Link>
            <a href="https://github.com/DavidHDev/react-bits" target="_blank" rel="noreferrer">React Bits 源仓库</a>
          </section>

          <details className={styles.drawerPanel} open>
            <summary><span>绑定对象</span><strong>{assignments.length}</strong></summary>
            <dl>
              <div><dt>NPC</dt><dd>{seats.length}</dd></div>
              <div><dt>工位</dt><dd>{workstations.length}</dd></div>
              <div><dt>绑定</dt><dd>{assignments.length}</dd></div>
            </dl>
          </details>

          <details className={styles.drawerPanel}>
            <summary><span>素材规则</span><strong>{materialAcceptance.length}</strong></summary>
            <div className={styles.drawerRows}>
              {materialAcceptance.map(([label, detail]) => (
                <article key={label}>
                  <span>{label}</span>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
          </details>

          <details className={styles.drawerPanel}>
            <summary><span>参考</span><strong>{references.length}</strong></summary>
            <div className={styles.drawerRows}>
              {references.map(([name, source, detail]) => (
                <article key={name}>
                  <span>{source}</span>
                  <strong>{name}</strong>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
          </details>
        </aside>
      </section>

      <section className={styles.bottomDock} aria-label="能力工坊日志">
        <div>
          <span>信息日志</span>
          <strong>能力治理</strong>
        </div>
        {reactBitsAdoption.map(([label, value, detail]) => (
          <article key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <p>{detail}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
