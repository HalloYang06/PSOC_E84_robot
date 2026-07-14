#ifndef __SMIF0_GUARD_H__
#define __SMIF0_GUARD_H__

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

void smif0_guard_early_init(void);
void smif0_guard_set_safe_to_block(bool safe_to_block);

#ifdef __cplusplus
}
#endif

#endif /* __SMIF0_GUARD_H__ */
