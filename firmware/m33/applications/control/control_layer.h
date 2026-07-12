#ifndef __CONTROL_LAYER_H__
#define __CONTROL_LAYER_H__

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

/* EMG 肌电报告。
 * 来源：
 * - 旧版 EMG CAN 帧 CONTROL_CAN_ID_EMG_REPORT。
 * - 或 F103 传感节点 0x7C2 帧转换后的兼容缓存。
 * 用途：
 * - 给 App、平台、M55 小模型或调试命令读取最近一次肌电数据。
 */
typedef struct
{
    /* 通道 1 原始/毫伏缩放值。旧版帧中来自 float ch1_mv。 */
    rt_uint16_t ch1_raw;
    /* 通道 2 原始/毫伏缩放值。F103 路径中暂存滤波肌电绝对值。 */
    rt_uint16_t ch2_raw;
    /* RMS 或近似肌电强度。旧版帧取 ch1/ch2 平均，F103 路径取滤波值。 */
    rt_uint16_t rms_raw;
    /* 数据序号。当前旧版/F103 路径暂未提供真实递增序号，保持 0。 */
    rt_uint8_t seq;
    /* 状态/标志位。F103 路径复用 flags，旧版路径保持 0。 */
    rt_uint8_t status;
    /* M33 收到并写入缓存时的 RT-Thread tick。 */
    rt_tick_t timestamp;
} control_emg_report_t;

/* 心率报告。
 * 来源：
 * - 旧版心率 CAN 帧 CONTROL_CAN_ID_HEART_REPORT。
 * - 或 F103 传感节点 0x7C2 帧转换后的兼容缓存。
 */
typedef struct
{
    /* 心率 BPM。F103 路径中来自 hr_filt。 */
    rt_uint16_t bpm;
    /* HRV 或心率原始值。F103 路径中暂存 hr_raw。 */
    rt_uint16_t hrv_ms;
    /* 信号质量 0~100。F103 flags bit1 有效时置 100。 */
    rt_uint8_t signal_quality;
    /* 状态/标志位。F103 路径复用 flags。 */
    rt_uint8_t status;
    /* M33 收到并写入缓存时的 RT-Thread tick。 */
    rt_tick_t timestamp;
} control_heart_report_t;

/* F103/C8T6 传感节点综合样本。
 * 这个结构体把 0x7C2 传感数据、0x7C3 健康数据、0x7C1 ACK 数据合到一个缓存里，
 * 方便 App/平台一次读取“这个传感节点最近是什么状态”。
 */
typedef struct
{
    /* 0x7C2 raw view: four little-endian uint16 ADC samples in one classic CAN frame. */
    rt_uint16_t adc_raw[4];
    /* 0x7C2 emg3 view: CH0=biceps, CH1=triceps, CH2=anterior deltoid. */
    rt_uint16_t emg3_raw[3];
    /* 0x7C2 emg3 flags byte. */
    rt_uint8_t emg3_flags;
    /* 0x7C2 emg3 sequence byte. */
    rt_uint8_t emg3_seq;
    /* 0x7C2: EMG 原始 ADC/采样值。 */
    rt_uint16_t emg_raw;
    /* 0x7C2: EMG 滤波值，有符号。 */
    rt_int16_t emg_filt;
    /* 0x7C2: 心率原始采样值。 */
    rt_uint16_t hr_raw;
    /* 0x7C2: 心率滤波后 BPM。 */
    rt_uint8_t hr_filt;
    /* 0x7C2: 传感节点上报的状态标志。 */
    rt_uint8_t flags;
    /* 0x7C3: F103/C8T6 节点运行状态。 */
    rt_uint8_t node_state;
    /* 0x7C3: 节点错误计数。 */
    rt_uint16_t node_err_cnt;
    /* 0x7C3: 节点内部队列占用/填充情况。 */
    rt_uint8_t node_q_fill;
    /* 0x7C1: 最近一次 ACK 对应的命令号。 */
    rt_uint8_t last_ack_cmd;
    /* 0x7C1: 最近一次 ACK 对应的命令序号。 */
    rt_uint8_t last_ack_seq;
    /* 0x7C1: 最近一次 ACK 状态码。 */
    rt_uint8_t last_ack_status;
    /* 最近一次 0x7C2 传感数据到达 tick。 */
    rt_tick_t sensor_timestamp;
    /* 最近一次 0x7C3 健康数据到达 tick。 */
    rt_tick_t health_timestamp;
    /* 最近一次 0x7C1 ACK 到达 tick。 */
    rt_tick_t ack_timestamp;
} control_sensor_node_sample_t;

