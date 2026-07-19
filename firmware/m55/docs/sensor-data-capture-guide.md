# Edgi-Talk IMU 数据采集到模型部署练习指南

这一步的目标不是马上做出很准的外骨骼模型，而是先把完整闭环跑通：

```text
M33 采集 IMU -> PC 保存 CSV -> 标注 -> 训练小模型 -> 导出模型 -> M55 部署推理
```

你现在已经证明 M55 上能跑一个最小 AI demo。下一步要证明的是：真实传感器数据能被我们稳定采到、保存、标注，并最终变成 M55 上的模型输入。

## 1. 为什么先用 IMU，不直接上肌电

肌电是正式外骨骼很重要的数据，但它不适合作为第一轮练习对象。肌电信号幅值小、噪声多，贴片位置、皮肤状态、前端放大、隔离保护、工频干扰都会影响数据。如果第一轮就用肌电，你很可能分不清问题来自 AI、采集电路、人体差异，还是标注方法。

IMU 更适合练手：

- 板上已经有 LSM6DS3TR。
- M33 例程已经启用 I2C 和 `BSP_USING_LSM6DS3`。
- 加速度和角速度数据直观，动作变化容易观察。
- 不涉及人体电信号安全隔离。

师傅给你的原则是：先用干净传感器跑通工艺，再把同一套工艺迁移到更脏、更难的肌电。

## 2. 两类固件的分工

第一阶段不要把所有功能塞到一个固件里。先分清两个角色：

```text
数据采集固件：Edgi_Talk_M33_LSM6DS3
模型推理固件：Edgi_Talk_M55_Blink_LED，也就是当前工程
```

采数据时，只烧录 M33 IMU 例程即可。它负责读取 LSM6DS3 并从串口打印。

部署模型时，需要烧录能启动 CM55 的 M33 固件，再烧录 M55 推理固件。M33 的作用是完成安全/非安全启动链路，并把 M55 拉起来；M55 负责跑推理。

注意：不要让 M33 和 M55 同时抢同一个 I2C IMU。正式工程里要么 M33 采集后通过 IPC/共享内存给 M55，要么把 IMU 采集移到 M55。第一轮训练部署练习先不做 IPC，先用 M33 采集离线 CSV，再把训练好的模型部署到 M55。

## 3. 先烧录 M33 IMU 例程

