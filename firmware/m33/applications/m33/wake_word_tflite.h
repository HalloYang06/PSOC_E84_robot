#ifndef WAKE_WORD_TFLITE_H
#define WAKE_WORD_TFLITE_H

#include <stdint.h>
#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

// 初始化 TFLite 唤醒词检测
rt_err_t wake_word_tflite_init(void);

// 检测唤醒词
// audio_data: 音频数据 (int16_t, 16kHz, mono)
// len: 样本数量
// 返回: RT_TRUE 表示检测到唤醒词
rt_bool_t wake_word_tflite_detect(const int16_t* audio_data, uint32_t len);

#ifdef __cplusplus
}
#endif

#endif // WAKE_WORD_TFLITE_H
