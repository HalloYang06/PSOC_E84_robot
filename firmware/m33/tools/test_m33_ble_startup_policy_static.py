from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(text, needle, source):
    if needle not in text:
        raise AssertionError(f"{source} missing {needle!r}")


def forbid(text, needle, source):
    if needle in text:
        raise AssertionError(f"{source} must not contain {needle!r}")


def require_order(text, needles, source):
    cursor = -1
    for needle in needles:
        position = text.find(needle, cursor + 1)
        if position < 0:
            raise AssertionError(f"{source} missing ordered item {needle!r}")
        cursor = position


def main():
    main_c = (ROOT / "applications/main.c").read_text(encoding="utf-8")
    gatt_c = (ROOT / "applications/m33/bt_app_gatt_handler.c").read_text(encoding="utf-8")
    bt_event_c = (ROOT / "applications/m33/app_bt_event_handler.c").read_text(encoding="utf-8")
    ble_service_c = (ROOT / "applications/m33/app_ble_service.c").read_text(encoding="utf-8")
    ble_service_h = (ROOT / "applications/m33/app_ble_service.h").read_text(encoding="utf-8")

    require(main_c, "#define M33_XIAOZHI_MINIMAL_FRAMEWORK 0", "default framework policy")
    require(main_c, "#define M33_ENABLE_BT_HCI 1", "BLE startup policy")

    framework_start = main_c.index("static void m33_init_framework(void)")
    framework_end = main_c.index("#ifdef __cplusplus", framework_start)
    framework = main_c[framework_start:framework_end]
    require_order(
        framework,
        [
            "m33_start_ipc_init_async();",
            "bt_board_bridge_init();",
            "app_ble_service_init();",
            "app_ble_service_start();",
            "m33_start_bt_hci();",
            "return;",
        ],
        "minimal BLE startup",
    )

    main_start = main_c.index("int main(void)")
    minimal_start = main_c.index("#if M33_XIAOZHI_MINIMAL_FRAMEWORK", main_start)
    minimal_end = main_c.index('    rt_kprintf("[m33] framework ok', minimal_start)
    minimal_loop = main_c[minimal_start:minimal_end]
    require(minimal_loop, "g_runtime.loop_count++;", "minimal framework heartbeat")
    require(minimal_loop, "rt_thread_mdelay(FRAME_PERIOD_MS);", "minimal framework pacing")
    forbid(minimal_loop, "m33_handle_ble_command();", "minimal framework loop")
    forbid(minimal_loop, "m33_publish_ble_telemetry", "minimal framework loop")

    hci_start = main_c.index("static void m33_start_bt_hci(void)")
    hci_end = main_c.index("static void m33_init_framework(void)", hci_start)
    hci_startup = main_c[hci_start:hci_end]
    require_order(
        hci_startup,
        [
            "m33_wait_for_m55_runtime_ready()",
            "bt_hci_transport_init();",
            "bt_hci_transport_start();",
        ],
        "M55-ready Bluetooth startup",
    )
    forbid(hci_startup, 'rt_thread_create("bt_start"', "Bluetooth startup context")

    for unsafe_call in (
        "m33_m55_comm_publish(",
        "m33_m55_comm_consume(",
        "control_set_mode(",
        "control_set_joint_target(",
        "control_emergency_stop(",
    ):
        forbid(gatt_c, unsafe_call, "BLE GATT callback boundary")

    forbid(bt_event_c, "{0x00, 0xA0, 0x50, 0x11, 0x44, 0x77}", "BLE identity")
    require(bt_event_c, "Cy_SysLib_GetUniqueId()", "BLE identity")
    require(bt_event_c, "g_local_bda[0] = 0xC0U", "BLE random-static identity")
    require(bt_event_c, "wiced_bt_set_local_bdaddr(g_local_bda, BLE_ADDR_RANDOM)", "BLE identity")

    require(ble_service_h, "#define APP_BLE_COMMAND_QUEUE_DEPTH 8U", "BLE command queue")
    require(ble_service_c, "command_queue[APP_BLE_COMMAND_QUEUE_DEPTH]", "BLE command queue")
    require(ble_service_c, "queue_count >= APP_BLE_COMMAND_QUEUE_DEPTH", "BLE command queue bound")
    forbid(ble_service_c, "app_ble_command_t last_command;", "BLE command queue")
    require(gatt_c, "submit_ret = app_ble_service_submit_command(&cmd);", "BLE queue backpressure")
    require(gatt_c, '"ERR:busy\\n"', "BLE queue backpressure")
    require(gatt_c, '"ERR:readonly\\n"', "BLE readonly motion boundary")
    require(gatt_c, "app_bt_command_is_readonly_safe", "BLE readonly motion boundary")
    require(gatt_c, 'rt_mutex_init(&g_nus_tx_lock, "nustx", RT_IPC_FLAG_PRIO)', "NUS TX serialization")
    require(gatt_c, "bt_app_gatt_send_frame", "NUS TX serialization")
    forbid(gatt_c, "memcpy(app_nus_tx, response", "NUS TX serialization")
    require(gatt_c, "#define M33_BT_GATT_VERBOSE_EVENTS 0", "GATT event log policy")

    worker_start = main_c.index("static void m33_ble_worker_entry(void *parameter)")
    worker_end = main_c.index("static void m33_start_ble_worker(void)", worker_start)
    worker = main_c[worker_start:worker_end]
    require(worker, "app_ble_service_peek_command", "BLE worker")
    require(worker, "m33_publish_ble_telemetry", "BLE worker")
    require(main_c, "bt_app_gatt_send_frame", "BLE telemetry frame serialization")
    require(main_c, "m33_ble_sample_is_fresh", "BLE telemetry freshness")
    for unsafe_call in (
        "control_set_mode(",
        "control_move_joint(",
        "control_motor_enable(",
        "control_motor_position_control(",
    ):
        forbid(worker, unsafe_call, "BLE worker safety boundary")


if __name__ == "__main__":
    main()
