"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { 下发机器人调试命令, 创建机器人调试Npc操作审核 } from "../../../actions";
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
  const body = text(message.body, "");
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
    if (type === "robotics_terminal_review" || type === "robotics_terminal_npc_request") return `[npc-review:${status}] ${commandText(message)}`;
    return `[${type}:${status}] ${text(message.title ?? message.body, "终端事件")}`;
  });
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
        ].map(([tab, label]) => (
          <button
            key={tab}
            type="button"
            className={tileStyles.panelTab}
            data-active={activeTab === tab ? "1" : "0"}
            onClick={() => setActiveTab(tab as TileTab)}
          >
            <span>{label}</span>
            <strong>{tab === "terminal" ? terminalMessages.length : 0}</strong>
          </button>
        ))}
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
          <article>
            <span>采集片段</span>
            <strong>{tile.kindLabel} / {tile.computerLabel}</strong>
            <p>从这个调试窗口开始/停止采集后，片段会按时间段出现在这里，可选择一个或多个片段标注。</p>
          </article>
          <article>
            <span>变量选择</span>
            <strong>电机、传感器、总线字段</strong>
            <p>用户可自由选择一个、两个或多个变量，NPC 只能先做预标注建议，不能替用户确认。</p>
          </article>
          <article>
            <span>导出</span>
            <strong>CSV / JSONL / Parquet / NPZ</strong>
            <p>导出的可训练数据集下载到当前操作电脑，同时作为证据供图表实验复用。</p>
          </article>
        </section>
      ) : (
        <section className={styles.dataWorkbenchPane} aria-label={`${tile.name} 图表实验`}>
          <article>
            <span>横轴</span>
            <strong>时间 / 采样序号 / CAN 字段</strong>
            <p>从本窗口采集片段或标注数据集中选择横轴变量。</p>
          </article>
          <article>
            <span>纵轴</span>
            <strong>角度 / 电流 / 温度 / 力矩 / IMU</strong>
            <p>支持多曲线叠加、片段对比、异常点和标注覆盖层。</p>
          </article>
          <article>
            <span>目标值</span>
            <strong>PID / FOC 调试参考线</strong>
            <p>用户设置目标值、上下限和振荡阈值，NPC 给出调参建议但不直接改硬件。</p>
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
