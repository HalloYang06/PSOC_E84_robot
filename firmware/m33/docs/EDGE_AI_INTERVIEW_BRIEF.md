# 边缘 AI 训练与推理面试文档

日期：2026-07-01

适用场景：用于面试中介绍本项目的边缘 AI 数据采集、TensorFlow 训练、TFLite 转换和端侧推理闭环。本文不是论文式描述，而是面试时能讲清楚“我做了什么、为什么这样做、结果怎么看、下一步怎么优化”的项目说明。

## 1. 一句话项目介绍

我做的是一个面向康复训练场景的边缘智能机械臂系统。系统通过 STM32F103 采集 EMG 肌电数据，通过 M33 汇总 EMG 和电机状态，再用 TensorFlow 在上位机训练动作意图识别模型，最后导出 TFLite 模型，为后续在 M55 或边缘端做实时推理做准备。

面试时可以这样说：

```text
这个项目不是单纯训练一个离线模型，而是打通了从传感器采集、窗口特征生成、TensorFlow 训练、模型评估、TFLite 导出，到边缘端推理接入的完整闭环。
```

## 2. 项目里的边缘 AI 是什么

这里的边缘 AI 指的是：模型不是只在云端或 PC 上跑，而是希望最终放到靠近硬件控制侧的边缘设备上，用实时采集到的 EMG 和电机状态数据做推理。

本项目里的角色分工是：

| 模块 | 作用 |
|---|---|
| STM32F103 | 采集 EMG 等传感数据，通过 CAN 上传 |
| M33 | 汇总传感器和电机状态，负责实时控制和安全裁决 |
| Windows / WSL2 工作站 | 做数据整理、TensorFlow 训练、离线评估 |
| TensorFlow / Keras | 训练动作识别模型 |
| TFLite / LiteRT | 把模型转换成适合边缘端运行的格式 |
| M55 / 边缘侧 | 后续运行轻量模型，输出意图识别结果 |

最重要的安全边界：

```text
AI 模型只输出意图或建议，不能直接控制电机。
真正是否输出电流、速度或位置控制命令，必须由 M33 安全逻辑裁决。
```

## 3. 为什么要做这个模型

康复机械臂需要知道用户当前是在放松、屈肘、伸肘，还是做其他训练动作。传统做法可以写固定阈值规则，例如 EMG 超过某个值就判定为动作，但这样对不同人、不同贴片位置、不同肌肉疲劳状态适应性差。

所以我用机器学习做第一版动作意图识别：

```text
输入：一段时间窗口内的 EMG 和电机状态统计特征
输出：动作类别，例如 elbow_flex / elbow_extend / rest / shoulder_flex
```

这样模型可以学习多个特征之间的组合关系，而不是只依赖单个阈值。

## 4. 数据采集链路

当前数据链路是：

```text
F103 采集 EMG
    -> CAN 上传
    -> M33 汇总 EMG + 电机状态
    -> 串口输出 EMG3MOTOR 文本
    -> Python 采集脚本读取串口
    -> 生成 raw.csv / trials.csv / windows.csv
```

当前训练主要使用：

```text
data/sensor_capture/S01_day2_windows.csv
```

三个 CSV 的含义：

| 文件 | 含义 | 用途 |
|---|---|---|
| raw.csv | 原始逐帧数据 | 后续做 1D CNN/LSTM 时使用 |
| trials.csv | 每段动作采集的元信息 | 检查标签、时长、subject |
| windows.csv | 已按时间窗口聚合好的特征表 | 当前第一版模型训练使用 |

`windows.csv` 每一行是一段时间窗口的统计特征，例如 EMG 均值、标准差、RMS、电机位置、速度、力矩、电流、异常计数等。

## 5. 为什么第一版用 windows.csv

第一版目标是先建立稳定 baseline，而不是一开始就做复杂时序模型。

选择 `windows.csv` 的原因：

- 它已经把原始时序数据变成了窗口特征，训练更快。
- 每一行都能直接对应一个 label，适合分类任务。
- 可以先用小型 MLP 证明动作意图识别链路可行。
- 容易导出 TFLite，后续端侧部署更简单。

面试时可以说：

```text
我没有一开始就上 LSTM 或 Transformer，而是先用窗口统计特征加小型 MLP 做 baseline。这样可以快速验证数据质量、标签质量和训练推理闭环，避免把问题复杂化。
```

## 6. TensorFlow 训练流程

训练脚本：

```text
tools/train_intent_tf.py
```

它做了这些事情：

