#include <rtthread.h>
#include <rtdevice.h>
#include <drivers/can.h>
#include <stdlib.h>
#include <string.h>

#include "sensor.h"
#include "control_layer_cfg.h"

/*
 * 传感器子模块职责：
 * - 解析旧版 EMG/心率 CAN 帧，以及 F103/C8T6 传感节点 0x7C1~0x7C3 帧。
 * - 用独立互斥锁缓存最近一次肌电、心率、F103 传感/健康/ACK 数据。
 * - 通过 control_layer.c 注册进来的 CAN 发送回调下发 F103 控制命令。
 * - 注册传感器调试命令：sensor_show、sensor_rate、f103_ping。
 *
 * 本文件不负责电机反馈、ROS 命令安全审核、CAN RX 线程调度。
 * 这些仍留在 control_layer.c，保证正式运动链路和安全状态机集中管理。
 */

/* 传感器缓存锁：保护 s_emg_report、s_heart_report、s_sensor_node_sample。 */
static struct rt_mutex s_sensor_lock;
/* 模块初始化标志：只有初始化成功后，查询 API 和发帧 API 才允许工作。 */
static rt_bool_t s_sensor_is_inited = RT_FALSE;
/* CAN 发送回调：由 control_layer.c 注册，实际调用 ctrl_can_send()。 */
static control_sensor_can_send_fn s_sensor_can_send = RT_NULL;
/* TX 序号回调：由 control_layer.c 注册，保持旧逻辑中的 s_tx_seq++ 顺序。 */
static control_sensor_next_seq_fn s_sensor_next_seq = RT_NULL;

/* 最近一次肌电兼容报告，供 control_get_emg_report() 读取。 */
static control_emg_report_t s_emg_report;
/* 最近一次心率兼容报告，供 control_get_heart_report() 读取。 */
static control_heart_report_t s_heart_report;
/* 最近一次 F103/C8T6 综合节点样本，供 control_get_sensor_node_sample() 读取。 */
static control_sensor_node_sample_t s_sensor_node_sample;

/* 从小端字节流读取 uint16。F103 数据帧和旧心率帧均使用小端。 */
static rt_uint16_t sensor_u16_from_le(const rt_uint8_t *buf)
{
    return (rt_uint16_t)((rt_uint16_t)buf[0] | ((rt_uint16_t)buf[1] << 8));
}

/* 从小端字节流读取 int16，用于 F103 emg_filt。 */
static rt_int16_t sensor_i16_from_le(const rt_uint8_t *buf)
{
    return (rt_int16_t)sensor_u16_from_le(buf);
}

/* float 缩放到 int32，保持旧 control_layer.c 中四舍五入行为不变。 */
static rt_int32_t sensor_float_to_scaled_i32(float value, float scale)
{
    float scaled = value * scale;

    if (scaled >= 0.0f)
    {
        return (rt_int32_t)(scaled + 0.5f);
    }

    return (rt_int32_t)(scaled - 0.5f);
}

/* 获取下一帧控制序号。回调未注册时返回 0，避免空指针。 */
static rt_uint8_t sensor_next_seq(void)
{
    if (s_sensor_next_seq == RT_NULL)
    {
        return 0U;
    }

    return s_sensor_next_seq();
}

/* 通过 control_layer.c 的 CAN 出口发帧。传感器模块自身不直接操作 CAN 设备。 */
static rt_err_t sensor_send(rt_uint32_t id, rt_uint8_t ide, const rt_uint8_t *data, rt_uint8_t len)
{
    if (s_sensor_can_send == RT_NULL)
    {
        return -RT_ERROR;
    }

    return s_sensor_can_send(id, ide, data, len);
}

/* 初始化传感器模块。
 * 第一次调用会创建互斥锁；重复调用只刷新回调函数。
 */
rt_err_t control_sensor_module_init(control_sensor_can_send_fn send_fn,
                                    control_sensor_next_seq_fn next_seq_fn)
{
    rt_err_t ret;

    if (s_sensor_is_inited)
    {
        s_sensor_can_send = send_fn;
        s_sensor_next_seq = next_seq_fn;
        return RT_EOK;
    }

    ret = rt_mutex_init(&s_sensor_lock, "sen_lock", RT_IPC_FLAG_PRIO);
    if (ret != RT_EOK)
    {
        return ret;
    }

    s_sensor_can_send = send_fn;
    s_sensor_next_seq = next_seq_fn;
    s_sensor_is_inited = RT_TRUE;
    return RT_EOK;
}

