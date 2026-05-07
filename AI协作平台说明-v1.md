# AI 协作平台 · 第一版可用平台说明（v1）

> **一句话定位**：调度多电脑、多 NPC、多 AI 引擎（Claude Code / Codex CLI）协作做软件项目的平台。AI 不是被锁在云上，而是跑在你（和你队友）的本地终端里，平台只做协调器。

---

## 一、平台是什么、解决什么

| 角色 | 在平台里是什么 | 类比 |
|---|---|---|
| **项目** | 一个 GitHub 仓库 + 一组协作配置 | 公司里的"产品"或"项目" |
| **工位** | 一台物理电脑（绑定 computer_node） | 部门／一个工作室 |
| **NPC** | 长期员工，挂在某工位下，有职责 / 知识库 / Skill | 部门里的"前端工程师小王" |
| **线程** | 实际跑的一个 Claude Code / Codex CLI 进程 | 小王今天打开的这个终端 |

**核心解决的问题**：

1. **AI 换手成本**：换一个模型 / 换一台机器，AI 上下文全丢。平台把"知识库 + Skill + 职责"沉淀到 NPC 这一层，**线程死了 NPC 还在**，新接手的 Claude/Codex 直接读 NPC 知识库继续。
2. **多人多机协作**：同一个项目，多人在不同电脑（甚至局域网内）同时跑 AI 时怎么不踩脚？答案是 **NPC 占用锁**（同一时间只有一个用户能给一个 NPC 派单）+ **同工位互发** + **跨工位 Handoff**。
3. **AI 不可控**：纯人工兜底通道、三级审核策略（项目/工位/NPC）、协作消息池审计——任何一个 AI 的动作都能回溯。
4. **黑盒**：本机 CLI 终端要能看见平台派发了什么任务、AI 回了什么。watcher 把消息流双向打通。

---

## 二、9 项必备能力对照表

| # | 能力 | 状态 | 关键入口 |
|---|---|---|---|
| 1 | 跨电脑统一调度 | ✅ | LAN 模式 + computer_node 绑定 |
| 2 | 三层下钻驾驶舱 | ✅ | `/projects/<id>` |
| 3 | 多窗口工作台 | ✅ | `/projects/<id>/workbench` |
| 4 | 多人共管 + NPC 占用锁 | ✅ | NpcTile 头部占用 badge |
| 5 | 触发式需求链 | ✅ | requirement.trigger / dependency_requirement_id |
| 6 | 三级人工审核 | ✅ | NPC > 工位 > 项目 default |
| 7 | 同工位互发 / 跨工位转手 | ✅ | NpcTile 同工位伙伴 + Handoff |
| 8 | 纯人工通道兜底 | ✅ | NpcTile 输入框直接派指令 |
| 9 | 平台 = 协调器（不锁 AI） | ✅ | watcher / runner 跑在用户机器上 |

**第一版可用平台 = 上面 9 项全绿**。

---

## 三、四层结构（项目→工位→NPC→线程）

```
项目层  collaboration_config.review_policy / skill_library
   ↓
工位层  workstation_profiles[computer_node_id] = { skill_inheritance, review_policy }
   ↓
NPC 层  seat = { responsibility, skillLoadout, knowledgeSummary, gitUserName, metadata.review_policy }
   ↓
线程层  Claude Code / Codex CLI 进程，只读上面三层、不持久化
```

**为什么是 4 层**：把"AI 换手"这件事拆开——
- 项目变了？换个 GitHub 仓库就行
- 工位变了？换台电脑，工位继承不动
- NPC 变了？给老员工调岗，知识库还能继承
- 线程变了？Claude Code 重启 / 切到 Codex / 换模型，**完全无感**

---

## 四、第一版实现的关键模块

### A. 项目驾驶舱 `/projects/[id]`
- 三层下钻：项目总览 → 工位分组 → NPC 卡片
- 全员 / 工位广播（preview + commit + 二次确认）
- scorecard 合格性 grade chip（看平台对自己的健康度自检）
- 跨工位 Handoff 面板

### B. NPC 工作台 `/projects/[id]/workbench` ← **核心日常工作面**
- 左栏按工位分组 + 搜索 + 批量勾选
- 右侧多瓷砖（1=全屏 / 2=横分 / 3-4=2×2 / 5+=滚动）
- 每个瓷砖：占用 badge / 档案 / 同工位伙伴 / 6 轨彩色消息流 / 派单输入框
- 占用锁 30s 心跳、关瓷砖自动释放、被人占用时输入框置灰

