# CAN 其它电机测量报告（忽略 3 号电机）

测量日期：2026-07-05  
被测板卡：Infineon PSOC Edge E84 / RT-Thread M33  
串口：KitProg3 USB-UART COM20，115200 baud  
CAN 配置：Classic CAN，1 Mbps  
测量范围：只测 1/2/4/5/6/7 号电机相关通信，3 号 CANSimple 电机不参与本报告  
安全边界：只使用 `cmd_motor_probe` 和 `cmd_motor_report`，没有发送 enable、position、speed、torque、zero 等运动命令。

## 1. 结论

本次接入的其它电机里，4/5/6 号电机在线并能稳定主动上报；1/2/7 号没有探测响应，也没有有效反馈缓存。

CAN 总线在 4/5/6 号电机主动上报约 100 Hz 的情况下仍然健康：总线利用率约 `5.7%`，总帧率约 `381.19 frames/s`，`TEC=0`、`REC=0`、`CEL=0`，无 error passive、warning、bus off，无 RX FIFO full/lost，无 TX timeout/send fail。

4/5/6 号电机主动上报周期非常稳定，周期约 `10 ms`，对应约 `94~95 fps`。3 号电机已按要求排除。

## 2. 电机在线探测

使用 `cmd_motor_probe <motor_id>` 做只读探测：

| 电机 | 探测结果 |
|---:|---|
| 1 | 无响应 |
| 2 | 无响应 |
| 4 | 有响应，UID `0x0137340c023029b3` |
| 5 | 有响应，UID `0x0137340c0230719f` |
| 6 | 有响应，UID `0x06b6311821301b68` |
| 7 | 无响应 |

`cmd_m33_prearm_check` 结果显示 `fresh_mask=0x00000038`、`fresh_count=3`，与 4/5/6 号电机有 fresh feedback 一致。系统整体仍 `ready=0`，原因包括急停/限位/代码限幅确认未完成，以及 required motor feedback 没有全部满足；本报告不代表可以运动。

## 3. 30 秒主动上报测量

正式测量命令窗口：

```text
cmd_control_init can0
cmd_motor_report 1 0
cmd_motor_report 2 0
cmd_motor_report 4 0
cmd_motor_report 5 0
cmd_motor_report 6 0
cmd_motor_report 7 0
canm_reset 1000000
canm_expect 0x7C2 20 std
canm_expect 0x7C3 1000 std
canm_expect 0x321 1000 std
canm_expect 0x180004FD 10 ext
canm_expect 0x180005FD 10 ext
canm_expect 0x180006FD 10 ext
cmd_motor_report 1 1
cmd_motor_report 2 1
cmd_motor_report 4 1
cmd_motor_report 5 1
cmd_motor_report 6 1
cmd_motor_report 7 1
wait 30s
canm_show
canm_ids
```

总线汇总：

```text
elapsed_ms=33104
rx=11005
tx=1614
frames_s=381.19
payload_Bps=3042
util_permille=57
tx_fail=0
id_overflow=0
```

错误与队列：

```text
TEC=0 REC=0 CEL=0 CEL_delta=0
LEC=0 DLEC=7 EP=0 EW=0 BO=0
rxf0_fill=0 rxf0_full=0 rxf0_lost=0
rx_lost_count=0 rx_full_count=0 rx_extract_fail=0 rx_drain_limit=0
tx_timeout=0 tx_send_fail=0 tx_pending_suppressed=0
```

## 4. 每个 CAN ID 指标

| CAN ID | 方向 | 对象 | 帧数 | fps | 周期 P50/P95/P99/max | 周期偏差 |
|---|---:|---|---:|---:|---|---|
| `0x180004FD` ext | RX | 4 号电机 active report | 3237 | 94.96 | 10/10/11/11 ms | P95 0 ms，max 1 ms |
| `0x180005FD` ext | RX | 5 号电机 active report | 3208 | 94.11 | 10/10/11/11 ms | P95 0 ms，max 1 ms |
| `0x180006FD` ext | RX | 6 号电机 active report | 3179 | 93.26 | 10/10/11/11 ms | P95 0 ms，max 1 ms |
| `0x7C2` std | RX | F103 传感器流 | 1719 | 50.43 | 20/20/20/20 ms | P95 0 ms，max 0 ms |
| `0x7C3` std | RX | F103 health | 34 | 0.99 | 1001/1004/1006/1006 ms | P95 4 ms，max 6 ms |
| `0x321` std | RX | NanoPi heartbeat | 35 | 1.02 | 1001/1006/1014/1014 ms | P95 6 ms，max 14 ms |
| `0x330~0x334` std | TX | M33 motor telemetry slots | 各约 325 | 各约 9.53 | N/A | N/A |

说明：当前 `canm_ids` 对 active-report 的 `jitter_p95/max` 字段打印为 `10/10 ms`，但同一窗口的周期分位数为 `10/10/11/11 ms`。这里报告采用“周期相对 10 ms 期望值的偏差”作为 jitter/周期偏差，即 P95 0 ms、max 1 ms。

## 5. 最新电机反馈缓存

```text
MOTOR[1]: id=0 tick=0  -> 无有效反馈
MOTOR[2]: id=0 tick=0  -> 无有效反馈
MOTOR[4]: id=4 mode=0 fault=0x00 pos=1434 mrad vel=35 mrad/s torque=0 mNm temp=30.0 C
MOTOR[5]: id=5 mode=0 fault=0x00 pos=5840 mrad vel=37 mrad/s torque=0 mNm temp=31.0 C
MOTOR[6]: id=6 mode=0 fault=0x00 pos=4576 mrad vel=-1 mrad/s torque=0 mNm temp=30.0 C
MOTOR[7]: id=0 tick=0  -> 无有效反馈
```

## 6. 指标逐项回答

| 指标 | 本次结果 |
|---|---|
| 总线利用率 | `5.7%` |
| frames/s | `381.19 frames/s` |
| 每个 CAN ID 周期偏差 | 4/5/6 号电机 active report 周期 P99/max 约 `11/11 ms`，相对 10 ms 期望 max 偏差约 `1 ms` |
| 端到端延迟 P50/P95/P99/max | 本次只开主动上报，没有 request/response seq，不能严格计算 E2E 延迟 |
| jitter P95/max | 4/5/6 号按周期偏差计算约 `0/1 ms` |
| 应用层 seq 丢包率 | 私有电机 active-report payload 没有 seq 字段，本次不可测 |
| error frame 数量和 TEC/REC | `CEL=0`，`TEC=0`，`REC=0` |
| TX/RX 队列 overflow | `rxf0_full=0`，`rxf0_lost=0`，`rx_drain_limit=0`，`tx_timeout=0`，`tx_send_fail=0`，`id_overflow=0` |

## 7. 建议

1. 4/5/6 号电机的 CAN 通信质量是健康的，可以作为后续电机侧通信基线。
2. 1/2/7 号当前没有响应；优先检查供电、CANH/CANL、终端电阻、实际 motor_id、协议类型和波特率。
3. 严格端到端延迟需要 request/response 可匹配字段。若电机协议没有 seq，可以后续在 M33 侧加“命令发出时间到下一帧该电机反馈”的近似测量。
4. 若后续同时接入更多电机或更高频上报，应重点观察 `util_permille`、`id_overflow`、`rxf0_full/lost`、`rx_drain_limit` 和 `tx_timeout`。
