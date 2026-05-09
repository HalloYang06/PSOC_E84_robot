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

type AcceptState =
  | { kind: "idle" }
  | { kind: "picking"; handoffId: string; taskId: string }
  | { kind: "submitting"; handoffId: string }
  | { kind: "ok"; handoffId: string; message: string }
  | { kind: "err"; handoffId: string; message: string };

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
  const [acceptState, setAcceptState] = useState<AcceptState>({ kind: "idle" });
  const [pickedSeatId, setPickedSeatId] = useState<string>("");
  const [acceptNote, setAcceptNote] = useState<string>("");

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

  function statusBadge(status: string | null): { label: string; cls: string } {
    const s = (status || "pending").toLowerCase();
    if (s === "accepted") return { label: "已接手", cls: styles.statusAccepted };
    if (s === "assigned") return { label: "已指派", cls: styles.statusAssigned };
    return { label: "待接手", cls: styles.statusPending };
  }

  function startAccept(item: HandoffItem) {
    const defaultPick = item.handoff_to || (seats[0]?.id ?? "");
    setPickedSeatId(defaultPick);
    setAcceptNote("");
    setAcceptState({ kind: "picking", handoffId: item.id, taskId: item.task_id });
  }

  function cancelAccept() {
    setAcceptState({ kind: "idle" });
    setPickedSeatId("");
    setAcceptNote("");
  }

  async function submitAccept(item: HandoffItem) {
    if (!pickedSeatId) {
      setAcceptState({ kind: "err", handoffId: item.id, message: "请先选一个 NPC 作为接手人" });
      return;
    }
    setAcceptState({ kind: "submitting", handoffId: item.id });
    try {
      const res = await fetch(
        apiClientUrl(`/api/tasks/${encodeURIComponent(item.task_id)}/handoffs/${encodeURIComponent(item.id)}/accept`),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            actor_type: "agent",
            actor_id: pickedSeatId,
            note: acceptNote.trim() || null,
          }),
        },
      );
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setAcceptState({ kind: "ok", handoffId: item.id, message: "已接手 ✓" });
      setPickedSeatId("");
      setAcceptNote("");
      await load();
      setTimeout(() => setAcceptState({ kind: "idle" }), 2400);
    } catch (e) {
      setAcceptState({
        kind: "err",
        handoffId: item.id,
        message: e instanceof Error ? e.message : "接手失败",
      });
    }
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
            const badge = statusBadge(item.current_status);
            const isAccepted = (item.current_status || "").toLowerCase() === "accepted";
            const picking = acceptState.kind === "picking" && acceptState.handoffId === item.id;
            const submitting = acceptState.kind === "submitting" && acceptState.handoffId === item.id;
            const okHere = acceptState.kind === "ok" && acceptState.handoffId === item.id;
            const errHere = acceptState.kind === "err" && acceptState.handoffId === item.id;
            return (
              <li key={item.id} className={`${styles.row} ${scope.isCross ? styles.rowCross : ""}`}>
                <div className={styles.rowHead}>
                  <span className={scope.isCross ? styles.tagCross : styles.tagSame}>
                    {scope.isCross ? "跨工位" : "同工位"}
                  </span>
                  <span className={badge.cls}>{badge.label}</span>
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
                {!isAccepted ? (
                  <div className={styles.acceptArea}>
                    {!picking ? (
                      <button
                        type="button"
                        className={styles.acceptBtn}
                        onClick={() => startAccept(item)}
                        title="选一个 NPC 作为接手人，状态会变成 accepted"
                      >
                        ✋ 我接手
                      </button>
                    ) : (
                      <div className={styles.acceptForm}>
                        <select
                          className={styles.acceptInput}
                          value={pickedSeatId}
                          onChange={(e) => setPickedSeatId(e.target.value)}
                          disabled={submitting}
                        >
                          <option value="">— 选 NPC —</option>
                          {seats.map((s) => {
                            const wsLabel = s.workstationName || s.computerNodeName || "未归属";
                            return (
                              <option key={s.id} value={s.id}>
                                {s.name}（{wsLabel}）
                              </option>
                            );
                          })}
                        </select>
                        <input
                          className={styles.acceptInput}
                          type="text"
                          placeholder="备注（可选）"
                          value={acceptNote}
                          onChange={(e) => setAcceptNote(e.target.value)}
                          disabled={submitting}
                        />
                        <button
                          type="button"
                          className={styles.acceptBtn}
                          onClick={() => submitAccept(item)}
                          disabled={submitting || !pickedSeatId}
                        >
                          {submitting ? "接手中…" : "确认接手"}
                        </button>
                        <button
                          type="button"
                          className={styles.cancelBtn}
                          onClick={cancelAccept}
                          disabled={submitting}
                        >
                          取消
                        </button>
                      </div>
                    )}
                    {okHere ? <small className={styles.acceptOk}>{(acceptState as { message: string }).message}</small> : null}
                    {errHere ? <small className={styles.acceptErr}>{(acceptState as { message: string }).message}</small> : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
