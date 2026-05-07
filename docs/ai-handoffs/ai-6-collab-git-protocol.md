# AI 交接记录

## 任务信息
- AI 身份：AI-6
- 角色：AI-6
- 任务名称：多 AI Git 协作与文档协议 / 统一自治入口收口
- 当前分支：`ai/collab-git-protocol`
- 对应 commit：未提交
- 更新时间：2026-04-20

## 负责范围
- 我负责：统一 Git 分支规范、commit 规范、交接模板、截图验收模板、禁止事项
- 我不负责：地图实现、数值平衡、HUD 设计、后端业务功能

## 已完成事项
- 新增 `docs/ai-handoffs/collab-git-protocol.md`
- 将统一附加要求写入“所有 AI 的强制入口规则”
- 明确分支命名、commit 规范、handoff 模板、截图验收模板、禁止事项
- 将“完成任务必须在最终回复输出交接文档路径”固化为收尾规则，并统一按标准名 `handoff-path-output` 引用
- 将“交接文档必须标明身份”补入收尾规则和协议模板
- 从 `ai/game-loop-core` 切出独立分支 `ai/collab-git-protocol`
- 将 `autonomous-taskloop`、`handoff-path-output`、`boss-dispatch-loop`、Boss 调度板、线程汇报模板、Boss 收件格式收成统一入口并写入协作协议
- 在主协议中新增“现行标准名 / 旧称与别名 / 清理顺序”规则，开始收敛入口名称漂移
- 清理 `boss-dispatch-board.md`、`unified-agent-prompt.md`、`embedded-mapping.md` 中的旧称和口语名，统一回标准入口名
- 在主协议中补入“第二批清理目标”“仓库统一引用要求”“完成标准”，继续推动全仓只保留一套标准引用

## 修改文件
- `docs/ai-handoffs/collab-git-protocol.md`
- `docs/ai-handoffs/boss-dispatch-board.md`
- `docs/ai-handoffs/unified-agent-prompt.md`
- `docs/ai-handoffs/embedded-mapping.md`
- `docs/ai-handoffs/ai-6-collab-git-protocol.md`

## 验证结果
- 使用方式：人工回读主协议、Boss 调度板、统一提示词和角色 handoff，确认标准入口名已写入关键入口文档
- 截图路径：无，本轮无 UI 改动
- 结果说明：当前仓库口径继续向 `unified-agent-prompt / autonomous-taskloop / handoff-path-output / boss-dispatch-loop / boss-dispatch-board / ai-thread-report-template / boss-intake-format` 收敛，且 AI-6 handoff 已去掉个人机器旧 skill 路径引用

## 未完成事项
- 未执行 git commit

## 风险
- 当前工作区存在大量未跟踪文件，暂未切换分支，避免影响其他并行工作
- 本次仅建立协作协议，是否全员执行仍需后续团队统一采用

## 接手建议
- 下一位 AI 应先读哪些文件：`多AI并行开发分工说明-2026-04-20.md`、`AI协作平台开发文档.md`、`docs/ai-handoffs/collab-git-protocol.md`
- 不要重复做什么：不要再分散写多份 Git 规范，优先以本协议为准增量修订
- 优先处理什么：按角色逐步补齐各自 `docs/ai-handoffs/<role>.md`，并落实截图留档路径

## 本轮更新

- 当前阶段：进行中
- 已完成：继续推进全仓统一引用收敛，把主协议里的清理范围从“第一批文档”扩大到“第二批全仓标准引用”
- 已完成：将 AI-6 自己的 handoff 中个人机器旧 skill 路径引用清掉，避免继续扩散非标准引用
- 修改文件：`docs/ai-handoffs/collab-git-protocol.md`；`docs/ai-handoffs/boss-dispatch-board.md`；`docs/ai-handoffs/unified-agent-prompt.md`；`docs/ai-handoffs/embedded-mapping.md`；`docs/ai-handoffs/ai-6-collab-git-protocol.md`
- 当前验证：人工回读上述文档，确认标准入口名表、第二批清理目标、仓库统一引用要求和完成标准都已写入主协议，且关键入口文档继续保持标准名口径
- 截图路径：无，本轮无 UI 改动
- 当前分支：`ai/collab-git-protocol`
- 下一步：继续按角色 handoff 逐份清理残留的旧入口叫法、旧 skill 路径和重复入口名，直到 `docs/ai-handoffs/` 下只剩标准引用
- 需要他人接力：Boss 可决定是否要求各角色在自己的 handoff 中显式引用这套统一入口
- 风险：当前仓库存在大量未跟踪文件和其他角色分支遗留，虽然已切出独立分支，但若后续直接提交仍需谨慎筛选范围

## 本轮补充

