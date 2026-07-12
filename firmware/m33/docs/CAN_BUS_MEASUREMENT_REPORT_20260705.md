# CAN 总线测量报告

测量时间：2026-07-05  
被测板卡：Infineon PSOC Edge E84 / RT-Thread M33  
串口：KitProg3 USB-UART COM20，115200 baud  
固件版本：RT-Thread 5.0.2，build Jun 17 2026 16:06:13  
CAN 配置：classic CAN，1 Mbps，CANFD0 channel 0，PCLK 20 MHz

## 1. 测量结论

当前 CAN 总线处于健康状态：`TEC=0`、`REC=0`、`CEL=0`、无 error passive、无 bus off。30 秒持续数据流下，总线利用率约 `1.3%`，总帧率约 `100.79 frames/s`，没有 RX FIFO lost/full、没有 TX timeout、没有发送失败。

F103 传感器数据帧 `0x7C2` 稳定在约 `50 Hz`，周期 `P50/P95/P99/max = 20/20/20/20 ms`，jitter `P95/max = 0/0 ms`。温和请求响应测试 `f103_ping 20 100` 下，端到端延迟 `P50/P95/P99/max = 18/24/25/25 ms`，ACK seq 丢包为 0。

风险点：压力测试 `f103_ping 100 10` 下，100 个请求只匹配到 16 个 ACK，匹配到的 ACK 延迟约 `1.09~1.14 s`。这不像 CAN 物理层问题，因为同时 `TEC/REC/CEL=0`、队列 overflow=0，更像 F103 应用层命令/ACK 处理能力或命令队列限制。

## 2. 启动与硬件基线

复位后 shell 正常：

```text
RT-Thread 5.0.2 build Jun 17 2026 16:06:13
```

CAN 寄存器探测：

```text
base=0x42840000 mram=0x42850000 ch=0 irq=106
ctl=0x00000000 status=0x00000000 ir=0x00000000
```

raw CAN 初始化成功：

```text
init ret=0
pclk0=20000000 pclk1=20000000 div=4 en=1
nbtp=0x06000e03 psr=0x00000708
```

在控制层未启动前，RX FIFO 很快被 F103 流填满：

```text
rxf0s fill=16 full=1 lost=0
poll id=0x000007c2 dlc=8
```

说明 F103 数据已经在总线上发送，初始 FIFO full 是因为软件尚未持续 drain，不是物理层错误。

控制层启动成功后：

```text
ctrl_can / ros_cmd / m_status / rehab_sv threads created
control_init ret=0
```

## 3. 30 秒持续流基线

测试命令：

```text
canm_reset 1000000
canm_expect 0x7C2 20 std
canm_expect 0x7C3 1000 std
canm_expect 0x321 1000 std
canm_seq 0x7C1 1 std
canm_pair 0x7C0 1 0x7C1 1 std
wait 30s
canm_show
canm_ids
```

总线汇总：

```text
elapsed_ms=36758
rx=1918
tx=1787
frames_s=100.79
payload_Bps=799
util_permille=13
est_bits=493954
tx_fail=0
id_overflow=0
```

错误与队列：

```text
TEC=0 REC=0 CEL=0 CEL_delta=0
LEC=0 DLEC=7 EP=0 EW=0 BO=0
rxf0_fill=2 rxf0_full=0 rxf0_lost=0
rx_lost_count=0 rx_full_count=0 rx_extract_fail=0 rx_drain_limit=0
tx_timeout=0 tx_send_fail=0 tx_pending_suppressed=0
```

关键 CAN ID：

| CAN ID | 方向 | 帧率 | 周期 P50/P95/P99/max | jitter P95/max | 说明 |
|---|---:|---:|---:|---:|---|
| 0x7C2 | RX | 50.19 fps | 20/20/20/20 ms | 0/0 ms | F103 传感器数据，稳定 |
| 0x7C3 | RX | 1.00 fps | 1001/1003/1004/1004 ms | 19/19 ms | F103 health |
| 0x321 | RX | 1.02 fps | 1001/1003/1004/1004 ms | 19/19 ms | NanoPi heartbeat |
| 0x330~0x334 | TX | 各 9.52 fps | N/A | N/A | M33 motor telemetry |
| 0x322 | TX | 1.02 fps | N/A | N/A | M33 status |

