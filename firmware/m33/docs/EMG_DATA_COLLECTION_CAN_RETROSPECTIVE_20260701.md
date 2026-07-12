# EMG 数据采集与 F103-M33 CAN 联调复盘表

日期：2026-07-01  
项目：肌电传感器辅助推理动作意图，结合电机状态生成康复助力控制建议  
涉及仓库：

- M33/英飞凌工程：`F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED`
- F103 传感器工程：`C:\Users\ASUS\Desktop\STM32demo\SenorsCollect`

## 1. 面试版项目概述

这个项目的目标是构建一个康复机械臂的数据采集和推理闭环。STM32F103 作为传感节点采集三路肌电模拟量，通过 CAN 总线上报给英飞凌 M33 控制板；M33 同时持有关节位置、速度、力矩估计、温度、策略输出电流命令等电机状态；PC 端 Python 脚本通过 M33 串口导出 CSV，后续用于 TensorFlow 训练动作意图模型。

第一版动作意图标签：

| 键盘输入 | CSV 标签 | 中文动作 | 训练意义 |
| --- | --- | --- | --- |
| `1` | `rest` | 静止/放松 | 负样本和基线 |
| `2` | `elbow_flex` | 抬小臂/屈肘 | 肱二头主导 |
| `3` | `elbow_extend` | 放下小臂/伸肘 | 肱三头主导，或屈肘后的反向动作 |
| `4` | `shoulder_flex` | 抬大臂/肩前屈 | 三角肌前束主导 |

传感器贴片与通道约定：

| CSV 字段 | F103 ADC | STM32 引脚 | 肌肉 |
| --- | --- | --- | --- |
| `emg_biceps` / `adc0` | `ADC1_IN0` | `PA0` | 肱二头 |
| `emg_triceps` / `adc1` | `ADC1_IN1` | `PA1` | 肱三头外侧头 |
| `emg_ant_deltoid` / `adc2` | `ADC1_IN2` | `PA2` | 三角肌前束 |
| `adc3` | `ADC1_IN3` | `PA3` | 保留调试，不进第一版模型 |

一句话面试表述：

> 我负责把外部 STM32F103 传感节点、英飞凌 M33 控制板和 PC 端训练数据采集打通。过程中定位过 CAN 单向通信、F103 RX 中断风暴、M33 固件版本错误、串口进程占用、采集脚本标签和窗口化、以及 ADC 贴片/供电导致的饱和和 0V 等问题，最后形成可复用的数据采集脚本和调试方法。

## 2. 系统数据链路

```mermaid
flowchart LR
    A["三路 EMG 模拟输出"] --> B["STM32F103 ADC1 DMA<br/>PA0/PA1/PA2/PA3"]
    B --> C["F103 data_fusion<br/>四路 ADC 快照"]
    C --> D["F103 CAN 0x7C2<br/>adc0..adc3 小端打包"]
    D --> E["英飞凌 M33 CAN 接收"]
    E --> F["M33 sensor.c 缓存<br/>EMG3 + ADC4 + ACK/health"]
    F --> G["M33 control_layer.c<br/>EMG3MOTOR 串口输出"]
    G --> H["KitProg3 USB-UART COM20"]
    H --> I["tools/collect_f103_sensor_data.py"]
    I --> J["raw.csv / windows.csv / trials.csv"]
    J --> K["TensorFlow 训练"]
```

CAN ID 约定：

| CAN ID | 方向 | 含义 |
| --- | --- | --- |
| `0x7C0` | M33 -> F103 | 控制命令，如设置频率、开始/停止上传 |
| `0x7C1` | F103 -> M33 | ACK，应答控制命令 |
| `0x7C2` | F103 -> M33 | 传感器数据，当前为四路 ADC raw |
| `0x7C3` | F103 -> M33 | health，包含状态、错误计数、队列深度、rx/tx 计数 |

电机数据边界：

- 当前不声称采集电机实际电流。
- 采集字段是 M33 策略侧可见状态：`pos_mrad`、`vel_mrad_s`、`torque_mNm`、`temp_c`、`output_current_cmd_a`、`limit_current_a`、`fresh/fault/saturated/stale`。
- `output_current_cmd_a` 是策略输出/下发电流命令，不是 measured current。

## 3. 总复盘表

