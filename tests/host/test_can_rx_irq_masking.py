from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_SERVICE = ROOT / "app" / "src" / "app_service.c"
CAN_TRANSPORT = ROOT / "app" / "src" / "can_transport.c"


def _extract_function_body(source: str, signature: str) -> str:
    start = source.index(signature)
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

    raise AssertionError(f"function body not closed: {signature}")


def test_rx_pending_irq_is_masked_until_main_loop_drain():
    callback = _extract_function_body(
        APP_SERVICE.read_text(encoding="utf-8"),
        "void HAL_CAN_RxFifo0MsgPendingCallback(CAN_HandleTypeDef *hcan_cb)",
    )
    poll = _extract_function_body(
        CAN_TRANSPORT.read_text(encoding="utf-8"),
        "void can_transport_poll_rx(void)",
    )

    assert "__HAL_CAN_DISABLE_IT" in callback
    assert "CAN_IT_RX_FIFO0_MSG_PENDING" in callback
    assert "__HAL_CAN_ENABLE_IT" in poll
    assert "CAN_IT_RX_FIFO0_MSG_PENDING" in poll


if __name__ == "__main__":
    test_rx_pending_irq_is_masked_until_main_loop_drain()
