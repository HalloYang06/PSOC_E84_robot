import { createHash } from "node:crypto";
import path from "node:path";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getApiBaseUrl } from "../../../../lib/config";

const ACCESS_TOKEN_COOKIE = "farm_access_token";
const GITHUB_SKILL_IMPORT_MAX_FILES = 40;
const GITHUB_SKILL_IMPORT_MAX_SKILLS = 120;
const GITHUB_SKILL_IMPORT_MAX_TEXT_BYTES = 600_000;
const GITHUB_SKILL_STORED_INSTRUCTION_LIMIT = 18_000;

type GithubSkillImportTarget = {
  owner: string;
  repo: string;
  ref: string;
  path: string;
  mode: "file" | "tree";
  sourceUrl: string;
};

type GithubSkillSourceFile = {
  owner: string;
  repo: string;
  ref: string;
  path: string;
  sourceUrl: string;
  rawUrl: string;
  content: string;
  importMode?: "standard" | "agent_markdown";
};

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function cloneRecord(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value) ? { ...(value as Record<string, unknown>) } : {};
}

function uniqueStrings(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.map((item) => text(item, "")).filter(Boolean)));
}

function normalizeStringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap((item) => normalizeStringList(item));
  const raw = text(value, "");
  if (!raw) return [];
  return raw
    .split(/[,\n，、|]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseStringList(value: FormDataEntryValue | null): string[] {
  return normalizeStringList(value);
}

function trimToLength(value: unknown, maxLength: number) {
  const raw = text(value, "");
  if (raw.length <= maxLength) return raw;
  return `${raw.slice(0, maxLength).trimEnd()}\n\n[内容已截断，完整内容请查看 GitHub 源文件]`;
}

function safeReturnTo(projectId: string, value: unknown) {
  const raw = text(value, "");
  const fallback = `/projects/${encodeURIComponent(projectId)}/2d-upgrade?panel=skills&action=github-import`;
  if (!raw.startsWith(`/projects/${projectId}/`)) return fallback;
  return raw;
}

function withResult(pathname: string, key: "team_notice" | "team_error", message: string, requestUrl: string) {
  const origin = new URL(requestUrl).origin;
  const url = new URL(pathname, origin);
  url.searchParams.set(key, message);
  return url;
}

function slugifyProjectSkillId(value: unknown, fallback = "skill") {
  const normalized = text(value, fallback)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9-_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return normalized || fallback;
}

function skillCategoryLabel(skill: Record<string, unknown>) {
  const metadata = cloneRecord(skill.metadata);
  if (text(metadata.category, "")) return text(metadata.category, "");
  if (text(skill.source, "") === "github") return "github";
  return "custom";
}

function skillSortRank(skill: Record<string, unknown>) {
  const source = text(skill.source, "custom");
  if (source === "custom") return 0;
  if (source === "agency-agents") return 1;
  return 2;
}

function sortProjectSkillLibrary(skills: Record<string, unknown>[]) {
  return skills.slice().sort((left, right) => {
    const sourceRank = skillSortRank(left) - skillSortRank(right);
    if (sourceRank !== 0) return sourceRank;
    const categoryRank = skillCategoryLabel(left).localeCompare(skillCategoryLabel(right), "zh-CN");
    if (categoryRank !== 0) return categoryRank;
    return text(left.label ?? left.id, "").localeCompare(text(right.label ?? right.id, ""), "zh-CN");
  });
}

function parseGithubUrl(rawUrl: string, pathOverride = "", branchOverride = ""): GithubSkillImportTarget {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new Error("请填写有效的 GitHub 地址，例如 https://github.com/owner/repo/tree/main/skills");
  }
  const host = parsed.hostname.toLowerCase();
  const parts = parsed.pathname.split("/").map((item) => decodeURIComponent(item)).filter(Boolean);
  const cleanPathOverride = pathOverride.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  const cleanBranchOverride = branchOverride.replace(/^\/+|\/+$/g, "");

  if (host === "raw.githubusercontent.com") {
    const [owner, repo, rawRef, ...pathParts] = parts;
    if (!owner || !repo || !rawRef) throw new Error("Raw GitHub 地址不完整，至少需要 owner/repo/branch/path");
    const filePath = cleanPathOverride || pathParts.join("/");
    if (!filePath) throw new Error("Raw GitHub 地址缺少文件路径");
    return { owner, repo, ref: cleanBranchOverride || rawRef || "main", path: filePath, mode: "file", sourceUrl: rawUrl };
  }

  if (host !== "github.com" && host !== "www.github.com") {
    throw new Error("当前只允许从 github.com 或 raw.githubusercontent.com 导入 Skill，避免误抓内网或不可信地址。");
  }

  const [owner, repo, modeSegment, rawRef, ...pathParts] = parts;
  if (!owner || !repo) throw new Error("GitHub 地址缺少 owner/repo，例如 https://github.com/owner/repo");
  const repoName = repo.replace(/\.git$/i, "");
  const isBlob = modeSegment === "blob";
  const isTree = modeSegment === "tree";
  const inferredPath = cleanPathOverride || (isBlob || isTree ? pathParts.join("/") : "");
  const inferredRef = cleanBranchOverride || (isBlob || isTree ? rawRef : "") || "";
  const mode: "file" | "tree" = isBlob || /\.[a-z0-9]+$/i.test(inferredPath) ? "file" : "tree";
  return { owner, repo: repoName, ref: inferredRef, path: inferredPath, mode, sourceUrl: rawUrl };
}

