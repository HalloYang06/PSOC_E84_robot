#include "voice_mode_intent.h"

#include <string.h>

#define VOICE_MODE_EVENT_ID_MAX_LEN 64U
#define VOICE_MODE_ALLOWED_JOINT_MASK UINT8_C(0x38)

static bool voice_mode_event_id_valid(const char *event_id)
{
    size_t i;

    if ((event_id == NULL) || (event_id[0] == '\0'))
    {
        return false;
    }

    for (i = 0U; event_id[i] != '\0'; i++)
    {
        const char c = event_id[i];

        if (i >= VOICE_MODE_EVENT_ID_MAX_LEN)
        {
            return false;
        }
        if (!(((c >= 'a') && (c <= 'z')) ||
              ((c >= 'A') && (c <= 'Z')) ||
              ((c >= '0') && (c <= '9')) ||
              (c == '-') || (c == '_') || (c == '.') || (c == ':')))
        {
            return false;
        }
    }

    return true;
}

static uint32_t voice_mode_hash_byte(uint32_t hash, uint8_t value)
{
    return (hash ^ value) * UINT32_C(16777619);
}

static uint32_t voice_mode_event_fingerprint(const char *event_id, const char *payload)
{
    uint32_t hash = UINT32_C(2166136261);
    const unsigned char *cursor;

    for (cursor = (const unsigned char *)event_id; *cursor != '\0'; cursor++)
    {
        hash = voice_mode_hash_byte(hash, *cursor);
    }
    hash = voice_mode_hash_byte(hash, 0U);
    for (cursor = (const unsigned char *)payload; *cursor != '\0'; cursor++)
    {
        hash = voice_mode_hash_byte(hash, *cursor);
    }

    return (hash == 0U) ? UINT32_C(1) : hash;
}

typedef struct
{
    const char *payload;
    voice_rehab_mode_t mode;
    voice_rehab_action_t action;
} voice_mode_allowlist_entry_t;

static const voice_mode_allowlist_entry_t g_voice_mode_allowlist[] =
{
    {"rehab.set_mode joints=4,5,6 mode=assist", VOICE_REHAB_MODE_ASSIST, VOICE_REHAB_ACTION_SET_MODE},
    {"rehab.set_mode joints=4,5,6 mode=resist", VOICE_REHAB_MODE_RESIST, VOICE_REHAB_ACTION_SET_MODE},
    {"rehab.adjust_level mode=assist delta=1", VOICE_REHAB_MODE_ASSIST, VOICE_REHAB_ACTION_LEVEL_UP},
    {"rehab.adjust_level mode=assist delta=-1", VOICE_REHAB_MODE_ASSIST, VOICE_REHAB_ACTION_LEVEL_DOWN},
    {"rehab.adjust_level mode=resist delta=1", VOICE_REHAB_MODE_RESIST, VOICE_REHAB_ACTION_LEVEL_UP},
    {"rehab.adjust_level mode=resist delta=-1", VOICE_REHAB_MODE_RESIST, VOICE_REHAB_ACTION_LEVEL_DOWN},
    {"切换助力模式", VOICE_REHAB_MODE_ASSIST, VOICE_REHAB_ACTION_SET_MODE},
    {"切换抗阻模式", VOICE_REHAB_MODE_RESIST, VOICE_REHAB_ACTION_SET_MODE},
    {"提高助力挡位", VOICE_REHAB_MODE_ASSIST, VOICE_REHAB_ACTION_LEVEL_UP},
    {"降低助力挡位", VOICE_REHAB_MODE_ASSIST, VOICE_REHAB_ACTION_LEVEL_DOWN},
    {"提高抗阻挡位", VOICE_REHAB_MODE_RESIST, VOICE_REHAB_ACTION_LEVEL_UP},
    {"降低抗阻挡位", VOICE_REHAB_MODE_RESIST, VOICE_REHAB_ACTION_LEVEL_DOWN},
    {"提高助力档位", VOICE_REHAB_MODE_ASSIST, VOICE_REHAB_ACTION_LEVEL_UP},
    {"降低助力档位", VOICE_REHAB_MODE_ASSIST, VOICE_REHAB_ACTION_LEVEL_DOWN},
    {"提高抗阻档位", VOICE_REHAB_MODE_RESIST, VOICE_REHAB_ACTION_LEVEL_UP},
    {"降低抗阻档位", VOICE_REHAB_MODE_RESIST, VOICE_REHAB_ACTION_LEVEL_DOWN}
};

static bool voice_mode_match_allowlist(const char *payload,
                                       voice_rehab_mode_t *mode,
                                       voice_rehab_action_t *action)
{
    size_t index;

    for (index = 0U;
         index < (sizeof(g_voice_mode_allowlist) / sizeof(g_voice_mode_allowlist[0]));
         index++)
    {
        if (strcmp(payload, g_voice_mode_allowlist[index].payload) == 0)
        {
            *mode = g_voice_mode_allowlist[index].mode;
            *action = g_voice_mode_allowlist[index].action;
            return true;
        }
    }

    return false;
}

bool voice_mode_intent_classify(voice_mode_event_source_t source,
                                const char *event_id,
                                const char *payload,
                                voice_mode_request_t *request)
{
    voice_rehab_mode_t mode = VOICE_REHAB_MODE_INVALID;
    voice_rehab_action_t action = VOICE_REHAB_ACTION_SET_MODE;

    if (request != NULL)
    {
        memset(request, 0, sizeof(*request));
        request->mode = VOICE_REHAB_MODE_INVALID;
    }
    if ((source != VOICE_MODE_EVENT_XIAOZHI_VLA_CONTROL) ||
        !voice_mode_event_id_valid(event_id) ||
        (payload == NULL) || (payload[0] == '\0') ||
        (request == NULL))
    {
        return false;
    }

    if (!voice_mode_match_allowlist(payload, &mode, &action))
    {
        return false;
    }

    request->mode = mode;
    request->action = action;
    request->joint_mask = VOICE_MODE_ALLOWED_JOINT_MASK;
    request->event_fingerprint = voice_mode_event_fingerprint(event_id, payload);
    return true;
}
