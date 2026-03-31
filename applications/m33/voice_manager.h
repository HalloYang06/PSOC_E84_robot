#ifndef VOICE_MANAGER_H
#define VOICE_MANAGER_H

#include <rtthread.h>

rt_err_t voice_manager_init(void);
rt_err_t voice_manager_start(void);
rt_err_t voice_manager_start_async(void);
rt_err_t voice_manager_stop(void);

#endif // VOICE_MANAGER_H
