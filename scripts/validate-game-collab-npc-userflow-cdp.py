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
    parser = argparse.ArgumentParser(description="Validate the user-facing Front C 7/8 game collaboration panel.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3010")
    parser.add_argument("--api-base", default="http://106.55.62.122:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/game-collab-qa")
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
    shot_data = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}).get("data")
    if not shot_data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(str(shot_data)))


def set_viewport(cdp: object, width: int, height: int, mobile: bool = False) -> None:
    cdp.send(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": mobile,
        },
    )


def validate_panel(cdp: object) -> dict[str, object]:
    return cdp_eval(
        cdp,
        """
        (() => {
          const root = document.scrollingElement || document.documentElement;
          const panel = document.querySelector('section[aria-label="小游戏双 NPC 协作试运行"]');
          const text = panel?.innerText || '';
          const checked = Array.from(panel?.querySelectorAll('input[name="autonomy_mode"]') || [])
            .filter((input) => input.checked)
            .map((input) => input.value);
          const buttons = Array.from(panel?.querySelectorAll('button') || []).map((button) => button.textContent?.trim());
          const threadLinks = Array.from(panel?.querySelectorAll('a[href^="codex://threads/"]') || [])
            .map((anchor) => anchor.textContent?.trim());
          const evidenceCards = Array.from(panel?.querySelectorAll('[aria-label="桌面接收证据"] article') || [])
            .map((card) => card.textContent?.trim() || '');
          const textarea = panel?.querySelector('textarea[name="brief"]');
          const inject = panel?.querySelector('input[name="brief"]');
          const rect = panel?.getBoundingClientRect();
          return {
            hasPanel: !!panel,
            hasSeven: text.includes('7号') || text.includes('前端 C 7'),
            hasEight: text.includes('8号') || text.includes('前端 C 8'),
            hasAutonomy: ['监督模式', '检查点模式', '完全自主'].every((item) => text.includes(item)),
            hasRisk: text.includes('破坏性操作') && text.includes('token'),
            hasInject: text.includes('插入新需求') && !!inject,
            hasStart: buttons.some((item) => (item || '').includes('启动 7/8 协作')),
            hasDesktopSync: text.includes('桌面同步') && (text.includes('桌面线程') || text.includes('后台接收')),
            hasDesktopEvidence: evidenceCards.length >= 2 && evidenceCards.every((item) => item.includes('桌面证据')),
            hasThreadLinks: threadLinks.some((item) => (item || '').includes('7号线程'))
              && threadLinks.some((item) => (item || '').includes('8号线程')),
            checked,
            textareaValue: textarea?.value || '',
            overflow: Math.max(0, root.scrollWidth - root.clientWidth),
            panelHeight: rect?.height || 0,
          };
        })()
        """,
    )


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    token, user_json = cdp_helpers.authenticate(args)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-game-collab-cdp-"))
    edge_process = None
    cdp = None
    report: dict[str, object] = {
        "verdict": "failed",
        "project_id": args.project_id,
        "web_base": args.web_base,
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
        origin = args.web_base.rstrip("/")
        cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        url = f"{origin}/projects/{args.project_id}/company"

        set_viewport(cdp, 1440, 1050)
        cdp.send("Page.navigate", {"url": url})
        wait_for(cdp, "document.body && document.body.innerText.includes('小游戏协作台')")
        cdp_eval(cdp, "document.querySelector('section[aria-label=\"小游戏双 NPC 协作试运行\"]')?.scrollIntoView({block:'center'}); true")
        time.sleep(0.6)
        desktop = validate_panel(cdp)
        desktop_path = output_dir / f"game-collab-desktop-{stamp}.png"
        screenshot(cdp, desktop_path)
        report["screenshots"].append(str(desktop_path))

        set_viewport(cdp, 390, 900, mobile=True)
        cdp.send("Page.navigate", {"url": url})
        wait_for(cdp, "document.body && document.body.innerText.includes('小游戏协作台')")
        cdp_eval(cdp, "document.querySelector('section[aria-label=\"小游戏双 NPC 协作试运行\"]')?.scrollIntoView({block:'center'}); true")
        time.sleep(0.6)
        mobile = validate_panel(cdp)
        mobile_path = output_dir / f"game-collab-mobile-{stamp}.png"
        screenshot(cdp, mobile_path)
        report["screenshots"].append(str(mobile_path))

        required = [
            "hasPanel",
            "hasSeven",
            "hasEight",
            "hasAutonomy",
            "hasRisk",
            "hasInject",
            "hasStart",
            "hasDesktopSync",
            "hasDesktopEvidence",
            "hasThreadLinks",
        ]
        failures = [
            f"desktop missing {key}" for key in required if not desktop.get(key)
        ] + [
            f"mobile missing {key}" for key in required if not mobile.get(key)
        ]
        if desktop.get("overflow", 0) > 2:
            failures.append(f"desktop horizontal overflow {desktop.get('overflow')}")
        if mobile.get("overflow", 0) > 2:
            failures.append(f"mobile horizontal overflow {mobile.get('overflow')}")
        report["desktop"] = desktop
        report["mobile"] = mobile
        report["failures"] = failures
        report["verdict"] = "passed" if not failures else "failed"
        report_path = output_dir / f"game-collab-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": not failures, "report": str(report_path), "screenshots": report["screenshots"], "failures": failures}, ensure_ascii=False, indent=2))
        return 0 if not failures else 1
    finally:
        if cdp is not None:
            cdp.close()
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
