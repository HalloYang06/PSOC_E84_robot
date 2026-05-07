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

BUTTON_SPECS = [
    ("主角协作管理", "human-party", "主角协作管理"),
    ("开发工坊", "development-workshop", "开发工坊"),
    ("NPC 管理", "npc-create", "NPC 管理"),
    ("电脑接入管理", "computers", "电脑接入管理"),
    ("Skill 管理仓库", "skills", "Skill 管理仓库"),
]
SURFACE_MARKERS = ["项目主角", "开发工坊", "主角协作管理", "显示协作焦点"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose map-side entry buttons versus direct routes.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=1900)
    parser.add_argument("--viewport-height", type=int, default=1100)
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
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1600])
    payload = result.get("result", {})
    return payload.get("value") if isinstance(payload, dict) else None


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


def wait_for_text(cdp: object, markers: list[str], *, timeout_seconds: float = 40) -> None:
    deadline = time.time() + timeout_seconds
    last_text = ""
    while time.time() < deadline:
        text = str(cdp_eval(cdp, "document.body ? document.body.innerText : ''") or "")
        last_text = text
        if any(marker in text for marker in markers):
            return
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for any marker {markers!r}; last text snippet={last_text[:240]!r}")


def launch_edge(args: argparse.Namespace) -> tuple[subprocess.Popen[bytes], Path, object]:
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-map-entry-edge-"))
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
        {"width": args.viewport_width, "height": args.viewport_height, "deviceScaleFactor": 1, "mobile": False},
    )
    return edge_process, profile_dir, cdp


def login_and_open_project(cdp: object, args: argparse.Namespace) -> None:
    cdp.send("Page.navigate", {"url": f"{args.web_base.rstrip('/')}/login"})
    wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('form')", timeout_seconds=35)
    login_result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const email = document.querySelector('input[name="email"], input[type="email"]');
          const password = document.querySelector('input[name="password"], input[type="password"]');
          const submit = document.querySelector('button[type="submit"], form button');
          if (!email || !password || !submit) return {{ ok: false }};
          email.value = {json.dumps(args.login_email)};
          email.dispatchEvent(new Event('input', {{ bubbles: true }}));
          password.value = {json.dumps(args.login_password)};
          password.dispatchEvent(new Event('input', {{ bubbles: true }}));
          submit.click();
          return {{ ok: true }};
        }})()
        """,
    )
    if not isinstance(login_result, dict) or not login_result.get("ok"):
        raise RuntimeError(f"Login form did not submit: {login_result}")
    wait_for(cdp, "location.pathname.includes('/projects')", timeout_seconds=45)
    cdp.send("Page.navigate", {"url": f"{args.web_base.rstrip('/')}/projects/{args.project_id}"})
    wait_for(cdp, f"location.href.includes({json.dumps(args.project_id)})", timeout_seconds=35)
    wait_for_text(cdp, SURFACE_MARKERS, timeout_seconds=35)
    time.sleep(1.0)


def locate_text_click_target(cdp: object, label: str) -> dict[str, object] | None:
    target = cdp_eval(
        cdp,
        f"""
        (() => {{
          const wanted = {json.dumps(label)};
          const nodes = Array.from(document.querySelectorAll('a, button'));
          const node = nodes.find((item) => {{
            const text = (item.innerText || item.textContent || '').replace(/\\s+/g, ' ').trim();
            if (!text.includes(wanted)) return false;
            const style = window.getComputedStyle(item);
            const rect = item.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 4 && rect.height > 4;
          }});
          if (!node) return null;
          node.scrollIntoView({{ block: 'center', inline: 'center', behavior: 'instant' }});
          const rect = node.getBoundingClientRect();
          return {{
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
            text: (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim(),
            tag: node.tagName,
          }};
        }})()
        """,
    )
    return target if isinstance(target, dict) else None


def click_point(cdp: object, x: float, y: float) -> None:
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "none"})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})


def click_text_button(cdp: object, label: str) -> dict[str, object]:
    target = locate_text_click_target(cdp, label)
    if not target:
        return {"clicked": False, "target": None}
    click_point(cdp, float(target["x"]), float(target["y"]))
    time.sleep(1.2)
    return {"clicked": True, "target": target}


def navigate_and_wait(cdp: object, url: str, expected_heading: str) -> None:
    cdp.send("Page.navigate", {"url": url})
    wait_for(cdp, f"location.href.includes({json.dumps(url.split('http://127.0.0.1:3000', 1)[-1])})", timeout_seconds=25)
    wait_for_text(cdp, [expected_heading], timeout_seconds=25)
    time.sleep(1.0)


def current_panel_state(cdp: object) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        """
        (() => {
          const panel = document.querySelector('#project-main-panel');
          const heading = panel ? panel.querySelector('h2') : null;
          const labels = Array.from(document.querySelectorAll('a, button'))
            .map((item) => (item.innerText || item.textContent || '').replace(/\\s+/g, ' ').trim())
            .filter(Boolean)
            .filter((text) => ['开发工坊', '主角协作管理', 'NPC 管理', '电脑接入管理', 'Skill 管理仓库'].includes(text));
          return {
            href: location.href,
            panel_exists: !!panel,
            panel_heading: heading ? (heading.textContent || '').trim() : '',
            active_tab: new URL(location.href).searchParams.get('tab') || '',
            visible_map_buttons: labels,
          };
        })()
        """,
    )
    return state if isinstance(state, dict) else {}


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    edge_process = None
    profile_dir: Path | None = None
    cdp = None
    results: dict[str, object] = {
        "stamp": stamp,
        "project_id": args.project_id,
        "screenshots": [],
        "buttons": [],
    }

    try:
        edge_process, profile_dir, cdp = launch_edge(args)
        login_and_open_project(cdp, args)

        before = output_dir / f"map-entry-00-project-map-{stamp}.png"
        screenshot(cdp, before)
        results["screenshots"].append(str(before))

        for label, tab, heading in BUTTON_SPECS:
            entry: dict[str, object] = {"label": label, "tab": tab}
            click_result = click_text_button(cdp, label)
            entry.update(click_result)
            try:
                wait_for(
                    cdp,
                    f"location.href.includes({json.dumps(f'tab={tab}')}) || !!document.querySelector('#project-main-panel h2')",
                    timeout_seconds=8,
                )
                entry["post_click_wait"] = "route-or-panel"
            except Exception as exc:  # noqa: BLE001
                entry["post_click_wait_error"] = str(exc)
            entry["after_click"] = current_panel_state(cdp)
            shot = output_dir / f"map-entry-after-click-{tab}-{stamp}.png"
            screenshot(cdp, shot)
            results["screenshots"].append(str(shot))
            entry["after_click_screenshot"] = str(shot)

            direct_url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab={tab}"
            navigate_and_wait(cdp, direct_url, heading)
            entry["after_direct_route"] = current_panel_state(cdp)
            shot = output_dir / f"map-entry-after-route-{tab}-{stamp}.png"
            screenshot(cdp, shot)
            results["screenshots"].append(str(shot))
            entry["after_route_screenshot"] = str(shot)

            cdp.send("Page.navigate", {"url": f"{args.web_base.rstrip('/')}/projects/{args.project_id}"})
            wait_for(cdp, f"location.href.includes({json.dumps(args.project_id)})", timeout_seconds=25)
            wait_for_text(cdp, SURFACE_MARKERS, timeout_seconds=25)
            time.sleep(1.0)
            results["buttons"].append(entry)

        report = output_dir / f"map-entry-diagnostic-report-{stamp}.json"
        report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    finally:
        if cdp is not None:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        if profile_dir is not None:
            shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
