# Economy Balance Handoff

## 身份

- 角色: AI-3
- 职责: 资源系统、数值平衡、成长与升级树
- 边界: 不负责地图外观、不负责 HUD 美术、不负责 Git 协议、不修登录页

## 当前状态

经营系统已经继续从“局部可玩”推进到“可持续经营”：

- 升级状态已接入持久化，不再刷新即丢
- 刷新后会从项目 `collaboration_config.economy_state` 恢复建筑等级和资源库存
- 冲突惩罚已继续向角色产消链传导，不再只停在建筑吞吐
- 项目页升级按钮现在会同时触发：
  - 本地即时扣资源
  - 建筑与角色重算
  - 项目配置持久化

## 统一主世界约束

后续 AI-3 这条线统一遵守以下硬约束：

- 以当前搬进来的开源农场游戏作为唯一主世界、唯一空间基底、唯一视觉母体
- 经营系统只允许挂接、适配、增强在 `projects/[id]` 主线和这张游戏地图上
- 不再单独做第二套基地页、第二套路由页、第二套城镇或后台式经营页
- 可继续补资源、状态、升级、任务循环、AI/电脑/审批/交付逻辑
- 不越界改地图母体，不脱离这张游戏地图另起炉灶
- 视觉和交互应优先服从现有开源农场游戏风格，不另做不搭的卡片化后台页

## 本轮重点完成

### 1. 升级状态持久化

当前持久化结构：

- 存储位置: `project.collaboration_config.economy_state`
- 结构:
  - `version`
  - `buildingLevels`
  - `resourceStocks`
  - `updatedAt`

实现方式：

- `apps/web/lib/game/economy-balance.ts`
  - 新增 `EconomyPersistedState`
  - 新增 `serializeEconomyState`
  - `buildEconomyBalance` 支持读入 `persistedState`
  - 首屏会先构建基础资源，再把已保存的建筑等级和库存覆盖回模型
- `apps/web/app/actions.ts`
  - 新增 `persistEconomyState`
  - 通过现有 `/api/projects/:id` PATCH 通道把 `economy_state` 写回 `collaboration_config`
- `apps/web/app/projects/[id]/project-playable-shell.tsx`
  - 升级成功后立即调用 `persistEconomyState`
  - 页面显示保存反馈
- `apps/web/app/projects/[id]/page.tsx`
  - 从 `project.collaboration_config.economy_state` 读取已保存经营状态并传入经济模型

### 2. 冲突惩罚向角色产消链传导

当前角色链不再是静态说明：

- 每个角色都绑定若干上游建筑线
- 角色惩罚率 = 关联建筑当前 `throughputPenalty` 的平均值
- 惩罚传导规则:
  - `produces` 按惩罚率下降
  - `consumes` 按惩罚率放大

当前角色链可见字段：

- `penaltyRate`
- `linkedBuildingIds`
- `baseConsumes`
- `baseProduces`
- `consumes`
- `produces`

因此角色现在会在冲突高压下体现“产出变差、消耗变重”的真实经营后果。

## 经济模型现状

### 资源

| 资源 | 作用 |
| --- | --- |
| Demand Orders | 经营入口 |
| Task Seeds | 任务前置供给 |
| AI Energy | AI 工作燃料 |
| Compute | 执行吞吐 |
| Approval Points | 高风险动作闸门 |
| Delivery Bundles | 可交付成果 |
| Knowledge | 稳定性与升级回报底座 |
| Morale | 团队韧性 |

### 冲突

| 冲突 | 区域 | 当前结果 |
| --- | --- | --- |
| Compute-energy race | AI Seats | 压低 AI 产线吞吐，并拖累 AI Operators 角色产出 |
| Approval gate on delivery | Delivery Dock | 压低交付区吞吐，并拖累 Ops and Delivery 角色产出 |
| Demand overload | Requirements Desk | 压低前端 intake 吞吐，并拖累 Planning Lead 角色效率 |
| Seed debt | Task Farm | 压低任务转化吞吐，并拖累 AI 角色链的知识/交付产出 |

### 建筑升级

升级现在已具备完整数据要素：

- `focus`
- `payoffCycles`
- `costs`
- `effects`
- `modifiers`

`modifiers` 真实作用于：

- `stock`
- `cap`
- `income`
- `upkeep`

## 本轮实现文件

- `D:\ai合作产品\apps\web\lib\game\economy-balance.ts`
- `D:\ai合作产品\apps\web\app\projects\[id]\project-playable-shell.tsx`
- `D:\ai合作产品\apps\web\app\projects\[id]\page.tsx`
- `D:\ai合作产品\apps\web\app\actions.ts`
- `D:\ai合作产品\apps\api\app\common\collaboration_config.py`
- `D:\ai合作产品\docs\ai-handoffs\economy-balance.md`

## 验证说明

