#ifndef SENSOR_FACTORY_H
#define SENSOR_FACTORY_H

#include "sensor_iface.h"

sensor_iface_t *sensor_factory_create(sensor_type_t type, const sensor_cfg_t *cfg);
void sensor_factory_on_emg_dma_complete_isr(void);

#endif
