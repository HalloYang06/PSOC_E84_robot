# 全盘前端验收记录 20260519-160043

项目：AI 协作平台自身
云端 Web：http://106.55.62.122:3001
云端 API：http://106.55.62.122:8011
云端项目：fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd
本机项目：proj_ai_collab

原则：从登录开始，能前端点击的全部前端点击；只有启动本机/云服务器 runner、写入虚拟串口样本这类浏览器无法替代的目标机动作才使用命令，并标注原因。

## 验收矩阵

| 区域 | 验收点 | 方式 | 结果 | 证据 |
| --- | --- | --- | --- | --- |
| 登录/项目入口 | 登录云端并进入项目 | 前端 | 待验 | |
| 主页面/资源治理 | 电脑接入、NPC、工位、Skill/Git 摘要入口 | 前端 | 待验 | |
| Windows runner | 本机作为 Windows 电脑接入、扫描设备/线程 | 前端生成命令 + 本机执行 | 待验 | |
| Linux runner | 云服务器作为 Linux 电脑接入、扫描设备/线程 | 前端生成命令 + SSH 执行 | 待验 | |
| NPC 工作台 | 多 NPC 瓷砖、对话/我的需求/我的任务、线程不是 NPC | 前端 | 待验 | |
| 派工闭环 | 绑定线程/NPC，任务派到正确电脑，离线/排队状态准确 | 前端 | 待验 | |
| 设备数据工作台 | 创建窗口、绑定真实设备、终端、采集、标注、导出、图表、NPC 建议 | 前端 + 真实串口样本注入 | 待验 | |
| 能力工坊 | 工位/NPC 瓷砖，Skill/知识库/Git 管理，不与上岗包冲突 | 前端 | 待验 | |
| 公司层 | 公司运行状态一览图，部门/NPC/任务/电脑健康/阻塞 | 前端 | 待验 | |
| 旧入口收敛 | 数据工厂/AI 实验室/观测台/驾驶舱不另起主流程 | 前端 | 待验 | |
| UI 约束 | 不暴露内部词，不跳转填空，视觉接近 NPC 工作台 | 前端截图 | 待验 | |

## 过程记录


### 2026-05-19 16:10-16:48 云端前端验收进展

- 登录：从云端 `/login` 开始，因 in-app browser 批量输入受限，使用逐键键盘输入完成登录，进入 `2d-upgrade`。登录后业务动作均在可见云端页面完成。
- 主页面：云端显示五个一级入口：主页面资源中心、NPC 工作台、设备数据工作台、能力工坊、公司层；截图见 `artifacts/full-platform-frontdoor-20260519/01-cloud-main.png`。
- 电脑接入：在主页面点击“电脑”进入电脑接入面板，前端生成本机 Windows 和云端 Linux 的配对命令。用户自己运行终端命令页面文案明确不需要审核，NPC 代操作终端才进待审。
- Windows runner：从页面为 `codex-local-win-0518133234` 生成令牌并执行页面给出的 PowerShell 命令。本机 runner 注册成功，前端刷新显示 `Codex 本机 Windows 验收 13:32:34 / 常驻接单 / 16 条线程 / 心跳 2026-05-19T08:31:42Z`。
- Linux runner：从页面为 `cloud-linux-main` 生成令牌并通过 SSH 在云服务器执行页面给出的 Bash 命令。前端刷新显示 `云端 Linux 主机 / 常驻接单 / 2 条线程 / 心跳 2026-05-19T08:35:50Z`。
- 设备数据工作台：云端 `/robotics` 左栏只显示用户创建的调试窗口，真实扫描设备只在“创建调试窗口”的下拉里索引，不直接铺到左栏。当前有 67 个真实设备可绑定，包含云端 Linux 串口/USB 和本机 Windows com0com/USB。
- 调试窗口：前端创建 `Windows COM30` 串口窗口，绑定 `Codex 本机 Windows 验收 13:32:34 / COM30`，波特率下拉为 115200，协助 NPC 绑定 `1号 NPC`。创建后左栏窗口数从 0 变 1，中间出现单个瓷砖。
- 终端分界：窗口终端显示用户终端输入框和 `NPC 代操作待审` 输入框分离；用户提交 `status` 后没有出现待审卡，符合“用户自己输入不审核”。
- 采集闭环：从前端点击“开始采集”，终端显示 `[capture:running]`，runner 日志显示下载 `run-device-capture-command.py` 并处理采集命令；前端点击“停止并生成片段”后，数据标注和图表实验计数均从 0 变 1，并显示“已生成采集片段”。
- 数据标注：可选择采集片段、自由勾选变量、填写标注规则/目标/人工标签、选择导出格式（CSV/JSONL/Parquet 清单/NPZ 清单/项目清单），并有 `NPC 预标注` 入口。
- 图表实验：可选择采集片段、横轴变量、多纵轴、目标值、PID/FOC/传感器/总线类型，并有 `请求 NPC 调参建议` 入口。

当前缺口/待修：