| 阶段 | 现象 | 关键日志/证据 | 根因定位 | 处理/修复 | 面试可讲点 |
| --- | --- | --- | --- | --- | --- |
| 需求定义 | 不清楚要采什么数据、窗口多长、标签是什么 | 最初只有 EMG，后续发现还要电机状态 | 模型输入和控制输出边界没有定义清楚 | 明确四类标签、3 路 EMG、2 个关节状态、300 ms 窗口、100 ms 步长 | 我先把数据闭环拆成模型输入、监督标签、控制建议和安全执行 |
| 传感器数量 | 只有三路 EMG，原来想四路 | `adc3` 有值但第四路不贴 | 三个肌肉足够覆盖屈肘、伸肘、抬肩，第四路保留调试 | 模型只用 `emg_biceps/triceps/ant_deltoid`，`adc3` 不进训练 | 降低第一版复杂度，避免无效通道污染模型 |
| 电机电流 | 误以为能采实际电流 | 源码里没有 `measured_current` 字段 | 当前协议只有策略输出电流命令/电流上限 | 字段命名为 `output_current_cmd_a`，不叫 measured | 保持工程严谨，不把命令值说成传感反馈 |
| Python 采集 | `saved rows=0` | 手动采集一段后 CSV 无行 | 脚本没有收到可解析的 `EMG3MOTOR,...` 串口行 | 先排串口/M33 固件，不直接怀疑贴片 | 我用分层定位避免在错误层反复调 |
| 串口占用 | COM20 打不开 | `PermissionError(13, 拒绝访问)` | 旧采集脚本或串口工具占用 KitProg3 UART | 找到进程并停止，重新打开 COM20 | 串口类问题先查进程占用和端口归属 |
| 固件命令缺失 | `emg_motor_stream: command not found` | `help` 里没有命令 | 板上烧录的是旧固件，不是包含新 shell 命令的 build 产物 | 重新编译并烧录正确 `build\rtthread.hex` | 固件版本和烧录产物必须闭环验证 |
| M33 命令崩溃 | 直接执行 `emg_motor_stream 1 20` 触发 mutex assertion | `_rt_mutex_take` assertion | `emg_motor_stream` 在 control layer 未初始化前访问 mutex/缓存 | 在命令入口自动调用 `control_layer_init()`，失败则报错退出 | 任何 shell 调试命令都要处理初始化前置条件 |
| F103-M33 CAN | M33 能收到 health，但 ACK/sensor 为 0 | `CTRL_DBG_F103: ack=0 sensor=0 health=166` | F103 发得出 health，但 M33->F103 控制帧没有被 F103 主循环处理 | 继续查 F103 FIFO 和中断 | 这是典型单向通信，不等于物理 CAN 不通 |
| F103 FIFO | F103 bxCAN FIFO0 满/溢出 | `RF0R=0x0000001B`，`FMP0=3/FULL0/FOVR0` | 控制帧已经到 F103，但 FIFO 没 drain | 绕开上层日志，读硬件寄存器定位 | 底层寄存器比业务日志更接近真相 |
| F103 RX 中断风暴 | halt 后 PC 在 `USB_LP_CAN1_RX0_IRQHandler` | `pc: 0x08003864`，反汇编到 CAN RX0 IRQ | ISR 只投递事件，不释放 FIFO，也不屏蔽 pending 中断，导致反复进中断，主循环饥饿 | ISR 先 disable RX pending，主循环 drain FIFO 后 enable | 我定位到不是协议错，而是中断模型设计缺陷 |
| F103 修复验证 | ACK/sensor 恢复 | `CAN RX match=1 id=7C0`，`CAN TX rc=0 id=7C1`，`CAN TX rc=0 id=7C2` | 修复有效 | 增加 host 回归测试覆盖 poll 顺序、direct FIFO、IRQ mask/unmask | 硬件 bug 也能沉淀成自动化回归 |
| M33 收数验证 | M33 看到 ADC/EMG | `ADC4: ch0=2081 ch1=1786 ch2=1864 ch3=1912` | F103->M33 sensor 链路打通 | `cmd_sensor_show` 成为现场确认入口 | 现场命令要能显示链路分段状态 |
| 采集全 0 | CSV 有行，但 EMG 全 0 | `EMG3MOTOR,...,0,0,0...` | 只开启了 M33 串口输出，没有让 F103 开始上报 `0x7C2` | 启动命令改成 `cmd_control_init; cmd_sensor_rate 2 50; emg_motor_stream 1 20` | 数据有行不等于传感器链路有数据 |
| 脚本命令 | 多条启动命令被当成一行 | 旧 `_serial_command_bytes` 只加一个 CRLF | RT-Thread shell 不一定支持分号作为一条命令内部解析 | 脚本把分号/换行拆成多条 CRLF 命令 | 把现场操作坑固化到工具里 |
| 标签输入 | 手敲英文容易拼错 | 出现 `reset`、`eblow_flex` | 人工输入标签不稳定 | 手动模式支持 `1/2/3/4` 快捷键映射标准标签 | 训练数据质量从采集入口保证 |
| trial 区分 | 担心多动作混在一个 CSV 影响训练 | `trial_index`、`trial_id`、`label_trial_index` | CSV 文件名不是标签，标签在列里；同一脚本可采多段 | `raw/windows/trials` 都保存标签和 trial 信息 | 数据集设计要支持多 session、多 trial |
| ADC 饱和 | `adc0=4095` | 4095 对应 12 位 ADC 满量程 3.3V | PA0 实际电压接近 3.3V，可能接到 VCC、输出饱和、板载上拉或供电/地问题 | 用万用表量 A0-GND，交换传感器 OUT，确认 3.3V 来源 | ADC raw 可换算电压，软件值能指导硬件排查 |
| ADC 贴地 | `adc1=0`、`adc2=0..5` | 最新 CSV：A1 0V，A2 约 0..0.004V | 不是脚本/CAN 问题，是 A1/A2 模拟输入线物理接近 GND | 查共地、电池、OUT/GND/VCC 接线，做通道交换实验 | 当 A0 已正常时，问题可收敛到单通道硬件链路 |
| 训练导入 | 担心 CSV 文件名都是时间、多个动作混在一起 | `label` 列和 `trial_id` 列存在 | TensorFlow 读取的是列，不依赖文件名表达标签 | 用 `windows.csv` 做特征输入，用 `label` 编码分类 | 文件是 session 容器，标签是监督信号 |

