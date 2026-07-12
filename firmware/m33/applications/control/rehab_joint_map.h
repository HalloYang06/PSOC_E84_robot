#ifndef __REHAB_JOINT_MAP_H__
#define __REHAB_JOINT_MAP_H__

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    REHAB_JOINT_ELBOW = 0,
    REHAB_JOINT_COUNT
} rehab_joint_id_t;

typedef struct
{
    rehab_joint_id_t rehab_joint;
    rt_uint8_t ros_joint_index;
    rt_uint8_t m33_joint_id;
    const char *name;
} rehab_joint_map_entry_t;

rt_bool_t rehab_joint_map_get(rehab_joint_id_t joint, rehab_joint_map_entry_t *out);
rt_bool_t rehab_joint_map_parse(const char *name, rehab_joint_id_t *out);
rt_bool_t rehab_joint_map_parse_entry(const char *name, rehab_joint_map_entry_t *out);
const char *rehab_joint_map_name(rehab_joint_id_t joint);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_JOINT_MAP_H__ */