/* 电机运行模式。值要和 RobStride/灵足私有协议 run_mode 参数保持一致。 */
typedef enum
{
    /* MIT 控制帧模式：位置/速度/kp/kd/力矩前馈打包在控制帧中。 */
    CONTROL_MOTOR_RUN_MODE_MIT = 0,
    /* PP 点位模式。 */
    CONTROL_MOTOR_RUN_MODE_PP = 1,
    /* 速度模式。 */
    CONTROL_MOTOR_RUN_MODE_SPEED = 2,
    /* 电流模式。 */
    CONTROL_MOTOR_RUN_MODE_CURRENT = 3,
    /* CSP 周期同步位置模式，当前正式灵足位置目标优先使用这个模式。 */
    CONTROL_MOTOR_RUN_MODE_CSP = 5,
} control_motor_run_mode_t;

/* 当前关节对应的底层电机协议类型。 */
typedef enum
{
    /* RobStride/灵足私有 29 位扩展帧协议。 */
    CONTROL_MOTOR_PROTOCOL_TYPE_PRIVATE = 0,
    /* CANSimple/ODrive-like 11 位标准帧协议，当前用于 3 号伺泰威路径。 */
    CONTROL_MOTOR_PROTOCOL_TYPE_CANSIMPLE = 1,
} control_motor_protocol_type_t;

/* 电机反馈缓存。
 * 注意 pos/vel 已尽量转换成关节侧单位，具体映射由 control_layer_cfg.h 的方向、减速比、零偏决定。
 */
typedef struct
{
    /* 底层电机 ID 或 CANSimple node id。 */
    rt_uint8_t motor_id;
    /* 反馈来源协议。 */
    control_motor_protocol_type_t protocol;
    /* 电机模式/状态字段，协议不同含义略有差异。 */
    rt_uint8_t mode_state;
    /* 故障摘要，协议不同含义略有差异。 */
    rt_uint8_t fault_summary;
    /* 关节位置，rad。 */
    float pos_rad;
    /* 关节速度，rad/s。 */
    float vel_rad_s;
    /* 力矩估计/反馈，Nm。 */
    float torque_nm;
    /* 温度，摄氏度。 */
    float temp_c;
    /* 最近一次更新 tick。 */
    rt_tick_t timestamp;
} control_motor_feedback_t;

/* 电机参数读写回复缓存。用于调试 run_mode、limit_cur、limit_spd 等参数。 */
typedef struct
{
    /* 回复来自哪个电机。 */
    rt_uint8_t motor_id;
    /* 参数索引，例如 0x7005 run_mode。 */
    rt_uint16_t index;
    /* 当参数是 u8 模式值时保存原始值。 */
    rt_uint8_t raw_u8;
    /* 当参数是 float 时保存解析值。 */
    float value_f32;
    /* 是否已经收到过有效回复。 */
    rt_bool_t valid;
    /* 最近一次更新 tick。 */
    rt_tick_t timestamp;
} control_motor_param_report_t;

