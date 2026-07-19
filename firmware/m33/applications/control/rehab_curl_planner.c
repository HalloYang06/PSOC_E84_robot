#include "rehab_curl_planner.h"

static float curl_abs(float value)
{
    return (value < 0.0f) ? -value : value;
}

static rt_bool_t curl_config_valid(const rehab_curl_config_t *config)
{
    return (config != RT_NULL) &&
           (config->hard_min_pos_rad <= config->top_target_pos_rad) &&
           (config->top_target_pos_rad < config->bottom_target_pos_rad) &&
           (config->bottom_target_pos_rad <= config->hard_max_pos_rad) &&
           (config->position_tolerance_rad > 0.0f) &&
           (config->max_feedback_velocity_rad_s > 0.0f) &&
           (config->segment_timeout_ms > 0U) &&
           (config->command_refresh_ms > 0U) &&
           (config->arrival_samples > 0U);
}

static rt_bool_t curl_position_inside_hard_limit(const rehab_curl_config_t *config,
                                                  float position_rad)
{
    return (position_rad >= config->hard_min_pos_rad) &&
           (position_rad <= config->hard_max_pos_rad);
}

static void curl_latch_fault(rehab_curl_planner_t *planner,
                             rehab_curl_result_t result)
{
    planner->phase = REHAB_CURL_PHASE_FAULT;
    planner->fault = result;
    planner->arrival_count = 0U;
    planner->command_pending = RT_FALSE;
}

static float curl_phase_target(const rehab_curl_planner_t *planner)
{
    return ((planner->phase == REHAB_CURL_PHASE_MOVE_BOTTOM) ||
            (planner->phase == REHAB_CURL_PHASE_DWELL_BOTTOM))
               ? planner->config.bottom_target_pos_rad
               : planner->config.top_target_pos_rad;
}

static void curl_enter_phase(rehab_curl_planner_t *planner,
                             rehab_curl_phase_t phase,
                             rt_uint32_t now_ms)
{
    planner->phase = phase;
    planner->phase_started_ms = now_ms;
    planner->arrival_count = 0U;
    planner->command_pending =
        ((phase == REHAB_CURL_PHASE_MOVE_TOP) ||
         (phase == REHAB_CURL_PHASE_MOVE_BOTTOM))
            ? RT_TRUE
            : RT_FALSE;
}

rehab_curl_result_t rehab_curl_planner_start(rehab_curl_planner_t *planner,
                                               const rehab_curl_config_t *config,
                                               float feedback_pos_rad,
                                               float feedback_vel_rad_s,
                                               rt_uint32_t now_ms)
{
    if ((planner == RT_NULL) || !curl_config_valid(config))
    {
        return REHAB_CURL_RESULT_INVALID_CONFIG;
    }

    rt_memset(planner, 0, sizeof(*planner));
    planner->config = *config;
    if (!curl_position_inside_hard_limit(config, feedback_pos_rad))
    {
        curl_latch_fault(planner, REHAB_CURL_RESULT_HARD_LIMIT);
        return planner->fault;
    }
    if (curl_abs(feedback_vel_rad_s) > config->max_feedback_velocity_rad_s)
    {
        curl_latch_fault(planner, REHAB_CURL_RESULT_OVERSPEED);
        return planner->fault;
    }

    planner->fault = REHAB_CURL_RESULT_OK;
    planner->last_command_ms = now_ms - config->command_refresh_ms;
    curl_enter_phase(planner, REHAB_CURL_PHASE_MOVE_TOP, now_ms);
    return REHAB_CURL_RESULT_OK;
}

