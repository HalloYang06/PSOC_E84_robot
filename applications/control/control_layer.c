#include <rtthread.h>
#include <rtdevice.h>
#include <drivers/can.h>
#include <stdlib.h>
#include <string.h>

#include "drv_can.h"
#include "control_layer.h"
#include "control_layer_cfg.h"

#ifndef RT_PI
#define RT_PI 3.14159265358979323846f
#endif

#ifndef CONTROL_CAN_USE_DIRECT_PDL
#define CONTROL_CAN_USE_DIRECT_PDL 1
#endif

#if (CONTROL_MOTOR_JOINT_COUNT < 1U) || (CONTROL_MOTOR_JOINT_COUNT > 7U)
#error "CONTROL_MOTOR_JOINT_COUNT must be within [1, 7]."
#endif

#define MOTOR_PRIVATE_TYPE_CTRL            0x01U
#define MOTOR_PRIVATE_TYPE_FEEDBACK        0x02U
#define MOTOR_PRIVATE_TYPE_ENABLE          0x03U
#define MOTOR_PRIVATE_TYPE_STOP            0x04U
#define MOTOR_PRIVATE_TYPE_SET_ZERO        0x06U
#define MOTOR_PRIVATE_TYPE_GET_ID          0x00U
#define MOTOR_PRIVATE_TYPE_PARAM_READ      0x11U
#define MOTOR_PRIVATE_TYPE_PARAM_WRITE     0x12U
#define MOTOR_PRIVATE_TYPE_ACTIVE_REPORT   0x18U
#define MOTOR_PRIVATE_GET_ID_REPLY         0xFEU
#define MOTOR_PRIVATE_BROADCAST_ID         0x7FU
#define CONTROL_CAN_RX_DRAIN_LIMIT         16U

#define MOTOR_PARAM_INDEX_RUN_MODE         0x7005U
#define MOTOR_PARAM_INDEX_SPD_REF          0x700AU
#define MOTOR_PARAM_INDEX_LOC_REF          0x7016U
#define MOTOR_PARAM_INDEX_LIMIT_SPD        0x7017U
#define MOTOR_PARAM_INDEX_LIMIT_CUR        0x7018U
#define MOTOR_PARAM_INDEX_MECH_POS         0x7019U
#define MOTOR_PARAM_INDEX_MECH_VEL         0x701BU
#define MOTOR_PARAM_INDEX_SPEED_ACC        0x7022U
#define MOTOR_PARAM_INDEX_PP_VEL_MAX       0x7024U
#define MOTOR_PARAM_INDEX_PP_ACC_SET       0x7025U

#define CANSIMPLE_CMD_HEARTBEAT            0x01U
#define CANSIMPLE_CMD_GET_ERROR            0x03U
#define CANSIMPLE_CMD_RX_SDO               0x04U
#define CANSIMPLE_CMD_TX_SDO               0x05U
#define CANSIMPLE_CMD_ADDRESS              0x06U
#define CANSIMPLE_CMD_SET_AXIS_STATE       0x07U
#define CANSIMPLE_CMD_MIT_CONTROL          0x08U
#define CANSIMPLE_CMD_GET_ENCODER_EST      0x09U
#define CANSIMPLE_CMD_SET_CONTROLLER_MODE  0x0BU
#define CANSIMPLE_CMD_SET_INPUT_POS        0x0CU
#define CANSIMPLE_CMD_SET_INPUT_VEL        0x0DU
#define CANSIMPLE_CMD_SET_INPUT_TORQUE     0x0EU
#define CANSIMPLE_CMD_SET_LIMITS           0x0FU
#define CANSIMPLE_CMD_GET_IQ               0x14U
#define CANSIMPLE_CMD_GET_SENSORLESS_EST   0x15U
#define CANSIMPLE_CMD_CLEAR_ERRORS         0x18U
#define CANSIMPLE_CMD_SET_ABSOLUTE_POS     0x19U
#define CANSIMPLE_CMD_GET_TORQUES          0x1CU

#define CANSIMPLE_AXIS_STATE_IDLE          1U
#define CANSIMPLE_AXIS_STATE_CLOSED_LOOP   8U
#define CANSIMPLE_CONTROL_MODE_TORQUE      1U
#define CANSIMPLE_CONTROL_MODE_VELOCITY    2U
#define CANSIMPLE_CONTROL_MODE_POSITION    3U
#define CANSIMPLE_INPUT_MODE_PASSTHROUGH   1U
#define CANSIMPLE_INPUT_MODE_VEL_RAMP      2U
#define CANSIMPLE_NODE_ID_BROADCAST        0x3FU
#define CONTROL_MOTOR_ID_INVALID           0xFFU

static rt_device_t s_can_dev = RT_NULL;
static rt_thread_t s_can_rx_thread = RT_NULL;
static rt_thread_t s_ros_cmd_thread = RT_NULL;
static rt_thread_t s_motor_status_thread = RT_NULL;
static struct rt_semaphore s_can_rx_sem;
static struct rt_mutex s_data_lock;
static struct rt_messagequeue s_ros_cmd_mq;
static rt_uint8_t s_ros_cmd_pool[CONTROL_ROS_CMD_QUEUE_DEPTH * sizeof(control_ros_command_t)];

static rt_bool_t s_is_inited = RT_FALSE;
static rt_uint8_t s_tx_seq = 0U;
static rt_uint8_t s_motor_status_seq = 0U;

static control_emg_report_t s_emg_report;
static control_heart_report_t s_heart_report;
static control_sensor_node_sample_t s_sensor_node_sample;
static control_ros_command_t s_last_ros_cmd;
static control_motor_probe_report_t s_last_motor_probe;
static control_motor_param_report_t s_last_motor_param;
static control_motor_feedback_t s_motor_feedback[CONTROL_MOTOR_JOINT_COUNT];
static rt_bool_t s_motor_probe_pending = RT_FALSE;
static rt_uint8_t s_motor_probe_expected_id = 0U;
static rt_uint32_t s_dbg_rx_total = 0U;
static rt_uint32_t s_dbg_rx_heartbeat = 0U;
static rt_tick_t s_last_nanopi_heartbeat_tick = 0U;
static rt_bool_t s_has_nanopi_heartbeat = RT_FALSE;
static rt_uint8_t s_last_ros_status_detail_code =
#if CONTROL_ROS_COMMAND_LOGGING_ONLY
    CONTROL_STATUS_DETAIL_LOGGING_ONLY;
#else
    CONTROL_STATUS_DETAIL_NONE;
#endif
static rt_uint32_t s_dbg_rx_f103_ack = 0U;
static rt_uint32_t s_dbg_rx_f103_sensor = 0U;
static rt_uint32_t s_dbg_rx_f103_health = 0U;
static rt_uint32_t s_dbg_rx_ros_id = 0U;
static rt_uint32_t s_dbg_ros_parsed = 0U;
static rt_uint32_t s_dbg_ros_enqueued = 0U;
static rt_uint32_t s_dbg_ros_applied = 0U;
static rt_uint32_t s_dbg_ros_queue_fail = 0U;
static rt_uint32_t s_dbg_last_rx_id = 0U;
static rt_uint8_t s_dbg_last_rx_ide = 0U;
static rt_uint8_t s_dbg_last_rx_len = 0U;
static rt_uint8_t s_dbg_last_rx_data[8];
static rt_bool_t s_cansimple_seen[64];
static rt_uint8_t s_cansimple_axis_state[64];
static rt_uint8_t s_cansimple_flags[64];
static rt_int8_t s_cansimple_temp_c[64];
static rt_uint8_t s_cansimple_life[64];
static rt_uint32_t s_cansimple_axis_error[64];
static rt_tick_t s_cansimple_heartbeat_tick[64];
static rt_bool_t s_cansimple_error_seen[64];
static rt_uint8_t s_cansimple_error_type[64];
static rt_uint8_t s_cansimple_error_len[64];
static rt_uint64_t s_cansimple_error_value[64];
static rt_tick_t s_cansimple_error_tick[64];

typedef struct
{
    rt_uint8_t joint_id;
    float speed_rad_s;
    float limit_cur;
    rt_uint32_t duration_ms;
    rt_uint32_t period_ms;
    volatile rt_bool_t stop_requested;
} control_speed_hold_ctx_t;

static rt_thread_t s_speed_hold_thread = RT_NULL;
static control_speed_hold_ctx_t s_speed_hold_ctx;

static const rt_uint8_t s_joint_motor_map[7] =
{
    (rt_uint8_t)CONTROL_MOTOR_JOINT1_ID,
    (rt_uint8_t)CONTROL_MOTOR_JOINT2_ID,
    (rt_uint8_t)CONTROL_MOTOR_JOINT3_ID,
    (rt_uint8_t)CONTROL_MOTOR_JOINT4_ID,
    (rt_uint8_t)CONTROL_MOTOR_JOINT5_ID,
    (rt_uint8_t)CONTROL_MOTOR_JOINT6_ID,
    (rt_uint8_t)CONTROL_MOTOR_JOINT7_ID,
};

static const rt_uint8_t s_joint_protocol_map[7] =
{
    (rt_uint8_t)CONTROL_MOTOR_JOINT1_PROTOCOL,
    (rt_uint8_t)CONTROL_MOTOR_JOINT2_PROTOCOL,
    (rt_uint8_t)CONTROL_MOTOR_JOINT3_PROTOCOL,
    (rt_uint8_t)CONTROL_MOTOR_JOINT4_PROTOCOL,
    (rt_uint8_t)CONTROL_MOTOR_JOINT5_PROTOCOL,
    (rt_uint8_t)CONTROL_MOTOR_JOINT6_PROTOCOL,
    (rt_uint8_t)CONTROL_MOTOR_JOINT7_PROTOCOL,
};

static const float s_joint_gear_ratio_map[7] =
{
    CONTROL_MOTOR_JOINT1_GEAR_RATIO,
    CONTROL_MOTOR_JOINT2_GEAR_RATIO,
    CONTROL_MOTOR_JOINT3_GEAR_RATIO,
    CONTROL_MOTOR_JOINT4_GEAR_RATIO,
    CONTROL_MOTOR_JOINT5_GEAR_RATIO,
    CONTROL_MOTOR_JOINT6_GEAR_RATIO,
    CONTROL_MOTOR_JOINT7_GEAR_RATIO,
};

static const rt_uint8_t s_joint_calibrated_map[7] =
{
    (rt_uint8_t)CONTROL_MOTOR_JOINT1_CALIBRATED,
    (rt_uint8_t)CONTROL_MOTOR_JOINT2_CALIBRATED,
    (rt_uint8_t)CONTROL_MOTOR_JOINT3_CALIBRATED,
    (rt_uint8_t)CONTROL_MOTOR_JOINT4_CALIBRATED,
    (rt_uint8_t)CONTROL_MOTOR_JOINT5_CALIBRATED,
    (rt_uint8_t)CONTROL_MOTOR_JOINT6_CALIBRATED,
    (rt_uint8_t)CONTROL_MOTOR_JOINT7_CALIBRATED,
};

static const float s_joint_direction_map[7] =
{
    CONTROL_MOTOR_JOINT1_DIRECTION,
    CONTROL_MOTOR_JOINT2_DIRECTION,
    CONTROL_MOTOR_JOINT3_DIRECTION,
    CONTROL_MOTOR_JOINT4_DIRECTION,
    CONTROL_MOTOR_JOINT5_DIRECTION,
    CONTROL_MOTOR_JOINT6_DIRECTION,
    CONTROL_MOTOR_JOINT7_DIRECTION,
};

static const float s_joint_zero_offset_rad_map[7] =
{
    CONTROL_MOTOR_JOINT1_ZERO_OFFSET_RAD,
    CONTROL_MOTOR_JOINT2_ZERO_OFFSET_RAD,
    CONTROL_MOTOR_JOINT3_ZERO_OFFSET_RAD,
    CONTROL_MOTOR_JOINT4_ZERO_OFFSET_RAD,
    CONTROL_MOTOR_JOINT5_ZERO_OFFSET_RAD,
    CONTROL_MOTOR_JOINT6_ZERO_OFFSET_RAD,
    CONTROL_MOTOR_JOINT7_ZERO_OFFSET_RAD,
};

static const char *s_joint_zero_source_map[7] =
{
    CONTROL_MOTOR_JOINT1_ZERO_SOURCE,
    CONTROL_MOTOR_JOINT2_ZERO_SOURCE,
    CONTROL_MOTOR_JOINT3_ZERO_SOURCE,
    CONTROL_MOTOR_JOINT4_ZERO_SOURCE,
    CONTROL_MOTOR_JOINT5_ZERO_SOURCE,
    CONTROL_MOTOR_JOINT6_ZERO_SOURCE,
    CONTROL_MOTOR_JOINT7_ZERO_SOURCE,
};

static rt_uint16_t ctrl_u16_from_le(const rt_uint8_t *buf)
{
    return (rt_uint16_t)((rt_uint16_t)buf[0] | ((rt_uint16_t)buf[1] << 8));
}

static rt_int16_t ctrl_i16_from_le(const rt_uint8_t *buf)
{
    return (rt_int16_t)ctrl_u16_from_le(buf);
}

static rt_uint16_t ctrl_u16_from_be(const rt_uint8_t *buf)
{
    return (rt_uint16_t)(((rt_uint16_t)buf[0] << 8) | (rt_uint16_t)buf[1]);
}

static void ctrl_u16_to_be(rt_uint16_t value, rt_uint8_t *buf)
{
    buf[0] = (rt_uint8_t)((value >> 8) & 0xFFU);
    buf[1] = (rt_uint8_t)(value & 0xFFU);
}

static void ctrl_u16_to_le(rt_uint16_t value, rt_uint8_t *buf)
{
    buf[0] = (rt_uint8_t)(value & 0xFFU);
    buf[1] = (rt_uint8_t)((value >> 8) & 0xFFU);
}

static rt_uint32_t ctrl_u32_from_le(const rt_uint8_t *buf)
{
    return (rt_uint32_t)buf[0] |
           ((rt_uint32_t)buf[1] << 8) |
           ((rt_uint32_t)buf[2] << 16) |
           ((rt_uint32_t)buf[3] << 24);
}

static rt_uint64_t ctrl_u64_from_le(const rt_uint8_t *buf)
{
    rt_uint64_t value = 0U;
    int i;

    for (i = 7; i >= 0; --i)
    {
        value = (value << 8) | (rt_uint64_t)buf[i];
    }

    return value;
}

static void ctrl_u32_to_le(rt_uint32_t value, rt_uint8_t *buf)
{
    buf[0] = (rt_uint8_t)(value & 0xFFU);
    buf[1] = (rt_uint8_t)((value >> 8) & 0xFFU);
    buf[2] = (rt_uint8_t)((value >> 16) & 0xFFU);
    buf[3] = (rt_uint8_t)((value >> 24) & 0xFFU);
}

static rt_int16_t ctrl_float_to_scaled_i16(float value, float scale)
{
    float scaled_f = value * scale;
    rt_int32_t scaled;

    if (scaled_f >= 0.0f)
    {
        scaled = (rt_int32_t)(scaled_f + 0.5f);
    }
    else
    {
        scaled = (rt_int32_t)(scaled_f - 0.5f);
    }

    if (scaled > 32767)
    {
        return 32767;
    }
    if (scaled < -32768)
    {
        return -32768;
    }

    return (rt_int16_t)scaled;
}

static rt_int8_t ctrl_float_to_scaled_i8(float value, float scale)
{
    float scaled_f = value * scale;
    rt_int32_t scaled;

    if (scaled_f >= 0.0f)
    {
        scaled = (rt_int32_t)(scaled_f + 0.5f);
    }
    else
    {
        scaled = (rt_int32_t)(scaled_f - 0.5f);
    }

    if (scaled > 127)
    {
        return 127;
    }
    if (scaled < -128)
    {
        return -128;
    }

    return (rt_int8_t)scaled;
}

static rt_uint8_t ctrl_temp_to_u8(float temp_c)
{
    if ((temp_c < 0.0f) || (temp_c > 254.0f))
    {
        return 0xFFU;
    }

    return (rt_uint8_t)(temp_c + 0.5f);
}

static void ctrl_i16_to_le(rt_int16_t value, rt_uint8_t *buf)
{
    rt_uint16_t raw = (rt_uint16_t)value;

    buf[0] = (rt_uint8_t)(raw & 0xFFU);
    buf[1] = (rt_uint8_t)((raw >> 8) & 0xFFU);
}

static float ctrl_float_from_le(const rt_uint8_t *buf)
{
    float value;

    rt_memcpy(&value, buf, sizeof(value));
    return value;
}

static void ctrl_float_to_le(float value, rt_uint8_t *buf)
{
    rt_memcpy(buf, &value, sizeof(value));
}

static rt_uint8_t ctrl_motor_id_by_joint(rt_uint8_t joint_id)
{
    if ((joint_id == 0U) || (joint_id > CONTROL_MOTOR_JOINT_COUNT))
    {
        return CONTROL_MOTOR_ID_INVALID;
    }

    return s_joint_motor_map[joint_id - 1U];
}

static rt_uint8_t ctrl_motor_protocol_by_joint(rt_uint8_t joint_id)
{
    if ((joint_id == 0U) || (joint_id > CONTROL_MOTOR_JOINT_COUNT))
    {
        return CONTROL_MOTOR_PROTOCOL_PRIVATE;
    }

    return s_joint_protocol_map[joint_id - 1U];
}

static float ctrl_motor_gear_ratio_by_joint(rt_uint8_t joint_id)
{
    float ratio;

    if ((joint_id == 0U) || (joint_id > CONTROL_MOTOR_JOINT_COUNT))
    {
        return 1.0f;
    }

    ratio = s_joint_gear_ratio_map[joint_id - 1U];
    return (ratio > 0.0f) ? ratio : 1.0f;
}

static rt_bool_t ctrl_motor_joint_is_calibrated(rt_uint8_t joint_id)
{
    if ((joint_id == 0U) || (joint_id > CONTROL_MOTOR_JOINT_COUNT))
    {
        return RT_FALSE;
    }

    return (s_joint_calibrated_map[joint_id - 1U] != 0U) ? RT_TRUE : RT_FALSE;
}

static float ctrl_motor_direction_by_joint(rt_uint8_t joint_id)
{
    float direction;

    if ((joint_id == 0U) || (joint_id > CONTROL_MOTOR_JOINT_COUNT))
    {
        return 1.0f;
    }

    direction = s_joint_direction_map[joint_id - 1U];
    return (direction < 0.0f) ? -1.0f : 1.0f;
}

static float ctrl_motor_zero_offset_by_joint(rt_uint8_t joint_id)
{
    if ((joint_id == 0U) || (joint_id > CONTROL_MOTOR_JOINT_COUNT))
    {
        return 0.0f;
    }

    return s_joint_zero_offset_rad_map[joint_id - 1U];
}

static const char *ctrl_motor_zero_source_by_joint(rt_uint8_t joint_id)
{
    if ((joint_id == 0U) || (joint_id > CONTROL_MOTOR_JOINT_COUNT))
    {
        return "invalid_joint";
    }

    return s_joint_zero_source_map[joint_id - 1U];
}

static float ctrl_joint_to_motor_position(rt_uint8_t joint_id, float joint_pos_rad)
{
    return (joint_pos_rad *
            ctrl_motor_direction_by_joint(joint_id) *
            ctrl_motor_gear_ratio_by_joint(joint_id)) +
           ctrl_motor_zero_offset_by_joint(joint_id);
}

static float ctrl_motor_to_joint_position(rt_uint8_t joint_id, float motor_pos_rad)
{
    return ((motor_pos_rad - ctrl_motor_zero_offset_by_joint(joint_id)) /
            ctrl_motor_gear_ratio_by_joint(joint_id)) *
           ctrl_motor_direction_by_joint(joint_id);
}

static float ctrl_joint_to_motor_velocity(rt_uint8_t joint_id, float joint_vel_rad_s)
{
    return joint_vel_rad_s *
           ctrl_motor_direction_by_joint(joint_id) *
           ctrl_motor_gear_ratio_by_joint(joint_id);
}

static float ctrl_motor_to_joint_velocity(rt_uint8_t joint_id, float motor_vel_rad_s)
{
    return (motor_vel_rad_s / ctrl_motor_gear_ratio_by_joint(joint_id)) *
           ctrl_motor_direction_by_joint(joint_id);
}

static rt_bool_t ctrl_motor_id_invalid_for_joint(rt_uint8_t joint_id, rt_uint8_t motor_id)
{
    rt_uint8_t protocol;

    if ((joint_id == 0U) || (joint_id > CONTROL_MOTOR_JOINT_COUNT) ||
        (motor_id == CONTROL_MOTOR_ID_INVALID))
    {
        return RT_TRUE;
    }

    protocol = ctrl_motor_protocol_by_joint(joint_id);
    if (protocol == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        return (motor_id > 0x3FU) ? RT_TRUE : RT_FALSE;
    }

    return (motor_id == 0U) ? RT_TRUE : RT_FALSE;
}

static rt_err_t ctrl_apply_ros_command(const control_ros_command_t *cmd);
static rt_bool_t ctrl_ros_command_is_calibration_telemetry(const control_ros_command_t *cmd);

static int ctrl_motor_index_by_motor_id(rt_uint8_t motor_id)
{
    rt_uint8_t i;

    for (i = 0U; i < CONTROL_MOTOR_JOINT_COUNT; i++)
    {
        if ((s_joint_motor_map[i] == motor_id) &&
            (s_joint_protocol_map[i] == CONTROL_MOTOR_PROTOCOL_PRIVATE))
        {
            return (int)i;
        }
    }

    return -1;
}

static int ctrl_motor_index_by_cansimple_node(rt_uint8_t node_id)
{
    rt_uint8_t i;

    for (i = 0U; i < CONTROL_MOTOR_JOINT_COUNT; i++)
    {
        if ((s_joint_motor_map[i] == node_id) &&
            (s_joint_protocol_map[i] == CONTROL_MOTOR_PROTOCOL_CANSIMPLE))
        {
            return (int)i;
        }
    }

    return -1;
}

static float ctrl_uint_to_float(rt_uint32_t x_int, float x_min, float x_max, int bits)
{
    const float span = x_max - x_min;
    const float offset = x_min;
    const rt_uint32_t max_int = (rt_uint32_t)((1UL << bits) - 1UL);

    return ((float)x_int) * span / (float)max_int + offset;
}

