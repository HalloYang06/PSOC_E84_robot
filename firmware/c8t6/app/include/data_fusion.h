#ifndef DATA_FUSION_H
#define DATA_FUSION_H

#include <stdbool.h>
#include <stdint.h>

#include "adc_channels.h"

#define FUSION_ADC_CHANNEL_COUNT APP_ADC_CHANNEL_COUNT

typedef struct
{
    uint32_t timestamp_ms;
    uint16_t adc_raw[FUSION_ADC_CHANNEL_COUNT];
    uint16_t emg_raw;
    float emg_filtered;
    uint16_t hr_raw;
    float hr_filtered;
    uint8_t adc_valid;
    uint8_t emg_valid;
    uint8_t hr_valid;
} fusion_snapshot_t;

typedef struct
{
    fusion_snapshot_t snapshot;
} data_fusion_t;

void data_fusion_init(data_fusion_t *fusion);
void data_fusion_update_adc4(data_fusion_t *fusion,
                             uint32_t timestamp_ms,
                             const uint16_t samples[FUSION_ADC_CHANNEL_COUNT]);
void data_fusion_update_emg(data_fusion_t *fusion, uint32_t timestamp_ms, uint16_t raw, float filtered);
void data_fusion_update_hr(data_fusion_t *fusion, uint32_t timestamp_ms, uint16_t raw, float filtered);
bool data_fusion_get_snapshot(const data_fusion_t *fusion, fusion_snapshot_t *snapshot);

#endif