1. 读取 `S01_day2_windows.csv`。
2. 排除 `session_id`、`trial_id`、`label`、窗口时间等非训练特征。
3. 自动选择可用的数值特征，去掉全空列和常量列。
4. 对 label 做稳定编码，例如 `elbow_flex -> 1`。
5. 按 `trial_id` 划分 train / validation / test，避免同一段动作泄漏到不同集合。
6. 用训练集计算 median / mean / std。
7. 对所有特征做标准化。
8. 用 `tf.keras` 训练一个小型 MLP。
9. 输出 accuracy、precision、recall、F1、confusion matrix。
10. 保存 Keras 模型、TFLite 模型、标签映射、标准化参数和预测结果。

模型结构：

```text
Input(20 features)
    -> Dense(128, relu)
    -> Dropout(0.25)
    -> Dense(64, relu)
    -> Dropout(0.25)
    -> Dense(32, relu)
    -> Dropout(0.25)
    -> Dense(4, softmax)
```

输出类别：

```text
elbow_extend
elbow_flex
rest
shoulder_flex
```

## 7. 为什么要保存 preprocess.json

模型不能只保存 `.keras` 或 `.tflite`。因为训练时对特征做了处理：

```text
缺失值填充
特征顺序
mean/std 标准化
label 编码
```

推理时必须使用完全相同的处理方式，否则输入分布会变，模型结果就不可信。

所以训练产物里保存了：

| 文件 | 作用 |
|---|---|
| intent_model.keras | TensorFlow/Keras 模型 |
| intent_model.tflite | 端侧推理模型 |
| labels.json | 类别编号和标签名映射 |
| preprocess.json | 特征列顺序、median、mean、std |
| metrics.json | 训练结果和评估指标 |
| confusion_matrix.csv | 混淆矩阵 |
| predictions.csv | 每个窗口的推理结果 |

面试时可以强调：

```text
端侧部署时不仅要带模型，还要带同一套特征顺序和标准化参数。否则模型输入会错位，推理结果会失真。
```

## 8. 当前训练结果

训练产物目录：

```text
artifacts/intent_model/run-20260701-210956
```

训练配置和结果：

| 指标 | 数值 |
|---|---:|
| 总样本数 | 7559 |
| 训练集 | 5275 |
| 验证集 | 1110 |
| 测试集 | 1174 |
| 特征数 | 20 |
| 训练轮数 | 1043 |
| 训练耗时 | 211.711 秒 |
| 测试集准确率 | 0.7598 |
| macro F1 | 0.7315 |
| weighted F1 | 0.7603 |

每类结果：

| 类别 | precision | recall | F1 | support |
|---|---:|---:|---:|---:|
| elbow_extend | 0.7226 | 0.7172 | 0.7199 | 396 |
| elbow_flex | 0.9041 | 0.6516 | 0.7573 | 376 |
| rest | 0.4848 | 0.7442 | 0.5872 | 86 |
| shoulder_flex | 0.7910 | 0.9462 | 0.8617 | 316 |

如果面试官问“效果怎么样”，可以这样回答：

```text
第一版四分类模型测试准确率大约 76%。其中 elbow_flex 的 precision 比较高，说明模型一旦判断为屈肘，通常比较可靠；但 elbow_flex 的 recall 还有提升空间，说明部分真实屈肘会被漏判成其他类别。elbow_extend 的 precision 和 recall 都在 72% 左右，说明屈伸之间仍有混淆。
```

## 9. precision、recall、F1 怎么解释

面试中不要只说 accuracy，因为动作分类里不同类别样本数量不均衡。

### precision

precision 关注的是：

```text
模型预测成某一类的样本里，有多少是真的这一类。
```

例如：

```text
模型预测 100 个窗口是 elbow_flex，其中 90 个是真的 elbow_flex，
那么 elbow_flex precision = 90 / 100 = 0.90。
```

本次 `elbow_flex precision = 0.9041`，说明模型只要预测成 `elbow_flex`，通常比较准。

### recall

recall 关注的是：

```text
真实属于某一类的样本里，有多少被模型找出来。
```

例如：

```text
真实有 100 个 elbow_flex，模型只找出 65 个，
那么 elbow_flex recall = 65 / 100 = 0.65。
```

本次 `elbow_flex recall = 0.6516`，说明真实屈肘动作还有一部分被漏判。

### F1

F1 是 precision 和 recall 的综合指标。

```text
precision 高但 recall 低：说明预测谨慎，预测出来比较准，但漏掉不少。
recall 高但 precision 低：说明抓得多，但误报也多。
F1 用来综合看两者平衡。
```

## 10. 混淆矩阵怎么读

当前测试集混淆矩阵：

```text
真实\预测        elbow_extend  elbow_flex  rest  shoulder_flex
elbow_extend        284          24       26       62
elbow_flex           72         245       42       17
rest                 21           1       64        0
shoulder_flex        16           1        0      299
```

行是真实标签，列是模型预测标签。

重点看肘关节屈伸：

