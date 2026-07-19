from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
POST_RESET_C = (ROOT / "applications" / "m33" / "bt_post_reset.c").read_text(
    encoding="utf-8"
)


class M33BlePostResetStaticTest(unittest.TestCase):
    def test_platform_config_accessor_uses_vendor_prototype(self):
        self.assertIn('#include "cybt_platform_util.h"', POST_RESET_C)
        self.assertNotIn("#define HCI_UART_DEFAULT_BAUDRATE", POST_RESET_C)


if __name__ == "__main__":
    unittest.main()
