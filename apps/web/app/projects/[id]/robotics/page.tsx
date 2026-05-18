import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCollaborationMessagesState,
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectState,
  getProjectThreadWorkstationsState,
} from "../../../../lib/server-data";
import { runnerStateLabel, summarizeRunnerDispatchState } from "../../../../lib/runner-status";
import { 下发机器人调试命令 } from "../../../actions";
import styles from "./robotics.module.css";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type AnyRecord = Record<string, any>;

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function isRawIdentifier(value: unknown) {
  const raw = text(value, "");
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)
    || /^[0-9a-f]{12,}$/i.test(raw);
}

function publicComputerName(node: AnyRecord, index: number) {
  const name = text(node.label ?? node.name ?? node.display_name, "");
  if (name && !isRawIdentifier(name)) return name;
  return `执行电脑 ${index + 1}`;
}

function nodeScan(node: AnyRecord): AnyRecord {
  const direct = node.device_interface_scan;
  if (direct && typeof direct === "object") return direct as AnyRecord;
  const metadata = node.metadata && typeof node.metadata === "object" ? node.metadata as AnyRecord : {};
  const scan = metadata.device_interface_scan ?? metadata.deviceInterfaceScan;
  return scan && typeof scan === "object" ? scan as AnyRecord : {};
}

function scanInterfaces(node: AnyRecord): AnyRecord[] {
  return asArray<AnyRecord>(nodeScan(node).interfaces);
}

function kindLabel(kind: string) {
  switch (kind) {
    case "serial": return "串口";
    case "can": return "CAN";
    case "usb": return "USB";
    case "spi": return "SPI";
    case "spi-can": return "SPI-CAN";
    case "ros": return "ROS";
    default: return "接口";
  }
}

function statusLabel(status: unknown) {
  switch (text(status, "unknown").toLowerCase()) {
    case "available": return "可读取";
    case "occupied": return "占用中";
    case "permission_needed": return "需权限";
    case "misconfigured": return "需配置";
    case "scan_tool_needed": return "需工具";
    case "offline": return "离线";
    default: return "待确认";
  }
}

function terminalLines(tile: DebugWindow) {
  const lines = [
    `$ open ${tile.name}`,
    `interface=${tile.kindLabel}  computer=${tile.computerLabel}`,
    `state=${tile.statusLabel}  mode=read-only`,
    `npc=${tile.boundNpc || "未绑定，创建或设置时选择 NPC"}`,
  ];
  if (tile.kind === "can") {
    lines.push("filter=none  bitrate=待确认  sample=100Hz");
    lines.push("hint: 接入 SocketCAN 后显示 can0/can1；发送帧必须强审。");
  } else if (tile.kind === "spi-can") {
    lines.push("chip=MCP251x  spi-clock=待确认  irq=待确认");
    lines.push("hint: SPI-CAN 只给配置建议，不直接改 overlay / module。");
  } else if (tile.kind === "serial") {
    lines.push("baud=115200  parity=none  stop=1");
    lines.push("hint: 串口写命令必须走审核，当前只读采集日志。");
  } else if (tile.kind === "usb") {
    lines.push("mode=enumerate  driver=待确认");
    lines.push("hint: 只读枚举设备，权限或驱动问题进入观测台。");
  } else if (tile.kind === "ros") {
    lines.push("topics=readonly  publish=blocked");
    lines.push("hint: ROS publish/service/action 必须强审。");
  } else {
    lines.push("config=等待扫描快照");
  }
  return lines;
}

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? value as AnyRecord : {};
}

function commandText(message: AnyRecord) {
  const extra = record(message.extra_data ?? message.metadata);
  const fromMeta = text(extra.terminal_command, "");
  if (fromMeta) return fromMeta;
  const body = text(message.body, "");
  const match = body.match(/只读命令：(.+)/);
  return match?.[1]?.trim() || body.split("\n").find((line) => line.includes("listen")) || "只读调试命令";
}

