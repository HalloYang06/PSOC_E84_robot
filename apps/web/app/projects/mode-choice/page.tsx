import Link from "next/link";

import {
  buildProjectEntryLiveRoute,
  buildProjectModeChoiceRoute,
  buildProjectModeDefinitions,
  buildModeShellPath,
  buildProjectModeChoicePath,
  buildProjectModeEntryPath,
  normalizeModeEntryId,
  projectEntryShellPath,
  type ModeEntryId,
  type ProjectModeDefinition,
} from "../mode-entry-paths";
import { requireModeEntryProjectContext } from "../mode-entry-server";
import styles from "../page.module.css";

type ModeChoicePageProps = {
  searchParams?: {
    projectId?: string;
    mode?: string;
  };
};

type ModeId = ModeEntryId;

export default async function ModeChoicePage({ searchParams }: ModeChoicePageProps) {
  const selectedProjectId = String(searchParams?.projectId ?? "").trim();
  const requestedMode = String(searchParams?.mode ?? "").trim();
  const selectedModeId: ModeId = normalizeModeEntryId(requestedMode);
  const returnTo = buildProjectModeChoicePath(selectedProjectId || undefined, selectedModeId);
  const { workspace, projects, selectedProject } = await requireModeEntryProjectContext(returnTo, selectedProjectId);
  const liveDefaultRoute = buildProjectEntryLiveRoute(selectedProject?.id);
  const branchPlaceholderRoute = buildProjectModeChoiceRoute(selectedProject?.id, selectedModeId);
  const modeDefinitions: ProjectModeDefinition[] = buildProjectModeDefinitions(selectedProject?.id);
  const selectedMode = modeDefinitions.find((mode) => mode.id === selectedModeId) ?? modeDefinitions[0];
  const selectedModeShellPath = selectedMode.shellPath;
  const selectedProjectLivePath = buildProjectModeEntryPath(selectedProject?.id, "2d-dev");
  const selectedProjectModeEntryPath = selectedProject
    ? buildProjectModeEntryPath(selectedProject.id, selectedMode.id)
    : "/projects";
  const selectedProjectModeBoardPath = buildProjectModeChoicePath(selectedProject?.id, selectedMode.id);
  const selectedProjectPrimaryHref = selectedProject
    ? selectedMode.id === "2d-dev"
      ? selectedProjectLivePath
      : selectedModeShellPath ?? selectedProjectModeBoardPath
    : "/projects";
  const selectedProjectPrimaryLabel = selectedProject
    ? selectedMode.id === "2d-dev"
      ? "进入当前项目 2D live 入口"
      : selectedMode.id === "2d-upgrade"
        ? "进入 2D 开发版升级版"
      : "打开当前模式占位壳"
    : "回项目管理入口页";
  const showSelectedProjectModeEntryAction = Boolean(
    selectedProject && selectedMode.id !== "2d-dev" && selectedMode.id !== "2d-upgrade",
  );
  const showSelectedProjectSecondaryAction = Boolean(selectedProject && selectedMode.id !== "2d-dev");
  const user = {
    name: String(workspace.user.name ?? workspace.user.display_name ?? "基地成员"),
    email: String(workspace.user.email ?? ""),
  };

  return (
    <main className={styles.page}>
      <section className={styles.header}>
        <div className={styles.headerCopy}>
          <span className={styles.kicker}>模式分流占位页</span>
          <h1>把 `/projects` 之后的分流层先钉成真页面。</h1>
          <p>
            这个页面不是今天的默认 live 入口，它只负责把未来四模式分流的真实位置固定在
            {" "}
            <code>/projects</code>
            {" "}
            之后。当前默认路径仍然是先选项目，再直接进入当前项目页入口壳里的
            {" "}
            <strong>2D 开发者模式入口</strong>
            。
          </p>
          <p>
            现在这块真实分流层已经进一步长成项目级分流板：不仅能锁定 `projectId`，还能在同一路由里切换查看当前项目的模式视角；
            默认仍先打开 `2D 开发者模式入口` 视角，继续坚持当前 live 2D 优先。
          </p>

          <div className={styles.routePanel}>
            <p className={styles.routeEyebrow}>今天的 live 默认路径</p>
            <div className={styles.routeChain} aria-label="current live default route">
              {liveDefaultRoute.map((item, index) => (
                <span key={`${item.marker}-${item.label}`} className={styles.routeStep}>
                  {item.kind === "route" ? <code>{item.marker}</code> : <span className={styles.routeTag}>{item.marker}</span>}
                  <span className={styles.routeRole}>
                    {item.label}
                    <small>{item.role}</small>
                  </span>
                  {index < liveDefaultRoute.length - 1 ? <span className={styles.routeDivider}>→</span> : null}
                </span>
              ))}
            </div>
            <p className={styles.routeNote}>
              真实的 2D 开发者模式默认仍直接落在
              {" "}
              <code>{selectedProject ? selectedProjectLivePath : projectEntryShellPath}</code>
              {" "}
              这个当前项目页入口壳里，不需要先绕到本页。
            </p>
          </div>

          <div className={styles.routePanel}>
            <p className={styles.routeEyebrow}>真实的后置分流占位层</p>
            <div className={styles.routeChain} aria-label="real branch placeholder route">
              {branchPlaceholderRoute.map((item, index) => (
                <span key={`${item.marker}-${item.label}`} className={styles.routeStep}>
                  {item.kind === "route" ? <code>{item.marker}</code> : <span className={styles.routeTag}>{item.marker}</span>}
                  <span className={styles.routeRole}>
                    {item.label}
                    <small>{item.role}</small>
                  </span>
                  {index < branchPlaceholderRoute.length - 1 ? <span className={styles.routeDivider}>→</span> : null}
                </span>
              ))}
            </div>
            <p className={styles.routeNote}>
              这个占位页现在只负责把未来分支固定在真实路由里，并把分流板切到具体项目与具体模式视角，不提前伪装成已经开放的教育版或 3D 模式入口。
            </p>
          </div>
        </div>

        <div className={styles.userCard}>
          <strong>{selectedProject ? selectedProject.name : "分流层已落地"}</strong>
          <span>{selectedProject ? `当前正在查看该项目的 ${selectedMode.label} 视角` : "当前只把未来分流层钉成真实页面"}</span>
          <div className={styles.userActions}>
            <Link
              href={selectedProjectPrimaryHref}
              className={styles.primaryButton}
            >
              {selectedProjectPrimaryLabel}
            </Link>
            {showSelectedProjectModeEntryAction ? (
              <Link href={selectedProjectModeEntryPath} className={styles.secondaryButton}>
                打开当前项目同模式视角
              </Link>
            ) : null}
            {showSelectedProjectSecondaryAction ? (
              <Link href={selectedProjectLivePath} className={styles.secondaryButton}>
                打开 2D live 入口
              </Link>
            ) : null}
            <Link href="/projects" className={styles.secondaryButton}>
              回项目广场
            </Link>
          </div>
          <span>{user.name || "基地成员"}</span>
          <span>{user.email}</span>
        </div>
      </section>

      <section className={styles.summaryRow}>
        <article className={styles.summaryCard}>
          <span>今天默认打开的视角</span>
          <strong>2D 开发者</strong>
        </article>
        <article className={styles.summaryCard}>
          <span>当前分流板路径</span>
          <strong>{selectedProjectModeBoardPath}</strong>
        </article>
        <article className={styles.summaryCard}>
          <span>当前模式视角</span>
          <strong>{selectedMode.label}</strong>
        </article>
      </section>

      <section className={styles.panel}>
        <div className={styles.block}>
          <div className={styles.blockHead}>
            <h2>{selectedProject ? `${selectedProject.name} 的模式视角板` : "先选项目，再看这个项目的模式视角板"}</h2>
            <p>
              {selectedProject
                ? "你已经把真实分流层切到了当前项目上下文里。下面会展示当前选中的模式视角：今天默认仍先看 2D 开发者模式，未来模式则只保留占位。"
                : "先从下面选择一个项目切换到它的分流板，之后这页会变成项目级的模式视角板，而不再只是全局说明页。"}
            </p>
          </div>

          {selectedProject ? (
            <>
              <div className={styles.tabs}>
                {modeDefinitions.map((mode) => (
                  <Link
                    key={`${selectedProject.id}-${mode.id}`}
                    href={buildProjectModeChoicePath(selectedProject.id, mode.id)}
                    className={selectedMode.id === mode.id ? styles.activeTab : styles.tab}
                  >
                    {mode.label}
                  </Link>
                ))}
              </div>

              <article className={styles.projectCard}>
                <div>
                  <strong>{selectedMode.label}</strong>
                  <p>{selectedMode.detail}</p>
                  <p>
                    <strong>当前入口公式：</strong>
                    {" "}
                    {selectedMode.routeSummary}
                  </p>
                  <p>
                    <strong>入口规则：</strong>
                    {" "}
                    {selectedMode.branchRule}
                  </p>
                </div>
                <div className={styles.metaCol}>
                  <span>{selectedMode.state}</span>
                  <small>{selectedProject.name}</small>
                  <div className={styles.metaActions}>
                    {selectedMode.id === "2d-dev" ? (
                      <Link href={selectedProjectLivePath} className={styles.primaryButton}>
                        进入当前项目 2D 入口
                      </Link>
                    ) : selectedMode.id === "2d-upgrade" && selectedModeShellPath ? (
                      <Link href={selectedModeShellPath} className={styles.primaryButton}>
                        进入 2D 开发版升级版
                      </Link>
                    ) : selectedModeShellPath ? (
                      <Link href={selectedModeShellPath} className={styles.primaryButton}>
                        打开此模式下游占位壳
                      </Link>
                    ) : (
                      <Link href={selectedProjectLivePath} className={styles.primaryButton}>
                        回到当前项目 2D 入口
                      </Link>
                    )}
                    {selectedMode.id !== "2d-dev" && selectedMode.id !== "2d-upgrade" ? (
                      <Link href={selectedProjectModeEntryPath} className={styles.secondaryButton}>
                        打开当前项目同模式视角
                      </Link>
                    ) : null}
                    {selectedMode.id !== "2d-dev" ? (
                      <Link href={selectedProjectLivePath} className={styles.secondaryButton}>
                        打开 2D live 入口
                      </Link>
                    ) : null}
                    <Link href={buildProjectModeChoicePath(selectedProject.id, selectedMode.id)} className={styles.secondaryButton}>
                      保持此模式视角
                    </Link>
                  </div>
                </div>
              </article>
            </>
          ) : (
            <div className={styles.emptyState}>还没有锁定项目上下文。先从下面挑一个项目，把这块真实分流板切到该项目名下。</div>
          )}
        </div>

        <div className={styles.block}>
          <div className={styles.blockHead}>
            <h2>{selectedProject ? "切换到别的项目分流板" : "选择一个项目来查看它的分流板"}</h2>
            <p>
              每个项目至少都保留一条明确的
              {" "}
              <code>进入 2D live 入口</code>
              {" "}
              路径；当你正在查看未来模式时，同一张卡还会额外给出
              {" "}
              <code>打开该模式下游壳</code>
              、<code>打开当前项目同模式视图</code> 和 <code>切到这个项目的分流板</code>。
              这样既不改变今天的默认 live 路径，也把真实的 mode-aware 分流动作接进了项目选择。
            </p>
          </div>

          {projects.length ? (
            <div className={styles.itemList}>
              {projects.map((project) => {
                const isSelected = selectedProject?.id === project.id;
                const projectLivePath = buildProjectModeEntryPath(project.id, "2d-dev");
                const projectModeEntryPath = buildProjectModeEntryPath(project.id, selectedMode.id);
                const projectModeBoardPath = buildProjectModeChoicePath(project.id, selectedMode.id);
                const projectModeShellPath = buildModeShellPath(selectedMode.id, project.id);
                const projectModePrimaryHref =
                  selectedMode.id === "2d-dev"
                    ? projectLivePath
                    : projectModeShellPath ?? projectModeBoardPath;
                const projectModePrimaryLabel =
                  selectedMode.id === "2d-dev"
                    ? "进入 2D live 入口"
                    : projectModeShellPath
                      ? `打开 ${selectedMode.label} 占位壳`
                      : "打开这个项目分流板";
                return (
                  <article key={project.id} className={styles.projectCard}>
                    <div>
                      <strong>{project.name}</strong>
                      <p>{project.description || "当前项目说明还没补充，先通过 live 入口或分流板继续进入。"}</p>
                    </div>
                    <div className={styles.metaCol}>
                      <span>{isSelected ? "当前分流板" : project.role}</span>
                      <small>{project.type}</small>
                      <div className={styles.metaActions}>
                        <Link href={projectLivePath} className={styles.primaryButton}>
                          进入 2D live 入口
                        </Link>
                        {selectedMode.id !== "2d-dev" ? (
                          <Link href={projectModePrimaryHref} className={styles.secondaryButton}>
                            {projectModePrimaryLabel}
                          </Link>
                        ) : null}
                        {selectedMode.id !== "2d-dev" ? (
                          <Link href={projectModeEntryPath} className={styles.secondaryButton}>
                            打开当前项目同模式视角
                          </Link>
                        ) : null}
                        <Link href={projectModeBoardPath} className={styles.secondaryButton}>
                          {isSelected ? "保持当前分流板" : "切到此项目分流板"}
                        </Link>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className={styles.emptyState}>
              你还没有可继续进入的项目。请先回到项目管理入口页创建项目或接受邀请，再从那里进入当前 live 的 2D 开发者模式入口。
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
