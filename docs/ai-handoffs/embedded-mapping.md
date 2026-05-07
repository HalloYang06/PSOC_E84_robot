# AI-4 嵌入式机器人项目真实需求映射

## 身份

- 角色: AI-4
- 职责: 嵌入式真实需求映射

更新时间：2026-04-20

目标：把“开发嵌入式机器人项目”的真实研发动作，正确翻译成经营游戏里的机制，并且保持平台既有的任务、Runner、交接、审批、构建、交付语义不变形。

适用范围：嵌入式、机器人、ROS、开发板、串口、固件、驱动、整机联调、硬件实验记录类项目。

不负责范围：地图美术、HUD、数值平衡、主循环重写。

## 协作执行约束

本角色后续继续执行时，统一遵守以下约束：

1. 先读 `多AI并行开发分工说明-2026-04-20.md`，再读 `AI协作平台开发文档.md`。
2. 不直接推 `main`。
3. 不改超出 AI-4 负责范围的文件；本角色默认只维护嵌入式真实需求映射相关文档或配置。
4. 必须维护自己的 handoff 文档，即 `docs/ai-handoffs/embedded-mapping.md`。
5. 通过 Git 和文档交流，不依赖长聊天记录做交接。
6. 临时 demo、验证开关、临时兜底逻辑在任务收尾前必须删除。
7. 涉及高风险硬件边界的设计变更，必须继续保留人工确认门槛，不得在后续迭代中被弱化。

## 设计原则

1. 游戏地图只能做研发流程的空间化表达，不能把真实研发边界美化成“自动一键完成”。
2. 每个建筑、资源和循环都必须能回指到真实平台实体，例如 requirement、task、agent、runner、handoff、approval、build、delivery、audit log。
3. 嵌入式项目和纯 Web 项目最大的差异，不是 UI，而是硬件风险、设备占用、实验记录、人工确认门槛。
4. 高风险硬件动作只能被映射为“待人工确认的门槛”或“待人工执行的实验步骤”，不能被映射为 AI 自动动作。
5. 好玩只能来自流程更易理解、更易协作，不能来自掩盖风险。

## 真实研发动作 -> 游戏机制映射表

| 真实研发动作 | 游戏内主要建筑/区域 | 游戏机制映射 | 资源/状态映射 | 限制与说明 |
| --- | --- | --- | --- | --- |
| 收需求 | 需求信箱 / 会议室 | 新需求进入收件箱，可被整理、标注类型、补充约束 | 需求卡、优先级、来源、验收条件、风险标签 | 不能直接把“口头想法”当已开工任务，必须先结构化 |
| 需求澄清 | 会议室 / 产品办公室 | 发起问答回合，补齐接口、硬件型号、边界条件 | 待澄清项、缺失字段、决策记录 | 未澄清完成的需求不能自动播种到任务田 |
| 需求拆解 | 任务大厅 / 任务田块 | 把一个需求拆成可执行任务，形成依赖链 | 任务卡、依赖、模块、验收标准、风险级别 | 拆解后才允许派发给 AI 或电脑 |
| 任务分级 | 任务大厅 | 任务按 P0/P1/P2 或风险等级显示不同标记 | 优先级、风险级别、阻塞状态 | 高风险任务默认进入待审批或待人工确认状态 |
| 指派 AI | AI 工位区 | 把任务卡派给特定 AI 工位，AI 开始规划或编码 | AI 负载、上下文健康、token 预算、成功率 | AI 工位只能处理授权目录和授权动作 |
| 指派电脑 | 电脑车间 / Runner 机房 | 把任务绑定到具备能力的 Runner 节点 | Runner 在线状态、OS、工具链、能力标签 | 必须按 capability 调度，不能把 ROS/embedded-build 任务派给不具备能力的节点 |
| Runner 执行 | 电脑车间 / 代码车间 | Runner 领取任务并在独立工作区执行构建、测试、脚本 | 工作区、日志、执行状态、退出码 | Runner 不是自由 shell；默认只做受控命令 |
| 建分支 | 代码车间 / 交付工坊 | 为任务生成任务分支，作为播种后进入开发地块 | branch、commit、diff、关联 task_id | 没有任务分支就不能把开发状态标为“已播种” |
| 文件边界控制 | 仓库围栏 / 工位权限牌 | 每个 AI/Runner 只可进入特定目录、模块、文件范围 | 可读目录、可写目录、禁区目录 | 文件边界是权限模型，不是装饰属性 |
| AI 生成代码或文档 | AI 工位区 | 工位持续产出代码、测试建议、文档草案 | changed_files、summary、risk_notes | 产出必须绑定具体任务，不能做无主改动 |
| 构建 | 代码车间 / 编译炉 | 消耗 Runner 能力执行编译、lint、单测、集成测试 | build 状态、产物、失败摘要、耗时 | 构建失败应回到任务田块形成阻塞，不应被包装成“随机事件” |
| 仿真 / 离线验证 | 硬件实验楼中的仿真台 | 在不接触真机的前提下做软件侧验证 | 仿真日志、录像、测试报告 | 仿真成功不等于可直接上真机 |
| 上传日志 | 档案室 / 实验记录台 | 串口日志、照片、截图、波形、错误摘要沉淀成记录 | 实验记录卡、附件、时间戳、设备编号 | 记录是后续审批和交接依据，不能省略 |
| 交接 | 交接站 / 聊天小院 | 生成 handoff 包并指定下一个 AI 或人工接手 | handoff 包、摘要、未决问题、相关文件 | 交接不是聊天气泡，必须是结构化包 |
| 阻塞上报 | 急救站 / 风险灯塔 | 任务因缺设备、缺需求、缺权限、编译失败而挂起 | blocked_reason、需要谁处理、恢复条件 | 阻塞必须可追溯，不能被隐藏成普通待机 |
| 人工审批 | 审批门岗 / 老板办公室 | 对高风险动作、发布动作、回滚动作做显式批准 | approval 单、审批人、备注、结论、时间 | 审批是硬门槛，不是加成 buff |
| 真机准备 | 硬件实验楼前置检查台 | 检查固件版本、电源、线束、限位、急停、环境 | 检查清单、设备占用状态、安全标签 | 未通过检查不得进入任何真机步骤 |
| 烧录 / 刷机 | 硬件实验楼 | 映射为“待人工执行实验步骤”而不是自动命令 | 待确认烧录单、目标板卡、版本号、回退版本 | AI 可生成步骤和校验项，但不能自动执行 |
| 串口写入 / 参数改写 | 硬件实验楼控制台 | 映射为人工确认后的受控步骤 | 参数变更单、旧值/新值、影响范围 | 属于高风险动作，不能默认为 Runner 自动执行 |
| 控制电机 / 机械臂 / 执行器 | 硬件实验区安全围栏内 | 映射为需要双确认的人工触发实验 | 危险等级、设备状态、现场确认 | 绝不能被游戏化成“点击建筑立即运行” |
| 整机联调 | 硬件实验楼 / 联调跑道 | 多任务、多设备、多日志汇聚的阶段性联动 | 设备占用、联调阶段、实验批次、结果 | 联调是稀缺资源循环，不应与普通软件任务等价 |
| 人工验收 | 审批门岗 / 交付工坊 | 人工根据验收单确认任务是否可合并、可发布、可继续实验 | 验收结论、问题列表、签字人 | 验收失败要回流到任务系统 |
| 合并代码 | 交付工坊 / 代码车间 | 审查通过后合并分支，更新主线状态 | merge 状态、review 记录、release note 草稿 | 未通过审查不得前进到交付态 |
| 发布构建产物 | 交付工坊 | 输出固件包、镜像、版本快照、交付说明 | artifact、版本号、校验和、发布时间 | 交付必须绑定已批准版本，不是从任意任务直接产出 |
| 回滚 | 急救站 / 审批门岗 | 映射为受控的恢复动作 | rollback 目标版本、原因、影响范围 | 回滚也属于高风险动作，需要审批与审计 |
| 审计留痕 | 档案室 / 审计柜 | 对任务、审批、Runner、交接、实验全过程留痕 | audit log、操作者、时间、对象 | 审计是底层系统真值，不是可选收集品 |

## 核心资源映射

| 真实研发资源 | 游戏内资源表示 | 正确语义 |
| --- | --- | --- |
| 需求 | 需求卡 / 信件 | 待澄清或待拆解的真实输入 |
| 任务 | 田块中的任务卡 | 可执行工作单元，不是装饰作物 |
| AI | 工位员工 / 可调度成员 | 具备角色、权限、上下文和预算的执行者 |
| Runner / 电脑 | 机房节点 / 车间设备 | 受控执行节点，不是无限产能建筑 |
| Git 分支 | 生长中的任务枝条 / 交付线 | 任务隔离边界 |
| 日志 | 档案 / 实验记录 | 真实追溯证据 |
| 审批额度 | 门岗通行令 | 显式人工许可，不是货币 |
| 设备占用 | 实验台占位状态 | 稀缺现实资源 |
| Token / 预算 | AI 工位能耗 / 预算表 | 成本与吞吐约束 |
| 上下文健康 | 工位负荷条 | 影响 AI 接手质量与交接必要性 |

## 核心循环映射

### 1. 软件主循环

收需求 -> 澄清 -> 拆任务 -> 指派 AI -> 指派 Runner -> 分支开发 -> 构建测试 -> 审查 -> 合并 -> 交付

游戏中应体现为：

- 需求信箱产生可处理的需求卡。
- 任务大厅把需求卡拆成多个田块任务。
- AI 工位负责产出，电脑车间负责执行。
- 代码车间返回 build、test、diff 和失败摘要。
- 交付工坊只接收已审查、已批准的产物。

### 2. 嵌入式扩展循环

收需求 -> 拆任务 -> 软件侧实现 -> 仿真验证 -> 人工审批 -> 真机准备检查 -> 人工执行硬件动作 -> 上传实验记录 -> 人工验收 -> 是否继续迭代

游戏中应体现为：

- 仿真台和真机实验台是两个阶段，不是一个按钮。
- 真机动作前必须经过审批门岗。
- 实验结果要回写到档案室，再反哺任务大厅和审批门岗。

### 3. 交接循环

上下文变重 / 任务跨模块 / 设备切换 / 班次变化 -> 生成 handoff 包 -> 指定接手 AI 或人工 -> 接手确认 -> 继续执行

游戏中应体现为：

- 交接站是流转枢纽，不是聊天装饰点。
- 交接包必须带摘要、相关文件、未决问题、风险说明、下一步建议。

## 建筑与机制建议

### 需求信箱

- 只负责收集、分类、澄清。
- 输出物必须是结构化 requirement。
- 没有验收条件的需求不能直接进入开发。

### 任务田块

- 任务从“播种”到“成长”对应 draft、planning、running、testing、reviewing。
- 阻塞态应明显枯黄或挂警示，而不是继续假装成长。
- 高风险任务卡必须带人工确认标记。

