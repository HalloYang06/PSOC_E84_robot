# 边缘 AI 训练、量化、推理学习手册

日期：2026-07-01

这份文档专门解释：我刚才到底帮你做了什么、这些脚本分别干什么、命令怎么运行、结果怎么看、为什么要先在 PC 上验证、后面怎么部署到 M55/TFLite Micro。

如果你现在还不理解 TensorFlow、TFLite、量化、C array，不要急。先按这份文档的顺序看。

## 0. 先给你一个总览

你现在已经完成了这条链路：

```text
采集好的 CSV 数据
    -> TensorFlow/Keras 训练
    -> 得到 Keras 模型
    -> 导出 float32 TFLite
    -> 导出 int8 量化 TFLite
    -> 在 PC 上分别跑推理验证
    -> 对比量化前后精度
    -> 把 int8 TFLite 转成 C array
    -> 后续放到 M55/TFLite Micro 工程
```

一句话：

```text
我们已经把“数据 -> 模型 -> 量化 -> PC验证 -> C数组部署文件”这条路打通了。
```

现在还没有做的是：

```text
把 intent_model_int8.cc 真正接入 M55/TFLite Micro 工程并在板子上跑。
```

## 1. 你现在有哪些重要文件

### 1.1 数据文件

当前训练用的是：

```text
data/sensor_capture/S01_day2_windows.csv
```

这个文件每一行是一段时间窗口的特征，例如：

```text
emg_biceps_rms
emg_triceps_rms
shoulder_pos_mrad_mean
elbow_vel_mrad_s_mean
label
```

其中：

```text
label = 真实动作标签
```

例如：

```text
elbow_flex
elbow_extend
rest
shoulder_flex
```

### 1.2 训练脚本

```text
tools/train_intent_tf.py
```

作用：

```text
读取 CSV
选择特征列
划分 train / val / test
标准化数据
用 TensorFlow/Keras 训练模型
保存模型和评估结果
导出 TFLite
```

### 1.3 TensorFlow 推理脚本

```text
tools/infer_intent_tf.py
```

作用：

```text
加载训练好的 Keras 模型
读取 CSV
用同样的特征顺序和标准化参数
对每一行数据做预测
输出 predictions.csv
```

### 1.4 量化脚本

```text
tools/quantize_intent_tf.py
```

作用：

```text
把 Keras 模型导出成 float32 TFLite
再导出成 full int8 TFLite
```

### 1.5 TFLite PC 评估脚本

```text
tools/eval_tflite_intent.py
```

作用：

```text
在 PC 上加载 .tflite 模型
跑同一份测试集
输出 accuracy / precision / recall / F1 / confusion matrix
```

这个脚本可以分别评估：

```text
float32 .tflite
int8 .tflite
```

### 1.6 C array 导出脚本

```text
tools/export_tflite_c_array.py
```

作用：

```text
把 intent_model_int8.tflite 转成 intent_model_int8.cc
```

为什么要这样？

因为 MCU 工程里通常不能直接像 PC 那样读取文件系统里的 `.tflite`，而是把模型作为 C 数组编译进固件。

## 2. 训练产物在哪里

这次正式训练的产物目录是：

```text
artifacts/intent_model/run-20260701-210956
```

里面最重要的文件：

| 文件 | 作用 |
|---|---|
| `intent_model.keras` | TensorFlow/Keras 原始模型 |
| `intent_model.tflite` | 训练脚本第一次导出的 TFLite |
| `intent_model_float32.tflite` | 后面量化工具导出的 float32 TFLite |
| `intent_model_int8.tflite` | int8 量化后的 TFLite，后续上 M55 用它 |
| `intent_model_int8.cc` | int8 模型转成的 C array |
| `labels.json` | 类别编号和标签名对应关系 |
| `preprocess.json` | 特征顺序、mean、std、median |
| `metrics.json` | Keras 模型训练结果 |
| `confusion_matrix.csv` | Keras 模型混淆矩阵 |
| `predictions.csv` | Keras 模型对整份 CSV 的预测结果 |
| `tflite_eval/float32_metrics.json` | float32 TFLite 在 PC 上的评估结果 |
| `tflite_eval/int8_metrics.json` | int8 TFLite 在 PC 上的评估结果 |

## 3. 为什么不是只保存一个模型文件

很多初学者会以为：

```text
有 model.tflite 就够了。
```

其实不够。

