type AnyRecord = Record<string, any>;

export type PlatformSkillRecord = {
  id: string;
  label: string;
  note: string;
  source: string;
  scope: "baseline" | "role";
  recommended_for?: string[];
  doc_path?: string;
  required?: boolean;
  category?: string;
  metadata?: AnyRecord;
};

export type PlatformSkillStarterKit = {
  id: string;
  label: string;
  note: string;
  skill_ids: string[];
};

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

export const DEFAULT_PLATFORM_SKILL_LIBRARY: PlatformSkillRecord[] = [
  {
    id: "github-repo-bootstrap",
    label: "GitHub 拉代码启动",
    note: "没有本地项目时，先用项目 GitHub 地址在当前电脑自行选择路径 clone，再继续接单；不要假设每台电脑路径一样。",
    source: "platform-baseline",
    scope: "baseline",
    required: true,
    category: "固定必备",
    recommended_for: ["github", "repo", "clone", "bootstrap", "远程电脑", "本地路径"],
  },
  {
    id: "ai-collab-productizer",
    label: "平台产品化推进",
    note: "先收主链，再补真实派单、回执和闭环；不要做 demo 式分叉，所有能力都要能被真实用户稳定使用。",
    source: "platform-baseline",
    scope: "baseline",
    required: true,
    category: "固定必备",
    recommended_for: ["platform", "product", "loop", "产品化", "闭环"],
  },
  {
    id: "continuous-orchestrator",
    label: "持续协作推进",
    note: "不等人催，持续接单、续推、检查阻塞并推动协作；但遇到高风险或自动化边界必须停下来人审。",
    source: "platform-baseline",
    scope: "baseline",
    required: true,
    category: "固定必备",
    recommended_for: ["autonomy", "orchestrator", "loop", "自动化", "心跳"],
  },
  {
    id: "handoff-path-output",
    label: "交接路径输出",
    note: "每轮都要留下明确 handoff 路径，不能依赖旧聊天记录；下一任 AI 必须能从 Git 和文档继续。",
    source: "platform-baseline",
    scope: "baseline",
    required: true,
    category: "固定必备",
    recommended_for: ["handoff", "doc", "continuation", "交接"],
  },
  {
    id: "verify-before-claim",
    label: "先验证再认领完成",
    note: "每轮都要跑 build、pytest、fresh 截图或等价验收；防跑偏、防假完成、防旧缓存污染。",
    source: "platform-baseline",
    scope: "baseline",
    required: true,
    category: "固定必备",
    recommended_for: ["verify", "build", "pytest", "screenshot", "acceptance", "截图"],
  },
  {
    id: "ai-required-requirement-ledger",
    label: "AI 必读需求表",
    note: "每个 NPC 开工前必须先读 docs/ai-requirements/ai-required-requirements-ledger.md：确认提需求者、被提需求者、任务正文、人审边界、完成后回给谁，以及是否允许自动续推。",
    source: "platform-baseline",
    scope: "baseline",
    required: true,
    category: "固定必备",
    doc_path: "docs/ai-requirements/ai-required-requirements-ledger.md",
    metadata: {
      category: "project-management",
      description:
        "适合担任 AI 协作契约守门位，重点负责需求表、派单边界、人审规则、最小回执、最终回复和下一步需求记录。常用于多 NPC 协作前的开工必读、上下文控制和跨 NPC 接力。",
      preferred_stations: ["协作调度工位", "需求拆解工位", "审核工位", "交付工位"],
      deliverables: ["AI 必读需求表", "人工审核边界", "派单回执协议", "下一步需求记录"],
      matching_text: "requirement ledger review approval token-control handoff dispatch ack final reply",
    },
    recommended_for: ["requirement", "ledger", "review", "approval", "handoff", "token-control", "需求表", "人审"],
  },
  {
    id: "browser-game-ui-architect",
    label: "游戏界面与 NPC 交互",
    note: "适合农场地图、HUD、NPC 面板、Enter 交互和可玩界面收口。",
    source: "platform-role",
    scope: "role",
    category: "前端/游戏",
    recommended_for: ["ui", "game", "map", "npc", "farm", "phaser", "frontend", "地图", "交互"],
  },
  {
    id: "frontend-skill",
    label: "前端落地与视觉收口",
    note: "适合首屏、可视层、组件排布、交互细节和移动端落地。",
    source: "platform-role",
    scope: "role",
    category: "前端/游戏",
    recommended_for: ["ui", "frontend", "visual", "layout", "interaction", "页面", "视觉"],
  },
  {
    id: "git-boundary-keeper",
    label: "Git 边界与结果回流",
    note: "适合仓库边界、分支提交、结果回流和多人协作冲突收口。",
    source: "platform-role",
    scope: "role",
    category: "工程协作",
    recommended_for: ["git", "repo", "branch", "merge", "boundary", "result", "仓库", "分支"],
  },
  {
    id: "dispatch-ack-closer",
    label: "派单与最小回执闭环",
    note: "适合派单、接单确认、过程回执和完成回执收口。",
    source: "platform-role",
    scope: "role",
    category: "协作闭环",
    recommended_for: ["dispatch", "ack", "receipt", "relay", "runner", "task", "派单", "回执"],
  },
  {
    id: "final-reply-closer",
    label: "最终回复与续推收口",
    note: "适合最终回复、下一步需求记录、自检和闭环补偿。",
    source: "platform-role",
    scope: "role",
    category: "协作闭环",
    recommended_for: ["final", "reply", "closure", "followup", "requirement", "result", "最终回复", "续推"],
  },
  {
    id: "review-gatekeeper",
    label: "人工审核与风控分流",
    note: "适合区分自动推进与等待人工审核的边界、证据说明和上下文控制。",
    source: "platform-role",
    scope: "role",
    category: "安全/审核",
    recommended_for: ["review", "approval", "audit", "human", "risk", "gate", "人审", "风险"],
  },
  {
    id: "thread-bridge-writeback",
    label: "线程同步与平台写回",
    note: "适合线程侧接单、电脑端同步、待办同步与平台回执写回。",
    source: "platform-role",
    scope: "role",
    category: "多电脑/线程",
    recommended_for: ["thread", "sync", "writeback", "todo", "receipt", "platform", "线程", "同步"],
  },
];

