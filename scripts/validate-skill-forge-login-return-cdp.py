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


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_HELPER_PATH = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helper: {CDP_HELPER_PATH}")
cdp_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helper)


FORBIDDEN_TERMS = [
    "adapter",
    "bridge",
    "session JSONL",
    "local path",
    "source_thread",
    "canonical",
    "requested id",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Skill Forge deep-link login return and company evidence context in a real browser.",
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--resource", default="seat:1号 NPC")
    parser.add_argument("--expected-stable-resource", default="seat:platform-npc-1")
    parser.add_argument("--tab", default="knowledge", choices=["skills", "knowledge", "git"])
    parser.add_argument("--output-dir", default="artifacts/skill-forge-login-return")
    return parser.parse_args()


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


def fill_field(cdp: object, selector: str, value: str) -> None:
    ok = cdp_eval(
        cdp,
        f"""
        (() => {{
          const field = document.querySelector({json.dumps(selector)});
          if (!field) return false;
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
          field.focus();
          if (setter) setter.call(field, {json.dumps(value)});
          else field.value = {json.dumps(value)};
          field.dispatchEvent(new Event('input', {{ bubbles: true }}));
          field.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return true;
        }})()
        """,
    )
    if not ok:
        raise RuntimeError(f"Could not fill selector {selector!r}")


def click_by_text(cdp: object, text: str, *, selector: str = "button, a", timeout_seconds: float = 20) -> None:
    point = wait_for(
        cdp,
        f"""
        (() => {{
          const needle = {json.dumps(text)};
          const items = Array.from(document.querySelectorAll({json.dumps(selector)}));
          const el = items.find((item) => (item.innerText || item.textContent || '').replace(/\\s+/g, ' ').includes(needle));
          if (!el) return false;
          el.scrollIntoView({{ block: 'center', inline: 'center' }});
          const rect = el.getBoundingClientRect();
          return {{ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
        }})()
        """,
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(point, dict):
        raise RuntimeError(f"Could not click text {text!r}: {point}")
    x = float(point["x"])
    y = float(point["y"])
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})


def click_first_link(cdp: object, text: str) -> str:
    href = wait_for(
        cdp,
        f"""
        (() => {{
          const needle = {json.dumps(text)};
          const link = Array.from(document.querySelectorAll('a')).find((item) =>
            (item.innerText || item.textContent || '').replace(/\\s+/g, ' ').includes(needle)
          );
          if (!link) return '';
          link.scrollIntoView({{ block: 'center', inline: 'center' }});
          const href = link.getAttribute('href') || '';
          link.click();
          return href;
        }})()
        """,
        timeout_seconds=20,
    )
    if not isinstance(href, str) or not href:
        raise RuntimeError(f"Could not click link containing {text!r}")
    return href


