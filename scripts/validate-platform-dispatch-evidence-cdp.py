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
from urllib.parse import urlencode
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
            "Read-only validation for the current NPC workbench dispatch evidence: "
            "NPC tiles, desktop-visible state, minimal receipts, review hints, and no internal terms."
        ),
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", default="proj_ai_collab")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/platform-dispatch-evidence")
    parser.add_argument("--viewport-width", type=int, default=1280)
    parser.add_argument("--viewport-height", type=int, default=720)
    parser.add_argument("--seats", default="", help="Optional comma-separated NPC names/config ids to open.")
    parser.add_argument("--boss-message-id", default="86c267bd-3f58-48f6-9605-ff0c46526b79")
    parser.add_argument("--boss-receipt-id", default="208c9715-9045-43f2-a0c6-2995bcc1828c")
    parser.add_argument(
        "--peer-message-ids",
        default="5771dd2d-dbf0-4689-9c7d-432a072ad97b,0d1ba683-e8d8-43f1-82f0-9e8daa4c7f9f,4db8e69d-28f3-485b-9c55-21b71bb44460,be59fc1c-42a8-4fdf-adc6-a6eacffee6cf",
    )
    parser.add_argument("--hardware-review-id", default="b8055690-0190-44d1-b9be-da7d4d4e6d13")
    return parser.parse_args()


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    token: str = "",
    timeout: int = 25,
) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def get_token(args: argparse.Namespace) -> tuple[str, str]:
    if args.no_auth:
        return "", ""
    if args.token:
        return args.token, args.userjson
    payload = request_json(
        f"{args.api_base.rstrip('/')}/api/auth/session",
        method="POST",
        payload={"email": args.login_email, "password": args.login_password},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get("access_token"):
        raise RuntimeError("Auth response did not include access_token")
    return str(data["access_token"]), json.dumps(data.get("user") or {}, ensure_ascii=True)


def api_get(args: argparse.Namespace, token: str, path: str, query: dict[str, object] | None = None) -> object:
    suffix = path if path.startswith("/") else f"/{path}"
    url = f"{args.api_base.rstrip()}{suffix}"
    if query:
        url = f"{url}?{urlencode(query)}"
    payload = request_json(url, token=token)
    return payload.get("data")


def list_messages(args: argparse.Namespace, token: str, **query: object) -> list[dict[str, object]]:
    data = api_get(args, token, "/api/collaboration/messages", {"project_id": args.project_id, **query})
    return data if isinstance(data, list) else []


def find_message(messages: list[dict[str, object]], message_id: str) -> dict[str, object] | None:
    return next((item for item in messages if str(item.get("id") or "") == message_id), None)


def artifact_exists_from_message(message: dict[str, object]) -> tuple[bool, str]:
    body = str(message.get("body") or "")
    marker = "完整输出可查看本地 artifact:"
    if marker not in body:
        return False, ""
    path = body.split(marker, 1)[1].strip().splitlines()[0].strip().strip("`")
    if not path:
        return False, ""
    return (REPO_ROOT / path).exists(), path


def cdp_eval(cdp: object, expression: str) -> object:
    result = cdp.send(
        "Runtime.evaluate",
        {"expression": expression, "awaitPromise": True, "returnByValue": True, "userGesture": True},
    )
    if "exceptionDetails" in result:
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1600])
    value = result.get("result", {})
    return value.get("value") if isinstance(value, dict) else None


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 35, interval_seconds: float = 0.35) -> object:
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
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def capture_workbench(args: argparse.Namespace, token: str, user_json: str, output_dir: Path, stamp: str) -> dict[str, object]:
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-dispatch-evidence-edge-"))
    edge_process: subprocess.Popen[bytes] | None = None
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
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")), None)
        if not isinstance(page_target, dict):
            raise RuntimeError("No Edge page target available")
        cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.viewport_width,
                "height": args.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        origin = args.web_base.rstrip("/")
        if token:
            cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        if user_json:
            cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        seat_query = str(getattr(args, "seats", "") or "").strip()
        if seat_query:
            from urllib.parse import quote

            seats = "%2C".join([quote(item.strip(), safe="") for item in seat_query.split(",") if item.strip()])
            url = f"{origin}/projects/{args.project_id}/workbench?seats={seats}"
        else:
            url = f"{origin}/projects/{args.project_id}/workbench"
        cdp.send("Page.navigate", {"url": url})
        wait_for(cdp, "document.readyState === 'complete' && document.body && document.body.innerText.includes('协同工作台')", timeout_seconds=40)
        time.sleep(2.0)
        cdp_eval(
            cdp,
            """
            (() => {
              const params = new URLSearchParams(location.search);
              const alreadyOpen = Array.from(document.querySelectorAll('textarea')).some((node) => {
                const placeholder = node.getAttribute('placeholder') || '';
                const visible = !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
                return visible && placeholder.includes('发指令');
              });
              if (alreadyOpen || params.get('seats')) return true;
              const openButton = Array.from(document.querySelectorAll('a[title="打开瓷砖"], a[data-workbench-open-tile]')).find((item) => {
                const rowText = item.closest('li')?.innerText || item.textContent || '';
                return rowText && !/Boss|资源|总览/.test(rowText);
              }) || document.querySelector('a[title="打开瓷砖"], a[data-workbench-open-tile]');
              if (openButton) {
                openButton.scrollIntoView({ block: 'center', inline: 'nearest' });
                openButton.click();
              }
              return Boolean(openButton) || alreadyOpen;
            })()
            """,
        )
        wait_for(
            cdp,
            """
            (() => {
              const body = document.body?.innerText || '';
              const composer = Array.from(document.querySelectorAll('textarea')).some((node) => {
                const placeholder = node.getAttribute('placeholder') || '';
                const visible = !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
                return visible && placeholder.includes('发指令');
              });
              return composer && body.includes('对话') && body.includes('我的需求') && body.includes('我的任务');
            })()
            """,
            timeout_seconds=45,
        )
        state = cdp_eval(
            cdp,
            """
            (() => {
              const body = document.body?.innerText || '';
              const composers = Array.from(document.querySelectorAll('textarea')).filter((node) => {
                const placeholder = node.getAttribute('placeholder') || '';
                const visible = !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
                return visible && placeholder.includes('发指令');
              }).map((node) => node.getAttribute('placeholder') || '');
              return { body, composers };
            })()
            """,
        )
        state = state if isinstance(state, dict) else {}
        text = str(state.get("body") or "")
        composers = state.get("composers") if isinstance(state.get("composers"), list) else []
        shot = output_dir / f"workbench-dispatch-evidence-{stamp}.png"
        screenshot(cdp, shot)
        internal_terms = [
            term
            for term in ["adapter", "bridge", "session JSONL", "source_thread", "canonical", "requested id", "raw UUID"]
            if term.lower() in text.lower()
        ]
        return {
            "url": str(cdp_eval(cdp, "location.href") or ""),
            "screenshot": str(shot),
            "failed_fetch_count": text.count("Failed to fetch"),
            "has_tile": "的对话" in text and bool(composers),
            "visible_composers": composers,
            "has_need_task_tabs": "我的需求" in text and "我的任务" in text,
            "has_desktop_or_runner_state": any(marker in text for marker in ["桌面", "电脑", "可投递", "等待电脑恢复", "离线"]),
            "has_receipt_or_review_hint": any(marker in text for marker in ["查看回执", "查看正文", "人工确认", "风险级别", "暂无协作消息"]),
            "internal_terms": internal_terms,
        }
    finally:
        if cdp is not None:
            try:
                cdp.close()
            except Exception:  # noqa: BLE001
                pass
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


