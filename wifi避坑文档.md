# wifi 避坑文档

## 31. 2026-06-20 小智链路新结论：平台下行已到 M33，剩余 blocker 是 speaker 播放

本轮确认：

1. 不要再把 WiFi/token 当主 blocker：
   - `wlan=1 ready=1`
   - `ip=192.168.3.32`
   - `saved=1 auto=1 storage=0`
   - `xz_ws=1`
   - `xz_stage=70`
   - `xz_errno=0`
   - `token_len=442`
2. M55 仍按官方产品路线：
   - `CM55 mic0 -> Opus -> WebSocket -> platform -> M33 TTS audio`
3. 为无人值守 QA 新增显式开关：
   - `m55qa_probe_pcm_on`
   - `m55qa_probe_pcm_off`
   - 只有打开 QA gate 且小智正在 listening 时，M55 才接收 `m33qa_xz_probe` 的 PCM。
4. QA gate 已验证：
   - `m55qa_probe_pcm_on` 返回 `voice_ack cmd=11 result=0`
   - `m55qa_capture_on` 返回 `voice_ack cmd=1 result=0`
   - `m33qa_xz_probe` 后，M33 收到平台下行：`tts audio rx total=1280`
   - M33 也进入播放写入：`tts audio write chunk=...`

本轮修复：

1. M55 不再把每个 TTS 下行包硬截断为最多 8 个 128B IPC chunk。
2. M55 发送 TTS chunk 到 M33 时增加短等待，避免 M33 队列瞬时满就直接丢。
3. M33 QA 控制命令增加短重试，避免瞬时 IPC 忙导致 `m55qa_capture_on ret=-255`。

当前剩余问题：

1. 平台/模型/下行不是空想，已经走到 M33。
2. 实验性的 M33 async speaker worker 会触发 RT-Thread audio 断言：
   - `(rt_object_get_type(&timer->parent) == RT_Object_Class_Timer) assertion failed at function:rt_timer_stop`
3. 因此 async speaker worker 已回退，下一步要参考板卡/RT-Thread 音频驱动的官方播放方式，而不是随便开 worker 写 `sound0`。
4. 真实用户语音仍要回到 CM55 mic0 路线验证；`m33qa_xz_probe` 只用于无人 QA，不是产品路径。

下一步建议：

1. 先修 M33 speaker 播放稳定性。
2. 再跑：
   - `m55qa_probe_pcm_on`
   - `m55qa_capture_on`
   - `m33qa_xz_probe`
   - `m55qa_capture_off`
   - `m55qa_status`
3. 成功标准是同时满足：
   - M33 出现 `tts audio rx total=...`
   - speaker 无断言
   - shell 仍响应
   - `tx_pending=0`
4. 不要回头重配 SSID/token/资源，除非 `m55qa_status` 里的 WiFi 或 WebSocket 指标明确退化。

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

## 8.2 2026-06-19 烧录 probe 选择坑

这轮 `program_with_resources.bat` 的真正阻塞点不是固件，而是 probe 选择。

现象：

1. 默认 `openocd.exe ... interface/kitprog3.cfg ...` 会先尝试板载 `KitProg3 CMSIS-DAP`，但在 `Acquisition in Test Mode` 阶段失败。
2. 直接改成通用 `interface/cmsis-dap.cfg` 时，OpenOCD 会落到外接 `Horco CMSIS-DAP v2`，随后报 `CMSIS-DAP command CMD_INFO failed`。
3. 最终确认板载下载器本体是 `USB\\VID_04B4&PID_F155`，父序列号是 `17040F11022F2400`，需要显式锁定它，不能让 OpenOCD 自选。

当前处理：

- `program_with_resources.bat` 已改成在 `kitprog3.cfg` 下显式加 `adapter serial 17040F11022F2400`。
- 这样可以稳定把 `rtthread.hex` 和 `whd_resources_all.bin` 写进去。
- 末尾仍可能看到 `kitprog3: failed to acquire the device`，但这发生在写入完成之后，属于收尾握手告警，不是写入失败。

可复用技巧：

- 同机同时插着板载 `KitProg3` 和外接 `Horco CMSIS-DAP` 时，不要靠自动探测。
- 先用 `Get-PnpDeviceProperty` 查 `DEVPKEY_Device_Parent`，再把板载 probe 的父序列号写进烧录脚本。
- 如果 `cmsis-dap` 走到 `CMD_INFO failed`，优先怀疑 probe 模式/驱动，而不是 hex 或资源文件。

## 8.2 2026-06-15 XiaoZhi WebSocket QA 结论

