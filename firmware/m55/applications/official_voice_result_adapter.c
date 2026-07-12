#include "official_voice_result_adapter.h"

#include "model_result_publisher.h"

#define VOICE_ASR_RESULT_NONE              0U
#define VOICE_ASR_RESULT_START_REQUEST     1U
#define VOICE_ASR_RESULT_PAUSE_REQUEST     2U
#define VOICE_ASR_RESULT_STOP_REQUEST      3U
#define VOICE_ASR_RESULT_FREE_TEXT         5U

const char *official_voice_map_id_label(rt_int32_t map_id)
{
    switch (map_id)
    {
    case OFFICIAL_VOICE_MAP_OK_INFINEON:
        return "official_wake_ok_infineon";
    case OFFICIAL_VOICE_MAP_PLAY_MUSIC:
        return "official_cmd_play_music";
    case OFFICIAL_VOICE_MAP_STOP_MUSIC:
        return "official_cmd_stop_music";
    case OFFICIAL_VOICE_MAP_NEXT_TRACK:
        return "official_cmd_next_track";
    case OFFICIAL_VOICE_MAP_PREVIOUS_TRACK:
        return "official_cmd_previous_track";
    case OFFICIAL_VOICE_MAP_INCREASE_VOLUME:
        return "official_cmd_increase_volume";
    case OFFICIAL_VOICE_MAP_DECREASE_VOLUME:
        return "official_cmd_decrease_volume";
    case OFFICIAL_VOICE_MAP_GOTO_HOMESCREEN:
        return "official_cmd_goto_homescreen";
    case OFFICIAL_VOICE_MAP_PAUSE_MUSIC:
        return "official_cmd_pause_music";
    case OFFICIAL_VOICE_MAP_VOLUME_LEVEL_0:
    case OFFICIAL_VOICE_MAP_VOLUME_LEVEL_1:
    case OFFICIAL_VOICE_MAP_VOLUME_LEVEL_2:
    case OFFICIAL_VOICE_MAP_VOLUME_LEVEL_3:
    case OFFICIAL_VOICE_MAP_VOLUME_LEVEL_4:
    case OFFICIAL_VOICE_MAP_VOLUME_LEVEL_5:
        return "official_cmd_volume_level";
    case OFFICIAL_VOICE_MAP_TIMEOUT:
        return "official_cmd_timeout";
    default:
        return "official_cmd_unknown";
    }
}

rt_err_t official_voice_publish_map_id(rt_int32_t map_id,
                                       rt_uint16_t confidence_permille,
                                       rt_uint16_t window_ms)
{
    rt_uint8_t model_code = MODEL_CODE_VOICE_ASR;
    rt_uint8_t result_code = VOICE_ASR_RESULT_FREE_TEXT;
    rt_bool_t detected = RT_TRUE;

    switch (map_id)
    {
    case OFFICIAL_VOICE_MAP_OK_INFINEON:
        model_code = MODEL_CODE_WAKE_WORD;
        result_code = MODEL_RESULT_CODE_WAKE_START_REQUEST;
        break;
    case OFFICIAL_VOICE_MAP_PLAY_MUSIC:
        result_code = VOICE_ASR_RESULT_START_REQUEST;
        break;
    case OFFICIAL_VOICE_MAP_PAUSE_MUSIC:
        result_code = VOICE_ASR_RESULT_PAUSE_REQUEST;
        break;
    case OFFICIAL_VOICE_MAP_STOP_MUSIC:
        result_code = VOICE_ASR_RESULT_STOP_REQUEST;
        break;
    case OFFICIAL_VOICE_MAP_TIMEOUT:
        result_code = VOICE_ASR_RESULT_NONE;
        detected = RT_FALSE;
        break;
    default:
        result_code = VOICE_ASR_RESULT_FREE_TEXT;
        break;
    }

    rt_kprintf("[official_voice_adapter] map_id=%ld label=%s model=%u result=%u conf=%u\n",
               (long)map_id,
               official_voice_map_id_label(map_id),
               model_code,
               result_code,
               confidence_permille);

    return model_result_publish(model_code,
                                result_code,
                                confidence_permille,
                                detected,
                                RT_TRUE,
                                window_ms);
}
