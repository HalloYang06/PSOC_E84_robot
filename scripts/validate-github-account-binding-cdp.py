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


TEST_GITHUB_URL = "https://github.com/openai/openai-agents-python.git"
TEST_ACCOUNT = "codex-github-verify"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate project GitHub account binding through the real Git panel UI.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="78151f5f-f08c-4e83-b0fc-9be89263ecb3")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
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


def restore_project(api_base: str, project_id: str, token: str, project: dict[str, object]) -> None:
    request_json(
        f"{api_base.rstrip('/')}/api/projects/{project_id}",
        method="PATCH",
        payload={
            "github_url": project.get("github_url"),
            "local_git_url": project.get("local_git_url"),
            "default_branch": project.get("default_branch") or project.get("defaultBranch") or "main",
            "develop_branch": project.get("develop_branch") or project.get("developBranch") or "develop",
            "collaboration_config": collaboration_config(project),
        },
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


def set_field_value(cdp: object, selector: str, value: str) -> None:
    updated = cdp_eval(
        cdp,
        f"""
        (() => {{
          const field = document.querySelector({json.dumps(selector)});
          if (!field) return false;
          const proto = field instanceof HTMLTextAreaElement
            ? window.HTMLTextAreaElement.prototype
            : field instanceof HTMLSelectElement
              ? window.HTMLSelectElement.prototype
              : window.HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
          field.focus();
          if (setter) setter.call(field, {json.dumps(value)});
          else field.value = {json.dumps(value)};
          field.dispatchEvent(new Event('input', {{ bubbles: true }}));
          field.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return true;
        }})()
        """,
    )
    if not updated:
        raise RuntimeError(f"Could not set field {selector}")


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


def wait_for_notice(cdp: object, expected: str) -> None:
    wait_for(
        cdp,
        f"""
        (() => {{
          const params = new URL(window.location.href).searchParams;
          const error = params.get('team_error') || '';
          if (error) return `ERROR: ${{error}}`;
          return (params.get('team_notice') || '').includes({json.dumps(expected)});
        }})()
        """,
        timeout_seconds=90,
    )
    error = cdp_eval(cdp, "new URL(window.location.href).searchParams.get('team_error') || ''")
    if error:
        raise RuntimeError(f"UI returned error: {error}")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    git_url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=git"
    screenshots: list[str] = []

    token, user = api_login(args.api_base, args.login_email, args.login_password)
    original_project = read_project(args.api_base, args.project_id, token)

    cookie_domain = urlparse(args.web_base).hostname or "127.0.0.1"
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-edge-github-account-"))
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

        cdp.send("Page.navigate", {"url": git_url})
        wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('[data-github-account-binding-card=\"1\"]')")
        shot = output_dir / f"github-account-binding-01-git-panel-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        set_field_value(cdp, "input[data-github-repository-url='1']", TEST_GITHUB_URL)
        set_field_value(cdp, "input[name='default_branch']", "main")
        set_field_value(cdp, "input[name='develop_branch']", "develop")
        click_selector(cdp, "[data-github-repository-bind-submit='1']")
        wait_for_notice(cdp, "Git 配置")

        wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('[data-github-account-login=\"1\"]')")
        set_field_value(cdp, "input[data-github-account-login='1']", TEST_ACCOUNT)
        set_field_value(cdp, "select[name='account_type']", "bot")
        set_field_value(cdp, "input[name='profile_url']", f"https://github.com/{TEST_ACCOUNT}")
        set_field_value(cdp, "select[name='credential_source']", "runner_env")
        set_field_value(cdp, "input[data-github-credential-ref='1']", "GITHUB_TOKEN_TEST_ONLY")
        set_field_value(cdp, "select[name='default_clone_protocol']", "https")
        set_field_value(cdp, "input[name='permission_scopes']", "repo, workflow")
        set_field_value(cdp, "textarea[name='notes']", "UI validation only: token is not stored in project config.")
        click_selector(cdp, "[data-github-account-bind-submit='1']")
        wait_for_notice(cdp, "GitHub 账号已绑定")

        after_project = read_project(args.api_base, args.project_id, token)
        after_config = collaboration_config(after_project)
        binding = after_config.get("github_account_binding")
        if not isinstance(binding, dict):
            raise RuntimeError("Project collaboration_config did not include github_account_binding after UI submit")
        if binding.get("account_login") != TEST_ACCOUNT:
            raise RuntimeError(f"Unexpected account_login after submit: {binding}")
        if binding.get("secret_storage") != "not_stored_in_project_config":
            raise RuntimeError(f"Secret storage marker missing from binding: {binding}")
        forbidden_keys = {"token", "access_token", "secret", "password", "private_key"}
        if forbidden_keys.intersection({str(key).lower() for key in binding.keys()}):
            raise RuntimeError(f"Binding appears to contain raw secret fields: {binding}")

        wait_for(cdp, "document.readyState === 'complete' && document.body.innerText.includes('codex-github-verify')")
        shot = output_dir / f"github-account-binding-02-bound-state-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        report = {
            "validated_at": datetime.now().astimezone().isoformat(),
            "project_id": args.project_id,
            "repository_url": TEST_GITHUB_URL,
            "account_login": TEST_ACCOUNT,
            "secret_storage": binding.get("secret_storage"),
            "screenshots": screenshots,
        }
        report_path = output_dir / f"github-account-binding-validation-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        restore_project(args.api_base, args.project_id, token, original_project)
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
