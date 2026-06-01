# AI 协作平台扩展全面 QA 问题清单 - 2026-06-01

本轮 QA 以 `docs/platform-agent-operating-architecture.md` 为总架构合同，覆盖云端对齐、构建、后端全量测试、真实云端页面、账号/项目隔离、runner 队列、Linux/Windows 接入命令、线程扫描可见性、NPC 工作台、设备数据工作台、MCP 工具和既有验证脚本可维护性。

## 基线

- 云端对齐通过：`web=http://106.55.62.122:3001`、`api=http://106.55.62.122:8011`、部署 `4393b401dcf5 / ai/game-loop-core / 2026-06-01T02:03:50Z`。
- 公网 smoke 通过：登录页 200，API health 200，`ready=true`。
- Web 构建通过：`npm --workspace apps/web run build`。
- 后端全量测试未通过：`python -m pytest apps/api/tests` 结果 `256 passed / 6 failed`。
- 云端用户/隔离回归通过：`cloud-user-ux-isolation/2026-06-01T02-10-32-148Z/report.json`，`ok=true`、`issues=[]`、`skipped=[]`。
- NPC 工作台派发证据只读验证通过：`dispatch-evidence/platform-dispatch-evidence-report-20260601-101640.json`。
- 云端 runner 临时派发 fullchain 通过：`runner-dispatch-fullchain/cloud-runner-dispatch-fullchain-report-20260601-101532.json`。
- Linux/Windows 接入命令验证通过：`cloud-onboarding/cloud-computer-onboarding-commands-report-20260601-101030.json`。

## P0 问题

### P0-1 Runner 队列仍有无法解释的陈旧 queued 命令

证据：

```powershell
python scripts/validate-runner-watch-queue-http.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --strict
```

结果：

- 电脑数 `5`，线程数清理后回到 `34`。
- 可接单 runner `1`，阻塞 runner `4`。
- queued command `16`，全部超过 10 分钟。
- `14` 条可解释为等待离线目标电脑恢复。
- `2` 条无法解释为离线目标电脑，最旧约 `16838` 分钟。

影响：

- 用户看到任务/线程扫描仍在排队，但平台无法解释为什么还在排。
- 这会破坏“离线/重连状态准确”和“不能假装派发成功”的 P0 合同。

建议：

- 后端给 `thread_scan_request` / runner command 增加 TTL 收口：过期且目标不离线时标为 `blocked` 或 `needs_user_action`。
- UI 给出“重新扫描 / 取消 / 改绑电脑 / 查看原因”，不要继续显示普通 queued。

### P0-2 线程扫描可见性验证脚本会污染线上线程，并且当前无法证明线程列表可在页面稳定选择

证据：

```powershell
python scripts/validate-computer-thread-visibility-http.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd
```

结果：

- 脚本失败：`Could not find computer thread preview section in HTML`。
- 源码会先创建电脑、注册 runner、同步 9 个 `可见性验收线程`，然后才抓 HTML。
- 异常路径只清电脑节点，不清已同步线程。
- 本轮发现线程数从 `34` 增到 `43`，已手动删除 `thread-http-101031-thread-01..09`，清理后线程数恢复 `34`。

影响：

- QA 脚本自身会污染真实项目，风险高。
- 线程扫描 -> 页面显示命名线程 -> 用户绑定 NPC 的 P0 闭环缺少可靠回归证据。

建议：

- 先修脚本：所有创建的线程必须放入 `finally` 清理，失败也清。
- 再改验证方式：用真实浏览器等待客户端渲染，不要只抓 SSR HTML 里的 `data-computer-thread-preview-for`。
- 产品侧确认线程绑定入口是否有稳定 data attributes，并只显示用户可读线程名。

### P0-3 多 runner / 多电脑防抢隔离脚本失败，无法证明绑定 runner 不被其他电脑抢单

证据：

```powershell
python scripts/validate-cloud-runner-workstation-isolation.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd
```

结果：

- 失败在临时电脑 `iso-a-0601101532` 创建后旋转 pairing token：`COMPUTER_NODE_NOT_FOUND`。
- cleanup 也返回 404，并出现乱码错误文案：`鐢佃剳鑺傜偣 does not exist`。

影响：

- 当前无法用脚本证明“任务只投给绑定电脑/runner，不能被别的电脑抢”。
- API 错误文案出现 mojibake，会污染用户可见错误或日志。

建议：

- 排查电脑节点创建接口是否忽略客户端传入 `id`，或 pairing token 路由是否按另一套 ID 查找。
- 更新隔离脚本使用创建响应里的真实 node id。
- 修复错误消息编码，确保中文错误不乱码。

### P0-4 后端全量测试 6 个失败，集中在派发真实状态契约和写 schema 安全契约