```text
真实 elbow_extend:
284 个判对
24 个误判成 elbow_flex
26 个误判成 rest
62 个误判成 shoulder_flex

真实 elbow_flex:
245 个判对
72 个误判成 elbow_extend
42 个误判成 rest
17 个误判成 shoulder_flex
```

可以得出的结论：

- `elbow_flex` 一旦被预测出来比较可靠，但有漏判。
- `elbow_extend` 和 `elbow_flex` 之间仍存在互相混淆。
- `elbow_extend` 有一部分会被误判成 `shoulder_flex`，可能和动作采集姿态、关节状态特征或标签边界有关。
- `rest` 样本数量较少，当前不是最稳定类别。

## 11. TensorFlow 推理流程

推理脚本：

```text
tools/infer_intent_tf.py
```

推理过程：

```text
读取新的 windows.csv
    -> 加载 preprocess.json
    -> 按训练时相同特征顺序取列
    -> 缺失值填充
    -> 标准化
    -> 加载 intent_model.keras
    -> TensorFlow predict
    -> 输出 predicted_label / confidence / 每类概率
```

输出文件：

```text
artifacts/intent_model/run-20260701-210956/predictions.csv
```

预测结果中重点字段：

| 字段 | 含义 |
|---|---|
| label | 真实标签 |
| predicted_label | 模型预测标签 |
| confidence | 预测类别的概率 |
| prob_elbow_extend | 伸肘概率 |
| prob_elbow_flex | 屈肘概率 |
| prob_rest | 静息概率 |
| prob_shoulder_flex | 肩屈概率 |

## 12. 为什么 Windows 和 WSL2 都要准备

我当前采用的是两阶段环境策略：

```text
Windows edgi-ai:
    用于开发训练脚本、快速跑通 CSV、CPU 训练和调试。

WSL2 edgi-tf:
    用于后续数据量变大、模型变复杂时，使用 NVIDIA GPU 加速训练。
```

原因是新版 TensorFlow 在 Windows 原生环境下不再像旧版本那样直接支持 NVIDIA GPU。Windows 端适合开发和小模型训练，WSL2 更适合正式 GPU 训练。

面试时可以说：

```text
我没有把固件开发 Python、采集脚本 Python 和训练 Python 混在一起，而是单独建了 Conda 训练环境，避免 TensorFlow、numpy、pandas 等依赖污染 RT-Thread 工具链。
```

## 13. 项目中我做了什么

可以按这几条讲：

1. 打通了 EMG + 电机状态的数据采集链路。
2. 把串口/CAN 数据整理成 raw、trial 和 window 三类 CSV。
3. 选择 `windows.csv` 做第一版动作意图识别 baseline。
4. 用 TensorFlow/Keras 写了训练脚本。
5. 做了 trial 级别的数据切分，降低相邻窗口泄漏风险。
6. 保存了模型、标签映射、标准化参数和训练指标。
7. 导出了 TFLite 模型，为 M55/边缘端推理做准备。
8. 写了 TensorFlow 推理脚本，对整份 CSV 生成预测结果。
9. 用 precision、recall、F1 和 confusion matrix 分析了屈肘/伸肘识别效果。

简历上可以写：

```text
完成康复机械臂 EMG 与电机状态数据采集到边缘 AI 训练的闭环：基于 Python 采集脚本生成窗口特征数据，使用 TensorFlow/Keras 训练动作意图识别 MLP 模型，导出 Keras/TFLite 产物，并通过混淆矩阵和 precision/recall/F1 分析 elbow_flex 与 elbow_extend 的识别效果。
```

## 14. 面试时可以怎么讲

### 30 秒版本

```text
我在康复机械臂项目里做了一个边缘 AI 训练闭环。前端由 STM32F103 采集 EMG，M33 汇总 EMG 和电机状态，上位机把数据整理成窗口特征 CSV。我用 TensorFlow/Keras 训练了一个小型 MLP 分类模型，识别 rest、elbow_flex、elbow_extend 和 shoulder_flex，并导出 TFLite，为后续 M55 端侧推理做准备。当前第一版测试准确率约 76%，其中 elbow_flex 的 precision 达到 90%，但 recall 还有提升空间。
```

### 2 分钟版本

```text
这个项目的目标是让康复机械臂能够根据用户肌电和电机状态识别训练动作。数据链路上，STM32F103 采集 EMG，通过 CAN 发给 M33；M33 汇总 EMG、关节和电机状态后，通过串口输出给 Python 采集脚本，生成 raw、trials 和 windows 三类 CSV。

第一版模型我没有直接用原始波形，而是选了 windows.csv，因为它已经是窗口统计特征，适合快速建立 baseline。我用 TensorFlow/Keras 做了一个小型 MLP，输入 20 个特征，输出四个类别：elbow_extend、elbow_flex、rest、shoulder_flex。

训练时我按 trial_id 切分训练集、验证集和测试集，避免同一个动作片段的相邻窗口同时出现在训练和测试中。训练后保存了 Keras 模型、TFLite 模型、labels.json 和 preprocess.json，保证端侧推理时特征顺序和标准化参数一致。

当前测试准确率约 76%。从混淆矩阵看，shoulder_flex 最稳定，elbow_flex 的 precision 高但 recall 偏低，说明模型判断为屈肘时比较准，但会漏掉一部分真实屈肘。下一步我会重点补充 elbow_flex / elbow_extend 的数据，并先做二分类模型优化肘关节屈伸识别。
```

