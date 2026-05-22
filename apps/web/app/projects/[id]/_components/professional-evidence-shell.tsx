import Link from "next/link";
import type { ReactNode } from "react";
import styles from "./professional-evidence-shell.module.css";

type AnyRecord = Record<string, any>;

type QuickLink = {
  label: string;
  href: string;
  active?: boolean;
  detail?: string;
};

type ActionLink = {
  label: string;
  href: string;
  primary?: boolean;
};

type CapabilityCard = {
  label: string;
  detail: string;
  href?: string;
};

type ArtifactCard = {
  label: string;
  path: string;
  href?: string;
  detail?: string;
  actionLabel?: string;
};

type SignalCard = {
  label: string;
  value: string;
  detail: string;
  href?: string;
  actionLabel?: string;
};

type ConsoleTone = "info" | "success" | "warning" | "error" | "review" | "npc";

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function exceptionSummary(view: AnyRecord | null): AnyRecord {
  const summary = view?.summary?.exception_summary;
  return summary && typeof summary === "object" ? (summary as AnyRecord) : {};
}

function artifactTitle(path: string) {
  return path.split(/[\\/]/).pop() || path;
}

function artifactDetail(path: string) {
  const normalized = text(path, "").replace(/\\/g, "/");
  if (!normalized) return "产出文件";
  const parts = normalized.split("/").filter(Boolean);
  const tail = parts.slice(-2);
  return tail.length ? tail.join(" / ") : normalized;
}

function taskArtifacts(view: AnyRecord | null, projectId: string, pageKey: string): ArtifactCard[] {
  const messages = Array.isArray(view?.messages) ? (view?.messages as AnyRecord[]) : [];
  const artifacts: ArtifactCard[] = [];
  const seen = new Set<string>();
  for (const message of messages) {
    const refs = Array.isArray(message?.artifact_refs) ? (message.artifact_refs as AnyRecord[]) : [];
    for (const ref of refs) {
      const path = text(ref.path, "");
      if (!path || seen.has(path)) continue;
      seen.add(path);
      const sourceMessageId = text(ref.source_message_id, "");
      artifacts.push({
        label: text(ref.label, artifactTitle(path) || "artifact"),
        path,
        detail: artifactDetail(path),
        actionLabel: sourceMessageId ? "回消息看产出" : "查看记录",
        href: sourceMessageId
          ? `/projects/${projectId}/workbench?from=${pageKey}&message_id=${encodeURIComponent(sourceMessageId)}`
            : `/projects/${projectId}/observability?from=${pageKey}&task_id=${encodeURIComponent(text(view?.task?.id, ""))}`,
      });
    }
  }
  return artifacts.slice(0, 6);
}

function userStatus(value: unknown, fallback = "等待") {
  const normalized = text(value, "").toLowerCase();
  if (!normalized) return fallback;
  if (/completed|complete|done|resolved|passed|success|ready|ok|can_continue/.test(normalized)) return "可继续";
  if (/running|active|in_progress|accepted|queued|pending/.test(normalized)) return "处理中";
  if (/review|approval|human/.test(normalized)) return "需人工确认";
  if (/pending_closeout|closeout/.test(normalized)) return "等结果";
  if (/blocked|failed|failure|error|rejected|timeout/.test(normalized)) return "异常";
  if (/offline|stale|disconnect/.test(normalized)) return "离线";
  if (/online|connected|live/.test(normalized)) return "在线";
  if (/waiting|idle|new/.test(normalized)) return "等待";
  return text(value, fallback);
}

function presentLinkState(value: unknown, ready = "已关联", waiting = "待回流") {
  return text(value, "") ? ready : waiting;
}

function isRawIdentifier(value: unknown) {
  const raw = text(value, "");
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)
    || /^[0-9a-f]{12,}$/i.test(raw);
}

function publicFocusSeat(value: unknown) {
  const raw = text(value, "");
  if (!raw || isRawIdentifier(raw)) return "负责 NPC";
  return raw;
}