static rt_uint32_t ctrl_float_to_uint(float x, float x_min, float x_max, int bits)
{
    const float span = x_max - x_min;
    const float offset = x_min;
    float clamped = x;
    float normalized;
    rt_uint32_t max_int = (rt_uint32_t)((1UL << bits) - 1UL);

    if (clamped < x_min)
    {
        clamped = x_min;
    }
    if (clamped > x_max)
    {
        clamped = x_max;
    }

    normalized = (clamped - offset) * (float)max_int / span;
    if (normalized < 0.0f)
    {
        normalized = 0.0f;
    }
    if (normalized > (float)max_int)
    {
        normalized = (float)max_int;
    }

    return (rt_uint32_t)(normalized + 0.5f);
}

static rt_int32_t ctrl_float_to_scaled_i32(float value, float scale)
{
    float scaled = value * scale;

    if (scaled >= 0.0f)
    {
        return (rt_int32_t)(scaled + 0.5f);
    }

    return (rt_int32_t)(scaled - 0.5f);
}

static rt_uint32_t ctrl_motor_private_ext_id(rt_uint8_t comm_type, rt_uint16_t data2, rt_uint8_t data1)
{
    return (((rt_uint32_t)comm_type & 0x1FU) << 24) |
           (((rt_uint32_t)data2 & 0xFFFFU) << 8) |
           ((rt_uint32_t)data1 & 0xFFU);
}

static rt_err_t ctrl_can_send(rt_uint32_t id, rt_uint8_t ide, const rt_uint8_t *data, rt_uint8_t len)
{
    struct rt_can_msg msg;
    rt_ssize_t written;

    if ((s_can_dev == RT_NULL) || (len > 8U) || ((data == RT_NULL) && (len > 0U)))
    {
        return -RT_EINVAL;
    }

    rt_memset(&msg, 0, sizeof(msg));
    msg.id = id;
    msg.ide = ide;
    msg.rtr = RT_CAN_DTR;
    msg.len = len;
    msg.hdr_index = -1;
#if defined(RT_CAN_USING_CANFD)
    msg.fd_frame = 0U;
    msg.brs = 0U;
#endif
    if (len > 0U)
    {
        rt_memcpy(msg.data, data, len);
    }

#if CONTROL_CAN_USE_DIRECT_PDL
    written = ifx_can_direct_send(&msg);
    return (written == RT_EOK) ? RT_EOK : -RT_ERROR;
#else
    written = rt_device_write(s_can_dev, 0, &msg, sizeof(msg));
    return (written == sizeof(msg)) ? RT_EOK : -RT_ERROR;
#endif
}

static rt_uint32_t ctrl_cansimple_std_id(rt_uint8_t node_id, rt_uint8_t cmd_id)
{
    return (((rt_uint32_t)node_id & 0x3FU) << 5) | ((rt_uint32_t)cmd_id & 0x1FU);
}

static rt_err_t ctrl_cansimple_send(rt_uint8_t node_id, rt_uint8_t cmd_id, const rt_uint8_t *data, rt_uint8_t len)
{
    if (node_id > 0x3FU)
    {
        return -RT_EINVAL;
    }

    return ctrl_can_send(ctrl_cansimple_std_id(node_id, cmd_id), RT_CAN_STDID, data, len);
}

static rt_uint64_t ctrl_u48_from_le(const rt_uint8_t *data)
{
    rt_uint64_t value = 0U;
    int i;

    for (i = 5; i >= 0; --i)
    {
        value = (value << 8) | (rt_uint64_t)data[i];
    }

    return value;
}

