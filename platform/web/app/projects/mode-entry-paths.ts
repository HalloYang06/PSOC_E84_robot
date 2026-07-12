export type ModeEntryId = "2d-dev" | "2d-upgrade" | "2d-edu" | "3d-dev" | "3d-edu";
export type FutureModeEntryId = Exclude<ModeEntryId, "2d-dev" | "2d-upgrade">;
export type FutureModePathMap<T> = Record<FutureModeEntryId, T>;

export const modeChoicePath = "/projects/mode-choice";
export const modeChoice2dDevPath = "/projects/mode-choice?mode=2d-dev";
export const projectEntryShellPath = "/projects/[id]";
export const projectEntryLiveModeLayerHint = `inside ${projectEntryShellPath}`;
export const futureModeEntryIds: FutureModeEntryId[] = ["2d-edu", "3d-dev", "3d-edu"];

export type ProjectEntryLiveRouteStep = {
  kind: "route" | "surface";
  marker: string;
  label: string;
  role: string;
};

export type ProjectFutureModeShellNavigation = {
  returnTo: string;
  modeBoardPath: string;
  currentProjectModePath: string;
  liveProjectPath: string;
  shellPath: string;
};

export type ModeEntryProjectSummary = {
  id: string;
  name: string;
  description: string;
  role: string;
  type: string;
};

export type ProjectModeDefinition = {
  id: ModeEntryId;
  label: string;
  state: string;
  detail: string;
  routeSummary: string;
  branchRule: string;
  shellPath: string | null;
};

export function buildProjectEntryLiveRoute(projectId?: string): ProjectEntryLiveRouteStep[] {
  const liveProjectPath = projectId ? buildProjectModeEntryPath(projectId, "2d-dev") : projectEntryShellPath;
  const liveModeLayerHint = projectId ? `inside ${liveProjectPath}` : projectEntryLiveModeLayerHint;
  return [
    { kind: "route", marker: "/login", label: "登录页", role: "只负责认证" },
    { kind: "route", marker: "/projects", label: "项目管理入口页", role: "只负责选项目" },
    { kind: "route", marker: liveProjectPath, label: "当前项目入口壳", role: "承接当前项目" },
    {
      kind: "surface",
      marker: liveModeLayerHint,
      label: "2D 开发者模式入口",
      role: projectId ? "当前 live 默认落点" : "当前 live 落点，不是独立路由",
    },
  ];
}

export const projectEntryLiveRoute: ProjectEntryLiveRouteStep[] = buildProjectEntryLiveRoute();

const modeShellPathById: FutureModePathMap<string> = {
  "2d-edu": "/projects/mode-choice/2d-edu",
  "3d-dev": "/projects/mode-choice/3d-dev",
  "3d-edu": "/projects/mode-choice/3d-edu",
};

export function isModeEntryId(value: string): value is ModeEntryId {
  return ["2d-dev", "2d-upgrade", "2d-edu", "3d-dev", "3d-edu"].includes(value);
}

function isFutureModeEntryId(value: string): value is FutureModeEntryId {
  return futureModeEntryIds.includes(value as FutureModeEntryId);
}

export function normalizeModeEntryId(value: unknown): ModeEntryId {
  const normalized = typeof value === "string" ? value.trim() : "";
  return isModeEntryId(normalized) ? normalized : "2d-dev";
}

export function buildProjectModeChoicePath(projectId?: string, mode: string = "2d-dev") {
  const params = new URLSearchParams();
  params.set("mode", normalizeModeEntryId(mode));
  if (projectId) params.set("projectId", projectId);
  return `${modeChoicePath}?${params.toString()}`;
}

export function buildModeShellPath(mode: FutureModeEntryId, projectId?: string): string;
export function buildModeShellPath(mode: string, projectId?: string): string | null;
export function buildModeShellPath(mode: string, projectId?: string) {
  const normalizedMode = normalizeModeEntryId(mode);
  if (!isFutureModeEntryId(normalizedMode)) return null;
  const shellPath = modeShellPathById[normalizedMode];
  const params = new URLSearchParams();
  params.set("mode", normalizedMode);
  if (projectId) params.set("projectId", projectId);
  return `${shellPath}?${params.toString()}`;
}

