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
from urllib.parse import urlencode
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


INTERNAL_TERMS = [
    "adapter",
    "bridge",
    "session jsonl",
    "codex-session",
    "source_thread",
    "provider cli",
    "local prompt file",
    "thread id",
    "desktop thread id",
    "workstation-inbox",
]

EXTERNAL_WALL_TERMS = [
    "langfuse",
    "phoenix",
    "opentelemetry",
    "mlflow",
    "ragas",
    "sentry",
    "grafana",
]

SURFACES = [
    {
        "key": "datasets",
        "path": "datasets",
        "title": "数据工场",
        "expected": ["当前证据链", "回 NPC 工作台", "看观测台"],
        "next": ["采集 / 样本", "复核 / QA", "manifest / 导出", "训练回执", "下一步"],
        "evidence": ["样本队列", "质检", "数据版本", "异常", "回执", "证据"],
    },
    {
        "key": "ai-lab",
        "path": "ai-lab",
        "title": "AI 实验室",
        "expected": ["实验态势", "回 NPC 工作台", "看观测台"],
        "next": ["下一步动作", "当前证据链", "下一步路径"],
        "evidence": ["运行回放", "证据索引", "异常入口", "待收口"],
    },
    {
        "key": "robotics",
        "path": "robotics",
        "title": "机器人现场",
        "expected": ["任务证据链", "回工作台", "查看观测台"],
        "next": ["下一步", "只读观测", "派给 NPC", "回工作台审批"],
        "evidence": ["派单", "证据", "异常", "topic", "波形"],
    },
    {
        "key": "observability",
        "path": "observability",
        "title": "观测台",
        "expected": ["当前证据链", "回 NPC 工作台", "全链路入口"],
        "next": ["打开 NPC 工作台", "重新同步", "催办", "延长等待"],
        "evidence": ["派工验真", "异常入口", "待收口", "回执", "证据", "执行电脑能力"],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate focused datasets / ai-lab / robotics / observability first screens.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", default="proj_ai_collab")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/professional-surfaces-fullchain")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=1100)
    return parser.parse_args()


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    token: str = "",
    timeout: int = 20,
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


def api_get(base: str, token: str, path: str, query: dict[str, object] | None = None) -> object:
    url = f"{base.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return request_json(url, token=token).get("data")


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
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        data = {"ok": False, "issues": [body or "alignment probe returned no output"]}
    data["exit_code"] = completed.returncode
    return data


def latest_matching(messages: list[dict[str, Any]], predicate) -> dict[str, Any] | None:
    for item in messages:
        if predicate(item):
            return item
    return None


def message_metadata(message: dict[str, Any] | None) -> dict[str, Any]:
    if not message:
        return {}
    extra = message.get("extra_data")
    meta = message.get("metadata")
    result: dict[str, Any] = {}
    if isinstance(extra, dict):
        result.update(extra)
    if isinstance(meta, dict):
        result.update(meta)
    return result


