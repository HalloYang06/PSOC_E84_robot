#include "rehab_wifi_panel.h"
#include "wifi_config_service.h"
#include "websocket_client.h"
#include "voice_service.h"
#include "xiaozhi_ui_state.h"
#include "xiaozhi_voice_relay.h"

#ifdef BSP_USING_LVGL

#include <lvgl.h>
#include <finsh.h>
#include <stdio.h>
#include <string.h>

#define REHAB_WIFI_PANEL_AUTO_QA 0

extern rt_err_t m55_xiaozhi_talk_start_from_ui(void);
extern rt_err_t m55_xiaozhi_talk_stop_from_ui(void);

static lv_obj_t *g_status_label;
static lv_obj_t *g_xiaozhi_panel;
static lv_obj_t *g_xiaozhi_label;
static lv_obj_t *g_xiaozhi_detail_label;
static lv_obj_t *g_xiaozhi_reply_label;
static lv_obj_t *g_xiaozhi_spinner;
static lv_obj_t *g_ap_list;
static lv_obj_t *g_qa_big_panel;
static lv_obj_t *g_qa_big_label;
static lv_obj_t *g_ssid_textarea;
static lv_obj_t *g_password_textarea;
static lv_obj_t *g_auto_checkbox;
static lv_obj_t *g_keyboard;
static lv_obj_t *g_keyboard_target;
static lv_timer_t *g_scan_refresh_timer;
#if REHAB_WIFI_PANEL_AUTO_QA
static lv_timer_t *g_auto_qa_timer;
#endif
static lv_timer_t *g_xiaozhi_refresh_timer;
static rt_thread_t g_xiaozhi_ui_thread;
static struct rt_semaphore g_xiaozhi_ui_sem;
static rt_bool_t g_xiaozhi_ui_worker_ready;
static volatile rt_uint8_t g_xiaozhi_ui_pending_cmd;
static rt_thread_t g_connect_thread;
static rt_bool_t g_connect_in_progress;
static rt_bool_t g_diag_visible;
static lv_timer_t *g_boot_panel_timer;
#if REHAB_WIFI_PANEL_AUTO_QA
static rt_bool_t g_auto_qa_done;
#endif

LV_FONT_DECLARE(rehab_wifi_font);

static void rehab_wifi_panel_refresh_scan_list(void);
static lv_obj_t *panel_button_sized(lv_obj_t *parent,
                                    const char *text,
                                    lv_event_cb_t cb,
                                    lv_coord_t width,
                                    lv_coord_t height,
                                    lv_color_t color,
                                    lv_color_t pressed_color);
static void start_scan_refresh_timer(void);
static void start_xiaozhi_refresh_timer(void);
static void rehab_wifi_panel_run_qa_scan(const char *source);
static void xiaozhi_ui_worker_thread_entry(void *parameter);
static rt_err_t xiaozhi_ui_queue_action(rt_uint8_t cmd);
static rt_err_t xiaozhi_ui_start_worker(void);
static void rehab_wifi_panel_boot_timer_cb(lv_timer_t *timer);

static const char *wifi_keyboard_lower_map[] =
{
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Del", "\n",
    "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "\n",
    "a", "s", "d", "f", "g", "h", "j", "k", "l", "\n",
    "ABC", "z", "x", "c", "v", "b", "n", "m", ".", "\n",
    "Close", "1#", "_", "-", "@", " ", "OK", NULL
};

static const char *wifi_keyboard_upper_map[] =
{
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Del", "\n",
    "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "\n",
    "A", "S", "D", "F", "G", "H", "J", "K", "L", "\n",
    "abc", "Z", "X", "C", "V", "B", "N", "M", ".", "\n",
    "Close", "1#", "_", "-", "@", " ", "OK", NULL
};

static const char *wifi_keyboard_symbol_map[] =
{
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Del", "\n",
    "!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "\n",
    "-", "_", "+", "=", "/", "\\", ":", ";", "\"", "\n",
    "abc", ".", ",", "?", "'", "`", "~", "|", "\n",
    "Close", "ABC", "[", "]", "{", "}", "OK", NULL
};

static const lv_buttonmatrix_ctrl_t wifi_keyboard_text_ctrl[] =
{
    3, 3, 3, 3, 3, 3, 3, 3, 3, 3, LV_KEYBOARD_CTRL_BUTTON_FLAGS | 5,
    3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
    3, 3, 3, 3, 3, 3, 3, 3, 3,
    LV_KEYBOARD_CTRL_BUTTON_FLAGS | 5, 3, 3, 3, 3, 3, 3, 3, 3,
    LV_KEYBOARD_CTRL_BUTTON_FLAGS | 4, LV_KEYBOARD_CTRL_BUTTON_FLAGS | 4, 4, 4, 4, 12, LV_KEYBOARD_CTRL_BUTTON_FLAGS | 4
};

static const lv_buttonmatrix_ctrl_t wifi_keyboard_symbol_ctrl[] =
{
    3, 3, 3, 3, 3, 3, 3, 3, 3, 3, LV_KEYBOARD_CTRL_BUTTON_FLAGS | 5,
    3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
    3, 3, 3, 3, 3, 3, 3, 3, 3,
    LV_KEYBOARD_CTRL_BUTTON_FLAGS | 5, 3, 3, 3, 3, 3, 3, 3,
    LV_KEYBOARD_CTRL_BUTTON_FLAGS | 4, LV_KEYBOARD_CTRL_BUTTON_FLAGS | 4, 4, 4, 4, 4, LV_KEYBOARD_CTRL_BUTTON_FLAGS | 4
};

static const lv_font_t *panel_font(void)
{
    return &rehab_wifi_font;
}

static rt_bool_t wifi_scan_available(const wifi_config_snapshot_t *snapshot)
{
    return ((snapshot != RT_NULL) &&
            (snapshot->whd_stage >= 19) &&
            (snapshot->netdev_name[0] != '\0')) ? RT_TRUE : RT_FALSE;
}

static const char *scan_result_text(const wifi_config_snapshot_t *snapshot)
{
    if (snapshot->scan_running)
    {
        return "扫描中";
    }
    if (snapshot->scan_count > 0)
    {
        return "扫描完成";
    }
    if (snapshot->scan_result == -RT_EBUSY)
    {
        return "扫描中";
    }
    if (snapshot->scan_result == -RT_ETIMEOUT)
    {
        return "超时重试";
    }
    if (snapshot->scan_result != RT_EOK)
    {
        return wifi_scan_available(snapshot) ? "扫描失败" : "WiFi未就绪";
    }
    if (snapshot->scan_request_count > 0U)
    {
        return "未找到";
    }
    return "点击扫描";
}

