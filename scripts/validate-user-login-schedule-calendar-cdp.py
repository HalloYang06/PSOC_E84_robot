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
    parser = argparse.ArgumentParser(description="Validate login -> home calendar -> schedule panel through Edge CDP.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", required=True)
    parser.add_argument("--login-password", required=True)
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=2048)
    parser.add_argument("--viewport-height", type=int, default=1152)
    return parser.parse_args()


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
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1200])
    value = result.get("result", {})
    if isinstance(value, dict):
        return value.get("value")
    return None


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 30, interval_seconds: float = 0.25) -> object:
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
    raise RuntimeError(f"Timed out waiting for expression: {expression[:180]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-calendar-flow-edge-"))
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

        cdp.send("Page.navigate", {"url": f"{web_base}/login?returnTo=/projects/{args.project_id}"})
        wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('form')", timeout_seconds=35)
        login_result = cdp_eval(
            cdp,
            f"""
            (() => {{
              const email = document.querySelector('input[name="email"], input[type="email"]');
              const password = document.querySelector('input[name="password"], input[type="password"]');
              if (!email || !password) return {{ ok: false, reason: 'missing-fields' }};
              email.value = {json.dumps(args.login_email)};
              email.dispatchEvent(new Event('input', {{ bubbles: true }}));
              email.dispatchEvent(new Event('change', {{ bubbles: true }}));
              password.value = {json.dumps(args.login_password)};
              password.dispatchEvent(new Event('input', {{ bubbles: true }}));
              password.dispatchEvent(new Event('change', {{ bubbles: true }}));
              const submit = document.querySelector('button[type="submit"], form button');
              if (!submit) return {{ ok: false, reason: 'missing-submit' }};
              submit.click();
              return {{ ok: true }};
            }})()
            """,
        )
        if not isinstance(login_result, dict) or not login_result.get("ok"):
            raise RuntimeError(f"Login form did not submit: {login_result}")

        wait_for(cdp, f"location.href.includes({json.dumps(args.project_id)})", timeout_seconds=40)
        wait_for(cdp, "!!document.querySelector('iframe')", timeout_seconds=35)
        wait_for(
            cdp,
            "(() => { const frame = document.querySelector('iframe'); return !!(frame && frame.contentDocument && frame.contentDocument.readyState === 'complete'); })()",
            timeout_seconds=35,
        )
        wait_for(
            cdp,
            "(() => { const frame = document.querySelector('iframe'); const win = frame && frame.contentWindow; return !!(win && Array.isArray(win.__platformScheduleHotspotSnapshot) && win.__platformScheduleHotspotSnapshot.length); })()",
            timeout_seconds=45,
        )
        time.sleep(1.0)

        hotspot_info = cdp_eval(
            cdp,
            """
            (() => {
              const frame = document.querySelector('iframe');
              const win = frame && frame.contentWindow;
              const snapshot = win && Array.isArray(win.__platformScheduleHotspotSnapshot)
                ? win.__platformScheduleHotspotSnapshot.slice(0, 4)
                : [];
              return {
                iframeUrl: frame ? frame.src : '',
                hotspot: snapshot[0] || null,
                scheduleTextVisible: document.body.innerText.includes('日程日历')
              };
            })()
            """,
        )
        shot_home = output_dir / f"user-login-05-home-calendar-hotspot-{stamp}.png"
        screenshot(cdp, shot_home)

        click_point = cdp_eval(
            cdp,
            """
            (() => {
              const frame = document.querySelector('iframe');
              const win = frame && frame.contentWindow;
              const hotspot = win && Array.isArray(win.__platformScheduleHotspotSnapshot)
                ? win.__platformScheduleHotspotSnapshot[0]
                : null;
              if (!frame || !hotspot) return { ok: false, reason: 'missing-hotspot' };
              const rect = frame.getBoundingClientRect();
              return {
                ok: true,
                x: rect.left + Number(hotspot.screenX),
                y: rect.top + Number(hotspot.screenY),
                hotspot
              };
            })()
            """,
        )
        if not isinstance(click_point, dict) or not click_point.get("ok"):
            raise RuntimeError(f"Could not resolve calendar click point: {click_point}")

        click_x = float(click_point["x"])
        click_y = float(click_point["y"])
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": click_x, "y": click_y})
        cdp.send(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": click_x, "y": click_y, "button": "left", "clickCount": 1},
        )
        cdp.send(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": click_x, "y": click_y, "button": "left", "clickCount": 1},
        )
        wait_for(
            cdp,
            "location.href.includes('tab=schedule') || document.body.innerText.includes('任务 DDL、每日安排、AI 当日排程')",
            timeout_seconds=25,
        )
        time.sleep(1.0)
        shot_schedule = output_dir / f"user-login-06-schedule-panel-from-calendar-{stamp}.png"
        screenshot(cdp, shot_schedule)

        panel_info = cdp_eval(
            cdp,
            """
            (() => ({
              url: location.href,
              hasSchedulePanel: document.body.innerText.includes('任务 DDL、每日安排、AI 当日排程'),
              hasDailyPlanForm: !!document.querySelector('textarea[name="daily_plan"]'),
              hasAiPlanForm: !!document.querySelector('textarea[name="body"]'),
              hasDeadlineInput: !!document.querySelector('input[name="due_at"]'),
              bodyText: document.body.innerText.slice(0, 1200)
            }))()
            """,
        )

        report = {
            "stamp": stamp,
            "project_id": args.project_id,
            "screenshots": [str(shot_home), str(shot_schedule)],
            "login_result": login_result,
            "hotspot_info": hotspot_info,
            "click_point": click_point,
            "panel_info": panel_info,
        }
        report_path = output_dir / f"user-login-schedule-calendar-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