## 15. 常见面试问题和回答

### Q1：为什么不用规则阈值？

可以回答：

```text
阈值规则实现简单，但 EMG 信号受个体差异、电极位置、疲劳状态和动作幅度影响很大。单一阈值很难泛化。机器学习模型可以综合 EMG RMS、均值、关节速度、电机电流等多个特征，学习特征组合和动作标签之间的关系。
```

### Q2：为什么第一版不用 LSTM 或 Transformer？

可以回答：

```text
因为当前输入是窗口统计特征，不是原始连续波形。第一版目标是验证数据链路和训练推理闭环，所以用 MLP 更合适，简单、可解释、训练快，也更容易导出 TFLite。等 raw.csv 数据量足够后，再考虑 1D CNN、LSTM 或 Tiny temporal CNN。
```

### Q3：怎么避免训练集和测试集泄漏？

可以回答：

```text
窗口数据有相邻重叠，同一个 trial 内的样本非常相似。如果随机按行切分，训练集和测试集可能出现几乎相同的窗口，导致指标虚高。所以我按 trial_id 分组切分，尽量保证同一个 trial 只进入 train、val 或 test 中的一个集合。
```

### Q4：为什么要保存 preprocess.json？

可以回答：

```text
训练时的特征顺序、缺失值填充、mean/std 标准化必须和推理时完全一致。只保存模型是不够的。如果端侧输入顺序或标准化参数不同，模型结果会失真。所以我把 feature_columns、median、mean、std 都保存到 preprocess.json。
```

### Q5：模型结果怎么看？

可以回答：

```text
我不只看 accuracy，还看 precision、recall、F1 和混淆矩阵。比如当前 elbow_flex 的 precision 是 0.9041，说明预测为屈肘时比较准；但 recall 是 0.6516，说明真实屈肘仍有漏判。这能指导下一步采集更多屈肘边界样本，而不是盲目加训练轮数。
```

### Q6：模型能不能直接控制电机？

可以回答：

```text
不能。这个项目里 AI 只输出动作意图或辅助建议，不能绕过 M33 直接输出电机控制命令。M33 仍然负责安全裁决、限流、限位、fresh/stale 判断和急停逻辑。这样能把 AI 推理和实时安全控制分开。
```

### Q7：下一步怎么优化？

可以回答：

```text
第一步是聚焦 elbow_flex 和 elbow_extend 做二分类模型，因为当前需求主要是肘关节屈伸。第二步补充更多 subject、更多天数和更多动作强度的数据，尤其是 rest 和屈伸边界动作。第三步尝试 1D CNN 直接用 raw.csv 的时序波形。第四步做 TFLite 量化和端侧延迟评估。
```

## 16. 当前不足和改进方向

当前不足：

- 数据主要来自 `S01_day2`，subject 数量少。
- `rest` 样本明显少于动作样本。
- `elbow_flex` 和 `elbow_extend` 仍有互相混淆。
- 当前模型用窗口统计特征，没有直接学习原始 EMG 波形形态。
- 端侧 M55 实时推理还没有完全接入控制闭环。

下一步计划：

1. 单独训练 `elbow_flex` / `elbow_extend` 二分类模型。
2. 增加 rest、轻微屈肘、轻微伸肘和过渡动作数据。
3. 增加不同佩戴位置、不同 subject、不同训练天数的数据。
4. 对 raw.csv 尝试 1D CNN 或 Tiny temporal CNN。
5. 做 TFLite int8 量化，比较精度、模型大小和推理延迟。
6. 在 M55/边缘侧验证输入封装、推理耗时和结果回传。
7. 让 M33 只把模型结果作为辅助输入，继续保持安全裁决权。

## 17. 面试重点总结

可以把这个项目总结成四个关键词：

```text
数据链路：F103 -> CAN -> M33 -> Python CSV
训练链路：windows.csv -> TensorFlow/Keras -> metrics
部署链路：Keras -> TFLite -> M55/边缘推理
安全边界：AI 只建议，M33 做最终控制裁决
```

最值得强调的不是“准确率有多高”，而是：

```text
我打通了真实嵌入式数据到边缘 AI 模型的工程闭环，并且能用指标分析当前模型哪里有效、哪里还需要补数据和优化。
```

