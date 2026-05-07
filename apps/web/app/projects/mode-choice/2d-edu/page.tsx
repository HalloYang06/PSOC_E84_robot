import Link from "next/link";

import {
  buildProjectFutureModeShellNavigation,
} from "../../mode-entry-paths";
import { requireModeEntryProjectContext } from "../../mode-entry-server";
import styles from "../../page.module.css";

type TwoDEducationShellPageProps = {
  searchParams?: {
    projectId?: string;
    mode?: string;
  };
};

export default async function TwoDEducationShellPage({ searchParams }: TwoDEducationShellPageProps) {
  const selectedProjectId = String(searchParams?.projectId ?? "").trim();
  const { returnTo, modeBoardPath, currentProjectModePath, liveProjectPath, shellPath } =
    buildProjectFutureModeShellNavigation("2d-edu", selectedProjectId || undefined);
  const { selectedProject } = await requireModeEntryProjectContext(returnTo, selectedProjectId);

  return (
    <main className={styles.page}>
      <section className={styles.header}>
        <div className={styles.headerCopy}>
          <span className={styles.kicker}>2D 教育版占位壳</span>
          <h1>把 2D 教育版的分流后下一页先钉出来。</h1>
          <p>
            这里是 <code>2D 教育版入口</code> 在 <code>{modeBoardPath}</code> 之后的第一张真实占位壳页面。
            它还不是可用的教学模式，只是把“分流后会去哪里”从说明文字推进到了真实路由。
          </p>
          <p>
            当前 live 路径仍然是 `2D 开发者模式入口`，也就是当前项目页入口壳里的农场地图、背包抽屉和 NPC 协作开发面。
            这个占位壳只负责把未来 2D 教学模式的下游位置钉住，不替换现有农场底座。
          </p>

          <div className={styles.routePanel}>
            <p className={styles.routeEyebrow}>当前占位下游路径</p>
            <div className={styles.routeChain} aria-label="2d education placeholder shell route">
              <span className={styles.routeStep}>
                <code>/login</code>
                <span className={styles.routeRole}>
                  登录页
                  <small>只负责认证</small>
                </span>
              </span>
              <span className={styles.routeDivider}>→</span>
              <span className={styles.routeStep}>
                <code>/projects</code>
                <span className={styles.routeRole}>
                  项目管理入口页
                  <small>只负责选项目</small>
                </span>
              </span>
              <span className={styles.routeDivider}>→</span>
              <span className={styles.routeStep}>
                <code>{modeBoardPath}</code>
                <span className={styles.routeRole}>
                  模式分流板
                  <small>切到 2D 教育版视角</small>
                </span>
              </span>
              <span className={styles.routeDivider}>→</span>
              <span className={styles.routeStep}>
                <code>{shellPath}</code>
                <span className={styles.routeRole}>
                  2D 教育版占位壳
                  <small>第一张真实下游占位页</small>
                </span>
              </span>
            </div>
            <p className={styles.routeNote}>
              下一步真正有价值的工作不再是补摘要，而是把教学任务链、教学 NPC 和教学结果面逐步接进这个占位壳。
            </p>
          </div>
        </div>

        <div className={styles.userCard}>
          <strong>{selectedProject ? selectedProject.name : "2D 教学分支占位"}</strong>
          <span>{selectedProject ? "当前正在查看这个项目的 2D 教育版下游占位壳" : "当前只固定 2D 教学模式的下游占位页"}</span>
          <div className={styles.userActions}>
            <Link href={liveProjectPath} className={styles.primaryButton}>
              {selectedProject ? "回当前项目 2D live 入口" : "回项目管理入口页"}
            </Link>
            {selectedProject ? (
              <Link href={currentProjectModePath} className={styles.secondaryButton}>
                回当前项目同模式视角
              </Link>
            ) : null}
            <Link href={modeBoardPath} className={styles.secondaryButton}>
              回 2D 教育版分流板
            </Link>
          </div>
        </div>
      </section>

      <section className={styles.summaryRow}>
        <article className={styles.summaryCard}>
          <span>当前状态</span>
          <strong>仅占位</strong>
        </article>
        <article className={styles.summaryCard}>
          <span>上游分流层</span>
          <strong>{modeBoardPath}</strong>
        </article>
        <article className={styles.summaryCard}>
          <span>当前真实 live</span>
          <strong>2D 开发者</strong>
        </article>
      </section>

      <section className={styles.panel}>
        <div className={styles.block}>
          <div className={styles.blockHead}>
            <h2>这个占位壳现在承担什么</h2>
            <p>它只做两件事：一是把 2D 教育版的下游入口位置钉成真实路由；二是明确告诉后续实现应该把什么接到这里。</p>
          </div>

          <div className={styles.itemList}>
            <article className={styles.projectCard}>
              <div>
                <strong>已经就位的部分</strong>
                <p>认证、项目选择、模式分流板和 2D 教育版下游占位壳已经连成了一条真实路由链。</p>
              </div>
              <div className={styles.metaCol}>
                <span>真实路由</span>
                <small>已落地</small>
              </div>
            </article>
            <article className={styles.projectCard}>
              <div>
                <strong>还没就位的部分</strong>
                <p>教学 NPC、教学任务链、教学用结果验收面还没接进来，所以这个页面仍然不是可用的教育模式。</p>
              </div>
              <div className={styles.metaCol}>
                <span>教学内容</span>
                <small>未开放</small>
              </div>
            </article>
          </div>
        </div>
      </section>
    </main>
  );
}