## 4. F103 侧源码解释

### 4.1 ADC 采样配置

源码：`C:\Users\ASUS\Desktop\STM32demo\SenorsCollect\Core\Src\adc.c`

关键点：

- `hadc1.Init.ScanConvMode = ADC_SCAN_ENABLE`
- `hadc1.Init.NbrOfConversion = 4`
- Rank 1 到 Rank 4 分别是 `ADC_CHANNEL_0/1/2/3`
- GPIO 配置为模拟输入：`PA0-WKUP`、`PA1`、`PA2`、`PA3`

对应关系：

```text
PA0 -> ADC1_IN0 -> adc0 -> emg_biceps
PA1 -> ADC1_IN1 -> adc1 -> emg_triceps
PA2 -> ADC1_IN2 -> adc2 -> emg_ant_deltoid
PA3 -> ADC1_IN3 -> adc3 -> debug/unused
```

ADC 是 12 位，所以：

```text
电压约等于 raw * 3.3 / 4095
raw=4095 约等于 3.3V
raw=0 约等于 0V
```

这解释了为什么 `adc0=4095` 不是“肌电强”，而是输入已经顶到满量程；`adc1=0` 也不是“肌电弱”，而是该线几乎在 GND。

### 4.2 ADC DMA 到数据融合

源码：

- `C:\Users\ASUS\Desktop\STM32demo\SenorsCollect\BSP\bsp_MuElec.c`
- `C:\Users\ASUS\Desktop\STM32demo\SenorsCollect\app\src\sensor_factory.c`
- `C:\Users\ASUS\Desktop\STM32demo\SenorsCollect\app\src\app_service.c`

链路：

1. `bsp_muelec_start_dma()` 调用 `HAL_ADC_Start_DMA()`，把四路 ADC 放进 DMA buffer。
2. ADC DMA 完成后进入 `HAL_ADC_ConvCpltCallback()`。
3. 回调里投递 `EVENT_EMG_SAMPLE_READY`。
4. `app_handle_event(EVENT_EMG_SAMPLE_READY)` 调用 `sensor_factory_read_emg_channels()` 读取四路样本。
5. `data_fusion_update_adc4()` 保存四路 raw。
6. 周期发送时 `app_send_telemetry()` 调用 `can_proto_encode_sensor()`。

