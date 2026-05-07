"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./npc-tile.module.css";

export type WorkbenchSeat = {
  id: string;
  name: string;
  computerNodeId: string;
  computerNodeName: string;
  providerId: string;
  providerLabel: string;
  responsibility: string;
  skillLoadout: string[];
  knowledgeSummary: string;
  automationEnabled: boolean;
  model: string;
  permissionLevel: string;
};

type NpcTileProps = {
  projectId: string;
  apiBaseUrl: string;
  seat: WorkbenchSeat;
  teammates: WorkbenchSeat[];
  onOpenTeammate: (id: string) => void;
  onClose: () => void;
};

type CollabMessage = {
  id: string;
  message_type: string;
  title: string | null;
  body: string;
  sender_type: string;
  sender_id: string | null;
  recipient_type: string | null;
  recipient_id: string | null;
  status: string;
  created_at?: string | null;
  dispatch_id?: string | null;
};

const NOISE_PREFIXES = [
  "watcher 启动",
  "watcher started",
  "mcp 启动",
  "mcp loaded",
  "mcp server",
  "heartbeat",
  "心跳",
];

function classifyMessage(msg: CollabMessage): { kind: "command" | "result" | "error" | "note"; summary: string; noisy: boolean } {
  const body = (msg.body || "").trim();
  const bodyLower = body.toLowerCase();
  const noisy = NOISE_PREFIXES.some((p) => bodyLower.startsWith(p.toLowerCase()));
  const type = (msg.message_type || "").toLowerCase();
  let kind: "command" | "result" | "error" | "note" = "note";
  if (type.includes("command") || type === "requirement_dispatch" || msg.sender_type === "human") kind = "command";
  else if (type.includes("result") || type === "ai_reply") kind = "result";
  if ((msg.status || "").toLowerCase() === "failed" || bodyLower.includes("error") || bodyLower.includes("失败")) kind = "error";

  const title = (msg.title || "").trim();
  let summary = title;
  if (!summary) {
    const firstLine = body.split(/\r?\n/).map((s) => s.trim()).find(Boolean) || "";
    summary = firstLine.slice(0, 160);
  }
  if (!summary) summary = "(空消息)";
  return { kind, summary, noisy };
}

