# seat-mcp-server — NPC 自主求助 MCP 服务

> 这是 Step 8 的核心。它让平台上的每个 NPC（seat）能在自己的 Claude/Codex CLI session 里**主动**调工具找别的 NPC 帮忙——不用用户去 UI 上点"派"按钮。

## 它是什么

一个 stdio MCP server（line-delimited JSON-RPC），在你的 NPC CLI 启动时被加载。它把项目里的 NPC 员工表、工位关系和协作队列接进 NPC 线程，让 NPC 能按结构化方式提出 Need，而不是靠关键词猜要派给谁。

| 工具 | NPC 会怎么用 |
|---|---|
| `list_peers()` | 看项目员工表：我是谁、同工位伙伴、跨工位伙伴、工位长、职责边界 |
| `create_need(...)` | 我缺输入、能力或协作产物时，写入结构化 Need |
| `check_my_needs(limit?)` | 查看我自己提出、等待别人满足的需求 |
| `check_my_tasks(limit?)` | 查看分配给我承接和完成的任务 |
| `request_help(role, ask, expected?)` | 兼容旧工具：内部只转成结构化 Need，不再按关键词直接派单 |
| `dispatch_to_peer(seat_id, title, body)` | 旧直派工具：仅用于用户已批准或低风险同工位场景；新主路径优先 `create_need` |
| `read_my_inbox(limit?)` | 兼容旧队列查询；新语义优先 `check_my_needs` / `check_my_tasks` |
| `mark_done(message_id, body, failed?)` | 长开窗口模式下写回执 |

核心链路：

```text
NPC 读员工表和基础 skill
  -> 调 create_need 写入“我的需求”
  -> 平台 NeedRouter 根据员工表、skill、知识库、状态和审核策略推荐承接 NPC
  -> 需要人审时进入驾驶舱 / NPC 待审卡
  -> 通过或免审后，目标 NPC 的“我的任务”出现 Task
  -> runner 只投递到目标 NPC 绑定的电脑和线程
```

审核规则仍由平台统一执行：
- 同工位、低风险、可信关系可以免审。
- 跨工位、高风险、硬件/部署/固件/ROS 写/真实运动/Git 回退等必须人审。
- 用户手动派单不需要用户审核自己。
- NPC 普通聊天里提到别的 NPC 不会自动派单，只有结构化 `create_need` 才进入 NeedRouter。

`request_help` 和 `dispatch_to_peer` 保留是为了兼容已有线程和旧 prompt；后续上岗包、文档和验收都应优先 `create_need`。

## 接入方式（本机）

### 1. 让你的 Claude / Codex CLI 加载这个 server

**Claude Code CLI** — 在你启动 NPC 的那个项目目录里（即 `--executor-cwd`），新建 `.mcp.json`：

```jsonc
{
  "mcpServers": {
    "seat-mcp": {
      "command": "python",
      "args": ["D:/ai合作产品/scripts/seat-mcp-server/server.py"]
    }
  }
}
```

或者用 CLI 注册（推荐，免改文件）：

```powershell
claude mcp add seat-mcp -- python "D:/ai合作产品/scripts/seat-mcp-server/server.py"
```

**Codex CLI** — 在 `~/.codex/config.toml` 里加：

```toml
[mcp_servers.seat-mcp]
command = "python"
args = ["D:/ai合作产品/scripts/seat-mcp-server/server.py"]
```

### 2. 不需要做什么

- **不需要**单独启动这个 server。它是 stdio 模式，CLI 会按需拉起、关闭。
- **不需要**手动配身份。watcher（`scripts/start-thread-watcher.ps1` → `platform-workstation-adapter.py`）会在派任务给 CLI 之前，把以下环境变量塞进父进程，CLI 再继承给 MCP server：

  | 环境变量 | 含义 |
  |---|---|
  | `PLATFORM_API_BASE` | 平台 API 根，如 `http://127.0.0.1:8010` |
  | `PLATFORM_PROJECT_ID` | 当前项目 |
  | `PLATFORM_WORKSTATION_ID` | 当前工位（电脑节点）的 config_id |
  | `PLATFORM_SEAT_ID` | 当前消息的收件 NPC seat 行 id（每条消息会动态更新） |
  | `PLATFORM_ADAPTER_TOKEN` | workstation adapter token（优先） |
  | `PLATFORM_AUTH_TOKEN` | 人类 session bearer（兜底） |

### 3. 验证它能跑

```powershell
cd "D:/ai合作产品"
python scripts/validate-seat-mcp-server.py
```

期望输出 `PASS — N/N 项全部通过`，并确认 `create_need`、`check_my_needs`、`check_my_tasks` 都在工具列表里。

## 接入方式（局域网另一台电脑）

平台支持多电脑分担工位（见 `project_lan_multi_pc.md`）。如果 NPC 跑在另一台 Windows/Mac/Linux 上，**这台电脑也需要装 seat-mcp-server**。

### A 方案 — 共享一份代码（推荐）

