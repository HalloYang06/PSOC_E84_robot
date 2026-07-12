from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_SERVICE = ROOT / "app" / "src" / "app_service.c"


def _extract_function_body(source: str, name: str) -> str:
    marker = f"void {name}(void)"
    start = source.index(marker)
    open_brace = source.index("{", start)
    depth = 0

    for index in range(open_brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace + 1:index]

    raise AssertionError(f"function body not closed: {name}")


def test_can_rx_is_polled_before_queue_events():
    body = _extract_function_body(APP_SERVICE.read_text(encoding="utf-8"), "app_service_run_once")

    poll_index = body.index("can_transport_poll_rx()")
    pop_index = body.index("event_queue_pop")

    assert poll_index < pop_index


if __name__ == "__main__":
    test_can_rx_is_polled_before_queue_events()
