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
from urllib.parse import quote


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
    parser = argparse.ArgumentParser(description="Current AI collaboration platform user-view acceptance.")
    parser.add_argument("--web-base", required=True)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/current-platform-userwalk")
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=1000)
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


def navigate(cdp: object, url: str, markers: list[str], timeout_seconds: float = 40) -> dict[str, object]:
    cdp.send("Page.navigate", {"url": url})
    marker_expr = " && ".join([f"(document.body?.innerText || '').includes({js(marker)})" for marker in markers])
    wait_for(cdp, f"document.readyState === 'complete' && document.body && document.body.innerText.length > 100 && {marker_expr}", timeout_seconds)
    time.sleep(0.6)
    return page_state(cdp)


def page_state(cdp: object) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        """
        (() => {
          const body = document.body?.innerText || '';
          const root = document.scrollingElement || document.documentElement;
          const visibleTextareas = Array.from(document.querySelectorAll('textarea')).filter((node) => {
            const visible = !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
            return visible;
          }).map((node) => node.getAttribute('placeholder') || '');
          return {
            href: location.href,
            title: document.title,
            bodyText: body,
            bodyPreview: body.slice(0, 2400),
            articleCount: document.querySelectorAll('article').length,
            detailsCount: document.querySelectorAll('details').length,
            visibleTextareas,
            buttons: Array.from(document.querySelectorAll('button')).map((button) => (button.textContent || '').trim()).filter(Boolean).slice(0, 80),
            links: Array.from(document.querySelectorAll('a')).map((link) => (link.textContent || '').trim()).filter(Boolean).slice(0, 80),
            horizontalOverflow: root.scrollWidth > root.clientWidth + 2,
            internalMatches: Array.from(new Set((body.match(/adapter|bridge|session JSONL|source_thread|canonical|requested id|raw UUID/ig) || []))),
          };
        })()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Unexpected page state: {state}")
    return state


def click_center(cdp: object, selector: str) -> bool:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const el = document.querySelector({js(selector)});
          if (!el) return {{ ok: false }};
          el.scrollIntoView({{ block: 'center', inline: 'nearest' }});
          const rect = el.getBoundingClientRect();
          return {{ ok: true, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
        }})()
        """,
    )
    if not isinstance(state, dict) or not state.get("ok"):
        return False
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": state["x"], "y": state["y"]})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": state["x"], "y": state["y"], "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": state["x"], "y": state["y"], "button": "left", "clickCount": 1})
    return True


