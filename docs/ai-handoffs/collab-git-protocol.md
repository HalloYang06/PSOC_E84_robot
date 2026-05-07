# AI 协作 Git 与交接协议

版本：v1.0  
角色：AI-6 / 协作秩序维护  
建议分支：`ai/collab-git-protocol`

## 1. 目的

本协议用于约束多 AI 并行开发时的 Git、文档、交接和截图验收行为，保证任何一个 AI 都能通过仓库内文档和 Git 历史接手工作，而不是依赖聊天记录。

本协议只负责协作秩序，不负责玩法实现、数值平衡、地图设计、HUD 设计或后端业务实现。

当前主线约束：

1. 后续一切实现统一收口到 `projects/[id]` 主线
2. 不再继续扩第二套“基地页”或平行壳层
3. 主循环、经营系统、建筑气质、HUD 反馈必须往同一条主线里收敛
4. 目标是做成一条真正可成长的养成经营游戏主线，而不是多套页面外壳并存

当前世界基底约束：

1. 所有开发都以当前搬进来的开源农场游戏为唯一主世界
2. 所有空间组织都以这套开源农场游戏地图为唯一空间基底
3. 所有视觉延展都以这套开源农场游戏为唯一视觉母体
4. 不再各自新做第二套页面、第二套城镇、第二套基地页
5. 所有玩法、建筑、经营系统、HUD、任务循环、AI / 电脑 / 审批 / 交付，都必须基于这套游戏地图实现和适配
6. 可以补功能、补状态、补交互、补经营循环，但不能脱离这张游戏地图另起炉灶
7. 美术资源优先围绕这套游戏找现成同风格素材，不自己画，不再做不搭的卡片化后台页

---

## 2. 所有 AI 的强制入口规则

所有 AI 开始工作前，必须按以下顺序执行：

1. 先读 `多AI并行开发分工说明-2026-04-20.md`
2. 再读 `AI协作平台开发文档.md`
3. 再读 `docs/ai-handoffs/boss-dispatch-board.md`
4. 再读 `docs/ai-handoffs/ai-thread-report-template.md`
5. 如需向 Boss 汇报，再读 `docs/ai-handoffs/boss-intake-format.md`
6. 确认自己负责范围、可修改目录、不可修改目录
7. 确认当前任务对应分支、交接文档、截图验收要求

所有 AI 必须额外遵守以下强制规则：

1. 不要直接推 `main`
2. 不要改超出自己负责范围的文件
3. 必须维护自己的 `docs/ai-handoffs/<role>.md`
4. 改完必须自己截图验证
5. 通过 Git 和文档交流，不靠长聊天记录
6. 临时 demo 和验证开关最后要删

---

## 2.1 统一入口

从当前阶段开始，多 AI 协作默认不再依赖自由发挥，而是统一从以下入口组合进入：

1. 基础执行入口：`docs/ai-handoffs/unified-agent-prompt.md`
2. 自治推进入口：`docs/ai-handoffs/autonomous-taskloop.md`
3. 收尾输出入口：`docs/ai-handoffs/handoff-path-output.md`
4. Boss 调度入口：`docs/ai-handoffs/boss-dispatch-loop.md`
5. Boss 实时判断板：`docs/ai-handoffs/boss-dispatch-board.md`
6. 线程回报模板：`docs/ai-handoffs/ai-thread-report-template.md`
7. Boss 收件格式：`docs/ai-handoffs/boss-intake-format.md`

### 2.2 各入口职责

1. `unified-agent-prompt.md` 负责统一所有 AI 的共同行为边界
2. `autonomous-taskloop.md` 负责让 AI 在自己职责内持续推进，不因每个小步骤都停下
3. `handoff-path-output.md` 负责强制最终回复输出交接文档路径，并要求交接文档标明身份
4. `boss-dispatch-loop.md` 负责 Boss 如何持续读取 handoff、判断状态、更新调度
5. `boss-dispatch-board.md` 负责当前阶段的真实优先级、状态灯和是否继续推进
6. `ai-thread-report-template.md` 负责每一轮工作后 handoff 文档的标准写法
7. `boss-intake-format.md` 负责向 Boss 回报时的最小结构化输入

### 2.3 默认使用顺序

普通执行角色默认按以下顺序使用：

1. 读取 `unified-agent-prompt.md`
2. 读取 `boss-dispatch-board.md`
3. 读取自己的 `docs/ai-handoffs/<role>.md`
4. 在职责范围内按 `autonomous-taskloop.md` 推进
5. 每轮结束按 `ai-thread-report-template.md` 更新 handoff
6. 对 Boss 回报时按 `boss-intake-format.md` 输出
7. 最终回复必须遵守 `handoff-path-output.md`

