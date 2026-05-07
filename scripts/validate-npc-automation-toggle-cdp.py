from __future__ import annotations

import importlib.util
import json
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
HELPER_PATH = SCRIPT_DIR / "validate-ui-frontdoor-collab-cdp.py"

spec = importlib.util.spec_from_file_location("ui_frontdoor_collab_helper", HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load helper module: {HELPER_PATH}")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

BrowserRuntime = helper.BrowserRuntime
find_free_port = helper.find_free_port
new_browser_profile = helper.new_browser_profile
login_via_ui = helper.login_via_ui
api_login = helper.api_login
list_project_messages = helper.list_project_messages
pick_message = helper.pick_message
js_string = helper.js_string
create_agent_command_via_selected_npc = helper.create_agent_command_via_selected_npc

WEB_BASE = "http://127.0.0.1:3000"
API_BASE = "http://127.0.0.1:8010"
OWNER_EMAIL = "lead@example.com"
OWNER_PASSWORD = "password"


def load_latest_fullchain_report() -> dict[str, object]:
    reports = sorted((REPO_ROOT / "artifacts").glob("ui-frontdoor-fullchain-report-*.json"))
    if not reports:
        raise RuntimeError("没有找到前台整链验收报告，无法复用现成的双电脑项目")
    report_path = reports[-1]
    return json.loads(report_path.read_text(encoding="utf-8"))


def create_npc_with_manual_mode(
    flow,
    *,
    project_id: str,
    npc_name: str,
    responsibility: str,
    computer_node_id: str,
    source_workstation_id: str,
    shot_before: Path,
    shot_after: Path,
) -> dict[str, object]:
    flow.navigate(f"{WEB_BASE}/projects/{project_id}?panel=team&tab=npc-create&drawer=npc-create")
    flow.wait_for_selector('[data-npc-create-form] input[name="name"]', timeout_seconds=45)
    flow.fill('[data-npc-create-form] input[name="name"]', npc_name)
    flow.fill('[data-npc-create-form] input[name="responsibility"]', responsibility)
    flow.set_select('[data-npc-create-form] select[name="source_workstation_id"]', source_workstation_id)
    flow.set_select('[data-npc-create-form] select[name="computer_node_id"]', computer_node_id)
    flow.fill(
        '[data-npc-create-form] textarea[name="knowledge_summary"]',
        "这个 NPC 专门用于验证关闭自动化后，只执行当前单条指令。",
    )
    flow.eval(
        """
        (() => {
          const checkbox = document.querySelector('[data-npc-create-form] input[type="checkbox"][name="automation_enabled"]');
          if (!(checkbox instanceof HTMLInputElement)) return false;
          checkbox.checked = false;
          checkbox.dispatchEvent(new Event('input', { bubbles: true }));
          checkbox.dispatchEvent(new Event('change', { bubbles: true }));
          return checkbox.checked === false;
        })()
        """
    )
    flow.screenshot(shot_before)
    flow.submit('[data-npc-create-form]')
    state = flow.wait_for(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-npc-rail-seat]')).find((item) =>
            ((item.textContent || '')).includes({js_string(npc_name)})
          );
          return match
            ? {{
                seatId: match.getAttribute('data-npc-rail-seat') || '',
                railText: match.textContent || '',
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.5,
    )
    flow.screenshot(shot_after)
    return state


def verify_profile_checkbox_off(flow, *, project_id: str, npc_seat_id: str, shot: Path) -> dict[str, object]:
    flow.navigate(
        f"{WEB_BASE}/projects/{project_id}?panel=team&tab=npc-create&seat={npc_seat_id}&drawer=npc-profile&drawer_id={npc_seat_id}"
    )
    flow.wait_for_selector('input[type="checkbox"][name="automation_enabled"]', timeout_seconds=45)
    state = flow.eval(
        """
        (() => {
          const checkbox = document.querySelector('input[type="checkbox"][name="automation_enabled"]');
          if (!(checkbox instanceof HTMLInputElement)) return null;
          return {
            checked: checkbox.checked,
            body: document.body ? document.body.innerText.slice(0, 4000) : '',
          };
        })()
        """
    )
    flow.screenshot(shot)
    return state


def wait_for_receipts(owner_token: str, *, project_id: str, command_title: str, timeout_seconds: float = 60.0) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_messages: list[dict[str, object]] = []
    while time.time() < deadline:
        last_messages = list_project_messages(API_BASE, project_id, owner_token)
        try:
            ack_message = pick_message(last_messages, title=command_title, message_type="agent_ack")
        except RuntimeError:
            ack_message = None
        try:
            result_message = pick_message(last_messages, title=command_title, message_type="agent_result")
        except RuntimeError:
            result_message = None
        if ack_message and result_message:
            return {
                "ack_message": ack_message,
                "result_message": result_message,
                "message_count": len(last_messages),
            }
        time.sleep(2.0)
    raise RuntimeError(
        f"等待单次执行回执超时：{command_title} / 最近消息数 {len(last_messages)}"
    )


def main() -> int:
    source = load_latest_fullchain_report()
    project_id = str(source.get("project_id") or source.get("steps", {}).get("create_project", {}).get("project_id"))
    member_pairing = source.get("steps", {}).get("member_pairing_token", {})
    member_thread_candidates = source.get("steps", {}).get("member_scan_threads", {}).get("after", {}).get("previewThreads", [])
    if not project_id or not member_pairing or not member_thread_candidates:
      raise RuntimeError("前台整链项目上下文不完整，无法复用第二台电脑线程")
    member_computer_id = str(member_pairing.get("pairingNode") or "")
    member_thread_id = str(member_thread_candidates[0])

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = REPO_ROOT / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="npc-automation-toggle-", dir=str(output_dir)))
    npc_name = f"单次执行NPC-{stamp[-6:]}"
    command_title = f"单次执行验证-{stamp[-6:]}"
    command_body = "请只处理这一次指令：先回最小回执，再回复一句说明你当前没有进入持续自动化。"

    report: dict[str, object] = {
        "project_id": project_id,
        "member_computer_id": member_computer_id,
        "member_thread_id": member_thread_id,
        "npc_name": npc_name,
        "command_title": command_title,
        "screenshots": {},
        "steps": {},
        "issues": [],
    }

    owner_token, _owner_user = api_login(API_BASE, OWNER_EMAIL, OWNER_PASSWORD)
    profile_dir = new_browser_profile(runtime_dir, "owner")
    with BrowserRuntime(find_free_port(), profile_dir, 1720, 1080) as flow:
        shot = output_dir / f"npc-automation-toggle-01-login-{stamp}.png"
        login_via_ui(flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=shot)
        report["screenshots"]["login"] = str(shot)

        shot_before = output_dir / f"npc-automation-toggle-02-create-before-{stamp}.png"
        shot_after = output_dir / f"npc-automation-toggle-03-create-after-{stamp}.png"
        created = create_npc_with_manual_mode(
            flow,
            project_id=project_id,
            npc_name=npc_name,
            responsibility="只执行当前单条命令，不持续自动化",
            computer_node_id=member_computer_id,
            source_workstation_id=member_thread_id,
            shot_before=shot_before,
            shot_after=shot_after,
        )
        report["steps"]["create_npc"] = created
        report["screenshots"]["create_before"] = str(shot_before)
        report["screenshots"]["create_after"] = str(shot_after)
        npc_seat_id = str(created.get("seatId") or "")
        if not npc_seat_id:
            raise RuntimeError(f"没有拿到新 NPC 的 seatId：{created}")

        shot_profile = output_dir / f"npc-automation-toggle-04-profile-{stamp}.png"
        profile_state = verify_profile_checkbox_off(flow, project_id=project_id, npc_seat_id=npc_seat_id, shot=shot_profile)
        report["steps"]["profile_state"] = profile_state
        report["screenshots"]["profile"] = str(shot_profile)
        if not isinstance(profile_state, dict) or profile_state.get("checked") is not False:
            raise RuntimeError(f"NPC 属性页自动化开关没有保持关闭：{profile_state}")

        shot_preview = output_dir / f"npc-automation-toggle-05-preview-{stamp}.png"
        shot_sent = output_dir / f"npc-automation-toggle-06-sent-{stamp}.png"
        command_state = create_agent_command_via_selected_npc(
            flow,
            project_id=project_id,
            npc_seat_id=npc_seat_id,
            command_title=command_title,
            command_body=command_body,
            shot_preview=shot_preview,
            shot_sent=shot_sent,
        )
        report["steps"]["command_state"] = command_state
        report["screenshots"]["preview"] = str(shot_preview)
        report["screenshots"]["sent"] = str(shot_sent)

        receipts = wait_for_receipts(owner_token, project_id=project_id, command_title=command_title)
        report["steps"]["receipts"] = receipts

        shot_receipts = output_dir / f"npc-automation-toggle-07-receipts-{stamp}.png"
        flow.navigate(f"{WEB_BASE}/projects/{project_id}?panel=team&tab=exchange&exchange_section=receipts")
        flow.wait_for_selector('[data-exchange-receipt-item], [data-exchange-section="receipts"]', timeout_seconds=45)
        flow.screenshot(shot_receipts)
        report["screenshots"]["receipts"] = str(shot_receipts)

    report_path = output_dir / f"npc-automation-toggle-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), "project_id": project_id, "issues": len(report["issues"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