/* 私有协议 Get_ID 探测结果。 */
typedef struct
{
    /* 被探测的电机 ID。 */
    rt_uint8_t motor_id;
    /* 电机返回的唯一 ID/序列号。 */
    rt_uint64_t unique_id;
    /* 是否已经收到有效探测回复。 */
    rt_bool_t valid;
    /* 最近一次更新 tick。 */
    rt_tick_t timestamp;
} control_motor_probe_report_t;

/* NanoPi -> M33 ROS 桥控制命令类型，对应 0x320 第 0 字节。 */
typedef enum
{
    /* 空命令/未识别。 */
    CONTROL_ROS_CMD_NONE = 0,
    /* 使能关节电机。 */
    CONTROL_ROS_CMD_ENABLE = 1,
    /* 停止关节电机。 */
    CONTROL_ROS_CMD_STOP = 2,
    /* 设置关节目标位置/速度/力矩限制。 */
    CONTROL_ROS_CMD_SET_TARGET = 3,
    /* 设置电机运行模式。 */
    CONTROL_ROS_CMD_SET_MODE = 4,
    /* 设置零点，正式装机后慎用。 */
    CONTROL_ROS_CMD_SET_ZERO = 5,
    /* 打开/关闭电机主动上报。 */
    CONTROL_ROS_CMD_SET_ACTIVE_REPORT = 6,
} control_ros_command_type_t;

/* 解析后的 ROS 桥命令缓存。 */
typedef struct
{
    /* 命令类型。 */
    control_ros_command_type_t command;
    /* ROS/机械臂关节 ID。 */
    rt_uint8_t joint_id;
    /* stop 时是否顺带清故障。 */
    rt_uint8_t clear_fault;
    /* set_mode 使用的运行模式。 */
    rt_uint8_t mode;
    /* active_report 命令的开关值。 */
    rt_uint8_t active_report_enable;
    /* 目标位置，单位 0.1 deg。 */
    rt_int16_t target_pos_01deg;
    /* 目标速度/限速，单位 rpm。 */
    rt_int16_t target_vel_rpm;
    /* 目标力矩/电流限制，沿用旧协议字段名 ma。 */
    rt_int16_t target_torque_ma;
    /* M33 解析到该命令时的 tick。 */
    rt_tick_t timestamp;
} control_ros_command_t;

/* 初始化控制层：打开/初始化 CAN，创建后台线程，初始化传感器子模块。 */
int control_layer_init(const char *can_name);

/* 使能指定关节电机。joint_id 为机械臂关节编号，不是底层 motor_id。 */
rt_err_t control_motor_enable(rt_uint8_t joint_id);
/* 停止指定关节电机；clear_fault 为真时尝试清除故障。 */
rt_err_t control_motor_stop(rt_uint8_t joint_id, rt_bool_t clear_fault);
/* 设置指定关节电机当前位置为零点；正式装机后需谨慎使用。 */
rt_err_t control_motor_set_zero(rt_uint8_t joint_id);
/* 设置指定关节电机运行模式，例如 MIT/SPEED/CURRENT/CSP。 */
rt_err_t control_motor_set_run_mode(rt_uint8_t joint_id, control_motor_run_mode_t mode);
/* 发送私有协议 MIT 控制帧：目标位置、速度、kp、kd、力矩前馈。 */
rt_err_t control_motor_private_control(rt_uint8_t joint_id,
                                       float target_pos_rad,
                                       float target_vel_rad_s,
                                       float kp,
                                       float kd,
                                       float target_torque_nm);