关键源码逻辑：

```c
case EVENT_EMG_SAMPLE_READY:
    if ((s_app.emg_sensor != 0) && (sensor_factory_read_emg_channels(adc_samples) == 0))
    {
        data_fusion_update_adc4(&s_app.fusion, s_app.ms_now, adc_samples);
        s_app.state = NODE_STATE_RUN;
    }
```

### 4.3 F103 0x7C2 打包

源码：`C:\Users\ASUS\Desktop\STM32demo\SenorsCollect\app\src\can_proto.c`

当前 `0x7C2` payload 是四路 `uint16_t` 小端：

```text
data[0..1] = adc0
data[2..3] = adc1
data[4..5] = adc2
data[6..7] = adc3
```

源码核心：

```c
message->id = F103_CAN_ID_SENSOR_TX;  // 0x7C2
message->dlc = 8U;
for (i = 0U; i < FUSION_ADC_CHANNEL_COUNT; ++i)
{
    const uint16_t sample = snapshot->adc_raw[i];
    message->data[i * 2U] = (uint8_t)(sample & 0xFFU);
    message->data[(i * 2U) + 1U] = (uint8_t)((sample >> 8) & 0xFFU);
}
```

### 4.4 F103 CAN RX 中断风暴根因

失败时，M33 能收到 F103 health，但 F103 不 ACK 控制命令：

```text
CTRL_DBG_F103: ack=0 sensor=0 health=166
```

F103 bxCAN 寄存器显示 FIFO0 已有帧且溢出：

```text
RF0R=0x0000001B
FMP0=3, FULL0=1, FOVR0=1
```

进一步 halt 后 PC 停在：

```text
pc: 0x08003864
USB_LP_CAN1_RX0_IRQHandler -> HAL_CAN_IRQHandler
```

根因：

- CAN RX pending 是电平型条件，只要 FIFO 非空就会继续 pending。
- 原 ISR 只投递 `EVENT_CAN_RX_PENDING`，没有释放 FIFO，也没有临时关闭 RX pending 中断。
- CPU 退出中断后马上再次进入 CAN RX0 IRQ，主循环没有机会执行 `can_transport_poll_rx()`。
- FIFO 最终 full/overrun，M33 永远收不到 ACK。

修复模式：

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

然后主循环 drain FIFO 后重新打开中断：

```c
while ((can->RF0R & CAN_RF0R_FMP0) > 0U)
{
    // 直接读 bxCAN FIFO mailbox
    SET_BIT(can->RF0R, CAN_RF0R_RFOM0);
    can_rx_dispatch(&message);
}

SET_BIT(can->RF0R, CAN_RF0R_FULL0 | CAN_RF0R_FOVR0);
__HAL_CAN_ENABLE_IT(s_hcan, CAN_IT_RX_FIFO0_MSG_PENDING);
```

同时 `app_service_run_once()` 开头优先 poll CAN：

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

复盘经验：

> 对于 FIFO 非空触发的 pending 中断，如果 ISR 不直接清除触发条件，就必须先 mask 中断，把 drain 操作交给主循环，drain 完再 unmask。否则会出现中断风暴，业务主循环被饿死。

## 5. 英飞凌 M33 侧源码解释

### 5.1 F103 传感帧解析

源码：`F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED\applications\control\sensor.c`

函数：`control_sensor_update_f103_sensor_report()`

核心逻辑：

```c
adc0 = sensor_u16_from_le(&msg->data[0]);
adc1 = sensor_u16_from_le(&msg->data[2]);
adc2 = sensor_u16_from_le(&msg->data[4]);
adc3 = sensor_u16_from_le(&msg->data[6]);

node.adc_raw[0] = adc0;
node.adc_raw[1] = adc1;
node.adc_raw[2] = adc2;
node.adc_raw[3] = adc3;
node.emg3_raw[0] = node.adc_raw[0];
node.emg3_raw[1] = node.adc_raw[1];
node.emg3_raw[2] = node.adc_raw[2];
node.emg3_seq = s_f103_sensor_seq++;
```

