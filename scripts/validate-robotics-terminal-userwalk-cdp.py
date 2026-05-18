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
from urllib.parse import quote, urlparse


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="User-view validation for robotics terminal tiles.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/p1-workbench-rebuild")
    parser.add_argument("--viewport-width", type=int, default=1880)
    parser.add_argument("--viewport-height", type=int, default=920)
    return parser.parse_args()


def js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def cdp_eval(cdp: object, expression: str) -> object:
    result = cdp.send(
        "Runtime.evaluate",
        {"expression": expression, "awaitPromise": True, "returnByValue": True, "userGesture": True},
    )
    if "exceptionDetails" in result:
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1600])
    payload = result.get("result", {})
    return payload.get("value") if isinstance(payload, dict) else None


def wait_for(cdp: object, expression: str, timeout_seconds: float = 35) -> object:
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
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {expression[:180]} last={last}")


def screenshot(cdp: object, path: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    path.write_bytes(base64.b64decode(str(shot.get("data") or "")))


def click(cdp: object, selector: str) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const el = document.querySelector({js(selector)});
          if (!el) return {{ ok: false, reason: 'missing', selector: {js(selector)} }};
          el.scrollIntoView({{ block: 'center', inline: 'center' }});
          const rect = el.getBoundingClientRect();
          return {{ ok: true, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, text: el.innerText || el.value || '' }};
        }})()
        """,
    )
    if not isinstance(state, dict) or not state.get("ok"):
        raise RuntimeError(f"Cannot click {selector}: {state}")
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": state["x"], "y": state["y"]})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": state["x"], "y": state["y"], "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": state["x"], "y": state["y"], "button": "left", "clickCount": 1})
    return state


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report: dict[str, object] = {"project_id": args.project_id, "web_base": web_base, "steps": [], "failures": []}

    token, user_json = cdp_helpers.authenticate(args)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="robotics-terminal-walk-"))
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
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        targets = cdp_helpers.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page"), None)
        if not page_target:
            raise RuntimeError("No browser page target")
        cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.sock.settimeout(60)
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        cdp.send("Emulation.setDeviceMetricsOverride", {
            "width": args.viewport_width,
            "height": args.viewport_height,
            "deviceScaleFactor": 1,
            "mobile": False,
        })
        origin = f"{urlparse(web_base).scheme}://{urlparse(web_base).netloc}"
        if token:
            cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
            if user_json:
                cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})

        url = f"{web_base}/projects/{quote(args.project_id, safe='')}/robotics"
        cdp.send("Page.navigate", {"url": url})
        wait_for(cdp, "document.readyState === 'complete' && document.body.innerText.includes('机器人现场')")
        first = cdp_eval(
            cdp,
            """
            (() => {
              const body = document.body.innerText || '';
              return {
                href: location.href,
                hasIndexSelect: !!document.querySelector('[class*="indexForm"] select[name="windows"]'),
                usableOptions: Array.from(document.querySelectorAll('[class*="indexForm"] select[name="windows"] option')).filter((item) => item.value).length,
                openButtons: document.querySelectorAll('a[aria-label^="打开 "]').length,
                settingsButtons: document.querySelectorAll('a[aria-label^="设置 "]').length,
                createButtonText: document.querySelector('[class*="indexForm"] button')?.innerText || '',
                interfaceLabel: document.querySelector('[class*="indexForm"] label span')?.innerText || '',
                hasCreateTitle: body.includes('创建调试窗口'),
                hasComputerJumpButton: Array.from(document.querySelectorAll('a')).some((a) => (a.innerText || '').includes('接入/检查电脑')),
                hasNpcCreationSelect: !!document.querySelector('[class*="indexForm"] select[name="npc"]'),
                disabledMarkers: document.querySelectorAll('[class*="openBtnDisabled"]').length,
                hasNoDemoText: body.includes('不建假窗口') && !body.includes('模板'),
                hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
              };
            })()
            """,
        )
        report["initial"] = first
        screenshot(cdp, output_dir / f"robotics-terminal-userwalk-initial-{stamp}.png")

        if isinstance(first, dict) and int(first.get("usableOptions") or 0) > 0:
            if first.get("hasComputerJumpButton"):
                report["failures"].append("robotics page still has computer jump button")  # type: ignore[union-attr]
            if not first.get("hasCreateTitle") or not first.get("hasNpcCreationSelect"):
                report["failures"].append("debug window creation does not expose indexed NPC selection")  # type: ignore[union-attr]
            click(cdp, '[class*="indexForm"] button')
            wait_for(cdp, "location.search.includes('windows=') && document.querySelectorAll('article').length > 0")
            time.sleep(0.5)
            tile = cdp_eval(
                cdp,
                """
                (() => {
                  const body = document.body.innerText || '';
                  const form = document.querySelector('form[class*="terminalCommandBar"]');
                  return {
                    href: location.href,
                    tileCount: document.querySelectorAll('article[class*="debugTilePanel"]').length,
                    hasTerminal: body.includes('$ open') && body.includes('mode=read-only'),
                    hasTerminalIo: body.includes('--- I/O ---') && (body.includes('[terminal]') || body.includes('[ack]') || body.includes('[result') || body.includes('# queued')),
                    hasNpcSelect: !!document.querySelector('select[name="bound_npc"]'),
                    hasCommandInput: !!document.querySelector('input[name="command"]'),
                    submitDisabled: !!form?.querySelector('button[type="submit"]')?.disabled,
                    hasTileSettingsLink: !!document.querySelector('a[aria-label^="设置 "]'),
                    hasJumpSelectNpc: Array.from(document.querySelectorAll('a')).some((a) => (a.innerText || '').includes('选择 NPC')),
                    hasInternalTerms: /adapter|session JSONL|local path|source_thread|canonical|requested id|raw UUID/.test(body),
                    hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
                  };
                })()
                """,
            )
            report["tile"] = tile
            screenshot(cdp, output_dir / f"robotics-terminal-userwalk-tile-{stamp}.png")
            if not isinstance(tile, dict) or not tile.get("hasTerminal") or not tile.get("hasTerminalIo") or not tile.get("hasNpcSelect") or not tile.get("hasCommandInput"):
                report["failures"].append("terminal tile controls missing")  # type: ignore[union-attr]
            if isinstance(tile, dict) and tile.get("hasJumpSelectNpc"):
                report["failures"].append("NPC binding still jumps away")  # type: ignore[union-attr]
            click(cdp, 'a[aria-label^="设置 "]')
            wait_for(cdp, "location.search.includes('settings=') && document.body.innerText.includes('窗口设置')")
            settings_state = cdp_eval(
                cdp,
                """
                (() => {
                  const body = document.body.innerText || '';
                  return {
                    href: location.href,
                    hasSettingsPanel: body.includes('窗口设置') && body.includes('电脑 runner') && body.includes('调试接口') && body.includes('协助 NPC'),
                    stillOnRobotics: location.pathname.endsWith('/robotics'),
                    hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
                  };
                })()
                """,
            )
            report["settings"] = settings_state
            screenshot(cdp, output_dir / f"robotics-terminal-userwalk-settings-{stamp}.png")
            if not isinstance(settings_state, dict) or not settings_state.get("hasSettingsPanel") or not settings_state.get("stillOnRobotics"):
                report["failures"].append("settings panel did not open in-place")  # type: ignore[union-attr]
        else:
            empty_ok = isinstance(first, dict) and first.get("hasNoDemoText") and int(first.get("openButtons") or 0) == 0
            if not empty_ok:
                report["failures"].append("empty/no-device state is misleading")  # type: ignore[union-attr]

        if isinstance(first, dict) and first.get("hasHorizontalOverflow"):
            report["failures"].append("initial horizontal overflow")  # type: ignore[union-attr]
        report["verdict"] = "passed" if not report["failures"] else "failed"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["verdict"] == "passed" else 1
    except Exception as exc:  # noqa: BLE001
        report["verdict"] = "failed"
        report["error"] = str(exc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
