#ifndef APPLICATIONS_M33_BT_SOURCE_MANIFEST_H
#define APPLICATIONS_M33_BT_SOURCE_MANIFEST_H

#include <rtthread.h>

typedef struct
{
    const char *name;
    rt_bool_t integrated;
    const char *missing_reason;
} bt_source_component_t;

typedef struct
{
    const char *backend_name;
    const bt_source_component_t *components;
    rt_size_t component_count;
} bt_source_manifest_t;

const bt_source_manifest_t *bt_source_manifest_get(void);
rt_bool_t bt_source_manifest_is_ready(void);

#endif