function terminalEventLines(tile: DebugWindow, messages: AnyRecord[]) {
  const related = messages
    .filter((message) => {
      const extra = record(message.extra_data ?? message.metadata);
      return text(extra.terminal_interface_id, "") === tile.id
        || text(extra.source_message_id, "") && messages.some((source) => source.id === extra.source_message_id && text(record(source.extra_data ?? source.metadata).terminal_interface_id, "") === tile.id);
    })
    .slice(0, 8)
    .reverse();
  if (!related.length) {
    return ["[terminal] 暂无输入输出。输入只读命令后，会在这里显示 queued / ack / result。"];
  }
  return related.map((message) => {
    const type = text(message.message_type ?? message.messageType, "event");
    const status = text(message.status, "open");
    if (type === "runner_command") return `$ ${commandText(message)}  # ${status}`;
    if (type === "runner_ack") return `[ack] ${text(message.body, "执行电脑已接单")}`;
    if (type === "runner_result") return `[result:${status}] ${text(message.body, "执行电脑已返回结果")}`;
    return `[${type}:${status}] ${text(message.title ?? message.body, "终端事件")}`;
  });
}

type DebugWindow = {
  id: string;
  name: string;
  kind: string;
  kindLabel: string;
  statusLabel: string;
  computerLabel: string;
  computerState: string;
  computerNodeId: string;
  runnerReady: boolean;
  runnerHint: string;
  transport: string;
  boundNpc: string;
  isUsable: boolean;
};

function buildDebugWindows(computers: AnyRecord[], seats: AnyRecord[]): DebugWindow[] {
  const seatNames = seats.map((seat) => text(seat.name ?? seat.label, "")).filter(Boolean);
  const windows: DebugWindow[] = [];
  computers.forEach((node, nodeIndex) => {
    const computerLabel = publicComputerName(node, nodeIndex);
    const runnerState = summarizeRunnerDispatchState(node);
    const computerState = runnerState.state;
    const computerNodeId = text(node.id ?? node.config_id ?? node.configId, "");
    scanInterfaces(node).forEach((item, itemIndex) => {
      const kind = text(item.kind, "unknown").toLowerCase();
      const label = kindLabel(kind);
      const rawName = text(item.name, `${label} ${itemIndex + 1}`);
      const status = text(item.status, "").toLowerCase();
      windows.push({
        id: `${computerNodeId || nodeIndex}:${text(item.id, `${nodeIndex}-${itemIndex}`)}`,
        name: `${label} · ${rawName}`,
        kind,
        kindLabel: label,
        statusLabel: statusLabel(item.status),
        computerLabel,
        computerState,
        computerNodeId,
        runnerReady: runnerState.canQueue && Boolean(computerNodeId),
        runnerHint: runnerState.detail,
        transport: text(item.transport, "只读"),
        boundNpc: seatNames[itemIndex % Math.max(1, seatNames.length)] ?? "",
        isUsable: Boolean(computerNodeId) && !["scan_tool_needed", "offline"].includes(status),
      });
    });
  });
  return windows;
}

function selectedWindowIds(searchValue: unknown, windows: DebugWindow[]) {
  const raw = text(searchValue, "");
  const requested = raw.split(",").map((item) => item.trim()).filter(Boolean);
  const ids = requested.length ? requested : windows.filter((item) => item.isUsable).slice(0, Math.min(2, windows.length)).map((item) => item.id);
  const known = new Set(windows.map((item) => item.id));
  return ids.filter((id) => known.has(id));
}

function roboticsHref(projectId: string, params: Record<string, string>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) query.set(key, value);
  });
  const suffix = query.toString();
  return `/projects/${projectId}/robotics${suffix ? `?${suffix}` : ""}`;
}

function withOpenWindow(projectId: string, currentIds: string[], id: string, npc = "", settings = "") {
  const next = currentIds.includes(id) ? currentIds.filter((item) => item !== id) : [...currentIds, id];
  return roboticsHref(projectId, {
    windows: next.join(","),
    npc,
    settings,
  });
}

function withSettings(projectId: string, currentIds: string[], id: string, npc = "") {
  const next = currentIds.includes(id) ? currentIds : [...currentIds, id];
  return roboticsHref(projectId, {
    windows: next.join(","),
    npc,
    settings: id,
  });
}

