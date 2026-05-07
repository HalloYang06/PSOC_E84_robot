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
from urllib.parse import urlparse


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
    parser = argparse.ArgumentParser(description="Run the AI collaboration platform from a real browser user's point of view.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default=str(Path("D:/ai合作产品/artifacts")))
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=1000)
    parser.add_argument("--keep-browser-open-ms", type=int, default=0)
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

    def click_text(self, text: str, selector: str = "button,a", timeout: float = 10) -> None:
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
                """,
            )
            if clicked:
                time.sleep(0.8)
                return
            time.sleep(0.3)
        raise RuntimeError(f"Could not click text {text!r} with selector {selector!r}")

    def click_button_near_text(self, nearby_text: str, button_text: str, timeout: float = 10) -> None:
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = self.eval(
                f"""
                (() => {{
                  const nearbyText = {js_string(nearby_text)};
                  const buttonText = {js_string(button_text)};
                  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                  let node = walker.nextNode();
                  while (node) {{
                    if ((node.textContent || '').includes(nearbyText)) {{
                      let host = node.parentElement;
                      while (host && host !== document.body) {{
                        const buttons = Array.from(host.querySelectorAll('button'));
                        const button = buttons.find((item) => (item.innerText || item.textContent || '').includes(buttonText));
                        if (button) {{
                          button.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
                          button.click();
                          return true;
                        }}
                        host = host.parentElement;
                      }}
                    }}
                    node = walker.nextNode();
                  }}
                  return `missing nearby=${{nearbyText}} button=${{buttonText}}`;
                }})()
                """,
            )
            if last is True:
                time.sleep(1.5)
                return
            time.sleep(0.3)
        raise RuntimeError(str(last))

    def fill_in_form(self, form_hint: str, name: str, value: str) -> None:
        ok = self.eval(
            f"""
            (() => {{
              const formHint = {js_string(form_hint)};
              const name = {js_string(name)};
              const value = {js_string(value)};
              const forms = Array.from(document.querySelectorAll('form'));
              const form = forms.find((item) => (item.innerText || item.textContent || '').includes(formHint));
              if (!form) return `missing form: ${{formHint}}`;
              const field = form.querySelector(`[name="${{CSS.escape(name)}}"]`);
              if (!field) return `missing field: ${{name}}`;
              field.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
              field.focus();
              field.value = value;
              field.dispatchEvent(new Event('input', {{ bubbles: true }}));
              field.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return true;
            }})()
            """,
        )
        if ok is not True:
            raise RuntimeError(str(ok))

    def select_in_form(self, form_hint: str, name: str, value: str) -> None:
        self.fill_in_form(form_hint, name, value)

    def submit_form(self, form_hint: str, button_text: str, timeout: float = 10) -> None:
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = self.eval(
                f"""
                (() => {{
                  const formHint = {js_string(form_hint)};
                  const buttonText = {js_string(button_text)};
                  const forms = Array.from(document.querySelectorAll('form'));
                  const form = forms.find((item) => (item.innerText || item.textContent || '').includes(formHint));
                  if (!form) return 'missing form';
                  const buttons = Array.from(form.querySelectorAll('button'));
                  const button = buttons.find((item) => (item.innerText || item.textContent || '').includes(buttonText));
                  if (!button) return 'missing button';
                  button.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
                  button.click();
                  return true;
                }})()
                """,
            )
            if last is True:
                time.sleep(2.0)
                return
            time.sleep(0.3)
        raise RuntimeError(f"Could not submit form {form_hint!r}/{button_text!r}: {last}")

    def screenshot(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        shot = self.cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
        data = str(shot.get("data") or "")
        if not data:
            raise RuntimeError("CDP returned an empty screenshot")
        output.write_bytes(base64.b64decode(data))


def authenticate(api_base: str, email: str, password: str) -> tuple[str, str]:
    payload = cdp_helper.request_json(
        f"{api_base.rstrip('/')}/api/auth/session",
        method="POST",
        payload={"email": email, "password": password},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get("access_token"):
        raise RuntimeError("Auth response did not include access_token")
    return str(data["access_token"]), json.dumps(data.get("user") or {}, ensure_ascii=True)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    token, user_json = authenticate(args.api_base, args.login_email, args.login_password)

    port = cdp_helper.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-user-flow-cdp-"))
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
        page_target = next(
            (item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")),
            None,
        )
        if not isinstance(page_target, dict):
            raise RuntimeError("No Edge page target available")
        cdp = cdp_helper.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.viewport_width,
                "height": args.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )

        origin = f"{urlparse(args.web_base).scheme}://{urlparse(args.web_base).netloc}"
        cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})

        flow = BrowserFlow(cdp)
        flow.navigate(f"{args.web_base.rstrip('/')}/projects", "项目管理入口", "新建项目")
        flow.click_text("邀请合作者")
        flow.wait_for_text("邀请合作者")
        shot = output_dir / f"user-flow-01-projects-invite-{stamp}.png"
        flow.screenshot(shot)
        screenshots.append(shot)

        flow.click_text("新建项目")
        project_name = f"用户视角验收-协作写作-{stamp}"
        node_id = f"user-flow-local-pc-{stamp}"
        codex_thread_id = f"codex-session-user-flow-researcher-{stamp}"
        claude_thread_id = f"claude-session-user-flow-writer-{stamp}"

        flow.fill_in_form("创建项目并进入", "name", project_name)
        flow.fill_in_form("创建项目并进入", "description", "从项目管理页实际创建，用于验证电脑、Codex、Claude NPC 与协作写作任务。")
        flow.fill_in_form("创建项目并进入", "local_git_url", "D:/ai合作产品")
        flow.submit_form("创建项目并进入", "创建项目并进入")
        project_url = flow.wait_for_url_contains("/projects/", timeout=30)
        flow.wait_for_text(project_name, "打开背包")
        shot = output_dir / f"user-flow-02-created-project-farm-{stamp}.png"
        flow.screenshot(shot)
        screenshots.append(shot)

        project_id = project_url.split("/projects/", 1)[1].split("?", 1)[0].split("/", 1)[0]

        flow.navigate(f"{args.web_base.rstrip('/')}/projects/{project_id}?panel=team&tab=computers", "电脑接入是第一步", "登记一台电脑")
        flow.fill_in_form("登记一台电脑", "id", node_id)
        flow.fill_in_form("登记一台电脑", "label", "本机 Windows 验收电脑")
        flow.select_in_form("登记一台电脑", "status", "online")
        flow.select_in_form("登记一台电脑", "connection_kind", "local")
        flow.fill_in_form("登记一台电脑", "workspace_root", "D:/ai合作产品")
        flow.fill_in_form("登记一台电脑", "git_root", "D:/ai合作产品")
        flow.fill_in_form("登记一台电脑", "read_paths", ".")
        flow.fill_in_form("登记一台电脑", "write_paths", "docs/ai-handoffs, apps/web")
        flow.submit_form("登记一台电脑", "登记电脑")
        flow.wait_for_text("本机 Windows 验收电脑", "状态：online")
        shot = output_dir / f"user-flow-03-computer-registered-{stamp}.png"
        flow.screenshot(shot)
        screenshots.append(shot)

        flow.navigate(f"{args.web_base.rstrip('/')}/projects/{project_id}?panel=team&tab=machine-room", "线程列表", "手动登记一个真实线程")
        flow.fill_in_form("手动登记一个真实线程", "id", codex_thread_id)
        flow.fill_in_form("手动登记一个真实线程", "name", "Codex 资料员")
        flow.select_in_form("手动登记一个真实线程", "computer_node_id", node_id)
        flow.select_in_form("手动登记一个真实线程", "ai_provider_id", "codex")
        flow.fill_in_form("手动登记一个真实线程", "ai_provider", "Codex")
        flow.fill_in_form("手动登记一个真实线程", "model", "gpt-5.4")
        flow.fill_in_form("手动登记一个真实线程", "responsibility", "找资料：收集文章素材和要点")
        flow.fill_in_form("手动登记一个真实线程", "notes", "用户在 Codex 软件里打开的资料员线程，路径由本机自行决定。")
        flow.submit_form("手动登记一个真实线程", "登记线程")
        flow.navigate(f"{args.web_base.rstrip('/')}/projects/{project_id}?panel=team&tab=machine-room", "线程列表", "手动登记一个真实线程")
        flow.wait_for_text("Codex 资料员", codex_thread_id)

        flow.fill_in_form("手动登记一个真实线程", "id", claude_thread_id)
        flow.fill_in_form("手动登记一个真实线程", "name", "Claude 写作者")
        flow.select_in_form("手动登记一个真实线程", "computer_node_id", node_id)
        flow.select_in_form("手动登记一个真实线程", "ai_provider_id", "claude")
        flow.fill_in_form("手动登记一个真实线程", "ai_provider", "Claude")
        flow.fill_in_form("手动登记一个真实线程", "model", "claude")
        flow.fill_in_form("手动登记一个真实线程", "responsibility", "写文章：根据资料整理成一篇短文")
        flow.fill_in_form("手动登记一个真实线程", "notes", "用户在 Claude 终端里打开的写作者线程，其他电脑可用 GitHub 自定本地路径。")
        flow.submit_form("手动登记一个真实线程", "登记线程")
        flow.navigate(f"{args.web_base.rstrip('/')}/projects/{project_id}?panel=team&tab=machine-room", "线程列表", "手动登记一个真实线程")
        flow.wait_for_text("Claude 写作者", claude_thread_id)
        shot = output_dir / f"user-flow-04-threads-registered-{stamp}.png"
        flow.screenshot(shot)
        screenshots.append(shot)

        flow.navigate(f"{args.web_base.rstrip('/')}/projects/{project_id}?panel=team&tab=machine-room", "Codex 资料员", "Claude 写作者")
        flow.click_button_near_text("Codex 资料员", "创建")
        flow.wait_for_text("已绑定")
        flow.navigate(f"{args.web_base.rstrip('/')}/projects/{project_id}?panel=team&tab=machine-room", "Claude 写作者")
        flow.click_button_near_text("Claude 写作者", "创建")
        flow.wait_for_text("已绑定", timeout=20)
        shot = output_dir / f"user-flow-05-npc-bound-{stamp}.png"
        flow.screenshot(shot)
        screenshots.append(shot)

        flow.navigate(f"{args.web_base.rstrip('/')}/projects/{project_id}?panel=team&tab=exchange", "下发协作指令", "当前推荐动作")
        flow.fill_in_form("下发协作指令", "recipient_id", codex_thread_id)
        flow.fill_in_form("下发协作指令", "title", "协作写作：资料收集")
        flow.fill_in_form(
            "下发协作指令",
            "body",
            "请作为资料员，围绕“多电脑多 AI 协作平台如何帮助小团队写文章和开发项目”整理 5 个要点。先回最小回执，再给最终资料提纲。",
        )
        flow.submit_form("下发协作指令", "发送协作指令")
        flow.wait_for_text("协作写作：资料收集")

        flow.fill_in_form("下发协作指令", "recipient_id", claude_thread_id)
        flow.fill_in_form("下发协作指令", "title", "协作写作：文章初稿")
        flow.fill_in_form(
            "下发协作指令",
            "body",
            "请作为写作者，等待资料员的要点后，把它整理成一篇 800 字以内的短文。先回最小回执，最终回复要可直接放入文档。",
        )
        flow.submit_form("下发协作指令", "发送协作指令")
        flow.wait_for_text("协作写作：文章初稿")
        shot = output_dir / f"user-flow-06-commands-dispatched-{stamp}.png"
        flow.screenshot(shot)
        screenshots.append(shot)

        report = {
            "stamp": stamp,
            "project_id": project_id,
            "project_name": project_name,
            "computer_node_id": node_id,
            "codex_thread_id": codex_thread_id,
            "claude_thread_id": claude_thread_id,
            "screenshots": [str(path) for path in screenshots],
            "url": flow.url(),
        }
        report_path = output_dir / f"user-flow-acceptance-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.keep_browser_open_ms > 0:
            time.sleep(args.keep_browser_open_ms / 1000)
        return 0
    finally:
        if cdp is not None:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