export const PLATFORM_SKILL_STARTER_KITS: PlatformSkillStarterKit[] = [
  {
    id: "ui-npc-kit",
    label: "游戏界面 / NPC 套装",
    note: "给负责农场界面、地图 NPC 和交互的线程。",
    skill_ids: ["browser-game-ui-architect", "frontend-skill"],
  },
  {
    id: "dispatch-loop-kit",
    label: "派单闭环 / 回执套装",
    note: "给负责派单、回执、最终回复和自动续推的 NPC。",
    skill_ids: ["dispatch-ack-closer", "final-reply-closer", "thread-bridge-writeback"],
  },
  {
    id: "review-git-kit",
    label: "审核 / Git 协作套装",
    note: "给负责仓库边界、审核门和结果回流的线程。",
    skill_ids: ["git-boundary-keeper", "review-gatekeeper"],
  },
];

export const PLATFORM_BASELINE_SKILL_IDS = DEFAULT_PLATFORM_SKILL_LIBRARY.filter((skill) => skill.scope === "baseline").map(
  (skill) => skill.id,
);

export const RESERVED_PLATFORM_SKILL_IDS = DEFAULT_PLATFORM_SKILL_LIBRARY.map((skill) => skill.id);

export function isBaselineSkill(skill: AnyRecord) {
  return text(skill.scope ?? skill.source, "").toLowerCase() === "baseline" || text(skill.source, "") === "platform-baseline";
}

function normalizeSkillList(value: unknown) {
  const skills = Array.isArray(value) ? value : typeof value === "string" ? value.split(/[\n,]/) : [];
  return skills.map((item) => text(item)).filter(Boolean);
}