def capture_observability(args: argparse.Namespace, token: str, user_json: str, output_dir: Path, stamp: str) -> dict[str, object]:
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-observability-evidence-edge-"))
    edge_process: subprocess.Popen[bytes] | None = None
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
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")), None)
        if not isinstance(page_target, dict):
            raise RuntimeError("No Edge page target available")
        cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.viewport_width,
                "height": args.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        origin = args.web_base.rstrip("/")
        if token:
            cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        if user_json:
            cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        url = f"{origin}/projects/{args.project_id}/observability"
        cdp.send("Page.navigate", {"url": url})
        wait_for(
            cdp,
            "document.readyState === 'complete' && document.body && document.body.innerText.includes('观测台') && document.body.innerText.includes('派工验真')",
            timeout_seconds=40,
        )
        time.sleep(2.0)
        text = str(cdp_eval(cdp, "document.body ? document.body.innerText : ''") or "")
        shot = output_dir / f"observability-dispatch-evidence-{stamp}.png"
        screenshot(cdp, shot)
        return {
            "url": str(cdp_eval(cdp, "location.href") or ""),
            "screenshot": str(shot),
            "has_dispatch_evidence": "派工验真" in text and "桌面 6/6" in text,
            "has_workbench_link": "打开 NPC 工作台" in text,
            "has_api_instance": "API 实例" in text and "127.0.0.1:8011" in text,
            "needs_processing": "需要处理" in text,
            "chain_ready": "链路可用" in text,
        }
    finally:
        if cdp is not None:
            try:
                cdp.close()
            except Exception:  # noqa: BLE001
                pass
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    token, user_json = get_token(args)

    checks: list[dict[str, object]] = []
    ui_state = capture_workbench(args, token, user_json, output_dir, stamp)
    checks.append({
        "name": "current workbench dispatch evidence",
        "ok": (
            ui_state["failed_fetch_count"] == 0
            and bool(ui_state.get("has_tile"))
            and bool(ui_state.get("has_need_task_tabs"))
            and bool(ui_state.get("has_desktop_or_runner_state"))
            and bool(ui_state.get("has_receipt_or_review_hint"))
            and not ui_state.get("internal_terms")
        ),
        "detail": ui_state,
    })

    ok = all(bool(item["ok"]) for item in checks)
    report = {
        "ok": ok,
        "project_id": args.project_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "checks": checks,
    }
    report_path = output_dir / f"platform-dispatch-evidence-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": ok, "report": str(report_path), "ui": ui_state}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
