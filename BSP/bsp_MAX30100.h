#ifndef BSP_MAX30100_H
#define BSP_MAX30100_H

#include <stdint.h>

#include "i2c.h"

#define MAX30100_I2C_ADDR_7BIT (0x57U)
#define MAX30100_EXPECTED_PART_ID (0x11U)

int32_t bsp_max30100_init(I2C_HandleTypeDef *hi2c);
int32_t bsp_max30100_read_sample(uint16_t *ir, uint16_t *red);
int32_t bsp_max30100_soft_reset(void);

#endif
