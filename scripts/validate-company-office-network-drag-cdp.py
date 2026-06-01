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
    parser = argparse.ArgumentParser(description="Validate draggable NPC office network on company page.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/company-office-network-qa")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=1050)
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
    value = result.get("result", {})
    return value.get("value") if isinstance(value, dict) else None


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 20, interval_seconds: float = 0.25) -> object:
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
    shot_data = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}).get("data")
    if not shot_data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(str(shot_data)))


def run_alignment_precheck(args: argparse.Namespace) -> dict[str, object]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "check_web_api_alignment.py"),
        "--web-base",
        args.web_base,
        "--api-base",
        args.api_base,
        "--project-id",
        args.project_id,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    body = completed.stdout.strip() or completed.stderr.strip()
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        data = {"ok": False, "issues": [body or "alignment probe returned no output"]}
    data["exit_code"] = completed.returncode
    return data


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    alignment = run_alignment_precheck(args)
    if not alignment.get("ok"):
      raise RuntimeError(f"Alignment precheck failed: {json.dumps(alignment, ensure_ascii=False)[:2000]}")

    token, user_json = cdp_helpers.authenticate(args)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-office-network-cdp-"))
    edge_process = None
    cdp = None
    report: dict[str, object] = {
        "verdict": "passed",
        "project_id": args.project_id,
        "alignment": alignment,
        "screenshots": [],
    }
    try:
        port = cdp_helpers.find_free_port()
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
        page_target = next(
            (item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")),
            None,
        )
        if not isinstance(page_target, dict):
            raise RuntimeError("No page target available")

        cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.viewport_width,
                "height": args.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        origin = args.web_base.rstrip("/")
        cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        url = f"{origin}/projects/{args.project_id}/company"
        cdp.send("Page.navigate", {"url": url})

        wait_for(
            cdp,
            """
            (() => {
              const text = document.body?.innerText || '';
              return text.includes('NPC 办公网') && document.querySelectorAll('section[aria-label="NPC 办公网"] a[href*="seat="]').length > 0;
            })()
            """,
        )
        time.sleep(1.0)
        before = cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const node = section?.querySelector('a[href*="seat="]');
              const line = section?.querySelector('svg a[data-kind] line[stroke-width]');
              const root = document.scrollingElement || document.documentElement;
              if (!section || !node || !line) return null;
              const rect = node.getBoundingClientRect();
              return {
                node: { left: rect.left, top: rect.top, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
                line: { x1: line.getAttribute('x1'), y1: line.getAttribute('y1'), x2: line.getAttribute('x2'), y2: line.getAttribute('y2') },
                overflow: Math.max(0, root.scrollWidth - root.clientWidth),
              };
            })()
            """,
        )
        if not isinstance(before, dict):
            raise RuntimeError("Office network nodes or lines were not available")
        if int(before.get("overflow") or 0) > 2:
            raise RuntimeError(f"Company page has horizontal overflow before drag: {before['overflow']}")

        before_shot = output_dir / f"office-network-before-drag-{stamp}.png"
        screenshot(cdp, before_shot)
        report["screenshots"].append(str(before_shot))

        start_x = float(before["node"]["x"])
        start_y = float(before["node"]["y"])
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": start_x, "y": start_y, "button": "none"})
        cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": start_x, "y": start_y, "button": "left", "clickCount": 1})
        for step in range(1, 9):
            cdp.send(
                "Input.dispatchMouseEvent",
                {
                    "type": "mouseMoved",
                    "x": start_x + step * 14,
                    "y": start_y + step * 7,
                    "button": "left",
                    "buttons": 1,
                },
            )
            time.sleep(0.05)
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": start_x + 112, "y": start_y + 56, "button": "left", "clickCount": 1})
        time.sleep(0.8)

        after = cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const node = section?.querySelector('a[href*="seat="]');
              const line = section?.querySelector('svg a[data-kind] line[stroke-width]');
              const root = document.scrollingElement || document.documentElement;
              if (!section || !node || !line) return null;
              const rect = node.getBoundingClientRect();
              return {
                node: { left: rect.left, top: rect.top, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
                line: { x1: line.getAttribute('x1'), y1: line.getAttribute('y1'), x2: line.getAttribute('x2'), y2: line.getAttribute('y2') },
                overflow: Math.max(0, root.scrollWidth - root.clientWidth),
              };
            })()
            """,
        )
        if not isinstance(after, dict):
            raise RuntimeError("Office network disappeared after drag")
        node_moved = abs(float(after["node"]["x"]) - start_x) > 24 or abs(float(after["node"]["y"]) - start_y) > 24
        line_changed = json.dumps(before.get("line"), sort_keys=True) != json.dumps(after.get("line"), sort_keys=True)
        if not node_moved:
            raise RuntimeError(f"NPC node did not move enough: before={before['node']} after={after['node']}")
        if not line_changed:
            raise RuntimeError(f"Office network line did not follow drag: before={before['line']} after={after['line']}")
        if int(after.get("overflow") or 0) > 2:
            raise RuntimeError(f"Company page has horizontal overflow after drag: {after['overflow']}")

        click_target = cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const link = section?.querySelector('svg [data-kind]');
              const line = link?.querySelector('line[stroke-width]');
              const svg = section?.querySelector('svg');
              if (!link || !line || !svg) return null;
              const rect = svg.getBoundingClientRect();
              const x1 = Number(line.getAttribute('x1') || 0);
              const y1 = Number(line.getAttribute('y1') || 0);
              const x2 = Number(line.getAttribute('x2') || 0);
              const y2 = Number(line.getAttribute('y2') || 0);
              return {
                x: rect.left + ((x1 + x2) / 2 / 100) * rect.width,
                y: rect.top + ((y1 + y2) / 2 / 100) * rect.height,
              };
            })()
            """,
        )
        if not isinstance(click_target, dict):
            raise RuntimeError(f"Could not find an office network line to click: {click_target}")
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": float(click_target["x"]), "y": float(click_target["y"]), "button": "none"})
        cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": float(click_target["x"]), "y": float(click_target["y"]), "button": "left", "clickCount": 1})
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": float(click_target["x"]), "y": float(click_target["y"]), "button": "left", "clickCount": 1})
        time.sleep(0.5)
        detail = cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const drawer = section.querySelector('[aria-label="协作线详情"]');
              const detailLink = drawer?.querySelector('a[href*="/workbench"]');
              return {
                drawerText: (drawer?.textContent || '').trim(),
                detailHref: detailLink?.getAttribute('href') || '',
                selected: section.querySelectorAll('svg [data-selected="1"]').length,
              };
            })()
            """,
        )
        if not isinstance(detail, dict) or not detail.get("drawerText") or not detail.get("detailHref"):
            raise RuntimeError(f"Clicking a collaboration line did not open details: {detail}")
        if int(detail.get("selected") or 0) < 1:
            raise RuntimeError(f"Clicked line was not visually selected: {detail}")

        filtered = cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const button = Array.from(section?.querySelectorAll('button') || []).find((item) => item.textContent?.trim() === '真实');
              button?.click();
              const edgeCount = section?.querySelectorAll('svg [data-kind="collaboration"]').length || 0;
              const dimmedNodes = section?.querySelectorAll('a[data-dimmed="1"]').length || 0;
              return {
                edgeCount,
                dimmedNodes,
                activeText: button?.getAttribute('data-active') || '',
              };
            })()
            """,
        )
        if not isinstance(filtered, dict) or filtered.get("activeText") != "1":
            raise RuntimeError(f"Office network filter did not activate: {filtered}")

        after_shot = output_dir / f"office-network-after-drag-{stamp}.png"
        screenshot(cdp, after_shot)
        report["screenshots"].append(str(after_shot))
        report["before"] = before
        report["after"] = after
        report["detail"] = detail
        report["filtered"] = filtered
        report["url"] = url
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)

    report_path = output_dir / f"office-network-drag-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": "passed", "report_path": str(report_path), "screenshots": report["screenshots"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
