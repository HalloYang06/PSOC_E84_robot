from __future__ import annotations

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
ONBOARDING_PATH = SCRIPT_DIR / "validate-ui-frontdoor-onboarding-cdp.py"
DUAL_HELPER_PATH = SCRIPT_DIR / "validate-dual-account-invite-collab-cdp.py"
COLLAB_PATH = SCRIPT_DIR / "validate-ui-frontdoor-collab-cdp.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


onboarding = load_module("ui_onboarding_helper", ONBOARDING_PATH)
dual_helper = load_module("dual_helper", DUAL_HELPER_PATH)
ui_collab = load_module("ui_frontdoor_collab_helper", COLLAB_PATH)

BrowserRuntime = dual_helper.BrowserRuntime
find_free_port = dual_helper.find_free_port
login_via_ui = dual_helper.login_via_ui
register_via_ui = dual_helper.register_via_ui
verify_projects_plaza = dual_helper.verify_projects_plaza
accept_invite_via_ui = dual_helper.accept_invite_via_ui
create_computer_via_ui = dual_helper.create_computer_via_ui
create_npc_via_ui = dual_helper.create_npc_via_ui
invite_via_ui = dual_helper.invite_via_ui
api_login = dual_helper.api_login
execute_command_chain_via_ui_and_adapter = dual_helper.execute_command_chain_via_ui_and_adapter
verify_shared_command_chain_visible = dual_helper.verify_shared_command_chain_visible
new_browser_profile = dual_helper.new_browser_profile
execute_command_chain_via_selected_npc = ui_collab.execute_command_chain_via_selected_npc
verify_agent_command_visible_direct = ui_collab.verify_agent_command_visible_direct
verify_receipts_visible_direct = ui_collab.verify_receipts_visible_direct