function humanTaskStatus(value: string) {
  const normalized = text(value, "").toLowerCase();
  if (["completed", "done", "resolved"].includes(normalized)) return "已完成";
  if (["blocked", "failed", "error", "rejected"].includes(normalized)) return "已阻塞";
  if (["pending_review", "waiting_review", "review"].includes(normalized)) return "待审核";
  if (["queued", "active", "running", "in_progress", "accepted"].includes(normalized)) return "处理中";
  if (!normalized || normalized === "message_focus") return "消息焦点";
  return text(value, "处理中");
}

function publicEventType(value: unknown) {
  const normalized = text(value, "").toLowerCase();
  if (/runner_command|dispatch/.test(normalized)) return "派单事件";
  if (/receipt|reply|final|closeout/.test(normalized)) return "回执";
  if (/review|approval/.test(normalized)) return "待人工确认";
  if (/desktop|question/.test(normalized)) return "桌面消息";
  if (/requirement|need/.test(normalized)) return "协作需求";
  if (/artifact|evidence/.test(normalized)) return "产出";
  if (/error|exception|failed/.test(normalized)) return "异常";
  if (/progress|ack|running/.test(normalized)) return "进度";
  return text(value, "日志");
}

function publicEventTitle(item: AnyRecord) {
  const raw = text(item.title ?? item.status, "协作事件");
  const cleaned = raw
    .replace(/^Task dispatch:\s*/i, "任务派发：")
    .replace(/^Dispatch:\s*/i, "派单：")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "当前任务")
    .replace(/\b[0-9a-f]{12,}\b/gi, "当前任务");
  return cleaned || "协作事件";
}

function publicEventBody(item: AnyRecord) {
  const raw = text(item.body ?? item.summary ?? item.status, "等待更多内容。");
  const type = text(item.message_type ?? item.type, "").toLowerCase();
  if (/runner_command|dispatch/.test(type)) {
    const status = userStatus(item.status, "已进入队列");
    return `任务已进入执行链路，当前状态：${status}。完整回执、异常和产出记录在观测台查看。`;
  }
  const cleaned = raw
    .replace(/\b(Task dispatch|Dispatch ID|Task ID|Message ID|Runner ID|source_message_id|source_thread|canonical|requested id|session JSONL|local path|adapter|bridge)\b/gi, "链路记录")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "当前任务")
    .replace(/\b[0-9a-f]{12,}\b/gi, "当前任务");
  return cleaned.length > 180 ? `${cleaned.slice(0, 180)}...` : cleaned;
}

function firstContextValue(values: unknown[], fallback = "") {
  for (const value of values) {
    const next = text(value, "");
    if (next) return next;
  }
  return fallback;
}

function consoleTone(value: unknown): ConsoleTone {
  const normalized = text(value, "").toLowerCase();
  if (/failed|failure|error|blocked|rejected/.test(normalized)) return "error";
  if (/warning|warn|risk|stale|timeout|unconfirmed/.test(normalized)) return "warning";
  if (/review|approval|human/.test(normalized)) return "review";
  if (/npc|agent|assistant|workstation/.test(normalized)) return "npc";
  if (/completed|success|done|ok|ready|passed/.test(normalized)) return "success";
  return "info";
}