因为模型训练前做了这些处理：

```text
1. 选择哪些特征列
2. 缺失值怎么填
3. 每个特征的 mean/std 是多少
4. 特征输入顺序是什么
5. label 编号怎么对应真实动作名
```

所以必须一起保存：

```text
模型文件
特征预处理参数
标签映射
```

对应文件就是：

```text
intent_model_int8.tflite
preprocess.json
labels.json
```

上板时也一样，不能只带模型。

## 4. TensorFlow、Keras、TFLite、TFLite Micro 是什么关系

### TensorFlow

TensorFlow 是机器学习框架，负责训练模型。

在这个项目里：

```text
TensorFlow 负责学习 EMG / 电机特征和动作标签之间的关系。
```

### Keras

Keras 是 TensorFlow 里的高级接口，让你更容易写神经网络。

我们训练模型时用的是：

```python
tf.keras
```

### TFLite

TFLite 是 TensorFlow Lite，适合移动端、嵌入式 Linux、边缘设备运行。

PC 上也可以用 TFLite Interpreter 运行 `.tflite` 模型，用来提前验证模型转换是否正确。

### TFLite Micro

TFLite Micro 是更小的运行时，面向 MCU，例如 Cortex-M 系列。

后续 M55 上如果跑模型，大概率就是：

```text
TFLite Micro + int8 model + tensor arena
```

## 5. 训练到底做了什么

我们运行的正式训练大概等价于：

```powershell
conda activate edgi-ai
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED

python tools\train_intent_tf.py ^
  --input data\sensor_capture\S01_day2_windows.csv ^
  --output-dir artifacts\intent_model\run-20260701-210956 ^
  --epochs 5000 ^
  --min-epochs 500 ^
  --patience 500 ^
  --max-train-seconds 7200 ^
  --batch-size 64 ^
  --hidden-units 128,64,32 ^
  --dropout 0.25 ^
  --learning-rate 0.001
```

你不用每次都手打这么长。后面可以简化。

这条命令的意思：

| 参数 | 意思 |
|---|---|
| `--input` | 训练用的 CSV |
| `--output-dir` | 模型和结果保存到哪里 |
| `--epochs 5000` | 最多训练 5000 轮 |
| `--min-epochs 500` | 至少跑 500 轮再允许早停 |
| `--patience 500` | 验证集 500 轮不提升就停止 |
| `--max-train-seconds 7200` | 最多训练 2 小时 |
| `--batch-size 64` | 每次取 64 行样本更新模型 |
| `--hidden-units 128,64,32` | 三层全连接网络 |
| `--dropout 0.25` | 防止过拟合 |
| `--learning-rate 0.001` | 学习率 |

实际训练没有跑满 2 小时，而是在 1043 轮停止。

为什么？

因为验证集效果长期不提升，早停机制认为继续训练意义不大。

这不是坏事。

```text
训练更久不等于模型更好。
如果验证集不提升，继续训练可能只是背训练集。
```

## 6. 训练结果怎么看

训练结果在：

```text
artifacts/intent_model/run-20260701-210956/metrics.json
```

这次核心结果：

```text
总样本数: 7559
训练集: 5275
验证集: 1110
测试集: 1174
特征数: 20
训练轮数: 1043
测试准确率: 0.7598
```

意思是：

```text
在没有参与训练的测试集上，模型大约 75.98% 的窗口分类正确。
```

## 7. precision、recall、F1 是什么

不要只看 accuracy，因为不同类别数量不一样。

### precision：预测出来的准不准

```text
模型预测为 elbow_flex 的样本里，有多少真的就是 elbow_flex。
```

本次：

```text
elbow_flex precision = 0.9041
```

意思是：

```text
模型只要说这是 elbow_flex，大多数时候是准的。
```

### recall：真实样本有没有被找出来

```text
真实 elbow_flex 的样本里，有多少被模型识别成 elbow_flex。
```

本次：

```text
elbow_flex recall = 0.6516
```

意思是：

```text
真实屈肘里，还有不少被模型漏判成别的动作。
```

### F1：precision 和 recall 的综合

```text
F1 越高，说明 precision 和 recall 综合越好。
```

这次每类 F1：

```text
elbow_extend   0.7199
elbow_flex     0.7573
rest           0.5872
shoulder_flex  0.8617
```

## 8. 混淆矩阵怎么看

文件：

```text
artifacts/intent_model/run-20260701-210956/confusion_matrix.csv
```