本轮确认 WiFi 已不是主阻塞点：

- 串口 `m55qa_status` 显示 `saved=1 auto=1`，复位后可自动连回。
- DHCP 正常，实测 `ip=192.168.3.32 gw=192.168.3.1 dns0=192.168.3.1`。
- `wlan=1 ready=1 rssi=-56`。

小智 WebSocket 仍未连通：

- 已将 `applications/websocket_client.c` 从手写 POSIX/lwIP socket 握手改为 lwIP 自带 `wsock_*` callback client 的薄适配层。
- 已打开 `RT_LWIP_USING_WEBSOCKET`，并编入 `src/apps/websocket/websocket_client.c`、`sha-1.c`、`base64-decode.c`。
- 为避免把 TLS/mbedTLS 拉进 M55，已把 lwIP websocket client 里的 TLS 引用改为 `#if LWIP_ALTCP_TLS` 条件编译；当前平台 URL 是明文 `ws://...:8011`。
- M55 构建通过，烧录 M55 hex 和 `whd_resources_all.bin` 均到 100%。
- 串口 QA 仍显示 `xz_ws=0 xz_stage=20 xz_errno=-4`，其中 `-4` 是 lwIP `ERR_RTE`，出现在 `wsock_connect()` / `altcp_connect()` 启动连接阶段。

当前判断：

- 云端 URL/token/path 之前已由 PC raw WebSocket 验证过可返回 `101 Switching Protocols`。
- 同板 WiFi/DHCP 正常，因此当前 blocker 更像 lwIP raw/altcp 路由或默认 netif 上下文问题，而不是 WiFi 扫描/连接问题。
- 下一步应优先在 M55 上诊断 `netif_default`、`ip_route()`、`altcp_connect()` 的输入和返回，或在官方 `wsock_connect_addr()` 前显式绑定可用 WiFi netif/local IP。
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

## 20. 2026-06-13 按源码实际中文集合补齐 LVGL 字库

现场问题：

- 在继续做小智真实状态面板后，固定 UI 文案新增了 `在线待唤醒/正在思考/正在回答/准备语音回复/说唤醒词，我会回应你` 等中文。
- 手写 symbols 容易继续漏字，导致同一类“方框字”反复出现。

本轮修正：

1. 从 `applications/rehab_wifi_panel.c`、`applications/xiaozhi_ui_state.c`、`applications/voice_service.c`、`applications/wifi_config_service.c` 自动提取固定 UI/状态文案里的中文字符。
2. 用提取出的 109 个不同中文字符和标点重新生成 `applications/rehab_wifi_font.c`。
3. 保留 `#include "lvgl.h"`，避免 `lv_font_conv` 默认生成的 `lvgl/lvgl.h` 路径在当前工程里编译失败。

验证：

- `python -m SCons -j4` 构建通过，固件尺寸约 `text=1227156 data=81428 bss=4528904`。
- 已用 `program_with_resources.bat` 烧录，M55 应用写入 `1310720 bytes`，WHD 资源写入 `466944 bytes`，两段 programming 均到 100%；末尾 KitProg3 acquire error 仍为既有现象。

边界：

- 这只覆盖固定 UI 文案。小智模型回复是任意中文，不能靠静态小字库完整覆盖所有汉字；后续若要完整显示长中文回复，应考虑外部字库/更大字库/回复摘要显示。官方小智主路径仍应以语音回复为主。

## 21. 2026-06-13 小智动态回复缺字兜底

### 现象

- 固定 UI 文案补齐后，小智平台动态回复仍可能出现方框字。
- 根因是模型回复不是固定集合，109 个源码抽取字无法覆盖任意聊天文本。

### 当前处理

1. `rehab_wifi_font` 保留源码抽取字库，同时把 `.fallback` 接到 LVGL 已启用的 `lv_font_simsun_16_cjk`。
2. `xiaozhi_ui_state` 保存动态回复时按 UTF-8 边界截断，避免 160 字节缓冲区切断半个汉字后造成乱码/方框。
3. 这样固定 UI 优先使用 18px Noto Sans SC，动态回复缺字时尽量回退到内置 CJK 字体。

### 后续取舍

- 如果要“任意中文长回复完全不缺字”，需要外置/完整中文字库或更大的生成字库，flash/text 体积会继续增加。
- 当前策略优先保证小智状态、短回复、唤醒/思考/回答流程可读，并给后续小模型保留资源。

## 22. 2026-06-13 小智音频协议先按 PCM 兼容

### 现状

- 官方参考例程的 WebSocket 二进制音频是 Opus。
- 当前 M55/M33 这条链路暂时没有完整 Opus 编解码闭环。

