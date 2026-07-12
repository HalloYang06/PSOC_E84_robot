# EMG + 电机数据采集调试分析报告

日期：2026-06-29

分支：`M33`

当前本地修复提交：`63cedce2 Add EMG motor data collection pipeline`

## 1. 调试背景

本项目需要采集三路 EMG 和电机状态数据，用于后续训练动作意图识别模型。

目标数据链路如下：

```text
F103 采集 EMG ADC
  -> CAN 0x7C2 上报
  -> 英飞凌 M33 接收并缓存传感器数据
  -> M33 通过 emg_motor_stream 输出串口文本
  -> KitProg3 USB-UART COM20
  -> tools/collect_f103_sensor_data.py 读取串口
  -> 导出 raw.csv / windows.csv / trials.csv
```

期望的串口遥测格式：

```text
EMG3MOTOR,<m33_ms>,<biceps>,<triceps>,<ant_deltoid>,<adc3_unused>,<flags>,<seq>,
<shoulder_pos>,<shoulder_vel>,<shoulder_torque>,<shoulder_temp>,<shoulder_current_cmd>,<shoulder_current_limit>,<shoulder_flags>,
<elbow_pos>,<elbow_vel>,<elbow_torque>,<elbow_temp>,<elbow_current_cmd>,<elbow_current_limit>,<elbow_flags>
```

采集脚本命令：

```powershell
python tools\collect_f103_sensor_data.py --source serial --manual --subject-id S01 --serial-start-command "emg_motor_stream 1 20" --serial-stop-command "emg_motor_stream 0"
```

## 2. 初始现象

手动采集时出现：

```text
serial_port=COM20
label> rest
[trial 1] saved rows=0
label> elbow_flex
[trial 2] saved rows=0
```

关键判断：

`rows=0` 不是“肌电信号太小”，而是 Python 脚本没有收到任何可解析的 `EMG3MOTOR,...` 串口数据行。也就是说，问题首先应该排查串口遥测链路，而不是直接怀疑电极贴片。

调试过程中还发现一次标签输入错误：

```text
reset
```

正确标签应该是：

```text
rest
```

这个标签错误不会导致 `rows=0`，只会导致 CSV 里的标签名不规范。

## 3. 串口与脚本排查

### 3.1 串口识别

当前英飞凌板子的串口为：

```text
COM20
KitProg3 USB-UART (COM20)
Manufacturer: Cypress
VID/PID: 04B4:F155
```

脚本已改为默认自动识别 KitProg3/Infineon 串口，因此一般不需要手动传 `--serial-port COM20`。

### 3.2 串口占用问题

调试中曾出现：

```text
SerialException: could not open port 'COM20': PermissionError(13, '拒绝访问。')
```

原因是有旧的采集脚本进程仍在运行，占用了 `COM20`。

处理方式：

```powershell
Stop-Process -Id <pid1>,<pid2>
```

操作注意：

```text
label> q
```

只有在 `label>` 提示下输入 `q` 才是退出脚本。录制过程中提示 `press Enter to stop` 时，应直接按空回车停止当前段，不要输入 `q`。

### 3.3 Python 脚本诊断增强

脚本已增加错误提示：如果板子返回 `command not found`，脚本会直接报固件命令不存在，而不是继续采集出 `rows=0`。

相关文件：

```text
tools/collect_f103_sensor_data.py
tools/test_collect_f103_sensor_data.py
```

## 4. 固件命令缺失问题

释放串口后，直接发送启动命令：

```text
emg_motor_stream 1 20
```

板子返回：

```text
emg_motor_stream: command not found.
```

继续测试原始导出名：

```text
cmd_emg_motor_stream 1 20
```

板子也返回：

```text
cmd_emg_motor_stream: command not found.
```

这说明当时板子里运行的固件并不包含新的 `emg_motor_stream` 命令。

但本地源码和 map 文件中确认存在该命令：

```text
applications/control/control_layer.c:
  MSH_CMD_EXPORT(cmd_emg_motor_stream, ...)
  MSH_CMD_EXPORT_ALIAS(cmd_emg_motor_stream, emg_motor_stream, ...)

rtthread.map:
  __fsym_emg_motor_stream
  __fsym_cmd_emg_motor_stream
```

因此可以判断：本地代码已经有命令，但板子上烧录的不是这版固件。

## 5. 烧录文件错误

进一步检查发现，RT-Thread Studio 的下载配置指向：

```text
Debug\rtthread.hex
```

但是文件时间如下：

```text
Debug\rtthread.hex        2026-06-17  旧固件
build\rtthread.hex        2026-06-27/29  SCons 新产物
```

结论：

之前很可能烧录的是旧的 `Debug\rtthread.hex`，而不是包含 `emg_motor_stream` 的 `build\rtthread.hex`。

