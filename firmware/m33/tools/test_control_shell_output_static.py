from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROL_C = ROOT / "applications" / "control" / "control_layer.c"


class ControlShellOutputStaticTest(unittest.TestCase):
    def setUp(self):
        self.source = CONTROL_C.read_text(encoding="utf-8")

    def test_background_control_logging_stays_suppressed(self):
        suppress = self.source.index("#define rt_kprintf(...) do { } while (0)")
        shell = self.source.index("#ifdef RT_USING_FINSH")
        self.assertLess(suppress, shell)

    def test_finsh_commands_restore_diagnostic_output(self):
        shell = self.source.index("#ifdef RT_USING_FINSH")
        finsh_include = self.source.index("#include <finsh.h>", shell)
        shell_prelude = self.source[shell:finsh_include]
        self.assertIn("#undef rt_kprintf", shell_prelude)


if __name__ == "__main__":
    unittest.main()
