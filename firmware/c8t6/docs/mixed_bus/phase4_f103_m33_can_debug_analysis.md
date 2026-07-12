# F103 与英飞凌 M33 CAN 联调故障分析文档

## 1. 背景与目标

本次联调目标是让 STM32F103 `sensor_collect` 固件通过 CAN 总线接入英飞凌 M33 控制板：

- F103 采集 ADC/EMG 数据。
- F103 周期上报 health 帧 `0x7C3`。
- M33 通过控制帧 `0x7C0` 配置 F103。
- F103 需要回 ACK 帧 `0x7C1`。
- F103 在开启 stream 后上报 sensor 帧 `0x7C2`。

现场最终验证结果：

```text
M33:
CTRL_DBG_F103: ack=4 sensor=19 health=270 ids ctrl=0x7C0 ack=0x7C1 sensor=0x7C2 health=0x7C3

cmd_sensor_show:
ADC4: ch0=2081 ch1=1786 ch2=1864 ch3=1912 sensor_tick=1692373
EMG3: biceps=2081 triceps=1786 ant_deltoid=1864 flags=0x00 seq=35 sensor_tick=1692373
```

这说明 F103 -> M33 health/sensor、M33 -> F103 control、F103 -> M33 ACK 三条链路都已经打通。

## 2. 硬件与端口记录

| 项目 | 现场值 |
| --- | --- |
| F103 工程 | `C:\Users\ASUS\Desktop\STM32demo\SenorsCollect` |
| F103 UART | `COM8` |
| F103 DAPLink | Horco CMSIS-DAP, serial `846703536441` |
| M33 UART | `COM20` |
| M33 KitProg3 | serial `1C161868022E2400` |
| CAN 控制帧 | `0x7C0` |
| F103 ACK | `0x7C1` |
| F103 sensor | `0x7C2` |
| F103 health | `0x7C3` |
| CAN 波特率 | 1 Mbps |

注意：Horco DAPLink 对默认 CMSIS-DAP v2 后端不稳定。稳定烧录方式见第 10 节。

## 3. 现象概述

最初现象不是完全 CAN 不通，而是“单向通”：

- M33 能收到 F103 的 `0x7C3` health。
- M33 发 `f103_ping` 或 `cmd_sensor_rate` 后，`ack=0`。
- F103 串口只打印 health TX，没有打印 `CAN RX match=1`。
- M33 侧 `cmd_sensor_show` 中 `ADC4/EMG3` 一直是 0。

典型失败日志：

```text
M33:
f103_ping sent count=3 delay=100 ret=0

cmd_control_debug:
CTRL_DBG: rx_total=166 hb=1026 ros_id=0 parsed=0 enq=0 applied=0 qfail=0
CTRL_DBG_F103: ack=0 sensor=0 health=166 ids ctrl=0x7C0 ack=0x7C1 sensor=0x7C2 health=0x7C3
CTRL_DBG_LAST: id=0x000007c3 ide=0 len=8 data=01 00 00 00 00 00 14 00

cmd_sensor_show:
ADC4: ch0=0 ch1=0 ch2=0 ch3=0 sensor_tick=0
EMG3: biceps=0 triceps=0 ant_deltoid=0 flags=0x00 seq=0 sensor_tick=0
```

这说明 M33 的接收路径可用，F103 的 health 发送也可用。问题集中在 M33 -> F103 控制帧接收/处理/ACK 这一段。

## 4. 第一层排查：确认不是线和波特率问题

读取 F103 bxCAN 寄存器后发现 FIFO0 中已经有 M33 发来的控制帧：

```text
40006400: 00010000   MCR
40006404: 00000c00   MSR
40006408: 1c000003   TSR
4000640c: 0000001b   RF0R
40006410: 00000000   RF1R
40006414: 00008f02   IER
40006418: 00000000   ESR
4000641c: 00180002   BTR
```

重点是 `RF0R=0x0000001B`：

- `FMP0=3`：FIFO0 里有 3 帧待读。
- `FULL0=1`：FIFO0 满。
- `FOVR0=1`：FIFO0 溢出。

