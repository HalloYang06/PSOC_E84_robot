# M33/NanoPi 0x320 单关节模式 mask 实施记录

日期：2026-07-17

## 1. 修改目的

旧的 `0x320 SET_MODE` 只携带模式值。M33 应用命令时固定使用 `0x38`，会同时选择 M33 关节 4、5、6，无法安全表达单关节助力或抗阻。

本次只修正模式命令的关节选择合同，不修改以下路径：

- MuJoCo 轨迹规划和 `SET_TARGET` 编码；
- 电机厂家协议、位置闭环和电流控制算法；
- M55 推理、LCD、SMIF 和双核 IPC；
- BLE 配对和 App 协议；
- NanoPi 产品服务默认只读策略。

## 2. SET_MODE 帧格式

标准帧 ID 为 `0x320`，发送端使用 DLC 8：

| Byte | 字段 | 说明 |
|---:|---|---|
| 0 | command | 固定 `0x04` |
| 1 | correlation sequence | 模式命令关联序号，不表示目标关节 |
| 2 | mode | `0=PASSIVE`、`1=ACTIVE`、`3=ASSIST`、`4=RESIST` |
| 3 | joint mask | 非 PASSIVE 时必须是支持集合内的单 bit |
| 4..7 | reserved | 固定为 0 |

当前支持集合为 `0x38`：

```text
M33 joint 4 -> 0x08
M33 joint 5 -> 0x10
M33 joint 6 -> 0x20
```

当前单关节 5 助力示例：

```text
320#042A031000000000
```

PASSIVE 示例：

```text
320#042A000000000000
```

## 3. M33 行为

M33 在三个边界校验主动模式 mask：

1. 解析边界：非 PASSIVE 的 DLC 小于 4 时不形成命令。
2. 安全审核边界：mask 为 0、多 bit 或超出 `0x38` 时拒绝。
3. 应用边界：进入 `rehab_mode_manager_apply_command()` 前再次校验。

通过审核后，`mode_cmd.joint_mask` 直接使用帧内 mask，不再扩展为默认 `0x38`。

PASSIVE 是安全降级例外。M33 继续接受历史 3 字节 `04 <seq> 00`，并把 mask 归一化为 0；该兼容不能用于 ACTIVE、ASSIST 或 RESIST。

Byte1 在现有 `control_ros_command_t` 中仍沿用历史字段名 `joint_id`，在 `SET_MODE` 应用路径中作为 sequence 使用。这是命名债务，不改变线上合同；本次没有大范围重命名，以免影响其他 `0x320` 操作码。

## 4. NanoPi 行为

NanoPi `scripts/nanopi_can_master.py` 增加专用模式编码器：

- 固定生成 8 字节帧；
- PASSIVE 自动使用 mask 0；
- 主动模式要求显式 `--joint-mask`；
- 缺失 mask、多 bit mask 和不支持 bit 在 SocketCAN 发送前报错；
- `--joint` 在 `m33 mode` 子命令中暂时承载 Byte1 sequence，不是目标关节。

示例编码命令：

```bash
python3 scripts/nanopi_can_master.py m33 mode \
  --iface can0 --joint 42 --mode 3 --joint-mask 0x10
```

该命令本身不建立持续 heartbeat，也不代表 M33 会放行动作。主动模式联调必须另行保证 heartbeat、急停、反馈和 pre-arm 条件。

## 5. 提交与验证

M33：

```text
5f7bd4781 fix(control): require single-joint rehab mode mask
9c7ef140f fix(can): send explicit passive mode mask
```

NanoPi：

```text
9462cf56 fix(can): 为康复模式携带单关节掩码
a305fb11 docs(can): 明确0x320单关节模式掩码
```

主机检查结果：

- M33 单关节 mask 合同测试 3 项通过；
- M33 CAN RX owner/队列与租约测试 12 项通过；
- NanoPi 安全模式脚本测试 9 项通过；
- NanoPi 模式帧编码测试 3 项通过；
- M33 完整 SCons 构建通过并生成 `build/rtthread.hex`。

完整构建仍输出工程原有 CAN、BLE 和 `main.c` 警告，本次新增代码没有编译错误。旧综合静态脚本还会被当前未提交的 `main.c` 框架宏差异拦住，本次没有修改或回退该文件。

## 6. 尚未完成的硬件验证

本次新协议固件尚未重新烧录，主动单关节 mask 尚未带电验证，不能声称助力/抗阻远程切换已经真机通过。

建议按以下顺序验证：

1. 烧录本次构建的 M33 `build/rtthread.hex`，不要烧录旧 `Debug/rtthread.hex`。
2. 电机不使能时发送 8 字节 PASSIVE，确认 `ros_id/parsed/enq/applied` 增长。
3. 发送缺 Byte3 的 ASSIST，确认解析拒绝且没有电机输出。
4. 发送 `joint_mask=0x18`，确认安全审核拒绝且 `applied` 不增长。
5. 确认 CAN 为 `ERROR-ACTIVE`、heartbeat 持续、急停有效、关节 5 反馈新鲜、故障位含义明确、限流生效。
6. 机械臂空载并有人值守时，才发送 `ASSIST + 0x10`，观察 `rehab status`、`cmd_control_debug` 和受限电流。
7. heartbeat 停止后确认租约超时自动回到 PASSIVE，并确认没有继续输出非零电流。

任何一步出现 HardFault、shell 无响应、CAN bus-off、旧命令被执行或 mask 扩展，都应立即停止主动测试并回退到 PASSIVE。

## 7. 后续债务

- 在线协议下一版本为 correlation sequence 建立独立命名，消除内部 `joint_id` 复用。
- 为解析函数增加可执行的主机单元测试；当前新增测试以源码合同和完整交叉编译为主。
- 把模式命令 ACK/拒绝原因和原始 mask 关联起来，便于 NanoPi 判断是否真正进入指定单关节模式。
- 主动模式发送工具应加入持续 heartbeat 会话和显式操作者确认，不应由语音、App 或模型结果直接调用底层 CAN 发送。