### AI 工位

- 展示 AI 职责、当前任务、上下文健康、预算消耗、是否等待别人。
- AI 可以建议、生成、分析、总结、移交。
- AI 不可以越过审批门岗直接碰真机。

### 电脑车间 / Runner 机房

- 展示 Runner 在线、能力标签、当前工作区、执行状态。
- 可执行构建、测试、日志采集、受控脚本。
- 不能被表现成“拥有电脑就能自动搞定硬件”。

### 硬件实验楼

- 必须拆成仿真区、检查区、真机区。
- 真机区所有动作都要经过审批门岗和人工确认。
- 重点显示设备占用、安全等级、最近实验记录、回退版本。

### 审批门岗

- 负责所有高风险动作放行。
- 审批单必须记录对象、原因、影响、回退方案、执行人。
- 未审批通过时，相关建筑只能显示“待人工处理”，不能继续推进。

### 交付工坊

- 只处理已经过审查、通过验收的代码或构建产物。
- 固件包、镜像、版本快照、发布说明都在这里形成。
- 不应绕过代码审查和审批直接出包。

### 档案室 / 交接站

- 档案室沉淀知识、日志、实验记录、决策。
- 交接站沉淀 handoff 包和接手记录。
- 二者都是研发真值源，不能只做剧情文本。

## 高风险动作人工确认清单

以下动作必须保留人工确认门槛，且默认不允许 AI 或 Runner 自动执行：

1. 烧录固件到真实开发板、控制板、机器人主控。
2. 通过串口、CAN、I2C、SPI、网口等接口向真机写入会改变状态的命令。
3. 控制电机、舵机、机械臂、夹爪、履带、轮组等执行器动作。
4. 上电、断电、切换供电、解除限位、旁路安全保护。
5. 修改 PID、限位、电流阈值、速度阈值、力矩阈值等关键控制参数。
6. 运行可能导致碰撞、夹伤、过热、过流、跌落的整机联调步骤。
7. 回滚或替换真实设备上的关键固件、引导程序、配置分区。
8. 对现场设备执行复位、校准、归零、自检等可能引起物理动作的命令。
9. 删除、覆盖或清空真实设备上的关键日志、配置或标定数据。
10. 任何平台无法确认“当前是否连接真实硬件”的动作。

每个高风险动作在游戏里都应至少经过以下门槛：

1. 形成结构化审批单。
2. 显示影响设备、目标版本、执行人、回退方案。
3. 人工确认现场条件已满足。
4. 人工触发执行。
5. 上传执行结果和实验记录。

## 不能做错位映射的红线

1. 不能把“审批”映射成可有可无的奖励按钮。审批是阻断危险动作的硬门。
2. 不能把“Runner”映射成拥有后就能自动完成所有研发动作的万能建筑。Runner 只是受控执行节点。
3. 不能把“AI 工位”映射成会直接控制真机的角色。AI 只能辅助，不能替代现场责任人。
4. 不能把“硬件实验楼”映射成纯展示区。它必须承载设备占用、实验记录、风险提示和人工确认。
5. 不能把“任务成长”映射成固定时间自动成熟。真实任务推进依赖构建结果、审查结果、审批结果和外部阻塞。
6. 不能把“交接”映射成普通聊天。交接必须是结构化 handoff 包。
7. 不能把“日志”映射成可丢弃的背景文本。日志和实验记录是追责与复盘依据。
8. 不能把“构建成功”映射成“真机可运行”。嵌入式里构建、仿真、真机验证是三层不同语义。
9. 不能把“高风险硬件动作”映射成一键自动执行的爽点。这会破坏平台的安全底线。
10. 不能把“人工确认”弱化成点一次确认框就结束。至少要保留动作对象、执行人、影响范围和回退方案。

## 对主循环的明确机制建议

本轮不改主循环实现，但后续机制应满足以下约束：

1. 所有嵌入式任务都应带 `risk_level` 与 `hardware_touch` 标记。
2. 当 `hardware_touch=true` 且动作属于高风险类别时，任务流必须经过审批门岗。
3. Runner 调度必须读取 capability，例如 `embedded-build`、`ros`、`serial-log`，而不是仅按在线状态派发。
4. 交付工坊应区分软件产物和硬件实验结果，不能混成同一种“完成奖励”。
5. 硬件实验楼应区分“仿真通过”“待真机确认”“人工已执行”“实验失败待复盘”四种关键状态。
6. 交接站必须能显示“为什么换手”“未决问题”“相关设备/文件”“建议接手角色”。

## 与现有后端 schema 对齐的增量建议

基于当前仓库里已有的 `tasks`、`approvals`、`lab`、`handoffs` schema，推荐优先做增量扩展，而不是新开系统。

### 1. `tasks` 模块建议补充字段

当前已有：`priority`、`status`、`branch`、`assignee_agent_id`、`acceptance_criteria`。

建议新增：

| 字段 | 示例 | 用途 |
| --- | --- | --- |
| `risk_level` | `H0` / `H1` / `H2` / `H3` / `H4` | 标记任务整体风险等级 |
| `hardware_touch` | `true` / `false` | 是否涉及真实硬件接触 |
| `hardware_action_type` | `firmware_flash` | 标记高风险动作类别 |
| `requires_human_approval` | `true` | 是否必须经过审批门岗 |
| `required_runner_capabilities` | `["embedded-build","ros"]` | Runner 调度约束 |
| `target_devices` | `["mcu-main-board","arm-controller"]` | 影响设备范围 |
| `simulation_required` | `true` | 是否要求先过仿真 |
| `rollback_plan` | 文本或结构化对象 | 高风险动作回退方案 |

推荐规则：

1. 当 `hardware_touch=true` 且 `risk_level>=H3` 时，自动要求审批。
2. 当任务存在 `hardware_action_type` 时，不允许直接标记为“已完成”，必须关联实验记录或审批结论。
3. 当设置了 `required_runner_capabilities` 时，调度时不能仅按 Runner 在线状态分发。

### 2. `approvals` 模块建议补充字段

当前已有：`level`、`action`、`notes`。

建议新增：

| 字段 | 示例 | 用途 |
| --- | --- | --- |
| `approval_template` | `embedded.firmware_flash.v1` | 区分审批模板 |
| `risk_summary` | `刷写主控板固件，存在无法启动风险` | 审批页直观风险摘要 |
| `impact_devices` | `["mcu-main-board"]` | 审批对象范围 |
| `execution_owner` | `human:zhangsan` | 指定谁执行现场动作 |
| `rollback_plan` | `保留 v1.2.3 固件回刷路径` | 回退策略 |
| `preflight_checklist` | 数组 | 审批前必填检查项 |
| `required_confirmations` | `2` | 单人或双人确认 |
| `environment_ready` | `false` | 现场环境是否确认完毕 |

推荐规则：

1. `lab` 发起审批，`approvals` 审核，`audit` 留痕，保持现有边界不变。
2. 对 H3/H4 动作，审批单不应只有一段备注，必须有结构化检查项与回退方案。
3. 模板优先做成枚举值和 payload 结构，不先做复杂工作流引擎。

### 3. `lab` 模块建议补充字段

当前已有：检查项、审批请求、状态汇总链路。

建议新增：

| 字段 | 示例 | 用途 |
| --- | --- | --- |
| `device_id` | `arm-controller-01` | 关联实验设备 |
| `experiment_type` | `real_hardware` / `simulation` | 区分仿真与真机 |
| `experiment_stage` | `preflight` / `executing` / `observing` / `reviewing` | 实验阶段 |
| `operator_user_id` | 用户 ID | 现场执行人 |
| `observer_user_id` | 用户 ID | 第二确认人或观察人 |
| `evidence_files` | 文件列表 | 串口日志、照片、视频、波形 |
| `firmware_version` | `v1.2.4-rc1` | 实验对应版本 |
| `previous_version` | `v1.2.3` | 回退版本 |
| `result_summary` | 文本 | 实验结果摘要 |
| `next_decision` | `retry` / `rollback` / `approve_next_step` | 实验后的下一步决策 |

推荐规则：

1. 仿真记录和真机记录都落 `lab`，但必须通过 `experiment_type` 区分。
2. 真机记录默认要求 `operator_user_id`，不能只记录 AI 或 Runner。
3. 没有证据文件或观察结论的高风险实验，不应被视作可验收。

### 4. `handoffs` 模块建议补充字段

当前已有：`summary`、`open_questions`、`next_steps`、`linked_approval_ids`、`context_health`。

建议新增：

| 字段 | 示例 | 用途 |
| --- | --- | --- |
| `risk_summary` | 文本 | 当前高风险点摘要 |
| `hardware_context` | 对象 | 设备、版本、实验状态 |
| `required_checks` | 数组 | 接手前必须确认的事项 |
| `evidence_refs` | 文件列表 | 实验日志和图片引用 |
| `handoff_kind` | `ai_to_human` / `human_to_ai` / `ai_to_ai` | 交接类型 |
| `recommended_role` | `embedded-debugger` | 建议接手角色 |
| `unsafe_to_continue` | `true` / `false` | 是否禁止未确认继续执行 |

推荐规则：

1. 一旦交接涉及真实设备，handoff 包里必须写清设备状态和风险摘要。
2. `unsafe_to_continue=true` 时，接手者只应先读记录和确认清单，不能直接继续动作。
3. 交接结构要服务于 Git 与文档协作，不能依赖长聊天记录补充背景。

## 模板与配置样例

本轮补充了一个配置样例文件，供后续实现审批模板、实验记录模板和 handoff payload 时复用：

- [embedded-config-examples.yaml](/D:/ai合作产品/docs/ai-handoffs/embedded-config-examples.yaml)

它不是主系统配置，只是 AI-4 产出的契约草案，目的是让后续实现少走弯路。

## 推荐后续落地项

1. 给 requirement、task、approval、handoff、runner capability 增加一组服务于嵌入式场景的字段和枚举。
2. 给项目页的建筑交互补充“高风险待审批”“待人工执行”“实验记录已回传”这类明确状态。
3. 在硬件实验楼的交互说明里明确区分 AI 可做与人工必须做的边界。
4. 为嵌入式任务建立统一的审批模板和实验记录模板。

## 本轮新增内容

1. 完成了嵌入式真实研发动作到游戏机制的系统映射。
2. 固化了高风险硬件动作的人审红线。
3. 补充了与现有后端 schema 对齐的增量字段建议。
4. 产出了可复用的嵌入式审批/实验/交接配置样例。

## AI-4 交接状态

### 已修改文件

1. `docs/ai-handoffs/embedded-mapping.md`
2. `docs/ai-handoffs/embedded-config-examples.yaml`

## 本轮更新

