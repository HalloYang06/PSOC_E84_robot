# TensorFlow 训练学习文档

日期：2026-07-01

适用范围：本文件面向当前康复机械臂项目里的 EMG + 电机数据训练链路，帮助理解 TensorFlow 是什么、为什么要这样搭环境、以及从采集数据到端侧模型的完整流程。

## 1. 先回答一句话：TF 是什么

这里说的 `TF` 一般指 **TensorFlow**。

TensorFlow 是一个机器学习框架。它的作用不是直接控制电机，而是帮助我们把采集到的数据训练成一个模型，让模型学会从输入数据里判断某种状态或意图。

在本项目里，TensorFlow 的角色可以理解成：

```text
EMG / 电机 / 关节状态数据
    -> TensorFlow 训练
    -> 得到一个小模型
    -> 转成端侧可运行格式
    -> M55 / 边缘侧推理
    -> 输出运动意图或训练状态建议
    -> M33 根据安全规则决定是否采纳
```

注意：模型输出只能作为辅助建议，不能绕过 M33 直接控制电机。

## 2. 为什么叫 TensorFlow

可以拆开理解：

- `Tensor`：张量，本质上就是多维数组。
- `Flow`：数据在一系列计算步骤里流动。

例如一条训练样本可以是这样的特征向量：

```text
[biceps_rms, triceps_rms, shoulder_vel, elbow_pos, ...]
```

多条样本放在一起，就是一个二维张量：

```text
样本数 x 特征数
```

模型训练时，TensorFlow 会做这些事：

```text
输入张量
    -> 神经网络层计算
    -> 输出预测结果
    -> 和真实 label 比较
    -> 计算 loss
    -> 自动更新模型参数
    -> 重复很多轮
```

## 3. TensorFlow、Keras、TFLite/LiteRT 的关系

训练链路里经常会看到几个名字：

| 名称 | 作用 | 本项目里怎么用 |
|---|---|---|
| TensorFlow | 底层机器学习框架 | 负责训练、评估、保存模型 |
| Keras / tf.keras | TensorFlow 的高级建模 API | 用更简单的代码搭神经网络 |
| TensorFlow Lite / LiteRT | 面向手机、嵌入式、边缘设备的模型格式和运行时 | 把训练好的模型转成端侧可部署的小模型 |

简单说：

```text
TensorFlow 负责训练
Keras 负责让训练代码更好写
TFLite/LiteRT 负责端侧运行
```

官方资料可以看：

- TensorFlow 首页：https://www.tensorflow.org/
- Keras 指南：https://www.tensorflow.org/guide/keras
- TensorFlow 安装说明：https://www.tensorflow.org/install/pip
- LiteRT/TFLite 端侧说明：https://ai.google.dev/edge/litert

## 4. 为什么要单独搭训练环境

当前工程是 RT-Thread / M33 固件工程，默认 Python 很可能被固件工具链、ESP-IDF、SCons、串口采集脚本等使用。

如果直接在系统 Python 里安装 TensorFlow，容易出现这些问题：

- 固件编译依赖被污染。
- 采集脚本依赖版本被改坏。
- TensorFlow、numpy、pandas 等包体积很大，版本依赖复杂。
- GPU 训练还涉及 CUDA/cuDNN，和普通 Python 包不是一个复杂度。

所以要单独建环境：

```text
固件开发环境：继续服务 RT-Thread / SCons / 串口工具
训练环境：专门服务 TensorFlow / pandas / scikit-learn / matplotlib
```

这就是为什么前面建议用 Conda 或 venv，而不是直接 `pip install tensorflow` 到默认 Python。

## 5. 为什么 Windows 和 WSL2 要分开看

你当前机器已经确认：

```text
GPU: NVIDIA GeForce RTX 4060 Laptop
Windows NVIDIA Driver: 566.07
WSL2: 已安装 Ubuntu
Windows Conda 环境 edgi-ai: Python 3.11 + TensorFlow 2.19
```

但是 Windows 原生 TensorFlow 环境检测结果是：

```text
GPU []
```

这不是你的显卡坏了，而是 TensorFlow 的平台支持策略导致的。

官方 TensorFlow 文档说明：Windows 原生环境里，TensorFlow 2.10 是最后一个支持 NVIDIA GPU 的版本；2.11 之后如果要用 NVIDIA GPU，推荐走 WSL2。

所以推荐两步走：

```text
Windows edgi-ai
    -> 先跑通数据读取、训练代码、指标输出
    -> CPU 也够用，调试方便

WSL2 Ubuntu
    -> 正式 GPU 训练
    -> 使用 tensorflow[and-cuda]
    -> 让 RTX 4060 参与训练
```

