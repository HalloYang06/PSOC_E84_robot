# Boss Dispatch Loop

## 身份

- 角色: Skill-Author
- 职责: Boss 调度闭环与派工板维护规范

## 负责范围

为当前仓库新增一个 Boss 调度型 skill，让调度角色基于 `docs/ai-handoffs/` 持续读取最新进展、判断优先级、更新共享派工板，并决定“继续 / 待验证 / 待接手 / 阻塞”。

## 标准引用

后续在仓库协作文档、Boss 调度、角色 handoff 中，统一引用：

1. `boss-dispatch-loop`
2. `docs/ai-handoffs/boss-dispatch-loop.md`

不要在协作文档里继续扩散 `skills/...` 目录路径作为默认入口引用；skill 目录仅视为实现细节。

## 已完成

1. 建立并维护标准入口引用 `docs/ai-handoffs/boss-dispatch-loop.md`
2. 补充该入口的仓库侧索引说明
3. 重写 `docs/ai-handoffs/boss-dispatch-board.md` 为带身份和当前实际状态的规范版

## 修改文件

1. `D:\ai合作产品\docs\ai-handoffs\boss-dispatch-board.md`
2. `D:\ai合作产品\docs\ai-handoffs\boss-dispatch-loop.md`

## 当前验证

1. 已确认 skill 文件落盘成功。
2. 已确认该入口的仓库侧说明已补齐。
3. 已确认调度板改为规范版并带 `## 身份`。
4. 本轮仅新增 skill 与文档，没有界面或运行时代码改动，因此未做截图验证。

## 下一步建议

1. 后续 Boss 角色默认叠加使用 `ai-boss + boss-dispatch-loop + handoff-path-output`。
2. 当 `economy-balance.md` 和 `game-hud-feedback.md` 产出后，Boss 调度板可以继续细化每条线的“当前 blocker / 下一步接手人”。

## 风险

1. 当前 AI-3 和 AI-5 的交接文档还未到位，所以派工板对这两条线只能先标 `待接手`。
2. 调度板依赖各角色 handoff 的质量，如果 handoff 不更新，Boss 判断会失真。