- 当前阶段: 按多 AI 并行协作规则切换到 Boss 调度与文档协作模式
- 已完成:
  - 已重读 `多AI并行开发分工说明-2026-04-20.md`
  - 已重读 Boss 调度板并确认 AI-4 当前状态为“进行中”
  - 已按新要求确认后续只通过 Git 与 `docs/ai-handoffs/` 留痕协作
  - 已确认 AI-4 继续只负责真实需求映射，不越界改主循环、地图美术、数值平衡、HUD
- 修改文件:
  - `D:\ai合作产品\docs\ai-handoffs\embedded-mapping.md`
- 当前验证:
  - 已核对 Boss 调度板对 AI-4 的下一步指令为“把映射继续压成最小可落地字段和审批模板”
  - 已核对 AI-4 自身 handoff 文档仍包含身份、范围、验证、下一步、风险
- 下一步:
  - 继续在 AI-4 范围内，把嵌入式映射压实成更小的后端字段清单或审批模板建议
  - 如需改动跨角色模块或涉及高风险门槛实现，先交由 Boss 判断
- 需要他人接力:
  - 当前无需他人立即接力，但后续若进入后端真实落地，应由对应后端角色接手实现
- 风险:
  - `ai-thread-report-template / boss-intake-format` 当前以 Boss 调度板中的统一入口形式存在；如需中文说明，应写作“`ai-thread-report-template`（AI 线程汇报模板）/ `boss-intake-format`（Boss 收件格式）”
  - 若 AI-4 越界去改 UI 或主循环，会破坏当前多 AI 分工边界

## 本轮更新（Boss 继续推进后）

- 当前阶段: AI-4 按 Boss 指令把嵌入式研发映射压成最小可落地字段与审批模板
- 已完成:
  - 追加“第一阶段最小可落地清单”
  - 将 `tasks / approvals / lab / handoffs` 收口为第一阶段最小字段集
  - 将审批模板收口为 3 个第一阶段必做模板：
    - `embedded.firmware_flash.v1`
    - `embedded.parameter_write.v1`
    - `embedded.actuator_motion.v1`
  - 明确了后端最小落地顺序：`tasks -> approvals -> handoffs -> lab`
- 修改文件:
  - `D:\ai合作产品\docs\ai-handoffs\embedded-mapping.md`
- 当前验证:
  - 已对照当前 `apps/api/app/modules/tasks/schemas.py`
  - 已对照当前 `apps/api/app/modules/approvals/schemas.py`
  - 已对照当前 `apps/api/app/modules/lab/schemas.py`
  - 已对照当前 `apps/api/app/modules/handoffs/schemas.py`
  - 已确认本轮仅做 AI-4 文档增量，没有越界修改其他角色模块
- 下一步:
  - 若继续留在 AI-4 范围内，可把这份最小字段清单再压成“后端实现任务拆解单”
  - 若进入真实 schema 落地，应由后端角色按此文档接手实现
- 需要他人接力:
  - 后端角色后续可直接按本节的第一阶段清单实现 schema 增量
- 风险:
  - 当前建议已足够小，但若直接进入实现，仍需 Boss 决定由哪个后端角色接手
  - `lab` 模块现有结构偏状态链与审批请求，实验记录结构可能需要最小新 schema 或 payload 扩展

## 本轮更新（Boss 再次继续推进后）

- 当前阶段: AI-4 把最小字段进一步压成最小 payload 示例
- 已完成:
  - 为 `tasks` 增加最小 create/read payload 示例
  - 为 `approvals` 增加最小 create/read payload 示例
  - 为 `handoffs` 增加最小 create/read payload 示例
  - 为 `lab` 增加最小实验记录 payload 示例
  - 明确了 `lab` 第一阶段若不新开实体，可先用结构化 `payload` 过渡
- 修改文件:
  - `D:\ai合作产品\docs\ai-handoffs\embedded-mapping.md`
- 当前验证:
  - 已对照现有 `tasks / approvals / handoffs / lab` schema，确认 payload 示例仍是增量思路
  - 已确认本轮没有越界修改前端或其他角色模块
- 下一步:
  - 若继续停留在 AI-4 范围，可整理成“后端实现任务拆解单”
  - 若进入实现，应由后端角色直接照本节 payload 示例落地
- 需要他人接力:
  - 后端角色可直接基于本节 payload 示例开始定义第一阶段接口
- 风险:
  - `lab` 的最小 payload 过渡方案能最快落地，但长期仍建议收敛为稳定实验记录 schema

### 当前验证

1. 已核对文档路径存在且可读取。
2. 已核对配置样例文件落盘成功。
3. 本轮为文档与配置草案交付，未改前端界面与后端接口，因此未进行界面截图验证。

### 建议下一步

1. 由后端实现方按本文件的字段建议补 `tasks`、`approvals`、`lab`、`handoffs` schema。
2. 由项目页交互实现方把 `pending_human_approval`、`pending_real_hardware`、`experiment_record_uploaded` 三类状态接到建筑提示。
3. 由审批与实验流实现方优先落 `embedded.firmware_flash.v1` 与 `embedded.actuator_motion.v1` 两个模板。

## 第一阶段最小可落地清单

这轮进一步收口后，推荐把 AI-4 的映射先压成“第一阶段就能落”的最小数据层增量，而不是一次做完整工作流引擎。

原则：

1. 只动 `tasks`、`approvals`、`lab`、`handoffs` 的增量字段。
2. 先把高风险动作的人审门槛做成数据约束。
3. 不新开系统，不做复杂审批编排，不做自动硬件执行。

### 第一阶段推荐枚举

`risk_level`

```text
H0 纯文档/无运行风险
H1 普通代码与配置改动
H2 影响构建、接口、联调路径
H3 涉及真实硬件写入或高风险实验准备
H4 涉及真实执行器动作、电源、刷机、关键参数写入
```

`hardware_action_type`

```text
none
firmware_flash
parameter_write
actuator_motion
power_operation
calibration
rollback
```

`experiment_type`

```text
simulation
bench_test
real_hardware
```

`handoff_kind`

```text
ai_to_ai
ai_to_human
human_to_ai
```

### `tasks` 最小落地字段

第一阶段建议只加这 6 个字段：

| 字段 | 是否第一阶段必加 | 说明 |
| --- | --- | --- |
| `risk_level` | 是 | 统一风险等级入口 |
| `hardware_touch` | 是 | 区分纯软件任务与真机任务 |
| `hardware_action_type` | 是 | 决定是否触发审批模板 |
| `requires_human_approval` | 是 | 显式卡住高风险动作 |
| `required_runner_capabilities` | 是 | 对齐 Runner 真能力约束 |
| `target_devices` | 是 | 设备范围追溯基础 |

第一阶段规则：

1. `hardware_touch=true` 且 `risk_level` 为 `H3/H4` 时，自动要求审批。
2. `hardware_action_type != none` 时，任务不能直接走到“已完成”，必须关联审批或实验结果。
3. 有 `required_runner_capabilities` 时，不能只按在线状态派发 Runner。

### `approvals` 最小落地字段

第一阶段建议只加这 6 个字段：

| 字段 | 是否第一阶段必加 | 说明 |
| --- | --- | --- |
| `approval_template` | 是 | 区分高风险动作模板 |
| `risk_summary` | 是 | 审批页一眼看懂风险 |
| `impact_devices` | 是 | 影响设备范围 |
| `execution_owner` | 是 | 谁负责现场执行 |
| `rollback_plan` | 是 | 没回退方案就不应放行 |
| `preflight_checklist` | 是 | 防止审批变成空按钮 |

第一阶段规则：

1. `lab` 发起审批，`approvals` 审核，`audit` 留痕。
2. H3/H4 动作不允许只有自由文本备注，必须有结构化检查项。
3. 第一阶段不做复杂工作流引擎，先做模板枚举和结构化 payload。

### `lab` 最小落地字段

第一阶段建议只加这 7 个字段：

| 字段 | 是否第一阶段必加 | 说明 |
| --- | --- | --- |
| `device_id` | 是 | 设备追溯入口 |
| `experiment_type` | 是 | 区分仿真与真机 |
| `experiment_stage` | 是 | 区分预检/执行/观察/复盘 |
| `operator_user_id` | 是 | 现场执行责任人 |
| `evidence_files` | 是 | 串口日志/照片/视频/波形证据 |
| `firmware_version` | 是 | 对齐版本追溯 |
| `result_summary` | 是 | 供审批/交接/验收读取 |

第一阶段规则：

1. 真机实验默认必须记录 `operator_user_id`，不能只记 AI 或 Runner。
2. 没有 `evidence_files` 的高风险实验不能算闭环。
3. `experiment_type=simulation` 不得等同于真机通过。

### `handoffs` 最小落地字段

第一阶段建议只加这 5 个字段：

| 字段 | 是否第一阶段必加 | 说明 |
| --- | --- | --- |
| `risk_summary` | 是 | 交接第一眼看到风险 |
| `hardware_context` | 是 | 设备/版本/实验状态上下文 |
| `required_checks` | 是 | 接手前必查事项 |
| `handoff_kind` | 是 | 区分 AI 交 AI / AI 交人 |
| `unsafe_to_continue` | 是 | 未确认前禁止继续执行 |

第一阶段规则：

1. 一旦交接涉及真实设备，必须写设备状态和风险摘要。
2. `unsafe_to_continue=true` 时，接手者先读记录和确认清单，不能直接继续动作。
3. 交接必须服务于 Git 与文档协作，不能依赖长聊天记录补背景。

## 第一阶段最小审批模板

优先只做这 3 个模板，就足以覆盖大多数高风险嵌入式动作。

### `embedded.firmware_flash.v1`

适用：

- 烧录固件
- 刷写 bootloader
- 替换板卡主程序

必填字段：

- `task_id`
- `impact_devices`
- `target_version`
- `previous_version`
- `execution_owner`
- `rollback_plan`
- `risk_summary`
- `preflight_checklist`

最低检查项：

1. 目标板卡身份已确认。
2. 当前供电与线缆状态已确认。
3. 回退固件已准备。
4. 串口日志采集已接好。
5. 急停或断电路径已确认。

### `embedded.parameter_write.v1`

适用：

- PID 参数写入
- 限位/阈值修改
- 控制参数更新

必填字段：

- `task_id`
- `impact_devices`
- `parameter_changes`
- `execution_owner`
- `rollback_plan`
- `risk_summary`
- `preflight_checklist`

最低检查项：

1. 原参数值已记录。
2. 安全范围已由人工确认。
3. 测试环境已隔离。

### `embedded.actuator_motion.v1`

适用：

- 电机转动
- 机械臂动作
- 夹爪/履带/轮组运动测试

必填字段：

- `task_id`
- `impact_devices`
- `execution_owner`
- `observer_user_id`
- `movement_scope`
- `rollback_plan`
- `risk_summary`
- `preflight_checklist`

