"use client";

import { useEffect, useState } from "react";
import styles from "./broadcast-modal.module.css";
import { apiClientUrl } from "../../../../lib/api-client-url";

type BroadcastTarget = {
  id: string;
  name: string;
  computer_node_id: string;
  provider_label: string;
  responsibility: string;
};

type ReviewDecision = {
  requires_review: boolean;
  source: string;
  seat_id: string;
  policy: string;
};

type BroadcastPreview = {
  scope: string;
  scope_label: string;
  target_count: number;
  targets: BroadcastTarget[];
  estimated_tokens: number;
  requires_human_review: boolean;
  review_decisions?: ReviewDecision[];
  review_force_count?: number;
  blockers: string[];
  warnings: string[];
  ready: boolean;
};

type BroadcastCommitResult = {
  broadcast_id: string;
  scope_label: string;
  target_count: number;
  created_message_ids: string[];
};

export type BroadcastModalProps = {
  apiBaseUrl: string;
  projectId: string;
  scope: string;
  scopeLabel: string;
  onClose: () => void;
};

export function BroadcastModal({ apiBaseUrl, projectId, scope, scopeLabel, onClose }: BroadcastModalProps) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState<BroadcastPreview | null>(null);
  const [committed, setCommitted] = useState<BroadcastCommitResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"idle" | "previewing" | "committing">("idle");

  useEffect(() => {
    setPreview(null);
  }, [body, scope]);

  async function callApi<T>(path: string): Promise<T> {
    const res = await fetch(apiClientUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ scope, title: title.trim() || undefined, body: body.trim(), message_type: "comment_message" }),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return (json?.data ?? json) as T;
  }

  async function runPreview() {
    setBusy("previewing");
    setError(null);
    try {
      const data = await callApi<BroadcastPreview>(`/api/collaboration/projects/${projectId}/broadcast/preview`);
      setPreview(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "预演失败");
    } finally {
      setBusy("idle");
    }
  }

  async function runCommit() {
    if (!preview?.ready) return;
    if (!confirm(`确认要把这条广播发给 ${preview.target_count} 个 NPC 吗？发出后无法撤回。`)) return;
    setBusy("committing");
    setError(null);
    try {
      const data = await callApi<BroadcastCommitResult>(`/api/collaboration/projects/${projectId}/broadcast/commit`);
      setCommitted(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "派发失败");
    } finally {
      setBusy("idle");
    }
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <header className={styles.head}>
          <strong>📣 {scopeLabel} 广播</strong>
          <button type="button" className={styles.closeBtn} onClick={onClose}>✕</button>
        </header>

        {committed ? (
          <div className={styles.successBox}>
            <strong>已派发到 {committed.target_count} 个 NPC ✓</strong>
            <small>broadcast_id: <code>{committed.broadcast_id.slice(0, 12)}…</code></small>
            <p>每个 NPC 都会在协作消息池里收到一条同 broadcast_id 的指令。</p>
            <button type="button" className={styles.primaryBtn} onClick={onClose}>知道了</button>
          </div>
        ) : (
          <>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>标题（可选）</label>
              <input
                type="text"
                className={styles.input}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例如：节前主线对齐"
                maxLength={120}
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>广播内容</label>
              <textarea
                className={styles.textarea}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="把要交代给所有 NPC 的指令、验收标准、时间窗口写清楚……"
                rows={6}
              />
              <small className={styles.charCount}>{body.trim().length} 字</small>
            </div>

            {error ? <p className={styles.errorBox}>⚠ {error}</p> : null}

            {preview ? (
              <div className={styles.previewBox}>
                <div className={styles.previewHead}>
                  <strong>预演 · {preview.scope_label}</strong>
                  <span>影响 {preview.target_count} 个 NPC · 预估 ~{preview.estimated_tokens} tokens</span>
                </div>
                {preview.requires_human_review ? (
                  <p className={styles.reviewBox}>
                    🛡 需要人工审核
                    {typeof preview.review_force_count === "number" && preview.review_force_count > 0
                      ? ` · 其中 ${preview.review_force_count} 个 NPC 触发强审策略`
                      : " · 因量级（≥5 NPC 或 ≥1500 字）触发"}
                  </p>
                ) : null}
                {preview.blockers.length > 0 ? (
                  <ul className={styles.blockerList}>
                    {preview.blockers.map((b, i) => (
                      <li key={i}>⛔ {b}</li>
                    ))}
                  </ul>
                ) : null}
                {preview.warnings.length > 0 ? (
                  <ul className={styles.warningList}>
                    {preview.warnings.map((w, i) => (
                      <li key={i}>⚠ {w}</li>
                    ))}
                  </ul>
                ) : null}
                <details className={styles.targetList}>
                  <summary>展开 NPC 列表（{preview.targets.length}）</summary>
                  <ul>
                    {preview.targets.map((t) => {
                      const decision = preview.review_decisions?.find((d) => d.seat_id === t.id);
                      return (
                        <li key={t.id}>
                          <strong>{t.name}</strong>
                          <small>
                            {t.provider_label || "未绑定 provider"}
                            {t.responsibility ? ` · ${t.responsibility}` : ""}
                            {decision ? (
                              <span className={decision.requires_review ? styles.reviewTagForce : styles.reviewTagSkip}>
                                {decision.requires_review ? "🛡 强审" : "⚡ 免审"}（{decision.source}）
                              </span>
                            ) : null}
                          </small>
                        </li>
                      );
                    })}
                  </ul>
                </details>
              </div>
            ) : null}

            <footer className={styles.foot}>
              <button
                type="button"
                className={styles.secondaryBtn}
                onClick={runPreview}
                disabled={busy !== "idle" || !body.trim()}
              >
                {busy === "previewing" ? "预演中…" : preview ? "重新预演" : "预演（先看影响面 + token 估算）"}
              </button>
              <button
                type="button"
                className={styles.primaryBtn}
                onClick={runCommit}
                disabled={!preview?.ready || busy !== "idle"}
                title={!preview ? "先点预演" : !preview.ready ? "处理 blocker 后再发" : "正式派发到协作消息池"}
              >
                {busy === "committing" ? "派发中…" : "确认广播"}
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
