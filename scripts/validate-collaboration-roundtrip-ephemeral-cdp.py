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
CDP_HELPER_PATH = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
APPS_API_DIR = REPO_ROOT / "apps" / "api"
ADAPTER_SCRIPT_PATH = SCRIPT_DIR / "platform-workstation-adapter.py"
MOCK_EXECUTOR_PATH = SCRIPT_DIR / "mock-workstation-executor.py"
REAL_PROVIDER_EXECUTOR_PATH = SCRIPT_DIR / "platform-provider-executor.py"

spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helper: {CDP_HELPER_PATH}")
cdp_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helper)


PROJECTS_HOME_MARKERS = ("推荐下一步", "新建项目")
CREATE_PROJECT_HINT = "创建项目并进入"
THREAD_FORM_HINT = "手动登记一个真实线程"
EXCHANGE_FORM_HINT = "下发协作指令"
PREVIEW_BUTTON_TEXT = "先预演协作指令"
FORMAL_SEND_BUTTON_TEXT = "正式发送到协作池"
PREVIEW_RESULT_HEADING = "最近一次总派工预演"
RECEIPTS_HEADING = "回执结果区"
LOGIN_BUTTON_TEXT = "进入平台"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an isolated collaboration round-trip acceptance flow in a temporary live environment.")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts"))
    parser.add_argument("--viewport-width", type=int, default=1800)
    parser.add_argument("--viewport-height", type=int, default=1100)
    parser.add_argument("--provider", default="claude", choices=["claude", "codex", "qwen"])
    parser.add_argument("--executor-mode", default="mock", choices=["mock", "real"])
    return parser.parse_args()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    token: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
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
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {body[:1600]}") from exc


