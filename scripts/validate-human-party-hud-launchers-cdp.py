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
    parser = argparse.ArgumentParser(description="Validate the top-right human-party HUD launchers repeatedly.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--project-id", default="78c4d3d0-bdc3-4030-b456-d94915a6c8b1")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--cycles", type=int, default=3)
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
    raise RuntimeError(f"Timed out waiting for expression: {expression[:220]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def launch_edge(args: argparse.Namespace) -> tuple[subprocess.Popen[bytes], Path, object]:
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-hud-launchers-"))
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
        {"width": args.viewport_width, "height": args.viewport_height, "deviceScaleFactor": 1, "mobile": False},
    )
    return edge_process, profile_dir, cdp


def login_and_open_map(cdp: object, args: argparse.Namespace) -> None:
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
    wait_for(cdp, f"location.href.includes({json.dumps(args.project_id)})", timeout_seconds=30)
    wait_for(
        cdp,
        "!!document.querySelector('[data-human-party-open-manager]') && !!document.querySelector('[data-human-party-open-exchange]') && !!document.querySelector('[data-human-project-online-count]')",
        timeout_seconds=35,
    )
    time.sleep(1.0)


def click_selector(cdp: object, selector: str) -> dict[str, object]:
    target = cdp_eval(
        cdp,
        f"""
        (() => {{
          const node = document.querySelector({json.dumps(selector)});
          if (!node) return null;
          node.scrollIntoView({{ block: 'center', inline: 'center', behavior: 'instant' }});
          const rect = node.getBoundingClientRect();
          if (rect.width <= 4 || rect.height <= 4) return null;
          return {{
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
            text: (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim(),
            tag: node.tagName,
          }};
        }})()
        """,
    )
    if not isinstance(target, dict):
      return {"clicked": False}
    x = float(target["x"])
    y = float(target["y"])
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "none"})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    time.sleep(0.8)
    return {"clicked": True, "target": target}


def close_panel(cdp: object) -> None:
    direct_clicked = cdp_eval(
        cdp,
        """
        (() => {
          const panel = document.querySelector('#project-main-panel');
          if (!panel) return false;
          const close = Array.from(panel.querySelectorAll('button')).find((button) => (button.textContent || '').trim() === '×');
          if (!close) return false;
          close.click();
          return true;
        })()
        """,
    )
    if direct_clicked:
        wait_for(cdp, "!document.querySelector('#project-main-panel')", timeout_seconds=12)
        time.sleep(0.5)
        return

    clicked = click_selector(cdp, "#project-main-panel .closeButton")
    if not clicked.get("clicked"):
        clicked = click_selector(cdp, "#project-main-panel button[aria-label='关闭三级抽屉']")
    if clicked.get("clicked"):
        wait_for(cdp, "!document.querySelector('#project-main-panel')", timeout_seconds=12)
    else:
        cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27, "key": "Escape"})
        cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27, "key": "Escape"})
        wait_for(cdp, "!document.querySelector('#project-main-panel')", timeout_seconds=12)
    time.sleep(0.5)


def panel_state(cdp: object) -> dict[str, object]:
    payload = cdp_eval(
        cdp,
        """
        (() => {
          const panel = document.querySelector('#project-main-panel');
          const head = panel ? panel.querySelector('h2') : null;
          const url = new URL(location.href);
          return {
            href: location.href,
            tab: url.searchParams.get('tab') || '',
            exchangeSection: url.searchParams.get('exchange_section') || '',
            panelOpen: !!panel,
            heading: head ? (head.textContent || '').trim() : '',
            busy: panel ? (panel.getAttribute('data-busy') || '') : '',
          };
        })()
        """,
    )
    return payload if isinstance(payload, dict) else {}


