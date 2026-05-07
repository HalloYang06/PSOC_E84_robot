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
from datetime import datetime
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_HELPER_PATH = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"

spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helper: {CDP_HELPER_PATH}")
cdp_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helper)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the guided /projects plaza flow through a real browser.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--expected-project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--output-dir", default=str(Path("D:/ai合作产品/artifacts")))
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=1100)
    return parser.parse_args()


def js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class BrowserFlow:
    def __init__(self, cdp):
        self.cdp = cdp

    def eval(self, expression: str):
        result = self.cdp.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        return result.get("result", {}).get("value")

    def text(self) -> str:
        value = self.eval("document.body ? document.body.innerText : ''")
        return str(value or "")

    def url(self) -> str:
        value = self.eval("location.href")
        return str(value or "")

    def wait_for_text(self, *markers: str, timeout: float = 20) -> str:
        deadline = time.time() + timeout
        last_text = ""
        while time.time() < deadline:
            last_text = self.text()
            if all(marker in last_text for marker in markers):
                return last_text
            time.sleep(0.35)
        missing = [marker for marker in markers if marker not in last_text]
        raise RuntimeError(f"Missing text markers: {missing}\nCurrent URL: {self.url()}\nLast text:\n{last_text[:2000]}")

    def wait_for_url_contains(self, marker: str, timeout: float = 20) -> str:
        deadline = time.time() + timeout
        last_url = ""
        while time.time() < deadline:
            last_url = self.url()
            if marker in last_url:
                return last_url
            time.sleep(0.35)
        raise RuntimeError(f"URL did not contain {marker!r}. Last URL: {last_url}")

    def navigate(self, url: str, *markers: str):
        self.cdp.send("Page.navigate", {"url": url})
        if markers:
            self.wait_for_text(*markers)
        time.sleep(0.8)

    def fill(self, selector: str, value: str):
        ok = self.eval(
            f"""
            (() => {{
              const field = document.querySelector({js_string(selector)});
              if (!field) return false;
              field.focus();
              field.value = {js_string(value)};
              field.dispatchEvent(new Event('input', {{ bubbles: true }}));
              field.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return true;
            }})()
            """
        )
        if not ok:
            raise RuntimeError(f"Could not fill selector {selector!r}")

    def click_text(self, text: str, selector: str = "button,a", timeout: float = 10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            clicked = self.eval(
                f"""
                (() => {{
                  const wanted = {js_string(text)};
                  const items = Array.from(document.querySelectorAll({js_string(selector)}));
                  const el = items.find((item) => (item.innerText || item.textContent || '').includes(wanted));
                  if (!el) return false;
                  el.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
                  el.click();
                  return true;
                }})()
                """
            )
            if clicked:
                time.sleep(1.2)
                return
            time.sleep(0.3)
        raise RuntimeError(f"Could not click text {text!r}")

    def click_href_contains(self, marker: str, selector: str = "a", timeout: float = 10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            clicked = self.eval(
                f"""
                (() => {{
                  const wanted = {js_string(marker)};
                  const items = Array.from(document.querySelectorAll({js_string(selector)}));
                  const el = items.find((item) => (item.getAttribute('href') || '').includes(wanted));
                  if (!el) return false;
                  el.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
                  el.click();
                  return true;
                }})()
                """
            )
            if clicked:
                time.sleep(1.2)
                return
            time.sleep(0.3)
        raise RuntimeError(f"Could not click href containing {marker!r}")

    def screenshot(self, output: Path):
        output.parent.mkdir(parents=True, exist_ok=True)
        shot = self.cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
        data = str(shot.get("data") or "")
        if not data:
            raise RuntimeError("CDP returned an empty screenshot")
        output.write_bytes(base64.b64decode(data))


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    port = cdp_helper.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-projects-plaza-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    screenshots: list[Path] = []
    try:
        edge_process = subprocess.Popen(
            [
                str(cdp_helper.find_edge()),
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
        targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        if not isinstance(targets, list) or not targets:
            cdp_helper.request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
            targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page"), None)
        if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
            raise RuntimeError("No CDP page target available")

        cdp = cdp_helper.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
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

        flow = BrowserFlow(cdp)
        web_base = args.web_base.rstrip("/")

        flow.navigate(f"{web_base}/login", "先登录，再进入项目", "进入平台")
        shot_login = output_dir / f"projects-plaza-01-login-{stamp}.png"
        flow.screenshot(shot_login)
        screenshots.append(shot_login)

        login_text = flow.text()
        if any(marker in login_text for marker in ("鏈", "鍩", "鐧", "妯")):
            raise RuntimeError(f"Found mojibake marker in /login page:\n{login_text[:2000]}")

        flow.fill('input[name="email"], input[type="email"]', args.login_email)
        flow.fill('input[name="password"], input[type="password"]', args.login_password)
        flow.click_text("进入平台", "button")

        body_text = flow.wait_for_text("项目管理入口", "推荐下一步", "最近项目", "我的项目")
        if any(marker in body_text for marker in ("鏈", "鍩", "鐧", "妯")):
            raise RuntimeError(f"Found mojibake marker in /projects page:\n{body_text[:2000]}")

        plaza_state = flow.eval(
            """
            (() => {
              const text = document.body ? document.body.innerText : "";
              const links = Array.from(document.querySelectorAll('a'))
                .map((item) => ({
                  text: (item.innerText || item.textContent || '').trim(),
                  href: item.getAttribute('href') || ''
                }))
                .filter((item) => item.href.includes('/projects/'));
              return {
                title: document.title,
                hasRecommended: text.includes('推荐下一步'),
                hasRecent: text.includes('最近项目'),
                hasProjectTabs: ['选择项目', '邀请合作者', '接受邀请', '新建项目'].every((item) => text.includes(item)),
                links
              };
            })()
            """
        )
        shot_plaza = output_dir / f"projects-plaza-02-guided-home-{stamp}.png"
        flow.screenshot(shot_plaza)
        screenshots.append(shot_plaza)

        went_to_project = False
        selected_project_target = None
        if isinstance(plaza_state, dict):
            live_links = [
                item
                for item in plaza_state.get("links", [])
                if isinstance(item, dict) and "/projects/" in str(item.get("href") or "")
            ]
            if live_links:
                preferred_link = next(
                    (
                        item
                        for item in live_links
                        if args.expected_project_id and args.expected_project_id in str(item.get("href") or "")
                    ),
                    None,
                )
                if preferred_link:
                    selected_project_target = str(preferred_link.get("href") or "")
                    flow.click_href_contains(args.expected_project_id, "a")
                elif "继续当前项目协作" in body_text:
                    flow.click_text("继续当前项目协作", "a,button")
                else:
                    flow.click_text("进入 2D live 入口", "a")
                if args.expected_project_id and selected_project_target:
                    flow.wait_for_url_contains(args.expected_project_id, timeout=35)
                else:
                    flow.wait_for_url_contains("/projects/", timeout=35)
                went_to_project = True

        shot_project = None
        if went_to_project:
            flow.wait_for_text("开发工坊", "NPC 管理")
            shot_project = output_dir / f"projects-plaza-03-project-live-entry-{stamp}.png"
            flow.screenshot(shot_project)
            screenshots.append(shot_project)

        report = {
            "timestamp": stamp,
            "login_email": args.login_email,
            "expected_project_id": args.expected_project_id,
            "projects_page_url": f"{web_base}/projects",
            "current_url": flow.url(),
            "plaza_state": plaza_state,
            "selected_project_target": selected_project_target,
            "went_to_project": went_to_project,
            "screenshots": [str(item) for item in screenshots],
        }
        report_path = output_dir / f"projects-plaza-guided-flow-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(str(report_path))
        return 0
    finally:
        if cdp is not None:
            try:
                cdp.close()
            except Exception:
                pass
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=5)
            except Exception:
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
