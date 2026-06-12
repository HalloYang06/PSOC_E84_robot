#include "rehab_wifi_panel.h"
#include "wifi_config_service.h"

#ifdef BSP_USING_LVGL

#include <lvgl.h>
#include <finsh.h>
#include <stdio.h>
#include <string.h>

static lv_obj_t *g_status_label;
static lv_obj_t *g_ap_list;
static lv_obj_t *g_qa_big_panel;
static lv_obj_t *g_qa_big_label;
static lv_obj_t *g_ssid_textarea;
static lv_obj_t *g_password_textarea;
static lv_obj_t *g_auto_checkbox;
static lv_obj_t *g_keyboard;
static lv_obj_t *g_keyboard_target;
static lv_timer_t *g_scan_refresh_timer;
static lv_timer_t *g_auto_qa_timer;
static rt_thread_t g_connect_thread;
static rt_bool_t g_connect_in_progress;
static rt_bool_t g_diag_visible;
static rt_bool_t g_auto_qa_done;

LV_FONT_DECLARE(rehab_wifi_font);

static void rehab_wifi_panel_refresh_scan_list(void);
static lv_obj_t *panel_button(lv_obj_t *parent, const char *text, lv_event_cb_t cb);
static void start_scan_refresh_timer(void);
static void rehab_wifi_panel_run_qa_scan(const char *source);

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

static const char *wifi_hint_text(const wifi_config_snapshot_t *snapshot)
{
    if (g_connect_in_progress)
    {
        return "正在连接路由器";
    }
    if (snapshot->wlan_connected)
    {
        return "网络已连接";
    }
    if (!wifi_scan_available(snapshot))
    {
        return "WiFi未就绪";
    }
    if (snapshot->ssid[0] == '\0')
    {
        return "请选择网络或手动输入";
    }
    if (snapshot->last_result != RT_EOK)
    {
        return "连接失败请检查密码";
    }
    return "输入密码后连接";
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
    char status[128];
    char qa[128];

    if (g_status_label == RT_NULL)
    {
        return;
    }

    (void)wifi_config_whd_diag();
    wifi_config_get_snapshot(&snapshot);
    rt_snprintf(status,
                sizeof(status),
                "%s  %ld个网络\n%s",
                wifi_state_text(&snapshot),
                (long)snapshot.scan_count,
                wifi_hint_text(&snapshot));
    lv_label_set_text(g_status_label, status);

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

static void connect_thread_entry(void *parameter)
{
    RT_UNUSED(parameter);
    (void)wifi_config_save();
    (void)wifi_config_connect();
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
                "rehab-arm://provision?project_id=fd6a55ed-a63c-44b3-b123-96fb3c154966&device_id=nanopi-m5&robot_id=rehab-arm-alpha&transport=ble");

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
    (void)panel_button(back_row, "返回", back_to_wifi_panel_event_cb);
    (void)panel_button(back_row, "刷新", qr_event_cb);
}
#endif

