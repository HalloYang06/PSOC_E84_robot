# Codex Platform Autonomy - 2026-04-21 Night

## 当前目标

把平台真正推进到这条终线：

- 平台里只看 AI 的最终回复、最小回执和状态变化
- 本机 Codex 软件里看完整过程
- 平台作为用户身份，可以拉多个真实线程一起协作开发这个平台自己
- 平台里的 NPC 不再是假名字，而是绑定真实电脑、真实线程、真实 Git 边界和真实 Skill

## 这轮完成

### 1. 确认线程是“真实扫描”，不是手工伪造

已经直接核对：

- 本机会话索引：`C:\Users\18312\.codex\session_index.jsonl`
- 后端库存：`apps/api/ai_collab.db -> project_thread_workstations`

当前新项目 `ai合作平台`（`10f6a858-f3e4-467c-87f5-726caa3cc2be`）里有两类工位：

- `12` 条真实扫描线程
- `4` 个平台内创建的管理型 NPC 席位

真实扫描线程的证据：

- `project_thread_workstations.config_id = codex-session-<session_id>`
- 这些 `<session_id>` 全都能在 `session_index.jsonl` 里对上
- `extra_data.source = runner_thread_scan`
- `extra_data.runner_id = runner-7e6c7eef`
- `extra_data.computer_node = Local Dev PC`

验证产物：

- `D:\ai合作产品\artifacts\thread-scan-and-seat-route-2026-04-21.json`

### 2. 前端已经把“真实线程”和“NPC 席位”拆开

项目页团队背包里新增并强化了两层区分：

- `电脑接入 -> 真实扫描线程`
- `机房 -> 真实线程页`
- 原有 `机房 -> NPC 信息页`

也就是说：

- 真实扫描线程是来源线程
- NPC 席位是平台里创建出来、绑定到这些线程上的可管理角色

不再把两者混成一个数。

### 3. 新增“NPC 席位自己回执”的后端接口

新增接口：

- `POST /api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}/messages`

作用：

- 允许平台中的某个真实 NPC 席位，以自己的身份写协作消息
- 不再走原来那个只会强制记成 `human` 的 `/api/collaboration/messages`

当前接口行为：

- `sender_type = "agent"`
- `sender_id = workstation_id`
- `agent_id = workstation_id`

### 4. 真实验证已经通过

我已经实际验证了这条链：

1. 用平台用户 `codex-platform-npc@local.dev / codex1234`
2. 通过 `/api/auth/session` 拿真实 access token
3. 对新项目中已有的需求：
   - `平台主链自检并推进下一步`
4. 以 `codex-platform-lead` 发一条最小回执

验证结果：

- `sender_type = "agent"`
- `sender_id = "codex-platform-lead"`
- `agent_id = "codex-platform-lead"`
- `status = "in_progress"`

说明这条“NPC 自己回复”的后端链已经真的通了。

验证后处理：

- 这条临时验证消息已经删除
- `remaining_message = 0`

注意：

- 当时用 Python 直发中文标题/正文仍然会受控制台编码影响，所以验证消息文本出现过 `?`
- 但这条消息已经被删掉，没有残留到项目里
- 后续页面正常操作走 web 表单即可，不需要再用 Python 直发中文内容

## 当前真实项目状态

新项目：

- 名称：`ai合作平台`
- 项目 ID：`10f6a858-f3e4-467c-87f5-726caa3cc2be`

平台用户 / 主负责 NPC 账号：

- 邮箱：`codex-platform-npc@local.dev`
- 密码：`codex1234`

电脑节点：

- `local-dev-pc`
- 标签：`Local Dev PC`
- runner：`runner-7e6c7eef`

已创建管理型 NPC 席位：

- `codex-platform-lead` -> `主负责 NPC`
- `codex-git-maintainer` -> `Git 维护员`
- `codex-thread-liaison` -> `线程联络员`
- `codex-skill-maintainer` -> `技能库维护员`

这些席位都绑定到了：

- 真实电脑：`Local Dev PC`
- 真实来源线程：`source_workstation_id`
- 自己的职责、Skill、Git 边界和地图坐标

## 当前最重要的架构结论

这条线已经确定了：

### 平台里显示什么

平台里只应该显示：

- 需求单
- 派单状态
- 最小回执
- 最终完成状态
- 谁接了、谁没接、谁完成了

### 本机 Codex 里显示什么

本机 Codex 软件里保留：

- 详细执行过程
- 推理过程
- 修改细节
- 长日志
- 中间讨论

也就是：

- 平台是“结果面板 / 调度台”
- 本机 Codex 是“过程终端”

## 下一步最该继续做

1. 把 `登记已接单 / 登记已完成` 的前端表单真正改走新接口
   - AI 目标用 `thread-workstations/{id}/messages`
   - 人工目标继续走普通 collaboration message

2. 把 `信息交流 / Git 合作` 的状态识别改成优先吃“真实 agent sender”
   - 不再主要靠 `sender_id` 文本猜是不是 AI

3. 用新项目 `ai合作平台` 继续做真实协作
   - 主负责 NPC 发维护派单
   - 其他 NPC 回最小回执
   - 平台只显示最终回复和状态变化

4. 再补真实登录态页面验证
   - 重点看 `ai合作平台` 这个项目
   - 重点看 `信息交流 / Git 合作 / 机房`

## 继续接手时先看

- `D:\ai合作产品\apps\web\app\projects\[id]\project-playable-shell.tsx`
- `D:\ai合作产品\apps\web\app\actions.ts`
- `D:\ai合作产品\apps\api\app\modules\collaboration\router.py`
- `D:\ai合作产品\artifacts\thread-scan-and-seat-route-2026-04-21.json`

