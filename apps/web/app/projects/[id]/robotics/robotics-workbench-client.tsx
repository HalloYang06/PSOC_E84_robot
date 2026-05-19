"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  下发机器人调试命令,
  创建机器人图表实验,
  创建机器人数据预标注请求,
  创建机器人调参建议请求,
  创建机器人调试Npc操作审核,
  导出机器人标注数据,
  记录机器人采集片段,
} from "../../../actions";
import tileStyles from "../workbench/_components/npc-tile.module.css";
import workbenchStyles from "../workbench/workbench.module.css";
import styles from "./robotics.module.css";

type AnyRecord = Record<string, any>;

type DebugWindow = {
  id: string;
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
  readCapability: boolean;
  writeCapabilityLabel: string;
  isUsable: boolean;
};

type TileTab = "terminal" | "dataset" | "chart";

type RoboticsWorkbenchClientProps = {
  projectId: string;
  projectName: string;
  windows: DebugWindow[];
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

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function record(value: unknown): AnyRecord {
  return value && typeof value === "object" ? value as AnyRecord : {};
}

function seatId(seat: AnyRecord, fallback: string) {
  return text(seat.id ?? seat.config_id ?? seat.configId ?? seat.row_id ?? seat.name, fallback);
}

function seatName(seat: AnyRecord, fallback: string) {
  return text(seat.name ?? seat.label ?? seat.display_name, fallback);
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
    if (type === "runner_command") return `$ ${commandText(message)}  # ${status}`;
    if (type === "runner_ack") return `[ack] ${text(message.body, "执行电脑已接单")}`;
    if (type === "runner_result") return `[result:${status}] ${text(message.body, "执行电脑已返回结果")}`;
    if (type === "robotics_capture_start") return `[capture:running] ${text(message.title, "开始采集")}`;
    if (type === "robotics_capture_segment") return `[capture:ready] ${text(record(message.extra_data ?? message.metadata).artifact_path, text(message.title, "采集片段"))}`;
    if (type === "robotics_terminal_review" || type === "robotics_terminal_npc_request") return `[npc-review:${status}] ${commandText(message)}`;
    return `[${type}:${status}] ${text(message.title ?? message.body, "终端事件")}`;
  });
}

function captureSegments(tile: DebugWindow, messages: AnyRecord[]) {
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
        channels: channels.length ? channels : ["time", "motor.current", "sensor.temperature"],
        createdAt: text(message.created_at ?? message.createdAt ?? extra.stopped_at, ""),
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
    .slice(0, 6)
    .reverse();
}

function segmentVariables(segments: ReturnType<typeof captureSegments>) {
  const values = new Set<string>();
  for (const segment of segments) {
    for (const channel of segment.channels) {
      values.add(channel);
    }
  }
  if (!values.size) {
    ["time", "motor.current", "motor.velocity", "sensor.temperature", "bus.frame"].forEach((item) => values.add(item));
  }
  return Array.from(values);
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
      <input type="hidden" name="interface_name" value={tile.name} />
      <input type="hidden" name="interface_kind" value={tile.kindLabel} />
      <input type="hidden" name="bound_npc" value={boundNpcId} />
      <input type="hidden" name="bound_npc_label" value={boundNpcLabel} />
    </>
  );
}