function formatTime(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function NpcTile({ projectId, apiBaseUrl, seat, teammates, onOpenTeammate, onClose }: NpcTileProps) {
  const [messages, setMessages] = useState<CollabMessage[] | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [hideNoisy, setHideNoisy] = useState(true);
  const [limit, setLimit] = useState(50);
  const [fetching, setFetching] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendNote, setSendNote] = useState<string | null>(null);
  const [headerCollapsed, setHeaderCollapsed] = useState(false);
  const [senderSeatId, setSenderSeatId] = useState<string>("");
  const streamRef = useRef<HTMLDivElement | null>(null);
  const autoScrollRef = useRef(true);

  const load = useCallback(
    async (size: number) => {
      setFetching(true);
      setFetchError(null);
      try {
        const url = `${apiBaseUrl}/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&recipient_type=thread_workstation&recipient_id=${encodeURIComponent(seat.id)}&limit=${size}`;
        const res = await fetch(url, { credentials: "include" });
        const json = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
          throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        }
        const data = (json?.data ?? []) as CollabMessage[];
        setMessages(data);
      } catch (e) {
        setFetchError(e instanceof Error ? e.message : "加载失败");
      } finally {
        setFetching(false);
      }
    },
    [apiBaseUrl, projectId, seat.id],
  );

  useEffect(() => {
    load(limit);
  }, [load, limit]);

  useEffect(() => {
    const t = setInterval(() => load(limit), 15000);
    return () => clearInterval(t);
  }, [load, limit]);

  const visible = useMemo(() => {
    const list = (messages || []).slice().reverse();
    if (!hideNoisy) return list;
    return list.filter((m) => !classifyMessage(m).noisy);
  }, [messages, hideNoisy]);

  useEffect(() => {
    if (!streamRef.current || !autoScrollRef.current) return;
    streamRef.current.scrollTop = streamRef.current.scrollHeight;
  }, [visible.length]);

  function onStreamScroll() {
    const el = streamRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    autoScrollRef.current = atBottom;
  }

  function toggleExpand(id: string) {
    setExpandedIds((curr) => {
      const next = new Set(curr);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function sendCommand() {
    const body = draft.trim();
    if (!body) return;
    setSending(true);
    setSendNote(null);
    const peerSeat = senderSeatId ? teammates.find((t) => t.id === senderSeatId) : null;
    try {
      const res = await fetch(`${apiBaseUrl}/api/collaboration/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          project_id: projectId,
          message_type: "comment_message",
          title: peerSeat ? `[同工位] ${peerSeat.name} → ${seat.name}` : null,
          body: peerSeat ? `（代发自 ${peerSeat.name}）\n\n${body}` : body,
          sender_type: peerSeat ? "agent" : "human",
          sender_id: peerSeat ? peerSeat.id : null,
          recipient_type: "thread_workstation",
          recipient_id: seat.id,
          status: "open",
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setDraft("");
      setSendNote(peerSeat ? `已以 ${peerSeat.name} 名义派发 ✓` : "已派发 ✓");
      autoScrollRef.current = true;
      await load(limit);
    } catch (e) {
      setSendNote(`派发失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setSending(false);
      setTimeout(() => setSendNote(null), 4000);
    }
  }

  const totalLoaded = messages?.length ?? 0;
  const filteredCount = visible.length;

  return (
    <article className={styles.tile}>
      <header className={styles.head}>
        <div className={styles.headLeft}>
          <strong className={styles.name} title={seat.name}>
            {seat.name}
          </strong>
          <small className={styles.subline}>
            <span title="所属电脑">🖥 {seat.computerNodeName || "未绑定"}</span>
            <span title="模型 provider">⚙ {seat.providerLabel || seat.providerId || "未绑定"}</span>
            {seat.model ? <span>· {seat.model}</span> : null}
            {seat.automationEnabled ? <span className={styles.pillOk}>自动化</span> : null}
          </small>
        </div>
        <div className={styles.headActions}>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => setHeaderCollapsed((v) => !v)}
            title={headerCollapsed ? "展开职责/技能/知识库" : "收起职责/技能/知识库（让消息流占更多空间）"}
          >
            {headerCollapsed ? "展开档案" : "收起档案"}
          </button>
          <button type="button" className={styles.closeBtn} onClick={onClose} title="关闭这个瓷砖">✕</button>
        </div>
      </header>

      {!headerCollapsed ? (
        <section className={styles.profile}>
          <div className={styles.profileRow}>
            <small className={styles.sectionLabel}>职责</small>
            <p className={styles.profileText}>{seat.responsibility || "未填写"}</p>
          </div>
          {seat.skillLoadout.length > 0 ? (
            <div className={styles.profileRow}>
              <small className={styles.sectionLabel}>Skill ({seat.skillLoadout.length})</small>
              <div className={styles.chipRow}>
                {seat.skillLoadout.slice(0, 6).map((skill) => (
                  <span key={skill} className={styles.chip}>{skill}</span>
                ))}
                {seat.skillLoadout.length > 6 ? (
                  <span className={styles.chipMore}>+{seat.skillLoadout.length - 6}</span>
                ) : null}
              </div>
            </div>
          ) : null}
          {seat.knowledgeSummary ? (
            <div className={styles.profileRow}>
              <small className={styles.sectionLabel}>知识库</small>
              <p className={styles.profileText}>
                {seat.knowledgeSummary.length > 140
                  ? `${seat.knowledgeSummary.slice(0, 140)}…`
                  : seat.knowledgeSummary}
              </p>
            </div>
          ) : null}
          <div className={styles.profileRow}>
            <small className={styles.sectionLabel}>
              同工位伙伴 ({teammates.length})
              <span className={styles.peerHint}>
                {seat.computerNodeId ? "· 同电脑可直接互发，免审" : "· 未绑定电脑"}
              </span>
            </small>
            {teammates.length === 0 ? (
              <p className={styles.profileTextDim}>同工位暂无其他 NPC。</p>
            ) : (
              <div className={styles.peerRow}>
                {teammates.map((peer) => (
                  <div key={peer.id} className={styles.peerChipGroup}>
                    <button
                      type="button"
                      className={styles.peerChip}
                      onClick={() => onOpenTeammate(peer.id)}
                      title={`打开 ${peer.name} 的瓷砖`}
                    >
                      <span className={styles.peerName}>{peer.name}</span>
                      <span className={styles.peerMeta}>{peer.providerLabel || peer.providerId || "—"}</span>
                    </button>
                    <button
                      type="button"
                      className={styles.peerSendBtn}
                      onClick={() => {
                        setSenderSeatId(peer.id);
                        const ta = document.querySelector<HTMLTextAreaElement>(`textarea[data-tile-id="${seat.id}"]`);
                        ta?.focus();
                      }}
                      title={`以 ${peer.name} 的名义给 ${seat.name} 发指令`}
                    >
                      代他派
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      ) : null}

      <div className={styles.streamToolbar}>
        <div className={styles.streamToolbarLeft}>
          <strong>消息流</strong>
          <small>
            {filteredCount}/{totalLoaded} 条{fetching ? " · 刷新中…" : ""}
          </small>
        </div>
        <div className={styles.streamToolbarRight}>
          <label className={styles.noiseToggle} title="过滤 watcher 启动 / mcp 加载 / heartbeat 等噪声日志">
            <input type="checkbox" checked={hideNoisy} onChange={(e) => setHideNoisy(e.target.checked)} />
            过滤噪声
          </label>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => setLimit((v) => Math.min(v + 50, 500))}
            disabled={fetching || limit >= 500}
            title="加载更早的消息"
          >
            更多历史（当前 {limit}）
          </button>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => load(limit)}
            disabled={fetching}
            title="手动刷新"
          >
            ⟳
          </button>
        </div>
      </div>

      <div
        className={styles.stream}
        ref={streamRef}
        onScroll={onStreamScroll}
      >
        {fetchError ? (
          <p className={styles.emptyError}>⚠ 加载失败：{fetchError}</p>
        ) : visible.length === 0 ? (
          <p className={styles.emptyHint}>
            {messages === null
              ? "加载中…"
              : hideNoisy && totalLoaded > 0
                ? "过滤后无消息，取消勾选「过滤噪声」看完整流。"
                : "暂无消息。"}
          </p>
        ) : (
          visible.map((msg) => {
            const { kind, summary } = classifyMessage(msg);
            const expanded = expandedIds.has(msg.id);
            const body = msg.body || "";
            const canExpand = body.length > 160 || body.includes("\n");
            return (
              <div key={msg.id} className={`${styles.msg} ${styles[`msg_${kind}`] || ""}`}>
                <div className={styles.msgHead}>
                  <span className={`${styles.badge} ${styles[`badge_${kind}`] || ""}`}>
                    {kind === "command" ? "派单" : kind === "result" ? "回执" : kind === "error" ? "错误" : "备注"}
                  </span>
                  <small className={styles.msgTime}>{formatTime(msg.created_at)}</small>
                  <small className={styles.msgStatus}>{msg.status}</small>
                </div>
                <p className={styles.msgSummary}>{summary}</p>
                {expanded ? (
                  <pre className={styles.msgFull}>{body}</pre>
                ) : canExpand ? (
                  <button
                    type="button"
                    className={styles.inlineBtn}
                    onClick={() => toggleExpand(msg.id)}
                    title="查看完整内容"
                  >
                    展开完整 ({body.length} 字)
                  </button>
                ) : null}
                {expanded ? (
                  <button
                    type="button"
                    className={styles.inlineBtn}
                    onClick={() => toggleExpand(msg.id)}
                  >
                    收起
                  </button>
                ) : null}
              </div>
            );
          })
        )}
      </div>

      <form
        className={styles.composer}
        onSubmit={(e) => {
          e.preventDefault();
          if (!sending) sendCommand();
        }}
      >
        {teammates.length > 0 ? (
          <div className={styles.composerSenderRow}>
            <small className={styles.sectionLabel}>身份</small>
            <select
              className={styles.composerSender}
              value={senderSeatId}
              onChange={(e) => setSenderSeatId(e.target.value)}
              title="选择以谁的身份发送：默认是你（用户），也可以代任意同工位 NPC 发"
            >
              <option value="">以"我"（用户）派单</option>
              {teammates.map((p) => (
                <option key={p.id} value={p.id}>
                  代 {p.name} 同工位互发
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <textarea
          data-tile-id={seat.id}
          className={styles.composerInput}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`给 ${seat.name} 发指令（Ctrl+Enter 发送）`}
          rows={2}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault();
              if (!sending && draft.trim()) sendCommand();
            }
          }}
        />
        <div className={styles.composerFoot}>
          <small className={styles.composerHint}>
            {sendNote || (seat.permissionLevel ? `权限：${seat.permissionLevel}` : "发送后会写入协作消息池，目标线程 watcher 会拉到")}
          </small>
          <div className={styles.composerActions}>
            <Link href={`/projects/${projectId}`} className={styles.linkBtn} title="返回项目驾驶舱">
              驾驶舱
            </Link>
            <button
              type="submit"
              className={styles.sendBtn}
              disabled={sending || !draft.trim()}
            >
              {sending ? "派发中…" : "发送"}
            </button>
          </div>
        </div>
      </form>
    </article>
  );
}
