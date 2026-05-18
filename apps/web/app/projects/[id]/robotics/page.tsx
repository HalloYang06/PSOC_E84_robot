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
import { ModelImportInspector } from "./model-import-inspector";
import { RosNodeConnector } from "./ros-node-connector";
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

function statusText(value: unknown) {
  return text(value, "").toLowerCase();
}

function computerDispatchState(node: AnyRecord | undefined) {
  return runnerStateLabel(node);
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

function publicComputerName(node: AnyRecord, index: number) {
  const name = text(node.name ?? node.label ?? node.display_name, "");
  if (name && !isRawIdentifier(name)) return name;
  return `执行电脑 ${index + 1}`;
}

function exceptionSummary(view: AnyRecord | null): AnyRecord {
  const summary = view?.summary?.exception_summary;
  return summary && typeof summary === "object" ? summary as AnyRecord : {};
}

function listText(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => text(item, "")).filter(Boolean);
  const raw = text(value, "");
  if (!raw) return [];
  return raw.split(/[,，;；\n]/).map((item) => item.trim()).filter(Boolean);
}

function nodeCapabilities(node: AnyRecord): string[] {
  const metadata = node.metadata && typeof node.metadata === "object" ? node.metadata as AnyRecord : {};
  return [
    ...listText(node.capabilities),
    ...listText(node.runner_capabilities),
    ...listText(node.device_capabilities),
    ...listText(metadata.capabilities),
    ...listText(metadata.runner_capabilities),
    ...listText(metadata.device_capabilities),
  ].map((item) => item.toLowerCase());
}

function supportsDeviceMode(capabilities: string[], mode: string) {
  const haystack = capabilities.join(" ");
  if (!haystack) return "待确认";
  if (mode === "can") return /can|socketcan|usb-can|canable|总线/.test(haystack) ? "可只读" : "待确认";
  if (mode === "serial") return /serial|uart|tty|com|串口/.test(haystack) ? "可只读" : "待确认";
  if (mode === "usb") return /usb|hid|dap|枚举/.test(haystack) ? "可只读" : "待确认";
  if (mode === "ros") return /ros|topic|bag|tf|joint/.test(haystack) ? "可只读" : "待确认";
  return "待确认";
}

const topicRows = [
  ["/joint_states", "sensor_msgs/JointState", "32 Hz", "只读"],
  ["/tf", "tf2_msgs/TFMessage", "60 Hz", "只读"],
  ["/camera/front", "sensor_msgs/Image", "12 Hz", "存档"],
  ["/imu/data", "sensor_msgs/Imu", "100 Hz", "波形"],
];

const diagnosticsCards = [
  ["motor_driver", "warning", "2 路电机驱动进入降额，先查电流波形与温升日志", "看波形"],
  ["ros_time_sync", "ok", "TF 与 joint_states 时钟偏差 < 8ms，可继续只读分析", "看 TF"],
  ["camera_drop", "warning", "前相机有丢帧，建议回放 rosbag 验证", "看 rosbag"],
];

const rosbagRows = [
  ["arm_calibration_2026-05-14.bag", "12 分钟", "joint/current/imu", "回放到 AI 实验室", "去回放"],
  ["camera_front_debug.bag", "4 分钟", "camera/tf", "核对丢帧原因", "看丢帧"],
  ["foc_tuning_snapshot.db3", "90 秒", "current/velocity", "只读分析 PID/FOC 建议", "看调参建议"],
];

const motorRows = [
  ["M1 shoulder", "FOC 只读", "电流 1.8A / 速度波动 6%", "建议先降 P 增 D，进入仿真验证", "去仿真验证"],
  ["M2 elbow", "PID 建议", "过冲 12% / 温升稳定", "先采 30s 波形，不写入参数", "看波形"],
  ["M3 gripper", "限位复核", "位置闭环正常", "真实夹爪动作必须待审", "回工作台审批"],
];

const reviewActionRows = [
  ["写入 PID / FOC 参数", "强审", "只能生成建议卡，不能直接下发。", "审批参数写入"],
  ["真实运动 / 夹爪动作", "强审", "必须由人确认安全范围、急停和现场状态。", "查看安全门"],
  ["固件 / 驱动 / 部署", "强审", "先给仿真或台架计划，执行前回工作台审批。", "审批固件动作"],
];

const debugModes = [
  ["can", "CAN 调试", "帧流、ID、decoder、采样频率"],
  ["serial", "串口调试", "日志、帧解析、波特率、只读采集"],
  ["usb", "USB 调试", "设备枚举、驱动状态、权限检查"],
  ["ros", "ROS 只读桥", "topic、TF、rosbag、观察卡"],
];

