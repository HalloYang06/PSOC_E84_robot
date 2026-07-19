#ifndef __VOICE_REHAB_IPC_BRIDGE_H__
#define __VOICE_REHAB_IPC_BRIDGE_H__

#include <rtthread.h>

#include "m33_m55_comm.h"

#ifdef __cplusplus
extern "C" {
#endif

#define VOICE_REHAB_IPC_QUEUE_DEPTH 4U

typedef struct
{
    rt_uint32_t total;
    rt_uint32_t accepted;
    rt_uint32_t invalid;
    rt_uint32_t queue_full;
    rt_uint32_t processed;
    rt_uint32_t applied;
    rt_uint32_t rejected;
    rt_uint32_t recv_fail;
    rt_uint32_t result_publish_fail;
    rt_uint32_t last_request_id;
    rt_uint32_t last_result;
    rt_uint32_t last_detail;
    rt_tick_t last_receive_tick;
} voice_rehab_ipc_bridge_diag_t;

rt_err_t voice_rehab_ipc_bridge_init(void);
rt_err_t voice_rehab_ipc_bridge_submit(const rehab_mode_request_msg_t *request);
void voice_rehab_ipc_bridge_diag_snapshot(voice_rehab_ipc_bridge_diag_t *out);

#ifdef __cplusplus
}
#endif

#endif /* __VOICE_REHAB_IPC_BRIDGE_H__ */
