from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
HELPER_PATH = SCRIPT_DIR / "validate-dual-account-invite-collab-cdp.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("dual_helper", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module: {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dual_helper = load_helper()
BrowserRuntime = dual_helper.BrowserRuntime
find_free_port = dual_helper.find_free_port
login_via_ui = dual_helper.login_via_ui
new_browser_profile = dual_helper.new_browser_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Screenshot and validate the computer manager runner-watch summary.",
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--project-id", default="78151f5f-f08c-4e83-b0fc-9be89263ecb3")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--viewport-width", type=int, default=1720)
    parser.add_argument("--viewport-height", type=int, default=1080)
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    runtime_dir = Path(tempfile.mkdtemp(prefix="computer-watch-summary-"))
    screenshots: dict[str, str] = {}
    issues: list[str] = []

    try:
        profile_dir = new_browser_profile(runtime_dir, "owner")
        with BrowserRuntime(find_free_port(), profile_dir, args.viewport_width, args.viewport_height) as flow:
            login_shot = output_dir / f"computer-watch-summary-01-login-{stamp}.png"
            login_via_ui(flow, web_base, email=args.login_email, password=args.login_password, shot=login_shot)
            screenshots["login"] = str(login_shot)

            flow.navigate(f"{web_base}/projects/{args.project_id}?panel=team&tab=computers")
            state = flow.wait_for(
                """
                (() => {
                  const summary = document.querySelector('[data-computer-watch-summary="true"]');
                  const panel = document.querySelector('#project-main-panel');
                  if (!summary || !panel) return false;
                  summary.scrollIntoView({ block: 'center', inline: 'nearest' });
                  return {
                    href: location.href,
                    text: (summary.textContent || '').trim(),
                    readyCount: summary.getAttribute('data-computer-watch-ready-count') || '',
                    blockedCount: summary.getAttribute('data-computer-watch-blocked-count') || '',
                    queuedCount: summary.getAttribute('data-computer-queued-command-count') || '',
                    recoveryCount: String(document.querySelectorAll('[data-computer-watch-recovery-node]').length),
                    body: document.body ? document.body.innerText.slice(0, 2200) : '',
                  };
                })()
                """,
                timeout_seconds=60,
                interval_seconds=0.5,
            )
            if not isinstance(state, dict):
                raise RuntimeError(f"Computer watch summary was not visible: {state}")
            if "常驻接单" not in str(state.get("text") or ""):
                issues.append("summary_missing_runner_watch_language")
            if str(state.get("queuedCount") or "") == "":
                issues.append("summary_missing_queued_command_count")
            blocked_count = int(str(state.get("blockedCount") or "0") or "0")
            recovery_count = int(str(state.get("recoveryCount") or "0") or "0")
            if blocked_count and recovery_count < blocked_count:
                issues.append("watch_recovery_buttons_missing_for_blocked_nodes")

            shot = output_dir / f"computer-watch-summary-02-computers-{stamp}.png"
            flow.screenshot(shot)
            screenshots["computers"] = str(shot)

            if blocked_count:
                opened = flow.eval(
                    """
                    (() => {
                      const button = document.querySelector('[data-computer-watch-recovery-node]');
                      if (!button) return false;
                      button.scrollIntoView({ block: 'center', inline: 'center' });
                      button.click();
                      return true;
                    })()
                    """,
                )
                if not opened:
                    issues.append("watch_recovery_button_could_not_be_clicked")
                else:
                    drawer_state = flow.wait_for(
                        """
                        (() => {
                          const command = document.querySelector('[data-computer-watch-command]');
                          if (!command) return false;
                          return {
                            node: command.getAttribute('data-computer-watch-command') || '',
                            text: (command.textContent || '').slice(0, 600),
                          };
                        })()
                        """,
                        timeout_seconds=45,
                        interval_seconds=0.5,
                    )
                    if not isinstance(drawer_state, dict) or "-Watch" not in str(drawer_state.get("text") or ""):
                        issues.append("watch_recovery_drawer_missing_watch_command")
                    drawer_shot = output_dir / f"computer-watch-summary-03-watch-command-{stamp}.png"
                    flow.screenshot(drawer_shot)
                    screenshots["watch_command"] = str(drawer_shot)

    finally:
        import shutil

        shutil.rmtree(runtime_dir, ignore_errors=True)

    report = {
        "stamp": stamp,
        "project_id": args.project_id,
        "screenshots": screenshots,
        "issues": issues,
        "validated": "computer-watch-summary",
    }
    report_path = output_dir / f"computer-watch-summary-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), "screenshots": screenshots, "issues": issues}, ensure_ascii=False))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
