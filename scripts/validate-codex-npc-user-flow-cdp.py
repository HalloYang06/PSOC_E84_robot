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
CLAUDE_FLOW_PATH = SCRIPT_DIR / "validate-claude-npc-user-flow-cdp.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collab = load_module("ui_frontdoor_collab_helper", COLLAB_HELPER_PATH)
flow_helper = load_module("claude_npc_flow_helper", CLAUDE_FLOW_PATH)

BrowserRuntime = collab.BrowserRuntime
find_free_port = collab.find_free_port
new_browser_profile = collab.new_browser_profile
login_via_ui = collab.login_via_ui
create_agent_command_via_selected_npc = collab.create_agent_command_via_selected_npc
verify_receipts_visible_direct = collab.verify_receipts_visible_direct

WEB_BASE = "http://127.0.0.1:3000"
API_BASE = "http://127.0.0.1:8010"
MAIN_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
OWNER_EMAIL = "codex-platform-npc@local.dev"
OWNER_PASSWORD = "password"
PREFERRED_CODEX_NPC_NAMES = ["NPC1", "NPC2", "NPC3"]


def _text(value: object) -> str:
    return str(value or "").strip()


def _metadata(item: dict[str, object]) -> dict[str, object]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def provider_id(item: dict[str, object]) -> str:
    metadata = _metadata(item)
    return _text(
        item.get("ai_provider_id")
        or item.get("ai_provider")
        or metadata.get("provider_id")
        or metadata.get("provider_family")
    ).lower()


def seat_type(item: dict[str, object]) -> str:
    metadata = _metadata(item)
    return _text(item.get("seat_type") or metadata.get("seat_type")).lower()


def source_thread_id(item: dict[str, object]) -> str:
    metadata = _metadata(item)
    return _text(item.get("source_workstation_id") or metadata.get("source_workstation_id"))


def pick_codex_npc(workstations: list[dict[str, object]]) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for item in workstations:
        item_id = _text(item.get("id") or item.get("workstation_id"))
        name = _text(item.get("name") or item.get("workstation_name"))
        source_thread = source_thread_id(item)
        if not item_id or provider_id(item) != "codex":
            continue
        if seat_type(item) not in {"codex", "npc"}:
            continue
        if not source_thread.startswith("codex-session-"):
            continue
        candidates.append(item)
    if not candidates:
        raise RuntimeError("没有找到已绑定 Codex 线程的长期 NPC，请先在 NPC 管理器创建或绑定一个 Codex NPC。")

    def score(item: dict[str, object]) -> tuple[int, int, str]:
        name = _text(item.get("name") or item.get("workstation_name"))
        preferred_rank = 10 - PREFERRED_CODEX_NPC_NAMES.index(name) if name in PREFERRED_CODEX_NPC_NAMES else 0
        active = 1 if _text(item.get("status")).lower() == "active" else 0
        return (preferred_rank, active, name)

    return sorted(candidates, key=score, reverse=True)[0]


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = REPO_ROOT / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="codex-npc-user-flow-", dir=str(output_dir)))
    report: dict[str, object] = {
        "stamp": stamp,
        "project_id": MAIN_PROJECT_ID,
        "owner_email": OWNER_EMAIL,
        "screenshots": {},
        "steps": {},
        "issues": [],
    }

    owner_token, owner_user = flow_helper.api_login(API_BASE, OWNER_EMAIL, OWNER_PASSWORD)
    workstations = flow_helper.list_workstations(owner_token, MAIN_PROJECT_ID)
    codex_npc = pick_codex_npc(workstations)
    npc_seat_id = _text(codex_npc.get("id") or codex_npc.get("workstation_id"))
    source_thread = source_thread_id(codex_npc)
    report["steps"]["owner_user"] = owner_user
    report["steps"]["codex_npc"] = codex_npc
    report["steps"]["source_thread_id"] = source_thread

    profile_dir = new_browser_profile(runtime_dir, "owner")
    try:
        with BrowserRuntime(find_free_port(), profile_dir, 1720, 1080) as flow:
            shot_login = output_dir / f"codex-npc-user-flow-01-login-{stamp}.png"
            login_via_ui(flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=shot_login)
            report["screenshots"]["login"] = str(shot_login)

            flow.navigate(
                f"{WEB_BASE}/projects/{MAIN_PROJECT_ID}?panel=team&tab=npc-create&seat={collab.quote(npc_seat_id)}"
                f"&drawer=npc-profile&drawer_id={collab.quote(npc_seat_id)}"
            )
            flow.wait_for_selector("[data-npc-manager-selected], [data-npc-profile-skill-summary]", timeout_seconds=45)
            shot_existing = output_dir / f"codex-npc-user-flow-02-existing-npc-{stamp}.png"
            flow.screenshot(shot_existing)
            report["screenshots"]["existing_npc"] = str(shot_existing)
            resolved_seat = flow.eval(
                f"""
                (() => {{
                  const candidates = Array.from(document.querySelectorAll('[data-npc-rail-seat]')).map((item) => ({{
                    id: item.getAttribute('data-npc-rail-seat') || '',
                    text: (item.textContent || '').trim(),
                  }}));
                  const byId = candidates.find((item) => item.id === {collab.js_string(npc_seat_id)});
                  const byName = candidates.find((item) => item.text.includes('NPC1')) ||
                    candidates.find((item) => item.text.includes({collab.js_string(_text(codex_npc.get("name") or ""))}));
                  return byId || byName || candidates[0] || null;
                }})()
                """
            )
            if isinstance(resolved_seat, dict) and _text(resolved_seat.get("id")):
                npc_seat_id = _text(resolved_seat.get("id"))
                report["steps"]["resolved_ui_seat"] = resolved_seat

            command_title = f"Codex NPC 用户链路验收-{stamp[-6:]}"
            expected_keywords = ["最终回复", "Codex NPC", stamp[-6:]]
            command_body = (
                "请只完成这一条平台协作指令，不要进入持续自动化。"
                "先回最小回执，然后最终回复必须包含："
                f"最终回复：Codex NPC 已完成用户链路验收 {stamp[-6:]}。"
            )
            shot_preview = output_dir / f"codex-npc-user-flow-03-dialog-preview-{stamp}.png"
            shot_sent = output_dir / f"codex-npc-user-flow-04-dispatch-visible-{stamp}.png"
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

            receipts = flow_helper.wait_for_claude_receipts(
                owner_token,
                project_id=MAIN_PROJECT_ID,
                title=command_title,
                timeout_seconds=240,
            )
            final_body = _text(receipts["result_message"].get("body") if isinstance(receipts.get("result_message"), dict) else "")
            missing_keywords = [keyword for keyword in expected_keywords if keyword not in final_body]
            if missing_keywords:
                raise RuntimeError(
                    f"Codex 最终回复缺少关键验收词：missing={missing_keywords!r}, actual={final_body!r}"
                )
            report["steps"]["receipts"] = receipts
            report["steps"]["expected_final_keywords"] = expected_keywords

            shot_receipts = output_dir / f"codex-npc-user-flow-05-receipts-{stamp}.png"
            receipt_state = verify_receipts_visible_direct(
                flow,
                project_id=MAIN_PROJECT_ID,
                command_title=command_title,
                shot=shot_receipts,
            )
            report["steps"]["receipt_state"] = receipt_state
            report["screenshots"]["receipts"] = str(shot_receipts)

        report["verdict"] = "passed"
        report_path = output_dir / f"codex-npc-user-flow-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"verdict": "passed", "report_path": str(report_path), "screenshots": report["screenshots"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        import shutil

        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
