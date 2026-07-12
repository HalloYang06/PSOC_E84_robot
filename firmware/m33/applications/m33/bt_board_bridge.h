#ifndef BT_BOARD_BRIDGE_H
#define BT_BOARD_BRIDGE_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
    rt_bool_t hci_uart_enabled;
    rt_bool_t low_power_enabled;
    rt_bool_t host_wake_supported;
    rt_bool_t device_wake_supported;
    const char *chip_name;
    const char *fw_family;
} bt_board_profile_t;

rt_err_t bt_board_bridge_init(void);
const bt_board_profile_t *bt_board_bridge_get_profile(void);
void bt_board_bridge_dump(void);

#ifdef __cplusplus
}
#endif

#endif
