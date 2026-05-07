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
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_HELPER_PATH = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"

spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helper: {CDP_HELPER_PATH}")
cdp_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helper)


WORKSHOP_FORM_TITLE = "把当前工位交给 AI 规划"
SCHEDULE_FORM_TITLE = "让 AI 安排今天"
EXCHANGE_FORM_TITLE = "下发协作指令"
NPC_PANEL_TITLE = "对话预览"
NPC_DIALOG_OPEN_BUTTON = "打开对话框"
NPC_DIALOG_PREVIEW_BUTTON = "先预演发给这个 NPC"
NPC_DIALOG_PREVIEW_HEADING = "最近一次发给"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate collaboration preview-only dispatch flows through the real browser.")
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


def read_agent_commands(api_base: str, project_id: str, token: str) -> list[dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/messages?project_id={quote(project_id)}&message_type=agent_command",
        token=token,
    )
    data = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def read_human_review_requests(api_base: str, project_id: str, token: str) -> list[dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/messages?project_id={quote(project_id)}&message_type=human_review_request",
        token=token,
    )
    data = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


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


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def click_by_text(cdp: object, text: str, *, selector: str = "button, a", timeout_seconds: float = 20) -> dict[str, object]:
    expr = f"""
    (() => {{
      const needle = {json.dumps(text)};
      const items = Array.from(document.querySelectorAll({json.dumps(selector)}));
      const el = items.find((item) => (item.innerText || item.textContent || '').replace(/\s+/g, ' ').includes(needle));
      if (!el) return {{ ok: false, reason: 'missing', needle, body: (document.body && document.body.innerText || '').slice(0, 1200) }};
      if ('disabled' in el && el.disabled) {{
        return {{
          ok: false,
          reason: 'disabled',
          needle,
          text: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 160),
        }};
      }}
      el.scrollIntoView({{ block: 'center', inline: 'center' }});
      const rect = el.getBoundingClientRect();
      return {{
        ok: true,
        text: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 160),
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
      }};
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



def click_selector(cdp: object, selector: str, *, timeout_seconds: float = 20) -> dict[str, object]:
    expr = f"""
    (() => {{
      const el = document.querySelector({json.dumps(selector)});
      if (!el) return null;
      if ('disabled' in el && el.disabled) return {{ ok: false, reason: 'disabled', selector }};
      el.scrollIntoView({{ block: 'center', inline: 'center' }});
      const rect = el.getBoundingClientRect();
      return {{
        ok: true,
        text: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 160),
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
      }};
    }})()
    """
    point = wait_for(cdp, expr, timeout_seconds=timeout_seconds)
    if not isinstance(point, dict) or not point.get('ok'):
        raise RuntimeError(f"Could not click selector {selector!r}: {point}")
    x = float(point['x'])
    y = float(point['y'])
    cdp.send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x, 'y': y})
    cdp.send('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
    cdp.send('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
    return point


def open_exchange_overview(cdp: object, *, timeout_seconds: float = 45) -> None:
    wait_for(
        cdp,
        "document.readyState === 'complete' && !!document.querySelector('[data-exchange-section=\"overview\"]') && !!document.querySelector('[data-exchange-composer-toggle=\"dispatch\"]')",
        timeout_seconds=timeout_seconds,
    )


def open_exchange_composer(cdp: object, composer_mode: str, *, timeout_seconds: float = 45) -> None:
    form_selector = '[data-project-sync-form=\"1\"]' if composer_mode == 'sync' else '[data-exchange-command-form=\"1\"]'
    toggle_selector = f'[data-exchange-composer-toggle=\"{composer_mode}\"]'
    result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const existing = document.querySelector({json.dumps(form_selector)});
          if (existing) return true;
          const button = document.querySelector({json.dumps(toggle_selector)});
          if (!button) return false;
          button.click();
          return true;
        }})()
        """
    )
    if not result:
        raise RuntimeError(f"Could not open exchange composer {composer_mode!r}")
    wait_for(cdp, f"document.readyState === 'complete' && !!document.querySelector({json.dumps(form_selector)})", timeout_seconds=timeout_seconds)


