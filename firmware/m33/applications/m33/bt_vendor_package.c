#include <rtthread.h>

#include "bt_vendor_package.h"

static const bt_vendor_package_item_t g_vendor_items[] = {
    {"btstack-wiced-include", "vendor_btstack/btstack/wiced_include", RT_TRUE},
    {"btstack-hci-uart-integration", "vendor_btstack/btstack_integration/COMPONENT_HCI-UART", RT_TRUE},
    {"btstack-abstraction-rtos", "vendor_btstack/abstraction_rtos/include", RT_TRUE},
    {"btstack-lib-cm33-dualmode-gcc", "vendor_btstack/lib/COMPONENT_CM33/COMPONENT_SOFTFP/TOOLCHAIN_GCC_ARM/libbtstack.a", RT_TRUE},
    {"btstack-config-seed", "vendor_btstack/config_seed", RT_FALSE},
};

const bt_vendor_package_item_t *bt_vendor_package_get(rt_size_t *count)
{
    if (count != RT_NULL)
    {
        *count = sizeof(g_vendor_items) / sizeof(g_vendor_items[0]);
    }

    return g_vendor_items;
}

rt_bool_t bt_vendor_package_is_imported(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_vendor_package_item_t *items = bt_vendor_package_get(&count);

    for (i = 0; i < count; i++)
    {
        if (!items[i].imported)
        {
            return RT_FALSE;
        }
    }

    return RT_TRUE;
}

rt_bool_t bt_vendor_package_is_build_wiring_ready(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_vendor_package_item_t *items = bt_vendor_package_get(&count);

    for (i = 0; i < count; i++)
    {
        if (rt_strcmp(items[i].name, "btstack-config-seed") == 0)
        {
            continue;
        }

        if (!items[i].imported)
        {
            return RT_FALSE;
        }
    }

    return RT_TRUE;
}

static void bt_vendor_package_dump(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_vendor_package_item_t *items = bt_vendor_package_get(&count);

    rt_kprintf("bt vendor package imported=%d items=%d\n",
               bt_vendor_package_is_imported(),
               (int)count);
    rt_kprintf("bt vendor package build_wiring_ready=%d\n",
               bt_vendor_package_is_build_wiring_ready());
    for (i = 0; i < count; i++)
    {
        rt_kprintf("  [%d] %s imported=%d path=%s\n",
                   (int)i,
                   items[i].name,
                   items[i].imported,
                   items[i].local_path);
    }
}
MSH_CMD_EXPORT(bt_vendor_package_dump, Dump imported official BTSTACK package assets);

