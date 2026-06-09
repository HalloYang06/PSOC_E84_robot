#include "m55_qa_bridge.h"

#include "common/m33_m55_comm.h"
#include "m55_model_bridge.h"

#include <finsh.h>

static rt_err_t m55qa_send_voice_control(voice_control_cmd_t cmd)
{
    m33_m55_message_t msg;

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_VOICE_CONTROL;
    msg.payload.voice_control.cmd = (rt_uint32_t)cmd;
    return m33_m55_comm_publish(&msg);
}

rt_err_t m55_qa_bridge_init(void)
{
    return RT_EOK;
}

static void m55qa_status(int argc, char **argv)
{
    rt_uint32_t seq = 0U;
    rt_uint8_t model_code = 0U;
    rt_uint8_t result_code = 0U;
    rt_uint16_t confidence = 0U;
    rt_uint8_t flags = 0U;
    rt_uint16_t window_ms = 0U;
    rt_tick_t timestamp = 0U;
    rt_bool_t has_model;
    rt_uint32_t ack_seq = 0U;
    rt_uint32_t ack_cmd = 0U;
    rt_int32_t ack_result = 0;
    rt_uint32_t ack_m55_tick = 0U;
    rt_tick_t ack_timestamp = 0U;
    rt_bool_t has_ack;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    has_model = m55_model_bridge_get_snapshot(&seq,
                                              &model_code,
                                              &result_code,
                                              &confidence,
                                              &flags,
                                              &window_ms,
                                              &timestamp);
    rt_kprintf("[m55qa] ipc_ready=%d tx_pending=%lu rx_pending=%lu has_model=%d\n",
               m33_m55_comm_is_ready() ? 1 : 0,
               (unsigned long)m33_m55_comm_tx_count(),
               (unsigned long)m33_m55_comm_rx_count(),
               has_model ? 1 : 0);
    if (has_model)
    {
        rt_kprintf("[m55qa] model seq=%lu code=%u result=%u conf=%u/1000 flags=0x%02x window_ms=%u age_ticks=%lu\n",
                   (unsigned long)seq,
                   model_code,
                   result_code,
                   confidence,
                   flags,
                   window_ms,
                   (unsigned long)(rt_tick_get() - timestamp));
    }

    has_ack = m55_model_bridge_get_voice_ack(&ack_seq,
                                             &ack_cmd,
                                             &ack_result,
                                             &ack_m55_tick,
                                             &ack_timestamp);
    if (has_ack)
    {
        rt_kprintf("[m55qa] voice_ack seq=%lu cmd=%lu result=%ld m55_tick=%lu age_ticks=%lu\n",
                   (unsigned long)ack_seq,
                   (unsigned long)ack_cmd,
                   (long)ack_result,
                   (unsigned long)ack_m55_tick,
                   (unsigned long)(rt_tick_get() - ack_timestamp));
    }
}
MSH_CMD_EXPORT(m55qa_status, Show CM55 IPC and latest AI/wake state);

static void m55qa_wake_on(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control(VOICE_CTRL_START_LISTEN);
    rt_kprintf("[m55qa] wake_on ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_wake_on, Request CM55 wake-word listening);

static void m55qa_wake_off(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control(VOICE_CTRL_STOP_LISTEN);
    rt_kprintf("[m55qa] wake_off ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_wake_off, Stop CM55 wake-word listening);

static void m55qa_capture_on(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control(VOICE_CTRL_START_CAPTURE);
    rt_kprintf("[m55qa] capture_on ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_capture_on, Request voice capture through existing voice path);

static void m55qa_capture_off(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control(VOICE_CTRL_STOP_CAPTURE);
    rt_kprintf("[m55qa] capture_off ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_capture_off, Stop voice capture through existing voice path);
