"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
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

function keyframeSrc(imageUrl: string, apiBaseUrl: string) {
  if (!imageUrl) return "";
  if (imageUrl.startsWith("/api/")) return `/api/proxy/${imageUrl.slice("/api/".length)}`;
  if (imageUrl.startsWith("/")) return imageUrl;
  return new URL(imageUrl, apiBaseUrl).toString();
}

function qualityReadyText(value: unknown) {
  return value ? "可标注" : "待补数据";
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

function Arm3DOverview({ motors, safetyState }: { motors: AnyRecord[]; safetyState: string }) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const cleanupRef = useRef<() => void>(() => {});
  const robotRef = useRef<AnyRecord | null>(null);
  const positions = useMemo(() => jointPositionsFromMotors(motors), [motors]);
  const jointValues = useMemo(() => jointValueMapFromMotors(motors), [motors]);
  const positionsRef = useRef(positions);
  const jointValuesRef = useRef(jointValues);
  const [urdfText, setUrdfText] = useState("");
  const placeholderPoseKey = urdfText ? "" : positions.map((position) => position.toFixed(4)).join("|");
  const [urdfName, setUrdfName] = useState("");
  const [urdfState, setUrdfState] = useState<"placeholder" | "loading" | "loaded" | "failed">("placeholder");
  const [urdfJoints, setUrdfJoints] = useState<JointDetail[]>([]);
  const urdfJointNames = useMemo(() => urdfJoints.map((joint) => joint.name), [urdfJoints]);
  const matchedUrdfJoints = useMemo(
    () => urdfJointNames.filter((name) => jointValues.has(name)),
    [jointValues, urdfJointNames],
  );

  useEffect(() => {
    positionsRef.current = positions;
    jointValuesRef.current = jointValues;
  }, [jointValues, positions]);

  function handleUrdfFile(file: File | null) {
    if (!file) return;
    setUrdfName(file.name);
    setUrdfState("loading");
    setUrdfJoints([]);
    file.text()
      .then((content) => {
        setUrdfJoints(parseUrdfJoints(content));
        setUrdfText(content);
      })
      .catch(() => {
        setUrdfText("");
        setUrdfState("failed");
      });
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
          const { default: URDFLoader } = await import("urdf-loader");
          if (disposed) return;
          const loader = new URDFLoader();
          (loader as AnyRecord).packages = "";
          (loader as AnyRecord).loadMeshCb = (_url: string, _manager: unknown, done: (mesh: unknown, err?: Error) => void) => {
            done(new THREE.Group(), new Error("外部 mesh 未在浏览器本地加载"));
          };
          const robot = loader.parse(urdfText) as AnyRecord;
          if (disposed) return;
          robotRef.current = robot;
          robot.rotation.x = -Math.PI / 2;
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
  }, [placeholderPoseKey, safetyState, urdfText]);

  useEffect(() => {
    const robot = robotRef.current;
    if (!robot) return;
    jointValues.forEach((value, name) => {
      if (robot.joints?.[name]) {
        robot.setJointValue?.(name, value);
      }
    });
  }, [jointValues, urdfJointNames]);

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
          <span>导入本机 URDF</span>
          <input
            type="file"
            accept=".urdf,.xml"
            data-testid="rehab-urdf-file"
            onChange={(event) => handleUrdfFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <p>只读预览：页面用电机上报角度驱动同名关节，不下发任何运动控制。mesh 资源未上传时会自动使用占位模型。</p>
      </div>
      <div ref={mountRef} className={styles.armCanvas} />
      {urdfJoints.length ? (
        <div className={styles.poseStatus}>
          <strong>匹配 {matchedUrdfJoints.length}/{urdfJoints.filter((joint) => !["fixed", "floating"].includes(joint.type)).length || urdfJoints.length}</strong>
          <span>同名关节会实时套用电机角度；未匹配关节保持模型默认姿态。</span>
        </div>
      ) : null}
      <div className={styles.armLegend}>
        {(urdfJointNames.length ? urdfJointNames : ARM_MODEL_JSON.joints).slice(0, 10).map((name, index) => (
          <span key={name}>{name}: {numberText(jointValues.get(name) ?? positions[index], " rad")}</span>
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
  const devices = useMemo(() => liveDashboard.devices.length ? liveDashboard.devices : [], [liveDashboard.devices]);
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
              <p>{qualityReady ? "可进入标注和导出。" : asArray<string>(dataQuality.blocking_reasons).join("；") || "等待设备档案和质量摘要。"}</p>
            </article>
            <article>
              <span>传感器</span>
              <strong>{text(sensorPayload.source, "等待载荷")}</strong>
              <p>EMG、心率、IMU、疲劳评分和意图输出作为非实时数据资产展示。</p>
            </article>
          </div>

          <div className={styles.primaryGrid}>
            <Arm3DOverview motors={motors} safetyState={stateLabel(currentSafetyState)} />

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
