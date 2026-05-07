from __future__ import annotations

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
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = REPO_ROOT / "artifacts"
ONBOARDING_PATH = SCRIPT_DIR / "validate-ui-frontdoor-onboarding-cdp.py"
DUAL_HELPER_PATH = SCRIPT_DIR / "validate-dual-account-invite-collab-cdp.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


onboarding = load_module("ui_onboarding_helper", ONBOARDING_PATH)
dual_helper = load_module("dual_helper", DUAL_HELPER_PATH)

BrowserRuntime = dual_helper.BrowserRuntime
find_free_port = dual_helper.find_free_port
login_via_ui = dual_helper.login_via_ui
new_browser_profile = dual_helper.new_browser_profile
create_computer_via_ui = dual_helper.create_computer_via_ui
api_login = dual_helper.api_login
request_json = dual_helper.request_json
cdp_helper = dual_helper.cdp_helper

WEB_BASE = onboarding.WEB_BASE
API_BASE = onboarding.API_BASE
VIEWPORT_WIDTH = onboarding.VIEWPORT_WIDTH
VIEWPORT_HEIGHT = onboarding.VIEWPORT_HEIGHT
OWNER_EMAIL = onboarding.OWNER_EMAIL
OWNER_PASSWORD = onboarding.OWNER_PASSWORD
PROJECT_ID = "7f2d9a27-cecf-4e61-af25-3792c24971e6"
CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


