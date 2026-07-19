from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "applications" / "control" / "rehab_service.h"
SERVICE = ROOT / "applications" / "control" / "rehab_service.c"
SHELL = ROOT / "applications" / "control" / "rehab_shell.c"


def test_overspeed_fault_latches_trigger_velocity() -> None:
    header = HEADER.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    shell = SHELL.read_text(encoding="utf-8")

    assert "last_fault_velocity_rad_s" in header
    assert "s_rehab.status.last_fault_velocity_rad_s = fault_velocity_rad_s" in service
    assert "fault_vel_x1000" in shell


if __name__ == "__main__":
    test_overspeed_fault_latches_trigger_velocity()
    print("rehab_overspeed_diag_static PASS")
