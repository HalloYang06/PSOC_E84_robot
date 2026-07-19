# Edge AI Deployment Log

日期：2026-07-01

本文记录边缘 AI 模型从 PC 训练、量化、TFLite 评估到准备接入 M55/TFLite Micro 的过程。它是操作记录，不是概念学习文档。

## 1. 当前状态

当前已完成：

```text
TensorFlow/Keras 训练
Keras 模型推理
float32 TFLite 导出
full int8 TFLite 导出
PC 上 float32/int8 TFLite 对比
int8 TFLite 转 C array
TFLM 固定输入 golden sample 导出
```

当前未完成：

```text
M55/TFLite Micro 工程接入
M55 固定输入推理 smoke test
M55 实时 EMG/电机窗口推理
M33 安全策略接入
```

## 2. 使用的数据和模型目录

训练数据：

```text
data/sensor_capture/S01_day2_windows.csv
```

模型产物目录：

```text
artifacts/intent_model/run-20260701-210956
```

主要模型文件：

```text
intent_model.keras
intent_model_float32.tflite
intent_model_int8.tflite
intent_model_int8.cc
```

配套参数：

```text
labels.json
preprocess.json
```

## 3. PC 端 TFLite 对比结果

float32 TFLite：

```text
路径: artifacts/intent_model/run-20260701-210956/intent_model_float32.tflite
大小: 55116 bytes
accuracy: 0.7598
```

int8 TFLite：

```text
路径: artifacts/intent_model/run-20260701-210956/intent_model_int8.tflite
大小: 22232 bytes
accuracy: 0.7589
```

结论：

```text
int8 量化后精度几乎没有下降，模型大小从 55 KB 降到 22 KB 左右。
```

PC 评估输出目录：

```text
artifacts/intent_model/run-20260701-210956/tflite_eval
```

关键文件：

```text
float32_metrics.json
int8_metrics.json
float32_predictions.csv
int8_predictions.csv
```

## 4. int8 模型输入输出参数

PC 端读取到的 int8 输入输出量化参数：

```text
input dtype: int8
input scale: 0.013371267355978489
input zero_point: 86

output dtype: int8
output scale: 0.00390625
output zero_point: -128
```

端侧输入处理顺序必须是：

```text
原始窗口特征
    -> 按 preprocess.json 的 feature_columns 排序
    -> 缺失值填充
    -> x_scaled = (x - mean) / std
    -> x_int8 = round(x_scaled / 0.013371267355978489 + 86)
    -> clip 到 [-128, 127]
    -> 送入 TFLite Micro
```

端侧输出解释：

```text
prob = 0.00390625 * (output_int8 - (-128))
```

类别映射来自 `labels.json`：

```text
0 = elbow_extend
1 = elbow_flex
2 = rest
3 = shoulder_flex
```

## 5. 算子兼容性记录

PC TFLite Interpreter 读取到的算子：

```text
FULLY_CONNECTED
FULLY_CONNECTED
FULLY_CONNECTED
FULLY_CONNECTED
SOFTMAX
```

M55/TFLite Micro 侧 resolver 至少需要：

```cpp
resolver.AddFullyConnected();
resolver.AddSoftmax();
```

当前模型是 MLP，没有 Conv2D/LSTM/Reshape 等复杂算子，适合先做 TFLite Micro smoke test。

## 6. C array 导出

已导出：

```text
artifacts/intent_model/run-20260701-210956/intent_model_int8.cc
```

C 符号：

```cpp
g_intent_model_int8_tflite
g_intent_model_int8_tflite_len
```

用途：

```text
把 int8 TFLite 模型编译进 M55/TFLite Micro 工程。
```

## 7. TFLM Golden Sample 包

本次继续生成了 TFLM 固定输入 golden sample 包：

```text
artifacts/intent_model/run-20260701-210956/tflm_golden/golden_samples.json
artifacts/intent_model/run-20260701-210956/tflm_golden/intent_golden_samples.cc
```

生成命令：

```powershell
conda activate edgi-ai
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED

python tools\export_tflm_golden_samples.py ^
  --model-dir artifacts\intent_model\run-20260701-210956 ^
  --tflite artifacts\intent_model\run-20260701-210956\intent_model_int8.tflite ^
  --input data\sensor_capture\S01_day2_windows.csv
```

输出摘要：

```text
sample_count: 8
feature_count: 20
class_count: 4
```

前四条样本是一类一个，并且 PC int8 推理预测正确：

| source_row | true_label | expected_label | expected_output_int8 |
|---:|---|---|---|
| 675 | elbow_extend | elbow_extend | [66, -103, -128, -91] |
| 644 | elbow_flex | elbow_flex | [-125, 125, -128, -128] |
| 9 | rest | rest | [-70, -113, 43, -116] |
| 5401 | shoulder_flex | shoulder_flex | [-81, -88, -128, 42] |

