#ifndef AUDIO_PLAYBACK_H
#define AUDIO_PLAYBACK_H

#include <rtthread.h>
#include "audio_capture.h"

rt_err_t audio_playback_init(void);
rt_err_t audio_playback_start(void);
rt_err_t audio_playback_stop(void);
rt_err_t audio_playback_write(const uint8_t *data, uint32_t len);
void audio_playback_clear(void);

#endif // AUDIO_PLAYBACK_H