void rehab_curl_planner_step(rehab_curl_planner_t *planner,
                             float feedback_pos_rad,
                             float feedback_vel_rad_s,
                             rt_bool_t feedback_fresh,
                             rt_bool_t motor_fault,
                             rt_uint32_t now_ms,
                             rehab_curl_output_t *output)
{
    float target;

    if (output == RT_NULL)
    {
        return;
    }
    rt_memset(output, 0, sizeof(*output));
    if (planner == RT_NULL)
    {
        output->action = REHAB_CURL_ACTION_STOP_FAULT;
        output->result = REHAB_CURL_RESULT_INVALID_CONFIG;
        return;
    }
    if (planner->phase == REHAB_CURL_PHASE_FAULT)
    {
        output->action = REHAB_CURL_ACTION_STOP_FAULT;
        output->result = planner->fault;
        output->phase = planner->phase;
        output->completed_repetitions = planner->completed_repetitions;
        return;
    }
    if ((planner->phase == REHAB_CURL_PHASE_IDLE) ||
        !curl_config_valid(&planner->config))
    {
        curl_latch_fault(planner, REHAB_CURL_RESULT_INVALID_CONFIG);
    }
    else if (!feedback_fresh)
    {
        curl_latch_fault(planner, REHAB_CURL_RESULT_STALE_FEEDBACK);
    }
    else if (motor_fault)
    {
        curl_latch_fault(planner, REHAB_CURL_RESULT_MOTOR_FAULT);
    }
    else if (!curl_position_inside_hard_limit(&planner->config, feedback_pos_rad))
    {
        curl_latch_fault(planner, REHAB_CURL_RESULT_HARD_LIMIT);
    }
    else if (curl_abs(feedback_vel_rad_s) > planner->config.max_feedback_velocity_rad_s)
    {
        curl_latch_fault(planner, REHAB_CURL_RESULT_OVERSPEED);
    }
    else if (((planner->phase == REHAB_CURL_PHASE_MOVE_TOP) ||
              (planner->phase == REHAB_CURL_PHASE_MOVE_BOTTOM)) &&
             ((rt_uint32_t)(now_ms - planner->phase_started_ms) >=
              planner->config.segment_timeout_ms))
    {
        curl_latch_fault(planner, REHAB_CURL_RESULT_SEGMENT_TIMEOUT);
    }

    if (planner->phase == REHAB_CURL_PHASE_FAULT)
    {
        output->action = REHAB_CURL_ACTION_STOP_FAULT;
        output->result = planner->fault;
        output->phase = planner->phase;
        output->completed_repetitions = planner->completed_repetitions;
        return;
    }

    target = curl_phase_target(planner);
    if ((planner->phase == REHAB_CURL_PHASE_MOVE_TOP) ||
        (planner->phase == REHAB_CURL_PHASE_MOVE_BOTTOM))
    {
        if (curl_abs(feedback_pos_rad - target) <= planner->config.position_tolerance_rad)
        {
            if (planner->arrival_count < 0xFFU)
            {
                planner->arrival_count++;
            }
            if (planner->arrival_count >= planner->config.arrival_samples)
            {
                curl_enter_phase(planner,
                                 (planner->phase == REHAB_CURL_PHASE_MOVE_TOP)
                                     ? REHAB_CURL_PHASE_DWELL_TOP
                                     : REHAB_CURL_PHASE_DWELL_BOTTOM,
                                 now_ms);
            }
        }
        else
        {
            planner->arrival_count = 0U;
        }
    }
    else if ((rt_uint32_t)(now_ms - planner->phase_started_ms) >= planner->config.dwell_ms)
    {
        if (planner->phase == REHAB_CURL_PHASE_DWELL_BOTTOM)
        {
            planner->completed_repetitions++;
            curl_enter_phase(planner, REHAB_CURL_PHASE_MOVE_TOP, now_ms);
        }
        else
        {
            curl_enter_phase(planner, REHAB_CURL_PHASE_MOVE_BOTTOM, now_ms);
        }
        target = curl_phase_target(planner);
    }

    if (((planner->phase == REHAB_CURL_PHASE_MOVE_TOP) ||
         (planner->phase == REHAB_CURL_PHASE_MOVE_BOTTOM)) &&
        (planner->command_pending ||
         ((rt_uint32_t)(now_ms - planner->last_command_ms) >=
          planner->config.command_refresh_ms)))
    {
        output->action = REHAB_CURL_ACTION_COMMAND_POSITION;
        output->target_pos_rad = curl_phase_target(planner);
        planner->last_command_ms = now_ms;
        planner->command_pending = RT_FALSE;
    }
    output->result = REHAB_CURL_RESULT_OK;
    output->phase = planner->phase;
    output->completed_repetitions = planner->completed_repetitions;
}
