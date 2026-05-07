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
    parser = argparse.ArgumentParser(description="Validate the A Agent poster-inspired UI theme and NPC rail avatars.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--project-id", default="78151f5f-f08c-4e83-b0fc-9be89263ecb3")
    parser.add_argument("--login-email", default="3245056131@qq.com")
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


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 35, interval_seconds: float = 0.25) -> object:
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
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-a-agent-ui-"))
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
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    cdp.send(
        "Emulation.setDeviceMetricsOverride",
        {"width": args.viewport_width, "height": args.viewport_height, "deviceScaleFactor": 1, "mobile": False},
    )
    return edge_process, profile_dir, cdp


def login(cdp: object, args: argparse.Namespace) -> None:
    cdp.send("Page.navigate", {"url": f"{args.web_base.rstrip('/')}/login"})
    wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('form')")
    result = cdp_eval(
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
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"Login form did not submit: {result}")
    wait_for(cdp, "location.pathname.includes('/projects')", timeout_seconds=45)


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, object] = {"stamp": stamp, "project_id": args.project_id, "screenshots": []}

    edge_process = None
    profile_dir: Path | None = None
    cdp = None
    try:
        edge_process, profile_dir, cdp = launch_edge(args)
        login(cdp, args)

        map_url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}"
        cdp.send("Page.navigate", {"url": map_url})
        wait_for(cdp, "!!document.querySelector('[data-panel-launcher=\"npc-create\"]') && !!document.querySelector('[data-human-party-hud]')")
        wait_for(
            cdp,
            """
            (() => {
              const frame = document.querySelector('iframe');
              const doc = frame && frame.contentDocument;
              return !!(doc && doc.querySelector('canvas'));
            })()
            """,
            timeout_seconds=45,
        )
        time.sleep(2.5)
        dock_state = cdp_eval(
            cdp,
            """
            (() => {
              const buttons = Array.from(document.querySelectorAll('[data-panel-launcher]'));
              return {
                buttonCount: buttons.length,
                labels: buttons.map((button) => button.textContent?.replace(/\\s+/g, ' ').trim() || ''),
                wrappedLabels: buttons.filter((button) => button.scrollWidth > button.clientWidth + 2).length,
                dockDisplay: getComputedStyle(document.querySelector('[aria-label="一级管理入口"]') || document.body).display,
              };
            })()
            """,
        )
        if not isinstance(dock_state, dict) or int(dock_state.get("buttonCount") or 0) <= 0:
            raise RuntimeError(f"Primary dock was not visible: {dock_state}")
        if int(dock_state.get("wrappedLabels") or 0) > 0:
            raise RuntimeError(f"Primary dock labels are clipped or wrapped: {dock_state}")
        results["dock_state"] = dock_state
        map_shot = output_dir / f"a-agent-ui-map-{stamp}.png"
        screenshot(cdp, map_shot)
        results["screenshots"].append(str(map_shot))

        npc_url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=npc-create"
        cdp.send("Page.navigate", {"url": npc_url})
        wait_for(cdp, "!!document.querySelector('#project-main-panel') && new URL(location.href).searchParams.get('tab') === 'npc-create'")
        wait_for(cdp, "!!document.querySelector('[data-poster-npc-avatar=\"true\"]')", timeout_seconds=20)
        wait_for(cdp, "!!document.querySelector('[data-poster-npc-hero-avatar=\"true\"]')", timeout_seconds=20)
        theme_state = cdp_eval(
            cdp,
            """
            (() => {
              const panel = document.querySelector('#project-main-panel');
              const hero = document.querySelector('[data-poster-npc-hero-avatar="true"]');
              const heroStyle = hero ? getComputedStyle(hero) : null;
              const npcAvatars = Array.from(document.querySelectorAll('[data-poster-npc-avatar="true"]')).map((item) => {
                const style = getComputedStyle(item);
                return {
                  backgroundImage: style.backgroundImage,
                  backgroundSize: style.backgroundSize,
                  width: style.width,
                  height: style.height,
                };
              });
              const panelStyle = panel ? getComputedStyle(panel) : null;
              return {
                npcAvatarCount: npcAvatars.length,
                npcAvatars,
                panelBorderColor: panelStyle ? panelStyle.borderColor : "",
                panelBackground: panelStyle ? panelStyle.backgroundImage : "",
                heroAvatarBackground: heroStyle ? heroStyle.backgroundImage : "",
                heroAvatarBackgroundSize: heroStyle ? heroStyle.backgroundSize : "",
                heroAvatarWidth: heroStyle ? heroStyle.width : "",
                heroAvatarHeight: heroStyle ? heroStyle.height : "",
                heading: document.querySelector('#project-main-panel h2')?.textContent?.trim() || "",
              };
            })()
            """,
        )
        if not isinstance(theme_state, dict) or int(theme_state.get("npcAvatarCount") or 0) <= 0:
            raise RuntimeError(f"NPC poster avatars were not visible: {theme_state}")
        if "/assets/a-agent/" not in str(theme_state.get("heroAvatarBackground") or ""):
            raise RuntimeError(f"NPC hero avatar is not using poster art: {theme_state}")
        if str(theme_state.get("heroAvatarBackgroundSize") or "").lower() != "contain":
            raise RuntimeError(f"NPC hero avatar may be cropped by CSS: {theme_state}")
        cropped_rail = [
            item
            for item in theme_state.get("npcAvatars", [])
            if isinstance(item, dict) and str(item.get("backgroundSize") or "").lower() != "contain"
        ]
        if cropped_rail:
            raise RuntimeError(f"NPC rail avatars may be cropped by CSS: {cropped_rail}")
        results["theme_state"] = theme_state
        npc_shot = output_dir / f"a-agent-ui-npc-panel-{stamp}.png"
        screenshot(cdp, npc_shot)
        results["screenshots"].append(str(npc_shot))

        report_path = output_dir / f"a-agent-ui-theme-report-{stamp}.json"
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