### 当前取舍

1. M55 `hello` 先上报 `pcm_s16le`，不再假装是 Opus。
2. 这样平台中转站如果按 PCM 处理，就能先把“说话 -> 平台 -> 回答”打通。
3. 后续如果要严格回官方 Opus，再补完整编解码，而不是继续让协议字段和实际数据打架。

## 23. 2026-06-15 小智连接当前卡在 WebSocket 传输层，不是 WiFi

现场结论：

1. WiFi 自动连接已稳定，复位后 `m55qa_status` 可见 `saved=1 auto=1 storage=0`、`wlan=1 ready=1`、`ip=192.168.3.32`。
2. CM55 独立 TCP 探针可以连到 `106.55.62.122:8011`，说明 WiFi、DHCP、网关、基础 TCP 都不是当前主因。
3. PC 侧使用同一个 URL 和 scoped token 做原始 WebSocket Upgrade，可以拿到 `HTTP/1.1 101 Switching Protocols`，说明平台 token、路径和云端服务有效。
4. CM55 手写 socket WebSocket 客户端已经能走到握手接收阶段，但 `recv` 在当前 RT-Thread/lwIP socket 路径上会阻塞；`select()`、`fcntl(O_NONBLOCK)`、`MSG_DONTWAIT`、`SO_RCVTIMEO`、`FIONBIO`、直调 `lwip_recv` 都不够可靠。

下一步建议：

- 不要继续把小智问题回退到 WiFi 扫描/资源固件方向。
- 改走 BSP 自带的 lwIP callback WebSocket 客户端：启用 `RT_LWIP_USING_WEBSOCKET`，把 `rt-thread/components/net/lwip/lwip-2.1.2/src/apps/websocket/*.c` 编进来，再用 `lwip/apps/websocket_client.h` 的 `wsock_connect/wsock_write` 包住现有 `applications/websocket_client.h` API。
- 只有当 `m55qa_status` 显示 `xz_ws=1` 后，再继续唤醒词、PCM/Opus、扬声器回复闭环。

## 24. 2026-06-15 WebSocket 已连通，当前阻塞转为音频格式/ASR

现场结论：

1. M55 编译通过并烧录后，WiFi 自动连接稳定：`saved=1 auto=1`、`wlan=1 ready=1`、`ip=192.168.3.32`。
2. 小智 WebSocket 已能连上：`xz_ws=1 xz_stage=70 xz_errno=0`。
3. `m55qa_capture_on` 已能触发 M55 麦克风采集，`m55qa_capture_off` 后可见上行统计，例如 `frames=2326 pcm_seq=2326 probe_lwip=387/744588`。
4. 目前没有收到 `stt/llm/tts` 或二进制语音回复；`probe_posix=0/2` 只证明收到过握手/控制文本。

本轮修正：

1. M55 WebSocket header 和 hello 已统一为协议 v3：
   - `Protocol-Version: 3`
   - `hello.version=3`
   - binary 使用 `[type=0,reserved=0,payload_size_be16,payload]`
2. M55 `audio_params.format` 改为 `pcm_s16le`，因为当前真实 payload 是 16 kHz mono S16LE PCM，不再声明成 Opus。
3. `WSMSG_MAXSIZE` 保持 `4096`，避免 60ms PCM 帧加 v3 头超过原来的 1420 限制。

仍需注意：

- 官方小智 ESP32 例程主路径是 Opus 编解码；当前 M55 还没有 Opus encoder，M33 也还没有 Opus decode->speaker 闭环。
- PC 侧 `ClientWebSocket` 探针证明平台 hello 可以接受并回显 `pcm_s16le`，但这不等于平台 ASR 后端已经处理 PCM。
- 下一步不要再回头查 WiFi 扫描/密码。应看平台 relay 日志确认 PCM 是否进入 ASR；若没有，就在 relay 侧做 PCM->ASR/Opus 转码，或在 M55/M33 补小型 Opus 编解码。

补充验证：

- 用户不在现场时，现场麦克风可能只有杂音/静音，不能单靠板端无回复判定 PCM 不通。
- 已用 Windows 语音合成生成清晰的 `16 kHz / mono / 16-bit` WAV，再把 PCM 按 v3 WebSocket 包发送到同一平台。
- 结果仍然只收到 `listen start/stop`，没有 `stt/llm/tts`。这基本说明当前平台 relay 还没有把 `pcm_s16le` 二进制帧送入 ASR。
- 继续方向应优先改 relay 侧 PCM ASR/转码，或回到官方 Opus 路线；不要再把时间花在现场杂音、WiFi、LVGL 上。

