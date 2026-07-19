# M33 CAN RX 与 ROS 命令线程解耦记录（2026-07-17）

## 1. 修改目标

本步骤只调整 `0x320` 命令的线程所有权，不改变 NanoPi/MuJoCo 报文格式、关节映射、限位参数和底层电机动作函数。

修改前，CAN RX 线程在解析和安全审核后直接调用 `ctrl_apply_ros_command()`。工程虽然已经创建了消息队列对象和 `ros_cmd` 消费函数，但生产者没有调用 `rt_mq_send()`，消费线程也被编译开关关闭。因此耗时的电机操作会占用 CAN RX 线程，并使 F103、心跳和电机反馈的收包时延互相影响。

## 2. 修改后的数据流

```text
NanoPi 0x320
    -> CAN RX 线程解析完整 control_ros_command_t 副本
    -> 第一次安全审核
    -> 非阻塞消息队列
    -> ros_cmd 线程检查排队时效
    -> 第二次安全审核
    -> 原 ctrl_apply_ros_command()
    -> 原电机/rehab_service 路径
```

关键约束：

- 队列深度仍为 16，没有动态内存分配；内存池使用 RT-Thread 的 `RT_MQ_BUF_SIZE` 计算消息头和对齐开销，实际容量与配置一致。
- 普通命令使用非阻塞 `rt_mq_send()`；队列满时拒绝新命令，不阻塞 CAN RX。
- STOP 和 SET_MODE/PASSIVE 不进入普通 MQ，而是进入独立安全锁存通道。
- 全局 PASSIVE 保存最新序号；单关节 STOP 使用位图保存，多个关节的停止请求不会互相覆盖，`clear_fault` 请求只累加、不回退。
- `ros_cmd` 每次处理普通命令前先取安全锁存，并在普通队列空闲时最多等待 10 ms 后再次检查，因此不需要清空普通队列，也不会误删先前的 STOP。
- MQ 收到的普通命令先放入线程本地 `deferred_normal`，回到循环顶部再次检查安全锁存后才执行，避免 STOP 在 10 ms 等待窗口内被一条普通动作插队。
- 普通命令在队列中超过 500 ms 后丢弃；STOP/PASSIVE 不因年龄被拒绝。
- 消费线程重新执行安全审核，避免心跳、反馈或模式在排队期间已经变化。
- `applied` 只在底层动作函数返回 `RT_EOK` 后增长。

## 3. 诊断字段

Shell 执行：

```text
cmd_control_debug
```

原有第一行仍保留：

```text
CTRL_DBG: ... ros_id=... parsed=... enq=... applied=... qfail=...
```

新增第二行：

```text
CTRL_DBG_Q: emergency=... stale=... recheck_reject=... apply_fail=... ttl_ms=500
```

含义：

- `emergency`：成功锁存的 STOP/PASSIVE 命令数。
- `stale`：消费时已超过 500 ms 的普通命令数。
- `recheck_reject`：RX 首次审核通过，但消费时二次审核拒绝的命令数。
- `apply_fail`：二次审核通过，但原动作函数执行失败的命令数。
- `qfail`：普通命令入队失败，或安全锁存输入无效的次数。

正常单次 `0x320` 被动模式冒烟应看到：

```text
ros_id +1
parsed +1
enq +1
applied +1
emergency +1
qfail/stale/recheck_reject/apply_fail 不增长
```

## 4. 自动验证

时效边界主机测试：

```powershell
rtk gcc -std=c11 -Wall -Wextra -Werror `
  -I tests/host -I applications/control `
  tests/host/control_ros_queue_timing_test.c `
  applications/control/control_ros_queue_timing.c `
  -o tmp/control_ros_queue_timing_test.exe
rtk ./tmp/control_ros_queue_timing_test.exe
```

结果：`control_ros_queue_timing_test PASS`。测试覆盖 TTL 边界、超时、32 位 tick 回绕和紧急命令时效豁免。

安全锁存主机测试：

```powershell
rtk gcc -std=c11 -Wall -Wextra -Werror `
  -I tests/host -I applications/control `
  tests/host/control_ros_emergency_latch_test.c `
  applications/control/control_ros_emergency_latch.c `
  -o tmp/control_ros_emergency_latch_test.exe
rtk ./tmp/control_ros_emergency_latch_test.exe
```

结果：`control_ros_emergency_latch_test PASS`。测试覆盖多关节 STOP 保留、PASSIVE 与 STOP 共存、`clear_fault` 累加和非法关节拒绝。

所有权静态测试：

```powershell
rtk python tools/test_m33_can_rx_owner_static.py
```

结果：6 项通过。测试约束消费线程开启、RX 不直接执行、普通/紧急入队存在，以及消费前完成时效和二次审核。

完整构建：

```powershell
rtk proxy cmd.exe /d /s /c "set RTT_EXEC_PATH=F:\RT-ThreadStudio\platform\env_released\env-new\tools\gnu_gcc\arm_gcc\mingw\bin&& F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j8"
```

