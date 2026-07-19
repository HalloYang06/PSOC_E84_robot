import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER_C = ROOT / "applications" / "m33" / "app_ble_worker.c"
WORKER_H = ROOT / "applications" / "m33" / "app_ble_worker.h"
GATT_C = ROOT / "applications" / "m33" / "bt_app_gatt_handler.c"
SERVICE_C = ROOT / "applications" / "m33" / "app_ble_service.c"
GATE_C = ROOT / "applications" / "m33" / "bt_runtime_gate.c"


def read(path):
    return path.read_text(encoding="utf-8")


def function_body(source, name):
    match = re.search(rf"\b{name}\s*\([^;]*?\)\s*\{{", source, re.S)
    if not match:
        raise AssertionError(f"missing function: {name}")
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {name}")


def production_worker_source():
    source = read(WORKER_C)
    host_block = source.index("#ifdef APP_BLE_WORKER_HOST_TEST")
    return source[source.index("#else", host_block) :]


class M33BleWorkerStaticTest(unittest.TestCase):
    def test_fixed_resources_and_no_heap(self):
        header = read(WORKER_H)
        source = read(WORKER_C)
        self.assertRegex(header, r"APP_BLE_RX_FRAGMENT_MAX\s+244U")
        self.assertRegex(header, r"APP_BLE_RX_QUEUE_DEPTH\s+4U")
        self.assertRegex(header, r"APP_BLE_FRAME_MAX\s+256U")
        self.assertRegex(header, r"APP_BLE_PARTIAL_TIMEOUT_MS\s+500U")
        self.assertRegex(header, r"APP_BLE_WORKER_STACK_SIZE\s+2048U")
        self.assertRegex(header, r"APP_BLE_WORKER_PRIORITY\s+22U")
        self.assertNotRegex(source, r"\b(?:rt_)?(?:m|c|re)alloc\s*\(")
        self.assertIn("APP_BLE_RX_QUEUE_DEPTH", source)
        self.assertIn("APP_BLE_WORKER_STACK_SIZE", source)

    def test_enqueue_is_nonblocking_and_does_not_overwrite(self):
        source = production_worker_source()
        body = function_body(source, "app_ble_worker_enqueue")
        self.assertIn("rt_mq_send", body)
        self.assertNotIn("rt_mq_send_wait", body)
        self.assertNotIn("rt_mq_urgent", body)
        self.assertNotIn("rt_mq_control", body)
        self.assertIn("app_ble_diag_note_rx_drop", body)
        self.assertIn("app_ble_diag_note_rx_queue_depth", body)

    def test_recv_uses_actual_message_length(self):
        source = production_worker_source()
        body = function_body(source, "app_ble_worker_entry")
        self.assertRegex(body, r"recv_len\s*=\s*rt_mq_recv\s*\(")
        self.assertRegex(body, r"recv_len\s*>\s*0")
        self.assertNotRegex(body, r"recv_len\s*!=\s*RT_EOK")
        sync_at = body.index("app_ble_reassembly_sync_generation", body.index("recv_len > 0"))
        feed_at = body.index("app_ble_reassembly_feed")
        self.assertLess(sync_at, feed_at)

    def test_begin_session_clears_queue_before_publishing_generation(self):
        source = production_worker_source()
        body = function_body(source, "app_ble_worker_begin_session")
        reset_at = body.index("rt_mq_control")
        busy_at = body.index("g_app_ble_notify_busy")
        publish_at = body.index("g_app_ble_generation =")
        self.assertLess(reset_at, publish_at)
        self.assertLess(busy_at, publish_at)

    def test_gatt_rx_callback_only_validates_and_enqueues(self):
        source = read(GATT_C)
        body = function_body(source, "app_bt_gatt_req_write_handler")
        self.assertIn("app_ble_service_enqueue_rx", body)
        enqueue_at = body.index("app_ble_service_enqueue_rx")
        generic_write_at = body.index("app_bt_set_value")
        self.assertLess(enqueue_at, generic_write_at)
        for forbidden in (
            "app_ble_service_parse_ascii_frame",
            "app_ble_service_submit_command",
            "sscanf",
            "rt_mutex_take",
            "app_bt_nus_notify",
        ):
            self.assertNotIn(forbidden, body)
        set_value_body = function_body(source, "app_bt_set_value")
        self.assertNotIn("app_ble_service_parse_ascii_frame", set_value_body)
        self.assertNotIn("app_ble_service_submit_command", set_value_body)
        self.assertNotIn("memcpy(app_nus_rx", set_value_body)
        reject_at = set_value_body.index("attr_handle == HDLC_NUS_RX_VALUE")
        attribute_copy_at = set_value_body.index("memcpy(p_attr->p_data")
        self.assertLess(reject_at, attribute_copy_at)

    def test_disconnect_resets_worker_session(self):
        source = read(GATT_C)
        body = function_body(source, "app_bt_gatt_connection_down")
        self.assertIn("app_ble_service_reset_rx_session", body)

    def test_generation_is_rechecked_around_strict_protocol_parse(self):
        source = production_worker_source()
        body = function_body(source, "app_ble_worker_handle_frame")
        checks = [match.start() for match in re.finditer("app_ble_worker_session_is_current", body)]
        self.assertGreaterEqual(len(checks), 2)
        parse_at = body.index("app_ble_protocol_parse")
        self.assertLess(checks[0], parse_at)
        self.assertLess(parse_at, checks[1])
        self.assertNotIn("app_ble_service_parse_ascii_frame", body)
        self.assertNotIn("app_ble_service_submit_rx_command", body)
        self.assertNotIn("ascii_frame", body)

    def test_worker_does_not_send_task10_notifications(self):
        source = production_worker_source()
        self.assertNotIn("app_bt_nus_notify", source)
        self.assertIn("bt_app_gatt_notify_from_worker", source)

    def test_only_worker_reaches_bounded_notification_primitive(self):
        source = read(GATT_C)
        notify = function_body(source, "bt_app_gatt_notify_from_worker")
        checks = [match.start() for match in re.finditer(
            "app_ble_worker_session_is_current", notify)]
        self.assertGreaterEqual(len(checks), 2)
        self.assertGreater(checks[-1], notify.index("rt_memcpy"))
        self.assertLess(checks[-1], notify.index(
            "wiced_bt_gatt_server_send_notification"))
        self.assertIn("GATT_CLIENT_CONFIG_NOTIFICATION", notify)
        self.assertRegex(notify, r"peer_mtu\s*-\s*3u")
        self.assertIn("wiced_bt_gatt_server_send_notification", notify)

        for name in (
            "bt_app_gatt_send",
            "app_bt_send_message",
            "app_bt_gatt_increment_notify_value",
        ):
            body = function_body(source, name)
            self.assertNotIn("wiced_bt_gatt_server_send_notification", body)
            self.assertNotIn("app_bt_nus_notify", body)

    def test_tx_uses_static_ack_queue_and_coalesced_telemetry_slot(self):
        header = read(WORKER_H)
        source = production_worker_source()
        self.assertRegex(header, r"APP_BLE_TX_ACK_QUEUE_DEPTH\s+4U")
        self.assertRegex(header, r"APP_BLE_TX_PAYLOAD_MAX\s+244U")
        self.assertIn("APP_BLE_TX_ACK_QUEUE_DEPTH", source)
        self.assertIn("g_app_ble_telemetry_pending", source)
        self.assertIn("g_app_ble_notify_busy", source)
        self.assertNotRegex(source, r"\b(?:rt_)?(?:m|c|re)alloc\s*\(")

        ack = function_body(source, "app_ble_worker_enqueue_ack")
        telemetry = function_body(source, "app_ble_worker_publish_telemetry")
        self.assertIn("app_ble_session_token_t", header)
        self.assertRegex(
            header,
            r"app_ble_worker_enqueue_ack\(const app_ble_session_token_t \*token",
        )
        self.assertRegex(
            header,
            r"app_ble_worker_publish_telemetry\(const app_ble_session_token_t \*token",
        )
        self.assertNotIn("message->generation = g_app_ble_generation", source)
        self.assertIn("rt_mq_send", ack)
        self.assertNotIn("rt_mq_urgent", ack)
        self.assertIn("rt_enter_critical", ack)
        self.assertIn("rt_exit_critical", ack)
        self.assertLess(ack.index("rt_enter_critical"), ack.index("rt_mq_send"))
        self.assertLess(ack.index("rt_mq_send"), ack.rindex("rt_exit_critical"))
        self.assertIn("g_app_ble_telemetry_pending", telemetry)
        self.assertIn("rt_enter_critical", telemetry)
        self.assertNotIn("rt_mutex_take", telemetry)

    def test_session_handover_serializes_ack_reset_with_enqueue(self):
        source = production_worker_source()
        begin = function_body(source, "app_ble_worker_begin_session")
        reset = function_body(source, "app_ble_worker_reset_session")
        for body in (begin, reset):
            self.assertIn("rt_enter_critical", body)
            self.assertIn("rt_exit_critical", body)
            self.assertLess(body.index("rt_enter_critical"),
                            body.index("g_app_ble_tx_ack_mq"))
            self.assertLess(body.index("g_app_ble_tx_ack_mq"),
                            body.rindex("rt_exit_critical"))

    def test_persistent_notify_buffer_is_completion_gated(self):
        worker = production_worker_source()
        gatt = read(GATT_C)
        drain = function_body(worker, "app_ble_worker_drain_tx")
        callback = function_body(gatt, "app_bt_gatt_callback")
        self.assertIn("app_ble_worker_notify_try_acquire", drain)
        self.assertLess(drain.index("rt_mq_recv"),
                        drain.index("app_ble_worker_notify_try_acquire"))
        req = function_body(gatt, "app_bt_gatt_req_cb")
        self.assertIn("app_ble_worker_notify_abort", drain)
        self.assertIn("app_ble_worker_notify_buffer_returned", callback)
        self.assertIn("app_ble_worker_notify_operation_complete", req)
        self.assertIn("GATT_HANDLE_VALUE_NOTIF", req)
        self.assertIn("HDLC_NUS_TX_VALUE", req)
        self.assertNotIn("app_ble_worker_notify_release", callback)
        self.assertIn("g_app_ble_notify_buffer", gatt)

    def test_service_owns_worker_lifecycle(self):
        source = read(SERVICE_C)
        self.assertIn("app_ble_worker_init()", function_body(source, "app_ble_service_init"))
        self.assertIn("app_ble_worker_start()", function_body(source, "app_ble_service_start"))
        self.assertIn("app_ble_worker_enqueue", function_body(source, "app_ble_service_enqueue_rx"))
        self.assertIn("app_ble_worker_reset_session", function_body(source, "app_ble_service_reset_rx_session"))

    def test_worker_dispatches_only_through_mode_manager(self):
        source = read(WORKER_C)
        self.assertIn('include "rehab_mode_manager.h"', source)
        self.assertIn("rehab_mode_manager_apply_app_command", source)
        for forbidden in (
            "control_layer",
            "rehab_service",
            "ifx_can",
            "Cy_CANFD",
            "rt_device_write",
            "motor_",
        ):
            self.assertNotIn(forbidden, source)

    def test_runtime_gate_has_safe_fallback_when_build_define_is_absent(self):
        source = read(GATE_C)
        self.assertRegex(source, r"#define\s+M33_ENABLE_APP_BLE_RUNTIME\s+0\b")


if __name__ == "__main__":
    unittest.main()
