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
  motor_state?: AnyRecord;
  sensor_state?: AnyRecord;
  safety?: AnyRecord;
  sync_status?: AnyRecord;
  manifest?: AnyRecord;
  data_quality?: AnyRecord;
  device_model?: AnyRecord;
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

type JointFlowRow = {
  jointName: string;
  sourceName: string;
  sourceLabel: string;
  rawValue: number | null;
  calibratedValue: number | null;
  velocity: number | null;
  effort: number | null;
  temperature: number | null;
  status: "matched" | "waiting" | "fault";
};

type UrdfVisualMesh = {
  linkName: string;
  meshPath: string;
  xyz: [number, number, number];
  rpy: [number, number, number];
  scale: [number, number, number];
};

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

function fallbackUrdfFromCalibrations(robotName: string, rows: JointCalibration[]) {
  const safeRobotName = robotName.replace(/[^A-Za-z0-9_-]+/g, "_") || "robot_model";
  const links = [`  <link name="base_link"/>`];
  const joints: string[] = [];
  rows.forEach((row, index) => {
    const linkName = `link_${index + 1}`;
    links.push(`  <link name="${linkName}"/>`);
    joints.push([
      `  <joint name="${row.jointName}" type="revolute">`,
      `    <parent link="${index === 0 ? "base_link" : `link_${index}`}"/>`,
      `    <child link="${linkName}"/>`,
      `    <origin xyz="0 0 ${((index + 1) * 0.08).toFixed(3)}" rpy="0 0 0"/>`,
      `    <axis xyz="0 0 1"/>`,
      `    <limit lower="-3.14" upper="3.14" effort="1" velocity="1"/>`,
      "  </joint>",
    ].join("\n"));
  });
  return `<robot name="${safeRobotName}">\n${links.join("\n")}\n${joints.join("\n")}\n</robot>\n`;
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

function publicDeviceName(device: DashboardDevice | null | undefined, index = 0) {
  const safeIndex = Math.max(0, index);
  const robotName = text(device?.robot_id, "");
  if (robotName && !isRawIdentifier(robotName)) return robotName;
  const deviceName = text(device?.device_id, "");
  if (deviceName && !isRawIdentifier(deviceName)) return deviceName;
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
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
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
  if (type === "sync_status") return "数据批次同步";
  if (type === "manifest") return "设备档案上传";
  if (type === "device_registration") return "设备注册";
  return type;
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
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${Number.isInteger(number) ? number : number.toFixed(3)}${unit}`;
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
    if (text(motor.source_label, "") === "ROS 关节状态") return [jointName].filter(Boolean);
    return [jointName, motorId || `motor_${index + 1}`].filter(Boolean);
  })));
}

function motorSourceKey(motor: AnyRecord, index = 0) {
  const jointName = text(motor.joint_name ?? motor.jointName, "");
  const motorId = text(motor.motor_id ?? motor.motorId, "");
  if (text(motor.source_label, "") === "ROS 关节状态") return jointName;
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
      };
    })
    .filter(Boolean) as AnyRecord[];
}

function poseSamplesFromTelemetry(motorPayload: AnyRecord, sensorPayload: AnyRecord) {
  const motors: AnyRecord[] = asArray<AnyRecord>(motorPayload.motors).map((motor) => ({ ...motor, source_label: "电机状态" }));
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
    return [0.42, -0.18, 0.24, 0.72, -0.32][index] ?? 0;
  });
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
  return `rehab-arm-pose-calibration:${urdfName || "placeholder"}`;
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
): JointFlowRow[] {
  const rowsByJoint = new Map(calibrations.map((row) => [row.jointName, row]));
  return jointNames.map((jointName) => {
    const row = rowsByJoint.get(jointName);
    const sourceName = row?.sourceName || "";
    const motor = sourceName ? sourceMotors.get(sourceName) : undefined;
    const rawValue = sourceName && sourceValues.has(sourceName) ? Number(sourceValues.get(sourceName)) : null;
    const calibratedValue = row ? calibratedJointValue(row, sourceValues) : null;
    const fault = Boolean(motor?.fault ?? motor?.has_fault ?? motor?.hasFault);
    return {
      jointName,
      sourceName,
      sourceLabel: text(motor?.source_label, sourceName ? "电机状态" : "等待上报"),
      rawValue,
      calibratedValue,
      velocity: numericOrNull(motor?.velocity ?? motor?.velocity_rad_s ?? motor?.velocityRadS),
      effort: numericOrNull(motor?.torque ?? motor?.effort ?? motor?.current),
      temperature: numericOrNull(motor?.temperature ?? motor?.temp_c ?? motor?.tempC),
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
  safetyState,
}: {
  deviceId: string;
  robotId: string;
  projectId: string;
  deviceModel: AnyRecord;
  motors: AnyRecord[];
  safetyState: string;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const cleanupRef = useRef<() => void>(() => {});
  const robotRef = useRef<AnyRecord | null>(null);
  const positions = useMemo(() => jointPositionsFromMotors(motors), [motors]);
  const jointValues = useMemo(() => jointValueMapFromMotors(motors), [motors]);
  const positionsRef = useRef(positions);
  const jointValuesRef = useRef(jointValues);
  const [urdfText, setUrdfText] = useState("");
  const [urdfPackage, setUrdfPackage] = useState<UrdfPackage | null>(null);
  const placeholderPoseKey = urdfText ? "" : positions.map((position) => position.toFixed(4)).join("|");
  const [urdfName, setUrdfName] = useState("");
  const [urdfState, setUrdfState] = useState<"placeholder" | "loading" | "loaded" | "failed">("placeholder");
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
  const jointRowsKey = jointRows.join("\u0001");
  const sourceNamesKey = sourceNames.join("\u0001");
  const [calibrations, setCalibrations] = useState<JointCalibration[]>([]);
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
    () => (jointRows.length ? jointRows : urdfJointNames.length ? urdfJointNames : ARM_MODEL_JSON.joints),
    [jointRows, urdfJointNames],
  );
  const flowRows = useMemo(
    () => jointFlowRows(flowJointNames, calibrations, jointValues, sourceMotors),
    [calibrations, flowJointNames, jointValues, sourceMotors],
  );
  const activeFlowRows = flowRows.filter((row) => row.status === "matched").length;

  useEffect(() => {
    positionsRef.current = positions;
    jointValuesRef.current = calibratedJointValues;
  }, [calibratedJointValues, positions]);

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
        restoredModelRef.current = restoreKey;
        serverCalibrationsRef.current = calibrationMapFromJson(mappingJson);
        let modelPackage: UrdfPackage;
        try {
          const response = await fetch(keyframeSrc(modelUrl, ""), { cache: "no-store", signal: controller.signal });
          if (!response.ok) throw new Error("model package fetch failed");
          const buffer = await response.arrayBuffer();
          modelPackage = await readUrdfPackageBuffer(fileName, buffer);
        } catch {
          const rows = Array.from(serverCalibrationsRef.current.values());
          if (!rows.length) throw new Error("model package restore failed");
          const generatedUrdf = fallbackUrdfFromCalibrations(packageName, rows);
          modelPackage = {
            fileName,
            packageName,
            urdfPath: urdfPath || `${packageName}/urdf/${packageName}.urdf`,
            urdfText: generatedUrdf,
            files: new Map([[urdfPath || `${packageName}/urdf/${packageName}.urdf`, new TextEncoder().encode(generatedUrdf).buffer]]),
          };
        }
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

      const camera = new THREE.PerspectiveCamera(42, width / height, 0.01, 100);
      camera.position.set(1.15, -1.45, 0.9);
      camera.lookAt(0.26, 0.08, 0.24);

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
      controls.minDistance = 0.55;
      controls.maxDistance = 3.4;
      controls.maxPolarAngle = Math.PI * 0.92;
      controls.target.set(0.24, 0.18, 0.18);
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
      const baseMat = new THREE.MeshStandardMaterial({ color: 0x1b3a3c, roughness: 0.62, metalness: 0.12 });
      const base = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.14, 0.08, 40), baseMat);
      base.position.y = 0.04;
      scene.add(base);

      function addPlaceholderArm() {
        const group = new THREE.Group();
        group.position.y = 0.1;
        scene.add(group);
        const jointMaterial = new THREE.MeshStandardMaterial({
          color: safetyState === "ok" ? 0x78e6aa : safetyState === "fault" ? 0xff705e : 0xffd166,
          roughness: 0.44,
          metalness: 0.18,
        });
        let cursor = new THREE.Vector3(0, 0, 0);
        const currentPositions = positionsRef.current;
        let yaw = currentPositions[1] || 0;
        let pitch = currentPositions[0] || 0.3;
        ARM_MODEL_JSON.links.slice(1).forEach((link, index) => {
          const length = link.length;
          if (index === 2) pitch -= currentPositions[3] || 0.4;
          if (index === 3) yaw += currentPositions[4] || 0;
          const dir = new THREE.Vector3(
            Math.cos(pitch) * Math.cos(yaw),
            Math.sin(pitch),
            Math.cos(pitch) * Math.sin(yaw),
          ).normalize();
          const mid = cursor.clone().add(dir.clone().multiplyScalar(length / 2));
          const geometry = new THREE.CylinderGeometry(link.radius, link.radius, length, 24);
          const material = new THREE.MeshStandardMaterial({ color: link.color, roughness: 0.58, metalness: 0.1 });
          const mesh = new THREE.Mesh(geometry, material);
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
          addPlaceholderArm();
          setUrdfState("placeholder");
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
          robot.traverse?.((child: AnyRecord) => {
            if (child.isMesh) {
              child.castShadow = false;
              child.receiveShadow = false;
              child.material = new THREE.MeshStandardMaterial({
                color: 0x8ef0c7,
                roughness: 0.62,
                metalness: 0.08,
              });
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
          addPlaceholderArm();
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
  }, [placeholderPoseKey, safetyState, urdfPackage, urdfText]);

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
          ? "URDF 未能完整加载，已回退占位模型"
          : "当前是占位模型，可导入 URDF";

  return (
    <section className={styles.armOverviewPanel} aria-label="机械臂 3D 总览">
      <div className={styles.panelHead}>
        <div>
          <span>URDF / Three.js 机械臂</span>
          <strong>{modelStateText}</strong>
        </div>
        <small>{matchedUrdfJoints.length || positions.length} 个关节正在匹配角度</small>
      </div>
      <div className={styles.urdfToolbar}>
        <label>
          <span>导入本机模型包</span>
          <input
            type="file"
            accept=".zip,.urdf,.xml"
            data-testid="rehab-urdf-file"
            onChange={(event) => handleUrdfFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <p>支持 URDF zip 包或单个 URDF。页面用电机状态或 ROS 关节状态驱动同名关节，只读预览，不下发任何运动控制。</p>
      </div>
      <div ref={mountRef} className={styles.armCanvas} />
      {urdfJoints.length ? (
        <div className={styles.poseStatus}>
          <strong>匹配 {matchedUrdfJoints.length}/{jointRows.length || urdfJoints.length}</strong>
          <span>{sourceLabels.join(" + ") || "角度状态"} 会实时套用到同名关节；模型资源已加载 {meshStats.loaded} 个，未加载 {meshStats.missing} 个。</span>
          <span>
            {modelSaveState === "saving"
              ? "正在保存到当前设备档案"
              : modelSaveState === "saved"
                ? "已保存到当前设备档案，刷新后会自动恢复"
                : modelSaveState === "restored"
                  ? "已从当前设备档案恢复模型包"
                  : modelSaveState === "error"
                    ? "模型档案同步失败，可重新导入"
                    : "导入后会保存到当前设备档案"}
          </span>
        </div>
      ) : null}
      <section className={flowStyles.jointFlowPanel} aria-label="关节状态流">
        <div className={flowStyles.jointFlowHead}>
          <div>
            <span>关节状态流</span>
            <strong>{activeFlowRows}/{flowRows.length} 个关节有实时角度</strong>
          </div>
          <small>{sourceNames.length ? `${sourceNames.length} 个只读角度来源` : "等待 NanoPi 或仿真主机上报"}</small>
        </div>
        <div className={flowStyles.jointFlowGrid} data-testid="rehab-joint-state-flow">
          {flowRows.slice(0, 8).map((row) => (
            <article key={row.jointName} data-state={row.status}>
              <div>
                <strong>{row.jointName}</strong>
                <span>{row.sourceName || "待匹配"} · {row.sourceLabel}</span>
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
      </section>
      {urdfJoints.length ? (
        <details className={styles.poseMappingPanel} open>
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
      <div className={styles.armLegend}>
        {(urdfJointNames.length ? urdfJointNames : ARM_MODEL_JSON.joints).slice(0, 10).map((name, index) => (
          <span key={name}>{name}: {numberText(calibratedJointValues.get(name) ?? positions[index], " rad")}</span>
        ))}
      </div>
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

  const selectedIndex = selected ? deviceIndexById.get(selected.device_id) ?? 0 : 0;
  const roleSignals = useMemo(() => roleSignalsFromDevices(devices), [devices]);
  const keyframe = selected?.camera_keyframe ?? {};
  const keyframePayload = payloadOf(keyframe);
  const motorPayload = payloadOf(selected?.motor_state);
  const sensorPayload = payloadOf(selected?.sensor_state);
  const safetyPayload = payloadOf(selected?.safety);
  const dataQuality = selected?.data_quality ?? {};
  const motors = asArray<AnyRecord>(motorPayload.motors);
  const poseSamples = useMemo(() => poseSamplesFromTelemetry(motorPayload, sensorPayload), [motorPayload, sensorPayload]);
  const imageUrl = text(keyframe.image_url, "");
  const absoluteImageUrl = keyframeSrc(imageUrl, apiBaseUrl);
  const motionAllowed = Boolean(safetyPayload.motion_allowed ?? selected?.motion_allowed);
  const currentSafetyState = safetyPayload.state ?? selected?.safety_state;
  const qualityReady = Boolean(dataQuality.annotation_ready);
  const roleCards = [
    { key: "nanopi", title: "NanoPi / Linux", subtitle: "本地 ROS 与设备接入节点", ...latestRoleStatus(roleSignals, "nanopi") },
    { key: "m33", title: "M33 / M55", subtitle: "安全裁决与轻量推理", ...latestRoleStatus(roleSignals, "m33") },
    { key: "app", title: "App / 现场", subtitle: "近场参数、患者信息、急停", ...latestRoleStatus(roleSignals, "app") },
    { key: "sim", title: "仿真主机", subtitle: "MuJoCo / RViz / 路径验证", ...latestRoleStatus(roleSignals, "sim") },
  ];

  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          <Link href={`/projects/${projectId}`} className={styles.backLink}>← 主页面</Link>
          <Link href={`/projects/${projectId}/robotics`} className={styles.backLink} prefetch={false}>设备数据工作台</Link>
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
            {pollState === "error" ? "实时刷新异常" : lastLiveUpdate ? `已同步 ${new Date(lastLiveUpdate).toLocaleTimeString("zh-CN", { hour12: false })}` : "准备同步"}
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

          <div className={styles.summaryGrid}>
            <article>
              <span>数据批次</span>
              <strong>{publicBatchLabel(selected?.current_session)}</strong>
              <p>{selected?.latest_upload_status || "等待上传"}</p>
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
          </div>

          <div className={styles.primaryGrid}>
            <Arm3DOverview
              deviceId={text(selected?.device_id, "")}
              robotId={text(selected?.robot_id, "")}
              projectId={projectId}
              deviceModel={record(selected?.device_model)}
              motors={poseSamples}
              safetyState={stateLabel(currentSafetyState)}
            />

            <aside className={styles.sideStack}>
              <section className={styles.safetyPanel} data-state={stateLabel(currentSafetyState)}>
                <span>安全状态</span>
                <strong>{stateText(currentSafetyState)}</strong>
                <p>急停：{boolText(safetyPayload.emergency_stop)}；M33 模式：{publicStateValue(safetyPayload.m33_mode)}；心跳：{text(safetyPayload.heartbeat_age_ms, "-")} ms。</p>
              </section>
              <section className={styles.taskPanel}>
                <span>下一步</span>
                <strong>{qualityReady ? "进入标注" : "先补齐数据"}</strong>
                <p>{qualityReady ? "用设备数据工作台做标注、导出和图表分析。" : "先让 NanoPi 上传完整数据批次、电机状态和质量报告。"}</p>
                <Link
                  href={`/projects/${projectId}/robotics?tab=dataset&device=${encodeURIComponent(selected?.device_id ?? "")}`}
                  prefetch={false}
                >
                  打开数据工作台
                </Link>
              </section>
            </aside>
          </div>

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
