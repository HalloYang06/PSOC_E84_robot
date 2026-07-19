# Intent TFLite Micro M55 Smoke Test 学习文档

这份文档记录当前 TensorFlow intent 模型接入 M55 的第一步：先跑固定 golden samples，不接实时传感器，也不控制电机。

## 1. 这一步要解决什么问题

训练完成后，模型已经从 Keras 转成了 int8 `.tflite`，并在 PC 上验证过：

```text
float32 TFLite accuracy: 0.7598
int8 TFLite accuracy:   0.7589
int8 model size:        22232 bytes
```

现在要确认同一个 int8 模型放到 M55 的 TFLite Micro 里以后，输出是否还和 PC 参考结果一致。

这里不直接接实时数据，是因为实时链路会多出很多变量：

```text
传感器采样
窗口切片
特征顺序
标准化 mean/scale
int8 量化 scale/zero_point
IPC 或共享内存
控制策略
```

如果一开始就接实时数据，错了也不知道是模型错、输入错、量化错，还是板端 TFLM 没跑对。固定 golden samples 可以先把“模型运行时是否正确”单独验证出来。

## 2. 当前新增文件

M55 工程：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
```

新增文件：

```text
applications/intent_model_int8.cc
applications/intent_model_int8.h
applications/intent_golden_samples.cc
applications/intent_golden_samples.h
applications/intent_tflm_smoke.cpp
tools/test_intent_tflm_smoke_contract.py
docs/intent-tflm-m55-smoke-guide.md
```

文件作用：

| 文件 | 作用 |
|---|---|
| `intent_model_int8.cc` | int8 `.tflite` 模型转出来的 C array |
| `intent_model_int8.h` | 声明模型数组符号 |
| `intent_golden_samples.cc` | 固定输入和 PC 参考输出 |
| `intent_golden_samples.h` | 声明 golden sample 数组符号 |
| `intent_tflm_smoke.cpp` | M55 端 TFLite Micro 冒烟测试命令 |
| `test_intent_tflm_smoke_contract.py` | PC 上的静态集成检查 |

## 3. M55 smoke test 做了什么

板端命令是：

```text
intent_tflm_smoke
intent_tflm_smoke -v
```

运行流程：

```text
1. tflite::GetModel(g_intent_model_int8_tflite)
2. 检查 TFLITE_SCHEMA_VERSION
3. 创建 tflite::MicroMutableOpResolver<2>
4. 创建 tflite::MicroInterpreter
5. 从 RT-Thread heap 分配 64KB tensor arena
6. AllocateTensors()
7. 检查 input tensor 是 int8，长度是 20
8. 检查 output tensor 是 int8，长度是 4
9. 逐条复制 golden input 到 input tensor
10. 调用 interpreter.Invoke()
11. 读取 output int8
12. 比较预测类别和 PC 参考类别
13. 比较 output int8 数组，允许 tolerance=2
```

类别顺序：

```text
0: elbow_extend
1: elbow_flex
2: rest
3: shoulder_flex
```

## 4. 在 PC 上先检查集成点

这一步不需要板子，只检查 M55 工程里文件是否齐、命令是否接好：

```powershell
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
python -m unittest tools.test_intent_tflm_smoke_contract
```

期望输出：

```text
Ran 5 tests
OK
```

这个测试不会跑 TFLite Micro 推理，它只是防止漏文件、漏命令、漏关键检查。

## 5. 构建 M55 固件

在 M55 工程目录构建：

```powershell
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

如果 `rtconfig.py` 里还是占位路径 `C:\Users\XXYYZZ`，先在当前 PowerShell 设置本机 GCC 路径：

```powershell
$env:RTT_EXEC_PATH='F:\RT-ThreadStudio\platform\env_released\env-new\tools\gnu_gcc\arm_gcc\mingw\bin'
```

如果本机环境 PATH 已经配置好，也可以尝试：

```powershell
python -m SCons -j4
```

构建通过才说明新增 `.cpp/.cc` 已经能和当前 RT-Thread、TFLite Micro 包一起编译。

当前验证记录：

```text
intent_golden_samples.o 已编译
intent_model_int8.o 已编译
intent_tflm_smoke.o 已编译
intent 相关 undefined reference 已解决
tensor arena 已改为 heap 分配，不再造成 64KB .bss overflow
```

整包链接当前仍被 M55 工程原有 LCD/SDIO 符号阻塞，例如：

```text
drv_lcd_get_init_result
drv_lcd_get_gfx_context
g_mmcsd_diag_*
m55_sdio_kick_change
```

这些不是 intent 模型接入引入的问题。要烧录完整固件，需要先修复这些已有链接项。

## 6. 在板子上怎么看结果

烧录 M55 固件后，打开串口，在 RT-Thread shell 输入：

```text
intent_tflm_smoke
```

期望看到类似：

```text
[intent_tflm] ready model=22232 arena=65536 used=...
[intent_tflm] golden pass 8/8 tolerance=2
```

如果想看每条样本的预测结果：

```text
intent_tflm_smoke -v
```

会看到类似：

```text
[intent_tflm] sample=0 pred=0/elbow_extend expected=0/elbow_extend score=[66,-103,-128,-91] mismatch=0
[intent_tflm] sample=1 pred=1/elbow_flex expected=1/elbow_flex score=[-125,125,-128,-128] mismatch=0
[intent_tflm] golden pass 8/8 tolerance=2
```

## 7. PC 对比有没有意义

有意义，但它验证的是“运行时一致性”，不是最终真实性能。

PC 对比能证明：

```text
同一个 int8 模型已经被正确加载
输入 tensor 的 dtype 和长度正确
输出 tensor 的 dtype 和长度正确
M55/TFLM 的 argmax 类别和 PC 一致
M55/TFLM 的 int8 输出和 PC 基本一致
```

PC 对比不能证明：

```text
实时采样一定正确
实时窗口切片一定正确
实际佩戴动作一定准
控制策略一定安全
```

所以当前 smoke test 通过后，下一步才是接实时窗口输入。

## 8. 如果失败先看哪里

常见失败和排查方向：

| 现象 | 优先检查 |
|---|---|
| schema mismatch | `.tflite` 文件和 TFLM 版本不兼容，或 C array 不是正确模型 |
| AllocateTensors failed | tensor arena 不够，先把 64KB 加大 |
| input bytes 不等于 20 | 模型输入不是当前训练特征数量，可能拿错模型 |
| output bytes 不等于 4 | 类别数量不一致，可能拿错模型或 labels |
| predicted index 不一致 | golden 输入、模型 C array、TFLM 算子实现需要逐项核对 |
| output int8 误差很大 | 可能读错 tensor、模型不是同一版、或算子注册/实现异常 |

## 9. 通过后的下一步

通过 `intent_tflm_smoke` 后，再做实时接入：

```text
1. 明确 M33 和 M55 谁负责采集原始数据。
2. 把实时数据整理成和训练 CSV 一样的 20 个特征。
3. 使用 preprocess.json 里的 mean/scale 做同样标准化。
4. 使用 int8 input scale/zero_point 做同样量化。
5. 把 int8[20] 喂给 M55 TFLM interpreter。
6. 输出 label、confidence、timestamp。
7. M33 根据安全策略决定是否真的控制电机。
```

面试时可以这样讲：

```text
我没有把训练好的模型直接放到板子上就接控制，而是先做 PC int8 参考推理，再导出 golden samples，在 M55 的 TFLite Micro 上跑固定输入对比输出。这样可以把模型转换、量化、TFLM runtime、tensor shape、算子兼容性先验证清楚。通过后再接实时传感器窗口，最后由 M33 做安全决策。
```
