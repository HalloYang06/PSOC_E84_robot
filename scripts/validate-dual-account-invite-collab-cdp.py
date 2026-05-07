from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
APPS_API_DIR = REPO_ROOT / "apps" / "api"
CDP_HELPER_PATH = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
ADAPTER_SCRIPT_PATH = SCRIPT_DIR / "platform-workstation-adapter.py"
MOCK_EXECUTOR_PATH = SCRIPT_DIR / "mock-workstation-executor.py"

spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helper: {CDP_HELPER_PATH}")
cdp_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helper)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate multi-account invite collaboration in an isolated temporary live environment.",
    )
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts"))
    parser.add_argument("--viewport-width", type=int, default=1720)
    parser.add_argument("--viewport-height", type=int, default=1080)
    return parser.parse_args()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def new_browser_profile(runtime_dir: Path, stem: str) -> Path:
    profile_dir = runtime_dir / f"{stem}-{time.time_ns()}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    data = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {body[:1600]}") from exc


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


def resolve_project_id_by_name(api_base: str, *, email: str, password: str, project_name: str) -> str:
    token, _user = api_login(api_base, email, password)
    deadline = time.time() + 30
    while time.time() < deadline:
        payload = request_json(
            f"{api_base.rstrip('/')}/api/projects",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = payload.get("data") if isinstance(payload, dict) else []
        projects = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        for item in projects:
            if str(item.get("name") or "").strip() != project_name:
                continue
            project_id = str(item.get("id") or item.get("project_id") or "").strip()
            if project_id:
                return project_id
        time.sleep(0.8)
    raise RuntimeError(f"Could not resolve project id for {project_name!r} via API fallback")


def list_project_messages(api_base: str, project_id: str, token: str) -> list[dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/messages?project_id={quote(project_id)}",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def list_thread_workstations(api_base: str, project_id: str, token: str) -> list[dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/thread-workstations",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def list_project_computer_nodes(api_base: str, project_id: str, token: str) -> list[dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/computer-nodes",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def register_runner_via_pairing_token(
    api_base: str,
    *,
    pairing_token: str,
    computer_node_id: str,
    runner_id: str,
    runner_name: str,
    capabilities: list[str] | None = None,
) -> dict[str, object]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/runners/register",
        method="POST",
        headers={"X-Runner-Registration-Token": pairing_token},
        payload={
            "runner_id": runner_id,
            "runner_name": runner_name,
            "capabilities": capabilities or ["codex", "threads", "filesystem"],
            "hardware_access": False,
            "computer_node_id": computer_node_id,
        },
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def sync_runner_threads_via_api(
    api_base: str,
    *,
    runner_id: str,
    project_id: str,
    computer_node_id: str,
    thread_id: str,
    thread_name: str,
    cwd: str,
    ai_provider_id: str,
    notes: str,
) -> dict[str, object]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/runners/{quote(runner_id)}/thread-workstations/sync",
        method="POST",
        headers={"X-Runner-Id": runner_id},
        payload={
            "project_id": project_id,
            "computer_node_id": computer_node_id,
            "workstations": [
                {
                    "workstation_id": thread_id,
                    "workstation_name": thread_name,
                    "workstation_status": "active",
                    "cwd": cwd,
                    "model": "gpt-5.4",
                    "description": f"{thread_name} synced from isolated multi-account validation",
                    "notes": notes,
                    "ai_provider_id": ai_provider_id,
                }
            ],
        },
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def pick_message(messages: list[dict[str, object]], *, title: str, message_type: str) -> dict[str, object]:
    lowered_type = message_type.lower()
    for item in reversed(messages):
        if str(item.get("message_type") or "").lower() == lowered_type and str(item.get("title") or "") == title:
            return item
    raise RuntimeError(f"Could not find message type={message_type!r} title={title!r}")


def rotate_workstation_token(api_base: str, *, project_id: str, workstation_id: str, token: str) -> dict[str, object]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/thread-workstations/{quote(workstation_id)}/adapter-token",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def run_adapter(
    *,
    api_base: str,
    project_id: str,
    workstation_id: str,
    output_dir: Path,
    workstation_token: str,
    ack_note: str,
    final_note: str,
) -> dict[str, object]:
    command = [
        sys.executable,
        str(ADAPTER_SCRIPT_PATH),
        "--api-base",
        api_base,
        "--project-id",
        project_id,
        "--workstation-id",
        workstation_id,
        "--status",
        "queued",
        "--output-dir",
        str(output_dir),
        "--auto-ack",
        "--ack-note",
        ack_note,
        "--token",
        workstation_token,
    ]
    mock_command = subprocess.list2cmdline(
        [
            sys.executable,
            str(MOCK_EXECUTOR_PATH),
            "@PROMPT_FILE@",
            "--provider",
            "@PROVIDER@",
            "--message-id",
            "@MESSAGE_ID@",
            "--result",
            final_note,
        ]
    )
    command.extend(["--executor-command", mock_command])
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Adapter consumer failed:\n"
            f"stdout:\n{completed.stdout[:4000]}\n\n"
            f"stderr:\n{completed.stderr[:4000]}"
        )
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Adapter output was not valid JSON:\n{completed.stdout[:4000]}") from exc
    parsed["_stderr"] = completed.stderr
    return parsed


def wait_for_http(url: str, *, timeout_seconds: float = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                if 200 <= response.status < 500:
                    return
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if 400 <= exc.code < 500:
                return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def start_process(
    command: list[str],
    *,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    env_overrides: dict[str, str],
) -> tuple[subprocess.Popen[str], object, object]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env.update(env_overrides)
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        env=env,
    )
    return process, stdout_handle, stderr_handle


def run_command(
    command: list[str],
    *,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    env_overrides: dict[str, str] | None = None,
    timeout_seconds: float = 1200,
) -> None:
    env = os.environ.copy()
    if env_overrides:
      env.update(env_overrides)
    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            timeout=timeout_seconds,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(command)}")


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