/* 打开/关闭指定关节电机主动上报。 */
rt_err_t control_motor_set_active_report(rt_uint8_t joint_id, rt_bool_t enable);
/* 读取指定关节最近一次电机反馈缓存。 */
rt_err_t control_get_motor_feedback(rt_uint8_t joint_id, control_motor_feedback_t *out);
/* Read the static joint calibration gate used by absolute position commands. */
rt_bool_t control_motor_is_joint_calibrated(rt_uint8_t joint_id);
/* 直接按底层 motor_id 发送私有协议 Get_ID 探测。 */
rt_err_t control_motor_probe_id(rt_uint8_t motor_id);
/* 读取最近一次私有协议 Get_ID 探测结果。 */
rt_err_t control_get_last_motor_probe(control_motor_probe_report_t *out);
/* 读取指定关节电机参数，例如 run_mode/limit_cur/limit_spd。 */
rt_err_t control_motor_read_parameter(rt_uint8_t joint_id, rt_uint16_t index);
/* 写指定关节电机参数；mode_value_is_u8 用于 run_mode 这类 u8 参数。 */
rt_err_t control_motor_write_parameter(rt_uint8_t joint_id, rt_uint16_t index, float value, rt_bool_t mode_value_is_u8);
/* 读取最近一次电机参数回复缓存。 */
rt_err_t control_get_last_motor_param(control_motor_param_report_t *out);
/* 私有协议速度模式控制：设置速度和电流限制。 */
/* Private protocol current-mode command, writes iq_ref after enabling the joint. */
rt_err_t control_motor_current_control(rt_uint8_t joint_id, float current_a);
rt_err_t control_motor_speed_control(rt_uint8_t joint_id, float speed_rad_s, float limit_cur);
/* 私有协议位置控制：csp_mode 为真时使用 CSP 参数流，否则走普通位置参数流。 */
rt_err_t control_motor_position_control(rt_uint8_t joint_id, float pos_rad, float limit_spd, rt_bool_t csp_mode);
/* CANSimple 位置控制：用于 CANSimple/ODrive-like 电机。 */
rt_err_t control_motor_cansimple_set_input_pos(rt_uint8_t joint_id, float pos_rad, float vel_ff_rad_s, float torque_ff_nm);
/* CANSimple 速度控制：用于 CANSimple/ODrive-like 电机。 */
rt_err_t control_motor_cansimple_set_input_vel(rt_uint8_t joint_id, float vel_rad_s, float torque_ff_nm);
/* CANSimple 力矩控制：用于 CANSimple/ODrive-like 电机。 */
rt_err_t control_motor_cansimple_set_input_torque(rt_uint8_t joint_id, float torque_nm);
/* 读取最近一次 NanoPi/ROS 0x320 命令缓存。 */
rt_err_t control_get_last_ros_command(control_ros_command_t *out);

/* 兼容旧接口：按 0.1deg/rpm/ma 字段设置关节目标。 */
rt_err_t control_joint_motor_set_target(rt_uint8_t joint_id,
                                        rt_int16_t target_pos_01deg,
                                        rt_int16_t target_vel_rpm,
                                        rt_int16_t target_torque_ma,
                                        rt_bool_t enable);
/* 兼容旧接口：停止关节电机。 */
rt_err_t control_joint_motor_stop(rt_uint8_t joint_id);

/* 配置传感器上报：设置周期并启动/停止 F103 与旧传感控制帧。 */
rt_err_t control_sensor_report_enable(rt_bool_t enable, rt_uint16_t period_ms);
/* 读取最近一次肌电报告。 */
rt_err_t control_get_emg_report(control_emg_report_t *out);
/* 读取最近一次心率报告。 */
rt_err_t control_get_heart_report(control_heart_report_t *out);
/* 读取最近一次 F103/C8T6 综合节点样本。 */
rt_err_t control_get_sensor_node_sample(control_sensor_node_sample_t *out);

/* 发布 M55/M33 小模型结果摘要给 NanoPi。该帧只表达模型建议，不授予运动许可。 */
rt_err_t control_publish_m55_model_result(rt_uint8_t model_code,
                                          rt_uint8_t result_code,
                                          rt_uint16_t confidence_permille,
                                          rt_uint8_t flags,
                                          rt_uint16_t window_ms);

/* 废弃的 RS00 命名兼容别名：保留给旧代码，不建议新代码继续使用。 */
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
