#ifndef REHAB_WIFI_PANEL_H
#define REHAB_WIFI_PANEL_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

rt_err_t rehab_wifi_panel_create(void);
void rehab_wifi_panel_note_ble_status(rt_bool_t connected, rt_uint32_t link_seq);

#ifdef __cplusplus
}
#endif

#endif
