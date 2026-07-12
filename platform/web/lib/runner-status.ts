type RunnerStatusRecord = Record<string, any>;

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function normalized(value: unknown) {
  return text(value, "").toLowerCase();
}

export type RunnerDispatchState =
  | "可投递"
  | "最近在线，可能延迟"
  | "等待电脑恢复"
  | "离线，需重连"
  | "状态未知，先检查接入"
  | "他人操作中";

export type RunnerStateTone = "ready" | "recent" | "stale" | "offline" | "unknown" | "occupied";

export type RunnerStateSummary = {
  state: RunnerDispatchState;
  tone: RunnerStateTone;
  canDispatch: boolean;
  canQueue: boolean;
  shortLabel: string;
  detail: string;
};

export function summarizeRunnerDispatchState(node: RunnerStatusRecord | null | undefined): RunnerStateSummary {
  if (!node) {
    return {
      state: "状态未知，先检查接入",
      tone: "unknown",
      canDispatch: false,
      canQueue: false,
      shortLabel: "状态未知",
      detail: "平台还没有拿到这台电脑的接入状态，先回电脑接入检查。",
    };
  }

  const metadata = node.metadata && typeof node.metadata === "object" ? node.metadata as RunnerStatusRecord : {};
  const watchState = normalized(node.runner_watch_state ?? node.runnerWatchState ?? metadata.runner_watch_state);
  const effective = normalized(
    node.runner_effective_status
      ?? node.runnerEffectiveStatus
      ?? node.runner_status
      ?? node.runnerStatus
      ?? node.status
      ?? metadata.runner_effective_status
      ?? metadata.runner_status,
  );
  const detail = text(node.runner_watch_detail ?? node.runnerWatchDetail ?? metadata.runner_watch_detail, "");
  const haystack = `${watchState} ${effective} ${detail}`.toLowerCase();

  if (/occupied|locked|busy_by_other|他人|占用/.test(haystack)) {
    return {
      state: "他人操作中",
      tone: "occupied",
      canDispatch: false,
      canQueue: true,
      shortLabel: "他人操作中",
      detail: detail || "这台电脑或线程正在被其他操作者占用，可以申请接手或改派。",
    };
  }

  if (watchState === "watching" || /watching|online|ready|active|connected/.test(effective)) {
    return {
      state: "可投递",
      tone: "ready",
      canDispatch: true,
      canQueue: true,
      shortLabel: "可投递",
      detail: detail || "目标电脑正在持续接单，可以派发并等待最小回执。",
    };
  }

  if (/recent|delay/.test(watchState) || /recent|delay/.test(effective)) {
    return {
      state: "最近在线，可能延迟",
      tone: "recent",
      canDispatch: false,
      canQueue: true,
      shortLabel: "可能延迟",
      detail: detail || "最近看到过这台电脑，但心跳不稳定。可以排队，但要提示用户可能延迟。",
    };
  }

  if (/stale|timeout/.test(watchState) || /stale|timeout/.test(effective)) {
    return {
      state: "等待电脑恢复",
      tone: "stale",
      canDispatch: false,
      canQueue: true,
      shortLabel: "等待电脑恢复",
      detail: detail || "持续接单心跳已过期，先让目标电脑重新运行持续接单命令。",
    };
  }

  if (/offline|lost|disconnect|failed|error|runner_offline|missing/.test(watchState) || /offline|lost|disconnect|failed|error/.test(effective)) {
    return {
      state: "离线，需重连",
      tone: "offline",
      canDispatch: false,
      canQueue: false,
      shortLabel: "需重连",
      detail: detail || "目标电脑离线或执行程序不可用，请重新接入或改派。",
    };
  }

  return {
    state: "状态未知，先检查接入",
    tone: "unknown",
    canDispatch: false,
    canQueue: false,
    shortLabel: "状态未知",
    detail: detail || "平台不能确认这台电脑是否能接单，先检查接入和线程扫描。",
  };
}

export function runnerCanDispatch(node: RunnerStatusRecord | null | undefined) {
  return summarizeRunnerDispatchState(node).canDispatch;
}

export function runnerStateLabel(node: RunnerStatusRecord | null | undefined) {
  return summarizeRunnerDispatchState(node).state;
}

export function runnerShortLabel(node: RunnerStatusRecord | null | undefined) {
  return summarizeRunnerDispatchState(node).shortLabel;
}
