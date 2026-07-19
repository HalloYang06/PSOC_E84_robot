#ifndef REHAB_CAN_LEASE_H
#define REHAB_CAN_LEASE_H

#include <rtthread.h>

typedef struct
{
    rt_tick_t last_heartbeat_tick;
    rt_tick_t last_stop_attempt_tick;
    rt_uint32_t mode_generation;
    rt_uint32_t timeout_count;
    rt_uint32_t stop_retry_count;
    rt_uint8_t owner_source;
    rt_bool_t has_heartbeat;
    rt_bool_t active;
    rt_bool_t stop_latched;
    rt_bool_t has_stop_attempt;
} rehab_can_lease_t;

void rehab_can_lease_note_heartbeat(rehab_can_lease_t *lease, rt_tick_t now);
void rehab_can_lease_note_mode(rehab_can_lease_t *lease,
                               rt_bool_t active,
                               rt_uint8_t owner_source,
                               rt_uint32_t mode_generation);
rt_bool_t rehab_can_lease_claim_stop(rehab_can_lease_t *lease,
                                     rt_tick_t now,
                                     rt_tick_t timeout_ticks,
                                     rt_tick_t retry_ticks,
                                     rt_uint8_t *owner_source,
                                     rt_uint32_t *mode_generation);
void rehab_can_lease_note_stop_result(rehab_can_lease_t *lease,
                                      rt_bool_t stopped,
                                      rt_bool_t ownership_changed);
rt_bool_t rehab_can_lease_can_enter_active_mode(const rehab_can_lease_t *lease);

#endif
