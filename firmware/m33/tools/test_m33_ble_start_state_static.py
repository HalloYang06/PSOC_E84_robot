import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT_H = (ROOT / "applications" / "m33" / "bt_hci_transport.h").read_text(encoding="utf-8")
TRANSPORT_C = (ROOT / "applications" / "m33" / "bt_hci_transport.c").read_text(encoding="utf-8")
EVENT_C = (ROOT / "applications" / "m33" / "app_bt_event_handler.c").read_text(encoding="utf-8")
GATE_C = (ROOT / "applications" / "m33" / "bt_runtime_gate.c").read_text(encoding="utf-8")


def c_function_body(source, function_name):
    match = re.search(rf"\b{re.escape(function_name)}\s*\([^;]*?\)\s*\{{", source, re.DOTALL)
    if match is None:
        raise AssertionError(f"missing function: {function_name}")

    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:index]
    raise AssertionError(f"unterminated function: {function_name}")


def assert_ready_failed_demotes(refresh_body):
    failed = refresh_body.find("hci.state == BT_HCI_STATE_FAILED")
    starting = refresh_body.find("g_m33_ble_gate_state == M33_BLE_GATE_STARTING", failed)
    ready = refresh_body.find("g_m33_ble_gate_state == M33_BLE_GATE_READY", failed)
    demote = refresh_body.find("g_m33_ble_gate_state = M33_BLE_GATE_FAILED", failed)
    if min(failed, starting, ready, demote) < 0 or not (failed < starting < ready < demote):
        raise AssertionError("READY gate must demote when transport is FAILED")