export function buildProjectFutureModeChoicePaths(projectId?: string): FutureModePathMap<string> {
  return {
    "2d-edu": buildProjectModeChoicePath(projectId, "2d-edu"),
    "3d-dev": buildProjectModeChoicePath(projectId, "3d-dev"),
    "3d-edu": buildProjectModeChoicePath(projectId, "3d-edu"),
  };
}

export function buildProjectFutureModeShellPaths(projectId?: string): FutureModePathMap<string> {
  return {
    "2d-edu": buildModeShellPath("2d-edu", projectId),
    "3d-dev": buildModeShellPath("3d-dev", projectId),
    "3d-edu": buildModeShellPath("3d-edu", projectId),
  };
}

export function buildProjectModeChoiceRoute(
  projectId: string | undefined,
  modeId: ModeEntryId,
): ProjectEntryLiveRouteStep[] {
  return [
    { kind: "route", marker: "/login", label: "登录页", role: "只负责认证" },
    { kind: "route", marker: "/projects", label: "项目管理入口页", role: "先锁定项目" },
    {
      kind: "route",
      marker: buildProjectModeChoicePath(projectId, modeId),
      label: "模式分流板",
      role: projectId ? "切到当前项目的目标模式视角" : "把未来模式分流钉成真实页面",
    },
    { kind: "surface", marker: "selected mode board", label: "项目级模式板", role: "展示当前项目的四模式落点" },
  ];
}

export function buildProjectModeDefinitions(projectId?: string): ProjectModeDefinition[] {
  const liveProjectPath = projectId ? buildProjectModeEntryPath(projectId, "2d-dev") : projectEntryShellPath;
  const modeBoardPaths = buildProjectFutureModeChoicePaths(projectId);
  const modeShellPaths = buildProjectFutureModeShellPaths(projectId);
  const twoDEduBoardPath = modeBoardPaths["2d-edu"];
  const twoDEduShellPath = modeShellPaths["2d-edu"];
  const threeDDevBoardPath = modeBoardPaths["3d-dev"];
  const threeDDevShellPath = modeShellPaths["3d-dev"];
  const threeDEduBoardPath = modeBoardPaths["3d-edu"];
  const threeDEduShellPath = modeShellPaths["3d-edu"];

  return [
    {
      id: "2d-dev",
      label: "2D 开发者模式入口",
      state: "当前 live",
      detail: "今天唯一真实开放的项目级模式，仍然落在当前项目入口壳里的 2D 农场协作界面。",
      routeSummary: `/login -> /projects -> ${liveProjectPath} -> 2D 开发者模式入口`,
      branchRule: "默认 live 路径仍然直接进入当前项目 2D 模式，不需要先绕到分流板。",
      shellPath: null,
    },
    {
      id: "2d-upgrade",
      label: "2D 开发版升级版入口",
      state: "开发中",
      detail:
        "保留原本 2D live 不动，单独打开一个卡通养成开发版。地图、角色、建筑和 HUD 图标来自 Blender MCP 渲染的透明 PNG，并且已经接入项目任务、需求、协作消息、电脑节点和用量数据。",
      routeSummary: `/login -> /projects -> ${projectId ? buildProject2dUpgradePath(projectId) : "/projects/[id]/2d-upgrade"} -> 2D 养成开发版`,
      branchRule: "这是新增的独立开发入口，用来先验证升级版玩法和后端数据联动，后续稳定后再逐步替代原 2D live。",
      shellPath: projectId ? buildProject2dUpgradePath(projectId) : null,
    },
    {
      id: "2d-edu",
      label: "2D 教育版入口",
      state: "规划中",
      detail: "真实分流层和下游占位壳已就位，但教学任务链、教学 NPC 和结果页还没有接进来。",
      routeSummary: `/login -> /projects -> ${twoDEduBoardPath} -> ${twoDEduShellPath ?? "2D 教育版占位壳"}`,
      branchRule: `教育版要从 ${twoDEduBoardPath} 这条真实分流路继续往下走，而不是复用当前 live 2D 的直接入口。`,
      shellPath: twoDEduShellPath,
    },
    {
      id: "3d-dev",
      label: "3D 开发者模式入口",
      state: "规划中",
      detail: "真实分流层和下游占位壳已就位，但 3D 世界壳、协作桥和开发工作流还没有接进来。",
      routeSummary: `/login -> /projects -> ${threeDDevBoardPath} -> ${threeDDevShellPath ?? "3D 开发者模式占位壳"}`,
      branchRule: `3D 开发者模式已经有真实分流路 ${threeDDevBoardPath}，但它还不能替代当前 live 的 2D 农场底座。`,
      shellPath: threeDDevShellPath,
    },
    {
      id: "3d-edu",
      label: "3D 教育版模式入口",
      state: "规划中",
      detail: "真实分流层和下游占位壳已就位，但 3D 教学内容、任务链和实验回流还没有接进来。",
      routeSummary: `/login -> /projects -> ${threeDEduBoardPath} -> ${threeDEduShellPath ?? "3D 教育版占位壳"}`,
      branchRule: `3D 教育版仍是最远期分支，今天只把入口位置固定到 ${threeDEduBoardPath} 这条真实页面。`,
      shellPath: threeDEduShellPath,
    },
  ];
}

