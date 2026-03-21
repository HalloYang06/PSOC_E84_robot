#include <rtthread.h>

#include "bt_source_layout.h"

static const bt_source_group_t g_btstack_groups[] = {
    {"core", "BTSTACK protocol core", "middleware/btstack/src", RT_TRUE},
    {"port", "RT-Thread BTSTACK port layer", "applications/m33/btstack_port", RT_TRUE},
    {"chipset", "CYW55 HCI chipset glue", "middleware/btstack/chipset/cyw55", RT_TRUE},
    {"profiles", "RFCOMM/SPP profile set", "middleware/btstack/profiles/rfcomm_spp", RT_TRUE},
    {"config", "Bluetooth configurator outputs", "config/bluetooth/design.cybt + generated sources", RT_TRUE},
};

const bt_source_group_t *bt_source_layout_get(rt_size_t *count)
{
    if (count != RT_NULL)
    {
        *count = sizeof(g_btstack_groups) / sizeof(g_btstack_groups[0]);
    }

    return g_btstack_groups;
}

rt_bool_t bt_source_layout_is_complete(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_source_group_t *groups = bt_source_layout_get(&count);

    for (i = 0; i < count; i++)
    {
        if (groups[i].required)
        {
            return RT_FALSE;
        }
    }

    return RT_TRUE;
}

static void bt_source_layout_dump(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_source_group_t *groups = bt_source_layout_get(&count);

    rt_kprintf("btstack source layout complete=%d groups=%d\n",
               bt_source_layout_is_complete(),
               (int)count);

    for (i = 0; i < count; i++)
    {
        rt_kprintf("  [%d] %s required=%d path=%s purpose=%s\n",
                   (int)i,
                   groups[i].group_name,
                   groups[i].required,
                   groups[i].expected_path,
                   groups[i].purpose);
    }
}
MSH_CMD_EXPORT(bt_source_layout_dump, Dump planned BTSTACK source directory layout);