def build_focus_context(
    messages: list[dict[str, Any]],
    tasks: list[dict[str, Any]] | None,
    api_base: str,
    token: str,
    project_id: str,
) -> dict[str, str]:
    focused = latest_matching(
        messages,
        lambda item: bool(item.get("task_id"))
        and bool(message_metadata(item).get("source_message_id") or item.get("id"))
        and str(item.get("project_id") or "") == project_id,
    )
    if focused:
        meta = message_metadata(focused)
        task_id = str(focused.get("task_id") or "")
        message_id = str(meta.get("source_message_id") or focused.get("id") or "")
        dispatch_id = str(focused.get("dispatch_id") or meta.get("dispatch_id") or "")
        source_seat = str(meta.get("authoritative_sender_seat_id") or focused.get("sender_id") or "")
        source_label = str(meta.get("authoritative_sender_label") or "")
        source_title = str(focused.get("title") or focused.get("body") or "当前证据链")[:120]
    else:
        task_id = ""
        message_id = ""
        dispatch_id = ""
        source_seat = ""
        source_label = ""
        source_title = "当前证据链"
    if focused and task_id and message_id:
        return {
            "task_id": task_id,
            "message_id": message_id,
            "dispatch_id": dispatch_id,
            "source_seat": source_seat,
            "source_label": source_label,
            "source_title": source_title,
        }

    task_list = tasks or []
    chosen_task = next(
        (
            item for item in task_list
            if str(item.get("project_id") or "") == project_id
            and str(item.get("id") or "").strip()
        ),
        None,
    )
    if not chosen_task:
        raise RuntimeError("Could not find a focused collaboration message or task context")

    task_id = str(chosen_task.get("id") or "").strip()
    view = api_get(api_base, token, f"/api/tasks/{task_id}/professional-view")
    if not isinstance(view, dict):
        raise RuntimeError(f"Could not load professional view for task {task_id}")
    messages_view = view.get("messages") if isinstance(view.get("messages"), list) else []
    receipts_view = view.get("receipts") if isinstance(view.get("receipts"), list) else []
    dispatches_view = view.get("dispatches") if isinstance(view.get("dispatches"), list) else []
    latest_message = messages_view[0] if messages_view else {}
    latest_receipt = receipts_view[0] if receipts_view else {}
    latest_dispatch = dispatches_view[0] if dispatches_view else {}
    task_obj = view.get("task") if isinstance(view.get("task"), dict) else chosen_task
    task_meta = message_metadata(latest_message if isinstance(latest_message, dict) else {})
    message_id = str(
        (latest_receipt.get("source_message_id") if isinstance(latest_receipt, dict) else "")
        or (latest_message.get("id") if isinstance(latest_message, dict) else "")
        or ""
    ).strip()
    return {
        "task_id": task_id,
        "message_id": message_id,
        "dispatch_id": str(
            (latest_message.get("dispatch_id") if isinstance(latest_message, dict) else "")
            or (latest_receipt.get("dispatch_id") if isinstance(latest_receipt, dict) else "")
            or (latest_dispatch.get("id") if isinstance(latest_dispatch, dict) else "")
            or ""
        ).strip(),
        "source_seat": str(
            task_meta.get("authoritative_sender_seat_id")
            or (latest_message.get("sender_id") if isinstance(latest_message, dict) else "")
            or ""
        ).strip(),
        "source_label": str(task_meta.get("authoritative_sender_label") or "").strip(),
        "source_title": str(task_obj.get("title") or chosen_task.get("title") or "当前证据链")[:120],
    }


def open_browser(args: argparse.Namespace, token: str, user_json: str) -> tuple[object, subprocess.Popen[bytes], Path]:
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-professional-surfaces-"))
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
    if token:
        cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
    if user_json:
        cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
    return cdp, edge_process, profile_dir


def build_surface_url(args: argparse.Namespace, surface_path: str, focus: dict[str, str], from_key: str) -> str:
    params = {
        "return_to": f"/projects/{args.project_id}/workbench",
        "from": from_key,
        "task_id": focus["task_id"],
        "message_id": focus["message_id"],
        "dispatch_id": focus["dispatch_id"],
        "source_seat": focus["source_seat"],
        "source_label": focus["source_label"],
        "source_title": focus["source_title"],
    }
    query = urlencode({key: value for key, value in params.items() if value})
    return f"{args.web_base.rstrip('/')}/projects/{args.project_id}/{surface_path}?{query}"


