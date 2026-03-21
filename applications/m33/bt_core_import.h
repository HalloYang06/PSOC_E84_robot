#ifndef APPLICATIONS_M33_BT_CORE_IMPORT_H
#define APPLICATIONS_M33_BT_CORE_IMPORT_H

#include <rtthread.h>

typedef struct
{
    const char *file_name;
    const char *role;
    const char *target_dir;
    rt_bool_t required;
} bt_core_import_item_t;

const bt_core_import_item_t *bt_core_import_get(rt_size_t *count);

#endif
