from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent

RUNNER_SCRIPTS = [
    "connect-ai-collab-runner.ps1",
    "connect-ai-collab-runner.sh",
    "sync-codex-session-threads.ps1",
    "sync-codex-session-threads.sh",
    "sync-claude-session-threads.ps1",
    "sync-claude-session-threads.sh",
    "platform-workstation-adapter.py",
    "platform-provider-executor.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download cloud runner scripts and validate Windows/Linux compatibility guardrails.",
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "cloud-runner-script-compatibility"))
    return parser.parse_args()


def text(value: object, fallback: str = "") -> str:
    raw = str(value or "").strip()
    return raw or fallback


def download(url: str) -> str:
    with urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def run_command(command: list[str], *, timeout: int = 30) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return completed.returncode, completed.stdout
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, (exc.stdout or "") + "\nTimed out"


def powershell_executable() -> str:
    return shutil.which("pwsh") or shutil.which("powershell") or ""


def validate_powershell(path: Path) -> tuple[bool, str]:
    exe = powershell_executable()
    if not exe:
        return False, "PowerShell executable not found"
    code = (
        "$ErrorActionPreference='Stop';"
        "$tokens=$null;$errors=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile({json.dumps(str(path))},[ref]$tokens,[ref]$errors) | Out-Null;"
        "if($errors.Count){$errors | ForEach-Object { $_.Message }; exit 1};"
        "exit 0"
    )
    rc, output = run_command([exe, "-NoProfile", "-NonInteractive", "-Command", code])
    return rc == 0, output.strip()


def validate_bash(path: Path) -> tuple[bool, str]:
    bash = shutil.which("bash")
    if not bash:
        return False, "bash executable not found"
    rc, output = run_command([bash, "-n", str(path)])
    return rc == 0, output.strip()


def validate_python(path: Path) -> tuple[bool, str]:
    rc, output = run_command([sys.executable, "-m", "py_compile", str(path)])
    return rc == 0, output.strip()


def contains_any(haystack: str, needles: list[str]) -> bool:
    return any(needle in haystack for needle in needles)


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    scratch = Path(tempfile.mkdtemp(prefix="runner-script-compat-"))

    report: dict[str, object] = {
        "ok": False,
        "web_base": web_base,
        "api_base": api_base,
        "scripts": {},
        "issues": [],
        "warnings": [],
    }

    try:
        scripts: dict[str, dict[str, object]] = {}
        for script in RUNNER_SCRIPTS:
            url = f"{web_base}/downloads/runner/{script}"
            path = scratch / script
            body = download(url)
            path.write_text(body, encoding="utf-8", newline="")
            item: dict[str, object] = {
                "url": url,
                "bytes": len(body.encode("utf-8")),
                "downloaded": True,
            }
            if "\r\n" in body:
                item["line_endings"] = "crlf"
            else:
                item["line_endings"] = "lf"
            scripts[script] = item

            if script.endswith(".ps1"):
                ok, detail = validate_powershell(path)
                item["syntax_ok"] = ok
                item["syntax_detail"] = detail
                if ok:
                    pass
                elif "PowerShell executable not found" in detail:
                    report["warnings"].append(f"{script} PowerShell syntax check skipped because PowerShell is unavailable on this machine")
                    item["syntax_ok"] = "skipped"
                else:
                    report["issues"].append(f"{script} PowerShell syntax check failed: {detail}")
            elif script.endswith(".sh"):
                ok, detail = validate_bash(path)
                item["syntax_ok"] = ok
                item["syntax_detail"] = detail
                if ok:
                    pass
                elif "bash executable not found" in detail:
                    report["warnings"].append(f"{script} bash -n skipped because bash is unavailable on this machine")
                    item["syntax_ok"] = "skipped"
                else:
                    report["issues"].append(f"{script} bash syntax check failed: {detail}")
            elif script.endswith(".py"):
                ok, detail = validate_python(path)
                item["syntax_ok"] = ok
                item["syntax_detail"] = detail
                if not ok:
                    report["issues"].append(f"{script} Python syntax check failed: {detail}")

            if ("127.0.0.1" in body or "localhost" in body) and script.startswith("connect-ai-collab-runner"):
                report["issues"].append(f"{script} contains local-only host text")
            elif "127.0.0.1" in body or "localhost" in body:
                report["warnings"].append(f"{script} contains a local development default; connect scripts must override it with cloud API")
            if script == "connect-ai-collab-runner.ps1":
                required = ["$Server", "$PairingToken", "$ComputerNodeId", "$Watch", "$SkipCodex", "$SkipClaude"]
                for token in required:
                    if token not in body:
                        report["issues"].append(f"{script} missing {token}")
                if "[switch]$WatchExecuteProviderCli" not in body:
                    report["issues"].append(f"{script} missing explicit provider execution switch")
            if script == "connect-ai-collab-runner.sh":
                required = ["--server", "--pairing-token", "--computer-node-id", "--watch", "--skip-codex", "--skip-claude"]
                for token in required:
                    if token not in body:
                        report["issues"].append(f"{script} missing {token}")
                if 'WATCH_EXECUTE_PROVIDER_CLI="false"' not in body:
                    report["issues"].append(f"{script} does not default provider execution to false")
            if script.endswith(".sh") and not body.startswith("#!/usr/bin/env bash"):
                report["issues"].append(f"{script} missing bash shebang")
            if script.endswith(".ps1") and not contains_any(body, ["param(", "param ("]):
                report["issues"].append(f"{script} missing PowerShell param block")

        report["scripts"] = scripts
        report["ok"] = not report["issues"]
        report_path = output_dir / f"cloud-runner-script-compatibility-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "ok": report["ok"],
            "report_path": str(report_path),
            "issues": report["issues"],
            "warnings": report["warnings"],
        }, ensure_ascii=False))
        return 0 if report["ok"] else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
