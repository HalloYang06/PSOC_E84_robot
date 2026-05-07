from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DUAL_HELPER_PATH = SCRIPT_DIR / 'validate-dual-account-invite-collab-cdp.py'

spec = importlib.util.spec_from_file_location('dual_helper', DUAL_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f'Cannot load helper module: {DUAL_HELPER_PATH}')
dual_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dual_helper)

BrowserRuntime = dual_helper.BrowserRuntime
find_free_port = dual_helper.find_free_port
login_via_ui = dual_helper.login_via_ui
new_browser_profile = dual_helper.new_browser_profile
api_login = dual_helper.api_login
create_npc_via_ui = dual_helper.create_npc_via_ui
verify_shared_command_chain_visible = dual_helper.verify_shared_command_chain_visible
list_project_messages = dual_helper.list_project_messages
pick_message = dual_helper.pick_message
rotate_workstation_token = dual_helper.rotate_workstation_token
run_adapter = dual_helper.run_adapter
verify_receipts_visible = dual_helper.verify_receipts_visible
js_string = dual_helper.js_string
execute_command_chain_via_ui_and_adapter = dual_helper.execute_command_chain_via_ui_and_adapter

WEB_BASE = 'http://127.0.0.1:3000'
API_BASE = 'http://127.0.0.1:8010'
OWNER_EMAIL = 'lead@example.com'
OWNER_PASSWORD = 'password'
OWNER_NAME = 'Lead'
OUTPUT_DIR = REPO_ROOT / 'artifacts'
BOUND_NPC_PREFIX = '第二台电脑协作NPC-'


def find_message(messages: list[dict[str, object]], *, title: str, message_type: str) -> dict[str, object] | None:
    lowered_type = message_type.lower()
    for item in reversed(messages):
        if str(item.get('message_type') or '').lower() == lowered_type and str(item.get('title') or '') == title:
            return item
    return None


