#include "bt_board_bridge.h"

#include <finsh.h>
#include "cycfg_connectivity_bt.h"

static bt_board_profile_t g_bt_board_profile;

rt_err_t bt_board_bridge_init(void)
{
    rt_memset(&g_bt_board_profile, 0, sizeof(g_bt_board_profile));
    g_bt_board_profile.hci_uart_enabled = RT_TRUE;
    g_bt_board_profile.low_power_enabled = CYCFG_BT_LP_ENABLED ? RT_TRUE : RT_FALSE;
    g_bt_board_profile.host_wake_supported = RT_TRUE;
    g_bt_board_profile.device_wake_supported = RT_TRUE;
    g_bt_board_profile.chip_name = "CYW55512/CYW55513";
    g_bt_board_profile.fw_family = "IFX_CYW55500A1";
    return RT_EOK;
}

const bt_board_profile_t *bt_board_bridge_get_profile(void)
{
    return &g_bt_board_profile;
}

void bt_board_bridge_dump(void)
{
    const bt_board_profile_t *p = bt_board_bridge_get_profile();

    rt_kprintf("bt board chip=%s fw=%s hci_uart=%d lp=%d host_wake=%d dev_wake=%d\n",
               p->chip_name,
               p->fw_family,
               p->hci_uart_enabled,
               p->low_power_enabled,
               p->host_wake_supported,
               p->device_wake_supported);
}
MSH_CMD_EXPORT(bt_board_bridge_dump, show bluetooth board bridge profile);