function terminalLines(tile: DebugWindow, boundNpcLabel: string) {
  const dispatchMode = tile.runnerCanDispatch ? "可接单" : tile.runnerCanQueue ? "排队等恢复" : "暂停提交";
  const lines = [
    `$ open ${tile.name}`,
    `接口=${tile.kindLabel}  电脑=${tile.computerLabel}`,
    `状态=${tile.statusLabel}  模式=用户终端`,
    `接单=${dispatchMode}  电脑状态=${tile.computerState}`,
    `读取=${tile.readCapability ? "可用" : "不可用"}  写入=${tile.writeCapabilityLabel}`,
    `协助NPC=${boundNpcLabel || tile.boundNpc || "未绑定，创建或设置时选择 NPC"}`,
  ];
  if (tile.kind === "can") {
    lines.push("filter=none  bitrate=待确认  sample=100Hz");
    lines.push("hint: 用户在这里手动发送不需要平台审核；NPC 代发必须先待审。");
  } else if (tile.kind === "spi-can") {
    lines.push("chip=MCP251x  spi-clock=待确认  irq=待确认");
    lines.push("hint: SPI-CAN 只给配置建议，不直接改 overlay / module。");
  } else if (tile.kind === "serial") {
    lines.push("baud=115200  parity=none  stop=1");
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
  const returnTo = windowsHref(projectId, openIds, boundNpcId);
  const segments = captureSegments(tile, terminalMessages);
  const variables = segmentVariables(segments);
  const datasetEvents = tileEvents(tile, terminalMessages, ["robotics_annotation_request", "robotics_dataset_export"]);
  const chartEvents = tileEvents(tile, terminalMessages, ["robotics_chart_snapshot", "robotics_tuning_request"]);

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
        <span className={tileStyles.threadChip}>协助 NPC：{boundNpcLabel || tile.boundNpc || "未绑定"}</span>
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
          const count = tab === "terminal" ? terminalEventLines(tile, terminalMessages).length : segments.length;
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
        <section className={styles.settingsPanel} aria-label={`${tile.name} 设置`}>
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
            <span>协助 NPC</span>
            <select value={boundNpcId} onChange={(event) => setBoundNpcId(event.target.value)}>
              <option value="">未绑定</option>
              {npcSeats.map((seat, index) => {
                const name = seatName(seat, `NPC ${index + 1}`);
                return <option key={seatId(seat, name)} value={seatId(seat, name)}>{name}</option>;
              })}
            </select>
          </label>
          <p>{tile.runnerHint}</p>
        </section>
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
            <input type="hidden" name="bound_npc_label" value={boundNpcLabel} />
            <button type="submit" disabled={!tile.runnerReady} title={submitTitle(tile)}>
              {submitLabel(tile)}
            </button>
          </form>
          <form action={记录机器人采集片段.bind(null, projectId)} className={styles.captureBar}>
            <input type="hidden" name="return_to" value={returnTo} />
            <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
            <input type="hidden" name="interface_id" value={tile.id} />
            <input type="hidden" name="interface_name" value={tile.name} />
            <input type="hidden" name="interface_kind" value={tile.kindLabel} />
            <input type="hidden" name="bound_npc" value={boundNpcId} />
            <input type="hidden" name="bound_npc_label" value={boundNpcLabel} />
            <label>
              <span>采样频率</span>
              <input name="sample_hz" defaultValue="100" inputMode="numeric" />
            </label>
            <label>
              <span>通道</span>
              <input name="channels" defaultValue="time,motor.current,motor.velocity,sensor.temperature,bus.frame" />
            </label>
            <button type="submit" name="capture_mode" value="start" disabled={!tile.runnerReady}>开始采集</button>
            <button type="submit" name="capture_mode" value="stop" disabled={!tile.runnerReady}>停止并生成片段</button>
          </form>
          <form action={创建机器人调试Npc操作审核.bind(null, projectId)} className={styles.npcReviewBar}>
            <input type="hidden" name="return_to" value={returnTo} />
            <input type="hidden" name="computer_node_id" value={tile.computerNodeId} />
            <input type="hidden" name="interface_id" value={tile.id} />
            <input type="hidden" name="interface_name" value={tile.name} />
            <input type="hidden" name="interface_kind" value={tile.kindLabel} />
            <input type="hidden" name="bound_npc" value={boundNpcId} />
            <input type="hidden" name="bound_npc_label" value={boundNpcLabel} />
            <span>NPC 代操作待审</span>
            <input name="command" placeholder="只有 NPC/AI 想替你操作时才填这里，例如 send 123#0102" />
            <button type="submit" disabled={!tile.runnerReady || !boundNpcId} title={boundNpcId ? submitTitle(tile) : "先选择负责这个调试窗口的 NPC"}>
              {tile.runnerReady ? "提交审核" : "需重连"}
            </button>
          </form>
        </>
      ) : activeTab === "dataset" ? (
        <section className={styles.dataWorkbenchPane} aria-label={`${tile.name} 数据标注`}>
          <form action={创建机器人数据预标注请求.bind(null, projectId)} className={styles.dataActionPanel}>
            <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={boundNpcId} boundNpcLabel={boundNpcLabel} />
            <span>采集片段</span>
            <strong>{segments.length ? `${segments.length} 个可标注片段` : `${tile.kindLabel} / ${tile.computerLabel}`}</strong>
            {segments.length ? (
              <ul className={styles.segmentList}>
                {segments.slice(0, 4).map((segment) => (
                  <li key={segment.id}>
                    <label className={styles.checkLine}>
                      <input type="checkbox" name="capture_ids" value={segment.id} defaultChecked />
                      <b>{segment.title}</b>
                    </label>
                    <input type="hidden" name="capture_titles" value={segment.title} />
                    <small>{segment.sampleHz}Hz · {segment.channels.slice(0, 3).join(" / ")}</small>
                    {segment.artifactPath ? <code>{segment.artifactPath}</code> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p>从这个调试窗口开始/停止采集后，片段会按时间段出现在这里，可选择一个或多个片段标注。</p>
            )}
            <span>预标注变量</span>
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
              <input name="label_schema" defaultValue="正常 / 过冲 / 振荡 / 缺失 / 异常" />
            </label>
            <label className={styles.fieldStack}>
              <span>标注目标</span>
              <textarea name="label_goal" rows={3} placeholder="例如：找出电机电流突增和温度异常片段，先让 NPC 给预标注建议" />
            </label>
            <button type="submit" disabled={!segments.length || !boundNpcId}>NPC 预标注</button>
          </form>
          <form action={导出机器人标注数据.bind(null, projectId)} className={styles.dataActionPanel}>
            <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={boundNpcId} boundNpcLabel={boundNpcLabel} />
            <span>变量选择</span>
            <strong>自由选择一个或多个变量</strong>
            {segments.slice(0, 4).map((segment) => (
              <input key={segment.id} type="hidden" name="capture_ids" value={segment.id} />
            ))}
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
              <input name="label_schema" defaultValue="human_confirmed" />
            </label>
            <label className={styles.fieldStack}>
              <span>人工备注</span>
              <textarea name="label_notes" rows={3} placeholder="确认、修正或补充 NPC 预标注结果" />
            </label>
            <span>导出</span>
            <select name="export_format" defaultValue="jsonl" aria-label="导出格式">
              <option value="csv">CSV</option>
              <option value="jsonl">JSONL</option>
              <option value="parquet">Parquet 清单</option>
              <option value="npz">NPZ 清单</option>
              <option value="manifest">项目清单</option>
            </select>
            <button type="submit" disabled={!segments.length}>导出标注数据</button>
          </form>
          <article className={styles.dataActionPanel}>
            <span>标注证据</span>
            <strong>{datasetEvents.length ? `${datasetEvents.length} 条闭环记录` : "等待预标注或导出"}</strong>
            {datasetEvents.length ? (
              <ul className={styles.eventList}>
                {datasetEvents.map((event) => (
                  <li key={text(event.id, text(event.title, "event"))}>
                    <b>{text(event.title, "数据事件")}</b>
                    <small>{text(event.status, "open")}</small>
                    {text(record(event.extra_data ?? event.metadata).artifact_path, "") ? <code>{text(record(event.extra_data ?? event.metadata).artifact_path, "")}</code> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p>NPC 预标注只生成建议；用户确认后再导出训练数据集，证据留在当前调试窗口。</p>
            )}
          </article>
        </section>
      ) : (
        <section className={styles.dataWorkbenchPane} aria-label={`${tile.name} 图表实验`}>
          <form action={创建机器人图表实验.bind(null, projectId)} className={styles.dataActionPanel}>
            <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={boundNpcId} boundNpcLabel={boundNpcLabel} />
            <span>横轴</span>
            <strong>{segments.length ? `${segments.length} 个片段可画图` : "等待本窗口采集片段"}</strong>
            {segments.slice(0, 4).map((segment) => (
              <label key={segment.id} className={styles.checkLine}>
                <input type="checkbox" name="capture_ids" value={segment.id} defaultChecked />
                <span>{segment.title}</span>
              </label>
            ))}
            <select name="x_axis" defaultValue={variables.includes("time") ? "time" : variables[0]} aria-label="横轴变量">
              {variables.map((variable) => <option key={variable} value={variable}>{variable}</option>)}
            </select>
            <span>纵轴</span>
            <div className={styles.variableGrid}>
              {variables.filter((item) => item !== "time").map((variable, index) => (
                <label key={variable} className={styles.checkLine}>
                  <input type="checkbox" name="y_axes" value={variable} defaultChecked={index < 2} />
                  <span>{variable}</span>
                </label>
              ))}
            </div>
            <span>目标值</span>
            <input name="target_value" placeholder="例如 1500 rpm / 0.8 A / 45 deg" />
            <select name="chart_mode" defaultValue="pid" aria-label="实验类型">
              <option value="pid">PID</option>
              <option value="foc">FOC</option>
              <option value="sensor">传感器</option>
              <option value="bus">总线</option>
            </select>
            <button type="submit" disabled={!segments.length}>保存图表快照</button>
          </form>
          <form action={创建机器人调参建议请求.bind(null, projectId)} className={styles.dataActionPanel}>
            <HiddenTileFields tile={tile} returnTo={returnTo} boundNpcId={boundNpcId} boundNpcLabel={boundNpcLabel} />
            <span>NPC 调参</span>
            <strong>PID / FOC 调试参考线</strong>
            {segments.slice(0, 4).map((segment) => (
              <input key={segment.id} type="hidden" name="capture_ids" value={segment.id} />
            ))}
            <select name="x_axis" defaultValue={variables.includes("time") ? "time" : variables[0]} aria-label="调参横轴">
              {variables.map((variable) => <option key={variable} value={variable}>{variable}</option>)}
            </select>
            <div className={styles.variableGrid}>
              {variables.filter((item) => item !== "time").map((variable, index) => (
                <label key={variable} className={styles.checkLine}>
                  <input type="checkbox" name="y_axes" value={variable} defaultChecked={index < 3} />
                  <span>{variable}</span>
                </label>
              ))}
            </div>
            <input name="target_value" placeholder="目标值或目标区间" />
            <select name="chart_mode" defaultValue="pid" aria-label="调参类型">
              <option value="pid">PID</option>
              <option value="foc">FOC</option>
              <option value="sensor">传感器</option>
              <option value="bus">总线</option>
            </select>
            <textarea name="symptoms" rows={3} placeholder="例如：启动过冲明显，稳态误差大，电流波形有高频抖动" />
            <button type="submit" disabled={!segments.length || !boundNpcId}>请求 NPC 调参建议</button>
          </form>
          <article className={styles.dataActionPanel}>
            <span>图表证据</span>
            <strong>{chartEvents.length ? `${chartEvents.length} 条实验记录` : "等待图表快照或调参建议"}</strong>
            {chartEvents.length ? (
              <ul className={styles.eventList}>
                {chartEvents.map((event) => (
                  <li key={text(event.id, text(event.title, "event"))}>
                    <b>{text(event.title, "图表事件")}</b>
                    <small>{text(event.status, "open")}</small>
                    {text(record(event.extra_data ?? event.metadata).artifact_path, "") ? <code>{text(record(event.extra_data ?? event.metadata).artifact_path, "")}</code> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p>NPC 可以基于用户选定的曲线、目标值和现象给建议；写入真实硬件参数仍回到终端待审。</p>
            )}
          </article>
        </section>
      )}
    </article>
  );
}

export function RoboticsWorkbenchClient({
  projectId,
  projectName,
  windows,
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
  const [openIds, setOpenIds] = useState<string[]>(initialOpenIds);
  const [defaultNpcId, setDefaultNpcId] = useState(initialNpcId);
  const usableWindows = useMemo(() => windows.filter((item) => item.isUsable), [windows]);
  const openWindows = useMemo(
    () => openIds.map((id) => windows.find((item) => item.id === id)).filter(Boolean) as DebugWindow[],
    [openIds, windows],
  );

  function openWindow(id: string) {
    setOpenIds((curr) => curr.includes(id) ? curr : [...curr, id]);
  }

  function toggleWindow(id: string) {
    setOpenIds((curr) => curr.includes(id) ? curr.filter((item) => item !== id) : [...curr, id]);
  }

  function closeWindow(id: string) {
    setOpenIds((curr) => curr.filter((item) => item !== id));
  }

  return (
    <main className={workbenchStyles.shell}>
      <header className={workbenchStyles.topbar}>
        <div className={workbenchStyles.topbarLeft}>
          <Link className={workbenchStyles.backLink} href={`/projects/${projectId}`}>← 主页面</Link>
          <div className={workbenchStyles.title}>
            <strong>{projectName}</strong>
            <small>{projectName} · 只显示本项目电脑扫描到的真实接口，不建假窗口</small>
          </div>
        </div>
        <div className={workbenchStyles.topbarRight}>
          <span className={workbenchStyles.kpi}>执行电脑 {onlineComputers}/{computerCount}</span>
          <span className={workbenchStyles.kpi}>已扫描 {scannedCount}</span>
          <span className={workbenchStyles.kpi}>窗口 {openWindows.length}/{windows.length}</span>
        </div>
      </header>

      <div className={workbenchStyles.body}>
        <aside className={workbenchStyles.sidebar}>
          <div className={workbenchStyles.sidebarHeader}>
            <input
              type="search"
              className={workbenchStyles.search}
              placeholder="搜索真实接口 / 电脑 / NPC"
              readOnly
              value="设备数据工作台"
            />
            <button type="button" className={workbenchStyles.batchBtn} onClick={() => setOpenIds(usableWindows.map((window) => window.id))}>
              打开全部 ({usableWindows.length})
            </button>
          </div>
          <ul className={workbenchStyles.groupList}>
            <li className={workbenchStyles.group}>
              <div className={workbenchStyles.groupHeader}>
                <span>🖥 真实接口索引</span>
                <small>{windows.length} 个接口</small>
              </div>
              <ul className={workbenchStyles.npcList}>
                {windows.map((window) => {
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
              <strong>{windows.length ? "点击左栏真实接口的 + 号打开调试瓷砖" : "等待本项目电脑扫描接口"}</strong>
              <p>{windows.length ? "每个调试瓷砖都有自己的终端、数据标注和图表实验，不会在页面之间来回跳。" : "请先在主页面接入电脑，并执行接口扫描。平台不会创建 demo 调试窗口误导你。"}</p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
