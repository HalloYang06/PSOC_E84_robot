from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
HELPER_PATH = SCRIPT_DIR / 'validate-dual-account-invite-collab-cdp.py'

spec = importlib.util.spec_from_file_location('dual_helper', HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f'Cannot load helper module: {HELPER_PATH}')
dual_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dual_helper)

BrowserRuntime = dual_helper.BrowserRuntime
BrowserFlow = dual_helper.BrowserFlow
find_free_port = dual_helper.find_free_port
register_via_ui = dual_helper.register_via_ui
login_via_ui = dual_helper.login_via_ui
ensure_logged_in = dual_helper.ensure_logged_in
create_computer_via_ui = dual_helper.create_computer_via_ui
invite_via_ui = dual_helper.invite_via_ui
accept_invite_via_ui = dual_helper.accept_invite_via_ui
verify_projects_plaza = dual_helper.verify_projects_plaza
create_npc_via_ui = dual_helper.create_npc_via_ui
js_string = dual_helper.js_string

WEB_BASE = os.environ.get('WEB_BASE', 'http://127.0.0.1:3001')
API_BASE = os.environ.get('API_BASE', 'http://127.0.0.1:8011')
OUTPUT_DIR = REPO_ROOT / 'artifacts'
VIEWPORT_WIDTH = 1720
VIEWPORT_HEIGHT = 1080
OWNER_EMAIL = os.environ.get('OWNER_EMAIL', 'lead@example.com')
OWNER_PASSWORD = os.environ.get('OWNER_PASSWORD', 'password')
OWNER_NAME = os.environ.get('OWNER_NAME', 'Lead')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Validate frontdoor onboarding through the real UI.')
    parser.add_argument('--web-base', default=WEB_BASE)
    parser.add_argument('--api-base', default=API_BASE)
    parser.add_argument('--owner-email', default=OWNER_EMAIL)
    parser.add_argument('--owner-password', default=OWNER_PASSWORD)
    parser.add_argument('--owner-name', default=OWNER_NAME)
    parser.add_argument('--output-dir', default=str(OUTPUT_DIR))
    return parser.parse_args()


