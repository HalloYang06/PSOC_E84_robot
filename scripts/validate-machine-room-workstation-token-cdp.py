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
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
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
    parser = argparse.ArgumentParser(description="Validate workstation adapter token issue/revoke through the real machine-room UI.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=2048)
    parser.add_argument("--viewport-height", type=int, default=1152)
    return parser.parse_args()


def request_json(url: str, *, method: str = "GET", payload: dict[str, object] | None = None, token: str | None = None) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {body[:1200]}") from exc


def api_login(api_base: str, email: str, password: str) -> tuple[str, dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/auth/session",
        method="POST",
        payload={"email": email, "password": password},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get("access_token"):
        raise RuntimeError("API login response did not include access_token")
    return str(data["access_token"]), data.get("user") if isinstance(data.get("user"), dict) else {}


def create_workstation(api_base: str, project_id: str, token: str, payload: dict[str, object]) -> dict[str, object]:
    response = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/thread-workstations",
        method="POST",
        payload=payload,
        token=token,
    )
    data = response.get("data") if isinstance(response, dict) else response
    return data if isinstance(data, dict) else {}


def delete_workstation(api_base: str, project_id: str, workstation_id: str, token: str) -> None:
    request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/thread-workstations/{quote(workstation_id, safe='')}",
        method="DELETE",
        token=token,
    )


def get_adapter_token_status(api_base: str, project_id: str, workstation_id: str, token: str) -> dict[str, object]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/thread-workstations/{quote(workstation_id, safe='')}/adapter-token",
        token=token,
    )
    data = payload.get("data") if isinstance(payload, dict) else payload
    return data if isinstance(data, dict) else {}


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


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 40, interval_seconds: float = 0.25) -> object:
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


def wait_for_machine_room_idle(cdp: object, *, timeout_seconds: float = 60) -> None:
    wait_for(
        cdp,
        """
        (() => {
          const panel = document.querySelector('#project-main-panel');
          if (!panel) return false;
          const busy = panel.getAttribute('data-busy');
          const overlay = panel.querySelector('[role="status"]');
          const overlayText = overlay?.textContent || '';
          return busy !== 'true' &&
            !overlay &&
            !overlayText.includes('正在处理') &&
            !overlayText.includes('正在提交到平台');
        })()
        """,
        timeout_seconds=timeout_seconds,
    )


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def submit_form(cdp: object, form_selector: str) -> None:
    submitted = cdp_eval(
        cdp,
        f"""
        (() => {{
          const form = document.querySelector({json.dumps(form_selector)});
          if (!form) return false;
          form.requestSubmit();
          return true;
        }})()
        """,
    )
    if not submitted:
        raise RuntimeError(f"Could not submit form {form_selector!r}")


def reveal_adapter_command(cdp: object, command_selector: str) -> None:
    revealed = cdp_eval(
        cdp,
        f"""
        (() => {{
          const commandBlock = document.querySelector({json.dumps(command_selector)});
          if (!commandBlock) return false;
          const details = commandBlock.closest('details');
          if (details) details.open = true;
          commandBlock.scrollIntoView({{ block: 'center', inline: 'center' }});
          return true;
        }})()
        """,
    )
    if not revealed:
        raise RuntimeError(f"Could not reveal adapter command block {command_selector!r}")