const canFrameRows = [
  ["0x180", "M1.status", "8", "angle=12.4 vel=0.02 current=1.8A", "100 Hz"],
  ["0x181", "M2.status", "8", "angle=31.8 vel=0.00 current=1.1A", "100 Hz"],
  ["0x240", "safety.state", "6", "estop=0 limit=0 locked=1", "20 Hz"],
  ["0x300", "emg.sample", "8", "seq=1283 quality=ok", "500 Hz"],
];

const serialRows = [
  ["ttyUSB0", "PSoC M33", "115200", "fault=0 mode=readonly temp=34C"],
  ["ttyUSB1", "C8T6 sensor", "921600", "emg seq=1283 imu ok spo2 wait"],
  ["COM debug", "motor drv", "115200", "param snapshot ready, write locked"],
];

const usbRows = [
  ["USB-CAN", "已枚举", "驱动可见，当前只读监听"],
  ["DAP-Link", "待连接", "固件烧录属于强审动作"],
  ["串口转接器", "已枚举", "串口采集可入数据工场"],
];

const debugSamplingDrafts: Record<string, { title: string; channels: string; rate: string; window: string; schema: string }> = {
  can: {
    title: "CAN 总线只读采样",
    channels: "can0:0x180,0x181,0x240,0x300",
    rate: "100Hz/500Hz",
    window: "30s",
    schema: "can_frame + motor_status + safety_state",
  },
  serial: {
    title: "串口日志只读采样",
    channels: "ttyUSB0,ttyUSB1",
    rate: "115200/921600",
    window: "60s",
    schema: "serial_line + device_status + sensor_sample",
  },
  usb: {
    title: "USB 设备枚举快照",
    channels: "USB-CAN,DAP-Link,串口转接器",
    rate: "snapshot",
    window: "1次",
    schema: "usb_device + permission_state + driver_state",
  },
  ros: {
    title: "ROS 只读 topic 采样",
    channels: "/joint_states,/tf,/camera/front,/imu/data",
    rate: "32-100Hz",
    window: "30s",
    schema: "ros_topic + tf + joint_state + imu",
  },
};