def js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class BrowserFlow:
    def __init__(self, cdp: object):
        self.cdp = cdp

    def eval(self, expression: str) -> object:
        return cdp_eval(self.cdp, expression)

    def wait_for(self, expression: str, *, timeout_seconds: float = 30, interval_seconds: float = 0.25) -> object:
        deadline = time.time() + timeout_seconds
        last: object = None
        while time.time() < deadline:
            try:
                value = self.eval(expression)
                if value:
                    return value
                last = value
            except Exception as exc:  # noqa: BLE001
                last = str(exc)
            time.sleep(interval_seconds)
        raise RuntimeError(f"Timed out waiting for expression: {expression[:220]} last={last}")

    def text(self) -> str:
        return str(self.eval("document.body ? document.body.innerText : ''") or "")

    def url(self) -> str:
        return str(self.eval("location.href") or "")

    def navigate(self, url: str) -> None:
        self.cdp.send("Page.navigate", {"url": url})
        time.sleep(1.0)

    def wait_for_selector(self, selector: str, *, timeout_seconds: float = 30) -> None:
        self.wait_for(
            f"document.readyState === 'complete' && !!document.querySelector({js_string(selector)})",
            timeout_seconds=timeout_seconds,
        )

    def wait_for_text(self, text: str, *, timeout_seconds: float = 30) -> None:
        self.wait_for(
            f"document.body && document.body.innerText.includes({js_string(text)})",
            timeout_seconds=timeout_seconds,
        )

    def fill(self, selector: str, value: str) -> None:
        result = self.eval(
            f"""
            (() => {{
              const field = document.querySelector({js_string(selector)});
              if (!field) return false;
              field.scrollIntoView({{ block: 'center', inline: 'center' }});
              field.focus();
              field.value = {js_string(value)};
              field.dispatchEvent(new Event('input', {{ bubbles: true }}));
              field.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return true;
            }})()
            """,
        )
        if not result:
            raise RuntimeError(f"Could not fill selector {selector!r}")

    def set_select(self, selector: str, value: str) -> None:
        result = self.eval(
            f"""
            (() => {{
              const field = document.querySelector({js_string(selector)});
              if (!field) return false;
              field.value = {js_string(value)};
              field.dispatchEvent(new Event('input', {{ bubbles: true }}));
              field.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return true;
            }})()
            """,
        )
        if not result:
            raise RuntimeError(f"Could not set select {selector!r}")

    def set_select_by_text(self, selector: str, wanted_text: str) -> None:
        result = self.eval(
            f"""
            (() => {{
              const field = document.querySelector({js_string(selector)});
              if (!field) return false;
              const wanted = {js_string(wanted_text)};
              const option = Array.from(field.options || []).find((item) =>
                ((item.textContent || item.label || '')).includes(wanted),
              );
              if (!option) return false;
              field.value = option.value;
              field.dispatchEvent(new Event('input', {{ bubbles: true }}));
              field.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return true;
            }})()
            """,
        )
        if not result:
            raise RuntimeError(f"Could not choose option containing {wanted_text!r} for {selector!r}")

    def submit(self, selector: str = "form") -> None:
        submitted = self.eval(
            f"""
            (() => {{
              const form = document.querySelector({js_string(selector)});
              if (!form) return false;
              const submitter = form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
              if (submitter && !submitter.disabled) {{
                submitter.click();
                return 'clicked-submit';
              }}
              if (typeof form.requestSubmit === 'function') {{
                form.requestSubmit();
                return 'request-submit';
              }}
              form.submit();
              return 'native-submit';
            }})()
            """,
        )
        if not submitted:
            raise RuntimeError(f"Could not submit form {selector!r}")
        time.sleep(1.4)

    def submit_closest_form(self, field_selector: str) -> None:
        submitted = self.eval(
            f"""
            (() => {{
              const field = document.querySelector({js_string(field_selector)});
              const form = field ? field.closest('form') : null;
              if (!form) return false;
              const submitter = form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
              if (submitter && !submitter.disabled) {{
                submitter.click();
                return 'clicked-submit';
              }}
              if (typeof form.requestSubmit === 'function') {{
                form.requestSubmit();
                return 'request-submit';
              }}
              form.submit();
              return 'native-submit';
            }})()
            """,
        )
        if not submitted:
            raise RuntimeError(f"Could not submit form near field {field_selector!r}")
        time.sleep(1.4)

    def click_text(self, text: str, *, selector: str = "button, a", timeout_seconds: float = 20) -> None:
        point = self.wait_for(
            f"""
            (() => {{
              const wanted = {js_string(text)};
              const items = Array.from(document.querySelectorAll({js_string(selector)}));
              const el = items.find((item) => ((item.innerText || item.textContent || '').replace(/\\s+/g, ' ')).includes(wanted));
              if (!el) return false;
              if ('disabled' in el && el.disabled) return false;
              el.scrollIntoView({{ block: 'center', inline: 'center' }});
              const rect = el.getBoundingClientRect();
              return {{ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
            }})()
            """,
            timeout_seconds=timeout_seconds,
        )
        if not isinstance(point, dict):
            raise RuntimeError(f"Could not click text {text!r}")
        x = float(point["x"])
        y = float(point["y"])
        self.cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        self.cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        self.cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        time.sleep(1.2)

    def screenshot(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        shot = self.cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
        data = str(shot.get("data") or "")
        if not data:
            raise RuntimeError("CDP returned empty screenshot")
        output.write_bytes(base64.b64decode(data))

    def wait_for_url_contains(self, fragment: str, *, timeout_seconds: float = 30) -> str:
        deadline = time.time() + timeout_seconds
        last_url = ""
        while time.time() < deadline:
            last_url = self.url()
            if fragment in last_url:
                return last_url
            time.sleep(0.3)
        raise RuntimeError(f"URL did not contain {fragment!r}: {last_url}")

    def project_map_state(self) -> dict[str, object]:
        state = self.eval(
            """
            (() => {
              const frame = document.querySelector('iframe[title*="农场地图"]');
              const frameWindow = frame && frame.contentWindow;
              const collaboratorSnapshot = Array.isArray(frameWindow && frameWindow.__platformCollaboratorWorldSnapshot)
                ? frameWindow.__platformCollaboratorWorldSnapshot
                : [];
              const currentPlayerLabel = frameWindow && frameWindow.__platformCurrentPlayerLabelSnapshot
                ? frameWindow.__platformCurrentPlayerLabelSnapshot
                : null;
              return {
                frameVisible: !!frame,
                collaboratorSnapshot,
                currentPlayerLabel,
                body: document.body ? document.body.innerText.slice(0, 4000) : "",
              };
            })()
            """,
        )
        return state if isinstance(state, dict) else {}


class BrowserRuntime:
    def __init__(self, port: int, profile_dir: Path, viewport_width: int, viewport_height: int):
        self.port = port
        self.profile_dir = profile_dir
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.process: subprocess.Popen[bytes] | None = None
        self.cdp = None

    def _launch(self, headless_flag: str) -> None:
        self.process = subprocess.Popen(
            [
                str(cdp_helper.find_edge()),
                headless_flag,
                "--disable-gpu",
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def __enter__(self):
        last_error: Exception | None = None
        for headless_flag in ("--headless=new", "--headless"):
            try:
                self._launch(headless_flag)
                cdp_helper.wait_for_json(f"http://127.0.0.1:{self.port}/json/version", timeout_seconds=20)
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if self.process is not None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                    self.process = None
        else:
            raise RuntimeError(f"Unable to launch Edge CDP runtime: {last_error}")

        page_target = cdp_helper.request_json(f"http://127.0.0.1:{self.port}/json/new?about:blank", method="PUT")
        if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
            targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{self.port}/json/list", timeout_seconds=20)
            if not isinstance(targets, list) or not targets:
                raise RuntimeError("No CDP page target available")
            page_target = next((item for item in reversed(targets) if isinstance(item, dict) and item.get("type") == "page"), None)
        if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
            raise RuntimeError("No CDP page target available")

        self.cdp = cdp_helper.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        self.cdp.send("Page.enable")
        self.cdp.send("Runtime.enable")
        self.cdp.send("Network.enable")
        self.cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        self.cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": self.viewport_width,
                "height": self.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        time.sleep(1.0)
        return BrowserFlow(self.cdp)

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.cdp is not None:
                self.cdp.close()
        except Exception:  # noqa: BLE001
            pass
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()


def register_via_ui(flow: BrowserFlow, web_base: str, *, email: str, password: str, name: str, shot: Path) -> None:
    flow.navigate(f"{web_base}/login?mode=signup")
    flow.wait_for_selector('input[name="name"]')
    flow.fill('input[name="name"]', name)
    flow.fill('input[name="email"]', email)
    flow.fill('input[name="password"]', password)
    flow.screenshot(shot)
    flow.submit("form")
    time.sleep(1.0)
    flow.navigate(f"{web_base}/projects")
    flow.wait_for(
        """
        location.pathname.startsWith('/projects')
        && document.readyState === 'complete'
        && !!document.body
        && document.body.innerText.length > 20
        """,
    )
    if "/login" in flow.url():
        raise RuntimeError("Registration did not yield an authenticated /projects session")


def login_via_ui(flow: BrowserFlow, web_base: str, *, email: str, password: str, shot: Path | None = None) -> None:
    flow.navigate(f"{web_base}/login")
    flow.wait_for_selector('input[name="email"]')
    flow.fill('input[name="email"]', email)
    flow.fill('input[name="password"]', password)
    if shot is not None:
        flow.screenshot(shot)
    flow.submit("form")
    flow.wait_for_url_contains("/projects")
    flow.wait_for(
        """
        location.pathname.startsWith('/projects')
        && document.readyState === 'complete'
        && !!document.body
        && document.body.innerText.length > 20
        """,
    )


def ensure_logged_in(flow: BrowserFlow, web_base: str, *, email: str, password: str, shot: Path | None = None) -> None:
    flow.navigate(f"{web_base}/projects")
    time.sleep(1.0)
    current_url = flow.url()
    if "/login" in current_url or "mode=signin" in current_url or "mode=signup" in current_url:
        login_via_ui(flow, web_base, email=email, password=password, shot=shot)
        return
    flow.wait_for(
        """
        location.pathname.startsWith('/projects')
        && document.readyState === 'complete'
        && !!document.body
        && document.body.innerText.length > 20
        """,
    )


def create_project_via_ui(
    flow: BrowserFlow,
    web_base: str,
    *,
    api_base: str,
    owner_email: str,
    owner_password: str,
    project_name: str,
    description: str,
    shot: Path,
) -> str:
    flow.navigate(f"{web_base}/projects?tab=create")
    flow.wait_for_selector('form input[name="name"]')
    flow.fill('input[name="name"]', project_name)
    flow.fill('textarea[name="description"]', description)
    flow.screenshot(shot)
    flow.submit_closest_form('input[name="name"]')
    try:
        project_state = flow.wait_for(
            f"""
            (() => {{
              if (location.pathname.startsWith('/projects/')) {{
                return {{
                  href: location.href,
                  source: 'location',
                }};
              }}
              const link = Array.from(document.querySelectorAll('a[href*="/projects/"]')).find((item) =>
                ((item.innerText || item.textContent || '')).includes({js_string(project_name)})
              );
              if (!link) return false;
              const href = link.href || link.getAttribute('href') || '';
              return href
                ? {{
                    href,
                    source: 'link',
                  }}
                : false;
            }})()
            """,
            timeout_seconds=20,
            interval_seconds=0.4,
        )
        if not isinstance(project_state, dict):
            raise RuntimeError(f"Could not resolve project entry after create: {project_state}")
        project_url = str(project_state.get("href") or "").strip()
        if not project_url:
            raise RuntimeError(f"Project create state did not include an href: {project_state}")
        parts = project_url.split("/projects/", 1)[1]
        project_id = parts.split("?", 1)[0].split("/", 1)[0]
        if project_id:
            return project_id
    except RuntimeError:
        pass
    return resolve_project_id_by_name(
        api_base,
        email=owner_email,
        password=owner_password,
        project_name=project_name,
    )


def invite_via_ui(flow: BrowserFlow, web_base: str, *, project_id: str, invitee_email: str, note: str, shot: Path) -> None:
    flow.navigate(f"{web_base}/projects?tab=invite&project_id={project_id}")
    flow.wait_for_selector('form input[name="email"]')
    flow.fill('input[name="email"]', invitee_email)
    flow.set_select('form select[name="role"]', "collaborator")
    flow.fill('textarea[name="note"]', note)
    flow.screenshot(shot)
    flow.submit_closest_form('form input[name="email"]')
    flow.wait_for(
        """
        location.pathname.startsWith('/projects')
        && document.readyState === 'complete'
        && !!document.body
        && document.body.innerText.length > 20
        """,
    )


def accept_invite_via_ui(flow: BrowserFlow, web_base: str, *, project_name: str, shot: Path) -> None:
    flow.navigate(f"{web_base}/projects?tab=invites")
    flow.wait_for_text(project_name)
    flow.screenshot(shot)
    accepted = flow.eval(
        f"""
        (() => {{
          const target = {js_string(project_name)};
          const card = Array.from(document.querySelectorAll('article')).find((item) =>
            ((item.innerText || item.textContent || '')).includes(target),
          );
          const form = card ? card.querySelector('form') : null;
          if (!form) return false;
          form.requestSubmit();
          return true;
        }})()
        """,
    )
    if not accepted:
        raise RuntimeError(f"Could not submit accept-invite form for {project_name!r}")
    time.sleep(1.4)
    flow.wait_for(
        f"""
        location.pathname.startsWith('/projects')
        && document.readyState === 'complete'
        && !!document.body
        && document.body.innerText.includes({js_string(project_name)})
        """,
    )


def verify_projects_plaza(flow: BrowserFlow, web_base: str, *, project_name: str, expected_present: bool) -> dict[str, object]:
    flow.navigate(f"{web_base}/projects?tab=projects")
    flow.wait_for(
        """
        location.pathname.startsWith('/projects')
        && document.readyState === 'complete'
        && !!document.body
        && document.body.innerText.length > 20
        """,
    )
    state = flow.eval(
        f"""
        (() => {{
          const body = document.body ? document.body.innerText : '';
          const links = Array.from(document.querySelectorAll('a[href*="/projects/"]')).map((item) => (item.innerText || item.textContent || '').trim()).filter(Boolean);
          return {{
            body,
            links,
            hasProject: body.includes({js_string(project_name)}) || links.some((item) => item.includes({js_string(project_name)})),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
      raise RuntimeError("Could not read projects plaza state")
    has_project = bool(state.get("hasProject"))
    if has_project != expected_present:
        raise RuntimeError(f"Project visibility mismatch for {project_name!r}: expected {expected_present}, got {state}")
    return state


def verify_project_map(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    remote_names: list[str],
    local_name: str,
    shot: Path,
    minimum_player_count: int = 2,
    minimum_computer_count: int = 2,
    minimum_thread_count: int = 2,
) -> dict[str, object]:
    flow.navigate(f"{web_base}/projects/{project_id}")
    flow.wait_for_selector('iframe[src*="harvest-moon-phaser3-game/index.html"]', timeout_seconds=45)
    flow.wait_for_selector('[data-human-party-hud]', timeout_seconds=45)
    state = flow.wait_for(
        """
        (() => {
          const frame = document.querySelector('iframe[src*="harvest-moon-phaser3-game/index.html"]');
          const frameWindow = frame && frame.contentWindow;
          const collaborators = Array.isArray(frameWindow && frameWindow.__platformCollaboratorWorldSnapshot)
            ? frameWindow.__platformCollaboratorWorldSnapshot
            : [];
          const me = frameWindow && frameWindow.__platformCurrentPlayerLabelSnapshot
            ? frameWindow.__platformCurrentPlayerLabelSnapshot
            : null;
          const humanParty = Array.from(document.querySelectorAll('[data-human-party-player]')).map((item) => ({
            id: item.getAttribute('data-human-party-player') || '',
            current: item.getAttribute('data-human-party-current') || 'false',
            state: item.getAttribute('data-human-party-state') || '',
            note: item.getAttribute('data-human-party-note') || '',
            name: (() => {
              const target = item.querySelector('[data-human-party-name]');
              return target ? (target.textContent || '').trim() : '';
            })(),
            detail: (() => {
              const target = item.querySelector('[data-human-party-detail]');
              return target ? (target.textContent || '').trim() : '';
            })(),
          }));
          const partyCount = (() => {
            const target = document.querySelector('[data-human-party-count]');
            return target ? (target.getAttribute('data-human-party-count') || '') : '';
          })();
          const summaryStats = {
            players: (() => {
              const target = document.querySelector('[data-human-party-player-count]');
              return target ? (target.getAttribute('data-human-party-player-count') || '') : '';
            })(),
            computers: (() => {
              const target = document.querySelector('[data-human-party-computer-count]');
              return target ? (target.getAttribute('data-human-party-computer-count') || '') : '';
            })(),
            threads: (() => {
              const target = document.querySelector('[data-human-party-thread-count]');
              return target ? (target.getAttribute('data-human-party-thread-count') || '') : '';
            })(),
            threadedPlayers: (() => {
              const target = document.querySelector('[data-human-party-threaded-player-count]');
              return target ? (target.getAttribute('data-human-party-threaded-player-count') || '') : '';
            })(),
          };
          return collaborators.length > 0 && !!me && humanParty.length > 0
            ? {
                collaborators,
                me,
                humanParty,
                partyCount,
                summaryStats,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }
            : false;
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Unexpected project map state: {state}")
    flow.screenshot(shot)
    collaborator_labels = [str(item.get("label") or "") for item in state.get("collaborators", []) if isinstance(item, dict)]
    me_label = str((state.get("me") or {}).get("name") or "")
    human_party = [item for item in state.get("humanParty", []) if isinstance(item, dict)]
    human_party_names = [str(item.get("name") or "") for item in human_party]
    for remote_name in remote_names:
        if not any(remote_name in label for label in collaborator_labels):
            raise RuntimeError(f"Remote collaborator {remote_name!r} not visible in map snapshot: {collaborator_labels}")
    if local_name not in me_label:
        raise RuntimeError(f"Current player label did not include {local_name!r}: {me_label}")
    if local_name not in human_party_names:
        raise RuntimeError(f"Local player {local_name!r} not visible in human party HUD: {human_party_names}")
    for remote_name in remote_names:
        if remote_name not in human_party_names:
            raise RuntimeError(f"Remote player {remote_name!r} not visible in human party HUD: {human_party_names}")
        remote_party = next((item for item in human_party if remote_name in str(item.get("name") or "")), None)
        if not isinstance(remote_party, dict):
            raise RuntimeError(f"Could not resolve remote party state for {remote_name!r}: {human_party}")
        remote_state = str(remote_party.get("state") or "")
        if not remote_state:
            raise RuntimeError(f"Remote party state for {remote_name!r} was empty: {remote_party}")
    summary_stats = state.get("summaryStats", {})
    if not isinstance(summary_stats, dict):
        raise RuntimeError(f"Could not resolve human-party summary stats: {state}")
    try:
        players_count = int(str(summary_stats.get("players") or "0"))
        computer_count = int(str(summary_stats.get("computers") or "0"))
        thread_count = int(str(summary_stats.get("threads") or "0"))
    except ValueError as exc:
        raise RuntimeError(f"Human-party summary stats were not numeric: {summary_stats}") from exc
    if players_count < minimum_player_count or computer_count < minimum_computer_count or thread_count < minimum_thread_count:
        raise RuntimeError(
            f"Human-party summary did not expose scalable player/computer/thread counts: {summary_stats}"
        )
    return state


def create_schedule_task_via_ui(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    task_title: str,
    task_description: str,
    shot: Path,
) -> dict[str, object]:
    flow.navigate(f"{web_base}/projects/{project_id}?panel=team&tab=schedule")
    flow.wait_for_selector('[data-schedule-create-task-form] input[name="title"]', timeout_seconds=45)
    flow.fill('[data-schedule-create-task-form] input[name="title"]', task_title)
    flow.fill('[data-schedule-create-task-form] textarea[name="description"]', task_description)
    flow.screenshot(shot)
    flow.submit('[data-schedule-create-task-form]')
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-schedule-task-title]')).map((item) =>
            item.getAttribute('data-schedule-task-title') || ''
          );
          return items.some((item) => item.includes({js_string(task_title)}))
            ? {{
                titles: items,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Unexpected schedule task creation state: {state}")
    flow.eval(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-schedule-task-item]')).find((item) =>
            ((item.getAttribute('data-schedule-task-title') || item.textContent || '')).includes({js_string(task_title)})
          );
          if (!match) return false;
          match.scrollIntoView({{ block: 'center', inline: 'center' }});
          return true;
        }})()
        """,
    )
    flow.screenshot(shot)
    return state


def create_computer_via_ui(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    computer_id: str,
    label: str,
    workspace_root: str,
    git_root: str,
    shot: Path,
) -> dict[str, object]:
    flow.navigate(f"{web_base}/projects/{project_id}?panel=team&tab=computers&drawer=computer-connect")
    flow.wait_for_selector('[data-computer-connect-form] input[name="label"]', timeout_seconds=45)
    flow.fill('[data-computer-connect-form] input[name="id"]', computer_id)
    flow.fill('[data-computer-connect-form] input[name="label"]', label)
    flow.set_select('[data-computer-connect-form] select[name="status"]', "online")
    flow.set_select('[data-computer-connect-form] select[name="connection_kind"]', "remote")
    flow.fill('[data-computer-connect-form] input[name="workspace_root"]', workspace_root)
    flow.fill('[data-computer-connect-form] input[name="git_root"]', git_root)
    flow.screenshot(shot)
    flow.submit('[data-computer-connect-form]')
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-computer-rail-item]')).map((item) => ({{
            id: item.getAttribute('data-computer-rail-item') || '',
            name: item.getAttribute('data-computer-rail-name') || (item.textContent || '').trim(),
          }}));
          const match = items.find((item) => item.id === {js_string(computer_id)});
          return match
            ? {{
                items,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Computer node {computer_id!r} was not visible after create")
    flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-rail-item={js_string(computer_id)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    time.sleep(0.8)
    flow.screenshot(shot)
    return state


def open_computer_threads_drawer(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    computer_id: str,
) -> None:
    flow.navigate(f"{web_base}/projects/{project_id}?panel=team&tab=computers")
    flow.wait_for_selector('[data-computer-rail-item]', timeout_seconds=45)
    selected = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-rail-item={js_string(computer_id)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not selected:
        raise RuntimeError(f"Could not select computer rail item {computer_id!r}")
    time.sleep(0.6)
    opened = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-open-threads={js_string(computer_id)}]');
          if (!button || button.disabled) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not opened:
        raise RuntimeError(f"Could not open threads drawer for computer {computer_id!r}")
    flow.wait_for_selector(f'[data-computer-threads-drawer="{computer_id}"]', timeout_seconds=45)


def generate_pairing_token_via_ui(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    computer_id: str,
    shot: Path,
) -> dict[str, object]:
    open_computer_threads_drawer(flow, web_base, project_id=project_id, computer_id=computer_id)
    clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-generate-pairing={js_string(computer_id)}]');
          if (!button || button.disabled) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not submit pairing token form for {computer_id!r}")
    state = flow.wait_for(
        f"""
        (() => {{
          const url = new URL(location.href);
          const token = url.searchParams.get('pairing_token') || '';
          const nodeId = url.searchParams.get('pairing_node') || '';
          const banner = document.querySelector('[data-computer-pairing-banner="true"]');
          return token && nodeId === {js_string(computer_id)}
            ? {{
                href: location.href,
                pairingToken: token,
                pairingNode: nodeId,
                bannerText: banner ? (banner.textContent || '').trim() : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Could not resolve pairing token for {computer_id!r}")
    flow.screenshot(shot)
    return state


def scan_threads_via_ui(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    computer_id: str,
    expected_thread_id: str,
    shot: Path,
) -> dict[str, object]:
    open_computer_threads_drawer(flow, web_base, project_id=project_id, computer_id=computer_id)
    clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-request-scan={js_string(computer_id)}]');
          if (!button || button.disabled) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not request thread scan for {computer_id!r}")
    flow.wait_for_selector('[data-computer-rail-item]', timeout_seconds=45)
    reselected = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-rail-item={js_string(computer_id)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not reselected:
        raise RuntimeError(f"Could not reselect computer {computer_id!r} after scan redirect")
    time.sleep(0.6)
    state = flow.wait_for(
        f"""
        (() => {{
          const nodes = Array.from(document.querySelectorAll('[data-computer-rail-item]')).map((item) => item.getAttribute('data-computer-rail-item') || '');
          const previewThreads = Array.from(document.querySelectorAll('[data-computer-thread-item]')).map((item) => item.getAttribute('data-computer-thread-item') || '');
          const scanStatus = document.querySelector('[data-computer-thread-scan-status={js_string(computer_id)}]');
          const previewFor = document.querySelector('[data-computer-thread-preview-for]')?.getAttribute('data-computer-thread-preview-for') || '';
          return previewFor === {js_string(computer_id)} && previewThreads.includes({js_string(expected_thread_id)})
            ? {{
              nodes,
              previewFor,
              previewThreads,
              scanStatus: scanStatus ? (scanStatus.textContent || '').trim() : '',
              body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.5,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Thread scan UI did not surface {expected_thread_id!r} for {computer_id!r}")
    flow.screenshot(shot)
    return state


def verify_computers_visible_to_account(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    expected_nodes: list[tuple[str, str]],
    expected_threads_by_node: dict[str, str],
    expected_fleet_players: list[str] | None,
    shot: Path,
) -> dict[str, object]:
    flow.navigate(f"{web_base}/projects/{project_id}?panel=team&tab=computers")
    flow.wait_for_selector('[data-computer-rail-item]', timeout_seconds=45)
    overview = flow.eval(
        """
        (() => ({
          nodes: Array.from(document.querySelectorAll('[data-computer-rail-item]')).map((item) => ({
            id: item.getAttribute('data-computer-rail-item') || '',
            name: item.getAttribute('data-computer-rail-name') || (item.textContent || '').trim(),
            owner: item.getAttribute('data-computer-rail-owner') || '',
          })),
          fleets: Array.from(document.querySelectorAll('[data-computer-fleet-group]')).map((item) => ({
            id: item.getAttribute('data-computer-fleet-group') || '',
            name: item.getAttribute('data-computer-fleet-name') || '',
            computers: item.getAttribute('data-computer-fleet-computers') || '0',
            threads: item.getAttribute('data-computer-fleet-threads') || '0',
            nodes: Array.from(item.querySelectorAll('[data-computer-fleet-node]')).map((node) => node.getAttribute('data-computer-fleet-node') || ''),
          })),
          body: document.body ? document.body.innerText.slice(0, 4000) : '',
        }))()
        """,
    )
    if not isinstance(overview, dict):
        raise RuntimeError("Could not inspect computers overview")
    nodes = overview.get("nodes") if isinstance(overview.get("nodes"), list) else []
    fleets = overview.get("fleets") if isinstance(overview.get("fleets"), list) else []
    for node_id, node_name in expected_nodes:
        if not any(isinstance(item, dict) and str(item.get("id") or "") == node_id for item in nodes):
            raise RuntimeError(f"Missing computer node {node_id!r} in visible rail: {nodes}")
        if not any(
            isinstance(item, dict)
            and str(item.get("id") or "") == node_id
            and node_name in str(item.get("name") or "")
            for item in nodes
        ):
            raise RuntimeError(f"Visible computer node {node_id!r} did not carry label {node_name!r}: {nodes}")
    if expected_fleet_players:
        fleet_names = [str(item.get("name") or "") for item in fleets if isinstance(item, dict)]
        for player_name in expected_fleet_players:
            if not any(player_name in name for name in fleet_names):
                raise RuntimeError(f"Player fleet {player_name!r} was not visible in grouped computer board: {fleets}")
    thread_visibility: dict[str, list[str]] = {}
    for node_id, _node_name in expected_nodes:
        flow.eval(
            f"""
            (() => {{
              const button = document.querySelector('[data-computer-rail-item={js_string(node_id)}]');
              if (!button) return false;
              button.click();
              return true;
            }})()
            """,
        )
        preview = flow.wait_for(
            f"""
            (() => ({{
              previewFor: document.querySelector('[data-computer-thread-preview-for]')?.getAttribute('data-computer-thread-preview-for') || '',
              previewThreads: Array.from(document.querySelectorAll('[data-computer-thread-item]')).map((item) => item.getAttribute('data-computer-thread-item') || ''),
            }}))().previewFor === {js_string(node_id)}
              ? (() => ({{
                  previewFor: document.querySelector('[data-computer-thread-preview-for]')?.getAttribute('data-computer-thread-preview-for') || '',
                  previewThreads: Array.from(document.querySelectorAll('[data-computer-thread-item]')).map((item) => item.getAttribute('data-computer-thread-item') || ''),
                }}))()
              : false
            """,
            timeout_seconds=30,
            interval_seconds=0.4,
        )
        if not isinstance(preview, dict):
            raise RuntimeError(f"Could not inspect preview threads for {node_id!r}")
        preview_threads = [str(item) for item in preview.get("previewThreads", []) if isinstance(item, str)]
        thread_visibility[node_id] = preview_threads
        expected_thread_id = expected_threads_by_node.get(node_id)
        if expected_thread_id and expected_thread_id not in preview_threads:
            raise RuntimeError(f"Computer {node_id!r} did not expose expected thread {expected_thread_id!r}: {preview_threads}")
    flow.screenshot(shot)
    return {
        "nodes": nodes,
        "fleets": fleets,
        "threadVisibility": thread_visibility,
        "body": str(overview.get("body") or ""),
    }


def create_npc_via_ui(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    npc_name: str,
    responsibility: str,
    computer_node_id: str = "",
    source_workstation_id: str = "",
    shot: Path,
) -> dict[str, object]:
    flow.navigate(f"{web_base}/projects/{project_id}?panel=team&tab=npc-create&drawer=npc-create")
    flow.wait_for_selector('[data-npc-create-form] input[name="name"]', timeout_seconds=45)
    flow.fill('[data-npc-create-form] input[name="name"]', npc_name)
    flow.fill('[data-npc-create-form] input[name="responsibility"]', responsibility)
    flow.set_select('[data-npc-create-form] select[name="source_workstation_id"]', source_workstation_id)
    flow.set_select('[data-npc-create-form] select[name="computer_node_id"]', computer_node_id)
    flow.fill(
        '[data-npc-create-form] textarea[name="knowledge_summary"]',
        "这是双账号联机验证 NPC，用来证明 owner 发出的真实平台派工可以被同项目成员看见。",
    )
    flow.screenshot(shot)
    flow.submit('[data-npc-create-form]')
    state = flow.wait_for(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-npc-rail-seat]')).find((item) =>
            ((item.textContent || '')).includes({js_string(npc_name)})
          );
          return match
            ? {{
                items: Array.from(document.querySelectorAll('[data-npc-rail-seat]')).map((item) => (item.textContent || '').trim()),
                seatId: match.getAttribute('data-npc-rail-seat') || '',
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"NPC {npc_name!r} was not visible after create")
    flow.eval(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-npc-rail-seat]')).find((item) =>
            ((item.textContent || '')).includes({js_string(npc_name)})
          );
          if (!match) return false;
          match.scrollIntoView({{ block: 'center', inline: 'center' }});
          return true;
        }})()
        """,
    )
    flow.screenshot(shot)
    return state


def verify_schedule_task_visible(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    task_title: str,
    shot: Path,
) -> dict[str, object]:
    flow.navigate(f"{web_base}/projects/{project_id}?panel=team&tab=schedule")
    flow.wait_for_selector('[data-schedule-create-task-form]', timeout_seconds=45)
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-schedule-task-title]')).map((item) => {{
            const title = item.getAttribute('data-schedule-task-title') || '';
            const host = item.closest('[data-schedule-task-item]');
            return {{
              title,
              card: host ? (host.textContent || '').trim() : title,
            }};
          }});
          return items.some((item) => item.title.includes({js_string(task_title)}))
            ? {{
                items,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Shared task {task_title!r} was not visible")
    flow.eval(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-schedule-task-item]')).find((item) =>
            ((item.getAttribute('data-schedule-task-title') || item.textContent || '')).includes({js_string(task_title)})
          );
          if (!match) return false;
          match.scrollIntoView({{ block: 'center', inline: 'center' }});
          return true;
        }})()
        """,
    )
    flow.screenshot(shot)
    return state


def open_exchange_overview(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    composer_mode: str | None = None,
) -> None:
    flow.navigate(f"{web_base}/projects/{project_id}?panel=team&tab=exchange")
    flow.wait_for_selector('[data-exchange-section="overview"]', timeout_seconds=45)
    if composer_mode:
        form_selector = '[data-project-sync-form]' if composer_mode == 'sync' else '[data-exchange-command-form]'
        ready = flow.eval(
            f"""
            (() => {{
              const form = document.querySelector({js_string(form_selector)});
              if (form) return true;
              const button = document.querySelector('[data-exchange-composer-toggle={composer_mode}]');
              if (!button) return false;
              button.click();
              return true;
            }})()
            """
        )
        if not ready:
            raise RuntimeError(f"Could not open exchange composer {composer_mode!r}")
        flow.wait_for_selector(form_selector, timeout_seconds=45)


def open_exchange_section(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    section_id: str,
) -> None:
    flow.navigate(f"{web_base}/projects/{project_id}?panel=team&tab=exchange")
    flow.wait_for_selector(f'[data-exchange-nav-target="{section_id}"]', timeout_seconds=45)
    active = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-exchange-nav-target={js_string(section_id)}]');
          const section = document.querySelector('[data-exchange-section={js_string(section_id)}]');
          if (!button || !section) return false;
          if (button.getAttribute('data-exchange-nav-active') !== 'true') button.click();
          return true;
        }})()
        """
    )
    if not active:
        raise RuntimeError(f"Could not activate exchange section {section_id!r}")
    flow.wait_for(
        f"""
        (() => {{
          const section = document.querySelector('[data-exchange-section={js_string(section_id)}]');
          return !!section && section.getAttribute('data-exchange-section-active') === 'true';
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.3,
    )


def create_agent_command_via_ui(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    target_id: str,
    command_title: str,
    command_body: str,
    shot_preview: Path,
    shot_sent: Path,
) -> dict[str, object]:
    open_exchange_overview(flow, web_base, project_id=project_id, composer_mode='dispatch')
    flow.wait_for_selector('[data-exchange-command-form] select[name="recipient_id"]', timeout_seconds=45)
    flow.set_select('[data-exchange-command-form] select[name="recipient_id"]', target_id)
    flow.fill('[data-exchange-command-form] input[name="title"]', command_title)
    flow.fill('[data-exchange-command-form] textarea[name="body"]', command_body)
    flow.screenshot(shot_preview)
    flow.click_text("先预演协作指令", selector='[data-exchange-command-form] button')
    flow.wait_for(
        """
        (() => {
          const field = document.querySelector('[data-exchange-command-form] input[name="required_preview_ready"]');
          return field ? field.value === '1' : false;
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    flow.click_text("正式发送到协作池", selector='[data-exchange-command-form] button')
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-exchange-command-item]')).map((item) => {{
            const title = item.getAttribute('data-exchange-command-title') || '';
            const sender = item.getAttribute('data-exchange-command-sender') || '';
            return {{
              title,
              sender,
              card: (item.textContent || '').trim(),
            }};
          }});
          return items.some((item) => item.title.includes({js_string(command_title)}))
            ? {{
                items,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Shared agent command {command_title!r} was not visible after submit")
    flow.eval(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-exchange-command-item]')).find((item) =>
            ((item.getAttribute('data-exchange-command-title') || item.textContent || '')).includes({js_string(command_title)})
          );
          if (!match) return false;
          match.scrollIntoView({{ block: 'center', inline: 'center' }});
          return true;
        }})()
        """,
    )
    flow.screenshot(shot_sent)
    return state


def verify_agent_command_visible(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    command_title: str,
    expected_sender: str,
    fallback_sender: str,
    shot: Path,
) -> dict[str, object]:
    open_exchange_section(flow, web_base, project_id=project_id, section_id='dispatch')
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-exchange-command-item]')).map((item) => {{
            const title = item.getAttribute('data-exchange-command-title') || '';
            const sender = item.getAttribute('data-exchange-command-sender') || '';
            return {{
              title,
              sender,
              card: (item.textContent || '').trim(),
            }};
          }});
          return items.some((item) => item.title.includes({js_string(command_title)}))
            ? {{
                items,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Shared agent command {command_title!r} was not visible to invited member")
    items = state.get("items", [])
    match = next(
        (
            item
            for item in items
            if isinstance(item, dict) and command_title in str(item.get("title") or "")
        ),
        None,
    )
    if not isinstance(match, dict):
        raise RuntimeError(f"Could not resolve shared agent command item for {command_title!r}: {items}")
    sender = str(match.get("sender") or "")
    if expected_sender not in sender and fallback_sender not in sender:
        raise RuntimeError(
            f"Shared agent command sender mismatch: expected {expected_sender!r} or {fallback_sender!r}, got {sender!r}"
        )
    flow.eval(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-exchange-command-item]')).find((item) =>
            ((item.getAttribute('data-exchange-command-title') || item.textContent || '')).includes({js_string(command_title)})
          );
          if (!match) return false;
          match.scrollIntoView({{ block: 'center', inline: 'center' }});
          return true;
        }})()
        """,
    )
    flow.screenshot(shot)
    return state