def click_button_by_text(cdp: object, text: str) -> bool:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const button = Array.from(document.querySelectorAll('button')).find((item) => (item.textContent || '').includes({js(text)}));
          if (!button) return {{ ok: false }};
          button.scrollIntoView({{ block: 'center', inline: 'nearest' }});
          const rect = button.getBoundingClientRect();
          return {{ ok: true, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
        }})()
        """,
    )
    if not isinstance(state, dict) or not state.get("ok"):
        return False
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": state["x"], "y": state["y"]})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": state["x"], "y": state["y"], "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": state["x"], "y": state["y"], "button": "left", "clickCount": 1})
    return True


def assert_page(report: dict[str, object], name: str, state: dict[str, object], required: list[str], *, forbid_internal: bool = True) -> None:
    body = str(state.get("bodyText") or "")
    failures = report.setdefault("failures", [])
    assert isinstance(failures, list)
    for marker in required:
        if marker not in body:
            failures.append(f"{name}: missing marker {marker}")
    if state.get("horizontalOverflow"):
        failures.append(f"{name}: horizontal overflow")
    if forbid_internal and state.get("internalMatches"):
        failures.append(f"{name}: exposes internal terms {state.get('internalMatches')}")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    web_base = args.web_base.rstrip("/")
    project_url = f"{web_base}/projects/{quote(args.project_id, safe='')}"
    report: dict[str, object] = {"project_id": args.project_id, "screenshots": [], "surfaces": {}, "failures": []}

    token, user_json = cdp_helpers.authenticate(args)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="current-platform-userwalk-"))
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
        if token:
            cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{web_base}/", "path": "/", "sameSite": "Lax"})
        if user_json:
            cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{web_base}/", "path": "/", "sameSite": "Lax"})

        main_state = navigate(cdp, f"{project_url}/2d-upgrade", ["Medical-Rehabilitation-Manipulator"])
        shot = output_dir / f"01-main-{stamp}.png"
        screenshot(cdp, shot)
        report["screenshots"].append(str(shot))
        report["surfaces"]["main"] = main_state
        assert_page(report, "main", main_state, ["Medical-Rehabilitation-Manipulator"], forbid_internal=False)

        company_state = navigate(cdp, f"{project_url}/company", ["公司层 / 运行态势图", "公司沙盘", "组织变更"])
        shot = output_dir / f"02-company-{stamp}.png"
        screenshot(cdp, shot)
        report["screenshots"].append(str(shot))
        report["surfaces"]["company"] = company_state
        assert_page(report, "company", company_state, ["公司沙盘", "部门区域", "组织变更", "电脑健康"])

        workbench_state = navigate(cdp, f"{project_url}/workbench", ["协同工作台", "项目资源索引", "派工验真"])
        if click_center(cdp, 'a[data-workbench-open-tile]'):
            wait_for(cdp, "Array.from(document.querySelectorAll('textarea')).some((node) => (node.placeholder || '').includes('发指令') && !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length))")
        workbench_open_state = page_state(cdp)
        shot = output_dir / f"03-workbench-open-{stamp}.png"
        screenshot(cdp, shot)
        report["screenshots"].append(str(shot))
        report["surfaces"]["workbench"] = workbench_open_state
        assert_page(report, "workbench", workbench_open_state, ["协同工作台", "的对话", "桌面可见", "我的需求", "我的任务"])

        robotics_url = f"{project_url}/robotics?windows={quote('wjy-windows:serial:COM30', safe='')}"
        robotics_state = navigate(cdp, robotics_url, ["创建调试窗口", "终端", "数据标注", "图表实验"])
        click_button_by_text(cdp, "数据标注")
        wait_for(cdp, "document.body.innerText.includes('采集片段') && document.body.innerText.includes('可用变量')")
        click_button_by_text(cdp, "图表实验")
        wait_for(cdp, "document.body.innerText.includes('横轴') && document.body.innerText.includes('纵轴')")
        robotics_final = page_state(cdp)
        shot = output_dir / f"04-robotics-{stamp}.png"
        screenshot(cdp, shot)
        report["screenshots"].append(str(shot))
        report["surfaces"]["robotics"] = robotics_final
        assert_page(report, "robotics", robotics_final, ["创建调试窗口", "终端", "数据标注", "图表实验", "横轴", "纵轴"])

        skill_state = navigate(cdp, f"{project_url}/skill-forge", ["能力工坊", "Skill", "打开全部"])
        click_center(cdp, 'a[href*="skill-forge?resources="], button')
        time.sleep(1)
        if "Skill 配置" not in str(page_state(cdp).get("bodyText") or ""):
            click_center(cdp, 'a,button')
            time.sleep(1)
        skill_final = page_state(cdp)
        shot = output_dir / f"05-skill-forge-{stamp}.png"
        screenshot(cdp, shot)
        report["screenshots"].append(str(shot))
        report["surfaces"]["skill_forge"] = skill_final
        assert_page(report, "skill_forge", skill_final, ["Skill 配置", "知识库配置", "Git 管理", "能力来源", "GitHub"])

        report["verdict"] = "passed" if not report["failures"] else "failed"
        report_path = output_dir / f"current-platform-userwalk-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"verdict": report["verdict"], "failures": report["failures"], "report_path": str(report_path), "screenshots": report["screenshots"]}, ensure_ascii=False, indent=2))
        return 0 if report["verdict"] == "passed" else 1
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
