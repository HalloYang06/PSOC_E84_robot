import Link from "next/link";
import { redirect } from "next/navigation";
import { getApiBaseUrl } from "../../../../lib/config";
import { getCurrentAuthState, getProjectState } from "../../../../lib/server-data";
import { RehabArmControlClient, type Dashboard } from "./rehab-arm-control-client";
import styles from "./rehab-arm-control.module.css";

export const dynamic = "force-dynamic";
export const revalidate = 0;

async function loadDashboard(): Promise<Dashboard> {
  try {
    const response = await fetch(new URL("/api/rehab-arm/v1/devices/dashboard", getApiBaseUrl()).toString(), {
      cache: "no-store",
    });
    const json = await response.json();
    const data = json?.data ?? json;
    if (response.ok && data && typeof data === "object") return data as Dashboard;
  } catch {}
  return {
    sync_role: "non_realtime_telemetry_data_asset_only",
    safety_boundary: {
      server_may_send: ["high_level_task", "data_request", "configuration_suggestion", "annotation_task", "vla_task_draft"],
      server_must_not_send: ["can_frame", "motor_current", "motor_torque", "motor_raw_position", "motor_velocity", "m33_override", "emergency_stop_dependency"],
      m33_final_authority: true,
    },
    devices: [],
    recent_events: [],
  };
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

  const dashboard = await loadDashboard();
  return (
    <RehabArmControlClient
      apiBaseUrl={getApiBaseUrl()}
      dashboard={dashboard}
      projectId={projectId}
      projectName={String(project.name ?? "项目")}
    />
  );
}
