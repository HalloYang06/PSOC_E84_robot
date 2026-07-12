#include "bt_stack_adapter.h"
#include "bt_middleware.h"

static const char *g_bt_stack_missing_piece = "BT middleware library";

rt_err_t bt_stack_adapter_probe(bt_stack_probe_t *probe)
{
    rt_err_t err;
    const bt_middleware_runtime_t *mw;

    if (probe == RT_NULL)
    {
        return -RT_EINVAL;
    }

    rt_memset(probe, 0, sizeof(*probe));
    probe->board_support_present = RT_TRUE;
    err = bt_middleware_init();
    mw = bt_middleware_get_runtime();
    probe->middleware_present = (mw->backend != BT_MW_BACKEND_NONE) ? RT_TRUE : RT_FALSE;
    probe->porting_layer_present = (mw->state == BT_MW_STATE_READY) ? RT_TRUE : RT_FALSE;
    probe->spp_profile_present = mw->spp_supported;

    switch (mw->backend)
    {
    case BT_MW_BACKEND_WICED:
        probe->backend_name = "wiced";
        break;
    case BT_MW_BACKEND_BTSTACK:
        probe->backend_name = "btstack";
        break;
    case BT_MW_BACKEND_NONE:
    default:
        probe->backend_name = "none";
        break;
    }

    switch (mw->state)
    {
    case BT_MW_STATE_READY:
        probe->status = BT_STACK_STATUS_PRESENT;
        break;
    case BT_MW_STATE_PROFILE_REQUIRED:
        probe->status = BT_STACK_STATUS_PROFILE_REQUIRED;
        break;
    case BT_MW_STATE_PORTING_REQUIRED:
        probe->status = BT_STACK_STATUS_PORTING_REQUIRED;
        break;
    case BT_MW_STATE_UNAVAILABLE:
    default:
        probe->status = BT_STACK_STATUS_UNAVAILABLE;
        break;
    }

    g_bt_stack_missing_piece = bt_middleware_get_missing_piece();
    return err;
}

const char *bt_stack_adapter_missing_piece(void)
{
    return g_bt_stack_missing_piece;
}

#include <finsh.h>

static void bt_stack_probe_cmd(void)
{
    bt_stack_probe_t probe;
    rt_err_t err = bt_stack_adapter_probe(&probe);

    rt_kprintf("bt backend=%s status=%d err=%d board=%d middleware=%d porting=%d spp=%d missing=%s\n",
               probe.backend_name != RT_NULL ? probe.backend_name : "none",
               probe.status,
               err,
               probe.board_support_present,
               probe.middleware_present,
               probe.porting_layer_present,
               probe.spp_profile_present,
               bt_stack_adapter_missing_piece());
}
MSH_CMD_EXPORT(bt_stack_probe_cmd, show bluetooth middleware migration status);