这说明 M33 不在这里滤波或重算 EMG，只是把 F103 的四路 ADC raw 缓存起来，并把前三路映射成三路 EMG。

### 5.2 M33 向 F103 开启上报

源码：`applications\control\sensor.c`

函数：`control_sensor_report_enable(enable, period_ms)`

它做两件事：

1. 发 `SET_RATE` 到 `0x7C0`，设置 F103 CAN 上传频率。
2. 发 `START_STREAM` 或 `STOP_STREAM` 到 `0x7C0`。

现场命令：

```text
cmd_sensor_rate 2 50
```

其中 `2` 是历史/兼容目标语义里的 CAN TX 目标，`50` 是 50 Hz。

### 5.3 M33 现场观察命令

命令：

```text
cmd_sensor_show
```

关键输出：

```text
ADC4: ch0=2081 ch1=1786 ch2=1864 ch3=1912 sensor_tick=1692373
EMG3: biceps=2081 triceps=1786 ant_deltoid=1864 flags=0x00 seq=35 sensor_tick=1692373
F103_HEALTH: state=... err=... q=... last_ack ...
```

判断方法：

- `health_tick` 更新但 `sensor_tick=0`：F103 health 到了，但 sensor 没到。
- `last_ack` 不更新：M33->F103 控制或 F103 ACK 链路有问题。
- `EMG3 seq` 增加且 `sensor_tick` 更新：F103 0x7C2 已进入 M33。
- `ADC4` 值异常：转去查 F103 ADC/传感器接线。

### 5.4 M33 串口输出格式

源码：`applications\control\control_layer.c`

输出行：

```text
EMG3MOTOR,<m33_ms>,<adc0>,<adc1>,<adc2>,<adc3>,<flags>,<seq>,
<shoulder_pos>,<shoulder_vel>,<shoulder_torque>,<shoulder_temp>,<shoulder_output_current_cmd>,<shoulder_limit_current>,<shoulder_flags>,
<elbow_pos>,<elbow_vel>,<elbow_torque>,<elbow_temp>,<elbow_output_current_cmd>,<elbow_limit_current>,<elbow_flags>
```

注意：

- 电机 `temp=255` 或 `stale=True` 表示当前没有新鲜电机反馈。
- 这不影响 EMG 采集，但训练助力大小时要过滤 stale 电机状态。

## 6. PC 采集脚本复盘

脚本：`F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED\tools\collect_f103_sensor_data.py`

### 6.1 输出文件

每次 session 输出三个 CSV：

| 文件 | 用途 |
| --- | --- |
| `<session>_raw.csv` | 原始逐帧数据，50 Hz 左右，保留 EMG、电机、label、trial |
| `<session>_windows.csv` | 训练更常用的窗口特征，默认 300 ms 窗口、100 ms 步长 |
| `<session>_trials.csv` | 每段动作的 trial 元数据，如 label、时长、样本数 |

训练时不是靠文件名识别动作，而是靠 CSV 里的 `label` 列。文件名只是 session 容器。

### 6.2 串口解析

函数：`parse_emg3_motor_serial_line()`

它只解析以 `EMG3MOTOR,` 开头的行，其他 shell 输出会忽略：

```python
if not line.startswith("EMG3MOTOR,"):
    return None
```

核心字段映射：

```python
adc0 = int(parts[2], 0)
adc1 = int(parts[3], 0)
adc2 = int(parts[4], 0)

row = {
    "adc0": adc0,
    "adc1": adc1,
    "adc2": adc2,
    "adc3": adc3,
    "emg_biceps": adc0,
    "emg_triceps": adc1,
    "emg_ant_deltoid": adc2,
}
```

### 6.3 手动模式

当前推荐命令：

```powershell
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED
python tools\collect_f103_sensor_data.py --source serial --protocol emg3-motor --manual --subject-id S01 --session-id S01_dayX --serial-port COM20 --serial-start-command "cmd_control_init; cmd_sensor_rate 2 50; emg_motor_stream 1 20" --serial-stop-command "emg_motor_stream 0"
```

操作方式：

```text
label> 1
[trial 1] label=rest recording... press Enter to stop

label> 2
[trial 2] label=elbow_flex recording... press Enter to stop

label> 3
[trial 3] label=elbow_extend recording... press Enter to stop

label> 4
[trial 4] label=shoulder_flex recording... press Enter to stop

label> q
```