后续复测：

- relay 更新后，同一个 PC 合成语音 PCM 探针已返回完整链路：`stt -> llm -> chat -> tts start/stop`。
- 这说明平台侧 `pcm_s16le` 兼容分支已经能进 ASR；后续仍需保留“官方 Opus 是长期主路径”的边界。
- 板端复位后 M55 IPC 恢复，`m55qa_xz_reconnect` 返回 `cmd=1003 result=0`，`xz_ws=1 xz_stage=70`。
- 板端再次 `capture_on/off` 后可见 `probe_lwip=386/742664`，说明 M55 采集和上行仍正常。
- 因为现场没人说话，本轮板端无 STT 不能判为失败；需要有人靠近板端麦克风说清晰提示词再验收。

## 25. 2026-06-15 小智交互与 M33 扬声器链路进展

本轮目标：

- 用户说唤醒词后自动开始录音。
- 录音时 LVGL 显示录音状态，长时间低声/静音后自动停止录音并切到“正在思考”。
- 回答不再占用 LVGL 大面积文本，优先走扬声器。

本轮修正：

1. M55 `voice_service.c` 增加自动 EOU 判断：
   - 最短录音约 `900 ms`。
   - 静音约 `1400 ms` 后自动 `listen stop`。
   - 最长录音约 `12000 ms` 防止一直录。
   - 停止后 UI 切到 `XIAOZHI_UI_THINKING`。
2. LVGL 小智面板改成紧凑状态：
   - `在线待唤醒`
   - `我在听`
   - `正在思考`
   - `正在回答`
   - 模型长回复不再默认显示在屏幕上，避免小屏遮挡和动态中文字库继续膨胀。
3. M33 扬声器方向确认根因：
   - 之前 `[audio_playback] ERROR: Cannot find sound0 device` 不是平台没回 TTS，而是 M33 `drv_i2s.c` 里 `M33_SKIP_SOUND0_INIT_FOR_XIAOZHI_QA` 默认置 `1`，启动时跳过了官方 `rt_hw_sound_init()`。
   - 已改为默认 `0`，恢复 `sound0` 注册。
   - 串口 `audio_playback_probe_cmd` 已验证 `sound0 -> found`。
4. M33 TTS 播放层改为走 RT-Thread 官方 `sound0` audio device：
   - 收到 M55 的 `MSG_TYPE_TTS_AUDIO` 后初始化/启动 `audio_playback`。
   - TTS chunk 当前为 `128 B`，直接写入 `sound0`，不再额外攒二级播放线程缓冲，减少阻塞和 `-RT_EFULL` 风险。
   - 单次底层写入不超过 `RT_AUDIO_REPLAY_MP_BLOCK_SIZE=4096`。

烧录注意：

- M55 仍使用 `wifi/program_with_resources.bat`，会同时烧 `rtthread.hex` 和 `whd_resources_all.bin`。
- M33 当前 hex 使用 C-AHB 地址 `0x0834xxxx`，OpenOCD 需要加 `0x58000000` offset 写到 SMIF 物理地址：

```sh
flash write_image erase D:/RT-ThreadStudio/workspace/yiliao_m33/build/rtthread.hex 0x58000000
```

验证结果：

- M55 构建通过。
- M33 构建通过，最新尺寸约 `text=280692 data=16076 bss=310744`。
- M55 烧录时应用写入 `1310720 bytes`，WHD 合并资源写入 `466944 bytes`。
- M33 最新烧录写入 `299008 bytes`。
- 复位后 `m55qa_status`：
  - `saved=1 auto=1 storage=0`
  - `wlan=1 ready=1 ip=192.168.3.32`
  - `xz_ws=1 xz_stage=70 xz_errno=0`
  - `wake_on=1 wake_ready=1`
- M33 串口：
  - `audio_playback_probe_cmd` 返回 `sound0 -> found`

剩余风险：

- `sound0` 已注册并可被 `audio_playback` 找到，但真实平台 TTS 语音是否已经从扬声器完整播出，还需要现场说话触发一次 `stt -> llm -> tts` 后听感确认。
- 官方小智长期路线仍建议补 Opus 编解码；当前为 `pcm_s16le` 兼容路线，优先打通完整闭环。

## 28. 2026-06-16 小智板端 ASR 已打通，剩余集中在 TTS 下行/播放

本轮关键结论：

1. WiFi 不再是当前问题：
   - `m55qa_status` 稳定显示 `saved=1 auto=1`、`wlan=1 ready=1`、`ip=192.168.3.32`。
   - 小智 WebSocket 稳定显示 `xz_ws=1 xz_stage=70 xz_errno=0`。
