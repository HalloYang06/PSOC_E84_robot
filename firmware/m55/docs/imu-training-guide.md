# IMU 动作分类训练教程

这份教程接在 `sensor-data-capture-guide.md` 后面。你已经用 M33 的 LSM6DS3 例程采集了 CSV，下一步就是用 Python 把这些数据训练成一个可以部署到 M55 的小模型。

第一轮我们**不直接用 TensorFlow**。原因不是 TensorFlow 不好，而是当前数据只有约 2 Hz，数据量也不大，更适合先用一个容易理解、容易导出成 C 的模型把闭环跑通。

当前训练链路是：

```text
data/*.csv
-> 滑动窗口
-> 特征提取
-> 小 MLP 或最近质心分类器
-> 生成 C 头文件
-> 后续接入 M55 edge_ai_exo_model_run()
```

## 1. 输入数据格式

采集脚本生成的 CSV 至少要包含这些列：

```text
label,ax_mg,ay_mg,az_mg,gx_mdps,gy_mdps,gz_mdps,temp_c
```

当前你已经采到：

```text
data/imu_idle_01.csv
data/imu_idle_02.csv
data/imu_idle_03.csv
data/imu_tilt_left_01.csv
...
data/imu_shake_03.csv
```

每一行是一个 IMU 采样点，每个文件的 `label` 表示这一段动作属于哪个类别。

## 2. 运行训练脚本

在当前 M55 工程目录执行：

```powershell
python tools\train_imu_classifier.py --model mlp --data data --pattern imu_*.csv --window-size 8 --step-size 4 --out-header applications\edge_ai\edge_ai_imu_mlp_model.h --report build\imu_training_report_mlp.txt
```

如果你想先看更容易理解的最近质心分类器，也可以运行：

```powershell
python tools\train_imu_classifier.py --model centroid --data data --pattern imu_*.csv --window-size 8 --step-size 4 --out-header applications\edge_ai\edge_ai_imu_centroid_model.h --report build\imu_training_report_centroid.txt
```

参数解释：

- `--model mlp`：训练一个很小的手写 MLP。它不是 TensorFlow，只是纯 Python 实现的小神经网络。
- `--model centroid`：训练最近质心分类器，逻辑更简单，适合对照学习。
- `--data data`：从 `data` 目录读取 CSV。
- `--pattern imu_*.csv`：只读取 IMU 采集文件。
- `--window-size 8`：每 8 个采样点组成一个训练窗口。当前 M33 例程约 2 Hz，所以约等于 4 秒。
- `--step-size 4`：窗口每次滑动 4 个采样点。这样相邻窗口会有一半重叠。
- `--out-header`：导出的 C 模型参数头文件。
- `--report`：训练报告。

## 3. 脚本做了什么

模型不是直接看单个采样点，而是看一个窗口。因为动作不是一个瞬间，而是一小段时间的变化。

每个窗口会提取 18 个特征：

```text
ax_mean, ay_mean, az_mean
gx_mean, gy_mean, gz_mean
temp_mean
ax_std, ay_std, az_std
gx_std, gy_std, gz_std
temp_std
acc_energy
gyro_energy
acc_range
gyro_range
```

这些特征可以这样理解：

- `mean`：这一段动作整体偏向哪个方向。
- `std`：这一段动作抖动大不大。
- `energy`：整体运动强度。
- `range`：窗口内变化范围。

MLP 会学习两层权重：

```text
18 个窗口特征 -> hidden layer -> 4 个动作类别
```

最近质心分类器会为每个标签计算一个“中心点”。推理时，新的窗口离哪个标签中心最近，就判成哪个标签。它比 MLP 简单，适合你理解“特征空间”这个概念。

## 4. 当前这批数据的训练结果

这次真实数据训练结果：

```text
Loaded 476 samples from 12 CSV files
Built 104 windows: train=79 test=25
Model: mlp
Labels: idle, shake, tilt_left, tilt_right
Test accuracy: 1.000
```

MLP 这次测试集全部分对。最近质心分类器作为对照，结果是：

```text
Model: centroid
Test accuracy: 0.920
```

最近质心的混淆矩阵：

```text
actual\predicted,idle,shake,tilt_left,tilt_right
idle,6,0,0,0
shake,0,4,0,2
tilt_left,0,0,7,0
tilt_right,0,0,0,6
```

