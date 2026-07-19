from pathlib import Path
import re
import subprocess
import tempfile
import unittest


M55_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = M55_ROOT.parent
M33_ROOT = WORKSPACE_ROOT / "Edgi_Talk_M33_LSM6DS3"


class EdgeAiSharedContractTest(unittest.TestCase):
    def setUp(self):
        self.contract_headers = [
            M33_ROOT / "applications" / "edge_ai" / "edge_ai_result_contract.h",
            M55_ROOT / "applications" / "edge_ai_bridge" / "edge_ai_result_contract.h",
        ]

    def test_result_contract_headers_are_shared_by_both_cores(self):
        for header in self.contract_headers:
            with self.subTest(header=str(header)):
                self.assertTrue(header.exists(), f"missing contract header: {header}")
                text = header.read_text(encoding="utf-8")
                self.assertRegex(text, r"#define\s+EDGE_AI_RESULT_BLOCK_OFFSET\s+0x00001000u")
                self.assertRegex(text, r"#define\s+EDGE_AI_RESULT_MAGIC\s+0x45414952u")
                self.assertIn("EDGE_AI_RESULT_FLAG_VALID", text)
                self.assertIn("EDGE_AI_RESULT_FLAG_AUX_ONLY", text)
                self.assertIn("EDGE_AI_RESULT_FLAG_TIMEOUT", text)
                self.assertIn("EDGE_AI_RESULT_FLAG_STALE_REJECTED", text)
                self.assertIn("typedef struct", text)
                self.assertIn("edge_ai_result_sharedmem_block_t", text)
                for field in [
                    "source_sequence",
                    "result_sequence",
                    "valid_flags",
                    "confidence_permille",
                    "latency_ms",
                    "commit_sequence",
                ]:
                    self.assertIn(field, text)

    def test_result_contract_headers_compile_as_c99(self):
        source = """
        #include "edge_ai_result_contract.h"

        int main(void)
        {
            edge_ai_result_sharedmem_block_t block;
            block.magic = EDGE_AI_RESULT_MAGIC;
            block.version = EDGE_AI_RESULT_VERSION;
            block.valid_flags = EDGE_AI_RESULT_FLAG_VALID | EDGE_AI_RESULT_FLAG_AUX_ONLY;
            return (block.magic == EDGE_AI_RESULT_MAGIC &&
                    block.version == EDGE_AI_RESULT_VERSION &&
                    (block.valid_flags & EDGE_AI_RESULT_FLAG_AUX_ONLY) != 0u &&
                    EDGE_AI_RESULT_BLOCK_OFFSET == 0x00001000u) ? 0 : 1;
        }
        """
        for header in self.contract_headers:
            with self.subTest(header=str(header)):
                with tempfile.TemporaryDirectory() as tmpdir:
                    c_file = Path(tmpdir) / "contract_compile_test.c"
                    exe_file = Path(tmpdir) / "contract_compile_test.exe"
                    c_file.write_text(source, encoding="utf-8")
                    result = subprocess.run(
                        [
                            "gcc",
                            "-std=c99",
                            "-Wall",
                            "-Wextra",
                            "-Werror",
                            "-I",
                            str(header.parent),
                            str(c_file),
                            "-o",
                            str(exe_file),
                        ],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stdout + result.stderr,
                    )


if __name__ == "__main__":
    unittest.main()