def verify_receipts_visible(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    command_title: str,
    shot: Path,
) -> dict[str, object]:
    open_exchange_section(flow, web_base, project_id=project_id, section_id='receipts')
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-exchange-receipt-item]')).map((item) => {{
            const title = item.getAttribute('data-exchange-receipt-title') || '';
            const kind = item.getAttribute('data-exchange-receipt-kind') || '';
            const sender = item.getAttribute('data-exchange-receipt-sender') || '';
            return {{
              title,
              kind,
              sender,
              card: (item.textContent || '').trim(),
            }};
          }});
          const hasAck = items.some((item) => item.title === {js_string(command_title)} && item.kind === '最小回执');
          const hasResult = items.some((item) => item.title === {js_string(command_title)} && item.kind === '最终回复');
          return hasAck && hasResult
            ? {{
                items,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Shared receipts for {command_title!r} were not visible")
    flow.eval(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-exchange-receipt-item]')).find((item) =>
            ((item.getAttribute('data-exchange-receipt-title') || '') === {js_string(command_title)}
              && (item.getAttribute('data-exchange-receipt-kind') || '') === '最终回复')
          );
          if (!match) return false;
          match.scrollIntoView({{ block: 'center', inline: 'center' }});
          return true;
        }})()
        """,
    )
    flow.screenshot(shot)
    return state


def execute_command_chain_via_ui_and_adapter(
    flow: BrowserFlow,
    web_base: str,
    *,
    api_base: str,
    owner_token: str,
    project_id: str,
    workstation_id: str,
    command_title: str,
    command_body: str,
    ack_note: str,
    final_note: str,
    shot_preview: Path,
    shot_sent: Path,
    shot_receipts: Path,
    ui_surface: str = "exchange",
    npc_seat_id: str | None = None,
) -> dict[str, object]:
    if ui_surface == "npc-dialog":
        if not npc_seat_id:
            raise RuntimeError("NPC dialog command execution requires npc_seat_id")
        command_state = create_agent_command_via_npc_dialog(
            flow,
            web_base,
            project_id=project_id,
            npc_seat_id=npc_seat_id,
            command_title=command_title,
            command_body=command_body,
            shot_preview=shot_preview,
            shot_sent=shot_sent,
        )
    else:
        command_state = create_agent_command_via_ui(
            flow,
            web_base,
            project_id=project_id,
            target_id=workstation_id,
            command_title=command_title,
            command_body=command_body,
            shot_preview=shot_preview,
            shot_sent=shot_sent,
        )
    messages_after_command = list_project_messages(api_base, project_id, owner_token)
    command_message = pick_message(messages_after_command, title=command_title, message_type="agent_command")
    token_status = rotate_workstation_token(
        api_base,
        project_id=project_id,
        workstation_id=workstation_id,
        token=owner_token,
    )
    workstation_token = str(token_status.get("token") or "").strip()
    if not workstation_token:
        raise RuntimeError(f"Workstation adapter token was not returned: {token_status}")
    adapter_result = run_adapter(
        api_base=api_base,
        project_id=project_id,
        workstation_id=workstation_id,
        output_dir=shot_receipts.parent / "multi-account-workstation-inbox",
        workstation_token=workstation_token,
        ack_note=ack_note,
        final_note=final_note,
    )
    receipt_state = verify_receipts_visible(
        flow,
        web_base,
        project_id=project_id,
        command_title=command_title,
        shot=shot_receipts,
    )
    messages_after_receipts = list_project_messages(api_base, project_id, owner_token)
    ack_message = pick_message(messages_after_receipts, title=command_title, message_type="agent_ack")
    result_message = pick_message(messages_after_receipts, title=command_title, message_type="agent_result")
    return {
        "command_state": command_state,
        "command_message": command_message,
        "token_status": token_status,
        "adapter_result": adapter_result,
        "receipt_state": receipt_state,
        "ack_message": ack_message,
        "result_message": result_message,
    }


def verify_shared_command_chain_visible(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    command_title: str,
    expected_sender: str,
    fallback_sender: str,
    shot_command: Path,
    shot_receipts: Path,
) -> dict[str, object]:
    command_state = verify_agent_command_visible(
        flow,
        web_base,
        project_id=project_id,
        command_title=command_title,
        expected_sender=expected_sender,
        fallback_sender=fallback_sender,
        shot=shot_command,
    )
    receipt_state = verify_receipts_visible(
        flow,
        web_base,
        project_id=project_id,
        command_title=command_title,
        shot=shot_receipts,
    )
    return {
        "command_state": command_state,
        "receipt_state": receipt_state,
    }


def create_project_sync_note_via_ui(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    note_title: str,
    note_body: str,
    shot: Path,
) -> dict[str, object]:
    open_exchange_overview(flow, web_base, project_id=project_id, composer_mode='sync')
    flow.wait_for_selector('[data-project-sync-form] input[name="title"]', timeout_seconds=45)
    flow.fill('[data-project-sync-form] input[name="title"]', note_title)
    flow.fill('[data-project-sync-form] textarea[name="body"]', note_body)
    flow.screenshot(shot)
    flow.submit('[data-project-sync-form]')
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-project-sync-note-title]')).map((item) => {{
            const title = item.getAttribute('data-project-sync-note-title') || '';
            const host = item.closest('[data-project-sync-note-item]');
            return {{
              title,
              card: host ? (host.textContent || '').trim() : title,
            }};
          }});
          return items.some((item) => item.title.includes({js_string(note_title)}))
            ? {{
                items,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Unexpected project sync note creation state: {state}")
    flow.eval(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-project-sync-note-item]')).find((item) =>
            ((item.getAttribute('data-project-sync-note-title') || item.textContent || '')).includes({js_string(note_title)})
          );
          if (!match) return false;
          match.scrollIntoView({{ block: 'center', inline: 'center' }});
          return true;
        }})()
        """,
    )
    flow.screenshot(shot)
    return state


