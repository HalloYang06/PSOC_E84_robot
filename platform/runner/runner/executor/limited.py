from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: str
    stderr: str


class LimitedExecutor:
    """
    First-version runner executor.

    This intentionally runs only a very small allowed command set. The backend can expand
    allowlists later. For now we support:
      - echo
      - git --version
      - python --version
      - node --version
    """

    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir

    def is_allowed(self, argv: list[str]) -> bool:
        if not argv:
            return False
        cmd = argv[0].lower()
        if cmd == "echo":
            return True
        if cmd == "git" and argv[1:] == ["--version"]:
            return True
        if cmd == "python" and argv[1:] == ["--version"]:
            return True
        if cmd == "node" and argv[1:] == ["--version"]:
            return True
        return False

    def run(self, argv: list[str], timeout_s: int = 60) -> ExecResult:
        if not self.is_allowed(argv):
            raise RuntimeError(f"Command not allowed: {argv}")
        if argv[0].lower() == "echo":
            return ExecResult(returncode=0, stdout=(" ".join(argv[1:]) + "\n"), stderr="")
        p = subprocess.run(
            argv,
            cwd=str(self.workdir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            shell=False,
        )
        return ExecResult(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
