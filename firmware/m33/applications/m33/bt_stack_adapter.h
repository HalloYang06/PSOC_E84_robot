#ifndef BT_STACK_ADAPTER_H
#define BT_STACK_ADAPTER_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    BT_STACK_STATUS_UNAVAILABLE = 0,
    BT_STACK_STATUS_PRESENT,
    BT_STACK_STATUS_PORTING_REQUIRED,
    BT_STACK_STATUS_PROFILE_REQUIRED
} bt_stack_status_t;

typedef struct
{
    bt_stack_status_t status;
    rt_bool_t board_support_present;
    rt_bool_t middleware_present;
    rt_bool_t porting_layer_present;
    rt_bool_t spp_profile_present;
    const char *backend_name;
} bt_stack_probe_t;

rt_err_t bt_stack_adapter_probe(bt_stack_probe_t *probe);
const char *bt_stack_adapter_missing_piece(void);

#ifdef __cplusplus
}
#endif

#endif
