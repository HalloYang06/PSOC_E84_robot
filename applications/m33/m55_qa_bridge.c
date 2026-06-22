#include "m55_qa_bridge.h"

#include "common/m33_m55_comm.h"
#include "m55_model_bridge.h"

#include <finsh.h>

static void m55qa_print_ip4(const char *label, rt_uint32_t ip)
{
    const rt_uint8_t *bytes = (const rt_uint8_t *)&ip;

    rt_kprintf("%s=%u.%u.%u.%u",
               label,
               bytes[0],
               bytes[1],
               bytes[2],
               bytes[3]);
}

static rt_err_t m55qa_send_voice_control(voice_control_cmd_t cmd)
{
    m33_m55_message_t msg;
    rt_err_t ret = -RT_ERROR;
    rt_uint32_t attempt;

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_VOICE_CONTROL;
    msg.payload.voice_control.cmd = (rt_uint32_t)cmd;
    for (attempt = 0U; attempt < 5U; attempt++)
    {
        ret = m33_m55_comm_publish(&msg);
        if (ret == RT_EOK)
        {
            return RT_EOK;
        }
        rt_thread_mdelay(50);
    }
    return ret;
}

static rt_bool_t m55qa_wait_voice_ack(voice_control_cmd_t cmd,
                                      rt_tick_t since_tick,
                                      rt_uint32_t timeout_ms,
                                      rt_int32_t *ack_result)
{
    rt_tick_t deadline = rt_tick_get() + rt_tick_from_millisecond((rt_int32_t)timeout_ms);

    while ((rt_int32_t)(deadline - rt_tick_get()) > 0)
    {
        rt_uint32_t ack_cmd = 0U;
        rt_int32_t result = 0;
        rt_tick_t timestamp = 0U;

        if (m55_model_bridge_get_voice_ack(RT_NULL, &ack_cmd, &result, RT_NULL, &timestamp) &&
            (ack_cmd == (rt_uint32_t)cmd) &&
            ((rt_int32_t)(timestamp - since_tick) >= 0))
        {
            if (ack_result != RT_NULL)
            {
                *ack_result = result;
            }
            return RT_TRUE;
        }
        rt_thread_mdelay(50);
    }

    return RT_FALSE;
}

