# 嵌入式端侧 AI 知识体系与工程路线图

这份文档写给刚开始接触机器学习、但正在做嵌入式项目的人。目标不是把所有 AI 名词背下来，而是建立一张可用于项目和求职的地图：知道每个概念属于哪一层，知道工程里真正要交付什么，也知道企业招聘时为什么会要求这些技能。

当前工程是 Edgi-Talk PSoC Edge E84 + RT-Thread + M55 的最小端侧 AI demo。它适合从 MCU 端 TinyML 入门：先用 IMU 数据训练小 MLP，再把模型参数部署到 M55。大模型、视觉模型、语音模型和边缘 Linux 平台也会讲，但它们不是当前 M55 第一阶段的主线。

## 1. 先分清几个概念

### AI、机器学习、深度学习、大模型

可以先用这个层级记：

```text
AI 人工智能
-> Machine Learning 机器学习
   -> Deep Learning 深度学习
      -> 大模型 / 视觉模型 / 语音模型 / 小型神经网络
```

- AI 是大概念，只要让机器表现出某种智能行为，都可以叫 AI。
- 机器学习是让程序从数据里学规则，而不是人手写所有规则。
- 深度学习是机器学习的一类，核心是多层神经网络。
- 大模型通常指参数很多、预训练数据很多、能力很泛化的模型，例如 LLM、VLM、多模态模型。
- MLP、CNN、RNN、Transformer 都是模型结构。它们可以很小，也可以很大。

你现在用的 IMU 动作识别，属于机器学习/小型深度学习；它不是大模型，但它和大模型共享一些基本概念：输入、特征、权重、推理、损失函数、训练、验证、量化、部署。

### 训练和推理

训练是在电脑或服务器上完成的：

```text
采集数据 -> 标注 -> 模型反复猜 -> 根据错误调整权重 -> 保存模型参数
```

推理是在产品运行时完成的：

```text
传感器输入 -> 预处理 -> 模型计算 -> 输出分类/检测/控制建议
```

对 MCU 来说，通常不在板子上训练模型。板子上只跑训练好的模型，也就是推理。

### 端侧 AI 和云端 AI

端侧 AI 是把模型放在设备本地运行。好处是低延迟、离线可用、隐私更好、通信成本低。代价是算力、内存、功耗都很有限。

云端 AI 是把模型放在服务器或云 GPU 上。好处是模型可以很大、更新方便、算力强。代价是依赖网络、延迟更高、隐私和成本压力更大。

嵌入式端侧 AI 关注的是：在有限资源里稳定地跑出足够好的结果。

## 2. 大模型基础知识

### 大模型到底“大”在哪里

大模型的“大”主要来自三件事：

- 参数多：模型内部有大量权重，常见 LLM 从数亿到数千亿参数不等。
- 数据多：预训练时看过海量文本、代码、图像、音频或视频。
- 计算多：训练和推理都需要大量矩阵乘法，内存带宽和算力压力很大。

大模型不是简单的“if else 很多”，而是一个巨大的函数。输入一段文本 token，它输出下一个 token 的概率分布。

### Token、Embedding、Transformer

大模型处理文字时，通常不会直接处理“汉字”或“单词”，而是先切成 token：

```text
用户输入 -> tokenizer -> token id -> embedding 向量 -> Transformer -> 输出 token 概率
```

- token：模型看到的最小文本单位，可能是一个字、一个词、一个词片段。
- embedding：把离散 token id 映射成连续向量。
- Transformer：当前大模型最常见的核心结构。
- attention：Transformer 里的关键机制，用来判断当前 token 应该关注上下文里的哪些位置。
- KV cache：推理时缓存历史上下文的 key/value，能加速生成，但会消耗内存。

大模型推理性能常用这些指标看：

- 首 token 延迟：输入后多久开始输出。
- tokens/s：每秒生成多少 token。
- 上下文长度：一次能看多长的输入。
- 峰值内存：模型权重、KV cache、中间张量占多少 RAM/VRAM。
- 功耗和温度：端侧设备不能只看速度，还要看持续运行是否降频。

### 预训练、微调、RAG

预训练是让模型先学习通用语言和知识。成本极高，一般个人和普通嵌入式团队不做。

微调是在已有模型基础上，用特定数据调整模型行为。常见方式有：

