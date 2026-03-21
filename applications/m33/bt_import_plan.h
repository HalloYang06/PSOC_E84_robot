#ifndef APPLICATIONS_M33_BT_IMPORT_PLAN_H
#define APPLICATIONS_M33_BT_IMPORT_PLAN_H

#include <rtthread.h>

typedef struct
{
    const char *step_name;
    const char *goal;
    const char *import_scope;
    const char *success_state;
    rt_bool_t blocking;
} bt_import_plan_step_t;

const bt_import_plan_step_t *bt_import_plan_get(rt_size_t *count);

#endif
