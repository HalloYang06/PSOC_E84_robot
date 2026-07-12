#ifndef BAIDU_TTS_H
#define BAIDU_TTS_H

#include <rtthread.h>

typedef void (*baidu_tts_callback_t)(const uint8_t *audio_data, uint32_t len, rt_err_t error);

rt_err_t baidu_tts_init(const char *api_key, const char *secret_key);
rt_bool_t baidu_tts_is_ready(void);
rt_err_t baidu_tts_synthesize(const char *text, baidu_tts_callback_t callback);

#endif
