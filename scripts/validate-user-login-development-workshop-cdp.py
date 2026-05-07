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
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the real user path: login -> development workshop -> add NPC "
            "-> station owner list -> outdoor map NPC -> cleanup."
        )
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--station-id", default="project-generator")
    parser.add_argument("--station-label", default="project-generator")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=2048)
    parser.add_argument("--viewport-height", type=int, default=1152)
    parser.add_argument("--keep-seat", action="store_true")
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


def list_workstations(api_base: str, project_id: str, token: str) -> list[dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/thread-workstations",
        token=token,
    )
    data = payload.get("data") if isinstance(payload, dict) else payload
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def find_workstation_by_name(items: list[dict[str, object]], name: str) -> dict[str, object] | None:
    for item in items:
        if str(item.get("name") or item.get("label") or "").strip() == name:
            return item
    return None


def delete_workstation(api_base: str, project_id: str, token: str, workstation: dict[str, object]) -> None:
    workstation_id = str(workstation.get("id") or workstation.get("name") or "").strip()
    if not workstation_id:
        raise RuntimeError("Created workstation has no id/name for cleanup")
    request_json(
        f"{api_base.rstrip('/')}/api/collaboration/projects/{project_id}/thread-workstations/{quote(workstation_id, safe='')}",
        method="DELETE",
        token=token,
    )


def remove_validation_artifacts(workstation: dict[str, object]) -> list[str]:
    removed: list[str] = []
    metadata = workstation.get("metadata") if isinstance(workstation.get("metadata"), dict) else {}
    npc_knowledge = metadata.get("npc_knowledge") if isinstance(metadata.get("npc_knowledge"), dict) else {}
    handoff_path = str(npc_knowledge.get("handoff_path") or "").strip()
    if handoff_path:
        candidate = (REPO_ROOT / handoff_path).resolve()
        try:
            candidate.relative_to(REPO_ROOT.resolve())
        except ValueError:
            candidate = None  # type: ignore[assignment]
        if candidate and candidate.exists():
            candidate.unlink()
            removed.append(str(candidate))
    return removed


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
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1400])
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


def click_by_text(cdp: object, text: str, *, selector: str = "button, a", timeout_seconds: float = 20) -> dict[str, object]:
    expr = f"""
    (() => {{
      const needle = {json.dumps(text)};
      const items = Array.from(document.querySelectorAll({json.dumps(selector)}));
      const el = items.find((item) => (item.innerText || item.textContent || '').replace(/\\s+/g, ' ').includes(needle));
      if (!el) return {{ ok: false, reason: 'missing', needle, body: (document.body && document.body.innerText || '').slice(0, 1200) }};
      el.scrollIntoView({{ block: 'center', inline: 'center' }});
      const rect = el.getBoundingClientRect();
      return {{
        ok: true,
        text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 160),
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
        width: rect.width,
        height: rect.height
      }};
    }})()
    """
    point = wait_for(cdp, expr, timeout_seconds=timeout_seconds)
    if not isinstance(point, dict) or not point.get("ok"):
        raise RuntimeError(f"Could not find clickable text {text!r}: {point}")
    x = float(point["x"])
    y = float(point["y"])
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return point


