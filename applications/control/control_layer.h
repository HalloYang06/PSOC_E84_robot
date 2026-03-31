#ifndef __CONTROL_LAYER_H__
#define __CONTROL_LAYER_H__

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
    rt_uint16_t ch1_raw;
    rt_uint16_t ch2_raw;
    rt_uint16_t rms_raw;
    rt_uint8_t seq;
    rt_uint8_t status;
    rt_tick_t timestamp;
} control_emg_report_t;

typedef struct
{
    rt_uint16_t bpm;
    rt_uint16_t hrv_ms;
    rt_uint8_t signal_quality;
    rt_uint8_t status;
    rt_tick_t timestamp;
} control_heart_report_t;

typedef enum
{
    CONTROL_MOTOR_RUN_MODE_MIT = 0,
    CONTROL_MOTOR_RUN_MODE_PP = 1,
    CONTROL_MOTOR_RUN_MODE_SPEED = 2,
    CONTROL_MOTOR_RUN_MODE_CURRENT = 3,
    CONTROL_MOTOR_RUN_MODE_CSP = 5,
} control_motor_run_mode_t;

typedef struct
{
    rt_uint8_t motor_id;
    rt_uint8_t mode_state;
    rt_uint8_t fault_summary;
    float pos_rad;
    float vel_rad_s;
    float torque_nm;
    float temp_c;
    rt_tick_t timestamp;
} control_motor_feedback_t;

typedef enum
{
    CONTROL_ROS_CMD_NONE = 0,
    CONTROL_ROS_CMD_ENABLE = 1,
    CONTROL_ROS_CMD_STOP = 2,
    CONTROL_ROS_CMD_SET_TARGET = 3,
    CONTROL_ROS_CMD_SET_MODE = 4,
    CONTROL_ROS_CMD_SET_ZERO = 5,
    CONTROL_ROS_CMD_SET_ACTIVE_REPORT = 6,
} control_ros_command_type_t;

typedef struct
{
    control_ros_command_type_t command;
    rt_uint8_t joint_id;
    rt_uint8_t clear_fault;
    rt_uint8_t mode;
    rt_uint8_t active_report_enable;
    rt_int16_t target_pos_01deg;
    rt_int16_t target_vel_rpm;
    rt_int16_t target_torque_ma;
    rt_tick_t timestamp;
} control_ros_command_t;

int control_layer_init(const char *can_name);

rt_err_t control_motor_enable(rt_uint8_t joint_id);
rt_err_t control_motor_stop(rt_uint8_t joint_id, rt_bool_t clear_fault);
rt_err_t control_motor_set_zero(rt_uint8_t joint_id);
rt_err_t control_motor_set_run_mode(rt_uint8_t joint_id, control_motor_run_mode_t mode);
rt_err_t control_motor_private_control(rt_uint8_t joint_id,
                                       float target_pos_rad,
                                       float target_vel_rad_s,
                                       float kp,
                                       float kd,
                                       float target_torque_nm);
rt_err_t control_motor_set_active_report(rt_uint8_t joint_id, rt_bool_t enable);
rt_err_t control_get_motor_feedback(rt_uint8_t joint_id, control_motor_feedback_t *out);
rt_err_t control_get_last_ros_command(control_ros_command_t *out);

/* Backward-compatible API */
rt_err_t control_joint_motor_set_target(rt_uint8_t joint_id,
                                        rt_int16_t target_pos_01deg,
                                        rt_int16_t target_vel_rpm,
                                        rt_int16_t target_torque_ma,
                                        rt_bool_t enable);
rt_err_t control_joint_motor_stop(rt_uint8_t joint_id);

rt_err_t control_sensor_report_enable(rt_bool_t enable, rt_uint16_t period_ms);
rt_err_t control_get_emg_report(control_emg_report_t *out);
rt_err_t control_get_heart_report(control_heart_report_t *out);

/* Deprecated RS00 naming compatibility aliases */
typedef control_motor_run_mode_t control_rs00_run_mode_t;
typedef control_motor_feedback_t control_rs00_feedback_t;

#define CONTROL_RS00_RUN_MODE_MIT        CONTROL_MOTOR_RUN_MODE_MIT
#define CONTROL_RS00_RUN_MODE_PP         CONTROL_MOTOR_RUN_MODE_PP
#define CONTROL_RS00_RUN_MODE_SPEED      CONTROL_MOTOR_RUN_MODE_SPEED
#define CONTROL_RS00_RUN_MODE_CURRENT    CONTROL_MOTOR_RUN_MODE_CURRENT
#define CONTROL_RS00_RUN_MODE_CSP        CONTROL_MOTOR_RUN_MODE_CSP

#define control_rs00_enable              control_motor_enable
#define control_rs00_stop                control_motor_stop
#define control_rs00_set_zero            control_motor_set_zero
#define control_rs00_set_run_mode        control_motor_set_run_mode
#define control_rs00_private_control     control_motor_private_control
#define control_rs00_set_active_report   control_motor_set_active_report
#define control_get_rs00_feedback        control_get_motor_feedback

#ifdef __cplusplus
}
#endif

#endif /* __CONTROL_LAYER_H__ */
