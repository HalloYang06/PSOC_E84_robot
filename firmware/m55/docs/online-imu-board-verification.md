# M33/M55 在线 IMU 链路板端验证记录

日期：2026-06-07

这份记录只写这次真实跑板验证的结论：M33 LSM6DS3 工程作为 producer，把真实 IMU 窗口写入共享内存；M55 工程作为 consumer，从共享内存读取窗口并运行 `imu_mlp` 分类。

## 1. 烧录关键点

PSoC Edge E84 的 M33/M55 应用放在 `0x6034...` / `0x6058...` 这类 SMIF 映射地址。OpenOCD 必须加载 SMIF flash loader：

```text
-s F:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\flm\cypress\cat1d
-c "set QSPI_FLASHLOADER ../flm/cypress/cat1d/PSE84_SMIF.FLM"
```

如果少了它，烧录会出现：

```text
Warn : no flash bank found for address 0x60340400
wrote 0 bytes from file ...
```

本次正确烧录结果：

```text
M33: wrote 188416 bytes from file F:/RT-ThreadStudio/workspace/Edgi_Talk_M33_LSM6DS3/build/rtthread.hex
M55: wrote 65536 bytes from file F:/RT-ThreadStudio/workspace/Edgi_Talk_M55_Blink_LED/rtthread.hex
```

## 2. 本次修正

第一次验证时，M55 一直打印：

```text
[edge_ai_online] waiting producer status=-4 attached=0 addr=0x261c0000
```

OpenOCD halt M33 后，PC 位于：

```text
rt_assert_handler
rt_console_set_device -> rt_device_open -> ifx_configure
```

原因是双核同时运行时，KitProg3 USB-UART 只有一个；当前让 M55 作为唯一日志核，M33 作为无串口 producer 更稳。M33 工程做了两个修正：

```text
packages/lsm6ds3tr/lsm6ds3tr-c_port.c
  INIT_APP_EXPORT 只创建 lsm6ds3 采集线程并返回，不再直接永久循环。

libraries/HAL_Drivers/drv_uart.c
  UART setup 失败时返回 -RT_ERROR，不再 RT_ASSERT 卡死。
```

这个修正背后的原则是：传感器采集任务不能阻塞启动链路；M33 producer 不应该依赖串口可用才工作。

## 3. 通过现象

重新构建并烧录 M33 后，打开 COM16 / 115200，M55 持续消费 M33 共享内存窗口：

```text
[edge_ai_online] seq=2 classifier=imu_mlp label=tilt_left score=51002 channels=7
[edge_ai_online] seq=3 classifier=imu_mlp label=tilt_left score=11822 channels=7
[edge_ai_online] seq=4 classifier=imu_mlp label=tilt_right score=11424 channels=7
[edge_ai_online] seq=13 classifier=imu_mlp label=tilt_right score=11908 channels=7
```

`channels=7` 表示 M33 producer 发布的是 7 通道窗口：`acc_x/acc_y/acc_z/gyro_x/gyro_y/gyro_z/temp`。`seq` 持续增长，说明 producer 在不断发布；M55 能打印分类结果，说明 consumer 能 attach、read、classify、ack。

## 4. 当前结论

本次已经跑通：

```text
M33 LSM6DS3 thread
-> edge_ai_m33_producer
-> shared memory 0x261C0000
-> M55 edge_ai_online_consumer
-> imu_mlp classifier
-> COM16 result log
```

下一步建议减少 M55 固定窗口 demo 的刷屏，只保留在线链路日志；再往后才是替换成 EMG/电机/关节角等正式外骨骼信号源。
