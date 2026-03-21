#ifndef APPLICATIONS_M33_BT_VENDOR_PACKAGE_H
#define APPLICATIONS_M33_BT_VENDOR_PACKAGE_H

#include <rtthread.h>

typedef struct
{
    const char *name;
    const char *local_path;
    rt_bool_t imported;
} bt_vendor_package_item_t;

const bt_vendor_package_item_t *bt_vendor_package_get(rt_size_t *count);
rt_bool_t bt_vendor_package_is_imported(void);
rt_bool_t bt_vendor_package_is_build_wiring_ready(void);

#endif
