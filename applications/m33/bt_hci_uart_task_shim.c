#include <rtthread.h>
#include "cybt_platform_task.h"

/* Real cybt_send_msg_to_hci_rx_task is now provided by bt_hci_uart_rx_task.c. */
static void bt_hci_uart_task_shim_placeholder(void)
{
    RT_UNUSED(BT_IND_TO_APP_SERIALIZATION);
}
