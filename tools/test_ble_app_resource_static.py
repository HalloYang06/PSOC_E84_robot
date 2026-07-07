from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def require(text, needle, source):
    if needle not in text:
        raise AssertionError(f"{source} missing {needle!r}")


def forbid(text, needle, source):
    if needle in text:
        raise AssertionError(f"{source} must not contain {needle!r}")


def main():
    ble_h = read_text("applications/m33/app_ble_service.h")
    ble_c = read_text("applications/m33/app_ble_service.c")
    gatt_c = read_text("applications/m33/bt_app_gatt_handler.c")
    hci_c = read_text("applications/m33/bt_hci_transport.c")
    post_reset_c = read_text("applications/m33/bt_post_reset.c")
    source_manifest_c = read_text("applications/m33/bt_source_manifest.c")
    main_c = read_text("applications/main.c")
    voice_c = read_text("applications/m33/voice_manager.c")

    for needle in (
        "#define APP_BLE_COMMAND_QUEUE_DEPTH 8U",
        "app_ble_command_t command_queue[APP_BLE_COMMAND_QUEUE_DEPTH]",
        "rt_uint8_t command_head",
        "rt_uint8_t command_tail",
        "rt_uint8_t command_count",
        "rt_uint32_t dropped_commands",
        "rt_uint8_t queued_commands",
    ):
        require(ble_h + ble_c, needle, "app_ble_service queue contract")

    for needle in (
        "if (g_app_ble.command_count >= APP_BLE_COMMAND_QUEUE_DEPTH)",
        "g_app_ble.runtime.dropped_commands++",
        "return -RT_EFULL;",
        "g_app_ble.command_queue[g_app_ble.command_tail] = *cmd;",
        "g_app_ble.command_tail = app_ble_next_queue_index(g_app_ble.command_tail);",
        "g_app_ble.command_count++;",
        "*cmd = g_app_ble.command_queue[g_app_ble.command_head];",
        "g_app_ble.command_head = app_ble_next_queue_index(g_app_ble.command_head);",
        "g_app_ble.command_count--;",
    ):
        require(ble_c, needle, "app_ble_service queue implementation")

    for needle in (
        "app_ble_command_t last_command",
        "rt_bool_t has_command",
    ):
        forbid(ble_c, needle, "app_ble_service queue implementation")

    for needle in (
        "hello_sensor_state.conn_id != 0u",
        "hello_sensor_state.conn_id != p_status->conn_id",
        "rejecting extra BLE connection",
    ):
        require(gatt_c, needle, "bt_app_gatt_handler single central guard")

    for forbidden in (
        "m33_m55_comm_consume",
        "control_move_joint",
        "control_set_mode",
        "voice_manager_start",
    ):
        forbid(ble_c + gatt_c, forbidden, "BLE/GATT layer resource isolation")

    for needle in (
        "#ifndef M33_ENABLE_APP_BLE_LINK",
        "#define M33_ENABLE_APP_BLE_LINK 1",
        "#define M33_ENABLE_BT_HCI M33_ENABLE_APP_BLE_LINK",
        "static void m33_init_ble_app_link(void)",
        "m33_init_ble_app_link();",
        "static void m33_handle_ble_command_minimal(void)",
        "m33_handle_ble_command_minimal();",
    ):
        require(main_c, needle, "main.c BLE app-link minimal framework path")

    require(main_c, "m33_handle_ble_command();", "main.c BLE command pump")
    require(main_c, "m33_publish_ble_telemetry", "main.c BLE telemetry pump")
    require(voice_c, "single owner for the M55 IPC RX queue", "voice_manager IPC ownership guard")
    require(hci_c, '#include "wiced_bt_stack.h"', "bt_hci_transport.c")
    require(post_reset_c, '#include "cybt_platform_util.h"', "bt_post_reset.c")
    forbid(source_manifest_c, "`r`n#include", "bt_source_manifest.c")


if __name__ == "__main__":
    main()
