#include <rtthread.h>

#include "bt_upstream_manifest.h"

static const bt_upstream_manifest_entry_t g_upstream_entries[] = {
    {
        "btstack-core",
        "Infineon/btstack: src + core protocol files",
        "middleware/btstack_template/core",
        "hci.c,l2cap.c,rfcomm.c,sdp_client.c,sdp_server.c",
        RT_TRUE
    },
    {
        "btstack-chipset-cyw55",
        "Infineon BTSTACK chipset glue for CYW55 controller family",
        "middleware/btstack_template/chipset/cyw55",
        "chipset init glue, HCI transport glue, controller patch helpers",
        RT_TRUE
    },
    {
        "btstack-port-rtthread",
        "RTOS port derived from BTSTACK FreeRTOS/ThreadX examples",
        "applications/m33/btstack_port",
        "run loop, memory hooks, UART hooks, mutex/thread/timer glue",
        RT_TRUE
    },
    {
        "btstack-rfcomm-spp",
        "Infineon RFCOMM/SPP example or equivalent profile sources",
        "middleware/btstack_template/profiles/rfcomm_spp",
        "spp service, rfcomm session glue, app bridge",
        RT_TRUE
    },
    {
        "bt-configurator-output",
        "Bluetooth Configurator outputs from ModusToolbox design.cybt",
        "middleware/btstack_template/config",
        "design.cybt, generated bt config sources, device database",
        RT_TRUE
    }
};

const bt_upstream_manifest_entry_t *bt_upstream_manifest_get(rt_size_t *count)
{
    if (count != RT_NULL)
    {
        *count = sizeof(g_upstream_entries) / sizeof(g_upstream_entries[0]);
    }

    return g_upstream_entries;
}

static void bt_upstream_manifest_dump(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_upstream_manifest_entry_t *entries = bt_upstream_manifest_get(&count);

    rt_kprintf("bt upstream manifest entries=%d\n", (int)count);
    for (i = 0; i < count; i++)
    {
        rt_kprintf("  [%d] %s mandatory=%d\n", (int)i, entries[i].module_name, entries[i].mandatory);
        rt_kprintf("      upstream=%s\n", entries[i].upstream_hint);
        rt_kprintf("      target=%s\n", entries[i].local_target);
        rt_kprintf("      files=%s\n", entries[i].required_files);
    }
}
MSH_CMD_EXPORT(bt_upstream_manifest_dump, Dump upstream BTSTACK integration manifest);
