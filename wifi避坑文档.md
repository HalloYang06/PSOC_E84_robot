# wifi 避坑文档

## 1. 现象

在 `wifi` 工程中启用 `WHD + FAL` 后，常见报错有：

```text
Read resource head error for partition[whd_firmware]
whd_bus_sdio_download_resource: TRX header mismatch
Read resource head error for partition[whd_clm]
ERROR: WLAN: could not download clm_blob file
```

最终表现为：

```text
[E/whd.wlan] Unable to start the WiFi module!
```

## 2. 根因总结

这次问题最终确认有 3 个根因：

1. `WHD` 资源分区一开始没有预烧录内容。
2. 资源打包头最初写成了 `12` 字节，但官方 `resource_hnd_t` 实际是 `16` 字节。
3. `whd_clm` 和 `whd_nvram` 位于同一个 `256KB` 擦除扇区，分开烧录会互相擦掉。

## 3. 正确配置思路

### 3.1 WHD 资源方式

`wifi` 工程要使用：

- `Flash Abstraction Layer (FAL)`

不要改成：

- `File System`

因为当前工程没有现成 `/sdcard` 挂载点，走 `FS` 会直接找不到资源文件。

### 3.2 分区名称

WHD 资源分区名必须保持：

- `whd_firmware`
- `whd_clm`
- `whd_nvram`

分区表定义见：

- [fal_cfg.h](/D:/RT-ThreadStudio/workspace/wifi/libraries/Common/board/ports/fal/fal_cfg.h)

### 3.3 外部 Flash 基地址

`norflash0` 的实际基地址见：

- [fal_flash_port.c](/D:/RT-ThreadStudio/workspace/wifi/libraries/Common/board/ports/fal/fal_flash_port.c)

关键定义：

```c
#define FLASH_START_ADDRESS 0x60E00000
```

因此资源物理地址为：

- `whd_firmware` -> `0x60E00000`
- `whd_clm` -> `0x60E60000`
- `whd_nvram` -> `0x60E70000`

## 4. 官方资源文件

本工程最终验证通过的资源文件如下：

- Firmware:
  - [55500A1.trxcse](/D:/RT-ThreadStudio/repo/Extract/Board_Support_Packages/Infineon/PSOC_E84-EDGI-TALK/1.1.0/libraries/components/wifi-host-driver/wifi-host-driver/WHD/COMPONENT_WIFI6/resources/firmware/COMPONENT_55500/COMPONENT_SM/55500A1.trxcse)
- CLM:
  - [55500A1.clm_blob](/D:/RT-ThreadStudio/repo/Extract/Board_Support_Packages/Infineon/PSOC_E84-EDGI-TALK/1.1.0/libraries/components/wifi-host-driver/wifi-host-driver/WHD/COMPONENT_WIFI6/resources/clm/COMPONENT_55500/55500A1.clm_blob)
- NVRAM:
  - [cyw55513modpse84som_rev3.txt](/D:/RT-ThreadStudio/repo/Extract/Board_Support_Packages/Infineon/PSOC_E84-EDGI-TALK/1.1.0/resources/cyw55513modpse84som_rev3.txt)

## 5. 资源打包的关键坑

### 5.1 资源头不是 12 字节，而是 16 字节

官方定义见：

- [wiced_resource.h](/D:/RT-ThreadStudio/workspace/wifi/libraries/components/wifi-host-driver/wifi-host-driver/WHD/COMPONENT_WIFI6/resources/resource_imp/wiced_resource.h)

`resource_hnd_t` 的布局是：

- `uint32_t location`
- `uint32_t size`
- `8` 字节 union 存储区

因此总长度是 `16` 字节。

如果错误地按 `12` 字节打包，运行时会出现：

```text
whd_bus_sdio_download_resource: TRX header mismatch
```

因为 `WHD` 读取 `block0` 时会把 `HDR0` 跳过去。

### 5.2 已修正的打包脚本

当前正确脚本：

- [pack_whd_resources.py](/D:/RT-ThreadStudio/workspace/tools/pack_whd_resources.py)

生成结果：

- [whd_firmware.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_firmware.bin)
- [whd_clm.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_clm.bin)
- [whd_nvram.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_nvram.bin)
- [whd_resources_all.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_resources_all.bin)

## 6. 烧录方式的关键坑

### 6.1 不要分开烧 `clm` 和 `nvram`

OpenOCD 日志已经证明这片外部 Flash 的擦除粒度是：

```text
Erase sector size: 0x00040000
```

也就是 `256KB`。

而：

- `whd_clm` 在 `0x60000`
- `whd_nvram` 在 `0x70000`

它们落在同一个 `0x40000 ~ 0x7FFFF` 擦除扇区里。

所以如果分开烧：

- 先烧 `clm`
- 再烧 `nvram`

后写入会把前一个擦掉，最后就会报：

```text
Read resource head error for partition[whd_clm]
```

### 6.2 正确做法：一次性烧录合并镜像

不要再使用以下脚本作为最终烧录方案：

- [program_resources_verify.bat](/D:/RT-ThreadStudio/workspace/wifi/program_resources_verify.bat)
- [program_with_resources_split.bat](/D:/RT-ThreadStudio/workspace/wifi/program_with_resources_split.bat)

这两个只适合调试验证。

最终应使用：

- [program_with_resources.bat](/D:/RT-ThreadStudio/workspace/wifi/program_with_resources.bat)