### C. 协作消息池 (`/api/collaboration/messages`)
- recipient_type 区分：thread_workstation（NPC）/ user / project
- sender_type 区分：human / agent / runner / watcher / system
- 6 角色色带：
  - 🟡 用户 (human)
  - 🟦 本 NPC (agent.self)
  - 🟪 同工位 NPC (agent.peer)
  - 🟥 跨工位 NPC (agent.external)
  - ⬜ Claude CLI / watcher
  - 🔵 系统

### D. 占用锁端点
- `POST /api/collaboration/projects/{id}/thread-workstations/{seat}/occupy`
- `POST .../release`
- `GET .../occupancy`
- 数据落地 `seat.metadata.occupancy = { user_id, user_name, acquired_at, heartbeat_at, preempted, preempted_user }`
- 90s 没续约视为过期

### E. 三级审核策略
- 优先级：NPC > 工位 > 项目 default > 内置规则（跨工位强审核）
- 数据：
  ```jsonc
  project.collaboration_config.review_policy: { default, workstations }
  seat.metadata.review_policy: "force" | "skip" | "inherit"
  ```
- 已通过 16/16 全链路验证（铁证：同项目下 force 优先级压过 skip）

### F. 触发式需求链
- requirement 字段：`target_seat_id` / `trigger` / `dependency_requirement_id`
- 后端 `dispatch_requirement` 状态变更时触发后续

### G. CLI 端可见
- watcher 把 NPC 派给本机 Claude CLI 的指令打印到终端
- 用户在 CLI 也能看到平台下发了什么、AI 回了什么、有没有出错

---

## 五、第一版上线的关键 commit

| commit | 内容 |
|---|---|
| `42f6063` | R1-R3 全链路验收 16/16（同工位互发 / 三级审核 / 触发链 / 多用户同步） |
| `dff15e6` | NPC 占用锁后端 + 90s 心跳 + 抢占语义 |
| `0f8f75a` | NPC 对话框统一视图（人/本NPC/同工位/跨工位/CLI 6 轨彩色） |
| 本轮 | NPC 占用锁前端 UI 接入 + 30s 心跳 + 关瓷砖自动释放 + 输入框锁 |

---

## 六、当前仓库（自验证用）

- 主项目：`proj_ai_collab` (= 平台自己的代码库 https://github.com/wenjunyong666/ai-)
- 两个 seat：`前端工位` (runner_pc1) + `执行工位` (runner_nanopi)
- 验证账号：`lead@example.com` / `chief@local`，密码统一 `demo-pass`

---

## 七、已验证的关键铁证

- 16/16 全链路：`scripts/validate-r1-r3-fullchain.py`
- 7/7 占用锁双用户：`scripts/validate-npc-occupancy.py`
- 占用锁前端生命周期：`scripts/validate-npc-occupancy-frontend.py`（new this round）
- 6 轨对话框分轨：`scripts/validate-npc-dialog-merge.py`
- 截图 6 张：`docs/screenshots/v1/`（详见使用说明）

> 三级审核优先级铁证（来自 16/16 报告）：
> ```
> 前端工位 (workstation skip) → requires_review=false, source=workstation
> 执行工位 (NPC force)        → requires_review=true,  source=npc
> ```
> 同一个项目同一次 broadcast，两个 seat 的审核结果不同，说明优先级真生效。

---

## 八、平台不做什么（明确边界）

- ❌ 不托管 AI 模型，不调用 Claude/Codex 云 API（用户自己的 CLI 调用云，平台只看回执）
- ❌ 不存 GitHub token（平台用 SSH 推，每个 NPC 一个 git author 身份）
- ❌ 不自动决定要不要审核——三级开关给你，你定
- ❌ 不替代 IDE / Git 客户端（这是协调层，不是开发工具）

---

## 九、下一版要补的（路线图节选）

按 ROI 排序：

| 优先级 | 项 | 价值 |
|---|---|---|
| A2 | NPC 状态可视化（红绿灯）| 一眼看到全公司谁在忙 |
| A3 | 触发链 DAG 可视化 | 需求依赖图 |
| B1 | NPC 接手 prompt 自动生成器 | 把 38b3a21 的复制按钮做成智能版 |
| B2 | 线程死亡检测 + 自动降级 | watcher 心跳超时把 NPC 标灰 |
| C1 | 审核策略真门控（不只 preview）| 现在只标记 requires_review，不阻断 |
| F1 | Watcher 注入 git author | GitHub 集成最后一公里 |

---

## 十、本仓库自身就是平台的第一个用户

`proj_ai_collab` 项目就是这个仓库自己，平台用自己调度自己开发自己。
当你看到这份说明、这些验收脚本、这些截图时，它们都是平台跑出来的产物。