static void ctrl_cansimple_note_heartbeat(rt_uint8_t node_id,
                                          rt_uint32_t axis_error,
                                          rt_uint8_t axis_state,
                                          rt_uint8_t flags,
                                          rt_int8_t temp_c,
                                          rt_uint8_t life)
{
    if (node_id > 0x3FU)
    {
        return;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    s_cansimple_seen[node_id] = RT_TRUE;
    s_cansimple_axis_error[node_id] = axis_error;
    s_cansimple_axis_state[node_id] = axis_state;
    s_cansimple_flags[node_id] = flags;
    s_cansimple_temp_c[node_id] = temp_c;
    s_cansimple_life[node_id] = life;
    s_cansimple_heartbeat_tick[node_id] = rt_tick_get();
    rt_mutex_release(&s_data_lock);
}

static void ctrl_cansimple_note_error(rt_uint8_t node_id,
                                      rt_uint8_t len,
                                      rt_uint64_t value)
{
    rt_uint8_t type;

    if (node_id > 0x3FU)
    {
        return;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    type = s_cansimple_error_type[node_id];
    s_cansimple_error_seen[node_id] = RT_TRUE;
    s_cansimple_error_len[node_id] = len;
    s_cansimple_error_value[node_id] = value;
    s_cansimple_error_tick[node_id] = rt_tick_get();
    rt_mutex_release(&s_data_lock);

    rt_kprintf("[control] cansimple error node=%u type=%u len=%u value=0x%08X%08X\n",
               (unsigned int)node_id,
               (unsigned int)type,
               (unsigned int)len,
               (unsigned int)((value >> 32) & 0xFFFFFFFFULL),
               (unsigned int)(value & 0xFFFFFFFFULL));
}

static rt_err_t ctrl_cansimple_request_error(rt_uint8_t node_id, rt_uint8_t error_type)
{
    rt_uint8_t payload[8] = {0};

    if ((node_id > 0x3FU) ||
        !((error_type == 0U) || (error_type == 1U) ||
          (error_type == 3U) || (error_type == 4U)))
    {
        return -RT_EINVAL;
    }

    payload[0] = error_type;
    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    s_cansimple_error_type[node_id] = error_type;
    s_cansimple_error_seen[node_id] = RT_FALSE;
    rt_mutex_release(&s_data_lock);

    return ctrl_cansimple_send(node_id, CANSIMPLE_CMD_GET_ERROR, payload, 1U);
}

static rt_err_t ctrl_cansimple_wait_axis_state(rt_uint8_t node_id,
                                               rt_uint8_t axis_state,
                                               rt_uint32_t timeout_ms)
{
    rt_tick_t start_tick;
    rt_tick_t timeout_tick;

    if (node_id > 0x3FU)
    {
        return -RT_EINVAL;
    }

    start_tick = rt_tick_get();
    timeout_tick = rt_tick_from_millisecond(timeout_ms);
    do
    {
        rt_bool_t ready;

        rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
        ready = (s_cansimple_seen[node_id] &&
                 (s_cansimple_axis_state[node_id] == axis_state) &&
                 (s_cansimple_axis_error[node_id] == 0U));
        rt_mutex_release(&s_data_lock);

        if (ready)
        {
            return RT_EOK;
        }

        rt_thread_mdelay(10);
    } while ((rt_tick_get() - start_tick) < timeout_tick);

    return -RT_ETIMEOUT;
}

static rt_err_t ctrl_cansimple_request_address(void)
{
    return ctrl_cansimple_send(CANSIMPLE_NODE_ID_BROADCAST, CANSIMPLE_CMD_ADDRESS, RT_NULL, 0U);
}

static rt_err_t ctrl_cansimple_set_axis_state(rt_uint8_t node_id, rt_uint32_t axis_state)
{
    rt_uint8_t payload[4] = {0};

    ctrl_u32_to_le(axis_state, &payload[0]);
    return ctrl_cansimple_send(node_id, CANSIMPLE_CMD_SET_AXIS_STATE, payload, sizeof(payload));
}

static rt_err_t ctrl_cansimple_clear_errors(rt_uint8_t node_id)
{
    rt_uint8_t payload[8] = {0};

    return ctrl_cansimple_send(node_id, CANSIMPLE_CMD_CLEAR_ERRORS, payload, sizeof(payload));
}

static rt_err_t ctrl_cansimple_set_controller_mode(rt_uint8_t node_id,
                                                   rt_uint32_t control_mode,
                                                   rt_uint32_t input_mode)
{
    rt_uint8_t payload[8] = {0};

    ctrl_u32_to_le(control_mode, &payload[0]);
    ctrl_u32_to_le(input_mode, &payload[4]);
    return ctrl_cansimple_send(node_id, CANSIMPLE_CMD_SET_CONTROLLER_MODE, payload, sizeof(payload));
}

static rt_err_t ctrl_cansimple_set_input_vel_node(rt_uint8_t node_id, float vel_rad_s, float torque_ff_nm)
{
    rt_uint8_t payload[8] = {0};
    float vel_rev_s;

    vel_rev_s = vel_rad_s * CONTROL_CANSIMPLE_VEL_REV_PER_RAD_S;
    ctrl_float_to_le(vel_rev_s, &payload[0]);
    ctrl_float_to_le(torque_ff_nm, &payload[4]);

    return ctrl_cansimple_send(node_id, CANSIMPLE_CMD_SET_INPUT_VEL, payload, sizeof(payload));
}

static rt_err_t ctrl_cansimple_velocity_start_node(rt_uint8_t node_id,
                                                   float speed_rad_s,
                                                   float limit_cur,
                                                   rt_bool_t clear_errors)
{
    rt_uint8_t payload[8] = {0};
    float vel_limit = speed_rad_s;
    rt_err_t ret;

    if (vel_limit < 0.0f)
    {
        vel_limit = -vel_limit;
    }

    if (clear_errors)
    {
        ret = ctrl_cansimple_clear_errors(node_id);
        if (ret != RT_EOK)
        {
            return ret;
        }
        rt_thread_mdelay(5);
    }

    ret = ctrl_cansimple_set_axis_state(node_id, CANSIMPLE_AXIS_STATE_CLOSED_LOOP);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_thread_mdelay(20);
    ret = ctrl_cansimple_set_controller_mode(node_id,
                                             CANSIMPLE_CONTROL_MODE_VELOCITY,
                                             CANSIMPLE_INPUT_MODE_PASSTHROUGH);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_thread_mdelay(5);
    ctrl_float_to_le(vel_limit * CONTROL_CANSIMPLE_VEL_REV_PER_RAD_S, &payload[0]);
    ctrl_float_to_le(limit_cur, &payload[4]);
    ret = ctrl_cansimple_send(node_id, CANSIMPLE_CMD_SET_LIMITS, payload, sizeof(payload));
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_thread_mdelay(5);
    ret = ctrl_cansimple_wait_axis_state(node_id,
                                         CANSIMPLE_AXIS_STATE_CLOSED_LOOP,
                                         CONTROL_CANSIMPLE_CLOSED_LOOP_WAIT_MS);
    if (ret != RT_EOK)
    {
        rt_kprintf("[control] cansimple node=%u no closed-loop heartbeat ret=%d, continue\n",
                   (unsigned int)node_id,
                   ret);
    }

    return ctrl_cansimple_set_input_vel_node(node_id, speed_rad_s, 0.0f);
}

static rt_err_t ctrl_cansimple_mit_control(rt_uint8_t node_id,
                                           float target_pos_rad,
                                           float target_vel_rad_s,
                                           float kp,
                                           float kd,
                                           float target_torque_nm)
{
    rt_uint8_t payload[8];
    rt_uint16_t pos_u;
    rt_uint16_t vel_u;
    rt_uint16_t kp_u;
    rt_uint16_t kd_u;
    rt_uint16_t tor_u;

    pos_u = (rt_uint16_t)ctrl_float_to_uint(target_pos_rad,
                                            CONTROL_CANSIMPLE_MIT_P_MIN_RAD,
                                            CONTROL_CANSIMPLE_MIT_P_MAX_RAD,
                                            16);
    vel_u = (rt_uint16_t)ctrl_float_to_uint(target_vel_rad_s,
                                            CONTROL_CANSIMPLE_MIT_V_MIN_RAD_S,
                                            CONTROL_CANSIMPLE_MIT_V_MAX_RAD_S,
                                            12);
    kp_u = (rt_uint16_t)ctrl_float_to_uint(kp,
                                           CONTROL_MOTOR_KP_MIN,
                                           CONTROL_MOTOR_KP_MAX,
                                           12);
    kd_u = (rt_uint16_t)ctrl_float_to_uint(kd,
                                           CONTROL_MOTOR_KD_MIN,
                                           CONTROL_MOTOR_KD_MAX,
                                           12);
    tor_u = (rt_uint16_t)ctrl_float_to_uint(target_torque_nm,
                                            CONTROL_CANSIMPLE_MIT_T_MIN_NM,
                                            CONTROL_CANSIMPLE_MIT_T_MAX_NM,
                                            12);

    payload[0] = (rt_uint8_t)((pos_u >> 8) & 0xFFU);
    payload[1] = (rt_uint8_t)(pos_u & 0xFFU);
    payload[2] = (rt_uint8_t)((vel_u >> 4) & 0xFFU);
    payload[3] = (rt_uint8_t)(((vel_u & 0x0FU) << 4) | ((kp_u >> 8) & 0x0FU));
    payload[4] = (rt_uint8_t)(kp_u & 0xFFU);
    payload[5] = (rt_uint8_t)((kd_u >> 4) & 0xFFU);
    payload[6] = (rt_uint8_t)(((kd_u & 0x0FU) << 4) | ((tor_u >> 8) & 0x0FU));
    payload[7] = (rt_uint8_t)(tor_u & 0xFFU);

    return ctrl_cansimple_send(node_id, CANSIMPLE_CMD_MIT_CONTROL, payload, sizeof(payload));
}

static void ctrl_update_emg_report(const struct rt_can_msg *msg)
{
    control_emg_report_t tmp;
    float ch1_mv;
    float ch2_mv;
    float rms_mv;

    if (msg->len < 8U)
    {
        return;
    }

    rt_memcpy(&ch1_mv, &msg->data[0], sizeof(ch1_mv));
    rt_memcpy(&ch2_mv, &msg->data[4], sizeof(ch2_mv));
    if (ch1_mv < 0.0f)
    {
        ch1_mv = 0.0f;
    }
    if (ch2_mv < 0.0f)
    {
        ch2_mv = 0.0f;
    }
    rms_mv = (ch1_mv + ch2_mv) * 0.5f;

    tmp.ch1_raw = (rt_uint16_t)ctrl_float_to_scaled_i32(ch1_mv, 1.0f);
    tmp.ch2_raw = (rt_uint16_t)ctrl_float_to_scaled_i32(ch2_mv, 1.0f);
    tmp.rms_raw = (rt_uint16_t)ctrl_float_to_scaled_i32(rms_mv, 1.0f);
    tmp.seq = 0U;
    tmp.status = 0U;
    tmp.timestamp = rt_tick_get();

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    s_emg_report = tmp;
    rt_mutex_release(&s_data_lock);
}

static void ctrl_update_heart_report(const struct rt_can_msg *msg)
{
    control_heart_report_t tmp;
    rt_uint32_t timestamp_ms;

    if (msg->len < 8U)
    {
        return;
    }

    tmp.bpm = ctrl_u16_from_le(&msg->data[0]);
    tmp.hrv_ms = ctrl_u16_from_le(&msg->data[2]);
    timestamp_ms = (rt_uint32_t)msg->data[4] |
                   ((rt_uint32_t)msg->data[5] << 8) |
                   ((rt_uint32_t)msg->data[6] << 16) |
                   ((rt_uint32_t)msg->data[7] << 24);
    tmp.signal_quality = (tmp.hrv_ms > 0U) ? 100U : 0U;
    tmp.status = 0U;
    tmp.timestamp = rt_tick_get();
    RT_UNUSED(timestamp_ms);

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    s_heart_report = tmp;
    rt_mutex_release(&s_data_lock);
}

static void ctrl_update_motor_feedback_private(const struct rt_can_msg *msg)
{
    rt_uint8_t comm_type;
    rt_uint8_t host_id;
    rt_uint16_t data2;
    rt_uint8_t motor_id;
    rt_uint8_t fault_summary;
    rt_uint8_t mode_state;
    int idx;
    control_motor_feedback_t fb;
    rt_uint16_t pos_u;
    rt_uint16_t vel_u;
    rt_uint16_t tor_u;
    rt_uint16_t temp_u;

    if ((msg->ide != RT_CAN_EXTID) || (msg->len < 8U))
    {
        return;
    }

    comm_type = (rt_uint8_t)((msg->id >> 24) & 0x1FU);
    if ((comm_type != MOTOR_PRIVATE_TYPE_FEEDBACK) && (comm_type != MOTOR_PRIVATE_TYPE_ACTIVE_REPORT))
    {
        return;
    }

    host_id = (rt_uint8_t)(msg->id & 0xFFU);
    if (host_id != (rt_uint8_t)CONTROL_MOTOR_MASTER_ID)
    {
        return;
    }

    data2 = (rt_uint16_t)((msg->id >> 8) & 0xFFFFU);
    motor_id = (rt_uint8_t)(data2 & 0xFFU);
    fault_summary = (rt_uint8_t)((data2 >> 8) & 0x3FU);
    mode_state = (rt_uint8_t)((data2 >> 14) & 0x03U);

    idx = ctrl_motor_index_by_motor_id(motor_id);
    if (idx < 0)
    {
        return;
    }

    pos_u = ctrl_u16_from_be(&msg->data[0]);
    vel_u = ctrl_u16_from_be(&msg->data[2]);
    tor_u = ctrl_u16_from_be(&msg->data[4]);
    temp_u = ctrl_u16_from_be(&msg->data[6]);

    fb.motor_id = motor_id;
    fb.protocol = CONTROL_MOTOR_PROTOCOL_TYPE_PRIVATE;
    fb.mode_state = mode_state;
    fb.fault_summary = fault_summary;
    fb.pos_rad = ctrl_uint_to_float(pos_u, CONTROL_MOTOR_P_MIN_RAD, CONTROL_MOTOR_P_MAX_RAD, 16);
    fb.vel_rad_s = ctrl_uint_to_float(vel_u, CONTROL_MOTOR_V_MIN_RAD_S, CONTROL_MOTOR_V_MAX_RAD_S, 16);
    fb.torque_nm = ctrl_uint_to_float(tor_u, CONTROL_MOTOR_T_MIN_NM, CONTROL_MOTOR_T_MAX_NM, 16);
    fb.temp_c = ((float)temp_u) / 10.0f;
    fb.timestamp = rt_tick_get();

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    s_motor_feedback[idx] = fb;
    rt_mutex_release(&s_data_lock);
}

static void ctrl_update_motor_feedback_cansimple(const struct rt_can_msg *msg)
{
    rt_uint8_t node_id;
    rt_uint8_t cmd_id;
    int idx;
    control_motor_feedback_t fb;
    rt_uint32_t active_errors;
    rt_uint16_t pos_u;
    rt_uint16_t vel_u;
    rt_uint16_t tor_u;

    if ((msg == RT_NULL) || (msg->ide != RT_CAN_STDID) || (msg->len < 1U))
    {
        return;
    }

    node_id = (rt_uint8_t)((msg->id >> 5) & 0x3FU);
    cmd_id = (rt_uint8_t)(msg->id & 0x1FU);

    idx = ctrl_motor_index_by_cansimple_node(node_id);
    if ((idx < 0) && (cmd_id != CANSIMPLE_CMD_ADDRESS))
    {
        return;
    }

    if ((cmd_id == CANSIMPLE_CMD_GET_ERROR) && ((msg->len == 4U) || (msg->len == 8U)))
    {
        rt_uint64_t value = (msg->len == 8U) ?
                            ctrl_u64_from_le(&msg->data[0]) :
                            (rt_uint64_t)ctrl_u32_from_le(&msg->data[0]);

        ctrl_cansimple_note_error(node_id, msg->len, value);
        return;
    }

    if ((cmd_id == CANSIMPLE_CMD_TX_SDO) && (msg->len >= 8U))
    {
        rt_uint16_t endpoint_id = ctrl_u16_from_le(&msg->data[1]);
        rt_uint32_t value = ctrl_u32_from_le(&msg->data[4]);

        rt_kprintf("[control] cansimple txsdo node=%u opcode=%u endpoint=%u value=0x%08X\n",
                   (unsigned int)node_id,
                   (unsigned int)msg->data[0],
                   (unsigned int)endpoint_id,
                   (unsigned int)value);
        return;
    }

    if (cmd_id == CANSIMPLE_CMD_ADDRESS)
    {
        if (msg->len >= 7U)
        {
            rt_uint8_t reported_node = msg->data[0];
            rt_uint64_t serial = ctrl_u48_from_le(&msg->data[1]);
            rt_uint32_t serial_lo = (rt_uint32_t)(serial & 0xFFFFFFFFULL);
            rt_uint16_t serial_hi = (rt_uint16_t)((serial >> 32) & 0xFFFFU);

            rt_kprintf("[control] cansimple address frame_node=%u node=%u serial=0x%04X%08X\n",
                       (unsigned int)node_id,
                       (unsigned int)reported_node,
                       (unsigned int)serial_hi,
                       (unsigned int)serial_lo);
        }
        return;
    }

    if ((cmd_id == CANSIMPLE_CMD_HEARTBEAT) && (msg->len >= 5U))
    {
        active_errors = ctrl_u32_from_le(&msg->data[0]);
        ctrl_cansimple_note_heartbeat(node_id,
                                      active_errors,
                                      msg->data[4],
                                      (msg->len >= 6U) ? msg->data[5] : 0U,
                                      (msg->len >= 7U) ? (rt_int8_t)msg->data[6] : 0,
                                      (msg->len >= 8U) ? msg->data[7] : 0U);
    }

    if (idx < 0)
    {
        return;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    fb = s_motor_feedback[idx];
    fb.motor_id = node_id;
    fb.protocol = CONTROL_MOTOR_PROTOCOL_TYPE_CANSIMPLE;
    fb.timestamp = rt_tick_get();

    switch (cmd_id)
    {
    case CANSIMPLE_CMD_HEARTBEAT:
        if (msg->len >= 5U)
        {
            active_errors = ctrl_u32_from_le(&msg->data[0]);
            fb.fault_summary = (rt_uint8_t)(active_errors & 0xFFU);
            fb.mode_state = msg->data[4];
            if (msg->len >= 7U)
            {
                fb.temp_c = (float)((rt_int8_t)msg->data[6]);
            }
        }
        break;

    case CANSIMPLE_CMD_MIT_CONTROL:
        if (msg->len >= 6U)
        {
            float motor_pos_rad;
            float motor_vel_rad_s;

            pos_u = ((rt_uint16_t)msg->data[1] << 8) | (rt_uint16_t)msg->data[2];
            vel_u = ((rt_uint16_t)msg->data[3] << 4) | ((rt_uint16_t)msg->data[4] >> 4);
            tor_u = (((rt_uint16_t)msg->data[4] & 0x0FU) << 8) | (rt_uint16_t)msg->data[5];
            motor_pos_rad = ctrl_uint_to_float(pos_u,
                                               CONTROL_CANSIMPLE_MIT_P_MIN_RAD,
                                               CONTROL_CANSIMPLE_MIT_P_MAX_RAD,
                                               16);
            motor_vel_rad_s = ctrl_uint_to_float(vel_u,
                                                 CONTROL_CANSIMPLE_MIT_V_MIN_RAD_S,
                                                 CONTROL_CANSIMPLE_MIT_V_MAX_RAD_S,
                                                 12);
            fb.pos_rad = ctrl_motor_to_joint_position((rt_uint8_t)(idx + 1), motor_pos_rad);
            fb.vel_rad_s = ctrl_motor_to_joint_velocity((rt_uint8_t)(idx + 1), motor_vel_rad_s);
            fb.torque_nm = ctrl_uint_to_float(tor_u,
                                              CONTROL_CANSIMPLE_MIT_T_MIN_NM,
                                              CONTROL_CANSIMPLE_MIT_T_MAX_NM,
                                              12);
        }
        break;

    case CANSIMPLE_CMD_GET_ENCODER_EST:
        if (msg->len >= 8U)
        {
            float motor_pos_rad = ctrl_float_from_le(&msg->data[0]) / CONTROL_CANSIMPLE_POS_REV_PER_RAD;
            float motor_vel_rad_s = ctrl_float_from_le(&msg->data[4]) / CONTROL_CANSIMPLE_VEL_REV_PER_RAD_S;

            fb.pos_rad = ctrl_motor_to_joint_position((rt_uint8_t)(idx + 1), motor_pos_rad);
            fb.vel_rad_s = ctrl_motor_to_joint_velocity((rt_uint8_t)(idx + 1), motor_vel_rad_s);
        }
        break;

    case CANSIMPLE_CMD_GET_TORQUES:
        if (msg->len >= 8U)
        {
            fb.torque_nm = ctrl_float_from_le(&msg->data[4]);
        }
        break;

    default:
        break;
    }

    s_motor_feedback[idx] = fb;
    rt_mutex_release(&s_data_lock);
}

static void ctrl_update_f103_sensor_report(const struct rt_can_msg *msg)
{
    control_sensor_node_sample_t node;
    control_emg_report_t emg;
    control_heart_report_t heart;
    rt_uint16_t emg_raw;
    rt_int16_t emg_filt;
    rt_uint16_t hr_raw;
    rt_uint8_t hr_filt;
    rt_uint8_t flags;
    rt_tick_t now;
    rt_int32_t emg_filt_abs;

    if ((msg == RT_NULL) || (msg->len < 8U))
    {
        return;
    }

    emg_raw = ctrl_u16_from_le(&msg->data[0]);
    emg_filt = ctrl_i16_from_le(&msg->data[2]);
    hr_raw = ctrl_u16_from_le(&msg->data[4]);
    hr_filt = msg->data[6];
    flags = msg->data[7];
    now = rt_tick_get();

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    node = s_sensor_node_sample;
    node.emg_raw = emg_raw;
    node.emg_filt = emg_filt;
    node.hr_raw = hr_raw;
    node.hr_filt = hr_filt;
    node.flags = flags;
    node.sensor_timestamp = now;
    s_sensor_node_sample = node;

    emg_filt_abs = (emg_filt < 0) ? -(rt_int32_t)emg_filt : (rt_int32_t)emg_filt;
    emg.ch1_raw = emg_raw;
    emg.ch2_raw = (rt_uint16_t)((emg_filt_abs > 65535) ? 65535 : emg_filt_abs);
    emg.rms_raw = emg.ch2_raw;
    emg.seq = 0U;
    emg.status = flags;
    emg.timestamp = now;
    s_emg_report = emg;

    heart.bpm = hr_filt;
    heart.hrv_ms = hr_raw;
    heart.signal_quality = (flags & 0x02U) ? 100U : 0U;
    heart.status = flags;
    heart.timestamp = now;
    s_heart_report = heart;
    rt_mutex_release(&s_data_lock);
}

static void ctrl_update_f103_health_report(const struct rt_can_msg *msg)
{
    control_sensor_node_sample_t node;

    if ((msg == RT_NULL) || (msg->len < 8U))
    {
        return;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    node = s_sensor_node_sample;
    node.node_state = msg->data[0];
    node.node_err_cnt = ctrl_u16_from_le(&msg->data[1]);
    node.node_q_fill = msg->data[3];
    node.health_timestamp = rt_tick_get();
    s_sensor_node_sample = node;
    rt_mutex_release(&s_data_lock);
}

static void ctrl_update_f103_ack_report(const struct rt_can_msg *msg)
{
    control_sensor_node_sample_t node;

    if ((msg == RT_NULL) || (msg->len < 3U))
    {
        return;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    node = s_sensor_node_sample;
    node.last_ack_cmd = msg->data[0];
    node.last_ack_seq = msg->data[1];
    node.last_ack_status = msg->data[2];
    node.ack_timestamp = rt_tick_get();
    s_sensor_node_sample = node;
    rt_mutex_release(&s_data_lock);
}

static void ctrl_update_motor_param_private(const struct rt_can_msg *msg)
{
    rt_uint8_t comm_type;
    rt_uint8_t host_id;
    rt_uint16_t data2;
    rt_uint8_t motor_id;
    rt_uint16_t index;
    control_motor_param_report_t param;

    if ((msg->ide != RT_CAN_EXTID) || (msg->len < 8U))
    {
        return;
    }

    comm_type = (rt_uint8_t)((msg->id >> 24) & 0x1FU);
    if ((comm_type != MOTOR_PRIVATE_TYPE_PARAM_READ) && (comm_type != MOTOR_PRIVATE_TYPE_PARAM_WRITE))
    {
        return;
    }

    host_id = (rt_uint8_t)(msg->id & 0xFFU);
    if (host_id != (rt_uint8_t)CONTROL_MOTOR_MASTER_ID)
    {
        return;
    }

    data2 = (rt_uint16_t)((msg->id >> 8) & 0xFFFFU);
    motor_id = (rt_uint8_t)(data2 & 0xFFU);
    index = (rt_uint16_t)((rt_uint16_t)msg->data[0] | ((rt_uint16_t)msg->data[1] << 8));

    rt_memset(&param, 0, sizeof(param));
    param.motor_id = motor_id;
    param.index = index;
    param.raw_u8 = msg->data[4];
    param.timestamp = rt_tick_get();
    param.valid = RT_TRUE;
    rt_memcpy(&param.value_f32, &msg->data[4], sizeof(float));

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    s_last_motor_param = param;
    rt_mutex_release(&s_data_lock);

    if (index == MOTOR_PARAM_INDEX_RUN_MODE)
    {
        rt_kprintf("[control] motor%u param 0x%04X mode=%u\n",
                   (unsigned int)motor_id,
                   (unsigned int)index,
                   (unsigned int)param.raw_u8);
    }
    else
    {
        rt_kprintf("[control] motor%u param 0x%04X value_x10000=%d\n",
                   (unsigned int)motor_id,
                   (unsigned int)index,
                   (int)ctrl_float_to_scaled_i32(param.value_f32, 10000.0f));
    }
}

static void ctrl_update_motor_probe_private(const struct rt_can_msg *msg)
{
    rt_uint8_t comm_type;
    rt_uint8_t reply_id;
    rt_uint16_t data2;
    control_motor_probe_report_t probe;
    rt_uint8_t i;

    if ((msg->ide != RT_CAN_EXTID) || (msg->len < 8U))
    {
        return;
    }

    comm_type = (rt_uint8_t)((msg->id >> 24) & 0x1FU);
    if (comm_type != MOTOR_PRIVATE_TYPE_GET_ID)
    {
        return;
    }

    reply_id = (rt_uint8_t)(msg->id & 0xFFU);
    if (reply_id != MOTOR_PRIVATE_GET_ID_REPLY)
    {
        return;
    }

    data2 = (rt_uint16_t)((msg->id >> 8) & 0xFFFFU);

    rt_memset(&probe, 0, sizeof(probe));
    probe.motor_id = (rt_uint8_t)(data2 & 0xFFU);
    probe.timestamp = rt_tick_get();
    probe.valid = RT_TRUE;

    for (i = 0U; i < 8U; i++)
    {
        probe.unique_id |= ((rt_uint64_t)msg->data[i]) << (8U * i);
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    if (!s_motor_probe_pending)
    {
        rt_mutex_release(&s_data_lock);
        return;
    }

    if ((s_motor_probe_expected_id != MOTOR_PRIVATE_BROADCAST_ID) &&
        (probe.motor_id != s_motor_probe_expected_id))
    {
        rt_mutex_release(&s_data_lock);
        return;
    }

    s_last_motor_probe = probe;
    s_motor_probe_pending = RT_FALSE;
    rt_mutex_release(&s_data_lock);

    rt_kprintf("[control] probe reply motor=0x%02X uid=0x%08lx%08lx\n",
               (unsigned int)probe.motor_id,
               (unsigned long)(probe.unique_id >> 32),
               (unsigned long)(probe.unique_id & 0xFFFFFFFFULL));
}

static rt_bool_t ctrl_parse_ros_command_can(const struct rt_can_msg *msg, control_ros_command_t *out)
{
    if ((msg == RT_NULL) || (out == RT_NULL))
    {
        return RT_FALSE;
    }

    if ((msg->ide != RT_CAN_STDID) || (msg->id != CONTROL_CAN_ID_ROS_COMMAND) || (msg->len < 2U))
    {
        return RT_FALSE;
    }

    rt_memset(out, 0, sizeof(*out));
    out->joint_id = msg->data[1];
    out->timestamp = rt_tick_get();

    switch (msg->data[0])
    {
    case CONTROL_ROS_CMD_OP_ENABLE:
        out->command = CONTROL_ROS_CMD_ENABLE;
        return RT_TRUE;

    case CONTROL_ROS_CMD_OP_STOP:
        if (msg->len < 3U)
        {
            return RT_FALSE;
        }
        out->command = CONTROL_ROS_CMD_STOP;
        out->clear_fault = msg->data[2];
        return RT_TRUE;

    case CONTROL_ROS_CMD_OP_SET_TARGET:
        if (msg->len < 8U)
        {
            return RT_FALSE;
        }
        out->command = CONTROL_ROS_CMD_SET_TARGET;
        out->target_pos_01deg = ctrl_i16_from_le(&msg->data[2]);
        out->target_vel_rpm = ctrl_i16_from_le(&msg->data[4]);
        out->target_torque_ma = ctrl_i16_from_le(&msg->data[6]);
        return RT_TRUE;

    case CONTROL_ROS_CMD_OP_SET_MODE:
        if (msg->len < 3U)
        {
            return RT_FALSE;
        }
        out->command = CONTROL_ROS_CMD_SET_MODE;
        out->mode = msg->data[2];
        return RT_TRUE;

    case CONTROL_ROS_CMD_OP_SET_ZERO:
        out->command = CONTROL_ROS_CMD_SET_ZERO;
        return RT_TRUE;

    case CONTROL_ROS_CMD_OP_ACTIVE_REPORT:
        if (msg->len < 3U)
        {
            return RT_FALSE;
        }
        out->command = CONTROL_ROS_CMD_SET_ACTIVE_REPORT;
        out->active_report_enable = msg->data[2];
        return RT_TRUE;

    default:
        return RT_FALSE;
    }
}

static const char *ctrl_ros_command_name(control_ros_command_type_t command)
{
    switch (command)
    {
    case CONTROL_ROS_CMD_ENABLE:
        return "enable";
    case CONTROL_ROS_CMD_STOP:
        return "stop";
    case CONTROL_ROS_CMD_SET_TARGET:
        return "set_target";
    case CONTROL_ROS_CMD_SET_MODE:
        return "set_mode";
    case CONTROL_ROS_CMD_SET_ZERO:
        return "set_zero";
    case CONTROL_ROS_CMD_SET_ACTIVE_REPORT:
        return "active_report";
    default:
        return "unknown";
    }
}

static const rt_int16_t s_ros_joint_min_01deg[CONTROL_ROS_JOINT_COUNT] =
{
    CONTROL_ROS_JOINT0_MIN_01DEG,
    CONTROL_ROS_JOINT1_MIN_01DEG,
    CONTROL_ROS_JOINT2_MIN_01DEG,
    CONTROL_ROS_JOINT3_MIN_01DEG,
    CONTROL_ROS_JOINT4_MIN_01DEG,
};

static const rt_int16_t s_ros_joint_max_01deg[CONTROL_ROS_JOINT_COUNT] =
{
    CONTROL_ROS_JOINT0_MAX_01DEG,
    CONTROL_ROS_JOINT1_MAX_01DEG,
    CONTROL_ROS_JOINT2_MAX_01DEG,
    CONTROL_ROS_JOINT3_MAX_01DEG,
    CONTROL_ROS_JOINT4_MAX_01DEG,
};

static const rt_uint8_t s_ros_joint_motor_joint_map[CONTROL_ROS_JOINT_COUNT] =
{
    (rt_uint8_t)CONTROL_ROS_JOINT0_MOTOR_JOINT,
    (rt_uint8_t)CONTROL_ROS_JOINT1_MOTOR_JOINT,
    (rt_uint8_t)CONTROL_ROS_JOINT2_MOTOR_JOINT,
    (rt_uint8_t)CONTROL_ROS_JOINT3_MOTOR_JOINT,
    (rt_uint8_t)CONTROL_ROS_JOINT4_MOTOR_JOINT,
};

static rt_bool_t ctrl_ros_joint_limit(rt_uint8_t joint_id, rt_int16_t *min_01deg, rt_int16_t *max_01deg)
{
    if ((min_01deg == RT_NULL) || (max_01deg == RT_NULL) ||
        (joint_id >= CONTROL_ROS_JOINT_COUNT))
    {
        return RT_FALSE;
    }

    *min_01deg = s_ros_joint_min_01deg[joint_id];
    *max_01deg = s_ros_joint_max_01deg[joint_id];
    return RT_TRUE;
}

static rt_uint8_t ctrl_ros_joint_to_motor_joint(rt_uint8_t ros_joint_id)
{
    if (ros_joint_id >= CONTROL_ROS_JOINT_COUNT)
    {
        return CONTROL_MOTOR_ID_INVALID;
    }

    return s_ros_joint_motor_joint_map[ros_joint_id];
}

static rt_uint32_t ctrl_tick_delta_ms(rt_tick_t newer, rt_tick_t older)
{
    return (rt_uint32_t)(((newer - older) * 1000U) / RT_TICK_PER_SECOND);
}

static rt_bool_t ctrl_motor_feedback_is_fresh(const control_motor_feedback_t *fb, rt_tick_t now)
{
    if ((fb == RT_NULL) || (fb->timestamp == 0U))
    {
        return RT_FALSE;
    }

    return (ctrl_tick_delta_ms(now, fb->timestamp) <= CONTROL_M33_MOTOR_STATUS_FRESH_MS) ? RT_TRUE : RT_FALSE;
}

static rt_uint8_t ctrl_motor_status_flags(const control_motor_feedback_t *fb)
{
    rt_uint8_t flags = 0U;

    if (fb == RT_NULL)
    {
        return flags;
    }

    if (fb->mode_state != 0U)
    {
        flags |= 0x01U;
    }
    if (fb->fault_summary != 0U)
    {
        flags |= 0x02U;
    }

    return flags;
}

static rt_err_t ctrl_publish_motor_status_slot(rt_uint8_t slot, const control_motor_feedback_t *fb)
{
    rt_uint8_t payload[8] = {0};
    rt_int16_t position_mrad;
    rt_int8_t velocity_drad_s;

    if ((fb == RT_NULL) || (slot >= CONTROL_MOTOR_JOINT_COUNT))
    {
        return -RT_EINVAL;
    }

    position_mrad = ctrl_float_to_scaled_i16(fb->pos_rad, 1000.0f);
    velocity_drad_s = ctrl_float_to_scaled_i8(fb->vel_rad_s, 10.0f);

    payload[0] = CONTROL_M33_MOTOR_STATUS_MARKER;
    payload[1] = s_motor_status_seq++;
    payload[2] = fb->motor_id;
    payload[3] = ctrl_motor_status_flags(fb);
    ctrl_i16_to_le(position_mrad, &payload[4]);
    payload[6] = (rt_uint8_t)velocity_drad_s;
    payload[7] = ctrl_temp_to_u8(fb->temp_c);

    return ctrl_can_send(CONTROL_CAN_ID_M33_MOTOR_STATUS_BASE + slot,
                         RT_CAN_STDID,
                         payload,
                         sizeof(payload));
}

static rt_uint8_t ctrl_publish_cached_motor_status_once(void)
{
    control_motor_feedback_t snapshot[CONTROL_MOTOR_JOINT_COUNT];
    rt_tick_t now = rt_tick_get();
    rt_uint8_t i;
    rt_uint8_t sent = 0U;

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    rt_memcpy(snapshot, s_motor_feedback, sizeof(snapshot));
    rt_mutex_release(&s_data_lock);

    for (i = 0U; i < CONTROL_MOTOR_JOINT_COUNT; i++)
    {
        if (!ctrl_motor_feedback_is_fresh(&snapshot[i], now))
        {
            continue;
        }
        if (ctrl_publish_motor_status_slot(i, &snapshot[i]) == RT_EOK)
        {
            sent++;
        }
    }

    return sent;
}

static void ctrl_motor_status_entry(void *parameter)
{
    RT_UNUSED(parameter);

    while (1)
    {
        (void)ctrl_publish_cached_motor_status_once();
        rt_thread_mdelay(CONTROL_M33_MOTOR_STATUS_PERIOD_MS);
    }
}

typedef enum
{
    CONTROL_ROS_SAFETY_BOOT = 0,
    CONTROL_ROS_SAFETY_LOGGING_ONLY,
    CONTROL_ROS_SAFETY_READY,
    CONTROL_ROS_SAFETY_RUNNING,
    CONTROL_ROS_SAFETY_LIMITED,
    CONTROL_ROS_SAFETY_EMERGENCY_STOP,
    CONTROL_ROS_SAFETY_FAULT,
} control_ros_safety_state_t;

typedef enum
{
    CONTROL_ROS_DECISION_REJECT = 0,
    CONTROL_ROS_DECISION_ACCEPT,
} control_ros_decision_t;

typedef enum
{
    CONTROL_ROS_REJECT_NONE = 0,
    CONTROL_ROS_REJECT_LOGGING_ONLY,
    CONTROL_ROS_REJECT_HEARTBEAT_TIMEOUT,
    CONTROL_ROS_REJECT_UNKNOWN_JOINT,
    CONTROL_ROS_REJECT_POSITION_LIMIT,
    CONTROL_ROS_REJECT_SPEED_LIMIT,
    CONTROL_ROS_REJECT_TORQUE_LIMIT,
    CONTROL_ROS_REJECT_JOINT_UNCALIBRATED,
    CONTROL_ROS_REJECT_UNSUPPORTED_CMD,
} control_ros_reject_reason_t;

typedef struct
{
    control_ros_safety_state_t state;
    control_ros_decision_t decision;
    control_ros_reject_reason_t reason;
    rt_uint32_t heartbeat_age_ms;
    rt_bool_t heartbeat_ok;
    rt_bool_t joint_known;
    rt_int16_t joint_min_01deg;
    rt_int16_t joint_max_01deg;
    rt_bool_t target_in_limit;
    rt_bool_t rpm_in_limit;
    rt_bool_t torque_in_limit;
    rt_bool_t joint_calibrated;
} control_ros_safety_assessment_t;

typedef struct
{
    rt_bool_t logging_only_clear;
    rt_bool_t heartbeat_ok;
    rt_bool_t estop_input_confirmed;
    rt_bool_t estop_safe_now;
    rt_bool_t power_input_confirmed;
    rt_bool_t power_safe_now;
    rt_bool_t limits_confirmed;
    rt_bool_t limits_safe_now;
    rt_bool_t position_limits_confirmed;
    rt_bool_t position_limits_safe_now;
    rt_bool_t speed_limits_confirmed;
    rt_bool_t speed_limits_safe_now;
    rt_bool_t torque_current_limits_confirmed;
    rt_bool_t torque_current_limits_safe_now;
    rt_bool_t required_motor_feedback_fresh;
    rt_bool_t required_motor_feedback_fault_free;
    rt_uint32_t heartbeat_age_ms;
    rt_uint32_t required_joint_mask;
    rt_uint32_t fresh_joint_mask;
    rt_uint32_t fault_joint_mask;
    rt_uint8_t fresh_count;
    rt_bool_t ready;
} control_prearm_check_t;

typedef struct
{
    const char *name;
    const char *source;
    rt_bool_t confirmed;
    rt_bool_t safe_now;
    const char *meaning;
} control_safety_input_diag_t;

static const char *ctrl_ros_safety_state_name(control_ros_safety_state_t state)
{
    switch (state)
    {
    case CONTROL_ROS_SAFETY_BOOT:
        return "boot";
    case CONTROL_ROS_SAFETY_LOGGING_ONLY:
        return "logging_only";
    case CONTROL_ROS_SAFETY_READY:
        return "ready";
    case CONTROL_ROS_SAFETY_RUNNING:
        return "running";
    case CONTROL_ROS_SAFETY_LIMITED:
        return "limited";
    case CONTROL_ROS_SAFETY_EMERGENCY_STOP:
        return "emergency_stop";
    case CONTROL_ROS_SAFETY_FAULT:
        return "fault";
    default:
        return "unknown";
    }
}

static const char *ctrl_ros_decision_name(control_ros_decision_t decision)
{
    return (decision == CONTROL_ROS_DECISION_ACCEPT) ? "accept" : "reject";
}

static const char *ctrl_ros_reject_reason_name(control_ros_reject_reason_t reason)
{
    switch (reason)
    {
    case CONTROL_ROS_REJECT_NONE:
        return "none";
    case CONTROL_ROS_REJECT_LOGGING_ONLY:
        return "logging_only_no_motor_output";
    case CONTROL_ROS_REJECT_HEARTBEAT_TIMEOUT:
        return "heartbeat_timeout";
    case CONTROL_ROS_REJECT_UNKNOWN_JOINT:
        return "unknown_joint";
    case CONTROL_ROS_REJECT_POSITION_LIMIT:
        return "target_out_of_limit";
    case CONTROL_ROS_REJECT_SPEED_LIMIT:
        return "velocity_out_of_limit";
    case CONTROL_ROS_REJECT_TORQUE_LIMIT:
        return "torque_out_of_limit";
    case CONTROL_ROS_REJECT_JOINT_UNCALIBRATED:
        return "joint_uncalibrated";
    case CONTROL_ROS_REJECT_UNSUPPORTED_CMD:
        return "unsupported_command";
    default:
        return "unknown";
    }
}

static rt_uint8_t ctrl_ros_reject_reason_detail_code(control_ros_reject_reason_t reason)
{
    switch (reason)
    {
    case CONTROL_ROS_REJECT_NONE:
        return CONTROL_STATUS_DETAIL_NONE;
    case CONTROL_ROS_REJECT_LOGGING_ONLY:
        return CONTROL_STATUS_DETAIL_LOGGING_ONLY;
    case CONTROL_ROS_REJECT_HEARTBEAT_TIMEOUT:
        return CONTROL_STATUS_DETAIL_HEARTBEAT_TIMEOUT;
    case CONTROL_ROS_REJECT_UNKNOWN_JOINT:
        return CONTROL_STATUS_DETAIL_UNKNOWN_JOINT;
    case CONTROL_ROS_REJECT_POSITION_LIMIT:
        return CONTROL_STATUS_DETAIL_TARGET_OUT_OF_LIMIT;
    case CONTROL_ROS_REJECT_SPEED_LIMIT:
        return CONTROL_STATUS_DETAIL_VELOCITY_OUT_OF_LIMIT;
    case CONTROL_ROS_REJECT_TORQUE_LIMIT:
        return CONTROL_STATUS_DETAIL_TORQUE_OUT_OF_LIMIT;
    case CONTROL_ROS_REJECT_JOINT_UNCALIBRATED:
        return CONTROL_STATUS_DETAIL_JOINT_UNCALIBRATED;
    case CONTROL_ROS_REJECT_UNSUPPORTED_CMD:
        return CONTROL_STATUS_DETAIL_UNSUPPORTED_COMMAND;
    default:
        return CONTROL_STATUS_DETAIL_UNSUPPORTED_COMMAND;
    }
}

static void ctrl_prearm_check_build(control_prearm_check_t *check, rt_uint32_t required_joint_mask)
{
    control_motor_feedback_t snapshot[CONTROL_MOTOR_JOINT_COUNT];
    rt_tick_t now = rt_tick_get();
    rt_uint8_t i;

    if (check == RT_NULL)
    {
        return;
    }

    rt_memset(check, 0, sizeof(*check));
    check->heartbeat_age_ms = 0xFFFFFFFFUL;
    check->required_joint_mask = required_joint_mask;

#if CONTROL_ROS_COMMAND_LOGGING_ONLY && !CONTROL_PREARM_ALLOW_WITH_LOGGING_ONLY
    check->logging_only_clear = RT_FALSE;
#else
    check->logging_only_clear = RT_TRUE;
#endif

    if (s_has_nanopi_heartbeat)
    {
        check->heartbeat_age_ms = ctrl_tick_delta_ms(now, s_last_nanopi_heartbeat_tick);
        check->heartbeat_ok =
            (check->heartbeat_age_ms <= CONTROL_ROS_HEARTBEAT_TIMEOUT_MS) ? RT_TRUE : RT_FALSE;
    }

    check->estop_input_confirmed =
        (CONTROL_PREARM_ESTOP_INPUT_CONFIRMED != 0U) ? RT_TRUE : RT_FALSE;
    check->estop_safe_now =
        (CONTROL_PREARM_ESTOP_SAFE_NOW != 0U) ? RT_TRUE : RT_FALSE;
    check->power_input_confirmed =
        ((CONTROL_PREARM_POWER_CHECK_REQUIRED == 0U) ||
         (CONTROL_PREARM_POWER_INPUT_CONFIRMED != 0U)) ? RT_TRUE : RT_FALSE;
    check->power_safe_now =
        ((CONTROL_PREARM_POWER_CHECK_REQUIRED == 0U) ||
         (CONTROL_PREARM_POWER_SAFE_NOW != 0U)) ? RT_TRUE : RT_FALSE;
    check->position_limits_confirmed =
        (CONTROL_PREARM_POSITION_LIMITS_CONFIRMED != 0U) ? RT_TRUE : RT_FALSE;
    check->position_limits_safe_now =
        (CONTROL_PREARM_POSITION_LIMITS_SAFE_NOW != 0U) ? RT_TRUE : RT_FALSE;
    check->speed_limits_confirmed =
        (CONTROL_PREARM_SPEED_LIMITS_CONFIRMED != 0U) ? RT_TRUE : RT_FALSE;
    check->speed_limits_safe_now =
        (CONTROL_PREARM_SPEED_LIMITS_SAFE_NOW != 0U) ? RT_TRUE : RT_FALSE;
    check->torque_current_limits_confirmed =
        (CONTROL_PREARM_TORQUE_CURRENT_LIMITS_CONFIRMED != 0U) ? RT_TRUE : RT_FALSE;
    check->torque_current_limits_safe_now =
        (CONTROL_PREARM_TORQUE_CURRENT_LIMITS_SAFE_NOW != 0U) ? RT_TRUE : RT_FALSE;
    check->limits_confirmed =
        ((CONTROL_PREARM_LIMITS_CONFIRMED != 0U) &&
         check->position_limits_confirmed &&
         check->speed_limits_confirmed &&
         check->torque_current_limits_confirmed) ? RT_TRUE : RT_FALSE;
    check->limits_safe_now =
        ((CONTROL_PREARM_LIMITS_SAFE_NOW != 0U) &&
         check->position_limits_safe_now &&
         check->speed_limits_safe_now &&
         check->torque_current_limits_safe_now) ? RT_TRUE : RT_FALSE;

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    rt_memcpy(snapshot, s_motor_feedback, sizeof(snapshot));
    rt_mutex_release(&s_data_lock);

    for (i = 0U; i < CONTROL_MOTOR_JOINT_COUNT; i++)
    {
        rt_uint32_t bit = (1UL << i);

        if ((check->required_joint_mask & bit) == 0U)
        {
            continue;
        }

        if (ctrl_motor_feedback_is_fresh(&snapshot[i], now))
        {
            check->fresh_joint_mask |= bit;
            check->fresh_count++;
        }
        if (snapshot[i].fault_summary != 0U)
        {
            check->fault_joint_mask |= bit;
        }
    }

    check->required_motor_feedback_fresh =
        ((check->fresh_joint_mask & check->required_joint_mask) == check->required_joint_mask)
            ? RT_TRUE : RT_FALSE;
    check->required_motor_feedback_fault_free =
        ((check->fault_joint_mask & check->required_joint_mask) == 0U) ? RT_TRUE : RT_FALSE;

    check->ready =
        (check->logging_only_clear &&
         check->heartbeat_ok &&
         check->estop_input_confirmed &&
         check->estop_safe_now &&
         check->power_input_confirmed &&
         check->power_safe_now &&
         check->limits_confirmed &&
         check->limits_safe_now &&
         check->required_motor_feedback_fresh &&
         check->required_motor_feedback_fault_free)
            ? RT_TRUE : RT_FALSE;
}

static void ctrl_ros_safety_assessment_init(control_ros_safety_assessment_t *assessment)
{
    if (assessment == RT_NULL)
    {
        return;
    }

    rt_memset(assessment, 0, sizeof(*assessment));
    assessment->state = CONTROL_ROS_SAFETY_LOGGING_ONLY;
    assessment->decision = CONTROL_ROS_DECISION_REJECT;
    assessment->reason = CONTROL_ROS_REJECT_LOGGING_ONLY;
    assessment->heartbeat_age_ms = 0xFFFFFFFFUL;
    assessment->heartbeat_ok = RT_FALSE;
    assessment->joint_known = RT_FALSE;
    assessment->target_in_limit = RT_TRUE;
    assessment->rpm_in_limit = RT_TRUE;
    assessment->torque_in_limit = RT_TRUE;
    assessment->joint_calibrated = RT_FALSE;
}

static rt_bool_t ctrl_ros_command_is_calibration_telemetry(const control_ros_command_t *cmd)
{
    if (cmd == RT_NULL)
    {
        return RT_FALSE;
    }

    return (cmd->command == CONTROL_ROS_CMD_SET_ACTIVE_REPORT) ? RT_TRUE : RT_FALSE;
}

static control_ros_reject_reason_t ctrl_ros_first_reject_reason(const control_ros_safety_assessment_t *assessment)
{
    if (assessment == RT_NULL)
    {
        return CONTROL_ROS_REJECT_UNSUPPORTED_CMD;
    }

    if (!assessment->heartbeat_ok)
    {
        return CONTROL_ROS_REJECT_HEARTBEAT_TIMEOUT;
    }
    if (!assessment->joint_known)
    {
        return CONTROL_ROS_REJECT_UNKNOWN_JOINT;
    }
    if (!assessment->target_in_limit)
    {
        return CONTROL_ROS_REJECT_POSITION_LIMIT;
    }
    if (!assessment->rpm_in_limit)
    {
        return CONTROL_ROS_REJECT_SPEED_LIMIT;
    }
    if (!assessment->torque_in_limit)
    {
        return CONTROL_ROS_REJECT_TORQUE_LIMIT;
    }
    if (!assessment->joint_calibrated)
    {
        return CONTROL_ROS_REJECT_JOINT_UNCALIBRATED;
    }

    return CONTROL_ROS_REJECT_NONE;
}

static void ctrl_assess_ros_command_safety(const control_ros_command_t *cmd,
                                           control_ros_safety_assessment_t *assessment)
{
    control_ros_reject_reason_t first_reject;

    if ((cmd == RT_NULL) || (assessment == RT_NULL))
    {
        return;
    }

    ctrl_ros_safety_assessment_init(assessment);

    if (s_has_nanopi_heartbeat)
    {
        assessment->heartbeat_age_ms = ctrl_tick_delta_ms(rt_tick_get(), s_last_nanopi_heartbeat_tick);
        assessment->heartbeat_ok =
            (assessment->heartbeat_age_ms <= CONTROL_ROS_HEARTBEAT_TIMEOUT_MS) ? RT_TRUE : RT_FALSE;
    }

    assessment->joint_known =
        ctrl_ros_joint_limit(cmd->joint_id, &assessment->joint_min_01deg, &assessment->joint_max_01deg);
    if (assessment->joint_known)
    {
        assessment->joint_calibrated =
            ctrl_motor_joint_is_calibrated(ctrl_ros_joint_to_motor_joint(cmd->joint_id));
    }

    if (cmd->command == CONTROL_ROS_CMD_STOP)
    {
        if (!assessment->joint_known)
        {
            assessment->reason = CONTROL_ROS_REJECT_UNKNOWN_JOINT;
            assessment->state = CONTROL_ROS_SAFETY_LIMITED;
            assessment->decision = CONTROL_ROS_DECISION_REJECT;
            return;
        }

        assessment->reason = CONTROL_ROS_REJECT_NONE;
        assessment->state = CONTROL_ROS_SAFETY_READY;
        assessment->decision = CONTROL_ROS_DECISION_ACCEPT;
        return;
    }

    if (ctrl_ros_command_is_calibration_telemetry(cmd))
    {
        if (!assessment->heartbeat_ok)
        {
            assessment->reason = CONTROL_ROS_REJECT_HEARTBEAT_TIMEOUT;
            assessment->state = CONTROL_ROS_SAFETY_LIMITED;
            assessment->decision = CONTROL_ROS_DECISION_REJECT;
            return;
        }
        if (!assessment->joint_known)
        {
            assessment->reason = CONTROL_ROS_REJECT_UNKNOWN_JOINT;
            assessment->state = CONTROL_ROS_SAFETY_LIMITED;
            assessment->decision = CONTROL_ROS_DECISION_REJECT;
            return;
        }
#if CONTROL_CALIBRATION_ACTIVE_REPORT_ENABLE
        assessment->reason = CONTROL_ROS_REJECT_NONE;
        assessment->state = CONTROL_ROS_SAFETY_READY;
        assessment->decision = CONTROL_ROS_DECISION_ACCEPT;
#else
        assessment->reason = CONTROL_ROS_REJECT_UNSUPPORTED_CMD;
        assessment->state = CONTROL_ROS_SAFETY_LIMITED;
        assessment->decision = CONTROL_ROS_DECISION_REJECT;
#endif
        return;
    }

    if (cmd->command != CONTROL_ROS_CMD_SET_TARGET)
    {
        assessment->target_in_limit = RT_FALSE;
        assessment->reason = CONTROL_ROS_REJECT_UNSUPPORTED_CMD;
        assessment->state = CONTROL_ROS_SAFETY_LIMITED;
        assessment->decision = CONTROL_ROS_DECISION_REJECT;
        return;
    }

    if (!assessment->joint_known)
    {
        assessment->target_in_limit = RT_FALSE;
    }
    else if ((cmd->target_pos_01deg < assessment->joint_min_01deg) ||
             (cmd->target_pos_01deg > assessment->joint_max_01deg))
    {
        assessment->target_in_limit = RT_FALSE;
    }

    if ((cmd->target_vel_rpm > CONTROL_ROS_MAX_TARGET_RPM) ||
        (cmd->target_vel_rpm < -CONTROL_ROS_MAX_TARGET_RPM))
    {
        assessment->rpm_in_limit = RT_FALSE;
    }

    if ((cmd->target_torque_ma > CONTROL_ROS_MAX_TARGET_TORQUE_MA) ||
        (cmd->target_torque_ma < -CONTROL_ROS_MAX_TARGET_TORQUE_MA))
    {
        assessment->torque_in_limit = RT_FALSE;
    }

    first_reject = ctrl_ros_first_reject_reason(assessment);
    if (first_reject != CONTROL_ROS_REJECT_NONE)
    {
        assessment->reason = first_reject;
        assessment->state = CONTROL_ROS_SAFETY_LIMITED;
        assessment->decision = CONTROL_ROS_DECISION_REJECT;
        return;
    }

#if CONTROL_ROS_COMMAND_LOGGING_ONLY
    assessment->reason = CONTROL_ROS_REJECT_LOGGING_ONLY;
    assessment->state = CONTROL_ROS_SAFETY_LOGGING_ONLY;
    assessment->decision = CONTROL_ROS_DECISION_REJECT;
#else
    assessment->reason = CONTROL_ROS_REJECT_NONE;
    assessment->state = CONTROL_ROS_SAFETY_READY;
    assessment->decision = CONTROL_ROS_DECISION_ACCEPT;
#endif
}

#if CONTROL_ROS_COMMAND_LOGGING_ONLY
static void ctrl_log_ros_command_only(const struct rt_can_msg *msg, const control_ros_command_t *cmd)
{
    rt_uint8_t data[8] = {0};
    rt_int32_t target_mrad;
    control_ros_safety_assessment_t assessment;

    if ((msg == RT_NULL) || (cmd == RT_NULL))
    {
        return;
    }

    if (msg->len > 0U)
    {
        rt_memcpy(data, msg->data, (msg->len > 8U) ? 8U : msg->len);
    }
    target_mrad = ((rt_int32_t)cmd->target_pos_01deg * 1745L) / 1000L;
    ctrl_assess_ros_command_safety(cmd, &assessment);
    s_last_ros_status_detail_code = ctrl_ros_reject_reason_detail_code(assessment.reason);

    rt_kprintf("RX 320 dlc=%u data=%02X%02X%02X%02X%02X%02X%02X%02X\n",
               (unsigned int)msg->len,
               (unsigned int)data[0],
               (unsigned int)data[1],
               (unsigned int)data[2],
               (unsigned int)data[3],
               (unsigned int)data[4],
               (unsigned int)data[5],
               (unsigned int)data[6],
               (unsigned int)data[7]);
    rt_kprintf("cmd=0x%02X name=%s joint_id=%u deg_x10=%d target_mrad=%ld rpm=%d torque_ma=%d\n",
               (unsigned int)data[0],
               ctrl_ros_command_name(cmd->command),
               (unsigned int)cmd->joint_id,
               (int)cmd->target_pos_01deg,
               (long)target_mrad,
               (int)cmd->target_vel_rpm,
               (int)cmd->target_torque_ma);
    rt_kprintf("safety_state=%s decision=%s reason=%s\n",
               ctrl_ros_safety_state_name(assessment.state),
               ctrl_ros_decision_name(assessment.decision),
               ctrl_ros_reject_reason_name(assessment.reason));
    rt_kprintf("audit heartbeat_ok=%u heartbeat_age_ms=%lu heartbeat_timeout_ms=%u joint_known=%u limit_01deg=[%d,%d]\n",
               assessment.heartbeat_ok ? 1U : 0U,
               (unsigned long)assessment.heartbeat_age_ms,
               (unsigned int)CONTROL_ROS_HEARTBEAT_TIMEOUT_MS,
               assessment.joint_known ? 1U : 0U,
               (int)assessment.joint_min_01deg,
               (int)assessment.joint_max_01deg);
    rt_kprintf("audit target_in_limit=%u rpm_in_limit=%u torque_in_limit=%u joint_calibrated=%u max_rpm=%d max_torque_ma=%d\n",
               assessment.target_in_limit ? 1U : 0U,
               assessment.rpm_in_limit ? 1U : 0U,
               assessment.torque_in_limit ? 1U : 0U,
               assessment.joint_calibrated ? 1U : 0U,
               (int)CONTROL_ROS_MAX_TARGET_RPM,
               (int)CONTROL_ROS_MAX_TARGET_TORQUE_MA);
    rt_kprintf("final action=no_motor_output logging_only=%u\n",
               (unsigned int)CONTROL_ROS_COMMAND_LOGGING_ONLY);
}
#endif

static void ctrl_log_ros_command_assessment(const struct rt_can_msg *msg,
                                            const control_ros_command_t *cmd,
                                            const control_ros_safety_assessment_t *assessment,
                                            const char *final_action)
{
    rt_uint8_t data[8] = {0};
    rt_int32_t target_mrad;

    if ((msg == RT_NULL) || (cmd == RT_NULL) || (assessment == RT_NULL))
    {
        return;
    }

    if (msg->len > 0U)
    {
        rt_memcpy(data, msg->data, (msg->len > 8U) ? 8U : msg->len);
    }
    target_mrad = ((rt_int32_t)cmd->target_pos_01deg * 1745L) / 1000L;

    rt_kprintf("RX 320 dlc=%u data=%02X%02X%02X%02X%02X%02X%02X%02X\n",
               (unsigned int)msg->len,
               (unsigned int)data[0],
               (unsigned int)data[1],
               (unsigned int)data[2],
               (unsigned int)data[3],
               (unsigned int)data[4],
               (unsigned int)data[5],
               (unsigned int)data[6],
               (unsigned int)data[7]);
    rt_kprintf("cmd=0x%02X name=%s ros_joint_id=%u motor_joint=%u deg_x10=%d target_mrad=%ld rpm=%d torque_ma=%d\n",
               (unsigned int)data[0],
               ctrl_ros_command_name(cmd->command),
               (unsigned int)cmd->joint_id,
               (unsigned int)ctrl_ros_joint_to_motor_joint(cmd->joint_id),
               (int)cmd->target_pos_01deg,
               (long)target_mrad,
               (int)cmd->target_vel_rpm,
               (int)cmd->target_torque_ma);
    rt_kprintf("safety_state=%s decision=%s reason=%s\n",
               ctrl_ros_safety_state_name(assessment->state),
               ctrl_ros_decision_name(assessment->decision),
               ctrl_ros_reject_reason_name(assessment->reason));
    rt_kprintf("audit heartbeat_ok=%u heartbeat_age_ms=%lu heartbeat_timeout_ms=%u joint_known=%u limit_01deg=[%d,%d]\n",
               assessment->heartbeat_ok ? 1U : 0U,
               (unsigned long)assessment->heartbeat_age_ms,
               (unsigned int)CONTROL_ROS_HEARTBEAT_TIMEOUT_MS,
               assessment->joint_known ? 1U : 0U,
               (int)assessment->joint_min_01deg,
               (int)assessment->joint_max_01deg);
    rt_kprintf("audit target_in_limit=%u rpm_in_limit=%u torque_in_limit=%u joint_calibrated=%u max_rpm=%d max_torque_ma=%d bench_motion=%u\n",
               assessment->target_in_limit ? 1U : 0U,
               assessment->rpm_in_limit ? 1U : 0U,
               assessment->torque_in_limit ? 1U : 0U,
               assessment->joint_calibrated ? 1U : 0U,
               (int)CONTROL_ROS_MAX_TARGET_RPM,
               (int)CONTROL_ROS_MAX_TARGET_TORQUE_MA,
               (unsigned int)CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE);
    rt_kprintf("final action=%s logging_only=%u\n",
               (final_action != RT_NULL) ? final_action : "unknown",
               (unsigned int)CONTROL_ROS_COMMAND_LOGGING_ONLY);
}

static rt_bool_t ctrl_handle_nanopi_heartbeat(const struct rt_can_msg *msg)
{
    rt_uint8_t payload[8] = {0};

    if ((msg == RT_NULL) || (msg->ide != RT_CAN_STDID) ||
        (msg->id != CONTROL_CAN_ID_NANOPI_HEARTBEAT))
    {
        return RT_FALSE;
    }

    payload[0] = 0xA5U;
    payload[1] = (msg->len > 0U) ? msg->data[0] : 0U;
    payload[2] = CONTROL_MOTOR_JOINT_COUNT;
    payload[3] = 0U;
#if CONTROL_ROS_COMMAND_LOGGING_ONLY
    payload[4] = CONTROL_STATUS_SAFETY_LIMITED;
    payload[5] = CONTROL_STATUS_MODE_LOGGING_ONLY;
    payload[6] = s_last_ros_status_detail_code;
#else
    payload[4] = (s_last_ros_status_detail_code == CONTROL_STATUS_DETAIL_NONE) ?
                 CONTROL_STATUS_SAFETY_OK : CONTROL_STATUS_SAFETY_LIMITED;
    payload[5] = ((s_last_ros_status_detail_code == CONTROL_STATUS_DETAIL_NONE) &&
                  CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE) ?
                 CONTROL_STATUS_MODE_ARMED : CONTROL_STATUS_MODE_STANDBY;
    payload[6] = s_last_ros_status_detail_code;
#endif
    payload[7] = 0U;

    s_last_nanopi_heartbeat_tick = rt_tick_get();
    s_has_nanopi_heartbeat = RT_TRUE;
    (void)ctrl_can_send(CONTROL_CAN_ID_M33_STATUS, RT_CAN_STDID, payload, sizeof(payload));
    return RT_TRUE;
}

static void ctrl_handle_can_message(const struct rt_can_msg *msg)
{
    control_ros_command_t ros_cmd;

    if (ctrl_handle_nanopi_heartbeat(msg))
    {
        s_dbg_rx_heartbeat++;
        return;
    }

    s_dbg_rx_total++;
    s_dbg_last_rx_id = msg->id;
    s_dbg_last_rx_ide = msg->ide;
    s_dbg_last_rx_len = msg->len;
    rt_memset(s_dbg_last_rx_data, 0, sizeof(s_dbg_last_rx_data));
    if (msg->len > 0U)
    {
        rt_memcpy(s_dbg_last_rx_data, msg->data, (msg->len > 8U) ? 8U : msg->len);
    }
    if ((msg->ide == RT_CAN_STDID) && (msg->id == CONTROL_CAN_ID_ROS_COMMAND))
    {
        s_dbg_rx_ros_id++;
    }

    if (ctrl_parse_ros_command_can(msg, &ros_cmd))
    {
#if CONTROL_ROS_COMMAND_LOGGING_ONLY
        control_ros_safety_assessment_t assessment;
        rt_err_t ret = -RT_EINVAL;

        s_dbg_ros_parsed++;
        ctrl_assess_ros_command_safety(&ros_cmd, &assessment);
        s_last_ros_status_detail_code = ctrl_ros_reject_reason_detail_code(assessment.reason);
        rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
        s_last_ros_cmd = ros_cmd;
        rt_mutex_release(&s_data_lock);

        if (ctrl_ros_command_is_calibration_telemetry(&ros_cmd) &&
            (assessment.decision == CONTROL_ROS_DECISION_ACCEPT))
        {
            ret = ctrl_apply_ros_command(&ros_cmd);
            if (ret != RT_EOK)
            {
                s_last_ros_status_detail_code = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
            }
            else
            {
                s_dbg_ros_applied++;
            }
            ctrl_log_ros_command_assessment(msg,
                                            &ros_cmd,
                                            &assessment,
                                            (ret == RT_EOK) ?
                                                "apply_calibration_telemetry_only" :
                                                "apply_calibration_telemetry_failed");
            return;
        }

        ctrl_log_ros_command_only(msg, &ros_cmd);
        return;
#else
        control_ros_safety_assessment_t assessment;
        rt_err_t ret;

        s_dbg_ros_parsed++;
        ctrl_assess_ros_command_safety(&ros_cmd, &assessment);
        s_last_ros_status_detail_code = ctrl_ros_reject_reason_detail_code(assessment.reason);
        if (assessment.decision != CONTROL_ROS_DECISION_ACCEPT)
        {
            rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
            s_last_ros_cmd = ros_cmd;
            rt_mutex_release(&s_data_lock);
            ctrl_log_ros_command_assessment(msg, &ros_cmd, &assessment, "reject_no_motor_output");
            return;
        }

        ret = ctrl_apply_ros_command(&ros_cmd);
        if (ret != RT_EOK)
        {
            s_last_ros_status_detail_code = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
        }
        rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
        s_last_ros_cmd = ros_cmd;
        rt_mutex_release(&s_data_lock);
        s_dbg_ros_applied++;
        ctrl_log_ros_command_assessment(msg,
                                        &ros_cmd,
                                        &assessment,
                                        (ret == RT_EOK) ? "apply_motor_output" : "apply_failed");
        if (ret != RT_EOK)
        {
            rt_kprintf("[control] ros cmd direct apply failed, cmd=%u joint=%u ret=%d\n",
                       (unsigned int)ros_cmd.command,
                       (unsigned int)ros_cmd.joint_id,
                       ret);
        }
        return;
#endif
    }

    if (msg->ide == RT_CAN_EXTID)
    {
        ctrl_update_motor_probe_private(msg);
        ctrl_update_motor_param_private(msg);
        ctrl_update_motor_feedback_private(msg);
        return;
    }

    ctrl_update_motor_feedback_cansimple(msg);

    if (msg->id == CONTROL_CAN_ID_EMG_REPORT)
    {
        ctrl_update_emg_report(msg);
    }
    else if (msg->id == CONTROL_CAN_ID_HEART_REPORT)
    {
        ctrl_update_heart_report(msg);
    }
    else if (msg->id == CONTROL_CAN_ID_F103_SENSOR)
    {
        s_dbg_rx_f103_sensor++;
        ctrl_update_f103_sensor_report(msg);
    }
    else if (msg->id == CONTROL_CAN_ID_F103_HEALTH)
    {
        s_dbg_rx_f103_health++;
        ctrl_update_f103_health_report(msg);
    }
    else if (msg->id == CONTROL_CAN_ID_F103_ACK)
    {
        s_dbg_rx_f103_ack++;
        ctrl_update_f103_ack_report(msg);
    }
}

static void ctrl_poll_can_messages(void)
{
    struct rt_can_msg msg;
    rt_uint8_t drained = 0U;

#if CONTROL_CAN_USE_DIRECT_PDL
    while ((drained < CONTROL_CAN_RX_DRAIN_LIMIT) &&
           (ifx_can_direct_recv(&msg) == (rt_ssize_t)sizeof(msg)))
    {
        ctrl_handle_can_message(&msg);
        drained++;
    }
#else
    while ((drained < CONTROL_CAN_RX_DRAIN_LIMIT) &&
           (rt_device_read(s_can_dev, 0, &msg, sizeof(msg)) == sizeof(msg)))
    {
        ctrl_handle_can_message(&msg);
        drained++;
    }
#endif
}

#if !CONTROL_CAN_USE_DIRECT_PDL
static rt_err_t ctrl_can_rx_indicate(rt_device_t dev, rt_size_t size)
{
    RT_UNUSED(dev);
    RT_UNUSED(size);

    rt_sem_release(&s_can_rx_sem);
    return RT_EOK;
}
#endif

static void ctrl_can_rx_entry(void *parameter)
{
    RT_UNUSED(parameter);

    while (1)
    {
#if CONTROL_CAN_USE_DIRECT_PDL
        ctrl_poll_can_messages();
        rt_thread_mdelay(10);
#else
        rt_device_control(s_can_dev, IFX_CAN_CMD_POLL_RX, RT_NULL);
        (void)rt_sem_take(&s_can_rx_sem, rt_tick_from_millisecond(10));

        ctrl_poll_can_messages();
#endif
    }
}

static rt_err_t ctrl_apply_ros_command(const control_ros_command_t *cmd)
{
    rt_uint8_t motor_joint;

    if (cmd == RT_NULL)
    {
        return -RT_EINVAL;
    }

    motor_joint = ctrl_ros_joint_to_motor_joint(cmd->joint_id);

    switch (cmd->command)
    {
    case CONTROL_ROS_CMD_ENABLE:
        return -RT_EINVAL;

    case CONTROL_ROS_CMD_STOP:
        return control_motor_stop(motor_joint, cmd->clear_fault ? RT_TRUE : RT_FALSE);

    case CONTROL_ROS_CMD_SET_TARGET:
        return control_joint_motor_set_target(motor_joint,
                                              cmd->target_pos_01deg,
                                              cmd->target_vel_rpm,
                                              cmd->target_torque_ma,
                                              RT_TRUE);

    case CONTROL_ROS_CMD_SET_MODE:
        return -RT_EINVAL;

    case CONTROL_ROS_CMD_SET_ZERO:
        return -RT_EINVAL;

    case CONTROL_ROS_CMD_SET_ACTIVE_REPORT:
        return control_motor_set_active_report(motor_joint,
                                               cmd->active_report_enable ? RT_TRUE : RT_FALSE);

    default:
        return -RT_EINVAL;
    }
}

static void ctrl_ros_cmd_entry(void *parameter)
{
    control_ros_command_t cmd;
    rt_err_t ret;

    RT_UNUSED(parameter);

    while (1)
    {
        if (rt_mq_recv(&s_ros_cmd_mq, &cmd, sizeof(cmd), RT_WAITING_FOREVER) != RT_EOK)
        {
            continue;
        }

        ret = ctrl_apply_ros_command(&cmd);

        rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
        s_last_ros_cmd = cmd;
        rt_mutex_release(&s_data_lock);
        s_dbg_ros_applied++;

        if (ret != RT_EOK)
        {
            rt_kprintf("[control] ros cmd apply failed, cmd=%u joint=%u ret=%d\n",
                       (unsigned int)cmd.command,
                       (unsigned int)cmd.joint_id,
                       ret);
        }
    }
}

int control_layer_init(const char *can_name)
{
    rt_err_t result;
#if !CONTROL_CAN_USE_DIRECT_PDL
    rt_uint16_t open_flags;
#endif
    const char *dev_name = can_name;

    if (s_is_inited)
    {
        return RT_EOK;
    }

    if ((dev_name == RT_NULL) || (dev_name[0] == '\0'))
    {
        dev_name = CONTROL_CAN_DEV_DEFAULT;
    }

    rt_kprintf("[control] init step1 dev=%s\n", dev_name);

    s_can_dev = rt_device_find(dev_name);
    if (s_can_dev == RT_NULL)
    {
#if CONTROL_CAN_USE_DIRECT_PDL
        rt_kprintf("[control] can device %s not found, continue direct pdl\n", dev_name);
#else
        rt_kprintf("[control] can device %s not found\n", dev_name);
        return -RT_ERROR;
#endif
    }

    rt_kprintf("[control] init step2 device found\n");

    result = rt_sem_init(&s_can_rx_sem, "c_rx", 0, RT_IPC_FLAG_FIFO);
    if (result != RT_EOK)
    {
        return result;
    }

    rt_kprintf("[control] init step3 sem ok\n");

    result = rt_mutex_init(&s_data_lock, "c_lock", RT_IPC_FLAG_PRIO);
    if (result != RT_EOK)
    {
        rt_sem_detach(&s_can_rx_sem);
        return result;
    }

    rt_kprintf("[control] init step4 mutex ok\n");

    result = rt_mq_init(&s_ros_cmd_mq,
                        "c_ros",
                        s_ros_cmd_pool,
                        sizeof(control_ros_command_t),
                        sizeof(s_ros_cmd_pool),
                        RT_IPC_FLAG_FIFO);
    if (result != RT_EOK)
    {
        rt_mutex_detach(&s_data_lock);
        rt_sem_detach(&s_can_rx_sem);
        return result;
    }

    rt_kprintf("[control] init step5 mq ok\n");

#if CONTROL_CAN_USE_DIRECT_PDL
    rt_kprintf("[control] init step6 direct pdl can init\n");
    result = ifx_can_direct_init();
    if (result != RT_EOK)
    {
        rt_mq_detach(&s_ros_cmd_mq);
        rt_mutex_detach(&s_data_lock);
        rt_sem_detach(&s_can_rx_sem);
        s_can_dev = RT_NULL;
        return result;
    }

    rt_kprintf("[control] init step7 direct open ret=%d\n", result);
    rt_kprintf("[control] init step8 direct rx poll mode\n");
#else
    open_flags = (rt_uint16_t)(RT_DEVICE_FLAG_RDWR | RT_DEVICE_FLAG_INT_RX | RT_DEVICE_FLAG_INT_TX);
    rt_kprintf("[control] init step6 open can flags=0x%04X\n", open_flags);
    result = rt_device_open(s_can_dev, open_flags);
    if ((result != RT_EOK) && (result != -RT_EBUSY))
    {
        rt_mq_detach(&s_ros_cmd_mq);
        rt_mutex_detach(&s_data_lock);
        rt_sem_detach(&s_can_rx_sem);
        s_can_dev = RT_NULL;
        return result;
    }

    rt_kprintf("[control] init step7 open ret=%d\n", result);
    rt_device_set_rx_indicate(s_can_dev, ctrl_can_rx_indicate);
    rt_kprintf("[control] init step8 rx indicate ok\n");
#endif

    s_can_rx_thread = rt_thread_create("ctrl_can",
                                       ctrl_can_rx_entry,
                                       RT_NULL,
                                       CONTROL_CAN_THREAD_STACK_SIZE,
                                       CONTROL_CAN_THREAD_PRIORITY,
                                       CONTROL_CAN_THREAD_TICK);
    if (s_can_rx_thread == RT_NULL)
    {
        rt_device_close(s_can_dev);
        rt_mq_detach(&s_ros_cmd_mq);
        rt_mutex_detach(&s_data_lock);
        rt_sem_detach(&s_can_rx_sem);
        s_can_dev = RT_NULL;
        return -RT_ENOMEM;
    }

    rt_kprintf("[control] init step9 can thread created\n");

    s_ros_cmd_thread = rt_thread_create("ros_cmd",
                                        ctrl_ros_cmd_entry,
                                        RT_NULL,
                                        CONTROL_ROS_THREAD_STACK_SIZE,
                                        CONTROL_ROS_THREAD_PRIORITY,
                                        CONTROL_ROS_THREAD_TICK);
    if (s_ros_cmd_thread == RT_NULL)
    {
        rt_thread_delete(s_can_rx_thread);
        s_can_rx_thread = RT_NULL;
        rt_device_close(s_can_dev);
        rt_mq_detach(&s_ros_cmd_mq);
        rt_mutex_detach(&s_data_lock);
        rt_sem_detach(&s_can_rx_sem);
        s_can_dev = RT_NULL;
        return -RT_ENOMEM;
    }

    rt_kprintf("[control] init step10 ros thread created\n");

    s_motor_status_thread = rt_thread_create("m_status",
                                             ctrl_motor_status_entry,
                                             RT_NULL,
                                             CONTROL_MOTOR_STATUS_THREAD_STACK_SIZE,
                                             CONTROL_MOTOR_STATUS_THREAD_PRIORITY,
                                             CONTROL_ROS_THREAD_TICK);
    if (s_motor_status_thread == RT_NULL)
    {
        rt_thread_delete(s_ros_cmd_thread);
        s_ros_cmd_thread = RT_NULL;
        rt_thread_delete(s_can_rx_thread);
        s_can_rx_thread = RT_NULL;
        rt_device_close(s_can_dev);
        rt_mq_detach(&s_ros_cmd_mq);
        rt_mutex_detach(&s_data_lock);
        rt_sem_detach(&s_can_rx_sem);
        s_can_dev = RT_NULL;
        return -RT_ENOMEM;
    }

    rt_kprintf("[control] init step10b motor status thread created\n");

    s_is_inited = RT_TRUE;
    rt_thread_startup(s_can_rx_thread);
    rt_thread_startup(s_ros_cmd_thread);
    rt_thread_startup(s_motor_status_thread);

    rt_kprintf("[control] init step11 threads started\n");

    rt_kprintf("[control] init step12 ready no sensor cfg sent\n");

    rt_kprintf("[control] init done on %s, motor_count=%u, ros_cmd_can_id=0x%03X\n",
               dev_name,
               (unsigned int)CONTROL_MOTOR_JOINT_COUNT,
               (unsigned int)CONTROL_CAN_ID_ROS_COMMAND);
    return RT_EOK;
}

rt_err_t control_motor_enable(rt_uint8_t joint_id)
{
    rt_uint8_t motor_id;
    rt_uint8_t payload[8] = {0};
    rt_uint32_t ext_id;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
    {
        return -RT_EINVAL;
    }

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        return ctrl_cansimple_set_axis_state(motor_id, CANSIMPLE_AXIS_STATE_CLOSED_LOOP);
    }

    ext_id = ctrl_motor_private_ext_id(MOTOR_PRIVATE_TYPE_ENABLE,
                                       (rt_uint16_t)CONTROL_MOTOR_MASTER_ID,
                                       motor_id);
    return ctrl_can_send(ext_id, RT_CAN_EXTID, payload, sizeof(payload));
}

rt_err_t control_motor_stop(rt_uint8_t joint_id, rt_bool_t clear_fault)
{
    rt_uint8_t motor_id;
    rt_uint8_t payload[8] = {0};
    rt_uint32_t ext_id;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
    {
        return -RT_EINVAL;
    }

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        rt_err_t ret;

        if (clear_fault)
        {
            ret = ctrl_cansimple_clear_errors(motor_id);
            if (ret != RT_EOK)
            {
                return ret;
            }
            rt_thread_mdelay(1);
        }

        return ctrl_cansimple_set_axis_state(motor_id, CANSIMPLE_AXIS_STATE_IDLE);
    }

    if (clear_fault)
    {
        payload[0] = 1U;
    }

    ext_id = ctrl_motor_private_ext_id(MOTOR_PRIVATE_TYPE_STOP,
                                       (rt_uint16_t)CONTROL_MOTOR_MASTER_ID,
                                       motor_id);
    return ctrl_can_send(ext_id, RT_CAN_EXTID, payload, sizeof(payload));
}

rt_err_t control_motor_set_zero(rt_uint8_t joint_id)
{
    rt_uint8_t motor_id;
    rt_uint8_t payload[8] = {0};
    rt_uint32_t ext_id;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
    {
        return -RT_EINVAL;
    }

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        ctrl_float_to_le(0.0f, &payload[0]);
        return ctrl_cansimple_send(motor_id, CANSIMPLE_CMD_SET_ABSOLUTE_POS, payload, 4U);
    }

    payload[0] = 1U;

    ext_id = ctrl_motor_private_ext_id(MOTOR_PRIVATE_TYPE_SET_ZERO,
                                       (rt_uint16_t)CONTROL_MOTOR_MASTER_ID,
                                       motor_id);
    return ctrl_can_send(ext_id, RT_CAN_EXTID, payload, sizeof(payload));
}

rt_err_t control_motor_set_run_mode(rt_uint8_t joint_id, control_motor_run_mode_t mode)
{
    rt_uint8_t motor_id;
    rt_uint8_t payload[8] = {0};
    rt_uint32_t ext_id;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
    {
        return -RT_EINVAL;
    }

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        rt_uint32_t control_mode = CANSIMPLE_CONTROL_MODE_POSITION;
        rt_uint32_t input_mode = CANSIMPLE_INPUT_MODE_PASSTHROUGH;

        if (mode == CONTROL_MOTOR_RUN_MODE_SPEED)
        {
            control_mode = CANSIMPLE_CONTROL_MODE_VELOCITY;
            input_mode = CANSIMPLE_INPUT_MODE_PASSTHROUGH;
        }
        else if ((mode == CONTROL_MOTOR_RUN_MODE_CURRENT) || (mode == CONTROL_MOTOR_RUN_MODE_MIT))
        {
            control_mode = CANSIMPLE_CONTROL_MODE_TORQUE;
            input_mode = CANSIMPLE_INPUT_MODE_PASSTHROUGH;
        }

        return ctrl_cansimple_set_controller_mode(motor_id, control_mode, input_mode);
    }

    payload[0] = (rt_uint8_t)(MOTOR_PARAM_INDEX_RUN_MODE & 0xFFU);
    payload[1] = (rt_uint8_t)((MOTOR_PARAM_INDEX_RUN_MODE >> 8) & 0xFFU);
    payload[4] = (rt_uint8_t)mode;

    ext_id = ctrl_motor_private_ext_id(MOTOR_PRIVATE_TYPE_PARAM_WRITE,
                                       (rt_uint16_t)CONTROL_MOTOR_MASTER_ID,
                                       motor_id);
    return ctrl_can_send(ext_id, RT_CAN_EXTID, payload, sizeof(payload));
}

rt_err_t control_motor_private_control(rt_uint8_t joint_id,
                                       float target_pos_rad,
                                       float target_vel_rad_s,
                                       float kp,
                                       float kd,
                                       float target_torque_nm)
{
    rt_uint8_t motor_id;
    rt_uint8_t payload[8];
    rt_uint16_t pos_u;
    rt_uint16_t vel_u;
    rt_uint16_t kp_u;
    rt_uint16_t kd_u;
    rt_uint16_t tor_u;
    rt_uint32_t ext_id;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
    {
        return -RT_EINVAL;
    }

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        rt_err_t ret;

        ret = control_motor_enable(joint_id);
        if (ret != RT_EOK)
        {
            return ret;
        }

        rt_thread_mdelay(1);
        return ctrl_cansimple_mit_control(motor_id,
                                          target_pos_rad,
                                          target_vel_rad_s,
                                          kp,
                                          kd,
                                          target_torque_nm);
    }

    pos_u = (rt_uint16_t)ctrl_float_to_uint(target_pos_rad,
                                            CONTROL_MOTOR_P_MIN_RAD,
                                            CONTROL_MOTOR_P_MAX_RAD,
                                            16);
    vel_u = (rt_uint16_t)ctrl_float_to_uint(target_vel_rad_s,
                                            CONTROL_MOTOR_V_MIN_RAD_S,
                                            CONTROL_MOTOR_V_MAX_RAD_S,
                                            16);
    kp_u = (rt_uint16_t)ctrl_float_to_uint(kp,
                                           CONTROL_MOTOR_KP_MIN,
                                           CONTROL_MOTOR_KP_MAX,
                                           16);
    kd_u = (rt_uint16_t)ctrl_float_to_uint(kd,
                                           CONTROL_MOTOR_KD_MIN,
                                           CONTROL_MOTOR_KD_MAX,
                                           16);
    tor_u = (rt_uint16_t)ctrl_float_to_uint(target_torque_nm,
                                            CONTROL_MOTOR_T_MIN_NM,
                                            CONTROL_MOTOR_T_MAX_NM,
                                            16);

    ctrl_u16_to_be(pos_u, &payload[0]);
    ctrl_u16_to_be(vel_u, &payload[2]);
    ctrl_u16_to_be(kp_u, &payload[4]);
    ctrl_u16_to_be(kd_u, &payload[6]);

    ext_id = ctrl_motor_private_ext_id(MOTOR_PRIVATE_TYPE_CTRL, tor_u, motor_id);
    return ctrl_can_send(ext_id, RT_CAN_EXTID, payload, sizeof(payload));
}

rt_err_t control_motor_set_active_report(rt_uint8_t joint_id, rt_bool_t enable)
{
    rt_uint8_t motor_id;
    rt_uint8_t payload[8] = {1, 2, 3, 4, 5, 6, 0, 0};
    rt_uint32_t ext_id;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
    {
        return -RT_EINVAL;
    }

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        return RT_EOK;
    }

    payload[6] = enable ? 1U : 0U;

    ext_id = ctrl_motor_private_ext_id(MOTOR_PRIVATE_TYPE_ACTIVE_REPORT,
                                       (rt_uint16_t)CONTROL_MOTOR_MASTER_ID,
                                       motor_id);
    return ctrl_can_send(ext_id, RT_CAN_EXTID, payload, sizeof(payload));
}

