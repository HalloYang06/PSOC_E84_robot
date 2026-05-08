"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./npc-tile.module.css";
import { apiClientUrl } from "../../../../../lib/api-client-url";

export type WorkbenchSeat = {
  id: string;
  name: string;
  workstationId: string;
  workstationName: string;
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
  gitUserName: string;
  gitUserEmail: string;
  reviewPolicy: string;
  leadSeatId: string;
  isLead: boolean;
};

type NpcTileProps = {
  projectId: string;
  apiBaseUrl: string;
  seat: WorkbenchSeat;
  teammates: WorkbenchSeat[];
  crossLeads?: WorkbenchSeat[];
  currentUserId: string;
  currentUserName: string;
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

type RoleTrack = "human" | "self" | "peer" | "external" | "watcher" | "system";

function classifyRole(
  msg: CollabMessage,
  selfId: string,
  peerIds: Set<string>,
  externalAgentIds: Set<string>,
): { role: RoleTrack; label: string } {
  const senderType = (msg.sender_type || "").toLowerCase();
  const senderId = msg.sender_id || "";
  const recipientId = msg.recipient_id || "";
  const body = (msg.body || "").toLowerCase();
  const type = (msg.message_type || "").toLowerCase();

  if (senderType === "human") return { role: "human", label: "用户" };
  if (senderType === "runner" || senderType === "watcher" || type.includes("watcher") || type.includes("heartbeat") || body.startsWith("watcher")) {
    return { role: "watcher", label: "Claude CLI/Watcher" };
  }
  if (senderType === "agent" && senderId === selfId) return { role: "self", label: "本 NPC" };
  if (senderType === "agent" && peerIds.has(senderId)) return { role: "peer", label: "同工位 NPC" };
  if (senderType === "agent" && externalAgentIds.has(senderId)) return { role: "external", label: "跨工位 NPC" };
  if (senderType === "agent") return { role: "external", label: "其他 Agent" };
  if (recipientId === selfId && senderType === "system") return { role: "system", label: "系统" };
  return { role: "system", label: senderType || "系统" };
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

export function NpcTile({ projectId, apiBaseUrl, seat, teammates, crossLeads = [], currentUserId, currentUserName, onOpenTeammate, onClose }: NpcTileProps) {
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
  const [editingIdentity, setEditingIdentity] = useState(false);
  const [gitName, setGitName] = useState(seat.gitUserName);
  const [gitEmail, setGitEmail] = useState(seat.gitUserEmail);
  const [reviewPolicy, setReviewPolicy] = useState(seat.reviewPolicy || "inherit");
  const [savingIdentity, setSavingIdentity] = useState(false);
  const [identityNote, setIdentityNote] = useState<string | null>(null);
  const streamRef = useRef<HTMLDivElement | null>(null);
  const autoScrollRef = useRef(true);

  type SeatQueueItem = {
    id: string;
    title: string;
    status: string;
    priority?: string;
    module?: string | null;
    from_agent?: string | null;
    to_agent?: string | null;
    target_seat_id?: string | null;
    trigger_kind?: string;
    context_summary?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
    branch?: string | null;
    due_at?: string | null;
  };
  type SeatQueues = {
    requirement_inbox: { items: SeatQueueItem[]; count: number };
    task_todo: { items: SeatQueueItem[]; count: number };
  };
  type Receipt = {
    id: string;
    receipt_kind: "ack" | "progress" | "done" | "reject";
    parent_requirement_id: string;
    sender_seat_id: string | null;
    recipient_seat_id: string | null;
    cross_workstation: boolean;
    title: string | null;
    body: string;
    created_at: string | null;
  };
  const [seatQueues, setSeatQueues] = useState<SeatQueues | null>(null);
  const [receipts, setReceipts] = useState<Receipt[] | null>(null);
  const [queueTab, setQueueTab] = useState<"inbox" | "todo" | "dispatch">("inbox");
  const [receiptDirection, setReceiptDirection] = useState<"incoming" | "outgoing">("incoming");

  type Occupancy = {
    user_id: string;
    user_name?: string | null;
    acquired_at?: string | null;
    heartbeat_at?: string | null;
    preempted?: boolean;
    preempted_user?: string | null;
  };
  const [occupancy, setOccupancy] = useState<Occupancy | null>(null);
  const [occupancyError, setOccupancyError] = useState<string | null>(null);
  const [occupancyBusy, setOccupancyBusy] = useState(false);
  const occupancyHeldByMe = !!occupancy && occupancy.user_id === currentUserId;
  const occupancyHeldByOther = !!occupancy && !occupancyHeldByMe;

  const occupyUrl = apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/thread-workstations/${encodeURIComponent(seat.id)}`);

  const refreshOccupancy = useCallback(async () => {
    try {
      const res = await fetch(`${occupyUrl}/occupancy`, { credentials: "include" });
      const json = await res.json().catch(() => ({}));
      if (res.ok) {
        const occ = (json?.data?.occupancy ?? null) as Occupancy | null;
        setOccupancy(occ);
        setOccupancyError(null);
      }
    } catch (e) {
      setOccupancyError(e instanceof Error ? e.message : "查询占用失败");
    }
  }, [occupyUrl]);

  const claimOccupancy = useCallback(
    async (force: boolean) => {
      setOccupancyBusy(true);
      setOccupancyError(null);
      try {
        const res = await fetch(`${occupyUrl}/occupy`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ force, user_name: currentUserName }),
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
          throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        }
        const data = json?.data ?? {};
        if (data.ok === false) {
          setOccupancy((data.occupied_by ?? null) as Occupancy | null);
          setOccupancyError(`已被 ${data.occupied_by?.user_name || "他人"} 占用，可点"申请抢占"`);
        } else {
          setOccupancy((data.occupancy ?? null) as Occupancy | null);
          setOccupancyError(null);
        }
      } catch (e) {
        setOccupancyError(e instanceof Error ? e.message : "占用失败");
      } finally {
        setOccupancyBusy(false);
      }
    },
    [occupyUrl, currentUserName],
  );

  const releaseOccupancy = useCallback(
    async (silent: boolean = false) => {
      if (!silent) setOccupancyBusy(true);
      try {
        const res = await fetch(`${occupyUrl}/release`, {
          method: "POST",
          credentials: "include",
        });
        const json = await res.json().catch(() => ({}));
        if (res.ok && json?.data?.ok !== false) {
          setOccupancy(null);
          setOccupancyError(null);
        }
      } catch {
        // best-effort
      } finally {
        if (!silent) setOccupancyBusy(false);
      }
    },
    [occupyUrl],
  );

  // open-tile auto-occupy + close auto-release + 30s heartbeat
  useEffect(() => {
    let cancelled = false;
    (async () => {
      await refreshOccupancy();
      if (cancelled) return;
      // soft-claim: only if no one holds it
      try {
        const res = await fetch(`${occupyUrl}/occupy`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ force: false, user_name: currentUserName }),
        });
        const json = await res.json().catch(() => ({}));
        if (!cancelled && res.ok) {
          const data = json?.data ?? {};
          if (data.ok === false) {
            setOccupancy((data.occupied_by ?? null) as Occupancy | null);
          } else {
            setOccupancy((data.occupancy ?? null) as Occupancy | null);
          }
        }
      } catch {}
    })();
    const heartbeat = setInterval(() => {
      // re-claim only if I'm already the holder (refreshes heartbeat_at)
      setOccupancy((curr) => {
        if (curr && curr.user_id === currentUserId) {
          fetch(`${occupyUrl}/occupy`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ force: false, user_name: currentUserName }),
          }).catch(() => {});
        }
        return curr;
      });
      refreshOccupancy();
    }, 30000);
    return () => {
      cancelled = true;
      clearInterval(heartbeat);
      // best-effort release on close (only if I held it)
      releaseOccupancy(true);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seat.id]);

  async function saveIdentity() {
    setSavingIdentity(true);
    setIdentityNote(null);
    try {
      const res = await fetch(
        apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/thread-workstations/${encodeURIComponent(seat.id)}`),
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            metadata: {
              git_user_name: gitName.trim() || seat.name,
              git_user_email: gitEmail.trim() || `bot+${seat.id}@noreply.invalid`,
              review_policy: reviewPolicy,
            },
          }),
        },
      );
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setIdentityNote("已保存 ✓（刷新页面可见同步）");
      setEditingIdentity(false);
    } catch (e) {
      setIdentityNote(`保存失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setSavingIdentity(false);
      setTimeout(() => setIdentityNote(null), 4000);
    }
  }

  const load = useCallback(
    async (size: number) => {
      setFetching(true);
      setFetchError(null);
      try {
        const base = apiClientUrl(`/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&limit=${size}`);
        const incomingUrl = `${base}&recipient_type=thread_workstation&recipient_id=${encodeURIComponent(seat.id)}`;
        const outgoingUrl = `${base}&sender_id=${encodeURIComponent(seat.id)}`;
        const queuesUrl = apiClientUrl(`/api/seats/${encodeURIComponent(seat.id)}/queues?limit=30`);
        const receiptsUrl = apiClientUrl(`/api/receipts/by-seat/${encodeURIComponent(seat.id)}?direction=${receiptDirection}&limit=30`);
        const [r1, r2, r3, r4] = await Promise.all([
          fetch(incomingUrl, { credentials: "include" }),
          fetch(outgoingUrl, { credentials: "include" }),
          fetch(queuesUrl, { credentials: "include" }).catch(() => null),
          fetch(receiptsUrl, { credentials: "include" }).catch(() => null),
        ]);
        const j1 = await r1.json().catch(() => ({}));
        const j2 = await r2.json().catch(() => ({}));
        if (!r1.ok) {
          const msg = j1?.error?.message ?? j1?.message ?? `HTTP ${r1.status}`;
          throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        }
        const incoming = (j1?.data ?? []) as CollabMessage[];
        const outgoing = r2.ok ? ((j2?.data ?? []) as CollabMessage[]) : [];
        const seen = new Set<string>();
        const merged: CollabMessage[] = [];
        for (const m of [...incoming, ...outgoing]) {
          if (!m.id || seen.has(m.id)) continue;
          seen.add(m.id);
          merged.push(m);
        }
        merged.sort((a, b) => {
          const ta = a.created_at ? Date.parse(a.created_at) : 0;
          const tb = b.created_at ? Date.parse(b.created_at) : 0;
          return tb - ta;
        });
        setMessages(merged);
        if (r3 && r3.ok) {
          const j3 = await r3.json().catch(() => ({}));
          const data = (j3?.data ?? null) as SeatQueues | null;
          if (data) setSeatQueues(data);
        }
        if (r4 && r4.ok) {
          const j4 = await r4.json().catch(() => ({}));
          const data = (j4?.data ?? []) as Receipt[];
          setReceipts(Array.isArray(data) ? data : []);
        }
      } catch (e) {
        setFetchError(e instanceof Error ? e.message : "加载失败");
      } finally {
        setFetching(false);
      }
    },
    [apiBaseUrl, projectId, seat.id, receiptDirection],
  );

  useEffect(() => {
    load(limit);
  }, [load, limit]);

  useEffect(() => {
    const t = setInterval(() => load(limit), 15000);
    return () => clearInterval(t);
  }, [load, limit]);

  const peerIds = useMemo(() => new Set(teammates.map((t) => t.id)), [teammates]);
  const externalAgentIds = useMemo(() => {
    const ids = new Set<string>();
    for (const m of messages || []) {
      if ((m.sender_type || "").toLowerCase() === "agent" && m.sender_id && m.sender_id !== seat.id && !peerIds.has(m.sender_id)) {
        ids.add(m.sender_id);
      }
    }
    return ids;
  }, [messages, peerIds, seat.id]);

  const visible = useMemo(() => {
    const list = (messages || []).slice().reverse();
    if (!hideNoisy) return list;
    return list.filter((m) => !classifyMessage(m).noisy);
  }, [messages, hideNoisy]);

  const pendingReviews = useMemo(() => {
    return (messages || []).filter((m) => (m.status || "") === "pending_review");
  }, [messages]);

  // 我的任务队列：收件给本 NPC、still open、按 created_at 正序（FIFO）
  const myQueue = useMemo(() => {
    const arr = (messages || []).filter((m) => {
      if ((m.recipient_id || "") !== seat.id) return false;
      const t = (m.message_type || "").toLowerCase();
      if (!["agent_command", "requirement_dispatch", "comment_message"].includes(t)) return false;
      const s = (m.status || "").toLowerCase();
      return ["queued", "pending", "acked", "in_progress"].includes(s);
    });
    // 按 created_at 升序（最老在前 = 队首）
    return arr.slice().sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")));
  }, [messages, seat.id]);

  const [reviewBusyId, setReviewBusyId] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState<string | null>(null);
  async function reviewMessage(id: string, action: "approve" | "reject") {
    setReviewBusyId(id);
    setReviewNote(null);
    try {
      const res = await fetch(apiClientUrl(`/api/collaboration/messages/${encodeURIComponent(id)}/review/${action}`), {
        method: "POST",
        credentials: "include",
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setReviewNote(action === "approve" ? "✓ 已通过" : "✓ 已打回");
      await load(limit);
    } catch (e) {
      setReviewNote(`失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setReviewBusyId(null);
      setTimeout(() => setReviewNote(null), 4000);
    }
  }

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

  async function sendCommand(opts?: { peerId?: string; peerName?: string }) {
    const body = draft.trim();
    if (!body) return;
    setSending(true);
    setSendNote(null);
    const isPeer = !!opts?.peerId;
    try {
      const res = await fetch(apiClientUrl("/api/collaboration/messages"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          project_id: projectId,
          message_type: "comment_message",
          title: isPeer ? `[NPC ${seat.name} → ${opts!.peerName || opts!.peerId}] 同工位派单` : null,
          body,
          // 同工位伙伴派单：sender 用本 NPC（agent + seat.id），recipient = 对方 seat.id
          sender_type: isPeer ? "agent" : "human",
          sender_id: isPeer ? seat.id : null,
          recipient_type: "thread_workstation",
          recipient_id: isPeer ? opts!.peerId! : seat.id,
          status: "queued",
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setDraft("");
      setSendNote(isPeer ? `已派给 ${opts!.peerName || opts!.peerId} ✓` : "已派发 ✓");
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
            {seat.isLead ? (
              <span className={styles.leadChip} title="本工位的工位长：跨工位消息默认转交给此 NPC">
                👑 工位长
              </span>
            ) : null}
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

      <div
        className={`${styles.occupancyBar} ${
          occupancyHeldByMe
            ? styles.occupancyMine
            : occupancyHeldByOther
              ? styles.occupancyOther
              : styles.occupancyIdle
        }`}
      >
        <span className={styles.occupancyDot} aria-hidden />
        <span className={styles.occupancyText}>
          {occupancyHeldByMe
            ? `🟢 你正在占用此 NPC`
            : occupancyHeldByOther
              ? `🟡 ${occupancy?.user_name || occupancy?.user_id} 正在占用`
              : `⚪ 空闲，可占用`}
        </span>
        {occupancyHeldByMe ? (
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => releaseOccupancy(false)}
            disabled={occupancyBusy}
            title="释放占用，让其他人可以接手"
          >
            释放
          </button>
        ) : occupancyHeldByOther ? (
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => claimOccupancy(true)}
            disabled={occupancyBusy}
            title="强制抢占（对方会被踢下来）"
          >
            申请抢占
          </button>
        ) : (
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => claimOccupancy(false)}
            disabled={occupancyBusy}
            title="占用此 NPC，避免他人同时操作"
          >
            占用
          </button>
        )}
        {occupancyError ? <small className={styles.occupancyHint}>{occupancyError}</small> : null}
      </div>

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
              GitHub 身份
              <span className={styles.peerHint}>· commit author（SSH 推送本机配）</span>
            </small>
            {editingIdentity ? (
              <div className={styles.identityForm}>
                <input
                  className={styles.identityInput}
                  value={gitName}
                  onChange={(e) => setGitName(e.target.value)}
                  placeholder="git user.name"
                />
                <input
                  className={styles.identityInput}
                  value={gitEmail}
                  onChange={(e) => setGitEmail(e.target.value)}
                  placeholder="git user.email"
                />
                <select
                  className={styles.identityInput}
                  value={reviewPolicy}
                  onChange={(e) => setReviewPolicy(e.target.value)}
                  title="人工审核策略：inherit 跟工位/项目，force 强审，skip 免审"
                >
                  <option value="inherit">审核：继承（项目/工位）</option>
                  <option value="force">审核：强审（必经）</option>
                  <option value="skip">审核：免审（直接落地）</option>
                </select>
                <div className={styles.identityActions}>
                  <button type="button" className={styles.iconBtn} onClick={saveIdentity} disabled={savingIdentity}>
                    {savingIdentity ? "保存中…" : "保存"}
                  </button>
                  <button
                    type="button"
                    className={styles.iconBtn}
                    onClick={() => {
                      setEditingIdentity(false);
                      setGitName(seat.gitUserName);
                      setGitEmail(seat.gitUserEmail);
                      setReviewPolicy(seat.reviewPolicy || "inherit");
                    }}
                  >
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <div className={styles.identityRow}>
                <p className={styles.profileText}>
                  <code className={styles.code}>{seat.gitUserName}</code>{" "}
                  <code className={styles.code}>&lt;{seat.gitUserEmail}&gt;</code>
                </p>
                <small className={styles.identityMeta}>
                  审核：
                  <span className={styles.reviewBadge} data-policy={seat.reviewPolicy}>
                    {seat.reviewPolicy === "force" ? "强审" : seat.reviewPolicy === "skip" ? "免审" : "继承"}
                  </span>
                </small>
                <button type="button" className={styles.iconBtn} onClick={() => setEditingIdentity(true)}>
                  改
                </button>
              </div>
            )}
            {identityNote ? <small className={styles.identityNote}>{identityNote}</small> : null}
          </div>
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
                  <div key={peer.id} className={styles.peerChip} data-lead={peer.isLead ? "1" : "0"}>
                    <button
                      type="button"
                      className={styles.peerOpenBtn}
                      onClick={() => onOpenTeammate(peer.id)}
                      title={`打开 ${peer.name} 的瓷砖${peer.isLead ? "（工位长）" : ""}`}
                    >
                      <span className={styles.peerName}>
                        {peer.isLead ? "👑 " : ""}
                        {peer.name}
                      </span>
                      <span className={styles.peerMeta}>{peer.providerLabel || peer.providerId || "—"}</span>
                    </button>
                    <button
                      type="button"
                      className={styles.peerDispatchBtn}
                      onClick={() => {
                        if (!draft.trim()) {
                          setSendNote(`先在底部 textarea 写内容，再点「派给 ${peer.name}」`);
                          setTimeout(() => setSendNote(null), 4000);
                          return;
                        }
                        sendCommand({ peerId: peer.id, peerName: peer.name });
                      }}
                      disabled={sending}
                      title={`以 ${seat.name} 身份直接派单给 ${peer.name}（同工位免审）`}
                    >
                      → 派
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          {crossLeads.length > 0 ? (
            <div className={styles.profileRow}>
              <small className={styles.sectionLabel}>
                跨工位通道（经工位长，{crossLeads.length}）
                <span className={styles.peerHint}>· 跨工位禁直派；后端兜底改寄给目标工位的工位长</span>
              </small>
              <div className={styles.peerRow}>
                {crossLeads.map((lead) => (
                  <div key={lead.id} className={styles.peerChip} data-cross="1">
                    <button
                      type="button"
                      className={styles.peerOpenBtn}
                      onClick={() => onOpenTeammate(lead.id)}
                      title={`打开 ${lead.name}（${lead.computerNodeName} 的工位长）的瓷砖`}
                    >
                      <span className={styles.peerName}>👑 {lead.name}</span>
                      <span className={styles.peerMeta}>{lead.computerNodeName || lead.computerNodeId}</span>
                    </button>
                    <button
                      type="button"
                      className={styles.peerDispatchBtn}
                      data-cross="1"
                      onClick={() => {
                        if (!draft.trim()) {
                          setSendNote(`先在底部 textarea 写内容，再点「→ 转交工位长 ${lead.name}」`);
                          setTimeout(() => setSendNote(null), 4000);
                          return;
                        }
                        sendCommand({ peerId: lead.id, peerName: lead.name });
                      }}
                      disabled={sending}
                      title={`以 ${seat.name} 身份请 ${lead.name}（${lead.computerNodeName} 工位长）转交（默认走人审）`}
                    >
                      → 转交
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {pendingReviews.length > 0 ? (
        <div className={styles.reviewBox}>
          <div className={styles.reviewHead}>
            <strong>📌 待审：自主合作消息（{pendingReviews.length}）</strong>
            <small className={styles.muted}>跨工位默认走人审；通过后才会派给本 NPC，打回则取消。</small>
          </div>
          <ul className={styles.reviewList}>
            {pendingReviews.slice(0, 5).map((m) => {
              const body = String(m.body || "");
              const crossMatch = body.match(/跨工位：([是否])/);
              const sourceMatch = body.match(/来源：([a-z_]+)/);
              const upstreamMatch = body.match(/上游 NPC:\s*([^\r\n]+)/);
              const isCross = crossMatch?.[1] === "是";
              const source = sourceMatch?.[1] || "";
              const upstream = upstreamMatch?.[1]?.trim() || "";
              return (
              <li key={m.id} className={styles.reviewItem}>
                <div className={styles.reviewMeta}>
                  <span className={styles.reviewSender}>
                    {upstream ? `来自 NPC ${upstream}` : `来自 ${(m.sender_type || "?")}/${String(m.sender_id || "").slice(0, 10)}`}
                    {isCross ? <span style={{ marginLeft: 6, padding: "1px 6px", borderRadius: 999, background: "rgba(255,232,109,0.16)", border: "1px solid rgba(255,232,109,0.4)", color: "#ffe8b3", fontSize: 10 }}>跨工位</span> : null}
                    {source ? <span style={{ marginLeft: 4, padding: "1px 6px", borderRadius: 999, background: "rgba(88,240,255,0.12)", border: "1px solid rgba(88,240,255,0.28)", color: "#b9fff3", fontSize: 10 }}>policy: {source}</span> : null}
                  </span>
                  <span className={styles.reviewTitle}>{m.title || body.slice(0, 60)}</span>
                </div>
                <div className={styles.reviewActions}>
                  <button
                    type="button"
                    className={styles.reviewApproveBtn}
                    disabled={reviewBusyId === m.id}
                    onClick={() => reviewMessage(m.id, "approve")}
                  >
                    通过
                  </button>
                  <button
                    type="button"
                    className={styles.reviewRejectBtn}
                    disabled={reviewBusyId === m.id}
                    onClick={() => reviewMessage(m.id, "reject")}
                  >
                    打回
                  </button>
                </div>
              </li>
              );
            })}
          </ul>
          {reviewNote ? <small className={styles.reviewNote}>{reviewNote}</small> : null}
        </div>
      ) : null}

      {(() => {
        const inboxItems = seatQueues?.requirement_inbox.items ?? [];
        const todoItems = seatQueues?.task_todo.items ?? [];
        const dispatchItems = myQueue;
        const inboxCount = seatQueues?.requirement_inbox.count ?? 0;
        const todoCount = seatQueues?.task_todo.count ?? 0;
        if (inboxCount === 0 && todoCount === 0 && dispatchItems.length === 0 && (receipts?.length ?? 0) === 0) {
          return null;
        }
        const activeItems = queueTab === "inbox" ? inboxItems : queueTab === "todo" ? todoItems : null;
        return (
          <div className={styles.queueBox}>
            <div className={styles.queueHead}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={() => setQueueTab("inbox")}
                  className={styles.iconBtn}
                  data-active={queueTab === "inbox" ? "1" : undefined}
                  title="需求队列：别人/自己派给我、未关闭的 requirement"
                >
                  📥 需求 {inboxCount}
                </button>
                <button
                  type="button"
                  onClick={() => setQueueTab("todo")}
                  className={styles.iconBtn}
                  data-active={queueTab === "todo" ? "1" : undefined}
                  title="任务队列：以本 NPC 的 agent 为 assignee 的未结 task"
                >
                  📋 任务 {todoCount}
                </button>
                <button
                  type="button"
                  onClick={() => setQueueTab("dispatch")}
                  className={styles.iconBtn}
                  data-active={queueTab === "dispatch" ? "1" : undefined}
                  title="派单消息：直接发给本 NPC 的 collaboration_message"
                >
                  ✉ 派单 {dispatchItems.length}
                </button>
              </div>
              <small className={styles.muted}>
                {queueTab === "inbox" ? "未接 / 在评估" : queueTab === "todo" ? "已接 task" : "FIFO；最老在最上"}
              </small>
            </div>
            {queueTab === "dispatch" ? (
              <ul className={styles.queueList}>
                {dispatchItems.slice(0, 6).map((m, i) => {
                  const isFromPeer = (m.sender_type || "").toLowerCase() === "agent" && peerIds.has(m.sender_id || "");
                  const isFromExternal = (m.sender_type || "").toLowerCase() === "agent" && !!m.sender_id && m.sender_id !== seat.id && !peerIds.has(m.sender_id);
                  const fromLabel = isFromPeer
                    ? `同工位 · ${teammates.find((t) => t.id === m.sender_id)?.name || m.sender_id}`
                    : isFromExternal
                      ? `跨工位 · ${m.sender_id}`
                      : (m.sender_type || "?");
                  return (
                    <li key={m.id} className={styles.queueItem} data-from={isFromPeer ? "peer" : isFromExternal ? "external" : (m.sender_type || "")}>
                      <span className={styles.queuePos}>#{i + 1}</span>
                      <div className={styles.queueMeta}>
                        <span className={styles.queueFrom}>{fromLabel}</span>
                        <span className={styles.queueTitle}>{m.title || (m.body || "").slice(0, 60) || "(无标题)"}</span>
                      </div>
                      <span className={styles.queueStatus} data-status={m.status}>{m.status}</span>
                    </li>
                  );
                })}
              </ul>
            ) : activeItems && activeItems.length > 0 ? (
              <ul className={styles.queueList}>
                {activeItems.slice(0, 6).map((it, i) => (
                  <li key={it.id} className={styles.queueItem} data-from={queueTab}>
                    <span className={styles.queuePos}>#{i + 1}</span>
                    <div className={styles.queueMeta}>
                      <span className={styles.queueFrom}>
                        {queueTab === "inbox"
                          ? (it.from_agent ? `← ${it.from_agent}` : it.trigger_kind || "manual")
                          : (it.module ? `module: ${it.module}` : it.priority || "—")}
                      </span>
                      <span className={styles.queueTitle}>{it.title || "(无标题)"}</span>
                    </div>
                    <span className={styles.queueStatus} data-status={it.status}>{it.status}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.muted} style={{ paddingLeft: 8 }}>
                {queueTab === "inbox" ? "暂无需求" : "暂无任务"}
              </p>
            )}
            {queueTab === "dispatch" && dispatchItems.length > 6 ? (
              <small className={styles.muted}>… 还有 {dispatchItems.length - 6} 条</small>
            ) : null}
            {queueTab !== "dispatch" && activeItems && activeItems.length > 6 ? (
              <small className={styles.muted}>… 还有 {activeItems.length - 6} 条</small>
            ) : null}
          </div>
        );
      })()}

      {receipts && receipts.length > 0 ? (
        <div className={styles.queueBox}>
          <div className={styles.queueHead}>
            <strong>🧾 回执流（{receipts.length}）</strong>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                type="button"
                onClick={() => setReceiptDirection("incoming")}
                className={styles.iconBtn}
                data-active={receiptDirection === "incoming" ? "1" : undefined}
                title="发给我的回执"
              >
                📨 收到
              </button>
              <button
                type="button"
                onClick={() => setReceiptDirection("outgoing")}
                className={styles.iconBtn}
                data-active={receiptDirection === "outgoing" ? "1" : undefined}
                title="我发的回执"
              >
                📤 发出
              </button>
            </div>
          </div>
          <ul className={styles.queueList}>
            {receipts.slice(0, 6).map((r) => {
              const kindLabel = ({ ack: "已接", progress: "进度", done: "完成", reject: "拒绝" } as const)[r.receipt_kind];
              return (
                <li key={r.id} className={styles.queueItem} data-from={r.cross_workstation ? "external" : "peer"}>
                  <span className={styles.queuePos}>{kindLabel}</span>
                  <div className={styles.queueMeta}>
                    <span className={styles.queueFrom}>
                      {r.cross_workstation ? "跨工位" : "同工位"}
                      {" · "}
                      {receiptDirection === "incoming"
                        ? (r.sender_seat_id ? `← ${r.sender_seat_id.slice(0, 8)}` : "(系统)")
                        : (r.recipient_seat_id ? `→ ${r.recipient_seat_id.slice(0, 8)}` : "(广播)")}
                    </span>
                    <span className={styles.queueTitle}>{r.title || r.body.slice(0, 60) || "(无标题)"}</span>
                  </div>
                  <span className={styles.queueStatus} data-status={r.receipt_kind}>{r.receipt_kind}</span>
                </li>
              );
            })}
          </ul>
          {receipts.length > 6 ? <small className={styles.muted}>… 还有 {receipts.length - 6} 条</small> : null}
        </div>
      ) : null}

      <div className={styles.streamToolbar}>
        <div className={styles.streamToolbarLeft}>
          <strong>消息流</strong>
          <small>
            {filteredCount}/{totalLoaded} 条{fetching ? " · 刷新中…" : ""}
          </small>
          <small className={styles.legend} title="按发送方/性质着色：人灰｜本NPC青｜同工位绿｜跨工位紫｜回执蓝｜系统红｜自主合作黄">
            <span className={`${styles.legendDot} ${styles.roleBadge_human}`}>人</span>
            <span className={`${styles.legendDot} ${styles.roleBadge_self}`}>我</span>
            <span className={`${styles.legendDot} ${styles.roleBadge_peer}`}>同工位</span>
            <span className={`${styles.legendDot} ${styles.roleBadge_external}`}>跨工位</span>
            <span className={`${styles.legendDot} ${styles.roleBadge_watcher}`}>CLI</span>
            <span className={`${styles.legendDot} ${styles.roleBadge_system}`}>系统</span>
          </small>
        </div>        <div className={styles.streamToolbarRight}>
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
            const { role, label: roleLabel } = classifyRole(msg, seat.id, peerIds, externalAgentIds);
            const expanded = expandedIds.has(msg.id);
            const body = msg.body || "";
            const canExpand = body.length > 160 || body.includes("\n");
            const senderLabel =
              role === "human"
                ? "用户"
                : role === "self"
                  ? `本 NPC · ${seat.name}`
                  : role === "peer"
                    ? `同工位 · ${teammates.find((t) => t.id === msg.sender_id)?.name || msg.sender_id}`
                    : role === "external"
                      ? `跨工位 · ${msg.sender_id || "?"}`
                      : role === "watcher"
                        ? "Claude CLI / Watcher"
                        : roleLabel;
            return (
              <div
                key={msg.id}
                className={`${styles.msg} ${styles[`msg_${kind}`] || ""} ${styles[`role_${role}`] || ""}`}
                data-role={role}
              >
                <div className={styles.msgHead}>
                  <span className={`${styles.roleBadge} ${styles[`roleBadge_${role}`] || ""}`} title={senderLabel}>
                    {senderLabel}
                  </span>
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
            {occupancyHeldByOther
              ? `⚠ ${occupancy?.user_name || "他人"} 正在占用，先抢占再发送`
              : sendNote || (seat.permissionLevel ? `权限：${seat.permissionLevel}` : "发送后会写入协作消息池，目标线程 watcher 会拉到")}
          </small>
          <div className={styles.composerActions}>
            <Link href={`/projects/${projectId}/cockpit`} className={styles.linkBtn} title="返回项目驾驶舱">
              驾驶舱
            </Link>
            <button
              type="submit"
              className={styles.sendBtn}
              disabled={sending || !draft.trim() || occupancyHeldByOther}
              title={occupancyHeldByOther ? "他人占用中，请先抢占" : "派发消息"}
            >
              {sending ? "派发中…" : "发送"}
            </button>
          </div>
        </div>
      </form>
    </article>
  );
}
