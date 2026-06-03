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
    parser.add_argument("--click-sync", action="store_true", help="Click the readonly sync button from the user view.")
    parser.add_argument(
        "--expect-runner-command",
        action="store_true",
        help="After clicking sync, assert a safe robotics.capture.start command reaches the bound runner inbox.",
    )
    parser.add_argument("--click-stop", action="store_true", help="After starting sync, click the stop-and-segment button.")
    parser.add_argument(
        "--expect-stop-command",
        action="store_true",
        help="After clicking stop, assert a safe robotics.capture.stop command reaches the bound runner inbox.",
    )
    parser.add_argument(
        "--verify-segment-tabs",
        action="store_true",
        help="After stop, open dataset and chart tabs and assert the generated segment is visible to users.",
    )
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


def request_runner_json(url: str, runner_id: str) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Runner-Id": runner_id,
        },
        method="GET",
    )
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


def runner_inbox(api_base: str, runner_id: str) -> list[dict[str, object]]:
    if not runner_id:
        return []
    payload = request_runner_json(
        f"{api_base.rstrip('/')}/api/runners/{quote(runner_id, safe='')}/inbox?status=all&limit=100",
        runner_id,
    )
    return as_records(payload.get("data"))


def parse_command_body(item: dict[str, object]) -> dict[str, object]:
    try:
        body = json.loads(text(item.get("body")))
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def find_new_capture_command(
    items: list[dict[str, object]],
    *,
    before_ids: set[str],
    kind: str,
    project_id: str,
    device_id: str,
    computer_node_id: str,
) -> dict[str, object] | None:
    for item in reversed(items):
        item_id = text(item.get("id"))
        if not item_id or item_id in before_ids:
            continue
        if text(item.get("message_type") or item.get("messageType")) != "runner_command":
            continue
        body = parse_command_body(item)
        if text(body.get("kind")) != kind:
            continue
        if text(body.get("project_id")) != project_id:
            continue
        if text(body.get("computer_node_id")) != computer_node_id:
            continue
        interface_id = text(body.get("interface_id"))
        if device_id not in interface_id and interface_id != "ros:/joint_states":
            continue
        if body.get("readonly") is not True:
            continue
        return {"message": item, "body": body}
    return None


def summarize_runner_command(found: dict[str, object]) -> dict[str, object]:
    command_message = found["message"] if isinstance(found.get("message"), dict) else {}
    command_body = found["body"] if isinstance(found.get("body"), dict) else {}
    return {
        "id": command_message.get("id"),
        "runner_id": command_message.get("recipient_id") or command_message.get("recipientId"),
        "status": command_message.get("status"),
        "title": command_message.get("title"),
        "kind": command_body.get("kind"),
        "project_id": command_body.get("project_id"),
        "computer_node_id": command_body.get("computer_node_id"),
        "interface_id": command_body.get("interface_id"),
        "readonly": command_body.get("readonly"),
        "sample_hz": command_body.get("sample_hz"),
        "platform_artifact_path": command_body.get("platform_artifact_path"),
    }


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