## 6. 烧录过程

重新构建命令：

```powershell
$env:RTT_EXEC_PATH='F:\gcc\bin'
F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j8
```

OpenOCD 能正常识别目标：

```text
Detected Device: PSE846GPS2DBZC4A
KitProg3 CMSIS-DAP VID:PID=04b4:f155
```

烧录新文件：

```text
build\rtthread.hex
```

OpenOCD 输出关键行：

```text
wrote 581632 bytes from file F:/RT-ThreadStudio/workspace/Edgi_Talk_M33_Blink_LED/build/rtthread.hex
```

说明写入已经完成。

注意：OpenOCD 在 shutdown/reset 阶段打印过：

```text
Error: kitprog3: failed to acquire the device
```

但这出现在写入完成之后。后续串口 `help` 能看到新命令，证明固件已烧入。

## 7. 新固件第一次运行的问题

烧录新固件后，`help` 中能看到：

```text
emg_motor_stream - stream EMG3 plus motor training telemetry over serial/CAN
cmd_emg_motor_st - stream EMG3 plus motor training telemetry over serial/CAN
```

但是直接执行：

```text
emg_motor_stream 1 20
```

一开始触发了 RT-Thread 断言：

```text
(rt_object_get_type(&mutex->parent.parent) == RT_Object_Class_Mutex) assertion failed
function: _rt_mutex_take
```

继续查看线程发现，复位后控制层线程没有启动：

```text
ctrl_can
ros_cmd
m_status
rehab_svc
```

手动执行：

```text
cmd_control_init
```

之后再运行：

```text
emg_motor_stream 1 20
```

就能正常输出：

```text
EMG3MOTOR,8480,0,0,0,0,0,...
EMG3MOTOR,8501,0,0,0,0,0,...
```

根因：

`emg_motor_stream` 依赖控制层的 mutex、传感器缓存和康复服务状态，但命令允许在 `control_layer_init()` 之前执行，导致未初始化对象被访问。

## 8. 固件修复

修改文件：

```text
applications/control/control_layer.c
```

修复方式：

当 `emg_motor_stream` 要打开串口或 CAN 训练遥测时，先检查控制层是否已初始化。如果没有初始化，则自动执行：

```c
control_layer_init(CONTROL_CAN_DEV_DEFAULT)
```

如果初始化失败，打印：

```text
emg_motor_stream init failed ret=<ret>
```

并关闭遥测开关，避免进入异常状态。

新增静态测试：

```text
tools/test_rehab_mode_static.py
```

测试要求 `cmd_emg_motor_stream` 中必须包含：

```text
control_layer_init(CONTROL_CAN_DEV_DEFAULT)
emg_motor_stream init failed ret=%d
```

## 9. 验证结果

### 9.1 软件测试

以下测试通过：

```powershell
python tools\test_rehab_mode_static.py
python -m unittest tools.test_collect_f103_sensor_data
python -m py_compile tools\collect_f103_sensor_data.py tools\test_collect_f103_sensor_data.py tools\test_rehab_mode_static.py
```

单元测试结果：

```text
Ran 23 tests
OK
```

### 9.2 编译验证

SCons 构建通过：

```text
text    data    bss     dec     hex
462028  15556   311664  789248  c0b00
```

输出固件：

```text
build\rtthread.hex
```

### 9.3 硬件验证

复位后不手动执行 `cmd_control_init`，直接执行：

```text
emg_motor_stream 1 20
```

实际输出：

```text
[control] init done on can0, motor_count=7, ros_cmd_can_id=0x320
emg_motor_stream serial=1 can=0 active=1 period_ms=20
EMG3MOTOR,...
```

统计结果：

```text
emg3motor_count=194
assertion_seen=False
```

说明 `emg_motor_stream` 已能自动初始化控制层，并稳定输出串口遥测。

### 9.4 Python 采集验证

Smoke test 命令：

```powershell
python tools\collect_f103_sensor_data.py --source serial --subject-id SMOKE --session-id smoke_emg_motor --duration-s 2 --max-frames 30 --serial-start-command "emg_motor_stream 1 20" --serial-stop-command "emg_motor_stream 0"
```

结果：

```text
serial_port=COM20
raw_csv=data\sensor_capture\smoke_emg_motor_raw.csv
window_csv=data\sensor_capture\smoke_emg_motor_windows.csv
frames=30 sensor_frames=30
```

说明以下链路已经打通：

```text
M33 串口遥测 -> Python 解析 -> CSV 写入
```

## 10. 当前剩余问题

现在已经不再是 `rows=0`，CSV 能正常写入数据行。

但是当前 EMG 值仍然为 0：

```text
EMG3MOTOR,...,0,0,0,0,0,...
```