def read_page_state(cdp: object) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const text = document.body ? document.body.innerText || '' : '';
          const lower = text.toLowerCase();
          return {{
            url: location.href,
            blank: text.trim().length < 40,
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 ||
              document.body.scrollWidth > document.documentElement.clientWidth + 1,
            hasOpenedNpc: text.includes('1号 NPC') && text.includes('知识库配置') && text.includes('最近索引'),
            hasNeedAuditLink: text.includes('看需求验收详情'),
            hasTaskAuditLink: text.includes('看任务验收详情'),
            hasAcceptanceDetail: text.includes('验收详情'),
            forbiddenHits: {json.dumps(FORBIDDEN_TERMS)}.filter((term) => lower.includes(term.toLowerCase())),
            rawUuidHits: Array.from(text.matchAll(/[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}/ig)).map((match) => match[0]).slice(0, 8),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError("Could not read page state")
    return state


def new_cdp() -> tuple[object, subprocess.Popen[bytes], Path]:
    port = cdp_helper.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-skill-forge-login-cdp-"))
    edge_process = subprocess.Popen(
        [
            str(cdp_helper.find_edge()),
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
    targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
    if not isinstance(targets, list) or not targets:
        cdp_helper.request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
    page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page"), None)
    if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
        raise RuntimeError("No CDP page target available")
    cdp = cdp_helper.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
    cdp.sock.settimeout(60)
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    cdp.send("Network.enable")
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    return cdp, edge_process, profile_dir


def validate_viewport(
    *,
    args: argparse.Namespace,
    viewport: dict[str, object],
    output_dir: Path,
    label: str,
    validate_roundtrip: bool,
) -> dict[str, object]:
    web_base = args.web_base.rstrip("/")
    skill_path = f"/projects/{args.project_id}/skill-forge?resources={args.resource}&tab={args.tab}"
    skill_url = f"{web_base}{skill_path}"
    cdp = None
    edge_process = None
    profile_dir = None
    screenshots: dict[str, str] = {}
    try:
        cdp, edge_process, profile_dir = new_cdp()
        cdp.send("Emulation.setDeviceMetricsOverride", viewport)
        cdp.send("Page.navigate", {"url": skill_url})
        wait_for(cdp, "document.readyState === 'complete' && document.body && document.body.innerText.includes('登录小A工作室')")
        login_url = str(cdp_eval(cdp, "location.href"))
        fill_field(cdp, 'input[name="email"]', args.login_email)
        fill_field(cdp, 'input[name="password"]', args.login_password)
        click_by_text(cdp, "进入项目空间", selector='button[type="submit"], button')
        wait_for(cdp, "!location.href.includes('/login') && document.body && document.body.innerText.includes('能力工坊')", timeout_seconds=45)
        wait_for(cdp, "document.body && document.body.innerText.includes('1号 NPC') && document.body.innerText.includes('最近索引')", timeout_seconds=20)
        after_login = read_page_state(cdp)
        shot = output_dir / f"{label}-after-login.png"
        screenshot(cdp, shot)
        screenshots["after_login"] = str(shot)

        company = None
        returned = None
        need_href = ""
        continue_href = ""
        if validate_roundtrip:
            need_href = click_first_link(cdp, "看需求验收详情")
            wait_for(cdp, "location.href.includes('/company') && document.body && document.body.innerText.includes('验收详情')", timeout_seconds=45)
            company = read_page_state(cdp)
            shot = output_dir / f"{label}-company.png"
            screenshot(cdp, shot)
            screenshots["company"] = str(shot)
            continue_href = click_first_link(cdp, "继续查看索引结果")
            wait_for(cdp, "location.href.includes('/skill-forge') && document.body && document.body.innerText.includes('最近索引')", timeout_seconds=45)
            returned = read_page_state(cdp)
            shot = output_dir / f"{label}-returned.png"
            screenshot(cdp, shot)
            screenshots["returned"] = str(shot)

        return {
            "label": label,
            "login_url": login_url,
            "skill_url": skill_url,
            "after_login": after_login,
            "need_href": need_href,
            "company": company,
            "continue_href": continue_href,
            "returned": returned,
            "screenshots": screenshots,
        }
    finally:
        if cdp is not None:
            try:
                cdp.close()
            except Exception:
                pass
        if edge_process is not None:
            try:
                edge_process.terminate()
                edge_process.wait(timeout=10)
            except Exception:
                edge_process.kill()
        if profile_dir is not None:
            shutil.rmtree(profile_dir, ignore_errors=True)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    desktop = validate_viewport(
        args=args,
        viewport={"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False},
        output_dir=output_dir,
        label="desktop",
        validate_roundtrip=True,
    )
    mobile = validate_viewport(
        args=args,
        viewport={"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True},
        output_dir=output_dir,
        label="mobile",
        validate_roundtrip=False,
    )

    expected_encoded = args.expected_stable_resource.replace(":", "%3A")
    states = [
        desktop["after_login"],
        desktop.get("company"),
        desktop.get("returned"),
        mobile["after_login"],
    ]
    state_dicts = [state for state in states if isinstance(state, dict)]
    pass_checks = bool(
        isinstance(desktop["after_login"], dict)
        and "/skill-forge" in str(desktop["after_login"].get("url", ""))
        and f"tab={args.tab}" in str(desktop["after_login"].get("url", ""))
        and desktop["after_login"].get("hasOpenedNpc")
        and desktop["after_login"].get("hasNeedAuditLink")
        and expected_encoded in str(desktop.get("need_href", ""))
        and isinstance(desktop.get("company"), dict)
        and desktop["company"].get("hasAcceptanceDetail")
        and expected_encoded in str(desktop["company"].get("url", ""))
        and expected_encoded in str(desktop.get("continue_href", ""))
        and isinstance(desktop.get("returned"), dict)
        and desktop["returned"].get("hasOpenedNpc")
        and expected_encoded in str(desktop["returned"].get("url", ""))
        and isinstance(mobile["after_login"], dict)
        and "/skill-forge" in str(mobile["after_login"].get("url", ""))
        and f"tab={args.tab}" in str(mobile["after_login"].get("url", ""))
        and mobile["after_login"].get("hasOpenedNpc")
        and all(not state.get("blank") for state in state_dicts)
        and all(not state.get("hasHorizontalOverflow") for state in state_dicts)
        and all(not state.get("forbiddenHits") for state in state_dicts)
        and all(not state.get("rawUuidHits") for state in state_dicts)
    )

    report = {
        "ok": pass_checks,
        "validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "web_base": args.web_base,
        "project_id": args.project_id,
        "resource": args.resource,
        "expected_stable_resource": args.expected_stable_resource,
        "desktop": desktop,
        "mobile": mobile,
    }
    report_path = output_dir / "skill-forge-login-return-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    screenshot_summary = {
        **{f"desktop_{key}": value for key, value in desktop["screenshots"].items()},
        **{f"mobile_{key}": value for key, value in mobile["screenshots"].items()},
    }
    print(json.dumps({"ok": pass_checks, "report": str(report_path), "screenshots": screenshot_summary}, ensure_ascii=False))
    return 0 if pass_checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
