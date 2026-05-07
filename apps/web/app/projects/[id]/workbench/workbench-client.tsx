"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import styles from "./workbench.module.css";
import { NpcTile, type WorkbenchSeat } from "./_components/npc-tile";

type WorkbenchClientProps = {
  projectId: string;
  projectName: string;
  seats: WorkbenchSeat[];
};

export function WorkbenchClient({ projectId, projectName, seats }: WorkbenchClientProps) {
  const [openIds, setOpenIds] = useState<string[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");

  const grouped = useMemo(() => {
    const groups = new Map<string, { name: string; seats: WorkbenchSeat[] }>();
    for (const seat of seats) {
      const key = seat.computerNodeId || "__unbound__";
      const name = seat.computerNodeName || (seat.computerNodeId ? seat.computerNodeId : "未绑定电脑");
      const bucket = groups.get(key) ?? { name, seats: [] };
      bucket.seats.push(seat);
      groups.set(key, bucket);
    }
    return Array.from(groups.entries()).map(([key, value]) => ({ key, ...value }));
  }, [seats]);

  const filteredGroups = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return grouped;
    return grouped
      .map((group) => ({
        ...group,
        seats: group.seats.filter(
          (s) =>
            s.name.toLowerCase().includes(q) ||
            s.computerNodeName.toLowerCase().includes(q) ||
            s.responsibility.toLowerCase().includes(q),
        ),
      }))
      .filter((g) => g.seats.length > 0);
  }, [grouped, filter]);

  const openSeats = useMemo(
    () => openIds.map((id) => seats.find((s) => s.id === id)).filter(Boolean) as WorkbenchSeat[],
    [openIds, seats],
  );

  function toggleOpen(id: string) {
    setOpenIds((curr) => (curr.includes(id) ? curr : [...curr, id]));
  }

  function closeOpen(id: string) {
    setOpenIds((curr) => curr.filter((x) => x !== id));
  }

  function toggleSelected(id: string) {
    setSelectedIds((curr) => {
      const next = new Set(curr);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function openAllSelected() {
    if (selectedIds.size === 0) return;
    setOpenIds((curr) => {
      const next = [...curr];
      for (const id of selectedIds) if (!next.includes(id)) next.push(id);
      return next;
    });
  }

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          <Link href={`/projects/${projectId}`} className={styles.backLink} title="返回项目驾驶舱">
            ← 驾驶舱
          </Link>
          <div className={styles.title}>
            <strong>{projectName}</strong>
            <small>NPC 工作台 · 同时打开多个 NPC 的对话/状态卡</small>
          </div>
        </div>
        <div className={styles.topbarRight}>
          <span className={styles.kpi}>共 {seats.length} 个 NPC</span>
          <span className={styles.kpi}>已打开 {openIds.length}</span>
          <span className={styles.kpi}>已勾选 {selectedIds.size}</span>
        </div>
      </header>

      <div className={styles.body}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarHeader}>
            <input
              type="search"
              className={styles.search}
              placeholder="搜索 NPC 名 / 电脑 / 职责"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <button
              type="button"
              className={styles.batchBtn}
              onClick={openAllSelected}
              disabled={selectedIds.size === 0}
              title="把勾选的 NPC 全部加到右侧瓷砖"
            >
              开启已勾选 ({selectedIds.size})
            </button>
          </div>

          {filteredGroups.length === 0 ? (
            <p className={styles.empty}>没有匹配的 NPC。</p>
          ) : (
            <ul className={styles.groupList}>
              {filteredGroups.map((group) => (
                <li key={group.key} className={styles.group}>
                  <div className={styles.groupHeader}>
                    <span>{group.name}</span>
                    <small>{group.seats.length} 个 NPC</small>
                  </div>
                  <ul className={styles.npcList}>
                    {group.seats.map((seat) => {
                      const isOpen = openIds.includes(seat.id);
                      const isSelected = selectedIds.has(seat.id);
                      return (
                        <li key={seat.id} className={`${styles.npcRow} ${isOpen ? styles.npcRowOpen : ""}`}>
                          <label className={styles.checkbox} title="勾选后批量开启">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleSelected(seat.id)}
                            />
                          </label>
                          <div className={styles.npcMain}>
                            <strong className={styles.npcName}>{seat.name}</strong>
                            <small className={styles.npcMeta}>
                              <span className={styles.dot} title="占用状态：S5 后接入" />
                              {seat.providerLabel || "未绑定 provider"}
                              {seat.automationEnabled ? " · 自动化已开" : ""}
                            </small>
                          </div>
                          <button
                            type="button"
                            className={styles.openBtn}
                            onClick={() => (isOpen ? closeOpen(seat.id) : toggleOpen(seat.id))}
                            title={isOpen ? "关闭瓷砖" : "打开瓷砖"}
                          >
                            {isOpen ? "✕" : "+"}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className={styles.main}>
          {openSeats.length === 0 ? (
            <div className={styles.placeholder}>
              <strong>点击左栏 NPC 行的 + 号，打开它的工作卡</strong>
              <p>多开会自动平分屏幕；单开则全屏。后续 S4 会把 Claude/Codex 的关键信息流实时挂进卡片。</p>
            </div>
          ) : (
            <div className={styles.tileGrid} data-tile-count={openSeats.length}>
              {openSeats.map((seat) => (
                <NpcTile
                  key={seat.id}
                  projectId={projectId}
                  seat={seat}
                  onClose={() => closeOpen(seat.id)}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
