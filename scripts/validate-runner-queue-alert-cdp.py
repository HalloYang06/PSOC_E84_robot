from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
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
        description="Validate the map-level runner queue blocker alert and its jump to computer management.",
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
    runtime_dir = Path(tempfile.mkdtemp(prefix="runner-queue-alert-"))
    screenshots: dict[str, str] = {}
    issues: list[str] = []

    try:
        profile_dir = new_browser_profile(runtime_dir, "owner")
        with BrowserRuntime(find_free_port(), profile_dir, args.viewport_width, args.viewport_height) as flow:
            login_shot = output_dir / f"runner-queue-alert-01-login-{stamp}.png"
            login_via_ui(flow, web_base, email=args.login_email, password=args.login_password, shot=login_shot)
            screenshots["login"] = str(login_shot)

            flow.navigate(f"{web_base}/projects/{args.project_id}")
            alert_state = flow.wait_for(
                """
                (() => {
                  const alert = document.querySelector('[data-runner-queue-alert="true"]');
                  if (!alert) return false;
                  return {
                    text: (alert.textContent || '').trim(),
                    queuedCount: alert.getAttribute('data-runner-queue-count') || '',
                    readyCount: alert.getAttribute('data-runner-watch-ready-count') || '',
                    blockedCount: alert.getAttribute('data-runner-watch-blocked-count') || '',
                    hardBlocker: alert.getAttribute('data-runner-queue-hard-blocker') || '',
                    href: location.href,
                  };
                })()
                """,
                timeout_seconds=60,
                interval_seconds=0.5,
            )
            if not isinstance(alert_state, dict):
                raise RuntimeError(f"Runner queue alert did not become visible: {alert_state}")
            alert_text = str(alert_state.get("text") or "")
            if "接单阻塞" not in alert_text and "接单提醒" not in alert_text:
                issues.append("alert_missing_runner_queue_language")
            if not str(alert_state.get("queuedCount") or "") or str(alert_state.get("queuedCount") or "") == "0":
                issues.append("alert_queued_count_missing")

            flow.wait_for_selector('iframe[src*="harvest-moon-phaser3-game/index.html"]', timeout_seconds=45)
            time.sleep(4)
            shot = output_dir / f"runner-queue-alert-02-map-{stamp}.png"
            flow.screenshot(shot)
            screenshots["map"] = str(shot)

            flow.click_text("接单", selector='[data-runner-queue-alert="true"]', timeout_seconds=20)

            panel_state = flow.wait_for(
                """
                (() => {
                  const panel = document.querySelector('#project-main-panel');
                  const summary = document.querySelector('[data-computer-watch-summary="true"]');
                  if (!panel || !summary) return false;
                  return {
                    panelText: (panel.textContent || '').slice(0, 1600),
                    queuedCount: summary.getAttribute('data-computer-queued-command-count') || '',
                  };
                })()
                """,
                timeout_seconds=60,
                interval_seconds=0.5,
            )
            if not isinstance(panel_state, dict):
                raise RuntimeError(f"Clicking alert did not open computer management: {panel_state}")

            shot = output_dir / f"runner-queue-alert-03-computers-{stamp}.png"
            flow.screenshot(shot)
            screenshots["computers"] = str(shot)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    report = {
        "stamp": stamp,
        "project_id": args.project_id,
        "screenshots": screenshots,
        "issues": issues,
        "validated": "runner-queue-alert",
    }
    report_path = output_dir / f"runner-queue-alert-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), "screenshots": screenshots, "issues": issues}, ensure_ascii=False))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
