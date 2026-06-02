import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCollaborationMessagesState,
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectState,
  getProjectThreadWorkstationsState,
} from "../../../../lib/server-data";
import { getApiBaseUrl } from "../../../../lib/config";
import { isNpcSeatRecord } from "../../../../lib/platform-provider";
import { summarizeRunnerDispatchState } from "../../../../lib/runner-status";
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
    .replace(/\badapters?\b/gi, "接入通道")
    .replace(/\bbridges?\b/gi, "同步通道")
    .replace(/\brunners?\b/gi, "接单进程");
}

function publicTransportName(kind: string, value: unknown) {
  const raw = text(value, "").toLowerCase();
  if (raw.includes("win32") && raw.includes("com")) return "Windows 串口";
  if (raw.includes("serial")) return "串口";
  if (raw.includes("socketcan") || raw === "can") return "CAN";
  if (raw.includes("usb")) return "USB";
  if (raw.includes("spi")) return "SPI-CAN";
  if (raw.includes("ros")) return "ROS";
  return `${kindLabel(kind)} 接口`;
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
  heartbeatLabel: string;
  scanLabel: string;
  scannedInterfaceLabel: string;
  reconnectHint: string;
  transport: string;
  boundNpc: string;
  readCapability: boolean;
  writeCapabilityLabel: string;
  isUsable: boolean;
};

type RoboticsRunnerSummary = {
  readyComputers: number;
  queueableComputers: number;
  reconnectComputers: number;
  unknownComputers: number;
  scannedInterfaces: number;
};

function deviceProjectId(device: AnyRecord) {
  const manifest = record(device.manifest);
  const boardManifest = record(device.board_manifest);
  const registration = record(device.registration);
  return text(
    device.project_id
    ?? device.projectId
    ?? manifest.project_id
    ?? manifest.projectId
    ?? boardManifest.project_id
    ?? boardManifest.projectId
    ?? registration.project_id
    ?? registration.projectId,
    "",
  );
}

async function getDeviceQualityDevices(projectId: string): Promise<AnyRecord[]> {
  try {
    const url = new URL("/api/rehab-arm/v1/devices/dashboard", getApiBaseUrl());
    url.searchParams.set("project_id", projectId);
    const response = await fetch(url.toString(), {
      cache: "no-store",
    });
    if (!response.ok) return [];
    const payload = await response.json();
    const data = record(payload).data;
    return asArray<AnyRecord>(record(data).devices).filter((device) => deviceProjectId(device) === projectId);
  } catch {
    return [];
  }
}

function interfaceReadyForWindow(status: string) {
  return status === "available";
}

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