这样做的好处是：

- Windows 侧适合快速开发和查看文件。
- WSL2 侧适合稳定使用 NVIDIA GPU。
- 不破坏 RT-Thread Studio 和固件工具链。
- 训练和嵌入式开发边界清楚。

## 6. 当前项目的数据文件怎么理解

当前采集目录：

```text
data/sensor_capture/
    S01_day2_raw.csv
    S01_day2_trials.csv
    S01_day2_windows.csv
```

三个文件的含义：

| 文件 | 含义 | 是否直接用于训练 |
|---|---|---|
| raw.csv | 原始逐帧数据，接近串口/CAN 上来的每一行 | 后续做更细模型时用 |
| trials.csv | 每段动作 trial 的元信息，例如 label、时长、subject | 辅助检查数据 |
| windows.csv | 已经按时间窗口聚合好的特征表 | 当前最适合先训练 |

`windows.csv` 里的每一行可以理解成一个训练样本：

```text
一小段时间窗口内的 EMG / 电机统计特征 -> 一个动作标签 label
```

例如：

```text
emg_biceps_rms
emg_triceps_rms
emg_ant_deltoid_rms
shoulder_pos_mrad_mean
shoulder_vel_mrad_s_mean
elbow_pos_mrad_mean
...
label = rest / elbow_flex / ...
```

模型要学的就是：

```text
给我这一段窗口里的传感器特征，我判断它更像哪个动作/状态。
```

## 7. 训练到底在训练什么

以动作意图识别为例：

输入：

```text
一组窗口特征 X
```

输出：

```text
动作类别 y
```

例如：

```text
X = [肱二头肌 RMS, 肱三头肌 RMS, 肩关节速度, 肘关节位置, ...]
y = elbow_flex
```

训练过程不是手写规则：

```text
如果 biceps_rms > 100 就是 elbow_flex
```

而是让模型自己从大量样本中学习：

```text
哪些特征组合更容易对应 rest
哪些特征组合更容易对应 elbow_flex
哪些特征组合更容易对应 elbow_extend
```

这就是机器学习和普通 if-else 规则的区别。

## 8. 推荐的第一版模型

当前 `windows.csv` 已经是统计特征表，不是原始连续波形。所以第一版不建议上来就用 LSTM、Transformer 或很复杂的网络。

最稳的第一版：

```text
输入：窗口统计特征
模型：小型 MLP
输出：动作类别 softmax
```

MLP 可以理解成普通全连接神经网络：

```text
特征输入
    -> Dense
    -> ReLU
    -> Dropout
    -> Dense
    -> ReLU
    -> 输出层 softmax
```

优点：

- 代码简单。
- 对表格特征友好。
- 容易转成 TFLite。
- 适合先建立 baseline。

后续如果要用原始波形，再考虑：

- 1D CNN：适合 EMG 时间序列局部形状。
- LSTM/GRU：适合较长时序依赖。
- Tiny temporal CNN：更适合 MCU/边缘部署。

## 9. 完整训练流程

### 9.1 数据采集

硬件链路：

```text
F103 采集 EMG
    -> CAN
    -> M33 汇总 EMG + 电机状态
    -> 串口输出 EMG3MOTOR
    -> Python 采集脚本
    -> raw.csv / trials.csv / windows.csv
```

目标是拿到带标签的数据：

```text
rest
elbow_flex
elbow_extend
shoulder_raise
...
```

采集时最重要的是标签准确。标签错了，模型会认真学习错误答案。

### 9.2 数据检查

训练前先检查：

```text
每个 label 有多少样本
有没有空值
有没有某些传感通道全是 0
有没有 stale/fault/saturated 过多
不同 subject 是否混在一起
```

推荐先看：

```python
import pandas as pd

df = pd.read_csv("data/sensor_capture/S01_day2_windows.csv")
print(df.shape)
print(df["label"].value_counts())
print(df.isna().sum().sort_values(ascending=False).head(20))
```

### 9.3 特征选择

不能把所有列都直接塞给模型。

这些列通常不是训练特征：

```text
session_id
subject_id
trial_id
label
window_index
window_start_ms
window_end_ms
```

这些列可以作为第一版特征候选：

```text
emg_biceps_mean/std/min/max/mav/rms
emg_triceps_mean/std/min/max/mav/rms
emg_ant_deltoid_mean/std/min/max/mav/rms
shoulder_pos/vel/torque/current
elbow_pos/vel/torque/current
stale_count/fault_count/saturated_count
```

如果某些列当前全是 0 或全是固定值，可以先去掉。

### 9.4 划分训练集、验证集、测试集