Boss 角色默认按以下顺序使用：

1. 读取 `boss-dispatch-loop.md`
2. 读取各角色 handoff 文档
3. 参考截图和验证结果
4. 更新 `boss-dispatch-board.md`
5. 继续派工或标记 `进行中 / 待验收 / 待接手 / 阻塞`

### 2.4 统一入口的执行要求

1. 这套入口组合是并行开发的默认入口，不再靠聊天临时补规则
2. 若某角色提示词与统一入口冲突，以仓库内最新 handoff 协议和 Boss 调度文档为准
3. 若技能名、文档名或旧叫法不一致，优先以仓库内现行文档路径为准，避免因为名称漂移导致执行分叉

---

## 2.5 入口名称收敛规则

多 AI 并行开发时，入口名称必须收敛到单一口径。任何文档、skill、handoff、Boss 回报里出现旧叫法，都必须能映射回当前标准名。

### 现行标准名

| 入口类型 | 当前标准名 | 当前标准路径 |
|---|---|---|
| 统一执行提示 | `unified-agent-prompt` | `docs/ai-handoffs/unified-agent-prompt.md` |
| 自治推进入口 | `autonomous-taskloop` | `docs/ai-handoffs/autonomous-taskloop.md` |
| 收尾输出入口 | `handoff-path-output` | `docs/ai-handoffs/handoff-path-output.md` |
| Boss 调度入口 | `boss-dispatch-loop` | `docs/ai-handoffs/boss-dispatch-loop.md` |
| Boss 调度板 | `boss-dispatch-board` | `docs/ai-handoffs/boss-dispatch-board.md` |
| 线程汇报模板 | `ai-thread-report-template` | `docs/ai-handoffs/ai-thread-report-template.md` |
| Boss 收件格式 | `boss-intake-format` | `docs/ai-handoffs/boss-intake-format.md` |

### 已知旧称与别名

| 旧称或别名 | 应收敛到 | 说明 |
|---|---|---|
| `handoff-path-closeout` | `handoff-path-output` | 本地已创建的 closeout skill 名，与仓库文档口径不一致；仓库协作口径统一回 `handoff-path-output` |
| `Boss 调度入口` | `boss-dispatch-loop` | 口语描述允许存在，但文档和 handoff 中优先写标准名 |
| `Boss 调度板` | `boss-dispatch-board` | 对外可写中文说明，但路径和引用应写标准文件名 |
| `AI 线程汇报模板` | `ai-thread-report-template` | 同上，优先保留标准路径 |
| `Boss 收件格式` | `boss-intake-format` | 同上，避免一个入口多种英文名并存 |

### 清理要求

1. 新增文档、handoff、技能说明时，优先使用当前标准名
2. 若必须提旧称，必须写成“旧称 -> 标准名”的映射，不允许只写旧称
3. Boss 派工、handoff 模板、最终回复、仓库协议，四处必须优先使用标准名
4. 不允许一个入口同时出现两个“看起来都是正式名”的写法
5. 若未来决定重命名某入口，必须先更新本协议中的标准名表，再批量改其他文档

### 清理顺序

1. 先以本协议定义标准名
2. 再以 Boss 调度文档统一引用
3. 再清理角色 handoff 中的旧称
4. 最后再处理本地 skill 目录名与仓库文档名是否对齐

这样做的目的是先稳定仓库协作口径，再处理本地实现细节，避免多人同时改名导致入口再次漂移。

### 第一批清理目标

当前阶段优先清理以下文档中的旧称、重复入口叫法和混用描述：

1. `docs/ai-handoffs/boss-dispatch-board.md`
2. `docs/ai-handoffs/unified-agent-prompt.md`
3. 各角色 `docs/ai-handoffs/<role>.md` 中对统一入口的引用

第一批清理只做“命名收敛”和“路径对齐”，不改各角色的业务判断、验收结论或实现方向。

### 第二批清理目标

第一批完成后，继续清理以下内容，直到仓库里只保留一套标准引用：

1. 各角色 handoff 中残留的旧入口叫法
2. 各角色 handoff 中残留的旧 skill 路径
3. 提示词文档中的重复入口描述
4. 同一个入口既写标准名、又写另一个像正式名的别名

### 仓库统一引用要求

从现在开始，仓库内的协议、提示词、Boss 调度文档、角色 handoff，统一遵守以下要求：

1. 一个入口只保留一个标准英文名
2. 中文说明只能作为解释，不能替代标准名
3. 路径引用优先写仓库内标准文档路径
4. 如果某个本地 skill 目录名与仓库标准名不一致，仓库文档仍以标准名为准
5. 交接文档里不再扩散个人机器上的旧 skill 目录名，避免后续协作引用漂移

