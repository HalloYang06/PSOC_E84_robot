# 用户使用文档（USER_GUIDE）

> 平台：AI 协作平台（项目→工位→NPC→线程 四层结构）
> 版本：2026-05-08（Step 0–8 全部上线）
> 适用：项目 owner / 工位用户 / NPC 监管员

---

## 1. 三件套先看哪里

打开浏览器到 `http://<平台主机>:3000/projects/<项目id>`，**默认进游戏壳**（Phaser 农场场景），顶部有一条 36px 高的薄 nav：

| 按钮 | 抽屉里显示什么 | 何时点 |
|---|---|---|
| 🛠️ 驾驶舱 | 项目全局视图（合格性 / 跨工位 / 待审 / 进度） | 每天上班先点一次扫一眼 |
| 🧑‍💼 工作台 | NPC 瓷砖（多 NPC 同屏，6 色消息流） | **大部分操作在这里** |
| 🏢 公司层 | 各工位的工位长瓷砖会议室 | 跨工位协调时打开 |
| 🙈 隐藏游戏 | 占位符 + 抽屉照常用 | 不想看动画时 |

抽屉是 70vw 宽、从右拉出，iframe 嵌的同一套页面（带 `?embed=drawer`），头部有「↗ 独立页」可在新标签页打开。**点遮罩或 ✕ 关闭。**

> 截图证据：`artifacts/full-walk-2026-05-08/03-game-shell.png` / `04-cockpit-drawer.png` / `05-company-drawer.png`

---

## 2. 工作台（用得最多）

打开「🧑‍💼 工作台」抽屉，或直接 `/projects/<id>/workbench`：

- 左栏 NPC 列表，按工位（电脑节点）分组
- 每行 NPC 名字旁有 `+` 号，点开瓷砖
- 瓷砖布局：1 个 = 全屏，2 个 = 横分，3-4 个 = 2×2，5+ 个自动滚动

> 截图证据：`06-workbench-overview.png` / `07-tile-opened.png`

### 2.1 NPC 瓷砖里能看到什么

打开 NPC B 瓷砖后从上到下：

1. **头部**：NPC 名 + provider + 工位长 chip（👑 金）+ review_policy
2. **同工位伙伴行**：本工位其他 NPC 的 chip（lead 加 👑 + 金边），右侧每个有 `→ 派` 按钮（**人工代发**，不是自主协作）
3. **跨工位通道（紫）**：列出其他工位的工位长，跨工位消息默认走这里转交
4. **我的任务队列（FIFO，最多 6 条）**：发件方着色，状态 chip
5. **消息流主体**：6 色着色（详见 §2.2），上滚翻历史，"过滤噪声"复选框过滤 watcher 启动等
6. **底部派单 textarea**：写指令，Ctrl+Enter 发送

### 2.2 消息流的六种颜色（关键）

每条消息 div 都带 `data-role="..."`，CSS 按 role 着色：

| role | 颜色 | 含义 | 例子 |
|---|---|---|---|
| `human` | 灰 | 人在 UI 派的单 | "请加登出按钮" |
| `self` | 青 | 本 NPC 发的（多半是回执） | "已修，链接 https://github.com/..." |
| `peer` | 绿 | **同工位**别的 NPC 发的 | "兄弟看下 PR #42" |
| `external` | 紫 | **跨工位** NPC 发的（默认要审） | "API 加了 paginate" |
| `watcher` | 蓝 | Claude CLI / watcher 回的 | watcher 心跳 / mcp 加载 |
| `system` | 红 | 平台系统消息 / 错误 | watcher 启动失败 |
| 加上：`status=pending_review` | 橙边 | 待审 | 跨工位默认状态 |

> 截图证据：`08-message-stream-colors.png`（实测 human=4 / self=8 / peer=8）

**用户为什么需要看到这些颜色**：一眼看出"哪条是别的 NPC 在找我"vs"哪条是用户在派我"vs"我自己的回执"。颜色是定位话题的最快路径，不用读 sender 字段。

---

## 3. 公司层（工位长会议室）

`/projects/<id>/company` 或顶 nav「🏢 公司层」抽屉：

- 只渲染 `isLead === true` 的 NPC 瓷砖
- 复用 NpcTile 组件，所以同样有 6 色消息流
- 工位长瓷砖会**同时出现在两处**：本工位（工作台）+ 公司层

> 截图证据：`05-company-drawer.png` / `10-company-page.png`

