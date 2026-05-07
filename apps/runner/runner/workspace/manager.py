from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    task_id: str
    path: Path
    logs_dir: Path
    artifacts_dir: Path


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.tasks_root = root / "tasks"
        self.logs_root = root / "logs"
        self.artifacts_root = root / "artifacts"

    def prepare(self, task_id: str) -> Workspace:
        task_path = self.tasks_root / task_id
        logs_dir = self.logs_root / task_id
        artifacts_dir = self.artifacts_root / task_id
        task_path.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        return Workspace(task_id=task_id, path=task_path, logs_dir=logs_dir, artifacts_dir=artifacts_dir)

    def cleanup(self, task_id: str) -> None:
        # First-version: keep workspace by default to aid debugging.
        # This method exists for future cleanup policies.
        _ = task_id

    def nuke(self, task_id: str) -> None:
        # Explicit destructive cleanup (not called by default).
        for base in (self.tasks_root, self.logs_root, self.artifacts_root):
            p = base / task_id
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

