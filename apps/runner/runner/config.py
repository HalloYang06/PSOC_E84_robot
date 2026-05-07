from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str | None = None) -> str:
    v = os.getenv(name)
    if v is None:
        if default is None:
            raise RuntimeError(f"Missing required env var: {name}")
        return default
    return v


@dataclass(frozen=True)
class RunnerConfig:
    runner_id: str
    runner_name: str
    platform_api_url: str
    runner_token: str
    workdir: Path
    allow_hardware_access: bool
    max_concurrent_tasks: int
    heartbeat_seconds: int
    poll_seconds: int
    cli_provider: str = "disabled"
    cli_executor_path: Path | None = None
    cli_timeout_seconds: int = 1800

    @staticmethod
    def from_env() -> "RunnerConfig":
        runner_id = _env("RUNNER_ID", "runner-local")
        runner_name = _env("RUNNER_NAME", runner_id)
        platform_api_url = _env("PLATFORM_API_URL", "http://localhost:8000").rstrip("/")
        runner_token = _env("RUNNER_TOKEN", "change-me")
        workdir = Path(_env("RUNNER_WORKDIR", "./artifacts/runner-workspace")).resolve()
        allow_hardware_access = _env("ALLOW_HARDWARE_ACCESS", "false").lower() in ("1", "true", "yes", "y")
        max_concurrent_tasks = int(_env("MAX_CONCURRENT_TASKS", "1"))
        heartbeat_seconds = int(_env("HEARTBEAT_SECONDS", "15"))
        poll_seconds = int(_env("POLL_SECONDS", "10"))
        cli_provider = _env("RUNNER_CLI_PROVIDER", "disabled").strip().lower() or "disabled"
        if cli_provider not in {"claude", "codex", "disabled"}:
            cli_provider = "disabled"
        cli_executor_raw = _env("RUNNER_CLI_EXECUTOR", "").strip()
        cli_executor_path = Path(cli_executor_raw).resolve() if cli_executor_raw else None
        cli_timeout_seconds = int(_env("RUNNER_CLI_TIMEOUT_SECONDS", "1800"))
        return RunnerConfig(
            runner_id=runner_id,
            runner_name=runner_name,
            platform_api_url=platform_api_url,
            runner_token=runner_token,
            workdir=workdir,
            allow_hardware_access=allow_hardware_access,
            max_concurrent_tasks=max_concurrent_tasks,
            heartbeat_seconds=heartbeat_seconds,
            poll_seconds=poll_seconds,
            cli_provider=cli_provider,
            cli_executor_path=cli_executor_path,
            cli_timeout_seconds=cli_timeout_seconds,
        )


def ensure_dirs(cfg: RunnerConfig) -> None:
    cfg.workdir.mkdir(parents=True, exist_ok=True)
    (cfg.workdir / "tasks").mkdir(parents=True, exist_ok=True)
    (cfg.workdir / "logs").mkdir(parents=True, exist_ok=True)
    (cfg.workdir / "artifacts").mkdir(parents=True, exist_ok=True)
    (cfg.workdir / "inbox").mkdir(parents=True, exist_ok=True)
    (cfg.workdir / "inbox" / "processed").mkdir(parents=True, exist_ok=True)

