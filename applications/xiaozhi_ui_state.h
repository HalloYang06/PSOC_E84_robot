#ifndef XIAOZHI_UI_STATE_H
#define XIAOZHI_UI_STATE_H

#include <rtthread.h>

#define XIAOZHI_UI_TEXT_MAX 160

typedef enum
{
    XIAOZHI_UI_OFFLINE = 0,
    XIAOZHI_UI_WAIT_NETWORK,
    XIAOZHI_UI_CONNECTING,
    XIAOZHI_UI_READY,
    XIAOZHI_UI_LISTENING,
    XIAOZHI_UI_THINKING,
    XIAOZHI_UI_SPEAKING,
    XIAOZHI_UI_ERROR
} xiaozhi_ui_phase_t;

typedef struct
{
    xiaozhi_ui_phase_t phase;
    rt_uint32_t updated_ms;
    rt_uint32_t wake_count;
    rt_uint32_t reply_count;
    rt_int32_t last_error;
    char detail[XIAOZHI_UI_TEXT_MAX];
    char last_reply[XIAOZHI_UI_TEXT_MAX];
} xiaozhi_ui_snapshot_t;

void xiaozhi_ui_state_set(xiaozhi_ui_phase_t phase, const char *detail, rt_int32_t err);
void xiaozhi_ui_state_set_reply(const char *reply);
void xiaozhi_ui_state_mark_wake(const char *wake_word);
void xiaozhi_ui_state_snapshot(xiaozhi_ui_snapshot_t *snapshot);
const char *xiaozhi_ui_phase_text(xiaozhi_ui_phase_t phase);

#endif
