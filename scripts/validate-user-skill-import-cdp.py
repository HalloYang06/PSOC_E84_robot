from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import shutil
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
    parser = argparse.ArgumentParser(description="Validate Agency Agents full skill import through the real Skill manager UI.")
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
          const overlayText = overlay?.textContent || '';
          return busy !== 'true' &&
            !overlay &&
            !overlayText.includes('正在处理') &&
            !overlayText.includes('正在提交到平台');
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


def submit_form(cdp: object, selector: str) -> None:
    submitted = cdp_eval(
        cdp,
        f"""
        (() => {{
          const button = document.querySelector({json.dumps(selector)});
          if (!button) return false;
          button.click();
          return true;
        }})()
        """,
    )
    if not submitted:
        raise RuntimeError(f"Could not click submit control {selector!r}")


def set_search_query(cdp: object, value: str) -> None:
    updated = cdp_eval(
        cdp,
        f"""
        (() => {{
          const input = Array.from(document.querySelectorAll('input')).find((node) =>
            (node.getAttribute('placeholder') || '').includes('搜索 Skill')
          );
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
        raise RuntimeError("Could not update skill search input")


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


def click_button_by_text(cdp: object, label: str) -> None:
    clicked = cdp_eval(
        cdp,
        f"""
        (() => {{
          const button = Array.from(document.querySelectorAll('button')).find((node) =>
            (node.textContent || '').includes({json.dumps(label)})
          );
          if (!button) return false;
          button.scrollIntoView({{ block: 'center', inline: 'center' }});
          button.click();
          return true;
        }})()
        """,
    )
    if not clicked:
        raise RuntimeError(f"Could not click button containing text {label!r}")


def read_skill_state(cdp: object) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        """
        (() => {
          const agencyNode = document.querySelector('[data-skill-agency-count]');
          const agencyCount = Number(agencyNode?.getAttribute('data-skill-agency-count') || '0');
          const categoryCards = Array.from(document.querySelectorAll('[data-skill-category-card]'));
          const railItems = Array.from(document.querySelectorAll('[data-skill-rail-item]')).map((node) => node.getAttribute('data-skill-rail-item'));
          const notice = new URL(window.location.href).searchParams.get('team_notice') || '';
          const error = new URL(window.location.href).searchParams.get('team_error') || '';
          return {
            agencyCount,
            categoryCardCount: categoryCards.length,
            firstCategoryText: categoryCards[0]?.textContent || '',
            railItems,
            notice,
            error,
          };
        })()
        """,
    )
    return state if isinstance(state, dict) else {}


def read_detail_state(cdp: object, skill_id: str) -> dict[str, object]:
    detail_selector = f'[data-skill-detail-drawer="{skill_id}"]'
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const drawer = document.querySelector({json.dumps(detail_selector)});
          const text = drawer?.textContent || document.body.innerText || '';
          return {{
            drawerVisible: !!drawer,
            bodyText: text,
          }};
        }})()
        """,
    )
    return state if isinstance(state, dict) else {}


def main() -> int:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    login_url = f"{args.web_base.rstrip('/')}/login"
    skills_path = f"/projects/{args.project_id}?panel=team&tab=skills"
    skills_url = f"{args.web_base.rstrip('/')}{skills_path}"
    report_path = output_dir / f"skill-import-validation-report-{stamp}.json"
    screenshots: list[str] = []

    token, user = api_login(args.api_base, args.login_email, args.login_password)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-edge-python-cdp-"))
    edge_process = None
    cdp = None
    try:
        edge_process = cdp_helpers.subprocess.Popen(
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
            stdout=cdp_helpers.subprocess.DEVNULL,
            stderr=cdp_helpers.subprocess.DEVNULL,
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
        shot = output_dir / f"skill-import-01-login-{stamp}.png"
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
            "document.readyState === 'complete' && !!document.querySelector('[data-skill-import-agency-pack=\"1\"]')",
            timeout_seconds=60,
        )
        wait_for_panel_idle(cdp, timeout_seconds=60)
        before_state = read_skill_state(cdp)
        shot = output_dir / f"skill-import-02-before-import-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        submit_form(cdp, '[data-skill-import-agency-pack="1"]')
        wait_for_panel_idle(cdp, timeout_seconds=90)
        wait_for(
          cdp,
          "window.location.href.includes('team_notice=') || window.location.href.includes('team_error=')",
          timeout_seconds=90,
        )
        after_state = read_skill_state(cdp)
        if after_state.get("error"):
            raise RuntimeError(f"Skill import returned team_error: {after_state['error']}")
        if int(after_state.get("agencyCount") or 0) < 185:
            raise RuntimeError(f"Agency skill count too low after import: {after_state}")
        if int(after_state.get("categoryCardCount") or 0) < 5:
            raise RuntimeError(f"Category cards did not render after import: {after_state}")
        shot = output_dir / f"skill-import-03-after-import-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        target_skill_id = "agency-frontend-developer"
        detail_url = f"{skills_url}&drawer=skill-detail&drawer_id={target_skill_id}"
        target_detail_selector = f'[data-skill-detail-drawer="{target_skill_id}"]'
        cdp.send("Page.navigate", {"url": detail_url})
        wait_for(
            cdp,
            f"!!document.querySelector({json.dumps(target_detail_selector)})",
            timeout_seconds=30,
        )
        detail_state = read_detail_state(cdp, target_skill_id)
        if not detail_state.get("drawerVisible"):
            raise RuntimeError(f"Skill detail drawer did not open: {detail_state}")
        body_text = str(detail_state.get("bodyText") or "")
        if "Agency Agents" not in body_text or "工程" not in body_text:
            raise RuntimeError(f"Skill detail drawer missing source/category text: {detail_state}")
        shot = output_dir / f"skill-import-04-detail-drawer-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        report = {
            "validated_at": datetime.now().astimezone().isoformat(),
            "project_id": args.project_id,
            "skills_url": skills_url,
            "before_state": before_state,
            "after_state": after_state,
            "detail_skill_id": target_skill_id,
            "detail_contains_source": "Agency Agents" in body_text,
            "detail_contains_category": "工程" in body_text,
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