static rt_err_t m55qa_send_voice_control_wait(voice_control_cmd_t cmd,
                                              rt_uint32_t timeout_ms,
                                              rt_int32_t *ack_result)
{
    rt_tick_t since_tick = rt_tick_get();
    rt_err_t ret = m55qa_send_voice_control(cmd);

    if (ret != RT_EOK)
    {
        return ret;
    }

    if (!m55qa_wait_voice_ack(cmd, since_tick, timeout_ms, ack_result))
    {
        return -RT_ETIMEOUT;
    }

    return RT_EOK;
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
        rt_kprintf("[m55qa] voice_status seq=%lu flags=0x%lx wake_on=%d wake_ready=%d wake_hit=%d xz_listening=%d xz_ws=%d xz_token=%d token_len=%lu staging_len=%lu frames=%lu windows=%lu detected=%lu pcm_seq=%lu len=%lu peak=%lu avg=%lu active=%lu/%lu wake_stage=%lu err=%ld xz_stage=%ld xz_errno=%ld heap=%lu/%lu max=%lu probe_or_bridge=%ld/%ld/%ld/%ld probe_lwip=%ld/%ld xz_cur=%lu/%lu xz_last=%lu/%lu xz_fail=%lu xz_rx=%lu/%lu frame_len=%lu tts_fwd=%lu/%lu tts_fail=%lu pcm_reject=%lu srv_hello=%lu srv_stt=%lu srv_tts=%lu/%lu/%lu srv_last=0x%08lx/0x%08lx srv_lens=%lu/%lu/%lu srv_err=0x%08lx/0x%08lx/0x%08lx age_ticks=%lu\n",
                   (unsigned long)voice_status_seq,
                   (unsigned long)voice_status.flags,
                   (voice_status.flags & VOICE_STATUS_FLAG_WAKE_LISTENING) ? 1 : 0,
                   (voice_status.flags & VOICE_STATUS_FLAG_WAKE_READY) ? 1 : 0,
                   (voice_status.flags & VOICE_STATUS_FLAG_LAST_WAKE) ? 1 : 0,
                   (voice_status.flags & VOICE_STATUS_FLAG_XIAOZHI_LISTENING) ? 1 : 0,
                   (voice_status.flags & VOICE_STATUS_FLAG_XIAOZHI_CONNECTED) ? 1 : 0,
                   (voice_status.flags & VOICE_STATUS_FLAG_XIAOZHI_HAS_TOKEN) ? 1 : 0,
                   (unsigned long)voice_status.xiaozhi_token_len,
                   (unsigned long)voice_status.xiaozhi_token_staging_len,
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
                   (long)voice_status.xiaozhi_ws_stage,
                   (long)voice_status.xiaozhi_ws_errno,
                   (unsigned long)voice_status.heap_used,
                   (unsigned long)voice_status.heap_total,
                   (unsigned long)voice_status.heap_max_used,
                   (long)voice_status.net_probe_posix_tcp,
                   (long)voice_status.net_probe_posix_errno,
                   (long)voice_status.net_probe_sal_tcp,
                   (long)voice_status.net_probe_sal_errno,
                   (long)voice_status.net_probe_lwip_tcp,
                   (long)voice_status.net_probe_lwip_errno,
                   (unsigned long)voice_status.xiaozhi_listening_chunks,
                   (unsigned long)voice_status.xiaozhi_listening_bytes,
                   (unsigned long)voice_status.xiaozhi_last_sent_chunks,
                   (unsigned long)voice_status.xiaozhi_last_sent_bytes,
                   (unsigned long)voice_status.xiaozhi_send_fail_count,
                   (unsigned long)voice_status.xiaozhi_rx_text_count,
                   (unsigned long)voice_status.xiaozhi_rx_binary_count,
                   (unsigned long)voice_status.xiaozhi_audio_frame_len,
                   (unsigned long)voice_status.xiaozhi_tts_forward_chunks,
                   (unsigned long)voice_status.xiaozhi_tts_forward_bytes,
                   (unsigned long)voice_status.xiaozhi_tts_forward_fail_count,
                   (unsigned long)voice_status.xiaozhi_tts_pcm_reject_count,
                   (unsigned long)voice_status.xiaozhi_server_hello_count,
                   (unsigned long)voice_status.xiaozhi_server_stt_count,
                   (unsigned long)voice_status.xiaozhi_server_tts_start_count,
                   (unsigned long)voice_status.xiaozhi_server_tts_stop_count,
                   (unsigned long)voice_status.xiaozhi_server_tts_sentence_count,
                   (unsigned long)voice_status.xiaozhi_server_last_type_code,
                   (unsigned long)voice_status.xiaozhi_server_last_state_code,
                   (unsigned long)(voice_status.xiaozhi_server_last_text_lens & 0x3ffU),
                   (unsigned long)((voice_status.xiaozhi_server_last_text_lens >> 10U) & 0x3ffU),
                   (unsigned long)((voice_status.xiaozhi_server_last_text_lens >> 20U) & 0x3ffU),
                   (unsigned long)voice_status.xiaozhi_server_last_error_code,
                   (unsigned long)voice_status.xiaozhi_server_last_reason_code,
                   0UL,
                   (unsigned long)(rt_tick_get() - voice_status_timestamp));
        rt_kprintf("[m55qa] netdev name=%s flags=0x%lx wlan=%lu ready=%lu rssi=%ld cloud_tcp=%ld/%ld wifi_diag=%ld scan=%ld whd_stage=%ld whd_result=%ld whd_flags=0x%lx saved=%lu auto=%lu storage=%ld ",
                   voice_status.netdev_name[0] ? voice_status.netdev_name : "(none)",
                   (unsigned long)voice_status.netdev_flags,
                   (unsigned long)voice_status.wlan_connected,
                   (unsigned long)voice_status.wlan_ready,
                   (long)voice_status.wlan_rssi,
                   (long)voice_status.cloud_tcp_result,
                   (long)voice_status.cloud_tcp_errno,
                   (long)voice_status.wifi_diag_result,
                   (long)voice_status.wifi_scan_count,
                   (long)voice_status.whd_stage,
                   (long)voice_status.whd_result,
                   (unsigned long)voice_status.whd_flags,
                   (unsigned long)voice_status.wifi_saved,
                   (unsigned long)voice_status.wifi_auto_connect,
                   (long)voice_status.wifi_storage_result);
        m55qa_print_ip4("ip", voice_status.netdev_ip);
        rt_kprintf(" ");
        m55qa_print_ip4("gw", voice_status.netdev_gw);
        rt_kprintf(" ");
        m55qa_print_ip4("mask", voice_status.netdev_mask);
        rt_kprintf(" ");
        m55qa_print_ip4("dns0", voice_status.netdev_dns0);
        rt_kprintf("\n");
        rt_kprintf("[m55qa] display lcd_init=%ld gfx=%ld mipi=%ld lcd_frames=%lu lcd_last=%ld lvgl_flush=%lu lvgl_last=%ld\n",
                   (long)voice_status.lcd_init_result,
                   (long)voice_status.lcd_gfx_status,
                   (long)voice_status.lcd_mipi_status,
                   (unsigned long)voice_status.lcd_frame_updates,
                   (long)voice_status.lcd_last_frame_status,
                   (unsigned long)voice_status.lvgl_flush_count,
                   (long)voice_status.lvgl_last_flush_status);
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
    rt_int32_t ack_result = 0;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control_wait(VOICE_CTRL_START_CAPTURE, 5000U, &ack_result);
    rt_kprintf("[m55qa] capture_on ret=%d ack=%ld tx_pending=%lu\n",
               ret,
               (long)ack_result,
               (unsigned long)m33_m55_comm_tx_count());
}
MSH_CMD_EXPORT(m55qa_capture_on, Request voice capture through existing voice path);

