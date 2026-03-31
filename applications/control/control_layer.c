#include <rtthread.h>
#include <rtdevice.h>
#include <drivers/can.h>
#include <stdlib.h>
#include <string.h>

#include "control_layer.h"
#include "control_layer_cfg.h"

#ifndef RT_PI
#define RT_PI 3.14159265358979323846f
#endif

#if (CONTROL_MOTOR_JOINT_COUNT < 1U) || (CONTROL_MOTOR_JOINT_COUNT > 5U)
#error "CONTROL_MOTOR_JOINT_COUNT must be within [1, 5]."
#endif

#define MOTOR_PRIVATE_TYPE_CTRL            0x01U
#define MOTOR_PRIVATE_TYPE_FEEDBACK        0x02U
#define MOTOR_PRIVATE_TYPE_ENABLE          0x03U
#define MOTOR_PRIVATE_TYPE_STOP            0x04U
#define MOTOR_PRIVATE_TYPE_SET_ZERO        0x06U
#define MOTOR_PRIVATE_TYPE_PARAM_WRITE     0x12U
#define MOTOR_PRIVATE_TYPE_ACTIVE_REPORT   0x18U

#define MOTOR_PARAM_INDEX_RUN_MODE         0x7005U

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
static control_motor_feedback_t s_motor_feedback[CONTROL_MOTOR_JOINT_COUNT];

static const rt_uint8_t s_joint_motor_map[5] =
{
    (rt_uint8_t)CONTROL_MOTOR_JOINT1_ID,
    (rt_uint8_t)CONTROL_MOTOR_JOINT2_ID,
    (rt_uint8_t)CONTROL_MOTOR_JOINT3_ID,
    (rt_uint8_t)CONTROL_MOTOR_JOINT4_ID,
    (rt_uint8_t)CONTROL_MOTOR_JOINT5_ID,
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

    written = rt_device_write(s_can_dev, 0, &msg, sizeof(msg));
    return (written == sizeof(msg)) ? RT_EOK : -RT_ERROR;
}

static void ctrl_update_emg_report(const struct rt_can_msg *msg)
{
    control_emg_report_t tmp;

    if (msg->len < 6U)
    {
        return;
    }

    tmp.ch1_raw = ctrl_u16_from_le(&msg->data[0]);
    tmp.ch2_raw = ctrl_u16_from_le(&msg->data[2]);
    tmp.rms_raw = ctrl_u16_from_le(&msg->data[4]);
    tmp.seq = (msg->len > 6U) ? msg->data[6] : 0U;
    tmp.status = (msg->len > 7U) ? msg->data[7] : 0U;
    tmp.timestamp = rt_tick_get();

    rt_mutex_take(&s_data_lock, RT_WAITING_FOREVER);
    s_emg_report = tmp;
    rt_mutex_release(&s_data_lock);
}

static void ctrl_update_heart_report(const struct rt_can_msg *msg)
{
    control_heart_report_t tmp;

    if (msg->len < 2U)
    {
        return;
    }

    tmp.bpm = ctrl_u16_from_le(&msg->data[0]);
    tmp.hrv_ms = (msg->len >= 4U) ? ctrl_u16_from_le(&msg->data[2]) : 0U;
    tmp.signal_quality = (msg->len >= 5U) ? msg->data[4] : 0U;
    tmp.status = (msg->len >= 6U) ? msg->data[5] : 0U;
    tmp.timestamp = rt_tick_get();

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

static void ctrl_handle_can_message(const struct rt_can_msg *msg)
{
    control_ros_command_t ros_cmd;

    if (ctrl_parse_ros_command_can(msg, &ros_cmd))
    {
        ctrl_enqueue_ros_command(&ros_cmd);
        return;
    }

    if (msg->ide == RT_CAN_EXTID)
    {
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

static rt_err_t ctrl_can_rx_indicate(rt_device_t dev, rt_size_t size)
{
    RT_UNUSED(dev);
    RT_UNUSED(size);

    rt_sem_release(&s_can_rx_sem);
    return RT_EOK;
}

static void ctrl_can_rx_entry(void *parameter)
{
    struct rt_can_msg msg;

    RT_UNUSED(parameter);

    while (1)
    {
        if (rt_sem_take(&s_can_rx_sem, RT_WAITING_FOREVER) != RT_EOK)
        {
            continue;
        }

        while (rt_device_read(s_can_dev, 0, &msg, sizeof(msg)) == sizeof(msg))
        {
            ctrl_handle_can_message(&msg);
        }
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
    rt_uint16_t open_flags;
    const char *dev_name = can_name;

    if (s_is_inited)
    {
        return RT_EOK;
    }

    if ((dev_name == RT_NULL) || (dev_name[0] == '\0'))
    {
        dev_name = CONTROL_CAN_DEV_DEFAULT;
    }

    s_can_dev = rt_device_find(dev_name);
    if (s_can_dev == RT_NULL)
    {
        rt_kprintf("[control] can device %s not found\n", dev_name);
        return -RT_ERROR;
    }

    result = rt_sem_init(&s_can_rx_sem, "c_rx", 0, RT_IPC_FLAG_FIFO);
    if (result != RT_EOK)
    {
        return result;
    }

    result = rt_mutex_init(&s_data_lock, "c_lock", RT_IPC_FLAG_PRIO);
    if (result != RT_EOK)
    {
        rt_sem_detach(&s_can_rx_sem);
        return result;
    }

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

    open_flags = (rt_uint16_t)(RT_DEVICE_FLAG_RDWR | RT_DEVICE_FLAG_INT_RX | RT_DEVICE_FLAG_INT_TX);
    result = rt_device_open(s_can_dev, open_flags);
    if ((result != RT_EOK) && (result != -RT_EBUSY))
    {
        rt_mq_detach(&s_ros_cmd_mq);
        rt_mutex_detach(&s_data_lock);
        rt_sem_detach(&s_can_rx_sem);
        s_can_dev = RT_NULL;
        return result;
    }

    rt_device_set_rx_indicate(s_can_dev, ctrl_can_rx_indicate);

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

    s_is_inited = RT_TRUE;
    rt_thread_startup(s_can_rx_thread);
    rt_thread_startup(s_ros_cmd_thread);

    (void)control_sensor_report_enable(RT_TRUE, CONTROL_SENSOR_DEFAULT_PERIOD_MS);

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

static int cmd_motor_fb(int argc, char **argv)
{
    control_motor_feedback_t fb;
    rt_uint8_t joint;

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

    rt_kprintf("MOTOR[%d]: id=%u mode=%u fault=0x%02X pos=%.3f rad vel=%.3f rad/s tor=%.3f Nm temp=%.1f C tick=%u\n",
               joint,
               fb.motor_id,
               fb.mode_state,
               fb.fault_summary,
               fb.pos_rad,
               fb.vel_rad_s,
               fb.torque_nm,
               fb.temp_c,
               fb.timestamp);
    return 0;
}
MSH_CMD_EXPORT(cmd_motor_fb, show motor latest feedback);

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
