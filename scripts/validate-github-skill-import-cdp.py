from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)


TEST_GITHUB_URL = "https://github.com/msitarzewski/agency-agents/blob/main/design/design-ui-designer.md"
TEST_REPO = "msitarzewski/agency-agents"
TEST_PATH = "design/design-ui-designer.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate free GitHub Skill import through the real Skill warehouse UI.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="78151f5f-f08c-4e83-b0fc-9be89263ecb3")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--github-url", default=TEST_GITHUB_URL)
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=2048)
    parser.add_argument("--viewport-height", type=int, default=1152)
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
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {body[:1200]}") from exc


def api_login(api_base: str, email: str, password: str) -> tuple[str, dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/auth/session",
        method="POST",
        payload={"email": email, "password": password},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get("access_token"):
        raise RuntimeError("API login response did not include access_token")
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    return str(data["access_token"]), user


def read_project(api_base: str, project_id: str, token: str) -> dict[str, object]:
    payload = request_json(f"{api_base.rstrip('/')}/api/projects/{project_id}", token=token)
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict) and isinstance(data.get("project"), dict):
        return data["project"]  # type: ignore[return-value]
    if isinstance(data, dict):
        return data
    raise RuntimeError(f"Project response did not include a project object: {payload}")


def collaboration_config(project: dict[str, object]) -> dict[str, object]:
    value = project.get("collaboration_config")
    return dict(value) if isinstance(value, dict) else {}


def skill_ids(config: dict[str, object]) -> set[str]:
    items = config.get("skill_library")
    if not isinstance(items, list):
        return set()
    return {str(item.get("id", "")).lower() for item in items if isinstance(item, dict) and item.get("id")}


def find_imported_github_skill(project: dict[str, object]) -> dict[str, object]:
    config = collaboration_config(project)
    items = config.get("skill_library")
    if not isinstance(items, list):
        return {}
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        if item.get("source") == "github" and metadata.get("external_repo") == TEST_REPO and metadata.get("external_path") == TEST_PATH:
            return item
    return {}


def remove_skill_from_project(api_base: str, project_id: str, token: str, skill_id: str) -> None:
    project = read_project(api_base, project_id, token)
    config = collaboration_config(project)
    items = config.get("skill_library")
    if not isinstance(items, list):
        return
    config["skill_library"] = [
        item
        for item in items
        if not (isinstance(item, dict) and str(item.get("id", "")).lower() == skill_id.lower())
    ]
    request_json(
        f"{api_base.rstrip('/')}/api/projects/{project_id}",
        method="PATCH",
        payload={"collaboration_config": config},
        token=token,
    )


