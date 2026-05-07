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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate in-project panel navigation from a real login session.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--viewport-width", type=int, default=1900)
    parser.add_argument("--viewport-height", type=int, default=1100)
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


def screenshot_with_min_size(cdp: object, output: Path, *, min_bytes: int = 90_000, attempts: int = 6) -> None:
    last_size = 0
    for attempt in range(1, attempts + 1):
        screenshot(cdp, output)
        last_size = output.stat().st_size
        if last_size >= min_bytes:
            return
        time.sleep(2.0 if attempt < 3 else 3.0)
    raise RuntimeError(f"Screenshot stayed too small after {attempts} attempts: {output} size={last_size}")


def wait_for_project_map_visual(cdp: object, *, timeout_seconds: float = 30) -> None:
    """Wait for the game shell/HUD to settle before the first map screenshot.

    The game view is allowed to be canvas, DOM layers, or mixed assets. The
    important validation rule is user-visible: wait until the game HUD exists,
    then use screenshot-size retry to avoid a mostly black pre-paint capture.
    """
    wait_for(
        cdp,
        """
        (() => {
          const text = document.body ? document.body.innerText : '';
          const hasGameHud = text.includes('项目列表') && (
            text.includes('显示协作焦点') ||
            text.includes('NPC 管理') ||
            text.includes('电脑接入管理')
          );
          const viewportReady = document.documentElement.clientWidth > 1000 && document.documentElement.clientHeight > 700;
          return hasGameHud && viewportReady;
        })()
        """,
        timeout_seconds=timeout_seconds,
    )
    # Give large tile assets and CSS backgrounds time to paint in headless Edge.
    time.sleep(6.0)


def click_text_button(cdp: object, label: str) -> None:
    ok = cdp_eval(
        cdp,
        f"""
        (() => {{
          const wanted = {json.dumps(label)};
          const buttons = Array.from(document.querySelectorAll('button, a'));
          const node = buttons.find((item) => (item.innerText || item.textContent || '').includes(wanted));
          if (!node) return false;
          node.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
          node.click();
          return true;
        }})()
        """,
    )
    if not ok:
        raise RuntimeError(f"Could not click button/link with text {label!r}")
    time.sleep(1.2)


def click_selector(cdp: object, selector: str) -> None:
    ok = cdp_eval(
        cdp,
        f"""
        (() => {{
          const node = document.querySelector({json.dumps(selector)});
          if (!node) return false;
          node.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
          node.click();
          return true;
        }})()
        """,
    )
    if not ok:
        raise RuntimeError(f"Could not click selector {selector!r}")
    time.sleep(1.0)


def close_panel_if_open(cdp: object) -> None:
    close_visible = cdp_eval(cdp, "!!document.querySelector('#project-main-panel .project-playable-shell_closeButton__MDVQP, #project-main-panel button[aria-label*=关闭], #project-main-panel button')")
    if close_visible:
        # Prefer the explicit close button in the panel head.
        ok = cdp_eval(
            cdp,
            """
            (() => {
              const panel = document.querySelector('#project-main-panel');
              if (!panel) return false;
              const buttons = Array.from(panel.querySelectorAll('button'));
              const close = buttons.find((item) => (item.innerText || item.textContent || '').trim() === '×' || (item.getAttribute('aria-label') || '').includes('关闭'));
              if (!close) return false;
              close.click();
              return true;
            })()
            """,
        )
        if ok:
            time.sleep(1.0)