rt_err_t control_get_motor_feedback(rt_uint8_t joint_id, control_motor_feedback_t *out)
{
    int idx;
    rt_uint8_t motor_id;

    if ((out == RT_NULL) || (!s_is_inited))
    {
        return -RT_EINVAL;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
    {
        return -RT_EINVAL;
    }

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        idx = ctrl_motor_index_by_cansimple_node(motor_id);
    }
    else
    {
        idx = ctrl_motor_index_by_motor_id(motor_id);
    }
    if (idx < 0)
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    *out = s_motor_feedback[idx];
    rt_mutex_release(&s_data_lock);

    return RT_EOK;
}

rt_err_t control_motor_probe_id(rt_uint8_t motor_id)
{
    rt_uint8_t payload[8] = {0};
    rt_uint32_t ext_id;
    rt_err_t ret;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    s_last_motor_probe.valid = RT_FALSE;
    s_motor_probe_expected_id = motor_id;
    s_motor_probe_pending = RT_TRUE;
    rt_mutex_release(&s_data_lock);

    ext_id = ctrl_motor_private_ext_id(MOTOR_PRIVATE_TYPE_GET_ID,
                                       (rt_uint16_t)CONTROL_MOTOR_MASTER_ID,
                                       motor_id);
    ret = ctrl_can_send(ext_id, RT_CAN_EXTID, payload, sizeof(payload));
    if (ret != RT_EOK)
    {
        rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
        s_motor_probe_pending = RT_FALSE;
        rt_mutex_release(&s_data_lock);
    }

    return ret;
}

