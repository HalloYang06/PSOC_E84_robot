from __future__ import annotations

import importlib.util
import argparse
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that a computer's scanned threads are visible in the project computer panel.",
    )
    parser.add_argument("--api-base", default=API_BASE)
    parser.add_argument("--web-base", default=WEB_BASE)
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--login-email", default=OWNER_EMAIL)
    parser.add_argument("--login-password", default=OWNER_PASSWORD)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


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


def browser_thread_preview(
    *,
    web_base: str,
    project_id: str,
    computer_id: str,
    token: str,
    output_dir: Path,
    stamp: str,
) -> dict[str, object]:
    screenshot_path = output_dir / f"computer-thread-visibility-browser-{stamp}.png"
    node_code = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const browser = await chromium.launch({{ headless: true }});
  const context = await browser.newContext({{ viewport: {{ width: 1440, height: 1000 }} }});
  await context.addCookies([{{
    name: 'farm_access_token',
    value: {json.dumps(token)},
    url: {json.dumps(web_base.rstrip('/') + '/')},
    sameSite: 'Lax'
  }}]);
  const page = await context.newPage();
  const url = `${{ {json.dumps(web_base.rstrip('/'))} }}/projects/${{ {json.dumps(project_id)} }}/2d-upgrade?panel=machine-room&action=thread-list&computer=${{ {json.dumps(computer_id)} }}`;
  await page.goto(url, {{ waitUntil: 'networkidle', timeout: 45000 }}).catch(async () => {{
    await page.goto(url, {{ waitUntil: 'domcontentloaded', timeout: 45000 }});
  }});
  await page.waitForTimeout(1800);
  const selector = `[data-computer-thread-preview-for="${{ {json.dumps(computer_id)} }}"]`;
  const section = await page.locator(selector).first();
  const sectionCount = await section.count();
  const result = await page.evaluate((computerId) => {{
    const section = document.querySelector(`[data-computer-thread-preview-for="${{computerId}}"]`);
    const items = section ? Array.from(section.querySelectorAll('[data-computer-thread-item]')) : [];
    const countEl = section ? section.querySelector('[data-computer-thread-rendered-count]') : null;
    return {{
      url: location.href,
      sectionFound: Boolean(section),
      renderedCount: items.length,
      renderedAttrCount: countEl ? Number(countEl.getAttribute('data-computer-thread-rendered-count') || '0') : 0,
      text: section ? section.innerText : document.body.innerText.slice(0, 1200),
      overflowX: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
    }};
  }}, {json.dumps(computer_id)});
  await page.screenshot({{ path: {json.dumps(str(screenshot_path))}, fullPage: true }});
  await browser.close();
  result.sectionCount = sectionCount;
  result.screenshot = {json.dumps(str(screenshot_path))};
  console.log(JSON.stringify(result));
}})().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""
    completed = subprocess.run(
        ["node", "-e", node_code],
        cwd=str(REPO_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=70,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"browser thread preview failed: {(completed.stderr or '').strip() or (completed.stdout or '').strip()}")
    return json.loads(completed.stdout.strip().splitlines()[-1])


def request_runner_json(
    url: str,
    *,
    runner_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Runner-Id": runner_id,
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else {}


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    web_base = args.web_base.rstrip("/")
    project_id = args.project_id
    output_dir = Path(args.output_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="computer-thread-visibility-http-"))
    computer_id = f"thread-http-{stamp[-6:]}"
    computer_label = f"Thread HTTP {stamp[-6:]}"
    runner_id = f"runner-http-{stamp[-6:]}"
    runner_name = f"Runner HTTP {stamp[-6:]}"
    html_dump_path = output_dir / f"computer-thread-visibility-html-{stamp}.html"
    synthetic_thread_ids = [f"{computer_id}-thread-{index:02d}" for index in range(1, 10)]
    created_thread_ids: list[str] = []
    token = ""

    report: dict[str, object] = {
        "stamp": stamp,
        "project_id": project_id,
        "computer_id": computer_id,
        "runner_id": runner_id,
        "html_dump": str(html_dump_path),
        "issues": [],
    }

    try:
        token, _user = api_login(api_base, args.login_email, args.login_password)
        request_json(
            f"{api_base}/api/collaboration/projects/{project_id}/computer-nodes",
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
            f"{api_base}/api/collaboration/projects/{project_id}/computer-nodes/{computer_id}/pairing-token",
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
            api_base,
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

        synthetic_threads = [
            {
                "workstation_id": synthetic_thread_ids[index - 1],
                "workstation_name": f"可见性验收线程 {index:02d}",
                "workstation_status": "active",
                "cwd": str(REPO_ROOT),
                "model": "gpt-5.4",
                "description": "Synthetic thread slot for computer visibility validation",
                "notes": "Created by validate-computer-thread-visibility-http.py; safe to delete with the computer node.",
                "ai_provider_id": "codex",
            }
            for index in range(1, 10)
        ]
        sync_payload = {
            "project_id": project_id,
            "computer_node_id": computer_id,
            "workstations": synthetic_threads,
        }
        sync_response = request_runner_json(
            f"{api_base}/api/runners/{runner_id}/thread-workstations/sync",
            runner_id=runner_id,
            payload=sync_payload,
        )
        sync_data = sync_response.get("data") if isinstance(sync_response, dict) else {}
        report["sync_thread_count"] = int((sync_data or {}).get("thread_count") or 0) if isinstance(sync_data, dict) else 0
        if report["sync_thread_count"] != len(synthetic_threads):
            raise RuntimeError(f"synthetic thread sync count mismatch: {sync_response}")
        created_thread_ids = list(synthetic_thread_ids)

        workstations_payload = request_json(
            f"{api_base}/api/collaboration/projects/{project_id}/thread-workstations",
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

        page_url = f"{web_base}/projects/{project_id}?panel=team&tab=computers&computer={computer_id}"
        html = fetch_text(page_url, token=token)
        html_dump_path.write_text(html, encoding="utf-8")

        section_match = re.search(
            rf'<section[^>]*data-computer-thread-preview-for="{re.escape(computer_id)}"[^>]*>(.*?)</section>',
            html,
            re.DOTALL,
        )
        browser_preview: dict[str, object] | None = None
        if section_match:
            section_html = section_match.group(1)
            rendered_count = len(re.findall(r"data-computer-thread-item=", section_html))
            badge_html = re.sub(r"<!--.*?-->", "", section_html, flags=re.DOTALL)
            badge_match = re.search(r"<span[^>]*>\s*(\d+)\s*条\s*</span>", badge_html)
            badge_count = int(badge_match.group(1)) if badge_match else rendered_count
        else:
            browser_preview = browser_thread_preview(
                web_base=web_base,
                project_id=project_id,
                computer_id=computer_id,
                token=token,
                output_dir=output_dir,
                stamp=stamp,
            )
            report["browser_preview"] = browser_preview
            rendered_count = int(browser_preview.get("renderedCount") or 0)
            badge_count = int(browser_preview.get("renderedAttrCount") or rendered_count)
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

        report_path = output_dir / f"computer-thread-visibility-http-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report_path": str(report_path), "issues": report["issues"]}, ensure_ascii=False))
        return 0 if not report["issues"] else 1
    except Exception as exc:  # noqa: BLE001
        report.setdefault("issues", []).append(str(exc))
        return_code = 1
        return return_code
    finally:
        cleanup_threads: list[dict[str, object]] = []
        if token:
            for thread_id in created_thread_ids or synthetic_thread_ids:
                try:
                    cleanup_payload = request_json(
                        f"{api_base}/api/collaboration/projects/{project_id}/thread-workstations/{thread_id}",
                        method="DELETE",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    cleanup_threads.append({"id": thread_id, "status": "ok", "payload": cleanup_payload})
                except Exception as exc:  # noqa: BLE001
                    cleanup_threads.append({"id": thread_id, "status": "warning", "message": str(exc)})
            report["cleanup_threads"] = cleanup_threads
            try:
                request_json(
                    f"{api_base}/api/collaboration/projects/{project_id}/computer-nodes/{computer_id}",
                    method="DELETE",
                    headers={"Authorization": f"Bearer {token}"},
                )
            except Exception:
                report.setdefault("issues", []).append("cleanup_delete_computer_failed")
        report_path = output_dir / f"computer-thread-visibility-http-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if report.get("issues"):
            print(json.dumps({"report_path": str(report_path), "issues": report["issues"]}, ensure_ascii=False))
        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
