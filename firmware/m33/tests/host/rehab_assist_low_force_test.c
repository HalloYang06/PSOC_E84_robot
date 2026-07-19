#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rehab_assist_strategy.h"

static void require_true(int condition, const char *message)
{
    if (!condition)
    {
        fprintf(stderr, "FAIL: %s\n", message);
        exit(1);
    }
}

static void require_close(float actual, float expected, float tolerance, const char *message)
{
    if (fabsf(actual - expected) > tolerance)
    {
        fprintf(stderr,
                "FAIL: %s actual=%f expected=%f tolerance=%f\n",
                message,
                actual,
                expected,
                tolerance);
        exit(1);
    }
}

static rehab_strategy_params_t assist_params(void)
{
    rehab_strategy_params_t params;

    memset(&params, 0, sizeof(params));
    params.follow_direction = -1.0f;
    params.assist_direction = 1.0f;
    params.assist_max_current_a = 1.0f;
    params.assist_current_gain_a_per_nm = 2.0f;
    params.assist_velocity_fallback_enabled = RT_TRUE;
    params.assist_velocity_enter_rad_s = 0.01f;
    params.assist_velocity_exit_rad_s = 0.005f;
    params.assist_min_current_a = 0.15f;
    params.assist_velocity_gain_a_per_rad_s = 1.0f;
    params.assist_slew_current_a_per_step = 0.03f;
    return params;
}

static control_motor_feedback_t feedback(float torque_nm, float vel_rad_s)
{
    control_motor_feedback_t fb;

    memset(&fb, 0, sizeof(fb));
    fb.torque_nm = torque_nm;
    fb.vel_rad_s = vel_rad_s;
    fb.timestamp = 1U;
    return fb;
}

static void test_low_force_velocity_fallback_is_bounded_and_resets(void)
{
    rehab_assist_strategy_state_t state;
    rehab_strategy_output_t out;
    rehab_strategy_params_t params = assist_params();
    control_motor_feedback_t fb = feedback(0.0f, 0.009f);

    rehab_assist_strategy_reset(&state);
    rehab_assist_strategy_step(&state, &params, &fb, 1.0f, &out);
    require_true(out.type == REHAB_STRATEGY_OUTPUT_STOP,
                 "velocity below the enter threshold must stay stopped");

    fb.vel_rad_s = 0.02f;
    rehab_assist_strategy_step(&state, &params, &fb, 1.0f, &out);
    require_true(out.engaged == RT_TRUE, "velocity fallback should engage without torque");
    require_true(out.type == REHAB_STRATEGY_OUTPUT_CURRENT,
                 "velocity fallback should request current control");
    require_close(out.current_a, 0.03f, 0.0001f,
                  "first assist current must add power in the motion direction");

    rehab_assist_strategy_step(&state, &params, &fb, 1.0f, &out);
    require_close(out.current_a, 0.06f, 0.0001f,
                  "assist current must continue with bounded steps");

    fb.vel_rad_s = 0.005f;
    rehab_assist_strategy_step(&state, &params, &fb, 1.0f, &out);
    require_true(out.type == REHAB_STRATEGY_OUTPUT_STOP,
                 "velocity at the exit threshold must stop assist");

    fb.vel_rad_s = 0.02f;
    rehab_assist_strategy_step(&state, &params, &fb, 1.0f, &out);
    require_close(out.current_a, 0.03f, 0.0001f,
                  "a new engagement must restart the slew from zero");
}

int main(void)
{
    test_low_force_velocity_fallback_is_bounded_and_resets();
    printf("rehab_assist_low_force_test PASS\n");
    return 0;
}