def fill_form_by_heading(cdp: object, heading: str, *, title: str, body: str) -> dict[str, object]:
    result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const needle = {json.dumps(heading)};
          const form = Array.from(document.querySelectorAll('form')).find((item) => ((item.innerText || item.textContent || '')).includes(needle));
          if (!form) return {{ ok: false, reason: 'missing-form', needle, body: (document.body && document.body.innerText || '').slice(0, 1200) }};
          const select = form.querySelector('select[name="recipient_id"]');
          if (select) {{
            const options = Array.from(select.options || []).filter((option) => option.value);
            if (!options.length) return {{ ok: false, reason: 'no-target-options', needle }};
            select.value = options[0].value;
            select.dispatchEvent(new Event('input', {{ bubbles: true }}));
            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
          }}
          const titleField = form.querySelector('input[name="title"]');
          const bodyField = form.querySelector('textarea[name="body"]');
          if (!titleField || !bodyField) return {{ ok: false, reason: 'missing-fields', needle }};
          titleField.focus();
          titleField.value = {json.dumps(title)};
          titleField.dispatchEvent(new Event('input', {{ bubbles: true }}));
          titleField.dispatchEvent(new Event('change', {{ bubbles: true }}));
          bodyField.focus();
          bodyField.value = {json.dumps(body)};
          bodyField.dispatchEvent(new Event('input', {{ bubbles: true }}));
          bodyField.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return {{
            ok: true,
            targetValue: select ? select.value : null,
            targetLabel: select && select.selectedOptions.length ? select.selectedOptions[0].textContent.trim() : null,
            title: titleField.value,
            bodyLength: bodyField.value.length,
          }};
        }})()
        """,
    )
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"Could not fill form {heading!r}: {result}")
    return result


def fill_form_by_button_text(cdp: object, button_text: str, *, title: str, body: str) -> dict[str, object]:
    result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const buttonNeedle = {json.dumps(button_text)};
          const form = Array.from(document.querySelectorAll('form')).find((item) =>
            Array.from(item.querySelectorAll('button')).some((button) => ((button.innerText || button.textContent || '')).includes(buttonNeedle))
          );
          if (!form) return {{ ok: false, reason: 'missing-form', buttonNeedle, body: (document.body && document.body.innerText || '').slice(0, 1200) }};
          const titleField = form.querySelector('input[name="title"]');
          const bodyField = form.querySelector('textarea[name="body"]');
          if (!titleField || !bodyField) return {{ ok: false, reason: 'missing-fields', buttonNeedle }};
          titleField.focus();
          titleField.value = {json.dumps(title)};
          titleField.dispatchEvent(new Event('input', {{ bubbles: true }}));
          titleField.dispatchEvent(new Event('change', {{ bubbles: true }}));
          bodyField.focus();
          bodyField.value = {json.dumps(body)};
          bodyField.dispatchEvent(new Event('input', {{ bubbles: true }}));
          bodyField.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return {{
            ok: true,
            title: titleField.value,
            bodyLength: bodyField.value.length,
          }};
        }})()
        """,
    )
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"Could not fill form using button {button_text!r}: {result}")
    return result


def click_form_button(cdp: object, heading: str, button_text: str, *, timeout_seconds: float = 20) -> dict[str, object]:
    expr = f"""
    (() => {{
      const formNeedle = {json.dumps(heading)};
      const buttonNeedle = {json.dumps(button_text)};
      const form = Array.from(document.querySelectorAll('form')).find((item) => ((item.innerText || item.textContent || '')).includes(formNeedle));
      if (!form) return {{ ok: false, reason: 'missing-form', formNeedle }};
      const button = Array.from(form.querySelectorAll('button')).find((item) => ((item.innerText || item.textContent || '')).replace(/\s+/g, ' ').includes(buttonNeedle));
      if (!button) return {{ ok: false, reason: 'missing-button', buttonNeedle }};
      if (button.disabled) return {{ ok: false, reason: 'disabled', buttonText: (button.innerText || button.textContent || '').trim() }};
      button.scrollIntoView({{ block: 'center', inline: 'center' }});
      const rect = button.getBoundingClientRect();
      return {{
        ok: true,
        text: (button.innerText || button.textContent || '').replace(/\s+/g, ' ').trim(),
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
      }};
    }})()
    """
    point = wait_for(cdp, expr, timeout_seconds=timeout_seconds)
    if not isinstance(point, dict) or not point.get("ok"):
        raise RuntimeError(f"Could not click button {button_text!r} in form {heading!r}: {point}")
    x = float(point["x"])
    y = float(point["y"])
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return point


def wait_for_page_text(cdp: object, text: str, *, timeout_seconds: float = 40) -> None:
    wait_for(cdp, f"document.body && document.body.innerText.includes({json.dumps(text)})", timeout_seconds=timeout_seconds)


