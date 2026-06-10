#include "rehab_wifi_panel.h"
#include "wifi_config_service.h"

#ifdef BSP_USING_LVGL

#include <lvgl.h>
#include <finsh.h>
#include <stdio.h>
#include <string.h>

static lv_obj_t *g_status_label;
static lv_obj_t *g_ssid_textarea;
static lv_obj_t *g_password_textarea;
static lv_obj_t *g_auto_checkbox;
static lv_obj_t *g_keyboard;

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
    rehab_wifi_panel_refresh();
}

static void diag_event_cb(lv_event_t *event)
{
    RT_UNUSED(event);
    (void)wifi_config_diag();
    (void)wifi_config_whd_diag();
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
    lv_obj_align(g_status_label, LV_ALIGN_TOP_LEFT, 24, 52);

    g_ssid_textarea = lv_textarea_create(screen);
    lv_textarea_set_one_line(g_ssid_textarea, true);
    lv_textarea_set_placeholder_text(g_ssid_textarea, "SSID");
    if (snapshot.ssid[0] != '\0')
    {
        lv_textarea_set_text(g_ssid_textarea, snapshot.ssid);
    }
    lv_obj_set_size(g_ssid_textarea, 280, 42);
    lv_obj_align(g_ssid_textarea, LV_ALIGN_TOP_LEFT, 24, 170);
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
    lv_obj_align(g_password_textarea, LV_ALIGN_TOP_LEFT, 24, 220);
    lv_obj_add_event_cb(g_password_textarea, keyboard_target_event_cb, LV_EVENT_ALL, RT_NULL);

    g_auto_checkbox = lv_checkbox_create(screen);
    lv_checkbox_set_text(g_auto_checkbox, "Auto connect");
    lv_obj_set_style_text_color(g_auto_checkbox, lv_color_hex(0xFFFFFF), 0);
    if (snapshot.auto_connect)
    {
        lv_obj_add_state(g_auto_checkbox, LV_STATE_CHECKED);
    }
    lv_obj_align(g_auto_checkbox, LV_ALIGN_TOP_LEFT, 318, 177);

    row = lv_obj_create(screen);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, 430, 50);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(row, 8, 0);
    lv_obj_align(row, LV_ALIGN_TOP_LEFT, 24, 272);
    (void)panel_button(row, "Scan", scan_event_cb);
    (void)panel_button(row, "Diag", diag_event_cb);
    (void)panel_button(row, "Save", save_event_cb);
    (void)panel_button(row, "Connect", connect_event_cb);

    row = lv_obj_create(screen);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, 430, 50);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(row, 8, 0);
    lv_obj_align(row, LV_ALIGN_TOP_LEFT, 24, 326);
    (void)panel_button(row, "Off", disconnect_event_cb);
    (void)panel_button(row, "Forget", forget_event_cb);

    g_keyboard = lv_keyboard_create(screen);
    lv_obj_set_size(g_keyboard, 480, 150);
    lv_obj_align(g_keyboard, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_add_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);

    (void)wifi_config_whd_diag();
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