/* 解析旧版 EMG 报告帧。
 * 帧格式：data[0..3] 为 float ch1_mv，data[4..7] 为 float ch2_mv。
 * 行为保持旧版不变：负值钳到 0，rms_raw 取两个通道平均值。
 */
void control_sensor_update_emg_report(const struct rt_can_msg *msg)
{
    /* tmp 是栈上临时对象，解析完整后一次性写入全局缓存，避免读者看到半更新状态。 */
    control_emg_report_t tmp;
    /* 旧版 EMG 帧直接传两个 float，单位按发送端约定理解为 mV/缩放值。 */
    float ch1_mv;
    float ch2_mv;
    /* 当前没有真正 RMS 窗口计算，沿用旧逻辑：两个通道平均值作为强度。 */
    float rms_mv;

    if ((msg == RT_NULL) || (msg->len < 8U))
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

    tmp.ch1_raw = (rt_uint16_t)sensor_float_to_scaled_i32(ch1_mv, 1.0f);
    tmp.ch2_raw = (rt_uint16_t)sensor_float_to_scaled_i32(ch2_mv, 1.0f);
    tmp.rms_raw = (rt_uint16_t)sensor_float_to_scaled_i32(rms_mv, 1.0f);
    tmp.seq = 0U;
    tmp.status = 0U;
    tmp.timestamp = rt_tick_get();

    rt_mutex_take(&s_sensor_lock, RT_WAITING_FOREVER);
    s_emg_report = tmp;
    rt_mutex_release(&s_sensor_lock);
}

/* 解析旧版心率报告帧。
 * 帧格式：data[0..1]=bpm，data[2..3]=hrv_ms，data[4..7]=旧时间戳。
 * 当前旧时间戳只读取后丢弃，缓存时间使用本机 rt_tick_get()，保持旧行为。
 */
void control_sensor_update_heart_report(const struct rt_can_msg *msg)
{
    control_heart_report_t tmp;
    rt_uint32_t timestamp_ms;

    if ((msg == RT_NULL) || (msg->len < 8U))
    {
        return;
    }

    tmp.bpm = sensor_u16_from_le(&msg->data[0]);
    tmp.hrv_ms = sensor_u16_from_le(&msg->data[2]);
    timestamp_ms = (rt_uint32_t)msg->data[4] |
                   ((rt_uint32_t)msg->data[5] << 8) |
                   ((rt_uint32_t)msg->data[6] << 16) |
                   ((rt_uint32_t)msg->data[7] << 24);
    tmp.signal_quality = (tmp.hrv_ms > 0U) ? 100U : 0U;
    tmp.status = 0U;
    tmp.timestamp = rt_tick_get();
    RT_UNUSED(timestamp_ms);

    rt_mutex_take(&s_sensor_lock, RT_WAITING_FOREVER);
    s_heart_report = tmp;
    rt_mutex_release(&s_sensor_lock);
}

/* 解析 F103/C8T6 传感帧 0x7C2。
 * 帧格式：
 * - data[0..1] emg_raw
 * - data[2..3] emg_filt
 * - data[4..5] hr_raw
 * - data[6]    hr_filt
 * - data[7]    flags
 * 同时更新三个缓存：
 * 1. control_sensor_node_sample_t 原始节点缓存。
 * 2. control_emg_report_t 兼容肌电缓存。
 * 3. control_heart_report_t 兼容心率缓存。
 */
