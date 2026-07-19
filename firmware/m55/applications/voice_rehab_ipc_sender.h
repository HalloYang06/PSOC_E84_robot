#ifndef VOICE_REHAB_IPC_SENDER_H
#define VOICE_REHAB_IPC_SENDER_H

#include <rtthread.h>

#include "m33_m55_comm.h"

#ifdef __cplusplus
extern "C" {
#endif

#define VOICE_REHAB_EVENT_HISTORY_DEPTH 8U
#define VOICE_REHAB_PENDING_DEPTH 8U

typedef struct
{
    rt_uint32_t published;
    rt_uint32_t publish_failed;
    rt_uint32_t duplicate_event;
    rt_uint32_t conflicting_event;
    rt_uint32_t invalid_intent;
    rt_uint32_t pending_full;
    rt_uint32_t result_received;
    rt_uint32_t result_foreign;
    rt_uint32_t result_unknown;
    rt_uint32_t result_duplicate;
    rt_uint32_t result_timeout;
    rt_uint32_t boot_epoch;
    rt_uint32_t last_request_id;
    rt_uint32_t last_result_status;
    rt_uint32_t last_result_detail;
    rt_uint32_t last_applied_mode;
    rt_uint32_t last_mode_generation;
    rt_uint32_t last_result_rtt_ms;
} voice_rehab_ipc_sender_diag_t;

rt_err_t voice_rehab_ipc_sender_init(void);
rt_err_t voice_rehab_ipc_sender_submit_vla(const char *event_id,
                                           const char *payload,
                                           rt_uint32_t *request_id);
void voice_rehab_ipc_sender_handle_result(const rehab_mode_result_msg_t *result);
void voice_rehab_ipc_sender_diag_snapshot(voice_rehab_ipc_sender_diag_t *out);

#ifdef __cplusplus
}
#endif

#endif /* VOICE_REHAB_IPC_SENDER_H */