- 当前阶段：进行中
- 已完成：给 `autonomous-taskloop.md`、`boss-dispatch-loop.md`、`handoff-path-output.md` 增加“标准引用”段，先把统一入口文档本身收口
- 已完成：在主协议中补写“第二批当前进度”，明确后续继续清理角色 handoff 里的 `skills/...` 路径扩散
- 已完成：继续清理 3 份入口 handoff 中对本地 skill 实现细节的默认引用，改成仓库侧标准入口说明
- 修改文件：`docs/ai-handoffs/collab-git-protocol.md`；`docs/ai-handoffs/autonomous-taskloop.md`；`docs/ai-handoffs/boss-dispatch-loop.md`；`docs/ai-handoffs/handoff-path-output.md`；`docs/ai-handoffs/ai-6-collab-git-protocol.md`
- 当前验证：人工回读上述 4 份入口文档，确认标准入口名与标准文档路径已经显式写入，且新增规则要求不再把 `skills/...` 目录路径当作默认协作入口
- 当前验证：人工回读 3 份入口 handoff，确认已不再把 `skills/README.md` 或具体 skill 目录作为默认入口引用
- 截图路径：无，本轮无 UI 改动
- 当前分支：`ai/collab-git-protocol`
- 下一步：继续逐份清理角色 handoff 中残留的旧 skill 路径、旧入口别名和重复引用，直到 `docs/ai-handoffs/` 与关键提示词里只剩标准口径
- 需要他人接力：Boss 如需加速，可要求各角色在自己的 handoff 头部补一行“统一入口引用”
- 风险：当前 shell 读取仓库较慢，逐份排查速度受限，因此我采用“先入口文档、后角色 handoff”的顺序渐进收口

## 本轮补充 2

- 当前阶段：进行中
- 已完成：清理 `autonomous-taskloop.md`、`boss-dispatch-loop.md`、`handoff-path-output.md` 的“修改文件”区，移除本地 `skills/...` 路径，只保留仓库标准文档路径
- 已完成：在主协议中补一条“优先清理高频角色 handoff 和核心入口文档”的第二批进度说明
- 修改文件：`docs/ai-handoffs/collab-git-protocol.md`；`docs/ai-handoffs/autonomous-taskloop.md`；`docs/ai-handoffs/boss-dispatch-loop.md`；`docs/ai-handoffs/handoff-path-output.md`；`docs/ai-handoffs/ai-6-collab-git-protocol.md`
- 当前验证：人工回读 3 份入口 handoff 的“修改文件”区，确认不再保留本地 `skills/...` 路径作为默认协作引用
- 截图路径：无，本轮无 UI 改动
- 当前分支：`ai/collab-git-protocol`
- 下一步：继续优先清理高频角色 handoff 和核心入口文档中的旧 skill 路径、旧入口别名和重复引用，直到 `docs/ai-handoffs/` 与关键提示词里只剩标准口径
- 需要他人接力：Boss 如需加速，可要求 AI-1、AI-3、AI-5 三条高频线优先自查并统一 handoff 引用口径
- 风险：当前仓库内仍有一些角色 handoff 保留中文口语名作为正文描述，虽然已开始配标准名解释，但还需要继续逐份收口

## 本轮补充 3

- 当前阶段：进行中
- 已完成：为 `game-loop-core.md`、`economy-balance.md`、`game-hud-feedback.md` 三份高频角色 handoff 增加“统一入口引用”段，先把高频引用模板钉成标准口径
- 已完成：在主协议中补写“高频角色优先策略”，明确 AI-1、AI-3、AI-5 三条线作为第二批清理优先对象
- 修改文件：`docs/ai-handoffs/collab-git-protocol.md`；`docs/ai-handoffs/game-loop-core.md`；`docs/ai-handoffs/economy-balance.md`；`docs/ai-handoffs/game-hud-feedback.md`；`docs/ai-handoffs/ai-6-collab-git-protocol.md`
- 当前验证：人工回读上述 3 份高频 handoff，确认都已显式写入 `unified-agent-prompt / autonomous-taskloop / handoff-path-output / ai-thread-report-template / boss-intake-format` 的标准引用
- 截图路径：无，本轮无 UI 改动
- 当前分支：`ai/collab-git-protocol`
- 下一步：继续从其余角色 handoff 与核心提示词中清理旧 skill 路径、旧入口别名和重复引用，直到 `docs/ai-handoffs/` 与关键提示词里只剩一套标准口径
- 需要他人接力：Boss 如需加速，可要求其他角色 handoff 统一补上同样的“统一入口引用”段
- 风险：高频 handoff 现在已钉住标准引用，但其余低频 handoff 仍可能保留历史叫法，需要继续逐份排查

