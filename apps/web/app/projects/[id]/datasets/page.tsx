import Link from "next/link";
import { redirect } from "next/navigation";
import {
  getCurrentAuthState,
  getProjectComputerNodesState,
  getProjectState,
  getProjectThreadWorkstationsState,
  getTaskProfessionalViewState,
} from "../../../../lib/server-data";
import { runnerCanDispatch } from "../../../../lib/runner-status";
import { ProfessionalWorkbenchShell } from "../_components/professional-evidence-shell";
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

const triageRows = [
  ["IMU 时间断点", "高", "118", "卡在 QA，等人工补 timestamp 再导出", "看异常", "observability"],
  ["音频缺 transcript", "中", "014", "卡在 AI 建议后复核，回工作台派单", "派复核", "workbench"],
  ["ROS bag 缺 topic", "高", "2026-05-12", "卡在 manifest/export，先补采集规则", "补采集", "workbench"],
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
    taskProfessionalState,
  ] = await Promise.all([
    getProjectComputerNodesState(projectId),
    getProjectThreadWorkstationsState(projectId),
    searchParams?.task_id ? getTaskProfessionalViewState(searchParams.task_id) : Promise.resolve({ data: null, status: 200, error: null }),
  ]);

  const computers = asArray<AnyRecord>(computersState.data);
  const seats = asArray<AnyRecord>(threadWorkstationsState.data);
  const taskView = taskProfessionalState.data as AnyRecord | null;
  const taskException = exceptionSummary(taskView);
  const focusTitle = text((searchParams as AnyRecord | undefined)?.source_title, "来自 NPC 工作台的数据任务焦点");
  const focusSeat = publicFocusSeat((searchParams as AnyRecord | undefined)?.source_label ?? searchParams?.source_seat);
  const onlineComputers = computers.filter(computerDispatchReady).length;
  const returnTo = safeProjectReturnPath(projectId, searchParams?.return_to);
  const selfPath = `/projects/${projectId}/datasets`;
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
  const deviceRunnerState = onlineComputers > 0 ? `${onlineComputers} 台执行电脑在线` : "执行通道待确认";
  const deviceSchemaFields = deviceSamplingDraft.schema
    .split("+")
    .map((item) => item.trim())
    .filter(Boolean);
  const roboticsReturnHref = `/projects/${projectId}/robotics?debug=${encodeURIComponent(deviceMode || "can")}&return_to=${encodeURIComponent(selfPath)}&from=datasets`;
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
  const actions: Array<[string, string, boolean?]> = [
    ["派给 NPC", workbenchHref, true],
    ["创建采集 / 预标注建议任务", workbenchHref],
    ["送去实验室", aiLabHref],
    ["查看异常", observabilityHref],
  ];
  const capabilityCards = [
    { label: "任务", detail: "采集、预标注建议、复核、QA、导出" },
    { label: "回执", detail: "平台只收最小回执和训练 / 导出结果" },
    { label: "产出", detail: "样本、manifest、schema、异常索引" },
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
    <ProfessionalWorkbenchShell
      projectId={projectId}
      pageKey="datasets"
      pageTitle="数据工场"
      pageSummary="像标注 IDE 一样管理数据：左侧选对象，中间只看当前工具，右侧开功能，底部看事件。"
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
      <section className={styles.ideSurface} aria-label="数据工场 IDE 工作面">
        <section className={styles.ideHero}>
          <div>
            <span>当前工具</span>
            <strong>{hasDeviceIntakeDraft ? "设备采样入库草案" : "样本队列与标注 QA"}</strong>
            <p>{hasDeviceIntakeDraft ? "从机器人现场带来的 CAN、串口、USB 或 ROS 只读采样建议，会先变成采集任务草案，再由人确认采样和入库。" : "数据工场只处理数据生命周期：采集、预标注建议、低置信复核、QA 放行、manifest/export 和训练回执。"}</p>
          </div>
          <div className={styles.ideHeroActions}>
            <Link href={workbenchHref}>派给 NPC</Link>
            <Link href={observabilityHref}>看记录</Link>
            <Link href={aiLabHref}>送实验室</Link>
          </div>
        </section>

        <div className={styles.ideMetrics}>
          {metrics.map(([label, value]) => (
            <article key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </article>
          ))}
        </div>

        {hasDeviceIntakeDraft ? (
          <section className={styles.ideToolPanel} aria-label="设备采样任务草案">
            <div className={styles.idePanelHead}>
              <div>
                <span>{deviceSamplingDraft.mode}</span>
                <strong>{deviceSamplingDraft.title}</strong>
              </div>
              <div>
                <Link href={roboticsReturnHref}>回调试台</Link>
                <Link href={workbenchHref}>交给 NPC 整理</Link>
              </div>
            </div>
            <div className={styles.ideFourGrid}>
              <article><span>通道</span><strong>{deviceSamplingDraft.channels}</strong><p>由人确认是否全部采集。</p></article>
              <article><span>频率 / 窗口</span><strong>{deviceSamplingDraft.rate} · {deviceSamplingDraft.window}</strong><p>这是草案，不会直接启动真实采集。</p></article>
              <article><span>字段</span><strong>{deviceSamplingDraft.schema}</strong><p>入库前确认 schema、timestamp 和单位。</p></article>
              <article><span>执行电脑</span><strong>{deviceRunnerState}</strong><p>采样前仍要确认 runner、端口权限和设备状态。</p></article>
            </div>
            <div className={styles.ideSplitGrid}>
              <section>
                <div className={styles.idePanelHead}><span>通道队列</span><strong>逐项确认</strong></div>
                <div className={styles.ideCompactRows}>
                  {(deviceChannelList.length ? deviceChannelList : ["待选择通道"]).map((channel, index) => (
                    <article key={`${channel}-${index}`}><strong>{channel}</strong><span>{index === 0 ? "主通道" : "候选通道"}</span><small>{deviceSamplingDraft.rate}</small></article>
                  ))}
                </div>
              </section>
              <section>
                <div className={styles.idePanelHead}><span>入库控制</span><strong>先任务后采样</strong></div>
                <div className={styles.ideCompactRows}>
                  <article><strong>字段映射</strong><span>{deviceSchemaFields.length ? deviceSchemaFields.join(" / ") : "待确认字段"}</span><small>进入 manifest 前先过 QA。</small></article>
                  <article><strong>人工确认</strong><span>必需</span><small>AI 只整理草案，不能替人确认采样。</small></article>
                </div>
              </section>
            </div>
          </section>
        ) : (
          <section className={styles.ideToolPanel} aria-label="样本队列工作区">
            <div className={styles.idePanelHead}>
              <div>
                <span>样本队列 / 当前样本</span>
                <strong>{taskView ? text(taskView.task?.title, focusTitle) : "arm-episode-022"}</strong>
              </div>
              <div>
                <a href="#quality">看 QA</a>
                <a href="#versions">看导出</a>
              </div>
            </div>
            <div className={styles.ideSplitGrid}>
              <section className={styles.sampleStage}>
                <div className={styles.frameStage} aria-hidden="true"><i /><i /><i /><b /></div>
                <div className={styles.timeline}>
                  {timelineSegments.map(([label, range, state]) => (
                    <article key={label} data-state={state}><span>{label}</span><strong>{range}</strong></article>
                  ))}
                </div>
              </section>
              <section className={styles.ideCompactRows}>
                {annotationLabels.map(([label, state, score, note]) => (
                  <article key={label} data-state={state}>
                    <strong>{label}</strong><span>{state} · {score}</span><small>{note}</small>
                  </article>
                ))}
              </section>
            </div>
            <div className={styles.ideTable}>
              {sampleRowsForView.map(([id, type, state, signal, owner, actionLabel, target]) => (
                <article key={id} data-state={state}>
                  <strong>{id}</strong>
                  <span>{type}</span>
                  <em>{state}</em>
                  <small>{signal}</small>
                  <p>{owner}</p>
                  <Link href={actionHref(target)}>{actionLabel}</Link>
                </article>
              ))}
            </div>
          </section>
        )}

        <section className={styles.ideTwoColumns} id="quality">
          <section>
            <div className={styles.idePanelHead}><span>低置信复核 / QA</span><Link href={workbenchHref}>派复核</Link></div>
            <div className={styles.ideCompactRows}>
              {qualityRows.map(([name, state, detail, actionLabel, target]) => (
                <article key={name}><strong>{name}</strong><span>{state}</span><p>{detail}</p><Link href={actionHref(target)}>{actionLabel}</Link></article>
              ))}
            </div>
          </section>
          <section id="versions">
            <div className={styles.idePanelHead}><span>manifest / export</span><Link href={aiLabHref}>训练入口</Link></div>
            <div className={styles.ideCompactRows}>
              {versionRows.map(([name, bundle, state, actionLabel, target]) => (
                <article key={name}><strong>{name}</strong><span>{bundle}</span><p>{state}</p><Link href={actionHref(target)}>{actionLabel}</Link></article>
              ))}
            </div>
          </section>
        </section>

        <details className={styles.ideDrawer}>
          <summary><span>数据对象 / 异常 / 完整动作链</span><strong>展开高级信息</strong></summary>
          <div className={styles.ideDrawerGrid}>
            {[...datasetTypes, ...triageRows.map(([label, level, sample, detail]) => [label, `${level} · ${sample}`, detail])].slice(0, 8).map(([label, detail, state]) => (
              <article key={`${label}-${detail}`}><strong>{label}</strong><span>{state}</span><p>{detail}</p></article>
            ))}
          </div>
        </details>
      </section>
    </ProfessionalWorkbenchShell>
  );
}
