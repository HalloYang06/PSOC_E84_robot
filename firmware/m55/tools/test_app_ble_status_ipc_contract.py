import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "applications" / "m33_m55_comm.h"
DEFAULT_CC = Path(
    r"F:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM"
    r"\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin\arm-none-eabi-gcc.exe"
)


class AppBleStatusIpcContractTest(unittest.TestCase):
    def test_target_abi_contract(self):
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

_Static_assert(MSG_TYPE_VOICE_LATENCY == 16, "latency ABI changed");
_Static_assert(MSG_TYPE_REHAB_MODE_REQUEST == 17, "rehab request ABI changed");
_Static_assert(MSG_TYPE_REHAB_MODE_RESULT == 18, "rehab result ABI changed");
_Static_assert(MSG_TYPE_APP_BLE_STATUS == 19, "BLE status type ABI");
_Static_assert(APP_BLE_STATUS_PROTOCOL_VERSION == 1UL, "BLE status version ABI");
_Static_assert(sizeof(app_ble_status_msg_t) == 12, "BLE status payload ABI");
_Static_assert(offsetof(app_ble_status_msg_t, version) == 0, "version offset");
_Static_assert(offsetof(app_ble_status_msg_t, connected) == 4, "connected offset");
_Static_assert(offsetof(app_ble_status_msg_t, link_seq) == 8, "link sequence offset");
_Static_assert(offsetof(m33_m55_message_t, payload) == 8, "payload offset");
_Static_assert(offsetof(m33_m55_message_t, payload.app_ble_status) == 8,
               "BLE status union offset");
_Static_assert(sizeof(m33_m55_message_t) == 308, "message ABI size changed");
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
