#ifndef BT_MIDDLEWARE_H
#define BT_MIDDLEWARE_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    BT_MW_BACKEND_NONE = 0,
    BT_MW_BACKEND_WICED,
    BT_MW_BACKEND_BTSTACK
} bt_middleware_backend_t;

typedef enum
{
    BT_MW_STATE_UNAVAILABLE = 0,
    BT_MW_STATE_PORTING_REQUIRED,
    BT_MW_STATE_PROFILE_REQUIRED,
    BT_MW_STATE_READY
} bt_middleware_state_t;

typedef struct
{
    bt_middleware_backend_t backend;
    bt_middleware_state_t state;
    rt_bool_t classic_supported;
    rt_bool_t ble_supported;
    rt_bool_t spp_supported;
    const char *missing_piece;
} bt_middleware_runtime_t;

rt_err_t bt_middleware_init(void);
const bt_middleware_runtime_t *bt_middleware_get_runtime(void);
const char *bt_middleware_get_missing_piece(void);

#ifdef __cplusplus
}
#endif

#endif