def segment_tab_state(cdp: object, tab: str) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          const forbidden = Array.from(new Set(body.match(new RegExp({js(FORBIDDEN_RE)}, 'ig')) || []));
          return {{
            href: location.href,
            tab: {js(tab)},
            hasSegmentTitle: body.includes('采集片段'),
            hasSegmentCount: /\\d+\\s*个采集片段|\\d+\\s*个片段可画图|可进入标注/.test(body),
            hasDownloadAction: body.includes('下载片段'),
            hasChartPreview: body.includes('片段可画图') || body.includes('预览曲线'),
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
            forbidden,
            bodySample: body.slice(0, 2200),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"invalid segment tab state: {state!r}")
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
        inbox_before: list[dict[str, object]] = []
        before_ids: set[str] = set()
        if args.expect_runner_command or args.expect_stop_command:
            if not binding["runner_id"]:
                raise RuntimeError("Cannot verify runner command because the selected computer has no bound runner_id.")
            inbox_before = runner_inbox(api_base, binding["runner_id"])
            before_ids = {text(item.get("id")) for item in inbox_before if text(item.get("id"))}
            report["runner_inbox_before_count"] = len(inbox_before)

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

        if args.click_sync:
            clicked = cdp_eval(
                cdp,
                """
                (() => {
                  const controls = Array.from(document.querySelectorAll('button, input[type="submit"]'));
                  const target = controls.find((node) => {
                    const text = (node.innerText || node.value || '').trim();
                    return text.includes('开始只读状态同步');
                  });
                  if (!target) return false;
                  target.scrollIntoView({ block: 'center', inline: 'center' });
                  target.click();
                  return true;
                })()
                """,
            )
            if not clicked:
                report["failures"].append("click-sync-button-not-found")  # type: ignore[union-attr]
            else:
                wait_for(
                    cdp,
                    """
                    (() => {
                      const body = document.body?.innerText || '';
                      return body.includes('采集请求已排队到目标电脑')
                        || body.includes('已排队到目标电脑')
                        || body.includes('开始只读状态同步');
                    })()
                    """,
                    timeout_seconds=30,
                )
                clicked_state = page_state(cdp, args.device_id, binding["computer_node_id"])
                clicked_shot = output_dir / f"bound-nanopi-robotics-sync-clicked-{args.viewport_width}x{args.viewport_height}-{stamp}.png"
                screenshot(cdp, clicked_shot)
                clicked_state["screenshot"] = str(clicked_shot)
                clicked_state["clickedSync"] = True
                clicked_state["ok"] = (
                    clicked_state["hasDevice"]
                    and clicked_state["hasSyncButton"]
                    and not clicked_state["hasHorizontalOverflow"]
                    and not clicked_state["forbidden"]
                )
                report["pages"].append(clicked_state)  # type: ignore[union-attr]
                if not clicked_state["ok"]:
                    report["failures"].append("bound-nanopi-robotics-sync-after-click")  # type: ignore[union-attr]

        start_command_ids = set(before_ids)
        if args.expect_runner_command:
            found: dict[str, object] | None = None
            deadline = time.time() + 45
            latest_inbox: list[dict[str, object]] = []
            while time.time() < deadline:
                latest_inbox = runner_inbox(api_base, binding["runner_id"])
                found = find_new_capture_command(
                    latest_inbox,
                    before_ids=before_ids,
                    kind="robotics.capture.start",
                    project_id=args.project_id,
                    device_id=args.device_id,
                    computer_node_id=binding["computer_node_id"],
                )
                if found:
                    break
                time.sleep(1)
            report["runner_inbox_after_count"] = len(latest_inbox)
            if not found:
                report["failures"].append("runner-command-not-enqueued")  # type: ignore[union-attr]
            else:
                forbidden_command_kinds = {
                    "can.write",
                    "serial.write",
                    "ros.publish",
                    "ros.service.call",
                    "ros.action.send",
                    "robotics.motion.start",
                    "motor.command",
                }
                command_body = found["body"] if isinstance(found.get("body"), dict) else {}
                report["runner_command"] = summarize_runner_command(found)
                start_command_ids = {text(item.get("id")) for item in latest_inbox if text(item.get("id"))}
                if text(command_body.get("kind")).lower() in forbidden_command_kinds:
                    report["failures"].append("unsafe-runner-command-kind")  # type: ignore[union-attr]

        if args.click_stop:
            clicked_stop = cdp_eval(
                cdp,
                """
                (() => {
                  const controls = Array.from(document.querySelectorAll('button, input[type="submit"]'));
                  const target = controls.find((node) => {
                    const text = (node.innerText || node.value || '').trim();
                    return text.includes('关闭并生成片段') || text.includes('停止并生成片段');
                  });
                  if (!target) return false;
                  target.scrollIntoView({ block: 'center', inline: 'center' });
                  target.click();
                  return true;
                })()
                """,
            )
            if not clicked_stop:
                report["failures"].append("click-stop-button-not-found")  # type: ignore[union-attr]
            else:
                wait_for(
                    cdp,
                    """
                    (() => {
                      const body = document.body?.innerText || '';
                      return body.includes('已生成采集片段')
                        || body.includes('关闭并生成片段')
                        || body.includes('停止并生成片段');
                    })()
                    """,
                    timeout_seconds=30,
                )
                stopped_state = page_state(cdp, args.device_id, binding["computer_node_id"])
                stopped_shot = output_dir / f"bound-nanopi-robotics-sync-stopped-{args.viewport_width}x{args.viewport_height}-{stamp}.png"
                screenshot(cdp, stopped_shot)
                stopped_state["screenshot"] = str(stopped_shot)
                stopped_state["clickedStop"] = True
                stopped_state["hasStopSegmentButton"] = "关闭并生成片段" in str(stopped_state.get("bodySample") or "") or "停止并生成片段" in str(stopped_state.get("bodySample") or "")
                stopped_state["ok"] = (
                    stopped_state["hasDevice"]
                    and not stopped_state["hasHorizontalOverflow"]
                    and not stopped_state["forbidden"]
                )
                report["pages"].append(stopped_state)  # type: ignore[union-attr]
                if not stopped_state["ok"]:
                    report["failures"].append("bound-nanopi-robotics-sync-after-stop")  # type: ignore[union-attr]

        if args.expect_stop_command:
            found_stop: dict[str, object] | None = None
            deadline = time.time() + 45
            latest_stop_inbox: list[dict[str, object]] = []
            while time.time() < deadline:
                latest_stop_inbox = runner_inbox(api_base, binding["runner_id"])
                found_stop = find_new_capture_command(
                    latest_stop_inbox,
                    before_ids=start_command_ids,
                    kind="robotics.capture.stop",
                    project_id=args.project_id,
                    device_id=args.device_id,
                    computer_node_id=binding["computer_node_id"],
                )
                if found_stop:
                    break
                time.sleep(1)
            report["runner_inbox_after_stop_count"] = len(latest_stop_inbox)
            if not found_stop:
                report["failures"].append("runner-stop-command-not-enqueued")  # type: ignore[union-attr]
            else:
                stop_body = found_stop["body"] if isinstance(found_stop.get("body"), dict) else {}
                report["runner_stop_command"] = summarize_runner_command(found_stop)
                if text(stop_body.get("kind")).lower() != "robotics.capture.stop" or stop_body.get("readonly") is not True:
                    report["failures"].append("unsafe-runner-stop-command")  # type: ignore[union-attr]
                if not text(stop_body.get("platform_artifact_path")):
                    report["failures"].append("stop-command-missing-artifact-path")  # type: ignore[union-attr]

        if args.verify_segment_tabs:
            for tab in ("dataset", "chart"):
                tab_target = (
                    f"{web_base}/projects/{quote(args.project_id, safe='')}/robotics"
                    f"?tab={quote(tab, safe='')}&device={quote(args.device_id, safe='')}"
                )
                cdp.send("Page.navigate", {"url": tab_target})
                wait_for(
                    cdp,
                    f"""
                    (() => {{
                      const body = document.body?.innerText || '';
                      return location.pathname.endsWith('/robotics')
                        && location.search.includes('tab={tab}')
                        && body.includes({js(args.device_id)})
                        && body.includes('采集片段');
                    }})()
                    """,
                    timeout_seconds=45,
                )
                tab_state = segment_tab_state(cdp, tab)
                tab_shot = output_dir / f"bound-nanopi-robotics-sync-{tab}-{args.viewport_width}x{args.viewport_height}-{stamp}.png"
                screenshot(cdp, tab_shot)
                tab_state["screenshot"] = str(tab_shot)
                tab_state["ok"] = (
                    tab_state["hasSegmentTitle"]
                    and tab_state["hasSegmentCount"]
                    and (tab != "dataset" or tab_state["hasDownloadAction"])
                    and (tab != "chart" or tab_state["hasChartPreview"])
                    and not tab_state["hasHorizontalOverflow"]
                    and not tab_state["forbidden"]
                )
                report["pages"].append(tab_state)  # type: ignore[union-attr]
                if not tab_state["ok"]:
                    report["failures"].append(f"segment-{tab}-tab-not-ready")  # type: ignore[union-attr]
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