def create_project_via_ui_pure(
    flow: BrowserFlow,
    *,
    project_name: str,
    description: str,
    shot: Path,
) -> dict[str, object]:
    flow.navigate(f'{WEB_BASE}/projects?tab=create')
    ready = flow.wait_for(
        """
        (() => {
          const state = {
            href: location.href,
            pathname: location.pathname,
            readyState: document.readyState,
            body: document.body ? document.body.innerText.slice(0, 2000) : '',
            hasNameInput: !!document.querySelector('form input[name="name"]'),
            hasCreateTab: Array.from(document.querySelectorAll('button')).some((item) =>
              ((item.innerText || item.textContent || '')).includes('新建项目')
            ),
          };
          return (state.hasNameInput || state.hasCreateTab || state.body.trim().length > 0)
            ? state
            : false;
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if isinstance(ready, dict) and not ready.get('hasNameInput'):
        opened = flow.eval(
            """
            (() => {
              const button = Array.from(document.querySelectorAll('button')).find((item) =>
                ((item.innerText || item.textContent || '')).includes('新建项目')
              );
              if (!button) return false;
              button.click();
              return true;
            })()
            """
        )
        if not opened:
            raise RuntimeError(f'Projects plaza did not expose the create-project entry: {ready}')
    flow.wait_for_selector('form input[name="name"]', timeout_seconds=45)
    flow.fill('form input[name="name"]', project_name)
    flow.fill('form textarea[name="description"]', description)
    flow.screenshot(shot)
    flow.submit_closest_form('form input[name="name"]')
    state = flow.wait_for(
        f"""
        (() => {{
          if (location.pathname.startsWith('/projects/')) {{
            return {{
              href: location.href,
              source: 'location',
              body: document.body ? document.body.innerText.slice(0, 2000) : '',
            }};
          }}
          const link = Array.from(document.querySelectorAll('a[href*="/projects/"]')).find((item) =>
            ((item.innerText || item.textContent || '')).includes({js_string(project_name)})
          );
          if (!link) return false;
          const href = link.href || link.getAttribute('href') || '';
          return href
            ? {{ href, source: 'link', body: document.body ? document.body.innerText.slice(0, 2000) : '' }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f'Could not resolve project id from UI state: {state}')
    href = str(state.get('href') or '').strip()
    if not href:
        raise RuntimeError(f'Project UI state did not include href: {state}')
    parsed = urlparse(href)
    marker = '/projects/'
    if marker not in parsed.path:
        raise RuntimeError(f'Project href did not include /projects/: {href}')
    project_id = parsed.path.split(marker, 1)[1].split('/', 1)[0].strip()
    if not project_id:
        raise RuntimeError(f'Could not parse project id from href: {href}')
    return {
        'project_id': project_id,
        'href': href,
        'source': str(state.get('source') or ''),
        'body': str(state.get('body') or ''),
    }


def open_project_map(flow: BrowserFlow, *, project_id: str, shot: Path) -> dict[str, object]:
    flow.navigate(f'{WEB_BASE}/projects/{project_id}')
    flow.wait_for_selector('iframe[src*="harvest-moon-phaser3-game/index.html"]', timeout_seconds=45)
    flow.screenshot(shot)
    state = flow.eval(
        """
        (() => ({
          href: location.href,
          title: document.title,
          body: document.body ? document.body.innerText.slice(0, 2000) : '',
        }))()
        """
    )
    return state if isinstance(state, dict) else {}


def open_computer_threads_drawer(flow: BrowserFlow, *, project_id: str, computer_id: str) -> None:
    flow.navigate(f'{WEB_BASE}/projects/{project_id}?panel=team&tab=computers')
    flow.wait_for_selector('[data-computer-rail-item]', timeout_seconds=45)
    selected = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-rail-item={js_string(computer_id)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """
    )
    if not selected:
        raise RuntimeError(f'Could not select computer {computer_id!r}')
    time.sleep(0.6)
    opened = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-open-threads={js_string(computer_id)}]');
          if (!button || button.disabled) return false;
          button.click();
          return true;
        }})()
        """
    )
    if not opened:
        raise RuntimeError(f'Could not open threads drawer for {computer_id!r}')
    flow.wait_for_selector(f'[data-computer-threads-drawer="{computer_id}"]', timeout_seconds=45)


def generate_pairing_token_via_ui_pure(flow: BrowserFlow, *, project_id: str, computer_id: str, shot: Path) -> dict[str, object]:
    open_computer_threads_drawer(flow, project_id=project_id, computer_id=computer_id)
    clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-generate-pairing={js_string(computer_id)}]');
          if (!button || button.disabled) return false;
          button.click();
          return true;
        }})()
        """
    )
    if not clicked:
        raise RuntimeError(f'Could not generate pairing token for {computer_id!r}')
    state = flow.wait_for(
        f"""
        (() => {{
          const banner = document.querySelector('[data-computer-pairing-banner="true"]');
          const url = new URL(location.href);
          const token = url.searchParams.get('pairing_token') || '';
          const nodeId = url.searchParams.get('pairing_node') || '';
          return token && nodeId === {js_string(computer_id)}
            ? {{
                pairingToken: token,
                pairingNode: nodeId,
                bannerText: banner ? (banner.textContent || '').trim() : '',
                href: location.href,
              }}
            : false;
        }})()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f'Could not resolve pairing token for {computer_id!r}: {state}')
    guide_state = flow.eval(
        f"""
        (() => {{
          const guide = document.querySelector('[data-computer-onboarding-guide={js_string(computer_id)}]');
          const oneClick = document.querySelector('[data-computer-one-click-connect-command={js_string(computer_id)}]');
          const register = document.querySelector('[data-computer-register-command={js_string(computer_id)}]');
          const codexSync = document.querySelector('[data-computer-codex-sync-command={js_string(computer_id)}]');
          const manualSync = document.querySelector('[data-computer-manual-sync-command={js_string(computer_id)}]');
          return {{
            guideVisible: Boolean(guide),
            oneClickCommand: oneClick ? (oneClick.textContent || '').trim() : '',
            registerCommand: register ? (register.textContent || '').trim() : '',
            codexSyncCommand: codexSync ? (codexSync.textContent || '').trim() : '',
            manualSyncCommand: manualSync ? (manualSync.textContent || '').trim() : '',
          }};
        }})()
        """
    )
    flow.screenshot(shot)
    result = dict(state)
    if isinstance(guide_state, dict):
        result['guide'] = guide_state
    return result


