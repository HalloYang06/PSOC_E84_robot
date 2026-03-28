from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


class ResolveTaskCliTest(unittest.TestCase):
    def test_cli_resolves_example_payload(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        input_path = repo_root / "vla_system" / "examples" / "clear_pick_and_place.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vla_system.cli.resolve_task_cli",
                "--input",
                str(input_path),
                "--pretty",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["task_type"], "pick_and_place")
        self.assertEqual(payload["object_id"], "bottle_01")
        self.assertFalse(payload["need_confirmation"])


if __name__ == "__main__":
    unittest.main()