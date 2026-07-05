#include "rehab_adrc.h"

void rehab_adrc_reset(rehab_adrc_state_t *state)
{
    if (state != RT_NULL)
    {
        state->z1 = 0.0f;
        state->z2 = 0.0f;
        state->z3 = 0.0f;
        state->last_trim = 0.0f;
        state->initialized = RT_FALSE;
    }
}

static float rehab_adrc_absf(float value)
{
    return (value >= 0.0f) ? value : -value;
}

static float rehab_adrc_clampf(float value, float limit)
{
    if (limit < 0.0f)
    {
        limit = -limit;
    }
    if (value > limit)
    {
        return limit;
    }
    if (value < -limit)
    {
        return -limit;
    }
    return value;
}

float rehab_adrc_step(rehab_adrc_state_t *state,
                      const rehab_adrc_profile_t *profile,
                      float measurement,
                      float dt_s,
                      rehab_adrc_observation_t *obs)
{
    float b0;
    float error;
    float eso_error;
    float raw_trim;
    float trim;

    if (obs != RT_NULL)
    {
        rt_memset(obs, 0, sizeof(*obs));
    }
    if ((state == RT_NULL) || (profile == RT_NULL))
    {
        return 0.0f;
    }
    if (dt_s <= 0.0f)
    {
        dt_s = 0.001f;
    }

    b0 = profile->b0;
    if (rehab_adrc_absf(b0) < 0.001f)
    {
        b0 = 0.001f;
    }

    error = measurement - profile->target;
    if (!state->initialized)
    {
        state->z1 = error;
        state->z2 = 0.0f;
        state->z3 = 0.0f;
        state->last_trim = 0.0f;
        state->initialized = RT_TRUE;
    }

    eso_error = state->z1 - error;
    state->z1 += dt_s * (state->z2 - (profile->beta1 * eso_error));
    state->z2 += dt_s * (state->z3 - (profile->beta2 * eso_error) + (b0 * state->last_trim));
    state->z3 += dt_s * (-(profile->beta3 * eso_error));

    raw_trim = (profile->kp * state->z1) +
               (profile->kd * state->z2) +
               (profile->disturbance_gain * state->z3);
    trim = rehab_adrc_clampf(raw_trim, profile->trim_limit);
    state->last_trim = trim;

    if (obs != RT_NULL)
    {
        obs->error = error;
        obs->z1 = state->z1;
        obs->z2 = state->z2;
        obs->z3 = state->z3;
        obs->trim_current_a = trim;
    }

    return trim;
}
