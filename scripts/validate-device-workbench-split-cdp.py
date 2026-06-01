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


FORBIDDEN_RE = r"adapter|bridge|session JSONL|local path|source_thread|canonical|requested id|raw UUID|camera_keyframe|\bJSONL\b|source=rehab-arm-control"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate device data workbench and rehab-arm control split from user view.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/validation/device-workbench-split")
    return parser.parse_args()


def js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def cdp_eval(cdp: object, expression: str) -> object:
    result = cdp.send("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True, "userGesture": True})
    if "exceptionDetails" in result:
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1600])
    payload = result.get("result", {})
    return payload.get("value") if isinstance(payload, dict) else None


def wait_for(cdp: object, expression: str, timeout_seconds: float = 45) -> object:
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


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    output.write_bytes(base64.b64decode(str(shot.get("data") or "")))


def set_viewport(cdp: object, width: int, height: int) -> None:
    cdp.send("Emulation.setDeviceMetricsOverride", {
        "width": width,
        "height": height,
        "deviceScaleFactor": 1,
        "mobile": width < 700,
    })


def page_state(cdp: object, kind: str) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          const href = location.href;
          const forbidden = Array.from(new Set(body.match(new RegExp({js(FORBIDDEN_RE)}, 'ig')) || []));
          const links = Array.from(document.querySelectorAll('a')).map((a) => (a.innerText || '').replace(/\\s+/g, ' ').trim());
          return {{
            kind: {js(kind)},
            href,
            title: document.title,
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
            forbidden,
            bodySample: body.slice(0, 2400),
            hasBlankMain: !body.trim() || document.querySelectorAll('main *').length < 8,
            roboticsSplit: body.includes('设备数据工作台') && body.includes('专项设备总控台') && body.includes('终端') && body.includes('数据标注') && body.includes('图表实验'),
            roboticsGenericLoop: body.includes('真实接口扫描') && body.includes('采集片段') && body.includes('打开专项总控'),
            rehabReadonly: body.includes('只读总览') && body.includes('不发 CAN') && body.includes('M33') && body.includes('NanoPi'),
            rehabDifferentFromRobotics: body.includes('康复机械臂专项总控') && !body.includes('通用设备数据工作台 · 终端 / 数据标注 / 图表实验'),
            hasWorkbenchBackLink: links.some((text) => text.includes('设备数据工作台')),
            urlExposesSource: href.includes('source='),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"invalid page state: {state!r}")
    return state


def validate_page(cdp: object, web_base: str, project_id: str, path: str, kind: str, output_dir: Path, stamp: str, width: int, height: int) -> dict[str, object]:
    set_viewport(cdp, width, height)
    cdp.send("Page.navigate", {"url": f"{web_base}/projects/{quote(project_id, safe='')}/{path}"})
    wait_for(cdp, "document.readyState === 'complete' && document.body && document.body.innerText.length > 100")
    time.sleep(0.5)
    state = page_state(cdp, kind)
    shot = output_dir / f"{kind}-{width}x{height}-{stamp}.png"
    screenshot(cdp, shot)
    state["screenshot"] = str(shot)
    if kind.startswith("robotics"):
        state["ok"] = (
            state["roboticsSplit"]
            and state["roboticsGenericLoop"]
            and not state["hasHorizontalOverflow"]
            and not state["forbidden"]
            and not state["hasBlankMain"]
        )
    else:
        state["ok"] = (
            state["rehabReadonly"]
            and state["rehabDifferentFromRobotics"]
            and state["hasWorkbenchBackLink"]
            and not state["urlExposesSource"]
            and not state["hasHorizontalOverflow"]
            and not state["forbidden"]
            and not state["hasBlankMain"]
        )
    return state


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report: dict[str, object] = {"project_id": args.project_id, "web_base": web_base, "pages": [], "failures": []}

    token, user_json = cdp_helpers.authenticate(args)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="device-split-cdp-"))
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
        origin = f"{urlparse(web_base).scheme}://{urlparse(web_base).netloc}"
        if token:
            cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
            if user_json:
                cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})

        checks = [
            ("robotics", "robotics-desktop", 1440, 980),
            ("robotics", "robotics-narrow", 390, 920),
            ("rehab-arm-control", "rehab-desktop", 1440, 980),
            ("rehab-arm-control", "rehab-narrow", 390, 920),
        ]
        for path, kind, width, height in checks:
            state = validate_page(cdp, web_base, args.project_id, path, kind, output_dir, stamp, width, height)
            report["pages"].append(state)  # type: ignore[union-attr]
            if not state.get("ok"):
                report["failures"].append(kind)  # type: ignore[union-attr]
        report_path = output_dir / "report.json"
        report["verdict"] = "passed" if not report["failures"] else "failed"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report"] = str(report_path)
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
