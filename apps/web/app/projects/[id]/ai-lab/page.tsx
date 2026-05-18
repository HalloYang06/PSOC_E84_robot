import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectBossPlansState,
  getProjectComputerNodesState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getTaskProfessionalViewState,
} from "../../../../lib/server-data";
import { runnerCanDispatch } from "../../../../lib/runner-status";
import { ProfessionalWorkbenchShell } from "../_components/professional-evidence-shell";
import styles from "./ai-lab.module.css";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type AnyRecord = Record<string, any>;

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function computerDispatchReady(node: AnyRecord | undefined) {
  return runnerCanDispatch(node);
}

function safeProjectReturnPath(projectId: string, value: unknown) {
  const raw = text(value, "");
  if (!raw.startsWith(`/projects/${projectId}/`)) return "";
  if (/^\/\//.test(raw) || raw.includes("\\") || raw.includes("://")) return "";
  return raw;
}

function labelProjectReturnPath(value: string) {
  if (value.includes("/workbench")) return "返回 NPC 工作台";
  if (value.includes("/datasets")) return "返回数据工场";
  if (value.includes("/robotics")) return "返回机器人现场";
  if (value.includes("/observability")) return "返回观测台";
  if (value.includes("/ai-lab")) return "返回 AI 实验室";
  return "返回来源";
}

function itemTitle(item: AnyRecord | null | undefined) {
  return text(item?.title ?? item?.name ?? item?.display_name ?? item?.type ?? item?.id, "未命名任务");
}

function numberText(value: unknown, fallback = "等待") {
  return Number.isFinite(Number(value)) ? String(Number(value)) : fallback;
}

function humanStatus(value: unknown, fallback = "等待") {
  const raw = text(value, fallback);
  const normalized = raw.toLowerCase();
  if (normalized === "waiting") return "等待";
  if (/can_continue|passed|ready|completed|complete/.test(normalized)) return "可继续";
  if (/active|running|in_progress/.test(normalized)) return "进行中";
  if (/review_required/.test(normalized)) return "需人工确认";
  if (/pending_closeout/.test(normalized)) return "待收口";
  if (/blocked/.test(normalized)) return "阻塞";
  if (/failed|error/.test(normalized)) return "异常";
  return raw;
}

function isRawIdentifier(value: unknown) {
  const raw = text(value, "");
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)
    || /^[0-9a-f]{12,}$/i.test(raw);
}

function publicFocusSeat(value: unknown, fallback = "当前工位") {
  const raw = text(value, "");
  if (!raw || isRawIdentifier(raw)) return fallback;
  return raw;
}

function exceptionSummary(view: AnyRecord | null): AnyRecord {
  const summary = view?.summary?.exception_summary;
  return summary && typeof summary === "object" ? (summary as AnyRecord) : {};
}

function buildEngineerNextStep(view: AnyRecord | null, projectId: string, selfPath: string, observabilityHref: string) {
  const summary = view?.summary ?? {};
  const releaseStatus = text(summary?.release_gate_status, "waiting");
  const manifestPath = text(summary?.dataset_manifest_artifact_path, "");
  const replayReady = Boolean(summary?.replay_ready);
  if (/review_required|pending_closeout|blocked|failed/.test(releaseStatus)) {
    return {
      label: "先处理阻塞",
      detail: "训练发布门还不能通过，先看观测台里的异常、待收口或审批记录。",
      href: observabilityHref,
      state: "blocked",
    };
  }
  if (!manifestPath) {
    return {
      label: "补齐训练数据入口",
      detail: "先让样本清单回到任务记录，再谈指标对比和下一次实验。",
      href: `/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`,
      state: "watch",
    };
  }
  if (replayReady) {
    return {
      label: "复盘仿真 / 回放",
      detail: "回放已准备好，先复盘异常线索，再由工程师决定下一次实验。",
      href: "#replay",
      state: "ready",
    };
  }
  return {
    label: releaseStatus === "can_continue" ? "回工作台确认下一步" : "查看指标与回执",
    detail: releaseStatus === "can_continue" ? "AI 给出继续建议，但训练放行和发布仍由工程师确认。" : "先核对实验运行、指标、训练回执和样本风险。",
    href: releaseStatus === "can_continue"
      ? `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`
      : observabilityHref,
    state: releaseStatus === "can_continue" ? "ready" : "waiting",
  };
}

