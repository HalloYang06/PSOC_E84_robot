#include "bt_middleware.h"
#include "bt_porting.h"
#include "bt_source_manifest.h"
#include "bt_vendor_package.h"

static bt_middleware_runtime_t g_bt_middleware_runtime;

rt_err_t bt_middleware_init(void)
{
    const bt_porting_profile_t *porting;

    rt_memset(&g_bt_middleware_runtime, 0, sizeof(g_bt_middleware_runtime));

#if defined(COMPONENT_WICED_DUALMODE)
    g_bt_middleware_runtime.backend = BT_MW_BACKEND_WICED;
    g_bt_middleware_runtime.state = BT_MW_STATE_PORTING_REQUIRED;
    g_bt_middleware_runtime.classic_supported = RT_TRUE;
    g_bt_middleware_runtime.ble_supported = RT_TRUE;
    g_bt_middleware_runtime.spp_supported = RT_TRUE;
    g_bt_middleware_runtime.missing_piece = "RT-Thread porting layer";
    return -RT_ENOSYS;
#elif defined(COMPONENT_WICED_BLE)
    g_bt_middleware_runtime.backend = BT_MW_BACKEND_WICED;
    g_bt_middleware_runtime.state = BT_MW_STATE_PROFILE_REQUIRED;
    g_bt_middleware_runtime.classic_supported = RT_FALSE;
    g_bt_middleware_runtime.ble_supported = RT_TRUE;
    g_bt_middleware_runtime.spp_supported = RT_FALSE;
    g_bt_middleware_runtime.missing_piece = "Bluetooth Classic / RFCOMM profile";
    return -RT_ENOSYS;
#elif defined(PKG_USING_BTSTACK)
    g_bt_middleware_runtime.backend = BT_MW_BACKEND_BTSTACK;
    g_bt_middleware_runtime.state = BT_MW_STATE_PORTING_REQUIRED;
    g_bt_middleware_runtime.classic_supported = RT_TRUE;
    g_bt_middleware_runtime.ble_supported = RT_TRUE;
    g_bt_middleware_runtime.spp_supported = RT_TRUE;
    g_bt_middleware_runtime.missing_piece = "RT-Thread BTSTACK porting layer";
    return -RT_ENOSYS;
#else
    bt_porting_init();
    porting = bt_porting_get_profile();

    g_bt_middleware_runtime.backend = BT_MW_BACKEND_BTSTACK;
    g_bt_middleware_runtime.classic_supported = RT_TRUE;
    g_bt_middleware_runtime.ble_supported = RT_TRUE;
    g_bt_middleware_runtime.spp_supported = RT_TRUE;

    if (!bt_vendor_package_is_build_wiring_ready())
    {
        g_bt_middleware_runtime.state = BT_MW_STATE_PORTING_REQUIRED;
        g_bt_middleware_runtime.missing_piece = "BTSTACK source integration";
        return -RT_ENOSYS;
    }

    if (!porting->btstack_glue_ready)
    {
        g_bt_middleware_runtime.state = BT_MW_STATE_PORTING_REQUIRED;
        g_bt_middleware_runtime.missing_piece = "RT-Thread BTSTACK porting layer";
        return -RT_ENOSYS;
    }

    g_bt_middleware_runtime.state = BT_MW_STATE_READY;
    g_bt_middleware_runtime.missing_piece = "none";
    return RT_EOK;
#endif
}

const bt_middleware_runtime_t *bt_middleware_get_runtime(void)
{
    return &g_bt_middleware_runtime;
}

const char *bt_middleware_get_missing_piece(void)
{
    return g_bt_middleware_runtime.missing_piece != RT_NULL ?
           g_bt_middleware_runtime.missing_piece :
           "BT middleware library";
}