2. M33 内置干净 PCM 探针已经能走到平台 ASR：
   - `m33qa_xz_probe` 从 M33 共享内存连续发布 4 段 16 kHz mono S16LE PCM。
   - CM55 状态里 `xz_last` 增长，例如 `193/370560`。
   - M33 串口能看到平台 ASR 文本，例如 `asr text: 不知道。`。
3. PC 对照验证平台不是瓶颈：
   - 同一 URL、同一 scoped token、同一 `Protocol-Version: 3`、同一 `pcm_s16le` raw PCM 方式，PC 测试返回完整 `stt -> llm -> chat -> tts start -> binary PCM frames -> tts stop`。
   - 这说明平台中转站的 ASR/LLM/TTS 是通的。

本轮修正：

1. CM55 上行 PCM 不再额外加 4 字节本地 v3 wrapper，直接用 WebSocket binary 发送 raw `pcm_s16le`。
2. M33->M55 IPC 不再被桥接线程吞掉共享 PCM，非控制消息转交 `voice_service_handle_ipc_message()`。
3. 共享 PCM 在 `xiaozhi_listening_active` 时也会被接收，适配 `m55qa_capture_on + m33qa_xz_probe` 这种无人现场 QA。
4. 对非 JSON 的 WebSocket text payload 做保护：
   - 像 PCM 的 payload 走音频路径。
   - 非 JSON 非 PCM 不再发给 M33 当 `TTS_REQUEST`，避免 LCD/串口出现乱码回复。

下一步只盯一个问题：

- 平台已经能返回 TTS binary，但板端还没稳定证明 `CM55 WebSocket callback -> MSG_TYPE_TTS_AUDIO -> M33 audio_playback_write -> sound0` 全链路。
- 后续不要再回退查 WiFi 扫描、密码、WHD 资源；除非 `m55qa_status` 里 `wlan/xz_ws` 明确掉线。

## 26. 2026-06-15 LVGL 字库与小智“思考中”兜底

现场症状：

1. LCD 小智区域会长时间停在“正在思考”。
2. 部分中文显示为方框字。

本轮修正：

1. `applications/xiaozhi_ui_state.c` 增加 UI 状态超时兜底：
   - `XIAOZHI_UI_THINKING` 超过约 `20 s` 未收到平台 TTS/文本回复时，回到 `XIAOZHI_UI_READY`，提示“未收到回复，请重试”。
   - `XIAOZHI_UI_SPEAKING` 超过约 `30 s` 未收到结束事件时，回到 `XIAOZHI_UI_READY`。
2. `applications/rehab_wifi_font.c` 将自定义 18px 字体的 `.fallback` 挂到已启用的 `lv_font_simsun_16_cjk`：
   - 常用 UI 字符仍走小型自定义字体。
   - 自定义字体没覆盖到的中文优先用系统 CJK fallback，避免继续出现大量方框字。
   - 这比把所有动态回复都塞进自定义字体更省 M55 空间。

验证结果：

1. M55 构建通过，最新尺寸约 `text=1407424 data=81508 bss=4528996`。
2. 使用 `program_with_resources.bat` 烧录，应用和 `whd_resources_all.bin` 都写入 100%。
3. 串口 `m55qa_status` 复测到稳定态：
   - `saved=1 auto=1`
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `wake_on=1 wake_ready=1`
   - `lvgl_flush` 增加且 `lvgl_last=0`

注意：

- COM4 当前是 M33 shell。M55 内部新增的 finsh 命令不会直接出现在 COM4；板端 M55 状态仍以 M33 侧 `m55qa_status` 的 IPC 快照为准。
- 若复位后短时间看到 `xz_stage=80 xz_errno=-13` 或 `lvgl_flush=0`，先等自动连接/刷新线程恢复，再以第二轮 `m55qa_status` 判断，不要立即回退到 WiFi 扫描问题。

## 27. 2026-06-15 小瑞唤醒与回应语音边界

目标体验：

1. 用户说“小瑞”。
2. LCD/LVGL 切到“我在听”，开始录音。
3. 静音/低音量一段时间后自动停止录音，切到“正在思考”。
4. 平台返回 TTS 音频时，M33 `sound0` 扬声器播放。

本轮修正：

1. M55 唤醒词对外统一为“小瑞”：
   - Edge Impulse 后端内部仍可返回 `xiaorui`。
   - Infineon DEEPCRAFT fallback 不再把用户交互显示成 `Okay Infineon`，而是同样映射到“小瑞”。
