#include "bt_porting.h"

#include <finsh.h>

static bt_porting_profile_t g_bt_porting_profile;

rt_err_t bt_porting_init(void)
{
    rt_memset(&g_bt_porting_profile, 0, sizeof(g_bt_porting_profile));
    g_bt_porting_profile.rtt_kernel_available = RT_TRUE;
    g_bt_porting_profile.mutex_available = RT_TRUE;
    g_bt_porting_profile.thread_available = RT_TRUE;
    g_bt_porting_profile.tick_available = RT_TRUE;
    g_bt_porting_profile.hci_uart_hook_ready = RT_TRUE;
    g_bt_porting_profile.btstack_glue_ready = RT_TRUE;
    return RT_EOK;
}

const bt_porting_profile_t *bt_porting_get_profile(void)
{
    return &g_bt_porting_profile;
}

const char *bt_porting_get_missing_piece(void)
{
    if (!g_bt_porting_profile.btstack_glue_ready)
    {
        return "BTSTACK RT-Thread glue";
    }
    return "none";
}

void bt_porting_dump(void)
{
    const bt_porting_profile_t *p = bt_porting_get_profile();

    rt_kprintf("bt porting rtt=%d mutex=%d thread=%d tick=%d hci_uart=%d glue=%d missing=%s\n",
               p->rtt_kernel_available,
               p->mutex_available,
               p->thread_available,
               p->tick_available,
               p->hci_uart_hook_ready,
               p->btstack_glue_ready,
               bt_porting_get_missing_piece());
}
MSH_CMD_EXPORT(bt_porting_dump, show btstack RT-Thread porting status);
