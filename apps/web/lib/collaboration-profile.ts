export type CollaborationProfile = {
  provider?: string;
  computer?: string;
  thread?: string;
  project?: string;
  role?: string;
  status?: string;
  note?: string;
  skills?: string[];
};

function normalizeParts(value: string) {
  return value
    .split(/[，,、\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseSkills(value: string) {
  return normalizeParts(value);
}

export function buildProfileNote(profile: CollaborationProfile) {
  const lines: string[] = [];
  if (profile.provider) lines.push(`提供方：${profile.provider}`);
  if (profile.computer) lines.push(`电脑：${profile.computer}`);
  if (profile.thread) lines.push(`线程：${profile.thread}`);
  if (profile.project) lines.push(`项目：${profile.project}`);
  if (profile.role) lines.push(`职责：${profile.role}`);
  if (profile.status) lines.push(`状态：${profile.status}`);
  if (profile.skills?.length) lines.push(`技能：${profile.skills.join("、")}`);
  if (profile.note) lines.push(`备注：${profile.note}`);
  return lines.join("\n");
}

export function parseProfileNote(note?: string | null): CollaborationProfile {
  if (!note) return {};
  const result: CollaborationProfile = {};
  for (const line of note.split(/\n+/)) {
    const [rawKey, ...rest] = line.split(/[：:]/);
    const key = rawKey?.trim();
    const value = rest.join(":").trim();
    if (!key || !value) continue;
    if (key.includes("提供方")) result.provider = value;
    if (key.includes("电脑")) result.computer = value;
    if (key.includes("线程")) result.thread = value;
    if (key.includes("项目")) result.project = value;
    if (key.includes("职责")) result.role = value;
    if (key.includes("状态")) result.status = value;
    if (key.includes("技能")) result.skills = parseSkills(value);
    if (key.includes("备注")) result.note = value;
  }
  return result;
}

export function combineProfileSummary(profile: CollaborationProfile) {
  const parts = [profile.provider, profile.computer, profile.thread].filter(Boolean);
  return parts.length > 0 ? parts.join(" / ") : "未绑定工位";
}