- 全参数微调：效果强，但资源要求高。
- LoRA/QLoRA：只训练少量适配参数，成本低很多。
- 指令微调：让模型更会按用户指令回答。

RAG 是 Retrieval-Augmented Generation，检索增强生成。它不一定修改模型权重，而是先从本地或云端知识库检索相关资料，再把资料塞进 prompt，让模型基于资料回答。

在工程里，RAG 很常见，因为它比重新训练大模型更容易维护。比如设备维修助手可以把产品手册、故障码、历史工单做成知识库。

### 大模型和嵌入式的关系

MCU 级别，例如 Cortex-M55，通常不适合跑真正的大语言模型。M55 适合跑：

- IMU 动作分类
- 关键词唤醒
- 小型异常检测
- 简单手势识别
- 小 MLP/CNN/传统 ML

更大的端侧模型通常放在：

- 手机 SoC：NPU/GPU/CPU 混合推理
- AI PC：NPU/GPU/CPU
- NVIDIA Jetson：TensorRT、CUDA、DeepStream
- Cortex-A + NPU 的边缘 Linux 板卡
- 工业网关、车载计算盒

所以你要建立一个分层意识：

```text
MCU TinyML：小模型、低功耗、硬实时、C/C++、RTOS
边缘 Linux AI：视觉/语音/小语言模型、Python/C++、ONNX/TensorRT/OpenVINO
云端大模型：训练/微调/RAG/Agent/服务化/GPU 集群
```

嵌入式端侧 AI 工程师不一定要训练大模型，但需要理解大模型如何被压缩、量化、部署，以及什么时候不该把大模型塞进小设备。

## 3. MLP、PyTorch、TensorFlow、TFLM 的区别

MLP 是一种模型结构。它通常长这样：

```text
输入特征 -> 全连接隐藏层 -> 激活函数 -> 输出类别
```

PyTorch 和 TensorFlow 是训练与建模框架。你可以用它们训练 MLP、CNN、Transformer，也可以导出模型给端侧运行时。

TFLM 是 TensorFlow Lite Micro，是 MCU 上的推理运行时。它负责把 `.tflite` 模型跑起来，不负责训练。

可以这样记：

```text
MLP：模型长什么样
PyTorch/TensorFlow：电脑上怎么训练模型
TFLite/ONNX/CoreML：模型交换或部署格式
TFLM/CMSIS-NN/ExecuTorch/ONNX Runtime：设备上怎么跑模型
```

当前工程第一阶段先用纯 Python 小 MLP，是为了让你看清楚：

```text
CSV 数据 -> 窗口特征 -> 权重和 bias -> C 数组 -> M55 推理
```

以后再接 TFLM 时，你就不会把 `.tflite`、tensor arena、operator resolver、量化参数当成黑盒。

## 4. 嵌入式端侧 AI 的完整工程链路

企业项目里，AI 不是只有模型文件。完整链路通常是：

```text
需求定义
-> 传感器和硬件选型
-> 数据采集
-> 数据标注
-> 数据清洗
-> 特征/预处理
-> 模型训练
-> 模型评估
-> 压缩和量化
-> 端侧运行时集成
-> 固件/应用集成
-> 性能、功耗、内存验证
-> 可靠性和安全验证
-> OTA/版本管理/现场监控
```

初学者容易只盯着“训练准确率”，但企业真正关心的是：

- 数据是不是代表真实场景。
- 错误分类会不会导致危险行为。
- 模型能不能在目标芯片上按时跑完。
- RAM/Flash 是否够。
- 功耗和温升能不能接受。
- 量化后准确率掉多少。
- 异常输入时系统是否有保护。
- 模型版本、数据版本、固件版本能否追溯。

对外骨骼、机器人、车载、工业控制这类系统，AI 输出通常不能直接等于控制输出。更稳妥的结构是：

```text
AI 识别意图/状态 -> 控制策略判断 -> 安全限幅/保护 -> 执行器输出
```

## 5. 知识体系地图

### 5.1 嵌入式基础

这是端侧 AI 的地基。招聘里即使写了 AI，很多岗位仍然优先看嵌入式基本功。

必须掌握：

