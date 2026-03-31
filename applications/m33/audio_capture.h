#ifndef AUDIO_CAPTURE_H
#define AUDIO_CAPTURE_H

#include <rtthread.h>

#define AUDIO_SAMPLE_RATE 16000
#define AUDIO_CHANNELS 1
#define AUDIO_BITS_PER_SAMPLE 16
#define AUDIO_FRAME_MS 200
#define AUDIO_FRAME_SAMPLES (AUDIO_SAMPLE_RATE * AUDIO_FRAME_MS / 1000)
#define AUDIO_FRAME_BYTES (AUDIO_FRAME_SAMPLES * AUDIO_CHANNELS * AUDIO_BITS_PER_SAMPLE / 8)

typedef void (*audio_capture_callback_t)(const uint8_t *data, uint32_t len);

rt_err_t audio_capture_init(void);
rt_err_t audio_capture_start(audio_capture_callback_t callback);
rt_err_t audio_capture_stop(void);
rt_bool_t audio_capture_is_running(void);

#endif // AUDIO_CAPTURE_H
