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


SKILL_ID = "ai-required-requirement-ledger"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the fixed AI required requirement ledger skill in the real UI.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="78151f5f-f08c-4e83-b0fc-9be89263ecb3")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=1000)
    return parser.parse_args()


def request_json(url: str, *, method: str = "GET", payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


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


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 70, interval_seconds: float = 0.35) -> object:
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
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def read_skill_state(cdp: object) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const skillId = {json.dumps(SKILL_ID)};
          const subject = document.querySelector(`[data-skill-detail-drawer="${{skillId}}"]`);
          const intro = document.querySelector(`[data-skill-detail-intro="${{skillId}}"]`);
          const stations = document.querySelector(`[data-skill-fit-stations="${{skillId}}"]`);
          const deliverables = document.querySelector(`[data-skill-deliverables="${{skillId}}"]`);
          const bodyText = document.body ? document.body.innerText : "";
          return {{
            subjectVisible: !!subject,
            introVisible: !!intro,
            stationsVisible: !!stations,
            deliverablesVisible: !!deliverables,
            subjectText: (subject?.textContent || "").trim(),
            introText: (intro?.textContent || "").trim(),
            stationText: (stations?.textContent || "").trim(),
            deliverableText: (deliverables?.textContent || "").trim(),
            bodyHasLedgerTitle: bodyText.includes("AI 必读需求表"),
            bodyHasFixedSkill: bodyText.includes("固定必备 Skill"),
            bodyHasDocPath: bodyText.includes("docs/ai-requirements/ai-required-requirements-ledger.md"),
          }};
        }})()
        """,
    )
    return state if isinstance(state, dict) else {}


def assert_skill_state(state: dict[str, object]) -> None:
    subject = str(state.get("subjectText") or "")
    intro = str(state.get("introText") or "")
    stations = str(state.get("stationText") or "")
    deliverables = str(state.get("deliverableText") or "")
    if not state.get("subjectVisible") or "AI 必读需求表" not in subject:
        raise RuntimeError(f"Required ledger skill detail drawer did not open: {state}")
    if not state.get("introVisible") or "AI 协作契约守门位" not in intro or "token 控制" not in intro:
        raise RuntimeError(f"Required ledger skill intro is not specific enough: {state}")
    if not state.get("stationsVisible") or "协作调度工位" not in stations or "审核工位" not in stations:
        raise RuntimeError(f"Required ledger skill stations are not collaboration/review oriented: {state}")
    if not state.get("deliverablesVisible") or "人工审核边界" not in deliverables or "派单回执协议" not in deliverables:
        raise RuntimeError(f"Required ledger skill deliverables are not concrete enough: {state}")
    if not state.get("bodyHasDocPath"):
        raise RuntimeError(f"Required ledger skill did not show the mandatory doc path to users: {state}")
    if "游戏玩法工位" in stations or "玩法方案" in deliverables:
        raise RuntimeError(f"Required ledger skill is still being misclassified as a game skill: {state}")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    detail_url = (
        f"{args.web_base.rstrip('/')}/projects/{args.project_id}"
        f"?panel=team&tab=skills&drawer=skill-detail&drawer_id={SKILL_ID}"
    )
    token, user = api_login(args.api_base, args.login_email, args.login_password)
    cookie_domain = urlparse(args.web_base).hostname or "127.0.0.1"
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-edge-required-ledger-"))
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

        cdp.send("Page.navigate", {"url": detail_url})
        wait_for(
            cdp,
            f"document.readyState === 'complete' && !!document.querySelector('[data-skill-detail-drawer={json.dumps(SKILL_ID)}]')",
            timeout_seconds=80,
        )
        wait_for(cdp, "document.body && document.body.innerText.includes('AI 必读需求表')", timeout_seconds=30)
        state = read_skill_state(cdp)
        assert_skill_state(state)
        shot = output_dir / f"required-ledger-skill-detail-{stamp}.png"
        screenshot(cdp, shot)
        report_path = output_dir / f"required-ledger-skill-validation-report-{stamp}.json"
        report = {
            "validated_at": datetime.now().astimezone().isoformat(),
            "project_id": args.project_id,
            "skill_id": SKILL_ID,
            "detail_url": detail_url,
            "state": state,
            "screenshots": [str(shot)],
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
