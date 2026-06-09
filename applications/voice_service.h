#ifndef VOICE_SERVICE_H
#define VOICE_SERVICE_H

#include <rtthread.h>

rt_err_t voice_service_init(const char *baidu_api_key, const char *baidu_secret_key);
rt_err_t voice_service_start(void);
rt_err_t voice_service_stop(void);
rt_err_t voice_service_request_capture_start(void);
rt_err_t voice_service_request_capture_stop(void);
rt_err_t voice_service_request_listen_start(void);
rt_err_t voice_service_request_listen_stop(void);
rt_err_t voice_service_dump_latest_pcm(const char *path);
rt_err_t voice_service_reconnect_xiaozhi(void);

#endif // VOICE_SERVICE_H
