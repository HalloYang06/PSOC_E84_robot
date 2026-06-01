from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CDP_HELPER_PATH = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"

spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helper: {CDP_HELPER_PATH}")
cdp_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helper)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate account/project isolation through the real browser.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--owner-email", default="lead@example.com")
    parser.add_argument("--owner-password", default="password")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--output-dir", default=str(Path("D:/ai合作产品/artifacts")))
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=1100)
    return parser.parse_args()


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    token: str | None = None,
) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {body[:1200]}") from exc


def api_session(api_base: str, email: str, password: str) -> tuple[str, dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/auth/session",
        method="POST",
        payload={"email": email, "password": password},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get("access_token"):
        raise RuntimeError(f"Session response did not include access_token for {email}")
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    return str(data["access_token"]), user


def api_register(api_base: str, email: str, name: str, password: str) -> dict[str, object]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/auth/register",
        method="POST",
        payload={
            "email": email,
            "name": name,
            "password": password,
            "global_role": "member",
        },
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError(f"Register response did not include user payload for {email}")
    return data


def get_project(api_base: str, project_id: str, token: str) -> dict[str, object]:
    payload = request_json(f"{api_base.rstrip('/')}/api/projects/{project_id}", token=token)
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, dict):
        raise RuntimeError(f"Project payload missing for {project_id}")
    return data


def get_workspace(api_base: str, token: str) -> dict[str, object]:
    payload = request_json(f"{api_base.rstrip('/')}/api/auth/workspace", token=token)
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, dict):
        raise RuntimeError("Workspace payload missing")
    return data


def cleanup_temp_user(email: str) -> None:
    api_root = REPO_ROOT / "apps" / "api"
    original_cwd = Path.cwd()
    os.chdir(api_root)
    try:
        sys.path.insert(0, str(api_root))
        from sqlalchemy import delete, select

        from app.db.models.invitation import Invitation
        from app.db.models.project_invite import ProjectInvite
        from app.db.models.project_member import ProjectMember
        from app.db.models.user import User
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                return
            db.execute(delete(ProjectMember).where(ProjectMember.user_id == user.id))
            db.execute(
                delete(ProjectInvite).where(
                    (ProjectInvite.invited_by_user_id == user.id) | (ProjectInvite.accepted_by_user_id == user.id)
                )
            )
            db.execute(
                delete(Invitation).where(
                    (Invitation.email == email)
                    | (Invitation.invited_by_user_id == user.id)
                    | (Invitation.accepted_by_user_id == user.id)
                )
            )
            db.delete(user)
            db.commit()
    finally:
        os.chdir(original_cwd)


