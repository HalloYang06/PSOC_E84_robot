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

## 8.1 2026-06-13 最小 WiFi 扫描 QA 结论

本次在 `wifi` 工程中先关闭/绕开 LVGL、语音、OpenClaw、HTTP 和自动连接，只保留 WiFi 初始化与开机自动扫描 QA。

关键结论：

1. 资源烧录不是当前阻塞点。官方 `Edgi_Talk_M55_WIFI` 和本工程合并资源镜像均已验证资源可用。
2. `FINSH_THREAD_PRIORITY=20` 时，CM55 shell 会在无有效控制台输入时长期占用调度，导致 WHD FreeRTOS 包装线程得不到运行；将 shell 优先级降到 `30` 后，WHD 线程可以运行。
3. 不能用 `rt_wlan_is_ready()` 判断是否可以扫描；它更偏向连接 ready 状态。开机扫描前应等 WHD 初始化阶段到 ready，并确认 `wlan0` 已注册。
4. 当前 porting 层原先的 active scan 后再 passive scan 在本板上不稳定，表现为上层等待 `SCAN_DONE` 超时。临时减枝方案改为 active-only 异步扫描，active 完成即上报 `RT_WLAN_DEV_EVT_SCAN_DONE`。

OpenOCD 内存 QA 成功证据：

```text
g_m55_wifi_scan_qa.magic        = 0x57465141  // "WFQA"
g_m55_wifi_scan_qa.phase        = 4
g_m55_wifi_scan_qa.scan_result  = 0
g_m55_wifi_scan_qa.scan_count   = 6
g_whd_scan_diag_start_calls     = 1
g_whd_scan_diag_start_ret       = 0
g_whd_scan_diag_callback_calls  = 13
g_whd_scan_diag_report_calls    = 12
g_whd_scan_diag_done_calls      = 1
```

当前临时 QA 入口：

- [main.c](/D:/RT-ThreadStudio/workspace/wifi/applications/main.c): `M55_WIFI_SCAN_QA_ONLY`
- [whd_wlan.c](/D:/RT-ThreadStudio/workspace/wifi/libraries/components/wifi-host-driver/porting/src/wlan/whd_wlan.c): active-only scan 与 `g_whd_scan_diag_*`

后续重新引入功能时，建议顺序为：

1. 保持 active-only scan，移除 QA-only 后只恢复正常 WiFi 配网服务。
2. 再恢复保存配置/自动连接。
3. 再恢复 LVGL 配网界面。
4. 最后恢复语音、OpenClaw、HTTP/WebSocket 等重负载模块。

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

## 11. LVGL 配网页扫描为空的排查顺序

LCD 配网页的目标是让用户不用命令行完成配网；命令行只保留给开发诊断。若点击“扫描”后列表为空，不要直接判断是界面坏了，按下面顺序看：

1. 先确认当前交互 shell 是 M55，不是 M33。M55 启动日志应出现 `This core is cortex-m55`，并且 WiFi 成功时应出现 `WLAN MAC Address`、`WLAN Firmware`、`WLAN CLM`、`wlan init success`。
2. 在配网页点“诊断”，看 `WHD stage/result`。如果 WHD 没到 ready，先回到资源烧录、SDIO、固件下载问题，不要调 UI。
3. 看扫描诊断字段：`cb` 是收到的 AP report 数，`done` 是扫描完成事件数，`timeout` 是等待扫描完成超时次数。
   - `cb=0 done=0 timeout>0`：底层扫描没有完成，优先查 WHD/SDIO/中断/事件。
   - `cb=0 done>0 timeout=0`：扫描确实完成但没看到 AP，优先确认路由器是 2.4G/5G 可见、距离、信道和国家码。
   - `cb>0 count=0`：缓存逻辑异常或隐藏 SSID 被过滤。
4. 新版 `wifi_config_scan()` 已经改为等待 `RT_WLAN_EVT_SCAN_DONE`，AP 回调会在等待期间持续缓存到 LVGL 列表。不要再用“刚点扫描立刻读取 0 个 AP”判断扫描失败。

常用现场命令：

```sh
m55_wifi_diag
m55_wifi_scan
# 等 3-5 秒
m55_wifi_aps
m55_wifi_status
```

## 12. 2026-06-11 LVGL 摄像头 QA 结论

本轮为了在 M55 串口不可用时继续 QA，使用 NanoPi 摄像头直拍英飞凌 LCD：

