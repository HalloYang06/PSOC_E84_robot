#include <rtthread.h>

#include "bt_source_entry.h"

static const bt_source_entry_t g_entries[] = {
    {
        "core-entry",
        "btstack_core_entry.c",
        "middleware/btstack_template/core",
        "Entry placeholder for BTSTACK core protocol integration",
        RT_TRUE
    },
    {
        "port-entry",
        "btstack_port_entry.c",
        "applications/m33/btstack_port",
        "Entry placeholder for RT-Thread BTSTACK port glue",
        RT_TRUE
    },
    {
        "chipset-entry",
        "btstack_chipset_cyw55_entry.c",
        "middleware/btstack_template/chipset/cyw55",
        "Entry placeholder for CYW55 HCI chipset glue",
        RT_TRUE
    },
    {
        "profile-entry",
        "btstack_rfcomm_spp_entry.c",
        "middleware/btstack_template/profiles/rfcomm_spp",
        "Entry placeholder for RFCOMM/SPP profile glue",
        RT_TRUE
    }
};

const bt_source_entry_t *bt_source_entry_get(rt_size_t *count)
{
    if (count != RT_NULL)
    {
        *count = sizeof(g_entries) / sizeof(g_entries[0]);
    }

    return g_entries;
}

rt_bool_t bt_source_entry_all_wired(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_source_entry_t *entries = bt_source_entry_get(&count);

    for (i = 0; i < count; i++)
    {
        if (!entries[i].wired_into_build)
        {
            return RT_FALSE;
        }
    }

    return RT_TRUE;
}

static void bt_source_entry_dump(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_source_entry_t *entries = bt_source_entry_get(&count);

    rt_kprintf("bt source entry wired=%d entries=%d\n",
               bt_source_entry_all_wired(),
               (int)count);

    for (i = 0; i < count; i++)
    {
        rt_kprintf("  [%d] %s wired=%d file=%s dir=%s purpose=%s\n",
                   (int)i,
                   entries[i].name,
                   entries[i].wired_into_build,
                   entries[i].entry_source,
                   entries[i].target_dir,
                   entries[i].purpose);
    }
}
MSH_CMD_EXPORT(bt_source_entry_dump, Dump minimal BTSTACK source entry placeholders);
