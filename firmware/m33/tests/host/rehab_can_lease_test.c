#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "rehab_can_lease.h"

static void test_expiry_latches_and_late_heartbeat_does_not_cancel_stop(void)
{
    rehab_can_lease_t lease = {0};
    rt_uint32_t generation = 0U;
    rt_uint8_t owner_source = 0U;

    rehab_can_lease_note_heartbeat(&lease, 100U);
    rehab_can_lease_note_mode(&lease, RT_TRUE, 1U, 7U);
    assert(rehab_can_lease_claim_stop(&lease, 600U, 500U, 100U,
                                      &owner_source, &generation) == RT_FALSE);
    assert(rehab_can_lease_claim_stop(&lease, 601U, 500U, 100U,
                                      &owner_source, &generation) == RT_TRUE);
    assert(owner_source == 1U);
    assert(generation == 7U);

    rehab_can_lease_note_heartbeat(&lease, 602U);
    assert(rehab_can_lease_claim_stop(&lease, 603U, 500U, 100U,
                                      &owner_source, &generation) == RT_FALSE);
    assert(rehab_can_lease_claim_stop(&lease, 701U, 500U, 100U,
                                      &owner_source, &generation) == RT_TRUE);
}

static void test_failed_stop_remains_latched_for_retry(void)
{
    rehab_can_lease_t lease = {0};
    rt_uint32_t generation = 0U;
    rt_uint8_t owner_source = 0U;

    rehab_can_lease_note_heartbeat(&lease, 10U);
    rehab_can_lease_note_mode(&lease, RT_TRUE, 2U, 3U);
    assert(rehab_can_lease_claim_stop(&lease, 100U, 50U, 20U,
                                      &owner_source, &generation) == RT_TRUE);
    assert(owner_source == 2U);
    rehab_can_lease_note_stop_result(&lease, RT_FALSE, RT_FALSE);

    assert(lease.stop_retry_count == 1U);
    assert(rehab_can_lease_claim_stop(&lease, 101U, 50U, 20U,
                                      &owner_source, &generation) == RT_FALSE);
    assert(rehab_can_lease_claim_stop(&lease, 120U, 50U, 20U,
                                      &owner_source, &generation) == RT_TRUE);
    assert(rehab_can_lease_can_enter_active_mode(&lease) == RT_FALSE);
}

static void test_success_or_ownership_change_releases_old_lease(void)
{
    rehab_can_lease_t lease = {0};
    rt_uint32_t generation = 0U;
    rt_uint8_t owner_source = 0U;

    rehab_can_lease_note_heartbeat(&lease, 10U);
    rehab_can_lease_note_mode(&lease, RT_TRUE, 1U, 3U);
    assert(rehab_can_lease_claim_stop(&lease, 100U, 50U, 20U,
                                      &owner_source, &generation) == RT_TRUE);
    rehab_can_lease_note_stop_result(&lease, RT_TRUE, RT_FALSE);
    assert(lease.active == RT_FALSE);
    assert(lease.stop_latched == RT_FALSE);

    rehab_can_lease_note_mode(&lease, RT_TRUE, 2U, 4U);
    lease.stop_latched = RT_TRUE;
    rehab_can_lease_note_stop_result(&lease, RT_FALSE, RT_TRUE);
    assert(lease.active == RT_FALSE);
    assert(lease.stop_latched == RT_FALSE);
}

static void test_tick_wrap_uses_unsigned_age(void)
{
    rehab_can_lease_t lease = {0};
    rt_uint32_t generation = 0U;
    rt_uint8_t owner_source = 0U;

    rehab_can_lease_note_heartbeat(&lease, UINT32_MAX - 20U);
    rehab_can_lease_note_mode(&lease, RT_TRUE, 1U, 9U);
    assert(rehab_can_lease_claim_stop(&lease, 29U, 50U, 20U,
                                      &owner_source, &generation) == RT_FALSE);
    assert(rehab_can_lease_claim_stop(&lease, 30U, 50U, 20U,
                                      &owner_source, &generation) == RT_TRUE);
}

int main(void)
{
    test_expiry_latches_and_late_heartbeat_does_not_cancel_stop();
    test_failed_stop_remains_latched_for_retry();
    test_success_or_ownership_change_releases_old_lease();
    test_tick_wrap_uses_unsigned_age();
    puts("rehab_can_lease_test PASS");
    return 0;
}