export default async function ProjectRoboticsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { windows?: string; npc?: string; settings?: string; team_notice?: string; team_error?: string };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/robotics`)}`);
  }

  const projectState = await getProjectState(projectId);
  const project = projectState.data;
  if (!project) {
    return (
      <main className={styles.emptyPage}>
        <p>项目不存在或无权限。</p>
        <Link href="/projects">返回项目列表</Link>
      </main>
    );
  }

  const [computersState, seatsState] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
  ]);
  const messagesState = await getCollaborationMessagesState({
    projectId,
    limit: 200,
  });
  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(seatsState.data);
  const terminalMessages = asArray<AnyRecord>(messagesState.data);
  const windows = buildDebugWindows(computers, seats);
  const usableWindows = windows.filter((item) => item.isUsable);
  const openIds = selectedWindowIds(searchParams?.windows, windows);
  const openWindows = openIds.map((id) => windows.find((item) => item.id === id)).filter(Boolean) as DebugWindow[];
  const onlineComputers = computers.filter((node) => runnerStateLabel(node) === "可投递").length;
  const scanned = computers.filter((node) => scanInterfaces(node).length > 0).length;
  const notice = text(searchParams?.team_notice, "");
  const error = text(searchParams?.team_error, "");
  const selectedNpc = text(searchParams?.npc, "");
  const settingsWindowId = text(searchParams?.settings, "");

  return (
    <main className={styles.debugShell}>
      <header className={styles.debugTopbar}>
        <div className={styles.topbarLeft}>
          <Link className={styles.backLink} href={`/projects/${projectId}`}>返回项目</Link>
          <div className={styles.title}>
            <strong>机器人现场</strong>
          <small>{text(project.name, "项目")} · 只显示本项目 runner 扫描到的真实接口</small>
          </div>
        </div>
        <div className={styles.topbarRight}>
          <span className={styles.kpi}>执行电脑 {onlineComputers}/{computers.length}</span>
          <span className={styles.kpi}>已扫描 {scanned}</span>
          <span className={styles.kpi}>窗口 {openWindows.length}/{windows.length}</span>
        </div>
      </header>

      <section className={styles.debugBody}>
        <aside className={styles.debugSidebar}>
          <div className={styles.sidebarHeader}>
            <strong>创建调试窗口</strong>
            <p>在当前页选择本项目电脑 runner、真实接口和协助 NPC；没有扫描结果就不创建假窗口。</p>
            <form className={styles.indexForm} action={`/projects/${projectId}/robotics`}>
              <label>
                <span>电脑 runner / 真实接口</span>
                <select name="windows" defaultValue={usableWindows[0]?.id ?? ""}>
                  {usableWindows.length ? usableWindows.map((window) => (
                    <option key={window.id} value={window.id}>{window.computerLabel} · {window.computerState} · {window.name}</option>
                  )) : <option value="">暂无可打开接口</option>}
                </select>
              </label>
              <label>
                <span>默认协助 NPC</span>
                <select name="npc" defaultValue={selectedNpc}>
                  <option value="">暂不绑定</option>
                  {seats.length ? seats.map((seat, index) => {
                    const name = text(seat.name ?? seat.label, `NPC ${index + 1}`);
                    return <option key={text(seat.id ?? seat.config_id ?? name, name)} value={name}>{name}</option>;
                  }) : null}
                </select>
              </label>
              <button type="submit" disabled={!usableWindows.length}>创建并打开终端</button>
            </form>
          </div>
          <ul className={styles.npcList}>
            <li className={styles.groupHeader}><span>真实接口索引</span><strong>{windows.length}</strong></li>
            {windows.map((window) => {
              const isOpen = openIds.includes(window.id);
              return (
                <li key={window.id} className={`${styles.npcRow} ${isOpen ? styles.npcRowOpen : ""}`}>
                  <span className={window.statusLabel === "可读取" ? styles.dotOnline : styles.dot} />
                  <div className={styles.npcMain}>
                    <span className={styles.npcName}>{window.name}</span>
                    <span className={styles.npcMeta}>{window.computerLabel} · {window.statusLabel}</span>
                  </div>
                  {window.isUsable ? (
                    <div className={styles.rowActions}>
                      <Link className={styles.openBtn} href={withOpenWindow(projectId, openIds, window.id, selectedNpc, settingsWindowId)} aria-label={`打开 ${window.name}`}>+</Link>
                      <Link className={styles.settingsBtn} href={withSettings(projectId, openIds, window.id, selectedNpc)} aria-label={`设置 ${window.name}`}>设</Link>
                    </div>
                  ) : (
                    <span className={styles.openBtnDisabled}>!</span>
                  )}
                </li>
              );
            })}
          </ul>
        </aside>

        <section className={styles.debugMain} data-mode="chat">
          {notice ? <div className={styles.inlineNotice} data-tone="success">{notice}</div> : null}
          {error ? <div className={styles.inlineNotice} data-tone="danger">{error}</div> : null}
          {openWindows.length ? (
            <div className={styles.tileGrid} data-tile-count={String(openWindows.length)}>
              {openWindows.map((window) => (
                <article key={window.id} className={styles.debugTilePanel}>
                  <header className={styles.tileHead}>
                    <div>
                      <input aria-label="调试窗口名称" defaultValue={window.name} />
                      <small>{window.kindLabel} · {window.transport} · {window.computerState}</small>
                    </div>
                    <Link href={withOpenWindow(projectId, openIds, window.id, selectedNpc, settingsWindowId === window.id ? "" : settingsWindowId)} aria-label={`关闭 ${window.name}`}>×</Link>
                  </header>
                  <div className={styles.threadBinding}>
                    <span className={styles.threadChip}>{window.statusLabel}</span>
                    <span className={styles.threadChip}>电脑：{window.computerLabel}</span>
                    <span className={styles.threadChip}>接单：{window.computerState}</span>
                    <span className={styles.threadChip}>协助 NPC：{selectedNpc || window.boundNpc || "未绑定"}</span>
                    <Link className={styles.threadChip} href={withSettings(projectId, openIds, window.id, selectedNpc)}>设置</Link>
                  </div>
                  {settingsWindowId === window.id ? (
                    <section className={styles.settingsPanel} aria-label={`${window.name} 设置`}>
                      <strong>窗口设置</strong>
                      <div>
                        <span>电脑 runner</span>
                        <b>{window.computerLabel} · {window.computerState}</b>
                      </div>
                      <div>
                        <span>调试接口</span>
                        <b>{window.name}</b>
                      </div>
                      <div>
                        <span>协助 NPC</span>
                        <b>{selectedNpc || window.boundNpc || "未绑定"}</b>
                      </div>
                      <p>{window.runnerHint}</p>
                    </section>
                  ) : null}
                  <section className={styles.terminalPane} aria-label={`${window.name} 终端`}>
                    {terminalLines(window).map((line) => <code key={line}>{line}</code>)}
                    <code className={styles.terminalDivider}>--- I/O ---</code>
                    {terminalEventLines(window, terminalMessages).map((line, index) => <code key={`${window.id}-event-${index}`}>{line}</code>)}
                    <code className={styles.terminalCursor}>$ _</code>
                  </section>
                  <form action={下发机器人调试命令.bind(null, projectId)} className={styles.terminalCommandBar}>
                    <input type="hidden" name="return_to" value={`/projects/${projectId}/robotics?windows=${encodeURIComponent(openIds.join(","))}`} />
                    <input type="hidden" name="computer_node_id" value={window.computerNodeId} />
                    <input type="hidden" name="interface_id" value={window.id} />
                    <input type="hidden" name="interface_name" value={window.name} />
                    <input type="hidden" name="interface_kind" value={window.kindLabel} />
                    <span>$</span>
                    <input name="command" placeholder="输入只读采样命令或过滤条件，例如 listen --rate 100Hz --window 30s" />
                    <select name="bound_npc" aria-label="绑定 NPC" defaultValue={selectedNpc}>
                      <option value="">不绑定 NPC</option>
                      {seats.map((seat, index) => {
                        const name = text(seat.name ?? seat.label, `NPC ${index + 1}`);
                        return <option key={text(seat.id ?? seat.config_id ?? name, name)} value={name}>{name}</option>;
                      })}
                    </select>
                    <button type="submit" disabled={!window.runnerReady} title={window.runnerReady ? "排队到所选执行电脑" : window.runnerHint}>
                      {window.runnerReady ? "排队执行" : "需重连"}
                    </button>
                  </form>
                </article>
              ))}
            </div>
          ) : (
            <div className={styles.placeholder}>
              <strong>{windows.length ? "没有可打开的真实接口" : "等待本项目电脑扫描接口"}</strong>
              <p>{windows.length ? "当前只有需要工具或权限的扫描项，先在对应电脑补齐扫描能力或权限，再打开调试终端。" : "请先在主页面接入电脑 runner，并执行接口扫描。平台不会创建 demo 调试窗口误导你。"}</p>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