def wait_for_http(url: str, *, timeout_seconds: float = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def start_process(command: list[str], *, cwd: Path, stdout_path: Path, stderr_path: Path, env_overrides: dict[str, str]) -> tuple[subprocess.Popen[str], object, object]:
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


def wait_for_page_text(cdp: object, text: str, *, timeout_seconds: float = 45) -> None:
    wait_for(cdp, f"document.body && document.body.innerText.includes({json.dumps(text, ensure_ascii=False)})", timeout_seconds=timeout_seconds)


def screenshot(cdp: object, output: Path, *, capture_beyond_viewport: bool = True) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": capture_beyond_viewport})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def click_by_text(cdp: object, text: str, *, selector: str = "button, a", timeout_seconds: float = 20) -> dict[str, object]:
    expr = f"""
    (() => {{
      const needle = {json.dumps(text, ensure_ascii=False)};
      const items = Array.from(document.querySelectorAll({json.dumps(selector)}));
      const el = items.find((item) => (item.innerText || item.textContent || '').replace(/\s+/g, ' ').includes(needle));
      if (!el) return {{ ok: false, reason: 'missing', needle, body: (document.body && document.body.innerText || '').slice(0, 1500) }};
      if ('disabled' in el && el.disabled) return {{ ok: false, reason: 'disabled', needle }};
      el.scrollIntoView({{ block: 'center', inline: 'center' }});
      const rect = el.getBoundingClientRect();
      return {{ ok: true, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
    }})()
    """
    point = wait_for(cdp, expr, timeout_seconds=timeout_seconds)
    if not isinstance(point, dict) or not point.get("ok"):
        raise RuntimeError(f"Could not find clickable text {text!r}: {point}")
    x = float(point["x"])
    y = float(point["y"])
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return point


def fill_form_field(cdp: object, form_hint: str, name: str, value: str) -> None:
    result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const formNeedle = {json.dumps(form_hint, ensure_ascii=False)};
          const fieldName = {json.dumps(name)};
          const nextValue = {json.dumps(value, ensure_ascii=False)};
          const form = Array.from(document.querySelectorAll('form')).find((item) => ((item.innerText || item.textContent || '')).includes(formNeedle));
          if (!form) return {{ ok: false, reason: 'missing-form', formNeedle, body: (document.body && document.body.innerText || '').slice(0, 1500) }};
          const field = form.querySelector(`[name="${{CSS.escape(fieldName)}}"]`);
          if (!field) return {{ ok: false, reason: 'missing-field', fieldName }};
          field.scrollIntoView({{ block: 'center', inline: 'center' }});
          field.focus();
          field.value = nextValue;
          field.dispatchEvent(new Event('input', {{ bubbles: true }}));
          field.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return {{ ok: true, tag: field.tagName.toLowerCase(), value: field.value }};
        }})()
        """,
    )
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"Could not fill field {name!r} in form {form_hint!r}: {result}")


def click_form_button(cdp: object, form_hint: str, button_text: str, *, timeout_seconds: float = 20) -> dict[str, object]:
    expr = f"""
    (() => {{
      const formNeedle = {json.dumps(form_hint, ensure_ascii=False)};
      const buttonNeedle = {json.dumps(button_text, ensure_ascii=False)};
      const form = Array.from(document.querySelectorAll('form')).find((item) => ((item.innerText || item.textContent || '')).includes(formNeedle));
      if (!form) return {{ ok: false, reason: 'missing-form', formNeedle }};
      const button = Array.from(form.querySelectorAll('button')).find((item) => ((item.innerText || item.textContent || '')).replace(/\s+/g, ' ').includes(buttonNeedle));
      if (!button) return {{ ok: false, reason: 'missing-button', buttonNeedle }};
      if (button.disabled) return {{ ok: false, reason: 'disabled', buttonText: (button.innerText || button.textContent || '').trim() }};
      button.scrollIntoView({{ block: 'center', inline: 'center' }});
      const rect = button.getBoundingClientRect();
      return {{ ok: true, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
    }})()
    """
    point = wait_for(cdp, expr, timeout_seconds=timeout_seconds)
    if not isinstance(point, dict) or not point.get("ok"):
        raise RuntimeError(f"Could not click button {button_text!r} in form {form_hint!r}: {point}")
    x = float(point["x"])
    y = float(point["y"])
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return point


def submit_form_by_selector(cdp: object, selector: str) -> None:
    submitted = cdp_eval(
        cdp,
        f"""
        (() => {{
          const form = document.querySelector({json.dumps(selector)});
          if (!form) return false;
          form.requestSubmit();
          return true;
        }})()
        """,
    )
    if not submitted:
        raise RuntimeError(f"Could not submit form {selector!r}")


def wait_for_selector(cdp: object, selector: str, *, timeout_seconds: float = 30) -> None:
    wait_for(
        cdp,
        f"document.readyState === 'complete' && !!document.querySelector({json.dumps(selector)})",
        timeout_seconds=timeout_seconds,
    )


def read_machine_room_token_state(cdp: object, thread_id: str) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const threadId = {json.dumps(thread_id)};
          const card = document.querySelector(`[data-machine-thread-card="${{CSS.escape(threadId)}}"]`);
          const command = card?.querySelector(`[data-adapter-command="${{CSS.escape(threadId)}}"]`);
          const banner = card?.querySelector(`[data-workstation-token-banner="${{CSS.escape(threadId)}}"]`);
          const issueForm = card?.querySelector(`[data-workstation-token-issue-form="${{CSS.escape(threadId)}}"]`);
          const revokeForm = card?.querySelector(`[data-workstation-token-revoke-form="${{CSS.escape(threadId)}}"]`);
          const lastAck = card?.querySelector(`[data-machine-thread-last-ack="${{CSS.escape(threadId)}}"]`);
          const lastResult = card?.querySelector(`[data-machine-thread-last-result="${{CSS.escape(threadId)}}"]`);
          const issueButton = issueForm?.querySelector('button');
          const revokeButton = revokeForm?.querySelector('button');
          const cardText = card?.innerText || card?.textContent || '';
          const commandText = command?.innerText || command?.textContent || '';
          return {{
            cardVisible: !!card,
            commandText,
            hasTokenFlagInCommand: commandText.includes('--token '),
            bannerVisible: !!banner,
            issueButtonText: (issueButton?.innerText || issueButton?.textContent || '').trim(),
            revokeDisabled: !!revokeButton?.disabled,
            hasRecentUseLabel: cardText.includes('最近使用'),
            hasRecentAckLabel: !!lastAck && (lastAck.getClientRects().length > 0 || (lastAck.textContent || '').includes('最近回执')),
            hasRecentResultLabel: !!lastResult && (lastResult.getClientRects().length > 0 || (lastResult.textContent || '').includes('最近最终回复')),
            recentAckText: (lastAck?.innerText || lastAck?.textContent || '').trim(),
            recentResultText: (lastResult?.innerText || lastResult?.textContent || '').trim(),
            cardText: cardText.slice(0, 4000),
          }};
        }})()
        """,
    )
    return state if isinstance(state, dict) else {}


def current_url(cdp: object) -> str:
    value = cdp_eval(cdp, "location.href")
    return str(value or "")


def wait_for_url_contains(cdp: object, fragment: str, *, timeout_seconds: float = 30) -> str:
    deadline = time.time() + timeout_seconds
    last_url = ""
    while time.time() < deadline:
        last_url = current_url(cdp)
        if fragment in last_url:
            return last_url
        time.sleep(0.3)
    raise RuntimeError(f"URL did not contain {fragment!r}: {last_url}")


def get_adapter_token_status(api_base: str, project_id: str, workstation_id: str, token: str) -> dict[str, object]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/thread-workstations/{quote(workstation_id, safe='')}/adapter-token",
        token=token,
    )
    data = payload.get("data") if isinstance(payload, dict) else payload
    return data if isinstance(data, dict) else {}