def poll_created_workstation(
    api_base: str,
    project_id: str,
    token: str,
    temp_name: str,
    *,
    timeout_seconds: float = 50,
) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_count = 0
    while time.time() < deadline:
        items = list_workstations(api_base, project_id, token)
        last_count = len(items)
        match = find_workstation_by_name(items, temp_name)
        if match:
            return match
        time.sleep(1.0)
    raise RuntimeError(f"Created workstation {temp_name!r} not found in API list; last_count={last_count}")


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    temp_name = f"Temp DevWorkshop NPC {stamp}"
    temp_role = "Ephemeral validation owner for development workshop station. Delete after test."
    station_path = f"/projects/{args.project_id}?panel=team&tab=development-workshop"
    login_url = f"{web_base}/login?returnTo={quote(station_path, safe='')}"
    station_url = f"{web_base}{station_path}"

    token, user = api_login(api_base, args.login_email, args.login_password)
    before_items = list_workstations(api_base, args.project_id, token)
    created: dict[str, object] | None = None
    cleaned = False
    artifact_cleanup: list[str] = []

    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-dev-workshop-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    screenshots: list[str] = []

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
                "--disable-background-networking",
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
        shot = output_dir / f"development-workshop-01-login-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        login_result = cdp_eval(
            cdp,
            f"""
            (() => {{
              const email = document.querySelector('input[name="email"], input[type="email"]');
              const password = document.querySelector('input[name="password"], input[type="password"]');
              if (!email || !password) return {{ ok: false, reason: 'missing-fields' }};
              email.value = {json.dumps(args.login_email)};
              email.dispatchEvent(new Event('input', {{ bubbles: true }}));
              email.dispatchEvent(new Event('change', {{ bubbles: true }}));
              password.value = {json.dumps(args.login_password)};
              password.dispatchEvent(new Event('input', {{ bubbles: true }}));
              password.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return {{ ok: true }};
            }})()
            """,
        )
        if not isinstance(login_result, dict) or not login_result.get("ok"):
            raise RuntimeError(f"Login fields did not fill: {login_result}")
        try:
            click_by_text(cdp, "\u8fdb\u5165\u5e73\u53f0", selector="button")
        except RuntimeError:
            click_by_text(cdp, "\u767b\u5f55", selector="button")

        try:
            wait_for(cdp, f"location.href.includes({json.dumps(args.project_id)})", timeout_seconds=45)
        except Exception:
            cdp.send("Page.navigate", {"url": station_url})
        wait_for(
            cdp,
            "document.body && document.body.innerText.includes('\u5f00\u53d1\u5de5\u574a') && document.body.innerText.includes('\u5de5\u4f4d\u680f')",
            timeout_seconds=60,
        )
        time.sleep(1.0)
        shot = output_dir / f"development-workshop-02-station-panel-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        add_click = click_by_text(cdp, "\u7ed9\u6b64\u5de5\u4f4d\u6dfb\u52a0 NPC", selector="button")
        wait_for(
            cdp,
            "document.querySelector('input[name=\"development_station_id\"]') && document.querySelector('input[name=\"name\"]') && document.body.innerText.includes('\u4e09\u7ea7')",
            timeout_seconds=30,
        )
        drawer_state = cdp_eval(
            cdp,
            f"""
            (() => {{
              const q = (name) => document.querySelector(`[name="${{name}}"]`);
              return {{
                stationId: q('development_station_id')?.value || '',
                stationLabel: q('development_station_label')?.value || '',
                defaultName: q('name')?.value || '',
                defaultRole: q('responsibility')?.value || '',
                returnTo: q('return_to')?.value || '',
                sourceThread: q('source_workstation_id')?.value || '',
                provider: q('ai_provider')?.value || ''
              }};
            }})()
            """,
        )
        if not isinstance(drawer_state, dict):
            raise RuntimeError(f"Unexpected drawer state: {drawer_state}")
        if drawer_state.get("stationId") != args.station_id:
            raise RuntimeError(f"Drawer station id mismatch: {drawer_state}")
        if "development-workshop" not in str(drawer_state.get("returnTo") or ""):
            raise RuntimeError(f"Drawer return_to should preserve development workshop: {drawer_state}")
        shot = output_dir / f"development-workshop-03-add-npc-drawer-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        fill_result = cdp_eval(
            cdp,
            f"""
            (() => {{
              const setValue = (name, value) => {{
                const el = document.querySelector(`[name="${{name}}"]`);
                if (!el) return false;
                el.value = value;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
              }};
              return {{
                name: setValue('name', {json.dumps(temp_name)}),
                responsibility: setValue('responsibility', {json.dumps(temp_role)}),
                source: setValue('source_workstation_id', ''),
                node: setValue('computer_node_id', ''),
                provider: setValue('ai_provider', 'Codex'),
                model: setValue('model', 'gpt-5.4'),
                knowledge: setValue('knowledge_summary', 'Ephemeral CDP validation for development workshop station ownership.')
              }};
            }})()
            """,
        )
        if not isinstance(fill_result, dict) or not fill_result.get("name") or not fill_result.get("responsibility"):
            raise RuntimeError(f"Create form did not fill: {fill_result}")
        submit_click = click_by_text(cdp, "\u521b\u5efa NPC", selector="button")

        created = poll_created_workstation(api_base, args.project_id, token, temp_name)
        metadata = created.get("metadata") if isinstance(created.get("metadata"), dict) else {}
        if metadata.get("development_station_id") != args.station_id:
            raise RuntimeError(f"Created NPC missing station metadata: {metadata}")
        if metadata.get("scene") != "map-farm":
            raise RuntimeError(f"Created NPC must stay outside the house on map-farm: {metadata}")

        wait_for(cdp, f"location.href.includes({json.dumps(args.project_id)})", timeout_seconds=30)
        cdp.send("Page.navigate", {"url": station_url})
        wait_for(
            cdp,
            f"document.body && document.body.innerText.includes({json.dumps(temp_name)}) && document.body.innerText.includes('\u5f53\u524d\u5de5\u4f4d\u8d1f\u8d23\u4eba NPC')",
            timeout_seconds=60,
        )
        owner_list_state = cdp_eval(
            cdp,
            f"""
            (() => {{
              const listItems = Array.from(document.querySelectorAll('li'));
              const ownerItem = listItems.find((item) => (item.innerText || '').includes({json.dumps(temp_name)}));
              const badges = Array.from(document.querySelectorAll('span')).map((item) => (item.innerText || '').trim()).filter(Boolean);
              return {{
                hasTempInOwnerList: !!ownerItem,
                ownerItemText: ownerItem ? ownerItem.innerText.slice(0, 400) : '',
                badges: badges.slice(0, 80)
              }};
            }})()
            """,
        )
        if not isinstance(owner_list_state, dict) or not owner_list_state.get("hasTempInOwnerList"):
            raise RuntimeError(f"Created NPC is not visibly listed as station owner: {owner_list_state}")
        time.sleep(1.0)
        shot = output_dir / f"development-workshop-04-created-owner-list-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        cdp_eval(
            cdp,
            """
            (() => {
              const frame = document.querySelector('iframe');
              if (!frame) return false;
              const url = new URL(frame.src, location.href);
              url.searchParams.set('scene', 'map-farm');
              url.searchParams.set('x', '760');
              url.searchParams.set('y', '720');
              frame.src = url.toString();
              return true;
            })()
            """,
        )
        wait_for(
            cdp,
            f"""
            (() => {{
              const frame = document.querySelector('iframe');
              const win = frame && frame.contentWindow;
              const list = win && Array.isArray(win.__platformSeatNpcWorldSnapshot) ? win.__platformSeatNpcWorldSnapshot : [];
              return list.some((item) => String(item.label || '').includes({json.dumps(temp_name)}));
            }})()
            """,
            timeout_seconds=60,
        )
        outdoor_snapshot = cdp_eval(
            cdp,
            """
            (() => {
              const frame = document.querySelector('iframe');
              const win = frame && frame.contentWindow;
              const list = win && Array.isArray(win.__platformSeatNpcWorldSnapshot) ? win.__platformSeatNpcWorldSnapshot : [];
              return list.map((item) => ({ id: item.id, label: item.label, scene: item.scene, x: item.x, y: item.y })).slice(0, 20);
            })()
            """,
        )
        shot = output_dir / f"development-workshop-05-outdoor-map-npc-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        cdp_eval(
            cdp,
            """
            (() => {
              const frame = document.querySelector('iframe');
              if (!frame) return false;
              const url = new URL(frame.src, location.href);
              url.searchParams.set('scene', 'map-home');
              url.searchParams.set('x', '1010');
              url.searchParams.set('y', '520');
              frame.src = url.toString();
              return true;
            })()
            """,
        )
        time.sleep(2.0)
        home_snapshot = cdp_eval(
            cdp,
            f"""
            (() => {{
              const frame = document.querySelector('iframe');
              const win = frame && frame.contentWindow;
              const list = win && Array.isArray(win.__platformSeatNpcWorldSnapshot) ? win.__platformSeatNpcWorldSnapshot : [];
              return {{
                hasTempInHome: list.some((item) => String(item.label || '').includes({json.dumps(temp_name)})),
                items: list.map((item) => ({{ id: item.id, label: item.label, scene: item.scene }})).slice(0, 20)
              }};
            }})()
            """,
        )
        if isinstance(home_snapshot, dict) and home_snapshot.get("hasTempInHome"):
            raise RuntimeError(f"Created NPC leaked into map-home: {home_snapshot}")

        if not args.keep_seat and created:
            delete_workstation(api_base, args.project_id, token, created)
            artifact_cleanup = remove_validation_artifacts(created)
            cleaned = True
            remaining = list_workstations(api_base, args.project_id, token)
            if find_workstation_by_name(remaining, temp_name):
                raise RuntimeError(f"Temporary NPC was not cleaned up: {temp_name}")

        report = {
            "stamp": stamp,
            "project_id": args.project_id,
            "login_email": args.login_email,
            "user": user,
            "temp_name": temp_name,
            "before_count": len(before_items),
            "created": created,
            "cleaned": cleaned,
            "artifact_cleanup": artifact_cleanup,
            "screenshots": screenshots,
            "drawer_state": drawer_state,
            "fill_result": fill_result,
            "owner_list_state": owner_list_state,
            "clicks": {"add": add_click, "submit": submit_click},
            "outdoor_snapshot": outdoor_snapshot,
            "home_snapshot": home_snapshot,
        }
        report_path = output_dir / f"development-workshop-user-flow-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)
        if created and not args.keep_seat and not cleaned:
            try:
                delete_workstation(api_base, args.project_id, token, created)
                remove_validation_artifacts(created)
                print(f"cleanup-after-failure: removed {temp_name}", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001
                print(f"cleanup-after-failure failed for {temp_name}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