这直接证明：

- M33 发出的 CAN 帧确实到达 F103。
- CAN 物理层、终端电阻、收发器、波特率大方向不是主因。
- 问题在 F103 固件没有及时 drain FIFO0。

进一步读取 FIFO 邮箱内容：

```text
4000640c: 0000001b
400065b0: f8000000
400065b4: 00000008
400065b8: 00002505
400065bc: 00000000
```

解码：

- `RIR=0xF8000000` -> 标准 ID `0x7C0`。
- `RDTR=0x00000008` -> DLC=8。
- `RDLR=0x00002505` -> payload 起始字节为 `05 25 00 00 ...`。

这与 M33 的 `f103_ping` / status 命令帧一致。

## 5. 第二层排查：主循环轮询不足

原始 `app_service_run_once()` 的结构是：

```c
void app_service_run_once(void)
{
    event_t event;
    if (event_queue_pop(&s_app.queue, &event))
    {
        app_handle_event(&event);
    }
    else
    {
        can_transport_poll_rx();
    }
}
```

这个逻辑有风险：如果 1ms tick、ADC、CAN 中断事件持续进入队列，`else` 空闲分支可能长期不执行，CAN RX 轮询就会饿死。

第一步修复是把 CAN RX poll 提到主循环开头：

```c
void app_service_run_once(void)
{
    event_t event;

    can_transport_poll_rx();

    if (event_queue_pop(&s_app.queue, &event))
    {
        app_handle_event(&event);
    }
    else
    {
        can_transport_poll_rx();
    }
}
```

这个改动是正确的防御性设计，但单独并没有解决现场问题。烧录后仍然：

```text
CTRL_DBG_F103: ack=0 sensor=0 health=194
RF0R=0x0000001b
s_rx_count=0
```

说明主循环不是简单“偶尔轮询不到”，而是更严重：主循环根本抢不到 CPU 去执行 poll。

## 6. 第三层排查：绕开 HAL 状态门控

当时怀疑 `HAL_CAN_GetRxFifoFillLevel()` 或 `HAL_CAN_GetRxMessage()` 被 HAL 句柄状态挡住，导致即使 FIFO 有数据，HAL 也不取。

因此将 `can_transport_poll_rx()` 改为直接读 bxCAN FIFO0 寄存器：

```c
while ((can->RF0R & CAN_RF0R_FMP0) > 0U)
{
    rir = can->sFIFOMailBox[CAN_RX_FIFO0].RIR;
    rdtr = can->sFIFOMailBox[CAN_RX_FIFO0].RDTR;
    rdlr = can->sFIFOMailBox[CAN_RX_FIFO0].RDLR;
    rdhr = can->sFIFOMailBox[CAN_RX_FIFO0].RDHR;

    /* 解码 StdId/DLC/data ... */

    SET_BIT(can->RF0R, CAN_RF0R_RFOM0);

    can_rx_dispatch(&message);
}
```

这能避免 HAL 状态机、HAL 头文件版本、句柄状态异常带来的不确定性。

但烧录后仍然没有 ACK。此时读 flash 指令确认，板子里确实已经是 direct FIFO 新代码，并不是烧录旧固件：

```text
08004438: 47f0e92d
0800443c: b08c4f3a
08004440: 280068b8
08004444: 6805d06a
```

因此问题继续下钻。

## 7. 关键定位：PC 停在 RX0 IRQ 入口

使用 pyOCD halt 后读取寄存器：

```text
general registers:
pc: 0x08003864
lr: 0xfffffff9
xpsr: 0x61000024
```

用 `fromelf` 定位 `0x08003864`：

```text
i.USB_LP_CAN1_RX0_IRQHandler
USB_LP_CAN1_RX0_IRQHandler
0x08003864: LDR r0,[pc,#4] ; hcan
0x08003866: B HAL_CAN_IRQHandler
```

这就是根因突破口：

- F103 当前不是停在主循环。
- F103 正在反复进入 `USB_LP_CAN1_RX0_IRQHandler`。
- RX0 中断一直 pending，导致主循环没有机会执行 `can_transport_poll_rx()`。

