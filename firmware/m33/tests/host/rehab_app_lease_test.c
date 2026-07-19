#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "rehab_app_lease.h"

static void test_heartbeat_requires_exact_owner_mode_and_session(void)
{
    rehab_app_lease_t lease = {0};

    assert(rehab_app_lease_begin(&lease, 3U, 7U, 11U, 100U, 500U) == RT_TRUE);
    assert(rehab_app_lease_note_heartbeat(&lease, 2U, 7U, 11U, 200U) == RT_FALSE);
    assert(lease.last_heartbeat_tick == 100U);
    assert(rehab_app_lease_note_heartbeat(&lease, 3U, 8U, 11U, 200U) == RT_FALSE);
    assert(rehab_app_lease_note_heartbeat(&lease, 3U, 7U, 12U, 200U) == RT_FALSE);
    assert(rehab_app_lease_note_heartbeat(&lease, 3U, 7U, 11U, 200U) == RT_TRUE);
    assert(lease.last_heartbeat_tick == 200U);
}

static void test_timeout_boundary_wrap_and_late_heartbeat(void)
{
    rehab_app_lease_t lease = {0};
    rt_uint32_t mode_generation = 0U;
    rt_uint32_t session_generation = 0U;
    rt_uint8_t owner_source = 0U;

    assert(rehab_app_lease_begin(&lease, 3U, 9U, 13U,
                                 UINT32_MAX - 20U, 50U) == RT_TRUE);
    assert(rehab_app_lease_claim_timeout_stop(&lease, 29U, 20U,
                                              &owner_source,
                                              &mode_generation,
                                              &session_generation) == RT_FALSE);
    assert(rehab_app_lease_claim_timeout_stop(&lease, 30U, 20U,
                                              &owner_source,
                                              &mode_generation,
                                              &session_generation) == RT_TRUE);
    assert(owner_source == 3U);
    assert(mode_generation == 9U);
    assert(session_generation == 13U);
    assert(lease.timeout_count == 1U);

    assert(rehab_app_lease_note_heartbeat(&lease, 3U, 9U, 13U, 31U) == RT_FALSE);
    assert(rehab_app_lease_claim_timeout_stop(&lease, 49U, 20U,
                                              &owner_source,
                                              &mode_generation,
                                              &session_generation) == RT_FALSE);
    assert(rehab_app_lease_claim_timeout_stop(&lease, 50U, 20U,
                                              &owner_source,
                                              &mode_generation,
                                              &session_generation) == RT_TRUE);
}

static void test_disconnect_only_latches_matching_session(void)
{
    rehab_app_lease_t lease = {0};
    rt_uint32_t mode_generation = 0U;
    rt_uint32_t session_generation = 0U;
    rt_uint8_t owner_source = 0U;

    assert(rehab_app_lease_begin(&lease, 3U, 5U, 21U, 100U, 500U) == RT_TRUE);
    assert(rehab_app_lease_claim_disconnect_stop(&lease, 20U, 110U, 20U,
                                                 &owner_source,
                                                 &mode_generation,
                                                 &session_generation) == RT_FALSE);
    assert(lease.stop_latched == RT_FALSE);
    assert(rehab_app_lease_claim_disconnect_stop(&lease, 21U, 110U, 20U,
                                                 &owner_source,
                                                 &mode_generation,
                                                 &session_generation) == RT_TRUE);
    assert(lease.disconnect_count == 1U);
    assert(session_generation == 21U);

    rehab_app_lease_note_stop_result(&lease, RT_FALSE, RT_FALSE);
    assert(lease.stop_retry_count == 1U);
    assert(rehab_app_lease_claim_disconnect_stop(&lease, 21U, 129U, 20U,
                                                 &owner_source,
                                                 &mode_generation,
                                                 &session_generation) == RT_FALSE);
    assert(rehab_app_lease_claim_disconnect_stop(&lease, 21U, 130U, 20U,
                                                 &owner_source,
                                                 &mode_generation,
                                                 &session_generation) == RT_TRUE);
}

static void test_latched_stop_blocks_begin_until_resolved(void)
{
    rehab_app_lease_t lease = {0};
    rt_uint32_t mode_generation = 0U;
    rt_uint32_t session_generation = 0U;
    rt_uint8_t owner_source = 0U;

    assert(rehab_app_lease_begin(&lease, 3U, 5U, 21U, 100U, 10U) == RT_TRUE);
    assert(rehab_app_lease_claim_timeout_stop(&lease, 111U, 20U,
                                              &owner_source,
                                              &mode_generation,
                                              &session_generation) == RT_TRUE);
    rehab_app_lease_note_stop_result(&lease, RT_FALSE, RT_FALSE);
    assert(rehab_app_lease_begin(&lease, 3U, 6U, 22U, 112U, 500U) == RT_FALSE);
    assert(lease.mode_generation == 5U);
    assert(lease.session_generation == 21U);
    assert(rehab_app_lease_claim_timeout_stop(&lease, 131U, 20U,
                                              &owner_source,
                                              &mode_generation,
                                              &session_generation) == RT_TRUE);

    rehab_app_lease_note_stop_result(&lease, RT_TRUE, RT_FALSE);
    assert(lease.active == RT_FALSE);
    assert(lease.stop_latched == RT_FALSE);
    assert(rehab_app_lease_begin(&lease, 3U, 6U, 22U, 132U, 500U) == RT_TRUE);
}