- C 语言、指针、结构体、内存布局、位运算。
- C++ 基础，尤其是面向对象、RAII、模板的基本阅读能力。
- MCU 启动流程、vector table、startup、linker script。
- 中断、优先级、临界区、原子操作。
- RTOS 线程、信号量、消息队列、定时器、调度。
- UART/I2C/SPI/PWM/ADC/DMA/GPIO。
- cache、DMA coherency、内存对齐。
- Flash/RAM/stack/heap 的限制。
- J-Link/OpenOCD/RT-Thread Studio/串口日志调试。
- SCons/CMake/Makefile、交叉编译工具链。

在本工程里，对应内容包括：

- M33 启动 M55 的链路。
- RT-Thread 的 `CPU` 和 GCC `-mcpu=cortex-m55` 的区别。
- 串口输出 `[edge_ai]` 作为可观测性。
- M55 上保持 LED 心跳，证明推理没有卡死主循环。

### 5.2 信号处理和传感器

端侧 AI 大多不是直接吃“抽象数据”，而是吃传感器流。

要掌握：

- 采样率、奈奎斯特、混叠。
- 滤波：均值滤波、中值滤波、低通、高通、带通。
- 窗口：window size、step size、overlap。
- 时域特征：mean、std、min、max、range、RMS、energy。
- 频域特征：FFT、频带能量、谱峰。
- 传感器标定：零偏、尺度、坐标系、温漂。
- 同步问题：多个传感器时间戳对齐。

IMU 动作识别里，窗口特征比单点数据更重要。因为动作是一段时间里的变化，不是某一行 CSV 的瞬间值。

### 5.3 机器学习基础

先掌握这些就够做第一批端侧项目：

- 训练集、验证集、测试集。
- 标签、特征、样本、窗口。
- 分类、回归、异常检测。
- 准确率、召回率、精确率、F1、混淆矩阵。
- 过拟合、欠拟合、数据泄漏。
- 标准化、归一化。
- Logistic Regression、SVM、Random Forest、KNN。
- MLP、CNN、RNN/GRU/LSTM、Transformer 的基本用途。
- 损失函数、梯度下降、学习率、epoch、batch。

端侧项目里，模型不是越复杂越好。小模型如果能满足需求，往往更适合量产。

### 5.4 深度学习和模型压缩

端侧 AI 里常见的优化手段：

- 量化：float32 -> int8/int4，减少内存和计算量。
- 剪枝：去掉不重要的连接或通道。
- 蒸馏：用大模型教小模型。
- 算子融合：把多个操作合成更少的内核调用。
- 硬件感知训练：训练时考虑目标硬件支持的算子和量化方式。
- 后训练量化 PTQ：训练后用校准数据量化。
- 量化感知训练 QAT：训练时模拟量化误差。

MCU 上最常见的是 int8 量化。原因很直接：Flash 少、RAM 少、浮点算力有限，而 CMSIS-NN、NPU、DSP 往往对 int8 有优化。

### 5.5 部署和运行时

不同设备对应不同运行时：

- Cortex-M MCU：TFLM、CMSIS-NN、CMSIS-DSP、厂商 ML SDK。
- Arm Cortex-A / Embedded Linux：ONNX Runtime、TensorFlow Lite、OpenVINO、TensorRT、vendor NPU SDK。
- NVIDIA Jetson：TensorRT、DeepStream、CUDA、GStreamer。
- PyTorch 端侧生态：ExecuTorch，面向 mobile/edge/embedded 的 PyTorch-native 部署。
- 本地 LLM：llama.cpp、ggml/GGUF、Ollama、MLC、ExecuTorch LLM 路线。

本工程 PSoC Edge E84 的相关方向：

- M55 + Helium DSP：适合优化 DSP 和小模型推理。
- Ethos-U55：适合后续神经网络加速。
- M33 + NNLite：适合低功耗场景。
- Infineon ModusToolbox ML / DEEPCRAFT：适合走厂商推荐的模型导入、验证和部署流程。

### 5.6 系统工程能力

企业项目非常看重这部分，因为模型只是系统的一环。

要会做：

- 数据采集 SOP：谁采、采多久、动作如何定义、环境如何记录。
- 版本管理：数据版本、模型版本、固件版本对应关系。
- 可观测性：串口日志、统计计数、错误码、推理耗时。
- 性能 profiling：CPU cycles、latency、RAM、Flash、功耗。
- 异常处理：传感器断线、数据越界、模型输出不确定、低电量。
- 安全策略：AI 结果只作为建议，关键动作要有规则保护。
- 自动化测试：主机侧模型测试、固件构建测试、硬件 smoke test。
- 文档：部署步骤、常见错误、烧录现象、实验结论。

