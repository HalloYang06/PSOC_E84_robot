# Release Notes 2026-05-08 — 同工位互认 + 工位长 + 真自主协作（Step 0–8 闭合）

> 分支 `ai/game-loop-core`，主要 commit：`e94b6bc6` `25053118` `418c6265` `2cf545e0` `78b83a8d` `7cbfc388` `565ab686` `7a2dd818`

---

## 这一轮做完了什么

按用户 2026-05-08 拍板的"按顺序来" 8 步清单，全部上线：

| Step | 内容 | commit |
|---|---|---|
| 0 | 消息瓷砖按用户色板分色（人灰/同工位绿/跨工位紫/回执蓝/系统红/自主黄） | `e94b6bc6` |
| 1 | 后端：sender_type=agent + recipient=thread_workstation 自动应用三级 review_policy | `25053118` |
| 2 | 前端：NpcTile 同工位伙伴行 + → 派 按钮（人工代发兜底） | `e94b6bc6` |
| 3 | 前端：NpcTile 我的任务队列卡（FIFO，前 6 条，按发件方着色） | `e94b6bc6` |
| 4 | 工位长身份（workstation_profiles.lead_seat_id + 👑 chip + 金描边） | `418c6265` |
| 5 | 跨工位强制走工位长（后端 redirect + 前端跨工位通道紫色 section） | `2cf545e0` |
| 6 | 公司层 `/projects/[id]/company` 工位长会议室页面 | `78b83a8d` |
| 7 | watcher 注入岗位手册三层文档约定 + GitHub 链接回复约定 | `565ab686` |
| 8 | **MCP server 自主求助**（真自主协作）+ 一键跨电脑配置脚本 | `7a2dd818` |

加上配套：
- `7cbfc388` — `/projects/[id]` 默认进游戏壳 + 顶部薄 nav + 右抽屉 iframe（前端信息架构整理）

---

## 用户原话兑现清单

1. **"NPC 之间自主合作，不是说我点击派那个按钮，他才会派发任务，而是需要我审核才能发出去，也可以开免审"**
   → Step 8：seat-mcp server 三个工具，NPC 自己调，后端 review gate 接管。

2. **"同一工位的 NPC 之间能互相提需求；不同工位的交流要走工位长"**
   → Step 1 + Step 5：同工位免审、跨工位强制 redirect 到目标工位长 + 强审。

3. **"我希望非常有条理，文件、知识库、skill 库都按 项目→工位→NPC→线程 来管"**
   → Step 7：watcher 在 prompt 里告诉 NPC 读三层文档（`docs/projects/<id>/README.md` / `docs/workstations/<node_id>.md` / `docs/npcs/<seat_id>/`）。

4. **"NPC 互相要认识，要看到队列里有什么，颜色要分清"**
   → Step 0/2/3：消息 6 色着色 + 同工位伙伴 chip + 任务队列卡。

5. **"工位长瓷砖要出现在两处：本工位 + 公司层"**
   → Step 4 + Step 6：NpcTile 头部 👑 chip + 公司层独立路由复用 NpcTile。

6. **"默认进游戏界面，其他面板隐藏，可以打开"**
   → `7cbfc388`：GameShell + 70vw 右抽屉 + iframe 隔离。

7. **"别的电脑也要能用，最好能弄到一键配置的脚本"**
   → Step 8 配套：`scripts/setup-seat-mcp.ps1` (Windows) + `setup-seat-mcp.sh` (macOS/Linux)，一行命令完成 5 步。

---

## 用户视角 — 验收记录

**全盘截图走查脚本**：`scripts/validate-full-walk-2026-05-08.mjs`

最近一次结果（2026-05-08 04:08:39 UTC）：**13/13 PASS**

```
✓ A 登录页
✓ B 项目列表
✓ C 游戏壳 + 顶部薄 nav 显示
✓ D 驾驶舱抽屉 70vw 拉出
✓ E 公司层抽屉打开
✓ F 工作台左栏按工位分组
✓ G NPC 瓷砖：→派 按钮存在
✓ G NPC 瓷砖：任务队列卡显示
✓ H 消息流出现 ≥3 种 role 着色（实际 3）
   data-role 分布: human=4 / self=8 / peer=8 / external=0 / watcher=0 / system=0
✓ H 同工位 (peer) 消息能命中绿色（peer=8）
✓ I 跨工位通道 section 出现
✓ K 公司层独立路由可达
```

> 截图：`artifacts/full-walk-2026-05-08/01..10-*.png`（10 张）
> Markdown 报告：`docs/screenshots/v1/full-walk-2026-05-08.md`

种子数据：6 类演示消息（人工 / 同工位 / 跨工位 / 自主求助 / 回执 / 系统），项目 `proj_ai_collab`，3 个 seat（前端工位 / 前端工位-副 / 执行工位）。

---

## 数据 / API 改动

### 新增端点

