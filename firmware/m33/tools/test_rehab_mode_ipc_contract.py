import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "applications" / "common" / "m33_m55_comm.h"
DEFAULT_CC = Path(
    r"F:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM"
    r"\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin\arm-none-eabi-gcc.exe"
)


class RehabModeIpcContractTest(unittest.TestCase):
    def test_target_abi_contract(self):
        self.assertNotIn("REHAB_MODE_RESULT_LOST", HEADER.read_text(encoding="utf-8"))

        compiler = os.environ.get("ARM_NONE_EABI_GCC")
        if not compiler:
            compiler = shutil.which("arm-none-eabi-gcc") or str(DEFAULT_CC)
        self.assertTrue(Path(compiler).is_file(), f"compiler not found: {compiler}")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            (temp / "rtthread.h").write_text(
                """
#ifndef RTTHREAD_H
#define RTTHREAD_H
typedef unsigned char rt_uint8_t;
typedef signed short rt_int16_t;
typedef unsigned short rt_uint16_t;
typedef signed int rt_int32_t;
typedef unsigned int rt_uint32_t;
typedef unsigned int rt_tick_t;
typedef int rt_err_t;
typedef int rt_bool_t;
#define RT_NAME_MAX 8
#define RT_NULL ((void *)0)
#endif
""",
                encoding="ascii",
            )
            (temp / "rthw.h").write_text(
                """
#ifndef RTHW_H
#define RTHW_H
#define RT_HW_CACHE_FLUSH 0
#define RT_HW_CACHE_INVALIDATE 1
static inline void rt_hw_cpu_dcache_ops(int ops, void *addr, int size)
{
    (void)ops;
    (void)addr;
    (void)size;
}
#endif
""",
                encoding="ascii",
            )
            source = temp / "contract.c"
            source.write_text(
                f"""
#include <stddef.h>
#include \"{HEADER.as_posix()}\"

typedef enum
{{
    REHAB_MODE_PASSIVE = 0,
    REHAB_MODE_ASSIST = 3,
    REHAB_MODE_RESIST = 4
}} existing_rehab_mode_t;

_Static_assert(MSG_TYPE_VOICE_LATENCY == 16, "existing latency ABI changed");
_Static_assert(MSG_TYPE_REHAB_MODE_REQUEST == 17, "request type ABI");
_Static_assert(MSG_TYPE_REHAB_MODE_RESULT == 18, "result type ABI");
_Static_assert(REHAB_MODE_PROTOCOL_VERSION == 3UL, "protocol version ABI");
_Static_assert(REHAB_MODE_SOURCE_VOICE == 1UL, "voice source ABI");
_Static_assert(REHAB_MODE_ACTION_SET_MODE == 0UL, "set-mode action ABI");
_Static_assert(REHAB_MODE_ACTION_LEVEL_UP == 1UL, "level-up action ABI");
_Static_assert(REHAB_MODE_ACTION_LEVEL_DOWN == 2UL, "level-down action ABI");
_Static_assert(REHAB_MODE_REQUEST_MODE_PASSIVE == 0UL, "passive mode ABI");
_Static_assert(REHAB_MODE_REQUEST_MODE_ASSIST == 3UL, "assist mode ABI");
_Static_assert(REHAB_MODE_REQUEST_MODE_RESIST == 4UL, "resist mode ABI");
_Static_assert(REHAB_MODE_JOINT_MASK == 0x38UL, "joint mask ABI");
_Static_assert(REHAB_MODE_MAX_TTL_MS == 500UL, "maximum TTL ABI");
_Static_assert(REHAB_MODE_RESULT_NONE == 0UL, "none result ABI");
_Static_assert(REHAB_MODE_RESULT_INVALID == 1UL, "invalid result ABI");
_Static_assert(REHAB_MODE_RESULT_QUEUE_FULL == 2UL, "queue-full result ABI");
_Static_assert(REHAB_MODE_RESULT_DUPLICATE == 3UL, "duplicate result ABI");
_Static_assert(REHAB_MODE_RESULT_STALE == 4UL, "stale result ABI");
_Static_assert(REHAB_MODE_RESULT_BUSY == 5UL, "busy result ABI");
_Static_assert(REHAB_MODE_RESULT_PRECONDITION == 6UL, "precondition result ABI");
_Static_assert(REHAB_MODE_RESULT_STOP_FAILED == 7UL, "stop-failed result ABI");
_Static_assert(REHAB_MODE_RESULT_APPLIED == 8UL, "applied result ABI");

#define ASSERT_REQUEST_U32(field, expected_offset)                               \
    _Static_assert(offsetof(rehab_mode_request_msg_t, field) == expected_offset, \
                   #field " request offset");                                  \
    _Static_assert(_Generic(((rehab_mode_request_msg_t *)0)->field,              \
                            rt_uint32_t: 1, default: 0),                          \
                   #field " request type")
_Static_assert(sizeof(rehab_mode_request_msg_t) == 32, "request payload ABI");
ASSERT_REQUEST_U32(version, 0);
ASSERT_REQUEST_U32(boot_epoch, 4);
ASSERT_REQUEST_U32(request_id, 8);
ASSERT_REQUEST_U32(source, 12);
ASSERT_REQUEST_U32(mode, 16);
ASSERT_REQUEST_U32(joint_mask, 20);
ASSERT_REQUEST_U32(ttl_ms, 24);
ASSERT_REQUEST_U32(action, 28);
#undef ASSERT_REQUEST_U32

#define ASSERT_RESULT_U32(field, expected_offset)                              \
    _Static_assert(offsetof(rehab_mode_result_msg_t, field) == expected_offset, \
                   #field " result offset");                                  \
    _Static_assert(_Generic(((rehab_mode_result_msg_t *)0)->field,              \
                            rt_uint32_t: 1, default: 0),                         \
                   #field " result type")
_Static_assert(sizeof(rehab_mode_result_msg_t) == 36, "result payload ABI");
ASSERT_RESULT_U32(version, 0);
ASSERT_RESULT_U32(boot_epoch, 4);
ASSERT_RESULT_U32(request_id, 8);
ASSERT_RESULT_U32(status, 12);
ASSERT_RESULT_U32(detail, 16);
ASSERT_RESULT_U32(requested_mode, 20);
ASSERT_RESULT_U32(applied_mode, 24);
ASSERT_RESULT_U32(joint_mask, 28);
ASSERT_RESULT_U32(mode_generation, 32);
#undef ASSERT_RESULT_U32

_Static_assert(sizeof(((m33_m55_message_t *)0)->type) == 4,
               "wire message type width");
_Static_assert(_Generic(((m33_m55_message_t *)0)->type,
                        rt_uint32_t: 1, default: 0),
               "wire message type must be rt_uint32_t");
_Static_assert(offsetof(m33_m55_message_t, payload) == 8, "payload offset");
_Static_assert(offsetof(m33_m55_message_t, payload.rehab_mode_request) == 8,
               "request union offset");
_Static_assert(offsetof(m33_m55_message_t, payload.rehab_mode_result) == 8,
               "result union offset");
_Static_assert(sizeof(m33_m55_message_t) == 308, "message ABI size");
int main(void) {{ return 0; }}
""",
                encoding="ascii",
            )
            result = subprocess.run(
                [
                    compiler,
                    "-std=c11",
                    "-fshort-enums",
                    "-fsyntax-only",
                    f"-I{temp}",
                    str(source),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