当时串口也出现：

```text
CAN RX pending q=0 err=0 rx=0 tx=...
CAN RX pending q=0 err=0 rx=0 tx=...
```

这说明中断回调确实在发生，但 `rx_count` 没增长，FIFO 没被释放。

## 8. 根因底层追溯

原始 RX pending 回调逻辑：

```c
void HAL_CAN_RxFifo0MsgPendingCallback(CAN_HandleTypeDef *hcan_cb)
{
    if ((hcan_cb != 0) && (hcan_cb->Instance == CAN1))
    {
        app_push_event_from_isr(EVENT_CAN_RX_PENDING, 0U, 0U);
    }
}
```

问题在于：这个回调只投递事件，不读 FIFO，也不暂时关闭 RX pending 中断。

底层行为链路如下：

1. M33 发送 `0x7C0` 控制帧。
2. F103 bxCAN 硬件把帧放进 FIFO0。
3. FIFO0 非空，触发 `USB_LP_CAN1_RX0_IRQn`。
4. HAL 进入 `HAL_CAN_IRQHandler()`。
5. HAL 调用 `HAL_CAN_RxFifo0MsgPendingCallback()`。
6. 回调只 push 一个事件，立即返回。
7. FIFO0 仍然非空，所以硬件中断条件依然成立。
8. CPU 刚退出中断，又马上再次进入同一个 RX0 中断。
9. 主循环被中断风暴饿死，永远没有机会 drain FIFO。
10. FIFO0 逐渐 full/overrun，M33 永远收不到 ACK。

一句话根因：

> F103 的 CAN RX pending ISR 没有释放 FIFO，也没有屏蔽 pending 中断，导致 FIFO 非空条件持续拉高中断，主循环被 RX 中断风暴饿死。

## 9. 最终修复

### 9.1 中断回调先屏蔽 RX pending

在 `HAL_CAN_RxFifo0MsgPendingCallback()` 中，先关闭 RX FIFO0 pending interrupt，再投递事件：

```c
void HAL_CAN_RxFifo0MsgPendingCallback(CAN_HandleTypeDef *hcan_cb)
{
    if ((hcan_cb != 0) && (hcan_cb->Instance == CAN1))
    {
        __HAL_CAN_DISABLE_IT(hcan_cb, CAN_IT_RX_FIFO0_MSG_PENDING);
        app_push_event_from_isr(EVENT_CAN_RX_PENDING, 0U, 0U);
    }
}
```

这样可以保证 CPU 不会因为 FIFO 未释放而无限重进 RX0 IRQ。

### 9.2 主循环 drain FIFO 后重新打开中断

在 `can_transport_poll_rx()` drain 完 FIFO 后，清理 full/overrun 标志，并重新打开 RX pending interrupt：

```c
if ((can->RF0R & (CAN_RF0R_FULL0 | CAN_RF0R_FOVR0)) != 0U)
{
    SET_BIT(can->RF0R, CAN_RF0R_FULL0 | CAN_RF0R_FOVR0);
}
__HAL_CAN_ENABLE_IT(s_hcan, CAN_IT_RX_FIFO0_MSG_PENDING);
```

### 9.3 保留主循环入口轮询

保留 `app_service_run_once()` 开头的主动 poll：

```c
can_transport_poll_rx();
```

原因：

- 中断丢失时仍可轮询兜底。
- 队列被 tick/ADC 事件占用时仍能优先 drain CAN。
- 对控制命令 ACK 延迟更友好。

## 10. 烧录与调试工具经验

Horco DAPLink 在本机上对默认 CMSIS-DAP v2 后端不稳定。

失败表现：

```text
probe-rs:
Failed to open probe
Could not determine a suitable packet size for this probe
Error handling CMSIS-DAP command Info

pyOCD default:
Timeout reading from probe 846703536441

OpenOCD default:
CMSIS-DAP command CMD_INFO failed
```

可用方式 1：OpenOCD 强制 HID 后端。