快捷键映射在脚本里：

```python
MANUAL_LABEL_SHORTCUTS = {
    "1": "rest",
    "2": "elbow_flex",
    "3": "elbow_extend",
    "4": "shoulder_flex",
}
```

### 6.4 多条启动命令问题

旧问题：

```powershell
--serial-start-command "cmd_control_init; cmd_sensor_rate 2 50; emg_motor_stream 1 20"
```

旧脚本会当成一整行发给 RT-Thread shell。如果 shell 不解析分号，实际只有 M33 串口输出被打开，F103 没有开始 `0x7C2` 上报，CSV 就会有行但 EMG 全 0。

修复：

```python
def _serial_command_bytes(command: str) -> bytes:
    commands = [item.strip() for item in re.split(r"[;\r\n]+", command) if item.strip()]
    if not commands:
        return b""
    return "".join(f"{item}\r\n" for item in commands).encode("utf-8")
```

现在分号和换行都会拆成多条 shell 命令。

### 6.5 guided 与 manual 的区别

| 模式 | 适用场景 | 优点 | 缺点 |
| --- | --- | --- | --- |
| guided | 标准化批量采集 | 自动按标签和 trial 计划走，样本更均衡 | 抬小臂/放下这类快动作会觉得 8 秒太长 |
| manual | 现场试验和自然动作 | 你自己按键开始/停止，每次动作长度可控 | 需要自觉保持每个 label 的 trial 数均衡 |

这次最终选择 manual，因为小臂抬起/放下动作很快，人工控制更符合真实动作节奏。

## 7. 数据质量复盘

### 7.1 当前有效数据与坏数据

出现过几类坏数据：

| 文件/现象 | 问题 | 是否可训练 |
| --- | --- | --- |
| `S01_day1_raw.csv` | 旧启动命令导致 EMG 全 0 | 不建议用于训练 |
| `S01_day2_raw.csv` 早期 | `adc0=4095`，第一路满量程 | 不建议用于训练 |
| `S01_day2_raw.csv` 后期 | `adc0` 正常，但 `adc1=0`、`adc2≈0` | 只能用于链路调试，不建议训练三分类 |
| 标签 `reset` / `eblow_flex` | 标签拼写错误 | 需要清洗或删除 |

最新一次统计：

```text
adc0: 0..294      约 0..0.237V，有数据
adc1: 0..0        约 0V，无数据
adc2: 0..5        约 0..0.004V，几乎无数据
adc3: 1290..1360 约 1.04..1.10V
```

结论：

- 采集链路已通。
- A1/A2 传感器或接线仍需硬件排查。
- 在三路 EMG 都稳定前，不要开始正式训练。

### 7.2 ADC 硬件排查方法

对每一路传感器做交换实验：

1. 用万用表量 `A0/A1/A2` 对 F103 GND 的电压。
2. 正常肌电模拟输出不应长期固定在 0V 或 3.3V。
3. 把正常 A0 的传感器 OUT 插到 A1：
   - 如果 `adc1` 正常，A1 引脚没问题，原 A1 传感器/线有问题。
   - 如果 `adc1` 仍为 0，查 A1 排针、PA1 引脚、板子线路。
4. 把异常 A1 的传感器 OUT 插到 A0：
   - 如果 `adc0` 变 0，说明异常跟着传感器走。
   - 如果 `adc0` 仍正常，说明 A1 端口/线更可疑。
5. 电池供电时必须共地：传感器 GND/电池负极/F103 GND 要连在一起。

### 7.3 正式训练前的数据准入标准

建议正式采集前做一个 30 秒 smoke test：

```text
rest 10s
elbow_flex 5 次
elbow_extend 5 次
shoulder_flex 5 次
```

通过标准：

- `emg_biceps` 在屈肘时明显变化。
- `emg_triceps` 在伸肘/放下或抗阻伸肘时明显变化。
- `emg_ant_deltoid` 在抬大臂时明显变化。
- 三路都不能长期 0 或 4095。
- `emg_seq` 持续增加。
- `sensor_tick` 更新。
- 电机字段如果 stale，要么暂时不作为训练目标，要么单独过滤。

## 8. TensorFlow 训练数据理解

