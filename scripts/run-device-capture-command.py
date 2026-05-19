#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_APP = REPO_ROOT / "apps" / "runner"
if str(RUNNER_APP) not in sys.path:
    sys.path.insert(0, str(RUNNER_APP))

from runner.hardware.device_capture import execute_device_capture_command  # noqa: E402

WORKER_WAIT_SECONDS = 8.0


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def safe_token(value: Any, fallback: str) -> str:
    raw = str(value or "").strip()
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in raw).strip("-")
    return safe[:96] or fallback


def capture_dir_for(payload: dict[str, Any], workdir: Path) -> Path:
    return (
        workdir
        / "device-captures"
        / safe_token(payload.get("project_id"), "project")
        / safe_token(payload.get("computer_node_id"), "computer")
        / safe_token(payload.get("interface_id"), "interface")
        / safe_token(payload.get("capture_id"), "capture")
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def completed_note(title: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "handled": True,
        "result_status": "completed",
        "note": title,
        "result": result,
    }


def failed_note(title: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "handled": True,
        "result_status": "failed",
        "note": title,
        "result": result,
    }


def run_worker(payload_file: Path, workdir: Path, *, allow_hardware_access: bool, repo_root: Path | None, git_push: bool) -> int:
    payload = json.loads(payload_file.read_text(encoding="utf-8-sig"))
    capture_dir = capture_dir_for(payload, workdir)
    stop_file = capture_dir / "stop-request.json"
    result_file = capture_dir / "worker-result.json"
    heartbeat_file = capture_dir / "worker-heartbeat.json"
    start_result = execute_device_capture_command(
        {**payload, "kind": "robotics.capture.start"},
        allow_hardware_access=allow_hardware_access,
        workdir=workdir,
        repo_root=repo_root,
        git_push=git_push,
    )
    write_json(capture_dir / "worker-start-result.json", start_result)
    deadline = time.time() + 24 * 60 * 60
    while time.time() < deadline:
        write_json(
            heartbeat_file,
            {
                "capture_id": safe_token(payload.get("capture_id"), "capture"),
                "status": "running",
                "updated_at": time.time(),
            },
        )
        if stop_file.exists():
            try:
                stop_payload = json.loads(stop_file.read_text(encoding="utf-8-sig"))
            except Exception:
                stop_payload = payload
            result = execute_device_capture_command(
                {**payload, **stop_payload, "kind": "robotics.capture.stop"},
                allow_hardware_access=allow_hardware_access,
                workdir=workdir,
                repo_root=repo_root,
                git_push=git_push,
            )
            write_json(result_file, result)
            return 0 if str(result.get("result_status") or "") == "completed" else 2
        time.sleep(0.2)
    result = failed_note(
        "采集会话等待停止超时",
        {
            "ok": False,
            "kind": "robotics.capture.stop",
            "capture_id": safe_token(payload.get("capture_id"), "capture"),
            "error": "capture worker timed out before stop request",
        },
    )
    write_json(result_file, result)
    return 2


def start_persistent_capture(payload: dict[str, Any], args: argparse.Namespace, repo_root: Path | None) -> dict[str, Any]:
    workdir = Path(args.workdir).resolve()
    capture_dir = capture_dir_for(payload, workdir)
    payload_file = capture_dir / "worker-payload.json"
    stop_file = capture_dir / "stop-request.json"
    result_file = capture_dir / "worker-result.json"
    for stale in (stop_file, result_file):
        stale.unlink(missing_ok=True)
    write_json(payload_file, payload)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--payload-file",
        str(payload_file),
        "--workdir",
        str(workdir),
    ]
    if args.hardware_access:
        command.append("--hardware-access")
    if repo_root is not None:
        command.extend(["--repo-root", str(repo_root)])
    if args.git_push:
        command.append("--git-push")
    stdout_path = capture_dir / "worker.out.log"
    stderr_path = capture_dir / "worker.err.log"
    stdout = stdout_path.open("ab")
    stderr = stderr_path.open("ab")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if os.name == "nt":
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    proc = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        stdout=stdout,
        stderr=stderr,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )
    stdout.close()
    stderr.close()
    return completed_note(
        "采集会话已在目标电脑后台运行",
        {
            "ok": True,
            "kind": "robotics.capture.start",
            "capture_id": safe_token(payload.get("capture_id"), "capture"),
            "status": "running" if args.hardware_access else "prepared",
            "capture_mode": "persistent_worker",
            "manifest": str((capture_dir / "manifest.json").relative_to(workdir)).replace("\\", "/"),
            "preview": str((capture_dir / "preview.jsonl").relative_to(workdir)).replace("\\", "/"),
            "worker_pid": proc.pid,
        },
    )


def stop_persistent_capture(payload: dict[str, Any], args: argparse.Namespace, repo_root: Path | None) -> dict[str, Any]:
    workdir = Path(args.workdir).resolve()
    capture_dir = capture_dir_for(payload, workdir)
    stop_file = capture_dir / "stop-request.json"
    result_file = capture_dir / "worker-result.json"
    write_json(stop_file, payload)
    deadline = time.time() + WORKER_WAIT_SECONDS
    while time.time() < deadline:
        if result_file.exists():
            try:
                return json.loads(result_file.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                break
        time.sleep(0.2)
    return execute_device_capture_command(
        payload,
        allow_hardware_access=bool(args.hardware_access),
        workdir=workdir,
        repo_root=repo_root,
        git_push=bool(args.git_push),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a device capture relay command using the shared runner capture implementation.")
    parser.add_argument("--payload-json", default="", help="JSON body from the platform runner command.")
    parser.add_argument("--payload-file", default="", help="Path to a UTF-8 JSON payload file from the runner script.")
    parser.add_argument("--workdir", required=True, help="Runner working directory for capture sessions and previews.")
    parser.add_argument("--hardware-access", action="store_true", help="Allow read-only hardware capture on this computer.")
    parser.add_argument("--repo-root", default=os.getenv("RUNNER_DEVICE_DATA_REPO", ""), help="Optional Git worktree for device capture evidence.")
    parser.add_argument("--git-push", action="store_true", default=truthy(os.getenv("RUNNER_DEVICE_DATA_GIT_PUSH")))
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    payload_text = args.payload_json
    if args.payload_file:
        payload_text = Path(args.payload_file).read_text(encoding="utf-8-sig")
    try:
        payload: dict[str, Any] = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        print(json.dumps({"result_status": "failed", "note": f"采集请求不是有效 JSON: {exc}", "result": {"ok": False}}, ensure_ascii=False))
        return 1

    repo_root = Path(args.repo_root).resolve() if str(args.repo_root or "").strip() else None
    if args.worker:
        return run_worker(Path(args.payload_file), Path(args.workdir).resolve(), allow_hardware_access=bool(args.hardware_access), repo_root=repo_root, git_push=bool(args.git_push))

    kind = str(payload.get("kind") or "").strip()
    if kind == "robotics.capture.start":
        result = start_persistent_capture(payload, args, repo_root)
    elif kind == "robotics.capture.stop":
        result = stop_persistent_capture(payload, args, repo_root)
    else:
        result = execute_device_capture_command(
            payload,
            allow_hardware_access=bool(args.hardware_access),
            workdir=Path(args.workdir).resolve(),
            repo_root=repo_root,
            git_push=bool(args.git_push),
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if str(result.get("result_status") or "") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
