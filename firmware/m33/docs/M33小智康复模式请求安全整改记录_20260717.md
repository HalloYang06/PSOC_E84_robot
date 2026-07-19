# M33 小智康复模式请求安全整改记录

日期：2026-07-17

## 1. 当前状态

当前代码已经完成语音模式请求的协议和安全基础，但**尚未把小智事件接到运动执行路径**。

现在烧录后：

- 小智不会因为新增代码自动进入助力或抗阻。
- `cmd_voice_precheck` 只读反馈并打印结果，不发送 CAN，不清故障，不使能电机。
- 现有 MuJoCo/CAN `SET_TARGET` 在 PASSIVE 模式保持原行为。
- rehab 处于非 PASSIVE 时，普通 `SET_TARGET` 被拒绝，避免两个线程同时写电机。

## 2. 已完成的小提交

M33：

- `d0f90dd28`：纯语音请求 guard。
- `f1a6200f2`：修正模式值、epoch、TTL、同模式重入和 PASSIVE 优先级。
- `f235034c0`、`618528245`：增加 versioned request/result IPC ABI，并修复宏重名。
- `f61a810a4`：增加严格零等待 IPC 结果发布。
- `a8072f1c7`：rehab 非 PASSIVE 时阻止普通 ROS target 与其争用电机。
- `a1f902f27`：增加独立 VOICE source 和真实 owner/generation 租约。
- `cd887ff04`：增加只读 joint5 voice active precheck。

M55 配套：

- `54da8808`、`dda5713d`：精确 allowlist，只接受 joint5 的明确 VLA control 指令。
- `1192f51e`、`b6f028b8`：与 M33 对齐 request/result wire ABI。

## 3. 请求协议

第一版只允许：

```text
joint = 5
joint_mask = 0x10
mode = PASSIVE(0) / ASSIST(3) / RESIST(4)
source = VOICE(1)
ttl <= 500 ms
```

请求携带 `boot_epoch + monotonic request_id`。M33 收包时记录自己的本地 tick，不比较 M55 和 M33 的绝对时间。

M55 的 `event_fingerprint` 只是诊断指纹，不能作为 request ID。原始 STT 不允许触发模式；只有明确标记的可信 VLA/control 事件才可以形成候选。

## 4. M33 guard 规则

- epoch 必须先在 PASSIVE、无 owner 时被明确接受。
- 请求 epoch 必须等于 trusted epoch，旧 epoch 不得回滚状态。
- 相同 epoch/request ID 是重复请求，不重复执行。
- 更小 request ID 是旧请求。
- 同模式新请求返回 ALREADY_ACTIVE，不重新初始化控制策略。
- ASSIST 与 RESIST 互切必须先进入 PASSIVE，不能直接切换。
- PASSIVE/STOP 可从任意当前模式抢占，不受 active precheck 阻挡。
- commit 只能在最终 APPLY/ALREADY_ACTIVE 成功后进行。

## 5. 单写者和所有权

已有 `ros_cmd` 单消费者线程继续作为未来语音命令唯一执行上下文。IPC 回调只能校验和零等待入队，不能调用电机或 rehab service。

所有权分为：

- `BENCH_MSH`：本地 Shell 调试。
- `CAN`：NanoPi/MuJoCo。
- `VOICE`：未来小智高层请求。

VOICE 不能伪装成 CAN，也不能抢占 CAN/MuJoCo 正在拥有的 active 动作。CAN 的 STOP/PASSIVE 始终可以抢占。

## 6. 电机 5 的 0x02 故障

本地 RobStride private parser 从扩展 ID bits 21:16 提取 `fault_summary`，从 bits 23:22 提取 `mode_state`。RobStride RS00 官方手册在“通信类型 2：电机反馈数据”中定义：

- bit16 欠压
- bit17 过流
- bit18 过温
- bit19 磁编码故障
- bit20 HALL 编码故障
- bit21 未标定
- mode 0/1/2 = Reset/Cali/Motor

因此当前观测：

```text
fault_summary = 0x02 -> bit1 -> 过流摘要
mode_state = 0       -> Reset
```

官方手册：<https://robstride.com/assets/product_manual_robStride00-05044b8c.pdf>

仓库没有保存电机实际固件版本，故障文字仍应在现场用厂家上位机复核；但安全判定不依赖具体文字，任何非零 `fault_summary` 都阻断新的 VOICE active 请求。

## 7. 只读 precheck

执行：

```text
cmd_voice_precheck
```

PASS 必须同时满足：

- control layer 已初始化；
- joint5 有反馈且 timestamp 非零；
- age 不超过 100 ms；
- private protocol；
- motor ID 为 5；
- joint5 静态标定 gate 有效；
- `fault_summary == 0`；
- 进入 active 前 `mode_state == 0`。

输出：

```text
VOICE_PRECHECK: result=PASS|REJECT joint=5 mask=0x10 reason=... age_ms=... fault=... mode=... proto=... id=... tick=...
VOICE_PRECHECK_CNT: total=... pass=... not_init=... no_feedback=... stale=... protocol=... id=... calibration=... fault=... mode=...
```

该命令无运动副作用。当前位置、力矩和温度还没有作为 PASS 门槛，因为 private feedback 的关节坐标转换和实际力矩语义尚未完成验证。

## 8. 当前无动作检查步骤

```text
cmd_control_init can0
cmd_motor_report 5 1
cmd_motor_fb 5
cmd_motor_fb 5
cmd_motor_fb 5
cmd_voice_precheck
cmd_m33_prearm_check 0x10
```

若需要尝试厂家 stop+clear fault，只执行：

```text
cmd_motor_stop 5 1
```

等待 500 ms 后重新连续读取三次 `cmd_motor_fb 5` 和一次 `cmd_voice_precheck`。

如果仍为 0x02：

- 禁止 `cmd_motor_en`、电流命令和 `rehab assist`。
- 断开动力、隔离机构，检查相线、接插件、驱动、电流采样和供电。
- 使用厂家上位机读取 type21/详细 fault 和固件版本。
- 不通过短接或堵转制造故障。

## 9. 仍然阻断运行接线的事项

1. M55 relay 当前仍以 `command` 子串识别 VLA kind，尚未形成可信 server event ID。
2. M33 尚未把 `MSG_TYPE_REHAB_MODE_REQUEST` 接入 `ros_cmd` 队列。
3. ASSIST/RESIST 的非阻塞两阶段 PASSIVE/zero transition 尚未实现。
4. 第一次非零电流前尚未等待 `mode_state==2 && fault==0` 的新反馈。
5. VOICE owner 运行期间尚未每 20 ms 复查 freshness/fault 并锁存停机。
6. request result 尚未由控制线程结算并回传 M55。
7. 电机 type21 full fault、固件版本、关节坐标和实际电流反馈尚未补齐。

在以上事项完成、0x02 清除且完成低电流空载验证前，VOICE runtime gate 必须保持关闭。
