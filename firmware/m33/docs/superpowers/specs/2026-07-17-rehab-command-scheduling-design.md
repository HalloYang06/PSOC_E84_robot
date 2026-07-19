# 康复模式调度、0x320 链路与异步命令设计

日期：2026-07-17  
状态：待用户审阅  
适用范围：M33 `rehab_svc`、CAN RX、ROS 命令队列，以及 NanoPi `0x320/0x321` 台架验证路径

## 1. 背景与当前证据

当前板端只读检查得到：

```text
rehab_sv  priority=21  status=ready  stack_used=53%
ctrl_can  priority=18  status=suspend
main      priority=10  status=suspend

rehab status mode=passive fresh=0 assist=0
CTRL_DBG: ros_id=0 parsed=0 enq=0 applied=0 qfail=0
```

该现场没有发现持续占用 CPU 的高优先级线程，因此不能把“助力没有输出”直接归因为 `rehab_svc` 饿死。更直接的事实是 M33 上电后没有收到任何 `0x320`，状态机一直处于 PASSIVE。

当前实现还存在以下架构缺口：

1. `rehab_svc` 没有周期计数、最近运行时刻和最大调度抖动，无法证明线程长期按 20 ms 周期运行。
2. `CONTROL_CAN_RX_THREAD_ENABLE=1`，但 `CONTROL_ROS_CMD_THREAD_ENABLE=0`。
3. CAN RX 线程解析、安全审核后直接调用 `ctrl_apply_ros_command()`，可能在 CAN 接收线程执行电机协议和带延迟的控制操作。
4. 已存在的 ROS MQ 和 `ros_cmd` worker 没有接入当前接收路径。
5. 当前 NanoPi 模式脚本发送 `0x321` 和 `0x320`，但没有形成可重复的端到端计数与状态验收记录。
6. 模式命令只在接收时检查 heartbeat；`rehab_mode_manager_tick()` 为空，进入 CAN 所有的主动模式后没有持续 heartbeat 超时降级。

## 2. 目标

1. 为 `rehab_svc` 增加无副作用的调度诊断：周期计数、最近运行 tick、最大调度抖动。
2. 在空载台架上用 `rehab assist 5` 证明模式真正进入 ASSIST，并观察受限、渐变的非零电流输出。
3. 让 NanoPi 发送的 `0x321/0x320` 到达 M33，使 `ros_id/parsed/applied` 按预期增长。
4. 把正式 CAN 命令路径改为 `CAN RX 解析/审核 -> 非阻塞入队 -> ros_cmd worker 消费/执行`。
5. 对队列满、旧命令、重复命令、heartbeat 过期和 STOP 提供明确行为。
6. 每个源码步骤独立提交、独立构建、独立板端验证，任何一步失败都能单独回退。

## 3. 非目标

- 不修改 MuJoCo 已完成的动作规划和轨迹生成语义。
- 不改变电机协议、CAN bitrate、物理关节映射或零点参数。
- 不把 M55 EMG 推理或小智语音结果直接转换为运动命令。
- 不在本工作中开启临床/佩戴运动配置。
- 不把 App/BLE 命令接入电机输出；BLE 使用单独设计和提交序列。
- 不同时重构整个 `control_layer.c`。

## 4. 实施顺序

### 4.1 第一步：`rehab_svc` 调度诊断

在 `rehab_service_status_t` 或专用只读诊断结构中增加：

```c
rt_uint32_t worker_cycle_count;
rt_tick_t worker_last_tick;
rt_uint32_t worker_max_jitter_ms;
```

统计规则：

1. worker 每轮开始时读取一次 `rt_tick_get()`。
2. 第一轮只建立基线，不计入 jitter。
3. 后续周期的 jitter 为 `abs(actual_delta_ms - CONTROL_REHAB_SERVICE_PERIOD_MS)`。
4. tick 差值使用无符号减法，允许 RT-Thread tick 回绕。
5. 只在已有 `s_rehab.lock` 下更新结构，不增加新 mutex。
6. worker 内不打印日志；由 `rehab status` 读取并显示。
7. 计数使用饱和或自然回绕均可，但文档和测试必须固定一种语义；本设计采用自然 `uint32_t` 回绕。

验收：

