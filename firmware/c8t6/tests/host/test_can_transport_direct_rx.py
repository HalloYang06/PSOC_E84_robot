from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAN_TRANSPORT = ROOT / "app" / "src" / "can_transport.c"


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


def test_rx_poll_drains_fifo_without_hal_state_gate():
    body = _extract_function_body(CAN_TRANSPORT.read_text(encoding="utf-8"), "can_transport_poll_rx")

    assert "sFIFOMailBox[CAN_RX_FIFO0]" in body
    assert "CAN_RF0R_RFOM0" in body
    assert "HAL_CAN_GetRxMessage" not in body
    assert "HAL_CAN_GetRxFifoFillLevel" not in body


if __name__ == "__main__":
    test_rx_poll_drains_fifo_without_hal_state_gate()
