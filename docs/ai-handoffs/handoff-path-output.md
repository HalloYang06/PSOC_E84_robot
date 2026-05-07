# 身份

- 角色: Skill Author / 交接规范维护者
- 负责线: 交接文档路径输出规则

## 负责范围

维护仓库内的收尾规范 skill，要求每次任务完成时：

- 更新自己的 `docs/ai-handoffs/<role>.md`
- 在最终回复里显式输出交接文档路径
- 在交接文档里标明身份

## 标准引用

后续在仓库协作文档、Boss 调度、角色 handoff 中，统一引用：

1. `handoff-path-output`
2. `docs/ai-handoffs/handoff-path-output.md`

不要再把旧 skill 名或 `skills/...` 目录路径当作协作入口名传播；本仓库协作口径统一为 `handoff-path-output`。

## 已完成

1. 建立并维护标准入口引用 `docs/ai-handoffs/handoff-path-output.md`
2. 把“最终回复必须输出交接文档路径”写成明确规则
3. 把“交接文档必须标明身份”补进 skill 约束

## 修改文件

1. `D:\ai合作产品\docs\ai-handoffs\handoff-path-output.md`

## 当前验证

1. skill 文件可读且规则完整
2. 本文档已按“身份 + 负责范围 + 已完成 + 修改文件 + 验证 + 下一步 + 风险”结构落盘

## 下一步

1. 在后续角色分工或 Boss 规则里默认叠加这个 skill
2. 如需 UI 可发现性，再补 `agents/openai.yaml`

## 待他人接力

1. Boss 或规范维护线可决定是否把它提升为默认强制 skill

## 风险

1. 这仍然是仓库级 skill，是否触发取决于后续任务是否按规则加载
2. 如果别的角色不维护自己的 handoff 文档，最终仍可能漏路径输出
