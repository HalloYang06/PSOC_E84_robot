import { redirect } from "next/navigation";

import { normalizeModeEntryProjects, selectModeEntryProject } from "./mode-entry-paths";
import { getWorkspaceState } from "../../lib/server-data";

type WorkspaceStateData = Awaited<ReturnType<typeof getWorkspaceState>>["data"];
type ModeEntryWorkspace = Exclude<WorkspaceStateData, null> & {
  user: NonNullable<Exclude<WorkspaceStateData, null>["user"]>;
};

export async function requireModeEntryWorkspace(returnTo: string): Promise<ModeEntryWorkspace> {
  const workspaceState = await getWorkspaceState();
  const loginPath = `/login?returnTo=${encodeURIComponent(returnTo)}`;

  if (workspaceState.status === 401 || workspaceState.status === 403) {
    redirect(loginPath);
  }

  const workspace = workspaceState.data;
  if (!workspace?.user) {
    redirect(loginPath);
  }

  return workspace as ModeEntryWorkspace;
}

export async function requireModeEntryProjectContext(returnTo: string, selectedProjectId?: string) {
  const workspace = await requireModeEntryWorkspace(returnTo);
  const projects = normalizeModeEntryProjects(workspace);
  const selectedProject = selectModeEntryProject(projects, selectedProjectId);

  return {
    workspace,
    projects,
    selectedProject,
  };
}
