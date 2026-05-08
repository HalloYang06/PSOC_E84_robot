# seat-mcp-server — NPC 自主求助 MCP 服务

> 这是 Step 8 的核心。它让平台上的每个 NPC（seat）能在自己的 Claude/Codex CLI session 里**主动**调工具找别的 NPC 帮忙——不用用户去 UI 上点"派"按钮。

## 它是什么

一个 stdio MCP server（line-delimited JSON-RPC），在你的 NPC CLI 启动时被加载，提供三个工具：

| 工具 | NPC 会怎么用 |
|---|---|
| `list_peers()` | 我有哪些伙伴可以调动？返回同工位（同电脑）/ 跨工位（其他电脑）名单 |
| `request_help(role, ask, expected?)` | 按角色关键字找伙伴自动派单（例："找一个 reviewer 帮我看 PR"） |
| `dispatch_to_peer(seat_id, title, body)` | 已经知道伙伴 seat_id，直接指名派单 |

每次调用都走平台后端 `POST /api/collaboration/messages`，**自动应用现有的三级 review_policy**：
- 同工位 → 默认 `queued`（直接进对方队列）
- 跨工位 → 默认 `pending_review`（用户在驾驶舱审核通过后才真发出）
- 项目/工位/NPC 任意一层 `review_policy=skip` → 免审

返回里的 `needs_review` 字段告诉 NPC 自己"是否需要等用户点通过"。

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

期望输出 `✅ PASS — N/N 项全部通过`。

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
| `request_help` 返回 `platform rejected the dispatch` | API 拒绝了 sender_id（不在项目 seat 列表） | 检查 `PLATFORM_SEAT_ID` 是不是该 NPC 的 row id |
| `request_help` 总是 `needs_review=true` | 默认行为：跨工位强审 | 用户去驾驶舱待审区点通过，或在项目设置里把 `review_policy.default` 改成 `never` |
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
内置：跨 computer_node_id → 强审
```

任何一层设 `force` → 一定 pending_review；设 `skip` → 一定 queued。

## 它解决了什么

- 用户**第四次**强调："npc 自主协作，不是说我点击派那个按钮，他才会派发任务，而是需要我审核才能发出去，也可以开免审"（见 `project_autonomous_collab_true_definition.md`）。
- 之前的"→派"按钮是**人工派单**换皮，不是自主协作。
- seat-mcp 让 NPC 在 CLI 里**自己识别需要、自己调工具发起**，平台负责审核 gate——这才是"真自主协作"。
