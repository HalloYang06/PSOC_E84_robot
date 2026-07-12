# TFLite Micro 集成方案

## 当前状态
- 模型已准备：hey_jarvis.tflite (52KB)
- 模型已转换：hey_jarvis_model.h (C数组)
- TFLite Micro 源码已下载

## 问题
网络问题导致无法下载预编译库

## 解决方案

### 方案1：手动下载 Infineon 库（推荐）
1. 访问 https://github.com/Infineon/ml-tflite-micro
2. 下载 ZIP 并解压到 `libraries/ml-tflite-micro`
3. 这是专为 Infineon MCU 优化的版本

### 方案2：使用现有 tflite-micro 编译
需要在你的电脑上执行：
```bash
cd D:\RT-ThreadStudio\workspace\yiliao_m33\libraries\tflite-micro

# 下载依赖
make -f tensorflow/lite/micro/tools/make/Makefile third_party_downloads

# 编译 ARM Cortex-M33
make -f tensorflow/lite/micro/tools/make/Makefile \
  TARGET=cortex_m_generic \
  TARGET_ARCH=cortex-m33 \
  OPTIMIZED_KERNEL_DIR=cmsis_nn \
  microlite
```

编译后会生成：
- `gen/cortex_m_generic_cortex-m33/lib/libtensorflow-microlite.a`

### 方案3：暂时使用能量检测（最快）
先用当前的能量检测算法验证整个流程，等网络好了再集成 TFLite。

## 建议
由于 TFLite 集成比较耗时，建议：
1. 先用能量检测完成 M33→M55→ASR→WebSocket 流程验证
2. 等整个系统跑通后再回来集成 TFLite
3. 或者你手动下载 Infineon 库后我继续配置

## 下一步
你选择哪个方案？
