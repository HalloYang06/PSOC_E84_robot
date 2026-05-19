from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate cloud-rendered computer onboarding commands for Windows and Linux runners.",
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts"))
    return parser.parse_args()


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else {}


def text(value: object, fallback: str = "") -> str:
    raw = str(value or "").strip()
    return raw or fallback


def cdp_eval(cdp: object, expression: str) -> object:
    result = cdp.send(
        "Runtime.evaluate",
        {"expression": expression, "awaitPromise": True, "returnByValue": True, "userGesture": True},
    )
    if "exceptionDetails" in result:
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1600])
    value = result.get("result", {})
    return value.get("value") if isinstance(value, dict) else None


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 35, interval_seconds: float = 0.35) -> object:
    deadline = time.time() + timeout_seconds
    last: object = None
    while time.time() < deadline:
        try:
            value = cdp_eval(cdp, expression)
            if value:
                return value
            last = value
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(interval_seconds)
    raise RuntimeError(f"Timed out waiting for expression: {expression[:220]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    import base64

    output.write_bytes(base64.b64decode(data))


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    web_base = args.web_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    node_id = f"cloud-command-p0-{stamp[-6:]}"
    runner_id = f"runner-{node_id}"
    node_label = f"Cloud Command P0 {stamp[-6:]}"

    login_payload = request_json(
        f"{api_base}/api/auth/session",
        method="POST",
        payload={"email": args.login_email, "password": args.login_password},
    )
    data = login_payload.get("data") if isinstance(login_payload, dict) else {}
    token = text(data.get("access_token") if isinstance(data, dict) else "")
    user_json = json.dumps(data.get("user") if isinstance(data, dict) else {}, ensure_ascii=True)
    if not token:
        raise RuntimeError("Auth response did not include access_token")

    report: dict[str, object] = {
        "ok": False,
        "project_id": args.project_id,
        "node_id": node_id,
        "runner_id": runner_id,
        "issues": [],
        "commands": {},
    }

    try:
        request_json(
            f"{api_base}/api/collaboration/projects/{quote(args.project_id)}/computer-nodes",
            method="POST",
            token=token,
            payload={
                "id": node_id,
                "label": node_label,
                "status": "offline",
                "connection_kind": "remote",
                "host": "cloud-command-validation",
                "os": "Windows/Linux",
                "metadata": {"source": "cloud_onboarding_command_validation"},
            },
        )
        pairing_payload = request_json(
            f"{api_base}/api/collaboration/projects/{quote(args.project_id)}/computer-nodes/{quote(node_id)}/pairing-token",
            method="POST",
            token=token,
            payload={},
        )
        pairing_token = text((pairing_payload.get("data") or {}).get("token") if isinstance(pairing_payload.get("data"), dict) else "")
        if not pairing_token:
            raise RuntimeError("Pairing token missing from API response")

        port = cdp_helpers.find_free_port()
        profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-cloud-command-edge-"))
        edge_process: subprocess.Popen[bytes] | None = None
        cdp = None
        try:
            edge_process = subprocess.Popen(
                [
                    str(cdp_helpers.find_edge()),
                    "--headless=new",
                    "--disable-gpu",
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            targets = cdp_helpers.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
            if not isinstance(targets, list) or not targets:
                cdp_helpers.request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
                targets = cdp_helpers.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
            page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")), None)
            if not isinstance(page_target, dict):
                raise RuntimeError("No Edge page target available")
            cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
            cdp.send("Page.enable")
            cdp.send("Runtime.enable")
            cdp.send("Network.enable")
            cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False},
            )
            cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{web_base}/", "path": "/", "sameSite": "Lax"})
            cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{web_base}/", "path": "/", "sameSite": "Lax"})
            url = (
                f"{web_base}/projects/{quote(args.project_id)}/2d-upgrade?panel=computers&action=pairing-token"
                f"&computer={quote(node_id)}&pairing_node={quote(node_id)}&pairing_token={quote(pairing_token)}"
            )
            cdp.send("Page.navigate", {"url": url})
            wait_for(
                cdp,
                f"""
                (() => {{
                  return document.readyState === 'complete'
                    && Boolean(document.querySelector(`[data-token-command="computer-pairing"]`))
                    && Boolean(document.querySelector(`[data-token-command="computer-pairing-linux"]`));
                }})()
                """,
                timeout_seconds=45,
            )
            commands = cdp_eval(
                cdp,
                f"""
                (() => {{
                  const read = (selector) => {{
                    const el = document.querySelector(selector);
                    return el ? (el.value || el.innerText || el.textContent || '').trim() : '';
                  }};
                  return {{
                    oneClickWindows: read(`[data-token-command="computer-pairing"]`),
                    oneClickLinux: read(`[data-token-command="computer-pairing-linux"]`),
                    watchWindows: read(`[data-token-command="computer-pairing"]`),
                    watchLinux: read(`[data-token-command="computer-pairing-linux"]`),
                    watchServiceWindows: '',
                    watchServiceLinux: '',
                    tokenWatchWindows: read(`[data-token-command="computer-pairing"]`),
                    tokenWatchLinux: read(`[data-token-command="computer-pairing-linux"]`),
                    pageText: document.body ? document.body.innerText.slice(0, 3000) : '',
                    href: location.href,
                  }};
                }})()
                """,
            )
            if not isinstance(commands, dict):
                raise RuntimeError("Could not read rendered commands from page")
            report["commands"] = commands
            shot = output_dir / f"cloud-computer-onboarding-commands-{stamp}.png"
            screenshot(cdp, shot)
            report["screenshot"] = str(shot)
        finally:
            if cdp is not None:
                try:
                    cdp.close()
                except Exception:  # noqa: BLE001
                    pass
            if edge_process is not None:
                edge_process.terminate()
                try:
                    edge_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    edge_process.kill()
            shutil.rmtree(profile_dir, ignore_errors=True)

        expected_api = api_base
        expected_web = web_base
        checks = {
            "oneClickWindows": ["connect-ai-collab-runner.ps1", expected_web, expected_api, "-Server", "-ProjectId"],
            "oneClickLinux": ["connect-ai-collab-runner.sh", expected_web, expected_api, "--server", "--project-id"],
            "watchWindows": ["connect-ai-collab-runner.ps1", expected_web, expected_api, "-Watch", "-HardwareAccess"],
            "watchLinux": ["connect-ai-collab-runner.sh", expected_web, expected_api, "--watch", "--hardware-access"],
            "tokenWatchWindows": ["connect-ai-collab-runner.ps1", expected_web, expected_api, "-Watch"],
            "tokenWatchLinux": ["connect-ai-collab-runner.sh", expected_web, expected_api, "--watch"],
        }
        issues: list[str] = []
        for key, needles in checks.items():
            command = text(report["commands"].get(key) if isinstance(report.get("commands"), dict) else "")
            if "127.0.0.1" in command or "localhost" in command:
                issues.append(f"{key} contains local-only host")
            for needle in needles:
                if needle not in command:
                    issues.append(f"{key} missing {needle}")
        unsafe_watch_tokens = {
            "watchWindows": "-WatchExecuteProviderCli",
            "watchLinux": "--watch-execute-provider-cli",
            "watchServiceWindows": "-WatchExecuteProviderCli",
            "watchServiceLinux": "--watch-execute-provider-cli",
            "tokenWatchWindows": "-WatchExecuteProviderCli",
            "tokenWatchLinux": "--watch-execute-provider-cli",
        }
        for key, needle in unsafe_watch_tokens.items():
            command = text(report["commands"].get(key) if isinstance(report.get("commands"), dict) else "")
            if needle in command:
                issues.append(f"{key} enables provider CLI execution from first pairing card")
        report["issues"] = issues
        report["ok"] = not issues
        report_path = output_dir / f"cloud-computer-onboarding-commands-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "issues": issues}, ensure_ascii=False))
        return 0 if not issues else 1
    finally:
        try:
            request_json(
                f"{api_base}/api/collaboration/projects/{quote(args.project_id)}/computer-nodes/{quote(node_id)}",
                method="DELETE",
                token=token,
            )
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
