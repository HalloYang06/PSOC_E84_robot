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
CODEX_FLOW_PATH = SCRIPT_DIR / "validate-codex-npc-user-flow-cdp.py"
CLAUDE_FLOW_PATH = SCRIPT_DIR / "validate-claude-npc-user-flow-cdp.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collab = load_module("ui_frontdoor_collab_helper", COLLAB_HELPER_PATH)
codex_flow = load_module("codex_npc_flow_helper", CODEX_FLOW_PATH)
claude_flow = load_module("claude_npc_flow_helper", CLAUDE_FLOW_PATH)

WEB_BASE = "http://127.0.0.1:3000"
API_BASE = "http://127.0.0.1:8010"
MAIN_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
OWNER_EMAIL = "codex-platform-npc@local.dev"
OWNER_PASSWORD = "password"


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


def source_thread_id(item: dict[str, object]) -> str:
    metadata = _metadata(item)
    return _text(item.get("source_workstation_id") or metadata.get("source_workstation_id"))


def pick_claude_npc(workstations: list[dict[str, object]]) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for item in workstations:
        item_id = _text(item.get("id") or item.get("workstation_id"))
        name = _text(item.get("name") or item.get("workstation_name"))
        source_thread = source_thread_id(item)
        if not item_id or provider_id(item) != "claude":
            continue
        if not source_thread.startswith("claude-session-"):
            continue
        if item_id.startswith("claude-session-"):
            continue
        if "Claude" not in name and "claude" not in item_id.lower():
            continue
        candidates.append(item)
    if not candidates:
        raise RuntimeError("没有找到已绑定 Claude 线程的 NPC，请先跑 Claude NPC 用户链路验收。")
    return sorted(candidates, key=lambda item: _text(item.get("updated_at") or item.get("created_at")), reverse=True)[0]


