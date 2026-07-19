#include "rehab_intensity_level.h"

static const float s_rehab_intensity_current_a[REHAB_INTENSITY_LEVEL_COUNT] =
{
    0.5f,
    1.0f,
    1.5f,
    2.0f,
};

float rehab_intensity_current_for_level(uint8_t level)
{
    if ((level < REHAB_INTENSITY_LEVEL_MIN) ||
        (level > REHAB_INTENSITY_LEVEL_MAX))
    {
        return 0.0f;
    }
    return s_rehab_intensity_current_a[level - REHAB_INTENSITY_LEVEL_MIN];
}

uint8_t rehab_intensity_level_for_current(float current_a)
{
    uint8_t level;

    for (level = REHAB_INTENSITY_LEVEL_MIN;
         level < REHAB_INTENSITY_LEVEL_MAX;
         level++)
    {
        if (current_a <= rehab_intensity_current_for_level(level))
        {
            return level;
        }
    }
    return REHAB_INTENSITY_LEVEL_MAX;
}

uint8_t rehab_intensity_adjust_level(uint8_t level, int8_t delta)
{
    int16_t adjusted;

    if ((level < REHAB_INTENSITY_LEVEL_MIN) ||
        (level > REHAB_INTENSITY_LEVEL_MAX))
    {
        return 0U;
    }

    adjusted = (int16_t)level + (int16_t)delta;
    if (adjusted < (int16_t)REHAB_INTENSITY_LEVEL_MIN)
    {
        adjusted = (int16_t)REHAB_INTENSITY_LEVEL_MIN;
    }
    else if (adjusted > (int16_t)REHAB_INTENSITY_LEVEL_MAX)
    {
        adjusted = (int16_t)REHAB_INTENSITY_LEVEL_MAX;
    }
    return (uint8_t)adjusted;
}
