import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "nanopi_rehab_mode.sh"


def find_bash():
    configured = os.environ.get("NANOPI_TEST_BASH")
    candidates = [
        configured,
        r"F:\Git\Git\bin\bash.exe" if os.name == "nt" else None,
        shutil.which("bash"),
    ]
    return next((pathlib.Path(item) for item in candidates if item and pathlib.Path(item).exists()), None)


BASH = find_bash()

HEALTHY_LINK = """\
4: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 state UP
    can <BERR-REPORTING> state ERROR-ACTIVE
    bitrate 1000000 sample-point 0.750
    re-started bus-errors arbit-lost error-warn error-pass bus-off
    0          0          0          0          0          0
"""


class NanoPiRehabModeScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_checks_can_link_before_transmit(self):
        self.assertIn('ip -details -statistics link show "$iface"', self.script)
        self.assertIn('state ERROR-ACTIVE', self.script)
        self.assertIn('nominal_bitrate=', self.script)
        self.assertIn('"$nominal_bitrate" != "1000000"', self.script)
        self.assertIn('bus_off', self.script)

    def test_only_passive_is_available_before_remote_safety_gates(self):
        self.assertIn('passive|stop)', self.script)
        self.assertIn('remote active modes are blocked', self.script)
        self.assertNotIn('active)\n        mode_code="01"', self.script)
        self.assertNotIn('assist)\n        mode_code="03"', self.script)
        self.assertNotIn('resist)\n        mode_code="04"', self.script)

    def test_prints_exact_frames_and_stops_on_cansend_failure(self):
        self.assertIn("set -euo pipefail", self.script)
        self.assertIn('321#${seq_hex}', self.script)
        self.assertIn('320#04${seq_hex}000000000000', self.script)
        self.assertIn('echo "tx 321#${seq_hex}"', self.script)
        self.assertIn('echo "tx 320#04${seq_hex}000000000000"', self.script)

    def run_script(self, mode, link_info=HEALTHY_LINK, extra_args=(), can_fail_at=0):
        if BASH is None:
            self.skipTest("Bash is unavailable")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = pathlib.Path(temp_dir_name)
            can_log = temp_dir / "can.log"
            can_count = temp_dir / "can.count"
            seq_file = temp_dir / "seq"
            for name, body in {
                "ip": '#!/usr/bin/env bash\nprintf "%s" "$FAKE_IP_OUTPUT"\n',
                "cansend": (
                    "#!/usr/bin/env bash\n"
                    "count=0\n"
                    '[[ -f "$CAN_COUNT" ]] && count="$(cat "$CAN_COUNT")"\n'
                    "count=$((count + 1))\n"
                    'printf "%s\\n" "$count" > "$CAN_COUNT"\n'
                    'printf "%s\\n" "$*" >> "$CAN_LOG"\n'
                    '[[ "${CAN_FAIL_AT:-0}" -eq "$count" ]] && exit 9\n'
                    "exit 0\n"
                ),
                "sleep": "#!/usr/bin/env bash\nexit 0\n",
            }.items():
                path = temp_dir / name
                path.write_text(body, encoding="utf-8", newline="\n")
                path.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{temp_dir}{os.pathsep}{env['PATH']}",
                    "FAKE_IP_OUTPUT": link_info,
                    "CAN_LOG": str(can_log),
                    "CAN_COUNT": str(can_count),
                    "CAN_FAIL_AT": str(can_fail_at),
                    "REHAB_SEQ_FILE": str(seq_file),
                }
            )
            result = subprocess.run(
                [str(BASH), str(SCRIPT), mode, "can0", *extra_args],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            frames = can_log.read_text(encoding="utf-8").splitlines() if can_log.exists() else []
            return result, frames

    def test_passive_executes_exact_frame_sequence(self):
        result, frames = self.run_script("passive")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(frames, ["can0 321#01", "can0 321#01", "can0 320#0401000000000000"])

    def test_lower_up_does_not_satisfy_up_preflight(self):
        result, frames = self.run_script("passive", HEALTHY_LINK.replace("NOARP,UP,", "NOARP,"))

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(frames, [])

    def test_dbitrate_does_not_satisfy_nominal_bitrate(self):
        link_info = HEALTHY_LINK.replace(
            "bitrate 1000000 sample-point 0.750",
            "bitrate 500000 sample-point 0.750 dbitrate 1000000",
        )
        result, frames = self.run_script("passive", link_info)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(frames, [])

    def test_active_mode_and_extra_arguments_send_nothing(self):
        active_result, active_frames = self.run_script("assist")
        extra_result, extra_frames = self.run_script("passive", extra_args=("unexpected",))

        self.assertNotEqual(active_result.returncode, 0)
        self.assertEqual(active_frames, [])
        self.assertNotEqual(extra_result.returncode, 0)
        self.assertEqual(extra_frames, [])

    def test_bus_off_history_sends_nothing(self):
        link_info = HEALTHY_LINK.replace(
            "0          0          0          0          0          0",
            "0          0          0          0          0          1",
        )
        result, frames = self.run_script("passive", link_info)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(frames, [])

    def test_cansend_failure_stops_remaining_frames(self):
        first_result, first_frames = self.run_script("passive", can_fail_at=1)
        second_result, second_frames = self.run_script("passive", can_fail_at=2)

        self.assertNotEqual(first_result.returncode, 0)
        self.assertEqual(first_frames, ["can0 321#01"])
        self.assertNotEqual(second_result.returncode, 0)
        self.assertEqual(second_frames, ["can0 321#01", "can0 321#01"])


if __name__ == "__main__":
    unittest.main()
