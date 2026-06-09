#ifndef OFFICIAL_VOICE_RESULT_ADAPTER_H
#define OFFICIAL_VOICE_RESULT_ADAPTER_H

#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    OFFICIAL_VOICE_MAP_OK_INFINEON = 101,
    OFFICIAL_VOICE_MAP_PLAY_MUSIC = 401,
    OFFICIAL_VOICE_MAP_STOP_MUSIC = 402,
    OFFICIAL_VOICE_MAP_NEXT_TRACK = 403,
    OFFICIAL_VOICE_MAP_PREVIOUS_TRACK = 404,
    OFFICIAL_VOICE_MAP_INCREASE_VOLUME = 405,
    OFFICIAL_VOICE_MAP_DECREASE_VOLUME = 406,
    OFFICIAL_VOICE_MAP_GOTO_HOMESCREEN = 407,
    OFFICIAL_VOICE_MAP_PAUSE_MUSIC = 408,
    OFFICIAL_VOICE_MAP_VOLUME_LEVEL_0 = 409,
    OFFICIAL_VOICE_MAP_VOLUME_LEVEL_1 = 410,
    OFFICIAL_VOICE_MAP_VOLUME_LEVEL_2 = 411,
    OFFICIAL_VOICE_MAP_VOLUME_LEVEL_3 = 412,
    OFFICIAL_VOICE_MAP_VOLUME_LEVEL_4 = 413,
    OFFICIAL_VOICE_MAP_VOLUME_LEVEL_5 = 414,
    OFFICIAL_VOICE_MAP_TIMEOUT = 128000,
} official_voice_map_id_t;

rt_err_t official_voice_publish_map_id(rt_int32_t map_id,
                                       rt_uint16_t confidence_permille,
                                       rt_uint16_t window_ms);
const char *official_voice_map_id_label(rt_int32_t map_id);

#ifdef __cplusplus
}
#endif

#endif