def focus_governance_preview(cdp: object, *, timeout_seconds: float = 20) -> None:
    wait_for(
        cdp,
        "!!document.querySelector('[data-collab-governance-preview]')",
        timeout_seconds=timeout_seconds,
    )
    cdp_eval(
        cdp,
        """
        (() => {
          const el = document.querySelector('[data-collab-governance-preview]');
          if (!el) return false;
          el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
          return true;
        })()
        """,
    )


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    project_path = f"/projects/{args.project_id}"
    workshop_path = f"{project_path}?panel=team&tab=development-workshop"
    schedule_path = f"{project_path}?panel=team&tab=schedule"
    exchange_path = f"{project_path}?panel=team&tab=exchange"
    npc_path = f"{project_path}?panel=team&tab=npc-create"
    login_url = f"{web_base}/login?returnTo={quote(workshop_path, safe='')}"

    token, user = api_login(api_base, args.login_email, args.login_password)
    before_commands = read_agent_commands(api_base, args.project_id, token)
    before_human_reviews = read_human_review_requests(api_base, args.project_id, token)
    before_count = len(before_commands)
    before_human_review_count = len(before_human_reviews)

    port = cdp_helper.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-collab-preview-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    screenshots: list[str] = []
    report: dict[str, object] = {}

    try:
        edge_process = subprocess.Popen(
            [
                str(cdp_helper.find_edge()),
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

        cdp.send("Page.navigate", {"url": login_url})
        wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('form')")
        shot = output_dir / f"collab-preview-01-login-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        login_result = cdp_eval(
            cdp,
            f"""
            (() => {{
              const email = document.querySelector('input[name="email"], input[type="email"]');
              const password = document.querySelector('input[name="password"], input[type="password"]');
              if (!email || !password) return {{ ok: false }};
              email.value = {json.dumps(args.login_email)};
              email.dispatchEvent(new Event('input', {{ bubbles: true }}));
              password.value = {json.dumps(args.login_password)};
              password.dispatchEvent(new Event('input', {{ bubbles: true }}));
              return {{ ok: true }};
            }})()
            """,
        )
        if not isinstance(login_result, dict) or not login_result.get("ok"):
            raise RuntimeError(f"Could not populate login form: {login_result}")
        click_by_text(cdp, "进入平台", selector='button[type="submit"], button, a')

        wait_for_page_text(cdp, WORKSHOP_FORM_TITLE, timeout_seconds=45)
        shot = output_dir / f"collab-preview-02-workshop-before-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        workshop_title = f"开发工坊预演 {stamp}"
        workshop_body = f"请先细化这个工位的下一步执行方案，产出最小回执、最终回复格式和需要人工确认的边界。{stamp}"
        workshop_fill = fill_form_by_heading(cdp, WORKSHOP_FORM_TITLE, title=workshop_title, body=workshop_body)
        click_form_button(cdp, WORKSHOP_FORM_TITLE, "先预演工位规划")
        wait_for_page_text(cdp, "最近一次工位规划预演", timeout_seconds=45)
        focus_governance_preview(cdp)
        shot = output_dir / f"collab-preview-03-workshop-after-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))
        workshop_count = len(read_agent_commands(api_base, args.project_id, token))

        cdp.send("Page.navigate", {"url": f"{web_base}{schedule_path}"})
        wait_for_page_text(cdp, SCHEDULE_FORM_TITLE, timeout_seconds=45)
        shot = output_dir / f"collab-preview-04-schedule-before-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        schedule_title = f"日程排程预演 {stamp}"
        schedule_body = f"请基于今天任务生成上午、下午、晚上安排，并标记需要人工审核的步骤。{stamp}"
        schedule_fill = fill_form_by_heading(cdp, SCHEDULE_FORM_TITLE, title=schedule_title, body=schedule_body)
        click_form_button(cdp, SCHEDULE_FORM_TITLE, "先预演 AI 排程")
        wait_for_page_text(cdp, "最近一次日程排程预演", timeout_seconds=45)
        focus_governance_preview(cdp)
        shot = output_dir / f"collab-preview-05-schedule-after-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))
        schedule_count = len(read_agent_commands(api_base, args.project_id, token))

        cdp.send("Page.navigate", {"url": f"{web_base}{exchange_path}"})
        open_exchange_overview(cdp, timeout_seconds=45)
        open_exchange_composer(cdp, "dispatch", timeout_seconds=45)
        shot = output_dir / f"collab-preview-06-exchange-before-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        exchange_title = f"总派工预演 {stamp}"
        exchange_body = f"请把资料收集、写作、验收拆成协作步骤，并说明最小回执与最终回复怎么回。{stamp}"
        exchange_fill = fill_form_by_heading(cdp, EXCHANGE_FORM_TITLE, title=exchange_title, body=exchange_body)
        click_form_button(cdp, EXCHANGE_FORM_TITLE, "先预演协作指令")
        wait_for_page_text(cdp, "最近一次总派工预演", timeout_seconds=45)
        focus_governance_preview(cdp)
        shot = output_dir / f"collab-preview-07-exchange-after-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))
        exchange_count = len(read_agent_commands(api_base, args.project_id, token))

        cdp.send("Page.navigate", {"url": f"{web_base}{exchange_path}"})
        open_exchange_overview(cdp, timeout_seconds=45)
        open_exchange_composer(cdp, "dispatch", timeout_seconds=45)
        high_risk_title = f"硬件烧录人审预演 {stamp}"
        high_risk_body = (
            f"请操作真实开发板，通过串口扫描 USB 设备并烧录固件到 NanoPi，"
            f"如果失败就回滚并继续重试。先说明仿真、只读探针和人工审核边界。{stamp}"
        )
        high_risk_fill = fill_form_by_heading(
            cdp,
            EXCHANGE_FORM_TITLE,
            title=high_risk_title,
            body=high_risk_body,
        )
        click_form_button(cdp, EXCHANGE_FORM_TITLE, "先预演协作指令")
        wait_for_page_text(cdp, "治理闸口会拦住直接派发", timeout_seconds=45)
        wait_for_page_text(cdp, "登记人工审核", timeout_seconds=45)
        focus_governance_preview(cdp)
        shot = output_dir / f"collab-preview-08-high-risk-review-gate-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))
        high_risk_count = len(read_agent_commands(api_base, args.project_id, token))
        high_risk_human_review_count = len(read_human_review_requests(api_base, args.project_id, token))

        cdp.send("Page.navigate", {"url": f"{web_base}{npc_path}"})
        wait_for_page_text(cdp, NPC_PANEL_TITLE, timeout_seconds=45)
        shot = output_dir / f"collab-preview-09-npc-panel-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_by_text(cdp, NPC_DIALOG_OPEN_BUTTON, selector="button, a")
        wait_for_page_text(cdp, NPC_DIALOG_PREVIEW_BUTTON, timeout_seconds=45)
        npc_title = f"NPC 对话预演 {stamp}"
        npc_body = f"请先拆出你自己的执行步骤、最小回执和最终回复格式，再说明哪些地方需要人工审核。{stamp}"
        npc_fill = fill_form_by_button_text(cdp, NPC_DIALOG_PREVIEW_BUTTON, title=npc_title, body=npc_body)
        shot = output_dir / f"collab-preview-10-npc-before-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_by_text(cdp, NPC_DIALOG_PREVIEW_BUTTON, selector="button")
        wait_for_page_text(cdp, NPC_DIALOG_PREVIEW_HEADING, timeout_seconds=45)
        focus_governance_preview(cdp)
        shot = output_dir / f"collab-preview-11-npc-after-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))
        final_count = len(read_agent_commands(api_base, args.project_id, token))
        final_human_review_count = len(read_human_review_requests(api_base, args.project_id, token))

        report = {
            "validated_at": stamp,
            "user": user,
            "project_id": args.project_id,
            "before_agent_command_count": before_count,
            "before_human_review_request_count": before_human_review_count,
            "after_workshop_preview_count": workshop_count,
            "after_schedule_preview_count": schedule_count,
            "after_exchange_preview_count": exchange_count,
            "after_high_risk_preview_count": high_risk_count,
            "after_high_risk_human_review_request_count": high_risk_human_review_count,
            "after_npc_dialog_preview_count": final_count,
            "after_npc_dialog_human_review_request_count": final_human_review_count,
            "workshop_fill": workshop_fill,
            "schedule_fill": schedule_fill,
            "exchange_fill": exchange_fill,
            "high_risk_fill": high_risk_fill,
            "npc_fill": npc_fill,
            "workshop_path": f"{web_base}{workshop_path}",
            "schedule_path": f"{web_base}{schedule_path}",
            "exchange_path": f"{web_base}{exchange_path}",
            "npc_path": f"{web_base}{npc_path}",
            "screenshots": screenshots,
        }
        report_path = output_dir / f"collab-preview-validation-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"REPORT_PATH={report_path}")
        return 0
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
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
