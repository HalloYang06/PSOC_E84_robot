"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiClientUrl } from "../../../../lib/api-client-url";
import {
  下发机器人调试命令,
  创建机器人图表实验,
  创建机器人调试窗口,
  创建机器人数据预标注请求,
  创建机器人调参建议请求,
  创建机器人调试Npc操作审核,
  更新机器人调试窗口,
  删除机器人调试窗口,
  导出机器人标注数据,
  请求串口USB扫描,
  记录机器人采集片段,
} from "../../../actions";
import tileStyles from "../workbench/_components/npc-tile.module.css";
import workbenchStyles from "../workbench/workbench.module.css";
import styles from "./robotics.module.css";

type AnyRecord = Record<string, any>;

type DebugWindow = {
  id: string;
  runnerInterfaceId: string;
  name: string;
  kind: string;
  kindLabel: string;
  statusLabel: string;
  computerLabel: string;
  computerState: string;
  runnerTone: string;
  computerNodeId: string;
  runnerReady: boolean;
  runnerCanDispatch: boolean;
  runnerCanQueue: boolean;
  runnerHint: string;
  transport: string;
  boundNpc: string;
  baudRate?: string;
  sampleHz?: string;
  channels?: string;
  readCapability: boolean;
  writeCapabilityLabel: string;
  isUsable: boolean;
};

type TileTab = "terminal" | "dataset" | "chart";

type RoboticsWorkbenchClientProps = {
  projectId: string;
  projectName: string;
  windows: DebugWindow[];
  initialSavedWindows: SavedDebugWindow[];
  npcSeats: AnyRecord[];
  terminalMessages: AnyRecord[];
  initialOpenIds: string[];
  initialNpcId: string;
  onlineComputers: number;
  computerCount: number;
  scannedCount: number;
  notice?: string;
  error?: string;
};

type SavedDebugWindow = {
  resourceId: string;
  name: string;
  type: string;
  baudRate: string;
  sampleHz: string;
  channels: string;
  boundNpc: string;
};

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? value as AnyRecord : {};
}

function artifactDownloadHref(projectId: string, artifactPath: string) {
  const params = new URLSearchParams({ path: artifactPath });
  return apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/artifacts/download?${params.toString()}`);
}

function ArtifactPathActions({ projectId, artifactPath, label = "下载" }: { projectId: string; artifactPath: string; label?: string }) {
  if (!artifactPath) return null;
  return (
    <span className={styles.artifactActions}>
      <span>采集证据已生成</span>
      <a href={artifactDownloadHref(projectId, artifactPath)} download>
        {label}
      </a>
    </span>
  );
}

function seatId(seat: AnyRecord, fallback: string) {
  return text(seat.id ?? seat.config_id ?? seat.configId ?? seat.row_id ?? seat.name, fallback);
}

function seatName(seat: AnyRecord, fallback: string) {
  return userFacingTerminalText(seat.name ?? seat.label ?? seat.display_name ?? fallback);
}

function commandText(message: AnyRecord) {
  const extra = record(message.extra_data ?? message.metadata);
  const fromMeta = text(extra.terminal_command, "");
  if (fromMeta) return fromMeta;
  const mode = text(extra.terminal_mode, "");
  if (mode === "capture_start") return `开始采集 ${text(extra.capture_sample_hz, "100")}Hz`;
  if (mode === "capture_stop") return "停止采集并生成片段";
  const body = text(message.body, "");
  try {
    const payload = JSON.parse(body) as AnyRecord;
    const kind = text(payload.kind, "");
    if (kind === "robotics.capture.start") return `开始采集 ${text(payload.sample_hz, "100")}Hz`;
    if (kind === "robotics.capture.stop") return "停止采集并生成片段";
  } catch {}
  const match = body.match(/只读命令：(.+)/);
  return match?.[1]?.trim() || body.split("\n").find((line) => line.includes("listen")) || "只读调试命令";
}

function userFacingTerminalText(value: unknown) {
  return text(value, "")
    .replace(/\bRunner\b/g, "接单窗口")
    .replace(/\brunner\b/g, "接单窗口")
    .replace(/\badapters?\b/gi, "适配器")
    .replace(/\bbridges?\b/gi, "桥接器")
    .replace(/\bsession JSONL\b/gi, "会话记录")
    .replace(/\blocal path\b/gi, "当前电脑路径")
    .replace(/\bsource_thread\b/gi, "来源线程")
    .replace(/\bcanonical\b/gi, "标准")
    .replace(/\brequested id\b/gi, "请求编号")
    .replace(/\braw UUID\b/gi, "原始编号");
}

function roboticsCaptureAckLine(value: unknown) {
  const raw = text(value, "");
  if (!/robotics\.capture|device capture|capture_id|preview_summary/.test(raw)) return "";
  const jsonMatch = raw.match(/```json\s*([\s\S]*?)```/) ?? raw.match(/({[\s\S]*})/);
  if (!jsonMatch?.[1]) return "采集回执已返回";
  try {
    const payload = JSON.parse(jsonMatch[1]) as AnyRecord;
    const sampleCount = text(payload.sample_count, "0");
    const byteCount = text(payload.byte_count, "0");
    const error = text(payload.error, "");
    const sync = record(payload.repo_sync);
    const cache = record(payload.local_cache);
    const syncStatus = text(sync.status, "");
    const syncLine = captureSyncStatusLabel(syncStatus);
    const cacheLine = captureCacheStatusLabel(text(cache.status, ""));
    const parts = [`采集回执：${sampleCount} 个样本`];
    if (byteCount && byteCount !== "0") parts.push(`${byteCount} bytes`);
    if (payload.preview) parts.push("预览文件已生成");
    if (syncLine) parts.push(syncLine);
    if (cacheLine) parts.push(cacheLine);
    if (error) parts.push(`提示：${userFacingTerminalText(error)}`);
    return parts.join(" · ");
  } catch {
    return "采集回执已返回";
  }
}

function terminalEventLines(tile: DebugWindow, messages: AnyRecord[]) {
  const related = messages
    .filter((message) => {
      const extra = record(message.extra_data ?? message.metadata);
      return text(extra.terminal_interface_id, "") === tile.id
        || text(extra.source_message_id, "") && messages.some((source) => source.id === extra.source_message_id && text(record(source.extra_data ?? source.metadata).terminal_interface_id, "") === tile.id);
    })
    .slice(0, 8)
    .reverse();
  if (!related.length) {
    if (tile.runnerCanDispatch) {
      return ["[terminal] 暂无输入输出。用户自己输入会直接排队到执行电脑；NPC 代操作会先显示待审。"];
    }
    if (tile.runnerCanQueue) {
      return ["[terminal] 执行电脑暂不可立即接单。用户命令会进入队列，等目标电脑恢复后再处理；NPC 代操作仍需先待审。"];
    }
    return ["[terminal] 执行电脑未处于可排队状态。先重连接单窗口，再提交用户终端命令或 NPC 代操作审核。"];
  }
  return related.map((message) => {
    const type = text(message.message_type ?? message.messageType, "event");
    const status = text(message.status, "open");
    const extra = record(message.extra_data ?? message.metadata);
    if (type === "runner_command") return `$ ${commandText(message)}  # ${status}`;
    if (type === "runner_ack") return `[ack] ${roboticsCaptureAckLine(message.body) || userFacingTerminalText(message.body) || "执行电脑已接单"}`;
    if (type === "runner_result") {
      const result = record(extra.runner_result);
      const captureId = text(result.capture_id ?? extra.capture_id, "");
      if (captureId) {
        const mode = text(result.kind ?? extra.terminal_mode, "");
        const resultStatus = text(result.status, text(result.capture_mode, status));
        const sampleCount = text(result.sample_count, "");
        if (mode === "robotics.capture.start" || text(extra.terminal_mode, "") === "capture_start") {
          return `[capture:running] 目标电脑已开始后台采集 ${captureId}`;
        }
        if (sampleCount && sampleCount !== "0") {
          return `[capture:done] 已收到 ${sampleCount} 个样本`;
        }
        return `[capture:${resultStatus}] ${text(result.error, "执行电脑已返回采集回执")}`;
      }
      return `[result:${status}] ${userFacingTerminalText(message.body) || "执行电脑已返回结果"}`;
    }
    if (type === "robotics_capture_start") return `[capture:running] ${text(message.title, "开始采集")}`;
    if (type === "robotics_capture_segment") return `[capture:ready] ${text(message.title, "采集片段")} 已生成`;
    if (type === "robotics_terminal_review" || type === "robotics_terminal_npc_request") return `[npc-review:${status}] ${commandText(message)}`;
    return `[${type}:${status}] ${text(message.title ?? message.body, "终端事件")}`;
  });
}