`cmd_sensor_show` 中也观察到：

```text
EMG3: biceps=0 triceps=0 ant_deltoid=0 flags=0x00 seq=0 sensor_tick=0
F103: emg_raw=0 emg_filt=0 hr_raw=0 hr_filt=0 flags=0x00 sensor_tick=0
```

这说明目前剩余问题在更上游：

```text
F103 EMG ADC -> F103 CAN 0x7C2 -> M33 sensor cache
```

不再是 Python 脚本或 M33 串口输出问题。

## 11. 后续排查建议

### 11.1 检查 F103 是否开始上报

先查看当前缓存：

```text
cmd_sensor_show
```

尝试打开 F103 传感器上报：

```text
cmd_sensor_rate 1 20
```

再次查看：

```text
cmd_sensor_show
```

如果 F103 数据进入 M33，应该看到：

```text
EMG3 seq 增加
sensor_tick 不为 0 并持续变化
```

### 11.2 检查 F103 ACK 和健康帧

运行：

```text
f103_ping 5 20
cmd_sensor_show
```

期望看到：

```text
F103_HEALTH health_tick 更新
last_ack cmd/seq/status 更新
```

如果 ACK 或健康帧不更新，优先检查：

```text
CAN 接线
CAN 波特率
F103 供电
F103 固件
终端电阻
0x7C0/0x7C1/0x7C2/0x7C3 协议是否一致
```

### 11.3 如果 seq 更新但 EMG 仍为 0

说明 CAN 链路已经通了，问题更可能在 F103 采样或模拟前端：

```text
电极贴片接触
EMG 模拟前端增益
F103 ADC 通道映射
F103 0x7C2 payload 布局
传感器供电和参考地
```

肱二头肌测试建议：

```text
IN+ / IN- 沿肱二头肌肌腹方向贴，间距约 2 cm
REF / GND 贴在骨性位置或肌肉活动较弱区域
做抗阻屈肘动作，不要只轻轻抬手
```

### 11.4 电机状态 stale 的解释

Smoke test 中电机字段出现：

```text
shoulder_stale=True
elbow_stale=True
temp_c=255
```

如果当前没有新鲜电机反馈，这是正常现象。

后续可用这些命令检查电机侧：

```text
cmd_motor_fb <joint>
cmd_m33_motor_status_once
cmd_cansimple_status
```

### 11.5 四路 ADC 与三路 EMG 训练输入

F103 的 `0x7C2` 传感器帧按四路 ADC 解析：

```text
data[0..1] = adc0 = CH0 = emg_biceps
data[2..3] = adc1 = CH1 = emg_triceps
data[4..5] = adc2 = CH2 = emg_ant_deltoid
data[6..7] = adc3 = CH3 = unused / not connected
```

因此 CSV 会同时保留原始字段：

```text
adc0, adc1, adc2, adc3
```

模型第一版只使用前三路肌电字段：

```text
emg_biceps, emg_triceps, emg_ant_deltoid
```

当前第 4 路没有接线，`adc3` 只用于调试观察，不进入窗口特征和模型输入。不要再把 `data[6]` 当成 `emg_flags`、`data[7]` 当成 `emg_seq`；M33 串口输出里的 `seq` 由 M33 本地生成。

## 12. 当前可用命令

### 12.1 手动采集

```powershell
python tools\collect_f103_sensor_data.py --source serial --manual --subject-id S01 --serial-start-command "emg_motor_stream 1 20" --serial-stop-command "emg_motor_stream 0"
```

推荐标签：

```text
rest
elbow_flex
elbow_extend
shoulder_flex
```

操作方式：

```text
label> rest
按空回车停止当前段
label> elbow_flex
按空回车停止当前段
label> q
```

### 12.2 短时间 smoke test

```powershell
python tools\collect_f103_sensor_data.py --source serial --subject-id SMOKE --session-id smoke_emg_motor --duration-s 2 --max-frames 30 --serial-start-command "emg_motor_stream 1 20" --serial-stop-command "emg_motor_stream 0"
```

期望结果：

```text
frames=30 sensor_frames=30
```

## 13. 调试结论

本次调试已经解决：

```text
COM20 识别
串口被占用导致无法打开
脚本 rows=0 无明确错误
板子缺少 emg_motor_stream 命令
烧错旧 Debug\rtthread.hex
emg_motor_stream 未初始化控制层导致 mutex 断言
M33 串口遥测到 Python CSV 的完整链路
```

当前仍需继续解决：

```text
F103 EMG 数据没有进入 M33，表现为 EMG3 三路均为 0，seq 和 sensor_tick 也为 0
```

下一步应集中排查 F103 上报、CAN 0x7C2、F103 控制命令和 EMG ADC 采样链路。