- 设备数据工作台的数据标注和图表证据区仍直接显示 `device-captures/...`、`artifacts/...` 路径。按 UI 约束应改为“预览文件 / 采集证据 / 下载片段”等用户词，不直接露路径。
- 虚拟串口样本注入到 COM31 时本机 Python 写入进程卡住，已停止该写入进程；本轮确认了采集命令、后台 worker 和片段索引闭环，但真实样本内容还需重新用不阻塞的串口写入方式补验。
- PowerShell `Start-Process -ArgumentList` 在 RunnerName 含中文/空格时会拆参导致 `Take/CodexMaxAgeDays` 参数绑定错误；页面生成的 runner 名 `codex-local-win-0518133234 Runner` 可运行。后续脚本/文档应提示整条命令直接粘贴运行，自动化执行时要用正确 quoting。

### 2026-05-19 17:06 设备采集根因定位与本机实采复验

- 先按合同重跑云端 Web/API 对齐：通过，Web/API 均为 `82b435e6976c`。
- 阅读 `ai-collab-architecture-executor` skill 和总方案，确认本轮不另起炉灶，只在现有设备数据工作台 / runner 采集链路上补缺口。
- runner 采集单元验证：`python -m pytest apps/runner/tests/test_relay_prompt_inbox.py -k "robotics_capture or preview_summary or preview_points or linux_scanned" -q`，8 项通过，说明后台采集会话、停止收口、summary 和图表点生成逻辑可用。
- 本机真实串口复验：用 com0com `COM30`/`COM31`，通过同一份 `scripts/run-device-capture-command.py` 启动 `COM30` 后台采集，再向 `COM31` 写入 40 行 `time/motor.current/motor.velocity/bus.voltage` 样本，停止采集后得到 `sample_count=40`、`byte_count=2680`，并生成 `preview_summary` 与 `preview_points`。证据目录：`artifacts/serial-capture-manual-20260519/`。
- 根因判断：云端前端创建的调试窗口 id 为 `电脑:serial:COM30` 形式，用于区分不同电脑资源；runner 采集器真实需要的是 `serial:COM30`。旧版本把前端窗口 id 直接作为采集命令 `interface_id` 下发，目标电脑无法解析真实端口，容易得到 0 样本。
- 本地修复：设备数据工作台资源对象新增独立 `runnerInterfaceId`，前端表单保留窗口 id 做瓷砖/消息匹配，同时把 `runner_interface_id` 传给 server action；`robotics.capture.start/stop` 下发给 runner 时使用真实扫描接口 id。已跑 `npx tsc -p apps/web/tsconfig.json --noEmit --pretty false` 通过。
- 总方案同步：补充“调试窗口 ID 与 runner 真实接口 ID 必须分离”的设备数据工作台合同，避免后续实现再把用户对象 id 当真实端口。

待云端复验：

- 部署本地修复后，从云端页面重新创建/打开 Windows COM30 调试窗口，前端点击开始采集，使用本机 COM31 注入样本，前端点击停止，确认数据标注 tab 和图表实验 tab 显示非 0 样本、可选真实数值变量并绘制曲线。

### 2026-05-19 17:12-17:38 云端设备采集前端闭环复验

- 部署 `5b280057` 后，云端对齐通过；云端设备数据工作台继续保持“左栏只显示用户创建窗口，真实设备只在创建下拉里索引”的结构。
- 从云端可见页面打开 `Windows COM30` 调试瓷砖，前端点击“开始采集”。本机 Windows runner 下载并执行 `run-device-capture-command.py`，worker payload 中真实接口已变为 `serial:COM30`，不再是带电脑前缀的窗口 ID。
- 通过本机 `COM31` 向 com0com 对端写入 30 行真实样本：`motor.current`、`motor.velocity`、`bus.voltage`。浏览器无法替代这个目标机串口注入动作，因此只这一步使用本机终端。
- 前端点击“停止并生成片段”后，目标机 runner 生成 `manifest.json` 和 `preview.jsonl`，本机证据目录：`D:\ai合作产品\ai-collab-runner\device-captures\fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd\codex-local-win-0518133234\serial-COM30\capture-43e51a924939\`。结果为 `sample_count=30`、`byte_count=1710`，包含 `preview_summary` 和 `preview_points`。
- 发现并修复 runner complete 422：旧接入脚本把完整 JSON 塞进 `note`，超过 API 4000 字符限制；已改为短摘要，结构化 `runner_result` 仍走 metadata。Windows/Linux 接入脚本均已修复并部署为 `49854926`。
- 发现并修复图表预览关联：同一 `capture_id` 的 start 回执会覆盖 stop 回执，导致图表 tab 只显示“等待低频预览点”。已改为优先保留 stop/有样本/有预览点的结果，并部署为 `94fc7654`。
- 云端最终用户视角结果：终端 tab 显示 `[capture:done] 已收到 30 个样本`；数据标注 tab 显示两个片段、可选择 `motor.current` / `motor.velocity` / `bus.voltage` 等真实变量；图表实验 tab 显示 `motor.current / motor.velocity / bus.voltage` 预览波形，证据区显示“已回传 30 个样本 / 1710 bytes · 预览文件已生成 · 等待配置仓库同步”。
- 仍需后续补齐：为该 Windows runner 配置 `RUNNER_DEVICE_DATA_REPO` 和可选推送，完成“采集停止后写入 GitHub 并清理本机缓存”的长期存储闭环；当前云端显示“等待配置仓库同步”是准确状态，不是假装已进 GitHub。