function captureSegments(tile: DebugWindow, messages: AnyRecord[]) {
  const runnerResults = new Map<string, AnyRecord>();
  const resultScore = (result: AnyRecord) => {
    const points = record(record(result).preview_points);
    const summary = record(record(result).preview_summary);
    return (Number(result.sample_count) || 0)
      + Object.keys(record(points.series)).length * 1000
      + Object.keys(record(summary.numeric_fields)).length * 100
      + (text(result.kind, "") === "robotics.capture.stop" ? 10 : 0);
  };
  for (const message of messages) {
    const extra = record(message.extra_data ?? message.metadata);
    if (text(message.message_type ?? message.messageType, "") !== "runner_result") continue;
    const belongsToTile = text(extra.terminal_interface_id, "") === tile.id
      || text(extra.source_message_id, "") && messages.some((source) => source.id === extra.source_message_id && text(record(source.extra_data ?? source.metadata).terminal_interface_id, "") === tile.id);
    if (!belongsToTile) continue;
    const result = record(extra.runner_result);
    const captureId = text(result.capture_id ?? extra.capture_id, "");
    if (captureId) {
      const previous = runnerResults.get(captureId);
      if (!previous || resultScore(result) >= resultScore(previous)) runnerResults.set(captureId, result);
    }
  }
  return messages
    .filter((message) => {
      const extra = record(message.extra_data ?? message.metadata);
      return text(message.message_type ?? message.messageType, "") === "robotics_capture_segment"
        && text(extra.terminal_interface_id, "") === tile.id;
    })
    .map((message, index) => {
      const extra = record(message.extra_data ?? message.metadata);
      const channels = Array.isArray(extra.capture_channels) ? extra.capture_channels.map((item) => text(item, "")).filter(Boolean) : [];
      return {
        id: text(extra.capture_id, text(message.id, `capture-${index + 1}`)),
        title: text(message.title, `采集片段 ${index + 1}`),
        artifactPath: text(extra.artifact_path, ""),
        sampleHz: text(extra.capture_sample_hz, "100"),
        channels: channels.length ? channels : ["time", "signal.value", "status.code"],
        createdAt: text(message.created_at ?? message.createdAt ?? extra.stopped_at, ""),
        runnerResult: runnerResults.get(text(extra.capture_id, "")) || {},
      };
    })
    .reverse();
}

function tileEvents(tile: DebugWindow, messages: AnyRecord[], types: string[]) {
  return messages
    .filter((message) => {
      const extra = record(message.extra_data ?? message.metadata);
      return types.includes(text(message.message_type ?? message.messageType, ""))
        && text(extra.terminal_interface_id, "") === tile.id;
    })
    .slice(0, 6);
}

function segmentVariables(segments: ReturnType<typeof captureSegments>) {
  const values = new Set<string>();
  for (const segment of segments) {
    for (const channel of segment.channels) {
      values.add(channel);
    }
    const summary = record(record(segment.runnerResult).preview_summary);
    const numericFields = record(summary.numeric_fields);
    Object.keys(numericFields).forEach((name) => values.add(name));
    const previewPoints = record(record(segment.runnerResult).preview_points);
    const series = record(previewPoints.series);
    Object.keys(series).forEach((name) => values.add(name));
  }
  if (!values.size) {
    ["time", "signal.value", "status.code", "event.count"].forEach((item) => values.add(item));
  }
  return Array.from(values);
}

function captureSyncStatusLabel(status: string) {
  if (status === "pushed") return "已推送到仓库";
  if (status === "committed") return "已写入仓库证据";
  if (status === "unchanged") return "仓库证据已存在";
  if (status === "waiting_for_repo") return "等待配置仓库同步";
  if (status === "repo_missing") return "设备数据仓库不可用";
  if (status === "not_git_repo") return "设备数据仓库未初始化";
  if (status === "copy_failed") return "写入仓库失败";
  if (status === "git_add_failed" || status === "git_commit_failed") return "仓库登记失败";
  if (status === "push_failed") return "已本地提交，等待重试推送";
  return "";
}

function captureCacheStatusLabel(status: string) {
  if (status === "cleaned" || status === "already_clean") return "本机临时缓存已清理";
  if (status === "kept_for_retry") return "本机保留待同步缓存";
  if (status === "cleanup_failed") return "本机缓存待人工清理";
  return "";
}

function captureResultLine(segment: ReturnType<typeof captureSegments>[number]) {
  const result = record(segment.runnerResult);
  const sampleCount = text(result.sample_count, "");
  const byteCount = text(result.byte_count, "");
  const sync = record(result.repo_sync);
  const cache = record(result.local_cache);
  const preview = text(sync.preview, text(result.preview, ""));
  const syncStatus = text(sync.status, "");
  const error = text(result.error, "");
  const statusParts = [captureSyncStatusLabel(syncStatus), captureCacheStatusLabel(text(cache.status, ""))].filter(Boolean);
  const syncTail = statusParts.length ? ` · ${statusParts.join(" · ")}` : "";
  if (sampleCount && sampleCount !== "0") {
    return `已回传 ${sampleCount} 个样本${byteCount ? ` / ${byteCount} bytes` : ""}${preview ? " · 预览文件已生成" : ""}${syncTail}`;
  }
  if (preview) return `预览文件已生成${syncTail}`;
  if (syncTail) return syncTail.replace(/^ · /, "");
  if (error) return `采集回执：${error}`;
  return "";
}

