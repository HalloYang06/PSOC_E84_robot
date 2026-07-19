# Edgi-Talk M55 端侧 AI Demo 教程

这份教程默认你还不熟悉 AI 部署。目标不是让你一次学完 TensorFlow、CMSIS-NN 和 PSoC Edge，而是先把第一条最小链路跑通：**M55 上有一段模型代码，输入一组特征，输出一个分类结果，串口能看到结果，LED 还在闪。**

## 1. 什么是端侧 AI

端侧 AI，就是模型不放在云端服务器，而是直接跑在设备上。对外骨骼机械臂来说，这很重要：

- 延迟低：动作意图、危险状态不能等云端返回。
- 离线可用：实验室、室外、弱网环境也能运行。
- 隐私更好：原始传感器数据不一定需要上传。

但端侧设备资源有限，所以模型要小，计算要省，内存要可控。

## 2. CMSIS-NN、TFLM、MTB ML 分别是什么

你可以先记住这个关系：

```text
传感器数据 -> 特征 -> 模型推理 -> 分类/回归结果 -> 控制策略
```

不同软件栈负责不同层：

- CMSIS-NN：Arm Cortex-M 上的神经网络算子优化库，擅长 int8 卷积、全连接、softmax 等底层计算。
- TensorFlow Lite Micro：嵌入式模型解释器，负责加载 `.tflite` 模型、管理 tensor arena、调用算子。
- Infineon MTB ML：英飞凌官方机器学习部署路线，后续可以结合 TFLM、Ethos-U55、NNLite 和 profiling 工具。

第一版 demo 不拉 TFLM，是为了减少变量。我们先把“输入、推理、输出、串口验证”这条链路跑通。

## 3. 这个 demo 做了什么

当前 demo 模拟了四个外骨骼传感器特征：

- `joint_angle_deg`：关节角度
- `joint_velocity_dps`：关节角速度
- `load_percent`：负载或受力百分比
- `emg_level`：肌电或意图强度的简化特征

输出四个类别：

- `idle`：静止或无明显动作
- `assist`：用户有主动运动意图，设备可辅助
- `resist`：反向或阻力状态
- `unsafe`：高负载、高速度或高风险状态

这些不是正式医学/控制模型，只是为了让你理解端侧推理流程。正式外骨骼模型需要采集真实数据、训练、量化、验证和安全评估。

## 4. 工程结构

关键文件：

```text
applications/main.c
applications/edge_ai/edge_ai_app.c
applications/edge_ai/edge_ai_exo_model.c
applications/edge_ai/edge_ai_exo_model.h
tests/edge_ai_model_test.c
docs/CHANGELOG.md
docs/board-notes.md
```

分层思路：

- `main.c`：系统入口，负责 LED 心跳和周期调用 demo。
- `edge_ai_app.c`：RT-Thread 展示层，准备模拟输入并打印结果。
- `edge_ai_exo_model.c`：纯 C 推理核心，不依赖 RT-Thread，方便 PC 测试。
- `tests/edge_ai_model_test.c`：主机侧测试，验证模型核心行为。

## 5. int8 小模型是什么意思

MCU 上常用 int8 模型，因为：

- int8 占内存少。
- int8 运算比 float 更适合 MCU/NPU。
- CMSIS-NN、Ethos-U55 等都重点优化 int8。

本 demo 使用 int8 特征和整数打分。它不是训练出来的模型，而是一个教学用的小型线性分类器。你可以把它理解为“模型雏形”：输入经过一组权重和偏置，得到每个类别的分数，分数最高的类别就是输出。

## 6. 如何验证推理核心

在 PC 上运行主机测试：

```powershell
gcc -std=c99 -Wall -Wextra -Iapplications/edge_ai tests/edge_ai_model_test.c applications/edge_ai/edge_ai_exo_model.c -o build/edge_ai_model_test.exe
.\build\edge_ai_model_test.exe
```

期望看到：

```text
PASS idle window: idle ...
PASS assist window: assist ...
PASS resist window: resist ...
PASS unsafe window: unsafe ...
```

这个测试不需要开发板。它证明推理核心在逻辑上能把四组样例分到预期类别。

## 7. 如何编译固件

推荐先用 RT-Thread Studio 编译。如果用命令行，确认工具链路径是 RT-Thread Studio 自带 GCC 13.3：

```text
F:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin
```

本工程 `rtconfig.py` 里有两个容易混淆的点：

