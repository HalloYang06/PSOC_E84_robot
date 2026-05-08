"use client";

import { useEffect, useState } from "react";
import styles from "./cross-workstation-handoffs.module.css";
import { apiClientUrl } from "../../../../lib/api-client-url";

type HandoffItem = {
  id: string;
  task_id: string;
  handoff_from: string | null;
  handoff_to: string | null;
  summary: string | null;
  reason: string | null;
  current_status: string | null;
  next_steps: string[];
  open_questions: string[];
  created_at: string | null;
};

type SeatLite = {
  id: string;
  name: string;
  workstationId: string;
  workstationName: string;
  computerNodeId: string;
  computerNodeName: string;
};

type Props = {
  apiBaseUrl: string;
  projectId: string;
  seats: SeatLite[];
};

function fmtTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function CrossWorkstationHandoffs({ apiBaseUrl, projectId, seats }: Props) {
  const [items, setItems] = useState<HandoffItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        apiClientUrl(`/api/handoffs?project_id=${encodeURIComponent(projectId)}&limit=100`),
        { credentials: "include" },
      );
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setItems((json?.data ?? []) as HandoffItem[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [apiBaseUrl, projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  function seatOf(agentId: string | null): SeatLite | null {
    if (!agentId) return null;
    return seats.find((s) => s.id === agentId) || null;
  }

  function classifyScope(item: HandoffItem): { isCross: boolean; label: string } {
    const from = seatOf(item.handoff_from);
    const to = seatOf(item.handoff_to);
    if (!from || !to) return { isCross: false, label: "未识别" };
    const fromKey = from.workstationId || from.computerNodeId;
    const toKey = to.workstationId || to.computerNodeId;
    if (!fromKey || !toKey) return { isCross: false, label: "工位未归属" };
    const cross = fromKey !== toKey;
    const fromLabel = from.workstationName || from.computerNodeName;
    const toLabel = to.workstationName || to.computerNodeName;
    return {
      isCross: cross,
      label: cross ? `${fromLabel} → ${toLabel}` : `本工位（${fromLabel}）`,
    };
  }

  return (
    <section className={styles.shell}>
      <header className={styles.head}>
        <strong>🔀 跨工位交接（Handoff）</strong>
        <div className={styles.headRight}>
          <small>
            {items === null ? "加载中…" : `共 ${items.length} 条`}
            {loading ? " · 刷新中…" : ""}
          </small>
          <button type="button" className={styles.refreshBtn} onClick={load} disabled={loading}>
            ⟳ 刷新
          </button>
        </div>
      </header>
      {error ? <p className={styles.errorBox}>⚠ {error}</p> : null}
      {items && items.length === 0 ? (
        <p className={styles.emptyHint}>
          还没有任何 Handoff 记录。Handoff 通常在 NPC 完成阶段、Token 满、需要换手时由其上游或人工创建。
        </p>
      ) : null}
      {items && items.length > 0 ? (
        <ul className={styles.list}>
          {items.map((item) => {
            const scope = classifyScope(item);
            const from = seatOf(item.handoff_from);
            const to = seatOf(item.handoff_to);
            return (
              <li key={item.id} className={`${styles.row} ${scope.isCross ? styles.rowCross : ""}`}>
                <div className={styles.rowHead}>
                  <span className={scope.isCross ? styles.tagCross : styles.tagSame}>
                    {scope.isCross ? "跨工位" : "同工位"}
                  </span>
                  <strong className={styles.rowTitle}>
                    {from?.name || item.handoff_from || "?"} → {to?.name || item.handoff_to || "?"}
                  </strong>
                  <small className={styles.rowMeta}>{scope.label}</small>
                  <small className={styles.rowTime}>{fmtTime(item.created_at)}</small>
                </div>
                {item.summary ? <p className={styles.rowSummary}>{item.summary}</p> : null}
                {item.next_steps && item.next_steps.length > 0 ? (
                  <details className={styles.rowDetails}>
                    <summary>展开 next_steps（{item.next_steps.length}）</summary>
                    <ul>
                      {item.next_steps.map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
                {item.open_questions && item.open_questions.length > 0 ? (
                  <details className={styles.rowDetails}>
                    <summary>open_questions ({item.open_questions.length})</summary>
                    <ul>
                      {item.open_questions.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