证据：

```powershell
python -m pytest apps/api/tests
```

失败：

- `test_runner_relay_command_accepts_structured_dispatch_id_without_legacy_body_hint`
- `test_runner_relay_command_rejects_dispatch_from_another_project`
- `test_security_write_schemas_do_not_expose_actor_or_status_fields`
- `test_task_professional_view_aggregates_dispatch_messages_artifacts_and_audit`
- `test_artifact_index_rejects_historical_alias_mismatch_even_when_source_message_id_matches`
- `test_task_professional_view_summarizes_runner_capability_and_active_auto_retry`

现象：

- 多个测试期待 `/api/tasks/{id}/dispatch` 返回 200，但当前返回 `409 TASK_DISPATCH_COMPUTER_UNBOUND`。
- `RunnerRelayCommandCreate` 写 schema 多出 `metadata` 字段，违反现有安全测试预期。

判断：

- 派发 409 可能是产品正确强化了“无绑定电脑/runner 不许假派发”，但测试 fixtures 还按旧合同构造。
- `metadata` 写入面是否允许需要重新定契约；如果允许，测试要改为白名单 metadata key；如果不允许，schema 要收回。

建议：

- 明确测试合同：P0 下 dispatch 测试必须创建真实可派 runner/computer，不能绕过状态检查。
- 对 relay `metadata` 增加 allowlist 或改内部字段来源，避免外部写接口开放任意 metadata。

## P1 问题

### P1-1 登录页仍显示旧口径“人工审核”

证据：

- `main-surface-sweep/surface-sweep-report-20260601-101150.json`
- 登录页文本包含：`人工审核、自动化开关、最终回复池都回到项目内`。

影响：

- 当前主产品口径已收敛为“人工确认”，登录页仍是旧词。
- 新用户第一屏会看到旧架构语言。

建议：

- 修改 `apps/web/app/login/page.tsx` 中的登录页卖点文案。

### P1-2 主页面仍暴露“运行评分 D”，用户视角像内部评分/缺陷等级

证据：

- `main-surface-sweep/surface-sweep-report-20260601-101150.md`
- 主项目地图页、电脑、Skill、日程、Git 等截图文本均出现：`运行评分 D (0.359)` 或 `运行评分 D (0.344)`。

影响：

- “合格性 D”此前已被禁，`运行评分 D`语义仍接近内部质量分。
- 普通用户不知道 D 是什么，也不知道该怎么修。

建议：

- 改成用户态状态：例如“运行状态需整理 / 有待处理项 / 查看改进建议”。
- 点击后列出可执行修复项，而不是裸露分数字母。

### P1-3 主页面多 tab deep link 失效或脚本合同漂移，资源中心定位不稳定

证据：

- `validate-main-project-surface-sweep.py` 中：
  - `/projects?tab=projects` 等待 `项目管理入口 / 我的项目` 失败。
  - `?panel=team&tab=development-workshop`、`human-party`、`npc-create` 等等待 URL 变化超时。
  - 多个 tab 文本摘要实际仍是同一主页面头部内容。

影响：

- 如果是脚本旧合同，说明回归脚本无法再证明入口可用。
- 如果是真实页面未按 query 打开对应面板，用户从链接回到指定资源区会不稳定。

建议：

- 先用浏览器确认 query deep link 是否真的选中目标 tab。
- 若产品已改入口，更新 `validate-main-project-surface-sweep.py` 的 URL/marker。
- 若产品未响应 query，修复主页面 tab state 初始化。

### P1-4 协作消息池缺少二级定位栏，可能退回旧长页面

证据：

- `main-surface-sweep/surface-sweep-report-20260601-101150.json`
- issue：`协作消息池缺少二级定位栏，结构可能退回旧形态。`

影响：

- 架构合同要求专业/非 NPC 工作台保持对象索引、中心工作区、右侧动作/证据、紧凑日志。
- 消息池如果没有二级定位，用户无法快速定位待确认、回执、阻塞、历史积压。

建议：

- 给协作消息池补二级定位：待确认、等待电脑恢复、最终结果、阻塞、历史。
- 或将完整消息池收进公司层/对象证据抽屉，只在主页面保留摘要入口。

### P1-5 设备数据工作台专项脚本失效，无法覆盖终端/数据标注/图表实验细链路

证据：

```powershell
python scripts/validate-robotics-terminal-userwalk-cdp.py ...
python scripts/validate-robotics-debug-modes-cdp.py ...
```

结果：

- `validate-robotics-terminal-userwalk-cdp.py` 等待 `创建调试窗口`、`绑定真实设备` 超时。
- `validate-robotics-debug-modes-cdp.py` 等待 `/robotics` 及 debug mode 表达式超时。
- 通用 `validate-cloud-user-ux-and-isolation.mjs` 能确认 `/robotics` 非空、无横向溢出、包含 `终端 / 数据标注 / 图表实验`，但无法证明具体调试模式可点击。

