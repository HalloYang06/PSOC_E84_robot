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
REPO_ROOT = SCRIPT_DIR.parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)


TEMP_DRAWER_ID = "__create-development-station__"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate editable development workshop stations via the real browser flow.")
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


def get_project(api_base: str, project_id: str, token: str) -> dict[str, object]:
    payload = request_json(f"{api_base.rstrip('/')}/api/projects/{project_id}", token=token)
    data = payload.get("data") if isinstance(payload, dict) else payload
    return data if isinstance(data, dict) else {}


def patch_project(api_base: str, project_id: str, token: str, payload: dict[str, object]) -> dict[str, object]:
    response = request_json(
        f"{api_base.rstrip('/')}/api/projects/{project_id}",
        method="PATCH",
        payload=payload,
        token=token,
    )
    data = response.get("data") if isinstance(response, dict) else response
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
      const el = items.find((item) => (item.innerText || item.textContent || '').replace(/\\s+/g, ' ').includes(needle));
      if (!el) return {{ ok: false, reason: 'missing', needle, body: (document.body && document.body.innerText || '').slice(0, 1200) }};
      el.scrollIntoView({{ block: 'center', inline: 'center' }});
      const rect = el.getBoundingClientRect();
      return {{
        ok: true,
        text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 160),
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


def remove_temp_station(api_base: str, project_id: str, token: str, station_id: str) -> None:
    project = get_project(api_base, project_id, token)
    collaboration_config = project.get("collaboration_config") if isinstance(project.get("collaboration_config"), dict) else {}
    stations = collaboration_config.get("development_workshop_stations") if isinstance(collaboration_config, dict) else []
    if not isinstance(stations, list):
        stations = []
    next_stations = [item for item in stations if isinstance(item, dict) and str(item.get("id") or "") != station_id]
    if isinstance(collaboration_config, dict):
        collaboration_config = dict(collaboration_config)
        collaboration_config["development_workshop_stations"] = next_stations
    patch_project(api_base, project_id, token, {"collaboration_config": collaboration_config})


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    temp_station_id = f"temp-station-{stamp}"
    temp_station_label = f"临时工位 {stamp[-6:]}"
    temp_station_path = f"docs/ai-handoffs/stations/{temp_station_id}.md"
    station_path = f"/projects/{args.project_id}?panel=team&tab=development-workshop"
    login_url = f"{web_base}/login?returnTo={quote(station_path, safe='')}"
    workshop_url = f"{web_base}{station_path}"

    token, user = api_login(api_base, args.login_email, args.login_password)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-station-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    screenshots: list[str] = []
    report: dict[str, object] = {}

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
        shot = output_dir / f"development-station-01-login-{stamp}.png"
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
            raise RuntimeError(f"Login fields missing: {login_result}")
        try:
            click_by_text(cdp, "进入平台", selector="button")
        except RuntimeError:
            click_by_text(cdp, "登录", selector="button")

        wait_for(cdp, "document.body && document.body.innerText.includes('开发工坊') && document.body.innerText.includes('工位栏')", timeout_seconds=60)
        shot = output_dir / f"development-station-02-workshop-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_by_text(cdp, "添加工位", selector="button")
        wait_for(cdp, f"document.querySelector('input[name=\"label\"]') && document.body.innerText.includes('新增开发工位')", timeout_seconds=30)
        drawer_state = cdp_eval(
            cdp,
            """
            (() => ({
              title: document.querySelector('[role="dialog"] strong')?.textContent || '',
              drawerLabel: document.querySelector('input[name="label"]')?.value || '',
              knowledgePath: document.querySelector('input[name="knowledge_handoff_path"]')?.value || '',
              riskLevel: document.querySelector('select[name="risk_level"]')?.value || ''
            }))()
            """,
        )
        shot = output_dir / f"development-station-03-create-drawer-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        fill_result = cdp_eval(
            cdp,
            f"""
            (() => {{
              const setValue = (name, value) => {{
                const el = document.querySelector(`[name="${{name}}"]`);
                if (!el) return false;
                el.value = value;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
              }};
              return {{
                label: setValue('label', {json.dumps(temp_station_label)}),
                icon: setValue('icon', '板'),
                station: setValue('station', '开发工坊 / 临时验收区'),
                map_scene: setValue('map_scene', 'map-farm'),
                map_location: setValue('map_location', '开发工坊外场左侧'),
                detail: setValue('detail', '这是浏览器验收临时工位，用于验证用户可以自定义工位和工位知识库。'),
                modes: setValue('modes', '2D 开发者模式, 多 AI 协作'),
                backend_anchor: setValue('backend_anchor', {json.dumps(f'/api/development/projects/{args.project_id}/framework#temp-validation')}),
                runner_capabilities: setValue('runner_capabilities', 'github-clone, build-test'),
                ai_responsibilities: setValue('ai_responsibilities', '拉代码, 编译验证, 写回执'),
                npc_role_templates: setValue('npc_role_templates', '临时资料员, 临时验收员'),
                assignment_keywords: setValue('assignment_keywords', 'temp-validation, 验收工位'),
                next_actions: setValue('next_actions', '创建 NPC, 发协作指令'),
                approval_policy: setValue('approval_policy', '仅限本地浏览器验收，不执行危险动作。'),
                knowledge_summary: setValue('knowledge_summary', '这是工位总知识库，不属于单个 NPC。'),
                knowledge_handoff_path: setValue('knowledge_handoff_path', {json.dumps(temp_station_path)}),
                knowledge_tags: setValue('knowledge_tags', 'temp-validation, station-knowledge')
              }};
            }})()
            """,
        )
        if not isinstance(fill_result, dict) or not fill_result.get("label"):
            raise RuntimeError(f"Create station form did not fill: {fill_result}")
        click_by_text(cdp, "创建工位", selector="button")

        wait_for(cdp, f"document.body && document.body.innerText.includes({json.dumps(temp_station_label)})", timeout_seconds=60)
        click_by_text(cdp, temp_station_label, selector="button")
        wait_for(cdp, f"document.body && document.body.innerText.includes({json.dumps(temp_station_label)})", timeout_seconds=20)
        shot = output_dir / f"development-station-04-created-rail-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_by_text(cdp, "编辑当前工位", selector="button")
        wait_for(cdp, f"document.querySelector('input[name=\"label\"]') && document.querySelector('input[name=\"label\"]').value.includes({json.dumps(temp_station_label)})", timeout_seconds=30)
        persisted_state = cdp_eval(
            cdp,
            """
            (() => ({
              label: document.querySelector('input[name="label"]')?.value || '',
              knowledgeSummary: document.querySelector('textarea[name="knowledge_summary"]')?.value || '',
              knowledgePath: document.querySelector('input[name="knowledge_handoff_path"]')?.value || '',
              knowledgeTags: document.querySelector('input[name="knowledge_tags"]')?.value || ''
            }))()
            """,
        )
        shot = output_dir / f"development-station-05-edit-drawer-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        project = get_project(api_base, args.project_id, token)
        collaboration_config = project.get("collaboration_config") if isinstance(project.get("collaboration_config"), dict) else {}
        stations = collaboration_config.get("development_workshop_stations") if isinstance(collaboration_config, dict) else []
        created_station = next((item for item in stations if isinstance(item, dict) and str(item.get("label") or "") == temp_station_label), None)
        if not isinstance(created_station, dict):
            raise RuntimeError(f"Temporary station not found in API response: {stations}")
        temp_station_id = str(created_station.get("id") or temp_station_id)
        knowledge_file = (REPO_ROOT / temp_station_path).resolve()
        knowledge_exists = knowledge_file.exists()

        report = {
            "stamp": stamp,
            "project_id": args.project_id,
            "user": user,
            "created_station": created_station,
            "drawer_state": drawer_state,
            "fill_result": fill_result,
            "persisted_state": persisted_state,
            "knowledge_file": str(knowledge_file),
            "knowledge_exists": knowledge_exists,
            "screenshots": screenshots,
        }
        report_path = output_dir / f"development-station-validation-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        try:
            remove_temp_station(api_base, args.project_id, token, temp_station_id)
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup station failed: {exc}", file=sys.stderr)
        knowledge_file = (REPO_ROOT / temp_station_path).resolve()
        if knowledge_file.exists():
            knowledge_file.unlink()
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
