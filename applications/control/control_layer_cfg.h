#ifndef __CONTROL_LAYER_CFG_H__
#define __CONTROL_LAYER_CFG_H__

/* Default CAN device name */
#ifndef CONTROL_CAN_DEV_DEFAULT
#define CONTROL_CAN_DEV_DEFAULT            "can0"
#endif

/* Control thread config */
#ifndef CONTROL_CAN_THREAD_STACK_SIZE
#define CONTROL_CAN_THREAD_STACK_SIZE      2048
#endif

#ifndef CONTROL_CAN_THREAD_PRIORITY
#define CONTROL_CAN_THREAD_PRIORITY        18
#endif

#ifndef CONTROL_CAN_THREAD_TICK
#define CONTROL_CAN_THREAD_TICK            10
#endif

/* ROS command task config */
#ifndef CONTROL_ROS_THREAD_STACK_SIZE
#define CONTROL_ROS_THREAD_STACK_SIZE      2048
#endif

#ifndef CONTROL_ROS_THREAD_PRIORITY
#define CONTROL_ROS_THREAD_PRIORITY        19
#endif

#ifndef CONTROL_ROS_THREAD_TICK
#define CONTROL_ROS_THREAD_TICK            10
#endif

#ifndef CONTROL_ROS_CMD_QUEUE_DEPTH
#define CONTROL_ROS_CMD_QUEUE_DEPTH        16
#endif

/* Motor private protocol defaults */
#ifndef CONTROL_MOTOR_MASTER_ID
#define CONTROL_MOTOR_MASTER_ID            0xFDU
#endif

#ifndef CONTROL_MOTOR_JOINT_COUNT
#define CONTROL_MOTOR_JOINT_COUNT          5U
#endif

#ifndef CONTROL_MOTOR_JOINT1_ID
#define CONTROL_MOTOR_JOINT1_ID            0x01U
#endif

#ifndef CONTROL_MOTOR_JOINT2_ID
#define CONTROL_MOTOR_JOINT2_ID            0x02U
#endif

#ifndef CONTROL_MOTOR_JOINT3_ID
#define CONTROL_MOTOR_JOINT3_ID            0x03U
#endif

#ifndef CONTROL_MOTOR_JOINT4_ID
#define CONTROL_MOTOR_JOINT4_ID            0x04U
#endif

#ifndef CONTROL_MOTOR_JOINT5_ID
#define CONTROL_MOTOR_JOINT5_ID            0x05U
#endif

#ifndef CONTROL_MOTOR_P_MIN_RAD
#define CONTROL_MOTOR_P_MIN_RAD            (-12.57f)
#endif

#ifndef CONTROL_MOTOR_P_MAX_RAD
#define CONTROL_MOTOR_P_MAX_RAD            (12.57f)
#endif

#ifndef CONTROL_MOTOR_V_MIN_RAD_S
#define CONTROL_MOTOR_V_MIN_RAD_S          (-33.0f)
#endif

#ifndef CONTROL_MOTOR_V_MAX_RAD_S
#define CONTROL_MOTOR_V_MAX_RAD_S          (33.0f)
#endif

#ifndef CONTROL_MOTOR_KP_MIN
#define CONTROL_MOTOR_KP_MIN               (0.0f)
#endif

#ifndef CONTROL_MOTOR_KP_MAX
#define CONTROL_MOTOR_KP_MAX               (500.0f)
#endif

#ifndef CONTROL_MOTOR_KD_MIN
#define CONTROL_MOTOR_KD_MIN               (0.0f)
#endif

#ifndef CONTROL_MOTOR_KD_MAX
#define CONTROL_MOTOR_KD_MAX               (5.0f)
#endif

#ifndef CONTROL_MOTOR_T_MIN_NM
#define CONTROL_MOTOR_T_MIN_NM             (-14.0f)
#endif

#ifndef CONTROL_MOTOR_T_MAX_NM
#define CONTROL_MOTOR_T_MAX_NM             (14.0f)
#endif

#ifndef CONTROL_MOTOR_DEFAULT_KP
#define CONTROL_MOTOR_DEFAULT_KP           (30.0f)
#endif

#ifndef CONTROL_MOTOR_DEFAULT_KD
#define CONTROL_MOTOR_DEFAULT_KD           (1.0f)
#endif

/* ROS command CAN protocol:
 * Byte0: cmd(1-enable 2-stop 3-set_target 4-set_mode 5-set_zero 6-active_report)
 * Byte1: joint_id
 * Byte2~7: payload by command
 */
#ifndef CONTROL_CAN_ID_ROS_COMMAND
#define CONTROL_CAN_ID_ROS_COMMAND         0x320U
#endif

