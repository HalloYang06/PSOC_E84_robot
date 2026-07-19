#ifndef __VOICE_ACTIVE_PRECHECK_H__
#define __VOICE_ACTIVE_PRECHECK_H__

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CONTROL_VOICE_PRECHECK_REJECT_NOT_INIT    (1UL << 0)
#define CONTROL_VOICE_PRECHECK_REJECT_NO_FEEDBACK (1UL << 1)
#define CONTROL_VOICE_PRECHECK_REJECT_STALE       (1UL << 2)
#define CONTROL_VOICE_PRECHECK_REJECT_PROTOCOL    (1UL << 3)
#define CONTROL_VOICE_PRECHECK_REJECT_ID          (1UL << 4)
#define CONTROL_VOICE_PRECHECK_REJECT_CALIBRATION (1UL << 5)
#define CONTROL_VOICE_PRECHECK_REJECT_FAULT       (1UL << 6)
#define CONTROL_VOICE_PRECHECK_REJECT_MODE        (1UL << 7)

typedef struct
{
    rt_bool_t passed;
    rt_uint32_t reason_mask;
    rt_uint32_t age_ms;
    rt_uint8_t fault_summary;
    rt_uint8_t mode_state;
    rt_uint8_t protocol;
    rt_uint8_t joint_id;
    rt_uint8_t motor_id;
    rt_tick_t assessment_tick;
} control_voice_precheck_result_t;

typedef struct
{
    rt_uint32_t total;
    rt_uint32_t pass;
    rt_uint32_t reject_not_init;
    rt_uint32_t reject_no_feedback;
    rt_uint32_t reject_stale;
    rt_uint32_t reject_protocol;
    rt_uint32_t reject_id;
    rt_uint32_t reject_calibration;
    rt_uint32_t reject_fault;
    rt_uint32_t reject_mode;
    control_voice_precheck_result_t last;
} control_voice_precheck_diag_t;

/* Read-only gate for a future voice request consumer. It never commands motion. */
rt_err_t control_voice_precheck_assess(control_voice_precheck_result_t *out);
void control_voice_precheck_diag_snapshot(control_voice_precheck_diag_t *out);

#ifdef __cplusplus
}
#endif

#endif