最低检查项：

1. 工作区已清空。
2. 限位与安全保护已开启。
3. 急停已测试可用。
4. 已切到低速或安全测试模式。

## 对现有 schema 的最小接口建议

为了尽量少改现有 Pydantic 结构，第一阶段建议这样接：

### `tasks`

- `TaskCreate` / `TaskUpdate` / `TaskRead` 增加：
  - `risk_level`
  - `hardware_touch`
  - `hardware_action_type`
  - `requires_human_approval`
  - `required_runner_capabilities`
  - `target_devices`

### `approvals`

- `ApprovalCreate` / `ApprovalRead` 增加：
  - `approval_template`
  - `risk_summary`
  - `impact_devices`
  - `execution_owner`
  - `rollback_plan`
  - `preflight_checklist`

### `lab`

- 若必须最小改动，优先给实验记录结构增加：
  - `device_id`
  - `experiment_type`
  - `experiment_stage`
  - `operator_user_id`
  - `evidence_files`
  - `firmware_version`
  - `result_summary`

### `handoffs`

- `HandoffPackageCreate` / `HandoffPackageRead` 增加：
  - `risk_summary`
  - `hardware_context`
  - `required_checks`
  - `handoff_kind`
  - `unsafe_to_continue`

## 对 Boss 的收口建议

如果要安排后端最小实现，建议顺序是：

1. 先改 `tasks`，因为它决定哪些任务需要审批。
2. 再改 `approvals`，因为它定义门岗结构。
3. 再改 `handoffs`，因为高风险任务需要结构化交接。
4. 最后改 `lab`，把实验记录补全。

这个顺序能最快把“高风险硬件动作必须人工确认”从文档要求变成数据层约束。

## 第一阶段最小 payload 示例

下面这些示例只服务于后端第一阶段增量实现，目的是让接手方知道“先做到什么程度就够用”。

### `tasks` 最小 create/read 示例

```json
{
  "project_id": "proj-001",
  "title": "刷写主控板 v1.2.4-rc1 固件",
  "module": "embedded",
  "priority": "P1",
  "status": "draft",
  "risk_level": "H3",
  "hardware_touch": true,
  "hardware_action_type": "firmware_flash",
  "requires_human_approval": true,
  "required_runner_capabilities": ["embedded-build", "serial-log"],
  "target_devices": ["mcu-main-board"],
  "acceptance_criteria": [
    "审批通过",
    "实验记录已上传",
    "启动日志正常"
  ]
}
```

最小只读返回至少应能补回：

- `risk_level`
- `hardware_touch`
- `hardware_action_type`
- `requires_human_approval`
- `required_runner_capabilities`
- `target_devices`

### `approvals` 最小 create/read 示例

```json
{
  "project_id": "proj-001",
  "task_id": "task-001",
  "level": "H3",
  "action": "flash_firmware",
  "approval_template": "embedded.firmware_flash.v1",
  "risk_summary": "刷写错误固件会导致主控板无法启动",
  "impact_devices": ["mcu-main-board"],
  "execution_owner": "human:zhangsan",
  "rollback_plan": "保留 v1.2.3 固件回刷路径",
  "preflight_checklist": [
    "目标板卡身份已确认",
    "供电状态已确认",
    "串口日志采集已连接"
  ],
  "notes": "仅允许人工现场执行"
}
```

最小只读返回至少应能补回：

- `approval_template`
- `risk_summary`
- `impact_devices`
- `execution_owner`
- `rollback_plan`
- `preflight_checklist`

### `handoffs` 最小 create/read 示例

```json
{
  "project_id": "proj-001",
  "task_id": "task-001",
  "handoff_from": "AI-4",
  "handoff_to": "human-review",
  "summary": "构建与仿真已完成，等待人工刷写",
  "reason": "进入高风险硬件执行阶段",
  "current_status": "waiting_human_approval",
  "risk_summary": "未确认板卡身份前不得继续刷写",
  "hardware_context": {
    "target_devices": ["mcu-main-board"],
    "target_version": "v1.2.4-rc1",
    "experiment_state": "pending_real_hardware"
  },
  "required_checks": [
    "确认板卡序列号",
    "确认回退固件在手",
    "确认串口日志连接"
  ],
  "handoff_kind": "ai_to_human",
  "unsafe_to_continue": true,
  "linked_approval_ids": ["approval-001"],
  "next_steps": [
    "人工批准刷写",
    "人工执行刷写",
    "上传启动日志"
  ]
}
```

最小只读返回至少应能补回：

- `risk_summary`
- `hardware_context`
- `required_checks`
- `handoff_kind`
- `unsafe_to_continue`

### `lab` 最小实验记录示例

如果第一阶段不新开复杂实验模型，至少应能承载下面这些字段：

```json
{
  "task_id": "task-001",
  "device_id": "mcu-main-board",
  "experiment_type": "real_hardware",
  "experiment_stage": "reviewing",
  "operator_user_id": "user-001",
  "firmware_version": "v1.2.4-rc1",
  "evidence_files": [
    "artifacts/lab/task-001/serial.log",
    "artifacts/lab/task-001/board-photo.jpg"
  ],
  "result_summary": "刷写完成，启动日志正常"
}
```

如果现阶段 `lab` 还不适合正式新增实体，最小替代做法是：

1. 先在 `lab` 相关写入接口里接受一个结构化 `payload`。
2. payload 至少包含上面的 7 个字段。
3. 等第二阶段再把实验记录独立成稳定 schema。
## 后端实现任务拆解单

这一节只服务后端接手，不要求前端同步开工。目标是让后端按 `tasks -> approvals -> handoffs -> lab` 的顺序增量落地，并把“高风险硬件动作必须人工确认”变成接口层和数据层都绕不过去的约束。

### 实施边界

- 本轮只改后端 schema、校验、默认值、接口读写行为和最小测试。
- 不改前端页面、不改 HUD、不改地图、不改主循环。
- 不把高风险硬件动作偷偷降级成 Runner 自动执行。
- 能复用现有 `payload` / `notes` / `data` 的地方先复用，避免第一阶段开太多新实体。

### 总体实施顺序

1. 先补 `tasks`，让任务层先表达“这是不是硬件动作、风险多高、是否必须人工审批”。
2. 再补 `approvals`，把高风险动作的审批模板和人工门槛结构化。
3. 再补 `handoffs`，确保 AI 交接给人或后续角色时不会丢失硬件上下文。
4. 最后补 `lab`，把真实实验记录和证据文件补齐。

### 第 1 步：`tasks` 增量改造

目标：
- 让任务一创建出来，就能被识别为普通软件任务还是嵌入式硬件风险任务。
- 给审批模块和派发模块一个统一上游信号。

需要改的 schema：
- `TaskCreate`
- `TaskUpdate`
- `TaskRead`

建议新增字段：
- `risk_level: str | None = None`
- `hardware_touch: bool = False`
- `hardware_action_type: str | None = None`
- `requires_human_approval: bool = False`
- `required_runner_capabilities: list[str] = Field(default_factory=list)`
- `target_devices: list[str] = Field(default_factory=list)`

接口行为要求：
- 当 `hardware_touch=true` 时，`hardware_action_type` 不能为空。
- 当 `risk_level` 为 `H2/H3/H4` 且 `hardware_touch=true` 时，`requires_human_approval` 不能为 `false`。
- 对普通软件任务，新增字段允许为空或默认值，不影响旧数据。
- `TaskRead` 必须把这些字段完整返回，不能只写不读。

最小验收标准：
- 能创建一条 `hardware_touch=true` 的嵌入式任务。
- 能创建一条普通软件任务且不受新字段影响。
- 高风险硬件任务若缺少人工审批标记，会被接口拒绝或规范化为必须审批。

建议后续 owner：
- 后端任务模块负责人

### 第 2 步：`approvals` 增量改造

目标：
- 让审批不再只是一个抽象 `action`，而是能明确记录模板、风险摘要、设备影响和回退计划。
- 把“人工确认门槛”放到真正承接高风险动作的地方。

需要改的 schema：
- `ApprovalCreate`
- `ApprovalRead`
- 如有必要，`ApprovalUpdate`

建议新增字段：
- `approval_template: str | None = None`
- `risk_summary: str | None = None`
- `impact_devices: list[str] = Field(default_factory=list)`
- `execution_owner: str | None = None`
- `rollback_plan: str | None = None`
- `preflight_checklist: list[str] = Field(default_factory=list)`

第一阶段至少支持的模板：
- `embedded.firmware_flash.v1`
- `embedded.parameter_write.v1`
- `embedded.actuator_motion.v1`

接口行为要求：
- 当审批关联的任务是 `requires_human_approval=true` 时，审批创建请求必须带上 `approval_template`。
- `approval_template` 为嵌入式模板时，`risk_summary`、`impact_devices`、`execution_owner`、`rollback_plan` 不能为空或空列表。
- `preflight_checklist` 至少保留原始顺序，避免人工执行时丢检查步骤。
- 审批通过前，不允许把任务推进到真实硬件执行态。

最小验收标准：
- 能创建一条固件刷写审批，并返回模板和检查项。
- 普通低风险审批仍可按旧结构运行。
- 高风险嵌入式任务缺模板或缺回退方案时被拒绝。

建议后续 owner：
- 后端审批模块负责人

### 第 3 步：`handoffs` 增量改造

目标：
- 让 AI 向人、AI 向 AI、AI 向 Runner 的交接都能带上硬件上下文，而不是只剩一句“等人处理”。
- 当任务因为硬件风险不能继续时，交接包能明确表达“禁止自动续跑”。

需要改的 schema：
- `HandoffPackageCreate`
- `HandoffPackageRead`

建议新增字段：
- `risk_summary: str | None = None`
- `hardware_context: dict = Field(default_factory=dict)`
- `required_checks: list[str] = Field(default_factory=list)`
- `handoff_kind: str | None = None`
- `unsafe_to_continue: bool = False`

接口行为要求：
- 对嵌入式高风险任务，交接包必须能挂上 `linked_approval_ids`。
- 当 `unsafe_to_continue=true` 时，后续消费方不能把它当作普通自动续跑任务。
- `handoff_kind` 第一阶段至少支持：`ai_to_human`、`ai_to_backend`、`human_to_runner`。
- `hardware_context` 第一阶段只要求接受结构化字典，不强制拆成独立实体。

最小验收标准：
- AI 能创建一条“等待人工审批”的交接包。
- 交接读取接口能把风险摘要、检查项和设备上下文返回给后续处理方。
- 高风险交接包可明确标记为不可自动继续。

建议后续 owner：
- 后端交接模块负责人

### 第 4 步：`lab` 增量改造

目标：
- 给真实硬件实验和验证结果一个最小可落地承载位。
- 先解决“证据在哪、谁做的、结果如何”这三个问题，不急着做复杂实验系统。

