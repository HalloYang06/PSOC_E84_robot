# 2026-07-02 M55 TensorFlow Lite Micro 构建记录

这份记录只针对 M55 工程：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
```

不要和 `F:\ym310` 混用；`F:\ym310` 是另一个工程。

## 本轮目标

在远端最新 `M55` 分支基础上，把 intent int8 模型、TFLite Micro smoke test、Opus 依赖和 WiFi/SDIO 诊断符号合到一个能完整链接的 M55 固件里。

## 为什么先处理构建

模型部署到 M55 之前，必须先证明这些东西可以一起进固件：

```text
int8 .tflite C array
golden samples
TFLite Micro runtime
M55 shell smoke command
工程原有 WiFi/Opus 代码
RT-Thread / SCons / GCC 链接流程
```

如果固件都不能链接，后面的烧录、串口运行、实时 IMU 推理都没有基础。

## 已处理的问题

### 1. Opus 头文件缺失

构建失败现象：

```text
applications\xiaozhi_opus_decoder.c:6:10: fatal error: opus.h: No such file or directory
```

根因：

```text
最新远端代码里 xiaozhi_opus_decoder.c 已经使用 Opus API，
但当前 M55 工程没有把 Opus include 路径和 Opus 源码组件接进 SCons。
```

修复：

```text
libraries/components/opus/SConscript
libraries/components/SConscript 引入 opus/SConscript
applications/SConscript 增加 libraries/components/opus/include
```

Opus 使用固定点配置：

```text
OPUS_BUILD
FIXED_POINT=1
DISABLE_FLOAT_API
VAR_ARRAYS
```

这样更适合 MCU，避免依赖浮点 Opus API。

### 2. SDIO/MMC 诊断符号 undefined reference

构建失败现象：

```text
undefined reference to g_mmcsd_diag_core_init
undefined reference to g_mmcsd_diag_thread_started
undefined reference to g_mmcsd_diag_change_sent
undefined reference to g_mmcsd_diag_change_err
undefined reference to g_mmcsd_diag_recv_count
undefined reference to g_mmcsd_diag_power_up_count
undefined reference to g_mmcsd_diag_cmd5_before_count
undefined reference to g_mmcsd_diag_cmd5_after_count
undefined reference to g_mmcsd_diag_cmd5_last_err
undefined reference to m55_sdio_kick_change
```

根因：

```text
wifi_config_service.c 和 whd_wlan.c 引用了本地 WiFi/SDIO 调试符号，
但当前工程里只有 extern 声明和调用，没有对应定义。
官方 BSP 和 Edgi_Talk_M55_WIFI 示例中也没有这些本地诊断符号。
```

修复：

```text
rt-thread/components/drivers/sdio/mmcsd_core.c
  定义并更新 g_mmcsd_diag_* 诊断计数。

libraries/HAL_Drivers/drv_sdio.c
  实现 m55_sdio_kick_change()，
  在 WHD 等待 SDIO probe 时重新投递 mmcsd_change(sdioX->host)。
```

### 3. Tensor arena 避免压进 .bss

M55 smoke test 使用 64KB tensor arena。这个 buffer 不应该直接作为大静态数组压进 `.bss`，否则容易造成 RAM 段压力。

当前做法：

```text
intent_tflm_smoke.cpp 使用 rt_malloc_align(kTensorArenaBytes, 16)
```

也就是运行时从 RT-Thread heap 分配，并做 16 字节对齐。

## PC 契约测试

这些测试不跑真实 MCU 推理，只检查工程集成是否正确。

```powershell
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED

python -m unittest tools.test_intent_tflm_smoke_contract
python -m unittest tools.test_opus_integration_contract
python -m unittest tools.test_sdio_diag_link_contract
```

当前结果：

```text
tools.test_intent_tflm_smoke_contract: 6 tests OK
tools.test_opus_integration_contract: 4 tests OK
tools.test_sdio_diag_link_contract: 3 tests OK
```

## M55 构建命令

```powershell
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED

$env:RTT_EXEC_PATH='F:\RT-ThreadStudio\platform\env_released\env-new\tools\gnu_gcc\arm_gcc\mingw\bin'
F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

构建日志：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\build\intent_tflm_build_with_opus_sdio_diag.log
```

关键结果：

```text
LINK rt-thread.elf
arm-none-eabi-objcopy -O ihex rt-thread.elf rtthread.hex
arm-none-eabi-size rt-thread.elf

text    1705752
data      81520
bss     4531064
dec     6318336
scons: done building targets.
```

产物：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\rt-thread.elf
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\rtthread.hex
```

## 这一步说明了什么

已经证明：

```text
M55 工程能拉取远端最新代码后继续构建
Opus 依赖已经接入
SDIO 诊断 undefined reference 已解决
intent int8 模型 C array 已进入构建
golden samples 已进入构建
intent_tflm_smoke shell 命令已进入构建
最终 rt-thread.elf / rtthread.hex 可以生成
```

还没有证明：

```text
板上 TFLite Micro 推理结果正确
实时 IMU 窗口接入正确
M33/M55 实时数据链路正确
动作识别可以直接控制电机
```

## 下一步

烧录 M55 后，在 RT-Thread shell 里先跑固定样本验证：

```text
intent_tflm_smoke
intent_tflm_smoke -v
```

期望看到：

```text
[intent_tflm] ready model=22232 arena=65536 used=...
[intent_tflm] golden pass ...
```

只有板上固定样本通过以后，才继续接实时 IMU 窗口。这样问题边界清楚：先验证模型 runtime，再验证实时数据，再验证控制策略。

## 面试说法

可以这样讲：

```text
我没有把训练好的 TensorFlow 模型直接放到 MCU 上就接电机控制，而是先做了分层验证。
PC 上先验证 float32/int8 TFLite 精度，再导出 int8 模型和 golden samples。
M55 侧先用 TFLite Micro 跑固定 golden samples，确认模型、量化参数、tensor shape、算子兼容和 runtime 输出一致。
同时我处理了嵌入式工程集成问题，包括 Opus 固定点库接入、SCons include/source 路径、SDIO 诊断符号链接，以及 tensor arena 的 heap 分配。
等 M55 固件能完整链接并在板上 smoke 通过后，才继续接实时 IMU 窗口和 M33 安全控制状态机。
```
