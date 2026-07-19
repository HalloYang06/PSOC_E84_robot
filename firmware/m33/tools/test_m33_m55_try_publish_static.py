from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_try_publish_is_strictly_nonblocking_and_ordered() -> None:
    header = (ROOT / "applications" / "common" / "m33_m55_comm.h").read_text(
        encoding="utf-8"
    )
    source = (ROOT / "applications" / "common" / "m33_m55_comm.c").read_text(
        encoding="utf-8"
    )

    assert "rt_err_t m33_m55_comm_try_publish(const m33_m55_message_t *msg);" in header
    start = source.index("rt_err_t m33_m55_comm_try_publish(")
    end = source.index("rt_err_t m33_m55_comm_publish(", start)
    body = source[start:end]

    assert "msg == RT_NULL" in body
    assert "!g_comm_runtime.initialized" in body
    assert body.count("return -RT_EBUSY;") >= 2
    assert "rt_mutex_take(&g_comm_runtime.lock, RT_WAITING_NO)" in body
    assert "mtb_ipc_queue_put(&g_comm_runtime.tx_queue, &local, 0)" in body
    assert body.index("mtb_ipc_queue_put") < body.index("rt_mutex_release")

    assert "RT_WAITING_FOREVER" not in body
    assert "m33_m55_comm_init" not in body
    assert "runtime_prepare" not in body
    assert "try_attach" not in body


if __name__ == "__main__":
    test_try_publish_is_strictly_nonblocking_and_ordered()