rt_err_t control_get_last_motor_probe(control_motor_probe_report_t *out)
{
    if ((out == RT_NULL) || (!s_is_inited))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    *out = s_last_motor_probe;
    rt_mutex_release(&s_data_lock);
    return RT_EOK;
}

rt_err_t control_motor_read_parameter(rt_uint8_t joint_id, rt_uint16_t index)
{
    rt_uint8_t motor_id;
    rt_uint8_t payload[8] = {0};
    rt_uint32_t ext_id;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
    {
        return -RT_EINVAL;
    }

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        return -RT_ENOSYS;
    }

    payload[0] = (rt_uint8_t)(index & 0xFFU);
    payload[1] = (rt_uint8_t)((index >> 8) & 0xFFU);
    ext_id = ctrl_motor_private_ext_id(MOTOR_PRIVATE_TYPE_PARAM_READ,
                                       (rt_uint16_t)CONTROL_MOTOR_MASTER_ID,
                                       motor_id);
    return ctrl_can_send(ext_id, RT_CAN_EXTID, payload, sizeof(payload));
}

rt_err_t control_motor_write_parameter(rt_uint8_t joint_id, rt_uint16_t index, float value, rt_bool_t mode_value_is_u8)
{
    rt_uint8_t motor_id;
    rt_uint8_t payload[8] = {0};
    rt_uint32_t ext_id;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
    {
        return -RT_EINVAL;
    }

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        return -RT_ENOSYS;
    }

    payload[0] = (rt_uint8_t)(index & 0xFFU);
    payload[1] = (rt_uint8_t)((index >> 8) & 0xFFU);
    if (mode_value_is_u8)
    {
        payload[4] = (rt_uint8_t)value;
    }
    else
    {
        rt_memcpy(&payload[4], &value, sizeof(float));
    }

    ext_id = ctrl_motor_private_ext_id(MOTOR_PRIVATE_TYPE_PARAM_WRITE,
                                       (rt_uint16_t)CONTROL_MOTOR_MASTER_ID,
                                       motor_id);
    return ctrl_can_send(ext_id, RT_CAN_EXTID, payload, sizeof(payload));
}