static void test_invalid_begin_and_claim_arguments_do_not_change_state(void)
{
    rehab_app_lease_t lease = {0};
    rt_uint32_t mode_generation = 0U;
    rt_uint32_t session_generation = 0U;
    rt_uint8_t owner_source = 0U;

    assert(rehab_app_lease_begin(&lease, 0U, 1U, 1U, 10U, 10U) == RT_FALSE);
    assert(rehab_app_lease_begin(&lease, 3U, 0U, 1U, 10U, 10U) == RT_FALSE);
    assert(rehab_app_lease_begin(&lease, 3U, 1U, 0U, 10U, 10U) == RT_FALSE);
    assert(rehab_app_lease_begin(&lease, 3U, 1U, 1U, 10U, 0U) == RT_FALSE);
    assert(lease.active == RT_FALSE);

    assert(rehab_app_lease_begin(&lease, 3U, 6U, 22U, 100U, 10U) == RT_TRUE);
    assert(rehab_app_lease_claim_timeout_stop(&lease, 111U, 20U,
                                              RT_NULL,
                                              &mode_generation,
                                              &session_generation) == RT_FALSE);
    assert(lease.stop_latched == RT_FALSE);
    assert(lease.timeout_count == 0U);
    assert(rehab_app_lease_claim_disconnect_stop(&lease, 22U, 111U, 20U,
                                                 &owner_source,
                                                 RT_NULL,
                                                 &session_generation) == RT_FALSE);
    assert(lease.stop_latched == RT_FALSE);
    assert(lease.disconnect_count == 0U);
}

static void test_active_begin_only_allows_same_owner_and_session(void)
{
    rehab_app_lease_t lease = {0};
    rt_uint32_t mode_generation = 0U;
    rt_uint32_t session_generation = 0U;
    rt_uint8_t owner_source = 0U;

    assert(rehab_app_lease_can_begin(&lease, 3U, 21U) == RT_TRUE);
    assert(rehab_app_lease_begin(&lease, 3U, 5U, 21U, 100U, 500U) == RT_TRUE);
    assert(rehab_app_lease_can_begin(&lease, 3U, 21U) == RT_TRUE);
    assert(rehab_app_lease_can_begin(&lease, 2U, 21U) == RT_FALSE);
    assert(rehab_app_lease_can_begin(&lease, 3U, 22U) == RT_FALSE);
    assert(rehab_app_lease_begin(&lease, 3U, 6U, 21U, 110U, 500U) == RT_TRUE);
    assert(lease.mode_generation == 6U);
    assert(lease.last_heartbeat_tick == 110U);

    lease.stop_latched = RT_TRUE;
    assert(rehab_app_lease_can_begin(&lease, 3U, 21U) == RT_FALSE);
    lease.stop_latched = RT_FALSE;

    assert(rehab_app_lease_begin(&lease, 2U, 7U, 21U, 120U, 500U) == RT_FALSE);
    assert(rehab_app_lease_begin(&lease, 3U, 7U, 22U, 120U, 500U) == RT_FALSE);
    assert(lease.owner_source == 3U);
    assert(lease.mode_generation == 6U);
    assert(lease.session_generation == 21U);
    assert(lease.last_heartbeat_tick == 110U);

    rehab_app_lease_revoke(&lease);
    assert(rehab_app_lease_begin(&lease, 3U, 7U, 22U, 120U, 500U) == RT_TRUE);
    assert(rehab_app_lease_claim_disconnect_stop(&lease, 21U, 121U, 20U,
                                                 &owner_source,
                                                 &mode_generation,
                                                 &session_generation) == RT_FALSE);
    assert(lease.stop_latched == RT_FALSE);
    assert(rehab_app_lease_can_begin(RT_NULL, 3U, 22U) == RT_FALSE);
    assert(rehab_app_lease_can_begin(&lease, 0U, 22U) == RT_FALSE);
    assert(rehab_app_lease_can_begin(&lease, 3U, 0U) == RT_FALSE);
}

static void test_unclaimed_stop_failure_does_not_increment_retry_count(void)
{
    rehab_app_lease_t lease = {0};

    rehab_app_lease_note_stop_result(&lease, RT_FALSE, RT_FALSE);
    assert(lease.stop_retry_count == 0U);
    assert(rehab_app_lease_begin(&lease, 3U, 5U, 21U, 100U, 500U) == RT_TRUE);
    rehab_app_lease_note_stop_result(&lease, RT_FALSE, RT_FALSE);
    assert(lease.stop_retry_count == 0U);
}

static void test_stop_result_or_revoke_clears_active_lease(void)
{
    rehab_app_lease_t lease = {0};

    assert(rehab_app_lease_begin(&lease, 3U, 5U, 21U, 100U, 500U) == RT_TRUE);
    lease.stop_latched = RT_TRUE;
    rehab_app_lease_note_stop_result(&lease, RT_FALSE, RT_TRUE);
    assert(lease.active == RT_FALSE);
    assert(lease.stop_latched == RT_FALSE);

    assert(rehab_app_lease_begin(&lease, 3U, 6U, 22U, 200U, 500U) == RT_TRUE);
    rehab_app_lease_revoke(&lease);
    assert(lease.active == RT_FALSE);
    assert(rehab_app_lease_note_heartbeat(&lease, 3U, 6U, 22U, 201U) == RT_FALSE);
}

int main(void)
{
    test_heartbeat_requires_exact_owner_mode_and_session();
    test_timeout_boundary_wrap_and_late_heartbeat();
    test_disconnect_only_latches_matching_session();
    test_latched_stop_blocks_begin_until_resolved();
    test_invalid_begin_and_claim_arguments_do_not_change_state();
    test_active_begin_only_allows_same_owner_and_session();
    test_unclaimed_stop_failure_does_not_increment_retry_count();
    test_stop_result_or_revoke_clears_active_lease();
    puts("rehab_app_lease_test PASS");
    return 0;
}
