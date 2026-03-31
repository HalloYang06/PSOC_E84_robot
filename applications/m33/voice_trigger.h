#ifndef VOICE_TRIGGER_H
#define VOICE_TRIGGER_H

#include <rtthread.h>

#define MAX_RECORDING_DURATION_MS 10000
#define MAX_RECORDING_BYTES ((AUDIO_SAMPLE_RATE * MAX_RECORDING_DURATION_MS / 1000) * 2)

typedef void (*voice_trigger_callback_t)(const uint8_t *audio_data, uint32_t len);

rt_err_t voice_trigger_init(void);
rt_err_t voice_trigger_start(voice_trigger_callback_t callback);
rt_err_t voice_trigger_stop(void);
rt_err_t voice_trigger_force_record(void);
rt_err_t voice_trigger_force_finish(void);

#endif // VOICE_TRIGGER_H