def count_occurrences(text: str, needles: list[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(needle.lower()) for needle in needles)


def find_visible_terms(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def analyze_surface_state(cdp: object, surface: dict[str, Any]) -> dict[str, Any]:
    state = cdp_eval(
        cdp,
        """
        (() => {
          const body = document.body?.innerText || '';
          const links = Array.from(document.querySelectorAll('a')).map((link) => ({
            text: (link.textContent || '').trim(),
            href: link.getAttribute('href') || '',
          }));
          const buttons = Array.from(document.querySelectorAll('button')).map((button) => ({
            text: (button.textContent || '').trim(),
            title: button.getAttribute('title') || '',
          }));
          const strongs = Array.from(document.querySelectorAll('strong')).map((node) => (node.textContent || '').trim()).slice(0, 120);
          const firstScreenButtons = Array.from(document.querySelectorAll('a, button'))
            .filter((node) => {
              const rect = node.getBoundingClientRect();
              const text = (node.textContent || '').trim();
              const isSecondaryExceptionAction = Boolean(node.closest('[aria-label="异常入口"]'));
              const style = window.getComputedStyle(node);
              return text
                && !isSecondaryExceptionAction
                && style.display !== 'none'
                && style.visibility !== 'hidden'
                && style.opacity !== '0'
                && rect.width > 1
                && rect.height > 1
                && rect.top >= 0
                && rect.top < window.innerHeight * 0.92;
            })
            .map((node) => (node.textContent || '').trim())
            .slice(0, 40);
          return {
            href: location.href,
            title: document.title,
            bodyText: body,
            bodyLength: body.length,
            linkCount: links.length,
            buttonCount: buttons.length,
            links,
            buttons,
            strongs,
            firstScreenButtons,
            horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 2,
            articleCount: document.querySelectorAll('article').length,
            h2Count: document.querySelectorAll('h2').length,
          };
        })()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Unexpected surface state for {surface['key']}: {state}")

    body = str(state.get("bodyText") or "")
    links = state.get("links") if isinstance(state.get("links"), list) else []
    link_texts = " ".join(str(item.get("text") or "") for item in links if isinstance(item, dict))
    all_text = f"{body}\n{link_texts}"

    expected_hits = [label for label in surface["expected"] if label in all_text]
    next_hits = [label for label in surface["next"] if label in all_text]
    evidence_hits = [label for label in surface["evidence"] if label in all_text]

    has_workbench_return = any(label in all_text for label in ["回 NPC 工作台", "返回 NPC 工作台", "回工作台"])
    has_observability_link = any(label in all_text for label in ["看观测台", "查看观测台", "观测台"])
    text_wall_risk = len(body) > 9000 or count_occurrences(body, ["说明", "用户需要", "平台负责", "这里不"]) >= 12
    external_wall_risk = count_occurrences(all_text, EXTERNAL_WALL_TERMS) >= 3
    first_screen_buttons = state.get("firstScreenButtons") if isinstance(state.get("firstScreenButtons"), list) else []
    primary_action_count = sum(
        1
        for item in first_screen_buttons
        if isinstance(item, str) and any(
            token in item for token in ["回 NPC 工作台", "回工作台", "看观测台", "查看观测台", "重新同步", "催办", "延长等待", "看数据工场", "看 AI 实验室", "看机器人现场"]
        )
    )

    return {
        "href": state.get("href"),
        "title": state.get("title"),
        "body_length": state.get("bodyLength"),
        "article_count": state.get("articleCount"),
        "expected_hits": expected_hits,
        "next_hits": next_hits,
        "evidence_hits": evidence_hits,
        "has_task_focus": any(label in all_text for label in ["当前证据链", "任务证据链", "来自 NPC 对话", "当前任务对象", "任务"]),
        "has_next_action": len(next_hits) > 0,
        "has_workbench_return": has_workbench_return,
        "has_observability_link": has_observability_link,
        "primary_action_count": primary_action_count,
        "horizontal_overflow": bool(state.get("horizontalOverflow")),
        "text_wall_risk": text_wall_risk,
        "external_wall_risk": external_wall_risk,
        "internal_terms": find_visible_terms(all_text, INTERNAL_TERMS),
        "missing_expected": [label for label in surface["expected"] if label not in expected_hits],
        "missing_evidence": [label for label in surface["evidence"] if label not in evidence_hits],
        "has_execution_computer_panel": all(label in all_text for label in ["执行电脑能力", "执行电脑调度"]),
        "strongs": state.get("strongs") if isinstance(state.get("strongs"), list) else [],
    }


def navigate_and_capture(cdp: object, args: argparse.Namespace, output_dir: Path, stamp: str, surface: dict[str, Any], focus: dict[str, str]) -> dict[str, Any]:
    url = build_surface_url(args, surface["path"], focus, surface["key"])
    cdp.send("Page.navigate", {"url": url})
    focus_title = str(focus.get("source_title") or "当前证据链")
    wait_for(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          return location.pathname.includes('/{surface["path"]}')
            && body.includes({json.dumps(surface["title"], ensure_ascii=False)})
            && (
              body.includes({json.dumps(focus_title, ensure_ascii=False)})
              || body.includes('当前证据链')
              || body.includes('任务证据链')
            );
        }})()
        """,
        timeout_seconds=35,
    )
    time.sleep(1.0)
    shot = output_dir / f"{surface['key']}-focused-{stamp}.png"
    screenshot(cdp, shot)
    analyzed = analyze_surface_state(cdp, surface)
    analyzed["screenshot"] = str(shot)
    return analyzed


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    alignment = run_alignment_precheck(args)
    token, user_json = cdp_helpers.authenticate(args)
    messages = api_get(args.api_base, token, "/api/collaboration/messages", {"project_id": args.project_id, "limit": 400})
    if not isinstance(messages, list):
        raise RuntimeError("Could not load collaboration messages")
    tasks = api_get(args.api_base, token, "/api/tasks", {"project_id": args.project_id})
    focus = build_focus_context(messages, tasks if isinstance(tasks, list) else [], args.api_base, token, args.project_id)

    cdp = None
    edge_process = None
    profile_dir = None
    surface_results: dict[str, Any] = {}
    try:
        cdp, edge_process, profile_dir = open_browser(args, token, user_json)
        for surface in SURFACES:
            surface_results[surface["key"]] = navigate_and_capture(cdp, args, output_dir, stamp, surface, focus)
    finally:
        if cdp is not None:
            cdp.close()
        if edge_process is not None and edge_process.poll() is None:
            edge_process.kill()
        if profile_dir is not None:
            shutil.rmtree(profile_dir, ignore_errors=True)

    failures: list[dict[str, str]] = []
    if not alignment.get("ok"):
        failures.append({"area": "desktop-sync", "reason": "; ".join(alignment.get("issues", [])) or "alignment failed"})

    for surface in SURFACES:
        result = surface_results[surface["key"]]
        if not result.get("has_task_focus"):
            failures.append({"area": surface["key"], "reason": "首屏没有清晰的当前任务/证据链焦点"})
        if not result.get("has_next_action"):
            failures.append({"area": surface["key"], "reason": "首屏缺少下一步动作"})
        if not result.get("has_workbench_return"):
            failures.append({"area": surface["key"], "reason": "首屏没有回 NPC 工作台入口"})
        if surface["key"] != "observability" and not result.get("has_observability_link"):
            failures.append({"area": surface["key"], "reason": "首屏没有进入观测台入口"})
        if surface["key"] == "observability" and int(result.get("primary_action_count") or 0) > 3:
            failures.append({"area": surface["key"], "reason": "首屏主动作超过 3 个，负责人第一眼仍然会被噪音淹没"})
        if result.get("horizontal_overflow"):
            failures.append({"area": surface["key"], "reason": "存在水平溢出"})
        if result.get("text_wall_risk"):
            failures.append({"area": surface["key"], "reason": "首屏仍偏文字墙"})
        if result.get("external_wall_risk"):
            failures.append({"area": surface["key"], "reason": "首屏仍像外链/开源参考墙"})
        for term in result.get("internal_terms", []):
            failures.append({"area": surface["key"], "reason": f"暴露内部词: {term}"})
        if surface["key"] == "observability" and "派工验真" not in result.get("evidence_hits", []):
            failures.append({"area": surface["key"], "reason": "首屏没有清晰看到派工验真/证据入口"})
        if surface["key"] == "observability" and not result.get("has_execution_computer_panel"):
            failures.append({"area": surface["key"], "reason": "观测台缺少部署前执行电脑能力面板"})

    report = {
        "verdict": "passed" if not failures else "failed",
        "project_id": args.project_id,
        "focus": focus,
        "alignment": alignment,
        "surfaces": surface_results,
        "screenshots": [surface_results[surface["key"]]["screenshot"] for surface in SURFACES],
        "open_source_reference_to_platform_capability": {
            "Langfuse/Phoenix 类 trace 参考": "转成任务 / 派单 / 回执 / 证据链首屏焦点，而不是独立观测工具入口",
            "OpenTelemetry/Grafana 类健康参考": "转成观测台里的服务实例健康、执行电脑在线、待收口入口",
            "MLflow/Ragas 类实验参考": "转成 AI 实验室里的运行回放、证据索引、训练回执和审批边界",
            "ROS/Gazebo/Foxglove 类现场参考": "转成机器人现场里的只读 topic / 波形 / 安全闸门和回工作台审批入口",
        },
        "failures": failures,
    }
    report_path = output_dir / f"professional-surfaces-fullchain-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "report": str(report_path)}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