static const char *wifi_state_text(const wifi_config_snapshot_t *snapshot)
{
    if (g_connect_in_progress)
    {
        return "正在连接";
    }
    if (snapshot->wlan_connected)
    {
        return "已连接";
    }
    if (snapshot->scan_running)
    {
        return "扫描中";
    }
    if (wifi_scan_available(snapshot))
    {
        return "待连接";
    }
    return "WiFi未就绪";
}

static const char *xiaozhi_state_text(const wifi_config_snapshot_t *snapshot)
{
    int stage;
    int err;

    if (!xiaozhi_voice_relay_has_token())
    {
        return "未配置Token";
    }
    if (websocket_client_is_connected())
    {
        return "已连接";
    }
    if ((snapshot == RT_NULL) || (snapshot->wlan_ready == 0U) || (snapshot->netdev_ip == 0U))
    {
        return "等待网络";
    }

    stage = websocket_client_last_stage();
    err = websocket_client_last_errno();
    if (err != 0)
    {
        if (stage == 10)
        {
            return "DNS失败";
        }
        if (stage == 20)
        {
            return "Socket失败";
        }
        if (stage == 30)
        {
            return "TCP失败";
        }
        if ((stage == 40) || (stage == 50))
        {
            return "握手失败";
        }
        if (stage == 60)
        {
            return "接收线程失败";
        }
        return "重试中";
    }

    if (stage == 0)
    {
        return "等待启动";
    }
    if (stage == 10)
    {
        return "解析中";
    }
    if (stage == 20)
    {
        return "建Socket";
    }
    if (stage == 30)
    {
        return "TCP连接";
    }
    if ((stage == 40) || (stage == 50))
    {
        return "握手中";
    }
    if (stage == 60)
    {
        return "接收启动";
    }
    return "连接中";
}

