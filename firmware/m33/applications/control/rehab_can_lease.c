#include "rehab_can_lease.h"

void rehab_can_lease_note_heartbeat(rehab_can_lease_t *lease, rt_tick_t now)
{
    if (lease == RT_NULL)
    {
        return;
    }

    lease->last_heartbeat_tick = now;
    lease->has_heartbeat = RT_TRUE;
}

void rehab_can_lease_note_mode(rehab_can_lease_t *lease,
                               rt_bool_t active,
                               rt_uint8_t owner_source,
                               rt_uint32_t mode_generation)
{
    if (lease == RT_NULL)
    {
        return;
    }

    lease->active = active;
    lease->owner_source = owner_source;
    lease->mode_generation = mode_generation;
    lease->stop_latched = RT_FALSE;
    lease->has_stop_attempt = RT_FALSE;
}

rt_bool_t rehab_can_lease_claim_stop(rehab_can_lease_t *lease,
                                     rt_tick_t now,
                                     rt_tick_t timeout_ticks,
                                     rt_tick_t retry_ticks,
                                     rt_uint8_t *owner_source,
                                     rt_uint32_t *mode_generation)
{
    if ((lease == RT_NULL) || (owner_source == RT_NULL) ||
        (mode_generation == RT_NULL) || !lease->active)
    {
        return RT_FALSE;
    }

    if (!lease->stop_latched)
    {
        if (lease->has_heartbeat &&
            ((now - lease->last_heartbeat_tick) <= timeout_ticks))
        {
            return RT_FALSE;
        }
        lease->stop_latched = RT_TRUE;
        lease->timeout_count++;
    }

    if (lease->has_stop_attempt &&
        ((now - lease->last_stop_attempt_tick) < retry_ticks))
    {
        return RT_FALSE;
    }

    lease->last_stop_attempt_tick = now;
    lease->has_stop_attempt = RT_TRUE;
    *owner_source = lease->owner_source;
    *mode_generation = lease->mode_generation;
    return RT_TRUE;
}

void rehab_can_lease_note_stop_result(rehab_can_lease_t *lease,
                                      rt_bool_t stopped,
                                      rt_bool_t ownership_changed)
{
    if (lease == RT_NULL)
    {
        return;
    }

    if (stopped || ownership_changed)
    {
        lease->active = RT_FALSE;
        lease->stop_latched = RT_FALSE;
        lease->has_stop_attempt = RT_FALSE;
    }
    else
    {
        lease->stop_retry_count++;
    }
}

rt_bool_t rehab_can_lease_can_enter_active_mode(const rehab_can_lease_t *lease)
{
    if (lease == RT_NULL)
    {
        return RT_FALSE;
    }
    return lease->stop_latched ? RT_FALSE : RT_TRUE;
}
