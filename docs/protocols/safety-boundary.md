# Safety boundary

## Owner

设计原则 `M33_ARCHITECTURAL_FINAL_SAFETY_AUTHORITY`：M33 是架构上的最终安全裁决者，控制层拥有电机 enable/stop/target/mode/zero 的最后执行入口。目标规则仍是由 M33 基于构建模式、heartbeat、mapping、calibration、bounds、反馈 freshness、fault 与 current mode 实现最终 fail-closed；下文严格区分该要求与当前代码证据。

## Consumers and direction

- 上行候选：App/Web/VLA/planner → ROS `JointTrajectory` → NanoPi bridge → CAN `0x320` → M33。
- 下行权威状态：M33 CAN `0x322` → NanoPi `/rehab_arm/safety_state` → platform telemetry/UI。
- 辅助上下文：C8T6 sensor、M55 AI result `0x323`、motor telemetry `0x330`–`0x334`、MuJoCo shadow；全部是 M33 safety decision 的输入或观测，不是许可。
- BLE side channel：phone/client 写 NUS RX，M33 仅允许 heartbeat 与 stream on/off；当前 profile 不接受运动写入。

## Format, units, and version

M33 `0x322` V2 的 positive permission 由 NanoPi parser 严格计算：marker 正确，safety state `ok`，control mode 为 `armed` 或 `active`，detail/error 为 0，才有 `motion_allowed=true`。`bench_armed` 默认不被允许，除非 bridge 显式设置 `allow_bench_motion_for_trajectory=true`。V1/短帧、坏 marker、过期状态都 fail closed。

ROS bridge 的关键 flags 当前默认值：`require_psoc_ok_for_trajectory=true`、`require_fresh_motor_status_for_trajectory=true`、`reject_out_of_limit_trajectory=true`、`enable_target_tx=false`。M33 build flags 当前为 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE=1`、`CONTROL_CLINICAL_MOTION_ENABLE=0`；这是 bench 能力，不是 clinical qualification。

M33 当前 per-command 证据位于 `ctrl_assess_ros_command_safety()`：对 `SET_TARGET` 检查 NanoPi heartbeat、joint mapping、position/rpm/`torque_ma` bounds 与 calibration；STOP 只要求 known joint，active-report telemetry 检查 heartbeat/mapping，其他 command 在该 ROS 路径拒绝。`ctrl_apply_ros_command()` 对 accepted `SET_TARGET` 随后调用 `control_joint_motor_set_target()`，后者仅再次检查 calibration。

已知缺口 `SET_TARGET_PREARM_RECHECK_GAP`（稳定证据标记 `SET_TARGET_DOES_NOT_RECHECK_FULL_PREARM_OR_CURRENT_MODE`）：反馈 freshness/fault 参与 `ctrl_prearm_check_build()` 与 status readiness，但当前 accepted `SET_TARGET` 路径没有重新检查完整 pre-arm 或 current mode。代码证据因此不能证明 stale feedback、fault、pre-arm failure 或错误 current mode 会在每条 target 应用前由 M33 再次 fail closed；这是临床使能前必须修复并测试的安全要求。

BLE 使用 Nordic UART Service UUID：service `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`，RX `6E400002-...`，TX notify `6E400003-...`。ASCII parser 能识别 `heartbeat`、`stream:on`、`stream:off`、`move:<joint>:<target>`、`mode:<token>` 和 `stop`；但 GATT policy 只把前三类标为 readonly-safe。`move:*`、`mode:*` 和 `stop` 在当前 profile 返回 `ERR:readonly`。代码未声明 BLE application protocol version、target unit 或完整 framing version，因此不可推断。

## Implementation links

- M33 safety/config 与 `ctrl_assess_ros_command_safety()`：`firmware/m33/applications/control/control_layer_cfg.h`、`firmware/m33/applications/control/control_layer.c`
- NanoPi gates/defaults：`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/safety_gate.py`、`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_can_bridge_node.py`
- BLE parser/policy：`firmware/m33/applications/m33/app_ble_service.c`、`firmware/m33/applications/m33/bt_app_gatt_handler.c`
- BLE UUID database：`firmware/m33/applications/m33/bt_app_gatt_db.h`
- VLA boundary：`ai/vla/services/vla_bridge_service.py`
- Platform boundary：`platform/api/app/modules/rehab_arm/service.py`

## Tests

- ROS fail-closed gates：`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/test/test_safety_gate.py`、`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/test/test_m33_ros_contract.py`
- BLE startup/policy static checks：`firmware/m33/tools/test_m33_ble_startup_policy_static.py`
- VLA suggestion boundary：`ai/vla/tests/test_control_boundary.py`
- Platform write/security boundary：`platform/api/tests/test_rehab_arm_vla_closed_loop_status.py`

## Failure behavior

缺失或陈旧 `0x322`、无新鲜 motor feedback、unknown joint、NaN/Inf、超限、轨迹为空/过长都会使 NanoPi 拒绝或停止 trajectory，并清空 pending points。target TX 默认 dry-run。M33 当前 `SET_TARGET` assessment 可证明拒绝 heartbeat timeout、unknown mapping、越界 position/rpm/`torque_ma` 和未校准关节；malformed/unsupported commands 也会被拒绝。当前代码不能证明它在 apply 前逐条重检完整 pre-arm/freshness/fault/current-mode 状态。BLE invalid frame 返回 `ERR:invalid`，queue full 返回 `ERR:busy`，运动类命令返回 `ERR:readonly`。

## Safety restrictions

- 不得把 `state=ok`、AI detected/high confidence、VLA candidate、App plan accepted、HTTP 2xx、MuJoCo 正常或 motor telemetry 新鲜单独解释为运动许可。
- 不得关闭 NanoPi gates 后假定安全；M33 的裁决不可旁路。
- 不得把 pre-arm/status 中存在 freshness/fault 检查解释为每条 `SET_TARGET` 已执行同一检查；必须关闭 `SET_TARGET_PREARM_RECHECK_GAP` 后才可声称 M33 完整落实最终裁决。
- development bench 与 clinical motion 互斥；当前源码配置仅证明 bench path。
- BLE `move:*`、`mode:*` 和 `stop` 保持只读；若未来开放，必须另行定义认证、单位、重放防护、超时和 M33 审核，不能只删除 `ERR:readonly`。
- 云端/API 没有直接 motor control。急停的安全实现必须落到可证明的本地 M33/硬件链路；当前 API `estop` 记录不能作为该链路已完成的证据。