### 完成标准

AI-6 这条线的“统一入口收敛”只有在以下条件同时满足时才算完成：

1. `docs/ai-handoffs/` 下关键入口文档全部只使用标准名
2. 角色 handoff 中不再出现会造成歧义的旧称
3. 不再出现 `handoff-path-closeout` 这类会与标准名并存的正式引用
4. Boss 派工、线程汇报、最终回复三类入口都能回指到同一套标准名表

---

### 第二批当前进度

本轮已经开始清理第二批目标中的以下项目：

1. 给 `autonomous-taskloop.md`、`boss-dispatch-loop.md`、`handoff-path-output.md` 增加“标准引用”段
2. 开始逐份清理角色 handoff 中扩散 `skills/...` 目录路径的写法，统一回 `docs/ai-handoffs/...` 标准文档路径
3. 先从统一入口文档本身收口，再逐步清理角色 handoff，避免多人协作时边改边漂移
4. 继续清理入口 handoff 中对本地 skill 实现细节的默认引用，只保留仓库侧标准入口说明
5. 优先清理高频角色 handoff 和核心入口文档，先消除最容易被反复复制的旧引用

后续继续按同样方式逐份清理其他角色 handoff，直到 `docs/ai-handoffs/` 下不再扩散旧 skill 路径。

### 高频角色优先策略

第二批清理默认优先处理以下高频 handoff：

1. `docs/ai-handoffs/game-loop-core.md`
2. `docs/ai-handoffs/economy-balance.md`
3. `docs/ai-handoffs/game-hud-feedback.md`

原因：

1. 这三条线处在 Boss 调度高频区域
2. 这三条线最容易被继续抄作模板或复用描述
3. 先把高频 handoff 的标准引用钉住，能更快降低后续入口漂移

当前进度：

1. 高频角色 handoff 已开始补“统一入口引用”
2. 核心入口文档已开始改成“标准名 + 中文说明”的单一写法

---

## 3. 分支命名规范

### 3.1 总规则

1. 一个角色一条任务线，不共用模糊分支
2. 一个分支只解决一个明确目标
3. 不允许多个 AI 长时间共同写同一分支
4. 不允许把未说明来源的临时改动混入交付分支
5. 不允许直接在 `main` 上开发、提交、推送

### 3.2 推荐格式

```text
ai/<role>-<topic>
```

或在需要更强任务标识时使用：

```text
ai/<role>/<task-id>-<topic>
```

### 3.3 推荐示例

```text
ai/game-loop-core
ai/building-scenes
ai/economy-balance
ai/embedded-mapping
ai/game-hud-feedback
ai/collab-git-protocol
ai/fe-game/TASK-012-dashboard-base
ai/be-task/TASK-021-task-api
```

### 3.4 分支使用要求

1. 开工前先确认当前分支是否匹配本次职责
2. 若分支职责已变化，必须新开分支，不在旧分支硬改方向
3. 分支名必须能看出角色或任务目标，禁止使用 `test`、`temp`、`fix1`、`new-branch`
4. 若任务需要跨模块协作，分支名之外还必须在交接文档里写清影响范围

---

## 4. Commit 规范

### 4.1 格式

```text
<type>(<scope>): <summary>
```

### 4.2 允许的 type

```text
feat
fix
docs
refactor
test
chore
style
infra
security
```

### 4.3 示例

```text
docs(collab): add multi-ai git handoff protocol
docs(ai-handoffs): add AI-6 handoff template and screenshot checklist
fix(game-hud): remove temporary verification toggle after screenshot pass
chore(web): delete temporary demo entry used during visual validation
```

### 4.4 提交要求

1. 一次 commit 只表达一类变化
2. commit 标题必须写结果，不写流水账
3. 若引入临时验证代码，必须在后续 commit 中明确删除
4. 文档改动和实现改动混在一起时，优先拆成两个 commit
5. 无法验证时，必须在 commit 对应的交接文档里写明原因和风险

---

## 5. Git 交流协议

多 AI 之间默认通过以下载体交流，而不是靠聊天上下文：

1. 分支名
2. commit 历史
3. `docs/ai-handoffs/<role>.md`
4. PR 描述或合并说明
5. 截图验收记录

### 5.1 交接优先级

接手者应优先读取：

1. 当前任务相关分支名
2. 最近 commit
3. 对应角色的 `docs/ai-handoffs/<role>.md`
4. 相关截图和验收结论
5. 再去读必要源码

### 5.2 不允许的交流方式