class ResilientBrowserRuntime(BrowserRuntime):
    def __enter__(self):
        last_error: Exception | None = None
        for _attempt in range(3):
            try:
                self.process = subprocess.Popen(
                    [
                        str(CHROME_PATH if CHROME_PATH.exists() else cdp_helper.find_edge()),
                        "--headless=new",
                        "--disable-gpu",
                        f"--remote-debugging-port={self.port}",
                        f"--user-data-dir={self.profile_dir}",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "about:blank",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                cdp_helper.wait_for_json(f"http://127.0.0.1:{self.port}/json/version", timeout_seconds=20)
                page_target = cdp_helper.request_json(f"http://127.0.0.1:{self.port}/json/new?about:blank", method="PUT")
                if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
                    targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{self.port}/json/list", timeout_seconds=20)
                    if not isinstance(targets, list) or not targets:
                        raise RuntimeError("No CDP page target available")
                    page_target = next(
                        (item for item in reversed(targets) if isinstance(item, dict) and item.get("type") == "page"),
                        None,
                    )
                if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
                    raise RuntimeError("No CDP page target available")
                self.cdp = cdp_helper.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
                self.cdp.send("Page.enable")
                self.cdp.send("Runtime.enable")
                self.cdp.send("Network.enable")
                self.cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                self.cdp.send(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": self.viewport_width,
                        "height": self.viewport_height,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                time.sleep(1.0)
                return dual_helper.BrowserFlow(self.cdp)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                try:
                    if self.cdp is not None:
                        self.cdp.close()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    if self.process is not None and self.process.poll() is None:
                        self.process.kill()
                except Exception:  # noqa: BLE001
                    pass
                self.cdp = None
                self.process = None
        raise RuntimeError(f"Could not establish browser CDP session after retries: {last_error}") from last_error


def wait_panel_idle(flow) -> dict[str, object]:
    state = flow.wait_for(
        """
        (() => {
          const panel = document.querySelector('#project-main-panel');
          if (!panel) return false;
          const busy = panel.getAttribute('data-busy') || '';
          const overlay = panel.querySelector('[role="status"]');
          return busy === 'false'
            ? {
                busy,
                overlayVisible: Boolean(overlay),
                href: location.href,
                body: document.body ? document.body.innerText.slice(0, 1800) : '',
              }
            : false;
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
      raise RuntimeError(f"Panel did not return to idle state: {state}")
    return state


def request_thread_scan(flow, *, computer_id: str) -> dict[str, object]:
    triggered = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-request-scan={json.dumps(computer_id)}]');
          if (!button || button.disabled) return false;
          const form = button.closest('form');
          if (!form) return false;
          form.requestSubmit();
          return true;
        }})()
        """
    )
    if not triggered:
        raise RuntimeError(f"Could not trigger thread scan for {computer_id}")
    return wait_panel_idle(flow)


def read_thread_preview_state(flow, *, computer_id: str) -> dict[str, object]:
    state = flow.wait_for(
        f"""
        (() => {{
          const panel = document.querySelector('[data-computer-thread-preview-for={json.dumps(computer_id)}]');
          if (!panel) return false;
          const badge = panel.querySelector('span');
          const badgeText = badge ? (badge.textContent || '').trim() : '';
          const badgeMatch = badgeText.match(/(\\d+)/);
          const renderedItems = Array.from(panel.querySelectorAll('[data-computer-thread-item]'));
          const scanStatus = panel.querySelector('[data-computer-thread-scan-status={json.dumps(computer_id)}]');
          const names = renderedItems.map((item) => {{
            const strong = item.querySelector('strong');
            return strong ? (strong.textContent || '').trim() : (item.textContent || '').trim();
          }});
          const preview = {{
            badgeText,
            badgeCount: badgeMatch ? Number(badgeMatch[1]) : 0,
            renderedCount: renderedItems.length,
            names,
            scanStatus: scanStatus ? (scanStatus.textContent || '').trim() : '',
            href: location.href,
            body: document.body ? document.body.innerText.slice(0, 2200) : '',
          }};
          return preview.badgeCount > 0 ? preview : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.5,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Thread preview did not become visible for {computer_id}: {state}")
    return state


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="computer-thread-visibility-"))
    computer_id = f"thread-visibility-{stamp[-6:]}"
    computer_label = f"Thread Visibility {stamp[-6:]}"
    runner_id = f"runner-{stamp[-6:]}"
    runner_name = f"Runner {stamp[-6:]}"

    report: dict[str, object] = {
        "stamp": stamp,
        "project_id": PROJECT_ID,
        "computer_id": computer_id,
        "runner_id": runner_id,
        "screenshots": {},
        "issues": [],
    }

    token, _owner = api_login(API_BASE, OWNER_EMAIL, OWNER_PASSWORD)

    try:
        profile_dir = new_browser_profile(runtime_dir, "owner")
        with ResilientBrowserRuntime(find_free_port(), profile_dir, VIEWPORT_WIDTH, VIEWPORT_HEIGHT) as flow:
            shot = OUTPUT_DIR / f"computer-thread-visibility-01-login-{stamp}.png"
            login_via_ui(flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=shot)
            report["screenshots"]["login"] = str(shot)

            shot = OUTPUT_DIR / f"computer-thread-visibility-02-create-computer-{stamp}.png"
            create_state = create_computer_via_ui(
                flow,
                WEB_BASE,
                project_id=PROJECT_ID,
                computer_id=computer_id,
                label=computer_label,
                workspace_root=str(REPO_ROOT),
                git_root=str(REPO_ROOT),
                shot=shot,
            )
            report["create_state"] = create_state
            report["screenshots"]["create_computer"] = str(shot)

            create_idle = wait_panel_idle(flow)
            report["create_idle_state"] = create_idle

            onboarding.open_computer_threads_drawer(flow, project_id=PROJECT_ID, computer_id=computer_id)
            shot = OUTPUT_DIR / f"computer-thread-visibility-03-before-generate-{stamp}.png"
            flow.screenshot(shot)
            report["screenshots"]["before_generate"] = str(shot)

            pairing_state = onboarding.generate_pairing_token_via_ui_pure(
                flow,
                project_id=PROJECT_ID,
                computer_id=computer_id,
                shot=OUTPUT_DIR / f"computer-thread-visibility-04-after-generate-{stamp}.png",
            )
            report["pairing_state"] = pairing_state
            report["screenshots"]["after_generate"] = str(OUTPUT_DIR / f"computer-thread-visibility-04-after-generate-{stamp}.png")

            guide = pairing_state.get("guide") if isinstance(pairing_state.get("guide"), dict) else {}
            one_click_command = str(guide.get("oneClickCommand") or "")
            if "connect-ai-collab-runner.ps1" not in one_click_command:
                raise RuntimeError(f"One-click connector command missing from onboarding guide: {one_click_command[:300]}")
            report["one_click_command_available"] = True

            connect_result = onboarding.run_powershell_script(
                "connect-ai-collab-runner.ps1",
                "-Server",
                API_BASE,
                "-PairingToken",
                str(pairing_state.get("pairingToken") or ""),
                "-ComputerNodeId",
                computer_id,
                "-RunnerName",
                runner_name,
                "-RunnerId",
                runner_id,
                "-ProjectId",
                PROJECT_ID,
                "-WorkspaceRoot",
                str(REPO_ROOT),
            )
            if int(connect_result.get("returncode", 1)) != 0:
                raise RuntimeError(f"connect-ai-collab-runner failed: {connect_result}")
            report["connect_result"] = connect_result

            onboarding.open_computer_threads_drawer(flow, project_id=PROJECT_ID, computer_id=computer_id)
            scan_idle = request_thread_scan(flow, computer_id=computer_id)
            report["scan_idle_state"] = scan_idle

            thread_preview = read_thread_preview_state(flow, computer_id=computer_id)
            report["thread_preview"] = thread_preview

            shot = OUTPUT_DIR / f"computer-thread-visibility-05-after-scan-{stamp}.png"
            flow.screenshot(shot)
            report["screenshots"]["after_scan"] = str(shot)

            if int(thread_preview.get("badgeCount", 0)) <= 6:
                report["issues"].append(
                    f"expected more than 6 synced threads for regression coverage, got {thread_preview.get('badgeCount')}"
                )
            if int(thread_preview.get("renderedCount", 0)) != int(thread_preview.get("badgeCount", 0)):
                report["issues"].append(
                    f"thread preview mismatch: rendered {thread_preview.get('renderedCount')} vs badge {thread_preview.get('badgeCount')}"
                )

        report_path = OUTPUT_DIR / f"computer-thread-visibility-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report_path": str(report_path), "issues": report["issues"]}, ensure_ascii=False))
        return 0 if not report["issues"] else 1
    finally:
        try:
            request_json(
                f"{API_BASE.rstrip('/')}/api/collaboration/projects/{PROJECT_ID}/computer-nodes/{computer_id}",
                method="DELETE",
                headers={"Authorization": f"Bearer {token}"},
            )
        except Exception:
            report.setdefault("issues", []).append("cleanup_delete_computer_failed")
        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
