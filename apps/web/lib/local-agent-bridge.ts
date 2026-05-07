import { mkdir, readFile, writeFile } from "fs/promises";
import { execFileSync } from "node:child_process";
import path from "path";
import { resolvePlatformCollabProtocol } from "./platform-collab-protocol";
import {
  buildPlatformRepoReferencePaths,
  platformRepoContextSummary,
  resolvePlatformRepoContext,
} from "./platform-repo-context";

const DEFAULT_PLATFORM_COLLAB_SKILLS = [
  "github-repo-bootstrap",
  "ai-collab-productizer",
  "continuous-orchestrator",
  "handoff-path-output",
  "verify-before-claim",
] as const;

export type LocalBridgeCommand = {
  id: string;
  projectId: string;
  target: "codex";
  provider?: string | null;
  workstationId: string;
  workstationName: string;
  computerNodeId?: string | null;
  computerNodeLabel?: string | null;
  title: string;
  body: string;
  status: "queued" | "seen" | "done";
  issuer: string;
  createdAt: string;
  route?: "manual_command" | "platform_autonomy" | null;
  sourceMessageId?: string | null;
  sourceRequirementId?: string | null;
  sourceStatus?: string | null;
  skillLoadout?: string[] | null;
  repoSummary?: string | null;
  gitAccessSummary?: string | null;
  referencePaths?: string[] | null;
};

type BridgeRecord = Record<string, unknown>;

function resolveRepoRoot() {
  const cwd = process.cwd();
  const normalized = cwd.replace(/\\/g, "/");
  if (normalized.endsWith("/apps/web")) {
    return path.resolve(cwd, "..", "..");
  }
  return cwd;
}

const ROOT = resolveRepoRoot();
const BRIDGE_DIR = path.join(ROOT, "docs", "ai-handoffs", "inbox");

function readWorkspaceGitDefaults() {
  try {
    const remoteUrl = execFileSync("git", ["remote", "get-url", "origin"], {
      cwd: ROOT,
      encoding: "utf8",
    }).trim();
    const currentBranch = execFileSync("git", ["branch", "--show-current"], {
      cwd: ROOT,
      encoding: "utf8",
    }).trim();
    return {
      githubUrl: remoteUrl || null,
      branch: currentBranch || null,
      localGitUrl: ROOT,
    };
  } catch {
    return {
      githubUrl: null,
      branch: null,
      localGitUrl: ROOT,
    };
  }
}

const WORKSPACE_GIT_DEFAULTS = readWorkspaceGitDefaults();

function bridgeJsonPath(projectId: string) {
  return path.join(BRIDGE_DIR, `project-${projectId}-codex.json`);
}

function bridgeMarkdownPath(projectId: string) {
  return path.join(BRIDGE_DIR, `project-${projectId}-codex.md`);
}

async function ensureBridgeDir() {
  await mkdir(BRIDGE_DIR, { recursive: true });
}

