import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectKnowledgeDocumentsState,
  getProjectSkillsState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
  getTaskProfessionalViewState,
} from "../../../../lib/server-data";
import { runnerStateLabel } from "../../../../lib/runner-status";
import { ProfessionalWorkbenchShell } from "../_components/professional-evidence-shell";
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

function publicFocusSeat(value: unknown, fallback = "负责 NPC") {
  const raw = text(value, "");
  if (!raw || isRawIdentifier(raw)) return fallback;
  return raw;
}

function safeProjectReturnPath(projectId: string, value: unknown) {
  const raw = text(value, "");
  if (!raw.startsWith(`/projects/${projectId}/`)) return "";
  if (/^\/\//.test(raw) || raw.includes("\\") || raw.includes("://")) return "";
  return raw;
}

function labelProjectReturnPath(value: string) {
  if (value.includes("/workbench")) return "返回 NPC 工作台";
  if (value.includes("/datasets")) return "返回数据工场";
  if (value.includes("/ai-lab")) return "返回 AI 实验室";
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/robotics")) return "返回机器人现场";
  if (value.includes("/observability")) return "返回观测台";
  if (value.includes("/skill-forge")) return "返回能力工坊";
  return "返回来源";
}

function exceptionSummary(view: AnyRecord | null): AnyRecord {
  const summary = view?.summary?.exception_summary;
  return summary && typeof summary === "object" ? summary as AnyRecord : {};
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

function interfaceKindLabel(kind: string) {
  switch (kind) {
    case "serial": return "串口";
    case "can": return "CAN";
    case "usb": return "USB";
    case "spi": return "SPI";
    case "spi-can": return "SPI-CAN";
    case "ros": return "ROS 只读";
    default: return "接口";
  }
}

function interfaceStatusLabel(status: unknown) {
  switch (text(status, "unknown").toLowerCase()) {
    case "available": return "可读取";
    case "occupied": return "占用中";
    case "permission_needed": return "需要权限";
    case "misconfigured": return "需配置";
    case "offline": return "离线";
    case "scan_tool_needed": return "需补扫描工具";
    default: return "待确认";
  }
}

function configHints(item: AnyRecord) {
  const kind = text(item.kind, "unknown").toLowerCase();
  if (kind === "serial") return ["波特率 115200/921600", "校验位 None", "停止位 1", "只读日志"];
  if (kind === "can") return ["SocketCAN", "bitrate 500k/1M", "ID 过滤器", "采样频率"];
  if (kind === "spi" || kind === "spi-can") return ["MCP251x / SPI-CAN", "SPI clock", "IRQ GPIO", "目标 CAN bitrate"];
  if (kind === "usb") return ["VID/PID", "驱动状态", "权限检查", "只读枚举"];
  if (kind === "ros") return ["topic 白名单", "采样频率", "TF 检查", "不 publish"];
  return ["读取方式", "采样窗口", "过滤规则", "安全边界"];
}

function detailLabel(key: string) {
  const labels: Record<string, string> = {
    hint: "提示",
    transport: "通道",
    vendor: "厂商",
    product: "产品",
    driver_hint: "驱动线索",
    topic_count: "Topic 数",
    bitrate: "比特率",
    operstate: "链路状态",
    mtu: "MTU",
  };
  return labels[key] ?? key.replace(/_/g, " ");
}

function publicDetailEntries(details: AnyRecord) {
  const hidden = new Set(["path", "cwd", "sysfs_name", "ip_details", "udev", "DEVLINKS"]);
  return Object.entries(details)
    .filter(([key]) => !hidden.has(key))
    .slice(0, 6)
    .map(([key, value]) => [detailLabel(key), text(typeof value === "object" ? JSON.stringify(value) : value, "-")]);
}

function buildInterfaceTiles(computers: AnyRecord[]) {
  const tiles: Array<AnyRecord & { computerLabel: string; computerState: string }> = [];
  computers.forEach((node, index) => {
    const computerLabel = publicComputerName(node, index);
    const computerState = runnerStateLabel(node);
    scanInterfaces(node).forEach((item, itemIndex) => {
      tiles.push({
        ...item,
        id: text(item.id, `${computerLabel}-${itemIndex + 1}`),
        name: text(item.name, `接口 ${itemIndex + 1}`),
        kind: text(item.kind, "unknown").toLowerCase(),
        status: text(item.status, "unknown"),
        computerLabel,
        computerState,
      });
    });
  });
  return tiles;
}

const templateTiles = [
  {
    id: "template-socketcan",
    kind: "can",
    name: "SocketCAN 模板",
    status: "template",
    computerLabel: "等待 runner 扫描",
    computerState: "等待电脑恢复",
    transport: "socketcan",
    read_capability: true,
    write_capability: "review_required",
    details: { hint: "Linux can0 / can1 扫描后会替换这里。" },
  },
  {
    id: "template-spi-can",
    kind: "spi-can",
    name: "SPI-CAN 模板",
    status: "template",
    computerLabel: "等待 runner 扫描",
    computerState: "等待电脑恢复",
    transport: "socketcan-via-spi",
    read_capability: true,
    write_capability: "review_required",
    details: { hint: "适合 NanoPi + MCP251x 这类 SPI 转 CAN 板，只显示配置建议，不直接改内核或发帧。" },
  },
  {
    id: "template-serial",
    kind: "serial",
    name: "串口模板",
    status: "template",
    computerLabel: "等待 runner 扫描",
    computerState: "等待电脑恢复",
    transport: "tty/com",
    read_capability: true,
    write_capability: "review_required",
    details: { hint: "ttyUSB/ttyACM/COM 扫描后可开多个调试窗。" },
  },
  {
    id: "template-ros",
    kind: "ros",
    name: "ROS 只读模板",
    status: "template",
    computerLabel: "等待 runner 扫描",
    computerState: "等待电脑恢复",
    transport: "ros-readonly",
    read_capability: true,
    write_capability: "review_required",
    details: { hint: "只读 topic / TF / bag 信息，publish/service/action 必须强审。" },
  },
];

export default async function ProjectRoboticsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { return_to?: string; from?: string; task_id?: string; source_seat?: string; source_label?: string; source_title?: string; tile?: string };
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

  const [
    computersState,
    seatsState,
    workstationsState,
    skillsState,
    documentsState,
    taskProfessionalState,
  ] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
    getProjectSkillsState(projectId),
    getProjectKnowledgeDocumentsState(projectId),
    searchParams?.task_id ? getTaskProfessionalViewState(searchParams.task_id) : Promise.resolve({ data: null, status: 200, error: null }),
  ]);

  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(seatsState.data);
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const skills = asArray<AnyRecord>(skillsState.data);
  const documents = asArray<AnyRecord>(documentsState.data);
  const taskView = taskProfessionalState.data as AnyRecord | null;
  const taskException = exceptionSummary(taskView);
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/robotics`;
  const focusTitle = text(searchParams?.source_title, "机器人现场远程调试");
  const focusSeat = publicFocusSeat(searchParams?.source_label ?? searchParams?.source_seat);
  const onlineComputers = computers.filter((node) => runnerStateLabel(node) === "可投递").length;
  const scannedComputers = computers.filter((node) => scanInterfaces(node).length > 0).length;
  const interfaceTiles = buildInterfaceTiles(computers);
  const visibleTiles = interfaceTiles.length ? interfaceTiles : templateTiles;
  const requestedTileId = text(searchParams?.tile, "");
  const activeTile = visibleTiles.find((item) => text(item.id, "") === requestedTileId) ?? visibleTiles[0];
  const activeDetails = activeTile?.details && typeof activeTile.details === "object" ? activeTile.details as AnyRecord : {};
  const latestScan = computers
    .map((node) => nodeScan(node).scanned_at ?? nodeScan(node).scannedAt)
    .map((value) => text(value, ""))
    .filter(Boolean)
    .sort()
    .at(-1) ?? "";
  const readiness = Math.min(
    100,
    Math.round((onlineComputers ? 30 : 0) + (scannedComputers ? 30 : 0) + (seats.length ? 14 : 0) + (skills.length ? 12 : 0) + (documents.length ? 8 : 0) + (workstations.length ? 6 : 0)),
  );
  const topLinks = [
    { label: "NPC 工作台", href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics` },
    { label: "数据工场", href: `/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics` },
    { label: "AI 实验室", href: `/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=robotics` },
    { label: "机器人现场", href: selfPath, active: true },
    { label: "观测台", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics` },
    ...(returnTo ? [{ label: labelProjectReturnPath(returnTo), href: returnTo }] : []),
  ];
  const navItems = [
    { label: "接口扫描", href: "#scan", detail: "runner 上报串口 / USB / CAN / SPI / ROS" },
    { label: "新建调试瓷砖", href: "#tiles", detail: "点击 + 开多个调试窗口" },
    { label: "采样入库", href: `/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics`, detail: "采样频率、窗口、schema" },
    { label: "NPC 辅助", href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`, detail: "让 NPC 看日志和给建议" },
    { label: "强审动作", href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`, detail: "写入 / 运动 / 固件 / ROS 写" },
    { label: "记录", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`, detail: "扫描、回执、证据链" },
  ];
  const capabilityCards = [
    { label: "远程管理", detail: "开发板第一次接入 runner 后，可在任意电脑登录平台管理。" },
    { label: "通用接口", detail: "串口、USB、SocketCAN、SPI-CAN、ROS 都是扫描到的接口对象。" },
    { label: "NPC 辅助", detail: "NPC 可绑定到调试瓷砖解释日志、建议过滤器和采样计划。" },
    { label: "安全边界", detail: "写帧、写串口、真实运动、固件、ROS 写操作必须强审。" },
  ];
  const signalCards = [
    { label: "远程就绪", value: `${readiness}%`, detail: "由 runner 在线、扫描快照、NPC 与能力配置共同计算。", href: "#scan", actionLabel: "看扫描" },
    { label: "执行电脑", value: `${onlineComputers}/${computers.length}`, detail: "离线时只能排队，不能误导为已执行。", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`, actionLabel: "检查状态" },
    { label: "接口", value: `${interfaceTiles.length}`, detail: latestScan ? `最近扫描 ${latestScan}` : "等待 runner 上报接口清单。", href: "#tiles", actionLabel: "看瓷砖" },
    { label: "异常", value: `${String(taskException.failed ?? 0)}`, detail: taskException.actionable ? "先看异常和日志记录。" : "当前只读链路可继续检查。", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`, actionLabel: "看记录" },
  ];
  const taskActions = [
    { label: "查看观测台", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`, primary: true },
    { label: "回 NPC 工作台", href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics` },
    { label: "采样入数据工场", href: `/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics` },
  ];

  return (
    <ProfessionalWorkbenchShell
      projectId={projectId}
      pageKey="robotics"
      pageTitle="机器人现场"
      pageSummary="远程硬件调试台：runner 扫描到接口，平台开调试瓷砖，危险动作走人审。"
      projectName={text(project.name, "项目")}
      topLinks={topLinks}
      sectionLinks={navItems}
      taskView={taskView}
      focusTitle={focusTitle}
      focusSeat={focusSeat}
      taskActions={taskActions}
      capabilityCards={capabilityCards}
      signalCards={signalCards}
    >
      <section className={styles.hardwareWorkbench} aria-label="远程硬件调试台">
        <section className={styles.hardwareTopbar} id="scan">
          <div>
            <span>远程 runner 扫描</span>
            <strong>{interfaceTiles.length ? "已获得接口快照" : "等待接口扫描"}</strong>
            <p>开发板只需要第一次接入 runner。之后你可以在任意电脑登录平台，查看接口、开调试窗、安排采样和让 NPC 辅助判断。</p>
          </div>
          <div className={styles.hardwareToolbar}>
            <Link href={`/projects/${projectId}?panel=computers`}>接入/检查电脑</Link>
            <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>分配 NPC</Link>
            <Link href={`/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>采样入库</Link>
          </div>
        </section>

        <section className={styles.hardwareIde}>
          <aside className={styles.debugTileRail} id="tiles" aria-label="调试瓷砖">
            <div className={styles.tileRailHead}>
              <span>调试瓷砖</span>
              <Link href="#new-tile" aria-label="新建调试瓷砖">+</Link>
            </div>
            {visibleTiles.map((item) => {
              const href = `${selfPath}?tile=${encodeURIComponent(text(item.id, ""))}`;
              const active = text(activeTile?.id, "") === text(item.id, "");
              return (
                <Link key={text(item.id, item.name)} className={styles.debugTile} data-active={active ? "1" : undefined} href={href}>
                  <span>{interfaceKindLabel(text(item.kind, "unknown"))}</span>
                  <strong>{text(item.name, "未命名接口")}</strong>
                  <small>{text(item.computerLabel, "执行电脑")} · {interfaceStatusLabel(item.status)}</small>
                </Link>
              );
            })}
          </aside>

          <section className={styles.debugStage} aria-label="当前调试窗口">
            <div className={styles.debugStageTop}>
              <div>
                <span>{interfaceKindLabel(text(activeTile?.kind, "unknown"))} 调试窗口</span>
                <strong>{text(activeTile?.name, "选择接口")}</strong>
              </div>
              <div className={styles.debugKnobs}>
                {configHints(activeTile ?? {}).map((hint) => <button key={hint} type="button">{hint}</button>)}
              </div>
            </div>

            <div className={styles.deviceCanvas}>
              <div className={styles.signalTrace} aria-hidden="true">
                {Array.from({ length: 32 }).map((_, index) => <i key={index} style={{ height: `${18 + ((index * 17) % 58)}%` }} />)}
              </div>
              <div className={styles.deviceReadout}>
                <span>{text(activeTile?.transport, "只读接口")}</span>
                <strong>{interfaceStatusLabel(activeTile?.status)}</strong>
                <p>{text(activeDetails.hint, "选择采样频率、过滤规则和窗口后，生成数据采集任务；写入类动作只会生成审核申请。")}</p>
              </div>
            </div>

            <div className={styles.sessionGrid}>
              <article>
                <span>读取</span>
                <strong>{activeTile?.read_capability === false ? "不可读取" : "只读允许"}</strong>
                <p>读取通道由 runner 在目标电脑/开发板执行，平台展示快照和回执。</p>
              </article>
              <article>
                <span>写入</span>
                <strong>必须审核</strong>
                <p>CAN 发送、串口写命令、SPI 配置、ROS publish/service/action 都不会直接执行。</p>
              </article>
              <article>
                <span>采样</span>
                <strong>可入数据工场</strong>
                <p>可按采样频率、窗口、接口过滤器生成数据工场采集计划。</p>
              </article>
            </div>
          </section>

          <aside className={styles.debugInspector} aria-label="属性和动作">
            <section>
              <span>当前接口</span>
              <strong>{text(activeTile?.computerLabel, "等待电脑")}</strong>
              <p>{text(activeTile?.computerState, "等待电脑恢复")} · {text(activeTile?.id, "未选择")}</p>
            </section>
            <section id="new-tile">
              <span>动作</span>
              <Link href="#tiles">+ 打开调试瓷砖</Link>
              <Link href={`/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>创建采样计划</Link>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>请求 NPC 协助</Link>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>申请强审动作</Link>
            </section>
            <section>
              <span>扫描详情</span>
              {publicDetailEntries(activeDetails).map(([key, value]) => (
                <p key={key}><b>{key}</b> {value}</p>
              ))}
              {!Object.keys(activeDetails).length ? <p>暂无接口详情，等待 runner 上报扫描快照。</p> : null}
            </section>
          </aside>
        </section>

        <section className={styles.hardwareLog} aria-label="事件日志">
          <span>事件 / 回执</span>
          <strong>{interfaceTiles.length ? "接口扫描已同步" : "等待 runner 扫描接口"}</strong>
          <p>第一版先打通“远程扫描 → 平台展示 → 开调试瓷砖 → 创建采样/审核入口”。实时帧流和采样回传会接在同一套接口对象上。</p>
        </section>
      </section>
    </ProfessionalWorkbenchShell>
  );
}
