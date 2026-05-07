from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

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

api_login = dual_helper.api_login
request_json = dual_helper.request_json

API_BASE = onboarding.API_BASE
WEB_BASE = onboarding.WEB_BASE
OWNER_EMAIL = onboarding.OWNER_EMAIL
OWNER_PASSWORD = onboarding.OWNER_PASSWORD
PROJECT_ID = "7f2d9a27-cecf-4e61-af25-3792c24971e6"


def fetch_text(url: str, *, token: str) -> str:
    request = Request(
        url,
        headers={
            "Cookie": f"farm_access_token={token}",
            "Accept": "text/html",
        },
        method="GET",
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="computer-thread-visibility-http-"))
    computer_id = f"thread-http-{stamp[-6:]}"
    computer_label = f"Thread HTTP {stamp[-6:]}"
    runner_id = f"runner-http-{stamp[-6:]}"
    runner_name = f"Runner HTTP {stamp[-6:]}"
    html_dump_path = OUTPUT_DIR / f"computer-thread-visibility-html-{stamp}.html"

    report: dict[str, object] = {
        "stamp": stamp,
        "project_id": PROJECT_ID,
        "computer_id": computer_id,
        "runner_id": runner_id,
        "html_dump": str(html_dump_path),
        "issues": [],
    }

    token, _user = api_login(API_BASE, OWNER_EMAIL, OWNER_PASSWORD)

    try:
        request_json(
            f"{API_BASE.rstrip('/')}/api/collaboration/projects/{PROJECT_ID}/computer-nodes",
            method="POST",
            headers={"Authorization": f"Bearer {token}"},
            payload={
                "id": computer_id,
                "label": computer_label,
                "status": "online",
                "connection_kind": "remote",
                "workspace_root": str(REPO_ROOT),
                "git_root": str(REPO_ROOT),
                "metadata": {"source": "thread_visibility_http_validation"},
            },
        )

        pairing = request_json(
            f"{API_BASE.rstrip('/')}/api/collaboration/projects/{PROJECT_ID}/computer-nodes/{computer_id}/pairing-token",
            method="POST",
            headers={"Authorization": f"Bearer {token}"},
            payload={},
        )
        pairing_token = str((pairing.get("data") or {}).get("token") or "").strip()
        if not pairing_token:
            raise RuntimeError("Pairing token missing from API response")
        report["pairing_token_tail"] = pairing_token[-8:]

        register_result = onboarding.run_powershell_script(
            "register-runner.ps1",
            "-Server",
            API_BASE,
            "-PairingToken",
            pairing_token,
            "-ComputerNodeId",
            computer_id,
            "-RunnerName",
            runner_name,
            "-RunnerId",
            runner_id,
        )
        if int(register_result.get("returncode", 1)) != 0:
            raise RuntimeError(f"register-runner failed: {register_result}")
        report["register_returncode"] = register_result["returncode"]

        sync_result = onboarding.run_powershell_script(
            "sync-codex-session-threads.ps1",
            "-Server",
            API_BASE,
            "-RunnerId",
            runner_id,
            "-ProjectId",
            PROJECT_ID,
            "-ComputerNodeId",
            computer_id,
        )
        if int(sync_result.get("returncode", 1)) != 0:
            raise RuntimeError(f"sync-codex-session-threads failed: {sync_result}")
        report["sync_returncode"] = sync_result["returncode"]

        workstations_payload = request_json(
            f"{API_BASE.rstrip('/')}/api/collaboration/projects/{PROJECT_ID}/thread-workstations",
            headers={"Authorization": f"Bearer {token}"},
        )
        workstations = workstations_payload.get("data") if isinstance(workstations_payload, dict) else []
        synced_threads = [
            item
            for item in (workstations if isinstance(workstations, list) else [])
            if isinstance(item, dict)
            and str(item.get("computer_node_id") or item.get("computer_node") or "").strip() == computer_id
        ]
        report["api_thread_count"] = len(synced_threads)

        html = fetch_text(
            f"{WEB_BASE.rstrip('/')}/projects/{PROJECT_ID}?panel=team&tab=computers&computer={computer_id}",
            token=token,
        )
        html_dump_path.write_text(html, encoding="utf-8")

        section_match = re.search(
            rf'<section[^>]*data-computer-thread-preview-for="{re.escape(computer_id)}"[^>]*>(.*?)</section>',
            html,
            re.DOTALL,
        )
        if not section_match:
            raise RuntimeError("Could not find computer thread preview section in HTML")
        section_html = section_match.group(1)
        rendered_count = len(re.findall(r"data-computer-thread-item=", section_html))
        badge_html = re.sub(r"<!--.*?-->", "", section_html, flags=re.DOTALL)
        badge_match = re.search(r"<span[^>]*>\s*(\d+)\s*条\s*</span>", badge_html)
        badge_count = int(badge_match.group(1)) if badge_match else rendered_count
        report["html_badge_count"] = badge_count
        report["html_rendered_count"] = rendered_count

        if report["api_thread_count"] != rendered_count:
            report["issues"].append(
                f"rendered thread count mismatch: api={report['api_thread_count']} html={rendered_count}"
            )
        if badge_count != rendered_count:
            report["issues"].append(
                f"badge/rendered mismatch: badge={badge_count} html={rendered_count}"
            )
        if rendered_count <= 6:
            report["issues"].append(
                f"expected more than 6 rendered threads for regression coverage, got {rendered_count}"
            )

        report_path = OUTPUT_DIR / f"computer-thread-visibility-http-report-{stamp}.json"
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
