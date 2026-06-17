"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import flowStyles from "./rehab-arm-joint-flow.module.css";
import styles from "./rehab-arm-control.module.css";

export type AnyRecord = Record<string, any>;

export type DashboardDevice = {
  device_id: string;
  robot_id: string;
  online_state: string;
  last_upload_ts_unix: number | null;
  safety_state: string;
  motion_allowed: boolean;
  current_session: string;
  latest_upload_status: string;
  latest_error: string;
  camera_keyframe?: AnyRecord;
  camera_stream_offer?: AnyRecord;
  command_center_snapshot?: AnyRecord;
  robot_render_state?: AnyRecord;
  wiring_health?: AnyRecord;
  safety_status?: AnyRecord;
  voice_relay?: AnyRecord;
  vla_plan_candidate?: AnyRecord;
  estop_ack?: AnyRecord;
  motor_state?: AnyRecord;
  sensor_state?: AnyRecord;
  safety?: AnyRecord;
  sync_status?: AnyRecord;
  manifest?: AnyRecord;
  data_quality?: AnyRecord;
  device_model?: AnyRecord;
  model_relay_response?: AnyRecord;
  xiaozhi_session?: AnyRecord;
};

export type Dashboard = {
  sync_role: string;
  safety_boundary: {
    server_may_send: string[];
    server_must_not_send: string[];
    m33_final_authority: boolean;
  };
  devices: DashboardDevice[];
  recent_events: AnyRecord[];
};

type Props = {
  apiBaseUrl: string;
  dashboard: Dashboard;
  projectId: string;
  projectName: string;
};

type JointDetail = {
  name: string;
  type: string;
  parent: string;
  child: string;
};

type UrdfPackage = {
  fileName: string;
  packageName: string;
  urdfPath: string;
  urdfText: string;
  files: Map<string, ArrayBuffer>;
};

type JointCalibration = {
  jointName: string;
  sourceName: string;
  unit: "rad" | "deg";
  direction: 1 | -1;
  offsetRad: number;
};

type RelayProviderPreset = {
  id: string;
  label: string;
  base_url: string;
  model_hint: string;
};

type RelayConfig = {
  provider: string;
  base_url: string;
  model: string;
  external_enabled: boolean;
  api_key_configured: boolean;
  presets: RelayProviderPreset[];
};

type JointFlowRow = {
  jointName: string;
  sourceName: string;
  sourceLabel: string;
  rawValue: number | null;
  calibratedValue: number | null;
  velocity: number | null;
  effort: number | null;
  temperature: number | null;
  freshnessText: string;
  freshnessState: "fresh" | "recent" | "stale" | "waiting";
  status: "matched" | "waiting" | "fault";
};

type UrdfVisualMesh = {
  linkName: string;
  meshPath: string;
  xyz: [number, number, number];
  rpy: [number, number, number];
  scale: [number, number, number];
};

type RenderJointRow = {
  name: string;
  position: number | null;
  velocity: number | null;
  fresh: boolean;
  limitClamped: boolean;
};

const DEFAULT_RELAY_PRESETS: RelayProviderPreset[] = [
  { id: "openai", label: "OpenAI", base_url: "https://api.openai.com/v1", model_hint: "gpt-4o-mini / gpt-4.1-mini" },
  { id: "azure_openai", label: "Azure OpenAI", base_url: "https://YOUR-RESOURCE.openai.azure.com/openai/v1", model_hint: "deployment name" },
  { id: "deepseek", label: "DeepSeek", base_url: "https://api.deepseek.com/v1", model_hint: "deepseek-chat" },
  { id: "qwen", label: "通义千问 / DashScope", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model_hint: "qwen-plus" },
  { id: "moonshot", label: "Moonshot / Kimi", base_url: "https://api.moonshot.cn/v1", model_hint: "moonshot-v1-8k" },
  { id: "zhipu", label: "智谱 GLM", base_url: "https://open.bigmodel.cn/api/paas/v4", model_hint: "glm-4-flash" },
  { id: "siliconflow", label: "硅基流动", base_url: "https://api.siliconflow.cn/v1", model_hint: "Qwen/Qwen2.5-7B-Instruct" },
  { id: "custom", label: "自定义 OpenAI-compatible", base_url: "", model_hint: "model id" },
];

function normalizeCalibration(value: unknown): JointCalibration | null {
  const row = record(value);
  const jointName = text(row.jointName ?? row.joint_name, "");
  if (!jointName) return null;
  return {
    jointName,
    sourceName: text(row.sourceName ?? row.source_name, ""),
    unit: text(row.unit, "rad") === "deg" ? "deg" : "rad",
    direction: Number(row.direction) === -1 ? -1 : 1,
    offsetRad: Number(row.offsetRad ?? row.offset_rad) || 0,
  };
}

function calibrationMapFromJson(value: unknown) {
  try {
    const parsed = typeof value === "string" ? JSON.parse(value) : value;
    const rows = asArray<unknown>(parsed).map(normalizeCalibration).filter(Boolean) as JointCalibration[];
    return new Map(rows.map((row) => [row.jointName, row]));
  } catch {
    return new Map<string, JointCalibration>();
  }
}

