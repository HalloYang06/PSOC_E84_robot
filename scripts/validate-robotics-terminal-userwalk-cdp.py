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


def cleanup_test_window(api_base: str, project_id: str, token: str, window_name: str = "验收串口窗口") -> None:
    if not api_base or not token:
        return
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    project_url = f"{api_base.rstrip('/')}/api/projects/{quote(project_id, safe='')}"
    request = Request(project_url, headers=headers, method="GET")
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    project = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(project, dict):
        return
    config = project.get("collaboration_config")
    if not isinstance(config, dict):
        return
    windows = config.get("robotics_debug_windows")
    if not isinstance(windows, list):
        return
    next_windows = [item for item in windows if not (isinstance(item, dict) and str(item.get("name") or "").strip() == window_name)]
    if len(next_windows) == len(windows):
        return
    next_config = {**config, "robotics_debug_windows": next_windows}
    body = json.dumps({"collaboration_config": next_config}, ensure_ascii=False).encode("utf-8")
    patch_request = Request(
        project_url,
        data=body,
        headers={**headers, "Content-Type": "application/json"},
        method="PATCH",
    )
    with urlopen(patch_request, timeout=20):
        pass


def fetch_robotics_debug_windows(api_base: str, project_id: str, token: str) -> list[dict[str, object]]:
    if not api_base or not token:
        return []
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    project_url = f"{api_base.rstrip('/')}/api/projects/{quote(project_id, safe='')}"
    request = Request(project_url, headers=headers, method="GET")
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    project = payload.get("data") if isinstance(payload, dict) else {}
    config = project.get("collaboration_config") if isinstance(project, dict) else {}
    windows = config.get("robotics_debug_windows") if isinstance(config, dict) else []
    return [item for item in windows if isinstance(item, dict)] if isinstance(windows, list) else []


