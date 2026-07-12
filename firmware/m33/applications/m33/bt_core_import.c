#include <rtthread.h>

#include "bt_core_import.h"

static const bt_core_import_item_t g_core_items[] = {
    {"hci.c", "Host controller interface core", "middleware/btstack_template/core", RT_TRUE},
    {"l2cap.c", "L2CAP channel management", "middleware/btstack_template/core", RT_TRUE},
    {"rfcomm.c", "Bluetooth Classic RFCOMM transport", "middleware/btstack_template/core", RT_TRUE},
    {"sdp_client.c", "Service discovery client", "middleware/btstack_template/core", RT_TRUE},
    {"sdp_server.c", "Service discovery server", "middleware/btstack_template/core", RT_TRUE},
};

const bt_core_import_item_t *bt_core_import_get(rt_size_t *count)
{
    if (count != RT_NULL)
    {
        *count = sizeof(g_core_items) / sizeof(g_core_items[0]);
    }

    return g_core_items;
}

static void bt_core_import_dump(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_core_import_item_t *items = bt_core_import_get(&count);

    rt_kprintf("bt core import items=%d\n", (int)count);
    for (i = 0; i < count; i++)
    {
        rt_kprintf("  [%d] %s required=%d dir=%s role=%s\n",
                   (int)i,
                   items[i].file_name,
                   items[i].required,
                   items[i].target_dir,
                   items[i].role);
    }
}
MSH_CMD_EXPORT(bt_core_import_dump, Dump first-wave BTSTACK core import list);