def click_via_expression(
    flow,
    expression: str,
    *,
    timeout_seconds: float = 20,
    interval_seconds: float = 0.3,
    label: str = 'element',
) -> None:
    point = flow.wait_for(expression, timeout_seconds=timeout_seconds, interval_seconds=interval_seconds)
    if not isinstance(point, dict) or 'x' not in point or 'y' not in point:
        raise RuntimeError(f'Could not resolve click target for {label}')
    x = float(point['x'])
    y = float(point['y'])
    flow.cdp.send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x, 'y': y})
    flow.cdp.send('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
    flow.cdp.send('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
    time.sleep(1.0)


def create_agent_command_via_selected_npc(
    flow,
    *,
    project_id: str,
    npc_seat_id: str,
    command_title: str,
    command_body: str,
    shot_preview: Path,
    shot_sent: Path,
) -> dict[str, object]:
    flow.navigate(f'{WEB_BASE}/projects/{project_id}?panel=team&tab=npc-create')
    flow.wait_for_selector('[data-npc-rail-seat]', timeout_seconds=45)
    click_via_expression(
        flow,
        f"""
        (() => {{
          const seat = Array.from(document.querySelectorAll('[data-npc-rail-seat]')).find(
            (node) => (node.getAttribute('data-npc-rail-seat') || '') === {js_string(npc_seat_id)}
          );
          if (!seat || ('disabled' in seat && seat.disabled)) return false;
          seat.scrollIntoView({{ block: 'center', inline: 'center' }});
          const rect = seat.getBoundingClientRect();
          if (!rect.width || !rect.height) return false;
          return {{ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
        label=f'NPC rail seat {npc_seat_id!r}',
    )
    dialog_opened_via_deep_link = False
    try:
        flow.wait_for(
            f"""
            (() => {{
              const selectedSeat = document.querySelector('[data-npc-manager-selected]')?.getAttribute('data-npc-manager-selected') || '';
              const selectedName = document.querySelector('[data-npc-manager-selected-name]')?.getAttribute('data-npc-manager-selected-name') || '';
              return selectedSeat === {js_string(npc_seat_id)} || selectedName === {js_string(npc_seat_id)};
            }})()
            """,
            timeout_seconds=12,
            interval_seconds=0.4,
        )
    except Exception:
        flow.navigate(
            f'{WEB_BASE}/projects/{project_id}?panel=team&tab=npc-create&seat={quote(npc_seat_id)}&drawer=npc-dialog&drawer_id={quote(npc_seat_id)}'
        )
        dialog_opened_via_deep_link = True
    if not dialog_opened_via_deep_link:
        click_via_expression(
            flow,
            """
            (() => {
              const button = document.querySelector('[data-npc-open-dialog="1"]');
              if (!button || ('disabled' in button && button.disabled)) return false;
              button.scrollIntoView({ block: 'center', inline: 'center' });
              const rect = button.getBoundingClientRect();
              if (!rect.width || !rect.height) return false;
              return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
            })()
            """,
            timeout_seconds=30,
            interval_seconds=0.3,
            label=f'NPC dialog button {npc_seat_id!r}',
        )
    dialog_form_expression = f"""
        (() => {{
          const form = Array.from(document.querySelectorAll('[data-npc-dialog-form]')).find(
            (node) => (node.getAttribute('data-npc-dialog-form') || '') === {js_string(npc_seat_id)}
          );
          return !!form && !!form.querySelector('input[name="title"]') && !!form.querySelector('textarea[name="body"]');
        }})()
        """
    try:
        flow.wait_for(dialog_form_expression, timeout_seconds=45, interval_seconds=0.4)
    except Exception:
        flow.navigate(
            f'{WEB_BASE}/projects/{project_id}?panel=team&tab=npc-create&seat={quote(npc_seat_id)}&drawer=npc-dialog&drawer_id={quote(npc_seat_id)}'
        )
        flow.wait_for(dialog_form_expression, timeout_seconds=45, interval_seconds=0.4)
    filled = flow.eval(
        f"""
        (() => {{
          const form = Array.from(document.querySelectorAll('[data-npc-dialog-form]')).find(
            (node) => (node.getAttribute('data-npc-dialog-form') || '') === {js_string(npc_seat_id)}
          );
          if (!form) return false;
          const title = form.querySelector('input[name="title"]');
          const body = form.querySelector('textarea[name="body"]');
          if (!title || !body) return false;
          title.focus();
          title.value = {js_string(command_title)};
          title.dispatchEvent(new Event('input', {{ bubbles: true }}));
          title.dispatchEvent(new Event('change', {{ bubbles: true }}));
          body.focus();
          body.value = {js_string(command_body)};
          body.dispatchEvent(new Event('input', {{ bubbles: true }}));
          body.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return true;
        }})()
        """
    )
    if not filled:
        raise RuntimeError(f'Could not fill NPC dialog command form for seat {npc_seat_id!r}')
    flow.screenshot(shot_preview)
    click_via_expression(
        flow,
        f"""
        (() => {{
          const button = Array.from(document.querySelectorAll('[data-npc-dialog-preview]')).find(
            (node) => (node.getAttribute('data-npc-dialog-preview') || '') === {js_string(npc_seat_id)}
          );
          if (!button || ('disabled' in button && button.disabled)) return false;
          button.scrollIntoView({{ block: 'center', inline: 'center' }});
          const rect = button.getBoundingClientRect();
          if (!rect.width || !rect.height) return false;
          return {{ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
        }})()
        """,
        timeout_seconds=30,
        interval_seconds=0.3,
        label=f'NPC preview button {npc_seat_id!r}',
    )
    flow.wait_for(
        f"""
        (() => {{
          const form = Array.from(document.querySelectorAll('[data-npc-dialog-form]')).find(
            (node) => (node.getAttribute('data-npc-dialog-form') || '') === {js_string(npc_seat_id)}
          );
          const field = form ? form.querySelector('input[name="required_preview_ready"]') : null;
          return field ? field.value === '1' : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    click_via_expression(
        flow,
        f"""
        (() => {{
          const button = Array.from(document.querySelectorAll('[data-npc-dialog-submit]')).find(
            (node) => (node.getAttribute('data-npc-dialog-submit') || '') === {js_string(npc_seat_id)}
          );
          if (!button || ('disabled' in button && button.disabled)) return false;
          button.scrollIntoView({{ block: 'center', inline: 'center' }});
          const rect = button.getBoundingClientRect();
          if (!rect.width || !rect.height) return false;
          return {{ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
        }})()
        """,
        timeout_seconds=30,
        interval_seconds=0.3,
        label=f'NPC submit button {npc_seat_id!r}',
    )
    flow.navigate(f'{WEB_BASE}/projects/{project_id}?panel=team&tab=exchange&exchange_section=dispatch')
    flow.wait_for_selector('[data-exchange-command-item], [data-exchange-section="dispatch"]', timeout_seconds=45)
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-exchange-command-item]')).map((item) => {{
            const title = item.getAttribute('data-exchange-command-title') || '';
            const sender = item.getAttribute('data-exchange-command-sender') || '';
            return {{ title, sender, card: (item.textContent || '').trim() }};
          }});
          return items.some((item) => item.title.includes({js_string(command_title)}))
            ? {{
                href: location.href,
                items,
                body: document.body ? document.body.innerText.slice(0, 4000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f'NPC dialog command {command_title!r} was not visible after submit')
    state['dialog_opened_via_deep_link'] = dialog_opened_via_deep_link
    flow.screenshot(shot_sent)
    return state


def create_agent_command_via_exchange_direct(
    flow,
    *,
    project_id: str,
    target_id: str,
    command_title: str,
    command_body: str,
    shot_preview: Path,
    shot_sent: Path,
) -> dict[str, object]:
    flow.navigate(f'{WEB_BASE}/projects/{project_id}?panel=team&tab=exchange&exchange_composer=dispatch')
    flow.wait_for_selector('[data-exchange-command-form] select[name="recipient_id"]', timeout_seconds=45)
    flow.set_select('[data-exchange-command-form] select[name="recipient_id"]', target_id)
    flow.fill('[data-exchange-command-form] input[name="title"]', command_title)
    flow.fill('[data-exchange-command-form] textarea[name="body"]', command_body)
    flow.screenshot(shot_preview)
    click_via_expression(
        flow,
        """
        (() => {
          const buttons = Array.from(document.querySelectorAll('[data-exchange-command-form] button'));
          const button = buttons[0];
          if (!button || button.disabled) return false;
          button.scrollIntoView({ block: 'center', inline: 'center' });
          const rect = button.getBoundingClientRect();
          if (!rect.width || !rect.height) return false;
          return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        })()
        """,
        timeout_seconds=30,
        interval_seconds=0.3,
        label='exchange preview button',
    )
    flow.wait_for(
        """
        (() => {
          const ready = document.querySelector('[data-exchange-command-form] input[name="required_preview_ready"]')?.value || '';
          const signature = document.querySelector('[data-exchange-command-form] input[name="required_preview_signature"]')?.value || '';
          const buttons = Array.from(document.querySelectorAll('[data-exchange-command-form] button'));
          const submit = buttons[1];
          return ready === '1' && !!signature && !!submit && !submit.disabled;
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    click_via_expression(
        flow,
        """
        (() => {
          const buttons = Array.from(document.querySelectorAll('[data-exchange-command-form] button'));
          const button = buttons[1];
          if (!button || button.disabled) return false;
          button.scrollIntoView({ block: 'center', inline: 'center' });
          const rect = button.getBoundingClientRect();
          if (!rect.width || !rect.height) return false;
          return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        })()
        """,
        timeout_seconds=30,
        interval_seconds=0.3,
        label='exchange submit button',
    )
    state = flow.wait_for(
        f"""
        (() => {{
          const banner = document.querySelector('[class*="successBanner"]');
          const text = banner ? (banner.textContent || '').trim() : '';
          return text.includes({js_string(command_title)})
            ? {{
                href: location.href,
                successBanner: text,
                errorBanner: document.querySelector('[class*="errorBanner"]')?.textContent || '',
                body: document.body ? document.body.innerText.slice(0, 5000) : '',
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f'Exchange command {command_title!r} did not surface success banner after submit')
    flow.screenshot(shot_sent)
    return state


def verify_agent_command_visible_direct(
    flow,
    *,
    project_id: str,
    command_title: str,
    expected_sender: str,
    fallback_sender: str,
    shot: Path,
) -> dict[str, object]:
    flow.navigate(f'{WEB_BASE}/projects/{project_id}?panel=team&tab=exchange&exchange_section=dispatch')
    flow.wait_for_selector('[data-exchange-command-item], [data-exchange-section=\"dispatch\"]', timeout_seconds=45)
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-exchange-command-item]')).map((item) => {{
            const title = item.getAttribute('data-exchange-command-title') || '';
            const sender = item.getAttribute('data-exchange-command-sender') || '';
            return {{ title, sender, card: (item.textContent || '').trim() }};
          }});
          return items.some((item) => item.title.includes({js_string(command_title)}))
            ? {{ items, body: document.body ? document.body.innerText.slice(0, 4000) : '' }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f'Command {command_title!r} was not visible in direct dispatch section route')
    match = next((item for item in state.get('items', []) if isinstance(item, dict) and command_title in str(item.get('title') or '')), None)
    if not isinstance(match, dict):
        raise RuntimeError(f'Could not resolve command row for {command_title!r}')
    sender = str(match.get('sender') or '')
    if expected_sender not in sender and fallback_sender not in sender:
        raise RuntimeError(f'Command sender mismatch: expected {expected_sender!r} or {fallback_sender!r}, got {sender!r}')
    flow.screenshot(shot)
    return state


def verify_receipts_visible_direct(
    flow,
    *,
    project_id: str,
    command_title: str,
    shot: Path,
) -> dict[str, object]:
    flow.navigate(f'{WEB_BASE}/projects/{project_id}?panel=team&tab=exchange&exchange_section=receipts')
    flow.wait_for_selector('[data-exchange-receipt-item], [data-exchange-section=\"receipts\"]', timeout_seconds=45)
    state = flow.wait_for(
        f"""
        (() => {{
          const items = Array.from(document.querySelectorAll('[data-exchange-receipt-item]')).map((item) => {{
            const title = item.getAttribute('data-exchange-receipt-title') || '';
            const kind = item.getAttribute('data-exchange-receipt-kind') || '';
            const sender = item.getAttribute('data-exchange-receipt-sender') || '';
            return {{ title, kind, sender, card: (item.textContent || '').trim() }};
          }});
          const hasAck = items.some((item) => item.title === {js_string(command_title)} && item.kind === '最小回执');
          const finalItems = items.filter((item) => item.title === {js_string(command_title)} && item.kind === '最终回复');
          const hasCompletedResult = finalItems.some((item) => item.card.includes('状态：completed'));
          return hasAck && hasCompletedResult
            ? {{ items, body: document.body ? document.body.innerText.slice(0, 4000) : '' }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f'Receipts for {command_title!r} were not visible in direct receipts route')
    flow.screenshot(shot)
    return state


def execute_command_chain_via_selected_npc(
    flow,
    *,
    owner_token: str,
    project_id: str,
    workstation_id: str,
    npc_seat_id: str,
    command_title: str,
    command_body: str,
    ack_note: str,
    final_note: str,
    shot_preview: Path,
    shot_sent: Path,
    shot_receipts: Path,
) -> dict[str, object]:
    current_step = 'open_npc_dialog'
    try:
        command_state = create_agent_command_via_selected_npc(
            flow,
            project_id=project_id,
            npc_seat_id=npc_seat_id,
            command_title=command_title,
            command_body=command_body,
            shot_preview=shot_preview,
            shot_sent=shot_sent,
        )
        current_step = 'load_command_message'
        messages_after_command = list_project_messages(API_BASE, project_id, owner_token)
        command_message = pick_message(messages_after_command, title=command_title, message_type='agent_command')
        current_step = 'rotate_workstation_token'
        token_status = rotate_workstation_token(
            API_BASE,
            project_id=project_id,
            workstation_id=workstation_id,
            token=owner_token,
        )
        workstation_token = str(token_status.get('token') or '').strip()
        if not workstation_token:
            raise RuntimeError(f'Workstation adapter token was not returned: {token_status}')
        current_step = 'run_adapter'
        adapter_result = run_adapter(
            api_base=API_BASE,
            project_id=project_id,
            workstation_id=workstation_id,
            output_dir=shot_receipts.parent / 'ui-frontdoor-collab-inbox',
            workstation_token=workstation_token,
            ack_note=ack_note,
            final_note=final_note,
        )
        current_step = 'verify_receipts'
        receipt_state = verify_receipts_visible_direct(
            flow,
            project_id=project_id,
            command_title=command_title,
            shot=shot_receipts,
        )
        current_step = 'load_receipt_messages'
        messages_after_receipts = list_project_messages(API_BASE, project_id, owner_token)
        ack_message = pick_message(messages_after_receipts, title=command_title, message_type='agent_ack')
        result_message = pick_message(messages_after_receipts, title=command_title, message_type='agent_result')
        return {
            'command_state': command_state,
            'command_message': command_message,
            'token_status': token_status,
            'adapter_result': adapter_result,
            'receipt_state': receipt_state,
            'ack_message': ack_message,
            'result_message': result_message,
        }
    except Exception as exc:
        raise RuntimeError(f'{current_step}: {exc}') from exc


def find_existing_bound_npc(flow, *, project_id: str) -> dict[str, object] | None:
    flow.navigate(f'{WEB_BASE}/projects/{project_id}?panel=team&tab=npc-create')
    flow.wait_for_selector('[data-npc-rail-seat]', timeout_seconds=45)
    state = flow.eval(
        f"""
        (() => {{
          const seats = Array.from(document.querySelectorAll('[data-npc-rail-seat]')).map((item) => ({{
            seat: item.getAttribute('data-npc-rail-seat') || '',
            text: (item.textContent || '').trim(),
          }}));
          const matches = seats.filter((item) => item.seat.startsWith({js_string(BOUND_NPC_PREFIX)}));
          return matches.length ? matches[matches.length - 1] : null;
        }})()
        """
    )
    return state if isinstance(state, dict) else None


def pick_latest_onboarding_report() -> Path:
    reports = sorted(OUTPUT_DIR.glob('ui-frontdoor-onboarding-report-*.json'))
    if not reports:
        raise RuntimeError('No ui-frontdoor onboarding report found')
    return reports[-1]


def main() -> int:
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    runtime_dir = Path(tempfile.mkdtemp(prefix='ui-frontdoor-collab-'))
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    source_report = pick_latest_onboarding_report()
    source = json.loads(source_report.read_text(encoding='utf-8'))

    project_id = str(source['steps']['create_project']['project_id'])
    collaborator_email = str(source['steps']['invite_collaborator']['invitee_email'])
    collaborator_password = 'password123'
    member_computer_id = str(source['steps']['member_pairing_token']['pairingNode'])
    member_thread_candidates = source['steps']['member_scan_threads']['after']['previewThreads']
    member_thread_id = str(member_thread_candidates[0])
    owner_sync_command = source['steps']['owner_runner_onboarding']['sync']['command']
    member_sync_command = source['steps']['member_runner_onboarding']['sync']['command']
    owner_workspace = Path(str(owner_sync_command[-1]))
    member_workspace = Path(str(member_sync_command[-1]))
    owner_workspace.mkdir(parents=True, exist_ok=True)
    member_workspace.mkdir(parents=True, exist_ok=True)

    owner_token, _owner_user = api_login(API_BASE, OWNER_EMAIL, OWNER_PASSWORD)

    npc_name = f'{BOUND_NPC_PREFIX}{stamp[-6:]}'
    npc_responsibility = '负责验证前台新建项目后，第二台电脑线程可以直接经由 NPC 接单并回写回执。'
    command_title = f'前台协作接单验证-{stamp[-6:]}'
    command_body = '请先回最小回执，再说明第二台电脑线程已经接单，并给出一句简短中文最终回复。'

    report = {
        'stamp': stamp,
        'source_report': str(source_report),
        'project_id': project_id,
        'collaborator_email': collaborator_email,
        'member_computer_id': member_computer_id,
        'member_thread_id': member_thread_id,
        'owner_workspace': str(owner_workspace),
        'member_workspace': str(member_workspace),
        'screenshots': {},
        'steps': {},
        'issues': [],
    }

    try:
        owner_profile = new_browser_profile(runtime_dir, 'owner')
        with BrowserRuntime(find_free_port(), owner_profile, 1720, 1080) as owner_flow:
            shot = output_dir / f'ui-frontdoor-collab-01-owner-login-{stamp}.png'
            login_via_ui(owner_flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=shot)
            report['screenshots']['owner_login'] = str(shot)

            shot = output_dir / f'ui-frontdoor-collab-02-owner-create-bound-npc-{stamp}.png'
            existing_npc = find_existing_bound_npc(owner_flow, project_id=project_id)
            if existing_npc:
                owner_flow.screenshot(shot)
                npc_state = {
                    'seatId': str(existing_npc.get('seat') or ''),
                    'reused': True,
                    'body': str(existing_npc.get('text') or ''),
                }
            else:
                npc_state = create_npc_via_ui(
                    owner_flow,
                    WEB_BASE,
                    project_id=project_id,
                    npc_name=npc_name,
                    responsibility=npc_responsibility,
                    computer_node_id=member_computer_id,
                    source_workstation_id=member_thread_id,
                    shot=shot,
                )
            report['steps']['create_bound_npc'] = npc_state
            report['screenshots']['create_bound_npc'] = str(shot)
            npc_seat_id = str(npc_state.get('seatId') or npc_name)

            shot_preview = output_dir / f'ui-frontdoor-collab-03-owner-npc-command-preview-{stamp}.png'
            shot_sent = output_dir / f'ui-frontdoor-collab-04-owner-npc-command-sent-{stamp}.png'
            shot_receipts = output_dir / f'ui-frontdoor-collab-05-owner-npc-receipts-{stamp}.png'
            command_mode = 'npc-dialog'
            try:
                command_chain = execute_command_chain_via_selected_npc(
                    owner_flow,
                    owner_token=owner_token,
                    project_id=project_id,
                    workstation_id=member_thread_id,
                    npc_seat_id=npc_seat_id,
                    command_title=command_title,
                    command_body=command_body,
                    ack_note='前台新项目协作链最小回执已回。',
                    final_note='第二台电脑线程已接单并完成前台协作链最终回复。',
                    shot_preview=shot_preview,
                    shot_sent=shot_sent,
                    shot_receipts=shot_receipts,
                )
            except Exception as exc:
                messages_after_error = list_project_messages(API_BASE, project_id, owner_token)
                existing_command = find_message(
                    messages_after_error,
                    title=command_title,
                    message_type='agent_command',
                )
                if existing_command is not None:
                    owner_command_state = verify_agent_command_visible_direct(
                        owner_flow,
                        project_id=project_id,
                        command_title=command_title,
                        expected_sender=OWNER_NAME,
                        fallback_sender=OWNER_EMAIL,
                        shot=shot_sent,
                    )
                    token_status = rotate_workstation_token(
                        API_BASE,
                        project_id=project_id,
                        workstation_id=member_thread_id,
                        token=owner_token,
                    )
                    workstation_token = str(token_status.get('token') or '').strip()
                    if not workstation_token:
                        raise RuntimeError(f'Workstation adapter token was not returned: {token_status}')
                    adapter_result = run_adapter(
                        api_base=API_BASE,
                        project_id=project_id,
                        workstation_id=member_thread_id,
                        output_dir=shot_receipts.parent / 'ui-frontdoor-collab-inbox',
                        workstation_token=workstation_token,
                        ack_note='前台新项目协作链最小回执已回。',
                        final_note='第二台电脑线程已接单并完成前台协作链最终回复。',
                    )
                    receipt_state = verify_receipts_visible_direct(
                        owner_flow,
                        project_id=project_id,
                        command_title=command_title,
                        shot=shot_receipts,
                    )
                    messages_after_receipts = list_project_messages(API_BASE, project_id, owner_token)
                    ack_message = pick_message(messages_after_receipts, title=command_title, message_type='agent_ack')
                    result_message = pick_message(messages_after_receipts, title=command_title, message_type='agent_result')
                    command_chain = {
                        'command_state': owner_command_state,
                        'command_message': existing_command,
                        'token_status': token_status,
                        'adapter_result': adapter_result,
                        'receipt_state': receipt_state,
                        'ack_message': ack_message,
                        'result_message': result_message,
                        'recovery': {
                            'mode': 'post-send-verification',
                            'detail': str(exc),
                        },
                    }
                else:
                    command_mode = 'exchange-fallback'
                    report['issues'].append({
                        'step': 'npc_dialog_dispatch',
                        'severity': 'medium',
                        'summary': '新创建并绑定线程的 NPC 从二级对象栏切到对话框时不稳定，已回退到协作消息池直发线程继续验证。',
                        'detail': str(exc),
                    })
                    send_state = create_agent_command_via_exchange_direct(
                        owner_flow,
                        project_id=project_id,
                        target_id=member_thread_id,
                        command_title=command_title,
                        command_body=command_body,
                        shot_preview=shot_preview,
                        shot_sent=shot_sent,
                    )
                    command_message = pick_message(
                        list_project_messages(API_BASE, project_id, owner_token),
                        title=command_title,
                        message_type='agent_command',
                    )
                    token_status = rotate_workstation_token(
                        API_BASE,
                        project_id=project_id,
                        workstation_id=member_thread_id,
                        token=owner_token,
                    )
                    workstation_token = str(token_status.get('token') or '').strip()
                    if not workstation_token:
                        raise RuntimeError(f'Workstation adapter token was not returned: {token_status}')
                    adapter_result = run_adapter(
                        api_base=API_BASE,
                        project_id=project_id,
                        workstation_id=member_thread_id,
                        output_dir=shot_receipts.parent / 'ui-frontdoor-collab-inbox',
                        workstation_token=workstation_token,
                        ack_note='前台新项目协作链最小回执已回。',
                        final_note='第二台电脑线程已接单并完成前台协作链最终回复。',
                    )
                    owner_command_state = verify_agent_command_visible_direct(
                        owner_flow,
                        project_id=project_id,
                        command_title=command_title,
                        expected_sender=OWNER_NAME,
                        fallback_sender=OWNER_EMAIL,
                        shot=shot_sent,
                    )
                    receipt_state = verify_receipts_visible_direct(
                        owner_flow,
                        project_id=project_id,
                        command_title=command_title,
                        shot=shot_receipts,
                    )
                    messages_after_receipts = list_project_messages(API_BASE, project_id, owner_token)
                    ack_message = pick_message(messages_after_receipts, title=command_title, message_type='agent_ack')
                    result_message = pick_message(messages_after_receipts, title=command_title, message_type='agent_result')
                    command_chain = {
                        'command_state': owner_command_state,
                        'send_state': send_state,
                        'command_message': command_message,
                        'token_status': token_status,
                        'adapter_result': adapter_result,
                        'receipt_state': receipt_state,
                        'ack_message': ack_message,
                        'result_message': result_message,
                    }
            report['steps']['owner_command_chain'] = command_chain
            report['steps']['command_mode'] = command_mode
            report['screenshots']['owner_command_preview'] = str(shot_preview)
            report['screenshots']['owner_command_sent'] = str(shot_sent)
            report['screenshots']['owner_receipts'] = str(shot_receipts)

        member_profile = new_browser_profile(runtime_dir, 'member')
        with BrowserRuntime(find_free_port(), member_profile, 1720, 1080) as member_flow:
            shot = output_dir / f'ui-frontdoor-collab-06-member-login-{stamp}.png'
            login_via_ui(member_flow, WEB_BASE, email=collaborator_email, password=collaborator_password, shot=shot)
            report['screenshots']['member_login'] = str(shot)

            shot_cmd = output_dir / f'ui-frontdoor-collab-07-member-command-visible-{stamp}.png'
            shot_receipts = output_dir / f'ui-frontdoor-collab-08-member-receipts-visible-{stamp}.png'
            member_command = verify_agent_command_visible_direct(
                member_flow,
                project_id=project_id,
                command_title=command_title,
                expected_sender=OWNER_NAME,
                fallback_sender=OWNER_EMAIL,
                shot=shot_cmd,
            )
            member_receipts = verify_receipts_visible_direct(
                member_flow,
                project_id=project_id,
                command_title=command_title,
                shot=shot_receipts,
            )
            member_visible = {
                'command_state': member_command,
                'receipt_state': member_receipts,
            }
            report['steps']['member_visible'] = member_visible
            report['screenshots']['member_command_visible'] = str(shot_cmd)
            report['screenshots']['member_receipts_visible'] = str(shot_receipts)

        report_path = output_dir / f'ui-frontdoor-collab-report-{stamp}.json'
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'report_path': str(report_path), 'project_id': project_id, 'command_title': command_title, 'issues': len(report['issues'])}, ensure_ascii=False))
        return 0
    finally:
        import shutil
        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
