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


class XiaoZhiLatencyIpcContractTest(unittest.TestCase):
    def test_target_abi_contract(self):
        header_text = HEADER.read_text(encoding="utf-8")
        self.assertIn("rt_uint32_t type;", header_text)
        self.assertNotIn("m33_m55_msg_type_t type;", header_text)

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
#endif
""",
                encoding="ascii",
            )
            source = temp / "contract.c"
            source.write_text(
                f"""
#include <stddef.h>
#include \"{HEADER.as_posix()}\"

_Static_assert(MSG_TYPE_VOICE_CONFIG == 15, "existing enum ABI changed");
_Static_assert(MSG_TYPE_VOICE_LATENCY == 16, "latency enum must append");
_Static_assert(VOICE_LATENCY_FLAG_VALID == 1UL, "valid flag ABI");
_Static_assert(VOICE_LATENCY_FLAG_REAL_WAKE == 2UL, "real wake flag ABI");
_Static_assert(VOICE_LATENCY_FLAG_MANUAL == 4UL, "manual flag ABI");
_Static_assert(VOICE_LATENCY_FLAG_QA_TEXT == 8UL, "QA text flag ABI");
_Static_assert(VOICE_LATENCY_MS_UNAVAILABLE == 0xFFFFFFFFUL,
               "unavailable latency sentinel ABI");
_Static_assert(sizeof(voice_latency_msg_t) == 44, "latency payload ABI");
#define ASSERT_U32_FIELD(field, expected_offset)                             \
    _Static_assert(offsetof(voice_latency_msg_t, field) == expected_offset, \
                   #field " offset");                                      \
    _Static_assert(_Generic(((voice_latency_msg_t *)0)->field,              \
                            rt_uint32_t: 1, default: 0),                     \
                   #field " type")
ASSERT_U32_FIELD(turn_seq, 0);
ASSERT_U32_FIELD(flags, 4);
ASSERT_U32_FIELD(wake_to_listen_ms, 8);
ASSERT_U32_FIELD(last_voice_to_stop_ms, 12);
ASSERT_U32_FIELD(stop_to_stt_ms, 16);
ASSERT_U32_FIELD(stt_to_llm_ms, 20);
ASSERT_U32_FIELD(llm_to_tts_start_ms, 24);
ASSERT_U32_FIELD(tts_start_to_first_packet_ms, 28);
ASSERT_U32_FIELD(first_packet_to_first_write_ms, 32);
ASSERT_U32_FIELD(speech_end_to_first_write_ms, 36);
ASSERT_U32_FIELD(wake_to_first_write_ms, 40);
#undef ASSERT_U32_FIELD
_Static_assert(sizeof(((m33_m55_message_t *)0)->type) == 4,
               "wire message type width");
_Static_assert(_Generic(((m33_m55_message_t *)0)->type,
                        rt_uint32_t: 1, default: 0),
               "wire message type must be rt_uint32_t");
_Static_assert(offsetof(m33_m55_message_t, payload) == 8, "payload offset");
_Static_assert(offsetof(m33_m55_message_t, payload.voice_latency) == 8,
               "latency union offset");
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