1. 只在聊天里说明“我改过了”，但仓库无文档留痕
2. 只留截图，不说明分支、文件和结论
3. 只留代码，不更新交接文档
4. 把关键风险只口头说明，不写入文档

---

## 6. `docs/ai-handoffs/<role>.md` 维护规范

每个 AI 都必须维护自己的角色交接文档，例如：

```text
docs/ai-handoffs/ai-6-collab-git-protocol.md
docs/ai-handoffs/ai-1-game-loop.md
docs/ai-handoffs/ai-5-game-hud-feedback.md
```

### 6.1 必填字段

```md
# 角色

## 身份信息
- AI 身份：
- 角色名：
- 交接人：

## 当前任务
- 任务名称：
- 当前分支：
- 负责范围：
- 不负责范围：

## 已完成
- 

## 本次修改文件
- 

## 当前状态
- 进行中 / 已完成 / 阻塞

## 截图验证
- 截图路径：
- 验证时间：
- 验证结论：

## 风险与遗留
- 

## 下一位接手者须知
- 
```

### 6.2 更新时机

1. 开始接任务时更新“当前任务”
2. 改完代码或文档后更新“已完成”和“本次修改文件”
3. 截图验证后补齐“截图验证”
4. 准备交接时必须写“风险与遗留”和“下一位接手者须知”

---

## 7. 标准交接模板

以下模板可直接复制进对应 `docs/ai-handoffs/<role>.md`：

```md
# AI 交接记录

## 任务信息
- AI 身份：
- 角色：
- 任务名称：
- 当前分支：
- 对应 commit：
- 更新时间：

## 负责范围
- 我负责：
- 我不负责：

## 已完成事项
- 

## 修改文件
- 

## 验证结果
- 使用方式：
- 截图路径：
- 结果说明：

## 未完成事项
- 

## 风险
- 

## 接手建议
- 下一位 AI 应先读哪些文件：
- 不要重复做什么：
- 优先处理什么：
```

---

## 8. 截图验收模板

所有 AI 改完后都必须自己截图验证，截图不是可选项。

### 8.1 截图最低要求

1. 截到本次改动实际生效的界面或结果
2. 截图文件名要能看出角色、日期、内容
3. 截图结论必须写进对应交接文档
4. 截图不能替代文字说明，必须同时写明“看到了什么、说明什么”

### 8.2 推荐命名

```text
artifacts/screenshots/<yyyy-mm-dd>/<role>-<topic>-01.png
```

示例：

```text
artifacts/screenshots/2026-04-20/ai-6-collab-git-protocol-01.png
```

### 8.3 截图验收记录模板

```md
## 截图验收
- 截图路径：
- 验证人：
- 验证时间：
- 验证环境：
- 验证步骤：
- 期望结果：
- 实际结果：
- 是否通过：是 / 否
- 如未通过，阻塞点：
```

### 8.4 截图验收判定

通过截图验收，至少要满足：

1. 能看出本次改动已经落地
2. 能看出没有明显错位、缺文案、空白页、报错遮挡
3. 能让接手者知道该改动现在哪个状态可用

---

## 9. PR / 合并说明模板

若使用 PR 或等价合并流程，说明中至少包含：

```md
## 任务
- 名称：
- 角色：
- 分支：

## 本次交付
- 

## 修改文件
- 

## 自测
- 命令或操作：
- 截图路径：
- 结果：

## 风险
- 

## 交接说明
- 后续接手文档：
- 需要关注的遗留事项：
```

---

## 10. 禁止事项

以下行为一律视为违反协作协议：

1. 直接推送或合并到 `main`
2. 修改超出自己职责边界的文件
3. 未更新 `docs/ai-handoffs/<role>.md` 就宣称完成
4. 未截图验证就宣称完成
5. 依赖长聊天记录作为唯一交接方式
6. 在提交中混入无关改动
7. 长时间占用同一分支却不留交接记录
8. 保留临时 demo、调试入口、验证开关不清理
9. 用“先这样以后再删”作为不清理临时代码的理由
10. 覆盖别人负责范围内的实现但不写说明
11. 不说明风险就交接
12. 用模糊 commit 信息掩盖真实改动

---

## 11. 执行结论

从本协议开始，所有 AI 的最小交付单元不再只是“代码改完”，而是：

1. 在正确分支上完成修改
2. 用规范 commit 留痕
3. 更新自己的 `docs/ai-handoffs/<role>.md`
4. 自己截图验证
5. 删除临时 demo 与验证开关
6. 让下一位接手者只靠 Git 和文档就能继续工作

满足以上 6 项，才算完成一次可接手的并行协作交付。