这说明第一批数据已经能区分大多数动作，但最近质心里 `shake` 有 2 个窗口被误判成 `tilt_right`。这不奇怪，因为当前采样率只有约 2 Hz，晃动动作的细节被采得太稀。

不要把 1.000 当成正式模型指标。数据量还太小，测试集也来自同一次采集方式。它只是告诉我们：数据链路、特征提取和训练脚本已经跑通。

## 5. 输出文件怎么看

训练后会生成：

```text
applications/edge_ai/edge_ai_imu_mlp_model.h
build/imu_training_report_mlp.txt
```

`edge_ai_imu_mlp_model.h` 里有：

```c
#define IMU_MLP_LABEL_COUNT 4
#define IMU_MLP_FEATURE_COUNT 18
#define IMU_MLP_HIDDEN_COUNT ...
static const char *const imu_mlp_labels[IMU_MLP_LABEL_COUNT] = { ... };
static const float imu_mlp_feature_means[IMU_MLP_FEATURE_COUNT] = { ... };
static const float imu_mlp_feature_scales[IMU_MLP_FEATURE_COUNT] = { ... };
static const float imu_mlp_w1[IMU_MLP_FEATURE_COUNT][IMU_MLP_HIDDEN_COUNT] = { ... };
static const float imu_mlp_b1[IMU_MLP_HIDDEN_COUNT] = { ... };
static const float imu_mlp_w2[IMU_MLP_HIDDEN_COUNT][IMU_MLP_LABEL_COUNT] = { ... };
static const float imu_mlp_b2[IMU_MLP_LABEL_COUNT] = { ... };
```

这些就是模型参数。后续 M55 端只需要做同样的窗口特征提取，再用这些数组做 ReLU MLP 前向计算，就能得到分类结果。

`imu_training_report_mlp.txt` 是训练报告。它在 `build` 目录下，属于临时构建产物，如果重新训练会覆盖。

## 6. 下一步怎么部署到 M55

当前 M55 工程的接口是：

```c
int edge_ai_exo_model_run(const edge_ai_exo_features_t *features, edge_ai_exo_result_t *result);
```

下一步我们要做一个新的 M55 推理适配层：

```text
IMU 窗口数据
-> 与 Python 相同的 18 个特征
-> 使用 edge_ai_imu_mlp_model.h 里的 mean/scale/w1/b1/w2/b2
-> 输出 idle / tilt_left / tilt_right / shake
```

第一版部署可以先不实时读 IMU，而是把几段 CSV 样例固化成测试窗口，验证 M55 上的 C 计算结果和 Python 一致。当前工程已经完成这一步，详见 `docs/imu-mlp-m55-deploy-guide.md`。确认一致后，再考虑在线采集。

## 7. 什么时候再用 TensorFlow / TFLM / MTB ML

建议顺序：

```text
第一轮：当前纯 Python MLP/最近质心模型，理解数据到 C 部署
第二轮：Python + TensorFlow/Keras 训练小 MLP，并导出 .tflite
第三轮：导出 int8 .tflite，用 TFLM 在 M55 跑
第四轮：走 Infineon MTB ML / DeepCraft Model Converter，评估 U55/NNLite
```

你现在最重要的是先建立“同一份数据，PC 训练，板端复现”的感觉。这个感觉建立起来之后，再换 TensorFlow 或 MTB ML 就不会迷路。

## 8. 常见问题

### 为什么窗口大小是 8？

因为当前 M33 例程约 500 ms 输出一次，也就是约 2 Hz。`window-size=8` 大约覆盖 4 秒动作。采样率提高到 50 Hz 后，窗口大小会重新设计，比如 50 或 100。

### 为什么不用单点分类？

单点只表示某个瞬间。动作识别更关心一段时间里的变化，比如抖动、倾斜、速度变化，所以要用窗口。

### 为什么现在的模型不是 int8？

第一轮先用 float 参数，目的是教学清楚和方便对齐 Python/C 结果。后续换 TFLM 或 MTB ML 时再做 int8 量化。

### 这能直接用于外骨骼吗？

不能。它是练习数据链路和部署链路的模型。正式外骨骼需要更高采样率、更严格标注、更多动作数据、安全保护和闭环控制验证。
