#include "voice_mode_request_guard.h"

#include <stddef.h>

static uint32_t voice_mode_is_supported(voice_mode_target_t mode)
{
    return (mode == VOICE_MODE_PASSIVE) ||
           (mode == VOICE_MODE_ASSIST) ||
           (mode == VOICE_MODE_RESIST);
}

static uint32_t voice_mode_current_is_supported(voice_mode_current_t mode)
{
    return voice_mode_is_supported(mode) ||
           (mode == VOICE_MODE_CURRENT_OTHER_ACTIVE);
}

void voice_mode_guard_init(voice_mode_guard_t *guard)
{
    if (guard != NULL)
    {
        guard->trusted_epoch = 0U;
        guard->committed_request_id = 0U;
    }
}

uint32_t voice_mode_guard_accept_epoch(voice_mode_guard_t *guard,
                                       uint32_t boot_epoch,
                                       voice_mode_current_t current_mode,
                                       uint32_t owner_action_active)
{
    if ((guard == NULL) || (boot_epoch == 0U) ||
        (current_mode != VOICE_MODE_CURRENT_PASSIVE) ||
        (owner_action_active != 0U))
    {
        return 0U;
    }

    if (guard->trusted_epoch != boot_epoch)
    {
        guard->trusted_epoch = boot_epoch;
        guard->committed_request_id = 0U;
    }
    return 1U;
}

voice_mode_decision_t voice_mode_guard_decide(
    const voice_mode_guard_t *guard,
    const voice_mode_request_t *request,
    uint32_t now_tick,
    uint32_t tick_hz,
    voice_mode_current_t current_mode,
    uint32_t owner_action_active,
    uint32_t active_preconditions_met)
{
    int32_t age;

    if ((guard == NULL) || (request == NULL) ||
        (request->source != VOICE_MODE_SOURCE_VOICE) ||
        (request->boot_epoch == 0U) || (request->request_id == 0U) ||
        (request->joint_mask != VOICE_MODE_JOINT_MASK) ||
        (tick_hz == 0U) ||
        (request->ttl_ms == 0U) ||
        (request->ttl_ms > VOICE_MODE_MAX_TTL_MS) ||
        !voice_mode_is_supported(request->target_mode) ||
        !voice_mode_current_is_supported(current_mode))
    {
        return VOICE_MODE_DECISION_REJECT_INVALID;
    }

    if ((guard->trusted_epoch == 0U) ||
        (request->boot_epoch != guard->trusted_epoch))
    {
        return ((owner_action_active != 0U) ||
                (current_mode != VOICE_MODE_CURRENT_PASSIVE)) ?
               VOICE_MODE_DECISION_NEEDS_REARM :
               VOICE_MODE_DECISION_REJECT_EPOCH;
    }

    age = (int32_t)(now_tick - request->received_tick);
    if ((age < 0) ||
        (((uint64_t)(uint32_t)age * UINT64_C(1000)) >
         ((uint64_t)request->ttl_ms * (uint64_t)tick_hz)))
    {
        return VOICE_MODE_DECISION_REJECT_EXPIRED;
    }

    if (request->request_id == guard->committed_request_id)
    {
        return VOICE_MODE_DECISION_REJECT_DUPLICATE;
    }
    if (request->request_id < guard->committed_request_id)
    {
        return VOICE_MODE_DECISION_REJECT_STALE;
    }

    if (request->target_mode == VOICE_MODE_PASSIVE)
    {
        return (current_mode == VOICE_MODE_CURRENT_PASSIVE) ?
               VOICE_MODE_DECISION_ALREADY_ACTIVE :
               VOICE_MODE_DECISION_APPLY_PASSIVE;
    }

    if (current_mode == request->target_mode)
    {
        return VOICE_MODE_DECISION_ALREADY_ACTIVE;
    }

    if (current_mode != VOICE_MODE_CURRENT_PASSIVE)
    {
        return VOICE_MODE_DECISION_NEEDS_PASSIVE;
    }

    if ((current_mode == VOICE_MODE_PASSIVE) &&
        (active_preconditions_met == 0U))
    {
        return VOICE_MODE_DECISION_REJECT_PRECONDITION;
    }

    return VOICE_MODE_DECISION_APPLY_ACTIVE;
}

uint32_t voice_mode_guard_commit(voice_mode_guard_t *guard,
                                 const voice_mode_request_t *request,
                                 voice_mode_decision_t decision)
{
    uint32_t successful;

    successful = (decision == VOICE_MODE_DECISION_APPLY_PASSIVE) ||
                 (decision == VOICE_MODE_DECISION_APPLY_ACTIVE) ||
                 (decision == VOICE_MODE_DECISION_ALREADY_ACTIVE);
    if ((guard == NULL) || (request == NULL) || !successful ||
        (request->source != VOICE_MODE_SOURCE_VOICE) ||
        (request->boot_epoch != guard->trusted_epoch) ||
        (request->request_id == 0U) ||
        (request->joint_mask != VOICE_MODE_JOINT_MASK) ||
        !voice_mode_is_supported(request->target_mode) ||
        ((decision == VOICE_MODE_DECISION_APPLY_PASSIVE) &&
         (request->target_mode != VOICE_MODE_PASSIVE)) ||
        ((decision == VOICE_MODE_DECISION_APPLY_ACTIVE) &&
         (request->target_mode == VOICE_MODE_PASSIVE)) ||
        (request->request_id <= guard->committed_request_id))
    {
        return 0U;
    }

    guard->committed_request_id = request->request_id;
    return 1U;
}
