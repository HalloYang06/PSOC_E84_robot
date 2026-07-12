#include <rtthread.h>

#include "bt_source_template.h"

static const bt_source_template_entry_t g_template_entries[] = {
    {"core", "middleware/btstack_template/core", "Place upstream BTSTACK core protocol sources here"},
    {"port", "applications/m33/btstack_port", "Place RT-Thread BTSTACK glue sources here"},
    {"chipset", "middleware/btstack_template/chipset/cyw55", "Place CYW55 HCI chipset glue here"},
    {"profiles", "middleware/btstack_template/profiles/rfcomm_spp", "Place RFCOMM/SPP profile sources here"},
    {"config", "middleware/btstack_template/config", "Place Bluetooth Configurator outputs here"},
};

const bt_source_template_entry_t *bt_source_template_get(rt_size_t *count)
{
    if (count != RT_NULL)
    {
        *count = sizeof(g_template_entries) / sizeof(g_template_entries[0]);
    }

    return g_template_entries;
}

static void bt_source_template_dump(void)
{
    rt_size_t i;
    rt_size_t count;
    const bt_source_template_entry_t *entries = bt_source_template_get(&count);

    rt_kprintf("btstack template entries=%d\n", (int)count);
    for (i = 0; i < count; i++)
    {
        rt_kprintf("  [%d] %s path=%s note=%s\n",
                   (int)i,
                   entries[i].name,
                   entries[i].template_path,
                   entries[i].note);
    }
}
MSH_CMD_EXPORT(bt_source_template_dump, Dump BTSTACK source template mapping);
