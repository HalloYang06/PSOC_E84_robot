from __future__ import annotations

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
COLLAB_HELPER_PATH = SCRIPT_DIR / "validate-ui-frontdoor-collab-cdp.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("ui_frontdoor_collab_helper", COLLAB_HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module: {COLLAB_HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load_helper()

WEB_BASE = "http://127.0.0.1:3000"
MAIN_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
OWNER_EMAIL = "codex-platform-npc@local.dev"
OWNER_PASSWORD = "password"


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = REPO_ROOT / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="exchange-receipt-rounds-", dir=str(output_dir)))
    report: dict[str, object] = {
        "stamp": stamp,
        "project_id": MAIN_PROJECT_ID,
        "screenshots": {},
        "steps": {},
    }

    try:
        with helper.BrowserRuntime(helper.find_free_port(), helper.new_browser_profile(runtime_dir, "owner"), 1720, 1080) as flow:
            shot_login = output_dir / f"exchange-receipt-rounds-01-login-{stamp}.png"
            helper.login_via_ui(flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=shot_login)
            report["screenshots"]["login"] = str(shot_login)

            flow.navigate(f"{WEB_BASE}/projects/{MAIN_PROJECT_ID}?panel=team&tab=exchange&exchange_section=receipts")
            flow.wait_for_selector('[data-exchange-section="receipts"]', timeout_seconds=45)
            state_all = flow.wait_for(
                """
                (() => {
                  const rounds = Array.from(document.querySelectorAll('[data-exchange-receipt-round]')).map((item) => ({
                    title: item.getAttribute('data-exchange-receipt-round') || '',
                    status: item.getAttribute('data-exchange-receipt-round-status') || '',
                    validation: item.getAttribute('data-exchange-receipt-round-validation') || '',
                    text: (item.textContent || '').trim(),
                  }));
                  const filters = Array.from(document.querySelectorAll('[data-exchange-receipt-filter]')).map((item) => ({
                    id: item.getAttribute('data-exchange-receipt-filter') || '',
                    active: item.getAttribute('data-exchange-receipt-filter-active') || '',
                    text: (item.textContent || '').trim(),
                  }));
                  const receiptItems = Array.from(document.querySelectorAll('[data-exchange-receipt-item]')).map((item) => ({
                    title: item.getAttribute('data-exchange-receipt-title') || '',
                    kind: item.getAttribute('data-exchange-receipt-kind') || '',
                  }));
                  const hasTimeline = !!document.querySelector('[data-receipt-step-state]');
                  return rounds.length && filters.length >= 4 && hasTimeline
                    ? { rounds, filters, receiptItems, href: location.href }
                    : false;
                })()
                """,
                timeout_seconds=45,
                interval_seconds=0.4,
            )
            report["steps"]["all_rounds"] = state_all
            shot_all = output_dir / f"exchange-receipt-rounds-02-all-{stamp}.png"
            flow.screenshot(shot_all)
            report["screenshots"]["all_rounds"] = str(shot_all)

            flow.click_text("隐藏验收", selector='[data-exchange-receipt-filter]')
            state_clean = flow.wait_for(
                """
                (() => {
                  const active = document.querySelector('[data-exchange-receipt-filter="clean"]');
                  const rounds = Array.from(document.querySelectorAll('[data-exchange-receipt-round]')).map((item) => ({
                    title: item.getAttribute('data-exchange-receipt-round') || '',
                    validation: item.getAttribute('data-exchange-receipt-round-validation') || '',
                    text: (item.textContent || '').trim(),
                  }));
                  return active && active.getAttribute('data-exchange-receipt-filter-active') === 'true'
                    ? { activeText: active.textContent || '', rounds, href: location.href }
                    : false;
                })()
                """,
                timeout_seconds=20,
                interval_seconds=0.3,
            )
            report["steps"]["clean_filter"] = state_clean
            shot_clean = output_dir / f"exchange-receipt-rounds-03-clean-filter-{stamp}.png"
            flow.screenshot(shot_clean)
            report["screenshots"]["clean_filter"] = str(shot_clean)

        report["verdict"] = "passed"
        report_path = output_dir / f"exchange-receipt-rounds-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"verdict": "passed", "report_path": str(report_path), "screenshots": report["screenshots"]}, ensure_ascii=False, indent=2))
        return 0
    finally:
        import shutil

        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
