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
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)

FORBIDDEN_RE = r"adapter|bridge|session JSONL|local path|source_thread|canonical|requested id|raw UUID|\bJSONL\b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate robotics device deep link from rehab-arm control page.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="proj_ai_collab")
    parser.add_argument("--device-id", default="nanopi-agent-cloud")
    parser.add_argument("--tab", default="data")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/validation/robotics-device-deeplink")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=980)
    return parser.parse_args()


def js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


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


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 45, interval_seconds: float = 0.25) -> object:
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
    raise RuntimeError(f"Timed out waiting for expression: {expression[:240]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def page_state(cdp: object, device_id: str) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          const params = new URLSearchParams(location.search);
          const forbidden = Array.from(new Set(body.match(new RegExp({js(FORBIDDEN_RE)}, 'ig')) || []));
          const activeTabs = Array.from(document.querySelectorAll('button[data-active="1"]'))
            .map((item) => (item.innerText || '').replace(/\\s+/g, ' ').trim());
          return {{
            href: location.href,
            title: document.title,
            queryDevice: params.get('device') || '',
            queryTab: params.get('tab') || '',
            hasDeeplinkNotice: body.includes('已从专项总控台打开') && body.includes('先确认只读状态'),
            hasDeviceTile: body.includes({js(device_id)}) && body.includes('开发板数据'),
            hasDataWorkbench: body.includes('通用设备数据工作台') && body.includes('终端') && body.includes('数据标注') && body.includes('图表实验'),
            hasReadonlyBoundary: body.includes('只读') && body.includes('不发真实运动控制'),
            activeTabs,
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
            forbidden,
            bodySample: body.slice(0, 2200),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"invalid page state: {state!r}")
    return state


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = (
        f"{web_base}/projects/{quote(args.project_id, safe='')}/robotics"
        f"?tab={quote(args.tab, safe='')}&device={quote(args.device_id, safe='')}"
    )

    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="robotics-device-deeplink-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    report: dict[str, object] = {
        "project_id": args.project_id,
        "device_id": args.device_id,
        "target": target,
        "pages": [],
        "failures": [],
    }

    try:
        try:
            token, user_json = cdp_helpers.authenticate(args)
        except Exception as auth_exc:  # noqa: BLE001
            report["verdict"] = "auth_blocked"
            report["error"] = f"Authentication failed before opening robotics page: {auth_exc}"
            report_path = output_dir / "report.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["report"] = str(report_path)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1

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
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")), None)
        if not isinstance(page_target, dict):
            raise RuntimeError("No page target available")

        cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
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
                "mobile": args.viewport_width < 600,
            },
        )
        origin = f"{urlparse(web_base).scheme}://{urlparse(web_base).netloc}"
        if token:
            result = cdp.send(
                "Network.setCookie",
                {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
            )
            if not result.get("success"):
                raise RuntimeError("Failed to set farm_access_token")
            if user_json:
                cdp.send(
                    "Network.setCookie",
                    {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
                )

        cdp.send("Page.navigate", {"url": target})
        wait_for(
            cdp,
            f"""
            (() => {{
              const body = document.body?.innerText || '';
              return document.readyState === 'complete'
                && location.pathname.endsWith('/robotics')
                && body.includes('通用设备数据工作台')
                && body.includes('已从专项总控台打开')
                && body.includes({js(args.device_id)});
            }})()
            """,
        )
        time.sleep(0.4)
        state = page_state(cdp, args.device_id)
        output = output_dir / f"robotics-device-deeplink-{args.viewport_width}x{args.viewport_height}-{stamp}.png"
        screenshot(cdp, output)
        state["screenshot"] = str(output)
        state["ok"] = (
            state["queryDevice"] == args.device_id
            and state["queryTab"] == args.tab
            and state["hasDeeplinkNotice"]
            and state["hasDeviceTile"]
            and state["hasDataWorkbench"]
            and state["hasReadonlyBoundary"]
            and not state["hasHorizontalOverflow"]
            and not state["forbidden"]
        )
        report["pages"].append(state)  # type: ignore[union-attr]
        if not state["ok"]:
            report["failures"].append("robotics-device-deeplink")  # type: ignore[union-attr]
        report["verdict"] = "passed" if not report["failures"] else "failed"
        report_path = output_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report"] = str(report_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["verdict"] == "passed" else 1
    except Exception as exc:  # noqa: BLE001
        report["verdict"] = "failed"
        report["error"] = str(exc)
        if cdp:
            try:
                state = page_state(cdp, args.device_id)
                output = output_dir / f"robotics-device-deeplink-failed-{stamp}.png"
                screenshot(cdp, output)
                state["screenshot"] = str(output)
                report["pages"].append(state)  # type: ignore[union-attr]
            except Exception as state_exc:  # noqa: BLE001
                report["state_error"] = str(state_exc)
        report_path = output_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report"] = str(report_path)
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
