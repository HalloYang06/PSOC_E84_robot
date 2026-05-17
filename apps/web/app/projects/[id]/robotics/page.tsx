import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectBossPlansState,
  getProjectComputerNodesState,
  getProjectKnowledgeDocumentsState,
  getProjectSkillsState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
  getTaskProfessionalViewState,
} from "../../../../lib/server-data";
import { ProfessionalEvidenceShell } from "../_components/professional-evidence-shell";
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
  if (!node) return "待确认";
  const watchState = statusText(node.runner_watch_state ?? node.runnerWatchState);
  const effective = statusText(node.runner_effective_status ?? node.runnerEffectiveStatus ?? node.runner_status ?? node.runnerStatus ?? node.status);
  if (watchState === "watching" || /watching|online|ready|active|connected/.test(effective)) return "可接单";
  if (/stale|timeout|delay|recent/.test(watchState) || /stale|timeout|delay|recent/.test(effective)) return "可能延迟";
  if (/offline|lost|disconnect|error|runner_offline|missing/.test(watchState) || /offline|lost|disconnect|error/.test(effective)) return "需重连";
  return "待确认";
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

function professionalMetric(view: AnyRecord | null, key: string) {
  const value = view?.summary?.[key];
  return Number.isFinite(Number(value)) ? String(Number(value)) : "0";
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

const operationQueue = [
  ["导入模型", "URDF / GLTF / GLB", "浏览器轻量解析"],
  ["连接仿真", "Gazebo / Webots / Isaac", "等执行电脑"],
  ["整理证据", "audio / imu / joint / camera", "可送数据工场"],
  ["高风险动作", "上电 / 运动 / 写参数", "人审"],
];

const safetyGates = [
  ["只读观察", "topic / bag / 日志 / 数据预览"],
  ["仿真优先", "先在 Gazebo / Webots / Isaac 验证"],
  ["人审写入", "部署 / 回退 / 硬件动作需要审核"],
];

const waveformBars = [34, 58, 42, 82, 46, 70, 38, 92, 54, 76, 44, 66, 52, 86, 48, 62, 36, 72];

const diagnosticRows = [
  ["TF 未对齐", "1", "先看 joint_states 与模型是否一致"],
  ["IMU 有断点", "2", "回数据工场补采样段"],
  ["相机帧率偏低", "1", "先做只读复查，不触发写入"],
];

const firstLookCards = [
  ["只读现场", "先看 topic、TF、波形和日志证据。", "先判断现场是否可继续推进"],
  ["仿真优先", "调参或动作验证先走回放和仿真。", "先回放再决定"],
  ["安全风险门", "写参数、部署和真实运动只走审批。", "风险先看清"],
];

const diagnosticsCards = [
  ["motor_driver", "warning", "2 路电机驱动进入降额，先查电流波形与温升日志", "看波形"],
  ["ros_time_sync", "ok", "TF 与 joint_states 时钟偏差 < 8ms，可继续只读分析", "看 TF"],
  ["camera_drop", "warning", "前相机有丢帧，建议回放 rosbag 验证", "看 rosbag"],
];

const logRows = [
  ["执行电脑", "最新只读巡检", "14:18", "topic 列表、TF、joint_states 已回流", "看观测台"],
  ["ros-sync", "连接观察", "14:11", "未执行 publish/service/action，仅做订阅检查", "看只读策略"],
  ["sim-gazebo", "回放计划", "13:56", "仿真回放待进入 AI 实验室执行", "去 AI 实验室"],
];

const rosbagRows = [
  ["arm_calibration_2026-05-14.bag", "12 分钟", "joint/current/imu", "回放到 AI 实验室", "去回放"],
  ["camera_front_debug.bag", "4 分钟", "camera/tf", "核对丢帧原因", "看丢帧"],
  ["foc_tuning_snapshot.db3", "90 秒", "current/velocity", "只读分析 PID/FOC 建议", "看调参建议"],
];

const tfRows = [
  ["base_link -> shoulder_link", "ok", "< 2 ms", "模型与 joint_states 对齐，保持只读观察"],
  ["shoulder_link -> elbow_link", "warning", "11 ms", "先回放 rosbag，确认是否是时钟抖动"],
  ["camera_front -> tool0", "warning", "缺 1 段", "先核对相机与末端坐标，不触发重标定写入"],
];

const motorRows = [
  ["M1 shoulder", "FOC 只读", "电流 1.8A / 速度波动 6%", "建议先降 P 增 D，进入仿真验证", "去仿真验证"],
  ["M2 elbow", "PID 建议", "过冲 12% / 温升稳定", "先采 30s 波形，不写入参数", "看波形"],
  ["M3 gripper", "限位复核", "位置闭环正常", "真实夹爪动作必须待审", "回工作台审批"],
];

const tuningAdviceRows = [
  ["电流纹波偏高", "先看 current / velocity 波形，再讨论 FOC 参数", "波形优先"],
  ["过冲明显", "先做 AI 实验室回放，确认是否由目标速度突变引起", "回放优先"],
  ["末端抖动", "先核对 TF 与 joint_states 时间轴，再决定是否需要仿真复核", "TF 优先"],
];

const reviewActionRows = [
  ["写入 PID / FOC 参数", "强审", "只能生成建议卡，不能直接下发。", "审批参数写入"],
  ["真实运动 / 夹爪动作", "强审", "必须由人确认安全范围、急停和现场状态。", "查看安全门"],
  ["固件 / 驱动 / 部署", "强审", "先给仿真或台架计划，执行前回工作台审批。", "审批固件动作"],
];

const readonlyCapabilityRows = [
  ["Topic", "Foxglove / Webviz", "只读订阅、频率、来源、异常片段"],
  ["Diagnostics", "Foxglove / ROS diagnostics", "设备状态、温升、时钟、驱动健康"],
  ["TF / URDF", "Webviz / MoveIt", "模型关系、joint 层次、坐标一致性"],
  ["rosbag", "rosbag2", "回放索引、时间段、主题覆盖、回放计划"],
  ["波形", "PlotJuggler", "电流 / IMU / joint 对齐与异常定位"],
  ["电机参数卡", "SimpleFOC / ODrive / moteus", "参数快照、风险说明、只读建议"],
];

const referenceModeRows = [
  ["Foxglove / Webviz", "Topic、TF、3D 模型与相机主题", "转成平台内的只读现场面板、话题清单和证据索引"],
  ["PlotJuggler", "波形对齐与异常片段定位", "转成波形面板、异常定位建议和数据工场入口"],
  ["rosbag2", "回放文件、时间段与主题覆盖", "转成 rosbag 索引、回放计划和 AI 实验室入口"],
  ["MoveIt / Gazebo / Webots", "规划、回放、仿真验证", "转成仿真优先的下一步动作卡，不在本页直接执行"],
  ["SimpleFOC / ODrive / moteus", "电机参数快照与调参经验", "转成电机参数卡、PID / FOC 建议和强审风险门"],
];

const riskGateRows = [
  ["只读能力", "可直接看", "topic、diagnostics、TF、rosbag、波形和参数卡都可以直接查看。", "看只读现场"],
  ["仿真与计划", "建议先做", "先去 AI 实验室或仿真环境验证，再决定是否需要现场动作。", "看仿真入口"],
  ["高风险动作", "必须强审", "实时控制、参数写入、固件、部署和真实运动只能走审批卡。", "去审批卡"],
];

const readonlyActionRows = [
  ["1. 导入模型", "先在本页导入 URDF / GLTF，导出 manifest 留证。", "检查模型", "model"],
  ["2. 做只读检查", "生成 topic 任务包，只做订阅与索引，不触发写入。", "生成只读检查", "model"],
  ["3. 看波形与 rosbag", "顺着同一条证据链看 TF、波形、回放计划。", "看日志与回放", "logs"],
  ["4. 提交证据或审批", "只读证据回平台；高风险动作一律回工作台审批。", "回 NPC 工作台", "workbench"],
];

const hmiStatusRows = [
  ["只读诊断", "3", "TF / IMU / 相机", "warning"],
  ["回放包", "3", "rosbag / db3", "ok"],
  ["执行电脑", "live", "只读巡检回流", "ok"],
  ["风险门", "强审", "写参数 / 运动", "danger"],
];

const hmiObjectRows = [
  ["base_link", "ok", "60 Hz"],
  ["shoulder / elbow", "warning", "32 Hz"],
  ["camera_front", "warning", "12 Hz"],
  ["imu/data", "ok", "100 Hz"],
];

const hmiMotorSnapshotRows = [
  ["M1", "1.8A", "纹波偏高"],
  ["M2", "12%", "过冲"],
  ["M3", "ok", "限位正常"],
];

const debugActors = [
  ["主角", "设备调试工程师", "负责判断、审批和现场安全"],
  ["负责 NPC", "机器人现场 NPC", "整理只读证据、生成任务包"],
  ["执行电脑", "Linux / NanoPi / Runner", "只读采集 CAN、串口、USB、ROS"],
];

const debugObjects = [
  ["CAN 总线", "can0", "500k / 1M 待验", "ready"],
  ["串口", "ttyUSB0", "115200 8N1", "ready"],
  ["USB 设备", "USB-CAN / 调试器", "枚举中", "warn"],
  ["ROS 只读桥", "/joint_states / /tf", "只读", "ready"],
  ["数据采样", "100-500 Hz", "入数据工场", "ready"],
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
    bossPlansState,
    taskProfessionalState,
  ] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
    getProjectSkillsState(projectId),
    getProjectKnowledgeDocumentsState(projectId),
    getProjectBossPlansState(projectId, 5),
    searchParams?.task_id ? getTaskProfessionalViewState(searchParams.task_id) : Promise.resolve({ data: null, status: 200, error: null }),
  ]);

  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(seatsState.data);
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const skills = asArray<AnyRecord>(skillsState.data);
  const documents = asArray<AnyRecord>(documentsState.data);
  const bossPlans = asArray<AnyRecord>(bossPlansState.data);
  const taskView = taskProfessionalState.data as AnyRecord | null;
  const taskException = exceptionSummary(taskView);
  const messageFocus = Boolean(searchParams?.message_id || searchParams?.dispatch_id || searchParams?.source_seat);
  const focusTitle = text(searchParams?.source_title, "来自 NPC 工作台的机器人现场焦点");
  const focusSeat = publicFocusSeat(searchParams?.source_label ?? searchParams?.source_seat);
  const onlineComputers = computers.filter((node) => computerDispatchState(node) === "可接单").length;
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
          state: dispatchState === "可接单" ? "可接单" : dispatchState === "可能延迟" ? "可能延迟" : dispatchState === "需重连" ? "需重连" : "待确认",
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
  const rightLinks = [
    ["看当前异常", `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`],
    ["提交诊断给 NPC", `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`],
    ["送样本入库", `/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics`],
    ["回放 / 仿真验证", `/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=robotics`],
    ["申请强审动作", `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`],
  ];
  const capabilityCards = [
    { label: "主体", detail: "机器人/电机调试工程师负责判断与审批" },
    { label: "AI 辅助", detail: "只读诊断、波形解释、回放建议、审批卡整理" },
    { label: "证据", detail: "manifest、topic 索引、波形证据" },
    { label: "边界", detail: "真实动作、写参数、firmware 都要人审" },
  ];
  const signalCards = [
    { label: "现场就绪", value: `${readiness}%`, detail: "就绪度只反映只读观测链路。", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`, actionLabel: "查看现场状态" },
    { label: "执行电脑", value: `${onlineComputers}/${computers.length}`, detail: "执行电脑状态异常先去观测台。", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`, actionLabel: "检查执行状态" },
    { label: "异常", value: `${String(taskException.failed ?? 0)}`, detail: taskException.actionable ? "先看异常和日志证据。" : "当前可以继续只读观测。", href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`, actionLabel: "回工作台处理" },
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
    <ProfessionalEvidenceShell
      projectId={projectId}
      pageKey="robotics"
      pageTitle="机器人现场"
      pageSummary="给机器人调试工程师和电机调参工程师看的只读安全现场页：中央看证据，右侧看风险，底部看日志与回放。"
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
      <section className={styles.workspace}>
        <section className={styles.firstLookStrip} aria-label="第一眼看到什么">
          {firstLookCards.map(([label, detail, note]) => (
            <article key={label}>
              <strong>{label}</strong>
              <p>{detail}</p>
              <small>{note}</small>
            </article>
          ))}
        </section>

        {taskView || messageFocus ? (
          <section className={styles.contextPanel} aria-label="任务证据链">
            <div>
              <span>任务证据链 · 来自 NPC 对话</span>
              <strong>{taskView ? text(taskView.task?.title, focusTitle) : focusTitle}</strong>
              <small>
                {focusSeat} · 派单 {text(searchParams?.dispatch_id, "") ? "已进入队列" : "未指定"}
              </small>
            </div>
            <div className={styles.contextStats}>
              <article><span>派单</span><strong>{professionalMetric(taskView, "dispatch_count")}</strong></article>
              <article><span>消息</span><strong>{professionalMetric(taskView, "message_count")}</strong></article>
              <article><span>证据</span><strong>{professionalMetric(taskView, "artifact_count")}</strong></article>
              <article data-alert={taskException.actionable ? "1" : undefined}>
                <span>异常</span><strong>{String(taskException.failed ?? 0)}</strong>
              </article>
            </div>
            <div className={styles.contextActions}>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>回工作台</Link>
              <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>查看观测台</Link>
              <Link href={`/projects/${projectId}/datasets?task_id=${encodeURIComponent(text(searchParams?.task_id, ""))}&message_id=${encodeURIComponent(text(searchParams?.message_id, ""))}&return_to=${encodeURIComponent(selfPath)}&from=robotics`}>入数据工场</Link>
            </div>
          </section>
        ) : null}

        <section className={styles.reviewActionPanel} aria-label="强审动作">
          <div className={styles.panelHead}>
            <span>安全 / 强审动作卡</span>
            <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>回工作台审批</Link>
          </div>
          <div className={styles.reviewActionGrid}>
            {reviewActionRows.map(([name, state, detail, actionLabel]) => (
              <article key={name}>
                <strong>{name}</strong>
                <span>{state}</span>
                <p>{detail}</p>
                <Link href={actionLabel === "查看风险门" ? roboticsLinks.safety : roboticsLinks.workbench}>{actionLabel}</Link>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.deviceDebugIde} aria-label="设备调试 IDE">
          <aside className={styles.debugLeftPane}>
            <div className={styles.debugPaneTitle}>
              <span>现场主角</span>
              <strong>设备调试工程师</strong>
            </div>
            <div className={styles.debugActorList}>
              {debugActors.map(([role, name, detail]) => (
                <article key={role}>
                  <span>{role}</span>
                  <strong>{name}</strong>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
            <div className={styles.debugObjectTree}>
              <span>对象树</span>
              {debugObjects.map(([name, port, detail, state]) => (
                <a key={name} href={name.includes("CAN") ? "#can-debug" : name.includes("串口") ? "#serial-debug" : name.includes("USB") ? "#usb-debug" : "#ros-debug"} data-state={state}>
                  <strong>{name}</strong>
                  <small>{port}</small>
                  <em>{detail}</em>
                </a>
              ))}
            </div>
            <div className={styles.debugCapabilityMatrix}>
              <div className={styles.debugPaneTitle}>
                <span>执行电脑能力矩阵</span>
                <strong>{onlineComputers}/{computers.length || 1} 在线</strong>
              </div>
              <div className={styles.debugComputerRows}>
                {computerCapabilityRows.map((node) => (
                  <article key={node.label}>
                    <div>
                      <strong>{node.label}</strong>
                      <small>{node.summary}</small>
                    </div>
                    <span data-state={node.state === "在线" ? "ready" : "wait"}>{node.state}</span>
                    <em>CAN {node.can}</em>
                    <em>串口 {node.serial}</em>
                    <em>USB {node.usb}</em>
                    <em>ROS {node.ros}</em>
                  </article>
                ))}
              </div>
            </div>
          </aside>

          <section className={styles.debugCenterPane}>
            <div className={styles.debugWorkbenchHeader}>
              <div>
                <span>设备调试台 / 默认只读</span>
                <strong>CAN、串口、USB、ROS 在同一个工程工作面里看</strong>
              </div>
              <div className={styles.debugHeaderActions}>
                <Link href={samplingDraftHref()}>采样入库</Link>
                <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>申请强审</Link>
              </div>
            </div>

            <div className={styles.debugTabs} role="tablist" aria-label="调试模式">
              {debugModes.map(([mode, label, detail]) => (
                <Link key={mode} href={debugModeHref(mode)} data-active={debugMode === mode ? "1" : undefined}>
                  <strong>{label}</strong>
                  <span>{detail}</span>
                </Link>
              ))}
            </div>

            <div className={styles.debugMainGrid} data-mode={debugMode}>
              {debugMode === "can" ? (
              <section className={styles.debugPanel} id="can-debug" aria-label="CAN 调试">
                <div className={styles.panelHead}>
                  <span>CAN 调试</span>
                  <Link href={samplingDraftHref("can")}>按频率采样</Link>
                </div>
                <div className={styles.canFrameTable}>
                  {canFrameRows.map(([id, name, dlc, payload, rate]) => (
                    <article key={`${id}-${name}`}>
                      <strong>{id}</strong>
                      <span>{name}</span>
                      <small>DLC {dlc} · {rate}</small>
                      <p>{payload}</p>
                    </article>
                  ))}
                </div>
              </section>
              ) : null}

              {debugMode === "serial" ? (
              <section className={styles.debugPanel} id="serial-debug" aria-label="串口调试">
                <div className={styles.panelHead}>
                  <span>串口调试</span>
                  <Link href={samplingDraftHref("serial")}>生成采样草案</Link>
                </div>
                <div className={styles.serialConsole}>
                  {serialRows.map(([port, device, baud, line]) => (
                    <article key={`${port}-${device}`}>
                      <strong>{port}</strong>
                      <span>{device} · {baud}</span>
                      <code>{line}</code>
                    </article>
                  ))}
                </div>
              </section>
              ) : null}

              {debugMode === "usb" ? (
              <section className={styles.debugPanel} id="usb-debug" aria-label="USB 调试">
                <div className={styles.panelHead}>
                  <span>USB 调试</span>
                  <Link href={samplingDraftHref("usb")}>生成采样草案</Link>
                </div>
                <div className={styles.usbGrid}>
                  {usbRows.map(([name, state, detail]) => (
                    <article key={name} data-state={state}>
                      <strong>{name}</strong>
                      <span>{state}</span>
                      <p>{detail}</p>
                    </article>
                  ))}
                </div>
              </section>
              ) : null}

              {debugMode === "ros" ? (
              <section className={styles.debugPanel} id="ros-debug" aria-label="ROS 只读桥">
                <div className={styles.panelHead}>
                  <span>ROS 只读桥</span>
                  <Link href={samplingDraftHref("ros")}>生成采样草案</Link>
                </div>
                <div className={styles.topicTable}>
                  {topicRows.map(([topic, type, rate, mode]) => (
                    <article key={topic}>
                      <strong>{topic}</strong>
                      <span>{type}</span>
                      <small>{rate}</small>
                      <em>{mode}</em>
                    </article>
                  ))}
                </div>
              </section>
              ) : null}
            </div>

            <div className={styles.debugBottomLog}>
              <span>事件 / 回执</span>
              <strong>只读检查 · 生成任务包 · 数据工场采样 · 强审动作</strong>
              <p>写 CAN、串口写命令、ROS publish/service/action、firmware 烧录和真实运动都不会在这里直接执行。</p>
            </div>
          </section>

          <aside className={styles.debugRightPane}>
            <div className={styles.debugPaneTitle}>
              <span>工具模式</span>
              <strong>选择右侧工具</strong>
            </div>
            <div className={styles.debugModeList}>
              {debugModes.map(([mode, label, detail]) => (
                <Link key={mode} href={debugModeHref(mode)} data-active={debugMode === mode ? "1" : undefined}>
                  <strong>{label}</strong>
                  <p>{detail}</p>
                </Link>
              ))}
            </div>
            <div className={styles.debugPropertyBox}>
              <span>当前权限</span>
              <strong>只读 / L0</strong>
              <p>AI 和 NPC 只能辅助解释、生成采样任务、整理审批卡，不能替人执行硬件写入。</p>
            </div>
            <div className={styles.debugPropertyBox}>
              <span>采样策略</span>
              <strong>{samplingDraft.rate} · {samplingDraft.window}</strong>
              <p>{samplingDraft.title}：{samplingDraft.schema}。进入数据工场后仍需人工确认采样任务。</p>
            </div>
          </aside>
        </section>

        <details className={styles.advancedEvidenceDrawer}>
          <summary>
            <span>高级证据区</span>
            <strong>模型、波形、TF、电机参数和历史面板</strong>
          </summary>

        <section className={styles.commandDeck} id="model" aria-label="机器人现场总控">
          <section className={styles.viewportPanel}>
            <div className={styles.panelHead}>
              <span>模型 / 仿真状态</span>
              <div className={styles.segmented}>
                <button type="button">模型</button>
                <button type="button">TF</button>
                <button type="button">仿真</button>
              </div>
            </div>
              <div className={styles.scene}>
                <div className={styles.sceneReadout}>
                  <strong>工程师先看模型和同步状态</strong>
                  <span>导入 URDF / GLTF 后识别关节；执行电脑可同步 robot_description、TF、joint_states。AI 只帮助解释证据，不代替你下现场动作。</span>
                </div>
              <div className={styles.floorGrid} />
              <div className={styles.viewerFrame}>
                <div className={styles.viewerCore}>
                  <i />
                  <i />
                  <i />
                  <i />
                </div>
              </div>
              <div className={styles.layerDock}>
                <span>URDF</span>
                <span>TF</span>
                <span>Joint</span>
                <span>Map</span>
              </div>
              <div className={styles.hmiObjectTree}>
                <span>对象树</span>
                {hmiObjectRows.map(([name, state, rate]) => (
                  <article key={name} data-state={state}>
                    <strong>{name}</strong>
                    <small>{rate}</small>
                  </article>
                ))}
              </div>
              <div className={styles.sceneWaveDock}>
                <span>current / velocity / imu</span>
                <div>
                  {waveformBars.slice(0, 12).map((height, index) => <i key={`${height}-${index}`} style={{ ["--h" as string]: `${height}%` }} />)}
                </div>
              </div>
              <div className={styles.motorSnapshot}>
                <span>电机参数卡</span>
                {hmiMotorSnapshotRows.map(([motor, value, note]) => (
                  <article key={motor}>
                    <strong>{motor}</strong>
                    <small>{value}</small>
                    <em>{note}</em>
                  </article>
                ))}
              </div>
            </div>
          </section>

          <section className={styles.modelColumn}>
            <ModelImportInspector />
            <RosNodeConnector />
              <div className={styles.operationQueue}>
                <div className={styles.panelHead}>
                  <span>下一步</span>
                  <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>整理给 NPC</Link>
                </div>
                {operationQueue.map(([label, detail, state]) => (
                  <article key={label}>
                  <strong>{label}</strong>
                  <p>{detail}</p>
                  <span>{state}</span>
                </article>
              ))}
            </div>
          </section>
        </section>

        <section className={styles.telemetryGrid} id="telemetry">
          <section className={styles.topicPanel}>
            <div className={styles.panelHead}>
              <span>Topic / 数据流</span>
              <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>查看日志</Link>
            </div>
            <div className={styles.topicTable}>
              {topicRows.map(([topic, type, rate, mode]) => (
                <article key={topic}>
                  <strong>{topic}</strong>
                  <span>{type}</span>
                  <small>{rate}</small>
                  <em>{mode}</em>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.wavePanel}>
            <div className={styles.panelHead}>
              <span>波形 / 事件对齐</span>
              <Link href={`/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>入库</Link>
            </div>
            <div className={styles.waveform}>
              {waveformBars.map((height, index) => <i key={`${height}-${index}`} style={{ ["--h" as string]: `${height}%` }} />)}
            </div>
            <div className={styles.signalRows}>
              <span>audio.in</span>
              <span>imu.acc</span>
              <span>joint.pos</span>
            </div>
          </section>
        </section>

        <section className={styles.tfPanel} aria-label="TF 与坐标一致性">
          <div className={styles.panelHead}>
            <span>TF / 坐标一致性</span>
            <Link href={`${selfPath}#model`}>回模型视图</Link>
          </div>
          <div className={styles.tfRows}>
            {tfRows.map(([name, state, lag, detail]) => (
              <article key={name} data-state={state}>
                <strong>{name}</strong>
                <span>{state}</span>
                <small>{lag}</small>
                <p>{detail}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.hmiDock} id="logs" aria-label="现场底部状态抽屉">
          <div className={styles.hmiStatusStrip}>
            {hmiStatusRows.map(([label, value, detail, state]) => (
              <article key={label} data-state={state}>
                <span>{label}</span>
                <strong>{value}</strong>
                <p>{detail}</p>
              </article>
            ))}
          </div>
          <div className={styles.hmiDrawers}>
            <details open>
              <summary>
                <span>诊断</span>
                <strong>异常卡与日志</strong>
              </summary>
              <div className={styles.diagnosticsCardGrid}>
                {diagnosticsCards.map(([name, state, detail, actionLabel]) => (
                  <article key={name} data-state={state}>
                    <strong>{name}</strong>
                    <span>{state}</span>
                    <p>{detail}</p>
                    <Link href={actionLabel === "看 TF" ? roboticsLinks.model : actionLabel === "看 rosbag" ? roboticsLinks.logs : roboticsLinks.telemetry}>{actionLabel}</Link>
                  </article>
                ))}
              </div>
              <div className={styles.logRows}>
                {logRows.map(([source, label, time, detail, actionLabel]) => (
                  <article key={`${source}-${label}`}>
                    <strong>{source}</strong>
                    <span>{label}</span>
                    <small>{time}</small>
                    <p>{detail}</p>
                    <Link href={actionLabel === "去 AI 实验室" ? roboticsLinks.aiLab : actionLabel === "看只读策略" ? roboticsLinks.safety : roboticsLinks.observability}>{actionLabel}</Link>
                  </article>
                ))}
              </div>
            </details>

            <details>
              <summary>
                <span>回放</span>
                <strong>rosbag / db3</strong>
              </summary>
              <div className={styles.rosbagRows}>
                {rosbagRows.map(([name, duration, topics, action, actionLabel]) => (
                  <article key={name}>
                    <strong>{name}</strong>
                    <span>{duration}</span>
                    <small>{topics}</small>
                    <p>{action}</p>
                    <Link href={actionLabel === "去回放" ? roboticsLinks.aiLab : actionLabel === "看调参建议" ? `${selfPath}#motor` : roboticsLinks.logs}>{actionLabel}</Link>
                  </article>
                ))}
              </div>
            </details>

            <details>
              <summary>
                <span>去向</span>
                <strong>证据链下一步</strong>
              </summary>
              <div className={styles.hmiActionStrip}>
                <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>看观测台</Link>
                <Link href={`/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>去 AI 实验室回放</Link>
                <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>回 NPC 工作台审批</Link>
              </div>
            </details>

            <details>
              <summary>
                <span>只读能力</span>
                <strong>证据与观测能力</strong>
              </summary>
              <div className={styles.capabilityRows}>
                {readonlyCapabilityRows.map(([name, source, detail]) => (
                  <article key={name}>
                    <strong>{name}</strong>
                    <span>{source}</span>
                    <p>{detail}</p>
                  </article>
                ))}
              </div>
              <div className={styles.referenceRows}>
                {referenceModeRows.map(([source, focus, result]) => (
                  <article key={source}>
                    <strong>{source}</strong>
                    <span>{focus}</span>
                    <p>{result}</p>
                  </article>
                ))}
              </div>
            </details>

            <details>
              <summary>
                <span>证据资源</span>
                <strong>上下文与下一步</strong>
              </summary>
              <div className={styles.resourceList}>
                <div><strong>{documents.length}</strong><small>知识库</small></div>
                <div><strong>{skills.length}</strong><small>能力包</small></div>
                <div><strong>{bossPlans.length}</strong><small>计划</small></div>
              </div>
              <div className={styles.workflowTrack}>
                {readonlyActionRows.map(([label, detail, actionLabel, target], index) => (
                  <article key={label}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{label.replace(/^\d+\.\s*/, "")}</strong>
                    <p>{detail}</p>
                    <Link href={target === "workbench" ? roboticsLinks.workbench : `${selfPath}#${target}`}>{actionLabel}</Link>
                  </article>
                ))}
              </div>
            </details>
          </div>
        </section>

        <section className={styles.bottomGrid}>
          <section className={styles.devicePanel}>
            <div className={styles.panelHead}>
              <span>电脑 / 执行状态</span>
              <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>管理</Link>
            </div>
            <div className={styles.deviceList}>
              {computers.length ? computers.slice(0, 6).map((node, index) => (
                <article key={text(node.id, text(node.name, "computer"))}>
                  <strong>{publicComputerName(node, index)}</strong>
                  <span>{text(node.runner_effective_status ?? node.runner_status ?? node.status, "未知状态")}</span>
                </article>
              )) : <p className={styles.emptyHint}>还没有电脑接入。</p>}
            </div>
          </section>

          <section className={styles.safetyPanel} id="safety">
            <div className={styles.panelHead}>
              <span>安全闸门</span>
              <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>审计</Link>
            </div>
            <div className={styles.gateGrid}>
              {safetyGates.map(([label, detail]) => (
                <article key={label}>
                  <strong>{label}</strong>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
          </section>
        </section>

        <section className={styles.diagnosticPanel}>
          <div className={styles.panelHead}>
            <span>只读诊断</span>
            <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>派给 NPC</Link>
          </div>
          <div className={styles.diagnosticRows}>
            {diagnosticRows.map(([label, count, detail]) => (
              <article key={label}>
                <strong>{label}</strong>
                <span>{count}</span>
                <p>{detail}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.motorPanel} id="motor" aria-label="电机只读调试">
          <div className={styles.panelHead}>
            <span>电机 / 调参建议</span>
            <Link href={`/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=robotics`}>仿真验证</Link>
          </div>
          <div className={styles.motorGrid}>
            {motorRows.map(([name, mode, signal, advice, actionLabel]) => (
              <article key={name}>
                <div>
                  <strong>{name}</strong>
                  <span>{mode}</span>
                </div>
                <p>{signal}</p>
                <small>{advice}</small>
                <Link href={actionLabel === "回工作台审批" ? roboticsLinks.workbench : actionLabel === "看波形" ? roboticsLinks.telemetry : roboticsLinks.aiLab}>{actionLabel}</Link>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.tuningAdvicePanel} aria-label="调参建议看板">
          <div className={styles.panelHead}>
            <span>PID / FOC 建议看板</span>
            <Link href={`${selfPath}#telemetry`}>看波形依据</Link>
          </div>
          <div className={styles.tuningAdviceGrid}>
            {tuningAdviceRows.map(([title, detail, state]) => (
              <article key={title}>
                <strong>{title}</strong>
                <span>{state}</span>
                <p>{detail}</p>
              </article>
            ))}
          </div>
        </section>
        </details>

      </section>

      <aside className={styles.rightRail}>
        <details className={styles.sideDrawer} open>
          <summary>
            <span>当前对象</span>
            <strong>模型 / Topic / 电机</strong>
          </summary>
          <div className={styles.objectInspector}>
            <article>
              <span>模型</span>
              <strong>URDF / GLTF</strong>
              <p>中央区导入和检查模型；右侧只显示对象状态，不放长说明。</p>
            </article>
            <article>
              <span>遥测</span>
              <strong>{topicRows.length} 个 topic</strong>
              <p>只读订阅、频率、TF 和波形进入中央工作面。</p>
            </article>
            <article>
              <span>电机</span>
              <strong>{motorRows.length} 张参数卡</strong>
              <p>AI 只给调参建议，写参数和真实运动必须回工作台审批。</p>
            </article>
          </div>
        </details>

        <details className={styles.sideDrawer} open>
          <summary>
            <span>风险门</span>
            <strong>强审动作</strong>
          </summary>
          <div className={styles.toolList}>
            <Link href={roboticsLinks.workbench}>审批写参数 / 运动</Link>
            <Link href={roboticsLinks.aiLab}>先去仿真验证</Link>
            <Link href={roboticsLinks.observability}>看风险证据</Link>
          </div>
        </details>

        <details className={styles.sideDrawer}>
          <summary>
            <span>现场动作</span>
            <strong>诊断去向</strong>
          </summary>
          <div className={styles.toolList}>
            {rightLinks.map(([label, href]) => <Link key={label} href={href}>{label}</Link>)}
          </div>
        </details>

        <details className={styles.sideDrawer}>
          <summary>
            <span>证据抽屉</span>
            <strong>回执 / 资源 / 证据链</strong>
          </summary>
          <div className={styles.resourceList}>
            <div><strong>{documents.length}</strong><small>知识库</small></div>
            <div><strong>{skills.length}</strong><small>能力包</small></div>
            <div><strong>{bossPlans.length}</strong><small>计划</small></div>
          </div>
          <div className={styles.toolList}>
            <Link href={roboticsLinks.observability}>看观测台证据</Link>
            <Link href={roboticsLinks.workbench}>回 NPC 工作台</Link>
            <Link href={roboticsLinks.datasets}>送样本入库</Link>
          </div>
        </details>

      </aside>
    </ProfessionalEvidenceShell>
  );
}
