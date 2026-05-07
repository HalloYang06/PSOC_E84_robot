type AnyRecord = Record<string, any>;

export type NpcKnowledgeProfile = {
  key: string;
  slug: string;
  title: string;
  summary: string;
  handoff_path: string;
  tags: string[];
  continuity_mode: "persistent_npc_identity";
  continuity_note: string;
};

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function normalizeList(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((item) => text(item)).filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

function looksCorruptedText(value: unknown) {
  const next = text(value);
  if (!next) return false;
  if (/\?{3,}/.test(next)) return true;
  if (/[�]/.test(next)) return true;
  return /(?:鍦|绂|鐮|寮|鏈|浠|鍗|闃|涓|绾|锟|搴勫洯)/.test(next);
}

function cleanKnowledgeText(value: unknown, fallback = "") {
  const next = text(value);
  if (!next) return fallback;
  return looksCorruptedText(next) ? fallback : next;
}

function shortHash(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash.toString(36).slice(0, 6) || "seat";
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

export function defaultNpcKnowledgeSlug(options: {
  knowledgeSlug?: string | null;
  name?: string | null;
  responsibility?: string | null;
  seatId?: string | null;
}) {
  const explicit = slugify(text(options.knowledgeSlug));
  if (explicit) return explicit;
  const base =
    slugify(text(options.name)) ||
    slugify(text(options.responsibility)) ||
    slugify(text(options.seatId)) ||
    "npc";
  const fingerprint = shortHash(
    [text(options.name), text(options.responsibility), text(options.seatId)].filter(Boolean).join("|") || base,
  );
  return `${base}-${fingerprint}`;
}

export function defaultNpcKnowledgeHandoffPath(slug: string) {
  return `docs/ai-handoffs/npc-memory/${slug}.md`;
}

export function defaultNpcKnowledgeSummary(options: {
  name?: string | null;
  responsibility?: string | null;
}) {
  const seatName = text(options.name, "这个 NPC");
  const responsibility = text(options.responsibility, "当前职责");
  return `${seatName} 是固定 NPC 席位，负责 ${responsibility}。线程、电脑和模型可以切换，但交接记忆、历史决策和知识库路径不能丢。`;
}

export function buildNpcKnowledgeProfile(options: {
  knowledgeSlug?: string | null;
  knowledgeTitle?: string | null;
  knowledgeSummary?: string | null;
  knowledgeHandoffPath?: string | null;
  knowledgeTags?: string[] | string | null;
  name?: string | null;
  responsibility?: string | null;
  seatId?: string | null;
}) {
  const slug = defaultNpcKnowledgeSlug(options);
  const handoffPath = text(options.knowledgeHandoffPath, defaultNpcKnowledgeHandoffPath(slug));
  const title = cleanKnowledgeText(options.knowledgeTitle, `${text(options.name, "NPC")} 固定知识库`);
  const summary = cleanKnowledgeText(options.knowledgeSummary, defaultNpcKnowledgeSummary(options));
  const tags = Array.from(
    new Set(
      ["npc", "continuity", ...normalizeList(options.knowledgeTags), text(options.responsibility)]
        .map((item) => text(item).toLowerCase())
        .filter(Boolean),
    ),
  );
  return {
    key: `npc:${slug}`,
    slug,
    title,
    summary,
    handoff_path: handoffPath,
    tags,
    continuity_mode: "persistent_npc_identity" as const,
    continuity_note:
      "Keep predecessor handoffs and verified context. Changing thread, computer, or model only changes the current execution shell.",
  } satisfies NpcKnowledgeProfile;
}

export function resolveNpcKnowledgeProfile(
  seat: AnyRecord | null | undefined,
  options?: {
    fallbackName?: string | null;
    fallbackResponsibility?: string | null;
  },
) {
  const metadata =
    seat?.metadata && typeof seat.metadata === "object" ? (seat.metadata as AnyRecord) : {};
  const stored =
    metadata.npc_knowledge && typeof metadata.npc_knowledge === "object"
      ? (metadata.npc_knowledge as AnyRecord)
      : {};
  return buildNpcKnowledgeProfile({
    seatId: text(seat?.id ?? seat?.config_id ?? seat?.row_id),
    name: text(seat?.name, text(options?.fallbackName)),
    responsibility: text(
      seat?.responsibility ?? metadata.responsibility,
      text(options?.fallbackResponsibility),
    ),
    knowledgeSlug: text(stored.slug ?? metadata.npc_identity_key).replace(/^npc:/, ""),
    knowledgeTitle: text(stored.title),
    knowledgeSummary: text(stored.summary),
    knowledgeHandoffPath: text(stored.handoff_path),
    knowledgeTags: stored.tags,
  });
}
