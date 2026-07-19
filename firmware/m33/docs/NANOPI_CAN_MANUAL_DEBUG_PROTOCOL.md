# NanoPi CAN 手动调试协议

Last updated: 2026-07-06

本文用于现场只拿 NanoPi 终端手动触发 CAN 帧时，快速判断 NanoPi、F103 传感节点、电机和 M33 链路是否在线。所有命令都是 bench-debug 手动调试命令，不代表系统已经具备运动许可。

## 1. 基本原则

- CAN 波特率：Classic CAN 1 Mbps。
- 物理测试必须关闭 loopback；loopback 只用于 NanoPi 自检。
- `candump` 看到自己刚 `cansend` 的帧，只能说明本机有发送回显，不代表对端收到了。
- 真正通了要看对端回包或对端主动上报。
- 如果 `ip -details -statistics link show can0` 里 `tx errors`、`bus-off`、`re-started bus-errors` 增长，优先查物理层、供电、终端电阻、CANH/CANL、共地和波特率。

## 2. NanoPi CAN 启动

正常物理总线测试：

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000 loopback off listen-only off berr-reporting on restart-ms 100
sudo ip link set can0 up
ip -details -statistics link show can0
```

确认输出中不要有：

```text
<LOOPBACK>
```

只做 NanoPi 本机自检时才打开 loopback：

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000 loopback on
sudo ip link set can0 up
```

自检需要两个终端：

```bash
# 终端 A
candump can0,123:7FF

# 终端 B
cansend can0 123#1122334455667788
```

看到 `123 [8] 11 22 33 44 55 66 77 88` 只说明 NanoPi SocketCAN/驱动/控制器基本可用，不证明外部 CANH/CANL 链路可用。

## 3. M33 / NanoPi 心跳

协议：

| CAN ID | 方向 | 含义 |
|---|---|---|
| `0x321` std | NanoPi -> M33 | heartbeat |
| `0x322` std | M33 -> NanoPi | heartbeat ACK / safety status |
| `0x330~0x337` std | M33 -> NanoPi | M33 聚合电机状态 |

NanoPi 发送 heartbeat：

```bash
candump can0,321:7FF,322:7FF
cansend can0 321#01
```

正常应看到：

```text
can0  322  [8]  A5 01 ...
```

如果只看到 `321 [1] 01`，通常只是 NanoPi 自己的发送回显，不能证明 M33 收到。需要接 M33 串口时用 `cmd_control_debug` 看 `hb=` 是否增加。

## 4. F103 / C8T6 传感节点

协议：

| CAN ID | 方向 | 含义 |
|---|---|---|
| `0x7C0` std | NanoPi/M33 -> F103 | 控制命令 |
| `0x7C1` std | F103 -> NanoPi/M33 | ACK |
| `0x7C2` std | F103 -> NanoPi/M33 | 传感数据，四路 ADC 小端 |
| `0x7C3` std | F103 -> NanoPi/M33 | health |

命令字：

| cmd | 含义 |
|---|---|
| `0x01` | SET_RATE |
| `0x03` | START_STREAM |
| `0x04` | STOP_STREAM |
| `0x05` | GET_STATUS |

手动 ping F103：

```bash
# 终端 A：只看 F103 回包
candump can0,7C1:7FF,7C2:7FF,7C3:7FF

# 终端 B：GET_STATUS, cmd=05 seq=01
cansend can0 7C0#0501000000000000
```

正常应看到：

```text
can0  7C1  [8]  05 01 00 ...
```

设置 50 Hz 并启动数据流：

```bash
# SET_RATE: cmd=01 seq=02 target=02 rate=0x0032
cansend can0 7C0#0102023200000000

# START_STREAM: cmd=03 seq=03
cansend can0 7C0#0303000000000000
```

正常应看到：

```text
can0  7C2  [8]  ...
can0  7C3  [8]  ...
```

停止数据流：

```bash
cansend can0 7C0#0404000000000000
```

判断：

