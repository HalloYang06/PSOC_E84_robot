from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
COLLAB_HELPER_PATH = SCRIPT_DIR / "validate-ui-frontdoor-collab-cdp.py"

spec = importlib.util.spec_from_file_location("ui_frontdoor_collab_helper", COLLAB_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load helper module: {COLLAB_HELPER_PATH}")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

BrowserRuntime = helper.BrowserRuntime
find_free_port = helper.find_free_port
new_browser_profile = helper.new_browser_profile
login_via_ui = helper.login_via_ui
api_login = helper.api_login
create_agent_command_via_selected_npc = helper.create_agent_command_via_selected_npc
verify_receipts_visible_direct = helper.verify_receipts_visible_direct
list_project_messages = helper.list_project_messages
pick_message = helper.pick_message
js_string = helper.js_string

WEB_BASE = "http://127.0.0.1:3000"
API_BASE = "http://127.0.0.1:8010"
MAIN_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
OWNER_EMAIL = "codex-platform-npc@local.dev"
OWNER_PASSWORD = "password"
STABLE_NPC_NAME = "Claude 平台验收员"
STABLE_NPC_ROLE = "负责验证 Claude 线程能通过平台 NPC 对话接单、最小回执和最终回复。"


def request_json(
    path: str,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{API_BASE.rstrip('/')}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {path}: {detail}") from exc


def list_workstations(token: str, project_id: str) -> list[dict[str, object]]:
    payload = request_json(f"/api/collaboration/projects/{project_id}/thread-workstations", token=token)
    data = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def pick_claude_thread(workstations: list[dict[str, object]]) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for item in workstations:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        item_id = str(item.get("id") or item.get("workstation_id") or "").strip()
        provider = str(
            item.get("ai_provider_id")
            or item.get("ai_provider")
            or metadata.get("provider_id")
            or metadata.get("provider_family")
            or ""
        ).strip().lower()
        source = str(item.get("source") or metadata.get("source") or "").strip()
        seat_type = str(item.get("seat_type") or metadata.get("seat_type") or "").strip().lower()
        if not item_id.startswith("claude-session-") and provider != "claude":
            continue
        if seat_type or source != "runner_thread_scan":
            continue
        candidates.append(item)
    if not candidates:
        raise RuntimeError("没有找到可绑定的 Claude 会话线程。请先运行 sync-claude-session-threads.ps1。")

    def score(item: dict[str, object]) -> tuple[int, str]:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        live = 1 if metadata.get("live_process_seen") or str(item.get("status") or "").lower() == "active" else 0
        source_kind = 1 if str(metadata.get("source_kind") or "") == "live_session_file" else 0
        updated = str(item.get("updated_at") or metadata.get("synced_at") or "")
        return (live + source_kind, updated)

    return sorted(candidates, key=score, reverse=True)[0]


def find_stable_claude_npc(
    workstations: list[dict[str, object]],
    *,
    source_thread_id: str,
) -> dict[str, object] | None:
    for item in reversed(workstations):
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        item_id = str(item.get("id") or item.get("workstation_id") or "").strip()
        name = str(item.get("name") or item.get("workstation_name") or "").strip()
        source = str(metadata.get("source_workstation_id") or item.get("source_workstation_id") or "").strip()
        provider = str(
            item.get("ai_provider_id")
            or item.get("ai_provider")
            or metadata.get("provider_id")
            or metadata.get("provider_label")
            or ""
        ).strip().lower()
        if not item_id:
            continue
        if name == STABLE_NPC_NAME and (source == source_thread_id or provider == "claude"):
            return item
    return None


def create_claude_npc_via_ui(
    flow,
    *,
    project_id: str,
    source_thread_id: str,
    computer_node_id: str,
    shot_before: Path,
    shot_after: Path,
) -> dict[str, object]:
    flow.navigate(f"{WEB_BASE}/projects/{project_id}?panel=team&tab=npc-create&drawer=npc-create")
    flow.wait_for_selector('[data-npc-create-form] input[name="name"]', timeout_seconds=45)
    flow.fill('[data-npc-create-form] input[name="name"]', STABLE_NPC_NAME)
    flow.fill('[data-npc-create-form] input[name="responsibility"]', STABLE_NPC_ROLE)
    flow.set_select('[data-npc-create-form] select[name="source_workstation_id"]', source_thread_id)
    flow.set_select('[data-npc-create-form] select[name="computer_node_id"]', computer_node_id)
    flow.fill('[data-npc-create-form] input[name="model"]', "sonnet")
    flow.fill('[data-npc-create-form] input[name="ai_provider"]', "Claude")
    flow.fill(
        '[data-npc-create-form] textarea[name="knowledge_summary"]',
        "长期保留：这是主项目用于验收 Claude 接入的稳定 NPC。默认关闭自动化，只在用户发送当前指令时执行一次，避免额外 token 消耗。",
    )
    flow.eval(
        """
        (() => {
          const checkbox = document.querySelector('[data-npc-create-form] input[type="checkbox"][name="automation_enabled"]');
          if (checkbox instanceof HTMLInputElement) {
            checkbox.checked = false;
            checkbox.dispatchEvent(new Event('input', { bubbles: true }));
            checkbox.dispatchEvent(new Event('change', { bubbles: true }));
          }
          return true;
        })()
        """
    )
    flow.screenshot(shot_before)
    flow.submit('[data-npc-create-form]')
    state = flow.wait_for(
        f"""
        (() => {{
          const match = Array.from(document.querySelectorAll('[data-npc-rail-seat]')).find((item) =>
            ((item.textContent || '')).includes({js_string(STABLE_NPC_NAME)})
          );
          return match
            ? {{
                seatId: match.getAttribute('data-npc-rail-seat') || '',
                railText: match.textContent || '',
                body: document.body ? document.body.innerText.slice(0, 5000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=60,
        interval_seconds=0.5,
    )
    if not isinstance(state, dict) or not str(state.get("seatId") or ""):
        raise RuntimeError(f"创建 Claude NPC 后没有在 NPC 栏找到稳定席位：{state}")
    flow.screenshot(shot_after)
    return state


def wait_for_claude_receipts(
    token: str,
    *,
    project_id: str,
    title: str,
    timeout_seconds: float = 180.0,
) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_messages: list[dict[str, object]] = []
    while time.time() < deadline:
        last_messages = list_project_messages(API_BASE, project_id, token)
        ack = None
        result = None
        try:
            ack = pick_message(last_messages, title=title, message_type="agent_ack")
        except Exception:
            ack = None
        try:
            result = pick_message(last_messages, title=title, message_type="agent_result")
        except Exception:
            result = None
        if ack and result and str(result.get("status") or "").lower() == "completed":
            return {
                "ack_message": ack,
                "result_message": result,
                "message_count": len(last_messages),
            }
        time.sleep(2.0)
    recent = [
        {
            "type": item.get("message_type"),
            "title": item.get("title"),
            "status": item.get("status"),
            "sender": item.get("sender_id"),
        }
        for item in last_messages[-12:]
    ]
    raise RuntimeError(f"等待 Claude NPC 回执超时：{title} / 最近消息：{recent}")


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = REPO_ROOT / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="claude-npc-user-flow-", dir=str(output_dir)))
    report: dict[str, object] = {
        "stamp": stamp,
        "project_id": MAIN_PROJECT_ID,
        "owner_email": OWNER_EMAIL,
        "stable_npc_name": STABLE_NPC_NAME,
        "screenshots": {},
        "steps": {},
        "issues": [],
    }

    owner_token, owner_user = api_login(API_BASE, OWNER_EMAIL, OWNER_PASSWORD)
    workstations = list_workstations(owner_token, MAIN_PROJECT_ID)
    claude_thread = pick_claude_thread(workstations)
    claude_thread_id = str(claude_thread.get("id") or claude_thread.get("workstation_id") or "").strip()
    computer_node_id = str(
        claude_thread.get("computer_node_id")
        or (claude_thread.get("metadata") if isinstance(claude_thread.get("metadata"), dict) else {}).get("computer_node_id")
        or "local-dev-pc"
    ).strip()
    report["steps"]["owner_user"] = owner_user
    report["steps"]["claude_thread"] = claude_thread

    existing_npc = find_stable_claude_npc(workstations, source_thread_id=claude_thread_id)

    profile_dir = new_browser_profile(runtime_dir, "owner")
    with BrowserRuntime(find_free_port(), profile_dir, 1720, 1080) as flow:
        shot_login = output_dir / f"claude-npc-user-flow-01-login-{stamp}.png"
        login_via_ui(flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=shot_login)
        report["screenshots"]["login"] = str(shot_login)

        if existing_npc:
            npc_seat_id = str(existing_npc.get("id") or existing_npc.get("workstation_id") or "").strip()
            flow.navigate(
                f"{WEB_BASE}/projects/{MAIN_PROJECT_ID}?panel=team&tab=npc-create&seat={npc_seat_id}&drawer=npc-profile&drawer_id={npc_seat_id}"
            )
            flow.wait_for_selector('[data-npc-manager-selected], [data-npc-profile-skill-summary]', timeout_seconds=45)
            shot_existing = output_dir / f"claude-npc-user-flow-02-existing-npc-{stamp}.png"
            flow.screenshot(shot_existing)
            report["steps"]["npc"] = {
                "mode": "reused",
                "seat_id": npc_seat_id,
                "name": existing_npc.get("name") or existing_npc.get("workstation_name"),
                "source_thread_id": claude_thread_id,
            }
            report["screenshots"]["existing_npc"] = str(shot_existing)
        else:
            shot_before = output_dir / f"claude-npc-user-flow-02-create-before-{stamp}.png"
            shot_after = output_dir / f"claude-npc-user-flow-03-create-after-{stamp}.png"
            created = create_claude_npc_via_ui(
                flow,
                project_id=MAIN_PROJECT_ID,
                source_thread_id=claude_thread_id,
                computer_node_id=computer_node_id,
                shot_before=shot_before,
                shot_after=shot_after,
            )
            npc_seat_id = str(created.get("seatId") or "").strip()
            report["steps"]["npc"] = {
                "mode": "created",
                "seat_id": npc_seat_id,
                "source_thread_id": claude_thread_id,
                "computer_node_id": computer_node_id,
                "create_state": created,
            }
            report["screenshots"]["create_before"] = str(shot_before)
            report["screenshots"]["create_after"] = str(shot_after)

        command_title = f"Claude NPC 用户链路验收-{stamp[-6:]}"
        expected_final = f"最终回复：Claude NPC 已完成用户链路验收 {stamp[-6:]}。"
        expected_final_keywords = ["最终回复", "Claude NPC", stamp[-6:]]
        command_body = (
            "请只完成这一条平台协作指令，不要开启持续自动化。"
            "你需要先让平台适配器回最小回执，然后最终回复必须只包含这一句："
            f"{expected_final}"
        )
        shot_preview = output_dir / f"claude-npc-user-flow-04-dialog-preview-{stamp}.png"
        shot_sent = output_dir / f"claude-npc-user-flow-05-dispatch-visible-{stamp}.png"
        command_state = create_agent_command_via_selected_npc(
            flow,
            project_id=MAIN_PROJECT_ID,
            npc_seat_id=npc_seat_id,
            command_title=command_title,
            command_body=command_body,
            shot_preview=shot_preview,
            shot_sent=shot_sent,
        )
        report["steps"]["command"] = command_state
        report["screenshots"]["dialog_preview"] = str(shot_preview)
        report["screenshots"]["dispatch_visible"] = str(shot_sent)

        receipts = wait_for_claude_receipts(owner_token, project_id=MAIN_PROJECT_ID, title=command_title)
        final_body = str(receipts["result_message"].get("body") or "")
        missing_keywords = [keyword for keyword in expected_final_keywords if keyword not in final_body]
        if missing_keywords:
            raise RuntimeError(
                "Claude 最终回复缺少关键验收词："
                f"missing={missing_keywords!r}, expected_hint={expected_final!r}, actual={final_body!r}"
            )
        report["steps"]["receipts"] = receipts
        report["steps"]["expected_final_keywords"] = expected_final_keywords

        shot_receipts = output_dir / f"claude-npc-user-flow-06-receipts-{stamp}.png"
        receipt_state = verify_receipts_visible_direct(
            flow,
            project_id=MAIN_PROJECT_ID,
            command_title=command_title,
            shot=shot_receipts,
        )
        report["steps"]["receipt_state"] = receipt_state
        report["screenshots"]["receipts"] = str(shot_receipts)

    report["verdict"] = "passed"
    report_path = output_dir / f"claude-npc-user-flow-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": "passed", "report_path": str(report_path), "screenshots": report["screenshots"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
