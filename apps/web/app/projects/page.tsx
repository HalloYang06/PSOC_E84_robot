import Script from "next/script";
import { redirect } from "next/navigation";

import { getWorkspaceState } from "../../lib/server-data";
import { ProjectsPlazaWorkbench } from "./projects-plaza-workbench-client";

const projectsRuntimeRecoveryScript = `
(() => {
  const recoveryKey = "ai-collab-projects-runtime-recovery-v1";
  const chunkPattern = /_next\\/static\\/chunks\\/.*\\.js/i;
  const textPattern =
    /ChunkLoadError|Loading chunk|Failed to fetch dynamically imported module|_next\\/static\\/chunks\\/webpack-/i;

  function shouldRecoverFromText(value) {
    try {
      const message =
        typeof value === "string"
          ? value
          : typeof value?.message === "string"
            ? value.message
            : typeof value?.reason?.message === "string"
              ? value.reason.message
              : String(value ?? "");
      return textPattern.test(message);
    } catch {
      return false;
    }
  }

  function triggerRecovery() {
    if (typeof window === "undefined" || window.location.pathname !== "/projects") return;
    try {
      if (window.sessionStorage.getItem(recoveryKey) === "1") return;
      window.sessionStorage.setItem(recoveryKey, "1");
    } catch {}

    try {
      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.set("__runtime_recover", String(Date.now()));
      window.location.replace(nextUrl.toString());
    } catch {
      window.location.reload();
    }
  }

  window.addEventListener(
    "error",
    (event) => {
      const target = event?.target;
      const src =
        typeof target?.src === "string"
          ? target.src
          : typeof target?.href === "string"
            ? target.href
            : "";
      if (shouldRecoverFromText(event?.error) || chunkPattern.test(src)) {
        triggerRecovery();
      }
    },
    true,
  );

  window.addEventListener("unhandledrejection", (event) => {
    if (shouldRecoverFromText(event?.reason)) {
      triggerRecovery();
    }
  });
})();
`;

export default async function ProjectsPage({
  searchParams,
}: {
  searchParams?: {
    team_error?: string;
    team_notice?: string;
  };
}) {
  const workspaceState = await getWorkspaceState();

  if (workspaceState.status === 401 || workspaceState.status === 403) {
    redirect("/login");
  }

  const workspace = workspaceState.data;
  if (!workspace?.user) {
    redirect("/login");
  }

  const projects = Array.isArray(workspace.projects)
    ? workspace.projects.map((project) => {
        const rawProject = project as Record<string, unknown>;
        return {
          id: String(rawProject.id ?? rawProject.project_id ?? ""),
          name: String(rawProject.name ?? rawProject.project_name ?? "未命名项目"),
          description: String(rawProject.description ?? "").trim(),
          role: String(rawProject.role ?? (rawProject.is_owner ? "owner" : "collaborator")),
          type: String(rawProject.project_type ?? "software"),
          pendingHumanReviewCount:
            Number(rawProject.pending_human_review_count ?? rawProject.pendingHumanReviewCount ?? 0) || 0,
          pendingHumanReviewTitle: String(
            rawProject.pending_human_review_title ?? rawProject.pendingHumanReviewTitle ?? "",
          ).trim(),
          pendingHumanReviewDetail: String(
            rawProject.pending_human_review_detail ?? rawProject.pendingHumanReviewDetail ?? "",
          ).trim(),
          pendingHumanReviewLevel: String(
            rawProject.pending_human_review_level ?? rawProject.pendingHumanReviewLevel ?? "",
          ).trim(),
        };
      })
    : [];
  const invitations = Array.isArray(workspace.pending_invitations)
    ? workspace.pending_invitations.map((invitation) => {
        const rawInvitation = invitation as Record<string, unknown>;
        const rawProject =
          rawInvitation.project && typeof rawInvitation.project === "object"
            ? (rawInvitation.project as Record<string, unknown>)
            : null;

        return {
          id: String(rawInvitation.id ?? ""),
          projectName: String(rawProject?.name ?? "未命名项目"),
          note: String(
            rawInvitation.note ??
              "接受邀请后，你才能进入这个项目并继续管理电脑、线程和 AI 成员。",
          ),
          role: String(rawInvitation.role ?? "collaborator"),
        };
      })
    : [];

  const user = {
    name: String(workspace.user.name ?? workspace.user.display_name ?? "基地成员"),
    email: String(workspace.user.email ?? ""),
  };

  return (
    <>
      <Script id="projects-runtime-recovery" strategy="beforeInteractive">
        {projectsRuntimeRecoveryScript}
      </Script>
      <ProjectsPlazaWorkbench
        user={user}
        projects={projects}
        invitations={invitations}
        workspaceError={typeof searchParams?.team_error === "string" ? searchParams.team_error : ""}
        workspaceNotice={typeof searchParams?.team_notice === "string" ? searchParams.team_notice : ""}
      />
    </>
  );
}