一般分三份：

```text
train: 训练模型参数
val: 调参和早停
test: 最后一次客观评估
```

注意：康复数据里最好不要简单随机乱切所有窗口。因为同一个 trial 里的相邻窗口很像，如果随机切分，训练集和测试集可能看到几乎一样的数据，指标会虚高。

更稳的方式是按 trial 或 subject 切分：

```text
同一个 trial 尽量只出现在 train/val/test 其中一边
```

第一版数据量少时可以先做简单切分，但文档和结果里要说明这是初版 baseline。

### 9.5 标准化

不同特征量纲差异很大：

```text
EMG ADC: 可能是几十到几千
位置 mrad: 可能是几百到几千
电流 A: 可能是小数
温度 C: 可能几十
```

神经网络不喜欢这些尺度混在一起，所以需要标准化：

```text
x_scaled = (x - mean) / std
```

训练时要保存标准化器。端侧推理也必须用同一套 mean/std，否则模型输入分布会变。

### 9.6 建模

第一版可以用 Keras 写：

```python
import tensorflow as tf

model = tf.keras.Sequential([
    tf.keras.layers.Input(shape=(num_features,)),
    tf.keras.layers.Dense(64, activation="relu"),
    tf.keras.layers.Dropout(0.2),
    tf.keras.layers.Dense(32, activation="relu"),
    tf.keras.layers.Dense(num_classes, activation="softmax"),
])

model.compile(
    optimizer="adam",
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)
```

这里几个词的含义：

| 概念 | 含义 |
|---|---|
| Dense | 全连接层 |
| ReLU | 常用非线性激活函数 |
| Dropout | 防止过拟合 |
| softmax | 输出每个类别的概率 |
| loss | 预测和真实答案的差距 |
| optimizer | 根据 loss 更新参数的方法 |
| accuracy | 分类准确率 |

### 9.7 训练

训练时通常会写：

```python
history = model.fit(
    X_train,
    y_train,
    validation_data=(X_val, y_val),
    epochs=100,
    batch_size=32,
    callbacks=[
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=10,
            restore_best_weights=True,
        )
    ],
)
```

几个关键词：

| 概念 | 含义 |
|---|---|
| epoch | 所有训练数据完整看一遍 |
| batch_size | 每次拿多少样本更新一次参数 |
| validation_data | 验证集，用来观察泛化能力 |
| EarlyStopping | 验证集不再变好就停止训练 |

### 9.8 评估

不要只看 accuracy，还要看：

```text
confusion matrix：哪些类别最容易混淆
per-class precision/recall：每个动作分别识别得怎么样
test accuracy：最后留出的测试集表现
bad case：错分样本对应的原始 trial
```

例如康复训练里，`rest` 和轻微动作很容易混淆。这个混淆比整体准确率更重要，因为它可能影响后续辅助策略。

### 9.9 保存模型

训练完成后保存：

```text
模型文件：model.keras
标签映射：labels.json
标准化参数：scaler.json 或 scaler.pkl
训练报告：metrics.json / confusion_matrix.png
```

这些东西是一套，不能只保存模型。

因为模型输出的是类别编号：

```text
0, 1, 2, ...
```

必须靠 `labels.json` 才知道：

```text
0 = rest
1 = elbow_flex
2 = elbow_extend
```

### 9.10 转成端侧模型

如果后续要在 M55 或其他边缘端跑，需要转换成 TFLite/LiteRT 模型：

```python
converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
tflite_model = converter.convert()

with open("model.tflite", "wb") as f:
    f.write(tflite_model)
```

端侧部署时要同时带上：

```text
model.tflite
labels.json
scaler 参数
输入特征顺序
窗口长度/步长
```

模型输入顺序必须和训练时完全一致。

### 9.11 端侧接入

端侧推理链路应当是：

```text
M33 汇总传感器窗口
    -> M55 / 边缘推理侧
    -> 按训练时相同顺序组特征
    -> 用训练时相同 mean/std 标准化
    -> TFLite/LiteRT 推理
    -> 得到类别概率
    -> 输出建议
    -> M33 安全裁决
```

不要让模型直接输出电机电流命令。

第一阶段建议模型输出：

```text
intent_label
confidence
timestamp
input_window_quality
```

例如：

```json
{
  "intent": "elbow_flex",
  "confidence": 0.82,
  "window_ms": 300,
  "quality": "ok"
}
```

然后由 M33 或上层策略决定怎么处理。

## 10. 为什么不是直接上板训练

训练和推理是两件事：

```text
训练：大量数据、多轮迭代、需要算力、需要调参
推理：拿训练好的模型，实时算一次输出
```

