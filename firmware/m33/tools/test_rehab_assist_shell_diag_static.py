from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "applications" / "control" / "rehab_shell.c"


def test_assist_direction_and_minimum_current_are_visible() -> None:
    source = SHELL.read_text(encoding="utf-8")

    assert "assist_dir_x1000" in source
    assert "assist_min_x1000" in source
    assert "params.assist_direction" in source
    assert "params.assist_min_current_a" in source


if __name__ == "__main__":
    test_assist_direction_and_minimum_current_are_visible()
    print("rehab_assist_shell_diag_static PASS")