| 现象 | 含义 |
|---|---|
| 只看到 `7C0` | 多半是 NanoPi 本机发送回显，F103 没回 |
| 有 `7C3` 没有 `7C1` | F103 能发 health，但可能没有收到/处理控制帧 |
| 有 `7C1` 没有 `7C2` | 控制链路通，查 stream enable、采样任务、F103 上报逻辑 |
| 有 `7C2` | F103 传感数据链路通 |

## 5. 私有协议电机 4/5/6

当前 bench 映射：

| 电机 | 协议 | 主动反馈 ID |
|---|---|---|
| 4 | Lingzu RS00 private extended-frame | `0x180004FD` ext |
| 5 | Lingzu RS00 private extended-frame | `0x180005FD` ext |
| 6 | Lingzu EL05 private extended-frame | `0x180006FD` ext |

Get_ID 请求的扩展帧 ID 公式：

```text
ext_id = (comm_type << 24) | (master_id << 8) | motor_id
comm_type = 0x00
master_id = 0xFD
```

手动 ping 4/5/6：

```bash
# 终端 A：看 Get_ID 回包和主动反馈
candump can0,000004FE:1FFFFFFF,000005FE:1FFFFFFF,000006FE:1FFFFFFF,180004FD:1FFFFFFF,180005FD:1FFFFFFF,180006FD:1FFFFFFF

# 终端 B：Get_ID
cansend can0 0000FD04#0000000000000000
cansend can0 0000FD05#0000000000000000
cansend can0 0000FD06#0000000000000000
```

正常回包类似：

```text
can0  000004FE  [8]  ...
can0  000005FE  [8]  ...
can0  000006FE  [8]  ...
```

如果只看主动反馈：

```bash
candump can0,180004FD:1FFFFFFF,180005FD:1FFFFFFF,180006FD:1FFFFFFF
```

看到 `180004FD/180005FD/180006FD` 持续出现，说明对应电机在主动上报。

## 6. CANSimple 电机 3

CANSimple 标准 ID 公式：

```text
std_id = (node_id << 5) | cmd_id
```

当前 3 号为 CANSimple/ODrive-like 节点，Address 请求使用广播 node `0x3F` 和 cmd `0x06`：

```bash
candump can0
cansend can0 7E6#
```

若有响应，会看到 Address 相关帧或节点心跳，例如 node 3 的心跳 ID：

```text
0x061 = (3 << 5) | 0x01
```

## 7. 常见误判

### 7.1 loopback 导致误判

如果 `ip -details -statistics link show can0` 显示：

```text
can <LOOPBACK,...>
```

此时 `candump` 看到的 `7C0`、`321`、`123` 可能只是 NanoPi 自己回环，不能证明物理总线通。物理测试前必须：

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000 loopback off listen-only off berr-reporting on restart-ms 100
sudo ip link set can0 up
```

### 7.2 后台 heartbeat 干扰

如果 `candump can0` 一直刷：

```text
can0  321  [1]  01
can0  321  [1]  02
```

说明有后台进程在发 NanoPi heartbeat。查进程：

```bash
ps aux | grep -E "cansend|can|heartbeat|python"
```

调试指定节点时建议用过滤器，只看目标 ID，避免被 `0x321` 刷屏干扰。

### 7.3 Network is down

出现：

```text
read: Network is down
write: Network is down
```

说明 `candump/cansend` 执行时 `can0` 没有处于 UP 状态，重新执行第 2 节启动命令。

## 8. 最小现场排查顺序

1. `ip -details -statistics link show can0`，确认 `can0` UP、1 Mbps、非 loopback。
2. 只看对端回包，不看本机发送回显。
3. F103：发 `7C0#0501000000000000`，等 `7C1` 或 `7C3`。
4. 电机：发 `0000FD04/05/06`，等 `000004FE/000005FE/000006FE` 或 `180004FD/180005FD/180006FD`。
5. M33：发 `321#01`，等 `322#A5...`。
6. 若无对端回包，马上看 `tx errors/bus-off` 是否增长，再查物理层。