function buildObservabilityHref(projectId: string, selfPath: string, taskId: string, searchParams?: AnyRecord) {
  const params = new URLSearchParams({ return_to: selfPath, from: "ai-lab" });
  if (taskId) params.set("task_id", taskId);
  const messageId = text(searchParams?.message_id, "");
  const dispatchId = text(searchParams?.dispatch_id, "");
  const sourceSeat = text(searchParams?.source_seat, "");
  const sourceTitle = text(searchParams?.source_title, "");
  if (messageId) params.set("message_id", messageId);
  if (dispatchId) params.set("dispatch_id", dispatchId);
  if (sourceSeat) params.set("source_seat", sourceSeat);
  if (sourceTitle) params.set("source_title", sourceTitle);
  if (text(searchParams?.goal_chain, "")) params.set("goal_chain", text(searchParams?.goal_chain, ""));
  return `/projects/${projectId}/observability?${params.toString()}`;
}

function buildRunBoard(view: AnyRecord | null, bossPlans: AnyRecord[]) {
  const summary = view?.summary ?? {};
  const runStatus = text(summary?.experiment_run_status, "waiting");
  const receiptStatus = text(summary?.training_receipt_status, "waiting");
  const releaseStatus = text(summary?.release_gate_status, "can_continue");
  const manifestPath = text(summary?.dataset_manifest_artifact_path, "");
  return [
    {
      label: "实验运行",
      status: /ready|completed/.test(runStatus) ? "ready" : /active|running|in_progress/.test(runStatus) ? "active" : /blocked|failed/.test(runStatus) ? "watch" : "waiting",
      detail:
        runStatus === "waiting"
          ? "等待桌面线程或执行电脑回流实验状态。"
          : `当前实验运行状态：${humanStatus(runStatus)}。`,
      actionLabel:
        runStatus === "waiting"
          ? "等待实验状态回流"
          : /active|running|in_progress/.test(runStatus)
            ? "继续实验派单"
            : /ready|completed/.test(runStatus)
              ? "查看实验结果"
              : "回工作台处理运行阻塞",
    },
    {
      label: "评估摘要",
      status: /completed|ready/.test(receiptStatus) ? "ready" : /blocked|failed/.test(receiptStatus) ? "watch" : "waiting",
      detail:
        receiptStatus === "waiting"
          ? "等待训练回执或评估摘要回流。"
          : `当前训练回执状态：${humanStatus(receiptStatus)}。`,
      actionLabel:
        receiptStatus === "waiting"
          ? "等待评估摘要"
          : /completed|ready/.test(receiptStatus)
            ? "查看评估回执"
            : "处理评估阻塞",
    },
    {
      label: "训练数据入口",
      status: manifestPath ? "ready" : "watch",
      detail: manifestPath ? `已登记样本清单：${manifestPath}` : "等待样本清单路径回流到任务记录。",
      actionLabel: manifestPath ? "打开数据入口" : "等待样本清单回流",
    },
    {
      label: "放行建议",
      status: /can_continue|ready|passed/.test(releaseStatus) ? "ready" : /review_required|pending_closeout/.test(releaseStatus) ? "watch" : "waiting",
      detail:
        releaseStatus === "can_continue"
          ? "系统给出可继续建议，仍需工程师确认下一步。"
          : releaseStatus === "waiting"
            ? "等待放行结论回流。"
            : `当前放行状态：${releaseStatus}。`,
      actionLabel:
        /can_continue|ready|passed/.test(releaseStatus)
          ? bossPlans.length > 0
            ? "确认下一步动作"
            : "回工作台确认"
          : /review_required|pending_closeout/.test(releaseStatus)
            ? "处理待收口 / 审批"
            : "等待放行结论",
    },
  ];
}

