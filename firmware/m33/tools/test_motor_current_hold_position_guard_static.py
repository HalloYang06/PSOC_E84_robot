from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "applications" / "control" / "control_layer.c"


def test_current_hold_checks_position_before_start_and_refresh() -> None:
    source = CONTROL.read_text(encoding="utf-8")

    assert "ctrl_motor_current_hold_position_safe" in source
    assert source.count("ctrl_motor_current_hold_position_safe(") >= 3
    assert "CONTROL_REHAB_ASSIST_JOINT5_HARD_MIN_RAW_RAD" in source
    assert "CONTROL_REHAB_ASSIST_JOINT5_HARD_MAX_RAW_RAD" in source
    assert "current_hold reject position" in source
    assert "current_hold position guard" in source


if __name__ == "__main__":
    test_current_hold_checks_position_before_start_and_refresh()
    print("motor_current_hold_position_guard_static PASS")