如果工位电脑能访问中央仓库（GitHub / 局域网 SMB / 同步盘）：

1. 把 `scripts/seat-mcp-server/server.py` 同步到工位电脑上的任意路径，例如 `C:\platform\seat-mcp-server\server.py`。
2. 在工位电脑的 CLI 配置里指向这个本地路径：

   ```jsonc
   // .mcp.json on the worker PC
   {
     "mcpServers": {
       "seat-mcp": {
         "command": "python",
         "args": ["C:/platform/seat-mcp-server/server.py"],
         "env": {
           "PLATFORM_API_BASE": "http://192.168.1.10:8010"
         }
       }
     }
   }
   ```

3. **关键：把 `PLATFORM_API_BASE` 显式写在 env 里**，因为这台电脑不会自动认 127.0.0.1。
4. 工位电脑也要装 watcher（`platform-workstation-adapter.py`），watcher 会在每次派任务时刷新 `PLATFORM_SEAT_ID`，所以 CLI 拉起的 MCP server 自动拿到正确身份。

### B 方案 — 工位电脑只装 watcher，不单独配 .mcp.json

如果工位电脑的 NPC 是被平台 watcher 拉起的（没有人在那台机上手动 `claude` 进 CLI），watcher 已经把环境变量传进 CLI 进程，**CLI 内部加载的 MCP server 自动继承**。这种情况下：

1. 把整个 `D:/ai合作产品/scripts/seat-mcp-server/` 同步到工位电脑（路径任意）。
2. 在 `claude mcp add` / `codex config.toml` 里指向同步过来的本地路径。
3. **不用再在 .mcp.json 里写 env**——watcher 已经把 `PLATFORM_API_BASE` / `PLATFORM_PROJECT_ID` / `PLATFORM_SEAT_ID` 等放在父进程 env 里，CLI 子进程会继承。

### 必须确认的网络项

| 项目 | 检查命令（在工位电脑上跑） |
|---|---|
| 平台 API 可达 | `curl http://<host>:8010/health`（应返回 `{"ok":true,...}` 或 200） |
| Python 在 PATH 里 | `python --version`（≥ 3.10） |
| 防火墙放行 | 平台主机允许 8010 入站；工位电脑允许 Python 出站 |

如果 `PLATFORM_API_BASE` 写错了，MCP 工具调用会返回 `{"ok": false, "error": "..."}`，但 NPC 不会崩溃，只是没法发起求助。

## 故障排查

| 现象 | 原因 | 修法 |
|---|---|---|
| `list_peers` 返回 `missing PLATFORM_PROJECT_ID or PLATFORM_SEAT_ID env` | watcher 没启动，CLI 在裸跑 | 用 `scripts/start-thread-watcher.ps1` 启动 NPC，不要手动 `claude` |
| `create_need` 返回 `REQUESTER_SEAT_NOT_FOUND` | 当前 seat 不在项目员工表 | 检查 `PLATFORM_SEAT_ID` 是不是该 NPC 的 row id |
| `create_need` 返回缺少字段 | Need 没有 expected_output 或 acceptance_criteria | 补齐期望产物和验收标准；草稿不能自动路由成任务 |
| `create_need` 返回需要审核 | NeedRouter 判定跨工位或高风险 | 用户去驾驶舱或 NPC 待审卡通过/打回 |
| `request_help` 仍被调用 | 旧线程或旧 prompt 还没迁移 | 它会被转成结构化 Need；更新上岗包让 NPC 优先用 `create_need` |
| 调任何工具 HTTP 401 | 没传 token | 设 `PLATFORM_ADAPTER_TOKEN` 或 `PLATFORM_AUTH_TOKEN`（watcher 会自动注入） |
| MCP server 不出现在 CLI 工具列表 | CLI 没识别到 .mcp.json | 重启 CLI session；或用 `claude mcp list` 检查 |

## 三层 review_policy 速查（决定 needs_review 的逻辑）

```
NPC 级 (seat.extra_data.review_policy)
    ↓ 不是 inherit 才生效
工位级 (collaboration_config.workstation_profiles[node].review_policy)
    ↓ 不是 inherit 才生效
项目级 default (collaboration_config.review_policy.default)
    ↓ 默认 cross_workstation_only
内置：跨逻辑工位 → 强审；没有逻辑工位时退回 computer_node_id
```

任何一层设 `force` → 一定 pending_review；设 `skip` → 一定 queued。

## 它解决了什么

- 用户**第四次**强调："npc 自主协作，不是说我点击派那个按钮，他才会派发任务，而是需要我审核才能发出去，也可以开免审"（见 `project_autonomous_collab_true_definition.md`）。
- 之前的"→派"按钮是**人工派单**换皮，不是自主协作。
- seat-mcp 让 NPC 在 CLI 里**自己识别需要、自己调 `create_need` 写入需求**，平台负责 NeedRouter、审核 gate、任务队列和 runner 投递。这才是“需求属于发起 NPC、任务属于承接 NPC”的多 agent 工作流。
