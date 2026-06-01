import Link from "next/link";
import { redirect } from "next/navigation";
import { getApiBaseUrl } from "../../../../lib/config";
import { getCurrentAuthState, getProjectState } from "../../../../lib/server-data";
import { RehabArmControlClient, type AnyRecord, type Dashboard, type DashboardDevice } from "./rehab-arm-control-client";
import styles from "./rehab-arm-control.module.css";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? value as AnyRecord : {};
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
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

async function getRehabArmDashboard(projectId: string): Promise<Dashboard> {
  try {
    const response = await fetch(new URL("/api/rehab-arm/v1/devices/dashboard", getApiBaseUrl()).toString(), {
      cache: "no-store",
    });
    if (!response.ok) return emptyDashboard();
    const payload = await response.json();
    const data = record(payload).data;
    const dashboard = record(data);
    const devices = asArray<AnyRecord>(dashboard.devices).filter((device) => deviceProjectId(device) === projectId) as DashboardDevice[];
    const deviceIds = new Set(devices.map((device) => text(device.device_id, "")).filter(Boolean));
    const recentEvents = asArray<AnyRecord>(dashboard.recent_events).filter((event) => {
      const eventProjectId = text(event.project_id ?? event.projectId, "");
      if (eventProjectId) return eventProjectId === projectId;
      const eventDeviceId = text(event.device_id, "");
      return !eventDeviceId || deviceIds.has(eventDeviceId);
    });
    return {
      ...emptyDashboard(),
      ...dashboard,
      safety_boundary: {
        ...emptyDashboard().safety_boundary,
        ...record(dashboard.safety_boundary),
      },
      devices,
      recent_events: recentEvents,
    };
  } catch {
    return emptyDashboard();
  }
}

export default async function RehabArmControlPage({ params }: { params: { id: string } }) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/rehab-arm-control`)}`);
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

  const dashboard = await getRehabArmDashboard(projectId);

  return (
    <RehabArmControlClient
      apiBaseUrl={getApiBaseUrl()}
      dashboard={dashboard}
      projectId={projectId}
      projectName={text(project.name, "项目")}
    />
  );
}
