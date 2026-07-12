import Link from "next/link";

import {
  modeChoice2dDevPath,
  modeChoicePath,
  projectEntryLiveRoute,
} from "./projects/mode-entry-paths";
import styles from "./game.module.css";

export default function NotFound() {
  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <section className={styles.card}>
          <div className={styles.kicker}>页面未找到</div>
          <h1 className={styles.title}>回到当前真实入口链。</h1>
          <p className={styles.subtitle}>
            当前仍然只有一条 live 路线，迷路时也应该回到同一条前门链，而不是跳去别的壳页或临时分流页。
          </p>
          <div className={styles.routePanel}>
            <p className={styles.routeEyebrow}>当前真实入口链</p>
            <div className={styles.routeChain} aria-label="current live recovery route">
              {projectEntryLiveRoute.map((item, index) => (
                <span key={`${item.marker}-${item.label}`} className={styles.routeStep}>
                  {item.kind === "route" ? <code>{item.marker}</code> : <span className={styles.routeTag}>{item.marker}</span>}
                  <span className={styles.routeRole}>
                    {item.label}
                    <small>{item.role}</small>
                  </span>
                  {index < projectEntryLiveRoute.length - 1 ? <span className={styles.routeDivider}>→</span> : null}
                </span>
              ))}
            </div>
            <p className={styles.routeNote}>
              这四步分别只承担自己的职责：登录认证、项目管理、当前项目入口壳，以及挂在入口壳里的 live 2D 模式层。
            </p>
          </div>
          <p className={styles.subtitle}>
            登录页只负责认证，项目管理入口页只负责选项目。现在已经有独立的 mode choice 占位页
            {" "}
            <code>{modeChoicePath}</code>
            {" "}
            固定在
            {" "}
            <code>/projects</code>
            {" "}
            之后；如果要显式回到当前默认分流视角，则是
            {" "}
            <code>{modeChoice2dDevPath}</code>
            。
            但今天的 live 2D 路径默认仍直接进入当前项目页入口壳。
          </p>
          <div className={styles.buttonRow} style={{ marginTop: 16 }}>
            <Link className={styles.button} href="/projects">
              回项目管理页
            </Link>
            <Link className={styles.button} href={modeChoice2dDevPath}>
              看当前 2D 分流视角
            </Link>
            <Link className={styles.button} href="/login">
              去登录页
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