function ageLabelFromSeconds(value: unknown) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  if (seconds < 60) return `${Math.round(seconds)} 秒前`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} 小时前`;
  return `${Math.round(hours / 24)} 天前`;
}

function publicTimeLabel(value: unknown) {
  const raw = text(value, "");
  if (!raw) return "";
  const ms = Date.parse(raw);
  if (!Number.isFinite(ms)) return raw;
  return new Date(ms).toLocaleString("zh-CN", { hour12: false });
}

function scanTimeLabel(scan: AnyRecord) {
  return publicTimeLabel(
    scan.scanned_at
      ?? scan.scannedAt
      ?? scan.updated_at
      ?? scan.updatedAt
      ?? scan.created_at
      ?? scan.createdAt
      ?? scan.ts
      ?? scan.timestamp,
  );
}

function nodeRecoveryFacts(node: AnyRecord, scan: AnyRecord, interfaceCount: number) {
  const metadata = record(node.metadata ?? node.extra_data ?? node.extraData);
  const heartbeatAge = ageLabelFromSeconds(
    node.runner_heartbeat_age_seconds
      ?? node.runnerHeartbeatAgeSeconds
      ?? metadata.runner_heartbeat_age_seconds
      ?? metadata.runnerHeartbeatAgeSeconds,
  );
  const heartbeatAt = publicTimeLabel(
    node.runner_last_heartbeat_at
      ?? node.runnerLastHeartbeatAt
      ?? metadata.runner_last_heartbeat_at
      ?? metadata.runnerLastHeartbeatAt
      ?? node.updated_at
      ?? node.updatedAt,
  );
  const scanAt = scanTimeLabel(scan);
  const reportedCount = Number(scan.interface_count ?? scan.interfaceCount ?? node.device_interface_count ?? node.deviceInterfaceCount);
  const count = Number.isFinite(reportedCount) && reportedCount >= 0 ? reportedCount : interfaceCount;
  return {
    heartbeatLabel: heartbeatAge ? `最近心跳 ${heartbeatAge}` : heartbeatAt ? `最近心跳 ${heartbeatAt}` : "暂无心跳记录",
    scanLabel: scanAt ? `最近扫描 ${scanAt}` : interfaceCount ? "已有接口扫描记录" : "暂无接口扫描记录",
    scannedInterfaceLabel: `${count} 个接口`,
    reconnectHint: "回到主页面检查电脑接入，复制 Windows/Linux 重连命令后保持接单窗口在线。",
  };
}

function buildDebugWindows(computers: AnyRecord[], seats: AnyRecord[]): DebugWindow[] {
  const seatNames = seats.map((seat) => seatName(seat, "")).filter(Boolean);
  const windows: DebugWindow[] = [];
  computers.forEach((node, nodeIndex) => {
    const computerLabel = publicComputerName(node, nodeIndex);
    const runnerState = summarizeRunnerDispatchState(node);
    const computerState = runnerState.state;
    const computerNodeId = text(node.id ?? node.config_id ?? node.configId, "");
    const scan = nodeScan(node);
    const interfaces = scanInterfaces(node);
    const recoveryFacts = nodeRecoveryFacts(node, scan, interfaces.length);
    interfaces.forEach((item, itemIndex) => {
      const kind = text(item.kind, "unknown").toLowerCase();
      const label = kindLabel(kind);
      const rawName = publicInterfaceName(item.name, `${label} ${itemIndex + 1}`);
      const status = text(item.status, "").toLowerCase();
      const writeCapability = text(item.write_capability ?? item.writeCapability, "review_required").toLowerCase();
      const scannedInterfaceId = text(item.id, `${nodeIndex}-${itemIndex}`);
      const runnerReadyForWindow = runnerState.canQueue && Boolean(computerNodeId);
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
        heartbeatLabel: recoveryFacts.heartbeatLabel,
        scanLabel: recoveryFacts.scanLabel,
        scannedInterfaceLabel: recoveryFacts.scannedInterfaceLabel,
        reconnectHint: recoveryFacts.reconnectHint,
        transport: publicTransportName(kind, item.transport),
        boundNpc: seatNames[itemIndex % Math.max(1, seatNames.length)] ?? "",
        readCapability: item.read_capability !== false && item.readCapability !== false,
        writeCapabilityLabel: writeCapability === "direct"
          ? "可写"
          : writeCapability === "blocked"
            ? "禁止"
            : "需确认",
        isUsable: runnerReadyForWindow && interfaceReadyForWindow(status),
      });
    });
  });
  return windows;
}

function summarizeRoboticsRunnerCounts(computers: AnyRecord[]): RoboticsRunnerSummary {
  return computers.reduce<RoboticsRunnerSummary>((summary, node) => {
    const state = summarizeRunnerDispatchState(node);
    if (state.canDispatch) {
      summary.readyComputers += 1;
    } else if (state.canQueue) {
      summary.queueableComputers += 1;
    } else if (state.tone === "offline") {
      summary.reconnectComputers += 1;
    } else {
      summary.unknownComputers += 1;
    }
    summary.scannedInterfaces += scanInterfaces(node).length;
    return summary;
  }, {
    readyComputers: 0,
    queueableComputers: 0,
    reconnectComputers: 0,
    unknownComputers: 0,
    scannedInterfaces: 0,
  });
}

function selectedWindowIds(searchValue: unknown, windows: DebugWindow[]) {
  const raw = text(searchValue, "");
  const requested = raw.split(",").map((item) => item.trim()).filter(Boolean);
  const ids = requested.length ? requested : [];
  const known = new Set(windows.map((item) => item.id));
  return ids.filter((id) => known.has(id));
}

function initialWorkbenchTab(searchValue: unknown) {
  const tab = text(searchValue, "").toLowerCase();
  if (["terminal", "dataset", "chart", "model", "data", "camera"].includes(tab)) return tab;
  return "";
}

function initialDeviceId(searchValue: unknown) {
  const value = text(searchValue, "");
  return isRawIdentifier(value) ? "" : value;
}

export default async function ProjectRoboticsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { windows?: string; npc?: string; settings?: string; tab?: string; device?: string; team_notice?: string; team_error?: string };
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

  const [computersState, seatsState, deviceQualityDevices] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getDeviceQualityDevices(projectId),
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
  const runnerSummary = summarizeRoboticsRunnerCounts(computers);
  const notice = text(searchParams?.team_notice, "");
  const error = text(searchParams?.team_error, "");
  const initialOpenIds = selectedWindowIds(searchParams?.windows, windows);
  const initialNpcId = text(searchParams?.npc, "");
  const initialTab = initialWorkbenchTab(searchParams?.tab);
  const requestedDeviceId = initialDeviceId(searchParams?.device);

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
      initialTab={initialTab}
      initialDeviceId={requestedDeviceId}
      readyComputers={runnerSummary.readyComputers}
      queueableComputers={runnerSummary.queueableComputers}
      reconnectComputers={runnerSummary.reconnectComputers}
      unknownComputers={runnerSummary.unknownComputers}
      computerCount={computers.length}
      scannedInterfaceCount={runnerSummary.scannedInterfaces}
      deviceQualityDevices={deviceQualityDevices}
      notice={notice}
      error={error}
    />
  );
}
