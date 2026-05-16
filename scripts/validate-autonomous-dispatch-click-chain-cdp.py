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
    "session JSONL",
    "codex-session",
    "线程 codex",
    "Provider CLI",
    "Local prompt file",
    "source_thread",
    "canonical_workstation_id",
    "requested_workstation_id",
]

RAW_LINEAGE_TERMS = [
    "source_message_id",
    "root_message_id",
    "delegation_context",
    "source_message",
    "root_message",
]

PATH_LEAK_TERMS = [
    "artifacts\\workstation-inbox\\",
    "artifacts/workstation-inbox/",
    "\\.codex\\sessions\\",
    "/.codex/sessions/",
    "C:\\Users\\",
    "D:\\ai合作产品\\artifacts\\",
]

FORMAL_SUBJECT_MARKERS = [
    "1号 前端实现",
    "2号 后端数据流",
    "3号 前端验收",
    "4号 平台路由",
    "5号 Runner 与桌面同步",
    "6号 Boss 总控",
]

CURRENT_CHAIN_SEAT_MARKERS = [
    "1号 前端实现",
    "2号 后端数据流",
    "3号 前端验收",
    "5号 Runner 与桌面同步",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate clickable autonomous dispatch chains for user/Boss/NPC flows.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", default="proj_ai_collab")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/autonomous-dispatch-click-chain")
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


