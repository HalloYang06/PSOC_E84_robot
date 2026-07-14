#ifndef __SMIF0_GUARD_CLIENT_H__
#define __SMIF0_GUARD_CLIENT_H__

#include <stdint.h>

#include <rtthread.h>

#include "smif0_guard_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

rt_err_t smif0_guard_client_init(void);
rt_err_t smif0_guard_client_lock(void);
void smif0_guard_client_unlock(void);
rt_err_t smif0_guard_client_acquire(smif0_guard_operation_t operation,
                                    uint32_t address,
                                    uint32_t length,
                                    uint32_t *request_seq_out);
rt_err_t smif0_guard_client_release(uint32_t request_seq);

#ifdef __cplusplus
}
#endif

#endif /* __SMIF0_GUARD_CLIENT_H__ */
