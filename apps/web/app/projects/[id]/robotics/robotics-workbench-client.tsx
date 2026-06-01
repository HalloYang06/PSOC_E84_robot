"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiClientUrl } from "../../../../lib/api-client-url";
import {
  下发机器人调试命令,
  创建机器人图表实验,
  创建机器人调试窗口,
  创建机器人数据预标注请求,
  创建机器人调参建议请求,
  创建机器人调试Npc操作审核,
  更新机器人调试窗口,
  删除机器人调试窗口,
  导出机器人标注数据,
  请求串口USB扫描,
  记录机器人采集片段,
} from "../../../actions";
import tileStyles from "../workbench/_components/npc-tile.module.css";
import workbenchStyles from "../workbench/workbench.module.css";
import { ModelImportInspector } from "./model-import-inspector";
import styles from "./robotics.module.css";

type AnyRecord = Record<string, any>;

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
  baudRate?: string;
  sampleHz?: string;
  channels?: string;
  readCapability: boolean;
  writeCapabilityLabel: string;
  isUsable: boolean;
};

type TileTab = "terminal" | "dataset" | "chart" | "model";
type DeviceTab = "data" | "camera" | "dataset" | "chart" | "model";
type DeviceWorkbenchMode = "boards" | "interfaces";
type InitialRoboticsTab = string;

type RoboticsWorkbenchClientProps = {
  projectId: string;
  projectName: string;
  windows: DebugWindow[];
  initialSavedWindows: SavedDebugWindow[];
  npcSeats: AnyRecord[];
  terminalMessages: AnyRecord[];
  initialOpenIds: string[];
  initialNpcId: string;
  initialTab: InitialRoboticsTab;
  readyComputers: number;
  queueableComputers: number;
  reconnectComputers: number;
  unknownComputers: number;
  computerCount: number;
  scannedInterfaceCount: number;
  deviceQualityDevices: AnyRecord[];
  notice?: string;
  error?: string;
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

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function isRawIdentifier(value: unknown) {
  const raw = text(value, "");
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)
    || /^[0-9a-f]{12,}$/i.test(raw);
}

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? value as AnyRecord : {};
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function initialDeviceTab(tab: InitialRoboticsTab): DeviceTab {
  if (tab === "camera" || tab === "dataset" || tab === "chart" || tab === "model") return tab;
  return "data";
}

function initialTileTab(tab: InitialRoboticsTab): TileTab {
  if (tab === "dataset" || tab === "chart" || tab === "model") return tab;
  return "terminal";
}

function payloadOf(value: unknown): AnyRecord {
  const next = record(value);
  return record(next.payload);
}

