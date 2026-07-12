#ifndef BSP_MUELEC_H
#define BSP_MUELEC_H

#include <stdint.h>

#include "adc.h"
#include "tim.h"

int32_t bsp_muelec_bind(ADC_HandleTypeDef *hadc, TIM_HandleTypeDef *htim);
int32_t bsp_muelec_start_dma(uint16_t *buffer, uint32_t len);
int32_t bsp_muelec_stop_dma(void);

#endif