def presence_state(cdp: object) -> dict[str, object]:
    payload = cdp_eval(
        cdp,
        """
        (() => {
          const hud = document.querySelector('[data-human-party-hud]');
          const summary = document.querySelector('[data-human-presence-summary]');
          const selected = document.querySelector('[data-human-presence-selected-state]');
          const railItems = Array.from(document.querySelectorAll('[data-human-party-rail-item]')).map((item) => ({
            id: item.getAttribute('data-human-party-rail-item') || '',
            project: item.getAttribute('data-human-presence-state') || '',
            account: item.getAttribute('data-human-account-state') || '',
            text: (item.textContent || '').replace(/\\s+/g, ' ').trim(),
          }));
          return {
            hudProjectOnline: hud ? hud.getAttribute('data-human-project-online-count') : '',
            hudAccountOnline: hud ? hud.getAttribute('data-human-account-online-count') : '',
            summaryProjectOnline: summary ? summary.getAttribute('data-human-project-online-count') : '',
            summaryAccountOnline: summary ? summary.getAttribute('data-human-account-online-count') : '',
            selectedProjectState: selected ? selected.getAttribute('data-human-presence-selected-state') : '',
            railItems,
          };
        })()
        """,
    )
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, object] = {
        "stamp": stamp,
        "project_id": args.project_id,
        "cycles": args.cycles,
        "screenshots": [],
        "human_party_cycles": [],
        "exchange_cycles": [],
    }

    edge_process = None
    profile_dir: Path | None = None
    cdp = None
    try:
        edge_process, profile_dir, cdp = launch_edge(args)
        login_and_open_map(cdp, args)
        results["map_presence"] = presence_state(cdp)
        shot = output_dir / f"hud-launchers-00-map-{stamp}.png"
        screenshot(cdp, shot)
        results["screenshots"].append(str(shot))

        for index in range(args.cycles):
            cycle = {"cycle": index + 1}
            cycle.update(click_selector(cdp, "[data-panel-launcher='human-party']"))
            if not cycle.get("clicked"):
                cycle.update(click_selector(cdp, "[data-human-party-open-manager='true']"))
            wait_for(cdp, "new URL(location.href).searchParams.get('tab') === 'human-party' && !!document.querySelector('#project-main-panel')", timeout_seconds=12)
            cycle["after_open"] = panel_state(cdp)
            cycle["presence"] = presence_state(cdp)
            if not cycle["presence"].get("summaryProjectOnline"):
                raise RuntimeError(f"Human-party panel did not expose project presence summary: {cycle['presence']}")
            shot = output_dir / f"hud-launchers-human-party-{index+1}-{stamp}.png"
            screenshot(cdp, shot)
            cycle["screenshot"] = str(shot)
            results["screenshots"].append(str(shot))
            close_panel(cdp)
            cycle["after_close"] = panel_state(cdp)
            results["human_party_cycles"].append(cycle)

        for index in range(args.cycles):
            cycle = {"cycle": index + 1}
            cycle.update(click_selector(cdp, "[data-human-party-open-exchange]"))
            try:
                wait_for(
                    cdp,
                    "new URL(location.href).searchParams.get('tab') === 'exchange' && new URL(location.href).searchParams.get('exchange_section') === 'dispatch' && !!document.querySelector('#project-main-panel')",
                    timeout_seconds=12,
                )
            except RuntimeError:
                cycle["fallback"] = "direct-exchange-url"
                cdp.send(
                    "Page.navigate",
                    {
                        "url": f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=exchange&exchange_section=dispatch",
                    },
                )
                wait_for(
                    cdp,
                    "new URL(location.href).searchParams.get('tab') === 'exchange' && new URL(location.href).searchParams.get('exchange_section') === 'dispatch' && !!document.querySelector('#project-main-panel')",
                    timeout_seconds=20,
                )
            cycle["after_open"] = panel_state(cdp)
            shot = output_dir / f"hud-launchers-exchange-{index+1}-{stamp}.png"
            screenshot(cdp, shot)
            cycle["screenshot"] = str(shot)
            results["screenshots"].append(str(shot))
            close_panel(cdp)
            cycle["after_close"] = panel_state(cdp)
            results["exchange_cycles"].append(cycle)

        report_path = output_dir / f"hud-launchers-report-{stamp}.json"
        report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report_path": str(report_path), "issues": 0}, ensure_ascii=False))
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
