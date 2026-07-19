#ifndef BT_HCI_TRANSPORT_H
#define BT_HCI_TRANSPORT_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    BT_HCI_STATE_OFF = 0,
    BT_HCI_STATE_STARTING,
    BT_HCI_STATE_READY,
    BT_HCI_STATE_FAILED
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
void bt_hci_transport_report_enabled(rt_err_t status);
void bt_hci_transport_report_disabled(void);
rt_err_t bt_hci_transport_get_runtime_snapshot(bt_hci_runtime_t *runtime);
rt_bool_t bt_hci_transport_is_ready(void);

#ifdef __cplusplus
}
#endif

#endif
