#ifndef M55_VOICE_MODE_BRIDGE_H
#define M55_VOICE_MODE_BRIDGE_H

#include "control_manager.h"

#ifdef __cplusplus
extern "C" {
#endif

rt_bool_t m55_voice_mode_bridge_parse(const char *text, control_mode_t *mode);
rt_err_t m55_voice_mode_bridge_handle_text(const char *text);

#ifdef __cplusplus
}
#endif

#endif
