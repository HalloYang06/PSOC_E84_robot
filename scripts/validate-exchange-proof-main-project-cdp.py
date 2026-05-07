from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

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
    parser = argparse.ArgumentParser(description="Validate the live main-project exchange proof detail drawer without mutating project data.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
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
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
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


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def click_selector(cdp: object, selector: str, *, timeout_seconds: float = 20) -> dict[str, object]:
    point = wait_for(
        cdp,
        f"""
        (() => {{
          const el = document.querySelector({json.dumps(selector)});
          if (!el) return null;
          if ('disabled' in el && el.disabled) {{
            return {{ ok: false, reason: 'disabled', text: (el.innerText || el.textContent || '').trim() }};
          }}
          el.scrollIntoView({{ block: 'center', inline: 'center' }});
          const rect = el.getBoundingClientRect();
          return {{
            ok: true,
            text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 160),
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
          }};
        }})()
        """,
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(point, dict) or not point.get("ok"):
        raise RuntimeError(f"Could not click selector {selector!r}: {point}")
    x = float(point["x"])
    y = float(point["y"])
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return point


def main() -> int:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    exchange_path = f"/projects/{args.project_id}?panel=team&tab=exchange"
    login_url = f"{args.web_base.rstrip('/')}/login?returnTo={quote(exchange_path, safe='')}"
    token, user = api_login(args.api_base, args.login_email, args.login_password)

    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-main-proof-cdp-"))
    edge_process = None
    cdp = None
    screenshots: list[str] = []
    report_path = output_dir / f"exchange-proof-main-project-report-{stamp}.json"
    report: dict[str, object] = {
        "runtime": {
            "web_base": args.web_base,
            "api_base": args.api_base,
            "project_id": args.project_id,
        },
        "user": user,
        "screenshots": screenshots,
    }

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
        shot = output_dir / f"exchange-proof-main-01-login-{stamp}.png"
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
        cdp.send("Page.navigate", {"url": f"{args.web_base.rstrip('/')}{exchange_path}"})
        wait_for(
            cdp,
            "document.readyState === 'complete' && !!document.querySelector('[data-exchange-nav-target=\"advanced-proof\"]')",
            timeout_seconds=60,
        )
        wait_for(
            cdp,
            "(() => { const panel = document.querySelector('#project-main-panel'); return !!panel && panel.getAttribute('data-busy') !== 'true'; })()",
            timeout_seconds=60,
        )
        shot = output_dir / f"exchange-proof-main-02-exchange-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        click_result = cdp_eval(
            cdp,
            """
            (() => {
              const button = document.querySelector('[data-exchange-nav-target=\"advanced-proof\"]');
              if (!button) return false;
              button.click();
              return true;
            })()
            """,
        )
        if not click_result:
            raise RuntimeError('Could not activate advanced-proof section')
        proof_lane_state = wait_for(
            cdp,
            """
            (() => {
              const section = document.querySelector('[data-exchange-section="advanced-proof"]');
              if (!section) return false;
              const details = section.querySelector('details');
              if (!(details instanceof HTMLDetailsElement)) return false;
              if (!details.open) details.open = true;
              section.scrollIntoView({ block: 'center', inline: 'nearest' });
              const items = Array.from(section.querySelectorAll('[data-exchange-proof-item]'));
              return {
                active: section.getAttribute('data-exchange-section-active') === 'true',
                detailsOpen: details.open,
                proofItemCount: items.length,
                detailButtonCount: section.querySelectorAll('[data-exchange-proof-item] [data-exchange-open-detail^="proof:"]').length,
                firstProofTitle: items[0]?.getAttribute('data-exchange-proof-title') || '',
                body: document.body ? document.body.innerText.slice(0, 5000) : '',
              };
            })()
            """,
            timeout_seconds=45,
        )
        if not isinstance(proof_lane_state, dict):
            raise RuntimeError(f"Could not resolve advanced proof lane state: {proof_lane_state}")
        report["proof_lane_state"] = proof_lane_state
        shot = output_dir / f"exchange-proof-main-03-proof-lane-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        proof_item_count = int(proof_lane_state.get("proofItemCount") or 0)
        detail_button_count = int(proof_lane_state.get("detailButtonCount") or 0)
        if proof_item_count <= 0 or detail_button_count <= 0:
            raise RuntimeError(f"Main project did not expose clickable proof cards: {proof_lane_state}")

        expected_title = str(proof_lane_state.get("firstProofTitle") or "").strip()
        trigger = wait_for(
            cdp,
            """
            (() => {
              const button = document.querySelector('[data-exchange-proof-item] [data-exchange-open-detail^="proof:"]');
              if (!button) return false;
              return {
                detailKey: button.getAttribute('data-exchange-open-detail') || '',
              };
            })()
            """,
            timeout_seconds=30,
        )
        if not isinstance(trigger, dict) or not str(trigger.get("detailKey") or "").strip():
            raise RuntimeError(f"Could not resolve proof detail trigger: {trigger}")
        detail_key = str(trigger["detailKey"])
        proof_detail_url = (
            f"{args.web_base.rstrip('/')}/projects/{args.project_id}"
            f"?panel=team&tab=exchange&drawer=exchange-detail&drawer_id={quote(detail_key, safe='')}"
        )
        cdp.send("Page.navigate", {"url": proof_detail_url})
        wait_for(
            cdp,
            "document.readyState === 'complete' && !!document.querySelector('[data-manager-drawer-kind=\"exchange-detail\"]')",
            timeout_seconds=60,
        )

        proof_drawer_state = wait_for(
            cdp,
            """
            (() => {
              const drawer = document.querySelector('[data-manager-drawer-kind="exchange-detail"]');
              if (!drawer) return false;
              const title = drawer.querySelector('strong')?.textContent || '';
              return {
                title,
                drawerText: (drawer.textContent || '').trim(),
                hasThreadJump: !!drawer.querySelector('[data-exchange-proof-jump-thread]'),
                hasSeatJump: !!drawer.querySelector('[data-exchange-proof-jump-seat]'),
              };
            })()
            """,
            timeout_seconds=45,
        )
        if not isinstance(proof_drawer_state, dict):
            raise RuntimeError(f"Could not resolve proof detail drawer state: {proof_drawer_state}")
        drawer_text = str(proof_drawer_state.get("drawerText") or "")
        if expected_title and expected_title not in drawer_text:
            raise RuntimeError(f"Proof detail drawer did not include expected title {expected_title!r}: {drawer_text[:600]!r}")
        if "真线程闭环证明" not in drawer_text:
            raise RuntimeError(f"Proof detail drawer did not expose proof detail copy: {drawer_text[:600]!r}")
        if "仓库与参考" not in drawer_text and "链路元信息" not in drawer_text:
            raise RuntimeError(f"Proof detail drawer did not expose proof metadata sections: {drawer_text[:600]!r}")
        if not bool(proof_drawer_state.get("hasThreadJump")) and not bool(proof_drawer_state.get("hasSeatJump")):
            raise RuntimeError(f"Proof detail drawer did not expose any jump actions: {proof_drawer_state}")
        report["proof_drawer_state"] = proof_drawer_state
        shot = output_dir / f"exchange-proof-main-04-proof-drawer-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        thread_jump_target = str(proof_drawer_state.get("hasThreadJump") and cdp_eval(
            cdp,
            """
            (() => {
              const button = document.querySelector('[data-manager-drawer-kind="exchange-detail"] [data-exchange-proof-jump-thread]');
              return button ? button.getAttribute('data-exchange-proof-jump-thread') || '' : '';
            })()
            """,
        ) or "")
        if not thread_jump_target:
            raise RuntimeError(f"Proof detail drawer did not expose a usable thread jump target: {proof_drawer_state}")

        click_selector(
            cdp,
            '[data-manager-drawer-kind="exchange-detail"] [data-exchange-proof-jump-thread]',
            timeout_seconds=30,
        )
        machine_room_focus_state = wait_for(
            cdp,
            """
            (() => {
              const panel = document.querySelector('#project-main-panel');
              if (!(panel instanceof HTMLElement) || panel.getAttribute('data-busy') === 'true') return false;
              const liveBanner = document.querySelector('[data-machine-room-focus-banner]');
              const historyBanner = document.querySelector('[data-machine-room-history-banner]');
              if (!liveBanner && !historyBanner) return false;
              const activeTab = document.querySelector('[data-panel-tab-active="true"]')?.textContent || '';
              return {
                activeTab,
                liveBannerId: liveBanner ? liveBanner.getAttribute('data-machine-room-focus-banner') || '' : '',
                historyBannerId: historyBanner ? historyBanner.getAttribute('data-machine-room-history-banner') || '' : '',
                panelText: (panel.textContent || '').slice(0, 4000),
              };
            })()
            """,
            timeout_seconds=45,
        )
        if not isinstance(machine_room_focus_state, dict):
            raise RuntimeError(f"Could not resolve machine-room focus state after proof jump: {machine_room_focus_state}")
        report["machine_room_focus_state"] = machine_room_focus_state
        if thread_jump_target not in {
            str(machine_room_focus_state.get("liveBannerId") or ""),
            str(machine_room_focus_state.get("historyBannerId") or ""),
        }:
            raise RuntimeError(
                f"Proof jump target {thread_jump_target!r} did not land on matching machine-room focus banner: {machine_room_focus_state}"
            )
        shot = output_dir / f"exchange-proof-main-05-machine-room-focus-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        report["result"] = {
            "advanced_proof_lane_visible": True,
            "main_project_has_clickable_proof_cards": True,
            "proof_detail_drawer_opened": True,
            "proof_detail_drawer_has_jump_action": True,
            "proof_thread_jump_opens_machine_room": True,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report["result"], ensure_ascii=False, indent=2))
        return 0
    finally:
        if cdp is not None:
            try:
                cdp.sock.close()
            except Exception:
                pass
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                edge_process.kill()
        if profile_dir.exists():
            import shutil

            shutil.rmtree(profile_dir, ignore_errors=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
