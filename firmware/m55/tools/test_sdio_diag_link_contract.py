from pathlib import Path
import unittest


M55_ROOT = Path(__file__).resolve().parents[1]
MMCSD_CORE = M55_ROOT / "rt-thread" / "components" / "drivers" / "sdio" / "mmcsd_core.c"
DRV_SDIO = M55_ROOT / "libraries" / "HAL_Drivers" / "drv_sdio.c"


class SdioDiagLinkContractTest(unittest.TestCase):
    def test_mmcsd_diag_symbols_are_defined(self):
        text = MMCSD_CORE.read_text(encoding="utf-8")

        expected = [
            "g_mmcsd_diag_core_init",
            "g_mmcsd_diag_thread_started",
            "g_mmcsd_diag_change_sent",
            "g_mmcsd_diag_change_err",
            "g_mmcsd_diag_recv_count",
            "g_mmcsd_diag_power_up_count",
            "g_mmcsd_diag_cmd5_before_count",
            "g_mmcsd_diag_cmd5_after_count",
            "g_mmcsd_diag_cmd5_last_err",
        ]

        for symbol in expected:
            with self.subTest(symbol=symbol):
                self.assertRegex(text, rf"volatile\s+rt_(?:u)?int32_t\s+{symbol}")

    def test_mmcsd_diag_counters_track_detection_flow(self):
        text = MMCSD_CORE.read_text(encoding="utf-8")

        self.assertIn("g_mmcsd_diag_core_init++", text)
        self.assertIn("g_mmcsd_diag_thread_started++", text)
        self.assertIn("g_mmcsd_diag_change_sent++", text)
        self.assertIn("g_mmcsd_diag_change_err++", text)
        self.assertIn("g_mmcsd_diag_recv_count++", text)
        self.assertIn("g_mmcsd_diag_power_up_count++", text)
        self.assertIn("g_mmcsd_diag_cmd5_before_count++", text)
        self.assertIn("g_mmcsd_diag_cmd5_after_count++", text)
        self.assertIn("g_mmcsd_diag_cmd5_last_err = err", text)

    def test_m55_sdio_kick_change_requeues_ready_hosts(self):
        text = DRV_SDIO.read_text(encoding="utf-8")

        self.assertIn("void m55_sdio_kick_change(void)", text)
        self.assertIn("mmcsd_change(sdio0->host)", text)
        self.assertIn("mmcsd_change(sdio1->host)", text)


if __name__ == "__main__":
    unittest.main()
