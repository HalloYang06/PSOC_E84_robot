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

static rt_err_t m55qa_send_voice_config(voice_config_key_t key, const char *value)
{
    m33_m55_message_t msg;

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_VOICE_CONFIG;
    msg.payload.voice_config.key = (rt_uint32_t)key;
    if (value != RT_NULL)
    {
        rt_strncpy(msg.payload.voice_config.value,
                   value,
                   sizeof(msg.payload.voice_config.value) - 1);
    }
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
    voice_status_msg_t voice_status;
    rt_uint32_t voice_status_seq = 0U;
    rt_tick_t voice_status_timestamp = 0U;
    rt_bool_t has_voice_status;

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

    rt_memset(&voice_status, 0, sizeof(voice_status));
    has_voice_status = m55_model_bridge_get_voice_status(&voice_status,
                                                         &voice_status_seq,
                                                         &voice_status_timestamp);
    if (has_voice_status)
    {
        rt_kprintf("[m55qa] voice_status seq=%lu flags=0x%lx frames=%lu windows=%lu detected=%lu pcm_seq=%lu len=%lu peak=%lu avg=%lu active=%lu/%lu wake_stage=%lu err=%ld age_ticks=%lu\n",
                   (unsigned long)voice_status_seq,
                   (unsigned long)voice_status.flags,
                   (unsigned long)voice_status.submitted_frames,
                   (unsigned long)voice_status.processed_windows,
                   (unsigned long)voice_status.detected_count,
                   (unsigned long)voice_status.latest_pcm_seq,
                   (unsigned long)voice_status.latest_pcm_len,
                   (unsigned long)voice_status.latest_peak,
                   (unsigned long)voice_status.latest_avg_abs,
                   (unsigned long)voice_status.latest_active_frames,
                   (unsigned long)voice_status.latest_total_frames,
                   (unsigned long)voice_status.wake_stage,
                   (long)voice_status.last_error,
                   (unsigned long)(rt_tick_get() - voice_status_timestamp));
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

static void m55qa_xz_url(int argc, char **argv)
{
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("[m55qa] usage: m55qa_xz_url <ws://host:port/path>\n");
        return;
    }

    ret = m55qa_send_voice_config(VOICE_CONFIG_XIAOZHI_URL, argv[1]);
    rt_kprintf("[m55qa] xz_url ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_xz_url, Set CM55 Xiaozhi websocket URL);

static void m55qa_xz_token(int argc, char **argv)
{
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("[m55qa] usage: m55qa_xz_token <platform_token>\n");
        return;
    }

    ret = m55qa_send_voice_config(VOICE_CONFIG_XIAOZHI_TOKEN, argv[1]);
    rt_kprintf("[m55qa] xz_token ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_xz_token, Set CM55 Xiaozhi platform token);

static void m55qa_xz_reconnect(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_config(VOICE_CONFIG_XIAOZHI_RECONNECT, "");
    rt_kprintf("[m55qa] xz_reconnect ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_xz_reconnect, Reconnect CM55 Xiaozhi websocket);
