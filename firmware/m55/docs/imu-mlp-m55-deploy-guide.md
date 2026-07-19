# IMU MLP 模型部署到 M55 教程

这份教程说明如何把 `tools/train_imu_classifier.py` 训练出的 IMU MLP 模型参数接入当前 M55 RT-Thread 工程，并通过串口验证板端 C 推理结果。

当前阶段仍然是**离线窗口推理验证**，不是在线读取 IMU。也就是说，M33 负责过数据采集，M55 现在先拿几段固定 IMU 窗口验证 C 端推理逻辑。

## 1. 为什么先做离线窗口推理

训练完成后，最容易出错的是 Python 和 C 两边计算不一致：

- 窗口大小不一致。
- 特征顺序不一致。
- 标准化 `mean/scale` 用错。
- MLP 权重矩阵维度弄反。
- C 端用了不同的数学函数。

所以第一步不是马上抢 IMU 外设，而是先把同一段 CSV 窗口固化到 M55 工程中，验证 M55 输出的标签和 Python 一致。

## 2. 新增模块

关键文件：

```text
applications/edge_ai/edge_ai_imu_mlp_model.h
applications/edge_ai/edge_ai_imu_mlp.h
applications/edge_ai/edge_ai_imu_mlp.c
applications/edge_ai/edge_ai_imu_mlp_demo.h
applications/edge_ai/edge_ai_imu_mlp_demo.c
tests/imu_mlp_inference_test.c
```

分工：

- `edge_ai_imu_mlp_model.h`：训练脚本生成的模型参数，包括标签、均值、尺度、MLP 权重和偏置。
- `edge_ai_imu_mlp.c`：纯 C 推理核心，不依赖 RT-Thread，可在 PC 上测试。
- `edge_ai_imu_mlp_demo.c`：RT-Thread 展示层，准备固定 IMU 窗口并打印推理结果。
- `tests/imu_mlp_inference_test.c`：主机测试，验证 C 端能把 4 段窗口分到正确标签。

## 3. M55 串口现象

烧录后 M55 串口应出现类似：

```text
[imu_mlp] demo init: trained from M33 LSM6DS3 CSV windows
[imu_mlp] labels: idle / shake / tilt_left / tilt_right
[imu_mlp] sample=0 expected=idle predicted=idle score=7547 logits=[7547,...]
[imu_mlp] sample=1 expected=shake predicted=shake score=33633 logits=[...]
[imu_mlp] sample=2 expected=tilt_left predicted=tilt_left score=7365 logits=[...]
[imu_mlp] sample=3 expected=tilt_right predicted=tilt_right score=5912 logits=[...]
```

`score` 和 `logits` 都乘了 1000 后转成整数打印，因为 `rt_kprintf` 的浮点格式支持不稳定。判断对不对主要看 `predicted`。

## 4. 主机侧验证

在 M55 工程目录运行：

```powershell
gcc -std=c99 -Wall -Wextra -Iapplications/edge_ai tests/imu_mlp_inference_test.c applications/edge_ai/edge_ai_imu_mlp.c -o build/imu_mlp_inference_test.exe
.\build\imu_mlp_inference_test.exe
```

期望输出：

```text
PASS idle ...
PASS shake ...
PASS tilt_left ...
PASS tilt_right ...
```

这个测试不需要板子，主要证明 C 端推理和模型参数是可用的。

## 5. 固件构建

M55 构建：

```powershell
F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

M33 IMU 工程构建：

```powershell
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_LSM6DS3
F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

注意：M33 工程 `rtconfig.py` 的 GCC 路径需要指向 RT-Thread Studio 自带 GCC 13.3，否则命令行无法构建。

## 6. 烧录和日志

推荐顺序：

```text
1. 烧录 M33 Non-Secure 固件，负责基础启动链路。
2. 烧录 M55 固件，负责 IMU MLP 推理 demo。
3. 打开 KitProg3 USB-UART 串口，查看 `[imu_mlp]` 日志。
```

如果串口里同时有 M33 和 M55 输出，优先看日志前缀：

```text
This core is cortex-m33
It's cortex-m55
[edge_ai] ...
[imu_mlp] ...
```

`[imu_mlp]` 是这次新增的 M55 端模型推理日志。

## 7. 下一步

离线窗口推理验证通过后，再进入在线数据链路设计：

```text
方案 A：M33 采 IMU -> IPC/共享内存 -> M55 推理
方案 B：M55 直接采 IMU -> M55 推理
```

第一版不建议两个核同时访问同一个 I2C IMU。在线链路要先设计数据所有权，再写驱动和 IPC。