优先改的 schema：
- `LabCheckRecordCreate`
- `LabApprovalRequestCreate`

第一阶段最小新增方向：
- 在实验相关写入口接受结构化 `payload`
- `payload` 至少包含：
  - `device_id`
  - `experiment_type`
  - `experiment_stage`
  - `operator_user_id`
  - `evidence_files`
  - `firmware_version`
  - `result_summary`

接口行为要求：
- 能写入真实硬件实验记录的最小信息和证据文件路径。
- 若任务来自高风险嵌入式审批，`experiment_stage` 不能直接跳过 `reviewing` / `approved` 之类的人工门槛阶段。
- `evidence_files` 可先只校验为字符串路径列表，不要求前端先接入上传控件。

最小验收标准：
- 能记录一条真实硬件实验结果。
- 能把实验记录与 `task_id` 关联。
- 高风险任务能在 `lab` 里看到与审批和执行相关的最小证据链。

建议后续 owner：
- 后端 lab 模块负责人

### 建议实现顺序对应的开发票据

1. 票据 A：补 `tasks` 嵌入式风险字段与校验。
2. 票据 B：补 `approvals` 嵌入式审批模板与必填校验。
3. 票据 C：补 `handoffs` 硬件交接上下文与禁止自动续跑标记。
4. 票据 D：补 `lab` 最小实验 payload 与证据字段承载。
5. 票据 E：补 1 轮最小 API / schema 测试，覆盖高风险任务必须人工确认这条红线。

### 后端联调时必须守住的红线

- 不能因为已有 Runner 体系，就让 `firmware_flash`、`parameter_write`、`actuator_motion` 在无人工确认时自动执行。
- 不能只在前端做隐藏按钮或弹窗校验，后端接口本身必须保留硬门槛。
- 不能把 `unsafe_to_continue` 只当展示字段，它必须能被流程消费方识别。
- 不能要求 AI 在 handoff 文本里“口头提醒风险”来替代结构化字段。

### 本轮更新（Boss 要求收成后端实现任务拆解单后）

- 已把 `tasks -> approvals -> handoffs -> lab` 收成后端可直接执行的任务拆解单。
- 每一步都补了：目标、需要改的 schema、字段建议、接口行为要求、最小验收标准、建议 owner。
- 明确保留实施边界：这轮只服务后端接手，不碰前端、不碰主循环。
- 明确保留红线：高风险硬件动作不得被降级为自动执行，人工确认必须在后端接口层可见且可校验。
## 后端票据顺序清单（本轮补强）

这一节把前面的拆解再压成更明确的票据顺序，方便后端直接开 issue / task，不需要再二次整理。

### 票据 A：`tasks` 增加嵌入式风险表达

目标：
- 让任务层先表达“是否触达硬件、风险等级、是否必须人工审批”。
- 为 `approvals` 和后续派发提供统一上游判断条件。

建议 owner：
- 后端 `tasks` 模块负责人

改动范围：
- `apps/api/app/modules/tasks/schemas.py`
- 如存在对应 service / router / persistence，同步补读写映射

最小实现内容：
- 在 `TaskCreate`、`TaskUpdate`、`TaskRead` 增加：
  - `risk_level`
  - `hardware_touch`
  - `hardware_action_type`
  - `requires_human_approval`
  - `required_runner_capabilities`
  - `target_devices`
- 增加最小校验：
  - `hardware_touch=true` 时，`hardware_action_type` 不能为空
  - `risk_level` 为 `H2/H3/H4` 且 `hardware_touch=true` 时，`requires_human_approval` 不能为 `false`

最小验收标准：
- 能创建普通软件任务，且旧字段兼容不受影响
- 能创建嵌入式高风险任务，并完整读回新增字段
- 高风险硬件任务不能以“无需人工审批”的状态落库

阻塞关系：
- 这是票据 B / C / D 的前置票据

### 票据 B：`approvals` 增加嵌入式审批模板和人工门槛

目标：
- 把高风险硬件动作的审批从抽象动作升级成结构化审批单。
- 确保人工确认门槛存在于后端接口层，而不是只存在于文档描述里。

建议 owner：
- 后端 `approvals` 模块负责人

改动范围：
- `apps/api/app/modules/approvals/schemas.py`
- 如存在审批创建/通过逻辑，同步补模板校验

最小实现内容：
- 在 `ApprovalCreate`、`ApprovalRead` 增加：
  - `approval_template`
  - `risk_summary`
  - `impact_devices`
  - `execution_owner`
  - `rollback_plan`
  - `preflight_checklist`
- 第一阶段支持的模板固定为：
  - `embedded.firmware_flash.v1`
  - `embedded.parameter_write.v1`
  - `embedded.actuator_motion.v1`
- 增加最小校验：
  - 当关联任务 `requires_human_approval=true` 时，`approval_template` 必填
  - 嵌入式审批模板下，`risk_summary`、`impact_devices`、`execution_owner`、`rollback_plan` 必填

最小验收标准：
- 能创建一条带模板的嵌入式审批记录
- 能完整读回检查项、设备影响、执行责任人和回退方案
- 高风险任务缺审批模板或缺关键字段时，请求被拒绝

阻塞关系：
- 依赖票据 A
- 票据 C / D 的风险链路依赖本票据返回的审批信息

### 票据 C：`handoffs` 增加硬件风险交接上下文

目标：
- 让高风险任务在交接时保留结构化硬件上下文和禁止自动续跑标记。
- 避免 AI 交接只剩自然语言摘要，导致后续角色误判可自动继续。

建议 owner：
- 后端 `handoffs` 模块负责人

改动范围：
- `apps/api/app/modules/handoffs/schemas.py`
- 如存在 handoff accept / assign / consume 逻辑，同步识别 `unsafe_to_continue`

最小实现内容：
- 在 `HandoffPackageCreate`、`HandoffPackageRead` 增加：
  - `risk_summary`
  - `hardware_context`
  - `required_checks`
  - `handoff_kind`
  - `unsafe_to_continue`
- 第一阶段约定：
  - `handoff_kind` 至少支持 `ai_to_human`、`ai_to_backend`、`human_to_runner`
  - 高风险嵌入式任务的交接包必须允许关联 `linked_approval_ids`

最小验收标准：
- 能创建“等待人工审批”的嵌入式 handoff
- 能读回硬件上下文、检查项、风险摘要和 `unsafe_to_continue`
- 高风险 handoff 不会被当作普通自动续跑任务处理

阻塞关系：
- 依赖票据 A、B

### 票据 D：`lab` 接受最小实验记录 payload

目标：
- 在不新开复杂实验系统的前提下，先承载真实硬件实验记录和证据路径。
- 给审批后的人工作业留下最小证据链。

建议 owner：
- 后端 `lab` 模块负责人

改动范围：
- `apps/api/app/modules/lab/schemas.py`
- 如存在实验记录写入口，同步接受结构化 `payload`

最小实现内容：
- 在现有实验相关写入口接受最小 `payload`
- `payload` 至少包含：
  - `device_id`
  - `experiment_type`
  - `experiment_stage`
  - `operator_user_id`
  - `evidence_files`
  - `firmware_version`
  - `result_summary`
- 若关联的是高风险审批任务，禁止跳过人工审核阶段直接进入“自动完成”

最小验收标准：
- 能写入一条与 `task_id` 关联的真实硬件实验记录
- 能保存证据文件路径和结果摘要
- 高风险任务的实验记录不能绕过人工阶段直接闭环

阻塞关系：
- 依赖票据 A、B
- 若要回写交接链路，建议同时联调票据 C

### 票据 E：最小测试与红线守卫

目标：
- 用最小测试把“高风险硬件动作必须人工确认”固化为不会被回归破坏的行为。

建议 owner：
- 对应后端模块负责人联合补齐，或由后端测试 owner 收口

改动范围：
- `tasks / approvals / handoffs / lab` 相关 schema / API 测试

最小实现内容：
- 覆盖以下场景：
  - 高风险嵌入式任务创建后必须标记 `requires_human_approval=true`
  - 没有审批模板的高风险审批请求被拒绝
  - `unsafe_to_continue=true` 的 handoff 不能被当作普通自动续跑输入
  - `lab` 记录不能绕过人工审核阶段直接宣告完成

最小验收标准：
- 四类红线场景至少各有 1 条自动化测试
- 任一红线回归时测试失败

阻塞关系：
- 依赖票据 A、B、C、D 至少完成 schema 层改造

### 建议开工顺序

1. 先做票据 A，因为所有后续判断都依赖任务层先表达风险。
2. 再做票据 B，因为人工审批门槛必须尽早落到后端接口。
3. 再做票据 C，确保高风险任务不会在交接时丢失红线状态。
4. 然后做票据 D，把实验记录和证据链补上。
5. 最后做票据 E，把红线写进测试。

### 不可绕开的后端红线

- 任何 `firmware_flash`、`parameter_write`、`actuator_motion` 只要落在高风险区间，就必须经过人工确认，不能被 Runner、默认自动流转、临时兜底逻辑绕开。
- 不能把人工确认仅做成前端按钮显隐或 UI 弹窗提示；后端 schema、校验和状态流转本身必须强制执行。
- 不能把 `unsafe_to_continue` 当作展示字段；后端消费方必须识别并阻止自动继续。
- 不能用自然语言备注替代结构化风控字段；缺字段时应该拒绝，而不是“先让它过”。

### 本轮更新（Boss 要求继续压实票据顺序后）

- 已把 `tasks -> approvals -> handoffs -> lab` 再压成可直接开工的票据顺序清单。
- 每张票据都单列了：目标、建议 owner、改动范围、最小实现内容、最小验收标准、阻塞关系。
- 重新明确了后端不可绕开的红线，避免任何自动化把高风险硬件动作偷渡成自动执行。
## 后端实施票据顺序 v2（进一步压实）

这一节只补强后端接手顺序，不改变前面已经确定的映射结论。目标是让后端负责人看到后，能直接按票据顺序排期、落 schema、补接口、写最小测试。

### 顺序总览

1. 票据 A：先改 `tasks`，把风险和人工审批要求挂到任务主记录。
2. 票据 B：再改 `approvals`，把高风险硬件审批模板和必填字段落到接口层。
3. 票据 C：再改 `handoffs`，把“禁止自动续跑”的交接上下文结构化。
4. 票据 D：最后改 `lab`，补真实硬件实验记录和证据链。
5. 票据 E：补最小测试，专门守住人工确认红线。

### 票据 A：`tasks` 风险主入口

建议 owner：
- 后端 `tasks` 模块负责人

是否需要测试：
- 需要

为什么先做：
- `tasks` 是后续审批、交接、实验记录的上游事实来源。
- 如果任务层不先表达风险，后续模块只能靠文本猜测，红线会失真。

