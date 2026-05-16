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


MODES = {
    "can": {
        "label": "CAN 调试",
        "required": ["CAN 调试", "0x180", "M1.status", "按频率采样"],
        "forbidden": ["ttyUSB0", "USB-CAN", "/joint_states"],
    },
    "serial": {
        "label": "串口调试",
        "required": ["串口调试", "ttyUSB0", "PSoC M33", "生成采样草案"],
        "forbidden": ["0x180", "USB-CAN", "/joint_states"],
    },
    "usb": {
        "label": "USB 调试",
        "required": ["USB 调试", "USB-CAN", "DAP-Link", "生成采样草案"],
        "forbidden": ["0x180", "ttyUSB0", "/joint_states"],
    },
    "ros": {
        "label": "ROS 只读桥",
        "required": ["ROS 只读桥", "/joint_states", "/tf", "生成采样草案"],
        "forbidden": ["0x180", "ttyUSB0", "DAP-Link"],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate robotics CAN/serial/USB/ROS debug mode switching.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="proj_ai_collab")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/robotics-debug-modes")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=1000)
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


def validate_mode(cdp: object, web_base: str, project_id: str, mode: str, output_dir: Path, stamp: str) -> dict[str, object]:
    expected = MODES[mode]
    target = f"{web_base}/projects/{quote(project_id, safe='')}/robotics?debug={quote(mode, safe='')}"
    cdp.send("Page.navigate", {"url": target})
    wait_for(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          return document.readyState === 'complete'
            && location.pathname.endsWith('/robotics')
            && new URLSearchParams(location.search).get('debug') === {js(mode)}
            && body.includes('机器人现场')
            && body.includes('设备调试工程师')
            && body.includes({js(expected["label"])});
        }})()
        """,
        timeout_seconds=45,
    )
    time.sleep(0.4)
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const main = document.querySelector('[data-mode="{mode}"]');
          const mainText = main?.innerText || '';
          const body = document.body?.innerText || '';
          const activeTop = Array.from(document.querySelectorAll('[role="tablist"] a[data-active="1"]'))
            .map((item) => (item.innerText || '').replace(/\\s+/g, ' ').trim());
          const activeRight = Array.from(document.querySelectorAll('a[data-active="1"]'))
            .map((item) => (item.innerText || '').replace(/\\s+/g, ' ').trim());
          const required = {js(expected["required"])};
          const forbidden = {js(expected["forbidden"])};
          return {{
            href: location.href,
            title: document.title,
            mode: main?.getAttribute('data-mode') || '',
            mainText: mainText.slice(0, 1800),
            requiredMissing: required.filter((label) => !mainText.includes(label)),
            forbiddenPresent: forbidden.filter((label) => mainText.includes(label)),
            activeTop,
            activeRight,
            panelCount: main ? main.querySelectorAll('section').length : 0,
            hasComputerCapabilityMatrix: body.includes('执行电脑能力矩阵') && body.includes('CAN') && body.includes('串口') && body.includes('ROS'),
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
            bodyHasInternalTerms: /adapter|bridge|session JSONL|local path|source_thread|canonical|requested id|raw UUID/.test(body),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Mode {mode} returned invalid browser state: {state!r}")
    output = output_dir / f"robotics-debug-{mode}-{stamp}.png"
    screenshot(cdp, output)
    state["screenshot"] = str(output)
    state["ok"] = (
        state.get("mode") == mode
        and state.get("panelCount") == 1
        and not state.get("requiredMissing")
        and not state.get("forbiddenPresent")
        and state.get("hasComputerCapabilityMatrix")
        and not state.get("hasHorizontalOverflow")
        and not state.get("bodyHasInternalTerms")
        and any(str(expected["label"]) in str(label) for label in state.get("activeTop", []))
    )
    return state


def validate_dataset_intake(cdp: object, mode: str, output_dir: Path, stamp: str) -> dict[str, object]:
    expected = MODES[mode]
    click_state = cdp_eval(
        cdp,
        """
        (() => {
          const links = Array.from(document.querySelectorAll('a'));
          const el = links.find((item) => {
            const text = (item.innerText || item.textContent || '').replace(/\s+/g, ' ').trim();
            return text.includes('按频率采样') || text.includes('生成采样草案');
          });
          if (!el) return { ok: false, reason: 'missing sampling link' };
          el.scrollIntoView({ block: 'center', inline: 'center' });
          const rect = el.getBoundingClientRect();
          return { ok: true, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, text: el.innerText || '' };
        })()
        """,
    )
    if not isinstance(click_state, dict) or not click_state.get("ok"):
        raise RuntimeError(f"Mode {mode} sampling link missing: {click_state}")
    x = float(click_state["x"])
    y = float(click_state["y"])
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    wait_for(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          return document.readyState === 'complete'
            && location.pathname.endsWith('/datasets')
            && new URLSearchParams(location.search).get('intake') === 'device'
            && new URLSearchParams(location.search).get('device_mode') === {js(mode)}
            && body.includes('设备采样任务草案')
            && body.includes({js(expected["label"])});
        }})()
        """,
        timeout_seconds=45,
    )
    time.sleep(0.3)
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          return {{
            href: location.href,
            hasDraft: body.includes('设备采样任务草案'),
            hasModeLabel: body.includes({js(expected["label"])}),
            hasHumanBoundary: body.includes('需要人确认') || body.includes('人确认'),
            hasQueueDraft: body.includes(`${{new URLSearchParams(location.search).get('device_mode') || 'device'}}-intake-draft`),
            hasSamplingTask: body.includes('设备采样草案') && body.includes('采集任务'),
            hasChannelQueue: body.includes('通道队列') && body.includes('逐项确认是否采样'),
            hasSamplingControls: body.includes('采样控制') && body.includes('人工确认采样'),
            hasRunnerState: body.includes('执行电脑能力待确认') || body.includes('台执行电脑在线'),
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
            bodyHasInternalTerms: /adapter|bridge|session JSONL|local path|source_thread|canonical|requested id|raw UUID/.test(body),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Mode {mode} dataset state invalid: {state!r}")
    output = output_dir / f"robotics-debug-datasets-{mode}-{stamp}.png"
    screenshot(cdp, output)
    state["screenshot"] = str(output)
    state["ok"] = (
        state.get("hasDraft")
        and state.get("hasModeLabel")
        and state.get("hasHumanBoundary")
        and state.get("hasQueueDraft")
        and state.get("hasSamplingTask")
        and state.get("hasChannelQueue")
        and state.get("hasSamplingControls")
        and state.get("hasRunnerState")
        and not state.get("hasHorizontalOverflow")
        and not state.get("bodyHasInternalTerms")
    )
    return state


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    token, user_json = cdp_helpers.authenticate(args)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="robotics-debug-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    report: dict[str, object] = {
        "project_id": args.project_id,
        "web_base": web_base,
        "modes": {},
        "failures": [],
    }

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
                "mobile": False,
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

        for mode in MODES:
            state = validate_mode(cdp, web_base, args.project_id, mode, output_dir, stamp)
            report["modes"][mode] = state  # type: ignore[index]
            if not state.get("ok"):
                report["failures"].append(mode)  # type: ignore[union-attr]
            dataset_state = validate_dataset_intake(cdp, mode, output_dir, stamp)
            report.setdefault("dataset_intake", {})[mode] = dataset_state  # type: ignore[index]
            if not dataset_state.get("ok"):
                report["failures"].append(f"datasets:{mode}")  # type: ignore[union-attr]

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