function numberText(value: unknown, unit = "") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${Number.isInteger(number) ? number : number.toFixed(2)}${unit}`;
}

function publicDataBatchLabel(value: unknown, fallback = "最近数据批次") {
  const raw = text(value, fallback);
  return raw.replace(/^session[\s_-]*/i, "批次 ");
}

const OPEN_SOURCE_MESH_URL = "/assets/open-source/robot-expressive/RobotExpressive.glb";

const ARM_STATE_MODEL = {
  joints: [
    "shoulder_lift_joint",
    "shoulder_abduction_joint",
    "upper_arm_rotation_joint",
    "elbow_lift_joint",
    "forearm_rotation_joint",
  ],
  links: [
    { name: "shoulder", length: 0.42, radius: 0.045 },
    { name: "upper_arm", length: 0.46, radius: 0.04 },
    { name: "forearm", length: 0.38, radius: 0.035 },
    { name: "wrist", length: 0.18, radius: 0.03 },
  ],
};

function latestMotorStateDevice(devices: AnyRecord[]) {
  const sorted = devices
    .filter((device) => asArray(record(payloadOf(device.motor_state)).motors).length > 0)
    .sort((a, b) => Number(record(a.motor_state).ts_unix ?? 0) - Number(record(b.motor_state).ts_unix ?? 0));
  return sorted[sorted.length - 1];
}

function motorsFromDevices(devices: AnyRecord[]) {
  return asArray<AnyRecord>(payloadOf(latestMotorStateDevice(devices)?.motor_state).motors);
}

function jointPositionsFromMotors(motors: AnyRecord[]) {
  const byName = new Map(motors.map((motor) => [text(motor.joint_name), Number(motor.position)]));
  return ARM_STATE_MODEL.joints.map((name, index) => {
    const value = byName.get(name);
    if (Number.isFinite(value)) return Number(value);
    return [0.24, -0.16, 0.18, 0.58, -0.2][index] ?? 0;
  });
}

function motorForJoint(motors: AnyRecord[], jointName: string, index: number) {
  return motors.find((motor) => text(motor.joint_name) === jointName)
    ?? motors.find((motor) => Number(motor.motor_id) === index + 1)
    ?? motors[index]
    ?? {};
}

function temperatureOf(motor: AnyRecord) {
  const direct = Number(motor.temperature);
  if (Number.isFinite(direct)) return direct;
  const temp = Number(record(motor.telemetry).temperature);
  return Number.isFinite(temp) ? temp : null;
}

function temperatureColor(temp: number | null) {
  if (temp == null) return 0x6f8d91;
  if (temp < 38) return 0x65d6ff;
  if (temp < 50) return 0x75e6a8;
  if (temp < 65) return 0xf1d06b;
  if (temp < 78) return 0xff9b5f;
  return 0xff5f5f;
}

function latestMotorStateLine(device: AnyRecord | undefined, motors: AnyRecord[]) {
  if (!device || !motors.length) return "等待设备上传电机状态；可先加载开源模型验证显示。";
  const ts = Number(record(device.motor_state).ts_unix);
  const when = Number.isFinite(ts) && ts > 0 ? new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false }) : "无时间戳";
  return `${deviceTitle(device)} · ${publicDeviceCode(device)} · ${motors.length} 个电机 · ${when}`;
}

function deviceId(device: AnyRecord, index = 0) {
  return text(device.device_id, `device-${index + 1}`);
}

function deviceTitle(device: AnyRecord, index = 0) {
  const robotName = text(device.robot_id, "");
  if (robotName && !isRawIdentifier(robotName)) return robotName;
  const code = text(device.device_id, "");
  if (code && !isRawIdentifier(code)) return code;
  return `设备 ${index + 1}`;
}

function publicDeviceCode(device: AnyRecord, index = 0) {
  const code = text(device.device_id, "");
  if (code && !isRawIdentifier(code)) return code;
  return `设备 ${index + 1}`;
}

function latestPayload(device: AnyRecord, key: string) {
  return payloadOf(device[key]);
}

function latestTime(device: AnyRecord, key: string) {
  const ts = Number(record(device[key]).ts_unix ?? device.last_upload_ts_unix);
  if (!Number.isFinite(ts) || ts <= 0) return "无记录";
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

function latestDeviceUploadTime(device: AnyRecord) {
  const timestamps = [
    Number(device.last_upload_ts_unix),
    Number(record(device.motor_state).ts_unix),
    Number(record(device.sensor_state).ts_unix),
    Number(record(device.camera_keyframe).ts_unix),
    Number(record(device.safety).ts_unix),
    Number(record(device.simulation_readiness).ts_unix),
  ].filter((value) => Number.isFinite(value) && value > 0);
  const latest = Math.max(0, ...timestamps);
  return latest > 0 ? new Date(latest * 1000).toLocaleString("zh-CN", { hour12: false }) : "无上传记录";
}

function dataQualityReady(device: AnyRecord) {
  return record(device.data_quality).annotation_ready === true;
}

function deviceSafetyText(device: AnyRecord) {
  const payload = latestPayload(device, "safety");
  const state = text(payload.state, text(device.safety_state, "unknown"));
  if (state === "ok") return "安全正常";
  if (state === "limited") return "受限";
  if (state === "emergency_stop") return "急停";
  if (state === "fault") return "故障";
  return state;
}

function deviceDataCounts(device: AnyRecord) {
  const motors = asArray<AnyRecord>(latestPayload(device, "motor_state").motors);
  const sensor = latestPayload(device, "sensor_state");
  const camera = latestPayload(device, "camera_keyframe");
  const board = boardCapabilities(device);
  return {
    motors: motors.length,
    sensorFields: Object.keys(sensor).filter((key) => !["schema_version", "device_id", "robot_id"].includes(key)).length,
    hasCamera: Boolean(text(camera.image_url) || text(camera.camera_id) || board.cameraDevices.length),
  };
}

function boardCapabilities(device: AnyRecord) {
  const manifest = record(latestPayload(device, "board_manifest").manifest);
  const capabilities = record(manifest.capabilities);
  return {
    manifest,
    platform: record(manifest.platform),
    controlBoundary: text(manifest.control_boundary, "未声明"),
    canInterfaces: asArray<AnyRecord>(capabilities.can_interfaces),
    serialDevices: asArray<string>(capabilities.serial_devices),
    cameraDevices: asArray<string>(capabilities.camera_devices),
    usbDevices: asArray<AnyRecord>(capabilities.usb_devices),
    ros2: record(capabilities.ros2),
  };
}

function ros2CapabilityText(ros2: AnyRecord) {
  if (ros2.available === true) return text(ros2.version, "已发现 ROS2");
  if (ros2.available === false) return "未发现";
  return "未知";
}

function usbDeviceLabel(device: AnyRecord, index: number) {
  return text(device.description, text(device.product, text(device.id, `USB ${index + 1}`)));
}

function canInterfaceLabel(iface: AnyRecord, index: number) {
  return text(iface.name, `can${index}`);
}

function keyframeSrc(imageUrl: string) {
  if (!imageUrl) return "";
  if (imageUrl.startsWith("/api/")) return `/api/proxy/${imageUrl.slice("/api/".length)}`;
  return imageUrl;
}

function cameraImageUrl(device: AnyRecord) {
  const camera = record(device.camera_keyframe);
  const payload = latestPayload(device, "camera_keyframe");
  return text(camera.image_url, text(payload.image_url, ""));
}

function sensorEntries(device: AnyRecord) {
  const sensor = latestPayload(device, "sensor_state");
  return Object.entries(sensor)
    .filter(([key]) => !["schema_version", "device_id", "robot_id", "source"].includes(key))
    .slice(0, 16);
}

function scalarText(value: unknown) {
  if (value == null || value === "") return "-";
  if (typeof value === "number") return Number.isFinite(value) ? (Number.isInteger(value) ? String(value) : value.toFixed(3)) : "-";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return JSON.stringify(value).slice(0, 96);
  return text(value, "-");
}

function motorVariableRows(device: AnyRecord) {
  const motors = asArray<AnyRecord>(latestPayload(device, "motor_state").motors);
  return motors.flatMap((motor, index) => {
    const joint = text(motor.joint_name, `motor_${text(motor.motor_id, String(index + 1))}`);
    return [
      { name: `${joint}.position`, value: numberText(motor.position, " rad"), source: "电机状态", time: latestTime(device, "motor_state") },
      { name: `${joint}.velocity`, value: numberText(motor.velocity, " rad/s"), source: "电机状态", time: latestTime(device, "motor_state") },
      { name: `${joint}.temperature`, value: temperatureOf(motor) == null ? "-" : numberText(temperatureOf(motor), " C"), source: "电机状态", time: latestTime(device, "motor_state") },
      { name: `${joint}.enabled`, value: motor.enabled == null ? "-" : String(Boolean(motor.enabled)), source: "电机状态", time: latestTime(device, "motor_state") },
    ];
  });
}

function sensorVariableRows(device: AnyRecord) {
  return sensorEntries(device).map(([key, value]) => ({
    name: `sensor.${key}`,
    value: scalarText(value),
    source: "传感器摘要",
    time: latestTime(device, "sensor_state"),
  }));
}

function cameraVariableRows(device: AnyRecord) {
  const camera = latestPayload(device, "camera_keyframe");
  const rows = [
    ["camera.camera_id", camera.camera_id],
    ["camera.scene_summary", camera.scene_summary],
    ["camera.detection_summary", camera.detection_summary],
    ["camera.vla_context", camera.vla_context],
  ];
  return rows
    .filter(([, value]) => text(value, ""))
    .map(([name, value]) => ({ name: String(name), value: scalarText(value), source: "摄像头关键帧", time: latestTime(device, "camera_keyframe") }));
}

function deviceVariableRows(device: AnyRecord) {
  return [...motorVariableRows(device), ...sensorVariableRows(device), ...cameraVariableRows(device)];
}

function MotorState3DViewer({
  motors,
  sourceLine,
  syncEnabled,
  showOpenSourceMesh,
}: {
  motors: AnyRecord[];
  sourceLine: string;
  syncEnabled: boolean;
  showOpenSourceMesh: boolean;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const positions = useMemo(() => jointPositionsFromMotors(motors), [motors]);

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
      const width = Math.max(320, target.clientWidth || 680);
      const height = Math.max(300, target.clientHeight || 420);
      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x061014);

      const camera = new THREE.PerspectiveCamera(42, width / height, 0.01, 100);
      camera.position.set(1.25, -1.45, 0.9);
      camera.lookAt(0.25, 0.1, 0.2);

      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(width, height);
      renderer.domElement.setAttribute("aria-label", "电机状态 3D 预览");
      target.replaceChildren(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.enablePan = true;
      controls.enableZoom = true;
      controls.minDistance = 0.55;
      controls.maxDistance = 3.8;
      controls.target.set(0.24, 0.16, 0.18);
      controls.update();

      scene.add(new THREE.HemisphereLight(0xecffff, 0x0a272f, 2.1));
      const keyLight = new THREE.DirectionalLight(0xffffff, 1.35);
      keyLight.position.set(1.4, -1.8, 2.2);
      scene.add(keyLight);
      const fillLight = new THREE.DirectionalLight(0x75f7dd, 0.55);
      fillLight.position.set(-1.1, 1.1, 1.2);
      scene.add(fillLight);
      scene.add(new THREE.GridHelper(1.5, 12, 0x214a48, 0x10272b));

      const base = new THREE.Mesh(
        new THREE.CylinderGeometry(0.12, 0.14, 0.08, 40),
        new THREE.MeshStandardMaterial({ color: 0x1b3a3c, roughness: 0.62, metalness: 0.12 }),
      );
      base.position.y = 0.04;
      scene.add(base);

      const group = new THREE.Group();
      group.position.y = 0.1;
      scene.add(group);

      let cursor = new THREE.Vector3(0, 0, 0);
      let yaw = positions[1] || 0;
      let pitch = positions[0] || 0.28;
      ARM_STATE_MODEL.links.forEach((link, index) => {
        if (index === 2) pitch -= positions[3] || 0.38;
        if (index === 3) yaw += positions[4] || 0;
        const jointName = ARM_STATE_MODEL.joints[Math.min(index, ARM_STATE_MODEL.joints.length - 1)];
        const motor = motorForJoint(motors, jointName, index);
        const temp = temperatureOf(motor);
        const color = temperatureColor(temp);
        const dir = new THREE.Vector3(
          Math.cos(pitch) * Math.cos(yaw),
          Math.sin(pitch),
          Math.cos(pitch) * Math.sin(yaw),
        ).normalize();
        const mid = cursor.clone().add(dir.clone().multiplyScalar(link.length / 2));
        const mesh = new THREE.Mesh(
          new THREE.CylinderGeometry(link.radius, link.radius, link.length, 28),
          new THREE.MeshStandardMaterial({ color, roughness: 0.54, metalness: 0.12 }),
        );
        mesh.position.copy(mid);
        mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
        group.add(mesh);
        const joint = new THREE.Mesh(
          new THREE.SphereGeometry(link.radius * 1.75, 24, 16),
          new THREE.MeshStandardMaterial({ color, roughness: 0.42, metalness: 0.18 }),
        );
        joint.position.copy(cursor);
        group.add(joint);
        cursor = cursor.add(dir.multiplyScalar(link.length));
      });
      const end = new THREE.Mesh(
        new THREE.SphereGeometry(0.045, 24, 16),
        new THREE.MeshStandardMaterial({ color: 0xeaffff, roughness: 0.45, metalness: 0.12 }),
      );
      end.position.copy(cursor);
      group.add(end);

      if (showOpenSourceMesh) {
        try {
          const { GLTFLoader } = await import("three/examples/jsm/loaders/GLTFLoader.js");
          const loader = new GLTFLoader();
          loader.load(OPEN_SOURCE_MESH_URL, (gltf: any) => {
            if (disposed) return;
            const model = gltf.scene;
            const box = new THREE.Box3().setFromObject(model);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z, 1);
            model.position.sub(center);
            model.scale.setScalar(0.34 / maxDim);
            model.position.set(-0.34, 0.14, -0.28);
            model.traverse((child: any) => {
              if (child.isMesh) {
                child.castShadow = true;
                child.receiveShadow = true;
              }
            });
            scene.add(model);
          });
        } catch {}
      }

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
        scene.traverse((object: any) => {
          object.geometry?.dispose?.();
          if (Array.isArray(object.material)) object.material.forEach((mat: any) => mat.dispose?.());
          else object.material?.dispose?.();
        });
        scene.clear();
        if (target.contains(renderer.domElement)) target.removeChild(renderer.domElement);
      };
    }

    void renderArm();
    return () => {
      disposed = true;
      cleanup();
    };
  }, [motors, positions, showOpenSourceMesh]);

  return (
    <section className={styles.motorStateViewer} aria-label="电机状态 3D 预览">
      <div className={styles.motorStateViewerHead}>
        <div>
          <span>{syncEnabled ? "数据同步中" : "显示最近状态"}</span>
          <strong>电机状态驱动的机器人姿态</strong>
        </div>
        <small>{sourceLine}</small>
      </div>
      <div ref={mountRef} className={styles.motorStateCanvas} data-testid="robotics-motor-state-canvas" />
      <div className={styles.tempLegend} aria-label="温度颜色图例">
        <span data-temp="cool">低温</span>
        <span data-temp="normal">正常</span>
        <span data-temp="warm">偏热</span>
        <span data-temp="hot">高温</span>
      </div>
      <div className={styles.motorJointLegend}>
        {ARM_STATE_MODEL.joints.map((joint, index) => {
          const motor = motorForJoint(motors, joint, index);
          const temp = temperatureOf(motor);
          return (
            <span key={joint}>
              {joint}: {numberText(positions[index], " rad")} / {temp == null ? "无温度" : numberText(temp, " C")}
            </span>
          );
        })}
      </div>
    </section>
  );
}

function DeviceDataOverview({ device }: { device: AnyRecord }) {
  const motorPayload = latestPayload(device, "motor_state");
  const sensorPayload = latestPayload(device, "sensor_state");
  const safetyPayload = latestPayload(device, "safety");
  const cameraPayload = latestPayload(device, "camera_keyframe");
  const simReport = simulationReport(device);
  const manifest = record(device.manifest);
  const board = boardCapabilities(device);
  const motors = asArray<AnyRecord>(motorPayload.motors);
  const quality = record(device.data_quality);
  const blockingReasons = asArray<string>(quality.blocking_reasons);
  return (
    <section className={styles.deviceDataPane} aria-label={`${deviceTitle(device)} Linux 开发板采集数据`}>
      <div className={styles.deviceDataSummary}>
        <article data-tone={text(device.online_state) === "online" ? "ok" : "idle"}>
          <span>设备在线</span>
          <strong>{text(device.online_state) === "online" ? "在线" : "离线"}</strong>
          <p>最近上传：{latestTime(device, "motor_state")}</p>
        </article>
        <article data-tone={text(device.safety_state) === "ok" ? "ok" : "warn"}>
          <span>安全状态</span>
          <strong>{deviceSafetyText(device)}</strong>
          <p>本地安全链路：{Boolean(safetyPayload.motion_allowed ?? device.motion_allowed) ? "允许运动" : "不允许运动"}</p>
        </article>
        <article>
          <span>电机数据</span>
          <strong>{motors.length} 个电机</strong>
          <p>{text(motorPayload.source, "等待电机状态")}</p>
        </article>
        <article data-tone={dataQualityReady(device) ? "ok" : "idle"}>
          <span>标注质量</span>
          <strong>{dataQualityReady(device) ? "可标注" : "待补数据"}</strong>
          <p>{blockingReasons.slice(0, 2).join("；") || text(device.latest_upload_status, "等待设备档案")}</p>
        </article>
      </div>

      <div className={styles.nanoPiDataGrid}>
        <article>
          <div className={styles.panelHead}>
            <div>
              <span>电机 / 关节</span>
              <strong>{motors.length ? "最近电机状态" : "等待电机状态"}</strong>
            </div>
            <small>{latestTime(device, "motor_state")}</small>
          </div>
          {motors.length ? (
            <div className={styles.deviceMotorTable}>
              <div><span>电机</span><span>关节</span><span>位置</span><span>速度</span><span>温度</span><span>状态</span></div>
              {motors.map((motor, index) => (
                <div key={`${text(motor.motor_id, "motor")}-${index}`} data-fault={motor.fault ? "true" : "false"}>
                  <span>{text(motor.motor_id, String(index + 1))}</span>
                  <span>{text(motor.joint_name, "-")}</span>
                  <span>{numberText(motor.position, " rad")}</span>
                  <span>{numberText(motor.velocity, " rad/s")}</span>
                  <span>{temperatureOf(motor) == null ? "-" : numberText(temperatureOf(motor), " C")}</span>
                  <span>{motor.fault ? "故障" : motor.enabled ? "使能" : "未使能"}</span>
                </div>
              ))}
            </div>
          ) : <p>等待 Linux 开发板上传电机或关节状态。当前页只显示数据，不触发真实控制。</p>}
        </article>

        <article>
          <div className={styles.panelHead}>
            <div>
              <span>传感器 / 模型</span>
              <strong>{text(sensorPayload.source, "sensor_state")}</strong>
            </div>
            <small>{latestTime(device, "sensor_state")}</small>
          </div>
          <div className={styles.sensorKeyGrid}>
            {Object.entries(sensorPayload).filter(([key]) => !["schema_version", "device_id", "robot_id"].includes(key)).slice(0, 12).map(([key, value]) => (
              <span key={key}><b>{key}</b>{typeof value === "object" ? JSON.stringify(value).slice(0, 80) : text(value, "-")}</span>
            ))}
            {!Object.keys(sensorPayload).length ? <p>等待设备侧上传传感器、IMU、心率、模型输出或其他机器人开发数据。</p> : null}
          </div>
        </article>

        <article>
          <div className={styles.panelHead}>
            <div>
              <span>摄像头 / 仿真</span>
              <strong>{text(cameraPayload.camera_id, "等待关键帧")}</strong>
            </div>
            <small>{latestTime(device, "camera_keyframe")}</small>
          </div>
          <p>{text(cameraPayload.scene_summary, text(cameraPayload.detection_summary, "开发板摄像头关键帧上传后，这里显示场景摘要和检测结果。"))}</p>
          <p>仿真准备度：{text(simReport.readiness, "未上传")}</p>
          <p>当前数据批次：{publicDataBatchLabel(device.current_session, publicDataBatchLabel(manifest.session_id, "暂无批次"))}</p>
        </article>
      </div>

      <details className={styles.boardManifestDrawer}>
        <summary>开发板能力清单</summary>
        <div className={styles.boardManifestGrid}>
          <article>
            <span>系统</span>
            <strong>{text(board.platform.hostname, text(board.manifest.device_id, deviceId(device)))}</strong>
            <p>{text(board.platform.release, "未上传系统版本")}</p>
          </article>
          <article>
            <span>ROS2</span>
            <strong>{ros2CapabilityText(board.ros2)}</strong>
            <p>{board.ros2.available === true ? "可继续做仿真/采集自检。" : "后续仿真主机需要先补 ROS2 环境。"}</p>
          </article>
          <article>
            <span>CAN</span>
            <strong>{board.canInterfaces.length ? `${board.canInterfaces.length} 个接口` : "未发现"}</strong>
            <p>{board.canInterfaces.slice(0, 3).map(canInterfaceLabel).join(" / ") || "等待板端设备档案或电机状态。"}</p>
          </article>
          <article>
            <span>串口</span>
            <strong>{board.serialDevices.length ? `${board.serialDevices.length} 个设备` : "未发现"}</strong>
            <p>{board.serialDevices.slice(0, 3).join(" / ") || "扫描开发板后显示 ttyUSB/ttyACM 等设备。"}</p>
          </article>
          <article>
            <span>摄像头</span>
            <strong>{board.cameraDevices.length ? `${board.cameraDevices.length} 路` : "未发现"}</strong>
            <p>{board.cameraDevices.slice(0, 3).join(" / ") || "camera_keyframe 可先补最近帧。"}</p>
          </article>
          <article>
            <span>USB</span>
            <strong>{board.usbDevices.length ? `${board.usbDevices.length} 个设备` : "未发现"}</strong>
            <p>{board.usbDevices.slice(0, 2).map(usbDeviceLabel).join(" / ") || "用于确认 USB-CAN、相机或传感器适配器。"}</p>
          </article>
        </div>
        <p>边界：{board.controlBoundary}。这里是只读清单，不代表允许运动，不下发 ROS、CAN 或电机命令。</p>
      </details>
    </section>
  );
}

function DeviceDataTile({
  projectId,
  device,
  index,
  npcSeats,
  defaultNpcId,
  initialTab,
  onClose,
}: {
  projectId: string;
  device: AnyRecord;
  index: number;
  npcSeats: AnyRecord[];
  defaultNpcId: string;
  initialTab: InitialRoboticsTab;
  onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<DeviceTab>(() => initialDeviceTab(initialTab));
  const [stateSyncEnabled, setStateSyncEnabled] = useState(false);
  const [showOpenSourceMesh, setShowOpenSourceMesh] = useState(false);
  const [selectedNpcId, setSelectedNpcId] = useState(defaultNpcId);
  const motors = asArray<AnyRecord>(latestPayload(device, "motor_state").motors);
  const counts = deviceDataCounts(device);
  const variables = deviceVariableRows(device);
  const cameraPayload = latestPayload(device, "camera_keyframe");
  const cameraSrc = keyframeSrc(cameraImageUrl(device));
  const assistantSeat = findSeatRecord(npcSeats, selectedNpcId) ?? npcSeats[0];
  const assistantState = summarizeNpcSeatDispatchState(assistantSeat);
  const assistantSkills = npcSkillNames(assistantSeat);
  const title = deviceTitle(device, index);
  const id = deviceId(device, index);
  return (
    <article className={tileStyles.tile}>
      <header className={tileStyles.head}>
        <div className={tileStyles.headLeft}>
          <strong className={tileStyles.name}>{title}</strong>
          <small className={tileStyles.subline}>{publicDeviceCode(device, index)} · {deviceSafetyText(device)} · {text(device.online_state, "unknown")}</small>
        </div>
        <div className={tileStyles.headActions}>
          <button type="button" className={tileStyles.closeBtn} onClick={onClose} aria-label={`关闭 ${title}`}>×</button>
        </div>
      </header>
      <div className={tileStyles.threadBinding}>
        <span className={tileStyles.threadChip}>开发板数据</span>
        <span className={tileStyles.threadChip}>电机 {counts.motors}</span>
        <span className={tileStyles.threadChip}>传感字段 {counts.sensorFields}</span>
        <span className={tileStyles.threadChip}>{counts.hasCamera ? "有摄像头关键帧" : "等待摄像头"}</span>
        <label className={styles.npcIndexSelect}>
          <span>NPC 资源</span>
          <select value={selectedNpcId} onChange={(event) => setSelectedNpcId(event.target.value)} aria-label={`${title} 选择协助 NPC`}>
            <option value="">自动选择</option>
            {npcSeats.map((seat, seatIndex) => {
              const name = seatName(seat, `NPC ${seatIndex + 1}`);
              return <option key={seatId(seat, name)} value={seatId(seat, name)}>{name}</option>;
            })}
          </select>
        </label>
      </div>
      <nav className={tileStyles.panelTabs} aria-label={`${title} 设备数据功能`}>
        {[
          ["data", "开发板数据", counts.motors + counts.sensorFields],
          ["camera", "摄像头", counts.hasCamera ? 1 : 0],
          ["dataset", "数据标注", dataQualityReady(device) ? 1 : 0],
          ["chart", "图表实验", variables.length],
          ["model", "模型预览", 1],
        ].map(([tab, label, count]) => (
          <button
            key={tab}
            type="button"
            className={tileStyles.panelTab}
            data-active={activeTab === tab ? "1" : "0"}
            onClick={() => setActiveTab(tab as DeviceTab)}
          >
            <span>{label}</span>
            <strong>{count}</strong>
          </button>
        ))}
      </nav>

      {activeTab === "data" ? (
        <DeviceDataOverview device={device} />
      ) : activeTab === "camera" ? (
        <section className={styles.deviceDataPane} aria-label={`${title} 摄像头帧采集`}>
          <div className={styles.cameraWorkbench}>
            <article className={styles.cameraPreviewPanel} data-empty={cameraSrc ? "0" : "1"}>
              <div className={styles.panelHead}>
                <div>
                  <span>摄像头关键帧</span>
                  <strong>{text(cameraPayload.camera_id, counts.hasCamera ? "已接收关键帧" : "等待 camera_keyframe")}</strong>
                </div>
                <small>{latestTime(device, "camera_keyframe")}</small>
              </div>
              {cameraSrc ? (
                <Image
                  src={cameraSrc}
                  alt={`${title} 最新摄像头关键帧`}
                  width={960}
                  height={540}
                  unoptimized
                  className={styles.cameraKeyframeImage}
                />
              ) : (
                <div className={styles.cameraEmptyFrame}>
                  <strong>等待 Linux 开发板上传图像</strong>
                  <p>预配置脚本接入服务器后，设备上传 camera_keyframe，平台会在这里显示最近帧。</p>
                </div>
              )}
            </article>
            <aside className={styles.cameraMetaPanel}>
              <article>
                <span>场景摘要</span>
                <p>{text(cameraPayload.scene_summary, "暂无场景摘要。")}</p>
              </article>
              <article>
                <span>检测结果</span>
                <p>{text(cameraPayload.detection_summary, "暂无检测摘要。")}</p>
              </article>
              <article>
                <span>VLA 上下文</span>
                <p>{text(cameraPayload.vla_context, "预留给高层任务规划；这里不展示也不下发底层电机命令。")}</p>
              </article>
            </aside>
          </div>
        </section>
      ) : activeTab === "dataset" ? (
        <section className={styles.deviceDataPane}>
          <div className={styles.deviceDataSummary}>
            <article data-tone={dataQualityReady(device) ? "ok" : "idle"}>
              <span>标注状态</span>
              <strong>{dataQualityReady(device) ? "可标注" : "待补数据"}</strong>
              <p>{qualityDetailLine(device)}</p>
            </article>
            <article>
              <span>数据来源</span>
              <strong>{publicDataBatchLabel(device.current_session)}</strong>
              <p>电机、传感器、摄像头和安全状态在同一设备编号下汇总，适配任意已接入的 Linux 开发板。</p>
            </article>
          </div>
          <div className={styles.annotationWorkbench}>
            <article className={styles.dataActionPanel}>
              <span>可标注变量</span>
              <strong>{variables.length ? `${variables.length} 个字段` : "等待设备数据"}</strong>
              <div className={styles.variablePills}>
                {variables.slice(0, 24).map((item) => <span key={`${item.source}-${item.name}`}>{item.name}</span>)}
                {!variables.length ? <span>等待电机状态 / 传感器摘要 / 摄像头关键帧</span> : null}
              </div>
            </article>
            <article className={styles.dataActionPanel}>
              <span>人工标签</span>
              <strong>为当前设备片段补充语义</strong>
              <textarea placeholder="例如：空载抬臂、视觉遮挡、传感器噪声、用户确认动作有效" />
              <select defaultValue="manifest">
                <option value="manifest">导出项目清单</option>
                <option value="jsonl">导出 JSONL</option>
                <option value="csv">导出 CSV</option>
              </select>
              <button type="button" disabled={!variables.length}>等待后端导出动作接入</button>
            </article>
            <article className={styles.dataActionPanel}>
              <span>NPC 资源索引</span>
              <strong>{assistantSeat ? seatName(assistantSeat, "协助 NPC") : "等待配置 NPC"}</strong>
              <p>{assistantState.detail}</p>
              <p>{npcKnowledgeLine(assistantSeat)}</p>
              <div className={styles.variablePills}>
                {assistantSkills.length ? assistantSkills.map((skill) => <span key={skill}>{skill}</span>) : <span>等待能力工坊分配 skill</span>}
              </div>
            </article>
          </div>
        </section>
      ) : activeTab === "chart" ? (
        <section className={styles.deviceDataPane}>
          <article className={styles.dataActionPanel}>
            <span>图表实验</span>
            <strong>从设备上报数据直接选变量</strong>
            <p>这里先列出当前值和来源；时间序列缓存接入后，同一批变量会直接进入曲线对比和实验记录。</p>
          </article>
          <article className={styles.dataActionPanel}>
            <span>NPC 资源索引</span>
            <strong>{assistantState.ready ? "可请求曲线分析建议" : assistantState.state}</strong>
            <p>当前选择：{assistantSeat ? seatName(assistantSeat, "协助 NPC") : "未选择"}。这里只索引 NPC 的线程、知识库和 skill，配置仍回到 NPC 工作台/能力工坊维护。</p>
          </article>
          <div className={styles.deviceMotorTable}>
            <div><span>变量</span><span>最近值</span><span>来源</span><span>时间</span></div>
            {variables.slice(0, 18).map((item) => (
              <div key={`${item.source}-${item.name}`}>
                <span>{item.name}</span>
                <span>{item.value}</span>
                <span>{item.source}</span>
                <span>{item.time}</span>
              </div>
            ))}
            {!variables.length ? (
              <div>
                <span>等待变量</span>
                <span>-</span>
                <span>device upload</span>
                <span>无记录</span>
              </div>
            ) : null}
          </div>
        </section>
      ) : (
        <section className={styles.modelWorkbenchPane} aria-label={`${title} 模型预览`}>
          <article className={`${styles.dataActionPanel} ${styles.dataFocusPanel}`}>
            <span>模型与状态预览</span>
            <strong>用电机状态看机器人整体姿态</strong>
            <p>关节颜色表达温度；这里是只读可视化，不发送 ROS 写操作，也不下发任何硬件动作。</p>
            <div className={styles.syncToolbar} aria-label="状态数据同步控制">
              <button type="button" onClick={() => setStateSyncEnabled(true)}>开始数据同步</button>
              <button type="button" onClick={() => setStateSyncEnabled(false)}>关闭数据同步</button>
              <button type="button" onClick={() => setShowOpenSourceMesh((value) => !value)}>
                {showOpenSourceMesh ? "隐藏开源 mesh" : "加载开源 mesh"}
              </button>
            </div>
            <MotorState3DViewer
              motors={motors}
              sourceLine={latestMotorStateLine(device, motors)}
              syncEnabled={stateSyncEnabled}
              showOpenSourceMesh={showOpenSourceMesh}
            />
            <ModelImportInspector />
          </article>
          <aside className={styles.dataDrawerRail} aria-label="模型预览说明">
            <details className={styles.workbenchDrawer} open>
              <summary><span>状态映射</span><strong>{motors.length ? `${motors.length} 个电机` : "等待电机状态"}</strong></summary>
              <article className={styles.dataActionPanel}>
                <p>position 映射姿态，temperature 映射关节颜色。真实运动仍由本地规划、Linux 开发板和底层安全控制器负责。</p>
              </article>
            </details>
            <details className={styles.workbenchDrawer}>
              <summary><span>开源 mesh</span><strong>RobotExpressive.glb / CC0</strong></summary>
              <article className={styles.dataActionPanel}>
                <p>开源 mesh 只用于验证 GLB 加载链路，不是正式机械臂 CAD。</p>
              </article>
            </details>
          </aside>
        </section>
      )}
    </article>
  );
}

function artifactDownloadHref(projectId: string, artifactPath: string) {
  const params = new URLSearchParams({ path: artifactPath });
  return apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/artifacts/download?${params.toString()}`);
}

