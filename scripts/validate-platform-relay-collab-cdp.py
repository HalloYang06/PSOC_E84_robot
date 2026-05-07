from __future__ import annotations

import base64
import importlib.util
import json
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
COLLAB_HELPER_PATH = SCRIPT_DIR / "validate-ui-frontdoor-collab-cdp.py"

WEB_BASE = "http://127.0.0.1:3000"
API_BASE = "http://127.0.0.1:8010"
MAIN_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
OWNER_EMAIL = "codex-platform-npc@local.dev"
OWNER_PASSWORD = "password"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collab = load_module("ui_frontdoor_collab_helper", COLLAB_HELPER_PATH)


def _text(value: object) -> str:
    return str(value or "").strip()


def request_json(path: str, *, token: str | None = None, timeout: int = 30) -> dict[str, object]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API_BASE.rstrip('/')}{path}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {path}: {detail}") from exc


def list_project_messages(token: str, project_id: str) -> list[dict[str, object]]:
    payload = request_json(f"/api/collaboration/messages?project_id={project_id}&limit=260", token=token)
    data = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def pick_completed_result(messages: list[dict[str, object]], *, title: str) -> dict[str, object] | None:
    for item in messages:
        if (
            _text(item.get("message_type")).lower() == "agent_result"
            and _text(item.get("title")) == title
            and _text(item.get("status")).lower() == "completed"
        ):
            return item
    return None


def wait_for_relay_results(token: str, *, first_title: str, second_title: str, timeout_seconds: int = 900) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_messages: list[dict[str, object]] = []
    while time.time() < deadline:
        last_messages = list_project_messages(token, MAIN_PROJECT_ID)
        first = pick_completed_result(last_messages, title=first_title)
        second = pick_completed_result(last_messages, title=second_title)
        if first and second:
            return {"first_result": first, "second_result": second, "message_count": len(last_messages)}
        time.sleep(3)
    recent = [
        {"type": item.get("message_type"), "title": item.get("title"), "status": item.get("status"), "sender": item.get("sender_id")}
        for item in last_messages[:16]
    ]
    raise TimeoutError(f"Timed out waiting for relay results: {first_title!r}, {second_title!r}; recent={recent}")