def session_navigate(cdp: object, url: str, marker: str) -> None:
    cdp.send("Page.navigate", {"url": url})
    wait_for(cdp, f"location.href.includes({json.dumps(url.split('http://127.0.0.1:3000', 1)[-1])})", timeout_seconds=25)
    wait_for(cdp, f"document.body && document.body.innerText.includes({json.dumps(marker)})", timeout_seconds=25)
    time.sleep(1.0)


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-panel-nav-edge-"))
    edge_process = None
    cdp = None
    screenshots: list[str] = []
    results: dict[str, object] = {"stamp": stamp, "project_id": args.project_id, "screenshots": screenshots, "steps": []}

    def add_step(name: str, status: str, note: str = "") -> None:
        results["steps"].append({"name": name, "status": status, "note": note})

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
        cdp.send("Emulation.setDeviceMetricsOverride", {"width": args.viewport_width, "height": args.viewport_height, "deviceScaleFactor": 1, "mobile": False})

        cdp.send("Page.navigate", {"url": f"{args.web_base.rstrip('/')}/login?returnTo=/projects/{args.project_id}"})
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
        wait_for(cdp, f"location.href.includes({json.dumps(args.project_id)})", timeout_seconds=45)
        wait_for(
            cdp,
            "document.body && (document.body.innerText.includes('项目主角') || document.body.innerText.includes('显示协作焦点') || document.body.innerText.includes('开发工坊'))",
            timeout_seconds=45,
        )
        wait_for_project_map_visual(cdp)
        shot = output_dir / f"panel-nav-01-project-map-{stamp}.png"
        screenshot_with_min_size(cdp, shot)
        screenshots.append(str(shot))
        add_step("project-map", "ok")

        panels = [
            ("主角协作管理", "主角协作管理", "panel-nav-02-human-party"),
            ("开发工坊", "开发工坊", "panel-nav-03-workshop"),
            ("NPC 管理", "NPC 管理", "panel-nav-04-npc"),
            ("电脑接入管理", "电脑接入管理", "panel-nav-05-computers"),
            ("Skill 管理仓库", "Skill 管理仓库", "panel-nav-06-skills"),
        ]
        for label, marker, slug in panels:
            try:
                click_text_button(cdp, label)
                wait_for(
                    cdp,
                    f"(() => {{ const panel = document.querySelector('#project-main-panel'); const heading = panel && panel.querySelector('h2'); return !!(panel && heading && (heading.textContent || '').includes({json.dumps(marker)})); }})()",
                    timeout_seconds=25,
                )
                shot = output_dir / f"{slug}-{stamp}.png"
                screenshot(cdp, shot)
                screenshots.append(str(shot))
                add_step(slug, "ok")
            except Exception as exc:
                add_step(slug, "failed", str(exc))
            finally:
                close_panel_if_open(cdp)

        # NPC profile from inside NPC manager.
        try:
            click_text_button(cdp, "NPC 管理")
            wait_for(cdp, "document.body && document.body.innerText.includes('NPC 管理')", timeout_seconds=20)
            click_selector(cdp, '[data-npc-open-profile="1"]')
            wait_for(cdp, "document.body && document.body.innerText.includes('属性 / 知识库')", timeout_seconds=20)
            shot = output_dir / f"panel-nav-08-npc-profile-{stamp}.png"
            screenshot(cdp, shot)
            screenshots.append(str(shot))
            add_step("npc-profile", "ok")
        except Exception as exc:
            add_step("npc-profile", "failed", str(exc))
        finally:
            close_panel_if_open(cdp)
            close_panel_if_open(cdp)

        # Skill detail from inside skills manager.
        try:
            click_text_button(cdp, "Skill 管理仓库")
            wait_for(cdp, "document.body && document.body.innerText.includes('Skill 管理仓库')", timeout_seconds=20)
            click_selector(cdp, '[data-skill-open-detail="1"]')
            wait_for(cdp, "document.body && document.body.innerText.includes('Skill 详情')", timeout_seconds=20)
            shot = output_dir / f"panel-nav-09-skill-detail-{stamp}.png"
            screenshot(cdp, shot)
            screenshots.append(str(shot))
            add_step("skill-detail", "ok")
        except Exception as exc:
            add_step("skill-detail", "failed", str(exc))
        finally:
            close_panel_if_open(cdp)
            close_panel_if_open(cdp)

        routed_panels = [
            ("schedule-route", f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=schedule", "日程日历", "panel-nav-10-schedule"),
            ("serial-tv-route", f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=serial-tv", "串口电视", "panel-nav-11-serial-tv"),
            ("machine-room-route", f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=machine-room", "线程调试", "panel-nav-12-machine-room"),
            ("exchange-route", f"{args.web_base.rstrip('/')}/projects/{args.project_id}?panel=team&tab=exchange", "协作消息池", "panel-nav-13-exchange"),
        ]
        for step_name, url, marker, slug in routed_panels:
            try:
                session_navigate(cdp, url, marker)
                if slug == "panel-nav-13-exchange":
                    folded_state = cdp_eval(
                        cdp,
                        """
                        (() => {
                          const primer = document.querySelector('[data-exchange-overview-primer="true"]');
                          const contract = document.querySelector('[data-ai-collab-contract="true"]');
                          return {
                            primerClosed: !!primer && !primer.open,
                            contractClosed: !!contract && !contract.open,
                          };
                        })()
                        """,
                    )
                    if not isinstance(folded_state, dict) or not folded_state.get("primerClosed") or not folded_state.get("contractClosed"):
                        raise RuntimeError(f"Exchange help folds are not collapsed by default: {folded_state}")
                shot = output_dir / f"{slug}-{stamp}.png"
                screenshot(cdp, shot)
                screenshots.append(str(shot))
                add_step(step_name, "ok")
            except Exception as exc:
                add_step(step_name, "failed", str(exc))

        report = output_dir / f"panel-nav-validation-report-{stamp}.json"
        report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    finally:
        if cdp is not None:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
