#ifndef APPLICATIONS_M33_BT_SOURCE_TEMPLATE_H
#define APPLICATIONS_M33_BT_SOURCE_TEMPLATE_H

#include <rtthread.h>

typedef struct
{
    const char *name;
    const char *template_path;
    const char *note;
} bt_source_template_entry_t;

const bt_source_template_entry_t *bt_source_template_get(rt_size_t *count);

#endif
