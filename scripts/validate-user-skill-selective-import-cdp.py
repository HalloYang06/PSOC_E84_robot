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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate selective Agency Agents import through the real Skill manager UI.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=2048)
    parser.add_argument("--viewport-height", type=int, default=1152)
    return parser.parse_args()


def request_json(url: str, *, method: str = "GET", payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
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
    return str(data["access_token"]), data.get("user") if isinstance(data.get("user"), dict) else {}


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


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 40, interval_seconds: float = 0.25) -> object:
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
    raise RuntimeError(f"Timed out waiting for expression: {expression[:220]} last={last}")


def wait_for_panel_idle(cdp: object, *, timeout_seconds: float = 60) -> None:
    wait_for(
        cdp,
        """
        (() => {
          const panel = document.querySelector('#project-main-panel');
          if (!panel) return false;
          const busy = panel.getAttribute('data-busy');
          const overlay = panel.querySelector('[role="status"]');
          return busy !== 'true' && !overlay;
        })()
        """,
        timeout_seconds=timeout_seconds,
    )


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def click_selector(cdp: object, selector: str) -> None:
    clicked = cdp_eval(
        cdp,
        f"""
        (() => {{
          const node = document.querySelector({json.dumps(selector)});
          if (!node) return false;
          node.scrollIntoView({{ block: 'center', inline: 'center' }});
          node.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not click selector {selector!r}")


def set_search_value(cdp: object, selector: str, value: str) -> None:
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
        raise RuntimeError(f"Could not set search value for {selector}")


def read_import_state(cdp: object) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        """
        (() => {
          const drawer = document.querySelector('[data-skill-import-drawer="1"]');
          const selectedCount = Number(document.querySelector('[data-skill-import-selected-count]')?.getAttribute('data-skill-import-selected-count') || '0');
          const visibleCount = Number(document.querySelector('[data-skill-import-visible-count]')?.getAttribute('data-skill-import-visible-count') || '0');
          const recommendedOnly = !!document.querySelector('[data-skill-import-recommended-view="curated"]')?.className.includes('Active');
          const options = Array.from(document.querySelectorAll('[data-skill-import-option]')).map((node) => ({
            id: node.getAttribute('data-skill-import-option') || '',
            text: (node.textContent || '').trim(),
          }));
          const notice = new URL(window.location.href).searchParams.get('team_notice') || '';
          const error = new URL(window.location.href).searchParams.get('team_error') || '';
          return {
            drawerVisible: !!drawer,
            selectedCount,
            visibleCount,
            recommendedOnly,
            optionCount: options.length,
            optionTexts: options.slice(0, 8),
            notice,
            error,
          };
        })()
        """,
    )
    return state if isinstance(state, dict) else {}


def main() -> int:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    login_url = f"{args.web_base.rstrip('/')}/login"
    skills_url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=skills"
    report_path = output_dir / f"skill-selective-import-validation-report-{stamp}.json"
    screenshots: list[str] = []

    token, user = api_login(args.api_base, args.login_email, args.login_password)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-edge-python-cdp-"))
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
        cdp.sock.settimeout(60)
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

        cdp.send("Page.navigate", {"url": login_url})
        wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('form')")
        shot = output_dir / f"skill-selective-import-01-login-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        cdp.send(
            "Network.setCookie",
            {
                "name": "farm_access_token",
                "value": token,
                "domain": "127.0.0.1",
                "path": "/",
                "httpOnly": False,
                "secure": False,
            },
        )
        cdp.send(
            "Network.setCookie",
            {
                "name": "farm_user",
                "value": json.dumps(user, ensure_ascii=True),
                "domain": "127.0.0.1",
                "path": "/",
                "httpOnly": False,
                "secure": False,
            },
        )

        cdp.send("Page.navigate", {"url": skills_url})
        wait_for(
            cdp,
            "document.readyState === 'complete' && !!document.querySelector('[data-skill-open-import-drawer=\"1\"]')",
            timeout_seconds=60,
        )
        wait_for_panel_idle(cdp, timeout_seconds=60)
        shot = output_dir / f"skill-selective-import-02-skills-before-open-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_selector(cdp, '[data-skill-open-import-drawer="1"]')
        wait_for(
            cdp,
            "!!document.querySelector('[data-skill-import-drawer=\"1\"]')",
            timeout_seconds=30,
        )
        wait_for_panel_idle(cdp, timeout_seconds=30)
        shot = output_dir / f"skill-selective-import-03-drawer-open-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_selector(cdp, '[data-skill-import-recommended-view="curated"]')
        wait_for(
            cdp,
            """
            (() => {
              const visibleCount = document.querySelector('[data-skill-import-visible-count]')?.getAttribute('data-skill-import-visible-count') || '';
              return visibleCount === '16';
            })()
            """,
            timeout_seconds=30,
        )
        shot = output_dir / f"skill-selective-import-04-curated-view-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_selector(cdp, '[data-skill-import-bundle="frontend-starter"]')
        wait_for(
            cdp,
            """
            (() => {
              const count = document.querySelector('[data-skill-import-selected-count]')?.getAttribute('data-skill-import-selected-count') || '';
              return count === '4';
            })()
            """,
            timeout_seconds=30,
        )
        after_select_state = read_import_state(cdp)
        const_text = " ".join(str(item.get("text") if isinstance(item, dict) else item) for item in after_select_state.get("optionTexts") or [])
        if "frontend developer" not in const_text.lower():
            raise RuntimeError(f"Frontend starter pack did not keep frontend developer visible: {after_select_state}")
        shot = output_dir / f"skill-selective-import-05-after-bundle-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_selector(cdp, '[data-skill-import-selected-submit="1"]')
        wait_for(
            cdp,
            f"""
            (() => {{
              const notice = new URL(window.location.href).searchParams.get('team_notice') || '';
              return notice.includes({json.dumps("选中 4 条")});
            }})()
            """,
            timeout_seconds=45,
        )
        wait_for_panel_idle(cdp, timeout_seconds=45)
        after_submit_state = read_import_state(cdp)
        if "选中 4 条" not in str(after_submit_state.get("notice") or ""):
            raise RuntimeError(f"Selective import notice did not mention selected count: {after_submit_state}")
        shot = output_dir / f"skill-selective-import-06-after-submit-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        report = {
            "validated_at": datetime.now().astimezone().isoformat(),
            "project_id": args.project_id,
            "skills_url": skills_url,
            "after_select_state": after_select_state,
            "after_submit_state": after_submit_state,
            "screenshots": screenshots,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        if cdp is not None:
            cdp.close()
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=5)
            except Exception:  # noqa: BLE001
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
