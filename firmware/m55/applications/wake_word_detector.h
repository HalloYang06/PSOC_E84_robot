#ifndef WAKE_WORD_DETECTOR_H
#define WAKE_WORD_DETECTOR_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SAMPLE_RATE 16000
#define AUDIO_DURATION_MS 1000
#define N_MFCC 40
#define N_FRAMES 49
#define INPUT_SIZE (N_FRAMES * N_MFCC)
#define OUTPUT_SIZE 2

#define WAKE_WORD_THRESHOLD 0.5f

bool WakeWordDetector_Init(void);
bool WakeWordDetector_Detect(const int16_t *audio_data, int audio_len, float *confidence);
void WakeWordDetector_GetInfo(void);
bool WakeWordDetector_DumpFeatures(const char *path);

#ifdef __cplusplus
}
#endif

#endif
