from pathlib import Path
import unittest


M55_ROOT = Path(__file__).resolve().parents[1]
OPUS_ROOT = M55_ROOT / "libraries" / "components" / "opus"


class OpusIntegrationContractTest(unittest.TestCase):
    def test_opus_headers_and_build_script_exist(self):
        expected = [
            OPUS_ROOT / "include" / "opus.h",
            OPUS_ROOT / "include" / "opus_defines.h",
            OPUS_ROOT / "include" / "opus_types.h",
            OPUS_ROOT / "SConscript",
        ]

        for path in expected:
            with self.subTest(path=str(path)):
                self.assertTrue(path.exists(), f"missing Opus integration file: {path}")

    def test_opus_component_is_included_by_libraries_sconscript(self):
        text = (M55_ROOT / "libraries" / "components" / "SConscript").read_text(encoding="utf-8")

        self.assertIn("opus/SConscript", text)

    def test_applications_can_include_opus_headers(self):
        text = (M55_ROOT / "applications" / "SConscript").read_text(encoding="utf-8")

        self.assertIn("libraries', 'components', 'opus", text)
        self.assertIn("os.path.join(opus_root, 'include')", text)

    def test_opus_sconscript_uses_fixed_point_sources(self):
        text = (OPUS_ROOT / "SConscript").read_text(encoding="utf-8")

        self.assertIn("FIXED_POINT", text)
        self.assertIn("DISABLE_FLOAT_API", text)
        self.assertIn("src/opus.c", text)
        self.assertIn("silk/fixed", text)
        self.assertIn("DefineGroup('opus'", text)


if __name__ == "__main__":
    unittest.main()
