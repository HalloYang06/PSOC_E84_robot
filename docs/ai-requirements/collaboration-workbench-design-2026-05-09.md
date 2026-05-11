# 协同工作台设计稿 - 2026-05-09

## 1. 产品定位

协同工作台不是平台主页面，也不是普通聊天页。它是项目里的一个核心工作页面，负责承载多人、多 NPC、多电脑、多线程的实时协同执行。

平台整体结构保持：

```text
项目 -> 工位 -> NPC -> 线程
公司 -> 部门 -> 员工 -> 工具/终端
```

但项目成员不只有一个人。平台必须同时支持：

- 单人项目：一个人接入多台电脑和多个 NPC。
- 多人项目：多个人类成员各自接入电脑、线程和 NPC，共同服务同一个项目。
- 混合协作：人和人、人和 NPC、NPC 和 NPC、不同成员电脑上的 NPC 之间协作。

## 2. 开源 multi-agent 项目的可借鉴点

本平台不应直接照搬 AutoGen、CrewAI、LangGraph 或 OpenHands，而是吸收它们的成熟协作模式。

- AutoGen：强调多 agent 对话和 human-in-the-loop。适合参考“人可以插入、agent 可以互相对话”的消息流。
- CrewAI：强调 crew、agent、task、process。适合参考“一个工位就是一个 crew，工位长负责协调，NPC 是专职员工”。
- LangGraph：强调 supervisor、handoff、状态图和可控流程。适合参考“工位长 / 项目负责人 / 审核节点 / 跨工位转交”的流程控制。
- OpenHands：强调真实软件开发 agent 能操作代码、命令行、浏览器并回传结果。适合参考 Claude Code / Codex 线程执行层的工具调用和结果回传。

参考资料：

- AutoGen multi-agent conversation: https://autogenhub.github.io/autogen/docs/Use-Cases/agent_chat/
- AutoGen human-in-the-loop: https://autogenhub.github.io/autogen/docs/tutorial/human-in-the-loop/
- CrewAI crews: https://docs.crewai.com/concepts/crews
- CrewAI processes: https://docs.crewai.com/concepts/processes
- OpenHands: https://github.com/OpenHands/OpenHands

## 3. 协同工作台的用户视角

用户进入协同工作台时，首先应该看懂三件事：

1. 当前项目有哪些工位，每个工位有哪些人和 NPC。
2. 哪些 NPC 背后有真实 Claude Code / Codex 线程在线。
3. 当前需求正在谁手里、谁在等谁、哪里需要人审。

工作台不应只展示“卡片很多”。它要把协作过程组织成可追踪的流水线。

## 4. 页面布局建议

### 左侧：项目组织树

按工位分组：

```text
主控执行节点 工位
  - 人：张三 / owner / 在线
  - NPC：前端工位 / Claude Code / 电脑 A / 在线
  - NPC：后端工位 / Codex / 电脑 B / 忙碌

边缘执行节点 工位
  - 人：李四 / member / 离线
  - NPC：执行工位 / Codex / 电脑 C / 离线
```

每个节点至少显示：

- 名字
- 类型：人类成员 / NPC
- 工位角色：工位长 / 成员
- 绑定电脑
- 线程类型：Claude Code / Codex / 其他 / 未绑定
- 线程状态：在线 / 离线 / 忙碌 / 阻塞 / 待绑定

### 中间：协作时间线

这是工作台的主工作区域。它不应该只是每个 NPC 一条孤立聊天记录，而应该统一显示：

- 人发起需求
- NPC 接收需求
- NPC 派给同工位伙伴
- NPC 转交跨工位工位长
- 线程开始执行
- 线程回传进度
- NPC 发送回执
- 人工审核通过 / 打回
- 最终汇总回复

推荐按“协作事件”展示，而不是按原始日志展示。

事件类型：

```text
human_message
agent_message
requirement_dispatch
agent_ack
agent_progress
agent_done
agent_reject
handoff
human_review_request
human_review_approved
human_review_rejected
thread_command
thread_result
thread_error
```

### 右侧：当前执行上下文

当选中某个需求、NPC 或线程时，右侧显示：

- 当前需求目标
- 当前负责人
- 上游是谁
- 下游是谁
- 当前线程在哪里执行
- 工作目录
- Git 分支
- 最新心跳
- 最近错误
- 可以执行的人类操作：接手、通过审核、打回、重新派发、转交

## 5. 核心协作闭环

### 5.1 人派给 NPC

人输入：

```text
请前端工位修复工作台里 NPC 消息流不清楚的问题。
```

系统创建：

```text
requirement
sender_type = human
target_type = thread_workstation
target_id = 前端工位 NPC
```

NPC 对应线程收到任务后必须先回：

```text
agent_ack
```

然后根据情况回：

