import pathlib
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "applications" / "m33" / "voice_mode_request_guard.c"


HARNESS = r'''
#include <assert.h>
#include <stdint.h>

#include "voice_mode_request_guard.h"

_Static_assert(VOICE_MODE_JOINT_MASK == 0x38U, "voice group mask");

static voice_mode_request_t request(uint32_t epoch,
                                    uint32_t id,
                                    uint32_t mode,
                                    uint32_t received_tick,
                                    uint32_t ttl_ms)
{
    voice_mode_request_t value = {
        VOICE_MODE_SOURCE_VOICE, epoch, id, VOICE_MODE_JOINT_MASK,
        mode, received_tick, ttl_ms,
    };
    return value;
}

int main(void)
{
    voice_mode_guard_t guard;
    voice_mode_request_t req;
    voice_mode_decision_t decision;

    voice_mode_guard_init(&guard);
    req = request(7U, 1U, VOICE_MODE_ASSIST, 100U, 500U);
    assert(voice_mode_guard_decide(&guard, &req, 100U, 1000U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_REJECT_EPOCH);
    assert(voice_mode_guard_accept_epoch(&guard, 0U,
                                         VOICE_MODE_CURRENT_PASSIVE, 0U) == 0U);
    assert(voice_mode_guard_accept_epoch(&guard, 7U,
                                         VOICE_MODE_CURRENT_ASSIST, 0U) == 0U);
    assert(voice_mode_guard_accept_epoch(&guard, 7U,
                                         VOICE_MODE_CURRENT_PASSIVE, 1U) == 0U);
    assert(voice_mode_guard_accept_epoch(&guard, 7U,
                                         VOICE_MODE_CURRENT_PASSIVE, 0U) == 1U);

    req = request(7U, 1U, VOICE_MODE_ASSIST, 100U, 500U);
    assert(voice_mode_guard_decide(&guard, &req, 100U, 0U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_REJECT_INVALID);
    req.ttl_ms = 501U;
    assert(voice_mode_guard_decide(&guard, &req, 100U, 1000U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_REJECT_INVALID);
    req = request(7U, 1U, 1U, 100U, 500U);
    assert(voice_mode_guard_decide(&guard, &req, 100U, 1000U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_REJECT_INVALID);

    /* 100 Hz: 50 ticks is exactly 500 ms; 51 ticks is expired. */
    req = request(7U, 1U, VOICE_MODE_ASSIST, 100U, 500U);
    assert(voice_mode_guard_decide(&guard, &req, 150U, 100U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_APPLY_ACTIVE);
    assert(voice_mode_guard_decide(&guard, &req, 151U, 100U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_REJECT_EXPIRED);
    req = request(7U, 1U, VOICE_MODE_ASSIST, 0xfffffff0U, 32U);
    assert(voice_mode_guard_decide(&guard, &req, 0x00000010U, 1000U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_APPLY_ACTIVE);
    assert(voice_mode_guard_decide(&guard, &req, 0x00000011U, 1000U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_REJECT_EXPIRED);

    req = request(7U, 10U, VOICE_MODE_ASSIST, 1000U, 500U);
    decision = voice_mode_guard_decide(&guard, &req, 1000U, 1000U,
                                       VOICE_MODE_CURRENT_PASSIVE, 0U, 0U);
    assert(decision == VOICE_MODE_DECISION_REJECT_PRECONDITION);
    assert(voice_mode_guard_commit(&guard, &req, decision) == 0U);
    assert(guard.committed_request_id == 0U);
    decision = voice_mode_guard_decide(&guard, &req, 1000U, 1000U,
                                       VOICE_MODE_CURRENT_PASSIVE, 0U, 1U);
    assert(decision == VOICE_MODE_DECISION_APPLY_ACTIVE);
    assert(voice_mode_guard_commit(&guard, &req, decision) == 1U);
    assert(voice_mode_guard_accept_epoch(&guard, 7U,
                                         VOICE_MODE_CURRENT_PASSIVE, 0U) == 1U);
    assert(voice_mode_guard_decide(&guard, &req, 1001U, 1000U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_REJECT_DUPLICATE);
    req = request(7U, 9U, VOICE_MODE_PASSIVE, 1001U, 500U);
    assert(voice_mode_guard_decide(&guard, &req, 1001U, 1000U,
                                   VOICE_MODE_CURRENT_ASSIST, 1U, 0U) ==
           VOICE_MODE_DECISION_REJECT_STALE);

    /* A fresh trusted STOP/passive request preempts every active mode. */
    req = request(7U, 11U, VOICE_MODE_PASSIVE, 1010U, 500U);
    assert(voice_mode_guard_decide(&guard, &req, 1010U, 1000U,
                                   VOICE_MODE_CURRENT_OTHER_ACTIVE, 1U, 0U) ==
           VOICE_MODE_DECISION_APPLY_PASSIVE);

    req = request(7U, 12U, VOICE_MODE_RESIST, 1020U, 500U);
    assert(voice_mode_guard_decide(&guard, &req, 1020U, 1000U,
                                   VOICE_MODE_CURRENT_ASSIST, 1U, 1U) ==
           VOICE_MODE_DECISION_NEEDS_PASSIVE);
    assert(voice_mode_guard_decide(&guard, &req, 1020U, 1000U,
                                   VOICE_MODE_CURRENT_OTHER_ACTIVE, 1U, 1U) ==
           VOICE_MODE_DECISION_NEEDS_PASSIVE);

    /* Same mode is an idempotent no-op, and a successful no-op is deduped. */
    req = request(7U, 13U, VOICE_MODE_ASSIST, 1030U, 500U);
    decision = voice_mode_guard_decide(&guard, &req, 1030U, 1000U,
                                       VOICE_MODE_CURRENT_ASSIST, 1U, 1U);
    assert(decision == VOICE_MODE_DECISION_ALREADY_ACTIVE);
    assert(voice_mode_guard_commit(&guard, &req, decision) == 1U);
    assert(voice_mode_guard_decide(&guard, &req, 1030U, 1000U,
                                   VOICE_MODE_CURRENT_ASSIST, 1U, 1U) ==
           VOICE_MODE_DECISION_REJECT_DUPLICATE);

    /* Epoch changes are never accepted by decide, including old replay. */
    req = request(8U, 1U, VOICE_MODE_ASSIST, 1040U, 500U);
    assert(voice_mode_guard_decide(&guard, &req, 1040U, 1000U,
                                   VOICE_MODE_CURRENT_ASSIST, 1U, 1U) ==
           VOICE_MODE_DECISION_NEEDS_REARM);
    assert(voice_mode_guard_decide(&guard, &req, 1040U, 1000U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_REJECT_EPOCH);
    assert(voice_mode_guard_accept_epoch(&guard, 8U,
                                         VOICE_MODE_CURRENT_PASSIVE, 0U) == 1U);
    req = request(7U, 14U, VOICE_MODE_PASSIVE, 1050U, 500U);
    assert(voice_mode_guard_decide(&guard, &req, 1050U, 1000U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_REJECT_EPOCH);
    req.received_tick = 1U;
    assert(voice_mode_guard_decide(&guard, &req, 1050U, 1000U,
                                   VOICE_MODE_CURRENT_PASSIVE, 0U, 1U) ==
           VOICE_MODE_DECISION_REJECT_EPOCH);

    req = request(8U, 2U, VOICE_MODE_PASSIVE, 1060U, 500U);
    assert(voice_mode_guard_commit(&guard, &req,
                                   VOICE_MODE_DECISION_APPLY_ACTIVE) == 0U);
    assert(guard.committed_request_id == 0U);

    return 0;
}
'''


def test_voice_mode_request_guard_behavior():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = pathlib.Path(temp_dir)
        harness = temp / "voice_mode_request_guard_test.c"
        executable = temp / "voice_mode_request_guard_test.exe"
        harness.write_text(HARNESS, encoding="ascii")
        result = subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "applications" / "m33"), str(harness),
             str(SOURCE), "-o", str(executable)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stderr
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
