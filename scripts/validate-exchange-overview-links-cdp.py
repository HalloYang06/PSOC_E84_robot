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
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)

SECTIONS = ["member-sync", "dispatch", "receipts", "thread-focus", "advanced-proof"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate every exchange overview second-level entry link.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=900)
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
        except Exception as exc:
            last = str(exc)
        time.sleep(interval_seconds)
    raise RuntimeError(f"Timed out waiting for expression: {expression[:220]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def login(cdp: object, *, web_base: str, project_id: str, email: str, password: str) -> object:
    cdp.send("Page.navigate", {"url": f"{web_base}/login?returnTo=/projects/{project_id}?panel=team%26tab=exchange"})
    wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('form')", timeout_seconds=35)
    result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const email = document.querySelector('input[name="email"], input[type="email"]');
          const password = document.querySelector('input[name="password"], input[type="password"]');
          if (!email || !password) return {{ ok: false, reason: 'missing-fields' }};
          email.value = {json.dumps(email)};
          email.dispatchEvent(new Event('input', {{ bubbles: true }}));
          email.dispatchEvent(new Event('change', {{ bubbles: true }}));
          password.value = {json.dumps(password)};
          password.dispatchEvent(new Event('input', {{ bubbles: true }}));
          password.dispatchEvent(new Event('change', {{ bubbles: true }}));
          const submit = document.querySelector('button[type="submit"], form button');
          if (!submit) return {{ ok: false, reason: 'missing-submit' }};
          submit.click();
          return {{ ok: true }};
        }})()
        """,
    )
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"Login form did not submit: {result}")
    wait_for(cdp, f"location.href.includes({json.dumps(f'/projects/{project_id}')})", timeout_seconds=45)
    wait_for(cdp, "!!document.querySelector('[data-exchange-overview-section-nav]')", timeout_seconds=45)
    time.sleep(1.0)
    return result


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-exchange-links-edge-"))
    edge_process = None
    cdp = None
    report: dict[str, object] = {
        "stamp": stamp,
        "project_id": args.project_id,
        "web_base": args.web_base,
        "sections": [],
        "screenshots": [],
        "verdict": "failed",
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
        page_target = next(
            (item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")),
            None,
        )
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

        web_base = args.web_base.rstrip("/")
        login_result = login(
            cdp,
            web_base=web_base,
            project_id=args.project_id,
            email=args.login_email,
            password=args.login_password,
        )
        report["login_result"] = login_result

        overview_info = cdp_eval(
            cdp,
            """
            (() => ({
              url: location.href,
              primer: !!document.querySelector('[data-exchange-overview-primer]'),
              navCount: document.querySelectorAll('[data-exchange-overview-nav]').length,
              cards: Array.from(document.querySelectorAll('[data-exchange-overview-card]')).map((item) => item.getAttribute('data-exchange-overview-card')),
            }))()
            """,
        )
        report["overview"] = overview_info
        overview_shot = output_dir / f"exchange-overview-links-00-overview-{stamp}.png"
        screenshot(cdp, overview_shot)
        report["screenshots"].append(str(overview_shot))

        if not isinstance(overview_info, dict) or overview_info.get("navCount") != len(SECTIONS) or not overview_info.get("primer"):
            raise RuntimeError(f"Exchange overview did not expose expected second-level nav: {overview_info}")

        for section in SECTIONS:
            cdp.send(
                "Page.navigate",
                {
                    "url": (
                        f"{web_base}/projects/{args.project_id}"
                        f"?panel=team&tab=exchange&exchange_section=overview"
                    )
                },
            )
            wait_for(cdp, "!!document.querySelector('[data-exchange-overview-section-nav]')", timeout_seconds=35)
            clicked = cdp_eval(
                cdp,
                f"""
                (() => {{
                  const link = document.querySelector(`[data-exchange-overview-nav="{section}"]`);
                  if (!link) return {{ ok: false, reason: 'missing-link' }};
                  link.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
                  link.click();
                  return {{ ok: true }};
                }})()
                """,
            )
            if not isinstance(clicked, dict) or not clicked.get("ok"):
                raise RuntimeError(f"Could not click exchange overview nav {section}: {clicked}")
            wait_for(
                cdp,
                f"""
                (() => {{
                  const section = document.querySelector(`[data-exchange-section="{section}"]`);
                  return location.href.includes('exchange_section={section}') &&
                    !!section &&
                    section.getAttribute('data-exchange-section-active') === 'true';
                }})()
                """,
                timeout_seconds=35,
            )
            time.sleep(0.8)
            state = cdp_eval(
                cdp,
                f"""
                (() => {{
                  const section = document.querySelector(`[data-exchange-section="{section}"]`);
                  return {{
                    id: {json.dumps(section)},
                    url: location.href,
                    active: !!section && section.getAttribute('data-exchange-section-active') === 'true',
                    detailButtons: section ? section.querySelectorAll('[data-exchange-open-detail]').length : 0,
                    text: section ? section.innerText.slice(0, 500) : ''
                  }};
                }})()
                """,
            )
            shot = output_dir / f"exchange-overview-links-{section}-{stamp}.png"
            screenshot(cdp, shot)
            report["screenshots"].append(str(shot))
            report["sections"].append(state)

        ok = all(isinstance(item, dict) and item.get("active") for item in report["sections"])
        report["verdict"] = "passed" if ok else "failed"
        report_path = output_dir / f"exchange-overview-links-report-{stamp}.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
