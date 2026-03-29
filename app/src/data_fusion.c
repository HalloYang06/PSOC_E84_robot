#include "data_fusion.h"

void data_fusion_init(data_fusion_t *fusion)
{
    if (fusion == 0)
    {
        return;
    }

    fusion->snapshot.timestamp_ms = 0U;
    fusion->snapshot.emg_raw = 0U;
    fusion->snapshot.emg_filtered = 0.0f;
    fusion->snapshot.hr_raw = 0U;
    fusion->snapshot.hr_filtered = 0.0f;
    fusion->snapshot.emg_valid = 0U;
    fusion->snapshot.hr_valid = 0U;
}

void data_fusion_update_emg(data_fusion_t *fusion, uint32_t timestamp_ms, uint16_t raw, float filtered)
{
    if (fusion == 0)
    {
        return;
    }

    fusion->snapshot.timestamp_ms = timestamp_ms;
    fusion->snapshot.emg_raw = raw;
    fusion->snapshot.emg_filtered = filtered;
    fusion->snapshot.emg_valid = 1U;
}

void data_fusion_update_hr(data_fusion_t *fusion, uint32_t timestamp_ms, uint16_t raw, float filtered)
{
    if (fusion == 0)
    {
        return;
    }

    fusion->snapshot.timestamp_ms = timestamp_ms;
    fusion->snapshot.hr_raw = raw;
    fusion->snapshot.hr_filtered = filtered;
    fusion->snapshot.hr_valid = 1U;
}

bool data_fusion_get_snapshot(const data_fusion_t *fusion, fusion_snapshot_t *snapshot)
{
    if ((fusion == 0) || (snapshot == 0))
    {
        return false;
    }

    *snapshot = fusion->snapshot;
    return (snapshot->emg_valid != 0U) && (snapshot->hr_valid != 0U);
}
