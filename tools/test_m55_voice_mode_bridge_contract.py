from pathlib import Path
import unittest


M33_ROOT = Path(__file__).resolve().parents[1]
APP_M33 = M33_ROOT / "applications" / "m33"


class M55VoiceModeBridgeContractTest(unittest.TestCase):
    def test_asr_text_is_routed_to_voice_mode_bridge(self):
        bridge = APP_M33 / "m55_model_bridge.c"
        self.assertTrue(bridge.exists(), f"missing M55 model bridge: {bridge}")
        text = bridge.read_text(encoding="utf-8")

        self.assertIn('#include "m55_voice_mode_bridge.h"', text)
        self.assertIn("case MSG_TYPE_ASR_TEXT:", text)
        self.assertIn("m55_voice_mode_bridge_handle_text(msg->payload.text.text)", text)

    def test_voice_mode_bridge_uses_whitelist_and_m33_control_owner(self):
        source = APP_M33 / "m55_voice_mode_bridge.c"
        header = APP_M33 / "m55_voice_mode_bridge.h"
        self.assertTrue(source.exists(), f"missing voice mode bridge source: {source}")
        self.assertTrue(header.exists(), f"missing voice mode bridge header: {header}")
        text = source.read_text(encoding="utf-8")

        required = [
            '#include "control_manager.h"',
            "control_set_mode",
            "CONTROL_MODE_PASSIVE",
            "CONTROL_MODE_ACTIVE",
            "CONTROL_MODE_MEMORY",
            "CONTROL_MODE_ASSIST",
            "m55_voice_mode_bridge_parse",
            "m55_voice_mode_bridge_handle_text",
            "切换",
            "进入",
            "被动",
            "主动",
            "记忆",
            "助力",
        ]
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)

        self.assertNotIn("control_move_joint", text)
        self.assertNotIn("motor_", text.lower())

    def test_voice_mode_bridge_rejects_question_like_text(self):
        source = APP_M33 / "m55_voice_mode_bridge.c"
        self.assertTrue(source.exists(), f"missing voice mode bridge source: {source}")
        text = source.read_text(encoding="utf-8")

        for fragment in ["什么", "怎么", "?"]:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)


if __name__ == "__main__":
    unittest.main()