```sh
ssh pi@192.168.2.66
sudo insmod /usr/lib/modules/6.1.141.can-new/kernel/drivers/media/usb/uvc/uvcvideo.ko
v4l2-ctl -d /dev/video45 -c auto_exposure=1,exposure_time_absolute=90,brightness=-10,contrast=65,backlight_compensation=0,sharpness=7
ffmpeg -hide_banner -loglevel error -f v4l2 -input_format mjpeg -video_size 1920x1080 -i /dev/video45 -frames:v 1 -y /tmp/ifx_diag_xy.jpg
```

为了让摄像头可读，LVGL 配网页底部增加黑底白字大号 QA 短码：

```text
R0 N0 C0 D0 T0
S1322 E02000002
X6c Y02
```

字段含义：

- `R`：`rt_wlan_is_ready()`，当前为 `0`，WiFi 管理层未 ready。
- `N`：scan running，当前为 `0`，扫描没有启动。
- `C/D/T`：scan report / scan done / scan timeout 计数，当前全为 `0`，说明不是扫描 API 或 LVGL 列表缓存问题。
- `S1322`：WHD SDIO BLHS `CHK_BL_INIT` 阶段，主机已写 `SDIO_BLHS_H2D_BL_INIT`。
- `E02000002`：`WHD_TIMEOUT`。
- `X6c Y02`：等待 `SDIO_BLHS_D2H_READY` 时，实际读到 D2H `0x6c`，期望位是 `0x02`。

结论：当前“WiFi 扫描不到”不是最终问题，真正卡点是 CYW55513/CYW55500 SDIO bootloader handshake 未给出期望的 `D2H_READY`。下一步优先查：

1. `BLHS_SUPPORT` 是否适用于当前 CYW55513 模组和固件资源组合。
2. `COMPONENT_55500/COMPONENT_55500A1`、`CYW55513IUBG`、NVRAM、CLM、firmware 是否严格匹配板卡。
3. `m55_sdio_kick_change()`、SDIO reset/power 时序、BT 共享启动窗口是否让 WiFi bootloader 进入异常状态。
4. 若仍只能靠摄像头 QA，保留黑底短码，不要改回小字诊断。

## 13. 2026-06-13 官方资料回查与下一轮上电测试

本轮用户明确要求先不要再猜、不要先做 LVGL；板子当前未上电，因此只做官方资料和本地源码对照，不做烧录/复位。

已确认的官方/原始基线：

1. Infineon WHD 官方仓库说明 WHD 是 Infineon WLAN 芯片的嵌入式 Wi-Fi Host Driver，Wi-Fi 6 `55500` 支持 `SDIO`。
2. Infineon `mtb-example-psoc-edge-wifi-web-server` 官方例程说明 PSOC Edge + AIROC `CYW55513` 可通过 `SoftAP + STA` 并发模式做 Web 配网；这说明后续 LCD/LVGL 配网方向成立，但必须等 WHD 初始化和扫描先跑通。
3. 本地 BSP `libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/bsp.mk` 明确：
   - `BSP_COMPONENTS` 包含 `WIFI_INTERFACE_SDIO`、`CYW55513_MOD_PSE84_SOM`。
   - `MPN_LIST` 包含 `CYW55513IUBG`。
   - `DEVICE_COMPONENTS` 为 `55500 55500A1 PSE84`。
   - `DEVICE_CYW55513IUBG_DIE` 为 `55500A1`。
   - `DEVICE_DEFINES` 为 `BLHS_SUPPORT TRXV5`。
4. 本地官方 `projects/Edgi_Talk_M55_WIFI` 例程 README 明确该例程用于 M55 上验证 Wi-Fi scanning、connection、iperf，运行路径也是先 `wifi scan` 再 `wifi join`。
5. 当前工程的 `board/SConscript` 与 `Edgi_Talk_M55_WIFI/board/SConscript` 的关键宏一致，包含 `BLHS_SUPPORT`、`COMPONENT_55500`、`COMPONENT_55500A1`、`COMPONENT_SM`、`TRXV5`。
6. 当前工程 `rtconfig.h/.config` 与 `Edgi_Talk_M55_WIFI` 的关键配置一致：`RT_SDIO_STACK_SIZE=2048`、`RT_SDIO_THREAD_PRIORITY=0`、`BSP_USING_SDIO0`、`WHD_RESOURCES_IN_EXTERNAL_STORAGE_FAL`、`WHD_USING_CHIP_CYW55500`、`WHD_USING_WIFI6`、`CY_WIFI_WHD_THREAD_STACK_SIZE=5120`。

