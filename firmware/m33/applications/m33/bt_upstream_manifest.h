#ifndef APPLICATIONS_M33_BT_UPSTREAM_MANIFEST_H
#define APPLICATIONS_M33_BT_UPSTREAM_MANIFEST_H

#include <rtthread.h>

typedef struct
{
    const char *module_name;
    const char *upstream_hint;
    const char *local_target;
    const char *required_files;
    rt_bool_t mandatory;
} bt_upstream_manifest_entry_t;

const bt_upstream_manifest_entry_t *bt_upstream_manifest_get(rt_size_t *count);

#endif