export function buildProjectFutureModeShellNavigation(
  mode: FutureModeEntryId,
  projectId?: string,
): ProjectFutureModeShellNavigation {
  const shellPath = buildModeShellPath(mode, projectId);
  return {
    returnTo: shellPath,
    modeBoardPath: buildProjectModeChoicePath(projectId, mode),
    currentProjectModePath: buildProjectModeEntryPath(projectId, mode),
    liveProjectPath: buildProjectModeEntryPath(projectId, "2d-dev"),
    shellPath,
  };
}

export function normalizeModeEntryProjects(
  workspace: Record<string, unknown> | null | undefined,
): ModeEntryProjectSummary[] {
  const rawProjects = Array.isArray(workspace?.projects) ? workspace.projects : [];
  return rawProjects
    .map((project) => {
      const record = project as Record<string, unknown>;
      const id = String(record.id ?? record.project_id ?? "").trim();
      return {
        id,
        name: String(record.name ?? record.project_name ?? "未命名项目"),
        description: String(record.description ?? "").trim(),
        role: String(record.role ?? (record.is_owner ? "owner" : "collaborator")),
        type: String(record.project_type ?? "software"),
      } satisfies ModeEntryProjectSummary;
    })
    .filter((project) => project.id);
}

export function selectModeEntryProject(
  projects: ModeEntryProjectSummary[],
  projectId?: string,
): ModeEntryProjectSummary | null {
  const normalizedProjectId = typeof projectId === "string" ? projectId.trim() : "";
  if (!normalizedProjectId) return null;
  return projects.find((project) => project.id === normalizedProjectId) ?? null;
}

export function buildProjectModeEntryPath(projectId?: string, mode: string = "2d-dev") {
  if (!projectId) return "/projects";
  const normalizedMode = normalizeModeEntryId(mode);
  if (normalizedMode === "2d-dev") return `/projects/${projectId}`;
  if (normalizedMode === "2d-upgrade") return buildProject2dUpgradePath(projectId);
  return `/projects/${projectId}?mode=${encodeURIComponent(normalizedMode)}`;
}

export function buildProject2dUpgradePath(projectId?: string) {
  if (!projectId) return "/projects";
  return `/projects/${encodeURIComponent(projectId)}/2d-upgrade`;
}
