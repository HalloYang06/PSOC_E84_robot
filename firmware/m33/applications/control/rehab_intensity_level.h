#ifndef __REHAB_INTENSITY_LEVEL_H__
#define __REHAB_INTENSITY_LEVEL_H__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define REHAB_INTENSITY_LEVEL_MIN   UINT8_C(1)
#define REHAB_INTENSITY_LEVEL_MAX   UINT8_C(4)
#define REHAB_INTENSITY_LEVEL_COUNT UINT8_C(4)

float rehab_intensity_current_for_level(uint8_t level);
uint8_t rehab_intensity_level_for_current(float current_a);
uint8_t rehab_intensity_adjust_level(uint8_t level, int8_t delta);

#ifdef __cplusplus
}
#endif

#endif /* __REHAB_INTENSITY_LEVEL_H__ */