def run_powershell_script(script_name: str, *args: str) -> dict[str, object]:
    command = [
        'powershell.exe',
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        str(REPO_ROOT / 'scripts' / script_name),
        *args,
    ]
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=180,
        check=False,
    )
    return {
        'command': command,
        'returncode': completed.returncode,
        'stdout': completed.stdout,
        'stderr': completed.stderr,
    }


def onboard_runner_via_user_scripts(
    *,
    server: str,
    pairing_token: str,
    computer_node_id: str,
    project_id: str,
    runner_id: str,
    runner_name: str,
    thread_id: str,
    thread_name: str,
    cwd: str,
) -> dict[str, object]:
    register_result = run_powershell_script(
        'register-runner.ps1',
        '-Server',
        server,
        '-PairingToken',
        pairing_token,
        '-ComputerNodeId',
        computer_node_id,
        '-RunnerName',
        runner_name,
        '-RunnerId',
        runner_id,
    )
    if int(register_result.get('returncode', 1)) != 0:
        raise RuntimeError(f'Runner registration failed for {computer_node_id}: {register_result}')
    sync_result = run_powershell_script(
        'sync-runner-threads.ps1',
        '-Server',
        server,
        '-RunnerId',
        runner_id,
        '-ProjectId',
        project_id,
        '-ComputerNodeId',
        computer_node_id,
        '-ThreadId',
        thread_id,
        '-ThreadName',
        thread_name,
        '-Cwd',
        cwd,
    )
    if int(sync_result.get('returncode', 1)) != 0:
        raise RuntimeError(f'Runner thread sync failed for {computer_node_id}: {sync_result}')
    return {
        'register': register_result,
        'sync': sync_result,
    }


