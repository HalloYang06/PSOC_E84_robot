#include "rehab_joint_map.h"

#include <stdlib.h>
#include <string.h>

#include "control_layer_cfg.h"

static const rehab_joint_map_entry_t s_rehab_joint_map[] =
{
    {REHAB_JOINT_ELBOW, 1U, CONTROL_REHAB_DEFAULT_M33_JOINT, "elbow"},
};

static rt_bool_t rehab_joint_map_parse_m33_id(const char *text, rt_uint8_t *out)
{
    char *endp;
    long value;

    if ((text == RT_NULL) || (out == RT_NULL) || (text[0] == '\0'))
    {
        return RT_FALSE;
    }

    value = strtol(text, &endp, 0);
    if ((endp == text) || (*endp != '\0') ||
        (value <= 0L) || (value > (long)CONTROL_MOTOR_JOINT_COUNT))
    {
        return RT_FALSE;
    }

    *out = (rt_uint8_t)value;
    return RT_TRUE;
}

rt_bool_t rehab_joint_map_get(rehab_joint_id_t joint, rehab_joint_map_entry_t *out)
{
    if ((out == RT_NULL) || (joint >= REHAB_JOINT_COUNT))
    {
        return RT_FALSE;
    }

    *out = s_rehab_joint_map[(rt_uint8_t)joint];
    return RT_TRUE;
}

rt_bool_t rehab_joint_map_parse(const char *name, rehab_joint_id_t *out)
{
    char *endp;
    long value;

    if (out == RT_NULL)
    {
        return RT_FALSE;
    }
    if ((name == RT_NULL) || (name[0] == '\0'))
    {
        *out = REHAB_JOINT_ELBOW;
        return RT_TRUE;
    }
    if ((strcmp(name, "elbow") == 0) || (strcmp(name, "elbow_lift_joint") == 0))
    {
        *out = REHAB_JOINT_ELBOW;
        return RT_TRUE;
    }

    value = strtol(name, &endp, 0);
    if ((endp != name) && (*endp == '\0') && (value == 0L))
    {
        *out = REHAB_JOINT_ELBOW;
        return RT_TRUE;
    }

    return RT_FALSE;
}

rt_bool_t rehab_joint_map_parse_entry(const char *name, rehab_joint_map_entry_t *out)
{
    rehab_joint_id_t joint;
    rt_uint8_t m33_joint;
    const char *value;

    if (out == RT_NULL)
    {
        return RT_FALSE;
    }

    if (rehab_joint_map_parse(name, &joint))
    {
        return rehab_joint_map_get(joint, out);
    }

    if (name == RT_NULL)
    {
        return RT_FALSE;
    }

    value = name;
    if (strncmp(name, "m33:", 4) == 0)
    {
        value = name + 4;
    }
    else if (strncmp(name, "m33_joint:", 10) == 0)
    {
        value = name + 10;
    }
    else if (strncmp(name, "motor:", 6) == 0)
    {
        value = name + 6;
    }
    else if (strncmp(name, "motor", 5) == 0)
    {
        value = name + 5;
    }
    else if (strncmp(name, "joint", 5) == 0)
    {
        value = name + 5;
    }

    if (!rehab_joint_map_parse_m33_id(value, &m33_joint))
    {
        return RT_FALSE;
    }

    out->rehab_joint = REHAB_JOINT_ELBOW;
    out->ros_joint_index = 0xFFU;
    out->m33_joint_id = m33_joint;
    out->name = "m33";
    return RT_TRUE;
}

const char *rehab_joint_map_name(rehab_joint_id_t joint)
{
    rehab_joint_map_entry_t entry;

    if (!rehab_joint_map_get(joint, &entry))
    {
        return "unknown";
    }
    return entry.name;
}