| 端点 | 用途 |
|---|---|
| `PATCH /api/collaboration/projects/{id}/workstation-profiles/{node_id}` | 设工位长 / 工位级 review_policy |
| `PATCH /api/collaboration/projects/{id}/review-policy` | 设项目级 review_policy.default |
| `POST /api/collaboration/messages/{id}/review/approve` | 通过待审消息 |
| `POST /api/collaboration/messages/{id}/review/reject` | 打回待审消息 |
| `GET /health` | 一键脚本自检用（短路径） |
| `GET /static/seat-mcp-server.py` | 远端拉 MCP server 源码 |

### 数据模型

- `Requirement` 新增 3 字段：`target_seat_id` / `trigger_kind` / `dependency_requirement_id`（commit `3b65db5a`，触发链支持）
- `Project.collaboration_config` 新增 keys：
  - `workstation_profiles[<node_id>].lead_seat_id` — 工位长
  - `workstation_profiles[<node_id>].review_policy` — 工位级 force/skip/inherit
  - `review_policy.default` — 项目级 always/cross_workstation_only/never
- `seat.extra_data.review_policy` — NPC 级 force/skip/inherit

### 行为变化

- 跨工位 agent → agent 消息 → 自动 redirect 到目标工位长，并在 body 注 `经工位长 X 转交（原始目标 NPC: Y）`
- 同工位 agent → agent 消息 → 默认 `queued`（如未设 force）
- 跨工位消息 → 默认 `status=pending_review`（如未设 skip）
- 派给 Claude/Codex 的 prompt 自动注入：seat_id 标识、三层文档路径、GitHub 链接回复约定、seat-mcp 工具说明

---

## 新增脚本 / 工具

| 文件 | 作用 |
|---|---|
| `scripts/seat-mcp-server/server.py` | stdio MCP server（`list_peers` / `request_help` / `dispatch_to_peer`） |
| `scripts/seat-mcp-server/README.md` | 单机 + 局域网工位接入说明 |
| `scripts/seat-mcp-server/.mcp.json.example` | Claude .mcp.json 模板 |
| `scripts/setup-seat-mcp.ps1` | Windows 一键配置（5 步） |
| `scripts/setup-seat-mcp.sh` | macOS/Linux 一键配置（同款 5 步） |
| `scripts/validate-seat-mcp-server.py` | MCP 协议 + 三工具 + review gate（31/31 PASS） |
| `scripts/validate-watcher-prompt-injection.py` | watcher prompt 17 项断言（17/17 PASS） |
| `scripts/validate-full-walk-2026-05-08.mjs` | 用户视角全盘截图（13/13 PASS） |
| `docs/npcs/README.md` | NPC 岗位手册目录约定 |
| `docs/USER_GUIDE.md` | 用户使用文档（本次新增） |

---

## 跨电脑接入（重点）

用户原话："别的电脑也要能用，最好能弄到一键配置的脚本"。

**Windows 工位电脑**：
```powershell
pwsh -ExecutionPolicy Bypass -File scripts/setup-seat-mcp.ps1 -ApiBase http://192.168.1.10:8010
```

**macOS / Linux 工位电脑**：
```bash
bash scripts/setup-seat-mcp.sh --api-base http://192.168.1.10:8010
```

脚本会：
1. 检测 Python ≥ 3.10
2. 从 `<ApiBase>/static/seat-mcp-server.py` 下载 server.py
3. 注册到 Claude / Codex CLI
4. 写永久 `PLATFORM_API_BASE` 环境变量
5. ping `<ApiBase>/health` 自检

之后启 watcher，env 自动透传到 CLI 子进程，CLI 加载的 seat-mcp 自动有正确身份。

详见 `scripts/seat-mcp-server/README.md`。

---

## 已知遗留 / 不做

- `peer_workstation` 这种 metadata 没入库：`CollaborationMessage` 模型本身没 `metadata` 列，跨/不跨用计算属性就够（见 `project_autonomous_collab_data_model.md`）
- `agent_result` receipt 不复制 `dispatch_id`：关联派单/回执仍用 `since_ts + agent_id` 兜底
- typecheck baseline 仍剩 `actions.ts` 两处旧错（与本轮无关）
- eslint 在 `D:\ai合作产品` 中文路径下跑不动（cross-spawn 子模块路径解析失败 — Windows 中文路径问题）
- 旧 `/projects/[id]/2d-upgrade` 路由保留兼容旧链接，但不再加新功能

---

## 下一步建议

1. **真端到端跑一次**（用户起 API + watcher，让一个 NPC 在 CLI 里调 `request_help`，看人工审核 → 派出去 → 对端 watcher 接走 → 回执）。这一轮我用脚本灌种子+截图验收，没真跑过 NPC 自主合作的全链路。
2. **驾驶舱待审区 UI** 还需要打磨（目前要审消息靠瓷砖橙色边提醒，没有全局聚合页）
3. **MCP 工具 e2e**（在工位电脑上跑 `claude mcp list` 确认 seat-mcp 真被加载）

---

## 参考文档

- 用户使用文档：`docs/USER_GUIDE.md`
- NPC 岗位手册约定：`docs/npcs/README.md`
- MCP server 接入：`scripts/seat-mcp-server/README.md`
- 截图验收报告：`docs/screenshots/v1/full-walk-2026-05-08.md`
- 平台合格性自检：`apps/web/app/projects/[id]/cockpit/qualification/page.tsx`