## 6. 技术栈总览

### PC 训练侧

建议学习顺序：

1. Python 基础：文件、列表、字典、函数、类、命令行参数。
2. NumPy：向量、矩阵、广播、统计。
3. pandas：读 CSV、清洗数据、分组统计。
4. matplotlib/seaborn：画波形、混淆矩阵、训练曲线。
5. scikit-learn：Logistic Regression、SVM、Random Forest、train/test split。
6. PyTorch 或 TensorFlow/Keras：训练 MLP、CNN、Transformer。
7. ONNX/TFLite：模型导出和转换。

初学者不要一开始就陷入大框架。先用纯 Python 或 NumPy 写一个小 MLP，会非常帮助你理解权重、bias、ReLU、softmax。

### MCU 固件侧

需要掌握：

- C/C++ 推理代码。
- RT-Thread/FreeRTOS/Zephyr 任一 RTOS。
- CMSIS-Core、CMSIS-DSP、CMSIS-NN。
- TensorFlow Lite Micro 的 tensor arena、operator resolver、MicroInterpreter。
- 目标芯片的 memory map、cache、DMA、时钟、功耗模式。
- SCons/CMake/Makefile 和交叉编译。
- 串口/JTAG/SWD 调试。

本工程当前路线：

```text
纯 C 小模型 -> Python 导出 C 数组 -> M55 前向计算
后续再切到 TFLM / MTB ML / Ethos-U55
```

### Embedded Linux / 边缘计算侧

如果目标是摄像头、语音、机器人、网关、Jetson，这部分很重要：

- Linux 基础、进程、线程、文件系统、systemd。
- C++、Python 混合工程。
- OpenCV、GStreamer、FFmpeg。
- ONNX Runtime、TensorRT、OpenVINO。
- CUDA/TensorRT/DeepStream，尤其是 Jetson 方向。
- Yocto/Buildroot，做产品镜像。
- Docker 适用于 Linux 边缘设备，但不适用于裸机 MCU。
- 网络和 OTA：MQTT、HTTP、gRPC、日志上传、远程升级。

### 大模型端侧侧重

如果以后做本地助手、语音交互、工业知识问答、设备诊断助手，要补：

- Transformer、attention、KV cache。
- tokenizer 和 prompt 设计。
- 量化格式：int8、int4、GGUF、AWQ/GPTQ 等。
- RAG：embedding、向量库、检索、重排、上下文压缩。
- 本地推理：llama.cpp、ExecuTorch、ONNX Runtime、TensorRT-LLM。
- 多模态：图像、语音、文本的输入输出管线。
- 可靠性：幻觉、拒答、权限、安全边界、日志审计。

注意：这条路线更偏 Cortex-A、Jetson、手机、AI PC，不是 Cortex-M55 第一阶段的重点。

## 7. 企业招聘需求怎么看

截至 2026 年，公开招聘和技术资料里，端侧 AI 岗位大致分成几类。

### 7.1 Embedded AI Engineer

典型要求：

- C/C++ 和 Python 都要会。
- 熟悉 MCU、RTOS、外设、调试。
- 能把模型部署进固件。
- 理解内存、功耗、实时性约束。
- 会 TFLite/TFLM、CMSIS-NN、ONNX 或厂商 SDK。
- 能写测试和文档。

这个岗位不是纯算法，也不是纯驱动。它要求你能把传感器、固件、模型、工具链接起来。

### 7.2 Edge AI / On-device Optimization Engineer

典型要求：

- 模型压缩、量化、剪枝、蒸馏。
- 低延迟推理和硬件加速。
- 熟悉 NPU、DSP、GPU、custom silicon。
- 会 profiling，能定位瓶颈是算子、内存拷贝、预处理还是运行时。
- 熟悉 ONNX Runtime、TensorRT、CoreML、ExecuTorch、OpenVINO 等。

Apple、Meta/PyTorch、NVIDIA、Qualcomm、机器人公司、车载公司都常见这种方向。

### 7.3 Edge Computer Vision Engineer

典型要求：