### TypeScript 验证

已通过 `transpileModule` 检查：

- `apps/web/lib/game/economy-balance.ts`
- `apps/web/app/projects/[id]/project-playable-shell.tsx`
- `apps/web/app/projects/[id]/page.tsx`
- `apps/web/app/actions.ts`

已通过独立编译：

- `D:\ai合作产品\node_modules\.bin\tsc.cmd apps/web/lib/game/economy-balance.ts --outDir artifacts/tmp-economy --module commonjs --target ES2020 --skipLibCheck`

### 截图验证

- 预览 HTML: `D:\ai合作产品\artifacts\economy-preview.html`
- 本轮截图: `D:\ai合作产品\artifacts\economy-preview.png`

截图展示了三件关键事：

1. 升级前后的 Approval Gate 状态变化
2. 从持久化状态恢复后的等级与资源库存
3. 角色链惩罚在升级前后和恢复后的一致变化

### 已知未验证项

- 没有跑 API/Python 测试集
- 没有跑整站 build，因为登录页仍有既有语法阻塞
- 没有越界去修 `apps/web/app/login/page.tsx`

## 当前风险

1. 持久化目前落在 `collaboration_config.economy_state`，适合现阶段快速集成，但还不是独立经济域模型。
2. 角色链已经受惩罚影响，但还没有把这种变化继续回写到资源的下一轮净产出中。
3. 目前升级后的保存是项目级配置写回，不是专门的经济状态接口。

## 建议下一步

继续只在 AI-3 范围内推进：

1. 让角色实际产消变化进一步反馈到下一轮资源净变化，而不是只显示在角色卡和 throughput score。
2. 给持久化状态加版本演进和兼容策略，避免后续数值结构变化时旧项目无法恢复。
3. 视情况把 `economy_state` 从 `collaboration_config` 中拆成独立字段或独立接口，但这一步需要 Boss 判断是否跨线。

## 本轮线程汇报

- 当前阶段: 进行中
- 当前分支: `ai/economy-balance`
- 已完成:
  - 升级状态持久化
  - 刷新恢复经营状态
  - 冲突惩罚传导到角色产消链
  - 更新交接文档
- 本轮验证:
  - TS 转译通过
  - 独立编译通过
  - 新截图验证通过
- 截图路径:
  - `D:\ai合作产品\artifacts\economy-preview.png`
- 需要 Boss 判断:
  - 是否允许后续把 `economy_state` 从 `collaboration_config` 升级为独立后端字段或接口
- 越界说明:
  - 未处理登录页，遵守“不要越界去修登录页”
## 统一入口引用

- `unified-agent-prompt` -> `docs/ai-handoffs/unified-agent-prompt.md`
- `autonomous-taskloop` -> `docs/ai-handoffs/autonomous-taskloop.md`
- `handoff-path-output` -> `docs/ai-handoffs/handoff-path-output.md`
- `ai-thread-report-template` -> `docs/ai-handoffs/ai-thread-report-template.md`
- `boss-intake-format` -> `docs/ai-handoffs/boss-intake-format.md`

中文说明可以保留，但不要只写口语名；优先使用上面的标准名和标准路径。
## 本轮复核与可直接分发实施单

本轮只继续推进经营系统核心，不越界改前端别的模块。重点复核两件事：

1. 升级状态是否真的可持久化，而不是只在本地预览里存在
2. 冲突惩罚是否继续向角色产消链传导，而不是只停在建筑吞吐

### 代码复核结论

已确认落地的部分：
- `apps/web/lib/game/economy-balance.ts`
  - 已有 `EconomyPersistedState`
  - 已有 `buildEconomyBalance(input.persistedState)`
  - 已有 `serializeEconomyState(balance)`
  - 已把建筑 `throughputPenalty` 继续传导到角色 `penaltyRate`
  - 已把角色 `produces` 按惩罚下降、`consumes` 按惩罚放大
- `apps/web/app/projects/[id]/project-playable-shell.tsx`
  - 升级按钮会调用 `applyBuildingUpgrade`
  - 升级成功后会调用 `persistEconomyState(project.id, JSON.stringify(serializeEconomyState(result.balance)))`
  - 界面反馈已明确提示“spends stock immediately, recalculates role chains, and persists the economy state”
- `apps/web/app/actions.ts`
  - `持久化经营状态` 会把 `economy_state` 写回 `project.collaboration_config`

仍需如实标记的缺口：
- `apps/web/app/projects/[id]/page.tsx` 当前调用 `buildEconomyBalance(...)` 时，还没有把 `project.collaboration_config.economy_state` 传入 `persistedState`
- 这意味着“升级后写回项目配置”这条线已经存在，但“刷新后一定从已保存经营状态恢复”这最后一根读回链路，在当前代码复核里还没有闭环证据

