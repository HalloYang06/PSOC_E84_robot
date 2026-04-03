/*
 * audio_processing.h
 * 音频处理和 MFCC 特征提取
 */

#ifndef AUDIO_PROCESSING_H
#define AUDIO_PROCESSING_H

#include <stdint.h>
#include <stdbool.h>

// MFCC 参数
#define FFT_SIZE 512
#define HOP_LENGTH 160
#define N_MEL_FILTERS 40

// 初始化音频处理
bool AudioProcessing_Init(void);

// 提取 MFCC 特征
// audio_data: 输入音频数据 (16-bit PCM)
// audio_len: 音频长度
// mfcc_output: 输出 MFCC 特征 [n_frames * n_mfcc]
// n_frames: 时间帧数
// n_mfcc: MFCC 系数数量
bool AudioProcessing_ExtractMFCC(const int16_t* audio_data,
                                  int audio_len,
                                  float* mfcc_output,
                                  int n_frames,
                                  int n_mfcc);

// 预加重滤波
void AudioProcessing_PreEmphasis(const int16_t* input,
                                  float* output,
                                  int length,
                                  float coeff);

// 分帧加窗
void AudioProcessing_FrameWindow(const float* input,
                                  float* output,
                                  int frame_size,
                                  int hop_length,
                                  int n_frames);

#endif  // AUDIO_PROCESSING_H
