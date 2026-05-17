import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectKnowledgeDocumentsState,
  getProjectMembersState,
  getProjectSkillsState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getProjectWorkstationsState,
  getSeatSkillAssignmentsState,
  getTaskProfessionalViewState,
} from "../../../../lib/server-data";
import { runnerCanDispatch } from "../../../../lib/runner-status";
import { ProfessionalEvidenceShell } from "../_components/professional-evidence-shell";
import styles from "./datasets.module.css";

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
  if (value.includes("/company")) return "返回公司层";
  if (value.includes("/ai-lab")) return "返回 AI 实验室";
  if (value.includes("/robotics")) return "返回机器人现场";
  if (value.includes("/observability")) return "返回观测台";
  if (value.includes("/skill-forge")) return "返回能力工坊";
  if (value.includes("/datasets")) return "返回数据工场";
  return "返回来源";
}

function professionalMetric(view: AnyRecord | null, key: string) {
  const value = view?.summary?.[key];
  return Number.isFinite(Number(value)) ? String(Number(value)) : "0";
}

function exceptionSummary(view: AnyRecord | null): AnyRecord {
  const summary = view?.summary?.exception_summary;
  return summary && typeof summary === "object" ? summary as AnyRecord : {};
}

function firstText(values: unknown[], fallback = "") {
  for (const value of values) {
    const next = text(value, "");
    if (next) return next;
  }
  return fallback;
}

function isRawIdentifier(value: unknown) {
  const raw = text(value, "");
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)
    || /^[0-9a-f]{12,}$/i.test(raw);
}

function publicFocusSeat(value: unknown, fallback = "负责 NPC") {
  const raw = text(value, "");
  if (!raw || isRawIdentifier(raw)) return fallback;
  return raw;
}

