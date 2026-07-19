from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "applications" / "xiaozhi_edge_impulse_wake_backend.cpp"
ENGINE_H = ROOT / "applications" / "xiaozhi_wake_engine.h"
ENGINE_C = ROOT / "applications" / "xiaozhi_wake_engine.c"
MAIN = ROOT / "applications" / "main.c"


def test_cpu_baseline_wraps_only_existing_tflm_invoke():
    text = BACKEND.read_text(encoding="utf-8")

    invoke = text.index("g_interpreter->Invoke()")
    begin = text.rfind("cpu_baseline_begin", 0, invoke)
    finish = text.index("cpu_baseline_finish", invoke)

    assert begin != -1
    assert begin < invoke < finish
    assert "rt_malloc" not in text[begin:finish]
    assert "mtb_ml_init" not in text[begin:finish]


def test_diag_contract_identifies_cpu_model_and_bounded_counters():
    header = ENGINE_H.read_text(encoding="utf-8")
    backend = BACKEND.read_text(encoding="utf-8")
    engine = ENGINE_C.read_text(encoding="utf-8")

    for field in (
        "invoke_count",
        "fail_count",
        "warmup_count",
        "last_us",
        "min_us",
        "max_us",
        "total_us",
        "timer_resolution_us",
    ):
        assert field in header

    assert '"cpu_tflm"' in engine
    assert '"official_xiaozhi_ei_int8"' in engine
    assert "DWT_CTRL_CYCCNTENA_Msk" in backend
    assert "rt_tick_get()" in backend
    assert "rt_hw_interrupt_disable" in backend
    assert "rt_hw_interrupt_enable" in backend


def test_existing_wake_diag_supports_read_and_explicit_reset():
    text = MAIN.read_text(encoding="utf-8")

    assert "xiaozhi_wake_engine_cpu_diag_get" in text
    assert "xiaozhi_wake_engine_cpu_diag_reset" in text
    assert 'rt_strcmp(argv[1], "reset")' in text
    assert "wake_cpu backend=%s model=%s" in text
    assert "%llu" not in text
    assert "cpu_diag.total_us >> 32" in text