```powershell
& "F:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\bin\openocd.exe" `
  -s "F:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\scripts" `
  -f interface\cmsis-dap.cfg `
  -c "cmsis-dap backend hid" `
  -c "adapter serial 846703536441" `
  -f target\stm32f1x.cfg `
  -c "adapter speed 100; init; reset halt; mdw 0xE0042000 1; reset run; shutdown"
```

可用方式 2：pyOCD 强制 HID + CMSIS-DAP v1。

```powershell
$env:PYOCD_USB_BACKEND='hidapiusb'
python -m pyocd load --no-config `
  -u 846703536441 `
  -t stm32f103rc `
  -f 100k `
  -O cmsis_dap.prefer_v1=true `
  -e chip `
  --format hex `
  "C:\Users\ASUS\Desktop\STM32demo\SenorsCollect\MDK-ARM\SenorsCollect\SenorsCollect.hex"
```

现场成功烧录日志：

```text
Loading ... SenorsCollect.hex
Erasing...
Programming...
Erased chip, programmed 22528 bytes (11 pages), skipped 0 bytes (0 pages)
```

注意：如果 `probe-rs`、`UV4.exe`、`openocd.exe` 残留进程占着 DAPLink，需要先关闭。否则会出现“探针能枚举但无法连接目标”的假故障。

## 11. 最终验证日志

F103 串口：

```text
CAN RX match=1 id=7C0 dlc=8 data=05 2A 00 00 00 00 00 00
CAN TX rc=0 id=7C1 dlc=8 data=05 2A 00 01 00 00 00 00

CAN RX match=1 id=7C0 dlc=8 data=05 2B 00 00 00 00 00 00
CAN CMD cmd=05 seq=43 status=0 dup=0 ack_rc=0 q=1 err=0 rx=2 tx=18
CAN TX rc=0 id=7C1 dlc=8 data=05 2B 00 01 00 00 00 00

CAN RX match=1 id=7C0 dlc=8 data=01 2C 02 14 00 00 00 00
CAN CMD cmd=01 seq=44 status=0 dup=0 ack_rc=0 q=1 err=0 rx=3 tx=21

CAN RX match=1 id=7C0 dlc=8 data=03 2D 00 00 00 00 00 00
CAN CMD cmd=03 seq=45 status=0 dup=0 ack_rc=0 q=2 err=0 rx=4 tx=21

CAN TX rc=0 id=7C2 dlc=8 data=41 08 04 07 54 07 7C 07
```

M33 串口：

```text
cmd_control_debug
CTRL_DBG_F103: ack=2 sensor=0 health=268 ids ctrl=0x7C0 ack=0x7C1 sensor=0x7C2 health=0x7C3

cmd_sensor_rate 2 50
sensor_rate ret=0

cmd_control_debug
CTRL_DBG_F103: ack=4 sensor=19 health=270 ids ctrl=0x7C0 ack=0x7C1 sensor=0x7C2 health=0x7C3

cmd_sensor_show
ADC4: ch0=2081 ch1=1786 ch2=1864 ch3=1912 sensor_tick=1692373
EMG3: biceps=2081 triceps=1786 ant_deltoid=1864 flags=0x00 seq=35 sensor_tick=1692373
```

## 12. 可复用调试方法

以后遇到类似“CAN 看起来一半通”的问题，按这个顺序排：

### 12.1 先分方向，不要直接怀疑全部链路

检查：

- A -> B 有没有包。
- B -> A 有没有包。
- 是否只有 health 通、控制不通。
- 是否 ACK 不通但 TX 还在。

本次就是：

- F103 -> M33 health 通。
- M33 -> F103 control 到了 FIFO。
- F103 没 drain FIFO，所以不 ACK。

### 12.2 读 CAN 控制器寄存器，比看上层日志更可靠

F103 bxCAN 关键寄存器：

```text
0x40006400 MCR
0x40006404 MSR
0x40006408 TSR
0x4000640C RF0R
0x40006410 RF1R
0x40006414 IER
0x40006418 ESR
0x4000641C BTR
```

重点看：

- `RF0R.FMP0`：FIFO0 里有几帧。
- `RF0R.FULL0`：FIFO0 是否满。
- `RF0R.FOVR0`：FIFO0 是否溢出。
- `ESR`：是否 bus-off/error-passive。
- `TSR`：TX 邮箱是否完成。

判断口诀：

```text
M33 说已发送 + F103 RF0R.FMP0 > 0:
    线和波特率基本不是主因，转查 F103 RX drain。