本轮已回正的实验改动：

1. `WHD/COMPONENT_WIFI6/src/whd_chip_constants.c`
   - 恢复官方 BSP 的 55500/TRXV5 RAM 常量：
     - `CHIP_RAM_SIZE = 0xE0000 - 0x20 - 0x1000`
     - `ATCM_RAM_BASE_ADDRESS = 0x3a0000 + 0x20 + 0x1000`
   - 原先把 `0x1000` 偏移去掉属于行为改动，且和官方 BSP 不一致。
2. `WHD/COMPONENT_WIFI6/src/bus_protocols/whd_bus_sdio_protocol.c`
   - `CHK_BL_INIT` 恢复严格等待 `SDIO_BLHS_D2H_READY`。
   - 不再接受 `TRXHDR_PARSE_DONE/VALDN_RESULT/VALDN_DONE` 作为 ready 替代；`0x6c` 应作为异常证据保留，而不是越过官方状态机。
   - 写 reset vector 后恢复官方错误语义：读回失败或值不一致不能强行改成成功。
3. 诊断埋点仍保留，用于下一次上电后读 `g_whd_diag_*` 判断卡点。

本轮编译验证：

```text
scons -j4
text=1278972 data=81488 bss=4534732
build OK
```

下一次板子上电后的最小验证顺序：

1. 烧录当前构建和合并后的 WHD 资源：
   - 使用 `program_with_resources.bat`。
   - 注意 OpenOCD 退出时可能仍有 KitProg3 acquire 报错，先看是否写入了主程序和资源镜像，不要只看退出码。
2. 复位后先等 20-30 秒，不要先点 LVGL 扫描。
3. 用 OpenOCD 读取诊断全局：
   - `g_whd_diag_extra0 = 0x2001b734`
   - `g_whd_diag_extra1 = 0x2001b738`
   - `g_whd_diag_flags  = 0x2001b73c`
   - `g_whd_diag_result = 0x2001b740`
   - `g_whd_diag_stage  = 0x2001b744`
4. 如果仍是 `S1322 E02000002 X6c Y02`：
   - 说明官方严格 BLHS 下还是等不到 `READY`，优先查 Wi-Fi 芯片 reset/power/SDIO bootloader 入口时序，而不是扫描 API 或 LVGL。
5. 如果通过 WHD init 并出现 `WLAN MAC Address / WLAN Firmware / WLAN CLM / wlan init success`：
   - 再运行 `m55_wifi_scan` 或 `wifi scan`。
   - 等 3-5 秒后运行 `m55_wifi_aps`。
   - 此时才回到 LVGL 配网页列表刷新和触摸交互。

## 14. 2026-06-13 WiFi + LVGL 触屏配网里程碑

本轮确认 WiFi 扫描与 LVGL 配网页已经从底层阻塞推进到可用交互阶段，是后续“小智连接服务器平台 / OpenClaw 工具调用 / M55 网络服务”的前置里程碑。

已完成：

1. WiFi 扫描链路打通：
   - `whd_wlan.c` 增加扫描诊断计数。
   - 现场曾读到 `scan_result=0`、`scan_count=6`，后续 LVGL 场景下也读到 WHD scan callback/report/done 计数增长，说明资源烧录、WHD 初始化和扫描回调已通。
   - 当前应继续使用 `program_with_resources.bat` 同时烧录主固件和 `whd_resources_all.bin`，不要只烧 `rtthread.hex`。
2. LVGL 配网页上线：
   - `applications/rehab_wifi_panel.c` 提供触屏扫描、选择 SSID、输入密码、保存、连接、断开、清除和诊断入口。
   - 默认隐藏黑底诊断覆盖层，诊断只作为开发按钮打开。
   - 配网页启动后会自动发起一次扫描，用户不再需要进命令行 `msh` 配网。
3. 触屏输入体验修复：
   - 自定义键盘的 `Del` 不再插入字符串 `Del`，而是执行删除。
   - 避免使用当前字体缺失的 LVGL 图标符号，减少方框字。
   - 重新压缩顶部状态文案、放大网络列表、整理按钮布局，减少互相覆盖。
4. 构建脚本补强：
   - `applications/SConscript` 显式加入 LVGL `env_support/rt-thread` include path。
   - `libraries/Common/board/SConscript` 显式补齐 LVGL port 编译所需的 `src` 下头文件路径，避免干净 worktree 中出现私有头找不到的问题。

