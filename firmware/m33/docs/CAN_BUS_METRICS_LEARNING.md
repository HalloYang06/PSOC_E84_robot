# CAN 总线量化测量学习文档

本文面向当前 M33/Infineon/RT-Thread 工程，用来把 CAN 通信从“能不能收到”推进到“性能和可靠性可量化”。重点指标包括总线利用率、frames/s、每个 CAN ID 的周期偏差、端到端延迟、jitter、应用层 seq 丢包、错误计数和队列 overflow。

## 1. 为什么不只看丢包率

丢包率只能回答“有没有少帧”，不能回答下面这些问题：

- 总线是不是已经接近饱和。
- 某个 CAN ID 的周期是否稳定，例如 10 ms 传感器帧有没有抖到 18 ms。
- 命令发出到响应返回要多久，P95/P99 是否已经影响控制环。
- CAN 控制器是否进入 error warning、error passive 或 bus off。
- 问题发生在物理层、控制器 FIFO、软件轮询线程，还是应用协议 seq。

所以 CAN 测量建议分三层看：

- 总线层：bitrate、总线利用率、frames/s、error frame、TEC/REC。
- 驱动/队列层：RX FIFO full/lost、TX timeout、发送失败、轮询一次是否经常 drain 到上限。
- 应用层：seq 丢包、周期偏差、jitter、端到端延迟。

## 2. 指标定义

### 2.1 总线利用率

总线利用率表示单位时间内 CAN 总线上被帧占用的 bit 比例：

```text
bus_utilization = transmitted_bits / (bitrate * measurement_time)
```

经典 CAN 的实际帧长会受 ID 类型、DLC、CRC、ACK、EOF、intermission 和 bit stuffing 影响。固件内测量通常只能估算。本工程使用经典 CAN 估算：

```text
standard frame bits ~= (47 + data_bytes * 8) * 1.2
extended frame bits ~= (67 + data_bytes * 8) * 1.2
```

注意：要做非常精确的总线占用，应使用 CAN 分析仪或逻辑分析仪；固件估算适合做趋势、压力测试和回归对比。

### 2.2 frames/s

frames/s 表示单位时间内观察到的帧数：

```text
frames_s = (rx_frames + tx_frames) / measurement_time_seconds
```

也可以按 CAN ID 分开看 `rx_fps` 和 `tx_fps`，用于识别哪个 ID 是流量大头。

### 2.3 每个 CAN ID 的周期偏差

如果某个 CAN ID 理论上每 `T` ms 来一次，实际相邻接收时间为 `interval_ms`，周期偏差是：

```text
period_deviation_ms = abs(interval_ms - expected_period_ms)
```

例如 F103 传感器帧如果配置为 10 ms 周期：

```text
canm_expect 0x7C1 10 std
```

之后 `canm_ids` 会给出该 ID 的周期 P50/P95/P99/max。

### 2.4 jitter

jitter 表示相邻周期之间的变化幅度：

```text
jitter_ms = abs(current_interval_ms - previous_interval_ms)
```

如果配置了 expected period，本工程也会把周期偏差作为 jitter 样本记录，便于直接看“偏离目标周期多少”。

重点看：

- `jitter_p95_ms`：大多数情况下是否稳定。
- `jitter_max_ms`：是否偶发卡顿或线程被抢占。

### 2.5 端到端延迟

端到端延迟需要有一个可匹配的请求和响应。最常用方式是在 TX 和 RX payload 中放同一个 seq：

```text
latency_ms = rx_timestamp(seq=N) - tx_timestamp(seq=N)
```

本工程支持配置 seq 匹配：

```text
canm_pair <tx_id> <tx_seq_offset> <rx_id> <rx_seq_offset> [std|ext]
```

默认配置示例：

```text
canm_default
# 等价于：
# canm_pair 0x7C0 1 0x7C1 1 std
# canm_seq  0x7C1 1 std
```

看延迟时建议关注：

- P50：正常中位延迟。
- P95：大多数场景的上界。
- P99：尾延迟，控制系统里很关键。
- max：最坏情况，可能来自线程调度、总线竞争、对端处理慢或错误重传。

### 2.6 应用层 seq 丢包率

如果 payload 里有递增 seq，可以检测应用层丢包：

```text
lost = current_seq - last_seq - 1
loss_permille = lost * 1000 / (received + lost)
```

配置方式：

```text
canm_seq <rx_id> <seq_offset> [std|ext]
```

如果对端复位导致 seq 归零，请先执行：

```text
canm_reset 1000000
canm_default
```

### 2.7 error frame、TEC、REC

CAN 控制器不会像普通 RX 帧一样把 error frame 交给应用层。固件侧通常读取控制器寄存器：

