"use client";

import { useEffect, useState } from "react";
import styles from "./requirement-dispatcher.module.css";
import { apiClientUrl } from "../../../../lib/api-client-url";

type SeatLite = {
  id: string;
  name: string;
  computerNodeId: string;
  computerNodeName: string;
};

type Props = {
  apiBaseUrl: string;
  projectId: string;
  seats: SeatLite[];
};

type ReqLite = {
  id: string;
  title: string;
  status: string;
};

export function RequirementDispatcher({ apiBaseUrl, projectId, seats }: Props) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [targetSeatId, setTargetSeatId] = useState("");
  const [trigger, setTrigger] = useState<"manual" | "after_requirement">("manual");
  const [dependencyId, setDependencyId] = useState("");
  const [reqs, setReqs] = useState<ReqLite[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!open || trigger !== "after_requirement") return;
    (async () => {
      try {
        const res = await fetch(
          apiClientUrl(`/api/requirements?project_id=${encodeURIComponent(projectId)}`),
          { credentials: "include" },
        );
        const json = await res.json().catch(() => ({}));
        const list = (json?.data ?? []) as ReqLite[];
        setReqs(list.slice(0, 80));
      } catch {
        /* ignore */
      }
    })();
  }, [open, trigger, apiBaseUrl, projectId]);

  async function submit() {
    if (!title.trim() || !targetSeatId || !body.trim()) {
      setNote("标题 / 目标 NPC / 内容必填");
      return;
    }
    setBusy(true);
    setNote(null);
    try {
      const createRes = await fetch(apiClientUrl(`/api/requirements`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          project_id: projectId,
          title: title.trim(),
          requirement_type: "thread_request",
          priority: "high",
          context_summary: body.trim(),
          expected_output: body.trim(),
          to_agent: targetSeatId,
          target_seat_id: targetSeatId,
          trigger_kind: trigger === "after_requirement" ? "on_requirement_done" : "manual",
          ...(trigger === "after_requirement" && dependencyId
            ? { dependency_requirement_id: dependencyId }
            : {}),
        }),
      });
      const createJson = await createRes.json().catch(() => ({}));
      if (!createRes.ok) {
        const msg = createJson?.error?.message ?? createJson?.message ?? `HTTP ${createRes.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      const reqId = createJson?.data?.id;
      if (!reqId) throw new Error("Requirement 创建成功但未返回 id");

      if (trigger === "manual") {
        const dispRes = await fetch(apiClientUrl(`/api/requirements/${encodeURIComponent(reqId)}/dispatch`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            actor_type: "human",
            target_type: "agent",
            target_id: targetSeatId,
            status: "queued",
            title: title.trim(),
            body: body.trim(),
          }),
        });
        const dispJson = await dispRes.json().catch(() => ({}));
        if (!dispRes.ok) {
          const msg = dispJson?.error?.message ?? dispJson?.message ?? `HTTP ${dispRes.status}`;
          throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        }
        setNote(`✓ 需求已创建并派发给 ${seats.find((s) => s.id === targetSeatId)?.name || targetSeatId}`);
      } else {
        setNote(`✓ 触发式需求已创建：前置需求完成后会以上游 NPC 身份自动派给 ${seats.find((s) => s.id === targetSeatId)?.name || targetSeatId}（跨工位将走人工审批）`);
      }
      setTitle("");
      setBody("");
      setDependencyId("");
    } catch (e) {
      setNote(`失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setBusy(false);
      setTimeout(() => setNote(null), 6000);
    }
  }

  if (!open) {
    return (
      <button type="button" className={styles.toggle} onClick={() => setOpen(true)}>
        ＋ 触发式派单（指定 NPC + 触发条件）
      </button>
    );
  }

  return (
    <div className={styles.shell}>
      <header className={styles.head}>
        <strong>📌 触发式派单</strong>
        <button type="button" className={styles.closeBtn} onClick={() => setOpen(false)}>
          收起
        </button>
      </header>
      <div className={styles.row}>
        <label className={styles.label}>标题</label>
        <input
          className={styles.input}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="例如：把 lint 改红的 5 处都修了"
          maxLength={120}
        />
      </div>
      <div className={styles.row}>
        <label className={styles.label}>目标 NPC（必填）</label>
        <select
          className={styles.input}
          value={targetSeatId}
          onChange={(e) => setTargetSeatId(e.target.value)}
        >
          <option value="">— 选一个 NPC —</option>
          {seats.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}（{s.computerNodeName || "未绑定电脑"}）
            </option>
          ))}
        </select>
      </div>
      <div className={styles.row}>
        <label className={styles.label}>触发条件</label>
        <select
          className={styles.input}
          value={trigger}
          onChange={(e) => setTrigger(e.target.value as "manual" | "after_requirement")}
        >
          <option value="manual">手动派发（立即派给目标 NPC）</option>
          <option value="after_requirement">前置需求完成 → 以上游 NPC 身份自动派（跨工位走人审）</option>
        </select>
      </div>
      {trigger === "after_requirement" ? (
        <div className={styles.row}>
          <label className={styles.label}>前置需求</label>
          <select
            className={styles.input}
            value={dependencyId}
            onChange={(e) => setDependencyId(e.target.value)}
          >
            <option value="">— 选一个前置需求 —</option>
            {reqs.map((r) => (
              <option key={r.id} value={r.id}>
                [{r.status}] {r.title}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className={styles.row}>
        <label className={styles.label}>内容（context_summary / expected_output）</label>
        <textarea
          className={styles.textarea}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="把要做的事 / 验收标准说清楚……"
          rows={4}
        />
      </div>
      <div className={styles.actions}>
        <button type="button" className={styles.submitBtn} onClick={submit} disabled={busy}>
          {busy ? "提交中…" : trigger === "manual" ? "立即派发" : "创建（等待前置完成）"}
        </button>
        {note ? <small className={styles.note}>{note}</small> : null}
      </div>
    </div>
  );
}
