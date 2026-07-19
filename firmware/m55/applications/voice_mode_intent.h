#ifndef VOICE_MODE_INTENT_H
#define VOICE_MODE_INTENT_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef uint32_t voice_mode_event_source_t;
#define VOICE_MODE_EVENT_UNTRUSTED           UINT32_C(0)
#define VOICE_MODE_EVENT_XIAOZHI_VLA_CONTROL UINT32_C(1)
#define VOICE_MODE_EVENT_RAW_STT              UINT32_C(2)

typedef uint32_t voice_rehab_mode_t;
#define VOICE_REHAB_MODE_PASSIVE UINT32_C(0)
#define VOICE_REHAB_MODE_ASSIST  UINT32_C(3)
#define VOICE_REHAB_MODE_RESIST  UINT32_C(4)
#define VOICE_REHAB_MODE_INVALID UINT32_MAX

typedef uint32_t voice_rehab_action_t;
#define VOICE_REHAB_ACTION_SET_MODE   UINT32_C(0)
#define VOICE_REHAB_ACTION_LEVEL_UP   UINT32_C(1)
#define VOICE_REHAB_ACTION_LEVEL_DOWN UINT32_C(2)

typedef struct
{
    voice_rehab_mode_t mode;
    voice_rehab_action_t action;
    uint8_t joint_mask;
    /* diagnostic/equality fingerprint only; never use as boot epoch or request ID. */
    uint32_t event_fingerprint;
} voice_mode_request_t;

bool voice_mode_intent_classify(voice_mode_event_source_t source,
                                const char *event_id,
                                const char *payload,
                                voice_mode_request_t *request);

#ifdef __cplusplus
}
#endif

#endif
