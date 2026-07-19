# Edgi-Talk PSoC Edge E84 板级笔记

这份笔记来自 `docs/board/PSOC-Edge-E84` 目录下四份 PDF 和当前 RT-Thread Studio 工程配置。目的不是复述手册，而是把“部署端侧 AI 时必须知道的硬件事实”整理出来。

## 1. MCU 和 AI 能力

PSoC Edge E84 是面向端侧 AI 的多核 MCU。数据手册中和 AI 部署最相关的是：

- Arm Cortex-M55，最高 400 MHz，带 Helium DSP、FPU、I/D cache。
- Arm Cortex-M33，最高 200 MHz，低功耗域，带 NNLite NPU。
- Arm Ethos-U55 NPU，最高 400 MHz，适合后续跑更正式的神经网络加速。
- 片上存储包含 256 KB ITCM、256 KB DTCM、系统 SRAM、RRAM 等。

对第一版 demo 来说，我们只用 M55 CPU 和内部 SRAM。这样能绕开 U55、NNLite、HyperRAM、TFLM 等更多变量，先证明“固件能跑推理”。

## 2. 外部存储

Core 原理图里看到：

- QSPI Flash：`S25FS128SAGMFI101`
- HyperRAM/PSRAM：`S70KS1283GABHV020`

当前生成配置里能看到 `m55_hyperram` 映射到 SMIF1 相关 memory location，但 `.config` 里 `BSP_USING_HYPERAM` 仍然是关闭状态。

第一版 demo 不打开 HyperRAM。后续如果模型变大，常见做法是：

- 模型权重放 QSPI Flash 或外部 XIP 区。
- tensor arena、较大的中间 buffer 放 HyperRAM。
- 注意 cache coherency：DMA 或 NPU 访问外部内存时，CPU cache 需要 clean/invalidate。

## 3. 板载外设

Basic/Core 原理图中和后续外骨骼项目相关的外设：

- IMU：`LSM6DS3TR-C`
- 湿度传感器：`AHT20`
- 音频 codec：`ES8388`
- Wi-Fi/BT：`CYW55512`
- 屏幕：MIPI DSI 800x480 触摸屏
- 存储：TF 卡槽、QSPI Flash、HyperRAM
- 三个用户 LED：
  - 红灯：`P16_7`
  - 绿灯：`P16_6`
  - 蓝灯：`P16_5`

当前 `applications/main.c` 使用 `GET_PIN(16, 6)`，也就是绿灯。第一版 demo 保留绿灯作为心跳。

## 4. LCD、触摸和 LVGL 接入记录

本次只启用板载 800x480 MIPI DSI LCD 做 AI 状态显示，UI 层放在 `applications/ui/`，不放在 `applications/edge_ai/`，也不参与模型推理。相关 BSP 宏为 `BSP_USING_LCD`、`COMPONENT_MTB_DISPLAY_tl043wvv02`、`BSP_USING_LVGL` 和 `USING_LVGL`。

触摸控制器使用 BSP 里的 ST7102 port，当前按 SDK 例程配置为软件 I2C1：

```text
BSP_SOFT_I2C1_SCL_PIN = 25
BSP_SOFT_I2C1_SDA_PIN = 107
ST7102 reset = GET_PIN(17, 3)
ST7102 irq   = GET_PIN(17, 2)
```

这组触摸引脚还需要后续硬件实测确认。为了避免触摸 I2C 未就绪时影响屏幕显示，`lv_port_indev.c` 现在会跳过触摸初始化并打印提示，不再直接 assert。

显示驱动的 GFXSS 路径使用 baremetal 编译条件。工程里的 `_BAREMETAL` 需要保持为 `1`，否则 `viv_dc_os.h` 会走 FreeRTOS 分支并要求 `FreeRTOS.h`，导致 M55 RT-Thread 工程编译失败。

## 5. BSP 状态

当前工程目录名和 BSP 目录仍叫 `TARGET_APP_KIT_PSE84_EVAL_EPC2`，这是官方 PSoC Edge E84 Evaluation Kit 的命名。但从原理图和生成 pin 配置看，这个工程已经包含 Edgi-Talk 的实际资源映射。

需要特别注意的差异：

- `bsp.mk` 元数据里仍有 `CYW55513IUBG`。
- Edgi-Talk 原理图上的无线芯片是 `CYW55512`。

这对当前 M55 CPU 推理 demo 没影响，因为我们不启用 Wi-Fi/BT。后续如果使用无线通信，一定要重新核对 BSP 组件、固件、SDIO、BT UART 和电源控制脚。

## 6. 启动链路

README 说明启动顺序是：

1. Secure M33
2. Non-secure M33
3. M55 application

因此第一版 demo 不碰 M33 工程、不碰安全启动、不改分区，只改 M55 应用层。烧录时仍要保证 M33 侧已经正确打开并启动 M55。

## 7. 对 AI 部署的建议

推荐分三步走：

1. M55 CPU + int8 小模型 demo：证明 RT-Thread 任务、串口、LED、推理循环可跑。
2. TFLM `.tflite` 模型：接入真实训练/量化模型格式。
3. Infineon MTB ML + Ethos-U55/NNLite：做 profiling、性能优化和加速部署。

不要一开始就把所有东西打开。嵌入式 AI 调试最怕变量太多：模型、内存、cache、NPU、外设、RTOS 任务同时出问题时，很难判断是哪一层坏了。