def resolve_ui_seat_id(flow, *, wanted_label: str, fallback_id: str) -> str:
    state = flow.wait_for(
        f"""
        (() => {{
          const fallback = {collab.js_string(fallback_id)};
          const wanted = {collab.js_string(wanted_label)};
          const candidates = Array.from(document.querySelectorAll('[data-npc-rail-seat]')).map((item) => ({{
            id: item.getAttribute('data-npc-rail-seat') || '',
            text: (item.textContent || '').trim(),
          }}));
          const byText = candidates.find((item) => item.text.includes(wanted));
          const byId = candidates.find((item) => item.id === fallback);
          const found = byText || byId || candidates[0] || null;
          return found && found.id ? found : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict) or not _text(state.get("id")):
        raise RuntimeError(f"无法在 NPC 精灵栏解析 {wanted_label} 的 UI seat id: {state}")
    return _text(state["id"])


def wait_for_completed_result(token: str, *, title: str, expected_keyword: str) -> dict[str, object]:
    receipts = claude_flow.wait_for_claude_receipts(
        token,
        project_id=MAIN_PROJECT_ID,
        title=title,
        timeout_seconds=240,
    )
    result = receipts.get("result_message")
    body = _text(result.get("body") if isinstance(result, dict) else "")
    if expected_keyword not in body:
        raise RuntimeError(f"最终回复缺少关键词 {expected_keyword!r}: {body!r}")
    return receipts


def verify_both_rounds_visible(flow, *, codex_title: str, claude_title: str, shot: Path) -> dict[str, object]:
    flow.navigate(f"{WEB_BASE}/projects/{MAIN_PROJECT_ID}?panel=team&tab=exchange&exchange_section=receipts")
    flow.wait_for_selector('[data-exchange-section="receipts"]', timeout_seconds=45)
    state = flow.wait_for(
        f"""
        (() => {{
          const rounds = Array.from(document.querySelectorAll('[data-exchange-receipt-round]')).map((item) => ({{
            title: item.getAttribute('data-exchange-receipt-round') || '',
            status: item.getAttribute('data-exchange-receipt-round-status') || '',
            text: (item.textContent || '').trim(),
          }}));
          const wanted = [{collab.js_string(codex_title)}, {collab.js_string(claude_title)}];
          const present = wanted.map((title) => rounds.find((item) => item.title === title && item.text.includes('状态：completed')));
          return present.every(Boolean) ? {{ rounds, href: location.href }} : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    flow.screenshot(shot)
    if not isinstance(state, dict):
        raise RuntimeError("双 NPC 协作回执轮次没有同时出现在协作消息池。")
    return state


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_stamp = stamp[-6:]
    output_dir = REPO_ROOT / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="dual-npc-article-collab-", dir=str(output_dir)))
    report: dict[str, object] = {
        "stamp": stamp,
        "project_id": MAIN_PROJECT_ID,
        "screenshots": {},
        "steps": {},
    }

    owner_token, owner_user = claude_flow.api_login(API_BASE, OWNER_EMAIL, OWNER_PASSWORD)
    workstations = claude_flow.list_workstations(owner_token, MAIN_PROJECT_ID)
    codex_npc = codex_flow.pick_codex_npc(workstations)
    claude_npc = pick_claude_npc(workstations)
    report["steps"]["owner_user"] = owner_user
    report["steps"]["codex_npc"] = codex_npc
    report["steps"]["claude_npc"] = claude_npc

    profile_dir = collab.new_browser_profile(runtime_dir, "owner")
    try:
        with collab.BrowserRuntime(collab.find_free_port(), profile_dir, 1720, 1080) as flow:
            shot_login = output_dir / f"dual-npc-article-collab-01-login-{stamp}.png"
            collab.login_via_ui(flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=shot_login)
            report["screenshots"]["login"] = str(shot_login)

            flow.navigate(f"{WEB_BASE}/projects/{MAIN_PROJECT_ID}?panel=team&tab=npc-create")
            flow.wait_for_selector("[data-npc-rail-seat]", timeout_seconds=45)
            codex_seat_id = resolve_ui_seat_id(
                flow,
                wanted_label=_text(codex_npc.get("name") or "NPC1"),
                fallback_id=_text(codex_npc.get("id") or codex_npc.get("workstation_id")),
            )
            claude_seat_id = resolve_ui_seat_id(
                flow,
                wanted_label="Claude",
                fallback_id=_text(claude_npc.get("id") or claude_npc.get("workstation_id")),
            )
            report["steps"]["resolved_seats"] = {"codex": codex_seat_id, "claude": claude_seat_id}

            codex_title = f"双NPC协作资料收集-{short_stamp}"
            codex_body = (
                "请只执行这一条单次协作指令，不要开启持续自动化。"
                "你负责给一篇给新用户看的短文做资料与结构提纲，主题是：为什么 AI 协作平台要用 NPC、电脑和线程三层管理。"
                f"最终回复必须包含：双NPC协作资料收集完成 {short_stamp}。"
            )
            codex_preview = output_dir / f"dual-npc-article-collab-02-codex-preview-{stamp}.png"
            codex_sent = output_dir / f"dual-npc-article-collab-03-codex-sent-{stamp}.png"
            report["steps"]["codex_command"] = collab.create_agent_command_via_selected_npc(
                flow,
                project_id=MAIN_PROJECT_ID,
                npc_seat_id=codex_seat_id,
                command_title=codex_title,
                command_body=codex_body,
                shot_preview=codex_preview,
                shot_sent=codex_sent,
            )
            report["screenshots"]["codex_preview"] = str(codex_preview)
            report["screenshots"]["codex_sent"] = str(codex_sent)
            report["steps"]["codex_receipts"] = wait_for_completed_result(
                owner_token,
                title=codex_title,
                expected_keyword=f"双NPC协作资料收集完成 {short_stamp}",
            )

            codex_final_body = _text(report["steps"]["codex_receipts"]["result_message"].get("body"))
            claude_title = f"双NPC协作成稿校验-{short_stamp}"
            claude_body = (
                "请只执行这一条单次协作指令，不要开启持续自动化。"
                "你现在接手 Codex NPC 的资料结果，写一段面向新用户的成稿草案，并指出还缺哪一项人工审核。"
                f"Codex 资料结果摘要：{codex_final_body[:600]}"
                f"\n最终回复必须包含：双NPC协作成稿完成 {short_stamp}。"
            )
            claude_preview = output_dir / f"dual-npc-article-collab-04-claude-preview-{stamp}.png"
            claude_sent = output_dir / f"dual-npc-article-collab-05-claude-sent-{stamp}.png"
            report["steps"]["claude_command"] = collab.create_agent_command_via_selected_npc(
                flow,
                project_id=MAIN_PROJECT_ID,
                npc_seat_id=claude_seat_id,
                command_title=claude_title,
                command_body=claude_body,
                shot_preview=claude_preview,
                shot_sent=claude_sent,
            )
            report["screenshots"]["claude_preview"] = str(claude_preview)
            report["screenshots"]["claude_sent"] = str(claude_sent)
            report["steps"]["claude_receipts"] = wait_for_completed_result(
                owner_token,
                title=claude_title,
                expected_keyword=f"双NPC协作成稿完成 {short_stamp}",
            )

            receipts_shot = output_dir / f"dual-npc-article-collab-06-receipts-{stamp}.png"
            report["steps"]["receipts_visible"] = verify_both_rounds_visible(
                flow,
                codex_title=codex_title,
                claude_title=claude_title,
                shot=receipts_shot,
            )
            report["screenshots"]["receipts"] = str(receipts_shot)

        report["verdict"] = "passed"
        report_path = output_dir / f"dual-npc-article-collab-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"verdict": "passed", "report_path": str(report_path), "screenshots": report["screenshots"]}, ensure_ascii=False, indent=2))
        return 0
    finally:
        import shutil

        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
