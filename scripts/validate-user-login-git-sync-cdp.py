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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the visual Git sync flow through the real browser.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=2048)
    parser.add_argument("--viewport-height", type=int, default=1152)
    parser.add_argument("--commit-request", action="store_true", help="After preview, also submit the real sync request.")
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
    with urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


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


def fill_field(cdp: object, selector: str, value: str) -> None:
    ok = cdp_eval(
        cdp,
        f"""
        (() => {{
          const field = document.querySelector({json.dumps(selector)});
          if (!field) return false;
          field.focus();
          field.value = {json.dumps(value)};
          field.dispatchEvent(new Event('input', {{ bubbles: true }}));
          field.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return true;
        }})()
        """,
    )
    if not ok:
        raise RuntimeError(f"Could not fill selector {selector!r}")


def read_sync_items(api_base: str, project_id: str, token: str) -> list[dict[str, object]]:
    payload = request_json(f"{api_base}/api/git/projects/{project_id}/activity?limit=20", token=token)
    items = payload.get("data") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict) and str(item.get("action") or "") == "project.sync_github"
    ]


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    git_path = f"/projects/{args.project_id}?panel=team&tab=git"
    login_url = f"{web_base}/login?returnTo={quote(git_path, safe='')}"
    git_url = f"{web_base}{git_path}"
    sync_provider = "github"
    sync_note = f"真实浏览器验收 / Git 同步预演 {stamp}"

    token, user = api_login(api_base, args.login_email, args.login_password)
    before_sync_items = read_sync_items(api_base, args.project_id, token)
    before_sync_count = len(before_sync_items)

    port = cdp_helper.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-git-sync-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    screenshots: list[str] = []

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
        shot = output_dir / f"git-sync-01-login-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        fill_field(cdp, 'input[name="email"], input[type="email"]', args.login_email)
        fill_field(cdp, 'input[name="password"], input[type="password"]', args.login_password)
        click_by_text(cdp, "进入平台", selector='button[type="submit"], button, a')

        wait_for(
            cdp,
            "document.body && document.body.innerText.includes('可视化 Git 同步') && document.body.innerText.includes('先预演 Git 同步')",
            timeout_seconds=45,
        )
        wait_for(cdp, f"location.href.includes({json.dumps(git_url)}) || location.href.includes({json.dumps(git_path)})", timeout_seconds=15)

        shot = output_dir / f"git-sync-02-panel-before-submit-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        fill_field(cdp, 'textarea[name="notes"]', sync_note)
        click_by_text(cdp, "先预演 Git 同步", selector='button[type="submit"], button')

        wait_for(
            cdp,
            "document.readyState === 'complete' && document.body && document.body.innerText.includes('最近一次同步预演')",
            timeout_seconds=45,
        )
        time.sleep(2.0)
        shot = output_dir / f"git-sync-03-panel-after-preview-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        cdp_eval(
            cdp,
            """
            (() => {
              const panel = document.querySelector('aside[data-busy]');
              if (panel) {
                panel.scrollTo({ top: panel.scrollHeight, behavior: 'instant' });
              } else {
                window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' });
              }
              return true;
            })()
            """,
        )
        time.sleep(1.0)
        shot = output_dir / f"git-sync-04-preview-detail-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        after_preview_items = read_sync_items(api_base, args.project_id, token)
        if len(after_preview_items) != before_sync_count:
            raise RuntimeError("Preview mode should not change sync activity count")

        matching_activity = None
        if args.commit_request:
            click_by_text(cdp, "登记 Git 同步请求", selector='button[type="submit"], button')
            wait_for(cdp, "document.readyState === 'complete'", timeout_seconds=45)
            time.sleep(2.0)
            shot = output_dir / f"git-sync-05-panel-after-request-{stamp}.png"
            screenshot(cdp, shot)
            screenshots.append(str(shot))

            after_request_items = read_sync_items(api_base, args.project_id, token)
            if len(after_request_items) <= before_sync_count:
                raise RuntimeError("Git sync activity count did not increase after browser submit")
            matching_activity = next((item for item in after_request_items if isinstance(item, dict)), None)
            if not isinstance(matching_activity, dict):
                raise RuntimeError("Git sync activity entry was not found after browser submit")
            sync_count_after = len(after_request_items)
        else:
            sync_count_after = len(after_preview_items)

        report = {
            "validated_at": stamp,
            "mode": "preview_and_request" if args.commit_request else "preview_only",
            "project_id": args.project_id,
            "user_email": args.login_email,
            "user_id": user.get("id") if isinstance(user, dict) else None,
            "git_url": git_url,
            "sync_provider": sync_provider,
            "sync_note": sync_note,
            "sync_count_before": before_sync_count,
            "sync_count_after": sync_count_after,
            "page_url_after_submit": cdp_eval(cdp, "location.href"),
            "activity_action": matching_activity.get("action") if isinstance(matching_activity, dict) else None,
            "activity_created_at": matching_activity.get("created_at") if isinstance(matching_activity, dict) else None,
            "screenshots": screenshots,
        }
        report_path = output_dir / f"git-sync-validation-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "report": str(report_path), "screenshots": screenshots}, ensure_ascii=False))
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
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