内容：

```text
真实\预测        elbow_extend  elbow_flex  rest  shoulder_flex
elbow_extend        284          24       26       62
elbow_flex           72         245       42       17
rest                 21           1       64        0
shoulder_flex        16           1        0      299
```

行是真实标签，列是预测标签。

看 `elbow_flex` 这一行：

```text
真实 elbow_flex:
72  个被误判成 elbow_extend
245 个判对成 elbow_flex
42  个被误判成 rest
17  个被误判成 shoulder_flex
```

所以当前模型对肘关节屈伸已经能识别，但还有混淆。

## 9. 为什么要在 PC 上跑推理验证

你问过：

```text
这种不是要在 MCU 上吗？PC 上有参照价值吗？
```

答案是：有，而且必须先做。

原因是验证分两层：

```text
PC 验证：
    验证模型转换和量化有没有把精度搞坏。

MCU 验证：
    验证 TFLite Micro、tensor arena、输入封装、实时延迟有没有问题。
```

如果 PC 上 int8 模型已经不准，那上板一定更麻烦。

所以顺序应该是：

```text
先 PC 上验证 int8 模型数学结果没问题
再上 M55 验证嵌入式运行没问题
```

PC 上主要看：

```text
Keras 模型 accuracy
float32 TFLite accuracy
int8 TFLite accuracy
模型大小
输入输出量化参数
算子类型
```

MCU 上主要看：

```text
能不能加载模型
tensor arena 够不够
推理耗时多少
输入 int8 量化是否一致
输出 label 是否和 PC 对得上
```

## 10. float32 TFLite 是什么

float32 TFLite 是把 Keras 模型转换成 TFLite 格式，但大部分权重和计算仍然是 float32。

优点：

```text
精度最接近原始 Keras 模型
PC/NanoPi/Linux 上容易跑
```

缺点：

```text
模型更大
MCU 上运行更慢
部分 MCU 不适合 float 运算
```

这次导出的文件：

```text
intent_model_float32.tflite
```

大小：

```text
55116 bytes
```

## 11. int8 量化是什么

int8 量化是把模型里的权重和计算从 float32 压到 8 位整数。

简单理解：

```text
float32:
    0.123456, -1.2345, 2.71828

int8:
    -128 到 127 之间的整数
```

为什么可以这样？

因为模型里的数字可以用：

```text
real_value = scale * (int8_value - zero_point)
```

来近似表示。

这样做的好处：

```text
模型更小
推理更快
更适合 MCU / DSP / NPU
更适合 TFLite Micro
```

这次导出的文件：

```text
intent_model_int8.tflite
```

大小：

```text
22232 bytes
```

比 float32 小很多。

## 12. 量化用的 representative dataset 是什么

int8 量化时，TensorFlow 需要知道模型输入大概是什么范围。

所以要给它一些真实样本，这叫：

```text
representative dataset
```

我们用的是：

```text
data/sensor_capture/S01_day2_windows.csv
```

前 512 行作为代表样本。

命令是：

```powershell
python tools\quantize_intent_tf.py ^
  --model-dir artifacts\intent_model\run-20260701-210956 ^
  --input data\sensor_capture\S01_day2_windows.csv ^
  --representative-limit 512
```

它输出：

```text
intent_model_float32.tflite
intent_model_int8.tflite
quantization_report.json
```

## 13. PC 上怎么对比量化前后

我们分别跑了：

```powershell
python tools\eval_tflite_intent.py ^
  --model-dir artifacts\intent_model\run-20260701-210956 ^
  --tflite artifacts\intent_model\run-20260701-210956\intent_model_float32.tflite ^
  --input data\sensor_capture\S01_day2_windows.csv ^
  --name float32
```

和：

```powershell
python tools\eval_tflite_intent.py ^
  --model-dir artifacts\intent_model\run-20260701-210956 ^
  --tflite artifacts\intent_model\run-20260701-210956\intent_model_int8.tflite ^
  --input data\sensor_capture\S01_day2_windows.csv ^
  --name int8
```

输出结果在：

```text
artifacts/intent_model/run-20260701-210956/tflite_eval/
```

里面有：

```text
float32_metrics.json
float32_predictions.csv
float32_confusion_matrix.csv

int8_metrics.json
int8_predictions.csv
int8_confusion_matrix.csv
```

## 14. 量化前后结果

这次结果：

