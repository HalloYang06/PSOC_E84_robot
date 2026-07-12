import { normalizePlatformProviderId, platformProviderLabel } from "./platform-provider";

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

export type NpcProvisioningState = "ready" | "degraded" | "blocked";

export type NpcProvisioningInput = {
  providerId?: string | null;
  providerLabel?: string | null;
  sourceThreadId?: string | null;
  hasActiveRequirement?: boolean | null;
  autonomyReady?: boolean | null;
  supportsLocalAutonomyBridge?: boolean | null;
  consumerScriptExists?: boolean | null;
  consumerStateExists?: boolean | null;
  consumerStateStale?: boolean | null;
  heartbeatMissing?: boolean | null;
  heartbeatStatus?: string | null;
  sessionSeen?: boolean | null;
  sessionRegistered?: boolean | null;
  sessionStatus?: string | null;
  sessionLaunchBlocked?: boolean | null;
  sessionLaunchBlockReason?: string | null;
};

export type NpcProvisioningSummary = {
  state: NpcProvisioningState;
  label: string;
  detail: string;
  missing: string[];
};

function hasActiveHeartbeat(heartbeatMissing: boolean, heartbeatStatus: string) {
  if (heartbeatMissing) return false;
  if (!heartbeatStatus) return true;
  return heartbeatStatus.toUpperCase() === "ACTIVE";
}

function joinNeeds(missing: string[]) {
  return missing.filter(Boolean).join("、");
}

export function summarizeNpcProvisioning(input: NpcProvisioningInput): NpcProvisioningSummary {
  const providerId = normalizePlatformProviderId(input.providerId);
  const providerLabel = text(input.providerLabel, platformProviderLabel(providerId));
  const sourceThreadId = text(input.sourceThreadId, "");
  const hasActiveRequirement = Boolean(input.hasActiveRequirement);
  const missing: string[] = [];

  if (!sourceThreadId) {
    missing.push("绑定来源线程");
  }

  if (providerId === "codex") {
    if (!input.consumerScriptExists) missing.push("生成本地 consumer");
    if (!hasActiveHeartbeat(Boolean(input.heartbeatMissing), text(input.heartbeatStatus, ""))) {
      missing.push("接通自治 heartbeat");
    }
    if (hasActiveRequirement && !input.consumerStateExists) {
      missing.push("跑首轮 consumer");
    } else if (hasActiveRequirement && input.consumerStateStale) {
      missing.push("刷新本地 state");
    }

    const state: NpcProvisioningState = missing.some((item) =>
      ["绑定来源线程", "生成本地 consumer", "接通自治 heartbeat"].includes(item),
    )
      ? "blocked"
      : missing.length
        ? "degraded"
        : "ready";

    return {
      state,
      label: state === "ready" ? "可直接使用" : state === "degraded" ? "还差一步" : "未接通",
      detail:
        state === "ready"
          ? hasActiveRequirement
            ? `${providerLabel} NPC 的线程桥、heartbeat 和本地 state 已经齐了，可以直接接平台 requirement。`
            : `${providerLabel} NPC 的线程桥和 heartbeat 已经齐了，接到平台 requirement 就能直接开工。`
          : `${providerLabel} NPC 还不能稳定直接用，先${joinNeeds(missing)}。`,
      missing,
    };
  }

  if (providerId === "claude") {
    const sessionStatus = text(input.sessionStatus, "");
    const sessionLaunchBlocked = Boolean(input.sessionLaunchBlocked);

    if (!input.sessionSeen) {
      missing.push("打开 Claude 会话");
    } else if (!input.sessionRegistered) {
      missing.push("登记 Claude 会话");
    }

    if (sessionStatus === "stale") {
      missing.push(sessionLaunchBlocked ? "手动刷新 Claude 会话" : "刷新 Claude 会话");
    } else if (sessionStatus === "idle") {
      missing.push(sessionLaunchBlocked ? "手动唤醒 Claude 会话" : "唤醒 Claude 会话");
    }

    const state: NpcProvisioningState = missing.some((item) => ["绑定来源线程", "打开 Claude 会话"].includes(item))
      ? "blocked"
      : missing.length
        ? "degraded"
        : "ready";

    return {
      state,
      label: state === "ready" ? "可直接使用" : state === "degraded" ? "还差一步" : "未接通",
      detail:
        state === "ready"
          ? `${providerLabel} NPC 已完成会话登记并通过平台直连检查，可以继续接平台 requirement。`
          : sessionLaunchBlocked
            ? `${providerLabel} NPC 已登记到平台，但当前环境阻止平台自动唤醒 Claude；先${joinNeeds(missing)}。`
            : `${providerLabel} NPC 还没稳定接通，先${joinNeeds(missing)}。`,
      missing,
    };
  }

  if (providerId) {
    if (providerId !== "codex" && providerId !== "claude") {
      missing.push(`补 ${providerLabel} adapter`);
    }
  } else {
    missing.push("选择提供方");
  }

  const state: NpcProvisioningState = missing.some((item) => ["绑定来源线程", "选择提供方"].includes(item))
    ? "blocked"
    : missing.length
      ? "degraded"
      : "ready";

  return {
    state,
    label: state === "ready" ? "可直接使用" : state === "degraded" ? "待接 adapter" : "未接通",
    detail:
      state === "ready"
        ? `${providerLabel || "当前"} NPC 已经具备统一平台协议，可以继续派单。`
        : `${providerLabel || "当前"} NPC 还没到直接可用状态，先${joinNeeds(missing)}。`,
    missing,
  };
}