function buildEvalModes(view: AnyRecord | null) {
  const exception = exceptionSummary(view);
  const qaStatus = text(view?.summary?.qa_status, "waiting");
  const metricsSummary = (view?.summary?.metrics_summary ?? {}) as AnyRecord;
  const metricEntries = Object.entries(metricsSummary).slice(0, 3);
  const lowConfidenceCount = view?.summary?.low_confidence_count;
  return [
    {
      label: "运行对比",
      source: "参数 / 指标 / 结论",
      detail:
        Number(view?.summary?.message_count ?? 0) > 0
          ? "对比当前任务里的最小回执、指标快照和继续建议。"
          : "等待回执和指标一起回流。",
      state: Number(view?.summary?.message_count ?? 0) > 0 ? "ready" : "waiting",
      actionLabel: "对比回执与指标",
    },
    {
      label: "指标快照",
      source: metricEntries.length ? metricEntries.map(([key, value]) => `${key}: ${String(value)}`).join(" · ") : "等待指标摘要",
      detail: metricEntries.length ? "已收到统一指标摘要，供工程师判断是否继续。" : "等待指标摘要回流，不再从长日志里猜指标。",
      state: metricEntries.length ? "ready" : "watch",
      actionLabel: metricEntries.length ? "查看评估指标" : "等待指标回流",
    },
    {
      label: "样本质量",
      source: `质检 ${humanStatus(qaStatus)} · 低置信 ${numberText(lowConfidenceCount, "等待")}`,
      detail:
        qaStatus === "waiting"
          ? "等待样本质检状态和低置信样本计数回流。"
          : "样本质量已进入同一任务记录，辅助工程师决定补样本、复核或继续训练。",
      state: exception.actionable || /blocked|failed/.test(qaStatus) ? "blocked" : qaStatus === "waiting" ? "watch" : "ready",
      actionLabel: qaStatus === "waiting" ? "等待质检回流" : "按质检结果处理样本",
    },
  ];
}

function buildModelReviewRows(view: AnyRecord | null) {
  const summary = view?.summary ?? {};
  const metricsSummary = (summary?.metrics_summary ?? {}) as AnyRecord;
  const metricEntries = Object.entries(metricsSummary).slice(0, 4);
  const receiptStatus = text(summary?.training_receipt_status, "waiting");
  const releaseStatus = text(summary?.release_gate_status, "waiting");
  const qaStatus = text(summary?.qa_status, "waiting");
  const replayReady = Boolean(summary?.replay_ready);
  return [
    {
      label: "指标对比",
      value: metricEntries.length ? metricEntries.map(([key, value]) => `${key}=${String(value)}`).join(" · ") : "等待指标摘要",
      detail: metricEntries.length ? "AI 汇总指标变化，工程师判断是否需要下一次实验。" : "指标未回流前不生成模型优劣结论。",
    },
    {
      label: "样本风险",
      value: `质检=${humanStatus(qaStatus)} · 低置信=${numberText(summary?.low_confidence_count)}`,
      detail: "低置信样本只作为复核线索，是否补样本由工程师确认。",
    },
    {
      label: "训练回执",
      value: humanStatus(receiptStatus),
      detail: receiptStatus === "waiting" ? "等待训练回执回流。" : "回执用于核对训练是否完成、是否有异常，不替人放行。",
    },
    {
      label: "下一次实验建议",
      value: replayReady ? "可结合回放复盘" : humanStatus(releaseStatus),
      detail: "AI 可以建议复盘路径或异常点，模型选择、训练放行、发布仍由人决定。",
    },
  ];
}

