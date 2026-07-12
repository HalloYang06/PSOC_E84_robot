#ifndef APPLICATIONS_M33_BT_SOURCE_ENTRY_H
#define APPLICATIONS_M33_BT_SOURCE_ENTRY_H

#include <rtthread.h>

typedef struct
{
    const char *name;
    const char *entry_source;
    const char *target_dir;
    const char *purpose;
    rt_bool_t wired_into_build;
} bt_source_entry_t;

const bt_source_entry_t *bt_source_entry_get(rt_size_t *count);
rt_bool_t bt_source_entry_all_wired(void);

#endif
