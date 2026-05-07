from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
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

WEB_BASE = onboarding.WEB_BASE
API_BASE = onboarding.API_BASE
VIEWPORT_WIDTH = onboarding.VIEWPORT_WIDTH
VIEWPORT_HEIGHT = onboarding.VIEWPORT_HEIGHT
OWNER_EMAIL = onboarding.OWNER_EMAIL
OWNER_PASSWORD = onboarding.OWNER_PASSWORD

PROJECT_ID = "78151f5f-f08c-4e83-b0fc-9be89263ecb3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that creating a computer clears the UI loading overlay and renders the node.",
    )
    parser.add_argument("--web-base", default=WEB_BASE)
    parser.add_argument("--api-base", default=API_BASE)
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--login-email", default=OWNER_EMAIL)
    parser.add_argument("--login-password", default=OWNER_PASSWORD)
    parser.add_argument("--viewport-width", type=int, default=VIEWPORT_WIDTH)
    parser.add_argument("--viewport-height", type=int, default=VIEWPORT_HEIGHT)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def configure_onboarding_helper(args: argparse.Namespace) -> None:
    onboarding.WEB_BASE = args.web_base.rstrip("/")
    onboarding.API_BASE = args.api_base.rstrip("/")
    onboarding.VIEWPORT_WIDTH = args.viewport_width
    onboarding.VIEWPORT_HEIGHT = args.viewport_height
    onboarding.OWNER_EMAIL = args.login_email
    onboarding.OWNER_PASSWORD = args.login_password


def main() -> int:
    args = parse_args()
    configure_onboarding_helper(args)
    web_base = args.web_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    project_id = args.project_id
    owner_email = args.login_email
    owner_password = args.login_password
    output_dir = Path(args.output_dir)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="computer-create-spinner-"))
    computer_id = f"create-check-{stamp[-6:]}"
    computer_label = f"Create Spinner Check {stamp[-6:]}"
    workspace_root = str(runtime_dir / "workspace")

    report: dict[str, object] = {
        "stamp": stamp,
        "project_id": project_id,
        "computer_id": computer_id,
        "screenshots": {},
        "issues": [],
    }

    token, _owner = api_login(api_base, owner_email, owner_password)

    try:
        profile_dir = new_browser_profile(runtime_dir, "owner")
        with BrowserRuntime(find_free_port(), profile_dir, args.viewport_width, args.viewport_height) as flow:
            shot = output_dir / f"computer-create-spinner-01-login-{stamp}.png"
            login_via_ui(flow, web_base, email=owner_email, password=owner_password, shot=shot)
            report["screenshots"]["login"] = str(shot)

            shot = output_dir / f"computer-create-spinner-02-before-submit-{stamp}.png"
            create_state = create_computer_via_ui(
                flow,
                web_base,
                project_id=project_id,
                computer_id=computer_id,
                label=computer_label,
                workspace_root=workspace_root,
                git_root=workspace_root,
                shot=shot,
            )
            report["create_computer"] = create_state
            report["screenshots"]["before_submit"] = str(shot)

            panel_state = flow.wait_for(
                """
                (() => {
                  const panel = document.querySelector('#project-main-panel');
                  if (!panel) return false;
                  const busy = panel.getAttribute('data-busy') || '';
                  const overlay = panel.querySelector('[role="status"]');
                  const successBanner = Array.from(panel.querySelectorAll('div')).find((item) => {
                    const value = item.textContent || '';
                    return value.includes('已登记电脑') || value.includes('Create Spinner Check');
                  });
                  return busy === 'false'
                    ? {
                        busy,
                        overlayVisible: Boolean(overlay),
                        successText: successBanner ? (successBanner.textContent || '').trim() : '',
                        href: location.href,
                        body: document.body ? document.body.innerText.slice(0, 1600) : '',
                      }
                    : false;
                })()
                """,
                timeout_seconds=25,
                interval_seconds=0.3,
            )
            if not isinstance(panel_state, dict):
                raise RuntimeError(f"Pending overlay did not clear after computer create: {panel_state}")
            report["panel_state_after_create"] = panel_state
            if panel_state.get("overlayVisible"):
                report["issues"].append("overlay_still_visible_after_create")
            panel_text = f"{panel_state.get('successText') or ''}\n{panel_state.get('body') or ''}"
            if "已登记电脑" not in panel_text and computer_id not in panel_text and computer_label not in panel_text:
                report["issues"].append("missing_success_notice_after_create")

            shot = output_dir / f"computer-create-spinner-03-after-create-{stamp}.png"
            flow.screenshot(shot)
            report["screenshots"]["after_create"] = str(shot)

        report_path = output_dir / f"computer-create-spinner-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report_path": str(report_path), "issues": report["issues"]}, ensure_ascii=False))
        return 0 if not report["issues"] else 1
    finally:
        try:
            request_json(
                f"{api_base}/api/collaboration/projects/{project_id}/computer-nodes/{computer_id}",
                method="DELETE",
                headers={"Authorization": f"Bearer {token}"},
            )
        except Exception:
            report.setdefault("issues", []).append("cleanup_delete_computer_failed")
        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
