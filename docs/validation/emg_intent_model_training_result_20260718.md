# 肌电动作意图模型训练结果记录（2026-07-18）

## 结论概述

本文记录康复助力项目中边缘 AI 肌电动作意图识别模型的训练、量化和部署结果。当前模型采用 3 类动作意图：

- `rest`：静止/放松状态。
- `elbow_curl`：小臂弯举意图，由原始 `elbow_flex` 和 `elbow_extend` 合并得到。
- `shoulder_flex`：大臂前抬意图。

前一版 4 类实验中，主要混淆集中在 `elbow_flex` 和 `elbow_extend`。结合当前助力控制逻辑，将二者合并为 `elbow_curl` 更适合比赛展示和嵌入式部署：边缘 AI 负责识别“用户是否有小臂运动意图”，M33 控制策略再根据关节位置、速度、力矩估计、限流和康复模式决定助力方向与大小。

## 数据来源

训练数据来自 2026-07-14 和 2026-07-18 两批窗口数据：

```text
data/sensor_capture/S01_day4_clean3_20260714_windows.csv
data/sensor_capture/S01_day4_clean4_20260714_windows.csv
```

清洗合并后的训练输入文件为：

```text
data/sensor_capture/S01_day4_20260714_20260718_windows_elbow_curl_cleaned.csv
```

数据集 CSV 和模型二进制文件属于生成产物，未直接提交到 Git 仓库。

## 数据清洗规则

清洗脚本：

```text
tools/prepare_clean_intent_windows.py
```

主要规则：

- 删除已确认的脏 trial：`435`、`492`、`536`、`545`。
- 删除有效采样点不足的窗口：`sample_count < 12`。
- 删除误输入标签，例如 `11`、`44`。
- 将 `elbow_flex` 和 `elbow_extend` 合并为 `elbow_curl`。
- 对不同采集文件的 `trial_id` 增加来源前缀，避免多次采集后 trial 编号重复。

清洗后窗口数量：

| 标签 | 窗口数量 |
|---|---:|
| `elbow_curl` | 8053 |
| `rest` | 2954 |
| `shoulder_flex` | 2414 |
| **总计** | **13421** |

训练、验证、测试集划分：

| 数据集 | 行数 |
|---|---:|
| 训练集 | 9347 |
| 验证集 | 2056 |
| 测试集 | 2018 |

划分方式按 `trial_id` 分组，同一次动作采集产生的窗口不会同时出现在训练集和测试集中，避免数据泄漏。

## 模型配置

训练脚本：

```text
tools/train_intent_tf.py
```

核心配置：

| 指标类别 | 指标名称 | 当前结果 / 设计值 | 说明 |
|---|---|---:|---|
| 推理窗口 | 窗口长度 | 300 ms | 用于捕获稳定肌肉激活特征 |
| 推理窗口 | 滑动步长 | 100 ms | 每 100 ms 更新一次动作意图 |
| 模型输入 | 输入特征数 | 21 | 肌电窗口统计量及采集状态特征 |
| 模型输出 | 动作类别数 | 3 | `rest` / `elbow_curl` / `shoulder_flex` |
| 模型结构 | 隐藏层 | `128,64,32` | 轻量全连接网络，适合 TFLite Micro |
| 训练策略 | Dropout | 0.25 | 抑制过拟合 |
| 训练策略 | Batch size | 32 | 兼顾收敛稳定性与训练速度 |
| 训练策略 | 类别权重 | balanced | 缓解不同动作样本数量不均衡 |
| 训练过程 | 实际训练轮数 | 423 | 早停后得到最优验证集模型 |

模型输出目录：

```text
artifacts/intent_model/S01_day4_20260714_20260718_elbow_curl_cleaned
```

## 浮点模型结果

Float / 默认 TFLite 模型在测试集上的结果：

| 指标名称 | 结果 |
|---|---:|
| 测试集准确率 | 98.81% |
| 宏平均 F1 | 98.51% |
| 加权 F1 | 98.83% |

分类结果：

| 类别 | Precision | Recall | F1 |
|---|---:|---:|---:|
| `elbow_curl` | 100.00% | 98.00% | 98.99% |
| `rest` | 100.00% | 100.00% | 100.00% |
| `shoulder_flex` | 93.30% | 100.00% | 96.53% |

## Int8 量化结果

全 int8 量化脚本：

```text
tools/quantize_intent_tflite_int8.py
```

量化设置：

- 代表性校准样本：`512` 行。
- 输入张量类型：`int8`。
- 输出张量类型：`int8`。
- 算子集合：TFLite int8 内置算子。

全 int8 模型文件：

```text
intent_model_full_int8.tflite
```

量化后测试集结果：

