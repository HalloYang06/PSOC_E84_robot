from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CFG = (ROOT / "applications" / "control" / "control_layer_cfg.h").read_text(
    encoding="utf-8"
)
SOURCE = (ROOT / "applications" / "control" / "rehab_resist_strategy.c").read_text(
    encoding="utf-8"
)
HEADER = (ROOT / "applications" / "control" / "rehab_resist_strategy.h").read_text(
    encoding="utf-8"
)
ASSIST_SOURCE = (
    ROOT / "applications" / "control" / "rehab_assist_strategy.c"
).read_text(encoding="utf-8")
STRATEGY_H = (ROOT / "applications" / "control" / "rehab_strategy.h").read_text(
    encoding="utf-8"
)


class RehabResistSlewStaticTest(unittest.TestCase):
    def test_resist_current_has_bounded_slew(self):
        self.assertIn(
            "#define CONTROL_REHAB_RESIST_SLEW_A_PER_STEP (0.03f)", CFG
        )
        self.assertIn("float last_current_a;", HEADER)
        self.assertIn("state->last_current_a = 0.0f;", SOURCE)
        self.assertIn("static float rehab_resist_strategy_slew", SOURCE)

        target = SOURCE.index("out->current_a = -params->resist_direction")
        slew = SOURCE.index("out->current_a = rehab_resist_strategy_slew", target)
        store = SOURCE.index("state->last_current_a = out->current_a", slew)
        self.assertLess(target, slew)
        self.assertLess(slew, store)
        self.assertIn("CONTROL_REHAB_RESIST_SLEW_A_PER_STEP", SOURCE[slew:store])

    def test_slew_never_leaves_output_above_new_limit(self):
        self.assertIn("static inline float rehab_strategy_clampf", STRATEGY_H)

        resist_slew = SOURCE.index("out->current_a = rehab_resist_strategy_slew")
        resist_cap = SOURCE.index(
            "out->current_a = rehab_strategy_clampf", resist_slew
        )
        resist_store = SOURCE.index("state->last_current_a = out->current_a", resist_cap)
        self.assertLess(resist_slew, resist_cap)
        self.assertLess(resist_cap, resist_store)

        assist_slew = ASSIST_SOURCE.index("out->current_a = rehab_assist_strategy_slew")
        assist_cap = ASSIST_SOURCE.index(
            "out->current_a = rehab_strategy_clampf", assist_slew
        )
        assist_store = ASSIST_SOURCE.index(
            "state->last_current_a = out->current_a", assist_cap
        )
        self.assertLess(assist_slew, assist_cap)
        self.assertLess(assist_cap, assist_store)


if __name__ == "__main__":
    unittest.main()
