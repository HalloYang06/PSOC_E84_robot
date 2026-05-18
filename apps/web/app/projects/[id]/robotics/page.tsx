import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectState,
  getProjectThreadWorkstationsState,
} from "../../../../lib/server-data";
import { runnerStateLabel } from "../../../../lib/runner-status";
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
    case "template": return "模板";
    case "offline": return "离线";
    default: return "待确认";
  }
}

function terminalLines(tile: DebugWindow) {
  const lines = [
    `$ open ${tile.name}`,
    `interface=${tile.kindLabel}  computer=${tile.computerLabel}`,
    `state=${tile.statusLabel}  mode=read-only`,
    `npc=${tile.boundNpc || "未绑定，点击右侧选择 NPC"}`,
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

type DebugWindow = {
  id: string;
  name: string;
  kind: string;
  kindLabel: string;
  statusLabel: string;
  computerLabel: string;
  computerState: string;
  transport: string;
  boundNpc: string;
};

function buildDebugWindows(computers: AnyRecord[], seats: AnyRecord[]): DebugWindow[] {
  const seatNames = seats.map((seat) => text(seat.name ?? seat.label, "")).filter(Boolean);
  const windows: DebugWindow[] = [];
  computers.forEach((node, nodeIndex) => {
    const computerLabel = publicComputerName(node, nodeIndex);
    const computerState = runnerStateLabel(node);
    scanInterfaces(node).forEach((item, itemIndex) => {
      const kind = text(item.kind, "unknown").toLowerCase();
      const label = kindLabel(kind);
      const rawName = text(item.name, `${label} ${itemIndex + 1}`);
      windows.push({
        id: text(item.id, `${nodeIndex}-${itemIndex}`),
        name: `${label} · ${rawName}`,
        kind,
        kindLabel: label,
        statusLabel: statusLabel(item.status),
        computerLabel,
        computerState,
        transport: text(item.transport, "只读"),
        boundNpc: seatNames[itemIndex % Math.max(1, seatNames.length)] ?? "",
      });
    });
  });
  if (windows.length) return windows;
  return [
    {
      id: "terminal-socketcan",
      name: "CAN 调试 · can0",
      kind: "can",
      kindLabel: "CAN",
      statusLabel: "等待扫描",
      computerLabel: "等待 Linux runner",
      computerState: "等待电脑恢复",
      transport: "SocketCAN",
      boundNpc: seatNames[0] ?? "",
    },
    {
      id: "terminal-spi-can",
      name: "SPI-CAN 调试 · MCP251x",
      kind: "spi-can",
      kindLabel: "SPI-CAN",
      statusLabel: "等待扫描",
      computerLabel: "等待 Linux runner",
      computerState: "等待电脑恢复",
      transport: "SPI 转 CAN",
      boundNpc: seatNames[1] ?? "",
    },
    {
      id: "terminal-serial",
      name: "串口调试 · ttyUSB0",
      kind: "serial",
      kindLabel: "串口",
      statusLabel: "等待扫描",
      computerLabel: "等待 runner",
      computerState: "等待电脑恢复",
      transport: "TTY/COM",
      boundNpc: seatNames[2] ?? "",
    },
  ];
}

function selectedWindowIds(searchValue: unknown, windows: DebugWindow[]) {
  const raw = text(searchValue, "");
  const requested = raw.split(",").map((item) => item.trim()).filter(Boolean);
  const ids = requested.length ? requested : windows.slice(0, Math.min(2, windows.length)).map((item) => item.id);
  const known = new Set(windows.map((item) => item.id));
  return ids.filter((id) => known.has(id));
}

function withOpenWindow(projectId: string, currentIds: string[], id: string) {
  const next = currentIds.includes(id) ? currentIds.filter((item) => item !== id) : [...currentIds, id];
  const query = next.length ? `?windows=${encodeURIComponent(next.join(","))}` : "";
  return `/projects/${projectId}/robotics${query}`;
}

export default async function ProjectRoboticsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { windows?: string };
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
  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(seatsState.data);
  const windows = buildDebugWindows(computers, seats);
  const openIds = selectedWindowIds(searchParams?.windows, windows);
  const openWindows = openIds.map((id) => windows.find((item) => item.id === id)).filter(Boolean) as DebugWindow[];
  const onlineComputers = computers.filter((node) => runnerStateLabel(node) === "可投递").length;
  const scanned = computers.filter((node) => scanInterfaces(node).length > 0).length;

  return (
    <main className={styles.debugShell}>
      <header className={styles.debugTopbar}>
        <div className={styles.topbarLeft}>
          <Link className={styles.backLink} href={`/projects/${projectId}`}>返回项目</Link>
          <div className={styles.title}>
            <strong>机器人现场</strong>
            <small>{text(project.name, "项目")} · 调试窗口像 NPC 对话框一样打开</small>
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
            <strong>调试窗口</strong>
            <p>左栏就是你创建过的串口、CAN、USB、SPI-CAN、ROS 调试窗口。</p>
            <Link className={styles.batchBtn} href={`/projects/${projectId}?panel=computers`}>接入/检查电脑</Link>
          </div>
          <ul className={styles.npcList}>
            <li className={styles.groupHeader}><span>已创建</span><strong>{windows.length}</strong></li>
            {windows.map((window) => {
              const isOpen = openIds.includes(window.id);
              return (
                <li key={window.id} className={`${styles.npcRow} ${isOpen ? styles.npcRowOpen : ""}`}>
                  <span className={window.statusLabel === "可读取" ? styles.dotOnline : styles.dot} />
                  <div className={styles.npcMain}>
                    <span className={styles.npcName}>{window.name}</span>
                    <span className={styles.npcMeta}>{window.computerLabel} · {window.statusLabel}</span>
                  </div>
                  <Link className={styles.openBtn} href={withOpenWindow(projectId, openIds, window.id)} aria-label={`打开 ${window.name}`}>+</Link>
                </li>
              );
            })}
          </ul>
        </aside>

        <section className={styles.debugMain} data-mode="chat">
          {openWindows.length ? (
            <div className={styles.tileGrid} data-tile-count={String(openWindows.length)}>
              {openWindows.map((window) => (
                <article key={window.id} className={styles.debugTilePanel}>
                  <header className={styles.tileHead}>
                    <div>
                      <input aria-label="调试窗口名称" defaultValue={window.name} />
                      <small>{window.kindLabel} · {window.transport} · {window.computerState}</small>
                    </div>
                    <Link href={withOpenWindow(projectId, openIds, window.id)} aria-label={`关闭 ${window.name}`}>×</Link>
                  </header>
                  <div className={styles.threadBinding}>
                    <span className={styles.threadChip}>{window.statusLabel}</span>
                    <span className={styles.threadChip}>绑定 NPC：{window.boundNpc || "未绑定"}</span>
                    <Link className={styles.threadChip} href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(`/projects/${projectId}/robotics`)}`}>选择 NPC</Link>
                    <Link className={styles.threadChip} href={`/projects/${projectId}/datasets?return_to=${encodeURIComponent(`/projects/${projectId}/robotics`)}`}>采样入库</Link>
                  </div>
                  <section className={styles.terminalPane} aria-label={`${window.name} 终端`}>
                    {terminalLines(window).map((line) => <code key={line}>{line}</code>)}
                    <code className={styles.terminalCursor}>$ _</code>
                  </section>
                  <footer className={styles.composer}>
                    <textarea className={styles.composerInput} placeholder="输入只读采样计划、过滤条件或请绑定 NPC 分析；写入动作会转成待审申请。" />
                    <div className={styles.composerFoot}>
                      <span className={styles.composerHint}>只读调试窗口 · 写帧/写串口/ROS 写/固件/真实运动都必须人审</span>
                      <button type="button">发送给 NPC</button>
                    </div>
                  </footer>
                </article>
              ))}
            </div>
          ) : (
            <div className={styles.placeholder}>
              <strong>从左栏点 + 打开调试窗口</strong>
              <p>每个窗口都会像 NPC 对话框一样成为一个独立瓷砖。你可以给串口/CAN/USB/SPI-CAN/ROS 窗口命名、绑定 NPC，并把输出入数据工场。</p>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
