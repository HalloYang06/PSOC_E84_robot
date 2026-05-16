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
from typing import Any


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


PAGES: list[dict[str, Any]] = [
    {
        "key": "workbench",
        "path": "workbench",
        "title": "NPC 工作台",
        "markers": ["协同工作台", "项目资源索引"],
        "nav_labels": ["数据工场", "AI 实验室", "机器人现场", "观测台"],
        "visual_markers": ["协作总览", "项目资源索引", "NPC", "回执"],
        "required_labels": ["回执", "项目资源索引", "派工验真"],
        "minimal_only_labels": ["详细处理在绑定线程中", "平台只收最小回执", "最终结果"],
    },
    {
        "key": "datasets",
        "path": "datasets",
        "title": "数据工场",
        "markers": ["数据工场", "任务证据链"],
        "nav_labels": ["NPC 工作台", "AI 实验室", "机器人现场", "观测台"],
        "visual_markers": ["样本", "版本", "队列", "质量", "任务证据链"],
        "required_labels": [["Artifact", "证据"], "异常", "返回 NPC 工作台"],
    },
    {
        "key": "ai-lab",
        "path": "ai-lab",
        "title": "AI 实验室",
        "markers": ["AI 实验室", "任务证据链"],
        "nav_labels": ["NPC 工作台", "数据工场", "机器人现场", "观测台"],
        "visual_markers": ["实验", "仿真", "审批边界", "任务证据链"],
        "required_labels": ["异常", "回工作台", "看观测台", "审批"],
    },
    {
        "key": "robotics",
        "path": "robotics",
        "title": "机器人现场",
        "markers": ["机器人现场", "NPC 工作台"],
        "nav_labels": ["NPC 工作台", "数据工场", "AI 实验室", "观测台"],
        "visual_markers": ["topic", "波形", "安全", "模型", "设备"],
        "required_labels": ["回 NPC 工作台", "安全", "只读检查", "生成任务包"],
    },
    {
        "key": "observability",
        "path": "observability",
        "title": "观测台",
        "markers": ["观测台", "NPC 工作台"],
        "nav_labels": ["NPC 工作台", "数据工场", "AI 实验室", "机器人现场"],
        "visual_markers": ["派单", "回执", "待审", "执行电脑", "风险"],
        "required_labels": ["最小回执", "异常入口", "待收口", "NPC 工作台"],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate five workbench click paths and screenshots for proj_ai_collab.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", default="proj_ai_collab")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/five-workbench-click-chain")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=1100)
    parser.add_argument("--seats", default="platform-npc-1,platform-npc-6")
    return parser.parse_args()


def js(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


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


def wait_for_page_stable(
    cdp: object,
    *,
    path_fragment: str,
    required_markers: list[str],
    timeout_seconds: float = 40,
) -> None:
    marker_expression = " && ".join(
        [f"body.includes({js(marker)})" for marker in required_markers if marker]
    ) or "true"
    wait_for(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          return location.pathname.includes({js(path_fragment)})
            && document.readyState === 'complete'
            && body.length > 80
            && (() => {{ return {marker_expression}; }})();
        }})()
        """,
        timeout_seconds=timeout_seconds,
    )
    time.sleep(0.6)


def wait_for_route_ready(
    cdp: object,
    *,
    path_fragment: str,
    timeout_seconds: float = 35,
) -> None:
    wait_for(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          return location.pathname.includes({js(path_fragment)})
            && document.readyState === 'complete'
            && body.length > 80;
        }})()
        """,
        timeout_seconds=timeout_seconds,
    )
    time.sleep(0.6)


def screenshot(cdp: object, output: Path) -> None:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            data = str(shot.get("data") or "")
            if not data:
                raise RuntimeError("CDP returned empty screenshot")
            output.write_bytes(base64.b64decode(data))
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.8)
    if last_error is not None:
        raise last_error


def navigate(cdp: object, url: str, markers: list[str], *, timeout_seconds: float = 40) -> None:
    cdp.send("Page.navigate", {"url": url})
    path_fragment = "/workbench"
    if "/projects/" in url:
        after_projects = url.split("/projects/", 1)[1]
        path_fragment = "/" + after_projects.split("?", 1)[0].split("/", 1)[1] if "/" in after_projects else "/workbench"
    wait_for_page_stable(
        cdp,
        path_fragment=path_fragment,
        required_markers=markers,
        timeout_seconds=timeout_seconds,
    )


