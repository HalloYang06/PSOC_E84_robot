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
    parser = argparse.ArgumentParser(description="Validate login -> project farm -> NPC dialog through Edge CDP.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", required=True)
    parser.add_argument("--login-password", required=True)
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=2048)
    parser.add_argument("--viewport-height", type=int, default=1152)
    return parser.parse_args()


def cdp_eval(cdp: object, expression: str, timeout_seconds: float = 20) -> object:
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
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-login-flow-edge-"))
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

        cdp.send("Page.navigate", {"url": f"{web_base}/login"})
        wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('form')")
        shot_login = output_dir / f"user-login-01-login-page-{stamp}.png"
        screenshot(cdp, shot_login)

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

        wait_for(cdp, "location.pathname.includes('/projects')", timeout_seconds=35)
        time.sleep(1.0)
        shot_projects = output_dir / f"user-login-02-projects-after-login-{stamp}.png"
        screenshot(cdp, shot_projects)

        project_click = cdp_eval(
            cdp,
            f"""
            (() => {{
              const link = Array.from(document.querySelectorAll('a')).find((item) =>
                (item.getAttribute('href') || '').includes({json.dumps(args.project_id)})
              );
              if (!link) return {{ ok: false, reason: 'missing-project-link', text: document.body.innerText.slice(0, 600) }};
              link.click();
              return {{ ok: true, href: link.getAttribute('href'), label: link.textContent.trim().slice(0, 80) }};
            }})()
            """,
        )
        if not isinstance(project_click, dict) or not project_click.get("ok"):
            cdp.send("Page.navigate", {"url": f"{web_base}/projects/{args.project_id}"})

        wait_for(cdp, f"location.href.includes({json.dumps(args.project_id)})", timeout_seconds=35)
        wait_for(cdp, "!!document.querySelector('iframe')", timeout_seconds=35)
        wait_for(
            cdp,
            "(() => { const frame = document.querySelector('iframe'); return !!(frame && frame.contentDocument && frame.contentDocument.readyState === 'complete'); })()",
            timeout_seconds=35,
        )
        wait_for(
            cdp,
            """
            (() => {
              const frame = document.querySelector('iframe');
              const doc = frame && frame.contentDocument;
              const win = frame && frame.contentWindow;
              return !!(doc && doc.body && win);
            })()
            """,
            timeout_seconds=45,
        )
        time.sleep(3.0)

        npc_info = cdp_eval(
            cdp,
            """
            (() => {
              const frame = document.querySelector('iframe');
              const doc = frame && frame.contentDocument;
              const win = frame && frame.contentWindow;
              if (!doc || !win) return { count: 0, reason: 'missing-iframe-document' };
              const nodes = Array.from(doc.querySelectorAll('.entity.seat-npc'));
              const visibleNodes = nodes.filter((node) => {
                const style = win.getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
              });
              return {
                count: nodes.length,
                visible: visibleNodes.length,
                visibleNames: visibleNodes.slice(0, 8).map((node) => (node.querySelector('.entity-nameplate')?.textContent || node.textContent || '').trim()),
                rects: nodes.slice(0, 8).map((node) => {
                  const rect = node.getBoundingClientRect();
                  return {
                    className: node.className,
                    left: node.style.left,
                    top: node.style.top,
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                    text: (node.querySelector('.entity-nameplate')?.textContent || '').trim(),
                    avatarClass: node.querySelector('.entity-avatar')?.className || ''
                  };
                }),
                hiddenClutter: nodes[0] ? {
                  flags: win.getComputedStyle(nodes[0].querySelector('.entity-seat-flags')).display,
                  badge: win.getComputedStyle(nodes[0].querySelector('.entity-seat-badge')).display,
                  prompt: win.getComputedStyle(nodes[0].querySelector('.entity-enter-prompt')).display,
                  step: win.getComputedStyle(nodes[0].querySelector('.entity-nameplate-step')).display
                } : null,
                payload: JSON.parse(win.localStorage.getItem('farm-platform-codex-seats-v1') || '{}').seats?.slice(0, 6).map((seat) => ({
                  id: seat.id,
                  name: seat.name,
                  x: seat.x,
                  y: seat.y,
                  avatar: seat.avatar
                })) || [],
                worldNpcs: (win.__platformSeatNpcWorldSnapshot || []).slice(0, 8)
              };
            })()
            """,
        )
        shot_map = output_dir / f"user-login-03-project-farm-map-{stamp}.png"
        screenshot(cdp, shot_map)
        shot_outdoor = None
        outdoor_npc_info = None

        if not (isinstance(npc_info, dict) and npc_info.get("worldNpcs")):
            outdoor_nav = cdp_eval(
                cdp,
                """
                (() => {
                  const frame = document.querySelector('iframe');
                  if (!frame) return { ok: false, reason: 'missing-iframe' };
                  const url = new URL(frame.src, location.href);
                  url.searchParams.set('scene', 'map-farm');
                  url.searchParams.set('x', '760');
                  url.searchParams.set('y', '720');
                  url.searchParams.delete('focus');
                  frame.src = url.toString();
                  return { ok: true, url: frame.src };
                })()
                """,
            )
            if not isinstance(outdoor_nav, dict) or not outdoor_nav.get("ok"):
                raise RuntimeError(f"Could not switch iframe to outdoor NPC scene: {outdoor_nav}")
            wait_for(
                cdp,
                "(() => { const frame = document.querySelector('iframe'); const doc = frame && frame.contentDocument; return !!(doc && doc.readyState === 'complete'); })()",
                timeout_seconds=35,
            )
            wait_for(
                cdp,
                "(() => { const frame = document.querySelector('iframe'); const win = frame && frame.contentWindow; return !!(win && Array.isArray(win.__platformSeatNpcWorldSnapshot) && win.__platformSeatNpcWorldSnapshot.length); })()",
                timeout_seconds=45,
            )
            time.sleep(1.0)
            outdoor_npc_info = cdp_eval(
                cdp,
                """
                (() => {
                  const frame = document.querySelector('iframe');
                  const win = frame && frame.contentWindow;
                  if (!win) return { count: 0, reason: 'missing-iframe-window' };
                  return {
                    iframeUrl: frame.src,
                    worldNpcs: (win.__platformSeatNpcWorldSnapshot || []).slice(0, 8)
                  };
                })()
                """,
            )
            shot_outdoor = output_dir / f"user-login-03b-project-outdoor-npc-map-{stamp}.png"
            screenshot(cdp, shot_outdoor)

        world_click_point = cdp_eval(
            cdp,
            """
            (() => {
              const frame = document.querySelector('iframe');
              const doc = frame && frame.contentDocument;
              const win = frame && frame.contentWindow;
              if (!doc || !win) return { ok: false, reason: 'missing-iframe-document' };
              const worldNpcs = Array.isArray(win.__platformSeatNpcWorldSnapshot) ? win.__platformSeatNpcWorldSnapshot : [];
              const npc = worldNpcs.find((item) => Number.isFinite(Number(item.screenX)) && Number.isFinite(Number(item.screenY)));
              if (!npc) return { ok: false, reason: 'missing-phaser-npc', worldNpcs };
              const frameRect = frame.getBoundingClientRect();
              return {
                ok: true,
                x: frameRect.left + Number(npc.screenX),
                y: frameRect.top + Number(npc.screenY),
                npc
              };
            })()
            """,
        )
        npc_click = {"ok": False, "mode": "phaser-world", "point": world_click_point}
        if isinstance(world_click_point, dict) and world_click_point.get("ok"):
            click_x = float(world_click_point["x"])
            click_y = float(world_click_point["y"])
            cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": click_x, "y": click_y})
            cdp.send(
                "Input.dispatchMouseEvent",
                {"type": "mousePressed", "x": click_x, "y": click_y, "button": "left", "clickCount": 1},
            )
            cdp.send(
                "Input.dispatchMouseEvent",
                {"type": "mouseReleased", "x": click_x, "y": click_y, "button": "left", "clickCount": 1},
            )
            time.sleep(1.0)
            npc_click = cdp_eval(
                cdp,
                """
                (() => ({
                  ok: location.href.includes('seat=') || !!document.querySelector('textarea[name="body"], textarea'),
                  mode: 'phaser-world',
                  url: location.href,
                  hasTextarea: !!document.querySelector('textarea[name="body"], textarea')
                }))()
                """,
            )
        if not isinstance(npc_click, dict) or not npc_click.get("ok"):
            npc_click = cdp_eval(
                cdp,
                """
                (() => {
                  const frame = document.querySelector('iframe');
                  const doc = frame && frame.contentDocument;
                  const win = frame && frame.contentWindow;
                  if (!doc || !win) return { ok: false, reason: 'missing-iframe-document', mode: 'dom-fallback' };
                  const nodes = Array.from(doc.querySelectorAll('.entity.seat-npc'));
                  const node = nodes.find((item) => item.classList.contains('visible')) || nodes[0];
                  if (!node) return { ok: false, reason: 'missing-npc', mode: 'dom-fallback' };
                  const target = node.querySelector('.entity-avatar-shell, .entity-nameplate, button') || node;
                  target.dispatchEvent(new win.MouseEvent('click', { bubbles: true, cancelable: true, view: win }));
                  return { ok: true, mode: 'dom-fallback', className: node.className, text: (node.textContent || '').trim().slice(0, 120) };
                })()
                """,
            )
        if not isinstance(npc_click, dict) or not npc_click.get("ok"):
            raise RuntimeError(f"NPC click failed: {npc_click}")
        wait_for(cdp, "location.href.includes('seat=') || !!document.querySelector('textarea[name=\"body\"], textarea')", timeout_seconds=25)
        time.sleep(1.0)
        shot_dialog = output_dir / f"user-login-04-npc-dialog-from-map-{stamp}.png"
        screenshot(cdp, shot_dialog)

        dialog_info = cdp_eval(
            cdp,
            """
            (() => ({
              url: location.href,
              hasTextarea: !!document.querySelector('textarea[name="body"], textarea'),
              bodyText: document.body.innerText.slice(0, 1200)
            }))()
            """,
        )

        report = {
            "stamp": stamp,
            "project_id": args.project_id,
            "login_email": args.login_email,
            "screenshots": [
                str(shot_login),
                str(shot_projects),
                str(shot_map),
                *([str(shot_outdoor)] if shot_outdoor else []),
                str(shot_dialog),
            ],
            "login_result": login_result,
            "project_click": project_click,
            "npc_info": npc_info,
            "outdoor_npc_info": outdoor_npc_info,
            "npc_click": npc_click,
            "dialog_info": dialog_info,
            "final_url": dialog_info.get("url") if isinstance(dialog_info, dict) else "",
        }
        report_path = output_dir / f"user-login-npc-flow-report-{stamp}.json"
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