### 8.1 文件名不等于标签

一个 session 文件可以同时包含多个动作：

```text
S01_day3_raw.csv
S01_day3_windows.csv
S01_day3_trials.csv
```

真正的标签在列里：

```text
label = rest / elbow_flex / elbow_extend / shoulder_flex
trial_id = 003_elbow_flex_02
trial_index = 3
label_trial_index = 2
```

所以多个动作混在一个 CSV 里不会影响训练，只要 `label` 正确。

### 8.2 为什么 trial id 不怕重复

单独看 `trial_id`，新 session 可能又从 `001_rest_01` 开始。训练时应使用组合键：

```text
global_trial_key = session_id + subject_id + trial_id
```

因此跨 session 不会混淆。

### 8.3 推荐训练输入

第一版分类模型建议用 `windows.csv`，因为它已经把 300 ms 的 raw 数据聚合成特征：

输入特征：

```text
emg_biceps_mean/rms/mav/std/min/max
emg_triceps_mean/rms/mav/std/min/max
emg_ant_deltoid_mean/rms/mav/std/min/max
elbow_pos_mrad_mean
elbow_vel_mrad_s_mean
shoulder_pos_mrad_mean
shoulder_vel_mrad_s_mean
```

标签：

```text
label
```

后续如果要做时序模型，可以直接用 `raw.csv` 重新切 300 ms 或 500 ms 序列窗口。

## 9. 推荐采集流程

### 9.1 硬件准备

1. F103 和三路肌电模块共地。
2. 确认传感器 OUT 接到 A0/A1/A2，而不是 VCC/GND。
3. 用万用表确认每路 OUT 对 GND 不固定 0V 或 3.3V。
4. M33 KitProg3 串口为 `COM20`。
5. F103 DAPLink 串口为 `COM8`。
6. F103 与 M33 CANH/CANL、终端电阻、供电正常。

### 9.2 M33/F103 链路检查

在 M33 shell：

```text
cmd_control_init
cmd_sensor_rate 2 50
cmd_sensor_show
```

期望：

```text
ADC4 有非零且非满量程值
EMG3 seq 增加
F103_HEALTH health_tick 更新
last_ack status=0
```

### 9.3 PC 手动采集

```powershell
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED
python tools\collect_f103_sensor_data.py --source serial --protocol emg3-motor --manual --subject-id S01 --session-id S01_day3 --serial-port COM20 --serial-start-command "cmd_control_init; cmd_sensor_rate 2 50; emg_motor_stream 1 20" --serial-stop-command "emg_motor_stream 0"
```

采集建议：

| 标签 | 单次动作建议 | 初始采集量 |
| --- | --- | --- |
| `rest` | 放松 2 到 5 秒 | 50 到 100 段 |
| `elbow_flex` | 抬小臂，必要时轻微抗阻 | 100 到 200 段 |
| `elbow_extend` | 放下小臂或抗阻伸肘 | 100 到 200 段 |
| `shoulder_flex` | 肘角固定，抬大臂 | 100 到 200 段 |

正式模型要更稳，建议每类至少几百段，分多天、多贴片位置、多疲劳状态采集。不要一次采完就认为泛化足够。

## 10. 烧录与调试工具经验

### 10.1 F103 烧录

Horco DAPLink 对默认 CMSIS-DAP v2 后端不稳定，稳定方式：

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

成功日志：

```text
Erasing...
Programming...
Erased chip, programmed 22528 bytes
```

### 10.2 探针识别

```text
COM20 KitProg3 USB-UART
COM8  Horco DAPLink UART

probe-rs list:
[0] Horco CMSIS-DAP -- serial 846703536441
[1] KitProg3 CMSIS-DAP -- serial 1C161868022E2400
```

如果灯不闪、烧录失败、串口打不开，优先检查：

- 进程占用：Keil、OpenOCD、probe-rs、pyOCD、串口助手、旧采集脚本。
- USB 是否枚举出 DAPLink/KitProg3。
- F103 是否接入正确 DAPLink，不要把 M33 KitProg3 当 F103。
- 固件 hex 是否是最新构建产物。

## 11. 最终可复用调试方法

### 11.1 分层定位

按这个顺序查：

