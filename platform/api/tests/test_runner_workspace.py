from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER_ROOT = ROOT / "apps" / "runner"
for candidate in (ROOT, RUNNER_ROOT):
    path = str(candidate)
    if path not in sys.path:
        sys.path.insert(0, path)

from runner.executor.limited import LimitedExecutor
from runner.workspace.manager import WorkspaceManager


def test_workspace_manager_creates_and_cleans_task_workspace(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)

    workspace = manager.prepare("TASK-001")

    assert workspace.path == tmp_path / "tasks" / "TASK-001"
    assert workspace.logs_dir == tmp_path / "logs" / "TASK-001"
    assert workspace.artifacts_dir == tmp_path / "artifacts" / "TASK-001"
    assert workspace.path.exists()
    assert workspace.logs_dir.exists()
    assert workspace.artifacts_dir.exists()

    manager.cleanup("TASK-001")
    assert workspace.path.exists()

    manager.nuke("TASK-001")
    assert not workspace.path.exists()
    assert not workspace.logs_dir.exists()
    assert not workspace.artifacts_dir.exists()


def test_limited_executor_matches_documented_allowlist(tmp_path: Path) -> None:
    executor = LimitedExecutor(tmp_path)

    assert executor.is_allowed(["echo", "hello", "world"]) is True
    assert executor.is_allowed(["git", "--version"]) is True
    assert executor.is_allowed(["python", "--version"]) is True
    assert executor.is_allowed(["node", "--version"]) is True
    assert executor.is_allowed(["bash", "-lc", "echo hello"]) is False

    result = executor.run(["echo", "workspace", "ready"])
    assert result.returncode == 0
    assert result.stdout == "workspace ready\n"
    assert result.stderr == ""
