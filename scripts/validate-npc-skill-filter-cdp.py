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
    parser = argparse.ArgumentParser(description="Validate NPC skill loadout filtering through the real NPC create drawer.")
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


def scroll_drawer_to_picker(cdp: object) -> None:
    cdp_eval(
        cdp,
        """
        (() => {
          const body = document.querySelector('[data-npc-skill-picker="npc-create"]');
          if (!body) return false;
          body.scrollIntoView({ block: 'center', inline: 'nearest' });
          return true;
        })()
        """,
    )


def read_picker_state(cdp: object) -> dict[str, object]:
    result = cdp_eval(
        cdp,
        """
        (() => {
          const picker = document.querySelector('[data-npc-skill-picker="npc-create"]');
          const visibleCountRaw = document.querySelector('[data-npc-skill-visible-count]')?.getAttribute('data-npc-skill-visible-count') || '';
          const selectedCountRaw = document.querySelector('[data-npc-skill-selected-count]')?.getAttribute('data-npc-skill-selected-count') || '';
          const options = Array.from(document.querySelectorAll('[data-npc-skill-option^="npc-create:"]'));
          const selected = Array.from(document.querySelectorAll('[data-npc-skill-selected-chip^="npc-create:"]'));
          return {
            pickerVisible: !!picker,
            visibleCountRaw,
            selectedCountRaw,
            optionCount: options.length,
            optionTexts: options.slice(0, 12).map((node) => (node.textContent || '').trim()),
            selectedTexts: selected.slice(0, 12).map((node) => (node.textContent || '').trim()),
            bodyText: document.body.innerText.slice(0, 2000),
          };
        })()
        """,
    )
    return result if isinstance(result, dict) else {}


def main() -> int:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    login_url = f"{args.web_base.rstrip('/')}/login"
    drawer_url = (
        f"{args.web_base.rstrip('/')}/projects/{args.project_id}"
        "?panel=team&tab=npc-create&drawer=npc-create"
    )
    report_path = output_dir / f"npc-skill-filter-validation-report-{stamp}.json"
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
        shot = output_dir / f"npc-skill-filter-01-login-{stamp}.png"
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

        cdp.send("Page.navigate", {"url": drawer_url})
        wait_for(
            cdp,
            "document.readyState === 'complete' && !!document.querySelector('[data-npc-skill-picker=\"npc-create\"]')",
            timeout_seconds=60,
        )
        wait_for_panel_idle(cdp, timeout_seconds=60)
        scroll_drawer_to_picker(cdp)
        before_state = read_picker_state(cdp)
        if not before_state.get("pickerVisible"):
            raise RuntimeError(f"NPC skill picker not visible: {before_state}")
        shot = output_dir / f"npc-skill-filter-02-before-filter-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        if str(before_state.get("selectedCountRaw") or "") != "npc-create:0":
            click_selector(cdp, '[data-npc-skill-selected-clear="npc-create"]')
            wait_for(
                cdp,
                """
                (() => {
                  const count = document.querySelector('[data-npc-skill-selected-count]')?.getAttribute('data-npc-skill-selected-count') || '';
                  return count === 'npc-create:0';
                })()
                """,
                timeout_seconds=30,
            )

        click_selector(cdp, '[data-npc-skill-preset="npc-create-frontend"]')
        wait_for(
            cdp,
            """
            (() => {
              const options = Array.from(document.querySelectorAll('[data-npc-skill-option^="npc-create:"]'));
              if (!options.length) return false;
              const text = options.map((node) => (node.textContent || '').toLowerCase()).join(' ');
              return text.includes('frontend');
            })()
            """,
            timeout_seconds=30,
        )
        scroll_drawer_to_picker(cdp)
        after_preset_state = read_picker_state(cdp)
        option_text = " ".join(str(item) for item in after_preset_state.get("optionTexts") or [])
        if "frontend" not in option_text.lower():
            raise RuntimeError(f"Filtered option list did not surface frontend skills: {after_preset_state}")
        if "accounts payable" in option_text.lower():
            raise RuntimeError(f"Unrelated specialized skill still visible after frontend preset: {after_preset_state}")
        shot = output_dir / f"npc-skill-filter-03-after-preset-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_selector(cdp, '[data-npc-skill-option="npc-create:agency-frontend-developer"] input[type="checkbox"]')
        wait_for(
            cdp,
            """
            (() => {
              const count = document.querySelector('[data-npc-skill-selected-count]')?.getAttribute('data-npc-skill-selected-count') || '';
              return count === 'npc-create:1';
            })()
            """,
            timeout_seconds=30,
        )
        after_select_state = read_picker_state(cdp)
        selected_text = " ".join(str(item) for item in after_select_state.get("selectedTexts") or [])
        if "frontend developer" not in selected_text.lower():
            raise RuntimeError(f"Selected skill tray did not surface frontend selection: {after_select_state}")
        if "前端工位" not in selected_text:
            raise RuntimeError(f"Selected skill tray did not show suitable workstation guidance: {after_select_state}")
        if "页面框架草图" not in selected_text:
            raise RuntimeError(f"Selected skill tray did not show common deliverables: {after_select_state}")
        shot = output_dir / f"npc-skill-filter-04-after-select-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_selector(cdp, '[data-npc-skill-selected-chip="npc-create:agency-frontend-developer"]')
        wait_for(
            cdp,
            """
            (() => {
              const count = document.querySelector('[data-npc-skill-selected-count]')?.getAttribute('data-npc-skill-selected-count') || '';
              return count === 'npc-create:0';
            })()
            """,
            timeout_seconds=30,
        )
        after_remove_state = read_picker_state(cdp)
        shot = output_dir / f"npc-skill-filter-05-after-remove-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        report = {
            "validated_at": datetime.now().astimezone().isoformat(),
            "project_id": args.project_id,
            "drawer_url": drawer_url,
            "before_state": before_state,
            "after_preset_state": after_preset_state,
            "after_select_state": after_select_state,
            "after_remove_state": after_remove_state,
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