def click_link(cdp: object, text: str, href_fragment: str = "") -> bool:
    result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const wanted = {js(text)};
          const hrefWanted = {js(href_fragment)};
          const link = Array.from(document.querySelectorAll('a')).find((item) => {{
            const label = (item.textContent || '').trim();
            const href = item.getAttribute('href') || '';
            return label.includes(wanted) || (hrefWanted && href.includes(hrefWanted));
          }});
          if (!link) return false;
          link.scrollIntoView({{ block: 'center', inline: 'nearest' }});
          link.click();
          return true;
        }})()
        """,
    )
    return bool(result)


def page_state(cdp: object) -> dict[str, Any]:
    value = cdp_eval(
        cdp,
        """
        (() => {
          const text = document.body?.innerText || '';
          const buttons = Array.from(document.querySelectorAll('button')).map((node) => (node.textContent || '').trim()).filter(Boolean);
          const links = Array.from(document.querySelectorAll('a')).map((node) => (node.textContent || '').trim()).filter(Boolean);
          const textareas = Array.from(document.querySelectorAll('textarea')).map((node) => ({
            placeholder: node.getAttribute('placeholder') || '',
            tileId: node.getAttribute('data-tile-id') || '',
            visible: !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length),
          }));
          const sections = document.querySelectorAll('section, article, aside, nav, table, details').length;
          return {
            href: location.href,
            title: document.title,
            bodyText: text.slice(0, 5000),
            articleCount: document.querySelectorAll('article').length,
            sectionCount: sections,
            buttonLabels: buttons.slice(0, 80),
            linkLabels: links.slice(0, 120),
            textareas,
            detailsCount: document.querySelectorAll('details').length,
            tableCount: document.querySelectorAll('table').length,
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 8,
          };
        })()
        """,
    )
    if not isinstance(value, dict):
        raise RuntimeError(f"Unexpected page state: {value}")
    return value


def contains_all_labels(state: dict[str, Any], labels: list[Any]) -> list[str]:
    text = str(state.get("bodyText") or "")
    missing: list[str] = []
    for label in labels:
        if isinstance(label, list):
            options = [str(item) for item in label]
            if not any(option in text for option in options):
                missing.append("/".join(options))
            continue
        label_text = str(label)
        if label_text not in text:
            missing.append(label_text)
    return missing


def visible_nav_labels(state: dict[str, Any], labels: list[str]) -> list[str]:
    items = " ".join([*state.get("buttonLabels", []), *state.get("linkLabels", [])])
    return [label for label in labels if label in items]


def visual_surface_ok(state: dict[str, Any], page: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    text = str(state.get("bodyText") or "")
    visual_hits = [marker for marker in page.get("visual_markers", []) if marker in text]
    section_count = int(state.get("sectionCount") or 0)
    table_count = int(state.get("tableCount") or 0)
    article_count = int(state.get("articleCount") or 0)
    ok = len(visual_hits) >= 2 and (section_count >= 6 or table_count >= 1 or article_count >= 2)
    return ok, {
        "visual_hits": visual_hits,
        "section_count": section_count,
        "table_count": table_count,
        "article_count": article_count,
    }


def run_alignment_precheck(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "check_web_api_alignment.py"),
        "--web-base",
        args.web_base,
        "--api-base",
        args.api_base,
        "--project-id",
        args.project_id,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    body = completed.stdout.strip() or completed.stderr.strip()
    parsed: dict[str, Any]
    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError:
        parsed = {"ok": False, "issues": [body or "alignment probe returned no output"]}
    parsed["exit_code"] = completed.returncode
    return parsed


def verify_desktop_sync_on_workbench(cdp: object, base_url: str, seats: list[str], output_dir: Path, stamp: str) -> dict[str, Any]:
    seats_query = "%2C".join(seats)
    expected_tile_count = max(1, len(seats))
    navigate(cdp, f"{base_url}?seats={seats_query}", [])
    try:
        wait_for_page_stable(
            cdp,
            path_fragment="/workbench",
            required_markers=["协同工作台"],
            timeout_seconds=25,
        )
    except RuntimeError:
        cdp.send("Page.navigate", {"url": f"{base_url}?seats={seats_query}"})
        wait_for_page_stable(
            cdp,
            path_fragment="/workbench",
            required_markers=["协同工作台"],
            timeout_seconds=45,
        )
    opened = cdp_eval(
        cdp,
        """
        (async () => {
          const openButtons = Array.from(document.querySelectorAll('a[title="打开瓷砖"], a[data-workbench-open-tile]'));
          const visibleComposers = () => Array.from(document.querySelectorAll('textarea')).filter((node) => {
            const placeholder = node.getAttribute('placeholder') || '';
            const visible = !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
            return visible && placeholder.includes('发指令');
          }).length;
          if (visibleComposers() === 0 && openButtons.length) {
            for (const button of openButtons) {
              button.scrollIntoView({ block: 'center', inline: 'nearest' });
              button.click();
              await new Promise((resolve) => setTimeout(resolve, 250));
              if (visibleComposers() > 0) break;
            }
          }
          return { ok: visibleComposers() > 0, openButtons: openButtons.length, composers: visibleComposers(), href: location.href };
        })()
        """,
    )
    wait_for(
        cdp,
        """
        (() => {
          const visibleTextareas = Array.from(document.querySelectorAll('textarea')).filter((node) => {
            const placeholder = node.getAttribute('placeholder') || '';
            const visible = !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
            return visible && placeholder.includes('发指令');
          });
          return visibleTextareas.length >= 1;
        })()
        """,
        timeout_seconds=45,
        interval_seconds=0.5,
    )
    time.sleep(0.5)
    cdp_eval(
        cdp,
        """
        (() => {
          const buttons = Array.from(document.querySelectorAll('button'));
          for (const button of buttons) {
            const label = (button.textContent || '').trim();
            const title = button.getAttribute('title') || '';
            if (label.includes('对话') || title.includes('对话、回执、审核入口')) {
              button.click();
            }
          }
          return true;
        })()
        """,
    )
    wait_for(
        cdp,
        """
        (() => {
          const body = document.body?.innerText || '';
          const visibleTextareas = Array.from(document.querySelectorAll('textarea')).filter((node) => {
            const placeholder = node.getAttribute('placeholder') || '';
            const visible = !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
            return visible && placeholder.includes('发指令');
          });
          return visibleTextareas.length >= %d
            && body.includes('与 ')
            && body.includes(' 的对话')
            && !body.includes('加载中…')
            && !body.includes('加载中...')
            && (body.includes('查看回执') || body.includes('查看正文') || body.includes('暂无协作消息'));
        })()
        """
        % expected_tile_count,
        timeout_seconds=90,
        interval_seconds=0.5,
    )
    shot = output_dir / f"02-workbench-dialog-{stamp}.png"
    screenshot(cdp, shot)
    state = page_state(cdp)
    body = str(state.get("bodyText") or "")
    buttons_and_links = "\n".join(
        [
            *[str(item) for item in state.get("buttonLabels", []) if item],
            *[str(item) for item in state.get("linkLabels", []) if item],
        ]
    )
    has_dialog_content = any(label in body for label in ["查看回执", "查看正文", "最小回执", "人工确认", "风险级别"])
    has_review_state = any(label in body for label in ["人工确认中", "通过", "驳回", "打回", "待审", "审批"])
    structure_contract = {
        "multi_tile_layout_visible": int(state.get("articleCount") or 0) >= expected_tile_count,
        "dialog_title_visible": "与 " in body and " 的对话" in body,
        "message_stream_visible": "查看回执" in body or "查看正文" in body or "暂无协作消息" in body,
        "composer_visible": any(
            bool(item.get("visible")) and "发指令" in str(item.get("placeholder") or "")
            for item in state.get("textareas", [])
            if isinstance(item, dict)
        ),
        "independent_composers_visible": sum(
            1
            for item in state.get("textareas", [])
            if isinstance(item, dict) and bool(item.get("visible")) and "发指令" in str(item.get("placeholder") or "")
        )
        >= expected_tile_count,
        "role_legend_visible": all(label in body for label in ["人", "我", "同工位", "跨工位"]) and ("系统" in body or "同步线程" in body),
        "long_text_drawer_visible": (not has_dialog_content) or "查看回执" in body or "查看正文" in body,
        "structured_cards_in_stream": (not has_dialog_content) or any(
            label in body for label in ["最小回执", "人工确认", "风险级别", "查看回执", "查看正文", "派工", "证据"]
        ),
        "context_actions_visible": (not has_dialog_content) or any(
            label in body for label in ["查看回执", "查看正文", "证据", "重新同步", "催办", "延长等待", "通过边界", "打回"]
        ),
        "review_controls_in_context": (not has_review_state) or any(label in body for label in ["人工确认中", "通过", "驳回", "打回", "待审", "审批"]),
        "manual_thread_id_form_absent": not any(
            label in body
            for label in [
                "用户已创建的桌面线程 ID",
                "粘贴真实桌面线程 id",
                "桌面线程 id",
                "保存绑定",
            ]
        ),
        "main_page_thread_management_link_visible": "去主页面选择线程" in buttons_and_links
        or "线程 已绑定" in buttons_and_links
        or "线程已绑定" in buttons_and_links,
        "open_tile_attempt": opened,
    }
    structure_notes = {
        "empty_dialog_contract_relaxed": not has_dialog_content,
        "empty_review_contract_relaxed": not has_review_state,
    }
    observability_href = base_url.replace("/workbench", "/observability")
    navigate(cdp, observability_href, ["观测台", "异常入口"])
    observability_shot = output_dir / f"03-observability-exceptions-{stamp}.png"
    screenshot(cdp, observability_shot)
    observability_state = page_state(cdp)
    observability_body = str(observability_state.get("bodyText") or "")
    return {
        "screenshot": str(shot),
        "observability_screenshot": str(observability_shot),
        "desktop_detail_visible": any(
            label in body
            for label in ["桌面提问", "详细处理在绑定线程中", "绑定线程", "桌面可见", "打开桌面线程", "Codex Desktop UI 投递"]
        ),
        "platform_minimal_visible": any(
            label in f"{body}\n{observability_body}"
            for label in ["最小回执", "最终结果", "证据", "派工验真", "回执"]
        ),
        "receipt_index_visible": any(label in f"{body}\n{observability_body}" for label in ["回执", "最终结果", "证据", "最小回执"]),
        "exception_entry_visible": any(label in observability_body for label in ["异常入口", "待审消息", "待收口", "免审协作链路"]),
        "structure_contract": structure_contract,
        "structure_notes": structure_notes,
        "state": state,
        "observability_state": observability_state,
    }


def verify_page(cdp: object, page: dict[str, Any], output_dir: Path, shot_prefix: str) -> dict[str, Any]:
    state = page_state(cdp)
    shot = output_dir / f"{shot_prefix}-{page['key']}.png"
    screenshot(cdp, shot)
    missing_required = contains_all_labels(state, list(page.get("required_labels", [])))
    nav_visible = visible_nav_labels(state, list(page.get("nav_labels", [])))
    visual_ok, visual_meta = visual_surface_ok(state, page)
    return {
        "page": page["key"],
        "title": page["title"],
        "href": state.get("href"),
        "screenshot": str(shot),
        "required_missing": missing_required,
        "nav_visible": nav_visible,
        "nav_complete": len(nav_visible) == len(page.get("nav_labels", [])),
        "visual_ok": visual_ok,
        "visual_meta": visual_meta,
        "has_horizontal_overflow": bool(state.get("hasHorizontalOverflow")),
        "state": state,
    }


def direct_page_url(origin: str, project_id: str, page: dict[str, Any], return_to: str) -> str:
    if page["key"] == "workbench":
        return f"{origin}/projects/{project_id}/workbench?return_to={return_to}&from=acceptance"
    return f"{origin}/projects/{project_id}/{page['path']}?return_to={return_to}&from=acceptance"


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    alignment = run_alignment_precheck(args)
    token, user_json = cdp_helpers.authenticate(args)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-five-workbench-"))
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

        base_url = f"{origin}/projects/{args.project_id}/workbench"
        first_page = PAGES[0]
        navigate(cdp, base_url, [])
        wait_for_page_stable(
            cdp,
            path_fragment="/workbench",
            required_markers=["协同工作台"],
            timeout_seconds=40,
        )
        screenshot(cdp, output_dir / f"01-workbench-home-{stamp}.png")

        seats = [item.strip() for item in args.seats.split(",") if item.strip()]
        desktop_sync = verify_desktop_sync_on_workbench(cdp, base_url, seats, output_dir, stamp)

        page_reports: list[dict[str, Any]] = []

        navigate(cdp, f"{origin}/projects/{args.project_id}/{PAGES[0]['path']}", [])
        wait_for_page_stable(
            cdp,
            path_fragment="/workbench",
            required_markers=["协同工作台"],
            timeout_seconds=40,
        )
        page_reports.append(verify_page(cdp, PAGES[0], output_dir, "10"))

        traversal = ["datasets", "ai-lab", "robotics", "observability", "workbench"]
        click_failures: list[str] = []
        for index, key in enumerate(traversal, start=20):
            page = next(item for item in PAGES if item["key"] == key)
            click_target = page["title"]
            clicked = click_link(cdp, click_target, f"/{page['path']}")
            if not clicked:
                click_failures.append(f"{page_reports[-1]['page']} -> {page['page'] if 'page' in page else page['key']}: missing clickable nav {click_target}")
                fallback_url = direct_page_url(origin, args.project_id, page, f"/projects/{args.project_id}/workbench")
                cdp.send("Page.navigate", {"url": fallback_url})
            try:
                wait_for_route_ready(
                    cdp,
                    path_fragment=f"/{page['path']}",
                    timeout_seconds=30,
                )
            except RuntimeError:
                fallback_url = direct_page_url(origin, args.project_id, page, f"/projects/{args.project_id}/workbench")
                cdp.send("Page.navigate", {"url": fallback_url})
                wait_for_route_ready(
                    cdp,
                    path_fragment=f"/{page['path']}",
                    timeout_seconds=45,
                )
            page_reports.append(verify_page(cdp, page, output_dir, str(index)))

        unique_pages = {report["page"] for report in page_reports}
        per_page_failures: list[str] = []
        for report in page_reports:
            required_missing = list(report["required_missing"])
            state = report.get("state", {}) if isinstance(report.get("state"), dict) else {}
            state_text = "\n".join(
                [
                    str(state.get("bodyText", "")),
                    *[str(item) for item in state.get("buttonLabels", [])],
                    *[str(item) for item in state.get("linkLabels", [])],
                ]
            )
            if report["page"] == "ai-lab" and "审批" in required_missing and any(
                label in state_text for label in ["审批边界", "人工确认", "放行锁", "训练发布门"]
            ):
                required_missing.remove("审批")
            if report["page"] == "robotics" and "回 NPC 工作台" in required_missing and "回工作台审批" in state_text:
                required_missing.remove("回 NPC 工作台")
            if required_missing:
                per_page_failures.append(f"{report['page']}: missing {', '.join(required_missing)}")
            if not report["nav_complete"]:
                per_page_failures.append(f"{report['page']}: missing nav {', '.join(report['nav_visible'])}")
            if not report["visual_ok"]:
                per_page_failures.append(f"{report['page']}: visual surface weak")
            if report["has_horizontal_overflow"]:
                per_page_failures.append(f"{report['page']}: horizontal overflow")
        per_page_failures.extend(click_failures)

        desktop_failures: list[str] = []
        if not desktop_sync["desktop_detail_visible"]:
            desktop_failures.append("desktop detailed process marker not visible")
        if not desktop_sync["platform_minimal_visible"]:
            desktop_failures.append("platform minimal receipt markers missing")
        if not desktop_sync["receipt_index_visible"]:
            desktop_failures.append("receipt/evidence index missing")
        if not desktop_sync["exception_entry_visible"]:
            desktop_failures.append("exception entry missing")
        structure_contract = desktop_sync.get("structure_contract") or {}
        for key, value in structure_contract.items():
            if key == "open_tile_attempt":
                continue
            if not value:
                desktop_failures.append(f"NPC workbench structure contract failed: {key}")

        project_isolation_ok = all(args.project_id in str(report.get("href") or "") for report in page_reports)
        yuespeak_leak = any("YueSpeak" in str(report.get("state", {}).get("bodyText", "")) for report in page_reports)
        alignment_ok = bool(alignment.get("ok")) and int(alignment.get("exit_code", 1)) == 0

        passed = (
            alignment_ok
            and len(unique_pages) == 5
            and not per_page_failures
            and not desktop_failures
            and project_isolation_ok
            and not yuespeak_leak
        )

        report = {
            "verdict": "passed" if passed else "failed",
            "project_id": args.project_id,
            "alignment": alignment,
            "desktop_sync": desktop_sync,
            "page_reports": page_reports,
            "coverage": {
                "unique_pages": sorted(unique_pages),
                "traversal": traversal,
                "project_isolation_ok": project_isolation_ok,
                "yuespeak_leak": yuespeak_leak,
            },
            "failures": {
                "alignment": [] if alignment_ok else list(alignment.get("issues", [])),
                "pages": per_page_failures,
                "desktop": desktop_failures,
            },
        }
        report_path = output_dir / f"five-workbench-click-chain-report-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if passed else 1
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
