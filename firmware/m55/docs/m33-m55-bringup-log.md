# M33 + M55 双核烧录与日志验证记录

这份文档记录本次把 M33 LSM6DS3 例程和 M55 IMU MLP 推理 demo 一起跑通的过程。它不是泛泛的说明书，而是这块 Edgi-Talk 板子当前工程里真实踩过的坑和验证结论。

## 1. 本次目标

我们要跑通的是这条最小闭环：

```text
M33 LSM6DS3 例程负责基础启动链路，并打开 M55 核
M55 Blink_LED 工程负责运行 edge_ai + imu_mlp 推理 demo
KitProg3 USB-UART 观察日志
```

先不要急着做 M33 到 M55 的在线 IMU 数据传输。本次 M55 侧用的是固定 IMU 窗口，目的只是证明“Python 训练出的模型参数已经能在 M55 C 代码里正确推理”。

## 2. M33 为什么也要烧

PSoC Edge E84 的启动顺序不是 M55 自己独立上电就运行。当前 BSP 的启动链路可以简单理解为：

```text
Secure M33 -> Non-secure M33 -> M33 调用 Cy_SysEnableCM55() -> M55 application
```

所以只烧 M55 不够。M55 固件写进 `0x60580400` 后，还需要 M33 固件执行：

```c
Cy_SysEnableCM55(MXCM55, CY_CM55_APP_BOOT_ADDR, 10);
```

当前 `CY_CM55_APP_BOOT_ADDR` 在 BSP 里定义为 `0x60580400`，和 M55 固件的烧录地址一致。

## 3. M33 例程的关键开关

M33 LSM6DS3 工程里必须确认：

```text
CONFIG_SOC_Enable_CM55=y
```

对应 `rtconfig.h` 里会有：

```c
#define SOC_Enable_CM55
```

本次还在 M33 例程 `applications/main.c` 里加了一次可见阶段的 CM55 启动请求：

```c
#ifdef SOC_Enable_CM55
    Cy_SysEnableCM55(MXCM55, CY_CM55_APP_BOOT_ADDR, 10);
    rt_kprintf("[m33] CM55 enable requested, boot=0x%08x\r\n", CY_CM55_APP_BOOT_ADDR);
#endif
```

这样做的作用是调试友好：即使早期 board init 里已经调用过，`main()` 里再执行一次也能让我们在串口可见阶段确认 M33 确实请求释放 M55。

## 4. M33 命令行构建的坑

RT-Thread Studio 点按钮构建 M33 时，会在 post-build 里运行 Edge Protect 工具，把 M33 hex 从内部链接地址转换成可烧录地址，并合并 secure CM33 固件。

命令行 SCons 如果没有跑这个后处理，直接烧 `rtthread.hex` 会出现这种现象：

```text
Warn : no flash bank found for address 0x08340400
wrote 0 bytes from file ...
```

原因是 `0x08340400` 不是 OpenOCD 当前 flash bank 能直接写的地址。正确的后处理会把它 relocation 到 `0x60340400`：

```text
Relocating segment 0x08340400-... to 0x60340400-...
Saved file to 'build/rtthread.hex'
merge: command "merge" succeeded
```

本次对 M33 工程做了两个命令行构建修正：

- `SConstruct` 优先查找工程内的 `tools/edgeprotecttools/bin/edgeprotecttools.exe`。
- `config/boot_with_extended_boot_scons.json` 使用工程内的 `tools/edgeprotecttools/cm33_s_signed_fw/proj_cm33_s_signed.hex`。

修正后，命令行 SCons 也能生成可烧录的 `build/rtthread.hex`。

## 5. 烧录顺序

推荐顺序：

```text
1. 编译并烧录 M33 LSM6DS3 工程的 build/rtthread.hex
2. 编译并烧录 M55 Blink_LED 工程的 rtthread.hex
3. 复位或让 OpenOCD reset run
4. 打开 COM16 / 115200 观察日志
```

本次实际串口是：

```text
COM16 KitProg3 USB-UART
```

M33 烧录成功日志关键行：

```text
wrote 184320 bytes from file F:/RT-ThreadStudio/workspace/Edgi_Talk_M33_LSM6DS3/build/rtthread.hex
```

M55 烧录成功日志关键行：

```text
wrote 61440 bytes from file F:/RT-ThreadStudio/workspace/Edgi_Talk_M55_Blink_LED/rtthread.hex
```

## 6. 本次串口验证结果

最终抓到的 M55 推理日志如下：

```text
[edge_ai] sample=0 angle=4 vel=2 load=5 emg=3 -> idle score=83 logits=[83,-26,-75,-120]
[imu_mlp] sample=0 expected=idle predicted=idle score=7547 logits=[7547,-5532,-2889,-3649]
[edge_ai] sample=1 angle=28 vel=34 load=38 emg=30 -> assist score=262 logits=[-269,262,-150,208]
[imu_mlp] sample=1 expected=shake predicted=shake score=33633 logits=[-6093,33633,-9427,-12500]
[edge_ai] sample=2 angle=-22 vel=-30 load=44 emg=18 -> resist score=192 logits=[-225,-92,192,110]
[imu_mlp] sample=2 expected=tilt_left predicted=tilt_left score=7365 logits=[-1434,-5866,7365,-1881]
[edge_ai] sample=3 angle=70 vel=92 load=92 emg=86 -> unsafe score=806 logits=[-909,782,-286,806]
[imu_mlp] sample=3 expected=tilt_right predicted=tilt_right score=5912 logits=[-1931,-1854,-2790,5912]
```

判断是否成功主要看两点：

- 有 `[edge_ai]`，说明 M55 上原来的模拟外骨骼小 demo 在跑。
- 有 `[imu_mlp] expected=... predicted=...` 且四类都匹配，说明从用户采集数据训练出的 MLP 参数已经能在 M55 C 代码里推理。

## 7. 这次学到的工程原则

第一，双核不是“两个固件分别烧了就都会跑”。M55 的运行依赖 M33 释放核。

第二，hex 地址要分清“链接地址”和“可编程地址”。M33 命令行构建必须跑 Edge Protect 后处理，否则 OpenOCD 可能写 0 字节。

第三，先做离线窗口推理是对的。我们已经证明了数据采集、Python 训练、C 参数导出、M55 板端推理这一条链路成立；下一步再做 M33 到 M55 的在线数据通道。
