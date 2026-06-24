#ifndef OFFICIAL_VOICE_SERVICE_H
#define OFFICIAL_VOICE_SERVICE_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

rt_err_t official_voice_pdm_self_test(rt_uint32_t duration_ms, rt_bool_t publish_on_activity);
rt_err_t official_voice_speaker_beep(rt_uint32_t duration_ms);
rt_err_t official_voice_speaker_play_pcm(const rt_int16_t *pcm, rt_uint32_t sample_count);
void official_voice_dump_status(void);

#ifdef __cplusplus
}
#endif

#endif
