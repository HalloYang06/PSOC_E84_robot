#ifndef BAIDU_ASR_H
#define BAIDU_ASR_H

#include <rtthread.h>

#define BAIDU_ASR_MAX_TEXT_LEN 512

typedef void (*baidu_asr_callback_t)(const char *text, rt_err_t error);

rt_err_t baidu_asr_init(const char *api_key, const char *secret_key);
rt_bool_t baidu_asr_is_ready(void);
rt_err_t baidu_asr_recognize(const uint8_t *audio_data, uint32_t len, baidu_asr_callback_t callback);

#endif
