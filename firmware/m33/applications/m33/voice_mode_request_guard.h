#ifndef VOICE_MODE_REQUEST_GUARD_H
#define VOICE_MODE_REQUEST_GUARD_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define VOICE_MODE_JOINT_MASK UINT32_C(0x38)
#define VOICE_MODE_MAX_TTL_MS UINT32_C(500)

typedef uint32_t voice_mode_source_t;
#define VOICE_MODE_SOURCE_VOICE UINT32_C(1)

typedef uint32_t voice_mode_target_t;
#define VOICE_MODE_PASSIVE UINT32_C(0)
#define VOICE_MODE_ASSIST  UINT32_C(3)
#define VOICE_MODE_RESIST  UINT32_C(4)

typedef uint32_t voice_mode_current_t;
#define VOICE_MODE_CURRENT_PASSIVE      VOICE_MODE_PASSIVE
#define VOICE_MODE_CURRENT_ASSIST       VOICE_MODE_ASSIST
#define VOICE_MODE_CURRENT_RESIST       VOICE_MODE_RESIST
#define VOICE_MODE_CURRENT_OTHER_ACTIVE UINT32_MAX

typedef uint32_t voice_mode_decision_t;
#define VOICE_MODE_DECISION_REJECT_INVALID      UINT32_C(0)
#define VOICE_MODE_DECISION_REJECT_EXPIRED      UINT32_C(1)
#define VOICE_MODE_DECISION_REJECT_DUPLICATE    UINT32_C(2)
#define VOICE_MODE_DECISION_REJECT_STALE        UINT32_C(3)
#define VOICE_MODE_DECISION_REJECT_PRECONDITION UINT32_C(4)
#define VOICE_MODE_DECISION_NEEDS_PASSIVE       UINT32_C(5)
#define VOICE_MODE_DECISION_NEEDS_REARM         UINT32_C(6)
#define VOICE_MODE_DECISION_REJECT_EPOCH        UINT32_C(7)
#define VOICE_MODE_DECISION_ALREADY_ACTIVE      UINT32_C(8)
#define VOICE_MODE_DECISION_APPLY_PASSIVE       UINT32_C(9)
#define VOICE_MODE_DECISION_APPLY_ACTIVE        UINT32_C(10)

typedef struct
{
    voice_mode_source_t source;
    uint32_t boot_epoch;
    uint32_t request_id;
    uint32_t joint_mask;
    voice_mode_target_t target_mode;
    uint32_t received_tick;
    uint32_t ttl_ms;
} voice_mode_request_t;

typedef struct
{
    uint32_t trusted_epoch;
    uint32_t committed_request_id;
} voice_mode_guard_t;

void voice_mode_guard_init(voice_mode_guard_t *guard);

uint32_t voice_mode_guard_accept_epoch(voice_mode_guard_t *guard,
                                       uint32_t boot_epoch,
                                       voice_mode_current_t current_mode,
                                       uint32_t owner_action_active);

voice_mode_decision_t voice_mode_guard_decide(
    const voice_mode_guard_t *guard,
    const voice_mode_request_t *request,
    uint32_t now_tick,
    uint32_t tick_hz,
    voice_mode_current_t current_mode,
    uint32_t owner_action_active,
    uint32_t active_preconditions_met);

/* Commit only after the caller has successfully applied the decision. */
uint32_t voice_mode_guard_commit(voice_mode_guard_t *guard,
                                 const voice_mode_request_t *request,
                                 voice_mode_decision_t decision);

#ifdef __cplusplus
}
#endif

#endif
