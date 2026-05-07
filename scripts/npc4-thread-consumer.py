#!/usr/bin/env python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


DEFAULT_WORKSTATION_ID = "codex-session-019db52e-dca5-7412-ba6c-621d0fc78537"
DEFAULT_WORKSTATION_NAME = "NPC4"


def main() -> int:
  script_path = Path(__file__).with_name("npc1-thread-consumer.py")
  state_path = Path(__file__).with_name(".npc4-thread-consumer-state.json")
  command = [
    sys.executable,
    str(script_path),
    "--workstation-id",
    DEFAULT_WORKSTATION_ID,
    "--workstation-name",
    DEFAULT_WORKSTATION_NAME,
    "--state-path",
    str(state_path),
    *sys.argv[1:],
  ]
  completed = subprocess.run(command, check=False)
  return completed.returncode


if __name__ == "__main__":
  raise SystemExit(main())