function modelInfoFromRecord(value: unknown) {
  const model = record(value);
  const payload = payloadOf(model);
  return {
    modelUrl: text(model.model_url ?? payload.model_url, ""),
    fileName: text(payload.file_name, "robot_model.zip"),
    packageName: text(payload.package_name, "robot_model"),
    urdfPath: text(payload.urdf_path, ""),
    sha256: text(payload.sha256, ""),
    mappingJson: payload.mapping_json,
  };
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

function isPublicPlaceholder(value: unknown) {
  const raw = text(value, "").toLowerCase();
  return !raw || raw === "unknown" || raw === "none" || raw === "null";
}

function publicDeviceName(device: DashboardDevice | null | undefined, index = 0) {
  const safeIndex = Math.max(0, index);
  const snapshot = payloadOf(device?.command_center_snapshot);
  const robotName = text(device?.robot_id, "");
  if (!isPublicPlaceholder(robotName) && !isRawIdentifier(robotName)) return robotName;
  const snapshotRobotName = text(snapshot.robot_id, "");
  if (!isPublicPlaceholder(snapshotRobotName) && !isRawIdentifier(snapshotRobotName)) return snapshotRobotName;
  const deviceName = text(device?.device_id, "");
  if (!isPublicPlaceholder(deviceName) && !isRawIdentifier(deviceName)) return deviceName;
  return `康复机械臂 ${safeIndex + 1}`;
}

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

function emptyDashboard(): Dashboard {
  return {
    sync_role: "cloud_readonly",
    safety_boundary: {
      server_may_send: ["只读状态查看", "数据质量检查", "高层任务草案"],
      server_must_not_send: ["CAN/电机真实控制", "力矩/速度/位置写入", "绕过 M33 安全链路"],
      m33_final_authority: true,
    },
    devices: [],
    recent_events: [],
  };
}

function filterDashboardForProject(value: unknown, projectId: string): Dashboard {
  const payload = record(value);
  const data = record(payload.data ?? payload);
  const baseline = emptyDashboard();
  const devices = asArray<AnyRecord>(data.devices)
    .filter((device) => deviceProjectId(device) === projectId) as DashboardDevice[];
  const deviceIds = new Set(devices.map((device) => text(device.device_id, "")).filter(Boolean));
  const recentEvents = asArray<AnyRecord>(data.recent_events).filter((event) => {
    const eventProjectId = text(event.project_id ?? event.projectId, "");
    if (eventProjectId) return eventProjectId === projectId;
    const eventDeviceId = text(event.device_id, "");
    return !eventDeviceId || deviceIds.has(eventDeviceId);
  });

  return {
    ...baseline,
    ...data,
    safety_boundary: {
      ...baseline.safety_boundary,
      ...record(data.safety_boundary),
    },
    devices,
    recent_events: recentEvents,
  };
}

function publicDeviceCode(device: DashboardDevice | null | undefined, index = 0) {
  const safeIndex = Math.max(0, index);
  const raw = text(device?.device_id, "");
  if (!raw || isRawIdentifier(raw)) return `设备 ${safeIndex + 1}`;
  return raw;
}

function publicBatchLabel(value: unknown, fallback = "暂无数据批次") {
  const raw = text(value, fallback);
  return raw.replace(/^session[\s_-]*/i, "批次 ");
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function payloadOf(value: unknown): AnyRecord {
  if (!value || typeof value !== "object") return {};
  const record = value as AnyRecord;
  return record.payload && typeof record.payload === "object" ? record.payload as AnyRecord : {};
}

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? value as AnyRecord : {};
}

function formatTime(value: unknown) {
  const ts = Number(value);
  if (!Number.isFinite(ts) || ts <= 0) return "无记录";
  const date = new Date(ts * 1000);
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? "00";
  return `${part("year")}/${part("month")}/${part("day")} ${part("hour")}:${part("minute")}:${part("second")}`;
}

function formatClock(value: number | null) {
  if (!value) return "";
  const date = new Date(value);
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? "00";
  return `${part("hour")}:${part("minute")}:${part("second")}`;
}

function timestampUnix(value: unknown): number | null {
  const source = record(value);
  const nestedPayload = record(source.payload);
  const candidates = [
    source.source_ts_unix,
    source.ts_unix,
    source.timestamp_unix,
    source.updated_at_unix,
    source.frame_ts_unix,
    nestedPayload.ts_unix,
    nestedPayload.timestamp_unix,
    nestedPayload.frame_ts_unix,
  ];
  for (const candidate of candidates) {
    const number = Number(candidate);
    if (Number.isFinite(number) && number > 0) return number;
  }
  return null;
}

function freshness(tsUnix: number | null, nowMs: number) {
  if (!tsUnix) return { text: "等待上报", state: "waiting" as const };
  if (nowMs <= 0) return { text: "等待刷新", state: "waiting" as const };
  const ageSeconds = Math.max(0, Math.round((nowMs - tsUnix * 1000) / 1000));
  if (ageSeconds < 15) return { text: "刚刚更新", state: "fresh" as const };
  if (ageSeconds < 120) return { text: `${ageSeconds} 秒前`, state: "fresh" as const };
  const ageMinutes = Math.round(ageSeconds / 60);
  if (ageMinutes < 10) return { text: `${ageMinutes} 分钟前`, state: "recent" as const };
  if (ageMinutes < 60) return { text: `${ageMinutes} 分钟未更新`, state: "stale" as const };
  return { text: `${Math.round(ageMinutes / 60)} 小时未更新`, state: "stale" as const };
}

function stateLabel(value: unknown) {
  switch (text(value, "ok")) {
    case "limited":
      return "limited";
    case "emergency_stop":
      return "emergency_stop";
    case "fault":
      return "fault";
    default:
      return "ok";
  }
}

function stateText(value: unknown) {
  switch (stateLabel(value)) {
    case "limited":
      return "受限";
    case "emergency_stop":
      return "急停";
    case "fault":
      return "故障";
    default:
      return "正常";
  }
}

function eventTitle(event: AnyRecord) {
  const type = text(event.record_type, "event");
  if (type === "motor_state") return "电机状态更新";
  if (type === "sensor_state") return "传感器摘要更新";
  if (type === "safety_state") return "安全状态更新";
  if (type === "camera_keyframe") return "摄像头关键帧";
  if (type === "xiaozhi_ws_input") return "M55 输入";
  if (type === "xiaozhi_ws_reply") return "平台回复";
  if (type === "sync_status") return "数据批次同步";
  if (type === "manifest") return "设备档案上传";
  if (type === "device_registration") return "设备注册";
  return type;
}

function xiaozhiEventLabel(value: unknown) {
  const raw = text(value, "waiting");
  if (raw === "hello") return "hello 握手";
  if (raw === "listen_start") return "开始听取";
  if (raw === "audio") return "音频帧";
  if (raw === "reply") return "平台回复";
  if (raw === "listen_stop") return "停止听取";
  if (raw === "disconnect") return "连接断开";
  return raw;
}

function xiaozhiKindLabel(value: unknown) {
  const raw = text(value, "");
  if (raw === "daily_chat") return "日常聊天";
  if (raw === "vla_command") return "VLA 语言输入";
  if (raw === "none") return "未分类";
  return raw || "等待分类";
}

function xiaozhiUiStateLabel(value: unknown) {
  switch (text(value, "offline")) {
    case "listening":
      return "正在听取";
    case "wake_detected":
      return "唤醒已触发";
    case "thinking":
      return "正在思考";
    case "speaking":
      return "正在播报";
    case "idle":
      return "待机";
    case "error":
      return "异常";
    case "offline":
      return "离线";
    default:
      return "未知状态";
  }
}

function xiaozhiUiStateTone(value: unknown) {
  switch (text(value, "offline")) {
    case "listening":
      return "ok";
    case "wake_detected":
      return "limited";
    case "thinking":
      return "limited";
    case "speaking":
      return "ok";
    case "idle":
      return "idle";
    case "error":
      return "fault";
    default:
      return "idle";
  }
}

function xiaozhiUiStateHint(value: unknown) {
  switch (text(value, "offline")) {
    case "listening":
      return "等待唤醒词和麦克风输入";
    case "wake_detected":
      return "已识别唤醒，准备开始录音";
    case "thinking":
      return "平台正在整理上下文并请求模型";
    case "speaking":
      return "平台正在通过扬声器回复";
    case "idle":
      return "没有新语音时进入待机";
    case "error":
      return "会话出现错误，检查 last_error";
    default:
      return "未建立会话或设备离线";
  }
}

function vlaGateLabel(value: unknown) {
  const gate = record(value);
  if (gate.participates_in_vla_l === true) return "进入 VLA-L";
  const route = text(gate.route, "");
  if (route === "daily_chat_only") return "日常聊天，不进 VLA";
  if (route === "no_vla_input") return "未进入 VLA";
  return "等待语言门控";
}

function xiaozhiDirectionLabel(recordType: unknown) {
  return text(recordType, "") === "xiaozhi_ws_reply" ? "平台 → M55" : "M55 → 平台";
}

function boolText(value: unknown) {
  return value ? "是" : "否";
}

function publicStateValue(value: unknown, fallback = "未上报") {
  const raw = text(value, fallback);
  return raw === "unknown" ? fallback : raw;
}

function publicSourceLabel(value: unknown, fallback = "等待载荷") {
  const raw = text(value, "");
  if (!raw) return fallback;
  return raw
    .replace(/nanopi_readonly_agent/gi, "只读数据节点")
    .replace(/readonly_agent/gi, "只读数据节点")
    .replace(/motor_state/gi, "电机状态")
    .replace(/joint_state/gi, "关节状态")
    .replace(/sensor_state/gi, "传感器摘要")
    .replace(/_/g, " ");
}

type RoleSignals = {
  onlineDevices: number;
  hasSafety: boolean;
  hasCamera: boolean;
  hasSimulation: boolean;
};

function roleSignalsFromDevices(devices: DashboardDevice[]): RoleSignals {
  return devices.reduce<RoleSignals>((signals, device) => ({
    onlineDevices: signals.onlineDevices + (device.online_state === "online" ? 1 : 0),
    hasSafety: signals.hasSafety || Object.keys(payloadOf(device.safety)).length > 0 || Boolean(text(device.safety_state, "")),
    hasCamera: signals.hasCamera || Boolean(text(payloadOf(device.camera_keyframe).image_url, "") || text(record(device.camera_keyframe).image_url, "")),
    hasSimulation: signals.hasSimulation || Object.keys(record((device as AnyRecord).simulation_readiness)).length > 0,
  }), {
    onlineDevices: 0,
    hasSafety: false,
    hasCamera: false,
    hasSimulation: false,
  });
}

function latestRoleStatus(signals: RoleSignals, kind: "nanopi" | "m33" | "app" | "sim") {
  if (kind === "nanopi") {
    return {
      value: signals.onlineDevices ? `${signals.onlineDevices} 台在线` : "等待接入",
      detail: signals.onlineDevices ? "已收到开发板或设备节点的只读状态。" : "运行 NanoPi/开发板数据代理后，这里会出现在线设备。",
      ready: signals.onlineDevices > 0,
    };
  }
  if (kind === "m33") {
    return {
      value: signals.hasSafety ? "有安全状态" : "等待安全状态",
      detail: "M33 是最终安全裁决；网页只显示状态，不解除急停或覆盖裁决。",
      ready: signals.hasSafety,
    };
  }
  if (kind === "app") {
    return {
      value: signals.hasCamera ? "可看现场帧" : "等待现场数据",
      detail: "App/现场侧负责近场参数与急停；平台只做远程协作和证据。",
      ready: signals.hasCamera,
    };
  }
  return {
    value: signals.hasSimulation ? "有仿真报告" : "等待仿真主机",
    detail: "仿真主机负责 MuJoCo/RViz/路径验证，云端只收状态和证据。",
    ready: signals.hasSimulation,
  };
}

function numberText(value: unknown, unit = "") {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${Number.isInteger(number) ? number : number.toFixed(3)}${unit}`;
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value));
}

function firstFiniteNumber(...values: unknown[]) {
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return null;
}

function motorPosition(motor: AnyRecord) {
  const value = Number(
    motor.position_rad
      ?? motor.positionRad
      ?? motor.angle_rad
      ?? motor.angleRad
      ?? motor.position_deg
      ?? motor.positionDeg
      ?? motor.angle_deg
      ?? motor.angleDeg
      ?? motor.position
      ?? motor.angle,
  );
  return Number.isFinite(value) ? value : null;
}

function motorTemperature(motor: AnyRecord) {
  return firstFiniteNumber(motor.temperature, motor.temp_c, motor.tempC, motor.motor_temperature_c, motor.motorTemperatureC);
}

type MuscleSignalRow = {
  key: string;
  label: string;
  value: number | null;
  fatigue: number | null;
  status: "active" | "moderate" | "quiet" | "unknown";
};

type HumanModelSource = {
  id: string;
  label: string;
  source: string;
  url: string;
  license: string;
  note: string;
};

type MotionPredictionRow = {
  key: string;
  label: string;
  value: string;
  detail: string;
  tone: "active" | "moderate" | "quiet" | "unknown";
};

const DEFAULT_HUMAN_MODEL_SOURCES: HumanModelSource[] = [
  {
    id: "anatom-models-upper-limb",
    label: "Open upper-limb GLB",
    source: "juncrose/anatom-models",
    url: "https://raw.githubusercontent.com/juncrose/anatom-models/main/upper-limb.glb",
    license: "Project page / public GitHub file",
    note: "默认 3D 承载位，优先加载这份开源上肢模型。",
  },
  {
    id: "anatomytool-upper-limb",
    label: "Open3DModel upper limb",
    source: "AnatomyTOOL / Open3D project",
    url: "https://anatomytool.org/content/open3dmodel-upper-limb-english-labels",
    license: "CC BY-SA",
    note: "适合做分肌肉标签和示意图的开源人体上肢参考。",
  },
  {
    id: "z-anatomy",
    label: "Z-Anatomy atlas",
    source: "Z-Anatomy",
    url: "https://github.com/Z-Anatomy",
    license: "Open source atlas",
    note: "更完整的开源解剖图谱备选入口。",
  },
];

function normalizedSignalValue(...values: unknown[]) {
  const raw = firstFiniteNumber(...values);
  if (raw === null) return null;
  return clamp01(raw > 1 ? raw / 100 : raw);
}

function muscleStatus(value: number | null): MuscleSignalRow["status"] {
  if (value === null) return "unknown";
  if (value >= 0.68) return "active";
  if (value >= 0.34) return "moderate";
  return "quiet";
}

function humanModelUrlFromSensor(sensorPayload: AnyRecord) {
  const model = record(sensorPayload.human_model ?? sensorPayload.humanModel ?? sensorPayload.model_outputs?.human_model ?? sensorPayload.modelOutputs?.human_model);
  return text(
    model.url
      ?? model.model_url
      ?? model.glb_url
      ?? sensorPayload.human_model_url
      ?? sensorPayload.humanModelUrl,
    DEFAULT_HUMAN_MODEL_SOURCES[0].url,
  );
}

function humanModelSourceFromSensor(sensorPayload: AnyRecord) {
  const model = record(sensorPayload.human_model ?? sensorPayload.humanModel ?? sensorPayload.model_outputs?.human_model ?? sensorPayload.modelOutputs?.human_model);
  return text(
    model.source
      ?? model.vendor
      ?? sensorPayload.human_model_source
      ?? sensorPayload.humanModelSource,
    DEFAULT_HUMAN_MODEL_SOURCES[0].source,
  );
}

function motionPredictionRowsFromSensor(sensorPayload: AnyRecord): MotionPredictionRow[] {
  const source = record(
    sensorPayload.motion_prediction
      ?? sensorPayload.motionPrediction
      ?? sensorPayload.action_prediction
      ?? sensorPayload.actionPrediction
      ?? sensorPayload.model_outputs
      ?? sensorPayload.modelOutputs,
  );
  const candidates = asArray<AnyRecord>(
    source.candidates
      ?? source.top_k
      ?? source.actions
      ?? sensorPayload.action_candidates
      ?? sensorPayload.predicted_actions,
  );
  const rows: MotionPredictionRow[] = [];
  candidates.slice(0, 3).forEach((candidate, index) => {
    rows.push({
      key: `candidate_${index + 1}`,
      label: text(candidate.label ?? candidate.name ?? candidate.action ?? candidate.id, `候选 ${index + 1}`),
      value: text(candidate.confidence ?? candidate.score ?? candidate.probability, candidate.confidence === 0 ? "0%" : "-"),
      detail: text(candidate.detail ?? candidate.reason ?? candidate.description ?? candidate.note, text(candidate.phase ?? candidate.intent, "等待动作模型")),
      tone: muscleStatus(normalizedSignalValue(candidate.confidence ?? candidate.score ?? candidate.probability) ?? null),
    });
  });
  if (rows.length) return rows;

  const intent = record(sensorPayload.intent_prediction ?? sensorPayload.intentPrediction ?? sensorPayload.intent ?? source.intent);
  const summary = text(
    source.summary
      ?? source.recommended_action
      ?? source.recommendation
      ?? intent.summary
      ?? sensorPayload.action_summary
      ?? sensorPayload.motion_summary,
    "等待动作预测模型接入",
  );
  const interfaceRef = text(
    source.interface
      ?? source.input
      ?? source.schema_version
      ?? sensorPayload.prediction_interface
      ?? "sensor_payload.motion_prediction / action_prediction / model_outputs",
    "sensor_payload.motion_prediction / action_prediction / model_outputs",
  );
  return [
    {
      key: "summary",
      label: "动作摘要",
      value: summary,
      detail: "输出给平台展示和审阅，不直接变成运动许可。",
      tone: "moderate",
    },
    {
      key: "interface",
      label: "接口字段",
      value: interfaceRef,
      detail: "后续可从 NanoPi、M55 或云端模型把 top-k 动作建议塞进这个结构。",
      tone: "quiet",
    },
    {
      key: "inputs",
      label: "输入映射",
      value: text(
        source.inputs
          ?? source.features
          ?? sensorPayload.emg_channels
          ?? sensorPayload.channels
          ?? "EMG + fatigue + IMU",
        "EMG + fatigue + IMU",
      ),
      detail: "建议字段：channel_id、muscle_name、confidence、top_k、time_window。",
      tone: "quiet",
    },
  ];
}

function muscleRowsFromSensor(sensorPayload: AnyRecord): MuscleSignalRow[] {
  const emg = record(sensorPayload.emg ?? sensorPayload.emg_state ?? sensorPayload.muscle_signals ?? sensorPayload.muscleSignal);
  const fatigue = record(sensorPayload.fatigue ?? sensorPayload.fatigue_state ?? sensorPayload.fatigue_model ?? sensorPayload.fatigueModel);
  const channels = asArray<AnyRecord>(emg.channels ?? sensorPayload.emg_channels ?? sensorPayload.channels);
  const byName = new Map<string, AnyRecord>();
  channels.forEach((channel, index) => {
    const name = text(channel.name ?? channel.channel ?? channel.location ?? channel.muscle, `ch${index + 1}`).toLowerCase();
    byName.set(name, channel);
  });

  function pickChannel(names: string[]) {
    for (const name of names) {
      const direct = byName.get(name);
      if (direct) return direct;
      const fuzzy = Array.from(byName.entries()).find(([key]) => names.some((candidate) => key.includes(candidate)));
      if (fuzzy) return fuzzy[1];
    }
    return {};
  }

  const specs = [
    { key: "deltoid", label: "肩部三角肌", names: ["deltoid", "shoulder", "jian", "ch1"] },
    { key: "biceps", label: "上臂屈肌", names: ["biceps", "upper_arm", "shangbi", "ch2"] },
    { key: "forearm", label: "前臂屈伸肌", names: ["forearm", "wrist", "qianbi", "wanbu", "ch3"] },
    { key: "trapezius", label: "肩颈稳定肌", names: ["trapezius", "neck", "trunk", "jianjing", "ch4"] },
  ];

  return specs.map((spec, index) => {
    const channel = pickChannel(spec.names);
    const value = normalizedSignalValue(
      channel.activation,
      channel.value,
      channel.rms,
      channel.emg,
      channel.score,
      emg[spec.key],
      emg[`ch${index + 1}`],
      sensorPayload[spec.key],
    );
    const fatigueValue = normalizedSignalValue(
      channel.fatigue,
      channel.fatigue_score,
      fatigue[spec.key],
      fatigue[`ch${index + 1}`],
      sensorPayload.fatigue_score,
      sensorPayload.fatigueScore,
    );
    return {
      key: spec.key,
      label: spec.label,
      value,
      fatigue: fatigueValue,
      status: muscleStatus(value),
    };
  });
}

function jointValueMapFromMotors(motors: AnyRecord[]) {
  const values = new Map<string, number>();
  motors.forEach((motor) => {
    const value = motorPosition(motor);
    if (value === null) return;
    const jointName = text(motor.joint_name ?? motor.jointName, "");
    const motorId = text(motor.motor_id ?? motor.motorId, "");
    if (jointName) values.set(jointName, value);
    if (motorId) values.set(motorId, value);
  });
  return values;
}

function motorSourceNames(motors: AnyRecord[]) {
  return Array.from(new Set(motors.flatMap((motor, index) => {
    const jointName = text(motor.joint_name ?? motor.jointName, "");
    const motorId = text(motor.motor_id ?? motor.motorId, "");
    const sourceLabel = text(motor.source_label, "");
    if (sourceLabel === "ROS 关节状态" || sourceLabel === "robot_render_state_v1") return [jointName].filter(Boolean);
    return [jointName, motorId || `motor_${index + 1}`].filter(Boolean);
  })));
}

function motorSourceKey(motor: AnyRecord, index = 0) {
  const jointName = text(motor.joint_name ?? motor.jointName, "");
  const motorId = text(motor.motor_id ?? motor.motorId, "");
  const sourceLabel = text(motor.source_label, "");
  if (sourceLabel === "ROS 关节状态" || sourceLabel === "robot_render_state_v1") return jointName;
  return jointName || motorId || `motor_${index + 1}`;
}

function motorBySourceName(motors: AnyRecord[]) {
  const values = new Map<string, AnyRecord>();
  motors.forEach((motor, index) => {
    const keys = [
      text(motor.joint_name ?? motor.jointName, ""),
      text(motor.motor_id ?? motor.motorId, ""),
      motorSourceKey(motor, index),
    ].filter(Boolean);
    keys.forEach((key) => {
      if (!values.has(key)) values.set(key, motor);
    });
  });
  return values;
}

function jointStateSamplesFromPayload(value: unknown) {
  const payload = record(value);
  const sourceTsUnix = timestampUnix(payload);
  const jointState = payload.joint_state ?? payload.joint_states ?? payload.jointState ?? payload.jointStates;
  if (Array.isArray(jointState)) {
    return jointState
      .map((item, index) => {
        const row = record(item);
        const jointName = text(row.name ?? row.joint_name ?? row.jointName, "");
        if (!jointName) return null;
        return {
          motor_id: text(row.source ?? row.id, `joint_state_${index + 1}`),
          joint_name: jointName,
          position_rad: Number(row.position_rad ?? row.positionRad ?? row.position),
          velocity: Number(row.velocity ?? row.velocity_rad_s ?? row.velocityRadS),
          torque: Number(row.effort ?? row.torque),
          current: row.current,
          temperature: row.temperature,
          enabled: false,
          fault: false,
          source_label: "ROS 关节状态",
          source_ts_unix: timestampUnix(row) ?? sourceTsUnix,
        };
      })
      .filter(Boolean) as AnyRecord[];
  }
  const row = record(jointState);
  const names = asArray<unknown>(row.name ?? row.names);
  const positions = asArray<unknown>(row.position ?? row.positions);
  const velocities = asArray<unknown>(row.velocity ?? row.velocities);
  const efforts = asArray<unknown>(row.effort ?? row.efforts);
  return names
    .map((name, index) => {
      const jointName = text(name, "");
      if (!jointName) return null;
      return {
        motor_id: `joint_state_${index + 1}`,
        joint_name: jointName,
        position_rad: Number(positions[index]),
        velocity: Number(velocities[index]),
        torque: Number(efforts[index]),
        enabled: false,
        fault: false,
        source_label: "ROS 关节状态",
        source_ts_unix: sourceTsUnix,
      };
    })
    .filter(Boolean) as AnyRecord[];
}

function poseSamplesFromTelemetry(motorPayload: AnyRecord, sensorPayload: AnyRecord) {
  const motorTsUnix = timestampUnix(motorPayload);
  const motors: AnyRecord[] = asArray<AnyRecord>(motorPayload.motors).map((motor) => ({
    ...motor,
    source_label: "电机状态",
    source_ts_unix: timestampUnix(motor) ?? motorTsUnix,
  }));
  const jointStates = [
    ...jointStateSamplesFromPayload(motorPayload),
    ...jointStateSamplesFromPayload(sensorPayload),
  ];
  const seen = new Set<string>();
  return [...motors, ...jointStates].filter((sample) => {
    const key = text(sample.joint_name ?? sample.jointName ?? sample.motor_id ?? sample.motorId, "");
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function keyframeSrc(imageUrl: string, apiBaseUrl: string) {
  if (!imageUrl) return "";
  if (imageUrl.startsWith("/api/")) return `/api/proxy/${imageUrl.slice("/api/".length)}`;
  if (imageUrl.startsWith("/")) return imageUrl;
  return new URL(imageUrl, apiBaseUrl).toString();
}

function publicApiBaseUrl(apiBaseUrl: string) {
  if (typeof window === "undefined") return apiBaseUrl.replace(/\/$/, "");
  try {
    const configured = new URL(apiBaseUrl);
    const page = new URL(window.location.href);
    const configuredHost = configured.hostname.toLowerCase();
    const pageHost = page.hostname.toLowerCase();
    if (["127.0.0.1", "localhost", "0.0.0.0"].includes(configuredHost) && !["127.0.0.1", "localhost"].includes(pageHost)) {
      configured.protocol = page.protocol;
      configured.hostname = page.hostname;
      configured.port = "8011";
    }
    return configured.toString().replace(/\/$/, "");
  } catch {
    return apiBaseUrl.replace(/\/$/, "");
  }
}

function qualityReadyText(value: unknown) {
  return value ? "可标注" : "待补数据";
}

function publicQualityReason(value: unknown) {
  const raw = text(value, "");
  if (!raw) return "";
  return raw
    .replace(/waiting for manifest_with_summary upload/gi, "等待设备档案与质量摘要")
    .replace(/manifest/gi, "设备档案")
    .replace(/session/gi, "数据批次")
    .replace(/motor_state/gi, "电机状态")
    .replace(/joint_state/gi, "关节状态")
    .replace(/_/g, " ");
}

const ARM_MODEL_JSON = {
  links: [
    { name: "base", length: 0.22, radius: 0.08, color: 0x75f7dd },
    { name: "shoulder", length: 0.42, radius: 0.045, color: 0x8ef0c7 },
    { name: "upper_arm", length: 0.46, radius: 0.04, color: 0xf1d06b },
    { name: "forearm", length: 0.38, radius: 0.035, color: 0x58f0ff },
    { name: "wrist", length: 0.18, radius: 0.03, color: 0xffa6b5 },
  ],
  joints: [
    "shoulder_lift_joint",
    "shoulder_abduction_joint",
    "upper_arm_rotation_joint",
    "elbow_lift_joint",
    "forearm_rotation_joint",
  ],
};

function jointPositionsFromMotors(motors: AnyRecord[]) {
  const byName = jointValueMapFromMotors(motors);
  return ARM_MODEL_JSON.joints.map((name, index) => {
    const value = byName.get(name);
    if (Number.isFinite(value)) return Number(value);
    return null;
  });
}

function renderJointRowsFromState(value: unknown): RenderJointRow[] {
  const state = record(value);
  const names = asArray<unknown>(state.joint_names ?? state.jointNames);
  const positions = asArray<unknown>(state.positions);
  const velocities = asArray<unknown>(state.velocities);
  const fresh = asArray<unknown>(state.fresh);
  const limitClamped = asArray<unknown>(state.limit_clamped ?? state.limitClamped);
  return names.map((name, index) => {
    const isFresh = fresh[index] === true;
    const position = Number(positions[index]);
    const velocity = Number(velocities[index]);
    return {
      name: text(name, `joint_${index + 1}`),
      position: isFresh && Number.isFinite(position) ? position : null,
      velocity: isFresh && Number.isFinite(velocity) ? velocity : null,
      fresh: isFresh,
      limitClamped: limitClamped[index] === true,
    };
  }).filter((row) => row.name);
}

function poseSamplesFromRenderState(value: unknown, tsUnix: number | null) {
  return renderJointRowsFromState(value).map((row, index) => ({
    motor_id: `robot_render_state_${index + 1}`,
    joint_name: row.name,
    position_rad: row.position,
    velocity: row.velocity,
    enabled: false,
    fault: false,
    limit_clamped: row.limitClamped,
    render_fresh: row.fresh,
    source_label: "robot_render_state_v1",
    source_ts_unix: row.fresh ? tsUnix : null,
  }));
}

function renderStateOfDevice(device: DashboardDevice | null | undefined) {
  const direct = record(device?.robot_render_state);
  if (Object.keys(direct).length) return direct;
  const snapshotPayload = payloadOf(device?.command_center_snapshot);
  return record(snapshotPayload.robot_render_state);
}

function latestRelayPayload(device: DashboardDevice | null | undefined, key: keyof DashboardDevice) {
  return payloadOf(device?.[key]);
}

function parseUrdfJoints(urdfText: string): JointDetail[] {
  const doc = new DOMParser().parseFromString(urdfText, "application/xml");
  if (doc.getElementsByTagName("parsererror")[0]) throw new Error("invalid urdf");
  return Array.from(doc.getElementsByTagName("joint")).map((joint, index) => ({
    name: joint.getAttribute("name") || `joint_${index + 1}`,
    type: joint.getAttribute("type") || "unknown",
    parent: joint.getElementsByTagName("parent")[0]?.getAttribute("link") || "-",
    child: joint.getElementsByTagName("child")[0]?.getAttribute("link") || "-",
  }));
}

function movableJoints(joints: JointDetail[]) {
  return joints.filter((joint) => !["fixed", "floating"].includes(joint.type));
}

function calibrationStorageKey(urdfName: string) {
  return `rehab-arm-pose-calibration:${urdfName || "unloaded"}`;
}

function loadSavedCalibrations(urdfName: string): Map<string, JointCalibration> {
  if (typeof window === "undefined") return new Map<string, JointCalibration>();
  try {
    const raw = window.localStorage.getItem(calibrationStorageKey(urdfName));
    const rows = JSON.parse(raw || "[]") as JointCalibration[];
    return new Map(rows.filter((row) => row?.jointName).map((row) => {
      const normalized: JointCalibration = {
        jointName: row.jointName,
        sourceName: text(row.sourceName, ""),
        unit: row.unit === "deg" ? "deg" : "rad",
        direction: row.direction === -1 ? -1 : 1,
        offsetRad: Number.isFinite(Number(row.offsetRad)) ? Number(row.offsetRad) : 0,
      };
      return [normalized.jointName, normalized];
    }));
  } catch {
    return new Map<string, JointCalibration>();
  }
}

function saveCalibrations(urdfName: string, rows: JointCalibration[]) {
  if (typeof window === "undefined" || !urdfName) return;
  try {
    window.localStorage.setItem(calibrationStorageKey(urdfName), JSON.stringify(rows));
  } catch {
    // Best effort only: calibration remains active in memory even if browser storage is unavailable.
  }
}

function defaultCalibrations(jointNames: string[], sourceNames: string[], previous = new Map<string, JointCalibration>()) {
  return jointNames.map((jointName) => {
    const old = previous.get(jointName);
    if (old) return old;
    const exact = sourceNames.find((source) => source === jointName) ?? "";
    const fuzzy = exact || (sourceNames.find((source) => source.toLowerCase().includes(jointName.replace(/_joint$/i, "").toLowerCase())) ?? "");
    return {
      jointName,
      sourceName: fuzzy,
      unit: "rad" as const,
      direction: 1 as const,
      offsetRad: 0,
    };
  });
}

function calibratedJointValue(row: JointCalibration, sourceValues: Map<string, number>) {
  const rawValue = sourceValues.get(row.sourceName);
  if (!Number.isFinite(rawValue)) return null;
  const inRadians = row.unit === "deg" ? Number(rawValue) * Math.PI / 180 : Number(rawValue);
  return inRadians * row.direction + row.offsetRad;
}

function numericOrNull(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function jointFlowRows(
  jointNames: string[],
  calibrations: JointCalibration[],
  sourceValues: Map<string, number>,
  sourceMotors: Map<string, AnyRecord>,
  nowMs: number,
): JointFlowRow[] {
  const rowsByJoint = new Map(calibrations.map((row) => [row.jointName, row]));
  return jointNames.map((jointName) => {
    const row = rowsByJoint.get(jointName);
    const directValue = sourceValues.has(jointName) ? Number(sourceValues.get(jointName)) : null;
    const sourceName = row?.sourceName || (directValue !== null ? jointName : "");
    const motor = sourceName ? sourceMotors.get(sourceName) : undefined;
    const rawValue = sourceName && sourceValues.has(sourceName) ? Number(sourceValues.get(sourceName)) : null;
    const calibratedValue = row ? calibratedJointValue(row, sourceValues) : directValue;
    const fault = Boolean(motor?.fault ?? motor?.has_fault ?? motor?.hasFault);
    const sourceFreshness = freshness(timestampUnix(motor), nowMs);
    return {
      jointName,
      sourceName,
      sourceLabel: text(motor?.source_label, sourceName ? "只读渲染反馈" : "等待上报"),
      rawValue,
      calibratedValue,
      velocity: numericOrNull(motor?.velocity ?? motor?.velocity_rad_s ?? motor?.velocityRadS),
      effort: numericOrNull(motor?.torque ?? motor?.effort ?? motor?.current),
      temperature: numericOrNull(motor?.temperature ?? motor?.temp_c ?? motor?.tempC),
      freshnessText: sourceFreshness.text,
      freshnessState: sourceFreshness.state,
      status: fault ? "fault" : calibratedValue === null ? "waiting" : "matched",
    };
  });
}

function normalizePackagePath(value: string) {
  return value.replace(/\\/g, "/").replace(/^\/+/, "");
}

function zipFileName(flags: number, bytes: Uint8Array) {
  return new TextDecoder(flags & 0x0800 ? "utf-8" : "utf-8").decode(bytes);
}

async function inflateRaw(data: Uint8Array) {
  if (typeof DecompressionStream === "undefined") {
    throw new Error("zip inflate is not available");
  }
  const source = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
  const stream = new Blob([source]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Response(stream).arrayBuffer();
}

async function readZipEntries(buffer: ArrayBuffer) {
  try {
    const { unzipSync } = await import("fflate");
    const entries = unzipSync(new Uint8Array(buffer));
    return new Map(Object.entries(entries)
      .filter(([name]) => !normalizePackagePath(name).endsWith("/"))
      .map(([name, bytes]) => {
        const normalized = normalizePackagePath(name);
        const copy = bytes.slice();
        return [normalized, copy.buffer.slice(copy.byteOffset, copy.byteOffset + copy.byteLength) as ArrayBuffer];
      }));
  } catch {
    // Fall back to the small built-in ZIP reader below. It covers the stored/deflated URDF packages used here.
  }
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  let eocd = -1;
  for (let offset = bytes.length - 22; offset >= Math.max(0, bytes.length - 66000); offset -= 1) {
    if (view.getUint32(offset, true) === 0x06054b50) {
      eocd = offset;
      break;
    }
  }
  if (eocd < 0) throw new Error("zip end record not found");
  const entries = view.getUint16(eocd + 10, true);
  let cursor = view.getUint32(eocd + 16, true);
  const files = new Map<string, ArrayBuffer>();

  for (let index = 0; index < entries; index += 1) {
    if (view.getUint32(cursor, true) !== 0x02014b50) throw new Error("invalid zip directory");
    const flags = view.getUint16(cursor + 8, true);
    const method = view.getUint16(cursor + 10, true);
    const compressedSize = view.getUint32(cursor + 20, true);
    const nameLength = view.getUint16(cursor + 28, true);
    const extraLength = view.getUint16(cursor + 30, true);
    const commentLength = view.getUint16(cursor + 32, true);
    const localOffset = view.getUint32(cursor + 42, true);
    const name = normalizePackagePath(zipFileName(flags, bytes.slice(cursor + 46, cursor + 46 + nameLength)));
    cursor += 46 + nameLength + extraLength + commentLength;
    if (!name || name.endsWith("/")) continue;
    if (view.getUint32(localOffset, true) !== 0x04034b50) throw new Error("invalid zip local file");
    const localNameLength = view.getUint16(localOffset + 26, true);
    const localExtraLength = view.getUint16(localOffset + 28, true);
    const dataStart = localOffset + 30 + localNameLength + localExtraLength;
    const compressed = bytes.slice(dataStart, dataStart + compressedSize);
    if (method === 0) {
      files.set(name, compressed.slice().buffer);
    } else if (method === 8) {
      files.set(name, await inflateRaw(compressed));
    }
  }
  return files;
}

async function readUrdfPackage(file: File): Promise<UrdfPackage> {
  return readUrdfPackageBuffer(file.name, await file.arrayBuffer(), async () => file.text());
}

async function readUrdfPackageBuffer(fileName: string, buffer: ArrayBuffer, readText?: () => Promise<string>): Promise<UrdfPackage> {
  if (!fileName.toLowerCase().endsWith(".zip")) {
    const urdfText = readText ? await readText() : new TextDecoder("utf-8").decode(buffer);
    return {
      fileName,
      packageName: fileName.replace(/\.[^.]+$/, "") || "robot_model",
      urdfPath: fileName,
      urdfText,
      files: new Map([[fileName, new TextEncoder().encode(urdfText).buffer]]),
    };
  }

  const files = await readZipEntries(buffer);
  const urdfPaths = Array.from(files.keys()).filter((name) => name.toLowerCase().endsWith(".urdf"));
  const preferred = urdfPaths.find((name) => /\/urdf\/[^/]+\.urdf$/i.test(name) && !/\.bak|backup/i.test(name))
    ?? urdfPaths.find((name) => !/\.bak|backup/i.test(name))
    ?? urdfPaths[0];
  if (!preferred) throw new Error("zip does not contain urdf");
  const rootName = preferred.split("/")[0] || fileName.replace(/\.[^.]+$/, "");
  return {
    fileName,
    packageName: rootName,
    urdfPath: preferred,
    urdfText: new TextDecoder("utf-8").decode(files.get(preferred)),
    files,
  };
}

function resolvePackageAsset(packageFiles: Map<string, ArrayBuffer>, packageName: string, rawPath: string) {
  const normalized = normalizePackagePath(rawPath);
  const withoutProtocol = normalized.replace(/^package:\/\//, "");
  const candidates = [
    normalized,
    withoutProtocol,
    withoutProtocol.replace(new RegExp(`^${packageName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/`), ""),
    `${packageName}/${withoutProtocol}`,
  ].map(normalizePackagePath);
  for (const candidate of candidates) {
    const direct = packageFiles.get(candidate);
    if (direct) return direct;
    const suffix = candidate.split("/").slice(-2).join("/").toLowerCase();
    const found = Array.from(packageFiles.entries()).find(([name]) => name.toLowerCase().endsWith(suffix));
    if (found) return found[1];
  }
  return null;
}

function numericTuple(value: string | null | undefined, fallback: [number, number, number]): [number, number, number] {
  const parts = text(value, "").split(/\s+/).map((item) => Number(item));
  if (parts.length < 3 || parts.some((item) => !Number.isFinite(item))) return fallback;
  return [parts[0], parts[1], parts[2]];
}

function parseUrdfVisualMeshes(urdfText: string): UrdfVisualMesh[] {
  if (typeof DOMParser === "undefined") return [];
  const document = new DOMParser().parseFromString(urdfText, "text/xml");
  return Array.from(document.querySelectorAll("robot > link")).flatMap((link) => {
    const linkName = text(link.getAttribute("name"), "");
    if (!linkName) return [];
    const visualNodes = Array.from(link.children).filter((child) => child.nodeName.toLowerCase() === "visual") as Element[];
    return visualNodes.map((visual) => {
      const origin = Array.from(visual.children).find((child) => child.nodeName.toLowerCase() === "origin");
      const geometry = Array.from(visual.children).find((child) => child.nodeName.toLowerCase() === "geometry");
      const mesh = geometry ? Array.from(geometry.children).find((child) => child.nodeName.toLowerCase() === "mesh") : undefined;
      return {
        linkName,
        meshPath: text(mesh?.getAttribute("filename"), ""),
        xyz: numericTuple(origin?.getAttribute("xyz"), [0, 0, 0]),
        rpy: numericTuple(origin?.getAttribute("rpy"), [0, 0, 0]),
        scale: numericTuple(mesh?.getAttribute("scale"), [1, 1, 1]),
      };
    }).filter((item) => item.meshPath);
  });
}

function Arm3DOverview({
  deviceId,
  robotId,
  projectId,
  deviceModel,
  motors,
  robotRenderState,
  wiringChecks,
  safetyState,
}: {
  deviceId: string;
  robotId: string;
  projectId: string;
  deviceModel: AnyRecord;
  motors: AnyRecord[];
  robotRenderState: AnyRecord;
  wiringChecks: AnyRecord[];
  safetyState: string;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const cleanupRef = useRef<() => void>(() => {});
  const [focusMode, setFocusMode] = useState(false);
  const robotRef = useRef<AnyRecord | null>(null);
  const positions = useMemo(() => jointPositionsFromMotors(motors), [motors]);
  const jointValues = useMemo(() => jointValueMapFromMotors(motors), [motors]);
  const positionsRef = useRef(positions);
  const jointValuesRef = useRef(jointValues);
  const sceneDataRef = useRef({
    badWiringChecks: [] as AnyRecord[],
    motors: [] as AnyRecord[],
    renderJointNames: [] as string[],
    safetyState,
    sourceMotors: new Map<string, AnyRecord>(),
  });
  const [urdfText, setUrdfText] = useState("");
  const [urdfPackage, setUrdfPackage] = useState<UrdfPackage | null>(null);
  const [urdfName, setUrdfName] = useState("");
  const [urdfState, setUrdfState] = useState<"demo" | "loading" | "loaded" | "failed">("demo");
  const [modelSaveState, setModelSaveState] = useState<"idle" | "saving" | "saved" | "error" | "restored">("idle");
  const [urdfJoints, setUrdfJoints] = useState<JointDetail[]>([]);
  const [meshStats, setMeshStats] = useState({ loaded: 0, missing: 0 });
  const restoredModelRef = useRef("");
  const serverCalibrationsRef = useRef(new Map<string, JointCalibration>());
  const applyResolvedUrdfPackageRef = useRef<(modelPackage: UrdfPackage, fileForSave: File | null) => void>(() => {});
  const urdfJointNames = useMemo(() => urdfJoints.map((joint) => joint.name), [urdfJoints]);
  const jointRows = useMemo(() => movableJoints(urdfJoints).map((joint) => joint.name), [urdfJoints]);
  const sourceNames = useMemo(() => motorSourceNames(motors), [motors]);
  const sourceLabels = useMemo(
    () => Array.from(new Set(motors.map((motor) => text(motor.source_label, "电机状态")).filter(Boolean))),
    [motors],
  );
  const sourceMotors = useMemo(() => motorBySourceName(motors), [motors]);
  const renderRows = useMemo(() => renderJointRowsFromState(robotRenderState), [robotRenderState]);
  const renderJointNames = useMemo(() => renderRows.map((row) => row.name), [renderRows]);
  const staleRenderRows = renderRows.filter((row) => !row.fresh).length;
  const clampedRenderRows = renderRows.filter((row) => row.limitClamped).length;
  const badWiringChecks = useMemo(
    () => wiringChecks.filter((item) => ["missing", "fault", "stale", "not_wired"].includes(text(item.status, ""))),
    [wiringChecks],
  );
  const averageTemperature = (() => {
    const values = motors.map(motorTemperature).filter((value): value is number => value !== null);
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  })();
  const jointRowsKey = jointRows.join("\u0001");
  const sourceNamesKey = sourceNames.join("\u0001");
  const [calibrations, setCalibrations] = useState<JointCalibration[]>([]);
  const [freshnessNowMs, setFreshnessNowMs] = useState(0);
  const calibratedJointValues = useMemo(() => {
    const values = new Map<string, number>();
    calibrations.forEach((row) => {
      const value = calibratedJointValue(row, jointValues);
      if (value !== null) values.set(row.jointName, value);
    });
    jointValues.forEach((value, name) => {
      if (!values.has(name)) values.set(name, value);
    });
    return values;
  }, [calibrations, jointValues]);
  const matchedUrdfJoints = useMemo(
    () => (jointRows.length ? jointRows : urdfJointNames).filter((name) => calibratedJointValues.has(name)),
    [calibratedJointValues, jointRows, urdfJointNames],
  );
  const flowJointNames = useMemo(
    () => (jointRows.length ? jointRows : renderJointNames.length ? renderJointNames : urdfJointNames.length ? urdfJointNames : ARM_MODEL_JSON.joints),
    [jointRows, renderJointNames, urdfJointNames],
  );
  const flowRows = useMemo(
    () => jointFlowRows(flowJointNames, calibrations, jointValues, sourceMotors, freshnessNowMs),
    [calibrations, flowJointNames, freshnessNowMs, jointValues, sourceMotors],
  );
  const activeFlowRows = flowRows.filter((row) => row.status === "matched").length;
  const staleFlowRows = flowRows.filter((row) => row.status === "matched" && row.freshnessState === "stale").length;
  const isHistoricalPose = activeFlowRows > 0 && staleFlowRows === activeFlowRows;

  useEffect(() => {
    setFreshnessNowMs(Date.now());
    const timer = window.setInterval(() => setFreshnessNowMs(Date.now()), 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    positionsRef.current = positions;
    jointValuesRef.current = calibratedJointValues;
    sceneDataRef.current = {
      badWiringChecks,
      motors,
      renderJointNames,
      safetyState,
      sourceMotors,
    };
  }, [badWiringChecks, calibratedJointValues, motors, positions, renderJointNames, safetyState, sourceMotors]);

  useEffect(() => {
    if (!jointRows.length) {
      setCalibrations([]);
      return;
    }
    setCalibrations((current) => {
      const saved = loadSavedCalibrations(urdfName);
      const previous = new Map<string, JointCalibration>();
      current.forEach((row) => previous.set(row.jointName, row));
      saved.forEach((row, jointName) => previous.set(jointName, row));
      serverCalibrationsRef.current.forEach((row, jointName) => previous.set(jointName, row));
      return defaultCalibrations(jointRows, sourceNames, previous);
    });
  }, [jointRows, jointRowsKey, sourceNames, sourceNamesKey, urdfName]);

  useEffect(() => {
    saveCalibrations(urdfName, calibrations);
  }, [calibrations, urdfName]);

  async function saveModelPackage(file: File, modelPackage: UrdfPackage, rows: JointCalibration[]) {
    if (!deviceId || !robotId || !projectId) return;
    setModelSaveState("saving");
    const form = new FormData();
    form.append("robot_id", robotId);
    form.append("project_id", projectId);
    form.append("file_name", file.name);
    form.append("package_name", modelPackage.packageName);
    form.append("urdf_path", modelPackage.urdfPath);
    form.append("joint_count", String(movableJoints(parseUrdfJoints(modelPackage.urdfText)).length));
    form.append("mesh_count", String(Array.from(modelPackage.files.keys()).filter((name) => /\.(stl|dae|obj|glb|gltf)$/i.test(name)).length));
    form.append("mapping_json", JSON.stringify(rows));
    form.append("file", file, file.name);
    try {
      const response = await fetch(`/api/proxy/rehab-arm/v1/devices/${encodeURIComponent(deviceId)}/model-package`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw new Error("model package upload failed");
      setModelSaveState("saved");
    } catch {
      setModelSaveState("error");
    }
  }

  function applyUrdfPackage(file: File, shouldSave: boolean) {
    setUrdfName(file.name);
    setUrdfState("loading");
    setUrdfJoints([]);
    setMeshStats({ loaded: 0, missing: 0 });
    readUrdfPackage(file)
      .then((modelPackage) => applyResolvedUrdfPackage(modelPackage, shouldSave ? file : null))
      .catch(() => {
        setUrdfText("");
        setUrdfPackage(null);
        setUrdfState("failed");
        setModelSaveState("error");
      });
  }
  function applyResolvedUrdfPackage(modelPackage: UrdfPackage, fileForSave: File | null) {
    const parsedJoints = parseUrdfJoints(modelPackage.urdfText);
    const rows = defaultCalibrations(movableJoints(parsedJoints).map((joint) => joint.name), sourceNames, serverCalibrationsRef.current);
    serverCalibrationsRef.current = new Map(rows.map((row) => [row.jointName, row]));
    setMeshStats({ loaded: 0, missing: 0 });
    setUrdfState("loading");
    setUrdfPackage(modelPackage);
    setUrdfJoints(parsedJoints);
    setUrdfName(modelPackage.fileName.endsWith(".zip") ? `${modelPackage.fileName} / ${modelPackage.urdfPath}` : modelPackage.fileName);
    setUrdfText(modelPackage.urdfText);
    if (fileForSave) void saveModelPackage(fileForSave, modelPackage, rows);
  }
  applyResolvedUrdfPackageRef.current = applyResolvedUrdfPackage;

  function handleUrdfFile(file: File | null) {
    if (!file) return;
    applyUrdfPackage(file, true);
  }

  useEffect(() => {
    if (!deviceId || urdfText) return;
    setModelSaveState("idle");
    const controller = new AbortController();
    async function restoreModelPackage() {
      try {
        let { modelUrl, fileName, packageName, urdfPath, sha256, mappingJson } = modelInfoFromRecord(deviceModel);
        if (!modelUrl) {
          const dashboardResponse = await fetch("/api/proxy/rehab-arm/v1/devices/dashboard", { cache: "no-store", signal: controller.signal });
          if (dashboardResponse.ok) {
            const dashboardPayload = await dashboardResponse.json();
            const device = asArray<AnyRecord>(record(dashboardPayload).data?.devices).find((item) => text(item.device_id, "") === deviceId);
            const fallback = modelInfoFromRecord(device?.device_model);
            modelUrl = fallback.modelUrl;
            fileName = fallback.fileName;
            packageName = fallback.packageName;
            urdfPath = fallback.urdfPath;
            sha256 = fallback.sha256;
            mappingJson = fallback.mappingJson;
          }
        }
        const restoreKey = `${deviceId}:${modelUrl}:${sha256}`;
        if (!modelUrl || restoredModelRef.current === restoreKey) return;
        serverCalibrationsRef.current = calibrationMapFromJson(mappingJson);
        let modelPackage: UrdfPackage;
        const response = await fetch(keyframeSrc(modelUrl, ""), { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("model package fetch failed");
        const buffer = await response.arrayBuffer();
        modelPackage = await readUrdfPackageBuffer(fileName, buffer);
        restoredModelRef.current = restoreKey;
        applyResolvedUrdfPackageRef.current(modelPackage, null);
        setModelSaveState("restored");
      } catch {
        if (!controller.signal.aborted) setModelSaveState("error");
      }
    }
    void restoreModelPackage();
    return () => controller.abort();
  }, [deviceId, deviceModel, urdfText]);

  function updateCalibration(jointName: string, patch: Partial<JointCalibration>) {
    setCalibrations((rows) => rows.map((row) => row.jointName === jointName ? { ...row, ...patch } : row));
  }

  function resetCalibration() {
    setCalibrations(defaultCalibrations(jointRows, sourceNames));
  }

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    let disposed = false;
    let cleanup = () => {};

    async function renderArm() {
      const THREE = await import("three");
      const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
      if (disposed || !mountRef.current) return;
      const target = mountRef.current;
      const width = Math.max(360, target.clientWidth || 720);
      const height = Math.max(320, target.clientHeight || 420);
      cleanupRef.current();
      robotRef.current = null;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x020a0d);

      const narrowViewport = width <= 520;
      const cameraTarget = new THREE.Vector3(0.08, 0.0, 0.16);
      const camera = new THREE.PerspectiveCamera(narrowViewport ? 48 : 34, width / height, 0.01, 100);
      camera.position.set(
        narrowViewport ? 2.25 : 1.85,
        narrowViewport ? -2.7 : -2.25,
        narrowViewport ? 1.62 : 1.35,
      );
      camera.lookAt(cameraTarget);

      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(width, height);
      renderer.domElement.setAttribute("aria-label", "机械臂 Three.js 总览");
      renderer.domElement.setAttribute("title", "拖拽旋转视角，滚轮缩放，右键平移");
      target.replaceChildren(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.enableRotate = true;
      controls.enableZoom = true;
      controls.enablePan = true;
      controls.minDistance = 0.7;
      controls.maxDistance = 4.2;
      controls.maxPolarAngle = Math.PI * 0.92;
      controls.target.copy(cameraTarget);
      controls.update();

      scene.add(new THREE.HemisphereLight(0xecffff, 0x0a272f, 2.2));
      const keyLight = new THREE.DirectionalLight(0xffffff, 1.2);
      keyLight.position.set(1.4, -1.8, 2.2);
      scene.add(keyLight);
      const fillLight = new THREE.DirectionalLight(0x75f7dd, 0.7);
      fillLight.position.set(-1.2, 1.1, 1.4);
      scene.add(fillLight);

      const grid = new THREE.GridHelper(1.5, 12, 0x214a48, 0x10272b);
      scene.add(grid);

      function statusForLink(jointName: string, index: number) {
        const aliases = [jointName, `motor_${index + 1}`, String(index + 1)].filter(Boolean).map((item) => item.toLowerCase());
        const matched = sceneDataRef.current.badWiringChecks.find((item) => {
          const haystack = [
            item.channel,
            item.joint_name,
            item.jointName,
            item.motor_id,
            item.motorId,
            item.evidence,
          ].map((value) => text(value, "").toLowerCase()).join(" ");
          return aliases.some((alias) => alias && haystack.includes(alias));
        });
        return text(matched?.status, "");
      }

      function temperatureColor(temp: number | null, fallback: number) {
        if (temp === null) return fallback;
        if (temp >= 62) return 0xe25a45;
        if (temp >= 48) return 0xd99b2b;
        if (temp >= 38) return 0xc7c95a;
        return 0x42c6b2;
      }

      function linkMaterial(baseColor: number, jointName: string, index: number, temp: number | null) {
        const status = statusForLink(jointName, index);
        if (status === "fault" || status === "missing") {
          return new THREE.MeshStandardMaterial({ color: 0xa2aab0, roughness: 0.82, metalness: 0.02, transparent: true, opacity: 0.58 });
        }
        if (status === "stale" || status === "not_wired") {
          return new THREE.MeshStandardMaterial({ color: 0xc99a3c, roughness: 0.78, metalness: 0.04, transparent: true, opacity: 0.72 });
        }
        return new THREE.MeshStandardMaterial({ color: temperatureColor(temp, baseColor), roughness: 0.58, metalness: 0.1 });
      }

      function materialForUrdfMesh(child: AnyRecord, index: number) {
        const names: string[] = [];
        let cursor: AnyRecord | null = child;
        while (cursor && names.length < 6) {
          const name = text(cursor.name, "");
          if (name) names.push(name);
          cursor = cursor.parent ?? null;
        }
        const jointName =
          names.find((name) => sceneDataRef.current.sourceMotors.has(name))
          ?? names.find((name) => sceneDataRef.current.renderJointNames.includes(name))
          ?? names.find((name) => ARM_MODEL_JSON.joints.includes(name))
          ?? names[0]
          ?? `mesh_${index + 1}`;
        const motor = sceneDataRef.current.sourceMotors.get(jointName) ?? sceneDataRef.current.motors[index] ?? {};
        return linkMaterial(0x8ef0c7, jointName, index, motorTemperature(motor));
      }

      function addDemoArmModel() {
        const group = new THREE.Group();
        group.position.y = 0.1;
        group.scale.setScalar(0.78);
        scene.add(group);
        const jointMaterial = new THREE.MeshStandardMaterial({
          color: sceneDataRef.current.safetyState === "ok" ? 0x78e6aa : sceneDataRef.current.safetyState === "fault" ? 0xff705e : 0xffd166,
          roughness: 0.44,
          metalness: 0.18,
        });
        let cursor = new THREE.Vector3(0, 0, 0);
        const currentPositions = positionsRef.current;
        let yaw = currentPositions[1] || 0;
        let pitch = currentPositions[0] || 0.3;
        ARM_MODEL_JSON.links.slice(1).forEach((link, index) => {
          const jointName = ARM_MODEL_JSON.joints[index] ?? link.name;
          const motor = sceneDataRef.current.motors[index] ?? sceneDataRef.current.sourceMotors.get(jointName) ?? {};
          const length = link.length;
          if (index === 2) pitch -= currentPositions[3] || 0.4;
          if (index === 3) yaw += currentPositions[4] || 0;
          const dir = new THREE.Vector3(
            Math.cos(pitch) * Math.cos(yaw),
            Math.sin(pitch),
            Math.cos(pitch) * Math.sin(yaw),
          ).normalize();
          const mid = cursor.clone().add(dir.clone().multiplyScalar(length / 2));
          const mesh = new THREE.Mesh(new THREE.CylinderGeometry(link.radius, link.radius, length, 24), linkMaterial(link.color, jointName, index, motorTemperature(motor)));
          mesh.position.copy(mid);
          mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
          group.add(mesh);
          const joint = new THREE.Mesh(new THREE.SphereGeometry(link.radius * 1.65, 24, 16), jointMaterial);
          joint.position.copy(cursor);
          group.add(joint);
          cursor = cursor.add(dir.multiplyScalar(length));
        });
        const end = new THREE.Mesh(new THREE.SphereGeometry(0.045, 24, 16), jointMaterial);
        end.position.copy(cursor);
        group.add(end);
      }

      function applyJointValues(robot: AnyRecord) {
        jointValuesRef.current.forEach((value, name) => {
          if (robot.joints?.[name]) {
            robot.setJointValue?.(name, value);
          }
        });
      }

      async function addUrdfOrPlaceholder() {
        if (!urdfText) {
          addDemoArmModel();
          setUrdfState("demo");
          return;
        }
        try {
          const [{ default: URDFLoader }, { STLLoader }] = await Promise.all([
            import("urdf-loader"),
            import("three/examples/jsm/loaders/STLLoader.js"),
          ]);
          if (disposed) return;
          const loader = new URDFLoader();
          (loader as AnyRecord).packages = (targetPackage: string) => targetPackage;
          (loader as AnyRecord).parseVisual = false;
          (loader as AnyRecord).parseCollision = false;
          let loadedMeshes = 0;
          let missingMeshes = 0;
          const robot = loader.parse(urdfText) as AnyRecord;
          if (disposed) return;
          robotRef.current = robot;
          robot.rotation.x = -Math.PI / 2;
          if (urdfPackage) {
            parseUrdfVisualMeshes(urdfText).forEach((visual) => {
              const link = robot.links?.[visual.linkName];
              const asset = resolvePackageAsset(urdfPackage.files, urdfPackage.packageName, visual.meshPath);
              if (!link || !asset || !visual.meshPath.toLowerCase().endsWith(".stl")) {
                missingMeshes += 1;
                return;
              }
              try {
                const geometry = new STLLoader().parse(asset);
                const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0x8ef0c7, roughness: 0.62, metalness: 0.08 }));
                const visualGroup = new THREE.Group();
                visualGroup.position.set(visual.xyz[0], visual.xyz[1], visual.xyz[2]);
                visualGroup.rotation.set(visual.rpy[0], visual.rpy[1], visual.rpy[2], "ZYX");
                visualGroup.scale.set(visual.scale[0], visual.scale[1], visual.scale[2]);
                visualGroup.add(mesh);
                link.add(visualGroup);
                loadedMeshes += 1;
              } catch {
                missingMeshes += 1;
              }
            });
          }
          setMeshStats({ loaded: loadedMeshes, missing: missingMeshes });
          let meshIndex = 0;
          robot.traverse?.((child: AnyRecord) => {
            if (child.isMesh) {
              child.castShadow = false;
              child.receiveShadow = false;
              child.material = materialForUrdfMesh(child, meshIndex);
              meshIndex += 1;
            }
          });
          const box = new THREE.Box3().setFromObject(robot as any);
          const size = box.getSize(new THREE.Vector3());
          const center = box.getCenter(new THREE.Vector3());
          const maxDim = Math.max(size.x, size.y, size.z, 0.001);
          robot.position.sub(center);
          robot.scale.setScalar(1.1 / maxDim);
          applyJointValues(robot);
          scene.add(robot as any);
          setUrdfState("loaded");
        } catch {
          addDemoArmModel();
          setUrdfState("failed");
        }
      }

      void addUrdfOrPlaceholder();

      let frame = 0;
      const animate = () => {
        if (disposed) return;
        frame = window.requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
      };
      animate();

      const resize = () => {
        if (!mountRef.current) return;
        const nextWidth = Math.max(320, mountRef.current.clientWidth || width);
        const nextHeight = Math.max(300, mountRef.current.clientHeight || height);
        camera.aspect = nextWidth / nextHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(nextWidth, nextHeight);
      };
      window.addEventListener("resize", resize);
      cleanup = () => {
        window.removeEventListener("resize", resize);
        window.cancelAnimationFrame(frame);
        controls.dispose();
        renderer.dispose();
        scene.clear();
        if (target.contains(renderer.domElement)) target.removeChild(renderer.domElement);
      };
      cleanupRef.current = cleanup;
    }

    void renderArm();
    return () => {
      disposed = true;
      cleanup();
    };
  }, [urdfPackage, urdfText]);

  useEffect(() => {
    const robot = robotRef.current;
    if (!robot) return;
    calibratedJointValues.forEach((value, name) => {
      if (robot.joints?.[name]) {
        robot.setJointValue?.(name, value);
      }
    });
  }, [calibratedJointValues, urdfJointNames]);

  const modelStateText =
    urdfState === "loaded"
      ? `已导入 ${urdfName || "URDF"}`
      : urdfState === "loading"
        ? "正在导入 URDF"
      : urdfState === "failed"
          ? "URDF 未能完整加载，正在显示默认可替换模型"
          : "默认可替换模型，可导入真实 URDF";

  return (
    <section className={styles.armOverviewPanel} data-focus={focusMode ? "true" : "false"} aria-label="机械臂 3D 总览">
      <div className={styles.panelHead}>
        <div>
          <span>URDF / Three.js 机械臂</span>
          <strong>{modelStateText}</strong>
        </div>
        <div className={styles.panelActions}>
          <small>{renderRows.length || matchedUrdfJoints.length || positions.length} 个关节正在匹配角度</small>
          <button type="button" onClick={() => setFocusMode((value) => !value)}>
            {focusMode ? "退出专注" : "展开 3D"}
          </button>
        </div>
      </div>
      <div ref={mountRef} className={styles.armCanvas} />
      <div className={styles.armTelemetryStrip} aria-label="机械臂渲染状态摘要">
        <article data-state={staleRenderRows ? "stale" : clampedRenderRows ? "clamped" : "fresh"}>
          <span>渲染反馈</span>
          <strong>{renderRows.length ? staleRenderRows ? `${staleRenderRows} 个未知` : "关节新鲜" : "等待状态"}</strong>
          <p>{renderRows.length ? clampedRenderRows ? `${clampedRenderRows} 个限位夹紧/仿真夹紧。` : "fresh=false 不用 0 位姿伪装。": "等待 robot_render_state_v1。"}</p>
        </article>
        <article data-state={badWiringChecks.length ? "stale" : averageTemperature !== null && averageTemperature >= 48 ? "clamped" : "fresh"}>
          <span>接线 / 温度</span>
          <strong>{badWiringChecks.length ? `${badWiringChecks.length} 路异常` : averageTemperature === null ? "等待温度" : numberText(averageTemperature, " ℃")}</strong>
          <p>颜色表达温度，link 透明/灰色表达接线异常。</p>
        </article>
        <article data-state={urdfJoints.length ? "fresh" : "stale"}>
          <span>模型匹配</span>
          <strong>{urdfJoints.length ? `${matchedUrdfJoints.length}/${jointRows.length || urdfJoints.length}` : "可替换模型"}</strong>
          <p>
            {urdfJoints.length
              ? `${sourceLabels.join(" + ") || "角度状态"} 套用到同名关节；mesh ${meshStats.loaded}/${meshStats.loaded + meshStats.missing}。`
              : "真实设备模型和人体 GLTF/VRM 后续由用户上传接入。"}
          </p>
        </article>
      </div>
      <details className={flowStyles.jointFlowPanel} aria-label="关节状态流">
        <summary className={flowStyles.jointFlowHead}>
          <div>
            <span>关节状态流</span>
            <strong>{activeFlowRows}/{flowRows.length} 个关节有{isHistoricalPose ? "历史" : "实时"}角度</strong>
          </div>
          <small>{sourceNames.length ? `${sourceNames.length} 个只读角度来源` : "等待 NanoPi 或仿真主机上报"}</small>
        </summary>
        {staleFlowRows ? (
          <div className={flowStyles.historyNotice} data-state={isHistoricalPose ? "historical" : "mixed"} data-testid="rehab-historical-pose-notice">
            <div>
              <strong>{isHistoricalPose ? "历史姿态预览" : "部分角度可能过期"}</strong>
              <span>
                {isHistoricalPose
                  ? "3D 模型正在使用最近一次上传的角度，只适合回看和校准核对。"
                  : `${staleFlowRows} 个关节长时间未更新，请核对采集状态。`}
              </span>
            </div>
            <Link href={`/projects/${projectId}/robotics?tab=terminal&device=${encodeURIComponent(deviceId)}`} prefetch={false}>
              打开设备数据工作台采集
            </Link>
          </div>
        ) : null}
        <div className={flowStyles.jointFlowGrid} data-testid="rehab-joint-state-flow">
          {flowRows.slice(0, 8).map((row) => (
            <article key={row.jointName} data-state={row.status}>
              <div>
                <strong>{row.jointName}</strong>
                <span>{row.sourceName || "待匹配"} · {row.sourceLabel}</span>
                <em data-freshness={row.freshnessState}>{row.freshnessText}</em>
              </div>
              <dl>
                <div>
                  <dt>原始</dt>
                  <dd>{row.rawValue === null ? "-" : numberText(row.rawValue, row.sourceName && calibrations.find((item) => item.jointName === row.jointName)?.unit === "deg" ? " deg" : " rad")}</dd>
                </div>
                <div>
                  <dt>套用</dt>
                  <dd>{row.calibratedValue === null ? "未套用" : numberText(row.calibratedValue, " rad")}</dd>
                </div>
                <div>
                  <dt>速度</dt>
                  <dd>{row.velocity === null ? "-" : numberText(row.velocity, " rad/s")}</dd>
                </div>
                <div>
                  <dt>温度</dt>
                  <dd>{row.temperature === null ? "-" : numberText(row.temperature, " ℃")}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
        <p className={flowStyles.jointFlowHint}>这些数值只用于网页预览和校准核对，不会写回 NanoPi、M33 或电机驱动。</p>
      </details>
      <details className={styles.urdfToolbar}>
        <summary>模型包 / URDF 导入</summary>
        <label>
          <span>导入本机模型包</span>
          <input
            type="file"
            accept=".zip,.urdf,.xml"
            data-testid="rehab-urdf-file"
            onChange={(event) => handleUrdfFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <p>支持 URDF zip 包或单个 URDF。页面优先用 robot_render_state_v1 的 joint_names/positions 驱动同名关节，只读预览，不下发任何运动控制。</p>
      </details>
      {urdfJoints.length ? (
        <details className={styles.poseMappingPanel}>
          <summary>
            <span>姿态映射</span>
            <button type="button" onClick={(event) => { event.preventDefault(); resetCalibration(); }}>重置映射</button>
          </summary>
          <div className={styles.mappingHint}>
            <strong>{sourceNames.length ? `${sourceNames.length} 个角度来源可选` : "等待角度状态上传"}</strong>
            <span>只影响当前浏览器预览：单位、方向和零点偏移用于把上报角度对齐到 URDF 关节。</span>
          </div>
          <div className={styles.mappingGrid} data-testid="rehab-pose-mapping">
            {calibrations.map((row) => {
              const preview = calibratedJointValue(row, jointValues);
              return (
                <div key={row.jointName} className={styles.mappingRow}>
                  <strong>{row.jointName}</strong>
                  <label>
                    <span>角度来源</span>
                    <select
                      value={row.sourceName}
                      onChange={(event) => updateCalibration(row.jointName, { sourceName: event.target.value })}
                    >
                      <option value="">待匹配</option>
                      {sourceNames.map((source) => <option key={source} value={source}>{source}</option>)}
                    </select>
                  </label>
                  <label>
                    <span>单位</span>
                    <select
                      value={row.unit}
                      onChange={(event) => updateCalibration(row.jointName, { unit: event.target.value === "deg" ? "deg" : "rad" })}
                    >
                      <option value="rad">弧度</option>
                      <option value="deg">角度</option>
                    </select>
                  </label>
                  <label>
                    <span>方向</span>
                    <select
                      value={String(row.direction)}
                      onChange={(event) => updateCalibration(row.jointName, { direction: event.target.value === "-1" ? -1 : 1 })}
                    >
                      <option value="1">正向</option>
                      <option value="-1">反向</option>
                    </select>
                  </label>
                  <label>
                    <span>零点偏移 rad</span>
                    <input
                      type="number"
                      step="0.01"
                      value={Number.isFinite(row.offsetRad) ? row.offsetRad : 0}
                      onChange={(event) => updateCalibration(row.jointName, { offsetRad: Number(event.target.value) || 0 })}
                    />
                  </label>
                  <small>{preview === null ? "未匹配" : `预览 ${numberText(preview, " rad")}`}</small>
                </div>
              );
            })}
          </div>
        </details>
      ) : null}
      <details className={styles.armLegendPanel}>
        <summary>
          关节角度概览
          <small>{(urdfJointNames.length ? urdfJointNames : renderJointNames.length ? renderJointNames : ARM_MODEL_JSON.joints).length} 个关节</small>
        </summary>
        <div className={styles.armLegend}>
          {(urdfJointNames.length ? urdfJointNames : renderJointNames.length ? renderJointNames : ARM_MODEL_JSON.joints).slice(0, 10).map((name, index) => (
            <span
              key={name}
              data-state={renderRows.find((row) => row.name === name)?.fresh === false ? "unknown" : renderRows.find((row) => row.name === name)?.limitClamped ? "clamped" : "fresh"}
            >
              {name}: {numberText(calibratedJointValues.get(name) ?? positions[index], " rad")}
            </span>
          ))}
        </div>
      </details>
    </section>
  );
}

function HumanMuscleOverview({ sensorPayload }: { sensorPayload: AnyRecord }) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const rows = useMemo(() => muscleRowsFromSensor(sensorPayload), [sensorPayload]);
  const rowsRef = useRef(rows);
  const activeRows = rows.filter((row) => row.status === "active").length;
  const averageFatigue = (() => {
    const values = rows.map((row) => row.fatigue).filter((value): value is number => value !== null);
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  })();

  useEffect(() => {
    rowsRef.current = rows;
  }, [rows]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    let disposed = false;
    let cleanup = () => {};

    async function renderHuman() {
      const THREE = await import("three");
      const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
      if (disposed || !mountRef.current) return;
      const target = mountRef.current;
      const width = Math.max(280, target.clientWidth || 420);
      const height = Math.max(320, target.clientHeight || 420);
      target.replaceChildren();

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x050807);
      const camera = new THREE.PerspectiveCamera(36, width / height, 0.01, 100);
      camera.position.set(0.8, -1.55, 1.08);
      camera.lookAt(0, 0, 0.35);

      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(width, height);
      renderer.domElement.setAttribute("aria-label", "人体肌电 Three.js 总览");
      target.appendChild(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.enablePan = false;
      controls.minDistance = 0.85;
      controls.maxDistance = 2.8;
      controls.target.set(0, 0, 0.34);
      controls.update();

      scene.add(new THREE.HemisphereLight(0xf7fff4, 0x13201c, 2.4));
      const key = new THREE.DirectionalLight(0xffffff, 1.2);
      key.position.set(0.7, -1.2, 1.8);
      scene.add(key);
      const rim = new THREE.DirectionalLight(0x39c6ac, 1);
      rim.position.set(-1.4, 1.1, 1.1);
      scene.add(rim);

      const grid = new THREE.GridHelper(1.15, 10, 0x29413a, 0x14231f);
      grid.position.z = -0.02;
      scene.add(grid);

      function colorFor(row: MuscleSignalRow) {
        if (row.value === null) return 0x59625e;
        if (row.value >= 0.68) return 0xe15c45;
        if (row.value >= 0.34) return 0xd6a33a;
        return 0x48c2a7;
      }

      function material(row: MuscleSignalRow, opacity = 0.82) {
        return new THREE.MeshStandardMaterial({
          color: colorFor(row),
          roughness: 0.62,
          metalness: 0.04,
          transparent: true,
          opacity: row.value === null ? 0.35 : opacity,
        });
      }

      const body = new THREE.Group();
      body.rotation.z = -0.04;
      scene.add(body);

      const skin = new THREE.MeshStandardMaterial({ color: 0xd9c8b4, roughness: 0.76, metalness: 0.02, transparent: true, opacity: 0.86 });
      const neutral = new THREE.MeshStandardMaterial({ color: 0x53645f, roughness: 0.82, metalness: 0.02, transparent: true, opacity: 0.55 });
      const rowByKey = new Map(rowsRef.current.map((row) => [row.key, row]));
      const unknownRow: MuscleSignalRow = { key: "unknown", label: "未知", value: null, fatigue: null, status: "unknown" };

      const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.18, 0.48, 10, 24), neutral);
      torso.position.set(0, 0, 0.42);
      body.add(torso);

      const head = new THREE.Mesh(new THREE.SphereGeometry(0.095, 28, 18), skin);
      head.position.set(0, 0, 0.82);
      body.add(head);

      const deltoid = rowByKey.get("deltoid") ?? unknownRow;
      const biceps = rowByKey.get("biceps") ?? unknownRow;
      const forearm = rowByKey.get("forearm") ?? unknownRow;
      const trapezius = rowByKey.get("trapezius") ?? unknownRow;
      [
        { row: deltoid, x: -0.24, y: 0, z: 0.62, sx: 0.07, sy: 0.045, sz: 0.09 },
        { row: deltoid, x: 0.24, y: 0, z: 0.62, sx: 0.07, sy: 0.045, sz: 0.09 },
        { row: trapezius, x: -0.09, y: -0.012, z: 0.69, sx: 0.075, sy: 0.04, sz: 0.055 },
        { row: trapezius, x: 0.09, y: -0.012, z: 0.69, sx: 0.075, sy: 0.04, sz: 0.055 },
      ].forEach((part) => {
        const patch = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 12), material(part.row));
        patch.scale.set(part.sx, part.sy, part.sz);
        patch.position.set(part.x, part.y, part.z);
        body.add(patch);
      });

      [
        { row: biceps, x: -0.32, y: 0, z: 0.43, rz: -0.25, length: 0.28, radius: 0.036 },
        { row: biceps, x: 0.32, y: 0, z: 0.43, rz: 0.25, length: 0.28, radius: 0.036 },
        { row: forearm, x: -0.44, y: 0, z: 0.23, rz: -0.08, length: 0.26, radius: 0.03 },
        { row: forearm, x: 0.44, y: 0, z: 0.23, rz: 0.08, length: 0.26, radius: 0.03 },
      ].forEach((part) => {
        const limb = new THREE.Mesh(new THREE.CapsuleGeometry(part.radius, part.length, 8, 16), material(part.row));
        limb.rotation.z = part.rz;
        limb.position.set(part.x, part.y, part.z);
        body.add(limb);
      });

      const fatigue = averageFatigue === null ? null : averageFatigue;
      const fatigueMat = new THREE.MeshStandardMaterial({
        color: fatigue === null ? 0x59625e : fatigue >= 0.72 ? 0xe15c45 : fatigue >= 0.42 ? 0xd6a33a : 0x48c2a7,
        roughness: 0.62,
        metalness: 0.02,
        transparent: true,
        opacity: fatigue === null ? 0.22 : 0.72,
      });
      const fatigueRing = new THREE.Mesh(new THREE.TorusGeometry(0.215, 0.006, 8, 72), fatigueMat);
      fatigueRing.rotation.x = Math.PI / 2;
      fatigueRing.position.set(0, 0, 0.5);
      body.add(fatigueRing);

      let frame = 0;
      const animate = () => {
        if (disposed) return;
        frame = window.requestAnimationFrame(animate);
        body.rotation.y = Math.sin(Date.now() / 3200) * 0.045;
        controls.update();
        renderer.render(scene, camera);
      };
      animate();

      const resize = () => {
        if (!mountRef.current) return;
        const nextWidth = Math.max(260, mountRef.current.clientWidth || width);
        const nextHeight = Math.max(300, mountRef.current.clientHeight || height);
        camera.aspect = nextWidth / nextHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(nextWidth, nextHeight);
      };
      window.addEventListener("resize", resize);
      cleanup = () => {
        window.removeEventListener("resize", resize);
        window.cancelAnimationFrame(frame);
        controls.dispose();
        renderer.dispose();
        scene.clear();
        if (target.contains(renderer.domElement)) target.removeChild(renderer.domElement);
      };
    }

    void renderHuman();
    return () => {
      disposed = true;
      cleanup();
    };
  }, [averageFatigue]);

  return (
    <section className={styles.humanPanel} aria-label="人体肌电模型">
      <div className={styles.panelHead}>
        <div>
          <span>人体肌电 / Three.js</span>
          <strong>{activeRows ? `${activeRows} 组肌肉高参与` : "等待肌电小模型"}</strong>
        </div>
        <small>{averageFatigue === null ? "疲劳 unknown" : `平均疲劳 ${Math.round(averageFatigue * 100)}%`}</small>
      </div>
      <div ref={mountRef} className={styles.humanCanvas} />
      <div className={styles.muscleGrid} aria-label="肌电通道状态">
        {rows.map((row) => (
          <article key={row.key} data-state={row.status}>
            <span>{row.label}</span>
            <strong>{row.value === null ? "unknown" : `${Math.round(row.value * 100)}%`}</strong>
            <p>fatigue {row.fatigue === null ? "unknown" : `${Math.round(row.fatigue * 100)}%`}</p>
          </article>
        ))}
      </div>
      <details className={styles.nestedDrawer}>
        <summary>
          人体模型替换
          <small>GLTF / VRM 承载位</small>
        </summary>
        <p>当前场景只做可替换的肌电语义预览；后续可接入开源人体 GLTF/VRM，并把肌肉区域映射到同一套 EMG/fatigue 字段。</p>
      </details>
    </section>
  );
}

function ControlStationOnboarding({ projectId }: { projectId: string }) {
  const steps = [
    { title: "1. NanoPi 上传只读状态", detail: "先接入设备代理，上传在线状态、电机状态、传感器摘要和关键帧。" },
    { title: "2. M33/M55 上报安全摘要", detail: "显示急停、限位、模式、心跳和模型输出；网页不覆盖安全链路。" },
    { title: "3. 进入设备数据工作台", detail: "采集、标注、图表实验都回到通用设备数据工作台完成。" },
  ];
  return (
    <section className={styles.onboardingPanel} aria-label="专项设备总控台接入引导">
      <div className={styles.onboardingCopy}>
        <span>等待首台设备</span>
        <strong>这里是康复机械臂只读总控，不是真机遥控器</strong>
        <p>真实接入前，先按下面三步把 NanoPi、M33/M55、App/现场数据和仿真证据串起来。平台负责看状态、沉淀证据和发起协作，不直接发运动指令。</p>
        <Link href={`/projects/${projectId}/robotics`} prefetch={false}>去设备数据工作台准备采集窗口</Link>
      </div>
      <div className={styles.onboardingSteps}>
        {steps.map((step) => (
          <article key={step.title}>
            <strong>{step.title}</strong>
            <p>{step.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function RehabArmControlClient({ apiBaseUrl, dashboard, projectId, projectName }: Props) {
  const [liveDashboard, setLiveDashboard] = useState(() => filterDashboardForProject(dashboard, projectId));
  const [pollState, setPollState] = useState<"idle" | "ok" | "error">("idle");
  const [lastLiveUpdate, setLastLiveUpdate] = useState<number | null>(null);
  const [estopRequestState, setEstopRequestState] = useState<"idle" | "sent" | "accepted" | "pending_m33_ack" | "m33_ack" | "error">("idle");
  const [relayPrompt, setRelayPrompt] = useState("");
  const [relayState, setRelayState] = useState<"idle" | "sending" | "ok" | "error">("idle");
  const [relayError, setRelayError] = useState("");
  const [lastRelayResponse, setLastRelayResponse] = useState<AnyRecord | null>(null);
  const [relayConfig, setRelayConfig] = useState<RelayConfig>({
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    model: "",
    external_enabled: true,
    api_key_configured: false,
    presets: DEFAULT_RELAY_PRESETS,
  });
  const [relayConfigKey, setRelayConfigKey] = useState("");
  const [relayConfigState, setRelayConfigState] = useState<"idle" | "loading" | "saving" | "saved" | "error">("idle");
  const [relayConfigError, setRelayConfigError] = useState("");
  const [relayExportState, setRelayExportState] = useState<"idle" | "creating" | "created" | "copied" | "error">("idle");
  const [relayExportError, setRelayExportError] = useState("");
  const [relayExportToken, setRelayExportToken] = useState("");
  const [relayExportExpiresAt, setRelayExportExpiresAt] = useState<number | null>(null);
  const [relayTokenTtlSeconds, setRelayTokenTtlSeconds] = useState(7 * 24 * 60 * 60);
  const [externalApiBaseUrl, setExternalApiBaseUrl] = useState(() => apiBaseUrl.replace(/\/$/, ""));
  const devices = useMemo(
    () => [...liveDashboard.devices].sort((a, b) => Number(b.last_upload_ts_unix ?? 0) - Number(a.last_upload_ts_unix ?? 0)),
    [liveDashboard.devices],
  );
  const [selectedDeviceId, setSelectedDeviceId] = useState(devices[0]?.device_id ?? "");
  const deviceIndexById = useMemo(
    () => new Map(devices.map((device, index) => [device.device_id, index])),
    [devices],
  );
  const selected = useMemo(
    () => devices.find((device) => device.device_id === selectedDeviceId) ?? devices[0] ?? null,
    [devices, selectedDeviceId],
  );

  useEffect(() => {
    setLiveDashboard(filterDashboardForProject(dashboard, projectId));
  }, [dashboard, projectId]);

  useEffect(() => {
    setExternalApiBaseUrl(publicApiBaseUrl(apiBaseUrl));
  }, [apiBaseUrl]);

  useEffect(() => {
    if (selectedDeviceId && devices.some((device) => device.device_id === selectedDeviceId)) return;
    setSelectedDeviceId(devices[0]?.device_id ?? "");
  }, [devices, selectedDeviceId]);

  useEffect(() => {
    let disposed = false;

    async function refreshDashboard() {
      try {
        const response = await fetch("/api/proxy/rehab-arm/v1/devices/dashboard", { cache: "no-store" });
        if (!response.ok) throw new Error("dashboard fetch failed");
        const payload = await response.json();
        if (disposed) return;
        setLiveDashboard(filterDashboardForProject(payload, projectId));
        setPollState("ok");
        setLastLiveUpdate(Date.now());
      } catch {
        if (!disposed) setPollState("error");
      }
    }

    void refreshDashboard();
    const timer = window.setInterval(refreshDashboard, 4000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [projectId]);

  useEffect(() => {
    let disposed = false;

    async function loadRelayConfig() {
      setRelayConfigState("loading");
      try {
        const response = await fetch(`/api/proxy/rehab-arm/v1/projects/${encodeURIComponent(projectId)}/model-relay/config`, { cache: "no-store" });
        if (!response.ok) throw new Error("model relay config fetch failed");
        const payload = await response.json();
        const data = record(record(payload).data);
        if (disposed) return;
        const presets = asArray<RelayProviderPreset>(data.presets).length ? asArray<RelayProviderPreset>(data.presets) : DEFAULT_RELAY_PRESETS;
        setRelayConfig({
          provider: text(data.provider, "openai"),
          base_url: text(data.base_url, "https://api.openai.com/v1"),
          model: text(data.model, ""),
          external_enabled: data.external_enabled !== false,
          api_key_configured: data.api_key_configured === true,
          presets,
        });
        setRelayConfigState("idle");
      } catch {
        if (!disposed) {
          setRelayConfigState("error");
          setRelayConfigError("无法读取服务端模型中转配置");
        }
      }
    }

    void loadRelayConfig();
    return () => {
      disposed = true;
    };
  }, [projectId]);

  const selectedIndex = selected ? deviceIndexById.get(selected.device_id) ?? 0 : 0;
  const roleSignals = useMemo(() => roleSignalsFromDevices(devices), [devices]);
  const keyframe = selected?.camera_keyframe ?? {};
  const keyframePayload = payloadOf(keyframe);
  const cameraStreamOffer = latestRelayPayload(selected, "camera_stream_offer");
  const robotRenderState = renderStateOfDevice(selected);
  const renderRows = renderJointRowsFromState(robotRenderState);
  const staleRenderCount = renderRows.filter((row) => !row.fresh).length;
  const clampedRenderCount = renderRows.filter((row) => row.limitClamped).length;
  const wiringHealth = record(selected?.wiring_health);
  const wiringChecks = asArray<AnyRecord>(wiringHealth.checks);
  const wiringBadCount = wiringChecks.filter((item) => ["missing", "fault", "stale"].includes(text(item.status, ""))).length;
  const motorPayload = payloadOf(selected?.motor_state);
  const sensorPayload = payloadOf(selected?.sensor_state);
  const safetyPayload = payloadOf(selected?.safety);
  const safetyStatus = record(selected?.safety_status);
  const voiceRelay = latestRelayPayload(selected, "voice_relay");
  const xiaozhiSession = latestRelayPayload(selected, "xiaozhi_session");
  const vlaCandidate = latestRelayPayload(selected, "vla_plan_candidate");
  const modelRelayRecord = record(selected?.model_relay_response);
  const modelRelayPayload = payloadOf(modelRelayRecord);
  const modelRelayResponse = lastRelayResponse ?? record(modelRelayPayload.relay_response);
  const modelRelayProvider = record(modelRelayResponse.provider);
  const modelRelaySuggestion = record(asArray<AnyRecord>(record(modelRelayResponse.suggestion).model_results)[0]);
  const estopAck = latestRelayPayload(selected, "estop_ack");
  const dataQuality = selected?.data_quality ?? {};
  const motors = asArray<AnyRecord>(motorPayload.motors);
  const xiaozhiEvents = liveDashboard.recent_events
    .filter((event) => {
      if (selected?.device_id && text(event.device_id, "") !== selected.device_id) return false;
      return ["xiaozhi_ws_input", "xiaozhi_ws_reply"].includes(text(event.record_type, ""));
    })
    .slice(0, 6);
  const modelRelayEvents = liveDashboard.recent_events
    .filter((event) => {
      if (selected?.device_id && text(event.device_id, "") !== selected.device_id) return false;
      return ["model_relay_request", "model_relay_response"].includes(text(event.record_type, ""));
    })
    .slice(0, 6);
  const poseSamples = useMemo(
    () => [
      ...poseSamplesFromRenderState(robotRenderState, timestampUnix(selected?.command_center_snapshot)),
      ...poseSamplesFromTelemetry(motorPayload, sensorPayload),
    ],
    [motorPayload, robotRenderState, selected?.command_center_snapshot, sensorPayload],
  );
  const imageUrl = text(keyframe.image_url, "");
  const absoluteImageUrl = keyframeSrc(imageUrl, apiBaseUrl);
  const motionAllowed = Boolean(safetyStatus.motion_allowed ?? safetyPayload.motion_allowed ?? selected?.motion_allowed);
  const currentSafetyState = safetyStatus.state ?? safetyPayload.state ?? selected?.safety_state;
  const qualityReady = Boolean(dataQuality.annotation_ready);
  const roleCards = [
    { key: "nanopi", title: "NanoPi / Linux", subtitle: "本地 ROS 与设备接入节点", ...latestRoleStatus(roleSignals, "nanopi") },
    { key: "m33", title: "M33 / M55", subtitle: "安全裁决与轻量推理", ...latestRoleStatus(roleSignals, "m33") },
    { key: "app", title: "App / 现场", subtitle: "近场参数、患者信息、急停", ...latestRoleStatus(roleSignals, "app") },
    { key: "sim", title: "仿真主机", subtitle: "MuJoCo / RViz / 路径验证", ...latestRoleStatus(roleSignals, "sim") },
  ];

  useEffect(() => {
    if (estopAck.m33_ack === true) {
      setEstopRequestState("m33_ack");
    } else if (estopAck.accepted_by_gateway === true) {
      setEstopRequestState("pending_m33_ack");
    }
  }, [estopAck.accepted_by_gateway, estopAck.m33_ack]);

  async function requestEstop() {
    if (!selected?.device_id) return;
    setEstopRequestState("sent");
    try {
      const requestId = `estop_${Date.now()}`;
      const response = await fetch(`/api/proxy/rehab-arm/v1/devices/${encodeURIComponent(selected.device_id)}/estop`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          schema_version: "estop_request_v1",
          request_id: requestId,
          robot_id: selected.robot_id || "rehab-arm-alpha",
          device_id: selected.device_id,
          project_id: projectId,
          source: "command_center",
          operator_id: "command_center_operator",
          reason: "operator_pressed_estop",
          requested_action: "disable_motor_output",
          control_boundary: "estop_request_requires_m33_ack",
        }),
      });
      if (!response.ok) throw new Error("estop request failed");
      const payload = await response.json();
      const ack = record(record(payload).data);
      setEstopRequestState(ack.m33_ack ? "m33_ack" : ack.accepted_by_gateway ? "pending_m33_ack" : "accepted");
    } catch {
      setEstopRequestState("error");
    }
  }

  function updateRelayProvider(providerId: string) {
    const preset = relayConfig.presets.find((item) => item.id === providerId);
    setRelayConfig((current) => ({
      ...current,
      provider: providerId,
      base_url: preset?.base_url || current.base_url,
    }));
  }

  async function saveRelayConfig() {
    setRelayConfigState("saving");
    setRelayConfigError("");
    try {
      const response = await fetch(`/api/proxy/rehab-arm/v1/projects/${encodeURIComponent(projectId)}/model-relay/config`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          provider: relayConfig.provider,
          base_url: relayConfig.base_url,
          model: relayConfig.model,
          api_key: relayConfigKey.trim() || undefined,
          external_enabled: relayConfig.external_enabled,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(text(record(payload).detail ?? record(payload).error?.message, "保存模型厂商失败"));
      const data = record(record(payload).data);
      const presets = asArray<RelayProviderPreset>(data.presets).length ? asArray<RelayProviderPreset>(data.presets) : relayConfig.presets;
      setRelayConfig({
        provider: text(data.provider, relayConfig.provider),
        base_url: text(data.base_url, relayConfig.base_url),
        model: text(data.model, relayConfig.model),
        external_enabled: data.external_enabled !== false,
        api_key_configured: data.api_key_configured === true,
        presets,
      });
      setRelayConfigKey("");
      setRelayConfigState("saved");
    } catch (error) {
      setRelayConfigState("error");
      setRelayConfigError(error instanceof Error ? error.message : "保存模型厂商失败");
    }
  }

  async function createRelayInvokeToken() {
    if (!selected?.device_id || relayExportState === "creating") return;
    setRelayExportState("creating");
    setRelayExportError("");
    try {
      const response = await fetch(
        `/api/proxy/rehab-arm/v1/projects/${encodeURIComponent(projectId)}/devices/${encodeURIComponent(selected.device_id)}/model/relay-token`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            ttl_seconds: relayTokenTtlSeconds,
            label: `relay-${selected.device_id}`,
          }),
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(text(record(payload).detail ?? record(payload).error?.message, "生成调用令牌失败"));
      const data = record(record(payload).data);
      setRelayExportToken(text(data.token, ""));
      setRelayExportExpiresAt(Number(data.expires_at_unix || 0) || null);
      setRelayExportState("created");
    } catch (error) {
      setRelayExportState("error");
      setRelayExportError(error instanceof Error ? error.message : "生成调用令牌失败");
    }
  }

  async function copyRelayInvokeToken() {
    if (!relayExportToken) return;
    try {
      await navigator.clipboard.writeText(relayExportToken);
      setRelayExportState("copied");
    } catch {
      setRelayExportState("created");
    }
  }

  async function requestModelRelay() {
    if (!selected?.device_id || relayState === "sending") return;
    setRelayState("sending");
    setRelayError("");
    try {
      const prompt = relayPrompt.trim() || "请基于当前机械臂只读遥测、安全状态、接线状态、语音/视觉/肌电摘要，生成高层康复建议和 dry-run 候选说明。";
      const response = await fetch(
        `/api/proxy/rehab-arm/v1/projects/${encodeURIComponent(projectId)}/devices/${encodeURIComponent(selected.device_id)}/model/relay`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            schema_version: "model_relay_request_v1",
            robot_id: selected.robot_id || "rehab-arm-alpha",
            device_id: selected.device_id,
            project_id: projectId,
            input_type: "vla_context",
            prompt,
            context_refs: {
              safety_state: stateText(currentSafetyState),
              motion_allowed: motionAllowed,
              wiring_overall: text(wiringHealth.overall, "unknown"),
              stale_joint_count: staleRenderCount,
              fresh_joint_count: Math.max(0, renderRows.length - staleRenderCount),
              camera_scene_summary: text(keyframePayload.scene_summary, ""),
              sensor_source: publicSourceLabel(sensorPayload.source, ""),
            },
            requested_outputs: ["high_level_task", "dry_run_joint_trajectory_candidate", "model_state_suggestion"],
            forbidden_outputs: [
              "can_frame",
              "motor_current",
              "motor_torque",
              "raw_motor_position",
              "raw_motor_velocity",
              "m33_safety_override",
              "direct_motor_command",
            ],
            operator_id: "command_center_operator",
            control_boundary: "model_relay_request_only_not_motion_permission",
          }),
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(text(record(payload).detail ?? record(payload).error?.message, "模型中转请求失败"));
      const data = record(record(payload).data);
      setLastRelayResponse(data);
      setRelayState("ok");
    } catch (error) {
      setRelayError(error instanceof Error ? error.message : "模型中转请求失败");
      setRelayState("error");
    }
  }

  const estopLabel =
    estopRequestState === "sent"
      ? "请求已发送"
      : estopRequestState === "accepted"
        ? "网关已接收"
        : estopRequestState === "pending_m33_ack"
          ? "等待 M33 确认"
          : estopRequestState === "m33_ack"
            ? "M33 已确认 / 急停生效"
            : estopRequestState === "error"
              ? "请求失败"
              : "可发送请求";
  const relayInvokeUrl = selected?.device_id
    ? `${externalApiBaseUrl}/api/rehab-arm/v1/projects/${projectId}/devices/${selected.device_id}/model/relay`
    : "";
  const wsBaseUrl = externalApiBaseUrl.replace(/^http:\/\//i, "ws://").replace(/^https:\/\//i, "wss://");
  const xiaozhiWsUrl = selected?.device_id
    ? `${wsBaseUrl}/api/rehab-arm/v1/projects/${encodeURIComponent(projectId)}/devices/${encodeURIComponent(selected.device_id)}/xiaozhi/ws?robot_id=${encodeURIComponent(selected.robot_id || "rehab-arm-alpha")}`
    : "";
  const xiaozhiLatestReply = xiaozhiEvents.find((event) => text(event.record_type, "") === "xiaozhi_ws_reply");
  const xiaozhiReplyPayload = payloadOf(xiaozhiLatestReply);
  const xiaozhiAudioFrames = xiaozhiEvents.filter((event) => text(payloadOf(event).event, "") === "audio_frame").length;
  const xiaozhiVisibleEvents = xiaozhiEvents.slice(0, 3);
  const xiaozhiUiState = text(
    xiaozhiSession.ui_state
      ?? xiaozhiReplyPayload.ui_state
      ?? (xiaozhiEvents.length ? "thinking" : (selected ? "offline" : "idle")),
    "offline",
  );
  const languageGate = record(
    xiaozhiReplyPayload.vla_language_gate
      ?? xiaozhiSession.vla_language_gate
      ?? modelRelayResponse.vla_language_gate
      ?? record(modelRelayResponse.vla_language_context).classification,
  );
  const relayBoundaryText = text(modelRelayResponse.control_boundary, "model_relay_only_not_motion_permission");
  const relayProviderText = modelRelayProvider.configured === true ? "服务端 provider 已配置" : "等待服务端 provider";
  const relayProviderPreset = relayConfig.presets.find((item) => item.id === relayConfig.provider);
  const relayCurlExample = selected?.device_id
    ? [
      `curl -X POST '${relayInvokeUrl}' \\`,
      `  -H 'Authorization: Bearer ${relayExportToken || "rehab-relay.v1..."}' \\`,
      "  -H 'Content-Type: application/json' \\",
      "  -d '{\"schema_version\":\"model_relay_request_v1\",\"robot_id\":\"rehab-arm-alpha\",\"input_type\":\"vla_context\",\"prompt\":\"请根据当前语音和遥测生成高层康复建议\",\"requested_outputs\":[\"high_level_task\",\"dry_run_joint_trajectory_candidate\"],\"control_boundary\":\"model_relay_request_only_not_motion_permission\"}'",
    ].join("\n")
    : "";
  const xiaozhiHelloExample = [
    "{\"type\":\"hello\",\"version\":3,\"features\":{\"mcp\":true},\"transport\":\"websocket\",",
    "\"audio_params\":{\"format\":\"opus\",\"sample_rate\":16000,\"channels\":1,\"frame_duration\":60}}",
  ].join("");
  const forbiddenRelayOutputs = [
    "can_frame",
    "motor_current",
    "motor_torque",
    "raw_motor_position",
    "raw_motor_velocity",
    "m33_safety_override",
    "direct_motor_command",
  ];
  const visionSummary = text(
    keyframePayload.scene_summary ?? keyframePayload.detection_summary ?? keyframePayload.vla_context,
    absoluteImageUrl ? "已接收摄像头关键帧，等待视觉摘要" : "等待 camera_keyframe_v1",
  );
  const languageSummary = text(
    xiaozhiSession.transcript ?? xiaozhiReplyPayload.transcript ?? voiceRelay.transcript ?? record(voiceRelay.intent).text,
    xiaozhiSession.event ? xiaozhiEventLabel(xiaozhiSession.event) : "等待 XiaoZhi listen/audio",
  );
  const actionCandidate = record(vlaCandidate.candidate);
  const actionSummary = text(
    modelRelaySuggestion.detail ?? modelRelayResponse.summary ?? actionCandidate.summary ?? actionCandidate.type,
    "等待 dry-run 动作候选",
  );

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          <Link href={`/projects/${projectId}`} className={styles.backLink}>← 主页面</Link>
          <Link href={`/projects/${projectId}/robotics`} className={styles.backLink} prefetch={false}>设备数据工作台</Link>
          <Link href={`/projects/${projectId}/model-relay-lab`} className={styles.backLink} prefetch={false}>模型练习场</Link>
          <div className={styles.title}>
            <strong>{projectName}</strong>
            <small>康复机械臂专项总控 · 只读状态 / 安全边界 / 数据质量</small>
          </div>
        </div>
        <div className={styles.topbarRight}>
          <span className={styles.kpi}>设备 {devices.length}</span>
          <span className={styles.kpi}>在线 {roleSignals.onlineDevices}</span>
          <span className={styles.kpi}>M33 裁决 {liveDashboard.safety_boundary.m33_final_authority ? "开启" : "未声明"}</span>
          <span className={styles.kpi}>
            {pollState === "error" ? "实时刷新异常" : lastLiveUpdate ? `已同步 ${formatClock(lastLiveUpdate)}` : "准备同步"}
          </span>
          <Link href={`/projects/${projectId}/rehab-arm-control`} className={styles.refreshLink}>刷新状态</Link>
        </div>
      </header>

      <div className={styles.body}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarHeader}>
            <input className={styles.search} readOnly value="设备索引" aria-label="设备索引" />
            <p className={styles.searchHint}>选择设备后查看最新状态。这里不提供真实运动控制。</p>
          </div>
          <ul className={styles.deviceList} aria-label="康复机械臂设备列表">
            {devices.map((device, index) => {
              const active = selected?.device_id === device.device_id;
              return (
                <li key={device.device_id}>
                  <button
                    type="button"
                    className={`${styles.deviceRow} ${active ? styles.deviceRowActive : ""}`}
                    data-state={stateLabel(device.safety_state)}
                    onClick={() => setSelectedDeviceId(device.device_id)}
                  >
                    <span className={styles.dot} data-online={device.online_state} />
                    <span className={styles.deviceMain}>
                      <strong>{publicDeviceName(device, index)}</strong>
                      <small>{publicDeviceCode(device, index)}</small>
                    </span>
                    <span className={styles.deviceState}>{stateText(device.safety_state)}</span>
                    <small className={styles.deviceTime}>最近上传：{formatTime(device.last_upload_ts_unix)}</small>
                  </button>
                </li>
              );
            })}
            {!devices.length ? (
              <li>
                <div className={styles.emptyDeviceRow}>
                  <strong>等待 NanoPi 接入</strong>
                  <small>机械臂设备注册并上传只读状态后，会出现在这里。</small>
                </div>
              </li>
            ) : null}
          </ul>
        </aside>

        <section className={styles.workspace}>
          <div className={styles.workbenchHeader}>
            <div>
              <span>当前设备</span>
              <h1>{publicDeviceName(selected, selectedIndex)}</h1>
              <p>{selected ? publicDeviceCode(selected, selectedIndex) : "NanoPi 注册后会出现在左侧设备索引中"}</p>
            </div>
            <div className={styles.compactStats}>
              <article data-tone={selected?.online_state === "online" ? "ok" : "idle"}>
                <span>在线</span>
                <strong>{selected?.online_state === "online" ? "在线" : "离线"}</strong>
              </article>
              <article data-tone={stateLabel(currentSafetyState)}>
                <span>安全</span>
                <strong>{stateText(currentSafetyState)}</strong>
              </article>
              <article data-tone={motionAllowed ? "ok" : "limited"}>
                <span>M33 允许运动</span>
                <strong>{motionAllowed ? "允许" : "不允许"}</strong>
              </article>
              <article data-tone={qualityReady ? "ok" : "idle"}>
                <span>数据</span>
                <strong>{qualityReadyText(qualityReady)}</strong>
              </article>
            </div>
          </div>

          <section className={styles.boundaryBar}>
            <strong>只读总览</strong>
            <p>服务器和网页只展示状态、图像、质量门和高层任务草案；不发 CAN、电流、力矩、速度、角度或 M33 覆盖。</p>
          </section>

          <section className={styles.vlaCommandStrip} aria-label="VLA 感知语言动作链路">
            <article data-stage="v">
              <span>V · camera/image</span>
              <strong>{text(keyframePayload.camera_id, absoluteImageUrl ? "关键帧已接入" : "等待图像")}</strong>
              <p>{visionSummary}</p>
              <small>{text(cameraStreamOffer.control_boundary, "camera_preview_only_not_motion_permission")}</small>
            </article>
            <article data-stage="l">
              <span>L · voice/language</span>
              <strong>{vlaGateLabel(languageGate)}</strong>
              <p>{languageSummary}</p>
              <small>{text(xiaozhiSession.control_boundary ?? xiaozhiReplyPayload.control_boundary ?? voiceRelay.control_boundary, "voice_only_not_motion_permission")}</small>
            </article>
            <article data-stage="a">
              <span>A · next action</span>
              <strong>{text(actionCandidate.type, relayState === "ok" ? "高层建议已生成" : "dry-run 候选")}</strong>
              <p>{actionSummary}</p>
              <small>{text(vlaCandidate.control_boundary ?? relayBoundaryText, "vla_candidate_only_not_motion_permission")}</small>
            </article>
          </section>

          <div className={styles.primaryGrid}>
            <div className={styles.sceneColumn}>
              <Arm3DOverview
                deviceId={text(selected?.device_id, "")}
                robotId={text(selected?.robot_id, "")}
                projectId={projectId}
                deviceModel={record(selected?.device_model)}
                motors={poseSamples}
                robotRenderState={robotRenderState}
                wiringChecks={wiringChecks}
                safetyState={stateLabel(currentSafetyState)}
              />
              <HumanMuscleOverview sensorPayload={sensorPayload} />
            </div>

            <aside className={styles.sideStack}>
              <section className={styles.safetyPanel} data-state={stateLabel(currentSafetyState)}>
                <span>安全状态</span>
                <strong>{stateText(currentSafetyState)}</strong>
                <p>motion_allowed 只读：{motionAllowed ? "true" : "false"}；模式：{publicStateValue(safetyStatus.control_mode ?? safetyPayload.control_mode ?? safetyPayload.m33_mode)}；心跳：{text(safetyStatus.heartbeat_age_ms ?? safetyPayload.heartbeat_age_ms, "-")} ms；来源：{publicSourceLabel(safetyStatus.source ?? safetyPayload.source, "M33")}。</p>
              </section>
              <section className={styles.xiaozhiPanel}>
                <div className={styles.panelMiniHeader}>
                  <span>XiaoZhi / M55 WebSocket</span>
                  <strong>{xiaozhiUiStateLabel(xiaozhiUiState)}</strong>
                </div>
                <div className={styles.xiaozhiStateRow} data-tone={xiaozhiUiStateTone(xiaozhiUiState)}>
                  <span className={styles.xiaozhiStateBadge}>{xiaozhiUiStateLabel(xiaozhiUiState)}</span>
                  <p>{xiaozhiUiStateHint(xiaozhiUiState)}</p>
                </div>
                <div className={styles.runtimeStrip} aria-label="XiaoZhi 运行摘要">
                  <article>
                    <span>分类</span>
                    <strong>{xiaozhiKindLabel(xiaozhiSession.kind ?? xiaozhiReplyPayload.kind)}</strong>
                  </article>
                  <article>
                    <span>VLA-L</span>
                    <strong>{vlaGateLabel(languageGate)}</strong>
                  </article>
                  <article>
                    <span>音频</span>
                    <strong>{numberText(xiaozhiSession.audio_bytes ?? xiaozhiReplyPayload.audio_bytes, " bytes")}</strong>
                  </article>
                </div>
                <div className={styles.xiaozhiEndpoint}>
                  <small>Endpoint</small>
                  <code>{xiaozhiWsUrl || "选择设备后生成 ws endpoint"}</code>
                </div>
                <div className={styles.xiaozhiSessionMeta} aria-label="XiaoZhi 会话状态">
                  <span>session</span>
                  <code>{text(xiaozhiSession.session_id ?? xiaozhiReplyPayload.session_id, "未建立")}</code>
                  <span>error</span>
                  <code>{text(xiaozhiSession.last_error ?? xiaozhiReplyPayload.last_error, "无")}</code>
                </div>
                <div className={styles.boundaryNote}>
                  <strong>语音只进 VLA 语言输入</strong>
                  <p>{text(xiaozhiSession.control_boundary ?? xiaozhiReplyPayload.control_boundary, "xiaozhi_voice_relay_only_not_motion_permission")}</p>
                </div>
                <details className={styles.streamDisclosure}>
                  <summary>
                    输入输出流
                    <small>{xiaozhiEvents.length ? `最近 ${xiaozhiEvents.length} 条` : "等待 M55"}</small>
                  </summary>
                  <div className={styles.ioStream} aria-label="XiaoZhi 输入输出流">
                    {xiaozhiVisibleEvents.map((event, index) => {
                      const eventPayload = payloadOf(event);
                      const detail = text(
                        eventPayload.reply ?? eventPayload.transcript ?? eventPayload.language_context ?? eventPayload.event,
                        xiaozhiEventLabel(eventPayload.event ?? event.record_type),
                      );
                      return (
                        <article key={`${text(event.record_type, "xiaozhi")}-${index}`}>
                          <div>
                            <span>{xiaozhiDirectionLabel(event.record_type)}</span>
                            <strong>{xiaozhiEventLabel(eventPayload.event ?? event.record_type)}</strong>
                          </div>
                          <p>{detail}</p>
                          <small>{formatTime(event.ts_unix)} · {xiaozhiKindLabel(eventPayload.kind)} · {vlaGateLabel(eventPayload.vla_language_gate)} · {text(eventPayload.control_boundary, "只读输入输出")}</small>
                        </article>
                      );
                    })}
                    {!xiaozhiEvents.length ? (
                      <p className={styles.emptyStream}>M55 完成 hello、listen 或音频帧后，这里会显示平台收到的输入和返回的 chat / listen stop。</p>
                    ) : null}
                  </div>
                </details>
              </section>
              <section className={styles.estopPanel} data-state={estopRequestState}>
                <span>急停请求</span>
                <strong>{estopLabel}</strong>
                <p>只有 estop_ack_v1 且 m33_ack=true 后，界面才显示“急停已执行”。HTTP 成功只代表请求进入本地安全路径。</p>
                <button type="button" disabled={!selected || estopRequestState === "sent"} onClick={requestEstop}>发起急停请求</button>
              </section>
              <section className={styles.relayPanel} data-state={relayState}>
                <div className={styles.panelMiniHeader}>
                  <span>模型中转</span>
                  <strong>{relayState === "sending" ? "请求中" : relayProviderText}</strong>
                </div>
                <div className={styles.relayStationGrid} aria-label="模型中转站状态">
                  <article>
                    <span>Provider</span>
                    <strong>{relayProviderPreset?.label || relayConfig.provider}</strong>
                    <p>{relayConfig.model || "未选择模型"}</p>
                  </article>
                  <article>
                    <span>外部调用</span>
                    <strong>{relayConfig.external_enabled && relayConfig.api_key_configured ? "启用" : "降级"}</strong>
                    <p>{relayConfig.api_key_configured ? "密钥仅服务端保存" : "未配置 API key"}</p>
                  </article>
                  <article>
                    <span>设备令牌</span>
                    <strong>{relayExportToken ? "已生成" : "未生成"}</strong>
                    <p>{relayExportExpiresAt ? `到期 ${formatTime(relayExportExpiresAt)}` : "用于 NanoPi/M55 调用"}</p>
                  </article>
                </div>
                <div className={styles.boundaryNote}>
                  <strong>{relayBoundaryText}</strong>
                  <p>{modelRelayProvider.external_call_ok === true ? "外部模型调用通过安全过滤" : text(modelRelayProvider.external_call_error, "未调用外部模型或安全降级")}</p>
                </div>
                <details className={styles.relayConfigPanel} open>
                  <summary>
                    调用试验台
                    <small>{relayState === "ok" ? "最近调用成功" : "高层建议 / dry-run 候选"}</small>
                  </summary>
                  <textarea
                    value={relayPrompt}
                    onChange={(event) => setRelayPrompt(event.target.value)}
                    rows={3}
                    placeholder="输入语音/视觉/肌电摘要后的高层问题；服务端只返回建议和 dry-run 候选。"
                    aria-label="模型中转提示"
                  />
                  <button type="button" disabled={!selected || relayState === "sending"} onClick={requestModelRelay}>
                    生成高层建议
                  </button>
                  {relayError ? <small className={styles.inlineError}>{relayError}</small> : null}
                  {modelRelaySuggestion.detail || modelRelayResponse.summary ? (
                    <small className={styles.relayResult}>{text(modelRelaySuggestion.detail, text(modelRelayResponse.summary, ""))}</small>
                  ) : null}
                </details>
                <details className={styles.relayConfigPanel}>
                  <summary>
                    接入地址和示例
                    <small>HTTP / XiaoZhi WS</small>
                  </summary>
                  <div className={styles.endpointList}>
                    <label>
                      <span>HTTP model relay</span>
                      <code>{relayInvokeUrl || "选择设备后生成 HTTP endpoint"}</code>
                    </label>
                    <label>
                      <span>XiaoZhi WebSocket</span>
                      <code>{xiaozhiWsUrl || "选择设备后生成 WebSocket endpoint"}</code>
                    </label>
                    <label>
                      <span>XiaoZhi hello</span>
                      <code>{xiaozhiHelloExample}</code>
                    </label>
                  </div>
                  <pre className={styles.codeExample}>{relayCurlExample}</pre>
                </details>
                <details className={styles.relayConfigPanel}>
                  <summary>
                    厂商和密钥
                    <small>{relayConfig.api_key_configured ? "密钥已在服务器保存" : "未配置密钥"}</small>
                  </summary>
                  <label>
                    <span>厂商</span>
                    <select value={relayConfig.provider} onChange={(event) => updateRelayProvider(event.target.value)}>
                      {relayConfig.presets.map((preset) => (
                        <option key={preset.id} value={preset.id}>{preset.label}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Base URL</span>
                    <input
                      value={relayConfig.base_url}
                      onChange={(event) => setRelayConfig((current) => ({ ...current, base_url: event.target.value }))}
                      placeholder="https://api.example.com/v1"
                    />
                  </label>
                  <label>
                    <span>模型</span>
                    <input
                      value={relayConfig.model}
                      onChange={(event) => setRelayConfig((current) => ({ ...current, model: event.target.value }))}
                      placeholder={relayConfig.presets.find((item) => item.id === relayConfig.provider)?.model_hint || "model id"}
                    />
                  </label>
                  <label>
                    <span>API key</span>
                    <input
                      type="password"
                      value={relayConfigKey}
                      onChange={(event) => setRelayConfigKey(event.target.value)}
                      placeholder={relayConfig.api_key_configured ? "留空则继续使用服务器已保存密钥" : "只保存到服务器，不返回浏览器"}
                      autoComplete="off"
                    />
                  </label>
                  <label className={styles.inlineToggle}>
                    <input
                      type="checkbox"
                      checked={relayConfig.external_enabled}
                      onChange={(event) => setRelayConfig((current) => ({ ...current, external_enabled: event.target.checked }))}
                    />
                    <span>启用外部模型调用</span>
                  </label>
                  <button type="button" disabled={relayConfigState === "saving"} onClick={saveRelayConfig}>
                    {relayConfigState === "saving" ? "保存中" : "保存厂商配置"}
                  </button>
                  {relayConfigState === "saved" ? <small className={styles.relayResult}>已保存到服务器环境配置；API key 不会返回给网页或设备。</small> : null}
                  {relayConfigError ? <small className={styles.inlineError}>{relayConfigError}</small> : null}
                </details>
                <details className={styles.relayConfigPanel}>
                  <summary>
                    设备调用令牌
                    <small>{relayExportToken ? "已生成" : "模型中转 / XiaoZhi"}</small>
                  </summary>
                  <p className={styles.tokenHint}>给 NanoPi、M55 或另一个 AI 使用的受限令牌；scope 只包含模型中转 invoke 和 XiaoZhi WebSocket，不是网页登录 token，不能改配置或访问项目资料。</p>
                  <label>
                    <span>有效期</span>
                    <select value={relayTokenTtlSeconds} onChange={(event) => setRelayTokenTtlSeconds(Number(event.target.value) || 7 * 24 * 60 * 60)}>
                      <option value={3600}>1 小时</option>
                      <option value={24 * 60 * 60}>1 天</option>
                      <option value={7 * 24 * 60 * 60}>7 天</option>
                      <option value={30 * 24 * 60 * 60}>30 天</option>
                    </select>
                  </label>
                  <button type="button" disabled={!selected || relayExportState === "creating"} onClick={createRelayInvokeToken}>
                    {relayExportState === "creating" ? "生成中" : "一键生成调用令牌"}
                  </button>
                  {relayExportToken ? (
                    <div className={styles.tokenBox}>
                      <label>
                        <span>Bearer token</span>
                        <textarea readOnly value={relayExportToken} rows={3} aria-label="模型中转调用令牌" />
                      </label>
                      <button type="button" onClick={copyRelayInvokeToken}>{relayExportState === "copied" ? "已复制" : "复制 token"}</button>
                      <small>
                        过期：{relayExportExpiresAt ? formatTime(relayExportExpiresAt) : "未知"}；HTTP 调用地址：
                        <code>{relayInvokeUrl}</code>
                        XiaoZhi WebSocket：
                        <code>{xiaozhiWsUrl}</code>
                      </small>
                    </div>
                  ) : null}
                  {relayExportError ? <small className={styles.inlineError}>{relayExportError}</small> : null}
                </details>
                <details className={styles.relayConfigPanel}>
                  <summary>
                    安全过滤和审计
                    <small>{modelRelayEvents.length ? `最近 ${modelRelayEvents.length} 条` : "等待调用"}</small>
                  </summary>
                  <div className={styles.forbiddenGrid}>
                    {forbiddenRelayOutputs.map((item) => <span key={item}>{item}</span>)}
                  </div>
                  <div className={styles.ioStream} aria-label="模型中转调用记录">
                    {modelRelayEvents.map((event, index) => {
                      const eventPayload = payloadOf(event);
                      const response = record(eventPayload.relay_response);
                      return (
                        <article key={`${text(event.record_type, "relay")}-${index}`}>
                          <div>
                            <span>{text(event.record_type, "") === "model_relay_response" ? "平台 → 设备" : "设备 → 平台"}</span>
                            <strong>{eventTitle(event)}</strong>
                          </div>
                          <p>{text(response.summary ?? eventPayload.prompt ?? response.control_boundary, "model relay event")}</p>
                          <small>{formatTime(event.ts_unix)} · {xiaozhiKindLabel(record(response.classification).type)} · {vlaGateLabel(response.vla_language_gate)} · {text(response.control_boundary ?? eventPayload.control_boundary, "model_relay_only_not_motion_permission")}</small>
                        </article>
                      );
                    })}
                    {!modelRelayEvents.length ? <p className={styles.emptyStream}>这里会显示模型中转请求、响应和安全降级结果；厂商 API key 不写入日志。</p> : null}
                  </div>
                </details>
              </section>
              <section className={styles.taskPanel}>
                <span>VLA / 训练 / 仿真入口</span>
                <strong>{qualityReady ? "可进入标注训练" : "先补齐 V/L/A 数据"}</strong>
                <p>V=摄像头关键帧，L=语音语言门控，A=高层 dry-run 候选。训练和 MuJoCo 结果都回到平台做证据，不直接变成真机运动。</p>
                <div className={styles.pipelineList}>
                  <article>
                    <span>1</span>
                    <p>NanoPi 上传 camera_keyframe_v1、sensor_state、robot_render_state。</p>
                  </article>
                  <article>
                    <span>2</span>
                    <p>模型中转分类 L：日常聊天不进 VLA，康复指令进入 VLA-L。</p>
                  </article>
                  <article>
                    <span>3</span>
                    <p>VLA-A 提交 vla_task_request_v1，只生成 dry-run 候选。</p>
                  </article>
                  <article>
                    <span>4</span>
                    <p>MuJoCo 上传 simulation_readiness，人工审核后才可能进入真机链路。</p>
                  </article>
                </div>
                <div className={styles.taskActions}>
                  <Link
                    href={`/projects/${projectId}/robotics?tab=dataset&device=${encodeURIComponent(selected?.device_id ?? "")}`}
                    prefetch={false}
                  >
                    数据/标注
                  </Link>
                  <Link href={`/projects/${projectId}/model-relay-lab`} prefetch={false}>
                    VLA-L 测试
                  </Link>
                </div>
              </section>
            </aside>
          </div>

          <div className={styles.summaryGrid}>
            <article>
              <span>数据批次</span>
              <strong>{publicBatchLabel(selected?.current_session)}</strong>
              <p>{selected?.latest_upload_status || "等待上传"}</p>
            </article>
            <article data-ready={!staleRenderCount ? "true" : "false"}>
              <span>渲染反馈</span>
              <strong>{renderRows.length ? `${renderRows.length - staleRenderCount}/${renderRows.length} 新鲜` : "等待 robot_render_state"}</strong>
              <p>{staleRenderCount ? `${staleRenderCount} 个关节未知，不用 0 位姿代替。` : clampedRenderCount ? `${clampedRenderCount} 个关节为限位夹紧/仿真夹紧。` : "Three.js 只读预览使用上报关节。"}</p>
            </article>
            <article data-ready={qualityReady ? "true" : "false"}>
              <span>数据质量</span>
              <strong>{qualityReadyText(qualityReady)}</strong>
              <p>{qualityReady ? "可进入标注和导出。" : asArray<string>(dataQuality.blocking_reasons).map(publicQualityReason).filter(Boolean).join("；") || "等待设备档案和质量摘要。"}</p>
            </article>
            <article>
              <span>传感器</span>
              <strong>{publicSourceLabel(sensorPayload.source)}</strong>
              <p>EMG、心率、IMU、疲劳评分和意图输出作为非实时数据资产展示。</p>
            </article>
            <article data-ready={!wiringBadCount ? "true" : "false"}>
              <span>接线检测</span>
              <strong>{wiringHealth.overall || "unknown"}</strong>
              <p>{wiringBadCount ? `${wiringBadCount} 路 missing/fault/stale，仅报警，不自动补偿控制。` : "未发现异常通道。"}</p>
            </article>
            <article>
              <span>VLA / 语音</span>
              <strong>{text(xiaozhiSession.kind, text(record(vlaCandidate.candidate).type, text(record(voiceRelay.intent).label, "等待建议")))}</strong>
              <p>
                {text(xiaozhiSession.event, "") ? `XiaoZhi ${text(xiaozhiSession.event)}；${numberText(xiaozhiSession.audio_bytes, " bytes")}。` : ""}
                {text(xiaozhiSession.control_boundary ?? vlaCandidate.control_boundary ?? voiceRelay.control_boundary, "AI/语音/VLA 输出必须带 control_boundary，不能作为运动许可。")}
              </p>
            </article>
          </div>

          <section className={styles.roleGrid} aria-label="康复机械臂四角色状态">
            {roleCards.map((role) => (
              <article key={role.key} data-ready={role.ready ? "true" : "false"}>
                <span>{role.title}</span>
                <strong>{role.value}</strong>
                <small>{role.subtitle}</small>
                <p>{role.detail}</p>
              </article>
            ))}
          </section>

          {!selected ? <ControlStationOnboarding projectId={projectId} /> : null}

          <details className={styles.drawerPanel}>
            <summary>摄像头关键帧</summary>
            <section className={styles.cameraPanel}>
              <div className={styles.panelHead}>
                <div>
                  <span>摄像头关键帧</span>
                  <strong>{text(keyframePayload.camera_id, "等待关键帧")}</strong>
                </div>
                <small>{formatTime(keyframePayload.frame_ts_unix ?? keyframe.ts_unix)}</small>
              </div>
              {absoluteImageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={absoluteImageUrl} alt="最新摄像头关键帧" className={styles.keyframe} />
              ) : (
                <div className={styles.emptyCamera}>
                  <strong>暂无图片</strong>
                  <p>NanoPi 上传低频 jpg/png/webp 关键帧后会显示在这里。</p>
                </div>
              )}
              <div className={styles.summaryGrid}>
                <article>
                  <span>检测摘要</span>
                  <p>{text(keyframePayload.detection_summary, "暂无目标检测摘要")}</p>
                </article>
                <article>
                  <span>场景摘要</span>
                  <p>{text(keyframePayload.scene_summary, "暂无场景摘要")}</p>
                </article>
                <article>
                  <span>VLA 上下文</span>
                  <p>{text(keyframePayload.vla_context, "预留高层任务上下文；不展示底层 CAN 或电机指令。")}</p>
                </article>
                <article>
                  <span>预览协商</span>
                  <p>
                    {text(cameraStreamOffer.transport, "camera_stream_offer_v1 待接入")}；
                    {text(cameraStreamOffer.max_fps, "15")} fps；
                    {text(cameraStreamOffer.control_boundary, "camera_preview_only_not_motion_permission")}
                  </p>
                </article>
              </div>
            </section>
          </details>

          <details className={styles.drawerPanel}>
            <summary>电机状态表 · {motors.length} 个电机</summary>
            <div className={styles.motorTable}>
              <div className={styles.tableHeader}>
                <span>电机</span><span>关节</span><span>位置</span><span>速度</span><span>电流</span><span>力矩</span><span>温度</span><span>错误</span><span>状态</span>
              </div>
              {motors.map((motor, index) => (
                <div key={`${text(motor.motor_id, "motor")}-${index}`} className={styles.tableRow} data-fault={motor.fault ? "true" : "false"}>
                  <span>{text(motor.motor_id, "-")}</span>
                  <span>{text(motor.joint_name, "-")}</span>
                  <span>{numberText(motor.position)}</span>
                  <span>{numberText(motor.velocity)}</span>
                  <span>{numberText(motor.current, " A")}</span>
                  <span>{numberText(motor.torque, " Nm")}</span>
                  <span>{numberText(motor.temperature, " C")}</span>
                  <span>{text(motor.error_code, "-")}</span>
                  <span>{motor.enabled ? "使能" : "未使能"} / {motor.fault ? "故障" : "正常"}</span>
                </div>
              ))}
              {!motors.length ? <p className={styles.emptyTable}>暂无电机状态上传。</p> : null}
            </div>
          </details>

          <details className={styles.drawerPanel}>
            <summary>设备档案和事件日志</summary>
            <div className={styles.detailGrid}>
              <section className={styles.identityPanel}>
                <span>设备档案</span>
                <dl>
                  <div><dt>设备编号</dt><dd>{publicDeviceCode(selected, selectedIndex)}</dd></div>
                  <div><dt>机器人名称</dt><dd>{publicDeviceName(selected, selectedIndex)}</dd></div>
                  <div><dt>当前数据批次</dt><dd>{publicBatchLabel(selected?.current_session, "无")}</dd></div>
                  <div><dt>上传状态</dt><dd>{selected?.latest_upload_status ?? "无记录"}</dd></div>
                  <div><dt>最近告警</dt><dd>{selected?.latest_error || "无"}</dd></div>
                </dl>
              </section>
              <section className={styles.eventLog}>
                <span>事件日志</span>
                {liveDashboard.recent_events.slice(0, 6).map((event, index) => (
                  <p key={`${text(event.record_type, "event")}-${index}`}>{eventTitle(event)} · {publicDeviceCode(devices.find((device) => device.device_id === event.device_id), index)} · {formatTime(event.ts_unix)}</p>
                ))}
                {!liveDashboard.recent_events.length ? <p>暂无上传事件。</p> : null}
              </section>
            </div>
          </details>
        </section>
      </div>
    </main>
  );
}