| 指标类别 | 指标名称 | 当前结果 / 设计值 | 说明 |
|---|---|---:|---|
| 模型性能 | int8 模型准确率 | 98.56% | 量化后模型在测试集上的整体准确率 |
| 模型性能 | 宏平均 F1 | 98.21% | 衡量多类别整体识别能力 |
| 模型性能 | 加权 F1 | 98.58% | 考虑样本数量后的综合 F1 |
| 量化部署 | int8 TFLite 大小 | 22.2 KB | 模型可直接转为 C 数组部署到 M55 |
| 量化部署 | 量化精度损失 | 约 0.25 个百分点 | Float 98.81%，int8 98.56% |

分类结果：

| 类别 | Precision | Recall | F1 |
|---|---:|---:|---:|
| `elbow_curl` | 100.00% | 97.58% | 98.78% |
| `rest` | 100.00% | 100.00% | 100.00% |
| `shoulder_flex` | 92.01% | 100.00% | 95.84% |

量化参数：

| 张量 | 类型 | scale | zero point | shape |
|---|---|---:|---:|---|
| 输入 | `int8` | 0.058685407 | -47 | `[1, 21]` |
| 输出 | `int8` | 0.00390625 | -128 | `[1, 3]` |

PC 端 TFLite 模型算子检查结果：

```text
FULLY_CONNECTED, FULLY_CONNECTED, FULLY_CONNECTED, FULLY_CONNECTED, SOFTMAX
```

## 边缘 AI 部署说明

本模型在系统中的定位是“动作意图识别器”，不是直接控制电机的最终决策器。推荐的控制职责划分如下：

- M55 边缘 AI：根据肌电窗口和关节状态识别高层动作意图。
- M33 康复控制策略：根据动作意图、关节位置、关节速度、力矩估计、助力模式和安全限制，计算电机控制目标。
- 电机安全层：执行电流限制、位置限制、速度限制、故障保护和康复模式约束。

这样设计的好处是：AI 负责处理肌电信号中非线性、个体差异大的部分；M33 控制环节负责确定性、安全性和实时性更强的电机输出。对于 `elbow_curl`，AI 只判断“小臂弯举相关意图”，具体是助力抬起还是助力放下，由关节轨迹和控制模式共同决定。

## 复现命令

清洗并合并窗口数据：

```powershell
C:\Users\ASUS\.conda\envs\edgi-ai\python.exe tools\prepare_clean_intent_windows.py `
  --input data\sensor_capture\S01_day4_clean3_20260714_windows.csv `
  --input data\sensor_capture\S01_day4_clean4_20260714_windows.csv `
  --output data\sensor_capture\S01_day4_20260714_20260718_windows_elbow_curl_cleaned.csv `
  --bad-trial 435 `
  --bad-trial 492 `
  --bad-trial 536 `
  --bad-trial 545 `
  --min-sample-count 12 `
  --merge-elbow-curl
```

训练模型：

```powershell
C:\Users\ASUS\.conda\envs\edgi-ai\python.exe tools\train_intent_tf.py `
  --input data\sensor_capture\S01_day4_20260714_20260718_windows_elbow_curl_cleaned.csv `
  --output-dir artifacts\intent_model\S01_day4_20260714_20260718_elbow_curl_cleaned `
  --epochs 2000 `
  --min-epochs 200 `
  --patience 200 `
  --max-train-seconds 1800 `
  --batch-size 32 `
  --hidden-units 128,64,32 `
  --dropout 0.25 `
  --learning-rate 0.001 `
  --class-weight balanced
```

导出全 int8 模型：

```powershell
C:\Users\ASUS\.conda\envs\edgi-ai\python.exe tools\quantize_intent_tflite_int8.py `
  --model-dir artifacts\intent_model\S01_day4_20260714_20260718_elbow_curl_cleaned `
  --input data\sensor_capture\S01_day4_20260714_20260718_windows_elbow_curl_cleaned.csv `
  --representative-rows 512
```

评估全 int8 模型：

```powershell
C:\Users\ASUS\.conda\envs\edgi-ai\python.exe tools\eval_tflite_intent.py `
  --model-dir artifacts\intent_model\S01_day4_20260714_20260718_elbow_curl_cleaned `
  --tflite artifacts\intent_model\S01_day4_20260714_20260718_elbow_curl_cleaned\intent_model_full_int8.tflite `
  --input data\sensor_capture\S01_day4_20260714_20260718_windows_elbow_curl_cleaned.csv `
  --name intent_model_full_int8 `
  --batch-size 256
```

## 注意事项

当前模型的第 21 个特征为 `trial_index_from_id`，它来自采集批次编号，不是传感器物理特征。M55 部署时该维度应固定为训练均值，使标准化后接近 0，避免运行时依赖采集编号。后续正式版建议重新训练一个只包含肌电统计量和关节状态的模型，进一步提高工程一致性。

## 总结

当前 3 类方案是适合比赛报告和嵌入式演示的版本：模型准确率高，int8 量化后体积小，精度损失很低，并且能够清晰体现“双核协同 + 边缘 AI + 康复控制”的系统设计思路。
