# Porcupine 唤醒词集成步骤

## 1. 注册并获取 Access Key
- 访问 https://console.picovoice.ai/
- 注册账号（免费）
- 获取 Access Key

## 2. 训练自定义唤醒词
- 在控制台选择 "Porcupine"
- 点击 "Train Custom Wake Word"
- 输入唤醒词：守望者 (shou wang zhe)
- 选择语言：Chinese (Mandarin)
- 训练完成后下载 .ppn 文件

## 3. 下载 Porcupine SDK
- 访问 https://github.com/Picovoice/porcupine
- 下载 ARM Cortex-M 版本
- 需要的文件：
  - lib/cortex-m33/libpv_porcupine.a (静态库)
  - include/pv_porcupine.h (头文件)
  - 你训练的 .ppn 模型文件

## 4. 集成到项目
```c
#include "pv_porcupine.h"

// 初始化
pv_porcupine_t *porcupine = NULL;
const char *access_key = "YOUR_ACCESS_KEY";
const char *model_path = "/path/to/守望者.ppn";

pv_status_t status = pv_porcupine_init(
    access_key,
    1,              // 唤醒词数量
    &model_path,    // 模型路径
    &sensitivity,   // 灵敏度 0.0-1.0
    &porcupine
);

// 处理音频帧（512 samples, 16kHz, 16bit, mono）
int16_t pcm[512];
int32_t keyword_index = -1;

status = pv_porcupine_process(porcupine, pcm, &keyword_index);
if (keyword_index >= 0) {
    // 检测到唤醒词！
}

// 清理
pv_porcupine_delete(porcupine);
```

## 5. 修改 voice_trigger.c
替换当前的能量检测算法为 Porcupine API 调用

## 注意事项
- Porcupine 需要固定帧长：512 samples (32ms @ 16kHz)
- 需要调整 audio_capture.c 的 AUDIO_FRAME_BYTES
- 免费版有并发限制，商用需要付费授权
