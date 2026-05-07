# Claude / Codex 命令快捷面板（2026-05-07）

> 平台派单表单上方挂了一个折叠面板，列出 Claude Code 里**自用最高频**的几条斜杠命令，
> 一键复制到剪贴板，到自己的 CLI 终端粘贴即可。**真正执行命令的还是你本机的 Claude Code，平台只负责快捷复制。**

## 在哪里能看到

两处都挂了同一个面板：

1. **驾驶舱 → 协作池 → 派单**（2D 升级版）：派单 drawer 顶部一个折叠条 `📋 Claude / Codex 常用命令快捷复制`
2. **机房 → 给在线电脑发一条最小命令**（playable-shell 经典版）：表单顶部同款折叠条

默认收起，点击展开。

## 面板里有哪些命令

只列**用户实际自用最高频**的 3 条：

| 命令 | 做什么 | 什么时候用 | 风险 |
|---|---|---|---|
| `/compact` | 把历史摘要后释放上下文 | 上下文快满、但还想继续 | **会消耗一次 LLM 调用** |
| `/plan` | 切到 plan-only 规划模式 | 复杂任务要先对齐方案 | 安全（仅模式开关） |
| `/resume` | 恢复一个历史会话 | 接着之前的对话继续 | 安全 |

## 多电脑场景

**直接到那台电脑的浏览器打开本页面点复制就行**——剪贴板天然在那台电脑上，不用走平台转发。

为什么不做"一键发送到远端线程"？因为 `/compact /plan /resume` 这些斜杠命令是 **Claude Code 交互式 REPL 内部解析**的，
非交互模式（`claude --print`）只会把它们当成普通文本 prompt 给 AI 看。在远端 watcher 端"发过去"也跑不出预期效果。
要在哪台电脑用，就在哪台电脑的浏览器复制 → 粘贴到那台电脑的 Claude 终端。

## 哪些命令**不放面板**

下面这些命令**不放面板**，请按平台正常派单流走，或在你自己 CLI 终端里手动确认后输入：

| 命令 | 为什么不放面板 |
|---|---|
| `/clear` | 一键清掉用户上下文，事故可能性高（不可恢复） |
| `/init` | 会在仓库写一份 CLAUDE.md，**改文件** |
| `/memory` | 编辑长期记忆，**改 ~/.claude** |
| `/permissions` | 查看/编辑工具权限，**改本地 settings.json** |
| `/config` | 改 CLI 配置（主题、绑定等） |
| `/login` `/logout` | 账号操作，**敏感** |
| `/help` `/status` `/cost` `/context` | 用户实测低频，留着只增加面板长度 |
| `codex --help` `codex doctor` | 同上，低频 |
| `codex exec "<prompt>"` | 这就是平台派单本身在用的命令——应该走"先预演再正式发送"的派单流，不要用快捷面板绕过治理 |

## 面板的设计原则

- **只放安全可一键触发**的命令：只读 / 仅影响自身上下文 / 不消耗钱外的 token
- **复制 ≠ 执行**：面板只把命令送到你的剪贴板，**真正按下回车的还是你**——避免误触
- **不一键发送到线程**：技术上能做，但派单走平台已有的 preview + 治理流更安全；命令面板只解决"我要在自己 Claude Code 终端打这条命令，但忘了拼写"的场景

## 关联文件

- 组件实现：`apps/web/app/projects/[id]/_components/claude-command-palette.tsx`
- 样式：`apps/web/app/projects/[id]/_components/claude-command-palette.module.css`
- 挂载点：
  - `apps/web/app/projects/[id]/2d-upgrade/project-2d-upgrade-game.tsx`（exchange / dispatch-command 模块）
  - `apps/web/app/projects/[id]/project-playable-shell.tsx`（sendRunnerCommand 表单上方）

## 想加新命令？

编辑 `claude-command-palette.tsx` 顶部的 `CLAUDE_COMMANDS` 数组，加一条 `{ cmd, desc, when, tone }`。

- `tone: "safe"` —— 完全只读
- `tone: "info"` —— 安全但**会消耗 token / 改自身上下文**（如 `/compact`）
- `tone: "danger"` —— 不要加，应走平台派单流

加之前先回顾上面"哪些命令不放面板"那张表的判断标准——**面板的价值在于精简，不在于全**。

