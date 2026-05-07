type AnyRecord = Record<string, unknown>;

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function normalizeSlashPath(value: string) {
  return value.replace(/\\/g, "/").replace(/\/+/g, "/");
}

function stripLeadingDotSlash(value: string) {
  return value.replace(/^\.\//, "");
}

function trimGitSuffix(value: string) {
  return value.replace(/\.git$/i, "");
}

function normalizeWorkspaceRoot(value: unknown) {
  const next = normalizeSlashPath(text(value, "")).replace(/\/+$/, "");
  return next || "";
}

function looksLikeUrl(value: string) {
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(value);
}

function looksLikeWindowsAbsolutePath(value: string) {
  return /^[a-z]:[\\/]/i.test(value);
}

function looksLikeUnixAbsolutePath(value: string) {
  return value.startsWith("/");
}

function normalizeReferenceValue(value: unknown) {
  const next = text(value, "");
  if (!next) return "";
  if (looksLikeUrl(next)) return next.replace(/\\/g, "/");
  return normalizeSlashPath(next);
}

function relativeToWorkspace(value: string, workspaceRoots: string[]) {
  const normalizedValue = normalizeSlashPath(value);
  for (const root of workspaceRoots) {
    if (!root) continue;
    const normalizedRoot = normalizeWorkspaceRoot(root);
    if (!normalizedRoot) continue;
    if (normalizedValue.toLowerCase() === normalizedRoot.toLowerCase()) return ".";
    if (normalizedValue.toLowerCase().startsWith(`${normalizedRoot.toLowerCase()}/`)) {
      return stripLeadingDotSlash(normalizedValue.slice(normalizedRoot.length + 1));
    }
  }
  return null;
}

function normalizeList(value: unknown) {
  const values = Array.isArray(value) ? value : typeof value === "string" ? value.split(/[\n,]/) : [];
  return values.map((item) => text(item)).filter(Boolean);
}

export type PlatformRepoContext = {
  version: "v1";
  collaboration_route: "github_repo" | "repo_relative_only";
  repository_url: string | null;
  branch: string | null;
  relative_root: string;
  local_path_policy: "each_computer_decides";
};

export function resolvePlatformRepoContext(
  value: unknown,
  defaults: {
    repositoryUrl?: string | null;
    branch?: string | null;
    relativeRoot?: string | null;
  } = {},
): PlatformRepoContext | null {
  const base = value && typeof value === "object" ? (value as AnyRecord) : {};
  const repositoryUrl = text(base.repository_url ?? defaults.repositoryUrl, "") || null;
  const branch = text(base.branch ?? defaults.branch, "") || null;
  const relativeRoot = text(base.relative_root ?? defaults.relativeRoot, "") || ".";
  if (!repositoryUrl && !branch) return null;
  return {
    version: "v1",
    collaboration_route: repositoryUrl ? "github_repo" : "repo_relative_only",
    repository_url: repositoryUrl,
    branch,
    relative_root: relativeRoot,
    local_path_policy: "each_computer_decides",
  };
}

export function buildPlatformRepoReferencePaths(options: {
  referencePaths?: unknown;
  gitBoundary?: unknown;
  handoffPath?: string | null;
  repositoryUrl?: string | null;
  branch?: string | null;
  workspaceRoots?: string[];
}) {
  const workspaceRoots = (options.workspaceRoots ?? [])
    .map((item) => normalizeWorkspaceRoot(item))
    .filter(Boolean);
  const prefersRepoRoute = Boolean(text(options.repositoryUrl, "") || text(options.branch, ""));
  const normalized = new Set<string>();
  const push = (raw: unknown) => {
    const next = normalizeReferenceValue(raw);
    if (!next) return;
    if (prefersRepoRoute && options.branch && /^branch:/i.test(next)) {
      return;
    }
    if (looksLikeUrl(next)) {
      normalized.add(trimGitSuffix(next));
      return;
    }
    const relative = relativeToWorkspace(next, workspaceRoots);
    if (relative) {
      if (relative !== ".") normalized.add(relative);
      return;
    }
    if (looksLikeWindowsAbsolutePath(next) || looksLikeUnixAbsolutePath(next)) {
      if (!prefersRepoRoute) normalized.add(next);
      return;
    }
    normalized.add(stripLeadingDotSlash(next));
  };

  push(options.repositoryUrl);
  if (options.branch) normalized.add(`branch:${text(options.branch)}`);
  normalizeList(options.gitBoundary).forEach(push);
  normalizeList(options.referencePaths).forEach(push);
  push(options.handoffPath);
  return Array.from(normalized);
}

export function platformRepoContextSummary(context: PlatformRepoContext | null) {
  if (!context) {
    return "仓库协作上下文待补";
  }
  const repoLabel = context.repository_url ? trimGitSuffix(context.repository_url) : "当前仓库";
  const branchLabel = context.branch ? `分支 ${context.branch}` : "分支待补";
  return `${repoLabel} / ${branchLabel} / 各电脑自行确定本地路径`;
}

export function platformRepoContextNote(context: PlatformRepoContext | null) {
  if (!context) {
    return "平台优先按 GitHub 仓库和相对路径协作；如果项目仓库信息还没补齐，再临时回退到普通参考资料。";
  }
  return `平台会先派发仓库地址${context.branch ? `、分支 ${context.branch}` : ""}和相对路径，各电脑自己决定 clone 到哪里，不要求统一绝对路径。`;
}