static void style_plain_panel(lv_obj_t *obj, lv_color_t bg)
{
    lv_obj_set_style_bg_color(obj, bg, 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(obj, 1, 0);
    lv_obj_set_style_border_color(obj, lv_color_hex(0xCBD5E1), 0);
    lv_obj_set_style_radius(obj, 6, 0);
}

static void rehab_wifi_panel_refresh(void)
{
    wifi_config_snapshot_t snapshot;
    xiaozhi_ui_snapshot_t xiaozhi;
    char status[128];
    char xiaozhi_status[96];
    char xiaozhi_detail[128];
    char xiaozhi_reply[128];
    char qa[128];
    const char *phase_text;
    rt_bool_t show_spinner = RT_FALSE;
    rt_bool_t xiaozhi_online;

    if ((g_status_label == RT_NULL) || (g_xiaozhi_label == RT_NULL))
    {
        return;
    }

    (void)wifi_config_whd_diag();
    wifi_config_get_snapshot(&snapshot);
    xiaozhi_ui_state_snapshot(&xiaozhi);
    xiaozhi_online = (xiaozhi_voice_relay_has_token() &&
                      websocket_client_is_connected()) ? RT_TRUE : RT_FALSE;
    if (xiaozhi_online &&
        (xiaozhi.phase == XIAOZHI_UI_THINKING) &&
        (xiaozhi.updated_ms != 0U) &&
        (((rt_uint32_t)rt_tick_get_millisecond() - xiaozhi.updated_ms) > 12000U))
    {
        xiaozhi_ui_state_set(XIAOZHI_UI_READY, "平台无回复，请重试", -RT_ETIMEOUT);
        xiaozhi_ui_state_snapshot(&xiaozhi);
    }
    rt_snprintf(status,
                sizeof(status),
                "%s  %ld个网络",
                wifi_state_text(&snapshot),
                (long)snapshot.scan_count);
    lv_label_set_text(g_status_label, status);

    if (!xiaozhi_voice_relay_has_token())
    {
        phase_text = "未配置Token";
        rt_snprintf(xiaozhi_detail, sizeof(xiaozhi_detail), "需要本地Token后才能连接平台");
    }
    else if (xiaozhi_online &&
             (xiaozhi.phase != XIAOZHI_UI_LISTENING) &&
             (xiaozhi.phase != XIAOZHI_UI_THINKING) &&
             (xiaozhi.phase != XIAOZHI_UI_SPEAKING))
    {
        phase_text = "在线待唤醒";
        rt_snprintf(xiaozhi_detail,
                    sizeof(xiaozhi_detail),
                    "已连接平台，说 xiaorui 或按说话  唤醒:%lu 回复:%lu",
                    (unsigned long)xiaozhi.wake_count,
                    (unsigned long)xiaozhi.reply_count);
    }
    else if ((snapshot.wlan_ready == 0U) || (snapshot.netdev_ip == 0U))
    {
        phase_text = "等待网络";
        rt_snprintf(xiaozhi_detail, sizeof(xiaozhi_detail), "WiFi连上后会自动连接小智");
    }
    else if ((xiaozhi.phase == XIAOZHI_UI_LISTENING) ||
             (xiaozhi.phase == XIAOZHI_UI_THINKING) ||
             (xiaozhi.phase == XIAOZHI_UI_SPEAKING))
    {
        phase_text = xiaozhi_ui_phase_text(xiaozhi.phase);
        show_spinner = ((xiaozhi.phase == XIAOZHI_UI_LISTENING) ||
                        (xiaozhi.phase == XIAOZHI_UI_THINKING) ||
                        (xiaozhi.phase == XIAOZHI_UI_SPEAKING)) ? RT_TRUE : RT_FALSE;
        if (xiaozhi.phase == XIAOZHI_UI_LISTENING)
        {
            rt_snprintf(xiaozhi_detail,
                        sizeof(xiaozhi_detail),
                        "我在，正在听  唤醒:%lu 回复:%lu",
                        (unsigned long)xiaozhi.wake_count,
                        (unsigned long)xiaozhi.reply_count);
        }
        else if (xiaozhi.phase == XIAOZHI_UI_THINKING)
        {
            rt_snprintf(xiaozhi_detail, sizeof(xiaozhi_detail), "问题已发送，等待平台模型");
        }
        else if (xiaozhi.phase == XIAOZHI_UI_SPEAKING)
        {
            rt_snprintf(xiaozhi_detail, sizeof(xiaozhi_detail), "正在通过扬声器回答");
        }
    }
    else if ((xiaozhi.phase == XIAOZHI_UI_READY) || xiaozhi_online)
    {
        phase_text = "在线待唤醒";
        if (xiaozhi_online)
        {
            rt_snprintf(xiaozhi_detail,
                        sizeof(xiaozhi_detail),
                        "已连接平台，说 xiaorui 或按说话  唤醒:%lu 回复:%lu",
                        (unsigned long)xiaozhi.wake_count,
                        (unsigned long)xiaozhi.reply_count);
        }
        else if (xiaozhi.detail[0] != '\0')
        {
            rt_snprintf(xiaozhi_detail,
                        sizeof(xiaozhi_detail),
                        "%s  唤醒:%lu 回复:%lu",
                        xiaozhi.detail,
                        (unsigned long)xiaozhi.wake_count,
                        (unsigned long)xiaozhi.reply_count);
        }
        else
        {
            rt_snprintf(xiaozhi_detail,
                        sizeof(xiaozhi_detail),
                        "说 xiaorui 后开始聊天  唤醒:%lu 回复:%lu",
                        (unsigned long)xiaozhi.wake_count,
                        (unsigned long)xiaozhi.reply_count);
        }
    }
    else
    {
        phase_text = xiaozhi_state_text(&snapshot);
        rt_snprintf(xiaozhi_detail,
                    sizeof(xiaozhi_detail),
                    "WS:%d/%d %s",
                    websocket_client_last_stage(),
                    websocket_client_last_errno(),
                    (xiaozhi.detail[0] != '\0') ? xiaozhi.detail : "等待响应");
    }

    rt_snprintf(xiaozhi_status,
                sizeof(xiaozhi_status),
                "小智：%s",
                phase_text);
    lv_label_set_text(g_xiaozhi_label, xiaozhi_status);
    if (g_xiaozhi_detail_label != RT_NULL)
    {
        lv_label_set_text(g_xiaozhi_detail_label, xiaozhi_detail);
    }
    if (g_xiaozhi_reply_label != RT_NULL)
    {
        if (xiaozhi.last_reply[0] != '\0')
        {
            rt_snprintf(xiaozhi_reply, sizeof(xiaozhi_reply), "回复：%s", xiaozhi.last_reply);
        }
        else if (xiaozhi_online)
        {
            rt_snprintf(xiaozhi_reply, sizeof(xiaozhi_reply), "可按说话开始，也可说 xiaorui");
        }
        else
        {
            rt_snprintf(xiaozhi_reply, sizeof(xiaozhi_reply), "说唤醒词后直接语音对话");
        }
        lv_label_set_text(g_xiaozhi_reply_label, xiaozhi_reply);
    }
    if (g_xiaozhi_spinner != RT_NULL)
    {
        if (show_spinner)
        {
            lv_obj_remove_flag(g_xiaozhi_spinner, LV_OBJ_FLAG_HIDDEN);
        }
        else
        {
            lv_obj_add_flag(g_xiaozhi_spinner, LV_OBJ_FLAG_HIDDEN);
        }
    }

    if ((g_qa_big_panel != RT_NULL) && (g_qa_big_label != RT_NULL))
    {
        rt_snprintf(qa,
                    sizeof(qa),
                    "WHD:%ld/%ld scan:%ld cb:%lu done:%lu timeout:%lu",
                    (long)snapshot.whd_stage,
                    (long)snapshot.whd_result,
                    (long)snapshot.scan_result,
                    (unsigned long)snapshot.scan_callback_count,
                    (unsigned long)snapshot.scan_done_count,
                    (unsigned long)snapshot.scan_timeout_count);
        lv_label_set_text(g_qa_big_label, qa);

        if (g_diag_visible)
        {
            lv_obj_remove_flag(g_qa_big_panel, LV_OBJ_FLAG_HIDDEN);
        }
        else
        {
            lv_obj_add_flag(g_qa_big_panel, LV_OBJ_FLAG_HIDDEN);
        }
    }
}

static void ap_button_event_cb(lv_event_t *event)
{
    rt_int32_t index = (rt_int32_t)(rt_ubase_t)lv_event_get_user_data(event);
    wifi_config_ap_t ap;

    if ((g_ssid_textarea == RT_NULL) || (wifi_config_get_scan_ap(index, &ap) != RT_EOK))
    {
        return;
    }

    lv_textarea_set_text(g_ssid_textarea, ap.ssid);
    (void)wifi_config_set_ssid(ap.ssid);
    rehab_wifi_panel_refresh();
}

static void rehab_wifi_panel_refresh_scan_list(void)
{
    rt_int32_t i;
    rt_int32_t count;
    char row[96];

    if (g_ap_list == RT_NULL)
    {
        return;
    }

    lv_obj_clean(g_ap_list);
    count = wifi_config_get_scan_count();
    if (count <= 0)
    {
        wifi_config_snapshot_t snapshot;
        lv_obj_t *button;
        char text[96];

        wifi_config_get_snapshot(&snapshot);
        if (snapshot.scan_running)
        {
            rt_snprintf(text, sizeof(text), "扫描中...");
        }
        else if ((snapshot.scan_request_count > 0U) && (snapshot.scan_callback_count == 0U) &&
                 (snapshot.scan_result == RT_EOK))
        {
            rt_snprintf(text, sizeof(text), "未找到网络，请重试");
        }
        else if (snapshot.scan_result != RT_EOK)
        {
            rt_snprintf(text, sizeof(text), "%s", scan_result_text(&snapshot));
        }
        else
        {
            rt_snprintf(text, sizeof(text), "点击扫描");
        }

        button = lv_list_add_button(g_ap_list, RT_NULL, text);
        lv_obj_set_style_text_font(button, panel_font(), 0);
        lv_obj_clear_flag(button, LV_OBJ_FLAG_CLICKABLE);
        return;
    }

    for (i = 0; (i < count) && (i < WIFI_CONFIG_SCAN_MAX_APS); i++)
    {
        wifi_config_ap_t ap;
        lv_obj_t *button;

        if (wifi_config_get_scan_ap(i, &ap) != RT_EOK)
        {
            continue;
        }

        rt_snprintf(row,
                    sizeof(row),
                    "%s  %lddBm  %s  信道%ld",
                    ap.ssid[0] ? ap.ssid : "(hidden)",
                    (long)ap.rssi,
                    wifi_config_security_name(ap.security),
                    (long)ap.channel);
        button = lv_list_add_button(g_ap_list, RT_NULL, row);
        lv_obj_set_style_text_font(button, panel_font(), 0);
        lv_obj_add_event_cb(button, ap_button_event_cb, LV_EVENT_CLICKED, (void *)(rt_ubase_t)i);
    }
}

static void scan_refresh_timer_cb(lv_timer_t *timer)
{
    RT_UNUSED(timer);
    rehab_wifi_panel_refresh_scan_list();
    rehab_wifi_panel_refresh();
}

static void start_scan_refresh_timer(void)
{
    if (g_scan_refresh_timer != RT_NULL)
    {
        lv_timer_delete(g_scan_refresh_timer);
        g_scan_refresh_timer = RT_NULL;
    }

    g_scan_refresh_timer = lv_timer_create(scan_refresh_timer_cb, 500, RT_NULL);
    if (g_scan_refresh_timer != RT_NULL)
    {
        lv_timer_set_repeat_count(g_scan_refresh_timer, 50);
        lv_timer_set_auto_delete(g_scan_refresh_timer, false);
    }
}

static void xiaozhi_refresh_timer_cb(lv_timer_t *timer)
{
    RT_UNUSED(timer);
    rehab_wifi_panel_refresh();
}

static void start_xiaozhi_refresh_timer(void)
{
    if (g_xiaozhi_refresh_timer != RT_NULL)
    {
        return;
    }

    g_xiaozhi_refresh_timer = lv_timer_create(xiaozhi_refresh_timer_cb, 500, RT_NULL);
    if (g_xiaozhi_refresh_timer != RT_NULL)
    {
        lv_timer_set_auto_delete(g_xiaozhi_refresh_timer, false);
    }
}

static void keyboard_show_for(lv_obj_t *target)
{
    if ((g_keyboard == RT_NULL) || (target == RT_NULL))
    {
        return;
    }

    if (g_keyboard_target != target)
    {
        g_keyboard_target = target;
        lv_keyboard_set_textarea(g_keyboard, target);
    }

    if (lv_obj_has_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN))
    {
        lv_obj_remove_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);
        lv_obj_move_foreground(g_keyboard);
    }
}

