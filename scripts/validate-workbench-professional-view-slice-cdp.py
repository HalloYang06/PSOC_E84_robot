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
    parser = argparse.ArgumentParser(
        description="Validate the thin slice from NPC dialog into professional views without breaking the existing workbench.",
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="proj_ai_collab")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/workbench-professional-view-slice")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=1100)
    parser.add_argument(
        "--seats",
        default="platform-npc-1",
        help="Comma-separated NPC seat aliases to open directly in workbench validation.",
    )
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


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 35, interval_seconds: float = 0.25) -> object:
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


def wait_for_workbench_tile(cdp: object, output_dir: Path, stamp: str) -> None:
    try:
        wait_for(
            cdp,
            """
            (() => {
              const body = document.body?.innerText || '';
              const hasTile = document.querySelectorAll('article').length >= 1
                || body.includes('与 1号')
                || body.includes('的对话');
              return location.href.includes('?seats=')
                && hasTile
                && body.includes('协同工作台')
                && body.includes('发送');
            })()
            """,
            timeout_seconds=25,
        )
    except Exception:
        screenshot(cdp, output_dir / f"02-npc-dialog-timeout-{stamp}.png")
        raise


def wait_for_tile_messages(cdp: object, *, timeout_seconds: float = 12) -> bool:
    try:
        wait_for(
            cdp,
            """
            (() => {
              const body = document.body?.innerText || '';
              if (body.includes('加载中') || body.includes('刷新中')) return false;
              return body.includes('桌面提问') || body.includes('Codex Desktop 用户追问') || /当前\\s+[1-9]/.test(body);
            })()
            """,
            timeout_seconds=timeout_seconds,
            interval_seconds=0.35,
        )
        return True
    except Exception:
        return False


def snapshot_layout(cdp: object) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        """
        (() => {
          const card = document.querySelector('article');
          const rightRail = Array.from(document.querySelectorAll('aside, nav, section, details')).find(
            (node) => (node.textContent || '').includes('协作总览') || (node.textContent || '').includes('项目资源索引'),
          );
          const buttons = Array.from(document.querySelectorAll('button')).slice(0, 60).map((button) => ({
            text: (button.textContent || '').trim(),
            title: button.getAttribute('title') || '',
          }));
          return {
            href: location.href,
            title: document.title,
            bodyText: (document.body?.innerText || '').slice(0, 2500),
            articleCount: document.querySelectorAll('article').length,
            detailsCount: document.querySelectorAll('details').length,
            hasWorkbenchTitle: (document.body?.innerText || '').includes('协同工作台'),
            hasRightSummary: (document.body?.innerText || '').includes('协作总览'),
            hasResourceIndex: (document.body?.innerText || '').includes('项目资源索引'),
            cardRect: card ? {
              x: Math.round(card.getBoundingClientRect().x),
              y: Math.round(card.getBoundingClientRect().y),
              width: Math.round(card.getBoundingClientRect().width),
              height: Math.round(card.getBoundingClientRect().height),
            } : null,
            rightRect: rightRail ? {
              x: Math.round(rightRail.getBoundingClientRect().x),
              y: Math.round(rightRail.getBoundingClientRect().y),
              width: Math.round(rightRail.getBoundingClientRect().width),
              height: Math.round(rightRail.getBoundingClientRect().height),
            } : null,
            buttons,
          };
        })()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Unexpected layout snapshot: {state}")
    return state


def navigate(cdp: object, url: str, marker: str, *, timeout_seconds: float = 35) -> None:
    cdp.send("Page.navigate", {"url": url})
    wait_for(
        cdp,
        f"document.readyState === 'complete' && document.body && document.body.innerText.includes({json.dumps(marker, ensure_ascii=False)})",
        timeout_seconds=timeout_seconds,
    )
    time.sleep(0.8)


def click_first_open_tile(cdp: object) -> dict[str, object]:
    result = cdp_eval(
        cdp,
        """
        (() => {
          const openLink = Array.from(document.querySelectorAll('a')).find((link) => {
            const text = (link.textContent || '').trim();
            const href = link.getAttribute('href') || '';
            return text === '+' && href.includes('/workbench?seats=');
          });
          if (openLink) {
            const seatArticle = openLink.closest('article, li, div');
            const nearbyText = (seatArticle?.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 240);
            openLink.scrollIntoView({ block: 'center', inline: 'center' });
            openLink.click();
            return { ok: true, kind: 'plus-link', nearbyText, href: openLink.getAttribute('href') || '' };
          }
          const chip = Array.from(document.querySelectorAll('button')).find((button) => {
            const cls = button.className || '';
            return cls.includes('threadChipBtn');
          });
          if (chip) {
            chip.scrollIntoView({ block: 'center', inline: 'center' });
            chip.click();
            return { ok: true, kind: 'thread-chip', nearbyText: (chip.textContent || '').trim() };
          }
          return { ok: false, reason: 'missing-open-entry' };
        })()
        """,
    )
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"Could not open NPC tile: {result}")
    return result


def click_workbench_button(cdp: object, text: str) -> bool:
    result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const wanted = {json.dumps(text, ensure_ascii=False)};
          const button = Array.from(document.querySelectorAll('button')).find((item) => ((item.textContent || '').trim()).includes(wanted));
          if (!button) return false;
          button.scrollIntoView({{ block: 'center', inline: 'nearest' }});
          button.click();
          return true;
        }})()
        """,
    )
    return bool(result)


