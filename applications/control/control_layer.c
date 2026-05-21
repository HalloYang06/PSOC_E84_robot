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

static rt_device_t s_can_dev = RT_NULL;
static rt_thread_t s_can_rx_thread = RT_NULL;
static rt_thread_t s_ros_cmd_thread = RT_NULL;
static struct rt_semaphore s_can_rx_sem;
static struct rt_mutex s_data_lock;
static struct rt_messagequeue s_ros_cmd_mq;
static rt_uint8_t s_ros_cmd_pool[CONTROL_ROS_CMD_QUEUE_DEPTH * sizeof(control_ros_command_t)];

static rt_bool_t s_is_inited = RT_FALSE;
static rt_uint8_t s_tx_seq = 0U;

static control_emg_report_t s_emg_report;
static control_heart_report_t s_heart_report;
static control_ros_command_t s_last_ros_cmd;
static control_motor_probe_report_t s_last_motor_probe;
static control_motor_param_report_t s_last_motor_param;
static control_motor_feedback_t s_motor_feedback[CONTROL_MOTOR_JOINT_COUNT];
static rt_bool_t s_motor_probe_pending = RT_FALSE;
static rt_uint8_t s_motor_probe_expected_id = 0U;

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

static rt_uint8_t ctrl_motor_id_by_joint(rt_uint8_t joint_id)
{
    if ((joint_id == 0U) || (joint_id > CONTROL_MOTOR_JOINT_COUNT))
    {
        return 0U;
    }

    return s_joint_motor_map[joint_id - 1U];
}