static void keyboard_hide(void)
{
    if (g_keyboard == RT_NULL)
    {
        return;
    }

    g_keyboard_target = RT_NULL;
    lv_keyboard_set_textarea(g_keyboard, RT_NULL);
    lv_obj_add_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);
}

static void keyboard_target_event_cb(lv_event_t *event)
{
    lv_event_code_t code = lv_event_get_code(event);

    if ((code == LV_EVENT_FOCUSED) || (code == LV_EVENT_CLICKED) || (code == LV_EVENT_PRESSED))
    {
        keyboard_show_for(lv_event_get_target(event));
    }
    else if ((code == LV_EVENT_READY) || (code == LV_EVENT_CANCEL) || (code == LV_EVENT_DEFOCUSED))
    {
        keyboard_hide();
        lv_obj_clear_state(lv_event_get_target(event), LV_STATE_FOCUSED);
    }
}

static void keyboard_event_cb(lv_event_t *event)
{
    lv_event_code_t code = lv_event_get_code(event);
    lv_obj_t *keyboard;
    uint32_t button_id;
    const char *text;

    if ((code == LV_EVENT_READY) || (code == LV_EVENT_CANCEL))
    {
        keyboard_hide();
        return;
    }

    if (code != LV_EVENT_VALUE_CHANGED)
    {
        return;
    }

    keyboard = lv_event_get_current_target(event);
    button_id = lv_keyboard_get_selected_button(keyboard);
    if (button_id == LV_BUTTONMATRIX_BUTTON_NONE)
    {
        return;
    }

    text = lv_keyboard_get_button_text(keyboard, button_id);
    if (text == RT_NULL)
    {
        return;
    }

    if (rt_strcmp(text, "Del") == 0)
    {
        lv_obj_t *target = lv_keyboard_get_textarea(keyboard);
        if (target != RT_NULL)
        {
            lv_textarea_delete_char(target);
        }
        lv_event_stop_processing(event);
    }
    else if (rt_strcmp(text, "Close") == 0)
    {
        keyboard_hide();
        lv_event_stop_processing(event);
    }
    else if (rt_strcmp(text, "OK") == 0)
    {
        lv_obj_t *target = lv_keyboard_get_textarea(keyboard);
        keyboard_hide();
        if (target != RT_NULL)
        {
            (void)lv_obj_send_event(target, LV_EVENT_READY, RT_NULL);
        }
        lv_event_stop_processing(event);
    }
    else
    {
        lv_keyboard_def_event_cb(event);
    }
}

static void scan_event_cb(lv_event_t *event)
{
    rt_err_t ret;

    RT_UNUSED(event);
    ret = wifi_config_scan();
    rt_kprintf("[rehab_wifi_panel] scan button ret=%d\n", ret);
    if (ret != RT_EOK)
    {
        (void)wifi_config_whd_diag();
    }
    rehab_wifi_panel_refresh_scan_list();
    rehab_wifi_panel_refresh();
    start_scan_refresh_timer();
}

static void rehab_wifi_panel_run_qa_scan(const char *source)
{
    wifi_config_snapshot_t snapshot;
    rt_err_t ret;

    if ((source == RT_NULL) || (rt_strcmp(source, "auto") != 0))
    {
        g_diag_visible = RT_TRUE;
    }
    (void)wifi_config_diag();
    (void)wifi_config_whd_diag();
    ret = wifi_config_scan();
    rehab_wifi_panel_refresh_scan_list();
    rehab_wifi_panel_refresh();
    start_scan_refresh_timer();
    wifi_config_get_snapshot(&snapshot);
    rt_kprintf("[rehab_wifi_panel] qa(%s) scan ret=%d ready=%lu running=%lu count=%ld cb=%lu done=%lu timeout=%lu whd=%ld/%ld flags=0x%lx\n",
               source ? source : "manual",
               ret,
               (unsigned long)snapshot.wlan_ready,
               (unsigned long)snapshot.scan_running,
               (long)snapshot.scan_count,
               (unsigned long)snapshot.scan_callback_count,
               (unsigned long)snapshot.scan_done_count,
               (unsigned long)snapshot.scan_timeout_count,
               (long)snapshot.whd_stage,
               (long)snapshot.whd_result,
               (unsigned long)snapshot.whd_flags);
}

#if REHAB_WIFI_PANEL_AUTO_QA
static void auto_qa_timer_cb(lv_timer_t *timer)
{
    wifi_config_snapshot_t snapshot;
    rt_uint32_t *ticks = (rt_uint32_t *)lv_timer_get_user_data(timer);

    if (g_auto_qa_done)
    {
        lv_timer_delete(timer);
        g_auto_qa_timer = RT_NULL;
        return;
    }

    if (ticks != RT_NULL)
    {
        (*ticks)++;
    }

    (void)wifi_config_whd_diag();
    wifi_config_get_snapshot(&snapshot);
    rehab_wifi_panel_refresh_scan_list();
    rehab_wifi_panel_refresh();

    if (wifi_scan_available(&snapshot) && (snapshot.scan_running == 0U) && (snapshot.scan_request_count == 0U))
    {
        rehab_wifi_panel_run_qa_scan("auto");
        g_auto_qa_done = RT_TRUE;
        return;
    }

    if ((ticks != RT_NULL) && (*ticks >= 60U))
    {
        rt_kprintf("[rehab_wifi_panel] qa(auto) stop wait ready=%lu running=%lu count=%ld cb=%lu done=%lu timeout=%lu whd=%ld/%ld flags=0x%lx\n",
               (unsigned long)wifi_scan_available(&snapshot),
                   (unsigned long)snapshot.scan_running,
                   (long)snapshot.scan_count,
                   (unsigned long)snapshot.scan_callback_count,
                   (unsigned long)snapshot.scan_done_count,
                   (unsigned long)snapshot.scan_timeout_count,
                   (long)snapshot.whd_stage,
                   (long)snapshot.whd_result,
                   (unsigned long)snapshot.whd_flags);
        g_auto_qa_done = RT_TRUE;
    }
}