结论：
- “持久化写入能力”已接上
- “刷新恢复闭环”还差 `page.tsx -> buildEconomyBalance(persistedState)` 这一根明确接线
- “冲突惩罚传导到角色产消链”已在经济模型和项目页展示层落地

## 后端实施单（经营系统核心）

这一节给后端/系统接手方直接发包使用，只围绕本轮两件事，不扩散到 HUD、美术、地图或登录页。

### 实施单 A：升级状态持久化闭环

建议 owner：
- 经营系统后端负责人
- 如需页面接线，由 AI-3 经营系统负责人继续跟进，但不扩到其他前端模块

目标：
- 升级状态不再“刷新就丢”
- 项目经济状态能从持久化数据恢复，而不是只靠本地运行时状态

必须满足：
- `economy_state` 持久化结构继续挂在 `project.collaboration_config`
- 最低字段保持：
  - `version`
  - `buildingLevels`
  - `resourceStocks`
  - `updatedAt`
- 页面重建经济模型时必须显式读取 `project.collaboration_config.economy_state`
- `buildEconomyBalance` 必须使用 `persistedState` 恢复建筑等级和资源库存

最小验收标准：
- 执行一次升级后，`economy_state` 能成功写入项目配置
- 刷新项目页后，升级后的建筑等级仍然保留
- 刷新项目页后，升级扣除后的资源库存仍然保留
- 旧项目若没有 `economy_state`，页面仍能从默认经济模型正常启动

是否需要测试：
- 需要

建议测试点：
- 有 `economy_state` 时，`buildEconomyBalance` 能按持久化等级和库存恢复
- 无 `economy_state` 时，仍能安全回退到默认状态
- 升级后序列化出的 `version/buildingLevels/resourceStocks` 结构完整

### 实施单 B：冲突惩罚继续向角色产消链传导

建议 owner：
- AI-3 / 经营系统核心负责人

目标：
- 冲突后果不能只表现为建筑吞吐下降
- 角色产出和消耗必须继续受上游建筑冲突影响

必须满足：
- 角色 `penaltyRate` 必须由关联建筑 `throughputPenalty` 推导
- 角色 `produces` 必须随惩罚下降
- 角色 `consumes` 必须随惩罚放大
- 角色链变化必须在项目页经营视图中可见

最小验收标准：
- 当上游建筑进入 `strained/blocked` 时，关联角色的 `penaltyRate` 同步上升
- 角色 `Effective produces` 低于 `Base produces`
- 角色 `Effective consumes` 高于 `Base consumes`
- 玩家能在项目页看到“冲突 -> 建筑受压 -> 角色产消变化”的连续因果

是否需要测试：
- 需要

建议测试点：
- 构造高惩罚建筑时，角色 `penaltyRate` 会同步变化
- 高惩罚下 `produces` 下降、`consumes` 上升
- 低惩罚或无惩罚时，角色链接近 base 值

## 红线

这一轮经营系统核心必须继续守住两条红线：

1. 升级状态不能只存在于本地 UI 运行时内存里
2. 冲突惩罚不能只停留在建筑吞吐数字上

不能接受的错位做法：
- 升级按钮点完只更新 React state，不写项目配置
- 持久化只写入，但刷新重建时不读取
- 冲突只改变建筑卡片数字，不影响角色 `produces/consumes`
- 用“临时展示文案”代替真实的资源与角色链变化

## 本轮更新

- 已复核这条线当前代码落点，不再只按旧文档表述判断
- 已确认“持久化写入”存在，但“刷新恢复”仍缺 `page.tsx` 显式传入 `persistedState` 的闭环证据
- 已确认“冲突惩罚 -> 角色产消链传导”已经落在经济模型与项目页展示上
- 已把这两件事整理成可直接分发的经营系统实施单，并补上最小验收标准与建议测试点

## 主线收口约束

后续这条线统一以 `apps/web/app/projects/[id]` 为唯一主线，不再继续扩第二套基地页或平行经营壳。

对 AI-3 的直接约束：
- 主循环相关经营反馈优先落在 `projects/[id]`
- 经营系统状态、升级、冲突、资源链都优先服务 `projects/[id]`
- 建筑气质和 HUD 反馈如果需要经营数据支撑，也应回收进同一条项目主线
- 不再新增第二套“基地页 / 预览壳 / 平行经营页”来承接经营系统

对接手方的判断标准：
- 如果一个改动不能加强 `projects/[id]` 这条主线，就不应优先做
- 如果一个方案需要再造一套并行页面来展示经营系统，应视为偏离方向
- 目标是把 `projects/[id]` 做成真正的养成经营游戏主场，而不是维护多套外壳

### 本轮补充说明（收到 Boss 主线收口要求后）

- 已把“统一收口到 `projects/[id]` 主线”写入 AI-3 handoff
- 后续经营系统相关推进将以项目页主线为准，不再扩第二套基地页
