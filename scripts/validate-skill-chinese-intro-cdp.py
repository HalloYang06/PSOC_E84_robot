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
    parser = argparse.ArgumentParser(description="Validate Chinese skill detail summaries through the real Skill manager UI.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--skill-id", default="agency-frontend-developer")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=2048)
    parser.add_argument("--viewport-height", type=int, default=1152)
    return parser.parse_args()


def request_json(url: str, *, method: str = "GET", payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
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


def wait_for_panel_idle(cdp: object, *, timeout_seconds: float = 60) -> None:
    wait_for(
        cdp,
        """
        (() => {
          const panel = document.querySelector('#project-main-panel');
          if (!panel) return false;
          const busy = panel.getAttribute('data-busy');
          const overlay = panel.querySelector('[role="status"]');
          return busy !== 'true' && !overlay;
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


def read_detail_state(cdp: object, skill_id: str) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const subject = document.querySelector('[data-skill-detail-drawer={json.dumps(skill_id)}]');
          const introNode = document.querySelector('[data-skill-detail-intro={json.dumps(skill_id)}]');
          const stationNode = document.querySelector('[data-skill-fit-stations={json.dumps(skill_id)}]');
          const deliverableNode = document.querySelector('[data-skill-deliverables={json.dumps(skill_id)}]');
          const notice = new URL(window.location.href).searchParams.get('team_notice') || '';
          const error = new URL(window.location.href).searchParams.get('team_error') || '';
          const introText = (introNode?.textContent || '').trim();
          const stationText = (stationNode?.textContent || '').trim();
          const deliverableText = (deliverableNode?.textContent || '').trim();
          return {{
            subjectVisible: !!subject,
            introVisible: !!introNode,
            stationVisible: !!stationNode,
            deliverableVisible: !!deliverableNode,
            subjectText: (subject?.textContent || '').trim(),
            introText,
            stationText,
            deliverableText,
            hasCjk: /[\\u3400-\\u9fff]/u.test(introText),
            hasSpecificMarkers:
              introText.includes('适合担任') &&
              introText.includes('重点负责') &&
              (introText.includes('常用于') || introText.includes('适合接')),
            stationHasMarkers:
              stationText.includes('适合工位') &&
              (stationText.includes('前端工位') || stationText.includes('App 工位') || stationText.includes('NanoPi 工位')),
            deliverableHasMarkers:
              deliverableText.includes('常见交付物') &&
              (deliverableText.includes('页面框架草图') || deliverableText.includes('组件拆分清单') || deliverableText.includes('交互实现结果')),
            notice,
            error,
          }};
        }})()
        """,
    )
    return state if isinstance(state, dict) else {}


def main() -> int:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    login_url = f"{args.web_base.rstrip('/')}/login"
    skills_url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=skills"
    detail_url = (
        f"{args.web_base.rstrip('/')}/projects/{args.project_id}"
        f"?panel=team&tab=skills&drawer=skill-detail&drawer_id={args.skill_id}"
    )
    report_path = output_dir / f"skill-chinese-intro-validation-report-{stamp}.json"
    screenshots: list[str] = []

    token, user = api_login(args.api_base, args.login_email, args.login_password)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-edge-python-cdp-"))
    edge_process = None
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
        shot = output_dir / f"skill-chinese-intro-01-login-{stamp}.png"
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
        cdp.send(
            "Network.setCookie",
            {
                "name": "farm_user",
                "value": json.dumps(user, ensure_ascii=True),
                "domain": "127.0.0.1",
                "path": "/",
                "httpOnly": False,
                "secure": False,
            },
        )

        cdp.send("Page.navigate", {"url": skills_url})
        wait_for(
            cdp,
            "document.readyState === 'complete' && !!document.querySelector('[data-skill-search-input=\"1\"]')",
            timeout_seconds=60,
        )
        wait_for_panel_idle(cdp, timeout_seconds=60)
        shot = output_dir / f"skill-chinese-intro-02-skills-panel-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        cdp.send("Page.navigate", {"url": detail_url})
        wait_for(
            cdp,
            f"document.readyState === 'complete' && !!document.querySelector('[data-skill-detail-drawer={json.dumps(args.skill_id)}]')",
            timeout_seconds=60,
        )
        wait_for(
            cdp,
            f"!!document.querySelector('[data-skill-detail-intro={json.dumps(args.skill_id)}]')",
            timeout_seconds=30,
        )
        wait_for(
            cdp,
            f"!!document.querySelector('[data-skill-fit-stations={json.dumps(args.skill_id)}]') && !!document.querySelector('[data-skill-deliverables={json.dumps(args.skill_id)}]')",
            timeout_seconds=30,
        )
        wait_for_panel_idle(cdp, timeout_seconds=60)
        detail_state = read_detail_state(cdp, args.skill_id)
        if not detail_state.get("subjectVisible"):
            raise RuntimeError(f"Skill detail drawer did not open for {args.skill_id}: {detail_state}")
        if not detail_state.get("introVisible"):
            raise RuntimeError(f"Skill detail intro node missing for {args.skill_id}: {detail_state}")
        if not detail_state.get("stationVisible"):
            raise RuntimeError(f"Skill fit station card missing for {args.skill_id}: {detail_state}")
        if not detail_state.get("deliverableVisible"):
            raise RuntimeError(f"Skill deliverable card missing for {args.skill_id}: {detail_state}")
        if not detail_state.get("hasCjk"):
            raise RuntimeError(f"Skill detail intro did not render Chinese text: {detail_state}")
        if not detail_state.get("hasSpecificMarkers"):
            raise RuntimeError(f"Skill detail intro was not specific enough: {detail_state}")
        if not detail_state.get("stationHasMarkers"):
            raise RuntimeError(f"Skill fit station card did not render expected Chinese guidance: {detail_state}")
        if not detail_state.get("deliverableHasMarkers"):
            raise RuntimeError(f"Skill deliverable card did not render expected Chinese outputs: {detail_state}")
        shot = output_dir / f"skill-chinese-intro-03-detail-drawer-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        report = {
            "validated_at": datetime.now().astimezone().isoformat(),
            "project_id": args.project_id,
            "skill_id": args.skill_id,
            "skills_url": skills_url,
            "detail_url": detail_url,
            "detail_state": detail_state,
            "screenshots": screenshots,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        if cdp is not None:
            cdp.close()
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=5)
            except Exception:  # noqa: BLE001
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
