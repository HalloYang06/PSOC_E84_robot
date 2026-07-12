#include "bsp_MuElec.h"

static ADC_HandleTypeDef *s_hadc;
static TIM_HandleTypeDef *s_htim;

int32_t bsp_muelec_bind(ADC_HandleTypeDef *hadc, TIM_HandleTypeDef *htim)
{
    if ((hadc == 0) || (htim == 0))
    {
        return -1;
    }

    s_hadc = hadc;
    s_htim = htim;
    return 0;
}

int32_t bsp_muelec_start_dma(uint16_t *buffer, uint32_t len)
{
    if ((s_hadc == 0) || (s_htim == 0) || (buffer == 0) || (len == 0U))
    {
        return -1;
    }

    /* TIM1_CH1 产生 1kHz 比较事件，作为 ADC 外部触发源。 */
    if (HAL_TIM_PWM_Start(s_htim, TIM_CHANNEL_1) != HAL_OK)
    {
        return -1;
    }

    if (HAL_ADC_Start_DMA(s_hadc, (uint32_t *)buffer, len) != HAL_OK)
    {
        (void)HAL_TIM_PWM_Stop(s_htim, TIM_CHANNEL_1);
        return -1;
    }
    return 0;
}

int32_t bsp_muelec_stop_dma(void)
{
    if ((s_hadc == 0) || (s_htim == 0))
    {
        return -1;
    }

    (void)HAL_ADC_Stop_DMA(s_hadc);
    (void)HAL_TIM_PWM_Stop(s_htim, TIM_CHANNEL_1);
    return 0;
}