后四条是额外固定样本，主要用于检查 M55 输出是否和 PC 一致。

注意：

```text
golden sample 的核心用途是验证 PC int8 与 M55/TFLM 输出一致，不是重新评估模型准确率。
```

## 8. M55 Smoke Test 建议

上 M55 的第一步不要接实时 EMG，也不要控制电机。

建议先写一个固定输入 smoke test：

```text
1. 编译 intent_model_int8.cc
2. 编译 tflm_golden/intent_golden_samples.cc
3. 初始化 TFLite Micro Interpreter
4. 注册 FullyConnected 和 Softmax
5. 分配 tensor arena
6. 逐条复制 g_intent_golden_input 到 input tensor
7. interpreter.Invoke()
8. 读取 output tensor
9. 和 g_intent_golden_expected_output 对比
10. 打印 predicted index / confidence
```

通过标准：

```text
每条样本的 argmax index 与 g_intent_golden_expected_indices 一致。
输出 int8 值允许有极小差异；如果完全一致最好。
```

如果不一致，优先检查：

```text
input tensor dtype 是否 int8
input scale/zero_point 是否和 PC 一致
模型 C array 是否是最新的 intent_model_int8.tflite
resolver 是否注册 FullyConnected 和 Softmax
tensor arena 是否足够
输出读取是否按 int8 解释
```

## 9. 路径纠正

`F:\ym310` 是另一个工程，不属于本次 TensorFlow intent 模型部署链路。

本次链路只使用下面两个工程：

```text
训练、量化、导出产物：
F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED

M55/TFLite Micro 部署：
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
```

以后不要把 `F:\ym310` 当成这个模型的部署目标。

## 10. M55/TFLite Micro smoke test 已接入

已经把 PC 端导出的 int8 TFLite 模型和 golden samples 放进 M55 工程：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\applications\intent_model_int8.cc
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\applications\intent_model_int8.h
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\applications\intent_golden_samples.cc
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\applications\intent_golden_samples.h
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\applications\intent_tflm_smoke.cpp
```

新增板端 shell 命令：

```text
intent_tflm_smoke
intent_tflm_smoke -v
```

它做的事情：

```text
1. 加载 g_intent_model_int8_tflite。
2. 使用 TFLite Micro MicroInterpreter。
3. 从 RT-Thread heap 分配 64KB tensor arena。
4. 检查 input/output 是否都是 int8。
5. 检查 input bytes 是否等于 20。
6. 检查 output bytes 是否等于 4。
7. 把 g_intent_golden_input 逐条复制到 input tensor。
8. 调用 interpreter.Invoke()。
9. 对比 argmax 预测类别。
10. 对比 output int8 数组，允许极小误差 tolerance=2。
```

期望串口输出类似：

```text
[intent_tflm] ready model=22232 arena=65536 used=...
[intent_tflm] golden pass 8/8 tolerance=2
```

这个 smoke test 的意义是验证“M55/TFLM 的运行结果和 PC int8 TFLite 参考输出一致”，不是重新评估模型 accuracy。

## 11. 下一步任务

推荐下一步：

```text
1. 构建 M55 工程，确认新增 TFLM smoke 代码能通过编译。
2. 烧录 M55 固件。
3. 串口执行 intent_tflm_smoke。
4. 如果 golden pass 8/8，再接实时窗口输入。
5. 实时输入接入时必须复用训练时的特征顺序、标准化和 int8 量化参数。
6. M55 只输出意图和置信度，最终控制仍交给 M33 安全策略。
```

## 12. M55 构建验证记录

构建时不要直接依赖 `rtconfig.py` 里的占位路径 `C:\Users\XXYYZZ`，本机可用 RT-Thread Studio 自带 GCC：

```powershell
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
$env:RTT_EXEC_PATH='F:\RT-ThreadStudio\platform\env_released\env-new\tools\gnu_gcc\arm_gcc\mingw\bin'
F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

本次验证结果：

```text
已编译：
CXX build\applications\intent_golden_samples.o
CXX build\applications\intent_model_int8.o
CXX build\applications\intent_tflm_smoke.o

已解决：
intent 模型数组未链接
golden sample 数组未链接
64KB tensor arena 放入 .bss 导致 RAM overflow

仍阻塞整包链接的旧问题：
drv_lcd_get_init_result / drv_lcd_get_gfx_context 等 LCD 符号未定义
g_mmcsd_diag_* 等 SDIO/MMC 诊断符号未定义
m55_sdio_kick_change 未定义
```

结论：

```text
intent TFLM smoke test 已经进入 M55 构建，并且新增代码自身的链接问题已经修完。
要生成完整 rt-thread.elf，还需要先修 M55 工程原有 LCD/SDIO 相关链接问题。
```
