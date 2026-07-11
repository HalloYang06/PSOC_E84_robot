from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(text, needle, source):
    if needle not in text:
        raise AssertionError(f"{source} missing {needle!r}")


def forbid(text, needle, source):
    if needle in text:
        raise AssertionError(f"{source} must not contain {needle!r}")


def main():
    main_c = (ROOT / "applications/main.c").read_text(encoding="utf-8")

    require(main_c, "#define LED_PIN_B GET_PIN(16, 5)", "blue heartbeat pin")
    require(main_c, "#define LED_PIN_R GET_PIN(16, 7)", "red LED pin")
    require(main_c, "rt_pin_mode(LED_PIN_R, PIN_MODE_OUTPUT);", "red LED setup")
    require(main_c, "rt_pin_write(LED_PIN_R, PIN_HIGH);", "red LED inactive state")

    minimal_start = main_c.index("#if M33_XIAOZHI_MINIMAL_FRAMEWORK", main_c.index("int main(void)"))
    minimal_end = main_c.index('rt_kprintf("[m33] framework ok', minimal_start)
    minimal_loop = main_c[minimal_start:minimal_end]
    require(minimal_loop, "g_runtime.loop_count++;", "minimal heartbeat loop")
    require(minimal_loop, "rt_thread_mdelay(FRAME_PERIOD_MS);", "minimal heartbeat loop")
    forbid(minimal_loop, "m33_handle_ble_command", "minimal heartbeat loop")
    forbid(minimal_loop, "m33_publish_ble_telemetry", "minimal heartbeat loop")


if __name__ == "__main__":
    main()
