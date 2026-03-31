#ifndef WAKE_WORD_MODEL_H
#define WAKE_WORD_MODEL_H

#ifdef __cplusplus
extern "C" {
#endif

// Hey Jarvis wake word model
extern unsigned char hey_jarvis_tflite[];
extern unsigned int hey_jarvis_tflite_len;

// Model configuration
#define WAKE_WORD_PROBABILITY_CUTOFF 0.85f
#define WAKE_WORD_SLIDING_WINDOW_SIZE 3
#define WAKE_WORD_TENSOR_ARENA_SIZE 65536

// Audio input configuration
#define WAKE_WORD_AUDIO_SAMPLE_RATE 16000
#define WAKE_WORD_AUDIO_FRAME_SIZE 320  // 20ms @ 16kHz

#ifdef __cplusplus
}
#endif

#endif // WAKE_WORD_MODEL_H
