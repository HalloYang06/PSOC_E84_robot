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
from urllib.parse import quote, urlparse

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
    parser = argparse.ArgumentParser(description="Validate the live main-project machine-room health chips without mutating project data.")
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
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError

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


def read_agent_commands(api_base: str, project_id: str, token: str) -> list[dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/collaboration/messages?project_id={quote(project_id)}&message_type=agent_command",
        token=token,
    )
    data = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


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
    machine_room_path = f"/projects/{args.project_id}?panel=team&tab=machine-room"
    login_url = f"{args.web_base.rstrip('/')}/login?returnTo={quote(machine_room_path, safe='')}"
    token, user = api_login(args.api_base, args.login_email, args.login_password)
    agent_commands_before = read_agent_commands(args.api_base, args.project_id, token)

    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-machine-room-health-cdp-"))
    edge_process = None
    cdp = None
    screenshots: list[str] = []
    report_path = output_dir / f"machine-room-health-main-project-report-{stamp}.json"

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
        shot = output_dir / f"machine-room-health-main-01-login-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))
        login_result = cdp_eval(
            cdp,
            f"""
            (() => {{
              const email = document.querySelector('input[name="email"], input[type="email"]');
              const password = document.querySelector('input[name="password"], input[type="password"]');
              if (!email || !password) return {{ ok: false, reason: 'missing-fields' }};
              const setValue = (input, value) => {{
                const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value');
                if (descriptor && descriptor.set) descriptor.set.call(input, value);
                else input.value = value;
                input.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: value }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
              }};
              setValue(email, {json.dumps(args.login_email)});
              setValue(password, {json.dumps(args.login_password)});
              const form = email.closest('form') || password.closest('form') || document.querySelector('form');
              const submit = form?.querySelector('button[type="submit"]') || document.querySelector('button[type="submit"]');
              if (!form || !submit) return {{ ok: false, reason: 'missing-submit' }};
              form.requestSubmit(submit);
              return {{ ok: true }};
            }})()
            """,
        )
        if not isinstance(login_result, dict) or not login_result.get("ok"):
            raise RuntimeError(f"Login form did not submit: {login_result}")
        wait_for(cdp, f"location.href.includes({json.dumps(machine_room_path)})", timeout_seconds=60)
        wait_for(
            cdp,
            """
            (() => {
              const body = document.body?.innerText || '';
              return document.readyState === 'complete'
                && body.includes('云端验收项目')
                && (body.includes('线程调试') || body.includes('AI 线程') || body.includes('6 个 · 在线电脑 1/1'));
            })()
            """,
            timeout_seconds=60,
        )
        wait_for(
            cdp,
            "(() => { const panel = document.querySelector('#project-main-panel'); return !!panel && panel.getAttribute('data-busy') !== 'true'; })()",
            timeout_seconds=60,
        )

        state = cdp_eval(
            cdp,
            """
            (() => {
              const cards = Array.from(document.querySelectorAll('[data-machine-thread-card]'));
              const attentionCards = Array.from(document.querySelectorAll('[data-machine-thread-attention-card]'));
              const attentionSummary = Array.from(document.querySelectorAll('[data-machine-room-attention-summary]')).map((card) => (card.innerText || card.textContent || '').trim());
              const firstHealthy = cards.find((card) => {
                const hasAck = !!card.querySelector('[data-machine-thread-last-ack]');
                const hasResult = !!card.querySelector('[data-machine-thread-last-result]');
                return hasAck || hasResult;
              }) || null;
              const firstCommand = cards.find((card) => !!card.querySelector('[data-machine-thread-last-command]')) || null;
              const firstStale = cards.find((card) => {
                const freshness = card.querySelector('[data-machine-thread-freshness][data-stale="true"]');
                return !!freshness;
              }) || null;
              const firstAttention = attentionCards[0] || null;
              const focusCard = firstCommand || firstHealthy || firstStale || cards[0] || null;
              if (focusCard) focusCard.scrollIntoView({ block: 'center', inline: 'center' });
              return {
                bodyText: (document.body?.innerText || '').slice(0, 5000),
                cardCount: cards.length,
                healthCardCount: cards.filter((card) => !!card.querySelector('[data-machine-thread-last-ack]') || !!card.querySelector('[data-machine-thread-last-result]')).length,
                commandCardCount: cards.filter((card) => !!card.querySelector('[data-machine-thread-last-command]')).length,
                staleCardCount: cards.filter((card) => !!card.querySelector('[data-machine-thread-freshness][data-stale=\"true\"]')).length,
                attentionCardCount: attentionCards.length,
                attentionSummary,
                firstHealthyText: firstHealthy ? (firstHealthy.innerText || firstHealthy.textContent || '').slice(0, 2500) : '',
                firstHealthyAck: firstHealthy?.querySelector('[data-machine-thread-last-ack]')?.textContent || '',
                firstHealthyResult: firstHealthy?.querySelector('[data-machine-thread-last-result]')?.textContent || '',
                firstHealthyHasInlineRecovery: !!firstHealthy?.querySelector('[data-machine-thread-recovery-preview-form]'),
                firstCommandThreadId: firstCommand?.getAttribute('data-machine-thread-card') || '',
                firstCommandText: firstCommand ? (firstCommand.innerText || firstCommand.textContent || '').slice(0, 2500) : '',
                firstCommandChip: firstCommand?.querySelector('[data-machine-thread-last-command]')?.textContent || '',
                firstStaleText: firstStale ? (firstStale.innerText || firstStale.textContent || '').slice(0, 2500) : '',
                firstStaleFreshness: firstStale?.querySelector('[data-machine-thread-freshness]')?.textContent || '',
                firstAttentionThreadId: firstAttention?.getAttribute('data-machine-thread-attention-card') || '',
                firstAttentionText: firstAttention ? (firstAttention.innerText || firstAttention.textContent || '').slice(0, 2500) : '',
                firstAttentionLabel: firstAttention?.querySelector('[data-machine-thread-recovery-label]')?.textContent || '',
                firstAttentionNext: firstAttention?.querySelector('[data-machine-thread-recovery-next]')?.textContent || '',
                firstAttentionHasTokenAction: !!firstAttention?.querySelector('[data-machine-thread-recovery-token] button'),
              };
            })()
            """,
        )
        if not isinstance(state, dict):
            raise RuntimeError(f"Unexpected machine-room health state: {state!r}")
        body_text = str(state.get("bodyText") or "")
        if int(state.get("cardCount") or 0) <= 0 and "AI 线程" not in body_text:
            raise RuntimeError(f"Main project machine-room has no visible thread evidence: {state}")
        if "6 个" not in body_text and "线程" not in body_text:
            raise RuntimeError(f"Main project machine-room summary is missing thread status: {state}")

        shot = output_dir / f"machine-room-health-main-02-machine-room-{stamp}.png"
        screenshot(cdp, shot)
        screenshots.append(str(shot))

        first_attention_thread_id = str(state.get("firstAttentionThreadId") or "").strip()
        preview_state = None
        agent_commands_after_preview = None
        if first_attention_thread_id:
            preview_click = cdp_eval(
                cdp,
                f"""
                (() => {{
                  const form = document.querySelector('[data-machine-thread-recovery-preview-form="{first_attention_thread_id}"]');
                  if (!form) return {{ ok: false, reason: 'missing-form' }};
                  const button = Array.from(form.querySelectorAll('button')).find((item) =>
                    ((item.innerText || item.textContent || '').replace(/\\s+/g, ' ').includes('先预演最小检查'))
                  ) || null;
                  if (!button) return {{ ok: false, reason: 'missing-preview-button' }};
                  if ('disabled' in button && button.disabled) {{
                    return {{ ok: false, reason: 'disabled', text: (button.innerText || button.textContent || '').trim() }};
                  }}
                  button.scrollIntoView({{ block: 'center', inline: 'center' }});
                  button.click();
                  return {{ ok: true, text: (button.innerText || button.textContent || '').trim() }};
                }})()
                """,
            )
            if not isinstance(preview_click, dict) or not preview_click.get("ok"):
                raise RuntimeError(f"Could not click machine-room recovery preview button: {preview_click}")
            wait_for(
                cdp,
                f"""
                (() => {{
                  const root = document.querySelector('[data-machine-thread-recovery-preview-card="{first_attention_thread_id}"]');
                  if (!root) return false;
                  return (root.innerText || root.textContent || '').includes('最近一次机房最小检查预演');
                }})()
                """,
                timeout_seconds=45,
            )
            preview_state = cdp_eval(
                cdp,
                f"""
                (() => {{
                  const root = document.querySelector('[data-machine-thread-recovery-preview-card="{first_attention_thread_id}"]');
                  if (!root) return null;
                  const text = (root.innerText || root.textContent || '').slice(0, 2500);
                  const previewButton = document.querySelector('[data-machine-thread-recovery-preview-form="{first_attention_thread_id}"] button[formaction]');
                  const submitButtons = Array.from(document.querySelectorAll('[data-machine-thread-recovery-preview-form="{first_attention_thread_id}"] button'));
                  const formalButton = submitButtons.find((item) => !(item.getAttribute('formaction') || '').trim()) || null;
                  return {{
                    visible: text.includes('最近一次机房最小检查预演'),
                    text,
                    formalButtonDisabled: !!formalButton && !!formalButton.disabled,
                  }};
                }})()
                """,
            )
            shot = output_dir / f"machine-room-health-main-04-recovery-preview-{stamp}.png"
            screenshot(cdp, shot)
            screenshots.append(str(shot))
            agent_commands_after_preview = read_agent_commands(args.api_base, args.project_id, token)
            if len(agent_commands_after_preview) != len(agent_commands_before):
                raise RuntimeError(
                    f"Machine-room recovery preview mutated agent_command count: before={len(agent_commands_before)} after={len(agent_commands_after_preview)}"
                )
            if not isinstance(preview_state, dict) or not preview_state.get("visible"):
                raise RuntimeError(f"Machine-room recovery preview did not become visible: {preview_state}")

        first_command_thread_id = str(state.get("firstCommandThreadId") or "").strip()
        exchange_state = None
        if first_command_thread_id:
            exchange_path = f"/projects/{args.project_id}?panel=team&tab=exchange&exchange_section=dispatch"
            cdp.send("Page.navigate", {"url": f"{args.web_base.rstrip('/')}{exchange_path}"})
            wait_for(
                cdp,
                "document.readyState === 'complete' && !!document.querySelector('[data-exchange-nav-target=\"thread-focus\"]')",
                timeout_seconds=60,
            )
            wait_for(
                cdp,
                "(() => { const panel = document.querySelector('#project-main-panel'); return !!panel && panel.getAttribute('data-busy') !== 'true'; })()",
                timeout_seconds=60,
            )
            wait_for(
                cdp,
                "(() => { const nav = document.querySelector('[data-exchange-nav-target=\"dispatch\"]'); return !!nav && nav.getAttribute('data-exchange-nav-active') === 'true'; })()",
                timeout_seconds=30,
            )
            exchange_state = cdp_eval(
                cdp,
                f"""
                (() => {{
                  const target = {json.dumps(first_command_thread_id)};
                  const normalizedTarget = target.toLowerCase();
                  const cards = Array.from(document.querySelectorAll('[data-exchange-dispatch-target]'));
                  const match = cards.find((card) => {{
                    const direct = (card.getAttribute('data-exchange-dispatch-target') || '').toLowerCase();
                    const aliases = (card.getAttribute('data-exchange-dispatch-aliases') || '')
                      .split('|')
                      .map((item) => item.trim().toLowerCase())
                      .filter(Boolean);
                    return direct === normalizedTarget || aliases.includes(normalizedTarget);
                  }}) || null;
                  if (match) match.scrollIntoView({{ block: 'center', inline: 'center' }});
                  return {{
                    dispatchCardCount: cards.length,
                    matchedThreadId: target,
                    matchedDispatchVisible: !!match,
                    matchedDispatchText: match ? (match.innerText || match.textContent || '').slice(0, 2500) : '',
                    matchedDispatchAliases: match ? (match.getAttribute('data-exchange-dispatch-aliases') || '') : '',
                  }};
                }})()
                """,
            )
            if not isinstance(exchange_state, dict):
                raise RuntimeError(f"Unexpected exchange state: {exchange_state!r}")
            if int(exchange_state.get("dispatchCardCount") or 0) <= 0:
                raise RuntimeError(f"Exchange panel has no visible dispatch cards: {exchange_state}")
            if not bool(exchange_state.get("matchedDispatchVisible")):
                raise RuntimeError(
                    f"Exchange panel did not reconcile dispatch card for thread {first_command_thread_id}: {exchange_state}"
                )
            exchange_shot = output_dir / f"machine-room-health-main-03-exchange-{stamp}.png"
            screenshot(cdp, exchange_shot)
            screenshots.append(str(exchange_shot))

        report = {
            "validated_at": stamp,
            "project_id": args.project_id,
            "user": user,
            "agent_command_count_before_preview": len(agent_commands_before),
            "agent_command_count_after_preview": len(agent_commands_after_preview or agent_commands_before),
            "machine_room": state,
            "recovery_preview": preview_state,
            "exchange": exchange_state,
            "screenshots": screenshots,
            "mode": "read_only_main_project_live_validation",
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "report": str(report_path), "machine_room": state}, ensure_ascii=False))
        return 0
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
                try:
                    edge_process.kill()
                except Exception:
                    pass
        try:
            import shutil
            shutil.rmtree(profile_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