```text
Keras/Test accuracy:   0.7598
TFLite float32 acc:    0.7598
TFLite int8 acc:       0.7589
```

意思是：

```text
int8 量化几乎没有损失精度。
```

模型大小：

```text
float32 TFLite: 55116 bytes
int8 TFLite:    22232 bytes
```

说明：

```text
int8 模型明显更小，更适合上 M55。
```

每类 F1 对比：

```text
类别             float32 F1   int8 F1
elbow_extend     0.7199       0.7273
elbow_flex       0.7573       0.7549
rest             0.5872       0.5872
shoulder_flex    0.8617       0.8559
```

结论：

```text
int8 量化可以接受。
```

## 15. int8 输入输出参数怎么看

PC 评估脚本读到了 int8 模型的输入输出量化参数：

```text
input dtype:  int8
input scale:  0.013371267355978489
input zero:   86

output dtype: int8
output scale: 0.00390625
output zero:  -128
```

这是什么意思？

### 输入量化

PC/端侧推理前，原始标准化后的 float 输入要变成 int8：

```text
int8_input = round(float_input / input_scale + input_zero)
```

也就是：

```text
int8_input = round(float_input / 0.013371267355978489 + 86)
```

然后限制在：

```text
-128 到 127
```

### 输出反量化

模型输出是 int8，要变回概率近似值：

```text
float_output = output_scale * (int8_output - output_zero)
```

也就是：

```text
float_output = 0.00390625 * (int8_output - (-128))
```

端侧也必须这样处理。

## 16. 算子兼容性怎么看

PC 评估脚本也读出了模型算子：

```text
FULLY_CONNECTED
FULLY_CONNECTED
FULLY_CONNECTED
FULLY_CONNECTED
SOFTMAX
```

这说明模型结构很简单：

```text
全连接层 + softmax
```

这对 TFLite Micro 很友好。

上 M55 时通常需要在 resolver 里注册：

```cpp
resolver.AddFullyConnected();
resolver.AddSoftmax();
```

如果后面模型改成 CNN，可能还要：

```cpp
resolver.AddConv2D();
resolver.AddReshape();
resolver.AddAveragePool2D();
```

但当前这个 MLP 模型不复杂。

## 17. C array 是什么

MCU 工程里不能像 PC 那样方便地读：

```text
intent_model_int8.tflite
```

所以要把模型文件变成 C/C++ 数组：

```cpp
const unsigned char g_intent_model_int8_tflite[] = {
    0x1c, 0x00, 0x00, 0x00, ...
};

const unsigned int g_intent_model_int8_tflite_len = 22232;
```

这样编译固件时，模型就会被编译进程序。

我们生成的文件：

```text
artifacts/intent_model/run-20260701-210956/intent_model_int8.cc
```

命令：

```powershell
python tools\export_tflite_c_array.py ^
  --input artifacts\intent_model\run-20260701-210956\intent_model_int8.tflite ^
  --output artifacts\intent_model\run-20260701-210956\intent_model_int8.cc ^
  --symbol g_intent_model_int8_tflite
```

后面可以把这个 `.cc` 文件放进 M55/TFLM 工程。

## 18. 上 M55 前要准备什么

上 M55 不是只复制 `intent_model_int8.cc`。

还需要这些东西：

### 18.1 模型 C array

```text
intent_model_int8.cc
```

### 18.2 特征顺序

来自：

```text
preprocess.json
```

里面的：

```text
feature_columns
```

端侧组输入时必须按这个顺序。

### 18.3 标准化参数

来自：

```text
preprocess.json
```

里面的：

```text
median
mean
std
```

端侧必须先做：

```text
x_scaled = (x - mean) / std
```

然后再做 int8 输入量化：

```text
x_int8 = round(x_scaled / input_scale + input_zero)
```

### 18.4 标签映射

来自：

```text
labels.json
```

类别顺序是：

```text
0 = elbow_extend
1 = elbow_flex
2 = rest
3 = shoulder_flex
```

端侧输出最大概率 index 后，要用这个映射转成动作名。

## 19. M55 上第一步不要接实时控制

第一次上 M55，不要直接控制电机。

正确顺序：

```text
1. 固定写死一组 PC 上用过的输入特征
2. 在 M55 上跑 TFLM 推理
3. 打印输出 int8 raw output
4. 反量化成概率
5. 和 PC 的 int8 推理结果对比
6. 确认一致后，再接实时窗口数据
7. 最后才把结果作为 M33 的辅助输入
```