2. M55 唤醒后按小智 WebSocket 协议先发送：
   - `listen.detect`，`text` 为“小瑞”。
   - 随后 `listen.start`，`mode` 为 `auto`。
3. 明确撤掉本地算法“人声”作为唤醒回应：
   - 现场听感反馈为杂音，不能作为用户回应。
   - `audio_playback_voice_cmd` 只能用于扬声器通路 QA，不能接入正式唤醒回应。
   - 真正的“我在”或回答音色必须来自小智/平台 TTS 音频，或后续准备经过听感验证的小体积真实提示音资源。

官方依据：

- Espressif 小智组件文档说明小智是双向流式语音/文本组件，支持 WebSocket、MQTT+UDP、OPUS/G.711/PCM，并提供离线唤醒词上报 API。
- 小智 WebSocket 协议文档说明设备侧 `listen` 消息包含 `detect/start/stop`，`detect` 表示本地唤醒检测触发。

验证结果：

1. M55 构建通过，最新尺寸约 `text=1407424 data=81508 bss=4528996`。
2. M33 构建通过，最新尺寸约 `text=286892 data=16076 bss=310744`。

待现场验证：

1. 烧录 M55 后，说“小瑞”，确认 LCD/LVGL 进入“我在听”。
2. 继续问一句清晰问题，确认状态顺序为“在线待唤醒 -> 我在听 -> 正在思考 -> 正在回答/在线待唤醒”。
3. 若平台 TTS 仍无声，优先看是否收到 `tts start/sentence_start/stop` 和 `MSG_TYPE_TTS_AUDIO`，再查 M33 播放链路。

## 28. 2026-06-16 小智官方 Opus/WebSocket v3 二进制帧修正

本轮根因：

1. 小智官方 WebSocket 例程的音频主路径是 Opus，不是裸 PCM。
2. 协议版本 3 的二进制帧也不是裸 Opus，而是：
   - `type=0`
   - `reserved=0`
   - `payload_size` 使用大端 `uint16_t`
   - 后面才是 Opus payload
3. 之前把 `hello.audio_params.format` 改为 `opus` 后，M55 上行仍直接发送 60ms PCM，协议字段和真实 payload 不一致，平台不会把它当有效语音处理。
4. 随后只补 Opus 解码还不够；若下行服务器返回 v3 binary，M55 也必须先剥掉 4 字节 v3 头，再把 payload 交给 Opus decoder。

本轮修正：

1. `applications/xiaozhi_opus_decoder.c/.h` 在原有解码器基础上增加本地 Opus encoder：
   - 16 kHz
   - mono
   - 60 ms / 960 samples
   - `OPUS_APPLICATION_AUDIO`
   - bitrate 约 24 kbps
   - complexity 降为 0，优先保证 M55 实时稳定。
2. `applications/voice_service.c` 上行发送链路改为：
   - 先攒满 60ms PCM。
   - 调用 `xiaozhi_opus_encoder_encode()` 编成 Opus。
   - 发送前补官方 v3 头 `00 00 len_hi len_lo`。
3. `applications/voice_service.c` 下行接收链路改为：
   - 收到 binary 后识别 v3 头。
   - 若头合法，剥掉 4 字节头后再 Opus decode。
   - 解码后的 PCM 再通过 `MSG_TYPE_TTS_AUDIO` 交给 M33 `sound0` 播放。
4. `VOICE_DETECT_THREAD_STACK` 从 16 KB 提到 64 KB：
   - 避免 Opus encode 在 `voice_det` 线程里吃栈导致 M55 voice status 停止刷新。
   - 不在 `voice_service_init()` 里预热 encoder，改为发送时懒初始化，避免启动路径卡死。

验证结果：

1. M55 构建通过：
   - `text=1629104 data=81508 bss=4529020`
2. 使用 `program_with_resources.bat` 烧录通过：
   - M55 `rtthread.hex` 写入约 `1712128 bytes`
   - `whd_resources_all.bin` 写入约 `466944 bytes`
3. 复位后串口 `m55qa_status` 可见稳定态：
   - `saved=1 auto=1`
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `wake_on=1 wake_ready=1`
   - `lvgl_flush` 持续增加
4. `m55qa_capture_on/off` 后，M55 不再卡死，状态继续刷新。
5. 上行字节数已从 PCM 量级变成 Opus 量级：
   - 例：`xz_last=153/27387`
   - 这表示 153 帧实际只发送约 27 KB Opus，而不是 153 * 1920B 的裸 PCM。

当前边界：

