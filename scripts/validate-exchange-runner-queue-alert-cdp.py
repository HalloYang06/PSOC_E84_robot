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
from urllib import request as urlrequest
from urllib.parse import urlparse

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
new_browser_profile = dual_helper.new_browser_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate runner queue blocker alerts inside the collaboration exchange panel.",
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="78151f5f-f08c-4e83-b0fc-9be89263ecb3")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--viewport-width", type=int, default=1720)
    parser.add_argument("--viewport-height", type=int, default=1080)
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts"))
    return parser.parse_args()


def authenticate(api_base: str, email: str, password: str) -> dict[str, object]:
    payload = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urlrequest.Request(
        f"{api_base.rstrip('/')}/api/auth/session",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    body = json.loads(raw)
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not data.get("access_token"):
        raise RuntimeError("Auth response did not include access_token")
    return data


def set_auth_cookies(flow: object, web_base: str, session: dict[str, object]) -> None:
    parsed = urlparse(web_base)
    origin = f"{parsed.scheme or 'http'}://{parsed.netloc or '127.0.0.1:3000'}"
    token = str(session.get("access_token") or "")
    user_json = json.dumps(session.get("user") or {}, ensure_ascii=True)
    result = flow.cdp.send(
        "Network.setCookie",
        {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
    )
    if not result.get("success"):
        raise RuntimeError("Failed to set farm_access_token")
    flow.cdp.send(
        "Network.setCookie",
        {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
    )


def read_alert(flow: object, selector: str) -> dict[str, str]:
    state = flow.wait_for(
        f"""
        (() => {{
          const alert = document.querySelector({json.dumps(selector)});
          if (!alert) return false;
          return {{
            text: (alert.textContent || '').replace(/\\s+/g, ' ').trim(),
            queuedCount: alert.getAttribute('data-exchange-runner-queue-count') || '',
            readyCount: alert.getAttribute('data-exchange-runner-ready-count') || '',
            blockedCount: alert.getAttribute('data-exchange-runner-blocked-count') || '',
            hardBlocker: alert.getAttribute('data-exchange-runner-hard-blocker') || '',
            href: location.href,
          }};
        }})()
        """,
        timeout_seconds=60,
        interval_seconds=0.5,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Alert did not become visible for {selector}: {state}")
    return {str(key): str(value) for key, value in state.items()}


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    runtime_dir = Path(tempfile.mkdtemp(prefix="exchange-runner-queue-alert-"))
    screenshots: dict[str, str] = {}
    issues: list[str] = []
    states: dict[str, dict[str, str]] = {}

    try:
        profile_dir = new_browser_profile(runtime_dir, "owner")
        with BrowserRuntime(find_free_port(), profile_dir, args.viewport_width, args.viewport_height) as flow:
            session = authenticate(args.api_base, args.login_email, args.login_password)
            set_auth_cookies(flow, web_base, session)

            overview_url = f"{web_base}/projects/{args.project_id}?panel=team&tab=exchange&exchange_section=overview"
            flow.navigate(overview_url)
            flow.wait_for_selector('[data-exchange-section="overview"]', timeout_seconds=60)
            overview_state = read_alert(flow, '[data-exchange-runner-queue-alert="true"]')
            states["overview"] = overview_state
            if not overview_state.get("queuedCount") or overview_state.get("queuedCount") == "0":
                issues.append("overview_queued_count_missing")
            if "接单阻塞" not in overview_state.get("text", "") and "接单提醒" not in overview_state.get("text", ""):
                issues.append("overview_missing_queue_attention_language")

            stale_queue_state = flow.eval(
                """
                (() => {
                  const card = document.querySelector('[data-exchange-stale-queue-guidance="true"]');
                  if (!card) return null;
                  return {
                    count: card.getAttribute('data-exchange-stale-queue-count') || '',
                    oldestAge: card.getAttribute('data-exchange-oldest-queue-age') || '',
                    text: (card.textContent || '').replace(/\\s+/g, ' ').trim(),
                  };
                })()
                """,
            )
            if int(overview_state.get("queuedCount") or "0") > 0:
                if not isinstance(stale_queue_state, dict):
                    issues.append("overview_stale_queue_guidance_missing")
                else:
                    states["stale_queue_guidance"] = {str(k): str(v) for k, v in stale_queue_state.items()}
                    if not states["stale_queue_guidance"].get("count") or states["stale_queue_guidance"].get("count") == "0":
                        issues.append("overview_stale_queue_count_missing")

            overview_shot = output_dir / f"exchange-runner-queue-alert-02-overview-{stamp}.png"
            flow.screenshot(overview_shot)
            screenshots["overview"] = str(overview_shot)

            if int(overview_state.get("queuedCount") or "0") > 0:
                opened_queue_drawer = flow.eval(
                    """
                    (() => {
                      const button = document.querySelector('[data-exchange-stale-queue-open-oldest="true"]');
                      if (!button) return false;
                      button.scrollIntoView({ block: 'center', inline: 'center' });
                      button.click();
                      return true;
                    })()
                    """,
                )
                if not opened_queue_drawer:
                    issues.append("overview_stale_queue_open_oldest_missing")
                else:
                    queue_drawer_state = flow.wait_for(
                        """
                        (() => {
                          const drawer = document.querySelector('[data-manager-drawer-kind="exchange-detail"]');
                          const actions = document.querySelector('[data-exchange-stale-queue-actions]');
                          if (!drawer || !actions) return false;
                          return {
                            messageId: actions.getAttribute('data-exchange-stale-queue-actions') || '',
                            text: (actions.textContent || '').replace(/\\s+/g, ' ').trim(),
                            keep: !!actions.querySelector('[data-exchange-stale-queue-action="keep"]'),
                            expire: !!actions.querySelector('[data-exchange-stale-queue-action="expire"]'),
                            requeue: !!actions.querySelector('[data-exchange-stale-queue-action="requeue"]'),
                          };
                        })()
                        """,
                        timeout_seconds=60,
                        interval_seconds=0.5,
                    )
                    if not isinstance(queue_drawer_state, dict):
                        issues.append("overview_stale_queue_actions_missing")
                    else:
                        states["stale_queue_actions"] = {str(k): str(v) for k, v in queue_drawer_state.items()}
                        if states["stale_queue_actions"].get("keep") != "True":
                            issues.append("stale_queue_keep_action_missing")
                        if states["stale_queue_actions"].get("expire") != "True":
                            issues.append("stale_queue_expire_action_missing")
                    queue_drawer_shot = output_dir / f"exchange-runner-queue-alert-05-stale-queue-actions-{stamp}.png"
                    flow.screenshot(queue_drawer_shot)
                    screenshots["stale_queue_actions"] = str(queue_drawer_shot)
                    flow.navigate(overview_url)
                    flow.wait_for_selector('[data-exchange-section="overview"]', timeout_seconds=60)

            clicked = flow.eval(
                """
                (() => {
                  const alert = document.querySelector('[data-exchange-runner-queue-alert="true"]');
                  const button = alert && Array.from(alert.querySelectorAll('button')).find((item) =>
                    ((item.textContent || '')).includes('接单') || ((item.textContent || '')).includes('阻塞')
                  );
                  if (!button) return false;
                  button.scrollIntoView({ block: 'center', inline: 'center' });
                  button.click();
                  return true;
                })()
                """,
            )
            if not clicked:
                issues.append("overview_restore_button_missing")
            else:
                computer_state = flow.wait_for(
                    """
                    (() => {
                      const summary = document.querySelector('[data-computer-watch-summary="true"]');
                      if (!summary) return false;
                      return {
                        queuedCount: summary.getAttribute('data-computer-queued-command-count') || '',
                        readyCount: summary.getAttribute('data-computer-watch-ready-count') || '',
                      };
                    })()
                    """,
                    timeout_seconds=60,
                    interval_seconds=0.5,
                )
                if not isinstance(computer_state, dict):
                    issues.append("overview_restore_button_did_not_open_computers")
                else:
                    states["computer_summary_after_click"] = {str(k): str(v) for k, v in computer_state.items()}
                    computer_shot = output_dir / f"exchange-runner-queue-alert-03-computers-{stamp}.png"
                    flow.screenshot(computer_shot)
                    screenshots["computers_after_click"] = str(computer_shot)

            dispatch_url = f"{web_base}/projects/{args.project_id}?panel=team&tab=exchange&exchange_section=dispatch"
            flow.navigate(dispatch_url)
            flow.wait_for_selector('[data-exchange-section="dispatch"]', timeout_seconds=60)
            dispatch_state = read_alert(flow, '[data-exchange-dispatch-runner-queue-alert="true"]')
            states["dispatch"] = dispatch_state
            if not dispatch_state.get("queuedCount") or dispatch_state.get("queuedCount") == "0":
                issues.append("dispatch_queued_count_missing")
            if "接单阻塞" not in dispatch_state.get("text", "") and "接单提醒" not in dispatch_state.get("text", "") and "目标电脑" not in dispatch_state.get("text", ""):
                issues.append("dispatch_missing_queue_attention_language")

            dispatch_shot = output_dir / f"exchange-runner-queue-alert-04-dispatch-{stamp}.png"
            flow.screenshot(dispatch_shot)
            screenshots["dispatch"] = str(dispatch_shot)
            time.sleep(0.5)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    report = {
        "stamp": stamp,
        "project_id": args.project_id,
        "states": states,
        "screenshots": screenshots,
        "issues": issues,
        "validated": "exchange-runner-queue-alert",
    }
    report_path = output_dir / f"exchange-runner-queue-alert-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), "screenshots": screenshots, "issues": issues}, ensure_ascii=False))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
