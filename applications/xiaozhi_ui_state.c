#include "xiaozhi_ui_state.h"

#include <string.h>

typedef struct
{
    rt_bool_t lock_ready;
    struct rt_mutex lock;
    xiaozhi_ui_snapshot_t snapshot;
} xiaozhi_ui_state_t;

static xiaozhi_ui_state_t g_xiaozhi_ui;

static void xiaozhi_ui_state_init_once(void)
{
    if (g_xiaozhi_ui.lock_ready)
    {
        return;
    }

    rt_memset(&g_xiaozhi_ui, 0, sizeof(g_xiaozhi_ui));
    rt_mutex_init(&g_xiaozhi_ui.lock, "xz_ui", RT_IPC_FLAG_PRIO);
    g_xiaozhi_ui.snapshot.phase = XIAOZHI_UI_OFFLINE;
    rt_strncpy(g_xiaozhi_ui.snapshot.detail, "等待网络", sizeof(g_xiaozhi_ui.snapshot.detail) - 1);
    g_xiaozhi_ui.lock_ready = RT_TRUE;
}

static void copy_text(char *dst, rt_size_t dst_size, const char *src)
{
    rt_size_t i;
    rt_size_t last_safe = 0;

    if ((dst == RT_NULL) || (dst_size == 0U))
    {
        return;
    }

    dst[0] = '\0';
    if (src != RT_NULL)
    {
        for (i = 0; (src[i] != '\0') && (i < dst_size - 1U); i++)
        {
            dst[i] = src[i];
            if (((rt_uint8_t)src[i] & 0xC0U) != 0x80U)
            {
                last_safe = i;
            }
        }

        if (src[i] == '\0')
        {
            dst[i] = '\0';
            return;
        }

        dst[last_safe] = '\0';
    }
}

void xiaozhi_ui_state_set(xiaozhi_ui_phase_t phase, const char *detail, rt_int32_t err)
{
    xiaozhi_ui_state_init_once();

    rt_mutex_take(&g_xiaozhi_ui.lock, RT_WAITING_FOREVER);
    g_xiaozhi_ui.snapshot.phase = phase;
    g_xiaozhi_ui.snapshot.updated_ms = (rt_uint32_t)rt_tick_get_millisecond();
    g_xiaozhi_ui.snapshot.last_error = err;
    if (detail != RT_NULL)
    {
        copy_text(g_xiaozhi_ui.snapshot.detail, sizeof(g_xiaozhi_ui.snapshot.detail), detail);
    }
    rt_mutex_release(&g_xiaozhi_ui.lock);
}

void xiaozhi_ui_state_set_reply(const char *reply)
{
    xiaozhi_ui_state_init_once();

    rt_mutex_take(&g_xiaozhi_ui.lock, RT_WAITING_FOREVER);
    g_xiaozhi_ui.snapshot.phase = XIAOZHI_UI_SPEAKING;
    g_xiaozhi_ui.snapshot.updated_ms = (rt_uint32_t)rt_tick_get_millisecond();
    g_xiaozhi_ui.snapshot.reply_count++;
    copy_text(g_xiaozhi_ui.snapshot.detail, sizeof(g_xiaozhi_ui.snapshot.detail), "正在回答");
    copy_text(g_xiaozhi_ui.snapshot.last_reply, sizeof(g_xiaozhi_ui.snapshot.last_reply), reply);
    rt_mutex_release(&g_xiaozhi_ui.lock);
}

void xiaozhi_ui_state_mark_wake(const char *wake_word)
{
    xiaozhi_ui_state_init_once();

    rt_mutex_take(&g_xiaozhi_ui.lock, RT_WAITING_FOREVER);
    g_xiaozhi_ui.snapshot.phase = XIAOZHI_UI_LISTENING;
    g_xiaozhi_ui.snapshot.updated_ms = (rt_uint32_t)rt_tick_get_millisecond();
    g_xiaozhi_ui.snapshot.wake_count++;
    copy_text(g_xiaozhi_ui.snapshot.detail,
              sizeof(g_xiaozhi_ui.snapshot.detail),
              (wake_word && wake_word[0]) ? wake_word : "我在听");
    rt_mutex_release(&g_xiaozhi_ui.lock);
}

void xiaozhi_ui_state_snapshot(xiaozhi_ui_snapshot_t *snapshot)
{
    if (snapshot == RT_NULL)
    {
        return;
    }

    xiaozhi_ui_state_init_once();

    rt_mutex_take(&g_xiaozhi_ui.lock, RT_WAITING_FOREVER);
    *snapshot = g_xiaozhi_ui.snapshot;
    rt_mutex_release(&g_xiaozhi_ui.lock);
}

const char *xiaozhi_ui_phase_text(xiaozhi_ui_phase_t phase)
{
    switch (phase)
    {
    case XIAOZHI_UI_WAIT_NETWORK:
        return "等待网络";
    case XIAOZHI_UI_CONNECTING:
        return "连接中";
    case XIAOZHI_UI_READY:
        return "在线待唤醒";
    case XIAOZHI_UI_LISTENING:
        return "我在听";
    case XIAOZHI_UI_THINKING:
        return "正在思考";
    case XIAOZHI_UI_SPEAKING:
        return "正在回答";
    case XIAOZHI_UI_ERROR:
        return "连接异常";
    case XIAOZHI_UI_OFFLINE:
    default:
        return "离线";
    }
}
