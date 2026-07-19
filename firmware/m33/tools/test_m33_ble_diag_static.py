import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAG_H = ROOT / "applications" / "m33" / "app_ble_diag.h"
DIAG_C = ROOT / "applications" / "m33" / "app_ble_diag.c"
RUNTIME_GATE_C = ROOT / "applications" / "m33" / "bt_runtime_gate.c"
HCI_PORT_C = ROOT / "applications" / "m33" / "bt_hci_uart_platform_port.c"
HCI_RX_TASK_C = ROOT / "applications" / "m33" / "bt_hci_uart_rx_task.c"
HCI_TX_TASK_C = ROOT / "applications" / "m33" / "bt_hci_uart_tx_task.c"


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


def assert_no_live_hci_snapshot_access(source):
    snapshot = c_function_body(source, "app_ble_diag_snapshot")
    forbidden = (
        "cybt_platform_task_get_queue_utilization",
        "cybt_platform_task_get_tx_heap_utilization",
        "cybt_task[",
    )
    for token in forbidden:
        if token in snapshot:
            raise AssertionError(f"snapshot performs live HCI access: {token}")


class M33BleDiagStaticTest(unittest.TestCase):
    def test_bounded_snapshot_api_exists(self):
        header = DIAG_H.read_text(encoding="utf-8")

        self.assertIn("app_ble_diag_snapshot_t", header)
        for field in (
            "gatt_events",
            "rx_drops",
            "rx_queue_peak",
            "tx_queue_peak",
            "notify_failures",
            "hci_rx_queue_last_percent",
            "hci_tx_queue_last_percent",
            "hci_rx_queue_sampled_peak_percent",
            "hci_tx_queue_sampled_peak_percent",
            "hci_rx_queue_sample_available",
            "hci_tx_queue_sample_available",
            "heap_free_bytes",
            "heap_min_free_bytes",
            "hci_tx_largest_free_bytes",
        ):
            self.assertRegex(header, rf"rt_uint32_t\s+{field}\s*;")
        self.assertIn("void app_ble_diag_snapshot(app_ble_diag_snapshot_t *out);", header)

    def test_shell_snapshot_uses_public_runtime_metrics(self):
        source = DIAG_C.read_text(encoding="utf-8")

        self.assertIn("rt_memory_info(", source)
        assert_no_live_hci_snapshot_access(source)
        self.assertIn("MSH_CMD_EXPORT_ALIAS(cmd_m33_ble_diag, m33_ble_diag", source)
        self.assertIn("BLE_DIAG_STACK_HIGH", source)
        self.assertIn("tx_heap_source=unsupported", source)
        self.assertIn("largest_free=unsupported", source)
        self.assertIn("rehab_svc", source)
        self.assertIn("tshell", source)

    def test_live_hci_snapshot_access_counterexamples_are_rejected(self):
        template = "void app_ble_diag_snapshot(void *out) {{ %s; }}"

        for unsafe in (
            "cybt_platform_task_get_queue_utilization(0)",
            "cybt_platform_task_get_tx_heap_utilization(0)",
            "out = cybt_task[0]",
        ):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(AssertionError):
                    assert_no_live_hci_snapshot_access(template % unsafe)

    def test_hci_cache_hook_is_wired_without_owner_polling(self):
        diag_source = DIAG_C.read_text(encoding="utf-8")
        source = HCI_PORT_C.read_text(encoding="utf-8")

        self.assertIn('#include "app_ble_diag.h"', source)
        self.assertIn("app_ble_diag_note_hci_queue_percent(task_id", source)
        self.assertIn("percent == CYBT_INVALID_QUEUE_UTILIZATION", diag_source)

        rx_source = HCI_RX_TASK_C.read_text(encoding="utf-8")
        rx_body = c_function_body(rx_source, "cybt_hci_rx_task")
        self.assertNotIn("cybt_platform_task_get_queue_utilization", rx_body)
        self.assertNotIn("HCI_RX_DIAG_SAMPLE_INTERVAL", rx_source)

        tx_source = HCI_TX_TASK_C.read_text(encoding="utf-8")
        tx_body = c_function_body(tx_source, "cybt_hci_tx_task")
        self.assertNotIn("cybt_platform_task_get_queue_utilization", tx_body)
        self.assertNotIn("HCI_TX_DIAG_SAMPLE_INTERVAL", tx_source)

    def test_named_stack_scan_is_lifecycle_protected(self):
        source = DIAG_C.read_text(encoding="utf-8")
        named = c_function_body(source, "app_ble_diag_named_stack_snapshot")
        shell = c_function_body(source, "app_ble_diag_shell_stack_snapshot")

        self.assertLess(named.index("rt_enter_critical()"), named.index("rt_thread_find("))
        self.assertLess(named.index("rt_thread_find("), named.index("app_ble_diag_stack_snapshot_locked("))
        self.assertLess(named.index("app_ble_diag_stack_snapshot_locked("), named.index("rt_exit_critical()"))
        self.assertNotIn("cybt_task[", source)
        self.assertLess(shell.index("rt_enter_critical()"), shell.index("rt_thread_self()"))
        self.assertLess(shell.index("rt_thread_self()"), shell.index("rt_exit_critical()"))

        snapshot = c_function_body(source, "app_ble_diag_snapshot")
        # RT_NAME_MAX is 8: these are comparison keys, not NUL-terminated display names.
        self.assertIn('app_ble_diag_named_stack_snapshot("rehab_sv")', snapshot)
        self.assertIn('app_ble_diag_named_stack_snapshot("ble_work")', snapshot)

    def test_runtime_remains_default_off_and_only_registers_diagnostics(self):
        source = RUNTIME_GATE_C.read_text(encoding="utf-8")

        self.assertRegex(
            source,
            re.compile(
                r"#ifndef\s+M33_ENABLE_APP_BLE_RUNTIME\s*\n"
                r"#define\s+M33_ENABLE_APP_BLE_RUNTIME\s+0",
                re.MULTILINE,
            ),
        )
        self.assertNotIn("m33_ble_gate_start();\nINIT_", source)


if __name__ == "__main__":
    unittest.main()
