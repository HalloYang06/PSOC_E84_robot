# CAN protocol

本页记录当前源码可证明的 project-specific classic CAN 契约。电机厂商私有帧不在本页展开。

## Owner

M33 控制层拥有主协议定义、状态发布和最终命令审核；NanoPi ROS bridge 是 `0x320/0x321` 生产者及 `0x322/0x323/0x330`–`0x334/0x7C2/0x7C3` 消费者；C8T6 拥有 `0x7C0`–`0x7C3` 子协议的 sensor-node 端。

## Consumers and direction

| CAN ID | 方向 | Owner → consumer | 当前用途 |
| --- | --- | --- | --- |
| `0x320` | NanoPi → M33 | ROS bridge → M33 | 关节命令；正式 bridge 当前只产生 `SET_TARGET` |
| `0x321` | NanoPi → M33 | ROS bridge → M33 | heartbeat sequence |
| `0x322` | M33 → NanoPi | M33 → ROS bridge | heartbeat response 与 M33 safety status |
| `0x323` | M33 → NanoPi | M33/M55 bridge → ROS bridge | model result suggestion only |
| `0x330`–`0x334` | M33 → NanoPi | M33 → ROS bridge | 五个正式 joint slot 的 motor telemetry |
| `0x7C0` | M33/host → C8T6 | 控制端 → C8T6 | sensor node 配置命令 |
| `0x7C1` | C8T6 → host | C8T6 → M33 | command ACK |
| `0x7C2` | C8T6 → M33/NanoPi | C8T6 → telemetry consumers | sensor sample |
| `0x7C3` | C8T6 → M33/NanoPi | C8T6 → telemetry consumers | node health |

## Format, units, and version

所有上述帧均由当前实现按 standard ID、classic CAN、最多 8-byte payload 处理；代码未声明总线 bitrate，因此本页不推断 bitrate。

### NanoPi/M33 control and status

- `0x320`：byte 0 opcode (`0x01 enable`, `0x02 stop`, `0x03 set_target`, `0x04 set_mode`, `0x05 set_zero`, `0x06 active_report`)，byte 1 joint ID。`set_target` 必须为 8 bytes：bytes 2–3 little-endian signed position，单位 `0.1 deg`；4–5 signed rpm；6–7 signed `torque_ma`。字段名沿用旧协议，代码证据没有证明它对所有电机都等价于物理扭矩。
- `0x321`：bridge 每秒发送 1-byte rolling sequence；M33 接受零长度并以 0 作为 sequence。没有显式 protocol version。
- `0x322` V2 形态为 8 bytes：marker `0xA5`、echoed sequence、motor count、error code、safety state、control mode、detail code、heartbeat age in `100 ms` units。当前 M33 回复的 byte 7 固定为 0；NanoPi parser 仍兼容较短 V1，但 V1 永不产生 `motion_allowed=true`。
- `0x323` 为 8 bytes：marker `0xB5`、sequence、model code、result code、confidence percent、flags、window in `10 ms`、source detail。M33 强制 OR `0x80 suggestion_only`；parser contract 未另设 version 字节。
- `0x330`–`0x334` 为 motor-status v1：marker `0xB3`、sequence、physical motor ID、flags、little-endian signed position in mrad、signed int8 velocity in `0.1 rad/s`、temperature °C (`0xFF` unknown)。slots 0–4 当前映射 motor 3–7；effort/current/torque 不在该帧中。

### C8T6 sensor node

- `0x7C0`/`0x7C1` 均为 8 bytes；control 是 command, sequence, 6-byte command payload，ACK 是 command, sequence, status 加最多 5-byte response。
- `0x7C2` 为 8 bytes：four little-endian `uint16` ADC raw channels。NanoPi 当前兼容 parser 把同一布局命名为 EMG raw/filtered、heart raw/BPM/flags；这与 C8T6 当前 four-ADC encoder 的语义不一致，因此代码证据不足以把这些高层名称作为稳定 wire contract。
- `0x7C3` 为 8 bytes：state、little-endian `uint16 error_count`、queue fill，余下 bytes 为 node/runtime counters。C8T6 config 带 `protocol_version=1`，但帧内无 version 字段。

## Implementation links

- M33 IDs、opcodes、状态枚举：`firmware/m33/applications/control/control_layer_cfg.h`
- M33 parse/publish/safety apply：`firmware/m33/applications/control/control_layer.c`
- ROS runtime bridge：`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_can_bridge_node.py`
- ROS status/motor/model parsers：`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_status.py`、`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_motor_status.py`、`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/m33_model_status.py`
- C8T6 wire encoder：`firmware/c8t6/app/src/can_proto.c`

## Tests

- NanoPi/M33 payloads and gating：`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/test/test_psoc_payload_tools.py`、`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/test/test_m33_ros_contract.py`
- motor telemetry：`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/test/test_psoc_motor_status.py`
- C8T6 CAN receive path：`firmware/c8t6/tests/host/test_can_transport_direct_rx.py`

## Failure behavior

错误 CAN ID、extended frame、过短 payload 或坏 marker 会被解析器拒绝；ROS bridge 对陈旧/缺失 `0x322`、陈旧 motor status、NaN、未知关节、超限或过多轨迹点 fail closed，并清空待发 points。`enable_target_tx=false` 时只记录 `DRY-RUN`。C8T6 对未知/非法 command 返回 nonzero ACK status，并缓存重复 sequence 的 ACK。

## Safety restrictions

`0x323` 与所有 sensor/motor telemetry 只提供上下文，不授予运动许可。NanoPi 自身 gate 只是前置防护。当前 M33 的 `ctrl_assess_ros_command_safety()` 对 `SET_TARGET` 可证明会检查 heartbeat、mapping、position/rpm/`torque_ma` bounds 与 calibration；STOP、active-report 和 unsupported commands 走各自不同分支。反馈 freshness/fault 参与 pre-arm/status readiness，但 accepted `SET_TARGET` apply path 尚未证明会重新执行完整 pre-arm/current-mode gate。设计上 M33 仍必须成为最终 fail-closed 边界；当前缺口必须补齐，且 development bench build 不得解释为 clinical motion。