- OpenCV、图像处理、相机标定。
- CNN、YOLO、Segmentation、Tracking。
- GStreamer/DeepStream/FFmpeg。
- Jetson/TensorRT/CUDA。
- 多线程 pipeline、零拷贝、实时视频流。

这类岗位经常要求 C++ 很强，因为部署和性能优化往往在 Python 之外。

### 7.4 AI Runtime / Compiler Engineer

典型要求：

- C++、系统编程、编译器基础。
- 算子实现、图优化、内存规划。
- 量化、kernel 优化、SIMD/NPU/GPU backend。
- 熟悉 MLIR/TVM/XLA/ONNX Runtime/TensorRT/ExecuTorch 这类系统。

这是更底层、更难的方向，适合喜欢系统和性能优化的人。

### 7.5 Embedded Linux AI Engineer

典型要求：

- Linux、Yocto/Buildroot、驱动和用户态服务。
- C++/Python 工程化。
- 摄像头、音频、网络、OTA。
- ONNX/TensorRT/OpenVINO/vendor NPU SDK。
- 产品稳定性和现场问题定位。

工业、机器人、安防、车载、智能硬件里很常见。

## 8. 项目要求：怎样的端侧 AI 项目才像样

一个能打动企业的端侧 AI 项目，不是只有“我训练了一个模型，准确率 99%”。更完整的项目应该包含：

### 问题定义

要说清楚：

- 识别什么。
- 为什么必须在端侧跑。
- 目标延迟是多少。
- 内存/Flash/功耗限制是多少。
- 错误输出会造成什么后果。

### 数据闭环

要有：

- 采集脚本。
- 数据格式。
- 标签定义。
- 数据量统计。
- 训练/测试划分。
- 异常数据处理。

### 模型和评估

要有：

- 选择模型的理由。
- 特征提取方式。
- 混淆矩阵。
- 错误案例分析。
- 与基线模型对比。
- 量化前后对比。

### 端侧部署

要有：

- 固件集成位置。
- 模型参数或模型文件。
- RAM/Flash 占用。
- 单次推理耗时。
- 串口或日志输出。
- 构建和烧录步骤。

### 工程安全

要有：

- 异常输入处理。
- 传感器掉线处理。
- 低置信度策略。
- 控制输出限幅。
- 人工可复现的验证步骤。

对当前工程来说，好的下一阶段交付物是：

```text
IMU CSV 数据集
-> Python MLP 训练报告
-> C 头文件模型参数
-> M55 端 C 前向推理
-> 主机侧一致性测试
-> 固件构建通过
-> 串口输出真实动作类别
```

## 9. 针对本工程的路线图

### 阶段 0：最小 M55 AI demo

目标：

- M55 固件能跑。
- LED 心跳不断。
- 串口有 `[edge_ai]` 输出。
- `edge_ai_exo_model_run()` 接口稳定。

你已经在这个方向上建立了基础。

### 阶段 1：离线 IMU 数据闭环

目标：

- M33 采集 LSM6DS3。
- PC 保存 CSV。
- 标签包括 `idle / tilt_left / tilt_right / shake`。
- Python 训练小 MLP。
- 输出训练报告和 C 模型头文件。

这个阶段的重点不是高准确率，而是把流程跑通。

### 阶段 2：M55 上复现 Python 推理

目标：

- 用 C 实现和 Python 一致的窗口特征。
- 用导出的 `w1/b1/w2/b2` 做 MLP 前向计算。
- 主机侧测试 C 和 Python 输出一致。
- 固件侧串口输出动作类别。

这一步完成后，你就真正从“模拟 AI demo”进入“真实数据训练模型部署”。

### 阶段 3：实时采集架构

目标：

- 决定 IMU 由 M33 采集还是 M55 采集。
- 如果 M33 采集，要设计 IPC/共享内存。
- 如果 M55 采集，要移植 I2C/IMU 驱动或使用 BSP 支持。
- 建立环形缓冲区和窗口调度。

这里不能让 M33 和 M55 同时抢同一个 I2C IMU。

### 阶段 4：量化和加速

目标：

- float MLP -> int8 MLP。
- 对比量化前后准确率。
- 用 CMSIS-NN 或厂商工具加速。
- 记录推理耗时、RAM、Flash。

这一步开始接近企业里“端侧优化”的工作。

### 阶段 5：TFLM / MTB ML / DEEPCRAFT