这个脚本会：

1. 烧录 [rtthread.hex](/D:/RT-ThreadStudio/workspace/wifi/Debug/rtthread.hex)
2. 再一次性烧录 [whd_resources_all.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_resources_all.bin)

## 7. 调试命令

为了定位这次问题，工程里加了两个 `msh` 调试命令，位于：

- [main.c](/D:/RT-ThreadStudio/workspace/wifi/applications/main.c)

命令如下：

```sh
whd_dump_head
whd_dump_block0
```

用途：

- `whd_dump_head`
  - 直接读取 `whd_firmware` 分区前 32 字节
- `whd_dump_block0`
  - 通过 `WHD` 的 `resource_ops.whd_get_resource_block()` 读取 firmware 第 0 块前 32 字节

最终正确输出中，`whd_dump_block0` 前 4 字节应为：

```text
48 44 52 30
```

也就是：

```text
HDR0
```

## 8. 最终成功标志

启动日志出现以下信息说明修复成功：

```text
WLAN MAC Address
WLAN Firmware
WLAN CLM
wlan init success
eth device init ok
```

## 9. M55 DEEPCRAFT 唤醒词与外部 RSRAM

### 9.1 M55 唤醒词模型必须放到 secondary/RSRAM

官方 DEEPCRAFT `AM_LSTM` 唤醒模型和工作缓冲较大，不能全部放进 M55 内部 `m55_data_INTERNAL`。如果链接时报：

```text
rtthread.elf section `.bss' will not fit in region `m55_data_INTERNAL'
region `m55_data_INTERNAL' overflowed
```

处理方式：

1. `applications/ifx_deepcraft/SConscript` 中定义 `CY_ML_MODEL_MEM=.cy_socmem_data`。
2. `Smart_Lights_Demo_config.c` 中的 `am_tensor_arena`、`data_feed_int`、`mtb_ml_input_buffer`、`xIn`、`features`、`output_scores` 都放入 `.cy_socmem_data`。
3. `board/linker_scripts/link.ld` 已将 `.cy_socmem_data` 映射到 `m55_data_secondary`，即外部/secondary RAM 区。

本次验证的成功构建产物：

```text
D:\RT-ThreadStudio\workspace\wifi\Debug\rtthread.hex
text=790760 data=246544 bss=1647468
```

### 9.2 只保留 WW-only，不要回到旧失败唤醒路径

主线唤醒入口是：

```text
voice_service -> xiaozhi_wake_engine -> ifx_deepcraft_wake_adapter -> mtb_wwd
```

不要把 `wake_word_detector.cpp` / `model_deployment.c` 的旧本地测试模型重新接回主线。它们只适合作为旧 demo/调试材料，不是当前小智唤醒词主线。

当前官方示例唤醒词仍是：

```text
OK Infineon
```

后续如果要换成“你好小智”，需要重新训练/导出官方 DEEPCRAFT 兼容唤醒词模型，而不是改字符串。

### 9.3 烧录后不要用 M33 串口命令误判 M55

`COM26` 是 KitProg3 USB-UART，但当前 shell 可能属于 M33。烧 M55 后，在该 shell 输入：

```text
wake_on
```

如果返回：

```text
wake_on: command not found.
```

这只能说明当前交互 shell 不是 M55 shell，不能说明 CM55 没跑。正确确认 CM55 是否运行：

```bat
cd /d D:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\bin
openocd.exe -s ../scripts -s ../flm/cypress/cat1d -f interface/kitprog3.cfg -f target/infineon/pse84xgxs2.cfg -c "init; targets cat1d.cm55; halt; reg pc; reg msp; resume; shutdown"
```

本次验证结果：

```text
pc (/32): 0x6059f636
msp (/32): 0x2003ff88
```

`pc` 落在 M55 镜像区间 `0x6058xxxx`，说明 CM55 已经从刚烧录的 M55 镜像运行。

本次实际成功日志为：

```text
[1300] WLAN MAC Address : 9C:C7:D3:E1:B8:40
[1301] WLAN Firmware    : wl0: Jul 25 2024 08:20:41 version 28.10.301 (aede64b) FWID 01-8cf45cc8
[1302] WLAN CLM         : API: 20.0 Data: IFX.5551x Compiler: 1.49.5 ClmImport: 1.48.0 Customization: v2 24/06/28 Creation: 2024-07-02 03:05:22
[1325] Disabled scanmac randomisation for 55500
[I/WLAN.dev] wlan init success
[I/WLAN.lwip] eth device init ok name:w0
[I/WLAN.dev] wlan init success
[I/WLAN.lwip] eth device init ok name:w1
```

## 9. 后续联网测试

WiFi 初始化成功后，可在 `msh` 中按以下顺序测试：

```sh
ifconfig
wifi scan
wifi join <SSID> <PASSWORD>
ifconfig
ping 8.8.8.8
ping www.baidu.com
```

## 10. 一句话结论

这次问题不是 `LVGL` 占 Flash，也不是 `WHD` 驱动本身坏了，而是：

- 资源没有预烧录
- 资源头格式最初打错
- 外部 Flash 擦除粒度导致分开烧录互相覆盖

最终正确方案是：

- `WHD resources = FAL`
- 使用修正后的 `16` 字节资源头
- 使用 [whd_resources_all.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_resources_all.bin) 一次性整体烧录