function ArtifactPathActions({ projectId, artifactPath, label = "下载" }: { projectId: string; artifactPath: string; label?: string }) {
  if (!artifactPath) return null;
  return (
    <span className={styles.artifactActions}>
      <span>采集证据已生成</span>
      <a href={artifactDownloadHref(projectId, artifactPath)} download>
        {label}
      </a>
    </span>
  );
}

function qualitySession(device: AnyRecord) {
  return record(record(device.data_quality).latest_session);
}

function qualityReady(device: AnyRecord) {
  return record(device.data_quality).annotation_ready === true;
}

function qualityStatusText(device: AnyRecord) {
  if (qualityReady(device)) return "可标注";
  const reasons = record(device.data_quality).blocking_reasons;
  if (Array.isArray(reasons) && reasons.length) return "需补数据";
  return "等待数据";
}

function qualityDetailLine(device: AnyRecord) {
  const session = qualitySession(device);
  const criteria = record(session.quality_criteria);
  const reasons = Array.isArray(record(device.data_quality).blocking_reasons)
    ? (record(device.data_quality).blocking_reasons as unknown[]).map((item) => text(item)).filter(Boolean)
    : [];
  if (reasons.length) return `阻塞：${reasons.slice(0, 2).join("；")}`;
  if (qualityReady(device)) {
    return `数据批次 ${publicDataBatchLabel(session.session_id, "-")} 已通过：运动关节 ${text(session.moving_joint_count, "0")}，电机条目 ${text(session.motor_entry_count_min, "0")}~${text(session.motor_entry_count_max, "0")}，阈值 ${text(criteria.min_moving_joints, "0")} 个运动关节。`;
  }
  return "上传设备质量摘要后，这里会显示质量门和标注入口状态。";
}

function DeviceQualityStrip({ devices }: { devices: AnyRecord[] }) {
  const visibleDevices = devices.slice(0, 4);
  const readyCount = devices.filter(qualityReady).length;
  const headline = devices.length ? `${readyCount}/${devices.length} 台设备可标注` : "等待设备上传数据";
  const latestReady = devices.find(qualityReady) ?? devices[0];
  const latestLine = latestReady ? qualityDetailLine(latestReady) : "上传质量报告后显示最近一次采集结果。";
  return (
    <section className={styles.qualityStrip} aria-label="设备数据质量状态">
      <div className={styles.qualityStripHead}>
        <div>
          <span>数据质量门</span>
          <strong>{headline}</strong>
        </div>
        <small>{latestLine}</small>
      </div>
      <details className={styles.compactDrawer}>
        <summary>查看设备详情</summary>
        <div className={styles.qualityCards}>
          {visibleDevices.length ? visibleDevices.map((device) => {
            const session = qualitySession(device);
            return (
              <article key={text(device.device_id, text(session.session_id, "device"))} data-ready={qualityReady(device) ? "true" : "false"}>
                <span>{qualityStatusText(device)}</span>
                <strong>{deviceTitle(device)}</strong>
                <p>{publicDeviceCode(device)} · {qualityDetailLine(device)}</p>
              </article>
            );
          }) : (
            <article data-ready="false">
              <span>等待数据</span>
              <strong>还没有可评估的采集批次</strong>
              <p>先从设备侧上传质量报告和设备档案，再进入标注和导出。</p>
            </article>
          )}
        </div>
      </details>
      <em>只读数据状态，不代表允许运动，也不下发 CAN 或电机命令。</em>
    </section>
  );
}

function deviceHasBusData(device: AnyRecord) {
  const manifest = record(device.manifest);
  const interfaces = asArray<AnyRecord>(manifest.interfaces);
  const interfaceKinds = interfaces.map((item) => text(item.kind ?? item.type ?? item.transport).toLowerCase());
  const board = boardCapabilities(device);
  return interfaceKinds.some((kind) => kind.includes("can") || kind.includes("serial") || kind.includes("usb"))
    || board.canInterfaces.length > 0
    || board.serialDevices.length > 0
    || board.usbDevices.length > 0
    || asArray(latestPayload(device, "motor_state").motors).length > 0
    || Object.keys(latestPayload(device, "sensor_state")).length > 0;
}

function AccessCheckPanel({
  devices,
  computerCount,
  readyComputers,
  queueableComputers,
  scannedInterfaceCount,
  workbenchMode,
  projectId,
  openFirstDevice,
}: {
  devices: AnyRecord[];
  computerCount: number;
  readyComputers: number;
  queueableComputers: number;
  scannedInterfaceCount: number;
  workbenchMode: DeviceWorkbenchMode;
  projectId: string;
  openFirstDevice: () => void;
}) {
  const latestDevice = devices[0];
  const latestBoard = latestDevice ? boardCapabilities(latestDevice) : null;
  const reports = devices.map(simulationReport).filter((report) => Object.keys(report).length > 0);
  const cameraCount = devices.filter((device) => deviceDataCounts(device).hasCamera).length;
  const busReadyCount = devices.filter(deviceHasBusData).length;
  const rosReadyCount = reports.filter((report) => text(report.readiness, "").startsWith("ready_")).length;
  const checks = [
    {
      label: "开发板",
      value: devices.length ? `${devices.length} 台` : "未接入",
      detail: latestDevice ? `${deviceTitle(latestDevice)} · ${text(latestDevice.online_state, "unknown")}` : "先运行开发板接入脚本或扫描 runner。",
      ready: devices.length > 0,
    },
    {
      label: "接单窗口",
      value: readyComputers ? `${readyComputers} 可运行` : queueableComputers ? `${queueableComputers} 可排队` : "未就绪",
      detail: computerCount ? `${computerCount} 台电脑在线记录；扫描到 ${scannedInterfaceCount} 个接口。` : "服务器还没有可用 runner。",
      ready: readyComputers + queueableComputers > 0,
    },
    {
      label: "ROS/仿真",
      value: reports.length ? `${rosReadyCount}/${reports.length}` : "无报告",
      detail: reports.length ? `最近 readiness: ${text(reports[0].readiness, "unknown")}` : "运行仿真环境自检并上传报告后显示。",
      ready: rosReadyCount > 0,
    },
    {
      label: "摄像头",
      value: cameraCount ? `${cameraCount} 路` : "无关键帧",
      detail: cameraCount ? "可进入开发板标签查看最近帧。" : "camera_keyframe 上传后进入 VLA/标注上下文。",
      ready: cameraCount > 0,
    },
    {
      label: "CAN/串口",
      value: busReadyCount ? `${busReadyCount} 台有数据` : "无数据",
      detail: "来自设备档案、电机状态或传感器摘要，只读检查。",
      ready: busReadyCount > 0,
    },
    {
      label: "最近上传",
      value: latestDevice ? latestDeviceUploadTime(latestDevice) : "无记录",
      detail: latestDevice ? text(deviceId(latestDevice), "device") : "等待设备首次同步。",
      ready: Boolean(latestDevice),
    },
  ];
  const setupSteps = [
    { label: "1. 注册设备", detail: "上传设备编号、机器人名称、主机名、在线状态和能力档案。" },
    { label: "2. 扫描接口", detail: "报告 CAN、串口、USB、摄像头、ROS2 环境和 runner 可执行能力。" },
    { label: "3. 上传只读数据", detail: "按需上传电机状态、传感器摘要、摄像头关键帧和仿真准备度。" },
    { label: "4. 进入采集/标注", detail: "确认安全边界后再开启数据同步、质量门、标注和图表实验。" },
  ];
  return (
    <section className={styles.accessCheckPanel} aria-label="Linux 开发板接入检查">
      <div className={styles.accessCheckHead}>
        <div>
          <span>接入检查</span>
          <strong>{workbenchMode === "boards" ? "先确认数据链路，再开始采集或标注" : "先扫描接口，再创建调试窗口"}</strong>
          <small>这个面板只读：它帮助判断下一步做什么，不代表允许真机运动。</small>
        </div>
        <div className={styles.accessActions}>
          <form action={请求串口USB扫描.bind(null, projectId)}>
            <input type="hidden" name="return_to" value={`/projects/${projectId}/robotics`} />
            <input type="hidden" name="computer_node_id" value="all" />
            <button type="submit" disabled={!computerCount}>
              {workbenchMode === "boards" ? "扫描开发板/runner" : "扫描真实接口"}
            </button>
          </form>
          {devices[0] ? <button type="button" onClick={openFirstDevice}>打开最近开发板</button> : <span>等待设备上传</span>}
        </div>
      </div>
      <div className={styles.accessCheckGrid}>
        {checks.map((item) => (
          <article key={item.label} data-ready={item.ready ? "true" : "false"}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            <p>{item.detail}</p>
          </article>
        ))}
      </div>
      <details className={styles.accessSetupDrawer}>
        <summary>开发板接入脚本清单</summary>
        <div className={styles.accessSetupGrid}>
          {setupSteps.map((step) => (
            <article key={step.label}>
              <strong>{step.label}</strong>
              <p>{step.detail}</p>
            </article>
          ))}
        </div>
        <p>平台只索引和展示这些数据；控制命令必须由具体机器人项目自己的安全链路决定。</p>
      </details>
      <details className={styles.accessSetupDrawer}>
        <summary>最近开发板能力清单</summary>
        <div className={styles.boardManifestGrid}>
          <article>
            <span>系统</span>
            <strong>{latestBoard ? text(latestBoard.platform.hostname, text(latestBoard.manifest.device_id, deviceId(latestDevice))) : "等待开发板"}</strong>
            <p>{latestBoard ? text(latestBoard.platform.release, "未上传系统版本") : "运行开发板扫描并上传后显示。"}</p>
          </article>
          <article>
            <span>ROS2</span>
            <strong>{latestBoard ? ros2CapabilityText(latestBoard.ros2) : "未知"}</strong>
            <p>用于判断仿真、采集和标注前置环境。</p>
          </article>
          <article>
            <span>CAN/串口/USB/摄像头</span>
            <strong>{latestBoard ? `${latestBoard.canInterfaces.length}/${latestBoard.serialDevices.length}/${latestBoard.usbDevices.length}/${latestBoard.cameraDevices.length}` : "0/0/0/0"}</strong>
            <p>{latestBoard ? "按 CAN、串口、USB、摄像头顺序统计。" : "先接入 Linux 开发板能力清单。"}</p>
          </article>
        </div>
        <p>这里只展示只读能力，不能作为运动许可；真实运动仍必须由机器人项目自己的安全链路裁决。</p>
      </details>
    </section>
  );
}