```text
PC CSV 是否有行
  -> M33 串口是否有 EMG3MOTOR
    -> M33 sensor cache 是否有 ADC4/EMG3
      -> M33 是否收到 0x7C2
        -> F103 是否发出 0x7C2
          -> F103 ADC raw 是否正常
            -> 传感器供电/共地/贴片/OUT 接线
```

不要看到 CSV 为 0 就直接调模型，也不要看到 ADC 为 0 就直接改 Python。

### 11.2 CAN 半通问题排查

判断口诀：

```text
health 有，ack 没有：
    F103 能发，M33 能收，但 M33->F103->ACK 链路坏。

F103 RF0R.FMP0 > 0：
    控制帧已经到 F103，查 F103 FIFO drain/ISR/主循环。

ack 有，sensor 没有：
    控制能到，查 F103 stream enable、采样、0x7C2 发送。

sensor 有，ADC 异常：
    通信链路没问题，查模拟输入和传感器。
```

### 11.3 面试讲述 STAR

Situation：

> 我做康复机械臂的动作意图识别，需要把 F103 传感节点的三路 EMG 和 M33 上的电机状态采集成训练数据。

Task：

> 难点是系统跨了三个层级：F103 ADC/CAN，M33 RT-Thread 控制层，PC Python 数据脚本。我要保证采集到的数据有标签、有 trial、有窗口特征，并且能解释每个异常值来自哪里。

Action：

> 我先定义协议和数据 schema，然后写 Python 采集脚本。调试时遇到 rows=0、串口占用、固件版本错误、CAN health 单向通、F103 ACK 丢失、ADC 饱和和 0V 等问题。我通过读 M33 日志、读 F103 bxCAN 寄存器、halt 查看 PC、分析 ISR 和主循环关系，定位到 F103 CAN RX pending 中断风暴。最后采用 ISR mask、主循环 direct drain FIFO、drain 后 unmask 的方式修复，并补了 host 回归测试。

Result：

> 修复后 M33 能看到 ACK、health、sensor 三类计数增长，`cmd_sensor_show` 能显示四路 ADC，PC 端能导出 `raw/windows/trials` 三个 CSV。脚本还支持手动按 1/2/3/4 采集标准标签，避免标签拼写错误。

Learning：

> 我学到跨板卡调试不能只看上层日志，必须能下钻到硬件寄存器和中断行为；数据采集也不是把值写进 CSV 就结束，还要保证标签、窗口、trial、通道映射和硬件有效性都可追溯。

## 12. 简历可写点

可以压缩成 3 到 4 条：

```text
- 设计并实现 F103-M33-PC 三端 EMG + 电机状态数据采集链路，定义 CAN 0x7C0~0x7C3 协议、串口 EMG3MOTOR 文本格式和 raw/windows/trials CSV 数据集 schema。
- 开发 Python 采集脚本，支持串口自动识别、手动/引导式采集、300 ms/100 ms 滑窗特征、trial 元数据、数字快捷标签和多命令启动。
- 定位并修复 F103 bxCAN RX pending 中断风暴问题，通过读取 RF0R、halt PC 和反汇编确认 CPU 被 CAN RX0 IRQ 饥饿，采用 ISR mask + 主循环 direct FIFO drain + unmask 方案恢复 ACK/sensor 链路。
- 建立数据质量排查方法，将 ADC raw 换算为电压，定位 4095 满量程、0V 贴地、共地/供电/OUT 接线等传感器问题，避免坏数据进入 TensorFlow 训练。
```

## 13. 当前遗留与下一步

当前链路状态：

- M33 串口采集链路可用。
- Python CSV 导出可用。
- 标签快捷键已实现。
- F103-M33 CAN 关键问题已定位并修复。
- A0 已从 4095 满量程恢复为可变化信号。
- A1/A2 仍出现 0V 或接近 0V，需要继续硬件排查。

下一步建议：

1. 用万用表和通道交换实验修复 A1/A2。
2. 三路 EMG 都稳定后，重新开新 session，例如 `S01_day3`，不要混入早期坏数据。
3. 每类至少先采 100 到 200 段，确认混淆矩阵后再扩到几百段。
4. TensorFlow 先用 `windows.csv` 做传统分类模型，确认有效后再上 raw 时序模型。
5. 电机 stale 过滤逻辑要在训练脚本中显式处理，避免把无效电机状态当监督目标。

