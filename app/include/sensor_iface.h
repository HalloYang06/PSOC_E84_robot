#ifndef SENSOR_IFACE_H
#define SENSOR_IFACE_H

#include <stdint.h>

typedef enum
{
    SENSOR_TYPE_EMG = 0,
    SENSOR_TYPE_HEART_RATE = 1
} sensor_type_t;

typedef struct
{
    uint16_t sample_rate_hz;
    uint8_t channel_or_addr;
} sensor_cfg_t;

typedef struct
{
    uint32_t sample_count;
    uint32_t error_count;
    uint8_t healthy;
} sensor_status_t;

typedef struct sensor_iface sensor_iface_t;

struct sensor_iface
{
    int32_t (*init)(sensor_iface_t *self, const sensor_cfg_t *cfg);
    int32_t (*start)(sensor_iface_t *self);
    int32_t (*stop)(sensor_iface_t *self);
    int32_t (*read)(sensor_iface_t *self, uint16_t *sample);
    int32_t (*get_status)(sensor_iface_t *self, sensor_status_t *status);
    void *ctx;
    sensor_type_t type;
};

#endif
