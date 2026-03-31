# microWakeWord 集成方案

## 概述
microWakeWord 是基于 TensorFlow Lite Micro 的开源唤醒词引擎，完全免费。

## 资源需求
- Flash: ~50KB (模型 + TFLite 运行时)
- RAM: ~10KB
- CPU: ARM Cortex-M33 (支持)

## 集成步骤

### 1. 下载 TensorFlow Lite Micro
```bash
git clone https://github.com/tensorflow/tflite-micro.git
```

或使用 CMSIS-Pack:
- 访问 https://www.keil.arm.com/packs/tensorflow-lite-micro-tensorflow/
- 下载 tensorflow-lite-micro pack

### 2. 下载 microWakeWord 模型
```bash
git clone https://github.com/kahrendt/microWakeWord.git
```

预训练模型位置：
- `microWakeWord/models/` 目录
- 选择一个中文模型或英文模型（如 "hey_jarvis"）

### 3. 文件结构
```
yiliao_m33/
├── libraries/
│   └── tflite-micro/
│       ├── lib/
│       │   └── libtensorflow-microlite.a
│       ├── include/
│       │   └── tensorflow/
│       └── models/
│           └── wake_word_model.tflite
```

### 4. 修改代码
在 voice_trigger.c 中：
```c
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

// 加载模型
const unsigned char wake_word_model[] = {...};  // 模型数据
const tflite::Model* model = tflite::GetModel(wake_word_model);

// 创建解释器
tflite::MicroInterpreter interpreter(...);

// 运行推理
interpreter.Invoke();

// 检查结果
float* output = interpreter.output(0)->data.f;
if (output[0] > 0.8) {
    // 检测到唤醒词
}
```

## 简化方案：使用预编译库

如果 TFLite Micro 太复杂，可以：
1. 先用当前的能量检测算法验证流程
2. 等整个系统跑通后再集成 ML 模型
3. 或者使用按键触发代替唤醒词

## 参考资料
- [microWakeWord GitHub](https://github.com/kahrendt/microWakeWord)
- [TensorFlow Lite Micro](https://github.com/tensorflow/tflite-micro)
- [TFLite Micro ARM Guide](https://blog.tensorflow.org/2021/02/accelerated-inference-on-arm-microcontrollers-with-tensorflow-lite.html)
