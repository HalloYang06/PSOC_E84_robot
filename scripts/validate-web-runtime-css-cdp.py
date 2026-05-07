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
import urllib.request
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that the running Web server serves the current project CSS chunks instead of stale empty CSS."
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=900)
    parser.add_argument("--min-largest-css-rules", type=int, default=100)
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


def fetch_css_health(hrefs: list[str]) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for href in hrefs:
        try:
            with urllib.request.urlopen(href, timeout=15) as response:
                body = response.read()
                checks.append(
                    {
                        "href": href,
                        "status": response.status,
                        "bytes": len(body),
                        "ok": response.status == 200 and len(body) > 0,
                    }
                )
        except Exception as exc:
            checks.append({"href": href, "status": "error", "bytes": 0, "ok": False, "error": str(exc)})
    return checks


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-css-health-edge-"))
    edge_process = None
    cdp = None
    report: dict[str, object] = {
        "stamp": stamp,
        "project_id": args.project_id,
        "web_base": args.web_base,
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
        project_url = f"{web_base}/projects/{args.project_id}"
        cdp.send("Page.navigate", {"url": f"{web_base}/login?returnTo=/projects/{args.project_id}"})
        wait_for(cdp, "document.readyState === 'complete' && !!document.querySelector('form')", timeout_seconds=35)
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
              const submit = document.querySelector('button[type="submit"], form button');
              if (!submit) return {{ ok: false, reason: 'missing-submit' }};
              submit.click();
              return {{ ok: true }};
            }})()
            """,
        )
        if not isinstance(login_result, dict) or not login_result.get("ok"):
            raise RuntimeError(f"Login form did not submit: {login_result}")

        wait_for(cdp, f"location.href.includes({json.dumps(f'/projects/{args.project_id}')})", timeout_seconds=45)
        wait_for(cdp, "!!document.querySelector('iframe')", timeout_seconds=45)
        time.sleep(6.0)

        runtime_info = cdp_eval(
            cdp,
            """
            (() => {
              const main = document.querySelector('main');
              const mainStyle = main ? getComputedStyle(main) : null;
              const styles = Array.from(document.styleSheets).map((sheet) => {
                let rules = -1;
                try { rules = sheet.cssRules.length; } catch {}
                return { href: sheet.href || 'inline', rules };
              });
              return {
                url: location.href,
                ready: document.readyState,
                title: document.title,
                mainClass: main ? main.className : '',
                mainPosition: mainStyle ? mainStyle.position : '',
                mainMinHeight: mainStyle ? mainStyle.minHeight : '',
                hasIframe: !!document.querySelector('iframe'),
                buttonCount: document.querySelectorAll('button').length,
                stylesheetHrefs: Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map((link) => link.href),
                styles,
              };
            })()
            """,
        )
        if not isinstance(runtime_info, dict):
            raise RuntimeError(f"Could not read runtime style info: {runtime_info}")

        css_checks = fetch_css_health([str(item) for item in runtime_info.get("stylesheetHrefs", []) if item])
        rule_counts = [int(item.get("rules", -1)) for item in runtime_info.get("styles", []) if isinstance(item, dict)]
        largest_rule_count = max(rule_counts or [-1])
        ok = (
            runtime_info.get("hasIframe") is True
            and runtime_info.get("mainPosition") == "relative"
            and largest_rule_count >= args.min_largest_css_rules
            and bool(css_checks)
            and all(bool(item.get("ok")) for item in css_checks)
        )

        shot = output_dir / f"web-runtime-css-health-{stamp}.png"
        screenshot(cdp, shot)
        report.update(
            {
                "verdict": "passed" if ok else "failed",
                "project_url": project_url,
                "login_result": login_result,
                "runtime_info": runtime_info,
                "largest_rule_count": largest_rule_count,
                "css_checks": css_checks,
                "screenshot": str(shot),
            }
        )
        report_path = output_dir / f"web-runtime-css-health-report-{stamp}.json"
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
