#include "m55_model_input_bridge.h"

#include "common/m33_m55_comm.h"
#include "control/control_layer.h"

#include <stdlib.h>

#define M55_MODEL_SNAPSHOT_FLAG_VALID 0x0001U
#define M55_MODEL_SNAPSHOT_FLAG_FRESH 0x0002U
#define M55_MODEL_MOTOR7_JOINT_ID     7U

static rt_uint32_t g_m55_input_seq;

rt_err_t m55_model_input_bridge_publish_snapshot(float emg_ch1,
                                                 float emg_ch2,
                                                 rt_uint16_t heart_rate,
                                                 rt_uint16_t spo2,
                                                 float shoulder_angle,
                                                 float elbow_angle,
                                                 float lateral_position)
{
    m33_m55_message_t msg;
    rt_err_t ret;

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_SENSOR_SNAPSHOT;
    msg.seq = ++g_m55_input_seq;
    msg.payload.sensor_snapshot.source = MODEL_INPUT_SRC_EMG;
    msg.payload.sensor_snapshot.flags = M55_MODEL_SNAPSHOT_FLAG_VALID |
                                        M55_MODEL_SNAPSHOT_FLAG_FRESH;
    msg.payload.sensor_snapshot.emg_ch1 = emg_ch1;
    msg.payload.sensor_snapshot.emg_ch2 = emg_ch2;
    msg.payload.sensor_snapshot.heart_rate = heart_rate;
    msg.payload.sensor_snapshot.spo2 = spo2;
    msg.payload.sensor_snapshot.shoulder_angle = shoulder_angle;
    msg.payload.sensor_snapshot.elbow_angle = elbow_angle;
    msg.payload.sensor_snapshot.lateral_position = lateral_position;
    msg.payload.sensor_snapshot.timestamp = rt_tick_get_millisecond();

    ret = m33_m55_comm_publish(&msg);
    rt_kprintf("[m55_input] snapshot seq=%lu emg=(%d,%d) hr=%u spo2=%u ret=%d\n",
               (unsigned long)msg.seq,
               (int)(emg_ch1 * 1000.0f),
               (int)(emg_ch2 * 1000.0f),
               heart_rate,
               spo2,
               ret);
    return ret;
}

rt_err_t m55_model_input_bridge_publish_motor7_snapshot(void)
{
    control_motor_feedback_t fb;
    m33_m55_message_t msg;
    rt_tick_t now;
    rt_uint16_t flags;
    rt_bool_t fresh;
    rt_err_t ret;

    ret = control_get_motor_feedback(M55_MODEL_MOTOR7_JOINT_ID, &fb);
    if (ret != RT_EOK)
    {
        rt_kprintf("[m55_input] motor7 feedback unavailable ret=%d\n", ret);
        return ret;
    }

    now = rt_tick_get();
    fresh = ((fb.timestamp != 0U) && ((now - fb.timestamp) <= RT_TICK_PER_SECOND)) ? RT_TRUE : RT_FALSE;
    flags = M55_MODEL_SNAPSHOT_FLAG_VALID;
    if (fresh)
    {
        flags |= M55_MODEL_SNAPSHOT_FLAG_FRESH;
    }

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_SENSOR_SNAPSHOT;
    msg.seq = ++g_m55_input_seq;
    msg.payload.sensor_snapshot.source = MODEL_INPUT_SRC_MOTOR_FEEDBACK;
    msg.payload.sensor_snapshot.flags = flags;
    msg.payload.sensor_snapshot.motor_id = fb.motor_id;
    msg.payload.sensor_snapshot.emg_ch1 = fb.pos_rad;
    msg.payload.sensor_snapshot.emg_ch2 = fb.vel_rad_s;
    msg.payload.sensor_snapshot.heart_rate = fb.mode_state;
    msg.payload.sensor_snapshot.spo2 = fb.fault_summary;
    msg.payload.sensor_snapshot.shoulder_angle = fb.torque_nm;
    msg.payload.sensor_snapshot.elbow_angle = fb.temp_c;
    msg.payload.sensor_snapshot.lateral_position = (float)M55_MODEL_MOTOR7_JOINT_ID;
    msg.payload.sensor_snapshot.timestamp = rt_tick_get_millisecond();

    ret = m33_m55_comm_publish(&msg);
    rt_kprintf("[m55_input] motor7 snapshot seq=%lu motor=%u flags=0x%04x pos=%d vel=%d tq=%d temp=%d ret=%d\n",
               (unsigned long)msg.seq,
               msg.payload.sensor_snapshot.motor_id,
               flags,
               (int)(fb.pos_rad * 1000.0f),
               (int)(fb.vel_rad_s * 1000.0f),
               (int)(fb.torque_nm * 1000.0f),
               (int)(fb.temp_c * 10.0f),
               ret);
    return ret;
}

static float parse_float_arg(int argc, char **argv, int index, float fallback)
{
    if ((argc <= index) || (argv[index] == RT_NULL))
    {
        return fallback;
    }
    return (float)atof(argv[index]);
}

static rt_uint16_t parse_u16_arg(int argc, char **argv, int index, rt_uint16_t fallback)
{
    long value;

    if ((argc <= index) || (argv[index] == RT_NULL))
    {
        return fallback;
    }

    value = strtol(argv[index], RT_NULL, 0);
    if (value < 0)
    {
        return 0U;
    }
    if (value > 65535L)
    {
        return 65535U;
    }
    return (rt_uint16_t)value;
}

static void m55_snapshot_test(int argc, char **argv)
{
    float emg1 = parse_float_arg(argc, argv, 1, 0.35f);
    float emg2 = parse_float_arg(argc, argv, 2, 0.12f);
    rt_uint16_t heart_rate = parse_u16_arg(argc, argv, 3, 72U);
    rt_uint16_t spo2 = parse_u16_arg(argc, argv, 4, 98U);
    rt_err_t ret;

    ret = m55_model_input_bridge_publish_snapshot(emg1,
                                                  emg2,
                                                  heart_rate,
                                                  spo2,
                                                  0.0f,
                                                  0.0f,
                                                  0.0f);
    rt_kprintf("m55_snapshot_test ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55_snapshot_test, Publish one M33 sensor snapshot to CM55);
MSH_CMD_EXPORT_ALIAS(m55_snapshot_test, m55_snap, Publish one M33 sensor snapshot to CM55);
