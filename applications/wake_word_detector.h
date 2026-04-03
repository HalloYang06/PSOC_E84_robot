/*
 * wake_word_detector.h
 * 语音唤醒词检测器头文件
 */

#ifndef WAKE_WORD_DETECTOR_H
#define WAKE_WORD_DETECTOR_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// 音频参数
#define SAMPLE_RATE 16000
#define AUDIO_DURATION_MS 1000
#define N_MFCC 40
#define N_FRAMES 49
#define INPUT_SIZE (N_FRAMES * N_MFCC)
#define OUTPUT_SIZE 2

// 检测阈值
#define WAKE_WORD_THRESHOLD 0.5f

// 初始化检测器
bool WakeWordDetector_Init(void);

// 运行唤醒词检测
bool WakeWordDetector_Detect(const int16_t* audio_data, int audio_len, float* confidence);

// 获取模型信息
void WakeWordDetector_GetInfo(void);

#ifdef __cplusplus
}
#endif

#endif  // WAKE_WORD_DETECTOR_H
