#ifndef __REHAB_MODE_MANAGER_H__
#define __REHAB_MODE_MANAGER_H__

#include <rtthread.h>

#include "rehab_service.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    REHAB_MODE_PASSIVE = 0,
    REHAB_MODE_ACTIVE = 1,
    REHAB_MODE_MEMORY = 2,
    REHAB_MODE_ASSIST = 3,
    REHAB_MODE_RESIST = 4,
} rehab_mode_t;

typedef enum
{
    REHAB_MODE_SUBMODE_IDLE = 0,
    REHAB_MODE_SUBMODE_RECORD = 1,
    REHAB_MODE_SUBMODE_PLAYBACK = 2,
} rehab_mode_submode_t;

typedef enum
{
    REHAB_MODE_STATUS_FLAG_HEARTBEAT_OK = 0x01U,
    REHAB_MODE_STATUS_FLAG_ASSIST_ENGAGED = 0x02U,
    REHAB_MODE_STATUS_FLAG_STALE_FEEDBACK = 0x04U,
    REHAB_MODE_STATUS_FLAG_REJECTED = 0x08U,
    REHAB_MODE_STATUS_FLAG_RECORD = 0x10U,
    REHAB_MODE_STATUS_FLAG_PLAYBACK = 0x20U,
} rehab_mode_status_flag_t;

typedef struct
{
    rehab_mode_t mode;
    rehab_mode_submode_t submode;
    rt_uint8_t joint_mask;
    rt_uint8_t assist_direction_mask;
    float max_velocity_rad_s;
    float assist_torque_enter_nm;
    rt_uint8_t sequence;
    rt_tick_t timestamp;
} rehab_mode_command_t;

typedef struct
{
    rehab_mode_t mode;
    rehab_mode_submode_t submode;
    rt_uint8_t active_joint_mask;
    rt_uint8_t flags;
    rt_uint8_t detail;
    rt_uint8_t assist_engaged_mask;
    rt_uint8_t sequence;
    rt_tick_t timestamp;
} rehab_mode_status_t;

rt_err_t rehab_mode_manager_init(void);
rt_err_t rehab_mode_manager_apply_command(const rehab_mode_command_t *cmd);
void rehab_mode_manager_record_reject(rt_uint8_t sequence, rt_uint8_t detail);
void rehab_mode_manager_note_heartbeat(void);
void rehab_mode_manager_tick(void);
rt_bool_t rehab_mode_manager_accepts_ros_target(void);
rt_bool_t rehab_mode_manager_accepts_ros_stop(void);
void rehab_mode_manager_get_status(rehab_mode_status_t *out);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_MODE_MANAGER_H__ */