export function mergePlatformSkillLoadout(...values: unknown[]) {
  const merged = [...PLATFORM_BASELINE_SKILL_IDS];
  values.forEach((value) => {
    merged.push(...normalizeSkillList(value));
  });
  return Array.from(new Set(merged));
}

export function splitPlatformSkillLoadout(value: unknown, skillLibrary: AnyRecord[]) {
  const allSkillIds = mergePlatformSkillLoadout(value);
  const baselineIdSet = new Set(
    [...PLATFORM_BASELINE_SKILL_IDS, ...skillLibrary.filter((skill) => isBaselineSkill(skill)).map((skill) => text(skill.id))]
      .filter(Boolean)
      .map((item) => item.toLowerCase()),
  );
  const baselineSkillIds: string[] = [];
  const roleSkillIds: string[] = [];
  allSkillIds.forEach((skillId) => {
    if (baselineIdSet.has(skillId.toLowerCase())) baselineSkillIds.push(skillId);
    else roleSkillIds.push(skillId);
  });
  return { allSkillIds, baselineSkillIds, roleSkillIds };
}

function tokenize(value: string) {
  return value
    .toLowerCase()
    .split(/[^a-z0-9\u4e00-\u9fff]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function contextHints(roleText: string, threadText: string) {
  const raw = `${roleText} ${threadText}`.toLowerCase();
  const hints = new Set<string>(tokenize(raw));
  const mappings: Array<[RegExp, string[]]> = [
    [/(ui|front|界面|前端|视觉|展示)/, ["ui", "frontend", "visual", "layout"]],
    [/(game|map|农场|地图|npc|交互|phaser)/, ["game", "map", "npc", "farm", "interaction"]],
    [/(git|repo|仓库|分支|回流|merge)/, ["git", "repo", "branch", "merge", "result"]],
    [/(dispatch|派单|ack|回执|runner|线程|relay|同步)/, ["dispatch", "ack", "runner", "thread", "relay", "sync"]],
    [/(final|reply|最终回复|结果|续推|follow)/, ["final", "reply", "closure", "followup", "result"]],
    [/(review|审核|审批|人审|风险|proof|验收|截图)/, ["review", "approval", "audit", "human", "risk", "verify", "screenshot"]],
    [/(requirement|需求|需求表|ledger|必读|token)/, ["requirement", "ledger", "token-control", "review"]],
  ];
  mappings.forEach(([pattern, tokens]) => {
    if (pattern.test(raw)) {
      tokens.forEach((token) => hints.add(token));
    }
  });
  return hints;
}

function recommendedTokens(skill: AnyRecord) {
  const tokens = new Set<string>();
  normalizeSkillList(skill.recommended_for).forEach((item) => tokenize(item).forEach((token) => tokens.add(token)));
  [text(skill.id), text(skill.label), text(skill.note), text(skill.category)].forEach((value) => {
    tokenize(value).forEach((token) => tokens.add(token));
  });
  return tokens;
}

export function recommendRoleSkillIds(options: {
  roleText?: string;
  threadText?: string;
  skillLibrary: AnyRecord[];
  limit?: number;
}) {
  const { roleText = "", threadText = "", skillLibrary, limit = 4 } = options;
  const hints = contextHints(roleText, threadText);
  return skillLibrary
    .filter((skill) => !isBaselineSkill(skill))
    .map((skill) => {
      const skillId = text(skill.id, "");
      const tokens = recommendedTokens(skill);
      let score = 0;
      tokens.forEach((token) => {
        if (hints.has(token)) score += 3;
      });
      if (roleText && text(skill.label, "").toLowerCase().includes(roleText.toLowerCase())) score += 2;
      if (threadText && text(skill.label, "").toLowerCase().includes(threadText.toLowerCase())) score += 1;
      return { skillId, score };
    })
    .filter((item) => item.skillId && item.score > 0)
    .sort((left, right) => right.score - left.score || left.skillId.localeCompare(right.skillId))
    .slice(0, limit)
    .map((item) => item.skillId);
}
