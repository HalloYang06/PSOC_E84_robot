from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GATT_C = (ROOT / "applications" / "m33" / "bt_app_gatt_handler.c").read_text(encoding="utf-8")
SERVICE_C = (ROOT / "applications" / "m33" / "app_ble_service.c").read_text(encoding="utf-8")
SERVICE_H = (ROOT / "applications" / "m33" / "app_ble_service.h").read_text(encoding="utf-8")
GATE_C = (ROOT / "applications" / "m33" / "bt_runtime_gate.c").read_text(encoding="utf-8")


def body(signature, next_signature):
    start = GATT_C.index(signature)
    return GATT_C[start:GATT_C.index(next_signature, start)]


class M33BleGattBoundsStaticTest(unittest.TestCase):
    def test_event_callback_checks_pointer_before_member_access(self):
        callback = body("wiced_bt_gatt_status_t app_bt_gatt_callback", "wiced_bt_gatt_status_t app_bt_gatt_req_cb")
        self.assertLess(callback.index("p_event_data == RT_NULL"), callback.index("p_event_data->attribute_request"))

    def test_write_rejects_null_payload_and_nonzero_offset(self):
        write = body("wiced_bt_gatt_status_t app_bt_gatt_req_write_handler", "wiced_bt_gatt_status_t app_bt_gatt_req_read_by_type_handler")
        self.assertIn("p_write_req == RT_NULL", write)
        self.assertIn("p_write_req->p_val == RT_NULL", write)
        self.assertIn("p_write_req->offset != 0u", write)
        self.assertIn("WICED_BT_GATT_INVALID_OFFSET", write)

    def test_cccd_length_is_checked_before_copy(self):
        setter = body("wiced_bt_gatt_status_t app_bt_set_value", "void app_bt_free_buffer")
        self.assertLess(setter.index("HDLD_NUS_TX_CLIENT_CHAR_CONFIG"), setter.index("memcpy(p_attr->p_data"))

    def test_response_allocation_failure_is_reported(self):
        callback = body("wiced_bt_gatt_status_t app_bt_gatt_callback", "wiced_bt_gatt_status_t app_bt_gatt_req_cb")
        self.assertIn("WICED_BT_GATT_INSUF_RESOURCE", callback)

    def test_disconnect_clears_existing_gatt_session_state(self):
        disconnect = body("wiced_bt_gatt_status_t app_bt_gatt_connection_down", "gatt_db_lookup_table_t *app_bt_find_by_handle")
        for statement in (
            "hello_sensor_state.conn_id = 0u",
            "hello_sensor_state.peer_mtu = 0u",
            "hello_sensor_state.flag_indication_sent = 0u",
            "hello_sensor_state.num_to_send = 0u",
            "memset(app_nus_tx_client_char_config, 0, app_nus_tx_client_char_config_len)",
            "memset(app_nus_rx, 0, MAX_LEN_NUS_RX)",
            "app_nus_rx_len = 0u",
            "memset(app_nus_tx, 0, MAX_LEN_NUS_TX)",
            "app_nus_tx_len = 0u",
        ):
            self.assertIn(statement, disconnect)
        self.assertIn("p_attr = app_bt_find_by_handle(HDLC_NUS_RX_VALUE)", disconnect)
        self.assertIn("p_attr = app_bt_find_by_handle(HDLC_NUS_TX_VALUE)", disconnect)
        self.assertGreaterEqual(disconnect.count("p_attr->cur_len = 0u"), 2)

    def test_disconnect_drops_pending_service_command(self):
        setter_start = SERVICE_C.index("rt_err_t app_ble_service_set_link_state")
        setter_end = SERVICE_C.index("rt_err_t app_ble_service_parse_ascii_frame", setter_start)
        setter = SERVICE_C[setter_start:setter_end]
        self.assertIn("if (!connected)", setter)
        self.assertIn("g_app_ble.has_command = RT_FALSE", setter)
        self.assertIn("rt_memset(&g_app_ble.last_command, 0, sizeof(g_app_ble.last_command))", setter)

    def test_runtime_is_read_through_locked_snapshot_api(self):
        self.assertIn("app_ble_service_get_runtime_snapshot(app_ble_runtime_t *runtime)", SERVICE_H)
        self.assertNotIn("const app_ble_runtime_t *app_ble_service_get_runtime(void)", SERVICE_H)
        snapshot_start = SERVICE_C.index("rt_err_t app_ble_service_get_runtime_snapshot")
        snapshot = SERVICE_C[snapshot_start:]
        self.assertLess(snapshot.index("!g_app_ble.initialized"), snapshot.index("rt_mutex_take(&g_app_ble.lock"))
        self.assertIn("rt_mutex_take(&g_app_ble.lock", snapshot)
        self.assertIn("*runtime = g_app_ble.runtime", snapshot)
        self.assertIn("rt_mutex_release(&g_app_ble.lock)", snapshot)
        self.assertNotIn("app_ble_service_get_runtime()->", GATT_C)
        self.assertNotIn("const app_ble_runtime_t *ble = app_ble_service_get_runtime()", GATE_C)

    def test_callback_trace_is_compile_time_disabled_but_counted(self):
        self.assertIn("#define M33_APP_BLE_GATT_TRACE 0", GATT_C)
        self.assertIn("#if M33_APP_BLE_GATT_TRACE", GATT_C)
        callback = body("wiced_bt_gatt_status_t app_bt_gatt_callback", "wiced_bt_gatt_status_t app_bt_gatt_req_cb")
        self.assertIn("g_bt_app_gatt_event_count++", callback)
        self.assertIn("app_ble_diag_note_gatt_event()", callback)
        self.assertNotIn("rt_kprintf(", callback)
        request = body("wiced_bt_gatt_status_t app_bt_gatt_req_cb", "wiced_bt_gatt_status_t app_bt_gatt_conn_status_cb")
        setter = body("wiced_bt_gatt_status_t app_bt_set_value", "void app_bt_free_buffer")
        self.assertNotIn("rt_kprintf(", request)
        self.assertNotIn("rt_kprintf(", setter)


if __name__ == "__main__":
    unittest.main()
