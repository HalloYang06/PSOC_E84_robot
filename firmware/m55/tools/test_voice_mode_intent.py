import ctypes
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VOICE_SERVICE = (ROOT / "applications" / "voice_service.c").read_text(encoding="utf-8")
SOURCE = ROOT / "applications" / "voice_mode_intent.c"
INCLUDE = ROOT / "applications"


class Request(ctypes.Structure):
    _fields_ = [
        ("mode", ctypes.c_uint32),
        ("action", ctypes.c_uint32),
        ("joint_mask", ctypes.c_uint8),
        ("event_fingerprint", ctypes.c_uint32),
    ]


class VoiceModeIntentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        dll = Path(cls.temp_dir.name) / "voice_mode_intent.dll"
        subprocess.run(
            [
                "gcc",
                "-std=c99",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-fshort-enums",
                "-shared",
                "-I",
                str(INCLUDE),
                str(SOURCE),
                "-o",
                str(dll),
            ],
            check=True,
        )
        cls.lib = ctypes.CDLL(str(dll))
        cls.classify = cls.lib.voice_mode_intent_classify
        cls.classify.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(Request),
        ]
        cls.classify.restype = ctypes.c_bool

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def classify_request(self, source, event_id, payload):
        request = Request(123, 99, 0xFF, 0xA5A5A5A5)
        accepted = self.classify(
            source,
            event_id.encode("utf-8") if event_id is not None else None,
            payload.encode("utf-8") if payload is not None else None,
            ctypes.byref(request),
        )
        return accepted, request

    def test_accepts_exact_protocol_modes_for_joint_group(self):
        cases = [
            ("rehab.set_mode joints=4,5,6 mode=assist", 3),
            ("rehab.set_mode joints=4,5,6 mode=resist", 4),
        ]
        for payload, mode in cases:
            with self.subTest(payload=payload):
                accepted, request = self.classify_request(1, "turn-42", payload)
                self.assertTrue(accepted)
                self.assertEqual(mode, request.mode)
                self.assertEqual(0, request.action)
                self.assertEqual(0x38, request.joint_mask)
                self.assertNotEqual(0, request.event_fingerprint)

    def test_accepts_only_exact_chinese_allowlist_commands(self):
        cases = [
            ("切换助力模式", 3),
            ("切换抗阻模式", 4),
        ]
        for payload, mode in cases:
            with self.subTest(payload=payload):
                accepted, request = self.classify_request(1, "turn-cn", payload)
                self.assertTrue(accepted)
                self.assertEqual(mode, request.mode)
                self.assertEqual(0, request.action)
                self.assertEqual(0x38, request.joint_mask)

    def test_accepts_exact_assist_and_resist_level_adjustments(self):
        cases = [
            ("rehab.adjust_level mode=assist delta=1", 3, 1),
            ("rehab.adjust_level mode=assist delta=-1", 3, 2),
            ("rehab.adjust_level mode=resist delta=1", 4, 1),
            ("rehab.adjust_level mode=resist delta=-1", 4, 2),
            ("提高助力挡位", 3, 1),
            ("降低助力挡位", 3, 2),
            ("提高抗阻挡位", 4, 1),
            ("降低抗阻挡位", 4, 2),
            ("提高助力档位", 3, 1),
            ("降低助力档位", 3, 2),
            ("提高抗阻档位", 4, 1),
            ("降低抗阻档位", 4, 2),
        ]
        for payload, mode, action in cases:
            with self.subTest(payload=payload):
                accepted, request = self.classify_request(1, "turn-level", payload)
                self.assertTrue(accepted)
                self.assertEqual(mode, request.mode)
                self.assertEqual(action, request.action)
                self.assertEqual(0x38, request.joint_mask)

    def test_raw_stt_and_untrusted_sources_never_trigger(self):
        payload = "rehab.set_mode joints=4,5,6 mode=assist"
        for source in (0, 2, 99):
            with self.subTest(source=source):
                accepted, _ = self.classify_request(source, "turn-stt-vla", payload)
                self.assertFalse(accepted)
        accepted, request = self.classify_request(1, "turn-stt-vla", payload)
        self.assertTrue(accepted)
        self.assertEqual(3, request.mode)

    def test_final_stt_locally_submits_fixed_rehab_intent(self):
        start = VOICE_SERVICE.index('if ((rt_strcmp(type, "stt") == 0)')
        end = VOICE_SERVICE.index('if (rt_strcmp(type, "tts") == 0)', start)
        stt_body = VOICE_SERVICE[start:end]
        self.assertIn("voice_service_submit_fixed_level_intent(text)", stt_body)
        helper_start = VOICE_SERVICE.index("static void voice_service_submit_fixed_level_intent")
        helper_end = VOICE_SERVICE.index("static void voice_service_handle_server_text", helper_start)
        helper = VOICE_SERVICE[helper_start:helper_end]
        self.assertIn("VOICE_REHAB_ACTION_SET_MODE", helper)
        self.assertIn("VOICE_REHAB_ACTION_LEVEL_UP", helper)
        self.assertIn("VOICE_REHAB_ACTION_LEVEL_DOWN", helper)
        self.assertIn("voice_rehab_ipc_sender_submit_vla", helper)

    def test_rejects_ambiguous_negated_substring_and_unknown_joint_inputs(self):
        rejected = [
            "rehab.set_mode joint=1 mode=assist mode=resist",
            "rehab.set_mode joint=1 mode=not_assist",
            "please rehab.set_mode joint=1 mode=assist now",
            "rehab.set_mode joint=5 mode=assist",
            "rehab.set_mode joint=5 mode=resist",
            "rehab.set_mode joint=5 mode=passive",
            "rehab.set_mode joints=4,5,6 mode=passive",
            "rehab.set_mode joint=0 mode=assist",
            "rehab.set_mode joint=1 mode=assist",
            "rehab.set_mode joint=2 mode=assist",
            "rehab.set_mode joint=3 mode=resist",
            "rehab.set_mode joint=4 mode=passive",
            "rehab.set_mode joint=6 mode=assist",
            "一号关节不要切换助力模式",
            "一号关节切换助力模式",
            "二号关节切换助力模式",
            "三号关节切换抗阻模式",
            "四号关节切换被动模式",
            "一号关节切换助力模式然后切换抗阻模式",
            "六号关节切换助力模式",
            "切换被动模式",
            "五号关节切换被动模式",
        ]
        for payload in rejected:
            with self.subTest(payload=payload):
                accepted, request = self.classify_request(1, "turn-reject", payload)
                self.assertFalse(accepted)
                self.assertEqual(0xFFFFFFFF, request.mode)
                self.assertEqual(0, request.action)
                self.assertEqual(0, request.joint_mask)
                self.assertEqual(0, request.event_fingerprint)

    def test_rejects_malformed_event_metadata_and_payload(self):
        for event_id, payload in (
            (None, "rehab.set_mode joints=4,5,6 mode=assist"),
            ("", "rehab.set_mode joints=4,5,6 mode=assist"),
            ("x" * 65, "rehab.set_mode joints=4,5,6 mode=assist"),
            ("bad id", "rehab.set_mode joints=4,5,6 mode=assist"),
            ("turn-1", None),
            ("turn-1", ""),
        ):
            with self.subTest(event_id=event_id, payload=payload):
                accepted, request = self.classify_request(1, event_id, payload)
                self.assertFalse(accepted)
                self.assertEqual(0xFFFFFFFF, request.mode)
                self.assertEqual(0, request.action)
                self.assertEqual(0, request.joint_mask)
                self.assertEqual(0, request.event_fingerprint)

    def test_event_id_boundary_accepts_64_and_rejects_65_bytes(self):
        payload = "rehab.set_mode joints=4,5,6 mode=assist"
        accepted, _ = self.classify_request(1, "x" * 64, payload)
        rejected, request = self.classify_request(1, "x" * 65, payload)
        self.assertTrue(accepted)
        self.assertFalse(rejected)
        self.assertEqual(0xFFFFFFFF, request.mode)

    def test_event_fingerprint_is_stable_equality_data_not_a_sequence(self):
        payload = "rehab.set_mode joints=4,5,6 mode=assist"
        first_ok, first = self.classify_request(1, "session-a:17", payload)
        duplicate_ok, duplicate = self.classify_request(1, "session-a:17", payload)
        next_ok, next_event = self.classify_request(1, "session-a:18", payload)
        self.assertTrue(first_ok and duplicate_ok and next_ok)
        self.assertEqual(first.event_fingerprint, duplicate.event_fingerprint)
        self.assertNotEqual(first.event_fingerprint, next_event.event_fingerprint)

    def test_module_has_no_formatting_dependency_or_sequence_identity_fields(self):
        source = SOURCE.read_text(encoding="utf-8")
        header = (INCLUDE / "voice_mode_intent.h").read_text(encoding="utf-8")
        self.assertNotIn("stdio.h", source)
        self.assertNotIn("snprintf", source)
        self.assertNotIn("dedupe_key", header)
        self.assertNotIn("request_id", header)
        self.assertNotIn("boot_epoch", header)
        self.assertIn("diagnostic/equality fingerprint", header)


if __name__ == "__main__":
    unittest.main()