1. 本轮现场/远程环境没有清晰人声，板端仍只看到 `xz_rx=3/0`，即有 hello/listen 控制文本，但未收到平台 TTS binary。
2. 这不能再判为 WiFi 问题：WiFi、token、websocket、上行 Opus 发送都已经有串口证据。
3. 下一步 QA 应让现场靠近麦克风说清晰问题，或在 PC 侧准备可用的 `opus.dll/ffmpeg` 后，用官方 v3 Opus 包做云端 smoke test。
4. 若清晰语音后仍无 `xz_rx` binary，应优先查平台 relay 的 Opus ASR 日志，而不是回退到 WiFi 扫描或资源固件方向。

## 29. 2026-06-20 小智打通到 M33 扬声器后的当前边界

本轮已确认：

1. 这轮主线按官方小智 WebSocket v1/Opus 走：
   - `Protocol-Version: 1`
   - `hello.version=1`
   - `audio_params.format=opus`
   - 16 kHz / mono / 60 ms
   - WebSocket binary frame 为 raw Opus payload
2. WiFi、token、WebSocket 不是当前主 blocker：
   - `saved=1 auto=1 storage=0`
   - `wlan=1 ready=1`
   - `xz_ws=1`
   - `xz_stage=70`
   - `xz_errno=0`
   - token 长度为 `442`
3. 手动 QA 流程已修正为官方手动模式：
   - `m55qa_capture_on` 发 `listen/start`，`mode=manual`
   - `m55qa_capture_off` 发 `listen/stop`，`mode=manual`
4. `VOICE_CTRL_STOP_CAPTURE` 必须先停止 CM55 `mic0`：
   - 否则 shell 可能显示 stop 命令已返回，但后台采集/语音处理还在继续，表现为 LVGL 一直“正在思考”或后续命令 pending。
5. 内置 QA `m33qa_xz_probe` 已经证明平台回包和 M33 播放链路至少通了一次：
   - M55 上行 Opus 例：`xz_last=180/32220`
   - M33 下行日志：`tts audio rx total=320`
   - M33 播放日志：`audio_playback Started`、`tts audio write chunk=...`

当前还没彻底收尾的点：

1. 长 `m33qa_xz_probe` 后再发 `m55qa_capture_off`，仍可能看到 `tx_pending=1`。
2. 这更像是 M33/M55 IPC 在 TTS 回放/status 发布期间的队列压力，不是 WiFi 资源、SSID、密码、token 或基础 WebSocket 连接问题。
3. `m55qa_xz_reconnect ret=0` 只表示异步 reconnect worker 已经排队，不表示已经连接成功；必须继续看 `m55qa_status` 里的 `xz_ws/xz_stage/xz_errno`。

下一步建议：

1. 不要再回到 WiFi 扫描/资源固件方向，除非 `wlan=0` 或 `xz_stage` 明确掉线。
2. 优先把 TTS 回放时的 M55->M33 发布和 M33->M55 stop/control 分流或限流，避免 TTS 下行期间控制消息被 IPC 队列拖住。
3. 真机用户路径仍以 CM55 本地 mic 为主，`m33qa_xz_probe` 是确定性 QA 工具，会比真实 mic 路径更容易压爆 IPC。

## 30. 2026-06-20 小智当前真实进展：官方 M55 mic 路径能 start/stop，TTS 还需限流收尾

本轮结论：

1. 不要再把 WiFi/token 当主 blocker：
   - `saved=1 auto=1 storage=0`
   - `wlan=1 ready=1`
   - `ip=192.168.3.32`
   - `xz_ws=1`
   - `xz_stage=70`
   - `xz_errno=0`
   - `token_len=442`
2. 当前官方主线是 CM55 本地麦克风：
   - `CM55 mic0 -> Opus -> XiaoZhi WebSocket -> platform -> M33 TTS audio`
   - 不是 `M33 PCM -> M55 -> XiaoZhi`。
3. `m33qa_xz_probe` 已经证明平台和扬声器链路有进展：
   - M33 串口出现过 `tts audio rx total=640`
   - `audio_playback Started`
   - `tts audio write chunk=...`
4. 但 `m33qa_xz_probe` 同时会给 IPC/TTS/status 造成很大压力，不能作为产品路径继续硬推。

本轮修改：

1. M55 `m55qa_status` 里的 `probe_or_bridge` 临时承载桥接线程诊断：
   - `loops`
   - `consumed`
   - `last_ret`
   - `phase`