static lv_obj_t *panel_button(lv_obj_t *parent, const char *text, lv_event_cb_t cb)
{
    lv_obj_t *button = lv_button_create(parent);
    lv_obj_t *label;

    lv_obj_set_size(button, 124, 46);
    lv_obj_add_event_cb(button, cb, LV_EVENT_CLICKED, RT_NULL);
    lv_obj_set_style_radius(button, 6, 0);
    lv_obj_set_style_bg_color(button, lv_color_hex(0x2563EB), 0);
    lv_obj_set_style_bg_color(button, lv_color_hex(0x1D4ED8), LV_STATE_PRESSED);

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
    lv_obj_t *row;
    lv_obj_t *diag_button;
    wifi_config_snapshot_t snapshot;

    (void)wifi_config_service_init();
    wifi_config_get_snapshot(&snapshot);

    lv_obj_clean(screen);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0xF4F7F8), 0);

    title = lv_label_create(screen);
    lv_label_set_text(title, "机械臂配网");
    lv_obj_set_style_text_color(title, lv_color_hex(0x111827), 0);
    lv_obj_set_style_text_font(title, panel_font(), 0);
    lv_obj_align(title, LV_ALIGN_TOP_LEFT, 22, 16);

    g_status_label = lv_label_create(screen);
    lv_obj_set_width(g_status_label, 430);
    lv_obj_set_style_text_color(g_status_label, lv_color_hex(0x1F2937), 0);
    lv_obj_set_style_text_font(g_status_label, panel_font(), 0);
    lv_obj_set_style_text_line_space(g_status_label, 4, 0);
    lv_label_set_long_mode(g_status_label, LV_LABEL_LONG_WRAP);
    lv_obj_align(g_status_label, LV_ALIGN_TOP_LEFT, 22, 54);

    g_ap_list = lv_list_create(screen);
    lv_obj_set_size(g_ap_list, 430, 188);
    style_plain_panel(g_ap_list, lv_color_hex(0xFFFFFF));
    lv_obj_set_style_pad_all(g_ap_list, 6, 0);
    lv_obj_align(g_ap_list, LV_ALIGN_TOP_LEFT, 22, 138);

    g_ssid_textarea = lv_textarea_create(screen);
    lv_textarea_set_one_line(g_ssid_textarea, true);
    lv_textarea_set_placeholder_text(g_ssid_textarea, "WiFi名称");
    if (snapshot.ssid[0] != '\0')
    {
        lv_textarea_set_text(g_ssid_textarea, snapshot.ssid);
    }
    lv_obj_set_size(g_ssid_textarea, 430, 46);
    lv_obj_set_style_text_font(g_ssid_textarea, panel_font(), 0);
    style_plain_panel(g_ssid_textarea, lv_color_hex(0xFFFFFF));
    lv_obj_align(g_ssid_textarea, LV_ALIGN_TOP_LEFT, 22, 340);
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
    lv_obj_set_size(g_password_textarea, 430, 46);
    lv_obj_set_style_text_font(g_password_textarea, panel_font(), 0);
    style_plain_panel(g_password_textarea, lv_color_hex(0xFFFFFF));
    lv_obj_align(g_password_textarea, LV_ALIGN_TOP_LEFT, 22, 392);
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
    lv_obj_align(g_auto_checkbox, LV_ALIGN_TOP_LEFT, 26, 444);

    row = lv_obj_create(screen);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, 430, 50);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(row, 14, 0);
    lv_obj_align(row, LV_ALIGN_TOP_LEFT, 22, 480);
    (void)panel_button(row, "扫描", scan_event_cb);
    (void)panel_button(row, "连接", connect_event_cb);
    (void)panel_button(row, "保存", save_event_cb);

    row = lv_obj_create(screen);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, 430, 50);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(row, 14, 0);
    lv_obj_align(row, LV_ALIGN_TOP_LEFT, 22, 536);
    (void)panel_button(row, "清除", forget_event_cb);
    (void)panel_button(row, "断开", disconnect_event_cb);
    diag_button = panel_button(row, g_diag_visible ? "隐藏" : "诊断", diag_event_cb);
    RT_UNUSED(diag_button);

    g_qa_big_panel = lv_obj_create(screen);
    lv_obj_remove_style_all(g_qa_big_panel);
    lv_obj_set_size(g_qa_big_panel, 430, 42);
    style_plain_panel(g_qa_big_panel, lv_color_hex(0xEAF2FF));
    lv_obj_set_style_pad_left(g_qa_big_panel, 8, 0);
    lv_obj_set_style_pad_top(g_qa_big_panel, 8, 0);
    lv_obj_align(g_qa_big_panel, LV_ALIGN_TOP_LEFT, 22, 592);

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

    rehab_wifi_panel_refresh_scan_list();
    rehab_wifi_panel_refresh();
    if (wifi_scan_available(&snapshot) && (snapshot.scan_request_count == 0U) && (snapshot.scan_running == 0U))
    {
        (void)wifi_config_scan();
        start_scan_refresh_timer();
    }
    return RT_EOK;
}

void lv_user_gui_init(void)
{
    (void)rehab_wifi_panel_create();
    start_auto_qa_timer();
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
