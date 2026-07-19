# M33 CAN 心跳租约与安全停机整改记录（2026-07-17）

## 1. 本次范围

本次只收紧 NanoPi 通过 CAN 控制主动、助力、抗阻三种电流控制模式时的心跳超时行为，未修改 MuJoCo 指令格式、CAN ID、助力算法参数、蓝牙配对代码和记忆回放控制路径。

目标链路：

```text
NanoPi 0x321 heartbeat
        |
        v
CAN RX 只更新时间戳
        |
        v
ros_cmd 线程每次循环执行 lease tick
        |
        v
超时认领 -> source + generation 条件 STOP -> 成功后提交 PASSIVE
```

当前 `CONTROL_ROS_HEARTBEAT_TIMEOUT_MS` 为 2500 ms。STOP 失败时保持原 CAN 活动模式的软件所有权，但锁存 `stop_pending`，禁止 rehab worker 继续输出，并每 100 ms 重试一次。

## 2. 提交拆分

| 提交 | 内容 |
| --- | --- |
| `d5dea99f5` | 纯 CAN 心跳租约状态机和主机测试 |
| `556105771` | service generation、actuation mutex、条件 STOP |
| `b6299eb09` | STOP 失败锁存和跨代 fault STOP 保护 |
| `3f15b70ac` | 在 ros_cmd 周期接入超时监督 |
| `9df194c4a` | `cmd_control_debug` 输出租约诊断 |

## 3. 并发约束

### 3.1 锁职责

- `s_rehab_adapter.lock`：只保护心跳租约、超时认领和诊断计数。
- `s_rehab.actuation_lock`：串行化模式代次切换、活动模式电机输出和 STOP。
- `s_rehab.lock`：保护 service 状态、策略状态和 worker 诊断。

service 固定锁顺序为：

```text
actuation_lock -> s_rehab.lock -> control_motor_* 内部同步
```

adapter 锁不会在调用 service API 时保持，避免 adapter/service 互锁。

### 3.2 generation 语义

每次成功切换 service 模式后 `mode_generation` 加一。rehab worker 计算策略时保存 generation，真正发电流前再次检查：

- generation 未变化；
- mode 未变化；
- `stop_pending == false`。

任一条件不满足就返回 `-RT_EBUSY`，旧控制周期不能在 STOP 或新模式切换后继续输出。

### 3.3 超时和接管

- 新心跳先取得 adapter 锁：刷新存活时间，超时不成立。
- 超时先取得 adapter 锁：进入锁存状态；之后到来的心跳不能撤销本次 STOP。
- Shell 已切换模式：service 的 source 或 generation 不匹配，旧 CAN STOP 返回 `-RT_EBUSY` 并退出，不会误停 Shell 新模式。
- STOP 失败：不把软件状态伪装成 PASSIVE；普通活动模式命令也不能清除 `stop_pending`。

## 4. 已完成验证

```powershell
rtk gcc -std=c99 -Wall -Wextra -Werror `
  -Itests/host -Iapplications/control `
  tests/host/rehab_can_lease_test.c `
  applications/control/rehab_can_lease.c `
  -o build/rehab_can_lease_test.exe
rtk .\build\rehab_can_lease_test.exe
rtk python tools/test_rehab_can_lease_static.py
rtk python tools/test_rehab_service_actuation_static.py
rtk python tools/test_m33_can_rx_owner_static.py
```

结果：租约主机测试通过；静态接线测试 6 项通过；service actuation 测试 2 项通过；CAN RX owner 测试 6 项通过。

全量 SCons 编译通过：

- `build/rtthread.hex` SHA-256：`d7d720811f7b019324c5d67b9ecd38da6ae92a9f8505fbe604a9dca3f332fee3`
- `rt-thread.elf` SHA-256：`d53d2452ff97d7f210f39306eae6adfb8744c6090c4526223150c47adda7b110`

编译仍有 `control_layer.c` 原有 unused 警告，本次没有扩大处理范围。

## 5. 烧录后验证顺序

2026-07-17 已使用 `tools/flash_m33_verified.ps1` 烧录 `build/rtthread.hex`。OpenOCD 完成原始地址校验和缓存失效后的 XIP 地址校验，并启动 M33。随后只做不触发动作的检查：

```text
cmd_control_debug
list_thread
rehab status
```

预期新增输出：

```text
CTRL_DBG_LEASE: mode=0 gen=<n> timeout=0 retry=0 latched=0 hb_timeout_ms=2500
```

然后恢复 NanoPi CAN，连续发送 `0x321` 心跳并重复执行 `cmd_control_debug`，确认 `hb` 增长且 `timeout` 不增长。只有完成急停、限位、反馈新鲜度和电机故障检查后，才在机械卸载或受控工装上测试活动模式超时：停止心跳超过 2500 ms，预期 `timeout` 加一、模式回到 PASSIVE；若 STOP 发送失败，`latched=1` 且 `retry` 以 100 ms 节流增长。

本次实机被动烟测结果：

```text
CTRL_DBG: rx_total=2 hb=48 ros_id=1 parsed=1 enq=1 applied=1 qfail=0
CTRL_DBG_Q: emergency=1 stale=0 recheck_reject=0 apply_fail=0 ttl_ms=500
CTRL_DBG_LEASE: mode=0 gen=1 timeout=0 retry=0 latched=0 hb_timeout_ms=2500
```

继续观察后 `hb` 从 48 增长到 64，其余计数不变。NanoPi `can0` 为 1 Mbps、`ERROR-ACTIVE`，TX/RX error、bus error 和 bus-off 均为 0。因此已验证新固件的心跳接收、被动命令解析、入队、消费和应用路径；尚未验证活动模式下停止心跳触发的条件 STOP。

## 6. 保留问题

1. 记忆回放的 `control_motor_position_control()` 仍是历史路径，尚未纳入 generation/actuation 保护；因此本次租约明确不监管 MEMORY 模式。
2. NanoPi 已于 2026-07-17 恢复，新 lease 固件已验证 `0x320/0x321 -> M33 -> 0x322` 被动链路和 `CTRL_DBG_LEASE` 诊断；2500 ms 条件 STOP 仍需在机械卸载或受控工装上验证。
3. 蓝牙配对和 App 代码本次未修改。接入前仍需单独审查回调栈、对象生命周期、MTU/长度校验、重复初始化和 M33/M55 共享资源冲突。
4. 本次已烧录并仅发送被动模式命令，没有发送主动、助力、抗阻动作命令；不能仅凭被动链路测试声称实机安全闭环完成。