export default async function ProjectRoboticsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { return_to?: string; from?: string; task_id?: string; message_id?: string; dispatch_id?: string; source_seat?: string; source_label?: string; source_title?: string; focus?: string; debug?: string };
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
  const focusTitle = text(searchParams?.source_title, "来自 NPC 工作台的机器人现场焦点");
  const focusSeat = publicFocusSeat(searchParams?.source_label ?? searchParams?.source_seat);
  const onlineComputers = computers.filter((node) => computerDispatchState(node) === "可投递").length;
  const computerCapabilityRows = computers.length
    ? computers.map((node, index) => {
        const capabilities = nodeCapabilities(node);
        const dispatchState = computerDispatchState(node);
        return {
          label: text(node.label ?? node.name, `执行电脑 ${index + 1}`),
          summary: [
            text(node.os, "系统待确认"),
            text(node.host, "地址待确认"),
          ].join(" · "),
          state: dispatchState,
          can: supportsDeviceMode(capabilities, "can"),
          serial: supportsDeviceMode(capabilities, "serial"),
          usb: supportsDeviceMode(capabilities, "usb"),
          ros: supportsDeviceMode(capabilities, "ros"),
        };
      })
    : [
        {
          label: "待登记执行电脑",
          summary: "先在主页面登记 Linux / NanoPi / 工作站",
          state: "待确认",
          can: "待确认",
          serial: "待确认",
          usb: "待确认",
          ros: "待确认",
        },
      ];
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/robotics`;
  const requestedDebugMode = text(searchParams?.debug, "can").toLowerCase();
  const debugMode = ["can", "serial", "usb", "ros"].includes(requestedDebugMode) ? requestedDebugMode : "can";
  const samplingDraft = debugSamplingDrafts[debugMode] ?? debugSamplingDrafts.can;
  const debugModeHref = (mode: string) => {
    const params = new URLSearchParams({ debug: mode });
    if (returnTo) params.set("return_to", returnTo);
    if (searchParams?.from) params.set("from", searchParams.from);
    if (searchParams?.task_id) params.set("task_id", searchParams.task_id);
    if (searchParams?.message_id) params.set("message_id", searchParams.message_id);
    if (searchParams?.dispatch_id) params.set("dispatch_id", searchParams.dispatch_id);
    if (searchParams?.source_seat) params.set("source_seat", searchParams.source_seat);
    if (searchParams?.source_label) params.set("source_label", searchParams.source_label);
    if (searchParams?.source_title) params.set("source_title", searchParams.source_title);
    return `${selfPath}?${params.toString()}`;
  };
  const samplingDraftHref = (mode = debugMode) => {
    const draft = debugSamplingDrafts[mode] ?? debugSamplingDrafts.can;
    const params = new URLSearchParams({
      return_to: selfPath,
      from: "robotics",
      intake: "device",
      device_mode: mode,
      channels: draft.channels,
      rate: draft.rate,
      window: draft.window,
      schema: draft.schema,
      source_title: draft.title,
    });
    if (searchParams?.task_id) params.set("task_id", searchParams.task_id);
    if (searchParams?.message_id) params.set("message_id", searchParams.message_id);
    if (searchParams?.dispatch_id) params.set("dispatch_id", searchParams.dispatch_id);
    if (searchParams?.source_seat) params.set("source_seat", searchParams.source_seat);
    if (searchParams?.source_label) params.set("source_label", searchParams.source_label);
    return `/projects/${projectId}/datasets?${params.toString()}`;
  };
  const readiness = Math.min(
    100,
    Math.round((onlineComputers ? 32 : 0) + (documents.length ? 18 : 0) + (skills.length ? 18 : 0) + (workstations.length ? 18 : 0) + (seats.length ? 14 : 0)),
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
    { label: "CAN 调试", href: debugModeHref("can"), detail: "帧流 / 过滤 / 采样频率", active: debugMode === "can" },
    { label: "串口调试", href: debugModeHref("serial"), detail: "端口 / 波特率 / 日志", active: debugMode === "serial" },
    { label: "USB 调试", href: debugModeHref("usb"), detail: "枚举 / 驱动 / 权限", active: debugMode === "usb" },
    { label: "ROS 只读桥", href: debugModeHref("ros"), detail: "topic / TF / rosbag", active: debugMode === "ros" },
    { label: "电机参数", href: "#motor", detail: "快照 / 波形 / 建议" },
    { label: "强审动作", href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`, detail: "写入 / 运动 / 固件" },
  ];
  const capabilityCards = [
    { label: "主体", detail: "机器人/电机调试工程师负责判断与审批" },
    { label: "AI 辅助", detail: "只读诊断、波形解释、回放建议、审批卡整理" },
    { label: "产出", detail: "manifest、topic 索引、波形记录" },
    { label: "边界", detail: "真实动作、写参数、firmware 都要人审" },
  ];
  const signalCards = [
    { label: "现场就绪", value: `${readiness}%`, detail: "就绪度只反映只读观测链路。", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`, actionLabel: "查看现场状态" },
    { label: "执行电脑", value: `${onlineComputers}/${computers.length}`, detail: "执行电脑状态异常先去观测台。", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`, actionLabel: "检查执行状态" },
    { label: "异常", value: `${String(taskException.failed ?? 0)}`, detail: taskException.actionable ? "先看异常和日志记录。" : "当前可以继续只读观测。", href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`, actionLabel: "回工作台处理" },
  ];
  const taskActions = [
    { label: "查看观测台", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`, primary: true },
    { label: "回 NPC 工作台", href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics` },
    { label: "进 AI 实验室回放", href: `/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=robotics` },
  ];
  const roboticsLinks = {
    observability: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`,
    workbench: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`,
    aiLab: `/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=robotics`,
    datasets: samplingDraftHref(),
    telemetry: `${selfPath}#telemetry`,
    model: `${selfPath}#model`,
    logs: `${selfPath}#logs`,
    safety: `${selfPath}#safety`,
  };

  return (
    <ProfessionalWorkbenchShell
      projectId={projectId}
      pageKey="robotics"
      pageTitle="机器人现场"
      pageSummary="像电机调试上位机一样工作：左侧对象树，中间当前调试工具，右侧动作与安全门，底部日志。"
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
      <section className={styles.ideSurface} aria-label="机器人现场 IDE 工作面">
        <section className={styles.ideHero}>
          <div>
            <span>当前工具</span>
            <strong>{debugMode === "serial" ? "串口调试" : debugMode === "usb" ? "USB 调试" : debugMode === "ros" ? "ROS 只读桥" : "CAN 调试"}</strong>
            <p>机器人现场只做只读检查、采样草案、记录整理和强审申请。写参数、真实运动、固件和 ROS 写操作都不能在这里直接执行。</p>
          </div>
          <div className={styles.ideHeroActions}>
            <Link href={samplingDraftHref()}>采样入库</Link>
            <Link href={roboticsLinks.workbench}>申请强审</Link>
            <Link href={roboticsLinks.observability}>看记录</Link>
          </div>
        </section>

        <section className={styles.deviceDebugIde} aria-label="设备调试 IDE">
          <section className={styles.debugCenterPane}>
            <div className={styles.debugWorkbenchHeader}>
              <div><span>调试参数</span><strong>只读 · {samplingDraft.rate} · {samplingDraft.window}</strong></div>
              <div className={styles.debugHeaderActions}><Link href={samplingDraftHref()}>生成采样草案</Link><Link href={roboticsLinks.datasets}>入数据工场</Link></div>
            </div>
            <div className={styles.debugTabs} role="tablist" aria-label="调试模式">
              {debugModes.map(([mode, label, detail]) => (
                <Link key={mode} href={debugModeHref(mode)} data-active={debugMode === mode ? "1" : undefined}><strong>{label}</strong><span>{detail}</span></Link>
              ))}
            </div>

            {debugMode === "serial" ? (
              <section className={styles.debugPanel} id="serial-debug" aria-label="串口调试">
                <div className={styles.panelHead}><span>串口调试</span><Link href={samplingDraftHref("serial")}>生成采样草案</Link></div>
                <div className={styles.serialConsole}>{serialRows.map(([port, device, baud, line]) => <article key={`${port}-${device}`}><strong>{port}</strong><span>{device} · {baud}</span><code>{line}</code></article>)}</div>
              </section>
            ) : debugMode === "usb" ? (
              <section className={styles.debugPanel} id="usb-debug" aria-label="USB 调试">
                <div className={styles.panelHead}><span>USB 调试</span><Link href={samplingDraftHref("usb")}>生成采样草案</Link></div>
                <div className={styles.usbGrid}>{usbRows.map(([name, state, detail]) => <article key={name} data-state={state}><strong>{name}</strong><span>{state}</span><p>{detail}</p></article>)}</div>
              </section>
            ) : debugMode === "ros" ? (
              <section className={styles.debugPanel} id="ros-debug" aria-label="ROS 只读桥">
                <div className={styles.panelHead}><span>ROS 只读桥</span><Link href={samplingDraftHref("ros")}>生成采样草案</Link></div>
                <div className={styles.topicTable}>{topicRows.map(([topic, type, rate, mode]) => <article key={topic}><strong>{topic}</strong><span>{type}</span><small>{rate}</small><em>{mode}</em></article>)}</div>
              </section>
            ) : (
              <section className={styles.debugPanel} id="can-debug" aria-label="CAN 调试">
                <div className={styles.panelHead}><span>CAN 调试</span><Link href={samplingDraftHref("can")}>按频率采样</Link></div>
                <div className={styles.canFrameTable}>{canFrameRows.map(([id, name, dlc, payload, rate]) => <article key={`${id}-${name}`}><strong>{id}</strong><span>{name}</span><small>DLC {dlc} · {rate}</small><p>{payload}</p></article>)}</div>
              </section>
            )}

            <div className={styles.debugBottomLog}>
              <span>事件 / 回执</span>
              <strong>只读检查 · 采样草案 · 强审动作</strong>
              <p>写 CAN、串口写命令、ROS publish/service/action、firmware 烧录和真实运动都不会在这里直接执行。</p>
            </div>
          </section>
        </section>

        <section className={styles.ideTwoColumns} id="safety">
          <section>
            <div className={styles.panelHead}><span>安全 / 强审动作卡</span><Link href={roboticsLinks.workbench}>回工作台审批</Link></div>
            <div className={styles.reviewActionGrid}>{reviewActionRows.map(([name, state, detail, actionLabel]) => <article key={name}><strong>{name}</strong><span>{state}</span><p>{detail}</p><Link href={actionLabel === "查看安全门" ? roboticsLinks.safety : roboticsLinks.workbench}>{actionLabel}</Link></article>)}</div>
          </section>
          <section>
            <div className={styles.panelHead}><span>执行通道</span><Link href={roboticsLinks.observability}>管理</Link></div>
            <div className={styles.debugComputerRows}>{computerCapabilityRows.slice(0, 4).map((node) => <article key={node.label}><div><strong>{node.label}</strong><small>{node.summary}</small></div><span data-state={node.state === "可投递" ? "ready" : "wait"}>{node.state}</span><em>CAN {node.can}</em><em>串口 {node.serial}</em><em>USB {node.usb}</em><em>ROS {node.ros}</em></article>)}</div>
          </section>
        </section>

        <details className={styles.advancedEvidenceDrawer}>
          <summary><span>高级记录区</span><strong>模型、波形、TF、电机参数和历史面板</strong></summary>
          <div className={styles.ideDrawerGrid}>
            {[...diagnosticsCards, ...motorRows, ...rosbagRows].slice(0, 9).map((row) => (
              <article key={row[0]}><strong>{row[0]}</strong><span>{row[1]}</span><p>{row[2]}</p></article>
            ))}
          </div>
        </details>
      </section>
    </ProfessionalWorkbenchShell>
  );
}
