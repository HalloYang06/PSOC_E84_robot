#ifndef BT_PORTING_H
#define BT_PORTING_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
    rt_bool_t rtt_kernel_available;
    rt_bool_t mutex_available;
    rt_bool_t thread_available;
    rt_bool_t tick_available;
    rt_bool_t hci_uart_hook_ready;
    rt_bool_t btstack_glue_ready;
} bt_porting_profile_t;

rt_err_t bt_porting_init(void);
const bt_porting_profile_t *bt_porting_get_profile(void);
const char *bt_porting_get_missing_piece(void);
void bt_porting_dump(void);

#ifdef __cplusplus
}
#endif

#endif