function buildTrainingLanes(view: AnyRecord | null) {
  const summary = view?.summary ?? {};
  const manifestPath = text(summary?.dataset_manifest_artifact_path, "");
  const manifestVersion = text(summary?.manifest_version, "");
  const sampleCount = summary?.sample_count;
  const lowConfidenceCount = summary?.low_confidence_count;
  const qaStatus = text(summary?.qa_status, "waiting");
  const exportStatus = text(summary?.export_status, "waiting");
  const receiptStatus = text(summary?.training_receipt_status, "waiting");
  const releaseStatus = text(summary?.release_gate_status, "waiting");
  return [
    {
      label: "训练数据入口",
      value: manifestPath ? "已有样本清单" : "等待入口",
      detail: manifestPath
        ? `${manifestVersion || "样本清单"} · 样本 ${numberText(sampleCount, "待回流")} · 低置信 ${numberText(lowConfidenceCount, "待回流")}`
        : "等待样本清单路径回流到任务记录。",
      actionLabel: manifestPath ? "查看样本清单入口" : "等待样本清单回流",
    },
    {
      label: "数据质检 / 导出",
      value: qaStatus === "waiting" && exportStatus === "waiting" ? "等待状态" : `${humanStatus(qaStatus)} / ${humanStatus(exportStatus)}`,
      detail:
        qaStatus === "waiting" && exportStatus === "waiting"
          ? "等待质检状态与导出状态回流。"
          : "数据工场质检与导出状态已进入实验闭环。",
      actionLabel: /needs_review|blocked|failed/.test(`${qaStatus} ${exportStatus}`) ? "回数据工场处理" : "按状态继续",
    },
    {
      label: "训练回执",
      value: receiptStatus === "waiting" ? "等待回执" : humanStatus(receiptStatus),
      detail: receiptStatus === "waiting" ? "只收训练是否完成、指标是否过线、是否需要人工决策。" : `训练回执已统一为 ${humanStatus(receiptStatus)}。`,
      actionLabel: receiptStatus === "waiting" ? "等待训练回流" : "看训练回执",
    },
    {
      label: "放行建议",
      value: releaseStatus === "waiting" ? "等待放行" : humanStatus(releaseStatus),
      detail:
        releaseStatus === "can_continue"
          ? "训练结果给出可继续建议，仍由工程师确认。"
          : releaseStatus === "waiting"
            ? "等待训练发布门状态回流。"
            : "训练结果要么回工作台确认，要么进观测台处理异常，不在这里悬空。",
      actionLabel:
        releaseStatus === "can_continue"
          ? "回工作台确认"
          : releaseStatus === "waiting"
            ? "等待放行结论"
            : "处理待收口",
    },
  ];
}

function buildModelCandidateRows(view: AnyRecord | null) {
  const summary = view?.summary ?? {};
  const metricsSummary = (summary?.metrics_summary ?? {}) as AnyRecord;
  const metricEntries = Object.entries(metricsSummary).slice(0, 3);
  const metricText = metricEntries.length
    ? metricEntries.map(([key, value]) => `${key}=${String(value)}`).join(" · ")
    : "等待指标回流";
  const qaStatus = text(summary?.qa_status, "waiting");
  const receiptStatus = text(summary?.training_receipt_status, "waiting");
  const releaseStatus = text(summary?.release_gate_status, "waiting");
  const sampleCount = numberText(summary?.sample_count, "待回流");
  const lowConfidenceCount = numberText(summary?.low_confidence_count, "待回流");
  return [
    {
      label: "当前候选",
      value: metricText,
      risk: `质检=${humanStatus(qaStatus)} · 低置信=${lowConfidenceCount}`,
      decision: releaseStatus === "can_continue" ? "可提交人工确认" : "等待发布门结论",
      state: releaseStatus === "can_continue" ? "ready" : /blocked|failed|review_required/.test(releaseStatus) ? "blocked" : "watch",
    },
    {
      label: "保守基线",
      value: `样本=${sampleCount} · 回执=${humanStatus(receiptStatus)}`,
      risk: "用于回退比较，不自动替换当前模型。",
      decision: "保留为人工对照",
      state: "watch",
    },
    {
      label: "下一轮实验",
      value: metricEntries.length ? "基于指标差异生成假设" : "等待指标后生成假设",
      risk: "AI 只建议实验方向，不决定模型选择。",
      decision: metricEntries.length ? "可整理实验假设" : "等待指标回流",
      state: metricEntries.length ? "ready" : "waiting",
    },
  ];
}