def screenshot_selector(flow, selector: str, output: Path, *, padding: int = 16) -> None:
    rect = flow.eval(
        f"""
        (() => {{
          const el = document.querySelector({collab.js_string(selector)});
          if (!el) return false;
          el.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
          const rect = el.getBoundingClientRect();
          const pad = {int(padding)};
          const x = Math.max(0, rect.left - pad);
          const y = Math.max(0, rect.top - pad);
          return {{
            x,
            y,
            width: Math.max(1, Math.min(window.innerWidth - x, rect.width + pad * 2)),
            height: Math.max(1, Math.min(window.innerHeight - y, rect.height + pad * 2)),
          }};
        }})()
        """
    )
    if not isinstance(rect, dict):
        raise RuntimeError(f"Could not locate screenshot selector: {selector}")
    shot = flow.cdp.send(
        "Page.captureScreenshot",
        {
            "format": "png",
            "clip": {
                "x": float(rect["x"]),
                "y": float(rect["y"]),
                "width": float(rect["width"]),
                "height": float(rect["height"]),
                "scale": 1,
            },
        },
    )
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError(f"CDP returned empty selector screenshot for {selector}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base64.b64decode(data))


def choose_relay_targets(flow) -> dict[str, object]:
    state = flow.wait_for(
        """
        (() => {
          const form = document.querySelector('[data-exchange-relay-form]');
          if (!form) return false;
          const first = form.querySelector('select[name="first_recipient_id"]');
          const second = form.querySelector('select[name="second_recipient_id"]');
          if (!first || !second) return false;
          const options = Array.from(first.options).map((option) => ({
            value: option.value || '',
            text: option.textContent || '',
          })).filter((item) => item.value);
          const codex = options.find((item) => /codex/i.test(item.text + ' ' + item.value)) || options[0] || null;
          const claude = options.find((item) =>
            item.value !== (codex && codex.value) && /claude/i.test(item.text + ' ' + item.value)
          ) || options.find((item) => item.value !== (codex && codex.value)) || codex;
          return codex && claude ? { first: codex, second: claude, options } : false;
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.4,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Could not resolve relay targets from UI: {state}")
    return state


def submit_relay_via_ui(flow, *, first_id: str, second_id: str, title: str, objective: str) -> dict[str, object]:
    flow.set_select('[data-exchange-relay-form] select[name="first_recipient_id"]', first_id)
    flow.set_select('[data-exchange-relay-form] select[name="second_recipient_id"]', second_id)
    flow.fill('[data-exchange-relay-form] input[name="title"]', title)
    flow.fill('[data-exchange-relay-form] textarea[name="objective"]', objective)
    collab.click_via_expression(
        flow,
        """
        (() => {
          const button = document.querySelector('[data-exchange-relay-form] button[type="submit"]');
          if (!button || button.disabled) return false;
          button.scrollIntoView({ block: 'center', inline: 'center' });
          const rect = button.getBoundingClientRect();
          if (!rect.width || !rect.height) return false;
          return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        })()
        """,
        timeout_seconds=30,
        interval_seconds=0.3,
        label="relay submit button",
    )
    try:
        state = flow.wait_for(
            """
            (() => {
              const success = document.querySelector('[class*="successBanner"]')?.textContent || '';
              const error = document.querySelector('[class*="errorBanner"]')?.textContent || '';
              if (success.includes('接力') || success.toLowerCase().includes('relay')) {
                return { href: location.href, success, error, body: document.body ? document.body.innerText.slice(0, 5000) : '' };
              }
              if (error) {
                return { href: location.href, success, error, body: document.body ? document.body.innerText.slice(0, 5000) : '' };
              }
              if (location.href.includes('exchange_section=receipts') || document.querySelector('[data-exchange-section="receipts"]')) {
                return { href: location.href, success: 'submitted-without-banner', error, body: document.body ? document.body.innerText.slice(0, 5000) : '' };
              }
              return false;
            })()
            """,
            timeout_seconds=20,
            interval_seconds=0.4,
        )
    except Exception:
        state = flow.eval(
            """
            (() => ({
              href: location.href,
              success: 'submitted-without-banner',
              error: document.querySelector('[class*="errorBanner"]')?.textContent || '',
              body: document.body ? document.body.innerText.slice(0, 5000) : ''
            }))()
            """
        )
    if not isinstance(state, dict) or _text(state.get("error")):
        raise RuntimeError(f"Relay submit surfaced an error: {state}")
    return state


def verify_relay_rounds_visible(flow, *, first_title: str, second_title: str, shot: Path) -> dict[str, object]:
    flow.navigate(f"{WEB_BASE}/projects/{MAIN_PROJECT_ID}?panel=team&tab=exchange&exchange_section=receipts")
    flow.wait_for_selector('[data-exchange-section="receipts"]', timeout_seconds=45)
    state = flow.wait_for(
        f"""
        (() => {{
          const rounds = Array.from(document.querySelectorAll('[data-exchange-receipt-round]')).map((item) => ({{
            title: item.getAttribute('data-exchange-receipt-round') || '',
            status: item.getAttribute('data-exchange-receipt-round-status') || '',
            text: (item.textContent || '').trim(),
          }}));
          const wanted = [{collab.js_string(first_title)}, {collab.js_string(second_title)}];
          const present = wanted.map((title) => rounds.find((item) =>
            item.title === title &&
            (item.status === 'completed' || item.status.includes('\\u5df2') || item.text.includes('completed'))
          ));
          return present.every(Boolean) ? {{ rounds, href: location.href, body: document.body ? document.body.innerText.slice(0, 6000) : '' }} : false;
        }})()
        """,
        timeout_seconds=60,
        interval_seconds=0.5,
    )
    flow.screenshot(shot)
    if not isinstance(state, dict):
        raise RuntimeError("Relay receipt rounds were not visible as completed in the UI.")
    return state


def verify_relay_status_visible(flow, *, relay_title: str, shot: Path) -> dict[str, object]:
    flow.navigate(f"{WEB_BASE}/projects/{MAIN_PROJECT_ID}?panel=team&tab=exchange")
    flow.wait_for_selector('[data-exchange-section="overview"]', timeout_seconds=45)
    state = flow.wait_for(
        f"""
        (() => {{
          const cards = Array.from(document.querySelectorAll('[data-exchange-relay-status-card]')).map((item) => ({{
            status: item.getAttribute('data-exchange-relay-status-card') || '',
            text: (item.textContent || '').trim(),
          }}));
          const matched = cards.find((item) =>
            item.text.includes({collab.js_string(relay_title)}) &&
            (item.status === 'completed' || item.text.includes('\\u5df2\\u5b8c\\u6210')) &&
            item.text.includes('\\u7b2c\\u4e00\\u68d2') &&
            item.text.includes('\\u7b2c\\u4e8c\\u68d2') &&
            item.text.includes('\\u4e0b\\u4e00\\u6b65')
          );
          return matched ? {{ cards, href: location.href, body: document.body ? document.body.innerText.slice(0, 5000) : '' }} : false;
        }})()
        """,
        timeout_seconds=60,
        interval_seconds=0.5,
    )
    if not isinstance(state, dict):
        raise RuntimeError("Relay status card was not visible as completed in the overview UI.")
    screenshot_selector(flow, '[data-exchange-relay-status-list="true"]', shot)
    return state


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_stamp = stamp[-6:]
    output_dir = REPO_ROOT / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix="platform-relay-collab-", dir=str(output_dir)))
    report: dict[str, object] = {"stamp": stamp, "project_id": MAIN_PROJECT_ID, "screenshots": {}, "steps": {}}
    owner_token, owner_user = collab.api_login(API_BASE, OWNER_EMAIL, OWNER_PASSWORD)
    report["steps"]["owner_user"] = owner_user

    profile_dir = collab.new_browser_profile(runtime_dir, "owner")
    try:
        with collab.BrowserRuntime(collab.find_free_port(), profile_dir, 1720, 1080) as flow:
            login_shot = output_dir / f"platform-relay-collab-01-login-{stamp}.png"
            collab.login_via_ui(flow, WEB_BASE, email=OWNER_EMAIL, password=OWNER_PASSWORD, shot=login_shot)
            report["screenshots"]["login"] = str(login_shot)

            flow.navigate(f"{WEB_BASE}/projects/{MAIN_PROJECT_ID}?panel=team&tab=exchange&exchange_composer=relay")
            flow.wait_for_selector('[data-exchange-relay-form]', timeout_seconds=45)
            targets = choose_relay_targets(flow)
            report["steps"]["targets"] = targets
            flow.eval(
                """
                (() => {
                  document.querySelector('[data-exchange-relay-form]')?.scrollIntoView({
                    block: 'center',
                    inline: 'nearest',
                    behavior: 'instant',
                  });
                  return true;
                })()
                """
            )
            time.sleep(0.4)
            form_shot = output_dir / f"platform-relay-collab-02-form-{stamp}.png"
            flow.screenshot(form_shot)
            report["screenshots"]["form"] = str(form_shot)

            relay_title = f"平台接力协作验收-{short_stamp}"
            first_title = f"{relay_title} / 第一棒资料拆解"
            second_title = f"{relay_title} / 第二棒最终交付"
            objective = (
                "用平台多 NPC 接力协作写一段给新用户看的说明：为什么 AI 合作平台要区分 NPC、电脑和线程。"
                f"第一棒收集结构，第二棒完成说明。最终第二棒回复必须包含：平台接力第二棒完成 {short_stamp}。"
            )
            submit_state = submit_relay_via_ui(
                flow,
                first_id=_text(targets["first"]["value"]),
                second_id=_text(targets["second"]["value"]),
                title=relay_title,
                objective=objective,
            )
            report["steps"]["submit"] = submit_state
            submit_shot = output_dir / f"platform-relay-collab-03-submitted-{stamp}.png"
            flow.screenshot(submit_shot)
            report["screenshots"]["submitted"] = str(submit_shot)

            report["steps"]["results"] = wait_for_relay_results(
                owner_token,
                first_title=first_title,
                second_title=second_title,
                timeout_seconds=900,
            )
            receipts_shot = output_dir / f"platform-relay-collab-04-receipts-{stamp}.png"
            report["steps"]["receipts_visible"] = verify_relay_rounds_visible(
                flow,
                first_title=first_title,
                second_title=second_title,
                shot=receipts_shot,
            )
            report["screenshots"]["receipts"] = str(receipts_shot)
            status_shot = output_dir / f"platform-relay-collab-05-status-{stamp}.png"
            report["steps"]["status_visible"] = verify_relay_status_visible(flow, relay_title=relay_title, shot=status_shot)
            report["screenshots"]["status"] = str(status_shot)

        report["verdict"] = "passed"
        report_path = output_dir / f"platform-relay-collab-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"verdict": "passed", "report_path": str(report_path), "screenshots": report["screenshots"]}, ensure_ascii=False, indent=2))
        return 0
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