- `TEC`：Transmit Error Counter。
- `REC`：Receive Error Counter。
- `CEL`：CAN Error Logging counter，可作为 error event 数量参考。
- `LEC/DLEC`：最近一次仲裁段/数据段错误类型。
- `EW`：Error Warning。
- `EP`：Error Passive。
- `BO`：Bus Off。

本工程通过 `ifx_can_direct_get_diag()` 读取 ECR/PSR/IR，并在 `canm_show` 中打印。

### 2.8 TX/RX 队列 overflow

本工程关注这些队列/缓冲风险：

- RX FIFO0 full：硬件 RX FIFO 达到满状态。
- RX FIFO0 lost：硬件 RX FIFO 因满而丢帧。
- RX drain limit：软件一次轮询读到上限，说明 RX 压力接近处理能力边界。
- TX timeout：等待 TX buffer 发出超时。
- TX send fail：PDL 发送接口返回失败。
- TX pending suppressed：旧逻辑中因为有 pending TX 而抑制新发送。

队列 overflow 不一定等于应用层丢包，但它通常是应用丢包的前兆。

## 3. 当前工程的测量实现

新增模块：

```text
applications/control/can_metrics.c
applications/control/can_metrics.h
```

接入点：

```text
control_layer.c
  ctrl_can_send()             -> can_metrics_record_tx()
  ctrl_handle_can_message()   -> can_metrics_record_rx()
  ctrl_poll_can_messages()    -> can_metrics_record_rx_drain_limit()
  control_layer_init()        -> can_metrics_reset()

drv_can.c
  ifx_can_direct_send()       -> TX fail/timeout 计数
  ifx_can_direct_recv()       -> RX FIFO full/lost/extract fail 计数
  ifx_can_direct_get_diag()   -> 读取 ECR/PSR/IR/RXF0S/TXBRP/TXBTO/TXBCF
```

当前测量粒度使用 RT-Thread tick 毫秒时间戳，`RT_TICK_PER_SECOND=1000` 时分辨率约 1 ms。

## 4. Shell 命令

### 4.1 清零并设置 bitrate

```text
canm_reset 1000000
```

### 4.2 加载本项目默认测量项

```text
canm_default
```

默认项：

```text
seq tracking: 0x7C1 payload[1]
latency pair: 0x7C0 payload[1] -> 0x7C1 payload[1]
bitrate:      1000000
```

### 4.3 配置某个 ID 的期望周期

```text
canm_expect 0x7C1 10 std
canm_expect 0x330 20 std
```

### 4.4 配置某个 ID 的 seq 丢包检测

```text
canm_seq 0x7C1 1 std
```

这里表示 `0x7C1` 的 payload 第 1 字节是 seq。

### 4.5 配置端到端延迟

```text
canm_pair 0x7C0 1 0x7C1 1 std
```

表示发送 ID `0x7C0` 的 payload[1] 与接收 ID `0x7C1` 的 payload[1] 匹配，计算 TX 到 RX 延迟。

### 4.6 查看汇总

```text
canm_show
```

输出包括：

```text
CANM_SUM ...
CANM_ERR ...
CANM_Q ...
CANM_LAT ...
```

### 4.7 查看每个 ID

```text
canm_ids
```

输出包括：

```text
CANM_ID id=...
```

## 5. 推荐测量流程

### 5.1 基线测量

1. 上电并确认 CAN 线连接正确。
2. 在 shell 中执行：

```text
canm_reset 1000000
canm_default
```

3. 如果已知周期，配置周期：

```text
canm_expect 0x7C1 10 std
canm_expect 0x330 20 std
```

4. 让系统稳定运行 30 到 60 秒。
5. 读取结果：

```text
canm_show
canm_ids
```

### 5.2 F103 请求-响应延迟测量

如果 `f103_ping` 使用 `0x7C0` 发请求、`0x7C1` 回响应，并且 payload[1] 是 seq：

```text
canm_reset 1000000
canm_default
f103_ping 100 10
canm_show
canm_ids
```

重点看：

- `CANM_LAT ... p50_ms/p95_ms/p99_ms/max_ms`
- `CANM_ID id=0x000007C1 ... seq_lost/seq_loss_permille`
- `CANM_Q ... rx_fifo0_lost/rx_fifo0_full/rx_drain_limit`

### 5.3 压力测量

压力测量目标是找到系统边界：

1. 降低对端发送周期，例如从 20 ms 改成 10 ms、5 ms。
2. 每档运行 30 秒。
3. 记录 `bus_util_permille`、`frames_s`、`jitter_p95_ms`、`seq_loss_permille`、`rx_fifo0_lost`。
4. 如果 `rx_drain_limit` 持续增加，说明软件轮询已接近瓶颈。
5. 如果 `TEC/REC/CEL` 增加，优先检查物理层、终端电阻、bitrate、接地和线束。

