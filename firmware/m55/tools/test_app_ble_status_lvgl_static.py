from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "applications" / "main.c"
PANEL = ROOT / "applications" / "rehab_wifi_panel.c"
PANEL_HEADER = ROOT / "applications" / "rehab_wifi_panel.h"


class AppBleStatusLvglStaticTest(unittest.TestCase):
    def test_ipc_consumer_updates_snapshot(self):
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn('#include "rehab_wifi_panel.h"', source)
        self.assertIn("msg.type == MSG_TYPE_APP_BLE_STATUS", source)
        self.assertIn("APP_BLE_STATUS_PROTOCOL_VERSION", source)
        self.assertIn("rehab_wifi_panel_note_ble_status", source)

    def test_non_ui_consumer_never_calls_lvgl(self):
        source = PANEL.read_text(encoding="utf-8")
        start = source.index("void rehab_wifi_panel_note_ble_status(")
        end = source.index("\n}", start) + 2
        consumer = source[start:end]
        self.assertNotIn("lv_", consumer)
        self.assertIn("rt_hw_interrupt_disable", consumer)
        self.assertIn("rt_hw_interrupt_enable", consumer)

    def test_lvgl_refresh_uses_fresh_snapshot(self):
        source = PANEL.read_text(encoding="utf-8")
        self.assertIn("REHAB_APP_BLE_STATUS_STALE_MS", source)
        self.assertIn("rehab_wifi_panel_ble_connected()", source)
        self.assertIn("蓝牙%s", source)
        self.assertIn('ble_connected ? "已连接" : "未连接"', source)

    def test_public_api_does_not_expose_lvgl_objects(self):
        header = PANEL_HEADER.read_text(encoding="utf-8")
        self.assertIn(
            "void rehab_wifi_panel_note_ble_status(rt_bool_t connected, rt_uint32_t link_seq);",
            header,
        )
        self.assertNotIn("lv_obj_t", header)


if __name__ == "__main__":
    unittest.main()