function splitDeviceChannels(value: string) {
  const normalized = value.includes(":") ? value.slice(value.indexOf(":") + 1) : value;
  return normalized
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

const datasetTypes = [
  ["音频", "audio / transcript / score", "待标注 18"],
  ["视觉", "image / video / frame", "待复核 7"],
  ["传感器", "imu / force / current", "异常 3"],
  ["ROS bag", "topic / tf / camera_info", "缺 topic 2"],
  ["Episode", "action / state / instruction", "可训练 42"],
];

const activeSampleCards = [
  ["当前样本", "arm-episode-022", "片段 72-128 / joint + camera", "标注员正在确认抓取段落、落点标签和关键帧边界。"],
  ["当前片段", "frame 72-128", "抓取前摇 / 接触 / 抬升", "当前工作段聚焦在接触到抬升的关键片段。"],
  ["AI 预标注建议", "抓取 + 对齐", "置信 0.63 / 2 处冲突", "AI 只给建议标签和片段建议，是否采纳由人确认。"],
  ["低置信定位", "frame 84 / frame 117", "夹爪角度波动 / depth 漂移", "先看低置信帧和片段，再决定补标、重标还是退回采集。"],
  ["QA 放行", "待人工放行", "schema 通过 / timestamp 待补", "QA 只在人工确认后放行到 manifest/export。"],
  ["训练回执", "等待回写", "dataset_v0.3.1", "导出后回看训练回执，再由人决定是否继续。"],
];

const annotationLabels = [
  ["抓取", "AI 建议", "0.63", "待人确认"],
  ["接触点", "冲突", "0.41", "先看帧 84"],
  ["抬升", "人工保留", "0.88", "可进 QA"],
];

const timelineSegments = [
  ["采集", "12-44", "ok"],
  ["预标注", "45-71", "ok"],
  ["当前复核", "72-128", "active"],
  ["QA", "129-151", "blocked"],
];

const sampleRows = [
  ["audio-intake-014", "采集任务", "待预标注", "audio + transcript", "上传完成，等待 AI 给出预标注建议", "看预标注建议", "workbench"],
  ["arm-episode-022", "AI 预标注建议", "低置信复核", "joint + camera", "关键帧动作得分偏低，等待标注员确认", "去复核", "workbench"],
  ["imu-telemetry-118", "低置信复核", "QA", "imu.acc gap", "需先补 timestamp 再进 QA", "看异常", "observability"],
  ["rosbag-2026-05-12", "manifest/export", "训练回执", "tf + camera", "人工确认导出后，等待训练回执", "收回执", "receipt"],
];

const qualityRows = [
  ["schema", "通过", "字段完整，待人工确认后进入 manifest", "看导出区", "versions"],
  ["privacy", "通过", "无手机号/邮箱，可继续", "人工核对", "versions"],
  ["files", "待查", "2 个样本缺附件，需要标注员回复核", "派复核", "workbench"],
  ["timestamp", "警告", "IMU 有 80ms 断点，阻塞训练", "看异常", "observability"],
];

const versionRows = [
  ["dataset_v0.3.1", "manifest + export", "等待训练回执", "收回执", "observability"],
  ["speech_seed_v2", "audio manifest", "待低置信复核完成", "去复核", "workbench"],
  ["episode_arm_v1", "episode manifest", "待 QA 收口", "看 QA", "observability"],
];

const intakeStages = [
  ["采集任务", "12 路", "2 路待补元数据", "补采集", "workbench"],
  ["样本队列", "48 批", "7 批等 AI 预标注建议", "看队列", "queue"],
  ["低置信复核", "18 条", "7 条待人工确认", "去复核", "quality"],
  ["manifest/export", "3 版", "1 版等待训练回执", "去导出", "versions"],
];

const triageRows = [
  ["IMU 时间断点", "高", "118", "卡在 QA，等人工补 timestamp 再导出", "看异常", "observability"],
  ["音频缺 transcript", "中", "014", "卡在 AI 建议后复核，回工作台派单", "派复核", "workbench"],
  ["ROS bag 缺 topic", "高", "2026-05-12", "卡在 manifest/export，先补采集规则", "补采集", "workbench"],
];

const exportRows = [
  ["训练集", "dataset_v0.3.1", "42 条已出 manifest，等待训练回执", "看回执", "observability"],
  ["回放集", "episode_arm_v1", "7 条仍在低置信复核", "回工作台", "workbench"],
  ["质检单", "quality_manifest_v4", "3 条异常会回流到样本队列", "看异常", "observability"],
];

const actionFlowRows = [
  ["采集任务", "补元数据", "回 NPC 工作台", "先把采集任务补齐，再让样本进入队列", "补采集", "workbench"],
  ["AI 预标注建议", "看建议", "派给 NPC", "AI 先给出建议标签，再由人决定是否采纳", "看预标注建议", "workbench"],
  ["低置信复核", "人工确认", "看异常 / 回工作台", "把低置信样本压到 QA 之前，由人确认收口", "去复核", "quality"],
  ["QA", "人工放行", "处理异常", "schema / privacy / timestamp 通过后，再由人决定是否导出", "看异常", "observability"],
  ["manifest/export", "人工确认导出", "送去实验室", "只让人工确认过的版本进入训练和回放", "去导出", "ai-lab"],
  ["训练回执", "看结果", "看观测台", "导出后回来看最小回执和训练结果，再决定下一步", "收回执", "observability"],
];

const blockerCards = [
  ["当前卡点", "低置信复核 7 条", "先派复核任务，再进 QA", "去复核", "workbench"],
  ["导出阻塞", "IMU timestamp", "修完再放行 manifest/export", "看异常", "observability"],
  ["训练等待", "训练回执未齐", "回工作台或观测台收结果", "收回执", "receipt"],
];

const quickActionChips = [
  ["派复核", "low-confidence"],
  ["看异常", "exceptions"],
  ["送实验室", "export"],
  ["收回执", "receipt"],
];

const sideRuleCards = [
  ["标注边界", "人确认", "AI 只给建议标签，是否采纳由标注员决定。"],
  ["QA 放行", "人放行", "schema、timestamp、privacy 通过后再放行。"],
  ["导出边界", "人确认", "只导出人工确认过的版本，不自动送训。"],
  ["训练回看", "看回执", "训练完成后回来看回执，再决定下一步。"],
];

const sideEvidenceRows = [
  ["schema", "12 字段", "manifest 字段已对齐训练入口。"],
  ["导出规则", "3 条", "episode、audio、rosbag 分开出单。"],
  ["训练回执", "dataset_v0.3.1", "等待训练完成后回写。"],
];

const sideExportConfigRows = [
  ["manifest", "dataset_v0.3.1", "人工确认字段后再出训练单。"],
  ["回流策略", "异常回队列", "QA 未放行的样本回到复核或采集。"],
  ["训练入口", "AI 实验室", "导出完成后再由人决定是否送训。"],
];

const sampleDecisionRows = [
  ["标签确认", "人确认", "采纳或修改 AI 建议后，人工提交标签和片段边界。"],
  ["低置信处理", "人判断", "先补标、重标或退回采集，不自动收口。"],
  ["导出边界", "人确认", "QA 通过后再决定是否进入 manifest/export 和训练回执。"],
];

export default async function ProjectDatasetsPage({
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
    intake?: string;
    device_mode?: string;
    channels?: string;
    rate?: string;
    window?: string;
    schema?: string;
    source_title?: string;
    source_label?: string;
  };
}) {
  const projectId = params.id;
  const auth = await getCurrentAuthState();
  if (!auth.data?.user) {
    redirect(`/login?returnTo=${encodeURIComponent(`/projects/${projectId}/datasets`)}`);
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

  const [
    computersState,
    threadWorkstationsState,
    workstationsState,
    skillsState,
    documentsState,
    assignmentsState,
    membersState,
    taskProfessionalState,
  ] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    getProjectWorkstationsState(projectId),
    getProjectSkillsState(projectId),
    getProjectKnowledgeDocumentsState(projectId),
    getSeatSkillAssignmentsState(projectId),
    getProjectMembersState(projectId),
    searchParams?.task_id ? getTaskProfessionalViewState(searchParams.task_id) : Promise.resolve({ data: null, status: 200, error: null }),
  ]);

  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(threadWorkstationsState.data);
  const workstations = asArray<AnyRecord>(workstationsState.data);
  const skills = asArray<AnyRecord>(skillsState.data);
  const documents = asArray<AnyRecord>(documentsState.data);
  const assignments = asArray<AnyRecord>(assignmentsState.data);
  const members = asArray<AnyRecord>(membersState.data);
  const taskView = taskProfessionalState.data as AnyRecord | null;
  const taskException = exceptionSummary(taskView);
  const messageFocus = Boolean(searchParams?.message_id || searchParams?.dispatch_id || searchParams?.source_seat);
  const focusTitle = text((searchParams as AnyRecord | undefined)?.source_title, "来自 NPC 工作台的证据链焦点");
  const focusSeat = publicFocusSeat((searchParams as AnyRecord | undefined)?.source_label ?? searchParams?.source_seat);
  const onlineComputers = computers.filter(computerDispatchReady).length;
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/datasets`;
  const repoReady = Boolean(project.github_url || project.local_git_url);
  const latestMessage = Array.isArray(taskView?.messages) ? (taskView.messages as AnyRecord[])[0] : null;
  const latestReceipt = Array.isArray(taskView?.receipts) ? (taskView.receipts as AnyRecord[])[0] : null;
  const latestDispatch = Array.isArray(taskView?.dispatches) ? (taskView.dispatches as AnyRecord[])[0] : null;
  const currentTaskId = text(taskView?.task?.id ?? taskView?.summary?.task_id, "");
  const currentDispatchId = firstText([
    searchParams?.dispatch_id,
    latestMessage?.dispatch_id,
    latestReceipt?.dispatch_id,
    latestDispatch?.id,
  ], "待生成");
  const currentSourceMessageId = firstText([
    searchParams?.message_id,
    latestReceipt?.source_message_id,
    latestMessage?.id,
  ], "待回流");
  const currentReceiptId = firstText([
    latestReceipt?.message_id,
    taskView?.summary?.latest_result_message_id,
  ], "等待回执");
  const currentReceiptCount = professionalMetric(taskView, "receipt_count");
  const currentArtifactCount = professionalMetric(taskView, "artifact_count");
  const currentSampleState = taskException.actionable ? "先处理异常样本，再由人确认下一步" : "可以继续人工标注、QA 放行或导出";
  const chainTaskParam = currentTaskId ? `&task_id=${encodeURIComponent(currentTaskId)}` : "";
  const chainMessageParam = currentSourceMessageId && currentSourceMessageId !== "待回流" ? `&message_id=${encodeURIComponent(currentSourceMessageId)}` : "";
  const workbenchHref = `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets${chainTaskParam}${chainMessageParam}`;
  const observabilityHref = `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=datasets${chainTaskParam}${chainMessageParam}`;
  const aiLabHref = `/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=datasets${chainTaskParam}${chainMessageParam}`;
  const intakeKind = text(searchParams?.intake, "");
  const deviceMode = text(searchParams?.device_mode, "");
  const hasDeviceIntakeDraft = intakeKind === "device" && ["can", "serial", "usb", "ros"].includes(deviceMode);
  const deviceModeLabel = deviceMode === "can" ? "CAN 调试" : deviceMode === "serial" ? "串口调试" : deviceMode === "usb" ? "USB 调试" : "ROS 只读桥";
  const deviceSamplingDraft = {
    title: text(searchParams?.source_title, `${deviceModeLabel}采样任务草案`),
    mode: deviceModeLabel,
    channels: text(searchParams?.channels, "待选择通道"),
    rate: text(searchParams?.rate, "待设定频率"),
    window: text(searchParams?.window, "待设定窗口"),
    schema: text(searchParams?.schema, "待确认字段"),
  };
  const deviceChannelList = splitDeviceChannels(deviceSamplingDraft.channels);
  const deviceRunnerState = onlineComputers > 0 ? `${onlineComputers} 台执行电脑在线` : "执行电脑能力待确认";
  const deviceSchemaFields = deviceSamplingDraft.schema
    .split("+")
    .map((item) => item.trim())
    .filter(Boolean);
  const roboticsReturnHref = `/projects/${projectId}/robotics?debug=${encodeURIComponent(deviceMode || "can")}&return_to=${encodeURIComponent(selfPath)}&from=datasets`;
  const activeViewer = hasDeviceIntakeDraft
    ? {
        sample: `${deviceMode || "device"}-intake-draft`,
        range: `${deviceSamplingDraft.rate} · ${deviceSamplingDraft.window}`,
        meta: `${deviceSamplingDraft.channels} · ${deviceSamplingDraft.schema}`,
      }
    : {
        sample: "arm-episode-022",
        range: "frame 72-128",
        meta: "joint + camera + imu · 当前只做复核和建议整理",
      };
  const activeCardsForView = hasDeviceIntakeDraft
    ? [
        ["当前样本", deviceSamplingDraft.title, deviceSamplingDraft.mode, "从设备调试台带来的只读采样草案，先确认通道、频率和窗口。"],
        ["当前片段", deviceSamplingDraft.window, deviceSamplingDraft.channels, "先只读采集，不触发真实设备动作或参数写入。"],
        ["AI 预标注建议", "等待采样", deviceSamplingDraft.schema, "AI 只能在样本入库后给出字段解释和低置信建议。"],
        ["低置信定位", "待生成", "采样后计算", "采样完成后再定位断点、缺字段、异常帧和低置信片段。"],
        ["QA 放行", "待人工放行", "schema / timestamp / 来源待核", "QA 只在人工确认后进入 manifest/export。"],
        ["训练回执", "等待回写", "采样未完成", "导出和训练都要等人工确认后的数据版本。"],
      ]
    : activeSampleCards;
  const sampleRowsForView = hasDeviceIntakeDraft
    ? [
        [
          `${deviceMode || "device"}-intake-draft`,
          "设备采样草案",
          "采集任务",
          `${deviceSamplingDraft.rate} · ${deviceSamplingDraft.window}`,
          deviceSamplingDraft.channels,
          "确认采样",
          "workbench",
        ],
        ...sampleRows,
      ]
    : sampleRows;
  const contextCards = [
    { label: "任务", value: currentTaskId ? "已聚焦" : "当前焦点", detail: taskView ? "当前工作对象" : "等待派单进入数据工场" },
    { label: "派单", value: currentDispatchId === "待生成" ? "待生成" : "已进入队列", detail: "当前执行链路" },
    { label: "回执", value: currentReceiptId === "等待回执" ? "等待回执" : "已回流", detail: `${currentReceiptCount} 条最小/最终回执` },
    { label: "证据", value: currentArtifactCount, detail: "manifest / schema / 异常样本" },
  ];
  const sourceMessageState = currentSourceMessageId === "待回流" || !currentSourceMessageId ? "待回流" : "已回流";
  const nextActionCards = [
    {
      label: "采集队列",
      title: "先收样本，再看 AI 预标注建议",
      detail: taskException.actionable ? "异常样本优先，避免脏数据继续向后流。" : "先补齐 transcript、topic 和 episode 元数据，再由 AI 辅助给出预标注建议。",
      href: "#queue",
    },
    {
      label: "待复核",
      title: "先收低置信样本，再由人确认 QA",
      detail: "先收低置信样本，再看 schema、timestamp、privacy、缺 topic，由人决定是否放行。",
      href: taskException.actionable
        ? `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=datasets`
        : "#quality",
    },
    {
      label: "导出 / 回执",
      title: "人工确认导出，再收训练回执",
      detail: "只把人工确认过的版本送去实验室，再回来看最小回执和训练结果。",
      href: "#versions",
    },
  ];

  const metrics = [
    ["样本", "70"],
    ["待预标注", "18"],
    ["待复核", "7"],
    ["可训练", "42"],
  ];
  const topLinks = [
    { label: "NPC 工作台", href: workbenchHref },
    { label: "数据工场", href: selfPath, active: true },
    { label: "AI 实验室", href: aiLabHref },
    { label: "机器人现场", href: `/projects/${projectId}/robotics?return_to=${encodeURIComponent(selfPath)}&from=datasets` },
    { label: "观测台", href: observabilityHref },
    ...(returnTo ? [{ label: labelProjectReturnPath(returnTo), href: returnTo }] : []),
  ];
  const sectionLinks = [
    { label: "采集任务", href: "#queue", detail: "来源 / 频率 / 元数据", active: text(searchParams?.intake, "") === "device" },
    { label: "当前样本", href: "#types", detail: "样本 / 片段 / 标签" },
    { label: "AI 预标注", href: "#queue", detail: "建议 / 置信度 / 冲突" },
    { label: "低置信", href: "#quality", detail: "复核 / 退回 / 补标" },
    { label: "QA 放行", href: "#quality", detail: "schema / privacy / timestamp" },
    { label: "导出版本", href: "#versions", detail: "manifest / export" },
    { label: "训练回执", href: workbenchHref, detail: "回执 / 指标 / 下一步" },
  ];
  const resourceCards = [
    ["执行电脑", `${onlineComputers}/${computers.length}`, observabilityHref],
    ["NPC", `${seats.length}`, workbenchHref],
    ["工位", `${workstations.length}`, observabilityHref],
    ["能力包", `${skills.length}`, workbenchHref],
    ["知识库", `${documents.length}`, observabilityHref],
    ["Git", repoReady ? "已设置" : "待设置", observabilityHref],
  ];
  const actions: Array<[string, string, boolean?]> = [
    ["派给 NPC", workbenchHref, true],
    ["创建采集 / 预标注建议任务", workbenchHref],
    ["送去实验室", aiLabHref],
    ["查看异常", observabilityHref],
  ];
  const capabilityCards = [
    { label: "任务", detail: "采集、预标注建议、复核、QA、导出" },
    { label: "回执", detail: "平台只收最小回执和训练 / 导出结果" },
    { label: "证据", detail: "样本、manifest、schema、异常索引" },
    { label: "能力", detail: "排队、预标注建议、低置信定位、QA 提示、导出任务" },
  ];
  const signalCards = [
    { label: "低置信复核", value: "7", detail: "先收低置信样本，再进入 QA。", href: workbenchHref, actionLabel: "派复核任务" },
    { label: "异常样本", value: "3", detail: "先处理 imu gap 和缺 topic 的样本。", href: observabilityHref, actionLabel: "看异常入口" },
    { label: "训练回执", value: `${currentReceiptCount}`, detail: "导出后回工作台或观测台看训练回执。", href: workbenchHref, actionLabel: "回工作台" },
  ];
  const actionHref = (target: string) =>
    target === "observability"
      ? observabilityHref
      : target === "versions"
        ? "#versions"
        : target === "quality"
          ? "#quality"
          : target === "queue"
            ? "#queue"
            : target === "types"
              ? "#types"
      : target === "ai-lab"
        ? aiLabHref
        : target === "receipt"
          ? workbenchHref
          : workbenchHref;

  return (
    <ProfessionalEvidenceShell
      projectId={projectId}
      pageKey="datasets"
      pageTitle="数据工场"
      pageSummary="中心工作面只保留样本队列、质检矩阵和数据版本时间线，不展示长日志。"
      projectName={text(project.name, "项目")}
      topLinks={topLinks}
      sectionLinks={sectionLinks}
      taskView={taskView}
      focusTitle={taskView ? text(taskView.task?.title, focusTitle) : focusTitle}
      focusSeat={focusSeat}
      taskActions={actions.map(([label, href, primary]) => ({ label, href, primary: Boolean(primary) }))}
      capabilityCards={capabilityCards}
      signalCards={signalCards}
    >
      <section className={styles.workspace}>
        <section className={styles.taskWorkbench} aria-label="当前数据任务工作台">
          <div className={styles.taskWorkbenchHead}>
            <div>
              <span>当前证据链</span>
              <strong>{taskView ? text(taskView.task?.title, focusTitle) : focusTitle}</strong>
              <p>{focusSeat} · {currentSampleState} · 质检和数据版本会沿同一条证据链回流。</p>
            </div>
            <div className={styles.taskWorkbenchActions}>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets${currentTaskId ? `&task_id=${encodeURIComponent(currentTaskId)}` : ""}${currentSourceMessageId && currentSourceMessageId !== "待回流" ? `&message_id=${encodeURIComponent(currentSourceMessageId)}` : ""}`}>回 NPC 工作台</Link>
              <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=datasets${currentTaskId ? `&task_id=${encodeURIComponent(currentTaskId)}` : ""}`}>看观测台</Link>
            </div>
          </div>
          <div className={styles.chainGrid}>
            {contextCards.map((card) => (
              <article key={card.label}>
                <span>{card.label}</span>
                <strong>{card.value}</strong>
                <small>{card.detail}</small>
              </article>
            ))}
            <article>
              <span>质检</span>
              <strong>人工确认</strong>
              <small>schema / privacy / timestamp 通过后才能放行</small>
            </article>
            <article>
              <span>数据版本</span>
              <strong>manifest/export</strong>
              <small>只把人工确认过的数据版本送入实验室</small>
            </article>
            <article>
              <span>执行电脑调度</span>
              <strong>{deviceRunnerState}</strong>
              <small>采样、回执和异常状态回观测台收口</small>
            </article>
          </div>
          <div className={styles.nextActionGrid}>
            {nextActionCards.map((card) => (
              card.href.startsWith("#") ? (
                <a key={card.label} href={card.href}>
                  <span>{card.label}</span>
                  <strong>{card.title}</strong>
                  <p>{card.detail}</p>
                </a>
              ) : (
                <Link key={card.label} href={card.href}>
                  <span>{card.label}</span>
                  <strong>{card.title}</strong>
                  <p>{card.detail}</p>
                </Link>
              )
            ))}
          </div>
        </section>

        {hasDeviceIntakeDraft ? (
          <section className={styles.deviceIntakeDraft} aria-label="设备采样任务草案">
            <div className={styles.deviceIntakeHead}>
              <div>
                <span>设备采样任务草案</span>
                <strong>{deviceSamplingDraft.title}</strong>
                <p>这只是从机器人现场带来的只读采样建议，采样、QA 和导出都需要人确认。</p>
              </div>
              <div className={styles.deviceIntakeActions}>
                <Link href={roboticsReturnHref}>回调试台</Link>
                <Link href={workbenchHref}>交给 NPC 整理</Link>
              </div>
            </div>
            <div className={styles.deviceIntakeGrid}>
              <article>
                <span>调试模式</span>
                <strong>{deviceSamplingDraft.mode}</strong>
                <small>只读进入采集队列</small>
              </article>
              <article>
                <span>通道</span>
                <strong>{deviceSamplingDraft.channels}</strong>
                <small>由人确认是否全部采集</small>
              </article>
              <article>
                <span>频率 / 窗口</span>
                <strong>{deviceSamplingDraft.rate} · {deviceSamplingDraft.window}</strong>
                <small>执行电脑按能力实际落地</small>
              </article>
              <article>
                <span>字段草案</span>
                <strong>{deviceSamplingDraft.schema}</strong>
                <small>进入 manifest 前先过 QA</small>
              </article>
            </div>
            <div className={styles.deviceIntakeWorkbench}>
              <section>
                <div className={styles.deviceIntakeSubhead}>
                  <span>通道队列</span>
                  <strong>逐项确认是否采样</strong>
                </div>
                <div className={styles.deviceChannelRows}>
                  {(deviceChannelList.length ? deviceChannelList : ["待选择通道"]).map((channel, index) => (
                    <article key={`${channel}-${index}`}>
                      <strong>{channel}</strong>
                      <span>{index === 0 ? "主通道" : "候选通道"}</span>
                      <small>{deviceSamplingDraft.rate} · {deviceSamplingDraft.window}</small>
                    </article>
                  ))}
                </div>
              </section>
              <section>
                <div className={styles.deviceIntakeSubhead}>
                  <span>采样控制</span>
                  <strong>先生成任务，再人工确认采样</strong>
                </div>
                <div className={styles.deviceDraftControls}>
                  <article>
                    <span>执行电脑</span>
                    <strong>{deviceRunnerState}</strong>
                    <small>{onlineComputers > 0 ? "真实采集前仍需人工确认权限和设备连接。" : "先去观测台确认 runner、端口权限和采集能力。"}</small>
                  </article>
                  <article>
                    <span>采样频率</span>
                    <strong>{deviceSamplingDraft.rate}</strong>
                    <small>草案值，不会直接启动真实采集。</small>
                  </article>
                  <article>
                    <span>字段映射</span>
                    <strong>{deviceSchemaFields.length ? deviceSchemaFields.join(" / ") : "待确认字段"}</strong>
                    <small>入库前由人确认 schema、timestamp 和单位。</small>
                  </article>
                </div>
              </section>
            </div>
          </section>
        ) : null}

        <section className={styles.blockerStrip} aria-label="当前卡点">
          {blockerCards.map(([label, value, detail, actionLabel, target]) => {
            const href =
              target === "observability"
                ? `/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=datasets`
                : target === "receipt"
                  ? `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets${currentTaskId ? `&task_id=${encodeURIComponent(currentTaskId)}` : ""}`
                  : `/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`;
            return (
              <article key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <p>{detail}</p>
                <Link href={href}>{actionLabel}</Link>
              </article>
            );
          })}
        </section>

        {taskView || messageFocus ? (
          <section className={styles.contextPanel} aria-label="任务证据链">
            <div>
              <span>当前消息上下文</span>
              <strong>{taskView ? text(taskView.task?.title, focusTitle) : focusTitle}</strong>
              <small>
                {focusSeat} · 消息 {sourceMessageState}
              </small>
            </div>
            <div className={styles.contextStats}>
              <article><span>派单</span><strong>{professionalMetric(taskView, "dispatch_count")}</strong></article>
              <article><span>回执</span><strong>{currentReceiptCount}</strong></article>
              <article><span>证据</span><strong>{professionalMetric(taskView, "artifact_count")}</strong></article>
              <article data-alert={taskException.actionable ? "1" : undefined}>
                <span>异常</span><strong>{String(taskException.failed ?? 0)}</strong>
              </article>
            </div>
            <div className={styles.contextActions}>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>回工作台</Link>
              <Link href={`/projects/${projectId}/ai-lab?task_id=${encodeURIComponent(currentTaskId)}&message_id=${encodeURIComponent(currentSourceMessageId === "待回流" ? text(searchParams?.message_id, "") : currentSourceMessageId)}&return_to=${encodeURIComponent(selfPath)}&from=datasets`}>送去实验室</Link>
            </div>
          </section>
        ) : null}

        <section className={styles.mainGrid}>
          <section className={styles.activeSamplePanel} aria-label="当前标注工作对象">
            <div className={styles.panelHead}>
              <span>当前样本 / 标注台</span>
              <Link href={`#quality`}>看 QA 状态</Link>
            </div>
            <div className={styles.annotationWorkbench}>
              <div className={styles.sampleViewer}>
                <div className={styles.viewerMeta}>
                  <span>{activeViewer.sample}</span>
                  <strong>{activeViewer.range}</strong>
                  <small>{activeViewer.meta}</small>
                </div>
                <div className={styles.frameStage} aria-hidden="true">
                  <i />
                  <i />
                  <i />
                  <b />
                </div>
                <div className={styles.timeline}>
                  {timelineSegments.map(([label, range, state]) => (
                    <article key={label} data-state={state}>
                      <span>{label}</span>
                      <strong>{range}</strong>
                    </article>
                  ))}
                </div>
              </div>
              <div className={styles.labelInspector}>
                <div>
                  <span>标签建议</span>
                  <strong>AI 只给建议，标注员确认后才写入</strong>
                </div>
                {annotationLabels.map(([label, state, score, note]) => (
                  <article key={label} data-state={state}>
                    <strong>{label}</strong>
                    <span>{state}</span>
                    <small>{score}</small>
                    <p>{note}</p>
                  </article>
                ))}
              </div>
            </div>
            <div className={styles.activeSampleGrid}>
              {activeCardsForView.map(([label, value, meta, detail]) => (
                <article key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                  <small>{meta}</small>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
            <div className={styles.sampleDecisionStrip}>
              {sampleDecisionRows.map(([label, value, detail]) => (
                <article key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.queuePanel} id="queue">
            <div className={styles.panelHead}>
              <span>样本队列 / AI 预标注</span>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>派给 NPC</Link>
            </div>
            <div className={styles.panelActionBar}>
              <span>当前动作：先收样本，再看 AI 预标注建议</span>
              <div>
                <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>创建预标注建议任务</Link>
                <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>看异常</Link>
              </div>
            </div>
            <div className={styles.sampleTable}>
              {sampleRowsForView.map(([id, type, state, signal, owner, actionLabel, target]) => (
                <article key={id} data-state={state}>
                  <strong>{id}</strong>
                  <span>{type}</span>
                  <em>{state}</em>
                  <small>{signal}</small>
                  <small>{owner}</small>
                  <Link href={actionHref(target)}>{actionLabel}</Link>
                </article>
              ))}
            </div>
          </section>
        </section>

        <section className={styles.opsGrid}>
          <section className={styles.qualityPanel} id="quality">
            <div className={styles.panelHead}>
              <span>低置信复核 / QA</span>
              <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>派单</Link>
            </div>
            <div className={styles.panelActionBar}>
              <span>当前动作：先收低置信样本，再由人确认 QA 放行</span>
              <div>
                <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>派复核任务</Link>
                <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>处理异常</Link>
              </div>
            </div>
            <div className={styles.qualityRows}>
              {qualityRows.map(([name, state, detail, actionLabel, target]) => (
                <article key={name}>
                  <strong>{name}</strong>
                  <span>{state}</span>
                  <p>{detail}</p>
                  <Link href={actionHref(target)}>{actionLabel}</Link>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.versionPanel} id="versions">
            <div className={styles.panelHead}>
              <span>manifest / export</span>
              <Link href={`/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>训练入口</Link>
            </div>
            <div className={styles.panelActionBar}>
              <span>当前动作：人工确认导出后，再看训练回执</span>
              <div>
                <Link href={`/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>送去实验室</Link>
                <Link href={`/projects/${projectId}/workbench?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>回工作台</Link>
              </div>
            </div>
            <div className={styles.versionRows}>
              {versionRows.map(([name, bundle, state, actionLabel, target]) => (
                <article key={name}>
                  <strong>{name}</strong>
                  <small>{bundle}</small>
                  <span>{state}</span>
                  <Link href={actionHref(target)}>{actionLabel}</Link>
                </article>
              ))}
            </div>
          </section>
        </section>

        <section className={styles.drawerDeck} aria-label="数据工场抽屉">
          <details className={styles.detailDrawer}>
            <summary>
              <span>数据状态</span>
              <strong>样本 / 预标注 / 复核 / 可训练</strong>
            </summary>
            <div className={styles.metrics}>
              {metrics.map(([label, value]) => (
                <article key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </article>
              ))}
            </div>
          </details>

          <details className={styles.detailDrawer}>
            <summary>
              <span>阶段索引</span>
              <strong>采集到导出的任务链</strong>
            </summary>
            <div className={styles.intakeStrip}>
              {intakeStages.map(([label, value, detail, actionLabel, target]) => (
                <article key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                  <small>{detail}</small>
                  {target === "queue" || target === "quality" || target === "versions" ? (
                    <a href={`#${target}`}>{actionLabel}</a>
                  ) : (
                    <Link href={actionHref(target)}>{actionLabel}</Link>
                  )}
                </article>
              ))}
            </div>
          </details>

          <details className={styles.detailDrawer}>
            <summary>
              <span>异常 / 回流日志</span>
              <strong>卡点、回流和人工处理入口</strong>
            </summary>
            <div className={styles.triageRows}>
              {triageRows.map(([label, level, sample, detail, actionLabel, target]) => (
                <article key={label} data-level={level}>
                  <strong>{label}</strong>
                  <span>{level}</span>
                  <small>{sample}</small>
                  <p>{detail}</p>
                  <Link href={actionHref(target)}>{actionLabel}</Link>
                </article>
              ))}
            </div>
          </details>
        </section>

        <section className={styles.drawerDeck} id="triage" aria-label="底部日志抽屉">
          <details className={styles.detailDrawer}>
            <summary>
              <span>导出 / 回执日志</span>
              <strong>数据版本、manifest、导出和训练回写</strong>
            </summary>
            <div className={styles.exportRows}>
              {exportRows.map(([label, version, detail, actionLabel, target]) => (
                <article key={label}>
                  <strong>{label}</strong>
                  <span>{version}</span>
                  <p>{detail}</p>
                  <Link href={actionHref(target)}>{actionLabel}</Link>
                </article>
              ))}
            </div>
          </details>

          <details className={styles.detailDrawer}>
            <summary>
              <span>完整动作链</span>
              <strong>展开看采集到训练的全链路</strong>
            </summary>
            <div className={styles.actionFlowGrid}>
              {actionFlowRows.map(([label, action, next, detail, actionLabel, target]) => (
                <article key={label}>
                  <span>{label}</span>
                  <strong>{action}</strong>
                  <em>{next}</em>
                  <p>{detail}</p>
                  {target === "quality" ? (
                    <a href="#quality">{actionLabel}</a>
                  ) : (
                    <Link href={actionHref(target)}>{actionLabel}</Link>
                  )}
                </article>
              ))}
            </div>
          </details>
        </section>

      </section>
      <section className={styles.rightRail}>
        <section className={styles.resourcePanel}>
          <div className={styles.panelHead}>
            <span>Schema / 规则</span>
            <Link href={`/projects/${projectId}/observability?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>异常入口</Link>
          </div>
          <div className={styles.sideRuleGrid}>
            {sideRuleCards.map(([label, value, detail]) => (
              <article key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <p>{detail}</p>
              </article>
            ))}
          </div>
        </section>
        <section className={styles.resourcePanel}>
          <div className={styles.panelHead}>
            <span>证据 / 训练回执</span>
            <Link href={`/projects/${projectId}/ai-lab?return_to=${encodeURIComponent(selfPath)}&from=datasets`}>看实验室</Link>
          </div>
          <div className={styles.sideEvidenceList}>
            {sideEvidenceRows.map(([label, value, detail]) => (
              <article key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <p>{detail}</p>
              </article>
            ))}
          </div>
        </section>
        <section className={styles.resourcePanel}>
          <div className={styles.panelHead}>
            <span>导出配置</span>
            <Link href={`#versions`}>看导出区</Link>
          </div>
          <div className={styles.sideEvidenceList}>
            {sideExportConfigRows.map(([label, value, detail]) => (
              <article key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <p>{detail}</p>
              </article>
            ))}
          </div>
        </section>
        <details className={styles.detailDrawer} id="types">
          <summary>
            <span>数据对象</span>
            <strong>采集对象与当前状态</strong>
          </summary>
          <div className={styles.typeGrid}>
            {datasetTypes.map(([label, detail, state]) => (
              <article key={label} id={label}>
                <strong>{label}</strong>
                <p>{detail}</p>
                <span>{state}</span>
              </article>
            ))}
          </div>
        </details>
        <section>
          <span>数据资源</span>
          <div className={styles.resourceGrid}>
            {resourceCards.map(([label, value, href]) => (
              <Link key={label} href={href}>
                <span>{label}</span>
                <strong>{value}</strong>
              </Link>
            ))}
          </div>
          <div className={styles.resourceSummary}>
            <div><strong>{members.length}</strong><small>成员</small></div>
            <div><strong>{assignments.length}</strong><small>能力包绑定</small></div>
            <div><strong>{documents.length}</strong><small>知识库</small></div>
          </div>
        </section>
      </section>
    </ProfessionalEvidenceShell>
  );
}
