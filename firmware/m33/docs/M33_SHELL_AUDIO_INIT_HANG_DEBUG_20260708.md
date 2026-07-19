# M33 Shell 启动卡死与音频初始化阻塞问题总结

日期：2026-07-08

## 背景

在 M33 工程联调康复控制链路时，串口能够看到 Secure Boot、PSRAM 初始化和 RT-Thread banner，但迟迟进不到 `msh />`。表现上像 hardfault、系统卡死或控制层没有启动，实际原因是启动阶段被音频设备初始化链路阻塞，控制 shell 和后续 rehab/CAN 命令没有机会起来。

本问题影响后续操作：

- 无法执行 `cmd_control_debug`、`cmd_sensor_show`、`cmd_motor_report` 等 M33 shell 命令。
- 无法通过 M33 shell 激活 F103 数据上报。
- 无法验证 NanoPi 通过 CAN 切换助力/阻力模式。
- 无法继续闭环验证 F103 -> M33 -> M55 -> NanoPi -> 云端平台链路。

## 现象

串口启动日志停在 RT-Thread 早期设备初始化附近：

```text
****************** PSOC Edge MCU: CM33 Secure Mode******************
PSRAM Cache is Enabled
PSRAM init successful
****************** PSOC Edge MCU: CM33 Secure Mode Exit******************

[D/drv_hyperam] hyperam init success, mapped at 0x64200000, size is 16777216 bytes, data width is 16

 \ | /
- RT -     Thread Operating System
 / | \     5.0.2 build Jul  8 2026 05:07:42
 2006 - 2022 Copyright by RT-Thread team
[I/I2C] I2C bus [i2c0] registered
[I/i2s] ...
```

随后没有稳定进入：

```text
msh />
```

因此外部看起来像 M33 hardfault 或 shell 起不来。

## 定位过程

1. 先确认串口和 DAPLink 正常：
   - COM16 是 KitProg3 USB-UART。
   - OpenOCD 能 reset run。
   - M33 secure boot 和 RT-Thread banner 能正常打印。

2. 抓完整启动日志，发现控制层日志和 shell 都没有出现，启动停在音频相关初始化附近。

3. 对比修改后日志，确认阻塞点集中在：
   - `sound0`
   - `ES8388`
   - `I2S`
   - `PDM/mic0`

4. 结论：不是 F103、M55 推理、NanoPi、rehab mode 或 CAN 协议导致 shell 不响应，而是音频设备在 boot 阶段初始化阻塞了 RT-Thread 后续组件。

## 根因

原始启动路径中，`sound0` 注册和 `ES8388/I2S` 硬件初始化发生在系统设备初始化阶段。该路径依赖 I2C/I2S/codec/shared clock 等资源，一旦初始化卡住，就会阻塞 RT-Thread 后续初始化流程，导致 `msh />` 不出现。

PDM 麦克风也和 I2S 存在共享时钟关系，启动阶段过早初始化 PDM 同样可能扩大阻塞面。

关键点：

- 控制链路没有坏。
- BLE 不需要切掉。
- 小智能力不应该删除。
- 需要把音频硬件初始化从启动强依赖改成按需初始化。

## 修复策略

### 1. 保留 BLE

BLE 仍然在 M33 启动阶段拉起，用于 APP 连接，不做裁剪。

启动成功日志中可以看到：

```text
[m33] app ble link step1 bt_board_bridge
[m33] app ble link step2 app_ble_service_init
[m33] app ble link step3 app_ble_service_start
[m33] app ble link step4 bt_hci_transport_init
[bt.hci] transport ready
[bt.hci] starting bring-up
[bt.hci] wiced_bt_stack_init result=0x00000000
[bt.hci] transport started
```

### 2. `sound0` 改为按需初始化

启动阶段不再自动注册/初始化 `sound0`，避免 ES8388/I2S 阻塞控制链路。

启动时只打印提示：