- 连续两次 `rehab status` 的 cycle count 增长。
- last tick 更新。
- 空闲台架最大 jitter 有界，不要求硬实时零抖动。
- `ps` 中 `rehab_sv` 栈占用不因诊断显著上升。

该步骤为一个独立提交，不改变助力算法或线程优先级。

### 4.2 第二步：Shell 助力台架验证

测试前置条件：

1. 机械臂空载并固定，人员不佩戴。
2. 急停和断电手段可立即触达。
3. `cmd_motor_fb 5` 连续反馈新鲜，确认位置、速度和故障位。
4. `rehab status` 显示 service 正常运行。
5. 助力最大电流、最小电流和 slew 参数保持提交 `eb7f0d754` 的保守默认值。

测试顺序：

```text
rehab status
cmd_motor_fb 5
rehab assist 5
rehab status
rehab status
rehab stop
rehab status
```

判定标准：

- `mode=assist`，不是继续停留在 passive。
- `fresh=1`。
- 人工轻推关节后 `assist=1`。
- `current_x1000` 从零渐变到非零，绝对值不超过 `limit_x1000`。
- 方向与人工运动方向一致；方向错误立即 STOP，不靠提高电流“试出来”。
- `last=0`，周期计数持续增长。
- `rehab stop` 后模式回到 passive，输出电流回零。

如果 `fault=0x02` 仍存在，必须先确认厂家协议含义和实际使能状态。该故障位不能在设计中无条件忽略。

本步骤原则上不修改源码；板端结果追加到验证文档并独立提交。

### 4.3 第三步：打通 NanoPi `0x320`

正式验证只使用显式台架脚本，不修改 NanoPi 开机服务默认行为。

CAN 协议保持：

```text
0x321: NanoPi heartbeat
0x320 byte0: command
      byte1: command correlation/joint field（保持现有帧兼容）
      byte2: mode for SET_MODE
```

验证顺序：

1. NanoPi 确认 `can0` 为 UP、bitrate 一致且无 bus-off。
2. `candump -L can0` 开始抓包。
3. 连续发送 heartbeat，再发送一次 PASSIVE 模式命令。
4. M33 `cmd_control_debug` 必须显示 `ros_id` 和 `parsed` 增长。
5. PASSIVE 验证通过后，才允许空载发送 ASSIST，并保持周期 heartbeat。
6. `applied` 只有在 worker 实际成功应用命令后增长。
7. 停止 heartbeat 后，活动 CAN 模式必须在定义的 TTL 内降级到 PASSIVE/STOP。

NanoPi 脚本必须：

- 明确区分 heartbeat sequence 和 M33 joint/correlation 字段。
- 支持 `passive|assist|resist|active`，默认只发送 passive。
- 对 `cansend` 返回值失败立即退出。
- 输出精确 CAN payload，方便与 candump 对账。
- 不在系统服务启动时自动发送非 PASSIVE 模式。

该步骤的 NanoPi 脚本和测试在集成仓库中独立提交；板端证据在 M33 验证文档中另行提交。

### 4.4 第四步：CAN RX 入队，`ros_cmd` 消费

#### 所有权

- `ctrl_can`：唯一 CAN RX owner，负责有界 drain、帧分类、解析和轻量安全审核。
- `s_ros_cmd_mq`：固定容量命令队列，复制完整 `control_ros_command_t`，不保存指向 CAN 临时缓冲区的指针。
- `ros_cmd`：唯一普通 ROS 命令执行者，调用 `ctrl_apply_ros_command()`。
- `rehab_svc`：继续唯一执行周期性 assist/resist 策略，不由 CAN RX 直接调用电机 API。

#### 入队规则

1. RX 侧使用 `rt_mq_send()` 或零等待等价接口，绝不等待队列空间。
2. 只有解析成功且初步审核通过的普通命令才入队。
3. 消息携带 `received_tick`、命令字段和必要的审核快照，不携带裸 CAN 指针。
4. `enq` 仅在 `rt_mq_send()` 成功后增长。
5. 队列满时 `qfail` 和 dropped counter 增长，返回接收循环；不能阻塞 CAN RX。
6. 队列满日志限频，不能每帧 `rt_kprintf`。

#### 消费规则

