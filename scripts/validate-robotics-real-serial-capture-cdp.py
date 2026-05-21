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
    parser = argparse.ArgumentParser(description="Cloud user-view serial capture validation for robotics workbench.")
    parser.add_argument("--web-base", required=True)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/robotics-real-serial-capture")
    parser.add_argument("--resource-text", default="COM30")
    parser.add_argument("--computer-text", default="wjy-windows")
    parser.add_argument("--npc-text", default="你是5号")
    parser.add_argument("--viewport-width", type=int, default=1880)
    parser.add_argument("--viewport-height", type=int, default=920)
    return parser.parse_args()


def js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def cdp_eval(cdp: object, expression: str) -> object:
    result = cdp.send("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True, "userGesture": True})
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
        time.sleep(0.3)
    raise RuntimeError(f"Timed out waiting for {expression[:220]} last={last}")


def screenshot(cdp: object, path: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    path.write_bytes(base64.b64decode(str(shot.get("data") or "")))


def fetch_url(url: str, token: str) -> tuple[int, bytes]:
    headers = {"Accept": "*/*"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=30) as response:
        return response.status, response.read()


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    window_name = f"Windows虚拟串口采集验收-{stamp}"
    report: dict[str, object] = {"project_id": args.project_id, "window_name": window_name, "steps": [], "failures": []}

    token, user_json = cdp_helpers.authenticate(args)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="robotics-real-serial-"))
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
        cdp.sock.settimeout(90)
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
        wait_for(cdp, "document.readyState === 'complete' && document.body.innerText.includes('创建调试窗口') && document.body.innerText.includes('绑定真实设备')")
        screenshot(cdp, output_dir / f"real-serial-initial-{stamp}.png")

        created = cdp_eval(
            cdp,
            f"""
            (() => {{
              const setValue = (selector, value) => {{
                const el = document.querySelector(selector);
                if (!el) return false;
                el.value = value;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
              }};
              const resource = Array.from(document.querySelectorAll('select[name="resource_id"] option'))
                .find((option) => (option.innerText || '').includes({js(args.resource_text)}) && (option.innerText || '').includes({js(args.computer_text)}));
              if (!resource) return {{ ok: false, reason: 'resource_missing', options: Array.from(document.querySelectorAll('select[name="resource_id"] option')).map((o) => o.innerText).slice(-20) }};
              setValue('input[name="window_name"]', {js(window_name)});
              setValue('select[name="window_type"]', 'serial');
              setValue('select[name="resource_id"]', resource.value);
              setValue('select[name="baud_rate"]', '115200');
              setValue('input[name="sample_hz"]', '50');
              setValue('input[name="channels"]', 'time,sample.0,sample.1,sample.2,state');
              const npcSelect = document.querySelector('select[name="bound_npc"]');
              if (npcSelect) {{
                const npc = Array.from(npcSelect.options).find((option) => (option.innerText || '').includes({js(args.npc_text)}));
                if (npc) {{
                  npcSelect.value = npc.value;
                  npcSelect.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
              }}
              const button = Array.from(document.querySelectorAll('button')).find((item) => (item.innerText || '').includes('创建并打开'));
              if (!button) return {{ ok: false, reason: 'button_missing' }};
              button.click();
              return {{ ok: true, resource: resource.innerText }};
            }})()
            """,
        )
        report["create"] = created
        if not isinstance(created, dict) or not created.get("ok"):
            report["failures"].append("create debug window failed")
            raise RuntimeError(f"create failed: {created}")
        wait_for(cdp, f"document.readyState === 'complete' && document.body.innerText.includes({js(window_name)}) && document.body.innerText.includes('开始采集')", timeout_seconds=30)
        screenshot(cdp, output_dir / f"real-serial-created-{stamp}.png")

        start_clicked = cdp_eval(
            cdp,
            """
            (() => {
              const form = document.querySelector('form[class*="captureBar"]');
              if (!form) return false;
              const sample = form.querySelector('input[name="sample_hz"]');
              if (sample) {
                sample.value = '50';
                sample.dispatchEvent(new Event('input', { bubbles: true }));
                sample.dispatchEvent(new Event('change', { bubbles: true }));
              }
              const channels = form.querySelector('input[name="channels"]');
              if (channels) {
                channels.value = 'time,sample.0,sample.1,sample.2,state';
                channels.dispatchEvent(new Event('input', { bubbles: true }));
                channels.dispatchEvent(new Event('change', { bubbles: true }));
              }
              const button = form.querySelector('button[value="start"]');
              if (!button || button.disabled) return false;
              button.click();
              return true;
            })()
            """,
        )
        report["start_clicked"] = start_clicked
        if not start_clicked:
            report["failures"].append("start capture button unavailable")
            raise RuntimeError("start capture unavailable")
        wait_for(cdp, "document.readyState === 'complete' && (document.body.innerText.includes('采集请求已排队') || document.body.innerText.includes('开始采集'))", timeout_seconds=30)
        time.sleep(6)

        stop_clicked = cdp_eval(
            cdp,
            """
            (() => {
              const form = document.querySelector('form[class*="captureBar"]');
              if (!form) return false;
              const button = form.querySelector('button[value="stop"]');
              if (!button || button.disabled) return false;
              button.click();
              return true;
            })()
            """,
        )
        report["stop_clicked"] = stop_clicked
        if not stop_clicked:
            report["failures"].append("stop capture button unavailable")
            raise RuntimeError("stop capture unavailable")
        wait_for(cdp, "document.readyState === 'complete' && document.body.innerText.includes('已生成采集片段')", timeout_seconds=30)
        wait_for(
            cdp,
            "document.body.innerText.includes('已收到') || document.body.innerText.includes('采集回执') || document.body.innerText.includes('等待配置仓库同步') || document.body.innerText.includes('本机临时缓存')",
            timeout_seconds=45,
        )
        screenshot(cdp, output_dir / f"real-serial-stopped-{stamp}.png")

        terminal_state = cdp_eval(
            cdp,
            """
            (() => {
              const body = document.body.innerText || '';
              const match = body.match(/已收到\\s+(\\d+)\\s+个样本/);
              return {
                hasSegment: body.includes('已生成采集片段') || body.includes('[capture:ready]'),
                hasSampleResult: !!match,
                sampleCount: match ? Number(match[1]) : 0,
                hasRepoStatus: body.includes('等待配置仓库同步') || body.includes('已写入仓库证据') || body.includes('已推送到仓库'),
                hasCacheStatus: body.includes('本机临时缓存') || body.includes('本机保留待同步缓存') || body.includes('本机缓存'),
                hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
              };
            })()
            """,
        )
        report["terminal_state"] = terminal_state
        if not isinstance(terminal_state, dict) or int(terminal_state.get("sampleCount") or 0) <= 0:
            report["failures"].append("serial capture did not return non-empty samples")

        cdp_eval(
            cdp,
            """
            (() => {
              const button = Array.from(document.querySelectorAll('button')).find((item) => (item.innerText || '').includes('数据标注'));
              if (!button) return false;
              button.click();
              return true;
            })()
            """,
        )
        wait_for(cdp, "document.body.innerText.includes('采集片段') && document.body.innerText.includes('导出标注数据')", timeout_seconds=20)
        dataset_state = cdp_eval(
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
              for (const box of document.querySelectorAll('input[name="capture_ids"], input[name="variables"]')) box.checked = true;
              setValue('input[name="label_schema"]', '用户自定义状态标签');
              setValue('textarea[name="label_notes"]', '真实串口采集验收：用户确认正常状态');
              setValue('textarea[name="manual_labels"]', 'capture-serial,sample.0,0,2,正常,虚拟串口稳定输出');
              setValue('select[name="export_format"]', 'jsonl');
              return {
                captureChecks: document.querySelectorAll('input[name="capture_ids"]').length,
                variableChecks: document.querySelectorAll('input[name="variables"]').length,
                exportEnabled: Array.from(document.querySelectorAll('button')).some((button) => (button.innerText || '').includes('导出标注数据') && !button.disabled),
                segmentText: (document.body.innerText || '').includes('个可标注片段'),
              };
            })()
            """,
        )
        report["dataset_state"] = dataset_state
        export_clicked = cdp_eval(
            cdp,
            """
            (() => {
              const button = Array.from(document.querySelectorAll('button')).find((item) => (item.innerText || '').includes('导出标注数据'));
              if (!button || button.disabled) return false;
              button.click();
              return true;
            })()
            """,
        )
        report["export_clicked"] = export_clicked
        if not export_clicked:
            report["failures"].append("dataset export button unavailable")
        else:
            wait_for(cdp, "document.readyState === 'complete' && (document.body.innerText.includes('标注数据导出') || document.body.innerText.includes('下载数据'))", timeout_seconds=30)
            screenshot(cdp, output_dir / f"real-serial-dataset-{stamp}.png")
            export_href = cdp_eval(
                cdp,
                """
                (() => {
                  const link = Array.from(document.querySelectorAll('a')).find((a) => (a.innerText || '').includes('下载数据'));
                  return link ? link.href : '';
                })()
                """,
            )
            report["export_href"] = export_href
            if export_href:
                status, body = fetch_url(str(export_href), token)
                (output_dir / f"real-serial-export-{stamp}.jsonl").write_bytes(body)
                report["download"] = {"status": status, "bytes": len(body), "preview": body[:300].decode("utf-8", errors="replace")}
                if len(body.strip()) == 0:
                    report["failures"].append("downloaded dataset export is empty")
            else:
                report["failures"].append("dataset download link missing")

        cdp_eval(
            cdp,
            """
            (() => {
              const button = Array.from(document.querySelectorAll('button')).find((item) => (item.innerText || '').includes('图表实验'));
              if (!button) return false;
              button.click();
              return true;
            })()
            """,
        )
        wait_for(cdp, "document.body.innerText.includes('横轴') && document.body.innerText.includes('纵轴')", timeout_seconds=20)
        chart_state = cdp_eval(
            cdp,
            """
            (() => ({
              hasAxisControls: !!document.querySelector('select[name="x_axis"]') && document.querySelectorAll('input[name="y_axes"]').length > 0,
              hasTarget: !!document.querySelector('input[name="target_value"]'),
              hasChartPreview: document.body.innerText.includes('图表预览') || document.body.innerText.includes('已收到') || document.querySelectorAll('svg, canvas').length > 0,
              hasNpcAdvice: document.body.innerText.includes('NPC 分析建议') || document.body.innerText.includes('请求 NPC 分析建议'),
              hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
            }))()
            """,
        )
        report["chart_state"] = chart_state
        screenshot(cdp, output_dir / f"real-serial-chart-{stamp}.png")
        if not isinstance(chart_state, dict) or not chart_state.get("hasAxisControls") or not chart_state.get("hasTarget"):
            report["failures"].append("chart controls missing after real capture")

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