```text
[W/i2s] sound0 auto registration deferred; run cmd_sound0_init when audio is needed.
```

需要使用小智音频播放能力时，再手动执行：

```text
cmd_sound0_init
```

这样做不是切掉小智，而是把小智音频从“启动强依赖”改为“需要时手动拉起”。

### 3. ES8388/I2S 硬件初始化延后

ES8388 codec 和 I2S 硬件初始化不再阻塞系统 boot。只有在音频设备被显式初始化/播放时才执行相关硬件初始化。

### 4. PDM/mic0 硬件初始化延后

`mic0` 可以保留设备注册，但 PDM 硬件初始化延迟到录音开始时执行。

启动日志示例：

```text
[I/drv.mic] audio pdm registered.
[I/drv.mic] !!!Note: pdm depends on i2s0, they share clock.
[I/drv.mic] mic0 registered; PDM hardware init deferred until record start.
```

## 修复后启动结果

修复后 M33 能稳定进入 shell：

```text
[W/i2s] sound0 auto registration deferred; run cmd_sound0_init when audio is needed.
[I/drv.mic] audio pdm registered.
[I/drv.mic] !!!Note: pdm depends on i2s0, they share clock.
[I/drv.mic] mic0 registered; PDM hardware init deferred until record start.
[m33] app ble link step1 bt_board_bridge
[m33] app ble link step2 app_ble_service_init
[m33] app ble link step3 app_ble_service_start
[m33] app ble link step4 bt_hci_transport_init
[bt.hci] transport ready
[bt.hci] starting bring-up
[bt.hci] wiced_bt_stack_init result=0x00000000
[bt.hci] transport started
msh />
```

这说明：

- M33 shell 已恢复。
- BLE 保留并正常启动。
- 小智音频能力保留，但改为按需初始化。
- 后续可以继续执行控制链路命令。

## 烧录注意事项

M33 镜像经过 relocation 后位于外部 SMIF/QSPI 地址，例如：

```text
0x60340400
```

烧录时必须让 OpenOCD 拉起 CM55/SMIF 依赖，否则会出现：

```text
Warn : no flash bank found for address 0x60340400
Warn : no flash bank found for address 0x70100000
wrote 0 bytes
```

正确烧录路径需要包含：

```text
set DEVICE PSE84xGxS2
set ENABLE_CM55 1
```

成功标志：

```text
Programming Finished
Verify Started
Verified OK
```

注意：OpenOCD 末尾偶发的 KitProg acquire warning 如果发生在 `Verified OK` 之后，一般不是烧录失败的证据，需要以 `Programming Finished` 和 `Verified OK` 为准。

## 后续调试建议

M33 shell 恢复后，按安全顺序继续调试：

1. 先读状态：

```text
cmd_control_debug
cmd_sensor_show
rehab status
cmd_ros_last
```

2. 再开电机反馈上报：

```text
cmd_motor_report 4 1
cmd_motor_report 5 1
cmd_motor_report 6 1
```

3. 回读反馈和预启动安全门：

```text
cmd_motor_fb 4
cmd_motor_fb 5
cmd_motor_fb 6
cmd_m33_prearm_check 0x38
```

4. 只有反馈新鲜、安全门通过时，才允许 NanoPi 发阻力/助力模式切换。

5. 测试完成后立即切回被动模式。

## 结论

这几次 M33 shell 起不来并不是 rehab 控制服务、F103、M55 推理或 NanoPi 模式切换本身的问题，而是启动阶段音频初始化阻塞了系统。

最终有效方案是：

- 启动阶段优先保证 M33 shell、控制链路、BLE。
- `sound0/ES8388/I2S/PDM` 改为按需初始化。
- 小智不删除，BLE 不关闭。
- 需要小智音频时执行 `cmd_sound0_init` 手动拉起音频设备。

该方案能让康复控制闭环先稳定跑起来，同时保留后续小智音频功能恢复入口。
