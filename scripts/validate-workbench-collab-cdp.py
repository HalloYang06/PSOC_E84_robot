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
    parser = argparse.ArgumentParser(description="Validate project workbench NPC collaboration UI through real Edge CDP.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="proj_ai_collab")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/page-audit-20260509-continued")
    parser.add_argument("--viewport-width", type=int, default=1440)
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
    value = result.get("result", {})
    return value.get("value") if isinstance(value, dict) else None


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
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    token, user_json = cdp_helpers.authenticate(args)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-workbench-edge-"))
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
            {
                "width": args.viewport_width,
                "height": args.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        origin = args.web_base.rstrip("/")
        cdp.send(
            "Network.setCookie",
            {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
        )
        if user_json:
            cdp.send(
                "Network.setCookie",
                {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
            )

        url = f"{origin}/projects/{args.project_id}/workbench"
        cdp.send("Page.navigate", {"url": url})
        wait_for(cdp, "document.readyState === 'complete' && document.body && document.body.innerText.includes('协同工作台')")
        time.sleep(1.0)
        wait_for(cdp, "document.body && document.body.innerText.includes('Boss NPC 项目生成器')", timeout_seconds=20)
        boss_result = cdp_eval(
            cdp,
            """
            (() => {
              const panel = document.querySelector('[data-testid="boss-npc-project-generator"]');
              if (!panel) return { ok: false, reason: 'missing-boss-panel' };
              const textarea = panel.querySelector('textarea');
              const button = Array.from(panel.querySelectorAll('button')).find((item) => (item.textContent || '').includes('生成分工方案'));
              if (!textarea || !button) return { ok: false, reason: 'missing-boss-controls' };
              textarea.focus();
              const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
              setter.call(textarea, '做一个 only 提示词就能让 Boss NPC 拆解、创建 NPC 建议、派发到 Codex 和 Claude Code 线程并完成验收的 AI 协作平台。');
              textarea.dispatchEvent(new Event('input', { bubbles: true }));
              textarea.dispatchEvent(new Event('change', { bubbles: true }));
              button.click();
              return { ok: true };
            })()
            """,
        )
        if not isinstance(boss_result, dict) or not boss_result.get("ok"):
            raise RuntimeError(f"Boss NPC flow could not start: {boss_result}")
        wait_for(
            cdp,
            "document.body && document.body.innerText.includes('派发给现有 NPC') && document.body.innerText.includes('项目 Boss / 产品拆解') && document.body.innerText.includes('真实浏览器') && document.body.innerText.includes('Boss 线程') && document.body.innerText.includes('项目运行契约') && document.body.innerText.includes('docs/ai-handoffs/project-operating-contract.md')",
            timeout_seconds=20,
        )
        boss_button_state = cdp_eval(
            cdp,
            """
            (() => {
              const panel = document.querySelector('[data-testid="boss-npc-project-generator"]');
              const button = panel ? Array.from(panel.querySelectorAll('button')).find((item) => (item.textContent || '').includes('派发给现有 NPC')) : null;
              return { disabled: button ? button.disabled : null, text: document.body.innerText.includes('Boss 线程未绑定') };
            })()
            """,
        )
        shot_boss = output_dir / f"workbench-real-00-boss-plan-{stamp}.png"
        screenshot(cdp, shot_boss)
        shot_overview = output_dir / f"workbench-real-01-overview-{stamp}.png"
        screenshot(cdp, shot_overview)

        time.sleep(2.0)
        click_result = cdp_eval(
            cdp,
            """
            (() => {
              const buttons = Array.from(document.querySelectorAll('button'));
              const openButton = buttons.find((button) => (button.getAttribute('title') || '') === '打开瓷砖');
              if (!openButton) return { ok: false, reason: 'missing-open-tile-button', body: document.body.innerText.slice(0, 1000) };
              openButton.scrollIntoView({ block: 'center', inline: 'center' });
              openButton.click();
              return { ok: true, text: openButton.textContent, title: openButton.getAttribute('title') };
            })()
            """,
        )
        if not isinstance(click_result, dict) or not click_result.get("ok"):
            raise RuntimeError(f"Could not open NPC tile: {click_result}")

        try:
            wait_for(cdp, "document.body && document.body.innerText.includes('精简协作对话')", timeout_seconds=20)
        except Exception as exc:
            debug = cdp_eval(
                cdp,
                """
                (() => ({
                  body: document.body.innerText.slice(0, 1800),
                  buttons: Array.from(document.querySelectorAll('button')).slice(0, 80).map((button, index) => ({
                    index,
                    text: (button.textContent || '').trim(),
                    title: button.getAttribute('title'),
                    disabled: button.disabled,
                    className: button.className,
                  })),
                }))()
                """,
            )
            debug_path = output_dir / f"workbench-real-debug-after-click-{stamp}.json"
            debug_path.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
            raise RuntimeError(f"NPC tile did not open after click; debug={debug_path}") from exc
        time.sleep(1.0)
        tile_text = str(cdp_eval(cdp, "document.body ? document.body.innerText : ''") or "")
        required_markers = ["NPC 自动化", "精简协作对话", "协作事件线", "start-thread-watcher.ps1"]
        missing = [marker for marker in required_markers if marker not in tile_text]
        if missing:
            raise RuntimeError(f"Workbench tile missing markers: {missing}")

        raw_click = cdp_eval(
            cdp,
            """
            (() => {
              const button = Array.from(document.querySelectorAll('button')).find((item) => (item.textContent || '').includes('查看原文'));
              if (!button) return { ok: false, reason: 'no-raw-button' };
              button.scrollIntoView({ block: 'center', inline: 'nearest' });
              button.click();
              return { ok: true, text: button.textContent };
            })()
            """,
        )
        time.sleep(0.6)
        shot_tile = output_dir / f"workbench-real-02-npc-tile-{stamp}.png"
        screenshot(cdp, shot_tile)

        post_text = str(cdp_eval(cdp, "document.body ? document.body.innerText : ''") or "")
        report = {
            "verdict": "passed",
            "url": url,
            "project_id": args.project_id,
            "login_email": args.login_email,
            "boss_result": boss_result,
            "boss_button_state": boss_button_state,
            "click_result": click_result,
            "raw_click": raw_click,
            "markers": {marker: marker in post_text for marker in [*required_markers, "Boss NPC 项目生成器", "Boss 线程未绑定", "项目运行契约", "docs/ai-handoffs/project-operating-contract.md", "派发给现有 NPC", "创建 NPC / skill 缺口", "线程回执原文", "查看原文"]},
            "screenshots": [str(shot_boss), str(shot_overview), str(shot_tile)],
        }
        report_path = output_dir / f"workbench-real-validation-report-{stamp}.json"
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
