#include <assert.h>
#include <stdio.h>

#include "rehab_curl_planner.h"

static rehab_curl_config_t test_config(void)
{
    rehab_curl_config_t config = {
        .hard_min_pos_rad = 6.238f,
        .hard_max_pos_rad = 7.829f,
        .top_target_pos_rad = 6.288f,
        .bottom_target_pos_rad = 7.779f,
        .position_tolerance_rad = 0.030f,
        .max_feedback_velocity_rad_s = 0.35f,
        .dwell_ms = 200U,
        .segment_timeout_ms = 15000U,
        .command_refresh_ms = 200U,
        .arrival_samples = 3U,
    };
    return config;
}

static void test_start_rejects_invalid_or_unsafe_position(void)
{
    rehab_curl_planner_t planner;
    rehab_curl_config_t config = test_config();

    assert(rehab_curl_planner_start(&planner, &config, 6.237f, 0.0f, 10U) ==
           REHAB_CURL_RESULT_HARD_LIMIT);
    assert(rehab_curl_planner_start(&planner, &config, 7.830f, 0.0f, 10U) ==
           REHAB_CURL_RESULT_HARD_LIMIT);
    assert(rehab_curl_planner_start(&planner, &config, 7.00f, 0.36f, 10U) ==
           REHAB_CURL_RESULT_OVERSPEED);

    config.top_target_pos_rad = config.bottom_target_pos_rad;
    assert(rehab_curl_planner_start(&planner, &config, 7.00f, 0.0f, 10U) ==
           REHAB_CURL_RESULT_INVALID_CONFIG);
}

static void test_cycles_between_calibrated_endpoints(void)
{
    rehab_curl_planner_t planner;
    rehab_curl_output_t output;
    rehab_curl_config_t config = test_config();

    assert(rehab_curl_planner_start(&planner, &config, 7.00f, 0.0f, 100U) ==
           REHAB_CURL_RESULT_OK);
    rehab_curl_planner_step(&planner, 7.00f, 0.0f, RT_TRUE, RT_FALSE, 100U, &output);
    assert(output.action == REHAB_CURL_ACTION_COMMAND_POSITION);
    assert(output.target_pos_rad == config.top_target_pos_rad);

    rehab_curl_planner_step(&planner, 6.300f, 0.0f, RT_TRUE, RT_FALSE, 300U, &output);
    assert(planner.phase == REHAB_CURL_PHASE_MOVE_TOP);
    rehab_curl_planner_step(&planner, 6.295f, 0.0f, RT_TRUE, RT_FALSE, 320U, &output);
    assert(planner.phase == REHAB_CURL_PHASE_MOVE_TOP);
    rehab_curl_planner_step(&planner, 6.290f, 0.0f, RT_TRUE, RT_FALSE, 340U, &output);
    assert(planner.phase == REHAB_CURL_PHASE_DWELL_TOP);

    rehab_curl_planner_step(&planner, 6.290f, 0.0f, RT_TRUE, RT_FALSE, 539U, &output);
    assert(planner.phase == REHAB_CURL_PHASE_DWELL_TOP);
    rehab_curl_planner_step(&planner, 6.290f, 0.0f, RT_TRUE, RT_FALSE, 540U, &output);
    assert(planner.phase == REHAB_CURL_PHASE_MOVE_BOTTOM);
    assert(output.action == REHAB_CURL_ACTION_COMMAND_POSITION);
    assert(output.target_pos_rad == config.bottom_target_pos_rad);

    rehab_curl_planner_step(&planner, 7.770f, 0.0f, RT_TRUE, RT_FALSE, 700U, &output);
    rehab_curl_planner_step(&planner, 7.775f, 0.0f, RT_TRUE, RT_FALSE, 720U, &output);
    rehab_curl_planner_step(&planner, 7.779f, 0.0f, RT_TRUE, RT_FALSE, 740U, &output);
    assert(planner.phase == REHAB_CURL_PHASE_DWELL_BOTTOM);
    rehab_curl_planner_step(&planner, 7.779f, 0.0f, RT_TRUE, RT_FALSE, 940U, &output);
    assert(planner.phase == REHAB_CURL_PHASE_MOVE_TOP);
    assert(planner.completed_repetitions == 1U);
    assert(output.target_pos_rad == config.top_target_pos_rad);
}