def wait_for_test_window_saved(api_base: str, project_id: str, token: str, window_name: str = "验收串口窗口", timeout_seconds: float = 20) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if any(str(item.get("name") or "").strip() == window_name for item in fetch_robotics_debug_windows(api_base, project_id, token)):
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def wait_for_test_window_field(
    api_base: str,
    project_id: str,
    token: str,
    field_name: str,
    expected_value: str,
    window_name: str = "验收串口窗口",
    timeout_seconds: float = 20,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            for item in fetch_robotics_debug_windows(api_base, project_id, token):
                if str(item.get("name") or "").strip() != window_name:
                    continue
                if str(item.get(field_name) or "").strip() == expected_value:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


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
    cleanup_test_window(args.api_base, args.project_id, token)
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
        wait_for(
            cdp,
            "document.readyState === 'complete' && (document.body.innerText.includes('设备数据工作台') || document.body.innerText.includes('创建调试窗口') || document.body.innerText.includes('机器人现场'))",
        )
        wait_for(
            cdp,
            "document.readyState === 'complete' && document.body.innerText.includes('创建调试窗口') && document.body.innerText.includes('绑定真实设备')",
        )
        first = cdp_eval(
            cdp,
            """
            (() => {
              const body = document.body.innerText || '';
              const resourceOptions = Array.from(document.querySelectorAll('select[name="resource_id"] option')).filter((item) => item.value);
              const leftWindowNames = Array.from(document.querySelectorAll('ul[class*="npcList"] strong')).map((item) => item.innerText || '');
              return {
                href: location.href,
                hasCreateWindowForm: body.includes('创建调试窗口') && !!document.querySelector('input[name="window_name"]'),
                hasWindowType: body.includes('窗口类型') && !!document.querySelector('select[name="window_type"]'),
                hasResourceSelect: body.includes('绑定真实设备') && !!document.querySelector('select[name="resource_id"]'),
                resourceOptions: resourceOptions.length,
                hasBaudSelect: body.includes('波特率') && Array.from(document.querySelectorAll('select[name="baud_rate"] option')).some((item) => item.value === '115200'),
                hasSampleHz: body.includes('采样频率') && !!document.querySelector('input[name="sample_hz"]'),
                hasChannels: body.includes('采集通道') && !!document.querySelector('input[name="channels"]'),
                hasNpcSelect: body.includes('协助 NPC') && !!document.querySelector('select[name="bound_npc"]'),
                leftWindowCountText: body.includes('0 个窗口'),
                leftWindowNames,
                openButtons: document.querySelectorAll('a[aria-label^="打开 "]').length,
                createButtonText: Array.from(document.querySelectorAll('button')).find((button) => (button.innerText || '').includes('创建并打开'))?.innerText || '',
                hasCreateTitle: body.includes('创建调试窗口') && body.includes('先创建一个调试窗口'),
                hasComputerJumpButton: Array.from(document.querySelectorAll('a')).some((a) => (a.innerText || '').includes('接入/检查电脑')),
                directlyListsScannedResources: leftWindowNames.length > 3,
                hasNoDemoText: body.includes('先创建调试窗口') && !body.includes('模板'),
                hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
              };
            })()
            """,
        )
        report["initial"] = first
        screenshot(cdp, output_dir / f"robotics-terminal-userwalk-initial-{stamp}.png")

        has_create_flow = isinstance(first, dict) and first.get("hasCreateWindowForm") and int(first.get("resourceOptions") or 0) > 0
        if has_create_flow:
            if first.get("hasComputerJumpButton"):
                report["failures"].append("robotics page still has computer jump button")  # type: ignore[union-attr]
            if not first.get("hasWindowType") or not first.get("hasResourceSelect") or not first.get("hasBaudSelect") or not first.get("hasSampleHz") or not first.get("hasChannels") or not first.get("hasNpcSelect"):
                report["failures"].append("debug window creation does not expose labeled resource and parameter controls")  # type: ignore[union-attr]
            if first.get("directlyListsScannedResources"):
                report["failures"].append("left rail still directly lists scanned resources instead of created windows")  # type: ignore[union-attr]
            created = cdp_eval(
                cdp,
                """
                (() => {
                  const setValue = (selector, value) => {
                    const el = document.querySelector(selector);
                    if (!el) return false;
                    el.value = value;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                  };
                  setValue('input[name="window_name"]', '验收串口窗口');
                  setValue('select[name="window_type"]', 'serial');
                  setValue('select[name="baud_rate"]', '115200');
                  setValue('input[name="sample_hz"]', '100');
                  setValue('input[name="channels"]', 'time,motor.current,motor.velocity');
                  const npcSelect = document.querySelector('select[name="bound_npc"]');
                  if (npcSelect && npcSelect.options.length > 1) {
                    npcSelect.selectedIndex = 1;
                    npcSelect.dispatchEvent(new Event('change', { bubbles: true }));
                  }
                  const button = Array.from(document.querySelectorAll('button')).find((item) => (item.innerText || '').includes('创建并打开'));
                  if (!button) return false;
                  button.click();
                  return true;
                })()
                """,
            )
            if not created:
                report["failures"].append("failed to create debug window from form")  # type: ignore[union-attr]
            wait_for(cdp, "document.body.innerText.includes('模式=用户终端') && document.querySelectorAll('article').length > 0")
            time.sleep(0.5)
            saved_by_api = wait_for_test_window_saved(args.api_base, args.project_id, token)
            report["savedByApiBeforeReload"] = saved_by_api
            if not saved_by_api:
                report["failures"].append("created debug window was not saved before reload")  # type: ignore[union-attr]
            persisted = cdp_eval(
                cdp,
                """
                (() => {
                  const before = (document.body.innerText || '').includes('验收串口窗口');
                  location.reload();
                  return before;
                })()
                """,
            )
            if not persisted:
                report["failures"].append("created debug window did not appear before reload")  # type: ignore[union-attr]
            wait_for(cdp, "document.readyState === 'complete' && document.body.innerText.includes('验收串口窗口') && document.body.innerText.includes('模式=用户终端')")
            report["persistence"] = cdp_eval(
                cdp,
                """
                (() => {
                  const body = document.body.innerText || '';
                  return {
                    hasCreatedWindowAfterReload: body.includes('验收串口窗口'),
                    hasOpenTileAfterReload: body.includes('模式=用户终端') && body.includes('$ open 验收串口窗口'),
                    stillOnRobotics: location.pathname.endsWith('/robotics'),
                  };
                })()
                """,
            )
            if not isinstance(report.get("persistence"), dict) or not report["persistence"].get("hasCreatedWindowAfterReload"):
                report["failures"].append("created debug window was not persisted in project state")  # type: ignore[union-attr]
            tile = cdp_eval(
                cdp,
                """
                (() => {
                  const body = document.body.innerText || '';
                  const form = document.querySelector('form[class*="terminalCommandBar"]');
                  const internalMatches = Array.from(new Set(body.match(/adapter|bridge|session JSONL|local path|source_thread|canonical|requested id|raw UUID|\\brunner\\b/ig) || []));
                  return {
                    href: location.href,
                    tileCount: document.querySelectorAll('article').length,
                    hasTerminal: body.includes('$ open') && body.includes('模式=用户终端'),
                    hasTerminalIo: body.includes('--- I/O ---') && (body.includes('[terminal]') || body.includes('[ack]') || body.includes('[result') || body.includes('# queued')),
                    hasNpcSelect: !!document.querySelector('select[name="bound_npc"]'),
                    hasCommandInput: !!document.querySelector('input[name="command"]'),
                    hasCaptureControls: !!document.querySelector('form[class*="captureBar"] input[name="sample_hz"]')
                      && !!document.querySelector('form[class*="captureBar"] input[name="channels"]')
                      && Array.from(document.querySelectorAll('form[class*="captureBar"] button')).some((button) => (button.innerText || '').includes('开始采集'))
                      && Array.from(document.querySelectorAll('form[class*="captureBar"] button')).some((button) => (button.innerText || '').includes('停止')),
                    submitDisabled: !!form?.querySelector('button[type="submit"]')?.disabled,
                    hasTileSettingsLink: Array.from(document.querySelectorAll('button')).some((button) => (button.innerText || '').trim() === '设置'),
                    hasJumpSelectNpc: Array.from(document.querySelectorAll('a')).some((a) => (a.innerText || '').includes('选择 NPC')),
                    hasInternalTerms: internalMatches.length > 0,
                    internalMatches,
                    hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
                  };
                })()
                """,
            )
            report["tile"] = tile
            screenshot(cdp, output_dir / f"robotics-terminal-userwalk-tile-{stamp}.png")
            if not isinstance(tile, dict) or not tile.get("hasTerminal") or not tile.get("hasTerminalIo") or not tile.get("hasNpcSelect") or not tile.get("hasCommandInput") or not tile.get("hasCaptureControls"):
                report["failures"].append("terminal tile controls missing")  # type: ignore[union-attr]
            if isinstance(tile, dict) and tile.get("hasJumpSelectNpc"):
                report["failures"].append("NPC binding still jumps away")  # type: ignore[union-attr]
            if isinstance(tile, dict) and tile.get("hasInternalTerms"):
                report["failures"].append(f"robotics tile exposes internal terms: {tile.get('internalMatches')}")  # type: ignore[union-attr]
            cdp.send(
                "Runtime.evaluate",
                {
                    "expression": "(() => { const btn = Array.from(document.querySelectorAll('button')).find((button) => (button.innerText || '').includes('数据标注')); if (!btn) return false; btn.click(); return true; })()",
                    "returnByValue": True,
                    "userGesture": True,
                },
            )
            wait_for(cdp, "document.body.innerText.includes('采集片段') && document.body.innerText.includes('变量选择') && document.body.innerText.includes('NPC 预标注') && document.body.innerText.includes('导出标注数据')")
            dataset_state = cdp_eval(
                cdp,
                """
                (() => {
                  const body = document.body.innerText || '';
                  return {
                    hasDatasetTab: body.includes('采集片段') && body.includes('变量选择') && body.includes('NPC 预标注') && body.includes('导出标注数据'),
                    hasCaptureChecks: document.querySelectorAll('input[name="capture_ids"][type="checkbox"]').length > 0 || body.includes('从这个调试窗口开始/停止采集后'),
                    hasVariableChecks: document.querySelectorAll('input[name="variables"][type="checkbox"]').length > 0,
                    hasLabelSchema: !!document.querySelector('input[name="label_schema"]'),
                    hasManualLabels: !!document.querySelector('textarea[name="manual_labels"]') && body.includes('人工标签'),
                    hasExportFormat: !!document.querySelector('select[name="export_format"]'),
                    hasPreLabelButton: Array.from(document.querySelectorAll('button')).some((button) => (button.innerText || '').includes('NPC 预标注')),
                    hasExportButton: Array.from(document.querySelectorAll('button')).some((button) => (button.innerText || '').includes('导出标注数据')),
                    hasRunnerResultSlot: body.includes('采集回执') || body.includes('已回传') || body.includes('等待预标注或导出'),
                    stillOnRobotics: location.pathname.endsWith('/robotics'),
                    hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
                  };
                })()
                """,
            )
            report["dataset"] = dataset_state
            screenshot(cdp, output_dir / f"robotics-terminal-userwalk-dataset-{stamp}.png")
            if (
                not isinstance(dataset_state, dict)
                or not dataset_state.get("hasDatasetTab")
                or not dataset_state.get("hasVariableChecks")
                or not dataset_state.get("hasLabelSchema")
                or not dataset_state.get("hasManualLabels")
                or not dataset_state.get("hasExportFormat")
                or not dataset_state.get("hasPreLabelButton")
                or not dataset_state.get("hasExportButton")
                or not dataset_state.get("hasRunnerResultSlot")
                or not dataset_state.get("stillOnRobotics")
            ):
                report["failures"].append("dataset tab controls missing or did not stay in tile")  # type: ignore[union-attr]
            cdp.send(
                "Runtime.evaluate",
                {
                    "expression": "(() => { const btn = Array.from(document.querySelectorAll('button')).find((button) => (button.innerText || '').includes('图表实验')); if (!btn) return false; btn.click(); return true; })()",
                    "returnByValue": True,
                    "userGesture": True,
                },
            )
            wait_for(cdp, "document.body.innerText.includes('横轴') && document.body.innerText.includes('纵轴') && document.body.innerText.includes('保存图表快照') && document.body.innerText.includes('请求 NPC 调参建议')")
            chart_state = cdp_eval(
                cdp,
                """
                (() => {
                  const body = document.body.innerText || '';
                  return {
                    hasChartTab: body.includes('横轴') && body.includes('纵轴') && body.includes('保存图表快照') && body.includes('请求 NPC 调参建议'),
                    hasXAxis: !!document.querySelector('select[name="x_axis"]'),
                    hasYAxis: document.querySelectorAll('input[name="y_axes"][type="checkbox"]').length > 0,
                    hasTarget: !!document.querySelector('input[name="target_value"]'),
                    hasMode: !!document.querySelector('select[name="chart_mode"]') && document.body.innerText.includes('PID') && document.body.innerText.includes('FOC'),
                    hasChartButton: Array.from(document.querySelectorAll('button')).some((button) => (button.innerText || '').includes('保存图表快照')),
                    hasTuningButton: Array.from(document.querySelectorAll('button')).some((button) => (button.innerText || '').includes('请求 NPC 调参建议')),
                    hasRunnerEvidenceSlot: body.includes('图表证据') && (body.includes('等待图表快照') || body.includes('已回传') || body.includes('采集回执')),
                    hasSummarySlot: body.includes('图表证据') && (body.includes('均值') || body.includes('已收到') || body.includes('等待图表快照')),
                    stillOnRobotics: location.pathname.endsWith('/robotics'),
                    hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
                  };
                })()
                """,
            )
            report["chart"] = chart_state
            screenshot(cdp, output_dir / f"robotics-terminal-userwalk-chart-{stamp}.png")
            if (
                not isinstance(chart_state, dict)
                or not chart_state.get("hasChartTab")
                or not chart_state.get("hasXAxis")
                or not chart_state.get("hasYAxis")
                or not chart_state.get("hasTarget")
                or not chart_state.get("hasMode")
                or not chart_state.get("hasChartButton")
                or not chart_state.get("hasTuningButton")
                or not chart_state.get("hasRunnerEvidenceSlot")
                or not chart_state.get("hasSummarySlot")
                or not chart_state.get("stillOnRobotics")
            ):
                report["failures"].append("chart tab controls missing or did not stay in tile")  # type: ignore[union-attr]
            cdp.send(
                "Runtime.evaluate",
                {
                    "expression": "(() => { const btn = Array.from(document.querySelectorAll('button')).find((button) => (button.innerText || '').trim() === '设置'); if (!btn) return false; btn.click(); return true; })()",
                    "returnByValue": True,
                    "userGesture": True,
                },
            )
            wait_for(cdp, "document.body.innerText.includes('窗口设置')")
            settings_state = cdp_eval(
                cdp,
                """
                (() => {
                  const body = document.body.innerText || '';
                  return {
                    href: location.href,
                    hasSettingsPanel: body.includes('窗口设置') && body.includes('执行电脑') && body.includes('调试接口') && body.includes('协助 NPC'),
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
            cdp_eval(
                cdp,
                """
                (() => {
                  const sample = document.querySelector('form[class*="settingsPanel"] input[name="sample_hz"]');
                  if (!sample) return false;
                  sample.value = '125';
                  sample.dispatchEvent(new Event('input', { bubbles: true }));
                  sample.dispatchEvent(new Event('change', { bubbles: true }));
                  const button = Array.from(document.querySelectorAll('form[class*="settingsPanel"] button'))
                    .find((item) => (item.innerText || '').includes('保存设置'));
                  if (!button) return false;
                  button.click();
                  return true;
                })()
                """,
            )
            settings_saved = wait_for_test_window_field(args.api_base, args.project_id, token, "sampleHz", "125")
            report["settingsPersisted"] = settings_saved
            if not settings_saved:
                report["failures"].append("settings changes were not persisted in project state")  # type: ignore[union-attr]
            cdp_eval(
                cdp,
                """
                (() => {
                  const button = Array.from(document.querySelectorAll('button[aria-label^="删除 "]'))
                    .find((item) => (item.getAttribute('aria-label') || '').includes('验收串口窗口'));
                  if (!button) return false;
                  button.click();
                  return true;
                })()
                """,
            )
            try:
                wait_for(cdp, "!document.body.innerText.includes('验收串口窗口') || document.body.innerText.includes('调试窗口已删除')", timeout_seconds=8)
            except TimeoutError:
                report["failures"].append("cleanup failed: test debug window remained after delete")  # type: ignore[union-attr]
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