function simulationReport(device: AnyRecord) {
  return record(record(record(device.simulation_readiness).payload).report);
}

function simulationTopicRows(report: AnyRecord) {
  const contract = record(report.topic_contract);
  const entries: Array<[string, AnyRecord]> = [
    ["轨迹输入", record(contract.trajectory_command)],
    ["关节状态", record(contract.joint_state)],
    ["安全状态", record(contract.safety_state)],
    ["传感器状态", record(contract.sensor_state)],
    ["VLA 任务", record(contract.vla_task_goal)],
  ];
  return entries
    .map(([label, item]) => ({
      label: String(label),
      topic: text(item.topic),
      messageType: text(item.message_type),
      direction: text(item.direction),
    }))
    .filter((item) => item.topic || item.messageType || item.direction);
}

function SimulationReadinessStrip({ devices }: { devices: AnyRecord[] }) {
  const reports = devices.map(simulationReport).filter((report) => Object.keys(report).length > 0);
  const readyReports = reports.filter((report) => text(report.readiness, "").startsWith("ready_"));
  const latest = reports[0] ?? {};
  const topicRows = simulationTopicRows(latest);
  const topicBoundary = text(record(latest.topic_contract).control_boundary, "simulation_topic_contract_not_motion_permission");
  const headline = reports.length
    ? `${readyReports.length}/${reports.length} 份仿真环境报告可用`
    : "等待仿真主机上传自检报告";
  const latestLine = reports.length
    ? `最近状态：${text(latest.readiness, "unknown")}；关节合同 ${text(record(latest.joint_contract).count, "0")} 个。`
    : "先在 Linux 仿真主机运行 check_sim_env --output，再上传到设备数据链路。";
  const steps = [
    {
      state: "先检查",
      title: "模型可导入",
      detail: "导入 URDF/结构文件，确认关节、父子关系和 limit，再进入仿真或回放。",
    },
    {
      state: "再运行",
      title: "仿真环境自检",
      detail: "在设备侧或仿真主机运行环境自检，区分 ROS、MuJoCo、模型文件和采集工具问题。",
    },
    {
      state: "最后采集",
      title: "数据闭环可标注",
      detail: "采集 joint state、传感、图像和质量报告，通过数据质量门后再进入标注和训练。",
    },
  ];
  return (
    <section className={styles.simReadinessStrip} aria-label="仿真与采集准备度">
      <div className={styles.simReadinessHead}>
        <div>
          <span>仿真准备度</span>
          <strong>{headline}</strong>
        </div>
        <small>{latestLine} 这是只读研发流程提示，不是运动许可，也不会触发真实设备动作。</small>
      </div>
      <details className={styles.compactDrawer}>
        <summary>查看推荐流程</summary>
        <div className={styles.simReadinessCards}>
          {steps.map((step) => (
            <article key={step.title}>
              <span>{step.state}</span>
              <strong>{step.title}</strong>
              <p>{step.detail}</p>
            </article>
          ))}
          {reports.slice(0, 3).map((report, index) => (
            <article key={`${text(report.readiness, "report")}-${index}`}>
              <span>{text(report.readiness, "unknown")}</span>
              <strong>{text(report.schema_version, "sim readiness report")}</strong>
              <p>{text(report.safety_note, "只读仿真环境自检，不进入真实控制链路。")}</p>
            </article>
          ))}
        </div>
      </details>
      <details className={styles.compactDrawer}>
        <summary>查看 ROS topic 合同</summary>
        {topicRows.length ? (
          <div className={styles.topicContractTable}>
            <div><span>用途</span><span>Topic</span><span>消息</span><span>方向</span></div>
            {topicRows.map((row) => (
              <div key={row.label}>
                <span>{row.label}</span>
                <code>{row.topic || "-"}</code>
                <span>{row.messageType || "-"}</span>
                <span>{row.direction || "-"}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className={styles.topicContractEmpty}>等待新版 check_sim_env 上传 topic_contract；旧报告仍可判断 readiness，但还不能在平台核对 topic 合同。</p>
        )}
        <p className={styles.topicContractNote}>边界：{topicBoundary}。这只是接口清单，不代表 topic 正在运行，也不会下发 ROS、CAN 或电机命令。</p>
      </details>
    </section>
  );
}

function seatId(seat: AnyRecord, fallback: string) {
  return text(seat.id ?? seat.config_id ?? seat.configId ?? seat.row_id ?? seat.name, fallback);
}

function seatName(seat: AnyRecord, fallback: string) {
  return publicNpcLabel(seat.name ?? seat.label ?? seat.display_name ?? fallback);
}

function publicNpcLabel(value: unknown) {
  const raw = userFacingTerminalText(value);
  const platformMatch = raw.match(/^platform-npc-(\d+)$/i);
  if (platformMatch) return `${platformMatch[1]}号 NPC`;
  const npcMatch = raw.match(/^npc[-_\s]*(\d+)$/i);
  if (npcMatch) return `${npcMatch[1]}号 NPC`;
  return raw;
}

function findSeatRecord(seats: AnyRecord[], value: string) {
  const target = text(value, "");
  if (!target) return undefined;
  return seats.find((seat) => seatId(seat, "") === target || seatName(seat, "") === target);
}

function seatProviderId(seat: AnyRecord | undefined) {
  if (!seat) return "";
  return text(
    seat.provider_id
      ?? seat.providerId
      ?? seat.adapter_provider
      ?? seat.adapterProvider
      ?? seat.thread_provider
      ?? seat.threadProvider,
    "",
  );
}

function seatComputerNodeId(seat: AnyRecord | undefined) {
  if (!seat) return "";
  return text(
    seat.computer_node_id
      ?? seat.computerNodeId
      ?? seat.bound_computer_node_id
      ?? seat.boundComputerNodeId
      ?? seat.workstation_computer_node_id
      ?? seat.workstationComputerNodeId,
    "",
  );
}

function seatThreadId(seat: AnyRecord | undefined) {
  if (!seat) return "";
  return text(
    seat.source_thread_id
      ?? seat.sourceThreadId
      ?? seat.thread_id
      ?? seat.threadId
      ?? seat.bound_thread_id
      ?? seat.boundThreadId,
    "",
  );
}

function npcSkillNames(seat: AnyRecord | undefined) {
  if (!seat) return [];
  const meta = record(seat.metadata);
  const extra = record(seat.extra_data ?? seat.extraData);
  const raw = seat.skill_loadout ?? seat.skillLoadout ?? meta.skill_loadout ?? extra.skill_loadout ?? seat.skills ?? meta.skills ?? [];
  return asArray<unknown>(raw)
    .map((item) => typeof item === "string" ? item : text(record(item).name ?? record(item).id ?? record(item).label, ""))
    .filter(Boolean)
    .slice(0, 6);
}

function npcKnowledgeLine(seat: AnyRecord | undefined) {
  if (!seat) return "未选择 NPC";
  const meta = record(seat.metadata);
  const extra = record(seat.extra_data ?? seat.extraData);
  return text(
    seat.knowledge_summary
      ?? seat.knowledgeSummary
      ?? meta.knowledge_summary
      ?? meta.knowledgeSummary
      ?? extra.knowledge_summary
      ?? extra.knowledgeSummary
      ?? seat.knowledge_path
      ?? seat.knowledgePath
      ?? meta.knowledge_path
      ?? extra.knowledge_path,
    "未索引知识库摘要",
  );
}

function summarizeNpcSeatDispatchState(seat: AnyRecord | undefined) {
  if (!seat) {
    return {
      ready: false,
      state: "先选择协助 NPC",
      detail: "先绑定负责这个调试窗口的 NPC，再发起预标注、图表分析或代操作确认。",
    };
  }
  if (!seatProviderId(seat)) {
    return {
      ready: false,
      state: "待选择执行通道",
      detail: "这个 NPC 还没选择执行通道，先去 NPC 工作台补齐接单方式。",
    };
  }
  if (!seatComputerNodeId(seat)) {
    return {
      ready: false,
      state: "待绑定电脑",
      detail: "这个 NPC 还没绑定目标电脑，协作请求暂时无法落到固定设备。",
    };
  }
  if (!seatThreadId(seat)) {
    return {
      ready: false,
      state: "待绑定线程",
      detail: "这个 NPC 还没绑定桌面线程，先扫描并绑定线程再继续协作请求。",
    };
  }
  return {
    ready: true,
    state: "协助 NPC 已就绪",
    detail: "这个 NPC 已具备执行通道、电脑和线程绑定，可以承接当前调试窗口的协作请求。",
  };
}

function commandText(message: AnyRecord) {
  const extra = record(message.extra_data ?? message.metadata);
  const fromMeta = text(extra.terminal_command, "");
  if (fromMeta) return fromMeta;
  const mode = text(extra.terminal_mode, "");
  if (mode === "capture_start") return `开始采集 ${text(extra.capture_sample_hz, "100")}Hz`;
  if (mode === "capture_stop") return "停止采集并生成片段";
  const body = text(message.body, "");
  try {
    const payload = JSON.parse(body) as AnyRecord;
    const kind = text(payload.kind, "");
    if (kind === "robotics.capture.start") return `开始采集 ${text(payload.sample_hz, "100")}Hz`;
    if (kind === "robotics.capture.stop") return "停止采集并生成片段";
  } catch {}
  const match = body.match(/只读命令：(.+)/);
  return match?.[1]?.trim() || body.split("\n").find((line) => line.includes("listen")) || "只读调试命令";
}

function userFacingTerminalText(value: unknown) {
  return text(value, "")
    .replace(/\bRunner\b/g, "接单窗口")
    .replace(/\brunner\b/g, "接单窗口")
    .replace(/\badapters?\b/gi, "接入通道")
    .replace(/\bbridges?\b/gi, "同步通道")
    .replace(/\bsession JSONL\b/gi, "线程记录")
    .replace(/\blocal path\b/gi, "当前电脑工作副本")
    .replace(/\bsource_thread\b/gi, "协作记录")
    .replace(/\bcanonical\b/gi, "协作记录")
    .replace(/\brequested id\b/gi, "协作记录")
    .replace(/\braw UUID\b/gi, "协作记录")
    .replace(/最小回执/g, "已收到提醒");
}

function publicTerminalStatus(status: unknown) {
  switch (text(status, "open")) {
    case "completed":
    case "done":
    case "success":
      return "已完成";
    case "failed":
    case "error":
      return "失败";
    case "running":
    case "in_progress":
      return "执行中";
    case "queued":
    case "pending":
      return "已排队";
    case "acked":
      return "已接单";
    case "cancelled":
      return "已取消";
    default:
      return text(status, "已记录");
  }
}

function publicTerminalEventPrefix(kind: string, status: unknown) {
  const label = publicTerminalStatus(status);
  if (kind === "ack") return "执行电脑回执";
  if (kind === "result") return `执行结果 · ${label}`;
  if (kind === "capture") return `采集回执 · ${label}`;
  if (kind === "review") return `NPC 代操作 · ${label}`;
  return `事件 · ${label}`;
}

function roboticsCaptureAckLine(value: unknown) {
  const raw = text(value, "");
  if (!/robotics\.capture|device capture|capture_id|preview_summary/.test(raw)) return "";
  const jsonMatch = raw.match(/```json\s*([\s\S]*?)```/) ?? raw.match(/({[\s\S]*})/);
  if (!jsonMatch?.[1]) return "采集回执已返回";
  try {
    const payload = JSON.parse(jsonMatch[1]) as AnyRecord;
    const sampleCount = text(payload.sample_count, "0");
    const byteCount = text(payload.byte_count, "0");
    const error = text(payload.error, "");
    const sync = record(payload.repo_sync);
    const cache = record(payload.local_cache);
    const syncStatus = text(sync.status, "");
    const syncLine = captureSyncStatusLabel(syncStatus);
    const cacheLine = captureCacheStatusLabel(text(cache.status, ""));
    const parts = [`采集回执：${sampleCount} 个样本`];
    if (byteCount && byteCount !== "0") parts.push(`${byteCount} bytes`);
    if (payload.preview) parts.push("预览文件已生成");
    if (syncLine) parts.push(syncLine);
    if (cacheLine) parts.push(cacheLine);
    if (error) parts.push(`提示：${userFacingTerminalText(error)}`);
    return parts.join(" · ");
  } catch {
    return "采集回执已返回";
  }
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
    if (tile.runnerCanDispatch) {
      return ["[terminal] 暂无输入输出。用户自己输入会直接排队到执行电脑；NPC 代操作会先显示待确认。"];
    }
    if (tile.runnerCanQueue) {
      return ["[terminal] 执行电脑暂不可立即接单。用户命令会进入队列，等目标电脑恢复后再处理；NPC 代操作仍需先确认。"];
    }
    return ["[terminal] 执行电脑未处于可排队状态。先重连接单窗口，再提交用户终端命令或 NPC 代操作确认。"];
  }
  return related.map((message) => {
    const type = text(message.message_type ?? message.messageType, "event");
    const status = text(message.status, "open");
    const extra = record(message.extra_data ?? message.metadata);
    if (type === "runner_command") return `$ ${commandText(message)}  # ${publicTerminalStatus(status)}`;
    if (type === "runner_ack") return `[${publicTerminalEventPrefix("ack", status)}] ${roboticsCaptureAckLine(message.body) || userFacingTerminalText(message.body) || "执行电脑已接单"}`;
    if (type === "runner_result") {
      const result = record(extra.runner_result);
      const captureId = text(result.capture_id ?? extra.capture_id, "");
      if (captureId) {
        const mode = text(result.kind ?? extra.terminal_mode, "");
        const resultStatus = text(result.status, text(result.capture_mode, status));
        const sampleCount = text(result.sample_count, "");
        if (mode === "robotics.capture.start" || text(extra.terminal_mode, "") === "capture_start") {
          return `[${publicTerminalEventPrefix("capture", "running")}] 目标电脑已开始后台采集`;
        }
        if (sampleCount && sampleCount !== "0") {
          return `[${publicTerminalEventPrefix("capture", "done")}] 已收到 ${sampleCount} 个样本`;
        }
        return `[${publicTerminalEventPrefix("capture", resultStatus)}] ${text(result.error, "执行电脑已返回采集回执")}`;
      }
      return `[${publicTerminalEventPrefix("result", status)}] ${userFacingTerminalText(message.body) || "执行电脑已返回结果"}`;
    }
    if (type === "robotics_capture_start") return `[${publicTerminalEventPrefix("capture", "running")}] ${text(message.title, "开始采集")}`;
    if (type === "robotics_capture_segment") return `[${publicTerminalEventPrefix("capture", "done")}] ${text(message.title, "采集片段")} 已生成`;
    if (type === "robotics_terminal_review" || type === "robotics_terminal_npc_request") return `[${publicTerminalEventPrefix("review", status)}] ${commandText(message)}`;
    return `[${publicTerminalEventPrefix("event", status)}] ${text(message.title ?? message.body, "终端事件")}`;
  });
}

function captureSegments(tile: DebugWindow, messages: AnyRecord[]) {
  const runnerResults = new Map<string, AnyRecord>();
  const resultScore = (result: AnyRecord) => {
    const points = record(record(result).preview_points);
    const summary = record(record(result).preview_summary);
    return (Number(result.sample_count) || 0)
      + Object.keys(record(points.series)).length * 1000
      + Object.keys(record(summary.numeric_fields)).length * 100
      + (text(result.kind, "") === "robotics.capture.stop" ? 10 : 0);
  };
  for (const message of messages) {
    const extra = record(message.extra_data ?? message.metadata);
    if (text(message.message_type ?? message.messageType, "") !== "runner_result") continue;
    const belongsToTile = text(extra.terminal_interface_id, "") === tile.id
      || text(extra.source_message_id, "") && messages.some((source) => source.id === extra.source_message_id && text(record(source.extra_data ?? source.metadata).terminal_interface_id, "") === tile.id);
    if (!belongsToTile) continue;
    const result = record(extra.runner_result);
    const captureId = text(result.capture_id ?? extra.capture_id, "");
    if (captureId) {
      const previous = runnerResults.get(captureId);
      if (!previous || resultScore(result) >= resultScore(previous)) runnerResults.set(captureId, result);
    }
  }
  return messages
    .filter((message) => {
      const extra = record(message.extra_data ?? message.metadata);
      return text(message.message_type ?? message.messageType, "") === "robotics_capture_segment"
        && text(extra.terminal_interface_id, "") === tile.id;
    })
    .map((message, index) => {
      const extra = record(message.extra_data ?? message.metadata);
      const channels = Array.isArray(extra.capture_channels) ? extra.capture_channels.map((item) => text(item, "")).filter(Boolean) : [];
      return {
        id: text(extra.capture_id, text(message.id, `capture-${index + 1}`)),
        title: text(message.title, `采集片段 ${index + 1}`),
        artifactPath: text(extra.artifact_path, ""),
        sampleHz: text(extra.capture_sample_hz, "100"),
        channels: channels.length ? channels : ["time", "signal.value", "status.code"],
        createdAt: text(message.created_at ?? message.createdAt ?? extra.stopped_at, ""),
        runnerResult: runnerResults.get(text(extra.capture_id, "")) || {},
      };
    })
    .reverse();
}

function tileEvents(tile: DebugWindow, messages: AnyRecord[], types: string[]) {
  return messages
    .filter((message) => {
      const extra = record(message.extra_data ?? message.metadata);
      return types.includes(text(message.message_type ?? message.messageType, ""))
        && text(extra.terminal_interface_id, "") === tile.id;
    })
    .slice(0, 6);
}

function segmentVariables(segments: ReturnType<typeof captureSegments>) {
  const values = new Set<string>();
  for (const segment of segments) {
    for (const channel of segment.channels) {
      values.add(channel);
    }
    const summary = record(record(segment.runnerResult).preview_summary);
    const numericFields = record(summary.numeric_fields);
    Object.keys(numericFields).forEach((name) => values.add(name));
    const previewPoints = record(record(segment.runnerResult).preview_points);
    const series = record(previewPoints.series);
    Object.keys(series).forEach((name) => values.add(name));
  }
  if (!values.size) {
    ["time", "signal.value", "status.code", "event.count"].forEach((item) => values.add(item));
  }
  return Array.from(values);
}

function captureSyncStatusLabel(status: string) {
  if (status === "pushed") return "已推送到仓库";
  if (status === "committed") return "已写入仓库证据";
  if (status === "unchanged") return "仓库证据已存在";
  if (status === "waiting_for_repo") return "等待配置仓库同步";
  if (status === "repo_missing") return "设备数据仓库不可用";
  if (status === "not_git_repo") return "设备数据仓库未初始化";
  if (status === "copy_failed") return "写入仓库失败";
  if (status === "git_add_failed" || status === "git_commit_failed") return "仓库登记失败";
  if (status === "push_failed") return "已本地提交，等待重试推送";
  return "";
}

function captureCacheStatusLabel(status: string) {
  if (status === "cleaned" || status === "already_clean") return "本机临时缓存已清理";
  if (status === "kept_for_retry") return "本机保留待同步缓存";
  if (status === "cleanup_failed") return "本机缓存待人工清理";
  return "";
}

function captureResultLine(segment: ReturnType<typeof captureSegments>[number]) {
  const result = record(segment.runnerResult);
  const sampleCount = text(result.sample_count, "");
  const byteCount = text(result.byte_count, "");
  const sync = record(result.repo_sync);
  const cache = record(result.local_cache);
  const preview = text(sync.preview, text(result.preview, ""));
  const syncStatus = text(sync.status, "");
  const error = text(result.error, "");
  const statusParts = [captureSyncStatusLabel(syncStatus), captureCacheStatusLabel(text(cache.status, ""))].filter(Boolean);
  const syncTail = statusParts.length ? ` · ${statusParts.join(" · ")}` : "";
  if (sampleCount && sampleCount !== "0") {
    return `已回传 ${sampleCount} 个样本${byteCount ? ` / ${byteCount} bytes` : ""}${preview ? " · 预览文件已生成" : ""}${syncTail}`;
  }
  if (preview) return `预览文件已生成${syncTail}`;
  if (syncTail) return syncTail.replace(/^ · /, "");
  if (error) return `采集回执：${error}`;
  return "";
}

function captureSummaryLine(segment: ReturnType<typeof captureSegments>[number]) {
  const summary = record(record(segment.runnerResult).preview_summary);
  const fields = record(summary.numeric_fields);
  const names = Object.keys(fields).slice(0, 3);
  if (!names.length) return "";
  return names.map((name) => {
    const stats = record(fields[name]);
    const min = text(stats.min, "");
    const max = text(stats.max, "");
    const mean = text(stats.mean, "");
    return `${name}: ${min}~${max}${mean ? ` / 均值 ${Number(mean).toFixed(3)}` : ""}`;
  }).join("；");
}

function captureTrainingRowLine(segment: ReturnType<typeof captureSegments>[number], variables: string[]) {
  const summary = record(record(segment.runnerResult).preview_summary);
  const fields = record(summary.numeric_fields);
  const selected = variables.filter((variable) => fields[variable]).slice(0, 3);
  if (!selected.length) return "";
  const count = selected.reduce((total, variable) => total + (Number(record(fields[variable]).count) || 0), 0);
  return `可导出 ${selected.join(" / ")} 的 count/min/max/mean 轻量训练行${count ? `，覆盖 ${count} 个样本统计` : ""}`;
}

function capturePreviewSeries(segment: ReturnType<typeof captureSegments>[number]) {
  const points = record(record(segment.runnerResult).preview_points);
  const series = record(points.series);
  return Object.entries(series)
    .map(([name, rawPoints]) => {
      const values = Array.isArray(rawPoints)
        ? rawPoints
            .map((point) => {
              const next = record(point);
              const x = Number(next.x);
              const y = Number(next.y);
              return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
            })
            .filter(Boolean) as { x: number; y: number }[]
        : [];
      return { name, values };
    })
    .filter((item) => item.values.length >= 2)
    .slice(0, 4);
}

function ChartPreview({ segment, targetValue }: { segment: ReturnType<typeof captureSegments>[number]; targetValue?: string }) {
  const series = capturePreviewSeries(segment);
  const target = Number(String(targetValue ?? "").trim());
  const hasTarget = Number.isFinite(target);
  if (!series.length) {
    return (
      <div className={styles.waveformPanel} data-empty="1">
        <strong>{segment.title}</strong>
        <span>等待低频预览点，先显示样本摘要</span>
        {captureSummaryLine(segment) ? <small>{captureSummaryLine(segment)}</small> : null}
      </div>
    );
  }
  const all = series.flatMap((item) => item.values);
  const minX = Math.min(...all.map((item) => item.x));
  const maxX = Math.max(...all.map((item) => item.x));
  const yValues = all.map((item) => item.y).concat(hasTarget ? [target] : []);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);
  const width = 320;
  const height = 150;
  const pad = 14;
  const sx = (x: number) => pad + ((x - minX) / Math.max(maxX - minX, 1)) * (width - pad * 2);
  const sy = (y: number) => height - pad - ((y - minY) / Math.max(maxY - minY, 1)) * (height - pad * 2);
  const targetY = hasTarget ? sy(target) : 0;
  return (
    <div className={styles.waveformPanel}>
      <div className={styles.waveformHead}>
        <strong>{segment.title}</strong>
        <small>{series.map((item) => item.name).join(" / ")}</small>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${segment.title} 预览波形`}>
        <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} />
        <line x1={pad} y1={pad} x2={pad} y2={height - pad} />
        {hasTarget ? <line className={styles.targetLine} x1={pad} y1={targetY} x2={width - pad} y2={targetY} /> : null}
        {series.map((item, index) => (
          <polyline
            key={item.name}
            className={styles[`waveLine${index + 1}` as keyof typeof styles] || styles.waveLine1}
            points={item.values.map((point) => `${sx(point.x).toFixed(1)},${sy(point.y).toFixed(1)}`).join(" ")}
          />
        ))}
      </svg>
      <small>{minY.toFixed(3)} ~ {maxY.toFixed(3)}{hasTarget ? ` · 目标 ${targetValue}` : ""}</small>
    </div>
  );
}

function HiddenTileFields({
  tile,
  returnTo,
  boundNpcId,
  boundNpcLabel,
}: {
  tile: DebugWindow;
  returnTo: string;
  boundNpcId: string;
  boundNpcLabel: string;
}) {
  return (
    <>
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
      <input type="hidden" name="interface_id" value={tile.id} />
      <input type="hidden" name="runner_interface_id" value={tile.runnerInterfaceId || tile.id} />
      <input type="hidden" name="interface_name" value={tile.name} />
      <input type="hidden" name="interface_kind" value={tile.kindLabel} />
      <input type="hidden" name="bound_npc" value={boundNpcId} />
      <input type="hidden" name="bound_npc_label" value={boundNpcLabel} />
    </>
  );
}

function terminalLines(tile: DebugWindow, boundNpcLabel: string) {
  const dispatchMode = tile.runnerCanDispatch ? "可接单" : tile.runnerCanQueue ? "排队等恢复" : "暂停提交";
  const sampleHz = text(tile.sampleHz, "100");
  const baudRate = text(tile.baudRate, "115200");
  const lines = [
    `$ open ${tile.name}`,
    `接口=${tile.kindLabel}  电脑=${tile.computerLabel}`,
    `状态=${tile.statusLabel}  模式=用户终端`,
    `接单=${dispatchMode}  电脑状态=${tile.computerState}`,
    `读取=${tile.readCapability ? "可用" : "不可用"}  写入=${tile.writeCapabilityLabel}`,
    `协助NPC=${publicNpcLabel(boundNpcLabel || tile.boundNpc) || "未绑定，创建或设置时选择 NPC"}`,
  ];
  if (tile.kind === "can") {
    lines.push(`filter=none  bitrate=待确认  sample=${sampleHz}Hz`);
    lines.push("提示：用户在这里手动发送不需要平台确认；NPC 代发必须先确认。");
  } else if (tile.kind === "spi-can") {
    lines.push("chip=MCP251x  spi-clock=待确认  irq=待确认");
    lines.push("提示：SPI-CAN 只给配置建议，不直接改系统配置。");
  } else if (tile.kind === "serial") {
    lines.push(`baud=${baudRate}  parity=none  stop=1`);
    lines.push("提示：用户手动输入直接进执行电脑；NPC 代写串口命令必须先确认。");
  } else if (tile.kind === "usb") {
    lines.push("mode=enumerate  driver=待确认");
    lines.push("提示：只读枚举设备，权限或驱动问题进入公司层证据。");
  } else if (tile.kind === "ros") {
    lines.push("topics=readonly  publish=blocked");
    lines.push("提示：ROS 写操作若由 NPC 代操作，必须先确认。");
  } else {
    lines.push("config=等待扫描快照");
  }
  return lines;
}

function submitLabel(tile: DebugWindow) {
  if (tile.runnerCanDispatch) return "提交终端请求";
  if (tile.runnerCanQueue) return "排队等重连";
  return "需重连";
}

function submitTitle(tile: DebugWindow) {
  if (tile.runnerCanDispatch) return "目标电脑正在持续接单，会排队并等待已收到提醒";
  if (tile.runnerCanQueue) return "目标电脑最近在线或等待恢复，命令会排队但不会假装已执行";
  return userFacingTerminalText(tile.runnerHint);
}

function windowsHref(projectId: string, openIds: string[], npcId = "") {
  const params = new URLSearchParams();
  if (openIds.length) params.set("windows", openIds.join(","));
  if (npcId) params.set("npc", npcId);
  const suffix = params.toString();
  return `/projects/${projectId}/robotics${suffix ? `?${suffix}` : ""}`;
}

function kindLabelForConfig(kind: string, fallback: string) {
  switch (kind) {
    case "serial": return "串口";
    case "can": return "CAN";
    case "usb": return "USB";
    case "spi-can": return "SPI-CAN";
    case "ros": return "ROS";
    default: return fallback || "接口";
  }
}

function configuredDebugWindows(resources: DebugWindow[], configs: SavedDebugWindow[]) {
  return configs
    .map((config) => {
      const source = resources.find((item) => item.id === config.resourceId);
      if (!source) return null;
      return {
        ...source,
        name: text(config.name, source.name),
        kind: text(config.type, source.kind),
        kindLabel: kindLabelForConfig(text(config.type, source.kind), source.kindLabel),
        boundNpc: text(config.boundNpc, source.boundNpc),
        baudRate: text(config.baudRate, "115200"),
        sampleHz: text(config.sampleHz, "100"),
        channels: text(config.channels, "time,signal.value,status.code,event.count"),
      };
    })
    .filter(Boolean) as DebugWindow[];
}

function DebugTile({
  projectId,
  tile,
  openIds,
  npcSeats,
  terminalMessages,
  deviceQualityDevices,
  initialNpcId,
  initialTab,
  onClose,
}: {
  projectId: string;
  tile: DebugWindow;
  openIds: string[];
  npcSeats: AnyRecord[];
  terminalMessages: AnyRecord[];
  deviceQualityDevices: AnyRecord[];
  initialNpcId: string;
  initialTab: InitialRoboticsTab;
  onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<TileTab>(() => initialTileTab(initialTab));
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [stateSyncEnabled, setStateSyncEnabled] = useState(false);
  const [showOpenSourceMesh, setShowOpenSourceMesh] = useState(false);
  const [boundNpcId, setBoundNpcId] = useState(initialNpcId);
  const selectedNpcRecord = findSeatRecord(npcSeats, boundNpcId);
  const boundNpcLabel = selectedNpcRecord ? seatName(selectedNpcRecord, boundNpcId) : "";
  const effectiveBoundNpcId = text(boundNpcId, tile.boundNpc);
  const effectiveBoundNpcLabel = publicNpcLabel(boundNpcLabel || tile.boundNpc || "");
  const effectiveNpcSeat = findSeatRecord(npcSeats, effectiveBoundNpcId || effectiveBoundNpcLabel);
  const npcDispatchState = summarizeNpcSeatDispatchState(effectiveNpcSeat);
  const returnTo = windowsHref(projectId, openIds, boundNpcId);
  const segments = captureSegments(tile, terminalMessages);
  const variables = segmentVariables(segments);
  const datasetEvents = tileEvents(tile, terminalMessages, ["robotics_annotation_request", "robotics_dataset_export"]);
  const chartEvents = tileEvents(tile, terminalMessages, ["robotics_chart_snapshot", "robotics_tuning_request"]);
  const [chartTargetValue, setChartTargetValue] = useState("");
  const sampleHz = text(tile.sampleHz, "100");
  const baudRate = text(tile.baudRate, "115200");
  const channels = text(tile.channels, "time,signal.value,status.code,event.count");
  const latestMotorDevice = latestMotorStateDevice(deviceQualityDevices);
  const latestMotors = motorsFromDevices(deviceQualityDevices);

  return (
    <article className={tileStyles.tile}>
      <header className={tileStyles.head}>
        <div className={tileStyles.headLeft}>
          <strong className={tileStyles.name}>{tile.name}</strong>
          <small className={tileStyles.subline}>{tile.kindLabel} · {tile.transport} · {tile.computerState}</small>
        </div>
        <div className={tileStyles.headActions}>
          <button type="button" className={tileStyles.closeBtn} onClick={onClose} aria-label={`关闭 ${tile.name}`}>×</button>
        </div>
      </header>
      <div className={tileStyles.threadBinding}>
        <span className={tileStyles.threadChip}>{tile.statusLabel}</span>
        <span className={tileStyles.threadChip}>电脑：{tile.computerLabel}</span>
        <span className={tileStyles.threadChip}>接单：{tile.computerState}</span>
        <span className={tileStyles.threadChip}>协助 NPC：{effectiveBoundNpcLabel || "未绑定"}</span>
        <button type="button" className={`${tileStyles.threadChip} ${styles.chipButton}`} onClick={() => setSettingsOpen((value) => !value)}>
          设置
        </button>
      </div>
      <nav className={tileStyles.panelTabs} aria-label={`${tile.name} 调试窗口功能`}>
        {[
          ["terminal", "终端"],
          ["dataset", "数据标注"],
          ["chart", "图表实验"],
          ["model", "模型预览"],
        ].map(([tab, label]) => {
          const count =
            tab === "terminal"
              ? terminalEventLines(tile, terminalMessages).length
              : tab === "dataset"
                ? segments.length + datasetEvents.length
                : tab === "chart"
                  ? segments.length + chartEvents.length
                  : 1;
          return (
            <button
              key={tab}
              type="button"
              className={tileStyles.panelTab}
              data-active={activeTab === tab ? "1" : "0"}
              onClick={() => setActiveTab(tab as TileTab)}
            >
              <span>{label}</span>
              <strong>{count}</strong>
            </button>
          );
        })}
      </nav>
      <section className={styles.runnerGate} data-tone={tile.runnerTone}>
        <strong>{tile.runnerCanDispatch ? "可立即提交" : tile.runnerCanQueue ? "可排队，等电脑恢复" : "先重连执行电脑"}</strong>
        <span>{userFacingTerminalText(tile.runnerHint)}</span>
        {!tile.runnerCanDispatch ? <em>保持目标电脑接单窗口在线后自动恢复</em> : null}
        {effectiveBoundNpcId && !npcDispatchState.ready ? <em>{npcDispatchState.detail}</em> : null}
      </section>
      {settingsOpen ? (
        <form action={更新机器人调试窗口.bind(null, projectId)} className={styles.settingsPanel} aria-label={`${tile.name} 设置`}>
          <input type="hidden" name="return_to" value={returnTo} />
          <input type="hidden" name="resource_id" value={tile.id} />
          <input type="hidden" name="window_type" value={tile.kind} />
          <strong>窗口设置</strong>
          <div>
            <span>执行电脑</span>
            <b>{tile.computerLabel} · {tile.computerState}</b>
          </div>
          <div>
            <span>调试接口</span>
            <b>{tile.name}</b>
          </div>
          <label>
            <span>窗口名</span>
            <input name="window_name" defaultValue={tile.name} />
          </label>
          <label>
            <span>协助 NPC</span>
            <input type="hidden" name="bound_npc" value={boundNpcId} />
            <select value={boundNpcId} onChange={(event) => setBoundNpcId(event.target.value)}>
              <option value="">未绑定</option>
              {npcSeats.map((seat, index) => {
                const name = seatName(seat, `NPC ${index + 1}`);
                return <option key={seatId(seat, name)} value={seatId(seat, name)}>{name}</option>;
              })}
            </select>
          </label>
          <label>
            <span>波特率</span>
            <select name="baud_rate" defaultValue={baudRate} aria-label="设置波特率">
              {["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600", "1000000", "2000000"].map((rate) => (
                <option key={rate} value={rate}>{rate}</option>
              ))}
            </select>
          </label>
          <label>
            <span>采样频率</span>
            <input name="sample_hz" defaultValue={sampleHz} inputMode="numeric" />
          </label>
          <label>
            <span>采集通道</span>
            <input name="channels" defaultValue={channels} />
          </label>
          <button type="submit">保存设置</button>
          <p>{effectiveBoundNpcId ? npcDispatchState.detail : tile.runnerHint}</p>
        </form>
      ) : null}
      {activeTab === "terminal" ? (
        <>
          <section className={styles.terminalPane} aria-label={`${tile.name} 终端`}>
            {terminalLines(tile, boundNpcLabel).map((line) => <code key={line}>{line}</code>)}
            <code className={styles.terminalDivider}>--- I/O ---</code>
            {terminalEventLines(tile, terminalMessages).map((line, index) => <code key={`${tile.id}-event-${index}`}>{line}</code>)}
            <code className={styles.terminalCursor}>$ _</code>
          </section>
          <form action={下发机器人调试命令.bind(null, projectId)} className={styles.terminalCommandBar}>
            <input type="hidden" name="return_to" value={returnTo} />
            <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
            <input type="hidden" name="interface_id" value={tile.id} />
            <input type="hidden" name="runner_interface_id" value={tile.runnerInterfaceId || tile.id} />
            <input type="hidden" name="interface_name" value={tile.name} />
            <input type="hidden" name="interface_kind" value={tile.kindLabel} />
            <span>$</span>
            <input name="command" placeholder="用户终端：自己输入直接执行；NPC 代操作需先确认" />
            <select name="bound_npc" aria-label="绑定 NPC" value={boundNpcId} onChange={(event) => setBoundNpcId(event.target.value)}>
              <option value="">不绑定 NPC</option>
              {npcSeats.map((seat, index) => {
                const name = seatName(seat, `NPC ${index + 1}`);
                return <option key={seatId(seat, name)} value={seatId(seat, name)}>{name}</option>;
              })}
            </select>
            <input type="hidden" name="bound_npc_label" value={effectiveBoundNpcLabel} />
            <button type="submit" disabled={!tile.runnerReady} title={submitTitle(tile)}>
              {submitLabel(tile)}
            </button>
          </form>
          <form action={记录机器人采集片段.bind(null, projectId)} className={styles.captureBar}>
            <input type="hidden" name="return_to" value={returnTo} />
            <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
            <input type="hidden" name="interface_id" value={tile.id} />
            <input type="hidden" name="runner_interface_id" value={tile.runnerInterfaceId || tile.id} />
            <input type="hidden" name="interface_name" value={tile.name} />
            <input type="hidden" name="interface_kind" value={tile.kindLabel} />
            <input type="hidden" name="bound_npc" value={effectiveBoundNpcId} />
            <input type="hidden" name="bound_npc_label" value={effectiveBoundNpcLabel} />
            <label>
              <span>采样频率</span>
              <input name="sample_hz" defaultValue={sampleHz} inputMode="numeric" />
            </label>
            <label>
              <span>波特率</span>
              <select name="baud_rate" defaultValue={baudRate} aria-label="波特率">
                {["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600", "1000000", "2000000"].map((rate) => (
                  <option key={rate} value={rate}>{rate}</option>
                ))}
              </select>
            </label>
            <label>
              <span>通道</span>
              <input name="channels" defaultValue={channels} />
            </label>
            <button type="submit" name="capture_mode" value="start" disabled={!tile.runnerReady}>开始采集</button>
            <button type="submit" name="capture_mode" value="stop" disabled={!tile.runnerReady}>停止并生成片段</button>
          </form>
          <form action={创建机器人调试Npc操作审核.bind(null, projectId)} className={styles.npcReviewBar}>
            <input type="hidden" name="return_to" value={returnTo} />
            <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
            <input type="hidden" name="interface_id" value={tile.id} />
            <input type="hidden" name="runner_interface_id" value={tile.runnerInterfaceId || tile.id} />
            <input type="hidden" name="interface_name" value={tile.name} />
            <input type="hidden" name="interface_kind" value={tile.kindLabel} />
            <input type="hidden" name="bound_npc" value={effectiveBoundNpcId} />
            <input type="hidden" name="bound_npc_label" value={effectiveBoundNpcLabel} />
            <span>NPC 代操作待确认</span>
            <input name="command" placeholder="只有 NPC/AI 想替你操作时才填这里，例如 send 123#0102" />
            <button
              type="submit"
              disabled={!tile.runnerReady || !effectiveBoundNpcId || !npcDispatchState.ready}
              title={
                !effectiveBoundNpcId
                  ? "先选择负责这个调试窗口的 NPC"
                  : !npcDispatchState.ready
                    ? npcDispatchState.detail
                    : submitTitle(tile)
              }
            >
              {!effectiveBoundNpcId ? "选择 NPC" : !npcDispatchState.ready ? "先补协作接入" : tile.runnerReady ? "提交确认" : "需重连"}
            </button>
          </form>
        </>
      ) : activeTab === "dataset" ? (
        <section className={styles.dataWorkbenchPane} aria-label={`${tile.name} 数据标注`}>
          <article className={`${styles.dataActionPanel} ${styles.dataFocusPanel}`}>
            <span>采集片段</span>
            <strong>{segments.length ? `${segments.length} 个可标注片段` : `${tile.kindLabel} / ${tile.computerLabel}`}</strong>
            {segments.length ? (
              <ul className={styles.segmentList}>
                {segments.slice(0, 6).map((segment) => (
                  <li key={segment.id}>
                    <b>{segment.title}</b>
                    <small>{segment.sampleHz}Hz · {segment.channels.slice(0, 4).join(" / ")}</small>
                    {captureResultLine(segment) ? <small>{captureResultLine(segment)}</small> : null}
                    {captureTrainingRowLine(segment, variables) ? <small>{captureTrainingRowLine(segment, variables)}</small> : null}
                    {segment.artifactPath ? <ArtifactPathActions projectId={projectId} artifactPath={segment.artifactPath} label="下载片段" /> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p>从终端开始/停止采集后，片段会按时间段出现在这里。标注动作在右侧抽屉里选择片段和变量。</p>
            )}
            <span>可用变量</span>
            <div className={styles.variablePills}>
              {variables.map((variable) => <span key={variable}>{variable}</span>)}
            </div>
          </article>
          <aside className={styles.dataDrawerRail} aria-label="数据标注操作抽屉">
            <details className={styles.workbenchDrawer} open>
              <summary>
                <span>NPC 预标注</span>
                <strong>{effectiveBoundNpcLabel ? npcDispatchState.state : "选择 NPC 后可用"}</strong>
              </summary>
              <form action={创建机器人数据预标注请求.bind(null, projectId)} className={styles.dataActionPanel}>
                <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={effectiveBoundNpcId} boundNpcLabel={effectiveBoundNpcLabel} />
                <span>选择片段</span>
                {segments.length ? segments.slice(0, 6).map((segment) => (
                  <label key={segment.id} className={styles.checkLine}>
                    <input type="checkbox" name="capture_ids" value={segment.id} defaultChecked />
                    <span>{segment.title}</span>
                    <input type="hidden" name="capture_titles" value={segment.title} />
                  </label>
                )) : <p>还没有可预标注的采集片段。</p>}
                <span>选择变量</span>
                <div className={styles.variableGrid}>
                  {variables.map((variable, index) => (
                    <label key={variable} className={styles.checkLine}>
                      <input type="checkbox" name="variables" value={variable} defaultChecked={index < 4} />
                      <span>{variable}</span>
                    </label>
                  ))}
                </div>
                <label className={styles.fieldStack}>
                  <span>标注规则</span>
                  <input name="label_schema" placeholder="用户自定义标签，例如：状态A / 状态B / 异常 / 需复核" />
                </label>
                <label className={styles.fieldStack}>
                  <span>标注目标</span>
                  <textarea name="label_goal" rows={3} placeholder="例如：找出任意变量的异常区间、状态切换、缺失样本或需要人工复核的时间段" />
                </label>
                <button
                  type="submit"
                  disabled={!segments.length || !effectiveBoundNpcId || !npcDispatchState.ready}
                  title={effectiveBoundNpcId ? npcDispatchState.detail : "先选择负责这个调试窗口的 NPC"}
                >
                  生成预标注建议
                </button>
              </form>
            </details>
            <details className={styles.workbenchDrawer}>
              <summary>
                <span>人工确认与导出</span>
                <strong>CSV / JSONL / 清单</strong>
              </summary>
              <form action={导出机器人标注数据.bind(null, projectId)} className={styles.dataActionPanel}>
                <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={effectiveBoundNpcId} boundNpcLabel={effectiveBoundNpcLabel} />
                {segments.slice(0, 6).map((segment) => (
                  <input key={segment.id} type="hidden" name="capture_ids" value={segment.id} />
                ))}
                <span>导出变量</span>
                <div className={styles.variableGrid}>
                  {variables.map((variable, index) => (
                    <label key={variable} className={styles.checkLine}>
                      <input type="checkbox" name="variables" value={variable} defaultChecked={index < 4} />
                      <span>{variable}</span>
                    </label>
                  ))}
                </div>
                <label className={styles.fieldStack}>
                  <span>确认标签</span>
                  <input name="label_schema" placeholder="用户确认后的标签体系或版本名" />
                </label>
                <label className={styles.fieldStack}>
                  <span>人工备注</span>
                  <textarea name="label_notes" rows={3} placeholder="确认、修正或补充 NPC 预标注结果" />
                </label>
                <label className={styles.fieldStack}>
                  <span>人工标签</span>
                  <textarea
                    name="manual_labels"
                    rows={5}
                    placeholder="每行一条：片段,变量,开始,结束,标签,备注。例如 capture-1,signal.value,1.2,2.4,异常,启动段"
                  />
                </label>
                {segments.some((segment) => captureTrainingRowLine(segment, variables)) ? (
                  <p>{segments.map((segment) => captureTrainingRowLine(segment, variables)).filter(Boolean).slice(0, 2).join("；")}</p>
                ) : null}
                <label className={styles.fieldStack}>
                  <span>导出格式</span>
                  <select name="export_format" defaultValue="jsonl" aria-label="导出格式">
                    <option value="csv">CSV</option>
                    <option value="jsonl">JSONL</option>
                    <option value="parquet">Parquet 清单</option>
                    <option value="npz">NPZ 清单</option>
                    <option value="manifest">项目清单</option>
                  </select>
                </label>
                <button type="submit" disabled={!segments.length}>导出标注数据</button>
              </form>
            </details>
            <details className={styles.workbenchDrawer}>
              <summary>
                <span>标注证据</span>
                <strong>{datasetEvents.length ? `${datasetEvents.length} 条记录` : "等待记录"}</strong>
              </summary>
              <article className={styles.dataActionPanel}>
                {datasetEvents.length ? (
                  <ul className={styles.eventList}>
                    {datasetEvents.map((event) => (
                      <li key={text(event.id, text(event.title, "event"))}>
                        <b>{text(event.title, "数据事件")}</b>
                        <small>{text(event.status, "open")}</small>
                        {text(record(event.extra_data ?? event.metadata).artifact_path, "") ? (
                          <ArtifactPathActions projectId={projectId} artifactPath={text(record(event.extra_data ?? event.metadata).artifact_path, "")} label="下载数据" />
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>NPC 预标注只生成建议；用户确认后再导出训练数据集，证据留在当前调试窗口。</p>
                )}
              </article>
            </details>
          </aside>
        </section>
      ) : activeTab === "chart" ? (
        <section className={styles.dataWorkbenchPane} aria-label={`${tile.name} 图表实验`}>
          <article className={`${styles.dataActionPanel} ${styles.dataFocusPanel}`}>
            <span>图表证据</span>
            <strong>{chartEvents.length ? `${chartEvents.length} 条实验记录` : "等待图表快照或分析建议"}</strong>
            {segments.length ? (
              <div className={styles.waveformStack}>
                {segments.slice(0, 3).map((segment) => (
                  <ChartPreview key={`${segment.id}-preview`} segment={segment} targetValue={chartTargetValue} />
                ))}
              </div>
            ) : null}
            {segments.some((segment) => captureResultLine(segment)) ? (
              <ul className={styles.eventList}>
                {segments.filter((segment) => captureResultLine(segment)).slice(0, 3).map((segment) => (
                  <li key={`${segment.id}-runner-result`}>
                    <b>{segment.title}</b>
                    <small>{captureResultLine(segment)}</small>
                    {captureSummaryLine(segment) ? <small>{captureSummaryLine(segment)}</small> : null}
                  </li>
                ))}
              </ul>
            ) : null}
            {chartEvents.length ? (
              <ul className={styles.eventList}>
                {chartEvents.map((event) => (
                  <li key={text(event.id, text(event.title, "event"))}>
                    <b>{text(event.title, "图表事件")}</b>
                    <small>{text(event.status, "open")}</small>
                    {text(record(event.extra_data ?? event.metadata).artifact_path, "") ? (
                      <ArtifactPathActions projectId={projectId} artifactPath={text(record(event.extra_data ?? event.metadata).artifact_path, "")} label="下载证据" />
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p>NPC 可以基于用户选定的曲线、目标值和现象给分析建议；涉及真实设备写入时仍回到终端待确认。</p>
            )}
          </article>
          <aside className={styles.dataDrawerRail} aria-label="图表实验操作抽屉">
            <details className={styles.workbenchDrawer} open>
              <summary>
                <span>坐标与快照</span>
                <strong>{segments.length ? `${segments.length} 个片段` : "等待采集"}</strong>
              </summary>
              <form action={创建机器人图表实验.bind(null, projectId)} className={styles.dataActionPanel}>
                <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={effectiveBoundNpcId} boundNpcLabel={effectiveBoundNpcLabel} />
                <span>选择片段</span>
                {segments.slice(0, 6).map((segment) => (
                  <label key={segment.id} className={styles.checkLine}>
                    <input type="checkbox" name="capture_ids" value={segment.id} defaultChecked />
                    <span>{segment.title}</span>
                  </label>
                ))}
                <label className={styles.fieldStack}>
                  <span>横轴变量</span>
                  <select name="x_axis" defaultValue={variables.includes("time") ? "time" : variables[0]} aria-label="横轴变量">
                    {variables.map((variable) => <option key={variable} value={variable}>{variable}</option>)}
                  </select>
                </label>
                <span>纵轴变量</span>
                <div className={styles.variableGrid}>
                  {variables.filter((item) => item !== "time").map((variable, index) => (
                    <label key={variable} className={styles.checkLine}>
                      <input type="checkbox" name="y_axes" value={variable} defaultChecked={index < 2} />
                      <span>{variable}</span>
                    </label>
                  ))}
                </div>
                <label className={styles.fieldStack}>
                  <span>水平目标值</span>
                  <input name="target_value" placeholder="例如 目标值 / 阈值 / 状态线 / 参考区间" value={chartTargetValue} onChange={(event) => setChartTargetValue(event.target.value)} />
                </label>
                <label className={styles.fieldStack}>
                  <span>实验类型</span>
                  <select name="chart_mode" defaultValue="sensor" aria-label="实验类型">
                    <option value="sensor">通用时序</option>
                    <option value="bus">总线数据</option>
                    <option value="pid">PID 调试</option>
                    <option value="foc">FOC 调试</option>
                  </select>
                </label>
                <button type="submit" disabled={!segments.length}>保存图表快照</button>
              </form>
            </details>
            <details className={styles.workbenchDrawer}>
              <summary>
                <span>NPC 分析建议</span>
                <strong>{effectiveBoundNpcLabel ? npcDispatchState.state : "选择 NPC 后可用"}</strong>
              </summary>
              <form action={创建机器人调参建议请求.bind(null, projectId)} className={styles.dataActionPanel}>
                <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={effectiveBoundNpcId} boundNpcLabel={effectiveBoundNpcLabel} />
                {segments.slice(0, 6).map((segment) => (
                  <input key={segment.id} type="hidden" name="capture_ids" value={segment.id} />
                ))}
                <label className={styles.fieldStack}>
                  <span>横轴变量</span>
                  <select name="x_axis" defaultValue={variables.includes("time") ? "time" : variables[0]} aria-label="调参横轴">
                    {variables.map((variable) => <option key={variable} value={variable}>{variable}</option>)}
                  </select>
                </label>
                <span>关注曲线</span>
                <div className={styles.variableGrid}>
                  {variables.filter((item) => item !== "time").map((variable, index) => (
                    <label key={variable} className={styles.checkLine}>
                      <input type="checkbox" name="y_axes" value={variable} defaultChecked={index < 3} />
                      <span>{variable}</span>
                    </label>
                  ))}
                </div>
                <label className={styles.fieldStack}>
                  <span>目标值或区间</span>
                  <input name="target_value" placeholder="目标值或目标区间" />
                </label>
                <label className={styles.fieldStack}>
                  <span>分析类型</span>
                  <select name="chart_mode" defaultValue="sensor" aria-label="分析类型">
                    <option value="sensor">通用时序</option>
                    <option value="bus">总线数据</option>
                    <option value="pid">PID 调试</option>
                    <option value="foc">FOC 调试</option>
                  </select>
                </label>
                <label className={styles.fieldStack}>
                  <span>现象描述</span>
                  <textarea name="symptoms" rows={3} placeholder="例如：某段数据突然跳变、周期性波动、状态切换后延迟、阈值附近反复抖动" />
                </label>
                <button
                  type="submit"
                  disabled={!segments.length || !effectiveBoundNpcId || !npcDispatchState.ready}
                  title={effectiveBoundNpcId ? npcDispatchState.detail : "先选择负责这个调试窗口的 NPC"}
                >
                  请求 NPC 分析建议
                </button>
              </form>
            </details>
          </aside>
        </section>
      ) : (
        <section className={styles.modelWorkbenchPane} aria-label={`${tile.name} 模型预览`}>
          <article className={`${styles.dataActionPanel} ${styles.dataFocusPanel}`}>
            <span>模型与状态预览</span>
            <strong>用电机状态看机器人整体姿态</strong>
            <p>这里把服务器最近收到的电机状态映射到 3D 结构，关节颜色表示温度。视图只读，不发送 ROS 写操作，也不下发任何硬件动作。</p>
            <div className={styles.syncToolbar} aria-label="状态数据同步控制">
              <form action={记录机器人采集片段.bind(null, projectId)}>
                <input type="hidden" name="return_to" value={returnTo} />
                <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
                <input type="hidden" name="interface_id" value={tile.id} />
                <input type="hidden" name="runner_interface_id" value={tile.runnerInterfaceId || tile.id} />
                <input type="hidden" name="interface_name" value={tile.name} />
                <input type="hidden" name="interface_kind" value={tile.kindLabel} />
                <input type="hidden" name="bound_npc" value={effectiveBoundNpcId} />
                <input type="hidden" name="bound_npc_label" value={effectiveBoundNpcLabel} />
                <input type="hidden" name="sample_hz" value="20" />
                <input type="hidden" name="baud_rate" value={baudRate} />
                <input type="hidden" name="channels" value="/rehab_arm/motor_state,/joint_states,/rehab_arm/safety_state" />
                <button
                  type="submit"
                  name="capture_mode"
                  value="start"
                  disabled={!tile.runnerReady}
                  onClick={() => setStateSyncEnabled(true)}
                >
                  开始数据同步
                </button>
                <button
                  type="submit"
                  name="capture_mode"
                  value="stop"
                  disabled={!tile.runnerReady}
                  onClick={() => setStateSyncEnabled(false)}
                >
                  关闭并生成片段
                </button>
              </form>
              <button type="button" onClick={() => setShowOpenSourceMesh((value) => !value)}>
                {showOpenSourceMesh ? "隐藏开源 mesh" : "加载开源 mesh"}
              </button>
            </div>
            <MotorState3DViewer
              motors={latestMotors}
              sourceLine={latestMotorStateLine(latestMotorDevice, latestMotors)}
              syncEnabled={stateSyncEnabled}
              showOpenSourceMesh={showOpenSourceMesh}
            />
            <ModelImportInspector />
          </article>
          <aside className={styles.dataDrawerRail} aria-label="模型预览说明">
            <details className={styles.workbenchDrawer} open>
              <summary>
                <span>状态映射</span>
                <strong>{latestMotors.length ? `${latestMotors.length} 个电机` : "等待电机状态"}</strong>
              </summary>
              <article className={styles.dataActionPanel}>
                {latestMotors.length ? (
                  <ul className={styles.eventList}>
                    {latestMotors.slice(0, 8).map((motor, index) => (
                      <li key={`${text(motor.motor_id, "motor")}-${index}`}>
                        <b>{text(motor.joint_name, `motor ${text(motor.motor_id, String(index + 1))}`)}</b>
                        <small>位置 {numberText(motor.position, " rad")} · 速度 {numberText(motor.velocity, " rad/s")} · 温度 {temperatureOf(motor) == null ? "无" : numberText(temperatureOf(motor), " C")}</small>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>等待 Linux 开发板或服务器同步工具上传电机/关节状态。没有数据时只显示默认姿态和开源 mesh 示例。</p>
                )}
              </article>
            </details>
            <details className={styles.workbenchDrawer} open>
              <summary>
                <span>推荐流程</span>
                <strong>URDF 到结构检查再到回放</strong>
              </summary>
              <article className={styles.dataActionPanel}>
                <p>第一步导入 URDF 或 GLB，确认关节数量、父子结构和限制。第二步导出项目清单，作为项目模型证据。第三步再把采集片段里的关节状态对齐到同名关节。</p>
                <p>如果 URDF 引用外部 mesh，平台第一版先显示结构和可解析的几何体；大型 mesh 后续交给模型资产索引，不直接塞进普通消息。</p>
              </article>
            </details>
            <details className={styles.workbenchDrawer}>
              <summary>
                <span>开源 mesh</span>
                <strong>RobotExpressive.glb / CC0</strong>
              </summary>
              <article className={styles.dataActionPanel}>
                <p>“加载开源 mesh”会载入 Three.js 示例模型 `RobotExpressive.glb`，许可证为 CC0 1.0。它只用于验证 GLB 加载链路，不是本项目的正式机械臂模型。</p>
              </article>
            </details>
            <details className={styles.workbenchDrawer}>
              <summary>
                <span>安全边界</span>
                <strong>只读显示</strong>
              </summary>
              <article className={styles.dataActionPanel}>
                <p>模型预览不是仿真控制器，不生成电机目标，不绕过本地控制器安全状态机。真实机器人运动仍必须经过本机规划、Linux 开发板桥接和底层安全裁决。</p>
              </article>
            </details>
          </aside>
        </section>
      )}
    </article>
  );
}

export function RoboticsWorkbenchClient({
  projectId,
  projectName,
  windows,
  initialSavedWindows,
  npcSeats,
  terminalMessages,
  initialOpenIds,
  initialNpcId,
  initialTab,
  readyComputers,
  queueableComputers,
  reconnectComputers,
  unknownComputers,
  computerCount,
  scannedInterfaceCount,
  deviceQualityDevices,
  notice = "",
  error = "",
}: RoboticsWorkbenchClientProps) {
  const [defaultNpcId, setDefaultNpcId] = useState(initialNpcId);
  const [savedWindows, setSavedWindows] = useState<SavedDebugWindow[]>(initialSavedWindows);
  const [workbenchMode, setWorkbenchMode] = useState<DeviceWorkbenchMode>(() => {
    if (initialTab === "terminal") return "interfaces";
    if (!initialTab && initialSavedWindows.length) return "interfaces";
    return "boards";
  });
  const router = useRouter();
  const configuredWindows = useMemo(() => configuredDebugWindows(windows, savedWindows), [windows, savedWindows]);
  const [openIds, setOpenIds] = useState<string[]>(() => {
    const knownDeviceIds = new Set(deviceQualityDevices.map((device, index) => deviceId(device, index)));
    const requested = initialOpenIds.filter((id) => savedWindows.some((item) => item.resourceId === id) || knownDeviceIds.has(id));
    if (requested.length) return requested;
    if (initialTab === "terminal") {
      const firstSavedWindow = savedWindows.find((item) => item.resourceId);
      if (firstSavedWindow?.resourceId) return [firstSavedWindow.resourceId];
    }
    if (!initialTab) {
      const firstSavedWindow = savedWindows.find((item) => item.resourceId);
      if (firstSavedWindow?.resourceId) return [firstSavedWindow.resourceId];
    }
    const firstDeviceId = deviceQualityDevices[0] ? deviceId(deviceQualityDevices[0], 0) : "";
    if (firstDeviceId) return [firstDeviceId];
    const firstSavedWindow = savedWindows.find((item) => item.resourceId);
    return firstSavedWindow?.resourceId ? [firstSavedWindow.resourceId] : [];
  });
  const usableWindows = useMemo(() => windows.filter((item) => item.isUsable), [windows]);
  const resourceById = useMemo(() => new Map(windows.map((item) => [item.id, item])), [windows]);
  const openWindows = useMemo(
    () => openIds.map((id) => configuredWindows.find((item) => item.id === id)).filter(Boolean) as DebugWindow[],
    [openIds, configuredWindows],
  );
  const devices = useMemo(() => deviceQualityDevices.filter((device) => deviceId(device)), [deviceQualityDevices]);
  const openDevices = useMemo(
    () => openIds.map((id) => devices.find((device, index) => deviceId(device, index) === id)).filter(Boolean) as AnyRecord[],
    [openIds, devices],
  );
  const openCount = openDevices.length + openWindows.length;
  const needsLiveRefresh = terminalMessages.some((message) => {
    const type = text(message.message_type ?? message.messageType, "");
    const status = text(message.status, "");
    return type === "runner_command" && ["pending", "queued", "acked", "in_progress", "running"].includes(status);
  }) || openCount > 0;

  useEffect(() => {
    if (!needsLiveRefresh) return;
    const timer = window.setInterval(() => {
      router.refresh();
    }, 3500);
    return () => window.clearInterval(timer);
  }, [needsLiveRefresh, router]);

  function previewCreateWindow(event: FormEvent<HTMLFormElement>) {
    const formData = new FormData(event.currentTarget);
    const resourceId = text(formData.get("resource_id"), "");
    const resource = resourceById.get(resourceId);
    if (!resource) return;
    const next: SavedDebugWindow = {
      resourceId,
      name: text(formData.get("window_name"), resource.name),
      type: text(formData.get("window_type"), resource.kind),
      baudRate: text(formData.get("baud_rate"), "115200"),
      sampleHz: text(formData.get("sample_hz"), "100"),
      channels: text(formData.get("channels"), "time,signal.value,status.code,event.count"),
      boundNpc: text(formData.get("bound_npc"), defaultNpcId),
    };
    window.setTimeout(() => {
      setSavedWindows((current) => [...current.filter((item) => item.resourceId !== resourceId), next]);
      setOpenIds((current) => current.includes(resourceId) ? current : [...current, resourceId]);
      const nextOpenIds = openIds.includes(resourceId) ? openIds : [...openIds, resourceId];
      window.history.replaceState(null, "", windowsHref(projectId, nextOpenIds, text(next.boundNpc, defaultNpcId)));
    }, 250);
  }

  function previewDeleteWindow(resourceId: string) {
    setSavedWindows((current) => current.filter((item) => item.resourceId !== resourceId));
    setOpenIds((current) => current.filter((item) => item !== resourceId));
    window.history.replaceState(null, "", windowsHref(projectId, openIds.filter((item) => item !== resourceId), defaultNpcId));
  }

  function toggleWindow(id: string) {
    setOpenIds((curr) => curr.includes(id) ? curr.filter((item) => item !== id) : [...curr, id]);
  }

  function openAllForMode() {
    if (workbenchMode === "boards") {
      setOpenIds(devices.map((device, index) => deviceId(device, index)));
      return;
    }
    setOpenIds(configuredWindows.map((window) => window.id));
  }

  function closeWindow(id: string) {
    setOpenIds((curr) => curr.filter((item) => item !== id));
  }

  const modeItemCount = workbenchMode === "boards" ? devices.length : configuredWindows.length;
  const workflowSteps = workbenchMode === "boards"
    ? [
      { label: "接入", detail: "NanoPi / Linux 主机上传只读状态" },
      { label: "查看", detail: "打开开发板数据、相机、模型预览" },
      { label: "沉淀", detail: "进入标注和图表实验形成证据" },
    ]
    : [
      { label: "扫描", detail: "从真实电脑同步串口/CAN/USB/ROS" },
      { label: "建窗", detail: "把接口保存成项目调试窗口" },
      { label: "采集", detail: "在瓷砖里完成终端、标注、图表" },
    ];

  return (
    <main className={`${workbenchStyles.shell} ${styles.roboticsWorkbenchShell}`}>
      <header className={workbenchStyles.topbar}>
        <div className={workbenchStyles.topbarLeft}>
          <Link className={workbenchStyles.backLink} href={`/projects/${projectId}`}>← 主页面</Link>
          <div className={workbenchStyles.title}>
            <strong>{projectName}</strong>
            <small>通用设备数据工作台 · 终端 / 数据标注 / 图表实验</small>
          </div>
        </div>
        <div className={workbenchStyles.topbarRight}>
          <span className={workbenchStyles.kpi}>开发板 {devices.length}</span>
          <span className={workbenchStyles.kpi}>接口设备 {usableWindows.length}</span>
          <span className={workbenchStyles.kpi}>已打开 {openCount}</span>
          <span className={workbenchStyles.kpi}>可标注 {devices.filter(dataQualityReady).length}</span>
          <span className={workbenchStyles.kpi}>扫描接口 {scannedInterfaceCount}</span>
        </div>
      </header>

      <div className={workbenchStyles.body}>
        <aside className={workbenchStyles.sidebar}>
          <div className={workbenchStyles.sidebarHeader}>
            <input
              type="search"
              className={workbenchStyles.search}
              placeholder="搜索开发板或接口设备"
              readOnly
              value="Linux 开发板"
            />
            <div className={styles.deviceModeSwitch} aria-label="选择设备类型">
              <button type="button" data-active={workbenchMode === "boards" ? "1" : "0"} onClick={() => setWorkbenchMode("boards")}>
                Linux 开发板
              </button>
              <button type="button" data-active={workbenchMode === "interfaces" ? "1" : "0"} onClick={() => setWorkbenchMode("interfaces")}>
                串口与设备
              </button>
            </div>
            <ol className={styles.sidebarWorkflow} aria-label="设备数据工作台操作顺序">
              {workflowSteps.map((step, index) => (
                <li key={step.label} data-active={index === 0 ? "1" : "0"}>
                  <span>{index + 1}</span>
                  <strong>{step.label}</strong>
                  <small>{step.detail}</small>
                </li>
              ))}
            </ol>
            <button type="button" className={workbenchStyles.batchBtn} onClick={openAllForMode}>
              打开当前类型 ({modeItemCount})
            </button>
            <form action={请求串口USB扫描.bind(null, projectId)} className={styles.scanInlineForm}>
              <input type="hidden" name="return_to" value={`/projects/${projectId}/robotics`} />
              <input type="hidden" name="computer_node_id" value="all" />
              <button type="submit" disabled={!computerCount}>
                {workbenchMode === "boards" ? "扫描 Linux 开发板" : "扫描真实接口"}
              </button>
            </form>
            {workbenchMode === "interfaces" ? (
              <details className={styles.setupDrawer}>
                <summary>创建调试窗口</summary>
                <form action={创建机器人调试窗口.bind(null, projectId)} onSubmit={previewCreateWindow} className={styles.windowCreateForm}>
                  <input type="hidden" name="return_to" value={`/projects/${projectId}/robotics`} />
                  <input name="window_name" placeholder="窗口名，例如 产线传感器串口" />
                  <label className={styles.createFullField}>
                    <span>窗口类型</span>
                    <select name="window_type" defaultValue="serial" aria-label="窗口类型">
                      <option value="serial">串口</option>
                      <option value="can">CAN</option>
                      <option value="usb">USB</option>
                      <option value="spi-can">SPI-CAN</option>
                      <option value="ros">ROS</option>
                    </select>
                  </label>
                  <label className={styles.createFullField}>
                    <span>绑定真实设备</span>
                    <select name="resource_id" aria-label="绑定真实设备">
                      {usableWindows.map((resource) => (
                        <option key={resource.id} value={resource.id}>{resource.name} · {resource.computerLabel} · {resource.computerState}</option>
                      ))}
                    </select>
                  </label>
                  <details className={styles.nestedSettings}>
                    <summary>参数和 NPC</summary>
                    <div className={styles.createParamGrid}>
                      <label>
                        <span>波特率</span>
                        <select name="baud_rate" defaultValue="115200" aria-label="波特率">
                          {["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600", "1000000", "2000000"].map((rate) => (
                            <option key={rate} value={rate}>{rate}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>采样频率</span>
                        <input name="sample_hz" defaultValue="100" aria-label="采样频率" />
                      </label>
                    </div>
                    <label className={styles.createFullField}>
                      <span>采集通道</span>
                      <input name="channels" defaultValue="time,signal.value,status.code,event.count" aria-label="采集通道" />
                    </label>
                    <label className={styles.createFullField}>
                      <span>协助 NPC</span>
                      <select name="bound_npc" aria-label="协助 NPC" defaultValue={defaultNpcId} onChange={(event) => setDefaultNpcId(event.target.value)}>
                        <option value="">不绑定 NPC</option>
                        {npcSeats.map((seat, index) => {
                          const name = seatName(seat, `NPC ${index + 1}`);
                          return <option key={seatId(seat, name)} value={seatId(seat, name)}>{name}</option>;
                        })}
                      </select>
                    </label>
                  </details>
                  <button type="submit" disabled={!usableWindows.length}>创建并打开</button>
                  <small>
                    {usableWindows.length
                      ? `${usableWindows.length} 个真实设备可绑定`
                      : "先扫描并让目标电脑可排队。"}
                  </small>
                </form>
              </details>
            ) : null}
          </div>
          <ul className={workbenchStyles.groupList}>
            {workbenchMode === "boards" ? (
              <li className={workbenchStyles.group}>
                <div className={workbenchStyles.groupHeader}>
                  <span>Linux 开发板</span>
                  <small>{devices.length} 台</small>
                </div>
                <ul className={workbenchStyles.npcList}>
                  {devices.map((device, index) => {
                    const id = deviceId(device, index);
                    const isOpen = openIds.includes(id);
                    const counts = deviceDataCounts(device);
                    return (
                      <li key={id} className={`${workbenchStyles.npcRow} ${isOpen ? workbenchStyles.npcRowOpen : ""}`}>
                        <div className={workbenchStyles.npcMain}>
                          <strong className={workbenchStyles.npcName}>{deviceTitle(device, index)}</strong>
                          <small className={workbenchStyles.npcMeta}>
                            <span className={text(device.online_state) === "online" ? workbenchStyles.dotOnline : workbenchStyles.dot} />
                            {publicDeviceCode(device, index)} · 电机 {counts.motors} · 传感 {counts.sensorFields} · {deviceSafetyText(device)}
                          </small>
                        </div>
                        <span className={styles.windowRowActions}>
                          <button
                            type="button"
                            className={workbenchStyles.openBtn}
                            aria-label={`${isOpen ? "关闭" : "打开"} ${deviceTitle(device, index)}`}
                            onClick={() => toggleWindow(id)}
                          >
                            {isOpen ? "✕" : "+"}
                          </button>
                        </span>
                      </li>
                    );
                  })}
                  {!devices.length ? (
                    <li className={workbenchStyles.npcRow}>
                      <div className={workbenchStyles.npcMain}>
                        <strong className={workbenchStyles.npcName}>等待 Linux 开发板接入</strong>
                        <small className={workbenchStyles.npcMeta}>预配置脚本连接服务器并上传设备数据后自动出现</small>
                      </div>
                    </li>
                  ) : null}
                </ul>
              </li>
            ) : (
              <li className={workbenchStyles.group}>
                <div className={workbenchStyles.groupHeader}>
                  <span>🖥 调试窗口</span>
                  <small>{configuredWindows.length} 个窗口</small>
                </div>
                <ul className={workbenchStyles.npcList}>
                  {configuredWindows.map((window) => {
                    const isOpen = openIds.includes(window.id);
                    return (
                      <li key={window.id} className={`${workbenchStyles.npcRow} ${isOpen ? workbenchStyles.npcRowOpen : ""}`}>
                        <div className={workbenchStyles.npcMain}>
                          <strong className={workbenchStyles.npcName}>{window.name}</strong>
                          <small className={workbenchStyles.npcMeta}>
                            <span className={window.statusLabel === "可读取" ? workbenchStyles.dotOnline : workbenchStyles.dot} />
                            {window.computerLabel} · {window.computerState} · {window.statusLabel}
                          </small>
                        </div>
                        <span className={styles.windowRowActions}>
                          <a
                            className={workbenchStyles.openBtn}
                            href={windowsHref(projectId, isOpen ? openIds.filter((id) => id !== window.id) : [...openIds, window.id], defaultNpcId)}
                            aria-label={`${isOpen ? "关闭" : "打开"} ${window.name}`}
                            onClick={(event) => {
                              event.preventDefault();
                              toggleWindow(window.id);
                            }}
                          >
                            {isOpen ? "✕" : "+"}
                          </a>
                          <form action={删除机器人调试窗口.bind(null, projectId)} onSubmit={() => previewDeleteWindow(window.id)}>
                            <input type="hidden" name="return_to" value={`/projects/${projectId}/robotics`} />
                            <input type="hidden" name="resource_id" value={window.id} />
                            <button type="submit" aria-label={`删除 ${window.name}`}>删</button>
                          </form>
                        </span>
                      </li>
                    );
                  })}
                  {!configuredWindows.length ? (
                    <li className={workbenchStyles.npcRow}>
                      <div className={workbenchStyles.npcMain}>
                        <strong className={workbenchStyles.npcName}>等待创建调试窗口</strong>
                        <small className={workbenchStyles.npcMeta}>先扫描真实接口，再用上方“创建调试窗口”绑定设备</small>
                      </div>
                    </li>
                  ) : null}
                </ul>
              </li>
            )}
          </ul>
        </aside>

        <section className={workbenchStyles.main} data-mode={openCount > 0 ? "chat" : "setup"}>
          {notice ? <div className={styles.inlineNotice} data-tone="success">{notice}</div> : null}
          {error ? <div className={styles.inlineNotice} data-tone="danger">{error}</div> : null}
          {openCount ? (
            <div className={`${workbenchStyles.tileGrid} ${styles.deviceTileGrid}`} data-tile-count={openCount}>
              {openDevices.map((device, index) => (
                <DeviceDataTile
                  key={deviceId(device, index)}
                  projectId={projectId}
                  device={device}
                  index={index}
                  npcSeats={npcSeats}
                  defaultNpcId={defaultNpcId}
                  initialTab={initialTab}
                  onClose={() => closeWindow(deviceId(device, index))}
                />
              ))}
              {openWindows.map((tile) => (
                <DebugTile
                  key={tile.id}
                  projectId={projectId}
                  tile={tile}
                  openIds={openIds}
                  npcSeats={npcSeats}
                  terminalMessages={terminalMessages}
                  deviceQualityDevices={deviceQualityDevices}
                  initialNpcId={text(tile.boundNpc, defaultNpcId)}
                  initialTab={initialTab}
                  onClose={() => closeWindow(tile.id)}
                />
              ))}
            </div>
          ) : (
            <div className={styles.overviewPage}>
              <AccessCheckPanel
                devices={deviceQualityDevices}
                computerCount={computerCount}
                readyComputers={readyComputers}
                queueableComputers={queueableComputers}
                scannedInterfaceCount={scannedInterfaceCount}
                workbenchMode={workbenchMode}
                projectId={projectId}
                openFirstDevice={() => devices[0] && setOpenIds([deviceId(devices[0], 0)])}
              />
              <DeviceQualityStrip devices={deviceQualityDevices} />
              <SimulationReadinessStrip devices={deviceQualityDevices} />
              <section className={styles.nextActionPanel} aria-label="下一步操作">
                <div>
                  <span>下一步</span>
                  <strong>{workbenchMode === "boards" ? "打开一台 Linux 开发板" : "打开一个串口/CAN/USB 设备"}</strong>
                  <p>{workbenchMode === "boards" ? "开发板显示遥测数据、摄像头、标注、图表和模型预览。" : "接口设备会进入带终端的调试页面，可做串口/CAN/USB 采集、NPC 辅助和图表实验。"}</p>
                </div>
                <div className={styles.quickActionGrid}>
                  <form action={请求串口USB扫描.bind(null, projectId)}>
                    <input type="hidden" name="return_to" value={`/projects/${projectId}/robotics`} />
                    <input type="hidden" name="computer_node_id" value="all" />
                    <button type="submit" disabled={!computerCount}>
                      {workbenchMode === "boards" ? "扫描 Linux 开发板" : "扫描接口"}
                    </button>
                  </form>
                  <a href="#model-preview">导入模型</a>
                  {workbenchMode === "boards" && devices[0] ? (
                    <button type="button" onClick={() => setOpenIds([deviceId(devices[0], 0)])}>打开最近开发板</button>
                  ) : workbenchMode === "interfaces" && configuredWindows[0] ? (
                    <a href={windowsHref(projectId, [configuredWindows[0].id], defaultNpcId)}>打开最近窗口</a>
                  ) : (
                    <span>{workbenchMode === "boards" ? "等待设备上传" : "创建后打开窗口"}</span>
                  )}
                </div>
              </section>
              <details id="model-preview" className={styles.modelDrawer}>
                <summary>模型预览</summary>
                <div className={styles.emptyModelPreview}>
                  <strong>导入 URDF 看结构</strong>
                  <p>只检查 link、joint 和 limit；不发 ROS、不控制设备。</p>
                  <ModelImportInspector />
                </div>
              </details>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
