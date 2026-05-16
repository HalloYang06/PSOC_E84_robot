from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate workbench desktop closeout actions from a real browser.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", default="proj_ai_collab")
    parser.add_argument("--workstation-id", default="platform-npc-1")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/workbench-closeout-actions")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=1100)
    return parser.parse_args()


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    token: str = "",
    workstation_id: str = "",
    timeout: int = 20,
) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if workstation_id:
        headers["X-Workstation-Id"] = workstation_id
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def run_alignment_precheck(args: argparse.Namespace) -> dict[str, object]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "check_web_api_alignment.py"),
        "--web-base",
        args.web_base,
        "--api-base",
        args.api_base,
        "--project-id",
        args.project_id,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    body = completed.stdout.strip() or completed.stderr.strip()
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        data = {"ok": False, "issues": [body or "alignment probe returned no output"]}
    data["exit_code"] = completed.returncode
    return data


def cdp_eval(cdp: object, expression: str) -> object:
    result = cdp.send(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
            "userGesture": True,
        },
    )
    if "exceptionDetails" in result:
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1600])
    value = result.get("result", {})
    return value.get("value") if isinstance(value, dict) else None


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 35, interval_seconds: float = 0.25) -> object:
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
    output.write_bytes(base64.b64decode(data))


def open_browser(args: argparse.Namespace, token: str, user_json: str) -> tuple[object, subprocess.Popen[bytes], Path]:
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-closeout-actions-"))
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
    page_target = next(
        (item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")),
        None,
    )
    if not isinstance(page_target, dict):
        raise RuntimeError("No Edge page target available")
    cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    cdp.send("Network.enable")
    cdp.send(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": args.viewport_width,
            "height": args.viewport_height,
            "deviceScaleFactor": 1,
            "mobile": False,
        },
    )
    origin = args.web_base.rstrip("/")
    if token:
        cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
    if user_json:
        cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
    return cdp, edge_process, profile_dir


def create_closeout_sample(args: argparse.Namespace, token: str) -> dict[str, object]:
    api = args.api_base.rstrip("/")
    command = request_json(
        f"{api}/api/collaboration/messages",
        method="POST",
        token=token,
        payload={
            "project_id": args.project_id,
            "message_type": "agent_command",
            "title": "前端验证：桌面待收口操作",
            "body": "这是一个真实前端点击验证样本：桌面 final 还没有同步，平台应允许用户催办、延长等待或手动收口。",
            "recipient_type": "thread_workstation",
            "recipient_id": args.workstation_id,
            "status": "in_progress",
            "metadata": {
                "validation_sample": True,
                "source": "validate-workbench-closeout-actions-cdp",
                "desktop_closeout_waiting": True,
                "needs_manual_closeout": True,
                "blocked_taxonomy": {
                    "failed": False,
                    "timed_out": True,
                    "auto_closed": False,
                    "retryable": True,
                    "platform_defect": True,
                    "desktop_closeout_waiting": True,
                    "nudge_required": True,
                    "wait_extension_available": True,
                    "manual_close_required": True,
                    "blocked_reason_code": "desktop_final_sync_lag",
                    "blocked_reason_label": "桌面 final 同步滞后，等待催办或手动收口",
                },
            },
        },
    )["data"]
    return command


def click_closeout_action(cdp: object, label: str, source_title: str, source_id: str) -> bool:
    return bool(
        cdp_eval(
            cdp,
            f"""
            (() => {{
              const sourceTitle = {json.dumps(source_title, ensure_ascii=False)};
              const sourceId = {json.dumps(source_id)};
              const label = {json.dumps(label, ensure_ascii=False)};
              const direct = document.querySelector(`[data-message-id="${{CSS.escape(sourceId)}}"]`);
              const candidates = direct ? [direct] : Array.from(document.querySelectorAll('article, div, section'));
              const cards = candidates.filter((node) => {{
                const text = node.textContent || '';
                return text.includes(sourceTitle)
                  && text.includes('催办')
                  && text.includes('延长等待');
              }});
              const root = cards
                .filter((node) => node.querySelectorAll('button').length >= 3)
                .sort((a, b) => a.getBoundingClientRect().height - b.getBoundingClientRect().height)[0];
              if (!root) return false;
              const button = Array.from(root.querySelectorAll('button')).find((item) => {{
                const text = (item.textContent || '').trim();
                return text.includes(label) && !item.disabled;
              }});
              if (!button) return false;
              button.scrollIntoView({{ block: 'center', inline: 'nearest' }});
              button.click();
              return true;
            }})()
            """,
        )
    )