void control_sensor_update_f103_sensor_report(const struct rt_can_msg *msg)
{
    /* node 保存 F103 原始综合样本；emg/heart 是给旧接口兼容使用的派生缓存。 */
    control_sensor_node_sample_t node;
    control_emg_report_t emg;
    control_heart_report_t heart;
    /* 0x7C2 原始字段。 */
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

    emg_raw = sensor_u16_from_le(&msg->data[0]);
    emg_filt = sensor_i16_from_le(&msg->data[2]);
    hr_raw = sensor_u16_from_le(&msg->data[4]);
    hr_filt = msg->data[6];
    flags = msg->data[7];
    now = rt_tick_get();

    /* 同一把锁内更新三个缓存，保证调用者读取时看到的是同一帧派生出来的数据。 */
    rt_mutex_take(&s_sensor_lock, RT_WAITING_FOREVER);
    node = s_sensor_node_sample;
    node.emg_raw = emg_raw;
    node.emg_filt = emg_filt;
    node.hr_raw = hr_raw;
    node.hr_filt = hr_filt;
    node.flags = flags;
    node.sensor_timestamp = now;
    s_sensor_node_sample = node;

    /* 兼容旧 EMG 报告：把滤波肌电的绝对值放到 ch2/rms，便于旧显示逻辑直接看强度。 */
    emg_filt_abs = (emg_filt < 0) ? -(rt_int32_t)emg_filt : (rt_int32_t)emg_filt;
    emg.ch1_raw = emg_raw;
    emg.ch2_raw = (rt_uint16_t)((emg_filt_abs > 65535) ? 65535 : emg_filt_abs);
    emg.rms_raw = emg.ch2_raw;
    emg.seq = 0U;
    emg.status = flags;
    emg.timestamp = now;
    s_emg_report = emg;

    /* 兼容旧心率报告：hr_filt 作为 bpm，hr_raw 暂存到 hrv_ms 字段。 */
    heart.bpm = hr_filt;
    heart.hrv_ms = hr_raw;
    heart.signal_quality = (flags & 0x02U) ? 100U : 0U;
    heart.status = flags;
    heart.timestamp = now;
    s_heart_report = heart;
    rt_mutex_release(&s_sensor_lock);
}

/* 解析 F103/C8T6 健康帧 0x7C3。
 * 帧格式：data[0]=node_state，data[1..2]=node_err_cnt，data[3]=node_q_fill。
 */
void control_sensor_update_f103_health_report(const struct rt_can_msg *msg)
{
    control_sensor_node_sample_t node;

    if ((msg == RT_NULL) || (msg->len < 8U))
    {
        return;
    }

    rt_mutex_take(&s_sensor_lock, RT_WAITING_FOREVER);
    node = s_sensor_node_sample;
    node.node_state = msg->data[0];
    node.node_err_cnt = sensor_u16_from_le(&msg->data[1]);
    node.node_q_fill = msg->data[3];
    node.health_timestamp = rt_tick_get();
    s_sensor_node_sample = node;
    rt_mutex_release(&s_sensor_lock);
}

/* 解析 F103/C8T6 ACK 帧 0x7C1。
 * 帧格式：data[0]=cmd，data[1]=seq，data[2]=status。
 */
void control_sensor_update_f103_ack_report(const struct rt_can_msg *msg)
{
    control_sensor_node_sample_t node;

    if ((msg == RT_NULL) || (msg->len < 3U))
    {
        return;
    }

    rt_mutex_take(&s_sensor_lock, RT_WAITING_FOREVER);
    node = s_sensor_node_sample;
    node.last_ack_cmd = msg->data[0];
    node.last_ack_seq = msg->data[1];
    node.last_ack_status = msg->data[2];
    node.ack_timestamp = rt_tick_get();
    s_sensor_node_sample = node;
    rt_mutex_release(&s_sensor_lock);
}

/* 配置传感器上报。
 * 发送顺序保持旧 control_layer.c 行为不变：
 * 1. 给 F103 发送 SET_RATE，设置 CAN 上报速率。
 * 2. 给 F103 发送 START_STREAM 或 STOP_STREAM。
 * 3. 给旧传感控制 CAN ID 发送 ENABLE_REPORT 兼容帧。
 */