def attempt_thread_scan_via_ui(flow: BrowserFlow, *, project_id: str, computer_id: str, shot_before: Path, shot_after: Path) -> dict[str, object]:
    open_computer_threads_drawer(flow, project_id=project_id, computer_id=computer_id)
    before = flow.eval(
        f"""
        (() => {{
          const status = document.querySelector('[data-computer-thread-scan-status={js_string(computer_id)}]');
          return {{
            previewThreads: Array.from(document.querySelectorAll('[data-computer-drawer-thread-item]')).map((item) => item.getAttribute('data-computer-drawer-thread-item') || ''),
            statusText: status ? (status.textContent || '').trim() : '',
            body: document.body ? document.body.innerText.slice(0, 2000) : '',
          }};
        }})()
        """
    )
    flow.screenshot(shot_before)
    clicked = flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-request-scan={js_string(computer_id)}]');
          if (!button || button.disabled) return false;
          button.click();
          return true;
        }})()
        """
    )
    if not clicked:
        return {
            'clicked': False,
            'reason': 'scan-button-disabled-or-missing',
            'before': before,
        }
    time.sleep(2.0)
    flow.navigate(f'{WEB_BASE}/projects/{project_id}?panel=team&tab=computers')
    flow.wait_for_selector('[data-computer-rail-item]', timeout_seconds=45)
    flow.eval(
        f"""
        (() => {{
          const button = document.querySelector('[data-computer-rail-item={js_string(computer_id)}]');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """
    )
    time.sleep(0.6)
    after = flow.eval(
        f"""
        (() => {{
          const status = document.querySelector('[data-computer-thread-scan-status={js_string(computer_id)}]');
          const previewFor = document.querySelector('[data-computer-thread-preview-for]')?.getAttribute('data-computer-thread-preview-for') || '';
          return {{
            previewFor,
            previewThreads: Array.from(document.querySelectorAll('[data-computer-thread-item]')).map((item) => item.getAttribute('data-computer-thread-item') || ''),
            drawerThreads: Array.from(document.querySelectorAll('[data-computer-drawer-thread-item]')).map((item) => item.getAttribute('data-computer-drawer-thread-item') || ''),
            statusText: status ? (status.textContent || '').trim() : '',
            pairingBanner: (() => {{
              const banner = document.querySelector('[data-computer-pairing-banner="true"]');
              return banner ? (banner.textContent || '').trim() : '';
            }})(),
            body: document.body ? document.body.innerText.slice(0, 3000) : '',
          }};
        }})()
        """
    )
    flow.screenshot(shot_after)
    after_dict = after if isinstance(after, dict) else {}
    threads = [str(item) for item in after_dict.get('previewThreads', []) if isinstance(item, str)]
    return {
        'clicked': True,
        'before': before if isinstance(before, dict) else {},
        'after': after_dict,
        'thread_count': len(threads),
        'scan_surfaced_threads': bool(threads),
    }


def main() -> int:
    global WEB_BASE, API_BASE, OWNER_EMAIL, OWNER_PASSWORD, OWNER_NAME, OUTPUT_DIR
    args = parse_args()
    WEB_BASE = str(args.web_base).rstrip('/')
    API_BASE = str(args.api_base).rstrip('/')
    OWNER_EMAIL = str(args.owner_email)
    OWNER_PASSWORD = str(args.owner_password)
    OWNER_NAME = str(args.owner_name)
    OUTPUT_DIR = Path(str(args.output_dir))
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix='ui-frontdoor-flow-'))
    report: dict[str, object] = {
        'stamp': stamp,
        'web_base': WEB_BASE,
        'api_base': API_BASE,
        'steps': {},
        'issues': [],
        'screenshots': {},
    }
    collaborator_email = f'ui-collab-{stamp}@local.dev'
    collaborator_password = 'password123'
    collaborator_name = 'UI Collaborator'
    project_name = f'UI前台验收项目-{stamp[-6:]}'
    first_computer_id = f'ui-pc-a-{stamp[-6:]}'
    second_computer_id = f'ui-pc-b-{stamp[-6:]}'
    owner_runner_id = f'runner-owner-{stamp[-6:]}'
    member_runner_id = f'runner-member-{stamp[-6:]}'
    owner_thread_id = f'owner-codex-{stamp[-6:]}'
    member_thread_id = f'member-codex-{stamp[-6:]}'
    first_workspace = runtime_dir / 'owner-workspace'
    second_workspace = runtime_dir / 'member-workspace'
    first_workspace.mkdir(parents=True, exist_ok=True)
    second_workspace.mkdir(parents=True, exist_ok=True)
    try:
        owner_profile = dual_helper.new_browser_profile(runtime_dir, 'owner')
        with BrowserRuntime(find_free_port(), owner_profile, VIEWPORT_WIDTH, VIEWPORT_HEIGHT) as owner_flow:
            shot = output_dir / f'ui-frontdoor-01-owner-login-{stamp}.png'
            login_via_ui(owner_flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=shot)
            report['screenshots']['owner_login'] = str(shot)

            shot = output_dir / f'ui-frontdoor-02-create-project-{stamp}.png'
            project_state = create_project_via_ui_pure(
                owner_flow,
                project_name=project_name,
                description='从真实前端走项目、新电脑、线程扫描、NPC、邀请协作者、第二台电脑。',
                shot=shot,
            )
            project_id = str(project_state['project_id'])
            report['steps']['create_project'] = project_state
            report['screenshots']['create_project'] = str(shot)

            shot = output_dir / f'ui-frontdoor-03-project-map-{stamp}.png'
            map_state = open_project_map(owner_flow, project_id=project_id, shot=shot)
            report['steps']['project_map'] = map_state
            report['screenshots']['project_map'] = str(shot)

            shot = output_dir / f'ui-frontdoor-04-owner-computer-create-{stamp}.png'
            owner_computer_state = create_computer_via_ui(
                owner_flow,
                WEB_BASE,
                project_id=project_id,
                computer_id=first_computer_id,
                label='Owner Validation PC',
                workspace_root=str(first_workspace),
                git_root=str(first_workspace),
                shot=shot,
            )
            report['steps']['owner_computer_create'] = owner_computer_state
            report['screenshots']['owner_computer_create'] = str(shot)

            shot = output_dir / f'ui-frontdoor-05-owner-pairing-token-{stamp}.png'
            pairing_state = generate_pairing_token_via_ui_pure(owner_flow, project_id=project_id, computer_id=first_computer_id, shot=shot)
            report['steps']['owner_pairing_token'] = pairing_state
            report['screenshots']['owner_pairing_token'] = str(shot)
            report['steps']['owner_runner_onboarding'] = onboard_runner_via_user_scripts(
                server=API_BASE,
                pairing_token=str(pairing_state.get('pairingToken') or ''),
                computer_node_id=first_computer_id,
                project_id=project_id,
                runner_id=owner_runner_id,
                runner_name='Owner Validation Runner',
                thread_id=owner_thread_id,
                thread_name='Owner Codex Mainline',
                cwd=str(first_workspace),
            )

            shot_before = output_dir / f'ui-frontdoor-06-owner-scan-before-{stamp}.png'
            shot_after = output_dir / f'ui-frontdoor-07-owner-scan-after-{stamp}.png'
            scan_state = attempt_thread_scan_via_ui(
                owner_flow,
                project_id=project_id,
                computer_id=first_computer_id,
                shot_before=shot_before,
                shot_after=shot_after,
            )
            report['steps']['owner_scan_threads'] = scan_state
            report['screenshots']['owner_scan_before'] = str(shot_before)
            report['screenshots']['owner_scan_after'] = str(shot_after)
            if not scan_state.get('scan_surfaced_threads'):
                report['issues'].append({
                    'step': 'owner_scan_threads',
                    'severity': 'high',
                    'summary': '从前端点了“扫描线程”，但没有在电脑线程预览里出现任何线程。',
                    'detail': scan_state,
                })

            shot = output_dir / f'ui-frontdoor-08-owner-create-npc-{stamp}.png'
            npc_state = create_npc_via_ui(
                owner_flow,
                WEB_BASE,
                project_id=project_id,
                npc_name='UI 验证 NPC',
                responsibility='负责验证前端用户流是否能把项目推进下去。',
                shot=shot,
            )
            report['steps']['owner_create_npc'] = npc_state
            report['screenshots']['owner_create_npc'] = str(shot)

            shot = output_dir / f'ui-frontdoor-09-owner-invite-collaborator-{stamp}.png'
            invite_via_ui(
                owner_flow,
                WEB_BASE,
                project_id=project_id,
                invitee_email=collaborator_email,
                note='请加入这个项目，验证第二位协作者能否从前端接入自己的电脑。',
                shot=shot,
            )
            report['steps']['invite_collaborator'] = {
                'invitee_email': collaborator_email,
                'project_id': project_id,
            }
            report['screenshots']['invite_collaborator'] = str(shot)

        member_profile = dual_helper.new_browser_profile(runtime_dir, 'member')
        with BrowserRuntime(find_free_port(), member_profile, VIEWPORT_WIDTH, VIEWPORT_HEIGHT) as member_flow:
            shot = output_dir / f'ui-frontdoor-10-member-signup-{stamp}.png'
            register_via_ui(member_flow, WEB_BASE, email=collaborator_email, password=collaborator_password, name=collaborator_name, shot=shot)
            report['screenshots']['member_signup'] = str(shot)

            before_accept = verify_projects_plaza(member_flow, WEB_BASE, project_name=project_name, expected_present=False)
            report['steps']['member_projects_before_accept'] = before_accept

            shot = output_dir / f'ui-frontdoor-11-member-accept-invite-{stamp}.png'
            accept_invite_via_ui(member_flow, WEB_BASE, project_name=project_name, shot=shot)
            report['screenshots']['member_accept_invite'] = str(shot)

            after_accept = verify_projects_plaza(member_flow, WEB_BASE, project_name=project_name, expected_present=True)
            report['steps']['member_projects_after_accept'] = after_accept

            shot = output_dir / f'ui-frontdoor-12-member-project-map-{stamp}.png'
            member_map_state = open_project_map(member_flow, project_id=project_id, shot=shot)
            report['steps']['member_project_map'] = member_map_state
            report['screenshots']['member_project_map'] = str(shot)

            shot = output_dir / f'ui-frontdoor-13-member-computer-create-{stamp}.png'
            member_computer_state = create_computer_via_ui(
                member_flow,
                WEB_BASE,
                project_id=project_id,
                computer_id=second_computer_id,
                label='Member Validation PC',
                workspace_root=str(second_workspace),
                git_root=str(second_workspace),
                shot=shot,
            )
            report['steps']['member_computer_create'] = member_computer_state
            report['screenshots']['member_computer_create'] = str(shot)

            shot = output_dir / f'ui-frontdoor-14-member-pairing-token-{stamp}.png'
            member_pairing_state = generate_pairing_token_via_ui_pure(member_flow, project_id=project_id, computer_id=second_computer_id, shot=shot)
            report['steps']['member_pairing_token'] = member_pairing_state
            report['screenshots']['member_pairing_token'] = str(shot)
            report['steps']['member_runner_onboarding'] = onboard_runner_via_user_scripts(
                server=API_BASE,
                pairing_token=str(member_pairing_state.get('pairingToken') or ''),
                computer_node_id=second_computer_id,
                project_id=project_id,
                runner_id=member_runner_id,
                runner_name='Member Validation Runner',
                thread_id=member_thread_id,
                thread_name='Member Codex Mainline',
                cwd=str(second_workspace),
            )

            shot_before = output_dir / f'ui-frontdoor-15-member-scan-before-{stamp}.png'
            shot_after = output_dir / f'ui-frontdoor-16-member-scan-after-{stamp}.png'
            member_scan_state = attempt_thread_scan_via_ui(
                member_flow,
                project_id=project_id,
                computer_id=second_computer_id,
                shot_before=shot_before,
                shot_after=shot_after,
            )
            report['steps']['member_scan_threads'] = member_scan_state
            report['screenshots']['member_scan_before'] = str(shot_before)
            report['screenshots']['member_scan_after'] = str(shot_after)
            if not member_scan_state.get('scan_surfaced_threads'):
                report['issues'].append({
                    'step': 'member_scan_threads',
                    'severity': 'high',
                    'summary': '第二位协作者也能点到“扫描线程”，但电脑线程预览里依然没有任何线程出现。',
                    'detail': member_scan_state,
                })

        report_path = output_dir / f'ui-frontdoor-onboarding-report-{stamp}.json'
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'report_path': str(report_path), 'issues': len(report['issues']), 'project_id': project_id}, ensure_ascii=False))
        return 0
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