控制层累计计数：

```text
rx_total=4194
heartbeat=83
F103 ack=0 sensor=4111 health=83
last_rx=0x7C2 len=8
```

F103 最近样本：

```text
ADC4 ch0=247 ch1=439 ch2=0 ch3=1321
F103 state=1 err=0 q=0
```

## 4. 温和 ping 延迟测试

测试命令：

```text
canm_reset 1000000
canm_seq 0x7C1 1 std
canm_pair 0x7C0 1 0x7C1 1 std
f103_ping 20 100
canm_show
canm_ids
```

总线汇总：

```text
elapsed_ms=8177
rx=453
tx=418
frames_s=106.51
payload_Bps=845
util_permille=14
tx_fail=0
```

端到端延迟：

```text
tx=0x7C0 payload[1] -> rx=0x7C1 payload[1]
matched=20
unmatched_rx=0
overwritten_tx=0
P50=18 ms
P95=24 ms
P99=25 ms
max=25 ms
```

应用层 seq：

```text
0x7C1 rx=20
seq_lost=0
seq_dup=0
```

队列与错误：

```text
TEC=0 REC=0 CEL=0
rxf0_full=0 rxf0_lost=0 rx_drain_limit=0
tx_timeout=0 tx_send_fail=0
```

## 5. 10 ms ping 压力测试

测试命令：

```text
canm_reset 1000000
canm_seq 0x7C1 1 std
canm_pair 0x7C0 1 0x7C1 1 std
f103_ping 100 10
canm_show
canm_ids
```

总线仍健康：

```text
frames_s=109.38
util_permille=14
TEC=0 REC=0 CEL=0
rxf0_full=0 rxf0_lost=0 rx_drain_limit=0
tx_timeout=0 tx_send_fail=0
```

但应用层 ACK 明显异常：

```text
0x7C0 tx=100
0x7C1 rx=16
matched=16
latency P50/P95/P99/max = 1089/1137/1137/1137 ms
seq_lost=0 for received ACKs
```

解释：`seq_lost=0` 只说明收到的 16 个 ACK 内部连续，不代表 100 个请求都被 F103 处理。实际请求响应匹配率是 `16/100 = 16%`。同时 CAN 控制器没有错误、没有 overflow，因此优先怀疑 F103 应用层命令处理、ACK 队列或协议限速，而不是 CAN 物理层。

## 6. 指标逐项回答

| 指标 | 结果 |
|---|---|
| 总线利用率 | 基线约 1.3%，ping 测试约 1.4%，固件估算值 |
| frames/s | 基线 100.79，温和 ping 106.51，压力 ping 109.38 |
| 每个 CAN ID 周期偏差 | 0x7C2 最稳定，20 ms 周期 P99/max 都为 20 ms；0x7C3/0x321 约 1 s 周期，P99/max 约 1004 ms |
| 端到端延迟 | 温和 ping P50/P95/P99/max = 18/24/25/25 ms；压力 ping 匹配 ACK 的 P50/P95/P99/max = 1089/1137/1137/1137 ms |
| jitter | 基线 0x7C2 P95/max = 0/0 ms；温和 ping 时 0x7C2 P95/max = 1/10 ms |
| 应用层 seq 丢包率 | 温和 ping 0x7C1 seq_lost=0；压力 ping 收到的 ACK 内部 seq_lost=0，但请求匹配率只有 16% |
| error frame 数量和 TEC/REC | CEL=0，TEC=0，REC=0，无 EW/EP/BO |
| TX/RX 队列 overflow | 正常测量阶段 rxf0_full=0、rxf0_lost=0、rx_drain_limit=0、tx_timeout=0、tx_send_fail=0 |

## 7. 建议

1. 保留当前 1 Mbps CAN 配置，物理层健康。
2. F103 `0x7C2` 20 ms 传感器流表现稳定，可以作为控制/模型输入基线。
3. `f103_ping` 不建议用 10 ms 间隔压测命令响应；当前 F103 只稳定处理较低频请求。
4. 如果需要高频命令响应，建议在 F103 固件侧增加命令队列深度、ACK 速率限制策略，或明确协议规定最小请求间隔。
5. 下次回归建议固定三组测试：30 s streaming、20x100 ms ping、100x10 ms ping，并比较 `matched`、`latency P99`、`F103 err`。