目标：

- 用 TensorFlow/Keras 或 PyTorch 训练等价模型。
- 导出 TFLite 或厂商支持格式。
- 用 TFLM 或 ModusToolbox ML 跑起来。
- 后续评估 Ethos-U55 / NNLite。

这一步不是第一天做，因为它会同时引入模型格式、运行时、算子支持、内存规划等多个变量。

### 阶段 6：真实外骨骼信号

目标：

- 接入更真实的外骨骼传感器，例如编码器、力传感器、肌电。
- 更新 `docs/board-notes.md` 说明硬件依据。
- 更新采集 SOP。
- 加入安全控制策略。

肌电信号比 IMU 难很多，要等数据闭环成熟后再做。

## 10. 学习路线建议

### 第 1 段：嵌入式基本功

成果目标：

- 会写稳定的 C。
- 会读 linker map。
- 会用串口和调试器定位问题。
- 会写 RTOS 线程和外设驱动。

练习项目：

- UART shell。
- I2C 读传感器。
- DMA ADC 采样。
- RTOS producer/consumer。
- 环形缓冲区。

### 第 2 段：Python 数据处理

成果目标：

- 会读 CSV。
- 会画传感器波形。
- 会按标签统计数据。
- 会做窗口切片和特征提取。

练习项目：

- 把 IMU CSV 画成三轴曲线。
- 计算每个动作的 mean/std/range。
- 输出混淆矩阵。

### 第 3 段：小模型训练

成果目标：

- 理解 Logistic Regression、MLP、CNN 的差异。
- 会训练和评估分类模型。
- 会分析误分类原因。

练习项目：

- IMU 四分类。
- 关键词唤醒玩具模型。
- 电机异常振动分类。

### 第 4 段：端侧部署

成果目标：

- 会把权重导出成 C 数组。
- 会在 MCU 上实现前向推理。
- 会测延迟、RAM、Flash。
- 会做主机侧和固件侧一致性测试。

练习项目：

- Python MLP 和 C MLP 输出一致。
- float -> int8 量化。
- TFLM hello_world/sine model 移植。

### 第 5 段：工程化和产品化

成果目标：

- 会管理数据版本和模型版本。
- 会写自动化测试。
- 会做故障保护。
- 会写可交接文档。

练习项目：

- 数据采集 SOP。
- 推理日志和错误码。
- OTA 模型版本号。
- 低置信度回退策略。

### 第 6 段：大模型和边缘 Linux

成果目标：

- 理解 Transformer、RAG、量化、本地推理。
- 能在 PC/Jetson/边缘 Linux 上跑小语言模型或视觉模型。
- 能解释为什么 MCU 不适合直接跑 LLM。

练习项目：

- llama.cpp 跑一个 1B/3B 小模型。
- 本地 RAG 设备手册问答。
- Jetson 上 YOLO + TensorRT。
- ONNX Runtime 部署小模型。

## 11. 面试和作品集怎么准备

### 简历上更有价值的写法

弱写法：

```text
熟悉 AI，使用 Python 训练模型，准确率 99%。
```

强写法：

```text
基于 PSoC Edge E84 和 RT-Thread 实现 IMU 四分类端侧 AI demo：
采集 12 组 LSM6DS3 CSV 数据，按滑动窗口提取 18 个时域特征，
训练小 MLP 并导出 C 权重，在 M55 固件中规划部署接口；
提供主机测试、训练报告、混淆矩阵和 compile-only 固件验证记录。
```

企业喜欢看到你能把数据、模型、固件、验证串起来。

### 面试常问问题

你应该能回答：

- 为什么端侧 AI 不直接用大模型。
- 为什么训练在 PC 上、推理在 MCU 上。
- MLP 和 Logistic Regression 的区别。
- TFLM 和 TensorFlow 的区别。
- 什么是量化，为什么 MCU 喜欢 int8。
- 混淆矩阵怎么看。
- 数据泄漏是什么。
- 为什么高测试准确率不等于能量产。
- 如何测量单次推理耗时。
- 如果模型输出错误，控制系统如何保护。
- 如果 Flash/RAM 不够，怎么优化。
- 如果某个 TFLite 算子不支持，怎么办。

### 项目答辩时要带的证据

建议准备：

