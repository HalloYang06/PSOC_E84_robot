#include "rehab_wifi_panel.h"
#include "wifi_config_service.h"

#ifdef BSP_USING_LVGL

#include <lvgl.h>
#include <finsh.h>
#include <stdio.h>
#include <string.h>

static lv_obj_t *g_status_label;
static lv_obj_t *g_ap_list;
static lv_obj_t *g_ssid_textarea;
static lv_obj_t *g_password_textarea;
static lv_obj_t *g_auto_checkbox;
static lv_obj_t *g_keyboard;
static lv_timer_t *g_scan_refresh_timer;

static void rehab_wifi_panel_refresh_scan_list(void);

static void rehab_wifi_panel_refresh(void)
{
    wifi_config_snapshot_t snapshot;
    char status[320];

    if (g_status_label == RT_NULL)
    {
        return;
    }

    wifi_config_get_snapshot(&snapshot);
    rt_snprintf(status,
                sizeof(status),
                "WiFi: %s  ready:%lu  rssi:%ld\nnetdev:%s flags:0x%lx\nWHD stage:%ld result:%ld\nsaved:%lu auto:%lu storage:%ld\nlast:%ld scan:%ld",
                snapshot.wlan_connected ? "connected" : "offline",
                (unsigned long)snapshot.wlan_ready,
                (long)snapshot.wlan_rssi,
                snapshot.netdev_name[0] ? snapshot.netdev_name : "none",
                (unsigned long)snapshot.netdev_flags,
                (long)snapshot.whd_stage,
                (long)snapshot.whd_result,
                (unsigned long)snapshot.saved,
                (unsigned long)snapshot.auto_connect,
                (long)snapshot.storage_result,
                (long)snapshot.last_result,
                (long)snapshot.scan_count);
    lv_label_set_text(g_status_label, status);
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
        lv_obj_t *button = lv_list_add_button(g_ap_list, LV_SYMBOL_WIFI, "No scanned networks. Tap Scan.");
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
                    "%s  %lddBm  %s  ch%ld",
                    ap.ssid[0] ? ap.ssid : "(hidden)",
                    (long)ap.rssi,
                    wifi_config_security_name(ap.security),
                    (long)ap.channel);
        button = lv_list_add_button(g_ap_list, LV_SYMBOL_WIFI, row);
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
        lv_timer_set_repeat_count(g_scan_refresh_timer, 10);
        lv_timer_set_auto_delete(g_scan_refresh_timer, false);
    }
}

static void keyboard_target_event_cb(lv_event_t *event)
{
    lv_event_code_t code = lv_event_get_code(event);

    if ((code == LV_EVENT_FOCUSED) && (g_keyboard != RT_NULL))
    {
        lv_keyboard_set_textarea(g_keyboard, lv_event_get_target(event));
        lv_obj_remove_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);
    }
    else if ((code == LV_EVENT_DEFOCUSED) && (g_keyboard != RT_NULL))
    {
        lv_keyboard_set_textarea(g_keyboard, RT_NULL);
        lv_obj_add_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);
    }
}

static void scan_event_cb(lv_event_t *event)
{
    RT_UNUSED(event);
    (void)wifi_config_scan();
    (void)wifi_config_whd_diag();
    rehab_wifi_panel_refresh_scan_list();
    rehab_wifi_panel_refresh();
    start_scan_refresh_timer();
}