def scroll_text_into_view(cdp: object, text: str, *, selector: str = "li, div, section, article", timeout_seconds: float = 20) -> None:
    result = wait_for(
        cdp,
        f"""
        (() => {{
          const needle = {json.dumps(text, ensure_ascii=False)};
          const items = Array.from(document.querySelectorAll({json.dumps(selector)}));
          const el = items.find((item) => ((item.innerText || item.textContent || '')).includes(needle));
          if (!el) return false;
          el.scrollIntoView({{ block: 'center', inline: 'nearest' }});
          return true;
        }})()
        """,
        timeout_seconds=timeout_seconds,
    )
    if result is not True:
        raise RuntimeError(f"Could not scroll text into view: {text}")


def api_register(api_base: str, email: str, password: str, name: str) -> dict[str, object]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/auth/register",
        method="POST",
        payload={"email": email, "password": password, "name": name, "global_role": "member"},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("Register response did not include user payload")
    return data


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


def list_project_messages(api_base: str, project_id: str, token: str) -> list[dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/messages?project_id={quote(project_id)}",
        token=token,
    )
    data = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def upsert_provider_execution_config(
    api_base: str,
    *,
    project_id: str,
    token: str,
    provider_id: str,
    provider_label: str,
    executor_command: str,
    executor_cwd: str,
    executor_timeout_seconds: int,
) -> dict[str, object]:
    existing_payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/ai-providers",
        token=token,
    )
    existing = existing_payload.get("data") if isinstance(existing_payload, dict) else []
    current = None
    if isinstance(existing, list):
        current = next(
            (
                item
                for item in existing
                if isinstance(item, dict)
                and str(item.get("id") or item.get("label") or "").strip().lower() == provider_id.strip().lower()
            ),
            None,
        )
    metadata = {
        "adapter": {
            "executor_command": executor_command,
            "executor_cwd": executor_cwd,
            "executor_timeout_seconds": executor_timeout_seconds,
        }
    }
    endpoint = f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/ai-providers"
    if isinstance(current, dict):
        payload = request_json(
            f"{endpoint}/{quote(str(current.get('id') or provider_id))}",
            method="PATCH",
            token=token,
            payload={"metadata": metadata, "model": provider_id},
        )
    else:
        payload = request_json(
            endpoint,
            method="POST",
            token=token,
            payload={
                "id": provider_id,
                "label": provider_label,
                "kind": provider_id,
                "model": provider_id,
                "metadata": metadata,
            },
        )
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def update_workstation_execution_config(
    api_base: str,
    *,
    project_id: str,
    workstation_id: str,
    token: str,
    metadata: dict[str, object],
) -> dict[str, object]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/thread-workstations/{quote(workstation_id)}",
        method="PATCH",
        token=token,
        payload={"metadata": metadata},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def pick_message(messages: list[dict[str, object]], *, title: str, message_type: str) -> dict[str, object]:
    lowered_type = message_type.lower()
    for item in reversed(messages):
        if str(item.get("message_type") or "").lower() == lowered_type and str(item.get("title") or "") == title:
            return item
    raise RuntimeError(f"Could not find message type={message_type!r} title={title!r}")


