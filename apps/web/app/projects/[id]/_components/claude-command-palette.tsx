"use client";

import { useState } from "react";
import styles from "./claude-command-palette.module.css";

type CommandTone = "safe" | "info" | "danger";

type ClaudeCommand = {
  cmd: string;
  desc: string;
  when: string;
  tone: CommandTone;
};

const CLAUDE_COMMANDS: ClaudeCommand[] = [
  { cmd: "/compact", desc: "把历史摘要后释放上下文（会消耗一次 LLM 调用）", when: "上下文快满、但还想继续这个会话时", tone: "info" },
  { cmd: "/plan", desc: "切到 plan-only 规划模式（只规划不动手）", when: "复杂任务要先对齐方案再实现时", tone: "safe" },
  { cmd: "/resume", desc: "恢复一个历史会话", when: "想接着之前的对话继续做时", tone: "safe" },
];

export function ClaudeCommandPalette({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function copy(cmd: string) {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(cmd);
      } else if (typeof document !== "undefined") {
        const ta = document.createElement("textarea");
        ta.value = cmd;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      } else {
        throw new Error("剪贴板不可用");
      }
      setCopied(cmd);
      setError(null);
      setTimeout(() => setCopied((c) => (c === cmd ? null : c)), 2400);
    } catch (e) {
      setError(`复制失败：${e instanceof Error ? e.message : "未知错误"}`);
      setTimeout(() => setError(null), 3000);
    }
  }

  return (
    <details
      className={styles.palette}
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className={styles.summary}>
        <span className={styles.summaryTitle}>📋 Claude / Codex 常用命令快捷复制</span>
        <span className={styles.summaryHint}>
          {open ? "收起" : "展开"}（共 {CLAUDE_COMMANDS.length} 条只读安全命令，复制后到自己 CLI 终端粘贴）
        </span>
      </summary>
      <div className={styles.intro}>
        <p>
          这些是<strong>你自己 Claude Code 终端里输入的自用命令</strong>，复制后到自己的 CLI 终端粘贴即可。
          多电脑场景：到那台电脑的浏览器再打开本页面点复制——剪贴板天然就在那台电脑上，不用走平台转发。
        </p>
        <p className={styles.introMore}>
          完整命令清单与放行原则见{" "}
          <a
            href="https://github.com/wenjunyong666/ai-/blob/main/docs/user-guides/CLAUDE_COMMAND_PALETTE_2026-05-07.md"
            target="_blank"
            rel="noopener noreferrer"
          >
            Claude 命令面板用户手册
          </a>
          。
        </p>
      </div>
      <ul className={styles.list}>
        {CLAUDE_COMMANDS.map((c) => (
          <li key={c.cmd} className={`${styles.item} ${styles[`tone_${c.tone}`] ?? ""}`}>
            <code className={styles.cmd}>{c.cmd}</code>
            <div className={styles.body}>
              <strong>{c.desc}</strong>
              <small>什么时候用：{c.when}</small>
            </div>
            <button
              type="button"
              className={styles.copyBtn}
              onClick={() => copy(c.cmd)}
              title={`复制 ${c.cmd} 到剪贴板`}
            >
              {copied === c.cmd ? "已复制 ✓" : "复制"}
            </button>
          </li>
        ))}
      </ul>
      {error ? <p className={styles.err}>{error}</p> : null}
    </details>
  );
}