- `DEVICE` 里的 GCC 编译参数已经改为 `-mcpu=cortex-m55`，因为当前固件实际运行在 M55。
- `CPU` 仍保留为 `cortex-m7`，这是 RT-Thread 用来选择 `rt-thread/libcpu/arm/<CPU>` 目录的名字。当前工程自带 RT-Thread 里没有 `cortex-m55` 目录，原 BSP 也是复用 `cortex-m7` 的上下文切换和中断桩代码。如果贸然改成 `cortex-m55`，链接阶段会找不到 `rt_hw_interrupt_disable()`、`rt_hw_interrupt_enable()` 等函数。

所以第一版采用“编译目标按 M55，RT-Thread libcpu 选择沿用现有 BSP”的组合。等后续 BSP 或 RT-Thread 提供 M55 专用 libcpu，再单独迁移。

## 8. 烧录后应该看到什么

串口应看到类似：

```text
Hello RT-Thread
It's cortex-m55
[edge_ai] demo init: simulated exoskeleton features, int8 tiny model
[edge_ai] labels: idle / assist / resist / unsafe
[edge_ai] sample=0 angle=4 vel=2 load=5 emg=3 -> idle ...
[edge_ai] sample=1 angle=28 vel=34 load=38 emg=30 -> assist ...
[edge_ai] sample=2 angle=-22 vel=-30 load=44 emg=18 -> resist ...
[edge_ai] sample=3 angle=70 vel=92 load=92 emg=86 -> unsafe ...
```

绿灯应继续闪烁。绿灯闪烁说明 RT-Thread 主循环没有被 AI 推理卡死。

## 9. LVGL 状态屏怎么看

本工程现在可以把 AI 结果显示到板载 MIPI DSI 屏上。UI 是单独一层，放在 `applications/ui/`，不放在 `applications/edge_ai/`。两层之间没有互相调用模型细节：`edge_ai_online_app.c` 只把最后一次在线推理结果写入 `edge_ai_ui_state` 快照，`applications/ui/edge_ai_lvgl_app.c` 只读取快照并刷新 LVGL 控件。

打开的关键编译宏在 `.config` 和 `rtconfig.h` 中：

```text
BSP_USING_LCD
COMPONENT_MTB_DISPLAY_tl043wvv02
BSP_USING_LVGL
USING_LVGL
BSP_USING_SOFT_I2C1
```

烧录后，屏幕应显示 `Edgi AI` 状态页。M33 producer 还没发布共享块时，状态会是 `waiting producer`；有新窗口后，会显示 classifier、label、score、seq 和 channel 数。串口仍然保留 `[edge_ai]` / `[edge_ai_online]` 输出，绿灯仍然作为心跳。

触摸控制器当前只作为可选输入初始化。如果 `ST7102` 或 `i2c1` 没准备好，日志会出现 `[lvgl] touch init skipped...`，屏幕显示不应因此 assert。这样做是为了先验证 LCD + UI + AI 状态链路，再单独排查触摸 I2C。

## 10. 后续怎么接真实模型

后续不要推倒重来。保持这个接口：

```c
int edge_ai_exo_model_run(const edge_ai_exo_features_t *features, edge_ai_exo_result_t *result);
```

演进路线：

1. 把 `edge_ai_app.c` 的模拟输入换成 IMU/力传感器/编码器采样。
2. 用 Python 训练一个小模型，并做 int8 量化。
3. 把手写模型替换成 TFLM `.tflite` 推理。
4. 用 Infineon MTB ML 做 profiling，评估是否需要 Ethos-U55 或 NNLite 加速。

每一步都要保留串口可观测结果。嵌入式开发里，“看得见”非常重要。

## 11. 常见问题

### 为什么不一开始就用 TFLM？

TFLM 更接近正式部署，但第一步会引入更多问题：C++ 编译、模型转换、tensor arena、算子注册、内存布局。先用小模型跑通流程，更容易定位问题。

### 为什么不启用 HyperRAM？

当前 demo 很小，内部 SRAM 足够。HyperRAM 涉及 SMIF 初始化和 cache coherency，后续模型变大再启用。

### 这个模型能直接控制外骨骼吗？

不能。它只是教学 demo。真实外骨骼控制需要严格的数据采集、模型验证、安全策略、异常保护和机械控制闭环。

### CMSIS-NN 已经用上了吗？

本工程已把 BSP 自带 CMSIS-NN 的最小源码集合纳入构建，并准备好 include path。第一版业务推理核心仍保持纯 C，便于教学和测试。后续接 TFLM 时，CMSIS-NN 会作为优化算子 backend 更自然地发挥作用。