def run_adapter(
    *,
    api_base: str,
    project_id: str,
    workstation_id: str,
    provider: str,
    output_dir: Path,
    workstation_token: str | None = None,
    ack_note: str | None = None,
    final_note: str | None = None,
    executor_mode: str = "mock",
    executor_cwd: str | None = None,
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
        str(ack_note or ""),
    ]
    if workstation_token:
        command.extend(["--token", workstation_token])
    if executor_mode == "mock":
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
                str(final_note or ""),
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


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{args.provider}"
    runtime_dir = Path(tempfile.mkdtemp(prefix="ai-collab-roundtrip-ephemeral-"))
    db_path = runtime_dir / "ai_collab_roundtrip.db"
    api_port = find_free_port()
    web_port = find_free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    web_base = f"http://127.0.0.1:{web_port}"
    email = f"roundtrip-{stamp}@local.dev"
    password = "password"
    user_name = "Ephemeral Roundtrip User"
    project_name = f"隔离验收协作闭环-{stamp}"
    thread_id = f"{args.provider}-ephemeral-writer-{stamp}"
    thread_name = f"{args.provider.title()} 写作者"
    command_title = f"隔离验收：协作写作 {stamp}"
    command_body = "请先回一条最小回执，再把一段可直接展示在最终回复池里的短结果写回平台。"
    ack_note = "最小回执：已接单，正在整理协作写作结果。"
    final_note = "最终回复：多电脑多 AI 协作平台先统一派工，再由线程回写最小回执和最终结果，能明显减少来回催办。"

    api_stdout = output_dir / f"ephemeral-roundtrip-api-{stamp}.out.log"
    api_stderr = output_dir / f"ephemeral-roundtrip-api-{stamp}.err.log"
    web_stdout = output_dir / f"ephemeral-roundtrip-web-{stamp}.out.log"
    web_stderr = output_dir / f"ephemeral-roundtrip-web-{stamp}.err.log"

    api_env = {
        "APP_ENV": "local",
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "DATABASE_AUTO_CREATE": "true",
        "DATABASE_AUTO_SEED": "true",
        "SECRET_KEY": "ephemeral-roundtrip-secret",
        "TOKEN_ENCRYPTION_KEY": "ephemeral-roundtrip-token-key-123456",
        "ALLOW_BOOTSTRAP_AUTH": "false",
    }
    web_env = {
        "NEXT_PUBLIC_API_BASE_URL": api_base,
    }

    api_process = None
    web_process = None
    api_handles: tuple[object, object] | None = None
    web_handles: tuple[object, object] | None = None
    cdp = None
    edge_process = None
    profile_dir: Path | None = None
    report: dict[str, object] = {}
    report_path = output_dir / f"ephemeral-roundtrip-validation-report-{stamp}.json"
    screenshots: list[str] = []
    exit_code = 1

    try:
        api_process, api_stdout_handle, api_stderr_handle = start_process(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
            cwd=APPS_API_DIR,
            stdout_path=api_stdout,
            stderr_path=api_stderr,
            env_overrides=api_env,
        )
        api_handles = (api_stdout_handle, api_stderr_handle)
        wait_for_http(f"{api_base}/openapi.json", timeout_seconds=60)

        api_register(api_base, email, password, user_name)
        owner_token, user = api_login(api_base, email, password)

        web_process, web_stdout_handle, web_stderr_handle = start_process(
            ["cmd.exe", "/c", "npm --workspace apps/web run start -- --hostname 127.0.0.1 --port " + str(web_port)],
            cwd=REPO_ROOT,
            stdout_path=web_stdout,
            stderr_path=web_stderr,
            env_overrides=web_env,
        )
        web_handles = (web_stdout_handle, web_stderr_handle)
        wait_for_http(f"{web_base}/login", timeout_seconds=90)

        port = cdp_helper.find_free_port()
        profile_dir = Path(tempfile.mkdtemp(prefix="codex-collab-roundtrip-cdp-"))
        edge_process = subprocess.Popen(
            [
                str(cdp_helper.find_edge()),
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
        targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        if not isinstance(targets, list) or not targets:
            cdp_helper.request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
            targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page"), None)
        if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
            raise RuntimeError("No CDP page target available")

        cdp = cdp_helper.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
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

        cdp.send("Page.navigate", {"url": f"{web_base}/login?returnTo={quote('/projects', safe='')}"})
        wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('form')")
        shot = output_dir / f"ephemeral-roundtrip-01-login-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        fill_form_field(cdp, "邮箱", "email", email)
        fill_form_field(cdp, "邮箱", "password", password)
        click_by_text(cdp, LOGIN_BUTTON_TEXT, selector="button[type=submit], button")
        for marker in PROJECTS_HOME_MARKERS:
            wait_for_page_text(cdp, marker, timeout_seconds=45)
        shot = output_dir / f"ephemeral-roundtrip-02-projects-home-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_by_text(cdp, "新建项目", selector="button, a")
        wait_for_page_text(cdp, CREATE_PROJECT_HINT, timeout_seconds=30)
        fill_form_field(cdp, CREATE_PROJECT_HINT, "name", project_name)
        fill_form_field(cdp, CREATE_PROJECT_HINT, "description", "隔离 live 环境里验证 preview、正式发送、最小回执和最终回复。")
        fill_form_field(cdp, CREATE_PROJECT_HINT, "local_git_url", str(REPO_ROOT))
        click_form_button(cdp, CREATE_PROJECT_HINT, CREATE_PROJECT_HINT)
        project_url = wait_for_url_contains(cdp, "/projects/", timeout_seconds=45)
        project_id = project_url.split("/projects/", 1)[1].split("?", 1)[0].split("/", 1)[0]
        wait_for_page_text(cdp, project_name, timeout_seconds=45)
        shot = output_dir / f"ephemeral-roundtrip-03-created-project-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        cdp.send("Page.navigate", {"url": f"{web_base}/projects/{project_id}?panel=team&tab=machine-room"})
        wait_for_page_text(cdp, THREAD_FORM_HINT, timeout_seconds=45)
        provider_label = {"claude": "Claude", "codex": "Codex", "qwen": "Qwen"}.get(args.provider, args.provider.title())
        fill_form_field(cdp, THREAD_FORM_HINT, "id", thread_id)
        fill_form_field(cdp, THREAD_FORM_HINT, "name", thread_name)
        fill_form_field(cdp, THREAD_FORM_HINT, "ai_provider_id", args.provider)
        fill_form_field(cdp, THREAD_FORM_HINT, "ai_provider", provider_label)
        fill_form_field(cdp, THREAD_FORM_HINT, "model", args.provider)
        fill_form_field(cdp, THREAD_FORM_HINT, "responsibility", "隔离验收写作者")
        fill_form_field(cdp, THREAD_FORM_HINT, "notes", f"临时 live 环境里的 {provider_label} 验收线程，用于验证协作闭环。")
        click_form_button(cdp, THREAD_FORM_HINT, "登记线程")
        wait_for_page_text(cdp, thread_name, timeout_seconds=45)
        shot = output_dir / f"ephemeral-roundtrip-04-thread-registered-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        token_issue_form_selector = f'[data-workstation-token-issue-form="{thread_id}"]'
        token_command_selector = f'[data-adapter-command="{thread_id}"]'
        token_card_selector = f'[data-machine-thread-card="{thread_id}"]'
        wait_for_selector(cdp, token_issue_form_selector, timeout_seconds=45)
        wait_for_selector(cdp, token_command_selector, timeout_seconds=45)

        if args.executor_mode == "real":
            provider_command = subprocess.list2cmdline(
                [
                    sys.executable,
                    str(REAL_PROVIDER_EXECUTOR_PATH),
                    "@PROMPT_FILE@",
                    "--provider",
                    "@PROVIDER@",
                    "--message-id",
                    "@MESSAGE_ID@",
                    "--model",
                    "@MODEL@",
                    "--cwd",
                    str(runtime_dir),
                ]
            )
            provider_data = upsert_provider_execution_config(
                api_base,
                project_id=project_id,
                token=owner_token,
                provider_id=args.provider,
                provider_label=provider_label,
                executor_command=provider_command,
                executor_cwd=str(runtime_dir),
                executor_timeout_seconds=420,
            )
            workstation_data = update_workstation_execution_config(
                api_base,
                project_id=project_id,
                workstation_id=thread_id,
                token=owner_token,
                metadata={
                    "adapter": {
                        "executor_timeout_seconds": 420,
                    }
                },
            )
        else:
            provider_data = {}
            workstation_data = {}

        submit_form_by_selector(cdp, token_issue_form_selector)
        issued_url = wait_for_url_contains(cdp, "adapter_token=", timeout_seconds=45)
        workstation_token = parse_qs(urlparse(issued_url).query).get("adapter_token", [""])[0].strip()
        if not workstation_token:
            raise RuntimeError(f"Machine-room issue flow did not expose adapter_token in URL: {issued_url}")
        machine_room_after_issue = read_machine_room_token_state(cdp, thread_id)
        status_after_issue = get_adapter_token_status(api_base, project_id, thread_id, owner_token)
        if not machine_room_after_issue.get("hasTokenFlagInCommand"):
            raise RuntimeError(f"Machine-room command is missing --token after issue: {machine_room_after_issue}")
        if not machine_room_after_issue.get("bannerVisible"):
            raise RuntimeError(f"One-time token banner did not appear after issue: {machine_room_after_issue}")
        if not status_after_issue.get("token_available"):
            raise RuntimeError(f"Adapter token status did not become available after issue: {status_after_issue}")
        shot = output_dir / f"ephemeral-roundtrip-04-machine-room-token-issued-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        cdp.send(
            "Page.navigate",
            {"url": f"{web_base}/projects/{project_id}?panel=team&tab=exchange&exchange_composer=dispatch"},
        )
        wait_for_page_text(cdp, EXCHANGE_FORM_HINT, timeout_seconds=45)
        fill_form_field(cdp, EXCHANGE_FORM_HINT, "recipient_id", thread_id)
        fill_form_field(cdp, EXCHANGE_FORM_HINT, "title", command_title)
        fill_form_field(cdp, EXCHANGE_FORM_HINT, "body", command_body)
        shot = output_dir / f"ephemeral-roundtrip-05-exchange-before-preview-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_form_button(cdp, EXCHANGE_FORM_HINT, PREVIEW_BUTTON_TEXT)
        wait_for_page_text(cdp, PREVIEW_RESULT_HEADING, timeout_seconds=45)
        shot = output_dir / f"ephemeral-roundtrip-06-exchange-after-preview-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        fill_form_field(cdp, EXCHANGE_FORM_HINT, "recipient_id", thread_id)
        fill_form_field(cdp, EXCHANGE_FORM_HINT, "title", command_title)
        fill_form_field(cdp, EXCHANGE_FORM_HINT, "body", command_body)
        click_form_button(cdp, EXCHANGE_FORM_HINT, FORMAL_SEND_BUTTON_TEXT)
        wait_for_page_text(cdp, command_title, timeout_seconds=45)
        shot = output_dir / f"ephemeral-roundtrip-07-exchange-after-send-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        messages_after_send = list_project_messages(api_base, project_id, owner_token)
        command_message = pick_message(messages_after_send, title=command_title, message_type="agent_command")

        adapter_result = run_adapter(
            api_base=api_base,
            project_id=project_id,
            workstation_id=thread_id,
            provider=args.provider,
            output_dir=output_dir / "ephemeral-workstation-inbox",
            workstation_token=workstation_token,
            ack_note=ack_note,
            final_note=final_note,
            executor_mode=args.executor_mode,
            executor_cwd=str(runtime_dir),
        )

        cdp.send(
            "Page.navigate",
            {"url": f"{web_base}/projects/{project_id}?panel=team&tab=exchange&exchange_section=receipts"},
        )
        wait_for_page_text(cdp, RECEIPTS_HEADING, timeout_seconds=45)
        wait_for_page_text(cdp, f"最小回执：{command_title}", timeout_seconds=45)
        wait_for_page_text(cdp, f"最终回复：{command_title}", timeout_seconds=45)
        wait_for(
            cdp,
            f"""
            (() => {{
              const section = document.querySelector('[data-exchange-section="receipts"][data-exchange-section-active="true"]');
              if (!section) return false;
              const title = {json.dumps(command_title, ensure_ascii=False)};
              const receiptItems = Array.from(section.querySelectorAll('[data-exchange-receipt-item]'));
              const matchedKinds = receiptItems
                .filter((item) => (item.textContent || '').includes(title))
                .map((item) => item.getAttribute('data-exchange-receipt-kind') || '');
              return matchedKinds.includes('最小回执') && matchedKinds.includes('最终回复');
            }})()
            """,
            timeout_seconds=45,
        )
        scroll_text_into_view(cdp, f"最终回复：{command_title}")
        shot = output_dir / f"ephemeral-roundtrip-08-exchange-after-roundtrip-{stamp}.png"
        screenshot(cdp, shot, capture_beyond_viewport=False)
        screenshots.append(str(shot))

        cdp.send("Page.navigate", {"url": f"{web_base}/projects/{project_id}?panel=team&tab=machine-room"})
        wait_for_selector(cdp, token_card_selector, timeout_seconds=45)
        wait_for(
            cdp,
            f"""
            (() => {{
              const card = document.querySelector({json.dumps(token_card_selector)});
              const text = card?.innerText || card?.textContent || '';
              return text.includes('最近使用');
            }})()
            """,
            timeout_seconds=45,
        )
        machine_room_after_use = read_machine_room_token_state(cdp, thread_id)
        status_after_use = get_adapter_token_status(api_base, project_id, thread_id, owner_token)
        if not status_after_use.get("last_used_at"):
            raise RuntimeError(f"Adapter token last_used_at was not recorded after real adapter use: {status_after_use}")
        if not machine_room_after_use.get("hasRecentUseLabel"):
            raise RuntimeError(f"Machine-room card is missing recent-use label after adapter use: {machine_room_after_use}")
        if not machine_room_after_use.get("hasRecentAckLabel"):
            raise RuntimeError(f"Machine-room card is missing recent-ack label after adapter use: {machine_room_after_use}")
        if not machine_room_after_use.get("hasRecentResultLabel"):
            raise RuntimeError(f"Machine-room card is missing recent-final label after adapter use: {machine_room_after_use}")
        if machine_room_after_use.get("hasTokenFlagInCommand"):
            raise RuntimeError(f"One-time token leaked into later machine-room command view: {machine_room_after_use}")
        shot = output_dir / f"ephemeral-roundtrip-09-machine-room-after-token-use-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        all_messages = list_project_messages(api_base, project_id, owner_token)
        ack_message = pick_message(all_messages, title=command_title, message_type="agent_ack")
        result_message = pick_message(all_messages, title=command_title, message_type="agent_result")
        if str(ack_message.get("body") or "") != ack_note:
            raise RuntimeError(f"Ack body mismatch: expected={ack_note!r} actual={str(ack_message.get('body') or '')!r}")
        actual_final_body = str(result_message.get("body") or "")
        adapter_final_body = ""
        receipts = adapter_result.get("receipts") if isinstance(adapter_result, dict) else []
        if isinstance(receipts, list):
            for item in receipts:
                receipt = item.get("receipt") if isinstance(item, dict) else None
                if isinstance(receipt, dict) and str(receipt.get("message_type") or "").lower() == "agent_result":
                    adapter_final_body = str(receipt.get("body") or "").strip()
        if args.executor_mode == "mock":
            if actual_final_body != final_note:
                raise RuntimeError(f"Final reply mismatch: expected={final_note!r} actual={actual_final_body!r}")
        else:
            if not actual_final_body.startswith("最终回复："):
                raise RuntimeError(f"Final reply is missing required prefix: {actual_final_body!r}")
            if adapter_final_body and actual_final_body != adapter_final_body:
                raise RuntimeError(
                    "Final reply mismatch between UI/API message and adapter receipt: "
                    f"adapter={adapter_final_body!r} actual={actual_final_body!r}"
                )

        report = {
            "validated_at": stamp,
            "runtime": {
                "api_base": api_base,
                "web_base": web_base,
                "api_port": api_port,
                "web_port": web_port,
                "database_path": str(db_path),
                "database_deleted_after_run": False,
            },
            "user": user,
            "project": {"id": project_id, "name": project_name},
            "thread": {"id": thread_id, "name": thread_name},
            "provider_execution": {"provider": args.provider, "executor_mode": args.executor_mode},
            "execution_config": {
                "provider": provider_data,
                "workstation": workstation_data,
            },
            "workstation_token": {
                "issued": {
                    "token_available": status_after_issue.get("token_available"),
                    "issued_at": status_after_issue.get("issued_at"),
                    "last_used_at": status_after_issue.get("last_used_at"),
                    "banner_visible": machine_room_after_issue.get("bannerVisible"),
                    "command_contains_token": machine_room_after_issue.get("hasTokenFlagInCommand"),
                    "issue_button_text": machine_room_after_issue.get("issueButtonText"),
                },
                "after_use": {
                    "token_available": status_after_use.get("token_available"),
                    "issued_at": status_after_use.get("issued_at"),
                    "last_used_at": status_after_use.get("last_used_at"),
                    "recent_use_visible": machine_room_after_use.get("hasRecentUseLabel"),
                    "recent_ack_visible": machine_room_after_use.get("hasRecentAckLabel"),
                    "recent_ack_text": machine_room_after_use.get("recentAckText"),
                    "recent_final_visible": machine_room_after_use.get("hasRecentResultLabel"),
                    "recent_final_text": machine_room_after_use.get("recentResultText"),
                    "command_contains_token": machine_room_after_use.get("hasTokenFlagInCommand"),
                    "issue_button_text": machine_room_after_use.get("issueButtonText"),
                },
            },
            "command": {
                "id": command_message["id"],
                "title": command_title,
                "status": command_message.get("status"),
            },
            "adapter": adapter_result,
            "ack": {
                "expected_body": ack_note,
                "message_id": ack_message.get("id"),
                "body": ack_message.get("body"),
            },
            "final_reply": {
                "expected_body": final_note if args.executor_mode == "mock" else (adapter_final_body or None),
                "message_id": result_message.get("id"),
                "body": result_message.get("body"),
            },
            "message_counts": {
                "all": len(all_messages),
                "agent_command": sum(1 for item in all_messages if str(item.get("message_type") or "").lower() == "agent_command"),
                "agent_ack": sum(1 for item in all_messages if str(item.get("message_type") or "").lower() == "agent_ack"),
                "agent_result": sum(1 for item in all_messages if str(item.get("message_type") or "").lower() == "agent_result"),
            },
            "screenshots": screenshots,
            "cleanup": {"temp_runtime_deleted": False},
        }
        exit_code = 0
    finally:
        if cdp is not None:
            try:
                cdp.close()
            except Exception:
                pass
        if edge_process is not None:
            try:
                edge_process.terminate()
                edge_process.wait(timeout=10)
            except Exception:
                try:
                    edge_process.kill()
                except Exception:
                    pass
        if profile_dir is not None:
            shutil.rmtree(profile_dir, ignore_errors=True)
        if web_process is not None:
            try:
                web_process.terminate()
                web_process.wait(timeout=10)
            except Exception:
                try:
                    web_process.kill()
                except Exception:
                    pass
        if api_process is not None:
            try:
                api_process.terminate()
                api_process.wait(timeout=10)
            except Exception:
                try:
                    api_process.kill()
                except Exception:
                    pass
        if web_handles is not None:
            for handle in web_handles:
                try:
                    handle.close()
                except Exception:
                    pass
        if api_handles is not None:
            for handle in api_handles:
                try:
                    handle.close()
                except Exception:
                    pass
        db_deleted = False
        try:
            if db_path.exists():
                db_path.unlink()
                db_deleted = True
        except Exception:
            db_deleted = False
        shutil.rmtree(runtime_dir, ignore_errors=True)
        if report:
            report.setdefault("cleanup", {})["temp_runtime_deleted"] = not runtime_dir.exists()
            report.setdefault("runtime", {})["database_deleted_after_run"] = db_deleted
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if report:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"REPORT_PATH={report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