最小改动点：
- 在 `TaskCreate`、`TaskUpdate`、`TaskRead` 增加：
  - `risk_level`
  - `hardware_touch`
  - `hardware_action_type`
  - `requires_human_approval`
  - `required_runner_capabilities`
  - `target_devices`

接口层要求：
- `hardware_touch=true` 时必须要求 `hardware_action_type`
- `risk_level` 为 `H2/H3/H4` 且 `hardware_touch=true` 时，接口必须拒绝 `requires_human_approval=false`
- `TaskRead` 必须完整回传这些字段，不能只写不读

数据层要求：
- 高风险硬件任务一旦落库，必须能被明确识别为“需要人工审批”
- 不能允许通过空值、默认值或兼容逻辑把高风险任务伪装成普通任务

最小验收标准：
- 普通软件任务创建/读取不受影响
- 高风险硬件任务创建后可完整读回新增字段
- 高风险硬件任务不能以“无需人工审批”状态被接受

### 票据 B：`approvals` 人工门槛入口

建议 owner：
- 后端 `approvals` 模块负责人

是否需要测试：
- 需要

依赖：
- 依赖票据 A

最小改动点：
- 在 `ApprovalCreate`、`ApprovalRead` 增加：
  - `approval_template`
  - `risk_summary`
  - `impact_devices`
  - `execution_owner`
  - `rollback_plan`
  - `preflight_checklist`
- 第一阶段审批模板固定为：
  - `embedded.firmware_flash.v1`
  - `embedded.parameter_write.v1`
  - `embedded.actuator_motion.v1`

接口层要求：
- 当关联任务 `requires_human_approval=true` 时，`approval_template` 必填
- 嵌入式审批模板下，`risk_summary`、`impact_devices`、`execution_owner`、`rollback_plan`、`preflight_checklist` 不能缺
- 审批未通过前，接口层不得把任务推进到真实硬件执行态

数据层要求：
- 审批记录必须能表达“谁来人工执行、影响哪些设备、失败如何回退”
- 不能只保存一个模糊 `action` 就算审批完成

最小验收标准：
- 能创建并读回一条嵌入式审批记录
- 高风险审批缺模板或缺关键字段时被拒绝
- 未审批通过的高风险任务不能进入真实硬件执行链

### 票据 C：`handoffs` 禁止自动续跑标记

建议 owner：
- 后端 `handoffs` 模块负责人

是否需要测试：
- 需要

依赖：
- 依赖票据 A、B

最小改动点：
- 在 `HandoffPackageCreate`、`HandoffPackageRead` 增加：
  - `risk_summary`
  - `hardware_context`
  - `required_checks`
  - `handoff_kind`
  - `unsafe_to_continue`

接口层要求：
- 高风险嵌入式 handoff 必须允许携带 `linked_approval_ids`
- `unsafe_to_continue=true` 时，任何后续自动消费逻辑都不能把它当作普通续跑输入
- 第一阶段 `handoff_kind` 至少支持：
  - `ai_to_human`
  - `ai_to_backend`
  - `human_to_runner`

数据层要求：
- 交接包里必须保留结构化风险和设备上下文
- 不能只靠自然语言摘要提醒“这里有风险”

最小验收标准：
- 能创建等待人工审批的 handoff 包
- 能读回风险摘要、设备上下文、检查项、`unsafe_to_continue`
- 高风险 handoff 不会被错误进入自动续跑路径

### 票据 D：`lab` 最小实验记录承载

建议 owner：
- 后端 `lab` 模块负责人

是否需要测试：
- 需要

依赖：
- 依赖票据 A、B
- 若要串完整风险链，建议联调票据 C

最小改动点：
- 在现有实验相关写入口接受结构化 `payload`
- 最小 `payload` 至少包含：
  - `device_id`
  - `experiment_type`
  - `experiment_stage`
  - `operator_user_id`
  - `evidence_files`
  - `firmware_version`
  - `result_summary`

接口层要求：
- 高风险任务进入真实硬件实验记录时，不能跳过人工审核/审批阶段
- `evidence_files` 至少以路径列表形式可写入
- `task_id` 必须能关联回原任务

数据层要求：
- 必须能留下谁操作、操作哪个设备、结果如何、证据在哪里
- 不能让真实硬件执行结果只存在于聊天文本或临时日志里

最小验收标准：
- 能写入并读回一条真实硬件实验记录
- 实验记录可关联 `task_id`
- 高风险实验链不能绕过人工阶段直接闭环

### 票据 E：红线守卫测试

建议 owner：
- 后端测试 owner 或对应模块负责人联合补齐

是否需要测试：
- 必须

依赖：
- 依赖票据 A、B、C、D 至少完成 schema / 接口改造

最小改动点：
- 为以下四类行为补最小自动化测试：
  - 高风险硬件任务不能绕过 `requires_human_approval`
  - 高风险审批不能缺模板和回退方案
  - `unsafe_to_continue=true` 的交接不能进入自动续跑
  - `lab` 记录不能绕过人工阶段直接完成

接口层要求：
- 任一红线被打破时，请求失败或状态流转失败

数据层要求：
- 任一红线被回归破坏时，测试应能直接暴露

最小验收标准：
- 四类红线至少各有 1 条测试
- 回归时测试失败，不能静默放过

### 不能被自动化绕开的硬门槛

- `firmware_flash`
- `parameter_write`
- `actuator_motion`

以上三类动作只要命中高风险条件，就必须保留人工确认门槛。这个门槛必须同时存在于：
- 接口层校验
- 数据层状态表达
- 交接层阻断标记

不能接受的错位做法：
- 只在前端隐藏按钮
- 只在文档里写“需要人工确认”
- 只靠 Runner 约定俗成不去执行
- 只靠 AI 在 handoff 里口头提醒

### 本轮更新（Boss 要求继续压实实施顺序后）

- 已把 `tasks -> approvals -> handoffs -> lab` 进一步压成后端实施票据顺序 v2
- 每一步都明确补了：建议 owner、是否需要测试、接口层要求、数据层要求、最小验收标准
- 继续固化红线：高风险硬件动作必须人工确认，且不能被任何自动化、默认流转、临时兜底绕开
## 后端实施单（可直接分发）

这一节用于直接发给后端负责人，不再需要他们从长文里二次提炼。默认实施顺序不变：`tasks -> approvals -> handoffs -> lab -> tests`。

### 分发说明

- 本实施单只覆盖后端 schema、接口、状态约束和最小测试。
- 不包含前端页面、HUD、地图、美术、主循环改造。
- 所有高风险硬件动作都必须保留人工确认门槛。
- 任何自动化、默认流转、Runner 执行链都不能绕开这条门槛。

### 实施单 A：`tasks`

建议 owner：
- 后端 `tasks` 模块负责人

实施目标：
- 让任务主记录先表达硬件触达、风险等级和人工审批需求。

需要落地的字段：
- `risk_level`
- `hardware_touch`
- `hardware_action_type`
- `requires_human_approval`
- `required_runner_capabilities`
- `target_devices`

接口层硬要求：
- `hardware_touch=true` 时，`hardware_action_type` 必填
- `risk_level` 为 `H2/H3/H4` 且 `hardware_touch=true` 时，`requires_human_approval` 不能为 `false`
- 读取接口必须完整返回新增字段

最小验收标准：
- 普通软件任务可正常创建和读取
- 高风险硬件任务可创建并完整读回新增字段
- 高风险硬件任务不能以“无需人工审批”状态进入系统

是否需要测试：
- 需要

建议测试点：
- 高风险任务创建时缺 `requires_human_approval=true` 被拒绝
- 普通软件任务不受新增字段影响

### 实施单 B：`approvals`

建议 owner：
- 后端 `approvals` 模块负责人

实施目标：
- 把高风险硬件审批做成结构化审批单，而不是松散备注。

需要落地的字段：
- `approval_template`
- `risk_summary`
- `impact_devices`
- `execution_owner`
- `rollback_plan`
- `preflight_checklist`

第一阶段模板：
- `embedded.firmware_flash.v1`
- `embedded.parameter_write.v1`
- `embedded.actuator_motion.v1`

接口层硬要求：
- 关联任务 `requires_human_approval=true` 时，`approval_template` 必填
- 使用嵌入式审批模板时，`risk_summary`、`impact_devices`、`execution_owner`、`rollback_plan`、`preflight_checklist` 不能缺
- 审批未通过前，不得进入真实硬件执行态

最小验收标准：
- 能创建并读取带模板的嵌入式审批记录
- 缺模板或缺关键字段的高风险审批请求会被拒绝
- 未审批通过的高风险任务不能进入真实硬件执行链

是否需要测试：
- 需要

建议测试点：
- 高风险审批缺模板被拒绝
- 高风险审批缺回退方案被拒绝
- 审批未通过时状态流转被阻断

### 实施单 C：`handoffs`

建议 owner：
- 后端 `handoffs` 模块负责人

实施目标：
- 让高风险任务在交接时保留风险上下文，并明确禁止自动续跑。

需要落地的字段：
- `risk_summary`
- `hardware_context`
- `required_checks`
- `handoff_kind`
- `unsafe_to_continue`

第一阶段 `handoff_kind`：
- `ai_to_human`
- `ai_to_backend`
- `human_to_runner`

接口层硬要求：
- 高风险 handoff 必须允许关联 `linked_approval_ids`
- `unsafe_to_continue=true` 时，后续自动消费逻辑必须阻断
- 读取接口必须返回风险摘要、设备上下文、检查项

最小验收标准：
- 能创建等待人工审批的 handoff 包
- 能读取 `unsafe_to_continue` 和结构化风险上下文
- 高风险 handoff 不会误入自动续跑路径

是否需要测试：
- 需要

建议测试点：
- `unsafe_to_continue=true` 的 handoff 无法进入自动续跑链
- 高风险 handoff 可正确挂接审批记录

### 实施单 D：`lab`

建议 owner：
- 后端 `lab` 模块负责人

实施目标：
- 给真实硬件实验记录一个最小可落地承载位，补上证据链。

最小 `payload`：
- `device_id`
- `experiment_type`
- `experiment_stage`
- `operator_user_id`
- `evidence_files`
- `firmware_version`
- `result_summary`

接口层硬要求：
- 高风险任务进入真实硬件实验链时，不能跳过人工审核阶段
- `task_id` 必须可关联
- `evidence_files` 至少支持路径列表写入和读取

最小验收标准：
- 能写入并读取一条真实硬件实验记录
- 记录中包含设备、操作者、证据路径、结果摘要
- 高风险实验链不能绕过人工阶段直接完成

是否需要测试：
- 需要

建议测试点：
- 高风险实验记录不能跳过人工审核阶段
- `task_id` 和证据路径可正常写入读取

### 实施单 E：红线守卫测试

建议 owner：
- 后端测试 owner，或由四个模块负责人联合补齐