def wait_for_surface_stable(
    cdp: object,
    *,
    path_fragment: str,
    required_markers: list[str],
    timeout_seconds: float = 35,
) -> None:
    marker_expression = " && ".join(
        [f"body.includes({json.dumps(marker, ensure_ascii=False)})" for marker in required_markers if marker]
    ) or "true"
    wait_for(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          return location.pathname.includes({json.dumps(path_fragment, ensure_ascii=False)})
            && document.readyState === 'complete'
            && body.length > 80
            && (() => {{ return {marker_expression}; }})();
        }})()
        """,
        timeout_seconds=timeout_seconds,
    )
    time.sleep(0.6)


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


def latest_matching(
    messages: list[dict[str, Any]],
    predicate,
) -> dict[str, Any] | None:
    for item in messages:
        if predicate(item):
            return item
    return None


def find_final_for_source(messages: list[dict[str, Any]], source_id: str) -> dict[str, Any] | None:
    return latest_matching(
        messages,
        lambda item: str(item.get("message_type") or "") in {"agent_result", "requirement_final_reply", "runner_result"}
        and str((item.get("metadata") or {}).get("source_message_id") or "") == source_id,
    )


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


def is_desktop_closeout_waiting(message: dict[str, Any] | None) -> bool:
    metadata = message_metadata(message)
    taxonomy = metadata.get("blocked_taxonomy")
    if not isinstance(taxonomy, dict):
        taxonomy = {}
    reason = str(
        taxonomy.get("blocked_reason_code")
        or taxonomy.get("exception_kind")
        or metadata.get("progress_state")
        or "",
    ).lower()
    return bool(
        metadata.get("desktop_closeout_waiting")
        or metadata.get("needs_manual_closeout")
        or taxonomy.get("desktop_closeout_waiting")
        or reason in {"desktop_final_sync_lag", "desktop_delivery_unconfirmed"}
    )


def is_hard_failed_current_message(message: dict[str, Any] | None, final: dict[str, Any] | None = None) -> bool:
    if not message or final or is_desktop_closeout_waiting(message):
        return False
    status = str(message.get("status") or "").lower()
    if status not in {"failed", "rejected", "cancelled", "error"}:
        return False
    metadata = message_metadata(message)
    if metadata.get("timeout_repair") or metadata.get("desktop_sync_retry_available"):
        return False
    return True


def find_latest_for_recipient_title(
    messages: list[dict[str, Any]],
    recipient_id: str,
    title_keyword: str,
) -> dict[str, Any] | None:
    return latest_matching(
        messages,
        lambda item: str(item.get("recipient_id") or "") == recipient_id
        and title_keyword in str(item.get("title") or ""),
    )


def open_browser(args: argparse.Namespace, token: str, user_json: str) -> tuple[object, subprocess.Popen[bytes], Path]:
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-autonomous-dispatch-"))
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


def click_text(cdp: object, text: str, *, selector: str = "button, a") -> bool:
    result = cdp_eval(
        cdp,
        f"""
        (() => {{
          const wanted = {json.dumps(text, ensure_ascii=False)};
          const node = Array.from(document.querySelectorAll({json.dumps(selector)})).find((item) => ((item.textContent || '').trim()).includes(wanted));
          if (!node) return false;
          node.scrollIntoView({{ block: 'center', inline: 'nearest' }});
          node.click();
          return true;
        }})()
        """,
    )
    return bool(result)


def wait_for_observability_ready(cdp: object, *, timeout_seconds: float = 30) -> None:
    wait_for(
        cdp,
        """
        (() => {
          const body = document.body?.innerText || '';
          const hasReadyMarker = [
            '当前证据链',
            '下一步动作',
            '最近协作证据',
            '工作内容',
            '异常入口',
            '桌面过程 / 待收口',
          ].some((label) => body.includes(label));
          return location.pathname.includes('/observability')
            && document.readyState === 'complete'
            && body.length > 80
            && body.includes('观测台')
            && hasReadyMarker;
        })()
        """,
        timeout_seconds=timeout_seconds,
    )
    time.sleep(0.6)


def find_visible_terms(text: str, terms: list[str]) -> list[str]:
    body = text.lower()
    hits: list[str] = []
    for term in terms:
        if term.lower() in body:
            hits.append(term)
    return hits


def count_subject_markers(text: str, markers: list[str]) -> int:
    return sum(1 for marker in markers if marker in text)


def find_path_leaks(text: str) -> list[str]:
    return find_visible_terms(text, PATH_LEAK_TERMS)


def find_raw_uuid_leaks(text: str) -> list[str]:
    import re

    return re.findall(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", text, flags=re.I)


def count_occurrences(text: str, marker: str) -> int:
    return text.count(marker)


def capture_workbench_dispatch_chain(
    cdp: object,
    args: argparse.Namespace,
    output_dir: Path,
    stamp: str,
) -> dict[str, Any]:
    base = f"{args.web_base.rstrip('/')}/projects/{args.project_id}/workbench?seats=platform-npc-1%2Cplatform-npc-2%2Cplatform-npc-3%2Cplatform-npc-4%2Cplatform-npc-5%2Cplatform-npc-6"
    cdp.send("Page.navigate", {"url": base})
    try:
        wait_for_surface_stable(
            cdp,
            path_fragment="/workbench",
            required_markers=["协同工作台", "派工验真"],
            timeout_seconds=40,
        )
    except RuntimeError:
        cdp.send("Page.navigate", {"url": base})
        wait_for_surface_stable(
            cdp,
            path_fragment="/workbench",
            required_markers=["协同工作台", "派工验真"],
            timeout_seconds=70,
        )
    click_text(cdp, "总览")
    wait_for(cdp, "document.body && document.body.innerText.includes('派工验真')", timeout_seconds=15)
    screenshot(cdp, output_dir / f"01-workbench-overview-{stamp}.png")

    state = cdp_eval(
        cdp,
        """
        (() => {
          const body = document.body?.innerText || '';
          const composers = Array.from(document.querySelectorAll('textarea')).filter((node) => {
            const placeholder = node.getAttribute('placeholder') || '';
            const visible = !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
            return visible && placeholder.includes('发指令');
          });
          return {
            hasDispatchEvidence: body.includes('派工验真'),
            hasUserDispatch: body.includes('用户派工'),
            hasPeerDispatch: body.includes('NPC互派'),
            hasReceiptIndex: body.includes('回执'),
            hasDesktopVisibility: body.includes('桌面 6/6'),
            hasPendingReview: body.includes('硬件强审') || body.includes('待审'),
            hasStructuredCardsInStream: ['最小回执', '人工确认', '风险级别', '查看回执', '派工', '证据'].some((label) => body.includes(label)),
            hasLongReceiptDrawer: body.includes('查看回执'),
            hasNoThreadIdForm: !['用户已创建的桌面线程 ID', '桌面线程 id', '粘贴真实桌面线程 id'].some((label) => body.includes(label)),
            composerCount: composers.length,
            tileCount: document.querySelectorAll('article').length,
          };
        })()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"Unexpected workbench state: {state}")

    wait_for(
        cdp,
        """
        (() => {
          const body = document.body?.innerText || '';
          return body.includes('打开桌面线程')
            && (body.includes('详细过程在桌面线程中') || body.includes('详细处理在绑定线程中'));
        })()
        """,
        timeout_seconds=20,
    )
    screenshot(cdp, output_dir / f"02-workbench-desktop-visible-{stamp}.png")

    receipt_clicked = click_text(cdp, "查看回执")
    if receipt_clicked:
      wait_for(cdp, "document.body && document.body.innerText.includes('平台登记的回执 / 最终结果')", timeout_seconds=10)
      screenshot(cdp, output_dir / f"03-workbench-receipt-expanded-{stamp}.png")

    evidence_clicked = click_text(cdp, "证据", selector="button")
    if evidence_clicked:
        time.sleep(1.2)
    workbench_after = str(cdp_eval(cdp, "document.body ? document.body.innerText : ''") or "")
    sync_clicked = click_text(cdp, "重新同步")
    if sync_clicked:
        time.sleep(0.8)
        screenshot(cdp, output_dir / f"03b-workbench-resync-{stamp}.png")
    nudge_clicked = click_text(cdp, "催办")
    if nudge_clicked:
        time.sleep(0.8)
        screenshot(cdp, output_dir / f"03c-workbench-nudge-{stamp}.png")
    extend_clicked = click_text(cdp, "延长等待")
    if extend_clicked:
        time.sleep(0.8)
        screenshot(cdp, output_dir / f"03d-workbench-extend-wait-{stamp}.png")
    return {
        "overview": state,
        "receipt_clicked": receipt_clicked,
        "evidence_clicked": evidence_clicked,
        "sync_clicked": sync_clicked,
        "nudge_clicked": nudge_clicked,
        "extend_clicked": extend_clicked,
        "hasBlockedAction": "异常" in workbench_after or "待审" in workbench_after,
        "hasFinalAction": "最新最终回执" in workbench_after or "查看回执" in workbench_after,
        "hasContinueAction": "继续观察" in workbench_after or "继续推进" in workbench_after or "继续下一步" in workbench_after or "下一步" in workbench_after,
        "hasPendingCloseout": "待收口" in workbench_after or "等待最小回执 / 最终结果" in workbench_after or "正在等待桌面最终记录写出回复" in workbench_after,
        "hasResyncAction": "重新同步" in workbench_after,
        "hasNudgeAction": "催办" in workbench_after or "继续催办" in workbench_after,
        "hasExtendAction": "延长等待" in workbench_after,
        "hasRetryLanguage": "桌面待收口，可催办或重新同步" in workbench_after or "重新同步" in workbench_after,
        "hardFailureVisible": "执行失败" in workbench_after or "hard failed" in workbench_after,
        "internal_terms": find_visible_terms(workbench_after, INTERNAL_TERMS),
        "path_leaks": find_path_leaks(workbench_after),
        "formal_subject_count": count_subject_markers(workbench_after, FORMAL_SUBJECT_MARKERS),
        "hasContextualEvidenceAction": "证据" in workbench_after,
        "hasContextualReviewAction": any(label in workbench_after for label in ["人工确认中", "通过", "驳回", "待审", "审批"]),
    }