结果：SCons exit code 0，`control_ros_queue_timing.o` 和 `control_ros_emergency_latch.o` 已链接，并生成 `build/rtthread.hex`。工程原有未使用变量/函数警告仍存在，本步骤没有扩大范围处理。

本次构建产物：

```text
rt-thread.elf       SHA-256 038D32DB99483DCEF2417E9CFF98EBAF61597C3F7732E8C72B09619E9159AE10
build/rtthread.hex  SHA-256 AD36FB5F9764BCD3D186B77F5F3B399A991921C03284CFC7C884E4BE56B81F75
```

哈希对应当时整个工作区构建状态，其中仍包含用户已有的其他未提交源码；它只用于板端问题与 ELF/HEX 精确对应。

## 5. 板端验证顺序

本步骤提交后再烧录，便于任何异常直接回到该提交之前。

1. 上电后先运行两次 `cmd_control_debug`，确认 Shell、心跳、F103 和电机反馈计数仍增长。
2. NanoPi 只发送已验证的 `passive` 冒烟命令，不发送 assist/active/resist。
3. 再运行 `cmd_control_debug`，确认 `ros_id/parsed/enq/applied` 各增长，错误计数不增长。
4. 运行 `list_thread`，确认 `ros_cmd` 存在且栈余量正常。
5. 在机械臂未完成故障含义确认和物理安全确认前，不执行 `rehab assist 5`。

## 6. 已知边界与下一步

安全锁存不能中断已经进入底层 CAN 动作调用的命令。STOP/PASSIVE 仍需等待该调用返回后才能执行，因此底层动作调用必须保持有界，不能在控制线程中无限等待。

初版提交 `57aa69dea` 使用 `RT_IPC_CMD_RESET` 处理满队列。复审发现 reset 可能同时删除先前排队的另一条 STOP，因此后续修正提交改为独立安全锁存。板端联调应使用包含修正提交的版本，不应停留在初版提交。

下一独立步骤是在 `ros_cmd`/rehab 服务所有权内实现心跳租约到期后的条件化停机，并确保停机失败可重试。不能把多关节 STOP 重新放回 CAN RX 线程，否则会再次阻塞收包。

## 7. 最终固件板端记录

最终修正提交：`07e6f27dd fix(control): preserve latched emergency commands`。

使用 `tools/flash_m33_verified.ps1` 烧录最终 `build/rtthread.hex`：

```text
raw verify: 593920 bytes
XIP verify: 585452 bytes
result: Verified flash completed successfully
```

烧录后 COM16 Shell 正常。`ps` 显示：

```text
ros_cmd   priority=19 stack=2048 max_used=22% suspend
ctrl_can  priority=18 stack=2048 max_used=13% suspend
rehab_sv  priority=21 stack=1536 max_used=44% suspend
tshell    priority=20 stack=4096 max_used=16% running
```

未发现线程栈逼近上限或 Shell 饿死。首次 `cmd_control_debug` 为：

```text
ros_id=0 parsed=0 enq=0 applied=0 qfail=0
emergency=0 stale=0 recheck_reject=0 apply_fail=0
F103 ack=0 sensor=0 health=0
```

当时外部总线没有任何流量。NanoPi `192.168.3.36` 无 ping，TCP 22 建连后在 SSH 密钥交换前由远端关闭，M33 的 F103/心跳计数也保持 0。因此最终修正版尚未完成 NanoPi `passive` 板端冒烟，不能把本次记录解释为端到端验证通过。

NanoPi/总线供电恢复后补测：

1. 连续两次 `cmd_control_debug`，确认 `hb` 或 F103 计数增长。
2. 运行 `tools/nanopi_rehab_mode.sh passive`。

### 2026-07-17 NanoPi 恢复补测

NanoPi `192.168.3.36` 恢复后，`can0` 状态为 `UP/ERROR-ACTIVE`、1 Mbps；TX/RX error、bus-off、restart、error-passive 均为 0。

安全脚本连续执行两次 PASSIVE，实际发送：

```text
321#01
321#01
320#040100

321#02
321#02
320#040200
```

NanoPi 收到 `0x322` 状态回包。M33 两次 `cmd_control_debug` 对比：

```text
ros_id=1 parsed=1 enq=1 applied=1
ros_id=2 parsed=2 enq=2 applied=2
```

`qfail=0 stale=0 recheck_reject=0 apply_fail=0`。这确认当前板上队列固件的 `0x320 -> CAN RX -> MQ -> ros_cmd -> apply -> 0x322` 被动模式链路已端到端通过。
3. 再执行 `cmd_control_debug`，确认 `ros_id/parsed/enq/applied/emergency` 各增长 1。
4. 确认 `qfail/stale/recheck_reject/apply_fail` 不增长，模式仍为 PASSIVE。