F103 RF0R.FMP0 = 0 + M33 收不到 ACK:
    查 F103 是否解析丢弃、ACK 是否入队、TX 邮箱是否发出。

F103 ESR bus-off/error-passive:
    查波特率、终端电阻、CANH/CANL、收发器供电、共地。
```

### 12.3 如果 FIFO 非空但 rx_count 不涨，立刻抓 PC

本次最关键证据是：

```text
pc: 0x08003864
```

反汇编定位：

```text
USB_LP_CAN1_RX0_IRQHandler -> HAL_CAN_IRQHandler
```

这说明 CPU 被 RX 中断风暴困住，不是业务代码解析错。

经验：

- 只看串口可能会误判为“主循环在跑”。
- health 能发不代表主循环完全健康，因为 health 可能在偶尔间隙或旧状态下还能发。
- PC/halt 证据可以把“猜测”变成“定位”。

### 12.4 ISR 中不要只投递事件却不处理持续电平型 pending

CAN RX pending 属于“只要 FIFO 非空就会继续 pending”的中断条件。

错误模式：

```c
ISR:
    push_event();
    return;
```

如果主循环负责清 FIFO，ISR 必须先 mask 对应中断：

```c
ISR:
    disable_rx_pending_irq();
    push_event();
```

主循环处理完后再 unmask：

```c
main_loop:
    drain_fifo();
    clear_full_overrun();
    enable_rx_pending_irq();
```

否则 FIFO 不空 -> IRQ 重入 -> 主循环无法 drain -> FIFO 更不空，这是典型死循环。

### 12.5 对控制通道优先级要高于普通数据采样

EMG/ADC 采样可以丢一两个周期，但控制命令 ACK 不应被长时间阻塞。

建议主循环优先级：

1. CAN RX drain。
2. 安全/故障处理。
3. 控制命令处理。
4. 传感器采样/滤波。
5. 普通 debug UART。

debug UART 不应在高频路径无限打印，否则会制造新的实时性问题。

## 13. 本次代码改动对应测试

新增 host 回归测试：

```text
tests/host/test_app_service_can_poll_order.py
tests/host/test_can_transport_direct_rx.py
tests/host/test_can_rx_irq_masking.py
```

覆盖点：

- `app_service_run_once()` 必须先 poll CAN，再处理普通事件。
- `can_transport_poll_rx()` 必须 direct drain FIFO，不能只依赖 HAL state gate。
- RX pending ISR 必须 mask 中断，poll 完必须 unmask。

运行方式：

```powershell
python tests\host\test_app_service_can_poll_order.py
python tests\host\test_can_transport_direct_rx.py
python tests\host\test_can_rx_irq_masking.py
```

现场三项均通过。

## 14. 后续建议

1. 减少 F103 串口 debug 打印频率，避免串口阻塞影响实时性。
2. 给 `event_queue_push_from_isr()` 的失败次数加计数，方便看队列是否被 tick/ADC 淹没。
3. health payload 中保留 `rx_count/tx_count/q_fill/error_count`，本次非常有用。
4. 给 M33 增加一个 `f103_diag` 命令，集中显示 ack/sensor/health/last frame/stale 状态。
5. 若后续加高频 EMG 数据，CAN sensor 帧要固定发送周期，控制 ACK 始终高优先级。

## 15. 一句话复盘

本次故障不是 CAN 线不通，而是 F103 的 CAN RX pending 中断设计不完整：ISR 只投递事件，不释放 FIFO、不屏蔽 pending 中断，导致 RX 中断风暴饿死主循环。最终通过“ISR 先 mask，中断外 drain FIFO，drain 后 unmask”的模式修复。