## 6. 结果解读

### 6.1 CANM_SUM

示例字段：

```text
CANM_SUM dur_ms=30000 bitrate=1000000 rx=3000 tx=100 bits=480000 util_permille=16 frames_s=103.33 tx_fail=0 id_overflow=0
```

关注点：

- `util_permille=16` 表示约 1.6% 总线利用率。
- `frames_s=103.33` 表示平均每秒约 103 帧。
- `tx_fail` 非 0 表示软件发送失败，需要结合 `CANM_Q` 看 TX timeout。
- `id_overflow` 非 0 表示观察到的 CAN ID 超过当前统计槽数量。

### 6.2 CANM_ERR

示例字段：

```text
CANM_ERR tec=0 rec=0 cel=0 lec=7 dlec=7 ew=0 ep=0 bo=0 psr=0x00000707 ir=0x00000000
```

关注点：

- `tec/rec` 增长：总线上存在错误或 ACK 问题。
- `bo=1`：bus off，需要检查物理层或 bitrate。
- `cel` 增长：出现过 CAN 错误事件。

### 6.3 CANM_Q

示例字段：

```text
CANM_Q rxf0_fill=0 rx_fifo0_lost=0 rx_fifo0_full=0 rx_extract_fail=0 rx_drain_limit=0 txbrp=0x0 txbto=0x1 txbcf=0x0 tx_timeout=0 tx_send_fail=0 tx_pending_suppressed=0
```

关注点：

- `rx_fifo0_lost > 0`：硬件 FIFO 已丢帧。
- `rx_drain_limit > 0`：软件一次轮询读满上限，可能要提高 poll 频率、加大 drain limit 或使用中断。
- `tx_timeout > 0`：TX buffer 卡住，可能是总线未 ACK、bus off 或控制器状态异常。

### 6.4 CANM_ID

示例字段：

```text
CANM_ID id=0x000007C1 ide=0 rx=3000 tx=0 rx_fps=100.00 tx_fps=0.00 period_ms p50=10 p95=11 p99=13 max=20 jitter_ms p95=2 max=10 seq_lost=0 seq_dup=0 seq_loss_permille=0
```

关注点：

- `period_ms p95/p99/max` 看周期稳定性。
- `jitter_ms p95/max` 看周期抖动。
- `seq_loss_permille` 看应用层丢包。

### 6.5 CANM_LAT

示例字段：

```text
CANM_LAT tx=0x000007C0/0 rx=0x000007C1/0 matched=100 timeout=0 pending=0 p50_ms=2 p95_ms=4 p99_ms=7 max_ms=9
```

关注点：

- `matched` 应接近请求数量。
- `timeout` 增长说明请求没有匹配到响应。
- `p99_ms/max_ms` 是控制系统里最应该关注的尾延迟。

## 7. 硬件检查清单

测量前先确认：

- 两端 bitrate 一致，本工程默认 1 Mbps。
- 使用 classic CAN 还是 CAN FD 一致，本工程当前强制 classic CAN。
- CANH/CANL 接反会导致 REC/TEC 增长或 bus off。
- 总线两端各 120 ohm 终端，断电测 CANH-CANL 约 60 ohm。
- 所有节点共地。
- 收发器供电、电平和 standby/silent 引脚状态正确。
- 线束不要过长，优先短线基线测试。

## 8. 当前实现限制

- 总线利用率是固件估算，不替代 CAN 分析仪。
- 时间戳是毫秒级，亚毫秒延迟需要硬件 timestamp 或更高分辨率计时器。
- 端到端延迟必须依赖可匹配 seq；没有 seq 只能估计，不能严格匹配。
- 应用层 seq 丢包只对配置了 `canm_seq` 的 ID 生效。
- 当前 ID 统计槽数量固定为 24，超过会增加 `id_overflow`。
- 当前 latency pair 数量固定为 4。
- `Debug` 目录里的 Eclipse makefile 是生成物；新增 C 文件后需要在 RT-Thread Studio 中 refresh/clean build，或重新生成 makefile，确保 `applications/control/can_metrics.c` 被加入构建。

## 9. 一套可复制的记录模板

```text
date:
firmware commit:
bitrate:
nodes:
termination:
test duration:
traffic setup:

canm_show:

canm_ids:

conclusion:
- bus utilization:
- frames/s:
- worst CAN ID period:
- latency P50/P95/P99/max:
- jitter P95/max:
- seq loss:
- TEC/REC/CEL:
- queue overflow:
- next action:
```

