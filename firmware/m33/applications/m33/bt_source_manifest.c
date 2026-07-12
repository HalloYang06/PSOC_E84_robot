#include <rtthread.h>

#include "bt_source_manifest.h"
#include "bt_source_layout.h"

static const bt_source_component_t g_btstack_components[] = {
    {"btstack-core", RT_FALSE, "BTSTACK core sources are not integrated"},
    {"btstack-port", RT_FALSE, "RT-Thread BTSTACK port sources are not integrated"},
    {"btstack-chipset-cyw55", RT_FALSE, "CYW55 HCI chipset glue is not integrated"},
    {"btstack-rfcomm-spp", RT_FALSE, "RFCOMM/SPP profile sources are not integrated"},
};

const bt_source_manifest_t *bt_source_manifest_get(void)
{
    static const bt_source_manifest_t manifest = {
        "btstack",
        g_btstack_components,
        sizeof(g_btstack_components) / sizeof(g_btstack_components[0])
    };

    return &manifest;
}

rt_bool_t bt_source_manifest_is_ready(void)
{
    rt_size_t i;
    const bt_source_manifest_t *manifest = bt_source_manifest_get();

    for (i = 0; i < manifest->component_count; i++)
    {
        if (!manifest->components[i].integrated)
        {
            return RT_FALSE;
        }
    }

    return RT_TRUE;
}

static void bt_source_manifest_dump(void)
{
    rt_size_t i;
    const bt_source_manifest_t *manifest = bt_source_manifest_get();

    rt_kprintf("bt source backend=%s ready=%d components=%d\n",
               manifest->backend_name,
               bt_source_manifest_is_ready(),
               (int)manifest->component_count);

    for (i = 0; i < manifest->component_count; i++)
    {
        const bt_source_component_t *component = &manifest->components[i];
        rt_kprintf("  [%d] %s integrated=%d missing=%s\n",
                   (int)i,
                   component->name,
                   component->integrated,
                   component->missing_reason);
    }
}
MSH_CMD_EXPORT(bt_source_manifest_dump, Dump BTSTACK source integration manifest);