function githubApiUrl(target: GithubSkillImportTarget, apiPath: string) {
  return `https://api.github.com/repos/${encodeURIComponent(target.owner)}/${encodeURIComponent(target.repo)}${apiPath}`;
}

async function fetchGithubJson(url: string) {
  const response = await fetch(url, {
    headers: { Accept: "application/vnd.github+json", "User-Agent": "ai-collab-platform-skill-import" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`GitHub API 返回 HTTP ${response.status}`);
  return (await response.json()) as Record<string, unknown>;
}

async function fetchGithubText(url: string) {
  const response = await fetch(url, {
    headers: { Accept: "text/plain, application/json;q=0.9, text/markdown;q=0.9, */*;q=0.5", "User-Agent": "ai-collab-platform-skill-import" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`GitHub 文件读取失败：HTTP ${response.status}`);
  const contentLength = Number(response.headers.get("content-length") ?? 0);
  if (contentLength > GITHUB_SKILL_IMPORT_MAX_TEXT_BYTES) throw new Error("这个 GitHub 文件太大，请指定具体 Skill 文件或目录。");
  const content = await response.text();
  if (content.length > GITHUB_SKILL_IMPORT_MAX_TEXT_BYTES) throw new Error("这个 GitHub 文件太大，请指定更小的 Skill 文件。");
  return content;
}

async function resolveGithubImportRef(target: GithubSkillImportTarget) {
  if (target.ref) return target.ref;
  try {
    const repoPayload = await fetchGithubJson(githubApiUrl(target, ""));
    return text(repoPayload.default_branch, "main");
  } catch {
    return "main";
  }
}

function githubRawUrl(owner: string, repo: string, ref: string, filePath: string) {
  return `https://raw.githubusercontent.com/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/${encodeURIComponent(ref)}/${filePath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/")}`;
}

function looksLikeGithubSkillFile(filePath: string, exactFileMode = false) {
  const normalized = filePath.replace(/\\/g, "/");
  const baseName = path.posix.basename(normalized).toLowerCase();
  if (exactFileMode) return /\.(md|mdx|json)$/i.test(baseName);
  if (/^(skill|skills|skill-pack|skill_pack)\.(md|mdx|json)$/i.test(baseName)) return true;
  if (/^skill[-_.].+\.(md|mdx|json)$/i.test(baseName)) return true;
  if (/(^|\/)(skills|skill|\.codex\/skills)\/.+\.(md|mdx|json)$/i.test(normalized)) return true;
  if (/\.skill\.(md|mdx|json)$/i.test(baseName)) return true;
  return false;
}

function looksLikeGithubAgentMarkdownFile(filePath: string) {
  const normalized = filePath.replace(/\\/g, "/").replace(/^\/+/, "");
  const lower = normalized.toLowerCase();
  const baseName = path.posix.basename(lower);
  if (!/\.(md|mdx)$/i.test(baseName)) return false;
  if (/^(readme|contributing|security|license|code_of_conduct|pull_request_template)\.mdx?$/i.test(baseName)) return false;
  if (lower.startsWith(".github/") || lower.startsWith("scripts/") || lower.startsWith("examples/")) return false;
  if (lower.split("/").some((part) => part.startsWith("."))) return false;
  return normalized.split("/").length >= 2;
}

async function readGithubSkillSourceFiles(target: GithubSkillImportTarget): Promise<GithubSkillSourceFile[]> {
  const resolvedRef = await resolveGithubImportRef(target);
  const activeTarget = { ...target, ref: resolvedRef };
  if (activeTarget.mode === "file") {
    const rawUrl = activeTarget.sourceUrl.includes("raw.githubusercontent.com")
      ? activeTarget.sourceUrl
      : githubRawUrl(activeTarget.owner, activeTarget.repo, activeTarget.ref, activeTarget.path);
    return [{
      owner: activeTarget.owner,
      repo: activeTarget.repo,
      ref: activeTarget.ref,
      path: activeTarget.path,
      sourceUrl: activeTarget.sourceUrl,
      rawUrl,
      content: await fetchGithubText(rawUrl),
      importMode: "standard",
    }];
  }

  const treePayload = await fetchGithubJson(githubApiUrl(activeTarget, `/git/trees/${encodeURIComponent(activeTarget.ref)}?recursive=1`));
  const tree = Array.isArray(treePayload.tree) ? (treePayload.tree as Record<string, unknown>[]) : [];
  const basePath = activeTarget.path.replace(/^\/+|\/+$/g, "");
  const prefix = basePath ? `${basePath}/` : "";
  let importMode: GithubSkillSourceFile["importMode"] = "standard";
  let candidatePaths = tree
    .filter((entry) => text(entry.type, "") === "blob")
    .map((entry) => text(entry.path, ""))
    .filter(Boolean)
    .filter((filePath) => (prefix ? filePath === basePath || filePath.startsWith(prefix) : true))
    .filter((filePath) => looksLikeGithubSkillFile(filePath))
    .slice(0, GITHUB_SKILL_IMPORT_MAX_FILES);

  if (!candidatePaths.length) {
    candidatePaths = tree
      .filter((entry) => text(entry.type, "") === "blob")
      .map((entry) => text(entry.path, ""))
      .filter(Boolean)
      .filter((filePath) => (prefix ? filePath === basePath || filePath.startsWith(prefix) : true))
      .filter((filePath) => looksLikeGithubAgentMarkdownFile(filePath))
      .slice(0, GITHUB_SKILL_IMPORT_MAX_FILES);
    importMode = "agent_markdown";
  }

  if (!candidatePaths.length) {
    throw new Error("这个 GitHub 目录里没有找到明显的 Skill 文件，也没有可转换的 Markdown agent profile。请指定 SKILL.md、skill.json、skills.json、skills/ 目录，或一个按目录分类存放角色 Markdown 的仓库。");
  }

  const files: GithubSkillSourceFile[] = [];
  for (const filePath of candidatePaths) {
    const rawUrl = githubRawUrl(activeTarget.owner, activeTarget.repo, activeTarget.ref, filePath);
    files.push({
      owner: activeTarget.owner,
      repo: activeTarget.repo,
      ref: activeTarget.ref,
      path: filePath,
      sourceUrl: activeTarget.sourceUrl,
      rawUrl,
      content: await fetchGithubText(rawUrl),
      importMode,
    });
  }
  return files;
}

function stripMarkdownFrontmatter(markdown: string) {
  if (!markdown.startsWith("---")) return markdown;
  const closeIndex = markdown.indexOf("\n---", 3);
  if (closeIndex < 0) return markdown;
  const afterClose = markdown.indexOf("\n", closeIndex + 4);
  return markdown.slice(afterClose >= 0 ? afterClose + 1 : closeIndex + 4);
}

function parseSimpleFrontmatter(markdown: string) {
  if (!markdown.startsWith("---")) return {};
  const closeIndex = markdown.indexOf("\n---", 3);
  if (closeIndex < 0) return {};
  const block = markdown.slice(3, closeIndex).trim();
  const result: Record<string, unknown> = {};
  for (const line of block.split(/\r?\n/)) {
    const match = /^([A-Za-z0-9_.-]+):\s*(.*)$/.exec(line.trim());
    if (!match) continue;
    const key = match[1];
    let value: unknown = match[2].trim();
    if (typeof value === "string" && value.startsWith("[") && value.endsWith("]")) {
      value = value.slice(1, -1).split(",").map((item) => item.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
    } else if (typeof value === "string") {
      value = value.replace(/^["']|["']$/g, "");
    }
    result[key] = value;
  }
  return result;
}

function extractMarkdownHeading(markdown: string) {
  const heading = /^#\s+(.+)$/m.exec(stripMarkdownFrontmatter(markdown));
  return text(heading?.[1], "");
}

function extractMarkdownSummary(markdown: string) {
  const body = stripMarkdownFrontmatter(markdown)
    .replace(/```[\s\S]*?```/g, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/!\[[^\]]*]\([^)]+\)/g, " ")
    .replace(/\[[^\]]+]\([^)]+\)/g, (match) => match.replace(/^\[|\]\([^)]+\)$/g, ""))
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && !line.startsWith("---") && !line.startsWith("|"));
  return trimToLength(body.slice(0, 3).join(" ").replace(/\s+/g, " "), 360);
}

function buildGithubProjectSkillId(sourceFile: GithubSkillSourceFile, rawId: unknown, index = 0) {
  const repoSlug = slugifyProjectSkillId(`${sourceFile.owner}-${sourceFile.repo}`, "github");
  const rawSlug = slugifyProjectSkillId(rawId, path.posix.basename(sourceFile.path).replace(/\.[^.]+$/, "") || `skill-${index + 1}`);
  const hash = createHash("sha1").update(`${sourceFile.owner}/${sourceFile.repo}/${sourceFile.path}#${rawSlug}#${index}`).digest("hex").slice(0, 8);
  return `github-${repoSlug}-${rawSlug}`.slice(0, 86).replace(/-+$/g, "") + `-${hash}`;
}

function normalizeGithubRecommendedFor(...values: unknown[]) {
  return uniqueStrings(values.flatMap((value) => normalizeStringList(value)).map((item) => item.toLowerCase()));
}

function normalizeGithubSkillRecord(skill: Record<string, unknown>, sourceFile: GithubSkillSourceFile, index: number, options: { category?: string; recommendedFor?: string[] }) {
  const metadata = cloneRecord(skill.metadata);
  const rawLabel = text(skill.label ?? metadata.label ?? metadata.name ?? skill.name ?? skill.title, "");
  const label = rawLabel || text(skill.id, "") || path.posix.basename(sourceFile.path).replace(/\.[^.]+$/, "");
  const description = text(skill.note ?? metadata.description ?? skill.description ?? metadata.summary, "");
  const category = text(options.category, "") || text(metadata.category ?? skill.category, "github");
  const recommendedFor = normalizeGithubRecommendedFor(options.recommendedFor, skill.recommended_for, metadata.recommended_for, metadata.tags, skill.tags, category, sourceFile.repo);
  return {
    id: buildGithubProjectSkillId(sourceFile, skill.id ?? metadata.id ?? label, index),
    label,
    note: description ? `从 GitHub 导入：${description}` : "从 GitHub 导入的外部 Skill，请在详情中补充项目化说明。",
    source: "github",
    scope: "role",
    recommended_for: recommendedFor,
    metadata: { ...metadata, category, source_url: sourceFile.sourceUrl, raw_url: sourceFile.rawUrl, external_repo: `${sourceFile.owner}/${sourceFile.repo}`, external_ref: sourceFile.ref, external_path: sourceFile.path, imported_from: "github", imported_format: "json", description },
  };
}

function parseGithubMarkdownSkill(sourceFile: GithubSkillSourceFile, index: number, options: { category?: string; recommendedFor?: string[] }) {
  const frontmatter = parseSimpleFrontmatter(sourceFile.content);
  const heading = extractMarkdownHeading(sourceFile.content);
  const fallbackLabel = path.posix.basename(sourceFile.path).replace(/\.[^.]+$/, "");
  const label = text(frontmatter.label ?? frontmatter.display_name ?? frontmatter.name ?? heading, fallbackLabel);
  const description = text(frontmatter.description ?? frontmatter.summary, "") || extractMarkdownSummary(sourceFile.content);
  const category = text(options.category, "") || text(frontmatter.category, "github");
  const recommendedFor = normalizeGithubRecommendedFor(options.recommendedFor, frontmatter.recommended_for, frontmatter.tags, frontmatter.keywords, category, sourceFile.repo);
  const rawId = frontmatter.id ?? frontmatter.name ?? label;
  return {
    id: buildGithubProjectSkillId(sourceFile, rawId, index),
    label,
    note: sourceFile.importMode === "agent_markdown"
      ? description ? `从 GitHub Agent Markdown 转换：${description}` : "从 GitHub 普通 Agent Markdown 转换的 Skill 草稿。"
      : description ? `从 GitHub 导入：${description}` : "从 GitHub 导入的 Markdown Skill。",
    source: "github",
    scope: "role",
    recommended_for: recommendedFor,
    metadata: { ...frontmatter, category, description: description || `GitHub Markdown Skill：${label}`, source_url: sourceFile.sourceUrl, raw_url: sourceFile.rawUrl, external_repo: `${sourceFile.owner}/${sourceFile.repo}`, external_ref: sourceFile.ref, external_path: sourceFile.path, imported_from: "github", imported_format: sourceFile.importMode === "agent_markdown" ? "agent_markdown" : "markdown", instructions: trimToLength(sourceFile.content, GITHUB_SKILL_STORED_INSTRUCTION_LIMIT) },
  };
}

function parseGithubSkillFile(sourceFile: GithubSkillSourceFile, options: { category?: string; recommendedFor?: string[] }) {
  const extension = path.posix.extname(sourceFile.path).toLowerCase();
  if (extension === ".json") {
    let parsed: unknown;
    try {
      parsed = JSON.parse(sourceFile.content);
    } catch {
      throw new Error(`GitHub JSON Skill 解析失败：${sourceFile.path}`);
    }
    const payload = parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
    const rawItems = Array.isArray(payload.skill_library) ? payload.skill_library : Array.isArray(payload.skills) ? payload.skills : Array.isArray(parsed) ? parsed : [payload];
    return rawItems.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object")).map((item, index) => normalizeGithubSkillRecord(item, sourceFile, index, options));
  }
  return [parseGithubMarkdownSkill(sourceFile, 0, options)];
}

async function readUpstreamJson(pathname: string, token: string) {
  const res = await fetch(`${getApiBaseUrl()}${pathname}`, {
    cache: "no-store",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.error?.message ?? `HTTP ${res.status}`);
  return json?.data ?? json;
}

async function patchUpstreamJson(pathname: string, token: string, body: Record<string, unknown>) {
  const res = await fetch(`${getApiBaseUrl()}${pathname}`, {
    method: "PATCH",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.error?.message ?? `HTTP ${res.status}`);
  return json?.data ?? json;
}

export async function POST(request: Request, ctx: { params: { id: string } }) {
  const projectId = ctx.params.id;
  const formData = await request.formData();
  const returnTo = safeReturnTo(projectId, formData.get("return_to"));
  try {
    const token = cookies().get(ACCESS_TOKEN_COOKIE)?.value ?? "";
    if (!token) throw new Error("登录态已过期，请重新登录后再导入 Skill。");
    const githubUrl = text(formData.get("github_url"), "");
    if (!githubUrl) throw new Error("请先粘贴 GitHub repo、目录、blob 或 raw 文件地址。");
    const target = parseGithubUrl(githubUrl, text(formData.get("github_path"), ""), text(formData.get("github_branch"), ""));
    const sourceFiles = await readGithubSkillSourceFiles(target);
    const importedSkills = sourceFiles
      .flatMap((sourceFile) => parseGithubSkillFile(sourceFile, {
        category: text(formData.get("category"), "github"),
        recommendedFor: parseStringList(formData.get("recommended_for")),
      }))
      .filter((item) => text(item.id, "") && text(item.label, ""))
      .slice(0, GITHUB_SKILL_IMPORT_MAX_SKILLS);
    if (!importedSkills.length) throw new Error("GitHub 内容里没有解析出可导入的 Skill，请确认文件是 Markdown 或 JSON Skill。");

    const project = await readUpstreamJson(`/api/projects/${encodeURIComponent(projectId)}`, token);
    const collaborationConfig = project?.collaboration_config && typeof project.collaboration_config === "object" ? { ...(project.collaboration_config as Record<string, unknown>) } : {};
    const currentSkillLibrary = Array.isArray(collaborationConfig.skill_library) ? [...(collaborationConfig.skill_library as Record<string, unknown>[])] : [];
    const currentSkillMap = new Map(currentSkillLibrary.map((item, index) => [text(item.id, "").toLowerCase(), { item, index }] as const).filter(([id]) => Boolean(id)));
    const nextSkills = [...currentSkillLibrary];
    let addedCount = 0;
    let updatedCount = 0;
    importedSkills.forEach((skill) => {
      const key = text(skill.id, "").toLowerCase();
      const existing = currentSkillMap.get(key);
      if (!existing) {
        addedCount += 1;
        nextSkills.push(skill);
        currentSkillMap.set(key, { item: skill, index: nextSkills.length - 1 });
        return;
      }
      if (JSON.stringify(existing.item) !== JSON.stringify(skill)) {
        updatedCount += 1;
        nextSkills[existing.index] = skill;
        currentSkillMap.set(key, { item: skill, index: existing.index });
      }
    });

    await patchUpstreamJson(`/api/projects/${encodeURIComponent(projectId)}`, token, {
      collaboration_config: { ...collaborationConfig, skill_library: sortProjectSkillLibrary(nextSkills) },
    });
    const repoLabel = `${target.owner}/${target.repo}`;
    const summary = addedCount || updatedCount
      ? `已从 GitHub 导入 Skill：${repoLabel} / 文件 ${sourceFiles.length} 个 / 新增 ${addedCount} 条 / 更新 ${updatedCount} 条`
      : `GitHub Skill 已是最新：${repoLabel} / ${importedSkills.length} 条`;
    return NextResponse.redirect(withResult(returnTo, "team_notice", summary, request.url));
  } catch (error) {
    return NextResponse.redirect(withResult(returnTo, "team_error", error instanceof Error ? error.message : "导入 GitHub Skill 失败", request.url));
  }
}
