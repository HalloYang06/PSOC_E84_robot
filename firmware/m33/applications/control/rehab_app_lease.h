#ifndef REHAB_APP_LEASE_H
#define REHAB_APP_LEASE_H

#include <rtthread.h>

typedef struct
{
    rt_tick_t last_heartbeat_tick;
    rt_tick_t last_stop_attempt_tick;
    rt_tick_t timeout_ticks;
    rt_uint32_t mode_generation;
    rt_uint32_t session_generation;
    rt_uint32_t timeout_count;
    rt_uint32_t disconnect_count;
    rt_uint32_t stop_retry_count;
    rt_uint8_t owner_source;
    rt_bool_t active;
    rt_bool_t stop_latched;
    rt_bool_t has_stop_attempt;
} rehab_app_lease_t;

rt_bool_t rehab_app_lease_can_begin(const rehab_app_lease_t *lease,
                                    rt_uint8_t owner_source,
                                    rt_uint32_t session_generation);
rt_bool_t rehab_app_lease_begin(rehab_app_lease_t *lease,
                                rt_uint8_t owner_source,
                                rt_uint32_t mode_generation,
                                rt_uint32_t session_generation,
                                rt_tick_t now,
                                rt_tick_t timeout_ticks);
rt_bool_t rehab_app_lease_note_heartbeat(rehab_app_lease_t *lease,
                                         rt_uint8_t owner_source,
                                         rt_uint32_t mode_generation,
                                         rt_uint32_t session_generation,
                                         rt_tick_t now);
rt_bool_t rehab_app_lease_claim_timeout_stop(rehab_app_lease_t *lease,
                                              rt_tick_t now,
                                              rt_tick_t retry_ticks,
                                              rt_uint8_t *owner_source,
                                              rt_uint32_t *mode_generation,
                                              rt_uint32_t *session_generation);
rt_bool_t rehab_app_lease_claim_disconnect_stop(rehab_app_lease_t *lease,
                                                 rt_uint32_t session_generation,
                                                 rt_tick_t now,
                                                 rt_tick_t retry_ticks,
                                                 rt_uint8_t *owner_source,
                                                 rt_uint32_t *mode_generation,
                                                 rt_uint32_t *claimed_session_generation);
void rehab_app_lease_note_stop_result(rehab_app_lease_t *lease,
                                      rt_bool_t stopped,
                                      rt_bool_t ownership_changed);
void rehab_app_lease_revoke(rehab_app_lease_t *lease);

#endif
