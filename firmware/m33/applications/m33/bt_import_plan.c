#include <rtthread.h>

#include "bt_import_plan.h"

static const bt_import_plan_step_t g_import_steps[] = {
    {
        "step-1-core",
        "Import the minimum BTSTACK core protocol set",
        "hci.c,l2cap.c,rfcomm.c,sdp_client.c,sdp_server.c plus required headers",
        "BTSTACK source integration reduced to porting/chipset gaps",
        RT_TRUE
    },
    {
        "step-2-chipset",
        "Import CYW55 controller glue",
        "CYW55 HCI transport glue, chipset init glue, controller patch helpers",
        "Controller family is represented in source tree",
        RT_TRUE
    },
    {
        "step-3-port",
        "Implement RT-Thread BTSTACK port layer",
        "run loop, memory hooks, mutex/thread/timer glue, UART hooks",
        "Missing piece moves from source integration to profile or runtime bring-up",
        RT_TRUE
    },
    {
        "step-4-profile",
        "Import RFCOMM/SPP profile glue",
        "SPP session layer, app bridge, service registration glue",
        "Bluetooth Classic SPP path can start integration testing",
        RT_TRUE
    },
    {
        "step-5-config",
        "Import Bluetooth Configurator outputs",
        "design.cybt and generated BT config sources",
        "Controller + stack have board-specific configuration inputs",
        RT_TRUE
    }
};

const bt_import_plan_step_t *bt_import_plan_get(rt_size_t *count)
{
    if (count != RT_NULL)
    {
        *count = sizeof(g_import_steps) / sizeof(g_import_steps[0]);
    }

    return g_import_steps;
}

static void bt_import_plan_dump(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_import_plan_step_t *steps = bt_import_plan_get(&count);

    rt_kprintf("bt import plan steps=%d\n", (int)count);
    for (i = 0; i < count; i++)
    {
        rt_kprintf("  [%d] %s blocking=%d\n", (int)i, steps[i].step_name, steps[i].blocking);
        rt_kprintf("      goal=%s\n", steps[i].goal);
        rt_kprintf("      import=%s\n", steps[i].import_scope);
        rt_kprintf("      success=%s\n", steps[i].success_state);
    }
}
MSH_CMD_EXPORT(bt_import_plan_dump, Dump minimum BTSTACK import plan);