static void diag_event_cb(lv_event_t *event)
{
    RT_UNUSED(event);
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
    (void)wifi_config_set_ssid(ssid);
    (void)wifi_config_set_password(password);
    (void)wifi_config_set_auto_connect(auto_connect);
    (void)wifi_config_save();
    (void)wifi_config_connect();
    (void)wifi_config_whd_diag();
    rehab_wifi_panel_refresh();
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

static lv_obj_t *panel_button(lv_obj_t *parent, const char *text, lv_event_cb_t cb)
{
    lv_obj_t *button = lv_button_create(parent);
    lv_obj_t *label;

    lv_obj_set_size(button, 96, 42);
    lv_obj_add_event_cb(button, cb, LV_EVENT_CLICKED, RT_NULL);

    label = lv_label_create(button);
    lv_label_set_text(label, text);
    lv_obj_center(label);
    return button;
}

rt_err_t rehab_wifi_panel_create(void)
{
    lv_obj_t *screen = lv_screen_active();
    lv_obj_t *title;
    lv_obj_t *row;
    wifi_config_snapshot_t snapshot;

    (void)wifi_config_service_init();
    wifi_config_get_snapshot(&snapshot);

    lv_obj_clean(screen);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101820), 0);

    title = lv_label_create(screen);
    lv_label_set_text(title, "Rehab Arm WiFi Setup");
    lv_obj_set_style_text_color(title, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_24, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 14);

    g_status_label = lv_label_create(screen);
    lv_obj_set_width(g_status_label, 430);
    lv_obj_set_style_text_color(g_status_label, lv_color_hex(0xD5E8D4), 0);
    lv_obj_set_style_text_font(g_status_label, &lv_font_montserrat_14, 0);
    lv_obj_align(g_status_label, LV_ALIGN_TOP_LEFT, 24, 48);

    g_ap_list = lv_list_create(screen);
    lv_obj_set_size(g_ap_list, 430, 96);
    lv_obj_set_style_bg_color(g_ap_list, lv_color_hex(0x182832), 0);
    lv_obj_set_style_border_color(g_ap_list, lv_color_hex(0x2E5266), 0);
    lv_obj_set_style_border_width(g_ap_list, 1, 0);
    lv_obj_align(g_ap_list, LV_ALIGN_TOP_LEFT, 24, 136);

    g_ssid_textarea = lv_textarea_create(screen);
    lv_textarea_set_one_line(g_ssid_textarea, true);
    lv_textarea_set_placeholder_text(g_ssid_textarea, "SSID");
    if (snapshot.ssid[0] != '\0')
    {
        lv_textarea_set_text(g_ssid_textarea, snapshot.ssid);
    }
    lv_obj_set_size(g_ssid_textarea, 280, 42);
    lv_obj_align(g_ssid_textarea, LV_ALIGN_TOP_LEFT, 24, 240);
    lv_obj_add_event_cb(g_ssid_textarea, keyboard_target_event_cb, LV_EVENT_ALL, RT_NULL);

    g_password_textarea = lv_textarea_create(screen);
    lv_textarea_set_one_line(g_password_textarea, true);
    lv_textarea_set_password_mode(g_password_textarea, true);
    lv_textarea_set_placeholder_text(g_password_textarea, "Password");
    if (snapshot.password[0] != '\0')
    {
        lv_textarea_set_text(g_password_textarea, snapshot.password);
    }
    lv_obj_set_size(g_password_textarea, 280, 42);
    lv_obj_align(g_password_textarea, LV_ALIGN_TOP_LEFT, 24, 288);
    lv_obj_add_event_cb(g_password_textarea, keyboard_target_event_cb, LV_EVENT_ALL, RT_NULL);

    g_auto_checkbox = lv_checkbox_create(screen);
    lv_checkbox_set_text(g_auto_checkbox, "Auto connect");
    lv_obj_set_style_text_color(g_auto_checkbox, lv_color_hex(0xFFFFFF), 0);
    if (snapshot.auto_connect)
    {
        lv_obj_add_state(g_auto_checkbox, LV_STATE_CHECKED);
    }
    lv_obj_align(g_auto_checkbox, LV_ALIGN_TOP_LEFT, 318, 247);

    row = lv_obj_create(screen);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, 430, 50);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(row, 8, 0);
    lv_obj_align(row, LV_ALIGN_TOP_LEFT, 24, 340);
    (void)panel_button(row, "Scan", scan_event_cb);
    (void)panel_button(row, "Diag", diag_event_cb);
    (void)panel_button(row, "Save", save_event_cb);
    (void)panel_button(row, "Connect", connect_event_cb);

    row = lv_obj_create(screen);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, 430, 50);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(row, 8, 0);
    lv_obj_align(row, LV_ALIGN_TOP_LEFT, 24, 394);
    (void)panel_button(row, "Off", disconnect_event_cb);
    (void)panel_button(row, "Forget", forget_event_cb);

    g_keyboard = lv_keyboard_create(screen);
    lv_obj_set_size(g_keyboard, 480, 150);
    lv_obj_align(g_keyboard, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_add_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);

    (void)wifi_config_whd_diag();
    rehab_wifi_panel_refresh_scan_list();
    rehab_wifi_panel_refresh();
    return RT_EOK;
}

void lv_user_gui_init(void)
{
    (void)rehab_wifi_panel_create();
}

static void rehab_wifi_panel_cmd(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);
    (void)rehab_wifi_panel_create();
}
MSH_CMD_EXPORT(rehab_wifi_panel_cmd, Show Rehab Arm WiFi LVGL setup panel);

#else

rt_err_t rehab_wifi_panel_create(void)
{
    return -RT_ENOSYS;
}

#endif