- 数据采集照片或接线说明。
- CSV 数据样例。
- 训练脚本。
- 训练报告。
- 混淆矩阵。
- 生成的 C 模型头文件。
- 主机侧测试输出。
- 固件构建输出。
- 串口运行截图。
- RAM/Flash/latency 统计。

这些东西比单纯说“我会 PyTorch”更有说服力。

## 12. 常见误区

### 误区 1：先学大模型再学端侧 AI

大模型很重要，但嵌入式端侧 AI 的地基仍然是传感器、实时系统、内存、功耗和部署。你可以了解大模型，但不要因为大模型热，就跳过嵌入式基本功。

### 误区 2：准确率越高越好

小数据集上的 100% 准确率很可能只是数据太少、测试集太像训练集。企业更关心真实场景、边界情况和失败模式。

### 误区 3：会训练就等于会部署

训练只是前半段。端侧部署还要解决模型格式、量化、内存、算子、实时性、功耗和系统稳定性。

### 误区 4：TFLM 是训练工具

TFLM 是 MCU 推理运行时，不是训练工具。训练通常用 Python、TensorFlow、PyTorch 或厂商平台完成。

### 误区 5：端侧 AI 就是把云端模型搬下来

真正的端侧 AI 经常需要重新设计模型、输入特征、采样策略和系统架构。把大模型硬塞进小设备，多半会失败。

## 13. 对你当前阶段的建议

你现在最应该掌握的是这条小闭环：

```text
串口采集 IMU
-> CSV 标签数据
-> Python 窗口特征
-> 小 MLP
-> C 头文件
-> M55 推理接口
-> 串口输出动作类别
```

这条链路看起来小，但它包含了企业端侧 AI 项目的核心骨架。等这条链路跑顺，再学 TFLM、CMSIS-NN、MTB ML、Ethos-U55、大模型端侧部署，都会清晰很多。

## 14. 参考资料

这些资料用于校准当前技术栈和招聘趋势，不需要一次读完。建议带着项目问题查。

- [Infineon PSOC Edge E84 文档](https://documentation.infineon.com/psocedge/docs/eyv1750399809563)：PSoC Edge E84 的 M55、M33、Ethos-U55、NNLite 等硬件定位。
- [KIT_PSE84_AI PSOC Edge E84 AI Kit Guide](https://documentation.infineon.com/psocedge/docs/cci1762693051052)：E84 AI kit 的板级能力、M55/M33/U55 组合和板载多媒体/连接能力。
- [Infineon ModusToolbox Machine Learning](https://www.infineon.com/design-resources/development-tools/sdk/modustoolbox-software/modustoolbox-machine-learning)：Infineon 官方 ML 部署工具链，覆盖模型导入、验证和嵌入式部署流程。
- [Arm CMSIS-NN Documentation](https://arm-software.github.io/CMSIS_6/main/NN/index.html)：Arm Cortex-M 上优化神经网络 kernel 的基础库。
- [TensorFlow Lite Micro paper](https://arxiv.org/abs/2010.08678)：解释 TFLM 面向 TinyML 系统的设计目标和约束。
- [PyTorch Edge / ExecuTorch](https://docs.pytorch.org/edge)：PyTorch 面向 mobile、edge、embedded 的端侧推理生态。
- [ONNX Runtime Execution Providers](https://onnxruntime.ai/docs/execution-providers)：了解 ONNX Runtime 如何通过不同 EP 对接 CPU/GPU/NPU 等硬件后端。
- [Cisco AI Workforce Consortium 2025 Report](https://www.cisco.com/content/dam/cisco-cdc/site/m/ai-workforce-consortium/documents/2025-ai-workforce-consortium-full-report.pdf)：报告中把 embedded engineer 的 AI 技能需求列为 Edge AI、C/C++、RTOS、硬件接口、测试和文档等。
- [Apple On-device Optimization 招聘示例](https://jobs.apple.com/en-us/details/200665634-0865/machine-learning-engineer-edge-ai-on-device-optimization)：体现 2026 年企业对 on-device AI、embedded/mobile/custom silicon/NPU/DSP 部署经验的要求。
- [PyTorch ExecuTorch Arm CPU/NPU 实践](https://pytorch.org/blog/efficient-edge-ai-on-arm-cpus-and-npus/)：展示端侧 PyTorch 模型向 Arm CPU/NPU 部署的方向。