---

## 4. 派单的 4 种路径（按"自主程度"排序）

| 谁触发 | 怎么做 | 默认审核 |
|---|---|---|
| 1. 用户人工 | 瓷砖底部 textarea → 发送 | 跨工位强审，同工位免审 |
| 2. 用户代发某 NPC | 同工位伙伴 chip 上的 `→ 派` 按钮 | 同上 |
| 3. 需求依赖触发 | 父 requirement done → 自动派下游 | 按 review_policy |
| 4. NPC 自主求助 ⭐ | NPC 自己在 CLI 里调 seat-mcp 工具 | **同上，这才是真自主协作** |

**自主求助怎么用**：
- 你启动 NPC（`scripts/start-thread-watcher.ps1 -ProjectId .. -WorkstationId .. [-SpawnWindow]`）后，NPC 的 Claude/Codex CLI 会自动加载 `seat-mcp` MCP server
- NPC 干活时如果需要别的 NPC 帮忙，**它自己**调四个工具之一：
  - `list_peers()` — 看谁在
  - `request_help(role, ask)` — 按角色找伙伴
  - `dispatch_to_peer(seat_id, title, body)` — 直接指名
  - `read_my_inbox(limit?)` — **自查自己的协作流**：别人派给我的派单 / 别人对我派单的 ack/done/reject 回执 / 我自己发出的派单状态。NPC 在 CLI 终端里直接看见完整交互。
- 工具调用结果会触发后端创建消息，**同工位默认 queued、跨工位默认 pending_review**
- 用户在驾驶舱待审区点"通过" → 真发出去；点"打回" → 取消

**让 Claude/Codex 在自己的窗口运行**（用户能看到 AI 真在打字）：
- 在 `start-thread-watcher.ps1` 后加 `-SpawnWindow`：每次 watcher 收到平台指令，都会**弹出一个独立 PowerShell 窗口**跑那条 claude/codex CLI 调用，用户能看到完整的对话。
- 弹出的窗口标题为 `NPC <workstation_id> · <provider>`，stdout 全部进 transcript，等 CLI 退出 3 秒后自动关闭。adapter 同时把 transcript 内容回写为 done 回执 body。

> 跨电脑配置见 §6 + `scripts/seat-mcp-server/README.md`

---

## 5. 三级 review_policy（人工审核开关）

判定优先级：**NPC > 工位 > 项目 default > 内置规则（跨工位强审）**

```
seat.extra_data.review_policy: force / skip / inherit
  ↓ inherit 时穿透到下层
collaboration_config.workstation_profiles[node].review_policy: force / skip / inherit
  ↓
collaboration_config.review_policy.default: always / cross_workstation_only(默认) / never
  ↓
内置：computer_node_id 不同 → 强审
```

设置入口（API 层，前端 toggle 在驾驶舱设置抽屉）：

- 项目级：`PATCH /api/collaboration/projects/{id}/review-policy { default: "never" }`
- 工位级：`PATCH /api/collaboration/projects/{id}/workstation-profiles/{node_id} { review_policy: "skip" }`
- NPC 级：改 seat 的 extra_data

**最常用**：把"代码审核 NPC"工位的 review_policy 设成 skip，让其他 NPC 找他时不需要等用户点通过。

---

## 6. 跨电脑接入（局域网工位）

平台支持多电脑分担工位（一台电脑不够跑那么多 NPC）。在另一台 Windows / Mac / Linux 电脑上配置：

### 一键脚本

**Windows**（在工位电脑 PowerShell 里跑）：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/setup-seat-mcp.ps1 `
  -ApiBase http://<平台主机IP>:8010
```

**macOS / Linux**：

```bash
bash scripts/setup-seat-mcp.sh --api-base http://<平台主机IP>:8010
```

脚本自动做：
1. 检测 Python ≥ 3.10
2. 从 `<ApiBase>/static/seat-mcp-server.py` 下载 server.py（或用 `-SourcePath` 指本地副本）
3. 注册到 Claude / Codex CLI（`claude mcp add` / `~/.codex/config.toml`）
4. 写入用户级 `PLATFORM_API_BASE` 环境变量（PowerShell 里 `[Environment]::SetEnvironmentVariable` / Linux 写 `~/.profile`）
5. ping `<ApiBase>/health` 自检

### 之后启动 watcher

