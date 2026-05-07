type AnyRecord = Record<string, unknown>;

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

export function normalizePlatformProviderId(value: unknown) {
  const raw = text(value, "").toLowerCase();
  if (!raw) return "";
  if (raw === "openai-codex" || raw === "openai_codex") return "codex";
  if (raw.includes("codex")) return "codex";
  if (raw.includes("claude") || raw.includes("anthropic")) return "claude";
  if (raw.includes("qwen")) return "qwen";
  if (raw.includes("glm")) return "glm";
  if (raw.includes("openclaw")) return "openclaw";
  return raw;
}

export function derivePlatformProviderIdFromThreadId(value: unknown) {
  const raw = text(value, "").toLowerCase();
  if (!raw) return "";
  if (raw.startsWith("codex-session-")) return "codex";
  if (raw.startsWith("claude-session-")) return "claude";
  if (raw.startsWith("qwen-session-")) return "qwen";
  if (raw.startsWith("glm-session-")) return "glm";
  if (raw.startsWith("openclaw-session-")) return "openclaw";
  return "";
}

export function platformProviderLabel(value: unknown) {
  const providerId = normalizePlatformProviderId(value);
  if (providerId === "codex") return "Codex";
  if (providerId === "claude") return "Claude";
  if (providerId === "qwen") return "Qwen";
  if (providerId === "glm") return "GLM";
  if (providerId === "openclaw") return "OpenClaw";
  return providerId ? providerId.toUpperCase() : "未知提供方";
}

export function platformProviderEndpoint(value: unknown) {
  const providerId = normalizePlatformProviderId(value);
  if (providerId === "codex") return "openai";
  if (providerId === "claude") return "anthropic";
  if (providerId === "qwen") return "dashscope";
  if (providerId === "glm") return "bigmodel";
  if (providerId === "openclaw") return "openclaw";
  return providerId || null;
}

export function platformProviderIdFromThread(thread: AnyRecord) {
  const metadata = thread.metadata && typeof thread.metadata === "object" ? (thread.metadata as AnyRecord) : {};
  const direct = normalizePlatformProviderId(
    thread.ai_provider_id ?? thread.ai_provider ?? metadata.provider ?? metadata.provider_id,
  );
  if (direct) return direct;
  return derivePlatformProviderIdFromThreadId(thread.id ?? thread.workstation_id ?? metadata.source_workstation_id);
}

export function platformProviderLabelFromThread(thread: AnyRecord) {
  const metadata = thread.metadata && typeof thread.metadata === "object" ? (thread.metadata as AnyRecord) : {};
  const providerId = platformProviderIdFromThread(thread);
  if (providerId) return platformProviderLabel(providerId);
  const direct = text(thread.ai_provider ?? metadata.provider_label ?? metadata.provider, "");
  if (direct) return platformProviderLabel(direct);
  return platformProviderLabel("");
}

export function platformProviderIdFromSeat(seat: AnyRecord) {
  const metadata = seat.metadata && typeof seat.metadata === "object" ? (seat.metadata as AnyRecord) : {};
  const direct = normalizePlatformProviderId(
    seat.ai_provider_id ??
      seat.ai_provider ??
      metadata.provider_id ??
      metadata.provider ??
      metadata.provider_label,
  );
  if (direct) return direct;
  return derivePlatformProviderIdFromThreadId(seat.source_workstation_id ?? metadata.source_workstation_id);
}

export function platformProviderLabelFromSeat(seat: AnyRecord) {
  const metadata = seat.metadata && typeof seat.metadata === "object" ? (seat.metadata as AnyRecord) : {};
  const providerId = platformProviderIdFromSeat(seat);
  if (providerId) return platformProviderLabel(providerId);
  return platformProviderLabel(
    seat.ai_provider ?? seat.ai_provider_id ?? metadata.provider_label ?? metadata.provider_id ?? metadata.provider,
  );
}

export function isNpcSeatType(value: unknown) {
  const normalized = text(value, "").toLowerCase();
  return normalized === "codex" || normalized === "npc";
}

export function isNpcSeatRecord(value: AnyRecord) {
  const metadata = value.metadata && typeof value.metadata === "object" ? (value.metadata as AnyRecord) : {};
  const extraData = value.extra_data && typeof value.extra_data === "object" ? (value.extra_data as AnyRecord) : {};
  return isNpcSeatType(metadata.seat_type ?? extraData.seat_type ?? value.seat_type);
}

export function seatTypeForProvider(providerId: unknown) {
  const normalized = normalizePlatformProviderId(providerId);
  return normalized === "codex" ? "codex" : "npc";
}

export function supportsPlatformNpcCreation(providerId: unknown) {
  const normalized = normalizePlatformProviderId(providerId);
  return ["codex", "claude", "qwen", "glm", "openclaw"].includes(normalized);
}

export function supportsLocalCodexAutonomyBridge(providerId: unknown) {
  return normalizePlatformProviderId(providerId) === "codex";
}