def read_token_state(cdp: object, command_selector: str, banner_selector: str) -> dict[str, object]:
    result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const commandBlock = document.querySelector({json.dumps(command_selector)});
          const banner = document.querySelector({json.dumps(banner_selector)});
          const commandText = commandBlock?.textContent || commandBlock?.innerText || '';
          const bodyText = document.body?.innerText || '';
          return {{
            commandText,
            hasTokenFlagInBlock: commandText.includes('--token'),
            hasTokenFlagInBody: bodyText.includes('--token'),
            bannerVisible: !!banner && banner.getClientRects().length > 0,
            bannerText: banner?.textContent || '',
          }};
        }})()
        """,
    )
    return result if isinstance(result, dict) else {}


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    workstation_id = f"temp-token-ws-{stamp[-6:]}"
    workstation_name = f"Temp Token Workstation {stamp[-6:]}"
    issue_form_selector = f'[data-workstation-token-issue-form="{workstation_id}"]'
    revoke_form_selector = f'[data-workstation-token-revoke-form="{workstation_id}"]'
    command_selector = f'[data-adapter-command="{workstation_id}"]'
    banner_selector = f'[data-workstation-token-banner="{workstation_id}"]'
    machine_room_path = f"/projects/{args.project_id}?panel=team&tab=machine-room"
    login_url = f"{web_base}/login?returnTo={quote(machine_room_path, safe='')}"

    token, user = api_login(api_base, args.login_email, args.login_password)
    created_workstation = False
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-machine-room-token-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    screenshots: list[str] = []
    report: dict[str, object] = {}

    try:
        create_workstation(
            api_base,
            args.project_id,
            token,
            {
                "id": workstation_id,
                "name": workstation_name,
                "ai_provider_id": "claude",
                "ai_provider": "Claude",
                "status": "active",
                "model": "claude-token-model",
                "responsibility": "Temporary validation for workstation adapter token UI",
                "metadata": {"source_kind": "manual_user_entry", "source": "machine_room_token_validation"},
            },
        )
        created_workstation = True

        edge_process = subprocess.Popen(
            [
                str(cdp_helpers.find_edge()),
                "--headless=new",
                "--disable-gpu",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        targets = cdp_helpers.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        if not isinstance(targets, list) or not targets:
            cdp_helpers.request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
            targets = cdp_helpers.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page"), None)
        if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
            raise RuntimeError("No CDP page target available")

        cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.sock.settimeout(60)
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.viewport_width,
                "height": args.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )

        cdp.send("Page.navigate", {"url": login_url})
        wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('form')")
        shot = output_dir / f"machine-room-token-01-login-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        cdp.send(
            "Network.setCookie",
            {
                "name": "farm_access_token",
                "value": token,
                "domain": "127.0.0.1",
                "path": "/",
                "httpOnly": False,
                "secure": False,
            },
        )
        cdp.send("Page.navigate", {"url": f"{web_base}{machine_room_path}"})
        wait_for(
            cdp,
            f"document.readyState === 'complete' && !!document.querySelector({json.dumps(issue_form_selector)}) && !!document.querySelector({json.dumps(command_selector)})",
            timeout_seconds=60,
        )
        reveal_adapter_command(cdp, command_selector)
        shot = output_dir / f"machine-room-token-02-before-issue-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        submit_form(cdp, issue_form_selector)
        wait_for_machine_room_idle(cdp, timeout_seconds=60)
        wait_for(
            cdp,
            f"window.location.href.includes({json.dumps('adapter_token=')}) && !!document.querySelector({json.dumps(banner_selector)})",
            timeout_seconds=60,
        )
        reveal_adapter_command(cdp, command_selector)
        shot = output_dir / f"machine-room-token-03-issued-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        after_issue_state = read_token_state(cdp, command_selector, banner_selector)
        status_after_issue = get_adapter_token_status(api_base, args.project_id, workstation_id, token)
        if not after_issue_state.get("hasTokenFlagInBlock"):
            raise RuntimeError(f"Adapter command did not show --token after issue: {after_issue_state}")
        if not after_issue_state.get("bannerVisible"):
            raise RuntimeError(f"One-time token banner is not visible after issue: {after_issue_state}")
        if not status_after_issue.get("token_available"):
            raise RuntimeError(f"Adapter token status did not become available after issue: {status_after_issue}")

        submit_form(cdp, revoke_form_selector)
        wait_for_machine_room_idle(cdp, timeout_seconds=60)
        wait_for(
            cdp,
            f"!window.location.href.includes({json.dumps('adapter_token=')})",
            timeout_seconds=60,
        )
        reveal_adapter_command(cdp, command_selector)
        shot = output_dir / f"machine-room-token-04-revoked-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        after_revoke_state = read_token_state(cdp, command_selector, banner_selector)
        status_after_revoke = get_adapter_token_status(api_base, args.project_id, workstation_id, token)
        if after_revoke_state.get("hasTokenFlagInBlock"):
            raise RuntimeError(f"Adapter command still shows --token after revoke: {after_revoke_state}")
        if status_after_revoke.get("token_available"):
            raise RuntimeError(f"Adapter token still reports available after revoke: {status_after_revoke}")

        report = {
            "project_id": args.project_id,
            "login_email": args.login_email,
            "user": user,
            "workstation_id": workstation_id,
            "status_after_issue": status_after_issue,
            "after_issue_state": after_issue_state,
            "status_after_revoke": status_after_revoke,
            "after_revoke_state": after_revoke_state,
            "screenshots": screenshots,
        }
    finally:
        cleanup_state = {"workstation_deleted": False}
        if created_workstation:
            try:
                delete_workstation(api_base, args.project_id, workstation_id, token)
                cleanup_state["workstation_deleted"] = True
            except Exception as exc:  # noqa: BLE001
                cleanup_state["workstation_deleted"] = str(exc)
        report["cleanup"] = cleanup_state
        report_path = output_dir / f"machine-room-token-validation-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if cdp is not None:
            try:
                cdp.close()
            except Exception:  # noqa: BLE001
                pass
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=10)
            except Exception:  # noqa: BLE001
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)

    print(json.dumps({"ok": True, "report": str(report_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