rt_err_t control_get_last_motor_param(control_motor_param_report_t *out)
{
    if ((out == RT_NULL) || (!s_is_inited))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    *out = s_last_motor_param;
    rt_mutex_release(&s_data_lock);
    return RT_EOK;
}

rt_err_t control_motor_cansimple_set_input_pos(rt_uint8_t joint_id,
                                               float pos_rad,
                                               float vel_ff_rad_s,
                                               float torque_ff_nm)
{
    rt_uint8_t motor_id;
    rt_uint8_t payload[8] = {0};
    float pos_rev;
    rt_int16_t vel_ff;
    rt_int16_t torque_ff;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id) ||
        (ctrl_motor_protocol_by_joint(joint_id) != CONTROL_MOTOR_PROTOCOL_CANSIMPLE))
    {
        return -RT_EINVAL;
    }

    pos_rev = ctrl_joint_to_motor_position(joint_id, pos_rad) * CONTROL_CANSIMPLE_POS_REV_PER_RAD;
    vel_ff = ctrl_float_to_scaled_i16(ctrl_joint_to_motor_velocity(joint_id, vel_ff_rad_s) *
                                      CONTROL_CANSIMPLE_VEL_REV_PER_RAD_S,
                                      CONTROL_CANSIMPLE_VEL_FF_SCALE);
    torque_ff = ctrl_float_to_scaled_i16(torque_ff_nm, CONTROL_CANSIMPLE_TORQUE_FF_SCALE);

    ctrl_float_to_le(pos_rev, &payload[0]);
    ctrl_i16_to_le(vel_ff, &payload[4]);
    ctrl_i16_to_le(torque_ff, &payload[6]);

    return ctrl_cansimple_send(motor_id, CANSIMPLE_CMD_SET_INPUT_POS, payload, sizeof(payload));
}

rt_err_t control_motor_cansimple_set_input_vel(rt_uint8_t joint_id, float vel_rad_s, float torque_ff_nm)
{
    rt_uint8_t motor_id;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id) ||
        (ctrl_motor_protocol_by_joint(joint_id) != CONTROL_MOTOR_PROTOCOL_CANSIMPLE))
    {
        return -RT_EINVAL;
    }

    return ctrl_cansimple_set_input_vel_node(motor_id,
                                             ctrl_joint_to_motor_velocity(joint_id, vel_rad_s),
                                             torque_ff_nm);
}

rt_err_t control_motor_cansimple_set_input_torque(rt_uint8_t joint_id, float torque_nm)
{
    rt_uint8_t motor_id;
    rt_uint8_t payload[8] = {0};

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    motor_id = ctrl_motor_id_by_joint(joint_id);
    if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id) ||
        (ctrl_motor_protocol_by_joint(joint_id) != CONTROL_MOTOR_PROTOCOL_CANSIMPLE))
    {
        return -RT_EINVAL;
    }

    ctrl_float_to_le(torque_nm, &payload[0]);
    return ctrl_cansimple_send(motor_id, CANSIMPLE_CMD_SET_INPUT_TORQUE, payload, 4U);
}

rt_err_t control_motor_speed_control(rt_uint8_t joint_id, float speed_rad_s, float limit_cur)
{
    rt_err_t ret;

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        rt_uint8_t motor_id = ctrl_motor_id_by_joint(joint_id);
        rt_uint8_t payload[8] = {0};
        float vel_limit = speed_rad_s;

        if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
        {
            return -RT_EINVAL;
        }

        vel_limit = ctrl_joint_to_motor_velocity(joint_id, vel_limit);
        if (vel_limit < 0.0f)
        {
            vel_limit = -vel_limit;
        }

        RT_UNUSED(payload);
        RT_UNUSED(vel_limit);
        return ctrl_cansimple_velocity_start_node(motor_id,
                                                  ctrl_joint_to_motor_velocity(joint_id, speed_rad_s),
                                                  limit_cur,
                                                  RT_TRUE);
    }

#if CONTROL_MOTOR_PRIVATE_SPEED_USE_MIT
    ret = control_motor_enable(joint_id);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_thread_mdelay(2);
    return control_motor_private_control(joint_id,
                                         0.0f,
                                         speed_rad_s,
                                         CONTROL_MOTOR_PRIVATE_SPEED_MIT_KP,
                                         CONTROL_MOTOR_PRIVATE_SPEED_MIT_KD,
                                         CONTROL_MOTOR_PRIVATE_SPEED_MIT_TORQUE);
#else
    ret = control_motor_set_run_mode(joint_id, CONTROL_MOTOR_RUN_MODE_SPEED);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_thread_mdelay(2);
    ret = control_motor_enable(joint_id);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_thread_mdelay(2);
    ret = control_motor_write_parameter(joint_id, MOTOR_PARAM_INDEX_LIMIT_CUR, limit_cur, RT_FALSE);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_thread_mdelay(1);
    ret = control_motor_write_parameter(joint_id,
                                        MOTOR_PARAM_INDEX_SPEED_ACC,
                                        CONTROL_MOTOR_DEFAULT_SPEED_ACC_RAD_S2,
                                        RT_FALSE);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_thread_mdelay(1);
    return control_motor_write_parameter(joint_id, MOTOR_PARAM_INDEX_SPD_REF, speed_rad_s, RT_FALSE);
#endif
}