static void start_auto_qa_timer(void)
{
    static rt_uint32_t ticks;

    if (g_auto_qa_timer != RT_NULL)
    {
        return;
    }

    ticks = 0U;
    g_auto_qa_done = RT_FALSE;
    g_diag_visible = RT_FALSE;
    g_auto_qa_timer = lv_timer_create(auto_qa_timer_cb, 1000, &ticks);
    if (g_auto_qa_timer != RT_NULL)
    {
        lv_timer_set_repeat_count(g_auto_qa_timer, 65);
        lv_timer_set_auto_delete(g_auto_qa_timer, false);
    }
}
#endif

static void connect_thread_entry(void *parameter)
{
    rt_err_t ret;
    wifi_config_snapshot_t snapshot;

    RT_UNUSED(parameter);
    ret = wifi_config_connect();
    if (ret == RT_EOK)
    {
        for (rt_uint32_t i = 0; i < 20U; i++)
        {
            wifi_config_get_snapshot(&snapshot);
            if (snapshot.wlan_ready && snapshot.netdev_ip != 0U)
            {
                break;
            }
            rt_thread_mdelay(500);
        }
    }
    (void)wifi_config_whd_diag();
    g_connect_in_progress = RT_FALSE;
    g_connect_thread = RT_NULL;
}

static void diag_event_cb(lv_event_t *event)
{
    RT_UNUSED(event);
    g_diag_visible = g_diag_visible ? RT_FALSE : RT_TRUE;
    (void)wifi_config_diag();
    (void)wifi_config_whd_diag();
    rehab_wifi_panel_refresh_scan_list();
    rehab_wifi_panel_refresh();
}

static void connect_event_cb(lv_event_t *event)
{
    const char *ssid;
    const char *password;
    rt_bool_t auto_connect;

    RT_UNUSED(event);

    ssid = lv_textarea_get_text(g_ssid_textarea);
    password = lv_textarea_get_text(g_password_textarea);
    auto_connect = lv_obj_has_state(g_auto_checkbox, LV_STATE_CHECKED) ? RT_TRUE : RT_FALSE;
    if ((ssid == RT_NULL) || (ssid[0] == '\0'))
    {
        rehab_wifi_panel_refresh();
        return;
    }
    if (g_connect_in_progress)
    {
        rehab_wifi_panel_refresh();
        return;
    }
    if (wifi_config_set_ssid(ssid) != RT_EOK)
    {
        rehab_wifi_panel_refresh();
        return;
    }
    if (wifi_config_set_password(password) != RT_EOK)
    {
        rehab_wifi_panel_refresh();
        return;
    }
    (void)wifi_config_set_auto_connect(auto_connect);
    g_connect_in_progress = RT_TRUE;
    g_connect_thread = rt_thread_create("wifi_join",
                                        connect_thread_entry,
                                        RT_NULL,
                                        4096,
                                        18,
                                        10);
    if (g_connect_thread != RT_NULL)
    {
        rt_thread_startup(g_connect_thread);
    }
    else
    {
        g_connect_in_progress = RT_FALSE;
    }
    rehab_wifi_panel_refresh();
    start_scan_refresh_timer();
}

static void save_event_cb(lv_event_t *event)
{
    const char *ssid;
    const char *password;
    rt_bool_t auto_connect;

    RT_UNUSED(event);

    ssid = lv_textarea_get_text(g_ssid_textarea);
    password = lv_textarea_get_text(g_password_textarea);
    auto_connect = lv_obj_has_state(g_auto_checkbox, LV_STATE_CHECKED) ? RT_TRUE : RT_FALSE;
    (void)wifi_config_set_ssid(ssid);
    (void)wifi_config_set_password(password);
    (void)wifi_config_set_auto_connect(auto_connect);
    (void)wifi_config_save();
    rehab_wifi_panel_refresh();
}

static void forget_event_cb(lv_event_t *event)
{
    RT_UNUSED(event);
    (void)wifi_config_forget();
    lv_textarea_set_text(g_ssid_textarea, "");
    lv_textarea_set_text(g_password_textarea, "");
    rehab_wifi_panel_refresh();
}

static void disconnect_event_cb(lv_event_t *event)
{
    RT_UNUSED(event);
    (void)wifi_config_disconnect();
    rehab_wifi_panel_refresh();
}

static rt_err_t xiaozhi_ui_start_worker(void)
{
    if (g_xiaozhi_ui_worker_ready)
    {
        return RT_EOK;
    }

    rt_sem_init(&g_xiaozhi_ui_sem, "xz_ui", 0, RT_IPC_FLAG_PRIO);
    g_xiaozhi_ui_thread = rt_thread_create("xz_ui",
                                           xiaozhi_ui_worker_thread_entry,
                                           RT_NULL,
                                           4096,
                                           20,
                                           10);
    if (g_xiaozhi_ui_thread == RT_NULL)
    {
        return -RT_ENOMEM;
    }

    rt_thread_startup(g_xiaozhi_ui_thread);
    g_xiaozhi_ui_worker_ready = RT_TRUE;
    return RT_EOK;
}

static rt_err_t xiaozhi_ui_queue_action(rt_uint8_t cmd)
{
    rt_err_t ret;

    ret = xiaozhi_ui_start_worker();
    if (ret != RT_EOK)
    {
        return ret;
    }

    g_xiaozhi_ui_pending_cmd = cmd;
    ret = rt_sem_release(&g_xiaozhi_ui_sem);
    if (ret != RT_EOK)
    {
        rt_kprintf("[rehab_wifi_panel] xiaozhi ui queue release ret=%d cmd=%u\n",
                   ret,
                   (unsigned)cmd);
    }
    return ret;
}

static void xiaozhi_ui_worker_thread_entry(void *parameter)
{
    RT_UNUSED(parameter);

    while (1)
    {
        rt_uint8_t cmd;

        rt_sem_take(&g_xiaozhi_ui_sem, RT_WAITING_FOREVER);
        cmd = g_xiaozhi_ui_pending_cmd;
        g_xiaozhi_ui_pending_cmd = 0U;

        if (cmd == 1U)
        {
            rt_kprintf("[rehab_wifi_panel] async xiaozhi start\n");
            (void)m55_xiaozhi_talk_start_from_ui();
        }
        else if (cmd == 2U)
        {
            rt_err_t ret;

            rt_kprintf("[rehab_wifi_panel] async xiaozhi stop\n");
            ret = m55_xiaozhi_talk_stop_from_ui();
            if (ret == RT_EOK)
            {
                xiaozhi_ui_state_set(XIAOZHI_UI_READY, "已停止，等待唤醒词", RT_EOK);
            }
            else
            {
                xiaozhi_ui_state_set(XIAOZHI_UI_READY, "停止失败，请重试", ret);
            }
        }
    }
}