class M33BleStartStateStaticTest(unittest.TestCase):
    def test_transport_includes_stack_init_declaration(self):
        self.assertIn('#include "wiced_bt_stack.h"', TRANSPORT_C)

    def test_transport_exposes_only_off_starting_ready_failed(self):
        enum = re.search(
            r"typedef\s+enum\s*\{(?P<body>.*?)\}\s*bt_hci_state_t\s*;",
            TRANSPORT_H,
            re.DOTALL,
        )
        self.assertIsNotNone(enum)
        states = re.findall(r"\bBT_HCI_STATE_[A-Z_]+\b", enum.group("body"))
        self.assertEqual(
            states,
            [
                "BT_HCI_STATE_OFF",
                "BT_HCI_STATE_STARTING",
                "BT_HCI_STATE_READY",
                "BT_HCI_STATE_FAILED",
            ],
        )

    def test_runtime_is_copied_through_snapshot_api(self):
        self.assertIn(
            "rt_err_t bt_hci_transport_get_runtime_snapshot(bt_hci_runtime_t *runtime);",
            TRANSPORT_H,
        )
        self.assertNotIn("const bt_hci_runtime_t *bt_hci_transport_get_runtime", TRANSPORT_H)

        snapshot = c_function_body(TRANSPORT_C, "bt_hci_transport_get_runtime_snapshot")
        self.assertIn("rt_hw_interrupt_disable()", snapshot)
        self.assertIn("*runtime = g_bt_hci_runtime", snapshot)
        self.assertIn("rt_hw_interrupt_enable(level)", snapshot)
        self.assertNotIn("rt_mutex", snapshot)

    def test_stack_init_acceptance_remains_starting_until_callback(self):
        start = c_function_body(TRANSPORT_C, "bt_hci_transport_start")
        call = start.index("wiced_bt_stack_init(")
        accepted = start.index("WICED_ALREADY_INITIALIZED", call)
        after_acceptance = start[accepted:]

        self.assertIn("BT_HCI_STATE_STARTING", start[:call])
        self.assertNotIn("BT_HCI_STATE_READY", after_acceptance)
        self.assertNotIn("g_bt_stack_started", TRANSPORT_C)

    def test_enabled_callback_is_the_only_readiness_reporter(self):
        report = c_function_body(TRANSPORT_C, "bt_hci_transport_report_enabled")
        self.assertIn("status == RT_EOK", report)
        self.assertIn("BT_HCI_STATE_READY", report)
        self.assertIn("BT_HCI_STATE_FAILED", report)
        self.assertNotIn("rt_mutex", report)
        self.assertIn("g_bt_hci_runtime.state == BT_HCI_STATE_STARTING", report)
        self.assertIn("rt_hw_interrupt_disable()", report)
        self.assertIn("rt_hw_interrupt_enable(level)", report)
        self.assertNotIn("bt_hci_transport_set_runtime(", report)
        update = c_function_body(TRANSPORT_C, "bt_hci_transport_set_runtime")
        self.assertIn("rt_hw_interrupt_disable()", update)
        self.assertIn("rt_hw_interrupt_enable(level)", update)
        self.assertNotIn("rt_mutex", update)

        callback = c_function_body(EVENT_C, "app_bt_management_callback")
        enabled_case = callback[callback.index("case BTM_ENABLED_EVT:"):callback.index("case BTM_DISABLED_EVT:")]
        self.assertIn("bt_hci_transport_report_enabled(", enabled_case)
        self.assertIn("p_event_data->enabled.status == WICED_BT_SUCCESS", enabled_case)
        self.assertLess(
            enabled_case.index("bt_hci_transport_report_enabled("),
            enabled_case.index("app_bt_application_init()"),
        )

        start = c_function_body(TRANSPORT_C, "bt_hci_transport_start")
        init = c_function_body(TRANSPORT_C, "bt_hci_transport_init")
        self.assertNotIn("bt_hci_transport_set_runtime(BT_HCI_STATE_READY", start)
        self.assertNotIn("runtime.state = BT_HCI_STATE_READY", init)

    def test_disabled_event_demotes_an_active_stack_to_failed(self):
        self.assertIn("void bt_hci_transport_report_disabled(void);", TRANSPORT_H)
        report = c_function_body(TRANSPORT_C, "bt_hci_transport_report_disabled")
        self.assertIn("BT_HCI_STATE_STARTING", report)
        self.assertIn("BT_HCI_STATE_READY", report)
        self.assertIn("BT_HCI_STATE_FAILED", report)
        self.assertIn("rt_hw_interrupt_disable()", report)
        self.assertNotIn("rt_mutex", report)

        callback = c_function_body(EVENT_C, "app_bt_management_callback")
        disabled_case = callback[callback.index("case BTM_DISABLED_EVT:"):callback.index("case BTM_PAIRING_IO_CAPABILITIES_BLE_REQUEST_EVT:")]
        self.assertIn("bt_hci_transport_report_disabled()", disabled_case)

    def test_gate_refreshes_async_transport_state(self):
        self.assertIn("#define M33_ENABLE_APP_BLE_RUNTIME 0", GATE_C)
        self.assertIn("M33_BLE_GATE_READY", GATE_C)
        self.assertNotIn("M33_BLE_GATE_RUNNING", GATE_C)

        refresh = c_function_body(GATE_C, "m33_ble_gate_refresh_transport_state")
        self.assertIn("bt_hci_transport_get_runtime_snapshot", refresh)
        self.assertLess(
            refresh.index("rt_mutex_take(&g_m33_ble_gate_lock"),
            refresh.index("bt_hci_transport_get_runtime_snapshot"),
            "transport state must be sampled after owning the gate mutex",
        )
        self.assertIn("BT_HCI_STATE_READY", refresh)
        self.assertIn("M33_BLE_GATE_READY", refresh)
        self.assertIn("BT_HCI_STATE_FAILED", refresh)
        self.assertIn("M33_BLE_GATE_FAILED", refresh)
        assert_ready_failed_demotes(refresh)

        status = c_function_body(GATE_C, "cmd_m33_ble_status")
        self.assertIn("m33_ble_gate_refresh_transport_state()", status)

        start = c_function_body(GATE_C, "m33_ble_gate_start")
        self.assertLess(
            start.index("m33_ble_gate_refresh_transport_state()"),
            start.index("rt_mutex_take(&g_m33_ble_gate_lock"),
            "a repeated start must observe an asynchronous READY/FAILED callback first",
        )
        self.assertNotIn(
            "g_m33_ble_gate_state = (ret == RT_EOK)",
            start,
            "an accepted asynchronous start is not READY",
        )

    def test_ready_failed_mapping_counterexample_is_rejected(self):
        unsafe = """
        if ((hci.state == BT_HCI_STATE_FAILED) &&
            (g_m33_ble_gate_state == M33_BLE_GATE_STARTING))
        {
            g_m33_ble_gate_state = M33_BLE_GATE_FAILED;
        }
        """
        with self.assertRaises(AssertionError):
            assert_ready_failed_demotes(unsafe)

    def test_status_does_not_take_an_uninitialized_gate_mutex(self):
        status = c_function_body(GATE_C, "cmd_m33_ble_status")
        self.assertIn("if (g_m33_ble_gate_lock_ready)", status)
        guard = status.index("if (g_m33_ble_gate_lock_ready)")
        take = status.index("rt_mutex_take(&g_m33_ble_gate_lock")
        fallback = status.index("else", guard)

        self.assertLess(guard, take)
        self.assertLess(take, fallback)
        self.assertIn("gate_state = g_m33_ble_gate_state", status[fallback:])
        self.assertIn("gate_error = g_m33_ble_gate_last_error", status[fallback:])

    def test_failure_path_does_not_delete_vendor_threads(self):
        combined = TRANSPORT_C + EVENT_C + GATE_C
        self.assertNotIn("rt_thread_delete(", combined)
        self.assertNotIn("rt_thread_detach(", combined)


if __name__ == "__main__":
    unittest.main()