2. `xz_bridge` 栈从 16 KB 提到 32 KB，并增加轻量心跳日志。
3. `voice_svc` 栈从 16 KB 提到 24 KB，`xz_stop` 线程栈从 4 KB 提到 8 KB。
4. `m33qa_xz_probe` 默认缩成约 3 秒短样本，原长样本改为 `m33qa_xz_probe full`。
5. M55 默认忽略 M33 PCM probe 作为 XiaoZhi 上行音频，避免把调试 PCM 流混进官方 mic0 主线。
6. TTS pending 处理从一次 drain 全部改为单包节流，避免语音服务线程长时间忙于下行音频。

验证结果：

1. M55 构建通过：
   - `text=1645224 data=68744 bss=4541560`
2. 烧录通过：
   - M55 `rtthread.hex` 写入 `1716224 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
3. 复位后 `m55qa_status` 健康：
   - WiFi 自动连接成功
   - token 不需要重新输入
   - WebSocket 已连接
4. 不走 M33 probe 的真实 CM55 mic 控制面通过：
   - `m55qa_capture_on` 得到新 `voice_ack cmd=1 result=0`
   - `m55qa_capture_off` 得到新 `voice_ack cmd=2 result=0`
   - 结束后 `tx_pending=0`

仍未完全解决：

1. 完整自然语音问答和完整扬声器回复还未稳定闭环。
2. TTS 下行期间仍需要继续做 IPC/播放限流，避免状态刷新或控制消息被挤压。
3. 下一步优先做 TTS 下行发布和控制消息分流/限流，不要回退到 WiFi 扫描、token 配置或资源固件方向。

## 31. 2026-06-22 M33 QA probe 已节流，后续不要把 probe 队列压力误判为 WiFi/token

本轮结论：

1. 本轮没有改 M55/WiFi 源码；只修了 M33 QA 工具 `m33qa_xz_probe`。
2. WiFi/token/WebSocket 基线仍然健康：
   - `saved=1 auto=1 storage=0`
   - `wlan=1 ready=1`
   - `ip=192.168.3.32`
   - `xz_token=1 token_len=442`
   - `xz_ws=1`
   - `xz_stage=70`
   - `xz_errno=0`
3. `m33qa_xz_probe` 现在默认 100 ms/帧，遇到 M33->M55 IPC 队列满/超时会 150 ms 退避重试，避免 QA 工具把 `m55qa_capture_off` 挤在队列后面。
4. 这不改变产品路径。产品路径仍然是：
   - `CM55 mic0 -> Opus -> XiaoZhi WebSocket/platform -> M33 speaker`
   - `m33qa_xz_probe` 只是确定性 QA 工具。

验证结果：

1. 1200 ms probe：
   - `m33qa_xz_probe 1200` 发完 20 个 1920B 包，共 `38400` bytes。
   - M33 日志：`retries=0 tx_pending=0`。
   - `m55qa_capture_off` 收到新 `voice_ack cmd=2 result=0`。
2. 3000 ms probe：
   - `m33qa_xz_probe 3000` 发完 50 个 1920B 包，共 `96000` bytes。
   - M33 日志：`retries=0 tx_pending=0`。
   - `m55qa_capture_off` 收到新 `voice_ack cmd=2 result=0`。
   - M33 收到平台下行音频：`tts audio rx total=1280`，并出现 `tts audio write chunk=...`。
   - 最终状态：`tx_pending=0`、`xz_ws=1`、`xz_stage=70`、`xz_errno=0`、`xz_last=183/32757`、`xz_rx=5/0`。

仍需注意：

1. 一次 1200 ms 测试后曾出现 `xz_ws=0 xz_stage=80`，手动 `m55qa_xz_reconnect` 后恢复到 `xz_ws=1 xz_stage=70 xz_errno=0`；后续 3000 ms 测试最终保持连接。
2. 这说明下一层仍要盯 XiaoZhi session stop/reconnect、平台事件和 STT/TTS 解析，不要回头重做 WiFi 扫描、token 或资源固件。
3. 当前状态快照里 `srv_stt/srv_tts` 没增长，但 M33 已收到二进制下行音频；下一步要查平台 event 日志和板端 server event 解析。

推荐下一步：

1. 用真实 CM55 mic0 做人工语音 QA，观察 `server event type=stt/tts/error`、`srv_stt`、`srv_tts`、`xz_rx text/binary`、`tts_fwd` 和 M33 `tts audio rx/write`。
2. 如果 stop 后 WebSocket 再次掉到 `stage=80`，优先修 session stop/reconnect 逻辑。
3. 只有当 `wlan=0`、`token_len=0`、或 `xz_ws=0` 持续不能 reconnect 时，才回到 WiFi/token 方向。
