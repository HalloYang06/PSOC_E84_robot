#ifndef APPLICATIONS_M33_BT_SOURCE_LAYOUT_H
#define APPLICATIONS_M33_BT_SOURCE_LAYOUT_H

#include <rtthread.h>

typedef struct
{
    const char *group_name;
    const char *purpose;
    const char *expected_path;
    rt_bool_t required;
} bt_source_group_t;

const bt_source_group_t *bt_source_layout_get(rt_size_t *count);
rt_bool_t bt_source_layout_is_complete(void);

#endif
