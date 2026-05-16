"use client";

import Link from "next/link";
import { useState } from "react";
import styles from "./game-shell.module.css";

type PanelKey = "map" | "cockpit" | "workbench" | "observability" | "company";

type GameShellProps = {
  projectId: string;
  projectName: string;
  gradeChip?: { grade: string; summary: string; color: string } | null;
  actionHint?: string;
  actionPanel?: PanelKey;
};

const PANELS: { key: PanelKey; label: string; title: string; path: (id: string) => string }[] = [
  { key: "map", label: "🗺️ 地图", title: "项目工作台地图 · 所有一级入口", path: (id) => `/projects/${id}/map` },
  { key: "cockpit", label: "🛠️ 驾驶舱", title: "项目驾驶舱（合格性 / KPI / 广播）", path: (id) => `/projects/${id}/cockpit` },
  { key: "workbench", label: "🧑‍💼 工作台", title: "NPC 工作台 · 瓷砖主操作面", path: (id) => `/projects/${id}/workbench` },
  { key: "observability", label: "📡 观测台", title: "派单、回执、待审、执行电脑和风险观测", path: (id) => `/projects/${id}/observability` },
  { key: "company", label: "🏢 公司层", title: "工位长会议室", path: (id) => `/projects/${id}/company` },
];

export function GameShell({ projectId, projectName, gradeChip = null, actionHint = "", actionPanel = "workbench" }: GameShellProps) {
  const [openPanel, setOpenPanel] = useState<PanelKey | null>(null);
  const [gameHidden, setGameHidden] = useState(false);

  const gameSrc = `/harvest-moon-phaser3-game/index.html?embed=project-shell&project=${encodeURIComponent(projectId)}`;

  return (
    <div className={styles.shell}>
      <header className={styles.topNav} data-active-panel={openPanel ?? ""}>
        <div className={styles.navLeft}>
          <Link href="/projects" className={styles.navLink} title="返回项目列表">← 项目</Link>
          <strong className={styles.projectName} title={projectId}>{projectName}</strong>
          {gradeChip ? (
            <span
              className={styles.gradeChip}
              style={{ backgroundColor: gradeChip.color }}
              title={gradeChip.summary}
            >
              合格性 {gradeChip.grade}
            </span>
          ) : null}
          {actionHint ? (
            <button
              type="button"
              className={styles.actionHint}
              title={`打开${PANELS.find((p) => p.key === actionPanel)?.title ?? "下一步面板"}`}
              onClick={() => setOpenPanel(actionPanel)}
            >
              {actionHint}
            </button>
          ) : null}
        </div>
        <nav className={styles.navRight}>
          {PANELS.map((p) => (
            <button
              key={p.key}
              type="button"
              className={styles.navBtn}
              data-active={openPanel === p.key ? "1" : "0"}
              title={p.title}
              onClick={() => setOpenPanel((curr) => (curr === p.key ? null : p.key))}
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            className={styles.navBtn}
            title={gameHidden ? "显示游戏画面" : "隐藏游戏画面"}
            onClick={() => setGameHidden((v) => !v)}
          >
            {gameHidden ? "🎮 显示游戏" : "🙈 隐藏游戏"}
          </button>
        </nav>
      </header>

      <main className={styles.body}>
        <div className={styles.gameFrameWrap} data-hidden={gameHidden ? "1" : "0"}>
          {!gameHidden ? (
            <iframe
              src={gameSrc}
              className={styles.gameFrame}
              title="Harvest Moon Phaser 3 Game"
              allow="autoplay; fullscreen"
            />
          ) : (
            <div className={styles.gameHiddenPlaceholder}>
              <strong>游戏已隐藏</strong>
              <p>点击右上角「🎮 显示游戏」重新显示。隐藏时工作面板占满视口。</p>
            </div>
          )}
        </div>

        {openPanel ? (
          <>
            <div className={styles.drawerBackdrop} onClick={() => setOpenPanel(null)} />
            <aside className={styles.drawer} data-panel={openPanel}>
              <div className={styles.drawerHead}>
                <strong>
                  {PANELS.find((p) => p.key === openPanel)?.title}
                </strong>
                <div className={styles.drawerHeadActions}>
                  <a
                    href={PANELS.find((p) => p.key === openPanel)!.path(projectId)}
                    target="_blank"
                    rel="noreferrer"
                    className={styles.drawerLink}
                    title="在独立页面打开（新标签页）"
                  >
                    ↗ 独立页
                  </a>
                  <button
                    type="button"
                    className={styles.drawerClose}
                    title="关闭抽屉（Esc）"
                    onClick={() => setOpenPanel(null)}
                  >
                    ✕
                  </button>
                </div>
              </div>
              <iframe
                key={openPanel}
                src={`${PANELS.find((p) => p.key === openPanel)!.path(projectId)}?embed=drawer`}
                className={styles.drawerFrame}
                title={PANELS.find((p) => p.key === openPanel)?.title}
              />
            </aside>
          </>
        ) : null}
      </main>
    </div>
  );
}
