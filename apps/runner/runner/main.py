from __future__ import annotations

import json
import importlib.util
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cli_bridge import dispatch_prompt_to_cli
from .client import PlatformClient
from .config import RunnerConfig, ensure_dirs
from .executor import LimitedExecutor
from .git_tools import execute_git_preflight, is_git_preflight_command
from .hardware.device_capture import execute_device_capture_command, is_device_capture_command
from .hardware.serial_tools import execute_serial_command, is_serial_command, parse_runner_command_body
from .hardware.serial_tools import scan_usb_and_serial_devices
from .logs import LogCollector
from .workspace import WorkspaceManager


def _detect_capabilities(cfg: RunnerConfig) -> list[str]:
    capabilities = ["git", "git.preflight", "python", "node", "runner.inbox", "runner.prompt.relay"]
    if cfg.allow_hardware_access:
        capabilities.extend(["hardware", "serial.usb.scan", "serial.write", "serial.waveform.aicsv", "robotics.capture"])
    return capabilities


def _write_prompt_inbox_file(cfg: RunnerConfig, message: dict[str, Any], log: LogCollector) -> str | None:
    """Persist a plain-text relay message into the runner inbox so the local CLI can pick it up."""
    inbox_dir = cfg.workdir / "inbox"
    try:
        inbox_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        log.write("error", f"Failed to create runner inbox dir {inbox_dir}: {exc}")
        return None
    message_id = str(message.get("id") or "").strip()
    if not message_id:
        return None
    file_path = inbox_dir / f"{message_id}.json"
    record = {
        "id": message_id,
        "title": message.get("title"),
        "body": message.get("body"),
        "project_id": message.get("project_id"),
        "task_id": message.get("task_id"),
        "dispatch_id": message.get("dispatch_id"),
        "sender_type": message.get("sender_type"),
        "sender_id": message.get("sender_id"),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        file_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log.write("error", f"Failed to write runner inbox file {file_path}: {exc}")
        return None
    return str(file_path)


def _archive_inbox_file(inbox_path: Path, log: LogCollector) -> None:
    """Move a fully-handled inbox file into inbox/processed/ so the next poll skips it."""
    try:
        processed_dir = inbox_path.parent / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        target = processed_dir / inbox_path.name
        if target.exists():
            target.unlink()
        inbox_path.replace(target)
    except Exception as exc:
        log.write("warn", f"Failed to archive inbox file {inbox_path}: {exc}")


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

    if is_device_capture_command(payload):
        kind = str((payload or {}).get("kind") or "robotics.capture").strip()
        status = str(message.get("status") or "").strip().lower()
        if status == "pending":
            client.ack_runner_message(
                cfg.runner_id,
                message_id,
                note=f"{cfg.runner_name} accepted {kind} and is handling the device capture request.",
            )
        result = execute_device_capture_command(
            payload or {},
            allow_hardware_access=cfg.allow_hardware_access,
            workdir=cfg.workdir,
            repo_root=cfg.device_data_repo_root,
            git_push=cfg.device_data_git_push,
        )
        client.complete_runner_message(
            cfg.runner_id,
            message_id,
            result_status=str(result.get("result_status") or "failed"),
            note=str(result.get("note") or ""),
            metadata={"runner_result": result.get("result") or {}, "runner_capability": "robotics.capture"},
        )
        log.write("info", f"Handled runner relay {message_id} kind={kind} status={result.get('result_status')}")
        return True

    # Fallback: plain text prompt. Drop it into runner workdir/inbox/ so the local
    # provider CLI (Claude Code / Codex / platform-workstation-adapter) can pick
    # it up, and ack the platform so the user sees "已下发". Acceptance fix for
    # "我在平台发指令根本过不来 CLI" — without this the message stays "pending"
    # forever and the dispatch UI shows it as queued.
    status = str(message.get("status") or "").strip().lower()
    inbox_path = _write_prompt_inbox_file(cfg, message, log)
    title = str(message.get("title") or "").strip()
    note_target = inbox_path or str(cfg.workdir / "inbox")
    if status == "pending":
        try:
            client.ack_runner_message(
                cfg.runner_id,
                message_id,
                note=f"{cfg.runner_name} accepted the prompt and wrote it to {note_target}.",
            )
        except Exception as exc:
            log.write("error", f"Failed to ack runner relay {message_id}: {exc}")

    provider = (cfg.cli_provider or "disabled").strip().lower()
    if provider in {"claude", "codex"} and inbox_path:
        cli_result = dispatch_prompt_to_cli(message, Path(inbox_path), cfg, log)
        try:
            client.complete_runner_message(
                cfg.runner_id,
                message_id,
                result_status=str(cli_result.get("result_status") or "failed"),
                note=str(cli_result.get("note") or ""),
            )
        except Exception as exc:
            log.write("error", f"Failed to complete runner relay {message_id}: {exc}")
        _archive_inbox_file(Path(inbox_path), log)
        log.write(
            "info",
            f"Handled runner relay {message_id} kind=cli.invoke provider={provider} "
            f"status={cli_result.get('result_status')}",
        )
        return True

    # Inbox persistence is delivery, not execution. Keep the platform command
    # acked until a CLI, Desktop bridge, or adapter reports the final result.
    log.write(
        "info",
        f"Handled runner relay {message_id} kind=prompt.inbox path={inbox_path or '<failed>'}",
    )
    return True


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


def _build_device_interface_scan() -> dict[str, Any]:
    scanner_path = Path(__file__).resolve().parents[3] / "scripts" / "scan-device-interfaces.py"
    if scanner_path.exists():
        spec = importlib.util.spec_from_file_location("ai_collab_device_scanner", scanner_path)
        if spec is not None and spec.loader is not None:
            scanner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(scanner)
            build_scan = getattr(scanner, "build_scan", None)
            if callable(build_scan):
                scan = build_scan()
                if isinstance(scan, dict):
                    return scan

    serial_scan = scan_usb_and_serial_devices()
    interfaces: list[dict[str, Any]] = []
    for item in serial_scan.get("serial_devices") or []:
        if not isinstance(item, dict):
            continue
        port = str(item.get("port") or item.get("label") or "").strip()
        if not port:
            continue
        interfaces.append(
            {
                "id": f"serial:{port}",
                "kind": "serial",
                "name": str(item.get("label") or port),
                "status": "available",
                "transport": str(item.get("source") or "serial"),
                "details": item,
                "read_capability": True,
                "write_capability": "review_required",
                "risk_level": "medium",
            }
        )
    for index, item in enumerate(serial_scan.get("usb_devices") or []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("device_id") or f"USB {index + 1}").strip()
        if not label:
            continue
        interfaces.append(
            {
                "id": f"usb:{index + 1}",
                "kind": "usb",
                "name": label,
                "status": "available",
                "transport": str(item.get("source") or "usb"),
                "details": item,
                "read_capability": True,
                "write_capability": "review_required",
                "risk_level": "low",
            }
        )
    return {
        "host": socket.gethostname(),
        "platform": serial_scan.get("host_os") or "",
        "scanner_version": "runner-package.v1",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "interfaces": interfaces,
        "summary": {
            "total": len(interfaces),
            "serial_count": len([item for item in interfaces if item.get("kind") == "serial"]),
            "usb_count": len([item for item in interfaces if item.get("kind") == "usb"]),
        },
        "warnings": [],
    }


def _sync_device_interfaces_if_configured(client: PlatformClient, cfg: RunnerConfig, log: LogCollector) -> bool:
    if not cfg.project_id or not cfg.computer_node_id:
        return False
    try:
        scan = _build_device_interface_scan()
        client.sync_device_interfaces(
            cfg.runner_id,
            project_id=cfg.project_id,
            computer_node_id=cfg.computer_node_id,
            scan=scan,
        )
        log.write(
            "info",
            f"Synced device interfaces project={cfg.project_id} computer={cfg.computer_node_id} count={len(scan['interfaces'])}",
        )
        return True
    except Exception as exc:
        log.write("warn", f"Device interface sync failed: {exc}")
        return False


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
    last_device_scan = 0.0
    while True:
        now = time.time()
        if now - last_hb >= cfg.heartbeat_seconds:
            try:
                client.heartbeat(cfg.runner_id)
            except Exception:
                pass
            last_hb = now
        if now - last_device_scan >= cfg.device_scan_seconds:
            _sync_device_interfaces_if_configured(client, cfg, relay_log)
            last_device_scan = now

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