export function ProfessionalWorkbenchShell({
  projectId,
  pageKey,
  pageTitle,
  pageSummary,
  projectName,
  topLinks,
  sectionLinks,
  taskView,
  focusTitle,
  focusSeat,
  taskActions,
  capabilityCards,
  signalCards,
  children,
}: {
  projectId: string;
  pageKey: "datasets" | "ai-lab" | "robotics";
  pageTitle: string;
  pageSummary: string;
  projectName: string;
  topLinks: QuickLink[];
  sectionLinks: QuickLink[];
  taskView: AnyRecord | null;
  focusTitle: string;
  focusSeat: string;
  taskActions: ActionLink[];
  capabilityCards: CapabilityCard[];
  signalCards: SignalCard[];
  children: ReactNode;
}) {
  const taskException = exceptionSummary(taskView);
  const artifacts = taskArtifacts(taskView, projectId, pageKey);
  const safeFocusSeat = publicFocusSeat(focusSeat);
  const primaryTaskActions = taskActions.slice(0, 3);
  const primarySignals = signalCards.slice(0, 3);
  const primaryCapabilities = capabilityCards.slice(0, 4);
  const primarySectionLinks = sectionLinks.slice(0, 8);
  const recentMessages = Array.isArray(taskView?.messages) ? (taskView.messages as AnyRecord[]).slice(0, 3) : [];
  const recentReceipts = Array.isArray(taskView?.receipts) ? (taskView.receipts as AnyRecord[]).slice(0, 3) : [];
  const hasActionableException = Boolean(taskException.actionable);
  const taskTitle = taskView ? text(taskView.task?.title, focusTitle) : focusTitle;
  const taskStatus = taskView ? userStatus(taskView.summary?.task_status, "消息焦点") : "消息焦点";
  const latestMessage = Array.isArray(taskView?.messages) ? (taskView.messages as AnyRecord[])[0] : null;
  const latestReceipt = Array.isArray(taskView?.receipts) ? (taskView.receipts as AnyRecord[])[0] : null;
  const latestDispatch = Array.isArray(taskView?.dispatches) ? (taskView.dispatches as AnyRecord[])[0] : null;
  const capabilitySummary = Array.isArray(taskView?.capability_summary) ? (taskView.capability_summary as AnyRecord[]) : [];
  const capabilityLabels = capabilitySummary.flatMap((item) => Array.isArray(item?.capability_labels) ? item.capability_labels as string[] : []).filter(Boolean);
  const currentDispatchId = firstContextValue([
    latestMessage?.dispatch_id,
    latestReceipt?.dispatch_id,
    latestDispatch?.id,
  ]);
  const currentSourceMessageId = firstContextValue([
    latestReceipt?.source_message_id,
    artifacts[0]?.href?.includes("message_id=") ? new URLSearchParams(artifacts[0].href.split("?")[1] || "").get("message_id") : "",
    latestMessage?.id,
  ]);
  const currentRunnerId = firstContextValue([
    capabilitySummary[0]?.runner_id,
    latestDispatch?.runner_id,
  ]);
  const pendingCloseoutCount = Number(taskView?.summary?.pending_closeout_count ?? 0);
  const evidenceStatus = text(taskView?.summary?.evidence_chain_status, artifacts.length ? "indexed" : "waiting");
  const activeTool = primarySectionLinks.find((link) => link.active) ?? primarySectionLinks[0] ?? null;
  const leftContext = [
    ["任务", taskView ? "已选择" : "当前焦点"],
    ["派单", presentLinkState(currentDispatchId, "已进入队列", "待生成")],
    ["消息", presentLinkState(currentSourceMessageId, "已回流", "待回流")],
    ["执行电脑", presentLinkState(currentRunnerId, "已分配", "待分配")],
  ];

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <nav className={styles.topbarNav}>
          {topLinks.map((link) => (
            <Link key={link.label} href={link.href} className={styles.navLink} data-active={link.active ? "1" : undefined}>
              {link.label}
            </Link>
          ))}
        </nav>
        <div className={styles.topbarMeta}>
          <span className={styles.metaChip}>项目 {projectName}</span>
          <span className={styles.metaChip}>工作台 {pageTitle}</span>
          <span className={styles.metaChip}>状态 {taskStatus}</span>
        </div>
      </header>

      <section className={styles.body}>
        <aside className={styles.leftRail} aria-label="主角和 NPC 索引">
          <div className={styles.actorStack}>
            <article className={styles.actorCard} data-kind="hero">
              <span>主角</span>
              <strong>项目负责人</strong>
              <small>{projectName}</small>
            </article>
            <article className={styles.actorCard} data-kind="npc">
              <span>负责 NPC</span>
              <strong>{safeFocusSeat}</strong>
              <small>{activeTool ? `当前工具：${activeTool.label}` : pageTitle}</small>
            </article>
          </div>

          <div className={styles.npcIndexPanel}>
            <span>NPC 索引</span>
            <Link href={`/projects/${projectId}?tab=npc-create&return_to=${encodeURIComponent(`/projects/${projectId}/${pageKey}`)}`}>
              添加 / 管理 NPC
            </Link>
            <Link href={`/projects/${projectId}/workbench?from=${pageKey}`}>
              查看 NPC 工作台
            </Link>
          </div>

          <div className={styles.leftContextPanel}>
            <span>当前上下文</span>
            {leftContext.map(([label, value]) => (
              <article key={label}>
                <small>{label}</small>
                <strong>{value}</strong>
              </article>
            ))}
            <article>
              <small>协作记录</small>
              <strong>{taskView ? "已聚焦" : "等待任务"}</strong>
            </article>
            <article>
              <small>执行通道</small>
              <strong>{currentRunnerId ? "可追踪" : "待确认"}</strong>
            </article>
          </div>
        </aside>

        <section className={styles.content}>
          <section className={styles.debugToolbar} aria-label="工作区参数">
            <span>{activeTool ? activeTool.label : "总览"}</span>
            <small>{taskTitle}</small>
            <small>产出 {userStatus(evidenceStatus, "等待")}</small>
            <small>执行电脑 {currentRunnerId ? "已分配" : "待分配"}</small>
            <small>协作记录 {taskView ? "已聚焦" : "等待"}</small>
            <small>执行通道 {currentRunnerId ? "可追踪" : "待确认"}</small>
            <small>{pendingCloseoutCount > 0 ? "结果待回流优先" : hasActionableException ? "异常优先" : "可继续"}</small>
            <small>权限 只读 / 人审写入</small>
          </section>
          <section className={styles.workbenchCanvas} aria-label="专业工作区">
            {children}
          </section>
        </section>

        <aside className={styles.rightRail} aria-label="功能按钮和属性抽屉">
          <section className={styles.toolLauncher} aria-label="功能按钮">
            <span>功能</span>
            <Link href={`/projects/${projectId}/observability?from=${pageKey}${taskView?.task?.id ? `&task_id=${encodeURIComponent(text(taskView.task.id, ""))}` : ""}`}>
              <strong>当前记录</strong>
              <small>派单 / 回执 / 产出索引</small>
            </Link>
            <Link href={`/projects/${projectId}/observability?from=${pageKey}`}>
              <strong>执行通道</strong>
              <small>在线 / 队列 / 最近心跳</small>
            </Link>
            {primarySectionLinks.map((link) => (
              link.href.startsWith("#") ? (
                <a key={link.label} href={link.href} data-active={link.active ? "1" : undefined}>
                  <strong>{link.label}</strong>
                  {link.detail ? <small>{link.detail}</small> : null}
                </a>
              ) : (
                <Link key={link.label} href={link.href} data-active={link.active ? "1" : undefined}>
                  <strong>{link.label}</strong>
                  {link.detail ? <small>{link.detail}</small> : null}
                </Link>
              )
            ))}
          </section>

          <details className={styles.drawer} open>
            <summary>
              <span>属性</span>
              <strong>现在先看</strong>
            </summary>
            <div className={styles.drawerBody}>
              {primarySignals.map((card) => (
                card.href ? (
                  <Link key={card.label} href={card.href} className={styles.drawerItem}>
                    <span>{card.label}</span>
                    <strong>{card.value}</strong>
                    <p>{card.detail}</p>
                    <small>{card.actionLabel || "查看"}</small>
                  </Link>
                ) : (
                  <article key={card.label} className={styles.drawerItem}>
                    <span>{card.label}</span>
                    <strong>{card.value}</strong>
                    <p>{card.detail}</p>
                  </article>
                )
              ))}
            </div>
          </details>

          <details className={styles.drawer}>
            <summary>
              <span>产出</span>
              <strong>{artifacts.length ? `${artifacts.length} 条` : "等待回流"}</strong>
            </summary>
            <div className={styles.drawerBody}>
              {artifacts.length ? artifacts.map((artifact) => (
                artifact.href ? (
                  <Link key={artifact.path} href={artifact.href} className={styles.drawerItem}>
                    <span>{artifact.label}</span>
                    <strong>{artifactTitle(artifact.path)}</strong>
                    <p>{artifact.detail || artifactDetail(artifact.path)}</p>
                    <small>{artifact.actionLabel || "查看记录"}</small>
                  </Link>
                ) : (
                  <article key={artifact.path} className={styles.drawerItem}>
                    <span>{artifact.label}</span>
                    <strong>{artifactTitle(artifact.path)}</strong>
                    <p>{artifact.detail || artifactDetail(artifact.path)}</p>
                  </article>
                )
              )) : <p className={styles.emptyText}>当前任务还没有产出索引，先从 NPC 工作台发起派单或等待已收到提醒回流。</p>}
            </div>
          </details>

          <details className={styles.drawer}>
            <summary>
              <span>执行通道</span>
              <strong>{currentRunnerId ? "已分配" : "待确认"}</strong>
            </summary>
            <div className={styles.drawerBody}>
              <article className={styles.drawerItem}>
                <span>执行通道</span>
                <strong>{currentRunnerId ? "当前任务已有执行通道" : "等待可投递电脑"}</strong>
                <p>这里只展示是否可追踪和可投递，具体线程绑定仍在主页面或 NPC 管理里选择。</p>
              </article>
              <Link href={`/projects/${projectId}/observability?from=${pageKey}`} className={styles.drawerItem}>
                <span>记录索引</span>
                <strong>查看观测台</strong>
                <p>回执、异常入口、结果回流和执行电脑状态都在同一条记录里查看。</p>
                <small>查看观测台</small>
              </Link>
            </div>
          </details>

          <details className={styles.drawer}>
            <summary>
              <span>能力</span>
              <strong>{primaryCapabilities.length || "待配置"}</strong>
            </summary>
            <div className={styles.drawerBody}>
              {primaryCapabilities.map((card) => (
                card.href ? (
                  <Link key={card.label} href={card.href} className={styles.drawerItem}>
                    <span>{card.label}</span>
                    <strong>{card.detail}</strong>
                  </Link>
                ) : (
                  <article key={card.label} className={styles.drawerItem}>
                    <span>{card.label}</span>
                    <strong>{card.detail}</strong>
                  </article>
                )
              ))}
            </div>
          </details>
        </aside>
      </section>

      <section className={styles.bottomDock} aria-label="事件日志">
        <div className={styles.logHeader}>
          <span>事件日志</span>
          <strong>{recentReceipts.length + recentMessages.length ? `${recentReceipts.length + recentMessages.length} 条` : "等待事件"}</strong>
        </div>
        <div className={styles.dockRows}>
          {[...recentReceipts, ...recentMessages].length ? [...recentReceipts, ...recentMessages].slice(0, 6).map((item, index) => (
            <article key={text(item.id ?? item.message_id, `log-${index}`)} data-tone={consoleTone(item.status ?? item.message_type)}>
              <span>{publicEventType(item.message_type ?? item.type)}</span>
              <strong>{publicEventTitle(item)}</strong>
              <p>{publicEventBody(item)}</p>
            </article>
          )) : <p className={styles.emptyText}>还没有事件进入当前任务。先在中央工作区确认下一步，再让 NPC 或执行电脑继续。</p>}
        </div>
      </section>
    </main>
  );
}

export const ProfessionalEvidenceShell = ProfessionalWorkbenchShell;
