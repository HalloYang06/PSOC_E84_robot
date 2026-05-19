import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCollaborationMessagesState,
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectState,
  getProjectThreadWorkstationsState,
} from "../../../../lib/server-data";
import { isNpcSeatRecord } from "../../../../lib/platform-provider";
import { runnerStateLabel, summarizeRunnerDispatchState } from "../../../../lib/runner-status";
import { RoboticsWorkbenchClient } from "./robotics-workbench-client";
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

function publicInterfaceName(value: unknown, fallback: string) {
  const name = text(value, fallback);
  return name
    .replace(/\badapters?\b/gi, "适配器")
    .replace(/\bbridges?\b/gi, "桥接器")
    .replace(/\brunners?\b/gi, "接单进程");
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

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? value as AnyRecord : {};
}

function seatId(seat: AnyRecord, fallback: string) {
  return text(seat.id ?? seat.config_id ?? seat.configId ?? seat.row_id ?? seat.name, fallback);
}

function seatName(seat: AnyRecord, fallback: string) {
  return text(seat.name ?? seat.label ?? seat.display_name, fallback);
}

type DebugWindow = {
  id: string;
  runnerInterfaceId: string;
  name: string;
  kind: string;
  kindLabel: string;
  statusLabel: string;
  computerLabel: string;
  computerState: string;
  runnerTone: string;
  computerNodeId: string;
  runnerReady: boolean;
  runnerCanDispatch: boolean;
  runnerCanQueue: boolean;
  runnerHint: string;
  transport: string;
  boundNpc: string;
  readCapability: boolean;
  writeCapabilityLabel: string;
  isUsable: boolean;
};

type SavedDebugWindow = {
  resourceId: string;
  name: string;
  type: string;
  baudRate: string;
  sampleHz: string;
  channels: string;
  boundNpc: string;
};

function normalizeSavedDebugWindows(value: unknown): SavedDebugWindow[] {
  return asArray<AnyRecord>(value)
    .map((item) => ({
      resourceId: text(item.resourceId ?? item.resource_id ?? item.interface_id, ""),
      name: text(item.name ?? item.label, ""),
      type: text(item.type ?? item.kind, "serial"),
      baudRate: text(item.baudRate ?? item.baud_rate, "115200"),
      sampleHz: text(item.sampleHz ?? item.sample_hz, "100"),
      channels: text(item.channels, "time,signal.value,status.code,event.count"),
      boundNpc: text(item.boundNpc ?? item.bound_npc ?? item.bound_npc_id, ""),
    }))
    .filter((item) => item.resourceId);
}

function buildDebugWindows(computers: AnyRecord[], seats: AnyRecord[]): DebugWindow[] {
  const seatNames = seats.map((seat) => seatName(seat, "")).filter(Boolean);
  const windows: DebugWindow[] = [];
  computers.forEach((node, nodeIndex) => {
    const computerLabel = publicComputerName(node, nodeIndex);
    const runnerState = summarizeRunnerDispatchState(node);
    const computerState = runnerState.state;
    const computerNodeId = text(node.id ?? node.config_id ?? node.configId, "");
    scanInterfaces(node).forEach((item, itemIndex) => {
      const kind = text(item.kind, "unknown").toLowerCase();
      const label = kindLabel(kind);
      const rawName = publicInterfaceName(item.name, `${label} ${itemIndex + 1}`);
      const status = text(item.status, "").toLowerCase();
      const writeCapability = text(item.write_capability ?? item.writeCapability, "review_required").toLowerCase();
      const scannedInterfaceId = text(item.id, `${nodeIndex}-${itemIndex}`);
      windows.push({
        id: `${computerNodeId || nodeIndex}:${scannedInterfaceId}`,
        runnerInterfaceId: scannedInterfaceId,
        name: `${label} · ${rawName}`,
        kind,
        kindLabel: label,
        statusLabel: statusLabel(item.status),
        computerLabel,
        computerState,
        runnerTone: runnerState.tone,
        computerNodeId,
        runnerReady: runnerState.canQueue && Boolean(computerNodeId),
        runnerCanDispatch: runnerState.canDispatch && Boolean(computerNodeId),
        runnerCanQueue: runnerState.canQueue && Boolean(computerNodeId),
        runnerHint: runnerState.detail,
        transport: text(item.transport, "只读"),
        boundNpc: seatNames[itemIndex % Math.max(1, seatNames.length)] ?? "",
        readCapability: item.read_capability !== false && item.readCapability !== false,
        writeCapabilityLabel: writeCapability === "direct"
          ? "可写"
          : writeCapability === "blocked"
            ? "禁止"
            : "需审核",
        isUsable: Boolean(computerNodeId) && !["scan_tool_needed", "offline"].includes(status),
      });
    });
  });
  return windows;
}

function selectedWindowIds(searchValue: unknown, windows: DebugWindow[]) {
  const raw = text(searchValue, "");
  const requested = raw.split(",").map((item) => item.trim()).filter(Boolean);
  const ids = requested.length ? requested : [];
  const known = new Set(windows.map((item) => item.id));
  return ids.filter((id) => known.has(id));
}

export default async function ProjectRoboticsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { windows?: string; npc?: string; settings?: string; tab?: string; team_notice?: string; team_error?: string };
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
  const npcSeats = seats.filter((seat) => isNpcSeatRecord(seat));
  const terminalMessages = asArray<AnyRecord>(messagesState.data);
  const windows = buildDebugWindows(computers, npcSeats);
  const config = record(project.collaboration_config);
  const savedWindows = normalizeSavedDebugWindows(config.robotics_debug_windows);
  const onlineComputers = computers.filter((node) => runnerStateLabel(node) === "可投递").length;
  const scanned = computers.filter((node) => scanInterfaces(node).length > 0).length;
  const notice = text(searchParams?.team_notice, "");
  const error = text(searchParams?.team_error, "");
  const initialOpenIds = selectedWindowIds(searchParams?.windows, windows);
  const initialNpcId = text(searchParams?.npc, "");

  return (
    <RoboticsWorkbenchClient
      projectId={projectId}
      projectName={text(project.name, "项目")}
      windows={windows}
      initialSavedWindows={savedWindows}
      npcSeats={npcSeats}
      terminalMessages={terminalMessages}
      initialOpenIds={initialOpenIds}
      initialNpcId={initialNpcId}
      onlineComputers={onlineComputers}
      computerCount={computers.length}
      scannedCount={scanned}
      notice={notice}
      error={error}
    />
  );
}