```text
agent_progress
agent_done
agent_reject
```

### 5.2 NPC 找同工位 NPC

同一个工位下 NPC 互相认识。NPC A 判断需要 NPC B 协助时：

```text
NPC A -> NPC B: requirement_dispatch
```

同工位默认免审，但必须留痕：

```text
source = same_workstation_auto_route
review_policy = skip
```

NPC B 完成后回给 NPC A：

```text
agent_done
recipient = NPC A
parent_requirement_id = 原需求
```

NPC A 再汇总给人。

### 5.3 NPC 跨工位协作

跨工位不能默认直派。流程应为：

```text
NPC A -> 目标工位长 -> 人审/工位长确认 -> NPC B
```

如果项目策略允许自动化，可以由工位长策略决定是否免审。

跨工位事件必须显示：

- 来源工位
- 目标工位
- 转交原因
- 审核策略
- 当前卡点

### 5.4 多人协作

人类成员也要成为协作图中的一等角色。

多人场景包括：

- A 成员把任务派给 B 成员电脑上的 NPC。
- A 成员电脑上的 NPC 请求 B 成员工位协助。
- B 成员可以在工作台中人工接手某个 NPC 的未完成任务。
- 项目 owner 或工位负责人可以审核跨工位高风险动作。

成员权限建议：

```text
owner: 项目总负责人，可管理成员、工位、审核策略
maintainer: 可管理工位和 NPC
member: 可派工、接手、回复、绑定自己电脑
viewer: 只读
computer_owner: 某台电脑的接入人，可管理该电脑上的线程
workstation_lead: 工位长，可处理本工位跨工位转交
```

## 6. Claude Code / Codex 统一线程模型

NPC 是长期身份，线程只是执行工具。不要让 UI 只显示 provider 文案，要统一成线程绑定对象。

建议数据形状：

```json
{
  "npc_id": "seat_frontend",
  "thread_binding": {
    "provider": "claude_code",
    "thread_id": "claude-session-xxx",
    "computer_node_id": "pc_a",
    "owner_user_id": "user_1",
    "workdir": "D:/ai合作产品",
    "status": "online",
    "last_heartbeat_at": "2026-05-09T20:00:00+08:00",
    "capabilities": ["shell", "git", "browser", "mcp"]
  }
}
```

Provider 枚举：

```text
claude_code
codex
qwen
gemini
openhands
manual
```

线程状态：

```text
unbound
offline
online
busy
blocked
stale
error
```

## 7. 当前代码已经具备的基础

当前仓库里已经有这些基础，不要推倒重来：

- `workbench-client.tsx` 已按工位分组 NPC。
- `npc-tile.tsx` 已有同工位伙伴、跨工位工位长、消息流、队列、回执流。
- 后端已有 `collaboration_message`。
- 后端已有 `receipts`。
- 后端已有 `ProjectThreadWorkstation`。
- 后端已有 Claude bridge 和 runner command 相关接口。
- runner/service 已能识别 codex / claude 类型。

现在缺的是把这些能力从“功能堆叠”整理成“协同流水线”。

## 8. 下一轮实现优先级

### P0：先把工作台重新定义成协同作业面

- 页面文案从 `NPC 工作台 · 同时打开多个 NPC 的对话/状态卡` 改为 `协同工作台 · 人 / NPC / 多电脑线程协作现场`。
- 左侧分组中同时显示人类成员和 NPC。
- NPC 行显示线程 provider、电脑、状态。
- 空态说明改成“选择一个人或 NPC 查看协作流”。

### P1：把 NPC 卡片改成协同执行卡

每张卡顶部固定显示：

- NPC 名字
- 所属工位
- 线程 provider
- 电脑节点
- 电脑接入人
- 当前状态

### P2：把消息流改成协作事件流

合并展示：

- 人和 NPC 消息
- NPC 和 NPC 消息
- requirement dispatch
- receipts
- review
- handoff
- thread command / result

### P3：打通同工位 NPC 自动协作

从 UI 上让用户能看到：

```text
NPC A 派给 NPC B -> NPC B 已接 -> NPC B 完成 -> NPC A 收到回执
```

这个闭环比“能发消息”更重要。

### P4：打通 Claude Code / Codex 统一绑定显示

把当前 provider、runner、watcher、thread scan 的信息统一显示在 NPC 卡片顶部和右侧上下文里。

## 9. 设计原则

- 人类成员和 NPC 都是一等协作者。
- NPC 长期存在，线程可以替换。
- 同工位协作应该顺滑，跨工位协作必须可审计。
- 平台展示协作状态和结果，不把底层执行日志全塞给用户。
- Claude Code 和 Codex 要统一进同一套线程绑定模型。
- 所有协作必须能回溯：谁发起、谁接手、谁执行、谁回执、谁审核。
