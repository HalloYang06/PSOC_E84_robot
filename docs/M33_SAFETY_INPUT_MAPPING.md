# M33 Safety Input Mapping

本文档定义 M33 进入 `armed/active` 之前必须具备的物理安全输入合同。当前阶段只完成诊断合同，真实 GPIO/ADC/CAN 输入源尚未绑定，因此默认必须保持 `ready=0` 和 `motion_allowed=false`。

## 目标

- 把急停、电机电源/电压、关节限位从“口头安全要求”变成 M33 可诊断、可记录、可上传的数据合同。
- 后续接线或改 M33 读取逻辑时，必须先更新本表，再改固件。
- App、NanoPi、服务器、平台和 VLA 只能读取这些状态，不能绕过 M33。

## 总原则

- M33 是唯一运动许可裁决点。
- `confirmed=1` 只表示该输入源已经接线、校准、测试过。
- `safe_now=1` 才表示此刻该输入处于可放行状态。
- pre-arm 必须同时满足 `confirmed=1` 和 `safe_now=1`。
- 任何输入未知、未接线、未校准、超时或值不可信时，都按不安全处理。
- 当前默认值必须是 `source=unwired confirmed=0 safe_now=0`。

## 输入映射 V1

| 安全输入 | 当前 source | 未来推荐 source | confirmed 条件 | safe_now 条件 | 失败时 M33 detail |
|---|---|---|---|---|---|
| `estop` 急停 | `unwired` | 独立硬件急停 GPIO，建议常闭回路 | 真实急停按钮已接入，断线也能触发不安全，按下/释放均验证 | 急停回路闭合且未触发 | `emergency_stop` |
| `power` 电机电源/电压 | `unwired` | 电机母线电压 ADC 或电源管理状态 GPIO/CAN | 电压量程、阈值、采样稳定性已校准 | 电压在安全范围内，无欠压/过压/电源故障 | `power_fault` |
| `limits` 关节限位 | `unwired` | 每关节软限位 + 必要硬限位 GPIO/编码器校准状态 | 机械零点、方向、软限位、硬限位触发方向已验证 | 当前目标和当前位置均在最终限位内，硬限位未触发 | `target_out_of_limit` 或 `motor_fault` |

## M33 串口诊断

烧录当前诊断固件后，可运行：

```text
cmd_m33_safety_inputs
cmd_m33_prearm_check
cmd_m33_prearm_check 0x40
```

当前正确输出应包含：

```text
SAFETY_INPUT: name=estop source=unwired confirmed=0 safe_now=0
SAFETY_INPUT: name=power source=unwired confirmed=0 safe_now=0
SAFETY_INPUT: name=limits source=unwired confirmed=0 safe_now=0
PREARM: ready=0 motion_allowed_would_be=0
PREARM_INPUT_DETAIL: estop source=unwired safe_now=0; power source=unwired safe_now=0; limits source=unwired safe_now=0
```

如果 7 号电机 telemetry 新鲜，`cmd_m33_prearm_check 0x40` 可以看到：

```text
PREARM_MOTORS: required_mask=0x00000040 fresh_mask=0x00000040 ... fresh_ok=1 fault_free=1
```

这只证明电机反馈条件满足，不代表物理安全输入满足。

## `0x322` 输出要求

NanoPi 只认 `motion_allowed=true` 作为运动候选许可。M33 后续只有同时满足以下条件，才允许让 NanoPi 解析为 `motion_allowed=true`：

```text
error_code == 0
safety_state == ok
control_mode == armed 或 active
detail_code == none
estop.confirmed == 1 && estop.safe_now == 1
power.confirmed == 1 && power.safe_now == 1
limits.confirmed == 1 && limits.safe_now == 1
heartbeat fresh
required motor feedback fresh
required motor feedback fault_free
logging_only disabled by an explicit reviewed firmware change
```

任一条件失败时：

- `motion_allowed` 必须为 `false`。
- M33 应进入 `limited`、`emergency_stop` 或 `fault`。
- `detail_code` 应给出最主要的阻断原因。

## 上层展示

App、平台、服务器和 NanoPi 日志应按下面方式展示，不要把未确认状态隐藏起来：

```json
{
  "safety_inputs": {
    "estop": {"source": "unwired", "confirmed": false, "safe_now": false},
    "power": {"source": "unwired", "confirmed": false, "safe_now": false},
    "limits": {"source": "unwired", "confirmed": false, "safe_now": false}
  },
  "motion_allowed": false
}
```

当前 ROS `/rehab_arm/safety_state` 还没有单独携带完整 `safety_inputs` 字段。第一阶段先通过 M33 串口和文档合同验收；后续再扩展 `0x322` 或增加低频状态帧。

## 接线和固件实现顺序

1. 选定每一路真实输入源，记录 pin、ADC channel、CAN 状态或编码器校准来源。
2. 写只读诊断读取函数，只打印 raw value，不参与 pre-arm。
3. 验证断线、触发、恢复、抖动和异常值。
4. 把 raw value 转成 `safe_now`。
5. 人工确认后把对应 `confirmed` 改为 1。
6. 再把该输入接入 `cmd_m33_prearm_check`。
7. 最后才考虑 `armed` 状态转换。

## 未确认项

- 急停按钮接到 M33 还是外部安全回路后再给 M33 状态。
- 电机母线电压由 M33 ADC 读、由电源板上报，还是由电机驱动状态间接判断。
- 每个关节是否都有硬限位，硬限位的常开/常闭和触发方向。
- 真实机械零点、关节方向、软限位、速度限制和电流限制。
- `0x322` 是否需要扩展安全输入 bitmask，或另开低频状态帧。

## 当前验收状态

- `cmd_m33_safety_inputs` 已烧录后验证。
- `cmd_m33_prearm_check 0x40` 已在 7 号 telemetry 新鲜时验证。
- 三路物理安全输入仍是 `unwired/confirmed=0/safe_now=0`。
- `ready=0` 和 `motion_allowed_would_be=0` 是当前正确结果。
- 没有发布轨迹，没有发送 `0x320`，没有电机运动。