function captureSummaryLine(segment: ReturnType<typeof captureSegments>[number]) {
  const summary = record(record(segment.runnerResult).preview_summary);
  const fields = record(summary.numeric_fields);
  const names = Object.keys(fields).slice(0, 3);
  if (!names.length) return "";
  return names.map((name) => {
    const stats = record(fields[name]);
    const min = text(stats.min, "");
    const max = text(stats.max, "");
    const mean = text(stats.mean, "");
    return `${name}: ${min}~${max}${mean ? ` / 均值 ${Number(mean).toFixed(3)}` : ""}`;
  }).join("；");
}

function captureTrainingRowLine(segment: ReturnType<typeof captureSegments>[number], variables: string[]) {
  const summary = record(record(segment.runnerResult).preview_summary);
  const fields = record(summary.numeric_fields);
  const selected = variables.filter((variable) => fields[variable]).slice(0, 3);
  if (!selected.length) return "";
  const count = selected.reduce((total, variable) => total + (Number(record(fields[variable]).count) || 0), 0);
  return `可导出 ${selected.join(" / ")} 的 count/min/max/mean 轻量训练行${count ? `，覆盖 ${count} 个样本统计` : ""}`;
}

function capturePreviewSeries(segment: ReturnType<typeof captureSegments>[number]) {
  const points = record(record(segment.runnerResult).preview_points);
  const series = record(points.series);
  return Object.entries(series)
    .map(([name, rawPoints]) => {
      const values = Array.isArray(rawPoints)
        ? rawPoints
            .map((point) => {
              const next = record(point);
              const x = Number(next.x);
              const y = Number(next.y);
              return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
            })
            .filter(Boolean) as { x: number; y: number }[]
        : [];
      return { name, values };
    })
    .filter((item) => item.values.length >= 2)
    .slice(0, 4);
}