WEB_BASE = onboarding.WEB_BASE
API_BASE = onboarding.API_BASE
OUTPUT_DIR = onboarding.OUTPUT_DIR
VIEWPORT_WIDTH = onboarding.VIEWPORT_WIDTH
VIEWPORT_HEIGHT = onboarding.VIEWPORT_HEIGHT
OWNER_EMAIL = onboarding.OWNER_EMAIL
OWNER_PASSWORD = onboarding.OWNER_PASSWORD
OWNER_NAME = onboarding.OWNER_NAME


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="ui-frontdoor-fullchain-"))
    first_workspace = runtime_dir / "owner-workspace"
    second_workspace = runtime_dir / "member-workspace"
    first_workspace.mkdir(parents=True, exist_ok=True)
    second_workspace.mkdir(parents=True, exist_ok=True)

    collaborator_email = f"ui-fullchain-collab-{stamp}@local.dev"
    collaborator_password = "password123"
    collaborator_name = "UI Fullchain Collaborator"
    project_name = f"UI前台整链验收项目-{stamp[-6:]}"
    project_description = "从真实前台走新建项目、两台电脑、线程扫描、创建 NPC、发协作任务、同项目共享回执。"
    first_computer_id = f"ui-full-a-{stamp[-6:]}"
    second_computer_id = f"ui-full-b-{stamp[-6:]}"
    owner_runner_id = f"runner-ui-full-owner-{stamp[-6:]}"
    member_runner_id = f"runner-ui-full-member-{stamp[-6:]}"
    owner_thread_id = f"owner-codex-full-{stamp[-6:]}"
    member_thread_id = f"member-codex-full-{stamp[-6:]}"
    npc_name = f"第二台电脑协作NPC-{stamp[-4:]}"
    command_title = f"前台整链协作验证-{stamp[-6:]}"
    command_body = (
        "请先回最小回执，再确认第二台电脑线程已经完成前台接单验证，"
        "最后用一段中文说明接下来建议平台继续做什么。"
    )
    ack_note = "前台整链协作验证最小回执已回。"
    final_note = "第二台电脑线程已完成前台整链协作验证，并给出下一步建议。"

    report: dict[str, object] = {
        "stamp": stamp,
        "web_base": WEB_BASE,
        "api_base": API_BASE,
        "project_name": project_name,
        "steps": {},
        "issues": [],
        "screenshots": {},
    }

    try:
        owner_profile = new_browser_profile(runtime_dir, "owner")
        with BrowserRuntime(find_free_port(), owner_profile, VIEWPORT_WIDTH, VIEWPORT_HEIGHT) as owner_flow:
            shot = output_dir / f"ui-fullchain-01-owner-login-{stamp}.png"
            login_via_ui(owner_flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=shot)
            report["screenshots"]["owner_login"] = str(shot)

            shot = output_dir / f"ui-fullchain-02-create-project-{stamp}.png"
            project_state = onboarding.create_project_via_ui_pure(
                owner_flow,
                project_name=project_name,
                description=project_description,
                shot=shot,
            )
            project_id = str(project_state["project_id"])
            report["steps"]["create_project"] = project_state
            report["screenshots"]["create_project"] = str(shot)

            shot = output_dir / f"ui-fullchain-03-owner-project-map-{stamp}.png"
            owner_map = onboarding.open_project_map(owner_flow, project_id=project_id, shot=shot)
            report["steps"]["owner_project_map"] = owner_map
            report["screenshots"]["owner_project_map"] = str(shot)

            shot = output_dir / f"ui-fullchain-04-owner-computer-create-{stamp}.png"
            owner_computer = create_computer_via_ui(
                owner_flow,
                WEB_BASE,
                project_id=project_id,
                computer_id=first_computer_id,
                label="Owner Fullchain PC",
                workspace_root=str(first_workspace),
                git_root=str(first_workspace),
                shot=shot,
            )
            report["steps"]["owner_computer_create"] = owner_computer
            report["screenshots"]["owner_computer_create"] = str(shot)

            shot = output_dir / f"ui-fullchain-05-owner-pairing-token-{stamp}.png"
            owner_pairing = onboarding.generate_pairing_token_via_ui_pure(
                owner_flow,
                project_id=project_id,
                computer_id=first_computer_id,
                shot=shot,
            )
            report["steps"]["owner_pairing_token"] = owner_pairing
            report["screenshots"]["owner_pairing_token"] = str(shot)

            report["steps"]["owner_runner_onboarding"] = onboarding.onboard_runner_via_user_scripts(
                server=API_BASE,
                pairing_token=str(owner_pairing.get("pairingToken") or ""),
                computer_node_id=first_computer_id,
                project_id=project_id,
                runner_id=owner_runner_id,
                runner_name="Owner Fullchain Runner",
                thread_id=owner_thread_id,
                thread_name="Owner Fullchain Codex Mainline",
                cwd=str(first_workspace),
            )

            shot_before = output_dir / f"ui-fullchain-06-owner-scan-before-{stamp}.png"
            shot_after = output_dir / f"ui-fullchain-07-owner-scan-after-{stamp}.png"
            owner_scan = onboarding.attempt_thread_scan_via_ui(
                owner_flow,
                project_id=project_id,
                computer_id=first_computer_id,
                shot_before=shot_before,
                shot_after=shot_after,
            )
            report["steps"]["owner_scan_threads"] = owner_scan
            report["screenshots"]["owner_scan_before"] = str(shot_before)
            report["screenshots"]["owner_scan_after"] = str(shot_after)
            if not owner_scan.get("scan_surfaced_threads"):
                raise RuntimeError(f"Owner thread scan did not surface real threads: {owner_scan}")

            shot = output_dir / f"ui-fullchain-08-owner-invite-collaborator-{stamp}.png"
            invite_via_ui(
                owner_flow,
                WEB_BASE,
                project_id=project_id,
                invitee_email=collaborator_email,
                note="请加入这个项目，从第二台电脑接入并一起验证前台协作闭环。",
                shot=shot,
            )
            report["steps"]["invite_collaborator"] = {
                "invitee_email": collaborator_email,
                "project_id": project_id,
            }
            report["screenshots"]["invite_collaborator"] = str(shot)

        member_profile = new_browser_profile(runtime_dir, "member")
        with BrowserRuntime(find_free_port(), member_profile, VIEWPORT_WIDTH, VIEWPORT_HEIGHT) as member_flow:
            shot = output_dir / f"ui-fullchain-09-member-signup-{stamp}.png"
            register_via_ui(
                member_flow,
                WEB_BASE,
                email=collaborator_email,
                password=collaborator_password,
                name=collaborator_name,
                shot=shot,
            )
            report["screenshots"]["member_signup"] = str(shot)

            before_accept = verify_projects_plaza(
                member_flow,
                WEB_BASE,
                project_name=project_name,
                expected_present=False,
            )
            report["steps"]["member_projects_before_accept"] = before_accept

            shot = output_dir / f"ui-fullchain-10-member-accept-invite-{stamp}.png"
            accept_invite_via_ui(member_flow, WEB_BASE, project_name=project_name, shot=shot)
            report["screenshots"]["member_accept_invite"] = str(shot)

            after_accept = verify_projects_plaza(
                member_flow,
                WEB_BASE,
                project_name=project_name,
                expected_present=True,
            )
            report["steps"]["member_projects_after_accept"] = after_accept

            shot = output_dir / f"ui-fullchain-11-member-project-map-{stamp}.png"
            member_map = onboarding.open_project_map(member_flow, project_id=project_id, shot=shot)
            report["steps"]["member_project_map"] = member_map
            report["screenshots"]["member_project_map"] = str(shot)

            shot = output_dir / f"ui-fullchain-12-member-computer-create-{stamp}.png"
            member_computer = create_computer_via_ui(
                member_flow,
                WEB_BASE,
                project_id=project_id,
                computer_id=second_computer_id,
                label="Member Fullchain PC",
                workspace_root=str(second_workspace),
                git_root=str(second_workspace),
                shot=shot,
            )
            report["steps"]["member_computer_create"] = member_computer
            report["screenshots"]["member_computer_create"] = str(shot)

            shot = output_dir / f"ui-fullchain-13-member-pairing-token-{stamp}.png"
            member_pairing = onboarding.generate_pairing_token_via_ui_pure(
                member_flow,
                project_id=project_id,
                computer_id=second_computer_id,
                shot=shot,
            )
            report["steps"]["member_pairing_token"] = member_pairing
            report["screenshots"]["member_pairing_token"] = str(shot)

            report["steps"]["member_runner_onboarding"] = onboarding.onboard_runner_via_user_scripts(
                server=API_BASE,
                pairing_token=str(member_pairing.get("pairingToken") or ""),
                computer_node_id=second_computer_id,
                project_id=project_id,
                runner_id=member_runner_id,
                runner_name="Member Fullchain Runner",
                thread_id=member_thread_id,
                thread_name="Member Fullchain Codex Mainline",
                cwd=str(second_workspace),
            )

            shot_before = output_dir / f"ui-fullchain-14-member-scan-before-{stamp}.png"
            shot_after = output_dir / f"ui-fullchain-15-member-scan-after-{stamp}.png"
            member_scan = onboarding.attempt_thread_scan_via_ui(
                member_flow,
                project_id=project_id,
                computer_id=second_computer_id,
                shot_before=shot_before,
                shot_after=shot_after,
            )
            report["steps"]["member_scan_threads"] = member_scan
            report["screenshots"]["member_scan_before"] = str(shot_before)
            report["screenshots"]["member_scan_after"] = str(shot_after)
            if not member_scan.get("scan_surfaced_threads"):
                raise RuntimeError(f"Member thread scan did not surface real threads: {member_scan}")

        owner_token, _owner_user = api_login(API_BASE, OWNER_EMAIL, OWNER_PASSWORD)

        owner_profile = new_browser_profile(runtime_dir, "owner-command")
        with BrowserRuntime(find_free_port(), owner_profile, VIEWPORT_WIDTH, VIEWPORT_HEIGHT) as owner_flow:
            shot = output_dir / f"ui-fullchain-16-owner-login-collab-{stamp}.png"
            login_via_ui(owner_flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=shot)
            report["screenshots"]["owner_login_collab"] = str(shot)

            shot = output_dir / f"ui-fullchain-17-create-bound-npc-{stamp}.png"
            npc_state = create_npc_via_ui(
                owner_flow,
                WEB_BASE,
                project_id=project_id,
                npc_name=npc_name,
                responsibility="负责在第二台电脑线程上接单并回写最小回执与最终回复。",
                computer_node_id=second_computer_id,
                source_workstation_id=member_thread_id,
                shot=shot,
            )
            report["steps"]["create_bound_npc"] = npc_state
            report["screenshots"]["create_bound_npc"] = str(shot)
            npc_seat_id = str(npc_state.get("seatId") or npc_name)

            shot_preview = output_dir / f"ui-fullchain-18-owner-command-preview-{stamp}.png"
            shot_sent = output_dir / f"ui-fullchain-19-owner-command-sent-{stamp}.png"
            shot_receipts = output_dir / f"ui-fullchain-20-owner-receipts-{stamp}.png"
            owner_command_chain = execute_command_chain_via_selected_npc(
                owner_flow,
                owner_token=owner_token,
                project_id=project_id,
                workstation_id=member_thread_id,
                npc_seat_id=npc_seat_id,
                command_title=command_title,
                command_body=command_body,
                ack_note=ack_note,
                final_note=final_note,
                shot_preview=shot_preview,
                shot_sent=shot_sent,
                shot_receipts=shot_receipts,
            )
            report["steps"]["owner_command_chain"] = owner_command_chain
            report["screenshots"]["owner_command_preview"] = str(shot_preview)
            report["screenshots"]["owner_command_sent"] = str(shot_sent)
            report["screenshots"]["owner_receipts"] = str(shot_receipts)

        member_profile = new_browser_profile(runtime_dir, "member-verify")
        with BrowserRuntime(find_free_port(), member_profile, VIEWPORT_WIDTH, VIEWPORT_HEIGHT) as member_flow:
            shot = output_dir / f"ui-fullchain-21-member-login-verify-{stamp}.png"
            login_via_ui(
                member_flow,
                WEB_BASE,
                email=collaborator_email,
                password=collaborator_password,
                shot=shot,
            )
            report["screenshots"]["member_login_verify"] = str(shot)

            shot_command = output_dir / f"ui-fullchain-22-member-command-visible-{stamp}.png"
            shot_receipts = output_dir / f"ui-fullchain-23-member-receipts-visible-{stamp}.png"
            member_visibility = {
                "command_state": verify_agent_command_visible_direct(
                    member_flow,
                    project_id=project_id,
                    command_title=command_title,
                    expected_sender=OWNER_NAME,
                    fallback_sender=OWNER_EMAIL,
                    shot=shot_command,
                ),
                "receipt_state": verify_receipts_visible_direct(
                    member_flow,
                    project_id=project_id,
                    command_title=command_title,
                    shot=shot_receipts,
                ),
            }
            report["steps"]["member_visible"] = member_visibility
            report["screenshots"]["member_command_visible"] = str(shot_command)
            report["screenshots"]["member_receipts_visible"] = str(shot_receipts)

        report_path = output_dir / f"ui-frontdoor-fullchain-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "report_path": str(report_path),
                    "project_id": project_id,
                    "command_title": command_title,
                    "issues": len(report["issues"]),
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
