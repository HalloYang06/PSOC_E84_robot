from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "applications" / "control" / "control_layer_cfg.h"
SERVICE = ROOT / "applications" / "control" / "rehab_service.c"


def test_control_velocity_and_hard_trip_are_separate() -> None:
    cfg = CFG.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")

    assert "CONTROL_REHAB_ASSIST_OVERSPEED_TRIP_RAD_S" in cfg
    assert "#define CONTROL_REHAB_ASSIST_OVERSPEED_TRIP_RAD_S (2.0f)" in cfg
    assert (
        "rehab_assist_overspeed(&fb, "
        "CONTROL_REHAB_ASSIST_OVERSPEED_TRIP_RAD_S)" in service
    )


if __name__ == "__main__":
    test_control_velocity_and_hard_trip_are_separate()
    print("rehab_assist_overspeed_config_static PASS")