static int ctrl_motor_index_by_motor_id(rt_uint8_t motor_id)
{
    rt_uint8_t i;

    for (i = 0U; i < CONTROL_MOTOR_JOINT_COUNT; i++)
    {
        if (s_joint_motor_map[i] == motor_id)
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

    if ((s_can_dev == RT_NULL) || (data == RT_NULL) || (len > 8U))
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
    rt_memcpy(msg.data, data, len);

#if CONTROL_CAN_USE_DIRECT_PDL
    written = ifx_can_direct_send(&msg);
    return (written == RT_EOK) ? RT_EOK : -RT_ERROR;
#else
    written = rt_device_write(s_can_dev, 0, &msg, sizeof(msg));
    return (written == sizeof(msg)) ? RT_EOK : -RT_ERROR;
#endif
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

static void ctrl_enqueue_ros_command(const control_ros_command_t *cmd)
{
    if (cmd == RT_NULL)
    {
        return;
    }

    if (rt_mq_send(&s_ros_cmd_mq, (void *)cmd, sizeof(*cmd)) != RT_EOK)
    {
        rt_kprintf("[control] ros command queue full, command dropped\n");
    }
}

static rt_bool_t ctrl_handle_nanopi_heartbeat(const struct rt_can_msg *msg)
{
    rt_uint8_t payload[8] = {0};
    rt_uint32_t tick;

    if ((msg == RT_NULL) || (msg->ide != RT_CAN_STDID) ||
        (msg->id != CONTROL_CAN_ID_NANOPI_HEARTBEAT))
    {
        return RT_FALSE;
    }

    tick = rt_tick_get();
    payload[0] = 0xA5U;
    payload[1] = (msg->len > 0U) ? msg->data[0] : 0U;
    payload[2] = CONTROL_MOTOR_JOINT_COUNT;
    payload[3] = 0U;
    payload[4] = (rt_uint8_t)(tick & 0xFFU);
    payload[5] = (rt_uint8_t)((tick >> 8) & 0xFFU);
    payload[6] = (rt_uint8_t)((tick >> 16) & 0xFFU);
    payload[7] = (rt_uint8_t)((tick >> 24) & 0xFFU);

    (void)ctrl_can_send(CONTROL_CAN_ID_M33_STATUS, RT_CAN_STDID, payload, sizeof(payload));
    return RT_TRUE;
}

static void ctrl_handle_can_message(const struct rt_can_msg *msg)
{
    control_ros_command_t ros_cmd;

    if (ctrl_handle_nanopi_heartbeat(msg))
    {
        return;
    }

    if (ctrl_parse_ros_command_can(msg, &ros_cmd))
    {
        ctrl_enqueue_ros_command(&ros_cmd);
        return;
    }

    if (msg->ide == RT_CAN_EXTID)
    {
        ctrl_update_motor_probe_private(msg);
        ctrl_update_motor_param_private(msg);
        ctrl_update_motor_feedback_private(msg);
        return;
    }

    if (msg->id == CONTROL_CAN_ID_EMG_REPORT)
    {
        ctrl_update_emg_report(msg);
    }
    else if (msg->id == CONTROL_CAN_ID_HEART_REPORT)
    {
        ctrl_update_heart_report(msg);
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
    if (cmd == RT_NULL)
    {
        return -RT_EINVAL;
    }

    switch (cmd->command)
    {
    case CONTROL_ROS_CMD_ENABLE:
        return control_motor_enable(cmd->joint_id);

    case CONTROL_ROS_CMD_STOP:
        return control_motor_stop(cmd->joint_id, cmd->clear_fault ? RT_TRUE : RT_FALSE);

    case CONTROL_ROS_CMD_SET_TARGET:
        return control_joint_motor_set_target(cmd->joint_id,
                                              cmd->target_pos_01deg,
                                              cmd->target_vel_rpm,
                                              cmd->target_torque_ma,
                                              RT_TRUE);

    case CONTROL_ROS_CMD_SET_MODE:
        return control_motor_set_run_mode(cmd->joint_id, (control_motor_run_mode_t)cmd->mode);

    case CONTROL_ROS_CMD_SET_ZERO:
        return control_motor_set_zero(cmd->joint_id);

    case CONTROL_ROS_CMD_SET_ACTIVE_REPORT:
        return control_motor_set_active_report(cmd->joint_id, cmd->active_report_enable ? RT_TRUE : RT_FALSE);

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

    s_is_inited = RT_TRUE;
    rt_thread_startup(s_can_rx_thread);
    rt_thread_startup(s_ros_cmd_thread);

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
    if (motor_id == 0U)
    {
        return -RT_EINVAL;
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
    if (motor_id == 0U)
    {
        return -RT_EINVAL;
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
    if (motor_id == 0U)
    {
        return -RT_EINVAL;
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
    if (motor_id == 0U)
    {
        return -RT_EINVAL;
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
    if (motor_id == 0U)
    {
        return -RT_EINVAL;
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
    if (motor_id == 0U)
    {
        return -RT_EINVAL;
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
    if (motor_id == 0U)
    {
        return -RT_EINVAL;
    }

    idx = ctrl_motor_index_by_motor_id(motor_id);
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
    if (motor_id == 0U)
    {
        return -RT_EINVAL;
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
    if (motor_id == 0U)
    {
        return -RT_EINVAL;
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

rt_err_t control_motor_speed_control(rt_uint8_t joint_id, float speed_rad_s, float limit_cur)
{
    rt_err_t ret;

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
}

rt_err_t control_motor_position_control(rt_uint8_t joint_id, float pos_rad, float limit_spd, rt_bool_t csp_mode)
{
    rt_err_t ret;
    control_motor_run_mode_t mode = csp_mode ? CONTROL_MOTOR_RUN_MODE_CSP : CONTROL_MOTOR_RUN_MODE_PP;

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
        ret = control_motor_write_parameter(joint_id, MOTOR_PARAM_INDEX_LIMIT_SPD, limit_spd, RT_FALSE);
        if (ret != RT_EOK)
        {
            return ret;
        }
    }
    else
    {
        ret = control_motor_write_parameter(joint_id, MOTOR_PARAM_INDEX_PP_VEL_MAX, limit_spd, RT_FALSE);
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
    return control_motor_write_parameter(joint_id, MOTOR_PARAM_INDEX_LOC_REF, pos_rad, RT_FALSE);
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

        ret = control_motor_write_parameter(ctx->joint_id,
                                            MOTOR_PARAM_INDEX_SPD_REF,
                                            ctx->speed_rad_s,
                                            RT_FALSE);
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
    float vel_rad_s;
    float torque_nm;

    if (!enable)
    {
        return control_motor_stop(joint_id, RT_FALSE);
    }

    pos_rad = ((float)target_pos_01deg) * 0.1f * RT_PI / 180.0f;
    vel_rad_s = ((float)target_vel_rpm) * 2.0f * RT_PI / 60.0f;

    /* Compatibility assumption: 1000 mA ~= 1 N.m */
    torque_nm = ((float)target_torque_ma) / 1000.0f;

    (void)control_motor_enable(joint_id);
    return control_motor_private_control(joint_id,
                                         pos_rad,
                                         vel_rad_s,
                                         CONTROL_MOTOR_DEFAULT_KP,
                                         CONTROL_MOTOR_DEFAULT_KD,
                                         torque_nm);
}

rt_err_t control_joint_motor_stop(rt_uint8_t joint_id)
{
    return control_motor_stop(joint_id, RT_FALSE);
}

rt_err_t control_sensor_report_enable(rt_bool_t enable, rt_uint16_t period_ms)
{
    rt_uint8_t payload[8] = {0};

    if (!s_is_inited)
    {
        return -RT_ERROR;
    }

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

#ifdef RT_USING_FINSH
#include <finsh.h>

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

    rt_kprintf("MOTOR[%d]: id=%u mode=%u fault=0x%02X pos_mrad=%d vel_mrad_s=%d tor_mNm=%d temp_dC=%d tick=%u\n",
               joint,
               fb.motor_id,
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
#endif