function ChartPreview({ segment, targetValue }: { segment: ReturnType<typeof captureSegments>[number]; targetValue?: string }) {
  const series = capturePreviewSeries(segment);
  const target = Number(String(targetValue ?? "").trim());
  const hasTarget = Number.isFinite(target);
  if (!series.length) {
    return (
      <div className={styles.waveformPanel} data-empty="1">
        <strong>{segment.title}</strong>
        <span>等待低频预览点，先显示样本摘要</span>
        {captureSummaryLine(segment) ? <small>{captureSummaryLine(segment)}</small> : null}
      </div>
    );
  }
  const all = series.flatMap((item) => item.values);
  const minX = Math.min(...all.map((item) => item.x));
  const maxX = Math.max(...all.map((item) => item.x));
  const yValues = all.map((item) => item.y).concat(hasTarget ? [target] : []);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);
  const width = 320;
  const height = 150;
  const pad = 14;
  const sx = (x: number) => pad + ((x - minX) / Math.max(maxX - minX, 1)) * (width - pad * 2);
  const sy = (y: number) => height - pad - ((y - minY) / Math.max(maxY - minY, 1)) * (height - pad * 2);
  const targetY = hasTarget ? sy(target) : 0;
  return (
    <div className={styles.waveformPanel}>
      <div className={styles.waveformHead}>
        <strong>{segment.title}</strong>
        <small>{series.map((item) => item.name).join(" / ")}</small>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${segment.title} 预览波形`}>
        <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} />
        <line x1={pad} y1={pad} x2={pad} y2={height - pad} />
        {hasTarget ? <line className={styles.targetLine} x1={pad} y1={targetY} x2={width - pad} y2={targetY} /> : null}
        {series.map((item, index) => (
          <polyline
            key={item.name}
            className={styles[`waveLine${index + 1}` as keyof typeof styles] || styles.waveLine1}
            points={item.values.map((point) => `${sx(point.x).toFixed(1)},${sy(point.y).toFixed(1)}`).join(" ")}
          />
        ))}
      </svg>
      <small>{minY.toFixed(3)} ~ {maxY.toFixed(3)}{hasTarget ? ` · 目标 ${targetValue}` : ""}</small>
    </div>
  );
}

function HiddenTileFields({
  tile,
  returnTo,
  boundNpcId,
  boundNpcLabel,
}: {
  tile: DebugWindow;
  returnTo: string;
  boundNpcId: string;
  boundNpcLabel: string;
}) {
  return (
    <>
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
      <input type="hidden" name="interface_id" value={tile.id} />
      <input type="hidden" name="runner_interface_id" value={tile.runnerInterfaceId || tile.id} />
      <input type="hidden" name="interface_name" value={tile.name} />
      <input type="hidden" name="interface_kind" value={tile.kindLabel} />
      <input type="hidden" name="bound_npc" value={boundNpcId} />
      <input type="hidden" name="bound_npc_label" value={boundNpcLabel} />
    </>
  );
}

function terminalLines(tile: DebugWindow, boundNpcLabel: string) {
  const dispatchMode = tile.runnerCanDispatch ? "可接单" : tile.runnerCanQueue ? "排队等恢复" : "暂停提交";
  const sampleHz = text(tile.sampleHz, "100");
  const baudRate = text(tile.baudRate, "115200");
  const lines = [
    `$ open ${tile.name}`,
    `接口=${tile.kindLabel}  电脑=${tile.computerLabel}`,
    `状态=${tile.statusLabel}  模式=用户终端`,
    `接单=${dispatchMode}  电脑状态=${tile.computerState}`,
    `读取=${tile.readCapability ? "可用" : "不可用"}  写入=${tile.writeCapabilityLabel}`,
    `协助NPC=${boundNpcLabel || tile.boundNpc || "未绑定，创建或设置时选择 NPC"}`,
  ];
  if (tile.kind === "can") {
    lines.push(`filter=none  bitrate=待确认  sample=${sampleHz}Hz`);
    lines.push("hint: 用户在这里手动发送不需要平台审核；NPC 代发必须先待审。");
  } else if (tile.kind === "spi-can") {
    lines.push("chip=MCP251x  spi-clock=待确认  irq=待确认");
    lines.push("hint: SPI-CAN 只给配置建议，不直接改 overlay / module。");
  } else if (tile.kind === "serial") {
    lines.push(`baud=${baudRate}  parity=none  stop=1`);
    lines.push("hint: 用户手动输入直接进执行电脑；NPC 代写串口命令必须先待审。");
  } else if (tile.kind === "usb") {
    lines.push("mode=enumerate  driver=待确认");
    lines.push("hint: 只读枚举设备，权限或驱动问题进入公司层证据。");
  } else if (tile.kind === "ros") {
    lines.push("topics=readonly  publish=blocked");
    lines.push("hint: ROS publish/service/action 若由 NPC 代操作，必须先待审。");
  } else {
    lines.push("config=等待扫描快照");
  }
  return lines;
}

function submitLabel(tile: DebugWindow) {
  if (tile.runnerCanDispatch) return "提交终端请求";
  if (tile.runnerCanQueue) return "排队等重连";
  return "需重连";
}

function submitTitle(tile: DebugWindow) {
  if (tile.runnerCanDispatch) return "目标电脑正在持续接单，会排队并等待最小回执";
  if (tile.runnerCanQueue) return "目标电脑最近在线或等待恢复，命令会排队但不会假装已执行";
  return tile.runnerHint;
}

function windowsHref(projectId: string, openIds: string[], npcId = "") {
  const params = new URLSearchParams();
  if (openIds.length) params.set("windows", openIds.join(","));
  if (npcId) params.set("npc", npcId);
  const suffix = params.toString();
  return `/projects/${projectId}/robotics${suffix ? `?${suffix}` : ""}`;
}

function kindLabelForConfig(kind: string, fallback: string) {
  switch (kind) {
    case "serial": return "串口";
    case "can": return "CAN";
    case "usb": return "USB";
    case "spi-can": return "SPI-CAN";
    case "ros": return "ROS";
    default: return fallback || "接口";
  }
}

function configuredDebugWindows(resources: DebugWindow[], configs: SavedDebugWindow[]) {
  return configs
    .map((config) => {
      const source = resources.find((item) => item.id === config.resourceId);
      if (!source) return null;
      return {
        ...source,
        name: text(config.name, source.name),
        kind: text(config.type, source.kind),
        kindLabel: kindLabelForConfig(text(config.type, source.kind), source.kindLabel),
        boundNpc: text(config.boundNpc, source.boundNpc),
        baudRate: text(config.baudRate, "115200"),
        sampleHz: text(config.sampleHz, "100"),
        channels: text(config.channels, "time,signal.value,status.code,event.count"),
      };
    })
    .filter(Boolean) as DebugWindow[];
}

function DebugTile({
  projectId,
  tile,
  openIds,
  npcSeats,
  terminalMessages,
  initialNpcId,
  onClose,
}: {
  projectId: string;
  tile: DebugWindow;
  openIds: string[];
  npcSeats: AnyRecord[];
  terminalMessages: AnyRecord[];
  initialNpcId: string;
  onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<TileTab>("terminal");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [boundNpcId, setBoundNpcId] = useState(initialNpcId);
  const selectedNpcRecord = npcSeats.find((seat) => seatId(seat, "") === boundNpcId);
  const boundNpcLabel = selectedNpcRecord ? seatName(selectedNpcRecord, boundNpcId) : "";
  const effectiveBoundNpcId = text(boundNpcId, tile.boundNpc);
  const effectiveBoundNpcLabel = boundNpcLabel || tile.boundNpc || "";
  const returnTo = windowsHref(projectId, openIds, boundNpcId);
  const segments = captureSegments(tile, terminalMessages);
  const variables = segmentVariables(segments);
  const datasetEvents = tileEvents(tile, terminalMessages, ["robotics_annotation_request", "robotics_dataset_export"]);
  const chartEvents = tileEvents(tile, terminalMessages, ["robotics_chart_snapshot", "robotics_tuning_request"]);
  const [chartTargetValue, setChartTargetValue] = useState("");
  const sampleHz = text(tile.sampleHz, "100");
  const baudRate = text(tile.baudRate, "115200");
  const channels = text(tile.channels, "time,signal.value,status.code,event.count");

  return (
    <article className={tileStyles.tile}>
      <header className={tileStyles.head}>
        <div className={tileStyles.headLeft}>
          <strong className={tileStyles.name}>{tile.name}</strong>
          <small className={tileStyles.subline}>{tile.kindLabel} · {tile.transport} · {tile.computerState}</small>
        </div>
        <div className={tileStyles.headActions}>
          <button type="button" className={tileStyles.closeBtn} onClick={onClose} aria-label={`关闭 ${tile.name}`}>×</button>
        </div>
      </header>
      <div className={tileStyles.threadBinding}>
        <span className={tileStyles.threadChip}>{tile.statusLabel}</span>
        <span className={tileStyles.threadChip}>电脑：{tile.computerLabel}</span>
        <span className={tileStyles.threadChip}>接单：{tile.computerState}</span>
        <span className={tileStyles.threadChip}>协助 NPC：{effectiveBoundNpcLabel || "未绑定"}</span>
        <button type="button" className={`${tileStyles.threadChip} ${styles.chipButton}`} onClick={() => setSettingsOpen((value) => !value)}>
          设置
        </button>
      </div>
      <nav className={tileStyles.panelTabs} aria-label={`${tile.name} 调试窗口功能`}>
        {[
          ["terminal", "终端"],
          ["dataset", "数据标注"],
          ["chart", "图表实验"],
        ].map(([tab, label]) => {
          const count =
            tab === "terminal"
              ? terminalEventLines(tile, terminalMessages).length
              : tab === "dataset"
                ? segments.length + datasetEvents.length
                : segments.length + chartEvents.length;
          return (
            <button
              key={tab}
              type="button"
              className={tileStyles.panelTab}
              data-active={activeTab === tab ? "1" : "0"}
              onClick={() => setActiveTab(tab as TileTab)}
            >
              <span>{label}</span>
              <strong>{count}</strong>
            </button>
          );
        })}
      </nav>
      <section className={styles.runnerGate} data-tone={tile.runnerTone}>
        <strong>{tile.runnerCanDispatch ? "可立即提交" : tile.runnerCanQueue ? "可排队，等电脑恢复" : "先重连执行电脑"}</strong>
        <span>{tile.runnerHint}</span>
        {!tile.runnerCanDispatch ? <em>保持目标电脑接单窗口在线后自动恢复</em> : null}
      </section>
      {settingsOpen ? (
        <form action={更新机器人调试窗口.bind(null, projectId)} className={styles.settingsPanel} aria-label={`${tile.name} 设置`}>
          <input type="hidden" name="return_to" value={returnTo} />
          <input type="hidden" name="resource_id" value={tile.id} />
          <input type="hidden" name="window_type" value={tile.kind} />
          <strong>窗口设置</strong>
          <div>
            <span>执行电脑</span>
            <b>{tile.computerLabel} · {tile.computerState}</b>
          </div>
          <div>
            <span>调试接口</span>
            <b>{tile.name}</b>
          </div>
          <label>
            <span>窗口名</span>
            <input name="window_name" defaultValue={tile.name} />
          </label>
          <label>
            <span>协助 NPC</span>
            <input type="hidden" name="bound_npc" value={boundNpcId} />
            <select value={boundNpcId} onChange={(event) => setBoundNpcId(event.target.value)}>
              <option value="">未绑定</option>
              {npcSeats.map((seat, index) => {
                const name = seatName(seat, `NPC ${index + 1}`);
                return <option key={seatId(seat, name)} value={seatId(seat, name)}>{name}</option>;
              })}
            </select>
          </label>
          <label>
            <span>波特率</span>
            <select name="baud_rate" defaultValue={baudRate} aria-label="设置波特率">
              {["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600", "1000000", "2000000"].map((rate) => (
                <option key={rate} value={rate}>{rate}</option>
              ))}
            </select>
          </label>
          <label>
            <span>采样频率</span>
            <input name="sample_hz" defaultValue={sampleHz} inputMode="numeric" />
          </label>
          <label>
            <span>采集通道</span>
            <input name="channels" defaultValue={channels} />
          </label>
          <button type="submit">保存设置</button>
          <p>{tile.runnerHint}</p>
        </form>
      ) : null}
      {activeTab === "terminal" ? (
        <>
          <section className={styles.terminalPane} aria-label={`${tile.name} 终端`}>
            {terminalLines(tile, boundNpcLabel).map((line) => <code key={line}>{line}</code>)}
            <code className={styles.terminalDivider}>--- I/O ---</code>
            {terminalEventLines(tile, terminalMessages).map((line, index) => <code key={`${tile.id}-event-${index}`}>{line}</code>)}
            <code className={styles.terminalCursor}>$ _</code>
          </section>
          <form action={下发机器人调试命令.bind(null, projectId)} className={styles.terminalCommandBar}>
            <input type="hidden" name="return_to" value={returnTo} />
            <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
            <input type="hidden" name="interface_id" value={tile.id} />
            <input type="hidden" name="runner_interface_id" value={tile.runnerInterfaceId || tile.id} />
            <input type="hidden" name="interface_name" value={tile.name} />
            <input type="hidden" name="interface_kind" value={tile.kindLabel} />
            <span>$</span>
            <input name="command" placeholder="用户终端：自己输入直接执行；NPC 代操作才待审" />
            <select name="bound_npc" aria-label="绑定 NPC" value={boundNpcId} onChange={(event) => setBoundNpcId(event.target.value)}>
              <option value="">不绑定 NPC</option>
              {npcSeats.map((seat, index) => {
                const name = seatName(seat, `NPC ${index + 1}`);
                return <option key={seatId(seat, name)} value={seatId(seat, name)}>{name}</option>;
              })}
            </select>
            <input type="hidden" name="bound_npc_label" value={effectiveBoundNpcLabel} />
            <button type="submit" disabled={!tile.runnerReady} title={submitTitle(tile)}>
              {submitLabel(tile)}
            </button>
          </form>
          <form action={记录机器人采集片段.bind(null, projectId)} className={styles.captureBar}>
            <input type="hidden" name="return_to" value={returnTo} />
            <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
            <input type="hidden" name="interface_id" value={tile.id} />
            <input type="hidden" name="runner_interface_id" value={tile.runnerInterfaceId || tile.id} />
            <input type="hidden" name="interface_name" value={tile.name} />
            <input type="hidden" name="interface_kind" value={tile.kindLabel} />
            <input type="hidden" name="bound_npc" value={effectiveBoundNpcId} />
            <input type="hidden" name="bound_npc_label" value={effectiveBoundNpcLabel} />
            <label>
              <span>采样频率</span>
              <input name="sample_hz" defaultValue={sampleHz} inputMode="numeric" />
            </label>
            <label>
              <span>波特率</span>
              <select name="baud_rate" defaultValue={baudRate} aria-label="波特率">
                {["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600", "1000000", "2000000"].map((rate) => (
                  <option key={rate} value={rate}>{rate}</option>
                ))}
              </select>
            </label>
            <label>
              <span>通道</span>
              <input name="channels" defaultValue={channels} />
            </label>
            <button type="submit" name="capture_mode" value="start" disabled={!tile.runnerReady}>开始采集</button>
            <button type="submit" name="capture_mode" value="stop" disabled={!tile.runnerReady}>停止并生成片段</button>
          </form>
          <form action={创建机器人调试Npc操作审核.bind(null, projectId)} className={styles.npcReviewBar}>
            <input type="hidden" name="return_to" value={returnTo} />
            <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
            <input type="hidden" name="interface_id" value={tile.id} />
            <input type="hidden" name="runner_interface_id" value={tile.runnerInterfaceId || tile.id} />
            <input type="hidden" name="interface_name" value={tile.name} />
            <input type="hidden" name="interface_kind" value={tile.kindLabel} />
            <input type="hidden" name="bound_npc" value={effectiveBoundNpcId} />
            <input type="hidden" name="bound_npc_label" value={effectiveBoundNpcLabel} />
            <span>NPC 代操作待审</span>
            <input name="command" placeholder="只有 NPC/AI 想替你操作时才填这里，例如 send 123#0102" />
            <button type="submit" disabled={!tile.runnerReady || !effectiveBoundNpcId} title={effectiveBoundNpcId ? submitTitle(tile) : "先选择负责这个调试窗口的 NPC"}>
              {tile.runnerReady ? "提交审核" : "需重连"}
            </button>
          </form>
        </>
      ) : activeTab === "dataset" ? (
        <section className={styles.dataWorkbenchPane} aria-label={`${tile.name} 数据标注`}>
          <article className={`${styles.dataActionPanel} ${styles.dataFocusPanel}`}>
            <span>采集片段</span>
            <strong>{segments.length ? `${segments.length} 个可标注片段` : `${tile.kindLabel} / ${tile.computerLabel}`}</strong>
            {segments.length ? (
              <ul className={styles.segmentList}>
                {segments.slice(0, 6).map((segment) => (
                  <li key={segment.id}>
                    <b>{segment.title}</b>
                    <small>{segment.sampleHz}Hz · {segment.channels.slice(0, 4).join(" / ")}</small>
                    {captureResultLine(segment) ? <small>{captureResultLine(segment)}</small> : null}
                    {captureTrainingRowLine(segment, variables) ? <small>{captureTrainingRowLine(segment, variables)}</small> : null}
                    {segment.artifactPath ? <ArtifactPathActions projectId={projectId} artifactPath={segment.artifactPath} label="下载片段" /> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p>从终端开始/停止采集后，片段会按时间段出现在这里。标注动作在右侧抽屉里选择片段和变量。</p>
            )}
            <span>可用变量</span>
            <div className={styles.variablePills}>
              {variables.map((variable) => <span key={variable}>{variable}</span>)}
            </div>
          </article>
          <aside className={styles.dataDrawerRail} aria-label="数据标注操作抽屉">
            <details className={styles.workbenchDrawer} open>
              <summary>
                <span>NPC 预标注</span>
                <strong>{effectiveBoundNpcLabel || "选择 NPC 后可用"}</strong>
              </summary>
              <form action={创建机器人数据预标注请求.bind(null, projectId)} className={styles.dataActionPanel}>
                <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={effectiveBoundNpcId} boundNpcLabel={effectiveBoundNpcLabel} />
                <span>选择片段</span>
                {segments.length ? segments.slice(0, 6).map((segment) => (
                  <label key={segment.id} className={styles.checkLine}>
                    <input type="checkbox" name="capture_ids" value={segment.id} defaultChecked />
                    <span>{segment.title}</span>
                    <input type="hidden" name="capture_titles" value={segment.title} />
                  </label>
                )) : <p>还没有可预标注的采集片段。</p>}
                <span>选择变量</span>
                <div className={styles.variableGrid}>
                  {variables.map((variable, index) => (
                    <label key={variable} className={styles.checkLine}>
                      <input type="checkbox" name="variables" value={variable} defaultChecked={index < 4} />
                      <span>{variable}</span>
                    </label>
                  ))}
                </div>
                <label className={styles.fieldStack}>
                  <span>标注规则</span>
                  <input name="label_schema" placeholder="用户自定义标签，例如：状态A / 状态B / 异常 / 需复核" />
                </label>
                <label className={styles.fieldStack}>
                  <span>标注目标</span>
                  <textarea name="label_goal" rows={3} placeholder="例如：找出任意变量的异常区间、状态切换、缺失样本或需要人工复核的时间段" />
                </label>
                <button type="submit" disabled={!segments.length || !effectiveBoundNpcId}>生成预标注建议</button>
              </form>
            </details>
            <details className={styles.workbenchDrawer}>
              <summary>
                <span>人工确认与导出</span>
                <strong>CSV / JSONL / 清单</strong>
              </summary>
              <form action={导出机器人标注数据.bind(null, projectId)} className={styles.dataActionPanel}>
                <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={effectiveBoundNpcId} boundNpcLabel={effectiveBoundNpcLabel} />
                {segments.slice(0, 6).map((segment) => (
                  <input key={segment.id} type="hidden" name="capture_ids" value={segment.id} />
                ))}
                <span>导出变量</span>
                <div className={styles.variableGrid}>
                  {variables.map((variable, index) => (
                    <label key={variable} className={styles.checkLine}>
                      <input type="checkbox" name="variables" value={variable} defaultChecked={index < 4} />
                      <span>{variable}</span>
                    </label>
                  ))}
                </div>
                <label className={styles.fieldStack}>
                  <span>确认标签</span>
                  <input name="label_schema" placeholder="用户确认后的标签体系或版本名" />
                </label>
                <label className={styles.fieldStack}>
                  <span>人工备注</span>
                  <textarea name="label_notes" rows={3} placeholder="确认、修正或补充 NPC 预标注结果" />
                </label>
                <label className={styles.fieldStack}>
                  <span>人工标签</span>
                  <textarea
                    name="manual_labels"
                    rows={5}
                    placeholder="每行一条：片段,变量,开始,结束,标签,备注。例如 capture-1,signal.value,1.2,2.4,异常,启动段"
                  />
                </label>
                {segments.some((segment) => captureTrainingRowLine(segment, variables)) ? (
                  <p>{segments.map((segment) => captureTrainingRowLine(segment, variables)).filter(Boolean).slice(0, 2).join("；")}</p>
                ) : null}
                <label className={styles.fieldStack}>
                  <span>导出格式</span>
                  <select name="export_format" defaultValue="jsonl" aria-label="导出格式">
                    <option value="csv">CSV</option>
                    <option value="jsonl">JSONL</option>
                    <option value="parquet">Parquet 清单</option>
                    <option value="npz">NPZ 清单</option>
                    <option value="manifest">项目清单</option>
                  </select>
                </label>
                <button type="submit" disabled={!segments.length}>导出标注数据</button>
              </form>
            </details>
            <details className={styles.workbenchDrawer}>
              <summary>
                <span>标注证据</span>
                <strong>{datasetEvents.length ? `${datasetEvents.length} 条记录` : "等待记录"}</strong>
              </summary>
              <article className={styles.dataActionPanel}>
                {datasetEvents.length ? (
                  <ul className={styles.eventList}>
                    {datasetEvents.map((event) => (
                      <li key={text(event.id, text(event.title, "event"))}>
                        <b>{text(event.title, "数据事件")}</b>
                        <small>{text(event.status, "open")}</small>
                        {text(record(event.extra_data ?? event.metadata).artifact_path, "") ? (
                          <ArtifactPathActions projectId={projectId} artifactPath={text(record(event.extra_data ?? event.metadata).artifact_path, "")} label="下载数据" />
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>NPC 预标注只生成建议；用户确认后再导出训练数据集，证据留在当前调试窗口。</p>
                )}
              </article>
            </details>
          </aside>
        </section>
      ) : (
        <section className={styles.dataWorkbenchPane} aria-label={`${tile.name} 图表实验`}>
          <article className={`${styles.dataActionPanel} ${styles.dataFocusPanel}`}>
            <span>图表证据</span>
            <strong>{chartEvents.length ? `${chartEvents.length} 条实验记录` : "等待图表快照或分析建议"}</strong>
            {segments.length ? (
              <div className={styles.waveformStack}>
                {segments.slice(0, 3).map((segment) => (
                  <ChartPreview key={`${segment.id}-preview`} segment={segment} targetValue={chartTargetValue} />
                ))}
              </div>
            ) : null}
            {segments.some((segment) => captureResultLine(segment)) ? (
              <ul className={styles.eventList}>
                {segments.filter((segment) => captureResultLine(segment)).slice(0, 3).map((segment) => (
                  <li key={`${segment.id}-runner-result`}>
                    <b>{segment.title}</b>
                    <small>{captureResultLine(segment)}</small>
                    {captureSummaryLine(segment) ? <small>{captureSummaryLine(segment)}</small> : null}
                  </li>
                ))}
              </ul>
            ) : null}
            {chartEvents.length ? (
              <ul className={styles.eventList}>
                {chartEvents.map((event) => (
                  <li key={text(event.id, text(event.title, "event"))}>
                    <b>{text(event.title, "图表事件")}</b>
                    <small>{text(event.status, "open")}</small>
                    {text(record(event.extra_data ?? event.metadata).artifact_path, "") ? (
                      <ArtifactPathActions projectId={projectId} artifactPath={text(record(event.extra_data ?? event.metadata).artifact_path, "")} label="下载证据" />
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p>NPC 可以基于用户选定的曲线、目标值和现象给分析建议；涉及真实设备写入时仍回到终端待审。</p>
            )}
          </article>
          <aside className={styles.dataDrawerRail} aria-label="图表实验操作抽屉">
            <details className={styles.workbenchDrawer} open>
              <summary>
                <span>坐标与快照</span>
                <strong>{segments.length ? `${segments.length} 个片段` : "等待采集"}</strong>
              </summary>
              <form action={创建机器人图表实验.bind(null, projectId)} className={styles.dataActionPanel}>
                <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={effectiveBoundNpcId} boundNpcLabel={effectiveBoundNpcLabel} />
                <span>选择片段</span>
                {segments.slice(0, 6).map((segment) => (
                  <label key={segment.id} className={styles.checkLine}>
                    <input type="checkbox" name="capture_ids" value={segment.id} defaultChecked />
                    <span>{segment.title}</span>
                  </label>
                ))}
                <label className={styles.fieldStack}>
                  <span>横轴变量</span>
                  <select name="x_axis" defaultValue={variables.includes("time") ? "time" : variables[0]} aria-label="横轴变量">
                    {variables.map((variable) => <option key={variable} value={variable}>{variable}</option>)}
                  </select>
                </label>
                <span>纵轴变量</span>
                <div className={styles.variableGrid}>
                  {variables.filter((item) => item !== "time").map((variable, index) => (
                    <label key={variable} className={styles.checkLine}>
                      <input type="checkbox" name="y_axes" value={variable} defaultChecked={index < 2} />
                      <span>{variable}</span>
                    </label>
                  ))}
                </div>
                <label className={styles.fieldStack}>
                  <span>水平目标值</span>
                  <input name="target_value" placeholder="例如 目标值 / 阈值 / 状态线 / 参考区间" value={chartTargetValue} onChange={(event) => setChartTargetValue(event.target.value)} />
                </label>
                <label className={styles.fieldStack}>
                  <span>实验类型</span>
                  <select name="chart_mode" defaultValue="sensor" aria-label="实验类型">
                    <option value="sensor">通用时序</option>
                    <option value="bus">总线数据</option>
                    <option value="pid">PID 调试</option>
                    <option value="foc">FOC 调试</option>
                  </select>
                </label>
                <button type="submit" disabled={!segments.length}>保存图表快照</button>
              </form>
            </details>
            <details className={styles.workbenchDrawer}>
              <summary>
                <span>NPC 分析建议</span>
                <strong>{effectiveBoundNpcLabel || "选择 NPC 后可用"}</strong>
              </summary>
              <form action={创建机器人调参建议请求.bind(null, projectId)} className={styles.dataActionPanel}>
                <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={effectiveBoundNpcId} boundNpcLabel={effectiveBoundNpcLabel} />
                {segments.slice(0, 6).map((segment) => (
                  <input key={segment.id} type="hidden" name="capture_ids" value={segment.id} />
                ))}
                <label className={styles.fieldStack}>
                  <span>横轴变量</span>
                  <select name="x_axis" defaultValue={variables.includes("time") ? "time" : variables[0]} aria-label="调参横轴">
                    {variables.map((variable) => <option key={variable} value={variable}>{variable}</option>)}
                  </select>
                </label>
                <span>关注曲线</span>
                <div className={styles.variableGrid}>
                  {variables.filter((item) => item !== "time").map((variable, index) => (
                    <label key={variable} className={styles.checkLine}>
                      <input type="checkbox" name="y_axes" value={variable} defaultChecked={index < 3} />
                      <span>{variable}</span>
                    </label>
                  ))}
                </div>
                <label className={styles.fieldStack}>
                  <span>目标值或区间</span>
                  <input name="target_value" placeholder="目标值或目标区间" />
                </label>
                <label className={styles.fieldStack}>
                  <span>分析类型</span>
                  <select name="chart_mode" defaultValue="sensor" aria-label="分析类型">
                    <option value="sensor">通用时序</option>
                    <option value="bus">总线数据</option>
                    <option value="pid">PID 调试</option>
                    <option value="foc">FOC 调试</option>
                  </select>
                </label>
                <label className={styles.fieldStack}>
                  <span>现象描述</span>
                  <textarea name="symptoms" rows={3} placeholder="例如：某段数据突然跳变、周期性波动、状态切换后延迟、阈值附近反复抖动" />
                </label>
                <button type="submit" disabled={!segments.length || !effectiveBoundNpcId}>请求 NPC 分析建议</button>
              </form>
            </details>
          </aside>
        </section>
      )}
    </article>
  );
}

export function RoboticsWorkbenchClient({
  projectId,
  projectName,
  windows,
  initialSavedWindows,
  npcSeats,
  terminalMessages,
  initialOpenIds,
  initialNpcId,
  onlineComputers,
  computerCount,
  scannedCount,
  notice = "",
  error = "",
}: RoboticsWorkbenchClientProps) {
  const [defaultNpcId, setDefaultNpcId] = useState(initialNpcId);
  const [savedWindows, setSavedWindows] = useState<SavedDebugWindow[]>(initialSavedWindows);
  const router = useRouter();
  const configuredWindows = useMemo(() => configuredDebugWindows(windows, savedWindows), [windows, savedWindows]);
  const [openIds, setOpenIds] = useState<string[]>(() => initialOpenIds.filter((id) => savedWindows.some((item) => item.resourceId === id)));
  const usableWindows = useMemo(() => windows.filter((item) => item.isUsable), [windows]);
  const resourceById = useMemo(() => new Map(windows.map((item) => [item.id, item])), [windows]);
  const openWindows = useMemo(
    () => openIds.map((id) => configuredWindows.find((item) => item.id === id)).filter(Boolean) as DebugWindow[],
    [openIds, configuredWindows],
  );
  const needsLiveRefresh = terminalMessages.some((message) => {
    const type = text(message.message_type ?? message.messageType, "");
    const status = text(message.status, "");
    return type === "runner_command" && ["pending", "queued", "acked", "in_progress", "running"].includes(status);
  }) || openWindows.some((window) => window.runnerReady && window.statusLabel.includes("采集") || window.statusLabel.includes("排队"));

  useEffect(() => {
    if (!needsLiveRefresh) return;
    const timer = window.setInterval(() => {
      router.refresh();
    }, 3500);
    return () => window.clearInterval(timer);
  }, [needsLiveRefresh, router]);

  function previewCreateWindow(event: FormEvent<HTMLFormElement>) {
    const formData = new FormData(event.currentTarget);
    const resourceId = text(formData.get("resource_id"), "");
    const resource = resourceById.get(resourceId);
    if (!resource) return;
    const next: SavedDebugWindow = {
      resourceId,
      name: text(formData.get("window_name"), resource.name),
      type: text(formData.get("window_type"), resource.kind),
      baudRate: text(formData.get("baud_rate"), "115200"),
      sampleHz: text(formData.get("sample_hz"), "100"),
      channels: text(formData.get("channels"), "time,signal.value,status.code,event.count"),
      boundNpc: text(formData.get("bound_npc"), defaultNpcId),
    };
    window.setTimeout(() => {
      setSavedWindows((current) => [...current.filter((item) => item.resourceId !== resourceId), next]);
      setOpenIds((current) => current.includes(resourceId) ? current : [...current, resourceId]);
      const nextOpenIds = openIds.includes(resourceId) ? openIds : [...openIds, resourceId];
      window.history.replaceState(null, "", windowsHref(projectId, nextOpenIds, text(next.boundNpc, defaultNpcId)));
    }, 250);
  }

  function previewDeleteWindow(resourceId: string) {
    setSavedWindows((current) => current.filter((item) => item.resourceId !== resourceId));
    setOpenIds((current) => current.filter((item) => item !== resourceId));
    window.history.replaceState(null, "", windowsHref(projectId, openIds.filter((item) => item !== resourceId), defaultNpcId));
  }

  function toggleWindow(id: string) {
    setOpenIds((curr) => curr.includes(id) ? curr.filter((item) => item !== id) : [...curr, id]);
  }

  function closeWindow(id: string) {
    setOpenIds((curr) => curr.filter((item) => item !== id));
  }

  return (
    <main className={`${workbenchStyles.shell} ${styles.roboticsWorkbenchShell}`}>
      <header className={workbenchStyles.topbar}>
        <div className={workbenchStyles.topbarLeft}>
          <Link className={workbenchStyles.backLink} href={`/projects/${projectId}`}>← 主页面</Link>
          <div className={workbenchStyles.title}>
            <strong>{projectName}</strong>
            <small>{projectName} · 先创建调试窗口，再从真实扫描设备里绑定接口</small>
          </div>
        </div>
        <div className={workbenchStyles.topbarRight}>
          <span className={workbenchStyles.kpi}>执行电脑 {onlineComputers}/{computerCount}</span>
          <span className={workbenchStyles.kpi}>已扫描 {scannedCount}</span>
          <span className={workbenchStyles.kpi}>窗口 {openWindows.length}/{configuredWindows.length}</span>
        </div>
      </header>

      <div className={workbenchStyles.body}>
        <aside className={workbenchStyles.sidebar}>
          <div className={workbenchStyles.sidebarHeader}>
            <input
              type="search"
              className={workbenchStyles.search}
              placeholder="搜索调试窗口 / 电脑 / NPC"
              readOnly
              value="设备数据工作台"
            />
            <button type="button" className={workbenchStyles.batchBtn} onClick={() => setOpenIds(configuredWindows.map((window) => window.id))}>
              打开全部 ({configuredWindows.length})
            </button>
            <form action={请求串口USB扫描.bind(null, projectId)} className={styles.scanInlineForm}>
              <input type="hidden" name="return_to" value={`/projects/${projectId}/robotics`} />
              <input type="hidden" name="computer_node_id" value="all" />
              <button type="submit" disabled={!computerCount}>扫描真实接口</button>
            </form>
            <form action={创建机器人调试窗口.bind(null, projectId)} onSubmit={previewCreateWindow} className={styles.windowCreateForm}>
              <input type="hidden" name="return_to" value={`/projects/${projectId}/robotics`} />
              <strong>创建调试窗口</strong>
              <input name="window_name" placeholder="窗口名，例如 产线传感器串口" />
              <label className={styles.createFullField}>
                <span>窗口类型</span>
                <select name="window_type" defaultValue="serial" aria-label="窗口类型">
                  <option value="serial">串口</option>
                  <option value="can">CAN</option>
                  <option value="usb">USB</option>
                  <option value="spi-can">SPI-CAN</option>
                  <option value="ros">ROS</option>
                </select>
              </label>
              <label className={styles.createFullField}>
                <span>绑定真实设备</span>
                <select name="resource_id" aria-label="绑定真实设备">
                  {usableWindows.map((resource) => (
                    <option key={resource.id} value={resource.id}>{resource.name} · {resource.computerLabel}</option>
                  ))}
                </select>
              </label>
              <div className={styles.createParamGrid}>
                <label>
                  <span>波特率</span>
                  <select name="baud_rate" defaultValue="115200" aria-label="波特率">
                    {["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600", "1000000", "2000000"].map((rate) => (
                      <option key={rate} value={rate}>{rate}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>采样频率</span>
                  <input name="sample_hz" defaultValue="100" aria-label="采样频率" />
                </label>
              </div>
              <label className={styles.createFullField}>
                <span>采集通道</span>
                <input name="channels" defaultValue="time,signal.value,status.code,event.count" aria-label="采集通道" />
              </label>
              <label className={styles.createFullField}>
                <span>协助 NPC</span>
                <select name="bound_npc" aria-label="协助 NPC" defaultValue={defaultNpcId} onChange={(event) => setDefaultNpcId(event.target.value)}>
                  <option value="">不绑定 NPC</option>
                  {npcSeats.map((seat, index) => {
                    const name = seatName(seat, `NPC ${index + 1}`);
                    return <option key={seatId(seat, name)} value={seatId(seat, name)}>{name}</option>;
                  })}
                </select>
              </label>
              <button type="submit" disabled={!usableWindows.length}>创建并打开</button>
              <small>{usableWindows.length ? `${usableWindows.length} 个真实设备可绑定` : "先扫描或接入电脑后再创建窗口"}</small>
            </form>
          </div>
          <ul className={workbenchStyles.groupList}>
            <li className={workbenchStyles.group}>
              <div className={workbenchStyles.groupHeader}>
                <span>🖥 调试窗口</span>
                <small>{configuredWindows.length} 个窗口</small>
              </div>
              <ul className={workbenchStyles.npcList}>
                {configuredWindows.map((window) => {
                  const isOpen = openIds.includes(window.id);
                  return (
                    <li key={window.id} className={`${workbenchStyles.npcRow} ${isOpen ? workbenchStyles.npcRowOpen : ""}`}>
                      <div className={workbenchStyles.npcMain}>
                        <strong className={workbenchStyles.npcName}>{window.name}</strong>
                        <small className={workbenchStyles.npcMeta}>
                          <span className={window.statusLabel === "可读取" ? workbenchStyles.dotOnline : workbenchStyles.dot} />
                          {window.computerLabel} · {window.statusLabel}
                        </small>
                      </div>
                      {window.isUsable ? (
                        <span className={styles.windowRowActions}>
                          <a
                            className={workbenchStyles.openBtn}
                            href={windowsHref(projectId, isOpen ? openIds.filter((id) => id !== window.id) : [...openIds, window.id], defaultNpcId)}
                            aria-label={`${isOpen ? "关闭" : "打开"} ${window.name}`}
                            onClick={(event) => {
                              event.preventDefault();
                              toggleWindow(window.id);
                            }}
                          >
                            {isOpen ? "✕" : "+"}
                          </a>
                          <form action={删除机器人调试窗口.bind(null, projectId)} onSubmit={() => previewDeleteWindow(window.id)}>
                            <input type="hidden" name="return_to" value={`/projects/${projectId}/robotics`} />
                            <input type="hidden" name="resource_id" value={window.id} />
                            <button type="submit" aria-label={`删除 ${window.name}`}>删</button>
                          </form>
                        </span>
                      ) : (
                        <span className={styles.openBtnDisabled}>!</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </li>
          </ul>
        </aside>

        <section className={workbenchStyles.main} data-mode={openWindows.length > 0 ? "chat" : "setup"}>
          {notice ? <div className={styles.inlineNotice} data-tone="success">{notice}</div> : null}
          {error ? <div className={styles.inlineNotice} data-tone="danger">{error}</div> : null}
          {openWindows.length ? (
            <div className={workbenchStyles.tileGrid} data-tile-count={openWindows.length}>
              {openWindows.map((window) => (
                <DebugTile
                  key={window.id}
                  projectId={projectId}
                  tile={window}
                  openIds={openIds}
                  npcSeats={npcSeats}
                  terminalMessages={terminalMessages}
                  initialNpcId={defaultNpcId}
                  onClose={() => closeWindow(window.id)}
                />
              ))}
            </div>
          ) : (
            <div className={workbenchStyles.placeholder}>
              <strong>{configuredWindows.length ? "点击左栏调试窗口的 + 号打开瓷砖" : "先创建一个调试窗口"}</strong>
              <p>{configuredWindows.length ? "每个调试瓷砖都有自己的大终端、数据标注和图表实验，不会在页面之间来回跳。" : "从左栏创建窗口：命名、选择串口/CAN/USB 等类型，再绑定真实扫描设备和参数。"}</p>
              <form action={请求串口USB扫描.bind(null, projectId)} className={styles.emptyScanForm}>
                <input type="hidden" name="return_to" value={`/projects/${projectId}/robotics`} />
                <input type="hidden" name="computer_node_id" value="all" />
                <button type="submit" disabled={!computerCount}>扫描真实接口</button>
                <span>{computerCount ? "扫描结果只进入创建窗口的设备下拉，不会直接铺到左栏。" : "先在主页面接入至少一台电脑。"}</span>
              </form>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
