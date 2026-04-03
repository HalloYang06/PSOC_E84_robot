/*
 * audio_processing.cc
 * 音频处理和 MFCC 特征提取实现
 */

#include "audio_processing.h"
#include <math.h>
#include <string.h>
#include <stdio.h>

// ARM CMSIS-DSP (如果可用)
#ifdef USE_CMSIS_DSP
#include "arm_math.h"
#endif

// 常量
#define PI 3.14159265358979323846f
#define PRE_EMPHASIS_COEFF 0.97f

// 初始化音频处理
bool AudioProcessing_Init(void) {
    printf("Audio processing initialized\n");
    return true;
}

// 预加重滤波
void AudioProcessing_PreEmphasis(const int16_t* input,
                                  float* output,
                                  int length,
                                  float coeff) {
    output[0] = (float)input[0];
    for (int i = 1; i < length; i++) {
        output[i] = (float)input[i] - coeff * (float)input[i - 1];
    }
}

// 汉明窗
static void apply_hamming_window(float* frame, int frame_size) {
    for (int i = 0; i < frame_size; i++) {
        float window = 0.54f - 0.46f * cosf(2.0f * PI * i / (frame_size - 1));
        frame[i] *= window;
    }
}

// 简化的 FFT (实际应使用 CMSIS-DSP 或 KissFFT)
static void simple_fft(const float* input, float* magnitude, int fft_size) {
    // TODO: 实现 FFT 或使用库
    // 这里是占位符，实际需要使用 ARM CMSIS-DSP 的 arm_rfft_fast_f32
    // 或者 KissFFT 库

#ifdef USE_CMSIS_DSP
    arm_rfft_fast_instance_f32 fft_instance;
    arm_rfft_fast_init_f32(&fft_instance, fft_size);

    float fft_output[fft_size * 2];
    arm_rfft_fast_f32(&fft_instance, (float*)input, fft_output, 0);

    // 计算幅度谱
    for (int i = 0; i < fft_size / 2; i++) {
        float real = fft_output[i * 2];
        float imag = fft_output[i * 2 + 1];
        magnitude[i] = sqrtf(real * real + imag * imag);
    }
#else
    // 占位符：简单的能量计算
    for (int i = 0; i < fft_size / 2; i++) {
        magnitude[i] = fabsf(input[i % fft_size]);
    }
#endif
}

// Mel 滤波器组
static void apply_mel_filterbank(const float* power_spectrum,
                                   float* mel_energies,
                                   int n_fft,
                                   int n_mels,
                                   int sample_rate) {
    // Mel 刻度转换
    auto hz_to_mel = [](float hz) {
        return 2595.0f * log10f(1.0f + hz / 700.0f);
    };

    auto mel_to_hz = [](float mel) {
        return 700.0f * (powf(10.0f, mel / 2595.0f) - 1.0f);
    };

    // 创建 Mel 滤波器
    float mel_min = hz_to_mel(0);
    float mel_max = hz_to_mel(sample_rate / 2.0f);

    // 简化实现：线性加权
    for (int m = 0; m < n_mels; m++) {
        float mel_energy = 0.0f;
        int start_bin = (m * n_fft) / (n_mels * 2);
        int end_bin = ((m + 1) * n_fft) / (n_mels * 2);

        for (int i = start_bin; i < end_bin && i < n_fft / 2; i++) {
            mel_energy += power_spectrum[i];
        }

        mel_energies[m] = log10f(mel_energy + 1e-10f);  // 对数能量
    }
}

// DCT (离散余弦变换)
static void apply_dct(const float* mel_energies, float* mfcc, int n_mels, int n_mfcc) {
    for (int i = 0; i < n_mfcc; i++) {
        float sum = 0.0f;
        for (int j = 0; j < n_mels; j++) {
            sum += mel_energies[j] * cosf(PI * i * (j + 0.5f) / n_mels);
        }
        mfcc[i] = sum;
    }
}

// 提取 MFCC 特征
bool AudioProcessing_ExtractMFCC(const int16_t* audio_data,
                                  int audio_len,
                                  float* mfcc_output,
                                  int n_frames,
                                  int n_mfcc) {
    if (audio_data == nullptr || mfcc_output == nullptr) {
        return false;
    }

    // 预加重
    float* emphasized = new float[audio_len];
    AudioProcessing_PreEmphasis(audio_data, emphasized, audio_len, PRE_EMPHASIS_COEFF);

    // 分帧处理
    int frame_size = FFT_SIZE;
    int hop_length = HOP_LENGTH;

    for (int frame_idx = 0; frame_idx < n_frames; frame_idx++) {
        int start = frame_idx * hop_length;
        if (start + frame_size > audio_len) {
            break;
        }

        // 提取当前帧
        float frame[FFT_SIZE] = {0};
        memcpy(frame, emphasized + start, frame_size * sizeof(float));

        // 加窗
        apply_hamming_window(frame, frame_size);

        // FFT
        float magnitude[FFT_SIZE / 2];
        simple_fft(frame, magnitude, FFT_SIZE);

        // 功率谱
        float power_spectrum[FFT_SIZE / 2];
        for (int i = 0; i < FFT_SIZE / 2; i++) {
            power_spectrum[i] = magnitude[i] * magnitude[i];
        }

        // Mel 滤波器组
        float mel_energies[N_MEL_FILTERS];
        apply_mel_filterbank(power_spectrum, mel_energies,
                            FFT_SIZE, N_MEL_FILTERS, 16000);

        // DCT 得到 MFCC
        float* mfcc_frame = mfcc_output + frame_idx * n_mfcc;
        apply_dct(mel_energies, mfcc_frame, N_MEL_FILTERS, n_mfcc);
    }

    delete[] emphasized;
    return true;
}

// 分帧加窗
void AudioProcessing_FrameWindow(const float* input,
                                  float* output,
                                  int frame_size,
                                  int hop_length,
                                  int n_frames) {
    for (int i = 0; i < n_frames; i++) {
        int start = i * hop_length;
        float* frame = output + i * frame_size;

        // 复制帧
        memcpy(frame, input + start, frame_size * sizeof(float));

        // 加窗
        apply_hamming_window(frame, frame_size);
    }
}