static void m55qa_capture_off(int argc, char **argv)
{
    rt_err_t ret;
    rt_int32_t ack_result = 0;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control_wait(VOICE_CTRL_STOP_CAPTURE, 5000U, &ack_result);
    rt_kprintf("[m55qa] capture_off ret=%d ack=%ld tx_pending=%lu\n",
               ret,
               (long)ack_result,
               (unsigned long)m33_m55_comm_tx_count());
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

static void m55qa_xz_token_begin(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_config(VOICE_CONFIG_XIAOZHI_TOKEN_BEGIN, "");
    rt_kprintf("[m55qa] xz_token_begin ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_xz_token_begin, Begin chunked CM55 Xiaozhi token update);

static void m55qa_xz_token_part(int argc, char **argv)
{
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("[m55qa] usage: m55qa_xz_token_part <token_chunk_48_to_60_chars>\n");
        return;
    }

    ret = m55qa_send_voice_config(VOICE_CONFIG_XIAOZHI_TOKEN_PART, argv[1]);
    rt_kprintf("[m55qa] xz_token_part ret=%d len=%lu\n",
               ret,
               (unsigned long)rt_strlen(argv[1]));
}
MSH_CMD_EXPORT(m55qa_xz_token_part, Append one chunk to CM55 Xiaozhi token);

static void m55qa_xz_token_commit(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_config(VOICE_CONFIG_XIAOZHI_TOKEN_COMMIT, "");
    rt_kprintf("[m55qa] xz_token_commit ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_xz_token_commit, Commit chunked CM55 Xiaozhi token and reconnect);

static void m55qa_xz_token_clear(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_config(VOICE_CONFIG_XIAOZHI_TOKEN_CLEAR, "");
    rt_kprintf("[m55qa] xz_token_clear ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_xz_token_clear, Clear CM55 Xiaozhi token);

static void m55qa_xz_reconnect(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_config(VOICE_CONFIG_XIAOZHI_RECONNECT, "");
    rt_kprintf("[m55qa] xz_reconnect ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_xz_reconnect, Reconnect CM55 Xiaozhi websocket);

static void m55qa_wifi_ssid(int argc, char **argv)
{
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("[m55qa] usage: m55qa_wifi_ssid <ssid>\n");
        return;
    }

    ret = m55qa_send_voice_config(VOICE_CONFIG_WIFI_SSID, argv[1]);
    rt_kprintf("[m55qa] wifi_ssid ret=%d len=%lu\n",
               ret,
               (unsigned long)rt_strlen(argv[1]));
}
MSH_CMD_EXPORT(m55qa_wifi_ssid, Set CM55 WiFi SSID in RAM);

static void m55qa_wifi_password(int argc, char **argv)
{
    rt_err_t ret;

    if (argc < 2)
    {
        rt_kprintf("[m55qa] usage: m55qa_wifi_password <password>\n");
        return;
    }

    ret = m55qa_send_voice_config(VOICE_CONFIG_WIFI_PASSWORD, argv[1]);
    rt_kprintf("[m55qa] wifi_password ret=%d len=%lu\n",
               ret,
               (unsigned long)rt_strlen(argv[1]));
}
MSH_CMD_EXPORT(m55qa_wifi_password, Set CM55 WiFi password in RAM);

static void m55qa_wifi_connect(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_config(VOICE_CONFIG_WIFI_CONNECT, "");
    rt_kprintf("[m55qa] wifi_connect ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_wifi_connect, Connect CM55 WiFi using staged SSID/password);

static void m55qa_wifi_disconnect(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_config(VOICE_CONFIG_WIFI_DISCONNECT, "");
    rt_kprintf("[m55qa] wifi_disconnect ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_wifi_disconnect, Disconnect CM55 WiFi);

static void m55qa_wifi_save(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_config(VOICE_CONFIG_WIFI_SAVE, "");
    rt_kprintf("[m55qa] wifi_save ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_wifi_save, Save CM55 WiFi credentials to local flash);

static void m55qa_wifi_forget(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_config(VOICE_CONFIG_WIFI_FORGET, "");
    rt_kprintf("[m55qa] wifi_forget ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_wifi_forget, Remove saved CM55 WiFi credentials);

static void m55qa_wifi_auto(int argc, char **argv)
{
    rt_err_t ret;
    const char *value = "1";

    if (argc >= 2)
    {
        value = (argv[1][0] == '0') ? "0" : "1";
    }

    ret = m55qa_send_voice_config(VOICE_CONFIG_WIFI_AUTO_CONNECT, value);
    rt_kprintf("[m55qa] wifi_auto ret=%d value=%s\n", ret, value);
}
MSH_CMD_EXPORT(m55qa_wifi_auto, Enable or disable CM55 saved WiFi auto-connect);

static void m55qa_net_probe(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control(VOICE_CTRL_NET_PROBE);
    rt_kprintf("[m55qa] net_probe ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_net_probe, Probe CM55 POSIX/SAL/lwIP socket creation);

static void m55qa_wifi_diag(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control(VOICE_CTRL_WIFI_DIAG);
    rt_kprintf("[m55qa] wifi_diag ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_wifi_diag, Refresh CM55 WLAN/netdev diagnostic snapshot);

static void m55qa_wifi_scan(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control(VOICE_CTRL_WIFI_SCAN);
    rt_kprintf("[m55qa] wifi_scan ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_wifi_scan, Ask CM55 to scan visible WiFi APs);

static void m55qa_whd_diag(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control(VOICE_CTRL_WHD_DIAG);
    rt_kprintf("[m55qa] whd_diag ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55qa_whd_diag, Refresh CM55 WHD init-stage diagnostic snapshot);

static void m55qa_probe_pcm_on(int argc, char **argv)
{
    rt_err_t ret;
    rt_int32_t ack_result = 0;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control_wait(VOICE_CTRL_M33_PCM_PROBE_ENABLE, 5000U, &ack_result);
    rt_kprintf("[m55qa] probe_pcm_on ret=%d ack=%ld tx_pending=%lu\n",
               ret,
               (long)ack_result,
               (unsigned long)m33_m55_comm_tx_count());
}
MSH_CMD_EXPORT(m55qa_probe_pcm_on, Enable M33 built-in PCM probe for Xiaozhi QA only);

static void m55qa_probe_pcm_off(int argc, char **argv)
{
    rt_err_t ret;
    rt_int32_t ack_result = 0;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55qa_send_voice_control_wait(VOICE_CTRL_M33_PCM_PROBE_DISABLE, 5000U, &ack_result);
    rt_kprintf("[m55qa] probe_pcm_off ret=%d ack=%ld tx_pending=%lu\n",
               ret,
               (long)ack_result,
               (unsigned long)m33_m55_comm_tx_count());
}
MSH_CMD_EXPORT(m55qa_probe_pcm_off, Disable M33 PCM probe and keep CM55 mic0 product uplink);
