from __future__ import annotations

import time
from typing import Any

from .client import PlatformClient
from .config import RunnerConfig, ensure_dirs
from .executor import LimitedExecutor
from .git_tools import execute_git_preflight, is_git_preflight_command
from .hardware.serial_tools import execute_serial_command, is_serial_command, parse_runner_command_body
from .logs import LogCollector
from .workspace import WorkspaceManager


def _detect_capabilities(cfg: RunnerConfig) -> list[str]:
    capabilities = ["git", "git.preflight", "python", "node", "runner.inbox"]
    if cfg.allow_hardware_access:
        capabilities.extend(["hardware", "serial.usb.scan", "serial.write", "serial.waveform.aicsv"])
    return capabilities


def _handle_task(task: dict[str, Any], ws_mgr: WorkspaceManager, client: PlatformClient, cfg: RunnerConfig) -> None:
    task_id = str(task.get("id") or task.get("task_id") or "unknown-task")
    ws = ws_mgr.prepare(task_id)
    log = LogCollector(ws.logs_dir / "runner.log")
    exe = LimitedExecutor(ws.path)

    log.write("info", f"Starting task {task_id}")
    client.post_task_log(task_id, "info", "Runner started task")

    # First-version: accept optional command list
    # task["commands"] = [["echo","hi"], ["git","--version"], ...]
    commands = task.get("commands") or []
    results: list[dict[str, Any]] = []
    for cmd in commands:
        if not isinstance(cmd, list) or not all(isinstance(x, str) for x in cmd):
            continue
        try:
            r = exe.run(cmd)
            results.append({"cmd": cmd, "returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr})
            log.write("info", f"Ran {cmd} rc={r.returncode}")
        except Exception as e:
            results.append({"cmd": cmd, "error": str(e)})
            log.write("error", f"Failed {cmd}: {e}")

    client.post_task_result(task_id, {"status": "done", "results": results})
    log.write("info", f"Finished task {task_id}")


def _handle_runner_relay_message(
    message: dict[str, Any],
    client: PlatformClient,
    cfg: RunnerConfig,
    log: LogCollector,
) -> bool:
    message_id = str(message.get("id") or "").strip()
    if not message_id:
        return False
    payload = parse_runner_command_body(str(message.get("body") or ""))
    if is_serial_command(payload):
        kind = str((payload or {}).get("kind") or "serial").strip()
        status = str(message.get("status") or "").strip().lower()
        if status == "pending":
            client.ack_runner_message(
                cfg.runner_id,
                message_id,
                note=f"{cfg.runner_name} accepted {kind} and is preparing the local hardware action.",
            )
        result = execute_serial_command(payload or {}, allow_hardware_access=cfg.allow_hardware_access)
        client.complete_runner_message(
            cfg.runner_id,
            message_id,
            result_status=str(result.get("result_status") or "failed"),
            note=str(result.get("note") or ""),
        )
        log.write("info", f"Handled runner relay {message_id} kind={kind} status={result.get('result_status')}")
        return True

    if is_git_preflight_command(payload):
        kind = str((payload or {}).get("kind") or "git.preflight").strip()
        status = str(message.get("status") or "").strip().lower()
        if status == "pending":
            client.ack_runner_message(
                cfg.runner_id,
                message_id,
                note=f"{cfg.runner_name} accepted {kind}. It will only run read-only Git capability checks.",
            )
        result = execute_git_preflight(payload or {})
        client.complete_runner_message(
            cfg.runner_id,
            message_id,
            result_status=str(result.get("result_status") or "failed"),
            note=str(result.get("note") or ""),
        )
        log.write("info", f"Handled runner relay {message_id} kind={kind} status={result.get('result_status')}")
        return True

    return False


def _poll_runner_relay_inbox(client: PlatformClient, cfg: RunnerConfig, log: LogCollector) -> None:
    for message in client.fetch_runner_inbox(cfg.runner_id, limit=10):
        try:
            _handle_runner_relay_message(message, client, cfg, log)
        except Exception as exc:
            message_id = str(message.get("id") or "").strip()
            log.write("error", f"Failed runner relay {message_id or '<unknown>'}: {exc}")
            if message_id:
                try:
                    client.complete_runner_message(
                        cfg.runner_id,
                        message_id,
                        result_status="failed",
                        note=f"Runner failed while handling the allowlisted relay command: {exc}",
                    )
                except Exception:
                    pass


def main() -> int:
    cfg = RunnerConfig.from_env()
    ensure_dirs(cfg)
    client = PlatformClient(base_url=cfg.platform_api_url, runner_id=cfg.runner_id, runner_token=cfg.runner_token)
    ws_mgr = WorkspaceManager(cfg.workdir)
    relay_log = LogCollector(cfg.workdir / "logs" / "runner-relay.log")

    # Register (best-effort)
    try:
        client.register(
            runner_id=cfg.runner_id,
            runner_name=cfg.runner_name,
            capabilities=_detect_capabilities(cfg),
            hardware_access=cfg.allow_hardware_access,
        )
    except Exception:
        # Allow runner to operate even if backend not ready yet.
        pass

    last_hb = 0.0
    while True:
        now = time.time()
        if now - last_hb >= cfg.heartbeat_seconds:
            try:
                client.heartbeat(cfg.runner_id)
            except Exception:
                pass
            last_hb = now

        try:
            _poll_runner_relay_inbox(client, cfg, relay_log)
        except Exception:
            pass

        task = client.fetch_next_task(cfg.runner_id)
        if task:
            try:
                _handle_task(task, ws_mgr, client, cfg)
            except Exception:
                # Keep running regardless of task failures.
                pass
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