影响：

- 设备数据工作台是 P1/P2 主工作台之一，但专项回归断了。
- CAN/串口/USB/ROS 只读入口和三 tab 切换没有可靠自动验收。

建议：

- 更新两条 robotics CDP 脚本的 marker 和选择器，贴合当前“设备数据工作台”文案。
- 加入桌面/移动截图、tab 点击、危险动作文案检查。

### P1-6 项目组织模型里逻辑工位为空

证据：

- `/api/projects/{project_id}/config` 当前返回：
  - `computer_nodes=5`
  - `thread_workstations=34`
  - `workstations=0`
  - `ai_providers=2`

影响：

- 架构合同定义 `Workstation` 是逻辑部门，`NPC Seat` 属于工位。
- 当前坐席存在但逻辑工位为空，会影响 NeedRouter 的同工位/跨工位、工位长、信任策略和公司层组织沙盘。

建议：

- 在主页面/公司层补“默认逻辑工位”创建或迁移。
- NeedRouter 在 `workstations=0` 时给出明确配置缺口，而不是默默退化为关键词/坐席直连。

### P1-7 旧 `.mjs` 页面/按钮全量脚本默认打本地 127.0.0.1:8010，不能直接用于云端 QA

证据：

```powershell
node scripts/validate-all-pages-walk.mjs
node scripts/validate-all-buttons.mjs
```

结果：

- 两者均默认请求 `127.0.0.1:8010/api/auth/session` 并失败。
- 没有可靠 `--help` 输出，也没有云端参数提示。

影响：

- “全面 QA”时容易误跑本地默认值，输出低价值错误。
- 旧脚本不能作为云端回归入口。

建议：

- 给脚本补 argparse / help / `--web-base` / `--api-base`。
- 默认值切到当前云端或要求显式传入，失败时输出可读提示。

## P2 问题

### P2-1 Web build 仍有 React Hook warnings

证据：

- `apps/web/app/projects/[id]/2d-upgrade/project-2d-upgrade-game.tsx`
- `apps/web/app/projects/[id]/project-playable-shell.tsx`
- `apps/web/app/projects/[id]/workbench/_components/npc-tile.tsx`

影响：

- 不阻塞构建，但会掩盖后续真实 warning。

建议：

- 独立做一次 hook dependency 清理，不和业务改动混提交。

### P2-2 文档/代码扫描仍有大量历史“人工审核/审批/最终回复/最小回执”术语

证据：

- `rg` 扫描显示大量历史文档、server action、prompt 和兼容逻辑中仍有旧词。

判断：

- 不是全部用户可见缺陷，不能机械替换。
- 已确认登录页和部分主页面文案可见，应优先改可见面。

建议：

- 分层处理：UI 文案先收口，内部 prompt/action 后续按语义确认再改。

## 已确认通过项

- 云端 web/api 对齐通过。
- 公网登录页/API health smoke 通过。
- Web production build 通过。
- 用户/项目/外部账号隔离回归通过，截图路径在 `cloud-user-ux-isolation/2026-06-01T02-10-32-148Z/`。
- 关键页面 `main / 2d / company / workbench / robotics / skill-forge / mobile / outsider` 均非空、无横向溢出、未命中当前脚本禁词。
- NPC 工作台点击 `1号 NPC` 后结构合同通过：`对话 / 我的需求 / 我的任务` 存在。
- Linux/Windows 接入命令当前验证通过：一键接入、持续接单、后台守护、桌面可见派单分层正确。
- runner 临时 fullchain 通过：创建电脑、pairing、注册 runner、heartbeat、命令入 inbox、ack、complete、可见回执、清理电脑节点。
- seat MCP server 本地验收通过：`49/49`，包括 `create_need`、`check_my_needs`、`check_my_tasks`，旧 `request_help` 仅转结构化 Need。

## 本轮未做的高风险验证

- 没有向真实 NPC 坐席发送新的人工派单，避免轰炸用户桌面。
- 没有执行 GitHub Skill import，因为会改真实 skill/知识库数据。
- 没有执行结构化 Need cloud routing 脚本，因为会创建真实 Need/Task；建议准备清理流程或专用 QA 项目后再跑。

## 下一轮最该修的闭环

优先修 `validate-computer-thread-visibility-http.py` 的失败清理和真实浏览器验证，然后修多 runner 隔离脚本使用创建响应 ID。原因很简单：这两条直接对应 P0 的“线程扫描可见”和“多电脑不抢单”，而且当前 QA 脚本本身会污染线上数据，先把验收地基修稳，再修产品 UI 才不会越测越乱。
