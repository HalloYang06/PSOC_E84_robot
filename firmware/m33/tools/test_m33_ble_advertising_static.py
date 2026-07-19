from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
GAP_C = (ROOT / "applications" / "m33" / "cycfg_gap.c").read_text(
    encoding="utf-8"
)
GAP_H = (ROOT / "applications" / "m33" / "cycfg_gap.h").read_text(
    encoding="utf-8"
)


class M33BleAdvertisingStaticTest(unittest.TestCase):
    def test_primary_advertisement_exposes_nus_uuid_within_31_bytes(self):
        name_match = re.search(r"cy_bt_adv_packet_elem_1\[(\d+)\]", GAP_C)
        self.assertIsNotNone(name_match)
        name_len = int(name_match.group(1))

        self.assertIn("cy_bt_adv_packet_elem_2[16] = {__UUID_SERVICE_NUS}", GAP_C)
        self.assertIn("BTM_BLE_ADVERT_TYPE_128SRV_COMPLETE", GAP_C)
        self.assertIn("#define CY_BT_ADV_PACKET_ELEM_COUNT 3", GAP_H)
        self.assertLessEqual((1 + 2) + (name_len + 2) + (16 + 2), 31)


if __name__ == "__main__":
    unittest.main()
