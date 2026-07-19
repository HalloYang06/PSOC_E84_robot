from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "applications" / "main.c"
GATT = ROOT / "applications" / "m33" / "bt_app_gatt_handler.c"


class M33BleStatusIpcPublishStaticTest(unittest.TestCase):
    def test_status_is_published_by_existing_ipc_pump(self):
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn('#include "m33/app_ble_service.h"', source)
        self.assertIn("static void m33_publish_app_ble_status(void)", source)
        self.assertIn("app_ble_service_get_runtime_snapshot", source)
        self.assertIn("MSG_TYPE_APP_BLE_STATUS", source)
        self.assertIn("APP_BLE_STATUS_PROTOCOL_VERSION", source)
        self.assertIn("m33_m55_comm_try_publish(&msg)", source)

        pump = source[source.index("static void m33_ipc_pump_entry(") :]
        pump = pump[: pump.index("static void m33_start_ipc_pump(")]
        self.assertIn("m33_publish_app_ble_status();", pump)

    def test_gatt_callback_does_not_publish_ipc(self):
        source = GATT.read_text(encoding="utf-8")
        self.assertNotIn("m33_m55_comm_publish", source)
        self.assertNotIn("m33_m55_comm_try_publish", source)


if __name__ == "__main__":
    unittest.main()