#ifndef CONTROL_ROS_CMD_OP_ENABLE
#define CONTROL_ROS_CMD_OP_ENABLE          0x01U
#endif

#ifndef CONTROL_ROS_CMD_OP_STOP
#define CONTROL_ROS_CMD_OP_STOP            0x02U
#endif

#ifndef CONTROL_ROS_CMD_OP_SET_TARGET
#define CONTROL_ROS_CMD_OP_SET_TARGET      0x03U
#endif

#ifndef CONTROL_ROS_CMD_OP_SET_MODE
#define CONTROL_ROS_CMD_OP_SET_MODE        0x04U
#endif

#ifndef CONTROL_ROS_CMD_OP_SET_ZERO
#define CONTROL_ROS_CMD_OP_SET_ZERO        0x05U
#endif

#ifndef CONTROL_ROS_CMD_OP_ACTIVE_REPORT
#define CONTROL_ROS_CMD_OP_ACTIVE_REPORT   0x06U
#endif

#ifndef CONTROL_CAN_CLASSIC_ONLY
#define CONTROL_CAN_CLASSIC_ONLY           1
#endif

/* STM32C8T6 sensor report IDs (project custom) */
#ifndef CONTROL_CAN_ID_EMG_REPORT
#define CONTROL_CAN_ID_EMG_REPORT          0x301U
#endif

#ifndef CONTROL_CAN_ID_HEART_REPORT
#define CONTROL_CAN_ID_HEART_REPORT        0x302U
#endif

#ifndef CONTROL_CAN_ID_SENSOR_CTRL
#define CONTROL_CAN_ID_SENSOR_CTRL         0x310U
#endif

#ifndef CONTROL_SENSOR_CMD_ENABLE_REPORT
#define CONTROL_SENSOR_CMD_ENABLE_REPORT   0x01U
#endif

#ifndef CONTROL_SENSOR_DEFAULT_PERIOD_MS
#define CONTROL_SENSOR_DEFAULT_PERIOD_MS   20U
#endif

/* Deprecated RS00 naming compatibility aliases */
#ifndef CONTROL_RS00_MASTER_ID
#define CONTROL_RS00_MASTER_ID             CONTROL_MOTOR_MASTER_ID
#endif

#ifndef CONTROL_RS00_JOINT1_ID
#define CONTROL_RS00_JOINT1_ID             CONTROL_MOTOR_JOINT1_ID
#endif

#ifndef CONTROL_RS00_JOINT2_ID
#define CONTROL_RS00_JOINT2_ID             CONTROL_MOTOR_JOINT2_ID
#endif

#ifndef CONTROL_RS00_P_MIN_RAD
#define CONTROL_RS00_P_MIN_RAD             CONTROL_MOTOR_P_MIN_RAD
#endif

#ifndef CONTROL_RS00_P_MAX_RAD
#define CONTROL_RS00_P_MAX_RAD             CONTROL_MOTOR_P_MAX_RAD
#endif

#ifndef CONTROL_RS00_V_MIN_RAD_S
#define CONTROL_RS00_V_MIN_RAD_S           CONTROL_MOTOR_V_MIN_RAD_S
#endif

#ifndef CONTROL_RS00_V_MAX_RAD_S
#define CONTROL_RS00_V_MAX_RAD_S           CONTROL_MOTOR_V_MAX_RAD_S
#endif

#ifndef CONTROL_RS00_KP_MIN
#define CONTROL_RS00_KP_MIN                CONTROL_MOTOR_KP_MIN
#endif

#ifndef CONTROL_RS00_KP_MAX
#define CONTROL_RS00_KP_MAX                CONTROL_MOTOR_KP_MAX
#endif

#ifndef CONTROL_RS00_KD_MIN
#define CONTROL_RS00_KD_MIN                CONTROL_MOTOR_KD_MIN
#endif

#ifndef CONTROL_RS00_KD_MAX
#define CONTROL_RS00_KD_MAX                CONTROL_MOTOR_KD_MAX
#endif

#ifndef CONTROL_RS00_T_MIN_NM
#define CONTROL_RS00_T_MIN_NM              CONTROL_MOTOR_T_MIN_NM
#endif

#ifndef CONTROL_RS00_T_MAX_NM
#define CONTROL_RS00_T_MAX_NM              CONTROL_MOTOR_T_MAX_NM
#endif

#ifndef CONTROL_RS00_DEFAULT_KP
#define CONTROL_RS00_DEFAULT_KP            CONTROL_MOTOR_DEFAULT_KP
#endif

#ifndef CONTROL_RS00_DEFAULT_KD
#define CONTROL_RS00_DEFAULT_KD            CONTROL_MOTOR_DEFAULT_KD
#endif

#endif /* __CONTROL_LAYER_CFG_H__ */