原因：

```text
如果一上来接实时控制，出问题时你不知道是模型错、输入错、量化错、TFLM错，还是控制逻辑错。
```

## 20. 你现在应该怎么学习

建议你按这个顺序学：

### 第一步：看训练结果

打开：

```text
artifacts/intent_model/run-20260701-210956/metrics.json
artifacts/intent_model/run-20260701-210956/confusion_matrix.csv
```

先理解：

```text
accuracy
precision
recall
F1
confusion matrix
```

### 第二步：看预测结果

打开：

```text
artifacts/intent_model/run-20260701-210956/predictions.csv
```

重点看：

```text
label
predicted_label
confidence
prob_elbow_extend
prob_elbow_flex
```

### 第三步：看 TFLite 对比结果

打开：

```text
artifacts/intent_model/run-20260701-210956/tflite_eval/float32_metrics.json
artifacts/intent_model/run-20260701-210956/tflite_eval/int8_metrics.json
```

比较：

```text
accuracy 有没有明显下降
每类 F1 有没有明显下降
模型大小有没有变小
输入输出 dtype 是不是 int8
```

### 第四步：看 C array

打开：

```text
artifacts/intent_model/run-20260701-210956/intent_model_int8.cc
```

理解它就是：

```text
把 .tflite 文件变成 C 数组。
```

## 21. 你以后怎么自己重新跑

### 21.1 激活环境

Windows PowerShell：

```powershell
conda activate edgi-ai
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_Blink_LED
```

### 21.2 重新训练

```powershell
python tools\train_intent_tf.py --input data\sensor_capture\S01_day2_windows.csv
```

它会自动输出到：

```text
artifacts/intent_model/<时间戳>
```

### 21.3 对 Keras 模型跑推理

把 `<模型目录>` 换成真实目录：

```powershell
python tools\infer_intent_tf.py ^
  --model-dir artifacts\intent_model\<模型目录> ^
  --input data\sensor_capture\S01_day2_windows.csv
```

### 21.4 导出 float32 和 int8 TFLite

```powershell
python tools\quantize_intent_tf.py ^
  --model-dir artifacts\intent_model\<模型目录> ^
  --input data\sensor_capture\S01_day2_windows.csv ^
  --representative-limit 512
```

### 21.5 评估 float32 TFLite

```powershell
python tools\eval_tflite_intent.py ^
  --model-dir artifacts\intent_model\<模型目录> ^
  --tflite artifacts\intent_model\<模型目录>\intent_model_float32.tflite ^
  --input data\sensor_capture\S01_day2_windows.csv ^
  --name float32
```

### 21.6 评估 int8 TFLite

```powershell
python tools\eval_tflite_intent.py ^
  --model-dir artifacts\intent_model\<模型目录> ^
  --tflite artifacts\intent_model\<模型目录>\intent_model_int8.tflite ^
  --input data\sensor_capture\S01_day2_windows.csv ^
  --name int8
```

### 21.7 导出 C array

```powershell
python tools\export_tflite_c_array.py ^
  --input artifacts\intent_model\<模型目录>\intent_model_int8.tflite ^
  --output artifacts\intent_model\<模型目录>\intent_model_int8.cc ^
  --symbol g_intent_model_int8_tflite
```

## 22. 这套流程里每一步的目的

| 步骤 | 目的 |
|---|---|
| Keras 训练 | 学出一个模型 |
| Keras 推理 | 确认原始模型能预测 |
| float32 TFLite 导出 | 确认模型能转成 TFLite |
| float32 TFLite PC 推理 | 确认转换后没坏 |
| int8 量化 | 让模型更小、更适合 MCU |
| int8 TFLite PC 推理 | 确认量化后精度没明显掉 |
| C array 导出 | 准备放进 M55 固件 |
| M55 固定输入推理 | 确认板端运行和 PC 一致 |
| M55 实时输入推理 | 接真实 EMG/电机窗口 |
| M33 安全裁决 | AI 只建议，控制权仍在 M33 |

## 23. 现在最重要的结论

当前这套模型已经满足：

```text
可以训练
可以推理
可以导出 float32 TFLite
可以导出 int8 TFLite
PC 上 int8 精度几乎不掉
可以转成 C array
算子简单，适合 TFLite Micro
```

当前还没完成：