def js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class BrowserFlow:
    def __init__(self, cdp):
        self.cdp = cdp

    def eval(self, expression: str):
        result = self.cdp.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if "exceptionDetails" in result:
            raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1600])
        return result.get("result", {}).get("value")

    def text(self) -> str:
        value = self.eval("document.body ? document.body.innerText : ''")
        return str(value or "")

    def url(self) -> str:
        value = self.eval("location.href")
        return str(value or "")

    def navigate(self, url: str):
        self.cdp.send("Page.navigate", {"url": url})
        time.sleep(1.0)

    def fill(self, selector: str, value: str):
        ok = self.eval(
            f"""
            (() => {{
              const field = document.querySelector({js_string(selector)});
              if (!field) return false;
              field.focus();
              field.value = {js_string(value)};
              field.dispatchEvent(new Event('input', {{ bubbles: true }}));
              field.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return true;
            }})()
            """
        )
        if not ok:
            raise RuntimeError(f"Could not fill selector {selector!r}")

    def click_text(self, text: str, selector: str = "button,a", timeout: float = 10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            clicked = self.eval(
                f"""
                (() => {{
                  const wanted = {js_string(text)};
                  const items = Array.from(document.querySelectorAll({js_string(selector)}));
                  const el = items.find((item) => (item.innerText || item.textContent || '').includes(wanted));
                  if (!el) return false;
                  el.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
                  el.click();
                  return true;
                }})()
                """
            )
            if clicked:
                time.sleep(1.2)
                return
            time.sleep(0.25)
        raise RuntimeError(f"Could not click text {text!r}")

    def wait_for(self, expression: str, timeout: float = 20):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = self.eval(expression)
            if last:
                return last
            time.sleep(0.25)
        raise RuntimeError(f"Timed out waiting for expression: {expression[:220]} last={last!r}")

    def screenshot(self, output: Path):
        output.parent.mkdir(parents=True, exist_ok=True)
        shot = self.cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
        data = str(shot.get("data") or "")
        if not data:
            raise RuntimeError("CDP returned an empty screenshot")
        output.write_bytes(base64.b64decode(data))


def run_browser_session(
    *,
    web_base: str,
    login_email: str,
    login_password: str,
    token: str = "",
    user_json: str = "",
    viewport_width: int,
    viewport_height: int,
    work,
):
    port = cdp_helper.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-account-isolation-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    try:
        edge_process = subprocess.Popen(
            [
                str(cdp_helper.find_edge()),
                "--headless=new",
                "--disable-gpu",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        if not isinstance(targets, list) or not targets:
            cdp_helper.request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
            targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page"), None)
        if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
            raise RuntimeError("No CDP page target available")

        cdp = cdp_helper.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": viewport_width,
                "height": viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        flow = BrowserFlow(cdp)
        origin = f"{urlparse(web_base).scheme}://{urlparse(web_base).netloc}"
        if token:
            cdp.send(
                "Network.setCookie",
                {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
            )
            if user_json:
                cdp.send(
                    "Network.setCookie",
                    {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
                )
            flow.navigate(f"{web_base.rstrip('/')}/projects")
        else:
            flow.navigate(f"{web_base.rstrip('/')}/login")
            flow.wait_for("document.readyState === 'complete' && !!document.querySelector('form')", timeout=20)
            flow.fill('input[name="email"], input[type="email"]', login_email)
            flow.fill('input[name="password"], input[type="password"]', login_password)
            flow.click_text("进入项目空间", "button")
        flow.wait_for("location.pathname === '/projects' && !!document.querySelector('main')", timeout=30)
        return work(flow)
    finally:
        if cdp is not None:
            try:
                cdp.close()
            except Exception:
                pass
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=5)
            except Exception:
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    owner_token, owner_user = api_session(args.api_base, args.owner_email, args.owner_password)
    workspace = get_workspace(args.api_base, owner_token)
    workspace_projects = workspace.get("projects") if isinstance(workspace.get("projects"), list) else []
    resolved_project_id = args.project_id
    requested_project_access = True
    try:
        project = get_project(args.api_base, resolved_project_id, owner_token)
    except Exception:
        requested_project_access = False
        first_project = workspace_projects[0] if workspace_projects else None
        if not isinstance(first_project, dict):
            raise RuntimeError(f"{args.owner_email} has no accessible project to validate isolation against")
        resolved_project_id = str(first_project.get("project_id") or first_project.get("id") or "").strip()
        if not resolved_project_id:
            raise RuntimeError(f"Could not resolve a fallback project id from workspace: {first_project}")
        project = get_project(args.api_base, resolved_project_id, owner_token)
    project_name = str(project.get("name") or resolved_project_id)

    outsider_email = f"account-isolation-{stamp.lower()}@example.com"
    outsider_name = f"Account Isolation {stamp[-6:]}"
    outsider_password = "password"
    cleanup_temp_user(outsider_email)
    api_register(args.api_base, outsider_email, outsider_name, outsider_password)
    outsider_token, outsider_user = api_session(args.api_base, outsider_email, outsider_password)

    screenshots: list[str] = []
    report: dict[str, object] = {
        "timestamp": stamp,
        "owner_email": args.owner_email,
        "outsider_email": outsider_email,
        "requested_project_id": args.project_id,
        "project_id": resolved_project_id,
        "project_name": project_name,
        "requested_project_access": requested_project_access,
        "owner_user": owner_user,
    }

    try:
        owner_shot = output_dir / f"account-isolation-01-owner-projects-{stamp}.png"

        def owner_work(flow: BrowserFlow):
            state = flow.eval(
                f"""
                (() => {{
                  const text = document.body ? document.body.innerText : '';
                  const hrefs = Array.from(document.querySelectorAll('a')).map((item) => item.getAttribute('href') || '');
                  return {{
                    url: location.href,
                    hasProjectName: text.includes({js_string(project_name)}),
                    hasProjectLink: hrefs.some((href) => href.includes({js_string(resolved_project_id)})),
                    projectLinkCount: hrefs.filter((href) => href.includes({js_string(resolved_project_id)})).length,
                  }};
                }})()
                """
            )
            flow.screenshot(owner_shot)
            return state

        owner_state = run_browser_session(
            web_base=args.web_base,
            login_email=args.owner_email,
            login_password=args.owner_password,
            token=owner_token,
            user_json=json.dumps(owner_user, ensure_ascii=True),
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
            work=owner_work,
        )
        screenshots.append(str(owner_shot))
        if not isinstance(owner_state, dict) or not owner_state.get("hasProjectLink"):
            raise RuntimeError(f"Owner projects page did not expose the expected project link: {owner_state}")

        outsider_projects_shot = output_dir / f"account-isolation-02-outsider-projects-{stamp}.png"
        outsider_forbidden_shot = output_dir / f"account-isolation-03-outsider-foreign-project-redirect-{stamp}.png"
        outsider_robotics_shot = output_dir / f"account-isolation-04-outsider-robotics-{stamp}.png"
        outsider_rehab_shot = output_dir / f"account-isolation-05-outsider-rehab-arm-{stamp}.png"

        def outsider_work(flow: BrowserFlow):
            projects_state = flow.eval(
                f"""
                (() => {{
                  const text = document.body ? document.body.innerText : '';
                  const hrefs = Array.from(document.querySelectorAll('a')).map((item) => item.getAttribute('href') || '');
                  return {{
                    url: location.href,
                    projectCountText: text,
                    hasForeignProjectName: text.includes({js_string(project_name)}),
                    hasForeignProjectLink: hrefs.some((href) => href.includes({js_string(resolved_project_id)})),
                  }};
                }})()
                """
            )
            flow.screenshot(outsider_projects_shot)

            flow.navigate(f"{args.web_base.rstrip('/')}/projects/{resolved_project_id}")
            time.sleep(2.0)
            forbidden_state = flow.eval(
                f"""
                (() => {{
                  const text = document.body ? document.body.innerText : '';
                  return {{
                    url: location.href,
                    bodyText: text,
                    hasErrorBanner: text.includes('当前账号没有这个项目的访问权限'),
                    hasNoPermissionText: text.includes('项目不存在或无权限'),
                    returnedToProjects: location.pathname === '/projects',
                    hasForeignProjectName: text.includes({js_string(project_name)}),
                  }};
                }})()
                """
            )
            flow.screenshot(outsider_forbidden_shot)

            device_states = {}
            for slug, shot in [("robotics", outsider_robotics_shot), ("rehab-arm-control", outsider_rehab_shot)]:
                flow.navigate(f"{args.web_base.rstrip('/')}/projects/{resolved_project_id}/{slug}")
                time.sleep(2.0)
                device_states[slug] = flow.eval(
                    f"""
                    (() => {{
                      const text = document.body ? document.body.innerText : '';
                      return {{
                        url: location.href,
                        hasErrorBanner: text.includes('当前账号没有这个项目的访问权限'),
                        hasNoPermissionText: text.includes('项目不存在或无权限'),
                        returnedToProjects: location.pathname === '/projects',
                        hasForeignProjectName: text.includes({js_string(project_name)}),
                        exposesDeviceWorkbench: text.includes('设备数据工作台') || text.includes('专项总控') || text.includes('只读总览'),
                      }};
                    }})()
                    """
                )
                flow.screenshot(shot)
            return {"projects_state": projects_state, "forbidden_state": forbidden_state, "device_states": device_states}

        outsider_state = run_browser_session(
            web_base=args.web_base,
            login_email=outsider_email,
            login_password=outsider_password,
            token=outsider_token,
            user_json=json.dumps(outsider_user, ensure_ascii=True),
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
            work=outsider_work,
        )
        screenshots.extend([str(outsider_projects_shot), str(outsider_forbidden_shot), str(outsider_robotics_shot), str(outsider_rehab_shot)])

        if not isinstance(outsider_state, dict):
            raise RuntimeError(f"Outsider browser state missing: {outsider_state!r}")
        projects_state = outsider_state.get("projects_state")
        forbidden_state = outsider_state.get("forbidden_state")
        if not isinstance(projects_state, dict) or projects_state.get("hasForeignProjectName") or projects_state.get("hasForeignProjectLink"):
            raise RuntimeError(f"Outsider /projects still exposed the foreign project: {projects_state}")
        forbidden_ok = isinstance(forbidden_state, dict) and (
            forbidden_state.get("hasErrorBanner")
            or forbidden_state.get("hasNoPermissionText")
            or forbidden_state.get("returnedToProjects")
        )
        if not forbidden_ok or forbidden_state.get("hasForeignProjectName"):
            raise RuntimeError(f"Outsider direct-open did not redirect cleanly: {forbidden_state}")
        device_states = outsider_state.get("device_states")
        if not isinstance(device_states, dict):
            raise RuntimeError(f"Outsider device workbench isolation state missing: {outsider_state}")
        for slug, state in device_states.items():
            if (
                not isinstance(state, dict)
                or not (state.get("hasErrorBanner") or state.get("hasNoPermissionText") or state.get("returnedToProjects"))
                or state.get("hasForeignProjectName")
                or state.get("exposesDeviceWorkbench")
            ):
                raise RuntimeError(f"Outsider direct-open exposed {slug}: {state}")

        report["owner_state"] = owner_state
        report["outsider_state"] = outsider_state
        report["screenshots"] = screenshots
        report_path = output_dir / f"account-project-isolation-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(str(report_path))
        return 0
    finally:
        cleanup_temp_user(outsider_email)


if __name__ == "__main__":
    raise SystemExit(main())
