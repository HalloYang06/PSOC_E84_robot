# Autonomous Taskloop

## 身份

- 角色: Skill-Author
- 职责: 自主分任务与持续执行闭环规范

## 负责范围

为当前仓库新增一个通用执行型 skill，让各角色 AI 在自己的边界内持续推进，不因每个小步骤都停下来等待确认，同时继续遵守角色边界、人工审批和 Git/文档交接规则。

## 标准引用

后续在仓库协作文档、Boss 调度、角色 handoff 中，统一引用：

1. `autonomous-taskloop`
2. `docs/ai-handoffs/autonomous-taskloop.md`

不要在协作文档里继续扩散 `skills/...` 目录路径作为默认入口引用；skill 目录仅视为实现细节。

## 已完成

1. 建立并维护标准入口引用 `docs/ai-handoffs/autonomous-taskloop.md`
2. 补充该入口的仓库侧索引说明

## 修改文件

1. `D:\ai合作产品\docs\ai-handoffs\autonomous-taskloop.md`

## 当前验证

1. 已确认 skill 文件落盘成功。
2. 已确认该入口的仓库侧说明已补齐。
3. 本轮仅新增 skill 与文档，没有界面或运行时代码改动，因此未做截图验证。

## 下一步建议

1. Boss 或分工文档可以显式要求各角色默认叠加 `autonomous-taskloop` 与 `handoff-path-output`。
2. 各角色 handoff 文档可以补一段“下一步自动推进建议”，让后续接手者更容易连续执行。

## 风险

1. 这是流程规范 skill，不会自动替代系统级调度器。
2. 如果角色边界定义不清，AI 仍可能因为“自主推进”而误入别人的范围，所以最好配合现有分工文档一起使用。
