from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVICE_H = (ROOT / "applications" / "control" / "rehab_service.h").read_text(
    encoding="utf-8"
)
SERVICE_C = (ROOT / "applications" / "control" / "rehab_service.c").read_text(
    encoding="utf-8"
)
SHELL_C = (ROOT / "applications" / "control" / "rehab_shell.c").read_text(
    encoding="utf-8"
)


class RehabIntensityServiceStaticTest(unittest.TestCase):
    def test_service_exposes_owned_intensity_level_updates(self):
        self.assertIn('#include "rehab_intensity_level.h"', SERVICE_C)
        self.assertIn("rehab_service_get_intensity_level", SERVICE_H)
        self.assertIn("rehab_service_set_intensity_level", SERVICE_H)
        self.assertIn("rehab_service_adjust_intensity_level", SERVICE_H)

        start = SERVICE_C.index("rt_err_t rehab_service_set_intensity_level")
        end = SERVICE_C.index("rt_err_t rehab_service_adjust_intensity_level", start)
        set_body = SERVICE_C[start:end]
        self.assertIn("rehab_service_intensity_owner_check_locked", set_body)
        self.assertIn("rehab_intensity_current_for_level", set_body)
        self.assertIn("s_rehab.params.assist_max_current_a", set_body)
        self.assertIn("s_rehab.params.assist_min_current_a = selected_current", set_body)
        self.assertIn("s_rehab.params.resist_max_current_a", set_body)
        self.assertNotIn("rehab_service_reset_all_strategy_states_locked", set_body)

        adjust_start = SERVICE_C.index("rt_err_t rehab_service_adjust_intensity_level")
        adjust_end = SERVICE_C.index("rt_err_t rehab_service_get_params", adjust_start)
        adjust_body = SERVICE_C[adjust_start:adjust_end]
        self.assertIn("s_rehab.params.assist_min_current_a = selected_current", adjust_body)

        owner_start = SERVICE_C.index(
            "static rt_err_t rehab_service_intensity_owner_check_locked"
        )
        owner_end = SERVICE_C.index(
            "rt_err_t rehab_service_get_intensity_level", owner_start
        )
        owner_body = SERVICE_C[owner_start:owner_end]
        self.assertIn("s_rehab.status.mode == REHAB_DEMO_MODE_PASSIVE", owner_body)
        self.assertIn("source == REHAB_CMD_SOURCE_BENCH_MSH", owner_body)
        self.assertIn("s_rehab.status.mode != mode", owner_body)
        self.assertIn("s_rehab.status.source != source", owner_body)

    def test_shell_supports_query_set_up_and_down(self):
        self.assertIn('strcmp(argv[1], "level") == 0', SHELL_C)
        self.assertIn('strcmp(argv[3], "up") == 0', SHELL_C)
        self.assertIn('strcmp(argv[3], "down") == 0', SHELL_C)
        self.assertIn("rehab_service_set_intensity_level", SHELL_C)
        self.assertIn("rehab_service_adjust_intensity_level", SHELL_C)
        self.assertIn("rehab level mode=%s level=%u current_x1000=%d ret=%d", SHELL_C)


if __name__ == "__main__":
    unittest.main()
