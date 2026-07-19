import pathlib
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "applications" / "control" / "rehab_intensity_level.c"

HARNESS = r'''
#include <assert.h>
#include <stdint.h>

#include "rehab_intensity_level.h"

int main(void)
{
    assert(rehab_intensity_current_for_level(1U) == 0.5f);
    assert(rehab_intensity_current_for_level(2U) == 1.0f);
    assert(rehab_intensity_current_for_level(3U) == 1.5f);
    assert(rehab_intensity_current_for_level(4U) == 2.0f);
    assert(rehab_intensity_current_for_level(0U) == 0.0f);
    assert(rehab_intensity_current_for_level(5U) == 0.0f);

    assert(rehab_intensity_level_for_current(0.1f) == 1U);
    assert(rehab_intensity_level_for_current(0.5f) == 1U);
    assert(rehab_intensity_level_for_current(0.51f) == 2U);
    assert(rehab_intensity_level_for_current(1.0f) == 2U);
    assert(rehab_intensity_level_for_current(1.01f) == 3U);
    assert(rehab_intensity_level_for_current(1.5f) == 3U);
    assert(rehab_intensity_level_for_current(1.51f) == 4U);
    assert(rehab_intensity_level_for_current(3.0f) == 4U);

    assert(rehab_intensity_adjust_level(1U, -1) == 1U);
    assert(rehab_intensity_adjust_level(1U, 1) == 2U);
    assert(rehab_intensity_adjust_level(3U, 1) == 4U);
    assert(rehab_intensity_adjust_level(4U, 1) == 4U);
    assert(rehab_intensity_adjust_level(4U, -3) == 1U);
    assert(rehab_intensity_adjust_level(0U, 1) == 0U);
    assert(rehab_intensity_adjust_level(5U, -1) == 0U);
    return 0;
}
'''


def test_rehab_intensity_level_mapping():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = pathlib.Path(temp_dir)
        harness = temp / "rehab_intensity_level_test.c"
        executable = temp / "rehab_intensity_level_test.exe"
        harness.write_text(HARNESS, encoding="ascii")
        result = subprocess.run(
            [
                "gcc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(ROOT / "applications" / "control"),
                str(harness),
                str(SOURCE),
                "-o",
                str(executable),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