本轮验证：

```text
D:\RT-ThreadStudio\workspace\wifi
scons -j4
build OK
text=1160736 data=17396 bss=4525076

program_with_resources.bat
rtthread.hex 写入成功
whd_resources_all.bin 写入成功

OpenOCD reset run
reset command issued
```

注意事项：

- OpenOCD/KitProg3 在写入或 reset 后仍可能打印 `failed to acquire the device`，但只要日志已经显示 `wrote ... rtthread.hex` 和 `wrote ... whd_resources_all.bin`，先不要把它等同于资源未烧录。
- 临时 M55 Git worktree 全量重建时曾因旧分支缺少 LVGL include path 失败；补齐路径后继续全量重建会卡在长时间 C++/LVGL 编译阶段，本地 `workspace\wifi` 主工作区构建和实机烧录已验证。
- WiFi 列表滚动曾怀疑会被刷新打回顶部，现场复查确认可以下拉，暂不改刷新逻辑。

下一步：

1. 继续用触屏配网页完成真实路由器连接，确认拿到 IP。
2. 在 M55 上恢复/验证小智连接服务器平台所需的网络客户端或 HTTP/WebSocket 路径。
3. WiFi 稳定后再恢复语音、小智唤醒和 OpenClaw/OpenAI 类服务，不要在 WiFi 未连通时同时调多条链路。

## 15. 2026-06-13 WiFi 优先与小智延后连接策略

现场现象：

- WiFi/LVGL 已能完成真实连接，但在加入“小智自动连接”后，配网阶段一度出现连接卡住或用户体验退化。
- M33 串口 shell 当前不稳定，`m55qa_status` 无法稳定返回，因此不能把 WiFi 配网页依赖在命令行控制链路上。

本轮结论：

1. WiFi 配网优先级最高。M55 启动后不得在 WiFi 未 ready、未拿到 IP 前启动 voice/mic/WebSocket。
2. 小智连接应是“网络稳定后的后置动作”：
   - 先等 `wlan_ready != 0` 且 `netdev_ip != 0`。
   - 连续多次确认 ready 后，再启动 wake listening 和 XiaoZhi WebSocket reconnect。
   - reconnect 失败只记录并延后重试，不能阻塞 LVGL 配网 UI。
3. 平台 token 只允许通过本地忽略文件或现场注入使用，不能提交进仓库或文档。

已落地：

- `main.c` 增加 `M55_XIAOZHI_AUTO_ENABLE`，当前策略是启用安全版自动连接，但自动线程先等 WiFi/IP 稳定，再启动小智。
- `voice_service_init()` 的首次 WebSocket 连接失败改为 deferred，不再导致整个 voice service 初始化失败；后续由 reconnect 路径在网络 ready 后处理。
- 本轮 M55 `scons -j4` 构建通过，并已用 `program_with_resources.bat` 烧入一次。

后续验证顺序：

1. 复位后先通过 LVGL 连 WiFi，确认屏幕显示已连接。
2. 等 10-20 秒观察是否有小智连接日志或平台侧连接事件。
3. 如果 M33 shell 恢复，再用 `m55qa_status` 看 `xz_token=1`、`xz_ws=1`、`wlan=1`、`ip!=0.0.0.0`。
4. 如果串口仍无响应，不要反复发命令；优先恢复 M33 shell 或用摄像头/平台侧日志做 QA。

## 16. 2026-06-13 对齐官方小智 WebSocket 例程

官方参考：

- 本地官方参考仓库：`D:\RT-ThreadStudio\workspace\_external_refs\xiaozhi-esp32`
- 关键文件：
  - `docs/websocket.md`
  - `main/protocols/websocket_protocol.cc`
  - `main/protocols/protocol.cc`

官方协议要点：

1. WebSocket 握手 header：
   - `Authorization: Bearer <token>`
   - `Protocol-Version: 1`
   - `Device-Id`
   - `Client-Id`
2. 设备 hello：
   - `type=hello`
   - `version=1`
   - `transport=websocket`
   - `features.mcp=true`
   - `audio_params.format=opus`
   - `sample_rate=16000`
   - `channels=1`
   - `frame_duration=60`
3. 听音控制：
   - `{"type":"listen","state":"start","mode":"auto"}`
   - stop 使用 `{"type":"listen","state":"stop"}`
   - wake detect 使用 `{"type":"listen","state":"detect","text":"..."}`。