function buildReleaseChecklist(view: AnyRecord | null) {
  const summary = view?.summary ?? {};
  const metricCount = Object.keys((summary?.metrics_summary as AnyRecord | undefined) ?? {}).length;
  const manifestPath = text(summary?.dataset_manifest_artifact_path, "");
  const qaStatus = text(summary?.qa_status, "waiting");
  const receiptStatus = text(summary?.training_receipt_status, "waiting");
  const releaseStatus = text(summary?.release_gate_status, "waiting");
  return [
    {
      label: "样本清单",
      state: manifestPath ? "ready" : "blocked",
      detail: manifestPath ? "已挂回任务记录" : "缺少样本清单，不能评估发布。",
    },
    {
      label: "指标摘要",
      state: metricCount > 0 ? "ready" : "watch",
      detail: metricCount > 0 ? `${metricCount} 项指标可核对` : "等待评估指标回流。",
    },
    {
      label: "数据质检",
      state: /completed|ready|passed|can_continue/.test(qaStatus) ? "ready" : qaStatus === "waiting" ? "watch" : "blocked",
      detail: `质检状态=${humanStatus(qaStatus)}`,
    },
    {
      label: "训练回执",
      state: /completed|ready|passed|can_continue/.test(receiptStatus) ? "ready" : receiptStatus === "waiting" ? "watch" : "blocked",
      detail: `训练回执=${humanStatus(receiptStatus)}`,
    },
    {
      label: "人工放行",
      state: releaseStatus === "can_continue" ? "review" : "blocked",
      detail: releaseStatus === "can_continue" ? "可交给工程师确认" : `训练发布门=${humanStatus(releaseStatus)}`,
    },
  ];
}

function buildBoundaryCards(view: AnyRecord | null) {
  const summary = view?.summary ?? {};
  const releaseStatus = text(summary?.release_gate_status, "waiting");
  const receiptStatus = text(summary?.training_receipt_status, "waiting");
  const qaStatus = text(summary?.qa_status, "waiting");
  const exportStatus = text(summary?.export_status, "waiting");
  const actionable = Boolean(exceptionSummary(view).actionable);
  const pendingCloseout = Number(summary?.pending_closeout_count ?? 0);
  return [
    {
      label: "AI 辅助",
      state: actionable ? "watch" : "ready",
      value: actionable ? "先观察" : "给建议",
      detail:
        summary?.experiment_run_status === "waiting"
          ? "等待实验字段回流后，由 AI 汇总实验运行、指标和异常。"
          : "AI 只做只读诊断、对比、预演和摘要建议；模型选择、放行、发布由人确认。",
    },
    {
      label: "审批边界",
      state: /review_required|pending_closeout|blocked/.test(releaseStatus) || pendingCloseout > 0 ? "blocked" : "ready",
      value:
        /review_required/.test(releaseStatus)
          ? "需审批"
          : pendingCloseout > 0 || /pending_closeout/.test(releaseStatus)
            ? "待收口"
            : "可继续",
      detail:
        releaseStatus === "waiting"
          ? "等待训练发布门状态回流。"
          : `训练发布门=${humanStatus(releaseStatus)} · 训练回执=${humanStatus(receiptStatus)} · 质检=${humanStatus(qaStatus)} · 导出=${humanStatus(exportStatus)}`,
    },
    {
      label: "强审动作",
      state: "review",
      value: "必须人审",
      detail: "部署、重启、硬件写入、运动动作继续留在平台审批链，不在实验室直接执行。",
    },
  ];
}

