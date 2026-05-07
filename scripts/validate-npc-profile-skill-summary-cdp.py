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
    parser = argparse.ArgumentParser(description="Validate NPC profile skill summary through the real NPC manager UI.")
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


def list_rail_seats(cdp: object) -> list[dict[str, str]]:
    result = cdp_eval(
        cdp,
        """
        (() => Array.from(document.querySelectorAll('[data-npc-rail-seat]')).map((node) => ({
          id: node.getAttribute('data-npc-rail-seat') || '',
          text: (node.textContent || '').trim(),
        })))()
        """,
    )
    return result if isinstance(result, list) else []


def read_profile_state(cdp: object) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        """
        (() => {
          const drawer = document.querySelector('[data-npc-profile-skill-summary]');
          const cards = Array.from(document.querySelectorAll('[data-npc-profile-skill-card]'));
          const stationTexts = cards
            .map((node) => (node.textContent || '').trim())
            .filter((text) => text.includes('适合工位：'));
          const deliverableTexts = cards
            .map((node) => (node.textContent || '').trim())
            .filter((text) => text.includes('常见交付物：'));
          return {
            drawerVisible: !!drawer,
            summaryText: (drawer?.textContent || '').trim(),
            cardCount: cards.length,
            cardTexts: cards.slice(0, 6).map((node) => (node.textContent || '').trim()),
            hasStationMarkers: stationTexts.some((text) => text.replace(/^.*适合工位：/, '').trim().length >= 4),
            hasDeliverableMarkers: deliverableTexts.some((text) => text.replace(/^.*常见交付物：/, '').trim().length >= 4),
            selectedNpcName: document.querySelector('h3')?.textContent?.trim() || '',
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
    npc_url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=npc-create"
    report_path = output_dir / f"npc-profile-skill-summary-validation-report-{stamp}.json"
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
        shot = output_dir / f"npc-profile-skill-summary-01-login-{stamp}.png"
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

        cdp.send("Page.navigate", {"url": npc_url})
        wait_for(
            cdp,
            "document.readyState === 'complete' && !!document.querySelector('[data-npc-open-profile=\"1\"]')",
            timeout_seconds=60,
        )
        wait_for_panel_idle(cdp, timeout_seconds=60)
        shot = output_dir / f"npc-profile-skill-summary-02-npc-panel-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        rail_seats = list_rail_seats(cdp)
        if not rail_seats:
            raise RuntimeError("NPC rail did not expose any selectable seats")

        inspected_profiles: list[dict[str, object]] = []
        profile_state: dict[str, object] | None = None
        chosen_seat_id = ""
        for seat in rail_seats[:6]:
            seat_id = str(seat.get("id") or "")
            if not seat_id:
                continue
            click_selector(cdp, f'[data-npc-rail-seat="{seat_id}"]')
            wait_for_panel_idle(cdp, timeout_seconds=60)
            click_selector(cdp, '[data-npc-open-profile="1"]')
            wait_for(
                cdp,
                "!!document.querySelector('[data-npc-profile-skill-summary]')",
                timeout_seconds=30,
            )
            wait_for_panel_idle(cdp, timeout_seconds=60)
            current_state = read_profile_state(cdp)
            current_state["seat_id"] = seat_id
            current_state["seat_text"] = seat.get("text") or ""
            inspected_profiles.append(current_state)
            if int(current_state.get("cardCount") or 0) > 0:
                profile_state = current_state
                chosen_seat_id = seat_id
                break

        if not profile_state:
            raise RuntimeError(f"NPC profile drawer did not show any role skill cards across visible seats: {inspected_profiles}")
        if not profile_state.get("drawerVisible"):
            raise RuntimeError(f"NPC profile drawer did not open: {profile_state}")
        if not profile_state.get("hasStationMarkers"):
            raise RuntimeError(f"NPC profile drawer did not show suitable workstation markers: {profile_state}")
        if not profile_state.get("hasDeliverableMarkers"):
            raise RuntimeError(f"NPC profile drawer did not show deliverable markers: {profile_state}")
        shot = output_dir / f"npc-profile-skill-summary-03-profile-drawer-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        report = {
            "validated_at": datetime.now().astimezone().isoformat(),
            "project_id": args.project_id,
            "npc_url": npc_url,
            "inspected_profiles": inspected_profiles,
            "chosen_seat_id": chosen_seat_id,
            "profile_state": profile_state,
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
