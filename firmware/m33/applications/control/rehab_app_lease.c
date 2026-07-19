#include "rehab_app_lease.h"

static rt_bool_t rehab_app_lease_claim_latched_stop(
    rehab_app_lease_t *lease,
    rt_tick_t now,
    rt_tick_t retry_ticks,
    rt_uint8_t *owner_source,
    rt_uint32_t *mode_generation,
    rt_uint32_t *session_generation)
{
    if ((owner_source == RT_NULL) || (mode_generation == RT_NULL) ||
        (session_generation == RT_NULL))
    {
        return RT_FALSE;
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
    *session_generation = lease->session_generation;
    return RT_TRUE;
}

rt_bool_t rehab_app_lease_can_begin(const rehab_app_lease_t *lease,
                                    rt_uint8_t owner_source,
                                    rt_uint32_t session_generation)
{
    if ((lease == RT_NULL) || (owner_source == 0U) ||
        (session_generation == 0U))
    {
        return RT_FALSE;
    }
    if (!lease->active)
    {
        return RT_TRUE;
    }
    return (!lease->stop_latched && (lease->owner_source == owner_source) &&
            (lease->session_generation == session_generation))
               ? RT_TRUE
               : RT_FALSE;
}

rt_bool_t rehab_app_lease_begin(rehab_app_lease_t *lease,
                                rt_uint8_t owner_source,
                                rt_uint32_t mode_generation,
                                rt_uint32_t session_generation,
                                rt_tick_t now,
                                rt_tick_t timeout_ticks)
{
    if ((mode_generation == 0U) || (timeout_ticks == 0U) ||
        !rehab_app_lease_can_begin(lease, owner_source, session_generation))
    {
        return RT_FALSE;
    }

    lease->owner_source = owner_source;
    lease->mode_generation = mode_generation;
    lease->session_generation = session_generation;
    lease->last_heartbeat_tick = now;
    lease->timeout_ticks = timeout_ticks;
    lease->active = RT_TRUE;
    lease->stop_latched = RT_FALSE;
    lease->has_stop_attempt = RT_FALSE;
    return RT_TRUE;
}

rt_bool_t rehab_app_lease_note_heartbeat(rehab_app_lease_t *lease,
                                         rt_uint8_t owner_source,
                                         rt_uint32_t mode_generation,
                                         rt_uint32_t session_generation,
                                         rt_tick_t now)
{
    if ((lease == RT_NULL) || !lease->active || lease->stop_latched ||
        (lease->owner_source != owner_source) ||
        (lease->mode_generation != mode_generation) ||
        (lease->session_generation != session_generation))
    {
        return RT_FALSE;
    }

    lease->last_heartbeat_tick = now;
    return RT_TRUE;
}

rt_bool_t rehab_app_lease_claim_timeout_stop(rehab_app_lease_t *lease,
                                              rt_tick_t now,
                                              rt_tick_t retry_ticks,
                                              rt_uint8_t *owner_source,
                                              rt_uint32_t *mode_generation,
                                              rt_uint32_t *session_generation)
{
    if ((lease == RT_NULL) || (owner_source == RT_NULL) ||
        (mode_generation == RT_NULL) || (session_generation == RT_NULL) ||
        !lease->active)
    {
        return RT_FALSE;
    }

    if (!lease->stop_latched)
    {
        if ((now - lease->last_heartbeat_tick) <= lease->timeout_ticks)
        {
            return RT_FALSE;
        }
        lease->stop_latched = RT_TRUE;
        lease->timeout_count++;
    }

    return rehab_app_lease_claim_latched_stop(lease,
                                               now,
                                               retry_ticks,
                                               owner_source,
                                               mode_generation,
                                               session_generation);
}

rt_bool_t rehab_app_lease_claim_disconnect_stop(rehab_app_lease_t *lease,
                                                 rt_uint32_t session_generation,
                                                 rt_tick_t now,
                                                 rt_tick_t retry_ticks,
                                                 rt_uint8_t *owner_source,
                                                 rt_uint32_t *mode_generation,
                                                 rt_uint32_t *claimed_session_generation)
{
    if ((lease == RT_NULL) || (owner_source == RT_NULL) ||
        (mode_generation == RT_NULL) ||
        (claimed_session_generation == RT_NULL) || !lease->active ||
        (lease->session_generation != session_generation))
    {
        return RT_FALSE;
    }

    if (!lease->stop_latched)
    {
        lease->stop_latched = RT_TRUE;
        lease->disconnect_count++;
    }

    return rehab_app_lease_claim_latched_stop(lease,
                                               now,
                                               retry_ticks,
                                               owner_source,
                                               mode_generation,
                                               claimed_session_generation);
}

void rehab_app_lease_note_stop_result(rehab_app_lease_t *lease,
                                      rt_bool_t stopped,
                                      rt_bool_t ownership_changed)
{
    if (lease == RT_NULL)
    {
        return;
    }

    if (stopped || ownership_changed)
    {
        rehab_app_lease_revoke(lease);
    }
    else if (lease->active && lease->stop_latched && lease->has_stop_attempt)
    {
        lease->stop_retry_count++;
    }
}

void rehab_app_lease_revoke(rehab_app_lease_t *lease)
{
    if (lease == RT_NULL)
    {
        return;
    }

    lease->active = RT_FALSE;
    lease->stop_latched = RT_FALSE;
    lease->has_stop_attempt = RT_FALSE;
}
