#ifndef __REHAB_FIXED_ACTION_H__
#define __REHAB_FIXED_ACTION_H__

#include <rtthread.h>

#include "rehab_scurve.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifndef RT_ERROR
#define RT_ERROR 1
#endif

#ifndef RT_EINVAL
#define RT_EINVAL 22
#endif

#define REHAB_FIXED_ACTION_JOINT_SLOTS 7U
#define REHAB_FIXED_ACTION_JOINT5_MASK 0x10U
#define REHAB_FIXED_ACTION_JOINT6_MASK 0x20U
#define REHAB_FIXED_ACTION_JOINT56_MASK 0x30U

typedef enum
{
    REHAB_FIXED_ACTION_NONE = 0,
    REHAB_FIXED_ACTION_ELBOW_FLEX_EXTEND,
    REHAB_FIXED_ACTION_SHOULDER_PLANAR,
    REHAB_FIXED_ACTION_COORDINATED,
    REHAB_FIXED_ACTION_SHOULDER_FORE_AFT,
} rehab_fixed_action_id_t;

typedef enum
{
    REHAB_FIXED_ACTION_STATE_IDLE = 0,
    REHAB_FIXED_ACTION_STATE_CSP_PREPARE,
    REHAB_FIXED_ACTION_STATE_MOVE_A,
    REHAB_FIXED_ACTION_STATE_DWELL_A,
    REHAB_FIXED_ACTION_STATE_MOVE_B,
    REHAB_FIXED_ACTION_STATE_DWELL_B,
    REHAB_FIXED_ACTION_STATE_DECEL_STOP,
    REHAB_FIXED_ACTION_STATE_COMPLETE,
    REHAB_FIXED_ACTION_STATE_PAUSED,
    REHAB_FIXED_ACTION_STATE_FAULT,
} rehab_fixed_action_state_t;

typedef enum
{
    REHAB_FIXED_ACTION_OUTPUT_NONE = 0,
    REHAB_FIXED_ACTION_OUTPUT_PREPARE,
    REHAB_FIXED_ACTION_OUTPUT_SETPOINT,
    REHAB_FIXED_ACTION_OUTPUT_STOP,
} rehab_fixed_action_output_action_t;

typedef struct
{
    rt_bool_t active;
    float hard_min_rad;
    float hard_max_rad;
    float safe_min_rad;
    float safe_max_rad;
} rehab_fixed_action_joint_profile_t;

typedef struct
{
    rehab_fixed_action_id_t id;
    rt_bool_t enabled;
    rt_uint8_t joint_mask;
    rehab_fixed_action_joint_profile_t joint[REHAB_FIXED_ACTION_JOINT_SLOTS];
    float max_velocity_rad_s;
    float max_accel_rad_s2;
    float max_jerk_rad_s3;
    float max_feedback_velocity_rad_s;
    rt_uint32_t dwell_ms;
    rt_uint32_t repetitions;
} rehab_fixed_action_profile_t;

typedef struct
{
    rt_uint8_t fresh_mask;
    rt_uint8_t fault_mask;
    float position_rad[REHAB_FIXED_ACTION_JOINT_SLOTS];
    float velocity_rad_s[REHAB_FIXED_ACTION_JOINT_SLOTS];
} rehab_fixed_action_feedback_t;

typedef struct
{
    rehab_fixed_action_output_action_t action;
    rehab_fixed_action_state_t state;
    rt_err_t result;
    rt_uint8_t joint_mask;
    float target_rad[REHAB_FIXED_ACTION_JOINT_SLOTS];
    rt_uint32_t completed_repetitions;
} rehab_fixed_action_output_t;

typedef struct
{
    const rehab_fixed_action_profile_t *profile;
    rehab_fixed_action_state_t state;
    rehab_scurve_profile_t segment[REHAB_FIXED_ACTION_JOINT_SLOTS];
    rt_uint32_t segment_started_ms;
    rt_uint32_t dwell_started_ms;
    rt_uint32_t segment_duration_ms;
    rt_uint32_t completed_repetitions;
    rt_err_t fault;
} rehab_fixed_action_runner_t;

const rehab_fixed_action_profile_t *rehab_fixed_action_profile(rehab_fixed_action_id_t id);
rt_err_t rehab_fixed_action_start(rehab_fixed_action_runner_t *runner,
                                  rehab_fixed_action_id_t id,
                                  const rehab_fixed_action_feedback_t *feedback,
                                  rt_uint32_t now_ms);
void rehab_fixed_action_step(rehab_fixed_action_runner_t *runner,
                             const rehab_fixed_action_feedback_t *feedback,
                             rt_uint32_t now_ms,
                             rehab_fixed_action_output_t *out);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_FIXED_ACTION_H__ */
