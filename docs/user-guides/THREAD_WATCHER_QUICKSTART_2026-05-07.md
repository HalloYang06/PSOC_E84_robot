# 线程 watcher 上手（3 分钟）

> 让本机的 Claude / Codex 线程接到平台派来的指令并显示过程。
> 这是通道 B（线程 = 工位 = 一个 PS 终端）的用户路径。
> 通道 A（runner 整机接单）请看 [LAN_QUICKSTART.md](../../LAN_QUICKSTART.md)。

---

## 心智模型：线程 = 一个 PS 终端

来自 MEMORY 的 `project_npc_workstation_semantics`：

- **NPC** = 长期员工（决定派给谁、怎么交接）
- **工位 / 线程** = 部门里一根 AI 工具线程，对应**一台电脑上一个常驻 PS 终端**
- **关一个终端 = 少一根接单线程**——平台不会自动把任务转到别的线程

所以："你打开几个 PS 终端跑 watcher，平台就有几条本机线程能接单。"

---

## 第 1 步 · 找到要绑的 `WorkstationId`

`WorkstationId` 就是数据库里 `project_thread_workstations.config_id`（不是表 PK，**支持中文**）。

**怎么从 UI 拿到**：
1. 浏览器进项目 `/projects/<id>/2d-upgrade`
2. 右侧 dock 找"机器房" / "NPC 管理"抽屉
3. 找到要绑的线程卡片，看它的 ID 或 name 字段——那就是 `WorkstationId`

例：`proj_ai_collab` 项目下有一条线程叫 `前端工位`，那就用 `前端工位` 这五个字。

**也可以查 DB**（开发者）：

```powershell
cd D:\ai合作产品\apps\api
python -c "import sqlite3; c=sqlite3.connect('ai_collab.db'); print(list(c.execute(\"SELECT config_id, name FROM project_thread_workstations WHERE project_id='proj_ai_collab'\")))"
```

---

## 第 2 步 · 在本机起 watcher 终端

打开一个**新的** PowerShell 窗口（不要复用已经在跑别的东西的窗口），cd 到仓库根：

```powershell
cd D:\ai合作产品
.\scripts\start-thread-watcher.ps1 -ProjectId proj_ai_collab -WorkstationId 'frontend-thread'
```

**关键引号约定**：
- ASCII 的 WorkstationId（如 `frontend-thread`）：直接写或加双引号都行
- **中文 WorkstationId**：必须用**单引号**包裹，否则 PowerShell 会被 `&` 等字符切断
  - ✅ `-WorkstationId '前端工位'`
  - ❌ `-WorkstationId "前端工位"`（特定情况下会被 `$` 字符插值踩坑）

启动成功后会看到：

```
========================================
项目线程 watcher 启动准备
项目: proj_ai_collab
线程: 前端工位
API:  http://127.0.0.1:8000
执行目录: D:\ai合作产品
轮询: 每 3s
========================================
```

横幅出现 = watcher 在跑。**这个窗口不能关**，关了就接不到单。

> 💡 多条线程怎么办：每条线程**新开**一个 PS 终端，每个终端跑一条 `start-thread-watcher.ps1`，互不干扰。

---

## 第 3 步 · 在平台派一条最小指令验证

1. 浏览器进项目 `/projects/<id>/2d-upgrade`
2. 右侧 dock → "Git 工作面板" 或 "团队"
3. 找"下发 Runner 命令"表单（在底部），目标电脑选你这台
4. 标题写 "ping watcher"，正文写 "请只回复一行：最终回复：pong-watcher"
5. 点"下发 Runner 命令"

回到 watcher 终端窗口，应该看到流式输出：

```
[收到平台指令] msg=msg-xxx title=ping watcher provider=claude
[正在调用 claude CLI ...]
最终回复：pong-watcher
[已回写平台] status=completed note_chars=18
```

回浏览器看消息池，应该看到刚才那条命令变成 `completed`，并且多了一条 `agent_result` 类型的消息，body 是 `[ping watcher] 最终回复：pong-watcher`。

**这就是合格性硬指标**："平台派单 → 本机 CLI 真起 → 用户能看到过程 → 平台拿到回复"。

---

## 怎么停 watcher

在 watcher 终端窗口按 **Ctrl+C**。看到 `KeyboardInterrupt` 或 watcher 退出码即可。

**注意**：watcher 停了之后，平台派给这条线程的指令会进 `pending` 队列累积，下次 watcher 再起会立刻把堆积的单都拉下来跑。所以**临时关一会儿没事**，**长期不在线就要去 UI 把这条线程标成离线**（避免别人继续派单）。

---

## 常见问题

### Q1 · `claude.cmd` 找不到

```powershell
where claude
# 应该返回 C:\Users\<you>\AppData\Roaming\npm\claude.cmd

# 没有就装：
npm install -g @anthropic-ai/claude-cli
claude --version
```

### Q2 · 中文 `WorkstationId` 报 `latin-1` / `UnicodeEncodeError`

这是 urllib 老 bug，**已修**（commit `1d1e997`，PlatformClient 自动 percent-encode 中文 header）。如果你还在踩，确认本机 `git pull` 到 `1d1e997` 或更新版本。

### Q3 · watcher 起来了但平台派单后没动静

按这个顺序排查：
1. **目标电脑选对了吗**：派单表单里"目标电脑"下拉得选你这台 PC 的 computer_node_id，不是别的
2. **WorkstationId 拼写对了吗**：watcher 那边的 `WorkstationId` 必须和 UI 上线程的 config_id 完全一致（中文一字不差）
3. **API 地址对吗**：默认 `http://127.0.0.1:8000`，跨机要带 `-ApiBase http://192.168.x.x:8000`
4. 看 watcher 终端有没有 `[poll error]` 之类的报错——发出来好定位

### Q4 · 一台电脑要绑几条线程

打几个 PS 终端，每个跑一条 `start-thread-watcher.ps1`，参数不同就行。watcher 之间无状态共享，互不干扰。

实际场景：
- PS 终端 1：`-WorkstationId 'frontend-thread'`（前端写代码）
- PS 终端 2：`-WorkstationId 'backend-thread'`（后端写 API）
- PS 终端 3：`-WorkstationId 'review-thread'`（审代码）

派任务时分别选 NPC，绑哪条线程就走哪个终端。

### Q5 · 怎么换 provider（claude → codex）

`start-thread-watcher.ps1` 加 `-Provider codex`：

```powershell
.\scripts\start-thread-watcher.ps1 -ProjectId proj_ai_collab -WorkstationId 'codex-thread' -Provider codex
```

不加 `-Provider` 就走 adapter-config 里的默认（通常 claude）。

---

## 相关文档

- 通道 A（runner 整机）上手：[LAN_QUICKSTART.md](../../LAN_QUICKSTART.md)
- 通道 A 合格性证据：[../acceptance/cli-bridge-walk-2026-05-07.md](../acceptance/cli-bridge-walk-2026-05-07.md)
- 通道 B 合格性证据：[../acceptance/thread-watcher-walk-2026-05-07.md](../acceptance/thread-watcher-walk-2026-05-07.md)
- watcher 启动器源码：[`scripts/start-thread-watcher.ps1`](../../scripts/start-thread-watcher.ps1)
- watcher 长跑核心：[`scripts/platform-workstation-adapter.py`](../../scripts/platform-workstation-adapter.py) 的 `--watch` 模式