工位电脑上：
```powershell
pwsh scripts/start-thread-watcher.ps1 `
  -ProjectId <项目id> `
  -WorkstationId <该电脑的工位id> `
  -ApiBase http://<平台主机IP>:8010
```

watcher 拉起 Claude/Codex CLI 时会注入：
- `PLATFORM_API_BASE` / `PROJECT_ID` / `WORKSTATION_ID` / `SEAT_ID`（每条消息动态刷）
- `PLATFORM_ADAPTER_TOKEN` 或 `PLATFORM_AUTH_TOKEN`

CLI 内部加载的 seat-mcp server 自动继承 env，无需重复配置。

### 必须检查的网络项

| 项 | 检查命令 |
|---|---|
| 平台 API 可达 | `curl http://<host>:8010/health`（200 OK） |
| Python ≥ 3.10 | `python --version` |
| 防火墙 | 平台主机放行 8010 入站；工位放行 Python 出站 |

故障排查表见 `scripts/seat-mcp-server/README.md` § 故障排查。

---

## 7. 验收脚本一览

| 脚本 | 验什么 | 命令 |
|---|---|---|
| `scripts/validate-full-walk-2026-05-08.mjs` | 全盘截图（用户视角，10 张） | `node scripts/validate-full-walk-2026-05-08.mjs` |
| `scripts/validate-game-shell-ui.mjs` | 游戏壳 + 抽屉 6 项断言 | `node scripts/validate-game-shell-ui.mjs` |
| `scripts/validate-tile-ui-2026-05-08.mjs` | NPC 瓷砖 → 派 / 队列 / 分色 | `node scripts/validate-tile-ui-2026-05-08.mjs` |
| `scripts/validate-cross-workstation-lead-redirect.mjs` | 跨工位走工位长 | 同上 |
| `scripts/validate-watcher-prompt-injection.py` | watcher 注入文档约定 | `python scripts/validate-watcher-prompt-injection.py` |
| `scripts/validate-seat-mcp-server.py` | MCP 工具 + review gate | `python scripts/validate-seat-mcp-server.py` |
| `scripts/validate-npc-autonomous-collab.mjs` | 自主合作端到端 | 同上 |
| `scripts/validate-queue-concurrency.mjs` | 队列并发原子性 | 同上 |
| `scripts/validate-seat-to-seat-direct.mjs` | 同工位直派 / 跨工位 pending | 同上 |

最近一次全盘走查：**13/13 PASS**，报告在 `docs/screenshots/v1/full-walk-2026-05-08.md`。

---

## 8. 用户视角易犯的错（FAQ）

**Q：进 `/projects/<id>` 看不到游戏壳，进了旧农场页？**
A：URL 上有 `legacy=` / `mode=` / `zone=` 参数会走旧版。去掉这些参数即可。

**Q：瓷砖里看不到"跨工位通道"section？**
A：项目里没人当工位长。在驾驶舱（或 PATCH workstation-profile）设 `lead_seat_id`。

**Q：跨工位消息发出去后对方收不到？**
A：状态是 `pending_review`（橙）。去驾驶舱待审区点通过；或者把 review_policy 改成 skip。

**Q：另一台电脑的 NPC 调 `request_help` 报 "missing PLATFORM_PROJECT_ID"？**
A：那台电脑没起 watcher，CLI 是裸跑的。用 `start-thread-watcher.ps1` 启动，或在 .mcp.json 的 env 里手动写 `PLATFORM_API_BASE`。

**Q：消息流没颜色？**
A：先确认浏览器没缓存旧 CSS（强刷 Ctrl+Shift+R）。再确认 sender_id 用的是 `seat.id`（中文名）不是 `row_id`（UUID） — 前端 peerIds 取的是 `seat.id`。

---

## 9. 一句话操作清单

1. 起服务：`uvicorn app.main:app --port 8010` + `npm run dev:web`
2. 浏览器 → `http://localhost:3000/projects/proj_ai_collab`
3. 顶 nav 点「🧑‍💼 工作台」 → 抽屉拉出 → 左栏点 `+` 开 NPC 瓷砖
4. 看 6 色消息流定位需要处理的事情（橙=待审 / 紫=跨工位别人找你）
5. 待审消息点通过；普通消息直接读
6. 自己派单：底部 textarea / 同工位伙伴 → 派
7. 让 NPC 自主合作：起 watcher → NPC 自己调 seat-mcp 工具

跨电脑工位：跑 `setup-seat-mcp.{ps1,sh}` 一键搞定，再启 watcher。