async function readJsonFile<T>(filePath: string, fallback: T): Promise<T> {
  try {
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function text(value: unknown, fallback = "") {
  const resolved = String(value ?? "").trim();
  return resolved || fallback;
}

function questionMarkHeavy(value: string) {
  if (!value) return true;
  const questionMarkCount = value.match(/\?/g)?.length ?? 0;
  return /^\?+$/.test(value) || questionMarkCount >= Math.ceil(value.length / 2);
}

function isCodexSessionTarget(value: unknown) {
  return text(value, "").toLowerCase().startsWith("codex-session-");
}

function workstationLookupKeys(item: BridgeRecord) {
  const metadata = item.metadata && typeof item.metadata === "object" ? (item.metadata as BridgeRecord) : {};
  const extraData = item.extra_data && typeof item.extra_data === "object" ? (item.extra_data as BridgeRecord) : {};
  return Array.from(
    new Set(
      [
        item.id,
        item.workstation_id,
        item.config_id,
        item.row_id,
        item.source_workstation_id,
        metadata.source_workstation_id,
        extraData.source_workstation_id,
      ]
        .map((candidate) => text(candidate, ""))
        .filter(Boolean),
    ),
  );
}

function resolveBridgeProjectRepoOverrides(project?: BridgeRecord | null) {
  const repositoryUrl = normalizeBridgeText(project?.github_url ?? project?.githubUrl, "") || null;
  const branch =
    normalizeBridgeText(
      project?.develop_branch ??
        project?.developBranch ??
        project?.default_branch ??
        project?.defaultBranch,
      "",
    ) || null;
  const localGitUrl = normalizeBridgeText(project?.local_git_url ?? project?.localGitUrl, "") || null;
  return {
    repositoryUrl,
    branch,
    localGitUrl,
  };
}

function normalizeGithubCredentialSource(value: unknown) {
  const normalized = normalizeBridgeText(value, "runner_env");
  return ["github_app", "oauth", "runner_env", "ssh_agent", "manual_review"].includes(normalized)
    ? normalized
    : "runner_env";
}

function githubCredentialSourceLabel(value: unknown) {
  const source = normalizeGithubCredentialSource(value);
  return (
    {
      github_app: "GitHub App",
      oauth: "OAuth 授权",
      runner_env: "Runner 环境变量",
      ssh_agent: "SSH Agent",
      manual_review: "人工审批后手动执行",
    } as Record<string, string>
  )[source];
}

function looksLikeRawGithubCredential(value: unknown) {
  const raw = normalizeBridgeText(value, "");
  if (!raw) return false;
  if (/^(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}$/i.test(raw)) return true;
  if (/^github_pat_[A-Za-z0-9_]{40,}$/i.test(raw)) return true;
  if (/-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(raw)) return true;
  return false;
}

function resolveBridgeGitAccessSummary(project?: BridgeRecord | null) {
  const config =
    project?.collaboration_config && typeof project.collaboration_config === "object"
      ? (project.collaboration_config as BridgeRecord)
      : {};
  const binding =
    config.github_account_binding && typeof config.github_account_binding === "object"
      ? (config.github_account_binding as BridgeRecord)
      : {};
  const accountLogin = normalizeBridgeText(binding.account_login ?? binding.login, "");
  const credentialSource = normalizeGithubCredentialSource(binding.credential_source);
  const credentialRefRaw = normalizeBridgeText(binding.credential_ref, "");
  const credentialRef = looksLikeRawGithubCredential(credentialRefRaw)
    ? "疑似明文密钥（已隐藏，请改用环境变量名）"
    : credentialRefRaw;
  if (!accountLogin && !credentialRef) {
    return "GitHub 账号未绑定；需要写仓库前先回平台请求补账号/凭据来源，禁止在消息里粘明文 token";
  }
  return [
    accountLogin ? `GitHub 身份 ${accountLogin}` : "GitHub 身份待补",
    `凭据 ${githubCredentialSourceLabel(credentialSource)}${credentialRef ? ` / ${credentialRef}` : ""}`,
    "不在项目配置或聊天正文保存明文 token",
  ].join(" / ");
}

function resolveBridgeWorkstationContext(
  workstations: BridgeRecord[],
  workstationId: string,
  project?: BridgeRecord | null,
) {
  const matched =
    workstations.find((item) => workstationLookupKeys(item).some((candidate) => candidate === workstationId)) ?? null;
  const metadata = matched?.metadata && typeof matched.metadata === "object" ? (matched.metadata as BridgeRecord) : {};
  const extraData =
    matched?.extra_data && typeof matched.extra_data === "object" ? (matched.extra_data as BridgeRecord) : {};
  const projectRepoOverrides = resolveBridgeProjectRepoOverrides(project);
  const providerId = normalizeBridgeText(
    matched?.ai_provider_id ??
      matched?.provider_id ??
      metadata.provider_id ??
      extraData.provider_id,
    "",
  );
  const responsibility = normalizeBridgeText(
    matched?.responsibility ?? metadata.responsibility ?? extraData.responsibility,
    "",
  );
  const threadName = normalizeBridgeText(matched?.name ?? matched?.workstation_name, "");
  const collabProtocol = resolvePlatformCollabProtocol(metadata.collab_protocol ?? extraData.collab_protocol, {
    providerId,
    roleText: responsibility,
    threadText: threadName,
    repoContext: {
      repository_url: projectRepoOverrides.repositoryUrl || WORKSPACE_GIT_DEFAULTS.githubUrl,
      branch: projectRepoOverrides.branch || WORKSPACE_GIT_DEFAULTS.branch,
      relative_root: ".",
    },
  });
  const rawRepoContext =
    collabProtocol.repo_context && typeof collabProtocol.repo_context === "object"
      ? (collabProtocol.repo_context as BridgeRecord)
      : {};
  const repoContext = resolvePlatformRepoContext({
    repository_url:
      projectRepoOverrides.repositoryUrl ||
      normalizeBridgeText(rawRepoContext.repository_url ?? rawRepoContext.repositoryUrl, "") ||
      WORKSPACE_GIT_DEFAULTS.githubUrl ||
      null,
    branch:
      projectRepoOverrides.branch ||
      normalizeBridgeText(rawRepoContext.branch, "") ||
      WORKSPACE_GIT_DEFAULTS.branch ||
      null,
    relative_root: normalizeBridgeText(rawRepoContext.relative_root ?? rawRepoContext.relativeRoot, ".") || ".",
  });
  const gitBoundary = normalizeStringList([
    ...(Array.isArray(matched?.git_boundary) ? (matched?.git_boundary as unknown[]) : []),
    ...(Array.isArray(metadata.git_boundary) ? (metadata.git_boundary as unknown[]) : []),
    ...(Array.isArray(extraData.git_boundary) ? (extraData.git_boundary as unknown[]) : []),
  ]);
  const handoffPath =
    normalizeBridgeText(
      metadata.npc_knowledge && typeof metadata.npc_knowledge === "object"
        ? (metadata.npc_knowledge as BridgeRecord).handoff_path
        : extraData.npc_knowledge && typeof extraData.npc_knowledge === "object"
          ? (extraData.npc_knowledge as BridgeRecord).handoff_path
          : "",
      "",
    ) || null;
  const referencePaths = buildPlatformRepoReferencePaths({
    referencePaths: collabProtocol.reference_paths,
    repositoryUrl: repoContext?.repository_url ?? null,
    branch: repoContext?.branch ?? null,
    gitBoundary,
    handoffPath,
    workspaceRoots: [
      ROOT,
      projectRepoOverrides.localGitUrl,
      WORKSPACE_GIT_DEFAULTS.localGitUrl,
      normalizeBridgeText(matched?.local_git_url ?? metadata.local_git_url ?? extraData.local_git_url, ""),
    ].filter((value): value is string => Boolean(value)),
  });
  return {
    workstationName:
      normalizeBridgeText(
        matched?.name ??
          matched?.workstation_name ??
          metadata.display_name ??
          metadata.name ??
          extraData.display_name ??
          extraData.name,
        fallbackWorkstationName(workstationId),
      ) || fallbackWorkstationName(workstationId),
    provider:
      normalizeBridgeText(
        matched?.ai_provider ??
          matched?.ai_provider_label ??
          matched?.provider ??
          metadata.ai_provider ??
          metadata.ai_provider_label ??
          extraData.ai_provider,
        isCodexSessionTarget(workstationId) ? "codex" : "",
      ) || null,
    computerNodeId:
      normalizeBridgeText(
        matched?.computer_node_id ?? matched?.computerNodeId ?? metadata.computer_node_id ?? extraData.computer_node_id,
        "",
      ) || null,
    computerNodeLabel:
      normalizeBridgeText(
        matched?.computer_node ??
          matched?.computerNode ??
          matched?.computer_node_label ??
          matched?.computerNodeLabel ??
          metadata.computer_node ??
          metadata.computer_node_label ??
          extraData.computer_node ??
          extraData.computer_node_label,
        "",
      ) || null,
    skillLoadout: normalizeSkillLoadout([
      ...(Array.isArray(matched?.skill_loadout) ? (matched?.skill_loadout as unknown[]) : []),
      ...(Array.isArray(matched?.skillLoadout) ? (matched?.skillLoadout as unknown[]) : []),
      ...(Array.isArray(metadata.additional_skill_ids) ? (metadata.additional_skill_ids as unknown[]) : []),
      ...(Array.isArray(metadata.skill_loadout) ? (metadata.skill_loadout as unknown[]) : []),
      ...(Array.isArray(extraData.additional_skill_ids) ? (extraData.additional_skill_ids as unknown[]) : []),
      ...(Array.isArray(extraData.skill_loadout) ? (extraData.skill_loadout as unknown[]) : []),
    ]),
    repoSummary: repoContext ? platformRepoContextSummary(repoContext) : null,
    gitAccessSummary: resolveBridgeGitAccessSummary(project),
    referencePaths,
  };
}

const LATIN1_MOJIBAKE_MARKER_REGEX = /(?:Ã.|Â.|â.|ðŸ|ï¿|¢|¤|¦|œ|ž|€|™)/;
const COMMON_MOJIBAKE_MARKER_REGEX =
  /(?:鍦ㄧ嚎|绂荤嚎|鐮斿彂鍩哄湴|寮€|鏈懡|浠诲姟|搴勫洯|蹇欒|鑱|顏|闄|娼|褰|閹|劏|绻)/g;

function mojibakeScore(value: string): number {
  if (!value) return 0;
  const latinMarkers = value.match(/(?:Ã.|Â.|â.|ðŸ|ï¿|¢|¤|¦|œ|ž|€|™)/g);
  const commonMarkers = value.match(COMMON_MOJIBAKE_MARKER_REGEX);
  return (latinMarkers?.length ?? 0) * 2 + (commonMarkers?.length ?? 0) * 3;
}

function decodeLikelyLatin1Mojibake(value: string): string {
  if (!LATIN1_MOJIBAKE_MARKER_REGEX.test(value)) return value;
  const bytes: number[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const charCode = value.charCodeAt(index);
    if (charCode > 0xff) return value;
    bytes.push(charCode);
  }
  try {
    const decoded = new TextDecoder("utf-8", { fatal: false }).decode(Uint8Array.from(bytes));
    if (!decoded) return value;
    return mojibakeScore(decoded) < mojibakeScore(value) ? decoded : value;
  } catch {
    return value;
  }
}

function looksPollutedText(value: string) {
  const normalized = value.trim();
  if (!normalized) return true;
  if (questionMarkHeavy(normalized)) return true;
  if (/[\uFFFD�]/.test(normalized)) return true;
  return mojibakeScore(normalized) >= 3;
}

function normalizeBridgeText(value: unknown, fallback = "") {
  if (value === null || value === undefined) return fallback;
  const normalized = decodeLikelyLatin1Mojibake(String(value).replace(/\r\n?/g, "\n")).trim();
  if (!normalized) return fallback;
  return looksPollutedText(normalized) ? fallback : normalized;
}

function normalizeSkillLoadout(value: unknown) {
  const values = Array.isArray(value) ? value : typeof value === "string" ? value.split(/[\n,]/) : [];
  const merged = [...values, ...DEFAULT_PLATFORM_COLLAB_SKILLS]
    .map((item) => String(item ?? "").trim())
    .filter(Boolean);
  return Array.from(new Set(merged));
}

function normalizeStringList(value: unknown) {
  const values = Array.isArray(value) ? value : typeof value === "string" ? value.split(/[\n,]/) : [];
  return Array.from(
    new Set(
      values
        .map((item) => normalizeBridgeText(item, ""))
        .filter(Boolean),
    ),
  );
}

function normalizeBridgeStatus(value: unknown): "queued" | "seen" | "done" {
  const normalized = text(value, "").toLowerCase();
  if (["done", "completed", "resolved"].includes(normalized)) return "done";
  if (normalized === "seen") return "seen";
  return "queued";
}

function fallbackWorkstationName(workstationId: string) {
  if (workstationId.toLowerCase().startsWith("codex-session-")) {
    return `Codex 线程 ${workstationId.slice(-6)}`;
  }
  return workstationId || "Codex 线程";
}

function fallbackCommandTitle(input: {
  sourceRequirementId?: string | null;
  workstationId?: string | null;
  workstationName?: string | null;
}) {
  const requirementId = text(input.sourceRequirementId, "");
  if (requirementId) return `Requirement ${requirementId.slice(0, 8)}`;
  const workstationName = text(input.workstationName, "") || fallbackWorkstationName(text(input.workstationId, ""));
  return `平台派单 / ${workstationName}`;
}

function fallbackCommandBody(input: {
  sourceRequirementId?: string | null;
  provider?: string | null;
  workstationId?: string | null;
  workstationName?: string | null;
}) {
  const provider = normalizeBridgeText(input.provider, "Codex");
  const workstationName = normalizeBridgeText(
    input.workstationName,
    fallbackWorkstationName(text(input.workstationId, "")),
  );
  const requirementId = text(input.sourceRequirementId, "");
  if (requirementId) {
    return `${provider} 已向 ${workstationName} 派发 Requirement ${requirementId.slice(0, 8)}，请在线程中查看详情。`;
  }
  return `${provider} 已向 ${workstationName} 派发平台指令，请在线程中查看详情。`;
}

function normalizeStoredCommand(raw: Partial<LocalBridgeCommand> & Record<string, unknown>, projectId: string) {
  const workstationId = text(raw.workstationId ?? raw.workstation_id, "codex-mainline");
  const sourceRequirementId = text(raw.sourceRequirementId ?? raw.source_requirement_id, "") || null;
  const provider = normalizeBridgeText(
    raw.provider,
    workstationId.toLowerCase().startsWith("codex-session-") ? "codex" : "",
  );
  const workstationName = normalizeBridgeText(
    raw.workstationName ?? raw.workstation_name,
    fallbackWorkstationName(workstationId),
  );
  const computerNodeId = normalizeBridgeText(raw.computerNodeId ?? raw.computer_node_id, "") || null;
  const computerNodeLabel =
    normalizeBridgeText(raw.computerNodeLabel ?? raw.computer_node_label, computerNodeId || "") || null;
  const title = normalizeBridgeText(
    raw.title,
    fallbackCommandTitle({
      sourceRequirementId,
      workstationId,
      workstationName,
    }),
  );
  const body = normalizeBridgeText(
    raw.body,
    fallbackCommandBody({
      sourceRequirementId,
      provider,
      workstationId,
      workstationName,
    }),
  );

  return {
    id: text(raw.id, `codex-${Date.now()}`),
    projectId: text(raw.projectId ?? raw.project_id, projectId),
    target: "codex" as const,
    provider: provider || null,
    workstationId,
    workstationName,
    computerNodeId,
    computerNodeLabel,
    title,
    body,
    status: normalizeBridgeStatus(raw.sourceStatus ?? raw.status),
    issuer: normalizeBridgeText(raw.issuer, "平台自治推进"),
    createdAt: text(raw.createdAt ?? raw.created_at, "") || new Date().toISOString(),
    route:
      text(raw.route, "").toLowerCase() === "platform_autonomy"
        ? "platform_autonomy"
        : "manual_command",
    sourceMessageId: text(raw.sourceMessageId ?? raw.source_message_id, "") || null,
    sourceRequirementId,
    sourceStatus: text(raw.sourceStatus ?? raw.source_status, "") || null,
    skillLoadout: normalizeSkillLoadout(raw.skillLoadout ?? raw.skill_loadout),
    repoSummary: normalizeBridgeText(raw.repoSummary ?? raw.repo_summary, "") || null,
    gitAccessSummary: normalizeBridgeText(raw.gitAccessSummary ?? raw.git_access_summary, "") || null,
    referencePaths: normalizeStringList(raw.referencePaths ?? raw.reference_paths),
  } satisfies LocalBridgeCommand;
}

function buildMarkdown(projectId: string, commands: LocalBridgeCommand[]) {
  const sections = commands.map((command) =>
    [
      `## ${command.createdAt}`,
      `- 目标：Codex / ${command.workstationName}`,
      `- 工位 ID：${command.workstationId}`,
      command.provider ? `- Provider：${command.provider}` : "",
      command.computerNodeLabel ? `- 电脑：${command.computerNodeLabel}` : "",
      command.computerNodeId ? `- 电脑 ID：${command.computerNodeId}` : "",
      command.skillLoadout?.length ? `- Skills：${command.skillLoadout.join(", ")}` : "",
      command.repoSummary ? `- 仓库协作：${command.repoSummary}` : "",
      command.gitAccessSummary ? `- GitHub 权限：${command.gitAccessSummary}` : "",
      command.referencePaths?.length ? `- 参考资料：${command.referencePaths.join(" / ")}` : "",
      `- 发起人：${command.issuer}`,
      `- 标题：${command.title}`,
      `- 状态：${command.status}`,
      command.route ? `- 路由：${command.route}` : "",
      command.sourceRequirementId ? `- Requirement：${command.sourceRequirementId}` : "",
      command.sourceMessageId ? `- Message：${command.sourceMessageId}` : "",
      command.sourceStatus ? `- 平台状态：${command.sourceStatus}` : "",
      `- 内容：${command.body}`,
      "",
    ]
      .filter(Boolean)
      .join("\n"),
  );

  return `# 项目 ${projectId} / Codex 收件箱\n\n${sections.join("")}`;
}

async function writeBridgeSnapshot(projectId: string, commands: LocalBridgeCommand[]) {
  await ensureBridgeDir();
  const normalized = commands
    .map((command) => normalizeStoredCommand(command, projectId))
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  await writeFile(bridgeJsonPath(projectId), JSON.stringify(normalized, null, 2), "utf8");
  await writeFile(bridgeMarkdownPath(projectId), buildMarkdown(projectId, normalized), "utf8");
  return normalized;
}

export async function readProjectCodexCommands(projectId: string): Promise<LocalBridgeCommand[]> {
  await ensureBridgeDir();
  const rawCommands = await readJsonFile<Array<Partial<LocalBridgeCommand> & Record<string, unknown>>>(
    bridgeJsonPath(projectId),
    [],
  );
  const normalized = rawCommands
    .map((command) => normalizeStoredCommand(command, projectId))
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  if (JSON.stringify(rawCommands) !== JSON.stringify(normalized)) {
    return writeBridgeSnapshot(projectId, normalized);
  }
  return normalized;
}

export async function appendProjectCodexCommand(input: {
  projectId: string;
  title: string;
  body: string;
  issuer?: string;
  workstationId: string;
  workstationName?: string;
  provider?: string;
  computerNodeId?: string;
  computerNodeLabel?: string;
  status?: "queued" | "seen" | "done";
  route?: "manual_command" | "platform_autonomy";
  sourceMessageId?: string;
  sourceRequirementId?: string;
  sourceStatus?: string;
  skillLoadout?: string[];
  repoSummary?: string;
  gitAccessSummary?: string;
  referencePaths?: string[];
}) {
  await ensureBridgeDir();

  const commands = await readProjectCodexCommands(input.projectId);
  const sourceMessageId = input.sourceMessageId?.trim() || null;
  if (sourceMessageId) {
    const existing = commands.find((item) => item.sourceMessageId === sourceMessageId) ?? null;
    if (existing) {
      const updated = normalizeStoredCommand(
        {
          ...existing,
          provider: input.provider?.trim() || existing.provider || "codex",
          workstationId: input.workstationId.trim() || existing.workstationId || "codex-mainline",
          workstationName:
            input.workstationName?.trim() || existing.workstationName || input.workstationId.trim() || "Codex 主工位",
          computerNodeId: input.computerNodeId?.trim() || existing.computerNodeId || null,
          computerNodeLabel: input.computerNodeLabel?.trim() || existing.computerNodeLabel || null,
          title: input.title.trim() || existing.title,
          body: input.body.trim() || existing.body,
          status: input.status ?? existing.status,
          issuer: input.issuer?.trim() || existing.issuer,
          route: input.route ?? existing.route ?? "manual_command",
          sourceMessageId,
          sourceRequirementId: input.sourceRequirementId?.trim() || existing.sourceRequirementId || null,
          sourceStatus: input.sourceStatus?.trim() || existing.sourceStatus || null,
          skillLoadout: input.skillLoadout ?? existing.skillLoadout ?? [],
          repoSummary: input.repoSummary?.trim() || existing.repoSummary || null,
          gitAccessSummary: input.gitAccessSummary?.trim() || existing.gitAccessSummary || null,
          referencePaths: input.referencePaths ?? existing.referencePaths ?? [],
          createdAt: existing.createdAt,
        },
        input.projectId,
      );
      if (JSON.stringify(existing) !== JSON.stringify(updated)) {
        const next = await writeBridgeSnapshot(
          input.projectId,
          commands.map((item) => (item.sourceMessageId === sourceMessageId ? updated : item)),
        );
        return { command: next.find((item) => item.sourceMessageId === sourceMessageId) ?? updated, created: false };
      }
      return { command: existing, created: false };
    }
  }

  const command = normalizeStoredCommand(
    {
      id: `codex-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      projectId: input.projectId,
      target: "codex",
      provider: input.provider?.trim() || "codex",
      workstationId: input.workstationId.trim() || "codex-mainline",
      workstationName: input.workstationName?.trim() || input.workstationId.trim() || "Codex 主工位",
      computerNodeId: input.computerNodeId?.trim() || null,
      computerNodeLabel: input.computerNodeLabel?.trim() || null,
      title: input.title.trim() || "未命名指令",
      body: input.body.trim(),
      status: input.status ?? "queued",
      issuer: input.issuer?.trim() || "平台自治推进",
      createdAt: new Date().toISOString(),
      route: input.route ?? "manual_command",
      sourceMessageId,
      sourceRequirementId: input.sourceRequirementId?.trim() || null,
      sourceStatus: input.sourceStatus?.trim() || null,
      skillLoadout: input.skillLoadout ?? [],
      repoSummary: input.repoSummary?.trim() || null,
      gitAccessSummary: input.gitAccessSummary?.trim() || null,
      referencePaths: input.referencePaths ?? [],
    },
    input.projectId,
  );

  const next = await writeBridgeSnapshot(input.projectId, [command, ...commands]);
  const createdCommand = next.find((item) => item.id === command.id) ?? command;
  return { command: createdCommand, created: true };
}

export async function syncProjectCodexDispatchInboxFromRecords(input: {
  projectId: string;
  dispatchMessages: BridgeRecord[];
  workstations?: BridgeRecord[];
  project?: BridgeRecord | null;
  issuer?: string;
}) {
  const workstations = Array.isArray(input.workstations) ? input.workstations : [];
  const messages = Array.isArray(input.dispatchMessages) ? input.dispatchMessages : [];
  const sortedMessages = [...messages].sort((left, right) => {
    const rightAt = new Date(text(right.updated_at ?? right.created_at, "1970-01-01T00:00:00.000Z")).getTime();
    const leftAt = new Date(text(left.updated_at ?? left.created_at, "1970-01-01T00:00:00.000Z")).getTime();
    return rightAt - leftAt;
  });

  let synced = 0;
  for (const message of sortedMessages) {
    const recipientId = text(message.recipient_id ?? message.agent_id, "");
    if (!isCodexSessionTarget(recipientId)) continue;

    const requirementId = text(message.requirement_id, "");
    const status = text(message.status, "queued");
    const workstationContext = resolveBridgeWorkstationContext(workstations, recipientId, input.project);
    const body = [
      text(message.body, ""),
      requirementId ? `Requirement: ${requirementId}` : "",
      status ? `Platform status: ${status}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    const { created } = await appendProjectCodexCommand({
      projectId: input.projectId,
      title: text(message.title, "平台新指令"),
      body,
      issuer: input.issuer || "平台自治推进",
      workstationId: recipientId,
      workstationName: workstationContext.workstationName,
      provider: workstationContext.provider || undefined,
      computerNodeId: workstationContext.computerNodeId || undefined,
      computerNodeLabel: workstationContext.computerNodeLabel || undefined,
      status: status === "done" ? "done" : status === "seen" ? "seen" : "queued",
      route: "platform_autonomy",
      sourceMessageId: text(message.id, ""),
      sourceRequirementId: requirementId,
      sourceStatus: status,
      skillLoadout: workstationContext.skillLoadout,
      repoSummary: workstationContext.repoSummary || undefined,
      gitAccessSummary: workstationContext.gitAccessSummary || undefined,
      referencePaths: workstationContext.referencePaths,
    });
    if (created) synced += 1;
  }

  return synced;
}