本轮修正：

- M55 `xiaozhi_voice_relay` 已从自定义 `version=3 + pcm_s16le + 20ms + mode=auto_stop` 改为官方例程形态 `version=1 + opus + 60ms + mode=auto`。
- PC smoke 脚本 `tools/xiaozhi_ws_smoke_test.ps1` 同步为官方 hello/listen 格式。
- 已用本地 token 在 PC 端验证官方 hello/listen 可被中转站接受：
  - `hello` 返回 `transport=websocket`、`audio_params.format=opus`、`frame_duration=60`。
  - `listen start mode=auto` 返回 ACK。
  - 发送 60ms 二进制帧并 stop 后，中转站返回 chat/VLA 分类回复。

仍需注意：

- 当前 M55 端还没有真正引入 Opus 编码器；本轮先把协议 JSON 和时序对齐官方例程。
- 当前中转站对 60ms 二进制帧已能给出回复，但后续要做到完全官方一致，应补 M55 Opus encoder 或让中转站明确兼容 PCM-to-ASR 转码边界。
- 不要在 WiFi 未 ready 前启动小智；官方协议对齐不能牺牲 LVGL 配网稳定性。

## 17. 2026-06-13 LVGL 配网页状态显示优化

现场照片反馈：

- WiFi 已能连接并显示扫描数量，但顶部状态区过挤，小智连接状态不够明显。
- 底部“诊断”按钮出现方框字，说明当前 `rehab_wifi_font` 并未覆盖所有中文 glyph 或按钮区域显示不稳定。

本轮修正：

1. WiFi 状态 label 只保留两行：连接状态/扫描数量 + 操作提示。
2. 小智状态拆成独立浅蓝状态条，固定显示 `XiaoZhi: <state> S:<stage> E:<errno>`，便于不用串口也能看 WebSocket 阶段。
3. 诊断按钮改为 `INFO/HIDE`，诊断面板默认文案改为 ASCII，避开字库缺字导致的方框字。

验证：

- `python -m SCons -j4` 构建通过。
- 本轮仅改 UI 显示，不改 WiFi 扫描、连接、自动连接和资源烧录流程。

## 18. 2026-06-13 LVGL 竖屏布局二次压缩与小智阶段显示

现场照片反馈：

- WiFi 列表、输入框、自动连接和两排按钮在 480x640 竖屏上仍然互相挤压。
- 小智状态只显示“连接中”，不足以判断是 DNS、TCP、WebSocket 握手还是自动线程未启动。

本轮修正：

1. AP 列表高度从 `188` 压到 `136`，SSID/密码输入框从 `46` 压到 `40`，给底部按钮区腾空间。
2. 6 个主按钮改为 `2 x 3` 紧凑网格，每个按钮 `198 x 42`，避免和“自动连接”复选框互相遮挡。
3. 小智状态按 WebSocket stage/errno 显示为 `等待启动/解析中/建Socket/TCP连接/握手中/DNS失败/TCP失败/握手失败/已连接` 等更具体状态。

验证：

- `python -m SCons -j4` 构建通过。
- 已用 `program_with_resources.bat` 烧录，应用和资源 programming 均到 100%；末尾 KitProg3 acquire error 仍为既有现象。

## 19. 2026-06-13 补齐 LVGL 配网页中文字库

现场问题：

- “诊断/隐藏”等按钮曾出现方框字，根因是 `rehab_wifi_font.c` 的 symbols 列表缺少 `诊`、`隐`、`藏` 等 glyph。
- 之前临时用 `INFO/HIDE` 绕开缺字，但这会让中文触屏界面体验变差。

本轮修正：

1. 使用 `lv_font_conv 1.5.3` 从 `C:\Windows\Fonts\Noto Sans SC (TrueType).otf` 重新生成 `applications/rehab_wifi_font.c`。
2. 扩展 symbols，覆盖配网页和小智状态常用字：`诊断隐藏未配置等待解析建握手接收线程启动选择输入检查扫码二维码启用发送小智` 等。
3. 将按钮和诊断面板文案恢复为中文：`诊断/隐藏`、`诊断等待刷新`。

验证：

- `python -m SCons -j4` 构建通过。
- 已用 `program_with_resources.bat` 烧录，应用和资源 programming 均到 100%；末尾 KitProg3 acquire error 仍为既有现象。