def load_messages(args: argparse.Namespace, token: str) -> list[dict[str, object]]:
    query = urlencode({"project_id": args.project_id, "limit": 600})
    data = request_json(f"{args.api_base.rstrip('/')}/api/collaboration/messages?{query}", token=token).get("data")
    return data if isinstance(data, list) else []


def has_action_receipt(messages: list[dict[str, object]], source_id: str, action: str) -> bool:
    for item in messages:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if str(meta.get("source_message_id") or "") != source_id:
            continue
        if meta.get("desktop_closeout_action") == action:
            return True
    return False


def wait_for_action_receipt(args: argparse.Namespace, token: str, source_id: str, action: str, *, timeout_seconds: float = 20) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if has_action_receipt(load_messages(args, token), source_id, action):
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    alignment = run_alignment_precheck(args)
    token, user_json = cdp_helpers.authenticate(args)
    if not token:
        raise RuntimeError("This validation requires an authenticated user")
    command = create_closeout_sample(args, token)
    command_id = str(command["id"])
    source_title = str(command.get("title") or "")

    cdp = None
    edge_process = None
    profile_dir = None
    clicked_nudge = False
    clicked_extend = False
    try:
        cdp, edge_process, profile_dir = open_browser(args, token, user_json)
        seats = args.workstation_id
        url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}/workbench?seats={seats}"
        cdp.send("Page.navigate", {"url": url})
        wait_for(
            cdp,
            f"""
            (() => {{
              const body = document.body?.innerText || '';
              return location.href.includes('/workbench')
                && body.includes('协同工作台')
                && body.includes({json.dumps(source_title, ensure_ascii=False)})
                && body.includes('催办')
                && body.includes('延长等待');
            }})()
            """,
            timeout_seconds=40,
        )
        screenshot(cdp, output_dir / f"01-closeout-actions-visible-{stamp}.png")

        clicked_nudge = click_closeout_action(cdp, "催办", source_title, command_id)
        if not wait_for_action_receipt(args, token, command_id, "nudge"):
            raise RuntimeError("Timed out waiting for nudge closeout receipt")
        screenshot(cdp, output_dir / f"02-closeout-nudged-{stamp}.png")

        clicked_extend = click_closeout_action(cdp, "延长等待", source_title, command_id)
        if not wait_for_action_receipt(args, token, command_id, "extend_wait"):
            raise RuntimeError("Timed out waiting for extend_wait closeout receipt")
        cdp.send("Runtime.evaluate", {"expression": "location.reload()", "returnByValue": True})
        wait_for(cdp, "document.body && document.body.innerText.includes('延长等待：前端验证')", timeout_seconds=20)
        screenshot(cdp, output_dir / f"03-closeout-extended-{stamp}.png")
    finally:
        if cdp is not None:
            cdp.close()
        if edge_process is not None and edge_process.poll() is None:
            edge_process.kill()
        if profile_dir is not None:
            shutil.rmtree(profile_dir, ignore_errors=True)

    messages = load_messages(args, token)
    command_after = next((item for item in messages if str(item.get("id") or "") == command_id), {})
    failures: list[dict[str, str]] = []
    if not alignment.get("ok"):
        failures.append({"area": "alignment", "reason": "; ".join(alignment.get("issues", [])) or "alignment failed"})
    if not clicked_nudge:
        failures.append({"area": "frontend", "reason": "nudge button was not clickable"})
    if not clicked_extend:
        failures.append({"area": "frontend", "reason": "extend wait button was not clickable"})
    if not has_action_receipt(messages, command_id, "nudge"):
        failures.append({"area": "backend", "reason": "nudge receipt was not created"})
    if not has_action_receipt(messages, command_id, "extend_wait"):
        failures.append({"area": "backend", "reason": "extend_wait receipt was not created"})
    if command_after.get("status") != "in_progress":
        failures.append({"area": "workflow", "reason": f"command status changed unexpectedly: {command_after.get('status')}"})

    report = {
        "verdict": "passed" if not failures else "failed",
        "project_id": args.project_id,
        "workstation_id": args.workstation_id,
        "command_id": command_id,
        "alignment": alignment,
        "clicked": {"nudge": clicked_nudge, "extend_wait": clicked_extend},
        "command_status": command_after.get("status"),
        "screenshots": [
            str(output_dir / f"01-closeout-actions-visible-{stamp}.png"),
            str(output_dir / f"02-closeout-nudged-{stamp}.png"),
            str(output_dir / f"03-closeout-extended-{stamp}.png"),
        ],
        "failures": failures,
    }
    report_path = output_dir / f"workbench-closeout-actions-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "report": str(report_path), "command_id": command_id}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