rt_err_t control_sensor_report_enable(rt_bool_t enable, rt_uint16_t period_ms)
{
    rt_uint8_t payload[8] = {0};
    rt_uint16_t rate_hz;
    rt_err_t ret;

    if (!s_sensor_is_inited)
    {
        return -RT_ERROR;
    }

    if (period_ms == 0U)
    {
        /* period_ms=0 表示使用默认周期，保持旧接口容错行为。 */
        period_ms = CONTROL_SENSOR_DEFAULT_PERIOD_MS;
    }

    /* F103 接口按 Hz 配置上报频率，旧上层接口按周期 ms 配置。 */
    rate_hz = (rt_uint16_t)(1000U / period_ms);
    if (rate_hz == 0U)
    {
        rate_hz = 1U;
    }

    payload[0] = CONTROL_F103_CMD_SET_RATE;          /* 命令：设置 F103 上报速率。 */
    payload[1] = sensor_next_seq();                  /* 命令序号，用于匹配 ACK。 */
    payload[2] = CONTROL_F103_RATE_TARGET_CAN_TX;    /* 目标：CAN TX 上报频率。 */
    payload[3] = (rt_uint8_t)(rate_hz & 0xFFU);      /* rate_hz 小端低字节。 */
    payload[4] = (rt_uint8_t)((rate_hz >> 8) & 0xFFU); /* rate_hz 小端高字节。 */
    ret = sensor_send(CONTROL_CAN_ID_F103_CTRL, RT_CAN_STDID, payload, sizeof(payload));
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_memset(payload, 0, sizeof(payload));
    payload[0] = enable ? CONTROL_F103_CMD_START_STREAM : CONTROL_F103_CMD_STOP_STREAM; /* 开/停流。 */
    payload[1] = sensor_next_seq();                                                     /* 命令序号。 */
    ret = sensor_send(CONTROL_CAN_ID_F103_CTRL, RT_CAN_STDID, payload, sizeof(payload));
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_memset(payload, 0, sizeof(payload));
    payload[0] = CONTROL_SENSOR_CMD_ENABLE_REPORT;              /* 旧传感控制协议：上报开关。 */
    payload[1] = enable ? 1U : 0U;                              /* 1=启用，0=关闭。 */
    payload[2] = (rt_uint8_t)(period_ms & 0xFFU);               /* period_ms 小端低字节。 */
    payload[3] = (rt_uint8_t)((period_ms >> 8) & 0xFFU);        /* period_ms 小端高字节。 */
    payload[7] = sensor_next_seq();                             /* 旧协议序号字段。 */

    return sensor_send(CONTROL_CAN_ID_SENSOR_CTRL, RT_CAN_STDID, payload, sizeof(payload));
}

/* 读取最近一次肌电兼容缓存。 */
rt_err_t control_get_emg_report(control_emg_report_t *out)
{
    if ((out == RT_NULL) || (!s_sensor_is_inited))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_sensor_lock, RT_WAITING_FOREVER);
    *out = s_emg_report;
    rt_mutex_release(&s_sensor_lock);

    return RT_EOK;
}

/* 读取最近一次心率兼容缓存。 */
rt_err_t control_get_heart_report(control_heart_report_t *out)
{
    if ((out == RT_NULL) || (!s_sensor_is_inited))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_sensor_lock, RT_WAITING_FOREVER);
    *out = s_heart_report;
    rt_mutex_release(&s_sensor_lock);

    return RT_EOK;
}

/* 读取最近一次 F103/C8T6 综合节点缓存。 */
rt_err_t control_get_sensor_node_sample(control_sensor_node_sample_t *out)
{
    if ((out == RT_NULL) || (!s_sensor_is_inited))
    {
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_sensor_lock, RT_WAITING_FOREVER);
    *out = s_sensor_node_sample;
    rt_mutex_release(&s_sensor_lock);

    return RT_EOK;
}

#ifdef RT_USING_FINSH
#include <finsh.h>

/* shell: 打印肌电、心率、F103 传感/健康/ACK 缓存，便于现场确认数据是否进入 M33。 */
static int cmd_sensor_show(int argc, char **argv)
{
    /* 三个缓存分别读取，打印出来用于判断：传感帧是否到达、健康帧是否到达、ACK 是否返回。 */
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

/* shell: 配置 F103 传感节点上报开关和周期。 */
static int cmd_sensor_rate(int argc, char **argv)
{
    /* 命令参数：sensor_rate <开关 0/1> <周期 ms>。 */
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

/* shell: 向 F103 发送 GET_STATUS，用于不启动数据流时验证 0x7C1 ACK/0x7C3 健康链路。 */
static int cmd_f103_ping(int argc, char **argv)
{
    /* 命令参数：f103_ping [次数] [间隔 ms]，只请求状态，不启动传感数据流。 */
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
        payload[1] = sensor_next_seq();
        ret = sensor_send(CONTROL_CAN_ID_F103_CTRL, RT_CAN_STDID, payload, sizeof(payload));
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