实施目标：
- 用自动化测试守住“高风险硬件动作必须人工确认”这条红线。

必须覆盖的红线场景：
- 高风险硬件任务不能绕过 `requires_human_approval`
- 高风险审批不能缺模板和回退方案
- `unsafe_to_continue=true` 的交接不能进入自动续跑
- `lab` 记录不能绕过人工阶段直接完成

最小验收标准：
- 四类红线至少各有 1 条自动化测试
- 任一红线被破坏时，测试必须失败

是否需要测试：
- 必须

建议测试点：
- 直接按四类红线场景写最小失败用例

### 后端统一红线

- `firmware_flash`
- `parameter_write`
- `actuator_motion`

以上动作只要命中高风险条件，就必须经过人工确认。

这条要求必须同时体现在：
- 任务字段
- 审批字段
- 交接阻断字段
- 实验记录阶段
- 自动化测试

以下做法一律不合格：
- 只在前端隐藏按钮
- 只在文档里提醒
- 只靠 Runner 默认不执行
- 只靠 AI 在 handoff 备注里口头说明
- 依赖“默认流转一般不会走到这里”的侥幸逻辑

### 本轮更新（Boss 要求整理成可直接分发的后端实施单后）

- 已把票据顺序、最小验收标准和红线守卫测试整理成可直接分发的后端实施单
- 实施单按 `tasks -> approvals -> handoffs -> lab -> tests` 排序
- 每一步都补了建议 owner、接口层硬要求、最小验收标准、是否需要测试和建议测试点
- 继续固化红线：高风险硬件动作必须人工确认，且不能被自动化和默认流转绕开
## 后端实施单 v2（发包版）

这一节是给后端负责人直接转发的版本。默认阅读顺序就是开工顺序：`tasks -> approvals -> handoffs -> lab -> tests`。如果只看一节，优先看这里。

### 发包总要求

- 只做后端 schema、接口、状态流转、最小自动化测试。
- 不改前端页面、不改 HUD、不改地图、不改主循环。
- 高风险硬件动作必须经过人工确认。
- 这条红线不能被以下路径绕开：
  - 自动化执行
  - 默认状态流转
  - 临时兜底逻辑
  - Runner 约定俗成
  - 文本备注替代结构化字段

### 发包 1：`tasks` 任务层先表达风险

建议 owner：
- 后端 `tasks` 模块负责人

交付目标：
- 让任务创建时就能明确是否触达硬件、属于哪类硬件动作、是否必须人工审批。

必须落地：
- `risk_level`
- `hardware_touch`
- `hardware_action_type`
- `requires_human_approval`
- `required_runner_capabilities`
- `target_devices`

接口层必须满足：
- `hardware_touch=true` 时，`hardware_action_type` 必填
- `hardware_touch=true` 且 `risk_level` 命中 `H2/H3/H4` 时，`requires_human_approval` 必须为 `true`
- 读取接口必须完整返回这些字段

最小验收标准：
- 普通软件任务仍可正常创建和读取
- 高风险硬件任务创建后可完整读回新增字段
- 高风险硬件任务不能以“无需人工审批”状态被接受

是否需要测试：
- 需要

红线守卫测试：
- 提交高风险硬件任务且 `requires_human_approval=false` 时，请求失败
- 提交普通软件任务时，兼容旧字段行为

### 发包 2：`approvals` 审批层承接人工门槛

建议 owner：
- 后端 `approvals` 模块负责人

交付目标：
- 把高风险硬件动作的人工审批变成结构化审批记录，而不是备注说明。

必须落地：
- `approval_template`
- `risk_summary`
- `impact_devices`
- `execution_owner`
- `rollback_plan`
- `preflight_checklist`

第一阶段模板固定：
- `embedded.firmware_flash.v1`
- `embedded.parameter_write.v1`
- `embedded.actuator_motion.v1`

接口层必须满足：
- 若关联任务 `requires_human_approval=true`，则 `approval_template` 必填
- 使用嵌入式模板时，`risk_summary`、`impact_devices`、`execution_owner`、`rollback_plan`、`preflight_checklist` 不能缺
- 审批未通过前，任何状态流转都不能进入真实硬件执行态

最小验收标准：
- 能创建并读取一条完整的嵌入式审批记录
- 高风险审批缺模板或缺关键字段时，请求被拒绝
- 审批未通过前，高风险任务不能进入真实硬件执行链

是否需要测试：
- 需要

红线守卫测试：
- 缺审批模板的高风险审批请求失败
- 缺回退方案的高风险审批请求失败
- 审批未通过时，任务推进到真实硬件执行态的请求失败

### 发包 3：`handoffs` 交接层阻断自动续跑

建议 owner：
- 后端 `handoffs` 模块负责人

交付目标：
- 让高风险任务在交接时明确带上结构化风险上下文，并能阻断后续自动续跑。

必须落地：
- `risk_summary`
- `hardware_context`
- `required_checks`
- `handoff_kind`
- `unsafe_to_continue`

第一阶段 `handoff_kind`：
- `ai_to_human`
- `ai_to_backend`
- `human_to_runner`

接口层必须满足：
- 高风险 handoff 必须允许挂接 `linked_approval_ids`
- `unsafe_to_continue=true` 时，任何自动消费逻辑都必须阻断
- 读取接口必须完整返回风险摘要、检查项、硬件上下文

最小验收标准：
- 能创建“等待人工审批”的高风险 handoff
- 能读取 `unsafe_to_continue` 和结构化硬件上下文
- 高风险 handoff 不会误入自动续跑链

是否需要测试：
- 需要

红线守卫测试：
- `unsafe_to_continue=true` 的 handoff 进入自动续跑时失败
- 高风险 handoff 可正确关联审批记录

### 发包 4：`lab` 实验记录层补证据链

建议 owner：
- 后端 `lab` 模块负责人

交付目标：
- 承载真实硬件实验记录、证据路径和结果摘要，避免结果只留在聊天或临时日志里。

必须落地的最小 `payload`：
- `device_id`
- `experiment_type`
- `experiment_stage`
- `operator_user_id`
- `evidence_files`
- `firmware_version`
- `result_summary`

接口层必须满足：
- 高风险任务进入真实硬件实验链时，不能跳过人工审核阶段
- `task_id` 必须可关联
- `evidence_files` 至少支持路径列表读写

最小验收标准：
- 能写入并读取一条真实硬件实验记录
- 记录中包含设备、操作者、结果摘要、证据路径
- 高风险实验链不能绕过人工阶段直接完成

是否需要测试：
- 需要

红线守卫测试：
- 高风险实验记录若跳过人工审核阶段，请求失败
- `task_id`、证据路径、结果摘要可正常写入读取

### 发包 5：统一红线守卫测试

建议 owner：
- 后端测试 owner，或四个模块负责人联合补齐

交付目标：
- 用自动化测试把“高风险硬件动作必须人工确认”固化成不会被回归破坏的行为。

必须覆盖：
- 高风险硬件任务不能绕过 `requires_human_approval`
- 高风险审批不能缺模板和回退方案
- `unsafe_to_continue=true` 的交接不能进入自动续跑
- 高风险实验记录不能绕过人工阶段直接完成

最小验收标准：
- 四类红线至少各有 1 条自动化测试
- 任一红线被破坏时，测试必须失败

是否需要测试：
- 必须

### 统一不可绕开红线

以下动作只要命中高风险条件，就必须保留人工确认门槛：
- `firmware_flash`
- `parameter_write`
- `actuator_motion`

这条门槛必须同时存在于：
- `tasks` 的风险字段
- `approvals` 的审批结构
- `handoffs` 的阻断标记
- `lab` 的阶段限制
- 自动化测试的失败用例

以下做法一律不合格：
- 只在前端隐藏按钮或弹窗提醒
- 只在后端备注里写“需要人工确认”
- 只靠 Runner 默认不执行
- 只靠默认流转“通常不会走到这里”
- 只靠临时兜底逻辑拦截

### 本轮更新（Boss 要求继续收成可直接分发实施单后）

- 已把现有票据顺序、最小验收标准和红线守卫测试进一步收成“后端实施单 v2（发包版）”
- 每一步都收敛成：交付目标、必须落地、接口层必须满足、最小验收标准、是否需要测试、红线守卫测试
- 再次固化了统一红线：高风险硬件动作必须人工确认，且不能被自动化、默认流转和临时兜底绕开
## 后端实施单 v3（领票执行版）

这一节继续只服务后端接手，目标是让后端负责人可以直接把下面内容拆成开发票据并开工，不需要再从上文二次提炼。

### 领票总原则

- 实施顺序固定为：`tasks -> approvals -> handoffs -> lab -> tests`
- 本轮只改后端 schema、接口校验、状态流转和最小自动化测试
- 不改前端页面、不改 HUD、不改主循环
- 高风险硬件动作必须人工确认，这条红线不能被自动化、默认流转、临时兜底、Runner 约定或备注文本绕开

### 票据 1：`tasks` 风险入口

建议 owner：
- 后端 `tasks` 模块负责人

本票据要交付：
- 让任务主记录能够明确表达硬件触达、动作类型、风险等级、人工审批要求

必须落地字段：
- `risk_level`
- `hardware_touch`
- `hardware_action_type`
- `requires_human_approval`
- `required_runner_capabilities`
- `target_devices`

接口层必须满足：
- `hardware_touch=true` 时，`hardware_action_type` 不能为空
- `hardware_touch=true` 且 `risk_level` 为 `H2/H3/H4` 时，`requires_human_approval` 必须为 `true`
- 读取接口必须返回全部新增字段

最小验收标准：
- 普通软件任务创建和读取不受影响
- 高风险硬件任务可完整创建并读回新增字段
- 高风险硬件任务不能以“无需人工审批”状态被接受

是否需要测试：
- 需要

红线守卫测试：
- 高风险硬件任务若提交 `requires_human_approval=false`，请求失败
- 普通软件任务仍按旧兼容路径成功创建

### 票据 2：`approvals` 人工门槛

建议 owner：
- 后端 `approvals` 模块负责人

本票据要交付：
- 让高风险硬件动作的审批成为结构化审批单，而不是松散说明

必须落地字段：
- `approval_template`
- `risk_summary`
- `impact_devices`
- `execution_owner`
- `rollback_plan`
- `preflight_checklist`

第一阶段模板：
- `embedded.firmware_flash.v1`
- `embedded.parameter_write.v1`
- `embedded.actuator_motion.v1`

接口层必须满足：
- 若关联任务 `requires_human_approval=true`，则 `approval_template` 必填
- 使用嵌入式模板时，`risk_summary`、`impact_devices`、`execution_owner`、`rollback_plan`、`preflight_checklist` 不能缺
- 审批未通过前，不允许进入真实硬件执行态

最小验收标准：
- 能创建并读取带模板的高风险审批记录
- 缺模板或缺关键字段的高风险审批请求被拒绝
- 未审批通过的高风险任务不能进入真实硬件执行链