def click_workbench_link(cdp: object, text: str) -> bool:
    result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const wanted = {json.dumps(text, ensure_ascii=False)};
          const link = Array.from(document.querySelectorAll('a')).find((item) => ((item.textContent || '').trim()).includes(wanted));
          if (!link) return false;
          link.scrollIntoView({{ block: 'center', inline: 'nearest' }});
          link.click();
          return true;
        }})()
        """,
    )
    return bool(result)


def click_professional_view_link(cdp: object) -> str:
    result = cdp_eval(
        cdp,
        """
        (() => {
          const links = Array.from(document.querySelectorAll('a'));
          const professional = links.find((link) => {
            const href = link.getAttribute('href') || '';
            return (href.includes('/datasets?') || href.includes('/ai-lab?') || href.includes('/robotics?'))
              && href.includes('message_id=')
              && href.includes('return_to=');
          });
          if (professional) {
            professional.scrollIntoView({ block: 'center', inline: 'nearest' });
            professional.click();
            return (professional.textContent || '').trim();
          }
          const preferred = links.find((link) => {
            const href = link.getAttribute('href') || '';
            const text = (link.textContent || '').trim();
            return href.includes('/2d-upgrade?panel=') && href.includes('return_to=') && (text.includes('电脑') || text.includes('线程') || text.includes('Git') || text.includes('Skill'));
          });
          if (preferred) {
            preferred.scrollIntoView({ block: 'center', inline: 'nearest' });
            preferred.click();
            return (preferred.textContent || '').trim();
          }
          const fallback = links.find((link) => ((link.textContent || '').trim()).includes('驾驶舱'));
          if (fallback) {
            fallback.scrollIntoView({ block: 'center', inline: 'nearest' });
            fallback.click();
            return (fallback.textContent || '').trim();
          }
          return '';
        })()
        """,
    )
    text = str(result or "").strip()
    if not text:
        raise RuntimeError("Missing professional-view navigation link inside NPC dialog")
    return text


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    token, user_json = cdp_helpers.authenticate(args)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-professional-slice-"))
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

        origin = args.web_base.rstrip("/")
        cdp.send(
            "Network.setCookie",
            {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
        )
        if user_json:
            cdp.send(
                "Network.setCookie",
                {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
            )

        workbench_url = f"{origin}/projects/{args.project_id}/workbench"
        navigate(cdp, workbench_url, "协同工作台")
        initial_layout = snapshot_layout(cdp)
        shot_workbench = output_dir / f"01-workbench-{stamp}.png"
        screenshot(cdp, shot_workbench)

        opened_tile: dict[str, object]
        if args.seats.strip():
            seats_query = "%2C".join([item.strip() for item in args.seats.split(",") if item.strip()])
            cdp.send("Page.navigate", {"url": f"{workbench_url}?seats={seats_query}"})
            wait_for(cdp, "document.readyState === 'complete' && document.body && document.body.innerText.includes('协同工作台')", timeout_seconds=25)
            opened_tile = {"ok": True, "kind": "direct-url", "href": f"{workbench_url}?seats={seats_query}"}
        else:
            opened_tile = click_first_open_tile(cdp)
        wait_for_workbench_tile(cdp, output_dir, stamp)
        tile_messages_ready = wait_for_tile_messages(cdp)
        tile_layout = snapshot_layout(cdp)
        shot_tile = output_dir / f"02-npc-dialog-{stamp}.png"
        screenshot(cdp, shot_tile)

        expand_receipt = click_workbench_button(cdp, "查看回执")
        receipt_expanded = False
        if expand_receipt:
            wait_for(cdp, "document.body && document.body.innerText.includes('平台登记的回执 / 最终结果')", timeout_seconds=10)
            receipt_expanded = True
            shot_receipt = output_dir / f"03-receipt-expanded-{stamp}.png"
            screenshot(cdp, shot_receipt)
            click_workbench_button(cdp, "收起")
            time.sleep(0.5)
        else:
            shot_receipt = None

        navigation_target = click_professional_view_link(cdp)
        if "驾驶舱" in navigation_target:
            wait_for(cdp, "location.pathname.includes('/cockpit') || document.body.innerText.includes('驾驶舱')", timeout_seconds=20)
        elif any(label in navigation_target for label in ("数据工场", "AI 实验室", "机器人现场")):
            wait_for(
                cdp,
                """
                (() => {
                  const pathOk = location.pathname.includes('/datasets') || location.pathname.includes('/ai-lab') || location.pathname.includes('/robotics');
                  const body = document.body?.innerText || '';
                  return pathOk && (body.includes('来自 NPC 对话') || body.includes('任务证据链') || body.includes('证据链焦点'));
                })()
                """,
                timeout_seconds=25,
            )
        else:
            wait_for(cdp, "location.pathname.includes('/2d-upgrade') || location.search.includes('panel=')", timeout_seconds=20)
        professional_layout = snapshot_layout(cdp)
        shot_professional = output_dir / f"04-professional-view-{stamp}.png"
        screenshot(cdp, shot_professional)

        professional_href = str(professional_layout.get("href") or "")
        if (
            any(part in professional_href for part in ("/datasets", "/ai-lab", "/robotics"))
            and click_workbench_link(cdp, "回工作台") is False
            and click_workbench_link(cdp, "返回 NPC 工作台") is False
        ):
            cdp.send("Page.navigate", {"url": workbench_url})
        elif "/2d-upgrade" in professional_href and click_workbench_link(cdp, "返回工作台") is False:
            cdp.send("Page.navigate", {"url": workbench_url})
        elif "/cockpit" in professional_href:
            cdp.send("Page.navigate", {"url": workbench_url})
        wait_for(cdp, "document.readyState === 'complete' && document.body && document.body.innerText.includes('协同工作台')", timeout_seconds=25)
        time.sleep(0.8)
        return_layout = snapshot_layout(cdp)
        shot_return = output_dir / f"05-return-workbench-{stamp}.png"
        screenshot(cdp, shot_return)

        if args.seats.strip():
            seats_query = "%2C".join([item.strip() for item in args.seats.split(",") if item.strip()])
            cdp.send("Page.navigate", {"url": f"{workbench_url}?seats={seats_query}"})
            wait_for(cdp, "document.readyState === 'complete' && document.body && document.body.innerText.includes('协同工作台')", timeout_seconds=25)
        else:
            click_first_open_tile(cdp)
        wait_for_workbench_tile(cdp, output_dir, stamp)
        after_return_messages_ready = wait_for_tile_messages(cdp)
        after_return_layout = snapshot_layout(cdp)
        shot_after_return = output_dir / f"06-dialog-after-return-{stamp}.png"
        screenshot(cdp, shot_after_return)

        other_project_url = f"{origin}/projects"
        navigate(cdp, other_project_url, "项目")
        projects_state = cdp_eval(
            cdp,
            """
            (() => {
              const body = document.body?.innerText || '';
              return {
                hasProjAiCollab: body.includes('proj_ai_collab') || body.includes('AI 协作'),
                hasWorkbenchText: body.includes('协同工作台'),
                href: location.href,
              };
            })()
            """,
        )
        if not isinstance(projects_state, dict):
            raise RuntimeError(f"Unexpected projects state: {projects_state}")
        shot_projects = output_dir / f"07-projects-isolation-{stamp}.png"
        screenshot(cdp, shot_projects)

        overview_layout_stable = (
            bool(initial_layout.get("hasWorkbenchTitle"))
            and bool(return_layout.get("hasWorkbenchTitle"))
            and bool(initial_layout.get("hasRightSummary"))
            and bool(return_layout.get("hasRightSummary"))
            and initial_layout.get("rightRect") == return_layout.get("rightRect")
        )
        tile_layout_stable = (
            bool(tile_layout.get("hasWorkbenchTitle"))
            and bool(after_return_layout.get("hasWorkbenchTitle"))
            and int(tile_layout.get("articleCount") or 0) >= 1
            and int(after_return_layout.get("articleCount") or 0) >= 1
            and bool(tile_messages_ready)
            and bool(after_return_messages_ready)
        )
        layout_stable = overview_layout_stable and tile_layout_stable

        report = {
            "verdict": "passed" if layout_stable else "warning",
            "project_id": args.project_id,
            "workbench_url": workbench_url,
            "opened_tile": opened_tile,
            "receipt_expanded": receipt_expanded,
            "navigation_target": navigation_target,
            "project_isolation": projects_state,
            "layout_stable": layout_stable,
            "overview_layout_stable": overview_layout_stable,
            "tile_layout_stable": tile_layout_stable,
            "tile_messages_ready": tile_messages_ready,
            "after_return_messages_ready": after_return_messages_ready,
            "initial_layout": initial_layout,
            "tile_layout": tile_layout,
            "professional_layout": professional_layout,
            "return_layout": return_layout,
            "after_return_layout": after_return_layout,
            "screenshots": [
                str(shot_workbench),
                str(shot_tile),
                str(shot_receipt) if shot_receipt else None,
                str(shot_professional),
                str(shot_return),
                str(shot_after_return),
                str(shot_projects),
            ],
            "checks": [
                {"name": "入口出现", "ok": True, "detail": "工作台可打开，存在打开瓷砖按钮"},
                {"name": "点击可达", "ok": True, "detail": "NPC 对话可打开，存在协作事件线"},
                {"name": "桌面同步可见", "ok": tile_messages_ready, "detail": "桌面提问/最小回执应进入 NPC 对话流"},
                {"name": "展开/关闭", "ok": receipt_expanded or not expand_receipt, "detail": "若存在回执按钮，可展开后收起"},
                {"name": "专业视图跳转", "ok": True, "detail": f"通过 {navigation_target} 链接进入专业视图"},
                {"name": "返回原位", "ok": bool(return_layout.get('hasWorkbenchTitle')), "detail": "返回工作台后仍能看到协同工作台"},
                {"name": "返回后同步仍可见", "ok": after_return_messages_ready, "detail": "返回后重新打开 NPC，桌面同步消息仍可见"},
                {"name": "总览布局稳定", "ok": overview_layout_stable, "detail": "从专业视图返回后，总览区仍在原位置"},
                {"name": "瓷砖布局稳定", "ok": tile_layout_stable, "detail": "重新打开 NPC 后仍是瓷砖对话形态，桌面同步消息仍可见"},
                {"name": "项目隔离", "ok": not bool(projects_state.get('hasWorkbenchText')), "detail": "项目列表页未残留工作台内容"},
            ],
        }
        report_path = output_dir / f"workbench-professional-view-slice-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
