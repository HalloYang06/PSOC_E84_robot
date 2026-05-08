"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import styles from "./workbench.module.css";
import { NpcTile, type WorkbenchSeat } from "./_components/npc-tile";
import { RequirementDispatcher } from "../_components/requirement-dispatcher";

type WorkbenchClientProps = {
  projectId: string;
  projectName: string;
  apiBaseUrl: string;
  seats: WorkbenchSeat[];
  currentUserId: string;
  currentUserName: string;
  pageMode?: "workbench" | "company";
  embedded?: boolean;
};

export function WorkbenchClient({ projectId, projectName, apiBaseUrl, seats, currentUserId, currentUserName, pageMode = "workbench", embedded = false }: WorkbenchClientProps) {
  const isCompany = pageMode === "company";
  const [openIds, setOpenIds] = useState<string[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");

  const grouped = useMemo(() => {
    const groups = new Map<string, { name: string; isLogical: boolean; seats: WorkbenchSeat[] }>();
    for (const seat of seats) {
      let key = "__unbound__";
      let name = "未归属工位";
      let isLogical = false;
      if (seat.workstationId) {
        key = `ws:${seat.workstationId}`;
        name = seat.workstationName || seat.workstationId;
        isLogical = true;
      } else if (seat.computerNodeId) {
        key = `node:${seat.computerNodeId}`;
        name = seat.computerNodeName || seat.computerNodeId;
      }
      const bucket = groups.get(key) ?? { name, isLogical, seats: [] };
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
            (s.workstationName || s.computerNodeName).toLowerCase().includes(q) ||
            s.responsibility.toLowerCase().includes(q),
        ),
      }))
      .filter((g) => g.seats.length > 0);
  }, [grouped, filter]);

  const openSeats = useMemo(
    () => openIds.map((id) => seats.find((s) => s.id === id)).filter(Boolean) as WorkbenchSeat[],
    [openIds, seats],
  );

  function seatGroupKey(s: WorkbenchSeat): string {
    return s.workstationId || s.computerNodeId || "";
  }

  const teammatesBySeat = useMemo(() => {
    const map = new Map<string, WorkbenchSeat[]>();
    for (const seat of seats) {
      const myKey = seatGroupKey(seat);
      const peers = seats.filter(
        (other) => other.id !== seat.id && (myKey ? seatGroupKey(other) === myKey : !seatGroupKey(other)),
      );
      map.set(seat.id, peers);
    }
    return map;
  }, [seats]);

  const crossLeadsBySeat = useMemo(() => {
    const map = new Map<string, WorkbenchSeat[]>();
    const seenLeadIds = new Set<string>();
    const allLeads = seats.filter((s) => {
      if (!s.isLead || !seatGroupKey(s)) return false;
      if (seenLeadIds.has(s.id)) return false;
      seenLeadIds.add(s.id);
      return true;
    });
    for (const seat of seats) {
      const myKey = seatGroupKey(seat);
      const others = allLeads.filter(
        (lead) => seatGroupKey(lead) !== myKey && lead.id !== seat.id,
      );
      map.set(seat.id, others);
    }
    return map;
  }, [seats]);

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
    <main className={styles.shell} data-embed={embedded ? "drawer" : undefined}>
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          <Link href={`/projects/${projectId}/cockpit`} className={styles.backLink} title="返回项目驾驶舱">
            ← 驾驶舱
          </Link>
          <div className={styles.title}>
            <strong>{projectName}</strong>
            <small>
              {isCompany
                ? "🏢 公司层 · 工位长会议室（每个工位的 lead 瓷砖；跨工位转交、群组决策都从这里发起）"
                : "NPC 工作台 · 同时打开多个 NPC 的对话/状态卡"}
            </small>
          </div>
        </div>
        <div className={styles.topbarRight}>
          <span className={styles.kpi}>
            {isCompany ? `共 ${seats.length} 位工位长` : `共 ${seats.length} 个 NPC`}
          </span>
          <span className={styles.kpi}>已打开 {openIds.length}</span>
          <span className={styles.kpi}>已勾选 {selectedIds.size}</span>
          {isCompany ? (
            <Link href={`/projects/${projectId}/workbench`} className={styles.backLink} title="返回 NPC 工作台（看所有 NPC）">
              工作台 →
            </Link>
          ) : (
            <Link href={`/projects/${projectId}/company`} className={styles.backLink} title="进入公司层：只看每个工位的工位长">
              🏢 公司层 →
            </Link>
          )}
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
                    <span>{group.isLogical ? "🏷 " : "🖥 "}{group.name}</span>
                    <small>{group.seats.length} 个 NPC{group.isLogical ? " · 逻辑工位" : ""}</small>
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
          <div style={{ marginBottom: 12 }}>
            <RequirementDispatcher
              apiBaseUrl={apiBaseUrl}
              projectId={projectId}
              seats={seats.map((s) => ({
                id: s.id,
                name: s.name,
                computerNodeId: s.computerNodeId || "",
                computerNodeName: s.computerNodeName || (s.computerNodeId ? s.computerNodeId : "未绑定电脑"),
              }))}
            />
          </div>
          {openSeats.length === 0 ? (
            <div className={styles.placeholder}>
              <strong>
                {isCompany
                  ? seats.length === 0
                    ? "还没有任何工位长"
                    : "点击左栏工位长行的 + 号，打开 ta 的会议室瓷砖"
                  : "点击左栏 NPC 行的 + 号，打开它的工作卡"}
              </strong>
              <p>
                {isCompany
                  ? "公司层只显示每个工位指定的工位长（👑）。在工位卡的「工位长」下拉里选定后会出现在这里。跨工位的消息默认会被路由到对应工位长。"
                  : "多开会自动平分屏幕；单开则全屏。后续 S4 会把 Claude/Codex 的关键信息流实时挂进卡片。"}
              </p>
            </div>
          ) : (
            <div className={styles.tileGrid} data-tile-count={openSeats.length}>
              {openSeats.map((seat) => (
                <NpcTile
                  key={seat.id}
                  projectId={projectId}
                  apiBaseUrl={apiBaseUrl}
                  seat={seat}
                  teammates={teammatesBySeat.get(seat.id) ?? []}
                  crossLeads={crossLeadsBySeat.get(seat.id) ?? []}
                  currentUserId={currentUserId}
                  currentUserName={currentUserName}
                  onOpenTeammate={toggleOpen}
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
