#ifndef VOICE_SERVICE_H
#define VOICE_SERVICE_H

#include <rtthread.h>
#include "m33_m55_comm.h"

rt_err_t voice_service_init(const char *baidu_api_key, const char *baidu_secret_key);
rt_err_t voice_service_start(void);
rt_err_t voice_service_stop(void);
rt_bool_t voice_service_is_running(void);
rt_err_t voice_service_request_capture_start(void);
rt_err_t voice_service_request_capture_stop(void);
rt_err_t voice_service_request_listen_start(void);
rt_err_t voice_service_request_listen_stop(void);
rt_err_t voice_service_set_wake_listening_direct(rt_bool_t enable);
rt_err_t voice_service_dump_latest_pcm(const char *path);
rt_err_t voice_service_prepare_xiaozhi_socket(void);
rt_err_t voice_service_reconnect_xiaozhi(void);
rt_err_t voice_service_submit_local_pcm(const rt_uint8_t *pcm, rt_uint32_t len);
rt_err_t voice_service_start_xiaozhi_talk(void);
rt_err_t voice_service_stop_xiaozhi_talk(void);
rt_err_t voice_service_abort_xiaozhi_talk_local(void);
rt_bool_t voice_service_xiaozhi_is_listening(void);
rt_err_t voice_service_publish_status_now(void);
rt_uint32_t voice_service_bridge_diag_loops(void);
rt_uint32_t voice_service_bridge_diag_consumed(void);
rt_int32_t voice_service_bridge_diag_last_ret(void);
rt_int32_t voice_service_bridge_diag_phase(void);
void voice_service_note_error(rt_err_t error);
void voice_service_handle_ipc_message(const m33_m55_message_t *msg);

#endif // VOICE_SERVICE_H
