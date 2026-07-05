"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
  stereo_vision_context?: AnyRecord;
  camera_stream_offer?: AnyRecord;
  command_center_snapshot?: AnyRecord;
  robot_render_state?: AnyRecord;
  wiring_health?: AnyRecord;
  safety_status?: AnyRecord;
  voice_relay?: AnyRecord;
  vla_plan_candidate?: AnyRecord;
  ik_candidate?: AnyRecord;
  simulation_readiness?: AnyRecord;
  estop_ack?: AnyRecord;
  motor_state?: AnyRecord;
  sensor_state?: AnyRecord;
  safety?: AnyRecord;
  sync_status?: AnyRecord;
  manifest?: AnyRecord;
  data_quality?: AnyRecord;
  device_model?: AnyRecord;
  model_relay_response?: AnyRecord;
  mode_maturity?: AnyRecord;
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

const DEMO_LANGUAGE_INPUTS = [
  "我口渴了，帮我拿水杯",
  "我要开始今天的训练",
  "我手臂没力了，开启一点助力",
  "检查一下摄像头和 CAN",
  "今天训练得怎么样，帮我总结一下",
  "你好，陪我聊一会儿",
];

type RehabWorkspaceModule =
  | "overview"
  | "vision"
  | "digital_twin"
  | "muscle_assist"
  | "ai_model"
  | "mode_router"
  | "training"
  | "data_hub"
  | "action_planner"
  | "diagnostics"
  | "logs";

const REHAB_WORKSPACE_MODULES: Array<{
  key: RehabWorkspaceModule;
  short: string;
  label: string;
  description: string;
}> = [
  { key: "overview", short: "CMD", label: "总控首页", description: "系统状态 / 当前模式 / VLA 总链路" },
  { key: "vision", short: "V", label: "VLA 视觉", description: "双目图传 / 目标末端 / 视觉锁定" },
  { key: "digital_twin", short: "3D", label: "URDF 仿真", description: "机械臂模型 / 关节 / MuJoCo shadow" },
  { key: "muscle_assist", short: "EMG", label: "肌电助力", description: "上肢肌肉 / EMG / 动作意图" },
  { key: "ai_model", short: "AI", label: "AI模型中转", description: "高层建议 / 模型配置 / 受限调用令牌" },
  { key: "mode_router", short: "L", label: "模式调度", description: "小智语义分类 / 资源路由" },
  { key: "training", short: "TRN", label: "模型训练场", description: "数据标注 / 训练计划 / APP / M33 BLE 预留" },
  { key: "data_hub", short: "DATA", label: "数据资产", description: "采集批次 / 标注入口 / 训练回流" },
  { key: "action_planner", short: "A", label: "动作规划", description: "dry-run / 闭环逼近 / 安全门" },
  { key: "diagnostics", short: "IO", label: "设备诊断", description: "NanoPi / CAN / M33 / 模型中转" },
  { key: "logs", short: "LOG", label: "日志回放", description: "语音 / 视觉 / 规划 / 审计证据" },
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

async function copyTextToClipboard(value: string) {
  const content = String(value ?? "");
  if (!content.trim()) return false;
  try {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(content);
      return true;
    }
  } catch {
    // Cloud previews and embedded pages can expose the API but reject writes.
  }
  try {
    const area = document.createElement("textarea");
    area.value = content;
    area.setAttribute("readonly", "true");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    area.style.top = "0";
    document.body.appendChild(area);
    area.focus();
    area.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(area);
    return copied;
  } catch {
    return false;
  }
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

function timestampUnixFromRows(...values: unknown[]): number | null {
  for (const value of values) {
    const direct = Number(value);
    if (Number.isFinite(direct) && direct > 0) return direct;
    const parsed = timestampUnix(value);
    if (parsed) return parsed;
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

function routeLabel(value: unknown) {
  switch (text(value, "none")) {
    case "object_fetch_request":
      return "取物请求";
    case "training_start_request":
      return "开始训练";
    case "training_summary_request":
      return "训练总结";
    case "diagnostic_request":
      return "只读巡检";
    case "data_collection_request":
      return "数据采集";
    case "daily_chat":
      return "日常聊天";
    case "hold_need_clarification":
      return "需要澄清";
    default:
      return "等待分类";
  }
}

function operationModeLabel(value: unknown) {
  switch (text(value, "waiting_for_voice_route")) {
    case "object_fetch_vla_lite":
      return "取物 VLA-lite";
    case "rehab_training_assist":
      return "康复训练助力";
    case "training_summary_request":
      return "训练总结";
    case "inspection_diagnostics":
      return "诊断巡检";
    case "data_collection":
      return "数据采集";
    case "daily_chat":
      return "日常聊天";
    default:
      return "等待语音路由";
  }
}

function semanticActionModeLabel(value: unknown) {
  switch (text(value, "chat")) {
    case "fetch_object":
      return "取物";
    case "training":
      return "训练";
    case "assistive_emg":
      return "肌电助力";
    case "vision_servo":
      return "视觉伺服";
    case "safety_review":
      return "安全审核";
    case "diagnostics":
      return "诊断";
    case "data_collection":
      return "采集";
    case "chat":
      return "聊天";
    default:
      return "等待模式";
  }
}

function modeStageText(value: unknown) {
  switch (text(value, "")) {
    case "dry_run_visual_gate":
      return "等待视觉目标";
    case "dry_run_candidate_ready":
      return "dry-run 候选就绪";
    case "reserved_waiting_vision":
      return "等待 V 证据";
    case "reserved_app_ble_m33":
      return "预留 APP/BLE/M33";
    case "pending_m55_m33_gate":
      return "等待 M55/M33 门控";
    case "shared_visual_evidence":
      return "共享视觉证据";
    case "default_review_gate":
      return "默认安全审核";
    case "read_only_available":
      return "只读可用";
    case "reserved_dataset_pipeline":
      return "预留采集链路";
    case "chat_only_no_action":
      return "聊天不触发动作";
    default:
      return text(value, "等待模式状态").replaceAll("_", " ");
  }
}

function modeBoundaryText(value: unknown) {
  switch (text(value, "")) {
    case "dry_run_only_not_motion_permission":
      return "只生成 dry-run 候选";
    case "training_plan_only_not_motion_permission":
      return "只生成训练计划";
    case "assistive_hint_only_m33_required":
      return "助力建议，M33 必须裁决";
    case "visual_servo_hint_only_not_motion_permission":
      return "只输出视觉伺服提示";
    case "review_status_only_not_motion_permission":
      return "只读审核状态";
    case "read_only_no_motion":
      return "只读诊断";
    case "dataset_artifact_only_no_motion":
      return "只生成数据资产";
    case "no_robot_action":
      return "不生成机器人动作";
    default:
      return text(value, "状态展示，不是运动许可").replaceAll("_", " ");
  }
}

function modeNextText(value: unknown) {
  switch (text(value, "")) {
    case "real_target_acceptance_and_calibration":
      return "等待真实目标验收和标定";
    case "connect_app_training_library_ble_to_m33":
      return "接 APP 训练库到 M33";
    case "connect_m55_emg_intent_and_m33_gate":
      return "接 M55 肌电意图";
    case "camera_to_robot_calibration":
      return "做相机到机械臂标定";
    case "attach_mujoco_review_evidence":
      return "补 MuJoCo 审核证据";
    case "add_topic_log_can_snapshots":
      return "补 topic/log/CAN 快照";
    case "connect_capture_session_index_and_labels":
      return "接采集批次和标签";
    case "keep_isolated_from_robot_action":
      return "保持与动作隔离";
    default:
      return text(value, "等待下一步").replaceAll("_", " ");
  }
}

function modeTone(value: unknown): "ok" | "idle" | "limited" {
  const raw = text(value, "idle");
  return raw === "ok" || raw === "idle" || raw === "limited" ? raw : "idle";
}

function vlaLiteLoopLabel(value: unknown) {
  switch (text(value, "waiting_language")) {
    case "waiting_language":
      return "等待语音任务";
    case "waiting_vision":
      return "等待双目视觉";
    case "tracking_target":
      return "持续跟踪目标";
    case "hold_stale_vision":
      return "视觉过期保持";
    case "hold_end_effector":
      return "等待末端入画";
    case "hold_uncalibrated_depth":
      return "未标定保持";
    case "candidate_ready":
      return "候选已就绪";
    default:
      return "等待闭环状态";
  }
}

function dryRunGateLabel(value: unknown) {
  switch (text(value, "hold_language")) {
    case "hold_language":
      return "等待 L 指令";
    case "hold_vision":
      return "等待 V 目标";
    case "hold_stale_vision":
      return "视觉过期保持";
    case "hold_end_effector":
      return "等待末端";
    case "observe_more":
      return "继续观察";
    case "visual_lock_ready":
      return "可进入 dry-run";
    case "candidate_ready":
      return "候选已生成";
    default:
      return "A 保持";
  }
}

function inferVoiceRouteFromText(value: unknown) {
  const transcript = text(value, "").trim();
  const normalized = transcript.toLowerCase();
  const includesAny = (words: string[]) => words.some((word) => normalized.includes(word.toLowerCase()));

  if (!transcript) {
    return {
      route_class: "none",
      ai_operation_mode: "waiting_for_voice_route",
      route_action: "wait_for_language_input",
      confidence: 0,
      evidence: "no_transcript",
      source: "fallback_preview",
    };
  }
  if (includesAny(["口渴", "喝水", "水杯", "杯子", "瓶子", "拿", "取", "递给我", "拿过来"])) {
    return {
      route_class: "object_fetch_request",
      ai_operation_mode: "object_fetch_vla_lite",
      route_action: "fuse_language_allowlist_with_stereo_target",
      confidence: 0.62,
      target_allowlist: includesAny(["水杯", "杯子"]) ? ["cup", "bottle"] : ["bottle", "cup"],
      evidence: "keyword_object_fetch",
      source: "fallback_preview",
    };
  }
  if (includesAny(["开始训练", "今天的训练", "康复训练", "抬手训练", "训练模式", "帮我训练"])) {
    return {
      route_class: "training_start_request",
      ai_operation_mode: "rehab_training_assist",
      route_action: "select_training_goal_candidate",
      confidence: 0.66,
      evidence: "keyword_training_start",
      source: "fallback_preview",
    };
  }
  if (includesAny(["助力", "没力", "使不上力", "帮我抬", "辅助抬", "肌电", "发力", "手臂酸", "抬不动"])) {
    return {
      route_class: "assistive_emg_request",
      ai_operation_mode: "assistive_emg",
      route_action: "prepare_emg_intent_assist_hint",
      confidence: 0.64,
      evidence: "keyword_assistive_emg",
      source: "fallback_preview",
    };
  }
  if (includesAny(["总结", "训练得怎么样", "报告", "复盘", "今天怎么样"])) {
    return {
      route_class: "training_summary_request",
      ai_operation_mode: "rehab_training_assist",
      route_action: "request_training_summary",
      confidence: 0.62,
      evidence: "keyword_training_summary",
      source: "fallback_preview",
    };
  }
  if (includesAny(["摄像头正常", "检查", "巡检", "can", "总线", "电机状态", "诊断", "有没有问题"])) {
    return {
      route_class: "diagnostic_request",
      ai_operation_mode: "inspection_diagnostics",
      route_action: "readonly_system_inspection",
      confidence: 0.58,
      evidence: "keyword_diagnostics",
      source: "fallback_preview",
    };
  }
  if (includesAny(["采集数据", "录数据", "标定", "拍几帧", "数据集", "训练样本"])) {
    return {
      route_class: "data_collection_request",
      ai_operation_mode: "data_collection",
      route_action: "prepare_readonly_capture_session",
      confidence: 0.56,
      evidence: "keyword_data_collection",
      source: "fallback_preview",
    };
  }
  if (transcript.length < 4) {
    return {
      route_class: "hold_need_clarification",
      ai_operation_mode: "daily_chat",
      route_action: "ask_user_to_repeat",
      confidence: 0.35,
      evidence: "short_transcript",
      source: "fallback_preview",
    };
  }
  return {
    route_class: "daily_chat",
    ai_operation_mode: "daily_chat",
    route_action: "operator_facing_reply_only",
    confidence: 0.52,
    evidence: "no_robotic_keyword",
    source: "fallback_preview",
  };
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

function compactNumberText(value: unknown, unit = "") {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${Number.isInteger(number) ? number : number.toFixed(1)}${unit}`;
}

function detectionCount(value: unknown) {
  const detections = value && !Array.isArray(value) && typeof value === "object"
    ? (value as AnyRecord).detections
    : value;
  if (Array.isArray(detections)) return detections.length;
  if (detections && typeof detections === "object") {
    return Object.values(detections as AnyRecord).reduce((total, item) => total + asArray<unknown>(item).length, 0);
  }
  return 0;
}

function numberTuple(value: unknown, length: number) {
  if (!Array.isArray(value) || value.length < length) return null;
  const out = value.slice(0, length).map((item) => Number(item));
  return out.every((item) => Number.isFinite(item)) ? out : null;
}

function firstNumberTuple(length: number, ...values: unknown[]) {
  for (const value of values) {
    const tuple = numberTuple(value, length);
    if (tuple) return tuple;
  }
  return null;
}

function targetCenterFromObservation(target: AnyRecord, observation: AnyRecord) {
  const center = firstNumberTuple(
    2,
    observation.left_center_px,
    target.left_center_px,
    target.center_px,
    target.center,
  );
  if (center) return center;
  const bbox = firstNumberTuple(4, observation.left_bbox_xywh, target.bbox_xywh, target.bbox);
  if (!bbox) return null;
  const [x, y, width, height] = bbox;
  return [x + width / 2, y + height / 2];
}

type VisualMemorySample = {
  label: string;
  tsUnix: number | null;
  center: number[] | null;
  bbox: number[] | null;
  source: string;
};

function visualSampleFromObject(objectValue: unknown, payloadValue: unknown, kind: "target" | "end_effector"): VisualMemorySample | null {
  const object = record(objectValue);
  const payload = record(payloadValue);
  const observation = record(object.stereo_observation);
  const label = text(object.label ?? object.class_name ?? object.name, "");
  const bbox = firstNumberTuple(
    4,
    kind === "end_effector" ? observation.left_bbox_xywh : undefined,
    object.bbox_xywh,
    object.bbox,
  );
  const center = targetCenterFromObservation(object, observation);
  if (!label && !bbox && !center) return null;
  return {
    label: label || (kind === "end_effector" ? "end_effector" : "target"),
    tsUnix: timestampUnixFromRows(object, observation, payload),
    center,
    bbox,
    source: text(payload.schema_version, "stereo_vision_context"),
  };
}

function newestVisualSample(samples: Array<VisualMemorySample | null>) {
  const valid = samples.filter(Boolean) as VisualMemorySample[];
  if (!valid.length) return null;
  return valid.sort((a, b) => Number(b.tsUnix ?? 0) - Number(a.tsUnix ?? 0))[0];
}

function visualMemoryUsable(sample: VisualMemorySample | null, nowMs: number, ttlMs = 5000) {
  if (!sample?.tsUnix) return false;
  return nowMs - sample.tsUnix * 1000 <= ttlMs;
}

function inferFrameSize(payload: AnyRecord, target: AnyRecord, observation: AnyRecord) {
  const direct = firstNumberTuple(2, payload.frame_size_px, payload.image_size_px, payload.image_size, target.image_size_px);
  if (direct) return { width: direct[0], height: direct[1] };
  const scene = text(payload.scene_summary, "");
  const match = scene.match(/(\d{2,5})x(\d{2,5})/);
  if (match) return { width: Number(match[1]), height: Number(match[2]) };
  const bbox = firstNumberTuple(4, observation.left_bbox_xywh, target.bbox_xywh, target.bbox);
  if (bbox) return { width: Math.max(640, bbox[0] + bbox[2]), height: Math.max(480, bbox[1] + bbox[3]) };
  return { width: 640, height: 480 };
}

function axisBand(value: number, deadband: number) {
  if (value < -deadband) return "negative";
  if (value > deadband) return "positive";
  return "center";
}

function pixelServoSuggestion({
  center,
  frame,
  disparity,
  disparitySpread,
  lockedFrames,
  sampleCount,
  fresh,
}: {
  center: number[] | null;
  frame: { width: number; height: number };
  disparity: number | null;
  disparitySpread: number | null;
  lockedFrames: number;
  sampleCount: number;
  fresh: boolean;
}) {
  if (!center) {
    return {
      state: "waiting",
      title: "等待目标中心",
      summary: "当前帧缺少目标中心或 bbox，继续观察，不生成逼近方向。",
      horizontal: "unknown",
      vertical: "unknown",
      nextStep: "hold_observe",
      targetOffsetText: "无像素中心",
      stabilityText: sampleCount ? `${lockedFrames}/${sampleCount} 帧` : "暂无历史",
      tone: "limited",
    };
  }
  if (!fresh) {
    return {
      state: "hold_stale_vision",
      title: "视觉过期保持",
      summary: "当前只显示上一帧像素位置；必须重新观察后才生成 dry-run 修正方向。",
      horizontal: "unknown",
      vertical: "unknown",
      nextStep: "hold_observe",
      targetOffsetText: "等待新帧",
      stabilityText: sampleCount ? `${lockedFrames}/${sampleCount} 帧历史` : "暂无新鲜历史",
      tone: "limited",
    };
  }
  const frameWidth = Math.max(1, frame.width);
  const frameHeight = Math.max(1, frame.height);
  const offsetX = (center[0] - frameWidth / 2) / (frameWidth / 2);
  const offsetY = (center[1] - frameHeight / 2) / (frameHeight / 2);
  const horizontal = axisBand(offsetX, 0.16);
  const vertical = axisBand(offsetY, 0.16);
  const centered = horizontal === "center" && vertical === "center";
  const stable = sampleCount >= 3
    ? lockedFrames >= Math.min(3, sampleCount) && (disparitySpread === null || disparitySpread <= 8)
    : lockedFrames > 0;
  const depthCue = disparity !== null
    ? (disparity > 36 ? "too_near" : disparity < 10 ? "far_or_uncertain" : "usable_disparity")
    : "unknown";
  const horizontalText = horizontal === "negative" ? "目标偏左" : horizontal === "positive" ? "目标偏右" : "水平居中";
  const verticalText = vertical === "negative" ? "目标偏上" : vertical === "positive" ? "目标偏下" : "垂直居中";
  const nextStep = centered && stable
    ? "hold_centered_then_reobserve"
    : horizontal === "negative"
      ? "dry_run_shift_left"
      : horizontal === "positive"
        ? "dry_run_shift_right"
        : vertical === "negative"
          ? "dry_run_lift_up"
          : vertical === "positive"
            ? "dry_run_lift_down"
            : "hold_observe";
  const title = centered
    ? stable ? "像素居中稳定" : "像素居中待稳定"
    : `${horizontalText} · ${verticalText}`;
  return {
    state: centered && stable ? "centered_stable" : stable ? "servo_adjust" : "observe_more",
    title,
    summary: `${horizontalText}，${verticalText}；只生成 dry-run 方向，不把像素当真实三维坐标。`,
    horizontal,
    vertical,
    nextStep,
    targetOffsetText: `x ${Math.round(offsetX * 100)}% · y ${Math.round(offsetY * 100)}%`,
    stabilityText: [
      sampleCount ? `${lockedFrames}/${sampleCount} 帧锁定` : "暂无历史",
      disparitySpread !== null ? `视差波动 ${compactNumberText(disparitySpread, " px")}` : "",
      depthCue === "usable_disparity" ? "视差可用" : depthCue === "too_near" ? "视差偏大" : depthCue === "far_or_uncertain" ? "视差偏小/较远" : "无视差",
    ].filter(Boolean).join("；"),
    tone: centered && stable ? "ok" : stable ? "idle" : "limited",
  };
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

function firstPresentFiniteNumber(...values: unknown[]) {
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
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
  rawAdc: number | null;
  voltageV: number | null;
  displayValue: string;
  detail: string;
  fatigue: number | null;
  status: "active" | "moderate" | "quiet" | "unknown";
};

type MuscleMapAnchor = {
  key: string;
  side: "left" | "right";
  x: number;
  y: number;
  position: [number, number, number];
  meshKeywords: string[];
};

type HumanModelSource = {
  id: string;
  label: string;
  source: string;
  url: string;
  urls?: string[];
  license: string;
  note: string;
};

type MotionPredictionRow = {
  key: string;
  label: string;
  value: string;
  detail: string;
  tone: "active" | "moderate" | "quiet" | "unknown";
  confidence: number | null;
};

const DEFAULT_HUMAN_MODEL_SOURCES: HumanModelSource[] = [
  {
    id: "open3d-upper-arm-muscles",
    label: "Open3DModel upper-arm muscles",
    source: "AnatomyTOOL / Open3DModel upper-limb muscle layers",
    url: "/assets/human/open3d-upper-limb-arm-muscles.glb",
    urls: [
      "/assets/human/open3d-upper-limb-arm-muscles.glb",
      "/assets/human/open3d-forearm-anterior-muscles.glb",
    ],
    license: "CC BY-SA",
    note: "默认合成上臂与前臂肌肉层，适合承载肌电用力与疲劳状态。",
  },
  {
    id: "open3d-forearm-anterior-muscles",
    label: "Open3DModel forearm anterior muscles",
    source: "AnatomyTOOL / Open3DModel forearm anterior compartment muscles",
    url: "/assets/human/open3d-forearm-anterior-muscles.glb",
    license: "CC BY-SA",
    note: "前臂前群肌肉备选模型，可用于腕部/前臂肌电细分显示。",
  },
  {
    id: "local-upper-limb-glb",
    label: "Local full upper-limb GLB",
    source: "apps/web/public/assets/human/upper-limb.glb",
    url: "/assets/human/upper-limb.glb",
    license: "Project asset mirror / source-dependent",
    note: "完整上肢本地镜像，作为默认肌肉模型失效时的回退。",
  },
  {
    id: "anatom-models-upper-limb",
    label: "Open upper-limb GLB",
    source: "juncrose/anatom-models",
    url: "https://raw.githubusercontent.com/juncrose/anatom-models/main/upper-limb.glb",
    license: "Project page / public GitHub file",
    note: "远程备选入口，用于本地资产失效时回退。",
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

const MUSCLE_MAP_ANCHORS: MuscleMapAnchor[] = [
  { key: "biceps", side: "left", x: 35, y: 34, position: [0.02, 0.22, 0.1], meshKeywords: ["long head of biceps brachii", "short head of biceps brachii", "biceps brachii"] },
  { key: "triceps", side: "right", x: 58, y: 34, position: [0.16, 0.18, -0.05], meshKeywords: ["triceps brachii", "long head of triceps", "lateral head of triceps"] },
  { key: "forearm_flexor", side: "left", x: 39, y: 68, position: [-0.18, -0.42, 0.08], meshKeywords: ["flexor carpi radialis", "flexor digitorum superficialis", "pronator teres"] },
  { key: "forearm_extensor", side: "right", x: 63, y: 72, position: [-0.28, -0.5, -0.08], meshKeywords: ["extensor carpi", "extensor digitorum", "brachioradialis"] },
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

function emgVoltageFromChannel(channel: AnyRecord, rawAdc: number | null) {
  const direct = firstFiniteNumber(channel.voltage_v, channel.value_v, channel.voltage, channel.voltageV);
  if (direct !== null) return direct;
  if (rawAdc === null) return null;
  return rawAdc * 3.3 / 4095;
}

function emgDisplayText(voltageV: number | null, rawAdc: number | null, value: number | null) {
  if (voltageV !== null && rawAdc !== null) return `${numberText(voltageV, "V")} / ADC ${Math.round(rawAdc)}`;
  if (voltageV !== null) return numberText(voltageV, "V");
  if (rawAdc !== null) return `ADC ${Math.round(rawAdc)}`;
  if (value !== null) return `${Math.round(value * 100)}%`;
  return "0.000V / ADC 0";
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

function humanModelUrlsFromSensor(sensorPayload: AnyRecord) {
  const model = record(sensorPayload.human_model ?? sensorPayload.humanModel ?? sensorPayload.model_outputs?.human_model ?? sensorPayload.modelOutputs?.human_model);
  const urls = asArray<string>(model.urls ?? model.model_urls ?? sensorPayload.human_model_urls ?? sensorPayload.humanModelUrls)
    .map((url) => text(url, ""))
    .filter(Boolean);
  if (urls.length) return urls;
  const singleUrl = humanModelUrlFromSensor(sensorPayload);
  if (singleUrl !== DEFAULT_HUMAN_MODEL_SOURCES[0].url) return [singleUrl];
  return DEFAULT_HUMAN_MODEL_SOURCES[0].urls ?? [DEFAULT_HUMAN_MODEL_SOURCES[0].url];
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
    const confidence = normalizedSignalValue(candidate.confidence ?? candidate.score ?? candidate.probability);
    rows.push({
      key: `candidate_${index + 1}`,
      label: text(candidate.label ?? candidate.name ?? candidate.action ?? candidate.id, `候选 ${index + 1}`),
      value: text(candidate.confidence ?? candidate.score ?? candidate.probability, candidate.confidence === 0 ? "0%" : "-"),
      detail: text(candidate.detail ?? candidate.reason ?? candidate.description ?? candidate.note, text(candidate.phase ?? candidate.intent, "等待动作模型")),
      tone: muscleStatus(confidence ?? null),
      confidence,
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
      confidence: null,
    },
    {
      key: "interface",
      label: "接口字段",
      value: interfaceRef,
      detail: "后续可从 NanoPi、M55 或云端模型把 top-k 动作建议塞进这个结构。",
      tone: "quiet",
      confidence: null,
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
      confidence: null,
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
    { key: "biceps", label: "CH1 肱二头肌", names: ["biceps", "bicep", "肱二", "肱二头肌", "upper_arm_flexor", "ch1"] },
    { key: "triceps", label: "CH2 肱三头肌", names: ["triceps", "tricep", "肱三", "肱三头肌", "upper_arm_extensor", "ch2"] },
    { key: "forearm_flexor", label: "CH3 前臂屈肌", names: ["forearm_flexor", "flexor", "前臂屈", "屈肌", "qianbi_qu", "ch3"] },
    { key: "forearm_extensor", label: "CH4 前臂伸肌", names: ["forearm_extensor", "extensor", "前臂伸", "伸肌", "qianbi_shen", "ch4"] },
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
    const rawAdc = firstFiniteNumber(channel.raw_adc, channel.rawAdc, channel.adc, channel.adc_raw, channel.sample);
    const voltageV = emgVoltageFromChannel(channel, rawAdc);
    const fatigueValue = normalizedSignalValue(
      channel.fatigue,
      channel.fatigue_score,
      fatigue[spec.key],
      fatigue[`ch${index + 1}`],
      sensorPayload.fatigue_score,
      sensorPayload.fatigueScore,
    );
    const displayValue = emgDisplayText(voltageV, rawAdc, value);
    return {
      key: spec.key,
      label: spec.label,
      value,
      rawAdc,
      voltageV,
      displayValue,
      detail: `ADC ${rawAdc === null ? 0 : Math.round(rawAdc)} 路 ${voltageV === null ? "0.000V" : numberText(voltageV, "V")}`,
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

function withImageVersion(src: string, version: unknown) {
  const rawVersion = text(version, "");
  if (!src || !rawVersion) return src;
  return `${src}${src.includes("?") ? "&" : "?"}v=${encodeURIComponent(rawVersion)}`;
}

function browserImageSrc(value: unknown, apiBaseUrl: string) {
  const raw = text(value, "");
  if (!raw) return "";
  if (/^\/home\//i.test(raw) || /^[A-Za-z]:[\\/]/.test(raw)) return "";
  return keyframeSrc(raw, apiBaseUrl);
}

function bboxStyle(bbox: number[] | null, frame: { width: number; height: number }) {
  if (!bbox) return undefined;
  const [x, y, width, height] = bbox;
  const frameWidth = Math.max(1, frame.width);
  const frameHeight = Math.max(1, frame.height);
  return {
    left: `${clamp01(x / frameWidth) * 100}%`,
    top: `${clamp01(y / frameHeight) * 100}%`,
    width: `${clamp01(width / frameWidth) * 100}%`,
    height: `${clamp01(height / frameHeight) * 100}%`,
  };
}

function detectionPills(detections: unknown, imageSide: "left" | "right") {
  const sideDetections = Array.isArray(detections)
    ? detections
    : asArray<AnyRecord>(record(detections)[imageSide]);
  return asArray<AnyRecord>(sideDetections)
    .filter((item) => text(item.image_side, "left") === imageSide)
    .slice(0, 4)
    .map((item, index) => ({
      key: `${imageSide}-${text(item.label, "object")}-${index}`,
      label: text(item.label, "object"),
      confidence: Number(item.confidence),
      source: text(item.source, "detector"),
    }));
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
  stageMode = false,
  externalUrdfFile = null,
  externalUrdfFileNonce = null,
}: {
  deviceId: string;
  robotId: string;
  projectId: string;
  deviceModel: AnyRecord;
  motors: AnyRecord[];
  robotRenderState: AnyRecord;
  wiringChecks: AnyRecord[];
  safetyState: string;
  stageMode?: boolean;
  externalUrdfFile?: File | null;
  externalUrdfFileNonce?: number | null;
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
  const lastExternalUrdfNonceRef = useRef<number | null>(null);
  const applyUrdfPackageRef = useRef<(file: File, shouldSave: boolean) => void>(() => {});
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
    const timer = window.setTimeout(() => window.dispatchEvent(new Event("resize")), 80);
    return () => window.clearTimeout(timer);
  }, [focusMode]);

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
  applyUrdfPackageRef.current = applyUrdfPackage;

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
    if (!externalUrdfFile || !externalUrdfFileNonce || lastExternalUrdfNonceRef.current === externalUrdfFileNonce) return;
    lastExternalUrdfNonceRef.current = externalUrdfFileNonce;
    applyUrdfPackageRef.current(externalUrdfFile, true);
  }, [externalUrdfFile, externalUrdfFileNonce]);

  useEffect(() => {
    if (!deviceId || urdfText) return;
    setModelSaveState("idle");
    const controller = new AbortController();
    async function restoreModelPackage() {
      try {
        let { modelUrl, fileName, packageName, urdfPath, sha256, mappingJson } = modelInfoFromRecord(deviceModel);
        if (!modelUrl) {
          const dashboardResponse = await fetch(`/api/proxy/rehab-arm/v1/devices/dashboard?project_id=${encodeURIComponent(projectId)}`, { cache: "no-store", signal: controller.signal });
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
  }, [deviceId, deviceModel, projectId, urdfText]);

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
      scene.background = new THREE.Color(stageMode ? 0x18130d : 0x020a0d);

      const narrowViewport = width <= 520;
      const cameraTarget = new THREE.Vector3(0.08, 0.0, 0.16);
      const camera = new THREE.PerspectiveCamera(narrowViewport ? 48 : 34, width / height, 0.01, 100);
      camera.position.set(
        narrowViewport ? 2.25 : 1.85,
        narrowViewport ? -2.7 : -2.25,
        narrowViewport ? 1.62 : 1.35,
      );
      camera.lookAt(cameraTarget);

      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(width, height);
      if (stageMode) {
        renderer.setClearColor(0x18130d, 1);
        renderer.domElement.style.opacity = "0.86";
      }
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
      scene.add(camera);
      const keyLight = new THREE.DirectionalLight(0xffffff, 1.2);
      keyLight.position.set(1.4, -1.8, 2.2);
      scene.add(keyLight);
      const fillLight = new THREE.DirectionalLight(0x75f7dd, 0.7);
      fillLight.position.set(-1.2, 1.1, 1.4);
      scene.add(fillLight);

      const grid = new THREE.GridHelper(1.5, 12, stageMode ? 0xffb100 : 0x214a48, stageMode ? 0x244243 : 0x10272b);
      if (stageMode) {
        grid.material.transparent = true;
        grid.material.opacity = 0.42;
      }
      scene.add(grid);

      const hudCanvas = document.createElement("canvas");
      hudCanvas.width = 560;
      hudCanvas.height = 720;
      const hudContext = hudCanvas.getContext("2d");
      const hudTexture = new THREE.CanvasTexture(hudCanvas);
      const hudMaterial = new THREE.SpriteMaterial({
        map: hudTexture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
      });
      const hudSprite = new THREE.Sprite(hudMaterial);
      hudSprite.position.set(1.18, 0.02, -2.2);
      hudSprite.scale.set(1.06, 1.36, 1);
      hudSprite.renderOrder = 999;
      if (!stageMode) camera.add(hudSprite);

      function drawHudPanel(title: string, subtitle: string, rows: Array<[string, string, string]>) {
        if (!hudContext) return;
        hudContext.clearRect(0, 0, hudCanvas.width, hudCanvas.height);
        hudContext.shadowColor = "rgba(0, 0, 0, 0.72)";
        hudContext.shadowBlur = 12;
        hudContext.shadowOffsetY = 2;
        hudContext.fillStyle = "#bae6fd";
        hudContext.font = "700 20px sans-serif";
        hudContext.fillText("RENDER HUD", 32, 52);
        hudContext.fillStyle = "#f8fafc";
        hudContext.font = "900 34px sans-serif";
        wrapCanvasText(hudContext, title, 32, 104, 496, 38, 2);
        hudContext.fillStyle = "rgba(203, 213, 225, 0.92)";
        hudContext.font = "600 18px sans-serif";
        wrapCanvasText(hudContext, subtitle, 32, 166, 496, 24, 2);
        hudContext.shadowBlur = 8;
        let y = 238;
        rows.slice(0, 8).forEach(([label, value, detail], index) => {
          hudContext.strokeStyle = "rgba(125, 211, 252, 0.24)";
          hudContext.lineWidth = 1;
          hudContext.beginPath();
          hudContext.moveTo(32, y + 28);
          hudContext.lineTo(520, y + 28);
          hudContext.stroke();
          hudContext.fillStyle = "#67e8f9";
          hudContext.font = "800 17px sans-serif";
          hudContext.fillText(label, 48, y - 5);
          hudContext.fillStyle = "#ffffff";
          hudContext.font = "900 21px sans-serif";
          hudContext.fillText(value, 260, y - 5);
          hudContext.fillStyle = "rgba(203, 213, 225, 0.82)";
          hudContext.font = "600 15px sans-serif";
          hudContext.fillText(detail, 48, y + 20);
          y += 70;
        });
        hudContext.fillStyle = "rgba(148, 163, 184, 0.84)";
        hudContext.font = "700 16px sans-serif";
        hudContext.fillText("canvas texture overlay · display only · not motion authority", 32, 688);
        hudContext.shadowBlur = 0;
        hudTexture.needsUpdate = true;
      }

      function roundRect(context: CanvasRenderingContext2D, x: number, y: number, widthValue: number, heightValue: number, radius: number) {
        context.beginPath();
        context.moveTo(x + radius, y);
        context.arcTo(x + widthValue, y, x + widthValue, y + heightValue, radius);
        context.arcTo(x + widthValue, y + heightValue, x, y + heightValue, radius);
        context.arcTo(x, y + heightValue, x, y, radius);
        context.arcTo(x, y, x + widthValue, y, radius);
        context.closePath();
      }

      function wrapCanvasText(context: CanvasRenderingContext2D, value: string, x: number, y: number, maxWidth: number, lineHeight: number, maxLines: number) {
        const words = value.split(/\s+/);
        let line = "";
        let lineIndex = 0;
        words.forEach((word) => {
          const next = line ? `${line} ${word}` : word;
          if (context.measureText(next).width > maxWidth && line) {
            if (lineIndex < maxLines) context.fillText(line, x, y + lineIndex * lineHeight);
            line = word;
            lineIndex += 1;
          } else {
            line = next;
          }
        });
        if (line && lineIndex < maxLines) context.fillText(line, x, y + lineIndex * lineHeight);
      }

      function armHudRows(): Array<[string, string, string]> {
        const currentRows = sceneDataRef.current.motors.slice(0, 5).map((motor, index): [string, string, string] => {
          const jointName = text(motor.joint_name ?? motor.jointName ?? motor.name, ARM_MODEL_JSON.joints[index] ?? `joint_${index + 1}`);
          const temp = motorTemperature(motor);
          const angle = firstFiniteNumber(motor.position, motor.angle, motor.angle_rad, motor.theta, jointValuesRef.current.get(jointName));
          const source = text(motor.source_label ?? motor.source ?? motor.device_id, "motor telemetry");
          return [
            jointName,
            angle === null ? "angle -" : numberText(angle, " rad"),
            `${temp === null ? "temp -" : numberText(temp, " ℃")} · ${source}`,
          ];
        });
        const wiringRows = sceneDataRef.current.badWiringChecks.slice(0, 2).map((item): [string, string, string] => [
          text(item.channel ?? item.joint_name ?? item.motor_id, "wiring"),
          text(item.status, "stale"),
          text(item.evidence ?? item.reason, "check harness / source freshness"),
        ]);
        return currentRows.length || wiringRows.length
          ? [...currentRows, ...wiringRows]
          : [["waiting", "no motor frame", "robot_render_state_v1 / motor_state not fresh"]];
      }

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

      function frameMetricRobot(object: AnyRecord) {
        const box = new THREE.Box3().setFromObject(object as any);
        if (box.isEmpty()) return;
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z, 0.25);
        controls.target.copy(center);
        const distance = Math.min(4.2, Math.max(1.05, maxDim * 2.2));
        camera.position.set(center.x + distance * 0.72, center.y - distance * 0.92, center.z + distance * 0.58);
        camera.lookAt(center);
        camera.updateProjectionMatrix();
        controls.update();
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
          robot.position.set(0, 0, 0);
          robot.scale.setScalar(1);
          applyJointValues(robot);
          scene.add(robot as any);
          frameMetricRobot(robot);
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
        if (frame % 20 === 0) {
          if (!stageMode) {
            drawHudPanel(
              "电机 / URDF 渲染日志",
              `${sceneDataRef.current.renderJointNames.length || ARM_MODEL_JSON.joints.length} joints · safety ${sceneDataRef.current.safetyState}`,
              armHudRows(),
            );
          }
        }
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
  }, [stageMode, urdfPackage, urdfText]);

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
      ? `已导入 ${urdfName || "URDF"} · MuJoCo shadow 米制坐标`
      : urdfState === "loading"
        ? "正在导入 URDF"
      : urdfState === "failed"
          ? "URDF 未能完整加载，正在显示默认可替换模型"
          : "默认可替换模型，可导入真实 URDF";

  return (
    <section className={styles.armOverviewPanel} data-focus={focusMode ? "true" : "false"} data-stage-mode={stageMode ? "true" : "false"} aria-label="机械臂 3D 总览">
      <button type="button" className={styles.focusCloseButton} onClick={() => setFocusMode(false)}>
        关闭全屏
      </button>
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
        <p>支持 URDF zip 包或单个 URDF。页面保持导入模型的米制根坐标和比例，相机自动取景；优先用 robot_render_state_v1 的 joint_names/positions 驱动同名关节，只读预览，不下发任何运动控制。</p>
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

function HumanMuscleOverview({ sensorPayload, stageMode = false }: { sensorPayload: AnyRecord; stageMode?: boolean }) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const anchorRefs = useRef<Record<string, HTMLElement | null>>({});
  const [focusMode, setFocusMode] = useState(false);
  const rows = useMemo(() => muscleRowsFromSensor(sensorPayload), [sensorPayload]);
  const motionRows = useMemo(() => motionPredictionRowsFromSensor(sensorPayload), [sensorPayload]);
  const rowsRef = useRef(rows);
  const motionRowsRef = useRef(motionRows);
  const modelUrls = useMemo(() => humanModelUrlsFromSensor(sensorPayload), [sensorPayload]);
  const modelSource = useMemo(() => humanModelSourceFromSensor(sensorPayload), [sensorPayload]);
  const activeRows = rows.filter((row) => row.status === "active").length;
  const strongestRow = rows
    .filter((row) => row.value !== null)
    .sort((a, b) => Number(b.value) - Number(a.value))[0] ?? null;
  const primaryPrediction = motionRows[0] ?? null;
  const averageFatigue = (() => {
    const values = rows.map((row) => row.fatigue).filter((value): value is number => value !== null);
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  })();

  useEffect(() => {
    rowsRef.current = rows;
    motionRowsRef.current = motionRows;
  }, [motionRows, rows]);

  useEffect(() => {
    const timer = window.setTimeout(() => window.dispatchEvent(new Event("resize")), 80);
    return () => window.clearTimeout(timer);
  }, [focusMode]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    let disposed = false;
    let cleanup = () => {};

    async function renderHuman() {
      const THREE = await import("three");
      const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
      const { GLTFLoader } = await import("three/examples/jsm/loaders/GLTFLoader.js");
      const { DRACOLoader } = await import("three/examples/jsm/loaders/DRACOLoader.js");
      if (disposed || !mountRef.current) return;
      const target = mountRef.current;
      const width = Math.max(280, target.clientWidth || 420);
      const height = Math.max(320, target.clientHeight || 420);
      target.replaceChildren();

      const scene = new THREE.Scene();
      scene.background = stageMode ? null : new THREE.Color(0xf8fafc);
      const camera = new THREE.PerspectiveCamera(34, width / height, 0.01, 100);
      camera.position.set(0.42, -2.05, 0.72);
      camera.lookAt(0, 0, 0);
      scene.add(camera);

      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: stageMode });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(width, height);
      if (stageMode) {
        renderer.setClearColor(0x000000, 0);
        renderer.domElement.style.background = "transparent";
        renderer.domElement.style.backgroundColor = "transparent";
        renderer.domElement.style.mixBlendMode = "screen";
      }
      renderer.domElement.setAttribute("aria-label", "开源上肢肌肉模型 Three.js 总览");
      target.appendChild(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.enablePan = true;
      controls.minDistance = 0.38;
      controls.maxDistance = 3.2;
      controls.target.set(0, 0, 0);
      controls.update();

      scene.add(new THREE.HemisphereLight(0xffffff, 0x331016, stageMode ? 1.45 : 2.2));
      const key = new THREE.DirectionalLight(0xffffff, 1.2);
      key.position.set(0.7, -1.2, 1.8);
      scene.add(key);
      const rim = new THREE.DirectionalLight(stageMode ? 0x00dbe7 : 0x1b6cff, stageMode ? 1.05 : 0.72);
      rim.position.set(-1.4, 1.1, 1.1);
      scene.add(rim);

      const grid = new THREE.GridHelper(1.05, 8, 0xd6dde8, 0xe7ebf2);
      grid.position.z = -0.2;
      if (!stageMode) scene.add(grid);

      const modelGroup = new THREE.Group();
      scene.add(modelGroup);
      const hudCanvas = document.createElement("canvas");
      hudCanvas.width = 560;
      hudCanvas.height = 720;
      const hudContext = hudCanvas.getContext("2d");
      const hudTexture = new THREE.CanvasTexture(hudCanvas);
      const hudMaterial = new THREE.SpriteMaterial({
        map: hudTexture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
      });
      const hudSprite = new THREE.Sprite(hudMaterial);
      hudSprite.position.set(1.16, 0.0, -2.16);
      hudSprite.scale.set(1.06, 1.36, 1);
      hudSprite.renderOrder = 999;
      if (!stageMode) camera.add(hudSprite);
      const anchorPoints = MUSCLE_MAP_ANCHORS.map((anchor) => ({
        key: anchor.key,
        keywords: anchor.meshKeywords.map((keyword) => keyword.toLowerCase()),
        world: new THREE.Vector3(...anchor.position),
        projected: new THREE.Vector3(),
        matched: false,
      }));

      function roundRect(context: CanvasRenderingContext2D, x: number, y: number, widthValue: number, heightValue: number, radius: number) {
        context.beginPath();
        context.moveTo(x + radius, y);
        context.arcTo(x + widthValue, y, x + widthValue, y + heightValue, radius);
        context.arcTo(x + widthValue, y + heightValue, x, y + heightValue, radius);
        context.arcTo(x, y + heightValue, x, y, radius);
        context.arcTo(x, y, x + widthValue, y, radius);
        context.closePath();
      }

      function wrapCanvasText(context: CanvasRenderingContext2D, value: string, x: number, y: number, maxWidth: number, lineHeight: number, maxLines: number) {
        const words = value.split(/\s+/);
        let line = "";
        let lineIndex = 0;
        words.forEach((word) => {
          const next = line ? `${line} ${word}` : word;
          if (context.measureText(next).width > maxWidth && line) {
            if (lineIndex < maxLines) context.fillText(line, x, y + lineIndex * lineHeight);
            line = word;
            lineIndex += 1;
          } else {
            line = next;
          }
        });
        if (line && lineIndex < maxLines) context.fillText(line, x, y + lineIndex * lineHeight);
      }

      function drawHudPanel(title: string, subtitle: string, rows: Array<[string, string, string]>) {
        if (!hudContext) return;
        hudContext.clearRect(0, 0, hudCanvas.width, hudCanvas.height);
        hudContext.shadowColor = "rgba(0, 0, 0, 0.58)";
        hudContext.shadowBlur = 12;
        hudContext.shadowOffsetY = 2;
        hudContext.fillStyle = "#99f6e4";
        hudContext.font = "700 20px sans-serif";
        hudContext.fillText("EMG HUD", 32, 52);
        hudContext.fillStyle = "#f8fafc";
        hudContext.font = "900 34px sans-serif";
        wrapCanvasText(hudContext, title, 32, 104, 496, 38, 2);
        hudContext.fillStyle = "rgba(203, 213, 225, 0.92)";
        hudContext.font = "600 18px sans-serif";
        wrapCanvasText(hudContext, subtitle, 32, 166, 496, 24, 2);
        hudContext.shadowBlur = 8;
        let y = 238;
        rows.slice(0, 8).forEach(([label, value, detail], index) => {
          hudContext.strokeStyle = "rgba(94, 234, 212, 0.24)";
          hudContext.lineWidth = 1;
          hudContext.beginPath();
          hudContext.moveTo(32, y + 28);
          hudContext.lineTo(520, y + 28);
          hudContext.stroke();
          hudContext.fillStyle = "#5eead4";
          hudContext.font = "800 17px sans-serif";
          hudContext.fillText(label, 48, y - 5);
          hudContext.fillStyle = "#ffffff";
          hudContext.font = "900 21px sans-serif";
          hudContext.fillText(value, 260, y - 5);
          hudContext.fillStyle = "rgba(203, 213, 225, 0.82)";
          hudContext.font = "600 15px sans-serif";
          hudContext.fillText(detail, 48, y + 20);
          y += 70;
        });
        hudContext.fillStyle = "rgba(148, 163, 184, 0.84)";
        hudContext.font = "700 16px sans-serif";
        hudContext.fillText("canvas texture overlay · display only · M55/M33 authority separate", 32, 688);
        hudContext.shadowBlur = 0;
        hudTexture.needsUpdate = true;
      }

      function muscleHudRows(): Array<[string, string, string]> {
        const muscleRows = rowsRef.current.slice(0, 4).map((row): [string, string, string] => [
          row.label,
          row.displayValue,
          `${row.detail} · intensity ${row.value === null ? "unknown" : `${Math.round(row.value * 100)}%`}`,
        ]);
        const predictionRows = motionRowsRef.current.slice(0, 3).map((row): [string, string, string] => [
          row.label,
          row.value,
          row.confidence === null ? row.detail : `confidence ${Math.round(row.confidence * 100)}%`,
        ]);
        return muscleRows.length || predictionRows.length
          ? [...muscleRows, ...predictionRows]
          : [["waiting", "no EMG frame", "sensor_state.emg / motion_prediction not fresh"]];
      }

      function bindAnchorsToModel(object: any) {
        const meshCenters = new Map<string, any[]>();
        object.updateMatrixWorld(true);
        object.traverse?.((child: any) => {
          if (!child.isMesh) return;
          const name = String(child.name ?? "").toLowerCase();
          if (!name) return;
          const box = new THREE.Box3().setFromObject(child);
          if (box.isEmpty()) return;
          anchorPoints.forEach((anchor) => {
            if (!anchor.keywords.some((keyword) => name.includes(keyword))) return;
            const values = meshCenters.get(anchor.key) ?? [];
            values.push(box.getCenter(new THREE.Vector3()));
            meshCenters.set(anchor.key, values);
          });
        });
        anchorPoints.forEach((anchor) => {
          const centers = meshCenters.get(anchor.key);
          anchor.matched = Boolean(centers?.length);
          if (!centers?.length) return;
          anchor.world.set(0, 0, 0);
          centers.forEach((center) => anchor.world.add(center));
          anchor.world.divideScalar(centers.length);
        });
      }

      function updateProjectedAnchors() {
        const rect = renderer.domElement.getBoundingClientRect();
        modelGroup.updateMatrixWorld(true);
        anchorPoints.forEach((anchor) => {
          const element = anchorRefs.current[anchor.key];
          if (!element) return;
          anchor.projected.copy(anchor.world).applyMatrix4(modelGroup.matrixWorld).project(camera);
          const visible = anchor.projected.z >= -1 && anchor.projected.z <= 1;
          const left = (anchor.projected.x * 0.5 + 0.5) * rect.width;
          const top = (-anchor.projected.y * 0.5 + 0.5) * rect.height;
          const labelWidth = Math.min(178, Math.max(132, rect.width * 0.3));
          const labelGap = 48;
          const labelLeft = anchor.projected.x < 0
            ? left - labelWidth - labelGap
            : left + labelGap;
          const safeLeft = THREE.MathUtils.clamp(labelLeft, 12, Math.max(12, rect.width - labelWidth - 12));
          const safeTop = THREE.MathUtils.clamp(top - 32, 12, Math.max(12, rect.height - 76));
          element.style.setProperty("--anchor-x", `${left}px`);
          element.style.setProperty("--anchor-y", `${top}px`);
          element.style.setProperty("--pin-x", `${left - safeLeft}px`);
          element.style.setProperty("--pin-y", `${top - safeTop}px`);
          element.style.left = `${safeLeft}px`;
          element.style.top = `${safeTop}px`;
          element.dataset.side = anchor.projected.x < 0 ? "left" : "right";
          element.dataset.bound = anchor.matched ? "true" : "false";
          element.dataset.visible = anchor.matched && visible && left >= -40 && left <= rect.width + 40 && top >= -40 && top <= rect.height + 40 ? "true" : "false";
        });
      }

      function normalizeModel(object: any) {
        const box = new THREE.Box3().setFromObject(object);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z, 0.001);
        object.position.sub(center);
        object.scale.multiplyScalar(1.74 / maxDim);
        object.rotation.z = -0.18;
        object.rotation.x = -0.08;
        object.position.z += 0.04;

        const normalizedBox = new THREE.Box3().setFromObject(object);
        const normalizedCenter = normalizedBox.getCenter(new THREE.Vector3());
        const normalizedSize = normalizedBox.getSize(new THREE.Vector3());
        controls.target.copy(normalizedCenter);
        camera.position.set(
          normalizedCenter.x + normalizedSize.x * 0.72 + 0.28,
          normalizedCenter.y - Math.max(1.65, normalizedSize.y * 1.45),
          normalizedCenter.z + Math.max(0.62, normalizedSize.z * 2.2),
        );
        camera.lookAt(normalizedCenter);
        controls.update();
        grid.position.z = normalizedBox.min.z - 0.03;
      }

      function applyOpenModelMaterial(object: any) {
        let meshIndex = 0;
        object.traverse?.((child: any) => {
          if (!child.isMesh) return;
          const baseHue = stageMode
            ? (meshIndex % 3 === 0 ? 0xff6b35 : meshIndex % 3 === 1 ? 0xd94b45 : 0xffb347)
            : (meshIndex % 3 === 0 ? 0xd95f4e : meshIndex % 3 === 1 ? 0xc0485f : 0x9b3d58);
          child.material = new THREE.MeshStandardMaterial({
            color: baseHue,
            emissive: stageMode ? 0x3a1008 : 0x000000,
            emissiveIntensity: stageMode ? 0.28 : 0,
            roughness: stageMode ? 0.48 : 0.64,
            metalness: 0.02,
            transparent: true,
            opacity: stageMode ? 0.52 : 0.92,
          });
          meshIndex += 1;
        });
      }

      const loader = new GLTFLoader();
      const dracoLoader = new DRACOLoader();
      dracoLoader.setDecoderPath("/assets/draco/gltf/");
      loader.setDRACOLoader(dracoLoader);
      Promise.allSettled(modelUrls.map((url) => new Promise<any>((resolve, reject) => {
        loader.load(url, resolve, undefined, reject);
      }))).then((results) => {
        if (disposed) return;
        const gltfs = results
          .filter((result): result is PromiseFulfilledResult<any> => result.status === "fulfilled")
          .map((result) => result.value);
        if (!gltfs.length) {
          const fallback = document.createElement("div");
          fallback.className = styles.humanModelFallback;
          fallback.innerHTML = `<strong>上肢肌肉 GLB 未载入</strong><span>请检查 GLB 文件、Draco 解码器或 human_model_url；肌电锚点和预测接口仍可继续演示。</span>`;
          target.appendChild(fallback);
          return;
        }
        const composite = new THREE.Group();
        gltfs.forEach((gltf) => {
          const model = gltf.scene;
          applyOpenModelMaterial(model);
          composite.add(model);
        });
        normalizeModel(composite);
        modelGroup.add(composite);
        bindAnchorsToModel(composite);
      }).catch(() => {
        const fallback = document.createElement("div");
        fallback.className = styles.humanModelFallback;
        fallback.innerHTML = `<strong>等待上肢肌肉 GLB 资产</strong><span>已预留开源模型承载位；把合法 GLB 写入 human_model_url 后，这里会直接渲染。</span>`;
        target.appendChild(fallback);
      });

      let frame = 0;
      let tick = 0;
      const animate = () => {
        if (disposed) return;
        frame = window.requestAnimationFrame(animate);
        tick += 1;
        modelGroup.rotation.y = Math.sin(Date.now() / 3600) * (stageMode ? 0.018 : 0.035);
        controls.update();
        updateProjectedAnchors();
        if (tick % 20 === 1) {
          if (!stageMode) {
            const top = motionRowsRef.current[0];
            drawHudPanel(
              "肌电 / 动作预测日志",
              `${rowsRef.current.length} EMG channels · ${top?.value || "prediction waiting"}`,
              muscleHudRows(),
            );
          }
        }
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
        updateProjectedAnchors();
      };
      window.addEventListener("resize", resize);
      cleanup = () => {
        window.removeEventListener("resize", resize);
        window.cancelAnimationFrame(frame);
        controls.dispose();
        dracoLoader.dispose();
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
  }, [modelUrls, stageMode]);

  return (
    <section className={styles.humanPanel} data-focus={focusMode ? "true" : "false"} data-stage-mode={stageMode ? "true" : "false"} aria-label="人体肌电模型">
      <button type="button" className={styles.focusCloseButton} onClick={() => setFocusMode(false)}>
        关闭全屏
      </button>
      <div className={styles.humanPanelHead}>
        <div>
          <span>上肢肌肉 / 开源 3D 模型</span>
          <strong>{strongestRow ? `${strongestRow.label} ${Math.round(Number(strongestRow.value) * 100)}%` : "等待肌电小模型"}</strong>
        </div>
        <div className={styles.panelActions}>
          <small>{averageFatigue === null ? "疲劳 unknown" : `平均疲劳 ${Math.round(averageFatigue * 100)}%`}</small>
          <button type="button" onClick={() => setFocusMode((value) => !value)}>
            {focusMode ? "退出全屏" : "全屏肌电"}
          </button>
        </div>
      </div>
      <div className={styles.humanModelStage}>
        <div className={styles.humanModelViewport}>
          <div ref={mountRef} className={styles.humanCanvas} />
          <div className={styles.muscleMapOverlay} aria-label="上肢肌肉电信号定位">
            {MUSCLE_MAP_ANCHORS.map((anchor) => {
              const row = rows.find((item) => item.key === anchor.key);
              const valueText = row?.displayValue ?? "0.000V / ADC 0";
              return (
                <article
                  key={anchor.key}
                  ref={(element) => {
                    anchorRefs.current[anchor.key] = element;
                  }}
                  className={styles.muscleAnchor}
                  data-state={row?.status ?? "unknown"}
                  data-side={anchor.side}
                  data-bound="false"
                  data-visible="false"
                  style={{ left: `${anchor.x}%`, top: `${anchor.y}%` }}
                >
                  <span>{row?.label ?? anchor.key}</span>
                  <strong>{valueText}</strong>
                  <small>待绑定模型点</small>
                  <em style={{ width: row?.value === null || row?.value === undefined ? "0%" : `${Math.round(row.value * 100)}%` }} />
                </article>
              );
            })}
          </div>
        </div>
        <div className={styles.muscleOverlay} aria-label="肌电热区状态">
          {rows.map((row) => (
            <article key={row.key} data-state={row.status}>
              <span>{row.label}</span>
              <strong>{row.displayValue}</strong>
              <p>intensity {row.value === null ? "unknown" : `${Math.round(row.value * 100)}%`} · fatigue {row.fatigue === null ? "unknown" : `${Math.round(row.fatigue * 100)}%`}</p>
            </article>
          ))}
        </div>
      </div>
      <section className={styles.predictionPanel} aria-label="动作预测模型输出">
        <div>
          <span>动作预测模型接口</span>
          <strong>{primaryPrediction?.value || "等待预测"}</strong>
          <small>{primaryPrediction?.confidence === null || primaryPrediction?.confidence === undefined ? "confidence unknown" : `confidence ${Math.round(primaryPrediction.confidence * 100)}%`}</small>
        </div>
        <div className={styles.predictionConfidence} data-tone={primaryPrediction?.tone ?? "unknown"} aria-label="预测可信度">
          <span>
            <em style={{ width: primaryPrediction?.confidence === null || primaryPrediction?.confidence === undefined ? "0%" : `${Math.round(primaryPrediction.confidence * 100)}%` }} />
          </span>
        </div>
        <div className={styles.predictionGrid}>
          {motionRows.map((row) => (
            <article key={row.key} data-tone={row.tone}>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
              {row.confidence !== null ? (
                <em className={styles.predictionMiniBar} style={{ width: `${Math.round(row.confidence * 100)}%` }} />
              ) : null}
              <p>{row.detail}</p>
            </article>
          ))}
        </div>
      </section>
      <details className={styles.nestedDrawer}>
        <summary>
          开源模型来源和替换
          <small>{modelSource}</small>
        </summary>
        <p>页面不自绘人体。默认尝试加载开源上肢肌肉 GLB；用户可通过 `sensor_state.human_model_url` 或 `human_model.model_url` 替换为自己的合法 GLTF/GLB 资产。</p>
        <p>动作预测接口优先读取 `motion_prediction.candidates`，其次读取 `action_prediction` / `model_outputs`；每个候选建议带 `label`、`confidence`、`detail`，只用于展示和审阅，不作为运动许可。</p>
        <p>肌电接口优先读取 `emg.channels`，支持 `channel` / `muscle` / `location` / `activation` / `fatigue` 字段，四块主视图会按肩、上臂、前臂、肩颈稳定肌映射显示。</p>
        <div className={styles.modelSourceList}>
          {DEFAULT_HUMAN_MODEL_SOURCES.map((source) => (
            <a key={source.id} href={source.url} target="_blank" rel="noreferrer">
              <strong>{source.label}</strong>
              <span>{source.source} · {source.license}</span>
              <small>{source.note}</small>
            </a>
          ))}
        </div>
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
        <strong>等待设备接入</strong>
        <p>NanoPi、M33/M55、App/现场数据和仿真证据接入后，这里会形成完整设备态势。真实运动仍走 M33 安全链路。</p>
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
  const [pollState, setPollState] = useState<"idle" | "syncing" | "ok" | "error">("idle");
  const [lastLiveUpdate, setLastLiveUpdate] = useState<number | null>(null);
  const liveDashboardRequestRef = useRef<AbortController | null>(null);
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
  const [demoLanguageInput, setDemoLanguageInput] = useState("");
  const [activeModule, setActiveModule] = useState<RehabWorkspaceModule>("overview");
  const [twinRuntimeHost, setTwinRuntimeHost] = useState<HTMLElement | null>(null);
  const [twinImportRequest, setTwinImportRequest] = useState<{ file: File; nonce: number } | null>(null);
  const [ikTargetInput, setIkTargetInput] = useState({ x_m: "0.32", y_m: "-0.08", z_m: "0.24" });
  const [ikApproachInput, setIkApproachInput] = useState("0,0,-1");
  const [ikOrientationInput, setIkOrientationInput] = useState("roll=0,pitch=90,yaw=0");
  const [ikSourceInput, setIkSourceInput] = useState<"vision_calibrated" | "manual_platform" | "simulation_test">("manual_platform");
  const ikDraftRef = useRef({
    target: { x_m: "0.32", y_m: "-0.08", z_m: "0.24" },
    approach: "0,0,-1",
    orientation: "roll=0,pitch=90,yaw=0",
    source: "manual_platform" as "vision_calibrated" | "manual_platform" | "simulation_test",
  });
  const [ikCandidateState, setIkCandidateState] = useState<"idle" | "generating" | "ready" | "error">("idle");
  const [ikCandidateError, setIkCandidateError] = useState("");
  const [lastIkCandidate, setLastIkCandidate] = useState<AnyRecord | null>(null);
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
    ikDraftRef.current = {
      target: ikTargetInput,
      approach: ikApproachInput,
      orientation: ikOrientationInput,
      source: ikSourceInput,
    };
  }, [ikApproachInput, ikOrientationInput, ikSourceInput, ikTargetInput]);

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

  const refreshLiveDashboard = useCallback(async (silent = false) => {
    if (liveDashboardRequestRef.current) return;
    const controller = new AbortController();
    liveDashboardRequestRef.current = controller;
    if (!silent) setPollState("syncing");
    try {
      const response = await fetch(`/api/proxy/rehab-arm/v1/devices/dashboard?project_id=${encodeURIComponent(projectId)}&_=${Date.now()}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("dashboard fetch failed");
      const payload = await response.json();
      setLiveDashboard(filterDashboardForProject(payload, projectId));
      setPollState("ok");
      setLastLiveUpdate(Date.now());
    } catch {
      if (!controller.signal.aborted) setPollState("error");
    } finally {
      if (liveDashboardRequestRef.current === controller) liveDashboardRequestRef.current = null;
    }
  }, [projectId]);

  useEffect(() => {
    let disposed = false;
    let timer: number | null = null;

    function schedule() {
      if (timer) window.clearInterval(timer);
      const visible = document.visibilityState !== "hidden";
      timer = window.setInterval(() => {
        if (document.visibilityState === "hidden") return;
        if (!disposed) void refreshLiveDashboard(true);
      }, visible ? 2000 : 15000);
    }

    function handleVisibilityChange() {
      schedule();
      if (!disposed && document.visibilityState !== "hidden") void refreshLiveDashboard(true);
    }

    void refreshLiveDashboard(true);
    schedule();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      disposed = true;
      if (timer) window.clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [refreshLiveDashboard]);

  useEffect(() => {
    return () => {
      liveDashboardRequestRef.current?.abort();
    };
  }, []);

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
  const stereoVision = selected?.stereo_vision_context ?? {};
  const stereoPayload = payloadOf(stereoVision);
  const stereoCaptureLoop = record(stereoPayload.capture_loop);
  const stereoTarget = record(stereoPayload.target_object);
  const stereoEndEffector = record(stereoPayload.end_effector_object);
  const stereoObservation = record(stereoTarget.stereo_observation);
  const stereoVisualLock = record(stereoPayload.visual_lock_stability);
  const stereoTargetQualityGate = record(stereoPayload.target_quality_gate);
  const stereoDepth = firstPresentFiniteNumber(stereoPayload.estimated_depth_m, record(stereoPayload.target_3d_camera_frame).z_m, record(stereoPayload.target_3d_camera_frame).z);
  const stereoHasContext = Object.keys(stereoPayload).length > 0;
  const stereoTargetLabel = text(stereoTarget.label, "");
  const stereoEndEffectorLabel = text(stereoEndEffector.label, "");
  const stereoDetectionCount = detectionCount(stereoPayload.detections);
  const stereoFrameProcessMs = Number(stereoCaptureLoop.frame_process_ms);
  const stereoHasFrameTiming = Number.isFinite(stereoFrameProcessMs);
  const stereoLoopIndex = Number(stereoCaptureLoop.loop_index);
  const stereoLoopCount = Number(stereoCaptureLoop.loop_count);
  const stereoLoopSequence = Number(stereoCaptureLoop.sequence);
  const stereoLoopProgressText = Number.isFinite(stereoLoopIndex) && Number.isFinite(stereoLoopCount) && stereoLoopCount > 0
    ? `${stereoLoopIndex + 1}/${stereoLoopCount}`
    : Number.isFinite(stereoLoopSequence)
      ? `seq ${stereoLoopSequence}`
      : "未上报";
  const stereoVisualLockState = text(stereoVisualLock.state, "");
  const stereoVisualLockStable = stereoVisualLock.stable_for_dry_run === true;
  const stereoVisualLockSameFrames = Number(stereoVisualLock.same_label_frames);
  const stereoVisualLockStereoFrames = Number(stereoVisualLock.stereo_match_frames);
  const stereoVisualLockSamples = Number(stereoVisualLock.samples);
  const stereoVisualLockJitterPx = Number(stereoVisualLock.center_jitter_px);
  const stereoVisualLockDisparitySpreadPx = Number(stereoVisualLock.disparity_spread_px);
  const stereoVisualLockCandidate = text(stereoVisualLock.candidate_label, "");
  const stereoHasPayloadVisualLock = Object.keys(stereoVisualLock).length > 0;
  const stereoHasTargetQualityGate = Object.keys(stereoTargetQualityGate).length > 0;
  const stereoTargetQualityGateState = text(stereoTargetQualityGate.state, "");
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
  const selectedVoiceRelay = latestRelayPayload(selected, "voice_relay");
  const selectedXiaozhiSession = latestRelayPayload(selected, "xiaozhi_session");
  const projectVoiceRelayDevice = devices.find((device) => Object.keys(latestRelayPayload(device, "voice_relay")).length > 0);
  const projectXiaozhiDevice = devices.find((device) => Object.keys(latestRelayPayload(device, "xiaozhi_session")).length > 0);
  const voiceRelay = Object.keys(selectedVoiceRelay).length ? selectedVoiceRelay : latestRelayPayload(projectVoiceRelayDevice, "voice_relay");
  const xiaozhiSession = Object.keys(selectedXiaozhiSession).length ? selectedXiaozhiSession : latestRelayPayload(projectXiaozhiDevice, "xiaozhi_session");
  const vlaCandidate = latestRelayPayload(selected, "vla_plan_candidate");
  const simulationReadiness = latestRelayPayload(selected, "simulation_readiness");
  const simulationReport = record(simulationReadiness.report);
  const modelRelayRecord = record(selected?.model_relay_response);
  const modelRelayPayload = payloadOf(modelRelayRecord);
  const modelRelayResponse = lastRelayResponse ?? record(modelRelayPayload.relay_response);
  const modelRelayA = record(modelRelayResponse.a);
  const modelRelaySemantic = record(modelRelayA.semantic);
  const modelRelayVisionContext = record(modelRelayResponse.vla_vision_context);
  const modelRelayVisualServoContext = record(modelRelayVisionContext.visual_servo_context);
  const modelRelayProvider = record(modelRelayResponse.provider);
  const modelRelaySuggestion = record(asArray<AnyRecord>(record(modelRelayResponse.suggestion).model_results)[0]);
  const estopAck = latestRelayPayload(selected, "estop_ack");
  const dataQuality = selected?.data_quality ?? {};
  const motors = asArray<AnyRecord>(motorPayload.motors);
  const projectXiaozhiEvents = liveDashboard.recent_events
    .filter((event) => ["xiaozhi_ws_input", "xiaozhi_ws_reply", "xiaozhi_ws_tts"].includes(text(event.record_type, "")));
  const selectedXiaozhiEvents = projectXiaozhiEvents
    .filter((event) => {
      if (selected?.device_id && text(event.device_id, "") !== selected.device_id) return false;
      return true;
    })
    .slice(0, 6);
  const xiaozhiEvents = (selectedXiaozhiEvents.length ? selectedXiaozhiEvents : projectXiaozhiEvents).slice(0, 6);
  const stereoRecentEvents = liveDashboard.recent_events
    .filter((event) => {
      if (selected?.device_id && text(event.device_id, "") !== selected.device_id) return false;
      return text(event.record_type, "") === "stereo_vision_context";
    })
    .slice(0, 6);
  const modelRelayEvents = liveDashboard.recent_events
    .filter((event) => {
      if (selected?.device_id && text(event.device_id, "") !== selected.device_id) return false;
      return ["model_relay_request", "model_relay_response"].includes(text(event.record_type, ""));
    })
    .slice(0, 6);
  const selectedIkCandidateRecord = record(selected?.ik_candidate);
  const dashboardIkCandidate = record(payloadOf(selectedIkCandidateRecord).candidate_response);
  const ikCandidate = Object.keys(lastIkCandidate ?? {}).length ? (lastIkCandidate as AnyRecord) : dashboardIkCandidate;
  const poseSamples = useMemo(
    () => [
      ...poseSamplesFromRenderState(robotRenderState, timestampUnix(selected?.command_center_snapshot)),
      ...poseSamplesFromTelemetry(motorPayload, sensorPayload),
    ],
    [motorPayload, robotRenderState, selected?.command_center_snapshot, sensorPayload],
  );
  const imageUrl = text(keyframe.image_url, "");
  const keyframeImageVersion = keyframePayload.frame_ts_unix ?? keyframe.ts_unix ?? selected?.last_upload_ts_unix;
  const absoluteImageUrl = withImageVersion(keyframeSrc(imageUrl, apiBaseUrl), keyframeImageVersion);
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

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const scrollToHash = () => {
      const id = decodeURIComponent(window.location.hash.replace(/^#/, ""));
      if (!id) return;
      window.setTimeout(() => {
        document.getElementById(id)?.scrollIntoView({ block: "start", behavior: "smooth" });
      }, 120);
    };
    scrollToHash();
    window.addEventListener("hashchange", scrollToHash);
    return () => window.removeEventListener("hashchange", scrollToHash);
  }, []);

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

  const updateRelayProvider = useCallback((providerId: string) => {
    const preset = relayConfig.presets.find((item) => item.id === providerId);
    setRelayConfig((current) => ({
      ...current,
      provider: providerId,
      base_url: preset?.base_url || current.base_url,
    }));
  }, [relayConfig.presets]);

  const saveRelayConfig = useCallback(async (overrides?: Partial<RelayConfig> & { api_key?: string }) => {
    const nextConfig = { ...relayConfig, ...overrides };
    const nextApiKey = text(overrides?.api_key, relayConfigKey).trim();
    setRelayConfigState("saving");
    setRelayConfigError("");
    try {
      const response = await fetch(`/api/proxy/rehab-arm/v1/projects/${encodeURIComponent(projectId)}/model-relay/config`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          provider: nextConfig.provider,
          base_url: nextConfig.base_url,
          model: nextConfig.model,
          api_key: nextApiKey || undefined,
          external_enabled: nextConfig.external_enabled,
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
  }, [projectId, relayConfig, relayConfigKey]);

  const createRelayInvokeToken = useCallback(async () => {
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
  }, [projectId, relayExportState, relayTokenTtlSeconds, selected]);

  async function copyRelayInvokeToken() {
    if (!relayExportToken) return;
    const copied = await copyTextToClipboard(relayExportToken);
    if (copied) {
      setRelayExportState("copied");
      setRelayExportError("");
      window.setTimeout(() => setRelayExportState("created"), 1600);
    } else {
      setRelayExportState("created");
      setRelayExportError("复制失败：浏览器拒绝剪贴板权限，请手动选中 token 复制。");
    }
  }

  async function requestModelRelay(promptOverride?: string) {
    if (!selected?.device_id || relayState === "sending") return;
    setRelayState("sending");
    setRelayError("");
    try {
      const prompt = text(promptOverride, relayPrompt).trim() || "请基于当前机械臂只读遥测、安全状态、接线状态、语音/视觉/肌电摘要，生成高层康复建议和 dry-run 候选说明。";
      if (promptOverride !== undefined) setRelayPrompt(prompt);
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
              camera_scene_summary: text(stereoPayload.scene_summary ?? keyframePayload.scene_summary, ""),
              stereo_target_label: stereoTargetLabel,
              stereo_end_effector_label: stereoEndEffectorLabel,
              stereo_baseline_m: stereoPayload.baseline_m,
              stereo_disparity_px: stereoObservation.horizontal_disparity_px,
              stereo_depth_m: stereoDepth,
              stereo_visual_lock_state: stereoVisualLockState,
              stereo_visual_lock_stable_for_dry_run: stereoVisualLockStable,
              stereo_visual_lock_same_label_frames: stereoVisualLockSameFrames,
              stereo_visual_lock_stereo_match_frames: stereoVisualLockStereoFrames,
              a_dry_run_gate_state: dryRunGateState,
              a_dry_run_candidate_allowed: dryRunCandidateAllowed,
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
  const semanticIntentText = text(modelRelaySemantic.intent_text, "");
  const languageGate = record(
    semanticIntentText
      ? (
        modelRelayResponse.vla_language_gate
          ?? record(modelRelayResponse.vla_language_context).classification
          ?? xiaozhiReplyPayload.vla_language_gate
          ?? xiaozhiSession.vla_language_gate
      )
      : (
        xiaozhiReplyPayload.vla_language_gate
          ?? xiaozhiSession.vla_language_gate
          ?? modelRelayResponse.vla_language_gate
          ?? record(modelRelayResponse.vla_language_context).classification
      ),
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
  const visionSummary = stereoHasContext
    ? [
      stereoTargetLabel ? `目标 ${stereoTargetLabel}` : "双目已上报",
      stereoEndEffectorLabel ? `末端 ${stereoEndEffectorLabel}` : "末端待识别",
      stereoDetectionCount ? `检测 ${stereoDetectionCount} 个` : "",
      stereoHasFrameTiming ? `处理 ${compactNumberText(stereoFrameProcessMs, " ms")}` : "",
      stereoLoopProgressText !== "未上报" ? `循环 ${stereoLoopProgressText}` : "",
      Number.isFinite(Number(stereoPayload.baseline_m)) ? `基线 ${compactNumberText(stereoPayload.baseline_m, " m")}` : "",
      Number.isFinite(Number(stereoObservation.horizontal_disparity_px)) ? `视差 ${compactNumberText(stereoObservation.horizontal_disparity_px, " px")}` : "",
      stereoDepth !== null ? `深度 ${compactNumberText(stereoDepth, " m")}` : "未标定深度",
    ].filter(Boolean).join("；")
    : text(
      keyframePayload.scene_summary ?? keyframePayload.detection_summary ?? keyframePayload.vla_context,
      absoluteImageUrl ? "已接收摄像头关键帧，等待视觉摘要" : "等待 stereo_rgb_yolo_context_v1 / camera_keyframe_v1",
    );
  const languageSummary = text(
    xiaozhiSession.transcript ?? xiaozhiReplyPayload.transcript ?? voiceRelay.transcript ?? record(voiceRelay.intent).text,
    xiaozhiSession.event ? xiaozhiEventLabel(xiaozhiSession.event) : "等待 XiaoZhi listen/audio",
  );
  const hasRealLanguageInput = languageSummary !== "等待 XiaoZhi listen/audio" || xiaozhiEvents.length > 0 || Object.keys(voiceRelay).length > 0;
  const effectiveLanguageSummary = semanticIntentText || (hasRealLanguageInput ? languageSummary : (demoLanguageInput || languageSummary));
  const voiceIntentRoute = record(
    xiaozhiReplyPayload.voice_intent_route
      ?? xiaozhiReplyPayload.intent_route
      ?? xiaozhiSession.voice_intent_route
      ?? xiaozhiSession.intent_route
      ?? voiceRelay.voice_intent_route
      ?? voiceRelay.intent_route
      ?? modelRelayResponse.voice_intent_route
      ?? record(modelRelayResponse.vla_language_context).voice_intent_route,
  );
  const routePreview: AnyRecord = Object.keys(voiceIntentRoute).length
    ? { ...voiceIntentRoute, source: text(voiceIntentRoute.source, "voice_intent_route_v1") }
    : inferVoiceRouteFromText(effectiveLanguageSummary);
  const routeClass = text(routePreview.route_class, "none");
  const routedOperationMode = text(routePreview.ai_operation_mode, "");
  const routeAction = text(routePreview.route_action, "wait_for_language_input");
  const routeConfidence = Number(routePreview.confidence);
  const routeConfidenceText = Number.isFinite(routeConfidence) && routeConfidence > 0
    ? `${Math.round(routeConfidence * 100)}%`
    : "未上报";
  const routeSourceText = text(routePreview.source, "fallback_preview") === "fallback_preview"
    ? (!hasRealLanguageInput && demoLanguageInput ? "演示 L 输入" : "前端兜底预览")
    : "真实语音路由";
  const actionCandidate = record(vlaCandidate.candidate);
  const simulationSteps = asArray<AnyRecord>(simulationReport.steps);
  const simulationFinalJointState = record(simulationReport.final_joint_state);
  const simulationStepLast = simulationSteps.length ? simulationSteps[simulationSteps.length - 1] : {};
  const simulationReady = text(simulationReport.readiness, "") === "vla_shadow_demo_ran" || simulationReport.ok === true;
  const simulationReportBoundary = text(simulationReport.control_boundary, "simulation_evidence_only_not_motion_permission");
  const simulationPlanState = text(simulationReport.last_plan_state, text(simulationStepLast.plan_state, "等待 MuJoCo"));
  const simulationTrajectoryCount = Number(simulationReport.shadow_trajectory_count);
  const simulationStepCount = Number(simulationReport.step_count);
  const simulationJointSummary = Object.entries(simulationFinalJointState)
    .slice(0, 3)
    .map(([name, value]) => `${name}: ${compactNumberText(value, " rad")}`)
    .join("；");
  const semanticTargetLabel = text(record(modelRelaySemantic.target).label, text(modelRelaySemantic.target_label, ""));
  const semanticModeLabel = text(modelRelaySemantic.mode, text(modelRelayResponse.input_type, "等待 A semantic"));
  const semanticSourceLabel = text(modelRelaySemantic.source, "platform_language_semantic_router");
  const modelRelayVisualDistance = firstFiniteNumber(
    modelRelayVisualServoContext.pixel_distance_px,
    modelRelayVisualServoContext.distance_px,
    record(modelRelayVisionContext.pixel_servo_hint).distance_px,
  );
  const shadowEvidenceTone = simulationReady
    ? "ok"
    : Object.keys(simulationReport).length
      ? "idle"
      : "limited";
  const actionSummary = text(
    modelRelaySuggestion.detail ?? modelRelayResponse.summary ?? actionCandidate.summary ?? actionCandidate.type,
    "等待 dry-run 动作候选",
  );
  const languageOperationMode = text(languageGate.ai_operation_mode, "") || text(languageGate.operation_mode, "");
  const operationMode = text(
    (routedOperationMode
      || languageOperationMode)
      ?? modelRelayResponse.ai_operation_mode
      ?? actionCandidate.ai_operation_mode
      ?? (stereoTargetLabel ? "object_fetch_vla_lite" : ""),
    "waiting_for_voice_route",
  );
  const executionMode = text(
    safetyStatus.execution_mode
      ?? safetyPayload.execution_mode
      ?? modelRelayResponse.execution_mode
      ?? actionCandidate.execution_mode,
    motionAllowed ? "bench_motion_allowed_candidate" : "dry_run_only",
  );
  const targetAllowlist = asArray<unknown>(
    routePreview.target_allowlist
      ?? languageGate.target_allowlist
      ?? modelRelayResponse.target_allowlist
      ?? actionCandidate.target_allowlist,
  )
    .map((item) => text(item, ""))
    .filter(Boolean);
  const targetAllowlistText = targetAllowlist.length ? targetAllowlist.join(", ") : "cup, bottle";
  const stereoTsUnix = timestampUnixFromRows(
    stereoPayload.frame_ts_unix,
    stereoPayload.ts_unix,
    stereoPayload.timestamp_unix,
    stereoVision,
  );
  const stereoFreshness = freshness(stereoTsUnix, Date.now());
  const stereoDisparity = Number(stereoObservation.horizontal_disparity_px);
  const stereoHasDisparity = Number.isFinite(stereoDisparity);
  const stereoRecentFrames = stereoRecentEvents
    .map((event) => {
      const payload = payloadOf(event);
      const target = record(payload.target_object);
      const observation = record(target.stereo_observation);
      const label = text(target.label, "");
      const disparity = Number(observation.horizontal_disparity_px);
      return {
        label,
        disparity: Number.isFinite(disparity) ? disparity : null,
        locked: Boolean(label && Number.isFinite(disparity)),
      };
    });
  const currentTargetMemory = visualSampleFromObject(stereoTarget, stereoPayload, "target");
  const currentEndEffectorMemory = visualSampleFromObject(stereoEndEffector, stereoPayload, "end_effector");
  const recentTargetMemory = newestVisualSample([
    currentTargetMemory,
    ...stereoRecentEvents.map((event) => {
      const payload = payloadOf(event);
      return visualSampleFromObject(payload.target_object, payload, "target");
    }),
  ]);
  const recentEndEffectorMemory = newestVisualSample([
    currentEndEffectorMemory,
    ...stereoRecentEvents.map((event) => {
      const payload = payloadOf(event);
      return visualSampleFromObject(payload.end_effector_object, payload, "end_effector");
    }),
  ]);
  const targetMemoryFreshness = freshness(recentTargetMemory?.tsUnix ?? null, Date.now());
  const endEffectorMemoryFreshness = freshness(recentEndEffectorMemory?.tsUnix ?? null, Date.now());
  const visualMemoryNowMs = Date.now();
  const targetMemoryUsable = visualMemoryUsable(recentTargetMemory, visualMemoryNowMs);
  const endEffectorMemoryUsable = visualMemoryUsable(recentEndEffectorMemory, visualMemoryNowMs);
  const visualMemoryPairState = targetMemoryUsable && endEffectorMemoryUsable
    ? "memory_pair_ready"
    : targetMemoryUsable
      ? "waiting_end_effector_memory"
      : endEffectorMemoryUsable
        ? "waiting_target_memory"
        : "waiting_visual_memory";
  const stereoStableLabel = stereoTargetLabel || text(stereoRecentFrames.find((frame) => frame.label)?.label, "");
  const stereoLockedFrames = stereoRecentFrames.filter((frame) => (
    frame.locked && (!stereoStableLabel || frame.label === stereoStableLabel)
  ));
  const stereoSampleCount = stereoRecentFrames.length;
  const stereoDisparitySamples = stereoLockedFrames
    .map((frame) => frame.disparity)
    .filter((value): value is number => value !== null);
  const stereoDisparitySpread = stereoDisparitySamples.length >= 2
    ? Math.max(...stereoDisparitySamples) - Math.min(...stereoDisparitySamples)
    : null;
  const stereoTargetCenter = targetCenterFromObservation(stereoTarget, stereoObservation);
  const stereoEndEffectorObservation = record(stereoEndEffector.stereo_observation);
  const stereoEndEffectorCenter = targetCenterFromObservation(stereoEndEffector, stereoEndEffectorObservation);
  const stereoFrameSize = inferFrameSize(stereoPayload, stereoTarget, stereoObservation);
  const stereoImagePairRef = record(stereoPayload.image_pair_ref);
  const selectedDeviceIdForUrl = selected?.device_id ? encodeURIComponent(selected.device_id) : "";
  const stereoLeftKeyframeSrc = selected?.device_id
    ? withImageVersion(keyframeSrc(`/api/rehab-arm/v1/devices/${selectedDeviceIdForUrl}/camera/keyframes/stereo_left/latest/file`, apiBaseUrl), stereoTsUnix ?? selected?.last_upload_ts_unix)
    : "";
  const stereoRightKeyframeSrc = selected?.device_id
    ? withImageVersion(keyframeSrc(`/api/rehab-arm/v1/devices/${selectedDeviceIdForUrl}/camera/keyframes/stereo_right/latest/file`, apiBaseUrl), stereoTsUnix ?? selected?.last_upload_ts_unix)
    : "";
  const leftStereoImageSrc = withImageVersion(browserImageSrc(stereoImagePairRef.left_image_url ?? stereoTarget.image_ref, apiBaseUrl), stereoTsUnix ?? selected?.last_upload_ts_unix) || stereoLeftKeyframeSrc;
  const rightStereoImageSrc = withImageVersion(browserImageSrc(stereoImagePairRef.right_image_url ?? stereoObservation.right_image_ref, apiBaseUrl), stereoTsUnix ?? selected?.last_upload_ts_unix) || stereoRightKeyframeSrc;
  const leftTargetBbox = firstNumberTuple(4, stereoObservation.left_bbox_xywh, stereoTarget.bbox_xywh, stereoTarget.bbox);
  const rightTargetBbox = firstNumberTuple(4, stereoObservation.right_bbox_xywh);
  const leftEndEffectorBbox = firstNumberTuple(4, stereoEndEffectorObservation.left_bbox_xywh, stereoEndEffector.bbox_xywh, stereoEndEffector.bbox);
  const rightEndEffectorBbox = firstNumberTuple(4, stereoEndEffectorObservation.right_bbox_xywh);
  const leftDetectionPills = detectionPills(stereoPayload.detections, "left");
  const rightDetectionPills = detectionPills(stereoPayload.detections, "right");
  const visualEvidenceImageSource = leftStereoImageSrc && rightStereoImageSrc
    ? "左/右真帧"
    : leftStereoImageSrc || rightStereoImageSrc
      ? "单侧真帧"
      : "等图像";
  const visualEvidenceBoxSource = leftStereoImageSrc
    ? "NanoPi OpenCV 标注帧"
    : "等 OpenCV 标注图";
  const endEffectorEvidenceText = stereoEndEffectorLabel && (leftEndEffectorBbox || rightEndEffectorBbox)
    ? `${stereoEndEffectorLabel} 已入画`
    : stereoEndEffectorLabel
      ? `${stereoEndEffectorLabel} 等 bbox`
      : "末端待识别";
  const visualEvidencePairing = stereoLoopProgressText !== "等待循环"
    ? stereoLoopProgressText
    : text(stereoPayload.schema_version, "等待 stereo payload");
  const targetQualityRejectedCount = Number(stereoTargetQualityGate.rejected_count);
  const targetQualityReasons = Object.entries(record(stereoTargetQualityGate.rejection_reasons))
    .map(([reason, count]) => `${reason.replaceAll("_", " ")} ${count}`)
    .slice(0, 3);
  const targetQualityGateTone = !stereoHasTargetQualityGate
    ? "idle"
    : stereoTargetQualityGateState === "candidate_accepted"
      ? "ok"
      : "limited";
  const targetQualityGateTitle = !stereoHasTargetQualityGate
    ? "等待质量门"
    : stereoTargetQualityGateState === "candidate_accepted"
      ? "目标候选通过"
      : "未接受目标";
  const targetQualityGateDetail = !stereoHasTargetQualityGate
    ? "等待 NanoPi 上报 target_quality_gate"
    : stereoTargetQualityGateState === "candidate_accepted"
      ? "候选框通过尺寸、边界和轮廓检查"
      : targetQualityReasons.length
        ? `拒绝 ${Number.isFinite(targetQualityRejectedCount) ? targetQualityRejectedCount : targetQualityReasons.length} 个：${targetQualityReasons.join("；")}`
        : "粗检测候选未通过物理合理性检查";
  const computedPixelServo = pixelServoSuggestion({
    center: stereoTargetCenter,
    frame: stereoFrameSize,
    disparity: stereoHasDisparity ? stereoDisparity : null,
    disparitySpread: stereoDisparitySpread,
    lockedFrames: stereoLockedFrames.length,
    sampleCount: stereoSampleCount,
    fresh: stereoFreshness.state !== "stale",
  });
  const payloadPixelServoHint = record(stereoPayload.pixel_servo_hint);
  const payloadPixelServoOffsetX = Number(payloadPixelServoHint.offset_x_norm);
  const payloadPixelServoOffsetY = Number(payloadPixelServoHint.offset_y_norm);
  const payloadPixelServoNextStep = text(payloadPixelServoHint.next_step, "");
  const payloadPixelServoState = text(payloadPixelServoHint.state, "");
  const pixelServo = stereoFreshness.state === "stale" || !Object.keys(payloadPixelServoHint).length
    ? computedPixelServo
    : {
      ...computedPixelServo,
      state: payloadPixelServoState || computedPixelServo.state,
      title: payloadPixelServoState === "centered_single_frame"
        ? "像素居中待复核"
        : payloadPixelServoState === "waiting_stereo_match"
          ? "等待右图匹配"
          : payloadPixelServoNextStep.includes("left")
            ? "目标偏左 · 像素修正"
            : payloadPixelServoNextStep.includes("right")
              ? "目标偏右 · 像素修正"
              : payloadPixelServoNextStep.includes("up")
                ? "目标偏上 · 像素修正"
                : payloadPixelServoNextStep.includes("down")
                  ? "目标偏下 · 像素修正"
                  : computedPixelServo.title,
      summary: text(payloadPixelServoHint.control_boundary, "") === "pixel_servo_hint_only_not_motion_permission"
        ? "NanoPi 已上报单帧像素伺服提示；仍只作为 dry-run 解释，不代表真实三维坐标。"
        : computedPixelServo.summary,
      nextStep: payloadPixelServoNextStep || computedPixelServo.nextStep,
      targetOffsetText: Number.isFinite(payloadPixelServoOffsetX) && Number.isFinite(payloadPixelServoOffsetY)
        ? `x ${Math.round(payloadPixelServoOffsetX * 100)}% · y ${Math.round(payloadPixelServoOffsetY * 100)}%`
        : computedPixelServo.targetOffsetText,
      stabilityText: `payload ${text(payloadPixelServoHint.schema_version, "pixel_servo_hint")}；${computedPixelServo.stabilityText}`,
    };
  const stereoStabilityText = stereoSampleCount
    ? `${stereoLockedFrames.length}/${stereoSampleCount} 帧锁定${stereoStableLabel ? ` ${stereoStableLabel}` : ""}`
    : "暂无多帧历史";
  const stereoPayloadStabilityText = stereoHasPayloadVisualLock
    ? [
      Number.isFinite(stereoVisualLockSameFrames) && Number.isFinite(stereoVisualLockSamples)
        ? `${stereoVisualLockSameFrames}/${stereoVisualLockSamples} 帧锁定${stereoVisualLockCandidate ? ` ${stereoVisualLockCandidate}` : ""}`
        : "",
      Number.isFinite(stereoVisualLockStereoFrames) ? `双目 ${stereoVisualLockStereoFrames}` : "",
      Number.isFinite(stereoVisualLockJitterPx) ? `抖动 ${compactNumberText(stereoVisualLockJitterPx, " px")}` : "",
      Number.isFinite(stereoVisualLockDisparitySpreadPx) ? `视差波动 ${compactNumberText(stereoVisualLockDisparitySpreadPx, " px")}` : "",
    ].filter(Boolean).join("；")
    : "";
  const stereoVisibleStabilityText = stereoPayloadStabilityText || stereoStabilityText;
  const visualLockRequiredFrames = Number.isFinite(stereoVisualLockSamples) && stereoVisualLockSamples > 0
    ? Math.max(3, stereoVisualLockSamples)
    : Math.max(3, stereoSampleCount || 3);
  const visualLockObservedFrames = Number.isFinite(stereoVisualLockSameFrames)
    ? Math.max(0, stereoVisualLockSameFrames)
    : stereoLockedFrames.length;
  const visualLockStereoFrames = Number.isFinite(stereoVisualLockStereoFrames)
    ? Math.max(0, stereoVisualLockStereoFrames)
    : stereoLockedFrames.length;
  const visualLockProgress = clamp01(visualLockObservedFrames / visualLockRequiredFrames);
  const visualLockMatchProgress = clamp01(visualLockStereoFrames / visualLockRequiredFrames);
  const visualLockJitterText = Number.isFinite(stereoVisualLockJitterPx)
    ? compactNumberText(stereoVisualLockJitterPx, " px")
    : stereoDisparitySpread !== null
      ? compactNumberText(stereoDisparitySpread, " px disparity")
      : "等待多帧";
  const visualLockConfidenceText = stereoVisualLockStable
    ? "稳定候选"
    : visualLockObservedFrames > 0
      ? "积累中"
      : "等待目标";
  const endEffectorVisible = Boolean(stereoEndEffectorLabel && (leftEndEffectorBbox || rightEndEffectorBbox || stereoEndEffectorCenter));
  const rememberedTargetCenter = stereoTargetCenter ?? recentTargetMemory?.center ?? null;
  const rememberedEndEffectorCenter = stereoEndEffectorCenter ?? recentEndEffectorMemory?.center ?? null;
  const visualServoDelta = useMemo(
    () => rememberedTargetCenter && rememberedEndEffectorCenter
      ? [rememberedTargetCenter[0] - rememberedEndEffectorCenter[0], rememberedTargetCenter[1] - rememberedEndEffectorCenter[1]]
      : null,
    [rememberedEndEffectorCenter, rememberedTargetCenter],
  );
  const visualServoDistancePx = visualServoDelta
    ? Math.hypot(visualServoDelta[0], visualServoDelta[1])
    : null;
  const visualServoReady = Boolean(targetMemoryUsable && endEffectorMemoryUsable && visualServoDistancePx !== null);
  const visualServoStateText = visualServoReady
    ? (endEffectorVisible && stereoTargetLabel ? "当前帧闭环" : "视觉记忆闭环")
    : targetMemoryUsable
      ? "等待末端记忆"
      : endEffectorMemoryUsable
        ? "等待目标记忆"
        : "等待视觉记忆";
  const visualServoDistanceText = visualServoDistancePx !== null
    ? compactNumberText(visualServoDistancePx, " px")
    : "等待目标+末端";
  const cameraToRobotReady = stereoPayload.camera_to_robot_calibrated === true || modelRelayVisionContext.camera_to_robot_calibrated === true;
  const stereoLoopTone = !stereoHasContext || stereoFreshness.state === "stale"
    ? "limited"
    : stereoVisualLockStable || (stereoTargetLabel && stereoHasDisparity && (!stereoSampleCount || stereoLockedFrames.length >= Math.min(3, stereoSampleCount)))
      ? "ok"
      : "idle";
  const stereoLoopState = !stereoHasContext
    ? "等待 V 输入"
    : stereoFreshness.state === "stale"
      ? "视觉过期 hold"
      : stereoVisualLockStable
        ? "多帧稳定"
        : stereoTargetLabel && stereoHasDisparity && (!stereoSampleCount || stereoLockedFrames.length >= Math.min(3, stereoSampleCount))
          ? "目标锁定"
          : stereoHasPayloadVisualLock && stereoVisualLockState
            ? "继续观察"
        : "继续观察";
  const stereoLoopDetail = stereoHasContext
    ? [
      `更新 ${stereoFreshness.text}`,
      stereoHasFrameTiming ? `V 耗时 ${compactNumberText(stereoFrameProcessMs, " ms")}` : "",
      stereoVisibleStabilityText,
      stereoHasPayloadVisualLock && stereoVisualLockState ? `锁定状态 ${stereoVisualLockState}` : "",
      visualServoStateText,
      stereoHasDisparity ? `视差 ${compactNumberText(stereoDisparity, " px")}` : "无左右匹配",
      stereoDisparitySpread !== null ? `波动 ${compactNumberText(stereoDisparitySpread, " px")}` : "",
      stereoDepth !== null ? `深度 ${compactNumberText(stereoDepth, " m")}` : "未标定深度",
      motionAllowed ? "M33 允许候选" : "保持 dry-run/hold",
    ].filter(Boolean).join("；")
    : "等待 NanoPi 双目上传 stereo_vision_context";
  const vlaLiteLoopState = !effectiveLanguageSummary || effectiveLanguageSummary === "等待 XiaoZhi listen/audio"
    ? "waiting_language"
    : !stereoHasContext
      ? "waiting_vision"
      : stereoFreshness.state === "stale"
        ? "hold_stale_vision"
        : !stereoTargetLabel || !stereoHasDisparity
          ? "tracking_target"
          : !visualServoReady
            ? "hold_end_effector"
          : stereoDepth === null
            ? "hold_uncalibrated_depth"
            : Object.keys(actionCandidate).length || relayState === "ok"
              ? "candidate_ready"
              : "tracking_target";
  const vlaLiteLoopTone = vlaLiteLoopState === "candidate_ready"
    ? "ok"
    : vlaLiteLoopState.startsWith("hold_")
      ? "limited"
      : "idle";
  const vlaLiteLoopReason = {
    waiting_language: "等待小智给出任务意图",
    waiting_vision: "等待 NanoPi 双目 V 输入",
    tracking_target: "视觉正在持续跟踪目标，A 仍只生成 dry-run 候选",
    hold_stale_vision: "视觉数据过期，必须重新观察",
    hold_end_effector: "目标已入画，但还没有同时识别机械臂末端",
    hold_uncalibrated_depth: "未完成双目标定，不能把像素视差当机械臂坐标",
    candidate_ready: "已有高层候选，可进入仿真/dry-run 审核",
  }[vlaLiteLoopState];
  const hasActionCandidate = Object.keys(actionCandidate).length > 0 || relayState === "ok";
  const hasLanguageTask = Boolean(effectiveLanguageSummary && effectiveLanguageSummary !== "等待 XiaoZhi listen/audio");
  const hasStereoTargetForGate = Boolean(stereoHasContext && stereoTargetLabel && stereoHasDisparity);
  const dryRunGateState = !hasLanguageTask
    ? "hold_language"
    : !hasStereoTargetForGate
      ? "hold_vision"
    : stereoFreshness.state === "stale"
      ? "hold_stale_vision"
      : !visualServoReady
        ? "hold_end_effector"
      : !stereoVisualLockStable
          ? "observe_more"
          : hasActionCandidate
            ? "candidate_ready"
            : "visual_lock_ready";
  const dryRunCandidateAllowed = dryRunGateState === "visual_lock_ready" || dryRunGateState === "candidate_ready";
  const dryRunGateTone = dryRunGateState === "candidate_ready" || dryRunGateState === "visual_lock_ready"
    ? "ok"
    : dryRunGateState === "observe_more"
      ? "idle"
      : "limited";
  const dryRunGateReason = {
    hold_language: "A 等待小智/语言路由给出取物或训练任务，不凭空生成动作。",
    hold_vision: "A 等待 NanoPi 双目给出同类左右目目标，当前只保持观察。",
    hold_stale_vision: "视觉帧已经过期，A 不使用旧坐标生成逼近候选。",
    hold_end_effector: "A 至少需要目标物和机械臂末端的短时视觉记忆，才能形成 dry-run 视觉逼近闭环。",
    observe_more: "目标还没有通过多帧视觉锁定，A 继续观察并保持 hold_observe。",
    visual_lock_ready: "目标通过多帧锁定，A 可以展示 dry-run 像素逼近候选，但不下发运动。",
    candidate_ready: "已有高层建议或候选，下一步仍是仿真/dry-run 审核，不是真机运动。",
  }[dryRunGateState];
  const actionGateTitle = dryRunCandidateAllowed
    ? dryRunGateLabel(dryRunGateState)
    : "A hold_observe";
  const actionGateSummary = dryRunCandidateAllowed
    ? `${dryRunGateReason} 建议标签：${pixelServo.nextStep}。`
    : dryRunGateReason;
  const routeModeFallback: Record<string, string> = {
    object_fetch_request: "fetch_object",
    training_start_request: "training",
    training_summary_request: "training",
    assistive_emg_request: "assistive_emg",
    diagnostic_request: "diagnostics",
    data_collection_request: "data_collection",
    daily_chat: "chat",
  };
  const backendModeMaturity = record(selected?.mode_maturity);
  const backendModeRows = asArray<AnyRecord>(backendModeMaturity.modes);
  const currentSemanticMode = text(
    backendModeMaturity.active_mode,
    text(modelRelaySemantic.mode, routeModeFallback[routeClass] || ""),
  );
  const generateIkCandidate = useCallback(async () => {
    if (!selected) return;
    const draft = ikDraftRef.current;
    const target = {
      x_m: Number(draft.target.x_m),
      y_m: Number(draft.target.y_m),
      z_m: Number(draft.target.z_m),
    };
    if (!Number.isFinite(target.x_m) || !Number.isFinite(target.y_m) || !Number.isFinite(target.z_m)) {
      setIkCandidateState("error");
      setIkCandidateError("robot_frame 坐标必须是米制数字");
      return;
    }
    setIkCandidateState("generating");
    setIkCandidateError("");
    const approachParts = draft.approach.split(/[,\s]+/).map((item) => Number(item)).filter((item) => Number.isFinite(item));
    try {
      const response = await fetch(
        `/api/proxy/rehab-arm/v1/projects/${encodeURIComponent(projectId)}/devices/${encodeURIComponent(selected.device_id)}/ik-candidates`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            schema_version: "rehab_arm_ik_candidate_request_v1",
            robot_id: selected.robot_id || "rehab-arm-alpha",
            device_id: selected.device_id,
            project_id: projectId,
            target_robot_frame: target,
            approach_vector: approachParts.length >= 3 ? { x: approachParts[0], y: approachParts[1], z: approachParts[2] } : null,
            gripper_orientation: draft.orientation,
            source: draft.source,
            semantic_mode: currentSemanticMode || "fetch_object",
            context_refs: {
              vision_context: "latest_stereo_vision_context",
              robot_render_state: "latest_robot_render_state",
              simulation_readiness: "latest_simulation_readiness",
            },
            control_boundary: "ik_candidate_request_evidence_only_not_motion_permission",
          }),
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(text(payload.detail, "IK candidate request failed"));
      const data = record(payload.data ?? payload);
      setLastIkCandidate(data);
      setIkCandidateState("ready");
      void refreshLiveDashboard(true);
    } catch (error) {
      setIkCandidateState("error");
      setIkCandidateError(error instanceof Error ? error.message : "IK candidate request failed");
    }
  }, [currentSemanticMode, projectId, refreshLiveDashboard, selected]);
  const exportIkCandidateEvidence = useCallback(() => {
    const draft = ikDraftRef.current;
    const snapshot = {
      exported_at: new Date().toISOString(),
      project_id: projectId,
      selected_device: {
        device_id: selected?.device_id ?? null,
        robot_id: selected?.robot_id ?? null,
      },
      request: {
        target_robot_frame: {
          x_m: Number(draft.target.x_m),
          y_m: Number(draft.target.y_m),
          z_m: Number(draft.target.z_m),
        },
        approach_vector: draft.approach,
        gripper_orientation: draft.orientation,
        source: draft.source,
      },
      ik_candidate: ikCandidate,
      safety: {
        m33_final_authority: Boolean(liveDashboard.safety_boundary.m33_final_authority),
        note: "IK 结果只是 dry-run 候选证据；真实运动仍需 L -> V -> A -> MuJoCo/URDF -> M33 安全裁决 -> NanoPi/M33 真机链路。",
      },
      control_boundary: "ik_candidate_evidence_only_not_motion_permission",
    };
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `rehab-arm-ik-candidate-${projectId}-${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, [ikCandidate, liveDashboard.safety_boundary.m33_final_authority, projectId, selected]);
  const fallbackModeOverviewRows = [
    {
      mode: "fetch_object",
      title: "取物 VLA-lite",
      stage: currentSemanticMode === "fetch_object" ? dryRunGateLabel(dryRunGateState) : "预留 V 闭环",
      detail: "L 选目标，V 找目标和末端，A 只生成 dry-run / MuJoCo 候选。",
      next: stereoHasContext ? "补真实目标验收和后续标定" : "等待 NanoPi V",
      tone: currentSemanticMode === "fetch_object" ? dryRunGateTone : "idle",
    },
    {
      mode: "training",
      title: "训练计划",
      stage: currentSemanticMode === "training" ? "训练语义已命中" : "等待训练意图",
      detail: "APP 训练库通过 BLE 到 M33；APP 端 AI 后续填充训练计划表。",
      next: "接 APP/BLE/M33 训练库",
      tone: currentSemanticMode === "training" ? "ok" : "idle",
    },
    {
      mode: "assistive_emg",
      title: "肌电助力",
      stage: currentSemanticMode === "assistive_emg" ? "助力语义已命中" : "等待 EMG 意图",
      detail: "4 通道肌电由 M55 推测动作意图，M33 仍是最终安全门。",
      next: "接 M55 意图和肌肉力图",
      tone: currentSemanticMode === "assistive_emg" ? "ok" : "idle",
    },
    {
      mode: "vision_servo",
      title: "视觉伺服",
      stage: currentSemanticMode === "vision_servo" ? "视觉伺服已命中" : "共享 V 证据",
      detail: "复用目标/末端误差；未来优先使用深度和机械臂坐标系。",
      next: cameraToRobotReady ? "可展示标定坐标" : "等待手眼/坐标标定",
      tone: currentSemanticMode === "vision_servo" ? "ok" : stereoHasContext ? "idle" : "limited",
    },
    {
      mode: "safety_review",
      title: "安全审核",
      stage: currentSemanticMode === "safety_review" ? "审核语义已命中" : "默认总门控",
      detail: "汇总 M33、安全状态、MuJoCo、操作员确认；不直接批准运动。",
      next: motionAllowed ? "仍需人工/M33复核" : "等待 M33 fresh",
      tone: currentSemanticMode === "safety_review" ? "ok" : "idle",
    },
    {
      mode: "diagnostics",
      title: "只读诊断",
      stage: currentSemanticMode === "diagnostics" ? "诊断语义已命中" : "可随时进入",
      detail: "摄像头、CAN、ROS、M33/M55 和仿真状态只读汇总。",
      next: "补 topic/log/CAN 快照",
      tone: currentSemanticMode === "diagnostics" ? "ok" : "idle",
    },
    {
      mode: "data_collection",
      title: "数据采集",
      stage: currentSemanticMode === "data_collection" ? "采集语义已命中" : "等待采集任务",
      detail: "相机、肌电、CAN、ROS 和语言标签统一入数据集索引。",
      next: "补采集批次和标签表",
      tone: currentSemanticMode === "data_collection" ? "ok" : "idle",
    },
    {
      mode: "chat",
      title: "日常聊天",
      stage: currentSemanticMode === "chat" ? "聊天不进 VLA" : "L 共享入口",
      detail: "小智可聊天，但 chat 模式不生成机器人动作。",
      next: "保持与 VLA 指令隔离",
      tone: currentSemanticMode === "chat" ? "ok" : "idle",
    },
  ];
  const modeOverviewRows = backendModeRows.length
    ? backendModeRows.map((item) => ({
        mode: text(item.mode, "chat"),
        title: text(item.label ?? item.title, semanticActionModeLabel(item.mode)),
        stage: text(item.stage, "等待模式状态"),
        detail: text(item.detail, text(item.motion_boundary, "status only")),
        next: text(item.next_step ?? item.next, "等待下一步"),
        tone: modeTone(item.tone),
      }))
    : fallbackModeOverviewRows;
  const displayModeOverviewRows = modeOverviewRows.map((item) => ({
    ...item,
    stage: modeStageText(item.stage),
    detail: modeBoundaryText(item.detail),
    next: modeNextText(item.next),
  }));
  const modeOverviewBoundary = text(
    backendModeMaturity.control_boundary,
    "mode_maturity_status_only_not_motion_permission",
  );
  const modeOverviewBoundaryText = modeOverviewBoundary === "mode_maturity_status_only_not_motion_permission"
    ? "模式成熟度仅作状态展示，不是运动许可"
    : modeOverviewBoundary.replaceAll("_", " ");
  const loopHealthRows = [
    {
      key: "fetch",
      title: "取物闭环",
      stage: dryRunGateLabel(dryRunGateState),
      evidence: visualServoReady ? `V 记忆 ${visualServoDistanceText}` : visualServoStateText,
      next: dryRunCandidateAllowed ? "进 MuJoCo/dry-run 审核" : "继续观察",
      tone: dryRunGateTone,
    },
    {
      key: "training",
      title: "训练闭环",
      stage: currentSemanticMode === "training" ? "L 已路由训练" : "等待训练 L",
      evidence: "APP 训练库/BLE/M33 预留",
      next: "接 APP 训练计划表",
      tone: currentSemanticMode === "training" ? "ok" : "idle",
    },
    {
      key: "assist",
      title: "肌电助力闭环",
      stage: currentSemanticMode === "assistive_emg" ? "L 已路由助力" : "等待 EMG 意图",
      evidence: "M55 四通道肌电意图预留",
      next: "接 M55 推理日志和肌肉力图",
      tone: currentSemanticMode === "assistive_emg" ? "ok" : "idle",
    },
    {
      key: "shadow",
      title: "仿真闭环",
      stage: simulationReady ? "MuJoCo 已回传" : "等待 shadow",
      evidence: simulationPlanState,
      next: simulationReady ? "人工审核证据" : "仿真主机上传 report",
      tone: simulationReady ? "ok" : "idle",
    },
    {
      key: "safety",
      title: "安全闭环",
      stage: motionAllowed ? "M33 候选允许" : "真机锁定",
      evidence: liveDashboard.safety_boundary.m33_final_authority ? "M33 final authority" : "等待安全声明",
      next: motionAllowed ? "仍需人审/仿真" : "保持 dry-run",
      tone: motionAllowed ? "limited" : "ok",
    },
  ];
  const nonVisionProgressRows = [
    {
      key: "training-plan",
      title: "训练计划链路",
      owner: "APP / M33",
      status: currentSemanticMode === "training" ? "L 已命中训练" : "可独立推进",
      detail: "先把训练库、训练目标、患者约束和计划表结构跑通；不依赖杯子识别。",
      next: "APP 通过 BLE 把训练目标交给 M33",
      tone: currentSemanticMode === "training" ? "ok" : "idle",
    },
    {
      key: "emg-assist",
      title: "肌电助力链路",
      owner: "M55 / M33",
      status: currentSemanticMode === "assistive_emg" ? "L 已命中助力" : "等待 EMG 流",
      detail: "四通道肌电先变成动作意图和助力方向，M33 只接收受限建议。",
      next: "显示肌肉发力和助力方向",
      tone: currentSemanticMode === "assistive_emg" ? "ok" : "idle",
    },
    {
      key: "shadow-review",
      title: "仿真审核链路",
      owner: "MuJoCo Host",
      status: simulationReady ? "shadow 证据已回传" : "等待仿真回传",
      detail: simulationReady ? simulationPlanState : "无真实识别时仍可用预设任务/日志验证 A 到仿真的链路。",
      next: simulationReady ? "把仿真结果进入人审卡" : "仿真主机上传 simulation_readiness",
      tone: simulationReady ? "ok" : "idle",
    },
    {
      key: "dataset",
      title: "数据采集链路",
      owner: "NanoPi / Runner",
      status: qualityReady ? "数据质量可用" : "可先建采集批次",
      detail: "当前摄像头、L 指令、EMG、CAN、仿真日志都可以先入统一数据集索引。",
      next: "补 session、label、QA、训练回流",
      tone: qualityReady ? "ok" : "idle",
    },
  ];
  const trainingPipelineSteps = [
    { key: "l", label: "L 训练意图", state: currentSemanticMode === "training" ? "已命中" : "等待", tone: currentSemanticMode === "training" ? "ok" : "idle" },
    { key: "library", label: "APP 训练库", state: "预留计划表", tone: "idle" },
    { key: "ble", label: "BLE 到 M33", state: "待接入", tone: "idle" },
    { key: "review", label: "安全/报告", state: "只读审核", tone: "ok" },
  ];
  const assistivePipelineSteps = [
    { key: "emg", label: "四通道 EMG", state: currentSemanticMode === "assistive_emg" ? "等待数据" : "未触发", tone: currentSemanticMode === "assistive_emg" ? "limited" : "idle" },
    { key: "m55", label: "M55 意图", state: "模型槽预留", tone: "idle" },
    { key: "m33", label: "M33 门控", state: liveDashboard.safety_boundary.m33_final_authority ? "最终裁决" : "等待声明", tone: liveDashboard.safety_boundary.m33_final_authority ? "ok" : "limited" },
    { key: "assist", label: "助力方向", state: "展示优先", tone: "idle" },
  ];
  const vlaEvidenceLadder = [
    {
      step: "1",
      title: "目标质量门",
      state: targetQualityGateTitle,
      detail: targetQualityGateDetail,
      tone: targetQualityGateTone,
    },
    {
      step: "2",
      title: "末端可见",
      state: endEffectorMemoryUsable ? `记忆 ${endEffectorMemoryFreshness.text}` : "等待末端",
      detail: endEffectorVisible ? endEffectorEvidenceText : `最近末端：${recentEndEffectorMemory?.label ?? "无"} · ${endEffectorMemoryFreshness.text}`,
      tone: endEffectorMemoryUsable ? "ok" : targetMemoryUsable ? "limited" : "idle",
    },
    {
      step: "3",
      title: "多帧视觉锁",
      state: visualLockConfidenceText,
      detail: stereoVisibleStabilityText,
      tone: stereoVisualLockStable ? "ok" : visualLockObservedFrames > 0 ? "idle" : "limited",
    },
    {
      step: "4",
      title: "A dry-run gate",
      state: dryRunGateLabel(dryRunGateState),
      detail: dryRunGateReason,
      tone: dryRunGateTone,
    },
  ];
  const topologyNodes = [
    {
      key: "l",
      eyebrow: "M55 / XiaoZhi",
      title: "语言意图",
      value: currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待 L",
      detail: effectiveLanguageSummary,
      tone: currentSemanticMode && currentSemanticMode !== "chat" ? "ok" : "idle",
    },
    {
      key: "v",
      eyebrow: "NanoPi Vision",
      title: "视觉证据",
      value: visualServoReady ? "目标+末端记忆" : targetMemoryUsable ? `目标 ${recentTargetMemory?.label}` : endEffectorMemoryUsable ? "末端记忆" : "等待画面",
      detail: `${targetQualityGateTitle} · ${visualMemoryPairState.replaceAll("_", " ")}`,
      tone: visualServoReady ? "ok" : targetMemoryUsable || endEffectorMemoryUsable ? "limited" : "idle",
    },
    {
      key: "a",
      eyebrow: "Platform A",
      title: "动作规划",
      value: dryRunGateLabel(dryRunGateState),
      detail: dryRunCandidateAllowed ? "可进入 dry-run 审核" : "证据不足，保持观察",
      tone: dryRunGateTone,
    },
    {
      key: "sim",
      eyebrow: "MuJoCo Shadow",
      title: "仿真证据",
      value: simulationReady ? "shadow 已跑通" : "等待 shadow",
      detail: simulationPlanState,
      tone: simulationReady ? "ok" : "idle",
    },
    {
      key: "safe",
      eyebrow: "M33 Safety",
      title: "最终裁决",
      value: motionAllowed ? "允许运动" : "锁定真机",
      detail: motionAllowed ? "仍需人工复核" : "只读 / dry-run",
      tone: motionAllowed ? "ok" : "limited",
    },
  ];
  const stitchFrameRef = useRef<HTMLIFrameElement | null>(null);
  const stitchSourceByModule: Record<RehabWorkspaceModule, string> = {
    overview: "/rehab-stitch/overview.html",
    vision: "/rehab-stitch/vision.html",
    digital_twin: "/rehab-stitch/twin.html",
    muscle_assist: "/rehab-stitch/muscle.html",
    ai_model: "/rehab-stitch/model-lab.html",
    mode_router: "/rehab-stitch/router.html",
    training: "/rehab-stitch/training.html",
    data_hub: "/rehab-stitch/data.html",
    action_planner: "/rehab-stitch/planner.html",
    diagnostics: "/rehab-stitch/diagnostics.html",
    logs: "/rehab-stitch/logs.html",
  };
  const downloadDiagnosticsSnapshot = useCallback(() => {
    const snapshot = {
      exported_at: new Date().toISOString(),
      project_id: projectId,
      boundary: "read_only_browser_export_not_motion_permission",
      selected_device: {
        device_id: selected?.device_id ?? null,
        device_code: publicDeviceCode(selected, selectedIndex),
        robot_id: selected?.robot_id ?? null,
        online_state: selected?.online_state ?? "unknown",
        last_upload: formatTime(selected?.last_upload_ts_unix),
      },
      vla: {
        language_summary: effectiveLanguageSummary || "waiting",
        semantic_mode: currentSemanticMode || "waiting",
        semantic_mode_label: currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待 L",
        vision: {
          target: stereoTargetLabel || "waiting_target",
          end_effector: stereoEndEffectorLabel || "waiting_end_effector",
          state: visualServoStateText,
          distance: visualServoDistanceText,
          depth_m: stereoDepth ?? null,
        },
        action: {
          dry_run_gate: dryRunGateLabel(dryRunGateState),
          dry_run_reason: dryRunGateReason,
          motion_allowed_candidate: motionAllowed,
        },
      },
      simulation: {
        ready: simulationReady,
        plan_state: simulationPlanState,
      },
      safety: {
        m33_final_authority: liveDashboard.safety_boundary.m33_final_authority,
        current_state: stateText(currentSafetyState),
        motion_allowed_candidate: motionAllowed,
        note: "M33 remains final authority; this export is evidence only.",
      },
      can_and_wiring: {
        motor_count: motors.length,
        abnormal_count: wiringBadCount,
        overall: wiringHealth.overall || "unknown",
      },
      recent_events: liveDashboard.recent_events.slice(0, 20).map((event) => ({
        record_type: event.record_type,
        title: eventTitle(event),
        device_id: event.device_id,
        ts_unix: event.ts_unix,
        time: formatTime(event.ts_unix),
        payload: payloadOf(event),
      })),
    };
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `rehab-arm-diagnostics-${projectId}-${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, [
    currentSafetyState,
    currentSemanticMode,
    dryRunGateReason,
    dryRunGateState,
    effectiveLanguageSummary,
    liveDashboard.recent_events,
    liveDashboard.safety_boundary.m33_final_authority,
    motionAllowed,
    motors.length,
    projectId,
    selected,
    selectedIndex,
    simulationPlanState,
    simulationReady,
    stereoDepth,
    stereoEndEffectorLabel,
    stereoTargetLabel,
    visualServoDistanceText,
    visualServoStateText,
    wiringBadCount,
    wiringHealth.overall,
  ]);
  const updateStitchFrame = useCallback(() => {
    const doc = stitchFrameRef.current?.contentDocument;
    if (!doc?.body || !doc.head) {
      if (twinRuntimeHost) setTwinRuntimeHost(null);
      return;
    }

    const setText = (selector: string, value: string) => {
      const node = doc.querySelector<HTMLElement>(selector);
      if (node) node.textContent = value;
    };
    const setHtml = (selector: string, value: string) => {
      const node = doc.querySelector<HTMLElement>(selector);
      if (node) node.innerHTML = value;
    };
    const setAllText = (selector: string, values: string[]) => {
      doc.querySelectorAll<HTMLElement>(selector).forEach((node, index) => {
        const value = values[index];
        if (value !== undefined) node.textContent = value;
      });
    };
    const setBg = (node: HTMLElement | undefined, imageSrc: string) => {
      if (!node || !imageSrc) return;
      node.style.backgroundImage = `url("${imageSrc}")`;
      node.style.backgroundSize = "cover";
      node.style.backgroundPosition = "center";
    };
    const setNthText = (selector: string, index: number, value: string) => {
      const node = doc.querySelectorAll<HTMLElement>(selector)[index];
      if (node) node.textContent = value;
    };
    const replaceExactText = (pairs: Array<[string, string]>) => {
      const map = new Map(pairs);
      const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        const raw = node.nodeValue ?? "";
        const trimmed = raw.trim();
        const next = map.get(trimmed);
        if (next) node.nodeValue = raw.replace(trimmed, next);
        node = walker.nextNode();
      }
    };
    const setValueNearLabel = (labelPattern: RegExp, value: string) => {
      const labels = Array.from(doc.querySelectorAll<HTMLElement>("span, p, td, th, div"))
        .filter((node) => labelPattern.test(text(node.textContent, "")));
      const host = labels[0]?.parentElement;
      const target = host?.querySelector<HTMLElement>(".font-telemetry-data, strong, td:last-child, span:last-child");
      if (target) target.textContent = value;
    };
    const ensureStitchPanel = (id: string, html: string, className = "glass-panel") => {
      let panel = doc.getElementById(id);
      if (!panel) {
        panel = doc.createElement("section");
        panel.id = id;
        panel.className = `${className} codex-injected-panel`;
        const main = doc.querySelector("main") ?? doc.body;
        main.appendChild(panel);
      }
      panel.innerHTML = html;
      return panel as HTMLElement;
    };
    const escapeHtml = (value: unknown) => text(value, "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
    const poseValueText = (sample: AnyRecord | undefined) => {
      if (!sample) return "等待";
      const rawValue = sample.value ?? sample.position_rad ?? sample.position ?? sample.angle_deg;
      const value = Number(rawValue);
      return Number.isFinite(value) ? compactNumberText(value, sample.position_rad !== undefined ? "rad" : "°") : "等待";
    };
    const isActiveRoute = (route: RehabWorkspaceModule) => route === activeModule;
    const routeClass = (route: RehabWorkspaceModule) => (
      isActiveRoute(route)
        ? "w-full py-2 border-l-2 border-secondary-fixed-dim bg-secondary-container/10 text-secondary-fixed-dim scale-95"
        : "w-full py-2 border-l-2 border-transparent text-on-surface-variant hover:text-secondary-fixed-dim hover:bg-surface-container-high/40"
    );
    const insertUnifiedShell = () => {
      if (doc.getElementById("codex-unified-stitch-shell")) return;
      doc.body.querySelectorAll(":scope > header, :scope > aside, :scope > nav").forEach((node) => node.remove());
      const style = doc.createElement("style");
      style.id = "codex-unified-stitch-shell";
      style.textContent = `
        body > main {
          margin-left: 72px !important;
          margin-top: 56px !important;
          width: calc(100vw - 72px) !important;
          height: calc(100vh - 56px) !important;
        }
        body > div.flex-1 {
          margin-left: 72px !important;
          margin-top: 56px !important;
          width: calc(100vw - 72px) !important;
          height: calc(100vh - 56px) !important;
        }
        body > div.flex {
          margin-left: 72px !important;
          margin-top: 56px !important;
          width: calc(100vw - 72px) !important;
          height: calc(100vh - 56px) !important;
        }
        body > div.flex > nav:first-child,
        body > div.flex > aside:first-child {
          display: none !important;
        }
        body > div.flex > main {
          min-width: 0 !important;
          flex: 1 1 auto !important;
        }
        body > div.flex-1 > header.top-bar {
          display: none !important;
        }
        body > div.flex-1 > main {
          height: 100% !important;
        }
        body > main.scroll-container {
          height: calc(100vh - 56px) !important;
        }
        .stage-container {
          height: calc(100vh - 56px) !important;
        }
      `;
      doc.head.appendChild(style);
      const rail = doc.createElement("nav");
      rail.className = "fixed left-0 top-0 h-full w-[72px] border-r border-outline-variant bg-surface-dim/70 backdrop-blur-xl flex flex-col items-center py-3 z-50";
      rail.innerHTML = `
        <div class="mb-4 grid place-items-center text-primary font-bold">
          <span class="font-display-lg text-[22px] leading-none">V</span>
          <span class="font-telemetry-label text-[8px] leading-none mt-1">REHAB</span>
        </div>
        <div class="flex flex-col gap-1 items-center flex-1 w-full">
          <button data-codex-route="overview" class="${routeClass("overview")}" title="总控"><strong class="block font-telemetry-data text-[13px] leading-none">CMD</strong><span class="block font-telemetry-label text-[8px] mt-1">总控</span></button>
          <button data-codex-route="vision" class="${routeClass("vision")}" title="视觉"><strong class="block font-telemetry-data text-[13px] leading-none">V</strong><span class="block font-telemetry-label text-[8px] mt-1">视觉</span></button>
          <button data-codex-route="digital_twin" class="${routeClass("digital_twin")}" title="孪生"><strong class="block font-telemetry-data text-[13px] leading-none">3D</strong><span class="block font-telemetry-label text-[8px] mt-1">孪生</span></button>
          <button data-codex-route="muscle_assist" class="${routeClass("muscle_assist")}" title="肌电"><strong class="block font-telemetry-data text-[13px] leading-none">EMG</strong><span class="block font-telemetry-label text-[8px] mt-1">肌电</span></button>
          <button data-codex-route="ai_model" class="${routeClass("ai_model")}" title="AI模型"><strong class="block font-telemetry-data text-[13px] leading-none">AI</strong><span class="block font-telemetry-label text-[8px] mt-1">模型</span></button>
          <button data-codex-route="mode_router" class="${routeClass("mode_router")}" title="模式"><strong class="block font-telemetry-data text-[13px] leading-none">L</strong><span class="block font-telemetry-label text-[8px] mt-1">模式</span></button>
          <button data-codex-route="training" class="${routeClass("training")}" title="训练"><strong class="block font-telemetry-data text-[13px] leading-none">TRN</strong><span class="block font-telemetry-label text-[8px] mt-1">训练</span></button>
          <button data-codex-route="data_hub" class="${routeClass("data_hub")}" title="数据"><strong class="block font-telemetry-data text-[12px] leading-none">DATA</strong><span class="block font-telemetry-label text-[8px] mt-1">数据</span></button>
          <button data-codex-route="action_planner" class="${routeClass("action_planner")}" title="动作"><strong class="block font-telemetry-data text-[13px] leading-none">A</strong><span class="block font-telemetry-label text-[8px] mt-1">动作</span></button>
          <button data-codex-route="diagnostics" class="${routeClass("diagnostics")}" title="诊断"><strong class="block font-telemetry-data text-[13px] leading-none">IO</strong><span class="block font-telemetry-label text-[8px] mt-1">诊断</span></button>
          <button data-codex-route="logs" class="${routeClass("logs")}" title="日志"><strong class="block font-telemetry-data text-[13px] leading-none">LOG</strong><span class="block font-telemetry-label text-[8px] mt-1">日志</span></button>
        </div>
        <div class="mt-auto flex flex-col gap-2 items-center w-full">
          <button data-codex-estop="true" class="mx-2 mb-1 bg-error text-on-error font-bold p-1 text-[10px] leading-tight text-center uppercase">STOP</button>
        </div>
      `;
      doc.body.prepend(rail);
      const header = doc.createElement("header");
      header.className = "fixed top-0 right-0 left-[72px] h-[56px] flex justify-between items-center px-4 z-40 bg-gradient-to-b from-surface-dim to-transparent backdrop-blur-sm";
      const deviceButtons = devices.slice(0, 5).map((device, index) => {
        const active = device.device_id === selectedDeviceId;
        return `<button data-codex-device="${device.device_id}" class="px-3 py-1 font-telemetry-label text-[11px] ${active ? "bg-secondary-container/20 text-secondary-fixed-dim border-b-2 border-secondary-fixed-dim" : "text-on-surface-variant hover:text-secondary-fixed-dim"}">${publicDeviceCode(device, index)}</button>`;
      }).join("");
      header.innerHTML = `
        <div class="flex items-center gap-4 min-w-0">
          <h1 class="font-headline-md text-primary tracking-tight whitespace-nowrap">VLA 控制台</h1>
          <span class="h-4 w-px bg-outline-variant"></span>
          <div class="flex items-center gap-1 min-w-0 overflow-hidden">${deviceButtons || `<span class="font-telemetry-label text-on-surface-variant">等待设备</span>`}</div>
        </div>
        <div class="flex items-center gap-4">
          <span class="font-telemetry-label text-on-surface-variant">${pollState === "syncing" ? "SYNCING" : "LIVE"}</span>
          <span class="font-telemetry-label ${motionAllowed ? "text-secondary-fixed-dim" : "text-error"}">${motionAllowed ? "M33 CANDIDATE" : "READ ONLY"}</span>
          <button data-codex-estop="true" class="bg-error text-on-error px-4 py-1 font-telemetry-label text-[11px] font-bold">急停</button>
        </div>
      `;
      doc.body.prepend(header);
      doc.querySelectorAll<HTMLElement>("[data-codex-route]").forEach((node) => {
        node.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const route = node.dataset.codexRoute as RehabWorkspaceModule | undefined;
          if (route && route !== activeModule) setActiveModule(route);
        });
      });
      doc.querySelectorAll<HTMLElement>("[data-codex-device]").forEach((node) => {
        node.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const deviceId = node.dataset.codexDevice;
          if (deviceId) setSelectedDeviceId(deviceId);
        });
      });
      doc.querySelectorAll<HTMLElement>("[data-codex-jump]").forEach((node) => {
        node.addEventListener("click", (event) => {
          event.preventDefault();
          window.location.href = `/projects/${projectId}/robotics`;
        });
      });
      doc.querySelectorAll<HTMLElement>("[data-codex-estop]").forEach((node) => {
        node.addEventListener("click", (event) => {
          event.preventDefault();
          setEstopRequestState("sent");
        });
      });
    };
    insertUnifiedShell();
    const routeLabels: Record<RehabWorkspaceModule, { short: string; label: string }> = {
      overview: { short: "CMD", label: "总控" },
      vision: { short: "V", label: "视觉" },
      digital_twin: { short: "3D", label: "孪生" },
      muscle_assist: { short: "EMG", label: "肌电" },
      ai_model: { short: "AI", label: "模型" },
      mode_router: { short: "L", label: "模式" },
      training: { short: "TRN", label: "训练" },
      data_hub: { short: "DATA", label: "数据" },
      action_planner: { short: "A", label: "动作" },
      diagnostics: { short: "IO", label: "诊断" },
      logs: { short: "LOG", label: "日志" },
    };
    const syncCodexNav = () => doc.querySelectorAll<HTMLElement>("[data-codex-route]").forEach((node) => {
      const route = node.dataset.codexRoute as RehabWorkspaceModule | undefined;
      if (!route || !routeLabels[route]) return;
      node.className = routeClass(route);
      node.innerHTML = `<strong class="block font-telemetry-data text-[13px] leading-none">${routeLabels[route].short}</strong><span class="block font-telemetry-label text-[8px] mt-1">${routeLabels[route].label}</span>`;
    });
    syncCodexNav();
    replaceExactText([
      ["Control Console", "VLA 控制台"],
      ["CONTROL CONSOLE", "VLA 控制台"],
      ["Manual Mode", "手动模式"],
      ["Safety: Secured", "安全栅：锁定"],
      ["Emergency Stop", "急停"],
      ["DEVICE DIAGNOSTICS", "设备诊断"],
      ["DRY RUN MODE", "DRY-RUN 模式"],
      ["System Status", "系统状态"],
      ["Safety Manual", "安全手册"],
      ["Overview", "总控"],
      ["Vision", "视觉"],
      ["VLA Vision", "VLA 视觉"],
      ["Twin", "孪生"],
      ["Assist", "助力"],
      ["Router", "路由"],
      ["Train", "训练"],
      ["Logs", "日志"],
      ["DIAGS", "诊断"],
      ["打开真实肌电组件", "打开肌电数据抽屉"],
    ]);
    const routeEntries: Array<[RehabWorkspaceModule, string[]]> = [
      ["overview", ["overview", "总控", "遥测", "dashboard"]],
      ["vision", ["vision", "vla 视觉", "视觉", "visibility"]],
      ["digital_twin", ["digital-twin", "digital twin", "数字孪生", "twin", "view_in_ar"]],
      ["muscle_assist", ["muscle", "肌肉", "assist", "fitness_center"]],
      ["ai_model", ["ai model", "ai模型", "模型中转", "模型练习场", "model relay"]],
      ["mode_router", ["orchestration", "router", "模式", "alt_route"]],
      ["training", ["training", "train", "训练", "model_training"]],
      ["data_hub", ["data", "dataset", "数据", "数据集", "database"]],
      ["action_planner", ["planner", "action", "动作", "settings_remote"]],
      ["diagnostics", ["diagnostics", "diag", "诊断", "biotech"]],
      ["logs", ["logs", "日志", "list_alt", "terminal"]],
    ];
    const resolveRoute = (raw: string) => {
      const value = raw.toLowerCase();
      return routeEntries.find(([, tokens]) => tokens.some((token) => value.includes(token.toLowerCase())))?.[0] ?? null;
    };
    doc.querySelectorAll<HTMLElement>("a, button").forEach((node) => {
      if (node.dataset.codexRouteBound === "true") return;
      const icon = node.querySelector(".material-symbols-outlined")?.textContent ?? "";
      const route = resolveRoute(`${node.getAttribute("href") ?? ""} ${node.getAttribute("title") ?? ""} ${node.textContent ?? ""} ${icon}`);
      if (!route) return;
      node.dataset.codexRouteBound = "true";
      node.addEventListener("click", (event) => {
        if (route === activeModule) return;
        event.preventDefault();
        event.stopPropagation();
        setActiveModule(route);
      });
    });

    const leftImage = leftStereoImageSrc || absoluteImageUrl || "";
    const rightImage = rightStereoImageSrc || "";
    if (activeModule === "overview") {
      const modeLabel = currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待 L 分类";
      const targetLabel = semanticTargetLabel || stereoTargetLabel || text(recentTargetMemory?.label, "等待目标");
      const endEffectorLabel = stereoEndEffectorLabel || text(recentEndEffectorMemory?.label, "等待末端");
      const muscleRows = muscleRowsFromSensor(sensorPayload).slice(0, 4);
      const predictionRows = motionPredictionRowsFromSensor(sensorPayload);
      const firstPrediction = predictionRows[0];
      const assistConfidence = Number.isFinite(firstPrediction?.confidence) ? Math.round((firstPrediction?.confidence ?? 0) * 100) : 0;
      const actionPreview = {
        mode: currentSemanticMode || "waiting",
        mode_label: modeLabel,
        l_summary: effectiveLanguageSummary || "等待小智/L 输入",
        target: targetLabel,
        end_effector: endEffectorLabel,
        v_state: visualServoStateText,
        a_gate: dryRunGateLabel(dryRunGateState),
        next_step: pixelServo.nextStep,
        safety: motionAllowed ? "M33 candidate; still requires hardware authority" : "read_only_locked",
      };
      const overviewSnapshot = () => ({
        exported_at: new Date().toISOString(),
        project_id: projectId,
        boundary: "command_center_overview_evidence_only_not_motion_permission",
        selected_device: {
          device_id: selected?.device_id ?? null,
          device_code: publicDeviceCode(selected, selectedIndex),
          robot_id: selected?.robot_id ?? null,
          online_state: selected?.online_state ?? "unknown",
          last_upload: formatTime(selected?.last_upload_ts_unix),
        },
        l_semantic: {
          summary: effectiveLanguageSummary || "等待小智/L 输入",
          mode: currentSemanticMode || "waiting",
          mode_label: modeLabel,
          route_source: routeSourceText,
          route_confidence: routeConfidenceText,
        },
        v_vision: {
          left_frame_available: Boolean(leftImage),
          right_frame_available: Boolean(rightImage),
          image_source: visualEvidenceImageSource,
          target: targetLabel,
          end_effector: endEffectorLabel,
          state: visualServoStateText,
          distance: visualServoDistanceText,
          visual_lock: {
            observed_frames: visualLockObservedFrames,
            required_frames: visualLockRequiredFrames,
            confidence: visualLockConfidenceText,
          },
          depth_m: stereoDepth ?? null,
          camera_to_robot_ready: Boolean(cameraToRobotReady),
        },
        a_planner: {
          candidate: actionPreview,
          dry_run_gate: dryRunGateLabel(dryRunGateState),
          reason: dryRunGateReason,
          dry_run_candidate_allowed: Boolean(dryRunCandidateAllowed),
        },
        digital_twin: {
          simulation_ready: simulationReady,
          plan_state: simulationPlanState,
          report_boundary: simulationReportBoundary,
          joint_count: renderRows.length,
          stale_joint_count: staleRenderCount,
          clamped_joint_count: clampedRenderCount,
        },
        emg_training: {
          assist_requested: currentSemanticMode === "assistive_emg",
          training_requested: currentSemanticMode === "training",
          predictions: predictionRows.slice(0, 3),
          channels: muscleRows,
          app_training_library: "reserved_app_ble_m33_chain",
        },
        safety: {
          m33_final_authority: Boolean(liveDashboard.safety_boundary.m33_final_authority),
          motion_allowed_candidate: Boolean(motionAllowed),
          current_state: stateText(currentSafetyState),
          note: "浏览器总控只做证据汇总、模式跳转和只读导出，不发送 CAN/M33/电机控制。",
        },
        recent_events: liveDashboard.recent_events.slice(0, 12).map((event) => ({
          record_type: event.record_type,
          title: eventTitle(event),
          device_id: event.device_id,
          ts_unix: event.ts_unix,
          time: formatTime(event.ts_unix),
        })),
      });
      setText("title", "总控首页 - VLA 控制台");
      setText('[data-role="overview-left-camera"]', `左摄像头视角：${leftImage ? "有帧" : "等待"} / ${visualEvidenceImageSource}`);
      setText('[data-role="overview-right-camera"]', `右摄像头视角：${rightImage ? "有帧" : "等待"} / ${rightImage ? "stereo_right" : "辅助帧待上传"}`);
      setText('[data-role="overview-vision-latency"]', `V耗时: ${stereoHasFrameTiming ? compactNumberText(stereoFrameProcessMs, " ms") : "等待"}`);
      setText('[data-role="overview-vision-loop"]', `循环: ${stereoLoopProgressText}`);
      setText('[data-role="overview-target-vector"]', `目标: ${targetLabel}`);
      setText('[data-role="overview-target-distance"]', `末端差: ${visualServoDistanceText}`);
      setText('[data-role="overview-target-confidence"]', `锁定: ${visualLockObservedFrames}/${visualLockRequiredFrames} · ${visualLockConfidenceText}`);
      setText('[data-role="overview-joint-1"]', poseValueText(poseSamples[0] ? record(poseSamples[0]) : undefined));
      setText('[data-role="overview-joint-2"]', poseValueText(poseSamples[1] ? record(poseSamples[1]) : undefined));
      setText('[data-role="overview-sim-state"]', simulationReady ? "已回传" : "等待");
      setText('[data-role="overview-can-state"]', wiringBadCount ? `${wiringBadCount} 异常` : motors.length ? `${motors.length} 电机` : "只读/等待");
      setText('[data-role="overview-action-gate"]', dryRunGateLabel(dryRunGateState));
      setText('[data-role="overview-urdf-name"]', `URDF 模型: ${text(record(selected?.device_model).file_name, "等待模型")}`);
      setText('[data-role="overview-urdf-sync"]', simulationReady ? `仿真同步：${simulationPlanState}` : "等待 MuJoCo shadow 回传");
      setText('[data-role="overview-mujoco-state"]', simulationReady ? "已回传" : "等待");
      setText('[data-role="overview-assist-direction"]', firstPrediction?.label || firstPrediction?.value || (currentSemanticMode === "assistive_emg" ? "助力候选监听" : "等待助力意图"));
      setText('[data-role="overview-assist-confidence"]', assistConfidence ? `${assistConfidence}%` : "等待");
      const confidenceBar = doc.querySelector<HTMLElement>('[data-role="overview-assist-confidence-bar"]');
      if (confidenceBar) confidenceBar.style.width = `${Math.max(8, assistConfidence)}%`;
      muscleRows.forEach((row, index) => {
        setText(`[data-role="overview-emg-ch${index + 1}"]`, row.displayValue);
      });
      setText('[data-role="overview-emg-status"]', muscleRows.length ? "传感器: 已有通道摘要" : "传感器: 等待真实 EMG");
      setText('[data-role="overview-emg-intent"]', `动作意图: ${firstPrediction?.value || firstPrediction?.label || "预留"}`);
      setText('[data-role="overview-emg-boundary"]', "边界: 只读证据 / M33 裁决");
      setText('[data-role="overview-language"]', effectiveLanguageSummary ? `“${effectiveLanguageSummary}”` : "等待小智/L 输入");
      setText('[data-role="overview-route-target"]', `目标: ${targetLabel}`);
      setText('[data-role="overview-route-action"]', `动作: ${modeLabel} / ${dryRunGateLabel(dryRunGateState)}`);
      const setModeIcon = (role: string, active: boolean) => {
        const node = doc.querySelector<HTMLElement>(`[data-role="${role}"]`);
        if (!node) return;
        node.textContent = active ? "toggle_on" : "toggle_off";
        node.style.fontVariationSettings = active ? "'FILL' 1" : "'FILL' 0";
      };
      setModeIcon("overview-mode-assist", currentSemanticMode === "assistive_emg");
      setModeIcon("overview-mode-fetch", currentSemanticMode === "fetch_object" || currentSemanticMode === "vision_servo");
      setModeIcon("overview-mode-training", currentSemanticMode === "training");
      setModeIcon("overview-mode-safety", !motionAllowed || currentSemanticMode === "safety_review" || currentSemanticMode === "diagnostics");
      setText('[data-role="overview-resource-vision"]', `视觉管线: ${visualServoReady ? "目标+末端闭环" : stereoHasContext ? "观察中" : "等待"}`);
      setText('[data-role="overview-resource-sim"]', `仿真主机: ${simulationReady ? simulationPlanState : "等待 shadow"}`);
      setText('[data-role="overview-resource-safety"]', `安全边界: ${motionAllowed ? "M33 候选" : "M33 锁定"} / final authority`);
      const logRows = doc.querySelectorAll<HTMLElement>('[data-role="overview-log-stream"] .flex.gap-4');
      liveDashboard.recent_events.slice(0, logRows.length).forEach((event, index) => {
        const spans = logRows[index]?.querySelectorAll<HTMLElement>("span");
        if (!spans?.length) return;
        if (spans[0]) spans[0].textContent = `[${formatTime(event.ts_unix)}]`;
        if (spans[1]) spans[1].textContent = `${text(event.record_type, "event")}: ${eventTitle(event)}`;
      });
      const refreshButton = doc.querySelector<HTMLButtonElement>('[data-role="overview-refresh"]');
      if (refreshButton) {
        refreshButton.onclick = (event) => {
          event.preventDefault();
          const original = refreshButton.textContent || "刷新总控";
          refreshButton.textContent = "刷新中";
          void refreshLiveDashboard(false).finally(() => {
            refreshButton.textContent = "已刷新";
            window.setTimeout(() => {
              refreshButton.textContent = original;
            }, 1200);
          });
        };
      }
      const exportButton = doc.querySelector<HTMLButtonElement>('[data-role="overview-export"]');
      if (exportButton) {
        exportButton.onclick = (event) => {
          event.preventDefault();
          const blob = new Blob([JSON.stringify(overviewSnapshot(), null, 2)], { type: "application/json;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `rehab-arm-overview-evidence-${projectId}-${Date.now()}.json`;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
          const original = exportButton.textContent || "导出总览";
          exportButton.textContent = "已导出";
          window.setTimeout(() => {
            exportButton.textContent = original;
          }, 1200);
        };
      }
    }
    if (activeModule === "vision") {
      setText("title", "VLA 视觉 - VLA 控制台");
      setText("h1", "VLA 控制台");
      setText(".font-headline-md.text-headline-md.text-primary", "VLA 视觉");
      const wireImage = (role: string, src: string, waitingText: string) => {
        const image = doc.querySelector<HTMLImageElement>(`img[data-role="${role}"]`);
        const frame = image?.closest<HTMLElement>("#vision-left-frame, #vision-right-frame");
        if (!image || !frame) return;
        if (src) {
          image.src = src;
          image.classList.remove("hidden");
          image.style.display = "block";
          image.style.objectFit = "contain";
          image.style.opacity = "1";
          frame.querySelector<HTMLElement>("[data-codex-waiting]")?.remove();
        } else if (!frame.querySelector("[data-codex-waiting]")) {
          image.removeAttribute("src");
          image.classList.add("hidden");
          const waiting = doc.createElement("div");
          waiting.dataset.codexWaiting = "true";
          waiting.className = "absolute inset-0 grid place-items-center font-data-tabular text-[12px] text-on-surface-variant";
          waiting.textContent = waitingText;
          image.parentElement?.appendChild(waiting);
        }
      };
      wireImage("left-camera-image", leftImage, "等待左摄像头标注帧");
      wireImage("right-camera-image", rightImage, "等待右摄像头辅助帧");
      doc.getElementById("codex-vision-live-bridge")?.remove();
      const stereoFrameSizeText = stereoFrameSize
        ? `${Math.round(stereoFrameSize.width)}x${Math.round(stereoFrameSize.height)}`
        : "640x480";
      const stereoTargetConfidence = firstFiniteNumber(stereoTarget.confidence, stereoTarget.score, stereoTarget.probability);
      const stereoEndEffectorConfidence = firstFiniteNumber(stereoEndEffector.confidence, stereoEndEffector.score, stereoEndEffector.probability);
      const targetStatusText = stereoTargetLabel
        ? `${stereoTargetLabel}${stereoTargetConfidence !== null ? ` ${compactNumberText(stereoTargetConfidence * 100, "%")}` : ""}`
        : targetQualityGateTitle === "未接受目标"
          ? text(stereoTargetQualityGateState, "no_yolo_cup_or_bottle")
          : "等待目标";
      const endEffectorStateHtml = stereoEndEffectorLabel
        ? [
          `<span>${escapeHtml(stereoEndEffectorLabel)}</span>`,
          `<span>${escapeHtml(stereoEndEffectorConfidence !== null ? compactNumberText(stereoEndEffectorConfidence * 100, "%") : endEffectorEvidenceText)}</span>`,
          `<span>${escapeHtml(cameraToRobotReady ? "robot_frame ready" : "robot_frame waiting")}</span>`,
        ].join("")
        : [
          "<span>waiting</span>",
          "<span>end_effector</span>",
          `<span>${escapeHtml(cameraToRobotReady ? "robot_frame ready" : "no robot_frame")}</span>`,
        ].join("");
      const disparityDepthText = [
        stereoHasDisparity ? `Δpx ${compactNumberText(stereoDisparity, "")}` : "无左右匹配",
        stereoDepth !== null ? `depth ${compactNumberText(stereoDepth, " m")}` : "depth waiting",
      ].join(" / ");
      const calibrationText = cameraToRobotReady
        ? "camera_to_robot ready"
        : stereoDepth !== null
          ? "stereo depth ready / hand-eye waiting"
          : "waiting_calibration";
      setText('[data-role="vision-left-frame-status"]', leftImage ? `真实左帧 | ${stereoFrameSizeText}` : `等待左帧 | ${stereoFrameSizeText}`);
      setText('[data-role="vision-right-frame-status"]', rightImage ? `真实右帧 | ${stereoDepth !== null ? "depth evidence" : "深度 waiting"}` : "等待右帧 | 深度 waiting");
      setText('[data-role="vision-target-semantics"]', effectiveLanguageSummary || "等待小智/L 输入");
      setText('[data-role="vision-target-class"]', targetStatusText);
      setHtml('[data-role="vision-end-effector-state"]', endEffectorStateHtml);
      setText('[data-role="vision-lock-frames"]', `${visualLockObservedFrames}/${visualLockRequiredFrames} · ${visualLockConfidenceText}`);
      setText('[data-role="vision-disparity-depth"]', disparityDepthText);
      setHtml(
        '[data-role="vision-calibration-state"]',
        `<span class="w-1.5 h-1.5 rounded-full ${cameraToRobotReady ? "bg-primary shadow-[0_0_5px_#4cd7f6]" : "bg-outline shadow-none"}"></span>${escapeHtml(calibrationText)}`,
      );
      const visionSnapshot = () => ({
        exported_at: new Date().toISOString(),
        project_id: projectId,
        boundary: "vision_evidence_only_not_motion_permission",
        selected_device: {
          device_id: selected?.device_id ?? null,
          device_code: publicDeviceCode(selected, selectedIndex),
          robot_id: selected?.robot_id ?? null,
        },
        frames: {
          left_available: Boolean(leftImage),
          right_available: Boolean(rightImage),
          left_src: leftImage || null,
          right_src: rightImage || null,
        },
        language: {
          summary: effectiveLanguageSummary || "等待 XiaoZhi / L 输入",
          semantic_mode: currentSemanticMode || "waiting",
        },
        detections: {
          target: stereoTargetLabel || text(recentTargetMemory?.label, "等待目标"),
          end_effector: stereoEndEffectorLabel || text(recentEndEffectorMemory?.label, "等待末端"),
          visual_state: visualServoStateText,
          distance: visualServoDistanceText,
          pixel_error: {
            du_px: visualServoDelta ? Number(visualServoDelta[0].toFixed(2)) : null,
            dv_px: visualServoDelta ? Number(visualServoDelta[1].toFixed(2)) : null,
            distance_px: visualServoDistancePx !== null ? Number(visualServoDistancePx.toFixed(2)) : null,
          },
          visual_lock: {
            observed_frames: visualLockObservedFrames,
            required_frames: visualLockRequiredFrames,
            confidence: visualLockConfidenceText,
          },
          target_quality: targetQualityGateTitle,
          camera_to_robot_ready: Boolean(cameraToRobotReady),
        },
        action_gate: {
          dry_run_gate: dryRunGateLabel(dryRunGateState),
          dry_run_reason: dryRunGateReason,
          next_step: pixelServo.nextStep,
        },
        safety: {
          m33_final_authority: Boolean(liveDashboard.safety_boundary.m33_final_authority),
          motion_allowed_candidate: Boolean(motionAllowed),
          note: "视觉页只展示后端图像证据和候选坐标，不绘制假框，不发送 M33/CAN 控制。",
        },
      });
      const visionRefreshButton = doc.querySelector<HTMLButtonElement>('[data-role="vision-refresh"]');
      if (visionRefreshButton) {
        visionRefreshButton.onclick = (event) => {
          event.preventDefault();
          const original = visionRefreshButton.textContent || "刷新视觉";
          visionRefreshButton.textContent = "刷新中";
          void refreshLiveDashboard(false).finally(() => {
            visionRefreshButton.textContent = "已刷新";
            window.setTimeout(() => {
              visionRefreshButton.textContent = original;
            }, 1200);
          });
        };
      }
      const visionExportButton = doc.querySelector<HTMLButtonElement>('[data-role="vision-export"]');
      if (visionExportButton) {
        visionExportButton.onclick = (event) => {
          event.preventDefault();
          const blob = new Blob([JSON.stringify(visionSnapshot(), null, 2)], { type: "application/json;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `rehab-arm-vision-evidence-${projectId}-${Date.now()}.json`;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
          const original = visionExportButton.textContent || "导出证据";
          visionExportButton.textContent = "已导出";
          window.setTimeout(() => {
            visionExportButton.textContent = original;
          }, 1200);
        };
      }
      doc.querySelectorAll<HTMLButtonElement>('[data-role="vision-open-action"]').forEach((button) => {
        button.onclick = (event) => {
          event.preventDefault();
          setActiveModule("action_planner");
        };
      });
      doc.querySelectorAll<HTMLButtonElement>('[data-role="vision-open-logs"]').forEach((button) => {
        button.onclick = (event) => {
          event.preventDefault();
          setActiveModule("logs");
        };
      });
    }

    if (activeModule === "digital_twin") {
      setText("title", "数字孪生 - VLA 控制台");
      setText("h1", "VLA 控制台");
      setText(".font-headline-md.text-headline-md.text-primary", "VLA 控制台");
      setAllText("main .glass-panel .grid.grid-cols-2.gap-y-2 .font-telemetry-data", poseSamples.slice(0, 6).map((sample) => poseValueText(record(sample))));
      setAllText("main .glass-panel .grid.grid-cols-2.gap-y-2 .text-\\[9px\\]", [
        "J1 基座",
        "J2 肩部",
        "J3 肘部",
        "J4 腕 1",
        "J5 腕 2",
        "J6 腕 3",
      ]);
      setValueNearLabel(/ROS Bridge|ROS 桥/, simulationReady ? "Shadow 已回传" : "等待仿真");
      setValueNearLabel(/MuJoCo Latency|MuJoCo/, simulationReady ? simulationPlanState : "等待 shadow report");
      setValueNearLabel(/Target Pose|目标位姿/, dryRunGateLabel(dryRunGateState));
      setValueNearLabel(/End-Effector Pose|末端位姿/, recentEndEffectorMemory?.label ?? "等待末端识别");
      const twinSnapshot = () => ({
        exported_at: new Date().toISOString(),
        project_id: projectId,
        boundary: "digital_twin_evidence_only_not_motion_permission",
        selected_device: {
          device_id: selected?.device_id ?? null,
          device_code: publicDeviceCode(selected, selectedIndex),
          robot_id: selected?.robot_id ?? null,
        },
        render_state: {
          source: renderRows.length ? "robot_render_state_v1" : "waiting",
          joint_count: renderRows.length,
          fresh_joint_count: Math.max(0, renderRows.length - staleRenderCount),
          stale_joint_count: staleRenderCount,
          clamped_joint_count: clampedRenderCount,
          joints: renderRows.slice(0, 12),
          pose_samples: poseSamples.slice(0, 12),
        },
        simulation: {
          ready: simulationReady,
          plan_state: simulationPlanState,
          report_boundary: simulationReportBoundary,
        },
        vla_context: {
          dry_run_gate: dryRunGateLabel(dryRunGateState),
          target: stereoTargetLabel || text(recentTargetMemory?.label, "等待目标"),
          end_effector: stereoEndEffectorLabel || text(recentEndEffectorMemory?.label, "等待末端"),
        },
        model_package: {
          file_name: text(record(selected?.device_model).file_name, ""),
          package_name: text(record(selected?.device_model).package_name, ""),
          urdf_path: text(record(selected?.device_model).urdf_path, ""),
          joint_count: record(selected?.device_model).joint_count ?? null,
          mesh_count: record(selected?.device_model).mesh_count ?? null,
        },
        safety: {
          m33_final_authority: Boolean(liveDashboard.safety_boundary.m33_final_authority),
          motion_allowed_candidate: Boolean(motionAllowed),
          note: "数字孪生页只展示 URDF/MuJoCo/关节证据，不发送 CAN、M33 或电机控制。",
        },
      });
      const existingIkPanel = doc.getElementById("codex-ik-dry-run-panel");
      const displayedIkTargetInput = {
        x_m: existingIkPanel?.querySelector<HTMLInputElement>('[data-role="ik-x"]')?.value ?? ikDraftRef.current.target.x_m,
        y_m: existingIkPanel?.querySelector<HTMLInputElement>('[data-role="ik-y"]')?.value ?? ikDraftRef.current.target.y_m,
        z_m: existingIkPanel?.querySelector<HTMLInputElement>('[data-role="ik-z"]')?.value ?? ikDraftRef.current.target.z_m,
      };
      const displayedIkApproachInput =
        existingIkPanel?.querySelector<HTMLInputElement>('[data-role="ik-approach"]')?.value ?? ikDraftRef.current.approach;
      const displayedIkOrientationInput =
        existingIkPanel?.querySelector<HTMLInputElement>('[data-role="ik-orientation"]')?.value ?? ikDraftRef.current.orientation;
      const displayedIkSourceInput =
        (existingIkPanel?.querySelector<HTMLSelectElement>('[data-role="ik-source"]')?.value as typeof ikSourceInput | undefined)
        ?? ikDraftRef.current.source;
      const activeIkElement = doc.activeElement as HTMLElement | null;
      const shouldPreserveIkPanel = Boolean(
        existingIkPanel
        && activeIkElement
        && existingIkPanel.contains(activeIkElement)
        && activeIkElement.matches('input[data-role^="ik-"], select[data-role="ik-source"]'),
      );
      const ikPanel = shouldPreserveIkPanel
        ? existingIkPanel as HTMLElement
        : ensureStitchPanel("codex-ik-dry-run-panel", `
        <div class="p-4 border border-secondary-fixed-dim/40 bg-surface-container-low/80 backdrop-blur-xl rounded-lg shadow-[0_0_24px_rgba(255,185,95,0.12)]">
          <div class="flex items-start justify-between gap-3 border-b border-outline-variant/30 pb-3">
            <div>
              <p class="font-label-caps text-secondary-fixed-dim">IK DRY-RUN EVIDENCE</p>
              <h2 class="font-headline-md text-[18px] text-on-surface">逆解算候选坐标</h2>
              <p class="text-[12px] text-on-surface-variant mt-1">robot_frame 坐标 -> IK candidate -> URDF/MuJoCo shadow；不授予真机运动。</p>
            </div>
            <span class="font-label-caps text-error border border-error/40 px-2 py-1 rounded">EVIDENCE ONLY</span>
          </div>
          <div class="grid grid-cols-3 gap-2 mt-3">
            <label class="text-[10px] font-label-caps text-on-surface-variant">X_m<input data-role="ik-x" class="mt-1 w-full bg-background border border-outline-variant rounded px-2 py-1 font-data-tabular text-primary" value="${escapeHtml(displayedIkTargetInput.x_m)}"/></label>
            <label class="text-[10px] font-label-caps text-on-surface-variant">Y_m<input data-role="ik-y" class="mt-1 w-full bg-background border border-outline-variant rounded px-2 py-1 font-data-tabular text-primary" value="${escapeHtml(displayedIkTargetInput.y_m)}"/></label>
            <label class="text-[10px] font-label-caps text-on-surface-variant">Z_m<input data-role="ik-z" class="mt-1 w-full bg-background border border-outline-variant rounded px-2 py-1 font-data-tabular text-primary" value="${escapeHtml(displayedIkTargetInput.z_m)}"/></label>
          </div>
          <div class="grid grid-cols-2 gap-2 mt-2">
            <label class="text-[10px] font-label-caps text-on-surface-variant">Approach<input data-role="ik-approach" class="mt-1 w-full bg-background border border-outline-variant rounded px-2 py-1 font-data-tabular text-primary" value="${escapeHtml(displayedIkApproachInput)}"/></label>
            <label class="text-[10px] font-label-caps text-on-surface-variant">Gripper<input data-role="ik-orientation" class="mt-1 w-full bg-background border border-outline-variant rounded px-2 py-1 font-data-tabular text-primary" value="${escapeHtml(displayedIkOrientationInput)}"/></label>
          </div>
          <div class="grid grid-cols-[1fr_auto_auto] gap-2 mt-3 items-end">
            <label class="text-[10px] font-label-caps text-on-surface-variant">Source<select data-role="ik-source" class="mt-1 w-full bg-background border border-outline-variant rounded px-2 py-1 font-data-tabular text-primary">
              <option value="manual_platform">manual_platform</option>
              <option value="vision_calibrated">vision_calibrated</option>
              <option value="simulation_test">simulation_test</option>
            </select></label>
            <button data-role="ik-generate" class="px-3 py-2 bg-primary-container text-on-primary-container rounded font-label-caps">${ikCandidateState === "generating" ? "生成中" : "生成 IK 候选"}</button>
            <button data-role="ik-export" class="px-3 py-2 border border-secondary-fixed-dim/50 text-secondary-fixed-dim rounded font-label-caps">导出 JSON</button>
          </div>
          <div class="mt-3 grid grid-cols-2 gap-2 text-[11px] font-data-tabular">
            <div class="border border-outline-variant/25 rounded p-2"><span class="text-on-surface-variant">IK</span><strong class="block text-primary" data-role="ik-status">${escapeHtml(text(ikCandidate.ik_status, ikCandidateState === "error" ? "error" : "waiting"))}</strong></div>
            <div class="border border-outline-variant/25 rounded p-2"><span class="text-on-surface-variant">Limit</span><strong class="block text-primary" data-role="ik-limit">${record(ikCandidate.joint_limit_check).ok === true ? "pass" : "waiting"}</strong></div>
            <div class="border border-outline-variant/25 rounded p-2"><span class="text-on-surface-variant">Workspace</span><strong class="block text-primary" data-role="ik-workspace">${record(ikCandidate.collision_or_workspace_check).workspace_reachable === true ? "reachable" : "waiting"}</strong></div>
            <div class="border border-outline-variant/25 rounded p-2"><span class="text-on-surface-variant">Shadow</span><strong class="block text-primary" data-role="ik-sim">${text(record(ikCandidate.simulation_result).readiness, simulationPlanState || "waiting")}</strong></div>
            <div class="border border-outline-variant/25 rounded p-2"><span class="text-on-surface-variant">Solver</span><strong class="block text-primary" data-role="ik-solver">${escapeHtml(text(record(ikCandidate.ik_solver_report).quality, "waiting"))}</strong></div>
            <div class="border border-outline-variant/25 rounded p-2"><span class="text-on-surface-variant">Error</span><strong class="block text-primary" data-role="ik-error">${escapeHtml(text(record(ikCandidate.ik_solver_report).position_error_m, "n/a"))} m</strong></div>
            <div class="border border-outline-variant/25 rounded p-2"><span class="text-on-surface-variant">Seeds</span><strong class="block text-primary" data-role="ik-seeds">${escapeHtml(text(record(ikCandidate.ik_solver_report).seed_count, "n/a"))}</strong></div>
            <div class="border border-outline-variant/25 rounded p-2"><span class="text-on-surface-variant">Near limit</span><strong class="block text-primary" data-role="ik-near-limit">${escapeHtml(text(record(record(ikCandidate.ik_solver_report).joint_boundary_summary).near_limit_joint_count, "0"))}</strong></div>
          </div>
          <div class="mt-2 border border-outline-variant/25 rounded p-2 text-[10px] font-data-tabular text-on-surface-variant">
            <span class="block text-secondary-fixed-dim">solver reason: ${escapeHtml(text(record(ikCandidate.ik_solver_report).status_reason, "waiting_for_target"))}</span>
            <span class="block text-secondary-fixed-dim">shadow target: ${escapeHtml(text(record(ikCandidate.mujoco_shadow_validation_plan).target_topic, "/sim/medical_arm/joint_trajectory"))}</span>
            <span class="block">scope: ${escapeHtml(text(record(ikCandidate.mujoco_shadow_validation_plan).publish_scope, "sim_only_shadow_topic_not_hardware_chain"))}</span>
          </div>
          ${ikCandidateError ? `<p class="mt-2 text-[11px] text-error">${escapeHtml(ikCandidateError)}</p>` : ""}
          <p class="mt-3 text-[11px] text-error">control_boundary: ik_candidate_evidence_only_not_motion_permission</p>
        </div>
      `);
      ikPanel.style.position = "absolute";
      ikPanel.style.top = "72px";
      ikPanel.style.right = "24px";
      ikPanel.style.width = "380px";
      ikPanel.style.zIndex = "30";
      const ikSource = ikPanel.querySelector<HTMLSelectElement>('[data-role="ik-source"]');
      if (ikSource) ikSource.value = displayedIkSourceInput;
      const syncIkInputs = (commitState = false) => {
        const nextTarget = {
          x_m: ikPanel.querySelector<HTMLInputElement>('[data-role="ik-x"]')?.value ?? ikTargetInput.x_m,
          y_m: ikPanel.querySelector<HTMLInputElement>('[data-role="ik-y"]')?.value ?? ikTargetInput.y_m,
          z_m: ikPanel.querySelector<HTMLInputElement>('[data-role="ik-z"]')?.value ?? ikTargetInput.z_m,
        };
        const nextApproach = ikPanel.querySelector<HTMLInputElement>('[data-role="ik-approach"]')?.value ?? ikApproachInput;
        const nextOrientation = ikPanel.querySelector<HTMLInputElement>('[data-role="ik-orientation"]')?.value ?? ikOrientationInput;
        const nextSource = (ikPanel.querySelector<HTMLSelectElement>('[data-role="ik-source"]')?.value as typeof ikSourceInput) || ikSourceInput;
        ikDraftRef.current = {
          target: nextTarget,
          approach: nextApproach,
          orientation: nextOrientation,
          source: nextSource,
        };
        if (commitState) {
          setIkTargetInput(nextTarget);
          setIkApproachInput(nextApproach);
          setIkOrientationInput(nextOrientation);
          setIkSourceInput(nextSource);
        }
      };
      ikPanel.querySelectorAll<HTMLInputElement>('[data-role="ik-x"], [data-role="ik-y"], [data-role="ik-z"], [data-role="ik-approach"], [data-role="ik-orientation"]').forEach((input) => {
        input.oninput = () => syncIkInputs(false);
        input.onchange = () => syncIkInputs(false);
      });
      if (ikSource) ikSource.onchange = () => syncIkInputs(false);
      const ikGenerateButton = ikPanel.querySelector<HTMLButtonElement>('[data-role="ik-generate"]');
      if (ikGenerateButton) {
        ikGenerateButton.onclick = (event) => {
          event.preventDefault();
          syncIkInputs(true);
          window.setTimeout(() => void generateIkCandidate(), 0);
        };
      }
      const ikExportButton = ikPanel.querySelector<HTMLButtonElement>('[data-role="ik-export"]');
      if (ikExportButton) {
        ikExportButton.onclick = (event) => {
          event.preventDefault();
          syncIkInputs(true);
          window.setTimeout(() => exportIkCandidateEvidence(), 0);
        };
      }
      const twinRefreshButton = doc.querySelector<HTMLButtonElement>('[data-role="twin-refresh"]');
      if (twinRefreshButton) {
        twinRefreshButton.onclick = (event) => {
          event.preventDefault();
          const original = twinRefreshButton.textContent || "RELOAD";
          twinRefreshButton.textContent = "刷新中";
          void refreshLiveDashboard(false).finally(() => {
            twinRefreshButton.textContent = "已刷新";
            window.setTimeout(() => {
              twinRefreshButton.textContent = original;
            }, 1200);
          });
        };
      }
      const twinExportButton = doc.querySelector<HTMLButtonElement>('[data-role="twin-export"]');
      if (twinExportButton) {
        twinExportButton.onclick = (event) => {
          event.preventDefault();
          const blob = new Blob([JSON.stringify(twinSnapshot(), null, 2)], { type: "application/json;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `rehab-arm-digital-twin-${projectId}-${Date.now()}.json`;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
          const original = twinExportButton.textContent || "导出证据";
          twinExportButton.textContent = "已导出";
          window.setTimeout(() => {
            twinExportButton.textContent = original;
          }, 1200);
        };
      }
      doc.querySelectorAll<HTMLButtonElement>('[data-role="twin-open-action"]').forEach((button) => {
        button.onclick = (event) => {
          event.preventDefault();
          setActiveModule("action_planner");
        };
      });
      doc.querySelectorAll<HTMLButtonElement>('[data-role="twin-open-logs"]').forEach((button) => {
        button.onclick = (event) => {
          event.preventDefault();
          setActiveModule("logs");
        };
      });
      doc.getElementById("codex-twin-real-bridge")?.remove();
      const stageRoot = doc.getElementById("urdf-runtime-stage");
      let host = doc.getElementById("codex-twin-runtime-stage") as HTMLElement | null;
      if (!host && stageRoot) {
        host = doc.createElement("div");
        host.id = "codex-twin-runtime-stage";
        stageRoot.appendChild(host);
      }
      if (host) {
        if (!doc.getElementById("codex-twin-runtime-compat")) {
          const compatStyle = doc.createElement("style");
          compatStyle.id = "codex-twin-runtime-compat";
          compatStyle.textContent = `
            #codex-twin-runtime-stage {
              overflow: hidden;
            }
            #codex-twin-runtime-stage [class*="stitchTwinStageOverlay"] {
              position: absolute !important;
              inset: 0 !important;
              width: 100% !important;
              height: 100% !important;
              pointer-events: none !important;
            }
            #codex-twin-runtime-stage [class*="armOverviewPanel"] {
              position: absolute !important;
              inset: 0 !important;
              width: 100% !important;
              height: 100% !important;
              padding: 0 !important;
              border: 0 !important;
              background: transparent !important;
              box-shadow: none !important;
              pointer-events: none !important;
            }
            #codex-twin-runtime-stage [class*="panelHead"],
            #codex-twin-runtime-stage [class*="armTelemetryStrip"],
            #codex-twin-runtime-stage [class*="jointFlowPanel"],
            #codex-twin-runtime-stage [class*="poseMappingPanel"],
            #codex-twin-runtime-stage [class*="armLegendPanel"],
            #codex-twin-runtime-stage [class*="stitchTwinHudReplica"],
            #codex-twin-runtime-stage [class*="focusCloseButton"] {
              display: none !important;
            }
            #codex-twin-runtime-stage [class*="armCanvas"] {
              position: absolute !important;
              inset: 0 !important;
              width: 100% !important;
              height: 100% !important;
              min-height: 100% !important;
              border: 0 !important;
              border-radius: 0 !important;
              background: transparent !important;
              box-shadow: none !important;
              pointer-events: auto !important;
            }
            #codex-twin-runtime-stage [class*="armCanvas"] canvas {
              width: 100% !important;
              height: 100% !important;
              display: block !important;
              background: transparent !important;
            }
            #codex-twin-runtime-stage [class*="urdfToolbar"] {
              position: absolute !important;
              right: 24px !important;
              bottom: 24px !important;
              left: auto !important;
              top: auto !important;
              z-index: 20 !important;
              width: 300px !important;
              max-height: 170px !important;
              overflow: auto !important;
              pointer-events: auto !important;
              opacity: 0.001 !important;
            }
          `;
          doc.head.appendChild(compatStyle);
        }
        host.style.position = "absolute";
        host.style.inset = "0";
        host.style.zIndex = "3";
        host.style.pointerEvents = "auto";
        host.style.width = "100%";
        host.style.height = "100%";
        host.style.minHeight = "420px";
        window.setTimeout(() => window.dispatchEvent(new Event("resize")), 80);
        if (twinRuntimeHost !== host) setTwinRuntimeHost(host);
      } else if (twinRuntimeHost) {
        setTwinRuntimeHost(null);
      }
      const stitchUrdfInput = doc.querySelector<HTMLInputElement>('#urdf-import-panel input[type="file"][data-testid="rehab-urdf-file"]');
      const stitchUrdfDropzone = stitchUrdfInput?.parentElement as HTMLElement | null;
      if (stitchUrdfInput && stitchUrdfInput.dataset.codexBound !== "true") {
        stitchUrdfInput.dataset.codexBound = "true";
        stitchUrdfInput.onchange = (event) => {
          const file = (event.currentTarget as HTMLInputElement).files?.[0] ?? null;
          if (!file) return;
          setTwinImportRequest({ file, nonce: Date.now() });
          const currentModelLabel = doc.querySelector<HTMLElement>("#urdf-import-panel span.font-data-tabular");
          if (currentModelLabel) currentModelLabel.textContent = `当前模型: ${file.name}`;
        };
      }
      if (stitchUrdfInput && stitchUrdfDropzone && stitchUrdfDropzone.dataset.codexBound !== "true") {
        stitchUrdfDropzone.dataset.codexBound = "true";
        stitchUrdfDropzone.onclick = (event) => {
          event.preventDefault();
          stitchUrdfInput.click();
        };
      }
      if (twinImportRequest?.file) {
        const currentModelLabel = doc.querySelector<HTMLElement>("#urdf-import-panel span.font-data-tabular");
        if (currentModelLabel) currentModelLabel.textContent = `当前模型: ${twinImportRequest.file.name}`;
      }
    }

    if (activeModule === "muscle_assist") {
      const muscleRows = muscleRowsFromSensor(sensorPayload).slice(0, 4);
      const predictionRows = motionPredictionRowsFromSensor(sensorPayload);
      const firstPrediction = predictionRows[0];
      const assistActive = currentSemanticMode === "assistive_emg";
      const confidenceText = firstPrediction?.detail.match(/\d+%/)?.[0]?.replace("%", "") || (assistActive ? "85" : "0");
      const intentText = firstPrediction?.value || (assistActive ? "助力意图监听" : "等待动作意图");
      const relayInferenceSummary = text(
        modelRelaySuggestion.detail
          ?? modelRelayResponse.summary
          ?? modelRelayResponse.reply
          ?? modelRelayResponse.message
          ?? xiaozhiSession.reply
          ?? xiaozhiReplyPayload.reply,
        "",
      );
      const modelInferenceSource = firstPrediction?.confidence !== null && firstPrediction?.confidence !== undefined
        ? "sensor_state.model_outputs"
        : Object.keys(modelRelayResponse).length
          ? "model_relay_response"
          : Object.keys(xiaozhiSession).length || Object.keys(xiaozhiReplyPayload).length
            ? "xiaozhi_session"
            : "waiting";
      const modelInferenceConfidence = firstPrediction?.confidence !== null && firstPrediction?.confidence !== undefined
        ? `${Math.round((firstPrediction.confidence ?? 0) * 100)}%`
        : Number.isFinite(routeConfidence) && routeConfidence > 0
          ? `${Math.round(routeConfidence * 100)}%`
          : confidenceText !== "0" ? `${confidenceText}%` : "未上报";
      const modelIntentText = firstPrediction?.confidence !== null && firstPrediction?.confidence !== undefined
        ? intentText
        : text(
          modelRelaySemantic.mode
            ?? xiaozhiSession.kind
            ?? xiaozhiReplyPayload.kind,
          currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待推理",
        );
      const modelInferenceRows = [
        {
          label: "模型结果",
          value: modelIntentText,
          detail: firstPrediction?.detail || relayInferenceSummary || effectiveLanguageSummary || "等待 M55 / 模型推理结果",
        },
        {
          label: "置信度",
          value: modelInferenceConfidence,
          detail: `source: ${modelInferenceSource}`,
        },
        {
          label: "语义模式",
          value: semanticActionModeLabel(currentSemanticMode),
          detail: semanticModeLabel || relayBoundaryText,
        },
        ...predictionRows.slice(0, 2).map((row) => ({
          label: row.label,
          value: row.value,
          detail: row.detail,
        })),
      ].filter((row) => text(row.value, "") || text(row.detail, "")).slice(0, 4);
      const emgChannelTexts = Array.from({ length: 4 }, (_, index) => (
        muscleRows[index]?.displayValue || "0.000V / ADC 0"
      ));
      const emgChannelLabels = Array.from({ length: 4 }, (_, index) => (
        muscleRows[index]?.label || `CH${index + 1} EMG`
      ));
      const emgLiveCount = muscleRows.filter((row) => (
        (row.rawAdc !== null && row.rawAdc > 0) || (row.voltageV !== null && row.voltageV > 0)
      )).length;
      const peakRowIndex = muscleRows.reduce((bestIndex, row, index) => {
        const bestRaw = muscleRows[bestIndex]?.rawAdc ?? -1;
        const raw = row.rawAdc ?? -1;
        return raw > bestRaw ? index : bestIndex;
      }, 0);
      const peakRow = muscleRows[peakRowIndex] ?? muscleRows[0];
      const peakText = peakRow ? `峰值信号: CH${peakRowIndex + 1} ${peakRow.displayValue}` : "峰值信号: 0.000V / ADC 0";
      const liveWavePath = (index: number) => {
        const row = muscleRows[index];
        const raw = Math.max(0, Math.min(4095, Math.round(row?.rawAdc ?? 0)));
        if (raw <= 0) return "M0,50 L100,50";
        const amplitude = Math.max(3, Math.min(34, Math.round((raw / 4095) * 42)));
        const phase = index * 7;
        const points = Array.from({ length: 21 }, (_, pointIndex) => {
          const x = pointIndex * 5;
          const sign = pointIndex % 2 === 0 ? 1 : -1;
          const ripple = ((pointIndex + phase) % 5) - 2;
          const y = Math.max(8, Math.min(92, 50 + (sign * amplitude) + ripple));
          return `${pointIndex === 0 ? "M" : "L"}${x},${y}`;
        });
        return points.join(" ");
      };
      const syncStitchMuscleTelemetry = () => {
        const panel = Array.from(doc.querySelectorAll<HTMLElement>(".glass-panel"))
          .find((node) => (
            !!node.querySelector(".waveform-container")
            && !!node.querySelector('[data-role="muscle-refresh"]')
          ));
        const channelCards = Array.from(
          panel?.querySelectorAll<HTMLElement>(".grid.grid-cols-4.gap-4.mb-4 > div") ?? [],
        ).slice(0, 4);
        channelCards.forEach((card, index) => {
          card.setAttribute("data-codex-emg-channel", String(index + 1));
          const children = Array.from(card.children) as HTMLElement[];
          const labelNode = children[0];
          const valueNode = children[1];
          if (labelNode) labelNode.textContent = emgChannelLabels[index];
          if (valueNode) valueNode.textContent = emgChannelTexts[index];
        });

        const waveformCards = Array.from(panel?.querySelectorAll<HTMLElement>(".waveform-container") ?? []).slice(0, 4);
        waveformCards.forEach((card, index) => {
          card.setAttribute("data-codex-emg-channel", String(index + 1));
          const labelNode = Array.from(card.querySelectorAll<HTMLElement>("div"))
            .find((node) => (
              node.classList.contains("absolute")
              && node.classList.contains("top-2")
              && node.classList.contains("left-2")
            ));
          if (labelNode) {
            labelNode.textContent = `CH${index + 1} ${emgChannelTexts[index]}`;
          }
          const path = card.querySelector<SVGPathElement>("svg path");
          if (path) {
            path.setAttribute("d", liveWavePath(index));
            path.setAttribute("stroke", muscleRows[index]?.rawAdc ? "#06b6d4" : "#869397");
          }
        });

        const emgMetricLabel = Array.from(doc.querySelectorAll<HTMLElement>("div"))
          .find((node) => text(node.textContent, "").trim() === "四路 EMG");
        const emgMetricValue = emgMetricLabel?.parentElement?.querySelectorAll<HTMLElement>("div")[1];
        if (emgMetricValue) emgMetricValue.textContent = `${emgLiveCount}/4 路上报`;

        const featurePanel = Array.from(doc.querySelectorAll<HTMLElement>(".glass-panel"))
          .find((node) => text(node.textContent, "").includes("Feature Extraction Monitor"));
        Array.from(featurePanel?.querySelectorAll<HTMLElement>("div") ?? []).forEach((node) => {
          const current = text(node.textContent, "").trim();
          if (current.startsWith("前臂肌电:")) {
            node.textContent = `前臂肌电: ${emgLiveCount}/4 路上报`;
          }
        });
      };
      const syncStitchModelInference = () => {
        const panel = Array.from(doc.querySelectorAll<HTMLElement>(".glass-panel"))
          .find((node) => (
            !!node.querySelector(".waveform-container")
            && !!node.querySelector('[data-role="muscle-refresh"]')
          ));
        if (!panel) return;
        let inferenceStrip = panel.querySelector<HTMLElement>("#codex-model-inference-strip");
        if (!inferenceStrip) {
          inferenceStrip = doc.createElement("div");
          inferenceStrip.id = "codex-model-inference-strip";
          const statusGrid = panel.querySelector<HTMLElement>(".grid.grid-cols-4.gap-4.mb-4");
          statusGrid?.insertAdjacentElement("afterend", inferenceStrip);
        }
        inferenceStrip.setAttribute("data-codex-model-inference", "true");
        inferenceStrip.className = "grid grid-cols-4 gap-3 mb-3";
        inferenceStrip.innerHTML = modelInferenceRows.map((row) => `
          <div class="rounded border border-primary/20 bg-primary/5 px-3 py-2 min-w-0">
            <div class="font-data-tabular text-[9px] text-on-surface-variant truncate">${escapeHtml(row.label)}</div>
            <div class="font-data-tabular text-xs text-primary truncate">${escapeHtml(row.value)}</div>
            <div class="font-data-tabular text-[9px] text-on-surface-variant truncate">${escapeHtml(row.detail)}</div>
          </div>
        `).join("");
      };
      setText("h1", "VLA 控制台");
      setText("h2", intentText);
      setNthText(".font-telemetry-data.text-display-lg", 0, confidenceText);
      setAllText(".grid.grid-cols-4 .font-telemetry-label.text-\\[9px\\]", muscleRows.map((row, index) => `CH${index + 1}: ${row.label}`));
      setAllText(".grid.grid-cols-2 .font-telemetry-data", [
        assistActive ? "助力模式" : "监听中",
        "4-CH EMG",
        "M33 门控",
        liveDashboard.safety_boundary.m33_final_authority ? "最终裁决" : "等待声明",
      ]);
      replaceExactText([
        ["REAL-TIME PREDICTION (监控)", "实时意图预测（只读）"],
        ["FLEXION", assistActive ? "ASSIST" : "WAIT"],
        ["98%", `${confidenceText}%`],
        ["屈曲动作识别成功", assistActive ? "检测到助力意图候选" : "等待 M55 肌电意图"],
        ["ACTIVE", assistActive ? "ACTIVE" : "STANDBY"],
        ["助力方向: 屈曲上升沿", assistActive ? "助力方向: 等待 M55 确认" : "助力方向: 未触发"],
        ["前臂肌电: 高阈值", assistActive ? "前臂肌电: 候选监听" : "前臂肌电: 等待输入"],
        ["峰值信号: 142µV", peakText],
        ["频率中值: 82Hz", "采样: C8T6 ADC → 3.3V"],
        ["目标预测: 肘关节屈曲", assistActive ? "目标预测: 助力候选" : "目标预测: 未触发"],
        ["动作流同步", "动作流监听"],
        ["等待动作预测模型接入", "M55 模型输出接入后实时更新"],
        ["APP同步", "APP/训练库"],
        ["流式传输", currentSemanticMode === "training" ? "训练计划" : "预留"],
        ["基线 15µV", emgChannelTexts[0]],
        ["基线 15μV", emgChannelTexts[0]],
        ["CH2: 肱三头肌 (Triceps) [活跃]", "CH2: 肱三头肌 (Triceps)"],
        ["CH2: 肱三头肌 (主发力)", "CH2: 肱三头肌"],
        ["活跃 142µV", emgChannelTexts[1]],
        ["活跃 142μV", emgChannelTexts[1]],
        ["微弱 24µV", emgChannelTexts[2]],
        ["微弱 24μV", emgChannelTexts[2]],
        ["基线 12µV", emgChannelTexts[3]],
        ["基线 12μV", emgChannelTexts[3]],
        ["HIGH", "WAIT"],
        ["© 2024 Industrial Robotics. Safety Protocol v4.2 Active.", "VLA Rehab Arm · M55 肌电证据 / M33 最终安全裁决"],
      ]);
      syncStitchMuscleTelemetry();
      syncStitchModelInference();
      const muscleSnapshot = () => ({
        exported_at: new Date().toISOString(),
        project_id: projectId,
        boundary: "emg_assist_evidence_only_not_motion_permission",
        selected_device: {
          device_id: selected?.device_id ?? null,
          device_code: publicDeviceCode(selected, selectedIndex),
          robot_id: selected?.robot_id ?? null,
        },
        semantic: {
          mode: currentSemanticMode || "waiting",
          l_summary: effectiveLanguageSummary || "等待小智/L 输入",
          assist_requested: assistActive,
        },
        m55_inference: {
          intent: intentText,
          confidence_percent: Number(confidenceText) || 0,
          source: modelInferenceSource,
          summary: relayInferenceSummary,
          visible_rows: modelInferenceRows,
          predictions: predictionRows,
        },
        emg_channels: muscleRows,
        training_link: {
          app_training_library: currentSemanticMode === "training" ? "training_requested" : "available_as_shared_resource",
          m33_ble_fetch: "reserved_for_training_targets_and_constraints",
        },
        safety: {
          m33_final_authority: Boolean(liveDashboard.safety_boundary.m33_final_authority),
          motion_allowed_candidate: Boolean(motionAllowed),
          note: "浏览器只展示肌电和助力意图证据，不发送助力、电机、CAN 或 M33 控制。",
        },
      });
      const refreshButton = doc.querySelector<HTMLButtonElement>('[data-role="muscle-refresh"]');
      if (refreshButton) {
        refreshButton.onclick = (event) => {
          event.preventDefault();
          const original = refreshButton.textContent || "刷新";
          refreshButton.textContent = "刷新中";
          void refreshLiveDashboard(false).finally(() => {
            refreshButton.textContent = "已刷新";
            window.setTimeout(() => {
              refreshButton.textContent = original;
            }, 1200);
          });
        };
      }
      const exportButton = doc.querySelector<HTMLButtonElement>('[data-role="muscle-export"]');
      if (exportButton) {
        exportButton.onclick = (event) => {
          event.preventDefault();
          const blob = new Blob([JSON.stringify(muscleSnapshot(), null, 2)], { type: "application/json;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `rehab-arm-emg-assist-${projectId}-${Date.now()}.json`;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
          const original = exportButton.textContent || "导出";
          exportButton.textContent = "已导出";
          window.setTimeout(() => {
            exportButton.textContent = original;
          }, 1200);
        };
      }
      const trainingButton = doc.querySelector<HTMLButtonElement>('[data-role="muscle-open-training"]');
      if (trainingButton) {
        trainingButton.onclick = (event) => {
          event.preventDefault();
          setActiveModule("training");
        };
      }
      const logsButton = doc.querySelector<HTMLButtonElement>('[data-role="muscle-open-logs"]');
      if (logsButton) {
        logsButton.onclick = (event) => {
          event.preventDefault();
          setActiveModule("logs");
        };
      }
    }

    if (activeModule === "ai_model") {
      const providerLabel = relayProviderPreset?.label || relayConfig.provider || "等待 provider";
      const modelLabel = relayConfig.model || "未选择模型";
      const externalState = relayConfig.external_enabled && relayConfig.api_key_configured ? "外部模型启用" : "安全降级 / 本地预留";
      const tokenState = relayExportToken ? `已生成 · ${relayExportExpiresAt ? formatTime(relayExportExpiresAt) : "过期时间未知"}` : "未生成受限令牌";
      const prompt = relayPrompt.trim() || effectiveLanguageSummary || "等待小智/L 输入或手动测试指令";
      const summary = text(modelRelaySuggestion.detail, text(modelRelayResponse.summary, "模型中转尚无新响应；页面只展示建议，不下发真机运动。"));
      const safetyLine = `${relayBoundaryText} · ${motionAllowed ? "M33 候选开放仍需硬件裁决" : "M33 保持锁定"}`;
      const quickPrompts = [
        "请判断这句话是日常聊天、取物、训练、助力、仿真还是诊断模式，只输出模式和原因。",
        "请基于当前 VLA 视觉、目标、末端和安全状态，生成取物 dry-run 候选 A 字段摘要。",
        "请总结当前训练/肌电/视觉/仿真状态，给出下一步演示建议。",
      ];
      setText('[data-role="model-provider-value"]', providerLabel);
      setText('[data-role="model-base-url-value"]', relayConfig.base_url || "等待服务器配置");
      setText('[data-role="model-id-value"]', modelLabel);
      setText('[data-role="model-secret-state"]', relayConfig.api_key_configured ? "服务端已保存密钥" : "未配置 API key");
      setText('[data-role="model-external-state"]', externalState);
      setText('[data-role="model-token-state"]', tokenState);
      setText('[data-role="model-ws-endpoint"]', xiaozhiWsUrl || "选择设备后生成 WebSocket endpoint");
      setText('[data-role="model-http-endpoint"]', relayInvokeUrl || "选择设备后生成 HTTP endpoint");
      const snippet = doc.querySelector<HTMLElement>('[data-role="model-xiaozhi-ws"] pre');
      if (snippet) {
        snippet.textContent = [
          "// NanoPi / M55 Client Snippet",
          `const ws = new WebSocket("${xiaozhiWsUrl || "等待生成 WebSocket endpoint"}");`,
          `const token = "${relayExportToken ? "已生成，点击复制获取" : "点击导出生成 scoped token"}";`,
          "ws.onmessage = (event) => {",
          "  const msg = JSON.parse(event.data);",
          "  // 只接受 high_level_task / semantic_summary / mode / dry_run",
          "  // 禁止 raw_motor_control / torque / current / position override",
          "};",
          `// HTTP: ${relayInvokeUrl || "选择设备后生成 HTTP endpoint"}`,
        ].join("\n");
      }
      setText('[data-role="model-current-prompt"]', prompt);
      setText('[data-role="model-relay-summary"]', summary);
      setText('[data-role="model-safety-line"]', safetyLine);
      setText('[data-role="model-llm-latency"]', modelRelayProvider.external_call_ok === true ? "已通过" : "等待");
      setText('[data-role="model-filter-state"]', motionAllowed ? "候选 / PASS" : "锁定 / PASS");
      setText('[data-role="model-mode-state"]', semanticModeLabel || "等待模式");
      setText('[data-role="model-target-state"]', semanticTargetLabel || "等待目标");
      setText('[data-role="model-export-state"]', relayExportState === "creating" ? "令牌生成中" : relayExportState === "created" ? "令牌已生成" : relayExportState === "copied" ? "令牌已复制" : relayExportState === "error" ? relayExportError || "令牌生成失败" : "只读/WS权限");
      const providerInput = doc.querySelector<HTMLSelectElement>('[data-role="model-provider-input"]');
      if (providerInput) {
        if (providerInput.dataset.codexOptionsHydrated !== "true" && relayConfig.presets.length) {
          providerInput.innerHTML = relayConfig.presets
            .map((preset) => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`)
            .join("");
          providerInput.dataset.codexOptionsHydrated = "true";
        }
        providerInput.value = relayConfig.provider;
        if (!providerInput.value && relayConfig.presets[0]?.id) providerInput.value = relayConfig.presets[0].id;
        if (providerInput.dataset.codexRelayBound !== "true") {
          providerInput.dataset.codexRelayBound = "true";
          providerInput.addEventListener("change", () => {
            updateRelayProvider(providerInput.value);
          });
        }
      }
      const baseUrlInput = doc.querySelector<HTMLInputElement>('[data-role="model-base-url-input"]');
      if (baseUrlInput && doc.activeElement !== baseUrlInput) baseUrlInput.value = relayConfig.base_url;
      const modelInput = doc.querySelector<HTMLInputElement>('[data-role="model-id-input"]');
      if (modelInput && doc.activeElement !== modelInput) modelInput.value = relayConfig.model;
      const chatOutput = doc.querySelector<HTMLElement>('[data-role="model-chat-output"]');
      if (chatOutput) {
        const eventHtml = modelRelayEvents.slice(0, 4).map((event) => {
          const eventPayload = payloadOf(event);
          const response = record(eventPayload.relay_response);
          const title = eventTitle(event);
          const detail = text(response.summary ?? eventPayload.prompt ?? response.control_boundary, "model relay event");
          const gate = text(response.control_boundary ?? eventPayload.control_boundary, relayBoundaryText);
          return `
            <div class="text-on-surface-variant border-t border-outline-variant/20 pt-2">
              <span class="text-secondary">[${escapeHtml(formatTime(event.ts_unix))}]</span> ${escapeHtml(title)}<br/>
              <span class="text-primary">${escapeHtml(detail)}</span><br/>
              <span class="text-error text-[10px]">${escapeHtml(gate)}</span>
            </div>
          `;
        }).join("");
        chatOutput.innerHTML = `
          <div class="text-on-surface-variant">
            <span class="text-secondary">[SYS]</span> Relay boundary: ${escapeHtml(relayBoundaryText)}<br/>
            <span class="text-secondary">[SYS]</span> Provider: ${escapeHtml(providerLabel)} / ${escapeHtml(modelLabel)}
          </div>
          <div class="flex flex-col gap-1 items-end">
            <span class="text-primary text-[10px] opacity-70">L / USER</span>
            <div class="bg-primary/10 border border-primary/30 rounded p-2 text-primary max-w-[80%] break-words">${escapeHtml(prompt)}</div>
          </div>
          <div class="flex flex-col gap-1 items-start">
            <span class="text-secondary text-[10px] opacity-70">LLM (Filtered via Relay)</span>
            <div class="bg-surface-container border border-outline-variant/30 rounded p-2 text-on-surface max-w-[90%] break-words">${escapeHtml(summary)}</div>
            <span class="text-[10px] text-error bg-error/10 border border-error/20 px-1 mt-1 rounded inline-block">${escapeHtml(safetyLine)}</span>
          </div>
          ${eventHtml}
        `;
      }
      const promptInput = doc.querySelector<HTMLInputElement>('[data-role="model-prompt"] input');
      if (promptInput) promptInput.value = prompt;
      doc.querySelectorAll<HTMLButtonElement>('[data-role="model-quick-prompts"] button').forEach((button, index) => {
        if (button.dataset.codexRelayBound === "true") return;
        button.dataset.codexRelayBound = "true";
        button.addEventListener("click", (event) => {
          event.preventDefault();
          const nextPrompt = quickPrompts[index] || quickPrompts[0];
          const latestInput = doc.querySelector<HTMLInputElement>('[data-role="model-prompt"] input');
          if (latestInput) latestInput.value = nextPrompt;
          setRelayPrompt(nextPrompt);
          setText('[data-role="model-current-prompt"]', nextPrompt);
        });
      });
      const requestButton = doc.querySelector<HTMLElement>('[data-role="model-request-button"]');
      if (requestButton) requestButton.textContent = relayState === "sending" ? "请求中" : "测试";
      if (requestButton && requestButton.dataset.codexRelayBound !== "true") {
        requestButton.dataset.codexRelayBound = "true";
        requestButton.addEventListener("click", (event) => {
          event.preventDefault();
          const latestPrompt = doc.querySelector<HTMLInputElement>('[data-role="model-prompt"] input')?.value ?? "";
          setRelayPrompt(latestPrompt);
          setText('[data-role="model-current-prompt"]', latestPrompt || "使用默认 VLA 上下文提示");
          void requestModelRelay(latestPrompt);
        });
      }
      const exportButton = doc.querySelector<HTMLElement>('[data-role="model-export-token"]');
      if (exportButton) exportButton.innerHTML = `<span class="material-symbols-outlined text-[14px]">download</span> ${relayExportState === "creating" ? "生成中" : relayExportToken ? "重新导出" : "导出"}`;
      if (exportButton && exportButton.dataset.codexRelayBound !== "true") {
        exportButton.dataset.codexRelayBound = "true";
        exportButton.addEventListener("click", (event) => {
          event.preventDefault();
          void createRelayInvokeToken();
        });
      }
      doc.querySelectorAll<HTMLElement>('[data-role="model-copy-ws"], [data-role="model-copy-token"]').forEach((button) => {
        button.dataset.copyValue = button.getAttribute("data-role") === "model-copy-token"
          ? relayExportToken
          : xiaozhiWsUrl || relayInvokeUrl || "";
        if (button.dataset.codexRelayBound === "true") return;
        button.dataset.codexRelayBound = "true";
        button.addEventListener("click", async (event) => {
          event.preventDefault();
          const value = button.dataset.copyValue || "";
          if (!value) return;
          const copied = await copyTextToClipboard(value);
          if (copied) {
            button.textContent = "已复制";
            setText('[data-role="model-export-state"]', "已复制到剪贴板");
            window.setTimeout(() => {
              button.innerHTML = '<span class="material-symbols-outlined text-[12px]">content_copy</span> 复制';
            }, 1200);
          } else {
            button.textContent = "复制失败";
            setText('[data-role="model-export-state"]', "复制失败：请手动选中内容复制");
          }
        });
      });
      const configButton = doc.querySelector<HTMLElement>('[data-role="model-save-config"]');
      if (configButton) configButton.textContent = relayConfigState === "saving" ? "保存中" : relayConfigState === "saved" ? "已保存" : "配置";
      if (configButton && configButton.dataset.codexRelayBound !== "true") {
        configButton.dataset.codexRelayBound = "true";
        configButton.addEventListener("click", (event) => {
          event.preventDefault();
          const latestProvider = doc.querySelector<HTMLSelectElement>('[data-role="model-provider-input"]')?.value || relayConfig.provider;
          const latestBaseUrl = doc.querySelector<HTMLInputElement>('[data-role="model-base-url-input"]')?.value || relayConfig.base_url;
          const latestModel = doc.querySelector<HTMLInputElement>('[data-role="model-id-input"]')?.value || relayConfig.model;
          const latestApiKey = doc.querySelector<HTMLInputElement>('[data-role="model-api-key-input"]')?.value || "";
          setRelayConfig((current) => ({
            ...current,
            provider: latestProvider,
            base_url: latestBaseUrl,
            model: latestModel,
          }));
          setRelayConfigKey(latestApiKey);
          void saveRelayConfig({
            provider: latestProvider,
            base_url: latestBaseUrl,
            model: latestModel,
            api_key: latestApiKey,
          });
        });
      }
      const evidenceButton = doc.querySelector<HTMLElement>('[data-role="model-export-evidence"]');
      if (evidenceButton && evidenceButton.dataset.codexRelayBound !== "true") {
        evidenceButton.dataset.codexRelayBound = "true";
        evidenceButton.addEventListener("click", (event) => {
          event.preventDefault();
          const evidence = {
            exported_at: new Date().toISOString(),
            project_id: projectId,
            boundary: "model_relay_evidence_only_not_motion_permission",
            selected_device: {
              device_id: selected?.device_id ?? null,
              device_code: publicDeviceCode(selected, selectedIndex),
              robot_id: selected?.robot_id ?? null,
            },
            provider: {
              label: providerLabel,
              provider: relayConfig.provider,
              base_url: relayConfig.base_url,
              model: relayConfig.model,
              external_enabled: relayConfig.external_enabled,
              api_key_configured: relayConfig.api_key_configured,
            },
            semantic: {
              mode: semanticModeLabel || currentSemanticMode || "waiting",
              target: semanticTargetLabel || stereoTargetLabel || "",
              l_summary: effectiveLanguageSummary || "",
              prompt: doc.querySelector<HTMLInputElement>('[data-role="model-prompt"] input')?.value || prompt,
            },
            relay: {
              summary,
              safety_line: safetyLine,
              control_boundary: relayBoundaryText,
              response: modelRelayResponse,
              recent_events: modelRelayEvents.slice(0, 6),
            },
            endpoints: {
              http: relayInvokeUrl,
              websocket: xiaozhiWsUrl,
              token_generated: Boolean(relayExportToken),
              token_expires_at_unix: relayExportExpiresAt,
            },
            safety: {
              m33_final_authority: Boolean(liveDashboard.safety_boundary.m33_final_authority),
              motion_allowed_candidate: Boolean(motionAllowed),
              note: "浏览器只导出模型中转证据，不发送 CAN、电机、M33 或真实运动控制。",
            },
          };
          const blob = new Blob([JSON.stringify(evidence, null, 2)], { type: "application/json;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `rehab-arm-ai-model-evidence-${projectId}-${Date.now()}.json`;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
          const original = evidenceButton.textContent || "导出证据";
          evidenceButton.textContent = "已导出";
          window.setTimeout(() => {
            evidenceButton.textContent = original;
          }, 1200);
        });
      }
    }

    if (activeModule === "mode_router") {
      const modeLabel = currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待 L 分类";
      const aMode = currentSemanticMode ? String(currentSemanticMode) : "waiting";
      const routeTargetLabel = semanticTargetLabel || stereoTargetLabel || text(recentTargetMemory?.label, "等待目标");
      const routeConfidenceValue = routeConfidenceText || (currentSemanticMode && currentSemanticMode !== "chat" ? "92%" : "等待");
      const routeGateState = vlaGateLabel(languageGate);
      const actionPreview = JSON.stringify(
        {
          mode: aMode,
          mode_label: modeLabel,
          l_summary: effectiveLanguageSummary || "等待小智语义",
          target: {
            label: semanticTargetLabel || stereoTargetLabel || text(recentTargetMemory?.label, "等待目标"),
            visual_state: visualServoReady ? "target_and_end_effector_ready" : stereoHasContext ? "vision_observing" : "waiting_vision",
          },
          end_effector: {
            label: stereoEndEffectorLabel || text(recentEndEffectorMemory?.label, "等待末端"),
          },
          resources: {
            vision: visualServoStateText,
            data_hub: currentSemanticMode === "data_collection" ? "capture_annotation_training_feedback" : "available",
            mujoco: simulationReady ? "shadow_ready" : "shadow_waiting",
            emg: currentSemanticMode === "assistive_emg" ? "intent_required" : "standby",
            app_training_library: currentSemanticMode === "training" ? "plan_required" : "reserved",
          },
          gate: {
            dry_run: dryRunGateLabel(dryRunGateState),
            m33_final_authority: Boolean(liveDashboard.safety_boundary.m33_final_authority),
            motion_allowed_candidate: Boolean(motionAllowed),
            note: "平台只生成候选 A 字段，M33 是最终安全裁决。",
          },
        },
        null,
        2,
      );
      setText('[data-role="router-transcript"]', effectiveLanguageSummary ? `“${effectiveLanguageSummary}”` : "等待小智/L 输入");
      setText('[data-role="router-current-mode"]', aMode);
      setText('[data-role="router-mode-label"]', modeLabel);
      setText('[data-role="router-confidence"]', routeConfidenceValue);
      setText('[data-role="router-target"]', routeTargetLabel);
      setText('[data-role="router-gate-state"]', routeGateState);
      setText('[data-role="router-route-source"]', routeSourceText || semanticSourceLabel || "platform_language_semantic_router");
      setText('[data-role="router-fetch-state"]', currentSemanticMode === "fetch_object" || currentSemanticMode === "vision_servo" ? "已触发" : "待机");
      setText('[data-role="router-training-state"]', currentSemanticMode === "training" ? "已触发" : "待机");
      setText('[data-role="router-assist-state"]', currentSemanticMode === "assistive_emg" ? "监听中" : "待机");
      setText('[data-role="router-chat-state"]', currentSemanticMode === "chat" ? "隔离聊天" : "待机");
      setText('[data-role="router-diagnostics-state"]', currentSemanticMode === "diagnostics" || currentSemanticMode === "safety_review" ? "已触发" : "待机");
      setText('[data-role="router-data-state"]', currentSemanticMode === "data_collection" ? "采集中" : "待机");
      setText('[data-role="router-evidence-json"]', actionPreview);
      setText('[data-role="language-summary"]', effectiveLanguageSummary || "等待小智语义");
      setText('[data-role="semantic-mode"] .font-data-tabular', modeLabel);
      setText('[data-role="active-mode-badge"]', `${modeLabel} · ${modeStageText(String(currentSemanticMode || "waiting"))}`);
      setText('[data-role="a-field-mode"] .font-data-tabular', `A 字段：${modeLabel}`);
      setText('[data-role="safety-boundary"] .font-label-caps', motionAllowed ? "M33 候选通过" : "M33 保持锁定");
      setText('[data-role="action-field-preview"] .whitespace-pre', actionPreview);
      setText('[data-role="resource-vision"]', visualServoReady ? "已就绪" : stereoHasContext ? "观察中" : "等待");
      setText('[data-role="resource-sim"]', simulationReady ? "已回传" : "预留");
      setText('[data-role="resource-emg"]', currentSemanticMode === "assistive_emg" ? "监听中" : "待触发");
      setText('[data-role="resource-app"]', currentSemanticMode === "training" ? "需计划" : currentSemanticMode === "data_collection" ? "DATA 接管" : "预留");
      setText('[data-role="resource-m33"]', motionAllowed ? "候选" : "只读");
      const routedModuleByMode: Record<string, RehabWorkspaceModule> = {
        fetch_object: "action_planner",
        vision_servo: "action_planner",
        training: "training",
        assistive_emg: "muscle_assist",
        diagnostics: "diagnostics",
        safety_review: "diagnostics",
        data_collection: "data_hub",
        chat: "logs",
      };
      const routedModule = routedModuleByMode[aMode] || "logs";
      const bindRouterNav = (role: string, module: RehabWorkspaceModule) => {
        doc.querySelectorAll<HTMLButtonElement>(`[data-role="${role}"]`).forEach((button) => {
          button.onclick = (event) => {
            event.preventDefault();
            setActiveModule(module);
          };
        });
      };
      bindRouterNav("router-open-vision", "vision");
      bindRouterNav("router-open-planner", "action_planner");
      bindRouterNav("router-open-training", "training");
      bindRouterNav("router-open-muscle", "muscle_assist");
      bindRouterNav("router-open-logs", "logs");
      const modeButton = doc.querySelector<HTMLButtonElement>('[data-role="router-open-mode"]');
      if (modeButton) {
        modeButton.textContent = routedModule === "logs" ? "查看证据" : "进入模式";
        modeButton.onclick = (event) => {
          event.preventDefault();
          setActiveModule(routedModule);
        };
      }
      const exportButton = doc.querySelector<HTMLButtonElement>('[data-role="router-export"]');
      if (exportButton) {
        exportButton.onclick = (event) => {
          event.preventDefault();
          const snapshot = {
            exported_at: new Date().toISOString(),
            project_id: projectId,
            boundary: "semantic_route_evidence_only_not_motion_permission",
            selected_device: {
              device_id: selected?.device_id ?? null,
              device_code: publicDeviceCode(selected, selectedIndex),
              robot_id: selected?.robot_id ?? null,
            },
            route: JSON.parse(actionPreview),
            routed_module: routedModule,
          };
          const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `rehab-arm-semantic-route-${projectId}-${Date.now()}.json`;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
          const original = exportButton.textContent || "导出路由";
          exportButton.textContent = "已导出";
          window.setTimeout(() => {
            exportButton.textContent = original;
          }, 1200);
        };
      }
      const refreshButton = doc.querySelector<HTMLButtonElement>('[data-role="router-refresh"]');
      if (refreshButton) {
        refreshButton.onclick = (event) => {
          event.preventDefault();
          const original = refreshButton.textContent || "刷新";
          refreshButton.textContent = "刷新中";
          void refreshLiveDashboard(false).finally(() => {
            refreshButton.textContent = "已刷新";
            window.setTimeout(() => {
              refreshButton.textContent = original;
            }, 1200);
          });
        };
      }
    }

    if (activeModule === "action_planner") {
      const modeLabel = currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待 L";
      const targetLabel = semanticTargetLabel || stereoTargetLabel || text(recentTargetMemory?.label, "等待目标");
      const endEffectorLabel = stereoEndEffectorLabel || text(recentEndEffectorMemory?.label, "等待末端");
      const deltaText = visualServoDelta
        ? `Δu ${compactNumberText(visualServoDelta[0], " px")} / Δv ${compactNumberText(visualServoDelta[1], " px")}`
        : "等待目标+末端像素误差";
      const plannerCandidate = {
        mode: currentSemanticMode || "waiting",
        mode_label: modeLabel,
        l_summary: effectiveLanguageSummary || "等待小智/L 输入",
        visual_evidence: {
          target: targetLabel,
          end_effector: endEffectorLabel,
          loop_state: visualServoStateText,
          pixel_error: {
            du_px: visualServoDelta ? Number(visualServoDelta[0].toFixed(2)) : null,
            dv_px: visualServoDelta ? Number(visualServoDelta[1].toFixed(2)) : null,
            distance_px: visualServoDistancePx !== null ? Number(visualServoDistancePx.toFixed(2)) : null,
          },
          target_quality: targetQualityGateTitle,
          visual_lock: visualLockConfidenceText,
          camera_to_robot_calibrated: Boolean(cameraToRobotReady),
        },
        planner: {
          dry_run_gate: dryRunGateLabel(dryRunGateState),
          dry_run_allowed: Boolean(dryRunCandidateAllowed),
          reason: dryRunGateReason,
          next_step: pixelServo.nextStep,
          loop_policy: "continuous_visual_servo_approach",
        },
        ik_candidate: {
          status: text(ikCandidate.ik_status, "waiting_for_robot_frame_target"),
          target_robot_frame: record(ikCandidate.target_robot_frame),
          candidate_joint_trajectory: record(ikCandidate.candidate_joint_trajectory),
          ik_solver_report: record(ikCandidate.ik_solver_report),
          joint_limit_check: record(ikCandidate.joint_limit_check),
          collision_or_workspace_check: record(ikCandidate.collision_or_workspace_check),
          simulation_result: record(ikCandidate.simulation_result),
          mujoco_shadow_validation_plan: record(ikCandidate.mujoco_shadow_validation_plan),
          control_boundary: text(ikCandidate.control_boundary, "ik_candidate_evidence_only_not_motion_permission"),
        },
        simulation: {
          mujoco_shadow: simulationReady ? "ready" : "waiting",
          state: simulationPlanState,
        },
        safety: {
          browser_can_control: false,
          m33_final_authority: Boolean(liveDashboard.safety_boundary.m33_final_authority),
          motion_allowed_candidate: Boolean(motionAllowed),
        },
      };
      const ikSolverReport = record(ikCandidate.ik_solver_report);
      const ikBoundarySummary = record(ikSolverReport.joint_boundary_summary);
      const ikQuality = text(ikSolverReport.quality, "waiting");
      const ikError = text(ikSolverReport.position_error_m, "n/a");
      const ikSeeds = text(ikSolverReport.seed_count, "0");
      const ikNearLimit = text(ikBoundarySummary.near_limit_joint_count, "0");
      const plannerMujocoState = simulationReady
        ? `MUJOCO: ${simulationPlanState || "shadow_ready"}`
        : `MUJOCO: ${text(record(ikCandidate.mujoco_shadow_validation_plan).readiness, "waiting_shadow")}`;
      const plannerM33State = motionAllowed ? "M33: 候选允许" : "M33: 保持锁定";
      const targetFrame = record(ikCandidate.target_robot_frame);
      setText('[data-role="planner-mode"] h1', `动作规划 / ${modeLabel}`);
      setText('[data-role="planner-l-mode"]', modeLabel);
      setText('[data-role="planner-v-target"]', targetLabel);
      setText('[data-role="planner-end-effector"]', endEffectorLabel);
      setText('[data-role="planner-depth-state"]', cameraToRobotReady ? "camera_to_robot ready" : stereoDepth !== null ? "stereo_depth ready / 外参待定" : "等待深度/标定");
      setText('[data-role="planner-dry-run-gate"]', dryRunGateLabel(dryRunGateState));
      setText('[data-role="planner-dry-run-reason"]', dryRunGateReason);
      setText('[data-role="planner-candidate-allowed"]', dryRunCandidateAllowed ? "候选可生成" : "保持观察");
      setText('[data-role="planner-mujoco-state"]', plannerMujocoState);
      setText('[data-role="planner-m33-state"]', plannerM33State);
      const targetXInput = doc.querySelector<HTMLInputElement>('[data-role="planner-target-x"]');
      const targetYInput = doc.querySelector<HTMLInputElement>('[data-role="planner-target-y"]');
      const targetZInput = doc.querySelector<HTMLInputElement>('[data-role="planner-target-z"]');
      if (targetXInput && doc.activeElement !== targetXInput) targetXInput.value = text(targetFrame.x_m, ikTargetInput.x_m);
      if (targetYInput && doc.activeElement !== targetYInput) targetYInput.value = text(targetFrame.y_m, ikTargetInput.y_m);
      if (targetZInput && doc.activeElement !== targetZInput) targetZInput.value = text(targetFrame.z_m, ikTargetInput.z_m);
      const syncPlannerTargetInputs = () => {
        const nextTarget = {
          x_m: doc.querySelector<HTMLInputElement>('[data-role="planner-target-x"]')?.value ?? ikTargetInput.x_m,
          y_m: doc.querySelector<HTMLInputElement>('[data-role="planner-target-y"]')?.value ?? ikTargetInput.y_m,
          z_m: doc.querySelector<HTMLInputElement>('[data-role="planner-target-z"]')?.value ?? ikTargetInput.z_m,
        };
        ikDraftRef.current = {
          ...ikDraftRef.current,
          target: nextTarget,
        };
        setIkTargetInput(nextTarget);
      };
      [targetXInput, targetYInput, targetZInput].forEach((input) => {
        if (!input || input.dataset.codexBound === "true") return;
        input.dataset.codexBound = "true";
        input.addEventListener("input", syncPlannerTargetInputs);
        input.addEventListener("change", syncPlannerTargetInputs);
      });
      setText('[data-role="planner-ik-status"]', text(ikCandidate.ik_status, ikCandidateState === "error" ? "error" : "waiting"));
      setText('[data-role="planner-ik-quality"]', ikQuality);
      setText('[data-role="planner-ik-error"]', `${ikError}${ikError !== "n/a" ? " m" : ""}`);
      setText('[data-role="planner-ik-seeds"]', ikSeeds);
      setText('[data-role="planner-ik-near-limit"]', ikNearLimit);
      setText('[data-role="planner-candidate-json"]', JSON.stringify(plannerCandidate, null, 2));
      setText('[data-role="planner-language"] .text-headline-md', effectiveLanguageSummary ? `“${effectiveLanguageSummary}”` : "等待小智/L 输入");
      setText('[data-role="planner-target"] .font-label-caps', targetLabel);
      setAllText('[data-role="planner-end-effector"] span', [
        `末端：${endEffectorLabel}`,
        `误差：${visualServoDistanceText}`,
      ]);
      setText('[data-role="planner-error"] .font-data-tabular', deltaText);
      setText('[data-role="planner-dry-run-label"]', dryRunCandidateAllowed ? "dry-run 候选可展示" : dryRunGateLabel(dryRunGateState));
      setText('[data-role="planner-sim"] [data-role="planner-error"] .font-data-tabular', deltaText);
      setText('[data-role="planner-action-preview"] code', JSON.stringify(plannerCandidate, null, 2));
      setText('[data-role="planner-m33"]', `安全边界：${motionAllowed ? "M33 候选通过，仍需硬件裁决" : "M33 保持锁定"}；浏览器只展示候选 A 字段，不发送 CAN/M33 控制。`);
      const loopLabels = Array.from(doc.querySelectorAll<HTMLElement>('[data-role="planner-loop-state"] .font-label-caps'));
      const loopValues = [
        hasLanguageTask ? "L 已输入" : "等待 L 指令",
        hasStereoTargetForGate ? "V 目标已入场" : "等待 V 目标",
        visualServoReady ? "目标+末端可配对" : visualServoStateText,
        dryRunCandidateAllowed ? "Dry-run 候选生成" : dryRunGateLabel(dryRunGateState),
        simulationReady ? "仿真已回传" : "等待仿真验证",
        motionAllowed ? "M33 候选" : "M33 锁定",
      ];
      loopValues.forEach((value, index) => {
        if (loopLabels[index]) loopLabels[index].textContent = value;
      });
      const exportButton = doc.querySelector<HTMLButtonElement>('[data-role="planner-export"]');
      if (exportButton) {
        exportButton.onclick = (event) => {
          event.preventDefault();
          const snapshot = {
            exported_at: new Date().toISOString(),
            project_id: projectId,
            boundary: "a_field_candidate_export_only_not_motion_permission",
            selected_device: {
              device_id: selected?.device_id ?? null,
              device_code: publicDeviceCode(selected, selectedIndex),
              robot_id: selected?.robot_id ?? null,
            },
            candidate: plannerCandidate,
          };
          const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `rehab-arm-a-candidate-${projectId}-${Date.now()}.json`;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
          const original = exportButton.textContent || "导出候选";
          exportButton.textContent = "已导出";
          window.setTimeout(() => {
            exportButton.textContent = original;
          }, 1200);
        };
        if ((exportButton.textContent || "").includes("日志")) exportButton.textContent = "导出候选";
      }
      doc.querySelectorAll<HTMLButtonElement>('[data-role="planner-export-evidence"]').forEach((button) => {
        button.onclick = (event) => {
          event.preventDefault();
          const snapshot = {
            exported_at: new Date().toISOString(),
            project_id: projectId,
            boundary: "a_field_candidate_export_only_not_motion_permission",
            selected_device: {
              device_id: selected?.device_id ?? null,
              device_code: publicDeviceCode(selected, selectedIndex),
              robot_id: selected?.robot_id ?? null,
            },
            candidate: plannerCandidate,
          };
          const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `rehab-arm-a-candidate-${projectId}-${Date.now()}.json`;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
          const original = button.textContent || "导出 dry-run 证据";
          button.textContent = "已导出";
          window.setTimeout(() => {
            button.textContent = original;
          }, 1200);
        };
      });
      doc.querySelectorAll<HTMLButtonElement>('[data-role="planner-generate-ik"]').forEach((button) => {
        button.onclick = (event) => {
          event.preventDefault();
          syncPlannerTargetInputs();
          button.textContent = "生成中";
          void generateIkCandidate().finally(() => {
            window.setTimeout(() => {
              button.innerHTML = '<span class="material-symbols-outlined text-sm">settings_suggest</span> 生成 IK 候选';
            }, 800);
          });
        };
      });
      const bindPlannerNav = (role: string, module: RehabWorkspaceModule) => {
        doc.querySelectorAll<HTMLButtonElement>(`[data-role="${role}"]`).forEach((button) => {
          button.onclick = (event) => {
            event.preventDefault();
            setActiveModule(module);
          };
        });
      };
      bindPlannerNav("planner-open-vision", "vision");
      bindPlannerNav("planner-open-twin", "digital_twin");
      bindPlannerNav("planner-open-logs", "logs");
      bindPlannerNav("planner-open-router", "mode_router");
      const evidenceButton = doc.querySelector<HTMLButtonElement>('[data-role="planner-open-evidence"]');
      if (evidenceButton) {
        evidenceButton.onclick = (event) => {
          event.preventDefault();
          setActiveModule("logs");
        };
      }
      const holdButton = doc.querySelector<HTMLButtonElement>('[data-role="planner-hold-dry-run"]');
      if (holdButton) {
        holdButton.onclick = (event) => {
          event.preventDefault();
          const original = holdButton.textContent || "保持 Dry-run";
          holdButton.textContent = "已保持只读";
          setText('[data-role="planner-dry-run-label"]', `保持 dry-run：${dryRunGateLabel(dryRunGateState)}`);
          window.setTimeout(() => {
            holdButton.textContent = original;
          }, 1200);
        };
      }
      const refreshButton = doc.querySelector<HTMLButtonElement>('[data-role="planner-refresh"]');
      if (refreshButton) {
        refreshButton.onclick = (event) => {
          event.preventDefault();
          const original = refreshButton.textContent || "刷新候选";
          refreshButton.textContent = "刷新中...";
          void refreshLiveDashboard(false).finally(() => {
            refreshButton.textContent = "已刷新";
            window.setTimeout(() => {
              refreshButton.textContent = original;
            }, 1200);
          });
        };
      }
    }

    if (activeModule === "training") {
      const trainingActive = currentSemanticMode === "training";
      const trainingSummary = trainingActive
        ? "L 已路由到训练模式，等待 APP 训练库给出计划表。"
        : "训练模式预留：APP 训练库、M55 肌电推理、M33 BLE 获取目标与约束。";
      const trainingPreview = JSON.stringify(
        {
          mode: "training",
          active: trainingActive,
          l_summary: effectiveLanguageSummary || "等待小智/L 输入",
          app_training_library: {
            source: "user_app_form_or_app_ai",
            status: trainingActive ? "plan_required" : "reserved",
            note: "训练库由手机 APP 维护，可由用户填写，也可由 APP 端 AI 根据 M55 推理补全。",
          },
          m55_emg_inference: {
            channels: 4,
            status: currentSemanticMode === "assistive_emg" ? "assistive_mode_requested" : "reserved_for_training_feedback",
            output: ["动作意图", "疲劳", "发力肌肉", "可信度"],
          },
          m33_ble_fetch: {
            status: "reserved",
            direction: "M33 通过 BLE 从 APP 拉取训练目标和约束",
            browser_control: false,
          },
          platform_role: ["模式路由", "只读审核", "计划可视化", "日志证据"],
          safety: {
            m33_final_authority: Boolean(liveDashboard.safety_boundary.m33_final_authority),
            motion_allowed_candidate: Boolean(motionAllowed),
          },
        },
        null,
        2,
      );
      setText('[data-role="training-session-id"]', trainingActive ? "训练会话：L 已触发" : "训练会话：预留/待触发");
      setText('[data-role="training-language"] .font-data-tabular', effectiveLanguageSummary ? `“${effectiveLanguageSummary}”` : "等待训练 L 指令");
      setText('[data-role="platform-router"] .font-data-tabular', trainingActive ? "模式：训练" : `模式：${currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待"}`);
      setText('[data-role="training-app-library"] .font-data-tabular', trainingActive ? "等待 APP 计划表" : "APP 训练库预留");
      setText('[data-role="training-m55"] .font-data-tabular', currentSemanticMode === "assistive_emg" ? "助力意图监听" : "M55 肌电推理预留");
      setText('[data-role="training-m33-ble"] .font-data-tabular', "M33 BLE 拉取约束");
      setText('[data-role="training-ai-summary"] .text-primary.font-bold', trainingActive ? "训练计划待生成" : "训练计划链路预留");
      setText('[data-role="training-ai-summary"] p', trainingSummary);
      const planRows = Array.from(doc.querySelectorAll<HTMLElement>('[data-role="training-plan-table"] .grid + div, [data-role="training-plan-table"] .grid div'));
      if (planRows.length >= 4) {
        planRows[1].textContent = trainingActive ? "待 APP 回传" : "未建立";
        planRows[3].textContent = "M33 裁决";
      }
      const trainingLogRows = doc.querySelectorAll<HTMLElement>('[data-role="training-action-preview"] .font-mono > div');
      [
        `[L] ${effectiveLanguageSummary || "等待训练语音"}`,
        `[模式] ${trainingActive ? "training 已命中" : `当前 ${currentSemanticMode || "waiting"}`}`,
        "[APP] 训练库由用户填写或 APP 端 AI 补全",
        "[M55] 四通道肌电输出动作意图/疲劳/可信度",
        "[M33] 通过 BLE 获取训练目标和约束，网页只做审核显示",
        `[安全] ${motionAllowed ? "M33 候选允许" : "M33 保持锁定"}`,
      ].forEach((line, index) => {
        if (trainingLogRows[index]) trainingLogRows[index].textContent = line;
      });
      const stageLabels = Array.from(doc.querySelectorAll<HTMLElement>('[data-role="training-stage"] .font-data-tabular'));
      const stageTexts = [
        trainingActive ? "01. L 训练意图" : "01. 等待 L",
        trainingActive ? "APP 待计划" : "目标：APP",
        trainingActive ? "已触发" : "Pending",
        "02. APP/AI 计划",
        "目标：训练库",
        "待开始",
        "03. M33 BLE 获取",
        "目标：约束",
        "待开始",
      ];
      stageTexts.forEach((line, index) => {
        if (stageLabels[index]) stageLabels[index].textContent = line;
      });
      setText('[data-role="training-safety"] .text-error.border', motionAllowed ? "M33 候选" : "M33 锁定");
      setAllText('[data-role="training-safety"] .font-data-tabular.text-\\[13px\\]', [
        "M33 管控",
        "训练约束",
        "异常断开",
      ]);
      const previewNode = doc.querySelector<HTMLElement>('[data-role="training-action-preview"]');
      if (previewNode) previewNode.dataset.preview = trainingPreview;
      const refreshButton = doc.querySelector<HTMLButtonElement>('[data-role="training-refresh"]');
      if (refreshButton) {
        refreshButton.onclick = (event) => {
          event.preventDefault();
          const original = refreshButton.textContent || "刷新训练库";
          refreshButton.textContent = "刷新中";
          void refreshLiveDashboard(false).finally(() => {
            refreshButton.textContent = "已刷新";
            window.setTimeout(() => {
              refreshButton.textContent = original;
            }, 1200);
          });
        };
      }
      const aiButton = doc.querySelector<HTMLButtonElement>('[data-role="training-open-ai"]');
      if (aiButton) {
        aiButton.onclick = (event) => {
          event.preventDefault();
          setActiveModule("ai_model");
        };
      }
      const exportButton = doc.querySelector<HTMLButtonElement>('[data-role="training-export"]');
      if (exportButton) {
        exportButton.onclick = (event) => {
          event.preventDefault();
          const snapshot = {
            exported_at: new Date().toISOString(),
            project_id: projectId,
            boundary: "training_orchestration_evidence_only_not_motion_permission",
            selected_device: {
              device_id: selected?.device_id ?? null,
              device_code: publicDeviceCode(selected, selectedIndex),
              robot_id: selected?.robot_id ?? null,
            },
            training_chain: JSON.parse(trainingPreview),
          };
          const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `rehab-arm-training-chain-${projectId}-${Date.now()}.json`;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
          const original = exportButton.textContent || "导出训练日志";
          exportButton.textContent = "已导出";
          window.setTimeout(() => {
            exportButton.textContent = original;
          }, 1200);
        };
      }
      const appButton = doc.querySelector<HTMLButtonElement>('[data-role="training-open-app"]');
      if (appButton) {
        appButton.innerHTML = '<span class="material-symbols-outlined text-[18px]" data-icon="apps">apps</span> 查看 APP 训练库';
        appButton.onclick = (event) => {
          event.preventDefault();
          window.open("/rehab-arm-mobile/index.html#training-library", "_blank", "noopener,noreferrer");
        };
      }
    }

    setText("#orchestration .text-\\[18px\\].text-primary-container", effectiveLanguageSummary || "等待 XiaoZhi / L 输入");
    setAllText("#orchestration .telemetry-strip span:last-child", [
      currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "WAITING",
      visualServoReady ? "V READY" : "V OBSERVE",
      dryRunGateLabel(dryRunGateState),
      motionAllowed ? "M33 CANDIDATE" : "M33 LOCKED",
    ]);
    setText("span.font-telemetry-data.italic", effectiveLanguageSummary || "等待 XiaoZhi / L 输入");
    setAllText("main .glass-panel span.font-telemetry-data", [
      currentSemanticMode ? semanticActionModeLabel(currentSemanticMode).toUpperCase() : "WAITING",
      visualServoReady ? "V READY" : "V OBSERVE",
      dryRunGateLabel(dryRunGateState).toUpperCase(),
      motionAllowed ? "M33 CANDIDATE" : "M33 LOCKED",
    ]);

    if (activeModule === "data_hub") {
      const batchLabel = publicBatchLabel(selected?.current_session, "暂无批次");
      const frameCount = Number(Boolean(leftImage)) + Number(Boolean(rightImage));
      const labelSummary = [
        stereoTargetLabel || recentTargetMemory?.label || "water_bottle:等待",
        stereoEndEffectorLabel || recentEndEffectorMemory?.label || "end_effector/gripper_tip:等待",
      ];
      const dataPacket = () => ({
        schema_version: "rehab_arm_dataset_evidence_v1",
        exported_at: new Date().toISOString(),
        project_id: projectId,
        selected_device_id: selectedDeviceId || selected?.device_id || "unknown",
        boundary: "dataset_evidence_only_not_motion_permission",
        note: "数据页只负责采集/标注/训练回流证据与入口，不发送 CAN/M33/电机控制。",
        current_batch: batchLabel,
        sources: {
          stereo_left_frame_available: Boolean(leftImage),
          stereo_right_frame_available: Boolean(rightImage),
          language_summary: effectiveLanguageSummary || "waiting",
          semantic_mode: currentSemanticMode || "waiting",
          emg_payload_source: publicSourceLabel(sensorPayload.source, "waiting"),
          simulation_ready: simulationReady,
          diagnostics_events: liveDashboard.recent_events.length,
        },
        labels: {
          target: stereoTargetLabel || recentTargetMemory?.label || "waiting",
          end_effector: stereoEndEffectorLabel || recentEndEffectorMemory?.label || "waiting",
          expected_classes: ["water_bottle", "end_effector", "gripper_tip"],
        },
        training_feedback: {
          quality_ready: qualityReady,
          data_collection_mode_active: currentSemanticMode === "data_collection",
          model_relay_available: relayConfig.external_enabled,
          app_training_library_reserved: true,
        },
        workbench_routes: {
          capture: `/projects/${projectId}/robotics?tab=camera&device=${encodeURIComponent(selected?.device_id ?? "")}`,
          annotation: `/projects/${projectId}/robotics?tab=dataset&device=${encodeURIComponent(selected?.device_id ?? "")}`,
          training: `/projects/${projectId}/robotics?tab=model&device=${encodeURIComponent(selected?.device_id ?? "")}`,
          evaluation: `/projects/${projectId}/robotics?tab=chart&device=${encodeURIComponent(selected?.device_id ?? "")}`,
        },
        safety_boundary: {
          m33_final_authority: liveDashboard.safety_boundary.m33_final_authority,
          browser_can_send_motion: false,
          forbidden_outputs: ["can_frame", "motor_current", "motor_torque", "raw_motor_position", "raw_motor_velocity", "m33_safety_override", "direct_motor_command"],
        },
      });
      const sourceRows = [
        { title: "双目视觉", value: frameCount ? `${frameCount}/2 帧可用` : "等待帧", detail: `${visualEvidenceImageSource} · ${visualServoStateText}`, tone: frameCount ? "text-primary" : "text-on-surface-variant" },
        { title: "L 指令", value: currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待小智", detail: effectiveLanguageSummary || "暂无语义输入", tone: currentSemanticMode ? "text-primary" : "text-on-surface-variant" },
        { title: "EMG/M55", value: publicSourceLabel(sensorPayload.source, "等待数据"), detail: currentSemanticMode === "assistive_emg" ? "助力样本可回流" : "非实时数据资产预留", tone: currentSemanticMode === "assistive_emg" ? "text-secondary-fixed-dim" : "text-on-surface-variant" },
        { title: "仿真/诊断", value: simulationReady ? "MuJoCo 已回传" : "等待 shadow", detail: `${liveDashboard.recent_events.length} 条审计事件`, tone: simulationReady ? "text-primary" : "text-on-surface-variant" },
      ];
      const sources = doc.querySelector<HTMLElement>('[data-role="data-sources"]');
      if (sources) {
        sources.innerHTML = sourceRows.map((row) => `
          <div class="border border-outline-variant/20 bg-surface-container p-3">
            <p class="font-label-caps ${row.tone}">${escapeHtml(row.title)}</p>
            <strong class="block font-data-tabular text-on-surface mt-1">${escapeHtml(row.value)}</strong>
            <p class="text-sm text-on-surface-variant mt-1">${escapeHtml(row.detail)}</p>
          </div>
        `).join("");
      }
      const keyframes = doc.querySelector<HTMLElement>('[data-role="data-keyframes"]');
      if (keyframes) {
        const frames = [
          { label: "左目样本", src: leftImage, note: stereoTargetLabel || "等待目标标签" },
          { label: "右目样本", src: rightImage, note: stereoEndEffectorLabel || "等待末端标签" },
        ];
        keyframes.innerHTML = frames.map((frame) => `
          <div class="relative bg-surface-container border border-outline-variant/20 overflow-hidden">
            ${frame.src
              ? `<img src="${escapeHtml(frame.src)}" alt="${escapeHtml(frame.label)}" class="w-full h-full object-cover opacity-80"/>`
              : `<div class="h-full min-h-[180px] grid place-items-center text-on-surface-variant">${escapeHtml(frame.note)}</div>`}
            <div class="absolute left-0 right-0 bottom-0 bg-black/60 px-2 py-1 font-data-tabular text-[11px] text-on-surface">${escapeHtml(frame.label)} · ${escapeHtml(frame.note)}</div>
          </div>
        `).join("");
      }
      setText('[data-role="data-quality"]', qualityReady ? "质量可用" : "等待质量门");
      setText('[data-role="data-batch"]', batchLabel);
      setText('[data-role="data-frames"]', `${frameCount}/2`);
      setText('[data-role="data-labels"]', labelSummary.join(" / "));
      setText('[data-role="data-feedback"]', qualityReady ? "可训练/评估" : currentSemanticMode === "data_collection" ? "采集中" : "待补样本");
      const packet = doc.querySelector<HTMLElement>('[data-role="data-packet"]');
      if (packet) packet.textContent = JSON.stringify(dataPacket(), null, 2);
      const bindDataButton = (selector: string, handler: (button: HTMLButtonElement) => void) => {
        const button = doc.querySelector<HTMLButtonElement>(selector);
        if (!button || button.dataset.codexBound === "true") return;
        button.dataset.codexBound = "true";
        button.addEventListener("click", (event) => {
          event.preventDefault();
          handler(button);
        });
      };
      bindDataButton('[data-role="data-refresh"]', (button) => {
        const original = button.textContent || "刷新";
        button.textContent = "刷新中...";
        void refreshLiveDashboard(false).finally(() => {
          button.textContent = "已刷新";
          window.setTimeout(() => {
            button.textContent = original;
          }, 1200);
        });
      });
      bindDataButton('[data-role="data-export"]', (button) => {
        const blob = new Blob([JSON.stringify(dataPacket(), null, 2)], { type: "application/json;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = doc.createElement("a");
        link.href = url;
        link.download = `rehab-arm-dataset-evidence-${projectId}-${Date.now()}.json`;
        link.click();
        URL.revokeObjectURL(url);
        const original = button.textContent || "导出证据";
        button.textContent = "已导出";
        window.setTimeout(() => {
          button.textContent = original;
        }, 1200);
      });
      bindDataButton('[data-role="data-copy-packet"]', (button) => {
        void copyTextToClipboard(packet?.textContent || JSON.stringify(dataPacket(), null, 2)).then((copied) => {
          if (!copied) return;
          const original = button.innerHTML;
          button.innerHTML = '<span class="material-symbols-outlined text-[18px]">done</span>';
          window.setTimeout(() => {
            button.innerHTML = original;
          }, 1200);
        });
      });
      bindDataButton('[data-role="data-open-workbench"]', () => {
        window.location.href = `/projects/${projectId}/robotics?tab=dataset&device=${encodeURIComponent(selected?.device_id ?? "")}`;
      });
      bindDataButton('[data-role="data-open-capture"]', () => {
        window.location.href = `/projects/${projectId}/robotics?tab=camera&device=${encodeURIComponent(selected?.device_id ?? "")}`;
      });
      bindDataButton('[data-role="data-open-annotation"]', () => {
        window.location.href = `/projects/${projectId}/robotics?tab=dataset&device=${encodeURIComponent(selected?.device_id ?? "")}`;
      });
      bindDataButton('[data-role="data-open-training"]', () => {
        window.location.href = `/projects/${projectId}/robotics?tab=model&device=${encodeURIComponent(selected?.device_id ?? "")}`;
      });
      bindDataButton('[data-role="data-open-evaluation"]', () => {
        window.location.href = `/projects/${projectId}/robotics?tab=chart&device=${encodeURIComponent(selected?.device_id ?? "")}`;
      });
      bindDataButton('[data-role="data-open-vision"]', () => {
        setActiveModule("vision");
      });
      bindDataButton('[data-role="data-open-ai"]', () => {
        setActiveModule("ai_model");
      });
      bindDataButton('[data-role="data-open-logs"]', () => {
        setActiveModule("logs");
      });
    }

    if (activeModule === "diagnostics") {
      const rows = Array.from(doc.querySelectorAll<HTMLTableRowElement>("tbody tr"));
      const diagnosticRows = [
        { name: "M33 安全门", type: "最终裁决", id: "final authority", status: motionAllowed ? "候选允许" : "真机锁定", age: stateText(currentSafetyState) },
        { name: "NanoPi 视觉", type: "双 USB 摄像头", id: publicDeviceCode(selected, selectedIndex), status: selected?.online_state === "online" ? "在线" : "离线", age: formatTime(selected?.last_upload_ts_unix) },
        { name: "VLA-V 双目", type: "视觉记忆", id: stereoHasContext ? "stereo_vision_context" : "等待 V", status: visualServoStateText, age: stereoLoopProgressText },
        { name: "VLA-A 规划", type: "dry-run", id: operationModeLabel(operationMode), status: dryRunGateLabel(dryRunGateState), age: dryRunGateReason },
        { name: "VLA-L / 小智", type: "M55 侧语义", id: text(xiaozhiSession.session_id, "等待会话"), status: xiaozhiUiStateLabel(xiaozhiSession.ui_state), age: effectiveLanguageSummary },
        { name: "CAN / 电机", type: "只读遥测", id: `${motors.length} motors`, status: wiringBadCount ? `${wiringBadCount} 路异常` : "等待/正常", age: wiringHealth.overall || "unknown" },
      ];
      diagnosticRows.forEach((item, index) => {
        const cells = rows[index]?.querySelectorAll<HTMLElement>("td");
        if (!cells?.length) return;
        cells[0].textContent = item.name;
        if (cells[1]) cells[1].textContent = item.type;
        if (cells[2]) cells[2].textContent = item.status;
        if (cells[3]) cells[3].textContent = item.age || item.id;
      });
      const nodeTexts: Array<[string, string[]]> = [
        ['[data-role="diagnostics-nanopi"] .flex.justify-between span:last-child', [
          leftStereoImageSrc || absoluteImageUrl ? "左目有帧" : "左目等待",
          rightStereoImageSrc ? "右目有帧" : "右目等待",
          stereoHasContext ? "V 上下文同步" : "等待上传",
        ]],
        ['[data-role="diagnostics-l"] .flex.justify-between span:last-child', [
          effectiveLanguageSummary || "等待语义摘要",
          currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待分类",
        ]],
        ['[data-role="diagnostics-training"] .flex.justify-between span:last-child', [
          currentSemanticMode === "training" ? "训练触发" : "训练库预留",
          "BLE 预留",
        ]],
        ['[data-role="diagnostics-vision"] .flex.justify-between span:last-child', [
          stereoDepth !== null ? compactNumberText(stereoDepth, " m") : "未标定深度",
          visualLockConfidenceText,
          visualServoStateText,
        ]],
        ['[data-role="diagnostics-planner"] .flex.justify-between span:last-child', [
          dryRunGateLabel(dryRunGateState),
          dryRunCandidateAllowed ? "候选可展示" : "保持观察",
        ]],
        ['[data-role="diagnostics-mujoco"] span:last-child', [
          simulationReady ? `已回传：${simulationPlanState}` : "等待仿真验证",
        ]],
        ['[data-role="diagnostics-m33"] .flex.justify-between span:last-child', [
          motionAllowed ? "候选通过" : "真机锁定",
          liveDashboard.safety_boundary.m33_final_authority ? "最终裁决" : "等待声明",
          currentSafetyState ? stateText(currentSafetyState) : "等待状态",
        ]],
        ['[data-role="diagnostics-can"] .flex.justify-between span:last-child', [
          wiringBadCount ? `${wiringBadCount} 路异常` : "等待/正常",
          motors.length ? `${motors.length} 电机` : "等待遥测",
          wiringHealth.overall || "只读遥测",
        ]],
      ];
      nodeTexts.forEach(([selector, values]) => setAllText(selector, values));
      setAllText('[data-role="diagnostics-safety"] .font-data-tabular.text-xs span:last-child', [
        motionAllowed ? "候选允许 / M33 裁决" : "真机锁定 / 只读",
        wiringBadCount ? `${wiringBadCount} 路异常` : "0 / 只读",
      ]);
      const logLines = doc.querySelectorAll<HTMLElement>("section.col-span-12 div.flex-1 p");
      liveDashboard.recent_events.slice(0, 8).forEach((event, index) => {
        if (logLines[index]) logLines[index].textContent = `[${formatTime(event.ts_unix)}] ${eventTitle(event)} · ${text(event.record_type, "event")}`;
      });
      const eventRows = doc.querySelectorAll<HTMLElement>('[data-role="diagnostics-events"] .font-data-tabular > div');
      const fallbackEvents = [
        `[系统] ${selected?.online_state === "online" ? "NanoPi 在线" : "NanoPi 等待在线"}`,
        `[L] ${effectiveLanguageSummary || "等待小智语义"}`,
        `[V] ${visualServoStateText} · ${visualServoDistanceText}`,
        `[A] ${dryRunGateLabel(dryRunGateState)} · ${dryRunGateReason}`,
        `[MuJoCo] ${simulationReady ? simulationPlanState : "等待 shadow 回传"}`,
        `[M33] ${motionAllowed ? "候选允许" : "保持锁定"} · 浏览器只读`,
        `[CAN] ${wiringBadCount ? `${wiringBadCount} 路异常` : "等待/正常"} · 只读观察`,
      ];
      fallbackEvents.forEach((line, index) => {
        const row = eventRows[index];
        if (!row) return;
        row.textContent = line;
      });
      const bindDiagnosticsButton = (selector: string, handler: (button: HTMLButtonElement) => void) => {
        const button = doc.querySelector<HTMLButtonElement>(selector);
        if (!button || button.dataset.codexBound === "true") return;
        button.dataset.codexBound = "true";
        button.addEventListener("click", (event) => {
          event.preventDefault();
          handler(button);
        });
      };
      bindDiagnosticsButton('[data-role="diagnostics-refresh"]', (button) => {
        const original = button.textContent || "刷新状态";
        button.textContent = "刷新中...";
        void refreshLiveDashboard(false).finally(() => {
          button.textContent = "已刷新";
          window.setTimeout(() => {
            button.textContent = original;
          }, 1200);
        });
      });
      bindDiagnosticsButton('[data-role="diagnostics-export"]', (button) => {
        downloadDiagnosticsSnapshot();
        const original = button.textContent || "导出诊断";
        button.textContent = "已导出";
        window.setTimeout(() => {
          button.textContent = original;
        }, 1200);
      });
      bindDiagnosticsButton('[data-role="diagnostics-open-logs"]', () => {
        setActiveModule("logs");
      });
    }

    if (activeModule === "logs") {
      const stream = doc.querySelector<HTMLElement>('[data-role="logs-stream"]');
      const keyframes = doc.querySelector<HTMLElement>('[data-role="logs-keyframes"]');
      const packet = doc.querySelector<HTMLElement>('[data-role="logs-packet"]');
      const fallbackLogEvents = [
        {
          record_type: "vla_language",
          ts_unix: Date.now() / 1000,
          payload: { summary: effectiveLanguageSummary || "等待小智/L 输入", mode: currentSemanticMode || "waiting" },
        },
        {
          record_type: "vla_vision",
          ts_unix: Date.now() / 1000,
          payload: { summary: `${visualServoStateText} · ${visualServoDistanceText}`, target: stereoTargetLabel || "等待目标", end_effector: stereoEndEffectorLabel || "等待末端" },
        },
        {
          record_type: "vla_action",
          ts_unix: Date.now() / 1000,
          payload: { summary: `${dryRunGateLabel(dryRunGateState)} · ${dryRunGateReason}`, m33_final_authority: liveDashboard.safety_boundary.m33_final_authority },
        },
      ];
      const eventsForLogs = liveDashboard.recent_events.length ? liveDashboard.recent_events : fallbackLogEvents;
      const logIcon = (kind: string) => {
        const value = kind.toLowerCase();
        if (value.includes("safety") || value.includes("estop") || value.includes("error")) return { icon: "warning", tone: "text-error", bg: "bg-error-container" };
        if (value.includes("vision") || value.includes("camera")) return { icon: "visibility", tone: "text-primary", bg: "bg-surface-variant" };
        if (value.includes("voice") || value.includes("language") || value.includes("xiaozhi")) return { icon: "mic", tone: "text-primary", bg: "bg-surface-variant" };
        if (value.includes("plan") || value.includes("action")) return { icon: "route", tone: "text-secondary-fixed-dim", bg: "bg-secondary-container/20" };
        if (value.includes("model")) return { icon: "psychology", tone: "text-secondary-fixed-dim", bg: "bg-secondary-container/20" };
        return { icon: "terminal", tone: "text-primary", bg: "bg-surface-variant" };
      };
      const logCategory = (kind: string) => {
        const value = kind.toLowerCase();
        if (value.includes("error") || value.includes("fault") || value.includes("estop") || value.includes("safety")) return value.includes("safety") ? "safety" : "errors";
        if (value.includes("command") || value.includes("action") || value.includes("plan") || value.includes("model")) return "commands";
        return "all";
      };
      const packetForEvent = (event: unknown) => {
        const eventRecord = record(event);
        return JSON.stringify({
          selected_event: Object.keys(eventRecord).length ? {
            record_type: eventRecord.record_type,
            ts_unix: eventRecord.ts_unix,
            title: eventTitle(eventRecord),
            payload: payloadOf(eventRecord),
          } : null,
          current_context: {
            l_summary: effectiveLanguageSummary || "waiting",
            mode: currentSemanticMode || "waiting",
            vision: {
              target: stereoTargetLabel || "waiting",
              end_effector: stereoEndEffectorLabel || "waiting",
              state: visualServoStateText,
              distance: visualServoDistanceText,
            },
            action: {
              dry_run_gate: dryRunGateLabel(dryRunGateState),
              reason: dryRunGateReason,
            },
            safety: {
              motion_allowed_candidate: motionAllowed,
              m33_final_authority: liveDashboard.safety_boundary.m33_final_authority,
            },
          },
        }, null, 2);
      };
      const logsEvidenceSnapshot = () => ({
        schema_version: "rehab_arm_logs_evidence_v1",
        exported_at: new Date().toISOString(),
        project_id: projectId,
        selected_device_id: selectedDeviceId || selected?.device_id || "unknown",
        boundary: "logs_evidence_export_only_not_motion_permission",
        note: "Browser log exports are local evidence snapshots only; they cannot grant motion permission or bypass M33.",
        safety_boundary: {
          browser_can_send_motion: false,
          forbidden_outputs: [
            "can_frame",
            "motor_current",
            "motor_torque",
            "raw_motor_position",
            "raw_motor_velocity",
            "m33_safety_override",
            "direct_motor_command",
          ],
          m33_final_authority: liveDashboard.safety_boundary.m33_final_authority,
          current_safety_state: stateText(currentSafetyState),
          motion_allowed_candidate: motionAllowed,
        },
        current_context: {
          semantic_mode: currentSemanticMode || "waiting",
          language_summary: effectiveLanguageSummary || "waiting",
          vision: {
            target: stereoTargetLabel || "waiting",
            end_effector: stereoEndEffectorLabel || "waiting",
            visual_servo_state: visualServoStateText,
            distance: visualServoDistanceText,
            left_frame_available: Boolean(leftStereoImageSrc || absoluteImageUrl),
            right_frame_available: Boolean(rightStereoImageSrc),
          },
          action: {
            dry_run_gate: dryRunGateLabel(dryRunGateState),
            dry_run_candidate_allowed: dryRunCandidateAllowed,
            reason: dryRunGateReason,
          },
        },
        recent_events: eventsForLogs.slice(0, 32).map((event, index) => {
          const eventRecord = record(event);
          return {
            index,
            record_type: text(eventRecord.record_type, `event_${index + 1}`),
            ts_unix: eventRecord.ts_unix,
            title: eventTitle(eventRecord),
            category: logCategory(text(eventRecord.record_type, "")),
            payload: payloadOf(eventRecord),
          };
        }),
      });
      const bindLogsButton = (selector: string, handler: (button: HTMLButtonElement) => void) => {
        const button = doc.querySelector<HTMLButtonElement>(selector);
        if (!button || button.dataset.codexBound === "true") return;
        button.dataset.codexBound = "true";
        button.addEventListener("click", (event) => {
          event.preventDefault();
          handler(button);
        });
      };
      if (stream) {
        stream.innerHTML = eventsForLogs.slice(0, 12).map((event, index) => {
          const eventRecord = record(event);
          const kind = text(eventRecord.record_type, `event_${index + 1}`);
          const payload = payloadOf(event);
          const response = record(payload.relay_response);
          const detail = text(
            response.summary
              ?? payload.summary
              ?? payload.prompt
              ?? payload.scene_summary
              ?? payload.status
              ?? payload.control_boundary,
            eventTitle(event),
          );
          const meta = logIcon(kind);
          const lineClass = index < Math.min(eventsForLogs.length, 12) - 1
            ? "relative pl-8 before:content-[''] before:absolute before:left-[11px] before:top-6 before:bottom-[-24px] before:w-[2px] before:bg-outline-variant/20"
            : "relative pl-8";
          return `
            <div class="${lineClass} cursor-pointer hover:bg-surface-variant/20 rounded-sm transition-colors" data-codex-log-index="${index}" data-codex-log-category="${logCategory(kind)}">
              <div class="absolute left-0 top-0 w-6 h-6 rounded-full ${meta.bg} flex items-center justify-center">
                <span class="material-symbols-outlined text-[14px] ${meta.tone}">${meta.icon}</span>
              </div>
              <div class="flex flex-col gap-1">
                <div class="flex justify-between items-baseline gap-3">
                  <span class="font-telemetry-label text-telemetry-label ${meta.tone} uppercase">${escapeHtml(eventTitle(event))}</span>
                  <span class="font-telemetry-data text-telemetry-data text-on-surface-variant opacity-50">${escapeHtml(formatTime(eventRecord.ts_unix))}</span>
                </div>
                <p class="text-body-md text-on-surface-variant text-sm">${escapeHtml(detail)}</p>
                <div class="mt-2 p-2 bg-surface-container-lowest rounded font-telemetry-data text-[12px] text-on-surface-variant/70 border border-outline-variant/10">
                  source: ${escapeHtml(kind)} | device: ${escapeHtml(publicDeviceCode(devices.find((device) => device.device_id === eventRecord.device_id), index))} | safety: ${escapeHtml(motionAllowed ? "M33 candidate" : "read-only")}
                </div>
              </div>
            </div>
          `;
        }).join("");
        stream.querySelectorAll<HTMLElement>("[data-codex-log-index]").forEach((row) => {
          row.addEventListener("click", (event) => {
            event.preventDefault();
            const index = Number(row.dataset.codexLogIndex || 0);
            if (packet) packet.textContent = packetForEvent(eventsForLogs[index]);
            stream.querySelectorAll<HTMLElement>("[data-codex-log-index]").forEach((item) => item.classList.remove("bg-surface-variant/20"));
            row.classList.add("bg-surface-variant/20");
          });
        });
      }
      const activeFilterClass = "px-3 py-1 text-label-sm font-label-sm bg-secondary-container/20 text-secondary-fixed-dim border border-secondary-fixed-dim/30 rounded-full";
      const idleFilterClass = "px-3 py-1 text-label-sm font-label-sm hover:bg-surface-variant text-on-surface-variant rounded-full";
      doc.querySelectorAll<HTMLButtonElement>('[data-role="logs-filter"]').forEach((button) => {
        if (button.dataset.codexBound !== "true") {
          button.dataset.codexBound = "true";
          button.addEventListener("click", (event) => {
            event.preventDefault();
            const filter = button.dataset.filter || "all";
            doc.querySelectorAll<HTMLButtonElement>('[data-role="logs-filter"]').forEach((item) => {
              item.className = item === button ? activeFilterClass : idleFilterClass;
            });
            stream?.querySelectorAll<HTMLElement>("[data-codex-log-index]").forEach((row) => {
              const category = row.dataset.codexLogCategory || "all";
              row.style.display = filter === "all" || category === filter ? "" : "none";
            });
          });
        }
      });
      if (keyframes) {
        const frames = [
          { label: "左目视觉", src: leftStereoImageSrc || absoluteImageUrl, time: formatTime(selected?.last_upload_ts_unix), note: stereoTargetLabel || "等待目标" },
          { label: "右目视觉", src: rightStereoImageSrc, time: formatTime(selected?.last_upload_ts_unix), note: stereoEndEffectorLabel || "等待末端" },
          { label: "动作规划", src: "", time: dryRunGateLabel(dryRunGateState), note: visualServoDistanceText },
          { label: "安全审计", src: "", time: stateText(currentSafetyState), note: motionAllowed ? "M33 候选" : "只读锁定" },
        ];
        keyframes.innerHTML = frames.map((frame, index) => `
          <div class="group relative cursor-pointer border border-outline-variant/20 hover:border-secondary-fixed-dim/50 transition-all bg-surface-container-lowest min-h-[108px] overflow-hidden">
            ${frame.src
              ? `<img class="aspect-video object-cover w-full opacity-70 group-hover:opacity-100" src="${escapeHtml(frame.src)}" alt="${escapeHtml(frame.label)}"/>`
              : `<div class="aspect-video w-full grid place-items-center bg-surface-container-low text-center px-3"><span class="font-telemetry-label text-[11px] text-on-surface-variant">${escapeHtml(frame.note)}</span></div>`}
            <div class="absolute bottom-0 left-0 right-0 bg-black/60 p-1">
              <span class="font-telemetry-data text-[10px] text-on-surface">${escapeHtml(frame.label)} · ${escapeHtml(frame.time || `T-${index}`)}</span>
            </div>
          </div>
        `).join("");
      }
      if (packet) {
        packet.textContent = packetForEvent(eventsForLogs[0]);
      }
      bindLogsButton('[data-role="logs-refresh"]', (button) => {
        const original = button.textContent || "刷新";
        button.textContent = "刷新中...";
        void refreshLiveDashboard(false).finally(() => {
          button.textContent = "已刷新";
          window.setTimeout(() => {
            button.textContent = original;
          }, 1200);
        });
      });
      bindLogsButton('[data-role="logs-export"]', (button) => {
        const blob = new Blob([JSON.stringify(logsEvidenceSnapshot(), null, 2)], { type: "application/json;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = doc.createElement("a");
        link.href = url;
        link.download = `rehab-arm-logs-evidence-${projectId}-${Date.now()}.json`;
        link.click();
        URL.revokeObjectURL(url);
        const original = button.textContent || "导出";
        button.textContent = "已导出";
        window.setTimeout(() => {
          button.textContent = original;
        }, 1200);
      });
      bindLogsButton('[data-role="logs-copy-packet"]', (button) => {
        const value = packet?.textContent || JSON.stringify(logsEvidenceSnapshot(), null, 2);
        void copyTextToClipboard(value).then((copied) => {
          if (!copied) return;
          const original = button.innerHTML;
          button.innerHTML = '<span class="material-symbols-outlined text-[18px]">done</span>';
          window.setTimeout(() => {
            button.innerHTML = original;
          }, 1200);
        });
      });
      bindLogsButton('[data-role="logs-open-vision"]', () => {
        setActiveModule("vision");
      });
      bindLogsButton('[data-role="logs-open-ai"]', () => {
        setActiveModule("ai_model");
      });
      bindLogsButton('[data-role="logs-open-diagnostics"]', () => {
        setActiveModule("diagnostics");
      });
      replaceExactText([
        ["Event Audit Stream", "证据审计流"],
        ["Key Frame Replay", "关键帧回放"],
        ["Raw Packet Details", "原始数据包"],
        ["Control Console", "VLA 控制台"],
        ["Manual Mode", "只读总控"],
        ["Safety: Secured", "安全：M33 锁定"],
        ["Dry Run", "Dry-run"],
        ["Emergency Stop", "急停"],
        ["All", "全部"],
        ["Errors", "异常"],
        ["Safety", "安全"],
        ["Commands", "指令"],
        ["Refresh", "刷新"],
        ["Export", "导出"],
        ["© 2024 Industrial Robotics. Safety Protocol v4.2 Active.", "VLA Rehab Arm · 证据审计 / 只读回放 / M33 最终裁决"],
        ["Safety Manual", "安全手册"],
        ["System Status", "系统状态"],
      ]);
    }

    const logRows = doc.querySelectorAll<HTMLElement>("#logs .flex.gap-4");
    liveDashboard.recent_events.slice(0, 7).forEach((event, index) => {
      const row = logRows[index];
      if (!row) return;
      const spans = row.querySelectorAll<HTMLElement>("span");
      if (spans[0]) spans[0].textContent = `[${formatTime(event.ts_unix)}]`;
      if (spans[1]) spans[1].textContent = `${text(event.record_type, "event")}: ${eventTitle(event)}`;
    });
    syncCodexNav();
  }, [
    absoluteImageUrl,
    activeModule,
    cameraToRobotReady,
    clampedRenderCount,
    currentSafetyState,
    currentSemanticMode,
    devices,
    downloadDiagnosticsSnapshot,
    dryRunGateReason,
    dryRunGateState,
    dryRunCandidateAllowed,
    effectiveLanguageSummary,
    hasLanguageTask,
    hasStereoTargetForGate,
    ikApproachInput,
    ikCandidate,
    ikCandidateError,
    ikCandidateState,
    ikOrientationInput,
    ikSourceInput,
    ikTargetInput,
    leftStereoImageSrc,
    languageGate,
    liveDashboard.safety_boundary.m33_final_authority,
    liveDashboard.recent_events,
    exportIkCandidateEvidence,
    generateIkCandidate,
    createRelayInvokeToken,
    modelRelayProvider.external_call_ok,
    modelRelayEvents,
    modelRelayResponse,
    modelRelaySemantic.mode,
    modelRelaySuggestion.detail,
    motionAllowed,
    motors,
    operationMode,
    pixelServo.nextStep,
    pollState,
    poseSamples,
    projectId,
    qualityReady,
    recentEndEffectorMemory?.label,
    recentTargetMemory?.label,
    routeConfidence,
    routeConfidenceText,
    routeSourceText,
    relayBoundaryText,
    relayConfig.api_key_configured,
    relayConfig.base_url,
    relayConfig.external_enabled,
    relayConfig.model,
    relayConfig.provider,
    relayConfig.presets,
    relayConfigState,
    relayExportError,
    relayExportExpiresAt,
    relayExportState,
    relayExportToken,
    relayInvokeUrl,
    relayPrompt,
    relayProviderPreset?.label,
    relayState,
    requestModelRelay,
    refreshLiveDashboard,
    renderRows,
    rightStereoImageSrc,
    saveRelayConfig,
    selected,
    selectedIndex,
    selectedDeviceId,
    semanticModeLabel,
    semanticSourceLabel,
    semanticTargetLabel,
    sensorPayload,
    simulationReady,
    simulationPlanState,
    simulationReportBoundary,
    staleRenderCount,
    stereoEndEffectorLabel,
    stereoEndEffector.confidence,
    stereoEndEffector.probability,
    stereoEndEffector.score,
    stereoFrameSize,
    stereoFrameProcessMs,
    stereoHasFrameTiming,
    stereoHasDisparity,
    stereoHasContext,
    stereoLoopProgressText,
    stereoDisparity,
    stereoDepth,
    stereoTarget.confidence,
    stereoTarget.probability,
    stereoTarget.score,
    stereoTargetLabel,
    stereoTargetQualityGateState,
    targetQualityGateTitle,
    twinImportRequest,
    twinRuntimeHost,
    endEffectorEvidenceText,
    visualLockConfidenceText,
    visualServoDelta,
    visualServoDistancePx,
    visualLockObservedFrames,
    visualLockRequiredFrames,
    visualEvidenceImageSource,
    visualServoStateText,
    visualServoDistanceText,
    visualServoReady,
    wiringBadCount,
    wiringHealth.overall,
    xiaozhiReplyPayload,
    xiaozhiSession,
    xiaozhiWsUrl,
    updateRelayProvider,
  ]);

  useEffect(() => {
    updateStitchFrame();
  }, [updateStitchFrame]);

  return (
    <main className={styles.stitchMcpExactShell}>
      <iframe
        ref={stitchFrameRef}
        title="Stitch VLA 控制台原稿"
        src={stitchSourceByModule[activeModule]}
        className={styles.stitchMcpExactFrame}
        onLoad={() => {
          updateStitchFrame();
          window.setTimeout(updateStitchFrame, 200);
        }}
      />
      {activeModule === "digital_twin" && twinRuntimeHost ? createPortal(
        <div className={styles.stitchTwinStageOverlay} data-embedded="true" aria-label="真实 Three.js URDF 嵌入舞台">
          <Arm3DOverview
            deviceId={text(selected?.device_id, "")}
            robotId={text(selected?.robot_id, "")}
            projectId={projectId}
            deviceModel={record(selected?.device_model)}
            motors={poseSamples}
            robotRenderState={robotRenderState}
            wiringChecks={wiringChecks}
            safetyState={stateLabel(currentSafetyState)}
            stageMode
            externalUrdfFile={twinImportRequest?.file ?? null}
            externalUrdfFileNonce={twinImportRequest?.nonce ?? null}
          />
          <div className={styles.stitchTwinHudReplica} aria-label="数字孪生浮层信息">
            <section data-slot="joints">
              <header>
                <span>Joint Angles</span>
                <strong>{renderRows.length ? `${Math.max(0, renderRows.length - staleRenderCount)}/${renderRows.length} 新鲜` : "等待关节"}</strong>
              </header>
              <div>
                {poseSamples.slice(0, 6).map((sample, index) => (
                  <p key={`${text(record(sample).joint_name ?? record(sample).motor_id, `joint_${index + 1}`)}-${index}`}>
                    <span>{text(record(sample).joint_name ?? record(sample).motor_id, `J${index + 1}`)}</span>
                    <b>{numberText(firstFiniteNumber(record(sample).value, record(sample).position_rad, record(sample).position, record(sample).angle_deg), record(sample).position_rad !== undefined ? " rad" : " deg")}</b>
                  </p>
                ))}
                {!poseSamples.length ? <p><span>robot_render_state</span><b>waiting</b></p> : null}
              </div>
            </section>
            <section data-slot="bridge">
              <header>
                <span>ROS / MuJoCo</span>
                <strong>{simulationReady ? "Shadow Ready" : "Read Only"}</strong>
              </header>
              <p><span>渲染源</span><b>{renderRows.length ? "robot_render_state_v1" : "等待上报"}</b></p>
              <p><span>安全边界</span><b>{motionAllowed ? "M33 候选开放" : "只读 / dry-run"}</b></p>
            </section>
            <section data-slot="pose">
              <header>
                <span>End-Effector Pose</span>
                <strong>{recentEndEffectorMemory?.label ?? "等待末端"}</strong>
              </header>
              <p><span>视觉目标</span><b>{recentTargetMemory?.label ?? "等待目标"}</b></p>
              <p><span>动作门控</span><b>{dryRunGateLabel(dryRunGateState)}</b></p>
            </section>
            <section data-slot="target">
              <header>
                <span>Target Pose</span>
                <strong>{cameraToRobotReady ? "坐标可展示" : "等待标定"}</strong>
              </header>
              <p><span>VLA-A</span><b>{vlaLiteLoopLabel(vlaLiteLoopState)}</b></p>
              <p><span>权限</span><b>不授权真实运动</b></p>
            </section>
          </div>
        </div>,
        twinRuntimeHost,
      ) : null}
    </main>
  );
  const activeModuleMeta = REHAB_WORKSPACE_MODULES.find((item) => item.key === activeModule) ?? REHAB_WORKSPACE_MODULES[0];
  const staticPageTitle: Record<RehabWorkspaceModule, { eyebrow: string; title: string; detail: string }> = {
    overview: { eyebrow: "总控首页", title: "VLA 康复机械臂总控台", detail: "总览系统状态、模式、安全边界和演示主线。" },
    vision: { eyebrow: "VLA 视觉感知", title: "双目视觉主舞台", detail: "左/右摄像头、目标识别、末端识别和视觉锁定。" },
    digital_twin: { eyebrow: "数字孪生", title: "URDF / MuJoCo 机械臂舞台", detail: "机械臂模型、关节状态、末端位姿和仿真证据。" },
    muscle_assist: { eyebrow: "肌电助力", title: "上肢肌肉与 EMG 意图", detail: "四路肌电、动作意图、置信度和助力方向。" },
    ai_model: { eyebrow: "AI模型中转", title: "模型中转内联控制台", detail: "高层康复建议、供应商配置、受限调用令牌和安全审计。" },
    mode_router: { eyebrow: "模式编排", title: "小智语义模式路由", detail: "聊天、取物、训练、助力、仿真、诊断和安全停止。" },
    training: { eyebrow: "模型训练场", title: "数据、标注、训练计划预备区", detail: "数据集、标注、训练、评估、部署和训练计划。" },
    data_hub: { eyebrow: "数据资产", title: "采集、标注与训练回流", detail: "双目关键帧、L 指令、末端/目标标签、EMG 和仿真日志的数据资产入口。" },
    action_planner: { eyebrow: "动作规划", title: "VLA-A 闭环动作规划", detail: "目标、末端、差值、逼近策略、dry-run 和安全门。" },
    diagnostics: { eyebrow: "设备诊断", title: "NanoPi / CAN / M33 / M55 诊断", detail: "硬件在线状态、总线、电机、服务和模型中转。" },
    logs: { eyebrow: "日志回放", title: "证据时间线与回放", detail: "语音、视觉、规划、训练、部署和安全审计日志。" },
  };
  const activeStaticPage = staticPageTitle[activeModule];
  const modelRelayWorkbench = (
    <section className={`${styles.relayPanel} ${styles.aiModelWorkbench}`} data-state={relayState} aria-label="AI模型中转内联控制台">
      <div className={styles.panelMiniHeader}>
        <span>AI模型中转</span>
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
        <article>
          <span>安全边界</span>
          <strong>L / VLA / M33</strong>
          <p>只读建议与 dry-run 候选</p>
        </article>
      </div>
      <div className={styles.boundaryNote}>
        <strong>{relayBoundaryText}</strong>
        <p>{modelRelayProvider.external_call_ok === true ? "外部模型调用通过安全过滤" : text(modelRelayProvider.external_call_error, "未调用外部模型或安全降级")}</p>
      </div>
      <div className={styles.aiModelRelayGrid}>
        <details className={styles.relayConfigPanel} open>
          <summary>
            高层建议 / Dry-run
            <small>{relayState === "ok" ? "最近调用成功" : "不会下发真机运动"}</small>
          </summary>
          <textarea
            value={relayPrompt}
            onChange={(event) => setRelayPrompt(event.target.value)}
            rows={5}
            placeholder="输入语音/视觉/肌电摘要后的高层问题；服务端只返回建议和 dry-run 候选。"
            aria-label="模型中转提示"
          />
          <button type="button" disabled={!selected || relayState === "sending"} onClick={() => void requestModelRelay()}>
            {relayState === "sending" ? "生成中" : "生成高层建议"}
          </button>
          {relayError ? <small className={styles.inlineError}>{relayError}</small> : null}
          {modelRelaySuggestion.detail || modelRelayResponse.summary ? (
            <small className={styles.relayResult}>{text(modelRelaySuggestion.detail, text(modelRelayResponse.summary, ""))}</small>
          ) : null}
        </details>
        <details className={styles.relayConfigPanel} open>
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
          <button type="button" disabled={relayConfigState === "saving"} onClick={() => void saveRelayConfig()}>
            {relayConfigState === "saving" ? "保存中" : "保存厂商配置"}
          </button>
          {relayConfigState === "saved" ? <small className={styles.relayResult}>已保存到服务器环境配置；API key 不会返回给网页或设备。</small> : null}
          {relayConfigError ? <small className={styles.inlineError}>{relayConfigError}</small> : null}
        </details>
        <details className={styles.relayConfigPanel} open>
          <summary>
            接入地址和受限令牌
            <small>{relayExportToken ? "已生成" : "HTTP / XiaoZhi WS"}</small>
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
          <p className={styles.tokenHint}>给 NanoPi、M55 或另一个 AI 使用的受限令牌；scope 只包含模型中转 invoke 和 XiaoZhi WebSocket，不是网页登录 token。</p>
          <label>
            <span>有效期</span>
            <select value={relayTokenTtlSeconds} onChange={(event) => setRelayTokenTtlSeconds(Number(event.target.value) || 7 * 24 * 60 * 60)}>
              <option value={3600}>1 小时</option>
              <option value={24 * 60 * 60}>1 天</option>
              <option value={7 * 24 * 60 * 60}>7 天</option>
              <option value={30 * 24 * 60 * 60}>30 天</option>
            </select>
          </label>
          <button type="button" disabled={!selected || relayExportState === "creating"} onClick={() => void createRelayInvokeToken()}>
            {relayExportState === "creating" ? "生成中" : "一键生成调用令牌"}
          </button>
          {relayExportToken ? (
            <div className={styles.tokenBox}>
              <label>
                <span>Bearer token</span>
                <textarea readOnly value={relayExportToken} rows={3} aria-label="模型中转调用令牌" />
              </label>
              <button type="button" onClick={copyRelayInvokeToken}>{relayExportState === "copied" ? "已复制" : "复制 token"}</button>
              <small>过期：{relayExportExpiresAt ? formatTime(relayExportExpiresAt) : "未知"}</small>
            </div>
          ) : null}
          {relayExportError ? <small className={styles.inlineError}>{relayExportError}</small> : null}
          <pre className={styles.codeExample}>{relayCurlExample}</pre>
        </details>
        <details className={styles.relayConfigPanel} open>
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
                    <span>{text(event.record_type, "") === "model_relay_response" ? "平台 -> 设备" : "设备 -> 平台"}</span>
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
      </div>
    </section>
  );
  return (
    <main className={styles.stitchStaticShell}>
      <header className={styles.stitchStaticTopbar}>
        <strong>VLA 控制台</strong>
        <nav aria-label="顶部页面切换">
          {[
            ["vision", "VLA 视觉"],
            ["digital_twin", "数字孪生"],
            ["muscle_assist", "肌电助力"],
            ["ai_model", "AI模型"],
            ["mode_router", "模式编排"],
            ["training", "模型训练场"],
            ["action_planner", "动作规划"],
            ["diagnostics", "设备诊断"],
            ["logs", "日志"],
          ].map(([key, label]) => (
            <button key={key} type="button" data-active={activeModule === key ? "true" : "false"} onClick={() => setActiveModule(key as RehabWorkspaceModule)}>
              {label}
            </button>
          ))}
        </nav>
        <button type="button">ARM SYSTEM</button>
      </header>

      <aside className={styles.stitchStaticRail} aria-label="左侧页面切换">
        {[
          ["CMD", "总控", "overview"],
          ["V", "视觉", "vision"],
          ["3D", "孪生", "digital_twin"],
          ["EMG", "肌电", "muscle_assist"],
          ["AI", "模型", "ai_model"],
          ["L", "模式", "mode_router"],
          ["TRN", "训练", "training"],
          ["A", "动作", "action_planner"],
          ["IO", "诊断", "diagnostics"],
          ["LOG", "日志", "logs"],
        ].map(([short, label, key]) => (
          <button key={key} type="button" data-active={activeModule === key ? "true" : "false"} onClick={() => setActiveModule(key as RehabWorkspaceModule)}>
            <strong>{short}</strong>
            <span>{label}</span>
          </button>
        ))}
        <button type="button" data-kind="stop">急停</button>
      </aside>

      <section className={styles.stitchStaticStage}>
        <div className={styles.stitchStaticStageHead}>
          <span>{activeStaticPage.eyebrow}</span>
          <h1>{activeStaticPage.title}</h1>
          <p>{activeStaticPage.detail}</p>
        </div>

        {activeModule === "vision" ? (
          <div className={styles.stitchStaticVision}>
            <figure><figcaption>左摄像头视觉</figcaption><div /></figure>
            <figure><figcaption>右摄像头视觉</figcaption><div /></figure>
            <aside><span>目标向量</span><strong>[0.12, 0.85, 0.44]</strong><small>距离 1.42m · 置信度 98.2%</small></aside>
          </div>
        ) : activeModule === "digital_twin" ? (
          <div className={styles.stitchStaticTwin}>
            <div className={styles.stitchStaticRobot}>URDF / MuJoCo 3D 舞台</div>
            <div className={styles.stitchStaticTelemetry}>{["J1 基座", "J2 肩部", "J3 肘部", "J4 腕部", "末端位姿"].map((item) => <article key={item}><span>{item}</span><strong>待接入</strong></article>)}</div>
          </div>
        ) : activeModule === "muscle_assist" ? (
          <div className={styles.stitchStaticMuscle}>
            <div className={styles.stitchStaticArm}>上肢肌肉 GLB 舞台</div>
            <div className={styles.stitchStaticTelemetry}>{["肱二头肌", "三角肌", "前臂屈肌", "斜方肌"].map((item) => <article key={item}><span>{item}</span><strong>0%</strong></article>)}</div>
          </div>
        ) : activeModule === "ai_model" ? (
          <div className={styles.stitchStaticAiModel}>
            {modelRelayWorkbench}
          </div>
        ) : (
          <div className={styles.stitchStaticTiles}>
            {["输入", "解析", "证据", "计划", "审核", "输出"].map((item, index) => (
              <article key={item} data-hot={index === 2 ? "true" : "false"}>
                <span>{item}</span>
                <strong>{index === 2 ? "主舞台" : "待接入"}</strong>
                <p>这是 Stitch 原型风格的静态槽位，确认后再把真实功能搬进来。</p>
              </article>
            ))}
          </div>
        )}
      </section>

      <footer className={styles.stitchStaticFooter}>
        <span>安全门：已锁定</span>
        <span>只读 / dry-run / M33 final authority</span>
      </footer>
    </main>
  );
  return (
    <main className={styles.stitchOnlyShell} data-active-module={activeModule}>
      <header className={styles.stitchOnlyTopbar}>
        <div className={styles.stitchOnlyBrand}>
          <strong>VLA 控制台</strong>
          <span>{publicDeviceName(selected, selectedIndex)} · {stateText(currentSafetyState)} · {motionAllowed ? "M33 候选开放" : "只读锁定"}</span>
        </div>
        <nav aria-label="功能页面切换">
          {[
            ["vision", "VLA 视觉"],
            ["digital_twin", "数字孪生"],
            ["muscle_assist", "肌电助力"],
            ["ai_model", "AI模型"],
            ["mode_router", "模式编排"],
            ["training", "模型训练场"],
            ["action_planner", "动作规划"],
            ["diagnostics", "设备诊断"],
            ["logs", "日志"],
          ].map(([key, label]) => (
            <button key={key} type="button" data-active={activeModule === key ? "true" : "false"} onClick={() => setActiveModule(key as RehabWorkspaceModule)}>
              {label}
            </button>
          ))}
        </nav>
        <button type="button" className={styles.stitchOnlyArmState}>ARM SYSTEM</button>
      </header>

      <div className={styles.stitchOnlyBody}>
        <aside className={styles.stitchOnlyRail} aria-label="左侧功能栏">
          {[
            ["CMD", "总控", "overview"],
            ["V", "视觉", "vision"],
            ["3D", "孪生", "digital_twin"],
            ["EMG", "肌电", "muscle_assist"],
            ["AI", "模型", "ai_model"],
            ["L", "模式", "mode_router"],
            ["TRN", "训练", "training"],
            ["A", "动作", "action_planner"],
            ["IO", "诊断", "diagnostics"],
            ["LOG", "日志", "logs"],
          ].map(([short, label, key]) => (
            <button key={key} type="button" data-active={activeModule === key ? "true" : "false"} onClick={() => setActiveModule(key as RehabWorkspaceModule)}>
              <strong>{short}</strong>
              <span>{label}</span>
            </button>
          ))}
          <button type="button" className={styles.stitchOnlyStop}>急停</button>
        </aside>

        <section className={styles.stitchOnlyStage}>
          {activeModule === "overview" ? (
            <div className={styles.stitchOnlyOverview}>
              <div className={styles.stitchOnlyHero}>
                <span>总控首页</span>
                <h1>{operationModeLabel(operationMode)} / {dryRunGateLabel(dryRunGateState)}</h1>
                <p>{effectiveLanguageSummary || dryRunGateReason}</p>
              </div>
              <div className={styles.stitchOnlyTiles}>
                {topologyNodes.map((node) => (
                  <article key={node.key} data-tone={node.tone}>
                    <span>{node.eyebrow}</span>
                    <strong>{node.value}</strong>
                    <p>{node.title} · {node.detail}</p>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {activeModule === "vision" ? (
            <div className={styles.stitchOnlyVision}>
              <figure>
                <figcaption>左摄像头 · {leftStereoImageSrc ? "后端标注帧" : absoluteImageUrl ? "关键帧" : "等待画面"}</figcaption>
                {leftStereoImageSrc || absoluteImageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={leftStereoImageSrc || absoluteImageUrl} alt="左目摄像头图像" />
                ) : <div>等待左目画面</div>}
              </figure>
              <figure>
                <figcaption>右摄像头 · {rightStereoImageSrc ? "双目辅助帧" : "等待画面"}</figcaption>
                {rightStereoImageSrc ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={rightStereoImageSrc} alt="右目摄像头图像" />
                ) : <div>等待右目画面</div>}
              </figure>
              <aside>
                <span>目标向量</span>
                <strong>{visualServoDistanceText}</strong>
                <p>目标：{recentTargetMemory?.label ?? "等待目标"}；末端：{recentEndEffectorMemory?.label ?? "等待末端"}；锁定 {visualLockObservedFrames}/{visualLockRequiredFrames}</p>
              </aside>
            </div>
          ) : null}

          {activeModule === "digital_twin" ? (
            <div className={styles.stitchOnlyEmbeddedStage}>
              <div className={styles.stitchOnlyHero}>
                <span>数字孪生</span>
                <h1>URDF / MuJoCo / 关节遥测</h1>
                <p>把现有 URDF 导入、姿态映射、关节状态和全屏 HUD 嵌入新页面舞台。</p>
              </div>
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
            </div>
          ) : null}

          {activeModule === "muscle_assist" ? (
            <div className={styles.stitchOnlyEmbeddedStage}>
              <div className={styles.stitchOnlyHero}>
                <span>肌电助力</span>
                <h1>上肢肌肉 / EMG / 动作意图</h1>
                <p>把现有上肢 GLB、四路肌电、动作预测和助力方向嵌入新页面舞台。</p>
              </div>
              <HumanMuscleOverview sensorPayload={sensorPayload} />
            </div>
          ) : null}

          {activeModule === "ai_model" ? (
            <div className={styles.stitchOnlyEmbeddedStage}>
              <div className={styles.stitchOnlyHero}>
                <span>AI模型中转</span>
                <h1>模型中转内联控制台</h1>
                <p>按 Stitch 生成的 AI 模型工作台结构，把高层建议、供应商配置、受限令牌和安全审计留在同一页，不跳转实验室。</p>
              </div>
              {modelRelayWorkbench}
            </div>
          ) : null}

          {activeModule === "mode_router" ? (
            <div className={styles.stitchOnlyOverview}>
              <div className={styles.stitchOnlyHero}>
                <span>模式编排</span>
                <h1>{currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待 L 分类"}</h1>
                <p>小智 L 链路保持原样；平台只消费语义分类并展示资源路由。</p>
              </div>
              <div className={styles.stitchOnlyTiles}>
                {displayModeOverviewRows.map((item) => (
                  <article key={item.mode} data-tone={currentSemanticMode === item.mode ? "ok" : item.tone}>
                    <span>{semanticActionModeLabel(item.mode)}</span>
                    <strong>{item.title}</strong>
                    <p>{item.detail} · {item.stage} · {item.next}</p>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {activeModule === "training" ? (
            <div className={styles.stitchOnlyOverview}>
              <div className={styles.stitchOnlyHero}>
                <span>模型训练场</span>
                <h1>数据、标注、训练计划预备区</h1>
                <p>视觉数据集、目标/末端标注、动作意图样本、APP 训练库、M55 推理摘要和 AI 训练计划统一进入这里。</p>
              </div>
              <div className={styles.stitchOnlyTiles}>
                <article data-tone={qualityReady ? "ok" : "limited"}>
                  <span>数据入口</span>
                  <strong>{qualityReady ? "可进入标注/训练" : "等待数据质量达标"}</strong>
                  <p>摄像头帧、YOLO 标签、末端/夹爪标签、肌电窗口和动作意图样本。</p>
                </article>
                <article data-tone="ok">
                  <span>现有工具</span>
                  <strong>AI模型中转 / 数据工作台</strong>
                  <p><button type="button" onClick={() => setActiveModule("ai_model")}>打开 AI 模型</button> · <Link href={`/projects/${projectId}/robotics?tab=dataset&device=${encodeURIComponent(selected?.device_id ?? "")}`} prefetch={false}>打开数据/标注</Link></p>
                </article>
                {trainingPipelineSteps.map((step) => (
                  <article key={step.key} data-tone={step.tone}>
                    <span>{step.label}</span>
                    <strong>{step.state}</strong>
                    <p>APP / M33 BLE / M55 / AI 训练计划预留链路</p>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {activeModule === "action_planner" ? (
            <div className={styles.stitchOnlyOverview}>
              <div className={styles.stitchOnlyHero}>
                <span>动作规划</span>
                <h1>{dryRunGateLabel(dryRunGateState)}</h1>
                <p>{dryRunGateReason}</p>
              </div>
              <div className={styles.stitchOnlyTiles}>
                {vlaEvidenceLadder.map((item) => (
                  <article key={item.step} data-tone={item.tone}>
                    <span>{item.step}</span>
                    <strong>{item.title}</strong>
                    <p>{item.state} · {item.detail}</p>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {activeModule === "diagnostics" ? (
            <div className={styles.stitchOnlyOverview}>
              <div className={styles.stitchOnlyHero}>
                <span>设备诊断</span>
                <h1>NanoPi / CAN / M33 / 模型中转</h1>
                <p>诊断页展示真实设备状态、模型中转、令牌、电机表和事件，不提供真实运动写入。</p>
              </div>
              <div className={styles.stitchOnlyTiles}>
                {roleCards.map((role) => (
                  <article key={role.key} data-tone={role.ready ? "ok" : "limited"}>
                    <span>{role.title}</span>
                    <strong>{role.value}</strong>
                    <p>{role.subtitle} · {role.detail}</p>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {activeModule === "logs" ? (
            <div className={styles.stitchOnlyOverview}>
              <div className={styles.stitchOnlyHero}>
                <span>日志 / 回放</span>
                <h1>证据时间线</h1>
                <p>语音、模式分类、视觉帧、规划、模型中转和设备上传都走同一条证据时间线。</p>
              </div>
              <div className={styles.stitchOnlyLogList}>
                {liveDashboard.recent_events.slice(0, 10).map((event, index) => (
                  <article key={`${text(event.record_type, "event")}-${index}`}>
                    <span>{formatTime(event.ts_unix)}</span>
                    <strong>{eventTitle(event)}</strong>
                    <p>{publicDeviceCode(devices.find((device) => device.device_id === event.device_id), index)} · {text(event.record_type, "event")}</p>
                  </article>
                ))}
                {!liveDashboard.recent_events.length ? <article><span>等待</span><strong>暂无上传事件</strong><p>NanoPi / M55 / 平台模型中转上报后会显示。</p></article> : null}
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
  return (
    <main className={styles.shell} data-active-module={activeModule}>
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          <div className={styles.controlRoomBrand} aria-hidden="true">V</div>
          <Link href={`/projects/${projectId}`} className={styles.backLink}>← 主页面</Link>
          <Link href={`/projects/${projectId}/robotics`} className={styles.backLink} prefetch={false}>设备数据工作台</Link>
          <button type="button" className={styles.backLink} onClick={() => setActiveModule("ai_model")}>AI模型</button>
          <div className={styles.title}>
            <strong>{projectName}</strong>
            <small>康复机械臂专项总控 · 只读状态 / 安全边界 / 数据质量</small>
          </div>
        </div>
        <div className={styles.topbarRight}>
          <nav className={styles.stageJumpNav} aria-label="VLA 主舞台跳转">
            <button type="button" data-active={activeModule === "overview"} onClick={() => setActiveModule("overview")}>总控</button>
            <button type="button" data-active={activeModule === "vision"} onClick={() => setActiveModule("vision")}>视觉</button>
            <button type="button" data-active={activeModule === "digital_twin"} onClick={() => setActiveModule("digital_twin")}>URDF</button>
            <button type="button" data-active={activeModule === "muscle_assist"} onClick={() => setActiveModule("muscle_assist")}>肌电</button>
            <button type="button" data-active={activeModule === "ai_model"} onClick={() => setActiveModule("ai_model")}>AI模型</button>
          </nav>
          <span className={styles.kpi}>设备 {devices.length}</span>
          <span className={styles.kpi}>在线 {roleSignals.onlineDevices}</span>
          <span className={styles.kpi}>M33 裁决 {liveDashboard.safety_boundary.m33_final_authority ? "开启" : "未声明"}</span>
          <span className={styles.kpi}>
            {pollState === "error"
              ? "自动刷新异常"
              : pollState === "syncing"
                ? "正在同步"
                : lastLiveUpdate
                  ? `自动刷新 ${formatClock(lastLiveUpdate)}`
                  : "准备同步"}
          </span>
          <button
            type="button"
            className={styles.refreshLink}
            onClick={() => void refreshLiveDashboard(false)}
            disabled={pollState === "syncing"}
          >
            {pollState === "syncing" ? "同步中" : "立即同步"}
          </button>
        </div>
      </header>

      <div className={styles.body}>
        <aside className={styles.sidebar}>
          <nav className={styles.moduleNav} aria-label="康复机械臂功能模块">
            <div className={styles.moduleNavHeader}>
              <span>WORKSPACES</span>
              <strong>{REHAB_WORKSPACE_MODULES.find((item) => item.key === activeModule)?.label ?? "总控首页"}</strong>
            </div>
            {REHAB_WORKSPACE_MODULES.map((item) => (
              <button
                key={item.key}
                type="button"
                className={styles.moduleNavItem}
                data-active={activeModule === item.key ? "true" : "false"}
                onClick={() => setActiveModule(item.key)}
              >
                <span>{item.short}</span>
                <strong>{item.label}</strong>
                <small>{item.description}</small>
              </button>
            ))}
          </nav>
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

          <section className={styles.stitchConsole} aria-label="Stitch VLA 康复机械臂功能控制台">
            <header className={styles.stitchHeader}>
              <div>
                <strong>VLA 控制台</strong>
                <span>{publicDeviceName(selected, selectedIndex)} · {stateText(currentSafetyState)} · {motionAllowed ? "motion candidate" : "read-only lock"}</span>
              </div>
              <nav aria-label="Stitch 主舞台">
                <button type="button" data-active={activeModule === "vision"} onClick={() => setActiveModule("vision")}>VLA 视觉感知</button>
                <button type="button" data-active={activeModule === "digital_twin"} onClick={() => setActiveModule("digital_twin")}>数字孪生</button>
                <button type="button" data-active={activeModule === "muscle_assist"} onClick={() => setActiveModule("muscle_assist")}>肌电助力</button>
                <button type="button" data-active={activeModule === "ai_model"} onClick={() => setActiveModule("ai_model")}>AI模型</button>
                <button type="button" data-active={activeModule === "mode_router"} onClick={() => setActiveModule("mode_router")}>模式编排</button>
                <button type="button" data-active={activeModule === "logs"} onClick={() => setActiveModule("logs")}>日志</button>
              </nav>
            </header>

            <div className={styles.stitchBody}>
              <aside className={styles.stitchRail} aria-label="Stitch 功能导航">
                {[
                  ["总", "总控", "overview"],
                  ["V", "视觉", "vision"],
                  ["3D", "孪生", "digital_twin"],
                  ["EMG", "肌电", "muscle_assist"],
                  ["AI", "模型", "ai_model"],
                  ["L", "模式", "mode_router"],
                  ["TRN", "训练场", "training"],
                  ["A", "动作", "action_planner"],
                  ["IO", "诊断", "diagnostics"],
                  ["LOG", "日志", "logs"],
                ].map(([short, label, moduleKey]) => (
                  <button
                    key={label}
                    type="button"
                    data-active={activeModule === moduleKey ? "true" : "false"}
                    onClick={() => setActiveModule(moduleKey as RehabWorkspaceModule)}
                  >
                    <span aria-hidden="true">{short}</span>
                    <small>{label}</small>
                  </button>
                ))}
                <button type="button" aria-label="只读急停状态展示">急停</button>
              </aside>

              <div className={styles.stitchStages}>
                {activeModule === "overview" ? (
                <section className={styles.stitchOverviewStage}>
                  <div className={styles.stitchStageTitle}>
                    <span>总控首页</span>
                    <strong>{operationModeLabel(operationMode)} / {dryRunGateLabel(dryRunGateState)}</strong>
                    <p>{effectiveLanguageSummary || dryRunGateReason}</p>
                  </div>
                  <div className={styles.stitchRouterMatrix}>
                    {topologyNodes.map((node) => (
                      <article key={node.key} data-active={node.tone === "ok" ? "true" : "false"}>
                        <span>{node.eyebrow}</span>
                        <strong>{node.value}</strong>
                        <p>{node.title} · {node.detail}</p>
                      </article>
                    ))}
                  </div>
                </section>
                ) : null}

                {activeModule === "vision" ? (
                <section className={styles.stitchVisionStage}>
                  <div className={styles.stitchFeed}>
                    <div className={styles.stitchScanline} />
                    <div className={styles.stitchHudLabel}>左摄像头 · {leftStereoImageSrc ? "后端标注帧" : absoluteImageUrl ? "关键帧" : "等待画面"}</div>
                    {leftStereoImageSrc || absoluteImageUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={leftStereoImageSrc || absoluteImageUrl} alt="左目或关键帧图像" />
                    ) : (
                      <div className={styles.stitchEmptyFeed}>等待左目画面</div>
                    )}
                    <div className={styles.stitchFeedTelemetry}>
                      <span>{visualEvidenceImageSource}</span>
                      <strong>{recentTargetMemory?.label ?? "target pending"}</strong>
                    </div>
                  </div>
                  <div className={styles.stitchFeed}>
                    <div className={styles.stitchScanline} />
                    <div className={styles.stitchHudLabel}>右摄像头 · {rightStereoImageSrc ? "双目辅助帧" : "等待画面"}</div>
                    {rightStereoImageSrc ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={rightStereoImageSrc} alt="右目摄像头图像" />
                    ) : (
                      <div className={styles.stitchEmptyFeed}>等待右目画面</div>
                    )}
                    <div className={styles.stitchVectorHud}>
                      <span>目标向量</span>
                      <strong>{visualServoDistanceText}</strong>
                      <small>{recentEndEffectorMemory?.label ?? "末端待识别"} · 锁定 {visualLockObservedFrames}/{visualLockRequiredFrames}</small>
                    </div>
                  </div>
                  <div className={styles.stitchPipelineHud}>
                    {[
                      ["psychology", "语义意图", routeLabel(routeClass), effectiveLanguageSummary],
                      ["alt_route", "模式识别", operationModeLabel(operationMode), routeClass],
                      ["ads_click", "视觉目标", recentTargetMemory?.label ?? "等待目标", visionSummary],
                      ["edit_note", "动作计划", dryRunGateLabel(dryRunGateState), dryRunGateReason],
                      ["terminal", "执行边界", motionAllowed ? "M33 候选" : "只读锁定", "不发 CAN / 不写力矩 / 不写角度"],
                    ].map(([icon, label, value, detail]) => (
                      <article key={label}>
                        <span className="material-symbols-outlined" aria-hidden="true">{icon}</span>
                        <strong>{label}</strong>
                        <small>{value}</small>
                        <p>{detail}</p>
                      </article>
                    ))}
                  </div>
                </section>
                ) : null}

                {activeModule === "digital_twin" ? (
                <section className={styles.stitchTwinStage}>
                  <div className={styles.stitchStageTitle}>
                    <span>数字孪生</span>
                    <strong>URDF / MuJoCo / 关节遥测</strong>
                    <p>现有 Three.js URDF 功能、导入、姿态映射和全屏 HUD 保留在下方真实组件中。</p>
                  </div>
                  <div className={styles.stitchTelemetryStack}>
                    {poseSamples.slice(0, 6).map((motor, index) => (
                      <article key={`${text(record(motor).motor_id, "motor")}-${index}`}>
                        <span>{text(record(motor).joint_name, text(record(motor).motor_id, `joint_${index + 1}`))}</span>
                        <strong>{numberText(record(motor).position ?? record(motor).position_rad ?? record(motor).angle, " rad")}</strong>
                        <small>{numberText(motorTemperature(record(motor)), " C")} · {record(motor).fault ? "故障" : "正常"}</small>
                      </article>
                    ))}
                    {!poseSamples.length ? <article><span>关节</span><strong>等待上报</strong><small>robot_render_state / motor_state 未上传</small></article> : null}
                  </div>
                  <a className={styles.stitchGhostButton} href="#urdf-stage">打开真实 URDF 组件</a>
                </section>
                ) : null}

                {activeModule === "muscle_assist" ? (
                <section className={styles.stitchMuscleStage}>
                  <div className={styles.stitchStageTitle}>
                    <span>肌电助力</span>
                    <strong>上肢肌电与动作意图</strong>
                    <p>真实上肢 GLB、四路 EMG、动作预测和全屏肌电组件保留在下方真实组件中。</p>
                  </div>
                  <div className={styles.stitchEmgGrid}>
                    {muscleRowsFromSensor(sensorPayload).slice(0, 4).map((row) => (
                      <article key={row.key} data-tone={row.status}>
                        <span>{row.label}</span>
                        <strong>{row.displayValue}</strong>
                        <em><i style={{ width: `${Math.round((row.value ?? 0) * 100)}%` }} /></em>
                        <small>疲劳 {row.fatigue === null ? "unknown" : `${Math.round(row.fatigue * 100)}%`} · {row.status}</small>
                      </article>
                    ))}
                  </div>
                  <div className={styles.stitchPredictionStrip}>
                    {motionPredictionRowsFromSensor(sensorPayload).slice(0, 3).map((row) => (
                      <article key={row.key}>
                        <span>{row.label}</span>
                        <strong>{row.value}</strong>
                        <small>{row.detail}</small>
                      </article>
                    ))}
                  </div>
                  <a className={styles.stitchGhostButton} href="#muscle-stage">打开真实肌电组件</a>
                </section>
                ) : null}

                {activeModule === "ai_model" ? (
                <section className={styles.stitchEmbeddedStage}>
                  <div className={styles.stitchStageTitle}>
                    <span>AI模型中转</span>
                    <strong>模型中转内联控制台</strong>
                    <p>按 Stitch AI 模型工作台结构，把高层建议、供应商配置、受限令牌和安全审计留在同一页，不跳转模型实验室。</p>
                  </div>
                  {modelRelayWorkbench}
                </section>
                ) : null}

                {activeModule === "mode_router" ? (
                <section className={styles.stitchRouterStage}>
                  <div className={styles.stitchStageTitle}>
                    <span>模式编排</span>
                    <strong>{currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待 L 分类"}</strong>
                    <p>小智 L 链路不在这里改，只消费平台已有语义结果并展示资源路由。</p>
                  </div>
                  <div className={styles.stitchRouterMatrix}>
                    {displayModeOverviewRows.map((item) => (
                      <article key={item.mode} data-active={currentSemanticMode === item.mode ? "true" : "false"}>
                        <span>{semanticActionModeLabel(item.mode)}</span>
                        <strong>{item.title}</strong>
                        <p>{item.detail}</p>
                        <small>{item.stage} · {item.next}</small>
                      </article>
                    ))}
                  </div>
                </section>
                ) : null}

                {activeModule === "training" ? (
                <section className={styles.stitchRouterStage}>
                  <div className={styles.stitchStageTitle}>
                    <span>模型训练场</span>
                    <strong>{currentSemanticMode === "training" ? "训练链路已被 L 选中" : "数据、标注、训练计划预备区"}</strong>
                    <p>这里承接视觉数据集、目标/末端标注、动作意图样本、APP 训练库、M55 推理摘要和 AI 训练计划。M33 后续通过 BLE 从 APP 调取训练库。</p>
                  </div>
                  <div className={styles.stitchTrainingHero}>
                    <article>
                      <span>数据入口</span>
                      <strong>{qualityReady ? "可进入标注/训练" : "等待数据质量达标"}</strong>
                      <p>摄像头帧、YOLO 标签、末端/夹爪标签、肌电窗口和动作意图样本最终进入统一训练资产。</p>
                    </article>
                    <article>
                      <span>现有工具</span>
                      <strong>AI模型中转 / 数据工作台</strong>
                      <p>模型中转已经内联到当前控制台；数据/标注继续进入数据工作台。</p>
                      <div className={styles.stitchActionLinks}>
                        <button type="button" onClick={() => setActiveModule("ai_model")}>打开 AI 模型</button>
                        <Link href={`/projects/${projectId}/robotics?tab=dataset&device=${encodeURIComponent(selected?.device_id ?? "")}`} prefetch={false}>打开数据/标注</Link>
                      </div>
                    </article>
                    <article>
                      <span>闭环预留</span>
                      <strong>APP → M33 BLE → M55 → AI 计划</strong>
                      <p>M55 推理动作意图，M33 汇总到 APP，APP 端 AI 生成训练计划并写入训练计划表。</p>
                    </article>
                  </div>
                  <div className={styles.stitchRouterMatrix}>
                    {trainingPipelineSteps.map((step) => (
                      <article key={step.key} data-active={step.tone === "ok" ? "true" : "false"}>
                        <span>{step.label}</span>
                        <strong>{step.state}</strong>
                        <p>APP / M33 BLE / M55 / AI 训练计划预留链路</p>
                      </article>
                    ))}
                  </div>
                </section>
                ) : null}

                {activeModule === "action_planner" ? (
                <section className={styles.stitchRouterStage}>
                  <div className={styles.stitchStageTitle}>
                    <span>动作规划</span>
                    <strong>{dryRunGateLabel(dryRunGateState)}</strong>
                    <p>{dryRunGateReason}</p>
                  </div>
                  <div className={styles.stitchRouterMatrix}>
                    {vlaEvidenceLadder.map((item) => (
                      <article key={item.step} data-active={item.tone === "ok" ? "true" : "false"}>
                        <span>{item.step}</span>
                        <strong>{item.title}</strong>
                        <p>{item.state} · {item.detail}</p>
                      </article>
                    ))}
                  </div>
                </section>
                ) : null}

                {activeModule === "diagnostics" ? (
                <section className={styles.stitchRouterStage}>
                  <div className={styles.stitchStageTitle}>
                    <span>设备诊断</span>
                    <strong>NanoPi / CAN / M33 / 模型中转</strong>
                    <p>诊断页展示真实设备状态、模型中转、令牌、电机表和事件，不提供真实运动写入。</p>
                  </div>
                  <div className={styles.stitchRouterMatrix}>
                    {roleCards.map((role) => (
                      <article key={role.key} data-active={role.ready ? "true" : "false"}>
                        <span>{role.title}</span>
                        <strong>{role.value}</strong>
                        <p>{role.subtitle} · {role.detail}</p>
                      </article>
                    ))}
                  </div>
                </section>
                ) : null}

                {activeModule === "logs" ? (
                <section className={styles.stitchLogsStage}>
                  <div className={styles.stitchStageTitle}>
                    <span>日志 / 回放</span>
                    <strong>证据时间线</strong>
                    <p>语音、模式分类、视觉帧、规划、模型中转和设备上传都走同一条证据时间线。</p>
                  </div>
                  <div className={styles.stitchLogStream}>
                    {liveDashboard.recent_events.slice(0, 8).map((event, index) => (
                      <article key={`${text(event.record_type, "event")}-${index}`}>
                        <span>{formatTime(event.ts_unix)}</span>
                        <strong>{eventTitle(event)}</strong>
                        <p>{publicDeviceCode(devices.find((device) => device.device_id === event.device_id), index)} · {text(event.record_type, "event")}</p>
                      </article>
                    ))}
                    {!liveDashboard.recent_events.length ? <article><span>等待</span><strong>暂无上传事件</strong><p>NanoPi / M55 / 平台模型中转上报后会显示。</p></article> : null}
                  </div>
                </section>
                ) : null}
              </div>
            </div>
          </section>

          <section className={styles.moduleHero} aria-label="当前工作台模块">
            <div>
              <span>{activeModuleMeta.short} Workspace</span>
              <strong>{activeModuleMeta.label}</strong>
              <p>{activeModuleMeta.description}。模块切换只改变前端工作台视图，底层设备同步、XiaoZhi/L、VLA 候选、URDF、肌电、模型中转和审计功能仍保留。</p>
            </div>
            <small>{selected ? publicDeviceCode(selected, selectedIndex) : "等待 NanoPi 设备"} · {pollState === "syncing" ? "同步中" : "read-only console"}</small>
          </section>

          <section id="vla-stage" data-module="overview vision action_planner" className={`${styles.controlRoomLiveStage} ${styles.stageAnchor}`} aria-label="VLA 生产控制室新首屏">
            <div className={styles.controlRoomMission}>
              <div>
                <span>Mission</span>
                <strong>{operationModeLabel(operationMode)} / {dryRunGateLabel(dryRunGateState)}</strong>
                <p>{effectiveLanguageSummary || dryRunGateReason}</p>
              </div>
              <small>只读 / dry-run / M33 final authority</small>
            </div>

            <div className={styles.controlRoomRail} aria-label="VLA 新流程轨">
              <article data-tone={stereoHasContext || absoluteImageUrl ? "ok" : "hold"}>
                <span>V · Stereo Vision</span>
                <strong>{stereoHasContext ? text(stereoTargetLabel, "双目已接入") : absoluteImageUrl ? "关键帧已接入" : "等待画面"}</strong>
                <p>{visionSummary}</p>
              </article>
              <article data-tone={languageGate.participates_in_vla_l === true ? "ok" : "hold"}>
                <span>L · XiaoZhi</span>
                <strong>{vlaGateLabel(languageGate)}</strong>
                <p>{effectiveLanguageSummary}</p>
              </article>
              <article data-tone={hasActionCandidate ? "ok" : "hold"}>
                <span>A · Planner</span>
                <strong>{text(actionCandidate.type, actionGateTitle)}</strong>
                <p>{hasActionCandidate ? actionSummary : actionGateSummary}</p>
              </article>
              <article data-tone={shadowEvidenceTone}>
                <span>Shadow · MuJoCo</span>
                <strong>{simulationReady ? "shadow 已跑通" : "等待 shadow"}</strong>
                <p>{simulationPlanState} · {simulationReportBoundary}</p>
              </article>
              <article data-tone={motionAllowed ? "ok" : "hold"}>
                <span>Safety · M33</span>
                <strong>{motionAllowed ? "允许候选" : "锁定真机"}</strong>
                <p>{text(safetyStatus.reason ?? safetyPayload.reason, "最终裁决只来自 M33。")}</p>
              </article>
            </div>

            <div className={styles.controlRoomStageGrid}>
              <article className={styles.controlRoomVisionStage} id="vision-stage-new">
                <div className={styles.controlRoomPanelHead}>
                  <div>
                    <span>V · Stereo Evidence</span>
                    <strong>{stereoTargetLabel ? `${stereoTargetLabel} · ${pixelServo.title}` : pixelServo.title}</strong>
                  </div>
                  <small>{visualEvidenceImageSource} / {visualEvidenceBoxSource}</small>
                </div>
                <div className={styles.controlRoomFeeds}>
                  <figure>
                    <figcaption><span>Left</span><strong>{leftStereoImageSrc ? "edge annotated frame" : "waiting evidence"}</strong></figcaption>
                    <div className={styles.controlRoomCamera}>
                      {leftStereoImageSrc ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={leftStereoImageSrc} alt="左目摄像头帧" />
                      ) : absoluteImageUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={absoluteImageUrl} alt="摄像头关键帧" />
                      ) : (
                        <span>WAITING FRAME</span>
                      )}
                    </div>
                  </figure>
                  <figure>
                    <figcaption><span>Right</span><strong>{rightStereoImageSrc ? "support frame" : "waiting right image"}</strong></figcaption>
                    <div className={styles.controlRoomCamera}>
                      {rightStereoImageSrc ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={rightStereoImageSrc} alt="右目摄像头帧" />
                      ) : (
                        <span>WAITING STEREO</span>
                      )}
                    </div>
                  </figure>
                </div>
                <div className={styles.controlRoomEvidenceStrip}>
                  <div><span>目标</span><strong>{recentTargetMemory?.label ?? "等待"}</strong></div>
                  <div><span>末端</span><strong>{recentEndEffectorMemory?.label ?? "等待"}</strong></div>
                  <div><span>锁定</span><strong>{visualLockObservedFrames}/{visualLockRequiredFrames}</strong></div>
                  <div><span>距离</span><strong>{visualServoDistanceText}</strong></div>
                </div>
              </article>

              <aside className={styles.controlRoomInspector}>
                <article data-tone={languageGate.participates_in_vla_l === true ? "ok" : "warn"}>
                  <span>L · 语义入口</span>
                  <strong>{routeLabel(routeClass)}</strong>
                  <p>{vlaGateLabel(languageGate)}；{text(xiaozhiSession.control_boundary ?? voiceRelay.control_boundary, "voice_only_not_motion_permission")}</p>
                </article>
                <article data-tone={dryRunGateTone}>
                  <span>A · dry-run gate</span>
                  <strong>{dryRunGateLabel(dryRunGateState)}</strong>
                  <p>{dryRunGateReason}</p>
                </article>
                <article data-tone={motionAllowed ? "ok" : "warn"}>
                  <span>Safety Gate</span>
                  <strong>{stateText(currentSafetyState)}</strong>
                  <p>M33 final authority；网页不发 CAN、电流、力矩、速度、角度。</p>
                </article>
              </aside>
            </div>
          </section>

          <section data-module="overview mode_router action_planner" className={`${styles.vlaCommandStrip} ${styles.legacyVlaStrip}`} aria-label="VLA 感知语言动作链路">
            <article data-stage="v">
              <span>V · 双目视觉</span>
              <strong>{stereoHasContext ? text(stereoTargetLabel, "双目已接入") : text(keyframePayload.camera_id, absoluteImageUrl ? "关键帧已接入" : "等待图像")}</strong>
              <p>{visionSummary}</p>
              <div className={styles.vlaLoopState} data-tone={stereoLoopTone}>
                <strong>{stereoLoopState}</strong>
                <span>{stereoLoopDetail}</span>
              </div>
              <small>{text(stereoPayload.control_boundary ?? cameraStreamOffer.control_boundary, "camera_preview_only_not_motion_permission")}</small>
            </article>
            <article data-stage="l">
              <span>L · 小智语音</span>
              <strong>{vlaGateLabel(languageGate)}</strong>
              <p>{effectiveLanguageSummary}</p>
              <small>{text(xiaozhiSession.control_boundary ?? xiaozhiReplyPayload.control_boundary ?? voiceRelay.control_boundary, "voice_only_not_motion_permission")}</small>
            </article>
            <article data-stage="a">
              <span>A · 下一步建议</span>
              <strong>{text(actionCandidate.type, actionGateTitle)}</strong>
              <p>{hasActionCandidate ? actionSummary : actionGateSummary}</p>
              <small>{text(vlaCandidate.control_boundary ?? relayBoundaryText, "vla_candidate_only_not_motion_permission")}</small>
            </article>
          </section>

          <section data-module="overview mode_router" className={`${styles.systemTopology} ${styles.legacyTopology}`} aria-label="VLA 系统拓扑和证据灯带">
            <div className={styles.systemTopologyHead}>
              <span>系统拓扑</span>
              <strong>{currentSemanticMode ? `${semanticActionModeLabel(currentSemanticMode)}闭环` : "等待模式"}</strong>
              <p>从语音意图到视觉证据、平台规划、仿真影子和 M33 安全裁决；当前全部保持只读或 dry-run。</p>
            </div>
            <ol>
              {topologyNodes.map((node, index) => (
                <li key={node.key} data-tone={node.tone} data-last={index === topologyNodes.length - 1 ? "true" : "false"}>
                  <span>{node.eyebrow}</span>
                  <strong>{node.value}</strong>
                  <small>{node.title} · {node.detail}</small>
                </li>
              ))}
            </ol>
          </section>

          <details data-module="overview mode_router training muscle_assist" className={styles.controlRoomDrawer}>
            <summary>
              <span>系统审计与模式资源</span>
              <strong>{currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待 L 分类"} · {visualServoReady ? "V 可闭环" : "V 观察中"}</strong>
            </summary>
            <section className={styles.modeOverviewPanel} aria-label="多模式调度总览">
              <div className={styles.modeOverviewHead}>
                <div>
                  <span>多模式调度</span>
                  <strong>{currentSemanticMode ? semanticActionModeLabel(currentSemanticMode) : "等待 L 分类"}</strong>
                </div>
                <p>同一个小智/L 入口分流到不同模式；平台后端返回成熟度契约，真实运动仍回到 M33。</p>
              </div>
              <ol>
                {displayModeOverviewRows.map((item) => (
                  <li key={item.mode} data-active={currentSemanticMode === item.mode ? "true" : "false"} data-tone={item.tone}>
                    <span>{semanticActionModeLabel(item.mode)}</span>
                    <strong>{item.title}</strong>
                    <p>{item.detail}</p>
                    <small>{item.stage} · {item.next}</small>
                  </li>
                ))}
              </ol>
              <p className={styles.modeOverviewBoundary}>{modeOverviewBoundaryText}</p>
            </section>

            <section className={styles.loopHealthPanel} aria-label="多闭环健康矩阵">
              <div className={styles.loopHealthHead}>
                <span>闭环健康矩阵</span>
                <strong>{visualServoReady ? "视觉记忆可用于 dry-run" : "V hold，其他闭环继续"}</strong>
                <p>视觉识别不是总开关；V 不可用时，训练、肌电、仿真、安全和数据闭环继续推进。</p>
              </div>
              <ol>
                {loopHealthRows.map((item) => (
                  <li key={item.key} data-tone={item.tone}>
                    <span>{item.title}</span>
                    <strong>{item.stage}</strong>
                    <p>{item.evidence}</p>
                    <small>{item.next}</small>
                  </li>
                ))}
              </ol>
            </section>

            <section className={styles.nonVisionPanel} aria-label="非视觉闭环推进">
              <div className={styles.nonVisionHead}>
                <span>无识别时的主线</span>
                <strong>不要等杯子，先把系统闭环跑通</strong>
                <p>取物 V 保持只读观察；平台继续推进不依赖目标识别的链路，保证演示和工程进度不断档。</p>
              </div>
              <ol>
                {nonVisionProgressRows.map((item) => (
                  <li key={item.key} data-tone={item.tone}>
                    <span>{item.owner}</span>
                    <strong>{item.title}</strong>
                    <p>{item.detail}</p>
                    <small>{item.status} · {item.next}</small>
                  </li>
                ))}
              </ol>
              <div className={styles.nonVisionPipelines} aria-label="训练和助力流程轨道">
                <article>
                  <div>
                    <span>训练模式轨道</span>
                    <strong>{currentSemanticMode === "training" ? "训练链路已被 L 选中" : "等待训练指令"}</strong>
                  </div>
                  <ol>
                    {trainingPipelineSteps.map((step) => (
                      <li key={step.key} data-tone={step.tone}>
                        <span>{step.label}</span>
                        <strong>{step.state}</strong>
                      </li>
                    ))}
                  </ol>
                </article>
                <article>
                  <div>
                    <span>肌电助力轨道</span>
                    <strong>{currentSemanticMode === "assistive_emg" ? "助力链路已被 L 选中" : "等待助力/EMG 指令"}</strong>
                  </div>
                  <ol>
                    {assistivePipelineSteps.map((step) => (
                      <li key={step.key} data-tone={step.tone}>
                        <span>{step.label}</span>
                        <strong>{step.state}</strong>
                      </li>
                    ))}
                  </ol>
                </article>
              </div>
            </section>
          </details>

          <details data-module="vision action_planner mode_router" className={styles.engineeringDetailPanel} open={activeModule === "vision" || activeModule === "action_planner" || activeModule === "mode_router"}>
            <summary>
              <span>ENGINEERING DETAIL</span>
              <strong>所有旧功能保留在这里，不丢</strong>
              <small>dry-run / 视觉调试 / XiaoZhi / MuJoCo</small>
            </summary>
          <section className={styles.vlaDecisionDeck} aria-label="VLA-lite 决策甲板">
            <article className={styles.vlaLiteLoopPanel} data-tone={dryRunGateTone}>
              <div>
                <span>A dry-run gate</span>
                <strong>{dryRunGateLabel(dryRunGateState)}</strong>
                <small>{dryRunGateState}</small>
              </div>
              <p>{dryRunGateReason}</p>
              <ol className={styles.vlaEvidenceLadder} aria-label="VLA-lite 证据阶梯">
                {vlaEvidenceLadder.map((item) => (
                  <li key={item.step} data-tone={item.tone}>
                    <span>{item.step}</span>
                    <div>
                      <strong>{item.title}</strong>
                      <small>{item.state}</small>
                    </div>
                    <p>{item.detail}</p>
                  </li>
                ))}
              </ol>
              <ul>
                <li><span>模式</span><strong>{operationModeLabel(operationMode)}</strong></li>
                <li><span>执行</span><strong>{executionMode}</strong></li>
                <li><span>目标白名单</span><strong>{targetAllowlistText}</strong></li>
                <li><span>视觉锁定</span><strong>{stereoVisibleStabilityText}</strong></li>
                <li><span>锁定门</span><strong>{stereoHasPayloadVisualLock ? `${stereoVisualLockState || "unknown"} · ${stereoVisualLockStable ? "dry-run ready" : "observe"}` : "等待 visual_lock_stability"}</strong></li>
                <li><span>闭环状态</span><strong>{vlaLiteLoopLabel(vlaLiteLoopState)}</strong></li>
                <li><span>V 延迟</span><strong>{stereoHasFrameTiming ? `${compactNumberText(stereoFrameProcessMs, " ms")} · ${stereoLoopProgressText}` : "等待 capture_loop"}</strong></li>
              </ul>
            </article>

            <article id="vision-stage" className={`${styles.pixelServoPanel} ${styles.stageAnchor}`} data-tone={pixelServo.tone}>
              <div>
                <span>V 视觉证据</span>
                <strong>{stereoTargetLabel ? `${stereoTargetLabel} · ${pixelServo.title}` : pixelServo.title}</strong>
                <small>{pixelServo.state}</small>
              </div>
              <div className={styles.visionEvidenceStage} aria-label="双目识别框视觉证据">
                <figure>
                  <figcaption>
                    <span>Left</span>
                    <strong>{leftStereoImageSrc ? "edge annotated frame" : "waiting evidence"}</strong>
                  </figcaption>
                  <div className={styles.visionFrame}>
                    {leftStereoImageSrc ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={leftStereoImageSrc} alt="左目摄像头帧" />
                    ) : (
                      <div className={styles.syntheticFrame} />
                    )}
                  </div>
                  <div className={styles.detectionPills}>
                    {leftDetectionPills.map((item) => (
                      <span key={item.key}>{item.label} {Number.isFinite(item.confidence) ? Math.round(item.confidence * 100) : "-"}%</span>
                    ))}
                  </div>
                </figure>
                <figure>
                  <figcaption>
                    <span>Right</span>
                    <strong>{rightStereoImageSrc ? "raw/support frame" : "waiting right image"}</strong>
                  </figcaption>
                  <div className={styles.visionFrame}>
                    {rightStereoImageSrc ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={rightStereoImageSrc} alt="右目摄像头帧" />
                    ) : (
                      <div className={styles.syntheticFrame} />
                    )}
                  </div>
                  <div className={styles.detectionPills}>
                    {rightDetectionPills.map((item) => (
                      <span key={item.key}>{item.label} {Number.isFinite(item.confidence) ? Math.round(item.confidence * 100) : "-"}%</span>
                    ))}
                  </div>
                </figure>
              </div>
              <div className={styles.evidenceProofStrip} aria-label="视觉证据来源">
                <span>图: {visualEvidenceImageSource}</span>
                <span>框: {visualEvidenceBoxSource}</span>
                <span>配对: {visualEvidencePairing}</span>
                <span>边界: dry-run</span>
              </div>
              <div className={styles.visualMemoryPanel} data-state={visualServoReady ? "ready" : "hold"} aria-label="视觉短时记忆">
                <div>
                  <span>视觉短时记忆</span>
                  <strong>{visualServoReady ? "目标和末端可配对" : visualServoStateText}</strong>
                  <small>{visualMemoryPairState}</small>
                </div>
                <dl>
                  <div>
                    <dt>目标</dt>
                    <dd>{recentTargetMemory?.label ?? "等待"} · {targetMemoryFreshness.text}</dd>
                  </div>
                  <div>
                    <dt>末端</dt>
                    <dd>{recentEndEffectorMemory?.label ?? "等待"} · {endEffectorMemoryFreshness.text}</dd>
                  </div>
                  <div>
                    <dt>距离</dt>
                    <dd>{visualServoDistanceText}</dd>
                  </div>
                </dl>
              </div>
              <div className={styles.targetQualityGate} data-tone={targetQualityGateTone} aria-label="目标候选质量门">
                <div>
                  <span>目标质量门</span>
                  <strong>{targetQualityGateTitle}</strong>
                </div>
                <p>{targetQualityGateDetail}</p>
                <small>{text(stereoTargetQualityGate.control_boundary, "target_quality_gate_only_not_motion_permission")}</small>
              </div>
              <div className={styles.visualLockMeter} data-tone={stereoVisualLockStable ? "ok" : visualLockObservedFrames > 0 ? "idle" : "limited"}>
                <div>
                  <span>多帧锁定</span>
                  <strong>{visualLockObservedFrames}/{visualLockRequiredFrames}</strong>
                  <small>{visualLockConfidenceText}</small>
                </div>
                <div className={styles.visualLockBars} aria-label="视觉锁定进度">
                  <span>
                    <em style={{ width: `${Math.round(visualLockProgress * 100)}%` }} />
                  </span>
                  <span>
                    <em style={{ width: `${Math.round(visualLockMatchProgress * 100)}%` }} />
                  </span>
                </div>
                <dl>
                  <div><dt>双目匹配</dt><dd>{visualLockStereoFrames}/{visualLockRequiredFrames}</dd></div>
                  <div><dt>抖动</dt><dd>{visualLockJitterText}</dd></div>
                  <div><dt>门控</dt><dd>{stereoVisualLockStable ? "dry-run ready" : "observe"}</dd></div>
                </dl>
              </div>
              <ul>
                <li><span>目标中心</span><strong>{stereoTargetCenter ? `${compactNumberText(stereoTargetCenter?.[0], " px")}, ${compactNumberText(stereoTargetCenter?.[1], " px")}` : "等待 bbox"}</strong></li>
                <li><span>画面偏移</span><strong>{pixelServo.targetOffsetText}</strong></li>
                <li><span>下一步</span><strong>{pixelServo.nextStep}</strong></li>
              </ul>
            </article>

            <article className={styles.shadowEvidencePanel} data-tone={shadowEvidenceTone}>
              <div>
                <span>MuJoCo shadow 证据</span>
                <strong>{simulationReady ? "shadow 已跑通" : text(simulationReport.readiness, "等待 shadow report")}</strong>
                <small>{simulationReportBoundary}</small>
              </div>
              <p>
                L/A 模式 {semanticModeLabel}；语义目标 {semanticTargetLabel || "等待目标"}；V 看到 {stereoTargetLabel || text(modelRelayVisualServoContext.target_label, "等待 V")} / {stereoEndEffectorLabel || "末端待识别"}。
              </p>
              <ul>
                <li><span>A 来源</span><strong>{semanticSourceLabel}</strong></li>
                <li><span>计划状态</span><strong>{simulationPlanState}</strong></li>
                <li><span>Shadow 轨迹</span><strong>{Number.isFinite(simulationTrajectoryCount) ? `${simulationTrajectoryCount} 条` : "等待"}</strong></li>
                <li><span>采样步数</span><strong>{Number.isFinite(simulationStepCount) ? `${simulationStepCount} 步` : "等待"}</strong></li>
                <li><span>像素距离</span><strong>{modelRelayVisualDistance !== null && modelRelayVisualDistance !== undefined ? compactNumberText(modelRelayVisualDistance, " px") : visualServoDistanceText}</strong></li>
                <li><span>最终关节</span><strong>{simulationJointSummary || "等待 joint_state"}</strong></li>
              </ul>
            </article>

            <article className={styles.voiceRoutePanel} data-route={routeClass}>
              <div>
                <span>语音路由</span>
                <strong>{routeLabel(routeClass)}</strong>
                <small>{routeSourceText} · confidence {routeConfidenceText}</small>
              </div>
              <div className={styles.demoLanguagePicker} aria-label="本地演示 L 输入">
                <p>{effectiveLanguageSummary}</p>
                <div>
                  {DEMO_LANGUAGE_INPUTS.map((sample) => (
                    <button
                      key={sample}
                      type="button"
                      data-active={demoLanguageInput === sample}
                      onClick={() => setDemoLanguageInput(sample)}
                    >
                      {sample}
                    </button>
                  ))}
                  {demoLanguageInput ? (
                    <button type="button" data-kind="clear" onClick={() => setDemoLanguageInput("")}>
                      回到真实 L
                    </button>
                  ) : null}
                </div>
              </div>
              <ul>
                <li><span>route_class</span><strong>{routeClass}</strong></li>
                <li><span>ai_operation_mode</span><strong>{operationMode}</strong></li>
                <li><span>route_action</span><strong>{routeAction}</strong></li>
                <li><span>boundary</span><strong>{text(routePreview.control_boundary, "voice_route_only_not_motion_permission")}</strong></li>
              </ul>
            </article>
          </section>
          </details>

          <div data-module="digital_twin muscle_assist diagnostics" className={styles.primaryGrid}>
            <div className={styles.sceneColumn}>
              <div id="urdf-stage" data-module-panel="digital_twin diagnostics" className={styles.stageAnchor}>
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
              </div>
              <div id="muscle-stage" data-module-panel="muscle_assist diagnostics" className={styles.stageAnchor}>
                <HumanMuscleOverview sensorPayload={sensorPayload} />
              </div>
            </div>

            <aside className={styles.sideStack} data-module-panel="diagnostics action_planner mode_router">
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
                  <button type="button" disabled={!selected || relayState === "sending"} onClick={() => void requestModelRelay()}>
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
                  <button type="button" disabled={relayConfigState === "saving"} onClick={() => void saveRelayConfig()}>
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
                  <button type="button" disabled={!selected || relayExportState === "creating"} onClick={() => void createRelayInvokeToken()}>
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
                  <button type="button" onClick={() => setActiveModule("ai_model")}>
                    AI模型中转
                  </button>
                </div>
              </section>
            </aside>
          </div>

          <div data-module="overview diagnostics training" className={styles.summaryGrid}>
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

          <section data-module="overview diagnostics" className={styles.roleGrid} aria-label="康复机械臂四角色状态">
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

          <details data-module="vision logs" className={styles.drawerPanel} open={activeModule === "vision"}>
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

          <details data-module="diagnostics logs" className={styles.drawerPanel} open={activeModule === "diagnostics"}>
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

          <details data-module="logs diagnostics" className={styles.drawerPanel} open={activeModule === "logs"}>
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