```text
M55/TFLite Micro 工程接入
端侧固定样本推理验证
端侧实时窗口输入
和 M33 的安全策略联动
```

下一步建议：

```text
先把 intent_model_int8.cc 放进 M55/TFLM 工程
写一个固定输入的 smoke test
让 M55 打印 predicted_label 和 confidence
和 PC int8 predictions.csv 对比
```

## 24. 如果你要面试怎么讲

可以这样讲：

```text
我做了一个边缘 AI 动作识别闭环。数据来自 F103 采集的 EMG 和 M33 汇总的电机状态，我先把原始数据整理成窗口特征 CSV，然后用 TensorFlow/Keras 训练 MLP 分类模型。训练后我没有直接上板，而是先导出 float32 TFLite 和 full int8 TFLite，在 PC 上用同一份测试集对比量化前后的 accuracy、F1 和混淆矩阵。结果 float32 TFLite accuracy 是 0.7598，int8 是 0.7589，精度几乎不掉，模型大小从 55KB 降到 22KB。最后我把 int8 模型转成 C array，准备接入 M55/TFLite Micro。整个过程中 AI 只输出动作意图，最终控制仍由 M33 做安全裁决。
```

这段就很完整。

## 25. 继续做的 M55 Golden Sample 准备

在量化和 PC 对比之后，我又补了一个专门给 M55/TFLite Micro smoke test 使用的 golden sample 导出工具：

```text
tools/export_tflm_golden_samples.py
```

它的作用是：

```text
从 CSV 中选择固定样本
    -> 按 preprocess.json 做同样的标准化
    -> 按 int8 TFLite 的 input scale / zero_point 做输入量化
    -> 用 PC TFLite Interpreter 跑 int8 推理
    -> 保存 input_int8 和 expected_output_int8
    -> 导出 JSON 和 C array
```

生成命令：

```powershell
python tools\export_tflm_golden_samples.py ^
  --model-dir artifacts\intent_model\run-20260701-210956 ^
  --tflite artifacts\intent_model\run-20260701-210956\intent_model_int8.tflite ^
  --input data\sensor_capture\S01_day2_windows.csv
```

输出文件：

```text
artifacts/intent_model/run-20260701-210956/tflm_golden/golden_samples.json
artifacts/intent_model/run-20260701-210956/tflm_golden/intent_golden_samples.cc
```

这两个文件的作用：

| 文件 | 作用 |
|---|---|
| `golden_samples.json` | 给人看的 PC 端参考结果 |
| `intent_golden_samples.cc` | 给 M55/TFLite Micro smoke test 编译用的固定输入/输出数组 |

前四条样本是一类一个，并且 PC int8 推理预测正确：

```text
elbow_extend -> elbow_extend
elbow_flex   -> elbow_flex
rest         -> rest
shoulder_flex -> shoulder_flex
```

注意：

```text
golden sample 不是用来重新评估模型准不准的。
它是用来确认 M55/TFLM 的输出是否和 PC int8 TFLite 输出一致。
```

如果 M55 上固定输入输出对不上，问题通常在：

```text
模型 C array 不是同一个
input tensor dtype/scale/zero_point 没处理对
输出 int8 解释错了
resolver 少注册算子
tensor arena 不够
```

更详细的操作记录见：

```text
docs/EDGE_AI_DEPLOYMENT_LOG.md
```

## 26. 当前已经进入 M55/TFLite Micro smoke test

这一步已经不只是“准备放进 M55”，而是已经在 M55 工程里加了固定输入冒烟测试。

M55 工程路径：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
```

新增的关键文件：

```text
applications/intent_model_int8.cc
applications/intent_model_int8.h
applications/intent_golden_samples.cc
applications/intent_golden_samples.h
applications/intent_tflm_smoke.cpp
docs/intent-tflm-m55-smoke-guide.md
```

板端命令：

```text
intent_tflm_smoke
intent_tflm_smoke -v
```

它验证的是：

```text
M55 能加载 int8 TFLite 模型
TFLite Micro 能 AllocateTensors
input tensor 是 int8[20]
output tensor 是 int8[4]
固定 golden samples 的预测类别和 PC int8 参考一致
output int8 分数和 PC 参考基本一致
```

注意：

```text
这一步仍然不是实时控制。
它是部署到 MCU 前非常重要的中间验证，目的是确认 PC 和 M55 的推理 runtime 对同一份输入给出一致输出。
```
