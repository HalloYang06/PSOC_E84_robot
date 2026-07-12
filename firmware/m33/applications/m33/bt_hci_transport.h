#ifndef BT_HCI_TRANSPORT_H
#define BT_HCI_TRANSPORT_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    BT_HCI_STATE_UNINITIALIZED = 0,
    BT_HCI_STATE_READY,
    BT_HCI_STATE_STACK_MISSING,
    BT_HCI_STATE_RUNNING,
    BT_HCI_STATE_ERROR
} bt_hci_state_t;

typedef struct
{
    bt_hci_state_t state;
    rt_bool_t hci_uart_expected;
    rt_bool_t dual_mode_expected;
    rt_bool_t spp_expected;
    rt_err_t last_error;
} bt_hci_runtime_t;

rt_err_t bt_hci_transport_init(void);
rt_err_t bt_hci_transport_start(void);
const bt_hci_runtime_t *bt_hci_transport_get_runtime(void);
rt_bool_t bt_hci_transport_is_ready(void);

#ifdef __cplusplus
}
#endif

#endif