static void xiaozhi_talk_event_cb(lv_event_t *event)
{
    RT_UNUSED(event);
    xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "正在启动小智", RT_EOK);
    (void)xiaozhi_ui_queue_action(1U);
    rehab_wifi_panel_refresh();
}

static void xiaozhi_stop_event_cb(lv_event_t *event)
{
    RT_UNUSED(event);
    xiaozhi_ui_state_set(XIAOZHI_UI_CONNECTING, "正在停止录音", RT_EOK);
    (void)xiaozhi_ui_queue_action(2U);
    rehab_wifi_panel_refresh();
}

#if 0
static void back_to_wifi_panel_event_cb(lv_event_t *event)
{
    RT_UNUSED(event);
    (void)rehab_wifi_panel_create();
}

static void qr_event_cb(lv_event_t *event)
{
    lv_obj_t *screen = lv_screen_active();
    lv_obj_t *title;
    lv_obj_t *hint;
    lv_obj_t *payload_label;
    lv_obj_t *back_row;
    char payload[256];

    RT_UNUSED(event);
    keyboard_hide();

    lv_obj_clean(screen);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0xF4F7F8), 0);

    title = lv_label_create(screen);
    lv_label_set_text(title, "扫码配网");
    lv_obj_set_style_text_color(title, lv_color_hex(0x111827), 0);
    lv_obj_set_style_text_font(title, panel_font(), 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 14);

    rt_snprintf(payload,
                sizeof(payload),
                "rehab-arm://provision?project_id=e201f41c-25a6-46e1-baf8-be6dcb83284c&device_id=nanopi-m5&robot_id=rehab-arm-alpha&transport=ble");

#if LV_USE_QRCODE
    {
        lv_obj_t *qr = lv_qrcode_create(screen);
        lv_qrcode_set_size(qr, 260);
        lv_qrcode_set_dark_color(qr, lv_color_hex(0x111827));
        lv_qrcode_set_light_color(qr, lv_color_hex(0xFFFFFF));
        (void)lv_qrcode_update(qr, payload, rt_strlen(payload));
        lv_obj_align(qr, LV_ALIGN_TOP_MID, 0, 68);
    }
#else
    {
        lv_obj_t *fallback = lv_label_create(screen);
        lv_label_set_text(fallback, "二维码未启用");
        lv_obj_set_style_text_font(fallback, panel_font(), 0);
        lv_obj_align(fallback, LV_ALIGN_TOP_MID, 0, 160);
    }
#endif

    hint = lv_label_create(screen);
    lv_label_set_text(hint, "手机扫码后选择网络并发送密码");
    lv_obj_set_style_text_color(hint, lv_color_hex(0x1F2937), 0);
    lv_obj_set_style_text_font(hint, panel_font(), 0);
    lv_obj_align(hint, LV_ALIGN_TOP_MID, 0, 350);

    payload_label = lv_label_create(screen);
    lv_label_set_text(payload_label, "BLE配网  device:nanopi-m5");
    lv_obj_set_style_text_color(payload_label, lv_color_hex(0x4B5563), 0);
    lv_obj_set_style_text_font(payload_label, panel_font(), 0);
    lv_obj_align(payload_label, LV_ALIGN_TOP_MID, 0, 386);

    back_row = lv_obj_create(screen);
    lv_obj_remove_style_all(back_row);
    lv_obj_set_size(back_row, 430, 50);
    lv_obj_set_flex_flow(back_row, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(back_row, 8, 0);
    lv_obj_align(back_row, LV_ALIGN_TOP_MID, 0, 438);
    (void)panel_button_sized(back_row,
                             "返回",
                             back_to_wifi_panel_event_cb,
                             198,
                             42,
                             lv_color_hex(0x2563EB),
                             lv_color_hex(0x1D4ED8));
    (void)panel_button_sized(back_row,
                             "刷新",
                             qr_event_cb,
                             198,
                             42,
                             lv_color_hex(0x2563EB),
                             lv_color_hex(0x1D4ED8));
}
#endif