1. worker 收到命令后重新检查 freshness，而不是完全相信入队时状态。
2. 普通命令 age 超过 TTL 时丢弃，`stale` counter 增长，不调用电机 API。
3. 非 PASSIVE 模式应用前重新检查 NanoPi heartbeat。
4. `applied` 只在 `ctrl_apply_ros_command()` 返回 `RT_EOK` 后增长。
5. apply 失败单独计数，并保存最近错误，不把失败算成 applied。
6. 对相同来源、相同 correlation、相同 payload 的紧邻重复命令做幂等丢弃；不得误删新的 STOP。

#### STOP 规则

STOP 不能与普通命令争用一个可能已满的 FIFO：

- RX 解析到 STOP/PASSIVE 时写入独立紧急锁存并唤醒 worker。
- worker 每次取普通队列前先消费紧急锁存。
- 后到 STOP 覆盖先到 STOP 是允许的；任何普通命令不能覆盖待处理 STOP。
- STOP 不因普通命令 age、未知运动参数或队列满而丢失。
- STOP 应保持现有安全审核边界，具体对 unknown joint 的策略在实现计划中用测试固定。

#### 计数与 Shell 状态

`cmd_control_debug` 至少显示：

```text
rx_total hb ros_id parsed enq applied qfail stale duplicate apply_fail urgent_stop
```

计数写入来自两个线程，使用 RT-Thread 原子 API、短临界区或同一统计锁；禁止依赖未定义的数据竞争。

## 5. 调度与优先级

当前优先级：

```text
ctrl_can  = 18
ros_cmd   = 19
tshell    = 20
rehab_svc = 21
```

RT-Thread 数字越小优先级越高。保留上述相对顺序：CAN 接收最高，命令消费次之，康复周期线程低于命令入口。

为了避免 `ros_cmd` 长时间压制 `rehab_svc`：

- worker 每次只消费一个命令，或采用明确的小批量上限。
- 任何电机协议内部等待必须有界。
- 不在 worker 中打印大段日志。
- 队列深度按突发吸收能力设置，不以堆积方式掩盖生产速度过快。

诊断数据用于判断是否需要调整优先级；没有板端 jitter 证据前不先改优先级。

## 6. 测试策略

### Host/静态测试

- `rehab_svc` 首周期、正常周期、延迟周期和 tick 回绕的 jitter 计算。
- RX 成功入队、队列满不阻塞。
- TTL 边界、TTL+1 过期。
- duplicate 丢弃和新 correlation 接受。
- apply 成功/失败计数语义。
- 普通队列满时 STOP 仍能被 worker 优先处理。
- heartbeat 超时后非 PASSIVE 命令拒绝，活动 CAN 模式降级。
- 禁止 CAN RX 路径直接调用 motor output API 的静态断言。

### 板端回归

每个固件步骤均执行：

1. 构建、记录 ELF/HEX hash 和 map。
2. 只烧录 M33 对应镜像并 verify。
3. Shell 空闲 60 秒。
4. `ps`、`free`、`rehab status`、`cmd_control_debug`。
5. CAN heartbeat/PASSIVE。
6. 空载 ASSIST 小电流验证。
7. 队列突发、旧命令和 STOP fault injection。
8. 确认 M55 IPC、F103、Wi-Fi/云端观测链路没有因 M33 调度变化退化。

## 7. 提交边界

建议提交顺序：

1. `diag(rehab): expose worker cycle and jitter status`
2. `docs(rehab): record shell assist bench result`
3. `fix(nanopi): send validated rehab mode frames`
4. `test(control): cover ROS queue freshness and urgent stop`
5. `fix(control): enqueue CAN commands for ros worker`
6. `docs(control): record async command board validation`

任何提交不得顺便修改 BLE、M55 IPC、SMIF、MuJoCo 或蓝牙配对代码。

## 8. 回退与成功标准

每一步使用 `git revert <commit>` 回退，不使用 destructive reset。

完成标准：

- `rehab_svc` 周期计数持续增长，last tick 更新，最大 jitter 可读。
- Shell `rehab assist 5` 在空载下产生受限且方向正确的渐变电流，并能可靠 STOP。
- NanoPi 抓包与 M33 `ros_id/parsed/enq/applied` 能逐帧对账。
- CAN RX 不再同步执行普通电机/模式命令。
- 队列满不会阻塞 CAN RX，旧命令不会应用，STOP 不会因队列满丢失。
- heartbeat 消失后，CAN 所有的活动模式在有限时间内安全降级。