工程路径：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_LSM6DS3
```

这个工程当前关键信息：

- `applications/main.c` 负责蓝灯 500 ms 心跳。
- `packages/lsm6ds3tr/lsm6ds3tr-c_port.c` 里有 `lsm6ds3tr_c_read_data_sample()`。
- 该函数通过 `INIT_APP_EXPORT(lsm6ds3tr_c_read_data_sample)` 自动启动。
- I2C 总线名是 `i2c0`。
- 当前默认输出频率偏低，适合 smoke test，不适合最终动作识别训练。

烧录后串口应看到类似：

```text
Acceleration [mg]:  15.23   -3.12   1000.45
Angular rate [mdps]: 2.50   -1.25    0.75
Temperature [degC]:  26.54
```

如果只能看到 `Hello RT-Thread` 和蓝灯闪，但没有传感器数据，优先检查：

- `.config` / `rtconfig.h` 是否有 `BSP_USING_LSM6DS3`。
- 是否有 `RT_USING_I2C`、`BSP_USING_I2C`、`BSP_USING_HW_I2C0`。
- `packages/lsm6ds3tr/SConscript` 是否被编进工程。
- 串口工具波特率是否为 115200。

## 4. 用脚本保存 CSV

当前 M55 工程提供了采集脚本：

```text
tools/serial_csv_logger.py
```

先安装 Python 串口库：

```powershell
python -m pip install pyserial
```

查看开发板串口号，例如设备管理器里是 `COM7`，采集 20 秒静止数据：

```powershell
python tools\serial_csv_logger.py --port COM7 --baud 115200 --label idle --duration 20 --out data\imu_idle.csv --raw-log data\imu_idle_raw.log
```

采集一个动作时，换标签和输出文件：

```powershell
python tools\serial_csv_logger.py --port COM7 --baud 115200 --label wave_left --duration 20 --out data\imu_wave_left.csv
```

CSV 字段为：

```text
host_ms,board_ms,label,ax_mg,ay_mg,az_mg,gx_mdps,gy_mdps,gz_mdps,temp_c
```

其中 `host_ms` 是 PC 收到这一行时的时间。当前 M33 例程没有输出板端时间，所以 `board_ms` 会为空。后续我们把 M33 例程改成一行 CSV 格式时，再补上板端时间。

## 5. 第一轮标签怎么设计

先别设计太多类别。第一轮只要能训练出一个小模型即可：

```text
idle
tilt_left
tilt_right
shake
```

每个类别先采 5 组，每组 20 秒。这样你会得到：

```text
data/imu_idle_01.csv
data/imu_idle_02.csv
...
data/imu_shake_05.csv
```

采集时动作要稳定，不要一边采 `tilt_left` 一边夹杂其他动作。数据质量差，模型会学得很混乱。

## 6. 训练路线怎么选

第一轮建议用 Python 训练小模型，因为这样你能清楚看到数据、特征和模型的关系：

```text
CSV -> 滑动窗口 -> 特征提取 -> 小 MLP / Logistic Regression -> int8 或 tflite
```

DeepCraft Studio 也可以用，尤其适合后面做完整产品化流程。建议顺序是：

1. Python 跑通最小训练，理解窗口、特征、标签、混淆矩阵。
2. 再用 DeepCraft Studio 复现同样数据集，学习它的数据管理、标注、训练和导出。
3. 部署时优先走 Infineon MTB ML / DeepCraft Model Converter，因为目标板就是 PSoC Edge E84。
4. TFLM 作为你必须理解的底层运行时，不作为第一轮手搓主线。

当前工程已经提供第一版训练教程和脚本：

```text
docs/imu-training-guide.md
tools/train_imu_classifier.py
```

采完 `data/imu_*.csv` 后，先按 `docs/imu-training-guide.md` 跑最近质心分类器，把“CSV 到 C 模型参数”这一步打通。

## 7. 部署到当前 M55 工程

当前 M55 工程已经有一个稳定接口：

```c
int edge_ai_exo_model_run(const edge_ai_exo_features_t *features, edge_ai_exo_result_t *result);
```

后续部署模型时不要推倒重来，逐步替换：

1. 保留 `edge_ai_app_run_once()` 的串口输出形式。
2. 把模拟特征替换成从训练数据中计算出来的同类特征。
3. 第一版可以把 Python 训练出的权重导出成 C 数组，先替换 `edge_ai_exo_model.c`。
4. 第二版再换成 `.tflite` + TFLM。
5. 第三版再走 DeepCraft / MTB ML 导出的 `IMAI_init / IMAI_compute / IMAI_finalize` 风格接口。

## 8. 推荐烧录顺序

采数据阶段：

```text
1. 烧录 Secure M33
2. 烧录 Edgi_Talk_M33_LSM6DS3
3. 打开串口，运行 serial_csv_logger.py 保存 CSV
```

部署推理阶段：

```text
1. 烧录 Secure M33
2. 烧录一个能 enable CM55 的 M33 Non-Secure 固件
3. 烧录当前 M55 推理工程
4. 串口确认 M55 输出模型识别结果
```

如果你用 `Edgi_Talk_M33_LSM6DS3` 同时作为启动 M55 的 M33 固件，要先确认它已经开启：

```text
RT-Thread Settings -> 硬件 -> select SOC Multi Core Mode -> Enable CM55 Core
```

## 9. 当前阶段的验收标准

第一轮数据链路跑通的标准不是准确率，而是这些证据：

- M33 固件能持续输出 LSM6DS3 数据。
- PC 能保存带标签的 CSV。
- 每个标签至少有几组数据文件。
- Python 或 DeepCraft 能读入数据并训练一个最小分类器。
- M55 工程能输出训练后模型的推理结果。

等这五件事完成，再开始讨论肌电采集和 IMU + EMG 融合。那时你已经有完整工艺，不会被复杂信号拖进泥里。
