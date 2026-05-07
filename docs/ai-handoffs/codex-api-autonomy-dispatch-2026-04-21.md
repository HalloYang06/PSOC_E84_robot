# Codex API Autonomy Dispatch Handoff - 2026-04-21

## 本轮目标
- 只在 `D:\ai合作产品\apps\api` 内补齐平台自治派单与最小回执闭环。
- 让维护/需求任务能稳定标记：
  - `queued`
  - `in_progress`
  - `done`
- 让平台能给指定 `agent/workstation` 写最小最终回执。

## 已完成

### 1. Requirements 新增自治派单动作
新增接口：
- `POST /api/requirements/{requirement_id}/dispatch`

作用：
- 把需求派给指定 `workstation / agent / human`
- 把 `Requirement.status` 推到 `queued`
- 对 `workstation / agent` 同步写 `Requirement.to_agent`
- 同时生成一条 `collaboration_messages` 里的 `requirement_dispatch`

关键保证：
- 只有当前项目成员才能派单
- 目标 `workstation / agent` 必须真实绑定在当前项目里，否则返回 `TARGET_NOT_FOUND`

### 2. Requirements 新增最小最终回执动作
新增接口：
- `POST /api/requirements/{requirement_id}/final-reply`

作用：
- 允许写最小回执：
  - `in_progress`
  - `done`
- 同时写两条数据：
  - `requirement_messages`
  - `collaboration_messages`
- `Requirement.status` 会跟着最小回执推进

当前策略：
- `final-reply` 不直接走原来的 `accept / close`
- 保留原有高权限动作边界
- 用“最小回执消息 + requirement 状态推进”实现平台需要的自治反馈

### 3. Collaboration 侧数据复用
没有新增新表。
本轮直接复用现有：
- `requirements`
- `requirement_messages`
- `collaboration_messages`

这样前端平台可以继续只靠现有消息流和需求流做：
- 派单
- 接单
- 最终回复池
- 当前负责人
- 当前推荐操作

## 改动文件
- `D:\ai合作产品\apps\api\app\modules\requirements\schemas.py`
- `D:\ai合作产品\apps\api\app\modules\requirements\repo.py`
- `D:\ai合作产品\apps\api\app\modules\requirements\service.py`
- `D:\ai合作产品\apps\api\app\modules\requirements\router.py`
- `D:\ai合作产品\apps\api\tests\test_requirement_autonomy_flow.py`

## 验证

### 定向验证
- `python -m pytest D:\ai合作产品\apps\api\tests\test_requirement_autonomy_flow.py -q`
- 结果：`2 passed`

覆盖内容：
- 项目成员可派单到真实 workstation
- 需求状态从 `queued` -> `in_progress` -> `done`
- `requirement_dispatch` / `requirement_final_reply` 协作消息成功写入
- outsider 不能派单、不能回执
- 派到不存在的目标会返回 `TARGET_NOT_FOUND`

### 全量验证
- `python -m pytest tests -q`
- 结果：`75 passed`

说明：
- 之前出现过一次 `test_suite.db` 被残留 pytest 进程占用
- 清理残留 python/pytest 进程后，全量测试已通过

## 风险与遗留

### 1. 当前仍然是“成员触发”的自治写入
这轮接口仍然走项目成员权限验证。
也就是说：
- 平台/用户/主负责 NPC 通过当前项目成员身份能操作
- 但还没有引入单独的“agent token / workstation token”写入权限模型

### 2. `to_agent` 仍然是字符串字段
当前把：
- `agent`
- `workstation`
都压到 `Requirement.to_agent`

这足够平台当前使用，但如果以后要更严格区分：
- `target_type`
- `target_id`
建议在 requirement 层补显式字段，或完全从 `collaboration_messages` 里取分发目标。

### 3. 目前 `final-reply` 是“最小最终回执”
它适合平台主视图和自治调度，不适合取代：
- 正式审批
- 正式关闭
- 高风险动作确认

这些仍然应该继续保留原有高权限动作。

## 接下来建议
前端现在可以直接接这两条：
- `dispatch`
- `final-reply`

优先把平台里的：
- `分给 AI / 分给人`
- `登记已接单`
- `登记已完成`
改成只调这两个后端接口，不再在前端拼临时状态。
