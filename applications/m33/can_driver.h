#ifndef CAN_DRIVER_H
#define CAN_DRIVER_H

#include <rtthread.h>
#include "control_manager.h"
#include "sensor_manager.h"

#define CAN_ID_MOTOR_SHOULDER 0x100
#define CAN_ID_MOTOR_ELBOW    0x101
#define CAN_ID_MOTOR_LATERAL  0x102
#define CAN_ID_SENSOR_EMG     0x200
#define CAN_ID_SENSOR_HEART   0x201
#define CAN_ID_SENSOR_IMU_ACC 0x202
#define CAN_ID_SENSOR_IMU_GYR 0x203

typedef struct
{
    rt_uint32_t id;
    rt_uint8_t dlc;
    rt_uint8_t data[8];
} rehab_can_frame_t;

rt_err_t can_driver_init(void);
rt_err_t can_send_joint_target(joint_id_t joint, float target);
rt_err_t can_process_frame(const rehab_can_frame_t *frame, sensor_data_t *snapshot);

#endif