function buildClosureActions(view: AnyRecord | null, projectId: string, selfPath: string) {
  const summary = view?.summary ?? {};
  const runStatus = text(summary?.experiment_run_status, "waiting");
  const receiptStatus = text(summary?.training_receipt_status, "waiting");
  const releaseStatus = text(summary?.release_gate_status, "waiting");
  const manifestPath = text(summary?.dataset_manifest_artifact_path, "");
  const manifestVersion = text(summary?.manifest_version, "");
  const qaStatus = text(summary?.qa_status, "waiting");
  const exportStatus = text(summary?.export_status, "waiting");
  const replayReady = Boolean(summary?.replay_ready);
  const metricCount = Object.keys((summary?.metrics_summary as AnyRecord | undefined) ?? {}).length;
  const taskId = text(view?.task?.id, "");
  return [
    {
      label: "实验运行",
      detail:
        runStatus === "waiting"
          ? "等待实验状态回流后再决定继续跑还是转处理。"
          : /active|running|in_progress/.test(runStatus)
            ? "实验还在跑，回工作台继续跟进。"
            : /ready|completed/.test(runStatus)
              ? "实验结果已回流，可转看指标和放行建议。"
              : "实验被阻塞，先去观测台定位。",
      href:
        /blocked|failed/.test(runStatus)
          ? `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=ai-lab${taskId ? `&task_id=${encodeURIComponent(taskId)}` : ""}`
          : `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`,
    },
    {
      label: "评估指标",
      detail: metricCount > 0 ? "指标已回流，供工程师判断这次实验是否值得继续。" : "指标还没回流，先等回执或报告更新。",
      href:
        metricCount > 0
          ? `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=ai-lab${taskId ? `&task_id=${encodeURIComponent(taskId)}` : ""}`
          : `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`,
    },
    {
      label: "训练数据",
      detail: manifestPath
        ? `${manifestVersion || "样本清单"} 已登记，质检=${humanStatus(qaStatus)}，导出=${humanStatus(exportStatus)}。`
        : "训练数据入口还没回流，先等样本清单进入任务记录。",
      href: `/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`,
    },
    {
      label: "仿真 / 回放",
      detail: replayReady ? "回放准备状态已回流，可沿回放复盘异常和下一次实验假设。" : "回放还没准备好，先等回放记录回流。",
      href: `#replay`,
    },
    {
      label: "训练回执",
      detail:
        receiptStatus === "waiting"
          ? "等待最小回执或最终结果回流。"
          : /completed|ready/.test(receiptStatus)
            ? "训练回执已到，可供工程师做放行确认。"
            : "训练回执提示阻塞，先去观测台处理。",
      href:
        /blocked|failed/.test(receiptStatus)
          ? `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=ai-lab${taskId ? `&task_id=${encodeURIComponent(taskId)}` : ""}`
          : `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`,
    },
    {
      label: "训练发布门",
      detail:
        releaseStatus === "can_continue"
          ? "具备继续建议，回工作台由工程师确认下一步。"
          : /review_required|pending_closeout/.test(releaseStatus)
            ? "还不能放行，先处理审批或待收口。"
            : "等待训练发布门结论回流。",
      href:
        releaseStatus === "can_continue"
          ? `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`
          : `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=ai-lab${taskId ? `&task_id=${encodeURIComponent(taskId)}` : ""}`,
    },
  ];
}