def cdp_eval(cdp: object, expression: str) -> object:
    result = cdp.send(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
            "userGesture": True,
        },
    )
    if "exceptionDetails" in result:
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1600])
    value = result.get("result", {})
    return value.get("value") if isinstance(value, dict) else None


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 60, interval_seconds: float = 0.3) -> object:
    deadline = time.time() + timeout_seconds
    last: object = None
    while time.time() < deadline:
        try:
            value = cdp_eval(cdp, expression)
            if value:
                return value
            last = value
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(interval_seconds)
    raise RuntimeError(f"Timed out waiting for expression: {expression[:240]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            break
        except TimeoutError as exc:
            last_error = exc
            time.sleep(1.2 + attempt)
    else:
        raise RuntimeError(f"CDP screenshot timed out after retries: {last_error}") from last_error
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def set_input_value(cdp: object, selector: str, value: str) -> None:
    updated = cdp_eval(
        cdp,
        f"""
        (() => {{
          const input = document.querySelector({json.dumps(selector)});
          if (!input) return false;
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
          input.focus();
          if (setter) setter.call(input, {json.dumps(value)});
          else input.value = {json.dumps(value)};
          input.dispatchEvent(new Event('input', {{ bubbles: true }}));
          input.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return true;
        }})()
        """,
    )
    if not updated:
        raise RuntimeError(f"Could not set input {selector}")


def click_selector(cdp: object, selector: str) -> None:
    clicked = cdp_eval(
        cdp,
        f"""
        (() => {{
          const node = document.querySelector({json.dumps(selector)});
          if (!node || node.disabled) return false;
          node.scrollIntoView({{ block: 'center', inline: 'center' }});
          node.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not click selector {selector!r}")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    skills_url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=skills"
    screenshots: list[str] = []
    imported_skill_id = ""
    should_cleanup_import = False

    token, user = api_login(args.api_base, args.login_email, args.login_password)
    before_project = read_project(args.api_base, args.project_id, token)
    before_ids = skill_ids(collaboration_config(before_project))

    cookie_domain = urlparse(args.web_base).hostname or "127.0.0.1"
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-edge-github-skill-"))
    edge_process = None
    cdp = None
    try:
        edge_process = subprocess.Popen(
            [
                str(cdp_helpers.find_edge()),
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
        targets = cdp_helpers.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        if not isinstance(targets, list) or not targets:
            cdp_helpers.request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
            targets = cdp_helpers.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page"), None)
        if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
            raise RuntimeError("No CDP page target available")

        cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.sock.settimeout(90)
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.viewport_width,
                "height": args.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        cdp.send("Page.navigate", {"url": f"{args.web_base.rstrip('/')}/login"})
        wait_for(cdp, "document.readyState === 'complete' && !!document.body")
        for cookie in (
            {"name": "farm_access_token", "value": token},
            {"name": "farm_user", "value": json.dumps(user, ensure_ascii=True)},
        ):
            cdp.send(
                "Network.setCookie",
                {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": cookie_domain,
                    "path": "/",
                    "httpOnly": False,
                    "secure": False,
                },
            )

        cdp.send("Page.navigate", {"url": skills_url})
        wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('[data-skill-open-github-import]')")
        shot = output_dir / f"github-skill-import-01-skill-warehouse-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_selector(cdp, "[data-skill-open-github-import]")
        wait_for(cdp, "!!document.querySelector('[data-skill-github-import-drawer=\"1\"]')")
        set_input_value(cdp, "input[name='github_url']", args.github_url)
        set_input_value(cdp, "input[name='category']", "design")
        set_input_value(cdp, "input[name='recommended_for']", "github, ui, design, npc")
        shot = output_dir / f"github-skill-import-02-drawer-filled-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_selector(cdp, "[data-skill-import-github-submit]")
        wait_for(
            cdp,
            """
            (() => {
              const params = new URL(window.location.href).searchParams;
              return (params.get('team_notice') || '').includes('GitHub') ||
                (params.get('team_error') || '').length > 0;
            })()
            """,
            timeout_seconds=90,
        )
        error = cdp_eval(cdp, "new URL(window.location.href).searchParams.get('team_error') || ''")
        if error:
            raise RuntimeError(f"GitHub import returned UI error: {error}")

        after_project = read_project(args.api_base, args.project_id, token)
        imported_skill = find_imported_github_skill(after_project)
        imported_skill_id = str(imported_skill.get("id") or "")
        if not imported_skill_id:
            raise RuntimeError("GitHub import completed but the imported skill was not found in project skill_library")
        should_cleanup_import = imported_skill_id.lower() not in before_ids

        detail_url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=skills&drawer=skill-detail&drawer_id={imported_skill_id}"
        cdp.send("Page.navigate", {"url": detail_url})
        wait_for(cdp, f"document.readyState === 'complete' && !!document.querySelector('[data-skill-detail-drawer={json.dumps(imported_skill_id)}]')")
        detail_state = cdp_eval(
            cdp,
            f"""
            (() => {{
              const bodyText = document.body ? document.body.innerText : '';
              return {{
                hasGithubSource: bodyText.includes('GitHub'),
                hasSourcePath: bodyText.includes({json.dumps(TEST_PATH)}),
                hasImportedNote: bodyText.includes('从 GitHub 导入'),
              }};
            }})()
            """,
        )
        if not isinstance(detail_state, dict) or not detail_state.get("hasGithubSource") or not detail_state.get("hasSourcePath"):
            raise RuntimeError(f"Imported GitHub skill detail did not expose source metadata: {detail_state}")
        shot = output_dir / f"github-skill-import-03-detail-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        report = {
            "validated_at": datetime.now().astimezone().isoformat(),
            "project_id": args.project_id,
            "github_url": args.github_url,
            "imported_skill_id": imported_skill_id,
            "cleanup_required": should_cleanup_import,
            "detail_state": detail_state,
            "screenshots": screenshots,
        }
        report_path = output_dir / f"github-skill-import-validation-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        if should_cleanup_import and imported_skill_id:
            remove_skill_from_project(args.api_base, args.project_id, token, imported_skill_id)
        if cdp is not None:
            cdp.close()
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