static void test_faults_latch_until_restart(void)
{
    rehab_curl_planner_t planner;
    rehab_curl_output_t output;
    rehab_curl_config_t config = test_config();

    assert(rehab_curl_planner_start(&planner, &config, 7.00f, 0.0f, 0U) ==
           REHAB_CURL_RESULT_OK);
    rehab_curl_planner_step(&planner, 7.00f, 0.36f, RT_TRUE, RT_FALSE, 20U, &output);
    assert(output.action == REHAB_CURL_ACTION_STOP_FAULT);
    assert(output.result == REHAB_CURL_RESULT_OVERSPEED);
    rehab_curl_planner_step(&planner, 7.00f, 0.0f, RT_TRUE, RT_FALSE, 40U, &output);
    assert(output.action == REHAB_CURL_ACTION_STOP_FAULT);

    assert(rehab_curl_planner_start(&planner, &config, 7.00f, 0.0f, 100U) ==
           REHAB_CURL_RESULT_OK);
    rehab_curl_planner_step(&planner, 7.830f, 0.0f, RT_TRUE, RT_FALSE, 120U, &output);
    assert(output.result == REHAB_CURL_RESULT_HARD_LIMIT);

    assert(rehab_curl_planner_start(&planner, &config, 7.00f, 0.0f, 200U) ==
           REHAB_CURL_RESULT_OK);
    rehab_curl_planner_step(&planner, 7.00f, 0.0f, RT_FALSE, RT_FALSE, 220U, &output);
    assert(output.result == REHAB_CURL_RESULT_STALE_FEEDBACK);

    assert(rehab_curl_planner_start(&planner, &config, 7.00f, 0.0f, 300U) ==
           REHAB_CURL_RESULT_OK);
    rehab_curl_planner_step(&planner, 7.00f, 0.0f, RT_TRUE, RT_TRUE, 320U, &output);
    assert(output.result == REHAB_CURL_RESULT_MOTOR_FAULT);
}

static void test_segment_timeout_and_command_refresh(void)
{
    rehab_curl_planner_t planner;
    rehab_curl_output_t output;
    rehab_curl_config_t config = test_config();

    config.segment_timeout_ms = 1000U;
    assert(rehab_curl_planner_start(&planner, &config, 7.00f, 0.0f, 100U) ==
           REHAB_CURL_RESULT_OK);
    rehab_curl_planner_step(&planner, 7.00f, 0.0f, RT_TRUE, RT_FALSE, 100U, &output);
    assert(output.action == REHAB_CURL_ACTION_COMMAND_POSITION);
    rehab_curl_planner_step(&planner, 6.90f, 0.0f, RT_TRUE, RT_FALSE, 299U, &output);
    assert(output.action == REHAB_CURL_ACTION_NONE);
    rehab_curl_planner_step(&planner, 6.90f, 0.0f, RT_TRUE, RT_FALSE, 300U, &output);
    assert(output.action == REHAB_CURL_ACTION_COMMAND_POSITION);
    rehab_curl_planner_step(&planner, 6.80f, 0.0f, RT_TRUE, RT_FALSE, 1100U, &output);
    assert(output.result == REHAB_CURL_RESULT_SEGMENT_TIMEOUT);
}

int main(void)
{
    test_start_rejects_invalid_or_unsafe_position();
    test_cycles_between_calibrated_endpoints();
    test_faults_latch_until_restart();
    test_segment_timeout_and_command_refresh();
    puts("rehab_curl_planner_test: PASS");
    return 0;
}