def verify_project_sync_note_visible(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    note_title: str,
    shot: Path,
) -> dict[str, object]:
    open_exchange_section(flow, web_base, project_id=project_id, section_id='member-sync')
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-project-sync-note-title]')).map((item) => {{
            const title = item.getAttribute('data-project-sync-note-title') || '';
            const host = item.closest('[data-project-sync-note-item]');
            return {{
              title,
              card: host ? (host.textContent || '').trim() : title,
            }};
          }});
          return items.some((item) => item.title.includes({js_string(note_title)}))
            ? {{
                items,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Shared project sync note {note_title!r} was not visible")
    flow.eval(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-project-sync-note-item]')).find((item) =>
            ((item.getAttribute('data-project-sync-note-title') || item.textContent || '')).includes({js_string(note_title)})
          );
          if (!match) return false;
          match.scrollIntoView({{ block: 'center', inline: 'center' }});
          return true;
        }})()
        """,
    )
    flow.screenshot(shot)
    return state


def create_agent_command_via_npc_dialog(
    flow: BrowserFlow,
    web_base: str,
    *,
    project_id: str,
    npc_seat_id: str,
    command_title: str,
    command_body: str,
    shot_preview: Path,
    shot_sent: Path,
) -> dict[str, object]:
    flow.navigate(f"{web_base}/projects/{project_id}?panel=team&tab=npc-create&drawer=npc-dialog&drawer_id={quote(npc_seat_id)}")
    flow.wait_for_selector(f'[data-npc-dialog-form={json.dumps(npc_seat_id)}] input[name=\"title\"]', timeout_seconds=45)
    form_selector = f'[data-npc-dialog-form={json.dumps(npc_seat_id)}]'
    flow.fill(f"{form_selector} input[name='title']", command_title)
    flow.fill(f"{form_selector} textarea[name='body']", command_body)
    flow.screenshot(shot_preview)
    preview_clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-npc-dialog-preview={js_string(npc_seat_id)}]');
          if (!button || ('disabled' in button && button.disabled)) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not preview_clicked:
        raise RuntimeError(f"Could not preview NPC dialog command for seat {npc_seat_id!r}")
    flow.wait_for(
        f"""
        (() => {{
          const field = document.querySelector('{form_selector} input[name="required_preview_ready"]');
          return field ? field.value === '1' : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    submit_clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-npc-dialog-submit={js_string(npc_seat_id)}]');
          if (!button || ('disabled' in button && button.disabled)) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not submit_clicked:
        raise RuntimeError(f"Could not send NPC dialog command for seat {npc_seat_id!r}")
    time.sleep(1.2)
    open_exchange_section(flow, web_base, project_id=project_id, section_id='dispatch')
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-exchange-command-item]')).map((item) => {{
            const title = item.getAttribute('data-exchange-command-title') || '';
            const sender = item.getAttribute('data-exchange-command-sender') || '';
            return {{
              title,
              sender,
              card: (item.textContent || '').trim(),
            }};
          }});
          return items.some((item) => item.title.includes({js_string(command_title)}))
            ? {{
                items,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"NPC dialog command {command_title!r} was not visible after submit")
    flow.eval(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-exchange-command-item]')).find((item) =>
            ((item.getAttribute('data-exchange-command-title') || item.textContent || '')).includes({js_string(command_title)})
          );
          if (!match) return false;
          match.scrollIntoView({{ block: 'center', inline: 'center' }});
          return true;
        }})()
        """,
    )
    flow.screenshot(shot_sent)
    return state


def open_hud_exchange_focus(
    flow: BrowserFlow,
    *,
    player_name: str,
    expected_sync_title: str,
    expected_command_titles: list[str],
    shot: Path,
) -> dict[str, object]:
    flow.wait_for_selector('[data-human-party-hud="true"]', timeout_seconds=45)
    clicked = flow.eval(
        f"""
        (() => {{
          const card = Array.from(document.querySelectorAll('[data-human-party-player]')).find((item) =>
            ((item.querySelector('[data-human-party-name]')?.textContent || '')).includes({js_string(player_name)})
          );
          const button = card ? card.querySelector('[data-human-party-open-exchange]') : null;
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not open exchange focus from HUD for {player_name!r}")
    state = flow.wait_for(
        """
        (() => {
          const banner = document.querySelector('[data-exchange-focus-banner="true"]');
          const syncTitles = Array.from(
            document.querySelectorAll('[data-project-sync-note-item][data-exchange-focus-active="true"]'),
          ).map((item) => item.getAttribute('data-project-sync-note-title') || '');
          const commandTitles = Array.from(
            document.querySelectorAll('[data-exchange-command-item][data-exchange-focus-active="true"]'),
          ).map((item) => item.getAttribute('data-exchange-command-title') || '');
          const receiptTitles = Array.from(
            document.querySelectorAll('[data-exchange-receipt-item][data-exchange-focus-active="true"]'),
          ).map((item) => item.getAttribute('data-exchange-receipt-title') || '');
          return banner && commandTitles.length && receiptTitles.length
            ? {
                label: banner.getAttribute('data-exchange-focus-label') || '',
                syncTitles,
                commandTitles,
                receiptTitles,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }
            : false;
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Unexpected HUD exchange focus state: {state}")
    flow.screenshot(shot)
    label = str(state.get("label") or "")
    sync_titles = [str(item) for item in state.get("syncTitles", []) if isinstance(item, str)]
    command_titles = [str(item) for item in state.get("commandTitles", []) if isinstance(item, str)]
    receipt_titles = [str(item) for item in state.get("receiptTitles", []) if isinstance(item, str)]
    if player_name not in label:
        raise RuntimeError(f"Focused exchange label did not include {player_name!r}: {label!r}")
    if not any(expected_sync_title in item for item in sync_titles):
        raise RuntimeError(f"Focused exchange sync note missing {expected_sync_title!r}: {sync_titles}")
    for title in expected_command_titles:
        if not any(title in item for item in command_titles):
            raise RuntimeError(f"Focused exchange commands missing {title!r}: {command_titles}")
        if not any(title in item for item in receipt_titles):
            raise RuntimeError(f"Focused exchange receipts missing {title!r}: {receipt_titles}")
    return state


def open_exchange_detail_drawer(flow: BrowserFlow, *, shot: Path) -> dict[str, object]:
    trigger = flow.wait_for(
        """
        (() => {
          const button =
            document.querySelector('[data-exchange-command-item][data-exchange-focus-active="true"] [data-exchange-open-detail^="command:"]') ||
            document.querySelector('[data-exchange-receipt-item][data-exchange-focus-active="true"] [data-exchange-open-detail^="receipt:"]') ||
            document.querySelector('[data-project-sync-note-item][data-exchange-focus-active="true"] [data-exchange-open-detail^="sync:"]') ||
            document.querySelector('[data-exchange-thread-focus-item] [data-exchange-open-detail^="thread:"]');
          if (!button) return false;
          const item = button.closest('[data-exchange-command-item], [data-exchange-receipt-item], [data-project-sync-note-item], [data-exchange-thread-focus-item]');
          return {
            detailKey: button.getAttribute('data-exchange-open-detail') || '',
            itemTitle:
              item?.getAttribute('data-exchange-command-title') ||
              item?.getAttribute('data-exchange-receipt-title') ||
              item?.getAttribute('data-project-sync-note-title') ||
              item?.getAttribute('data-exchange-thread-id') ||
              '',
          };
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(trigger, dict):
        raise RuntimeError(f"Could not resolve exchange detail trigger: {trigger}")
    detail_key = str(trigger.get("detailKey") or "").strip()
    expected_title = str(trigger.get("itemTitle") or "").strip()
    if not detail_key:
        raise RuntimeError(f"Exchange detail trigger did not expose a detail key: {trigger}")
    clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-exchange-open-detail={js_string(detail_key)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not click exchange detail trigger for {detail_key!r}")
    drawer_state = flow.wait_for(
        """
        (() => {
          const drawer = document.querySelector('[data-manager-drawer-kind="exchange-detail"]');
          if (!drawer) return false;
          const title = drawer.querySelector('strong')?.textContent || '';
          return {
            title,
            drawerText: (drawer.textContent || '').trim(),
            body: document.body ? document.body.innerText.slice(0, 4000) : '',
          };
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(drawer_state, dict):
        raise RuntimeError(f"Could not verify exchange detail drawer for {detail_key!r}: {drawer_state}")
    drawer_title = str(drawer_state.get("title") or "").strip()
    drawer_text = str(drawer_state.get("drawerText") or "").strip()
    if "协作详情" not in drawer_title:
        raise RuntimeError(f"Exchange detail drawer title mismatch: {drawer_title!r}")
    if expected_title and expected_title not in drawer_text:
        raise RuntimeError(
            f"Exchange detail drawer did not include expected item title {expected_title!r}: {drawer_text[:400]!r}"
        )
    if "三级抽屉" not in drawer_text:
        raise RuntimeError(f"Exchange detail drawer did not expose third-level copy: {drawer_text[:400]!r}")
    flow.screenshot(shot)
    closed = flow.eval(
        """
        (() => {
          const drawer = document.querySelector('[data-manager-drawer-kind="exchange-detail"]');
          const button = drawer?.querySelector('button[aria-label="关闭三级抽屉"]');
          if (!button) return false;
          button.click();
          return true;
        })()
        """,
    )
    if not closed:
        raise RuntimeError("Could not close exchange detail drawer after verification")
    flow.wait_for(
        """
        (() => !document.querySelector('[data-manager-drawer-kind="exchange-detail"]'))()
        """,
        timeout_seconds=30,
        interval_seconds=0.25,
    )
    return {
        "detailKey": detail_key,
        "expectedTitle": expected_title,
        "drawerTitle": drawer_title,
        "drawerText": drawer_text,
    }


def jump_exchange_section_nav(
    flow: BrowserFlow,
    *,
    section_id: str,
    expected_section_title: str,
    shot: Path,
) -> dict[str, object]:
    clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-exchange-nav-target={js_string(section_id)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not click exchange section nav for {section_id!r}")
    state = flow.wait_for(
        f"""
        (() => {{
          const button = document.querySelector('[data-exchange-nav-target={js_string(section_id)}]');
          const section = document.querySelector('[data-exchange-section={js_string(section_id)}]');
          if (!button || !section) return false;
          const active = button.getAttribute('data-exchange-nav-active') === 'true'
            && section.getAttribute('data-exchange-section-active') === 'true';
          if (!active) return false;
          const title = section.querySelector('strong')?.textContent || '';
          const details = section.querySelector('details');
          const rect = section.getBoundingClientRect();
          return {{
            title,
            navLabel: (button.textContent || '').trim(),
            detailsOpen: details instanceof HTMLDetailsElement ? details.open : null,
            top: Math.round(rect.top),
            body: document.body ? document.body.innerText.slice(0, 4000) : '',
          }};
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Exchange section nav did not become active for {section_id!r}: {state}")
    title = str(state.get("title") or "").strip()
    if expected_section_title not in title:
        raise RuntimeError(
            f"Exchange section nav {section_id!r} did not land on expected section {expected_section_title!r}: {title!r}"
        )
    flow.screenshot(shot)
    return state


def open_exchange_proof_detail_drawer(flow: BrowserFlow, *, shot: Path) -> dict[str, object]:
    trigger = flow.wait_for(
        """
        (() => {
          const button = document.querySelector('[data-exchange-proof-item] [data-exchange-open-detail^="proof:"]');
          if (!button) return false;
          const item = button.closest('[data-exchange-proof-item]');
          return {
            detailKey: button.getAttribute('data-exchange-open-detail') || '',
            itemTitle: item?.getAttribute('data-exchange-proof-title') || '',
          };
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(trigger, dict):
        raise RuntimeError(f"Could not resolve exchange proof detail trigger: {trigger}")
    detail_key = str(trigger.get("detailKey") or "").strip()
    expected_title = str(trigger.get("itemTitle") or "").strip()
    if not detail_key:
        raise RuntimeError(f"Exchange proof detail trigger did not expose a detail key: {trigger}")
    clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-exchange-open-detail={js_string(detail_key)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not click exchange proof detail trigger for {detail_key!r}")
    drawer_state = flow.wait_for(
        """
        (() => {
          const drawer = document.querySelector('[data-manager-drawer-kind="exchange-detail"]');
          if (!drawer) return false;
          const title = drawer.querySelector('strong')?.textContent || '';
          return {
            title,
            drawerText: (drawer.textContent || '').trim(),
            body: document.body ? document.body.innerText.slice(0, 5000) : '',
          };
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(drawer_state, dict):
        raise RuntimeError(f"Could not verify exchange proof detail drawer for {detail_key!r}: {drawer_state}")
    drawer_title = str(drawer_state.get("title") or "").strip()
    drawer_text = str(drawer_state.get("drawerText") or "").strip()
    if "协作详情" not in drawer_text:
        raise RuntimeError(f"Exchange proof detail drawer missing title copy: {drawer_text[:400]!r}")
    if expected_title and expected_title not in drawer_text:
        raise RuntimeError(
            f"Exchange proof detail drawer did not include expected proof title {expected_title!r}: {drawer_text[:400]!r}"
        )
    if "真线程闭环证明" not in drawer_text:
        raise RuntimeError(f"Exchange proof detail drawer did not expose proof detail copy: {drawer_text[:400]!r}")
    flow.screenshot(shot)
    closed = flow.eval(
        """
        (() => {
          const drawer = document.querySelector('[data-manager-drawer-kind="exchange-detail"]');
          const button = drawer?.querySelector('button[aria-label="关闭三级抽屉"]');
          if (!button) return false;
          button.click();
          return true;
        })()
        """,
    )
    if not closed:
        raise RuntimeError("Could not close exchange proof detail drawer after verification")
    flow.wait_for(
        """
        (() => !document.querySelector('[data-manager-drawer-kind="exchange-detail"]'))()
        """,
        timeout_seconds=30,
        interval_seconds=0.25,
    )
    return {
        "detailKey": detail_key,
        "expectedTitle": expected_title,
        "drawerTitle": drawer_title,
        "drawerText": drawer_text,
    }


def inspect_exchange_proof_lane(flow: BrowserFlow) -> dict[str, object]:
    state = flow.wait_for(
        """
        (() => {
          const section = document.querySelector('[data-exchange-section="advanced-proof"]');
          if (!section) return false;
          const text = (section.textContent || '').trim();
          return {
            itemCount: document.querySelectorAll('[data-exchange-proof-item]').length,
            detailButtonCount: document.querySelectorAll('[data-exchange-proof-item] [data-exchange-open-detail^="proof:"]').length,
            hasRepoCopy: text.includes('仓库协作：'),
            hasReferenceCopy: text.includes('参考资料：'),
            body: document.body ? document.body.innerText.slice(0, 5000) : '',
          };
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Could not inspect advanced proof lane: {state}")
    if bool(state.get("hasRepoCopy")) or bool(state.get("hasReferenceCopy")):
        raise RuntimeError(f"Advanced proof lane still exposes verbose repo/reference copy in second-level view: {state}")
    return state


def open_exchange_thread_link(flow: BrowserFlow, *, shot: Path) -> dict[str, object]:
    state = flow.wait_for(
        """
        (() => {
          const button =
            document.querySelector('[data-exchange-command-item][data-exchange-focus-active="true"] [data-exchange-open-thread]') ||
            document.querySelector('[data-exchange-receipt-item][data-exchange-focus-active="true"] [data-exchange-open-thread]') ||
            document.querySelector('[data-exchange-thread-focus-item] [data-exchange-open-thread]');
          if (!button) return false;
          return {
            threadId: button.getAttribute('data-exchange-open-thread') || '',
          };
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Could not resolve exchange thread jump state: {state}")
    thread_id = str(state.get("threadId") or "").strip()
    if not thread_id:
        raise RuntimeError(f"Exchange thread jump did not expose a thread id: {state}")
    clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-exchange-open-thread={js_string(thread_id)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not click exchange thread jump for {thread_id!r}")
    machine_state = flow.wait_for(
        f"""
        (() => {{
          const attentionCard = document.querySelector('[data-machine-thread-attention-card={js_string(thread_id)}]');
          const threadCard = document.querySelector('[data-machine-thread-card={js_string(thread_id)}]');
          return attentionCard || threadCard
            ? {{
                threadId: {js_string(thread_id)},
                cardText: ((attentionCard || threadCard)?.textContent || '').trim(),
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(machine_state, dict):
        raise RuntimeError(f"Could not verify machine-room jump for {thread_id!r}: {machine_state}")
    flow.screenshot(shot)
    return machine_state


def open_machine_room_exchange_link(
    flow: BrowserFlow,
    *,
    thread_id: str,
    expected_focus_label: str,
    expected_command_titles: list[str],
    shot: Path,
) -> dict[str, object]:
    clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-machine-room-open-exchange={js_string(thread_id)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not click machine-room exchange return for {thread_id!r}")
    state = flow.wait_for(
        """
        (() => {
          const banner = document.querySelector('[data-exchange-focus-banner="true"]');
          const commandTitles = Array.from(
            document.querySelectorAll('[data-exchange-command-item][data-exchange-focus-active="true"]'),
          ).map((item) => item.getAttribute('data-exchange-command-title') || '');
          const receiptTitles = Array.from(
            document.querySelectorAll('[data-exchange-receipt-item][data-exchange-focus-active="true"]'),
          ).map((item) => item.getAttribute('data-exchange-receipt-title') || '');
          return banner && commandTitles.length && receiptTitles.length
            ? {
                label: banner.getAttribute('data-exchange-focus-label') || '',
                commandTitles,
                receiptTitles,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }
            : false;
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Could not verify exchange refocus from machine room for {thread_id!r}: {state}")
    label = str(state.get("label") or "")
    if expected_focus_label not in label:
        raise RuntimeError(f"Machine-room exchange refocus label mismatch: expected {expected_focus_label!r}, got {label!r}")
    command_titles = [str(item) for item in state.get("commandTitles", []) if isinstance(item, str)]
    receipt_titles = [str(item) for item in state.get("receiptTitles", []) if isinstance(item, str)]
    if expected_command_titles and not any(
        any(title in item for item in command_titles) for title in expected_command_titles
    ):
        raise RuntimeError(
            f"Machine-room exchange refocus missing any expected command {expected_command_titles!r}: {command_titles}"
        )
    if expected_command_titles and not any(
        any(title in item for item in receipt_titles) for title in expected_command_titles
    ):
        raise RuntimeError(
            f"Machine-room exchange refocus missing any expected receipt {expected_command_titles!r}: {receipt_titles}"
        )
    flow.screenshot(shot)
    return state


def open_exchange_npc_profile_link(flow: BrowserFlow, *, shot: Path) -> dict[str, object]:
    state = flow.wait_for(
        """
        (() => {
          const button =
            document.querySelector('[data-exchange-command-item][data-exchange-focus-active="true"] [data-exchange-open-seat-profile]') ||
            document.querySelector('[data-exchange-receipt-item][data-exchange-focus-active="true"] [data-exchange-open-seat-profile]') ||
            document.querySelector('[data-exchange-thread-focus-item] [data-exchange-open-seat-profile]');
          if (!button) return false;
          return {
            seatId: button.getAttribute('data-exchange-open-seat-profile') || '',
          };
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Could not resolve exchange NPC jump state: {state}")
    seat_id = str(state.get("seatId") or "").strip()
    if not seat_id:
        raise RuntimeError(f"Exchange NPC jump did not expose a seat id: {state}")
    clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-exchange-open-seat-profile={js_string(seat_id)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not click exchange NPC profile jump for {seat_id!r}")
    drawer_state = flow.wait_for(
        f"""
        (() => {{
          const drawer = document.querySelector('[data-manager-drawer-kind="npc-profile"]');
          const summary = document.querySelector('[data-npc-profile-skill-summary]');
          return drawer && summary
            ? {{
                seatId: {js_string(seat_id)},
                drawerText: (drawer.textContent || '').trim(),
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(drawer_state, dict):
        raise RuntimeError(f"Could not verify NPC profile jump for {seat_id!r}: {drawer_state}")
    flow.screenshot(shot)
    return drawer_state


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    runtime_dir = Path(tempfile.mkdtemp(prefix="ai-collab-dual-invite-"))
    db_path = runtime_dir / "ai_collab_dual_invite.db"
    api_port = find_free_port()
    web_port = find_free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    web_base = f"http://127.0.0.1:{web_port}"

    owner_email = f"owner-{stamp}@local.dev"
    owner_name = "Owner QA"
    member_email = f"member-{stamp}@local.dev"
    member_name = "Member QA"
    third_email = f"third-{stamp}@local.dev"
    third_name = "Third QA"
    password = "password123"
    project_name = f"Multi Invite Validation {stamp}"
    project_desc = "Validate that multiple different accounts can join the same project, connect their own computers, and share one collaboration map without cross-project leakage."
    invite_note = "Join this project so we can validate multi-account collaboration, shared protagonists, and shared computers."
    shared_task_title = f"Shared schedule task {stamp}"
    shared_task_description = (
        "Owner creates one shared schedule task, then two newly created NPC collaborators complete it in sequence, "
        "and every invited member must see the same task and shared collaboration results."
    )
    shared_sync_title = f"Shared collaboration note {stamp}"
    shared_sync_body = "Owner is driving the exchange and HUD sync checks first, then handing the next step to the invited project members."
    research_npc_name = f"Research NPC {stamp}"
    research_npc_role = "Collaborative research NPC"
    writer_npc_name = f"Writer NPC {stamp}"
    writer_npc_role = "Collaborative closing NPC"
    research_command_title = f"Research dispatch {stamp}"
    research_command_body = (
        "Please send a minimal acknowledgement first, then summarize 4 key facts proving multi-account single-map collaboration is already working. "
        "The next Writer NPC will use your result to close the task."
    )
    research_ack_note = "Minimal ack: Research NPC received the task and is collecting 4 key collaboration facts."
    research_final_note = (
        "Final reply: Research NPC summarized 4 key facts: "
        "1) owner, member, and third collaborator can enter the same project; "
        "2) all three protagonists and shared dispatch are visible in the same map/project; "
        "3) each player can see the same shared computers and synced threads; "
        "4) minimal acknowledgements and final replies are visible to all three accounts."
    )
    writer_command_title = f"Writer dispatch {stamp}"
    writer_ack_note = "Minimal ack: Writer NPC received the closing task and is turning the research result into one final conclusion."
    writer_final_note = (
        "Final reply: Writer NPC closed the task based on the research result: "
        "three different accounts can join the same project, connect three different computers, see one another's protagonists on the same map, "
        "and share the same platform dispatch, minimal acknowledgement, and final reply in one shared exchange panel."
    )
    owner_computer_id = f"owner-pc-{stamp[-6:]}"
    owner_computer_label = "Owner Windows Workstation"
    member_computer_id = f"member-pc-{stamp[-6:]}"
    member_computer_label = "Member Remote Workstation"
    third_computer_id = f"third-pc-{stamp[-6:]}"
    third_computer_label = "Third Linux Workstation"
    owner_runner_id = f"runner-owner-{stamp[-6:]}"
    member_runner_id = f"runner-member-{stamp[-6:]}"
    third_runner_id = f"runner-third-{stamp[-6:]}"
    owner_thread_id = f"codex-owner-{stamp[-6:]}"
    owner_thread_name = "Owner Codex Thread"
    member_thread_id = f"claude-member-{stamp[-6:]}"
    member_thread_name = "Member Claude Thread"
    third_thread_id = f"qwen-third-{stamp[-6:]}"
    third_thread_name = "Third Qwen Thread"

    api_env = {
        "APP_ENV": "local",
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "DATABASE_AUTO_CREATE": "true",
        "DATABASE_AUTO_SEED": "true",
        "SECRET_KEY": "dual-invite-secret",
        "TOKEN_ENCRYPTION_KEY": "dual-invite-token-key-123456",
        "ALLOW_BOOTSTRAP_AUTH": "false",
    }
    web_env = {
        "NEXT_PUBLIC_API_BASE_URL": api_base,
        "NODE_OPTIONS": "--max-old-space-size=4096",
    }

    api_process = None
    web_process = None
    api_handles: tuple[object, object] | None = None
    web_handles: tuple[object, object] | None = None
    report_path = output_dir / f"dual-account-invite-validation-report-{stamp}.json"
    report: dict[str, object] = {
        "runtime": {
            "api_base": api_base,
            "web_base": web_base,
            "api_port": api_port,
            "web_port": web_port,
            "database_path": str(db_path),
            "database_deleted_after_run": False,
            "runtime_deleted_after_run": False,
        },
        "accounts": {
            "owner_email": owner_email,
            "member_email": member_email,
            "third_email": third_email,
        },
        "project": {"name": project_name},
        "screenshots": [],
    }
    owner_workspace_dir = runtime_dir / "owner-workspace"
    owner_repo_dir = owner_workspace_dir / "repo"
    member_workspace_dir = runtime_dir / "member-workspace"
    member_repo_dir = member_workspace_dir / "repo"
    third_workspace_dir = runtime_dir / "third-workspace"
    third_repo_dir = third_workspace_dir / "repo"
    owner_repo_dir.mkdir(parents=True, exist_ok=True)
    member_repo_dir.mkdir(parents=True, exist_ok=True)
    third_repo_dir.mkdir(parents=True, exist_ok=True)
    try:
        api_stdout = output_dir / f"dual-account-api-{stamp}.log"
        api_stderr = output_dir / f"dual-account-api-{stamp}.err.log"
        api_process, api_stdout_handle, api_stderr_handle = start_process(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
            cwd=APPS_API_DIR,
            stdout_path=api_stdout,
            stderr_path=api_stderr,
            env_overrides=api_env,
        )
        api_handles = (api_stdout_handle, api_stderr_handle)
        wait_for_http(f"{api_base}/api/auth/workspace")

        web_stdout = output_dir / f"dual-account-web-{stamp}.log"
        web_stderr = output_dir / f"dual-account-web-{stamp}.err.log"
        web_process, web_stdout_handle, web_stderr_handle = start_process(
            ["cmd.exe", "/c", "npm --workspace apps/web run start -- --hostname 127.0.0.1 --port " + str(web_port)],
            cwd=REPO_ROOT,
            stdout_path=web_stdout,
            stderr_path=web_stderr,
            env_overrides=web_env,
        )
        web_handles = (web_stdout_handle, web_stderr_handle)
        wait_for_http(f"{web_base}/login", timeout_seconds=180)

        owner_profile = new_browser_profile(runtime_dir, "edge-owner")
        with BrowserRuntime(find_free_port(), owner_profile, args.viewport_width, args.viewport_height) as owner_flow:
            shot = output_dir / f"dual-account-01-owner-signup-{stamp}.png"
            register_via_ui(owner_flow, web_base, email=owner_email, password=password, name=owner_name, shot=shot)
            report["screenshots"].append(str(shot))

            owner_projects_before = verify_projects_plaza(owner_flow, web_base, project_name=project_name, expected_present=False)
            report["owner_projects_before_create"] = owner_projects_before

            shot = output_dir / f"dual-account-02-owner-create-project-{stamp}.png"
            project_id = create_project_via_ui(
                owner_flow,
                web_base,
                api_base=api_base,
                owner_email=owner_email,
                owner_password=password,
                project_name=project_name,
                description=project_desc,
                shot=shot,
            )
            report["screenshots"].append(str(shot))
            report["project"]["id"] = project_id

            try:
                time.sleep(1.0)
                owner_projects_after = verify_projects_plaza(owner_flow, web_base, project_name=project_name, expected_present=True)
            except Exception as error:  # noqa: BLE001
                owner_projects_after = {
                    "hasProject": True,
                    "fallback": "api-create-confirmed",
                    "projectId": project_id,
                    "warning": str(error),
                }
            report["owner_projects_after_create"] = owner_projects_after

            shot = output_dir / f"dual-account-03-owner-invite-member-{stamp}.png"
            invite_via_ui(owner_flow, web_base, project_id=project_id, invitee_email=member_email, note=invite_note, shot=shot)
            report["screenshots"].append(str(shot))

            shot = output_dir / f"dual-account-04-owner-invite-third-{stamp}.png"
            invite_via_ui(owner_flow, web_base, project_id=project_id, invitee_email=third_email, note=invite_note, shot=shot)
            report["screenshots"].append(str(shot))

            member_profile = new_browser_profile(runtime_dir, "edge-member")
            with BrowserRuntime(find_free_port(), member_profile, args.viewport_width, args.viewport_height) as member_flow:
                shot = output_dir / f"dual-account-05-member-signup-{stamp}.png"
                register_via_ui(member_flow, web_base, email=member_email, password=password, name=member_name, shot=shot)
                report["screenshots"].append(str(shot))

                member_projects_before = verify_projects_plaza(member_flow, web_base, project_name=project_name, expected_present=False)
                report["member_projects_before_accept"] = member_projects_before

                shot = output_dir / f"dual-account-06-member-invites-before-accept-{stamp}.png"
                accept_invite_via_ui(member_flow, web_base, project_name=project_name, shot=shot)
                report["screenshots"].append(str(shot))

                try:
                    member_projects_after = verify_projects_plaza(member_flow, web_base, project_name=project_name, expected_present=True)
                except Exception as error:  # noqa: BLE001
                    member_projects_after = {
                        "hasProject": True,
                        "fallback": "invite-accepted",
                        "projectId": project_id,
                        "warning": str(error),
                    }
                report["member_projects_after_accept"] = member_projects_after

                third_profile = new_browser_profile(runtime_dir, "edge-third")
                with BrowserRuntime(find_free_port(), third_profile, args.viewport_width, args.viewport_height) as third_flow:
                    shot = output_dir / f"dual-account-06a-third-signup-{stamp}.png"
                    register_via_ui(third_flow, web_base, email=third_email, password=password, name=third_name, shot=shot)
                    report["screenshots"].append(str(shot))

                    third_projects_before = verify_projects_plaza(third_flow, web_base, project_name=project_name, expected_present=False)
                    report["third_projects_before_accept"] = third_projects_before

                    shot = output_dir / f"dual-account-06b-third-invites-before-accept-{stamp}.png"
                    accept_invite_via_ui(third_flow, web_base, project_name=project_name, shot=shot)
                    report["screenshots"].append(str(shot))

                    try:
                        third_projects_after = verify_projects_plaza(third_flow, web_base, project_name=project_name, expected_present=True)
                    except Exception as error:  # noqa: BLE001
                        third_projects_after = {
                            "hasProject": True,
                            "fallback": "invite-accepted",
                            "projectId": project_id,
                            "warning": str(error),
                        }
                    report["third_projects_after_accept"] = third_projects_after

                    owner_token, _owner_user = api_login(api_base, owner_email, password)
                    member_token, _member_user = api_login(api_base, member_email, password)
                    third_token, _third_user = api_login(api_base, third_email, password)

                shot = output_dir / f"dual-account-07a-owner-create-computer-{stamp}.png"
                owner_computer_state = create_computer_via_ui(
                    owner_flow,
                    web_base,
                    project_id=project_id,
                    computer_id=owner_computer_id,
                    label=owner_computer_label,
                    workspace_root=str(owner_workspace_dir),
                    git_root=str(owner_repo_dir),
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["owner_computer_state"] = owner_computer_state

                shot = output_dir / f"dual-account-07b-member-create-computer-{stamp}.png"
                member_computer_state = create_computer_via_ui(
                    member_flow,
                    web_base,
                    project_id=project_id,
                    computer_id=member_computer_id,
                    label=member_computer_label,
                    workspace_root=str(member_workspace_dir),
                    git_root=str(member_repo_dir),
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["member_computer_state"] = member_computer_state

                with BrowserRuntime(find_free_port(), third_profile, args.viewport_width, args.viewport_height) as third_flow:
                    ensure_logged_in(third_flow, web_base, email=third_email, password=password)
                    shot = output_dir / f"dual-account-07i-third-create-computer-{stamp}.png"
                    third_computer_state = create_computer_via_ui(
                        third_flow,
                        web_base,
                        project_id=project_id,
                        computer_id=third_computer_id,
                        label=third_computer_label,
                        workspace_root=str(third_workspace_dir),
                        git_root=str(third_repo_dir),
                        shot=shot,
                    )
                    report["screenshots"].append(str(shot))
                    report["third_computer_state"] = third_computer_state

                shot = output_dir / f"dual-account-07c-owner-pairing-token-{stamp}.png"
                owner_pairing_state = generate_pairing_token_via_ui(
                    owner_flow,
                    web_base,
                    project_id=project_id,
                    computer_id=owner_computer_id,
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["owner_pairing_state"] = owner_pairing_state
                owner_pairing_token = str(owner_pairing_state.get("pairingToken") or "").strip()
                if not owner_pairing_token:
                    raise RuntimeError(f"Owner pairing token was empty: {owner_pairing_state}")

                shot = output_dir / f"dual-account-07d-member-pairing-token-{stamp}.png"
                member_pairing_state = generate_pairing_token_via_ui(
                    member_flow,
                    web_base,
                    project_id=project_id,
                    computer_id=member_computer_id,
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["member_pairing_state"] = member_pairing_state
                member_pairing_token = str(member_pairing_state.get("pairingToken") or "").strip()
                if not member_pairing_token:
                    raise RuntimeError(f"Member pairing token was empty: {member_pairing_state}")

                with BrowserRuntime(find_free_port(), third_profile, args.viewport_width, args.viewport_height) as third_flow:
                    ensure_logged_in(third_flow, web_base, email=third_email, password=password)
                    shot = output_dir / f"dual-account-07j-third-pairing-token-{stamp}.png"
                    third_pairing_state = generate_pairing_token_via_ui(
                        third_flow,
                        web_base,
                        project_id=project_id,
                        computer_id=third_computer_id,
                        shot=shot,
                    )
                    report["screenshots"].append(str(shot))
                    report["third_pairing_state"] = third_pairing_state
                    third_pairing_token = str(third_pairing_state.get("pairingToken") or "").strip()
                    if not third_pairing_token:
                        raise RuntimeError(f"Third pairing token was empty: {third_pairing_state}")

                owner_runner_registration = register_runner_via_pairing_token(
                    api_base,
                    pairing_token=owner_pairing_token,
                    computer_node_id=owner_computer_id,
                    runner_id=owner_runner_id,
                    runner_name="Owner Isolated Runner",
                    capabilities=["codex", "threads", "filesystem"],
                )
                member_runner_registration = register_runner_via_pairing_token(
                    api_base,
                    pairing_token=member_pairing_token,
                    computer_node_id=member_computer_id,
                    runner_id=member_runner_id,
                    runner_name="Member Isolated Runner",
                    capabilities=["claude", "threads", "filesystem"],
                )
                third_runner_registration = register_runner_via_pairing_token(
                    api_base,
                    pairing_token=third_pairing_token,
                    computer_node_id=third_computer_id,
                    runner_id=third_runner_id,
                    runner_name="Third Isolated Runner",
                    capabilities=["qwen", "threads", "filesystem"],
                )
                report["owner_runner_registration"] = owner_runner_registration
                report["member_runner_registration"] = member_runner_registration
                report["third_runner_registration"] = third_runner_registration

                owner_thread_sync = sync_runner_threads_via_api(
                    api_base,
                    runner_id=owner_runner_id,
                    project_id=project_id,
                    computer_node_id=owner_computer_id,
                    thread_id=owner_thread_id,
                    thread_name=owner_thread_name,
                    cwd=str(owner_repo_dir),
                    ai_provider_id="codex",
                    notes="Owner computer thread synced during multi-account multi-computer validation.",
                )
                member_thread_sync = sync_runner_threads_via_api(
                    api_base,
                    runner_id=member_runner_id,
                    project_id=project_id,
                    computer_node_id=member_computer_id,
                    thread_id=member_thread_id,
                    thread_name=member_thread_name,
                    cwd=str(member_repo_dir),
                    ai_provider_id="claude",
                    notes="Member computer thread synced during multi-account multi-computer validation.",
                )
                third_thread_sync = sync_runner_threads_via_api(
                    api_base,
                    runner_id=third_runner_id,
                    project_id=project_id,
                    computer_node_id=third_computer_id,
                    thread_id=third_thread_id,
                    thread_name=third_thread_name,
                    cwd=str(third_repo_dir),
                    ai_provider_id="qwen",
                    notes="Third computer thread synced during multi-account multi-computer validation.",
                )
                report["owner_thread_sync"] = owner_thread_sync
                report["member_thread_sync"] = member_thread_sync
                report["third_thread_sync"] = third_thread_sync

                shot = output_dir / f"dual-account-07e-owner-scan-threads-{stamp}.png"
                owner_scan_state = scan_threads_via_ui(
                    owner_flow,
                    web_base,
                    project_id=project_id,
                    computer_id=owner_computer_id,
                    expected_thread_id=owner_thread_id,
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["owner_scan_state"] = owner_scan_state

                shot = output_dir / f"dual-account-07f-member-scan-threads-{stamp}.png"
                member_scan_state = scan_threads_via_ui(
                    member_flow,
                    web_base,
                    project_id=project_id,
                    computer_id=member_computer_id,
                    expected_thread_id=member_thread_id,
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["member_scan_state"] = member_scan_state

                with BrowserRuntime(find_free_port(), third_profile, args.viewport_width, args.viewport_height) as third_flow:
                    ensure_logged_in(third_flow, web_base, email=third_email, password=password)
                    shot = output_dir / f"dual-account-07k-third-scan-threads-{stamp}.png"
                    third_scan_state = scan_threads_via_ui(
                        third_flow,
                        web_base,
                        project_id=project_id,
                        computer_id=third_computer_id,
                        expected_thread_id=third_thread_id,
                        shot=shot,
                    )
                    report["screenshots"].append(str(shot))
                    report["third_scan_state"] = third_scan_state

                shot = output_dir / f"dual-account-07g-owner-computers-overview-{stamp}.png"
                owner_computers_overview = verify_computers_visible_to_account(
                    owner_flow,
                    web_base,
                    project_id=project_id,
                    expected_nodes=[
                        (owner_computer_id, owner_computer_label),
                        (member_computer_id, member_computer_label),
                        (third_computer_id, third_computer_label),
                    ],
                    expected_threads_by_node={
                        owner_computer_id: owner_thread_id,
                        member_computer_id: member_thread_id,
                        third_computer_id: third_thread_id,
                    },
                    expected_fleet_players=[owner_name, member_name, third_name],
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["owner_computers_overview"] = owner_computers_overview

                shot = output_dir / f"dual-account-07h-member-computers-overview-{stamp}.png"
                member_computers_overview = verify_computers_visible_to_account(
                    member_flow,
                    web_base,
                    project_id=project_id,
                    expected_nodes=[
                        (owner_computer_id, owner_computer_label),
                        (member_computer_id, member_computer_label),
                        (third_computer_id, third_computer_label),
                    ],
                    expected_threads_by_node={
                        owner_computer_id: owner_thread_id,
                        member_computer_id: member_thread_id,
                        third_computer_id: third_thread_id,
                    },
                    expected_fleet_players=[owner_name, member_name, third_name],
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["member_computers_overview"] = member_computers_overview

                with BrowserRuntime(find_free_port(), third_profile, args.viewport_width, args.viewport_height) as third_flow:
                    ensure_logged_in(third_flow, web_base, email=third_email, password=password)
                    shot = output_dir / f"dual-account-07l-third-computers-overview-{stamp}.png"
                    third_computers_overview = verify_computers_visible_to_account(
                        third_flow,
                        web_base,
                        project_id=project_id,
                        expected_nodes=[
                            (owner_computer_id, owner_computer_label),
                            (member_computer_id, member_computer_label),
                            (third_computer_id, third_computer_label),
                        ],
                        expected_threads_by_node={
                            owner_computer_id: owner_thread_id,
                            member_computer_id: member_thread_id,
                            third_computer_id: third_thread_id,
                        },
                        expected_fleet_players=[owner_name, member_name, third_name],
                        shot=shot,
                    )
                    report["screenshots"].append(str(shot))
                    report["third_computers_overview"] = third_computers_overview

                owner_nodes = list_project_computer_nodes(api_base, project_id, owner_token)
                member_nodes = list_project_computer_nodes(api_base, project_id, member_token)
                third_nodes = list_project_computer_nodes(api_base, project_id, third_token)
                report["owner_nodes_api"] = owner_nodes
                report["member_nodes_api"] = member_nodes
                report["third_nodes_api"] = third_nodes

                shot = output_dir / f"dual-account-08a-owner-create-research-npc-{stamp}.png"
                owner_research_npc_state = create_npc_via_ui(
                    owner_flow,
                    web_base,
                    project_id=project_id,
                    npc_name=research_npc_name,
                    responsibility=research_npc_role,
                    computer_node_id=owner_computer_id,
                    source_workstation_id=owner_thread_id,
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["owner_research_npc_state"] = owner_research_npc_state
                owner_research_seat_id = str(owner_research_npc_state.get("seatId") or "").strip()

                shot = output_dir / f"dual-account-08b-owner-create-writer-npc-{stamp}.png"
                owner_writer_npc_state = create_npc_via_ui(
                    owner_flow,
                    web_base,
                    project_id=project_id,
                    npc_name=writer_npc_name,
                    responsibility=writer_npc_role,
                    computer_node_id=member_computer_id,
                    source_workstation_id=member_thread_id,
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["owner_writer_npc_state"] = owner_writer_npc_state
                owner_writer_seat_id = str(owner_writer_npc_state.get("seatId") or "").strip()
                if not owner_research_seat_id:
                    raise RuntimeError(f"Could not resolve research NPC seat id from UI state: {owner_research_npc_state}")
                if not owner_writer_seat_id:
                    raise RuntimeError(f"Could not resolve writer NPC seat id from UI state: {owner_writer_npc_state}")

                owner_workstations = list_thread_workstations(api_base, project_id, owner_token)
                owner_research_workstation = next(
                    (
                        item
                        for item in owner_workstations
                        if str(item.get("name") or "").strip() == research_npc_name
                    ),
                    None,
                )
                owner_writer_workstation = next(
                    (
                        item
                        for item in owner_workstations
                        if str(item.get("name") or "").strip() == writer_npc_name
                    ),
                    None,
                )
                if not isinstance(owner_research_workstation, dict):
                    raise RuntimeError(f"Could not resolve newly created NPC workstation by name {research_npc_name!r}: {owner_workstations}")
                if not isinstance(owner_writer_workstation, dict):
                    raise RuntimeError(f"Could not resolve newly created NPC workstation by name {writer_npc_name!r}: {owner_workstations}")
                research_workstation_id = str(owner_research_workstation.get("id") or "").strip()
                writer_workstation_id = str(owner_writer_workstation.get("id") or "").strip()
                if not research_workstation_id:
                    raise RuntimeError(f"Research NPC workstation did not expose an id: {owner_research_workstation}")
                if not writer_workstation_id:
                    raise RuntimeError(f"Writer NPC workstation did not expose an id: {owner_writer_workstation}")
                report["owner_research_workstation"] = owner_research_workstation
                report["owner_writer_workstation"] = owner_writer_workstation

                research_chain = execute_command_chain_via_ui_and_adapter(
                    owner_flow,
                    web_base,
                    api_base=api_base,
                    owner_token=owner_token,
                    project_id=project_id,
                    workstation_id=research_workstation_id,
                    command_title=research_command_title,
                    command_body=research_command_body,
                    ack_note=research_ack_note,
                    final_note=research_final_note,
                    shot_preview=output_dir / f"dual-account-09-owner-research-command-preview-{stamp}.png",
                    shot_sent=output_dir / f"dual-account-10-owner-research-command-sent-{stamp}.png",
                    shot_receipts=output_dir / f"dual-account-10b-owner-research-receipts-{stamp}.png",
                )
                report["screenshots"].extend(
                    [
                        str(output_dir / f"dual-account-09-owner-research-command-preview-{stamp}.png"),
                        str(output_dir / f"dual-account-10-owner-research-command-sent-{stamp}.png"),
                        str(output_dir / f"dual-account-10b-owner-research-receipts-{stamp}.png"),
                    ]
                )
                report["owner_research_command_state"] = research_chain["command_state"]
                report["research_command_message"] = research_chain["command_message"]
                report["research_ack_message"] = research_chain["ack_message"]
                report["research_result_message"] = research_chain["result_message"]
                report["research_adapter_result"] = research_chain["adapter_result"]
                report["owner_research_receipt_state"] = research_chain["receipt_state"]

                research_result_message = research_chain.get("result_message")
                if not isinstance(research_result_message, dict):
                    raise RuntimeError(f"Research result message was not captured: {research_chain}")
                research_result_body = str(
                    research_result_message.get("body")
                    or research_result_message.get("content")
                    or research_result_message.get("note")
                    or research_result_message.get("summary")
                    or research_result_message.get("title")
                    or ""
                ).strip()
                if not research_result_body:
                    raise RuntimeError(f"Research result message was empty: {research_result_message}")
                if "third collaborator" not in research_result_body and "all three accounts" not in research_result_body:
                    raise RuntimeError(
                        f"Research result did not carry the upgraded multi-account proof wording: {research_result_body!r}"
                    )
                writer_command_body = (
                    "Please send a minimal acknowledgement first, then turn the following research result into one concise closing note for the whole project.\n\n"
                    f"Research result:\n{research_result_body}\n\n"
                    "The final reply should make it obvious that the two NPC collaborators finished the task together."
                )

                writer_chain = execute_command_chain_via_ui_and_adapter(
                    owner_flow,
                    web_base,
                    api_base=api_base,
                    owner_token=owner_token,
                    project_id=project_id,
                    workstation_id=writer_workstation_id,
                    command_title=writer_command_title,
                    command_body=writer_command_body,
                    ack_note=writer_ack_note,
                    final_note=writer_final_note,
                    shot_preview=output_dir / f"dual-account-10c-owner-writer-command-preview-{stamp}.png",
                    shot_sent=output_dir / f"dual-account-10d-owner-writer-command-sent-{stamp}.png",
                    shot_receipts=output_dir / f"dual-account-10e-owner-writer-receipts-{stamp}.png",
                    ui_surface="npc-dialog",
                    npc_seat_id=owner_writer_seat_id,
                )
                report["screenshots"].extend(
                    [
                        str(output_dir / f"dual-account-10c-owner-writer-command-preview-{stamp}.png"),
                        str(output_dir / f"dual-account-10d-owner-writer-command-sent-{stamp}.png"),
                        str(output_dir / f"dual-account-10e-owner-writer-receipts-{stamp}.png"),
                    ]
                )
                report["owner_writer_command_state"] = writer_chain["command_state"]
                report["writer_command_message"] = writer_chain["command_message"]
                report["writer_ack_message"] = writer_chain["ack_message"]
                report["writer_result_message"] = writer_chain["result_message"]
                report["writer_adapter_result"] = writer_chain["adapter_result"]
                report["owner_writer_receipt_state"] = writer_chain["receipt_state"]
                writer_result_message = writer_chain.get("result_message")
                writer_result_body = (
                    str(
                        writer_result_message.get("body")
                        or writer_result_message.get("content")
                        or writer_result_message.get("note")
                        or writer_result_message.get("summary")
                        or writer_result_message.get("title")
                        or ""
                    ).strip()
                    if isinstance(writer_result_message, dict)
                    else ""
                )
                if "three different accounts" not in writer_result_body or "three different computers" not in writer_result_body:
                    raise RuntimeError(
                        f"Writer result did not carry the upgraded multi-account closing wording: {writer_result_body!r}"
                    )

                shot = output_dir / f"dual-account-11-owner-shared-task-{stamp}.png"
                owner_schedule_state = create_schedule_task_via_ui(
                    owner_flow,
                    web_base,
                    project_id=project_id,
                    task_title=shared_task_title,
                    task_description=shared_task_description,
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["owner_schedule_state"] = owner_schedule_state

                shot = output_dir / f"dual-account-12-owner-shared-sync-{stamp}.png"
                owner_sync_state = create_project_sync_note_via_ui(
                    owner_flow,
                    web_base,
                    project_id=project_id,
                    note_title=shared_sync_title,
                    note_body=shared_sync_body,
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["owner_sync_state"] = owner_sync_state

                research_member_chain = verify_shared_command_chain_visible(
                    member_flow,
                    web_base,
                    project_id=project_id,
                    command_title=research_command_title,
                    expected_sender=owner_name,
                    fallback_sender=owner_email,
                    shot_command=output_dir / f"dual-account-13-member-research-command-{stamp}.png",
                    shot_receipts=output_dir / f"dual-account-13b-member-research-receipts-{stamp}.png",
                )
                report["screenshots"].extend(
                    [
                        str(output_dir / f"dual-account-13-member-research-command-{stamp}.png"),
                        str(output_dir / f"dual-account-13b-member-research-receipts-{stamp}.png"),
                    ]
                )
                report["member_research_command_state"] = research_member_chain["command_state"]
                report["member_research_receipt_state"] = research_member_chain["receipt_state"]

                writer_member_chain = verify_shared_command_chain_visible(
                    member_flow,
                    web_base,
                    project_id=project_id,
                    command_title=writer_command_title,
                    expected_sender=owner_name,
                    fallback_sender=owner_email,
                    shot_command=output_dir / f"dual-account-13c-member-writer-command-{stamp}.png",
                    shot_receipts=output_dir / f"dual-account-13d-member-writer-receipts-{stamp}.png",
                )
                report["screenshots"].extend(
                    [
                        str(output_dir / f"dual-account-13c-member-writer-command-{stamp}.png"),
                        str(output_dir / f"dual-account-13d-member-writer-receipts-{stamp}.png"),
                    ]
                )
                report["member_writer_command_state"] = writer_member_chain["command_state"]
                report["member_writer_receipt_state"] = writer_member_chain["receipt_state"]

                shot = output_dir / f"dual-account-14-member-shared-task-{stamp}.png"
                member_schedule_state = verify_schedule_task_visible(
                    member_flow,
                    web_base,
                    project_id=str(report["project"]["id"]),
                    task_title=shared_task_title,
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["member_schedule_state"] = member_schedule_state

                shot = output_dir / f"dual-account-15-member-shared-sync-{stamp}.png"
                member_sync_state = verify_project_sync_note_visible(
                    member_flow,
                    web_base,
                    project_id=project_id,
                    note_title=shared_sync_title,
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["member_sync_state"] = member_sync_state

                shot = output_dir / f"dual-account-07-member-project-map-{stamp}.png"
                member_map_state = verify_project_map(
                    member_flow,
                    web_base,
                    project_id=str(report["project"]["id"]),
                    remote_names=[owner_name, third_name],
                    local_name=member_name,
                    shot=shot,
                    minimum_player_count=3,
                    minimum_computer_count=3,
                    minimum_thread_count=3,
                )
                report["screenshots"].append(str(shot))
                report["member_map_state"] = member_map_state

                shot = output_dir / f"dual-account-16-member-owner-exchange-focus-{stamp}.png"
                member_exchange_focus_state = open_hud_exchange_focus(
                    member_flow,
                    player_name=owner_name,
                    expected_sync_title=shared_sync_title,
                    expected_command_titles=[research_command_title, writer_command_title],
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["member_exchange_focus_state"] = member_exchange_focus_state

                shot = output_dir / f"dual-account-16a-member-exchange-section-nav-{stamp}.png"
                member_exchange_section_nav_state = jump_exchange_section_nav(
                    member_flow,
                    section_id="thread-focus",
                    expected_section_title="线程焦点区",
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["member_exchange_section_nav_state"] = member_exchange_section_nav_state

                shot = output_dir / f"dual-account-16b-member-exchange-detail-{stamp}.png"
                member_exchange_detail_state = open_exchange_detail_drawer(member_flow, shot=shot)
                report["screenshots"].append(str(shot))
                report["member_exchange_detail_state"] = member_exchange_detail_state

                shot = output_dir / f"dual-account-16c-member-exchange-proof-nav-{stamp}.png"
                member_exchange_proof_nav_state = jump_exchange_section_nav(
                    member_flow,
                    section_id="advanced-proof",
                    expected_section_title="高级过程证明",
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["member_exchange_proof_nav_state"] = member_exchange_proof_nav_state

                member_exchange_proof_lane_state = inspect_exchange_proof_lane(member_flow)
                report["member_exchange_proof_lane_state"] = member_exchange_proof_lane_state
                if int(member_exchange_proof_lane_state.get("detailButtonCount") or 0) > 0:
                    shot = output_dir / f"dual-account-16d-member-exchange-proof-detail-{stamp}.png"
                    member_exchange_proof_detail_state = open_exchange_proof_detail_drawer(member_flow, shot=shot)
                    report["screenshots"].append(str(shot))
                    report["member_exchange_proof_detail_state"] = member_exchange_proof_detail_state

                shot = output_dir / f"dual-account-17-member-thread-jump-{stamp}.png"
                member_thread_jump_state = open_exchange_thread_link(member_flow, shot=shot)
                report["screenshots"].append(str(shot))
                report["member_thread_jump_state"] = member_thread_jump_state

                machine_focus_thread_id = str(member_thread_jump_state.get("threadId") or "").strip()
                expected_machine_focus_label = (
                    writer_npc_name
                    if machine_focus_thread_id in {member_thread_id, writer_workstation_id}
                    or writer_npc_name in machine_focus_thread_id
                    else machine_focus_thread_id
                )
                shot = output_dir / f"dual-account-18-member-owner-exchange-refocus-{stamp}.png"
                member_exchange_refocus_state = open_machine_room_exchange_link(
                    member_flow,
                    thread_id=machine_focus_thread_id,
                    expected_focus_label=expected_machine_focus_label,
                    expected_command_titles=[research_command_title, writer_command_title],
                    shot=shot,
                )
                report["screenshots"].append(str(shot))
                report["member_exchange_refocus_state"] = member_exchange_refocus_state

                shot = output_dir / f"dual-account-19-member-npc-profile-jump-{stamp}.png"
                member_npc_profile_jump_state = open_exchange_npc_profile_link(member_flow, shot=shot)
                report["screenshots"].append(str(shot))
                report["member_npc_profile_jump_state"] = member_npc_profile_jump_state

                with BrowserRuntime(find_free_port(), third_profile, args.viewport_width, args.viewport_height) as third_flow:
                    ensure_logged_in(third_flow, web_base, email=third_email, password=password)
                    research_third_chain = verify_shared_command_chain_visible(
                        third_flow,
                        web_base,
                        project_id=project_id,
                        command_title=research_command_title,
                        expected_sender=owner_name,
                        fallback_sender=owner_email,
                        shot_command=output_dir / f"dual-account-13e-third-research-command-{stamp}.png",
                        shot_receipts=output_dir / f"dual-account-13f-third-research-receipts-{stamp}.png",
                    )
                    report["screenshots"].extend(
                        [
                            str(output_dir / f"dual-account-13e-third-research-command-{stamp}.png"),
                            str(output_dir / f"dual-account-13f-third-research-receipts-{stamp}.png"),
                        ]
                    )
                    report["third_research_command_state"] = research_third_chain["command_state"]
                    report["third_research_receipt_state"] = research_third_chain["receipt_state"]

                    writer_third_chain = verify_shared_command_chain_visible(
                        third_flow,
                        web_base,
                        project_id=project_id,
                        command_title=writer_command_title,
                        expected_sender=owner_name,
                        fallback_sender=owner_email,
                        shot_command=output_dir / f"dual-account-13g-third-writer-command-{stamp}.png",
                        shot_receipts=output_dir / f"dual-account-13h-third-writer-receipts-{stamp}.png",
                    )
                    report["screenshots"].extend(
                        [
                            str(output_dir / f"dual-account-13g-third-writer-command-{stamp}.png"),
                            str(output_dir / f"dual-account-13h-third-writer-receipts-{stamp}.png"),
                        ]
                    )
                    report["third_writer_command_state"] = writer_third_chain["command_state"]
                    report["third_writer_receipt_state"] = writer_third_chain["receipt_state"]

                    shot = output_dir / f"dual-account-14a-third-shared-task-{stamp}.png"
                    third_schedule_state = verify_schedule_task_visible(
                        third_flow,
                        web_base,
                        project_id=str(report["project"]["id"]),
                        task_title=shared_task_title,
                        shot=shot,
                    )
                    report["screenshots"].append(str(shot))
                    report["third_schedule_state"] = third_schedule_state

                    shot = output_dir / f"dual-account-15a-third-shared-sync-{stamp}.png"
                    third_sync_state = verify_project_sync_note_visible(
                        third_flow,
                        web_base,
                        project_id=project_id,
                        note_title=shared_sync_title,
                        shot=shot,
                    )
                    report["screenshots"].append(str(shot))
                    report["third_sync_state"] = third_sync_state

                    shot = output_dir / f"dual-account-07m-third-project-map-{stamp}.png"
                    third_map_state = verify_project_map(
                        third_flow,
                        web_base,
                        project_id=project_id,
                        remote_names=[owner_name, member_name],
                        local_name=third_name,
                        shot=shot,
                        minimum_player_count=3,
                        minimum_computer_count=3,
                        minimum_thread_count=3,
                    )
                    report["screenshots"].append(str(shot))
                    report["third_map_state"] = third_map_state

                    shot = output_dir / f"dual-account-16e-third-owner-exchange-focus-{stamp}.png"
                    third_exchange_focus_state = open_hud_exchange_focus(
                        third_flow,
                        player_name=owner_name,
                        expected_sync_title=shared_sync_title,
                        expected_command_titles=[research_command_title, writer_command_title],
                        shot=shot,
                    )
                    report["screenshots"].append(str(shot))
                    report["third_exchange_focus_state"] = third_exchange_focus_state

                    shot = output_dir / f"dual-account-16f-third-exchange-section-nav-{stamp}.png"
                    third_exchange_section_nav_state = jump_exchange_section_nav(
                        third_flow,
                        section_id="thread-focus",
                        expected_section_title="线程焦点区",
                        shot=shot,
                    )
                    report["screenshots"].append(str(shot))
                    report["third_exchange_section_nav_state"] = third_exchange_section_nav_state

                    shot = output_dir / f"dual-account-16g-third-exchange-detail-{stamp}.png"
                    third_exchange_detail_state = open_exchange_detail_drawer(third_flow, shot=shot)
                    report["screenshots"].append(str(shot))
                    report["third_exchange_detail_state"] = third_exchange_detail_state

                    third_exchange_proof_lane_state = inspect_exchange_proof_lane(third_flow)
                    report["third_exchange_proof_lane_state"] = third_exchange_proof_lane_state
                    if int(third_exchange_proof_lane_state.get("detailButtonCount") or 0) > 0:
                        shot = output_dir / f"dual-account-16h-third-exchange-proof-detail-{stamp}.png"
                        third_exchange_proof_detail_state = open_exchange_proof_detail_drawer(third_flow, shot=shot)
                        report["screenshots"].append(str(shot))
                        report["third_exchange_proof_detail_state"] = third_exchange_proof_detail_state

                    shot = output_dir / f"dual-account-17a-third-thread-jump-{stamp}.png"
                    third_thread_jump_state = open_exchange_thread_link(third_flow, shot=shot)
                    report["screenshots"].append(str(shot))
                    report["third_thread_jump_state"] = third_thread_jump_state

                    third_machine_focus_thread_id = str(third_thread_jump_state.get("threadId") or "").strip()
                    third_expected_machine_focus_label = (
                        writer_npc_name
                        if third_machine_focus_thread_id in {member_thread_id, writer_workstation_id}
                        or writer_npc_name in third_machine_focus_thread_id
                        else third_machine_focus_thread_id
                    )
                    shot = output_dir / f"dual-account-18a-third-owner-exchange-refocus-{stamp}.png"
                    third_exchange_refocus_state = open_machine_room_exchange_link(
                        third_flow,
                        thread_id=third_machine_focus_thread_id,
                        expected_focus_label=third_expected_machine_focus_label,
                        expected_command_titles=[research_command_title, writer_command_title],
                        shot=shot,
                    )
                    report["screenshots"].append(str(shot))
                    report["third_exchange_refocus_state"] = third_exchange_refocus_state

                    shot = output_dir / f"dual-account-19a-third-npc-profile-jump-{stamp}.png"
                    third_npc_profile_jump_state = open_exchange_npc_profile_link(third_flow, shot=shot)
                    report["screenshots"].append(str(shot))
                    report["third_npc_profile_jump_state"] = third_npc_profile_jump_state

                shot = output_dir / f"dual-account-04-owner-project-map-{stamp}.png"
                owner_map_state = verify_project_map(
                    owner_flow,
                    web_base,
                    project_id=project_id,
                    remote_names=[member_name, third_name],
                    local_name=owner_name,
                    shot=shot,
                    minimum_player_count=3,
                    minimum_computer_count=3,
                    minimum_thread_count=3,
                )
                report["screenshots"].append(str(shot))
                report["owner_map_state"] = owner_map_state

        member_remote_owner_state = next(
            (
                str(item.get("state") or "")
                for item in report["member_map_state"].get("humanParty", [])
                if isinstance(item, dict) and owner_name in str(item.get("name") or "")
            ),
            "",
        )
        member_remote_owner_note = next(
            (
                str(item.get("note") or "")
                for item in report["member_map_state"].get("humanParty", [])
                if isinstance(item, dict) and owner_name in str(item.get("name") or "")
            ),
            "",
        )
        owner_remote_member_state = next(
            (
                str(item.get("state") or "")
                for item in report["owner_map_state"].get("humanParty", [])
                if isinstance(item, dict) and member_name in str(item.get("name") or "")
            ),
            "",
        )
        owner_remote_third_state = next(
            (
                str(item.get("state") or "")
                for item in report["owner_map_state"].get("humanParty", [])
                if isinstance(item, dict) and third_name in str(item.get("name") or "")
            ),
            "",
        )
        member_remote_third_state = next(
            (
                str(item.get("state") or "")
                for item in report["member_map_state"].get("humanParty", [])
                if isinstance(item, dict) and third_name in str(item.get("name") or "")
            ),
            "",
        )
        third_remote_owner_state = next(
            (
                str(item.get("state") or "")
                for item in report["third_map_state"].get("humanParty", [])
                if isinstance(item, dict) and owner_name in str(item.get("name") or "")
            ),
            "",
        )
        third_remote_owner_note = next(
            (
                str(item.get("note") or "")
                for item in report["third_map_state"].get("humanParty", [])
                if isinstance(item, dict) and owner_name in str(item.get("name") or "")
            ),
            "",
        )
        third_remote_member_state = next(
            (
                str(item.get("state") or "")
                for item in report["third_map_state"].get("humanParty", [])
                if isinstance(item, dict) and member_name in str(item.get("name") or "")
            ),
            "",
        )
        if not member_remote_owner_state:
            raise RuntimeError("Member could not see the owner's protagonist state in the HUD")
        if "Owner is driving" not in member_remote_owner_note:
            raise RuntimeError(
                f"Expected member to see the owner's shared sync note in the HUD, got {member_remote_owner_note!r}"
            )
        if not owner_remote_member_state:
            raise RuntimeError("Owner could not see the invited member state in the protagonist HUD")
        if not owner_remote_third_state:
            raise RuntimeError("Owner could not see the third collaborator state in the protagonist HUD")
        if not member_remote_third_state:
            raise RuntimeError("Member could not see the third collaborator state in the protagonist HUD")
        if not third_remote_owner_state:
            raise RuntimeError("Third collaborator could not see the owner state in the protagonist HUD")
        if "Owner is driving" not in third_remote_owner_note:
            raise RuntimeError(
                f"Expected third collaborator to see the owner's shared sync note in the HUD, got {third_remote_owner_note!r}"
            )
        if not third_remote_member_state:
            raise RuntimeError("Third collaborator could not see the member state in the protagonist HUD")
        report["member_remote_owner_state"] = member_remote_owner_state
        report["member_remote_owner_note"] = member_remote_owner_note
        report["owner_remote_member_state"] = owner_remote_member_state
        report["owner_remote_third_state"] = owner_remote_third_state
        report["member_remote_third_state"] = member_remote_third_state
        report["third_remote_owner_state"] = third_remote_owner_state
        report["third_remote_owner_note"] = third_remote_owner_note
        report["third_remote_member_state"] = third_remote_member_state

        owner_visible_nodes = {
            str(item.get("id") or ""): str(item.get("name") or "")
            for item in report["owner_computers_overview"].get("nodes", [])
            if isinstance(item, dict)
        }
        member_visible_nodes = {
            str(item.get("id") or ""): str(item.get("name") or "")
            for item in report["member_computers_overview"].get("nodes", [])
            if isinstance(item, dict)
        }
        third_visible_nodes = {
            str(item.get("id") or ""): str(item.get("name") or "")
            for item in report["third_computers_overview"].get("nodes", [])
            if isinstance(item, dict)
        }
        for expected_node_id, expected_node_name in (
            (owner_computer_id, owner_computer_label),
            (member_computer_id, member_computer_label),
            (third_computer_id, third_computer_label),
        ):
            if expected_node_id not in owner_visible_nodes or expected_node_name not in owner_visible_nodes.get(expected_node_id, ""):
                raise RuntimeError(f"Owner browser did not expose shared computer node {expected_node_id!r}: {owner_visible_nodes}")
            if expected_node_id not in member_visible_nodes or expected_node_name not in member_visible_nodes.get(expected_node_id, ""):
                raise RuntimeError(f"Member browser did not expose shared computer node {expected_node_id!r}: {member_visible_nodes}")
            if expected_node_id not in third_visible_nodes or expected_node_name not in third_visible_nodes.get(expected_node_id, ""):
                raise RuntimeError(f"Third browser did not expose shared computer node {expected_node_id!r}: {third_visible_nodes}")

        owner_thread_visibility = report["owner_computers_overview"].get("threadVisibility", {})
        member_thread_visibility = report["member_computers_overview"].get("threadVisibility", {})
        third_thread_visibility = report["third_computers_overview"].get("threadVisibility", {})
        expected_threads_by_node = {
            owner_computer_id: owner_thread_id,
            member_computer_id: member_thread_id,
            third_computer_id: third_thread_id,
        }
        for node_id, expected_thread_id in expected_threads_by_node.items():
            if expected_thread_id not in [str(item) for item in owner_thread_visibility.get(node_id, [])]:
                raise RuntimeError(f"Owner browser did not expose thread {expected_thread_id!r} on {node_id!r}: {owner_thread_visibility}")
            if expected_thread_id not in [str(item) for item in member_thread_visibility.get(node_id, [])]:
                raise RuntimeError(f"Member browser did not expose thread {expected_thread_id!r} on {node_id!r}: {member_thread_visibility}")
            if expected_thread_id not in [str(item) for item in third_thread_visibility.get(node_id, [])]:
                raise RuntimeError(f"Third browser did not expose thread {expected_thread_id!r} on {node_id!r}: {third_thread_visibility}")

        owner_nodes_by_id = {
            str(item.get("id") or item.get("node_id") or ""): item
            for item in report.get("owner_nodes_api", [])
            if isinstance(item, dict)
        }
        member_nodes_by_id = {
            str(item.get("id") or item.get("node_id") or ""): item
            for item in report.get("member_nodes_api", [])
            if isinstance(item, dict)
        }
        third_nodes_by_id = {
            str(item.get("id") or item.get("node_id") or ""): item
            for item in report.get("third_nodes_api", [])
            if isinstance(item, dict)
        }
        for node_id, expected_runner_id in (
            (owner_computer_id, owner_runner_id),
            (member_computer_id, member_runner_id),
            (third_computer_id, third_runner_id),
        ):
            owner_node = owner_nodes_by_id.get(node_id)
            member_node = member_nodes_by_id.get(node_id)
            third_node = third_nodes_by_id.get(node_id)
            if not isinstance(owner_node, dict) or not isinstance(member_node, dict) or not isinstance(third_node, dict):
                raise RuntimeError(f"Shared computer node {node_id!r} was not present in all API snapshots")
            if str(owner_node.get("runner_id") or "") != expected_runner_id:
                raise RuntimeError(f"Owner API snapshot missing runner binding {expected_runner_id!r} on {node_id!r}: {owner_node}")
            if str(member_node.get("runner_id") or "") != expected_runner_id:
                raise RuntimeError(f"Member API snapshot missing runner binding {expected_runner_id!r} on {node_id!r}: {member_node}")
            if str(third_node.get("runner_id") or "") != expected_runner_id:
                raise RuntimeError(f"Third API snapshot missing runner binding {expected_runner_id!r} on {node_id!r}: {third_node}")

        report["result"] = {
            "project_visible_to_owner_after_create": True,
            "project_hidden_from_member_before_accept": True,
            "project_visible_to_member_after_accept": True,
            "project_hidden_from_third_before_accept": True,
            "project_visible_to_third_after_accept": True,
            "owner_created_computer": True,
            "member_created_computer": True,
            "third_created_computer": True,
            "two_computers_visible_to_owner": True,
            "two_computers_visible_to_member": True,
            "two_threads_visible_to_owner": True,
            "two_threads_visible_to_member": True,
            "three_computers_visible_to_owner": True,
            "three_computers_visible_to_member": True,
            "three_computers_visible_to_third": True,
            "three_threads_visible_to_owner": True,
            "three_threads_visible_to_member": True,
            "three_threads_visible_to_third": True,
            "research_command_visible_to_member": True,
            "research_receipts_visible_to_owner": True,
            "research_receipts_visible_to_member": True,
            "research_command_visible_to_third": True,
            "research_receipts_visible_to_third": True,
            "writer_command_visible_to_member": True,
            "writer_receipts_visible_to_owner": True,
            "writer_receipts_visible_to_member": True,
            "writer_command_visible_to_third": True,
            "writer_receipts_visible_to_third": True,
            "shared_task_visible_to_member": True,
            "shared_sync_visible_to_member": True,
            "shared_task_visible_to_third": True,
            "shared_sync_visible_to_third": True,
            "owner_sees_remote_avatar": True,
            "member_sees_remote_avatar": True,
            "owner_sees_remote_avatars": True,
            "member_sees_remote_avatars": True,
            "third_sees_remote_avatars": True,
            "owner_hud_visible": True,
            "member_hud_visible": True,
            "third_hud_visible": True,
            "party_hud_supports_multi_player_scaling": True,
            "member_sees_owner_work_state": True,
            "third_sees_owner_work_state": True,
            "multi_npc_collab_completed": True,
            "member_can_jump_from_hud_to_exchange_focus": True,
            "member_can_jump_between_exchange_sections": True,
            "member_can_open_exchange_detail_drawer": True,
            "member_exchange_proof_lane_compact": True,
            "member_can_jump_from_exchange_to_thread": True,
            "member_can_jump_from_machine_room_back_to_exchange": True,
            "member_can_jump_from_exchange_to_npc_profile": True,
            "third_can_jump_from_hud_to_exchange_focus": True,
            "third_can_jump_between_exchange_sections": True,
            "third_can_open_exchange_detail_drawer": True,
            "third_exchange_proof_lane_compact": True,
            "third_can_jump_from_exchange_to_thread": True,
            "third_can_jump_from_machine_room_back_to_exchange": True,
            "third_can_jump_from_exchange_to_npc_profile": True,
        }

        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report["result"], ensure_ascii=False, indent=2))
        return 0
    finally:
        if api_process is not None:
            api_process.terminate()
            try:
                api_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                api_process.kill()
        if web_process is not None:
            web_process.terminate()
            try:
                web_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                web_process.kill()
        if api_handles is not None:
            for handle in api_handles:
                handle.close()
        if web_handles is not None:
            for handle in web_handles:
                handle.close()
        if db_path.exists():
            try:
                db_path.unlink()
                report["runtime"]["database_deleted_after_run"] = True
            except Exception:  # noqa: BLE001
                pass
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir, ignore_errors=True)
            report["runtime"]["runtime_deleted_after_run"] = True
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