export default async function ProjectAiLabPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: {
    return_to?: string;
    from?: string;
    task_id?: string;
    message_id?: string;
    dispatch_id?: string;
    source_seat?: string;
    source_label?: string;
    source_title?: string;
    goal_chain?: string;
  };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/ai-lab`)}`);
  }

  const projectState = await getProjectState(projectId);
  const project = projectState.data;
  if (!project) {
    return (
      <main className={styles.emptyPage}>
        <p>项目不存在或无权限。</p>
        <Link href="/projects">返回项目列表</Link>
      </main>
    );
  }

  const [taskProfessionalState, computersState, threadWorkstationsState, bossPlansState] = await Promise.all([
    searchParams?.task_id
      ? getTaskProfessionalViewState(searchParams.task_id)
      : Promise.resolve({ data: null, status: 200, error: null }),
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectBossPlansState(projectId, 4),
  ]);

  const taskView = taskProfessionalState.data as AnyRecord | null;
  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(threadWorkstationsState.data);
  const bossPlans = asArray<AnyRecord>(bossPlansState.data);
  const taskException = exceptionSummary(taskView);
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/ai-lab`;
  const focusTitle = text(searchParams?.source_title, itemTitle(taskView?.task));
  const focusSeat = publicFocusSeat(searchParams?.source_label ?? searchParams?.source_seat);
  const boundSeats = seats.filter((seat) =>
    text(seat.sourceWorkstationId ?? seat.source_workstation_id ?? seat.bound_thread_id ?? seat.target_thread_id, ""),
  ).length;
  const onlineComputers = computers.filter(computerDispatchReady).length;
  const runBoard = buildRunBoard(taskView, bossPlans);
  const evalModes = buildEvalModes(taskView);
  const modelReviewRows = buildModelReviewRows(taskView);
  const trainingLanes = buildTrainingLanes(taskView);
  const modelCandidateRows = buildModelCandidateRows(taskView);
  const releaseChecklist = buildReleaseChecklist(taskView);
  const boundaryCards = buildBoundaryCards(taskView);
  const closureActions = buildClosureActions(taskView, projectId, selfPath);
  const manifestPath = text(taskView?.summary?.dataset_manifest_artifact_path, "");
  const releaseStatus = text(taskView?.summary?.release_gate_status, "waiting");
  const runStatus = text(taskView?.summary?.experiment_run_status, "waiting");
  const qaStatus = text(taskView?.summary?.qa_status, "waiting");
  const metricCount = Object.keys((taskView?.summary?.metrics_summary as AnyRecord | undefined) ?? {}).length;
  const taskId = text(taskView?.task?.id, searchParams?.task_id ?? "");
  const observabilityHref = buildObservabilityHref(projectId, selfPath, taskId, searchParams);
  const engineerNextStep = buildEngineerNextStep(taskView, projectId, selfPath, observabilityHref);
  const nextStepLine =
    releaseStatus === "can_continue"
      ? "可回 NPC 工作台由工程师确认下一步。"
      : /review_required|pending_closeout|blocked/.test(releaseStatus)
        ? "先处理审批、待收口或阻塞。"
        : manifestPath
          ? "先看训练数据和指标是否足够。"
          : "先补齐训练数据入口。";

  const topLinks = [
    { label: "NPC 工作台", href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab` },
    { label: "数据工场", href: `/projects/${projectId}/datasets?return_to=${encodeURIComponent(selfPath)}&from=ai-lab` },
    { label: "AI 实验室", href: selfPath, active: true },
    { label: "机器人现场", href: `/projects/${projectId}/robotics?return_to=${encodeURIComponent(selfPath)}&from=ai-lab` },
    { label: "观测台", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=ai-lab` },
    ...(returnTo ? [{ label: labelProjectReturnPath(returnTo), href: returnTo }] : []),
  ];
  const sectionLinks = [
    { label: "Run Board", href: "#run-board", detail: "运行 / 排队 / 回执", active: true },
    { label: "指标对比", href: "#model-review", detail: "模型 / 数据 / 阈值" },
    { label: "评估摘要", href: "#model-review", detail: "结论 / 异常 / 样本风险" },
    { label: "回放仿真", href: "#replay", detail: "rosbag / episode / sim" },
    { label: "数据入口", href: "#data-drawer", detail: "manifest / dataset" },
    { label: "训练发布门", href: "#release-drawer", detail: "人工确认 / 放行锁" },
  ];
  const taskActions = [
    { label: "回 NPC 工作台", href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`, primary: true },
    { label: "看观测台", href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=ai-lab` },
    {
      label: "当前记录",
      href: taskView
        ? `/projects/${projectId}/observability?from=ai-lab&task_id=${encodeURIComponent(text(taskView.task?.id, ""))}`
        : `/projects/${projectId}/observability?from=ai-lab`,
    },
  ];
  const capabilityCards = [
    { label: "任务", detail: "实验对象仍是同一条任务链路" },
    { label: "回执", detail: "只看最小回执、最终状态和下一步动作" },
    { label: "产出", detail: "回放、报告、日志都从记录索引进入" },
    { label: "审计", detail: "审批边界和收口动作继续在审计链上" },
  ];
  const signalCards = [
    {
      label: "Boss 计划",
      value: String(bossPlans.length),
      detail: bossPlans.length > 0 ? "当前已有拆分任务可继续" : "当前没有新的 Boss 拆分",
      href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`,
      actionLabel: "回工作台继续",
    },
    {
      label: "执行电脑在线",
      value: `${onlineComputers}/${computers.length}`,
      detail: "实验室只消费执行电脑上报状态，不替代外部工具。",
      href: `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`,
      actionLabel: "看执行状态",
    },
    {
      label: "桌面线程",
      value: `${boundSeats}/${seats.length}`,
      detail: "主页面按线程名字选择；实验室只显示是否可继续协作。",
      href: `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`,
      actionLabel: "回工作台",
    },
  ];

  return (
    <ProfessionalWorkbenchShell
      projectId={projectId}
      pageKey="ai-lab"
      pageTitle="AI 实验室"
      pageSummary="把实验、仿真、指标、审批边界和回放记录收进同一条任务记录，辅助工程师判断下一步。"
      projectName={text(project.name, "项目")}
      topLinks={topLinks}
      sectionLinks={sectionLinks}
      taskView={taskView}
      focusTitle={focusTitle}
      focusSeat={focusSeat}
      taskActions={taskActions}
      capabilityCards={capabilityCards}
      signalCards={signalCards}
    >
      <section className={styles.labDesk} aria-label="AI 实验室主工作台">
        <section className={styles.labHero}>
          <div>
            <span className={styles.sectionTag}>当前工具</span>
            <h2>Run Board / 评估台</h2>
            <p>{nextStepLine} AI 实验室只整理实验运行、指标、训练数据、回放和训练发布门，不替人选择模型、训练放行或发布。</p>
          </div>
          <div className={styles.heroActions}>
            <Link href={engineerNextStep.href}>工程师下一步</Link>
            <Link href={observabilityHref}>看记录</Link>
            <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=ai-lab`}>回 NPC 工作台</Link>
          </div>
        </section>

        <section className={styles.runBoardPanel} id="run-board">
          <div className={styles.runHeader}>
            <div>
              <span className={styles.sectionTag}>Run Board</span>
              <strong>{taskView ? itemTitle(taskView.task) : "等待任务焦点进入实验室"}</strong>
            </div>
            <div className={styles.statusPills}>
              <span>实验 {humanStatus(runStatus)}</span>
              <span>指标 {metricCount ? `${metricCount} 项` : "等待"}</span>
              <span>发布门 {humanStatus(releaseStatus)}</span>
            </div>
          </div>

          <div className={styles.runBoard}>
            {runBoard.map((item) => (
              <article key={item.label} data-state={item.status}>
                <span>{item.label}</span>
                <strong>{item.status === "active" ? "进行中" : item.status === "ready" ? "已具备" : item.status === "watch" ? "待推进" : "等待"}</strong>
                <p>{item.detail}</p>
                <small>{item.actionLabel}</small>
              </article>
            ))}
          </div>

          <div className={styles.evalGrid}>
            {evalModes.map((item) => (
              <article key={item.label} data-state={item.state}>
                <small>{item.source}</small>
                <strong>{item.label}</strong>
                <span>{item.actionLabel}</span>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.labSplit}>
          <section className={styles.compactPanel} id="model-review">
            <div className={styles.compactHead}>
              <span className={styles.sectionTag}>模型评估</span>
              <strong>指标、风险、回执、下一轮假设</strong>
            </div>
            <div className={styles.modelReviewGrid}>
              {modelReviewRows.map((row) => (
                <article key={row.label}>
                  <span>{row.label}</span>
                  <strong>{row.value}</strong>
                  <p>{row.detail}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.compactPanel} id="release-drawer">
            <div className={styles.compactHead}>
              <span className={styles.sectionTag}>训练发布门</span>
              <strong>{humanStatus(releaseStatus)}</strong>
            </div>
            <div className={styles.releaseChecklist}>
              {releaseChecklist.map((item) => (
                <article key={item.label} data-state={item.state}>
                  <span>{item.label}</span>
                  <strong>{item.detail}</strong>
                </article>
              ))}
            </div>
          </section>
        </section>

        <details className={styles.labDetails} id="replay">
          <summary>
            <span>回放、数据契约、候选模型和边界记录</span>
            <strong>展开高级信息</strong>
          </summary>
          <div className={styles.detailsGrid}>
            {[...modelCandidateRows.map((row) => ({ title: row.label, body: row.value, detail: row.decision })),
              ...trainingLanes.map((lane) => ({ title: lane.label, body: lane.value, detail: lane.actionLabel })),
              ...boundaryCards.map((item) => ({ title: item.label, body: item.value, detail: item.detail })),
              ...closureActions.slice(0, 3).map((item) => ({ title: item.label, body: "下一步动作", detail: item.detail }))].slice(0, 12).map((item) => (
              <article key={`${item.title}-${item.body}`}>
                <span>{item.title}</span>
                <strong>{item.body}</strong>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
        </details>
      </section>
    </ProfessionalWorkbenchShell>
  );
}
