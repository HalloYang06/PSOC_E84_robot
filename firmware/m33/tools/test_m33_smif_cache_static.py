from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUARD_C = ROOT / "board" / "smif0_guard.c"


class M33SmifCacheStaticTest(unittest.TestCase):
    def test_sram_guard_invalidates_cpuss_icache_before_returning_to_xip(self):
        body = GUARD_C.read_text(encoding="utf-8", errors="ignore")

        self.assertIn(".cy_ramfunc", body)
        self.assertIn(
            "ICACHE0->CMD = ICACHE_CMD_INV_Msk | ICACHE_CMD_BUFF_INV_Msk",
            body,
        )
        self.assertIn(
            "ICACHE0->CMD & (ICACHE_CMD_INV_Msk | ICACHE_CMD_BUFF_INV_Msk)",
            body,
        )
        self.assertNotIn("Cy_SMIF_CacheInvalidate", body)


if __name__ == "__main__":
    unittest.main()