rt_err_t control_motor_position_control(rt_uint8_t joint_id, float pos_rad, float limit_spd, rt_bool_t csp_mode)
{
    rt_err_t ret;
    control_motor_run_mode_t mode = csp_mode ? CONTROL_MOTOR_RUN_MODE_CSP : CONTROL_MOTOR_RUN_MODE_PP;
    float motor_pos_rad;
    float motor_limit_spd;

    if (!ctrl_motor_joint_is_calibrated(joint_id))
    {
        rt_kprintf("[control] reject position control: joint=%u uncalibrated\n",
                   (unsigned int)joint_id);
        return -RT_EINVAL;
    }

    motor_pos_rad = ctrl_joint_to_motor_position(joint_id, pos_rad);
    motor_limit_spd = ctrl_joint_to_motor_velocity(joint_id, limit_spd);
    if (motor_limit_spd < 0.0f)
    {
        motor_limit_spd = -motor_limit_spd;
    }

    if (ctrl_motor_protocol_by_joint(joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
    {
        rt_uint8_t motor_id = ctrl_motor_id_by_joint(joint_id);
        rt_uint8_t payload[8] = {0};

        if (ctrl_motor_id_invalid_for_joint(joint_id, motor_id))
        {
            return -RT_EINVAL;
        }

        ret = ctrl_cansimple_set_controller_mode(motor_id,
                                                 CANSIMPLE_CONTROL_MODE_POSITION,
                                                 CANSIMPLE_INPUT_MODE_PASSTHROUGH);
        if (ret != RT_EOK)
        {
            return ret;
        }

        rt_thread_mdelay(1);
        ctrl_float_to_le(motor_limit_spd * CONTROL_CANSIMPLE_VEL_REV_PER_RAD_S,
                         &payload[0]);
        ctrl_float_to_le(CONTROL_CANSIMPLE_POSITION_LIMIT_CURRENT, &payload[4]);
        ret = ctrl_cansimple_send(motor_id, CANSIMPLE_CMD_SET_LIMITS, payload, sizeof(payload));
        if (ret != RT_EOK)
        {
            return ret;
        }

        rt_thread_mdelay(1);
        ret = control_motor_enable(joint_id);
        if (ret != RT_EOK)
        {
            return ret;
        }

        rt_thread_mdelay(1);
        return control_motor_cansimple_set_input_pos(joint_id, pos_rad, 0.0f, 0.0f);
    }

    ret = control_motor_set_run_mode(joint_id, mode);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_thread_mdelay(2);
    ret = control_motor_enable(joint_id);
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_thread_mdelay(2);
    if (csp_mode)
    {
        ret = control_motor_write_parameter(joint_id, MOTOR_PARAM_INDEX_LIMIT_SPD, motor_limit_spd, RT_FALSE);
        if (ret != RT_EOK)
        {
            return ret;
        }
    }
    else
    {
        ret = control_motor_write_parameter(joint_id, MOTOR_PARAM_INDEX_PP_VEL_MAX, motor_limit_spd, RT_FALSE);
        if (ret != RT_EOK)
        {
            return ret;
        }

        rt_thread_mdelay(1);
        ret = control_motor_write_parameter(joint_id,
                                            MOTOR_PARAM_INDEX_PP_ACC_SET,
                                            CONTROL_MOTOR_DEFAULT_POS_ACC_RAD_S2,
                                            RT_FALSE);
        if (ret != RT_EOK)
        {
            return ret;
        }
    }

    rt_thread_mdelay(1);
    return control_motor_write_parameter(joint_id, MOTOR_PARAM_INDEX_LOC_REF, motor_pos_rad, RT_FALSE);
}

static void ctrl_speed_hold_entry(void *parameter)
{
    control_speed_hold_ctx_t *ctx = (control_speed_hold_ctx_t *)parameter;
    rt_uint32_t elapsed_ms = 0U;
    rt_err_t ret;

    ret = control_motor_speed_control(ctx->joint_id, ctx->speed_rad_s, ctx->limit_cur);
    if (ret != RT_EOK)
    {
        rt_kprintf("[control] speed_hold init failed ret=%d\n", ret);
        goto done;
    }

    while (!ctx->stop_requested && (elapsed_ms < ctx->duration_ms))
    {
        rt_thread_mdelay(ctx->period_ms);
        elapsed_ms += ctx->period_ms;

        if (ctx->stop_requested)
        {
            break;
        }

        if (ctrl_motor_protocol_by_joint(ctx->joint_id) == CONTROL_MOTOR_PROTOCOL_CANSIMPLE)
        {
            ret = control_motor_cansimple_set_input_vel(ctx->joint_id, ctx->speed_rad_s, 0.0f);
        }
#if CONTROL_MOTOR_PRIVATE_SPEED_USE_MIT
        else
        {
            ret = control_motor_private_control(ctx->joint_id,
                                                0.0f,
                                                ctx->speed_rad_s,
                                                CONTROL_MOTOR_PRIVATE_SPEED_MIT_KP,
                                                CONTROL_MOTOR_PRIVATE_SPEED_MIT_KD,
                                                CONTROL_MOTOR_PRIVATE_SPEED_MIT_TORQUE);
        }
#else
        else
        {
            ret = control_motor_write_parameter(ctx->joint_id,
                                                MOTOR_PARAM_INDEX_SPD_REF,
                                                ctx->speed_rad_s,
                                                RT_FALSE);
        }
#endif
        if (ret != RT_EOK)
        {
            rt_kprintf("[control] speed_hold refresh failed ret=%d elapsed=%u\n",
                       ret,
                       (unsigned int)elapsed_ms);
            break;
        }
    }

done:
    (void)control_motor_stop(ctx->joint_id, RT_FALSE);
    rt_kprintf("[control] speed_hold done joint=%u elapsed=%u\n",
               (unsigned int)ctx->joint_id,
               (unsigned int)elapsed_ms);
    s_speed_hold_thread = RT_NULL;
}

rt_err_t control_get_last_ros_command(control_ros_command_t *out)
{
    if ((out == RT_NULL) || (!s_is_inited))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    *out = s_last_ros_cmd;
    rt_mutex_release(&s_data_lock);

    return RT_EOK;
}

rt_err_t control_joint_motor_set_target(rt_uint8_t joint_id,
                                        rt_int16_t target_pos_01deg,
                                        rt_int16_t target_vel_rpm,
                                        rt_int16_t target_torque_ma,
                                        rt_bool_t enable)
{
    float pos_rad;
    float limit_spd_rad_s;

    if (!enable)
    {
        return control_motor_stop(joint_id, RT_FALSE);
    }

    pos_rad = ((float)target_pos_01deg) * 0.1f * RT_PI / 180.0f;
    limit_spd_rad_s = ((float)target_vel_rpm) * 2.0f * RT_PI / 60.0f;
    if (limit_spd_rad_s < 0.0f)
    {
        limit_spd_rad_s = -limit_spd_rad_s;
    }
    if (limit_spd_rad_s <= 0.0f)
    {
        limit_spd_rad_s = 0.1f;
    }

    if (!ctrl_motor_joint_is_calibrated(joint_id))
    {
        rt_kprintf("[control] reject joint target: joint=%u uncalibrated pos_01deg=%d rpm=%d\n",
                   (unsigned int)joint_id,
                   (int)target_pos_01deg,
                   (int)target_vel_rpm);
        return -RT_EINVAL;
    }

    return control_motor_position_control(joint_id, pos_rad, limit_spd_rad_s, RT_TRUE);
}

rt_err_t control_joint_motor_stop(rt_uint8_t joint_id)
{
    return control_motor_stop(joint_id, RT_FALSE);
}

rt_err_t control_sensor_report_enable(rt_bool_t enable, rt_uint16_t period_ms)
{
    rt_uint8_t payload[8] = {0};
    rt_uint16_t rate_hz;
    rt_err_t ret;

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

    if (period_ms == 0U)
    {
        period_ms = CONTROL_SENSOR_DEFAULT_PERIOD_MS;
    }

    rate_hz = (rt_uint16_t)(1000U / period_ms);
    if (rate_hz == 0U)
    {
        rate_hz = 1U;
    }

    payload[0] = CONTROL_F103_CMD_SET_RATE;
    payload[1] = s_tx_seq++;
    payload[2] = CONTROL_F103_RATE_TARGET_CAN_TX;
    payload[3] = (rt_uint8_t)(rate_hz & 0xFFU);
    payload[4] = (rt_uint8_t)((rate_hz >> 8) & 0xFFU);
    ret = ctrl_can_send(CONTROL_CAN_ID_F103_CTRL, RT_CAN_STDID, payload, sizeof(payload));
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_memset(payload, 0, sizeof(payload));
    payload[0] = enable ? CONTROL_F103_CMD_START_STREAM : CONTROL_F103_CMD_STOP_STREAM;
    payload[1] = s_tx_seq++;
    ret = ctrl_can_send(CONTROL_CAN_ID_F103_CTRL, RT_CAN_STDID, payload, sizeof(payload));
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_memset(payload, 0, sizeof(payload));
    payload[0] = CONTROL_SENSOR_CMD_ENABLE_REPORT;
    payload[1] = enable ? 1U : 0U;
    payload[2] = (rt_uint8_t)(period_ms & 0xFFU);
    payload[3] = (rt_uint8_t)((period_ms >> 8) & 0xFFU);
    payload[7] = s_tx_seq++;

    return ctrl_can_send(CONTROL_CAN_ID_SENSOR_CTRL, RT_CAN_STDID, payload, sizeof(payload));
}

rt_err_t control_get_emg_report(control_emg_report_t *out)
{
    if ((out == RT_NULL) || (!s_is_inited))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    *out = s_emg_report;
    rt_mutex_release(&s_data_lock);

    return RT_EOK;
}

rt_err_t control_get_heart_report(control_heart_report_t *out)
{
    if ((out == RT_NULL) || (!s_is_inited))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    *out = s_heart_report;
    rt_mutex_release(&s_data_lock);

    return RT_EOK;
}

rt_err_t control_get_sensor_node_sample(control_sensor_node_sample_t *out)
{
    if ((out == RT_NULL) || (!s_is_inited))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    *out = s_sensor_node_sample;
    rt_mutex_release(&s_data_lock);

    return RT_EOK;
}

#ifdef RT_USING_FINSH
#include <finsh.h>

static int cmd_motor_fb(int argc, char **argv);

static int cmd_control_init(int argc, char **argv)
{
    const char *name = CONTROL_CAN_DEV_DEFAULT;

    if (argc >= 2)
    {
        name = argv[1];
    }

    rt_kprintf("control_init ret=%d\n", control_layer_init(name));
    return 0;
}
MSH_CMD_EXPORT(cmd_control_init, init control layer: control_init [can_dev]);

static int cmd_motor_en(int argc, char **argv)
{
    if (argc < 2)
    {
        rt_kprintf("usage: motor_en <joint(1~%u)>\n", (unsigned int)CONTROL_MOTOR_JOINT_COUNT);
        return -1;
    }

    rt_kprintf("motor_en ret=%d\n", control_motor_enable((rt_uint8_t)atoi(argv[1])));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_en, enable motor by joint id);

static int cmd_motor_stop(int argc, char **argv)
{
    rt_uint8_t clear = 0;

    if (argc < 2)
    {
        rt_kprintf("usage: motor_stop <joint(1~%u)> [clear_fault(0|1)]\n",
                   (unsigned int)CONTROL_MOTOR_JOINT_COUNT);
        return -1;
    }

    if (argc >= 3)
    {
        clear = (rt_uint8_t)atoi(argv[2]);
    }

    rt_kprintf("motor_stop ret=%d\n",
               control_motor_stop((rt_uint8_t)atoi(argv[1]), clear ? RT_TRUE : RT_FALSE));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_stop, stop motor by joint id);

static int cmd_motor_ctrl(int argc, char **argv)
{
    rt_uint8_t joint;
    float p;
    float v;
    float kp;
    float kd;
    float t;

    if (argc < 7)
    {
        rt_kprintf("usage: motor_ctrl <joint> <pos_rad> <vel_rad_s> <kp> <kd> <torque_nm>\n");
        return -1;
    }

    joint = (rt_uint8_t)atoi(argv[1]);
    p = (float)atof(argv[2]);
    v = (float)atof(argv[3]);
    kp = (float)atof(argv[4]);
    kd = (float)atof(argv[5]);
    t = (float)atof(argv[6]);

    rt_kprintf("motor_ctrl ret=%d\n", control_motor_private_control(joint, p, v, kp, kd, t));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_ctrl, private protocol motor control frame);

static int cmd_motor_mode(int argc, char **argv)
{
    if (argc < 3)
    {
        rt_kprintf("usage: motor_mode <joint(1~%u)> <mode(0|1|2|3|5)>\n",
                   (unsigned int)CONTROL_MOTOR_JOINT_COUNT);
        return -1;
    }

    rt_kprintf("motor_mode ret=%d\n",
               control_motor_set_run_mode((rt_uint8_t)atoi(argv[1]),
                                          (control_motor_run_mode_t)atoi(argv[2])));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_mode, set motor run mode by private protocol);

static int cmd_motor_probe(int argc, char **argv)
{
    long motor_id = CONTROL_MOTOR_JOINT1_ID;

    if (argc >= 2)
    {
        motor_id = strtol(argv[1], RT_NULL, 0);
    }

    rt_kprintf("motor_probe ret=%d id=0x%02lX\n",
               control_motor_probe_id((rt_uint8_t)motor_id),
               motor_id & 0xFF);
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_probe, probe raw motor id by private get-id frame default joint1);

static int cmd_motor_read(int argc, char **argv)
{
    long index;

    if (argc < 3)
    {
        rt_kprintf("usage: motor_read <joint> <index_hex>\n");
        return -1;
    }

    index = strtol(argv[2], RT_NULL, 0);
    rt_kprintf("motor_read ret=%d\n",
               control_motor_read_parameter((rt_uint8_t)atoi(argv[1]), (rt_uint16_t)index));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_read, read motor single parameter by private protocol);

static int cmd_motor_write(int argc, char **argv)
{
    long index;
    float value;
    rt_bool_t is_mode;

    if (argc < 4)
    {
        rt_kprintf("usage: motor_write <joint> <index_hex> <value>\n");
        return -1;
    }

    index = strtol(argv[2], RT_NULL, 0);
    value = (float)atof(argv[3]);
    is_mode = (((rt_uint16_t)index) == MOTOR_PARAM_INDEX_RUN_MODE) ? RT_TRUE : RT_FALSE;
    rt_kprintf("motor_write ret=%d\n",
               control_motor_write_parameter((rt_uint8_t)atoi(argv[1]), (rt_uint16_t)index, value, is_mode));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_write, write motor single parameter by private protocol);

static int cmd_motor_speed(int argc, char **argv)
{
    if (argc < 4)
    {
        rt_kprintf("usage: motor_speed <joint> <speed_rad_s> <limit_cur>\n");
        return -1;
    }

    rt_kprintf("motor_speed ret=%d\n",
               control_motor_speed_control((rt_uint8_t)atoi(argv[1]),
                                           (float)atof(argv[2]),
                                           (float)atof(argv[3])));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_speed, speed mode control by private protocol);

static int cmd_motor_torque(int argc, char **argv)
{
    rt_uint8_t joint;
    rt_err_t ret;

    if (argc < 3)
    {
        rt_kprintf("usage: motor_torque <joint> <torque_nm>\n");
        return -1;
    }

    joint = (rt_uint8_t)atoi(argv[1]);
    ret = control_motor_set_run_mode(joint, CONTROL_MOTOR_RUN_MODE_CURRENT);
    if (ret == RT_EOK)
    {
        rt_thread_mdelay(1);
        ret = control_motor_enable(joint);
    }
    if (ret == RT_EOK)
    {
        rt_thread_mdelay(1);
        ret = control_motor_cansimple_set_input_torque(joint, (float)atof(argv[2]));
    }

    rt_kprintf("motor_torque ret=%d\n", ret);
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_torque, CANSimple torque control: motor_torque <joint> <torque_nm>);

static int cmd_motor_speed_hold(int argc, char **argv)
{
    rt_uint32_t duration_ms = 1000U;
    rt_uint32_t period_ms = 20U;

    if (argc < 4)
    {
        rt_kprintf("usage: motor_speed_hold <joint> <speed_rad_s> <limit_cur> [duration_ms] [period_ms]\n");
        return -1;
    }

    if (s_speed_hold_thread != RT_NULL)
    {
        rt_kprintf("motor_speed_hold already running, use motor_hold_stop first\n");
        return -1;
    }

    if (argc >= 5)
    {
        duration_ms = (rt_uint32_t)strtoul(argv[4], RT_NULL, 0);
    }
    if (argc >= 6)
    {
        period_ms = (rt_uint32_t)strtoul(argv[5], RT_NULL, 0);
    }

    if (duration_ms == 0U)
    {
        duration_ms = 1000U;
    }
    if (duration_ms > 10000U)
    {
        duration_ms = 10000U;
    }
    if (period_ms < 5U)
    {
        period_ms = 5U;
    }
    if (period_ms > 200U)
    {
        period_ms = 200U;
    }

    s_speed_hold_ctx.joint_id = (rt_uint8_t)atoi(argv[1]);
    s_speed_hold_ctx.speed_rad_s = (float)atof(argv[2]);
    s_speed_hold_ctx.limit_cur = (float)atof(argv[3]);
    s_speed_hold_ctx.duration_ms = duration_ms;
    s_speed_hold_ctx.period_ms = period_ms;
    s_speed_hold_ctx.stop_requested = RT_FALSE;

    s_speed_hold_thread = rt_thread_create("m_spd_hold",
                                           ctrl_speed_hold_entry,
                                           &s_speed_hold_ctx,
                                           2048,
                                           CONTROL_ROS_THREAD_PRIORITY,
                                           CONTROL_ROS_THREAD_TICK);
    if (s_speed_hold_thread == RT_NULL)
    {
        rt_kprintf("motor_speed_hold create failed\n");
        return -1;
    }

    rt_thread_startup(s_speed_hold_thread);
    rt_kprintf("motor_speed_hold start joint=%u speed_x1000=%d cur_x1000=%d duration=%u period=%u\n",
               (unsigned int)s_speed_hold_ctx.joint_id,
               (int)ctrl_float_to_scaled_i32(s_speed_hold_ctx.speed_rad_s, 1000.0f),
               (int)ctrl_float_to_scaled_i32(s_speed_hold_ctx.limit_cur, 1000.0f),
               (unsigned int)s_speed_hold_ctx.duration_ms,
               (unsigned int)s_speed_hold_ctx.period_ms);
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_speed_hold, periodically refresh speed command and auto stop);

static int cmd_cansimple_scan(int argc, char **argv)
{
    rt_uint32_t count = 5U;
    rt_uint32_t period_ms = 300U;
    rt_uint32_t i;
    rt_err_t ret = RT_EOK;

    if (argc >= 2)
    {
        count = (rt_uint32_t)strtoul(argv[1], RT_NULL, 0);
    }
    if (argc >= 3)
    {
        period_ms = (rt_uint32_t)strtoul(argv[2], RT_NULL, 0);
    }

    if (!s_is_inited)
    {
        rt_kprintf("cansimple_scan control not inited\n");
        return -1;
    }

    if (count == 0U)
    {
        count = 1U;
    }
    if (count > 20U)
    {
        count = 20U;
    }
    if (period_ms < 50U)
    {
        period_ms = 50U;
    }
    if (period_ms > 2000U)
    {
        period_ms = 2000U;
    }

    rt_kprintf("cansimple_scan count=%u period=%u: wait address replies\n",
               (unsigned int)count,
               (unsigned int)period_ms);
    for (i = 0U; i < count; ++i)
    {
        ret = ctrl_cansimple_request_address();
        if (ret != RT_EOK)
        {
            rt_kprintf("cansimple_scan send failed ret=%d index=%u\n", ret, (unsigned int)i);
            return ret;
        }
        rt_thread_mdelay(period_ms);
    }

    return ret;
}
MSH_CMD_EXPORT(cmd_cansimple_scan, scan ODrive CANSimple nodes by Address command);

static int cmd_cansimple_status(int argc, char **argv)
{
    rt_uint8_t node_id;
    rt_tick_t now = rt_tick_get();
    rt_bool_t any = RT_FALSE;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    if (!s_is_inited)
    {
        rt_kprintf("cansimple_status control not inited\n");
        return -1;
    }

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    for (node_id = 0U; node_id < 64U; ++node_id)
    {
        if (s_cansimple_seen[node_id])
        {
            rt_uint32_t age_ms = (rt_uint32_t)((now - s_cansimple_heartbeat_tick[node_id]) *
                                               1000U / RT_TICK_PER_SECOND);

            any = RT_TRUE;
            rt_kprintf("cansimple node=%u state=%u error=0x%08X flags=0x%02X temp=%d life=%u age_ms=%u\n",
                       (unsigned int)node_id,
                       (unsigned int)s_cansimple_axis_state[node_id],
                       (unsigned int)s_cansimple_axis_error[node_id],
                       (unsigned int)s_cansimple_flags[node_id],
                       (int)s_cansimple_temp_c[node_id],
                       (unsigned int)s_cansimple_life[node_id],
                       (unsigned int)age_ms);
        }
    }
    rt_mutex_release(&s_data_lock);

    if (!any)
    {
        rt_kprintf("cansimple no heartbeat seen\n");
    }

    return 0;
}
MSH_CMD_EXPORT(cmd_cansimple_status, show cached CANSimple heartbeat state);

static int cmd_cansimple_clear(int argc, char **argv)
{
    rt_uint8_t node_id;
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("usage: cmd_cansimple_clear <node_id>\n");
        return -1;
    }

    node_id = (rt_uint8_t)strtoul(argv[1], RT_NULL, 0);
    if (node_id > 0x3FU)
    {
        rt_kprintf("cansimple_clear invalid node_id=%u\n", (unsigned int)node_id);
        return -1;
    }

    ret = ctrl_cansimple_clear_errors(node_id);
    rt_kprintf("cansimple_clear node=%u ret=%d\n", (unsigned int)node_id, ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_cansimple_clear, clear CANSimple node errors);

static int cmd_cansimple_enable(int argc, char **argv)
{
    rt_uint8_t node_id;
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("usage: cmd_cansimple_enable <node_id>\n");
        return -1;
    }

    node_id = (rt_uint8_t)strtoul(argv[1], RT_NULL, 0);
    if (node_id > 0x3FU)
    {
        rt_kprintf("cansimple_enable invalid node_id=%u\n", (unsigned int)node_id);
        return -1;
    }

    ret = ctrl_cansimple_set_axis_state(node_id, CANSIMPLE_AXIS_STATE_CLOSED_LOOP);
    rt_kprintf("cansimple_enable node=%u state=%u ret=%d\n",
               (unsigned int)node_id,
               (unsigned int)CANSIMPLE_AXIS_STATE_CLOSED_LOOP,
               ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_cansimple_enable, set CANSimple node to closed loop);

static int cmd_cansimple_idle(int argc, char **argv)
{
    rt_uint8_t node_id;
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("usage: cmd_cansimple_idle <node_id>\n");
        return -1;
    }

    node_id = (rt_uint8_t)strtoul(argv[1], RT_NULL, 0);
    if (node_id > 0x3FU)
    {
        rt_kprintf("cansimple_idle invalid node_id=%u\n", (unsigned int)node_id);
        return -1;
    }

    ret = ctrl_cansimple_set_axis_state(node_id, CANSIMPLE_AXIS_STATE_IDLE);
    rt_kprintf("cansimple_idle node=%u state=%u ret=%d\n",
               (unsigned int)node_id,
               (unsigned int)CANSIMPLE_AXIS_STATE_IDLE,
               ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_cansimple_idle, set CANSimple node to idle);

static int cmd_cansimple_mode(int argc, char **argv)
{
    rt_uint8_t node_id;
    rt_uint32_t control_mode;
    rt_uint32_t input_mode;
    rt_err_t ret;

    if (argc < 4)
    {
        rt_kprintf("usage: cmd_cansimple_mode <node_id> <control_mode> <input_mode>\n");
        rt_kprintf("       velocity ramp: cmd_cansimple_mode <node_id> 2 2\n");
        return -1;
    }

    node_id = (rt_uint8_t)strtoul(argv[1], RT_NULL, 0);
    control_mode = (rt_uint32_t)strtoul(argv[2], RT_NULL, 0);
    input_mode = (rt_uint32_t)strtoul(argv[3], RT_NULL, 0);
    if (node_id > 0x3FU)
    {
        rt_kprintf("cansimple_mode invalid node_id=%u\n", (unsigned int)node_id);
        return -1;
    }

    ret = ctrl_cansimple_set_controller_mode(node_id, control_mode, input_mode);
    rt_kprintf("cansimple_mode node=%u control=%u input=%u ret=%d\n",
               (unsigned int)node_id,
               (unsigned int)control_mode,
               (unsigned int)input_mode,
               ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_cansimple_mode, set CANSimple controller and input mode);

static int cmd_cansimple_error(int argc, char **argv)
{
    rt_uint8_t node_id;
    rt_uint8_t types[4] = {0U, 1U, 3U, 4U};
    rt_uint8_t count = 4U;
    rt_uint8_t i;
    rt_err_t ret = RT_EOK;

    if (argc < 2)
    {
        rt_kprintf("usage: cmd_cansimple_error <node_id> [type:0 motor,1 encoder,3 controller,4 system]\n");
        return -1;
    }

    node_id = (rt_uint8_t)strtoul(argv[1], RT_NULL, 0);
    if (node_id > 0x3FU)
    {
        rt_kprintf("cansimple_error invalid node_id=%u\n", (unsigned int)node_id);
        return -1;
    }

    if (argc >= 3)
    {
        types[0] = (rt_uint8_t)strtoul(argv[2], RT_NULL, 0);
        count = 1U;
    }

    for (i = 0U; i < count; ++i)
    {
        ret = ctrl_cansimple_request_error(node_id, types[i]);
        rt_kprintf("cansimple_error request node=%u type=%u ret=%d\n",
                   (unsigned int)node_id,
                   (unsigned int)types[i],
                   ret);
        if (ret != RT_EOK)
        {
            return ret;
        }
        rt_thread_mdelay(120);
    }

    return ret;
}
MSH_CMD_EXPORT(cmd_cansimple_error, query CANSimple detailed error);

static int cmd_cansimple_sdo_read(int argc, char **argv)
{
    rt_uint8_t node_id;
    rt_uint16_t endpoint_id;
    rt_uint8_t payload[8] = {0};
    rt_err_t ret;

    if (argc < 3)
    {
        rt_kprintf("usage: cmd_cansimple_sdo_read <node_id> <endpoint_id>\n");
        return -1;
    }

    node_id = (rt_uint8_t)strtoul(argv[1], RT_NULL, 0);
    endpoint_id = (rt_uint16_t)strtoul(argv[2], RT_NULL, 0);
    if (node_id > 0x3FU)
    {
        rt_kprintf("cansimple_sdo_read invalid node_id=%u\n", (unsigned int)node_id);
        return -1;
    }

    payload[0] = 0U;
    ctrl_u16_to_le(endpoint_id, &payload[1]);
    ret = ctrl_cansimple_send(node_id, CANSIMPLE_CMD_RX_SDO, payload, sizeof(payload));
    rt_kprintf("cansimple_sdo_read node=%u endpoint=%u ret=%d\n",
               (unsigned int)node_id,
               (unsigned int)endpoint_id,
               ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_cansimple_sdo_read, read CANSimple endpoint by RxSdo);

static int cmd_cansimple_sdo_write_u32(int argc, char **argv)
{
    rt_uint8_t node_id;
    rt_uint16_t endpoint_id;
    rt_uint32_t value;
    rt_uint8_t payload[8] = {0};
    rt_err_t ret;

    if (argc < 4)
    {
        rt_kprintf("usage: cmd_cansimple_sdo_write_u32 <node_id> <endpoint_id> <value>\n");
        return -1;
    }

    node_id = (rt_uint8_t)strtoul(argv[1], RT_NULL, 0);
    endpoint_id = (rt_uint16_t)strtoul(argv[2], RT_NULL, 0);
    value = (rt_uint32_t)strtoul(argv[3], RT_NULL, 0);
    if (node_id > 0x3FU)
    {
        rt_kprintf("cansimple_sdo_write_u32 invalid node_id=%u\n", (unsigned int)node_id);
        return -1;
    }

    payload[0] = 1U;
    ctrl_u16_to_le(endpoint_id, &payload[1]);
    ctrl_u32_to_le(value, &payload[4]);
    ret = ctrl_cansimple_send(node_id, CANSIMPLE_CMD_RX_SDO, payload, sizeof(payload));
    rt_kprintf("cansimple_sdo_write_u32 node=%u endpoint=%u value=0x%08X ret=%d\n",
               (unsigned int)node_id,
               (unsigned int)endpoint_id,
               (unsigned int)value,
               ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_cansimple_sdo_write_u32, write CANSimple endpoint by RxSdo);

static int cmd_cansimple_speed(int argc, char **argv)
{
    rt_uint8_t node_id;
    float speed_rad_s;
    float limit_cur;
    rt_uint32_t duration_ms = 5000U;
    rt_uint32_t period_ms = 200U;
    rt_uint32_t elapsed_ms = 0U;
    rt_err_t ret;

    if (argc < 4)
    {
        rt_kprintf("usage: cmd_cansimple_speed <node_id> <speed_rad_s> <limit_cur> [duration_ms] [period_ms]\n");
        return -1;
    }

    node_id = (rt_uint8_t)strtoul(argv[1], RT_NULL, 0);
    speed_rad_s = (float)atof(argv[2]);
    limit_cur = (float)atof(argv[3]);
    if (argc >= 5)
    {
        duration_ms = (rt_uint32_t)strtoul(argv[4], RT_NULL, 0);
    }
    if (argc >= 6)
    {
        period_ms = (rt_uint32_t)strtoul(argv[5], RT_NULL, 0);
    }

    if (node_id > 0x3FU)
    {
        rt_kprintf("cansimple_speed invalid node_id=%u\n", (unsigned int)node_id);
        return -1;
    }
    if (duration_ms == 0U)
    {
        duration_ms = 5000U;
    }
    if (duration_ms > 30000U)
    {
        duration_ms = 30000U;
    }
    if (period_ms < 20U)
    {
        period_ms = 20U;
    }
    if (period_ms > 1000U)
    {
        period_ms = 1000U;
    }

    ret = ctrl_cansimple_velocity_start_node(node_id, speed_rad_s, limit_cur, RT_TRUE);
    if (ret != RT_EOK)
    {
        rt_kprintf("cansimple_speed start failed node=%u ret=%d\n", (unsigned int)node_id, ret);
        return ret;
    }

    while (elapsed_ms < duration_ms)
    {
        rt_thread_mdelay(period_ms);
        elapsed_ms += period_ms;

        ret = ctrl_cansimple_set_input_vel_node(node_id, speed_rad_s, 0.0f);
        if (ret != RT_EOK)
        {
            rt_kprintf("cansimple_speed refresh failed node=%u ret=%d elapsed=%u\n",
                       (unsigned int)node_id,
                       ret,
                       (unsigned int)elapsed_ms);
            break;
        }
    }

    (void)ctrl_cansimple_set_input_vel_node(node_id, 0.0f, 0.0f);
    rt_thread_mdelay(5);
    (void)ctrl_cansimple_set_axis_state(node_id, CANSIMPLE_AXIS_STATE_IDLE);
    rt_kprintf("cansimple_speed done node=%u elapsed=%u ret=%d\n",
               (unsigned int)node_id,
               (unsigned int)elapsed_ms,
               ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_cansimple_speed, raw CANSimple velocity test by node id);

static int cmd_motor3_status(int argc, char **argv)
{
    char *fb_argv[] = {"motor_fb", "3"};

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    (void)cmd_cansimple_status(0, RT_NULL);
    return cmd_motor_fb(2, fb_argv);
}
MSH_CMD_EXPORT(cmd_motor3_status, show CANSimple heartbeat and joint3 feedback);

static int cmd_motor3_enable(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    rt_kprintf("motor3_enable ret=%d\n", control_motor_enable(3U));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor3_enable, enable CANSimple motor node 3);

static int cmd_motor3_stop(int argc, char **argv)
{
    rt_bool_t clear = RT_TRUE;

    if (argc >= 2)
    {
        clear = (atoi(argv[1]) != 0) ? RT_TRUE : RT_FALSE;
    }

    rt_kprintf("motor3_stop ret=%d\n", control_motor_stop(3U, clear));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor3_stop, stop CANSimple motor node 3: motor3_stop [clear_fault]);

static int cmd_motor3_speed(int argc, char **argv)
{
    float speed_rad_s;
    float limit_cur;
    rt_uint32_t duration_ms = 1000U;
    rt_uint32_t period_ms = 20U;
    char duration_buf[12];
    char period_buf[12];
    char *hold_argv[] = {"motor_speed_hold", "3", RT_NULL, RT_NULL, duration_buf, period_buf};

    if (argc < 3)
    {
        rt_kprintf("usage: motor3_speed <speed_rad_s> <limit_cur> [duration_ms] [period_ms]\n");
        return -1;
    }

    speed_rad_s = (float)atof(argv[1]);
    limit_cur = (float)atof(argv[2]);
    if (argc >= 4)
    {
        duration_ms = (rt_uint32_t)strtoul(argv[3], RT_NULL, 0);
    }
    if (argc >= 5)
    {
        period_ms = (rt_uint32_t)strtoul(argv[4], RT_NULL, 0);
    }

    rt_snprintf(duration_buf, sizeof(duration_buf), "%u", (unsigned int)duration_ms);
    rt_snprintf(period_buf, sizeof(period_buf), "%u", (unsigned int)period_ms);
    hold_argv[2] = argv[1];
    hold_argv[3] = argv[2];

    rt_kprintf("motor3_speed node=3 speed_x1000=%d cur_x1000=%d\n",
               (int)ctrl_float_to_scaled_i32(speed_rad_s, 1000.0f),
               (int)ctrl_float_to_scaled_i32(limit_cur, 1000.0f));
    return cmd_motor_speed_hold(6, hold_argv);
}
MSH_CMD_EXPORT(cmd_motor3_speed, run CANSimple motor node 3 velocity hold);

static int cmd_motor3_pos(int argc, char **argv)
{
    float pos_rad;
    float limit_spd;

    if (argc < 3)
    {
        rt_kprintf("usage: motor3_pos <pos_rad> <limit_spd_rad_s>\n");
        return -1;
    }

    pos_rad = (float)atof(argv[1]);
    limit_spd = (float)atof(argv[2]);
    rt_kprintf("motor3_pos ret=%d pos_mrad=%d limit_mrad_s=%d\n",
               control_motor_position_control(3U, pos_rad, limit_spd, RT_TRUE),
               (int)ctrl_float_to_scaled_i32(pos_rad, 1000.0f),
               (int)ctrl_float_to_scaled_i32(limit_spd, 1000.0f));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor3_pos, set CANSimple motor node 3 position);

static int cmd_motor3_torque(int argc, char **argv)
{
    char *torque_argv[] = {"motor_torque", "3", RT_NULL};

    if (argc < 2)
    {
        rt_kprintf("usage: motor3_torque <torque_nm>\n");
        return -1;
    }

    torque_argv[2] = argv[1];
    return cmd_motor_torque(3, torque_argv);
}
MSH_CMD_EXPORT(cmd_motor3_torque, set CANSimple motor node 3 torque);

static int cmd_motor_hold_stop(int argc, char **argv)
{
    rt_uint8_t clear = 1U;

    if (argc >= 2)
    {
        clear = (rt_uint8_t)atoi(argv[1]);
    }

    s_speed_hold_ctx.stop_requested = RT_TRUE;
    rt_kprintf("motor_hold_stop ret=%d\n",
               control_motor_stop(s_speed_hold_ctx.joint_id, clear ? RT_TRUE : RT_FALSE));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_hold_stop, stop active speed hold command);

static int cmd_motor_pos(int argc, char **argv)
{
    rt_bool_t csp_mode = RT_TRUE;

    if (argc < 4)
    {
        rt_kprintf("usage: motor_pos <joint> <pos_rad> <limit_spd> [csp(0|1)]\n");
        return -1;
    }

    if (argc >= 5)
    {
        csp_mode = (atoi(argv[4]) != 0) ? RT_TRUE : RT_FALSE;
    }

    rt_kprintf("motor_pos ret=%d\n",
               control_motor_position_control((rt_uint8_t)atoi(argv[1]),
                                              (float)atof(argv[2]),
                                              (float)atof(argv[3]),
                                              csp_mode));
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_pos, position/CSP mode control by private protocol);

static int cmd_motor_fb(int argc, char **argv)
{
    control_motor_feedback_t fb;
    rt_uint8_t joint;
    rt_int32_t pos_mrad;
    rt_int32_t vel_mrad_s;
    rt_int32_t tor_mnm;
    rt_int32_t temp_dc;

    if (argc < 2)
    {
        rt_kprintf("usage: motor_fb <joint(1~%u)>\n", (unsigned int)CONTROL_MOTOR_JOINT_COUNT);
        return -1;
    }

    joint = (rt_uint8_t)atoi(argv[1]);
    if (control_get_motor_feedback(joint, &fb) != RT_EOK)
    {
        rt_kprintf("get feedback failed\n");
        return -1;
    }

    pos_mrad = ctrl_float_to_scaled_i32(fb.pos_rad, 1000.0f);
    vel_mrad_s = ctrl_float_to_scaled_i32(fb.vel_rad_s, 1000.0f);
    tor_mnm = ctrl_float_to_scaled_i32(fb.torque_nm, 1000.0f);
    temp_dc = ctrl_float_to_scaled_i32(fb.temp_c, 10.0f);

    rt_kprintf("MOTOR[%d]: id=%u proto=%u mode=%u fault=0x%02X pos_mrad=%d vel_mrad_s=%d tor_mNm=%d temp_dC=%d tick=%u\n",
               joint,
               fb.motor_id,
               (unsigned int)fb.protocol,
               fb.mode_state,
               fb.fault_summary,
               (int)pos_mrad,
               (int)vel_mrad_s,
               (int)tor_mnm,
               (int)temp_dc,
               (unsigned int)fb.timestamp);
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_fb, show motor latest feedback);

static int cmd_m33_joint_calib(int argc, char **argv)
{
    rt_uint8_t joint;
    rt_uint8_t start = 1U;
    rt_uint8_t end = (rt_uint8_t)CONTROL_MOTOR_JOINT_COUNT;

    if (argc >= 2)
    {
        joint = (rt_uint8_t)atoi(argv[1]);
        if ((joint == 0U) || (joint > CONTROL_MOTOR_JOINT_COUNT))
        {
            rt_kprintf("usage: m33_joint_calib [joint(1~%u)]\n",
                       (unsigned int)CONTROL_MOTOR_JOINT_COUNT);
            return -1;
        }
        start = joint;
        end = joint;
    }

    for (joint = start; joint <= end; joint++)
    {
        rt_kprintf("JOINT_CALIB: joint=%u motor_id=%u proto=%u calibrated=%u direction_x1000=%d gear_x1000=%d zero_mrad=%d zero_source=%s\n",
                   (unsigned int)joint,
                   (unsigned int)ctrl_motor_id_by_joint(joint),
                   (unsigned int)ctrl_motor_protocol_by_joint(joint),
                   ctrl_motor_joint_is_calibrated(joint) ? 1U : 0U,
                   (int)ctrl_float_to_scaled_i32(ctrl_motor_direction_by_joint(joint), 1000.0f),
                   (int)ctrl_float_to_scaled_i32(ctrl_motor_gear_ratio_by_joint(joint), 1000.0f),
                   (int)ctrl_float_to_scaled_i32(ctrl_motor_zero_offset_by_joint(joint), 1000.0f),
                   ctrl_motor_zero_source_by_joint(joint));
    }
    rt_kprintf("JOINT_CALIB_NOTE: absolute position commands are rejected while calibrated=0\n");
    rt_kprintf("JOINT_ZERO_POLICY: %s\n", CONTROL_FORMAL_ZERO_POLICY);

    return 0;
}
MSH_CMD_EXPORT(cmd_m33_joint_calib, show M33 joint calibration gate and offsets);

static int cmd_m33_motor_status_once(int argc, char **argv)
{
    rt_uint8_t sent;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    sent = ctrl_publish_cached_motor_status_once();
    rt_kprintf("m33_motor_status_once sent=%u base=0x%03X period_ms=%u fresh_ms=%u\n",
               (unsigned int)sent,
               (unsigned int)CONTROL_CAN_ID_M33_MOTOR_STATUS_BASE,
               (unsigned int)CONTROL_M33_MOTOR_STATUS_PERIOD_MS,
               (unsigned int)CONTROL_M33_MOTOR_STATUS_FRESH_MS);
    return 0;
}
MSH_CMD_EXPORT(cmd_m33_motor_status_once, publish cached 0x330 motor telemetry once);

static int cmd_motor_param(int argc, char **argv)
{
    control_motor_param_report_t param;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    if (control_get_last_motor_param(&param) != RT_EOK || !param.valid)
    {
        rt_kprintf("no motor param response\n");
        return -1;
    }

    if (param.index == MOTOR_PARAM_INDEX_RUN_MODE)
    {
        rt_kprintf("MOTOR_PARAM: id=%u index=0x%04X mode=%u tick=%u\n",
                   (unsigned int)param.motor_id,
                   (unsigned int)param.index,
                   (unsigned int)param.raw_u8,
                   (unsigned int)param.timestamp);
    }
    else
    {
        rt_kprintf("MOTOR_PARAM: id=%u index=0x%04X raw=%u value_x10000=%d tick=%u\n",
                   (unsigned int)param.motor_id,
                   (unsigned int)param.index,
                   (unsigned int)param.raw_u8,
                   (int)ctrl_float_to_scaled_i32(param.value_f32, 10000.0f),
                   (unsigned int)param.timestamp);
    }
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_param, show latest motor parameter response);

static int cmd_motor_probe_last(int argc, char **argv)
{
    control_motor_probe_report_t probe;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ctrl_poll_can_messages();

    if (control_get_last_motor_probe(&probe) != RT_EOK || !probe.valid)
    {
        rt_kprintf("no motor probe response\n");
        return -1;
    }

    rt_kprintf("MOTOR_PROBE: id=0x%02X uid=0x%08lx%08lx tick=%u\n",
               (unsigned int)probe.motor_id,
               (unsigned long)(probe.unique_id >> 32),
               (unsigned long)(probe.unique_id & 0xFFFFFFFFULL),
               probe.timestamp);
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_probe_last, show latest get-id probe response);

static int cmd_ros_last(int argc, char **argv)
{
    control_ros_command_t cmd;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    if (control_get_last_ros_command(&cmd) != RT_EOK)
    {
        rt_kprintf("get ros cmd failed\n");
        return -1;
    }

    rt_kprintf("ROS_CMD: cmd=%u joint=%u clear=%u mode=%u active=%u pos=%d vel=%d tor=%d tick=%u\n",
               (unsigned int)cmd.command,
               (unsigned int)cmd.joint_id,
               (unsigned int)cmd.clear_fault,
               (unsigned int)cmd.mode,
               (unsigned int)cmd.active_report_enable,
               (int)cmd.target_pos_01deg,
               (int)cmd.target_vel_rpm,
               (int)cmd.target_torque_ma,
               cmd.timestamp);
    return 0;
}
MSH_CMD_EXPORT(cmd_ros_last, show last ros command from can);

static int cmd_control_debug(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    rt_kprintf("CTRL_DBG: rx_total=%lu hb=%lu ros_id=%lu parsed=%lu enq=%lu applied=%lu qfail=%lu\n",
               (unsigned long)s_dbg_rx_total,
               (unsigned long)s_dbg_rx_heartbeat,
               (unsigned long)s_dbg_rx_ros_id,
               (unsigned long)s_dbg_ros_parsed,
               (unsigned long)s_dbg_ros_enqueued,
               (unsigned long)s_dbg_ros_applied,
               (unsigned long)s_dbg_ros_queue_fail);
    rt_kprintf("CTRL_DBG_F103: ack=%lu sensor=%lu health=%lu ids ctrl=0x%03X ack=0x%03X sensor=0x%03X health=0x%03X\n",
               (unsigned long)s_dbg_rx_f103_ack,
               (unsigned long)s_dbg_rx_f103_sensor,
               (unsigned long)s_dbg_rx_f103_health,
               (unsigned int)CONTROL_CAN_ID_F103_CTRL,
               (unsigned int)CONTROL_CAN_ID_F103_ACK,
               (unsigned int)CONTROL_CAN_ID_F103_SENSOR,
               (unsigned int)CONTROL_CAN_ID_F103_HEALTH);
    rt_kprintf("CTRL_DBG_LAST: id=0x%08lx ide=%u len=%u data=%02X %02X %02X %02X %02X %02X %02X %02X\n",
               (unsigned long)s_dbg_last_rx_id,
               (unsigned int)s_dbg_last_rx_ide,
               (unsigned int)s_dbg_last_rx_len,
               s_dbg_last_rx_data[0], s_dbg_last_rx_data[1],
               s_dbg_last_rx_data[2], s_dbg_last_rx_data[3],
               s_dbg_last_rx_data[4], s_dbg_last_rx_data[5],
               s_dbg_last_rx_data[6], s_dbg_last_rx_data[7]);
    return 0;
}
MSH_CMD_EXPORT(cmd_control_debug, show control can rx debug counters);

static int cmd_m33_prearm_check(int argc, char **argv)
{
    control_prearm_check_t check;
    rt_uint32_t required_joint_mask = (rt_uint32_t)CONTROL_PREARM_REQUIRED_JOINT_MASK;
    rt_bool_t mask_overridden = RT_FALSE;

    if (argc >= 2)
    {
        required_joint_mask = (rt_uint32_t)strtoul(argv[1], RT_NULL, 0);
        mask_overridden = RT_TRUE;
    }
    if (required_joint_mask == 0U)
    {
        rt_kprintf("usage: m33_prearm_check [required_joint_mask_hex]\n");
        rt_kprintf("example: m33_prearm_check 0x40  # slot6 / 0x336 / current motor7 check\n");
        return -1;
    }

    ctrl_poll_can_messages();
    ctrl_prearm_check_build(&check, required_joint_mask);

    rt_kprintf("PREARM: ready=%u motion_allowed_would_be=%u\n",
               check.ready ? 1U : 0U,
               check.ready ? 1U : 0U);
    rt_kprintf("PREARM_MASK: required_mask=0x%08lX source=%s default_mask=0x%08X\n",
               (unsigned long)check.required_joint_mask,
               mask_overridden ? "argv" : "config",
               (unsigned int)CONTROL_PREARM_REQUIRED_JOINT_MASK);
    rt_kprintf("PREARM_MODE: logging_only_clear=%u logging_only_compile=%u allow_with_logging_only=%u\n",
               check.logging_only_clear ? 1U : 0U,
               (unsigned int)CONTROL_ROS_COMMAND_LOGGING_ONLY,
               (unsigned int)CONTROL_PREARM_ALLOW_WITH_LOGGING_ONLY);
    rt_kprintf("PREARM_HEARTBEAT: ok=%u age_ms=%lu timeout_ms=%u\n",
               check.heartbeat_ok ? 1U : 0U,
               (unsigned long)check.heartbeat_age_ms,
               (unsigned int)CONTROL_ROS_HEARTBEAT_TIMEOUT_MS);
    rt_kprintf("PREARM_INPUTS: estop_confirmed=%u power_confirmed=%u limits_confirmed=%u\n",
               check.estop_input_confirmed ? 1U : 0U,
               check.power_input_confirmed ? 1U : 0U,
               check.limits_confirmed ? 1U : 0U);
    rt_kprintf("PREARM_INPUT_DETAIL: estop source=%s safe_now=%u; power source=%s safe_now=%u; limits source=%s safe_now=%u\n",
               CONTROL_PREARM_ESTOP_INPUT_SOURCE,
               check.estop_safe_now ? 1U : 0U,
               CONTROL_PREARM_POWER_INPUT_SOURCE,
               check.power_safe_now ? 1U : 0U,
               CONTROL_PREARM_LIMITS_SOURCE,
               check.limits_safe_now ? 1U : 0U);
    rt_kprintf("PREARM_CODE_LIMITS: position confirmed=%u safe_now=%u; speed confirmed=%u safe_now=%u; torque_current confirmed=%u safe_now=%u\n",
               check.position_limits_confirmed ? 1U : 0U,
               check.position_limits_safe_now ? 1U : 0U,
               check.speed_limits_confirmed ? 1U : 0U,
               check.speed_limits_safe_now ? 1U : 0U,
               check.torque_current_limits_confirmed ? 1U : 0U,
               check.torque_current_limits_safe_now ? 1U : 0U);
    rt_kprintf("PREARM_MOTORS: required_mask=0x%08lX fresh_mask=0x%08lX fault_mask=0x%08lX fresh_count=%u fresh_ok=%u fault_free=%u\n",
               (unsigned long)check.required_joint_mask,
               (unsigned long)check.fresh_joint_mask,
               (unsigned long)check.fault_joint_mask,
               (unsigned int)check.fresh_count,
               check.required_motor_feedback_fresh ? 1U : 0U,
               check.required_motor_feedback_fault_free ? 1U : 0U);
    rt_kprintf("PREARM_NOTE: diagnostic only; this command never changes mode and never enables motion\n");

    return check.ready ? 0 : -1;
}
MSH_CMD_EXPORT(cmd_m33_prearm_check, show diagnostic pre-arm checklist without enabling motion);

static int cmd_m33_safety_inputs(int argc, char **argv)
{
    const control_safety_input_diag_t inputs[] =
    {
        {
            "estop",
            CONTROL_PREARM_ESTOP_INPUT_SOURCE,
            (CONTROL_PREARM_ESTOP_INPUT_CONFIRMED != 0U) ? RT_TRUE : RT_FALSE,
            (CONTROL_PREARM_ESTOP_SAFE_NOW != 0U) ? RT_TRUE : RT_FALSE,
            "emergency stop input must be wired, tested, and released"
        },
        {
            "power",
            CONTROL_PREARM_POWER_INPUT_SOURCE,
            ((CONTROL_PREARM_POWER_CHECK_REQUIRED == 0U) ||
             (CONTROL_PREARM_POWER_INPUT_CONFIRMED != 0U)) ? RT_TRUE : RT_FALSE,
            ((CONTROL_PREARM_POWER_CHECK_REQUIRED == 0U) ||
             (CONTROL_PREARM_POWER_SAFE_NOW != 0U)) ? RT_TRUE : RT_FALSE,
            (CONTROL_PREARM_POWER_CHECK_REQUIRED != 0U)
                ? "motor power and voltage must be monitored and inside safe range"
                : "power OK input is not used in this firmware slice"
        },
        {
            "limits",
            CONTROL_PREARM_LIMITS_SOURCE,
            (CONTROL_PREARM_LIMITS_CONFIRMED != 0U) ? RT_TRUE : RT_FALSE,
            (CONTROL_PREARM_LIMITS_SAFE_NOW != 0U) ? RT_TRUE : RT_FALSE,
            "joint limits must be calibrated before any assisted motion"
        },
    };
    rt_uint8_t i;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    for (i = 0U; i < (rt_uint8_t)(sizeof(inputs) / sizeof(inputs[0])); i++)
    {
        rt_kprintf("SAFETY_INPUT: name=%s source=%s confirmed=%u safe_now=%u meaning=%s\n",
                   inputs[i].name,
                   inputs[i].source,
                   inputs[i].confirmed ? 1U : 0U,
                   inputs[i].safe_now ? 1U : 0U,
                   inputs[i].meaning);
    }
    rt_kprintf("SAFETY_INPUT_NOTE: diagnostic only; defaults are unwired/unconfirmed and must block prearm\n");

    return 0;
}
MSH_CMD_EXPORT(cmd_m33_safety_inputs, show physical safety input contract without enabling motion);

/* Deprecated aliases */
static int cmd_rs00_en(int argc, char **argv)
{
    return cmd_motor_en(argc, argv);
}
MSH_CMD_EXPORT(cmd_rs00_en, deprecated alias: use motor_en);

static int cmd_rs00_stop(int argc, char **argv)
{
    return cmd_motor_stop(argc, argv);
}
MSH_CMD_EXPORT(cmd_rs00_stop, deprecated alias: use motor_stop);

static int cmd_rs00_ctrl(int argc, char **argv)
{
    return cmd_motor_ctrl(argc, argv);
}
MSH_CMD_EXPORT(cmd_rs00_ctrl, deprecated alias: use motor_ctrl);

static int cmd_rs00_mode(int argc, char **argv)
{
    return cmd_motor_mode(argc, argv);
}
MSH_CMD_EXPORT(cmd_rs00_mode, deprecated alias: use motor_mode);

static int cmd_rs00_fb(int argc, char **argv)
{
    return cmd_motor_fb(argc, argv);
}
MSH_CMD_EXPORT(cmd_rs00_fb, deprecated alias: use motor_fb);

static int cmd_sensor_show(int argc, char **argv)
{
    control_emg_report_t emg;
    control_heart_report_t heart;
    control_sensor_node_sample_t node;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    if (control_get_emg_report(&emg) == RT_EOK)
    {
        rt_kprintf("EMG: ch1=%u ch2=%u rms=%u seq=%u status=%u tick=%u\n",
                   emg.ch1_raw,
                   emg.ch2_raw,
                   emg.rms_raw,
                   emg.seq,
                   emg.status,
                   emg.timestamp);
    }

    if (control_get_heart_report(&heart) == RT_EOK)
    {
        rt_kprintf("HR : bpm=%u hrv=%u quality=%u status=%u tick=%u\n",
                   heart.bpm,
                   heart.hrv_ms,
                   heart.signal_quality,
                   heart.status,
                   heart.timestamp);
    }

    if (control_get_sensor_node_sample(&node) == RT_EOK)
    {
        rt_kprintf("F103: emg_raw=%u emg_filt=%d hr_raw=%u hr_filt=%u flags=0x%02X sensor_tick=%u\n",
                   node.emg_raw,
                   node.emg_filt,
                   node.hr_raw,
                   node.hr_filt,
                   node.flags,
                   node.sensor_timestamp);
        rt_kprintf("F103_HEALTH: state=%u err=%u q=%u health_tick=%u last_ack cmd=0x%02X seq=%u status=%u ack_tick=%u\n",
                   node.node_state,
                   node.node_err_cnt,
                   node.node_q_fill,
                   node.health_timestamp,
                   node.last_ack_cmd,
                   node.last_ack_seq,
                   node.last_ack_status,
                   node.ack_timestamp);
    }

    return 0;
}
MSH_CMD_EXPORT(cmd_sensor_show, show latest emg and heart reports);

static int cmd_sensor_rate(int argc, char **argv)
{
    rt_bool_t en;
    rt_uint16_t period;
    rt_err_t ret;

    if (argc < 3)
    {
        rt_kprintf("usage: sensor_rate <en(0|1)> <period_ms>\n");
        return -1;
    }

    en = (atoi(argv[1]) != 0) ? RT_TRUE : RT_FALSE;
    period = (rt_uint16_t)atoi(argv[2]);

    ret = control_sensor_report_enable(en, period);
    rt_kprintf("sensor_rate ret=%d\n", ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_sensor_rate, configure stm32 sensor report period);

static int cmd_f103_ping(int argc, char **argv)
{
    rt_uint32_t count = 1U;
    rt_uint32_t delay_ms = 20U;
    rt_uint32_t i;
    rt_uint8_t payload[8] = {0};
    rt_err_t ret = RT_EOK;

    if (argc >= 2)
    {
        count = (rt_uint32_t)atoi(argv[1]);
    }
    if (argc >= 3)
    {
        delay_ms = (rt_uint32_t)atoi(argv[2]);
    }
    if (count == 0U)
    {
        count = 1U;
    }

    for (i = 0U; i < count; i++)
    {
        rt_memset(payload, 0, sizeof(payload));
        payload[0] = CONTROL_F103_CMD_GET_STATUS;
        payload[1] = s_tx_seq++;
        ret = ctrl_can_send(CONTROL_CAN_ID_F103_CTRL, RT_CAN_STDID, payload, sizeof(payload));
        if (ret != RT_EOK)
        {
            rt_kprintf("f103_ping send failed i=%lu ret=%d\n", (unsigned long)i, ret);
            return ret;
        }
        if (delay_ms > 0U)
        {
            rt_thread_mdelay(delay_ms);
        }
    }

    rt_kprintf("f103_ping sent count=%lu delay=%lu ret=%d\n",
               (unsigned long)count,
               (unsigned long)delay_ms,
               ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_f103_ping, send F103 GET_STATUS frames: f103_ping [count] [delay_ms]);
MSH_CMD_EXPORT_ALIAS(cmd_f103_ping, f103_ping, send F103 GET_STATUS frames: f103_ping [count] [delay_ms]);
#endif
