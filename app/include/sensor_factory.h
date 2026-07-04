#ifndef SENSOR_FACTORY_H
#define SENSOR_FACTORY_H

#include "adc_channels.h"
#include "sensor_iface.h"

#define SENSOR_FACTORY_ADC_CHANNEL_COUNT APP_ADC_CHANNEL_COUNT

sensor_iface_t *sensor_factory_create(sensor_type_t type, const sensor_cfg_t *cfg);
int32_t sensor_factory_read_emg_channels(uint16_t samples[SENSOR_FACTORY_ADC_CHANNEL_COUNT]);
void sensor_factory_on_emg_dma_complete_isr(void);

#endif