def capture_observability_dispatch_chain(
    cdp: object,
    args: argparse.Namespace,
    output_dir: Path,
    stamp: str,
) -> dict[str, Any]:
    url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}/observability"
    cdp.send("Page.navigate", {"url": url})
    wait_for_observability_ready(cdp, timeout_seconds=40)
    time.sleep(1.2)
    screenshot(cdp, output_dir / f"04-observability-overview-{stamp}.png")

    click_text(cdp, "打开 NPC 工作台", selector="a")
    wait_for(cdp, "location.pathname.includes('/workbench') && document.body && document.body.innerText.includes('协同工作台')", timeout_seconds=20)
    screenshot(cdp, output_dir / f"05-observability-back-to-workbench-{stamp}.png")

    cdp.send("Page.navigate", {"url": url})
    wait_for_observability_ready(cdp, timeout_seconds=30)
    obs_text = str(cdp_eval(cdp, "document.body ? document.body.innerText : ''") or "")
    blocked_clicked = click_text(cdp, "待审消息", selector="a")
    time.sleep(0.8)
    blocked_target_visible = bool(
        cdp_eval(
            cdp,
            "location.pathname.includes('/workbench') && document.body && document.body.innerText.includes('协同工作台')",
        ),
    )
    cdp.send("Page.navigate", {"url": url})
    wait_for_observability_ready(cdp, timeout_seconds=30)
    resync_clicked = click_text(cdp, "重新同步", selector="button, a")
    if resync_clicked:
        time.sleep(0.8)
        screenshot(cdp, output_dir / f"06-observability-resync-{stamp}.png")
    cdp.send("Page.navigate", {"url": url})
    wait_for_observability_ready(cdp, timeout_seconds=30)
    nudge_clicked = click_text(cdp, "催办", selector="button, a")
    if nudge_clicked:
        time.sleep(0.8)
        screenshot(cdp, output_dir / f"07-observability-nudge-{stamp}.png")
    cdp.send("Page.navigate", {"url": url})
    wait_for_observability_ready(cdp, timeout_seconds=30)
    extend_clicked = click_text(cdp, "延长等待", selector="button, a")
    if extend_clicked:
        time.sleep(0.8)
        screenshot(cdp, output_dir / f"08-observability-extend-wait-{stamp}.png")
    return {
        "hasFlowStrip": "派工证据流" in obs_text,
        "hasExceptionEntry": "异常入口" in obs_text,
        "hasContinuePrompt": "继续让 NPC 开发" in obs_text or "继续" in obs_text,
        "blocked_clicked": blocked_clicked and blocked_target_visible,
        "hasPendingCloseout": "超时收口" in obs_text or "待收口" in obs_text,
        "hasResyncAction": "重新同步" in obs_text,
        "hasNudgeAction": "催办" in obs_text or "继续催办" in obs_text,
        "resync_clicked": resync_clicked,
        "nudge_clicked": nudge_clicked,
        "extend_clicked": extend_clicked,
        "hasExtendAction": "延长等待" in obs_text,
        "hasRetryLanguage": "桌面待收口，可催办或重新同步" in obs_text or "重新同步" in obs_text,
        "hardFailureVisible": "执行失败" in obs_text or "hard failed" in obs_text,
        "internal_terms": find_visible_terms(obs_text, INTERNAL_TERMS),
        "raw_lineage_terms": find_visible_terms(obs_text, RAW_LINEAGE_TERMS),
        "raw_uuid_leaks": find_raw_uuid_leaks(obs_text),
        "path_leaks": find_path_leaks(obs_text),
        "formal_subject_count": count_subject_markers(obs_text, FORMAL_SUBJECT_MARKERS),
        "current_subject_count": count_occurrences(obs_text, "当前主体"),
        "formal_npc_count": count_occurrences(obs_text, "正式 NPC"),
        "current_only_pending_review_count": count_occurrences(obs_text, "当前待审"),
        "current_only_closeout_count": count_occurrences(obs_text, "当前待收口"),
        "historical_backlog_count": count_occurrences(obs_text, "历史积压"),
        "lineage_left_rail_present": "当前目标 / 链路" in obs_text and "先确认当前目标链是不是同一条目标。" in obs_text,
        "lineage_drawer_present": "当前目标链" in obs_text and "起点记录" in obs_text and "当前负责" in obs_text,
        "lineage_source_present": "起点记录" in obs_text and "哪次派工进入" in obs_text,
        "lineage_root_present": "汇总记录" in obs_text and "同一目标链" in obs_text,
        "lineage_delegation_present": "当前负责" in obs_text and "当前目标" in obs_text,
        "lineage_peer_details_present": "状态 / 当前链路" in obs_text and "起点记录" in obs_text and "汇总记录" in obs_text and "当前负责" in obs_text,
        "chain_members_drawer_present": "当前链路成员" in obs_text and "已挂回" in obs_text,
        "chain_member_count": count_subject_markers(obs_text, CURRENT_CHAIN_SEAT_MARKERS),
        "history_drawer_present": (
            "历史积压" in obs_text
            and (
                "历史积压已收进抽屉，不再压住当前判断。" in obs_text
                or any(
                    marker in obs_text
                    for marker in [
                        "保留给负责人复盘，不压住当前链路。",
                        "需要时回 NPC 工作台逐条重新同步或手动收口。",
                        "涉及硬件、部署、运动或写入动作时仍必须人工确认。",
                    ]
                )
            )
        ),
    }


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

    human_to_boss = latest_matching(
        messages,
        lambda item: item.get("sender_type") == "human" and str(item.get("recipient_id") or "") == "platform-npc-6",
    )
    boss_to_peer = latest_matching(
        messages,
        lambda item: str(item.get("sender_id") or "") == "platform-npc-6"
        and str(item.get("recipient_id") or "").startswith("platform-npc-")
        and str(item.get("recipient_id") or "") != "platform-npc-6",
    )
    peer_progress = latest_matching(
        messages,
        lambda item: str(item.get("sender_id") or "").startswith("platform-npc-")
        and str(item.get("sender_id") or "") != "platform-npc-6"
        and str(item.get("recipient_id") or "") == "platform-npc-6"
        and str(item.get("message_type") or "") in {"agent_progress", "agent_ack", "agent_result", "desktop_minimal_receipt"},
    )
    blocked_message = latest_matching(
        messages,
        lambda item: str(item.get("status") or "") == "pending_review" and str(item.get("recipient_id") or "") == "platform-npc-5",
    )

    boss_final = find_final_for_source(messages, str(human_to_boss.get("id") if human_to_boss else ""))
    peer_final = find_final_for_source(messages, str(boss_to_peer.get("id") if boss_to_peer else ""))
    current_seat_dispatch = find_latest_for_recipient_title(messages, "platform-npc-3", "前端截图验收脚本")
    peer_is_waiting_desktop_final = bool(
        peer_progress
        and str((peer_progress.get("metadata") or {}).get("progress_state") or "") == "awaiting_desktop_reply"
        and peer_final is None
    )
    current_chain_hard_failed = any(
        [
            is_hard_failed_current_message(human_to_boss, boss_final),
            is_hard_failed_current_message(boss_to_peer, peer_final),
            is_hard_failed_current_message(peer_progress, peer_final),
            is_hard_failed_current_message(current_seat_dispatch, None),
        ],
    )

    cdp = None
    edge_process = None
    profile_dir = None
    try:
        cdp, edge_process, profile_dir = open_browser(args, token, user_json)
        workbench = capture_workbench_dispatch_chain(cdp, args, output_dir, stamp)
        observability = capture_observability_dispatch_chain(cdp, args, output_dir, stamp)
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
    if human_to_boss is None:
        failures.append({"area": "backend", "reason": "missing latest user -> Boss dispatch"})
    if boss_to_peer is None:
        failures.append({"area": "backend", "reason": "missing latest Boss -> peer dispatch"})
    if peer_progress is None:
        failures.append({"area": "desktop-sync", "reason": "missing peer progress / desktop-visible relay"})
    if not workbench.get("overview", {}).get("hasDesktopVisibility"):
        failures.append({"area": "desktop-sync", "reason": "desktop detailed-process marker not visible in workbench"})
    if not workbench.get("overview", {}).get("hasReceiptIndex"):
        failures.append({"area": "frontend", "reason": "minimal receipt / result index not visible in workbench"})
    if int(workbench.get("overview", {}).get("tileCount") or 0) < 2:
        failures.append({"area": "frontend", "reason": "multi-NPC tile layout not visible in workbench"})
    if int(workbench.get("overview", {}).get("composerCount") or 0) < 2:
        failures.append({"area": "frontend", "reason": "multiple NPC tiles do not keep independent composers visible"})
    if not workbench.get("overview", {}).get("hasStructuredCardsInStream"):
        failures.append({"area": "frontend", "reason": "structured cards are not visibly rendered inside the workbench message stream"})
    if not workbench.get("overview", {}).get("hasLongReceiptDrawer"):
        failures.append({"area": "frontend", "reason": "long receipt drawer / expand action not visible in workbench"})
    if not workbench.get("overview", {}).get("hasNoThreadIdForm"):
        failures.append({"area": "frontend-copy", "reason": "workbench still asks the user for a desktop thread id"})
    if not workbench.get("hasBlockedAction"):
        failures.append({"area": "frontend", "reason": "blocked / pending-review action not visible in workbench"})
    if not workbench.get("hasFinalAction"):
        failures.append({"area": "frontend", "reason": "final receipt action not clickable / visible in workbench"})
    if not workbench.get("hasResyncAction"):
        failures.append({"area": "frontend", "reason": "pending-closeout resync action not visible in workbench"})
    if not workbench.get("hasNudgeAction"):
        failures.append({"area": "frontend", "reason": "pending-closeout nudge action not visible in workbench"})
    if not workbench.get("hasExtendAction"):
        failures.append({"area": "frontend", "reason": "pending-closeout extend-wait action not visible in workbench"})
    if not workbench.get("hasRetryLanguage"):
        failures.append({"area": "frontend", "reason": "workbench does not explain auto-retry / resync path in user language"})
    if not workbench.get("hasContextualEvidenceAction"):
        failures.append({"area": "frontend", "reason": "evidence entry is not kept in the same workbench context as the receipt/action card"})
    if not workbench.get("hasContextualReviewAction"):
        failures.append({"area": "frontend", "reason": "review / approval status is not visible in the same workbench context"})
    if int(workbench.get("formal_subject_count") or 0) < 2:
        failures.append({"area": "frontend-copy", "reason": "workbench does not consistently foreground formal seat / NPC names"})
    if current_chain_hard_failed and workbench.get("hardFailureVisible") and workbench.get("hasPendingCloseout"):
        failures.append({"area": "frontend", "reason": "current chain hard-failed where pending-closeout / resync should be used"})
    if not observability.get("hasExceptionEntry"):
        failures.append({"area": "frontend", "reason": "observability missing blocked entry"})
    if not observability.get("hasResyncAction"):
        failures.append({"area": "frontend", "reason": "pending-closeout resync action not visible in observability"})
    if not observability.get("hasNudgeAction"):
        failures.append({"area": "frontend", "reason": "pending-closeout nudge action not visible in observability"})
    if not observability.get("hasExtendAction"):
        failures.append({"area": "frontend", "reason": "pending-closeout extend-wait action not visible in observability"})
    if not observability.get("hasRetryLanguage"):
        failures.append({"area": "frontend", "reason": "observability does not explain auto-retry / resync path in user language"})
    if int(observability.get("formal_subject_count") or 0) < 1:
        failures.append({"area": "frontend-copy", "reason": "observability does not foreground formal seat / NPC names in current-subject cards"})
    if int(observability.get("current_subject_count") or 0) < 1 or int(observability.get("formal_npc_count") or 0) < 1:
        failures.append({"area": "frontend-copy", "reason": "observability first screen does not explicitly show current subject and formal NPC markers"})
    if int(observability.get("current_only_pending_review_count") or 0) < 1 or int(observability.get("current_only_closeout_count") or 0) < 1:
        failures.append({"area": "frontend", "reason": "observability does not keep pending review / closeout scoped to the current chain"})
    if not observability.get("lineage_left_rail_present"):
        failures.append({"area": "frontend", "reason": "observability does not expose a left rail for the current goal / lineage objects"})
    if not observability.get("lineage_drawer_present"):
        failures.append({"area": "frontend", "reason": "observability does not expose readable chain lineage as a user-visible drawer"})
    if not observability.get("lineage_source_present") or not observability.get("lineage_root_present") or not observability.get("lineage_delegation_present"):
        failures.append({"area": "frontend", "reason": "observability does not make the dispatch entry, main chain, and current handoff readable enough for QA"})
    if not observability.get("lineage_peer_details_present"):
        failures.append({"area": "frontend", "reason": "observability peer drawer does not show readable chain details for downstream NPC branches"})
    if not observability.get("chain_members_drawer_present"):
        failures.append({"area": "frontend", "reason": "observability does not show which 1/2/3/5 seats are already attached to the current target chain"})
    if int(observability.get("chain_member_count") or 0) < 4:
        failures.append({"area": "frontend", "reason": "observability does not make 1/2/3/5 target-chain membership visible enough for QA"})
    if not observability.get("history_drawer_present"):
        failures.append({"area": "frontend", "reason": "observability does not clearly fold historical backlog into a drawer instead of the current workspace"})
    for term in observability.get("raw_lineage_terms", []):
        failures.append({"area": "frontend-copy", "reason": f"user-facing observability still exposes raw chain field: {term}"})
    for value in observability.get("raw_uuid_leaks", []):
        failures.append({"area": "frontend-copy", "reason": f"user-facing observability still exposes raw record id: {value}"})
    if current_chain_hard_failed and observability.get("hardFailureVisible") and observability.get("hasPendingCloseout"):
        failures.append({"area": "frontend", "reason": "current observability chain hard-failed where pending-closeout / resync should be used"})
    if peer_is_waiting_desktop_final and not (workbench.get("hasPendingCloseout") or observability.get("hasPendingCloseout")):
        failures.append({"area": "desktop-sync", "reason": "desktop final sync lag is not surfaced as pending closeout action"})
    if is_hard_failed_current_message(current_seat_dispatch, None):
        failures.append({"area": "desktop-sync", "reason": "desktop interference path still hard-fails current acceptance dispatch"})
    for term in workbench.get("internal_terms", []):
        failures.append({"area": "frontend-copy", "reason": f"user-facing workbench exposes internal term: {term}"})
    for term in observability.get("internal_terms", []):
        failures.append({"area": "frontend-copy", "reason": f"user-facing observability exposes internal term: {term}"})
    for term in workbench.get("path_leaks", []):
        failures.append({"area": "frontend-copy", "reason": f"user-facing workbench exposes artifact/session path: {term}"})
    for term in observability.get("path_leaks", []):
        failures.append({"area": "frontend-copy", "reason": f"user-facing observability exposes artifact/session path: {term}"})

    report = {
        "verdict": "passed" if not failures else "failed",
        "project_id": args.project_id,
        "alignment": alignment,
        "paths": {
            "user_dispatch": {
                "dispatch": human_to_boss,
                "final_receipt": boss_final,
                "ok": bool(human_to_boss and boss_final),
            },
            "boss_dispatch": {
                "dispatch": boss_to_peer,
                "peer_progress": peer_progress,
                "ok": bool(boss_to_peer and peer_progress),
            },
            "npc_peer_dispatch": {
                "progress": peer_progress,
                "final_receipt": peer_final,
                "blocked": blocked_message,
                "waiting_desktop_final": peer_is_waiting_desktop_final,
                "ok": bool(peer_progress),
            },
        },
        "workbench": workbench,
        "observability": observability,
        "current_chain_hard_failed": current_chain_hard_failed,
        "stale_hard_failure_text_visible": bool(
            (workbench.get("hardFailureVisible") or observability.get("hardFailureVisible"))
            and not current_chain_hard_failed
        ),
        "screenshots": [
            str(output_dir / f"01-workbench-overview-{stamp}.png"),
            str(output_dir / f"02-workbench-desktop-visible-{stamp}.png"),
            str(output_dir / f"03-workbench-receipt-expanded-{stamp}.png"),
            str(output_dir / f"03b-workbench-resync-{stamp}.png"),
            str(output_dir / f"03c-workbench-nudge-{stamp}.png"),
            str(output_dir / f"03d-workbench-extend-wait-{stamp}.png"),
            str(output_dir / f"04-observability-overview-{stamp}.png"),
            str(output_dir / f"05-observability-back-to-workbench-{stamp}.png"),
            str(output_dir / f"06-observability-resync-{stamp}.png"),
            str(output_dir / f"07-observability-nudge-{stamp}.png"),
            str(output_dir / f"08-observability-extend-wait-{stamp}.png"),
        ],
        "failures": failures,
    }
    report_path = output_dir / f"autonomous-dispatch-click-chain-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "report": str(report_path)}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