是否需要测试：
- 需要

红线守卫测试：
- 缺审批模板的高风险审批请求失败
- 缺回退方案的高风险审批请求失败
- 审批未通过时，推进到真实硬件执行态的请求失败

### 票据 3：`handoffs` 阻断自动续跑

建议 owner：
- 后端 `handoffs` 模块负责人

本票据要交付：
- 让高风险任务在交接时保留结构化风险上下文，并明确阻断自动续跑

必须落地字段：
- `risk_summary`
- `hardware_context`
- `required_checks`
- `handoff_kind`
- `unsafe_to_continue`

第一阶段 `handoff_kind`：
- `ai_to_human`
- `ai_to_backend`
- `human_to_runner`

接口层必须满足：
- 高风险 handoff 必须允许关联 `linked_approval_ids`
- `unsafe_to_continue=true` 时，任何自动消费逻辑都必须阻断
- 读取接口必须返回风险摘要、检查项、硬件上下文

最小验收标准：
- 能创建“等待人工审批”的高风险 handoff
- 能读取 `unsafe_to_continue` 和结构化风险上下文
- 高风险 handoff 不会误入自动续跑路径

是否需要测试：
- 需要

红线守卫测试：
- `unsafe_to_continue=true` 的 handoff 进入自动续跑时失败
- 高风险 handoff 能正确挂接审批记录

### 票据 4：`lab` 真实实验记录

建议 owner：
- 后端 `lab` 模块负责人

本票据要交付：
- 承载真实硬件实验记录、证据路径和结果摘要，补齐执行证据链

最小 `payload`：
- `device_id`
- `experiment_type`
- `experiment_stage`
- `operator_user_id`
- `evidence_files`
- `firmware_version`
- `result_summary`

接口层必须满足：
- 高风险任务进入真实硬件实验链时，不能跳过人工审核阶段
- `task_id` 必须可关联
- `evidence_files` 至少支持路径列表读写

最小验收标准：
- 能写入并读取一条真实硬件实验记录
- 记录中包含设备、操作者、结果摘要、证据路径
- 高风险实验链不能绕过人工阶段直接完成

是否需要测试：
- 需要

红线守卫测试：
- 高风险实验记录若跳过人工审核阶段，请求失败
- `task_id`、证据路径、结果摘要可正常写入读取

### 票据 5：统一红线守卫测试

建议 owner：
- 后端测试 owner，或四个模块负责人联合补齐

本票据要交付：
- 用最小自动化测试固定“高风险硬件动作必须人工确认”这条红线

必须覆盖场景：
- 高风险硬件任务不能绕过 `requires_human_approval`
- 高风险审批不能缺模板和回退方案
- `unsafe_to_continue=true` 的交接不能进入自动续跑
- 高风险实验记录不能绕过人工阶段直接完成

最小验收标准：
- 四类红线至少各有 1 条自动化测试
- 任一红线被破坏时，测试必须失败

是否需要测试：
- 必须

### 统一红线重申

以下动作只要命中高风险条件，就必须经过人工确认：
- `firmware_flash`
- `parameter_write`
- `actuator_motion`

这条门槛必须同时存在于：
- `tasks` 风险字段
- `approvals` 审批结构
- `handoffs` 阻断标记
- `lab` 阶段限制
- 自动化测试失败用例

以下做法一律不合格：
- 只在前端隐藏按钮或弹窗提醒
- 只在文档或备注中写“需要人工确认”
- 只靠 Runner 默认不执行
- 只靠默认流转“通常不会走到这里”
- 只靠临时兜底逻辑拦截

### 本轮更新（Boss 要求继续压实后端实施单后）

- 已把现有内容继续收成“后端实施单 v3（领票执行版）”
- 每张票据都按“交付内容 / 必须落地字段 / 接口层必须满足 / 最小验收标准 / 是否需要测试 / 红线守卫测试”整理
- 再次固化红线：高风险硬件动作必须人工确认，且不能被任何自动化、默认流转和临时兜底绕开
## 主世界统一约束

后续所有映射与实施建议，统一以当前搬进来的开源农场游戏为唯一主世界、唯一空间基底、唯一视觉母体。

对 AI-4 这条线的直接约束：
- 不再假设存在第二套页面、第二套城镇、第二套基地页
- `tasks / approvals / handoffs / lab` 的映射，最终都应服务同一张游戏地图里的建筑、房间、入口、交互点和经营循环
- AI、电脑、Runner、人工审批、构建、交付等真实研发动作，只能映射成这套农场游戏主世界里的系统与机制，不能脱离地图另起炉灶
- 后端结构即使先行落地，也应以“回接这张地图中的真实玩法节点”为目标，而不是支持另一套后台式空间

对后续接手方的判断标准：
- 如果一个方案需要新开第二套经营页来承接玩法，应视为偏离方向
- 如果一个系统不能回落到现有农场地图中的建筑或场景节点，应优先重审映射是否错位
- HUD、任务循环、审批门槛、交付反馈都应附着在同一主世界中，而不是拆成卡片化后台页

对美术与资源适配的影响：
- 优先围绕这套开源农场游戏寻找现成同风格素材
- 不自己另画一套不搭的资源母体
- 不再把真实研发系统包装成脱离地图的后台卡片页

### 本轮补充说明（收到 Boss 主世界统一规则后）

- 已把“开源农场游戏地图是唯一主世界”写入 AI-4 handoff
- 后续 AI-4 的映射与实施拆解将默认以这张地图为唯一空间承载，不再为第二套页面提供结构前提
## 地图空间落点约束

这条线后续不能停留在抽象系统说明。所有“真实研发动作 -> 游戏机制”的映射，最终都必须继续落到当前开源农场游戏地图里的具体空间节点。

AI-4 后续默认使用的空间锚点：
- 建筑：承载不同研发阶段的功能建筑
- 门岗：承载审批、放行、阻断、人工确认
- 工位：承载 AI / 电脑 / Runner / 人工协作执行位
- 实验区：承载真实硬件实验、验证、证据记录、风险隔离

判断标准：
- 如果一个映射找不到对应建筑、门岗、工位或实验区，就说明还没映射完成
- 如果一个机制只能停留在后台字段层，而不能回接到地图中的空间节点，就说明仍然偏抽象

## 真实研发动作 -> 地图空间节点 -> 后端机制

这一节把 AI-4 的映射继续从“系统层”压到“地图空间层”，方便后续 AI-1 / AI-2 / AI-5 接手时，知道这些后端结构最终应该附着在哪些地图节点上。

### 收需求

地图空间节点：
- 需求受理建筑
- 前台接待工位

对应后端机制：
- `tasks` 的任务入口
- 需求转任务的创建动作

映射要求：
- 不能只表现为一个弹窗表单
- 必须在地图里对应一个真正接单、排队、转单的建筑/工位

### 拆任务

地图空间节点：
- 规划工位
- 调度桌

对应后端机制：
- `tasks` 的字段拆分
- 优先级、模块、目标设备、风险等级

映射要求：
- 玩家应理解这是“把需求拆成可执行工单”的空间动作
- 不应漂浮成与地图无关的抽象列表

### 派 AI

地图空间节点：
- AI 工位
- 协作席位

对应后端机制：
- `tasks.assignee_agent_id`
- `required_runner_capabilities`
- 角色链中的 AI 产消位

映射要求：
- 派 AI 不是纯文本说明，而是地图里的工位分配行为

### 派电脑 / 派 Runner

地图空间节点：
- 机房工位
- 电脑节点区

对应后端机制：
- 电脑能力匹配
- Runner capability 约束
- 后续 `tasks` / `handoffs` 对执行能力的要求

映射要求：
- 必须让玩家知道是“哪台机子/哪类执行位”接了任务
- 不能只在后台静默完成

### Runner 执行

地图空间节点：
- 执行工位
- 构建机位

对应后端机制：
- 任务执行态
- 运行日志
- 构建产物

映射要求：
- 可以自动执行的软件动作落在执行工位
- 但高风险硬件动作不能在这里被直接自动通关

### 文件边界

地图空间节点：
- 工位权限区
- 文件移交桌

对应后端机制：
- handoff payload
- 文件范围
- required checks

映射要求：
- 文件边界要被表现成“谁能碰哪块工作台/资料区”
- 不能只是一句文档备注

### 交接

地图空间节点：
- 交接台
- 调度中枢

对应后端机制：
- `handoffs`
- `handoff_kind`
- `unsafe_to_continue`

映射要求：
- 交接一定要有明确空间节点，不能漂在系统外
- 高风险任务交接要能在地图里被看作“停在门口等人接”

### 人工审批

地图空间节点：
- 门岗
- 审批岗亭

对应后端机制：
- `approvals`
- `approval_template`
- `preflight_checklist`

映射要求：
- 这是 AI-4 的核心红线落点
- 高风险硬件动作必须卡在门岗/岗亭，不能从执行工位直接穿过去

### 构建

地图空间节点：
- 构建车间
- 打包工位

对应后端机制：
- 构建状态
- 产物生成
- 可交付包

映射要求：
- 构建可以自动化
- 但构建结果进入高风险硬件执行前，仍要回到人工审批门岗

### 交付

地图空间节点：
- 出货口
- 交付码头

对应后端机制：
- 交付状态
- 最终产物
- 审批后的放行

映射要求：
- 交付不是后台完成提示，而是地图里明确的“放行/出货”结果

### 真实硬件实验

地图空间节点：
- 实验区
- 隔离测试区

对应后端机制：
- `lab`
- `experiment_stage`
- `evidence_files`

映射要求：
- 所有真实硬件实验必须回到实验区
- 不能被当成普通 Runner 工位自动执行
- 必须能沉淀证据链

## 高风险动作的地图阻断点

以下动作在地图里必须被阻断在“门岗/审批岗亭 -> 实验区”链路上，不能直接从工位自动越过：
- `firmware_flash`
- `parameter_write`
- `actuator_motion`

正确地图链路应为：
1. 任务在建筑/工位中形成执行准备
2. 到门岗/审批岗亭等待人工确认
3. 放行后进入实验区
4. 在实验区留下证据与结果
5. 再决定是否允许交付或继续下一步

不合格映射：
- 直接从 AI 工位自动跳到“已完成”
- 直接从机房工位自动刷写硬件
- 只在后台状态里写 `approved`，但地图里没有门岗阻断
- 只在日志里写实验成功，但地图里没有实验区承载

### 本轮补充说明（收到“必须映射到建筑/门岗/工位/实验区”要求后）

- 已把 AI-4 映射从抽象系统层继续压到地图空间层
- 新增了“真实研发动作 -> 地图空间节点 -> 后端机制”映射
- 再次明确红线：高风险硬件动作必须卡在门岗与实验区链路中，不能被自动执行
