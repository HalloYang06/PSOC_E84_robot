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
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)


FORBIDDEN_RE = r"adapter|bridge|session JSONL|local path|source_thread|canonical|requested id|raw UUID|\bJSONL\b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate that a bound NanoPi device can show readonly state sync in robotics workbench.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--device-id", default="nanopi-agent-cloud")
    parser.add_argument("--robot-id", default="medical-arm-agent-cloud")
    parser.add_argument("--computer-node-id", default="")
    parser.add_argument("--runner-id", default="")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/validation/bound-nanopi-robotics-sync")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=980)
    return parser.parse_args()


def js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def request_json(url: str, *, method: str = "GET", payload: dict[str, object] | None = None, token: str = "") -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def text(value: object, fallback: str = "") -> str:
    raw = str(value if value is not None else "").strip()
    return raw or fallback


def as_records(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def pick_computer(api_base: str, project_id: str, token: str, requested_node_id: str, requested_runner_id: str) -> dict[str, str]:
    if requested_node_id:
        return {"computer_node_id": requested_node_id, "runner_id": requested_runner_id}
    payload = request_json(f"{api_base.rstrip('/')}/api/collaboration/projects/{quote(project_id, safe='')}/computer-nodes", token=token)
    nodes = as_records(payload.get("data"))
    if not nodes:
        raise RuntimeError("No project computer nodes available to bind NanoPi device.")
    selected = next((node for node in nodes if text(node.get("runner_id") or node.get("runnerId"))), nodes[0])
    node_id = text(selected.get("id") or selected.get("config_id") or selected.get("configId"))
    if not node_id:
        raise RuntimeError(f"Selected computer node has no public id: {selected}")
    return {
        "computer_node_id": node_id,
        "runner_id": text(selected.get("runner_id") or selected.get("runnerId") or requested_runner_id),
    }


def upload_bound_device_metadata(api_base: str, project_id: str, device_id: str, robot_id: str, computer_node_id: str, runner_id: str) -> dict[str, object]:
    common = {
        "project_id": project_id,
        "device_id": device_id,
        "robot_id": robot_id,
        "computer_node_id": computer_node_id,
        "runner_id": runner_id,
    }
    register = request_json(
        f"{api_base.rstrip('/')}/api/rehab-arm/v1/devices/register",
        method="POST",
        payload={
            **common,
            "device_type": "nanopi",
            "software_version": "validation-readonly-binding",
            "capabilities": ["ros2_readonly", "camera_keyframe", "linux_board_status"],
        },
    )
    board = request_json(
        f"{api_base.rstrip('/')}/api/rehab-arm/v1/devices/{quote(device_id, safe='')}/board-manifest",
        method="POST",
        payload={
            **common,
            "manifest": {
                "schema_version": "linux_board_manifest_v1",
                "device_id": device_id,
                "robot_id": robot_id,
                "computer_node_id": computer_node_id,
                "runner_id": runner_id,
                "hostname": device_id,
                "platform": {"os": "Linux", "role": "NanoPi 只读数据节点"},
                "capabilities": {
                    "can_interfaces": [],
                    "serial_devices": [],
                    "camera_devices": [],
                    "usb_devices": [],
                    "ros2": {"available": True, "topics": ["/joint_states", "/rehab_arm/safety_state"]},
                },
                "control_boundary": "readonly_discovery_only_not_motion_permission",
            },
        },
    )
    return {"register": register, "board_manifest": board}


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
    raise RuntimeError(f"Timed out waiting for {expression[:220]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    output.write_bytes(base64.b64decode(str(shot.get("data") or "")))


def page_state(cdp: object, device_id: str, computer_node_id: str) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          const forbidden = Array.from(new Set(body.match(new RegExp({js(FORBIDDEN_RE)}, 'ig')) || []));
          return {{
            href: location.href,
            title: document.title,
            hasDevice: body.includes({js(device_id)}),
            hasSyncButton: body.includes('开始只读状态同步'),
            noFollowOnlyHint: !body.includes('当前设备只提供服务器最近状态，还没有绑定可执行电脑'),
            hasReadonlyBoundary: body.includes('只读') && body.includes('不发真实运动控制'),
            hasWorkbenchLoop: body.includes('设备数据工作台') && body.includes('数据标注') && body.includes('图表实验'),
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
            forbidden,
            computerNodeId: {js(computer_node_id)},
            bodySample: body.slice(0, 2600),
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
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report: dict[str, object] = {
        "project_id": args.project_id,
        "device_id": args.device_id,
        "pages": [],
        "failures": [],
    }
    token, user_json = cdp_helpers.authenticate(args)
    binding = pick_computer(api_base, args.project_id, token, args.computer_node_id, args.runner_id)
    upload_result = upload_bound_device_metadata(
        api_base,
        args.project_id,
        args.device_id,
        args.robot_id,
        binding["computer_node_id"],
        binding["runner_id"],
    )
    report["binding"] = binding
    report["upload"] = upload_result
    target = (
        f"{web_base}/projects/{quote(args.project_id, safe='')}/robotics"
        f"?tab=model&device={quote(args.device_id, safe='')}"
    )
    report["target"] = target

    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="bound-nanopi-sync-cdp-"))
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
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.viewport_width,
                "height": args.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": args.viewport_width < 700,
            },
        )
        origin = f"{urlparse(web_base).scheme}://{urlparse(web_base).netloc}"
        if token:
            cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
            if user_json:
                cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        cdp.send("Page.navigate", {"url": target})
        wait_for(
            cdp,
            f"""
            (() => {{
              const body = document.body?.innerText || '';
              return location.pathname.endsWith('/robotics')
                && body.includes({js(args.device_id)})
                && body.includes('模型与状态预览')
                && body.includes('开始只读状态同步');
            }})()
            """,
        )
        state = page_state(cdp, args.device_id, binding["computer_node_id"])
        shot = output_dir / f"bound-nanopi-robotics-sync-{args.viewport_width}x{args.viewport_height}-{stamp}.png"
        screenshot(cdp, shot)
        state["screenshot"] = str(shot)
        state["ok"] = (
            state["hasDevice"]
            and state["hasSyncButton"]
            and state["noFollowOnlyHint"]
            and state["hasReadonlyBoundary"]
            and state["hasWorkbenchLoop"]
            and not state["hasHorizontalOverflow"]
            and not state["forbidden"]
        )
        report["pages"].append(state)  # type: ignore[union-attr]
        if not state["ok"]:
            report["failures"].append("bound-nanopi-robotics-sync")  # type: ignore[union-attr]
        report["verdict"] = "passed" if not report["failures"] else "failed"
        report_path = output_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report"] = str(report_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["verdict"] == "passed" else 1
    except Exception as exc:  # noqa: BLE001
        report["verdict"] = "failed"
        report["error"] = str(exc)
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