## 本轮补充 4

- 当前阶段：进行中
- 已完成：把 `boss-dispatch-board.md` 和 `unified-agent-prompt.md` 的标题口径收成“标准名 + 中文说明”，并把 Boss 调度板中的旧入口表述改成标准名写法
- 修改文件：`docs/ai-handoffs/collab-git-protocol.md`；`docs/ai-handoffs/boss-dispatch-board.md`；`docs/ai-handoffs/unified-agent-prompt.md`；`docs/ai-handoffs/ai-6-collab-git-protocol.md`
- 当前验证：人工回读上述核心入口文档，确认已出现 `boss-dispatch-board（Boss 调度板）` 与 `unified-agent-prompt（统一执行提示词）` 的单一写法，且 Boss 板中的旧入口表述已替换为标准名
- 截图路径：无，本轮无 UI 改动
- 当前分支：`ai/collab-git-protocol`
- 下一步：继续从其余角色 handoff 与核心入口文档中清理旧 skill 路径、旧入口别名和重复引用，直到 `docs/ai-handoffs/` 与关键提示词里只剩一套标准口径
- 需要他人接力：Boss 如需加速，可要求低频角色 handoff 也补上“统一入口引用”段
- 风险：核心入口文档已开始统一命名，但正文里仍有少量中文口语描述，需要继续逐步收口成标准名优先

## 本轮补充 5

- 当前阶段：进行中
- 已完成：把新的“唯一主世界 / 唯一空间基底 / 唯一视觉母体”约束写入主协议，明确后续统一基于当前搬进来的开源农场游戏地图实现，不再扩第二套页面体系
- 修改文件：`docs/ai-handoffs/collab-git-protocol.md`；`docs/ai-handoffs/ai-6-collab-git-protocol.md`
- 当前验证：人工回读主协议，确认已新增开源农场游戏作为唯一主世界、唯一空间基底、唯一视觉母体的硬约束，并明确禁止脱离地图另起炉灶
- 截图路径：无，本轮无 UI 改动
- 当前分支：`ai/collab-git-protocol`
- 下一步：继续在高频与低频角色 handoff 中清理任何会导向“第二套页面 / 第二套城镇 / 第二套基地页”的表述，并统一回到开源农场游戏单主世界约束
- 需要他人接力：Boss 可据此要求相关角色停止独立扩页面壳层，统一围绕开源农场游戏地图适配玩法与系统
- 风险：这条约束已进入主协议，但其他角色的既有 handoff 如仍保留分叉表述，后续仍需继续逐份清理

## 本轮补充 6

- 当前阶段：进行中
- 已完成：把“唯一主线是这套开源农场游戏，不允许再扩第二套页面体系”同步写入 `unified-agent-prompt.md` 和 `boss-dispatch-board.md`
- 修改文件：`docs/ai-handoffs/unified-agent-prompt.md`；`docs/ai-handoffs/boss-dispatch-board.md`；`docs/ai-handoffs/ai-6-collab-git-protocol.md`
- 当前验证：人工回读统一提示词与 Boss 调度板，确认两处都已明确“唯一主线 / 唯一地图基底 / 不再扩第二套页面体系”
- 截图路径：无，本轮无 UI 改动
- 当前分支：`ai/collab-git-protocol`
- 下一步：继续把这条单主线约束往更多角色 handoff 和核心提示词里收，直到执行层不再出现第二套页面体系的表述
- 需要他人接力：Boss 可要求各角色在下一轮 handoff 中显式对齐“开源农场游戏唯一主线”
- 风险：核心协议、提示词和调度板都已对齐，但角色 handoff 正文里仍可能残留旧表述，后续还需继续清理

## 本轮补充 4

- 当前阶段：进行中
- 已完成：把新的仓库主线约束写入 `collab-git-protocol.md`，明确后续统一收口到 `projects/[id]` 主线，不再扩第二套基地页
- 修改文件：`docs/ai-handoffs/collab-git-protocol.md`；`docs/ai-handoffs/ai-6-collab-git-protocol.md`
- 当前验证：人工回读主协议，确认已新增 `projects/[id]` 主线约束，并明确主循环、经营系统、建筑气质、HUD 反馈必须往同一条主线收敛
- 截图路径：无，本轮无 UI 改动
- 当前分支：`ai/collab-git-protocol`
- 下一步：继续在高频与低频角色 handoff 中收敛引用口径，同时让后续协作默认服从 `projects/[id]` 单主线约束
- 需要他人接力：Boss 可据此要求相关角色停止扩第二套基地页壳层，统一回主线
- 风险：这条约束已经写入协作文档，但其他角色的既有 handoff 如仍保留“基地页”分叉表述，后续仍需继续逐份清理