MCU/边缘端适合推理，不适合做第一阶段训练。

原因：

- 训练要反复读大量数据。
- 训练要保存和更新大量参数。
- 训练要画图、看指标、调参。
- 出错后要快速重跑。
- Windows/WSL2 工作站更方便做数据分析。

所以正确分工是：

```text
PC / WSL2: 训练、评估、转换模型
M55 / 边缘端: 推理
M33: 实时控制和安全裁决
```

## 11. 第一阶段你应该怎么学

建议按这个顺序学，不要一上来陷进 CUDA 或复杂网络：

1. 先理解 `windows.csv` 每一行是什么。
2. 用 pandas 统计 label 数量、空值、特征范围。
3. 用 scikit-learn 做一个 LogisticRegression / RandomForest baseline。
4. 用 TensorFlow/Keras 做一个小 MLP。
5. 看训练曲线和 confusion matrix。
6. 保存 `.keras`、`labels.json`、标准化参数。
7. 转成 `.tflite`。
8. 用 Python 加载 `.tflite` 做一次离线推理验证。
9. 再考虑 M55/端侧接入。

这样学的好处是每一步都有可验证结果，不会变成“环境装好了但不知道下一步干嘛”。

## 12. 当前推荐环境

### Windows CPU 调试环境

当前已有：

```powershell
conda activate edgi-ai
python -c "import tensorflow as tf; print(tf.__version__); print(tf.config.list_physical_devices('GPU'))"
```

预期：

```text
TensorFlow 2.19
GPU []
```

这没问题，适合先跑通代码。

### WSL2 GPU 训练环境

进入 WSL：

```powershell
wsl -d Ubuntu
```

在 Ubuntu 里建环境：

```bash
conda create -n edgi-tf python=3.12 -y
conda activate edgi-tf
python -m pip install -U pip
pip install "tensorflow[and-cuda]" pandas scikit-learn matplotlib
```

验证：

```bash
python -c "import tensorflow as tf; print(tf.__version__); print(tf.config.list_physical_devices('GPU'))"
```

如果能看到 GPU 设备，就可以用 RTX 4060 训练。

## 13. 最小训练脚本应该做什么

后续可以写一个脚本：

```text
tools/train_intent_tf.py
```

它至少应该包含：

```text
1. 读取 windows.csv
2. 选择特征列
3. 清理空值和无效列
4. 编码 label
5. 划分 train/val/test
6. 标准化特征
7. 训练 Keras MLP
8. 输出 accuracy 和 confusion matrix
9. 保存 model.keras
10. 保存 labels.json 和 scaler 参数
11. 可选：导出 model.tflite
```

第一版先追求链路闭环，不追求很高准确率。

## 14. 常见坑

### 14.1 数据太少

目前只有 `S01_day2` 一组数据时，模型很容易只记住这个人的信号特点。

需要逐步增加：

```text
更多 trial
更多 subject
更多天数
更多动作强度
更多佩戴状态
```

### 14.2 标签不准

标签比模型结构更重要。

如果采集时把 `rest` 标成了 `elbow_flex`，模型会学错，而且很难从训练日志里一眼看出来。

### 14.3 数据泄漏

同一个动作 trial 的相邻窗口非常相似。如果随机切分窗口，测试集可能和训练集几乎一样，准确率会虚高。

更好的做法是按 trial 或 subject 切分。

### 14.4 训练和推理特征不一致

训练时用了这些特征：

```text
[a, b, c, d]
```

端侧推理时必须也是：

```text
[a, b, c, d]
```

不能变成：

```text
[b, a, d, c]
```

顺序错了，模型结果会乱。

### 14.5 忘记标准化

训练时如果做了标准化，端侧也必须做同样的标准化。

### 14.6 只看准确率

康复场景里要重点看错分类型。

例如：

```text
把 rest 误判为 elbow_flex
```

可能比：

```text
把 elbow_flex 误判为 elbow_extend
```

更危险或更需要处理，具体取决于后续控制策略。

## 15. 本项目的目标闭环

最终希望形成：

```text
采集
    -> raw.csv / windows.csv
    -> TensorFlow 训练
    -> 离线评估
    -> TFLite/LiteRT 转换
    -> 端侧推理
    -> M33 安全裁决
    -> 康复训练辅助
```

第一阶段验收标准建议设为：

```text
能读取 S01_day2_windows.csv
能训练出一个小模型
能输出每类动作的识别效果
能保存模型和标签映射
能导出 tflite
能用 Python tflite runtime 做一次离线推理
```

完成这一步后，再谈模型优化、端侧延迟、量化、M55 接入，才有稳定基础。