static lv_obj_t *panel_button_sized(lv_obj_t *parent,
                                    const char *text,
                                    lv_event_cb_t cb,
                                    lv_coord_t width,
                                    lv_coord_t height,
                                    lv_color_t color,
                                    lv_color_t pressed_color)
{
    lv_obj_t *button = lv_button_create(parent);
    lv_obj_t *label;

    lv_obj_set_size(button, width, height);
    lv_obj_add_event_cb(button, cb, LV_EVENT_CLICKED, RT_NULL);
    lv_obj_set_style_radius(button, 6, 0);
    lv_obj_set_style_bg_color(button, color, 0);
    lv_obj_set_style_bg_color(button, pressed_color, LV_STATE_PRESSED);

    label = lv_label_create(button);
    lv_label_set_text(label, text);
    lv_label_set_long_mode(label, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_font(label, panel_font(), 0);
    lv_obj_set_style_text_color(label, lv_color_hex(0xFFFFFF), 0);
    lv_obj_center(label);
    return button;
}

rt_err_t rehab_wifi_panel_create(void)
{
    lv_obj_t *screen = lv_screen_active();
    lv_obj_t *title;
    lv_obj_t *voice_row;
    lv_obj_t *row;
    lv_obj_t *diag_button;
    wifi_config_snapshot_t snapshot;

    (void)wifi_config_service_init();
    wifi_config_get_snapshot(&snapshot);

    lv_obj_clean(screen);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0xF4F7F8), 0);

    title = lv_label_create(screen);
    lv_label_set_text(title, "小智语音助手");
    lv_obj_set_style_text_color(title, lv_color_hex(0x111827), 0);
    lv_obj_set_style_text_font(title, panel_font(), 0);
    lv_obj_align(title, LV_ALIGN_TOP_LEFT, 22, 16);

    g_status_label = lv_label_create(screen);
    lv_obj_set_width(g_status_label, 430);
    lv_obj_set_style_text_color(g_status_label, lv_color_hex(0x1F2937), 0);
    lv_obj_set_style_text_font(g_status_label, panel_font(), 0);
    lv_label_set_long_mode(g_status_label, LV_LABEL_LONG_CLIP);
    lv_obj_align(g_status_label, LV_ALIGN_TOP_LEFT, 22, 48);

    g_xiaozhi_panel = lv_obj_create(screen);
    lv_obj_remove_style_all(g_xiaozhi_panel);
    lv_obj_set_size(g_xiaozhi_panel, 430, 150);
    style_plain_panel(g_xiaozhi_panel, lv_color_hex(0xE0F2FE));
    lv_obj_set_style_pad_all(g_xiaozhi_panel, 12, 0);
    lv_obj_align(g_xiaozhi_panel, LV_ALIGN_TOP_LEFT, 22, 78);

    g_xiaozhi_spinner = lv_spinner_create(g_xiaozhi_panel);
    lv_obj_set_size(g_xiaozhi_spinner, 36, 36);
    lv_spinner_set_anim_params(g_xiaozhi_spinner, 900, 90);
    lv_obj_set_style_arc_color(g_xiaozhi_spinner, lv_color_hex(0x38BDF8), LV_PART_MAIN);
    lv_obj_set_style_arc_color(g_xiaozhi_spinner, lv_color_hex(0x0369A1), LV_PART_INDICATOR);
    lv_obj_set_style_arc_width(g_xiaozhi_spinner, 4, LV_PART_MAIN);
    lv_obj_set_style_arc_width(g_xiaozhi_spinner, 5, LV_PART_INDICATOR);
    lv_obj_align(g_xiaozhi_spinner, LV_ALIGN_TOP_RIGHT, 0, 0);
    lv_obj_add_flag(g_xiaozhi_spinner, LV_OBJ_FLAG_HIDDEN);

    g_xiaozhi_label = lv_label_create(g_xiaozhi_panel);
    lv_obj_set_width(g_xiaozhi_label, 350);
    lv_label_set_long_mode(g_xiaozhi_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(g_xiaozhi_label, lv_color_hex(0x075985), 0);
    lv_obj_set_style_text_font(g_xiaozhi_label, panel_font(), 0);
    lv_obj_align(g_xiaozhi_label, LV_ALIGN_TOP_LEFT, 0, 0);

    g_xiaozhi_detail_label = lv_label_create(g_xiaozhi_panel);
    lv_obj_set_width(g_xiaozhi_detail_label, 400);
    lv_label_set_long_mode(g_xiaozhi_detail_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(g_xiaozhi_detail_label, lv_color_hex(0x0F172A), 0);
    lv_obj_set_style_text_font(g_xiaozhi_detail_label, panel_font(), 0);
    lv_obj_align(g_xiaozhi_detail_label, LV_ALIGN_TOP_LEFT, 0, 42);

    g_xiaozhi_reply_label = lv_label_create(g_xiaozhi_panel);
    lv_obj_set_width(g_xiaozhi_reply_label, 400);
    lv_label_set_long_mode(g_xiaozhi_reply_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(g_xiaozhi_reply_label, lv_color_hex(0x334155), 0);
    lv_obj_set_style_text_font(g_xiaozhi_reply_label, panel_font(), 0);
    lv_obj_align(g_xiaozhi_reply_label, LV_ALIGN_TOP_LEFT, 0, 90);

    voice_row = lv_obj_create(screen);
    lv_obj_remove_style_all(voice_row);
    lv_obj_set_size(voice_row, 430, 50);
    lv_obj_set_flex_flow(voice_row, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(voice_row, 12, 0);
    lv_obj_align(voice_row, LV_ALIGN_TOP_LEFT, 22, 238);
    (void)panel_button_sized(voice_row,
                             "说话",
                             xiaozhi_talk_event_cb,
                             209,
                             48,
                             lv_color_hex(0x059669),
                             lv_color_hex(0x047857));
    (void)panel_button_sized(voice_row,
                             "停止",
                             xiaozhi_stop_event_cb,
                             209,
                             48,
                             lv_color_hex(0xDC2626),
                             lv_color_hex(0xB91C1C));

    g_ap_list = lv_list_create(screen);
    lv_obj_set_size(g_ap_list, 430, 62);
    style_plain_panel(g_ap_list, lv_color_hex(0xFFFFFF));
    lv_obj_set_style_pad_all(g_ap_list, 6, 0);
    lv_obj_align(g_ap_list, LV_ALIGN_TOP_LEFT, 22, 302);

    g_ssid_textarea = lv_textarea_create(screen);
    lv_textarea_set_one_line(g_ssid_textarea, true);
    lv_textarea_set_placeholder_text(g_ssid_textarea, "WiFi名称");
    if (snapshot.ssid[0] != '\0')
    {
        lv_textarea_set_text(g_ssid_textarea, snapshot.ssid);
    }
    lv_obj_set_size(g_ssid_textarea, 430, 40);
    lv_obj_set_style_text_font(g_ssid_textarea, panel_font(), 0);
    style_plain_panel(g_ssid_textarea, lv_color_hex(0xFFFFFF));
    lv_obj_align(g_ssid_textarea, LV_ALIGN_TOP_LEFT, 22, 376);
    lv_obj_add_event_cb(g_ssid_textarea, keyboard_target_event_cb, LV_EVENT_FOCUSED, RT_NULL);
    lv_obj_add_event_cb(g_ssid_textarea, keyboard_target_event_cb, LV_EVENT_CLICKED, RT_NULL);
    lv_obj_add_event_cb(g_ssid_textarea, keyboard_target_event_cb, LV_EVENT_READY, RT_NULL);
    lv_obj_add_event_cb(g_ssid_textarea, keyboard_target_event_cb, LV_EVENT_CANCEL, RT_NULL);
    lv_obj_add_event_cb(g_ssid_textarea, keyboard_target_event_cb, LV_EVENT_DEFOCUSED, RT_NULL);

    g_password_textarea = lv_textarea_create(screen);
    lv_textarea_set_one_line(g_password_textarea, true);
    lv_textarea_set_password_mode(g_password_textarea, true);
    lv_textarea_set_placeholder_text(g_password_textarea, "密码");
    if (snapshot.password[0] != '\0')
    {
        lv_textarea_set_text(g_password_textarea, snapshot.password);
    }
    lv_obj_set_size(g_password_textarea, 430, 40);
    lv_obj_set_style_text_font(g_password_textarea, panel_font(), 0);
    style_plain_panel(g_password_textarea, lv_color_hex(0xFFFFFF));
    lv_obj_align(g_password_textarea, LV_ALIGN_TOP_LEFT, 22, 422);
    lv_obj_add_event_cb(g_password_textarea, keyboard_target_event_cb, LV_EVENT_FOCUSED, RT_NULL);
    lv_obj_add_event_cb(g_password_textarea, keyboard_target_event_cb, LV_EVENT_CLICKED, RT_NULL);
    lv_obj_add_event_cb(g_password_textarea, keyboard_target_event_cb, LV_EVENT_READY, RT_NULL);
    lv_obj_add_event_cb(g_password_textarea, keyboard_target_event_cb, LV_EVENT_CANCEL, RT_NULL);
    lv_obj_add_event_cb(g_password_textarea, keyboard_target_event_cb, LV_EVENT_DEFOCUSED, RT_NULL);

    g_auto_checkbox = lv_checkbox_create(screen);
    lv_checkbox_set_text(g_auto_checkbox, "自动连接");
    lv_obj_set_style_text_color(g_auto_checkbox, lv_color_hex(0x111827), 0);
    lv_obj_set_style_text_font(g_auto_checkbox, panel_font(), 0);
    if (snapshot.auto_connect)
    {
        lv_obj_add_state(g_auto_checkbox, LV_STATE_CHECKED);
    }
    lv_obj_align(g_auto_checkbox, LV_ALIGN_TOP_LEFT, 26, 468);

    row = lv_obj_create(screen);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, 430, 82);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW_WRAP);
    lv_obj_set_style_pad_column(row, 8, 0);
    lv_obj_set_style_pad_row(row, 8, 0);
    lv_obj_align(row, LV_ALIGN_TOP_LEFT, 22, 500);
    (void)panel_button_sized(row, "扫描", scan_event_cb, 98, 36, lv_color_hex(0x2563EB), lv_color_hex(0x1D4ED8));
    (void)panel_button_sized(row, "连接", connect_event_cb, 98, 36, lv_color_hex(0x2563EB), lv_color_hex(0x1D4ED8));
    (void)panel_button_sized(row, "保存", save_event_cb, 98, 36, lv_color_hex(0x475569), lv_color_hex(0x334155));
    (void)panel_button_sized(row, "清除", forget_event_cb, 98, 36, lv_color_hex(0x475569), lv_color_hex(0x334155));
    (void)panel_button_sized(row, "断开", disconnect_event_cb, 98, 36, lv_color_hex(0x64748B), lv_color_hex(0x475569));
    diag_button = panel_button_sized(row,
                                     g_diag_visible ? "隐藏" : "诊断",
                                     diag_event_cb,
                                     98,
                                     36,
                                     lv_color_hex(0x64748B),
                                     lv_color_hex(0x475569));
    RT_UNUSED(diag_button);

    g_qa_big_panel = lv_obj_create(screen);
    lv_obj_remove_style_all(g_qa_big_panel);
    lv_obj_set_size(g_qa_big_panel, 430, 34);
    style_plain_panel(g_qa_big_panel, lv_color_hex(0xEAF2FF));
    lv_obj_set_style_pad_left(g_qa_big_panel, 8, 0);
    lv_obj_set_style_pad_top(g_qa_big_panel, 8, 0);
    lv_obj_align(g_qa_big_panel, LV_ALIGN_TOP_LEFT, 22, 594);

    g_qa_big_label = lv_label_create(g_qa_big_panel);
    lv_label_set_text(g_qa_big_label, "诊断等待刷新");
    lv_obj_set_width(g_qa_big_label, 410);
    lv_label_set_long_mode(g_qa_big_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(g_qa_big_label, lv_color_hex(0x1E3A8A), 0);
    lv_obj_set_style_text_font(g_qa_big_label, panel_font(), 0);
    lv_obj_align(g_qa_big_label, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_add_flag(g_qa_big_panel, LV_OBJ_FLAG_HIDDEN);

    g_keyboard = lv_keyboard_create(screen);
    lv_keyboard_set_map(g_keyboard, LV_KEYBOARD_MODE_TEXT_LOWER, wifi_keyboard_lower_map, wifi_keyboard_text_ctrl);
    lv_keyboard_set_map(g_keyboard, LV_KEYBOARD_MODE_TEXT_UPPER, wifi_keyboard_upper_map, wifi_keyboard_text_ctrl);
    lv_keyboard_set_map(g_keyboard, LV_KEYBOARD_MODE_SPECIAL, wifi_keyboard_symbol_map, wifi_keyboard_symbol_ctrl);
    lv_keyboard_set_mode(g_keyboard, LV_KEYBOARD_MODE_TEXT_LOWER);
    lv_keyboard_set_popovers(g_keyboard, false);
    lv_obj_set_style_text_font(g_keyboard, panel_font(), 0);
    lv_obj_set_size(g_keyboard, 480, 214);
    lv_obj_align(g_keyboard, LV_ALIGN_BOTTOM_MID, 0, 0);
    (void)lv_obj_remove_event_cb(g_keyboard, lv_keyboard_def_event_cb);
    lv_obj_add_event_cb(g_keyboard, keyboard_event_cb, LV_EVENT_VALUE_CHANGED, RT_NULL);
    lv_obj_add_event_cb(g_keyboard, keyboard_event_cb, LV_EVENT_READY, RT_NULL);
    lv_obj_add_event_cb(g_keyboard, keyboard_event_cb, LV_EVENT_CANCEL, RT_NULL);
    lv_obj_add_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);

    (void)xiaozhi_ui_start_worker();
    rehab_wifi_panel_refresh_scan_list();
    rehab_wifi_panel_refresh();
    start_xiaozhi_refresh_timer();
    RT_UNUSED(snapshot);
    return RT_EOK;
}

void lv_user_gui_init(void)
{
    lv_obj_t *screen = lv_screen_active();
    lv_obj_t *title;
    lv_obj_t *hint;

    lv_obj_clean(screen);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x0F172A), 0);

    title = lv_label_create(screen);
    lv_label_set_text(title, "XiaoZhi");
    lv_obj_set_style_text_color(title, lv_color_hex(0xE0F2FE), 0);
    lv_obj_set_style_text_font(title, panel_font(), 0);
    lv_obj_align(title, LV_ALIGN_CENTER, 0, -24);

    hint = lv_label_create(screen);
    lv_label_set_text(hint, "starting...");
    lv_obj_set_style_text_color(hint, lv_color_hex(0x93C5FD), 0);
    lv_obj_set_style_text_font(hint, panel_font(), 0);
    lv_obj_align(hint, LV_ALIGN_CENTER, 0, 24);

    g_boot_panel_timer = lv_timer_create(rehab_wifi_panel_boot_timer_cb, 800, RT_NULL);
    if (g_boot_panel_timer != RT_NULL)
    {
        lv_timer_set_repeat_count(g_boot_panel_timer, 1);
    }
}

static void rehab_wifi_panel_boot_timer_cb(lv_timer_t *timer)
{
    RT_UNUSED(timer);
    g_boot_panel_timer = RT_NULL;
    (void)rehab_wifi_panel_create();
}

static void rehab_wifi_panel_cmd(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    (void)rehab_wifi_panel_create();
}
MSH_CMD_EXPORT(rehab_wifi_panel_cmd, Show Rehab Arm WiFi LVGL setup panel);

static void rehab_wifi_panel_qa_cmd(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    (void)rehab_wifi_panel_create();
    rehab_wifi_panel_run_qa_scan("cmd");
}
MSH_CMD_EXPORT(rehab_wifi_panel_qa_cmd, Open LVGL WiFi panel and start scan);

#else

rt_err_t rehab_wifi_panel_create(void)
{
    return -RT_ENOSYS;
}

#endif
